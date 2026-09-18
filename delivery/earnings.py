# Purpose: Single resolver for what one delivery pays the driver.
# Used by: DeliveryTask.calculate_driver_earnings, the payout worksheet queue + tallies, the pay-rate console.
# Notes: The ONLY module allowed to know the fallback figures. Resolution is per-driver card, then the
#        fleet card, then FALLBACK — an empty rate table must never make a fee None. Same shape as
#        delivery/charges.py: a Python function and its queryset twin, so the rule lives in one place.

from decimal import Decimal, ROUND_HALF_UP

from django.db.models import Case, When, F, Q, Value, DecimalField
from django.db.models.functions import Coalesce

# What the fee was before it became configurable. Kept as the floor of the
# resolution chain so a fresh install, or a date no card covers, still pays
# exactly what the hardcoded rule used to pay.
FALLBACK_NORMAL_FEE = Decimal('10.00')
FALLBACK_HUB_FEE = Decimal('10.00')
FALLBACK_PND_PERCENT = Decimal('80.00')
# An exchange starts level with a normal delivery, so adding the leg changes no
# driver's pay on the day it ships. Raise it on the rate card, not here.
FALLBACK_EXCHANGE_FEE = Decimal('10.00')

CENTS = Decimal('0.01')


class RateCard:
    """The three figures a fee is built from, plus where they came from.

    A plain object rather than the model row itself because the fallback has no
    row, and every caller wants the same attributes regardless.
    """

    __slots__ = ('normal_fee', 'hub_fee', 'pick_and_drop_percent', 'exchange_fee',
                 'source', 'rate_id')

    def __init__(self, normal_fee, hub_fee, pick_and_drop_percent,
                 exchange_fee=None, source='fallback', rate_id=None):
        self.normal_fee = Decimal(str(normal_fee))
        self.hub_fee = Decimal(str(hub_fee))
        self.pick_and_drop_percent = Decimal(str(pick_and_drop_percent))
        # Cards written before the exchange leg existed have no figure of their
        # own; falling back to the normal fee keeps them pricing as they always did.
        self.exchange_fee = Decimal(str(
            exchange_fee if exchange_fee is not None else normal_fee))
        self.source = source          # 'driver' | 'fleet' | 'fallback'
        self.rate_id = rate_id

    @classmethod
    def from_row(cls, row):
        return cls(
            row.normal_fee, row.hub_fee, row.pick_and_drop_percent,
            exchange_fee=getattr(row, 'exchange_fee', None),
            source='driver' if row.driver_id else 'fleet',
            rate_id=row.pk,
        )

    @property
    def is_fallback(self):
        return self.source == 'fallback'

    def __repr__(self):
        return (f'<RateCard {self.source} normal={self.normal_fee} '
                f'hub={self.hub_fee} pnd={self.pick_and_drop_percent}% '
                f'exchange={self.exchange_fee}>')


FALLBACK_CARD = RateCard(
    FALLBACK_NORMAL_FEE, FALLBACK_HUB_FEE, FALLBACK_PND_PERCENT,
    exchange_fee=FALLBACK_EXCHANGE_FEE, source='fallback')


def rate_rows(driver_ids=None, on_date=None):
    """Rate card rows, newest agreement first.

    `driver_ids` narrows to those drivers' cards plus the fleet card; `on_date`
    narrows to cards covering that day. The fleet card is matched with
    ``driver_id__isnull``, never ``__in=[None]`` — SQL's ``IN (NULL)`` matches
    nothing, which made the fleet card invisible and every driver fall through
    to the fallback.
    """
    from fleet.models import DeliveryPayRate
    qs = DeliveryPayRate.objects.all()
    if driver_ids is not None:
        ids = [d for d in driver_ids if d is not None]
        qs = qs.filter(Q(driver_id__in=ids) | Q(driver_id__isnull=True))
    if on_date is not None:
        qs = qs.filter(effective_from__lte=on_date).filter(
            Q(effective_to__isnull=True) | Q(effective_to__gte=on_date))
    return list(qs.order_by('-effective_from', '-id'))


def _pick(rows, driver_id):
    """Driver card first, then fleet card, then the fallback. `rows` must already
    be filtered to cards that cover the date in question, newest first."""
    if driver_id is not None:
        for row in rows:
            if row.driver_id == driver_id:
                return RateCard.from_row(row)
    for row in rows:
        if row.driver_id is None:
            return RateCard.from_row(row)
    return FALLBACK_CARD


def resolve_card(driver_id=None, on_date=None):
    """The rate card in force for one driver on one date.

    A per-driver card always beats the fleet card; the fleet card beats the
    fallback. Dates are day-precise for the same reason salary agreements are —
    a card that ended on the 10th must not price a delivery made on the 30th.
    """
    from django.utils import timezone
    on_date = on_date or timezone.localdate()
    return _pick(rate_rows([driver_id] if driver_id else [], on_date), driver_id)


