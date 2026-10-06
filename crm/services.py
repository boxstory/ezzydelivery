# Purpose: All CRM business logic — lead creation from each source, stage sync with PricingEnquiry.crm_status, convert-to-Business, follow-up digest.
# Used by: workforce/crm_views.py, webpages/views.py hooks, workforce pricing_inquiry_update_status, crm management commands.
# Notes: Stage<->crm_status sync is two one-way functions (set_lead_stage writes to inquiry; sync_lead_from_pricing_status writes to lead) so no loop is possible.
#        Board columns are LeadStage rows, so which stage a driver lands in is data, not code — see crm/stage_rules.py.

import logging
import re

from django.db import transaction
from django.utils import timezone

from . import stage_rules
from .contact_tags import apply_tag, strip_tags
from .models import Lead, LeadActivity, LeadStage

logger = logging.getLogger(__name__)

SITE_BASE_URL = 'https://ezzydelivery.qa'

# Identity mapping except won <-> converted (PricingEnquiry predates the Lead model)
STAGE_TO_CRM_STATUS = {
    Lead.STAGE_NEW: 'new',
    Lead.STAGE_CONTACTED: 'contacted',
    Lead.STAGE_QUOTED: 'quoted',
    Lead.STAGE_NEGOTIATING: 'negotiating',
    Lead.STAGE_WON: 'converted',
    Lead.STAGE_LOST: 'lost',
    Lead.STAGE_ON_HOLD: 'on_hold',
}
CRM_STATUS_TO_STAGE = {v: k for k, v in STAGE_TO_CRM_STATUS.items()}


# ── Stage lookups ────────────────────────────────────────────────────────────
# Everything that used to read Lead.STAGE_CHOICES / Lead.CLOSED_STAGES goes
# through these so a staff-created column behaves like a built-in one.

def board_stages(category):
    """Active columns for one board, left→right."""
    return LeadStage.board_columns(category)


def closed_stage_keys(category=None):
    """Terminal stage keys — for queryset filters like `exclude(stage__in=...)`.
    Includes staff-created terminal columns, which is why callers must not use
    Lead.CLOSED_STAGES directly."""
    return list(LeadStage.closed_keys(category))


def outcome_stage_keys(outcome, category=None):
    """Stage keys a board counts as `outcome` ('won' | 'lost').

    Reports and the win-rate columns used to test the literal key 'won', which
    only held while both boards shared the business keys. The driver board names
    its own outcome columns (approved/rejected), so the meaning is read off
    LeadStage.outcome instead."""
    return list(LeadStage.outcome_keys(outcome, category))


def initial_stage_key(category):
    """Where a brand-new lead on this board starts.

    The board's catch-all column if it elected one, else its leftmost column.
    Falls back to the legacy 'new' only on an unseeded DB — relying on the model
    default instead would drop a driver card into a business key and strand it in
    the Unsorted lane."""
    columns = LeadStage.board_columns(category)
    if not columns:
        return Lead.STAGE_NEW
    for column in columns:
        if column.is_fallback:
            return column.key
    return columns[0].key


def get_stage(category, key):
    """The LeadStage row for one board+key, or None (unknown/inactive key)."""
    return LeadStage.objects.filter(category=category, key=key).first()


def is_closed_stage(category, key):
    return key in LeadStage.closed_keys(category)


def normalize_phone(raw):
    """Digits-only form used for phone matching (e.g. '+974 6645-1589' -> '97466451589').
    Strips a leading '00' international access code so pricing-form entries like
    '00974 6645 1589' normalize the same as '+974 6645 1589'."""
    digits = re.sub(r'\D', '', str(raw or ''))
    if digits.startswith('00') and len(digits) > 10:
        digits = digits[2:]
    return digits


def _log_activity(lead, activity_type, body, user=None):
    return LeadActivity.objects.create(
        lead=lead, activity_type=activity_type, body=body, created_by=user,
    )


def fire_lead_trigger(trigger_key, lead, **extra):
    """Run the AutoFlows staff built for a lead event (Auto Triggers → Marketing).

    ``phone`` is in the context on purpose: it is what the "Person this event is
    about" recipient resolves to, so a flow can message the lead itself. A flow
    failure must never break lead creation or a stage move, so everything here
    is swallowed and logged.
    """
    try:
        from core.auto_flow_executor import execute_flows_for_trigger

        context = {
            'lead_id': lead.pk,
            'lead_name': strip_tags(lead.contact_name) or lead.company_name or '',
            'lead_company': lead.company_name or '',
            'lead_phone': lead.phone or '',
            'phone': lead.phone or '',
            'lead_stage': lead.stage_label,
            'lead_source': lead.get_source_display(),
            'lead_category': lead.get_category_display(),
            'lead_url': f'{SITE_BASE_URL}/workforce/crm/leads/{lead.pk}/',
            'assigned_to': (lead.assigned_to.get_username() if lead.assigned_to_id else ''),
        }
        context.update(extra)
        execute_flows_for_trigger(trigger_key, extra_context=context)
    except Exception:
        logger.exception('crm: auto flow %s failed for lead %s', trigger_key, lead.pk)


def create_lead_from_pricing_inquiry(inquiry):
    """Idempotent: OneToOne get_or_create keyed on the inquiry."""
    stage = CRM_STATUS_TO_STAGE.get(inquiry.crm_status, Lead.STAGE_NEW)
    lead, created = Lead.objects.get_or_create(
        pricing_enquiry=inquiry,
        defaults={
            'source': Lead.SOURCE_PRICING,
            'company_name': (inquiry.business_name or '')[:200],
            'contact_name': (inquiry.full_name or '')[:100],
            'phone': normalize_phone(inquiry.business_contact_number)[:50],
            'product_category': (inquiry.product_category or '')[:200],
            'stage': stage,
            # A lead born already won/lost must carry a close date or the
            # board's "last N days" window can never age it out.
            'closed_at': timezone.now() if is_closed_stage(Lead.CATEGORY_BUSINESS, stage) else None,
            'assigned_to': inquiry.assigned_to,
        },
    )
    if created:
        _log_activity(lead, LeadActivity.TYPE_NOTE,
                      f'Lead created from pricing inquiry #{inquiry.id}')
        fire_lead_trigger('lead_created', lead)
        # Same number already chasing us on WhatsApp? One card, both sources.
        try:
            auto_merge_duplicate(lead)
        except Exception:
            logger.exception('crm: auto-merge failed for lead %s', lead.pk)
    return lead, created


def create_lead_from_whatsapp_inquiry(inquiry):
    """Idempotent: OneToOne get_or_create keyed on the inquiry."""
    notes_bits = []
    if inquiry.product_name:
        notes_bits.append(f'Product: {inquiry.product_name}')
    if inquiry.additional_info:
        notes_bits.append(inquiry.additional_info)
    lead, created = Lead.objects.get_or_create(
        whatsapp_inquiry=inquiry,
        defaults={
            'source': Lead.SOURCE_WA_FORM,
            'company_name': (inquiry.company_name or '')[:200],
            'contact_name': (inquiry.contact_person or '')[:100],
            'phone': normalize_phone(inquiry.contact_number)[:50],
            'product_category': (inquiry.product_category or '')[:200],
            'notes': '\n'.join(notes_bits),
        },
    )
    if created:
        _log_activity(lead, LeadActivity.TYPE_NOTE,
                      f'Lead created from WhatsApp quick inquiry #{inquiry.id}')
        fire_lead_trigger('lead_created', lead)
        try:
            auto_merge_duplicate(lead)
        except Exception:
            logger.exception('crm: auto-merge failed for lead %s', lead.pk)
    return lead, created


