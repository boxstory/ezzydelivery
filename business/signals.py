"""
Business Signals
================

Handles automatic actions when business data changes.
"""
import logging
from django.db import models
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.utils import timezone
from business.models import Business, PickupLocation
from warehouse.models import Warehouse

logger = logging.getLogger(__name__)


@receiver(post_save, sender=Business, dispatch_uid='business.create_fulfillment_store_on_service_enable')
def create_fulfillment_store_on_service_enable(sender, instance, created, **kwargs):
    """
    Automatically create a "Fulfillment Store" pickup location when
    fulfillment service is enabled for a business.

    This signal triggers when:
    - A business is created with fulfillment_service_enabled=True
    - An existing business enables fulfillment service

    Args:
        sender: The Business model class
        instance: The Business instance being saved
        created: Boolean indicating if this is a new instance
        **kwargs: Additional keyword arguments
    """
    # Check if fulfillment service is enabled
    if not instance.fulfillment_service_enabled:
        return

    # Check if fulfillment store already exists (by title OR by is_fulfilment_center flag)
    fulfillment_store_exists = PickupLocation.objects.filter(
        business=instance,
    ).filter(
        models.Q(pickup_location_title__icontains="fulfillment") |
        models.Q(pickup_location_title__icontains="fulfilment") |
        models.Q(is_fulfilment_center=True)
    ).exists()

    if fulfillment_store_exists:
        logger.debug(f"Fulfillment store already exists for business {instance.business_id}")
        return

    # Create the fulfillment pickup location carrying the real warehouse identity.
    # Warehouse resolution: the business's own active warehouse link, else the
    # default warehouse, else the first one. Generic title only if none exists.
    try:
        from warehouse.models import SellerWarehouseLink
        link = SellerWarehouseLink.objects.filter(
            business=instance, is_active=True).order_by('-is_default', 'priority').first()
        warehouse = link.warehouse if link else Warehouse.objects.order_by('-is_default', 'name').first()

        if warehouse:
            title = f"WH: {warehouse.name}"
            locality = warehouse.address or warehouse.city or 'EzzyDelivery Fulfillment Center'
            lat, lon = warehouse.latitude, warehouse.longitude
        else:
            title, locality, lat, lon = (
                "Fulfillment Store", "EzzyDelivery Fulfillment Center", None, None)

        PickupLocation.objects.create(
            business=instance,
            pickup_location_title=title,
            locality=locality,
            pickup_lat=lat,
            pickup_lon=lon,
            pickup_status='active',
            is_fulfilment_center=True,
            warehouse=warehouse,
        )
        logger.info(
            f"Created fulfilment pickup location '{title}' for business {instance.business_id}")

        # Update the fulfillment_activated_at timestamp if not already set
        if not instance.fulfillment_activated_at:
            Business.objects.filter(pk=instance.pk).update(
                fulfillment_activated_at=timezone.now()
            )
            logger.info(f"Set fulfillment_activated_at for business {instance.business_id}")

    except Exception as e:
        logger.error(f"Failed to create Fulfillment Store for business {instance.business_id}: {e}")


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
                # The post_save signal will handle creating the pickup location

        except Business.DoesNotExist:
            pass
