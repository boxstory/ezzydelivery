# Purpose: All CRM business logic — lead creation from each source, stage sync with PricingEnquiry.crm_status, convert-to-Business, follow-up digest.
# Used by: workforce/crm_views.py, webpages/views.py hooks, workforce pricing_inquiry_update_status, crm management commands.
# Notes: Stage<->crm_status sync is two one-way functions (set_lead_stage writes to inquiry; sync_lead_from_pricing_status writes to lead) so no loop is possible.
#        Board columns are LeadStage rows, so which stage a driver lands in is data, not code — see crm/stage_rules.py.

import logging
import re

from django.db import transaction
from django.utils import timezone

from . import stage_rules
from .models import Lead, LeadActivity, LeadStage

logger = logging.getLogger(__name__)

SITE_BASE_URL = 'https://ezzydelivery.qa'
ADMIN_WHATSAPP_NUMBER = '97466451589'  # same admin target as send_admin_inquiry_notification

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
            'lead_name': lead.contact_name or lead.company_name or '',
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


def wa_read_blocked(identifiers):
    """'' when this conversation may be opened in the CRM, else the refusal reason.

    Takes the resolved identifier set for a chat (phones and/or @lid values) and
    resolves each back to a phone through the contact directory, because inbound rows
    are keyed by LID and a LID lookup is the only way to spot a platform account.
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

    existing = (
        Lead.objects.filter(phone__in=_phone_variants(phone), merged_into__isnull=True)
        .exclude(stage__in=closed_stage_keys())
        .order_by('-created_at')
        .first()
    )
    if existing:
        return existing, False

    contact = _wa_contact_for_phone(phone)
    name = contact.display_name if contact else ''

    lead = Lead.objects.create(
        source=Lead.SOURCE_WA_INBOUND,
        category=category,
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
    if new_stage == Lead.STAGE_WON:
        fire_lead_trigger('lead_won', lead)
    elif new_stage == Lead.STAGE_LOST:
        fire_lead_trigger('lead_lost', lead)
    return lead


def sync_lead_from_pricing_status(inquiry):
    """Called from the legacy pricing_inquiry_update_status view: pull the
    inquiry's crm_status/assignee onto its lead WITHOUT writing back (no loop)."""
    lead = getattr(inquiry, 'lead', None)
    if lead is None:
        return None

    updates = []
    new_stage = CRM_STATUS_TO_STAGE.get(inquiry.crm_status)
    if new_stage and new_stage != lead.stage:
        lead.stage = new_stage
        lead.stage_changed_at = timezone.now()
        lead.closed_at = timezone.now() if is_closed_stage(lead.category, new_stage) else None
        updates += ['stage', 'stage_changed_at', 'closed_at']
        _log_activity(lead, LeadActivity.TYPE_STAGE_CHANGE,
                      f'Stage set to {lead.stage_label} (via pricing inquiry page)')
    if inquiry.assigned_to_id != lead.assigned_to_id:
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
            business_name=(lead.company_name or lead.contact_name or '')[:100],
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
    Unassigned due leads go to the admin number. Safe to re-run (read-only).

    Switched off with the ``wa_lead_followup_digest`` trigger (Auto Triggers →
    Marketing); the sender number and channel come from the ``followups`` route.
    """
    from core.whatsapp_utils import send_routed_message, trigger_enabled

    if not trigger_enabled('wa_lead_followup_digest'):
        logger.info('crm digest: wa_lead_followup_digest is switched off — nothing sent')
        return {'sent': 0, 'skipped': 0, 'recipients': [], 'errors': [], 'disabled': True}

    grouped = build_followup_digest()
    result = {'sent': 0, 'skipped': 0, 'recipients': [], 'errors': []}

    for user, leads in grouped.items():
        if user is None:
            number = ADMIN_WHATSAPP_NUMBER
            heading = f'📋 CRM: {len(leads)} unassigned lead(s) need follow-up'
            label = 'admin (unassigned)'
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


def driver_lead_target_stage(driver, stages=None):
    """Stage key a driver-category lead should sit in for this driver's status.

    `stages` lets callers that already fetched the driver board's columns avoid a
    query per driver; omit it for one-off lookups."""
    if stages is None:
        stages = board_stages(Lead.CATEGORY_DRIVER)
    return stage_rules.target_stage_key(driver, stages)


def reconcile_driver_leads():
    """Make the driver board mirror the real applicant pool: ensure every driver
    application has a driver-category lead, and set each lead's stage to match
    its driver's current form status. Creates missing leads, advances existing
    ones. Safe (and cheap) to call on every driver-board render."""
    from django.db.models import Count
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
    existing = list(Lead.objects.filter(
        category=Lead.CATEGORY_DRIVER, merged_into__isnull=True))

    # Already-bound leads are looked up by their FK. Unbound ones are offered by phone
    # key and CLAIMED (popped) by the first driver that matches, so two drivers sharing
    # a number end up with one card each instead of fighting over the same one — which
    # is what left a real applicant with no card at all.
    leads_by_driver = {l.driver_id: l for l in existing if l.driver_id}
    unbound_by_key = {}
    for lead in existing:
        if lead.driver_id:
            continue
        for k in _driver_match_keys(lead.phone, lead.wa_chat_override):
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
                contact_name=name[:100],
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

    keys = _driver_match_keys(lead.phone, lead.wa_chat_override)
    if not keys:
        return []
    q = Q()
    for k in keys:
        q |= Q(driver_phone__endswith=k) | Q(driver_whatsapp__endswith=k)
    return list(Driver.objects.select_related('profile').filter(q).order_by('driver_id'))


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

def duplicate_candidates(lead, limit=10):
    """Other open leads on the same board whose number matches this one."""
    if not lead.phone:
        return []
    variants = _phone_variants(normalize_phone(lead.phone))
    if not variants:
        return []
    return list(
        Lead.objects
        .filter(category=lead.category, phone__in=variants, merged_into__isnull=True)
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
        # staff already know, so its own values win.
        filled = []
        for field in ('company_name', 'contact_name', 'phone', 'product_category',
                      'wa_chat_override', 'wa_session'):
            if not getattr(primary, field, '') and getattr(duplicate, field, ''):
                setattr(primary, field, getattr(duplicate, field))
                filled.append(field)
        if primary.assigned_to_id is None and duplicate.assigned_to_id:
            primary.assigned_to_id = duplicate.assigned_to_id
            filled.append('assigned_to')
        if primary.next_followup_at is None and duplicate.next_followup_at:
            primary.next_followup_at = duplicate.next_followup_at
            filled.append('next_followup_at')
        if primary.driver_id is None and duplicate.driver_id:
            primary.driver_id = duplicate.driver_id
            filled.append('driver')
        if primary.converted_business_id is None and duplicate.converted_business_id:
            primary.converted_business_id = duplicate.converted_business_id
            filled.append('converted_business')
        if filled:
            primary.save(update_fields=filled + ['updated_at'])

        duplicate.merged_into = primary
        duplicate.merged_at = timezone.now()
        duplicate.merged_by = user
        duplicate.save(update_fields=['merged_into', 'merged_at', 'merged_by', 'updated_at'])

    _log_activity(
        primary, LeadActivity.TYPE_NOTE,
        f'Merged lead #{duplicate.pk} ({duplicate.get_source_display()}) into this card.'
        + (f' Filled: {", ".join(filled)}.' if filled else ''),
        user,
    )
    _log_activity(
        duplicate, LeadActivity.TYPE_NOTE,
        f'Merged into lead #{primary.pk} — this card is now shown inside that one.', user,
    )
    return True, ''


def unmerge_lead(child, user=None):
    """Put an absorbed lead back on the board as its own card."""
    if not child.merged_into_id:
        return False, 'That lead is not merged into anything.'
    parent_id = child.merged_into_id
    child.merged_into = None
    child.merged_at = None
    child.merged_by = None
    child.save(update_fields=['merged_into', 'merged_at', 'merged_by', 'updated_at'])
    _log_activity(child, LeadActivity.TYPE_NOTE,
                  f'Un-merged from lead #{parent_id} — back on the board on its own.', user)
    return True, ''


def auto_merge_duplicate(lead, user=None):
    """Fold a freshly created lead into an existing card for the same number.

    The OLDER card stays primary: staff already know it, it carries the history, and
    its id is the one in links and messages. Returns the surviving lead.
    """
    candidates = duplicate_candidates(lead, limit=1)
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
