"""
Step 1: Expand driver_status choices to accept both old and new values.
Add driver_availability field.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('fleet', '0008_earnings_verification'),
    ]

    # Transitional choices: accept both old Title Case and new snake_case values
    TRANSITIONAL_STATUS_CHOICES = [
        ('Pending on Review', 'Pending on Review'),
        ('Processing', 'Processing'),
        ('Approved', 'Approved'),
        ('Rejected', 'Rejected'),
        ('Blocked', 'Blocked'),
        ('Active', 'Active'),
        ('Approval Pending', 'Approval Pending'),
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('blocked', 'Blocked'),
        ('suspended', 'Suspended'),
    ]

    AVAILABILITY_CHOICES = [
        ('offline', 'Offline'),
        ('available', 'Available'),
        ('on_delivery', 'On Delivery'),
        ('on_break', 'On Break'),
        ('returning', 'Returning'),
    ]

    operations = [
        # Expand choices to accept both old and new values during transition
        migrations.AlterField(
            model_name='driver',
            name='driver_status',
            field=models.CharField(
                choices=TRANSITIONAL_STATUS_CHOICES,
                db_index=True,
                default='pending',
                max_length=100,
            ),
        ),
        # Add driver_availability field
        migrations.AddField(
            model_name='driver',
            name='driver_availability',
            field=models.CharField(
                choices=AVAILABILITY_CHOICES,
                db_index=True,
                default='offline',
                help_text='Real-time availability status of the driver',
                max_length=20,
            ),
        ),
        # Add availability index
        migrations.AddIndex(
            model_name='driver',
            index=models.Index(fields=['driver_availability'], name='driver_avail_idx'),
        ),
    ]
