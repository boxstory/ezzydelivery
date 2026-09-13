# Purpose: Fill the P2P rate card with every size × vehicle × speed × distance combination.
# Used by: ops, by hand — `python manage.py fill_p2p_rate_card`. Idempotent; safe to re-run.
# Notes: The seed migration deliberately left the new dimensions unpriced. This turns that gap
#        into an explicit row per combination, priced from the table below, so no booking falls
#        through to a catch-all. Edit PRICING and re-run to reprice; ops edits to price/is_active
#        on a generated row survive unless --reprice is passed.

from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from p2p.models import (
    P2PRateBand, P2P_MAX_BOXES, P2P_SIZE_CHOICES, P2P_SMALLEST_FIT, P2P_SPEED_CHOICES,
    P2P_VEHICLE_CHOICES, P2P_VEHICLE_FITS,
)
from p2p.pricing import max_journey_km

# Every generated row carries this priority, which is how the command finds its own
# rows again and how they beat the priority-10 quote guards seeded in migration 0002.
GENERATED_PRIORITY = 20

# --- The price model ------------------------------------------------------
# Additive, so a reader can see where each number came from:
#     price = ladder[distance] + size + vehicle + speed
# The base ladder is today's live pricing (25/35/40/55), unchanged, so an envelope or
# small box on a bike still quotes exactly what the public tier table advertises.
# The last rung closes on the longest journey the calculator will accept rather than on
# no limit: past it there is no bookable job, and a row that says "to infinity" describes
# one. Filled in at run time from max_journey_km() — see _ladder().
LADDER = [
    (Decimal('10'), Decimal('25')),
    (Decimal('20'), Decimal('35')),
    (Decimal('30'), Decimal('40')),
    (None,          Decimal('55')),
]


def _ladder():
    """The ladder with its open top rung closed on the real maximum journey."""
    top = Decimal(max_journey_km())
    return [(top if km is None else km, price) for km, price in LADDER]

# Handling uplift for the bigger boxes. None = never automatic, always a staff quote.
# Bulky was None until 2026-09-10 and is now +50, continuing the steps above it
# (m +10, l +25); it rides on a pickup or bigger, per P2P_VEHICLE_FITS.
SIZE_ADD = {'xs': Decimal('0'), 's': Decimal('0'), 'm': Decimal('10'),
            'l': Decimal('25'), 'xl': Decimal('50')}

# What the vehicle itself costs on top. None = never automatic. Truck was None until
# 2026-09-10 and is now +100 — double the van, which is the step the series was already
# taking (bike 0, car +5, suv +25, van +50).
VEHICLE_ADD = {'bike': Decimal('0'), 'car': Decimal('5'),
               'suv': Decimal('25'), 'van': Decimal('50'), 'truck': Decimal('100')}

# "Any vehicle" is priced as the smallest one that can actually carry the size, not as
# free. Charging nothing for it would open an arbitrage the customer finds immediately:
# skip the vehicle picker and a large box costs 25 QAR less than the SUV it has to go on.
SMALLEST_FIT = P2P_SMALLEST_FIT

# A scheduled job can be routed with the rest of the day's work, so it is cheaper
# than dropping everything for an express run.
SPEED_ADD = {'express': Decimal('0'), 'standard': Decimal('-5')}

# Which vehicles can actually carry each size. Both live in p2p.models now, because
# the staff rate-card matrix reads the same two tables to decide which combinations are
# everyday ones — a second copy here would have been a second thing to keep in step.
FITS = P2P_VEHICLE_FITS

MIN_PRICE = Decimal('20')


def combinations():
    """Every row the card should hold, as (shape_key, defaults) pairs.

    A combination that can be priced gets one row per distance band. One that cannot
    — bulky, a truck, or a box the vehicle will not take — gets a single quote row
    covering every distance, because a quote does not get cheaper for being nearby.

    No row is open-ended: both ceilings close on the real limits of a bookable job
    (P2P_MAX_BOXES, max_journey_km()).
    """
    vehicles = [''] + [slug for slug, _ in P2P_VEHICLE_CHOICES]
    for size, _ in P2P_SIZE_CHOICES:
        for vehicle in vehicles:
            for speed, _ in P2P_SPEED_CHOICES:
                charged_as = SMALLEST_FIT[size] if vehicle == '' else vehicle
                priceable = (
                    SIZE_ADD[size] is not None
                    and charged_as is not None
                    and VEHICLE_ADD[charged_as] is not None
                    and vehicle in FITS[size]
                )
                if not priceable:
                    yield (
                        {'min_boxes': 1, 'max_boxes': P2P_MAX_BOXES, 'size': size,
                         'up_to_kg': None, 'vehicle': vehicle, 'speed': speed,
                         'up_to_km': Decimal(max_journey_km())},
                        {'price': Decimal('0'), 'needs_quote': True},
                    )
                    continue
                for up_to_km, base in _ladder():
                    price = base + SIZE_ADD[size] + VEHICLE_ADD[charged_as] + SPEED_ADD[speed]
                    yield (
                        {'min_boxes': 1, 'max_boxes': P2P_MAX_BOXES, 'size': size,
                         'up_to_kg': None, 'vehicle': vehicle, 'speed': speed,
                         'up_to_km': up_to_km},
                        {'price': max(price, MIN_PRICE), 'needs_quote': False},
                    )


class Command(BaseCommand):
    help = "Fill the P2P rate card with a row for every size/vehicle/speed/distance combination."

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run', action='store_true',
            help="Print what would change and write nothing.")
        parser.add_argument(
            '--reprice', action='store_true',
            help="Also overwrite the price on rows that already exist. Off by default so "
                 "an ops price change is not undone by a re-run.")
        parser.add_argument(
            '--clear', action='store_true',
            help="Delete every generated row instead of writing any. Leaves the seeded "
                 "ladder and quote guards alone.")

    @transaction.atomic
    def handle(self, *args, **options):
        dry = options['dry_run']

        if options['clear']:
            qs = P2PRateBand.objects.filter(priority=GENERATED_PRIORITY)
            count = qs.count()
            if not dry:
                qs.delete()
            self.stdout.write(self.style.WARNING(
                f"{'Would delete' if dry else 'Deleted'} {count} generated row(s)."))
            return

        created = updated = unchanged = 0
        for key, defaults in combinations():
            row = P2PRateBand.objects.filter(**key).first()
            if row is None:
                created += 1
                if not dry:
                    P2PRateBand.objects.create(
                        **key, **defaults, priority=GENERATED_PRIORITY, is_active=True)
                continue
            changes = {}
            if row.priority != GENERATED_PRIORITY:
                changes['priority'] = GENERATED_PRIORITY
            if row.needs_quote != defaults['needs_quote']:
                changes['needs_quote'] = defaults['needs_quote']
            if options['reprice'] and row.price != defaults['price']:
                changes['price'] = defaults['price']
            if changes:
                updated += 1
                if not dry:
                    for field, value in changes.items():
                        setattr(row, field, value)
                    row.save(update_fields=list(changes) + ['updated_at'])
            else:
                unchanged += 1

        verb = 'Would create' if dry else 'Created'
        self.stdout.write(self.style.SUCCESS(
            f"{verb} {created}, updated {updated}, unchanged {unchanged}. "
            f"Card now holds {P2PRateBand.objects.count()} row(s)."))
        if dry:
            transaction.set_rollback(True)
