# Purpose: Add the same-day pick & deliver and residential-pickup rules to rate card v1.
# Used by: the suggested-price engine — both dimensions were normalised but priced by nothing.
# Notes: get_or_create keyed on (ruleset, dimension, label) so re-running never duplicates a
#        line, and so the rows already added by hand on production are adopted, not doubled.

from django.db import migrations


def seed(apps, schema_editor):
    PricingRuleSet = apps.get_model('webpages', 'PricingRuleSet')
    PricingRule = apps.get_model('webpages', 'PricingRule')
    ruleset = PricingRuleSet.objects.filter(code='rate_card_v1').first()
    if ruleset is None:
        return

    PricingRule.objects.get_or_create(
        ruleset=ruleset, dimension='same_day_pickup',
        label='Frequent same-day pick & deliver',
        defaults=dict(
            explanation='Collection and delivery inside the same day cannot be batched into '
                        'the next morning run — it costs a dedicated leg.',
            match_field='same_day_required', match_kind='boolean_true',
            effect='add', amount='5.00', priority=10),
    )
    PricingRule.objects.get_or_create(
        ruleset=ruleset, dimension='pickup_type',
        label='Residential pickup point',
        defaults=dict(
            explanation='Home collection: no dock, residential parking, and the sender may '
                        'not be in. Commercial premises and fulfilment centres rank below '
                        'the threshold and pay nothing. How MANY pickup points there are is '
                        'priced separately by the pickup_locations ladder.',
            match_field='pickup_type_rank', match_kind='numeric_range',
            match_min='3.00', effect='add', amount='2.00', priority=10),
    )


def unseed(apps, schema_editor):
    PricingRule = apps.get_model('webpages', 'PricingRule')
    PricingRule.objects.filter(dimension__in=('same_day_pickup', 'pickup_type')).delete()


class Migration(migrations.Migration):

    dependencies = [('webpages', '0016_alter_pricingrule_dimension')]

    operations = [migrations.RunPython(seed, unseed)]
