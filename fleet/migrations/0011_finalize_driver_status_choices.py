"""
Step 3: Finalize driver_status choices - remove old Title Case values.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('fleet', '0010_migrate_driver_status_values'),
    ]

    FINAL_STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('blocked', 'Blocked'),
        ('suspended', 'Suspended'),
    ]

    operations = [
        migrations.AlterField(
            model_name='driver',
            name='driver_status',
            field=models.CharField(
                choices=FINAL_STATUS_CHOICES,
                db_index=True,
                default='pending',
                max_length=100,
            ),
        ),
    ]
