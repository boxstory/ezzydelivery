# Purpose: Staff-facing CRM views — leads kanban board, list, detail, manual create, stage/field updates, WAHA inbox, link-lead-to-business, reports.
# Used by: workforce/urls.py (crm/... routes); templates in workforce/templates/workforce/crm/.
# Notes: Business logic lives in crm/services.py; JSON endpoints mirror the pricing_inquiry_update_status fetch-POST pattern.

import logging
import re
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db.models import Count, Max, Q
from django.db.models.functions import TruncMonth
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from core.decorators import staff_required
from crm import services as crm_services
from crm.models import InboxDismissal, Lead, LeadActivity

logger = logging.getLogger(__name__)

BOARD_CLOSED_WINDOW_DAYS = 30


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
    leads = Lead.objects.select_related('assigned_to', 'converted_business')

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
    resolved via the synced WhatsAppContact directory. Three queries total."""
    ident_map = {}   # message identifier -> [lead, ...]
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
            .values_list('lid', 'phone')
        )
        for lid, phone in lid_rows:
            for ident in (lid, f'{lid}@lid'):
                ident_map.setdefault(ident, []).extend(phone_map[phone])
        idents = list(ident_map)
        hits = set(
            WhatsAppMessage.objects.filter(from_number__in=idents)
            .values_list('from_number', flat=True).distinct()
        ) | set(
            WhatsAppMessage.objects.filter(to_number__in=idents)
            .values_list('to_number', flat=True).distinct()
        )
        for ident in hits:
            for lead in ident_map.get(ident, ()):
                lead.has_wa_chat = True
    except Exception:
        logger.exception('crm: WA chat annotation failed')


@login_required(login_url='/accounts/login/')
@staff_required
def crm_leads_board(request):
    """Kanban pipeline board grouped by stage."""
    leads, search, source_filter, assigned_filter, category_filter = _filtered_leads(request)

    closed_cutoff = timezone.now() - timedelta(days=BOARD_CLOSED_WINDOW_DAYS)
    leads = list(
        leads.filter(
            Q(closed_at__isnull=True) | Q(closed_at__gte=closed_cutoff)
        ).order_by('-created_at')
    )
    _annotate_wa_chats(leads)

    by_stage = {key: [] for key, _ in Lead.STAGE_CHOICES}
    for lead in leads:
        by_stage.setdefault(lead.stage, []).append(lead)

    columns = [
        {
            'key': key,
            'label': label,
            'leads': by_stage[key],
            'count': len(by_stage[key]),
            'overdue': sum(1 for lead in by_stage[key] if lead.is_overdue),
        }
        for key, label in Lead.STAGE_CHOICES
    ]

    open_total = sum(c['count'] for c in columns if c['key'] not in Lead.CLOSED_STAGES)
    overdue_total = sum(c['overdue'] for c in columns)
    won_window = len(by_stage[Lead.STAGE_WON])

    context = {
        'page_title': 'Leads Board',
        'columns': columns,
        'open_total': open_total,
        'overdue_total': overdue_total,
        'won_window': won_window,
        'search': search,
        'source_filter': source_filter,
        'assigned_filter': assigned_filter,
        'category_filter': category_filter,
        'staff_users': _staff_users(),
        'source_choices': Lead.SOURCE_CHOICES,
        'category_choices': Lead.CATEGORY_CHOICES,
        'closed_window_days': BOARD_CLOSED_WINDOW_DAYS,
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
        ).exclude(stage__in=Lead.CLOSED_STAGES)

    leads = leads.order_by('-created_at')

    total_count = Lead.objects.count()
    open_count = Lead.objects.exclude(stage__in=Lead.CLOSED_STAGES).count()
    overdue_count = (
        Lead.objects.filter(next_followup_at__lt=timezone.localdate())
        .exclude(stage__in=Lead.CLOSED_STAGES).count()
    )
    won_count = Lead.objects.filter(stage=Lead.STAGE_WON).count()

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
        'stage_choices': Lead.STAGE_CHOICES,
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
    """All WhatsAppMessage from/to identifiers that can mean this lead's phone:
    bare digits with/without the 974 country code, @c.us JIDs, and the
    anonymized @lid JIDs resolved via the synced WhatsAppContact directory."""
    phone = crm_services.normalize_phone(lead.phone)
    override = crm_services.normalize_phone(getattr(lead, 'wa_chat_override', '') or '')
    idents = set()
    if phone:
        idents |= crm_services._phone_variants(phone)
    if override:
        idents.add(override)
        idents.add(f'{override}@lid')
        idents |= crm_services._phone_variants(override)
    if not idents:
        return set()
    try:
        from whatsapp.models import WhatsAppContact
        lids = (
            WhatsAppContact.objects
            .filter(Q(phone__in=list(idents)) | Q(lid__in=list(idents)))
            .exclude(lid='')
            .values_list('lid', flat=True)
        )
        for lid in lids:
            idents.add(lid)
            idents.add(f'{lid}@lid')
    except Exception:
        logger.exception('crm: lid lookup failed for lead %s', lead.pk)
    for p in list(idents):
        if '@' not in p:
            idents.add(f'{p}@c.us')
    return idents


def _lead_wa_conversation(lead):
    """Full WhatsApp conversation for a lead's phone, oldest first, with media
    annotations (`media_kind`, `media_proxy`) on each row. Returns
    (messages, media_items) — media_items is the photo/video subset for the
    Media panel, newest first.

    Not gated on WAHA_ENABLED (that flag gates sending): the message table is
    filled by the webhook regardless, same as the CRM inbox."""
    if not lead.phone and not lead.wa_chat_override:
        return [], []

    idents = _lead_wa_identifiers(lead)
    if not idents:
        return [], []

    try:
        from whatsapp.models import WhatsAppMessage
        from whatsapp.wa_chats_view import _extract_media

        rows = list(
            WhatsAppMessage.objects
            .filter(Q(from_number__in=idents) | Q(to_number__in=idents))
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

    wa_messages, wa_media = _lead_wa_conversation(lead)

    context = {
        'page_title': f'Lead – {lead.company_name or lead.contact_name or lead.phone}',
        'lead': lead,
        'activities': lead.activities.select_related('created_by').order_by('-created_at'),
        'staff_users': _staff_users(),
        'stage_choices': Lead.STAGE_CHOICES,
        'wa_messages': wa_messages,
        'wa_media': wa_media,
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

    idents = _lead_wa_identifiers(lead)
    if not idents:
        raise Http404
    msg = get_object_or_404(
        WhatsAppMessage.objects.filter(
            Q(from_number__in=idents) | Q(to_number__in=idents)
        ),
        pk=msg_id,
    )
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
    results = [
        {'phone': c.phone, 'lid': c.lid, 'name': c.display_name}
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

    variants = crm_services._phone_variants(identifier)
    contact = (
        WhatsAppContact.objects
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
            seen, inserted, counterparties = pull_chat_history(chat_id)
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
    """Stream WAHA media for any message — used by the inbox chat preview,
    where no lead exists yet. Staff-gated; same proxy as the lead route."""
    from whatsapp.models import WhatsAppMessage
    msg = get_object_or_404(WhatsAppMessage, pk=msg_id)
    return _stream_wa_media(msg)


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
            resp = FileResponse(
                msg.media_file.open('rb'),
                content_type=msg.media_mime.split(';')[0].strip() or 'application/octet-stream',
            )
            resp['Cache-Control'] = 'private, max-age=86400'
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

    resp = StreamingHttpResponse(
        upstream.iter_content(chunk_size=64 * 1024),
        content_type=media.get('mime') or upstream.headers.get('Content-Type', 'application/octet-stream'),
    )
    if upstream.headers.get('Content-Length'):
        resp['Content-Length'] = upstream.headers['Content-Length']
    resp['Cache-Control'] = 'private, max-age=86400'
    return resp


def _wa_sender_identifiers(raw_sender):
    """Identifier set for an inbox sender string (digits, JID, or @lid alias):
    all phone variants, @c.us JIDs, and the lid mapping both ways via the
    WhatsAppContact directory."""
    raw = (raw_sender or '').strip()
    digits = raw.split('@', 1)[0]
    if not digits:
        return set()
    idents = {raw, digits} if raw else {digits}

    try:
        from whatsapp.models import WhatsAppContact
        phones = set()
        if raw.endswith('@lid'):
            idents.add(f'{digits}@lid')
            contact = WhatsAppContact.objects.filter(lid=digits).first()
            if contact and contact.phone:
                phones.update(crm_services._phone_variants(contact.phone))
        else:
            phones.update(crm_services._phone_variants(crm_services.normalize_phone(digits)))
            # Bare digits can be a phone OR an unsuffixed lid — try both.
            contact = (
                WhatsAppContact.objects.filter(phone__in=list(phones)).exclude(lid='').first()
                or WhatsAppContact.objects.filter(lid=digits).first()
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

    GET ?sender=<from_number as shown in the inbox row> — returns the last 100
    messages both directions with media annotations for the modal."""
    from whatsapp.models import WhatsAppMessage
    from whatsapp.wa_chats_view import _extract_media

    idents = _wa_sender_identifiers(request.GET.get('sender', ''))
    if not idents:
        return JsonResponse({'success': False, 'error': 'sender is required'}, status=400)

    rows = list(
        WhatsAppMessage.objects
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
            }
            return render(request, 'workforce/crm/lead_form.html', context)

        followup, date_error = _parse_followup_date(request.POST.get('next_followup_at'))
        if date_error:
            context = {
                'page_title': 'New Lead',
                'staff_users': _staff_users(),
                'error': date_error,
                'form_data': request.POST,
            }
            return render(request, 'workforce/crm/lead_form.html', context)

        lead = Lead.objects.create(
            source=Lead.SOURCE_MANUAL,
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

    context = {'page_title': 'New Lead', 'staff_users': _staff_users()}
    return render(request, 'workforce/crm/lead_form.html', context)


@login_required(login_url='/accounts/login/')
@staff_required
def crm_lead_update_stage(request, lead_id):
    """AJAX: move a lead to a new pipeline stage (board drag-drop + detail page)."""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    lead = get_object_or_404(Lead, pk=lead_id)
    new_stage = request.POST.get('stage', '').strip()
    try:
        crm_services.set_lead_stage(lead, new_stage, request.user)
    except ValueError as exc:
        return JsonResponse({'success': False, 'error': str(exc)}, status=400)
    return JsonResponse({
        'success': True,
        'stage': lead.stage,
        'stage_display': lead.get_stage_display(),
    })


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
        lead_id = int(request.POST.get('lead_id', ''))
        business_id = int(request.POST.get('business_id', ''))
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

    waha_enabled = getattr(settings, 'WAHA_ENABLED', False)

    # Live session status banner — which number the WAHA bridge is connected to
    waha_session = None
    try:
        from whatsapp.waha_views import fetch_waha_session_status
        waha_session = fetch_waha_session_status()
    except Exception:
        logger.exception('crm: WAHA session status fetch failed')

    rows = []
    search = request.GET.get('search', '').strip()

    try:
        from whatsapp.models import WhatsAppMessage
        grouped = (
            WhatsAppMessage.objects
            .filter(direction='inbound')
            .exclude(from_number='')
            # Groups and status broadcasts are not promotable senders
            .exclude(from_number__contains='-')
            .exclude(from_number__contains='@g.us')
            .exclude(from_number__istartswith='status')
            .values('from_number')
            .annotate(last_at=Max('received_at'), msg_count=Count('id'))
            .order_by('-last_at')
        )
        if search:
            grouped = grouped.filter(from_number__icontains=search)
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
        lid_pn = {}
        contact_names = {}
        sender_digits = {r['from_number'].split('@', 1)[0] for r in grouped}
        try:
            from whatsapp.models import WhatsAppContact
            directory = WhatsAppContact.objects.filter(
                Q(lid__in=sender_digits) | Q(phone__in=sender_digits)
            )
            for c in directory:
                if c.lid:
                    lid_pn[c.lid] = c.phone
                if c.display_name:
                    contact_names[c.phone] = c.display_name
        except Exception:
            logger.exception('crm: contact directory lookup failed')
        # Digits that still look like lids (too long for a phone, no mapping
        # yet) — fall back to WAHA's lids API for rows not synced yet.
        missing_lids = {
            d for d in sender_digits
            if d not in lid_pn and d.isdigit() and len(d) > 13
        }
        if missing_lids:
            try:
                from whatsapp.wa_chats_view import _lid_map, _waha_base
                waha_map = _lid_map(
                    _waha_base(),
                    getattr(settings, 'WAHA_DEFAULT_SESSION', 'default') or 'default',
                    getattr(settings, 'WAHA_API_KEY', '') or '',
                )
                for lid in missing_lids:
                    if lid in waha_map:
                        lid_pn[lid] = waha_map[lid]
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
            Lead.objects.exclude(stage__in=Lead.CLOSED_STAGES)
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
            real = lid_pn.get(digits)
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
            _WM.objects.filter(direction='inbound', from_number=row['from_number'])
            .order_by('-received_at').first()
        )
        row['last_body'] = _clean_wa_body(last.body)[:160] if last else ''
        row['last_type'] = last.message_type if last else ''
        icon_label = WA_MEDIA_LABELS.get(row['last_type'])
        if not row['last_body'] and icon_label:
            row['last_media_icon'], row['last_media_label'] = icon_label

    from urllib.parse import urlencode
    context = {
        'page_title': 'WhatsApp Inbox',
        'page_obj': page_obj,
        'search': search,
        'waha_enabled': waha_enabled,
        'waha_session': waha_session,
        'per_page': request.GET.get('per_page', '25'),
        'filter_params': urlencode({'search': search}) if search else '',
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

    session = getattr(settings, 'WAHA_DEFAULT_SESSION', 'default') or 'default'
    started = _time.monotonic()
    budget_s = 20  # stay well inside gunicorn's 30s window

    try:
        chats = waha_get(f'/api/{session}/chats', params={'limit': 40}, timeout=15)
    except Exception as exc:
        logger.warning('crm resync: chat list failed: %s', exc)
        return JsonResponse(
            {'success': False, 'error': 'WAHA unreachable — could not list chats'},
            status=502,
        )

    scanned = 0
    inserted = 0
    partial = False
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
    # Refresh the contact directory too, but only with time left in the
    # budget — no Celery worker runs in this deployment, so it's inline here
    # (steady-state ~5s) with a daily cron as the freshness backstop.
    contacts_sync = 'skipped'
    if not partial and _time.monotonic() - started < budget_s:
        try:
            from whatsapp.contacts import sync_contacts
            cres = sync_contacts(session=session)
            contacts_sync = f"{cres['created']} new, {cres['updated']} updated"
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
        row['stage']: row['n']
        for row in Lead.objects.values('stage').annotate(n=Count('id'))
    }
    stage_data = [
        {'key': key, 'label': label, 'count': stage_counts.get(key, 0)}
        for key, label in Lead.STAGE_CHOICES
    ]

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
    won = stage_counts.get(Lead.STAGE_WON, 0)
    lost = stage_counts.get(Lead.STAGE_LOST, 0)
    context = {
        'page_title': 'CRM Reports',
        'total_count': total,
        'open_count': total - won - lost,
        'won_count': won,
        'lost_count': lost,
        'win_rate': round(won * 100 / (won + lost)) if (won + lost) else None,
        'avg_days_to_close': avg_days_to_close,
        'stage_data': stage_data,
        'monthly_chart': monthly_chart,
        'per_staff': per_staff,
        'per_source': per_source,
    }
    return render(request, 'workforce/crm/crm_reports.html', context)
