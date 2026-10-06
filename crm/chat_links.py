# Purpose: Tie an owner's WhatsApp chat to the lead their pricing form created, when the form names a different (office) number.
# Used by: whatsapp/waha_views.waha_webhook (a "Ref P123-ab12cd" in an inbound message), webpages/views (?wa=<code> on the
#          pricing link sent from the inbox), workforce/crm_views.crm_wa_send_link (tags that link).
# Notes: Linking adds the chat as a LeadWaLink labelled Owner and folds any separate open card for that chat into one
#        (older card stays primary, as in auto_merge_duplicate), so it is reversible with Unmerge. Never creates a lead.

import hashlib
import hmac
import logging
import re
import secrets

from django.conf import settings
from django.db.models import Q

from .models import Lead, LeadActivity, PricingLinkRef

logger = logging.getLogger(__name__)

OWNER_LABEL = 'Owner'

# "Ref P125-3f9a2c": P = pricing enquiry, W = WhatsApp quick inquiry, then the row id
# and a keyed checksum, so nobody can attach their chat to a lead by guessing ids.
_REF_RE = re.compile(r'\bRef\W{0,3}([PW])(\d{1,9})-([0-9a-f]{6})\b', re.IGNORECASE)
_LINK_CODE_RE = re.compile(r'^[A-Za-z0-9_-]{8}$')
# The pricing form's public entry points, as they appear in the inbox's link message.
_PRICING_URL_RE = re.compile(r'(https?://(?:www\.)?ezzydelivery\.qa/3pl/(?:pricing|inquiry)/)(?![?#\w])')


def _checksum(kind, pk):
    msg = f'crm-chat-ref:{kind}{pk}'.encode()
    return hmac.new(settings.SECRET_KEY.encode(), msg, hashlib.sha256).hexdigest()[:6]


def ref_for(kind, pk):
    """The reference a customer's prefilled WhatsApp message carries, e.g. 'Ref P125-3f9a2c'."""
    return f'Ref {kind}{pk}-{_checksum(kind, pk)}'


def parse_ref(text):
    """(kind, pk) from the first valid reference in `text`, or None."""
    for match in _REF_RE.finditer(text or ''):
        kind, pk, code = match.group(1).upper(), int(match.group(2)), match.group(3).lower()
        if hmac.compare_digest(code, _checksum(kind, pk)):
            return kind, pk
    return None


def _lead_for_ref(kind, pk):
    field = 'pricing_enquiry_id' if kind == 'P' else 'whatsapp_inquiry_id'
    return Lead.objects.filter(**{field: pk}).select_related('merged_into').first()


def _phone_behind(identifier, session):
    """Real phone digits for a chat identifier: itself if it is a phone, the
    directory's phone for a lid on that session, else ''."""
    from whatsapp.models import WhatsAppContact
    from .services import is_lid_value, normalize_phone

    if not is_lid_value(identifier):
        return identifier
    contact = (WhatsAppContact.objects.filter(session=session, lid=identifier)
               .exclude(phone='').first())
    return normalize_phone(contact.phone) if contact else ''


def _open_cards_for_chat(lead, identifier, phone, session):
    """Other open, unmerged cards on the lead's board that belong to this chat."""
    from .services import _phone_variants, closed_stage_keys, is_lid_value

    if is_lid_value(identifier):
        # A lid is issued per linked device: the same digits on our other number are
        # someone else. An unscoped (blank-session) link is an operator's assertion.
        q = Q(wa_links__identifier=identifier) & (Q(wa_links__session=session) | Q(wa_links__session=''))
    else:
        q = Q(wa_links__identifier=identifier)
    if phone:
        variants = list(_phone_variants(phone))
        q |= Q(phone__in=variants) | Q(phone_2__in=variants) | Q(wa_links__identifier__in=variants)
    return list(
        Lead.objects.filter(q, category=lead.category, merged_into__isnull=True)
        .exclude(pk=lead.pk)
        .exclude(stage__in=closed_stage_keys(lead.category))
        .distinct().order_by('created_at')
    )


