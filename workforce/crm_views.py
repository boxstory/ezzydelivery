# Purpose: Staff-facing CRM views — leads kanban board, list, detail, manual create, stage/field updates, WAHA inbox, link-lead-to-business, reports.
# Used by: workforce/urls.py (crm/... routes); templates in workforce/templates/workforce/crm/.
# Notes: Business logic lives in crm/services.py; JSON endpoints mirror the pricing_inquiry_update_status fetch-POST pattern.

import logging
import re
from datetime import timedelta

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.core.cache import cache
from django.db import models
from django.db.models import Count, Max, Q
from django.db.models.functions import TruncMonth
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from core.decorators import staff_required
from crm import services as crm_services
from crm import stage_rules as crm_stage_rules
from crm.models import STAGE_CACHE_KEY, InboxDismissal, Lead, LeadActivity, LeadStage
from core.validators import safe_int

logger = logging.getLogger(__name__)

# Board columns are LeadStage rows managed by staff at /workforce/crm/stages/ —
# label, order, colour, terminal-ness, how long a closed card lingers, and (on the
# driver board) which applicant condition auto-files a card there. Nothing about
# the funnel is hardcoded here any more.


def _staff_users():
    return User.objects.filter(is_staff=True).order_by('first_name', 'username')


def _parse_followup_date(raw):
    """(date_or_None, error) from a YYYY-MM-DD form value. Empty input is a
    valid 'no date'; anything unparseable returns an error instead of letting
    the raw string reach the DateField and 500 on save."""
    from django.utils.dateparse import parse_date
    raw = (raw or '').strip()
    if not raw:
        return None, ''
    try:
        parsed = parse_date(raw)
    except ValueError:
        parsed = None
    if parsed is None:
        return None, 'Invalid follow-up date — use the YYYY-MM-DD format.'
    return parsed, ''


def _filtered_leads(request):
    """Shared filter logic for board + list."""
    # Absorbed duplicates never appear on their own — they render inside their parent.
    leads = (Lead.objects.select_related('assigned_to', 'converted_business')
             .filter(merged_into__isnull=True)
             .prefetch_related('merged_children'))

    search = request.GET.get('search', '').strip()
    if search:
        leads = leads.filter(
            Q(company_name__icontains=search) |
            Q(contact_name__icontains=search) |
            Q(phone__icontains=search) |
            Q(product_category__icontains=search)
        )

    source_filter = request.GET.get('source', '').strip()
    if source_filter:
        leads = leads.filter(source=source_filter)

    category_filter = request.GET.get('category', '').strip()
    if category_filter in {c for c, _ in Lead.CATEGORY_CHOICES}:
        leads = leads.filter(category=category_filter)

    assigned_filter = request.GET.get('assigned', '').strip()
    if assigned_filter == 'me':
        leads = leads.filter(assigned_to=request.user)
    elif assigned_filter == 'none':
        leads = leads.filter(assigned_to__isnull=True)
    elif assigned_filter:
        try:
            leads = leads.filter(assigned_to_id=int(assigned_filter))
        except ValueError:
            pass

    return leads, search, source_filter, assigned_filter, category_filter


def _annotate_wa_chats(leads):
    """Bulk-set lead.has_wa_chat for leads whose phone has WhatsApp messages
    on record. Matches every identifier form the store may hold: bare digits
    with/without the 974 country code, @c.us JIDs, and anonymized @lid JIDs
    resolved via the synced WhatsAppContact directory. Three queries total.

    Deliberately spans every WAHA session: a lead counts as "has chat" whether
    they messaged our ops number or our marketing one. LID identifiers are the
    exception — a lid only means something relative to the session that issued
    it, so those are matched as (session, lid) pairs."""
    ident_map = {}   # message identifier -> [lead, ...]  (phone-based, session-independent)
    lid_map = {}     # (session, lid identifier) -> [lead, ...]
    phone_map = {}   # bare digit variant -> [lead, ...] (for lid lookup)
    for lead in leads:
        lead.has_wa_chat = False
        phone = crm_services.normalize_phone(lead.phone)
        override = crm_services.normalize_phone(getattr(lead, 'wa_chat_override', '') or '')
        variants = set()
        if phone:
            variants |= crm_services._phone_variants(phone)
        if override:
            variants.add(override)
            variants |= crm_services._phone_variants(override)
            # A manual override is an operator asserting "this identifier is
            # this lead" — honour it on any session.
            ident_map.setdefault(f'{override}@lid', []).append(lead)
        if not variants:
            continue
        for p in variants:
            phone_map.setdefault(p, []).append(lead)
            ident_map.setdefault(p, []).append(lead)
            ident_map.setdefault(f'{p}@c.us', []).append(lead)
    if not ident_map:
        return
    try:
        from whatsapp.models import WhatsAppContact, WhatsAppMessage
        lid_rows = (
            WhatsAppContact.objects
            .filter(phone__in=list(phone_map))
            .exclude(lid='')
            .values_list('session', 'lid', 'phone')
        )
        for sess, lid, phone in lid_rows:
            for ident in (lid, f'{lid}@lid'):
                lid_map.setdefault((sess, ident), []).extend(phone_map[phone])
        idents = list(ident_map) + [ident for _s, ident in lid_map]
        hits = set(
            WhatsAppMessage.objects.filter(from_number__in=idents)
            .values_list('session', 'from_number').distinct()
        ) | set(
            WhatsAppMessage.objects.filter(to_number__in=idents)
            .values_list('session', 'to_number').distinct()
        )
        for sess, ident in hits:
            for lead in ident_map.get(ident, ()):
                lead.has_wa_chat = True
            for lead in lid_map.get((sess, ident), ()):
                lead.has_wa_chat = True
    except Exception:
        logger.exception('crm: WA chat annotation failed')


@login_required(login_url='/accounts/login/')
@staff_required
def crm_leads_board(request, board_category=Lead.CATEGORY_BUSINESS):
    """Kanban pipeline board grouped by stage — one board per lead category
    (business sales pipeline vs driver recruitment pipeline)."""
    leads, search, source_filter, assigned_filter, category_filter = _filtered_leads(request)
    leads = leads.filter(category=board_category)

    is_driver_board = board_category == Lead.CATEGORY_DRIVER

    # Driver board mirrors the real applicant pool: ensure a card exists for every
    # driver application and each card's stage matches the driver's form status.
    if is_driver_board:
        try:
            crm_services.reconcile_driver_leads()
        except Exception:
            logger.exception('crm: driver lead reconcile failed')

    stage_rows = crm_services.board_stages(board_category)

    # Each terminal column decides for itself how long a closed card lingers
    # (hide_after_days); a blank one never ages a card out. Leads whose stage has
    # no column any more are always kept — they surface in the Unsorted lane.
    now = timezone.now()
    hide_map = {s.key: s.hide_after_days for s in stage_rows if s.hide_after_days}
    keep = Q(closed_at__isnull=True) | ~Q(stage__in=list(hide_map))
    for key, days in hide_map.items():
        keep |= Q(stage=key, closed_at__gte=now - timedelta(days=days))
    leads = list(leads.filter(keep).order_by('-created_at'))
    _annotate_wa_chats(leads)

    by_stage = {s.key: [] for s in stage_rows}
    for lead in leads:
        by_stage.setdefault(lead.stage, []).append(lead)

    # Once the first terminal column is reached the funnel is over — everything
    # from there on renders as a parked "bay" (no chevron, muted title) instead of
    # a flowing stage. Derived from the data so a new column styles itself.
    columns, in_bays = [], False
    for index, stage in enumerate(stage_rows):
        bucket = by_stage[stage.key]
        bay_start = stage.is_closed and not in_bays
        in_bays = in_bays or stage.is_closed
        columns.append({
            'key': stage.key,
            'label': stage.label,
            'leads': bucket,
            'count': len(bucket),
            'overdue': sum(1 for lead in bucket if lead.is_overdue),
            'swatch': stage.dot_swatch,
            'is_closed': stage.is_closed,
            'is_manual': stage.is_manual,
            'confirm_text': stage.confirm_text,
            'needs_reason': stage.needs_reason,
            'droppable': True,
            'is_first': index == 0,
            'in_bays': in_bays,
            'bay_start': bay_start,
        })

    # Cards stranded by a deleted or deactivated column — visible and draggable
    # out, never a drop target, so nothing silently disappears from the board.
    known = {s.key for s in stage_rows}
    orphans = [lead for lead in leads if lead.stage not in known]
    if orphans:
        columns.append({
            'key': '', 'label': 'Unsorted', 'leads': orphans, 'count': len(orphans),
            'overdue': sum(1 for lead in orphans if lead.is_overdue),
            'swatch': 'grey', 'is_closed': False, 'is_manual': True,
            'confirm_text': '', 'needs_reason': False, 'droppable': False,
            'is_first': not columns, 'in_bays': True, 'bay_start': False,
        })

    closed_keys = crm_services.closed_stage_keys(board_category)
    open_total = sum(c['count'] for c in columns if c['key'] not in closed_keys)
    overdue_total = sum(c['overdue'] for c in columns)
    # Headline outcome metric = the leftmost terminal column (Won / Approved).
    outcome = next((c for c in columns if c['is_closed']), None)
    window_days = max(hide_map.values()) if hide_map else None

    context = {
        'page_title': 'Driver Leads Board' if is_driver_board else 'Leads Board',
        'board_category': board_category,
        'is_driver_board': is_driver_board,
        'columns': columns,
        'open_total': open_total,
        'overdue_total': overdue_total,
        'outcome_total': outcome['count'] if outcome else 0,
        'outcome_label': outcome['label'] if outcome else 'Closed',
        'search': search,
        'source_filter': source_filter,
        'assigned_filter': assigned_filter,
        'category_filter': category_filter,
        'staff_users': _staff_users(),
        'source_choices': Lead.SOURCE_CHOICES,
        'category_choices': Lead.CATEGORY_CHOICES,
        'closed_window_days': window_days,
        'today': timezone.localdate(),
    }
    return render(request, 'workforce/crm/leads_board.html', context)


