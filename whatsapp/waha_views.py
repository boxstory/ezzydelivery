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

from . import sessions as wa_sessions
from .auth import _bearer_ok, _verify_waha_hmac
from .models import WhatsAppMessage
from core.validators import safe_int


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


def fetch_waha_session_status(session=None, timeout=4):
    """Return the WAHA session state for ops UIs. Cached for 30s.

    The fetch happens whenever WAHA_API_KEY is configured — independent of the
    feature flags (WAHA_ENABLED, WAHA_VERIFY_USE_WAHA). The banner should show
    real WAHA reachability so ops can confirm the session is healthy regardless
    of whether the platform is currently routing through it.

    Shape: {
        'configured':  bool — WAHA_API_KEY is set,
        'reachable':   bool — got a 2xx from WAHA,
        'status':      'WORKING' | 'SCAN_QR_CODE' | 'STARTING' | 'STOPPED'
                       | 'FAILED' | 'UNREACHABLE' | 'NOT_CONFIGURED' | '',
        'session':     session name,
        'phone':       '+97455555555' when connected, else '',
        'push_name':   display name when WAHA returns one, else '',
        'used_for_orders':  bool — WAHA_ENABLED flag (platform-wide routing),
        'used_for_verify':  bool — WAHA_VERIFY_USE_WAHA flag,
        'fetched_at':  ISO timestamp,
        'error':       str when reachable=False (network/HTTP error).
    }
    """
    from django.core.cache import cache

    session = wa_sessions.normalize(session)
    used_for_orders = bool(getattr(settings, 'WAHA_ENABLED', False))
    used_for_verify = bool(getattr(settings, 'WAHA_VERIFY_USE_WAHA', False))
    api_key = getattr(settings, 'WAHA_API_KEY', '') or ''

    if not api_key:
        return {
            'configured': False, 'reachable': False,
            'status': 'NOT_CONFIGURED', 'session': session,
            'phone': '', 'push_name': '',
            'used_for_orders': used_for_orders,
            'used_for_verify': used_for_verify,
            'fetched_at': dj_timezone.now().isoformat(),
            'error': 'WAHA_API_KEY not set',
        }

    cache_key = f'waha_session_status_{session}'
    cached = cache.get(cache_key)
    if cached is not None:
        # Refresh flag-derived fields each call (cheap, no API hit).
        cached['used_for_orders'] = used_for_orders
        cached['used_for_verify'] = used_for_verify
        return cached

    base = getattr(settings, 'WAHA_BASE_URL', 'http://127.0.0.1:3000').rstrip('/')
    url = f'{base}/api/sessions/{session}'
    headers = {'X-Api-Key': api_key, 'Accept': 'application/json'}

    result = {
        'configured': True, 'reachable': False,
        'status': 'UNREACHABLE', 'session': session,
        'phone': '', 'push_name': '',
        'used_for_orders': used_for_orders,
        'used_for_verify': used_for_verify,
        'fetched_at': dj_timezone.now().isoformat(),
        'error': '',
    }
    try:
        resp = requests.get(url, headers=headers, timeout=timeout)
    except requests.exceptions.RequestException as e:
        result['error'] = f'WAHA unreachable: {e}'
        cache.set(cache_key, result, 15)  # short cache for network errors so recovery is fast
        return result

    if resp.status_code >= 400:
        result['error'] = f'HTTP {resp.status_code}'
        cache.set(cache_key, result, 15)
        return result

    try:
        data = resp.json() if resp.text else {}
    except ValueError:
        result['error'] = 'Invalid JSON from WAHA'
        cache.set(cache_key, result, 15)
        return result

    status = str((data or {}).get('status') or '').upper() or 'UNKNOWN'
    me = (data or {}).get('me') or {}
    phone = ''
    if isinstance(me, dict):
        me_id = str(me.get('id') or '').split('@')[0]
        if me_id:
            phone = '+' + me_id
        push_name = str(me.get('pushName') or '')
    else:
        push_name = ''

    result.update({
        'reachable': True,
        'status': status,
        'phone': phone,
        'push_name': push_name,
        'error': '',
    })
    cache.set(cache_key, result, 30)
    return result


