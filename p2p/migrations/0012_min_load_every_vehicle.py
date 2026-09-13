# Purpose: Give every vehicle a smallest-load figure, not just the pickup.
# Used by: migrate — one pass over p2p_p2pvehiclecapacity.
# Notes: The rule is "you only get this vehicle once the smaller one is full", so each floor is
#        the capacity of the vehicle below it on the ladder: car starts where the bike's box ends
#        (0.027), van where the pickup's bed ends (1.5), truck where the van ends (6.0). The bike
#        is the bottom of the ladder and has no floor. The pickup is the exception ops set by
#        hand: 1.0 rather than the car's 0.4, because a pickup is a cubic-metre job.
#        The floor is ignored whenever nothing smaller can carry the load, so none of these can
#        strand a booking between two vehicles.

from django.db import migrations

MIN_LOAD = {
    'bike': '0',
    'car': '0.0270',
    'suv': '1.0000',
    'van': '1.5000',
    'truck': '6.0000',
}


def seed(apps, schema_editor):
    P2PVehicleCapacity = apps.get_model('p2p', 'P2PVehicleCapacity')
    for vehicle, minimum in MIN_LOAD.items():
        P2PVehicleCapacity.objects.filter(vehicle=vehicle).update(min_cbm=minimum)


def unseed(apps, schema_editor):
    """Back to the pickup-only state migration 0011 left."""
    P2PVehicleCapacity = apps.get_model('p2p', 'P2PVehicleCapacity')
    P2PVehicleCapacity.objects.exclude(vehicle='suv').update(min_cbm=0)


class Migration(migrations.Migration):

    dependencies = [('p2p', '0011_vehicle_min_load')]

    operations = [migrations.RunPython(seed, unseed)]