@login_required(login_url='/accounts/login/')
@staff_required
def crm_leads_list(request):
    """Filterable table of all leads."""
    from workforce.views import paginate_queryset

    leads, search, source_filter, assigned_filter, category_filter = _filtered_leads(request)

    stage_filter = request.GET.get('stage', '').strip()
    if stage_filter:
        leads = leads.filter(stage=stage_filter)

    overdue_filter = request.GET.get('overdue', '').strip()
    if overdue_filter == '1':
        leads = leads.filter(
            next_followup_at__lt=timezone.localdate()
        ).exclude(stage__in=crm_services.closed_stage_keys())

    leads = leads.order_by('-created_at')

    # Metrics scoped to the active category tab (All / Business / Drivers). The closed
    # keys are scoped to the same board: a terminal column that exists on only one
    # board would otherwise reclassify the other board's leads with the same key.
    scoped = Lead.objects.all()
    scoped_category = None
    if category_filter in {c for c, _ in Lead.CATEGORY_CHOICES}:
        scoped_category = category_filter
        scoped = scoped.filter(category=category_filter)
    scoped_closed = crm_services.closed_stage_keys(scoped_category)
    total_count = scoped.count()
    open_count = scoped.exclude(stage__in=scoped_closed).count()
    overdue_count = (
        scoped.filter(next_followup_at__lt=timezone.localdate())
        .exclude(stage__in=scoped_closed).count()
    )
    won_count = scoped.filter(stage=Lead.STAGE_WON).count()

    # Stage filter options follow the board being looked at; with no category
    # filter, show each distinct key once (the boards share most of them).
    if category_filter in {c for c, _ in Lead.CATEGORY_CHOICES}:
        stage_choices = [(s.key, s.label) for s in crm_services.board_stages(category_filter)]
    else:
        seen, stage_choices = set(), []
        for stage in LeadStage.objects.filter(is_active=True).order_by('category', 'position'):
            if stage.key in seen:
                continue
            seen.add(stage.key)
            stage_choices.append((stage.key, stage.label))
    stage_choices = stage_choices or Lead.STAGE_CHOICES

    page_obj = paginate_queryset(request, leads, items_per_page=50)

    from urllib.parse import urlencode
    filter_params = urlencode({k: v for k, v in {
        'search': search,
        'stage': stage_filter,
        'source': source_filter,
        'assigned': assigned_filter,
        'overdue': overdue_filter,
        'category': category_filter,
    }.items() if v})

    context = {
        'page_title': 'Leads',
        'page_obj': page_obj,
        'per_page': request.GET.get('per_page', '50'),
        'filter_params': filter_params,
        'search': search,
        'source_filter': source_filter,
        'assigned_filter': assigned_filter,
        'stage_filter': stage_filter,
        'overdue_filter': overdue_filter,
        'category_filter': category_filter,
        'staff_users': _staff_users(),
        'stage_choices': stage_choices,
        'source_choices': Lead.SOURCE_CHOICES,
        'category_choices': Lead.CATEGORY_CHOICES,
        'total_count': total_count,
        'open_count': open_count,
        'overdue_count': overdue_count,
        'won_count': won_count,
        'today': timezone.localdate(),
    }
    return render(request, 'workforce/crm/leads_list.html', context)


# Friendly icon + label per WAHA message_type for text-less preview rows
WA_MEDIA_LABELS = {
    'image': ('fa-image', 'Photo'),
    'sticker': ('fa-note-sticky', 'Sticker'),
    'video': ('fa-video', 'Video'),
    'audio': ('fa-microphone', 'Voice note'),
    'ptt': ('fa-microphone', 'Voice note'),
    'voice': ('fa-microphone', 'Voice note'),
    'document': ('fa-paperclip', 'Document'),
    'vcard': ('fa-address-card', 'Contact card'),
    'location': ('fa-location-dot', 'Location'),
}

_B64_BLOB_RE = re.compile(r'[A-Za-z0-9+/=\s]{80,}')


def _clean_wa_body(body):
    """Message text safe for previews. Some WAHA webhook payloads put the raw
    base64 media bytes in `body` — that renders as an endless garbage string,
    so treat it as no-text and let the media label speak instead."""
    body = (body or '').strip()
    if body.startswith('data:') or _B64_BLOB_RE.fullmatch(body):
        return ''
    return body


def _media_kind(mime, message_type):
    """Coarse media bucket for template rendering: image/audio/video/document/''."""
    m = (mime or '').lower()
    if m.startswith('image/'):
        return 'image'
    if m.startswith('audio/'):
        return 'audio'
    if m.startswith('video/'):
        return 'video'
    if m:
        return 'document'
    if message_type == 'sticker':
        return 'image'
    if message_type in ('image', 'audio', 'video', 'document'):
        return message_type
    return ''


def _lead_wa_identifiers(lead):
    """WhatsAppMessage from/to identifiers that can mean this lead's phone.

    Returns (idents, lid_pairs):
      idents    — phone-shaped identifiers (bare digits with/without the 974
                  country code, @c.us JIDs). Meaningful on any WAHA session.
      lid_pairs — {(session, lid identifier)}. A LID is issued per linked
                  device, so the same lid string on our other number belongs to
                  a different person and must only match within its session.
    """
    phone = crm_services.normalize_phone(lead.phone)
    override = crm_services.normalize_phone(getattr(lead, 'wa_chat_override', '') or '')
    idents = set()
    lid_pairs = set()
    if phone:
        idents |= crm_services._phone_variants(phone)
    if override:
        idents.add(override)
        # A manual override is an operator asserting the mapping — trust it on
        # any session rather than guessing which one they meant.
        idents.add(f'{override}@lid')
        idents |= crm_services._phone_variants(override)
    if not idents:
        return set(), set()
    try:
        from whatsapp.models import WhatsAppContact
        rows = (
            WhatsAppContact.objects
            .filter(Q(phone__in=list(idents)) | Q(lid__in=list(idents)))
            .exclude(lid='')
            .values_list('session', 'lid')
        )
        for sess, lid in rows:
            lid_pairs.add((sess, lid))
            lid_pairs.add((sess, f'{lid}@lid'))
    except Exception:
        logger.exception('crm: lid lookup failed for lead %s', lead.pk)
    for p in list(idents):
        if '@' not in p:
            idents.add(f'{p}@c.us')
    return idents, lid_pairs


def _lead_wa_q(lead, session=''):
    """Q matching every WhatsAppMessage that belongs to this lead, or None.

    Unscoped it spans all WAHA sessions on purpose — one unified customer
    history whether they wrote to our ops or marketing number — while keeping
    lid matches inside the session that issued them.

    Pass `session` to narrow to a single number. That is an AND on top of the
    identifier match, not a replacement for the per-lid scoping above: a lid
    still only counts on the session that issued it.
    """
    idents, lid_pairs = _lead_wa_identifiers(lead)
    if not idents and not lid_pairs:
        return None
    q = None
    if idents:
        ident_list = list(idents)
        q = Q(from_number__in=ident_list) | Q(to_number__in=ident_list)
    for sess, lid in lid_pairs:
        clause = Q(session=sess) & (Q(from_number=lid) | Q(to_number=lid))
        q = clause if q is None else (q | clause)
    if session:
        q = q & Q(session=session)
    return q


def _lead_wa_session_stats(lead):
    """{session: {'count', 'last_at'}} for every number this lead has talked on.

    Feeds the number picker on the detail page: without the counts, switching
    lines is a guess, and a staff member who lands on an empty number cannot
    tell "wrong number picked" from "customer never replied".
    """
    # Same platform-account gate as the conversation itself — otherwise the
    # picker would leak "this number has 412 messages" for a blocked chat.
    if crm_services.wa_read_blocked(_lead_wa_identifiers(lead)):
        return {}
    wa_q = _lead_wa_q(lead)
    if wa_q is None:
        return {}
    try:
        from whatsapp.models import WhatsAppMessage
        rows = (
            WhatsAppMessage.objects.filter(wa_q)
            .values('session')
            .annotate(count=Count('pk'), last_at=Max('received_at'))
        )
        return {r['session']: {'count': r['count'], 'last_at': r['last_at']} for r in rows}
    except Exception:
        logger.exception('crm: WA session stats failed for lead %s', lead.pk)
        return {}


def _lead_wa_conversation(lead, session=''):
    """Full WhatsApp conversation for a lead's phone, oldest first, with media
    annotations (`media_kind`, `media_proxy`) on each row. Returns
    (messages, media_items) — media_items is the photo/video subset for the
    Media panel, newest first.

    `session` narrows the thread to one of our numbers; blank keeps the merged
    all-numbers view.

    Not gated on WAHA_ENABLED (that flag gates sending): the message table is
    filled by the webhook regardless, same as the CRM inbox."""
    if not lead.phone and not lead.wa_chat_override:
        return [], []

    # A lead whose number belongs to a platform account must not expose that
    # account's conversation (it carries auth messages) — same gate as the inbox.
    if crm_services.wa_read_blocked(_lead_wa_identifiers(lead)):
        return [], []

    wa_q = _lead_wa_q(lead, session)
    if wa_q is None:
        return [], []

    try:
        from whatsapp.models import WhatsAppMessage
        from whatsapp.wa_chats_view import _extract_media

        rows = list(
            WhatsAppMessage.objects
            .filter(wa_q)
            .order_by('-received_at', '-created_at')[:200]
        )[::-1]
    except Exception:
        logger.exception('crm: failed to load WA messages for lead %s', lead.pk)
        return [], []

    messages, media_items = [], []
    for row in rows:
        media = None
        try:
            media = _extract_media(row)
        except Exception:
            pass
        has_source = bool(row.media_file) or bool((media or {}).get('url'))
        kind = (
            _media_kind(row.media_mime or (media or {}).get('mime', ''), row.message_type)
            if has_source else ''
        )
        row.media_kind = kind
        row.media_proxy = (
            reverse('workforce:crm_lead_wa_media', args=[lead.pk, row.pk])
            if kind and has_source else ''
        )
        row.body = _clean_wa_body(row.body)
        if not row.body and not row.media_proxy and row.message_type == 'text':
            continue  # empty text rows (reactions/protocol events) add noise
        messages.append(row)
        if row.media_proxy and kind in ('image', 'video'):
            media_items.append(row)

    media_items.reverse()
    return messages, media_items


