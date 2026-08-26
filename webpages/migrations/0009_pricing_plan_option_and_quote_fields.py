# Purpose: Add the quotable plan catalogue and the quote-agreement columns on PricingEnquiry.
# Used by: webpages.views.inquiry_quote, workforce pricing inquiry screens.
# Notes: quote_token lands non-unique here on purpose — a callable default is evaluated once for
#        the whole table, so 0010 backfills a distinct value per row before 0011 adds the constraint.

import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('webpages', '0008_pricingenquiry_email'),
    ]

    operations = [
        migrations.CreateModel(
            name='PricingPlanOption',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('key', models.SlugField(help_text='Stable identifier posted by the form. Do not rename in use.', max_length=50, unique=True)),
                ('name', models.CharField(max_length=100)),
                ('subtitle', models.CharField(blank=True, max_length=150, null=True)),
                ('description', models.TextField(blank=True, null=True)),
                ('price_display', models.CharField(blank=True, max_length=30, null=True)),
                ('price_unit', models.CharField(blank=True, help_text="e.g. 'QR per delivery'", max_length=60, null=True)),
                ('price_value', models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True)),
                ('features', models.TextField(blank=True, help_text='One feature per line — rendered as the ticked list on the card.', null=True)),
                ('is_custom_quote', models.BooleanField(default=False, help_text="No fixed price — selecting it means 'contact me to agree a rate'.")),
                ('badge', models.CharField(blank=True, help_text="Ribbon text, e.g. 'Most Popular'. Leave empty for none.", max_length=30, null=True)),
                ('is_featured', models.BooleanField(default=False)),
                ('is_active', models.BooleanField(default=True)),
                ('sort_order', models.PositiveIntegerField(default=0)),
                ('created_at', models.DateTimeField(auto_now_add=True, null=True)),
                ('updated_at', models.DateTimeField(auto_now=True, null=True)),
            ],
            options={
                'verbose_name': 'Pricing Plan Option',
                'verbose_name_plural': 'Pricing Plan Options',
                'ordering': ['sort_order', 'id'],
            },
        ),
        migrations.AddField(
            model_name='pricingenquiry',
            name='quote_token',
            field=models.UUIDField(default=uuid.uuid4, editable=False, null=True),
        ),
        migrations.AddField(
            model_name='pricingenquiry',
            name='selected_plan',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                                    related_name='agreements', to='webpages.pricingplanoption'),
        ),
        migrations.AddField(
            model_name='pricingenquiry',
            name='agreed_plan_name',
            field=models.CharField(blank=True, max_length=100, null=True),
        ),
        migrations.AddField(
            model_name='pricingenquiry',
            name='agreed_price_display',
            field=models.CharField(blank=True, max_length=30, null=True),
        ),
        migrations.AddField(
            model_name='pricingenquiry',
            name='agreed_price_unit',
            field=models.CharField(blank=True, max_length=60, null=True),
        ),
        migrations.AddField(
            model_name='pricingenquiry',
            name='agreed_price_value',
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True),
        ),
        migrations.AddField(
            model_name='pricingenquiry',
            name='plan_agreed_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='pricingenquiry',
            name='plan_agreement_ip',
            field=models.GenericIPAddressField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='pricingenquiry',
            name='plan_agreement_user_agent',
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
        migrations.AddField(
            model_name='pricingenquiry',
            name='plan_agreement_note',
            field=models.TextField(blank=True, null=True),
        ),
    ]
