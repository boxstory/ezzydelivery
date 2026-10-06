# Purpose: WhatsApp chat labels — every WAHA labels call, the WhatsAppContact mirror, and the push of a label change onto our other numbers.
# Used by: whatsapp/wa_chats_view.py (inbox panel + "Save to WhatsApp"), sync_wa_chat_labels cron.
# Notes: WhatsApp stays the source of truth; the contact row is a queryable mirror. Label ids are per number,
#        so a label crosses numbers by NAME (case- and plural-insensitive) and is created there when missing.

import logging

import time

import requests
from django.conf import settings
from django.core.cache import cache
from django.db.models import Q
from django.utils import timezone

logger = logging.getLogger(__name__)

# WhatsApp's own label palette, in WAHA's order (structures/labels.dto.js):
# creating a label takes either this index as `color` or the hex as `colorHex`,
# never both, and an off-palette hex is rejected with a 422.
PALETTE = [
    '#ff9485', '#64c4ff', '#ffd429', '#dfaef0', '#99b6c1',
    '#55ccb3', '#ff9dff', '#d3a91d', '#6d7cce', '#d7e752',
    '#00d0e2', '#ffc5c7', '#93ceac', '#f74848', '#00a0f2',
    '#83e422', '#ffaf04', '#b5ebff', '#9ba6ff', '#9368cf',
]
FALLBACK_COLOR = 4  # '#99b6c1', a neutral grey, for a label with no usable colour

# WhatsApp's built-in chat-list filters, which WAHA reports alongside real
# labels. They are each person's own view of their inbox, not a tag on the
# contact, so the backfill never copies them to another number.
LIST_FILTERS = {'unread', 'favorite', 'favourite', 'group'}

# A chat object exists for anyone WhatsApp has ever exchanged a key with, so
# these system rows are not evidence of a conversation — see has_real_chat().
NOTIFICATION_TYPES = {
    'e2e_notification', 'notification', 'notification_template', 'protocol',
    'ciphertext', 'gp2', 'call_log', 'revoked', 'unknown',
}


def _base():
    return (getattr(settings, 'WAHA_BASE_URL', 'http://127.0.0.1:3000') or '').rstrip('/')


def call(method, path, payload=None, timeout=15):
    """(status, json-or-None) for a WAHA call; status 0 on a network error."""
    try:
        resp = requests.request(
            method, f'{_base()}{path}', json=payload,
            headers={'X-Api-Key': getattr(settings, 'WAHA_API_KEY', '') or ''}, timeout=timeout)
    except requests.exceptions.RequestException:
        return 0, None
    try:
        return resp.status_code, resp.json()
    except ValueError:
        return resp.status_code, None


# ---------------------------------------------------------------- WAHA reads


def session_labels(session):
    """Every label defined on this number, or None when WAHA cannot say."""
    status, body = call('GET', f'/api/{session}/labels')
    return body if status == 200 and isinstance(body, list) else None


def chat_labels(session, chat_id):
    """The labels on one chat, or None when WAHA cannot say."""
    status, body = call('GET', f'/api/{session}/labels/chats/{chat_id}/')
    return body if status == 200 and isinstance(body, list) else None


def canonical_chat_id(session, chat_id):
    """The chat id a label write must use — the lid form when there is one.

    WhatsApp stores labels against the chat's own id, which for a modern chat is
    a lid. A PUT addressed to '<phone>@c.us' is accepted with a 200 and then
    silently applies nothing, so every write resolves the id first. Reads work
    either way. Groups and ids we cannot resolve are passed through unchanged.
    """
    ident = str(chat_id or '').strip()
    if not ident.endswith('@c.us'):
        return ident
    phone = ident.split('@', 1)[0]
    if not phone.isdigit():
        return ident
    key = f'wa_lid_for_pn:{session}:{phone}'
    hit = cache.get(key)
    if hit is not None:
        return hit or ident
    status, body = call('GET', f'/api/{session}/lids/pn/{phone}')
    lid = ''
    if status == 200 and isinstance(body, dict) and body.get('lid'):
        lid = str(body['lid'])
        lid = lid if lid.endswith('@lid') else f'{lid}@lid'
    cache.set(key, lid, 7 * 24 * 60 * 60)  # a contact's lid does not change
    return lid or ident