def _phone_variants(phone):
    """Digit forms that can mean the same Qatar number (with/without 974).
    Also falls back to the last-8-digit local suffix for messy free-text entries
    (stray leading 0, wrong country code, extra digits) so a WA chat still
    matches when the stored number doesn't cleanly fall into 8 or 974+8 digits."""
    variants = {phone}
    if len(phone) == 8:
        variants.add('974' + phone)
    elif phone.startswith('974') and len(phone) == 11:
        variants.add(phone[3:])
    if len(phone) > 8:
        last8 = phone[-8:]
        variants.add(last8)
        variants.add('974' + last8)
    return variants


def platform_account_numbers():
    """Every phone/WhatsApp number that belongs to a real platform account.

    Conversations with these numbers are OUR OWN traffic with our own users, not
    prospect chats — they carry auth messages, so the CRM must refuse to open them
    rather than merely hide them from the inbox listing. Cached briefly because it is
    checked on every chat read.
    """
    from django.core.cache import cache

    key = 'crm_platform_account_numbers_v1'
    numbers = cache.get(key)
    if numbers is None:
        from core.models import Profile

        numbers = set()
        for phone, whatsapp in Profile.objects.values_list('phone', 'whatsapp'):
            for value in (phone, whatsapp):
                normalized = normalize_phone(value)
                if normalized:
                    numbers.update(_phone_variants(normalized))
        cache.set(key, numbers, 300)
    return numbers


def is_platform_account_number(*candidates):
    """True when any candidate identifier resolves to a platform account's number."""
    owned = platform_account_numbers()
    if not owned:
        return False
    for candidate in candidates:
        if not candidate:
            continue
        normalized = normalize_phone(candidate)
        if not normalized:
            continue
        if _phone_variants(normalized) & owned:
            return True
    return False


def wa_read_blocked(identifiers, user=None):
    """'' when this conversation may be opened in the CRM, else the refusal reason.

    Takes the resolved identifier set for a chat (phones and/or @lid values) and
    resolves each back to a phone through the contact directory, because inbound rows
    are keyed by LID and a LID lookup is the only way to spot a platform account.

    With `user`, also refuses a chat under a marketing-only WhatsApp label to staff
    outside marketing (whatsapp/label_access.py).
    """
    from whatsapp.models import WhatsAppContact

    phones = set()
    lids = set()
    for ident in identifiers or ():
        raw = str(ident or '')
        bare = raw.split('@')[0]
        if '@lid' in raw or (bare.isdigit() and len(bare) > 13):
            lids.add(bare)
        else:
            phones.add(bare)

    if lids:
        for lid, phone in WhatsAppContact.objects.filter(
            lid__in=lids
        ).values_list('lid', 'phone'):
            if phone:
                phones.add(phone)

    if is_platform_account_number(*phones):
        return (
            'This number belongs to an EzzyDelivery account, so its conversation '
            'cannot be opened here — it carries account and verification messages. '
            'Use the account\'s own profile page instead.'
        )
    if user is not None:
        from whatsapp import label_access
        if label_access.identifiers_hidden(user, phones | lids):
            return label_access.REFUSAL
    return ''


def _wa_contact_for_phone(phone):
    """WhatsAppContact directory row for a normalized phone, or None.

    A phone can have one row per WAHA session (the lid differs per linked
    number); they describe the same person, so prefer whichever actually
    carries a name rather than letting row order decide.
    """
    try:
        from whatsapp.models import WhatsAppContact
        return WhatsAppContact.objects.filter(
            phone__in=_phone_variants(phone)
        ).order_by('saved_name', 'push_name').exclude(
            saved_name='', push_name=''
        ).first() or WhatsAppContact.objects.filter(
            phone__in=_phone_variants(phone)
        ).first()
    except Exception:
        logger.exception('crm: contact lookup failed for %s', phone)
        return None


def create_lead_from_wa_number(phone, user=None, category=Lead.CATEGORY_BUSINESS):
    """WAHA inbox promote. Returns (lead, created). Dedupes on an existing open
    lead with the same normalized phone instead of creating a duplicate."""
    phone = normalize_phone(phone)
    if not phone:
        raise ValueError('A phone number is required')
    if category not in {c for c, _ in Lead.CATEGORY_CHOICES}:
        category = Lead.CATEGORY_BUSINESS

    # Any card already carrying this number — as its phone, 2nd mobile or a linked
    # chat — is this sender's card.
    existing = (
        _cards_with_numbers([phone])
        .filter(merged_into__isnull=True)
        .exclude(stage__in=closed_stage_keys())
        .order_by('-created_at')
        .first()
    )
    if existing:
        from .chat_links import _already_on
        if not _already_on(existing, phone):
            # Matched on the card's 2nd mobile: the lead page reads chats from the
            # phone and linked numbers only, so join this one.
            add_wa_link(existing, phone, user=user)
        return existing, False

    contact = _wa_contact_for_phone(phone)
    name = contact.display_name if contact else ''

    lead = Lead.objects.create(
        source=Lead.SOURCE_WA_INBOUND,
        category=category,
        stage=initial_stage_key(category),
        phone=phone,
        contact_name=name[:100],
        company_name=name[:200] if (contact and contact.is_business) else '',
        notes=_recent_wa_messages_text(phone, contact=contact),
    )
    _log_activity(
        lead, LeadActivity.TYPE_NOTE,
        'Driver lead created from inbound WhatsApp messages'
        if category == Lead.CATEGORY_DRIVER
        else 'Lead created from inbound WhatsApp messages',
        user,
    )
    fire_lead_trigger('lead_created', lead)
    return lead, True


def _recent_wa_messages_text(phone, limit=5, contact=None):
    """Copy the sender's recent inbound WAHA message bodies into the new lead's notes.

    Matches every identifier form the store may hold for this sender: bare
    digits with/without 974, @c.us JIDs, and the anonymized @lid alias."""
    idents = set()
    for p in _phone_variants(phone):
        idents.update({p, f'{p}@c.us'})
    if contact is None:
        contact = _wa_contact_for_phone(phone)
    if contact and contact.lid:
        idents.update({contact.lid, f'{contact.lid}@lid'})
    try:
        from whatsapp.models import WhatsAppMessage
        bodies = list(
            WhatsAppMessage.objects
            .filter(direction='inbound', from_number__in=idents)
            .exclude(body='')
            .order_by('-received_at')
            .values_list('body', flat=True)[:limit]
        )
        if not bodies:
            return ''
        return 'Recent WhatsApp messages:\n' + '\n'.join(
            f'- {b[:300]}' for b in reversed(bodies)
        )
    except Exception:
        logger.exception('crm: failed to read WAHA messages for %s', phone)
        return ''


def set_lead_stage(lead, new_stage, user=None):
    """Validate + set stage, log activity, and sync the linked PricingEnquiry.

    The stage must be a column on *this lead's own board*, so a business lead can
    never be dropped into a driver-only column (or vice versa)."""
    stage = get_stage(lead.category, new_stage)
    if stage is None:
        # Before the stages are seeded (fresh DB mid-migrate), fall back to the
        # legacy constant rather than making every stage move impossible.
        if not LeadStage.objects.exists() and new_stage in {s for s, _ in Lead.STAGE_CHOICES}:
            stage = None
        else:
            raise ValueError(f'Invalid stage: {new_stage}')
    if new_stage == lead.stage:
        return lead

    old_display = lead.stage_label
    lead.stage = new_stage
    lead.stage_changed_at = timezone.now()
    closed = stage.is_closed if stage else new_stage in Lead.CLOSED_STAGES
    lead.closed_at = timezone.now() if closed else None
    lead.save(update_fields=['stage', 'stage_changed_at', 'closed_at', 'updated_at'])

    _log_activity(lead, LeadActivity.TYPE_STAGE_CHANGE,
                  f'Stage: {old_display} → {lead.stage_label}', user)

    # One-way sync back to the legacy pricing-inquiry CRM status. A column with a
    # blank crm_status (every staff-created one) simply doesn't mirror — this used
    # to be a dict lookup that raised KeyError on any unmapped stage.
    inquiry = lead.pricing_enquiry
    if inquiry:
        new_status = stage.crm_status if stage else STAGE_TO_CRM_STATUS.get(new_stage, '')
        if new_status and inquiry.crm_status != new_status:
            inquiry.crm_status = new_status
            inquiry.save(update_fields=['crm_status', 'date_modified'])

    # Marketing auto-flows. The generic move always fires; won/lost fire on top
    # so a flow can greet a won lead without having to test the stage itself.
    fire_lead_trigger('lead_stage_changed', lead,
                      old_stage=old_display, new_stage=lead.stage_label)
    # Read the column's declared outcome, not its key — the driver board's win is
    # called "approved", and testing the literal 'won' skipped it entirely.
    outcome = stage.outcome if stage else (
        'won' if new_stage == Lead.STAGE_WON else
        'lost' if new_stage == Lead.STAGE_LOST else ''
    )
    if outcome == 'won':
        fire_lead_trigger('lead_won', lead)
    elif outcome == 'lost':
        fire_lead_trigger('lead_lost', lead)
    return lead


