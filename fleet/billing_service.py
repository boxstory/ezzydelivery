# Purpose: The receivable leg — bill a business for delivery charges, take payment, void.
# Used by: the Charges to Collect console, the charge invoice screens (staff + seller) and their actions.
# Notes: A task's fee is recovered EITHER by withholding it from a COD payout (settled_delivery_charge)
#        OR by a charge invoice (charge_invoice) — never both. billable_tasks() is the single gate.

from decimal import Decimal

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from delivery.charges import BILLABLE_CHARGE
from delivery.models import DeliveryTask
from fleet.models import (
    BusinessChargeInvoice,
    BusinessChargeInvoiceLine,
    BusinessInvoicePayment,
)
from fleet.wallet_service import WalletService


# A completed job is billable whether the customer paid COD or prepaid — the
# fee is earned either way. Same statuses the driver and payout legs use.
BILLABLE_STATUSES = ['delivered', 'partial_delivery']

VALID_KINDS = {k for k, _ in BusinessChargeInvoiceLine.KIND_CHOICES}
KIND_NAMES = dict(BusinessChargeInvoiceLine.KIND_CHOICES)

# What staff may hand-add to an invoice. A delivery charge is never one of them:
# that line has to be tied to a DeliveryTask, or the task stays billable and the
# same job gets charged again on the next invoice.
EDITABLE_KINDS = [(k, v) for k, v in BusinessChargeInvoiceLine.KIND_CHOICES
                  if k != 'delivery_charge']

# Same ceiling the Charges to Collect desk enforces on a typed charge — a figure
# past this is a slipped decimal point, not a delivery.
MAX_LINE_AMOUNT = Decimal('10000')


def billable_tasks(business_id=None, date_from=None, date_to=None,
                   verified_only=False):
    """Deliveries whose charge is still to be collected from the client.

    Excludes anything already recovered the other way — a COD payout that
    withheld a delivery charge, whether it froze the per-task figure or capped
    the line at the COD available. Billing those again would charge the same
    delivery twice.
    """
    qs = DeliveryTask.objects.filter(
        dl_task_status__in=BILLABLE_STATUSES,
        charge_invoice__isnull=True,
        settled_delivery_charge__isnull=True,
    ).exclude(
        cod_client_settle_txn__payout_deductions__kind='delivery_charge'
    ).annotate(fee=BILLABLE_CHARGE).filter(fee__gt=0)

    if business_id:
        qs = qs.filter(order__business_id=business_id)
    if date_from:
        qs = qs.filter(completed_at__date__gte=date_from)
    if date_to:
        qs = qs.filter(completed_at__date__lte=date_to)
    if verified_only:
        qs = qs.filter(charge_verification_status__in=['verified', 'published'])
    return qs


def outstanding_for_business(business_id):
    """(billed, paid, outstanding) across every live invoice for one account."""
    rows = BusinessChargeInvoice.objects.filter(
        business_id=business_id
    ).exclude(status=BusinessChargeInvoice.STATUS_VOID).aggregate(
        billed=Sum('total_amount'), paid=Sum('amount_paid'),
    )
    billed = rows['billed'] or Decimal('0')
    paid = rows['paid'] or Decimal('0')
    return billed, paid, billed - paid


def _clean_extras(extras):
    """Validate hand-added invoice lines into [{kind,label,amount}]."""
    lines = []
    for raw in (extras or []):
        amount = Decimal(str(raw.get('amount') or '0'))
        if amount < 0:
            raise ValueError("Charge amount cannot be negative")
        if amount == 0:
            continue
        kind = raw.get('kind') or 'other_charge'
        if kind not in VALID_KINDS:
            raise ValueError(f"Unknown charge type '{kind}'")
        lines.append({
            'kind': kind,
            'label': (raw.get('label') or KIND_NAMES[kind])[:120],
            'amount': amount,
        })
    return lines


