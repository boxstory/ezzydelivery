# Purpose: Strip one-time codes out of WhatsApp message text before it is persisted, so our own auth OTPs never sit readable in WhatsAppMessage.
# Used by: whatsapp/management/commands/backfill_waha.py (upsert_message), whatsapp/waha_views.py (outbound log), whatsapp/management/commands/redact_wa_secrets.py.
# Notes: The WAHA container is linked to the company number, so backfill ingests our own `fromMe` auth messages verbatim — body AND raw_payload. Redaction is deliberately broad: a false positive costs a staff member seeing "[code hidden]" in a chat, a false negative is an account takeover.

import re

PLACEHOLDER = '[code hidden]'

# Wording from core/whatsapp_utils.py message_templates plus generic variants.
# Deliberately NOT included: a bare "one-time" (matched "a one-time payment of QAR 900")
# and "2fa" (matched "2Fa" inside a base64 media payload). Both destroyed real content.
_SECRET_CONTEXT = re.compile(
    r'(verification code|password reset|reset code|one[- ]time (?:password|code|pin)|'
    r'\bOTP\b|security code|login code|confirmation code)',
    re.IGNORECASE,
)

# Our own auth templates (core/whatsapp_utils.py) — short, and every digit run in them
# is the code, so they can be redacted wholesale.
_OWN_TEMPLATE = re.compile(r'EZZY[^\n]{0,40}(verification|password reset)', re.IGNORECASE)

# 4-8 digit runs, optionally wrapped in WhatsApp bold markers.
_CODE = re.compile(r'(?<!\d)\*?(\d{4,8})\*?(?!\d)')

# How far after the context phrase a code may sit, for third-party messages.
_WINDOW = 80
# Bodies longer than this are not auth messages; ours are a few hundred chars.
_MAX_BODY = 2000


def _is_opaque_blob(text):
    """base64 / encoded media bodies: no spaces early on. Substituting inside one
    corrupts the payload, and it can never be an auth message."""
    head = text[:200]
    return len(head) >= 200 and ' ' not in head and '\n' not in head


def looks_like_secret(text):
    """True when this message body is one of our own code-bearing auth messages, or a
    third-party one-time code forwarded to the company number."""
    if not text or len(text) > _MAX_BODY or _is_opaque_blob(text):
        return False
    return bool(_SECRET_CONTEXT.search(text) and _CODE.search(text))


def redact_text(text):
    """(clean_text, changed) — replaces the code, keeps the surrounding wording so a
    staff member can still see what kind of message it was."""
    if not looks_like_secret(text):
        return text, False

    if _OWN_TEMPLATE.search(text):
        cleaned = _CODE.sub(PLACEHOLDER, text)
        return cleaned, cleaned != text

    # Third-party message: only touch digits close to the phrase, so reference
    # numbers and amounts elsewhere in the text survive.
    cleaned, last = [], 0
    for hit in _SECRET_CONTEXT.finditer(text):
        start, end = hit.start(), min(len(text), hit.end() + _WINDOW)
        if start < last:
            continue
        cleaned.append(text[last:hit.end()])
        cleaned.append(_CODE.sub(PLACEHOLDER, text[hit.end():end]))
        last = end
    cleaned.append(text[last:])
    result = ''.join(cleaned)
    return result, result != text


def redact_payload(payload, original_text=''):
    """Same treatment for the raw WAHA payload, which repeats the body verbatim.

    Walks strings recursively because the code appears in several keys depending on
    the WAHA version (`body`, `_data.body`, `caption`, …). Only runs when the message
    is code-bearing, so ordinary chats are stored untouched.
    """
    if not looks_like_secret(original_text or _first_text(payload)):
        return payload, False

    changed = [False]

    def walk(node):
        if isinstance(node, str):
            cleaned = _CODE.sub(PLACEHOLDER, node) if _CODE.search(node) else node
            if cleaned != node:
                changed[0] = True
            return cleaned
        if isinstance(node, dict):
            return {k: walk(v) for k, v in node.items()}
        if isinstance(node, list):
            return [walk(v) for v in node]
        return node

    return walk(payload), changed[0]


def _first_text(payload):
    """Best-effort body from a raw payload, for callers that only have the payload."""
    if isinstance(payload, dict):
        for key in ('body', 'text', 'caption'):
            value = payload.get(key)
            if isinstance(value, str) and value:
                return value
        inner = payload.get('_data')
        if isinstance(inner, dict):
            return _first_text(inner)
    return ''
