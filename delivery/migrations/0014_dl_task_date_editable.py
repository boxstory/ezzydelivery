# Stub recreated for graph consistency (migration already applied).
import datetime
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('delivery', '0013_hub_delivery_fields'),
    ]

    operations = [
        migrations.AlterField(
            model_name='deliverytask',
            name='dl_task_date',
            field=models.DateField(default=datetime.date.today),
        ),
    ]
