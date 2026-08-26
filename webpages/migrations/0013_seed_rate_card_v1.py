# Purpose: Seed the active rate card — the volume x distance matrix plus the adjustment rules.
# Used by: webpages.pricing.engine, which reads whichever rate card is active.
# Notes: Idempotent on (ruleset, dimension, label) and fills defaults ONLY on create, so a rate the
#        sales desk edits in admin is never overwritten by a later deploy. The matrix supersedes the
#        FAQ copy at client_faq_100.html:260-275, which had the volume tiers inverted.

from django.db import migrations


RULESET = {
    'code': 'rate_card_v1',
    'name': 'Rate card v1',
    'notes': ('Volume x distance matrix. Price falls as volume rises in every distance band. '
              'Supersedes the inverted slabs still published on the FAQ and pricing pages. '
              'Over 30 km is deliberately absent — no published rate exists, so the engine '
              'flags those leads for manual pricing rather than inventing one.'),
    'is_active': True,
    'base_price_default': 25,
    'min_price_floor': 15,
    'floor_basis': 'config',
    'rounding_step': 1,
    'rounding_mode': 'nearest',
    'max_total_discount_pct': 40,
    'max_total_uplift_pct': 60,
}

# Volume tiers, in monthly orders. The form's "101-300" band has a midpoint of
# 200.5 and therefore lands in Mid — the tier boundary at 150 falls inside that
# band, and the midpoint is what resolves it.
LOW, MID, HIGH = (None, 150), (150, 1300), (1300, None)

# Distance bands, in km, matched against the midpoints in bands.DISTANCE_MIDPOINT
# (5 / 12.5 / 20 / 27.5). Upper bounds are exclusive.
D_UNDER_10 = (None, 10)
D_10_15 = (10, 15)
D_15_25 = (15, 25)
D_25_30 = (25, 30)

MATRIX = [
    # (tier label, volume range, distance label, distance range, price)
    ('High volume (1300+/mo)', HIGH, 'under 10 km', D_UNDER_10, 15),
    ('High volume (1300+/mo)', HIGH, '10-15 km', D_10_15, 19),
    ('High volume (1300+/mo)', HIGH, '15-25 km', D_15_25, 20),
    ('High volume (1300+/mo)', HIGH, '25-30 km', D_25_30, 30),

    ('Mid volume (150+/mo)', MID, 'under 10 km', D_UNDER_10, 20),
    ('Mid volume (150+/mo)', MID, '10-15 km', D_10_15, 25),
    ('Mid volume (150+/mo)', MID, '15-25 km', D_15_25, 25),
    ('Mid volume (150+/mo)', MID, '25-30 km', D_25_30, 30),

    ('Low volume (under 150/mo)', LOW, 'under 10 km', D_UNDER_10, 25),
    ('Low volume (under 150/mo)', LOW, '10-15 km', D_10_15, 30),
    ('Low volume (under 150/mo)', LOW, '15-25 km', D_15_25, 30),
    ('Low volume (under 150/mo)', LOW, '25-30 km', D_25_30, 30),
]

