"""
Purpose: Relabel first-mile pickups that were auto-cancelled after the driver had already collected the goods and the delivery leg then completed.
Used by: one-off staff repair — `python manage.py repair_collected_pickup_cancels [--apply]`; safe to re-run, reports nothing when clean.
Notes: Only touches pickups whose latest delivery task is delivered/partial. Pickups cancelled with a genuinely cancelled order are left alone.
"""

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from delivery import models as delivery_models
from delivery.services.pickup import log_pickup_history

DELIVERED_DL_STATUSES = ['delivered', 'partial_delivery']


class Command(BaseCommand):
    help = "Reopen pickups wrongly cancelled after collection, as handed_off"

    def add_arguments(self, parser):
        parser.add_argument(
            '--apply', action='store_true',
            help='Write the repairs. Without this the command only reports what it would change.',
        )

    def handle(self, *args, **options):
        apply_changes = options['apply']

        candidates = delivery_models.PickupTask.objects.filter(
            status='cancelled', collected_at__isnull=False,
        ).select_related('order', 'driver', 'transfer_to_driver').order_by('id')

        targets = []
        for pickup in candidates:
            task = pickup.order.delivery_task.order_by('-id').first()
            if not task or task.dl_task_status not in DELIVERED_DL_STATUSES:
                continue
            auto_confirm = bool(
                pickup.transfer_to_driver_id
                and not pickup.transfer_confirmed_at
                and task.driver_id == pickup.transfer_to_driver_id
            )
            targets.append((pickup, task, auto_confirm))

        self.stdout.write(f"Scanned {candidates.count()} pickup(s) cancelled after collection.")
        for pickup, task, auto_confirm in targets:
            self.stdout.write(
                f"  #{pickup.pk:<5} {pickup.order.order_number:<28} "
                f"disp={pickup.disposition:<13} dl={task.dl_task_status:<17} "
                f"{'+confirm transfer' if auto_confirm else ''}"
            )

        if not targets:
            self.stdout.write(self.style.SUCCESS("\nNothing to repair."))
            return

        if not apply_changes:
            self.stdout.write(self.style.WARNING(
                f"\nDry run — {len(targets)} pickup(s) would become handed_off. "
                f"Re-run with --apply to write."
            ))
            return

        with transaction.atomic():
            for pickup, task, auto_confirm in targets:
                update_fields = ['status', 'updated_at']
                if auto_confirm:
                    pickup.transfer_confirmed_at = task.updated_at or timezone.now()
                    update_fields.append('transfer_confirmed_at')
                pickup.status = 'handed_off'
                pickup.save(update_fields=update_fields)

                notes = "Corrected: was auto-cancelled after collection; the delivery completed"
                if auto_confirm:
                    notes += f", transfer to {pickup.transfer_to_driver} confirmed"
                log_pickup_history(pickup, 'cancelled', 'handed_off', notes=notes[:255])

        self.stdout.write(self.style.SUCCESS(
            f"\nRepaired {len(targets)} pickup task(s) to handed_off."
        ))