def _lead_wa_session_choice(lead, requested):
    """Which number the lead page shows → (session, options, changed, explicit).

    `session` is '' for the merged all-numbers view, otherwise a WAHA session
    name. `options` is the picker payload. `changed` is True when `requested`
    is a new, valid choice the caller should persist onto the lead.

    `explicit` says whether a human chose this number or the page merely landed
    on it. Only an explicit choice may override which line a reply goes out
    from: the reading tab defaulting to the house number must not quietly move
    business-lead sends off the number configured on the Auto Triggers page —
    the client would see a different sender with nobody having asked for it.

    Precedence, and why:
      1. `requested` (?session= on the URL) — an explicit click always wins.
      2. `lead.wa_session` — the number this lead was last worked on. A driver
         switched to Ezzy6000 must still be on Ezzy6000 tomorrow.
      3. The default session (66451589) — the house number, per the ops rule.
      4. …unless the default has no messages for this lead and another number
         does. Landing on a blank panel while the real thread sits one tab away
         reads as "this lead never replied", which is the bug this picker is
         meant to end.
    """
    from whatsapp import sessions as wa_sessions

    stats = _lead_wa_session_stats(lead)
    live = wa_sessions.list_sessions()
    known = {s['name'] for s in live} | set(stats)
    default = wa_sessions.default_session()
    stored = (lead.wa_session or '').strip()

    def _valid(value):
        return value == Lead.WA_SESSION_ALL or (value in known and wa_sessions.is_valid(value))

    requested = (requested or '').strip()
    changed = bool(requested) and _valid(requested) and requested != stored
    picked = requested if (requested and _valid(requested)) else (stored if _valid(stored) else '')
    explicit = bool(picked)

    if not picked:
        if stats.get(default, {}).get('count'):
            picked = default
        elif stats:
            # Busiest-first, newest as the tiebreak — the thread most likely meant.
            # Sort on a float, not the datetime: `last_at` is None on rows that
            # never got a timestamp, and mixing None (or a naive fallback) into
            # a datetime comparison raises.
            picked = max(
                stats.items(),
                key=lambda kv: (
                    kv[1]['count'],
                    kv[1]['last_at'].timestamp() if kv[1]['last_at'] else 0.0,
                ),
            )[0]
        else:
            picked = default

    total = sum(s['count'] for s in stats.values())
    options = [{
        'name': Lead.WA_SESSION_ALL,
        'label': 'All numbers',
        'phone': '',
        'status': '',
        'count': total,
        'active': picked == Lead.WA_SESSION_ALL,
    }]
    seen = set()
    for s in live:
        seen.add(s['name'])
        options.append({
            'name': s['name'],
            'label': s['push_name'] or s['name'],
            'phone': s['phone'],
            'status': s['status'],
            'count': stats.get(s['name'], {}).get('count', 0),
            'active': picked == s['name'],
        })
    # Numbers we no longer host but still hold history for — hiding them would
    # make those messages unreachable from this page.
    for name in sorted(set(stats) - seen):
        options.append({
            'name': name,
            'label': name,
            'phone': '',
            'status': 'GONE',
            'count': stats[name]['count'],
            'active': picked == name,
        })

    return ('' if picked == Lead.WA_SESSION_ALL else picked), options, changed, explicit


def _ai_summary_available():
    """True when the ai_agent unified provider stack has a usable provider."""
    try:
        from ai_agent.services.unified_service import get_chat_service
        return get_chat_service('chat').is_available()[0]
    except Exception:
        logger.exception('crm: AI availability check failed')
        return False


@login_required(login_url='/accounts/login/')
@staff_required
def crm_lead_detail(request, lead_id):
    """Lead detail: source summary, editors, activity timeline, full WA
    conversation, shared-media gallery, AI summary."""
    lead = get_object_or_404(
        Lead.objects.select_related(
            'assigned_to', 'converted_business', 'pricing_enquiry', 'whatsapp_inquiry'
        ),
        pk=lead_id,
    )

    # Which of our numbers this conversation runs on. Persisted with .update()
    # so remembering a tab never touches updated_at — that field drives the
    # follow-up digests and must keep meaning "the lead moved".
    wa_session, wa_session_options, wa_session_changed, wa_session_explicit = (
        _lead_wa_session_choice(lead, request.GET.get('session')))
    if wa_session_changed:
        stored = wa_session or Lead.WA_SESSION_ALL
        Lead.objects.filter(pk=lead.pk).update(wa_session=stored)
        lead.wa_session = stored

    wa_messages, wa_media = _lead_wa_conversation(lead, wa_session)

    # Driver leads: keep the pipeline stage in sync with the applicant's real
    # form status (the timeline) and show driver-funnel labels + the timeline.
    driver = None
    driver_sections = None
    stage_rows = crm_services.board_stages(lead.category)
    if lead.category == Lead.CATEGORY_DRIVER:
        driver = crm_services._driver_for_lead(lead)
        if driver:
            # Cards in a manual column, or pinned by staff, stay put — same rule as the
            # board. `user=None` because this mirror is automatic: attributing it to
            # whoever opened the page put false actors in the timeline.
            manual = crm_stage_rules.manual_stage_keys(stage_rows)
            target = crm_services.driver_lead_target_stage(driver, stage_rows)
            if (target and target != lead.stage and lead.stage not in manual
                    and not lead.stage_pinned):
                crm_services.set_lead_stage(lead, target, None)
            from workforce.views import _driver_application_sections
            driver_sections = _driver_application_sections(driver)
    # LeadStage rows, not (key, label) tuples — the template needs each column's
    # confirm_text / needs_reason so the chips can prompt like the board does.
    stage_choices = stage_rows

    # Starter text for the "Send from EZZY" composer. Driver leads get the fleet
    # wording, business leads the sales one; editable on the AI Config Messages
    # tab, and '' (blank composer) when that template is switched off.
    from core.message_templates import (
        CRM_DRIVER_LEAD_MANUAL, CRM_LEAD_MANUAL, render_template,
    )
    wa_send_message = render_template(
        CRM_DRIVER_LEAD_MANUAL if lead.category == Lead.CATEGORY_DRIVER else CRM_LEAD_MANUAL,
        lead_name=lead.contact_name or lead.company_name or 'there',
        company=lead.company_name or '',
        staff_name=request.user.get_full_name() or request.user.username,
    ) or ''

    context = {
        'page_title': f'Lead – {lead.company_name or lead.contact_name or lead.phone}',
        'lead': lead,
        'activities': lead.activities.select_related('created_by').order_by('-created_at'),
        'staff_users': _staff_users(),
        'stage_choices': stage_choices,
        'driver': driver,
        'driver_sections': driver_sections,
        # "Two cards in one": what has been absorbed here, and what still could be.
        'merged_children': list(
            lead.merged_children.select_related('merged_by').order_by('created_at')
        ),
        'duplicate_candidates': crm_services.duplicate_candidates(lead),
        'wa_messages': wa_messages,
        'wa_media': wa_media,
        'wa_session': wa_session,
        'wa_session_options': wa_session_options,
        # Only a chosen number overrides the composer. Blank = keep the section
        # route from the Auto Triggers page, i.e. exactly today's behaviour.
        'wa_send_session': wa_session if wa_session_explicit else '',
        'wa_send_message': wa_send_message,
        # Across every number — lets the empty state say "the thread is on
        # another line" instead of the flatly wrong "this lead never wrote".
        'wa_total_messages': wa_session_options[0]['count'] if wa_session_options else 0,
        'ai_summary': lead.ai_summary,
        'ai_available': _ai_summary_available(),
        'today': timezone.localdate(),
    }
    return render(request, 'workforce/crm/lead_detail.html', context)


@login_required(login_url='/accounts/login/')
@staff_required
def crm_lead_ai_summary(request, lead_id):
    """POST: generate the AI summary of the lead's conversation and persist it
    on the Lead. force=1 regenerates; otherwise an existing summary is returned."""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST required'}, status=405)

    lead = get_object_or_404(Lead, pk=lead_id)

    if request.POST.get('force') != '1' and lead.ai_summary:
        return JsonResponse({'success': True, 'summary': lead.ai_summary, 'cached': True})

    wa_messages, _ = _lead_wa_conversation(lead)
    summary, error = crm_services.generate_lead_ai_summary(lead, wa_messages)
    if error:
        return JsonResponse({'success': False, 'error': error})

    lead.ai_summary = summary
    lead.ai_summary_at = timezone.now()
    lead.save(update_fields=['ai_summary', 'ai_summary_at', 'updated_at'])
    return JsonResponse({'success': True, 'summary': summary, 'cached': False})


@login_required(login_url='/accounts/login/')
@staff_required
def crm_lead_wa_media(request, lead_id, msg_id):
    """Stream a WAHA media file for a message in this lead's conversation.

    The nginx /waha/ proxy is htpasswd-gated for ops only, so CRM staff get
    media through this Django-auth proxy instead. The WAHA API key stays
    server-side."""
    from django.http import Http404

    lead = get_object_or_404(Lead, pk=lead_id)
    if not lead.phone and not lead.wa_chat_override:
        raise Http404

    from whatsapp.models import WhatsAppMessage

    wa_q = _lead_wa_q(lead)
    if wa_q is None:
        raise Http404
    msg = get_object_or_404(WhatsAppMessage.objects.filter(wa_q), pk=msg_id)
    return _stream_wa_media(msg)


@login_required(login_url='/accounts/login/')
@staff_required
def crm_wa_contact_search(request):
    """GET ?q=: typeahead search across the synced WhatsAppContact directory (phone or
    name), used by the lead-detail 'Link WhatsApp Chat' widget when auto-matching by
    the lead's stored phone missed a real chat (e.g. enquiry phone != WhatsApp number,
    or the chat is indexed by WhatsApp LID)."""
    q = request.GET.get('q', '').strip()
    if len(q) < 3:
        return JsonResponse({'results': []})

    from whatsapp.models import WhatsAppContact

    contacts = (
        WhatsAppContact.objects
        .filter(Q(phone__icontains=q) | Q(saved_name__icontains=q) | Q(push_name__icontains=q))
        .exclude(lid='')
        .order_by('-updated_at')[:15]
    )
    # `session` rides along so the link-chat POST can resolve the lid against
    # the number that actually issued it.
    results = [
        {'phone': c.phone, 'lid': c.lid, 'name': c.display_name, 'session': c.session}
        for c in contacts
    ]
    return JsonResponse({'results': results})


@login_required(login_url='/accounts/login/')
@staff_required
def crm_lead_link_chat(request, lead_id):
    """POST identifier=<phone|lid>: manually connect a lead to a WhatsApp chat when
    auto-matching by the lead's stored phone failed or picked the wrong number.
    Saves the override on the lead, then immediately pulls that chat's history in
    from WAHA (rather than waiting on the resync/cron sweep) so the conversation
    panel populates right away."""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST required'}, status=405)

    lead = get_object_or_404(Lead, pk=lead_id)
    raw_identifier = request.POST.get('identifier', '').strip()
    identifier = crm_services.normalize_phone(raw_identifier)
    if not identifier:
        return JsonResponse({'success': False, 'error': 'A phone number or contact is required'}, status=400)

    lead.wa_chat_override = identifier[:50]
    lead.save(update_fields=['wa_chat_override', 'updated_at'])

    from whatsapp.models import WhatsAppContact
    from whatsapp.waha_backfill import pull_chat_history
    from whatsapp import sessions as wa_sessions

    # Which number this chat lives on. The typeahead sends back the session of
    # the row the operator picked; a hand-typed phone falls back to the default.
    session = wa_sessions.normalize(request.POST.get('session'))

    variants = crm_services._phone_variants(identifier)
    contact = (
        WhatsAppContact.objects
        .filter(session=session)
        .filter(Q(phone__in=list(variants)) | Q(lid=identifier))
        .exclude(lid='')
        .first()
    )
    chat_id_candidates = []
    if contact:
        chat_id_candidates.append(f'{contact.lid}@lid')
    elif len(identifier) >= 12:
        # Long digit string with no directory match is most likely a raw lid, not a phone.
        chat_id_candidates.append(f'{identifier}@lid')
    best_variant = next((v for v in variants if len(v) in (8, 11)), identifier)
    chat_id_candidates.append(f'{best_variant}@c.us')

    seen = inserted = 0
    counterparties = set()
    for chat_id in chat_id_candidates:
        try:
            seen, inserted, counterparties = pull_chat_history(chat_id, session=session)
        except Exception:
            logger.exception('crm: manual link backfill failed for lead %s via %s', lead.pk, chat_id)
            continue
        if seen:
            break

    # A phone-based chatId can resolve fine in WAHA while every message inside is
    # stamped with a privacy LID we have no directory entry for yet (see lead #2,
    # 2026-07-19) — if so, re-point the override at that LID so has_wa_chat actually
    # matches, instead of leaving it pointed at a phone the stored messages don't use.
    lid_counterparties = {c for c in counterparties if c.endswith('@lid')}
    if lid_counterparties:
        resolved_lid = next(iter(lid_counterparties)).replace('@lid', '')
        if resolved_lid and resolved_lid != identifier:
            lead.wa_chat_override = resolved_lid[:50]
            lead.save(update_fields=['wa_chat_override', 'updated_at'])

    LeadActivity.objects.create(
        lead=lead, activity_type=LeadActivity.TYPE_NOTE,
        body=(
            f'WhatsApp chat manually linked ({raw_identifier})'
            + (f' — {seen} message(s) pulled in' if seen else ' — no messages found on WhatsApp yet')
        ),
        created_by=request.user,
    )

    if not seen:
        return JsonResponse({
            'success': True, 'connected': False,
            'message': 'Saved, but no WhatsApp messages were found for that number yet.',
        })

    return JsonResponse({
        'success': True, 'connected': True,
        'messages_found': seen, 'messages_inserted': inserted,
        'message': f'Connected — {seen} message(s) pulled in.',
    })


