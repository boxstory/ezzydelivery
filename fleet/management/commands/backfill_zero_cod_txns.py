"""
Purpose: Create the missing 0 QAR cod_collection ledger row for delivered zero-COD tasks.
Used by: one-off/periodic staff run — `python manage.py backfill_zero_cod_txns [--apply]`.
Notes: Zero-COD deliveries never recorded a transaction, so staff had nothing to attach the
       delivery fee to when billing the client. Rows carry 0 QAR so no wallet balance moves.
"""

from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db.models import Q

from delivery import models as delivery_models
from fleet import models as fleet_models
from fleet.wallet_service import WalletService


class Command(BaseCommand):
    help = "Create 0 QAR cod_collection transactions for delivered zero-COD tasks that have none."

    def add_arguments(self, parser):
        parser.add_argument(
            '--apply', action='store_true',
            help="Write the transactions. Without this the command only reports what it would create.",
        )
        parser.add_argument(
            '--driver', type=str, default=None,
            help="Limit to one driver code (e.g. ezzy.dr001).",
        )

    def handle(self, *args, **options):
        apply_changes = options['apply']

        tasks = delivery_models.DeliveryTask.objects.filter(
            dl_task_status__in=['delivered', 'partial_delivery'],
            driver__isnull=False,
        ).filter(
            Q(order__cod_amount=0) | Q(order__cod_amount__isnull=True)
        ).exclude(
            id__in=fleet_models.DriverTransaction.objects.filter(
                transaction_type='cod_collection', delivery_task__isnull=False,
            ).values_list('delivery_task_id', flat=True)
        ).select_related('order', 'driver').order_by('completed_at')

        if options['driver']:
            tasks = tasks.filter(driver__driver_code=options['driver'])

        total = tasks.count()
        if not total:
            self.stdout.write(self.style.SUCCESS("Nothing to backfill — every delivered zero-COD task already has a ledger row."))
            return

        by_driver = {}
        for task in tasks:
            by_driver[str(task.driver)] = by_driver.get(str(task.driver), 0) + 1

        self.stdout.write(f"{total} delivered zero-COD task(s) without a cod_collection row:")
        for driver_label, count in sorted(by_driver.items(), key=lambda kv: -kv[1]):
            self.stdout.write(f"  {driver_label:24} {count}")

        if not apply_changes:
            self.stdout.write(self.style.WARNING("\nDry run — nothing written. Re-run with --apply to create these rows."))
            return

        created = 0
        for task in tasks.iterator():
            order_number = task.order.order_number if task.order else task.dl_task_number
            WalletService.record_transaction(
                driver=task.driver,
                transaction_type='cod_collection',
                amount=Decimal('0'),
                description=f"Zero COD for order {order_number} (prepaid / no cash due)",
                notes="Backfilled — no cash collected; row exists so the delivery fee can be billed to the client.",
                delivery_task=task,
                payment_method=task.payment_method or None,
            )
            created += 1

        self.stdout.write(self.style.SUCCESS(f"Created {created} zero-COD transaction(s)."))
