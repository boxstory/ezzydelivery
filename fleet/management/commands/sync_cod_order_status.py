"""
Purpose: Reconcile Order.cod_status_by_staff with the driver-leg truth on the delivery task.
Used by: manual run — `python manage.py sync_cod_order_status [--apply] [--include-reverse]`
Notes: Dry-run by default. Only ever touches the DRIVER leg; cod_settled_with_business rows and
       the client/business payout (Leg 3) are never modified.
"""
from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Sum

from delivery import models as delivery_models
from orders import models as orders_models


class Command(BaseCommand):
    help = ("Align Order.cod_status_by_staff with whether the driver leg is "
            "actually settled. Dry-run unless --apply is passed.")

    def add_arguments(self, parser):
        parser.add_argument(
            '--apply', action='store_true',
            help='Write the changes. Without this the command only reports.',
        )
        parser.add_argument(
            '--include-reverse', action='store_true',
            help='Also fix the reverse drift (order says with-Ezzy while the '
                 'driver leg is still open). Off by default because it moves a '
                 'status backwards.',
        )

    def handle(self, *args, **options):
        apply_changes = options['apply']
        include_reverse = options['include_reverse']

        # Driver leg is done but the order still says the cash sits with the
        # driver. cod_with_ezzy is the correct intermediate state: out of the
        # driver's hands, not yet paid out to the business.
        forward = delivery_models.DeliveryTask.objects.filter(
            cod_collected=True, cod_settled=True,
            order__cod_status_by_staff='cod_with_driver',
        ).select_related('order')

        # Reverse drift: the order claims Ezzy holds the money but the driver
        # never settled it.
        reverse = delivery_models.DeliveryTask.objects.filter(
            cod_collected=True, cod_settled=False,
            order__cod_status_by_staff='cod_with_ezzy',
        ).select_related('order')

        self._report('driver leg settled -> cod_with_ezzy', forward)
        self._report('driver leg still open -> cod_with_driver', reverse,
                     skipped=not include_reverse)

        if not apply_changes:
            self.stdout.write(self.style.WARNING(
                '\nDRY RUN — nothing written. Re-run with --apply to commit.'))
            return

        with transaction.atomic():
            forward_ids = [t.order_id for t in forward if t.order_id]
            changed = orders_models.Order.objects.filter(
                id__in=forward_ids, cod_status_by_staff='cod_with_driver',
            ).update(cod_status_by_staff='cod_with_ezzy') if forward_ids else 0

            reverse_changed = 0
            if include_reverse:
                reverse_ids = [t.order_id for t in reverse if t.order_id]
                if reverse_ids:
                    reverse_changed = orders_models.Order.objects.filter(
                        id__in=reverse_ids, cod_status_by_staff='cod_with_ezzy',
                    ).update(cod_status_by_staff='cod_with_driver')

        self.stdout.write(self.style.SUCCESS(
            f'\nAPPLIED — {changed} order(s) -> cod_with_ezzy'
            + (f', {reverse_changed} order(s) -> cod_with_driver' if include_reverse else '')))

    def _report(self, label, qs, skipped=False):
        total = qs.aggregate(s=Sum('cod_collected_amount'))['s'] or 0
        count = qs.count()
        head = f'\n{label}: {count} task(s), {total} QAR'
        self.stdout.write(self.style.MIGRATE_HEADING(head))
        if skipped:
            self.stdout.write('  (skipped — pass --include-reverse to act on these)')
        for task in qs.order_by('cod_settled_at', 'pk')[:100]:
            self.stdout.write(
                f'  task {task.id} {task.dl_task_number or "-"} '
                f'{task.payment_method or "cash":7s} {task.cod_collected_amount} QAR '
                f'order {task.order.order_number if task.order else "-"}'
            )
        if count > 100:
            self.stdout.write(f'  ... and {count - 100} more')
