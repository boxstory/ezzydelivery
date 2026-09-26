# Purpose: One answer to "how much cash does the driver take at this door", and how to split it back.
# Used by: the driver PWA card + detail sheet, the completion endpoints, and the staff COD screens.
# Notes: The driver is shown ONE figure and never asked to tell COD from fee — the split is ours to
#        do on the way back in. COD is the client's money; the fee is Ezzy's own revenue.

from collections import namedtuple
from decimal import Decimal

CENTS = Decimal('0.01')

# total    — the single number the driver is shown and asked for
# cod_due  — the client's money inside that total
# fee_due  — our delivery fee inside that total, cash at this door
CollectAmount = namedtuple('CollectAmount', ['total', 'cod_due', 'fee_due'])


def _money(value):
    return Decimal(str(value or 0)).quantize(CENTS)


def amount_to_collect(task):
    """What the driver must collect on this delivery, as one figure plus its parts.

    A fee is due at the door in two cases: a P2P booking whose receiver pays, and
    a client switched to `customer_pays_delivery`. Everyone else is billed on
    their charge invoice, so nothing is due for it and fee_due is zero.
    """
    order = getattr(task, 'order', None)
    if order is None:
        return CollectAmount(Decimal('0.00'), Decimal('0.00'), Decimal('0.00'))

    cod_due = Decimal('0.00')
    # 'online_paid' means the customer already settled; there is nothing at the door.
    if order.cod_status_by_client != 'online_paid':
        cod_due = _money(order.cod_amount)

    fee_due = Decimal('0.00')
    booking = getattr(order, 'p2p_booking', None)
    if booking is not None and booking.fee_due_at_delivery:
        fee_due = _money(booking.fee_amount)
    else:
        # Clients on 'customer pays delivery' pass the charge to the buyer, so it
        # is due at the door on top of the COD — on an online-paid order too. For
        # these clients 'online_paid' covers the goods only: the drivers were
        # taking the fee in cash while the app said "collect 0", so none of it was
        # recorded (Alan the label, backfilled 2026-09-26). Never both this and an
        # invoice — billable_tasks() drops the task once the cash is recorded.
        business = getattr(order, 'business', None)
        if business is not None and getattr(business, 'customer_pays_delivery', False):
            from delivery.charges import billable_charge
            fee_due = _money(billable_charge(task))

    return CollectAmount(cod_due + fee_due, cod_due, fee_due)


def split_collected(task, collected):
    """Split what the driver actually handed over into (cod_part, fee_part).

    The client's money is satisfied FIRST. If the driver comes back short, the
    shortfall falls on our own fee, never on the business's COD — we carry the
    risk of an under-collection, because the alternative is telling a client
    their customer's money went missing to cover our charge.

    Anything above the expected total is treated as COD: an overpayment is the
    customer's, and it has to show up on the leg that settles to them.
    """
    collected = _money(collected)
    if collected <= 0:
        return Decimal('0.00'), Decimal('0.00')

    due = amount_to_collect(task)
    if due.fee_due <= 0:
        return collected, Decimal('0.00')

    cod_part = min(collected, due.cod_due)
    fee_part = min(collected - cod_part, due.fee_due)
    # Whatever is left over is the customer's money, not extra fee.
    cod_part += collected - cod_part - fee_part
    return cod_part, fee_part
