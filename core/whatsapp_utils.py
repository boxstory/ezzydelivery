"""
WhatsApp Verification Utilities
Handles sending verification codes via n8n webhook to WhatsApp
"""
import logging
import random
import string
import secrets
import hashlib
import hmac
import requests
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from datetime import timedelta
from .models import WhatsAppVerification

logger = logging.getLogger(__name__)


def generate_verification_code(length=6):
    """Generate a cryptographically secure numeric verification code.

    Uses `secrets` (not `random`) because this code gates password resets —
    a predictable Mersenne-Twister sequence would let an attacker predict a
    victim's OTP from their own observed codes.
    """
    return ''.join(secrets.choice(string.digits) for _ in range(length))


def generate_secure_token():
    """Generate a cryptographically secure token for webhook authentication"""
    return secrets.token_urlsafe(32)


def generate_webhook_signature(payload, secret_key):
    """
    Generate HMAC signature for webhook payload

    Args:
        payload: Dict payload to sign
        secret_key: Secret key from settings

    Returns:
        str: Hex digest of HMAC signature
    """
    import json
    message = json.dumps(payload, sort_keys=True).encode()
    signature = hmac.new(
        secret_key.encode(),
        message,
        hashlib.sha256
    ).hexdigest()
    return signature


def validate_input_phone(phone_number):
    """
    Validate and sanitize phone number input

    Args:
        phone_number: Phone number string

    Returns:
        tuple: (is_valid, sanitized_number, error_message)
    """
    import re

    # Remove any whitespace
    phone = str(phone_number).strip()

    # Remove non-digit characters
    phone = re.sub(r'\D', '', phone)

    # Check if it's a valid Qatar number (starting with 974 or just the local number)
    if len(phone) < 8:
        return False, None, "Phone number too short"

    if len(phone) > 15:
        return False, None, "Phone number too long"

    # Ensure it starts with country code or add it
    if not phone.startswith('974'):
        if len(phone) == 8:
            phone = '974' + phone
        else:
            return False, None, "Invalid Qatar phone number format"

    return True, phone, None