def sync_lead_from_pricing_status(inquiry):
    """Called from the legacy pricing_inquiry_update_status view: pull the
    inquiry's crm_status/assignee onto its lead WITHOUT writing back (no loop).

    Only *completed* form submissions get a lead automatically, so an inquiry a
    visitor abandoned mid-form has none. Staff staging such a row on the detail
    page is exactly the signal that it belongs on the board, so create it here
    rather than leaving the status change stranded on the legacy page."""
    lead = getattr(inquiry, 'lead', None)
    if lead is None:
        lead, created = create_lead_from_pricing_inquiry(inquiry)
        if created:
            # Stage/assignee already come from the inquiry in the defaults.
            return lead

    updates = []
    new_stage = CRM_STATUS_TO_STAGE.get(inquiry.crm_status)
    if new_stage and new_stage != lead.stage:
        lead.stage = new_stage
        lead.stage_changed_at = timezone.now()
        lead.closed_at = timezone.now() if is_closed_stage(lead.category, new_stage) else None
        updates += ['stage', 'stage_changed_at', 'closed_at']
        _log_activity(lead, LeadActivity.TYPE_STAGE_CHANGE,
                      f'Stage set to {lead.stage_label} (via pricing inquiry page)')
    # The lead owns its owner now (crm/ownership.py): the legacy page may fill an
    # empty slot, but never clears a taken lead or hands it to someone else —
    # its assignee is often stale, and a status save re-posts it every time.
    if inquiry.assigned_to_id and lead.assigned_to_id is None:
        lead.assigned_to_id = inquiry.assigned_to_id
        updates.append('assigned_to')
    if updates:
        lead.save(update_fields=updates + ['updated_at'])
    return lead


def convert_lead_to_business(lead, user=None):
    """Create a pending Business from the lead. Returns (business, created).
    Idempotent under concurrency: the lead row is locked for the check+create,
    so two simultaneous calls cannot both create a Business."""
    from business.models import Business
    from core.views import generate_secure_id

    if lead.converted_business_id:
        return lead.converted_business, False

    with transaction.atomic():
        lead = Lead.objects.select_for_update().get(pk=lead.pk)
        if lead.converted_business_id:
            return lead.converted_business, False

        business_id = generate_secure_id()
        while Business.objects.filter(business_id=business_id).exists():
            business_id = generate_secure_id()

        inquiry = lead.pricing_enquiry
        business = Business.objects.create(
            business_id=business_id,
            business_name=(lead.company_name or strip_tags(lead.contact_name) or '')[:100],
            business_phone=lead.phone[:100],
            business_whatsapp=lead.phone[:100],
            business_product_category=(lead.product_category or '')[:100],
            business_website=(inquiry.website_url or '')[:255] if inquiry else '',
            business_instagram=(inquiry.instagram_profile or '')[:100] if inquiry else '',
            business_status='pending',
            user=user,
            profile=getattr(user, 'profile', None) if user else None,
        )
        lead.converted_business = business
        lead.save(update_fields=['converted_business', 'updated_at'])
        set_lead_stage(lead, Lead.STAGE_WON, user)
        _log_activity(lead, LeadActivity.TYPE_CONVERSION,
                      f'Converted to Business #{business_id} ({business.business_name})', user)
    return business, True


def link_lead_to_business(lead, business, user=None):
    """Attach an existing Business to a lead (staff action on the business
    verification page) and mark the lead Won. Returns (linked, error) — error
    is '' on success. Locks the lead so concurrent links cannot double-fire."""
    with transaction.atomic():
        lead = Lead.objects.select_for_update().get(pk=lead.pk)
        if lead.converted_business_id == business.pk:
            return True, ''
        if lead.converted_business_id:
            return False, f'Lead #{lead.pk} is already linked to Business #{lead.converted_business_id}'
        lead.converted_business = business
        lead.save(update_fields=['converted_business', 'updated_at'])
        set_lead_stage(lead, Lead.STAGE_WON, user)
        _log_activity(lead, LeadActivity.TYPE_CONVERSION,
                      f'Linked to Business #{business.pk} ({business.business_name})', user)
    return True, ''


def build_followup_digest():
    """Group due/overdue open leads by assignee. Returns {user_or_None: [leads]}."""
    today = timezone.localdate()
    due = (
        Lead.objects
        .filter(next_followup_at__lte=today, merged_into__isnull=True)
        .exclude(stage__in=closed_stage_keys())
        .select_related('assigned_to')
        .order_by('next_followup_at')
    )
    grouped = {}
    for lead in due:
        grouped.setdefault(lead.assigned_to, []).append(lead)
    return grouped


def _format_digest_message(leads, heading):
    today = timezone.localdate()
    lines = [heading, '']
    for lead in leads:
        overdue_days = (today - lead.next_followup_at).days
        when = f'{overdue_days}d overdue' if overdue_days > 0 else 'due today'
        name = lead.company_name or lead.contact_name or lead.phone or f'Lead #{lead.id}'
        lines.append(
            f'• {name} — {lead.get_stage_display()} ({when})\n'
            f'  {SITE_BASE_URL}/workforce/crm/leads/{lead.id}/'
        )
    return '\n'.join(lines)


def send_followup_digests(dry_run=False):
    """Send one WhatsApp digest per assignee with due/overdue leads.
    Unassigned due leads go to the admin number configured on the trigger row.
    Safe to re-run (read-only).

    Switched off with the ``wa_lead_followup_digest`` trigger (Auto Triggers →
    Marketing); the sender number and channel come from the ``followups`` route.
    """
    from core.whatsapp_utils import alert_recipient, send_routed_message, trigger_enabled

    if not trigger_enabled('wa_lead_followup_digest'):
        logger.info('crm digest: wa_lead_followup_digest is switched off — nothing sent')
        return {'sent': 0, 'skipped': 0, 'recipients': [], 'errors': [], 'disabled': True}

    grouped = build_followup_digest()
    result = {'sent': 0, 'skipped': 0, 'recipients': [], 'errors': []}

    for user, leads in grouped.items():
        if user is None:
            # Unassigned leads have no staff owner to message, so they go to the
            # digest trigger's "Sends to" number on the Auto Triggers page.
            number = alert_recipient('wa_lead_followup_digest')
            heading = f'📋 CRM: {len(leads)} unassigned lead(s) need follow-up'
            label = 'admin (unassigned)'
            if not number:
                logger.warning('crm digest: no admin recipient configured — unassigned block skipped')
                result['skipped'] += 1
                continue
        else:
            profile = getattr(user, 'profile', None)
            number = normalize_phone(
                (profile.whatsapp or profile.phone) if profile else ''
            )
            heading = f'📋 CRM follow-ups due: {len(leads)} lead(s)'
            label = user.get_username()
            if not number:
                logger.warning('crm digest: no WhatsApp number for staff %s — skipped', label)
                result['skipped'] += 1
                continue

        result['recipients'].append(f'{label} ({number}): {len(leads)} lead(s)')
        if dry_run:
            continue
        try:
            resp = send_routed_message(
                'followups', number, _format_digest_message(leads, heading))
            if resp.get('success'):
                result['sent'] += 1
            else:
                result['errors'].append(f'{label}: {resp.get("error", "send failed")}')
        except Exception as exc:
            logger.exception('crm digest: send failed for %s', label)
            result['errors'].append(f'{label}: {exc}')
    return result


