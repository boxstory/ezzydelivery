# Purpose: Fill Order.route_distance_km / route_distance_exact for orders saved before the field existed.
# Used by: one-off backfill after migration orders/0056; safe to re-run.
# Notes: Dry-run by default, like the other COD/ledger backfills. Distances are straight-line, not road distance.

from django.core.management.base import BaseCommand

from delivery.geo import apply_route_distance, zone_coord_map
from orders.models import Order


class Command(BaseCommand):
    help = "Backfill the stored pickup→drop distance on orders (dry run by default)"

    def add_arguments(self, parser):
        parser.add_argument(
            '--apply', action='store_true',
            help='Write the distances (default is a dry run)',
        )
        parser.add_argument(
            '--business', type=int,
            help='Limit to one business_id',
        )
        parser.add_argument(
            '--all', action='store_true',
            help='Recompute every order, not just those with no distance yet',
        )
        parser.add_argument(
            '--no-routing', action='store_true',
            help='Skip OSRM and store straight-line distances only',
        )

    def handle(self, *args, **options):
        apply_changes = options['apply']
        use_routing = not options.get('no_routing')
        zone_coords = zone_coord_map()

        if use_routing:
            from delivery.routing import health
            ok, detail = health()
            self.stdout.write(('  routing: ' + detail) if ok
                              else self.style.WARNING('  routing unavailable — ' + detail))
            use_routing = ok

        orders = Order.objects.select_related('pickup_location').order_by('pk')
        if options.get('business'):
            orders = orders.filter(business_id=options['business'])
        if not options.get('all'):
            orders = orders.filter(route_distance_km__isnull=True)

        total = orders.count()
        self.stdout.write(f'Examining {total} order(s)')

        fields = ['route_distance_km', 'route_distance_exact', 'route_distance_source']
        changed, by_source, unlocatable = [], {}, 0
        for order in orders.iterator(chunk_size=500):
            if apply_route_distance(order, zone_coords, use_routing=use_routing):
                changed.append(order)
            if order.route_distance_km is None:
                unlocatable += 1
            else:
                by_source[order.route_distance_source] = \
                    by_source.get(order.route_distance_source, 0) + 1

            if apply_changes and len(changed) >= 500:
                Order.objects.bulk_update(changed, fields, batch_size=500)
                changed = []

        if apply_changes and changed:
            Order.objects.bulk_update(changed, fields, batch_size=500)

        self.stdout.write(f'  road distance (OSRM):     {by_source.get("osrm", 0)}')
        self.stdout.write(f'  straight line:            {by_source.get("straight_line", 0)}')
        self.stdout.write(f'  zone estimate:            {by_source.get("zone_estimate", 0)}')
        self.stdout.write(f'  unlocatable (left null):  {unlocatable}')
        if apply_changes:
            self.stdout.write(self.style.SUCCESS('Distances written.'))
        else:
            self.stdout.write(self.style.NOTICE('Dry run — re-run with --apply to write.'))