@login_required(login_url='/accounts/login/')
@staff_required
def crm_wa_media(request, msg_id):
    """Stream WAHA media for any message — used by the inbox chat preview, where no
    lead exists yet. Staff-gated, and refuses attachments from a platform account's
    own conversation: a bare pk is otherwise enough to walk the whole media table."""
    from django.http import Http404

    from whatsapp.models import WhatsAppMessage
    msg = get_object_or_404(WhatsAppMessage, pk=msg_id)
    if crm_services.wa_read_blocked([msg.from_number, msg.to_number]):
        logger.warning('crm: blocked WA media read for platform account by user %s', request.user.pk)
        raise Http404
    return _stream_wa_media(msg)


# A WhatsApp sender picks the mimetype of what they send us, and it is stored raw
# at whatsapp/waha_views.py:586. Echoing it back as the response Content-Type lets
# an outsider serve text/html or image/svg+xml from our own origin, where the CSP
# allows 'unsafe-inline' — script then runs in a staff session that reaches the
# payout and COD consoles. Only these types are ever served as themselves.
_WA_MEDIA_INLINE_TYPES = frozenset({
    'image/jpeg', 'image/png', 'image/gif', 'image/webp',
    'audio/mpeg', 'audio/ogg', 'audio/opus', 'audio/mp4', 'audio/aac', 'audio/amr',
    'video/mp4', 'video/webm', 'video/3gpp',
    'application/pdf',
})


def _safe_media_type(raw_mime):
    """Map a sender-supplied mimetype onto something safe to serve.

    Anything not explicitly allowed — notably text/html, image/svg+xml and
    application/xhtml+xml — collapses to application/octet-stream so the browser
    downloads it instead of rendering it on our origin.
    """
    mime = (raw_mime or '').split(';')[0].strip().lower()
    return mime if mime in _WA_MEDIA_INLINE_TYPES else 'application/octet-stream'


def _stream_wa_media(msg):
    """Serve a message's media: local archive first, live WAHA fetch fallback."""
    import requests as http
    from django.http import Http404, StreamingHttpResponse

    from whatsapp.wa_chats_view import _extract_media, _waha_base

    msg_id = msg.pk
    # Local archive first — WAHA purges its own media copies within minutes,
    # so the live fetch below only works for very fresh messages.
    if msg.media_file:
        try:
            from django.http import FileResponse
            served_type = _safe_media_type(msg.media_mime)
            resp = FileResponse(
                msg.media_file.open('rb'),
                content_type=served_type,
                # Anything we would not render inline is forced to download.
                as_attachment=(served_type == 'application/octet-stream'),
            )
            resp['Cache-Control'] = 'private, max-age=86400'
            resp['X-Content-Type-Options'] = 'nosniff'
            return resp
        except Exception:
            logger.exception('crm: archived media read failed for msg %s', msg_id)

    media = _extract_media(msg) or {}
    url = media.get('url') or ''
    if not url:
        raise Http404
    # _extract_media rewrites to same-origin /waha/...; undo that for the
    # server-side fetch straight to the WAHA container. Any other host is
    # refused — the URL comes from webhook payload data, and fetching it
    # server-side with the API key attached would be an SSRF hole.
    if url.startswith('/waha/'):
        url = _waha_base() + url[len('/waha'):]
    elif not url.startswith(_waha_base() + '/'):
        logger.warning('crm: refusing non-WAHA media URL for msg %s', msg_id)
        raise Http404

    try:
        upstream = http.get(
            url,
            headers={'X-Api-Key': getattr(settings, 'WAHA_API_KEY', '') or ''},
            stream=True,
            timeout=30,
        )
    except Exception:
        logger.exception('crm: WAHA media fetch failed for msg %s', msg_id)
        raise Http404
    if upstream.status_code != 200:
        raise Http404

    served_type = _safe_media_type(
        media.get('mime') or upstream.headers.get('Content-Type', '')
    )
    resp = StreamingHttpResponse(upstream.iter_content(chunk_size=64 * 1024),
                                 content_type=served_type)
    if upstream.headers.get('Content-Length'):
        resp['Content-Length'] = upstream.headers['Content-Length']
    resp['Cache-Control'] = 'private, max-age=86400'
    resp['X-Content-Type-Options'] = 'nosniff'
    if served_type == 'application/octet-stream':
        resp['Content-Disposition'] = f'attachment; filename="wa-media-{msg_id}"'
    return resp


def _wa_sender_identifiers(raw_sender, session=None):
    """Identifier set for an inbox sender string (digits, JID, or @lid alias):
    all phone variants, @c.us JIDs, and the lid mapping both ways via the
    WhatsAppContact directory.

    `session` scopes the lid lookups: a lid is issued per linked device, so
    resolving one against the wrong session would attach a stranger's phone to
    this sender. None means the default session.
    """
    raw = (raw_sender or '').strip()
    digits = raw.split('@', 1)[0]
    if not digits:
        return set()
    idents = {raw, digits} if raw else {digits}

    try:
        from whatsapp.models import WhatsAppContact
        from whatsapp import sessions as wa_sessions
        scoped = WhatsAppContact.objects.filter(session=wa_sessions.normalize(session))
        phones = set()
        if raw.endswith('@lid'):
            idents.add(f'{digits}@lid')
            contact = scoped.filter(lid=digits).first()
            if contact and contact.phone:
                phones.update(crm_services._phone_variants(contact.phone))
        else:
            phones.update(crm_services._phone_variants(crm_services.normalize_phone(digits)))
            # Bare digits can be a phone OR an unsuffixed lid — try both.
            contact = (
                scoped.filter(phone__in=list(phones)).exclude(lid='').first()
                or scoped.filter(lid=digits).first()
            )
            if contact:
                if contact.lid:
                    idents.update({contact.lid, f'{contact.lid}@lid'})
                if contact.phone:
                    phones.update(crm_services._phone_variants(contact.phone))
        for p in phones:
            idents.update({p, f'{p}@c.us'})
    except Exception:
        logger.exception('crm: sender ident expansion failed for %s', raw_sender)
    return idents


@login_required(login_url='/accounts/login/')
@staff_required
def crm_wa_chat_preview(request):
    """JSON conversation preview for an inbox sender (before any lead exists).

    GET ?sender=<from_number as shown in the inbox row>&session=<name> — returns
    the last 100 messages both directions with media annotations for the modal.
    Scoped to one session: the inbox row came from a specific number, and an
    @lid sender means nothing outside the session that issued it."""
    from whatsapp.models import WhatsAppMessage
    from whatsapp.wa_chats_view import _extract_media
    from whatsapp import sessions as wa_sessions

    session = wa_sessions.from_request(request)
    idents = _wa_sender_identifiers(request.GET.get('sender', ''), session=session)
    if not idents:
        return JsonResponse({'success': False, 'error': 'sender is required'}, status=400)

    # AUTHORIZATION, not filtering: `sender` comes straight from the query string, so
    # without this any CRM-capable staff member could read a platform user's own
    # conversation — including the password-reset codes we send them.
    blocked = crm_services.wa_read_blocked(idents)
    if blocked:
        logger.warning('crm: blocked WA chat read for platform account by user %s', request.user.pk)
        return JsonResponse({'success': False, 'error': blocked}, status=403)

    rows = list(
        WhatsAppMessage.objects
        .filter(session=session)
        .filter(Q(from_number__in=idents) | Q(to_number__in=idents))
        .order_by('-received_at', '-created_at')[:100]
    )[::-1]

    messages = []
    for row in rows:
        media = None
        try:
            media = _extract_media(row)
        except Exception:
            pass
        has_source = bool(row.media_file) or bool((media or {}).get('url'))
        kind = (
            _media_kind(row.media_mime or (media or {}).get('mime', ''), row.message_type)
            if has_source else ''
        )
        body = _clean_wa_body(row.body)
        if not body and not kind and row.message_type == 'text':
            continue
        messages.append({
            'direction': row.direction,
            'body': body,
            'type': row.message_type,
            'media_kind': kind,
            'media_url': reverse('workforce:crm_wa_media', args=[row.pk]) if kind else '',
            'time': (
                timezone.localtime(row.received_at).strftime('%d %b, %H:%M')
                if row.received_at else ''
            ),
        })
    return JsonResponse({'success': True, 'messages': messages})


