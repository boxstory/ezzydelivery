# Generated manually to rename tables from client_* to business_*

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('business', '0020_businessprofile_business_linkedin_and_more'),
    ]

    operations = [
        migrations.AlterModelTable(
            name='business',
            table='business_business',
        ),
        migrations.AlterModelTable(
            name='businessapisettings',
            table='business_businessapisettings',
        ),
        migrations.AlterModelTable(
            name='businesslogo',
            table='business_businesslogo',
        ),
        migrations.AlterModelTable(
            name='businessposter',
            table='business_businessposter',
        ),
        migrations.AlterModelTable(
            name='businessprofile',
            table='business_businessprofile',
        ),
        migrations.AlterModelTable(
            name='businesssocialinfo',
            table='business_businesssocialinfo',
        ),
        migrations.AlterModelTable(
            name='businessteamprofile',
            table='business_businessteamprofile',
        ),
        migrations.AlterModelTable(
            name='driverdirectory',
            table='business_driverdirectory',
        ),
        migrations.AlterModelTable(
            name='pickuplocation',
            table='business_pickuplocation',
        ),
    ]
