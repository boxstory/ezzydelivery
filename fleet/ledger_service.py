# Purpose: The only writer of BusinessLedgerEntry — one client account, one running balance.
# Used by: the client ledger console, and the COD/charge/payout services that post into the account.
# Notes: Balance = what EzzyDelivery owes the client (negative = client owes us). A reversal is a
#        contra entry, never a delete, so a voided row and its reversal cancel and both stay visible.

from decimal import Decimal

from django.db import transaction
from django.db.models import (
    DecimalField, F, OuterRef, Q, Subquery, Sum, Value,
)
from django.db.models.functions import Coalesce
from django.utils import timezone

from fleet.models import BusinessChargeInvoice, BusinessLedgerEntry

ZERO = Decimal('0.00')

# Balances are summed at 14 digits, not the 12 a single row carries: an account
# with thousands of rows can total past what one entry could hold.
BALANCE_FIELD = DecimalField(max_digits=14, decimal_places=2)


def _money(value):
    """Coerce to a 2dp Decimal, treating None as zero."""
    if value in (None, ''):
        return ZERO
    return Decimal(str(value)).quantize(Decimal('0.01'))


# ─────────────────────────────────────────────────────────────────────────────
# Posting
# ─────────────────────────────────────────────────────────────────────────────

@transaction.atomic
def post(business, segment, debit=None, credit=None, description='',
         occurred_on=None, status=None, billing_state=None, kind=None,
         delivery_task=None, order=None, driver=None, txn=None,
         charge_invoice=None, reversal_of=None, reference=None,
         payment_method=None, created_by=None):
    """Write one line to a client's account.

    Exactly one side carries a figure, and it must be positive. The database
    enforces both, but failing here gives the caller a message naming the
    problem instead of a constraint violation from three frames down.

    The order and task numbers are frozen onto the row rather than joined at
    read time, so a later rename cannot restate a line already sent to a client.
    """
    debit = _money(debit)
    credit = _money(credit)

    if debit and credit:
        raise ValueError("A ledger entry takes a debit or a credit, not both")
    if not debit and not credit:
        raise ValueError("A ledger entry needs an amount on one side")
    if debit < 0 or credit < 0:
        raise ValueError("A ledger entry amount cannot be negative")
    if not description:
        raise ValueError("A ledger entry needs a description")

    if order is None and delivery_task is not None:
        order = delivery_task.order

    return BusinessLedgerEntry.objects.create(
        business=business,
        occurred_on=occurred_on or timezone.localdate(),
        segment=segment,
        kind=kind,
        status=status or BusinessLedgerEntry.STATUS_OPEN,
        billing_state=billing_state or BusinessLedgerEntry.BILLING_NOT_BILLABLE,
        debit=debit,
        credit=credit,
        description=description[:200],
        delivery_task=delivery_task,
        order=order,
        driver=driver,
        txn=txn,
        charge_invoice=charge_invoice,
        reversal_of=reversal_of,
        order_number=(order.order_number if order else None),
        task_number=(delivery_task.dl_task_number if delivery_task else None),
        reference=reference,
        payment_method=payment_method,
        created_by=created_by,
    )


@transaction.atomic
def reverse(entry, reason=None, created_by=None, occurred_on=None):
    """Contra-post an entry and mark the original void.

    Both rows stay on the account and they cancel each other, which is why the
    balance deliberately does NOT skip void rows: dropping the original while
    keeping its reversal would move the balance by the amount twice.
    """
    if entry.status == BusinessLedgerEntry.STATUS_VOID:
        raise ValueError(f"{entry.entry_code} is already void")
    if entry.reversed_by.exists():
        raise ValueError(f"{entry.entry_code} has already been reversed")

    label = reason or f"Reversal of {entry.entry_code}"
    contra = post(
        business=entry.business,
        segment=BusinessLedgerEntry.SEGMENT_REVERSAL,
        # The mirror image: what was a credit comes back as a debit.
        debit=entry.credit or None,
        credit=entry.debit or None,
        description=label,
        occurred_on=occurred_on or timezone.localdate(),
        status=BusinessLedgerEntry.STATUS_CLEARED,
        kind=entry.kind,
        delivery_task=entry.delivery_task,
        order=entry.order,
        driver=entry.driver,
        txn=entry.txn,
        charge_invoice=entry.charge_invoice,
        reversal_of=entry,
        reference=entry.entry_code,
        created_by=created_by,
    )

    entry.status = BusinessLedgerEntry.STATUS_VOID
    entry.save(update_fields=['status'])
    return contra


