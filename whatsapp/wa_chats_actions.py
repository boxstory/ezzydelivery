"""
Purpose: Inbox write actions beyond plain text — attachments and voice notes, reactions, forward, edit/delete, number check, archive/unread.
Used by: whatsapp/chats_urls.py (/waha/wa-chats/<action>/), called from the inbox page JS in wa_chats_view.py.
Notes: Every action takes a strict session name and refuses chats under a marketing-only label (label_access). Message ids are WAHA's full serialized ids (`true_<chat>_<key>`), the inbox row's `waha_id`.
"""
import base64
import io
import json
import logging
import re

import requests

from django.conf import settings
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from . import label_access
from . import sessions as wa_sessions
from .models import WhatsAppMessage, WhatsAppReaction
from .wa_chats_view import (
    _CHAT_ID_RE, _REPLY_ID_RE, _no_store, _refuse_hidden, _staff_only, _waha_base,
)


logger = logging.getLogger(__name__)

# WhatsApp sends photos/videos up to 16 MB as media; anything bigger (or of a
# type it will not preview) goes as a document. The overall cap keeps one
# upload + base64 hop to WAHA inside nginx's 60 s response ceiling.
MEDIA_MAX_BYTES = 16 * 1024 * 1024
FILE_MAX_BYTES = 30 * 1024 * 1024
_IMAGE_MIMES = {'image/jpeg', 'image/png'}
# Other stills (WebP from websites, HEIC from iPhones, GIF, BMP…) are re-encoded
# to JPEG so they arrive as a photo rather than a document.
_PHOTO_EXTS = {'jpg', 'jpeg', 'png', 'webp', 'heic', 'heif', 'gif', 'bmp', 'tif', 'tiff', 'avif'}
PHOTO_MAX_SIDE = 2560
_WAHA_TIMEOUT = 50

# A reaction is one emoji (with modifiers / ZWJ sequences), never text.
_EMOJI_MAX_LEN = 16


def _waha(method, path, payload=None, timeout=15):
    """Call WAHA → (ok, status, body). Never raises."""
    api_key = getattr(settings, 'WAHA_API_KEY', '') or ''
    try:
        resp = requests.request(
            method, f"{_waha_base()}{path}", json=payload if payload is not None else {},
            headers={'X-Api-Key': api_key, 'Content-Type': 'application/json'}, timeout=timeout,
        )
    except requests.exceptions.Timeout:
        return False, 0, 'WAHA timed out'
    except requests.exceptions.RequestException as e:
        return False, 0, f'WAHA unreachable: {e}'[:300]
    try:
        body = resp.json()
    except ValueError:
        body = (resp.text or '')[:2000]
    return 200 <= resp.status_code < 300, resp.status_code, body


def _result(ok, status, body, **extra):
    """WAHA outcome → inbox JSON (502 on a WAHA failure, with its message)."""
    if ok:
        return _no_store({"ok": True, **extra})
    err = body.get('message') if isinstance(body, dict) else body
    return _no_store({"ok": False, "waha_status": status, "error": str(err or 'WAHA error')[:500]}, status=502)