@login_required(login_url='/accounts/login/')
@staff_required
def crm_lead_create(request):
    """Manual lead creation form."""
    if request.method == 'POST':
        company_name = request.POST.get('company_name', '').strip()
        contact_name = request.POST.get('contact_name', '').strip()
        phone = crm_services.normalize_phone(request.POST.get('phone', ''))
        if not (company_name or contact_name or phone):
            context = {
                'page_title': 'New Lead',
                'staff_users': _staff_users(),
                'error': 'Provide at least a company, contact name, or phone number.',
                'form_data': request.POST,
                'category_choices': Lead.CATEGORY_CHOICES,
                'initial_category': request.POST.get('category', Lead.CATEGORY_BUSINESS),
            }
            return render(request, 'workforce/crm/lead_form.html', context)

        followup, date_error = _parse_followup_date(request.POST.get('next_followup_at'))
        if date_error:
            context = {
                'page_title': 'New Lead',
                'staff_users': _staff_users(),
                'error': date_error,
                'form_data': request.POST,
                'category_choices': Lead.CATEGORY_CHOICES,
                'initial_category': request.POST.get('category', Lead.CATEGORY_BUSINESS),
            }
            return render(request, 'workforce/crm/lead_form.html', context)

        category = request.POST.get('category', '').strip()
        if category not in {c for c, _ in Lead.CATEGORY_CHOICES}:
            category = Lead.CATEGORY_BUSINESS
        lead = Lead.objects.create(
            source=Lead.SOURCE_MANUAL,
            category=category,
            company_name=company_name[:200],
            contact_name=contact_name[:100],
            phone=phone[:50],
            product_category=request.POST.get('product_category', '').strip()[:200],
            notes=request.POST.get('notes', '').strip(),
            next_followup_at=followup,
        )
        assigned_to_id = request.POST.get('assigned_to', '').strip()
        if assigned_to_id:
            try:
                lead.assigned_to = User.objects.get(pk=int(assigned_to_id))
                lead.save(update_fields=['assigned_to', 'updated_at'])
            except (User.DoesNotExist, ValueError):
                pass
        LeadActivity.objects.create(
            lead=lead, activity_type=LeadActivity.TYPE_NOTE,
            body='Lead created manually', created_by=request.user,
        )
        return redirect('workforce:crm_lead_detail', lead.pk)

    initial_category = request.GET.get('category', '').strip()
    if initial_category not in {c for c, _ in Lead.CATEGORY_CHOICES}:
        initial_category = Lead.CATEGORY_BUSINESS
    context = {
        'page_title': 'New Lead',
        'staff_users': _staff_users(),
        'category_choices': Lead.CATEGORY_CHOICES,
        'initial_category': initial_category,
    }
    return render(request, 'workforce/crm/lead_form.html', context)


@login_required(login_url='/accounts/login/')
@staff_required
def crm_lead_update_stage(request, lead_id):
    """AJAX: move a lead to a new pipeline stage (board drag-drop + detail page)."""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    lead = get_object_or_404(Lead, pk=lead_id)
    new_stage = request.POST.get('stage', '').strip()
    rejection_reason = request.POST.get('rejection_reason', '').strip()

    # A column that rewrites the driver's real verification status is the same
    # privilege as the ops-only verification page (it activates vehicles and WhatsApps
    # the applicant). This route is reachable by Marketing, so re-check the desk here
    # rather than letting the board be a way around the department gate.
    target_stage = crm_services.get_stage(lead.category, new_stage)
    if lead.category == Lead.CATEGORY_DRIVER and target_stage and target_stage.write_back:
        from core.departments import ADMIN, OPS, user_departments
        if not (user_departments(request.user) & {OPS, ADMIN}):
            return JsonResponse({
                'success': False,
                'error': (
                    f'"{target_stage.label}" changes the driver\'s real application status '
                    'and notifies them, so it needs the Operations desk. Ask ops to make '
                    'this decision, or move the card to a column that does not write back.'
                ),
            }, status=403)

    try:
        crm_services.set_lead_stage(lead, new_stage, request.user)
    except ValueError as exc:
        return JsonResponse({'success': False, 'error': str(exc)}, status=400)

    # Driver leads: moving into a decision column updates the real applicant
    synced_driver = None
    sync_failed = False
    try:
        driver = crm_services.sync_driver_status_from_lead(
            lead, request.user, rejection_reason=rejection_reason
        )
        synced_driver = driver.driver_id if driver else None
    except Exception:
        logger.exception('crm: driver status sync failed for lead %s', lead.pk)
        sync_failed = True

    # Staff were told "this will approve this driver" — if the write-back reached
    # nobody, say so instead of reporting a success that changed nothing.
    if target_stage and target_stage.write_back and not synced_driver:
        note = (
            'the driver record could not be updated (see server logs)' if sync_failed
            else 'no driver record matches this number, so nothing was sent to an applicant'
        )
        warning_prefix = f'The card moved, but {note}. '
    else:
        warning_prefix = ''

    # A manual move only needs pinning when it DISAGREES with the driver's application
    # status — checked after the write-back, so a column that just set the driver to
    # match (Approved, Rejected, back-to-queue) keeps auto-filing instead of freezing.
    conflict = crm_services.stage_move_conflict(lead, target_stage)
    warning = ''
    if conflict:
        crm_services.pin_lead_stage(lead, request.user, conflict)
        warning = (
            f'{conflict} The card is pinned here and will stay put — use "Resume '
            'auto-filing" on the lead page to hand it back to the application status.'
        )
    elif lead.stage_pinned:
        # It agrees again, so there is nothing left to protect it from.
        crm_services.unpin_lead_stage(lead, request.user)

    warning = f'{warning_prefix}{warning}'.strip()

    return JsonResponse({
        'success': True,
        'stage': lead.stage,
        'stage_display': lead.stage_label,
        'stage_swatch': lead.stage_swatch,
        'synced_driver': synced_driver,
        'pinned': lead.stage_pinned,
        'warning': warning,
    })


@login_required(login_url='/accounts/login/')
@staff_required
def crm_lead_unpin_stage(request, lead_id):
    """AJAX: hand a pinned driver card back to automatic filing."""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST required'}, status=405)
    lead = get_object_or_404(Lead, pk=lead_id)
    crm_services.unpin_lead_stage(lead, request.user)

    # Tell staff where it is about to go, so "resume" is not a blind action.
    moves_to = ''
    if lead.category == Lead.CATEGORY_DRIVER:
        stages = crm_services.board_stages(Lead.CATEGORY_DRIVER)
        driver = crm_services._driver_for_lead(lead)
        target = crm_stage_rules.target_stage_key(driver, stages) if driver else None
        if target and target != lead.stage:
            moves_to = next((s.label for s in stages if s.key == target), target)

    return JsonResponse({'success': True, 'pinned': False, 'moves_to': moves_to})


@login_required(login_url='/accounts/login/')
@staff_required
def crm_lead_update(request, lead_id):
    """AJAX: update assignee, follow-up date, notes, and contact fields."""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    lead = get_object_or_404(Lead, pk=lead_id)

    changes = []

    if 'assigned_to' in request.POST:
        assigned_to_id = request.POST.get('assigned_to', '').strip()
        if assigned_to_id == '':
            if lead.assigned_to_id is not None:
                lead.assigned_to = None
                changes.append(('assignment', 'Assignment cleared'))
        else:
            try:
                user = User.objects.get(pk=int(assigned_to_id))
                if lead.assigned_to_id != user.pk:
                    lead.assigned_to = user
                    changes.append((
                        'assignment',
                        f'Assigned to {user.get_full_name() or user.username}',
                    ))
            except (User.DoesNotExist, ValueError):
                pass

    if 'next_followup_at' in request.POST:
        new_date, date_error = _parse_followup_date(request.POST.get('next_followup_at'))
        if date_error:
            return JsonResponse({'success': False, 'error': date_error}, status=400)
        if new_date != lead.next_followup_at:
            lead.next_followup_at = new_date
            changes.append((
                'followup',
                f'Follow-up date set to {new_date.isoformat()}' if new_date else 'Follow-up date cleared',
            ))

    if 'notes' in request.POST:
        notes = request.POST.get('notes', '').strip()
        if notes != (lead.notes or ''):
            lead.notes = notes
            changes.append(('note', 'Notes updated'))

    for field, max_len in (('company_name', 200), ('contact_name', 100),
                           ('product_category', 200)):
        if field in request.POST:
            value = request.POST.get(field, '').strip()[:max_len]
            if value != getattr(lead, field):
                setattr(lead, field, value)
                changes.append(('note', f'{field.replace("_", " ").title()} updated'))

    if 'phone' in request.POST:
        phone = crm_services.normalize_phone(request.POST.get('phone', ''))[:50]
        if phone != lead.phone:
            lead.phone = phone
            changes.append(('note', 'Phone updated'))

    if changes:
        lead.save()
        activity_type = changes[0][0] if len(changes) == 1 else LeadActivity.TYPE_NOTE
        if activity_type not in {t for t, _ in LeadActivity.TYPE_CHOICES}:
            activity_type = LeadActivity.TYPE_NOTE
        LeadActivity.objects.create(
            lead=lead, activity_type=activity_type,
            body='; '.join(body for _, body in changes),
            created_by=request.user,
        )

    return JsonResponse({
        'success': True,
        'changes': len(changes),
        'assigned_to': (lead.assigned_to.get_full_name() or lead.assigned_to.username)
                       if lead.assigned_to else '',
        'next_followup_at': lead.next_followup_at.isoformat() if lead.next_followup_at else '',
    })


@login_required(login_url='/accounts/login/')
@staff_required
def crm_lead_add_activity(request, lead_id):
    """AJAX: append a note/follow-up to the lead timeline."""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    lead = get_object_or_404(Lead, pk=lead_id)
    body = request.POST.get('body', '').strip()
    if not body:
        return JsonResponse({'success': False, 'error': 'Activity text is required'}, status=400)
    activity_type = request.POST.get('activity_type', LeadActivity.TYPE_NOTE)
    if activity_type not in {t for t, _ in LeadActivity.TYPE_CHOICES}:
        activity_type = LeadActivity.TYPE_NOTE
    activity = LeadActivity.objects.create(
        lead=lead, activity_type=activity_type, body=body, created_by=request.user,
    )
    return JsonResponse({
        'success': True,
        'activity': {
            'id': activity.pk,
            'type': activity.activity_type,
            'type_display': activity.get_activity_type_display(),
            'body': activity.body,
            'created_by': request.user.get_full_name() or request.user.username,
            'created_at': timezone.localtime(activity.created_at).strftime('%d %b, %H:%M'),
        },
    })


@login_required(login_url='/accounts/login/')
@staff_required
def crm_lead_delete_activity(request, lead_id, activity_id):
    """AJAX: delete an activity (creator or superadmin only)."""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    activity = get_object_or_404(LeadActivity, pk=activity_id, lead_id=lead_id)
    is_superadmin = getattr(getattr(request.user, 'profile', None), 'is_superadmin', False)
    if activity.created_by_id != request.user.pk and not is_superadmin:
        return JsonResponse({'success': False, 'error': 'Not allowed'}, status=403)
    activity.delete()
    return JsonResponse({'success': True})


@login_required(login_url='/accounts/login/')
@staff_required
def crm_lead_link_business(request):
    """AJAX (business verification page): attach an open CRM lead to a real
    Business account. Marks the lead Won and logs who linked it."""
    from business.models import Business

    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    try:
        lead_id = safe_int(request.POST.get('lead_id'), default=0, minimum=0)
        business_id = safe_int(request.POST.get('business_id'), default=0, minimum=0)
    except ValueError:
        return JsonResponse({'success': False, 'error': 'lead_id and business_id are required'}, status=400)

    lead = get_object_or_404(Lead, pk=lead_id)
    business = get_object_or_404(Business, pk=business_id)
    if lead.category != Lead.CATEGORY_BUSINESS:
        return JsonResponse({'success': False, 'error': 'Driver leads cannot be linked to a business'}, status=400)

    try:
        linked, error = crm_services.link_lead_to_business(lead, business, request.user)
    except Exception:
        logger.exception('crm: link failed for lead %s -> business %s', lead_id, business_id)
        return JsonResponse({'success': False, 'error': 'Linking failed'}, status=500)
    if not linked:
        return JsonResponse({'success': False, 'error': error}, status=400)
    return JsonResponse({
        'success': True,
        'lead_id': lead.pk,
        'lead_url': reverse('workforce:crm_lead_detail', args=[lead.pk]),
    })


