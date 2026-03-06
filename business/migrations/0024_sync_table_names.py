# Generated manually to sync Django state with actual database table names
# Reverts migration 0021's rename from business_* back to client_* to match models

from django.db import migrations


class Migration(migrations.Migration):
    """
    This migration renames tables back from business_* to client_* to match
    the db_table settings in the models. Migration 0021 renamed them, but
    the models still use the client_* prefix.
    """

    dependencies = [
        ('business', '0023_sync_fulfillment_fields'),
    ]

    operations = [
        migrations.AlterModelTable(
            name='business',
            table='client_business',
        ),
        migrations.AlterModelTable(
            name='businessapisettings',
            table='client_businessapisettings',
        ),
        migrations.AlterModelTable(
            name='businesslogo',
            table='client_businesslogo',
        ),
        migrations.AlterModelTable(
            name='businessposter',
            table='client_businessposter',
        ),
        migrations.AlterModelTable(
            name='businessprofile',
            table='client_businessprofile',
        ),
        migrations.AlterModelTable(
            name='businesssocialinfo',
            table='client_businesssocialinfo',
        ),
        migrations.AlterModelTable(
            name='businessteamprofile',
            table='client_businessteamprofile',
        ),
        migrations.AlterModelTable(
            name='driverdirectory',
            table='client_driverdirectory',
        ),
        migrations.AlterModelTable(
            name='pickuplocation',
            table='client_pickuplocation',
        ),
    ]
