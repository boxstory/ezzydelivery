"""
Purpose: One-device-per-driver enforcement — resolve the device a driver just signed in
         from, revoke the previous one, and issue/verify the WhatsApp confirmation code.
Used by: fleet/device_signals.py, core/middleware.DriverDeviceMiddleware,
         fleet/views_device.py, workforce device-approval views.
Notes:   Session keys are the only device handle the web gives us — no browser exposes
         IMEI or a serial — so a revoked device is flagged inside its own session data
         rather than deleted, which is what lets the old phone explain itself.
"""
import logging
from importlib import import_module

from django.conf import settings
from django.utils import timezone

from core.models import WhatsAppVerification
from core.whatsapp_utils import create_verification
from fleet.models import Driver, DriverDevice

logger = logging.getLogger(__name__)

# Cookie holding the device token. Long-lived and HttpOnly: it is not a
# credential on its own (the session cookie still authenticates), it only says
# "this browser has been confirmed before", so it must not be readable by JS.
DEVICE_COOKIE = 'ezzy_device'
DEVICE_COOKIE_AGE = 60 * 60 * 24 * 365 * 2  # 2 years

# Session keys used to carry state between the login signal, the middleware and
# the verify view.
SESSION_REVOKED = '_driver_device_revoked'
SESSION_PENDING_DEVICE = '_driver_device_pending'
SESSION_SET_TOKEN = '_driver_device_set_token'

OTP_RESEND_COOLDOWN = 60      # seconds between sends
OTP_MAX_SENDS = 5             # per device, before ops has to step in


def enforcement_enabled():
    """Ops kill switch for the whole one-device rule."""
    return getattr(settings, 'DRIVER_DEVICE_ENFORCEMENT', True)


def is_driver(user):
    try:
        profile = getattr(user, 'profile', None)
        return bool(profile and profile.is_driver)
    except Exception:
        return False


def is_enrolled_driver(user):
    """True only for drivers who can actually work.

    Applicants are deliberately outside the rule. `Profile.is_driver` is set the
    moment someone submits the join-driver application, long before anyone has
    looked at it, so keying off that flag would put an OTP between an applicant
    and their own application form — and burn a WhatsApp send on people who may
    never be approved.

    What the rule protects is tasks and COD cash, and neither exists until the
    driver is approved. So the gate starts at the first login after approval.
    """
    if not is_driver(user):
        return False
    try:
        return Driver.objects.filter(user=user, driver_status='approved').exists()
    except Exception:
        return False


def driver_phone_candidates(user):
    """Every number we could reach this driver on, best first, de-duplicated.

    A driver record can carry a landline-style contact number in one field and a
    WhatsApp number in the other, and nothing guarantees the preferred one has a
    WhatsApp account at all. Sending to the first and giving up strands the
    driver with no way to confirm a device, so the sender walks this list.
    """
    driver = Driver.objects.filter(user=user).order_by('-driver_id').first()
    candidates = []
    if driver:
        candidates += [driver.driver_whatsapp, driver.driver_phone]
    profile = getattr(user, 'profile', None)
    if profile:
        candidates += [profile.whatsapp, profile.phone]

    seen, ordered = set(), []
    for value in candidates:
        value = str(value).strip() if value else ''
        if value and value not in seen:
            seen.add(value)
            ordered.append(value)
    return ordered


def driver_phone(user):
    """Best WhatsApp number for a driver, preferring the fleet record."""
    candidates = driver_phone_candidates(user)
    return candidates[0] if candidates else ''


def mask_phone(phone):
    """Show only the last two digits — enough to recognise, not enough to leak."""
    digits = ''.join(ch for ch in str(phone) if ch.isdigit())
    if len(digits) < 4:
        return '•••'
    return f"{'•' * (len(digits) - 2)}{digits[-2:]}"


def describe_device(request):
    """Rough handset label for the ops list. Never trusted for anything."""
    ua = request.META.get('HTTP_USER_AGENT', '')[:255]
    low = ua.lower()
    if 'iphone' in low:
        platform = 'iPhone'
    elif 'ipad' in low:
        platform = 'iPad'
    elif 'android' in low:
        platform = 'Android'
    elif 'windows' in low:
        platform = 'Windows'
    elif 'mac os' in low:
        platform = 'Mac'
    else:
        platform = 'Unknown'

    if 'edg/' in low:
        browser = 'Edge'
    elif 'chrome' in low and 'chromium' not in low:
        browser = 'Chrome'
    elif 'firefox' in low:
        browser = 'Firefox'
    elif 'safari' in low:
        browser = 'Safari'
    else:
        browser = 'Browser'
    return ua, f'{platform} · {browser}'


def _flag_session_revoked(session_key, reason):
    """Write the revocation into the other device's own session.

    Deleting the session row would work too, but the old phone would then land
    on a blank login page with no idea why — and that is an ops call at 6am.
    Flagging costs the same and lets the device explain itself. The session is
    inert either way: the middleware gates every request.
    """
    if not session_key:
        return
    try:
        engine = import_module(settings.SESSION_ENGINE)
        store = engine.SessionStore(session_key)
        if not store.exists(session_key):
            return
        store[SESSION_REVOKED] = reason
        store.save()
    except Exception:
        logger.exception('Could not flag driver session %s as revoked', session_key)


