# core/templatetags/custom_filters.py
from django import template
import hmac
import hashlib
import os
import re
import logging

register = template.Library()
logger = logging.getLogger(__name__)


@register.filter
def short_timesince(value):
    """Compact timesince: abbreviates unit names but keeps the same structure.

    '5 hours, 12 minutes' -> '5 hr, 12 min'
    '2 days, 3 hours'     -> '2 d, 3 hr'
    """
    if not value:
        return ''
    from django.utils.timesince import timesince
    raw = timesince(value)
    abbrev = [
        ('minutes', 'min'), ('minute', 'min'),
        ('hours', 'hr'), ('hour', 'hr'),
        ('days', 'd'), ('day', 'd'),
        ('weeks', 'wk'), ('week', 'wk'),
        ('months', 'mo'), ('month', 'mo'),
        ('years', 'yr'), ('year', 'yr'),
    ]
    for long, short in abbrev:
        raw = re.sub(r'\b' + long + r'\b', short, raw)
    return raw


@register.filter
def mul(value, arg):
    """Multiply the value by the argument."""
    try:
        return float(value) * float(arg)
    except (ValueError, TypeError):
        return 0

@register.filter
def multiply(value, arg):
    """Multiply the value by the argument (alias for mul)."""
    return mul(value, arg)

@register.filter
def div(value, arg):
    """Divide the value by the argument."""
    try:
        if float(arg) == 0:
            return 0
        return float(value) / float(arg)
    except (ValueError, TypeError):
        return 0

@register.filter
def get_item(dictionary, key):
    """Look up a value in a dict by key (templates can't do dict[key] syntax)."""
    if dictionary is None:
        return None
    try:
        return dictionary.get(key)
    except AttributeError:
        return None

@register.filter
def floatformat_custom(value, arg):
    """Custom float format that handles None/invalid."""
    try:
        return format(float(value), f'.{arg}f')
    except (ValueError, TypeError):
        return value

@register.filter
def safe_image_url(image_field, default='/media/business/product_images/product_image_default.jpg'):
    """
    Safely get image URL with fallback to default.
    Returns the image URL if valid, otherwise returns default.
    """
    if not image_field:
        return default
    try:
        url = image_field.url
        # If the URL looks valid, return it
        if url and url.startswith('/media/'):
            return url
        return default
    except (ValueError, AttributeError):
        return default

@register.filter
def safe_brand_logo_url(image_field):
    """
    Safely get brand logo URL with fallback to default brand logo.
    """
    return safe_image_url(image_field, default='/media/business/product_images/brand_logo_default.jpg')


@register.filter
def whatsapp_number(value):
    """
    Clean phone number for wa.me links.
    Strips +, spaces, dashes. Prepends 974 for local Qatar numbers (8 digits).
    Usage: {{ order.customer_whatsapp|whatsapp_number }}
    """
    if not value:
        return ''
    # Remove +, spaces, dashes, parentheses
    cleaned = re.sub(r'[\s+\-()]+', '', str(value))
    # If 8 digits (Qatar local number), prepend 974
    if len(cleaned) == 8 and cleaned.isdigit():
        cleaned = '974' + cleaned
    return cleaned


@register.filter(is_safe=True)
def get_zone_from_address(address):
    """
    Extract zone name from address string.
    """
    if not address:
        return "No Zone"

    try:
        address = str(address).strip()

        # Look for "Zone XX" or "zone XX"
        zone_match = re.search(r'[Zz]one\s+(\d+)', address)
        if zone_match:
            return f"Zone {zone_match.group(1)}"

        # Extract first part before comma
        address_clean = re.sub(r'^(zone|street|building|bldg|st|bl)\s+\d+,?\s*', '', address, flags=re.IGNORECASE)
        parts = address_clean.split(',')
        if parts:
            zone_part = parts[0].strip()
            if zone_part and not zone_part.isdigit() and len(zone_part) > 2:
                return zone_part

        return address[:30] + ('...' if len(address) > 30 else '')
    except Exception as e:
        logger.debug(f"Could not extract zone from address: {e}")
        return str(address)[:30]


def _get_time_slot():
    """Get current 4-hour time slot as integer (changes every 4 hours)."""
    import time
    return int(time.time()) // (4 * 3600)


def generate_order_verify_key(order_number, customer_phone, time_slot=None):
    """Generate a short HMAC key for order verification links. Valid for 4 hours."""
    from django.conf import settings
    if time_slot is None:
        time_slot = _get_time_slot()
    phone_clean = re.sub(r'[\s+\-()]+', '', str(customer_phone))
    msg = f"{order_number}:{phone_clean}:{time_slot}".encode()
    key = settings.SECRET_KEY.encode()
    return hmac.new(key, msg, hashlib.sha256).hexdigest()[:12]


def verify_order_key(order_number, customer_phone, provided_key):
    """Verify a key, checking current and previous 4-hour window."""
    current_slot = _get_time_slot()
    for slot in (current_slot, current_slot - 1):
        expected = generate_order_verify_key(order_number, customer_phone, time_slot=slot)
        if hmac.compare_digest(provided_key, expected):
            return True
    return False


@register.filter
def verify_key(order):
    """
    Generate a short verification key for order WhatsApp links.
    Usage: {{ order|verify_key }}
    """
    if not order or not hasattr(order, 'order_number') or not hasattr(order, 'customer_phone'):
        return ''
    return generate_order_verify_key(order.order_number, order.customer_phone)


# Module-level zone cache to avoid N+1 queries (zones rarely change)
_zone_cache = {}
_zone_cache_loaded = False


def _get_zone_map():
    """Load all zones into a dict once, reuse across template renders."""
    global _zone_cache, _zone_cache_loaded
    if not _zone_cache_loaded:
        from delivery.models import ZoneName
        _zone_cache = {
            z.zone_number: z.zone_name
            for z in ZoneName.objects.all()
            if z.zone_name
        }
        _zone_cache_loaded = True
    return _zone_cache


@register.simple_tag
def get_zone_display(order):
    """
    Get zone display for order - tries zone number first, then address.
    Usage: {% get_zone_display order %}
    """
    try:
        # Try zone number first
        if hasattr(order, 'dl_zone') and order.dl_zone:
            try:
                zone_number = int(order.dl_zone)
                zone_map = _get_zone_map()
                zone_name = zone_map.get(zone_number)
                if zone_name:
                    return zone_name
                return f"Zone {zone_number}"
            except (ValueError, Exception):
                pass

        # Fallback to customer address
        if hasattr(order, 'customer_address') and order.customer_address:
            return get_zone_from_address(order.customer_address)

        return "No Zone"
    except Exception as e:
        logger.debug(f"Error getting zone display: {e}")
        return "No Zone"


@register.filter
def to_json(value):
    """Serialise a value to JSON for an HTML *attribute*.

    Deliberately returns a plain str, not a SafeString, so Django autoescapes
    the quotes for the attribute context. The browser decodes them again when
    the value is read back via ``element.dataset.*``, so JSON.parse gets valid
    JSON — no single-to-double quote substitution needed on the JS side.

    For a value going inside a <script> block use core.json_utils.safe_json in
    the view instead; that escapes < > & rather than the attribute delimiters.
    """
    import json as _json
    from django.core.serializers.json import DjangoJSONEncoder
    try:
        return _json.dumps(value, cls=DjangoJSONEncoder)
    except (TypeError, ValueError):
        return 'null'
