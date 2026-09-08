"""
Purpose: Repair DeliveryTask rows whose dl_task_status drifted off its real terminal value (task shows 'pending' etc. though it was completed).
Used by: staff ops — `python manage.py repair_task_status_drift [--apply]`; safe to re-run, reports nothing when clean.
Notes: Writes via queryset .update() on purpose — a normal save() would re-fire delivery signals and re-send customer WhatsApp / COD auto-flows for old deliveries.
"""

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from delivery import models as delivery_models
from orders import models as orders_models

import logging

logger = logging.getLogger(__name__)

# A task carrying completed_at must be sitting on one of these.
TERMINAL_STATUSES = {
    'delivered', 'partial_delivery', 'failed', 'rejected', 'cancelled', 'dropsownlost',
}

# Mirrors STATUS_TO_CLIENT in workforce.views.update_task_status
STATUS_TO_CLIENT = {
    'delivered': '2',
    'partial_delivery': '2',
    'failed': 'rejected',
    'rejected': 'rejected',
    'cancelled': '9',
    'dropsownlost': 'rejected',
}


class Command(BaseCommand):
    help = "Repair delivery tasks whose dl_task_status drifted away from their real terminal status"

    def add_arguments(self, parser):
        parser.add_argument(
            '--apply', action='store_true',
            help='Write the repairs. Without this the command only reports what it would change.',
        )
        parser.add_argument(
            '--task', type=str, default='',
            help='Limit to a single dl_task_number.',
        )

    def handle(self, *args, **options):
        apply_changes = options['apply']
        only_task = options['task'].strip()

        # A completed task parked on a non-terminal status is the drift signature.
        drifted = delivery_models.DeliveryTask.objects.filter(
            completed_at__isnull=False,
        ).exclude(
            dl_task_status__in=TERMINAL_STATUSES,
        ).select_related('order').order_by('completed_at')

        if only_task:
            drifted = drifted.filter(dl_task_number=only_task)

        repairs, unresolved = [], []

        for task in drifted:
            point = delivery_models.TaskStatusPoint.objects.filter(
                task=task,
            ).order_by('-created_at', '-id').first()
            history = orders_models.OrderStatusHistory.objects.filter(
                order_id=task.order_id, field_name='dl_task_status',
            ).order_by('-created_at', '-id').first()

            from_point = point.new_status if point else None
            from_history = history.new_value if history else None

            # Only touch a row when both independent trails agree on a terminal
            # status. Anything less is a judgement call for staff, not a script.
            if (from_point and from_point == from_history
                    and from_point in TERMINAL_STATUSES):
                repairs.append((task, from_point))
            else:
                unresolved.append((task, from_point, from_history))

        self.stdout.write(
            f"Scanned {drifted.count()} completed task(s) sitting on a non-terminal status."
        )

        for task, target in repairs:
            self.stdout.write(
                f"  {task.dl_task_number:<28} {task.dl_task_status} → {target}"
            )
        for task, from_point, from_history in unresolved:
            self.stdout.write(self.style.WARNING(
                f"  {task.dl_task_number:<28} SKIPPED — status point={from_point}, "
                f"history={from_history} (no agreement)"
            ))

        if not repairs:
            self.stdout.write(self.style.SUCCESS("Nothing to repair."))
            return

        if not apply_changes:
            self.stdout.write(self.style.WARNING(
                f"\nDry run — {len(repairs)} task(s) would be repaired. Re-run with --apply to write."
            ))
            return

        now = timezone.now()
        with transaction.atomic():
            for task, target in repairs:
                fields = {'dl_task_status': target, 'updated_at': now}
                client_status = STATUS_TO_CLIENT.get(target)
                if client_status:
                    fields['dl_task_status_client'] = client_status
                delivery_models.DeliveryTask.objects.filter(pk=task.pk).update(**fields)
                logger.info(
                    "Repaired task %s status drift: %s → %s",
                    task.dl_task_number, task.dl_task_status, target,
                )

        self.stdout.write(self.style.SUCCESS(f"\nRepaired {len(repairs)} task(s)."))
