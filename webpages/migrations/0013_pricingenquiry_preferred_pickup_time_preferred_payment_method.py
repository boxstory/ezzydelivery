from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('webpages', '0012_pricing_enquiry_crm_fields'),
    ]

    operations = [
        migrations.AddField(
            model_name='pricingenquiry',
            name='preferred_pickup_time',
            field=models.CharField(blank=True, max_length=100, null=True),
        ),
        migrations.AddField(
            model_name='pricingenquiry',
            name='preferred_payment_method',
            field=models.CharField(blank=True, max_length=100, null=True),
        ),
    ]