def _log_instance_send(session, to_jid, ok, detail='', status_code=None):
    """Attribute a WAHA send to the instance that owns this session, if any.

    Sessions are mapped to instances on the WhatsApp instances page; a session
    no instance claims simply is not logged there, because that console lists
    per instance and an unclaimed row would have nowhere to appear.
    """
    from core.models import WhatsAppInstance
    from core.whatsapp_utils import log_send_attempt

    try:
        inst = WhatsAppInstance.objects.filter(waha_session=session).first()
        if inst is None:
            return
        log_send_attempt(inst.instance_name, _strip_jid(to_jid), ok,
                         detail=detail, status_code=status_code, channel='waha')
    except Exception:
        # Logging must never break the send it describes.
        logger.exception('Could not log WAHA send for session %s', session)


def send_waha_text(to, text, session=None):
    """Send a WAHA outbound text and log a WhatsAppMessage row.

    Reusable helper extracted from the `waha_send` view so background tasks
    (e.g. the address-verification drain worker) can send without going through
    HTTP. Returns ``(ok: bool, info: dict)``. ``info`` contains either
    ``message_obj``/``message_id``/``phone`` on success or ``error`` on failure.
    """
    # send_waha_text is the low-level primitive — gate is held by callers
    # (drain worker checks WAHA_VERIFY_USE_WAHA, legacy notifier checks
    # WAHA_ENABLED). We only require the API key to be configured here.
    if not (getattr(settings, 'WAHA_API_KEY', '') or ''):
        return False, {'error': 'WAHA_API_KEY not configured'}
    if not isinstance(to, str) or not isinstance(text, str):
        return False, {'error': 'to and text required'}

    session = wa_sessions.normalize(session)
    # Which of our numbers this went out from — a constant display string was
    # fine with one session, but is ambiguous once a second number exists.
    sender = wa_sessions.sender_number(session)

    if '@' not in to:
        digits = re.sub(r'\D', '', to)
        if not digits:
            return False, {'error': 'invalid phone'}
        to_jid = f'{digits}@c.us'
    else:
        if not _strip_jid(to):
            return False, {'error': 'invalid phone'}
        to_jid = to

    url = f"{getattr(settings, 'WAHA_BASE_URL', 'http://127.0.0.1:3000').rstrip('/')}/api/sendText"
    headers = {
        'X-Api-Key': getattr(settings, 'WAHA_API_KEY', '') or '',
        'Content-Type': 'application/json',
    }
    payload = {'chatId': to_jid, 'text': text, 'session': session}

    waha_status = 0
    waha_body = None
    err = None

    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=15)
        waha_status = resp.status_code
        try:
            waha_body = resp.json()
        except ValueError:
            waha_body = (resp.text or '')[:4000]
    except requests.exceptions.Timeout:
        err = 'timeout'
    except requests.exceptions.RequestException as e:
        err = f'network error: {e}'

    success = (200 <= waha_status < 300) and err is None

    # Mirror the attempt onto the sending number's log, so the WhatsApp
    # instances console shows WAHA traffic too. Deliberately does NOT feed the
    # Evolution failover health marker: a WAHA problem says nothing about
    # whether that number's Evolution socket is alive.
    _log_instance_send(session, to_jid, success,
                       detail=(err or f'HTTP {waha_status}') if not success else '',
                       status_code=waha_status)

    if not success:
        # Still log a failed-outbound row for audit, then return the error.
        WhatsAppMessage.objects.create(
            waha_message_id=f'out-fail-{uuid.uuid4().hex}',
            session=session,
            direction='outbound',
            from_number=sender,
            to_number=_strip_jid(to_jid),
            body=text,
            message_type='text',
            status='failed',
            error_kind='waha_send_error',
            processed_at=dj_timezone.now(),
            raw_payload=(waha_body if isinstance(waha_body, (dict, list)) else {'response': str(waha_body)[:4000], 'err': err}),
        )
        return False, {'error': err or f'HTTP {waha_status}', 'status': waha_status}

    wid = None
    if isinstance(waha_body, dict):
        wid = waha_body.get('id')
        if not wid:
            inner = waha_body.get('_data') or {}
            if isinstance(inner, dict):
                wid = inner.get('id')
    if not wid:
        wid = f'out-{uuid.uuid4().hex}'

    raw_payload_store = waha_body if isinstance(waha_body, (dict, list)) else {'response': str(waha_body)[:4000]}

    # Never persist a one-time code we just sent — the CRM chat panels let staff read
    # any conversation, including a password reset for someone else's account.
    from whatsapp.secrets import redact_payload, redact_text
    stored_text, _ = redact_text(text)
    raw_payload_store, _ = redact_payload(raw_payload_store, text)

    obj = WhatsAppMessage.objects.create(
        waha_message_id=str(wid),
        session=session,
        direction='outbound',
        from_number=sender,
        to_number=_strip_jid(to_jid),
        body=stored_text,
        message_type='text',
        status='processed',
        processed_at=dj_timezone.now(),
        raw_payload=raw_payload_store,
    )
    return True, {'message_obj': obj, 'message_id': str(wid), 'phone': _strip_jid(to_jid)}


