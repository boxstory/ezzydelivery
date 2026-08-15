"""
Purpose: Password reset flow backed by WhatsApp OTP verification.
Used by: core/urls.py (password_reset_request/verify/confirm), login "Forgot Password?" link.
Notes: OTP is sent via core.whatsapp_utils (Evolution API fallback). Request/verify are
        rate limited and the request step is enumeration-safe (same response whether or not
        an account exists).
"""
import logging

from django.shortcuts import render, redirect
from django.contrib.auth import get_user_model
from django.contrib import messages
from django.contrib.auth.hashers import make_password
from django.core.cache import cache
from django.views.decorators.http import require_http_methods
from .whatsapp_utils import (
    create_verification,
    verify_code,
    send_password_reset_completion_notification,
    validate_input_phone,
    whatsapp_auth_channel_down
)
from .models import Profile, WhatsAppVerification

logger = logging.getLogger(__name__)

User = get_user_model()

# Rate limit configuration
SEND_COOLDOWN_SECONDS = 60          # min seconds between OTP sends per phone
SEND_MAX_PER_WINDOW = 5             # max OTP sends per phone within the window
SEND_WINDOW_SECONDS = 60 * 60       # 1 hour
IP_MAX_PER_WINDOW = 20              # max reset requests per IP within the window


def _client_ip(request):
    """Best-effort client IP, honouring the proxy header used in production."""
    forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
    if forwarded:
        return forwarded.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR', 'unknown')


def _send_throttled(phone):
    """
    Enforce per-phone OTP send limits.

    Returns (allowed, error_message). error_message is None when allowed.
    """
    cooldown_key = f'pwreset:cooldown:{phone}'
    if cache.get(cooldown_key):
        return False, 'Please wait a moment before requesting another code.'

    window_key = f'pwreset:count:{phone}'
    count = cache.get(window_key, 0)
    if count >= SEND_MAX_PER_WINDOW:
        return False, 'Too many reset attempts. Please try again later.'

    cache.set(cooldown_key, 1, SEND_COOLDOWN_SECONDS)
    cache.set(window_key, count + 1, SEND_WINDOW_SECONDS)
    return True, None


@require_http_methods(["GET", "POST"])
def password_reset_request(request):
    """
    Password reset request via WhatsApp OTP.

    Enumeration-safe: regardless of whether an account exists, the user is shown the
    same confirmation and forwarded to the verification step.
    """
    if request.method == 'POST':
        reset_method = request.POST.get('reset_method')  # 'whatsapp' (email tab disabled)
        identifier = request.POST.get('identifier')  # phone number

        if reset_method == 'email':
            # Email reset is disabled until SMTP is configured.
            messages.error(request, 'Email reset is currently unavailable. Please use WhatsApp.')
            return render(request, 'accounts/password_reset_request.html')

        # Default / WhatsApp path
        # Per-IP throttle to deter enumeration scanning.
        ip_key = f'pwreset:ip:{_client_ip(request)}'
        ip_count = cache.get(ip_key, 0)
        if ip_count >= IP_MAX_PER_WINDOW:
            messages.error(request, 'Too many requests. Please try again later.')
            return render(request, 'accounts/password_reset_request.html')
        cache.set(ip_key, ip_count + 1, SEND_WINDOW_SECONDS)

        # Validate and sanitize phone number input
        is_valid, sanitized_phone, error_msg = validate_input_phone(identifier)
        if not is_valid:
            messages.error(request, f'Invalid phone number: {error_msg}')
            return render(request, 'accounts/password_reset_request.html')

        # A total WhatsApp outage is reported before the account lookup, so the
        # answer is identical for every number and still tells the truth instead
        # of promising a code that cannot be sent.
        if whatsapp_auth_channel_down():
            logger.error('Password reset unavailable: no connected WhatsApp instance')
            messages.error(
                request,
                'WhatsApp verification is temporarily unavailable. '
                'Please contact support to reset your password.'
            )
            return render(request, 'accounts/password_reset_request.html')

        # Generic confirmation shown in all cases (no account enumeration).
        generic_msg = 'If an account with that number exists, a verification code has been sent to WhatsApp.'

        profile = Profile.objects.filter(whatsapp=sanitized_phone).select_related('user').first()

        if profile and profile.user:
            allowed, throttle_err = _send_throttled(sanitized_phone)
            if not allowed:
                messages.error(request, throttle_err)
                return render(request, 'accounts/password_reset_request.html')

            try:
                result = create_verification(
                    user=profile.user,
                    phone_number=sanitized_phone,
                    verification_type='password_reset'
                )
                if not (result.get('success') and result.get('send_result', {}).get('success')):
                    # Detail stays server-side; the user still sees generic_msg so
                    # a failed send cannot be used to confirm the account exists.
                    logger.error('Password reset code to %s not delivered: %s',
                                 sanitized_phone, result)
            except Exception:
                # Never leak internal errors / account existence.
                logger.exception('Password reset send failed for %s', sanitized_phone)

        # Always behave identically: stash phone and move to verify step.
        request.session['reset_phone'] = sanitized_phone
        messages.success(request, generic_msg)
        return redirect('core:password_reset_verify')

    return render(request, 'accounts/password_reset_request.html')


