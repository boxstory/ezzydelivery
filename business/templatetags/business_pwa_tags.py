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


# Status badge mapping: (css_modifier, label, icon)
_STATUS_MAP = {
    'dms_2': ('delivered', 'Delivered', 'fa-check-circle'),
    'dms_0': ('assigned', 'Assigned', 'fa-user-check'),
    'dms_1': ('transit', 'In Transit', 'fa-truck'),
    'dms_4': ('transit', 'In Transit', 'fa-truck'),
    'dms_3': ('failed', 'Failed', 'fa-times-circle'),
    'dms_9': ('cancelled', 'Cancelled', 'fa-ban'),
    'cancelled': ('cancelled', 'Cancelled', 'fa-ban'),
    'delivered': ('delivered', 'Delivered', 'fa-check-circle'),
    'fulfilled': ('delivered', 'Delivered', 'fa-check-circle'),
    'to_review': ('review', 'Review', 'fa-clock'),
    'ready_to_pickup': ('ready', 'Ready', 'fa-box'),
    'publish': ('pending', 'Pending', 'fa-hourglass'),
}


@register.simple_tag
def order_status_badge(order):
    """Return HTML for a PWA status badge based on order + delivery task status."""
    try:
        delivery = order.delivery_task.first() if hasattr(order, 'delivery_task') else None
    except Exception:
        delivery = None

    key = None
    if delivery and hasattr(delivery, 'dl_task_status_dms'):
        dms = str(delivery.dl_task_status_dms)
        dms_key = 'dms_' + dms
        if dms_key in _STATUS_MAP:
            key = dms_key

    if key is None:
        status = getattr(order, 'order_status', '')
        if status in _STATUS_MAP:
            key = status
        else:
            key = 'publish'

    modifier, label, icon = _STATUS_MAP[key]
    html = (
        '<span class="pwa-order-status-badge pwa-order-status-badge--{mod}">'
        '<i class="fas {icon}"></i> {label}</span>'
    ).format(mod=modifier, icon=icon, label=label)
    return mark_safe(html)
