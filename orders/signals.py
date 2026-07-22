import logging
from django.db import transaction
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.contrib.auth.models import User
from django.utils import timezone
from django.db.models import Max
from orders import models as orders_models
from delivery import models as delivery_models
import uuid
import json

# Local aliases for commonly used models
Order = orders_models.Order
OrderBarcode = orders_models.OrderBarcode
AddressVerification = orders_models.AddressVerification
OrderVerificationLog = orders_models.OrderVerificationLog
DlAddressUpdate = delivery_models.DlAddressUpdate
DeliveryTask = delivery_models.DeliveryTask

logger = logging.getLogger('orders')

# Old verification status is stored on the instance as instance._old_verification_status
# to avoid thread-safety issues with a global dict.


def generate_sequence_code(number):
    """
    Generate sequence code: AA001-AA999, AB001-AB999, AC001-AC999, etc.
    After AZ999 -> BA001, etc.

    - number: 1-based order count
    - Returns: AA001, AA002, ... AA999, AB001, ... AZ999, BA001, ...
    """
    # Calculate which group of 999 we're in (0-indexed)
    group = (number - 1) // 999
    # Position within the group (1-999)
    position = ((number - 1) % 999) + 1

    # First letter: A, B, C, ... Z (group // 26)
    # Second letter: A, B, C, ... Z (group % 26)
    first_letter = chr(ord('A') + (group // 26) % 26)
    second_letter = chr(ord('A') + (group % 26))

    return f"{first_letter}{second_letter}{position:03d}"


def generate_order_number(business, client_order_code):
    """
    Generate order number in format: {business_code}-{client_order_code}-{global_sequence}
    Example: BZH092-3789-AA001

    - client_order_code: full client order ID (or YMMDD fallback)
    - Sequence: AA001-AA999, AB001-AB999, ... global across ALL orders (not per business)
    """
    # Use client_order_code as the middle part — last 5 digits, stripped of separators
    if client_order_code and client_order_code not in ('ORD', ''):
        import re
        # Remove separators: . - _ #
        cleaned = re.sub(r'[.\-_#]', '', str(client_order_code).strip())
        # Take last 5 characters if longer than 5
        code_part = cleaned[-5:] if len(cleaned) > 5 else cleaned
    else:
        # Fallback to YMMDD date if no client order code
        now = timezone.localtime()
        year_digit = str(now.year)[-1]
        code_part = f"{year_digit}{now.month:02d}{now.day:02d}"

    # Get total order count across ALL businesses (global sequence)
    total_orders = Order.objects.count()

    # Generate sequence: AA001, AA002, ... AA999, AB001, etc.
    sequence = generate_sequence_code(total_orders + 1)

    # Build order number - use business_code, fallback to business_id or 'EZY'
    business_code = business.business_code if business.business_code else f"BIZ{business.business_id}"
    order_number = f"{business_code}-{code_part}-{sequence}"

    return order_number

def _create_pickup_task_on_commit(order_id):
    """Runs after the creating transaction commits — order row is guaranteed visible."""
    from delivery.services.pickup import create_pickup_task_if_needed
    order = Order.objects.filter(pk=order_id).select_related('business', 'pickup_location').first()
    if order:
        create_pickup_task_if_needed(order, source='order_create')


@receiver(pre_save, sender=Order, dispatch_uid='orders.order_pre_save')
def order_pre_save_receiver(sender, instance, *args, **kwargs):
    if not instance.order_number:
        # Generate order number: {business_code}-{client_order_code}-{YMMDD}-{sequence}
        instance.order_number = generate_order_number(
            instance.business,
            instance.client_order_code or 'ORD'
        )

    # Store old status values for change detection
    if instance.pk:
        try:
            old_instance = Order.objects.get(pk=instance.pk)
            instance._old_verification_status = old_instance.verification_status
            instance._old_order_status = old_instance.order_status
            instance._old_task_status = old_instance.task_status
            instance._old_cod_status_by_staff = old_instance.cod_status_by_staff
        except Order.DoesNotExist:
            pass


@receiver(post_save, sender=Order, dispatch_uid='orders.order_post_save')
def order_post_save_receiver(sender, instance, created, *args, **kwargs):
    logger.debug('order_post_save_receiver')
    if created:
        logger.debug(f'New order created: {instance}')
        if not instance.order_number or instance.order_number == "":
            # Fallback order number generation
            business_code = instance.business.business_code if instance.business.business_code else f"BIZ{instance.business.business_id}"
            instance.order_number = f"{business_code}-{instance.id}"
            instance.save(update_fields=['order_number'])
            logger.debug(f'Generated fallback order_number: {instance.order_number}')
        
        # Save original order data as proof
        if not instance.original_order_data:
            from django.utils import timezone
            instance.original_order_data = {
                'order_number': instance.order_number,
                'client_order_code': instance.client_order_code,
                'customer_name': instance.customer_name,
                'customer_phone': instance.customer_phone,
                'customer_address': instance.customer_address,
                'cod_amount': str(instance.cod_amount) if instance.cod_amount is not None else None,
                'order_status': instance.order_status,
                'created_at': timezone.now().isoformat(),
                'business_id': instance.business.business_id,
            }
            instance.save(update_fields=['original_order_data'])
        
        # Create initial address verification record and send verification link
        if instance.customer_address:
            address_verification, addr_created = orders_models.AddressVerification.objects.get_or_create(
                order=instance,
                defaults={
                    'original_address': instance.customer_address,
                    'verification_result': 'pending'
                }
            )

            # Generate verification token and send WhatsApp link
            if addr_created or not address_verification.verification_token:
                token = address_verification.generate_token()
                address_verification.save()

                # WhatsApp verification link is sent later when the delivery task is published
                # (see delivery/signals.py → _send_location_verification_on_publish)
        
        if instance.order_number not in DlAddressUpdate.objects.values_list('dl_task_number', flat=True):
            from decimal import Decimal
            DlAddressUpdate.objects.create(
                full_name=instance.customer_name,
                order_id=instance.id,
                dl_task_number=instance.order_number,
                mobile_no=instance.customer_phone,
                dl_zone=instance.dl_zone,
                dl_street=instance.dl_street,
                dl_building=instance.dl_building,
                dl_longitude=Decimal('0'),
                dl_latitude=Decimal('0'))

        if instance.order_number not in OrderBarcode.objects.values_list('order_number', flat=True):
            OrderBarcode.objects.create(
                order_id=instance.id, order_number=instance.order_number)

        # OrderItem entries should be created when products are added to the order
        # Not automatically on order creation

        # Log initial order creation in status history
        try:
            _log_order_created(instance)
        except Exception as e:
            logger.error(f"Error logging order creation: {e}")

        # Fire auto flows for order creation
        try:
            from core.auto_flow_executor import execute_flows_for_trigger
            execute_flows_for_trigger('staff_order_create', extra_context={
                'order_number': instance.order_number or '',
                'customer_name': instance.customer_name or '',
                'customer_phone': instance.customer_phone or '',
                'customer_address': instance.customer_address or '',
                'cod_amount': str(instance.cod_amount) if instance.cod_amount else '0',
                'business_name': str(instance.business) if instance.business else '',
                'zone': str(instance.dl_zone) if instance.dl_zone else '',
            })
        except Exception as e:
            logger.warning(f"Auto flow failed for order create {instance.pk}: {e}")

        # First-mile pickup: auto-create a pickup task for non-fulfilment clients
        # with pickup_task_enabled (service gates internally; never raises).
        transaction.on_commit(
            lambda order_id=instance.pk: _create_pickup_task_on_commit(order_id)
        )

    # Handle verification status changes
    if not created:
        old_status = getattr(instance, '_old_verification_status', '')
        if old_status != instance.verification_status:
            from django.utils import timezone

            # Log verification status change
            orders_models.OrderVerificationLog.objects.create(
                order=instance,
                action='verification_status_changed',
                old_status=old_status,
                new_status=instance.verification_status,
                verified_by=instance.verified_by
            )

            # Fire auto flows for order verify
            try:
                from core.auto_flow_executor import execute_flows_for_trigger
                execute_flows_for_trigger('staff_order_verify', extra_context={
                    'order_number': instance.order_number or '',
                    'customer_name': instance.customer_name or '',
                    'customer_phone': instance.customer_phone or '',
                    'customer_address': instance.customer_address or '',
                    'cod_amount': str(instance.cod_amount) if instance.cod_amount else '0',
                    'business_name': str(instance.business) if instance.business else '',
                    'zone': str(instance.dl_zone) if instance.dl_zone else '',
                })
            except Exception as e:
                logger.warning(f"Auto flow failed for order verify {instance.pk}: {e}")
            
        # Log all status field changes to OrderStatusHistory
        _log_order_status_changes(instance)

        # Fire auto flows for order status changes
        old_order_status = getattr(instance, '_old_order_status', '')
        if old_order_status and old_order_status != instance.order_status:
            order_ctx = {
                'order_number': instance.order_number or '',
                'customer_name': instance.customer_name or '',
                'customer_phone': instance.customer_phone or '',
                'customer_address': instance.customer_address or '',
                'cod_amount': str(instance.cod_amount) if instance.cod_amount else '0',
                'business_name': str(instance.business) if instance.business else '',
                'zone': str(instance.dl_zone) if instance.dl_zone else '',
                'task_status': instance.order_status or '',
            }
            try:
                from core.auto_flow_executor import execute_flows_for_trigger
                if instance.order_status == 'publish':
                    execute_flows_for_trigger('staff_order_publish', order=instance, extra_context=order_ctx)
                elif instance.order_status == 'cancelled':
                    execute_flows_for_trigger('staff_order_cancel', order=instance, extra_context=order_ctx)
            except Exception as e:
                logger.warning(f"Auto flow failed for order status change {instance.pk}: {e}")

        # Auto-create delivery task when order is published
        if instance.order_status == 'publish' and old_order_status != 'publish' and not instance.task_created:
            from django.conf import settings
            if getattr(settings, 'DISPATCH_BATCHING_ENABLED', False):
                try:
                    from dispatch.tasks import process_verified_order
                    process_verified_order.delay(instance.id)
                    logger.info(f"Order {instance.order_number} queued for batch processing")
                except Exception as e:
                    logger.error(f"Error queuing order for batching: {e}, falling back to direct task creation")
                    _create_delivery_task_from_order(instance)
            else:
                _create_delivery_task_from_order(instance)

        # Send customer WhatsApp notification on order cancellation
        old_order_status2 = getattr(instance, '_old_order_status', '')
        if instance.order_status == 'cancelled' and old_order_status2 != 'cancelled':
            # Cancel guard: an order cancellation pulls its first-mile pickup task
            try:
                from delivery.services.pickup import cancel_pickup_for_order
                cancel_pickup_for_order(instance)
            except Exception as e:
                logger.warning(f"Pickup cancel guard failed for order {instance.pk}: {e}")
            try:
                from core.order_notifications import notify_order_event
                notify_order_event('order_cancelled', order=instance)
            except Exception as e:
                logger.warning(f"Cancellation notification failed for order {instance.order_number}: {e}")
            # Fire wa_order_cancelled auto flows
            try:
                from core.auto_flow_executor import execute_flows_for_trigger
                execute_flows_for_trigger('wa_order_cancelled', extra_context={
                    'order_number': instance.order_number or '',
                    'customer_name': instance.customer_name or '',
                    'customer_phone': instance.customer_phone or '',
                    'customer_address': instance.customer_address or '',
                    'cod_amount': str(instance.cod_amount) if instance.cod_amount else '0',
                    'business_name': str(instance.business) if instance.business else '',
                })
            except Exception as e:
                logger.warning(f"Auto flow failed for wa_order_cancelled {instance.pk}: {e}")

        # Clean up stored old status from instance
        for attr in ('_old_verification_status', '_old_order_status', '_old_task_status', '_old_cod_status_by_staff'):
            if hasattr(instance, attr):
                delattr(instance, attr)


def _resolve_zone_number(zone, area_name=None):
    """
    Resolve a zone number from various inputs.
    - If zone is already a valid integer, return it.
    - If zone is a zone name string, look it up in ZoneName/ZoneArea.
    - If area_name is provided, try matching it to get the zone number.
    Returns zone number (int) or None.
    """
    # Already a number
    if zone and str(zone).isdigit() and int(str(zone)) > 0:
        return int(str(zone))

    # Try zone as a name string
    zone_str = str(zone).strip() if zone else ''
    search_terms = [t for t in [zone_str, area_name] if t]

    if not search_terms:
        return None

    from django.db.models import Q
    for term in search_terms:
        if not term:
            continue
        # Try ZoneName (zone_name or zone_name_arabic) - exact first, then contains
        zone_obj = delivery_models.ZoneName.objects.filter(
            Q(zone_name__iexact=term) | Q(zone_name_arabic__iexact=term)
        ).first()
        if zone_obj:
            logger.info(f"Resolved zone name '{term}' -> zone {zone_obj.zone_number}")
            return zone_obj.zone_number

        # Try ZoneArea (area_name or area_name_arabic) - exact first, then contains
        area_obj = delivery_models.ZoneArea.objects.select_related('zone').filter(
            Q(area_name__iexact=term) | Q(area_name_arabic__iexact=term)
        ).first()
        if area_obj:
            logger.info(f"Resolved area name '{term}' -> zone {area_obj.zone.zone_number}")
            return area_obj.zone.zone_number

    # Fallback: check if any area_name appears within the search terms
    for term in search_terms:
        if not term or len(term) < 4:
            continue
        # icontains match
        zone_obj = delivery_models.ZoneName.objects.filter(
            Q(zone_name__icontains=term) | Q(zone_name_arabic__icontains=term)
        ).first()
        if zone_obj:
            logger.info(f"Resolved zone name (partial) '{term}' -> zone {zone_obj.zone_number}")
            return zone_obj.zone_number

        area_obj = delivery_models.ZoneArea.objects.select_related('zone').filter(
            Q(area_name__icontains=term) | Q(area_name_arabic__icontains=term)
        ).first()
        if area_obj:
            logger.info(f"Resolved area name (partial) '{term}' -> zone {area_obj.zone.zone_number}")
            return area_obj.zone.zone_number

    # Reverse: check if any ZoneArea area_name exists within the full address
    full_text = ' '.join(t for t in search_terms if t).lower()
    if len(full_text) >= 4:
        for area in delivery_models.ZoneArea.objects.select_related('zone').filter(is_active=True):
            if area.area_name.lower() in full_text:
                logger.info(f"Resolved area name (reverse) '{area.area_name}' -> zone {area.zone.zone_number}")
                return area.zone.zone_number

    return None


def _geocode_address_from_qnas(zone, street, building, area_name=None):
    """
    Look up lat/lng for a Qatar address using QNAS API.

    Geocoding priority (returned tier in parentheses):
    1. zone + street + building -> exact building coordinates from QNAS ('exact')
    2. zone + street (no building) -> first available building on street ('street')
    3. zone only (no street) -> zone center from ZoneName model ('zone_center')
    4. area_name only -> resolve zone, then use zone center ('zone_center')

    Returns (latitude, longitude, tier) — tier is one of the Order.COORDS_ACCURACY
    keys ('exact', 'street', 'zone_center'), or (None, None, None) on failure.
    """
    import requests
    from decimal import Decimal
    from decouple import config

    # Step 1: Resolve zone number (handles zone names, area names)
    zone_number = _resolve_zone_number(zone, area_name)

    # If we have zone + street, try QNAS API for building-level coordinates
    if zone_number and street:
        token = config("QNAS_TOKEN", default="")
        domain = config("QNAS_DOMAIN", default="ezzydelivery.qa")

        if not token:
            logger.warning("QNAS_TOKEN not configured, skipping QNAS geocoding")
        else:
            headers = {
                "X-Token": token,
                "X-Domain": domain,
                "Accept": "application/json",
                "User-Agent": "EzzyDelivery/1.0",
                "Referer": f"https://{domain}/",
                "Origin": f"https://{domain}",
            }

            try:
                url = f"https://qnas.qa/get_buildings/{zone_number}/{street}"
                resp = requests.get(url, headers=headers, timeout=10)

                if resp.status_code == 200:
                    buildings_data = resp.json()
                    if isinstance(buildings_data, list) and buildings_data:
                        # Try exact building match
                        if building:
                            building_str = str(building)
                            for b in buildings_data:
                                if str(b.get("building_number", "")) == building_str:
                                    lat = Decimal(str(b["x"]))
                                    lng = Decimal(str(b["y"]))
                                    logger.info(f"QNAS geocoded zone={zone_number}, street={street}, building={building} -> ({lat}, {lng}) [exact]")
                                    return lat, lng, 'exact'

                        # Building missing or not found: use first available building on street
                        first = buildings_data[0]
                        if first.get("x") and first.get("y"):
                            lat = Decimal(str(first["x"]))
                            lng = Decimal(str(first["y"]))
                            src = "first building on street" if not building else f"building {building} not found, using nearest"
                            logger.info(f"QNAS geocoded zone={zone_number}, street={street} ({src}) -> ({lat}, {lng}) [street]")
                            return lat, lng, 'street'
                    else:
                        logger.info(f"QNAS returned no buildings for zone={zone_number}, street={street}")
                else:
                    logger.warning(f"QNAS API returned {resp.status_code} for zone={zone_number}, street={street}")

            except Exception as e:
                logger.error(f"QNAS geocoding error for zone={zone_number}, street={street}, building={building}: {e}")

    # Step 2: Fallback to zone center from ZoneName model
    if zone_number:
        try:
            zone_obj = delivery_models.ZoneName.objects.get(zone_number=zone_number)
            if zone_obj.latitude and zone_obj.longitude:
                lat = Decimal(str(zone_obj.latitude))
                lng = Decimal(str(zone_obj.longitude))
                logger.info(f"Geocoded from ZoneName center: zone={zone_number} -> ({lat}, {lng}) [zone_center]")
                return lat, lng, 'zone_center'
        except delivery_models.ZoneName.DoesNotExist:
            logger.info(f"Zone {zone_number} not found in ZoneName model")

    return None, None, None


def _create_delivery_task_from_order(order):
    """Create delivery task from verified order (DMS push handled by delivery signal)"""
    from django.utils import timezone
    from decimal import Decimal
    from business.models import PickupLocation

    try:
        # Auto-assign pickup location if not set:
        # Priority: active fulfilment centre → default active → first active
        if not order.pickup_location_id:
            fallback_pl = (
                PickupLocation.objects.filter(
                    business=order.business,
                    pickup_status='active',
                    is_fulfilment_center=True,
                ).order_by('-is_default', 'id').first()
                or
                PickupLocation.objects.filter(
                    business=order.business,
                    pickup_status='active',
                ).order_by('-is_default', 'id').first()
            )
            if fallback_pl:
                order.pickup_location = fallback_pl
                order.save(update_fields=['pickup_location'])
                logger.info(
                    f"Order {order.order_number}: auto-assigned pickup location "
                    f"'{fallback_pl.pickup_location_title}' "
                    f"(fulfilment={fallback_pl.is_fulfilment_center})"
                )

        # For fulfillment orders, auto-assign the best warehouse location as hub_warehouse
        if (order.pickup_location and order.pickup_location.is_fulfilment_center
                and not order.hub_warehouse_id):
            try:
                from warehouse.utils import get_recommended_warehouse_location
                wh_location = get_recommended_warehouse_location(order)
                if wh_location:
                    order.hub_warehouse = wh_location
                    order.save(update_fields=['hub_warehouse'])
                    logger.info(
                        f"Order {order.order_number}: auto-assigned hub_warehouse "
                        f"'{wh_location.warehouse.name} / {wh_location.name}' via priority"
                    )
            except Exception as e:
                logger.warning(f"hub_warehouse auto-assign failed for {order.order_number}: {e}")

        # Hub delivery orders: delivery task created later when batch arrives at hub.
        # Ensure address update and geocode are still created, but skip task creation.
        if order.is_hub_delivery:
            DlAddressUpdate.objects.get_or_create(
                order=order,
                defaults={
                    'full_name': order.customer_name or '',
                    'dl_task_number': order.order_number,
                    'mobile_no': order.customer_phone or '',
                    'dl_zone': order.dl_zone,
                    'dl_street': order.dl_street,
                    'dl_building': order.dl_building,
                    'dl_latitude': order.latitude or Decimal('0'),
                    'dl_longitude': order.longitude or Decimal('0'),
                    'dl_unit': '0',
                    'area_name': order.customer_address or '',
                }
            )
            logger.info(
                f"Order {order.order_number}: hub delivery — "
                f"delivery task will be created after hub pickup batch arrives at hub."
            )
            order.task_created = False
            order.task_status = 'awaiting_hub_pickup'
            order.save(update_fields=['task_created', 'task_status'])
            return None

        # Get or create address update — seed with all available order coords
        address_update, created = DlAddressUpdate.objects.get_or_create(
            order=order,
            defaults={
                'full_name': order.customer_name or '',
                'dl_task_number': order.order_number,
                'mobile_no': order.customer_phone or '',
                'dl_zone': order.dl_zone,
                'dl_street': order.dl_street,
                'dl_building': order.dl_building,
                'dl_latitude': order.latitude or Decimal('0'),
                'dl_longitude': order.longitude or Decimal('0'),
                'dl_unit': '0',
                'area_name': order.customer_address or '',
            }
        )

        # If record already existed, sync any updated order coords into it
        if not created:
            addr_dirty = False
            if order.dl_zone is not None and address_update.dl_zone != order.dl_zone:
                address_update.dl_zone = order.dl_zone
                addr_dirty = True
            if order.dl_street is not None and address_update.dl_street != order.dl_street:
                address_update.dl_street = order.dl_street
                addr_dirty = True
            if order.dl_building is not None and address_update.dl_building != order.dl_building:
                address_update.dl_building = order.dl_building
                addr_dirty = True
            if order.latitude and (not address_update.dl_latitude or address_update.dl_latitude == Decimal('0')):
                address_update.dl_latitude = order.latitude
                addr_dirty = True
            if order.longitude and (not address_update.dl_longitude or address_update.dl_longitude == Decimal('0')):
                address_update.dl_longitude = order.longitude
                addr_dirty = True
            if addr_dirty:
                address_update.save()

        # Auto-geocode via QNAS if no coords yet
        if not address_update.dl_latitude or address_update.dl_latitude == Decimal('0'):
            if order.dl_zone or order.dl_street or address_update.area_name:
                lat, lng, tier = _geocode_address_from_qnas(
                    order.dl_zone, order.dl_street, order.dl_building,
                    area_name=address_update.area_name
                )
                if lat is not None and lng is not None:
                    address_update.dl_latitude = lat
                    address_update.dl_longitude = lng
                    address_update.save(update_fields=['dl_latitude', 'dl_longitude'])
                    order_dirty_fields = []
                    if not order.latitude or order.latitude == Decimal('0'):
                        order.latitude = lat
                        order_dirty_fields.append('latitude')
                    if not order.longitude or order.longitude == Decimal('0'):
                        order.longitude = lng
                        order_dirty_fields.append('longitude')
                    if tier and order.coords_accuracy != tier:
                        order.coords_accuracy = tier
                        order_dirty_fields.append('coords_accuracy')
                    if order_dirty_fields:
                        order.save(update_fields=order_dirty_fields)

        # Map delivery_speed → dl_speed
        _dl_speed_map = {'same_day': 'Same Day', 'express': 'On Demand'}
        dl_speed = _dl_speed_map.get(order.delivery_speed, 'Normal')

        # Map Order.coords_accuracy → DeliveryTask.address_accuracy
        # Keys must match Order.COORDS_ACCURACY choices (orders/models.py)
        coords_to_accuracy = {
            'by_customer': 'by_customer',
            'by_staff':    'by_staff',
            'by_driver':   'by_driver',
            'exact':       'geocoded',
            'street':      'geocoded',
            'landmark':    'geocoded',
            'zone_center': 'geocoded',
            'ai_estimate': 'geocoded',
        }
        address_accuracy = coords_to_accuracy.get(order.coords_accuracy or '', 'unverified')

        # Task date: use scheduled date if set, else today
        import datetime as _dt
        task_date = order.scheduled_date if order.scheduled_delivery and order.scheduled_date else _dt.date.today()

        # Preferred time: use scheduled_time if set
        preferred_time = ''
        if order.scheduled_delivery and order.scheduled_time:
            hour = order.scheduled_time.hour
            if hour < 13:
                preferred_time = '9am-1pm'
            elif hour < 18:
                preferred_time = '2pm-6pm'
            else:
                preferred_time = '6pm-10pm'

        # Create delivery task with all mapped fields
        delivery_task = DeliveryTask.objects.create(
            dl_task_number=order.order_number,
            dl_task_description=(order.package_description or f"Delivery for {order.order_number}")[:100],
            order=order,
            business=order.business,
            dl_address_update=address_update,
            dl_task_status='for_review',
            dl_task_status_client='for_review',
            pickup_location=order.pickup_location,
            task_leg='single',
            dl_task_date=task_date,
            dl_price=order.dl_amount or 0,
            dl_waight=order.package_qty or 1,
            dl_speed=dl_speed,
            preferred_time=preferred_time,
            address_accuracy=address_accuracy,
        )

        # Update order
        order.task_created = True
        order.task_status = 'dl_task_listed'
        order.save(update_fields=['task_created', 'task_status'])

        return delivery_task
    except Exception as e:
        logger.error(f"Error creating delivery task for order {order.id}: {str(e)}", exc_info=True)
        return None


# ---- Status history tracking helpers ----

# Display name lookups for status fields
_ORDER_STATUS_DISPLAY = dict(orders_models.ORDER_STATUS_BY_CLIENT)
_TASK_STATUS_DISPLAY = dict(orders_models.TASK_STATUS_BY_STAFF)
_VERIFICATION_DISPLAY = dict(orders_models.Order.VERIFICATION_STATUS)
_COD_STATUS_DISPLAY = dict(orders_models.COD_STATUS_BY_STAFF)

_STATUS_FIELDS = [
    # (field_name, old_attr, display_dict)
    ('order_status', '_old_order_status', _ORDER_STATUS_DISPLAY),
    ('task_status', '_old_task_status', _TASK_STATUS_DISPLAY),
    ('verification_status', '_old_verification_status', _VERIFICATION_DISPLAY),
    ('cod_status_by_staff', '_old_cod_status_by_staff', _COD_STATUS_DISPLAY),
]


def _log_order_status_changes(instance):
    """Log all changed status fields on an Order to OrderStatusHistory."""
    OrderStatusHistory = orders_models.OrderStatusHistory
    entries = []
    for field_name, old_attr, display_dict in _STATUS_FIELDS:
        old_val = getattr(instance, old_attr, None)
        new_val = getattr(instance, field_name, None)
        if old_val is not None and old_val != new_val:
            entries.append(OrderStatusHistory(
                order=instance,
                field_name=field_name,
                old_value=old_val or '',
                new_value=new_val or '',
                old_display=display_dict.get(old_val, old_val or ''),
                new_display=display_dict.get(new_val, new_val or ''),
                changed_by=getattr(instance, '_status_changed_by', None),
            ))
    if entries:
        OrderStatusHistory.objects.bulk_create(entries)


def _log_order_created(instance):
    """Log initial status values when an order is first created."""
    OrderStatusHistory = orders_models.OrderStatusHistory
    OrderStatusHistory.objects.create(
        order=instance,
        field_name='order_status',
        old_value='',
        new_value=instance.order_status,
        old_display='',
        new_display=_ORDER_STATUS_DISPLAY.get(instance.order_status, instance.order_status),
        notes='Order created',
    )


def log_delivery_task_status_change(task, field_name, old_val, new_val, display_dict, notes=None):
    """Log a delivery task status change to the order's status history."""
    OrderStatusHistory = orders_models.OrderStatusHistory
    try:
        OrderStatusHistory.objects.create(
            order=task.order,
            field_name=field_name,
            old_value=old_val or '',
            new_value=new_val or '',
            old_display=display_dict.get(old_val, old_val or ''),
            new_display=display_dict.get(new_val, new_val or ''),
            notes=notes or '',
        )
    except Exception as e:
        logger.error(f"Error logging delivery task status change: {e}")
   

# ============================================================================
# WAREHOUSE INVENTORY MANAGEMENT SIGNALS
# ============================================================================
# REMOVED: adjust_warehouse_inventory_on_status_change and delivery_task_pre_save_receiver
# These were duplicating the reservation-based inventory system in warehouse/signals.py.
# The correct flow is: reserve on ready_to_pickup → fulfill on delivered → release on cancelled.
# All handled by warehouse/signals.py (reserve_stock_for_order, fulfill_stock_reservation,
# release_stock_reservation, return_stock_on_failed_delivery).
# ============================================================================
