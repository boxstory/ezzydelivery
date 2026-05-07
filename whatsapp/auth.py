"""
Auth helpers for the WAHA bridge.

- _bearer_ok: constant-time check of the Authorization: Bearer <token>
  header against settings.WAHA_AGENT_TOKEN. Used by /messages/, /send/.
- _verify_waha_hmac: HMAC-SHA512 over the raw request body, header
  X-Webhook-Hmac. Used by the inbound webhook. Returns (ok, reason).
"""
import hmac
import hashlib

from django.conf import settings


def _bearer_ok(request):
    expected = getattr(settings, 'WAHA_AGENT_TOKEN', '') or ''
    if not expected:
        # Empty token in settings = misconfigured; refuse rather than allow-all.
        return False
    auth = request.META.get('HTTP_AUTHORIZATION', '') or ''
    if not auth.lower().startswith('bearer '):
        return False
    presented = auth.split(' ', 1)[1].strip()
    try:
        return hmac.compare_digest(presented.encode('utf-8'), expected.encode('utf-8'))
    except Exception:
        return False


def _verify_waha_hmac(request, raw_body):
    """
    Verify the X-Webhook-Hmac header on an inbound WAHA webhook.

    raw_body: bytes — the exact request body. Caller must read it once
    and pass it through; do not re-read request.body after parsing JSON.

    Returns (ok: bool, reason: str). reason is empty when ok=True.
    """
    secret = getattr(settings, 'WAHA_WEBHOOK_HMAC_SECRET', '') or ''
    presented = request.META.get('HTTP_X_WEBHOOK_HMAC', '') or ''

    # In DEBUG without a secret configured, allow through to ease local dev.
    if not secret:
        if getattr(settings, 'DEBUG', False):
            return True, ''
        return False, 'WAHA_WEBHOOK_HMAC_SECRET not configured'

    if not presented:
        return False, 'missing X-Webhook-Hmac header'

    try:
        digest = hmac.new(
            secret.encode('utf-8'),
            raw_body or b'',
            hashlib.sha512,
        ).hexdigest()
    except Exception as e:
        return False, f'hmac compute error: {e}'

    if hmac.compare_digest(digest, presented.strip()):
        return True, ''
    return False, 'hmac mismatch'