@login_required(login_url='/accounts/login/')
@staff_required
def crm_whatsapp_inbox(request):
    """Inbound WAHA senders not yet known: promote to lead or dismiss."""
    from workforce.views import paginate_queryset
    from whatsapp import sessions as wa_sessions

    waha_enabled = getattr(settings, 'WAHA_ENABLED', False)

    # Which of our numbers to show. Defaults to ALL of them: any number can
    # produce a lead, and hiding one behind a tab would silently lose them.
    # ?session=<name> narrows to one.
    wa_session_list = wa_sessions.list_sessions()
    requested = (request.GET.get('session', '') or '').strip()
    session_filter = (
        wa_sessions.normalize(requested)
        if requested and requested.lower() != 'all'
        else ''
    )

    # Live session status banner — which number the WAHA bridge is connected to
    waha_session = None
    try:
        from whatsapp.waha_views import fetch_waha_session_status
        waha_session = fetch_waha_session_status(session=session_filter or None)
    except Exception:
        logger.exception('crm: WAHA session status fetch failed')

    rows = []
    search = request.GET.get('search', '').strip()

    try:
        from whatsapp.models import WhatsAppMessage
        # 'system' rows are encryption notices and the like — a sender with no
        # message. Counting them here put ~74 people in the triage queue who
        # had never written to us.
        inbound = WhatsAppMessage.objects.filter(direction='inbound').exclude(message_type='system')
        if session_filter:
            inbound = inbound.filter(session=session_filter)
        grouped = (
            inbound
            .exclude(from_number='')
            # Groups and status broadcasts are not promotable senders
            .exclude(from_number__contains='-')
            .exclude(from_number__contains='@g.us')
            .exclude(from_number__istartswith='status')
            # Grouped per session, not per bare identifier: an @lid sender only
            # identifies someone relative to the number that received it, so the
            # same lid on our other number is a different person.
            .values('session', 'from_number')
            .annotate(last_at=Max('received_at'), msg_count=Count('id'))
            .order_by('-last_at')
        )
        if search:
            # Senders are stored under the id WhatsApp delivered them as, which
            # for almost every modern sender is an @lid — never the number the
            # row displays. Matching the raw id alone meant searching the very
            # number on screen returned "no unknown senders", so the term is
            # resolved through the contact directory (and names) first.
            from whatsapp.models import WhatsAppContact
            search_digits = ''.join(ch for ch in search if ch.isdigit())
            contact_q = Q(saved_name__icontains=search) | Q(push_name__icontains=search)
            if search_digits:
                contact_q |= Q(phone__icontains=search_digits) | Q(lid__icontains=search_digits)
            search_digit_ids = set()
            for c in WhatsAppContact.objects.filter(contact_q).only('phone', 'lid'):
                search_digit_ids.update(d for d in (c.phone, c.lid) if d)
            # The directory only covers senders the contact cron has seen. Rows
            # resolved live off WAHA's lids API would still be unfindable, so
            # search the same (cached) map the row rendering uses.
            if search_digits:
                try:
                    from whatsapp.wa_chats_view import _lid_map, _waha_base
                    api_key = getattr(settings, 'WAHA_API_KEY', '') or ''
                    scope = [session_filter] if session_filter else [
                        s['name'] for s in wa_session_list
                    ]
                    for sess in scope:
                        for lid, phone in _lid_map(_waha_base(), sess, api_key).items():
                            if search_digits in phone:
                                search_digit_ids.update({lid, phone})
                except Exception:
                    logger.exception('crm: inbox search lid lookup failed')
            # Both id shapes: the webhook strips the @suffix, the backfill keeps it.
            search_ids = set()
            for d in search_digit_ids:
                search_ids.update({d, f'{d}@lid', f'{d}@c.us'})
            match = Q(from_number__icontains=search)
            if search_ids:
                match |= Q(from_number__in=search_ids)
            grouped = grouped.filter(match)
        grouped = [
            r for r in grouped
            # Newer-style group ids: 120363-prefixed and far longer than any phone
            if not (r['from_number'].split('@', 1)[0].startswith('120363')
                    and len(r['from_number'].split('@', 1)[0]) > 15)
        ]

        # Resolve EVERY sender id against the synced contact directory by its
        # digits part — @lid JIDs, bare lid digits (webhook variants store
        # them without the suffix), @c.us JIDs, and bare phones all match, so
        # saved chats/contacts supply the real number + name.
        lid_pn = {}          # (session, lid digits) -> real phone
        contact_names = {}
        sender_digits = {r['from_number'].split('@', 1)[0] for r in grouped}
        try:
            from whatsapp.models import WhatsAppContact
            directory = WhatsAppContact.objects.filter(
                Q(lid__in=sender_digits) | Q(phone__in=sender_digits)
            )
            for c in directory:
                if c.lid:
                    lid_pn[(c.session, c.lid)] = c.phone
                if c.display_name:
                    contact_names[c.phone] = c.display_name
        except Exception:
            logger.exception('crm: contact directory lookup failed')
        # Digits that still look like lids (too long for a phone, no mapping
        # yet) — fall back to WAHA's lids API, once per session on screen.
        missing_by_session = {}
        for r in grouped:
            d = r['from_number'].split('@', 1)[0]
            if (r['session'], d) not in lid_pn and d.isdigit() and len(d) > 13:
                missing_by_session.setdefault(r['session'], set()).add(d)
        if missing_by_session:
            try:
                from whatsapp.wa_chats_view import _lid_map, _waha_base
                api_key = getattr(settings, 'WAHA_API_KEY', '') or ''
                for sess, lids in missing_by_session.items():
                    waha_map = _lid_map(_waha_base(), sess, api_key)
                    for lid in lids:
                        if lid in waha_map:
                            lid_pn[(sess, lid)] = waha_map[lid]
            except Exception:
                logger.exception('crm: lid map fetch failed')

        business_numbers = set(
            WhatsAppMessage.objects
            .filter(direction='inbound', business__isnull=False)
            .values_list('from_number', flat=True).distinct()
        )
        # Expand each dismissal to all digit variants (with/without 974) so a
        # sender can't resurface under a different identifier form. Raw values
        # kept too for legacy rows and lid-only dismissals.
        dismissed_numbers = set()
        for dismissed in InboxDismissal.objects.values_list('phone', flat=True):
            dismissed_numbers.add(dismissed)
            normalized_dismissed = crm_services.normalize_phone(dismissed)
            if normalized_dismissed:
                dismissed_numbers.update(crm_services._phone_variants(normalized_dismissed))

        from core.models import Profile
        profile_numbers = set()
        for phone, whatsapp in Profile.objects.exclude(
            phone='', whatsapp=''
        ).values_list('phone', 'whatsapp'):
            for value in (phone, whatsapp):
                normalized = crm_services.normalize_phone(value)
                if normalized:
                    profile_numbers.add(normalized)

        # Keyed by every digit variant (with/without 974) so a lead saved as
        # '55512345' still matches an inbox sender '97455512345' and vice versa.
        open_leads = {}
        for phone, pk in (
            Lead.objects.filter(merged_into__isnull=True)
            .exclude(stage__in=crm_services.closed_stage_keys())
            .exclude(phone='').order_by('created_at').values_list('phone', 'pk')
        ):
            normalized_lead = crm_services.normalize_phone(phone)
            if not normalized_lead:
                continue
            for variant in crm_services._phone_variants(normalized_lead):
                open_leads[variant] = pk

        for row in grouped:
            number = row['from_number']
            digits = number.split('@', 1)[0]
            real = lid_pn.get((row['session'], digits))
            if real == digits:
                real = None  # sender already displays as its own phone
            if real:
                row['real_number'] = real
            check = real or number
            row['contact_name'] = contact_names.get(real or digits, '')
            candidates = {number, check}
            normalized = crm_services.normalize_phone(check)
            if normalized:
                candidates.update(crm_services._phone_variants(normalized))
            if candidates & (business_numbers | dismissed_numbers):
                continue
            if normalized in profile_numbers:
                continue
            row['existing_lead_id'] = open_leads.get(normalized)
            rows.append(row)
    except Exception:
        logger.exception('crm: WA inbox query failed')

    page_obj = paginate_queryset(request, rows, items_per_page=25)

    from whatsapp.models import WhatsAppMessage as _WM
    for row in page_obj:
        last = (
            _WM.objects.filter(
                direction='inbound',
                session=row['session'],
                from_number=row['from_number'],
            )
            .order_by('-received_at').first()
        )
        row['last_body'] = _clean_wa_body(last.body)[:160] if last else ''
        row['last_type'] = last.message_type if last else ''
        icon_label = WA_MEDIA_LABELS.get(row['last_type'])
        if not row['last_body'] and icon_label:
            row['last_media_icon'], row['last_media_label'] = icon_label

    from urllib.parse import urlencode
    filter_params = {k: v for k, v in (('search', search), ('session', session_filter)) if v}
    context = {
        'page_title': 'WhatsApp Inbox',
        'page_obj': page_obj,
        'search': search,
        'waha_enabled': waha_enabled,
        'waha_session': waha_session,
        # Tab strip is only worth rendering once a second number is linked.
        'wa_sessions': wa_session_list if len(wa_session_list) > 1 else [],
        'wa_session_filter': session_filter,
        'per_page': request.GET.get('per_page', '25'),
        'filter_params': urlencode(filter_params) if filter_params else '',
    }
    return render(request, 'workforce/crm/whatsapp_inbox.html', context)


@login_required(login_url='/accounts/login/')
@staff_required
def crm_wa_promote(request):
    """AJAX: create (or reuse) a lead from an inbound WhatsApp number."""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    phone = request.POST.get('phone', '').strip()
    category = (
        Lead.CATEGORY_DRIVER
        if request.POST.get('category') == Lead.CATEGORY_DRIVER
        else Lead.CATEGORY_BUSINESS
    )
    try:
        lead, created = crm_services.create_lead_from_wa_number(
            phone, request.user, category=category,
        )
    except ValueError as exc:
        return JsonResponse({'success': False, 'error': str(exc)}, status=400)
    return JsonResponse({
        'success': True,
        'created': created,
        'lead_id': lead.pk,
        'lead_url': reverse('workforce:crm_lead_detail', args=[lead.pk]),
    })


@login_required(login_url='/accounts/login/')
@staff_required
def crm_wa_dismiss(request):
    """AJAX: mark an inbound WhatsApp number as not-a-lead (hidden from inbox)."""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    phone = request.POST.get('phone', '').strip()
    if not phone:
        return JsonResponse({'success': False, 'error': 'Phone required'}, status=400)
    # Store the digits-only form so '974...@c.us' and '+974 ...' variants all
    # collapse to one dismissal (lid-only senders keep their raw string).
    normalized = crm_services.normalize_phone(phone) or phone
    InboxDismissal.objects.get_or_create(
        phone=normalized[:50], defaults={'dismissed_by': request.user},
    )
    return JsonResponse({'success': True})


