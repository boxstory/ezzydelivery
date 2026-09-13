# Purpose: Renumber existing charge invoices from INVC-YYYYMMDD-NNNN to INV-{business code}-YYMM-NNNN.
# Used by: one-off data migration; new invoices are numbered by BusinessChargeInvoice._generate_invoice_code.
# Notes: Ledger rows carry the invoice code in reference_number, so they are rewritten in step or they
#        would point at a code that no longer exists. Anything without a business code is left alone.

from django.db import migrations
from django.utils import timezone


def _segment(code):
    cleaned = ''.join(ch for ch in (code or '').strip().upper() if ch.isalnum())
    return cleaned[:16]


def renumber(apps, schema_editor):
    Invoice = apps.get_model('fleet', 'BusinessChargeInvoice')
    Txn = apps.get_model('fleet', 'DriverTransaction')

    seq_by_prefix = {}
    for inv in Invoice.objects.select_related('business').order_by('issued_at', 'id'):
        if not inv.invoice_code.startswith('INVC-'):
            continue
        segment = _segment(getattr(inv.business, 'business_code', ''))
        if not segment:
            # No code, no number to build — left on its old code rather than
            # given one that names nobody.
            continue

        # Qatar time, not UTC: an invoice issued at 21:30 on the 31st belongs to
        # the month the office was in when it went out.
        stamp = timezone.localtime(inv.issued_at).strftime('%y%m')
        prefix = f"INV-{segment}-{stamp}-"
        seq = seq_by_prefix.get(prefix)
        if seq is None:
            seq = Invoice.objects.filter(invoice_code__startswith=prefix).count()
        seq += 1
        seq_by_prefix[prefix] = seq

        old_code, new_code = inv.invoice_code, f"{prefix}{seq:04d}"
        Txn.objects.filter(reference_number=old_code).update(reference_number=new_code)
        inv.invoice_code = new_code
        inv.save(update_fields=['invoice_code'])


def unrenumber(apps, schema_editor):
    """Nothing to put back: the old codes are not recoverable from the new ones."""
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('fleet', '0041_businesschargeinvoiceline_amend_reason_and_more'),
    ]

    operations = [
        migrations.RunPython(renumber, unrenumber),
    ]
