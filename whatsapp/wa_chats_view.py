"""
Agent inbox UI — a WhatsApp-Web-style two-pane chat browser backed by WAHA + the
WhatsAppMessage table. The page is htpasswd-gated at nginx, so the bearer token
for the send composer is rendered into the page source intentionally.
"""
import hashlib
import json
import logging
import re
from datetime import datetime, time, timedelta, timezone as dt_tz

import requests

from django.conf import settings
from django.db.models import Q
from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .models import WhatsAppMessage


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


def _waha_base():
    return (getattr(settings, 'WAHA_BASE_URL', 'http://127.0.0.1:3000') or '').rstrip('/')


def _rewrite_waha_url(url):
    if not url:
        return url
    s = str(url)
    base = _waha_base()
    # Idempotent: already same-origin under /waha.
    if s.startswith('/waha/'):
        return s
    for prefix in (base, 'http://127.0.0.1:3000'):
        if prefix and s.startswith(prefix):
            tail = s[len(prefix):]
            if not tail.startswith('/'):
                tail = '/' + tail
            return '/waha' + tail
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
        or sid
    )
    return {'id': sid, 'name': name}


def _sender_color(sender_id):
    if not sender_id:
        return _SENDER_PALETTE[0]
    h = hashlib.md5(str(sender_id).encode('utf-8')).digest()
    return _SENDER_PALETTE[h[0] % len(_SENDER_PALETTE)]


def _row_to_dict(row, chat_id):
    payload = row.raw_payload if isinstance(row.raw_payload, dict) else {}
    inner = payload.get('payload') if isinstance(payload, dict) else None
    type_source = inner if isinstance(inner, dict) else payload
    mtype = _msg_type(type_source) or row.message_type or 'text'
    if mtype == 'unknown' and row.message_type:
        mtype = row.message_type
    media = _extract_media(row)
    is_group = str(chat_id).endswith('@g.us')
    sender = None
    if is_group:
        sender_payload = inner if isinstance(inner, dict) else payload
        sender = _group_sender(sender_payload)
        if sender and sender.get('id'):
            sender['color'] = _sender_color(sender['id'])
    return {
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
    }


def _live_to_dict(msg, chat_id):
    if not isinstance(msg, dict):
        return None
    waha_id = msg.get('id') or ''
    mtype = _msg_type(msg)
    media = _extract_media_from_payload(msg)
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
    return {
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
    }