def _already_on(lead, identifier):
    """True when the lead page already shows this chat: it is the lead's phone or
    one of its linked numbers (the 2nd mobile is not read for chats)."""
    from .services import _phone_variants, normalize_phone

    own = set(_phone_variants(normalize_phone(lead.phone))) if lead.phone else set()
    own |= {normalize_phone(v) for v in lead.wa_link_values}
    return normalize_phone(identifier) in own


def attach_chat_to_lead(lead, identifier, session='', note='', user=None):
    """Join one WhatsApp chat to `lead`; fold any separate open card for it in.

    `identifier` is how the chat's messages are stored: phone digits, or a lid
    (meaningful only on `session`). Returns the surviving lead.
    """
    from .services import _log_activity, add_wa_link, merge_leads, normalize_phone

    ident = normalize_phone(identifier)
    if not ident:
        return lead
    primary = lead.merged_into or lead
    phone = _phone_behind(ident, session)

    for other in _open_cards_for_chat(primary, ident, phone, session):
        older, newer = (other, primary) if other.created_at <= primary.created_at else (primary, other)
        ok, error = merge_leads(older, newer, user)
        if ok:
            primary = older
        else:
            logger.info('crm chat link: could not merge #%s into #%s: %s', newer.pk, older.pk, error)

    if not _already_on(primary, ident):
        add_wa_link(primary, ident, session=session, label=OWNER_LABEL, user=user)
    if note:
        _log_activity(primary, LeadActivity.TYPE_NOTE, note, user)
    return primary


def link_from_message(session, from_number, body, is_group=False):
    """Webhook hook: an inbound message carrying a lead reference links its chat.

    Returns the lead linked, or None. Group chats never link — the sender there is a
    participant, not the chat the lead should follow."""
    if is_group or not from_number:
        return None
    found = parse_ref(body)
    if not found:
        return None
    lead = _lead_for_ref(*found)
    if lead is None:
        return None
    if _already_on(lead.merged_into or lead, from_number):
        return lead.merged_into or lead
    source = 'pricing form' if found[0] == 'P' else 'WhatsApp quick inquiry'
    return attach_chat_to_lead(
        lead, from_number, session,
        note=f'WhatsApp chat {from_number} linked as {OWNER_LABEL}: it wrote with the reference '
             f'from the {source} confirmation, so it is the same business.')


# ---------------------------------------------------------------- inbox → form

def tag_pricing_link(body, session, phone, user=None):
    """Add ?wa=<code> to the pricing-form links in an inbox message. Returns the
    new body; a body with no pricing link comes back unchanged and records nothing."""
    if not _PRICING_URL_RE.search(body or ''):
        return body
    ref = PricingLinkRef.objects.create(
        code=secrets.token_urlsafe(6)[:8], session=(session or '')[:64],
        identifier=(phone or '')[:50], sent_by=user)
    return _PRICING_URL_RE.sub(lambda m: f'{m.group(1)}?wa={ref.code}', body)


def remember_link_code(request):
    """Keep a ?wa=<code> from the inbox's pricing link for the rest of the form."""
    code = (request.GET.get('wa') or '').strip()
    if _LINK_CODE_RE.match(code):
        request.session['pricing_wa_ref'] = code


def link_from_pricing_ref(lead, request):
    """After the form creates `lead`: attach the chat the inbox sent this link to."""
    from django.utils import timezone

    code = request.session.pop('pricing_wa_ref', None)
    if not lead or not code:
        return lead
    ref = PricingLinkRef.objects.filter(code=code).first()
    if ref is None or not ref.identifier:
        return lead
    survivor = attach_chat_to_lead(
        lead, ref.identifier, ref.session,
        note=f'WhatsApp chat {ref.identifier} linked as {OWNER_LABEL}: the form was opened from '
             f'the pricing link sent to that chat on {timezone.localtime(ref.created_at):%d %b %Y}.')
    PricingLinkRef.objects.filter(pk=ref.pk).update(used_at=timezone.now(), lead=survivor)
    return survivor
