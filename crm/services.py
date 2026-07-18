# Purpose: All CRM business logic — lead creation from each source, stage sync with PricingEnquiry.crm_status, convert-to-Business, follow-up digest.
# Used by: workforce/crm_views.py, webpages/views.py hooks, workforce pricing_inquiry_update_status, crm management commands.
# Notes: Stage<->crm_status sync is two one-way functions (set_lead_stage writes to inquiry; sync_lead_from_pricing_status writes to lead) so no loop is possible.

import logging
import re

from django.db import transaction
from django.utils import timezone

from .models import Lead, LeadActivity

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


def normalize_phone(raw):
    """Digits-only form used for phone matching (e.g. '+974 6660-9347' -> '97466609347')."""
    return re.sub(r'\D', '', str(raw or ''))


def _log_activity(lead, activity_type, body, user=None):
    return LeadActivity.objects.create(
        lead=lead, activity_type=activity_type, body=body, created_by=user,
    )


def create_lead_from_pricing_inquiry(inquiry):
    """Idempotent: OneToOne get_or_create keyed on the inquiry."""
    lead, created = Lead.objects.get_or_create(
        pricing_enquiry=inquiry,
        defaults={
            'source': Lead.SOURCE_PRICING,
            'company_name': (inquiry.business_name or '')[:200],
            'contact_name': (inquiry.full_name or '')[:100],
            'phone': normalize_phone(inquiry.business_contact_number)[:50],
            'product_category': (inquiry.product_category or '')[:200],
            'stage': CRM_STATUS_TO_STAGE.get(inquiry.crm_status, Lead.STAGE_NEW),
            'assigned_to': inquiry.assigned_to,
        },
    )
    if created:
        _log_activity(lead, LeadActivity.TYPE_NOTE,
                      f'Lead created from pricing inquiry #{inquiry.id}')
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
    return lead, created


def create_lead_from_wa_number(phone, user=None):
    """WAHA inbox promote. Returns (lead, created). Dedupes on an existing open
    lead with the same normalized phone instead of creating a duplicate."""
    phone = normalize_phone(phone)
    if not phone:
        raise ValueError('A phone number is required')

    existing = (
        Lead.objects.filter(phone=phone)
        .exclude(stage__in=Lead.CLOSED_STAGES)
        .order_by('-created_at')
        .first()
    )
    if existing:
        return existing, False

    lead = Lead.objects.create(
        source=Lead.SOURCE_WA_INBOUND,
        phone=phone,
        notes=_recent_wa_messages_text(phone),
    )
    _log_activity(lead, LeadActivity.TYPE_NOTE,
                  'Lead created from inbound WhatsApp messages', user)
    return lead, True


def _recent_wa_messages_text(phone, limit=5):
    """Copy the sender's recent inbound WAHA message bodies into the new lead's notes."""
    try:
        from whatsapp.models import WhatsAppMessage
        bodies = list(
            WhatsAppMessage.objects
            .filter(direction='inbound', from_number=phone)
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
    """Validate + set stage, log activity, and sync the linked PricingEnquiry."""
    valid = {s for s, _ in Lead.STAGE_CHOICES}
    if new_stage not in valid:
        raise ValueError(f'Invalid stage: {new_stage}')
    if new_stage == lead.stage:
        return lead

    old_display = lead.get_stage_display()
    lead.stage = new_stage
    lead.stage_changed_at = timezone.now()
    lead.closed_at = timezone.now() if new_stage in Lead.CLOSED_STAGES else None
    lead.save(update_fields=['stage', 'stage_changed_at', 'closed_at', 'updated_at'])

    _log_activity(lead, LeadActivity.TYPE_STAGE_CHANGE,
                  f'Stage: {old_display} → {lead.get_stage_display()}', user)

    # One-way sync back to the legacy pricing-inquiry CRM status
    inquiry = lead.pricing_enquiry
    if inquiry:
        new_status = STAGE_TO_CRM_STATUS[new_stage]
        if inquiry.crm_status != new_status:
            inquiry.crm_status = new_status
            inquiry.save(update_fields=['crm_status', 'date_modified'])
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
        lead.closed_at = timezone.now() if new_stage in Lead.CLOSED_STAGES else None
        updates += ['stage', 'stage_changed_at', 'closed_at']
        _log_activity(lead, LeadActivity.TYPE_STAGE_CHANGE,
                      f'Stage set to {lead.get_stage_display()} (via pricing inquiry page)')
    if inquiry.assigned_to_id != lead.assigned_to_id:
        lead.assigned_to_id = inquiry.assigned_to_id
        updates.append('assigned_to')
    if updates:
        lead.save(update_fields=updates + ['updated_at'])
    return lead


def convert_lead_to_business(lead, user=None):
    """Create a pending Business from the lead. Returns (business, created).
    Idempotent: an already-converted lead returns its existing business."""
    from business.models import Business
    from core.views import generate_secure_id

    if lead.converted_business_id:
        return lead.converted_business, False

    with transaction.atomic():
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


def build_followup_digest():
    """Group due/overdue open leads by assignee. Returns {user_or_None: [leads]}."""
    today = timezone.localdate()
    due = (
        Lead.objects
        .filter(next_followup_at__lte=today)
        .exclude(stage__in=Lead.CLOSED_STAGES)
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
    Unassigned due leads go to the admin number. Safe to re-run (read-only)."""
    from core.whatsapp_utils import send_whatsapp_message_api

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
            resp = send_whatsapp_message_api(number, _format_digest_message(leads, heading))
            if resp.get('success'):
                result['sent'] += 1
            else:
                result['errors'].append(f'{label}: {resp.get("error", "send failed")}')
        except Exception as exc:
            logger.exception('crm digest: send failed for %s', label)
            result['errors'].append(f'{label}: {exc}')
    return result