def _messages_response(request, chat_id):
    if not chat_id:
        return JsonResponse({"ok": False, "error": "chatId required"}, status=400)

    stripped_id = _strip_jid(chat_id)
    is_group = str(chat_id).endswith('@g.us')

    try:
        limit = int(request.GET.get('limit', '1000'))
    except (TypeError, ValueError):
        limit = 1000
    if limit < 1:
        limit = 1
    if limit > 2000:
        limit = 2000

    now_qatar = datetime.now(QATAR_OFFSET)
    today_start_qatar = datetime.combine(now_qatar.date(), time(0, 0), tzinfo=QATAR_OFFSET)
    today_start_utc = today_start_qatar.astimezone(dt_tz.utc)
    today_start_ts = int(today_start_utc.timestamp())

    qs = (
        WhatsAppMessage.objects
        .filter(received_at__lt=today_start_utc)
        .filter(Q(from_number=stripped_id) | Q(to_number=stripped_id))
        .order_by('-received_at')[:limit]
    )
    db_rows = list(qs)
    db_rows.reverse()

    db_dicts = [_row_to_dict(r, chat_id) for r in db_rows]
    seen_ids = {r.waha_message_id for r in db_rows if r.waha_message_id}

    if not db_rows:
        live_limit = 300
        cutoff_ts = 0
    else:
        live_limit = 100
        cutoff_ts = today_start_ts

    live_msgs = []
    base = _waha_base()
    session = getattr(settings, 'WAHA_DEFAULT_SESSION', 'default') or 'default'
    api_key = getattr(settings, 'WAHA_API_KEY', '') or ''
    url = f"{base}/api/{session}/chats/{chat_id}/messages"
    try:
        resp = requests.get(
            url,
            params={'limit': live_limit, 'downloadMedia': 'false'},
            headers={'X-Api-Key': api_key},
            timeout=20,
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
            live_msgs = []
    except (requests.exceptions.Timeout, requests.exceptions.RequestException) as e:
        logger.warning("waha live messages failed: %s", e)
        live_msgs = []

    live_dicts = []
    for m in live_msgs:
        if not isinstance(m, dict):
            continue
        wid = str(m.get('id') or '')
        if wid and wid in seen_ids:
            continue
        ts = int(m.get('timestamp') or 0)
        if ts < cutoff_ts:
            continue
        d = _live_to_dict(m, chat_id)
        if d is not None:
            live_dicts.append(d)
            if wid:
                seen_ids.add(wid)

    merged = db_dicts + live_dicts
    merged.sort(key=lambda x: x.get('timestamp') or 0)

    return JsonResponse({"ok": True, "messages": merged, "is_group": is_group}, status=200)


@require_http_methods(["GET", "POST"])
def wa_chats(request):
    if request.method == 'POST':
        return wa_chats_send(request)

    if request.GET.get('messages') == '1':
        chat_id = (request.GET.get('chatId') or '').strip()
        return _messages_response(request, chat_id)

    return _render_page(request)


@csrf_exempt
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

    session = data.get('session') or getattr(settings, 'WAHA_DEFAULT_SESSION', 'default') or 'default'

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


@csrf_exempt
@require_http_methods(["POST"])
def wa_chats_resync(request):
    chat_id = (request.GET.get('chatId') or '').strip()
    if not chat_id:
        return JsonResponse({"ok": False, "error": "chatId required"}, status=400)

    base = _waha_base()
    session = getattr(settings, 'WAHA_DEFAULT_SESSION', 'default') or 'default'
    api_key = getattr(settings, 'WAHA_API_KEY', '') or ''
    url = f"{base}/api/{session}/chats/{chat_id}/messages"

    try:
        resp = requests.get(
            url,
            params={'limit': 200, 'downloadMedia': 'true'},
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
        if not isinstance(m, dict):
            continue
        waha_id = str(m.get('id') or '')
        if not waha_id:
            continue
        total += 1

        from_jid = m.get('from') or ''
        to_jid = m.get('to') or ''
        from_number = _strip_jid(from_jid)
        to_number = _strip_jid(to_jid)
        body_text = m.get('body') or ''
        message_type = _msg_type(m)

        media = m.get('media') if isinstance(m.get('media'), dict) else {}
        media_url = media.get('url') or ''
        media_mime = media.get('mimetype') or media.get('mime') or ''

        ts = m.get('timestamp')
        if isinstance(ts, (int, float)):
            received_at = datetime.fromtimestamp(ts, tz=dt_tz.utc)
        else:
            received_at = None

        direction = 'outbound' if m.get('fromMe') is True else 'inbound'

        defaults = {
            'session': session,
            'direction': direction,
            'from_number': from_number,
            'to_number': to_number,
            'body': body_text,
            'message_type': message_type,
            'media_url': media_url,
            'media_mime': media_mime,
            'status': 'archived',
            'received_at': received_at,
            'raw_payload': m,
        }

        obj, created = WhatsAppMessage.objects.get_or_create(
            waha_message_id=waha_id,
            defaults=defaults,
        )
        if created:
            inserted += 1
        else:
            # Backfill media if previously missing; never clobber existing.
            changed = False
            if not obj.media_url and media_url:
                obj.media_url = media_url
                changed = True
            if not obj.media_mime and media_mime:
                obj.media_mime = media_mime
                changed = True
            if changed:
                obj.save(update_fields=['media_url', 'media_mime', 'updated_at'])

    return JsonResponse({"ok": True, "count": total, "inserted": inserted, "messages": []}, status=200)


def _render_page(request):
    bearer = getattr(settings, 'WAHA_AGENT_TOKEN', '') or ''
    session = getattr(settings, 'WAHA_DEFAULT_SESSION', 'default') or 'default'
    html = (
        _CHATS_HTML
        .replace('%BEARER%', bearer)
        .replace('%SESSION%', session)
    )
    return HttpResponse(html, content_type='text/html; charset=utf-8')


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
  width: 100%;
  border: 0.0625rem solid var(--wa-border);
  border-radius: 0.5rem;
  padding: 0.4375rem 0.625rem;
  font-size: 0.8125rem;
  background: #fff;
  outline: none;
}
.wa-search:focus { border-color: var(--wa-brand); }
.wa-side__selects { display: flex; gap: 0.375rem; }
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
.wa-row__body { flex: 1; min-width: 0; }
.wa-row__top {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  gap: 0.5rem;
}
.wa-row__name {
  font-size: 0.875rem;
  color: #111b21;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 11rem;
}
.wa-row__time { font-size: 0.6875rem; color: var(--wa-muted); flex: 0 0 auto; }
.wa-row__preview {
  color: var(--wa-muted);
  font-size: 0.8125rem;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
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
}
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
.wa-media-img { max-width: 100%; border-radius: 0.375rem; display: block; }
.wa-media-video { max-width: 100%; border-radius: 0.375rem; display: block; }
.wa-media-audio { width: 100%; }
.wa-doc { color: #027eb5; text-decoration: none; }

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
</style>
</head>
<body>
<div class="wa-app">
  <aside class="wa-side">
    <div class="wa-side__hdr">
      <span class="wa-chip">WAHA</span>
      <span class="wa-side__phone" id="wa-phone-text">agent inbox</span>
    </div>
    <div class="wa-side__filters">
      <input class="wa-search" id="wa-search" placeholder="Search or new number…" autocomplete="off">
      <div class="wa-side__selects">
        <select class="wa-select" id="wa-type-filter">
          <option value="all">All chats</option>
          <option value="dm">Direct</option>
          <option value="group">Groups</option>
        </select>
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
      <button class="wa-btn wa-btn--ghost" id="wa-resync" type="button" title="Resync from WAHA">↻ Resync</button>
    </div>
    <div class="wa-msgs" id="wa-msgs">
      <div class="wa-empty">No chat selected.</div>
    </div>
    <div class="wa-err" id="wa-err"></div>
    <div class="wa-comp">
      <textarea class="wa-comp__ta" id="wa-comp-ta" rows="1" placeholder="Type a message" disabled></textarea>
      <button class="wa-comp__send" id="wa-comp-send" type="button" disabled>Send</button>
    </div>
  </section>
</div>

<script>
(function () {
  'use strict';

  var SESSION = '%SESSION%';
  var BEARER  = '%BEARER%';

  var SENDER_PALETTE = ["#06cf9c","#7f66ff","#e542a3","#3fa9f5","#f5871f","#15c2c4","#b85cff","#f04a4a"];
  var LABEL_CACHE_KEY = 'wa_label_map_v1';
  var LABEL_CACHE_TS_KEY = 'wa_label_map_v1_ts';
  var LABEL_TTL_MS = 24 * 60 * 60 * 1000;

  var noLabels = (function () {
    try { return new URLSearchParams(window.location.search).get('nolabels') === '1'; }
    catch (e) { return false; }
  })();

  var state = {
    chats: [],            // raw WAHA chats
    rendered: [],         // currently rendered list (after filters)
    activeChatId: null,
    activeChatName: null,
    activeIsGroup: false,
    labelMap: null,       // {label_id: Set(chat_id)}
    labels: [],           // [{id,name,color}]
    labelsLoaded: false,
  };

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
  function fmtTime(ts) {
    if (!ts) return '';
    try { return new Date(ts * 1000).toLocaleString(); }
    catch (e) { return ''; }
  }
  function fmtShortTime(ts) {
    if (!ts) return '';
    try {
      var d = new Date(ts * 1000);
      var hh = d.getHours();
      var mm = d.getMinutes();
      var ampm = hh >= 12 ? 'pm' : 'am';
      hh = hh % 12; if (!hh) hh = 12;
      return hh + ':' + (mm < 10 ? '0' + mm : mm) + ' ' + ampm;
    } catch (e) { return ''; }
  }
  function chatIsGroup(id) { return String(id || '').endsWith('@g.us'); }

  // ---------- Chat list load + render ----------
  function loadChats() {
    return fetch('/waha/api/' + encodeURIComponent(SESSION) + '/chats?limit=2000', { credentials: 'same-origin' })
      .then(function (r) { return r.ok ? r.json() : []; })
      .then(function (data) {
        var list = Array.isArray(data) ? data : (data && Array.isArray(data.chats) ? data.chats : []);
        state.chats = list.map(function (c) {
          var id = c.id && c.id._serialized ? c.id._serialized : (c.id || '');
          return {
            id: String(id || ''),
            name: c.name || c.formattedTitle || c.pushname || (c.id && c.id.user) || String(id || ''),
            lastMessage: (c.lastMessage && c.lastMessage.body) || '',
            timestamp: c.timestamp || (c.lastMessage && c.lastMessage.timestamp) || 0,
          };
        }).filter(function (c) { return !!c.id; });
        renderList();
      })
      .catch(function () { /* ignore */ });
  }

  function renderList() {
    var listEl = $('wa-list');
    var q = ($('wa-search').value || '').trim();
    var typeF = $('wa-type-filter').value;
    var labelF = $('wa-label-filter').value;

    var filtered = state.chats.slice();

    if (typeF === 'dm') filtered = filtered.filter(function (c) { return c.id.endsWith('@c.us'); });
    else if (typeF === 'group') filtered = filtered.filter(function (c) { return c.id.endsWith('@g.us'); });

    if (labelF && state.labelMap && state.labelMap[labelF]) {
      var allowed = state.labelMap[labelF];
      filtered = filtered.filter(function (c) { return allowed.has ? allowed.has(c.id) : (allowed.indexOf(c.id) !== -1); });
    }

    if (q) {
      var qlc = q.toLowerCase();
      filtered = filtered.filter(function (c) {
        return (c.name && c.name.toLowerCase().indexOf(qlc) !== -1)
            || (c.id && c.id.toLowerCase().indexOf(qlc) !== -1);
      });

      if (/^\d{8,15}$/.test(q)) {
        var virtId = q + '@c.us';
        var hasMatch = filtered.some(function (c) { return c.id === virtId; });
        if (!hasMatch) {
          filtered.unshift({
            id: virtId,
            name: 'New chat: ' + q,
            lastMessage: '',
            timestamp: 0,
            virtual: true,
          });
        }
      }
    }

    filtered.sort(function (a, b) { return (b.timestamp || 0) - (a.timestamp || 0); });

    state.rendered = filtered;

    if (!filtered.length) {
      listEl.innerHTML = '<div class="wa-empty">No chats.</div>';
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
      av.textContent = initials(c.name);

      var body = document.createElement('div');
      body.className = 'wa-row__body';

      var top = document.createElement('div');
      top.className = 'wa-row__top';
      var nm = document.createElement('div');
      nm.className = 'wa-row__name';
      nm.textContent = c.name;
      var tm = document.createElement('div');
      tm.className = 'wa-row__time';
      tm.textContent = fmtShortTime(c.timestamp);
      top.appendChild(nm); top.appendChild(tm);

      var pv = document.createElement('div');
      pv.className = 'wa-row__preview';
      pv.textContent = c.lastMessage || (c.virtual ? 'Tap to start' : '');

      body.appendChild(top); body.appendChild(pv);
      row.appendChild(av); row.appendChild(body);
      row.addEventListener('click', function () { openChat(c.id, c.name); });

      frag.appendChild(row);
    });
    listEl.innerHTML = '';
    listEl.appendChild(frag);
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
    populateLabelSelect();
    state.labelsLoaded = true;
    return true;
  }
  function populateLabelSelect() {
    var sel = $('wa-label-filter');
    var current = sel.value;
    sel.innerHTML = '';
    var optAll = document.createElement('option');
    optAll.value = ''; optAll.textContent = 'All labels';
    sel.appendChild(optAll);
    state.labels.forEach(function (lb) {
      var o = document.createElement('option');
      o.value = lb.id;
      o.textContent = lb.name || lb.id;
      sel.appendChild(o);
    });
    if (current) sel.value = current;
  }
  function loadLabels() {
    if (noLabels) return;
    var cached = readLabelCache();
    if (cached && hydrateLabelCache(cached)) return;

    fetch('/waha/api/' + encodeURIComponent(SESSION) + '/labels', { credentials: 'same-origin' })
      .then(function (r) { return r.ok ? r.json() : []; })
      .then(function (labels) {
        if (!Array.isArray(labels)) labels = [];
        state.labels = labels.map(function (lb) {
          return { id: String(lb.id || ''), name: lb.name || '', color: lb.color || '' };
        }).filter(function (lb) { return !!lb.id; });
        populateLabelSelect();

        var map = {};
        var pending = state.labels.map(function (lb) {
          return fetch('/waha/api/' + encodeURIComponent(SESSION) + '/labels/' + encodeURIComponent(lb.id) + '/chats',
                       { credentials: 'same-origin' })
            .then(function (r) { return r.ok ? r.json() : []; })
            .then(function (chats) {
              if (!Array.isArray(chats)) chats = [];
              var set = new Set();
              chats.forEach(function (c) {
                var id = c && c.id && c.id._serialized ? c.id._serialized : (c && c.id) || '';
                if (id) set.add(String(id));
              });
              map[lb.id] = set;
            })
            .catch(function () { map[lb.id] = new Set(); });
        });
        Promise.all(pending).then(function () {
          state.labelMap = map;
          state.labelsLoaded = true;
          writeLabelCache(map, state.labels);
        });
      })
      .catch(function () { /* ignore */ });
  }

  // ---------- Conversation ----------
  function openChat(id, name) {
    state.activeChatId = id;
    state.activeChatName = name;
    state.activeIsGroup = chatIsGroup(id);

    var av = $('wa-conv-avatar');
    av.textContent = initials(name);
    av.style.background = avatarColor(id);
    $('wa-conv-name').textContent = name || id;
    $('wa-conv-sub').textContent = id;
    $('wa-comp-ta').disabled = false;
    $('wa-comp-send').disabled = false;

    Array.prototype.forEach.call(document.querySelectorAll('.wa-row'), function (r) {
      r.classList.toggle('wa-row--active', r.dataset.chatId === id);
    });

    loadMessages();
  }

  function loadMessages() {
    if (!state.activeChatId) return;
    var url = '/waha/wa-chats/?messages=1&chatId=' + encodeURIComponent(state.activeChatId) + '&limit=1000';
    fetch(url, { credentials: 'same-origin' })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (!data || !data.ok) {
          showError((data && data.error) || 'Failed to load messages');
          return;
        }
        renderMessages(data.messages || []);
      })
      .catch(function (e) { showError('Network error: ' + e); });
  }

  function renderBody(msg) {
    var wrap = document.createElement('div');
    var t = msg.type || 'text';
    var media = msg.media || null;

    if (t === 'image' && media && media.url) {
      var img = document.createElement('img');
      img.className = 'wa-media-img';
      img.src = media.url;
      wrap.appendChild(img);
      if (msg.body) {
        var cap = document.createElement('div');
        cap.style.marginTop = '0.25rem';
        cap.textContent = msg.body;
        wrap.appendChild(cap);
      }
    } else if (t === 'video' && media && media.url) {
      var v = document.createElement('video');
      v.className = 'wa-media-video';
      v.controls = true; v.src = media.url;
      wrap.appendChild(v);
      if (msg.body) {
        var cap2 = document.createElement('div');
        cap2.style.marginTop = '0.25rem';
        cap2.textContent = msg.body;
        wrap.appendChild(cap2);
      }
    } else if (t === 'audio' && media && media.url) {
      var au = document.createElement('audio');
      au.className = 'wa-media-audio';
      au.controls = true; au.src = media.url;
      wrap.appendChild(au);
    } else if (t === 'document' && media && media.url) {
      var a = document.createElement('a');
      a.className = 'wa-doc'; a.target = '_blank'; a.rel = 'noopener';
      a.href = media.url;
      a.textContent = '📎 ' + (msg.body || 'Document');
      wrap.appendChild(a);
    } else if (t === 'location') {
      var loc = document.createElement('span');
      loc.textContent = '📍 location';
      wrap.appendChild(loc);
    } else if (t === 'sticker' && media && media.url) {
      var st = document.createElement('img');
      st.className = 'wa-media-img';
      st.style.maxWidth = '8rem';
      st.src = media.url;
      wrap.appendChild(st);
    } else {
      var s = document.createElement('span');
      s.textContent = msg.body || '';
      wrap.appendChild(s);
    }
    return wrap;
  }

  function senderHeader(sender) {
    if (!sender) return null;
    var hdr = document.createElement('div');
    hdr.className = 'wa-bubble__sender';
    hdr.style.color = sender.color || senderColor(sender.id);
    hdr.textContent = sender.name || sender.id || '';
    if (sender.id) {
      var idSpan = document.createElement('span');
      idSpan.className = 'wa-bubble__sender-id';
      idSpan.textContent = ' +' + sender.id;
      hdr.appendChild(idSpan);
    }
    return hdr;
  }

  function renderMessages(msgs) {
    hideError();
    var box = $('wa-msgs');
    box.innerHTML = '';
    if (!msgs.length) {
      box.innerHTML = '<div class="wa-empty">No messages yet.</div>';
      return;
    }
    msgs.forEach(function (m) {
      var row = document.createElement('div');
      row.className = 'wa-msg ' + (m.direction === 'outbound' ? 'wa-msg--out' : 'wa-msg--in');
      var bubble = document.createElement('div');
      bubble.className = 'wa-bubble' + (m.direction === 'outbound' ? ' wa-bubble--out' : '');

      if (state.activeIsGroup && m.direction !== 'outbound' && m.sender) {
        var sh = senderHeader(m.sender);
        if (sh) bubble.appendChild(sh);
      }

      bubble.appendChild(renderBody(m));

      var tm = document.createElement('div');
      tm.className = 'wa-bubble__time';
      tm.textContent = fmtTime(m.timestamp);
      bubble.appendChild(tm);

      row.appendChild(bubble);
      box.appendChild(row);
    });
    box.scrollTop = box.scrollHeight;
  }

  function appendOutgoingLocal(text) {
    var box = $('wa-msgs');
    if (box.querySelector('.wa-empty')) box.innerHTML = '';
    var row = document.createElement('div');
    row.className = 'wa-msg wa-msg--out';
    var bubble = document.createElement('div');
    bubble.className = 'wa-bubble wa-bubble--out';
    var s = document.createElement('span');
    s.textContent = text;
    bubble.appendChild(s);
    var tm = document.createElement('div');
    tm.className = 'wa-bubble__time';
    tm.textContent = fmtTime(Math.floor(Date.now() / 1000));
    bubble.appendChild(tm);
    row.appendChild(bubble);
    box.appendChild(row);
    box.scrollTop = box.scrollHeight;
  }

  function showError(msg) {
    var el = $('wa-err');
    el.textContent = msg;
    el.style.display = 'block';
    setTimeout(hideError, 5000);
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
    if (!txt) return;

    var btn = $('wa-comp-send');
    btn.disabled = true;

    fetch('/waha/wa-chats/send/', {
      method: 'POST',
      credentials: 'same-origin',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': 'Bearer ' + BEARER,
      },
      body: JSON.stringify({ to: state.activeChatId, text: txt }),
    })
      .then(function (r) { return r.json().then(function (j) { return { ok: r.ok, status: r.status, body: j }; }); })
      .then(function (res) {
        btn.disabled = false;
        if (res.ok && res.body && res.body.ok) {
          ta.value = '';
          appendOutgoingLocal(txt);
        } else {
          showError('Send failed: ' + (res.body && (res.body.waha || res.body.error) || res.status));
        }
      })
      .catch(function (e) {
        btn.disabled = false;
        showError('Send error: ' + e);
      });
  }

  // ---------- Resync ----------
  function resyncActive() {
    if (!state.activeChatId) return;
    var btn = $('wa-resync');
    btn.disabled = true;
    fetch('/waha/wa-chats/resync/?chatId=' + encodeURIComponent(state.activeChatId), {
      method: 'POST',
      credentials: 'same-origin',
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
    loadChats();
    if (state.activeChatId) loadMessages();
  }

  // ---------- Wire up ----------
  $('wa-search').addEventListener('input', renderList);
  $('wa-type-filter').addEventListener('change', renderList);
  $('wa-label-filter').addEventListener('change', renderList);
  $('wa-resync').addEventListener('click', resyncActive);
  $('wa-comp-send').addEventListener('click', sendMessage);
  $('wa-comp-ta').addEventListener('keydown', function (e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  });

  loadChats();
  loadLabels();
  setInterval(poll, 30000);
})();
</script>
</body>
</html>
"""
