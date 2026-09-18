# Purpose: Repair the client rows that migration 0010's default=True switched fulfilment on for.
# Used by: business.Business.fulfillment_service_enabled / _status / _activated_at
# Notes: Do not trust fulfillment_activated_at as evidence of activation — it is stamped on rows
#        that were never onboarded (36 of them carry a value equal to created_at, and rows that
#        were explicitly switched off keep theirs too). The only honest evidence that a client is
#        really on fulfilment is a warehouse footprint: an active SellerWarehouseLink, stock on a
#        shelf, or a product request. Clients with a footprint get promoted to status='active';
#        the rest are switched off and their stale FC pickup flags cleared, mirroring
#        workforce.views._retire_fulfilment_pickup_locations.

from django.db import migrations
from django.utils import timezone


def has_warehouse_footprint(apps, business):
    """True when this client is really running fulfilment, on evidence only."""
    SellerWarehouseLink = apps.get_model('warehouse', 'SellerWarehouseLink')
    StockLevel = apps.get_model('warehouse', 'StockLevel')
    InboundProductRequest = apps.get_model('warehouse', 'InboundProductRequest')
    OutboundProductRequest = apps.get_model('warehouse', 'OutboundProductRequest')

    return (
        SellerWarehouseLink.objects.filter(business=business, is_active=True).exists()
        or StockLevel.objects.filter(product__business=business, quantity_on_hand__gt=0).exists()
        or InboundProductRequest.objects.filter(business=business).exists()
        or OutboundProductRequest.objects.filter(business=business).exists()
    )


def retire_fulfilment_pickup_locations(apps, business):
    """Settle FC-flagged pickup rows for a client coming off fulfilment.

    The test is whether a warehouse sits behind the row, NOT whether the link is
    still active. A row carrying a warehouse_id is a hub address however stale its
    link: clearing its flag would return the hub to the collection pool and send a
    driver for goods that are already there. Deactivate it instead.
    """
    PickupLocation = apps.get_model('business', 'PickupLocation')

    for loc in PickupLocation.objects.filter(business=business, is_fulfilment_center=True):
        if loc.warehouse_id:
            if loc.pickup_status != 'inactive':
                loc.pickup_status = 'inactive'
                loc.save(update_fields=['pickup_status'])
        else:
            # Legacy shape: the client's own shop address wearing a stale stamp from
            # the removed create_fulfillment_store_on_service_enable signal. Clear the
            # flag and keep the address collectable — deactivating it would leave the
            # client with no address at all and pickup refuses on 'fulfilment_center'.
            loc.is_fulfilment_center = False
            loc.save(update_fields=['is_fulfilment_center'])


def repair(apps, schema_editor):
    Business = apps.get_model('business', 'Business')

    mis_flagged = Business.objects.filter(
        fulfillment_service_enabled=True
    ).exclude(fulfillment_service_status='active')

    now = timezone.now()
    for business in mis_flagged:
        if has_warehouse_footprint(apps, business):
            # Really on fulfilment — the status field is what is stale here, not the flag.
            business.fulfillment_service_status = 'active'
            if not business.fulfillment_activated_at:
                business.fulfillment_activated_at = now
            business.save(update_fields=[
                'fulfillment_service_status', 'fulfillment_activated_at',
            ])
        else:
            # Never onboarded. The flag is pure fallout from 0010's default.
            business.fulfillment_service_enabled = False
            business.save(update_fields=['fulfillment_service_enabled'])
            retire_fulfilment_pickup_locations(apps, business)


def noop(apps, schema_editor):
    """Not reversible: the pre-repair rows cannot be told apart from deliberate settings."""


class Migration(migrations.Migration):

    dependencies = [
        ('business', '0040_fulfillment_service_default_false'),
        ('warehouse', '0012_alter_warehouse_country'),
        ('product', '0010_product_label_print_count_product_label_printed_at_and_more'),
    ]

    operations = [
        migrations.RunPython(repair, noop),
    ]
