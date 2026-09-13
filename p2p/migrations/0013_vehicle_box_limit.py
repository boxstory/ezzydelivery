# Purpose: Per-vehicle, per-size box count ceilings — the limit volume cannot express.
# Used by: p2p.pricing (vehicle_can_carry / vehicle_verdict), the rate-card page.
# Notes: Seeded with the car only, from what ops counted: 3 medium or 6 small. Those two are
#        volumetrically incompatible (0.141 cbm against 0.090), which is the whole reason the
#        table exists. Every other pairing is left unseeded — a missing row means no count
#        limit and the cbm rule decides alone, so nothing else on the card moves.

from django.db import migrations, models

SEED = [
    ('car', 'm', 3),
    ('car', 's', 6),
]


def seed(apps, schema_editor):
    P2PVehicleBoxLimit = apps.get_model('p2p', 'P2PVehicleBoxLimit')
    for vehicle, size, cap in SEED:
        P2PVehicleBoxLimit.objects.get_or_create(
            vehicle=vehicle, size=size,
            defaults={'max_boxes': cap, 'is_active': True})


def unseed(apps, schema_editor):
    P2PVehicleBoxLimit = apps.get_model('p2p', 'P2PVehicleBoxLimit')
    for vehicle, size, _ in SEED:
        P2PVehicleBoxLimit.objects.filter(vehicle=vehicle, size=size).delete()


class Migration(migrations.Migration):

    dependencies = [('p2p', '0012_min_load_every_vehicle')]

    operations = [
        migrations.CreateModel(
            name='P2PVehicleBoxLimit',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('vehicle', models.CharField(choices=[('bike', 'Motorcycle'), ('car', 'Car'), ('suv', 'SUV / Pickup'), ('van', 'Van'), ('truck', 'Truck')], help_text='Which vehicle this count is for', max_length=10)),
                ('size', models.CharField(choices=[('xs', 'Envelope / Docs (≤ 0.5 kg)'), ('s', 'Small Box (≤ 3 kg)'), ('m', 'Medium Box (≤ 10 kg)'), ('l', 'Large Box (≤ 25 kg)'), ('xl', 'Bulky / Extra Large (25 kg+)')], help_text='Which box size the count applies to', max_length=2)),
                ('max_boxes', models.PositiveIntegerField(blank=True, help_text='Most boxes of this size the vehicle takes. Blank = volume decides.', null=True)),
                ('is_active', models.BooleanField(db_index=True, default=True, help_text='Off = no count limit on this pairing')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name': 'P2P vehicle box limit',
                'verbose_name_plural': 'P2P vehicle box limits',
                'ordering': ['vehicle', 'size', 'id'],
            },
        ),
        migrations.AddConstraint(
            model_name='p2pvehicleboxlimit',
            constraint=models.UniqueConstraint(fields=('vehicle', 'size'), name='uniq_p2p_box_limit_vehicle_size'),
        ),
        migrations.RunPython(seed, unseed),
    ]