def generate_lead_ai_summary(lead, wa_messages):
    """Claude-generated sales summary of the lead's WhatsApp conversation + activity.

    `wa_messages` are WhatsAppMessage rows oldest-first. Returns (summary, error)
    — exactly one is non-empty. Caller handles caching. Uses the ai_agent
    unified provider stack (zhipu/groq/anthropic per AI_CHAT_* settings).
    """
    lines = []
    for m in wa_messages[-120:]:
        who = 'Customer' if m.direction == 'inbound' else 'EzzyDelivery'
        ts = m.received_at.strftime('%d %b %H:%M') if m.received_at else ''
        body = (m.body or '').strip()
        if not body:
            body = f'[{m.get_message_type_display()} attachment]'
        lines.append(f'{who} ({ts}): {body[:500]}')
    convo = '\n'.join(lines) if lines else '(no WhatsApp messages on record)'

    notes = (lead.notes or '').strip()
    activities = list(
        lead.activities.order_by('-created_at')
        .values_list('activity_type', 'body')[:15]
    )
    activity_text = '\n'.join(f'- [{t}] {b[:200]}' for t, b in activities) or '(none)'

    prompt = (
        'You are a sales assistant for EzzyDelivery, a delivery/logistics company in Qatar. '
        'Summarize this CRM lead for a salesperson opening the file.\n\n'
        f'Lead: {lead.company_name or "-"} / contact {lead.contact_name or "-"} / '
        f'phone {lead.phone or "-"} / source {lead.get_source_display()} / '
        f'stage {lead.get_stage_display()} / category {lead.product_category or "-"}\n\n'
        f'Internal notes:\n{notes or "(none)"}\n\n'
        f'Activity log (newest first):\n{activity_text}\n\n'
        f'WhatsApp conversation (oldest first):\n{convo}\n\n'
        'Reply in plain text (no markdown symbols) with exactly these four short sections, '
        'each on its own lines:\n'
        'WHO: one line on who this lead is and what they want.\n'
        'STATUS: 1-2 lines on where the deal stands now.\n'
        'KEY POINTS: 2-4 short bullet lines starting with "- " (pricing discussed, '
        'products, objections, promises made).\n'
        'NEXT ACTION: one line recommending the next step for the salesperson.\n'
        'If the conversation is in Arabic, still answer in English. Be factual; do not invent details.'
    )

    try:
        from ai_agent.services.unified_service import (
            GeminiService, OpenAICompatService, get_chat_service,
        )
        service = get_chat_service('chat')
        available, msg = service.is_available()
        if not available:
            return '', f'AI is not available: {msg}'
        # Reasoning models (glm-4.7-flash) spend tokens thinking before the
        # answer; the default AI_AGENT_MAX_TOKENS budget truncates to empty
        # content on long prompts. These instances are built per-call, so
        # raising the cap here doesn't leak into other ai_agent features.
        for svc in (service, getattr(service, 'primary', None), getattr(service, 'fallback', None)):
            if isinstance(svc, (OpenAICompatService, GeminiService)):
                svc.max_tokens = 3000
        result = service.chat(messages=[{'role': 'user', 'content': prompt}])
        if result.get('error'):
            return '', f"AI summary failed: {result.get('message', 'unknown error')}"
        text = (result.get('content') or '').strip()
        if not text:
            return '', 'AI returned an empty response.'
        return text, ''
    except Exception:
        logger.exception('crm: AI summary failed for lead %s', lead.pk)
        return '', 'AI summary failed — check the server logs for details.'


# ── Driver lead ⇄ driver application status sync ─────────────────────────────
# Driver-category leads mirror the applicant's real form status. Which column a
# driver lands in is NOT hardcoded here — each driver-board LeadStage row carries
# `auto_rules` (see crm/stage_rules.py) and the columns are scanned right-to-left,
# first match wins, so terminal columns beat progress ones. Staff can add a column
# and bind it to a condition without a code change.
#
# A column with no auto_rules is a manual lane: reconcile never moves a card into
# or out of it, so a staff drag sticks.

def _driver_match_keys(*phones):
    """Last-8-digit keys used to match a lead phone against a driver's numbers.

    Only genuine phone shapes contribute a key. WhatsApp LIDs are 15-digit privacy
    identifiers that live in the same fields (`wa_chat_override`), and taking their
    last 8 digits invented a key that could collide with a real number.
    """
    keys = set()
    for p in phones:
        n = normalize_phone(p)
        # 8 = local Qatar, 9-13 = with a country code. Longer is a LID, not a phone.
        if 8 <= len(n) <= 13:
            keys.add(n[-8:])
    return keys


def is_lid_value(value):
    """True when a stored identifier is a WhatsApp LID rather than a phone number.

    LIDs are 14-15 digit privacy identifiers that share fields like
    ``wa_chat_override`` with real numbers. Running ``_phone_variants`` over one
    invents a '974' + last-8 number that can belong to a stranger — it then
    matches the wrong chat, or asks WAHA for a thread that does not exist. Every
    caller that wants to read one of those fields as a phone asks this first.

    Same boundary as :func:`_driver_match_keys`: 8 = local Qatar, 9-13 = with a
    country code, longer is a LID.
    """
    n = normalize_phone(value)
    return n.isdigit() and len(n) > 13


def add_wa_link(lead, identifier, session='', label='', user=None):
    """Join another WhatsApp number (or lid) to this lead. Returns (link, created).

    An existing link for the same identifier keeps its row; a label or session
    given now fills in whatever it was missing.
    """
    from .models import LeadWaLink

    ident = normalize_phone(identifier)[:50]
    if not ident:
        return None, False
    link, created = LeadWaLink.objects.get_or_create(
        lead=lead, identifier=ident,
        defaults={'session': (session or '')[:64], 'label': (label or '').strip()[:40], 'created_by': user},
    )
    if not created:
        fields = []
        if label and not link.label:
            link.label = label.strip()[:40]
            fields.append('label')
        if session and not link.session:
            link.session = session[:64]
            fields.append('session')
        if fields:
            link.save(update_fields=fields)
    return link, created


def remove_wa_link(lead, identifier):
    """Detach one linked number. True when something was removed."""
    from .models import LeadWaLink

    ident = normalize_phone(identifier)
    removed, _ = LeadWaLink.objects.filter(lead=lead, identifier=ident).delete()
    if lead.wa_chat_override and normalize_phone(lead.wa_chat_override) == ident:
        lead.wa_chat_override = ''
        lead.save(update_fields=['wa_chat_override', 'updated_at'])
        removed += 1
    return bool(removed)


def repoint_wa_link(lead, old_identifier, new_identifier):
    """A linked phone turned out to be stored under a lid — point the link at it."""
    from .models import LeadWaLink

    old, new = normalize_phone(old_identifier), normalize_phone(new_identifier)[:50]
    if not new or old == new:
        return
    link = LeadWaLink.objects.filter(lead=lead, identifier=old).first()
    if link is None:
        add_wa_link(lead, new)
    elif LeadWaLink.objects.filter(lead=lead, identifier=new).exists():
        link.delete()
    else:
        link.identifier = new
        link.save(update_fields=['identifier'])


