# Purpose: Slabs become a fraction of what the vehicle holds, and the car's medium count is 6.
# Used by: migrate — adds two columns to p2p_p2pboxtier, rewrites the four tier rows.
# Notes: The old slabs were absolute, so "4-10 boxes, +25" meant a full car and a fifth-full van,
#        and three of the four were dead on a bike (which takes one small box). Written as halves
#        of the vehicle's own ceiling, two rows say 1-3 and 4-6 in a car and 1-10 and 11-20 in a
#        van. The 11+ quote rule stays an absolute count on purpose: "too big to check out" is
#        about the job, not about how full the vehicle is.

from django.db import migrations, models


def seed(apps, schema_editor):
    P2PBoxTier = apps.get_model('p2p', 'P2PBoxTier')
    P2PVehicleBoxLimit = apps.get_model('p2p', 'P2PVehicleBoxLimit')

    # Ops re-counted: a car takes six medium boxes, not three.
    P2PVehicleBoxLimit.objects.filter(vehicle='car', size='m').update(max_boxes=6)

    P2PBoxTier.objects.all().delete()
    # Every range closes on a real number — the card carries no open ends, so a blank
    # ceiling is written as the limit of a bookable job rather than as "no limit".
    top, heaviest = 20, '1000'

    # One box is the band price and nothing else, whatever fraction of the vehicle it
    # happens to fill. Without this row a bike is 100% full at a single small box and the
    # commonest booking on the platform would be charged as a full vehicle.
    P2PBoxTier.objects.create(
        min_boxes=1, max_boxes=1, up_to_kg=heaviest,
        from_fill=None, to_fill=None, uplift='0', needs_quote=False, is_active=True)

    # Two halves of whichever vehicle the job is priced as. The uplift is carried over
    # from the slabs these replace: an untouched first half stays free, a full vehicle
    # stays at the +25 the old top priced slab charged.
    P2PBoxTier.objects.create(
        min_boxes=1, max_boxes=top, up_to_kg=heaviest,
        from_fill=None, to_fill='0.500', uplift='0', needs_quote=False, is_active=True)
    P2PBoxTier.objects.create(
        min_boxes=1, max_boxes=top, up_to_kg=heaviest,
        from_fill='0.500', to_fill=None, uplift='25', needs_quote=False, is_active=True)

    # Absolute, and deliberately not a fill row: past eleven boxes a human prices it,
    # in a car and in a van alike.
    P2PBoxTier.objects.create(
        min_boxes=11, max_boxes=top, up_to_kg=heaviest,
        from_fill=None, to_fill=None, uplift='0', needs_quote=True, is_active=True)


def unseed(apps, schema_editor):
    """Back to the absolute slabs migration 0008 left, and the car's medium count to 3."""
    P2PBoxTier = apps.get_model('p2p', 'P2PBoxTier')
    P2PVehicleBoxLimit = apps.get_model('p2p', 'P2PVehicleBoxLimit')
    P2PVehicleBoxLimit.objects.filter(vehicle='car', size='m').update(max_boxes=3)
    P2PBoxTier.objects.all().delete()
    for lo, hi, uplift, quote in [(1, 1, '0', False), (2, 3, '10', False),
                                  (4, 10, '25', False), (11, 20, '0', True)]:
        P2PBoxTier.objects.create(min_boxes=lo, max_boxes=hi, up_to_kg='1000',
                                  uplift=uplift, needs_quote=quote, is_active=True)


class Migration(migrations.Migration):

    dependencies = [('p2p', '0013_vehicle_box_limit')]

    operations = [
        migrations.AddField(
            model_name='p2pboxtier',
            name='from_fill',
            field=models.DecimalField(blank=True, decimal_places=3, help_text='How full the vehicle is, from. 0.5 = half. Blank = no lower bound.', max_digits=4, null=True),
        ),
        migrations.AddField(
            model_name='p2pboxtier',
            name='to_fill',
            field=models.DecimalField(blank=True, decimal_places=3, help_text='How full the vehicle is, up to and including. 1 = full. Blank = no upper bound.', max_digits=4, null=True),
        ),
        migrations.RunPython(seed, unseed),
    ]
