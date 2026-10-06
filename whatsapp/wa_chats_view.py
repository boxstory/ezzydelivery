"""
Agent inbox UI — a WhatsApp-Web-style two-pane chat browser backed by WAHA + the
WhatsAppMessage table. nginx puts an htpasswd in front, and every endpoint here
also needs a staff login: chats under a marketing-only label (label_access.py)
are hidden from staff outside marketing, so the browser never reads chats from
WAHA directly — the list, labels and read receipts all come through here.
"""
import hashlib
import json
import logging
import re
from datetime import datetime, time, timedelta, timezone as dt_tz
from functools import wraps

import requests

from django.conf import settings
from django.contrib.auth.views import redirect_to_login
from django.db.models import Q
from django.http import HttpResponse, JsonResponse
from django.middleware.csrf import get_token
from django.shortcuts import redirect
from django.utils.html import escape
from django.views.decorators.http import require_http_methods

from . import chat_labels as chat_labels_svc
from . import label_access
from . import session_access
from . import sessions as wa_sessions
from .models import WhatsAppMessage
from core.validators import safe_int


logger = logging.getLogger(__name__)


# Asia/Qatar +3, no DST — explicit per spec; not Django's TIME_ZONE on purpose.
QATAR_OFFSET = dt_tz(timedelta(hours=3))


_WAHA_TYPE_MAP = {
    'chat': 'text',
    'image': 'image',
    'ptt': 'audio',
    'audio': 'audio',
    'video': 'video',
    'document': 'document',
    'location': 'location',
    'sticker': 'sticker',
    'vcard': 'contact',
    'multi_vcard': 'contact',
    'contact_card': 'contact',
}

_SENDER_PALETTE = [
    "#06cf9c", "#7f66ff", "#e542a3", "#3fa9f5",
    "#f5871f", "#15c2c4", "#b85cff", "#f04a4a",
]


def _strip_jid(jid):
    if not jid:
        return ''
    return str(jid).split('@', 1)[0]


def _msg_type(payload):
    if not isinstance(payload, dict):
        return 'unknown'
    raw = None
    data = payload.get('_data') or {}
    if isinstance(data, dict):
        raw = data.get('type')
    if not raw:
        raw = payload.get('type')
    if not raw:
        return 'text'
    return _WAHA_TYPE_MAP.get(str(raw).lower(), 'unknown')


def _raw_type(payload):
    if not isinstance(payload, dict):
        return ''
    data = payload.get('_data') if isinstance(payload.get('_data'), dict) else {}
    return str(data.get('type') or payload.get('type') or '').lower()


# Messages with no body that still happened — an empty bubble reads as broken.
_NOTICE_TEXT = {
    'revoked': 'This message was deleted',
    'call_log': 'Call',
}


def _parse_vcard(text):
    """One vCard → {'name', 'phone'}. The PHOTO line is a multi-KB base64 blob
    and is never returned."""
    name, phone = '', ''
    for line in str(text or '').splitlines():
        key, _, value = line.partition(':')
        head = key.split(';', 1)[0].strip().upper()
        if head == 'FN' and not name:
            name = value.strip()
        elif head == 'TEL' and not phone:
            waid = re.search(r'waid=(\d+)', key)
            phone = ('+' + waid.group(1)) if waid else value.strip()
    return {'name': name, 'phone': phone}


def _vcard_contacts(payload, body):
    """Contact-card message → list of {'name', 'phone'} (multi_vcard has many)."""
    data = payload.get('_data') if isinstance(payload, dict) and isinstance(payload.get('_data'), dict) else {}
    cards = []
    for item in data.get('vcardList') or []:
        if isinstance(item, dict):
            c = _parse_vcard(item.get('vcard'))
            c['name'] = c['name'] or str(item.get('displayName') or '')
            cards.append(c)
    if not cards and body:
        cards.append(_parse_vcard(body))
    if cards and not cards[0]['name']:
        cards[0]['name'] = str(data.get('vcardFormattedName') or '')
    return [c for c in cards if c['name'] or c['phone']]


def _decorate_special(d, payload):
    """Contact cards and body-less events: replace the raw text the bubble
    would otherwise print verbatim."""
    if d['type'] == 'contact':
        d['contacts'] = _vcard_contacts(payload, d['body'])
        d['body'] = ''
    elif d['type'] == 'unknown' and not d['body']:
        d['notice'] = _NOTICE_TEXT.get(_raw_type(payload), '')
    data = payload.get('_data') if isinstance(payload, dict) and isinstance(payload.get('_data'), dict) else {}
    d['edited'] = bool(data.get('latestEditSenderTimestampMs') or data.get('latestEditMsgKey'))
    return d


def _is_staff(user):
    if not getattr(user, 'is_authenticated', False):
        return False
    if user.is_staff:
        return True
    profile = getattr(user, 'profile', None)
    return bool(profile and profile.is_staff)


def _requested_session(request):
    """The number a request acts on, read the way the views read it: ?session=,
    else the POST form or JSON body, else the default number."""
    raw = request.GET.get('session')
    if raw is None and request.method == 'POST':
        if request.content_type in ('multipart/form-data', 'application/x-www-form-urlencoded'):
            raw = request.POST.get('session')
        else:
            try:
                body = json.loads(request.body.decode('utf-8') or '{}')
            except (ValueError, UnicodeDecodeError):
                body = None
            if isinstance(body, dict):
                raw = body.get('session')
    return wa_sessions.normalize(raw)


def _session_from_row(view):
    """Mark a view whose number comes from a stored row, not the request — it
    runs session_access itself (media/<id>/ carries no ?session=)."""
    view._session_from_row = True
    return view


def _staff_only(view):
    """Staff login on top of the nginx htpasswd: without knowing who is looking,
    marketing-only chats could not be kept from anyone. Also the number gate —
    a staff member opens only the WhatsApp numbers ticked for them on Staff Roles
    (whatsapp/session_access.py)."""
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        wants_page = 'text/html' in request.headers.get('Accept', '')
        if _is_staff(request.user):
            if getattr(view, '_session_from_row', False):
                return view(request, *args, **kwargs)
            session = _requested_session(request)
            if session_access.can_open(request.user, session):
                return view(request, *args, **kwargs)
            if wants_page and request.method == 'GET':
                landing = session_access.first_open(request.user)
                if landing:
                    return redirect(f'{request.path}?session={landing}')
                return HttpResponse('No WhatsApp number is open to you yet. Ask a super admin to '
                                    'tick one for you on Staff Roles.', status=403)
            return JsonResponse({"ok": False, "error": session_access.REFUSAL}, status=403)
        if not request.user.is_authenticated:
            if wants_page:
                return redirect_to_login(request.get_full_path())
            return JsonResponse({"ok": False, "error": "Sign in to the staff portal."}, status=401)
        if wants_page:
            return HttpResponse('Staff only.', status=403)
        return JsonResponse({"ok": False, "error": "Staff only."}, status=403)
    return wrapper


def _refuse_hidden():
    return _no_store({"ok": False, "error": label_access.REFUSAL}, status=403)


def _waha_base():
    return (getattr(settings, 'WAHA_BASE_URL', 'http://127.0.0.1:3000') or '').rstrip('/')


# WAHA builds file URLs from its own container hostname, not from the address we
# reach it on, so the host it hands back ('localhost:3000') is one the browser
# cannot resolve and CSP blocks. Any /api/files/ URL is ours whatever the host.
_WAHA_FILE_URL_RE = re.compile(r'^https?://[^/]+(/api/files/.*)$', re.IGNORECASE)


def _rewrite_waha_url(url):
    if not url:
        return url
    s = str(url)
    base = _waha_base()
    # Idempotent: already same-origin under /waha.
    if s.startswith('/waha/'):
        return s
    for prefix in (base, 'http://127.0.0.1:3000', 'http://localhost:3000'):
        if prefix and s.startswith(prefix):
            tail = s[len(prefix):]
            if not tail.startswith('/'):
                tail = '/' + tail
            return '/waha' + tail
    match = _WAHA_FILE_URL_RE.match(s)
    if match:
        return '/waha' + match.group(1)
    return s


def _extract_media_from_payload(payload):
    if not isinstance(payload, dict):
        return None
    media = payload.get('media')
    if isinstance(media, dict):
        url = media.get('url') or ''
        mime = media.get('mimetype') or media.get('mime') or ''
        if url or mime:
            return {'url': _rewrite_waha_url(url), 'mime': mime}
    inner = payload.get('payload')
    if isinstance(inner, dict):
        m2 = inner.get('media')
        if isinstance(m2, dict):
            url = m2.get('url') or ''
            mime = m2.get('mimetype') or m2.get('mime') or ''
            if url or mime:
                return {'url': _rewrite_waha_url(url), 'mime': mime}
    return None


def _extract_media(row_or_payload):
    if isinstance(row_or_payload, WhatsAppMessage):
        row = row_or_payload
        url = row.media_url or ''
        mime = row.media_mime or ''
        if not url:
            payload = row.raw_payload if isinstance(row.raw_payload, dict) else {}
            inner = payload.get('payload') if isinstance(payload, dict) else None
            if isinstance(inner, dict):
                m = inner.get('media')
                if isinstance(m, dict):
                    url = m.get('url') or url
                    mime = mime or m.get('mimetype') or m.get('mime') or ''
            if not url:
                m = payload.get('media') if isinstance(payload, dict) else None
                if isinstance(m, dict):
                    url = m.get('url') or url
                    mime = mime or m.get('mimetype') or m.get('mime') or ''
        if not url and not mime:
            return None
        return {'url': _rewrite_waha_url(url), 'mime': mime}
    return _extract_media_from_payload(row_or_payload)


def _group_sender(payload):
    if not isinstance(payload, dict):
        return None
    data = payload.get('_data') if isinstance(payload.get('_data'), dict) else {}
    author = payload.get('author') or payload.get('participant') or data.get('author')
    if not author:
        return None
    sid = _strip_jid(author)
    name = (
        payload.get('notifyName')
        or data.get('notifyName')
        or payload.get('senderName')
        or ''
    ).strip()
    if name == sid:
        name = ''  # a bare id is not a name — let the UI fall back to '+id' once
    # Group authors arrive as anonymized @lid JIDs, not phone numbers —
    # _resolve_lid_senders() swaps these for the real number via WAHA's lids API.
    return {'id': sid, 'name': name or None, 'is_lid': str(author).endswith('@lid')}


def _sender_color(sender_id):
    if not sender_id:
        return _SENDER_PALETTE[0]
    h = hashlib.md5(str(sender_id).encode('utf-8')).digest()
    return _SENDER_PALETTE[h[0] % len(_SENDER_PALETTE)]


# Keyed per session: a lid identifies a contact relative to the linked device,
# so each of our numbers hands out a different lid for the same person. A
# session-less key would let the two sessions' maps overwrite each other.
_LID_CACHE_TTL = 6 * 3600


def _lid_cache_key(session):
    return f'waha_lid_map_v2:{session}'


def _lid_map(base, session, api_key):
    """lid digits -> phone digits, from WAHA's /lids API. Cached 6h per session."""
    from django.core.cache import cache
    mp = cache.get(_lid_cache_key(session))
    if isinstance(mp, dict):
        return mp
    mp = {}
    try:
        resp = requests.get(
            f"{base}/api/{session}/lids",
            params={'limit': 100000},
            headers={'X-Api-Key': api_key},
            timeout=15,
        )
        if 200 <= resp.status_code < 300:
            for row in resp.json():
                if isinstance(row, dict):
                    lid = _strip_jid(row.get('lid'))
                    pn = _strip_jid(row.get('pn'))
                    if lid and pn:
                        mp[lid] = pn
    except (requests.exceptions.RequestException, ValueError) as e:
        logger.warning("waha lids fetch failed (session=%s): %s", session, e)
        return mp  # don't cache a failed fetch
    cache.set(_lid_cache_key(session), mp, _LID_CACHE_TTL)
    return mp


def _resolve_lid_senders(msgs, base, session, api_key):
    """Swap anonymized @lid sender ids for real phone digits, in place."""
    from django.core.cache import cache
    lids = set()
    for m in msgs:
        s = m.get('sender')
        if s and s.pop('is_lid', False) and s.get('id'):
            s['_lid'] = s['id']
            lids.add(s['id'])
    if not lids:
        return
    mp = _lid_map(base, session, api_key)
    # New participants may not be in the cached bulk map yet — look up a few
    # individually and fold them into the cache.
    updated = False
    for lid in [l for l in lids if l not in mp][:5]:
        try:
            resp = requests.get(
                f"{base}/api/{session}/lids/{lid}",
                headers={'X-Api-Key': api_key},
                timeout=5,
            )
            if 200 <= resp.status_code < 300:
                pn = _strip_jid(resp.json().get('pn'))
                if pn:
                    mp[lid] = pn
                    updated = True
        except (requests.exceptions.RequestException, ValueError):
            pass
    if updated:
        cache.set(_lid_cache_key(session), mp, _LID_CACHE_TTL)
    for m in msgs:
        s = m.get('sender')
        if s and s.get('_lid'):
            pn = mp.get(s.pop('_lid'))
            if pn:
                s['id'] = pn


_QUOTE_PLACEHOLDER = {
    'image': 'Photo', 'video': 'Video', 'audio': 'Audio', 'ptt': 'Voice message',
    'document': 'Document', 'sticker': 'Sticker', 'location': 'Location',
    'vcard': 'Contact', 'multi_vcard': 'Contacts',
}


_FILE_TYPES = ('image', 'video', 'audio', 'document', 'sticker')


def _media_size(payload):
    """The attachment's size in bytes as WhatsApp reports it, or None."""
    data = payload.get('_data') if isinstance(payload, dict) else None
    size = data.get('size') if isinstance(data, dict) else None
    return size if isinstance(size, int) and size > 0 else None


def _filename_of(payload):
    """A document's file name, as WhatsApp shows it on the bubble."""
    if not isinstance(payload, dict):
        return ''
    data = payload.get('_data') if isinstance(payload.get('_data'), dict) else {}
    media = payload.get('media') if isinstance(payload.get('media'), dict) else {}
    return str(data.get('filename') or media.get('filename') or '')[:200]


def _quoted(payload):
    """The message this one replies to, as WAHA reports it (`replyTo`), or None.

    `id` is the short WhatsApp key; rows on screen carry it as the tail of their
    serialized id, which is how the browser finds the original to jump to.
    """
    if not isinstance(payload, dict):
        return None
    rt = payload.get('replyTo')
    if not isinstance(rt, dict) or not rt.get('id'):
        return None
    data = rt.get('_data') if isinstance(rt.get('_data'), dict) else {}
    body = rt.get('body') or data.get('body') or ''
    kind = (data.get('type') or '').lower()
    if kind in _QUOTE_PLACEHOLDER:
        # A media body can be the base64 thumbnail; show the caption, else the kind.
        body = data.get('caption') or _QUOTE_PLACEHOLDER[kind]
    return {'id': str(rt['id']), 'body': str(body)[:300]}


def _row_to_dict(row, chat_id):
    payload = row.raw_payload if isinstance(row.raw_payload, dict) else {}
    inner = payload.get('payload') if isinstance(payload, dict) else None
    type_source = inner if isinstance(inner, dict) else payload
    if _is_noise_message(type_source):
        return None
    mtype = _msg_type(type_source) or row.message_type or 'text'
    if mtype == 'unknown' and row.message_type:
        mtype = row.message_type
    media = _extract_media(row)
    # Deleted for everyone: the archived file stays on disk but is not shown.
    revoked = _raw_type(type_source) == 'revoked'
    if revoked:
        media = None
    is_group = str(chat_id).endswith('@g.us')
    # WAHA drops its own copy of a file within minutes, and our archive of it
    # lives in private storage that has no public URL — so hand the browser our
    # streamer, which reads the archive and falls back to WAHA for fresh media.
    # Group media is only downloaded on a click (`stored` false = show a download
    # button), so a group file gets the streamer even with no WAHA link stored.
    if not revoked and (media or row.media_file or (is_group and mtype in _FILE_TYPES)):
        media = {
            'url': '/waha/wa-chats/media/%d/' % row.pk,
            'mime': row.media_mime or (media or {}).get('mime', ''),
            'stored': bool(row.media_file),
            'size': _media_size(type_source),
        }
    sender = None
    if is_group:
        sender_payload = inner if isinstance(inner, dict) else payload
        sender = _group_sender(sender_payload)
        if sender and sender.get('id'):
            sender['color'] = _sender_color(sender['id'])

    # Surface lat/lng + linked AddressVerificationJob (if any) so the inbox UI
    # can render a Google Maps link and "Apply to order" CTA for manual_review
    # jobs created by the auto-import → verify-link flow.
    location = None
    if mtype == 'location' and row.latitude is not None and row.longitude is not None:
        location = {
            'latitude':  float(row.latitude),
            'longitude': float(row.longitude),
        }
    verification_job = None
    try:
        vjob = row.verification_jobs_received.select_related('order').order_by('-id').first()
        if vjob:
            verification_job = {
                'id': vjob.id,
                'status': vjob.status,
                'order_id': vjob.order_id,
                'order_number': vjob.order.order_number if vjob.order_id else None,
                'customer_name': vjob.order.customer_name if vjob.order_id else None,
            }
    except Exception:
        verification_job = None

    return _decorate_special({
        'id': row.pk,
        'waha_id': row.waha_message_id,
        'direction': row.direction,
        'from': row.from_number,
        'to': row.to_number,
        'body': row.body or '',
        'type': mtype,
        'media': media,
        'timestamp': int(row.received_at.timestamp()) if row.received_at else 0,
        'sender': sender,
        'location': location,
        'verification_job': verification_job,
        'quoted': _quoted(type_source),
        'filename': _filename_of(type_source),
        'ack': None,
    }, type_source)


_NOISE_RAW_TYPES = {
    'e2e_notification',     # encryption setup — invisible in WhatsApp Web too
    'notification',          # generic protocol notification
    'notification_template', # group/system templated notification
    'protocol',              # protocol-level placeholder
}


def _is_noise_message(payload):
    """True for protocol-only messages (encryption setup, etc.). Hidden from UI."""
    if not isinstance(payload, dict):
        return False
    data = payload.get('_data') if isinstance(payload.get('_data'), dict) else {}
    raw = (data.get('type') or payload.get('type') or '').lower()
    return raw in _NOISE_RAW_TYPES


def _live_media_url(session, chat_id, waha_id):
    """Inbox URL that streams a not-yet-stored message's attachment (and stores it)."""
    from urllib.parse import urlencode
    return '/waha/wa-chats/media-live/?' + urlencode({'session': session, 'chatId': chat_id, 'msgId': waha_id})


def _live_to_dict(msg, chat_id, session=None):
    if not isinstance(msg, dict):
        return None
    if _is_noise_message(msg):
        return None
    waha_id = msg.get('id') or ''
    mtype = _msg_type(msg)
    media = _extract_media_from_payload(msg)
    # Listed with downloadMedia=false, so a media message comes with no URL
    # (our own fresh sends especially: the webhook does not store fromMe).
    if msg.get('hasMedia') and waha_id and session and not (media or {}).get('url'):
        media = {'url': _live_media_url(session, chat_id, waha_id), 'mime': (media or {}).get('mime') or ''}
    if media:
        media['stored'] = False
        media['size'] = _media_size(msg)
    from_jid = msg.get('from') or ''
    to_jid = msg.get('to') or ''
    body = msg.get('body') or ''
    ts = int(msg.get('timestamp') or 0)
    direction = 'outbound' if msg.get('fromMe') is True else 'inbound'
    is_group = str(chat_id).endswith('@g.us')
    sender = None
    if is_group:
        sender = _group_sender(msg)
        if sender and sender.get('id'):
            sender['color'] = _sender_color(sender['id'])
    return _decorate_special({
        'id': None,
        'waha_id': str(waha_id),
        'direction': direction,
        'from': _strip_jid(from_jid),
        'to': _strip_jid(to_jid),
        'body': body,
        'type': mtype,
        'media': media,
        'timestamp': ts,
        'sender': sender,
        'quoted': _quoted(msg),
        'filename': _filename_of(msg),
        'ack': msg.get('ack'),
    }, msg)


def _apply_live_acks(dicts, live_msgs):
    """Give archived rows the tick WhatsApp reports now (sent/delivered/read).

    Our copy was stored when the message went out, so its ack is stale; the
    live copy of the same message id carries the current one.
    """
    acks = {str(m.get('id')): m.get('ack') for m in live_msgs
            if isinstance(m, dict) and m.get('id') and m.get('ack') is not None}
    for d in dicts:
        if d.get('ack') is None and d.get('waha_id') in acks:
            d['ack'] = acks[d['waha_id']]


def _attach_reactions(msgs, session):
    """Give each message its stored reactions (WAHA's list only says one exists)."""
    from .wa_chats_actions import reactions_for
    found = reactions_for(session, [m.get('waha_id') for m in msgs])
    for m in msgs:
        m['reactions'] = found.get(m.get('waha_id') or '', [])


def _messages_response(request, chat_id):
    """
    Two modes:
      - Initial open  (no before_ts): newest `limit` messages = DB recent + WAHA live, deduped.
      - Scroll-up    (before_ts=X):   newest `limit` messages older than X.
                                       DB by received_at < X; WAHA by offset, filtered by ts.
    Always returned ASCENDING by ts so the JS can append/prepend without re-sorting.
    """
    if not chat_id:
        return JsonResponse({"ok": False, "error": "chatId required"}, status=400)
    if label_access.chat_hidden(request.user, wa_sessions.from_request(request), chat_id):
        return _refuse_hidden()

    stripped_id = _strip_jid(chat_id)
    is_group = str(chat_id).endswith('@g.us')

    try:
        limit = safe_int(request.GET.get('limit'), default=50, minimum=1, maximum=500)
    except (TypeError, ValueError):
        limit = 50
    if limit < 1:
        limit = 1
    if limit > 200:
        limit = 200

    try:
        before_ts = safe_int(request.GET.get('before_ts'), default=0, minimum=0)
    except (TypeError, ValueError):
        before_ts = 0

    base = _waha_base()
    session = wa_sessions.from_request(request)
    api_key = getattr(settings, 'WAHA_API_KEY', '') or ''

    if before_ts > 0:
        # ---- Older-page mode ----
        cutoff_dt = datetime.fromtimestamp(before_ts, tz=dt_tz.utc)
        qs = (
            WhatsAppMessage.objects
            .filter(session=session)
            .filter(received_at__lt=cutoff_dt)
            .filter(Q(from_number=stripped_id) | Q(to_number=stripped_id))
            .order_by('-received_at')[:limit]
        )
        db_rows = list(qs)
        db_dicts = [d for d in (_row_to_dict(r, chat_id) for r in db_rows) if d is not None]
        seen_ids = {r.waha_message_id for r in db_rows if r.waha_message_id}

        # WAHA paginates by offset (newest first). We don't know exactly how
        # many newer-than-cutoff items WAHA holds, so pull a generous batch
        # and filter by ts — caller passes `older_offset` to skip already-shown.
        try:
            older_offset = safe_int(request.GET.get('older_offset'), default=0, minimum=0, maximum=100000)
        except (TypeError, ValueError):
            older_offset = 0
        if older_offset < 0:
            older_offset = 0

        live_msgs = []
        url = f"{base}/api/{session}/chats/{chat_id}/messages"
        try:
            resp = requests.get(
                url,
                params={'limit': limit, 'offset': older_offset, 'downloadMedia': 'false'},
                headers={'X-Api-Key': api_key},
                timeout=27,
            )
            if 200 <= resp.status_code < 300:
                try:
                    body = resp.json()
                    if isinstance(body, list):
                        live_msgs = body
                    elif isinstance(body, dict) and isinstance(body.get('messages'), list):
                        live_msgs = body['messages']
                except ValueError:
                    pass
        except (requests.exceptions.Timeout, requests.exceptions.RequestException) as e:
            logger.warning("waha older messages failed: %s", e)

        live_dicts = []
        for m in live_msgs:
            if not isinstance(m, dict):
                continue
            wid = str(m.get('id') or '')
            if wid and wid in seen_ids:
                continue
            ts = int(m.get('timestamp') or 0)
            if ts >= before_ts:
                continue  # already shown
            d = _live_to_dict(m, chat_id, session)
            if d is not None:
                live_dicts.append(d)
                if wid:
                    seen_ids.add(wid)

        _apply_live_acks(db_dicts, live_msgs)
        merged = db_dicts + live_dicts
        merged.sort(key=lambda x: x.get('timestamp') or 0)
        # Trim to caller's requested page size from the OLDER end (we want the
        # newest items just-before before_ts, so keep the tail).
        if len(merged) > limit:
            merged = merged[-limit:]
        if is_group:
            _resolve_lid_senders(merged, base, session, api_key)
        _attach_reactions(merged, session)
        has_more = len(db_rows) >= limit or len(live_msgs) > 0

        resp = JsonResponse(
            {"ok": True, "messages": merged, "is_group": is_group, "has_more": has_more},
            status=200,
        )
        resp['Cache-Control'] = 'no-store, no-cache, must-revalidate, private'
        return resp

    # ---- Initial-open mode ----
    qs = (
        WhatsAppMessage.objects
        .filter(session=session)
        .filter(Q(from_number=stripped_id) | Q(to_number=stripped_id))
        .order_by('-received_at')[:limit]
    )
    db_rows = list(qs)
    db_dicts = [d for d in (_row_to_dict(r, chat_id) for r in db_rows) if d is not None]
    seen_ids = {r.waha_message_id for r in db_rows if r.waha_message_id}

    # Match WAHA fetch size to user's request — WEBJS scales ~linearly with limit
    # and this endpoint must finish within gunicorn's 30s window.
    live_limit = limit
    live_msgs = []
    url = f"{base}/api/{session}/chats/{chat_id}/messages"
    try:
        resp = requests.get(
            url,
            params={'limit': live_limit, 'downloadMedia': 'false'},
            headers={'X-Api-Key': api_key},
            timeout=27,
        )
        if 200 <= resp.status_code < 300:
            try:
                body = resp.json()
                if isinstance(body, list):
                    live_msgs = body
                elif isinstance(body, dict) and isinstance(body.get('messages'), list):
                    live_msgs = body['messages']
            except ValueError:
                live_msgs = []
        else:
            logger.warning("waha live messages non-2xx: %s", resp.status_code)
    except (requests.exceptions.Timeout, requests.exceptions.RequestException) as e:
        logger.warning("waha live messages failed: %s", e)

    live_dicts = []
    for m in live_msgs:
        if not isinstance(m, dict):
            continue
        wid = str(m.get('id') or '')
        if wid and wid in seen_ids:
            continue
        d = _live_to_dict(m, chat_id, session)
        if d is not None:
            live_dicts.append(d)
            if wid:
                seen_ids.add(wid)

    _apply_live_acks(db_dicts, live_msgs)
    merged = db_dicts + live_dicts
    merged.sort(key=lambda x: x.get('timestamp') or 0)
    if len(merged) > limit:
        merged = merged[-limit:]
    if is_group:
        _resolve_lid_senders(merged, base, session, api_key)
    _attach_reactions(merged, session)
    has_more = len(db_rows) >= limit or len(live_msgs) >= live_limit

    resp = JsonResponse(
        {"ok": True, "messages": merged, "is_group": is_group, "has_more": has_more},
        status=200,
    )
    resp['Cache-Control'] = 'no-store, no-cache, must-revalidate, private'
    return resp


def _chat_latest_response(request):
    """Latest received_at per phone-number digits, both directions.

    Used by the chat-list UI to bump WAHA's `chat.timestamp` when our DB has
    seen a more recent message via webhook. Returns {digits: epoch_ts}.
    """
    from django.db.models import Max
    latest = {}
    # Scoped to the session whose chat list is on screen — otherwise a customer
    # who also messaged our other number would bump this thread's timestamp.
    scoped = WhatsAppMessage.objects.filter(session=wa_sessions.from_request(request))

    rows = scoped.values('from_number').annotate(ts=Max('received_at'))
    for r in rows:
        n = r.get('from_number') or ''
        ts = r.get('ts')
        if not n or not ts:
            continue
        latest[n] = max(latest.get(n, 0), int(ts.timestamp()))

    rows = scoped.values('to_number').annotate(ts=Max('received_at'))
    for r in rows:
        n = r.get('to_number') or ''
        ts = r.get('ts')
        if not n or not ts:
            continue
        latest[n] = max(latest.get(n, 0), int(ts.timestamp()))

    try:
        hidden = label_access.hidden_identifiers(request.user, wa_sessions.from_request(request))
    except label_access.MembershipUnknown:
        return _no_store({"ok": False, "error": "Cannot check marketing-only labels right now."}, status=503)
    latest = {n: ts for n, ts in latest.items() if n not in hidden}

    resp = JsonResponse({"ok": True, "latest": latest}, status=200)
    resp['Cache-Control'] = 'no-store, no-cache, must-revalidate, private'
    return resp


@_staff_only
@require_http_methods(["GET", "POST"])
def wa_chats(request):
    if request.method == 'POST':
        return wa_chats_send(request)

    if request.GET.get('chats') == '1':
        return _chat_list_response(request)

    if request.GET.get('labels') == '1':
        return _labels_response(request)

    if request.GET.get('chat_labels') == '1':
        return _chat_labels_response(request)

    if request.GET.get('messages') == '1':
        chat_id = (request.GET.get('chatId') or '').strip()
        return _messages_response(request, chat_id)

    if request.GET.get('chat_latest') == '1':
        return _chat_latest_response(request)

    if request.GET.get('info') == '1':
        return _chat_info_response(request)

    if request.GET.get('names') == '1':
        from . import chat_panel
        ids = [i.strip() for i in (request.GET.get('ids') or '').split(',') if i.strip()]
        session = wa_sessions.from_request(request)
        ids = [i for i in ids if not label_access.chat_hidden(request.user, session, i)]
        # A connected CRM lead names the chat like a saved contact — but lead
        # data is only for a staff login with CRM access, like the panel.
        leads = chat_panel.lead_names(session, ids) if chat_panel.can_see_leads(request.user) else {}
        return _no_store({"ok": True, "names": chat_panel.push_names(session, ids), "leads": leads})

    if request.GET.get('who') == '1':
        from . import chat_panel
        chat_id = (request.GET.get('chatId') or '').strip()
        if not chat_id:
            return _no_store({"ok": False, "error": "chatId required"}, status=400)
        session = wa_sessions.from_request(request)
        if label_access.chat_hidden(request.user, session, chat_id):
            return _refuse_hidden()
        lead_name = ''
        if chat_panel.can_see_leads(request.user):
            lead_name = chat_panel.lead_names(session, [chat_id]).get(chat_id, '')
        return _no_store({"ok": True, **chat_panel.chat_identity(session, chat_id), "lead_name": lead_name})

    if request.GET.get('media') == '1':
        return _chat_media_response(request)

    if request.GET.get('lead_search') == '1':
        return _lead_search_response(request)

    if request.GET.get('find') == '1':
        return _find_response(request)

    return _render_page(request)


def _waha_json(path, params=None, timeout=15):
    """(status, json-or-None) for a WAHA GET; status 0 on a network error."""
    api_key = getattr(settings, 'WAHA_API_KEY', '') or ''
    try:
        resp = requests.get(f"{_waha_base()}{path}", params=params,
                            headers={'X-Api-Key': api_key}, timeout=timeout)
    except requests.exceptions.RequestException:
        return 0, None
    try:
        return resp.status_code, resp.json()
    except ValueError:
        return resp.status_code, None


def _chat_id_of(chat):
    cid = chat.get('id') if isinstance(chat, dict) else None
    return str(cid.get('_serialized') if isinstance(cid, dict) else cid or '')


def _chat_list_response(request):
    """One page of the chat list, minus chats this user may not see.

    `fetched` is WAHA's own page size, so the browser can page on by offset even
    when hidden chats make the returned list shorter.
    """
    session = wa_sessions.from_request(request)
    limit = safe_int(request.GET.get('limit'), default=50, minimum=1, maximum=200)
    offset = safe_int(request.GET.get('offset'), default=0, minimum=0, maximum=100000)
    status, body = _waha_json(f"/api/{session}/chats", {'limit': limit, 'offset': offset}, timeout=20)
    if status != 200 or not isinstance(body, list):
        return _no_store({"ok": False, "chats": [], "fetched": 0, "error": f"WAHA {status or 'unreachable'}"}, status=502)
    try:
        hidden = label_access.hidden_identifiers(request.user, session)
    except label_access.MembershipUnknown:
        return _no_store({"ok": False, "chats": [], "fetched": 0,
                          "error": "Cannot check marketing-only labels right now — try again shortly."}, status=503)
    chats = [c for c in body if isinstance(c, dict) and _strip_jid(_chat_id_of(c)) not in hidden]
    return _no_store({"ok": True, "chats": chats, "fetched": len(body)})


def _find_response(request):
    """Contacts matching the search box — any part of the phone, or the name.

    The browser only holds the chat pages loaded so far, and most 1:1 chats
    are @lid ids with no phone in them; the contact directory maps both.
    """
    from .models import WhatsAppContact
    session = wa_sessions.from_request(request)
    q = (request.GET.get('q') or '').strip()[:64]
    digits = re.sub(r'\D', '', q)
    rows = WhatsAppContact.objects.filter(session=session)
    if re.fullmatch(r'[\d\s+()-]+', q) and len(digits) >= 4:
        rows = rows.filter(phone__contains=digits)
    elif len(q) >= 2:
        rows = rows.filter(Q(saved_name__icontains=q) | Q(push_name__icontains=q))
    else:
        return _no_store({"ok": True, "hits": []})
    try:
        hidden = label_access.hidden_identifiers(request.user, session)
    except label_access.MembershipUnknown:
        return _no_store({"ok": False, "hits": []}, status=503)
    hits = []
    for phone, lid, saved, push in rows.order_by('-updated_at').values_list(
            'phone', 'lid', 'saved_name', 'push_name')[:60]:
        if phone in hidden or (lid and lid in hidden):
            continue
        hits.append({
            'chat_id': f'{lid}@lid' if lid else f'{phone}@c.us',
            'alt_id': f'{phone}@c.us' if lid and phone else '',
            'phone': phone,
            'name': (saved or push or '').strip()[:100],
        })
        if len(hits) >= 30:
            break
    return _no_store({"ok": True, "hits": hits, "messages": _find_messages(session, q, hidden)})


def _message_chat_id(row):
    """WAHA's chat id for a stored message: the other side of the conversation."""
    payload = row.raw_payload if isinstance(row.raw_payload, dict) else {}
    inner = payload.get('payload') if isinstance(payload.get('payload'), dict) else payload
    jid = inner.get('to' if row.direction == 'outbound' else 'from') or ''
    if '@' in str(jid):
        return str(jid)
    num = row.to_number if row.direction == 'outbound' else row.from_number
    return num if '@' in num else (f'{num}@c.us' if num else '')


def _find_messages(session, q, hidden, limit=30):
    """Newest stored messages whose text contains the query (3+ characters)."""
    if len(q) < 3:
        return []
    from .models import WhatsAppContact
    rows = (WhatsAppMessage.objects.filter(session=session, body__icontains=q)
            .exclude(message_type__in=('contact', 'system'))
            .only('waha_message_id', 'direction', 'from_number', 'to_number', 'body', 'received_at', 'raw_payload')
            .order_by('-received_at')[:limit * 3])
    out = []
    for row in rows:
        chat_id = _message_chat_id(row)
        if not chat_id or _strip_jid(chat_id) in hidden:
            continue
        body = row.body
        at = body.lower().find(q.lower())
        start = max(0, at - 30)
        snippet = ('…' if start else '') + body[start:start + 120].replace('\n', ' ')
        out.append({
            'chat_id': chat_id,
            'id': row.pk,
            'waha_id': row.waha_message_id,
            'snippet': snippet,
            'from_me': row.direction == 'outbound',
            'timestamp': int(row.received_at.timestamp()) if row.received_at else 0,
            'name': '',
        })
        if len(out) >= limit:
            break
    # Name each chat from the contact directory (lid or phone).
    keys = {_strip_jid(m['chat_id']) for m in out}
    names, lid_of = {}, {}
    for phone, lid, saved, push in WhatsAppContact.objects.filter(session=session).filter(
            Q(phone__in=keys) | Q(lid__in=keys)).values_list('phone', 'lid', 'saved_name', 'push_name'):
        if lid:
            lid_of.setdefault(phone, lid)
        nm = (saved or push or '').strip()[:100]
        if nm:
            names.setdefault(phone, nm)
            if lid:
                names.setdefault(lid, nm)
    for m in out:
        bare_id = _strip_jid(m['chat_id'])
        m['name'] = names.get(bare_id, '')
        # Older rows were stored against the phone; WAHA now knows the chat by
        # its lid, and opening the phone id would show a second, empty thread.
        if m['chat_id'].endswith('@c.us') and lid_of.get(bare_id):
            m['chat_id'] = lid_of[bare_id] + '@lid'
    return out


def _labels_response(request):
    """This number's labels and the chats under each, as the user may see them.

    Staff outside marketing get neither the marketing-only labels nor any chat
    carrying one. `complete` is false when a label's chats could not be read, so
    the browser does not keep a partial map for a day.
    """
    session = wa_sessions.from_request(request)
    status, labels = _waha_json(f"/api/{session}/labels")
    if status != 200 or not isinstance(labels, list):
        return _no_store({"ok": False, "labels": [], "map": {}, "complete": False}, status=502)
    see_all = label_access.can_see_all(request.user)
    restricted = set() if see_all else label_access.restricted_label_ids(session)
    try:
        hidden = label_access.hidden_identifiers(request.user, session)
    except label_access.MembershipUnknown:
        return _no_store({"ok": False, "labels": [], "map": {}, "complete": False}, status=503)
    out, chat_map, complete = [], {}, True
    mirrored = None
    for lb in labels:
        if not isinstance(lb, dict) or not lb.get('id') or str(lb['id']) in restricted:
            continue
        lid = str(lb['id'])
        out.append({'id': lid, 'name': lb.get('name') or '', 'color': lb.get('color') or '',
                    'colorHex': lb.get('colorHex') or ''})
        chats = label_access.label_chats(session, lid)
        if chats is None:
            # WAHA could not list this label's chats — fall back to the contact
            # mirror so the chips still show. Still `complete=False`, so the
            # browser does not keep this map for the day.
            complete = False
            if mirrored is None:
                mirrored = chat_labels_svc.mirrored_map(session)
            chats = mirrored.get(lid, [])
        chat_map[lid] = [c for c in chats if _strip_jid(c) not in hidden]
    return _no_store({"ok": True, "labels": out, "map": chat_map, "complete": complete})