@transaction.atomic
def post_opening_balance(business, created_by=None, occurred_on=None):
    """Seed an account with where it already stands.

    Without this every client opens at zero while genuinely holding COD and
    owing invoices, so the ledger would contradict reality from its first row.

    Only what is already *documented* is seeded: COD we are holding, and the
    unpaid balance of live invoices. Charges that are not yet on an invoice are
    deliberately excluded — they have no document, and they will post as normal
    entries when one is issued. Seeding them here would bill them twice.
    """
    from delivery.models import DeliveryTask

    if BusinessLedgerEntry.objects.filter(
        business=business, segment=BusinessLedgerEntry.SEGMENT_OPENING
    ).exists():
        raise ValueError(f"{business.business_name} already has an opening balance")

    on = occurred_on or timezone.localdate()

    cod_held = DeliveryTask.objects.filter(
        order__business=business,
        cod_collected=True,
        cod_settled=True,
        cod_client_settled=False,
        dl_task_status__in=['delivered', 'partial_delivery'],
    ).aggregate(t=Sum('cod_collected_amount'))['t'] or ZERO

    outstanding = ZERO
    for inv in BusinessChargeInvoice.objects.filter(business=business).exclude(
        status=BusinessChargeInvoice.STATUS_VOID
    ):
        outstanding += inv.amount_due or ZERO

    created = []
    if cod_held > 0:
        created.append(post(
            business=business,
            segment=BusinessLedgerEntry.SEGMENT_OPENING,
            credit=cod_held,
            description="Opening balance - COD held by EzzyDelivery",
            occurred_on=on,
            status=BusinessLedgerEntry.STATUS_OPEN,
            created_by=created_by,
        ))
    if outstanding > 0:
        created.append(post(
            business=business,
            segment=BusinessLedgerEntry.SEGMENT_OPENING,
            debit=outstanding,
            description="Opening balance - invoices outstanding",
            occurred_on=on,
            status=BusinessLedgerEntry.STATUS_OPEN,
            created_by=created_by,
        ))
    return created


# ─────────────────────────────────────────────────────────────────────────────
# Reading
# ─────────────────────────────────────────────────────────────────────────────

def balance(business, as_of=None):
    """What we owe this client right now. Negative means they owe us."""
    qs = BusinessLedgerEntry.objects.filter(business=business)
    if as_of:
        qs = qs.filter(occurred_on__lte=as_of)
    return qs.aggregate(
        t=Coalesce(Sum(F('credit') - F('debit')), Value(ZERO), output_field=BALANCE_FIELD)
    )['t']


def with_running_balance(qs):
    """Annotate each row with the account balance as at that row.

    Deliberately a correlated subquery and NOT a window function. A window is
    evaluated after WHERE, so the moment staff filter the ledger to one segment
    the "balance" column would silently restate itself as a running total of
    only the filtered rows — a page that looks like a statement and lies. This
    form always sums the whole account up to each row, whatever is on screen.
    """
    running = BusinessLedgerEntry.objects.filter(
        business=OuterRef('business'),
    ).filter(
        Q(occurred_on__lt=OuterRef('occurred_on'))
        | Q(occurred_on=OuterRef('occurred_on'), id__lte=OuterRef('id'))
    ).values('business').annotate(
        t=Sum(F('credit') - F('debit'))
    ).values('t')[:1]

    return qs.annotate(
        balance_after=Coalesce(
            Subquery(running, output_field=BALANCE_FIELD),
            Value(ZERO),
            output_field=BALANCE_FIELD,
        )
    )


def entries(business, segment=None, status=None, direction=None,
            date_from=None, date_to=None, search=None):
    """The account, filtered for display, every row carrying the true balance."""
    qs = BusinessLedgerEntry.objects.filter(business=business).select_related(
        'delivery_task', 'order', 'driver', 'txn', 'charge_invoice', 'created_by'
    )

    if segment:
        qs = qs.filter(segment=segment)
    if status:
        qs = qs.filter(status=status)
    if direction == 'receivable':
        qs = qs.filter(debit__gt=0)
    elif direction == 'payable':
        qs = qs.filter(credit__gt=0)
    if date_from:
        qs = qs.filter(occurred_on__gte=date_from)
    if date_to:
        qs = qs.filter(occurred_on__lte=date_to)
    if search:
        needle = search.strip()
        qs = qs.filter(
            Q(entry_code__icontains=needle)
            | Q(order_number__icontains=needle)
            | Q(task_number__icontains=needle)
            | Q(reference__icontains=needle)
            | Q(description__icontains=needle)
        )

    return with_running_balance(qs)


def segment_summary(business):
    """Per-segment totals and how much of each is still open.

    This is what the strip across the top of the ledger reads: one card per
    segment, each saying what it totals and what has not yet cleared.
    """
    rows = BusinessLedgerEntry.objects.filter(business=business).values(
        'segment'
    ).annotate(
        debit_total=Coalesce(Sum('debit'), Value(ZERO), output_field=BALANCE_FIELD),
        credit_total=Coalesce(Sum('credit'), Value(ZERO), output_field=BALANCE_FIELD),
    ).order_by('segment')

    open_rows = BusinessLedgerEntry.objects.filter(
        business=business,
        status__in=[BusinessLedgerEntry.STATUS_PENDING, BusinessLedgerEntry.STATUS_OPEN],
    ).values('segment').annotate(
        open_net=Coalesce(
            Sum(F('credit') - F('debit')), Value(ZERO), output_field=BALANCE_FIELD
        ),
        open_count=Sum(Value(1), output_field=DecimalField(max_digits=10, decimal_places=0)),
    )
    open_by_segment = {r['segment']: r for r in open_rows}

    labels = dict(BusinessLedgerEntry.SEGMENT_CHOICES)
    out = []
    for row in rows:
        seg = row['segment']
        opened = open_by_segment.get(seg, {})
        out.append({
            'segment': seg,
            'label': labels.get(seg, seg),
            'debit_total': row['debit_total'],
            'credit_total': row['credit_total'],
            'net': row['credit_total'] - row['debit_total'],
            'open_net': opened.get('open_net', ZERO),
            'open_count': int(opened.get('open_count') or 0),
        })
    return out