def send_whatsapp_verification(phone_number, verification_code, verification_type):
    """
    Send verification code via n8n webhook to WhatsApp with security

    Args:
        phone_number: Phone number to send to (format: 97466451589)
        verification_code: The 6-digit code
        verification_type: Type of verification (password_reset, phone_add, etc.)

    Returns:
        dict: Response from the messaging channel with success status and code
    """
    # Get n8n webhook URL from settings
    n8n_webhook_url = getattr(settings, 'N8N_WHATSAPP_WEBHOOK_URL', None)
    n8n_webhook_secret = getattr(settings, 'N8N_WEBHOOK_SECRET_KEY', None)

    # Validate HTTPS for production when using the webhook channel
    if n8n_webhook_url and not settings.DEBUG and not n8n_webhook_url.startswith('https://'):
        return {
            'success': False,
            'error': 'Webhook URL must use HTTPS in production',
            'code': None
        }

    # Prepare message based on verification type
    message_templates = {
        'password_reset': f"""
🔐 *EZZY Delivery - Password Reset*

Your password reset verification code is:

*{verification_code}*

This code will expire in 10 minutes.

If you didn't request this, please ignore this message.
        """,
        'phone_add': f"""
📱 *EZZY Delivery - Phone Verification*

Your phone number verification code is:

*{verification_code}*

This code will expire in 10 minutes.
        """,
        'phone_update': f"""
📱 *EZZY Delivery - Phone Update*

Your phone update verification code is:

*{verification_code}*

This code will expire in 10 minutes.
        """,
        'account_verify': f"""
✅ *EZZY Delivery - Account Verification*

Your account verification code is:

*{verification_code}*

This code will expire in 10 minutes.
        """,
        'inquiry_thanks': f"""
✅ *Thank You for Your 3PL Inquiry!*

We've received your inquiry and appreciate your interest in EZZY Delivery.

Our team will review your business requirements and contact you within 24 hours with a customized quote.

In the meantime, feel free to reach out to us if you have any questions.

Best regards,
*EZZY Delivery Team* 🚚
        """
    }

    message = message_templates.get(verification_type, f"Your EZZY verification code is: {verification_code}")

    # If the n8n webhook is not configured, fall back to the Evolution API
    # (the channel already used for other transactional WhatsApp messages).
    if not n8n_webhook_url:
        # Failover: a verification code is useless if it does not arrive, so try
        # another connected number rather than dropping it on a dead session.
        api_result = send_whatsapp_message_failover(phone_number, message.strip())
        if not api_result.get('success'):
            logger.error('WhatsApp %s code to %s not delivered: %s',
                         verification_type, phone_number, api_result)
        return {
            'success': api_result.get('success', False),
            'code': verification_code,
            'message': 'Verification code sent via Evolution API' if api_result.get('success') else None,
            'error': None if api_result.get('success') else api_result.get('error', 'Failed to send via Evolution API')
        }

    # Prepare webhook payload
    payload = {
        'phone': phone_number,
        'message': message.strip(),
        'code': verification_code,
        'type': verification_type,
        'timestamp': timezone.now().isoformat()
    }

    # Prepare headers with security
    headers = {
        'Content-Type': 'application/json',
        'User-Agent': 'EZZY-Delivery/1.0'
    }

    # Add HMAC signature if secret key is configured
    if n8n_webhook_secret:
        signature = generate_webhook_signature(payload, n8n_webhook_secret)
        headers['X-Webhook-Signature'] = signature

    try:
        # Send to n8n webhook with security headers
        response = requests.post(
            n8n_webhook_url,
            json=payload,
            headers=headers,
            timeout=10,
            verify=True  # Verify SSL certificates
        )

        if response.status_code == 200:
            return {
                'success': True,
                'code': verification_code,
                'message': 'Verification code sent successfully'
            }
        else:
            return {
                'success': False,
                'error': f'Webhook returned status {response.status_code}',
                'code': verification_code  # Return code for testing purposes
            }

    except requests.exceptions.RequestException as e:
        return {
            'success': False,
            'error': f'Failed to send WhatsApp message: {str(e)}',
            'code': verification_code  # Return code for testing purposes
        }


def send_password_reset_completion_notification(user, phone_number):
    """
    Send notification via n8n webhook when password reset is completed

    Args:
        user: User object whose password was reset
        phone_number: Phone number to notify

    Returns:
        dict: Response with success status
    """
    n8n_webhook_url = getattr(settings, 'N8N_PASSWORD_RESET_COMPLETE_WEBHOOK_URL', None)
    n8n_webhook_secret = getattr(settings, 'N8N_WEBHOOK_SECRET_KEY', None)

    # Validate HTTPS for production when using the webhook channel
    if n8n_webhook_url and not settings.DEBUG and not n8n_webhook_url.startswith('https://'):
        return {'success': False, 'error': 'Webhook must use HTTPS in production'}

    message = f"""
✅ *EZZY Delivery - Password Reset Successful*

Your password has been successfully reset.

Username: {user.username}
Time: {timezone.now().strftime('%Y-%m-%d %H:%M:%S')}

If you did not perform this action, please contact support immediately.
    """

    # If the dedicated webhook is not configured, fall back to the Evolution API.
    if not n8n_webhook_url:
        return send_whatsapp_message_api(phone_number, message.strip())

    payload = {
        'phone': phone_number,
        'message': message.strip(),
        'type': 'password_reset_complete',
        'user_id': user.id,
        'username': user.username,
        'timestamp': timezone.now().isoformat()
    }

    headers = {
        'Content-Type': 'application/json',
        'User-Agent': 'EZZY-Delivery/1.0'
    }

    if n8n_webhook_secret:
        signature = generate_webhook_signature(payload, n8n_webhook_secret)
        headers['X-Webhook-Signature'] = signature

    try:
        response = requests.post(
            n8n_webhook_url,
            json=payload,
            headers=headers,
            timeout=10,
            verify=True
        )

        return {
            'success': response.status_code == 200,
            'status_code': response.status_code
        }

    except requests.exceptions.RequestException as e:
        return {
            'success': False,
            'error': f'Failed to send notification: {str(e)}'
        }