@transaction.atomic
def issue_charge_invoice(business, task_ids=None, extras=None, created_by=None,
                         notes=None, due_date=None):
    """Bill a business for the selected deliveries plus any hand-added lines.

    Every figure is recomputed here from locked rows — a browser-supplied total
    is never trusted. Each task's fee is frozen onto its invoice line, so a later
    edit in Client Charges cannot restate a document already sent to the client.

    Returns ``(invoice, billed_count, skipped_count)``; ``(None, 0, skipped)``
    when nothing was billable.
    """
    # Checked before anything is read: the invoice number is built from the
    # client's own code, so an account without one cannot be numbered at all.
    # Raising here rather than at save() keeps the message about the account
    # instead of about a code generator.
    BusinessChargeInvoice.code_segment_for(business)

    extra_lines = _clean_extras(extras)

    locked = []
    requested = 0
    if task_ids:
        requested = len(set(task_ids))
        locked = list(
            billable_tasks(business_id=business.business_id)
            .filter(id__in=task_ids)
            .select_for_update(of=('self',))
            .select_related('order')
            .order_by('completed_at', 'id')
        )

    skipped = requested - len(locked)
    if not locked and not extra_lines:
        return None, 0, skipped

    task_total = sum((Decimal(str(t.fee)) for t in locked), Decimal('0'))
    extra_total = sum((l['amount'] for l in extra_lines), Decimal('0'))
    total = task_total + extra_total

    dates = [t.completed_at.date() for t in locked if t.completed_at]
    invoice = BusinessChargeInvoice.objects.create(
        business=business,
        period_from=min(dates) if dates else None,
        period_to=max(dates) if dates else None,
        total_amount=total,
        amount_paid=Decimal('0'),
        status=BusinessChargeInvoice.STATUS_ISSUED,
        due_date=due_date,
        notes=notes,
        issued_by=created_by,
    )

    # One revenue row per charge kind, not per delivery — a 300-order invoice
    # would otherwise write 300 ledger rows for a single billed amount. The
    # per-delivery detail lives on the invoice lines.
    delivery_txn = None
    if task_total > 0:
        delivery_txn = WalletService.record_transaction(
            driver=None,
            transaction_type='delivery_charge',
            amount=task_total,
            description=(
                f"Delivery charges billed to {business.business_name} "
                f"on invoice {invoice.invoice_code}"
            ),
            created_by=created_by,
            reference_number=invoice.invoice_code,
            business=business,
        )

    BusinessChargeInvoiceLine.objects.bulk_create([
        BusinessChargeInvoiceLine(
            invoice=invoice,
            delivery_task=t,
            charge_txn=delivery_txn,
            kind='delivery_charge',
            label=(
                f"Delivery {t.order.order_number}" if t.order and t.order.order_number
                else f"Delivery {t.dl_task_number or t.id}"
            )[:120],
            amount=Decimal(str(t.fee)),
        )
        for t in locked
    ], batch_size=500)

    for line in extra_lines:
        charge_txn = WalletService.record_transaction(
            driver=None,
            transaction_type=line['kind'],
            amount=line['amount'],
            description=(
                f"{line['label']} billed to {business.business_name} "
                f"on invoice {invoice.invoice_code}"
            ),
            created_by=created_by,
            reference_number=invoice.invoice_code,
            business=business,
        )
        BusinessChargeInvoiceLine.objects.create(
            invoice=invoice,
            delivery_task=None,
            charge_txn=charge_txn,
            kind=line['kind'],
            label=line['label'],
            amount=line['amount'],
        )

    if locked:
        DeliveryTask.objects.filter(id__in=[t.id for t in locked]).update(
            charge_invoice=invoice
        )

    return invoice, len(locked), skipped


def _resync_invoice_totals(invoice):
    """Restate an invoice's total from its live lines and re-derive its status."""
    total = invoice.lines.aggregate(t=Sum('amount'))['t'] or Decimal('0')
    paid = invoice.amount_paid or Decimal('0')

    invoice.total_amount = total
    if paid <= 0:
        invoice.status = BusinessChargeInvoice.STATUS_ISSUED
    elif total - paid <= 0:
        invoice.status = BusinessChargeInvoice.STATUS_PAID
    else:
        invoice.status = BusinessChargeInvoice.STATUS_PART_PAID
    invoice.save(update_fields=['total_amount', 'status'])
    return invoice


def _assert_editable(invoice):
    """Any invoice that is not void takes line edits.

    A paid invoice included: adding to one restates it to part-paid and the
    client owes the difference, which beats reissuing a document they already
    have. Money already received is still protected — ``remove_invoice_charge_line``
    refuses to drop the total below ``amount_paid``, so a paid invoice can grow
    but never shrink.
    """
    if invoice.status == BusinessChargeInvoice.STATUS_VOID:
        raise ValueError("This invoice is void — nothing can be added to it")