def put_chat_labels(session, chat_id, ids):
    """Replace a chat's whole label set — WhatsApp has no add/remove call."""
    status, _ = call('PUT', f'/api/{session}/labels/chats/{canonical_chat_id(session, chat_id)}/',
                     {'labels': [{'id': str(i)} for i in ids]})
    return status


def confirm_chat_labels(session, chat_id, ids, retry_after=1.2):
    """True once WhatsApp reports the set we just wrote.

    WA Web applies the change asynchronously, so the first read can still show
    the old set. One retry covers that; a lasting mismatch means the write did
    not take, and the panel says so instead of claiming it saved.
    """
    wanted = {str(i) for i in ids}
    for attempt in (0, 1):
        rows = chat_labels(session, chat_id)
        if rows is not None and {str(l.get('id')) for l in rows if isinstance(l, dict)} == wanted:
            return True
        if attempt == 0 and retry_after:
            time.sleep(retry_after)
    return False


# WhatsApp's own ceiling per number; WAHA answers 422 past it.
MAX_LABELS = 20


def create_label_detail(session, name, color=None, color_hex=''):
    """(label, error) for a create — the error is WhatsApp's own words.

    WAHA takes `color` (palette index) or `colorHex`, never both. We prefer the
    index because the source label already carries one; an off-palette hex is a
    422, so it is mapped back to an index rather than sent through.
    """
    if color is None:
        color = PALETTE.index(color_hex) if color_hex in PALETTE else FALLBACK_COLOR
    status, body = call('POST', f'/api/{session}/labels', {'name': name[:100], 'color': int(color)})
    if not 200 <= status < 300 or not isinstance(body, dict) or not body.get('id'):
        logger.warning('wa labels: could not create %r on %s (HTTP %s): %s', name, session, status, body)
        said = body.get('message') if isinstance(body, dict) else ''
        return None, str(said or f'WhatsApp refused it (HTTP {status or "network"}).')
    logger.info('wa labels: created %r on %s as id %s', name, session, body.get('id'))
    return body, ''


def create_label(session, name, color=None, color_hex=''):
    """The label, or None when WhatsApp refused it."""
    return create_label_detail(session, name, color=color, color_hex=color_hex)[0]


# ------------------------------------------------------- names across numbers


def norm(name):
    """Key for matching a label across numbers: 'Drivers' and 'Driver' are one.

    Our numbers were labelled by different people, so the same meaning is spelt
    'Driver' on one and 'Drivers' on another, 'Client' vs 'Clients'. Matching on
    the exact string would quietly create a duplicate label on the other phone.
    """
    key = ' '.join(str(name or '').split()).casefold()
    if len(key) > 3 and key.endswith('s') and not key.endswith('ss'):
        key = key[:-1]
    return key


def find_label(labels, name):
    """The label on that number meaning `name`, exact match first."""
    wanted = norm(name)
    rows = [l for l in (labels or []) if isinstance(l, dict)]
    for row in rows:
        if str(row.get('name') or '') == str(name or ''):
            return row
    for row in rows:
        if norm(row.get('name')) == wanted:
            return row
    return None


# ------------------------------------------------------- the contact mirror