def lid_phones(identifiers, sessions=()):
    """{lid: phone digits} for the lids among `identifiers` whose real number we know.

    The contact directory first (the daily contact sync fills it), then WAHA's
    cached lids map for `sessions`. Never calls WAHA; an unknown lid is simply
    absent from the result.
    """
    from django.core.cache import cache
    from whatsapp.models import WhatsAppContact
    from whatsapp.wa_chats_view import _lid_cache_key

    lids = {normalize_phone(i) for i in identifiers if is_lid_value(i)}
    if not lids:
        return {}
    out = dict(WhatsAppContact.objects.filter(lid__in=lids).exclude(phone='').values_list('lid', 'phone'))
    for session in dict.fromkeys(s for s in sessions if s):
        missing = lids - out.keys()
        if not missing:
            break
        mp = cache.get(_lid_cache_key(session))
        if isinstance(mp, dict):
            out.update({lid: mp[lid] for lid in missing if mp.get(lid)})
    return out


def accounts_for_numbers(identifiers, lid_phone=None):
    """{identifier: [account, ...]} — the platform user(s) registered on each number.

    A lead's numbers often turn into logins: the owner signs up to manage the
    dashboard, the office signs up as a team member. This only *reports* who
    they are; a lead never blocks anyone from creating an account (signup
    checks other accounts only). Lids are resolved to a phone through the
    contact directory first; a lid with no known phone matches nobody.
    """
    import re
    from django.db.models import Q
    from core.models import Profile

    phone_of = {}
    if lid_phone is None:
        lid_phone = lid_phones(identifiers)
    for ident in identifiers:
        n = normalize_phone(ident)
        phone = lid_phone.get(n, '') if is_lid_value(n) else n
        if 8 <= len(phone) <= 13:
            phone_of[ident] = phone[-8:]
    out = {i: [] for i in identifiers}
    if not phone_of:
        return out

    q = Q()
    for last8 in set(phone_of.values()):
        rx = r'\D*'.join(last8) + r'\D*$'
        q |= Q(phone__regex=rx) | Q(whatsapp__regex=rx)
    profiles = list(Profile.objects.filter(q).select_related('user'))
    if not profiles:
        return out

    from business.models import Business
    from fleet.models import Driver
    user_ids = [p.user_id for p in profiles if p.user_id]
    biz = {}
    for uid, name in Business.objects.filter(user_id__in=user_ids).values_list('user_id', 'business_name'):
        biz.setdefault(uid, name)
    driver_status = dict(Driver.objects.filter(profile__in=profiles).values_list('profile_id', 'driver_status'))

    for p in profiles:
        user = p.user
        if user is None:
            continue
        if user.is_staff or p.is_staff:
            role = 'Staff'
        elif p.user_id in biz:
            role = f'Client · {biz[p.user_id]}'
        elif p.pk in driver_status:
            role = 'Driver' if driver_status[p.pk] == 'approved' else 'Driver applicant'
        elif p.is_business:
            role = 'Client team'
        else:
            role = 'Customer'
        acct = {
            'user_id': user.pk,
            'username': user.username,
            'name': ' '.join(x for x in (p.first_name, p.last_name) if x) or user.get_full_name() or user.username,
            'role': role,
        }
        own = {re.sub(r'\D', '', v or '')[-8:] for v in (p.phone, p.whatsapp)}
        for ident, last8 in phone_of.items():
            if last8 in own and all(a['user_id'] != user.pk for a in out[ident]):
                out[ident].append(acct)
    return out


def lead_wa_numbers(lead):
    """Every WhatsApp number on a lead for the "Numbers" list: the lead's own phone
    (primary) plus each linked number with its label, and the platform account(s)
    registered on it. `blocked` marks numbers whose chat the CRM will not show
    because they belong to an account (see wa_read_blocked)."""
    rows = []
    phone = normalize_phone(lead.phone)
    if phone:
        rows.append({'identifier': phone, 'label': 'Primary', 'session': '', 'primary': True, 'is_lid': False})
    legacy = normalize_phone(lead.wa_chat_override or '')
    for link in lead.wa_links.all():
        rows.append({'identifier': link.identifier, 'label': link.label or 'Linked', 'session': link.session,
                     'primary': False, 'is_lid': is_lid_value(link.identifier)})
    if legacy and all(r['identifier'] != legacy for r in rows):
        rows.append({'identifier': legacy, 'label': 'Linked', 'session': '', 'primary': False,
                     'is_lid': is_lid_value(legacy)})
    idents = [r['identifier'] for r in rows]
    lid_phone = lid_phones(idents, [r['session'] for r in rows])
    accounts = accounts_for_numbers(idents, lid_phone=lid_phone)
    for r in rows:
        r['accounts'] = accounts.get(r['identifier'], [])
        r['blocked'] = bool(r['accounts'])
        # `phone` is the real number behind the row — a lid's comes from the
        # contact directory and is '' when unknown. A bare 8-digit number is a
        # Qatar local one (the driver form stores it that way); show it
        # dialable. Display only — never feed `display` back in as a lid.
        ident = r['identifier']
        phone = lid_phone.get(ident, '') if r['is_lid'] else ident
        r['phone'] = phone
        r['display'] = '+' + ('974' + phone if len(phone) == 8 else phone) if phone else ident
    return rows


def driver_lead_target_stage(driver, stages=None):
    """Stage key a driver-category lead should sit in for this driver's status.

    `stages` lets callers that already fetched the driver board's columns avoid a
    query per driver; omit it for one-off lookups."""
    if stages is None:
        stages = board_stages(Lead.CATEGORY_DRIVER)
    return stage_rules.target_stage_key(driver, stages)


# Any fixed number works; it only has to be the same for every caller.
_DRIVER_RECONCILE_LOCK = 4_752_118


def reconcile_driver_leads(driver_ids=None):
    """Make the driver board mirror the real applicant pool: ensure every driver
    application has a driver-category lead, and set each lead's stage to match
    its driver's current form status. Creates missing leads, advances existing
    ones. Safe (and cheap) to call on every driver-board render.

    `driver_ids` limits the pass to those applicants. The driver form passes the
    one it just saved, so the card exists before anyone opens the board — the
    WhatsApp inbox showed a fresh applicant as "No lead" until then.

    The board, the roster and the form can run this at the same moment, and two
    passes that both see no card for a new driver would each create one. A
    transaction-scoped lock makes them take turns."""
    from django.db import connection

    with transaction.atomic():
        if connection.vendor == 'postgresql':
            with connection.cursor() as cur:
                cur.execute('SELECT pg_advisory_xact_lock(%s)', [_DRIVER_RECONCILE_LOCK])
        return _reconcile_driver_leads(driver_ids)


