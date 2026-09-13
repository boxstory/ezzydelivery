# Purpose: Keep the Live Tracking link for clients who already had it before it became a per-client setting.
# Used by: business.Business.live_tracking_enabled (added in 0034)
# Notes: The sidebar link was ungated, so every client could reach the map. Defaulting the new
#        flag to False would silently take a working feature away from live clients — backfill
#        the ones that are trading and let staff switch it off deliberately instead.

from django.db import migrations


def enable_for_existing_clients(apps, schema_editor):
    Business = apps.get_model('business', 'Business')
    Business.objects.filter(business_status='active').update(live_tracking_enabled=True)


def noop(apps, schema_editor):
    """Nothing to undo: the column goes away with 0034's reverse."""


class Migration(migrations.Migration):

    dependencies = [
        ('business', '0034_business_live_tracking_enabled'),
    ]

    operations = [
        migrations.RunPython(enable_for_existing_clients, noop),
    ]