@login_required(login_url='/accounts/login/')
@staff_required
def crm_wa_resync(request):
    """AJAX: pull recent WAHA chats into WhatsAppMessage so the inbox picks up
    senders whose messages never arrived via webhook (bridge downtime, etc.)."""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    # Like the webhook, this only needs the bridge configured — WAHA_ENABLED
    # gates order-notification routing, not the inbox.
    if not getattr(settings, 'WAHA_API_KEY', ''):
        return JsonResponse({'success': False, 'error': 'WAHA bridge is not configured'}, status=400)

    import time as _time
    from whatsapp.management.commands.backfill_waha import upsert_message, waha_get
    from whatsapp import sessions as wa_sessions

    # Sweeps every linked number: the inbox spans all of them, so resyncing
    # only one would leave the other's senders invisible. ?session=<name>
    # narrows it when an operator is chasing one number.
    requested = (request.POST.get('session') or request.GET.get('session') or '').strip()
    if requested and requested.lower() != 'all':
        session_names = [wa_sessions.normalize(requested)]
    else:
        session_names = [s['name'] for s in wa_sessions.list_sessions()]

    started = _time.monotonic()
    budget_s = 20  # stay well inside gunicorn's 30s window

    scanned = 0
    inserted = 0
    partial = False
    listed_any = False
    for session in session_names:
        if _time.monotonic() - started > budget_s:
            partial = True
            break
        try:
            chats = waha_get(f'/api/{session}/chats', params={'limit': 40}, timeout=15)
            listed_any = True
        except Exception as exc:
            logger.warning('crm resync: chat list failed for %s: %s', session, exc)
            continue

        for chat in chats if isinstance(chats, list) else []:
            cid = chat.get('id') if isinstance(chat, dict) else None
            if isinstance(cid, dict):
                cid = cid.get('_serialized')
            if not cid or str(cid).endswith('@g.us'):
                continue  # inbox tracks direct senders only
            if _time.monotonic() - started > budget_s:
                partial = True
                break
            try:
                msgs = waha_get(
                    f'/api/{session}/chats/{cid}/messages',
                    params={'limit': 15, 'downloadMedia': 'false'},
                    timeout=10,
                )
            except Exception:
                continue
            scanned += 1
            for m in msgs if isinstance(msgs, list) else []:
                if not isinstance(m, dict) or not m.get('id'):
                    continue
                try:
                    _obj, created = upsert_message(m, session, cid)
                    if created:
                        inserted += 1
                except Exception:
                    logger.exception('crm resync: upsert failed for %s', m.get('id'))

    if not listed_any:
        return JsonResponse(
            {'success': False, 'error': 'WAHA unreachable — could not list chats'},
            status=502,
        )

    # Refresh the contact directory too, but only with time left in the
    # budget — no Celery worker runs in this deployment, so it's inline here
    # (steady-state ~5s) with a daily cron as the freshness backstop.
    contacts_sync = 'skipped'
    if not partial and _time.monotonic() - started < budget_s:
        created_n = updated_n = 0
        try:
            from whatsapp.contacts import sync_contacts
            for session in session_names:
                if _time.monotonic() - started >= budget_s:
                    break
                cres = sync_contacts(session=session)
                created_n += cres['created']
                updated_n += cres['updated']
            contacts_sync = f"{created_n} new, {updated_n} updated"
        except Exception:
            logger.exception('crm resync: contact sync failed')
            contacts_sync = 'failed'

    return JsonResponse({
        'success': True,
        'chats_scanned': scanned,
        'new_messages': inserted,
        'partial': partial,
        'contacts_sync': contacts_sync,
    })


@login_required(login_url='/accounts/login/')
@staff_required
def crm_contacts(request):
    """Synced WhatsApp contact directory — phone ↔ lid ↔ name reference.

    Defaults to rows with a name or address-book membership; ?all=1 shows the
    full directory (thousands of bare lid mappings).
    """
    from workforce.views import paginate_queryset
    from whatsapp.models import WhatsAppContact

    search = request.GET.get('search', '').strip()
    show_all = request.GET.get('all') == '1'

    qs = WhatsAppContact.objects.all()
    if search:
        qs = qs.filter(
            Q(phone__icontains=search) | Q(lid__icontains=search) |
            Q(saved_name__icontains=search) | Q(push_name__icontains=search)
        )
    elif not show_all:
        qs = qs.filter(
            Q(is_my_contact=True) | ~Q(saved_name='') | ~Q(push_name='')
        )
    qs = qs.order_by('-is_my_contact', '-updated_at')

    page_obj = paginate_queryset(request, qs, items_per_page=50)
    last_sync = (
        WhatsAppContact.objects.exclude(synced_at=None)
        .order_by('-synced_at').values_list('synced_at', flat=True).first()
    )

    from urllib.parse import urlencode
    params = {}
    if search:
        params['search'] = search
    if show_all:
        params['all'] = '1'
    context = {
        'page_title': 'WhatsApp Contacts',
        'page_obj': page_obj,
        'search': search,
        'show_all': show_all,
        # Only worth labelling the session once more than one number is linked.
        'wa_multi_session': (
            WhatsAppContact.objects.values('session').distinct().count() > 1
        ),
        'total_count': WhatsAppContact.objects.count(),
        'last_sync': last_sync,
        'per_page': request.GET.get('per_page', '50'),
        'filter_params': urlencode(params),
    }
    return render(request, 'workforce/crm/contacts.html', context)


@login_required(login_url='/accounts/login/')
@staff_required
def crm_reports(request):
    """Funnel and conversion stats across the leads pipeline."""
    today = timezone.localdate()

    stage_counts = {
        (row['category'], row['stage']): row['n']
        for row in Lead.objects.values('category', 'stage').annotate(n=Count('id'))
    }
    # One funnel PER BOARD. Merging them produced a nonsense column set: the boards
    # share stage keys but not meanings, so "Quoted" and "Uploads Completed" were being
    # added together under whichever label happened to come first.
    funnels = []
    for category, category_label in Lead.CATEGORY_CHOICES:
        rows = [
            {
                'key': stage.key,
                'label': stage.label,
                'count': stage_counts.get((category, stage.key), 0),
                'is_closed': stage.is_closed,
            }
            for stage in LeadStage.board_columns(category)
        ]
        if not rows:
            rows = [
                {'key': key, 'label': label,
                 'count': stage_counts.get((category, key), 0), 'is_closed': False}
                for key, label in Lead.STAGE_CHOICES
            ]
        total = sum(r['count'] for r in rows)
        funnels.append({
            'category': category,
            'label': category_label,
            'rows': rows,
            'total': total,
            'peak': max((r['count'] for r in rows), default=0),
        })

    twelve_months_ago = (today.replace(day=1) - timedelta(days=365))
    monthly = (
        Lead.objects.filter(created_at__date__gte=twelve_months_ago)
        .annotate(month=TruncMonth('created_at'))
        .values('month', 'source')
        .annotate(n=Count('id'))
        .order_by('month')
    )
    months = sorted({row['month'].strftime('%Y-%m') for row in monthly})
    source_labels = dict(Lead.SOURCE_CHOICES)
    counts_by_source = {}
    for row in monthly:
        counts_by_source.setdefault(row['source'], {})[row['month'].strftime('%Y-%m')] = row['n']
    # Series in fixed SOURCE_CHOICES order so colors stay stable across filters
    monthly_chart = {
        'months': months,
        'series': [
            {'name': label,
             'data': [counts_by_source.get(key, {}).get(m, 0) for m in months]}
            for key, label in Lead.SOURCE_CHOICES
            if counts_by_source.get(key)
        ],
    }

    per_staff = []
    staff_rows = (
        Lead.objects.filter(assigned_to__isnull=False)
        .values('assigned_to__id', 'assigned_to__first_name',
                'assigned_to__last_name', 'assigned_to__username')
        .annotate(
            total=Count('id'),
            won=Count('id', filter=Q(stage=Lead.STAGE_WON)),
            lost=Count('id', filter=Q(stage=Lead.STAGE_LOST)),
        )
        .order_by('-total')
    )
    for row in staff_rows:
        closed = row['won'] + row['lost']
        name = (f"{row['assigned_to__first_name']} {row['assigned_to__last_name']}".strip()
                or row['assigned_to__username'])
        per_staff.append({
            'name': name,
            'total': row['total'],
            'won': row['won'],
            'lost': row['lost'],
            'win_rate': round(row['won'] * 100 / closed) if closed else None,
        })

    source_rows = (
        Lead.objects.values('source')
        .annotate(total=Count('id'), won=Count('id', filter=Q(stage=Lead.STAGE_WON)))
        .order_by('-total')
    )
    per_source = [
        {
            'label': source_labels.get(row['source'], row['source']),
            'total': row['total'],
            'won': row['won'],
            'rate': round(row['won'] * 100 / row['total']) if row['total'] else 0,
        }
        for row in source_rows
    ]

    closed_leads = Lead.objects.filter(closed_at__isnull=False)
    avg_days_to_close = None
    durations = [
        (lead.closed_at - lead.created_at).days
        for lead in closed_leads.only('created_at', 'closed_at')
    ]
    if durations:
        avg_days_to_close = round(sum(durations) / len(durations), 1)

    total = Lead.objects.count()
    # stage_counts is keyed by (category, stage), so sum across boards — reading it with
    # a bare stage key silently returned 0 and zeroed every headline tile.
    won = sum(n for (_cat, key), n in stage_counts.items() if key == Lead.STAGE_WON)
    lost = sum(n for (_cat, key), n in stage_counts.items() if key == Lead.STAGE_LOST)
    context = {
        'page_title': 'CRM Reports',
        'total_count': total,
        'open_count': total - won - lost,
        'won_count': won,
        'lost_count': lost,
        'win_rate': round(won * 100 / (won + lost)) if (won + lost) else None,
        'avg_days_to_close': avg_days_to_close,
        'funnels': funnels,
        'monthly_chart': monthly_chart,
        'per_staff': per_staff,
        'per_source': per_source,
    }
    return render(request, 'workforce/crm/crm_reports.html', context)


# ── Board columns (LeadStage) — staff-managed pipeline configuration ─────────
# Adding a column used to mean editing DRIVER_STAGE_LABELS + a migration. These
# four views let ops do it from the UI: label, order, colour, terminal-ness, how
# long closed cards linger, and (driver board) which applicant condition files a
# card there automatically.

def _stage_board(request):
    """Which board is being configured. Defaults to the business pipeline."""
    board = (request.GET.get('board') or request.POST.get('board') or '').strip()
    valid = {c for c, _ in Lead.CATEGORY_CHOICES}
    return board if board in valid else Lead.CATEGORY_BUSINESS