def create_verification(user=None, phone_number=None, verification_type='password_reset'):
    """
    Create a new WhatsApp verification record and send the code

    Args:
        user: User object (optional, can be None for password reset)
        phone_number: Phone number to verify
        verification_type: Type of verification

    Returns:
        dict: Response with success status, verification object, and send result
    """
    # Validate and sanitize phone number
    is_valid, sanitized_phone, error_msg = validate_input_phone(phone_number)

    if not is_valid:
        return {
            'success': False,
            'error': error_msg,
            'verification': None,
            'send_result': None
        }

    # Generate verification code
    code = generate_verification_code()

    # Set expiration (10 minutes from now)
    expires_at = timezone.now() + timedelta(minutes=10)

    # Create verification record with sanitized phone
    verification = WhatsAppVerification.objects.create(
        user=user,
        phone_number=sanitized_phone,
        verification_code=code,
        verification_type=verification_type,
        expires_at=expires_at
    )

    # Send via WhatsApp
    send_result = send_whatsapp_verification(sanitized_phone, code, verification_type)

    return {
        'success': True,
        'verification': verification,
        'send_result': send_result
    }


def send_location_verification_whatsapp(order, verification_token, phone_number):
    """
    Send location verification link via n8n webhook to WhatsApp

    Args:
        order: Order object
        verification_token: Unique token for verification link
        phone_number: Phone number to send to

    Returns:
        dict: Response with success status
    """
    from django.conf import settings as django_settings

    n8n_webhook_url = getattr(settings, 'N8N_WHATSAPP_WEBHOOK_URL', None)
    n8n_webhook_secret = getattr(settings, 'N8N_WEBHOOK_SECRET_KEY', None)

    if not n8n_webhook_url:
        return {
            'success': False,
            'error': 'N8N webhook URL not configured'
        }

    # Validate HTTPS for production
    if not settings.DEBUG and not n8n_webhook_url.startswith('https://'):
        return {
            'success': False,
            'error': 'Webhook URL must use HTTPS in production'
        }

    # Build short verification URL: /v/<phone>/<token>/
    base_url = getattr(django_settings, 'BASE_URL', 'https://your-domain.com')
    verification_url = f"{base_url}/v/{phone_number}/{verification_token}/"

    # Build self-service update URL (order-specific with secure key, valid 4hrs)
    from urllib.parse import quote
    from core.templatetags.custom_filters import generate_order_verify_key
    verify_key = generate_order_verify_key(order.order_number, order.customer_phone)
    update_location_url = f"{base_url}/orders/verify/?order={quote(order.order_number)}&key={verify_key}"

    message = f"""📍 *EZZY Delivery - Address Verification Required*

Hello {order.customer_name},

Your order *{order.order_number}* is ready for delivery!

*Delivery Details:*
📦 Items: {order.order_items.count()} item(s)
💰 COD: {order.cod_amount} QR
📍 Address: {order.customer_address}

*🔴 ACTION REQUIRED:*
Please verify your delivery location by clicking the link below:

{verification_url}

This will open a map where you can:
✅ Confirm your exact location
✅ Update address details if needed
✅ Add delivery instructions

⏰ This link will expire in 7 days.

📌 You can also update your location anytime at:
{update_location_url}

If you have any questions, please contact us.

Thank you for choosing EZZY Delivery! 🚚"""

    payload = {
        'phone': phone_number,
        'message': message.strip(),
        'type': 'location_verification',
        'order_id': order.id,
        'order_number': order.order_number,
        'verification_token': verification_token,
        'verification_url': verification_url,
        'timestamp': timezone.now().isoformat()
    }

    headers = {
        'Content-Type': 'application/json',
        'User-Agent': 'EZZY-Delivery/1.0'
    }

    if n8n_webhook_secret:
        signature = generate_webhook_signature(payload, n8n_webhook_secret)
        headers['X-Webhook-Signature'] = signature

    try:
        response = requests.post(
            n8n_webhook_url,
            json=payload,
            headers=headers,
            timeout=10,
            verify=True
        )

        return {
            'success': response.status_code == 200,
            'status_code': response.status_code,
            'verification_url': verification_url
        }

    except requests.exceptions.RequestException as e:
        return {
            'success': False,
            'error': f'Failed to send WhatsApp message: {str(e)}'
        }


