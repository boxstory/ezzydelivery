"""
WAHA bridge HTTP views.

Four function-based endpoints:
  - waha_webhook:           public, HMAC-verified, ingests inbound messages
  - waha_messages_list:     bearer-authed, lists & optionally claims messages
  - waha_message_processed: bearer-authed, marks a row processed/failed
  - waha_send:              bearer-authed, proxies an outbound text via WAHA
"""
import json
import logging
import re
import uuid
from datetime import datetime, timezone as dt_timezone

import requests

from django.conf import settings
from django.db import transaction
from django.http import JsonResponse
from django.utils import timezone as dj_timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .auth import _bearer_ok, _verify_waha_hmac
from .models import WhatsAppMessage


logger = logging.getLogger(__name__)


_VALID_STATUSES = {c[0] for c in WhatsAppMessage.STATUS_CHOICES}

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


def _strip_jid(jid):
    # WAHA JIDs look like "97455555555@c.us" or "...@s.whatsapp.net"; we store
    # the bare phone digits so lookups by from_number/to_number stay simple.
    if not jid:
        return ''
    return str(jid).split('@', 1)[0]


def _map_message_type(payload):
    raw = None
    data = payload.get('_data') or {}
    if isinstance(data, dict):
        raw = data.get('type')
    if not raw:
        raw = payload.get('type')
    if not raw:
        return 'text'
    return _WAHA_TYPE_MAP.get(str(raw).lower(), 'unknown')


def _serialize_message(obj):
    return {
        'id': obj.id,
        'waha_message_id': obj.waha_message_id,
        'direction': obj.direction,
        'from_number': obj.from_number,
        'to_number': obj.to_number,
        'body': obj.body,
        'message_type': obj.message_type,
        'media_url': obj.media_url,
        'media_mime': obj.media_mime,
        'status': obj.status,
        'received_at': obj.received_at.isoformat() if obj.received_at else None,
        'picked_up_at': obj.picked_up_at.isoformat() if obj.picked_up_at else None,
        'business_id': obj.business_id,
        'order_id': obj.order_id,
    }


@csrf_exempt
@require_http_methods(["POST"])
def waha_webhook(request):
    raw_body = request.body
    ok, reason = _verify_waha_hmac(request, raw_body)
    if not ok:
        return JsonResponse({"ok": False, "error": reason}, status=403)

    try:
        try:
            data = json.loads(raw_body.decode('utf-8') if isinstance(raw_body, (bytes, bytearray)) else raw_body)
        except (ValueError, UnicodeDecodeError) as e:
            return JsonResponse({"ok": False, "error": f"invalid json: {e}"}, status=400)

        if not isinstance(data, dict):
            return JsonResponse({"ok": False, "error": "envelope must be object"}, status=400)

        event = data.get("event") or data.get("type")
        if event not in ("message", "message.any"):
            return JsonResponse({"ok": True, "ignored": "event"}, status=200)

        payload = data.get("payload") or {}
        if not isinstance(payload, dict):
            return JsonResponse({"ok": False, "error": "payload must be object"}, status=400)

        # Ignore echoes of messages we ourselves sent through WAHA.
        if payload.get("fromMe") is True:
            return JsonResponse({"ok": True, "ignored": "fromMe"}, status=200)

        waha_message_id = payload.get("id")
        if not waha_message_id:
            return JsonResponse({"ok": False, "error": "missing payload.id"}, status=400)

        from_number = _strip_jid(payload.get("from"))
        to_number = _strip_jid(payload.get("to"))
        body = payload.get("body") or ""
        message_type = _map_message_type(payload)

        media = payload.get("media") or {}
        if not isinstance(media, dict):
            media = {}
        media_url = media.get("url") or ""
        media_mime = media.get("mimetype") or ""

        ts = payload.get("timestamp")
        if isinstance(ts, (int, float)):
            received_at = datetime.fromtimestamp(ts, tz=dt_timezone.utc)
        else:
            received_at = dj_timezone.now()

        session = data.get("session") or getattr(settings, 'WAHA_DEFAULT_SESSION', 'default')

        # update_or_create on waha_message_id makes webhook re-deliveries idempotent.
        obj, created = WhatsAppMessage.objects.update_or_create(
            waha_message_id=str(waha_message_id),
            defaults={
                'session': session,
                'direction': 'inbound',
                'from_number': from_number,
                'to_number': to_number,
                'body': body,
                'message_type': message_type,
                'media_url': media_url,
                'media_mime': media_mime,
                'status': 'received',
                'received_at': received_at,
                'raw_payload': data,
            },
        )

        return JsonResponse({"ok": True, "id": obj.id, "created": created}, status=200)
    except Exception:
        logger.exception("waha_webhook unexpected failure")
        return JsonResponse({"ok": False, "error": "internal"}, status=500)


@require_http_methods(["GET"])
def waha_messages_list(request):
    if not _bearer_ok(request):
        return JsonResponse({"error": "unauthorized"}, status=401)

    status = request.GET.get('status', 'received')
    if status not in _VALID_STATUSES:
        return JsonResponse({"error": f"invalid status: {status}"}, status=400)

    try:
        limit = int(request.GET.get('limit', '50'))
    except (TypeError, ValueError):
        return JsonResponse({"error": "invalid limit"}, status=400)
    if limit < 1:
        limit = 1
    if limit > 200:
        limit = 200

    mark_raw = (request.GET.get('mark_picked_up', '') or '').strip().lower()
    mark_picked_up = mark_raw in {'1', 'true', 'yes', 'y'}

    with transaction.atomic():
        qs = WhatsAppMessage.objects.filter(status=status).order_by('received_at')[:limit]

        if mark_picked_up and status == 'received':
            ids = list(qs.values_list('id', flat=True))
            if ids:
                locked = WhatsAppMessage.objects.select_for_update().filter(id__in=ids)
                locked.update(status='picked_up', picked_up_at=dj_timezone.now())
                rows_qs = WhatsAppMessage.objects.filter(id__in=ids).order_by('received_at')
            else:
                rows_qs = WhatsAppMessage.objects.none()
            rows = [_serialize_message(o) for o in rows_qs]
        else:
            rows = [_serialize_message(o) for o in qs]

    return JsonResponse({"ok": True, "count": len(rows), "messages": rows}, status=200)


