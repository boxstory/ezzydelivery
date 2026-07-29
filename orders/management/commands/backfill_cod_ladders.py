"""
Purpose: Bring both COD status ladders on existing orders in line with reality — fill the never-set operational status and derive the seller-facing one from it.
Used by: manual run — `python manage.py backfill_cod_ladders [--apply]`
Notes: Dry-run by default. Touches status labels only; no amount, balance or settlement flag is read or written.
"""
from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Count, Q

from orders import models as orders_models
from orders.cod_status import client_status_for, CLIENT_STATES_NOT_DERIVED


class Command(BaseCommand):
    help = ("Fill null cod_status_by_staff on COD orders and derive "
            "cod_status_by_client from it. Dry-run unless --apply.")

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true',
                            help='Write the changes. Without this the command only reports.')

    def handle(self, *args, **options):
        cod_orders = orders_models.Order.objects.filter(cod_amount__gt=0)

        # 1. Orders that never got an operational status. "Not collected" is the
        #    honest starting state; null reads as "nobody has looked at this".
        #    Only safe where no COD has actually been taken.
        unset = cod_orders.filter(
            Q(cod_status_by_staff__isnull=True) | Q(cod_status_by_staff='')
        ).exclude(
            delivery_task__cod_collected=True
        ).distinct()
        unset_ids = list(unset.values_list('id', flat=True))
        self.stdout.write(self.style.MIGRATE_HEADING(
            f'\n1. Never-set operational status -> not_collected: {len(unset_ids)} order(s)'))

        # Anything with a collection but no status is a real inconsistency and is
        # reported rather than guessed at.
        stranded = cod_orders.filter(
            Q(cod_status_by_staff__isnull=True) | Q(cod_status_by_staff='')
        ).filter(delivery_task__cod_collected=True).distinct()
        if stranded.exists():
            self.stdout.write(self.style.WARNING(
                f'   {stranded.count()} order(s) HAVE a collection but no status — '
                f'left alone, needs a look: '
                + ', '.join(stranded.values_list('order_number', flat=True)[:10])))

        # 2. Seller-facing ladder derived from the operational one.
        client_changes = {}
        to_update = []
        for order in cod_orders.exclude(
            cod_status_by_client__in=CLIENT_STATES_NOT_DERIVED
        ).only('id', 'cod_status_by_staff', 'cod_status_by_client').iterator():
            staff = order.cod_status_by_staff
            if not staff and order.id in set(unset_ids):
                staff = 'not_collected'
            target = client_status_for(staff, order.cod_status_by_client)
            if target and target != order.cod_status_by_client:
                key = f'{order.cod_status_by_client or "(null)"} -> {target}'
                client_changes[key] = client_changes.get(key, 0) + 1
                order.cod_status_by_client = target
                to_update.append(order)

        self.stdout.write(self.style.MIGRATE_HEADING(
            f'\n2. Seller-facing status derived: {len(to_update)} order(s)'))
        for key, count in sorted(client_changes.items(), key=lambda kv: -kv[1]):
            self.stdout.write(f'   {key}: {count}')

        skipped = cod_orders.filter(
            cod_status_by_client__in=CLIENT_STATES_NOT_DERIVED).count()
        self.stdout.write(f'\n   Left untouched (prepaid / non-COD): {skipped}')

        if not options['apply']:
            self.stdout.write(self.style.WARNING(
                '\nDRY RUN — nothing written. Re-run with --apply to commit.'))
            return

        with transaction.atomic():
            if unset_ids:
                orders_models.Order.objects.filter(id__in=unset_ids).update(
                    cod_status_by_staff='not_collected')
            if to_update:
                orders_models.Order.objects.bulk_update(
                    to_update, ['cod_status_by_client'], batch_size=500)

        self.stdout.write(self.style.SUCCESS(
            f'\nAPPLIED — {len(unset_ids)} operational, {len(to_update)} seller-facing.'))
