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
    if _is_noise_message(type_source):
        return None
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
        'location': location,
        'verification_job': verification_job,
    }


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


def _live_to_dict(msg, chat_id):
    if not isinstance(msg, dict):
        return None
    if _is_noise_message(msg):
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
    """
    Two modes:
      - Initial open  (no before_ts): newest `limit` messages = DB recent + WAHA live, deduped.
      - Scroll-up    (before_ts=X):   newest `limit` messages older than X.
                                       DB by received_at < X; WAHA by offset, filtered by ts.
    Always returned ASCENDING by ts so the JS can append/prepend without re-sorting.
    """
    if not chat_id:
        return JsonResponse({"ok": False, "error": "chatId required"}, status=400)

    stripped_id = _strip_jid(chat_id)
    is_group = str(chat_id).endswith('@g.us')

    try:
        limit = int(request.GET.get('limit', '50'))
    except (TypeError, ValueError):
        limit = 50
    if limit < 1:
        limit = 1
    if limit > 200:
        limit = 200

    try:
        before_ts = int(request.GET.get('before_ts', '0') or '0')
    except (TypeError, ValueError):
        before_ts = 0

    base = _waha_base()
    session = getattr(settings, 'WAHA_DEFAULT_SESSION', 'default') or 'default'
    api_key = getattr(settings, 'WAHA_API_KEY', '') or ''

    if before_ts > 0:
        # ---- Older-page mode ----
        cutoff_dt = datetime.fromtimestamp(before_ts, tz=dt_tz.utc)
        qs = (
            WhatsAppMessage.objects
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
            older_offset = int(request.GET.get('older_offset', '0') or '0')
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
            d = _live_to_dict(m, chat_id)
            if d is not None:
                live_dicts.append(d)
                if wid:
                    seen_ids.add(wid)

        merged = db_dicts + live_dicts
        merged.sort(key=lambda x: x.get('timestamp') or 0)
        # Trim to caller's requested page size from the OLDER end (we want the
        # newest items just-before before_ts, so keep the tail).
        if len(merged) > limit:
            merged = merged[-limit:]
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
        d = _live_to_dict(m, chat_id)
        if d is not None:
            live_dicts.append(d)
            if wid:
                seen_ids.add(wid)

    merged = db_dicts + live_dicts
    merged.sort(key=lambda x: x.get('timestamp') or 0)
    if len(merged) > limit:
        merged = merged[-limit:]
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

    rows = WhatsAppMessage.objects.values('from_number').annotate(ts=Max('received_at'))
    for r in rows:
        n = r.get('from_number') or ''
        ts = r.get('ts')
        if not n or not ts:
            continue
        latest[n] = max(latest.get(n, 0), int(ts.timestamp()))

    rows = WhatsAppMessage.objects.values('to_number').annotate(ts=Max('received_at'))
    for r in rows:
        n = r.get('to_number') or ''
        ts = r.get('ts')
        if not n or not ts:
            continue
        latest[n] = max(latest.get(n, 0), int(ts.timestamp()))

    resp = JsonResponse({"ok": True, "latest": latest}, status=200)
    resp['Cache-Control'] = 'no-store, no-cache, must-revalidate, private'
    return resp


@require_http_methods(["GET", "POST"])
def wa_chats(request):
    if request.method == 'POST':
        return wa_chats_send(request)

    if request.GET.get('messages') == '1':
        chat_id = (request.GET.get('chatId') or '').strip()
        return _messages_response(request, chat_id)

    if request.GET.get('chat_latest') == '1':
        return _chat_latest_response(request)

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
    session = getattr(settings, 'WAHA_DEFAULT_SESSION', 'default') or 'default'
    html = _CHATS_HTML.replace('%SESSION%', session)
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
  display: flex;
  align-items: center;
  gap: 0.1875rem;
  flex: 0 0 auto;
  max-width: 55%;
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

  var SENDER_PALETTE = ["#06cf9c","#7f66ff","#e542a3","#3fa9f5","#f5871f","#15c2c4","#b85cff","#f04a4a"];
  var LABEL_CACHE_KEY = 'wa_label_map_v1';
  var LABEL_CACHE_TS_KEY = 'wa_label_map_v1_ts';
  var LABEL_TTL_MS = 24 * 60 * 60 * 1000;

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
    var url = '/waha/api/' + encodeURIComponent(SESSION) +
              '/chats?limit=' + CHATS_PAGE_SIZE + '&offset=' + fetchOffset;
    return fetch(url, { credentials: 'same-origin' })
      .then(function (r) { return r.ok ? r.json() : []; })
      .then(function (data) {
        var list = Array.isArray(data) ? data : (data && Array.isArray(data.chats) ? data.chats : []);
        if (append) {
          if (list.length < CHATS_PAGE_SIZE) state.chatsExhausted = true;
          state.chatsOffset += list.length;
        }
        var mapped = list.map(function (c) {
          var id = c.id && c.id._serialized ? c.id._serialized : (c.id || '');
          var lastMsg = c.lastMessage || {};
          var lastType = ((lastMsg._data && lastMsg._data.type) || lastMsg.type || '').toString().toLowerCase();
          // WAHA returns the literal string "Unknown number" for unsaved contacts.
          // Treat it the same as a missing name so we can fall back to the phone digits.
          var waName = (c.name || c.formattedTitle || c.pushname || '').trim();
          var hasRealName = !!waName && waName.toLowerCase() !== 'unknown number';
          var digits = (c.id && c.id.user) || String(id || '').split('@')[0] || '';
          var displayName = hasRealName ? waName : (digits ? '+' + digits : String(id));
          return {
            id: String(id || ''),
            name: displayName,
            hasName: hasRealName,
            lastMessage: lastMsg.body || '',
            lastType: lastType,
            timestamp: c.timestamp || lastMsg.timestamp || 0,
            pinned: !!c.pinned,
            unread: parseInt(c.unreadCount, 10) || 0,
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
        // Bump timestamps from our DB if a webhook has seen a more recent
        // message than WAHA's chat.timestamp (WhatsApp Web cache often lags).
        return enrichChatTimes();
      })
      .catch(function () {
        state.chatsLoading = false;
      });
  }
  function enrichChatTimes() {
    return fetch('/waha/wa-chats/?chat_latest=1', { credentials: 'same-origin' })
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

    // WhatsApp ordering: pinned first (preserving recency within pinned),
    // then everything else by timestamp desc. Virtual phone-search rows go to top.
    filtered.sort(function (a, b) {
      if (!!a.virtual !== !!b.virtual) return a.virtual ? -1 : 1;
      if (!!a.pinned  !== !!b.pinned)  return a.pinned  ? -1 : 1;
      return (b.timestamp || 0) - (a.timestamp || 0);
    });

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
      tm.className = 'wa-row__time' + (c.unread > 0 ? ' wa-row__time--unread' : '');
      tm.textContent = fmtShortTime(c.timestamp);
      top.appendChild(nm); top.appendChild(tm);

      var pvLine = document.createElement('div');
      pvLine.className = 'wa-row__pv-line';
      var pv = document.createElement('div');
      pv.className = 'wa-row__preview';
      pv.textContent = c.lastMessage || (c.virtual ? 'Tap to start' : '');
      pvLine.appendChild(pv);
      if (c.pinned) {
        var pin = document.createElement('span');
        pin.className = 'wa-row__pin';
        pin.textContent = '\u{1F4CC}'; // 📌
        pin.title = 'Pinned';
        pvLine.appendChild(pin);
      }
      if (c.unread > 0) {
        var bd = document.createElement('span');
        bd.className = 'wa-row__unread';
        bd.textContent = c.unread > 99 ? '99+' : String(c.unread);
        pvLine.appendChild(bd);
      }
      var chips = renderLabelChips(c.id);
      if (chips) pvLine.appendChild(chips);

      body.appendChild(top); body.appendChild(pvLine);
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
          return {
            id: String(lb.id || ''),
            name: lb.name || '',
            color: lb.color || '',
            colorHex: lb.colorHex || '',
          };
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
          state.labelsByChat = buildLabelsByChat(map, state.labels);
          state.labelsLoaded = true;
          writeLabelCache(map, state.labels);
          // Re-render so freshly-loaded label chips appear in the chat list.
          renderList();
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
    var url = '/waha/wa-chats/?messages=1&chatId=' + encodeURIComponent(chatIdAtCall) + '&limit=50';
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
    var url = '/waha/wa-chats/?messages=1&chatId=' + encodeURIComponent(chatIdAtCall) +
              '&limit=50&before_ts=' + state.msgsOldestTs +
              '&older_offset=' + (state.msgsLiveOffsetSeen || 0);
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
          return;
        }
        state.msgs = older.concat(state.msgs);
        state.msgsOldestTs = older[0].timestamp || state.msgsOldestTs;
        state.msgsLiveOffsetSeen += older.length;
        state.msgsHasMore = !!res.data.has_more;
        renderMessages(state.msgs);
        // Preserve scroll position so user stays on the same content.
        box.scrollTop = box.scrollHeight - prevHeight;
      })
      .catch(function () {
        state.msgsLoading = false;
        if (loader.parentNode) loader.parentNode.removeChild(loader);
      });
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
      },
      body: JSON.stringify({ to: state.activeChatId, text: txt }),
    })
      .then(function (r) {
        return r.text().then(function (raw) {
          var j = null;
          try { j = JSON.parse(raw); } catch (e) {}
          return { ok: r.ok, status: r.status, body: j, raw: raw };
        });
      })
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
        if (state.chatsLoading || state.chatsExhausted) return;
        var threshold = 200;  // px from bottom
        if (listEl.scrollTop + listEl.clientHeight >= listEl.scrollHeight - threshold) {
          loadChats(true);
        }
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
