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


# ---------------------------------------------------------------------------
# Orders manifest (client console) — row state resolution
# ---------------------------------------------------------------------------

# Lane = the colour of the 3px rail on the left edge of a manifest row. Only rows
# that need the merchant's attention get one; settled rows stay unmarked so the
# exceptions are the only thing carrying colour.
_LANE_BY_STATE = {
    'failed': 'alert',
    'review': 'warn',
    'ready': 'live',
    'assigned': 'live',
    'transit': 'live',
    'pending': 'live',
    'delivered': 'settled',
    'cancelled': 'settled',
}


@register.simple_tag
def manifest_state(order):
    """
    Resolve one manifest row's display state.

    Returns a dict of {state, label, lane} where `state` is the semantic modifier
    used for the status dot, `label` is the human text, and `lane` is the row-rail
    modifier ('alert' / 'warn' / 'live' / '' for settled rows). Stock problems
    override the lane because they block dispatch regardless of delivery progress.
    """
    from business.templatetags.business_pwa_tags import (
        _resolve_order_status, _DL_STATUS_MAP, _ORDER_STATUS_MAP,
    )

    source, key = _resolve_order_status(order)
    status_map = _DL_STATUS_MAP if source == 'dl' else _ORDER_STATUS_MAP
    state, label, _icon = status_map[key]

    # The shared PWA map calls a published-but-undispatched order "Pending". On the
    # manifest that clashes with the Published tally and the Publish action, and an
    # action should keep its name through the whole flow.
    if source == 'order' and key == 'publish':
        label = 'Published'

    lane = _LANE_BY_STATE.get(state, 'live')
    stock = getattr(order, 'stock_flag', '')
    if stock == 'out_of_stock':
        lane = 'alert'
    elif stock == 'low_stock' and lane != 'alert':
        lane = 'warn'

    return {'state': state, 'label': label, 'lane': lane}
