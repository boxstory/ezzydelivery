# core/templatetags/custom_filters.py
from django import template
import os
import re
import logging

register = template.Library()
logger = logging.getLogger(__name__)

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
                from delivery.models import ZoneName
                zone = ZoneName.objects.filter(zone_number=zone_number).first()
                if zone and zone.zone_name:
                    return zone.zone_name
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
