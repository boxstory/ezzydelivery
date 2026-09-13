# Purpose: Move rate card v2's 15 QR tier down from 1300+ to 500+ orders a month.
# Used by: the suggested-price engine — retiers every base rule on the active card.
# Notes: Edits v2 in place rather than cutting a v3: the shape of the card is unchanged,
#        only where the volume boundary sits. Suggestions already stored keep their own
#        snapshot, so nothing already quoted is rewritten.

from django.db import migrations

OLD_HIGH, NEW_HIGH = '1300.00', '500.00'


def retier(apps, schema_editor):
    PricingRule = apps.get_model('webpages', 'PricingRule')
    base = PricingRule.objects.filter(ruleset__code='rate_card_v2',
                                      dimension='volume_distance_base')
    # The 15 QR tier: everything at or above the boundary.
    base.filter(match_min=OLD_HIGH).update(match_min=NEW_HIGH)
    # The 20 QR tier: everything below it, down to 150.
    base.filter(match_max=OLD_HIGH).update(match_max=NEW_HIGH)

    for rule in base.all():
        if rule.label.startswith('High volume'):
            rule.label = rule.label.replace('(1300+/mo)', '(500+/mo)')
            rule.save(update_fields=['label'])
        elif rule.label.startswith('Mid volume'):
            rule.label = rule.label.replace('(150+/mo)', '(150-500/mo)')
            rule.save(update_fields=['label'])

    PricingRuleSet = apps.get_model('webpages', 'PricingRuleSet')
    PricingRuleSet.objects.filter(code='rate_card_v2').update(
        notes=(
            'Calibrated against evidence, not theory. In 673 verified deliveries we have only '
            'ever billed 20 or 25 QR, and the median is 20 in EVERY distance band under 30 km — '
            'the rate tracks the account, not the kilometre. The desk says the same thing on '
            'WhatsApp ("we do flat 20Qr", "inside doha 20 Qr"). So Doha is flat and the base '
            'moves on volume: 25 under 150 orders a month, 20 from 150, 15 from 500. Beyond '
            'Doha it steps to the numbers the desk actually quotes (30 outside Doha, 35 Al '
            'Khor); over 30 km stays off the card because those are priced by hand and have '
            'run to 70. Surcharges are only for the rare and genuinely costly: express, bulky, '
            '15 kg+, special handling, six or more pickup points. Same-day delivery (66% of '
            'leads), COD (64%), same-day pick and deliver (49%), home pickup (49%), returns '
            '(47%) and several pickups a day (44%) are NOT surcharged — a fee nearly every '
            'lead pays is a higher base with extra steps, and stacking six of them is why v1 '
            'hit its uplift cap on every second lead.'
        ))


def unretier(apps, schema_editor):
    PricingRule = apps.get_model('webpages', 'PricingRule')
    base = PricingRule.objects.filter(ruleset__code='rate_card_v2',
                                      dimension='volume_distance_base')
    base.filter(match_min=NEW_HIGH).update(match_min=OLD_HIGH)
    base.filter(match_max=NEW_HIGH).update(match_max=OLD_HIGH)
    for rule in base.all():
        if rule.label.startswith('High volume'):
            rule.label = rule.label.replace('(500+/mo)', '(1300+/mo)')
            rule.save(update_fields=['label'])
        elif rule.label.startswith('Mid volume'):
            rule.label = rule.label.replace('(150-500/mo)', '(150+/mo)')
            rule.save(update_fields=['label'])


class Migration(migrations.Migration):

    dependencies = [('webpages', '0018_rate_card_v2')]

    operations = [migrations.RunPython(retier, unretier)]
