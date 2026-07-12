# Purpose: Backfill missing cod_collection transactions for partial deliveries whose
#          COD was collected before the partial-delivery wallet recording was added.
# Used by: One-off staff run — `python manage.py backfill_partial_cod [--apply]`
# Notes:   Dry-run by default. Balance-neutral: already-settled tasks also get an
#          offsetting cod_deposit so driver cod_in_hand is unchanged. Idempotent.

from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import F

from delivery.models import DeliveryTask
from fleet.models import Driver, DriverTransaction
from fleet.wallet_service import WalletService


class Command(BaseCommand):
    help = "Backfill cod_collection transactions for partial deliveries missing them."

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true',
                            help='Commit changes (default is a dry run).')
        parser.add_argument('--default-method', default='cash',
                            choices=['cash', 'pos', 'fawran'],
                            help='Payment method to use when a task has none recorded.')

    def handle(self, *args, **opts):
        apply = opts['apply']
        default_method = opts['default_method']

        # Tasks already carrying a cod_collection transaction are skipped (idempotent)
        recorded_ids = set(
            DriverTransaction.objects.filter(
                transaction_type='cod_collection', delivery_task__isnull=False
            ).values_list('delivery_task_id', flat=True)
        )

        candidates = DeliveryTask.objects.filter(
            dl_task_status='partial_delivery',
            cod_collected=True,
            cod_collected_amount__gt=0,
        ).select_related('order', 'driver', 'cod_submission_txn')

        targets = [t for t in candidates if t.id not in recorded_ids]

        self.stdout.write(f"Found {len(targets)} partial deliveries missing a COD collection.")
        if not targets:
            return

        total_collected = Decimal('0')
        for t in targets:
            if not t.driver_id:
                self.stdout.write(self.style.WARNING(
                    f"  SKIP task {t.id} ({_num(t)}) — no driver linked."))
                continue

            amount = Decimal(str(t.cod_collected_amount))
            method = t.payment_method if t.payment_method in ('cash', 'pos', 'fawran') else default_method
            deposit_method = (t.cod_submission_txn.payment_method
                              if t.cod_submission_txn and t.cod_submission_txn.payment_method else 'cash')
            settled = t.cod_settled

            if settled:
                fold = f" [settled → fold into deposit #{t.cod_submission_txn_id}]" if t.cod_submission_txn_id else " [settled → +offset deposit]"
            else:
                fold = ""
            line = f"  task {t.id} ({_num(t)}) — {amount} via {method}{fold}"
            self.stdout.write(line)
            total_collected += amount

            if not apply:
                continue

            with transaction.atomic():
                # Ensure the task carries the method so reports/breakdowns attribute it
                if t.payment_method not in ('cash', 'pos', 'fawran'):
                    t.payment_method = method
                    t.payment_split = {method: float(amount)}
                    t.save(update_fields=['payment_method', 'payment_split'])

                coll = WalletService.record_transaction(
                    driver=t.driver,
                    transaction_type='cod_collection',
                    amount=amount,
                    description=f"COD collected for order {_num(t)} (partial delivery)",
                    delivery_task=t,
                    payment_method=method,
                    notes='[backfill] partial-delivery COD collection',
                )
                _backdate(coll, t.cod_collected_at)

                if settled and t.cod_submission_txn_id:
                    # Already deposited — fold the amount into the existing deposit so
                    # the report keeps a single deposit line (not one per task), and
                    # mirror the deposit's effect so cod_in_hand stays unchanged.
                    sub = DriverTransaction.objects.select_for_update().get(pk=t.cod_submission_txn_id)
                    sub.amount = (sub.amount or Decimal('0')) + amount
                    sub.notes = (sub.notes or '') + f" | [backfill] +{amount} partial COD ({_num(t)})"
                    sub.save(update_fields=['amount', 'notes'])
                    Driver.objects.filter(pk=t.driver_id).update(cod_in_hand=F('cod_in_hand') - amount)
                elif settled:
                    # Settled but with no linked deposit — record a standalone offset.
                    dep = WalletService.record_transaction(
                        driver=t.driver,
                        transaction_type='cod_deposit',
                        amount=amount,
                        description=f"COD deposit for order {_num(t)} (already settled)",
                        delivery_task=t,
                        payment_method=deposit_method,
                        notes='[backfill] offset — COD already settled to admin',
                    )
                    _backdate(dep, t.cod_settled_at)

        verb = "Recorded" if apply else "Would record"
        self.stdout.write(self.style.SUCCESS(
            f"\n{verb} {len(targets)} collection(s), total {total_collected} QAR."))
        if not apply:
            self.stdout.write("Dry run — re-run with --apply to commit.")


def _num(task):
    return task.order.order_number if task.order else f"task#{task.id}"


def _backdate(txn, when):
    """created_at is auto_now_add, so override it after creation for accurate dating."""
    if when:
        DriverTransaction.objects.filter(pk=txn.pk).update(created_at=when)
