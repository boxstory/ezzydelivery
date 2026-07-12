# Generated manually to add warehouse capacity configuration fields
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('warehouse', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='warehouse',
            name='total_zones',
            field=models.IntegerField(default=0, help_text='Total number of zones in this warehouse'),
        ),
        migrations.AddField(
            model_name='warehouse',
            name='racks_per_zone',
            field=models.IntegerField(default=0, help_text='Number of racks in each zone'),
        ),
        migrations.AddField(
            model_name='warehouse',
            name='shelves_per_rack',
            field=models.IntegerField(default=0, help_text='Number of shelves in each rack'),
        ),
        migrations.AddField(
            model_name='warehouse',
            name='bins_per_shelf',
            field=models.IntegerField(default=0, help_text='Number of bins in each shelf'),
        ),
        migrations.AddField(
            model_name='warehouse',
            name='zone_naming_pattern',
            field=models.CharField(default='A,B,C,D', help_text="Zone naming pattern (e.g., 'A,B,C' or '1,2,3' or 'NORTH,SOUTH')", max_length=50),
        ),
        migrations.AddField(
            model_name='warehouse',
            name='rack_naming_pattern',
            field=models.CharField(choices=[('numeric', 'Numeric (01, 02, 03...)'), ('alpha', 'Alpha (A, B, C...)')], default='numeric', help_text='How to name racks within zones', max_length=20),
        ),
        migrations.AddField(
            model_name='warehouse',
            name='shelf_naming_pattern',
            field=models.CharField(choices=[('numeric', 'Numeric (01, 02, 03...)'), ('alpha', 'Alpha (A, B, C...)')], default='numeric', help_text='How to name shelves within racks', max_length=20),
        ),
        migrations.AddField(
            model_name='warehouse',
            name='bin_naming_pattern',
            field=models.CharField(choices=[('numeric', 'Numeric (01, 02, 03...)'), ('alpha', 'Alpha (A, B, C...)')], default='numeric', help_text='How to name bins within shelves', max_length=20),
        ),
        migrations.AddField(
            model_name='warehouse',
            name='is_capacity_configured',
            field=models.BooleanField(default=False, help_text='Has the warehouse capacity been configured?'),
        ),
        migrations.AddField(
            model_name='warehouse',
            name='capacity_configured_at',
            field=models.DateTimeField(blank=True, help_text='When was capacity configuration completed?', null=True),
        ),
    ]