def get_route_instance(section):
    """Return the active WhatsAppInstance a platform section must send from, or None.

    Sections are defined in core.models.WhatsAppSenderRoute.SECTION_CHOICES and
    configured on the workforce Auto Triggers page. A disabled route or an
    inactive instance means "no restriction" (caller falls back to default).
    """
    from core.models import WhatsAppSenderRoute
    route = (WhatsAppSenderRoute.objects
             .select_related('instance')
             .filter(section=section, is_enabled=True).first())
    inst = route.instance if route else None
    return inst if (inst and inst.is_active) else None


def get_route(section):
    """The enabled WhatsAppSenderRoute row for a section, or None."""
    from core.models import WhatsAppSenderRoute
    return (WhatsAppSenderRoute.objects
            .select_related('instance')
            .filter(section=section, is_enabled=True).first())


def get_instance_for_session(session):
    """The active WhatsAppInstance whose WAHA session this is, or None.

    The reverse of ``whatsapp.sessions.for_instance`` — used when the number is
    picked directly (a staff member choosing which line a conversation runs on)
    rather than derived from a section route, so the composer can still name the
    sender and an Evolution fallback still lands on the same number.
    """
    from core.models import WhatsAppInstance
    if not session:
        return None
    return WhatsAppInstance.objects.filter(waha_session=session, is_active=True).first()


def resolve_send_target(section, session=''):
    """Which instance and channel a send will actually use → (instance, channel).

    ``session`` is an explicit staff override of the section's number. Because a
    session name only means anything to WAHA, choosing one also forces the WAHA
    channel — otherwise the message would leave on the section's Evolution
    instance and arrive from a different number than the one that was picked.
    """
    from core.models import WhatsAppSenderRoute

    route = get_route(section)
    inst = route.instance if (route and route.instance and route.instance.is_active) else None
    channel = (route.channel if route else '') or WhatsAppSenderRoute.CHANNEL_EVOLUTION

    if session:
        override = get_instance_for_session(session)
        if override is not None:
            inst = override
        channel = WhatsAppSenderRoute.CHANNEL_WAHA
    return inst, channel


def send_routed_message(section, phone_number, message, session=''):
    """Send one message through a section's configured number AND channel.

    The Auto Triggers page owns both halves of that choice, and they are
    genuinely independent: the same number is reachable through Evolution (by
    ``instance_name``) or through WAHA (by ``waha_session``), so business leads
    can stay on Evolution while driver leads run on WAHA.

    ``session`` overrides the number for this one send — the caller has already
    validated it (see workforce.views.whatsapp_send_routed); an invalid name
    must never reach here, because it would silently fall back to the default
    session and send from the wrong line.

    Returns the same ``{'success': bool, ...}`` shape as
    ``send_whatsapp_message_api`` whichever channel carries it.
    """
    from core.models import WhatsAppSenderRoute

    inst, channel = resolve_send_target(section, session)

    if channel != WhatsAppSenderRoute.CHANNEL_WAHA:
        return send_whatsapp_message_api(phone_number, message, instance_obj=inst)

    try:
        from whatsapp import sessions as wa_sessions
        from whatsapp.waha_views import send_waha_text

        ok, info = send_waha_text(
            str(phone_number), message,
            session=session or wa_sessions.for_instance(inst))
        if ok:
            return {'success': True, 'channel': 'waha', 'message_id': info.get('message_id', '')}
        return {'success': False, 'channel': 'waha',
                'error': info.get('error') or 'WAHA send failed'}
    except Exception as exc:
        logger.exception('WAHA send failed for section %s — falling back to Evolution', section)
        result = send_whatsapp_message_api(phone_number, message, instance_obj=inst)
        result.setdefault('waha_error', str(exc))
        return result


# A dead Evolution session keeps reporting connectionState "open" long after its
# WhatsApp socket is gone, so health can only be learned from real send results.
# Short TTL so an instance recovers on its own once it starts working again.
INSTANCE_DOWN_TTL = 300


