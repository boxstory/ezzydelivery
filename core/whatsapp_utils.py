"""
WhatsApp Verification Utilities
Handles sending verification codes via n8n webhook to WhatsApp
"""
import random
import string
import secrets
import hashlib
import hmac
import requests
from django.conf import settings
from django.utils import timezone
from datetime import timedelta
from .models import WhatsAppVerification


def generate_verification_code(length=6):
    """Generate a random numeric verification code"""
    return ''.join(random.choices(string.digits, k=length))


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
        dict: Response from n8n webhook with success status and code
    """
    # Get n8n webhook URL from settings
    n8n_webhook_url = getattr(settings, 'N8N_WHATSAPP_WEBHOOK_URL', None)
    n8n_webhook_secret = getattr(settings, 'N8N_WEBHOOK_SECRET_KEY', None)

    if not n8n_webhook_url:
        return {
            'success': False,
            'error': 'N8N webhook URL not configured',
            'code': None
        }

    # Validate HTTPS for production
    if not settings.DEBUG and not n8n_webhook_url.startswith('https://'):
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
        """
    }

    message = message_templates.get(verification_type, f"Your EZZY verification code is: {verification_code}")

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

    if not n8n_webhook_url:
        # Silently fail if webhook not configured
        return {'success': False, 'error': 'Webhook not configured'}

    # Validate HTTPS for production
    if not settings.DEBUG and not n8n_webhook_url.startswith('https://'):
        return {'success': False, 'error': 'Webhook must use HTTPS in production'}

    message = f"""
✅ *EZZY Delivery - Password Reset Successful*

Your password has been successfully reset.

Username: {user.username}
Time: {timezone.now().strftime('%Y-%m-%d %H:%M:%S')}

If you did not perform this action, please contact support immediately.
    """

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

    # Build verification URL
    from django.urls import reverse
    verification_path = reverse('orders:verify_location', kwargs={'token': verification_token})

    # Get base URL from settings or request
    base_url = getattr(django_settings, 'BASE_URL', 'https://your-domain.com')
    verification_url = f"{base_url}{verification_path}"

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

        # Check code
        if verification.verification_code == code:
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