def revoke_other_devices(user, keep_id=None, reason=DriverDevice.REVOKED_NEW_DEVICE):
    """Retire every live device for this driver except `keep_id`."""
    others = DriverDevice.objects.filter(
        user=user, status__in=[DriverDevice.STATUS_PENDING, DriverDevice.STATUS_ACTIVE]
    )
    if keep_id:
        others = others.exclude(pk=keep_id)

    for device in others:
        _flag_session_revoked(device.session_key, reason)
        device.status = DriverDevice.STATUS_REVOKED
        device.revoked_at = timezone.now()
        device.revoked_reason = reason
        device.save(update_fields=['status', 'revoked_at', 'revoked_reason', 'last_seen_at'])
    return others


def bind_device(request, user):
    """Resolve the device this login came from. Returns the DriverDevice.

    A device that has been verified before is trusted again without a code, even
    if it was revoked in the meantime — that is a driver going back to their own
    phone, not a stranger. A token we have never activated gets the OTP gate.
    """
    # This login supersedes any earlier revocation of this session. Django's
    # login() cycles the session key but carries the data over, so the flag
    # would otherwise survive and sign the driver straight back out.
    request.session.pop(SESSION_REVOKED, None)

    if not request.session.session_key:
        request.session.save()
    session_key = request.session.session_key

    token = request.COOKIES.get(DEVICE_COOKIE) or ''
    known = None
    if token:
        known = DriverDevice.objects.filter(
            user=user, device_token=token, activated_at__isnull=False
        ).first()

    ua, label = describe_device(request)
    ip = request.META.get('REMOTE_ADDR')

    if known:
        revoke_other_devices(user, keep_id=known.pk)
        known.status = DriverDevice.STATUS_ACTIVE
        known.session_key = session_key
        known.revoked_at = None
        known.revoked_reason = ''
        known.user_agent = ua
        known.ip_address = ip
        known.label = label
        known.save()
        request.session.pop(SESSION_PENDING_DEVICE, None)
        return known

    revoke_other_devices(user)
    from core.whatsapp_utils import generate_secure_token
    device = DriverDevice.objects.create(
        user=user,
        device_token=generate_secure_token(),
        session_key=session_key,
        status=DriverDevice.STATUS_PENDING,
        user_agent=ua,
        ip_address=ip,
        label=label,
    )
    request.session[SESSION_PENDING_DEVICE] = device.pk
    request.session[SESSION_SET_TOKEN] = device.device_token
    logger.info('Driver %s signed in from an unrecognised device (%s)', user.pk, label)
    return device


def send_device_code(device):
    """Send (or resend) the confirmation code. Returns (ok, message)."""
    now = timezone.now()
    if device.otp_sent_at and (now - device.otp_sent_at).total_seconds() < OTP_RESEND_COOLDOWN:
        wait = OTP_RESEND_COOLDOWN - int((now - device.otp_sent_at).total_seconds())
        return False, f'Please wait {wait} seconds before asking for another code.'

    if device.otp_send_count >= OTP_MAX_SENDS:
        return False, 'Too many codes requested. Please contact operations to release this device.'

    candidates = driver_phone_candidates(device.user)
    if not candidates:
        return False, 'No WhatsApp number on file. Please contact operations.'

    # Try each number we hold until one actually takes the message. The first
    # choice is often a contact number with no WhatsApp account behind it, and a
    # code sent there is silently lost — the driver sees "sent" and waits forever.
    last_error = None
    for phone in candidates:
        result = create_verification(
            user=device.user, phone_number=phone, verification_type='device_verify'
        )
        if not result.get('success'):
            last_error = result.get('error')
            continue

        send_result = result.get('send_result') or {}
        device.otp_sent_at = now
        device.otp_send_count += 1
        device.save(update_fields=['otp_sent_at', 'otp_send_count', 'last_seen_at'])

        if send_result.get('success', True):
            return True, f'Code sent to {mask_phone(phone)} on WhatsApp.'

        # The row exists, so ops can still read the code out if needed.
        last_error = send_result.get('error')
        logger.error('Device code for driver %s not delivered to %s: %s',
                     device.user_id, mask_phone(phone), send_result)

    logger.error('Device code for driver %s failed on every number (%d tried): %s',
                 device.user_id, len(candidates), last_error)
    return False, ('We could not deliver a code to any number on your record. '
                   'Please ask operations to unlock this device.')


def verify_device_code(device, code):
    """Check a submitted code. Returns (ok, message)."""
    code = (code or '').strip()
    if not code.isdigit() or len(code) != 6:
        return False, 'Enter the 6-digit code from WhatsApp.'

    verification = WhatsAppVerification.objects.filter(
        user=device.user, verification_type='device_verify', is_verified=False
    ).order_by('-created_at').first()

    if not verification:
        return False, 'No code was requested. Tap "Send code" to get one.'
    if verification.is_expired():
        return False, 'That code has expired. Tap "Send code" to get a new one.'
    if not verification.can_attempt():
        return False, 'Too many wrong attempts. Tap "Send code" to get a new one.'

    verification.attempts += 1
    if verification.verification_code != code:
        verification.save(update_fields=['attempts'])
        left = max(0, verification.max_attempts - verification.attempts)
        return False, f'Wrong code. {left} attempt(s) left.'

    verification.is_verified = True
    verification.verified_at = timezone.now()
    verification.save(update_fields=['attempts', 'is_verified', 'verified_at'])

    activate_device(device)
    return True, 'Device confirmed.'


def activate_device(device, approved_by=None):
    """Mark a device usable — by code, or by an ops release."""
    device.status = DriverDevice.STATUS_ACTIVE
    device.activated_at = device.activated_at or timezone.now()
    device.revoked_at = None
    device.revoked_reason = ''
    if approved_by:
        device.approved_by = approved_by
    device.save()
    revoke_other_devices(device.user, keep_id=device.pk)
    return device
