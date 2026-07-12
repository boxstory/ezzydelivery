from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('webpages', '0004_pricingenquiry_assigned_to_pricingenquiry_crm_status_and_more'),
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
