# Purpose: Single source of truth for the {placeholders} a client may use in a
#          WhatsApp notification trigger message (/business/settings/whatsapp-triggers/).
# Used by: core/order_notifications.py (render), business/views.py + whatsapp_triggers.html (help panel).
# Notes:   The settings page help panel is generated FROM TOKEN_GROUPS — adding a token
#          here is all it takes to list it, so the page can never advertise a dead token.
#          Bodies also support {if token}…{else}…{endif} (core.message_templates.apply_conditionals).

import logging
import re

from django.conf import settings

logger = logging.getLogger(__name__)

# Tokens shown on the settings page, in display order. (name, help text).
# A token resolving to '' is deliberate: a blank line reads better than "None"
# in a customer's WhatsApp, and it makes {if token} the "do we know this?" test.
TOKEN_GROUPS = [
    {
        'label': 'Customer',
        'icon': 'fa-solid fa-user',
        'tokens': [
            ('customer_name', 'Name on the order'),
            ('customer_phone', 'Customer phone number'),
            ('delivery_address', 'Delivery address'),
        ],
    },
    {
        'label': 'Order',
        'icon': 'fa-solid fa-box',
        'tokens': [
            ('order_number', 'EZZY order number'),
            ('client_order_code', 'Your own order reference'),
            ('order_date', 'Date the order was placed (e.g. 21 Sep 2026)'),
            ('order_status', 'Current order status'),
            ('package_description', 'What is in the package'),
            ('item_count', 'Number of pieces in the order'),
            ('order_items', 'Item list, e.g. "Shirt x2, Cap x1"'),
            ('order_total', 'Value of the order items, e.g. 250.00'),
            ('cod_amount', 'Cash to collect, e.g. 150.00 (blank when nothing to collect)'),
            ('payment_method', '"Cash on Delivery" or "Prepaid"'),
        ],
    },
    {
        'label': 'Delivery',
        'icon': 'fa-solid fa-truck-fast',
        'tokens': [
            ('task_number', 'Delivery task code'),
            ('tracking_link', 'Live tracking link for the customer'),
            ('delivery_date', 'Date of the delivery run'),
            ('time_slot', 'Preferred time slot, when the customer picked one'),
            ('delivery_speed', 'Normal / Same Day / On Demand'),
            ('failure_reason', 'Why an attempt failed (Failed trigger only)'),
            ('reschedule_date', 'New date after a failed attempt'),
        ],
    },
    {
        'label': 'Driver',
        'icon': 'fa-solid fa-motorcycle',
        'tokens': [
            ('driver_name', 'Assigned driver'),
            ('driver_phone', 'Driver contact number'),
            ('vehicle_type', 'Car / Bike / Van'),
            ('vehicle_number', 'Vehicle plate number'),
        ],
    },
    {
        'label': 'Your business',
        'icon': 'fa-solid fa-store',
        'tokens': [
            ('business_name', 'Your store name'),
            ('business_phone', 'Your contact number'),
            ('business_whatsapp', 'Your WhatsApp number'),
        ],
    },
]

TOKEN_NAMES = [name for group in TOKEN_GROUPS for name, _ in group['tokens']]

# Matches {token} and the {if token} of a conditional block, so validation does
# not flag a legitimate {if cod_amount} as an unknown placeholder.
_TOKEN_RE = re.compile(r'\{(?:if\s+)?(\w+)\}')
_CONTROL_WORDS = {'else', 'endif'}


def unknown_tokens(body):
    """Placeholder names used in ``body`` that we cannot fill. Order-preserving."""
    seen = []
    for name in _TOKEN_RE.findall(body or ''):
        if name in _CONTROL_WORDS or name in TOKEN_NAMES or name in seen:
            continue
        seen.append(name)
    return seen


# ---------------------------------------------------------------------------
# Value resolution
# ---------------------------------------------------------------------------

def _money(value):
    """'150.00', or '' for nothing/zero — a zero line is noise in a customer message."""
    try:
        amount = float(value or 0)
    except (TypeError, ValueError):
        return ''
    return f'{amount:.2f}' if amount else ''


def _date(value, fmt='%d %b %Y'):
    return value.strftime(fmt) if value else ''


def _choice_label(obj, field, value):
    """Human label for a choices field ('customer_not_home' → 'Customer Not Home')."""
    if not value:
        return ''
    try:
        return dict(obj._meta.get_field(field).choices or []).get(value, value)
    except Exception:
        return value


def _site_url():
    return (getattr(settings, 'SITE_URL', '') or 'https://ezzydelivery.qa').rstrip('/')


def _driver_values(task):
    driver = getattr(task, 'driver', None) if task else None
    if not driver:
        return {'driver_name': '', 'driver_phone': '', 'vehicle_type': '', 'vehicle_number': ''}

    vehicle = (driver.driver_vehicle.filter(vehicle_status='active').first()
               or driver.driver_vehicle.first())
    return {
        'driver_name': driver.driver_name or '',
        'driver_phone': driver.driver_phone or '',
        'vehicle_type': _choice_label(vehicle, 'vehicle_type', vehicle.vehicle_type) if vehicle else '',
        'vehicle_number': (vehicle.vehicle_no if vehicle else '') or '',
    }