@transaction.atomic
def add_invoice_charge_line(invoice, kind, label, amount, created_by=None):
    """Put another hand-added charge on a live invoice.

    Books its own revenue row, exactly as issuing an extra line does, so the
    ledger and the document stay in step and a later void reverses it cleanly.
    """
    invoice = BusinessChargeInvoice.objects.select_for_update().select_related(
        'business'
    ).get(pk=invoice.pk)
    _assert_editable(invoice)

    if kind not in dict(EDITABLE_KINDS):
        raise ValueError(
            "A delivery charge can only be billed by selecting the delivery on "
            "the Charges to Collect desk"
        )

    cleaned = _clean_extras([{'kind': kind, 'label': label, 'amount': amount}])
    if not cleaned:
        raise ValueError("Enter an amount for the charge")
    line_spec = cleaned[0]

    charge_txn = WalletService.record_transaction(
        driver=None,
        transaction_type=line_spec['kind'],
        amount=line_spec['amount'],
        description=(
            f"{line_spec['label']} billed to {invoice.business.business_name} "
            f"on invoice {invoice.invoice_code}"
        ),
        created_by=created_by,
        reference_number=invoice.invoice_code,
        business=invoice.business,
    )
    line = BusinessChargeInvoiceLine.objects.create(
        invoice=invoice,
        delivery_task=None,
        charge_txn=charge_txn,
        kind=line_spec['kind'],
        label=line_spec['label'],
        amount=line_spec['amount'],
    )

    _resync_invoice_totals(invoice)
    return line, invoice


@transaction.atomic
def remove_invoice_charge_line(invoice, line_id, created_by=None):
    """Take a hand-added charge back off a live invoice.

    The line is deleted rather than flagged, which is what keeps
    ``void_charge_invoice`` correct — it reverses by walking the lines that are
    still there, so a removed line can never be reversed a second time. The
    reversal transaction booked here is the audit trail.
    """
    invoice = BusinessChargeInvoice.objects.select_for_update().select_related(
        'business'
    ).get(pk=invoice.pk)
    _assert_editable(invoice)

    line = invoice.lines.select_related('charge_txn').filter(pk=line_id).first()
    if not line:
        raise ValueError("That charge is not on this invoice")
    if line.delivery_task_id:
        raise ValueError(
            "A billed delivery cannot be taken off on its own — void the invoice "
            "to put its deliveries back on the desk"
        )

    paid = invoice.amount_paid or Decimal('0')
    if (invoice.total_amount or Decimal('0')) - (line.amount or Decimal('0')) < paid:
        raise ValueError(
            f"Removing this line would drop the invoice below the {paid} already "
            f"received against it"
        )

    txn = line.charge_txn
    if txn is not None:
        WalletService.record_transaction(
            driver=None,
            transaction_type=txn.transaction_type,
            amount=-abs(txn.amount),
            description=(
                f"{line.label} reversed for {invoice.business.business_name} "
                f"(removed from invoice {invoice.invoice_code})"
            ),
            created_by=created_by,
            reference_number=invoice.invoice_code,
            business=invoice.business,
        )

    line.delete()
    _resync_invoice_totals(invoice)
    return invoice


@transaction.atomic
def amend_invoice_line_amount(invoice, line_id, amount, created_by=None, reason=None):
    """Correct a mis-keyed amount on a line of an invoice that is already issued.

    Issuing freezes a line so an edit on the Charges to Collect desk cannot
    restate a document the client has been sent — which is right for a real
    repricing and wrong for a fat-fingered figure. This is the one way back in,
    and the view gates it to super admins.

    The revenue row the line was booked on is restated by the same delta rather
    than a second row being written: every delivery line on an invoice shares
    one transaction, and ``void_charge_invoice`` reverses whatever that row says
    at void time, so a correction booked anywhere else would leave the void
    reversing a figure the invoice no longer claims. The delivery's own verified
    charge follows too, so the desk and the document keep saying the same thing.
    """
    invoice = BusinessChargeInvoice.objects.select_for_update().select_related(
        'business'
    ).get(pk=invoice.pk)
    _assert_editable(invoice)

    line = invoice.lines.select_related('charge_txn', 'delivery_task').filter(pk=line_id).first()
    if not line:
        raise ValueError("That charge is not on this invoice")

    new_amount = Decimal(str(amount)).quantize(Decimal('0.01'))
    if new_amount < 0:
        raise ValueError("Charge amount cannot be negative")
    if new_amount > MAX_LINE_AMOUNT:
        raise ValueError(f"Charge looks wrong — over {MAX_LINE_AMOUNT:,.0f} QAR")

    old_amount = line.amount or Decimal('0')
    delta = new_amount - old_amount
    if delta == 0:
        raise ValueError(f"This charge is already {old_amount:.2f} QAR")

    # Mirror how _resync_invoice_totals will restate the invoice, so the guard
    # below tests the total the save is actually about to produce.
    lines_total = invoice.lines.aggregate(t=Sum('amount'))['t'] or Decimal('0')
    projected = lines_total + delta
    paid = invoice.amount_paid or Decimal('0')
    if projected < paid:
        raise ValueError(
            f"That would drop the invoice to {projected:.2f}, below the {paid:.2f} "
            f"already received against it"
        )

    txn = line.charge_txn
    if txn is not None:
        txn.amount = (txn.amount or Decimal('0')) + delta
        txn.description = (
            f"{txn.description.rstrip('.')} (amended by "
            f"{getattr(created_by, 'username', 'staff')})"
        )[:255]
        txn.save(update_fields=['amount', 'description'])

    if line.original_amount is None:
        line.original_amount = old_amount
    line.amount = new_amount
    line.amended_at = timezone.now()
    line.amended_by = created_by
    line.amend_reason = (reason or '')[:255]
    line.save(update_fields=[
        'amount', 'original_amount', 'amended_at', 'amended_by', 'amend_reason',
    ])

    # The task's verified figure is what every other charge screen reads. Left
    # behind, the desk would keep showing the wrong number for a delivery whose
    # invoice has already been corrected.
    task = line.delivery_task
    if task is not None:
        task.verified_delivery_charge = new_amount
        task.save(update_fields=['verified_delivery_charge'])

    _resync_invoice_totals(invoice)
    return line, invoice


