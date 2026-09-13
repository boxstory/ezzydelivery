"""
Purpose: Drop the duplicated business code from shipping label numbers written before 2026-09-10 (LBL-MVA124-MVA124-5850-AB785-DCD323 -> LBL-MVA124-5850-AB785-DCD323).
Used by: one-off staff repair — `python manage.py shorten_label_numbers [--apply]`; safe to re-run, reports nothing when clean.
Notes: The order number already opens with the business code, so only the added prefix is removed — the tail printed on the label image and the barcode (order.order_number) are untouched.
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from delivery import models as delivery_models


class Command(BaseCommand):
    help = "Remove the repeated business code from existing shipping label numbers"

    def add_arguments(self, parser):
        parser.add_argument(
            '--apply', action='store_true',
            help='Write the repairs. Without this the command only reports what it would change.',
        )

    def handle(self, *args, **options):
        apply_changes = options['apply']

        labels = delivery_models.ShippingLabel.objects.select_related(
            'order', 'order__business').order_by('id')

        targets, collisions = [], []
        for label in labels:
            business = getattr(label.order, 'business', None)
            code = getattr(business, 'business_code', None)
            if not code or not label.label_number:
                continue
            doubled = f"LBL-{code}-{code}-"
            if not label.label_number.startswith(doubled):
                continue
            new_number = f"LBL-{code}-" + label.label_number[len(doubled):]
            if delivery_models.ShippingLabel.objects.filter(
                    label_number=new_number).exclude(pk=label.pk).exists():
                collisions.append((label, new_number))
                continue
            targets.append((label, new_number))

        self.stdout.write(f"Scanned {labels.count()} shipping label(s).")
        if not targets and not collisions:
            self.stdout.write(self.style.SUCCESS("Nothing to shorten — all label numbers are clean."))
            return

        for label, new_number in targets:
            self.stdout.write(f"  {label.label_number}  ->  {new_number}")
        for label, new_number in collisions:
            self.stdout.write(self.style.WARNING(
                f"  SKIP {label.label_number} — {new_number} is already taken"))

        if not apply_changes:
            self.stdout.write(self.style.WARNING(
                f"\nDry run — {len(targets)} label(s) would be shortened. "
                f"Re-run with --apply to write."))
            return

        with transaction.atomic():
            for label, new_number in targets:
                label.label_number = new_number
                label.save(update_fields=['label_number', 'updated_at'])

        self.stdout.write(self.style.SUCCESS(f"\nShortened {len(targets)} label number(s)."))
