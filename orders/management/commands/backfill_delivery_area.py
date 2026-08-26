# Purpose: Fill Order.delivery_area_name / delivery_area_source for orders saved before the fields existed.
# Used by: one-off backfill after migration orders/0063; re-run with --all after import_zones,
#          discover_zone_areas, or a zone-area pin move, since stored names are not auto-refreshed.
# Notes: Dry-run by default, like backfill_route_distance. Reads one cached zone-area map and
#        makes no external calls. The default filter is delivery_area_source='' — "never computed" —
#        so a second run over settled data reports 0 rather than re-chewing unresolvable orders.

from django.core.management.base import BaseCommand

from delivery.geo import apply_delivery_area, zone_area_map
from orders.models import Order


class Command(BaseCommand):
    help = "Backfill the stored delivery area name on orders (dry run by default)"

    def add_arguments(self, parser):
        parser.add_argument(
            '--apply', action='store_true',
            help='Write the area names (default is a dry run)',
        )
        parser.add_argument(
            '--business', type=int,
            help='Limit to one business_id',
        )
        parser.add_argument(
            '--all', action='store_true',
            help='Recompute every order, not just those never computed',
        )

    def handle(self, *args, **options):
        apply_changes = options['apply']
        area_map = zone_area_map()

        zones = len(area_map)
        areas = sum(len(v) for v in area_map.values())
        self.stdout.write(f'  zone areas loaded: {areas} across {zones} zone(s)')

        orders = Order.objects.order_by('pk').only(
            'pk', 'dl_zone', 'latitude', 'longitude',
            'delivery_area_name', 'delivery_area_source',
        )
        if options.get('business'):
            orders = orders.filter(business_id=options['business'])
        if not options.get('all'):
            orders = orders.filter(delivery_area_source='')

        total = orders.count()
        self.stdout.write(f'Examining {total} order(s)')

        fields = ['delivery_area_name', 'delivery_area_source']
        changed, by_source = [], {}
        for order in orders.iterator(chunk_size=500):
            if apply_delivery_area(order, area_map):
                changed.append(order)
            by_source[order.delivery_area_source] = \
                by_source.get(order.delivery_area_source, 0) + 1

            if apply_changes and len(changed) >= 500:
                Order.objects.bulk_update(changed, fields, batch_size=500)
                changed = []

        if apply_changes and changed:
            Order.objects.bulk_update(changed, fields, batch_size=500)

        self.stdout.write(f'  nearest area to pin:      {by_source.get("pin", 0)}')
        self.stdout.write(f'  only area in the zone:    {by_source.get("only_area", 0)}')
        self.stdout.write(f'  same as zone (blanked):   {by_source.get("same_as_zone", 0)}')
        self.stdout.write(f'  unresolved (left blank):  {by_source.get("unresolved", 0)}')
        self.stdout.write(self.style.WARNING(
            '  unresolved covers orders with no zone, no pin in a multi-area zone, '
            'and zones that carry no areas at all — data, not a bug.'
        ))
        if apply_changes:
            self.stdout.write(self.style.SUCCESS('Delivery areas written.'))
        else:
            self.stdout.write(self.style.NOTICE('Dry run — re-run with --apply to write.'))
