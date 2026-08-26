# Purpose: Give every inquiry its own quote token, then make the column unique.
# Used by: webpages.views.inquiry_quote — the token is the only key that view accepts.
# Notes: 0009's AddField evaluated uuid4() ONCE for the whole table, so every existing row shares
#        one value. Rewriting them row by row here is what lets the unique index build; splitting
#        this out of 0009 is deliberate, not accidental.

import uuid

from django.db import migrations, models


def assign_tokens(apps, schema_editor):
    PricingEnquiry = apps.get_model('webpages', 'PricingEnquiry')
    # Every row, not just the null ones — the duplicates are non-null.
    for pk in PricingEnquiry.objects.values_list('pk', flat=True).iterator():
        PricingEnquiry.objects.filter(pk=pk).update(quote_token=uuid.uuid4())


def noop(apps, schema_editor):
    """Reversing only drops the constraint; the tokens themselves stay valid."""


class Migration(migrations.Migration):

    dependencies = [
        ('webpages', '0010_seed_pricing_plans_and_quote_tokens'),
    ]

    operations = [
        migrations.RunPython(assign_tokens, noop),
        migrations.AlterField(
            model_name='pricingenquiry',
            name='quote_token',
            field=models.UUIDField(default=uuid.uuid4, editable=False, null=True, unique=True),
        ),
    ]