def _reconcile_driver_leads(driver_ids):
    from django.db.models import Count, Q
    from fleet.models import Driver

    stages = board_stages(Lead.CATEGORY_DRIVER)
    if not stages:
        return 0, 0
    closed = LeadStage.closed_keys(Lead.CATEGORY_DRIVER)
    manual = stage_rules.manual_stage_keys(stages)

    drivers = (
        Driver.objects.select_related('user', 'profile')
        .prefetch_related('driver_document', 'driver_vehicle', 'preferred_zone_groups')
        # Annotated so a `has_deliveries` rule costs no extra query per driver.
        .annotate(dl_task_count=Count('deliverytask', distinct=True))
    )
    existing = Lead.objects.filter(category=Lead.CATEGORY_DRIVER, merged_into__isnull=True)
    if driver_ids is not None:
        drivers = drivers.filter(pk__in=driver_ids)
        # Their own cards, plus every unclaimed card one of them might claim.
        existing = existing.filter(Q(driver_id__in=driver_ids) | Q(driver__isnull=True))
    # wa_links feeds the phone keys of unbound cards below.
    existing = list(existing.prefetch_related('wa_links'))

    # Already-bound leads are looked up by their FK. Unbound ones are offered by phone
    # key and CLAIMED (popped) by the first driver that matches, so two drivers sharing
    # a number end up with one card each instead of fighting over the same one — which
    # is what left a real applicant with no card at all.
    leads_by_driver = {l.driver_id: l for l in existing if l.driver_id}
    unbound_by_key = {}
    for lead in existing:
        if lead.driver_id:
            continue
        for k in _driver_match_keys(lead.phone, *lead.wa_link_values):
            unbound_by_key.setdefault(k, []).append(lead)

    now = timezone.now()
    to_create, to_update, to_bind, newly_linked = [], [], [], []
    for d in drivers:
        prof = getattr(d, 'profile', None)
        keys = _driver_match_keys(d.driver_phone, d.driver_whatsapp, getattr(prof, 'whatsapp', ''))
        if not keys:
            continue
        target = stage_rules.target_stage_key(d, stages)
        if not target:
            continue
        name = ''
        if d.user:
            name = (d.user.get_full_name() or d.user.username or '').strip()

        lead = leads_by_driver.get(d.pk)
        if lead is None:
            for k in keys:
                bucket = unbound_by_key.get(k)
                while bucket:
                    candidate = bucket.pop(0)
                    if candidate.driver_id:
                        continue          # claimed by an earlier driver this pass
                    lead = candidate
                    lead.driver = d
                    leads_by_driver[d.pk] = lead
                    to_bind.append(lead)
                    # This card came in from WhatsApp (or by hand) and has now been
                    # matched to a real application — the same "one card, both
                    # origins" idea as a merge, recorded so it is not silent.
                    newly_linked.append((lead, d))
                    break
                if lead is not None:
                    break

        if lead is None:
            phone = normalize_phone(d.driver_phone or d.driver_whatsapp or (getattr(prof, 'whatsapp', '') or ''))
            new_lead = Lead(
                category=Lead.CATEGORY_DRIVER,
                source=Lead.SOURCE_DRIVER_APP,
                driver=d,
                phone=phone[:50],
                # bulk_create below skips Lead.save(), so the category tag is applied here
                # too — otherwise every reconciled driver card lands untagged.
                contact_name=apply_tag(name, Lead.CATEGORY_DRIVER),
                stage=target,
                stage_changed_at=now,
                closed_at=now if target in closed else None,
            )
            to_create.append(new_lead)
        elif lead.stage != target and lead.stage not in manual and not lead.stage_pinned:
            # Two things stop reconcile here: a card parked in a manual column, and a
            # card a staff member pinned by moving it somewhere the application status
            # does not justify. Both mean "a human decided this", so leave it alone.
            lead.stage = target
            lead.stage_changed_at = now
            lead.updated_at = now
            lead.closed_at = now if target in closed else None
            to_update.append(lead)

    if to_create:
        Lead.objects.bulk_create(to_create)
    if to_bind:
        Lead.objects.bulk_update(to_bind, ['driver'])
        for lead, d in newly_linked:
            _log_activity(
                lead, LeadActivity.TYPE_NOTE,
                f'Matched to driver application {d.driver_code or d.pk} by phone number — '
                'this card now covers both the conversation and the application.',
            )
    if to_update:
        Lead.objects.bulk_update(
            to_update, ['stage', 'stage_changed_at', 'closed_at', 'updated_at']
        )
    return len(to_create), len(to_update)


# Reverse direction: staff moving a driver lead into a column that declares a
# `write_back` applies that outcome to the applicant's real verification status
# (mirrors the Approve / Reject / Under-review actions on the verification page,
# including WhatsApp auto-flows). Columns with a blank write_back are board-only —
# they reflect the applicant's own progress and can't be forced by a drag.

def driver_candidates_for_lead(lead):
    """Every fleet.Driver whose number matches this lead. More than one means a
    duplicate registration — the caller must not pick for the user."""
    from django.db.models import Q
    from fleet.models import Driver

    keys = _driver_match_keys(lead.phone, *lead.wa_link_values)
    if not keys:
        return []
    q = Q()
    for k in keys:
        q |= Q(driver_phone__endswith=k) | Q(driver_whatsapp__endswith=k)
    return list(Driver.objects.select_related('profile').filter(q).order_by('driver_id'))


def lead_candidates_for_driver(driver):
    """Unbound driver cards whose numbers match this driver — the reverse of
    driver_candidates_for_lead, offered on the driver page's Leads tab so staff can
    connect a WhatsApp / manual card the reconcile pass never claimed.

    The SQL regex only narrows the search; each hit is re-checked with
    _driver_match_keys so a lid in wa_chat_override / wa_links can't match on its
    last 8 digits."""
    from django.db.models import Q

    prof = getattr(driver, 'profile', None)
    keys = _driver_match_keys(driver.driver_phone, driver.driver_whatsapp,
                              getattr(prof, 'whatsapp', '') or '')
    if not keys:
        return []
    q = Q()
    for k in keys:
        rx = r'\D*'.join(k) + r'\D*$'
        q |= Q(phone__regex=rx) | Q(wa_chat_override__regex=rx) | Q(wa_links__identifier__regex=rx)
    leads = (
        Lead.objects.filter(q, category=Lead.CATEGORY_DRIVER, driver__isnull=True,
                            merged_into__isnull=True)
        .distinct().prefetch_related('wa_links', 'merged_children')
    )
    return [l for l in leads if _driver_match_keys(l.phone, *l.wa_link_values) & keys]


def connect_lead_to_driver(lead, driver, user=None):
    """Bind an unclaimed driver card to this driver (sets the authoritative
    Lead.driver FK). Raises ValueError with a staff-readable reason when it can't.

    Only a number-matched candidate is accepted, and only while the driver has no
    card of its own — two live cards on one driver would make reconcile pick one
    at random. The stage catches up on the next driver-board reconcile."""
    if driver.crm_leads.filter(merged_into__isnull=True).exclude(pk=lead.pk).exists():
        raise ValueError('This driver already has a CRM card. Merge the cards on the CRM instead.')
    if lead.driver_id == driver.pk:
        return False
    if lead.driver_id:
        raise ValueError('That card is already connected to another driver.')
    if all(c.pk != lead.pk for c in lead_candidates_for_driver(driver)):
        raise ValueError("That card's numbers don't match this driver.")
    lead.driver = driver
    lead.save(update_fields=['driver', 'updated_at'])
    _log_activity(
        lead, LeadActivity.TYPE_NOTE,
        f'Connected to driver {driver.driver_code or driver.pk} from the driver page — '
        'this card now covers both the conversation and the application.',
        user=user,
    )
    return True


def _driver_for_lead(lead):
    """The applicant this lead is about, or None.

    The FK is authoritative once set, so the board, the detail page and the
    verification write-back can never resolve to different drivers (they used to:
    one matched by first-key, the other by newest-updated). Phone matching is only a
    fallback for a lead that has not been bound yet, and it REFUSES to guess when the
    number matches more than one applicant.
    """
    if lead.driver_id:
        return lead.driver

    candidates = driver_candidates_for_lead(lead)
    if len(candidates) == 1:
        return candidates[0]
    if len(candidates) > 1:
        logger.warning(
            'crm: lead %s phone matches %s drivers (%s) — refusing to guess',
            lead.pk, len(candidates), [d.pk for d in candidates],
        )
    return None


# ── Duplicate leads: two cards in one ────────────────────────────────────────
# The same prospect arrives twice — a pricing form and a WhatsApp chat, or a driver
# application and an inbox promote. Rather than flattening them (which loses which
# doors they came through) the newer card is absorbed INTO the older one: both rows
# survive, the child renders as a sub-card inside the parent, and the parent's card
# shows both source badges. Undoable, because nothing is destroyed.

def _lead_numbers(lead, include_ops=False):
    """Every phone-shaped number on a lead: phone, 2nd mobile and phone-shaped linked
    chats (never a lid); with `include_ops`, also the pricing form's operation-team
    number."""
    raw = [lead.phone, lead.phone_2] + [v for v in lead.wa_link_values if not is_lid_value(v)]
    if include_ops and lead.pricing_enquiry_id:
        raw.append(getattr(lead.pricing_enquiry, 'operation_team_contact_number', ''))
    return {n for n in (normalize_phone(r) for r in raw if r) if n}