def _order_totals(order):
    items = order.order_items.all()
    total = sum(float(i.total_price or 0) for i in items)
    count = order.package_qty or sum(i.quantity or 0 for i in items)
    return {'order_total': _money(total), 'item_count': str(count or '')}


def build_context(order, task=None, body=''):
    """Every token's value for this order/task.

    ``body`` is used only to skip the extra queries for tokens the message does
    not mention — an item list or a vehicle plate costs a query each, and most
    trigger messages use neither.
    """
    business = getattr(order, 'business', None)
    cod = _money(order.cod_amount)

    ctx = {
        # Customer
        'customer_name': order.customer_name or '',
        'customer_phone': order.customer_phone or '',
        'delivery_address': order.customer_address or '',
        # Order
        'order_number': order.order_number or '',
        'client_order_code': order.client_order_code or '',
        'order_date': _date(order.order_date),
        'order_status': _choice_label(order, 'order_status', order.order_status),
        'package_description': order.package_description or '',
        'cod_amount': cod,
        'payment_method': 'Cash on Delivery' if cod else 'Prepaid',
        # Delivery
        'task_number': (getattr(task, 'dl_task_number', '') or '') if task else '',
        'tracking_link': '',
        'delivery_date': _date(getattr(task, 'dl_task_date', None) if task else order.scheduled_date),
        'time_slot': _choice_label(order, 'preferred_time_slot', order.preferred_time_slot),
        'delivery_speed': (getattr(task, 'dl_speed', '') if task else order.delivery_speed) or '',
        'failure_reason': '',
        'reschedule_date': '',
        # Business
        'business_name': getattr(business, 'business_name', '') or '',
        'business_phone': getattr(business, 'business_phone', '') or '',
        'business_whatsapp': getattr(business, 'business_whatsapp', '') or '',
        # Filled below only when the body asks for them
        'order_items': '',
        'order_total': '',
        'item_count': '',
        'driver_name': '',
        'driver_phone': '',
        'vehicle_type': '',
        'vehicle_number': '',
    }

    if task is not None:
        if task.tracking_token:
            ctx['tracking_link'] = f'{_site_url()}/track/{task.tracking_token}/'
        ctx['failure_reason'] = _choice_label(task, 'failure_reason', task.failure_reason)
        ctx['reschedule_date'] = _date(task.reschedule_date)

    used = set(_TOKEN_RE.findall(body or ''))

    if used & {'driver_name', 'driver_phone', 'vehicle_type', 'vehicle_number'}:
        ctx.update(_driver_values(task))
    if 'order_items' in used:
        ctx['order_items'] = order.whatsapp_product_summary or ''
    if used & {'order_total', 'item_count'}:
        ctx.update(_order_totals(order))

    return ctx


def render(body, order, task=None):
    """Fill ``body`` with this order's values. Never raises — a template mistake
    must not swallow the notification, so an unfillable token is left verbatim."""
    from core.message_templates import _SafeDict, apply_conditionals

    if not body:
        return ''
    try:
        context = build_context(order, task=task, body=body)
        return apply_conditionals(body, context).format_map(_SafeDict(**context)).strip()
    except Exception:
        logger.exception('Trigger message render failed for order %s — sending raw body',
                         getattr(order, 'order_number', '?'))
        return body.strip()


# ---------------------------------------------------------------------------
# Default message previews
#
# The settings page shows each trigger's built-in message as the textarea
# placeholder, so a client can see what we send before deciding to override it.
# Rather than restate those bodies here (two copies drift), we run the real
# builder in core/order_notifications.py against a stub whose every field is the
# matching {token}. What the client reads is therefore the actual default, already
# written in the placeholder vocabulary they can copy and edit.
# ---------------------------------------------------------------------------

# Settings-page trigger → the lifecycle event that _build_message() knows.
# 'picked_up' and 'start_ride' are absent on purpose: no event fires for them.
TRIGGER_TO_EVENT = {
    'assigned': 'driver_assigned',
    'out_for_delivery': 'out_for_delivery',
    'delivered': 'delivered',
    'failed': 'delivery_failed',
}


class _StubDate:
    def strftime(self, fmt):
        return '{reschedule_date}'


class _StubUser:
    def get_full_name(self):
        return '{driver_name}'


class _StubDriver:
    driver_code = '{driver_name}'
    driver_phone = '{driver_phone}'
    user = _StubUser()


class _StubOrder:
    customer_name = '{customer_name}'
    order_number = '{order_number}'
    customer_address = '{delivery_address}'
    cod_amount = '{cod_amount}'
    cancellation_reason = '{order_status}'
    CANCELLATION_REASON_CHOICES = []


class _StubTask:
    driver = _StubDriver()
    failure_reason = '{failure_reason}'
    reschedule_date = _StubDate()
    FAILURE_REASON_CHOICES = []


def default_message(trigger_status):
    """The built-in message for a trigger, written with {tokens}. '' when none."""
    event = TRIGGER_TO_EVENT.get(trigger_status)
    if not event:
        return ''
    from core.order_notifications import _build_message
    try:
        return _build_message(event, _StubOrder(), _StubTask()) or ''
    except Exception:
        # A new field in _build_message the stub has not got. Better a blank
        # placeholder than a 500 on a settings page.
        logger.exception('Default message preview failed for trigger %s', trigger_status)
        return ''
