# Purpose: Sync WhatsApp contacts (phone, lid, names) from WAHA into WhatsAppContact.
# Used by: workforce.crm_views.crm_wa_resync (inbox Resync button); sync_wa_contacts cron; callable from shell.
# Notes: Full-directory upsert keyed on phone digits; only rows that changed are written.
#        Also walks the chat list so unknown senders (absent from the contacts
#        API) still get their id + number + chat name saved.

import logging

import requests
from django.conf import settings
from django.utils import timezone

from . import sessions as wa_sessions
from .models import WhatsAppContact

logger = logging.getLogger(__name__)


def _digits(jid):
    return str(jid or '').split('@', 1)[0]


def _waha_get(path, params=None, timeout=30):
    base = (getattr(settings, 'WAHA_BASE_URL', '') or '').rstrip('/')
    resp = requests.get(
        f'{base}{path}',
        params=params,
        headers={'X-Api-Key': getattr(settings, 'WAHA_API_KEY', '') or ''},
        timeout=timeout,
    )
    resp.raise_for_status()
    return resp.json()


def sync_contacts(session=None):
    """Pull lids + contacts from WAHA and upsert WhatsAppContact rows.

    Rows are scoped to the session: lids are issued per linked device, so each
    of our numbers hands out a different lid for the same person. Syncing two
    sessions into one row would flap the lid on every cron pass.

    Returns {'seen': n, 'created': n, 'updated': n} or raises on WAHA failure.
    """
    session = wa_sessions.normalize(session)

    lid_to_phone = {}
    for row in _waha_get(f'/api/{session}/lids', params={'limit': 100000}, timeout=20):
        if isinstance(row, dict):
            lid, pn = _digits(row.get('lid')), _digits(row.get('pn'))
            if lid and pn:
                lid_to_phone[lid] = pn
    phone_to_lid = {pn: lid for lid, pn in lid_to_phone.items()}

    # One merged record per phone. @lid ids resolve through the lids map;
    # unresolvable @lid-only entries are skipped (no usable number to store).
    merged = {}
    # 180s, not 60s: the main number's directory is ~6.5 MB / ~8.6k contacts and
    # WAHA takes ~80s to serialise it, so a 60s cap failed every nightly pass and
    # silently froze that session's names (the inbox then shows bare lids).
    for c in _waha_get('/api/contacts/all', params={'session': session}, timeout=180):
        if not isinstance(c, dict) or c.get('isGroup') or c.get('isMe'):
            continue
        cid = str(c.get('id') or '')
        if cid.endswith('@lid'):
            phone = lid_to_phone.get(_digits(cid))
        elif cid.endswith('@c.us'):
            phone = _digits(cid)
        else:
            continue
        if not phone or not phone.isdigit():
            continue
        rec = merged.setdefault(phone, {
            'saved_name': '', 'push_name': '',
            'is_business': False, 'is_my_contact': False,
        })
        # Same phone can appear twice (once per alias) — keep the richest values.
        rec['saved_name'] = rec['saved_name'] or (c.get('name') or '').strip()
        rec['push_name'] = rec['push_name'] or (c.get('pushname') or '').strip()
        rec['is_business'] = rec['is_business'] or bool(c.get('isBusiness'))
        rec['is_my_contact'] = rec['is_my_contact'] or bool(c.get('isMyContact'))

    # Chat list too — unknown senders often aren't in the contacts API at all,
    # but every open chat carries its id (phone or lid) + display name. Saving
    # those lets the CRM inbox resolve bare lid senders to a real number.
    try:
        chats = _waha_get(f'/api/{session}/chats', params={'limit': 100000}, timeout=60)
    except Exception:
        logger.exception('wa contacts: chat list fetch failed — contacts-only sync')
        chats = []
    for chat in chats if isinstance(chats, list) else []:
        if not isinstance(chat, dict):
            continue
        cid = chat.get('id')
        if isinstance(cid, dict):
            cid = cid.get('_serialized')
        cid = str(cid or '')
        digits = _digits(cid)
        # Skip groups (old '974...-163...' style, @g.us, and 120363... ids),
        # status broadcasts, and anything non-numeric.
        if (not digits.isdigit() or cid.endswith('@g.us')
                or (digits.startswith('120363') and len(digits) > 15)):
            continue
        if cid.endswith('@lid') or len(digits) > 13:
            phone = lid_to_phone.get(digits)
            lid_from_chat = digits
        else:
            phone = digits
            lid_from_chat = ''
        if not phone:
            continue  # lid with no known number — nothing usable to store yet
        if lid_from_chat and phone not in phone_to_lid:
            phone_to_lid[phone] = lid_from_chat
        rec = merged.setdefault(phone, {
            'saved_name': '', 'push_name': '',
            'is_business': False, 'is_my_contact': False,
        })
        rec['push_name'] = rec['push_name'] or (chat.get('name') or '').strip()

    # Directory rows only matter when they carry something beyond a bare phone:
    # a name, a business flag, address-book membership, or a lid mapping.
    now = timezone.now()
    created = updated = 0
    existing = {c.phone: c for c in WhatsAppContact.objects.filter(session=session)}
    to_create, to_update = [], []
    for phone, rec in merged.items():
        lid = phone_to_lid.get(phone, '')
        if not (rec['saved_name'] or rec['push_name'] or rec['is_business']
                or rec['is_my_contact'] or lid):
            continue
        obj = existing.get(phone)
        if obj is None:
            to_create.append(WhatsAppContact(
                session=session, phone=phone, lid=lid, saved_name=rec['saved_name'],
                push_name=rec['push_name'], is_business=rec['is_business'],
                is_my_contact=rec['is_my_contact'], synced_at=now,
            ))
            continue
        dirty = False
        for field, value in (
            ('lid', lid or obj.lid),
            ('saved_name', rec['saved_name'] or obj.saved_name),
            ('push_name', rec['push_name'] or obj.push_name),
            ('is_business', rec['is_business'] or obj.is_business),
            ('is_my_contact', rec['is_my_contact'] or obj.is_my_contact),
        ):
            if getattr(obj, field) != value:
                setattr(obj, field, value)
                dirty = True
        if dirty:
            obj.synced_at = now
            to_update.append(obj)

    if to_create:
        WhatsAppContact.objects.bulk_create(to_create, batch_size=500)
        created = len(to_create)
    if to_update:
        WhatsAppContact.objects.bulk_update(
            to_update,
            ['lid', 'saved_name', 'push_name', 'is_business', 'is_my_contact', 'synced_at'],
            batch_size=500,
        )
        updated = len(to_update)

    return {'seen': len(merged), 'created': created, 'updated': updated}