def _raw_message_type(payload):
    data = payload.get('_data') or {}
    raw = data.get('type') if isinstance(data, dict) else None
    return str(raw or payload.get('type') or '').lower()


def _map_message_type(payload):
    raw = _raw_message_type(payload)
    if not raw:
        return 'text'
    return _WAHA_TYPE_MAP.get(raw, 'unknown')


# WhatsApp protocol chatter, not something a person sent: encryption-key
# notices, hosted-account banners, group membership changes. They carry no
# body, but they do carry a sender — so storing them invents an "unknown
# sender" in the CRM inbox for someone who never wrote to us. Merely asking
# WAHA whether a number exists is enough to produce one.
# `call_log` and `revoked` are deliberately NOT here: a missed call or a
# deleted message is a real person making contact, which is a lead signal.
_SYSTEM_EVENT_TYPES = frozenset({
    'e2e_notification', 'notification_template', 'gp2', 'protocol', 'ciphertext',
})


def is_system_event(payload):
    """True for WhatsApp system notifications that should never become a row."""
    return _raw_message_type(payload) in _SYSTEM_EVENT_TYPES


def resolve_jid_to_phone(jid, timeout=4, session=None):
    """Resolve a WhatsApp JID (phone or @lid) to a digits-only phone number.

    WAHA returns sender JIDs in two forms:
      - `97455555555@c.us`        → phone is the user part (split on '@').
      - `110698537439251@lid`     → user part is a privacy LID, not the phone.
                                    Resolve via /api/contacts.

    Returns the digits-only phone (e.g. '97455555555'), or empty string if
    we can't resolve. Cached 15 min keyed by (session, JID) so the webhook
    stays fast even under burst.

    The session matters: a LID is issued per linked device, so the same LID
    string can mean different people on our two numbers. Callers must pass the
    session the JID arrived on; None falls back to the default session.
    """
    if not jid:
        return ''
    jid = str(jid)
    # Already a phone-style JID — just strip the suffix.
    if '@lid' not in jid:
        return jid.split('@', 1)[0]

    from django.core.cache import cache
    sess = wa_sessions.normalize(session)
    cache_key = f'waha_lid_phone:{sess}:{jid}'
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    api_key = getattr(settings, 'WAHA_API_KEY', '') or ''
    if not api_key:
        return ''
    base = getattr(settings, 'WAHA_BASE_URL', 'http://127.0.0.1:3000').rstrip('/')
    try:
        resp = requests.get(
            f'{base}/api/contacts',
            params={'session': sess, 'contactId': jid},
            headers={'X-Api-Key': api_key, 'Accept': 'application/json'},
            timeout=timeout,
        )
        if resp.status_code >= 400:
            cache.set(cache_key, '', 60)  # short cache on failure
            return ''
        data = resp.json() if resp.text else {}
        phone = str((data or {}).get('number') or '').strip()
        # Sanity: phone should be all digits.
        if phone and phone.isdigit():
            cache.set(cache_key, phone, 60 * 15)  # 15 min
            return phone
    except (requests.exceptions.RequestException, ValueError):
        pass
    cache.set(cache_key, '', 60)
    return ''


def _extract_location(payload):
    """Pull (latitude, longitude) from a WAHA location-type payload.

    WAHA puts coordinates in different places depending on protocol version:
      - payload.location.{latitude,longitude}        (modern)
      - payload._data.location.{latitude,longitude}  (whatsapp-web.js native)
      - payload._data.lat/lng                        (legacy)
      - payload.{lat,lng} or payload.{latitude,longitude}
    Returns (lat, lng) as floats, or (None, None) if not parsable.
    """
    if not isinstance(payload, dict):
        return None, None

    candidates = []
    loc = payload.get('location')
    if isinstance(loc, dict):
        candidates.append(loc)
    inner = payload.get('_data') or {}
    if isinstance(inner, dict):
        if isinstance(inner.get('location'), dict):
            candidates.append(inner['location'])
        candidates.append(inner)
    candidates.append(payload)

    for c in candidates:
        if not isinstance(c, dict):
            continue
        lat = c.get('latitude') or c.get('lat')
        lng = c.get('longitude') or c.get('lng') or c.get('lon')
        try:
            if lat is not None and lng is not None:
                return float(lat), float(lng)
        except (TypeError, ValueError):
            continue
    return None, None