def _stages_redirect(board):
    return redirect(f"{reverse('workforce:crm_stages_manage')}?board={board}")


def _clean_stage_key(raw, label):
    """Slugified, <=20 chars (Lead.stage's max_length). Falls back to the label."""
    from django.utils.text import slugify
    key = slugify(raw or label or '').replace('-', '_')[:20].strip('_')
    return key


@login_required(login_url='/accounts/login/')
@staff_required
def crm_stages_manage(request, board_category=None):
    """Configure one board's kanban columns: list every column with its rules and
    lead count, plus the add form."""
    board = board_category or _stage_board(request)
    stages = list(LeadStage.objects.filter(category=board).order_by('position', 'pk'))

    counts = {
        row['stage']: row['n']
        for row in Lead.objects.filter(category=board).values('stage').annotate(n=Count('id'))
    }
    known = {s.key for s in stages}
    rows = [
        {
            'stage': stage,
            'lead_count': counts.get(stage.key, 0),
            'rule_labels': [crm_stage_rules.RULE_LABELS.get(r, r) for r in (stage.auto_rules or [])],
        }
        for stage in stages
    ]
    orphan_count = sum(n for key, n in counts.items() if key not in known)

    context = {
        'page_title': 'Board Columns',
        'board': board,
        'is_driver_board': board == Lead.CATEGORY_DRIVER,
        'rows': rows,
        'orphan_count': orphan_count,
        'rule_groups': crm_stage_rules.RULE_GROUPS,
        'swatch_choices': LeadStage.SWATCH_CHOICES,
        'write_back_choices': LeadStage.WRITE_BACK_CHOICES,
        'next_position': (stages[-1].position + 1) if stages else 1,
        'move_targets': [(s.key, s.label) for s in stages],
    }
    return render(request, 'workforce/crm/stages_manage.html', context)


@login_required(login_url='/accounts/login/')
@staff_required
def crm_stage_save(request):
    """POST: create a column, or update an existing one (stage_id present)."""
    board = _stage_board(request)
    if request.method != 'POST':
        return _stages_redirect(board)

    stage_id = (request.POST.get('stage_id') or '').strip()
    label = (request.POST.get('label') or '').strip()
    if not label:
        messages.error(request, 'A column needs a name.')
        return _stages_redirect(board)

    stage = None
    if stage_id:
        stage = LeadStage.objects.filter(pk=stage_id, category=board).first()
        if stage is None:
            messages.error(request, 'That column no longer exists.')
            return _stages_redirect(board)

    rules = [r for r in request.POST.getlist('auto_rules') if r in crm_stage_rules.VALID_RULES]
    write_back = (request.POST.get('write_back') or '').strip()
    if write_back not in {c for c, _ in LeadStage.WRITE_BACK_CHOICES}:
        write_back = ''
    swatch = (request.POST.get('dot_swatch') or 'grey').strip()
    if swatch not in {c for c, _ in LeadStage.SWATCH_CHOICES}:
        swatch = 'grey'

    hide_after = (request.POST.get('hide_after_days') or '').strip()
    try:
        hide_after_days = int(hide_after) if hide_after else None
        if hide_after_days is not None and hide_after_days < 1:
            hide_after_days = None
    except ValueError:
        hide_after_days = None

    try:
        position = safe_int(request.POST.get('position'), default=0, minimum=0, maximum=100000)
    except ValueError:
        position = 0

    confirm_text = (request.POST.get('confirm_text') or '').strip()[:120]
    # A column that rewrites a driver's real status (and messages them) must always
    # prompt — the board's guard is driven by this text, so a blank one would approve
    # or reject a real applicant on a stray drag with no dialog at all.
    if write_back and not confirm_text:
        confirm_text = f'move this driver to "{label[:60]}"'

    fields = {
        'label': label[:60],
        'position': max(position, 0),
        'is_closed': request.POST.get('is_closed') == '1',
        'hide_after_days': hide_after_days,
        'is_fallback': request.POST.get('is_fallback') == '1',
        'auto_rules': rules,
        'write_back': write_back,
        'confirm_text': confirm_text,
        'needs_reason': request.POST.get('needs_reason') == '1',
        'dot_swatch': swatch,
        'is_active': request.POST.get('is_active') == '1',
    }
    # Only the business form carries crm_status; a driver form must not blank it.
    if 'crm_status' in request.POST:
        fields['crm_status'] = (request.POST.get('crm_status') or '').strip()[:20]

    if stage is None:
        key = _clean_stage_key(request.POST.get('key'), label)
        if not key:
            messages.error(request, 'Could not build a key from that name — use letters or numbers.')
            return _stages_redirect(board)
        if LeadStage.objects.filter(category=board, key=key).exists():
            messages.error(request, f'A column with the key "{key}" already exists on this board.')
            return _stages_redirect(board)

        # Rules are evaluated right-to-left, so a column created at the far end would
        # silently outrank Approved/Rejected. Land new columns just BEFORE the first
        # outcome column instead, and say so, rather than handing staff maximum
        # precedence by default.
        if not fields['is_closed']:
            first_closed = (
                LeadStage.objects.filter(category=board, is_closed=True)
                .order_by('position').first()
            )
            if first_closed and fields['position'] >= first_closed.position:
                fields['position'] = first_closed.position
                LeadStage.objects.filter(
                    category=board, position__gte=first_closed.position
                ).update(position=models.F('position') + 1)
                messages.info(
                    request,
                    f'Placed "{label}" before "{first_closed.label}" — columns are matched '
                    'from the right, so anything after an outcome column would outrank it. '
                    'Use the arrows to move it if you meant somewhere else.',
                )

        stage = LeadStage.objects.create(category=board, key=key, **fields)
        cache.delete(STAGE_CACHE_KEY)
        messages.success(request, f'Column "{stage.label}" added.')
    else:
        # The key is what Lead.stage stores, so it is never editable — renaming a
        # column changes its label only and no card has to move.
        for name, value in fields.items():
            setattr(stage, name, value)
        stage.save()
        messages.success(request, f'Column "{stage.label}" updated.')

    # Exactly one fallback per board, or reconcile has nowhere to put an
    # unmatched driver.
    if stage.is_fallback:
        LeadStage.objects.filter(category=board).exclude(pk=stage.pk).update(is_fallback=False)
        cache.delete(STAGE_CACHE_KEY)
    elif board == Lead.CATEGORY_DRIVER and not LeadStage.objects.filter(
        category=board, is_fallback=True, is_active=True
    ).exists():
        # Without an active catch-all, an unmatched driver silently lands in whatever
        # column happens to be leftmost. Put it back rather than leave the board in
        # that state.
        stage.is_fallback = True
        stage.save(update_fields=['is_fallback', 'updated_at'])
        messages.warning(
            request,
            f'"{stage.label}" has been kept as the catch-all — every driver board needs '
            'exactly one, or applicants that match no column would be filed at random. '
            'Set the catch-all on another column first if you want to move it.',
        )
    return _stages_redirect(board)


@login_required(login_url='/accounts/login/')
@staff_required
def crm_stage_delete(request):
    """POST: delete a staff-created column, optionally moving its cards first."""
    board = _stage_board(request)
    if request.method != 'POST':
        return _stages_redirect(board)

    stage = LeadStage.objects.filter(pk=(request.POST.get('stage_id') or '').strip(),
                                     category=board).first()
    if stage is None:
        messages.error(request, 'That column no longer exists.')
        return _stages_redirect(board)
    if stage.is_system:
        messages.error(
            request,
            f'"{stage.label}" is a built-in column and cannot be deleted. '
            'Untick "Show on board" to hide it instead.',
        )
        return _stages_redirect(board)

    occupied = Lead.objects.filter(category=board, stage=stage.key)
    move_to = (request.POST.get('move_to') or '').strip()
    count = occupied.count()
    if count:
        target = LeadStage.objects.filter(category=board, key=move_to).exclude(pk=stage.pk).first()
        if target is None:
            messages.error(
                request,
                f'"{stage.label}" still holds {count} lead(s). Pick a column to move them to first.',
            )
            return _stages_redirect(board)
        now = timezone.now()
        occupied.update(
            stage=target.key,
            stage_changed_at=now,
            closed_at=now if target.is_closed else None,
            updated_at=now,
        )
        messages.info(request, f'Moved {count} lead(s) to "{target.label}".')

    label = stage.label
    stage.delete()
    messages.success(request, f'Column "{label}" deleted.')
    return _stages_redirect(board)


@login_required(login_url='/accounts/login/')
@staff_required
def crm_stage_reorder(request):
    """POST: persist a new left-to-right column order (order=<id>,<id>,...)."""
    board = _stage_board(request)
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST required'}, status=405)

    raw = (request.POST.get('order') or '').strip()
    ids = [part for part in raw.split(',') if part.strip().isdigit()]
    if not ids:
        return JsonResponse({'success': False, 'error': 'No order supplied'}, status=400)

    stages = {str(s.pk): s for s in LeadStage.objects.filter(category=board)}
    changed = []
    for index, pk in enumerate(ids, start=1):
        stage = stages.get(pk)
        if stage and stage.position != index:
            stage.position = index
            changed.append(stage)
    if changed:
        LeadStage.objects.bulk_update(changed, ['position'])
        cache.delete(STAGE_CACHE_KEY)
    return JsonResponse({'success': True, 'moved': len(changed)})


@login_required(login_url='/accounts/login/')
@staff_required
def crm_lead_merge(request, lead_id):
    """POST duplicate_id=<pk>: fold another card for the same prospect into this one.

    Both rows survive — the absorbed card keeps its own source, inquiry link and
    timeline and renders inside this one, so a wrong merge can be undone."""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST required'}, status=405)
    primary = get_object_or_404(Lead, pk=lead_id)
    duplicate = Lead.objects.filter(pk=(request.POST.get('duplicate_id') or '').strip()).first()
    if duplicate is None:
        return JsonResponse({'success': False, 'error': 'Pick a lead to merge.'}, status=400)

    ok, error = crm_services.merge_leads(primary, duplicate, request.user)
    if not ok:
        return JsonResponse({'success': False, 'error': error}, status=400)
    return JsonResponse({
        'success': True,
        'merged_id': duplicate.pk,
        'children': primary.merged_children.count(),
    })


@login_required(login_url='/accounts/login/')
@staff_required
def crm_lead_unmerge(request, lead_id):
    """POST child_id=<pk>: put an absorbed card back on the board on its own."""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST required'}, status=405)
    parent = get_object_or_404(Lead, pk=lead_id)
    child = parent.merged_children.filter(pk=(request.POST.get('child_id') or '').strip()).first()
    if child is None:
        return JsonResponse({'success': False, 'error': 'That card is not merged into this one.'},
                            status=400)

    ok, error = crm_services.unmerge_lead(child, request.user)
    if not ok:
        return JsonResponse({'success': False, 'error': error}, status=400)
    return JsonResponse({'success': True, 'child_id': child.pk})