def _health_cache():
    """The cache instance health is shared through.

    Must be a cross-process cache: the default cache is LocMemCache, which is
    private to one gunicorn worker, so a dead session learned by one worker
    would stay invisible to the others. The 'ratelimit' cache is the configured
    database-backed one every worker can see.
    """
    from django.core.cache import caches
    try:
        return caches['ratelimit']
    except Exception:
        from django.core.cache import cache
        return cache


def _instance_down_key(instance_name):
    return f'wa:instance_down:{instance_name}'


def _looks_like_dead_socket(status_code, body):
    """True when a failed send means "this session has no live WhatsApp socket".

    Evolution answers 500 {"response":{"message":"Connection Closed"}} on sends
    and 428 Precondition Required on reads once the socket dies. A 400 for a bad
    recipient must NOT count — that is the number's fault, not the sender's.
    """
    if status_code in (428, 500):
        return True
    return 'connection closed' in str(body).lower()


def _failure_reason(body):
    """The human-readable bit of an Evolution error, for the ops console."""
    if isinstance(body, dict):
        nested = body.get('response')
        if isinstance(nested, dict) and nested.get('message'):
            return str(nested['message'])
        payload = (body.get('output') or {}).get('payload') or {}
        if payload.get('message'):
            return str(payload['message'])
        if body.get('error'):
            return str(body['error'])
    return str(body)[:200]


# Rows kept per instance. The console shows 5; the rest are headroom for
# working out when a number started failing. Busy numbers run a few hundred
# messages a day, so this is a few hours of history — enough to answer "since
# when", without letting the table grow without bound.
SEND_LOG_KEEP_PER_INSTANCE = 200


def mask_phone(phone_number):
    """Recipient with the middle digits hidden, for the ops log."""
    digits = ''.join(c for c in str(phone_number or '') if c.isdigit())
    if len(digits) <= 6:
        return digits
    return f'{digits[:4]}****{digits[-3:]}'


def log_send_attempt(instance_name, phone_number, ok, detail='', status_code=None, channel='waha'):
    """Record a send made outside the Evolution client (currently WAHA).

    The console lists attempts per number, and most traffic leaves over WAHA —
    logging only the Evolution path made healthy numbers look idle.
    """
    _record_send_log(instance_name, phone_number, ok,
                     {'error': detail} if detail else {}, status_code, channel)


def _record_send_log(instance_name, phone_number, ok, body, status_code=None, channel='evolution'):
    """Append this send attempt to the instance's log, then trim the tail.

    Never stores the message: these rows include OTP and password-reset sends,
    and the console that reads them is a staff page.
    """
    from core.models import WhatsAppSendLog

    if not instance_name:
        return
    try:
        WhatsAppSendLog.objects.create(
            instance_name=instance_name,
            channel=channel,
            phone_number=mask_phone(phone_number),
            success=bool(ok),
            status_code=status_code if isinstance(status_code, int) else None,
            detail='' if ok else _failure_reason(body)[:255],
        )
        keep = list(WhatsAppSendLog.objects.filter(instance_name=instance_name)
                    .values_list('id', flat=True)[:SEND_LOG_KEEP_PER_INSTANCE])
        if len(keep) >= SEND_LOG_KEEP_PER_INSTANCE:
            (WhatsAppSendLog.objects
             .filter(instance_name=instance_name).exclude(id__in=keep).delete())
    except Exception:
        # A logging failure must never take down the send it is describing.
        logger.exception('Could not write WhatsApp send log for %s', instance_name)


def _record_instance_health(instance_name, ok, body, status_code=None):
    """Remember whether this instance's socket is usable, for failover.

    Stores why and when as well as the bare fact, because the WhatsApp instances
    console shows this to staff — "Connected" from Evolution plus "last send
    failed: Connection Closed" from here is what makes a zombie session obvious.
    """
    if not instance_name:
        return
    cache = _health_cache()
    key = _instance_down_key(instance_name)
    if ok:
        cache.delete(key)
    elif _looks_like_dead_socket(status_code, body):
        reason = _failure_reason(body)
        cache.set(key, {
            'at': timezone.now().isoformat(),
            'reason': reason,
            'status_code': status_code,
        }, INSTANCE_DOWN_TTL)
        logger.error('WhatsApp instance %s looks disconnected: %s', instance_name, body)


