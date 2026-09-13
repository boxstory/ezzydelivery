# Purpose: Seed the P2P rate card with today's live pricing, unchanged.
# Used by: migrate — runs once; re-running is a no-op because it keys on the row shape.
# Notes: These ten rows reproduce webpages/static/webpages/js/p2p-calculator.js exactly (the 25/35/
#        40/55 ladder and the m|l|xl + suv|van|truck quote rule). Prices for the NEW dimensions
#        (box-count ranges, kg refinements, express vs scheduled) are deliberately NOT invented
#        here — ops add those rows in admin once they have decided the numbers.

from django.db import migrations


# (min_boxes, max_boxes, size, up_to_kg, vehicle, speed, up_to_km, price, needs_quote, priority)
SEED_ROWS = [
    # The distance ladder, applying to anything not caught by a quote rule below.
    (1, None, '', None, '', '', 10, 25, False, 0),
    (1, None, '', None, '', '', 20, 35, False, 0),
    (1, None, '', None, '', '', 30, 40, False, 0),
    (1, None, '', None, '', '', None, 55, False, 0),

    # Quote-only overrides. Priority 10 so they beat the ladder regardless of how
    # specific a future ladder row becomes — a bulky item must never fall through
    # to an automatic price just because someone added a narrower distance band.
    (1, None, 'm', None, '', '', None, 0, True, 10),
    (1, None, 'l', None, '', '', None, 0, True, 10),
    (1, None, 'xl', None, '', '', None, 0, True, 10),
    (1, None, '', None, 'suv', '', None, 0, True, 10),
    (1, None, '', None, 'van', '', None, 0, True, 10),
    (1, None, '', None, 'truck', '', None, 0, True, 10),
]


def seed(apps, schema_editor):
    P2PRateBand = apps.get_model('p2p', 'P2PRateBand')
    for (min_b, max_b, size, kg, vehicle, speed, km, price, quote, priority) in SEED_ROWS:
        P2PRateBand.objects.get_or_create(
            min_boxes=min_b, max_boxes=max_b, size=size, up_to_kg=kg,
            vehicle=vehicle, speed=speed, up_to_km=km,
            defaults={
                'price': price,
                'needs_quote': quote,
                'priority': priority,
                'is_active': True,
            },
        )


def unseed(apps, schema_editor):
    """Remove only the rows this migration created, never rows ops added later."""
    P2PRateBand = apps.get_model('p2p', 'P2PRateBand')
    for (min_b, max_b, size, kg, vehicle, speed, km, _p, _q, _pr) in SEED_ROWS:
        P2PRateBand.objects.filter(
            min_boxes=min_b, max_boxes=max_b, size=size, up_to_kg=kg,
            vehicle=vehicle, speed=speed, up_to_km=km,
        ).delete()


class Migration(migrations.Migration):

    dependencies = [('p2p', '0001_initial')]

    operations = [migrations.RunPython(seed, unseed)]