def _apply_inbound_location(msg):
    """Match a location-type WhatsAppMessage to an AddressVerificationJob and
    apply the coordinates to the order. Runs synchronously inside the webhook.

    Match rule:
      1. Find newest AddressVerificationJob with same phone + status='sent'.
      2. If sent_at is within WAHA_VERIFY_MATCH_WINDOW_HOURS → auto-apply.
      3. Otherwise → flip job to 'manual_review' so agent inbox surfaces it.
      4. If no matching sent job exists → no-op (logged).

    Apply means:
      - Write lat/lng to Order.latitude/longitude
      - Write same to DlAddressUpdate.dl_latitude/dl_longitude (creates if absent)
      - Set Order.coords_accuracy='exact', verification_status='address_verified'
      - Record an OrderStatusHistory row
      - Flip job to 'verified', stamp replied_at + completed_at, copy coords to
        applied_latitude/applied_longitude, link received_message.
    """
    from datetime import timedelta
    from decimal import Decimal
    from django.db import transaction

    from .models import AddressVerificationJob

    if not msg.latitude or not msg.longitude or not msg.from_number:
        return None

    window_hours = max(1, int(getattr(settings, 'WAHA_VERIFY_MATCH_WINDOW_HOURS', 24)))
    cutoff = dj_timezone.now() - timedelta(hours=window_hours)

    # Resolve sender JID → phone. WhatsApp may send the sender as `@lid`
    # (privacy identifier) rather than `@c.us` (phone). The raw `from` JID is
    # in raw_payload.payload.from; msg.from_number is the user-part only,
    # which equals the phone for c.us but is a meaningless LID otherwise.
    raw = msg.raw_payload if isinstance(msg.raw_payload, dict) else {}
    inner = raw.get('payload') if isinstance(raw, dict) else None
    raw_from_jid = (inner or {}).get('from') or msg.from_number
    resolved_phone = resolve_jid_to_phone(raw_from_jid, session=msg.session) or msg.from_number

    # Match against jobs by the resolved phone (digits only).
    job = (
        AddressVerificationJob.objects
        .select_related('order')
        .filter(phone=resolved_phone, status='sent')
        .order_by('-sent_at')
        .first()
    )
    if not job:
        logger.info('inbound location from %s but no matching sent job', msg.from_number)
        return None

    # Late → manual review.
    if not job.sent_at or job.sent_at < cutoff:
        job.status = 'manual_review'
        job.received_message = msg
        job.replied_at = dj_timezone.now()
        job.notes = (job.notes + f'\nLate location pin received {dj_timezone.now().isoformat()} — needs agent confirm').strip()
        job.save(update_fields=['status', 'received_message', 'replied_at', 'notes'])
        return job

    # Auto-apply.
    from orders.models import Order, OrderStatusHistory
    from delivery.models import DlAddressUpdate

    lat = Decimal(str(msg.latitude))
    lng = Decimal(str(msg.longitude))

    with transaction.atomic():
        order = job.order
        order.latitude = lat
        order.longitude = lng
        order.coords_accuracy = 'exact'
        order.verification_status = 'address_verified'
        order.save(update_fields=['latitude', 'longitude', 'coords_accuracy', 'verification_status'])

        addr, _ = DlAddressUpdate.objects.get_or_create(
            order=order,
            defaults={
                'full_name': order.customer_name or '',
                'dl_task_number': order.order_number,
                'mobile_no': order.customer_phone or '',
                'dl_zone': order.dl_zone,
                'dl_street': order.dl_street,
                'dl_building': order.dl_building,
                'dl_latitude': lat,
                'dl_longitude': lng,
                'dl_unit': '0',
                'area_name': order.customer_address or '',
            },
        )
        if addr.dl_latitude != lat or addr.dl_longitude != lng:
            addr.dl_latitude = lat
            addr.dl_longitude = lng
            addr.save(update_fields=['dl_latitude', 'dl_longitude'])

        OrderStatusHistory.objects.create(
            order=order,
            field_name='location_update',
            old_value='',
            new_value=f'{lat},{lng}',
            old_display='No pin',
            new_display=f'By Client · {lat}, {lng}',
            changed_by=None,
            notes='Shared WhatsApp location pin',
        )

        job.status = 'verified'
        job.received_message = msg
        job.replied_at = dj_timezone.now()
        job.completed_at = dj_timezone.now()
        job.applied_latitude = lat
        job.applied_longitude = lng
        job.save(update_fields=[
            'status', 'received_message', 'replied_at', 'completed_at',
            'applied_latitude', 'applied_longitude',
        ])
        msg.order = order
        msg.status = 'processed'
        msg.processed_at = dj_timezone.now()
        msg.save(update_fields=['order', 'status', 'processed_at'])

    logger.info(
        'auto-applied WhatsApp location to order %s from %s (job #%s)',
        order.order_number, msg.from_number, job.pk,
    )
    return job