@transaction.atomic
def record_invoice_payment(invoice, amount, payment_method='bank', reference=None,
                           received_on=None, notes=None, created_by=None):
    """Record money received against a charge invoice and advance its status."""
    invoice = BusinessChargeInvoice.objects.select_for_update().get(pk=invoice.pk)

    amount = Decimal(str(amount))
    if amount <= 0:
        raise ValueError("Payment amount must be more than zero")
    if invoice.status == BusinessChargeInvoice.STATUS_VOID:
        raise ValueError("This invoice is void — nothing is owed on it")
    if amount > invoice.amount_due:
        raise ValueError(
            f"Payment {amount} is more than the {invoice.amount_due} still due"
        )

    payment_txn = WalletService.record_transaction(
        driver=None,
        transaction_type='client_payment',
        amount=amount,
        description=(
            f"Payment received from {invoice.business.business_name} "
            f"against invoice {invoice.invoice_code}"
        ),
        created_by=created_by,
        reference_number=invoice.invoice_code,
        notes=notes,
        payment_method=payment_method,
        business=invoice.business,
    )

    payment = BusinessInvoicePayment.objects.create(
        invoice=invoice,
        amount=amount,
        payment_method=payment_method,
        reference=reference,
        received_on=received_on or timezone.localdate(),
        notes=notes,
        payment_txn=payment_txn,
        created_by=created_by,
    )

    invoice.amount_paid = (invoice.amount_paid or Decimal('0')) + amount
    invoice.status = (
        BusinessChargeInvoice.STATUS_PAID if invoice.amount_due <= 0
        else BusinessChargeInvoice.STATUS_PART_PAID
    )
    invoice.save(update_fields=['amount_paid', 'status'])
    return payment


@transaction.atomic
def void_charge_invoice(invoice, created_by=None, reason=None):
    """Cancel an issued invoice: unbook its revenue and free its deliveries.

    Refused once any money has been received against it — a paid invoice is
    settled history, and voiding it would strand the payment against a document
    that no longer claims anything.
    """
    invoice = BusinessChargeInvoice.objects.select_for_update().get(pk=invoice.pk)

    if invoice.status == BusinessChargeInvoice.STATUS_VOID:
        raise ValueError("This invoice is already void")
    if (invoice.amount_paid or Decimal('0')) > 0:
        raise ValueError(
            "Payments have been received against this invoice — refund and "
            "remove them before voiding"
        )

    # Reverse each revenue row once. Delivery lines share one transaction, so
    # walking lines without de-duplicating would reverse it many times over.
    seen = set()
    for line in invoice.lines.select_related('charge_txn'):
        txn = line.charge_txn
        if txn is None or txn.id in seen:
            continue
        seen.add(txn.id)
        WalletService.record_transaction(
            driver=None,
            transaction_type=txn.transaction_type,
            amount=-abs(txn.amount),
            description=(
                f"Charges reversed for {invoice.business.business_name} "
                f"(invoice {invoice.invoice_code} voided)"
            ),
            created_by=created_by,
            reference_number=invoice.invoice_code,
            business=invoice.business,
        )

    # The deliveries go back on the desk to be billed again.
    DeliveryTask.objects.filter(charge_invoice=invoice).update(charge_invoice=None)

    invoice.status = BusinessChargeInvoice.STATUS_VOID
    invoice.voided_at = timezone.now()
    invoice.voided_by = created_by
    invoice.void_reason = (reason or '')[:255]
    invoice.save(update_fields=['status', 'voided_at', 'voided_by', 'void_reason'])
    return invoice
