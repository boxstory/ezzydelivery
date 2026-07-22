# Purpose: One-time cleanup — merge generic "Fulfillment Store" placeholder pickup rows
# Used by: python manage.py consolidate_fulfillment_stores [--apply]
# Notes: Dry-run by default; only businesses with a real warehouse-identity row are merged.

from django.core.management.base import BaseCommand

from business.models import Business, PickupLocation
from warehouse.signals import merge_placeholder_fulfilment_rows


class Command(BaseCommand):
    help = (
        "Merge generic fulfilment placeholder pickup locations (no coords, "
        "'Fulfillment Store' title) into the business's warehouse-identity "
        "'WH: …' row. Dry-run unless --apply is passed."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--apply', action='store_true',
            help='Actually re-point references and retire placeholders.',
        )

    def handle(self, *args, **options):
        apply = options['apply']
        mode = 'APPLY' if apply else 'DRY-RUN'
        self.stdout.write(f"== Fulfilment pickup consolidation ({mode}) ==")

        merged = 0
        unmergeable = []

        businesses = Business.objects.filter(
            pickup_location__is_fulfilment_center=True).distinct()
        for business in businesses:
            fulfil_rows = PickupLocation.objects.filter(
                business=business, is_fulfilment_center=True)
            if fulfil_rows.count() < 2:
                # Single row: nothing to merge. If it's a coordless placeholder whose
                # warehouse FK (or the default warehouse) is known, refresh it in place
                # with the warehouse identity — same row, no re-pointing needed.
                row = fulfil_rows.first()
                if row and row.pickup_status == 'active' and row.pickup_lat is None:
                    from warehouse.models import Warehouse
                    warehouse = row.warehouse or Warehouse.objects.filter(
                        is_default=True, is_active=True).first()
                    if warehouse and warehouse.latitude is not None:
                        self.stdout.write(
                            f"  {business.business_name}: refresh in place "
                            f"'{row.pickup_location_title}' (id={row.pk}) → "
                            f"'WH: {warehouse.name}' + coords"
                        )
                        if apply:
                            row.pickup_location_title = f"WH: {warehouse.name}"
                            row.locality = warehouse.address or warehouse.city or row.locality
                            row.pickup_lat = warehouse.latitude
                            row.pickup_lon = warehouse.longitude
                            row.warehouse = warehouse
                            row.save(update_fields=[
                                'pickup_location_title', 'locality',
                                'pickup_lat', 'pickup_lon', 'warehouse'])
                        merged += 1
                    else:
                        unmergeable.append(
                            f"{business.business_name} (id={business.business_id}): only "
                            f"'{row.pickup_location_title}' — no coords and no usable warehouse"
                        )
                continue

            # Keep the best warehouse-identity row: has coords, prefer warehouse-linked
            keep = fulfil_rows.filter(pickup_lat__isnull=False).order_by(
                '-warehouse__is_default', 'id').first()
            if not keep:
                unmergeable.append(
                    f"{business.business_name} (id={business.business_id}): "
                    f"{fulfil_rows.count()} fulfilment rows but none has coordinates"
                )
                continue

            actions = merge_placeholder_fulfilment_rows(business, keep, apply=apply)
            for line in actions:
                self.stdout.write(f"  {line}")
            merged += len(actions)

        self.stdout.write(f"\n{merged} placeholder row(s) {'merged' if apply else 'would be merged'}.")
        if unmergeable:
            self.stdout.write("\nNeeds attention (no merge target — link the business to a warehouse):")
            for line in unmergeable:
                self.stdout.write(f"  ! {line}")
        if not apply:
            self.stdout.write("\nRe-run with --apply to execute.")