def _serialize_message(obj):
    return {
        'id': obj.id,
        'waha_message_id': obj.waha_message_id,
        # Which of our numbers this belongs to — consumers handling more than
        # one need it to reply from the right sender.
        'session': obj.session,
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

        # Protocol chatter (encryption notices, group membership changes) has a
        # sender but no message — storing it puts a phantom unknown sender in
        # the CRM inbox.
        if is_system_event(payload):
            return JsonResponse({"ok": True, "ignored": "system"}, status=200)

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

        # Location pins: extract lat/lng from the payload (best-effort across
        # WAHA versions). Stored on the message; the post-save hook below
        # routes them to the matching AddressVerificationJob.
        lat = lng = None
        if message_type == 'location':
            lat, lng = _extract_location(payload)

        ts = payload.get("timestamp")
        if isinstance(ts, (int, float)):
            received_at = datetime.fromtimestamp(ts, tz=dt_timezone.utc)
        else:
            received_at = dj_timezone.now()

        # Validated, not trusted: the session name is written to the DB and
        # interpolated into WAHA URLs by downstream lookups.
        session = wa_sessions.normalize(data.get("session"))

        # update_or_create on (session, waha_message_id) makes webhook
        # re-deliveries idempotent. The session MUST be part of the lookup:
        # WAHA ids are unique per chat, not per session, so keying on the id
        # alone would let one number's message overwrite another's row.
        obj, created = WhatsAppMessage.objects.update_or_create(
            session=session,
            waha_message_id=str(waha_message_id),
            defaults={
                'direction': 'inbound',
                'from_number': from_number,
                'to_number': to_number,
                'body': body,
                'message_type': message_type,
                'media_url': media_url,
                'media_mime': media_mime,
                'latitude': lat,
                'longitude': lng,
                'status': 'received',
                'received_at': received_at,
                'raw_payload': data,
            },
        )

        # Media is archived into Django storage by the per-minute
        # archive_wa_media cron — WAHA purges its own copy within minutes.

        # Try to apply the location pin to a queued verification job. We swallow
        # exceptions because the webhook must still return 200 to WAHA — the
        # message has been saved either way, agents can re-process manually.
        applied_job_id = None
        if created and message_type == 'location' and lat is not None and lng is not None:
            try:
                job = _apply_inbound_location(obj)
                applied_job_id = job.pk if job else None
            except Exception:
                logger.exception('apply_inbound_location failed for msg %s', obj.id)

        return JsonResponse(
            {"ok": True, "id": obj.id, "created": created, "applied_job_id": applied_job_id},
            status=200,
        )
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
        limit = safe_int(request.GET.get('limit'), default=50, minimum=1, maximum=500)
    except (TypeError, ValueError):
        return JsonResponse({"error": "invalid limit"}, status=400)
    if limit < 1:
        limit = 1
    if limit > 200:
        limit = 200

    mark_raw = (request.GET.get('mark_picked_up', '') or '').strip().lower()
    mark_picked_up = mark_raw in {'1', 'true', 'yes', 'y'}

    # This is a CLAIM queue — picking a row up hides it from every other
    # consumer. So it defaults to a single session rather than the whole table:
    # a client written for one number must never silently start draining
    # another number's inbox when a new session is added. `session=all` is the
    # explicit opt-in for a cross-session drain.
    session_raw = (request.GET.get('session', '') or '').strip().lower()
    drain_all = session_raw == 'all'
    session = None if drain_all else wa_sessions.from_request(request)

    with transaction.atomic():
        base_qs = WhatsAppMessage.objects.filter(status=status)
        if not drain_all:
            base_qs = base_qs.filter(session=session)
        qs = base_qs.order_by('received_at')[:limit]

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

    session = wa_sessions.normalize(data.get('session'))

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
        from_number=wa_sessions.sender_number(session),
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