def instance_down_info(instance_name):
    """Details of this instance's last failed send, or None when it looks fine.

    Returns a dict with 'at' (ISO timestamp), 'reason' and 'status_code'.
    """
    if not instance_name:
        return None
    info = _health_cache().get(_instance_down_key(instance_name))
    return info if isinstance(info, dict) else ({'at': '', 'reason': '', 'status_code': None} if info else None)


def instance_is_down(instance_name):
    """True when a recent send proved this instance's socket is dead."""
    return instance_down_info(instance_name) is not None


def get_auth_instance():
    """The instance auth codes (OTP / password reset) should send from, or None.

    Order of preference:
      1. The configured default (``settings.EVOLUTION_INSTANCE``) when it is not
         known to be disconnected — auth codes should come from the main number
         so recipients recognise the sender.
      2. Any other active instance that is not known to be disconnected, so a
         password reset still lands while the main number is being re-linked.
    """
    from core.models import WhatsAppInstance

    default_name = (getattr(settings, 'EVOLUTION_INSTANCE', '') or '').strip()
    if default_name and not instance_is_down(default_name):
        return WhatsAppInstance.objects.filter(
            instance_name=default_name, is_active=True).first()

    for inst in WhatsAppInstance.objects.filter(is_active=True).order_by('-is_default', 'id'):
        if not instance_is_down(inst.instance_name):
            return inst
    return None


def whatsapp_auth_channel_down():
    """True when no active instance can currently deliver an auth code.

    Checked before a password-reset lookup so an outage is reported to everyone
    identically — the answer does not depend on the phone number typed in, so it
    cannot be used to probe which numbers have accounts.
    """
    from core.models import WhatsAppInstance

    names = list(WhatsAppInstance.objects.filter(
        is_active=True).values_list('instance_name', flat=True))
    if not names:
        return True
    return all(instance_is_down(n) for n in names)


def send_whatsapp_message_failover(phone_number, message):
    """Send a message, retrying on another number if the first session is dead.

    Only used for auth codes, where delivery matters more than which number the
    message arrives from. Ordinary notifications keep their routed sender.
    """
    from core.models import WhatsAppInstance

    preferred = get_auth_instance()
    result = send_whatsapp_message_api(phone_number, message, instance_obj=preferred)
    if result.get('success'):
        return result

    tried = {result.get('instance')}
    for inst in WhatsAppInstance.objects.filter(is_active=True).order_by('-is_default', 'id'):
        if inst.instance_name in tried or instance_is_down(inst.instance_name):
            continue
        logger.warning('WhatsApp auth send failing over from %s to %s',
                       result.get('instance'), inst.instance_name)
        result = send_whatsapp_message_api(phone_number, message, instance_obj=inst)
        tried.add(inst.instance_name)
        if result.get('success'):
            return result
    return result


def send_whatsapp_message_api(phone_number, message, instance_obj=None):
    """
    Send WhatsApp message via Evolution API

    Args:
        phone_number: Phone number with country code (e.g., 97466451589)
        message: Message text to send
        instance_obj: optional WhatsAppInstance whose instance_name overrides
            settings.EVOLUTION_INSTANCE (lets a trigger pick a specific number).

    Returns:
        dict: Response with success status
    """
    api_url = getattr(settings, 'EVOLUTION_URL', None)
    api_key = getattr(settings, 'EVOLUTION_API_KEY', None)
    instance = getattr(settings, 'EVOLUTION_INSTANCE', None)
    if instance_obj is not None and (getattr(instance_obj, 'instance_name', '') or '').strip():
        instance = instance_obj.instance_name.strip()

    if not api_url or not api_key or not instance:
        return {
            'success': False,
            'error': 'Evolution API not configured'
        }

    # Clean phone number
    phone = str(phone_number).strip()
    phone = phone.replace('+', '').replace(' ', '').replace('-', '')

    # Evolution API endpoint
    endpoint = f"{api_url}/message/sendText/{instance}"

    payload = {
        'number': phone,
        'text': message.strip()
    }

    headers = {
        'Content-Type': 'application/json',
        'apikey': api_key
    }

    try:
        response = requests.post(
            endpoint,
            json=payload,
            headers=headers,
            timeout=10,
            verify=True
        )

        ok = response.status_code in [200, 201]
        body = response.json() if response.text else {}
        _record_instance_health(instance, ok, body, response.status_code)
        _record_send_log(instance, phone, ok, body, response.status_code)

        return {
            'success': ok,
            'status_code': response.status_code,
            'instance': instance,
            'response': body
        }

    except requests.exceptions.RequestException as e:
        _record_instance_health(instance, False, None)
        _record_send_log(instance, phone, False, {'error': str(e)})
        return {
            'success': False,
            'instance': instance,
            'error': f'Failed to send WhatsApp message: {str(e)}'
        }


