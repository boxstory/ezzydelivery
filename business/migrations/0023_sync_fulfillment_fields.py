# Generated manually to sync Django state with existing database columns

from django.db import migrations, models


class Migration(migrations.Migration):
    """
    This migration syncs Django's model state with the database.
    The actual columns were added in 0022 via RunSQL.
    This migration only updates Django's internal state.
    """

    dependencies = [
        ('business', '0022_add_fulfillment_service_fields'),
    ]

    operations = [
        # Use SeparateDatabaseAndState to tell Django these fields exist
        # without trying to create them in the database
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AddField(
                    model_name='business',
                    name='fulfillment_service_enabled',
                    field=models.BooleanField(
                        default=False,
                        help_text='Enable fulfillment service (WMS integration) for this business'
                    ),
                ),
                migrations.AddField(
                    model_name='business',
                    name='fulfillment_activated_at',
                    field=models.DateTimeField(
                        blank=True,
                        null=True,
                        help_text='When the fulfillment service was activated'
                    ),
                ),
            ],
            database_operations=[],  # No database changes needed - columns already exist
        ),
    ]
