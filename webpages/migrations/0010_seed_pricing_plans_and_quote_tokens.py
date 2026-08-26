# Purpose: Seed the two live plan options shown on the quote page.
# Used by: webpages.views.inquiry_quote (the price table it renders).
# Notes: Idempotent on `key` and only fills on create — a rate the sales desk edited in admin is
#        never overwritten by a later deploy. Token backfill lives in 0011, next to its constraint.

from django.db import migrations


PLANS = [
    {
        'key': 'flat_48h',
        'name': 'Flat Rate — 48 Hour Delivery',
        'subtitle': 'One price, every order',
        'description': (
            'A single flat rate per delivery with a 48-hour delivery window. '
            'No zone maths and no distance surcharge — you know the cost of every '
            'order the moment it comes in.'
        ),
        'price_display': '25',
        'price_unit': 'QR per delivery',
        'price_value': 25,
        'features': (
            'Flat 25 QR per delivery\n'
            'Delivered within 48 hours\n'
            'Same price to every covered area\n'
            'Cash on Delivery supported\n'
            'Live tracking and proof of delivery'
        ),
        'is_custom_quote': False,
        'badge': 'Most Popular',
        'is_featured': True,
        'sort_order': 1,
    },
    {
        'key': 'talk_to_sales',
        'name': 'Custom Plan',
        'subtitle': 'Discuss with our sales team',
        'description': (
            'High volume, same-day delivery, fulfillment or special handling? '
            'Pick this and our sales team will build a rate around your numbers '
            'and call you back.'
        ),
        'price_display': "Let's talk",
        'price_unit': 'custom quote',
        'price_value': None,
        'features': (
            'Volume-based rates\n'
            'Same-day and express options\n'
            'Fulfillment and storage add-ons\n'
            'Special handling and white glove\n'
            'A named account manager'
        ),
        'is_custom_quote': True,
        'badge': '',
        'is_featured': False,
        'sort_order': 2,
    },
]


def seed(apps, schema_editor):
    PricingPlanOption = apps.get_model('webpages', 'PricingPlanOption')
    for row in PLANS:
        # create_defaults would overwrite staff edits, so only fill on create.
        PricingPlanOption.objects.get_or_create(key=row['key'], defaults=row)


def unseed(apps, schema_editor):
    PricingPlanOption = apps.get_model('webpages', 'PricingPlanOption')
    PricingPlanOption.objects.filter(key__in=[r['key'] for r in PLANS]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('webpages', '0009_pricing_plan_option_and_quote_fields'),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]