def trigger_enabled(trigger_key):
    """False when staff switched this automatic message off on Auto Triggers.

    An unregistered key defaults to on, so a send is never silently lost just
    because its AutoTriggerConfig row has not been created yet.
    """
    from core.models import AutoTriggerConfig
    try:
        return AutoTriggerConfig.is_trigger_enabled(trigger_key)
    except Exception:
        logger.exception('Trigger lookup failed for %s — sending anyway', trigger_key)
        return True


def send_inquiry_thank_you_message(phone_number, business_name):
    """
    Send thank you message to customer after 3PL inquiry submission via WhatsApp API

    Switched off with the ``wa_quote_thank_you`` trigger; sends from the CRM &
    Leads number so the prospect's reply lands in the sales inbox.

    Args:
        phone_number: Customer phone number
        business_name: Customer business name

    Returns:
        dict: Response with success status
    """
    if not trigger_enabled('wa_quote_thank_you'):
        return {'success': False, 'disabled': True, 'error': 'Trigger is switched off'}

    message = f"""✅ *Thank You for Your 3PL Inquiry!*

Hi {business_name},

We've received your inquiry and appreciate your interest in EZZY Delivery.

Our team will review your business requirements and contact you within 24 hours with a customized quote.

In the meantime, feel free to reach out to us if you have any questions.

Best regards,
*EZZY Delivery Team* 🚚
"""
    return send_routed_message('crm_leads', phone_number, message)


FLEET_WHATSAPP_NUMBER = '97466124545'


def get_fleet_instance():
    """Return the WhatsApp instance driver-applicant messages send from, or None.

    Order of preference:
      1. The ``driver_onboarding`` sender route, when staff configured one on
         the Auto Triggers page — that page is the one place this is set.
      2. The fleet admin number (97466124545), the historical default.
      3. The orders/tasks route, so a send still goes out from a real number.
    """
    from core.models import WhatsAppInstance
    routed = get_route_instance('driver_onboarding')
    if routed:
        return routed
    inst = WhatsAppInstance.objects.filter(
        phone_number=FLEET_WHATSAPP_NUMBER, is_active=True).first()
    return inst or get_route_instance('orders_tasks')


def send_driver_application_thank_you(phone_number, first_name=''):
    """Thank-you + we'll-reach-back message to a driver applicant.

    Sent from the driver-onboarding number so the applicant's replies reach the
    team that reviews the application. Two independent switches: the
    ``wa_driver_application_thanks`` trigger (Auto Triggers page) and the
    message body itself (AI Config → Messages).

    Args:
        phone_number: Applicant WhatsApp/phone number (local or with 974)
        first_name: Applicant first name for the greeting (optional)

    Returns:
        dict: Response with success status
    """
    from core.message_templates import DRIVER_APPLICATION_THANKS, render_template

    if not trigger_enabled('wa_driver_application_thanks'):
        return {'success': False, 'disabled': True, 'error': 'Trigger is switched off'}

    is_valid, phone, error = validate_input_phone(phone_number)
    if not is_valid:
        return {'success': False, 'error': error or 'Invalid phone number'}

    message = render_template(
        DRIVER_APPLICATION_THANKS,
        first_name=(first_name or '').strip() or 'there',
    )
    if message is None:
        return {'success': False, 'disabled': True, 'error': 'Template is switched off'}

    # Routed: the driver_onboarding route decides both the number and whether
    # this goes out over WAHA or Evolution. get_fleet_instance() still supplies
    # the historical fleet-number fallback when no route is configured.
    if get_route('driver_onboarding'):
        return send_routed_message('driver_onboarding', phone, message)
    return send_whatsapp_message_api(phone, message, instance_obj=get_fleet_instance())