def _json_body(request):
    try:
        data = json.loads(request.body.decode('utf-8') or '{}')
    except (ValueError, UnicodeDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _session_or_none(value):
    return value.strip() if wa_sessions.is_valid(value) else None


def _chat_from_message_id(message_id):
    """`true_974..@c.us_KEY[_participant]` → `974..@c.us` (the chat it lives in)."""
    parts = str(message_id).split('_')
    return parts[1] if len(parts) >= 3 else ''


def _own_message(message_id):
    return str(message_id).startswith('true_')


def _set_inner(row, **fields):
    """Write fields into a stored message's WAHA payload (`payload._data` too),
    so the inbox reads the edit/revoke from our copy, which wins over WAHA's."""
    raw = row.raw_payload if isinstance(row.raw_payload, dict) else {}
    inner = raw.get('payload') if isinstance(raw.get('payload'), dict) else raw
    data = inner.get('_data') if isinstance(inner.get('_data'), dict) else {}
    for k, v in fields.items():
        if k == 'body':
            inner['body'] = v
        data[k] = v
    inner['_data'] = data
    row.raw_payload = raw


# ---------- 1 + 2. Attachments and voice notes ----------

def _as_photo(raw, mime, filename):
    """A still image as (bytes, mime, filename) WhatsApp will show as a photo, or None.

    JPEG/PNG up to 16 MB go untouched. Anything else that Pillow can open, or a
    bigger photo, becomes a JPEG with the longest side capped; an animated GIF
    or WebP keeps its first frame. None means "send it as a document".
    """
    if mime in _IMAGE_MIMES and len(raw) <= MEDIA_MAX_BYTES:
        return raw, mime, filename
    ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''
    if mime == 'image/svg+xml' or not (mime.startswith('image/') or ext in _PHOTO_EXTS):
        return None
    try:
        from PIL import Image, ImageOps
        try:
            import pillow_heif
            pillow_heif.register_heif_opener()
        except ImportError:
            pass
        img = Image.open(io.BytesIO(raw))
        img.load()
        img = ImageOps.exif_transpose(img)
        if img.mode in ('RGBA', 'LA', 'P'):
            img = img.convert('RGBA')
            flat = Image.new('RGB', img.size, (255, 255, 255))
            flat.paste(img, mask=img.split()[-1])
            img = flat
        img = img.convert('RGB')
        img.thumbnail((PHOTO_MAX_SIDE, PHOTO_MAX_SIDE))
        out = io.BytesIO()
        img.save(out, 'JPEG', quality=85, optimize=True)
    except Exception as e:  # not an image after all, or one Pillow cannot read
        logger.info('wa inbox: %s not converted to a photo (%s); sending as a document', filename, e)
        return None
    stem = filename.rsplit('.', 1)[0] if '.' in filename else filename
    return out.getvalue(), 'image/jpeg', (stem or 'photo') + '.jpg'


@_staff_only
@require_http_methods(["POST"])
def wa_chats_send_media(request):
    """Multipart: file, to, session, [caption], [reply_to], [voice=1].

    Any still image goes as a photo (WebP/HEIC/GIF… re-encoded to JPEG), video
    up to 16 MB as video, a recording as a voice note (WAHA converts it to
    opus); everything else as a document so it arrives untouched.
    """
    session = _session_or_none(request.POST.get('session'))
    if not session:
        return _no_store({"ok": False, "error": "invalid session"}, status=400)
    to = (request.POST.get('to') or '').strip()
    if not _CHAT_ID_RE.match(to):
        return _no_store({"ok": False, "error": "invalid chat"}, status=400)
    if label_access.chat_hidden(request.user, session, to):
        return _refuse_hidden()
    upload = request.FILES.get('file')
    if not upload:
        return _no_store({"ok": False, "error": "no file"}, status=400)
    if upload.size > FILE_MAX_BYTES:
        return _no_store({"ok": False, "error": f"File is over {FILE_MAX_BYTES // (1024 * 1024)} MB."}, status=413)
    reply_to = (request.POST.get('reply_to') or '').strip()
    if reply_to and not _REPLY_ID_RE.match(reply_to):
        return _no_store({"ok": False, "error": "invalid reply_to"}, status=400)

    mime = (upload.content_type or 'application/octet-stream').split(';')[0].strip().lower()
    filename = (upload.name or 'file').replace('/', '_')[:120]
    caption = (request.POST.get('caption') or '').strip()[:4000]
    as_voice = request.POST.get('voice') == '1'
    raw = upload.read()
    photo = None if as_voice else _as_photo(raw, mime, filename)

    if as_voice:
        endpoint, extra = 'sendVoice', {'convert': True}
    elif photo:
        raw, mime, filename = photo
        endpoint, extra = 'sendImage', {'caption': caption}
    elif mime.startswith('video/') and upload.size <= MEDIA_MAX_BYTES:
        # WhatsApp plays H.264 mp4 only; WAHA's ffmpeg converts anything else.
        endpoint, extra = 'sendVideo', {'caption': caption, 'convert': mime != 'video/mp4'}
    else:
        endpoint, extra = 'sendFile', {'caption': caption}

    payload = {
        'chatId': to,
        'session': session,
        'file': {
            'mimetype': mime,
            'filename': filename,
            'data': base64.b64encode(raw).decode('ascii'),
        },
        **extra,
    }
    if reply_to:
        payload['reply_to'] = reply_to
    ok, status, body = _waha('POST', f'/api/{endpoint}', payload, timeout=_WAHA_TIMEOUT)
    if not ok:
        logger.warning('wa inbox %s failed: %s %s', endpoint, status, str(body)[:300])
    return _result(ok, status, body, sent_as=endpoint)


# ---------- 3. Reactions ----------

@_staff_only
@require_http_methods(["POST"])
def wa_chats_react(request):
    """{session, messageId, emoji} — empty emoji removes our reaction."""
    data = _json_body(request)
    if data is None:
        return _no_store({"ok": False, "error": "invalid json"}, status=400)
    session = _session_or_none(data.get('session'))
    message_id = str(data.get('messageId') or '').strip()
    emoji = str(data.get('emoji') or '').strip()
    if not session or not _REPLY_ID_RE.match(message_id):
        return _no_store({"ok": False, "error": "invalid message"}, status=400)
    if len(emoji) > _EMOJI_MAX_LEN or re.search(r'[\w<>]', emoji):
        return _no_store({"ok": False, "error": "invalid emoji"}, status=400)
    if label_access.chat_hidden(request.user, session, _chat_from_message_id(message_id)):
        return _refuse_hidden()
    ok, status, body = _waha('PUT', '/api/reaction',
                             {'messageId': message_id, 'reaction': emoji, 'session': session})
    if ok:
        WhatsAppReaction.objects.update_or_create(
            session=session, message_id=message_id, sender='me',
            defaults={'emoji': emoji, 'staff': request.user},
        )
    return _result(ok, status, body, emoji=emoji)


def reactions_for(session, message_ids):
    """{message_id: [{'emoji', 'me'}]} for the messages on screen."""
    ids = [m for m in message_ids if m]
    if not ids:
        return {}
    out = {}
    rows = (WhatsAppReaction.objects
            .filter(session=session, message_id__in=ids)
            .exclude(emoji='')
            .order_by('updated_at')
            .values_list('message_id', 'emoji', 'sender'))
    for mid, emoji, sender in rows:
        out.setdefault(mid, []).append({'emoji': emoji, 'me': sender == 'me'})
    return out


# ---------- 4. Forward ----------

@_staff_only
@require_http_methods(["POST"])
def wa_chats_forward(request):
    """{session, messageId, chatIds: [...]} — forward one message to up to 5 chats."""
    data = _json_body(request)
    if data is None:
        return _no_store({"ok": False, "error": "invalid json"}, status=400)
    session = _session_or_none(data.get('session'))
    message_id = str(data.get('messageId') or '').strip()
    targets = data.get('chatIds')
    if not session or not _REPLY_ID_RE.match(message_id):
        return _no_store({"ok": False, "error": "invalid message"}, status=400)
    if not isinstance(targets, list) or not 1 <= len(targets) <= 5:
        return _no_store({"ok": False, "error": "pick 1 to 5 chats"}, status=400)
    targets = [str(t).strip() for t in targets]
    if any(not _CHAT_ID_RE.match(t) for t in targets):
        return _no_store({"ok": False, "error": "invalid chat"}, status=400)
    # Neither the source nor any destination may be a chat this login cannot open.
    for chat in [_chat_from_message_id(message_id)] + targets:
        if label_access.chat_hidden(request.user, session, chat):
            return _refuse_hidden()
    failed = []
    for chat in targets:
        ok, status, body = _waha('POST', '/api/forwardMessage',
                                 {'chatId': chat, 'messageId': message_id, 'session': session}, timeout=20)
        if not ok:
            failed.append(chat)
            logger.warning('wa inbox forward to %s failed: %s %s', chat, status, str(body)[:300])
    if failed:
        return _no_store({"ok": False, "failed": failed,
                          "error": f"Forward failed for {len(failed)} of {len(targets)} chat(s)."}, status=502)
    return _no_store({"ok": True, "sent": len(targets)})


# ---------- 5. Edit / delete our own messages ----------

def _own_message_request(request):
    """Shared checks for edit/delete → (session, chat_id, message_id) or a response."""
    data = _json_body(request)
    if data is None:
        return None, _no_store({"ok": False, "error": "invalid json"}, status=400)
    session = _session_or_none(data.get('session'))
    chat_id = str(data.get('chatId') or '').strip()
    message_id = str(data.get('messageId') or '').strip()
    if not session or not _CHAT_ID_RE.match(chat_id) or not _REPLY_ID_RE.match(message_id):
        return None, _no_store({"ok": False, "error": "invalid message"}, status=400)
    if not _own_message(message_id):
        return None, _no_store({"ok": False, "error": "Only messages we sent can be changed."}, status=400)
    if label_access.chat_hidden(request.user, session, chat_id):
        return None, _refuse_hidden()
    return (session, chat_id, message_id, data), None


@_staff_only
@require_http_methods(["POST"])
def wa_chats_edit(request):
    """{session, chatId, messageId, text}. WhatsApp allows edits for 15 minutes."""
    parsed, refusal = _own_message_request(request)
    if refusal:
        return refusal
    session, chat_id, message_id, data = parsed
    text = str(data.get('text') or '').strip()
    if not text:
        return _no_store({"ok": False, "error": "text required"}, status=400)
    ok, status, body = _waha('PUT', f'/api/{session}/chats/{chat_id}/messages/{message_id}', {'text': text})
    if ok:
        row = WhatsAppMessage.objects.filter(session=session, waha_message_id=message_id).first()
        if row:
            row.body = text
            _set_inner(row, body=text, latestEditSenderTimestampMs=int(timezone.now().timestamp() * 1000))
            row.save(update_fields=['body', 'raw_payload', 'updated_at'])
    return _result(ok, status, body, text=text)


@_staff_only
@require_http_methods(["POST"])
def wa_chats_delete(request):
    """{session, chatId, messageId} — delete for everyone (WhatsApp's ~2-day window)."""
    parsed, refusal = _own_message_request(request)
    if refusal:
        return refusal
    session, chat_id, message_id, _data = parsed
    ok, status, body = _waha('DELETE', f'/api/{session}/chats/{chat_id}/messages/{message_id}', None)
    if ok:
        row = WhatsAppMessage.objects.filter(session=session, waha_message_id=message_id).first()
        if row:
            # The archived file is kept (records); the inbox stops showing it.
            # message_type must change too: a stored 'text' overrides the
            # payload's 'revoked' and the row would render as an empty bubble.
            row.body = ''
            row.message_type = 'unknown'
            _set_inner(row, body='', type='revoked')
            row.save(update_fields=['body', 'message_type', 'raw_payload', 'updated_at'])
    return _result(ok, status, body)


# ---------- 6. Is this number on WhatsApp? (new conversation / number search) ----------

@_staff_only
@require_http_methods(["GET"])
def wa_chats_check_number(request):
    """?phone=<digits>&session= → {exists, chatId}. Only called for a typed number
    that has no chat yet, so it never runs per message or per list row."""
    session = _session_or_none(request.GET.get('session'))
    phone = re.sub(r'\D', '', request.GET.get('phone') or '')
    if not session or not 8 <= len(phone) <= 15:
        return _no_store({"ok": False, "error": "invalid number"}, status=400)
    api_key = getattr(settings, 'WAHA_API_KEY', '') or ''
    try:
        resp = requests.get(f"{_waha_base()}/api/contacts/check-exists",
                            params={'phone': phone, 'session': session},
                            headers={'X-Api-Key': api_key}, timeout=15)
        body = resp.json()
    except (requests.exceptions.RequestException, ValueError):
        return _no_store({"ok": False, "error": "WAHA unreachable"}, status=502)
    if not resp.ok or not isinstance(body, dict):
        return _no_store({"ok": False, "error": "check failed"}, status=502)
    chat_id = str(body.get('chatId') or '')
    exists = bool(body.get('numberExists'))
    if exists and chat_id and label_access.chat_hidden(request.user, session, chat_id):
        return _refuse_hidden()
    return _no_store({"ok": True, "exists": exists, "chatId": chat_id if _CHAT_ID_RE.match(chat_id) else ''})


# ---------- 7. Archive / unarchive / mark unread ----------

_CHAT_ACTIONS = {'archive', 'unarchive', 'unread'}


@_staff_only
@require_http_methods(["POST"])
def wa_chats_chat_action(request):
    """{session, chatId, action: archive|unarchive|unread}."""
    data = _json_body(request)
    if data is None:
        return _no_store({"ok": False, "error": "invalid json"}, status=400)
    session = _session_or_none(data.get('session'))
    chat_id = str(data.get('chatId') or '').strip()
    action = data.get('action')
    if not session or not _CHAT_ID_RE.match(chat_id) or action not in _CHAT_ACTIONS:
        return _no_store({"ok": False, "error": "invalid request"}, status=400)
    if label_access.chat_hidden(request.user, session, chat_id):
        return _refuse_hidden()
    ok, status, body = _waha('POST', f'/api/{session}/chats/{chat_id}/{action}', {})
    return _result(ok, status, body, action=action)
