# Purpose: One definition of "inbound WhatsApp senders not yet triaged" — the rows behind the CRM WhatsApp Inbox page and the daily triage cron.
# Used by: workforce.crm_views.crm_whatsapp_inbox, crm.wa_triage, crm/management/commands/triage_wa_inbox.py.
# Notes: Senders group per (session, from_number) because an @lid only identifies someone relative to the number that received it; ids resolve to real phones through the synced contact directory first, then WAHA's lids API.

import logging

from django.conf import settings
from django.db.models import Count, Max, Q

from crm import services as crm_services
from crm.models import InboxDismissal, Lead

logger = logging.getLogger(__name__)


def collect_senders(session_filter='', search='', wa_session_list=None):
    """Untriaged inbound senders, newest first.

    Each row is a dict: ``session``, ``from_number``, ``last_at``, ``msg_count``,
    ``contact_name``, optionally ``real_number`` (when the sender id is an @lid we
    could resolve) and ``existing_lead_id`` (an open lead on the same number).

    Senders already known to us — a number attached to a business, a dismissed one,
    or one belonging to a registered profile — are dropped entirely. Returns [] and
    logs if the WhatsApp side is unavailable, so neither caller breaks on it.
    """
    rows = []
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
                    from whatsapp import sessions as wa_sessions
                    from whatsapp.wa_chats_view import _lid_map, _waha_base
                    api_key = getattr(settings, 'WAHA_API_KEY', '') or ''
                    if wa_session_list is None:
                        wa_session_list = wa_sessions.list_sessions()
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
    return rows
