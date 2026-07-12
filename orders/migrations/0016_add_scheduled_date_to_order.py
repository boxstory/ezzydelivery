# Stub recreated for graph consistency (migration already applied).
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('orders', '0015_order_cancellation_notes_order_cancellation_reason_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='order',
            name='scheduled_date',
            field=models.DateField(blank=True, help_text='Scheduled delivery date if scheduled_delivery is True', null=True),
        ),
    ]
