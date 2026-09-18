# Purpose: The refund ceiling for an order and the leg that can pay it.
# Used by: the replacement/exchange flow, the client return form, and process_cod_return.
# Notes: Refund figures are TYPED BY STAFF, never derived from items — 28% of orders carry no
#        OrderItem rows and 78% of the rows that exist have no unit_price, so quantity x price
#        is unavailable for most of the book. These helpers validate and route an amount; they
#        never invent one.

from decimal import Decimal

from django.db.models import Sum

ZERO = Decimal('0.00')


def _money(value):
    """Coerce to a 2dp Decimal, treating None as zero."""
    if value in (None, ''):
        return ZERO
    return Decimal(str(value)).quantize(Decimal('0.01'))


def _collected_tasks(order):
    """Tasks on this order that actually took money from the customer."""
    from delivery import models as delivery_models

    return delivery_models.DeliveryTask.objects.filter(order=order, cod_collected=True)


def refunded_for(order, task=None):
    """COD already handed back on this order, or on one task of it.

    cod_return rows are written positive (WalletService.record_cod_return rejects
    anything else), but abs() keeps this honest against a hand-corrected row.
    """
    from fleet import models as fleet_models

    task_ids = [task.id] if task is not None else list(
        _collected_tasks(order).values_list('id', flat=True))
    if not task_ids:
        return ZERO

    total = fleet_models.DriverTransaction.objects.filter(
        transaction_type='cod_return',
        delivery_task_id__in=task_ids,
    ).aggregate(total=Sum('amount'))['total']
    return abs(_money(total))


def collected_for(order):
    """COD actually taken from the customer, NET of refunds already made.

    business/views.py's older _collected_cod_for ignored prior refunds, so two
    sequential returns each believed the full amount was still refundable. An
    order the driver never collected on has nothing to hand back, however large
    its cod_amount is.
    """
    gross = _collected_tasks(order).aggregate(
        total=Sum('cod_collected_amount'))['total']
    return max(_money(gross) - refunded_for(order), ZERO)


def refund_ceiling(order):
    """The most that may be handed back on this order. Never derived from item prices."""
    return collected_for(order)


def task_headroom(task):
    """What is still refundable against one task's own collection."""
    return max(_money(task.cod_collected_amount) - refunded_for(task.order, task=task), ZERO)


def refund_route(order, amount):
    """Which leg can pay a refund of `amount` on `order`.

    Returns (route, task, reason):
      ('driver_wallet', task, '')  -> process_cod_return against that task
      ('client_ledger', None, '')  -> post against the seller's float
      (None, None, '<why not>')

    The driver's wallet can only pay back cash it still holds for this order, so
    a settled or prepaid order falls through to the seller's float instead.
    """
    from fleet import ledger_service

    amount = _money(amount)
    if amount <= ZERO:
        return None, None, "Refund amount must be more than zero."

    ceiling = refund_ceiling(order)
    if amount > ceiling:
        return None, None, (
            f"Refund of {amount} exceeds the {ceiling} still refundable on this order."
        )

    # Prefer the driver's wallet: the cash is still with him and the round trip
    # never touches the seller's account.
    for task in _collected_tasks(order).filter(cod_client_settled=False).order_by('-id'):
        if task.driver_id and task_headroom(task) >= amount:
            return 'driver_wallet', task, ''

    float_available = ledger_service.available_refund_credit(order.business)
    if float_available >= amount:
        return 'client_ledger', None, ''

    return None, None, (
        f"COD for this order is already settled with the seller and their float is "
        f"{float_available}. Take a payment from them, or reverse the COD payout first."
    )
