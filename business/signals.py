"""
Business Signals
================

Handles automatic actions when business data changes.
"""
import logging
from django.db.models.signals import pre_save
from django.dispatch import receiver
from business.models import Business, PickupLocation

logger = logging.getLogger(__name__)


# NOTE: the old `create_fulfillment_store_on_service_enable` post_save receiver used to
# live here. Because `Business.fulfillment_service_enabled` defaults to True, it fired on
# every business's first save and stamped in an `is_fulfilment_center=True` PickupLocation
# pointing at the default warehouse — for clients who had no SellerWarehouseLink and were
# never onboarded to fulfilment. A stale FC flag makes first-mile pickup silently refuse
# (delivery/services/pickup.py -> 'fulfilment_center'), so those clients got no pickup jobs.
#
# Fulfilment pickup locations are now created in exactly one place: staff link the business
# to a warehouse in the warehouse dashboard, and `warehouse.signals
# .seller_warehouse_link_post_save` creates/updates the "WH: <name>" row (and the matching
# post_delete deactivates it on unlink). Do not reintroduce a Business-level auto-create.


@receiver(pre_save, sender=PickupLocation, dispatch_uid='business.autofill_pickup_coords_from_qnas')
def autofill_pickup_coords_from_qnas(sender, instance, **kwargs):
    """
    Auto-fill pickup_lat/pickup_lon from the QNAS address (zone/street/building)
    when the location is saved without a map pin.

    Reuses the same geocoder as order delivery addresses
    (orders.signals._geocode_address_from_qnas): exact building match first,
    then first building on street, then zone center. Never overwrites an
    existing pin — clear lat/lon and save to force a re-geocode.
    """
    if instance.pickup_lat is not None and instance.pickup_lon is not None:
        return
    if not instance.pickup_zone_no:
        return

    try:
        from orders.signals import _geocode_address_from_qnas
        lat, lng, tier = _geocode_address_from_qnas(
            instance.pickup_zone_no,
            instance.pickup_street_no,
            instance.pickup_building_no,
            area_name=instance.locality or None,
        )
        if lat is not None and lng is not None:
            instance.pickup_lat = lat
            instance.pickup_lon = lng
            logger.info(
                f"Auto-geocoded pickup location '{instance.pickup_location_title}' "
                f"(zone={instance.pickup_zone_no}, street={instance.pickup_street_no}, "
                f"building={instance.pickup_building_no}) -> ({lat}, {lng}) [{tier}]"
            )
    except Exception as e:
        logger.warning(
            f"QNAS auto-geocode failed for pickup location "
            f"'{instance.pickup_location_title}': {e}"
        )


@receiver(pre_save, sender=Business, dispatch_uid='business.track_fulfillment_service_change')
def track_fulfillment_service_change(sender, instance, **kwargs):
    """
    Track when fulfillment service is being enabled.

    This runs before save to detect if fulfillment_service_enabled
    is being changed from False to True.

    Args:
        sender: The Business model class
        instance: The Business instance being saved
        **kwargs: Additional keyword arguments
    """
    if instance.pk:  # Only for existing instances
        try:
            old_instance = Business.objects.get(pk=instance.pk)

            # Check if fulfillment service is being enabled
            if not old_instance.fulfillment_service_enabled and instance.fulfillment_service_enabled:
                logger.info(f"Fulfillment service being enabled for business {instance.business_id}")
                # Audit trail only — this no longer creates a pickup location. The
                # fulfilment pickup row is created when staff link the business to a
                # warehouse (warehouse.signals.seller_warehouse_link_post_save).

        except Business.DoesNotExist:
            pass
