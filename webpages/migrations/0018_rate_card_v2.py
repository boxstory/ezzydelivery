# Purpose: Rate card v2 — recalibrated against what we have actually billed, and activated.
# Used by: the suggested-price engine; v1 is deactivated but kept so old suggestions stay explainable.
# Notes: Two changes of substance. The base is FLAT across Doha and moves on volume (25/20/15),
#        because 673 verified deliveries say the charge tracks the account, not the kilometre.
#        And only rare exceptions are surcharged — anything most leads tick is in the base.

from django.db import migrations

CARD = dict(
    name='Rate card v2',
    base_price_default='25.00',
    min_price_floor='15.00',
    floor_basis='config',
    rounding_step='1.00',
    rounding_mode='nearest',
    max_total_discount_pct='40.00',
    max_total_uplift_pct='60.00',
    is_active=True,
    notes=(
        'Calibrated against evidence, not theory. In 673 verified deliveries we have only '
        'ever billed 20 or 25 QR, and the median is 20 in EVERY distance band under 30 km — '
        'the rate tracks the account, not the kilometre. The desk says the same thing on '
        'WhatsApp ("we do flat 20Qr", "inside doha 20 Qr"). So Doha is flat and the base '
        'moves on volume: 25 low, 20 mid, 15 high. Beyond Doha it steps to the numbers the '
        'desk actually quotes (30 outside Doha, 35 Al Khor); over 30 km stays off the card '
        'because those are priced by hand and have run to 70. '
        'Surcharges are only for the rare and genuinely costly: express, bulky, 15 kg+, '
        'special handling, six or more pickup points. Same-day delivery (66% of leads), COD '
        '(64%), same-day pick and deliver (49%), home pickup (49%), returns (47%) and several '
        'pickups a day (44%) are NOT surcharged — a fee nearly every lead pays is a higher '
        'base with extra steps, and stacking six of them is why v1 hit its uplift cap on '
        'every second lead.'
    ),
)

TIERS = [
    ('High volume (1300+/mo)', '1300.00', None, '15.00', '25.00'),
    ('Mid volume (150+/mo)', '150.00', '1300.00', '20.00', '30.00'),
    ('Low volume (under 150/mo)', None, '150.00', '25.00', '35.00'),
]
DOHA_BANDS = [('under 10 km', None, '10.00'),
              ('10-15 km', '10.00', '15.00'),
              ('15-25 km', '15.00', '25.00')]

ADJUSTMENTS = [
    dict(dimension='speed', label='Express (few hours)', match_field='speed_rank',
         match_kind='numeric_range', match_min='4.00', effect='add', amount='5.00', priority=5,
         explanation='A dedicated run rather than a batched one — 23% of leads. Same-day and '
                     'next-day are NOT surcharged: two thirds of the market promises them, so '
                     'they are in the base.'),
    dict(dimension='speed', label='Standard 3-5 days', match_field='speed_rank',
         match_kind='numeric_range', match_min='1.00', match_max='2.00',
         effect='add', amount='-2.00', priority=20,
         explanation='Fully batchable. The only discount on the card.'),
    dict(dimension='size', label='Bulky items (appliances / furniture)', match_field='size_rank',
         match_kind='numeric_range', match_min='3.00', effect='add', amount='5.00', priority=10,
         explanation='5% of leads. Will not fit a normal run.'),
    dict(dimension='weight', label='Heavy parcels (15 kg+)', match_field='weight_mid_kg',
         match_kind='numeric_range', match_min='15.00', effect='add', amount='5.00', priority=5,
         explanation='Under 2% of leads. 5-15 kg is ordinary and is not surcharged.'),
    dict(dimension='special_handling', label='Chilled / frozen handling',
         match_field='special_handling', match_kind='contains', match_value='Chilled / Frozen',
         effect='add', amount='5.00', priority=10, stop_on_match=False),
    dict(dimension='special_handling', label='Oversized / heavy handling',
         match_field='special_handling', match_kind='contains', match_value='Oversized / Heavy',
         effect='add', amount='5.00', priority=20, stop_on_match=False),
    dict(dimension='special_handling', label='High-value goods',
         match_field='special_handling', match_kind='contains', match_value='High-value',
         effect='add', amount='3.00', priority=30, stop_on_match=False),
    dict(dimension='special_handling', label='Fragile goods',
         match_field='special_handling', match_kind='contains', match_value='Fragile',
         effect='add', amount='2.00', priority=40, stop_on_match=False),
    dict(dimension='pickup_locations', label='Six or more pickup locations',
         match_field='pickup_locations_mid', match_kind='numeric_range', match_min='6.00',
         effect='add', amount='3.00', priority=5,
         explanation='Scattered collection is a different job. Two to five points are in the base.'),
]


def seed(apps, schema_editor):
    PricingRuleSet = apps.get_model('webpages', 'PricingRuleSet')
    PricingRule = apps.get_model('webpages', 'PricingRule')
    if PricingRuleSet.objects.filter(code='rate_card_v2').exists():
        return

    ruleset = PricingRuleSet.objects.create(code='rate_card_v2', **CARD)

    for tier, vmin, vmax, doha, remote in TIERS:
        for band_label, dmin, dmax in DOHA_BANDS:
            PricingRule.objects.create(
                ruleset=ruleset, dimension='volume_distance_base',
                label=f'{tier} — {band_label}',
                explanation='Flat across Doha — the billed rate tracks the account, not the km.',
                match_field='monthly_orders', match_kind='numeric_range',
                match_min=vmin, match_max=vmax,
                match2_field='distance_km', match2_min=dmin, match2_max=dmax,
                effect='set_base', amount=doha, priority=10)
        PricingRule.objects.create(
            ruleset=ruleset, dimension='volume_distance_base', label=f'{tier} — 25-30 km',
            explanation='Outside Doha. The desk quotes 30 here, 35 for Al Khor.',
            match_field='monthly_orders', match_kind='numeric_range',
            match_min=vmin, match_max=vmax,
            match2_field='distance_km', match2_min='25.00', match2_max='30.00',
            effect='set_base', amount=remote, priority=10)
        # Distance is unanswered on most records, and a flat 25 for a 2,000-order
        # account is plainly wrong. Volume alone still tiers, assuming Doha.
        # Priority 90 so it only wins after every matrix cell has been tried.
        PricingRule.objects.create(
            ruleset=ruleset, dimension='volume_distance_base',
            label=f'{tier} — distance not given (assumes Doha)',
            explanation='Distance was not answered. Priced as Doha at this volume — confirm '
                        'the areas before committing to it.',
            match_field='monthly_orders', match_kind='numeric_range',
            match_min=vmin, match_max=vmax,
            effect='set_base', amount=doha, priority=90)

    for rule in ADJUSTMENTS:
        PricingRule.objects.create(ruleset=ruleset, **rule)

    # Single-active invariant: the historical model's save() does not carry it.
    PricingRuleSet.objects.exclude(pk=ruleset.pk).update(is_active=False)


def unseed(apps, schema_editor):
    PricingRuleSet = apps.get_model('webpages', 'PricingRuleSet')
    PricingRuleSet.objects.filter(code='rate_card_v2').delete()
    PricingRuleSet.objects.filter(code='rate_card_v1').update(is_active=True)


class Migration(migrations.Migration):

    dependencies = [('webpages', '0017_seed_urgency_and_pickup_type_rules')]

    operations = [migrations.RunPython(seed, unseed)]
