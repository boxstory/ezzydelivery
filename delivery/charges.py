# Purpose: Single resolver for the delivery charge billed to a business client.
# Used by: the client payout report/action/invoice, the Client Charges console,
#          DeliveryTask.billable_charge, and the printed waybill line.
# Notes: Always `is not None` — a charge staff deliberately verified at 0.00 must never fall back to dl_price.

from decimal import Decimal

from django.db.models import Case, When, F, DecimalField, Value


def billable_charge(task):
    """The delivery charge to bill for one task.

    The staff-verified figure from the Client Charges console when one exists,
    otherwise the raw system charge — so tasks that were never put through
    verification bill exactly as they did before.
    """
    if getattr(task, 'verified_delivery_charge', None) is not None:
        return Decimal(str(task.verified_delivery_charge))
    return Decimal(str(task.dl_price or 0))


def charge_paid(task):
    """What a payout actually deducted for one task.

    Falls back to the live figure for payouts made before the charge was frozen
    (``settled_delivery_charge``), so historic invoices still render.
    """
    if getattr(task, 'settled_delivery_charge', None) is not None:
        return Decimal(str(task.settled_delivery_charge))
    return billable_charge(task)


# Queryset form of billable_charge(), for aggregation and annotation.
BILLABLE_CHARGE = Case(
    When(verified_delivery_charge__isnull=False, then=F('verified_delivery_charge')),
    When(dl_price__isnull=False, then=F('dl_price')),
    default=Value(Decimal('0.00')),
    output_field=DecimalField(max_digits=10, decimal_places=2),
)


def known_charge(task):
    """billable_charge(), or None when the task has not been priced yet.

    dl_price is left at 0.00 on most tasks until the Client Charges console
    verifies the real figure (351 of the 354 tasks created in the 30 days to
    2026-09-21), so an unverified zero means "not priced yet", not "free
    delivery". A verified zero is a real decision and comes back as 0.

    For display only — anything that BILLS must keep using billable_charge(),
    where an unpriced task correctly contributes nothing.
    """
    if getattr(task, 'verified_delivery_charge', None) is not None:
        return Decimal(str(task.verified_delivery_charge))
    charge = Decimal(str(task.dl_price or 0))
    return charge if charge > 0 else None


def waybill_charges(orders):
    """{order_id: Decimal} — the delivery charge to print on each order's label.

    One query for the whole print run rather than one per label. An order with
    several tasks (a retry, an exchange leg) resolves to its latest task, which
    is the charge that will actually be billed.

    P2P carries its fee on the order itself because the booking is priced
    before any task exists, so ``Order.dl_amount`` is the fallback for a label
    printed at the packing bench ahead of dispatch. An order with neither is
    left out of the map entirely: the charge is not yet known, and printing
    "QAR 0.00" would read as free delivery. See known_charge() for the same
    rule applied to an unverified zero on the task itself.
    """
    from delivery.models import DeliveryTask

    order_ids = [o.id for o in orders]
    if not order_ids:
        return {}

    charges = {}
    # Ascending id, so the last row written per order is its newest task.
    tasks = (DeliveryTask.objects
             .filter(order_id__in=order_ids)
             .order_by('order_id', 'id')
             .only('id', 'order_id', 'dl_price', 'verified_delivery_charge'))
    for task in tasks:
        charge = known_charge(task)
        if charge is not None:
            charges[task.order_id] = charge

    for order in orders:
        if order.id not in charges:
            fee = Decimal(str(order.dl_amount or 0))
            if fee > 0:
                charges[order.id] = fee

    return charges


def collect_totals(orders):
    """{order_id: Decimal} — the single figure a label prints as "Collect".

    The goods COD plus the delivery charge, as one number. The label is the
    driver's instruction at the door, and two money figures on a package
    invited the wrong one being taken.

    Falls back to the COD alone when the charge is not priced yet, so a label
    printed ahead of verification still carries the cash it knows about.
    """
    charges = waybill_charges(orders)
    return {
        o.id: Decimal(str(o.cod_amount or 0)) + charges.get(o.id, Decimal('0'))
        for o in orders
    }
