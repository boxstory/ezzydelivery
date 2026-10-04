"""
Purpose: Marketing-only WhatsApp labels — decides which chats a staff member may open in the inbox and the CRM.
Used by: whatsapp/wa_chats_view.py, crm/services.wa_read_blocked, workforce.views.whatsapp_label_access
Notes: Which chats carry a label is read live from WAHA and cached briefly. If it cannot be read and no copy is cached, non-marketing staff are refused (fails closed).
"""
import logging

import requests
from django.conf import settings
from django.core.cache import cache
from django.db.models import Q

logger = logging.getLogger(__name__)

# A label added on the phone takes effect within this long.
CHATS_TTL = 120
# Last good read, used while WAHA is unreachable.
STALE_TTL = 24 * 60 * 60

REFUSAL = 'This chat is marketing-only.'


class MembershipUnknown(Exception):
    """A restricted label's chats could not be read and nothing is cached."""


def can_see_all(user):
    """Marketing staff and super admins see every chat."""
    from core.departments import MKT, user_departments

    return bool(getattr(user, 'is_authenticated', False) and MKT in user_departments(user))


def bare(ident):
    """'97455…@c.us' / '1234@lid' / '97455…' → the digits WhatsAppMessage stores."""
    return str(ident or '').split('@', 1)[0].strip()


def restricted_label_ids(session):
    from .models import RestrictedChatLabel

    return set(RestrictedChatLabel.objects.filter(session=session).values_list('label_id', flat=True))


def restricted_sessions():
    from .models import RestrictedChatLabel

    return set(RestrictedChatLabel.objects.values_list('session', flat=True).distinct())


def _waha_get(path):
    base = (getattr(settings, 'WAHA_BASE_URL', 'http://127.0.0.1:3000') or '').rstrip('/')
    try:
        resp = requests.get(f'{base}{path}', headers={'X-Api-Key': getattr(settings, 'WAHA_API_KEY', '') or ''},
                            timeout=10)
    except requests.exceptions.RequestException:
        return None
    if resp.status_code != 200:
        return None
    try:
        return resp.json()
    except ValueError:
        return None


def label_chats(session, label_id):
    """Chat ids carrying this label, or None when WAHA cannot say and nothing is cached."""
    key = f'wa_label_chats:{session}:{label_id}'
    hit = cache.get(key)
    if hit is not None:
        return hit
    body = _waha_get(f'/api/{session}/labels/{label_id}/chats')
    if not isinstance(body, list):
        return cache.get(key + ':stale')
    ids = []
    for c in body:
        if not isinstance(c, dict):
            continue
        cid = c.get('id')
        cid = cid.get('_serialized') if isinstance(cid, dict) else cid
        if cid:
            ids.append(str(cid))
    cache.set(key, ids, CHATS_TTL)
    cache.set(key + ':stale', ids, STALE_TTL)
    return ids


def restricted_identifiers(session):
    """Bare ids (phone and lid alike) of every chat on this number under a restricted label.

    Raises MembershipUnknown when a restricted label's chats cannot be read.
    A chat may be listed by its lid while our message rows carry the phone, or
    the other way round, so both are added through the contact directory.
    """
    from .models import WhatsAppContact

    label_ids = restricted_label_ids(session)
    if not label_ids:
        return set()
    idents = set()
    for label_id in label_ids:
        chats = label_chats(session, label_id)
        if chats is None:
            raise MembershipUnknown(f'{session}:{label_id}')
        idents.update(bare(c) for c in chats if bare(c))
    if idents:
        listed = set(idents)
        for phone, lid in WhatsAppContact.objects.filter(session=session).filter(
            Q(phone__in=listed) | Q(lid__in=listed)
        ).values_list('phone', 'lid'):
            idents.update(v for v in (phone, lid) if v)
    return idents


def hidden_identifiers(user, session):
    """Bare ids this user may not see on this number; raises MembershipUnknown."""
    if can_see_all(user):
        return set()
    return restricted_identifiers(session)


def chat_hidden(user, session, chat_id):
    """True when this user may not open the chat (also when it cannot be checked)."""
    if can_see_all(user):
        return False
    try:
        return bare(chat_id) in restricted_identifiers(session)
    except MembershipUnknown:
        logger.warning('wa label access: membership unknown on %s, refusing %s', session, user)
        return True


def _candidates(ident):
    b = bare(ident)
    if not b:
        return set()
    out = {b}
    digits = ''.join(ch for ch in b if ch.isdigit())
    if digits:
        out.add(digits)
        if len(digits) == 8:
            out.add('974' + digits)
    return out


def identifiers_hidden(user, identifiers):
    """True when any of these phones/lids is a restricted chat on any number.

    For the CRM, which reads a person's conversation across all our numbers.
    """
    if can_see_all(user):
        return False
    wanted = set()
    for ident in identifiers or ():
        wanted |= _candidates(ident)
    if not wanted:
        return False
    for session in restricted_sessions():
        try:
            if wanted & restricted_identifiers(session):
                return True
        except MembershipUnknown:
            logger.warning('wa label access: membership unknown on %s, refusing %s', session, user)
            return True
    return False