def chat_phone(session, chat_id):
    """The contact's phone digits for a chat id, or '' when there is no phone.

    A '…@c.us' chat carries the number. A '…@lid' chat does not — a lid is
    device-relative and expanding one invents a live 974 number, so it is only
    resolved through the directory. Group chats have no contact at all.
    """
    from crm.services import is_lid_value

    from .models import WhatsAppContact

    ident = str(chat_id or '').strip()
    if not ident or ident.endswith('@g.us'):
        return ''
    bare = ident.split('@', 1)[0].strip()
    if not bare.isdigit():
        return ''
    if ident.endswith('@c.us') and not is_lid_value(bare):
        return bare
    return (WhatsAppContact.objects.filter(session=session, lid=bare)
            .values_list('phone', flat=True).first() or '')


def store(session, chat_id, labels, phone=None):
    """Mirror a chat's labels onto its WhatsAppContact row. True when stored.

    The contact row is the base data: it is what the CRM and any "who carries
    label X" query read, instead of asking WAHA chat by chat. A chat we cannot
    tie to a phone (a group, or a lid we have never synced) keeps its labels in
    WhatsApp only — we never mint a phone number to have somewhere to write.
    """
    from .models import WhatsAppContact

    phone = phone or chat_phone(session, chat_id)
    if not phone:
        return False
    rows = [{'id': str(l.get('id')), 'name': l.get('name') or '', 'colorHex': l.get('colorHex') or ''}
            for l in (labels or []) if isinstance(l, dict) and l.get('id') is not None]
    rows.sort(key=lambda r: (r['name'].casefold(), r['id']))
    contact, created = WhatsAppContact.objects.get_or_create(
        session=session, phone=phone, defaults={'labels': rows, 'labels_synced_at': timezone.now()})
    if created:
        return True
    if contact.labels != rows:
        contact.labels = rows
        contact.labels_synced_at = timezone.now()
        contact.save(update_fields=['labels', 'labels_synced_at', 'updated_at'])
    else:
        WhatsAppContact.objects.filter(pk=contact.pk).update(labels_synced_at=timezone.now())
    return True


def mirrored_map(session):
    """{label id: [chat id, …]} from the contact mirror — the fallback for the list.

    A chat is addressed by its lid or by its phone depending on how WhatsApp
    listed it, so each contact contributes both of its ids and the browser
    matches whichever one it holds.
    """
    from .models import WhatsAppContact

    out = {}
    rows = (WhatsAppContact.objects.filter(session=session).exclude(labels=[])
            .values_list('phone', 'lid', 'labels'))
    for phone, lid, labels in rows:
        ids = [f'{phone}@c.us'] + ([f'{lid}@lid'] if lid else [])
        for row in labels or []:
            if isinstance(row, dict) and row.get('id'):
                out.setdefault(str(row['id']), []).extend(ids)
    return out


def contact_labels(session, phone):
    """The mirrored labels for a contact on this number (DB only, no WAHA call)."""
    from .models import WhatsAppContact

    rows = (WhatsAppContact.objects.filter(session=session, phone=phone)
            .values_list('labels', flat=True).first())
    return rows if isinstance(rows, list) else []


# ----------------------------------------------------- push to our other numbers


def has_real_chat(session, phone):
    """True when this number has actually conversed with that contact.

    WhatsApp hands every number a chat object the moment it exchanges keys with
    a contact, so "a chat exists" is not evidence. Our own message rows are
    checked first (free); otherwise one WAHA page is read and system rows are
    ignored.
    """
    from .models import WhatsAppMessage

    if WhatsAppMessage.objects.filter(session=session).filter(
            Q(from_number=phone) | Q(to_number=phone)).exists():
        return True
    status, body = call('GET', f'/api/{session}/chats/{phone}@c.us/messages'
                               '?limit=20&downloadMedia=false', None, timeout=25)
    if status != 200 or not isinstance(body, list):
        return False
    for msg in body:
        if not isinstance(msg, dict):
            continue
        kind = str(((msg.get('_data') or {}) if isinstance(msg.get('_data'), dict) else {}).get('type') or '')
        if kind in NOTIFICATION_TYPES:
            continue
        if msg.get('fromMe') or msg.get('body') or msg.get('hasMedia'):
            return True
    return False


