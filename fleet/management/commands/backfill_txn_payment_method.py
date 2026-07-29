"""
Purpose: Fill in DriverTransaction.payment_method on COD rows that were written without one, using the linked task.
Used by: manual run — `python manage.py backfill_txn_payment_method [--apply]`
Notes: Dry-run by default. Reads already prefer the task's method, so this changes grouping/exports only, never a balance.
"""
from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Count

from fleet import models as fleet_models


class Command(BaseCommand):
    help = ("Backfill payment_method on COD transactions that have none, "
            "copying it from the delivery task. Dry-run unless --apply.")

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true',
                            help='Write the changes. Without this the command only reports.')

    def handle(self, *args, **options):
        rows = fleet_models.DriverTransaction.objects.filter(
            transaction_type='cod_collection',
            payment_method__isnull=True,
            delivery_task__isnull=False,
        ).exclude(
            delivery_task__payment_method='',
        ).select_related('delivery_task')

        by_method = {}
        fixable = []
        for txn in rows:
            method = txn.delivery_task.payment_method
            if not method:
                continue
            fixable.append((txn, method))
            by_method[method] = by_method.get(method, 0) + 1

        orphans = fleet_models.DriverTransaction.objects.filter(
            transaction_type='cod_collection', payment_method__isnull=True,
        ).count() - len(fixable)

        self.stdout.write(self.style.MIGRATE_HEADING(
            f'\nRows that can be filled from their task: {len(fixable)}'))
        for method, count in sorted(by_method.items(), key=lambda kv: -kv[1]):
            self.stdout.write(f'  -> {method}: {count}')
        self.stdout.write(
            f'\nLeft null (no task, or task has no method either): {orphans}')

        if not options['apply']:
            self.stdout.write(self.style.WARNING(
                '\nDRY RUN — nothing written. Re-run with --apply to commit.'))
            return

        with transaction.atomic():
            for txn, method in fixable:
                txn.payment_method = method
            fleet_models.DriverTransaction.objects.bulk_update(
                [t for t, _ in fixable], ['payment_method'], batch_size=500)

        self.stdout.write(self.style.SUCCESS(
            f'\nAPPLIED — {len(fixable)} transaction(s) given a payment method.'))