# dimension, match_field, match_kind, match_value, min, max, effect, amount, label
ADJUSTMENTS = [
    ('weight', 'weight_mid_kg', 'numeric_range', None, 5, 15, 'add', 5,
     'Heavier parcels (5-15 kg)', 'Handling load above the standard parcel.'),
    ('weight', 'weight_mid_kg', 'numeric_range', None, 15, None, 'add', 10,
     'Heavy parcels (15 kg+)', 'Often needs a larger vehicle.'),

    ('size', 'size_rank', 'numeric_range', None, 3, None, 'add', 8,
     'Bulky items (appliances / furniture)', 'Vehicle capacity and two-man handling.'),

    ('speed', 'speed_rank', 'numeric_range', None, 4, None, 'add', 15,
     'Express (few hours)', 'Dedicated run, no batching.'),
    ('speed', 'speed_rank', 'numeric_range', None, 3, 4, 'add', 10,
     'Same-day delivery', 'Limits route batching.'),
    ('speed', 'speed_rank', 'numeric_range', None, 1, 2, 'add', -2,
     'Standard 3-5 days', 'Fully batchable — discount.'),

    ('cod', 'cod_required', 'boolean_true', None, None, None, 'add', 2,
     'Cash on delivery', 'Cash handling, reconciliation and settlement.'),
    ('cod', 'cod_share_mid', 'numeric_range', None, 75, None, 'add', 1,
     'Mostly COD (over 75% of orders)', 'Higher cash exposure per run.'),

    ('special_handling', 'special_handling', 'contains', 'Chilled / Frozen', None, None, 'add', 8,
     'Chilled / frozen handling', 'Cold chain.'),
    ('special_handling', 'special_handling', 'contains', 'Oversized / Heavy', None, None, 'add', 10,
     'Oversized / heavy handling', 'Larger vehicle and extra crew.'),
    ('special_handling', 'special_handling', 'contains', 'High-value', None, None, 'add', 5,
     'High-value goods', 'Extra custody and insurance.'),
    ('special_handling', 'special_handling', 'contains', 'Fragile', None, None, 'add', 3,
     'Fragile goods', 'Careful handling and packing checks.'),

    ('returns', 'returns_required', 'boolean_true', None, None, None, 'add', 3,
     'Return logistics', 'Reverse leg back to the client.'),

    ('pickup_locations', 'pickup_locations_mid', 'numeric_range', None, 6, None, 'add', 5,
     'Six or more pickup locations', 'Multi-stop first mile.'),
    ('pickup_locations', 'pickup_locations_mid', 'numeric_range', None, 4, 6, 'add', 3,
     'Four to five pickup locations', 'Multi-stop first mile.'),
    ('pickup_locations', 'pickup_locations_mid', 'numeric_range', None, 2, 4, 'add', 2,
     'Two to three pickup locations', 'Multi-stop first mile.'),

    ('pickups_per_day', 'pickups_per_day_mid', 'numeric_range', None, 6, None, 'add', 4,
     'Six or more pickups a day', 'Repeated first-mile runs.'),
    ('pickups_per_day', 'pickups_per_day_mid', 'numeric_range', None, 3, 6, 'add', 2,
     'Three to five pickups a day', 'Repeated first-mile runs.'),
]


def seed(apps, schema_editor):
    PricingRuleSet = apps.get_model('webpages', 'PricingRuleSet')
    PricingRule = apps.get_model('webpages', 'PricingRule')

    ruleset, created = PricingRuleSet.objects.get_or_create(
        code=RULESET['code'],
        defaults={k: v for k, v in RULESET.items() if k != 'code'},
    )
    if created:
        # save() carries the single-active rule, but a data migration runs against
        # a historical model without it — so enforce it explicitly here.
        PricingRuleSet.objects.filter(is_active=True).exclude(pk=ruleset.pk).update(is_active=False)

    priority = 10
    for tier_label, (vol_min, vol_max), dist_label, (d_min, d_max), price in MATRIX:
        label = f'{tier_label} — {dist_label}'
        PricingRule.objects.get_or_create(
            ruleset=ruleset, dimension='volume_distance_base', label=label,
            defaults={
                'match_field': 'monthly_orders',
                'match_kind': 'numeric_range',
                'match_min': vol_min, 'match_max': vol_max,
                'match2_field': 'distance_km',
                'match2_min': d_min, 'match2_max': d_max,
                'effect': 'set_base', 'amount': price,
                'explanation': f'Rate card v1 matrix: {tier_label}, {dist_label} = {price} QR.',
                'priority': priority, 'stop_on_match': True,
            },
        )
        priority += 10

    for (dimension, field, kind, value, low, high,
         effect, amount, label, explanation) in ADJUSTMENTS:
        PricingRule.objects.get_or_create(
            ruleset=ruleset, dimension=dimension, label=label,
            defaults={
                'match_field': field, 'match_kind': kind, 'match_value': value,
                'match_min': low, 'match_max': high,
                'effect': effect, 'amount': amount,
                'explanation': explanation,
                'priority': priority,
                # Two dimensions stack rather than stopping at the first hit:
                # special handling is a multi-select (fragile AND frozen), and
                # COD charges a base fee PLUS a surcharge for a high cash share.
                # Everywhere else the ranges are mutually exclusive anyway.
                'stop_on_match': dimension not in ('special_handling', 'cod'),
            },
        )
        priority += 10


def unseed(apps, schema_editor):
    PricingRuleSet = apps.get_model('webpages', 'PricingRuleSet')
    PricingRuleSet.objects.filter(code=RULESET['code']).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('webpages', '0012_pricing_rules_and_suggestions'),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]
