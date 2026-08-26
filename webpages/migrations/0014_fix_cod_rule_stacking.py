# Purpose: Let the COD rules stack, so the high-cash-share surcharge can actually fire.
# Used by: webpages.pricing.engine, which stops at the first matching rule in a dimension.
# Notes: As seeded in 0013 the base "Cash on delivery" rule matched first and stopped, making the
#        "Mostly COD (over 75%)" rule unreachable. 0013 is fixed for fresh installs; this repairs
#        databases where it already ran. Scoped to the seeded label so a staff-authored rule is
#        never touched.

from django.db import migrations


def fix(apps, schema_editor):
    PricingRule = apps.get_model('webpages', 'PricingRule')
    PricingRule.objects.filter(
        dimension='cod', label='Cash on delivery', stop_on_match=True,
    ).update(stop_on_match=False)


def unfix(apps, schema_editor):
    PricingRule = apps.get_model('webpages', 'PricingRule')
    PricingRule.objects.filter(
        dimension='cod', label='Cash on delivery', stop_on_match=False,
    ).update(stop_on_match=True)


class Migration(migrations.Migration):

    dependencies = [
        ('webpages', '0013_seed_rate_card_v1'),
    ]

    operations = [
        migrations.RunPython(fix, unfix),
    ]
