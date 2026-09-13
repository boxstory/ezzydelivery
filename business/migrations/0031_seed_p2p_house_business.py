# Purpose: Create the system Business that owns P2P orders from senders who have no business.
# Used by: migrate; resolved at runtime by p2p.services.house_business()
# Notes: Order.business is non-nullable, so a personal sender needs somewhere to hang. Four model
#        defaults are WRONG for this row and each breaks something silently if left — see below.

from django.db import migrations

# Above generate_secure_id()'s ceiling (core/views.py returns 100000-999998), so this
# id can never collide with a real business created through the signup flow.
HOUSE_BUSINESS_ID = 999999
HOUSE_BUSINESS_CODE = 'EZP2P'


def seed(apps, schema_editor):
    Business = apps.get_model('business', 'Business')
    Business.objects.get_or_create(
        business_code=HOUSE_BUSINESS_CODE,
        defaults={
            'business_id': HOUSE_BUSINESS_ID,
            'business_name': 'EzzyDelivery P2P',
            'business_bio': 'Personal point-to-point deliveries booked from the public site.',

            # Defaults that must be overridden. Each one fails quietly, not loudly:
            #  - business_status defaults to 'pending', and the first-mile gate
            #    (delivery/services/pickup.py) refuses any business that is not active,
            #    so parcels would simply never be collected.
            'business_status': 'active',
            #  - pickup_task_enabled defaults to False, which is right for a normal
            #    client but fatal here: the pickup leg IS the P2P job.
            'pickup_task_enabled': True,
            #  - pickup_disposition_default defaults to 'drop', which routes the parcel
            #    to a hub. A P2P parcel goes to the receiver, by the same driver.
            'pickup_disposition_default': 'self_deliver',
            #  - pickup_mode_default defaults to 'assigned', and there is no driver
            #    directory for this business, so an assigned task is visible to nobody.
            'pickup_mode_default': 'public_pool',
            #  - fulfillment_service_enabled defaults to True, which would run a
            #    warehouse lookup on every personal parcel.
            'fulfillment_service_enabled': False,
        },
    )


def unseed(apps, schema_editor):
    """Only removes the row if nothing hangs off it — never orphan live orders."""
    Business = apps.get_model('business', 'Business')
    Order = apps.get_model('orders', 'Order')
    if Order.objects.filter(business__business_code=HOUSE_BUSINESS_CODE).exists():
        return
    Business.objects.filter(business_code=HOUSE_BUSINESS_CODE).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('business', '0030_pickuplocation_contact_name_and_more'),
        ('orders', '0065_order_p2p_customer_order_package_weight_kg_and_more'),
    ]

    operations = [migrations.RunPython(seed, unseed)]