@csrf_exempt
@require_http_methods(["POST"])
def waha_message_processed(request, message_id):
    if not _bearer_ok(request):
        return JsonResponse({"error": "unauthorized"}, status=401)

    try:
        body_raw = request.body
        data = json.loads(body_raw.decode('utf-8') if isinstance(body_raw, (bytes, bytearray)) else body_raw) if body_raw else {}
    except (ValueError, UnicodeDecodeError) as e:
        return JsonResponse({"error": f"invalid json: {e}"}, status=400)
    if not isinstance(data, dict):
        return JsonResponse({"error": "body must be object"}, status=400)

    try:
        obj = WhatsAppMessage.objects.get(pk=message_id)
    except WhatsAppMessage.DoesNotExist:
        return JsonResponse({"error": "not found"}, status=404)

    error_kind = (data.get('error_kind') or '').strip()
    if error_kind:
        obj.status = 'failed'
        obj.error_kind = error_kind[:64]
        obj.processed_at = dj_timezone.now()
    else:
        obj.status = 'processed'
        obj.processed_at = dj_timezone.now()
        order_id = data.get('order_id')
        if order_id is not None:
            try:
                from orders.models import Order
                if Order.objects.filter(pk=order_id).exists():
                    obj.order_id = order_id
            except Exception:
                logger.exception("waha_message_processed order lookup failed")

    obj.save()
    return JsonResponse({"ok": True, "id": obj.id, "status": obj.status}, status=200)


@csrf_exempt
@require_http_methods(["POST"])
def waha_send(request):
    if not _bearer_ok(request):
        return JsonResponse({"error": "unauthorized"}, status=401)

    try:
        body_raw = request.body
        data = json.loads(body_raw.decode('utf-8') if isinstance(body_raw, (bytes, bytearray)) else body_raw) if body_raw else {}
    except (ValueError, UnicodeDecodeError) as e:
        return JsonResponse({"error": f"invalid json: {e}"}, status=400)
    if not isinstance(data, dict):
        return JsonResponse({"error": "body must be object"}, status=400)

    to = data.get('to')
    text = data.get('text')
    if not isinstance(to, str) or not isinstance(text, str):
        return JsonResponse({"error": "to and text required"}, status=400)

    session = data.get('session') or getattr(settings, 'WAHA_DEFAULT_SESSION', 'default')

    if '@' not in to:
        digits = re.sub(r'\D', '', to)
        if not digits:
            return JsonResponse({"error": "invalid to"}, status=400)
        to = f"{digits}@c.us"
    else:
        if not _strip_jid(to):
            return JsonResponse({"error": "invalid to"}, status=400)

    url = f"{getattr(settings, 'WAHA_BASE_URL', 'http://127.0.0.1:3000').rstrip('/')}/api/sendText"
    headers = {
        'X-Api-Key': getattr(settings, 'WAHA_API_KEY', '') or '',
        'Content-Type': 'application/json',
    }
    payload = {"chatId": to, "text": text, "session": session}

    waha_status = 0
    waha_body = None
    timed_out = False
    network_err = False

    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=15)
        waha_status = resp.status_code
        try:
            waha_body = resp.json()
        except ValueError:
            waha_body = (resp.text or '')[:4000]
    except requests.exceptions.Timeout:
        timed_out = True
        waha_body = 'timeout'
    except requests.exceptions.RequestException as e:
        network_err = True
        waha_body = f'network error: {e}'[:4000]

    success = (200 <= waha_status < 300) and not timed_out and not network_err

    if success:
        wid = None
        if isinstance(waha_body, dict):
            wid = waha_body.get('id')
            if not wid:
                inner = waha_body.get('_data') or {}
                if isinstance(inner, dict):
                    wid = inner.get('id')
        if not wid:
            wid = f"out-{uuid.uuid4().hex}"
        msg_status = 'processed'
        error_kind = ''
        processed_at = dj_timezone.now()
    else:
        wid = f"out-fail-{uuid.uuid4().hex}"
        msg_status = 'failed'
        error_kind = 'waha_send_error'
        processed_at = dj_timezone.now()

    raw_payload_store = waha_body if isinstance(waha_body, (dict, list)) else {'response': str(waha_body)[:4000]}

    obj = WhatsAppMessage.objects.create(
        waha_message_id=str(wid),
        session=session,
        direction='outbound',
        from_number=getattr(settings, 'WAHA_DEFAULT_FROM', '') or '',
        to_number=_strip_jid(to),
        body=text,
        message_type='text',
        status=msg_status,
        error_kind=error_kind,
        processed_at=processed_at,
        raw_payload=raw_payload_store,
    )

    if isinstance(waha_body, str) and len(waha_body) > 4000:
        waha_body = waha_body[:4000]

    response_body = {
        "ok": success,
        "waha_status": waha_status,
        "message_id": obj.id,
        "waha": waha_body,
    }

    if timed_out:
        http_status = 504
    elif network_err or not success:
        http_status = 502
    else:
        http_status = 200

    return JsonResponse(response_body, status=http_status)
