# Purpose: Price a client's delivery from its distance rate card (BusinessDistanceRate rows).
# Used by: orders.signals (every order save), the seller Delivery Pricing tab (re-price on save).
# Notes: Bands are staff-edited data — no price or km figure lives in code. Only a
#        'rate_card' fee, or a blank-source fee of 0, is ever written; a staff-typed fee wins.

from decimal import Decimal

CENTS = Decimal('0.01')

# Orders past the door. Their charge is history — the invoice and payout legs own it.
CLOSED_ORDER_STATUSES = ('delivered', 'returned', 'cancelled')

# Task statuses where the driver has finished; same set the staff edit screens freeze.
TERMINAL_TASK_STATUSES = ('delivered', 'partial_delivery', 'cancelled', 'rejected',
                          'dropsownlost', 'returned_to_shipper')

# Only the legs that carry the order's own delivery. A return leg is priced on its own.
PRICED_LEGS = ('single', 'hub_delivery')


def band_price(rates, km):
    """The price of the first band that covers ``km``, or None.

    ``rates`` must be ordered by ceiling, blanks last (the model's default
    ordering). A blank ceiling covers everything beyond the bands before it.
    """
    if km is None:
        return None
    km = Decimal(str(km))
    for rate in rates:
        if rate.up_to_km is None or km <= rate.up_to_km:
            return Decimal(str(rate.price)).quantize(CENTS)
    return None


def fee_for_order(order, rates=None):
    """What the rate card says this order costs, or None when it cannot say."""
    if rates is None:
        rates = list(order.business.distance_rates.all()) if order.business_id else []
    return band_price(rates, order.route_distance_km)


def _is_priceable(order):
    if order.order_type != 'normal_delivery':
        return False  # P2P and return pickups have their own pricing
    if order.order_status in CLOSED_ORDER_STATUSES:
        return False
    if order.dl_amount_source == 'manual':
        return False
    if order.dl_amount_source == '' and (order.dl_amount or 0) > 0:
        return False  # typed or imported before the rate card existed — keep it
    return True


def apply_rate_card(order, rates=None):
    """Set the order's fee — and its open tasks' charge — from the rate card.

    Writes through queryset updates so it is safe to call from post_save, and
    mirrors the values onto ``order`` in memory so a task created later in the
    same save picks the fee up. Returns True when anything was written.
    """
    from delivery.models import DeliveryTask
    from orders.models import Order

    if not _is_priceable(order):
        return False
    fee = fee_for_order(order, rates)
    if fee is None:
        return False

    changed = False
    if order.dl_amount != fee or order.dl_amount_source != 'rate_card':
        Order.objects.filter(pk=order.pk).update(dl_amount=fee, dl_amount_source='rate_card')
        order.dl_amount = fee
        order.dl_amount_source = 'rate_card'
        changed = True

    # Tasks already on an invoice or payout, or with a staff-verified charge, keep
    # the figure that was settled or checked.
    written = DeliveryTask.objects.filter(
        order_id=order.pk,
        task_leg__in=PRICED_LEGS,
        charge_invoice__isnull=True,
        settled_delivery_charge__isnull=True,
        verified_delivery_charge__isnull=True,
    ).exclude(
        dl_task_status__in=TERMINAL_TASK_STATUSES,
    ).exclude(dl_price=fee).update(dl_price=fee)
    return changed or bool(written)


def reprice_open_orders(business):
    """Run the rate card over every open order of one client. Returns how many changed."""
    from orders.models import Order

    rates = list(business.distance_rates.all())
    if not rates:
        return 0
    count = 0
    orders = Order.objects.filter(
        business=business, order_type='normal_delivery',
    ).exclude(order_status__in=CLOSED_ORDER_STATUSES).exclude(dl_amount_source='manual')
    for order in orders.only('id', 'business_id', 'order_type', 'order_status',
                             'dl_amount', 'dl_amount_source', 'route_distance_km'):
        if apply_rate_card(order, rates):
            count += 1
    return count