def _chat_labels_response(request):
    """One chat's labels, read live (the browser's map can be a day old)."""
    session = wa_sessions.from_request(request)
    chat_id = (request.GET.get('chatId') or '').strip()
    if not _CHAT_ID_RE.match(chat_id):
        return _no_store({"ok": False, "error": "invalid chatId"}, status=400)
    if label_access.chat_hidden(request.user, session, chat_id):
        return _refuse_hidden()
    status, body = _waha_json(f"/api/{session}/labels/chats/{chat_id}/")
    if status != 200 or not isinstance(body, list):
        return _no_store({"ok": False, "error": "Could not read this chat's labels."}, status=502)
    # Opening a chat is also how the contact mirror stays current: this is the
    # one place that reads a chat's real label set on an ordinary page view.
    chat_labels_svc.store(session, chat_id, body)
    restricted = set() if label_access.can_see_all(request.user) else label_access.restricted_label_ids(session)
    return _no_store({"ok": True, "labels": [
        {"id": str(l.get('id')), "name": l.get('name') or '', "colorHex": l.get('colorHex') or ''}
        for l in body if isinstance(l, dict) and str(l.get('id')) not in restricted
    ]})


@_staff_only
@require_http_methods(["POST"])
def wa_chats_mark_read(request):
    """Mark a chat read in WhatsApp (blue ticks), as opening it on the phone does."""
    try:
        data = json.loads(request.body.decode('utf-8') or '{}')
    except (ValueError, UnicodeDecodeError):
        return _no_store({"ok": False, "error": "invalid json"}, status=400)
    if not isinstance(data, dict) or not wa_sessions.is_valid(data.get('session')):
        return _no_store({"ok": False, "error": "invalid session"}, status=400)
    session = data['session'].strip()
    chat_id = str(data.get('chatId') or '').strip()
    if not _CHAT_ID_RE.match(chat_id):
        return _no_store({"ok": False, "error": "invalid chatId"}, status=400)
    if label_access.chat_hidden(request.user, session, chat_id):
        return _refuse_hidden()
    api_key = getattr(settings, 'WAHA_API_KEY', '') or ''
    try:
        resp = requests.post(f"{_waha_base()}/api/{session}/chats/{chat_id}/messages/read",
                             json={}, headers={'X-Api-Key': api_key}, timeout=15)
    except requests.exceptions.RequestException:
        return _no_store({"ok": False, "error": "WAHA unreachable"}, status=502)
    return _no_store({"ok": 200 <= resp.status_code < 300}, status=200 if resp.ok else 502)


def _no_store(data, status=200):
    resp = JsonResponse(data, status=status)
    resp['Cache-Control'] = 'no-store, no-cache, must-revalidate, private'
    return resp


def _chat_info_response(request):
    """Right-hand panel: who the chat is, plus its CRM leads for staff who may see them."""
    from . import chat_panel

    chat_id = (request.GET.get('chatId') or '').strip()
    if not chat_id:
        return _no_store({"ok": False, "error": "chatId required"}, status=400)
    session = wa_sessions.from_request(request)
    if label_access.chat_hidden(request.user, session, chat_id):
        return _refuse_hidden()
    data = {
        "ok": True,
        "info": chat_panel.chat_info(session, chat_id),
        "media_counts": chat_panel.media_counts(session, chat_id),
        "leads_visible": chat_panel.can_see_leads(request.user),
        "can_link": chat_panel.can_link_leads(request.user),
        "can_save_docs": chat_panel.can_save_driver_docs(request.user),
        "can_verify_docs": chat_panel.can_verify_driver_docs(request.user),
        "can_label": chat_panel.can_link_leads(request.user),
    }
    if data["leads_visible"] and data["info"]["kind"] == 'person':
        from crm import ownership

        connected = chat_panel.connected_leads(session, chat_id)
        can_link = data["can_link"]
        stage_cache = {}
        # Someone else's lead still shows — name, stage and owner, so nobody starts a
        # second card for the same person — but without the working card's controls.
        data["leads"] = [
            chat_panel.lead_dict(
                l, how, detail=can_link and ownership.can_see_lead(request.user, l),
                stage_cache=stage_cache, label=label)
            for l, how, label in connected
        ]
        if connected and can_link:
            data["staff"] = chat_panel.staff_options(request.user)
        data["suggested"] = [] if connected else [
            chat_panel.lead_dict(l) for l in chat_panel.suggested_leads(
                session, chat_id, request.GET.get('name') or '', user=request.user,
            )
        ]
        # The platform login(s) on this number, or reached through a connected lead.
        data["accounts"] = chat_panel.chat_accounts(data["info"]["phone"], connected, request.user)
    return _no_store(data)


def _chat_media_response(request):
    from . import chat_panel

    chat_id = (request.GET.get('chatId') or '').strip()
    kind = request.GET.get('kind') or 'photos'
    if not chat_id or kind not in chat_panel.MEDIA_KINDS:
        return _no_store({"ok": False, "error": "chatId and a valid kind required"}, status=400)
    offset = safe_int(request.GET.get('offset'), default=0, minimum=0, maximum=100000)
    if label_access.chat_hidden(request.user, wa_sessions.from_request(request), chat_id):
        return _refuse_hidden()
    items, more = chat_panel.media_items(wa_sessions.from_request(request), chat_id, kind, offset)
    return _no_store({"ok": True, "kind": kind, "items": items, "has_more": more})


def _lead_search_response(request):
    from . import chat_panel

    if not chat_panel.can_link_leads(request.user):
        return _no_store({"ok": False, "error": "Sign in with CRM access"}, status=403)
    leads = chat_panel.search_leads(request.GET.get('q') or '', user=request.user)
    return _no_store({"ok": True, "leads": [chat_panel.lead_dict(l) for l in leads]})


@_staff_only
@require_http_methods(["POST"])
def wa_chats_link_lead(request):
    """Link the open chat to an existing CRM lead, or unlink it (never creates one).

    CSRF-protected and gated on a Django staff login with CRM link rights — the
    htpasswd on /waha/ alone is not enough to write to the CRM.
    """
    from crm.models import Lead
    from . import chat_panel

    if not chat_panel.can_link_leads(request.user):
        return _no_store({"ok": False, "error": "Sign in to the staff portal with CRM access to link leads."}, status=403)
    try:
        data = json.loads(request.body.decode('utf-8') or '{}')
    except (ValueError, UnicodeDecodeError):
        return _no_store({"ok": False, "error": "invalid json"}, status=400)
    if not isinstance(data, dict):
        return _no_store({"ok": False, "error": "body must be object"}, status=400)

    chat_id = str(data.get('chatId') or '').strip()
    digits, suffix = chat_panel.split_chat_id(chat_id)
    if suffix not in ('lid', 'c.us') or not digits.isdigit():
        return _no_store({"ok": False, "error": "Only a person's chat can be linked to a lead."}, status=400)
    lead_id = safe_int(data.get('lead_id'), default=0, minimum=0)
    lead = Lead.objects.filter(pk=lead_id).select_related('merged_into').first()
    if not lead:
        return _no_store({"ok": False, "error": "Lead not found"}, status=404)
    if lead.merged_into_id:
        lead = lead.merged_into
    from crm import ownership
    if not ownership.can_see_lead(request.user, lead):
        return _no_store({"ok": False, "error": f"Lead #{lead.pk} belongs to "
                          f"{ownership.user_label(lead.assigned_to)} — only they or a lead manager can link chats to it."},
                         status=403)
    session = wa_sessions.normalize(data.get('session'))
    if label_access.chat_hidden(request.user, session, chat_id):
        return _refuse_hidden()
    if data.get('action') == 'unlink':
        if not chat_panel.unlink_lead(lead, session, chat_id, request.user):
            return _no_store({"ok": False, "error": "This lead is matched by its own phone number, not a linked one — change the phone in the CRM instead."}, status=400)
        return _no_store({"ok": True})
    label = str(data.get('label') or '').strip()[:40]
    chat_panel.link_lead(lead, session, chat_id, request.user, label=label)
    return _no_store({"ok": True, "lead": chat_panel.lead_dict(lead, 'linked', label=label)})


_CHAT_ID_RE = re.compile(r'^[\w.-]+@(?:c\.us|lid|g\.us)$')




@_staff_only
@require_http_methods(["POST"])
def wa_chats_set_labels(request):
    """Add/remove WhatsApp Business labels on a chat — the change lands in WhatsApp.

    WAHA's PUT replaces the chat's whole label set, so the browser sends only what
    it changed and we apply it to the labels read fresh from WAHA here; a label
    added on the phone meanwhile is kept, not wiped. Same gate as link-lead.
    """
    from . import chat_panel

    if not chat_panel.can_link_leads(request.user):
        return _no_store({"ok": False, "error": "Sign in to the staff portal with CRM access to change labels."}, status=403)
    try:
        data = json.loads(request.body.decode('utf-8') or '{}')
    except (ValueError, UnicodeDecodeError):
        return _no_store({"ok": False, "error": "invalid json"}, status=400)
    if not isinstance(data, dict):
        return _no_store({"ok": False, "error": "body must be object"}, status=400)

    # Strict: a junk name must not fall back to — and relabel — the default number.
    if not wa_sessions.is_valid(data.get('session')):
        return _no_store({"ok": False, "error": "invalid session"}, status=400)
    session = data['session'].strip()
    chat_id = str(data.get('chatId') or '').strip()
    if not _CHAT_ID_RE.match(chat_id):
        return _no_store({"ok": False, "error": "invalid chatId"}, status=400)
    if label_access.chat_hidden(request.user, session, chat_id):
        return _refuse_hidden()
    add = data.get('add') or []
    remove = data.get('remove') or []
    if not isinstance(add, list) or not isinstance(remove, list):
        return _no_store({"ok": False, "error": "add and remove must be lists"}, status=400)
    add = {str(x) for x in add}
    remove = {str(x) for x in remove}

    known = chat_labels_svc.session_labels(session)
    if known is None:
        return _no_store({"ok": False, "error": "Could not read this number's labels from WhatsApp."}, status=502)
    known_ids = {str(l.get('id')) for l in known if isinstance(l, dict)}
    # Outside marketing the marketing-only labels are not offered, so not settable.
    if not label_access.can_see_all(request.user):
        known_ids -= label_access.restricted_label_ids(session)
    if not (add | remove) <= known_ids:
        return _no_store({"ok": False, "error": "Unknown label — reload the page."}, status=400)

    current = chat_labels_svc.chat_labels(session, chat_id)
    if current is None:
        return _no_store({"ok": False, "error": "Could not read this chat's labels from WhatsApp."}, status=502)
    ids = [str(l.get('id')) for l in current if isinstance(l, dict)]
    ids = [i for i in ids if i not in remove] + sorted(add - set(ids))

    status = chat_labels_svc.put_chat_labels(session, chat_id, ids)
    if not 200 <= status < 300:
        return _no_store({"ok": False, "error": f"WhatsApp refused the change (HTTP {status or 'network'})."}, status=502)
    logger.info("wa labels: %s set %s on %s (+%s -%s)", request.user, ids, chat_id, sorted(add), sorted(remove))
    # A 2xx is not proof: WhatsApp applies the change asynchronously, and for
    # some chats it accepts the call and applies nothing. Say so rather than
    # reporting a save that did not happen.
    confirmed = chat_labels_svc.confirm_chat_labels(session, chat_id, ids)
    if not confirmed:
        logger.warning("wa labels: %s not confirmed by WhatsApp for %s (wanted %s)", session, chat_id, ids)

    # The contact row is the base data — mirror what WhatsApp now holds, then
    # carry the same change to our other numbers that already chat this person.
    by_name = {str(l.get('id')): (l.get('name') or '') for l in known if isinstance(l, dict)}
    chat_labels_svc.store(session, chat_id, [l for l in known
                                             if isinstance(l, dict) and str(l.get('id')) in set(ids)])
    sync = chat_labels_svc.propagate(
        session, chat_id,
        [by_name.get(i, '') for i in sorted(add)],
        [by_name.get(i, '') for i in sorted(remove)],
        actor=str(request.user),
    )
    # The mirror still runs on every number (a label belongs to the contact), but
    # the note only names numbers this person may open.
    open_numbers = session_access.allowed(request.user)
    if open_numbers is not None and isinstance(sync, list):
        sync = [r for r in sync if isinstance(r, dict) and r.get('session') in open_numbers]

    # `ids` is the set WhatsApp now holds, because we just wrote it. Reading the
    # chat back here is not safe: WAHA can still answer with the pre-PUT set for
    # a moment, and replying with that left the panel showing "nothing saved"
    # until the page was reloaded. Names/colours come from the lists already
    # read, so no extra call is needed either.
    by_id = {str(l.get('id')): l for l in known if isinstance(l, dict)}
    for l in current:
        if isinstance(l, dict):
            by_id.setdefault(str(l.get('id')), l)
    shown = known_ids | {i for i in ids if label_access.can_see_all(request.user)}
    return _no_store({"ok": True, "sync": sync, "confirmed": confirmed, "labels": [
        {"id": i, "name": (by_id.get(i) or {}).get('name') or '',
         "colorHex": (by_id.get(i) or {}).get('colorHex') or ''}
        for i in ids if i in shown
    ]})


@_staff_only
@require_http_methods(["POST"])
def wa_chats_create_label(request):
    """Create a new WhatsApp label on this number, from the chat panel.

    A label belongs to the whole number, not to the chat it was made from, so
    this is narrower than setting labels: marketing and super admins only. The
    new label is not applied here — the browser ticks it and the ordinary
    "Save to WhatsApp" puts it on the chat, so one path writes to a chat.
    """
    if not label_access.can_see_all(request.user):
        return _no_store({"ok": False,
                          "error": "Only marketing staff and super admins can create a label."}, status=403)
    try:
        data = json.loads(request.body.decode('utf-8') or '{}')
    except (ValueError, UnicodeDecodeError):
        return _no_store({"ok": False, "error": "invalid json"}, status=400)
    if not isinstance(data, dict):
        return _no_store({"ok": False, "error": "body must be object"}, status=400)
    if not wa_sessions.is_valid(data.get('session')):
        return _no_store({"ok": False, "error": "invalid session"}, status=400)
    session = data['session'].strip()

    name = ' '.join(str(data.get('name') or '').split())[:100]
    if not name:
        return _no_store({"ok": False, "error": "Give the label a name."}, status=400)
    color = safe_int(data.get('color'), default=chat_labels_svc.FALLBACK_COLOR, minimum=0)
    if color >= len(chat_labels_svc.PALETTE):
        color = chat_labels_svc.FALLBACK_COLOR

    known = chat_labels_svc.session_labels(session)
    if known is None:
        return _no_store({"ok": False, "error": "Could not read this number's labels from WhatsApp."}, status=502)
    # Already there under this name (or its plural): hand it back so the panel
    # ticks it instead of making WhatsApp hold two labels that mean one thing.
    existing = chat_labels_svc.find_label(known, name)
    if existing is not None:
        return _no_store({"ok": True, "existing": True, "label": {
            "id": str(existing.get('id')), "name": existing.get('name') or '',
            "colorHex": existing.get('colorHex') or ''}})

    # WhatsApp holds at most 20 labels per number and the built-in ones count,
    # so say that plainly instead of passing back a bare 422.
    if len(known) >= chat_labels_svc.MAX_LABELS:
        return _no_store({"ok": False, "error": (
            f"This number already has WhatsApp's maximum of {chat_labels_svc.MAX_LABELS} labels — "
            "delete one in WhatsApp first.")}, status=400)

    row, refused = chat_labels_svc.create_label_detail(session, name, color=color)
    if row is None:
        return _no_store({"ok": False, "error": refused}, status=502)
    logger.info("wa labels: %s created %r on %s as id %s", request.user, name, session, row.get('id'))
    return _no_store({"ok": True, "existing": False, "label": {
        "id": str(row.get('id')), "name": row.get('name') or name,
        "colorHex": row.get('colorHex') or chat_labels_svc.PALETTE[color]}})


@_staff_only
@require_http_methods(["POST"])
def wa_chats_save_doc(request):
    """File a chat photo onto the linked driver lead's documents (Selfie, QID…).

    CSRF-protected like link-lead, and gated on CRM + driver-document rights. The
    photo must come from this chat and the lead must be connected to this chat,
    so a hand-written id cannot move one person's photo onto another's file.
    """
    from crm.models import Lead
    from . import chat_panel

    if not chat_panel.can_save_driver_docs(request.user):
        return _no_store({"ok": False, "error": "Your account cannot edit driver documents."}, status=403)
    try:
        data = json.loads(request.body.decode('utf-8') or '{}')
    except (ValueError, UnicodeDecodeError):
        return _no_store({"ok": False, "error": "invalid json"}, status=400)
    if not isinstance(data, dict):
        return _no_store({"ok": False, "error": "body must be object"}, status=400)

    session = wa_sessions.normalize(data.get('session'))
    chat_id = str(data.get('chatId') or '').strip()
    if label_access.chat_hidden(request.user, session, chat_id):
        return _refuse_hidden()
    lead_id = safe_int(data.get('lead_id'), default=0, minimum=0)
    connected = {l.pk: l for l, _how, _label in chat_panel.connected_leads(session, chat_id)}
    lead = connected.get(lead_id)
    if not lead or lead.category != Lead.CATEGORY_DRIVER or not lead.driver_id:
        return _no_store({"ok": False, "error": "This chat has no connected driver lead with a driver profile."}, status=400)
    from crm import ownership
    if not ownership.can_see_lead(request.user, lead):
        return _no_store({"ok": False, "error": f"Lead #{lead.pk} belongs to "
                          f"{ownership.user_label(lead.assigned_to)} — only they or a lead manager can file to it."},
                         status=403)
    msg = chat_panel._chat_rows(session, chat_id).filter(
        pk=safe_int(data.get('msg_id'), default=0, minimum=0)).first()
    if not msg:
        return _no_store({"ok": False, "error": "Photo not found in this chat."}, status=404)
    doc_type = str(data.get('doc_type') or '')
    side = str(data.get('side') or 'front')
    try:
        chat_panel.save_chat_photo_to_driver(lead, msg, doc_type, side, request.user)
    except ValueError as e:
        return _no_store({"ok": False, "error": str(e)}, status=400)
    return _no_store({"ok": True, "docs": chat_panel.driver_documents(lead.driver)})


_REPLY_ID_RE = re.compile(r'^(true|false)_[\w.@-]+_[\w@.-]+$')


@_staff_only
@require_http_methods(["POST"])
def wa_chats_send(request):
    try:
        body_raw = request.body
        data = json.loads(body_raw.decode('utf-8') if isinstance(body_raw, (bytes, bytearray)) else body_raw) if body_raw else {}
    except (ValueError, UnicodeDecodeError) as e:
        return JsonResponse({"ok": False, "error": f"invalid json: {e}"}, status=400)
    if not isinstance(data, dict):
        return JsonResponse({"ok": False, "error": "body must be object"}, status=400)

    to = data.get('to')
    text = data.get('text')
    if not isinstance(to, str) or not isinstance(text, str) or not to or not text:
        return JsonResponse({"ok": False, "error": "to and text required"}, status=400)

    session = wa_sessions.normalize(data.get('session'))

    if label_access.chat_hidden(request.user, session, to):
        return _refuse_hidden()

    if '@' not in to:
        digits = re.sub(r'\D', '', to)
        if not digits:
            return JsonResponse({"ok": False, "error": "invalid to"}, status=400)
        to = f"{digits}@c.us"
    else:
        if not _strip_jid(to):
            return JsonResponse({"ok": False, "error": "invalid to"}, status=400)

    base = _waha_base()
    api_key = getattr(settings, 'WAHA_API_KEY', '') or ''
    url = f"{base}/api/sendText"
    payload = {"chatId": to, "text": text, "session": session}
    # Quote-reply: WAHA wants the full serialized id of the message answered
    # (e.g. `false_974...@c.us_3EB0...`), which is the inbox row's `waha_id`.
    reply_to = data.get('reply_to')
    if reply_to:
        if not isinstance(reply_to, str) or not _REPLY_ID_RE.match(reply_to):
            return JsonResponse({"ok": False, "error": "invalid reply_to"}, status=400)
        payload["reply_to"] = reply_to

    try:
        resp = requests.post(
            url,
            json=payload,
            headers={'X-Api-Key': api_key, 'Content-Type': 'application/json'},
            timeout=15,
        )
    except requests.exceptions.Timeout:
        return JsonResponse({"ok": False, "waha_status": 0, "waha": "timeout"}, status=504)
    except requests.exceptions.RequestException as e:
        return JsonResponse({"ok": False, "waha_status": 0, "waha": f"network error: {e}"[:4000]}, status=502)

    waha_status = resp.status_code
    try:
        waha_body = resp.json()
    except ValueError:
        waha_body = (resp.text or '')[:4000]

    success = 200 <= waha_status < 300
    http_status = 200 if success else 502
    return JsonResponse({"ok": success, "waha_status": waha_status, "waha": waha_body}, status=http_status)


def store_live_message(session, m, archive=True):
    """Save one WAHA message dict (fetched with downloadMedia=true) → (row, created).

    Shared by resync and the live-media route. Never clobbers a stored row's
    fields, only fills missing media; archives the file straight away because
    WAHA purges its downloaded copy within minutes — unless `archive` is False
    (a group resync: group media waits for a click).
    """
    from whatsapp.secrets import redact_payload, redact_text
    waha_id = str(m.get('id') or '')
    body_text = m.get('body') or ''
    # Our own outbound sends come through here too, auth codes included.
    m, _ = redact_payload(m, body_text)
    body_text, _ = redact_text(body_text)
    media = m.get('media') if isinstance(m.get('media'), dict) else {}
    media_url = media.get('url') or ''
    media_mime = media.get('mimetype') or media.get('mime') or ''
    ts = m.get('timestamp')
    received_at = datetime.fromtimestamp(ts, tz=dt_tz.utc) if isinstance(ts, (int, float)) else None
    obj, created = WhatsAppMessage.objects.get_or_create(
        session=session,
        waha_message_id=waha_id,
        defaults={
            'direction': 'outbound' if m.get('fromMe') is True else 'inbound',
            'from_number': _strip_jid(m.get('from') or ''),
            'to_number': _strip_jid(m.get('to') or ''),
            'body': body_text,
            'message_type': _msg_type(m),
            'media_url': media_url,
            'media_mime': media_mime,
            'status': 'archived',
            'received_at': received_at,
            'raw_payload': m,
        },
    )
    if not created:
        changed = []
        if not obj.media_url and media_url:
            obj.media_url = media_url
            changed.append('media_url')
        if not obj.media_mime and media_mime:
            obj.media_mime = media_mime
            changed.append('media_mime')
        if changed:
            obj.save(update_fields=changed + ['updated_at'])
    if archive and obj.media_url and not obj.media_file:
        try:
            from whatsapp.media_archive import archive_message_media
            archive_message_media(obj)
        except Exception:
            logger.exception('media archive failed for msg %s', obj.pk)
    return obj, created


@_staff_only
@require_http_methods(["POST"])
def wa_chats_resync(request):
    chat_id = (request.GET.get('chatId') or '').strip()
    if not chat_id:
        return JsonResponse({"ok": False, "error": "chatId required"}, status=400)

    base = _waha_base()
    session = wa_sessions.from_request(request)
    if label_access.chat_hidden(request.user, session, chat_id):
        return _refuse_hidden()
    api_key = getattr(settings, 'WAHA_API_KEY', '') or ''
    url = f"{base}/api/{session}/chats/{chat_id}/messages"
    # Group media is downloaded only when someone clicks it, so a group resync
    # does not ask WAHA to pull 200 messages' worth of files.
    is_group = chat_id.endswith('@g.us')

    try:
        resp = requests.get(
            url,
            params={'limit': 200, 'downloadMedia': 'false' if is_group else 'true'},
            headers={'X-Api-Key': api_key},
            timeout=25,
        )
    except requests.exceptions.Timeout:
        return JsonResponse({"ok": False, "error": "timeout"}, status=504)
    except requests.exceptions.RequestException as e:
        return JsonResponse({"ok": False, "error": f"network error: {e}"[:4000]}, status=502)

    if not (200 <= resp.status_code < 300):
        return JsonResponse({"ok": False, "error": f"waha {resp.status_code}"}, status=502)

    try:
        body = resp.json()
    except ValueError:
        return JsonResponse({"ok": False, "error": "invalid waha response"}, status=502)

    if isinstance(body, dict) and isinstance(body.get('messages'), list):
        msgs = body['messages']
    elif isinstance(body, list):
        msgs = body
    else:
        msgs = []

    inserted = 0
    total = 0
    for m in msgs:
        if not isinstance(m, dict) or not m.get('id'):
            continue
        total += 1
        _obj, created = store_live_message(session, m, archive=not is_group)
        if created:
            inserted += 1

    return JsonResponse({"ok": True, "count": total, "inserted": inserted, "messages": []}, status=200)


@_staff_only
@require_http_methods(["GET"])
def wa_chats_avatar(request):
    """A chat's WhatsApp profile photo, from our saved copy (loaded on first ask).

    404 = no photo; the browser keeps that answer for an hour so an inbox full of
    photo-less contacts does not re-ask on every re-render.
    """
    from django.http import FileResponse
    from . import profile_photos

    chat_id = (request.GET.get('chatId') or '').strip()
    if not profile_photos.is_valid_chat_id(chat_id):
        return HttpResponse(status=400)
    if label_access.chat_hidden(request.user, wa_sessions.from_request(request), chat_id):
        return HttpResponse(status=404)
    row = profile_photos.get_photo(wa_sessions.from_request(request), chat_id)
    if not row or not row.has_photo or not row.photo:
        resp = HttpResponse(status=404)
        resp['Cache-Control'] = 'private, max-age=%d' % (3600 if row else 300)
        return resp
    ext = row.photo.name.rsplit('.', 1)[-1].lower()
    ctype = {'jpg': 'image/jpeg', 'png': 'image/png', 'webp': 'image/webp'}.get(ext, 'application/octet-stream')
    try:
        resp = FileResponse(row.photo.open('rb'), content_type=ctype)
    except OSError:
        logger.warning('avatar file missing for %s', row)
        return HttpResponse(status=404)
    resp['Cache-Control'] = 'private, max-age=86400'
    resp['X-Content-Type-Options'] = 'nosniff'
    return resp


@_staff_only
@_session_from_row
@require_http_methods(["GET"])
def wa_chats_media(request, msg_id):
    """Stream one stored message's attachment to the inbox UI.

    The archive lives in private storage with no public URL — deliberately, so
    customer photos are not readable off /media/ — and WAHA's own copy is gone
    within minutes. This is the inbox's only way to show either. Protected by the
    same nginx htpasswd as the rest of /waha/, and it reuses the CRM streamer so
    the mimetype hardening stays in one place.

    Deliberately NOT behind crm_services.wa_read_blocked, on the account owner's
    explicit decision (2026-09-18). That gate stops a Django staff user opening a
    registered account's conversation from the CRM, where the audience is every
    staff member. This surface is different: the caller has already passed the
    htpasswd on /waha/, and the message list sitting beside this endpoint already
    serves those same conversations in full text. Applying it here hid only the
    attachments of driver and client chats — the inbox's main traffic — while
    their messages stayed on screen, so it bought no confidentiality and cost the
    ops team every photo and voice note. The CRM's own gate is untouched.

    ?fetch=1 is the inbox's download click (group media is never archived by the
    cron): a file we do not hold yet is pulled from WhatsApp and kept first.
    """
    from django.http import Http404
    from django.shortcuts import get_object_or_404

    from workforce.crm_views import _stream_wa_media

    msg = get_object_or_404(WhatsAppMessage, pk=msg_id)
    # The URL carries no ?session=, so the number gate runs on the row itself.
    if not session_access.can_open(request.user, msg.session):
        raise Http404
    if not label_access.can_see_all(request.user):
        try:
            hidden = label_access.restricted_identifiers(msg.session)
        except label_access.MembershipUnknown:
            hidden = None
        if hidden is None or {msg.from_number, msg.to_number} & hidden:
            raise Http404
    if request.GET.get('fetch') == '1' and not msg.media_file:
        _fetch_on_demand(msg)
    return _stream_wa_media(msg)


def _fetch_on_demand(msg, chat_id=None):
    from .media_archive import fetch_on_demand
    try:
        fetch_on_demand(msg, chat_id)
    except Exception:
        logger.exception('media fetch on demand failed for msg %s', msg.pk)


_LIVE_MSG_ID_RE = re.compile(r'^(true|false)_[\w.@-]+_[\w@.-]+$')


@_staff_only
@require_http_methods(["GET"])
def wa_chats_media_live(request):
    """?session=&chatId=&msgId= — attachment of a message we have not stored yet.

    Stores the message (and archives its file) on first view, then serves it the
    way media/<id>/ does, so the next load reads our own copy. A row stored
    without its file (a group's, or one whose WAHA link expired) is fetched afresh.
    """
    from django.http import Http404

    from workforce.crm_views import _stream_wa_media

    session = (request.GET.get('session') or '').strip()
    chat_id = (request.GET.get('chatId') or '').strip()
    msg_id = (request.GET.get('msgId') or '').strip()
    if not wa_sessions.is_valid(session) or not _CHAT_ID_RE.match(chat_id) or not _LIVE_MSG_ID_RE.match(msg_id):
        raise Http404
    if label_access.chat_hidden(request.user, session, chat_id):
        raise Http404
    row = WhatsAppMessage.objects.filter(session=session, waha_message_id=msg_id).first()
    if row is None:
        status, m = _waha_json(f"/api/{session}/chats/{chat_id}/messages/{msg_id}",
                               {'downloadMedia': 'true'}, timeout=40)
        if status != 200 or not isinstance(m, dict) or str(m.get('id') or '') != msg_id:
            raise Http404
        row, _created = store_live_message(session, m)
    elif not row.media_file:
        _fetch_on_demand(row, chat_id)
    return _stream_wa_media(row)


def _label_rules_token(user, session):
    see_all = label_access.can_see_all(user)
    ids = '' if see_all else ','.join(sorted(label_access.restricted_label_ids(session)))
    return hashlib.sha1(f'{see_all}|{ids}'.encode()).hexdigest()[:10]


def _session_health_link(user):
    """The QR/session dashboard is super-admin only, so only they get the link."""
    from core.departments import ADMIN, user_departments

    if ADMIN not in user_departments(user):
        return ''
    return ('<div class="wa-modal__foot"><a href="/waha/wa-dashboard/?session=%SESSION%">'
            'Session health &amp; QR →</a></div>')


def _render_page(request):
    session = wa_sessions.from_request(request)
    # Header chip names the number on screen — its WhatsApp display name, else
    # the raw WAHA session name.
    label = next(
        (s['push_name'] for s in wa_sessions.list_sessions() if s['name'] == session and s['push_name']),
        session,
    )
    html = (
        _CHATS_HTML
        .replace('%SESSION_LABEL%', escape(label))
        .replace('%SESSION_TABS%', wa_sessions.render_tabs(session, request.path, always=True,
                                                           only=session_access.allowed(request.user)))
        .replace('%SESSION_HEALTH_LINK%', _session_health_link(request.user))
        .replace('%SESSION%', session)
        .replace('%CSRF%', get_token(request))
        .replace('%LABEL_RULES%', _label_rules_token(request.user, session))
        .replace('%CAN_MAKE_LABEL%', 'true' if label_access.can_see_all(request.user) else 'false')
        .replace('%LABEL_COLORS%', json.dumps(chat_labels_svc.PALETTE))
    )
    resp = HttpResponse(html, content_type='text/html; charset=utf-8')
    # Voice notes record from the microphone, which the site-wide policy
    # (core/middleware.py) blocks; it only fills the header when unset.
    resp['Permissions-Policy'] = 'geolocation=(self), camera=(self), microphone=(self), payment=(), usb=()'
    return resp


_CHATS_HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>WAHA Inbox</title>
<style>
/* WhatsApp-Web parity palette — intentionally NOT Brand Kit. */
:root {
  --wa-brand: #00a884;
  --wa-brand-hover: #008f6f;
  --wa-brand-tint: #e7f6f0;
  --wa-out: #d9fdd3;
  --wa-in: #ffffff;
  --wa-conv-bg: #efeae2;
  --wa-sidebar: #f0f2f5;
  --wa-border: #e9edef;
  --wa-muted: #667781;
  --wa-muted-2: #8696a0;
}
* { box-sizing: border-box; }
html, body { height: 100%; margin: 0; padding: 0; overflow: hidden; }
body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
  font-size: 0.875rem;
  color: #111b21;
  background: #d1d7db;
}

.wa-app {
  display: flex;
  height: 100vh;
  width: 100%;
}

