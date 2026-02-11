from django import template
from django.utils.safestring import mark_safe
from orders.models import Order
from core.context_processors import get_cached_business

register = template.Library()


@register.simple_tag(takes_context=True)
def business_pending_count(context):
    """Return count of pending orders for the current business user."""
    request = context.get('request')
    if not request or not request.user.is_authenticated:
        return 0
    try:
        business = get_cached_business(request)
        if not business:
            return 0
        count = Order.objects.filter(
            business=business.business_id
        ).exclude(
            order_status__in=['delivered', 'fulfilled', 'cancelled']
        ).count()
        return count
    except Exception:
        return 0


# Delivery task status mapping: dl_task_status text field → (css_modifier, label, icon)
_DL_STATUS_MAP = {
    'delivered': ('delivered', 'Delivered', 'fa-check-circle'),
    'assigned': ('assigned', 'Assigned', 'fa-user-check'),
    'accepted': ('assigned', 'Accepted', 'fa-user-check'),
    'picked_up': ('transit', 'Picked Up', 'fa-box-open'),
    'start_ride': ('transit', 'In Transit', 'fa-truck'),
    'out_for_delivery': ('transit', 'Out for Delivery', 'fa-truck'),
    'in_transit': ('transit', 'In Transit', 'fa-truck'),
    'contacted': ('transit', 'Contacted', 'fa-phone'),
    'non_reachable': ('failed', 'Non Reachable', 'fa-phone-slash'),
    'failed': ('failed', 'Failed', 'fa-times-circle'),
    'rejected': ('cancelled', 'Rejected', 'fa-ban'),
    'cancelled': ('cancelled', 'Cancelled', 'fa-ban'),
    'pending': ('pending', 'Pending', 'fa-hourglass'),
    'for_review': ('review', 'Review', 'fa-clock'),
    'publish_to_dms': ('pending', 'Published', 'fa-hourglass'),
    'address_pending': ('review', 'Addr. Pending', 'fa-map-marker-alt'),
    'customer_confiration_pending': ('review', 'Confirm Pending', 'fa-phone'),
}

# Order status fallback mapping: order_status → (css_modifier, label, icon)
_ORDER_STATUS_MAP = {
    'cancelled': ('cancelled', 'Cancelled', 'fa-ban'),
    'delivered': ('delivered', 'Delivered', 'fa-check-circle'),
    'fulfilled': ('delivered', 'Delivered', 'fa-check-circle'),
    'to_review': ('review', 'Review', 'fa-clock'),
    'ready_to_pickup': ('ready', 'Ready', 'fa-box'),
    'publish': ('pending', 'Pending', 'fa-hourglass'),
    'processing': ('pending', 'Processing', 'fa-hourglass'),
}


def _resolve_order_status(order):
    """Resolve the display status for an order. Delivery task status takes priority."""
    try:
        delivery = order.delivery_task.first() if hasattr(order, 'delivery_task') else None
    except Exception:
        delivery = None

    # If delivery task exists, use its text status (takes priority over order status)
    if delivery:
        dl_status = getattr(delivery, 'dl_task_status', '')
        if dl_status and dl_status in _DL_STATUS_MAP:
            return ('dl', dl_status)

    # Fall back to order status
    status = getattr(order, 'order_status', '')
    if status in _ORDER_STATUS_MAP:
        return ('order', status)

    return ('order', 'publish')


@register.simple_tag
def order_status_badge(order):
    """Return HTML for a PWA status badge based on order + delivery task status."""
    source, key = _resolve_order_status(order)
    status_map = _DL_STATUS_MAP if source == 'dl' else _ORDER_STATUS_MAP
    modifier, label, icon = status_map[key]
    html = (
        '<span class="pwa-order-status-badge pwa-order-status-badge--{mod}">'
        '<i class="fas {icon}"></i> {label}</span>'
    ).format(mod=modifier, icon=icon, label=label)
    return mark_safe(html)


@register.simple_tag
def order_status_class(order):
    """Return just the CSS modifier string (e.g. 'delivered', 'failed') for card accent."""
    source, key = _resolve_order_status(order)
    status_map = _DL_STATUS_MAP if source == 'dl' else _ORDER_STATUS_MAP
    modifier, _, _ = status_map[key]
    return modifier