def other_sessions(session, phone):
    """Our other WhatsApp numbers that have this contact in their directory."""
    from . import sessions as wa_sessions
    from .models import WhatsAppContact

    live = [str(s.get('name') or '') for s in wa_sessions.list_sessions()
            if isinstance(s, dict) and str(s.get('status') or '') in ('WORKING', 'UNKNOWN')]
    known = set(WhatsAppContact.objects.filter(phone=phone).values_list('session', flat=True))
    # A number cannot label its own chat — WhatsApp answers 500 — and that chat
    # is the "message yourself" thread, not this contact's.
    return [s for s in live
            if s and s != session and s in known and wa_sessions.sender_number(s) != phone]


def propagate(session, chat_id, add_names, remove_names, actor=None, only=None):
    """Apply the same label change to our other numbers. Returns a per-number report.

    Best effort by design: the save on the open number has already succeeded, so
    a refusal here is reported to the user, never raised. A name missing on the
    other number is created there, and labels set on that phone by hand are kept
    because the whole set is merged, not replaced. `only` limits the push to
    those numbers (the backfill command); the inbox pushes to every number.
    """
    add_names = [n for n in (add_names or []) if str(n).strip()]
    remove_names = [n for n in (remove_names or []) if str(n).strip()]
    if not (add_names or remove_names):
        return []
    phone = chat_phone(session, chat_id)
    if not phone:
        return []

    source = session_labels(session) or []
    report = []
    for target in other_sessions(session, phone):
        if only is not None and target not in only:
            continue
        entry = {'session': target, 'added': [], 'removed': [], 'created': [], 'error': ''}
        if not has_real_chat(target, phone):
            entry['error'] = 'no chat on this number'
            report.append(entry)
            continue
        known = session_labels(target)
        if known is None:
            entry['error'] = 'could not read its labels'
            report.append(entry)
            continue
        target_chat = canonical_chat_id(target, f'{phone}@c.us')
        current = chat_labels(target, target_chat)
        if current is None:
            entry['error'] = 'could not read the chat'
            report.append(entry)
            continue
        ids = [str(l.get('id')) for l in current if isinstance(l, dict)]

        drop = set()
        for name in remove_names:
            row = find_label(known, name)
            if row is not None and str(row.get('id')) in ids:
                drop.add(str(row.get('id')))
                entry['removed'].append(row.get('name') or name)
        for name in add_names:
            row = find_label(known, name)
            if row is None:
                row = create_label(target, name, color=_color_of(source, name))
                if row is None:
                    entry['error'] = f'could not create {name}'
                    continue
                entry['created'].append(row.get('name') or name)
            if str(row.get('id')) not in ids:
                ids.append(str(row.get('id')))
                entry['added'].append(row.get('name') or name)
        ids = [i for i in ids if i not in drop]

        if not (entry['added'] or entry['removed']):
            report.append(entry)
            continue
        status = put_chat_labels(target, target_chat, ids)
        if not 200 <= status < 300:
            entry['error'] = f'WhatsApp refused the change (HTTP {status or "network"})'
            entry['added'], entry['removed'] = [], []
            report.append(entry)
            continue
        store(target, target_chat, [l for l in known if str(l.get('id')) in set(ids)], phone=phone)
        logger.info('wa labels: %s synced %s to %s for %s (+%s -%s)',
                    actor or 'system', session, target, phone, entry['added'], entry['removed'])
        report.append(entry)
    return report


def _color_of(source, name):
    """The palette index this label uses on the number it is being copied from."""
    row = find_label(source, name)
    if not isinstance(row, dict):
        return None
    color = row.get('color')
    if isinstance(color, int) and 0 <= color < len(PALETTE):
        return color
    hex_value = str(row.get('colorHex') or '')
    return PALETTE.index(hex_value) if hex_value in PALETTE else None