/* Sidebar */
.wa-side {
  width: 21.25rem;
  flex: 0 0 21.25rem;
  background: var(--wa-sidebar);
  border-right: 0.0625rem solid var(--wa-border);
  display: flex;
  flex-direction: column;
  min-width: 0;
}
.wa-side__hdr {
  padding: 0.625rem 0.875rem;
  display: flex;
  align-items: center;
  gap: 0.5rem;
  border-bottom: 0.0625rem solid var(--wa-border);
  background: var(--wa-sidebar);
}
.wa-chip {
  background: var(--wa-brand);
  color: #fff;
  border-radius: 0.75rem;
  padding: 0.125rem 0.5rem;
  font-size: 0.75rem;
  font-weight: 600;
  letter-spacing: 0.03125rem;
  max-width: 12rem;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.wa-side__phone { color: var(--wa-muted); font-size: 0.75rem; }

.wa-side__filters {
  padding: 0.5rem 0.75rem;
  display: flex;
  flex-direction: column;
  gap: 0.375rem;
  border-bottom: 0.0625rem solid var(--wa-border);
}
.wa-search {
  flex: 1;
  min-width: 0;
  border: 0.0625rem solid var(--wa-border);
  border-radius: 0.5rem;
  padding: 0.4375rem 0.625rem;
  font-size: 0.8125rem;
  background: #fff;
  outline: none;
}
.wa-search:focus { border-color: var(--wa-brand); }
.wa-side__row { display: flex; align-items: center; gap: 0.375rem; }
.wa-select--type { flex: 0 0 6.5rem; }
/* Quick picks for the two most-used labels; they drive #wa-label-filter. */
.wa-qlabel {
  flex: 0 0 auto;
  border: 0.0625rem solid var(--wa-border);
  border-radius: 0.375rem;
  padding: 0.3125rem 0.5rem;
  font-size: 0.75rem;
  background: #fff;
  color: #111b21;
  white-space: nowrap;
  cursor: pointer;
}
.wa-qlabel:hover { border-color: var(--wa-brand); }
.wa-qlabel.is-active { border-color: var(--wa-brand); color: var(--wa-brand); font-weight: 600; }
.wa-select { min-width: 0; }
.wa-select {
  flex: 1;
  border: 0.0625rem solid var(--wa-border);
  border-radius: 0.375rem;
  padding: 0.3125rem 0.375rem;
  font-size: 0.75rem;
  background: #fff;
  color: #111b21;
  outline: none;
}

.wa-list { flex: 1; overflow-y: auto; }
.wa-row {
  display: flex;
  align-items: center;
  gap: 0.625rem;
  padding: 0.625rem 0.875rem;
  border-bottom: 0.0625rem solid var(--wa-border);
  cursor: pointer;
  background: var(--wa-sidebar);
}
.wa-row:hover { background: #ebeef0; }
.wa-row--active { background: #f0f2f5; box-shadow: inset 0.1875rem 0 0 var(--wa-brand); }
.wa-row--virtual { background: var(--wa-brand-tint); }
.wa-avatar {
  width: 2.5rem;
  height: 2.5rem;
  border-radius: 50%;
  background: #cfd8dc;
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 0.8125rem;
  font-weight: 600;
  flex: 0 0 2.5rem;
}
/* Saved WhatsApp profile photo laid over the initials; removed if it fails to load. */
.wa-avatar, .wa-who__av { position: relative; overflow: hidden; }
.wa-pic { position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover; border-radius: 50%; background: #cfd8dc; }
/* Two-column grid: name / preview on the left, time / WhatsApp labels stacked on the right. */
.wa-row__body {
  flex: 1;
  min-width: 0;
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  column-gap: 0.5rem;
  row-gap: 0.125rem;
  align-items: center;
}
.wa-row__top { display: contents; }
.wa-row__name {
  font-size: 0.875rem;
  color: #111b21;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 11rem;
}
.wa-row__time { font-size: 0.6875rem; color: var(--wa-muted); white-space: nowrap; justify-self: end; }
.wa-row__time--unread { color: var(--wa-brand); font-weight: 600; }
.wa-row__pin {
  font-size: 0.625rem;
  color: var(--wa-muted-2);
  margin-left: 0.25rem;
  vertical-align: middle;
}
.wa-row__unread {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 1.125rem;
  height: 1.125rem;
  padding: 0 0.375rem;
  border-radius: 0.625rem;
  background: var(--wa-brand);
  color: #fff;
  font-size: 0.625rem;
  font-weight: 700;
  flex: 0 0 auto;
}
.wa-row__pv-line {
  display: flex;
  align-items: center;
  gap: 0.375rem;
  min-width: 0;
}
.wa-row__pv-who { color: var(--wa-muted-2); }
.wa-row__preview {
  color: var(--wa-muted);
  font-size: 0.8125rem;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  flex: 1 1 auto;
  min-width: 0;
}
.wa-row__labels {
  grid-column: 2;
  grid-row: 2;
  justify-self: end;
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 0.1875rem;
  max-width: 9rem;
  overflow: hidden;
}
.wa-label-chip {
  display: inline-flex;
  align-items: center;
  font-size: 0.5625rem;
  font-weight: 600;
  line-height: 1;
  padding: 0.125rem 0.3125rem;
  border-radius: 0.5rem;
  white-space: nowrap;
  max-width: 5rem;
  overflow: hidden;
  text-overflow: ellipsis;
  letter-spacing: 0.01em;
}
.wa-label-chip__dot {
  width: 0.3125rem;
  height: 0.3125rem;
  border-radius: 50%;
  margin-right: 0.1875rem;
  flex: 0 0 auto;
}

/* Conversation */
.wa-conv { flex: 1; display: flex; flex-direction: column; background: var(--wa-conv-bg); min-width: 0; }
.wa-conv__hdr {
  padding: 0.5rem 0.875rem;
  display: flex;
  align-items: center;
  gap: 0.625rem;
  background: var(--wa-sidebar);
  border-bottom: 0.0625rem solid var(--wa-border);
}
.wa-conv__name { font-weight: 600; font-size: 0.9375rem; }
.wa-conv__sub { font-size: 0.75rem; color: var(--wa-muted); }
.wa-btn {
  border: 0;
  background: var(--wa-brand);
  color: #fff;
  border-radius: 0.375rem;
  padding: 0.375rem 0.75rem;
  font-size: 0.75rem;
  cursor: pointer;
  text-decoration: none;
}
.wa-btn:hover { background: var(--wa-brand-hover); }
.wa-btn--ghost {
  background: transparent;
  color: var(--wa-brand);
  border: 0.0625rem solid var(--wa-brand);
}
.wa-btn--ghost:hover { background: var(--wa-brand-tint); }
.wa-conv__spacer { flex: 1; }

.wa-msgs {
  flex: 1;
  overflow-y: auto;
  padding: 0.875rem 1.25rem;
  display: flex;
  flex-direction: column;
  gap: 0.375rem;
}
.wa-msg { display: flex; }
.wa-msg--in { justify-content: flex-start; }
.wa-msg--out { justify-content: flex-end; }
.wa-bubble {
  max-width: 60%;
  padding: 0.5rem 0.75rem;
  border-radius: 0.5rem;
  background: var(--wa-in);
  box-shadow: 0 0.0625rem 0 rgba(0,0,0,0.04);
  font-size: 0.875rem;
  line-height: 1.3;
  word-wrap: break-word;
  overflow-wrap: anywhere;
  /* WhatsApp keeps the sender's own line breaks; without this they collapse
     and a multi-line notice arrives as one paragraph. */
  white-space: pre-wrap;
}
.wa-fmt-mono {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 0.8125rem;
  background: rgba(0, 0, 0, 0.05);
  padding: 0 0.1875rem;
  border-radius: 0.1875rem;
}
.wa-link { color: #027eb5; text-decoration: underline; }
.wa-bubble--out { background: var(--wa-out); }
.wa-bubble__sender {
  font-size: 0.75rem;
  font-weight: 600;
  margin-bottom: 0.1875rem;
}
.wa-bubble__sender-id {
  font-weight: 400;
  color: var(--wa-muted);
  margin-left: 0.25rem;
}
.wa-bubble__time {
  font-size: 0.625rem;
  color: var(--wa-muted);
  margin-top: 0.1875rem;
  text-align: right;
}
/* Sent-message status, as WhatsApp shows it: ✓ sent, ✓✓ delivered, blue ✓✓ read. */
.wa-bubble__tick { margin-left: 0.25rem; letter-spacing: -0.125rem; font-weight: 600; }
.wa-bubble__tick--read { color: #53bdeb; }
.wa-bubble__tick--err { color: #f15c6d; letter-spacing: 0; }
/* Photos and video stills sit in one standard frame whatever their pixel size,
   as WhatsApp does: fixed width, height from the aspect ratio but clamped, and
   the overflow cropped. The full picture opens in the media viewer on click. */
.wa-media-img, .wa-vthumb { width: 16.25rem; max-width: 100%; }
.wa-media-img {
  height: auto; min-height: 8rem; max-height: 20rem;
  object-fit: cover; background: #0b141a;
  border-radius: 0.375rem; display: block;
}
.wa-media-sticker { width: 8rem; height: 8rem; object-fit: contain; display: block; }
.wa-media-video { width: 100%; height: 100%; object-fit: cover; border-radius: 0.375rem; display: block; }
.wa-vthumb { position: relative; cursor: zoom-in; height: 12rem; background: #0b141a; border-radius: 0.375rem; overflow: hidden; }
.wa-vthumb__play {
  position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%);
  width: 3rem; height: 3rem; border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  background: rgba(11,20,26,0.6); color: #fff; font-size: 1.25rem; pointer-events: none;
}
.wa-vthumb--broken::after {
  content: "Video unavailable"; position: absolute; inset: 0;
  display: flex; align-items: center; justify-content: center;
  color: #aebac1; font-size: 0.75rem;
}
.wa-media-audio { width: 100%; }
/* Group media is not downloaded until asked for; this button stands in. */
.wa-mgate {
  display: flex; align-items: center; justify-content: center; gap: 0.5rem;
  width: 16.25rem; max-width: 100%; height: 8rem;
  background: #0b141a; color: #e9edef; border: 0; border-radius: 0.375rem;
  font: inherit; font-size: 0.8125rem; cursor: pointer;
}
.wa-mgate:hover, .wa-mgate:focus-visible { background: #202c33; }
.wa-mgate--sticker { width: 8rem; }
.wa-mgate__icon {
  width: 2.25rem; height: 2.25rem; border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  background: rgba(233,237,239,0.14); font-size: 1rem;
}
.wa-mgate__cap { margin-top: 0.25rem; }
.wa-doc { color: #027eb5; text-decoration: none; }
.wa-msg--hit .wa-bubble { animation: wa-hit-flash 2.5s ease-out; }
@keyframes wa-hit-flash { 0%, 40% { box-shadow: 0 0 0 0.1875rem var(--wa-brand); } 100% { box-shadow: 0 0 0 0 transparent; } }
@media (prefers-reduced-motion: reduce) { .wa-msg--hit .wa-bubble { animation: none; outline: 0.1875rem solid var(--wa-brand); } }
.wa-loadmore { display: flex; align-items: center; justify-content: space-between; gap: 0.5rem; padding: 0.75rem 1rem; font-size: 0.8125rem; color: var(--wa-muted, #667781); }
.wa-list__section { padding: 0.75rem 1rem 0.375rem; font-size: 0.75rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.04em; color: var(--wa-brand); }
.wa-contact { display: flex; align-items: center; gap: 0.5rem; min-width: 12rem; padding: 0.25rem 0; }
.wa-contact + .wa-contact { border-top: 1px solid rgba(0,0,0,0.08); }
.wa-contact__icon { font-size: 1.5rem; line-height: 1; }
.wa-contact__name { font-weight: 600; }
.wa-contact__phone { font-size: 0.8rem; opacity: 0.75; }
.wa-notice { font-style: italic; opacity: 0.7; }

.wa-err {
  display: none;
  background: #fee;
  color: #a00;
  padding: 0.375rem 0.75rem;
  font-size: 0.75rem;
  border-top: 0.0625rem solid #fbb;
}

.wa-comp {
  display: flex;
  gap: 0.5rem;
  padding: 0.625rem 0.875rem;
  background: var(--wa-sidebar);
  border-top: 0.0625rem solid var(--wa-border);
}
.wa-comp__ta {
  flex: 1;
  border: 0.0625rem solid var(--wa-border);
  border-radius: 0.5rem;
  padding: 0.4375rem 0.625rem;
  font-size: 0.875rem;
  font-family: inherit;
  resize: none;
  min-height: 2.25rem;
  max-height: 8rem;
  outline: none;
}
.wa-comp__ta:focus { border-color: var(--wa-brand); }
.wa-comp__send {
  background: var(--wa-brand);
  border: 0;
  color: #fff;
  border-radius: 0.5rem;
  padding: 0 1rem;
  cursor: pointer;
  font-weight: 600;
}
.wa-comp__send:hover { background: var(--wa-brand-hover); }
.wa-comp__send:disabled { background: #b6cfc6; cursor: not-allowed; }

.wa-empty { color: var(--wa-muted); padding: 1.25rem; text-align: center; font-size: 0.8125rem; }

/* Quote-reply: the ↩ on each bubble, the quoted strip inside a reply, and the
   "Replying to" bar above the composer. */
.wa-msg { align-items: center; gap: 0.25rem; }
.wa-msg--out { flex-direction: row-reverse; justify-content: flex-start; }
.wa-reply-btn {
  border: 0; background: transparent; color: var(--wa-muted);
  width: 1.75rem; height: 1.75rem; border-radius: 50%;
  font-size: 1rem; line-height: 1; cursor: pointer;
  opacity: 0; transition: opacity 0.12s;
}
.wa-msg:hover .wa-reply-btn, .wa-reply-btn:focus-visible { opacity: 1; }
.wa-reply-btn:hover { background: rgba(0,0,0,0.06); color: var(--wa-brand); }
@media (hover: none) { .wa-reply-btn { opacity: 0.6; } }
.wa-quote {
  display: block; width: 100%; text-align: left;
  border: 0; border-left: 0.25rem solid var(--wa-brand);
  background: rgba(0,0,0,0.05); border-radius: 0.375rem;
  padding: 0.3125rem 0.5rem; margin-bottom: 0.3125rem;
  font: inherit; font-size: 0.8125rem; color: var(--wa-muted);
  cursor: pointer; white-space: normal;
}
.wa-quote__who { display: block; font-size: 0.75rem; font-weight: 600; color: var(--wa-brand); }
.wa-quote__text {
  display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical;
  overflow: hidden; white-space: pre-wrap;
}
.wa-replybar {
  display: flex; align-items: center; gap: 0.5rem;
  padding: 0.5rem 0.875rem 0; background: var(--wa-sidebar);
  border-top: 0.0625rem solid var(--wa-border);
}
.wa-replybar[hidden] { display: none; }
.wa-replybar .wa-quote { flex: 1; min-width: 0; margin: 0; cursor: default; }
.wa-replybar + .wa-comp { border-top: 0; }
.wa-replybar__close {
  border: 0; background: transparent; color: var(--wa-muted);
  font-size: 1.25rem; line-height: 1; cursor: pointer; padding: 0.25rem;
}
.wa-replybar__close:hover { color: var(--wa-text, #111b21); }

/* Per-message actions (reply · react · more), shown beside the bubble on hover. */
.wa-acts { display: flex; gap: 0.125rem; opacity: 0; transition: opacity 0.12s; }
.wa-msg:hover .wa-acts, .wa-acts:focus-within { opacity: 1; }
@media (hover: none) { .wa-acts { opacity: 0.6; } }
.wa-acts .wa-reply-btn { opacity: 1; }
.wa-bubble { position: relative; }
.wa-msg--reacted .wa-bubble { margin-bottom: 0.875rem; }
.wa-reacts {
  position: absolute; bottom: -0.875rem; right: 0.5rem;
  border: 0.0625rem solid var(--wa-border); background: #fff; border-radius: 1rem;
  padding: 0 0.375rem; font-size: 0.8125rem; line-height: 1.375rem;
  box-shadow: 0 0.0625rem 0.125rem rgba(0,0,0,0.12); cursor: pointer; white-space: nowrap;
}
.wa-msg--in .wa-reacts { right: auto; left: 0.5rem; }
.wa-edited { font-style: italic; margin-right: 0.25rem; }

/* Floating menus: reaction picker, message menu, chat menu. */
.wa-pop {
  position: fixed; z-index: 50; background: #fff; border-radius: 0.5rem;
  box-shadow: 0 0.375rem 1.5rem rgba(11,20,26,0.22); padding: 0.25rem; min-width: 10rem;
}
.wa-pop--emoji { display: flex; gap: 0.125rem; min-width: 0; border-radius: 1.5rem; padding: 0.25rem 0.375rem; }
.wa-pop__emoji {
  border: 0; background: transparent; font-size: 1.375rem; line-height: 1;
  width: 2.25rem; height: 2.25rem; border-radius: 50%; cursor: pointer;
}
.wa-pop__emoji:hover { background: var(--wa-sidebar); }
.wa-pop__emoji.is-on { background: var(--wa-brand-tint); }
.wa-pop__item {
  display: block; width: 100%; text-align: left; border: 0; background: transparent;
  padding: 0.5rem 0.75rem; font: inherit; font-size: 0.875rem; color: #111b21;
  border-radius: 0.375rem; cursor: pointer;
}
.wa-pop__item:hover { background: var(--wa-sidebar); }
.wa-pop__item--danger { color: #d93025; }

/* Composer icons (attach, mic), the attachment bar and the recorder. */
.wa-comp { align-items: flex-end; }
.wa-comp__icon {
  flex: none; width: 2.25rem; height: 2.25rem; border: 0; border-radius: 50%;
  background: transparent; color: var(--wa-muted); cursor: pointer;
  display: flex; align-items: center; justify-content: center;
}
.wa-comp__icon svg { width: 1.375rem; height: 1.375rem; }
.wa-comp__icon:hover { background: rgba(0,0,0,0.06); color: var(--wa-brand); }
.wa-comp__icon:disabled { opacity: 0.4; cursor: not-allowed; background: transparent; }
.wa-comp__send { align-self: stretch; }
.wa-comp--rec > :not(.wa-rec) { display: none; }
.wa-rec { display: flex; align-items: center; gap: 0.625rem; flex: 1; min-height: 2.25rem; }
.wa-rec[hidden] { display: none; }
.wa-rec__dot { width: 0.625rem; height: 0.625rem; border-radius: 50%; background: #f15c6d; animation: wa-rec-blink 1s infinite; }
@keyframes wa-rec-blink { 50% { opacity: 0.25; } }
@media (prefers-reduced-motion: reduce) { .wa-rec__dot { animation: none; } }
.wa-rec__time { font-variant-numeric: tabular-nums; font-weight: 600; }
.wa-rec__hint { color: var(--wa-muted); flex: 1; }
.wa-attachbar {
  display: flex; align-items: center; gap: 0.625rem;
  padding: 0.5rem 0.875rem 0; background: var(--wa-sidebar);
  border-top: 0.0625rem solid var(--wa-border);
}
.wa-attachbar[hidden] { display: none; }
.wa-replybar:not([hidden]) + .wa-attachbar { border-top: 0; }
.wa-attachbar:not([hidden]) + .wa-comp { border-top: 0; }
.wa-attachbar__thumb { width: 3rem; height: 3rem; object-fit: cover; border-radius: 0.375rem; flex: none; }
.wa-attachbar__thumb[hidden] { display: none; }
.wa-attachbar__icon {
  width: 3rem; height: 3rem; border-radius: 0.375rem; flex: none; background: #fff;
  display: flex; align-items: center; justify-content: center; font-size: 1.5rem;
}
.wa-attachbar__icon[hidden] { display: none; }
.wa-attachbar__info { flex: 1; min-width: 0; display: flex; flex-direction: column; }
.wa-attachbar__name { font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.wa-attachbar__meta { font-size: 0.75rem; color: var(--wa-muted); }
.wa-conv--drop .wa-msgs { outline: 0.1875rem dashed var(--wa-brand); outline-offset: -0.5rem; }

/* Forward picker + edit dialog. */
.wa-fwd { width: min(26rem, calc(100vw - 2rem)); }
.wa-fwd__search { width: 100%; margin-bottom: 0.5rem; }
.wa-fwd__list { max-height: 50vh; overflow-y: auto; }
.wa-fwd__row {
  display: flex; align-items: center; gap: 0.625rem; padding: 0.5rem; border-radius: 0.375rem; cursor: pointer;
}
.wa-fwd__row:hover { background: var(--wa-sidebar); }
.wa-fwd__row input { width: 1rem; height: 1rem; accent-color: var(--wa-brand); }
.wa-fwd__name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.wa-modal__foot--split { display: flex; align-items: center; justify-content: space-between; gap: 0.75rem; }
.wa-edit__ta {
  width: 100%; min-height: 6rem; resize: vertical; font: inherit; font-size: 0.875rem;
  border: 0.0625rem solid var(--wa-border); border-radius: 0.5rem; padding: 0.5rem 0.625rem; outline: none;
}
.wa-edit__ta:focus { border-color: var(--wa-brand); }
.wa-edit__note { font-size: 0.75rem; color: var(--wa-muted); margin-top: 0.375rem; }
/* "Send reminder" preview: the whole multi-line reminder visible before it goes. */
.wa-remind { width: min(30rem, calc(100vw - 2rem)); }
.wa-remind__ta { min-height: 18rem; }

/* Chat list: marked-unread dot and the Archived tag. */
.wa-row__unread--dot { min-width: 0.75rem; width: 0.75rem; height: 0.75rem; padding: 0; }
.wa-row__tag {
  flex: none; font-size: 0.6875rem; color: var(--wa-muted); border: 0.0625rem solid var(--wa-border);
  border-radius: 0.25rem; padding: 0 0.25rem; margin-left: 0.25rem;
}
.wa-err--ok { background: #e7f6f0; color: #0b6e55; border-top-color: #b9e4d4; }

/* Gear in the sidebar header — opens the session picker popup. */
.wa-side__spacer { flex: 1; }
.wa-gear {
  border: 0;
  background: transparent;
  color: var(--wa-muted);
  width: 2rem;
  height: 2rem;
  border-radius: 50%;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
}
.wa-gear:hover { background: rgba(0,0,0,0.06); color: #111b21; }
.wa-gear svg { width: 1.125rem; height: 1.125rem; }

/* Session picker popup — one row per WhatsApp number linked to WAHA. */
.wa-modal {
  border: 0;
  border-radius: 0.625rem;
  padding: 0;
  width: min(22rem, calc(100vw - 2rem));
  box-shadow: 0 0.75rem 2rem rgba(0,0,0,0.25);
  color: #111b21;
}
.wa-modal::backdrop { background: rgba(11,20,26,0.45); }
.wa-modal__hdr {
  display: flex;
  align-items: center;
  padding: 0.75rem 1rem;
  border-bottom: 0.0625rem solid var(--wa-border);
  font-weight: 600;
}
.wa-modal__close {
  margin-left: auto;
  border: 0;
  background: transparent;
  font-size: 1.25rem;
  line-height: 1;
  color: var(--wa-muted);
  cursor: pointer;
}
.wa-modal__body { padding: 0.5rem; }
.wa-modal__foot {
  padding: 0.625rem 1rem;
  border-top: 0.0625rem solid var(--wa-border);
  font-size: 0.75rem;
}
.wa-modal__foot a { color: var(--wa-brand); text-decoration: none; }
.wa-sess { display: flex; flex-direction: column; gap: 0.25rem; }
.wa-sess__tab {
  display: block;
  padding: 0.5rem 0.75rem;
  border-radius: 0.5rem;
  font-size: 0.8125rem;
  line-height: 1.3;
  text-decoration: none;
  color: #111b21;
  border: 0.0625rem solid transparent;
}
.wa-sess__tab:hover { background: var(--wa-sidebar); }
.wa-sess__tab--on {
  color: var(--wa-brand);
  font-weight: 600;
  background: var(--wa-brand-tint);
  border-color: var(--wa-brand);
}
.wa-sess__name { display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.wa-sess__num { display: block; font-size: 0.75rem; color: var(--wa-muted); font-weight: 400; font-variant-numeric: tabular-nums; }
/* Right-hand contact panel — info, CRM leads, media. Full height beside the
   conversation on wide screens; slides over it below 75rem. */
.wa-app { position: relative; }
.wa-info {
  width: 22rem;
  flex: 0 0 22rem;
  display: flex;
  flex-direction: column;
  background: #fff;
  border-left: 0.0625rem solid var(--wa-border);
  min-width: 0;
}
.wa-info[hidden] { display: none; }
@media (max-width: 75rem) {
  .wa-info {
    position: absolute;
    top: 0; right: 0; bottom: 0;
    z-index: 20;
    box-shadow: -0.5rem 0 1.5rem rgba(0,0,0,0.15);
  }
}
.wa-info__hdr {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0 0.875rem;
  min-height: 3.5rem;
  background: var(--wa-sidebar);
  border-bottom: 0.0625rem solid var(--wa-border);
  font-weight: 600;
}
.wa-info__body { flex: 1; overflow-y: auto; }
.wa-info__sec { padding: 0.875rem; border-bottom: 0.5rem solid var(--wa-sidebar); }
.wa-info__sec-title {
  font-size: 0.75rem;
  font-weight: 600;
  color: var(--wa-muted);
  text-transform: uppercase;
  letter-spacing: 0.04em;
  margin-bottom: 0.5rem;
  display: flex;
  align-items: center;
  gap: 0.375rem;
}
/* Top summary: one compact row (avatar · name/phone · lead label), expands to the full details. */
.wa-info__sec--who { padding: 0; }
.wa-who__sum {
  display: flex;
  align-items: center;
  gap: 0.625rem;
  padding: 0.625rem 0.875rem;
  cursor: pointer;
  list-style: none;
}
.wa-who__sum::-webkit-details-marker { display: none; }
.wa-who__sum:hover { background: var(--wa-sidebar); }
.wa-who__av {
  width: 2.5rem; height: 2.5rem; flex: 0 0 2.5rem;
  border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  color: #fff; font-size: 0.875rem; font-weight: 600;
  background: #cfd8dc;
}
.wa-who__txt { flex: 1; min-width: 0; }
.wa-who__name { font-weight: 600; font-size: 0.9375rem; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.wa-who__phone { color: var(--wa-muted); font-size: 0.75rem; font-variant-numeric: tabular-nums; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.wa-who__label {
  display: inline-flex; align-items: center; gap: 0.3125rem;
  max-width: 8.5rem;
  padding: 0.125rem 0.5rem;
  border: 0.0625rem solid var(--wa-border);
  border-radius: 0.75rem;
  font-size: 0.6875rem;
  white-space: nowrap;
  flex: 0 1 auto;
  min-width: 0;
}
.wa-who__label span:last-child { overflow: hidden; text-overflow: ellipsis; }
.wa-who__label--none { color: var(--wa-muted-2); }
.wa-who__chev { color: var(--wa-muted-2); transition: transform 0.15s ease; flex: 0 0 auto; }
.wa-who[open] .wa-who__chev { transform: rotate(180deg); }
.wa-who__detail { padding: 0 0.875rem 0.75rem; }
.wa-who__detail .wa-kv { margin-top: 0; }
.wa-kv { display: grid; grid-template-columns: 6.5rem 1fr; gap: 0.3125rem 0.5rem; font-size: 0.8125rem; margin-top: 0.625rem; }
.wa-kv dt { color: var(--wa-muted); }
.wa-kv dd { margin: 0; overflow-wrap: anywhere; font-variant-numeric: tabular-nums; }

.wa-lead {
  border: 0.0625rem solid var(--wa-border);
  border-radius: 0.5rem;
  padding: 0.625rem 0.75rem;
  margin-bottom: 0.5rem;
  font-size: 0.8125rem;
}
.wa-lead__top { display: flex; align-items: baseline; gap: 0.5rem; }
.wa-lead__name { font-weight: 600; color: #111b21; text-decoration: none; flex: 1; min-width: 0; overflow-wrap: anywhere; }
.wa-lead__name:hover { text-decoration: underline; }
.wa-lead__id { color: var(--wa-muted-2); font-size: 0.75rem; font-variant-numeric: tabular-nums; }
.wa-lead__stage { display: inline-flex; align-items: center; gap: 0.3125rem; font-size: 0.75rem; margin-top: 0.25rem; }
.wa-lead__dot { width: 0.5rem; height: 0.5rem; border-radius: 50%; background: #9aa5ad; }
.wa-lead__meta { color: var(--wa-muted); font-size: 0.75rem; margin-top: 0.25rem; line-height: 1.45; }
.wa-lead__how { font-size: 0.6875rem; color: var(--wa-muted); border: 0.0625rem solid var(--wa-border); border-radius: 0.25rem; padding: 0 0.3125rem; }
.wa-lead__actions { margin-top: 0.5rem; display: flex; gap: 0.375rem; }
.wa-btn__icon { width: 0.875rem; height: 0.875rem; vertical-align: -0.125rem; margin-right: 0.25rem; }
.wa-btn--sm { padding: 0.25rem 0.625rem; font-size: 0.75rem; }
.wa-note { font-size: 0.75rem; color: var(--wa-muted); line-height: 1.45; }
/* WhatsApp labels in the contact panel — ticking one sets it on the chat in WhatsApp. */
.wa-wlabels { display: grid; grid-template-columns: 1fr 1fr; gap: 0.25rem 0.75rem; }
.wa-wlabels__row {
  display: flex; align-items: center; gap: 0.375rem;
  font-size: 0.8125rem; min-width: 0; cursor: pointer;
}
.wa-wlabels__row span:last-child { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.wa-wlabels__row input { margin: 0; accent-color: var(--wa-brand); flex: 0 0 auto; }
.wa-wlabels__row .wa-label-chip__dot { width: 0.5rem; height: 0.5rem; margin: 0; }
.wa-wlabels__bar { display: flex; align-items: center; gap: 0.5rem; margin-top: 0.625rem; }
.wa-wlabels__bar .wa-btn:disabled { opacity: 0.45; cursor: default; }
/* View mode: just the chat's labels, inline, with Change on the same line. */
.wa-wlabels__line { display: flex; align-items: center; flex-wrap: wrap; gap: 0.375rem 0.75rem; }
.wa-wlabels { flex: 1 1 100%; }
.wa-wlabels--view { display: flex; flex-wrap: wrap; gap: 0.25rem 0.875rem; flex: 0 1 auto; }
.wa-wlabels--view .wa-wlabels__row { cursor: default; }
.wa-wlabels--view input { display: none; }
.wa-wlabels__row[hidden], .wa-wlabels[hidden], .wa-wlabels__bar[hidden], .wa-wlabels__edit[hidden], .wa-btn[hidden] { display: none; }
.wa-mk { margin-top: 0.5rem; }
.wa-mk__form { display: flex; align-items: center; flex-wrap: wrap; gap: 0.375rem; margin-top: 0.375rem; }
.wa-mk__name { flex: 1 1 9rem; min-width: 0; }
.wa-mk__swatches { display: flex; flex-wrap: wrap; gap: 0.25rem; flex: 1 1 100%; }
.wa-mk__sw {
  width: 1rem; height: 1rem; border-radius: 50%; border: 1px solid rgba(0,0,0,0.15);
  padding: 0; cursor: pointer; flex: 0 0 auto;
}
.wa-mk__sw[aria-pressed="true"] { outline: 2px solid var(--wa-brand); outline-offset: 2px; }
.wa-mk[hidden], .wa-mk__form[hidden] { display: none; }
.wa-wlabels__edit { flex: 0 0 auto; margin-left: auto; }
.wa-note--warn { color: #8a5a00; }
/* Working card for a connected lead — edit stage, owner, follow-up, notes in place. */
.wa-lead--work { padding: 0.75rem; }
.wa-lead__flags { display: flex; flex-wrap: wrap; gap: 0.25rem; margin-top: 0.375rem; }
.wa-flag {
  font-size: 0.6875rem;
  padding: 0 0.375rem;
  border-radius: 0.25rem;
  background: var(--wa-sidebar);
  color: #3b4a54;
  line-height: 1.25rem;
}
.wa-flag--warn { background: #fdecea; color: #b42318; }
.wa-flag--ok { background: var(--wa-brand-tint); color: #067a5f; }
.wa-lead__form { display: grid; grid-template-columns: 1fr 1fr; gap: 0.5rem; margin-top: 0.625rem; }
.wa-lead__form--full { grid-column: 1 / -1; }
.wa-lead__form label { display: block; font-size: 0.6875rem; color: var(--wa-muted); margin-bottom: 0.125rem; }
.wa-inp {
  width: 100%;
  border: 0.0625rem solid var(--wa-border);
  border-radius: 0.375rem;
  padding: 0.3125rem 0.375rem;
  font-size: 0.75rem;
  font-family: inherit;
  background: #fff;
  color: #111b21;
  outline: none;
}
.wa-inp:focus { border-color: var(--wa-brand); }
.wa-inp--overdue { border-color: #f04a4a; color: #b42318; }
.wa-lead__facts { display: grid; grid-template-columns: 5.5rem 1fr; gap: 0.1875rem 0.5rem; font-size: 0.75rem; margin: 0.625rem 0 0; }
.wa-lead__facts dt { color: var(--wa-muted); }
.wa-lead__facts dd { margin: 0; overflow-wrap: anywhere; }
.wa-lead__block { margin-top: 0.625rem; font-size: 0.75rem; }
.wa-lead__block > summary { cursor: pointer; color: var(--wa-muted); font-weight: 600; }
.wa-lead__block p { margin: 0.25rem 0 0; white-space: pre-wrap; color: #3b4a54; line-height: 1.45; }
.wa-actlog { list-style: none; margin: 0.375rem 0 0; padding: 0; }
.wa-actlog li { padding: 0.3125rem 0; border-top: 0.0625rem solid var(--wa-border); }
.wa-actlog__meta { font-size: 0.6875rem; color: var(--wa-muted); }
.wa-actlog__body { color: #3b4a54; overflow-wrap: anywhere; }
.wa-lead__note { display: flex; gap: 0.375rem; margin-top: 0.5rem; }
.wa-lead__note .wa-inp { flex: 1; }
.wa-lead__msg { font-size: 0.6875rem; margin-top: 0.375rem; min-height: 0; }
.wa-lead__msg--err { color: #b42318; }
.wa-lead__msg--ok { color: #067a5f; }
.wa-lead__foot { display: flex; gap: 0.375rem; margin-top: 0.625rem; flex-wrap: wrap; }
.wa-lead__foot a { text-decoration: none; }
.wa-lead__actions { flex-wrap: wrap; }
.wa-lead__label-inp { flex: 1; min-width: 8rem; }
.wa-nums { list-style: none; margin: 0.5rem 0 0; padding: 0; font-size: 0.75rem; }
.wa-nums__row { display: flex; flex-wrap: wrap; align-items: center; gap: 0.25rem 0.5rem; padding: 0.25rem 0; border-top: 0.0625rem dashed var(--wa-border); }
.wa-nums__label { font-weight: 600; min-width: 4.5rem; }
.wa-nums__id { font-variant-numeric: tabular-nums; color: #3b4a54; }
.wa-nums__acct { color: var(--wa-muted); border: 0.0625rem solid var(--wa-border); border-radius: 0.25rem; padding: 0 0.3125rem; }
.wa-nums__open { flex: none; padding: 0.0625rem 0.5rem; font-size: 0.6875rem; line-height: 1.4; }
.wa-lead-search { margin-top: 0.5rem; }
/* Platform account card — the user / business on this number. Reuses the lead card frame. */
.wa-acct__user { color: var(--wa-muted-2); font-size: 0.75rem; overflow-wrap: anywhere; }
/* Account card closed to one line; the name gives way (ellipsis) before the flags do. */
.wa-acct__name { flex: 0 1 auto; min-width: 0; font-weight: 600; color: #111b21; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.wa-acct--open .wa-acct__name { white-space: normal; overflow-wrap: anywhere; }
.wa-acct__sub { margin-top: 0.5rem; padding-top: 0.5rem; border-top: 0.0625rem dashed var(--wa-border); font-size: 0.75rem; }
.wa-acct__subtop { display: flex; align-items: center; flex-wrap: wrap; gap: 0.25rem 0.5rem; }
.wa-acct__subname { font-weight: 600; color: #111b21; overflow-wrap: anywhere; }
.wa-acct__sub .wa-lead__meta { margin-top: 0.125rem; }
.wa-acct__sub .wa-lead__foot { margin-top: 0.375rem; }
/* Account + labels strips: minimal height — tight padding and a hairline
   between them instead of the grey band. */
.wa-info__sec--tight { padding: 0.5rem 0.875rem; }
.wa-info__sec--tight .wa-info__sec-title { margin-bottom: 0.25rem; }
.wa-info__sec--joined { border-bottom: 0.0625rem solid var(--wa-border); }
.wa-info__sec-title[hidden] { display: none; }
/* Account: no heading. Line 1 = user icon, name, roles, Verified / Verification;
   then one indented line per business / driver record with its Open button.
   The caret opens the details underneath and frames the card. */
.wa-acct { font-size: 0.8125rem; }
.wa-acct + .wa-acct { margin-top: 0.5rem; }
.wa-acct--open {
  border: 0.0625rem solid var(--wa-border);
  border-radius: 0.5rem;
  padding: 0.375rem 0.625rem 0.5rem;
}
.wa-acct__line, .wa-acct__row { display: flex; align-items: center; gap: 0.375rem; min-width: 0; }
.wa-acct__row { margin-top: 0.375rem; padding-left: 0.875rem; }
.wa-acct__toggle {
  display: inline-flex; align-items: center; gap: 0.375rem;
  flex: 0 1 auto; min-width: 2.75rem;
  padding: 0; border: 0; background: none;
  font: inherit; color: inherit; text-align: left; cursor: pointer;
}
.wa-acct__toggle::before { content: '\25B8'; flex: none; color: var(--wa-muted); font-size: 0.75rem; }
.wa-acct__toggle[aria-expanded="true"]::before { content: '\25BE'; }
.wa-acct__toggle:hover .wa-acct__name { text-decoration: underline; }
.wa-acct__icon { display: inline-flex; flex: none; color: var(--wa-muted); }
.wa-acct__icon svg { width: 1rem; height: 1rem; }
.wa-acct__rowname { flex: 0 1 auto; min-width: 0; color: #3b4a54; font-weight: 500; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.wa-acct__line .wa-flag, .wa-acct__row .wa-flag { flex: none; }
.wa-acct__end { flex: none; margin-left: auto; }
a.wa-acct__end { text-decoration: none; padding: 0.125rem 0.5rem; }
.wa-acct__body { margin-top: 0.5rem; }
.wa-acct__body[hidden] { display: none; }
.wa-acct__none { display: flex; align-items: center; gap: 0.375rem; }
.wa-lead-search .wa-search { margin-bottom: 0.375rem; }

.wa-tabs { display: flex; flex-wrap: wrap; gap: 0.25rem; margin-bottom: 0.625rem; }
.wa-tab {
  border: 0.0625rem solid var(--wa-border);
  background: #fff;
  color: var(--wa-muted);
  border-radius: 1rem;
  padding: 0.25rem 0.625rem;
  font-size: 0.75rem;
  cursor: pointer;
}
.wa-tab:hover { background: var(--wa-sidebar); }
.wa-tab--on { background: var(--wa-brand-tint); border-color: var(--wa-brand); color: var(--wa-brand); font-weight: 600; }
.wa-tab__n { font-variant-numeric: tabular-nums; opacity: 0.8; margin-left: 0.1875rem; }
.wa-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 0.25rem; }
.wa-grid__cell {
  position: relative;
  aspect-ratio: 1;
  background: var(--wa-sidebar);
  border-radius: 0.25rem;
  overflow: hidden;
  display: block;
}
.wa-grid__cell img, .wa-grid__cell video { width: 100%; height: 100%; object-fit: cover; display: block; }
.wa-grid__play {
  position: absolute; inset: 0;
  display: flex; align-items: center; justify-content: center;
  color: #fff; font-size: 1.25rem; text-shadow: 0 0 0.375rem rgba(0,0,0,0.6);
  pointer-events: none;
}
.wa-grid__cell--broken::after {
  content: "unavailable";
  position: absolute; inset: 0;
  display: flex; align-items: center; justify-content: center;
  font-size: 0.6875rem; color: var(--wa-muted-2);
}
.wa-mlist { display: flex; flex-direction: column; gap: 0.375rem; }
.wa-mitem { border-bottom: 0.0625rem solid var(--wa-border); padding-bottom: 0.375rem; font-size: 0.8125rem; }
.wa-mitem__meta { font-size: 0.6875rem; color: var(--wa-muted); margin-bottom: 0.1875rem; }
.wa-mitem a { color: #027eb5; overflow-wrap: anywhere; }
.wa-mitem audio { width: 100%; height: 2.25rem; }
.wa-mitem__text { color: #3b4a54; font-size: 0.75rem; overflow-wrap: anywhere; margin-top: 0.1875rem; }
.wa-more { margin-top: 0.625rem; width: 100%; }
/* Media viewer: photos and videos open large in a popup instead of a new tab. */
.wa-lb {
  border: 0; padding: 0; margin: 0;
  width: 100vw; height: 100vh; max-width: 100vw; max-height: 100vh;
  background: rgba(11,20,26,0.94);
  color: #e9edef;
}
.wa-lb::backdrop { background: rgba(11,20,26,0.6); }
.wa-lb[open] { display: flex; flex-direction: column; }
.wa-lb__bar { display: flex; align-items: center; gap: 0.75rem; padding: 0.625rem 1rem; font-size: 0.8125rem; }
.wa-lb__meta { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: #aebac1; }
.wa-lb__count { color: #aebac1; font-variant-numeric: tabular-nums; }
.wa-lb__btn {
  border: 0; background: transparent; color: #e9edef; cursor: pointer;
  font-size: 0.8125rem; text-decoration: none; padding: 0.375rem 0.625rem; border-radius: 0.375rem;
}
.wa-lb__btn:hover { background: rgba(255,255,255,0.1); }
.wa-lb__close { font-size: 1.5rem; line-height: 1; }
.wa-lb__body { flex: 1; min-height: 0; display: flex; }
.wa-lb__stage { flex: 1; min-height: 0; min-width: 0; display: flex; align-items: center; justify-content: center; position: relative; padding: 0 3.5rem 1rem; }
.wa-lb__stage img, .wa-lb__stage video { max-width: 100%; max-height: 100%; object-fit: contain; border-radius: 0.25rem; }
.wa-lb__caption { text-align: center; font-size: 0.8125rem; color: #d1d7db; padding: 0 1rem 1rem; white-space: pre-wrap; }
.wa-lb__nav {
  position: absolute; top: 50%; transform: translateY(-50%);
  width: 2.75rem; height: 2.75rem; border-radius: 50%;
  border: 0; background: rgba(255,255,255,0.12); color: #fff; font-size: 1.25rem; cursor: pointer;
}
.wa-lb__nav:hover { background: rgba(255,255,255,0.22); }
.wa-lb__nav[hidden] { display: none; }
.wa-lb__nav--prev { left: 0.75rem; }
.wa-lb__nav--next { right: 0.75rem; }
.wa-lb__missing { color: #aebac1; }
.wa-lb__save { display: inline-flex; align-items: center; gap: 0.375rem; }
.wa-lb__save[hidden] { display: none; }
.wa-lb__sel {
  background: rgba(255,255,255,0.08); color: #e9edef;
  border: 0.0625rem solid rgba(255,255,255,0.2); border-radius: 0.375rem;
  padding: 0.25rem 0.375rem; font: inherit; font-size: 0.75rem; max-width: 12rem;
}
.wa-lb__sel option { color: #111b21; }
/* Driver-profile document in the viewer: number / expiry / image check beside the scan. */
.wa-lb__doc {
  flex: none; width: 20rem; overflow-y: auto; padding: 0 1rem 1rem;
  border-left: 0.0625rem solid rgba(255,255,255,0.12);
  display: flex; flex-direction: column; gap: 0.625rem; font-size: 0.8125rem;
}
.wa-lb__doc[hidden], .wa-lb__doc-fields[hidden], .wa-lb__err[hidden], .wa-lb__note[hidden], .wa-lb__btn[hidden] { display: none; }
.wa-lb__doc-title { font-weight: 600; font-size: 0.9375rem; }
.wa-lb__doc-fields { display: grid; grid-template-columns: 1fr 1fr; gap: 0.5rem; }
.wa-lb__lbl { display: flex; flex-direction: column; gap: 0.25rem; min-width: 0; font-size: 0.6875rem; color: #8696a0; text-transform: uppercase; letter-spacing: 0.04em; }
.wa-lb__inp {
  min-width: 0; background: rgba(255,255,255,0.08); color: #e9edef; color-scheme: dark;
  border: 0.0625rem solid rgba(255,255,255,0.2); border-radius: 0.375rem;
  padding: 0.375rem 0.5rem; font: inherit; font-size: 0.8125rem; text-transform: none; letter-spacing: normal;
}
.wa-lb__inp:focus { outline: none; border-color: var(--wa-brand); }
.wa-lb__inp[readonly] { opacity: 0.7; }
.wa-lb__btn--line { border: 0.0625rem solid rgba(255,255,255,0.25); }
.wa-lb__btn--primary { background: var(--wa-brand); color: #fff; }
.wa-lb__btn--primary:hover { background: var(--wa-brand-hover); }
.wa-lb__btn:disabled { opacity: 0.5; cursor: wait; }
#wa-lb-doc-useai { align-self: flex-start; }
.wa-lb__facts { margin: 0; display: grid; grid-template-columns: auto 1fr; gap: 0.3125rem 0.75rem; }
.wa-lb__facts dt { font-size: 0.6875rem; color: #8696a0; text-transform: uppercase; letter-spacing: 0.04em; padding-top: 0.0625rem; }
.wa-lb__facts dd { margin: 0; color: #e9edef; overflow-wrap: anywhere; }
.wa-lb__err { margin: 0; color: #f15c6d; font-weight: 600; }
.wa-lb__note { margin: 0; color: #aebac1; font-size: 0.75rem; }
.wa-lb__doc-acts { display: flex; flex-wrap: wrap; gap: 0.375rem; }
@media (max-width: 48rem) {
  .wa-lb__body { flex-direction: column; }
  .wa-lb__stage { padding: 0 3.5rem 0.5rem; }
  .wa-lb__doc { width: auto; max-height: 45vh; border-left: 0; border-top: 0.0625rem solid rgba(255,255,255,0.12); padding-top: 0.75rem; }
}
/* Driver lead: documents on the driver's profile, against the application rule. */
.wa-docs__grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(6.5rem, 1fr)); gap: 0.375rem; margin-top: 0.375rem; }
.wa-docs__tile { border: 0.0625rem solid var(--wa-border); border-radius: 0.375rem; padding: 0.3125rem; min-width: 0; }
.wa-docs__tile--missing { border-style: dashed; }
.wa-docs__thumbs { display: flex; gap: 0.25rem; height: 3.5rem; }
.wa-docs__thumb { flex: 1; min-width: 0; cursor: zoom-in; }
.wa-docs__thumb img { width: 100%; height: 100%; object-fit: cover; border-radius: 0.25rem; display: block; background: var(--wa-sidebar); }
.wa-docs__empty {
  flex: 1; display: flex; align-items: center; justify-content: center;
  background: var(--wa-sidebar); border-radius: 0.25rem; color: var(--wa-muted); font-size: 0.6875rem;
}
.wa-docs__name { font-weight: 600; margin-top: 0.25rem; color: #111b21; }
.wa-docs__sub { color: var(--wa-muted); font-size: 0.6875rem; overflow-wrap: anywhere; }
.wa-docs__sub--bad { color: #b42318; }
.wa-docs__open { font-size: 0.6875rem; color: #027eb5; text-decoration: none; }
.wa-docs .wa-flag { font-weight: 400; margin-left: 0.25rem; }
.wa-docs__add { margin-top: 0.25rem; width: 100%; }
.wa-pick { width: min(30rem, calc(100vw - 2rem)); }
.wa-pick .wa-modal__body { padding: 0.75rem; max-height: 70vh; overflow-y: auto; }
.wa-pick__side { display: flex; align-items: center; gap: 0.5rem; font-size: 0.75rem; color: var(--wa-muted); margin-bottom: 0.5rem; }
.wa-pick__side[hidden] { display: none; }
.wa-pick__side .wa-inp { width: auto; }
.wa-pick__grid .wa-grid__cell { border: 0; padding: 0; cursor: pointer; }
.wa-pick__grid .wa-grid__cell:hover, .wa-pick__grid .wa-grid__cell:focus-visible { outline: 0.1875rem solid var(--wa-brand); outline-offset: -0.1875rem; }
.wa-pick__grid .wa-grid__cell:disabled { opacity: 0.5; cursor: wait; }
.wa-pick__msg { margin-top: 0.5rem; }
.wa-pick #wa-pick-more { margin-top: 0.5rem; }
.wa-media-img, .wa-grid__cell { cursor: zoom-in; }
.wa-sess__dot { display: inline-block; width: 0.4375rem; height: 0.4375rem; border-radius: 50%; margin-right: 0.25rem; background: #b9b9b9; }
.wa-sess__dot--on { background: var(--wa-brand); }
</style>
</head>
<body>
<div class="wa-app">
  <aside class="wa-side">
    <div class="wa-side__hdr">
      <span class="wa-chip" id="wa-sess-chip" title="%SESSION%">%SESSION_LABEL%</span>
      <span class="wa-side__phone" id="wa-phone-text">agent inbox</span>
      <span class="wa-side__spacer"></span>
      <button class="wa-gear" id="wa-sess-open" type="button" title="Switch WhatsApp number" aria-label="Sessions" aria-haspopup="dialog"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg></button>
    </div>
    <dialog class="wa-modal" id="wa-sess-modal" aria-label="WhatsApp sessions">
      <div class="wa-modal__hdr">Sessions<button class="wa-modal__close" id="wa-sess-close" type="button" aria-label="Close">&times;</button></div>
      <div class="wa-modal__body">%SESSION_TABS%</div>
      %SESSION_HEALTH_LINK%
    </dialog>
    <div class="wa-side__filters">
      <div class="wa-side__row">
        <input class="wa-search" id="wa-search" placeholder="Search or new number…" autocomplete="off">
        <select class="wa-select wa-select--type" id="wa-type-filter" autocomplete="off">
          <option value="all">All chats</option>
          <option value="dm" selected>Persons</option>
          <option value="group">Groups</option>
          <option value="archived">Archived</option>
        </select>
      </div>
      <div class="wa-side__row">
        <button class="wa-qlabel" type="button" data-label-name="driver" aria-pressed="false" hidden>Driver</button>
        <button class="wa-qlabel" type="button" data-label-name="leads to follow" aria-pressed="false" hidden>Leads to follow</button>
        <select class="wa-select" id="wa-label-filter">
          <option value="">All labels</option>
        </select>
      </div>
    </div>
    <div class="wa-list" id="wa-list">
      <div class="wa-empty">Loading chats…</div>
    </div>
  </aside>

  <section class="wa-conv">
    <div class="wa-conv__hdr">
      <div class="wa-avatar" id="wa-conv-avatar">--</div>
      <div>
        <div class="wa-conv__name" id="wa-conv-name">Select a chat</div>
        <div class="wa-conv__sub" id="wa-conv-sub"></div>
      </div>
      <div class="wa-conv__spacer"></div>
      <button class="wa-btn wa-btn--ghost" id="wa-chat-more" type="button" title="Mark unread, archive" aria-label="Chat actions" aria-haspopup="menu" disabled>⋮ Chat</button>
      <button class="wa-btn wa-btn--ghost" id="wa-resync" type="button" title="Resync from WAHA">↻ Resync</button>
      <button class="wa-btn wa-btn--ghost" id="wa-info-toggle" type="button" title="Contact info, leads &amp; media" aria-controls="wa-info" disabled><svg class="wa-btn__icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><circle cx="12" cy="12" r="10"/><path d="M12 16v-4M12 8h.01"/></svg>Info</button>
    </div>
    <div class="wa-msgs" id="wa-msgs">
      <div class="wa-empty">No chat selected.</div>
    </div>
    <div class="wa-err" id="wa-err"></div>
    <div class="wa-replybar" id="wa-replybar" hidden>
      <div class="wa-quote" id="wa-replybar-quote"></div>
      <button class="wa-replybar__close" id="wa-replybar-close" type="button" title="Cancel reply" aria-label="Cancel reply">&times;</button>
    </div>
    <div class="wa-attachbar" id="wa-attachbar" hidden>
      <img class="wa-attachbar__thumb" id="wa-attach-thumb" alt="" hidden>
      <div class="wa-attachbar__icon" id="wa-attach-icon" aria-hidden="true" hidden>📄</div>
      <div class="wa-attachbar__info">
        <span class="wa-attachbar__name" id="wa-attach-name"></span>
        <span class="wa-attachbar__meta" id="wa-attach-meta"></span>
      </div>
      <button class="wa-replybar__close" id="wa-attach-close" type="button" title="Remove attachment" aria-label="Remove attachment">&times;</button>
    </div>
    <div class="wa-comp">
      <button class="wa-comp__icon" id="wa-comp-attach" type="button" title="Attach a photo, video or file (or paste / drop one)" aria-label="Attach a file" disabled><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48"/></svg></button>
      <input type="file" id="wa-comp-file" hidden>
      <textarea class="wa-comp__ta" id="wa-comp-ta" rows="1" placeholder="Type a message" disabled></textarea>
      <button class="wa-comp__icon" id="wa-comp-mic" type="button" title="Record a voice note" aria-label="Record a voice note" disabled><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="9" y="2" width="6" height="12" rx="3"/><path d="M5 10a7 7 0 0 0 14 0M12 17v5M8 22h8"/></svg></button>
      <button class="wa-comp__send" id="wa-comp-send" type="button" disabled>Send</button>
      <div class="wa-rec" id="wa-rec" hidden>
        <span class="wa-rec__dot" aria-hidden="true"></span>
        <span class="wa-rec__time" id="wa-rec-time">0:00</span>
        <span class="wa-rec__hint">Recording voice note…</span>
        <button class="wa-btn wa-btn--ghost" id="wa-rec-cancel" type="button">Cancel</button>
        <button class="wa-btn" id="wa-rec-send" type="button">Send</button>
      </div>
    </div>
  </section>

  <aside class="wa-info" id="wa-info" aria-label="Contact info" hidden>
    <div class="wa-info__hdr">
      <span>Contact info</span>
      <button class="wa-modal__close" id="wa-info-close" type="button" aria-label="Close panel">&times;</button>
    </div>
    <div class="wa-info__body">
      <section class="wa-info__sec wa-info__sec--who" id="wa-info-who"></section>
      <section class="wa-info__sec wa-info__sec--tight wa-info__sec--joined" id="wa-info-accounts" hidden></section>
      <section class="wa-info__sec wa-info__sec--tight" id="wa-info-labels" hidden></section>
      <section class="wa-info__sec" id="wa-info-leads"></section>
      <section class="wa-info__sec">
        <div class="wa-info__sec-title">Media, links &amp; docs</div>
        <div class="wa-tabs" id="wa-media-tabs" role="tablist"></div>
        <div id="wa-media-body"></div>
      </section>
    </div>
  </aside>
</div>

<datalist id="wa-label-options">
  <option value="Owner"></option><option value="Office"></option><option value="Manager"></option>
  <option value="Accounts"></option><option value="Driver"></option><option value="Other"></option>
</datalist>
<dialog class="wa-lb" id="wa-lb" aria-label="Media viewer">
  <div class="wa-lb__bar">
    <span class="wa-lb__meta" id="wa-lb-meta"></span>
    <span class="wa-lb__count" id="wa-lb-count"></span>
    <span class="wa-lb__save" id="wa-lb-save" hidden>
      <select class="wa-lb__sel" id="wa-lb-save-type" aria-label="Save as driver document"></select>
      <button class="wa-lb__btn" id="wa-lb-save-btn" type="button">Save to driver file</button>
    </span>
    <a class="wa-lb__btn" id="wa-lb-dl" href="#" download>Download</a>
    <button class="wa-lb__btn wa-lb__close" id="wa-lb-close" type="button" aria-label="Close">&times;</button>
  </div>
  <div class="wa-lb__body">
    <div class="wa-lb__stage" id="wa-lb-stage">
      <button class="wa-lb__nav wa-lb__nav--prev" id="wa-lb-prev" type="button" aria-label="Previous">&#8249;</button>
      <button class="wa-lb__nav wa-lb__nav--next" id="wa-lb-next" type="button" aria-label="Next">&#8250;</button>
    </div>
    <!-- A driver-profile document photo: the same number / expiry / image-check
         panel as the CRM document popup, posting to the same workforce endpoints. -->
    <aside class="wa-lb__doc" id="wa-lb-doc" aria-label="Document details" hidden>
      <div class="wa-lb__doc-title" id="wa-lb-doc-title">Document</div>
      <div class="wa-lb__doc-fields" id="wa-lb-doc-fields">
        <label class="wa-lb__lbl">Number<input class="wa-lb__inp" id="wa-lb-doc-no" maxlength="100" autocomplete="off"></label>
        <label class="wa-lb__lbl">Expiry<input class="wa-lb__inp" id="wa-lb-doc-exp" type="date"></label>
      </div>
      <button class="wa-lb__btn wa-lb__btn--line" id="wa-lb-doc-useai" type="button" hidden>Use values from image</button>
      <dl class="wa-lb__facts" id="wa-lb-doc-facts"></dl>
      <p class="wa-lb__err" id="wa-lb-doc-err" hidden></p>
      <p class="wa-lb__note" id="wa-lb-doc-ro" hidden>Your account can view these details but not change them.</p>
      <div class="wa-lb__doc-acts">
        <button class="wa-lb__btn wa-lb__btn--line" id="wa-lb-doc-verify" type="button" hidden>Mark verified</button>
        <button class="wa-lb__btn wa-lb__btn--line" id="wa-lb-doc-unverify" type="button" hidden>Undo verification</button>
        <button class="wa-lb__btn wa-lb__btn--line" id="wa-lb-doc-submit" type="button" hidden>Submit</button>
        <button class="wa-lb__btn wa-lb__btn--primary" id="wa-lb-doc-submitverify" type="button" hidden>Submit &amp; verify</button>
      </div>
    </aside>
  </div>
  <div class="wa-lb__caption" id="wa-lb-caption"></div>
</dialog>
<dialog class="wa-modal wa-fwd" id="wa-fwd" aria-label="Forward message">
  <div class="wa-modal__hdr">Forward to…<button class="wa-modal__close" id="wa-fwd-close" type="button" aria-label="Close">&times;</button></div>
  <div class="wa-modal__body">
    <input class="wa-search wa-fwd__search" id="wa-fwd-q" placeholder="Search chats" autocomplete="off">
    <div class="wa-fwd__list" id="wa-fwd-list"></div>
  </div>
  <div class="wa-modal__foot wa-modal__foot--split"><span id="wa-fwd-count">Pick up to 5 chats</span><button class="wa-btn" id="wa-fwd-send" type="button" disabled>Forward</button></div>
</dialog>
<dialog class="wa-modal" id="wa-edit" aria-label="Edit message">
  <div class="wa-modal__hdr">Edit message<button class="wa-modal__close" id="wa-edit-close" type="button" aria-label="Close">&times;</button></div>
  <div class="wa-modal__body">
    <textarea class="wa-edit__ta" id="wa-edit-ta"></textarea>
    <div class="wa-edit__note">WhatsApp allows edits for 15 minutes after sending. The customer sees "Edited".</div>
  </div>
  <div class="wa-modal__foot wa-modal__foot--split"><span></span><button class="wa-btn" id="wa-edit-save" type="button">Save</button></div>
</dialog>
<dialog class="wa-modal wa-remind" id="wa-remind" aria-label="Send reminder">
  <div class="wa-modal__hdr"><span id="wa-remind-title">Send reminder</span><button class="wa-modal__close" id="wa-remind-close" type="button" aria-label="Close">&times;</button></div>
  <div class="wa-modal__body">
    <textarea class="wa-edit__ta wa-remind__ta" id="wa-remind-ta" aria-label="Reminder message"></textarea>
    <div class="wa-edit__note">Sends in this chat like a typed message — the same reminder the CRM lead page offers. Edit it first if needed.</div>
  </div>
  <div class="wa-modal__foot wa-modal__foot--split"><span></span><button class="wa-btn" id="wa-remind-send" type="button">Send</button></div>
</dialog>
<dialog class="wa-modal wa-pick" id="wa-pick" aria-label="Choose a photo from this chat">
  <div class="wa-modal__hdr"><span id="wa-pick-title">Choose a photo</span><button class="wa-modal__close" id="wa-pick-close" type="button" aria-label="Close">&times;</button></div>
  <div class="wa-modal__body">
    <label class="wa-pick__side" id="wa-pick-side-wrap">Side
      <select class="wa-inp" id="wa-pick-side"><option value="front">Front</option><option value="back">Back</option></select>
    </label>
    <div class="wa-grid wa-pick__grid" id="wa-pick-grid"></div>
    <div class="wa-note wa-pick__msg" id="wa-pick-msg"></div>
    <button class="wa-btn wa-btn--ghost wa-btn--sm" id="wa-pick-more" type="button" hidden>Load more</button>
  </div>
</dialog>

<script>
(function () {
  'use strict';

  var SESSION = '%SESSION%';

  // Session picker lives in a <dialog>; the gear in the sidebar header opens it.
  var sessModal = document.getElementById('wa-sess-modal');
  document.getElementById('wa-sess-open').addEventListener('click', function () { sessModal.showModal(); });
  document.getElementById('wa-sess-close').addEventListener('click', function () { sessModal.close(); });
  sessModal.addEventListener('click', function (e) { if (e.target === sessModal) sessModal.close(); });

  // Every call to our own endpoints must say which number it means — the DB
  // queries behind them are session-scoped.
  function wq(url) {
    return url + (url.indexOf('?') < 0 ? '?' : '&') + 'session=' + encodeURIComponent(SESSION);
  }

  var SENDER_PALETTE = ["#06cf9c","#7f66ff","#e542a3","#3fa9f5","#f5871f","#15c2c4","#b85cff","#f04a4a"];
  // WhatsApp labels are read in full from WAHA once a day, per number: label
  // ids are per-number, so one shared cache showed another number's labels.
  // v3: the map now comes from our server, filtered to what this login may see.
  // The rules token changes when marketing-only labels change, so a cached map
  // never outlives the rules it was filtered under.
  var LABEL_RULES = '%LABEL_RULES%';
  // Making a label changes the list for everyone on this number, so it is
  // marketing + super-admin only; the server gates it again on POST.
  var CAN_MAKE_LABEL = %CAN_MAKE_LABEL%;
  var LABEL_COLORS = %LABEL_COLORS%;
  var LABEL_CACHE_KEY = 'wa_label_map_v3:' + SESSION + ':' + LABEL_RULES;
  var LABEL_CACHE_TS_KEY = 'wa_label_map_v3_ts:' + SESSION + ':' + LABEL_RULES;
  var LABEL_TTL_MS = 24 * 60 * 60 * 1000;
  try {
    localStorage.removeItem('wa_label_map_v1'); localStorage.removeItem('wa_label_map_v1_ts');
    localStorage.removeItem('wa_label_map_v2:' + SESSION); localStorage.removeItem('wa_label_map_v2_ts:' + SESSION);
  } catch (e) { /* ignore */ }

  var noLabels = (function () {
    try { return new URLSearchParams(window.location.search).get('nolabels') === '1'; }
    catch (e) { return false; }
  })();

  var state = {
    chats: [],            // raw WAHA chats (accumulated across pages)
    chatIds: null,        // Set of c.id for O(1) dedupe across pages
    rendered: [],         // currently rendered list (after filters)
    activeChatId: null,
    activeChatName: null,
    activeIsGroup: false,
    labelMap: null,       // {label_id: Set(chat_id)}
    labels: [],           // [{id,name,color}]
    labelsByChat: null,   // {chat_id: [labelObj, ...]} — built from labelMap
    labelsLoaded: false,
    chatsOffset: 0,       // next batch starts here
    chatsLoading: false,
    chatsExhausted: false,
    // Per-conversation message pagination
    msgs: [],             // currently rendered messages, ASC by ts
    msgsOldestTs: 0,      // earliest ts in `msgs`; cursor for older pages
    msgsLiveOffsetSeen: 0,// WAHA offset already fetched for this chat
    msgsHasMore: true,    // false once we run out of older history
    msgsLoading: false,
  };
  var CHATS_PAGE_SIZE = 50;

  function $(id) { return document.getElementById(id); }
  function escapeHtml(s) {
    if (s == null) return '';
    return String(s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }
  function hashIdx(s, mod) {
    s = String(s || '');
    var h = 0;
    for (var i = 0; i < s.length; i++) {
      h = (h * 31 + s.charCodeAt(i)) | 0;
    }
    return Math.abs(h) % mod;
  }
  function senderColor(id) { return SENDER_PALETTE[hashIdx(id, SENDER_PALETTE.length)]; }

  function initials(name) {
    var n = String(name || '').trim();
    if (!n) return '·';
    var parts = n.split(/\s+/);
    if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
    return (parts[0][0] + parts[1][0]).toUpperCase();
  }
  function avatarColor(id) {
    return SENDER_PALETTE[hashIdx(id, SENDER_PALETTE.length)];
  }
  // Profile photos: our saved copy, lazy-loaded over the initials. A chat
  // without one is remembered so re-renders don't ask again.
  var avatarNone = {};
  // The chat list is rebuilt on every refresh; `reuse` moves the row's already
  // loaded <img> into the new row instead of making a fresh one, which would
  // drop back to the initials and reload — the flicker seen every 30s.
  var listPics = {};
  function addPhoto(node, chatId, reuse) {
    if (!chatId || avatarNone[chatId]) return;
    if (reuse && listPics[chatId]) { node.appendChild(listPics[chatId]); return; }
    var img = document.createElement('img');
    if (reuse) listPics[chatId] = img;
    img.className = 'wa-pic';
    img.alt = '';
    img.loading = 'lazy';
    img.decoding = 'async';
    img.addEventListener('error', function () { avatarNone[chatId] = true; delete listPics[chatId]; img.remove(); });
    img.src = wq('/waha/wa-chats/avatar/?chatId=' + encodeURIComponent(chatId));
    node.appendChild(img);
  }
  function clockOf(d) {
    var hh = d.getHours();
    var mm = d.getMinutes();
    var ampm = hh >= 12 ? 'pm' : 'am';
    hh = hh % 12; if (!hh) hh = 12;
    return hh + ':' + (mm < 10 ? '0' + mm : mm) + ' ' + ampm;
  }
  // The page's one timestamp, used by both the chat list and the message
  // bubbles. Every stamp carries how many whole days back it was — 0d today,
  // then 1d, 2d, 3d ... — counted on calendar days, not 24h blocks, and never
  // rolling over into months or years. Today is stamped 0d rather than left as
  // a bare clock so that no row is ever read as "just now" by default.
  function fmtShortTime(ts) {
    if (!ts) return '';
    try {
      var d = new Date(ts * 1000);
      var now = new Date();
      var startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate());
      var days = Math.floor((startOfToday - new Date(d.getFullYear(), d.getMonth(), d.getDate())) / 86400000);
      // A clock skew or a message stamped slightly ahead of us must not print '-1d'.
      if (days < 0) days = 0;
      return days + 'd ' + clockOf(d);
    } catch (e) { return ''; }
  }
  function chatIsGroup(id) { return String(id || '').endsWith('@g.us'); }

  // WhatsApp's own markup — *bold*, _italic_, ~strikethrough~, `mono` and
  // ```mono``` — plus clickable links, rendered the way WhatsApp renders it.
  // Built as DOM nodes and never as an HTML string: a message body is written
  // by whoever is on the other end, so innerHTML here would be a stored-XSS
  // hole. Everything user-supplied lands via textContent or .href, and .href
  // only ever holds a string that already matched http(s)://  or www.
  function richFind(text) {
    var best = null;
    function offer(index, length, kind, inner, href) {
      if (index < 0 || length <= 0) return;
      if (!best || index < best.index) {
        best = { index: index, length: length, kind: kind, inner: inner, href: href || '' };
      }
    }
    var m = /```([\s\S]+?)```/.exec(text);
    if (m) offer(m.index, m[0].length, 'mono', m[1]);
    m = /`([^`\n]+)`/.exec(text);
    if (m) offer(m.index, m[0].length, 'mono', m[1]);
    m = /\b(?:https?:\/\/|www\.)[^\s]+/i.exec(text);
    if (m) {
      // A full stop or bracket after a link belongs to the sentence, not the URL.
      var raw = m[0].replace(/[.,;:!?)\]}'"]+$/, '');
      offer(m.index, raw.length, 'link', raw,
            /^www\./i.test(raw) ? 'https://' + raw : raw);
    }
    m = /\*([^\s*](?:[^*]*[^\s*])?)\*/.exec(text);
    if (m) offer(m.index, m[0].length, 'strong', m[1]);
    m = /~([^\s~](?:[^~]*[^\s~])?)~/.exec(text);
    if (m) offer(m.index, m[0].length, 's', m[1]);
    // Underscores only outside a word, so order_number and file_name.pdf survive.
    m = /(^|[^A-Za-z0-9_])_([^\s_](?:[^_]*[^\s_])?)_(?![A-Za-z0-9_])/.exec(text);
    if (m) offer(m.index + m[1].length, m[0].length - m[1].length, 'em', m[2]);
    return best;
  }
  function appendRich(parent, text) {
    var rest = (text == null) ? '' : String(text);
    var guard = 0;
    while (rest && guard++ < 1000) {
      var hit = richFind(rest);
      if (!hit) break;
      if (hit.index > 0) parent.appendChild(document.createTextNode(rest.slice(0, hit.index)));
      if (hit.kind === 'link') {
        var a = document.createElement('a');
        a.className = 'wa-link';
        a.href = hit.href;
        a.target = '_blank';
        a.rel = 'noopener noreferrer';
        a.textContent = hit.inner;
        parent.appendChild(a);
      } else if (hit.kind === 'mono') {
        var code = document.createElement('code');
        code.className = 'wa-fmt-mono';
        code.textContent = hit.inner;   // WhatsApp does not format inside monospace
        parent.appendChild(code);
      } else {
        var el = document.createElement(hit.kind);
        appendRich(el, hit.inner);      // bold inside italic, links inside bold
        parent.appendChild(el);
      }
      rest = rest.slice(hit.index + hit.length);
    }
    if (rest) parent.appendChild(document.createTextNode(rest));
  }
  function richText(text) {
    var frag = document.createDocumentFragment();
    appendRich(frag, text);
    return frag;
  }

  var PREVIEW_TYPE_LABELS = {
    image: 'Photo', video: 'Video', ptt: 'Voice message', audio: 'Audio',
    document: 'Document', sticker: 'Sticker', location: 'Location',
    vcard: 'Contact', contact_card: 'Contact', revoked: 'Message deleted',
    call_log: 'Call',
  };
  // A media message has no body, so the row would otherwise read "You: " and
  // nothing else once the sender prefix goes on.
  function previewTypeLabel(type) {
    return PREVIEW_TYPE_LABELS[String(type || '').toLowerCase()] || '';
  }
  function vcardPreview(body) {
    var fn = String(body || '').match(/^FN:(.*)$/m);
    return fn && fn[1].trim() ? '👤 ' + fn[1].trim() : '';
  }
  // Who spoke last, for the preview line. Only groups need a name — in a 1:1
  // the other party is the chat itself, so WhatsApp labels our side only.
  function lastSenderName(lastMsg, chatId) {
    if (!lastMsg || lastMsg.fromMe || !chatIsGroup(chatId)) return '';
    var notify = ((lastMsg._data && lastMsg._data.notifyName) || '').trim();
    if (notify) return notify;
    var author = String(lastMsg.author || lastMsg.participant || '');
    // A @lid is device-relative, not a phone number — never print it as one.
    if (author.indexOf('@c.us') !== -1) return '+' + author.split('@')[0];
    return '';
  }

  // ---------- Chat list load + render ----------
  // append=true → fetch the NEXT page and append. append=false → reset, fetch first page.
  // The poll loop calls loadChats() (no append) every 30s to refresh the top of the list.
  function loadChats(append) {
    if (state.chatsLoading) return Promise.resolve();
    if (append && state.chatsExhausted) return Promise.resolve();
    var firstLoad = !append && state.chats.length === 0;
    if (firstLoad) {
      state.chatsOffset = 0;
      state.chatsExhausted = false;
      state.chatIds = new Set();
    } else if (!state.chatIds) {
      state.chatIds = new Set(state.chats.map(function (c) { return c.id; }));
    }
    state.chatsLoading = true;
    // append → next page; refresh poll → re-fetch first page (merge, don't reset).
    var fetchOffset = append ? state.chatsOffset : 0;
    // Through our server, not WAHA: it drops chats under a label this
    // login may not see. `fetched` is WAHA's page size before that filter.
    var url = wq('/waha/wa-chats/?chats=1&limit=' + CHATS_PAGE_SIZE + '&offset=' + fetchOffset);
    return fetch(url, { credentials: 'same-origin' })
      .then(function (r) { return r.json().catch(function () { return {}; }); })
      .then(function (data) {
        if (data && data.ok === false && data.error) showError(data.error);
        // A failed page (WAHA slow or down → 502/503/504) is not the end of the
        // list: it used to read as "0 fetched", mark the list exhausted, and
        // scrolling never loaded another chat until a page reload. Leave the
        // offset alone so the next scroll (or the 30s refresh) retries it.
        if (!data || data.ok !== true || typeof data.fetched !== 'number') {
          state.chatsLoading = false;
          if (append) retryChatPage();
          return;
        }
        state.chatsRetryMs = 0;
        state.chatsFailed = false;
        var list = Array.isArray(data.chats) ? data.chats : [];
        var fetched = data.fetched;
        // The first load is page one too — without this the first scroll
        // re-fetched page one, added nothing, and the list never grew again.
        if (append || firstLoad) {
          if (fetched < CHATS_PAGE_SIZE) state.chatsExhausted = true;
          state.chatsOffset += fetched;
        }
        var mapped = list.map(function (c) {
          var id = c.id && c.id._serialized ? c.id._serialized : (c.id || '');
          var lastMsg = c.lastMessage || {};
          var lastType = ((lastMsg._data && lastMsg._data.type) || lastMsg.type || '').toString().toLowerCase();
          // WAHA returns the literal string "Unknown number" for unsaved contacts.
          // Treat it the same as a missing name so we can fall back to the phone digits.
          var waName = (c.name || c.formattedTitle || c.pushname || '').trim();
          // WAHA also fills `name` with the formatted number ("+974 7402 4778")
          // for unsaved contacts — digits alone are not a name either.
          var hasRealName = !!waName && waName.toLowerCase() !== 'unknown number' && !/^[+\d\s().-]+$/.test(waName);
          var digits = (c.id && c.id.user) || String(id || '').split('@')[0] || '';
          var usableLabel = !!waName && waName.toLowerCase() !== 'unknown number';
          var displayName = usableLabel ? waName : (digits ? '+' + digits : String(id));
          var numberLabel = displayName;
          // Unsaved contact: title it with the name they set in WhatsApp, as the header does.
          var pushName = !hasRealName ? (pushNames[String(id)] || '') : '';
          var leadName = !hasRealName ? (leadNames[String(id)] || '') : '';
          // A connected CRM lead names the chat like a saved contact (no "~").
          if (leadName) displayName = leadName;
          else if (pushName) displayName = '~ ' + pushName;
          return {
            id: String(id || ''),
            name: displayName,
            number: numberLabel,
            pushName: pushName,
            leadName: leadName,
            hasName: hasRealName,
            // A contact card's body is the raw vCard (photo included) — show its name.
            lastMessage: /vcard/.test(lastType) ? vcardPreview(lastMsg.body) : (lastMsg.body || ''),
            lastType: lastType,
            lastFromMe: !!lastMsg.fromMe,
            lastSender: lastSenderName(lastMsg, id),
            timestamp: c.timestamp || lastMsg.timestamp || 0,
            pinned: !!c.pinned,
            archived: !!c.archived,
            // The open chat is being read on screen — no badge on it.
            unread: (String(id) === state.activeChatId && document.visibilityState === 'visible')
              ? 0 : (parseInt(c.unreadCount, 10) || 0),
          };
        }).filter(function (c) {
          if (!c.id) return false;
          // Hide rows whose only activity is a protocol notification (encryption setup)
          // when there's also no contact name and no body — pure inbox noise.
          var noisyType = c.lastType === 'e2e_notification' ||
                          c.lastType === 'notification' ||
                          c.lastType === 'notification_template' ||
                          c.lastType === 'protocol';
          if (noisyType && !c.hasName && !c.lastMessage) return false;
          return true;
        });
        if (append) {
          mapped.forEach(function (c) {
            if (!state.chatIds.has(c.id)) {
              state.chatIds.add(c.id);
              state.chats.push(c);
            }
          });
        } else if (state.chats.length === 0) {
          state.chats = mapped;
          state.chatIds = new Set(mapped.map(function (c) { return c.id; }));
        } else {
          // Polling refresh: merge first-page updates into existing chats so
          // scroll-loaded pages aren't discarded. New chats are prepended (sort
          // re-orders by timestamp anyway); known chats get fresh metadata.
          mapped.forEach(function (c) {
            if (state.chatIds.has(c.id)) {
              for (var i = 0; i < state.chats.length; i++) {
                if (state.chats[i].id === c.id) {
                  state.chats[i] = c;
                  break;
                }
              }
            } else {
              state.chatIds.add(c.id);
              state.chats.unshift(c);
            }
          });
        }
        state.chatsLoading = false;
        renderList();
        // Also after the 30s refresh: a scroll that landed while it was in
        // flight was dropped (chatsLoading), so pick it up now.
        setTimeout(fillChatList, 0);
        loadPushNames();
        // Bump timestamps from our DB if a webhook has seen a more recent
        // message than WAHA's chat.timestamp (WhatsApp Web cache often lags).
        return enrichChatTimes();
      })
      .catch(function () {
        state.chatsLoading = false;
        if (append) retryChatPage();
      });
  }
  // At the bottom of the list a further scroll fires no event, so a failed page
  // is retried on a timer (3s, 6s, 12s… max 30s) while the reader is still there.
  function retryChatPage() {
    state.chatsFailed = true;
    renderList();   // shows the Load more bar
    state.chatsRetryMs = Math.min((state.chatsRetryMs || 1500) * 2, 30000);
    setTimeout(fillChatList, state.chatsRetryMs);
  }
  function loadMoreBar() {
    var bar = el('div', 'wa-loadmore');
    bar.appendChild(el('span', 'wa-loadmore__msg', 'Couldn\u2019t load more chats.'));
    var btn = el('button', 'wa-btn wa-btn--ghost', 'Load more');
    btn.type = 'button';
    btn.id = 'wa-list-loadmore';
    btn.addEventListener('click', function () {
      btn.disabled = true;
      btn.textContent = 'Loading…';
      loadChats(true);
    });
    bar.appendChild(btn);
    return bar;
  }
  // WhatsApp names for unsaved contacts, from our saved contact directory
  // (the server makes no WhatsApp calls for this). Asked once per chat and
  // kept for the page's lifetime, so the 30s refresh reuses them.
  var pushNames = {};
  var leadNames = {};
  var pushAsked = {};
  function loadPushNames() {
    var ids = state.chats.filter(function (c) {
      return !c.hasName && !pushAsked[c.id] && /@(lid|c\.us)$/.test(c.id);
    }).map(function (c) { return c.id; }).slice(0, 80);
    if (!ids.length) return;
    ids.forEach(function (id) { pushAsked[id] = true; });
    fetch(wq('/waha/wa-chats/?names=1&ids=' + encodeURIComponent(ids.join(','))), { credentials: 'same-origin' })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (j) {
        if (!j || !j.ok) { ids.forEach(function (id) { delete pushAsked[id]; }); return; }
        var changed = false;
        var leads = j.leads || {};
        state.chats.forEach(function (c) {
          if (c.hasName) return;
          var n = j.names[c.id], ln = leads[c.id];
          if (n) pushNames[c.id] = n;
          if (ln) leadNames[c.id] = ln;
          var want = ln || (n ? '~ ' + n : '');
          if (want && c.name !== want) { c.pushName = n || c.pushName; c.leadName = ln || ''; c.name = want; changed = true; }
        });
        if (changed) renderList();
        loadPushNames();  // next batch, if the list is longer than one
      })
      .catch(function () { ids.forEach(function (id) { delete pushAsked[id]; }); });
  }

  function enrichChatTimes() {
    return fetch(wq('/waha/wa-chats/?chat_latest=1'), { credentials: 'same-origin' })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (j) {
        if (!j || !j.ok || !j.latest) return;
        var latest = j.latest;
        var changed = false;
        state.chats.forEach(function (c) {
          var digits = String(c.id).split('@')[0];
          var dbTs = latest[digits];
          if (dbTs && dbTs > (c.timestamp || 0)) {
            c.timestamp = dbTs;
            changed = true;
          }
        });
        if (changed) renderList();
      })
      .catch(function () { /* ignore */ });
  }

  // Server contact-directory lookup for the search box (see findContacts).
  var finder = { q: null, hits: [], messages: [], timer: null };

  function renderList() {
    var listEl = $('wa-list');
    var q = ($('wa-search').value || '').trim();
    var typeF = $('wa-type-filter').value;
    var labelF = $('wa-label-filter').value;

    var filtered = state.chats.slice();

    // One-to-one chats arrive as @c.us or (mostly, since WA's privacy change) @lid —
    // so "Persons" is anything that isn't a group, channel or broadcast list.
    // Archived chats leave the inbox as on the phone; a search still finds them.
    if (typeF === 'archived') filtered = filtered.filter(function (c) { return c.archived; });
    else if (!q) filtered = filtered.filter(function (c) { return !c.archived; });

    if (typeF === 'dm') filtered = filtered.filter(function (c) { return !/@(g\.us|newsletter|broadcast)$/.test(c.id); });
    else if (typeF === 'group') filtered = filtered.filter(function (c) { return c.id.endsWith('@g.us'); });

    if (labelF && state.labelMap && state.labelMap[labelF]) {
      var allowed = state.labelMap[labelF];
      filtered = filtered.filter(function (c) { return allowed.has ? allowed.has(c.id) : (allowed.indexOf(c.id) !== -1); });
    }

    if (q) {
      var qlc = q.toLowerCase();
      // Directory hits for this query: most chats are @lid ids that carry no
      // phone, so a number search only finds them through the server lookup.
      var hits = finder.q === q ? finder.hits : [];
      var hitIds = {};
      hits.forEach(function (h) { hitIds[h.chat_id] = h; if (h.alt_id) hitIds[h.alt_id] = h; });
      filtered = filtered.filter(function (c) {
        return (c.name && c.name.toLowerCase().indexOf(qlc) !== -1)
            || (c.number && c.number.toLowerCase().indexOf(qlc) !== -1)
            || (c.id && c.id.toLowerCase().indexOf(qlc) !== -1)
            || !!hitIds[c.id];
      });
      var shown = {};
      filtered.forEach(function (c) { var h = hitIds[c.id]; if (h) shown[h.phone] = true; });
      // Typed id filters (Persons / Groups / a label) still apply to these.
      if (typeF !== 'group' && !labelF) {
        hits.forEach(function (h) {
          if (shown[h.phone]) return;
          shown[h.phone] = true;
          filtered.push({
            id: h.chat_id,
            name: h.name || '+' + h.phone,
            number: '+' + h.phone,
            hasName: !!h.name,
            lastMessage: h.name ? '+' + h.phone : '',
            timestamp: 0,
          });
        });
      }

      if (/^\d{8,15}$/.test(q)) {
        var virtId = q + '@c.us';
        var hasMatch = filtered.some(function (c) { return c.id === virtId; })
          || hits.some(function (h) { return h.phone === q && shown[h.phone]; });
        if (!hasMatch) {
          scheduleNumberCheck(q);
          var nc = numCheck[q];
          filtered.unshift({
            id: virtId,
            name: 'New chat: ' + q,
            lastMessage: NUM_TEXT[nc ? nc.state : 'checking'],
            timestamp: 0,
            virtual: true,
            digits: q,
          });
        }
      }
    }

    // WhatsApp ordering: pinned first (preserving recency within pinned),
    // then everything else by timestamp desc. Virtual phone-search rows go to top.
    filtered.sort(function (a, b) {
      if (!!a.virtual !== !!b.virtual) return a.virtual ? -1 : 1;
      if (!!a.pinned  !== !!b.pinned)  return a.pinned  ? -1 : 1;
      return (b.timestamp || 0) - (a.timestamp || 0);
    });

    state.rendered = filtered;
    var msgHits = (q && finder.q === q && !labelF && typeF !== 'group') ? finder.messages : [];

    if (!filtered.length && !msgHits.length) {
      listEl.innerHTML = '<div class="wa-empty">No chats.</div>';
      if (state.chatsFailed && !state.chatsExhausted) listEl.appendChild(loadMoreBar());
      return;
    }

    var frag = document.createDocumentFragment();
    filtered.forEach(function (c) {
      var row = document.createElement('div');
      row.className = 'wa-row' + (c.virtual ? ' wa-row--virtual' : '');
      if (c.id === state.activeChatId) row.className += ' wa-row--active';
      row.dataset.chatId = c.id;
      row.dataset.chatName = c.name;

      var av = document.createElement('div');
      av.className = 'wa-avatar';
      av.style.background = avatarColor(c.id);
      av.textContent = initials(c.pushName || c.name);
      addPhoto(av, c.id, true);

      var body = document.createElement('div');
      body.className = 'wa-row__body';

      var top = document.createElement('div');
      top.className = 'wa-row__top';
      var nm = document.createElement('div');
      nm.className = 'wa-row__name';
      nm.textContent = c.name;
      var tm = document.createElement('div');
      tm.className = 'wa-row__time' + (c.unread ? ' wa-row__time--unread' : '');
      tm.textContent = fmtShortTime(c.timestamp);
      top.appendChild(nm); top.appendChild(tm);

      var pvLine = document.createElement('div');
      pvLine.className = 'wa-row__pv-line';
      var pv = document.createElement('div');
      pv.className = 'wa-row__preview';
      var pvText = c.lastMessage || previewTypeLabel(c.lastType);
      var pvWho = c.lastFromMe ? 'You' : (c.lastSender || '');
      if (pvText && pvWho) {
        var who = document.createElement('span');
        who.className = 'wa-row__pv-who';
        who.textContent = pvWho + ': ';
        pv.appendChild(who);
        pv.appendChild(document.createTextNode(pvText));
      } else {
        pv.textContent = pvText || (c.virtual ? 'Tap to start' : '');
      }
      pvLine.appendChild(pv);
      if (c.pinned) {
        var pin = document.createElement('span');
        pin.className = 'wa-row__pin';
        pin.textContent = '\u{1F4CC}'; // 📌
        pin.title = 'Pinned';
        pvLine.appendChild(pin);
      }
      if (c.archived && typeF !== 'archived') pvLine.appendChild(el('span', 'wa-row__tag', 'Archived'));
      if (c.unread > 0) {
        var bd = document.createElement('span');
        bd.className = 'wa-row__unread';
        bd.textContent = c.unread > 99 ? '99+' : String(c.unread);
        pvLine.appendChild(bd);
      } else if (c.unread < 0) {
        // Marked unread by hand: WhatsApp shows a dot with no count.
        var dot = el('span', 'wa-row__unread wa-row__unread--dot', '');
        dot.title = 'Marked as unread';
        pvLine.appendChild(dot);
      }
      body.appendChild(top); body.appendChild(pvLine);
      // WhatsApp labels sit on the second line, directly under the time.
      var chips = renderLabelChips(c.id);
      if (chips) body.appendChild(chips);
      row.appendChild(av); row.appendChild(body);
      row.addEventListener('click', function () {
        if (c.virtual) {
          var nc = numCheck[c.digits];
          if (nc && nc.state === 'no') { showError('+' + c.digits + ' is not on WhatsApp.'); return; }
          if (nc && nc.state === 'yes' && nc.chatId) { openChat(nc.chatId, '+' + c.digits, false); return; }
        }
        openChat(c.id, c.name, c.hasName);
      });

      frag.appendChild(row);
    });
    if (msgHits.length) frag.appendChild(renderMessageHits(msgHits));
    if (state.chatsFailed && !state.chatsExhausted) frag.appendChild(loadMoreBar());
    listEl.innerHTML = '';
    listEl.appendChild(frag);
  }

  // A message id's prefix names the chat (phone or lid copy); the tail is the message.
  function idTail(k) { return String(k || '').split('_').pop(); }

  // After a message-search click: once the chat's messages are drawn, scroll to
  // the hit — paging older history in until it shows up or we pass its time.
  function tryJump() {
    var j = state.jumpTo;
    if (!j || j.chatId !== state.activeChatId) return;
    var box = $('wa-msgs');
    var hit = null;
    state.msgs.some(function (m) {
      if ((j.tail && idTail(m.waha_id) === j.tail) || (j.id && m.id === j.id)) { hit = m; return true; }
      return false;
    });
    var row = hit && box.querySelector('.wa-msg[data-key="' + String(msgKey(hit)).replace(/"/g, '') + '"]');
    if (row) {
      state.jumpTo = null;
      row.scrollIntoView({ block: 'center' });
      row.classList.add('wa-msg--hit');
      setTimeout(function () { row.classList.remove('wa-msg--hit'); }, 2500);
      return;
    }
    var passed = state.msgsOldestTs && j.ts && state.msgsOldestTs < j.ts - 120;
    if (state.msgsHasMore && !passed && j.pages++ < 15) {
      loadOlderMessages();
    } else {
      state.jumpTo = null;
      showError('That message is not in this chat\'s loaded history.');
    }
  }

  // Search results inside stored messages, under the chat matches.
  function renderMessageHits(hits) {
    var names = {};
    state.chats.forEach(function (c) { names[c.id] = c.name; });
    var box = document.createDocumentFragment();
    box.appendChild(el('div', 'wa-list__section', 'Messages'));
    hits.forEach(function (m) {
      var name = names[m.chat_id] || m.name ||
        (chatIsGroup(m.chat_id) ? 'Group' : '+' + m.chat_id.split('@')[0]);
      var row = el('div', 'wa-row wa-row--msg');
      var body = el('div', 'wa-row__body');
      var top = el('div', 'wa-row__top');
      top.appendChild(el('div', 'wa-row__name', name));
      top.appendChild(el('div', 'wa-row__time', fmtShortTime(m.timestamp)));
      var pv = el('div', 'wa-row__preview');
      if (m.from_me) pv.appendChild(el('span', 'wa-row__pv-who', 'You: '));
      pv.appendChild(document.createTextNode(m.snippet));
      var line = el('div', 'wa-row__pv-line');
      line.appendChild(pv);
      body.appendChild(top); body.appendChild(line);
      var chips = renderLabelChips(m.chat_id);
      if (chips) body.appendChild(chips);
      row.appendChild(body);
      row.addEventListener('click', function () {
        openChat(m.chat_id, name, !!(names[m.chat_id] || m.name));
        state.jumpTo = { chatId: m.chat_id, id: m.id, tail: idTail(m.waha_id), ts: m.timestamp, pages: 0 };
      });
      box.appendChild(row);
    });
    return box;
  }

  // ---------- Labels ----------
  function readLabelCache() {
    if (noLabels) return null;
    try {
      var ts = parseInt(localStorage.getItem(LABEL_CACHE_TS_KEY) || '0', 10);
      if (!ts || (Date.now() - ts) > LABEL_TTL_MS) return null;
      var raw = localStorage.getItem(LABEL_CACHE_KEY);
      if (!raw) return null;
      var parsed = JSON.parse(raw);
      if (!parsed || typeof parsed !== 'object') return null;
      return parsed;
    } catch (e) { return null; }
  }
  function writeLabelCache(map, labels) {
    if (noLabels) return;
    try {
      var serial = {};
      Object.keys(map).forEach(function (k) {
        serial[k] = Array.from(map[k]);
      });
      localStorage.setItem(LABEL_CACHE_KEY, JSON.stringify({ map: serial, labels: labels }));
      localStorage.setItem(LABEL_CACHE_TS_KEY, String(Date.now()));
    } catch (e) { /* quota etc — ignore */ }
  }
  function hydrateLabelCache(cached) {
    if (!cached || !cached.map) return false;
    var map = {};
    Object.keys(cached.map).forEach(function (k) {
      map[k] = new Set(cached.map[k] || []);
    });
    state.labelMap = map;
    state.labels = Array.isArray(cached.labels) ? cached.labels : [];
    state.labelsByChat = buildLabelsByChat(map, state.labels);
    populateLabelSelect();
    state.labelsLoaded = true;
    return true;
  }
  function buildLabelsByChat(labelMap, labels) {
    // Reverse-index { chat_id: [labelObj, ...] } for O(1) lookup at render time.
    var byChat = {};
    if (!labelMap || !labels) return byChat;
    var labelById = {};
    labels.forEach(function (l) { if (l && l.id != null) labelById[String(l.id)] = l; });
    Object.keys(labelMap).forEach(function (lid) {
      var lbl = labelById[String(lid)];
      if (!lbl) return;
      var ids = labelMap[lid];
      if (!ids || typeof ids.forEach !== 'function') return;
      ids.forEach(function (chatId) {
        if (!byChat[chatId]) byChat[chatId] = [];
        byChat[chatId].push(lbl);
      });
    });
    return byChat;
  }
  function chatLabels(chatId) {
    return (state.labelsByChat && state.labelsByChat[chatId]) || [];
  }
  function renderLabelChips(chatId) {
    var lbls = chatLabels(chatId);
    if (!lbls.length) return null;
    var wrap = document.createElement('div');
    wrap.className = 'wa-row__labels';
    lbls.forEach(function (l) {
      var color = l.colorHex || '#8696a0';
      var chip = document.createElement('span');
      chip.className = 'wa-label-chip';
      // Tinted bg + matching dark text — readable on the muted sidebar.
      chip.style.background = hexAlpha(color, 0.16);
      chip.style.color = color;
      var dot = document.createElement('span');
      dot.className = 'wa-label-chip__dot';
      dot.style.background = color;
      chip.appendChild(dot);
      chip.appendChild(document.createTextNode(l.name || ''));
      wrap.appendChild(chip);
    });
    return wrap;
  }
  function hexAlpha(hex, a) {
    // #rrggbb → rgba(r,g,b,a). Falls back to muted on parse failure.
    var m = /^#([0-9a-f]{6})$/i.exec(String(hex || ''));
    if (!m) return 'rgba(134,150,160,' + a + ')';
    var n = parseInt(m[1], 16);
    return 'rgba(' + ((n >> 16) & 255) + ',' + ((n >> 8) & 255) + ',' + (n & 255) + ',' + a + ')';
  }
  // WhatsApp hands one number several labels with the same name (two "Unread",
  // "Favorites", "Groups"). Show one per name — the copy on the most chats — plus
  // any copy in `keep` (ids ticked on the open chat, so they can be unticked).
  function visibleLabels(keep) {
    var best = {};
    function uses(lb) { var set = state.labelMap && state.labelMap[lb.id]; return set ? set.size : 0; }
    state.labels.forEach(function (lb) {
      var k = (lb.name || lb.id).trim().toLowerCase();
      if (!best[k] || uses(lb) > uses(best[k])) best[k] = lb;
    });
    return state.labels.filter(function (lb) {
      return best[(lb.name || lb.id).trim().toLowerCase()] === lb || (keep && keep.has(lb.id));
    });
  }

  function populateLabelSelect() {
    var sel = $('wa-label-filter');
    var current = sel.value;
    sel.innerHTML = '';
    var optAll = document.createElement('option');
    optAll.value = ''; optAll.textContent = 'All labels';
    sel.appendChild(optAll);
    visibleLabels().forEach(function (lb) {
      var o = document.createElement('option');
      o.value = lb.id;
      o.textContent = lb.name || lb.id;
      sel.appendChild(o);
    });
    if (current) sel.value = current;
    syncQuickLabels();
  }
  // Quick-pick buttons resolve their label by name (the copy the dropdown
  // shows), and stay hidden on a number that has no such label.
  function quickLabelId(name) {
    var hit = visibleLabels().filter(function (lb) { return (lb.name || '').trim().toLowerCase() === name; })[0];
    return hit ? hit.id : '';
  }
  function syncQuickLabels() {
    var cur = $('wa-label-filter').value;
    document.querySelectorAll('.wa-qlabel').forEach(function (b) {
      var id = quickLabelId(b.dataset.labelName);
      b.dataset.labelId = id;
      b.hidden = !id;
      var on = !!id && id === cur;
      b.classList.toggle('is-active', on);
      b.setAttribute('aria-pressed', on ? 'true' : 'false');
    });
  }
  function loadLabels() {
    if (noLabels) return;
    var cached = readLabelCache();
    if (cached && hydrateLabelCache(cached)) return;

    fetch(wq('/waha/wa-chats/?labels=1'), { credentials: 'same-origin' })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (data) {
        if (!data || !data.ok) return;
        state.labels = (data.labels || []).filter(function (lb) { return !!lb.id; });
        var map = {};
        state.labels.forEach(function (lb) { map[lb.id] = new Set((data.map && data.map[lb.id]) || []); });
        state.labelMap = map;
        state.labelsByChat = buildLabelsByChat(map, state.labels);
        state.labelsLoaded = true;
        populateLabelSelect();  // duplicates resolve by chat count, now known
        // A partial read must not stand in for a whole day — retry next open.
        if (data.complete && state.labels.length) writeLabelCache(map, state.labels);
        // Re-render so freshly-loaded label chips appear in the chat list.
        renderList();
      })
      .catch(function () { /* ignore */ });
  }

  // ---------- Conversation ----------
  function openChat(id, name, hasName) {
    state.activeChatId = id;
    state.activeChatName = name;
    state.activeIsGroup = chatIsGroup(id);
    if (!hasName && !state.activeIsGroup) nameFromWhatsApp(id);

    var av = $('wa-conv-avatar');
    av.textContent = initials(name);
    av.style.background = avatarColor(id);
    addPhoto(av, id);
    $('wa-conv-name').textContent = name || id;
    $('wa-conv-sub').textContent = id;
    $('wa-comp-ta').disabled = false;
    $('wa-comp-send').disabled = false;
    $('wa-comp-attach').disabled = false;
    $('wa-comp-mic').disabled = false;
    $('wa-chat-more').disabled = false;
    cancelReply();
    clearAttachment();
    stopRecording(true);

    Array.prototype.forEach.call(document.querySelectorAll('.wa-row'), function (r) {
      r.classList.toggle('wa-row--active', r.dataset.chatId === id);
    });

    $('wa-info-toggle').disabled = false;
    panel.loadedFor = null;
    setPanelOpen(panel.open);
    loadMessages();
    markChatRead(id, false);
  }

  // Opening a chat reads it, as in WhatsApp: the sender gets blue ticks and the
  // unread badge clears here and on the phone. `force` = a new message came in
  // while the chat was open (only counted as read if the tab is on screen).
  function markChatRead(id, force) {
    if (force && document.visibilityState !== 'visible') return;
    var chat = null;
    for (var i = 0; i < state.chats.length; i++) { if (state.chats[i].id === id) { chat = state.chats[i]; break; } }
    if (!force && chat && !chat.unread) return;
    if (chat && chat.unread) { chat.unread = 0; renderList(); }
    fetch('/waha/wa-chats/read/', {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': CSRF },
      body: JSON.stringify({ session: SESSION, chatId: id }),
    }).catch(function () { /* the next open retries */ });
  }

  // Header title for a chat with no saved name: the name the person set in
  // WhatsApp ("~ Name", as WhatsApp Web shows it), else their real phone number.
  function nameFromWhatsApp(id) {
    fetch(wq('/waha/wa-chats/?who=1&chatId=' + encodeURIComponent(id)), { credentials: 'same-origin' })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (w) {
        if (!w || !w.ok || state.activeChatId !== id) return;
        var title = w.saved_name || w.lead_name || (w.push_name ? '~ ' + w.push_name : '') || (w.phone ? '+' + w.phone : '');
        if (title) $('wa-conv-name').textContent = title;
      })
      .catch(function () { /* keep the number */ });
  }

  // Initial chat-open: newest 50, replace.
  function loadMessages() {
    if (!state.activeChatId) return;
    state.msgs = [];
    state.msgsHasMore = true;
    state.msgsLoading = false;
    state.msgsOldestTs = 0;
    state.msgsLiveOffsetSeen = 0;
    var box = $('wa-msgs');
    if (box) box.innerHTML = '<div class="wa-empty">Loading messages…</div>';
    hideError();
    var chatIdAtCall = state.activeChatId;
    var url = wq('/waha/wa-chats/?messages=1&chatId=' + encodeURIComponent(chatIdAtCall) + '&limit=50');
    state.msgsLoading = true;
    fetch(url, { credentials: 'same-origin' })
      .then(function (r) {
        return r.text().then(function (raw) {
          var data = null;
          try { data = JSON.parse(raw); } catch (e) {}
          return { ok: r.ok, status: r.status, data: data };
        });
      })
      .then(function (res) {
        state.msgsLoading = false;
        if (chatIdAtCall !== state.activeChatId) return; // user switched chats
        if (!res.ok || !res.data || !res.data.ok) {
          var msg = (res.data && res.data.error) || ('HTTP ' + res.status);
          if (box) box.innerHTML = '';
          showError('Failed to load messages: ' + msg);
          return;
        }
        state.msgs = res.data.messages || [];
        state.msgsHasMore = !!res.data.has_more;
        state.msgsOldestTs = state.msgs.length ? (state.msgs[0].timestamp || 0) : 0;
        state.msgsLiveOffsetSeen = 50;
        renderMessages(state.msgs);
        tryJump();
      })
      .catch(function (e) {
        state.msgsLoading = false;
        if (box) box.innerHTML = '';
        showError('Network error: ' + e);
      });
  }

  // Scroll-up older page: fetch 50 messages older than the current oldest.
  function loadOlderMessages() {
    if (!state.activeChatId) return;
    if (state.msgsLoading || !state.msgsHasMore || !state.msgsOldestTs) return;
    var chatIdAtCall = state.activeChatId;
    var box = $('wa-msgs');
    if (!box) return;
    state.msgsLoading = true;
    // Show a tiny indicator at the top
    var loader = document.createElement('div');
    loader.className = 'wa-empty wa-empty--top';
    loader.textContent = 'Loading older messages…';
    box.insertBefore(loader, box.firstChild);
    var prevHeight = box.scrollHeight;
    var url = wq('/waha/wa-chats/?messages=1&chatId=' + encodeURIComponent(chatIdAtCall) +
              '&limit=50&before_ts=' + state.msgsOldestTs +
              '&older_offset=' + (state.msgsLiveOffsetSeen || 0));
    fetch(url, { credentials: 'same-origin' })
      .then(function (r) {
        return r.text().then(function (raw) {
          var data = null;
          try { data = JSON.parse(raw); } catch (e) {}
          return { ok: r.ok, status: r.status, data: data };
        });
      })
      .then(function (res) {
        state.msgsLoading = false;
        if (loader.parentNode) loader.parentNode.removeChild(loader);
        if (chatIdAtCall !== state.activeChatId) return;
        if (!res.ok || !res.data || !res.data.ok) return;
        var older = res.data.messages || [];
        if (!older.length) {
          state.msgsHasMore = false;
          tryJump();
          return;
        }
        state.msgs = older.concat(state.msgs);
        state.msgsOldestTs = older[0].timestamp || state.msgsOldestTs;
        state.msgsLiveOffsetSeen += older.length;
        state.msgsHasMore = !!res.data.has_more;
        renderMessages(state.msgs);
        // Preserve scroll position so user stays on the same content.
        box.scrollTop = box.scrollHeight - prevHeight;
        tryJump();
      })
      .catch(function () {
        state.msgsLoading = false;
        if (loader.parentNode) loader.parentNode.removeChild(loader);
      });
  }

  // Group media is not downloaded until someone asks: photos, videos and
  // stickers show a download button, voice notes and documents load only when
  // played or opened. ?fetch=1 has the server pull the file from WhatsApp and
  // keep it (whatsapp/media_archive.fetch_on_demand).
  var GATE_KINDS = { image: 'Photo', video: 'Video', sticker: 'Sticker' };
  function withFetch(url) { return url + (url.indexOf('?') === -1 ? '?' : '&') + 'fetch=1'; }
  function mediaGate(msg, t, media) {
    var wrap = document.createElement('div');
    var b = el('button', 'wa-mgate' + (t === 'sticker' ? ' wa-mgate--sticker' : ''));
    b.type = 'button';
    b.title = 'Download from WhatsApp';
    b.appendChild(el('span', 'wa-mgate__icon', '\u2B07'));
    b.appendChild(el('span', null, GATE_KINDS[t] + (media.size ? ' \u00B7 ' + fmtSize(media.size) : '')));
    b.addEventListener('click', function () {
      media.url = withFetch(media.url);
      media.stored = true;
      media.clicked = true;
      wrap.replaceWith(renderBody(msg));
    });
    wrap.appendChild(b);
    if (msg.body && t !== 'sticker') {
      var cap = el('div', 'wa-mgate__cap');
      cap.appendChild(richText(msg.body));
      wrap.appendChild(cap);
    }
    return wrap;
  }
  // A file that was just asked for and WhatsApp no longer has.
  function goneOnError(node, kind) {
    node.addEventListener('error', function () {
      node.replaceWith(el('span', 'wa-notice', '\u{1F4CE} ' + kind + ' no longer available on WhatsApp'));
    });
  }

  function renderBody(msg) {
    var wrap = document.createElement('div');
    var t = msg.type || 'text';
    var media = msg.media || null;
    var gated = !!(state.activeIsGroup && media && media.url && media.stored === false);
    if (gated && GATE_KINDS[t]) return mediaGate(msg, t, media);

    if (t === 'image' && media && media.url) {
      var img = document.createElement('img');
      img.className = 'wa-media-img';
      if (media.clicked) goneOnError(img, 'Photo');
      img.src = media.url;
      img.dataset.lbUrl = media.url;
      img.dataset.lbKind = 'photo';
      img.dataset.lbMeta = fmtDate(msg.timestamp, true) + ' · ' + (msg.direction === 'outbound' ? 'Sent' : 'Received');
      img.dataset.lbCaption = (msg.body && msg.body.indexOf(' ') !== -1) ? msg.body : '';
      wrap.appendChild(img);
      if (msg.body) {
        var cap = document.createElement('div');
        cap.style.marginTop = '0.25rem';
        cap.appendChild(richText(msg.body));
        wrap.appendChild(cap);
      }
    } else if (t === 'video' && media && media.url) {
      // A still preview with a play mark; clicking opens the video in the media viewer.
      var vt = document.createElement('div');
      vt.className = 'wa-vthumb';
      vt.dataset.lbUrl = media.url;
      vt.dataset.lbKind = 'video';
      vt.dataset.lbMeta = fmtDate(msg.timestamp, true) + ' · ' + (msg.direction === 'outbound' ? 'Sent' : 'Received');
      vt.dataset.lbCaption = msg.body || '';
      vt.setAttribute('role', 'button');
      vt.setAttribute('aria-label', 'Play video');
      var v = document.createElement('video');
      v.className = 'wa-media-video';
      v.preload = 'metadata'; v.muted = true; v.playsInline = true; v.src = media.url + '#t=0.1';
      v.addEventListener('error', function () { vt.classList.add('wa-vthumb--broken'); });
      vt.appendChild(v);
      vt.appendChild(el('span', 'wa-vthumb__play', '▶'));
      wrap.appendChild(vt);
      if (msg.body) {
        var cap2 = document.createElement('div');
        cap2.style.marginTop = '0.25rem';
        cap2.appendChild(richText(msg.body));
        wrap.appendChild(cap2);
      }
    } else if (t === 'audio' && media && media.url) {
      var au = document.createElement('audio');
      au.className = 'wa-media-audio';
      au.controls = true;
      if (gated) au.preload = 'none';
      au.src = gated ? withFetch(media.url) : media.url;
      wrap.appendChild(au);
    } else if (t === 'document' && media && media.url) {
      var a = document.createElement('a');
      a.className = 'wa-doc'; a.target = '_blank'; a.rel = 'noopener';
      a.href = gated ? withFetch(media.url) : media.url;
      a.textContent = '📎 ' + (msg.filename || msg.body || 'Document');
      wrap.appendChild(a);
      if (msg.filename && msg.body && msg.body !== msg.filename) {
        var dcap = document.createElement('div');
        dcap.appendChild(richText(msg.body));
        wrap.appendChild(dcap);
      }
    } else if (t === 'location') {
      var locBox = document.createElement('div');
      locBox.className = 'wa-location';
      if (msg.location && typeof msg.location.latitude === 'number') {
        var lat = msg.location.latitude;
        var lng = msg.location.longitude;
        var a = document.createElement('a');
        a.href = 'https://maps.google.com/?q=' + lat + ',' + lng;
        a.target = '_blank'; a.rel = 'noopener';
        a.textContent = '📍 ' + lat.toFixed(5) + ', ' + lng.toFixed(5);
        a.style.textDecoration = 'underline';
        locBox.appendChild(a);
      } else {
        var loc = document.createElement('span');
        loc.textContent = '📍 location';
        locBox.appendChild(loc);
      }
      // Verification-job CTA: shows the matched order + quick-apply for manual_review jobs.
      var vj = msg.verification_job;
      if (vj) {
        var meta = document.createElement('div');
        meta.style.marginTop = '4px';
        meta.style.fontSize = '0.7rem';
        var statusColors = {
          'verified':      'background:#198754;color:#fff;',
          'manual_review': 'background:#ffc107;color:#000;',
          'sent':          'background:#0dcaf0;color:#000;',
          'queued':        'background:#6c757d;color:#fff;',
          'failed':        'background:#dc3545;color:#fff;',
          'cancelled':     'background:#e9ecef;color:#495057;',
        };
        var badge = document.createElement('span');
        badge.style.cssText = 'padding:2px 6px;border-radius:6px;margin-right:6px;' + (statusColors[vj.status] || '');
        badge.textContent = vj.status.replace('_', ' ');
        meta.appendChild(badge);
        if (vj.order_number) {
          var orderLink = document.createElement('a');
          orderLink.href = '/workforce/orders/' + vj.order_id + '/';
          orderLink.target = '_blank';
          orderLink.textContent = vj.order_number + (vj.customer_name ? ' · ' + vj.customer_name : '');
          orderLink.style.color = 'inherit';
          orderLink.style.textDecoration = 'underline';
          meta.appendChild(orderLink);
        }
        if (vj.status === 'manual_review') {
          var applyBtn = document.createElement('button');
          applyBtn.type = 'button';
          applyBtn.textContent = 'Apply pin';
          applyBtn.style.cssText = 'margin-left:6px;padding:2px 8px;background:#198754;color:#fff;border:none;border-radius:6px;cursor:pointer;font-size:0.65rem;';
          applyBtn.onclick = function () {
            if (!confirm('Apply this WhatsApp pin to order ' + (vj.order_number || ('#' + vj.order_id)) + '?')) return;
            applyBtn.disabled = true; applyBtn.textContent = '...';
            var csrf = (document.querySelector('[name=csrfmiddlewaretoken]') || {}).value
              || (document.cookie.split(';').find(function (c) { return c.trim().startsWith('csrftoken='); }) || '=').split('=')[1] || '';
            fetch('/workforce/orders/temp/verify-queue/' + vj.id + '/action/', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf },
              body: JSON.stringify({ action: 'apply_to_order' }),
            }).then(function (r) { return r.json(); }).then(function (data) {
              if (data.success) {
                badge.textContent = 'verified';
                badge.style.cssText = 'padding:2px 6px;border-radius:6px;margin-right:6px;' + statusColors['verified'];
                applyBtn.remove();
              } else {
                applyBtn.disabled = false; applyBtn.textContent = 'Apply pin';
                alert('Error: ' + (data.error || 'apply failed'));
              }
            }).catch(function (err) {
              applyBtn.disabled = false; applyBtn.textContent = 'Apply pin';
              alert('Error: ' + err.message);
            });
          };
          meta.appendChild(applyBtn);
        }
        locBox.appendChild(meta);
      }
      wrap.appendChild(locBox);
    } else if (t === 'sticker' && media && media.url) {
      var st = document.createElement('img');
      st.className = 'wa-media-sticker';
      if (media.clicked) goneOnError(st, 'Sticker');
      st.src = media.url;
      wrap.appendChild(st);
    } else if (t === 'contact') {
      // The server parsed the vCard; its raw text carries a base64 photo.
      var cards = msg.contacts && msg.contacts.length ? msg.contacts : [{ name: 'Contact', phone: '' }];
      cards.forEach(function (c) {
        var card = el('div', 'wa-contact');
        card.appendChild(el('span', 'wa-contact__icon', '👤'));
        var info = el('div', 'wa-contact__info');
        info.appendChild(el('div', 'wa-contact__name', c.name || c.phone || 'Contact'));
        if (c.phone && c.name) info.appendChild(el('div', 'wa-contact__phone', c.phone));
        card.appendChild(info);
        wrap.appendChild(card);
      });
    } else if (msg.notice) {
      wrap.appendChild(el('span', 'wa-notice', msg.notice));
    } else if (/^(image|video|audio|document|sticker)$/.test(t) && !(media && media.url)) {
      // The file is not available (WAHA purged it before we archived it): say so
      // instead of drawing an empty bubble.
      var kind = { image: 'Photo', video: 'Video', audio: 'Audio', document: 'Document', sticker: 'Sticker' }[t];
      wrap.appendChild(el('span', 'wa-notice', '\u{1F4CE} ' + (msg.filename || kind) + ' (file not available)'));
      if (msg.body && t !== 'sticker') {
        var mcap = document.createElement('div');
        mcap.appendChild(richText(msg.body));
        wrap.appendChild(mcap);
      }
    } else {
      var s = document.createElement('span');
      s.appendChild(richText(msg.body || ''));
      wrap.appendChild(s);
    }
    return wrap;
  }

  function senderHeader(sender) {
    if (!sender) return null;
    var hdr = document.createElement('div');
    hdr.className = 'wa-bubble__sender';
    hdr.style.color = sender.color || senderColor(sender.id);
    // With a push name: "Name +974...". Without: just "+974..." — never twice.
    hdr.textContent = sender.name || (sender.id ? '+' + sender.id : '');
    if (sender.name && sender.id && sender.name !== sender.id) {
      var idSpan = document.createElement('span');
      idSpan.className = 'wa-bubble__sender-id';
      idSpan.textContent = ' +' + sender.id;
      hdr.appendChild(idSpan);
    }
    return hdr;
  }

  function msgRow(m) {
      var row = document.createElement('div');
      row.className = 'wa-msg ' + (m.direction === 'outbound' ? 'wa-msg--out' : 'wa-msg--in');
      var bubble = document.createElement('div');
      bubble.className = 'wa-bubble' + (m.direction === 'outbound' ? ' wa-bubble--out' : '');

      if (state.activeIsGroup && m.direction !== 'outbound' && m.sender) {
        var sh = senderHeader(m.sender);
        if (sh) bubble.appendChild(sh);
      }

      if (m.quoted) bubble.appendChild(quoteBlock(m.quoted, true));

      bubble.appendChild(renderBody(m));

      var tm = document.createElement('div');
      tm.className = 'wa-bubble__time';
      if (m.edited && !m.notice) tm.appendChild(el('span', 'wa-edited', 'Edited'));
      tm.appendChild(document.createTextNode(fmtShortTime(m.timestamp)));
      if (m.direction === 'outbound') setTick(tm, m.ack);
      bubble.appendChild(tm);

      row.dataset.key = msgKey(m);
      row.appendChild(bubble);
      // Only a message WhatsApp knows by id can be quoted, reacted to or forwarded.
      if (m.waha_id && !m.notice) row.appendChild(msgActions(m, row));
      drawReactions(row, m);
      return row;
  }

  function actBtn(label, glyph, onClick) {
    var b = document.createElement('button');
    b.type = 'button';
    b.className = 'wa-reply-btn';
    b.title = label;
    b.setAttribute('aria-label', label);
    b.textContent = glyph;
    b.addEventListener('click', function (e) { e.stopPropagation(); onClick(b); });
    return b;
  }
  function msgActions(m, row) {
    var acts = document.createElement('div');
    acts.className = 'wa-acts';
    acts.appendChild(actBtn('Reply', '\u21A9', function () { startReply(m); }));
    acts.appendChild(actBtn('React', '\u263A', function (b) { openReactions(b, m, row); }));
    acts.appendChild(actBtn('More', '\u22EE', function (b) { openMsgMenu(b, m, row); }));
    return acts;
  }

  // ---------- Quote-reply ----------
  // Quoted ids are WhatsApp's short key; our rows are keyed by the serialized
  // id, which ends in `_<short key>` (groups add `_<participant>` after it).
  function findRowByShortId(shortId) {
    if (!shortId) return null;
    var safe = String(shortId).replace(/["\\]/g, '');
    return $('wa-msgs').querySelector('.wa-msg[data-key$="_' + safe + '"], .wa-msg[data-key*="_' + safe + '_"]');
  }
  function msgByShortId(shortId) {
    for (var i = 0; i < state.msgs.length; i++) {
      var k = String(state.msgs[i].waha_id || '');
      if (k && (k.slice(-(shortId.length + 1)) === '_' + shortId || k.indexOf('_' + shortId + '_') !== -1)) return state.msgs[i];
    }
    return null;
  }
  function whoOf(m) {
    if (!m) return '';
    if (m.direction === 'outbound') return 'You';
    if (m.sender) return m.sender.name || (m.sender.id ? '+' + m.sender.id : '');
    return state.activeChatName || '';
  }
  function quoteText(m) {
    if (m.body) return m.body;
    var t = { image: 'Photo', video: 'Video', audio: 'Audio', ptt: 'Voice message', voice: 'Voice message',
              document: 'Document', sticker: 'Sticker', location: 'Location', contact: 'Contact' }[m.type];
    return t || 'Message';
  }
  // `q` is {id, body}; `jump` makes it a link back to the original bubble.
  function quoteBlock(q, jump) {
    var el = document.createElement(jump ? 'button' : 'div');
    if (jump) el.type = 'button';
    el.className = 'wa-quote';
    var orig = msgByShortId(q.id);
    var who = q.who || whoOf(orig);
    if (who) {
      var w = document.createElement('span');
      w.className = 'wa-quote__who';
      w.textContent = who;
      el.appendChild(w);
    }
    var t = document.createElement('span');
    t.className = 'wa-quote__text';
    t.textContent = q.body || (orig ? quoteText(orig) : 'Message');
    el.appendChild(t);
    if (jump) {
      el.title = 'Show the original message';
      el.addEventListener('click', function () {
        var row = findRowByShortId(q.id);
        if (!row) { showError('The original message is further back — scroll up to load it.'); return; }
        row.scrollIntoView({ block: 'center', behavior: 'smooth' });
        row.classList.remove('wa-msg--hit');
        void row.offsetWidth;
        row.classList.add('wa-msg--hit');
      });
    }
    return el;
  }
  function startReply(m) {
    state.replyTo = { waha_id: m.waha_id, who: whoOf(m), body: quoteText(m) };
    var box = $('wa-replybar-quote');
    box.innerHTML = '';
    var w = document.createElement('span');
    w.className = 'wa-quote__who';
    w.textContent = 'Replying to ' + (state.replyTo.who || 'message');
    box.appendChild(w);
    var t = document.createElement('span');
    t.className = 'wa-quote__text';
    t.textContent = state.replyTo.body;
    box.appendChild(t);
    $('wa-replybar').hidden = false;
    $('wa-comp-ta').focus();
  }
  function cancelReply() {
    state.replyTo = null;
    $('wa-replybar').hidden = true;
  }

  function postJSON(url, body) {
    return fetch(url, {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': CSRF },
      body: JSON.stringify(body),
    }).then(function (r) { return r.json().catch(function () { return { ok: false, error: 'HTTP ' + r.status }; }); });
  }

  // ---------- Floating menus ----------
  var pop = null;
  function closePop() { if (pop) { pop.remove(); pop = null; } }
  function openPop(anchor, build) {
    closePop();
    pop = document.createElement('div');
    pop.className = 'wa-pop';
    pop.setAttribute('role', 'menu');
    build(pop);
    document.body.appendChild(pop);
    var r = anchor.getBoundingClientRect();
    var left = Math.min(Math.max(8, r.left + r.width / 2 - pop.offsetWidth / 2), window.innerWidth - pop.offsetWidth - 8);
    var top = r.top - pop.offsetHeight - 6;
    if (top < 8) top = r.bottom + 6;
    pop.style.left = left + 'px';
    pop.style.top = top + 'px';
    var first = pop.querySelector('button');
    if (first) first.focus();
  }
  function menuItem(p, label, onClick, danger) {
    var b = document.createElement('button');
    b.type = 'button';
    b.className = 'wa-pop__item' + (danger ? ' wa-pop__item--danger' : '');
    b.setAttribute('role', 'menuitem');
    b.textContent = label;
    b.addEventListener('click', function () { closePop(); onClick(); });
    p.appendChild(b);
  }
  document.addEventListener('click', function (e) { if (pop && !pop.contains(e.target)) closePop(); });
  document.addEventListener('keydown', function (e) { if (e.key === 'Escape') closePop(); });
  window.addEventListener('resize', closePop);

  // ---------- Reactions ----------
  var REACTIONS = ['\u{1F44D}', '\u2764\uFE0F', '\u{1F602}', '\u{1F62E}', '\u{1F622}', '\u{1F64F}'];
  function myReaction(m) {
    var mine = (m.reactions || []).filter(function (r) { return r.me; })[0];
    return mine ? mine.emoji : '';
  }
  function openReactions(anchor, m, row) {
    var mine = myReaction(m);
    openPop(anchor, function (p) {
      p.classList.add('wa-pop--emoji');
      REACTIONS.forEach(function (e) {
        var b = document.createElement('button');
        b.type = 'button';
        b.className = 'wa-pop__emoji' + (e === mine ? ' is-on' : '');
        b.textContent = e;
        b.title = e === mine ? 'Remove your reaction' : 'React ' + e;
        b.addEventListener('click', function () { closePop(); sendReaction(m, row, e === mine ? '' : e); });
        p.appendChild(b);
      });
    });
  }
  function sendReaction(m, row, emoji) {
    var before = m.reactions;
    var others = (m.reactions || []).filter(function (r) { return !r.me; });
    m.reactions = emoji ? others.concat([{ emoji: emoji, me: true }]) : others;
    drawReactions(row, m);
    postJSON('/waha/wa-chats/react/', { session: SESSION, messageId: m.waha_id, emoji: emoji })
      .then(function (j) {
        if (j && j.ok) return;
        m.reactions = before;
        drawReactions(row, m);
        showError('Reaction failed: ' + ((j && j.error) || ''));
      })
      .catch(function (e) { m.reactions = before; drawReactions(row, m); showError('Reaction error: ' + e); });
  }
  function drawReactions(row, m) {
    var bubble = row.querySelector('.wa-bubble');
    var old = bubble.querySelector('.wa-reacts');
    if (old) old.remove();
    var list = m.reactions || [];
    row.classList.toggle('wa-msg--reacted', list.length > 0);
    if (!list.length) return;
    var order = [];
    list.forEach(function (r) { if (order.indexOf(r.emoji) === -1) order.push(r.emoji); });
    var chip = document.createElement('button');
    chip.type = 'button';
    chip.className = 'wa-reacts';
    chip.textContent = order.join('') + (list.length > 1 ? ' ' + list.length : '');
    chip.title = list.map(function (r) { return (r.me ? 'You' : 'Them') + ' ' + r.emoji; }).join(' · ');
    if (m.waha_id) chip.addEventListener('click', function (e) { e.stopPropagation(); openReactions(chip, m, row); });
    bubble.appendChild(chip);
  }

  // ---------- Message menu: forward, edit, delete ----------
  var EDIT_WINDOW_S = 15 * 60;            // WhatsApp's edit limit
  var DELETE_WINDOW_S = 2 * 24 * 3600;    // "delete for everyone" limit, about two days
  function ownMessage(m) { return m.direction === 'outbound' && String(m.waha_id || '').indexOf('true_') === 0 && !m.notice; }
  function ageS(m) { return Date.now() / 1000 - (m.timestamp || 0); }
  function openMsgMenu(anchor, m, row) {
    openPop(anchor, function (p) {
      menuItem(p, 'Reply', function () { startReply(m); });
      menuItem(p, 'Forward', function () { openForward(m); });
      if (ownMessage(m) && m.type === 'text' && ageS(m) < EDIT_WINDOW_S) menuItem(p, 'Edit', function () { openEdit(m, row); });
      if (ownMessage(m) && ageS(m) < DELETE_WINDOW_S) menuItem(p, 'Delete for everyone', function () { deleteMessage(m, row); }, true);
    });
  }
  function redrawRow(row, m) {
    var fresh = msgRow(m);
    row.replaceWith(fresh);
    return fresh;
  }

  var editing = null;
  function openEdit(m, row) {
    editing = { m: m, row: row, chatId: state.activeChatId };
    $('wa-edit-ta').value = m.body || '';
    $('wa-edit').showModal();
    $('wa-edit-ta').focus();
  }
  function saveEdit() {
    if (!editing) return;
    var text = ($('wa-edit-ta').value || '').trim();
    if (!text || text === editing.m.body) { $('wa-edit').close(); return; }
    var job = editing;
    $('wa-edit-save').disabled = true;
    postJSON('/waha/wa-chats/edit/', { session: SESSION, chatId: job.chatId, messageId: job.m.waha_id, text: text })
      .then(function (j) {
        $('wa-edit-save').disabled = false;
        if (!j || !j.ok) { showError('Edit failed: ' + ((j && j.error) || '')); return; }
        $('wa-edit').close();
        job.m.body = text;
        job.m.edited = true;
        if (job.row.isConnected) redrawRow(job.row, job.m);
      })
      .catch(function (e) { $('wa-edit-save').disabled = false; showError('Edit error: ' + e); });
  }

  function deleteMessage(m, row) {
    if (!window.confirm('Delete this message for everyone? The customer will see "This message was deleted".')) return;
    postJSON('/waha/wa-chats/delete/', { session: SESSION, chatId: state.activeChatId, messageId: m.waha_id })
      .then(function (j) {
        if (!j || !j.ok) { showError('Delete failed: ' + ((j && j.error) || '')); return; }
        m.body = ''; m.media = null; m.quoted = null; m.reactions = [];
        m.type = 'unknown'; m.notice = 'This message was deleted';
        if (row.isConnected) redrawRow(row, m);
      })
      .catch(function (e) { showError('Delete error: ' + e); });
  }

  var fwd = { msg: null, picked: {} };
  function openForward(m) {
    fwd = { msg: m, picked: {} };
    $('wa-fwd-q').value = '';
    renderForward();
    $('wa-fwd').showModal();
    $('wa-fwd-q').focus();
  }
  function renderForward() {
    var q = ($('wa-fwd-q').value || '').trim().toLowerCase();
    var picked = Object.keys(fwd.picked).length;
    var list = state.chats.filter(function (c) {
      if (/@(newsletter|broadcast)$/.test(c.id)) return false;
      return !q || (c.name || '').toLowerCase().indexOf(q) !== -1
        || (c.number || '').toLowerCase().indexOf(q) !== -1 || c.id.indexOf(q) !== -1;
    }).sort(function (a, b) { return (b.timestamp || 0) - (a.timestamp || 0); }).slice(0, 60);
    var box = $('wa-fwd-list');
    box.innerHTML = '';
    if (!list.length) box.appendChild(el('div', 'wa-empty', 'No chats match.'));
    list.forEach(function (c) {
      var lab = document.createElement('label');
      lab.className = 'wa-fwd__row';
      var cb = document.createElement('input');
      cb.type = 'checkbox';
      cb.checked = !!fwd.picked[c.id];
      cb.disabled = !cb.checked && picked >= 5;
      cb.addEventListener('change', function () {
        if (cb.checked) fwd.picked[c.id] = c.name; else delete fwd.picked[c.id];
        renderForward();
      });
      lab.appendChild(cb);
      lab.appendChild(el('span', 'wa-fwd__name', c.name || c.id));
      box.appendChild(lab);
    });
    $('wa-fwd-count').textContent = picked ? picked + ' selected (max 5)' : 'Pick up to 5 chats';
    $('wa-fwd-send').disabled = !picked;
  }
  function sendForward() {
    var ids = Object.keys(fwd.picked);
    if (!ids.length || !fwd.msg) return;
    $('wa-fwd-send').disabled = true;
    postJSON('/waha/wa-chats/forward/', { session: SESSION, messageId: fwd.msg.waha_id, chatIds: ids })
      .then(function (j) {
        $('wa-fwd-send').disabled = false;
        if (!j || !j.ok) { showError('Forward failed: ' + ((j && j.error) || '')); return; }
        $('wa-fwd').close();
        showInfo('Forwarded to ' + ids.length + ' chat' + (ids.length > 1 ? 's' : '') + '.');
      })
      .catch(function (e) { $('wa-fwd-send').disabled = false; showError('Forward error: ' + e); });
  }

  // ---------- Attachments ----------
  var MB = 1024 * 1024;
  var attach = { file: null, url: null };
  function fmtSize(n) { return n >= MB ? (n / MB).toFixed(1) + ' MB' : Math.max(1, Math.round(n / 1024)) + ' KB'; }
  // Mirrors the server's choice in wa_chats_actions.wa_chats_send_media.
  function sendsAs(f) {
    // Any still image goes as a photo; the server re-encodes WebP/HEIC/GIF to JPEG.
    if ((/^image\//.test(f.type) && f.type !== 'image/svg+xml') || /\.(heic|heif|webp|avif)$/i.test(f.name || '')) return 'Photo';
    if (/^video\//.test(f.type) && f.size <= 16 * MB) return 'Video';
    return 'Document';
  }
  function setAttachment(file) {
    if (!file || !state.activeChatId) return;
    if (file.size > 30 * MB) { showError('That file is ' + fmtSize(file.size) + '. The inbox sends files up to 30 MB.'); return; }
    clearAttachment();
    attach.file = file;
    var kind = sendsAs(file);
    $('wa-attach-name').textContent = file.name || 'Pasted image';
    $('wa-attach-meta').textContent = fmtSize(file.size) + ' · sends as ' + kind.toLowerCase();
    var th = $('wa-attach-thumb');
    if (/^image\//.test(file.type)) {
      attach.url = URL.createObjectURL(file);
      // HEIC and some others have no browser preview; fall back to the icon.
      th.onerror = function () { th.hidden = true; $('wa-attach-icon').textContent = '\u{1F5BC}'; $('wa-attach-icon').hidden = false; };
      th.src = attach.url;
      th.hidden = false;
      $('wa-attach-icon').hidden = true;
    } else {
      th.hidden = true;
      th.removeAttribute('src');
      $('wa-attach-icon').textContent = kind === 'Video' ? '\u{1F3AC}' : '\u{1F4C4}';
      $('wa-attach-icon').hidden = false;
    }
    $('wa-attachbar').hidden = false;
    $('wa-comp-ta').placeholder = 'Add a caption (optional)';
    $('wa-comp-ta').focus();
  }
  function clearAttachment() {
    if (attach.url) URL.revokeObjectURL(attach.url);
    attach = { file: null, url: null };
    $('wa-attachbar').hidden = true;
    $('wa-comp-ta').placeholder = 'Type a message';
    $('wa-comp-file').value = '';
  }
  function uploadMedia(file, caption, reply, voice) {
    var to = state.activeChatId;
    var label = voice ? '\u{1F3A4} Voice message' : '\u{1F4CE} ' + (file.name || 'Attachment') + (caption ? '\n' + caption : '');
    var row = appendOutgoingLocal(label, reply);
    var tm = row.querySelector('.wa-bubble__time');
    var fd = new FormData();
    fd.append('file', file, file.name || 'file');
    fd.append('to', to);
    fd.append('session', SESSION);
    if (caption) fd.append('caption', caption);
    if (reply) fd.append('reply_to', reply.waha_id);
    if (voice) fd.append('voice', '1');
    fetch('/waha/wa-chats/send-media/', { method: 'POST', credentials: 'same-origin', headers: { 'X-CSRFToken': CSRF }, body: fd })
      .then(function (r) { return r.json().catch(function () { return { ok: false, error: 'HTTP ' + r.status }; }); })
      .then(function (j) {
        if (j && j.ok) {
          setTick(tm, 1);
          // The real copy (with the file) replaces this placeholder on the next fetch.
          setTimeout(function () { if (state.activeChatId === to) refreshMessages(); }, 2500);
          return;
        }
        row.classList.remove('wa-msg--local');
        setTick(tm, -1);
        showError('Send failed: ' + ((j && j.error) || ''));
      })
      .catch(function (e) { row.classList.remove('wa-msg--local'); setTick(tm, -1); showError('Send error: ' + e); });
  }

  // ---------- Voice notes ----------
  var rec = { mr: null, chunks: [], timer: null, start: 0, cancelled: false, chat: null };
  var VOICE_MAX_S = 600;
  function voiceMime() {
    var c = ['audio/ogg;codecs=opus', 'audio/webm;codecs=opus', 'audio/mp4'];
    for (var i = 0; i < c.length; i++) {
      if (window.MediaRecorder && MediaRecorder.isTypeSupported && MediaRecorder.isTypeSupported(c[i])) return c[i];
    }
    return '';
  }
  function setRecUi(on) {
    document.querySelector('.wa-comp').classList.toggle('wa-comp--rec', on);
    $('wa-rec').hidden = !on;
  }
  function tickRec() {
    var s = Math.floor((Date.now() - rec.start) / 1000);
    $('wa-rec-time').textContent = Math.floor(s / 60) + ':' + String(s % 60).padStart(2, '0');
    if (s >= VOICE_MAX_S) stopRecording(false);
  }
  function startRecording() {
    if (!state.activeChatId || (rec.mr && rec.mr.state !== 'inactive')) return;
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia || !window.MediaRecorder) {
      showError('This browser cannot record audio.');
      return;
    }
    navigator.mediaDevices.getUserMedia({ audio: true }).then(function (stream) {
      var mime = voiceMime();
      rec.chunks = [];
      rec.cancelled = false;
      rec.chat = state.activeChatId;
      rec.mr = mime ? new MediaRecorder(stream, { mimeType: mime }) : new MediaRecorder(stream);
      rec.mr.ondataavailable = function (e) { if (e.data && e.data.size) rec.chunks.push(e.data); };
      rec.mr.onstop = function () {
        stream.getTracks().forEach(function (t) { t.stop(); });
        clearInterval(rec.timer);
        setRecUi(false);
        if (rec.cancelled || !rec.chunks.length) return;
        if (rec.chat !== state.activeChatId) { showError('Voice note discarded: the chat changed while recording.'); return; }
        var type = (rec.mr.mimeType || mime || 'audio/webm').split(';')[0];
        var ext = /ogg/.test(type) ? 'ogg' : /mp4/.test(type) ? 'm4a' : 'webm';
        var file = new File(rec.chunks, 'voice-note.' + ext, { type: type });
        var reply = state.replyTo;
        cancelReply();
        uploadMedia(file, '', reply, true);
      };
      rec.mr.start(1000);
      rec.start = Date.now();
      setRecUi(true);
      tickRec();
      rec.timer = setInterval(tickRec, 500);
    }).catch(function (e) {
      showError(e && e.name === 'NotAllowedError'
        ? 'Microphone blocked: allow microphone access for this site in the browser.'
        : 'Could not start recording: ' + e);
    });
  }
  function stopRecording(cancel) {
    if (!rec.mr || rec.mr.state === 'inactive') return;
    rec.cancelled = !!cancel;
    rec.mr.stop();
  }

  // ---------- Number check (search / new conversation only) ----------
  // A typed number with no chat yet is checked once against WhatsApp, after the
  // writer pauses; nothing else in the inbox calls this.
  var numCheck = {};
  var numTimer = null;
  function scheduleNumberCheck(digits) {
    if (numCheck[digits]) return;
    clearTimeout(numTimer);
    numTimer = setTimeout(function () {
      if (($('wa-search').value || '').trim() !== digits || numCheck[digits]) return;
      numCheck[digits] = { state: 'checking' };
      fetch(wq('/waha/wa-chats/check-number/?phone=' + encodeURIComponent(digits)), { credentials: 'same-origin' })
        .then(function (r) { return r.json().catch(function () { return null; }); })
        .then(function (j) {
          numCheck[digits] = (j && j.ok) ? { state: j.exists ? 'yes' : 'no', chatId: j.chatId || '' } : { state: 'error' };
          if (($('wa-search').value || '').trim() === digits) renderList();
        })
        .catch(function () { numCheck[digits] = { state: 'error' }; });
    }, 700);
  }
  var NUM_TEXT = {
    checking: 'Checking WhatsApp…',
    yes: 'On WhatsApp: tap to start',
    no: 'Not on WhatsApp',
    error: 'Could not check: tap to try anyway',
  };

  // ---------- Chat actions: mark unread, archive ----------
  function findChat(id) {
    for (var i = 0; i < state.chats.length; i++) { if (state.chats[i].id === id) return state.chats[i]; }
    return null;
  }

  // A lead card's number → its chat. A lid only exists on the WhatsApp number
  // that issued it, so one from another session reloads the inbox there
  // (?open=). A phone with no chat in the loaded list asks WhatsApp which chat
  // it is — the thread may be stored under a lid.
  function openNumberChat(n, btn) {
    var lid = n.is_lid ? n.identifier : '';
    if (lid && n.session && n.session !== SESSION) {
      window.location.href = '/waha/wa-chats/?session=' + encodeURIComponent(n.session) +
        '&open=' + encodeURIComponent(lid + '@lid');
      return;
    }
    var hit = (lid && findChat(lid + '@lid')) || (n.phone && findChat(n.phone + '@c.us'));
    if (hit) { openChat(hit.id, hit.name, hit.hasName); return; }
    if (lid) { openChat(lid + '@lid', n.phone ? n.display : '', false); return; }
    btn.disabled = true;
    fetch(wq('/waha/wa-chats/check-number/?phone=' + encodeURIComponent(n.phone)), { credentials: 'same-origin' })
      .then(function (r) { return r.json().catch(function () { return null; }); })
      .then(function (j) {
        btn.disabled = false;
        if (!j || !j.ok) { showError((j && j.error) || 'Could not check ' + n.display + ' on WhatsApp.'); return; }
        if (!j.exists) { showError(n.display + ' is not on WhatsApp.'); return; }
        var c = j.chatId && findChat(j.chatId);
        if (c) openChat(c.id, c.name, c.hasName);
        else openChat(j.chatId || n.phone + '@c.us', n.display, false);
      })
      .catch(function () { btn.disabled = false; showError('Could not check ' + n.display + ' on WhatsApp.'); });
  }
  // ?open=<chatId>: arrive with that chat open (openNumberChat on another session).
  function openFromUrl() {
    var id = '';
    try { id = new URLSearchParams(window.location.search).get('open') || ''; } catch (e) { return; }
    if (!/^[\w.-]+@(?:c\.us|lid)$/.test(id)) return;
    var c = findChat(id);
    if (c) openChat(c.id, c.name, c.hasName);
    else openChat(id, /@c\.us$/.test(id) ? '+' + id.split('@')[0] : '', false);
  }
  function openChatMenu(anchor) {
    var id = state.activeChatId;
    if (!id) return;
    var c = findChat(id);
    var archived = !!(c && c.archived);
    openPop(anchor, function (p) {
      menuItem(p, 'Mark as unread', function () { chatAction(id, 'unread'); });
      menuItem(p, archived ? 'Unarchive chat' : 'Archive chat', function () { chatAction(id, archived ? 'unarchive' : 'archive'); });
    });
  }
  function chatAction(id, action) {
    postJSON('/waha/wa-chats/chat-action/', { session: SESSION, chatId: id, action: action })
      .then(function (j) {
        if (!j || !j.ok) { showError('Could not ' + (action === 'unread' ? 'mark it unread' : action + ' it') + ': ' + ((j && j.error) || '')); return; }
        var c = findChat(id);
        if (c) {
          if (action === 'archive') c.archived = true;
          else if (action === 'unarchive') c.archived = false;
          else c.unread = -1;
        }
        // Leaving it open would read it again (unread) or keep a hidden chat on screen (archive).
        if (action !== 'unarchive' && state.activeChatId === id) closeChat();
        renderList();
        showInfo({ archive: 'Chat archived. Find it under Archived.', unarchive: 'Chat moved back to the inbox.',
                   unread: 'Marked as unread.' }[action]);
      })
      .catch(function (e) { showError('Chat action error: ' + e); });
  }
  function closeChat() {
    stopRecording(true);
    clearAttachment();
    cancelReply();
    state.activeChatId = null;
    state.activeChatName = null;
    state.msgs = [];
    var av = $('wa-conv-avatar');
    av.innerHTML = '';
    av.textContent = '--';
    av.style.background = '';
    $('wa-conv-name').textContent = 'Select a chat';
    $('wa-conv-sub').textContent = '';
    $('wa-msgs').innerHTML = '<div class="wa-empty">No chat selected.</div>';
    ['wa-comp-ta', 'wa-comp-send', 'wa-comp-attach', 'wa-comp-mic', 'wa-chat-more', 'wa-info-toggle']
      .forEach(function (k) { $(k).disabled = true; });
    setPanelOpen(panel.open);   // hides it (no chat) without changing the saved preference
    Array.prototype.forEach.call(document.querySelectorAll('.wa-row--active'), function (r) { r.classList.remove('wa-row--active'); });
  }

  // WhatsApp ack: -1 failed, 0 pending, 1 sent, 2 delivered, 3 read, 4 played.
  function setTick(tm, ack) {
    var old = tm.querySelector('.wa-bubble__tick');
    if (old) old.remove();
    if (ack === null || ack === undefined) return;
    var t = document.createElement('span');
    var n = parseInt(ack, 10);
    t.className = 'wa-bubble__tick' + (n >= 3 ? ' wa-bubble__tick--read' : n < 0 ? ' wa-bubble__tick--err' : '');
    t.textContent = n < 0 ? '!' : n === 0 ? '🕓' : n === 1 ? '✓' : '✓✓';
    t.title = ['Failed', 'Pending', 'Sent', 'Delivered', 'Read', 'Played'][Math.min(n, 4) + 1] || '';
    tm.appendChild(t);
  }

  function msgKey(m) { return m.waha_id || ('db' + m.id); }

  // Background refresh (the 30s poll): fetch the newest page and append only
  // messages not already on screen. Never blanks the pane, never re-renders an
  // unchanged chat, and only follows to the bottom if the reader was already there.
  function refreshMessages() {
    if (!state.activeChatId || state.msgsLoading) return;
    var chatIdAtCall = state.activeChatId;
    var url = wq('/waha/wa-chats/?messages=1&chatId=' + encodeURIComponent(chatIdAtCall) + '&limit=50');
    fetch(url, { credentials: 'same-origin' })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (data) {
        if (!data || !data.ok || chatIdAtCall !== state.activeChatId || state.msgsLoading) return;
        var known = {};
        state.msgs.forEach(function (m) { known[msgKey(m)] = m; });
        var box = $('wa-msgs');
        // Ticks move on (sent → delivered → read) on messages already drawn.
        (data.messages || []).forEach(function (m) {
          var k = known[msgKey(m)];
          if (!k || m.direction !== 'outbound' || m.ack == null || m.ack === k.ack) return;
          k.ack = m.ack;
          var row = box.querySelector('.wa-msg[data-key="' + String(msgKey(m)).replace(/"/g, '') + '"] .wa-bubble__time');
          if (row) setTick(row, m.ack);
        });
        var fresh = (data.messages || []).filter(function (m) { return !known[msgKey(m)]; });
        if (!fresh.length) return;
        if (fresh.some(function (m) { return m.direction !== 'outbound'; })) markChatRead(chatIdAtCall, true);
        var atBottom = box.scrollHeight - box.scrollTop - box.clientHeight < 80;
        var empty = box.querySelector('.wa-empty');
        if (empty) empty.remove();
        // A just-sent message was drawn locally; its real copy is in `fresh` now.
        if (fresh.some(function (m) { return m.direction === 'outbound'; })) {
          Array.prototype.forEach.call(box.querySelectorAll('.wa-msg--local'), function (n) { n.remove(); });
        }
        fresh.forEach(function (m) { box.appendChild(msgRow(m)); });
        state.msgs = state.msgs.concat(fresh);
        if (atBottom) box.scrollTop = box.scrollHeight;
      })
      .catch(function () { /* next poll retries */ });
  }

  function renderMessages(msgs) {
    hideError();
    var box = $('wa-msgs');
    box.innerHTML = '';
    if (!msgs.length) {
      box.innerHTML = '<div class="wa-empty">No messages yet.</div>';
      return;
    }
    msgs.forEach(function (m) { box.appendChild(msgRow(m)); });
    box.scrollTop = box.scrollHeight;
  }

  function appendOutgoingLocal(text, reply) {
    var box = $('wa-msgs');
    if (box.querySelector('.wa-empty')) box.innerHTML = '';
    var row = document.createElement('div');
    row.className = 'wa-msg wa-msg--out wa-msg--local';
    var bubble = document.createElement('div');
    bubble.className = 'wa-bubble wa-bubble--out';
    if (reply) bubble.appendChild(quoteBlock({ id: '', who: reply.who, body: reply.body }, false));
    var s = document.createElement('span');
    s.textContent = text;
    bubble.appendChild(s);
    var tm = document.createElement('div');
    tm.className = 'wa-bubble__time';
    tm.textContent = fmtShortTime(Math.floor(Date.now() / 1000));
    setTick(tm, 0);
    bubble.appendChild(tm);
    row.appendChild(bubble);
    box.appendChild(row);
    box.scrollTop = box.scrollHeight;
    return row;
  }

  function showError(msg) {
    var el = $('wa-err');
    el.classList.remove('wa-err--ok');
    el.textContent = msg;
    el.style.display = 'block';
    setTimeout(hideError, 5000);
  }
  function showInfo(msg) {
    showError(msg);
    $('wa-err').classList.add('wa-err--ok');
  }
  function hideError() {
    var el = $('wa-err');
    el.style.display = 'none';
    el.textContent = '';
  }

  // ---------- Send ----------
  function sendMessage() {
    if (!state.activeChatId) return;
    var ta = $('wa-comp-ta');
    var txt = (ta.value || '').trim();
    if (attach.file) {
      var file = attach.file;
      var rp = state.replyTo;
      ta.value = '';
      cancelReply();
      clearAttachment();
      uploadMedia(file, txt, rp, false);
      return;
    }
    if (!txt) return;
    ta.value = '';
    var reply = state.replyTo;
    cancelReply();
    postText(txt, reply);
  }

  // Draw the bubble now with a pending clock; the server round trip can sit
  // behind slow inbox polls, and the writer should not wait on it to type on.
  // Shared by the composer and "Send reminder" so both send the same way.
  function postText(txt, reply) {
    var row = appendOutgoingLocal(txt, reply);
    var tm = row.querySelector('.wa-bubble__time');
    var sendBody = { to: state.activeChatId, text: txt, session: SESSION };
    if (reply) sendBody.reply_to = reply.waha_id;

    fetch('/waha/wa-chats/send/', {
      method: 'POST',
      credentials: 'same-origin',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': CSRF,
      },
      body: JSON.stringify(sendBody),
    })
      .then(function (r) {
        return r.text().then(function (raw) {
          var j = null;
          try { j = JSON.parse(raw); } catch (e) {}
          return { ok: r.ok, status: r.status, body: j, raw: raw };
        });
      })
      .then(function (res) {
        if (res.ok && res.body && res.body.ok) {
          setTick(tm, 1);
        } else {
          failLocal(row, tm, txt);
          showError('Send failed: ' + (res.body && (res.body.waha || res.body.error) || res.status));
        }
      })
      .catch(function (e) {
        failLocal(row, tm, txt);
        showError('Send error: ' + e);
      });
  }

  // A failed bubble stays on screen (the poll only clears pending locals) and
  // its text goes back in the composer unless the writer has moved on.
  function failLocal(row, tm, txt) {
    row.classList.remove('wa-msg--local');
    setTick(tm, -1);
    var ta = $('wa-comp-ta');
    if (!ta.value) ta.value = txt;
  }

  // ---------- Resync ----------
  function resyncActive() {
    if (!state.activeChatId) return;
    var btn = $('wa-resync');
    btn.disabled = true;
    fetch(wq('/waha/wa-chats/resync/?chatId=' + encodeURIComponent(state.activeChatId)), {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'X-CSRFToken': CSRF },
    })
      .then(function (r) { return r.json().then(function (j) { return { ok: r.ok, body: j }; }); })
      .then(function (res) {
        btn.disabled = false;
        if (res.ok && res.body && res.body.ok) {
          loadMessages();
        } else {
          showError('Resync failed: ' + (res.body && res.body.error || ''));
        }
      })
      .catch(function (e) {
        btn.disabled = false;
        showError('Resync error: ' + e);
      });
  }

  // ---------- Poll ----------
  function poll() {
    // A background tab's refresh still holds a server worker for as long as
    // WAHA takes; skip it and catch up when the tab is shown again.
    if (document.hidden) return;
    loadChats();
    if (state.activeChatId) refreshMessages();
  }


  // ---------- Contact panel (info · CRM leads · media) ----------
  var CSRF = '%CSRF%';
  var SWATCH = { grey: '#9aa5ad', slate: '#5b6b78', blue: '#3b82f6', teal: '#14b8a6', green: '#22c55e',
                 forest: '#15803d', violet: '#8b5cf6', amber: '#f59e0b', red: '#ef4444' };
  var MEDIA_TABS = [['photos', 'Photos'], ['videos', 'Videos'], ['files', 'Files'],
                    ['links', 'Links'], ['voice', 'Voice'], ['audio', 'Audio']];
  var panel = { open: true, loadedFor: null, kind: 'photos', offset: 0, counts: {}, data: null };
  try {
    var savedOpen = localStorage.getItem('waInfoOpen');
    panel.open = savedOpen === null ? window.innerWidth > 1200 : savedOpen === '1';
  } catch (e) { /* storage blocked — keep default */ }

  function el(tag, cls, text) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text != null) n.textContent = text;
    return n;
  }
  function fmtDate(ts, withTime) {
    if (!ts) return '—';
    var o = { timeZone: 'Asia/Qatar', day: '2-digit', month: 'short', year: 'numeric' };
    if (withTime) { o.hour = '2-digit'; o.minute = '2-digit'; }
    return new Date(ts * 1000).toLocaleString('en-GB', o);
  }

  function setPanelOpen(open) {
    panel.open = open;
    try { localStorage.setItem('waInfoOpen', open ? '1' : '0'); } catch (e) { /* ignore */ }
    $('wa-info').hidden = !(open && state.activeChatId);
    $('wa-info-toggle').setAttribute('aria-expanded', open ? 'true' : 'false');
    if (open && state.activeChatId && panel.loadedFor !== state.activeChatId) loadPanel();
  }

  function loadPanel() {
    var chatId = state.activeChatId;
    if (!chatId) return;
    panel.loadedFor = chatId;
    $('wa-info-who').innerHTML = '<div class="wa-empty">Loading…</div>';
    $('wa-info-accounts').hidden = true;
    $('wa-info-leads').innerHTML = '';
    $('wa-info-labels').hidden = true;  // the previous chat's ticks must not show
    $('wa-media-tabs').innerHTML = '';
    $('wa-media-body').innerHTML = '';
    var url = wq('/waha/wa-chats/?info=1&chatId=' + encodeURIComponent(chatId) +
                 '&name=' + encodeURIComponent(state.activeChatName || ''));
    // Returned so the media viewer can repaint its document panel once fresh data lands.
    return fetch(url, { credentials: 'same-origin' })
      .then(function (r) { return r.json(); })
      .then(function (d) {
        if (state.activeChatId !== chatId) return;
        if (!d.ok) throw new Error(d.error || 'failed');
        panel.data = d;
        panel.counts = d.media_counts || {};
        renderWho(d);
        renderAccounts(d);
        renderWaLabels(d);
        renderLeads(d);
        var first = MEDIA_TABS.filter(function (t) { return panel.counts[t[0]] > 0; })[0];
        if (!(panel.counts[panel.kind] > 0)) panel.kind = first ? first[0] : 'photos';
        renderMediaTabs();
        loadMedia(false);
      })
      .catch(function () {
        if (state.activeChatId !== chatId) return;
        panel.loadedFor = null;
        $('wa-info-who').innerHTML = '<div class="wa-empty">Could not load contact info.</div>';
      });
  }

  // What the save did on our other numbers, as a short trailing note.
  function syncNote(rows) {
    if (!Array.isArray(rows) || !rows.length) return '';
    var parts = [];
    rows.forEach(function (r) {
      var moved = (r.added || []).concat(r.removed || []);
      if (r.error) parts.push(r.session + ': ' + r.error);
      else if (moved.length) parts.push(r.session + ': ' + moved.join(', '));
    });
    return parts.length ? ' · ' + parts.join(' · ') : '';
  }

  // WhatsApp labels for the open chat. Ticks are read fresh from WAHA; saving
  // sends only what changed and the server applies it to WhatsApp's current set.
  function renderWaLabels(d) {
    var box = $('wa-info-labels');
    var chatId = state.activeChatId;
    box.innerHTML = '';
    if (noLabels || !state.labels.length) { box.hidden = true; return; }
    box.hidden = false;
    // The heading is only there to introduce the full checkbox list; once the
    // chat has labels the chips speak for themselves.
    var title = el('div', 'wa-info__sec-title', 'WhatsApp labels');
    box.appendChild(title);
    // One line: the chat's labels, then the Change button beside them.
    var line = el('div', 'wa-wlabels__line');
    var list = el('div', 'wa-wlabels');
    line.appendChild(list);
    box.appendChild(line);
    var current = new Set(chatLabels(chatId).map(function (l) { return String(l.id); }));
    var touched = false;
    var savedHere = false;  // once saved, the panel's live read must not undo it
    function addRow(lb, checked) {
      var row = el('label', 'wa-wlabels__row');
      var cb = el('input');
      cb.type = 'checkbox';
      cb.value = lb.id;
      cb.checked = !!checked;
      cb.disabled = !d.can_label;
      var dot = el('span', 'wa-label-chip__dot');
      dot.style.background = lb.colorHex || '#8696a0';
      row.appendChild(cb); row.appendChild(dot); row.appendChild(el('span', null, lb.name));
      list.appendChild(row);
      return cb;
    }
    visibleLabels(current).forEach(function (lb) { addRow(lb, current.has(lb.id)); });
    function boxes() { return Array.prototype.slice.call(list.querySelectorAll('input')); }
    function setTicks() { boxes().forEach(function (cb) { cb.checked = current.has(cb.value); }); }
    // A labelled chat shows only its labels; "Change" opens the full list.
    var editing = !current.size;
    var editBtn = null, bar = null, cancelBtn = null, make = null;
    function applyMode() {
      if (!current.size) editing = true;
      var view = !editing || !d.can_label;
      list.classList.toggle('wa-wlabels--view', view);
      boxes().forEach(function (cb) {
        cb.parentElement.hidden = view && !current.has(cb.value);
        cb.disabled = view;
      });
      if (view && !current.size) list.hidden = true; else list.hidden = false;
      title.hidden = view && !!current.size;
      if (editBtn) editBtn.hidden = editing;
      if (bar) bar.hidden = !editing;
      if (make) make.hidden = !editing;
      if (cancelBtn) cancelBtn.hidden = !current.size;
    }

    // The cached map can be up to a day old — read this chat's labels live.
    fetch(wq('/waha/wa-chats/?chat_labels=1&chatId=' + encodeURIComponent(chatId)), { credentials: 'same-origin' })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (data) {
        var arr = data && data.ok ? data.labels : null;
        if (!Array.isArray(arr) || state.activeChatId !== chatId || savedHere) return;
        applyChatLabels(chatId, arr);
        current = new Set(arr.map(function (l) { return String(l.id); }));
        if (!touched) { setTicks(); editing = !current.size; applyMode(); }
      })
      .catch(function () { /* keep the cached ticks */ });

    if (!d.can_label) {
      applyMode();
      box.appendChild(el('div', 'wa-note', 'Read-only: sign in to the staff portal with CRM access to change labels.'));
      return;
    }
    editBtn = el('button', 'wa-btn wa-btn--sm wa-btn--ghost wa-wlabels__edit', 'Change');
    editBtn.type = 'button';
    line.appendChild(editBtn);
    bar = el('div', 'wa-wlabels__bar');
    var btn = el('button', 'wa-btn wa-btn--sm', 'Save to WhatsApp');
    btn.type = 'button';
    btn.disabled = true;
    cancelBtn = el('button', 'wa-btn wa-btn--sm wa-btn--ghost', 'Cancel');
    cancelBtn.type = 'button';
    var msg = el('span', 'wa-note');
    bar.appendChild(btn); bar.appendChild(cancelBtn); bar.appendChild(msg);
    box.appendChild(bar);
    var saved = el('div', 'wa-note');
    box.appendChild(saved);

    // A label this number does not have yet. It is created on WhatsApp straight
    // away — a label belongs to the number — and then simply ticked, so the one
    // "Save to WhatsApp" below is still what puts it on this chat.
    if (CAN_MAKE_LABEL) {
      make = el('div', 'wa-mk');
      var openBtn = el('button', 'wa-btn wa-btn--sm wa-btn--ghost', '+ New label');
      openBtn.type = 'button';
      var form = el('div', 'wa-mk__form');
      form.hidden = true;
      var name = el('input', 'wa-search wa-mk__name');
      name.type = 'text';
      name.placeholder = 'Label name';
      name.maxLength = 100;
      var swatches = el('div', 'wa-mk__swatches');
      var color = LABEL_COLORS.length > 4 ? 4 : 0;
      LABEL_COLORS.forEach(function (hex, i) {
        var sw = el('button', 'wa-mk__sw');
        sw.type = 'button';
        sw.style.background = hex;
        sw.title = hex;
        sw.setAttribute('aria-pressed', i === color ? 'true' : 'false');
        sw.addEventListener('click', function () {
          color = i;
          Array.prototype.forEach.call(swatches.children, function (other, j) {
            other.setAttribute('aria-pressed', j === i ? 'true' : 'false');
          });
        });
        swatches.appendChild(sw);
      });
      var makeBtn = el('button', 'wa-btn wa-btn--sm', 'Create');
      makeBtn.type = 'button';
      var dropBtn = el('button', 'wa-btn wa-btn--sm wa-btn--ghost', 'Cancel');
      dropBtn.type = 'button';
      var makeMsg = el('span', 'wa-note');
      form.appendChild(name); form.appendChild(makeBtn); form.appendChild(dropBtn);
      form.appendChild(makeMsg); form.appendChild(swatches);
      make.appendChild(openBtn); make.appendChild(form);
      box.appendChild(make);

      function showForm(open) {
        form.hidden = !open;
        openBtn.hidden = open;
        makeMsg.textContent = '';
        if (open) name.focus();
      }
      openBtn.addEventListener('click', function () { showForm(true); });
      dropBtn.addEventListener('click', function () { name.value = ''; showForm(false); });
      name.addEventListener('keydown', function (e) {
        if (e.key === 'Enter') { e.preventDefault(); makeBtn.click(); }
      });
      makeBtn.addEventListener('click', function () {
        var wanted = name.value.trim();
        if (!wanted) { makeMsg.textContent = 'Give the label a name.'; name.focus(); return; }
        makeBtn.disabled = true; makeBtn.textContent = 'Creating…'; makeMsg.textContent = '';
        fetch('/waha/wa-chats/create-label/', {
          method: 'POST',
          credentials: 'same-origin',
          headers: { 'Content-Type': 'application/json', 'X-CSRFToken': CSRF },
          body: JSON.stringify({ session: SESSION, name: wanted, color: color }),
        })
          .then(function (r) { return r.json().catch(function () { return { ok: false, error: 'HTTP ' + r.status }; }); })
          .then(function (j) {
            makeBtn.disabled = false; makeBtn.textContent = 'Create';
            if (!j.ok || !j.label) { makeMsg.textContent = j.error || 'Could not create it'; return; }
            var lb = j.label;
            if (!state.labels.some(function (x) { return String(x.id) === lb.id; })) {
              state.labels.push(lb);
              if (!state.labelMap) state.labelMap = {};
              if (!state.labelMap[lb.id]) state.labelMap[lb.id] = new Set();
              writeLabelCache(state.labelMap, state.labels);
              populateLabelSelect();  // it can be filtered on straight away
            }
            var existing = boxes().filter(function (cb) { return cb.value === lb.id; })[0];
            if (existing) existing.checked = true;
            else addRow(lb, true);
            touched = true;
            btn.disabled = false;   // "Save to WhatsApp" now has something to do
            name.value = '';
            showForm(false);
            saved.textContent = '';
            msg.textContent = j.existing
              ? '“' + lb.name + '” already exists on this number — ticked it.'
              : '“' + lb.name + '” created. Save to put it on this chat.';
          })
          .catch(function () {
            makeBtn.disabled = false; makeBtn.textContent = 'Create';
            makeMsg.textContent = 'Network error';
          });
      });
    }
    applyMode();
    editBtn.addEventListener('click', function () { editing = true; saved.textContent = ''; applyMode(); });
    cancelBtn.addEventListener('click', function () {
      setTicks(); touched = false; editing = false;
      btn.disabled = true; msg.textContent = '';
      applyMode();
    });
    function diff() {
      var add = [], remove = [];
      boxes().forEach(function (cb) {
        if (cb.checked && !current.has(cb.value)) add.push(cb.value);
        if (!cb.checked && current.has(cb.value)) remove.push(cb.value);
      });
      return { add: add, remove: remove };
    }
    list.addEventListener('change', function () {
      touched = true;
      var x = diff();
      btn.disabled = !(x.add.length || x.remove.length);
      msg.textContent = '';
    });
    btn.addEventListener('click', function () {
      var x = diff();
      btn.disabled = true; btn.textContent = 'Saving…'; msg.textContent = '';
      fetch('/waha/wa-chats/set-labels/', {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': CSRF },
        body: JSON.stringify({ session: SESSION, chatId: chatId, add: x.add, remove: x.remove }),
      })
        .then(function (r) { return r.json().catch(function () { return { ok: false, error: 'HTTP ' + r.status }; }); })
        .then(function (j) {
          btn.textContent = 'Save to WhatsApp';
          if (!j.ok) { btn.disabled = false; msg.textContent = j.error || 'Could not save'; return; }
          applyChatLabels(chatId, j.labels);
          current = new Set(j.labels.map(function (l) { return String(l.id); }));
          touched = false;
          savedHere = true;
          setTicks();
          editing = !current.size;
          applyMode();
          var note = (j.confirmed === false ? 'Sent to WhatsApp — not confirmed yet'
                                            : 'Saved to WhatsApp') + syncNote(j.sync);
          if (editing) msg.textContent = note;
          else saved.textContent = note;
        })
        .catch(function () { btn.disabled = false; btn.textContent = 'Save to WhatsApp'; msg.textContent = 'Network error'; });
    });
  }

  // Put one chat's labels into the label map/cache and redraw the list chips.
  function applyChatLabels(chatId, labels) {
    if (!state.labelMap) state.labelMap = {};
    var ids = new Set((labels || []).map(function (l) { return String(l.id); }));
    var changed = false;
    state.labels.forEach(function (lb) {
      var set = state.labelMap[lb.id] || (state.labelMap[lb.id] = new Set());
      if (ids.has(lb.id) && !set.has(chatId)) { set.add(chatId); changed = true; }
      if (!ids.has(lb.id) && set.has(chatId)) { set.delete(chatId); changed = true; }
    });
    if (!changed) return;
    state.labelsByChat = buildLabelsByChat(state.labelMap, state.labels);
    writeLabelCache(state.labelMap, state.labels);
    renderList();
  }

  // Top of the panel: one compact row — avatar, name/phone, lead label — that
  // expands into the full contact details.
  function renderWho(d) {
    var info = d.info;
    var box = $('wa-info-who');
    box.innerHTML = '';
    var det = el('details', 'wa-who');
    var sum = el('summary', 'wa-who__sum');
    var av = el('div', 'wa-who__av', initials(state.activeChatName));
    av.style.background = avatarColor(state.activeChatId);
    addPhoto(av, state.activeChatId);
    sum.appendChild(av);
    var txt = el('div', 'wa-who__txt');
    // A chat with no saved name is titled by its number — show the name the
    // person set in WhatsApp instead, marked with "~" as WhatsApp Web does.
    var title = state.activeChatName || info.chat_id;
    var leadTitle = (d.leads && d.leads[0] && (d.leads[0].company || d.leads[0].name)) ? d.leads[0].name : '';
    if (/^Lead #\d+$/.test(leadTitle)) leadTitle = '';  // an unnamed lead is not a name
    if (!info.saved_name && leadTitle && (/^[+\d\s]+$/.test(title) || title.charAt(0) === '~')) title = leadTitle;
    else if (info.push_name && /^[+\d\s]+$/.test(title)) title = '~ ' + info.push_name;
    txt.appendChild(el('div', 'wa-who__name', title));
    txt.appendChild(el('div', 'wa-who__phone', info.kind === 'group' ? 'Group chat'
      : info.phone ? '+' + info.phone : 'Number hidden (private id)'));
    sum.appendChild(txt);
    if (info.kind === 'person' && d.leads_visible) {
      var leads = d.leads || [];
      var lab = el('span', 'wa-who__label' + (leads.length ? '' : ' wa-who__label--none'));
      if (leads.length) {
        var dot = el('span', 'wa-lead__dot');
        dot.style.background = SWATCH[leads[0].swatch] || SWATCH.grey;
        lab.appendChild(dot);
        lab.appendChild(el('span', null, leads[0].stage + (leads.length > 1 ? ' +' + (leads.length - 1) : '')));
        lab.title = leads.map(function (l) { return '#' + l.id + ' ' + l.name + ' — ' + l.stage + ' (' + l.category + ')'; }).join('\n');
      } else {
        lab.appendChild(el('span', null, 'No lead'));
      }
      sum.appendChild(lab);
    }
    sum.appendChild(el('span', 'wa-who__chev', '▾'));
    det.appendChild(sum);

    var wrap = el('div', 'wa-who__detail');
    var kv = el('dl', 'wa-kv');
    // Every row is always listed; a value we don't have stays blank rather than
    // the row disappearing, so the layout is the same for every chat.
    function row(k, v) { kv.appendChild(el('dt', null, k)); kv.appendChild(el('dd', null, v || v === 0 ? String(v) : '')); }
    row('On number', ($('wa-sess-chip') || {}).textContent || SESSION);
    if (info.kind === 'group') {
      row('Group id', info.chat_id);
    } else {
      row('Phone', info.phone ? '+' + info.phone : '');
      row('WhatsApp name', info.push_name);
      row('Saved as', info.saved_name);
      row('LID', info.lid);
    }
    row('Messages', info.messages ? info.messages + ' stored · ' + info.inbound + ' received' : '');
    row('First message', info.first_at ? fmtDate(info.first_at, false) : '');
    row('Last message', info.last_at ? fmtDate(info.last_at, true) : '');
    wrap.appendChild(kv);
    det.appendChild(wrap);
    box.appendChild(det);
  }

  // POST to a CRM endpoint as form data. The workforce gate answers an account
  // without that desk with a redirect/HTML page, so a non-JSON reply is "no access".
  function postForm(url, fields) {
    var fd = new FormData();
    Object.keys(fields).forEach(function (k) { fd.append(k, fields[k]); });
    return fetch(url, { method: 'POST', credentials: 'same-origin', body: fd,
                        headers: { 'X-CSRFToken': CSRF, 'X-Requested-With': 'XMLHttpRequest' } })
      .then(function (r) {
        return r.json().catch(function () { return { success: false, error: 'Your account cannot do this here (HTTP ' + r.status + ').' }; });
      });
  }

  function leadHead(l) {
    var top = el('div', 'wa-lead__top');
    var a = el('a', 'wa-lead__name', l.name);
    a.href = l.url; a.target = '_blank'; a.rel = 'noopener';
    top.appendChild(a);
    top.appendChild(el('span', 'wa-lead__id', '#' + l.id));
    if (l.how) top.appendChild(el('span', 'wa-lead__how',
      l.how === 'linked' ? (l.this_label || 'Linked number') : 'Primary number'));
    return top;
  }

  // Compact card — suggestions and search results.
  function leadCard(l, opts) {
    var card = el('div', 'wa-lead');
    card.appendChild(leadHead(l));
    var st = el('div', 'wa-lead__stage');
    var dot = el('span', 'wa-lead__dot');
    dot.style.background = SWATCH[l.swatch] || SWATCH.grey;
    st.appendChild(dot);
    st.appendChild(el('span', null, l.stage + ' · ' + l.category + ' lead'));
    card.appendChild(st);
    var meta = [];
    if (l.company) meta.push(l.company);
    if (l.phone) meta.push(l.phone);
    if (l.sources) meta.push('Source: ' + l.sources);
    meta.push('Assigned: ' + (l.assigned || 'nobody'));
    if (l.followup) meta.push('Follow-up: ' + l.followup);
    if (l.created) meta.push('Created: ' + l.created);
    card.appendChild(el('div', 'wa-lead__meta', meta.join(' · ')));
    if (opts && opts.link) {
      var act = el('div', 'wa-lead__actions');
      // Who this number is to the lead — the owner, the office… — kept on the link.
      var lab = el('input', 'wa-inp wa-lead__label-inp');
      lab.placeholder = 'Who is this? e.g. Office';
      lab.maxLength = 40;
      lab.setAttribute('list', 'wa-label-options');
      var btn = el('button', 'wa-btn wa-btn--sm', 'Link this chat');
      btn.type = 'button';
      btn.addEventListener('click', function () { linkLead(l, btn, lab.value.trim()); });
      act.appendChild(lab);
      act.appendChild(btn);
      card.appendChild(act);
    }
    return card;
  }

  // Working card — a connected lead, editable in place through the CRM's own endpoints.
  function workCard(l, staff) {
    var card = el('div', 'wa-lead wa-lead--work');
    card.appendChild(leadHead(l));

    var flags = el('div', 'wa-lead__flags');
    function flag(t, cls) { flags.appendChild(el('span', 'wa-flag' + (cls ? ' wa-flag--' + cls : ''), t)); }
    flag(l.category + ' lead');
    if (l.stage_days != null) flag(l.stage_days + 'd in stage');
    if (!l.is_open) flag('Closed', 'ok');
    if (l.overdue) flag('Follow-up overdue', 'warn');
    else if (l.is_open && !l.followup) flag('No follow-up set', 'warn');
    if (l.is_open && !l.assigned) flag('Unassigned', 'warn');
    if (l.pinned) flag('Stage pinned');
    card.appendChild(flags);

    // Every number the lead talks from (owner, office…) and the account on each.
    if ((l.numbers || []).length) {
      var chatDigits = String(state.activeChatId).split('@')[0];
      var chatPhone = (panel.data && panel.data.info && panel.data.info.phone) || '';
      var nums = el('ul', 'wa-nums');
      l.numbers.forEach(function (n) {
        var li = el('li', 'wa-nums__row');
        li.appendChild(el('span', 'wa-nums__label', n.label));
        // A lid shows its real number when the directory knows it; the lid stays on hover.
        var idEl = el('span', 'wa-nums__id', n.phone ? n.display : 'Private id ' + n.identifier);
        if (n.is_lid && n.phone) idEl.title = 'WhatsApp private id ' + n.identifier;
        li.appendChild(idEl);
        var here = n.identifier === chatDigits || (chatPhone && n.phone && n.phone.slice(-8) === chatPhone.slice(-8));
        // "this chat" or Open chat sits right beside the number; accounts follow.
        if (here) li.appendChild(el('span', 'wa-flag wa-flag--ok', 'this chat'));
        else {
          var go = el('button', 'wa-btn wa-btn--sm wa-btn--ghost wa-nums__open', 'Open chat');
          go.type = 'button';
          go.addEventListener('click', function () { openNumberChat(n, go); });
          li.appendChild(go);
        }
        (n.accounts || []).forEach(function (a) {
          var acc = el('span', 'wa-nums__acct', '\u{1F464} ' + a.name + ' · ' + a.role);
          acc.title = '@' + a.username;
          li.appendChild(acc);
        });
        nums.appendChild(li);
      });
      card.appendChild(nums);
    }

    var msg = el('div', 'wa-lead__msg');
    function say(text, ok) { msg.textContent = text || ''; msg.className = 'wa-lead__msg' + (text ? (ok ? ' wa-lead__msg--ok' : ' wa-lead__msg--err') : ''); }

    var form = el('div', 'wa-lead__form');
    // Stage
    var stWrap = el('div', 'wa-lead__form--full');
    stWrap.appendChild(el('label', null, 'Stage'));
    var stSel = el('select', 'wa-inp');
    (l.stages || []).forEach(function (s) {
      var o = el('option', null, s.label); o.value = s.key; if (s.key === l.stage_key) o.selected = true; stSel.appendChild(o);
    });
    stSel.addEventListener('change', function () {
      var label = stSel.options[stSel.selectedIndex].text;
      if (!confirm('Move lead #' + l.id + ' to "' + label + '"?')) { stSel.value = l.stage_key; return; }
      stSel.disabled = true; say('Saving…', true);
      postForm(l.urls.stage, { stage: stSel.value }).then(function (j) {
        stSel.disabled = false;
        if (!j.success) { stSel.value = l.stage_key; say(j.error || 'Could not move the lead'); return; }
        l.stage_key = j.stage;
        say(j.warning || ('Moved to ' + j.stage_display), !j.warning);
        refreshPanelSoon();
      }).catch(function () { stSel.disabled = false; stSel.value = l.stage_key; say('Network error'); });
    });
    stWrap.appendChild(stSel);
    form.appendChild(stWrap);
    // Assignee
    var asWrap = el('div');
    asWrap.appendChild(el('label', null, 'Assigned to'));
    var asSel = el('select', 'wa-inp');
    var none = el('option', null, 'Unassigned'); none.value = ''; asSel.appendChild(none);
    (staff || []).forEach(function (u) {
      var o = el('option', null, u.name); o.value = String(u.id); if (String(u.id) === String(l.assigned_id)) o.selected = true; asSel.appendChild(o);
    });
    asSel.addEventListener('change', function () {
      asSel.disabled = true; say('Saving…', true);
      postForm(l.urls.update, { assigned_to: asSel.value }).then(function (j) {
        asSel.disabled = false;
        if (!j.success) { asSel.value = String(l.assigned_id); say(j.error || 'Could not reassign'); return; }
        l.assigned_id = asSel.value; say(j.assigned_to ? 'Assigned to ' + j.assigned_to : 'Assignment cleared', true);
      }).catch(function () { asSel.disabled = false; say('Network error'); });
    });
    asWrap.appendChild(asSel);
    form.appendChild(asWrap);
    // Follow-up
    var fuWrap = el('div');
    fuWrap.appendChild(el('label', null, 'Follow-up'));
    var fu = el('input', 'wa-inp' + (l.overdue ? ' wa-inp--overdue' : ''));
    fu.type = 'date'; fu.value = l.followup || '';
    fu.addEventListener('change', function () {
      fu.disabled = true; say('Saving…', true);
      postForm(l.urls.update, { next_followup_at: fu.value }).then(function (j) {
        fu.disabled = false;
        if (!j.success) { fu.value = l.followup || ''; say(j.error || 'Could not save the date'); return; }
        l.followup = j.next_followup_at; fu.classList.remove('wa-inp--overdue');
        say(j.next_followup_at ? 'Follow-up set to ' + j.next_followup_at : 'Follow-up cleared', true);
      }).catch(function () { fu.disabled = false; say('Network error'); });
    });
    fuWrap.appendChild(fu);
    form.appendChild(fuWrap);
    card.appendChild(form);
    if (l.docs) card.appendChild(docsBlock(l));

    // Facts
    var facts = el('dl', 'wa-lead__facts');
    function fact(k, v) { if (!v && v !== 0) return; facts.appendChild(el('dt', null, k)); facts.appendChild(el('dd', null, String(v))); }
    fact('Company', l.company);
    fact('Phone', l.phone);
    fact('Source', l.sources);
    fact('Product', l.product);
    fact('Business', l.business);
    fact('Driver', l.driver);
    fact('Created', l.created + (l.age_days != null ? ' (' + l.age_days + 'd ago)' : ''));
    fact('Activity', l.activity_count + ' entr' + (l.activity_count === 1 ? 'y' : 'ies'));
    card.appendChild(facts);

    function block(title, text, open) {
      if (!text) return;
      var d = el('details', 'wa-lead__block'); if (open) d.open = true;
      d.appendChild(el('summary', null, title));
      d.appendChild(el('p', null, text));
      card.appendChild(d);
    }
    block('Notes', l.notes, false);
    block('AI summary', l.ai_summary, false);

    // Recent activity + add note
    var actD = el('details', 'wa-lead__block'); actD.open = true;
    actD.appendChild(el('summary', null, 'Recent activity'));
    // Not `wa-acts` — that is the message hover toolbar (opacity 0 until hover).
    var list = el('ul', 'wa-actlog');
    function actItem(a) {
      var li = el('li');
      li.appendChild(el('div', 'wa-actlog__meta', a.type + ' · ' + a.by + ' · ' + fmtDate(a.at, true)));
      li.appendChild(el('div', 'wa-actlog__body', a.body));
      return li;
    }
    (l.activities || []).forEach(function (a) { list.appendChild(actItem(a)); });
    if (!(l.activities || []).length) list.appendChild(el('li', 'wa-note', 'No activity yet.'));
    actD.appendChild(list);
    var note = el('div', 'wa-lead__note');
    var ni = el('input', 'wa-inp'); ni.placeholder = 'Add a note to the lead…'; ni.maxLength = 1000;
    var nb = el('button', 'wa-btn wa-btn--sm', 'Add'); nb.type = 'button';
    function addNote() {
      var body = ni.value.trim(); if (!body) return;
      nb.disabled = true; say('Saving…', true);
      postForm(l.urls.note, { body: body, activity_type: 'note' }).then(function (j) {
        nb.disabled = false;
        if (!j.success) { say(j.error || 'Could not add the note'); return; }
        ni.value = ''; say('Note added', true);
        var empty = list.querySelector('.wa-note'); if (empty) empty.remove();
        list.insertBefore(actItem({ type: j.activity.type_display, by: j.activity.created_by, at: Math.floor(Date.now() / 1000), body: j.activity.body }), list.firstChild);
      }).catch(function () { nb.disabled = false; say('Network error'); });
    }
    nb.addEventListener('click', addNote);
    ni.addEventListener('keydown', function (e) { if (e.key === 'Enter') { e.preventDefault(); addNote(); } });
    note.appendChild(ni); note.appendChild(nb);
    actD.appendChild(note);
    card.appendChild(actD);

    card.appendChild(msg);

    var foot = el('div', 'wa-lead__foot');
    var open = el('a', 'wa-btn wa-btn--sm', 'Open in CRM ↗'); open.href = l.url; open.target = '_blank'; open.rel = 'noopener';
    foot.appendChild(open);
    if (l.how === 'linked') {
      var ub = el('button', 'wa-btn wa-btn--ghost wa-btn--sm', 'Unlink chat'); ub.type = 'button';
      ub.addEventListener('click', function () { unlinkLead(l, ub); });
      foot.appendChild(ub);
    }
    card.appendChild(foot);
    return card;
  }

  // Driver lead: the documents on the driver's profile against the application
  // rule (a selfie plus two IDs). A chat photo is filed here from the viewer's
  // "Save to driver file".
  function docsBlock(l) {
    var d = l.docs;
    var box = el('details', 'wa-lead__block wa-docs'); box.open = true;
    var sum = el('summary', null, 'Required documents');
    sum.appendChild(el('span', 'wa-flag wa-flag--' + (d.complete ? 'ok' : 'warn'), d.complete ? 'Complete' : 'Incomplete'));
    box.appendChild(sum);
    var needs = [];
    if (!d.selfie_ok) needs.push('Selfie');
    if (d.ids_have < d.ids_need) needs.push((d.ids_need - d.ids_have) + ' more ID');
    box.appendChild(el('div', 'wa-note', 'Selfie ' + (d.selfie_ok ? '\u2713' : '\u2717') + ' · IDs ' +
      d.ids_have + ' of ' + d.ids_need + (needs.length ? ' — needs ' + needs.join(' + ') : '')));
    var grid = el('div', 'wa-docs__grid');
    d.items.forEach(function (it) {
      var tile = el('div', 'wa-docs__tile' + (it.front ? '' : ' wa-docs__tile--missing'));
      var thumbs = el('div', 'wa-docs__thumbs');
      [['front', it.front], ['back', it.back]].forEach(function (p) {
        if (!p[1]) return;
        var a = el('a', 'wa-docs__thumb'); a.href = p[1];
        a.dataset.lbUrl = p[1]; a.dataset.lbKind = 'photo';
        a.dataset.lbMeta = it.type + (p[0] === 'back' ? ' (back)' : '') + ' · driver profile';
        a.dataset.lbDoc = it.type;   // the viewer shows this document's number / expiry / check
        var im = el('img'); im.loading = 'lazy'; im.alt = it.type; im.src = p[1];
        a.appendChild(im); thumbs.appendChild(a);
      });
      if (!it.front) thumbs.appendChild(el('span', 'wa-docs__empty', 'Missing'));
      tile.appendChild(thumbs);
      tile.appendChild(el('div', 'wa-docs__name', it.type + (it.required ? ' *' : '')));
      var sub = [];
      if (it.number) sub.push(it.number);
      if (it.expiry) sub.push((it.expired ? 'Expired ' : 'Exp ') + it.expiry);
      if (sub.length) tile.appendChild(el('div', 'wa-docs__sub' + (it.expired ? ' wa-docs__sub--bad' : ''), sub.join(' · ')));
      if (it.url) { var o = el('a', 'wa-docs__open', 'Open ↗'); o.href = it.url; o.target = '_blank'; o.rel = 'noopener'; tile.appendChild(o); }
      if (panel.data && panel.data.can_save_docs) {
        var add = el('button', 'wa-btn wa-btn--sm wa-docs__add' + (it.front ? ' wa-btn--ghost' : ''),
                     it.front ? 'Replace from chat' : '+ Add from chat');
        add.type = 'button';
        add.addEventListener('click', function () { openPicker(l, it); });
        tile.appendChild(add);
      }
      grid.appendChild(tile);
    });
    box.appendChild(grid);
    box.appendChild(el('div', 'wa-note', '* required, plus any ' + d.ids_need + ' IDs. ' +
      (panel.data && panel.data.can_save_docs
        ? 'Use “Add from chat” on a tile, or open any photo and use “Save to driver file”.'
        : 'Your account cannot file photos onto driver documents.')));
    var pl = el('a', 'wa-btn wa-btn--sm', 'Driver profile ↗');
    pl.href = d.driver_url; pl.target = '_blank'; pl.rel = 'noopener';
    var f = el('div', 'wa-lead__foot');
    // Only when something is still owed (the server sends no reminder otherwise).
    if (l.reminder) {
      var rb = el('button', 'wa-btn wa-btn--sm', l.reminder.label.replace(/^Reminder/, 'Send reminder'));
      rb.type = 'button';
      rb.id = 'wa-docs-remind';
      rb.addEventListener('click', function () { openRemind(l); });
      f.appendChild(rb);
    }
    f.appendChild(pl); box.appendChild(f);
    return box;
  }

  var refreshTimer = null;
  function refreshPanelSoon() {
    clearTimeout(refreshTimer);
    refreshTimer = setTimeout(function () { panel.loadedFor = null; if (panel.open) loadPanel(); }, 1500);
  }

  // EzzyDelivery accounts: the user / business whose number this chat is, or
  // that a connected lead became (converted business, linked driver).
  function renderAccounts(d) {
    var box = $('wa-info-accounts');
    box.innerHTML = '';
    if (d.info.kind === 'group' || !d.leads_visible) { box.hidden = true; return; }
    box.hidden = false;
    var accts = d.accounts || [];
    // No heading: a user icon at the start of each row says "EzzyDelivery account".
    if (!accts.length) {
      var none = el('div', 'wa-acct__none');
      none.appendChild(userIcon());
      none.appendChild(el('span', 'wa-note', d.info.phone
        ? 'No user or business is registered on this number.'
        : 'The number behind this private id is not known yet, so only connected leads were checked.'));
      box.appendChild(none);
      return;
    }
    accts.forEach(function (a) { box.appendChild(accountCard(a)); });
  }

  var ACCT_ICONS = {
    user: '<path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/>',
    business: '<rect x="2" y="7" width="20" height="14" rx="2"/><path d="M16 21V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v16"/>',
    driver: '<rect x="1" y="3" width="15" height="13"/><path d="M16 8h4l3 3v5h-7V8z"/><circle cx="5.5" cy="18.5" r="2.5"/><circle cx="18.5" cy="18.5" r="2.5"/>',
  };
  // A driver row shows their vehicle: the Font Awesome Free (CC BY 4.0) glyphs the
  // CRM board chip and the roster plate use (workforce_tags.vehicle_icon), keyed
  // by DriverVehicle.vehicle_type. No vehicle on file keeps the generic truck.
  var VEHICLE_ICONS = {
    bike: 'M280 32c-13.3 0-24 10.7-24 24s10.7 24 24 24l57.7 0 16.4 30.3L256 192l-45.3-45.3c-12-12-28.3-18.7-45.3-18.7L64 128c-17.7 0-32 14.3-32 32l0 32 96 0c88.4 0 160 71.6 160 160c0 11-1.1 21.7-3.2 32l70.4 0c-2.1-10.3-3.2-21-3.2-32c0-52.2 25-98.6 63.7-127.8l15.4 28.6C402.4 276.3 384 312 384 352c0 70.7 57.3 128 128 128s128-57.3 128-128s-57.3-128-128-128c-13.5 0-26.5 2.1-38.7 6L418.2 128l61.8 0c17.7 0 32-14.3 32-32l0-32c0-17.7-14.3-32-32-32l-20.4 0c-7.5 0-14.7 2.6-20.5 7.4L391.7 78.9l-14-26c-7-12.9-20.5-21-35.2-21L280 32zM462.7 311.2l28.2 52.2c6.3 11.7 20.9 16 32.5 9.7s16-20.9 9.7-32.5l-28.2-52.2c2.3-.3 4.7-.4 7.1-.4c35.3 0 64 28.7 64 64s-28.7 64-64 64s-64-28.7-64-64c0-15.5 5.5-29.7 14.7-40.8zM187.3 376c-9.5 23.5-32.5 40-59.3 40c-35.3 0-64-28.7-64-64s28.7-64 64-64c26.9 0 49.9 16.5 59.3 40l66.4 0C242.5 268.8 190.5 224 128 224C57.3 224 0 281.3 0 352s57.3 128 128 128c62.5 0 114.5-44.8 125.8-104l-66.4 0zM128 384a32 32 0 1 0 0-64 32 32 0 1 0 0 64z',
    car: 'M171.3 96L224 96l0 96-112.7 0 30.4-75.9C146.5 104 158.2 96 171.3 96zM272 192l0-96 81.2 0c9.7 0 18.9 4.4 25 12l67.2 84L272 192zm256.2 1L428.2 68c-18.2-22.8-45.8-36-75-36L171.3 32c-39.3 0-74.6 23.9-89.1 60.3L40.6 196.4C16.8 205.8 0 228.9 0 256L0 368c0 17.7 14.3 32 32 32l33.3 0c7.6 45.4 47.1 80 94.7 80s87.1-34.6 94.7-80l130.7 0c7.6 45.4 47.1 80 94.7 80s87.1-34.6 94.7-80l33.3 0c17.7 0 32-14.3 32-32l0-48c0-65.2-48.8-119-111.8-127zM434.7 368a48 48 0 1 1 90.5 32 48 48 0 1 1 -90.5-32zM160 336a48 48 0 1 1 0 96 48 48 0 1 1 0-96z',
    van: 'M64 104l0 88 96 0 0-96L72 96c-4.4 0-8 3.6-8 8zm482 88L465.1 96 384 96l0 96 162 0zm-226 0l0-96-96 0 0 96 96 0zM592 384l-16 0c0 53-43 96-96 96s-96-43-96-96l-128 0c0 53-43 96-96 96s-96-43-96-96l-16 0c-26.5 0-48-21.5-48-48L0 104C0 64.2 32.2 32 72 32l120 0 160 0 113.1 0c18.9 0 36.8 8.3 49 22.8L625 186.5c9.7 11.5 15 26.1 15 41.2L640 336c0 26.5-21.5 48-48 48zm-64 0a48 48 0 1 0 -96 0 48 48 0 1 0 96 0zM160 432a48 48 0 1 0 0-96 48 48 0 1 0 0 96z',
    pickup: 'M368.6 96l76.8 96L288 192l0-96 80.6 0zM224 80l0 112L64 192c-17.7 0-32 14.3-32 32l0 64c-17.7 0-32 14.3-32 32s14.3 32 32 32l33.1 0c-.7 5.2-1.1 10.6-1.1 16c0 61.9 50.1 112 112 112s112-50.1 112-112c0-5.4-.4-10.8-1.1-16l66.3 0c-.7 5.2-1.1 10.6-1.1 16c0 61.9 50.1 112 112 112s112-50.1 112-112c0-5.4-.4-10.8-1.1-16l33.1 0c17.7 0 32-14.3 32-32s-14.3-32-32-32l0-64c0-17.7-14.3-32-32-32l-48.6 0L418.6 56c-12.1-15.2-30.5-24-50-24L272 32c-26.5 0-48 21.5-48 48zm0 288a48 48 0 1 1 -96 0 48 48 0 1 1 96 0zm288 0a48 48 0 1 1 -96 0 48 48 0 1 1 96 0z',
    pickup3ton: 'M48 0C21.5 0 0 21.5 0 48L0 368c0 26.5 21.5 48 48 48l16 0c0 53 43 96 96 96s96-43 96-96l128 0c0 53 43 96 96 96s96-43 96-96l32 0c17.7 0 32-14.3 32-32s-14.3-32-32-32l0-64 0-32 0-18.7c0-17-6.7-33.3-18.7-45.3L512 114.7c-12-12-28.3-18.7-45.3-18.7L416 96l0-48c0-26.5-21.5-48-48-48L48 0zM416 160l50.7 0L544 237.3l0 18.7-128 0 0-96zM112 416a48 48 0 1 1 96 0 48 48 0 1 1 -96 0zm368-48a48 48 0 1 1 0 96 48 48 0 1 1 0-96z',
    pickup_big: 'M64 32C28.7 32 0 60.7 0 96L0 304l0 80 0 16c0 44.2 35.8 80 80 80c26.2 0 49.4-12.6 64-32c14.6 19.4 37.8 32 64 32c44.2 0 80-35.8 80-80c0-5.5-.6-10.8-1.6-16L416 384l33.6 0c-1 5.2-1.6 10.5-1.6 16c0 44.2 35.8 80 80 80s80-35.8 80-80c0-5.5-.6-10.8-1.6-16l1.6 0c17.7 0 32-14.3 32-32l0-64 0-16 0-10.3c0-9.2-3.2-18.2-9-25.3l-58.8-71.8c-10.6-13-26.5-20.5-43.3-20.5L480 144l0-48c0-35.3-28.7-64-64-64L64 32zM585 256l-105 0 0-64 48.8 0c2.4 0 4.7 1.1 6.2 2.9L585 256zM528 368a32 32 0 1 1 0 64 32 32 0 1 1 0-64zM176 400a32 32 0 1 1 64 0 32 32 0 1 1 -64 0zM80 368a32 32 0 1 1 0 64 32 32 0 1 1 0-64z',
  };
  function acctIcon(kind, label) {
    var i = el('span', 'wa-acct__icon');
    i.title = label;
    i.setAttribute('role', 'img');
    i.setAttribute('aria-label', label);
    i.innerHTML = VEHICLE_ICONS[kind]
      ? '<svg viewBox="0 0 640 512" fill="currentColor" aria-hidden="true"><path d="' + VEHICLE_ICONS[kind] + '"/></svg>'
      : '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' + ACCT_ICONS[kind] + '</svg>';
    return i;
  }
  function userIcon() { return acctIcon('user', 'EzzyDelivery account'); }

  var ACCT_OK = { active: 1, approved: 1 };
  var ACCT_WARN = { inactive: 1, suspended: 1, rejected: 1, blocked: 1 };
  function statusFlag(text, key) {
    return el('span', 'wa-flag' + (ACCT_OK[key] ? ' wa-flag--ok' : ACCT_WARN[key] ? ' wa-flag--warn' : ''), text);
  }
  function openLink(url, text) {
    var f = el('div', 'wa-lead__foot');
    var a = el('a', 'wa-btn wa-btn--sm', text + ' ↗'); a.href = url; a.target = '_blank'; a.rel = 'noopener';
    f.appendChild(a);
    return f;
  }
  function accountSub(title, flags, meta, url, linkText) {
    var sub = el('div', 'wa-acct__sub');
    var top = el('div', 'wa-acct__subtop');
    top.appendChild(el('span', 'wa-acct__subname', title));
    flags.forEach(function (f) { if (f) top.appendChild(f); });
    sub.appendChild(top);
    meta = meta.filter(Boolean);
    if (meta.length) sub.appendChild(el('div', 'wa-lead__meta', meta.join(' · ')));
    if (url) sub.appendChild(openLink(url, linkText));
    return sub;
  }

  function acctBtn(url, text) {
    var b = el('a', 'wa-btn wa-btn--sm wa-btn--ghost wa-acct__end', text + ' ↗');
    b.href = url; b.target = '_blank'; b.rel = 'noopener';
    return b;
  }
  // A business / team / driver record under the person: icon, name, flags, Open.
  function recordRow(kind, label, title, flags, url, linkText) {
    var row = el('div', 'wa-acct__row');
    row.appendChild(acctIcon(kind, label));
    row.appendChild(el('span', 'wa-acct__rowname', title));
    flags.forEach(function (f) { if (f) row.appendChild(f); });
    if (url) row.appendChild(acctBtn(url, linkText));
    return row;
  }

  // Line 1 is the person: name, roles, then "Verified" or the Verification
  // button. One line under it per business / team / driver record, each with
  // its Open button. The caret opens the rest (facts, order counts) below.
  function accountCard(a) {
    var card = el('div', 'wa-acct');
    var line = el('div', 'wa-acct__line');
    var tog = el('button', 'wa-acct__toggle');
    tog.type = 'button';
    tog.setAttribute('aria-expanded', 'false');
    tog.appendChild(userIcon());
    tog.appendChild(el('span', 'wa-acct__name', a.name));
    line.appendChild(tog);
    (a.roles || []).forEach(function (r) { line.appendChild(el('span', 'wa-flag', r)); });
    if (a.active === false) line.appendChild(el('span', 'wa-flag wa-flag--warn', 'Login disabled'));
    if (a.verification_key === 'verified') line.appendChild(el('span', 'wa-flag wa-flag--ok wa-acct__end', 'Verified'));
    else if (a.verify_url) {
      var vb = acctBtn(a.verify_url, 'Verify');
      vb.title = 'Open the verification page for this person';
      line.appendChild(vb);
    }
    card.appendChild(line);

    (a.businesses || []).forEach(function (b) {
      card.appendChild(recordRow('business', 'Business #' + b.id, b.name,
        [statusFlag(b.status, b.status_key)], b.url, 'Open business'));
    });
    (a.teams || []).forEach(function (t) {
      card.appendChild(recordRow('business', 'Team member', t.business,
        [el('span', 'wa-flag', t.role), statusFlag(t.status, (t.status || '').toLowerCase())], t.url, 'Open business'));
    });
    var dr = a.driver;
    if (dr) {
      card.appendChild(recordRow(VEHICLE_ICONS[dr.vehicle_type] ? dr.vehicle_type : 'driver',
        (dr.vehicle ? dr.vehicle + ' · ' : '') + 'Driver #' + dr.id, dr.code || 'Driver #' + dr.id,
        [statusFlag(dr.status, dr.status_key)], dr.url, 'Open driver'));
    }

    var body = el('div', 'wa-acct__body');
    body.hidden = true;
    if (a.username) body.appendChild(el('div', 'wa-acct__user', '@' + a.username));
    if ((a.match || []).length) body.appendChild(el('div', 'wa-lead__meta', 'Matched by: ' + a.match.join(' · ')));

    if (a.username) {
      var facts = el('dl', 'wa-lead__facts');
      var fact = function (k, v) { if (!v && v !== 0) return; facts.appendChild(el('dt', null, k)); facts.appendChild(el('dd', null, String(v))); };
      fact('User no.', a.user_number);
      fact('Email', a.email);
      fact('Phone', a.phone);
      fact('WhatsApp', a.whatsapp);
      fact('Verification', a.verification);
      fact('Joined', a.joined ? fmtDate(a.joined, false) : '');
      fact('Last login', a.last_login ? fmtDate(a.last_login, true) : 'Never');
      if (a.p2p_orders) fact('P2P bookings', a.p2p_orders);
      body.appendChild(facts);
    }

    // Status and the Open buttons already sit on the record lines above.
    (a.businesses || []).forEach(function (b) {
      body.appendChild(accountSub(b.name + ' #' + b.id, [], [
        b.code,
        b.orders ? b.orders + ' order' + (b.orders === 1 ? '' : 's') + (b.last_order ? ', last ' + fmtDate(b.last_order, false) : '') : 'No orders yet',
        b.phone ? 'Business no. ' + b.phone : '',
        b.whatsapp && b.whatsapp !== b.phone ? 'WhatsApp ' + b.whatsapp : '',
        (b.match || []).length ? 'Matched by: ' + b.match.join(', ') : '',
      ]));
    });
    if (dr) body.appendChild(accountSub('Driver #' + dr.id, [el('span', 'wa-flag', dr.availability)], [dr.code]));
    card.appendChild(body);

    tog.addEventListener('click', function () {
      var open = body.hidden;
      body.hidden = !open;
      tog.setAttribute('aria-expanded', open ? 'true' : 'false');
      card.classList.toggle('wa-acct--open', open);
    });
    return card;
  }

  function renderLeads(d) {
    var box = $('wa-info-leads');
    box.innerHTML = '';
    if (d.info.kind === 'group') { box.hidden = true; return; }
    box.hidden = false;
    box.appendChild(el('div', 'wa-info__sec-title', 'CRM leads' + (d.leads && d.leads.length ? ' (' + d.leads.length + ')' : '')));
    if (!d.leads_visible) {
      var n = el('div', 'wa-note');
      n.appendChild(document.createTextNode('Sign in to the '));
      var a = el('a', null, 'staff portal'); a.href = '/accounts/login/?next=/waha/wa-chats/'; a.target = '_blank';
      n.appendChild(a);
      n.appendChild(document.createTextNode(' with CRM access to see this chat’s leads.'));
      box.appendChild(n);
      return;
    }
    if (d.leads.length) {
      d.leads.forEach(function (l) { box.appendChild(l.urls ? workCard(l, d.staff) : leadCard(l)); });
      if (!d.can_link) box.appendChild(el('div', 'wa-note', 'Read-only: your account cannot edit leads here.'));
      return;
    }
    box.appendChild(el('div', 'wa-note', 'No lead is connected to this chat.'));
    if (d.suggested && d.suggested.length) {
      box.appendChild(el('div', 'wa-info__sec-title', 'Possible matches'));
      d.suggested.forEach(function (l) { box.appendChild(leadCard(l, { link: d.can_link })); });
    }
    if (!d.can_link) {
      box.appendChild(el('div', 'wa-note', 'Your account cannot link leads.'));
      return;
    }
    var wrap = el('div', 'wa-lead-search');
    var input = el('input', 'wa-search');
    input.placeholder = 'Find a lead by name, company, phone or #id…';
    input.autocomplete = 'off';
    var results = el('div');
    wrap.appendChild(input);
    wrap.appendChild(results);
    box.appendChild(wrap);
    var timer = null;
    input.addEventListener('input', function () {
      clearTimeout(timer);
      var q = input.value.trim();
      if (q.length < 2) { results.innerHTML = ''; return; }
      timer = setTimeout(function () {
        fetch('/waha/wa-chats/?lead_search=1&q=' + encodeURIComponent(q), { credentials: 'same-origin' })
          .then(function (r) { return r.json(); })
          .then(function (j) {
            if (input.value.trim() !== q) return;
            results.innerHTML = '';
            if (!j.ok || !j.leads.length) { results.appendChild(el('div', 'wa-note', j.error || 'No leads found.')); return; }
            j.leads.forEach(function (l) { results.appendChild(leadCard(l, { link: true })); });
          });
      }, 250);
    });
    box.appendChild(el('div', 'wa-note', 'New leads come only from the driver or pricing form — link an existing one here.'));
  }

  function postLink(payload) {
    return fetch('/waha/wa-chats/link-lead/', {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': CSRF },
      body: JSON.stringify(payload),
    }).then(function (r) { return r.json().catch(function () { return { ok: false, error: 'HTTP ' + r.status }; }); });
  }

  function linkLead(l, btn, label) {
    var n = (l.links || []).length;
    var msg = 'Link this chat to lead #' + l.id + ' (' + l.name + ')' + (label ? ' as "' + label + '"' : '') + '?';
    if (n) msg += '\n\nIt is added alongside the ' + n + ' number' + (n > 1 ? 's' : '') + ' already linked — nothing is replaced.';
    if (!confirm(msg)) return;
    btn.disabled = true; btn.textContent = 'Linking…';
    postLink({ lead_id: l.id, chatId: state.activeChatId, session: SESSION, label: label || '' })
      .then(function (j) {
        if (!j.ok) { btn.disabled = false; btn.textContent = 'Link this chat'; alert(j.error || 'Could not link'); return; }
        loadPanel();
      })
      .catch(function () { btn.disabled = false; btn.textContent = 'Link this chat'; alert('Network error'); });
  }

  function unlinkLead(l, btn) {
    if (!confirm('Unlink this chat from lead #' + l.id + ' (' + l.name + ')?')) return;
    btn.disabled = true;
    postLink({ action: 'unlink', lead_id: l.id, chatId: state.activeChatId, session: SESSION })
      .then(function (j) {
        if (!j.ok) { btn.disabled = false; alert(j.error || 'Could not unlink'); return; }
        loadPanel();
      })
      .catch(function () { btn.disabled = false; alert('Network error'); });
  }

  function renderMediaTabs() {
    var tabs = $('wa-media-tabs');
    tabs.innerHTML = '';
    MEDIA_TABS.forEach(function (t) {
      var b = el('button', 'wa-tab' + (t[0] === panel.kind ? ' wa-tab--on' : ''), t[1]);
      b.type = 'button';
      b.setAttribute('role', 'tab');
      b.setAttribute('aria-selected', t[0] === panel.kind ? 'true' : 'false');
      b.appendChild(el('span', 'wa-tab__n', String(panel.counts[t[0]] || 0)));
      b.addEventListener('click', function () {
        if (panel.kind === t[0]) return;
        panel.kind = t[0];
        renderMediaTabs();
        loadMedia(false);
      });
      tabs.appendChild(b);
    });
  }

  function loadMedia(append) {
    var chatId = state.activeChatId, kind = panel.kind;
    var body = $('wa-media-body');
    if (!append) { panel.offset = 0; body.innerHTML = '<div class="wa-empty">Loading…</div>'; }
    var url = wq('/waha/wa-chats/?media=1&chatId=' + encodeURIComponent(chatId) + '&kind=' + kind + '&offset=' + panel.offset);
    fetch(url, { credentials: 'same-origin' })
      .then(function (r) { return r.json(); })
      .then(function (j) {
        if (state.activeChatId !== chatId || panel.kind !== kind) return;
        if (!append) body.innerHTML = '';
        var old = body.querySelector('.wa-more');
        if (old) old.remove();
        if (!j.ok) { body.appendChild(el('div', 'wa-empty', 'Could not load.')); return; }
        if (!append && !j.items.length) {
          body.appendChild(el('div', 'wa-empty', 'Nothing here yet.'));
          return;
        }
        var grid = kind === 'photos' || kind === 'videos';
        var holder = body.querySelector(grid ? '.wa-grid' : '.wa-mlist');
        if (!holder) { holder = el('div', grid ? 'wa-grid' : 'wa-mlist'); body.appendChild(holder); }
        j.items.forEach(function (it) { holder.appendChild(mediaItem(kind, it)); });
        panel.offset += j.items.length;
        if (j.has_more) {
          var more = el('button', 'wa-btn wa-btn--ghost wa-more', 'Load more');
          more.type = 'button';
          more.addEventListener('click', function () { more.disabled = true; loadMedia(true); });
          body.appendChild(more);
        }
      })
      .catch(function () {
        if (!append) body.innerHTML = '<div class="wa-empty">Could not load.</div>';
      });
  }

  function mediaItem(kind, it) {
    var when = fmtDate(it.ts, true) + ' · ' + (it.direction === 'outbound' ? 'Sent' : 'Received');
    // A group file nobody has downloaded yet: a download tile, fetched on tap.
    var gated = state.activeIsGroup && it.stored === false;
    var url = gated ? withFetch(it.url) : it.url;
    if (kind === 'photos' || kind === 'videos') {
      var cell = el('a', 'wa-grid__cell');
      cell.href = url; cell.title = when;
      cell.dataset.lbUrl = url;
      cell.dataset.lbKind = kind === 'videos' ? 'video' : 'photo';
      cell.dataset.lbMeta = when;
      cell.dataset.lbCaption = it.caption || '';
      if (gated) {
        cell.title = when + ' · tap to download';
        cell.appendChild(el('span', 'wa-grid__play', '\u2B07'));
        return cell;
      }
      var m;
      if (kind === 'photos') {
        m = el('img'); m.loading = 'lazy'; m.alt = it.caption || 'Photo'; m.src = it.url;
      } else {
        m = el('video'); m.preload = 'metadata'; m.muted = true; m.src = it.url + '#t=0.1';
        cell.appendChild(m);
        cell.appendChild(el('span', 'wa-grid__play', '▶'));
      }
      m.addEventListener('error', function () { m.remove(); cell.classList.add('wa-grid__cell--broken'); });
      if (kind === 'photos') cell.appendChild(m);
      return cell;
    }
    var item = el('div', 'wa-mitem');
    item.appendChild(el('div', 'wa-mitem__meta', when));
    if (kind === 'links') {
      (it.urls || []).forEach(function (u) {
        var a = el('a', null, u); a.href = u; a.target = '_blank'; a.rel = 'noopener noreferrer';
        item.appendChild(a); item.appendChild(el('br'));
      });
      if (it.text) item.appendChild(el('div', 'wa-mitem__text', it.text));
    } else if (kind === 'files') {
      var f = el('a', null, '📄 ' + (it.filename || it.caption || 'Document'));
      f.href = url; f.target = '_blank'; f.rel = 'noopener';
      item.appendChild(f);
      if (it.mime) item.appendChild(el('div', 'wa-mitem__text', it.mime));
    } else {
      var au = el('audio'); au.controls = true; au.preload = 'none'; au.src = url;
      item.appendChild(au);
    }
    return item;
  }


  // ---------- Media viewer ----------
  // Anything carrying data-lb-url opens here; prev/next walks the other
  // data-lb-url items in the same container (a panel grid or the chat).
  var lb = { items: [], i: 0 };
  function openViewer(target) {
    var scope = target.closest('.wa-grid, .wa-docs__grid, #wa-msgs') || document;
    var nodes = Array.prototype.slice.call(scope.querySelectorAll('[data-lb-url]'));
    lb.items = nodes.map(function (n) {
      return { url: n.dataset.lbUrl, kind: n.dataset.lbKind || 'photo', meta: n.dataset.lbMeta || '',
               caption: n.dataset.lbCaption || '', doc: n.dataset.lbDoc || '' };
    });
    lb.i = Math.max(0, nodes.indexOf(target));
    showViewer();
    var dlg = $('wa-lb');
    if (!dlg.open) dlg.showModal();
  }
  function showViewer() {
    var it = lb.items[lb.i];
    if (!it) return;
    var stage = $('wa-lb-stage');
    Array.prototype.forEach.call(stage.querySelectorAll('img, video, .wa-lb__missing'), function (n) { n.remove(); });
    var m;
    if (it.kind === 'video') {
      m = document.createElement('video'); m.controls = true; m.autoplay = true; m.src = it.url;
    } else {
      m = document.createElement('img'); m.alt = it.caption || 'Photo'; m.src = it.url;
    }
    // A video "error" is often a format this browser can't play, not a missing file.
    m.addEventListener('error', function () {
      m.replaceWith(el('div', 'wa-lb__missing', it.kind === 'video'
        ? 'This video can\u2019t play here — use Download to open it.'
        : 'This file is no longer available.'));
    });
    stage.insertBefore(m, $('wa-lb-next'));
    $('wa-lb-meta').textContent = it.meta;
    $('wa-lb-caption').textContent = it.caption;
    $('wa-lb-count').textContent = lb.items.length > 1 ? (lb.i + 1) + ' / ' + lb.items.length : '';
    $('wa-lb-dl').href = it.url;
    updateSaveControl(it);
    updateDocPanel(it);
    $('wa-lb-prev').hidden = lb.i <= 0;
    $('wa-lb-next').hidden = lb.i >= lb.items.length - 1;
  }
  function saveDoc(l, msgId, docType, side) {
    return fetch('/waha/wa-chats/save-doc/', {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': CSRF },
      body: JSON.stringify({ session: SESSION, chatId: state.activeChatId, lead_id: l.id,
                             msg_id: msgId, doc_type: docType, side: side }),
    }).then(function (r) { return r.json().catch(function () { return { ok: false, error: 'HTTP ' + r.status }; }); });
  }

  // "Add from chat" on a document tile: pick one of this chat's photos for it.
  var pick = { lead: null, item: null, offset: 0, chat: null };
  function openPicker(l, it) {
    pick.lead = l; pick.item = it; pick.offset = 0; pick.chat = state.activeChatId;
    $('wa-pick-title').textContent = (it.front ? 'Replace ' : 'Add ') + it.type + ' — choose a photo';
    var single = it.type === 'Selfie';
    $('wa-pick-side-wrap').hidden = single;
    $('wa-pick-side').value = (!single && it.front && !it.back) ? 'back' : 'front';
    $('wa-pick-grid').innerHTML = '';
    $('wa-pick-msg').textContent = 'Loading photos…';
    $('wa-pick-more').hidden = true;
    $('wa-pick').showModal();
    loadPickPhotos();
  }
  function loadPickPhotos() {
    var chat = pick.chat;
    fetch(wq('/waha/wa-chats/?media=1&kind=photos&chatId=' + encodeURIComponent(chat) + '&offset=' + pick.offset),
          { credentials: 'same-origin' })
      .then(function (r) { return r.json(); })
      .then(function (j) {
        if (pick.chat !== chat) return;
        if (!j.ok) throw new Error(j.error || 'failed');
        (j.items || []).forEach(function (p) {
          var b = el('button', 'wa-grid__cell'); b.type = 'button';
          b.title = fmtDate(p.ts, true) + ' · ' + (p.direction === 'outbound' ? 'Sent' : 'Received');
          var im = el('img'); im.loading = 'lazy'; im.alt = 'Photo'; im.src = p.url;
          im.addEventListener('error', function () { b.classList.add('wa-grid__cell--broken'); im.remove(); });
          b.appendChild(im);
          b.addEventListener('click', function () { pickPhoto(p, b); });
          $('wa-pick-grid').appendChild(b);
        });
        pick.offset += (j.items || []).length;
        $('wa-pick-more').hidden = !j.has_more;
        $('wa-pick-msg').textContent = pick.offset ? 'Tap the photo to save.' : 'No photos in this chat yet — ask the driver to send one.';
      })
      .catch(function () { if (pick.chat === chat) $('wa-pick-msg').textContent = 'Could not load photos.'; });
  }
  function pickPhoto(p, b) {
    var it = pick.item, side = it.type === 'Selfie' ? 'front' : $('wa-pick-side').value;
    var has = side === 'front' ? it.front : it.back;
    var name = it.type + (it.type === 'Selfie' ? '' : ' (' + side + ')');
    if (!confirm(has ? 'Replace the driver’s ' + name + ' with this photo?' : 'Save this photo as the driver’s ' + name + '?')) return;
    b.disabled = true; $('wa-pick-msg').textContent = 'Saving…';
    saveDoc(pick.lead, p.id, it.type, side).then(function (j) {
      b.disabled = false;
      if (!j.ok) { $('wa-pick-msg').textContent = j.error || 'Could not save.'; return; }
      pick.lead.docs = j.docs;
      $('wa-pick').close();
      panel.loadedFor = null; loadPanel();
    }).catch(function () { b.disabled = false; $('wa-pick-msg').textContent = 'Network error'; });
  }
  $('wa-pick-more').addEventListener('click', function () { $('wa-pick-more').hidden = true; loadPickPhotos(); });
  $('wa-pick-close').addEventListener('click', function () { $('wa-pick').close(); });
  $('wa-pick').addEventListener('click', function (e) { if (e.target === $('wa-pick')) $('wa-pick').close(); });

  // "Save to driver file": only for a photo from this chat, while the chat has a
  // connected driver lead and the account may edit driver documents.
  function docLead() {
    var d = panel.data;
    if (!d || !d.can_save_docs || !d.leads || panel.loadedFor !== state.activeChatId) return null;
    return d.leads.filter(function (l) { return l.docs; })[0] || null;
  }
  function msgIdOf(url) {
    var m = /\/waha\/wa-chats\/media\/(\d+)\//.exec(url || '');
    return m ? m[1] : '';
  }
  function updateSaveControl(it) {
    var box = $('wa-lb-save'), l = docLead();
    box.hidden = !(l && it.kind === 'photo' && msgIdOf(it.url));
    if (box.hidden) return;
    var sel = $('wa-lb-save-type');
    sel.innerHTML = '';
    var ph = el('option', null, 'Save as…'); ph.value = ''; sel.appendChild(ph);
    l.docs.items.forEach(function (d) {
      (d.type === 'Selfie' ? ['front'] : ['front', 'back']).forEach(function (side) {
        var has = side === 'front' ? d.front : d.back;
        var o = el('option', null, d.type + (d.type === 'Selfie' ? '' : side === 'front' ? ' — front' : ' — back') + (has ? ' (replace)' : ''));
        o.value = d.type + '|' + side;
        sel.appendChild(o);
      });
    });
    var btn = $('wa-lb-save-btn');
    btn.disabled = false; btn.textContent = 'Save to driver file';
  }
  $('wa-lb-save-btn').addEventListener('click', function () {
    var it = lb.items[lb.i], l = docLead(), sel = $('wa-lb-save-type'), btn = this;
    if (!it || !l) return;
    if (!sel.value) { sel.focus(); return; }
    var parts = sel.value.split('|'), label = sel.options[sel.selectedIndex].text;
    var ask = /\(replace\)$/.test(label)
      ? 'Replace the ' + label.replace(' (replace)', '') + ' photo on the driver’s profile with this one?'
      : 'Save this photo as the driver’s ' + label + '?';
    if (!confirm(ask)) return;
    btn.disabled = true; btn.textContent = 'Saving…';
    saveDoc(l, msgIdOf(it.url), parts[0], parts[1])
      .then(function (j) {
        if (!j.ok) { btn.disabled = false; btn.textContent = 'Save to driver file'; alert(j.error || 'Could not save'); return; }
        l.docs = j.docs;
        updateSaveControl(it);
        btn.textContent = 'Saved \u2713';
        refreshPanelSoon();
      })
      .catch(function () { btn.disabled = false; btn.textContent = 'Save to driver file'; alert('Network error'); });
  });

  // ---------- Document panel in the viewer ----------
  // A driver-profile document photo shows the same number / expiry / image-check
  // panel as the CRM popup (workforce/js/doc_viewer.js) and posts to the same
  // workforce endpoints — no second write path. Nothing is saved until Submit.
  var lbDoc = null;   // { base, item } for the document on show, else null
  function docForItem(it) {
    var d = panel.data;
    if (!it || !it.doc || !d || !d.leads || panel.loadedFor !== state.activeChatId) return null;
    var l = d.leads.filter(function (x) { return x.docs; })[0];
    if (!l) return null;
    var item = l.docs.items.filter(function (x) { return x.type === it.doc; })[0];
    return item && item.id ? { base: l.docs.doc_edit_base + item.id, item: item } : null;
  }
  function docFact(dl, label, value) {
    if (!value) return;
    dl.appendChild(el('dt', null, label));
    dl.appendChild(el('dd', null, value));
  }
  function updateDocPanel(it) {
    lbDoc = docForItem(it);
    $('wa-lb-doc').hidden = !lbDoc;
    if (!lbDoc) return;
    var item = lbDoc.item, canEdit = !!panel.data.can_save_docs;
    $('wa-lb-doc-title').textContent = item.type;
    $('wa-lb-doc-fields').hidden = item.type === 'Selfie';
    $('wa-lb-doc-no').value = item.number || '';
    $('wa-lb-doc-exp').value = item.expiry || '';
    $('wa-lb-doc-no').readOnly = $('wa-lb-doc-exp').readOnly = !canEdit;
    var facts = $('wa-lb-doc-facts');
    facts.innerHTML = '';
    docFact(facts, 'Issued from', item.issued);
    docFact(facts, 'Image check', item.check);
    docFact(facts, 'Why', item.check_note);
    docFact(facts, 'Number on image', item.ai_no);
    docFact(facts, 'Expiry on image', item.ai_expiry);
    $('wa-lb-doc-ro').hidden = canEdit || !!panel.data.can_verify_docs;
    docShowErr('');
    docBusy(false);
    docRefresh();
  }
  function docDirty() {
    if (!lbDoc || lbDoc.item.type === 'Selfie' || !panel.data.can_save_docs) return false;
    return $('wa-lb-doc-no').value.trim() !== (lbDoc.item.number || '')
      || $('wa-lb-doc-exp').value !== (lbDoc.item.expiry || '');
  }
  // Submit / Submit & verify only once a field really differs; while it does,
  // Submit & verify stands in for Mark verified, which would verify the old values.
  function docRefresh() {
    if (!lbDoc) return;
    var item = lbDoc.item, dirty = docDirty(), canVerify = !!panel.data.can_verify_docs;
    var no = $('wa-lb-doc-no').value.trim(), exp = $('wa-lb-doc-exp').value;
    $('wa-lb-doc-submit').hidden = !dirty;
    $('wa-lb-doc-submitverify').hidden = !dirty || !canVerify;
    $('wa-lb-doc-verify').hidden = !canVerify || item.verified || dirty;
    $('wa-lb-doc-unverify').hidden = !canVerify || !item.verified;
    $('wa-lb-doc-useai').hidden = !(panel.data.can_save_docs && item.type !== 'Selfie' &&
      ((item.ai_no && no !== item.ai_no) || (item.ai_expiry_iso && exp !== item.ai_expiry_iso)));
  }
  function docShowErr(msg) {
    var e = $('wa-lb-doc-err');
    e.textContent = msg || '';
    e.hidden = !msg;
  }
  function docBusy(busy) {
    ['wa-lb-doc-submit', 'wa-lb-doc-submitverify', 'wa-lb-doc-verify', 'wa-lb-doc-unverify']
      .forEach(function (id) { $(id).disabled = busy; });
  }
  // X-Requested-With: a department refusal then comes back as JSON with its reason,
  // not a redirect to dashboard HTML.
  function docPost(url, fields) {
    var fd = new FormData();
    Object.keys(fields).forEach(function (k) { fd.append(k, fields[k]); });
    return fetch(url, { method: 'POST', credentials: 'same-origin', body: fd,
                        headers: { 'X-CSRFToken': CSRF, 'X-Requested-With': 'XMLHttpRequest' } })
      .then(function (r) {
        return r.json().catch(function () {
          throw new Error('The server did not answer properly (HTTP ' + r.status + '). Try again.');
        });
      })
      .then(function (j) {
        if (!j.success) throw new Error(j.error || 'Could not save this document.');
        return j;
      });
  }
  // Save the fields and/or (un)verify, then reload the panel so the tile and this
  // viewer both show what the server now holds — including the re-run image match.
  function docRun(save, action) {
    if (!lbDoc) return;
    if (action === 'verify' && !confirm('Confirm you checked the number and expiry against the image?')) return;
    var doc = lbDoc, chat = state.activeChatId, shown = lb.items[lb.i] && lb.items[lb.i].url;
    docShowErr('');
    docBusy(true);
    var chain = Promise.resolve();
    if (save) {
      chain = chain.then(function () {
        return docPost(doc.base + '/edit/', {
          document_type: doc.item.type,   // the endpoint rewrites every field it is sent
          document_no: $('wa-lb-doc-no').value.trim(),
          document_issued_from: doc.item.issued || '',
          document_expiry_date: $('wa-lb-doc-exp').value,
        });
      });
    }
    if (action) chain = chain.then(function () { return docPost(doc.base + '/verify/', { action: action }); });
    chain
      .then(function () {
        if (state.activeChatId !== chat) return;
        panel.loadedFor = null;
        return loadPanel();
      })
      .then(function () {
        var it = lb.items[lb.i];
        if ($('wa-lb').open && it && it.url === shown) updateDocPanel(it);
      })
      .catch(function (err) {
        docBusy(false);
        docShowErr(err && err.name !== 'TypeError' && err.message ? err.message : 'Could not reach the server. Try again.');
      });
  }
  $('wa-lb-doc-no').addEventListener('input', docRefresh);
  $('wa-lb-doc-exp').addEventListener('input', docRefresh);
  $('wa-lb-doc-exp').addEventListener('change', docRefresh);
  $('wa-lb-doc-useai').addEventListener('click', function () {
    if (!lbDoc) return;
    if (lbDoc.item.ai_no) $('wa-lb-doc-no').value = lbDoc.item.ai_no;
    if (lbDoc.item.ai_expiry_iso) $('wa-lb-doc-exp').value = lbDoc.item.ai_expiry_iso;
    docRefresh();
  });
  $('wa-lb-doc-submit').addEventListener('click', function () { docRun(true, ''); });
  $('wa-lb-doc-submitverify').addEventListener('click', function () { docRun(true, 'verify'); });
  $('wa-lb-doc-verify').addEventListener('click', function () { docRun(false, 'verify'); });
  $('wa-lb-doc-unverify').addEventListener('click', function () { docRun(false, 'unverify'); });

  function stepViewer(d) {
    var n = lb.i + d;
    if (n < 0 || n >= lb.items.length) return;
    lb.i = n;
    showViewer();
  }
  function closeViewer() {
    var v = $('wa-lb-stage').querySelector('video');
    if (v) v.pause();
    $('wa-lb').close();
  }
  $('wa-lb-prev').addEventListener('click', function () { stepViewer(-1); });
  $('wa-lb-next').addEventListener('click', function () { stepViewer(1); });
  $('wa-lb-close').addEventListener('click', closeViewer);
  $('wa-lb').addEventListener('close', function () {
    Array.prototype.forEach.call($('wa-lb-stage').querySelectorAll('img, video, .wa-lb__missing'), function (n) { n.remove(); });
  });
  $('wa-lb').addEventListener('click', function (e) {
    if (e.target === $('wa-lb') || e.target === $('wa-lb-stage')) closeViewer();
  });
  $('wa-lb').addEventListener('keydown', function (e) {
    // Arrows inside a field (document number / expiry, "Save as…") move the caret, not the photo.
    if (e.target.closest && e.target.closest('input, select, textarea')) return;
    if (e.key === 'ArrowLeft') { e.preventDefault(); stepViewer(-1); }
    else if (e.key === 'ArrowRight') { e.preventDefault(); stepViewer(1); }
  });
  // One delegated handler covers the chat and the panel, including items added later.
  document.addEventListener('click', function (e) {
    var t = e.target.closest && e.target.closest('[data-lb-url]');
    if (!t || t.closest('#wa-lb')) return;
    e.preventDefault();
    openViewer(t);
  });

  // ---------- Wire up ----------
  // Back on the tab with a chat open: whatever arrived meanwhile is now seen.
  document.addEventListener('visibilitychange', function () {
    if (document.visibilityState !== 'visible' || !state.activeChatId) return;
    var c = state.chats.filter(function (x) { return x.id === state.activeChatId; })[0];
    if (c && c.unread) markChatRead(state.activeChatId, true);
  });

  // A filter can shrink the list below the fold — then no scroll ever fires.
  function refilter() { renderList(); fillChatList(); }
  function findContacts() {
    var q = ($('wa-search').value || '').trim();
    clearTimeout(finder.timer);
    if (q === finder.q) return;
    finder.timer = setTimeout(function () {
      fetch(wq('/waha/wa-chats/?find=1&q=' + encodeURIComponent(q)), { credentials: 'same-origin' })
        .then(function (r) { return r.ok ? r.json() : null; })
        .then(function (data) {
          if (q !== ($('wa-search').value || '').trim()) return;   // typed on since
          finder.q = q;
          finder.hits = (data && Array.isArray(data.hits)) ? data.hits : [];
          finder.messages = (data && Array.isArray(data.messages)) ? data.messages : [];
          renderList();
        })
        .catch(function () { /* the loaded-chats match still shows */ });
    }, 250);
  }
  $('wa-search').addEventListener('input', function () { refilter(); findContacts(); });
  $('wa-type-filter').addEventListener('change', refilter);
  $('wa-label-filter').addEventListener('change', function () { syncQuickLabels(); refilter(); });
  document.querySelectorAll('.wa-qlabel').forEach(function (b) {
    b.addEventListener('click', function () {
      var sel = $('wa-label-filter');
      var id = b.dataset.labelId || '';
      sel.value = sel.value === id ? '' : id;  // second click clears
      syncQuickLabels();
      refilter();
    });
  });
  $('wa-resync').addEventListener('click', resyncActive);
  $('wa-comp-send').addEventListener('click', sendMessage);
  $('wa-info-toggle').addEventListener('click', function () { setPanelOpen(!panel.open || $('wa-info').hidden); });
  $('wa-info-close').addEventListener('click', function () { setPanelOpen(false); });

  // Scrolling only fires while the list overflows; if a page added nothing new
  // (duplicates, filtered out, hidden noise) keep fetching until it does.
  function fillChatList() {
    var listEl = $('wa-list');
    if (!listEl || state.chatsLoading || state.chatsExhausted) return;
    if (listEl.scrollTop + listEl.clientHeight >= listEl.scrollHeight - 200) loadChats(true);
  }

  // Infinite scroll on the chat list: bottom → next page of chats.
  (function wireInfiniteScroll() {
    var listEl = $('wa-list');
    if (!listEl) return;
    var ticking = false;
    listEl.addEventListener('scroll', function () {
      if (ticking) return;
      ticking = true;
      requestAnimationFrame(function () {
        ticking = false;
        fillChatList();
      });
    });
  })();

  // Scroll-up on the messages pane: top → previous page of messages.
  (function wireMessagesScroll() {
    var msgsEl = $('wa-msgs');
    if (!msgsEl) return;
    var ticking = false;
    msgsEl.addEventListener('scroll', function () {
      if (ticking) return;
      ticking = true;
      requestAnimationFrame(function () {
        ticking = false;
        if (state.msgsLoading || !state.msgsHasMore) return;
        if (msgsEl.scrollTop < 80) loadOlderMessages();
      });
    });
  })();
  $('wa-replybar-close').addEventListener('click', cancelReply);
  $('wa-comp-attach').addEventListener('click', function () { $('wa-comp-file').click(); });
  $('wa-comp-file').addEventListener('change', function () { setAttachment(this.files && this.files[0]); });
  $('wa-attach-close').addEventListener('click', clearAttachment);
  $('wa-comp-ta').addEventListener('paste', function (e) {
    var files = e.clipboardData && e.clipboardData.files;
    if (files && files.length) { e.preventDefault(); setAttachment(files[0]); }
  });
  (function wireDrop() {
    var conv = document.querySelector('.wa-conv');
    conv.addEventListener('dragover', function (e) {
      if (!state.activeChatId || !e.dataTransfer || Array.prototype.indexOf.call(e.dataTransfer.types, 'Files') === -1) return;
      e.preventDefault();
      conv.classList.add('wa-conv--drop');
    });
    conv.addEventListener('dragleave', function (e) { if (!conv.contains(e.relatedTarget)) conv.classList.remove('wa-conv--drop'); });
    conv.addEventListener('drop', function (e) {
      conv.classList.remove('wa-conv--drop');
      if (!state.activeChatId || !e.dataTransfer || !e.dataTransfer.files.length) return;
      e.preventDefault();
      setAttachment(e.dataTransfer.files[0]);
    });
  })();
  $('wa-comp-mic').addEventListener('click', startRecording);
  $('wa-rec-send').addEventListener('click', function () { stopRecording(false); });
  $('wa-rec-cancel').addEventListener('click', function () { stopRecording(true); });
  $('wa-chat-more').addEventListener('click', function (e) { e.stopPropagation(); openChatMenu(this); });
  $('wa-fwd-q').addEventListener('input', renderForward);
  $('wa-fwd-send').addEventListener('click', sendForward);
  $('wa-fwd-close').addEventListener('click', function () { $('wa-fwd').close(); });
  $('wa-edit-save').addEventListener('click', saveEdit);
  $('wa-edit-close').addEventListener('click', function () { $('wa-edit').close(); });

  // "Send reminder": preview the missing-items reminder, then send it in this chat.
  var remindChat = null;
  function openRemind(l) {
    remindChat = state.activeChatId;
    $('wa-remind-title').textContent = l.reminder.label;
    $('wa-remind-ta').value = l.reminder.body;
    $('wa-remind').showModal();
  }
  $('wa-remind-send').addEventListener('click', function () {
    var txt = ($('wa-remind-ta').value || '').trim();
    $('wa-remind').close();
    // The chat changed under the dialog (a poll or a click): never send to the wrong person.
    if (!txt || !remindChat || remindChat !== state.activeChatId) return;
    postText(txt, null);
  });
  $('wa-remind-close').addEventListener('click', function () { $('wa-remind').close(); });
  $('wa-edit-ta').addEventListener('keydown', function (e) {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); saveEdit(); }
  });
  $('wa-msgs').addEventListener('scroll', closePop);
  $('wa-comp-ta').addEventListener('keydown', function (e) {
    if (e.key === 'Escape' && state.replyTo) { cancelReply(); return; }
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  });

  loadChats().then(openFromUrl);
  loadLabels();
  setInterval(poll, 30000);
  document.addEventListener('visibilitychange', function () { if (!document.hidden) poll(); });
})();
</script>
</body>
</html>
"""
