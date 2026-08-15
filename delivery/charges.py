# Purpose: Single resolver for the delivery charge billed to a business client.
# Used by: the client payout report/action/invoice, the Client Charges console, and DeliveryTask.billable_charge.
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