def send_admin_inquiry_notification(inquiry):
    """
    Send notification to admin about new 3PL inquiry submission via WhatsApp API

    Switched off with the ``wa_quote_admin_alert`` trigger; sends from the CRM &
    Leads number so the alert sits in the same thread the sales desk works in.

    Args:
        inquiry: PricingEnquiry object

    Returns:
        dict: Response with success status
    """
    if not trigger_enabled('wa_quote_admin_alert'):
        return {'success': False, 'disabled': True, 'error': 'Trigger is switched off'}

    inquiry_url = f"https://ezzydelivery.qa/3pl/inquiry/{inquiry.id}/preview/"

    message = f"""📩 *NEW 3PL INQUIRY RECEIVED*

*Company:* {inquiry.business_name}
*Contact:* {inquiry.full_name}
*Phone:* {inquiry.business_contact_number}
*Email:* {inquiry.email or '—'}

*Product Category:* {inquiry.product_category}
*Order Volume (Last Month):* {inquiry.avarage_number_of_order_done_last_month}
*Preferred Start:* {inquiry.preferred_start_date}

*Services Required:*
• COD: {'Yes' if inquiry.is_required_COD_service else 'No'}
• Fulfillment (Outside QA): {'Yes' if inquiry.is_required_fulfillment_service_for_operate_from_outside_qatar else 'No'}
• Return Logistics: {'Yes' if inquiry.is_return_logistics_required else 'No'}

*Submitted:* {timezone.now().strftime('%Y-%m-%d %H:%M:%S')}
*Inquiry ID:* {inquiry.id}

👉 View inquiry details:
{inquiry_url}
"""

    return send_routed_message('crm_leads', '97466451589', message)


def verify_code(phone_number, code, verification_type):
    """
    Verify a code against stored verification records

    Args:
        phone_number: Phone number to verify
        code: The code to check
        verification_type: Type of verification

    Returns:
        dict: Result with success status and verification object
    """
    try:
        # Get most recent non-verified verification for this phone and type
        verification = WhatsAppVerification.objects.filter(
            phone_number=phone_number,
            verification_type=verification_type,
            is_verified=False
        ).order_by('-created_at').first()

        if not verification:
            return {
                'success': False,
                'error': 'No verification code found',
                'verification': None
            }

        # Consume an attempt atomically: re-fetch the row under a lock so that
        # concurrent verifications serialize on it. Without the lock, N parallel
        # guesses all read the same `attempts` value and the lost-update leaves
        # the counter far below N, bypassing the max_attempts brute-force cap.
        with transaction.atomic():
            verification = (
                WhatsAppVerification.objects
                .select_for_update()
                .get(pk=verification.pk)
            )

            # Check if expired
            if verification.is_expired():
                return {
                    'success': False,
                    'error': 'Verification code expired',
                    'verification': verification
                }

            # Check if too many attempts
            if not verification.can_attempt():
                return {
                    'success': False,
                    'error': 'Too many verification attempts',
                    'verification': verification
                }

            # Increment attempts
            verification.attempts += 1
            verification.save()

            # Check code (constant-time to avoid a timing side-channel on the OTP)
            if hmac.compare_digest(str(verification.verification_code), str(code)):
                verification.is_verified = True
                verification.verified_at = timezone.now()
                verification.save()

                return {
                    'success': True,
                    'message': 'Code verified successfully',
                    'verification': verification
                }
            else:
                return {
                    'success': False,
                    'error': 'Invalid verification code',
                    'verification': verification
                }

    except Exception as e:
        return {
            'success': False,
            'error': f'Verification error: {str(e)}',
            'verification': None
        }
