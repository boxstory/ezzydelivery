# Purpose: Keep every driver who is already working on the road when dashboard access becomes a separate permission.
# Used by: manage.py migrate (pairs with 0048, which adds the column)
# Notes: The new column defaults to False, so without this every approved driver in production
#        would lose the app the moment 0048 lands. Ship both together, before the gated code.

from django.db import migrations


def enable_for_approved_drivers(apps, schema_editor):
    """Everyone already approved was, by definition, already allowed to work."""
    Driver = apps.get_model('fleet', 'Driver')
    Driver.objects.filter(driver_status='approved').update(dashboard_access_enabled=True)


def noop(apps, schema_editor):
    """Nothing to undo: the column goes away with 0048's reverse."""


class Migration(migrations.Migration):

    dependencies = [
        ('fleet', '0048_driver_dashboard_access_enabled_and_more'),
    ]

    operations = [
        migrations.RunPython(enable_for_approved_drivers, noop),
    ]