def _cards_with_numbers(numbers, include_ops=False):
    """Leads carrying any of `numbers` as their phone, 2nd mobile or a linked chat —
    and with `include_ops`, as (the last 8 digits of) their pricing form's
    operation-team number.

    The operation-team number is only ever a suggestion: one owner can run two
    shops and type the same number into both forms, so nothing merges on it.
    """
    from django.db.models import F, Func, Q, Value
    from django.db.models.functions import Right

    variants, tails = set(), set()
    for number in numbers:
        variants |= set(_phone_variants(normalize_phone(number)))
        if len(number) >= 8:
            tails.add(number[-8:])
    if not variants:
        return Lead.objects.none()
    q = Q(phone__in=variants) | Q(phone_2__in=variants) | Q(wa_links__identifier__in=variants)
    qs = Lead.objects.all()
    if include_ops and tails:
        qs = qs.annotate(op_tail=Right(
            Func(F('pricing_enquiry__operation_team_contact_number'), Value(r'\D'), Value(''),
                 Value('g'), function='regexp_replace'), 8))
        q |= Q(op_tail__in=tails)
    return qs.filter(q).distinct()


def duplicate_candidates(lead, limit=10, include_ops=True):
    """Other open leads on the same board that share a number with this one.

    A business usually registers with the office line while the owner chats from
    their own phone, so every number on either card counts, not just `phone`.
    The detail page's suggestions include the pricing form's operation-team number;
    auto_merge_duplicate passes include_ops=False and merges on identity only.
    """
    # An absorbed card is already folded into its parent — offering the parent (or a
    # sibling) as a "separate card" to merge would just loop back to where it lives.
    if lead.merged_into_id:
        return []
    numbers = _lead_numbers(lead, include_ops)
    if not numbers:
        return []
    return list(
        _cards_with_numbers(numbers, include_ops)
        .filter(category=lead.category, merged_into__isnull=True)
        .exclude(pk=lead.pk)
        .exclude(stage__in=closed_stage_keys(lead.category))
        .select_related('assigned_to')
        .order_by('created_at')[:limit]
    )


def merge_leads(primary, duplicate, user=None):
    """Absorb `duplicate` into `primary`. Returns (ok, error).

    The duplicate keeps its own source, inquiry link and timeline — it is hidden from
    the board and shown inside the primary card instead. A driver binding moves up to
    the primary so its card keeps tracking the applicant.
    """
    if primary.pk == duplicate.pk:
        return False, 'A lead cannot be merged into itself.'
    if primary.category != duplicate.category:
        return False, (
            'These leads are on different boards — a business lead and a driver '
            'applicant are not the same record.'
        )
    if duplicate.merged_into_id:
        return False, f'Lead #{duplicate.pk} is already merged into #{duplicate.merged_into_id}.'
    if primary.merged_into_id:
        return False, (
            f'Lead #{primary.pk} is itself merged into #{primary.merged_into_id} — '
            'merge into that card instead.'
        )

    with transaction.atomic():
        # Anything already nested under the duplicate moves up, so the tree stays one
        # level deep and a card never hides another card's children.
        for grandchild in duplicate.merged_children.all():
            grandchild.merged_into = primary
            grandchild.save(update_fields=['merged_into', 'updated_at'])

        # Fill blanks on the survivor rather than overwrite — the primary is the card
        # staff already know, so its own values win. Where both have a value and they
        # disagree, the detail page lists it (merge_differences) for staff to pick.
        filled = []
        for field in MERGE_TEXT_FIELDS + ('wa_session',):
            if not getattr(primary, field, '') and getattr(duplicate, field, ''):
                setattr(primary, field, getattr(duplicate, field))
                filled.append(field)
        for field in MERGE_FK_FIELDS + ('next_followup_at',):
            if getattr(primary, field) is None and getattr(duplicate, field) is not None:
                setattr(primary, field, getattr(duplicate, field))
                filled.append(field)
        if filled:
            primary.save(update_fields=filled + ['updated_at'])

        # Every extra WhatsApp number on the absorbed card joins the survivor, plus the
        # absorbed card's own phone when it is a different number, so no chat is lost.
        primary_numbers = set(_phone_variants(normalize_phone(primary.phone))) if primary.phone else set()
        primary_numbers |= {normalize_phone(v) for v in primary.wa_link_values}
        added_links = []
        extra = [(l.identifier, l.session, l.label) for l in duplicate.wa_links.all()]
        if duplicate.phone and normalize_phone(duplicate.phone) not in primary_numbers:
            extra.insert(0, (duplicate.phone, '', f'From #{duplicate.pk}'))
        for identifier, session, label in extra:
            ident = normalize_phone(identifier)
            if not ident or ident in primary_numbers:
                continue
            link, created = add_wa_link(primary, ident, session=session, label=label, user=user)
            if created:
                added_links.append(link.identifier)
                primary_numbers.add(link.identifier)

        duplicate.merged_into = primary
        duplicate.merged_at = timezone.now()
        duplicate.merged_by = user
        # Read back after save — Lead.save() re-tags contact_name, and un-merge compares
        # against what actually landed on the parent.
        duplicate.merge_filled = {
            'fields': {f: _merge_value(primary, f) for f in filled},
            'wa_links': added_links,
        }
        duplicate.save(update_fields=['merged_into', 'merged_at', 'merged_by',
                                      'merge_filled', 'updated_at'])

    summary = []
    if filled:
        summary.append(f'Filled: {", ".join(MERGE_FIELD_LABELS.get(f, f) for f in filled)}.')
    if added_links:
        summary.append(f'Added WhatsApp number{"s" if len(added_links) > 1 else ""}: '
                       f'{", ".join(added_links)}.')
    _log_activity(
        primary, LeadActivity.TYPE_NOTE,
        ' '.join([f'Merged lead #{duplicate.pk} ({duplicate.get_source_display()}) into this card.']
                 + summary),
        user,
    )
    _log_activity(
        duplicate, LeadActivity.TYPE_NOTE,
        f'Merged into lead #{primary.pk} — this card is now shown inside that one.', user,
    )
    return True, ''


# Fields a merge compares and fills. Text blanks are '', FK/date blanks are None.
MERGE_TEXT_FIELDS = ('company_name', 'contact_name', 'phone', 'phone_2', 'product_category', 'notes')
MERGE_FK_FIELDS = ('assigned_to_id', 'driver_id', 'converted_business_id')
MERGE_FIELD_LABELS = {
    'company_name': 'Company', 'contact_name': 'Contact', 'phone': 'Phone', 'phone_2': '2nd mobile',
    'product_category': 'Product category', 'notes': 'Notes', 'wa_session': 'WhatsApp number used',
    'assigned_to_id': 'Assigned to', 'driver_id': 'Driver record',
    'converted_business_id': 'Converted business', 'next_followup_at': 'Next follow-up',
}
# What "Use this value" may copy from an absorbed card. The driver binding and the
# converted business are left out: repointing those moves real records, not a label.
MERGE_ADOPTABLE_FIELDS = ('company_name', 'contact_name', 'phone', 'phone_2', 'product_category',
                          'notes', 'assigned_to_id', 'next_followup_at')


def _merge_value(lead, field):
    """A field's value in JSON-safe form, for merge_filled and comparisons."""
    value = getattr(lead, field)
    if field == 'next_followup_at':
        return value.isoformat() if value else None
    return value


def _merge_display(lead, field):
    value = getattr(lead, field)
    if field == 'assigned_to_id':
        user = lead.assigned_to
        return (user.get_full_name() or user.username) if user else ''
    if field == 'next_followup_at':
        return value.strftime('%d %b %Y') if value else ''
    return value or ''