class CardResolver:
    """Loads the rate rows once, then answers (driver, date) from memory.

    The payout desk prices a page of deliveries that can span months. Resolving
    per row would be a query per delivery; resolving once for the whole page
    would price a delivery made in June with the card that started in August.
    This does neither.
    """

    def __init__(self, driver_ids=None):
        self._rows = rate_rows(driver_ids)

    def for_driver(self, driver_id, on_date):
        from django.utils import timezone
        on_date = on_date or timezone.localdate()
        return _pick([r for r in self._rows if r.covers_date(on_date)], driver_id)

    def for_task(self, task):
        return self.for_driver(
            getattr(task, 'driver_id', None),
            getattr(task, 'dl_task_date', None),
        )


def driver_fee(task, card=None):
    """What one delivery pays its driver, before any staff override.

    This is the *proposal* the verification queue shows. The figure actually
    paid is ``verified_earnings`` once staff have set it — applied by the
    caller, never folded in here, so "what does the rule say" stays answerable
    after a manual adjustment.
    """
    if card is None:
        card = resolve_card(
            getattr(task, 'driver_id', None),
            getattr(task, 'dl_task_date', None),
        )

    if task.task_leg == 'hub_delivery':
        return card.hub_fee.quantize(CENTS, rounding=ROUND_HALF_UP)

    # Before the order-type branches on purpose: an exchange is two handovers in
    # one visit whatever the goods travel as, and pricing it as a pick & drop
    # percentage would pay it off a delivery charge the replacement does not carry.
    if task.task_leg == 'exchange':
        return card.exchange_fee.quantize(CENTS, rounding=ROUND_HALF_UP)

    order = getattr(task, 'order', None)
    if order and order.order_type == 'pick_and_drop':
        charge = Decimal(str(task.dl_price or 0))
        fee = charge * card.pick_and_drop_percent / Decimal('100')
        return fee.quantize(CENTS, rounding=ROUND_HALF_UP)

    return card.normal_fee.quantize(CENTS, rounding=ROUND_HALF_UP)


def _window(row):
    """The Q that matches deliveries this card actually covers, by their own date."""
    q = Q(dl_task_date__gte=row.effective_from)
    if row.effective_to is not None:
        q &= Q(dl_task_date__lte=row.effective_to)
    return q


def _card_branches(row, extra=None):
    """The fee branches for one card: hub leg, exchange, pick & drop, everything else.

    The order here mirrors driver_fee() exactly. These two are twins — a branch
    added to one and not the other means the queue prices a delivery differently
    from the task page showing it.
    """
    scope = _window(row)
    if extra is not None:
        scope &= extra
    percent = Decimal(str(row.pick_and_drop_percent)) / Decimal('100')
    return [
        When(scope & Q(task_leg='hub_delivery'), then=Value(row.hub_fee)),
        When(scope & Q(task_leg='exchange'), then=Value(row.exchange_fee)),
        When(scope & Q(order__order_type='pick_and_drop'),
             then=Coalesce(F('dl_price'), Value(Decimal('0.00'))) * Value(percent)),
        When(scope, then=Value(row.normal_fee)),
    ]


def fee_expr(rows=None, include_verified=True):
    """Queryset twin of driver_fee() — the SQL that prices a whole queue at once.

    `rows` is a rate_rows() list. Every branch carries the card's own date
    window, so a queue spanning a rate change is priced the way each delivery
    was priced on its own day rather than the way today's card would price it.
    Driver cards are emitted before fleet cards, and newest first within each,
    which is the same precedence _pick() applies in Python.

    Rounding differs from driver_fee() by at most one fils on a pick & drop
    line: the DecimalField output rounds on fetch rather than per row.
    """
    rows = rate_rows() if rows is None else rows

    branches = []
    if include_verified:
        branches.append(When(verified_earnings__isnull=False, then=F('verified_earnings')))

    # Per-driver cards first — a fleet branch would otherwise swallow them.
    for row in rows:
        if row.driver_id is not None:
            branches.extend(_card_branches(row, Q(driver_id=row.driver_id)))
    for row in rows:
        if row.driver_id is None:
            branches.extend(_card_branches(row))

    # Nothing covers this delivery's date: the built-in fallback, spelled out
    # rather than left to a bare default, so hub and pick & drop keep their
    # shape when no card has ever been saved.
    branches.append(When(task_leg='hub_delivery', then=Value(FALLBACK_HUB_FEE)))
    branches.append(When(
        order__order_type='pick_and_drop',
        then=Coalesce(F('dl_price'), Value(Decimal('0.00')))
        * Value(FALLBACK_PND_PERCENT / Decimal('100'))))

    return Case(
        *branches,
        default=Value(FALLBACK_NORMAL_FEE),
        output_field=DecimalField(max_digits=12, decimal_places=2),
    )
