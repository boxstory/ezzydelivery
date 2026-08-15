"""
Purpose: Close first-mile pickups left claimable in the driver pool after their order or delivery leg already ended (cancelled/delivered).
Used by: staff ops — `python manage.py repair_stale_pickup_tasks [--apply]`; safe to re-run, reports nothing when clean.
Notes: Also reports (never edits) orders whose latest delivery task is cancelled while the order row is not — that split is a staff judgement call.
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from delivery import models as delivery_models
from delivery.selectors import TERMINAL_DL_STATUSES, TERMINAL_ORDER_STATUSES
from delivery.services.pickup import cancel_pickup_for_order
from orders import models as orders_models

# Pickups that have not been executed yet — these are the ones worth closing.
# 'collected'/'dropped'/'handed_off' mean the driver already did the work.
OPEN_PICKUP_STATUSES = ['pending', 'accepted', 'in_progress', 'arrived']


class Command(BaseCommand):
    help = "Cancel pickup tasks whose order/delivery leg already ended"

    def add_arguments(self, parser):
        parser.add_argument(
            '--apply', action='store_true',
            help='Write the repairs. Without this the command only reports what it would change.',
        )

    def _latest_dl_status(self, order):
        task = order.delivery_task.order_by('-id').first()
        return task.dl_task_status if task else None

    def handle(self, *args, **options):
        apply_changes = options['apply']

        stale = []
        candidates = delivery_models.PickupTask.objects.filter(
            status__in=OPEN_PICKUP_STATUSES,
        ).select_related('order', 'business').order_by('id')

        for pickup in candidates:
            order = pickup.order
            latest_dl = self._latest_dl_status(order)
            if (order.order_status in TERMINAL_ORDER_STATUSES
                    or latest_dl in TERMINAL_DL_STATUSES):
                stale.append((pickup, latest_dl))

        self.stdout.write(f"Scanned {candidates.count()} open pickup task(s).")

        for pickup, latest_dl in stale:
            self.stdout.write(
                f"  #{pickup.pk:<5} {pickup.order.order_number:<28} "
                f"pickup={pickup.status:<12} order={pickup.order.order_status:<10} "
                f"dl={latest_dl or '—'}"
            )

        # Advisory: order row and its delivery task disagree. Reported only — flipping
        # order_status has COD/payout side effects, so staff decide case by case.
        split = []
        for order in orders_models.Order.objects.exclude(
            order_status='cancelled',
        ).filter(delivery_task__dl_task_status='cancelled').distinct().order_by('id'):
            if self._latest_dl_status(order) == 'cancelled':
                split.append(order)

        if split:
            self.stdout.write(self.style.WARNING(
                f"\n{len(split)} order(s) whose latest delivery task is cancelled but the "
                f"order is not — review manually, NOT changed by this command:"
            ))
            for order in split:
                self.stdout.write(self.style.WARNING(
                    f"  #{order.pk:<5} {order.order_number:<28} order={order.order_status}"
                ))

        if not stale:
            self.stdout.write(self.style.SUCCESS("\nNo stale pickup tasks."))
            return

        if not apply_changes:
            self.stdout.write(self.style.WARNING(
                f"\nDry run — {len(stale)} pickup(s) would be cancelled. "
                f"Re-run with --apply to write."
            ))
            return

        with transaction.atomic():
            for pickup, latest_dl in stale:
                if pickup.order.order_status == 'cancelled':
                    reason = 'Order was cancelled'
                elif pickup.order.order_status == 'delivered' or latest_dl in ('delivered', 'partial_delivery'):
                    reason = 'Order was delivered without a first-mile pickup'
                else:
                    reason = 'Delivery task was cancelled'
                cancel_pickup_for_order(pickup.order, reason=reason)

        self.stdout.write(self.style.SUCCESS(f"\nCancelled {len(stale)} pickup task(s)."))