def _merge_same(field, a, b):
    if field == 'phone':
        # Same number in another format (55000123 vs 97455000123) is not a conflict.
        na, nb = normalize_phone(a), normalize_phone(b)
        return na == nb or bool(set(_phone_variants(na)) & set(_phone_variants(nb)))
    if isinstance(a, str) and isinstance(b, str):
        return a.strip() == b.strip()
    return a == b


def merge_differences(parent, child):
    """Fields where the parent and an absorbed card both hold a value and they disagree.

    The merge kept the parent's value silently; this is what the detail page shows so
    staff can see what the other card said and take it with "Use this value".
    """
    rows = []
    for field in MERGE_ADOPTABLE_FIELDS:
        mine, theirs = getattr(parent, field), getattr(child, field)
        if mine in (None, '') or theirs in (None, '') or _merge_same(field, mine, theirs):
            continue
        rows.append({
            'field': field,
            'label': MERGE_FIELD_LABELS[field],
            'parent_value': _merge_display(parent, field),
            'child_value': _merge_display(child, field),
        })
    return rows


def adopt_merged_value(parent, child, field, user=None):
    """Copy one field from an absorbed card onto its parent. Returns (ok, error)."""
    if child.merged_into_id != parent.pk:
        return False, 'That card is not merged into this one.'
    if field not in MERGE_ADOPTABLE_FIELDS:
        return False, 'That field cannot be copied.'
    old = _merge_display(parent, field)
    setattr(parent, field, getattr(child, field))
    parent.save(update_fields=[field, 'updated_at'])
    # A deliberate choice — un-merge must not take it back.
    recorded = (child.merge_filled or {}).get('fields', {})
    if field in recorded:
        recorded.pop(field)
        child.save(update_fields=['merge_filled', 'updated_at'])
    _log_activity(
        parent, LeadActivity.TYPE_NOTE,
        f'{MERGE_FIELD_LABELS[field]} taken from merged lead #{child.pk}: '
        f'"{old}" → "{_merge_display(parent, field)}".',
        user,
    )
    return True, ''


def unmerge_lead(child, user=None):
    """Put an absorbed lead back on the board as its own card.

    Takes back what the merge wrote onto the parent — the blanks it filled and the
    WhatsApp numbers it added — wherever the parent still holds the merged value.
    Anything staff changed since the merge is theirs and stays.
    """
    from .models import LeadWaLink

    if not child.merged_into_id:
        return False, 'That lead is not merged into anything.'
    parent = child.merged_into
    record = child.merge_filled or {}
    reverted, kept = [], []
    with transaction.atomic():
        clear = []
        for field, value in (record.get('fields') or {}).items():
            if not hasattr(parent, field):
                continue
            if _merge_value(parent, field) == value:
                blank = None if field in MERGE_FK_FIELDS or field == 'next_followup_at' else ''
                setattr(parent, field, blank)
                clear.append(field)
                reverted.append(MERGE_FIELD_LABELS.get(field, field))
            else:
                kept.append(MERGE_FIELD_LABELS.get(field, field))
        if clear:
            parent.save(update_fields=clear + ['updated_at'])
        links = record.get('wa_links') or []
        removed = 0
        if links:
            removed, _ = LeadWaLink.objects.filter(lead=parent, identifier__in=links).delete()

        child.merged_into = None
        child.merged_at = None
        child.merged_by = None
        child.merge_filled = {}
        child.save(update_fields=['merged_into', 'merged_at', 'merged_by',
                                  'merge_filled', 'updated_at'])

    _log_activity(child, LeadActivity.TYPE_NOTE,
                  f'Un-merged from lead #{parent.pk} — back on the board on its own.', user)
    detail = [f'Un-merged lead #{child.pk} — it is back on the board on its own.']
    if reverted:
        detail.append(f'Cleared what the merge had filled: {", ".join(reverted)}.')
    if removed:
        detail.append(f'Removed {removed} WhatsApp number{"s" if removed > 1 else ""} it had added.')
    if kept:
        detail.append(f'Kept (changed since the merge): {", ".join(kept)}.')
    _log_activity(parent, LeadActivity.TYPE_NOTE, ' '.join(detail), user)
    return True, ''


def auto_merge_duplicate(lead, user=None):
    """Fold a freshly created lead into an existing card for the same number.

    The OLDER card stays primary: staff already know it, it carries the history, and
    its id is the one in links and messages. Returns the surviving lead.
    """
    candidates = duplicate_candidates(lead, limit=1, include_ops=False)
    if not candidates:
        return lead
    other = candidates[0]
    older, newer = (other, lead) if other.created_at <= lead.created_at else (lead, other)
    ok, _error = merge_leads(older, newer, user)
    return older if ok else lead


def stage_move_conflict(lead, stage, stages=None):
    """'' when this lead's column agrees with its driver's real application status,
    otherwise a plain-English description of the disagreement.

    A driver card's column is normally recomputed from the driver record on every board
    render. Called AFTER a move (and after any write-back) to decide whether the card now
    needs pinning: if the rules would file it somewhere else, a human has overridden the
    data and reconcile must stop touching it.

    Always agrees when the lead is not a driver lead or the column is a manual lane —
    nothing auto-files those in the first place.
    """
    if lead.category != Lead.CATEGORY_DRIVER or stage is None:
        return ''
    if stage.is_manual:
        return ''

    if stages is None:
        stages = board_stages(Lead.CATEGORY_DRIVER)
    driver = _driver_for_lead(lead)
    if driver is None:
        return (
            f'No driver record matches this number yet, so "{stage.label}" cannot be '
            'confirmed from an application.'
        )

    target = stage_rules.target_stage_key(driver, stages)
    if target == stage.key:
        return ''

    where = next((s.label for s in stages if s.key == target), target)
    return (
        f'This applicant\'s application status puts them in "{where}", not "{stage.label}".'
    )


def pin_lead_stage(lead, user=None, reason=''):
    """Freeze this card where staff put it — reconcile stops overriding it."""
    if lead.stage_pinned:
        return False
    lead.stage_pinned = True
    lead.stage_pinned_at = timezone.now()
    lead.save(update_fields=['stage_pinned', 'stage_pinned_at', 'updated_at'])
    _log_activity(
        lead, LeadActivity.TYPE_STAGE_CHANGE,
        f'Pinned to "{lead.stage_label}" — auto-filing paused. {reason}'.strip(), user,
    )
    return True


def unpin_lead_stage(lead, user=None):
    """Hand this card back to auto-filing. The next board render re-files it from the
    driver's real application status, which may move it immediately."""
    if not lead.stage_pinned:
        return False
    lead.stage_pinned = False
    lead.stage_pinned_at = None
    lead.save(update_fields=['stage_pinned', 'stage_pinned_at', 'updated_at'])
    _log_activity(
        lead, LeadActivity.TYPE_STAGE_CHANGE,
        'Unpinned — the card follows the driver\'s application status again.', user,
    )
    return True


def sync_driver_status_from_lead(lead, user=None, rejection_reason=''):
    """Apply a driver lead's column to the matched driver's verification status.
    No-op for non-driver leads, columns with no write_back, or no phone match.
    Returns the driver whose status changed, or None."""
    if lead.category != Lead.CATEGORY_DRIVER:
        return None
    stage = get_stage(Lead.CATEGORY_DRIVER, lead.stage)
    target = stage.write_back if stage else ''
    if not target:
        return None
    driver = _driver_for_lead(lead)
    profile = getattr(driver, 'profile', None) if driver else None
    if profile is None or profile.verification_status == target:
        return None
    from workforce.views import apply_verification_status
    apply_verification_status(profile, target, user, {'rejection_reason': rejection_reason})
    _log_activity(
        lead, LeadActivity.TYPE_STAGE_CHANGE,
        f'Driver application status set to "{target}" from board move', user,
    )
    return driver