@require_http_methods(["GET", "POST"])
def password_reset_verify(request):
    """
    Verify WhatsApp code for password reset. Supports re-sending the code.
    """
    phone_number = request.session.get('reset_phone')

    if not phone_number:
        messages.error(request, 'Session expired. Please start over.')
        return redirect('core:password_reset_request')

    if request.method == 'POST':
        # Resend handling
        if request.POST.get('action') == 'resend':
            allowed, throttle_err = _send_throttled(phone_number)
            if not allowed:
                messages.error(request, throttle_err)
                return render(request, 'accounts/password_reset_verify.html', {'phone_number': phone_number})

            profile = Profile.objects.filter(whatsapp=phone_number).select_related('user').first()
            if profile and profile.user:
                try:
                    create_verification(
                        user=profile.user,
                        phone_number=phone_number,
                        verification_type='password_reset'
                    )
                except Exception:
                    pass
            messages.success(request, 'If an account with that number exists, a new code has been sent.')
            return render(request, 'accounts/password_reset_verify.html', {'phone_number': phone_number})

        verification_code = (request.POST.get('verification_code') or '').strip()

        result = verify_code(phone_number, verification_code, 'password_reset')

        if result['success']:
            request.session['verified_reset'] = result['verification'].id
            messages.success(request, 'Code verified! Please enter your new password.')
            return redirect('core:password_reset_confirm')
        else:
            messages.error(request, result.get('error', 'Invalid verification code'))

    context = {'phone_number': phone_number}
    return render(request, 'accounts/password_reset_verify.html', context)


@require_http_methods(["GET", "POST"])
def password_reset_confirm(request):
    """
    Confirm new password after WhatsApp verification.
    """
    verification_id = request.session.get('verified_reset')

    if not verification_id:
        messages.error(request, 'Please verify your code first.')
        return redirect('core:password_reset_request')

    if request.method == 'POST':
        password1 = request.POST.get('password1')
        password2 = request.POST.get('password2')

        if password1 != password2:
            messages.error(request, 'Passwords do not match')
            return render(request, 'accounts/password_reset_confirm.html')

        if not password1 or len(password1) < 8:
            messages.error(request, 'Password must be at least 8 characters')
            return render(request, 'accounts/password_reset_confirm.html')

        try:
            verification = WhatsAppVerification.objects.get(id=verification_id, is_verified=True)
        except WhatsAppVerification.DoesNotExist:
            messages.error(request, 'Verification is no longer valid. Please start over.')
            request.session.pop('reset_phone', None)
            request.session.pop('verified_reset', None)
            return redirect('core:password_reset_request')

        if not verification.user:
            messages.error(request, 'User not found')
            return render(request, 'accounts/password_reset_confirm.html')

        try:
            # Update password
            verification.user.password = make_password(password1)
            verification.user.save(update_fields=['password'])

            # Invalidate this OTP and any other outstanding reset OTPs for the phone
            # so a verified code cannot be reused.
            WhatsAppVerification.objects.filter(
                phone_number=verification.phone_number,
                verification_type='password_reset'
            ).delete()

            # Best-effort completion notification (never blocks the reset).
            try:
                send_password_reset_completion_notification(
                    user=verification.user,
                    phone_number=verification.phone_number
                )
            except Exception:
                pass

            request.session.pop('reset_phone', None)
            request.session.pop('verified_reset', None)

            messages.success(request, 'Password reset successfully! You can now login.')
            return redirect('account_login')

        except Exception as e:
            messages.error(request, f'Error resetting password: {str(e)}')

    return render(request, 'accounts/password_reset_confirm.html')
