"""
Custom template filters for orders app
"""
import logging
import re
from django import template
from django.utils.safestring import mark_safe

register = template.Library()
logger = logging.getLogger(__name__)


@register.filter(is_safe=True)
def get_zone_from_address(address):
    """
    Extract zone name from address string.

    Looks for patterns like:
    - "Zone 44"
    - "zone 44"
    - "Al Dafna"
    - Any text before comma, street, or building

    Args:
        address: Address string

    Returns:
        str: Extracted zone name or "No Zone"
    """
    if not address:
        return "No Zone"

    try:
        address = str(address).strip()

        # Pattern 1: Look for "Zone XX" or "zone XX"
        zone_match = re.search(r'[Zz]one\s+(\d+)', address)
        if zone_match:
            return f"Zone {zone_match.group(1)}"

        # Pattern 2: Extract first part before comma, street, or building
        # Remove common prefixes
        address_clean = re.sub(r'^(zone|street|building|bldg|st|bl)\s+\d+,?\s*', '', address, flags=re.IGNORECASE)

        # Split by comma and take first part
        parts = address_clean.split(',')
        if parts:
            zone_part = parts[0].strip()

            # If it's not just numbers or too short, return it
            if zone_part and not zone_part.isdigit() and len(zone_part) > 2:
                return zone_part

        # Fallback: return first 30 characters of address
        return address[:30] + ('...' if len(address) > 30 else '')

    except Exception as e:
        logger.debug(f"Could not extract zone from address: {e}")
        return str(address)[:30]


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

    Usage in template:
        {% get_zone_display order %}

    Args:
        order: Order object

    Returns:
        str: Zone name or address-based location
    """
    try:
        # Try to get zone number first
        if hasattr(order, 'dl_zone') and order.dl_zone:
            try:
                zone_number = int(order.dl_zone)
                zone_map = _get_zone_map()
                zone_name = zone_map.get(zone_number)
                if zone_name:
                    return zone_name
                else:
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
