import logging
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
    Generate order number in format: {business_code}-{YMMDD}-{sequence}
    Example: BIZCODE-60113-AA001

    - YMMDD: Year(last digit) + Month(2 digits) + Day(2 digits)
    - Sequence: AA001-AA999, AB001-AB999, ... never resets, continues globally per business
    """
    now = timezone.localtime()

    # Format date as YMMDD (e.g., 60113 for Jan 13, 2026)
    year_digit = str(now.year)[-1]  # Last digit of year
    date_part = f"{year_digit}{now.month:02d}{now.day:02d}"

    # Get total order count for this business (never resets)
    total_orders = Order.objects.filter(business=business).count()

    # Generate sequence: AA001, AA002, ... AA999, AB001, etc.
    sequence = generate_sequence_code(total_orders + 1)

    # Build order number - use business_code, fallback to business_id or 'EZY'
    business_code = business.business_code if business.business_code else f"BIZ{business.business_id}"
    order_number = f"{business_code}-{date_part}-{sequence}"

    return order_number

@receiver(pre_save, sender=Order)
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


@ receiver(post_save, sender=Order)
def order_post_save_receiver(sender, instance,  created, *args, **kwargs):
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
                'cod_amount': instance.cod_amount,
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

                # Send verification link via WhatsApp (only if N8N webhook is configured)
                try:
                    from django.conf import settings as django_settings
                    n8n_url = getattr(django_settings, 'N8N_WHATSAPP_WEBHOOK_URL', None)
                    if n8n_url:
                        from core.whatsapp_utils import send_location_verification_whatsapp
                        from core.whatsapp_utils import validate_input_phone

                        # Validate and sanitize phone number
                        is_valid, sanitized_phone, error_msg = validate_input_phone(instance.customer_phone)

                        if is_valid:
                            result = send_location_verification_whatsapp(
                                order=instance,
                                verification_token=token,
                                phone_number=sanitized_phone
                            )

                            if result['success']:
                                logger.info(f"Location verification link sent for order {instance.order_number}")
                            else:
                                logger.warning(f"Failed to send location verification: {result.get('error', 'Unknown error')}")
                        else:
                            logger.warning(f"Invalid phone number for order {instance.order_number}: {error_msg}")
                except Exception as e:
                    logger.error(f"Error sending location verification for order {instance.id}: {str(e)}", exc_info=True)
        
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
            instance.save()
        
        if instance.order_number not in OrderBarcode.objects.values_list('order_number'):
            OrderBarcode.objects.create(
                order_id=instance.id, order_number= instance.order_number )
            instance.save()

        # OrderItem entries should be created when products are added to the order
        # Not automatically on order creation

        # Log initial order creation in status history
        try:
            _log_order_created(instance)
        except Exception as e:
            logger.error(f"Error logging order creation: {e}")

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
            
            # Auto-create delivery task when order is verified
            if instance.verification_status == 'verified' and not instance.task_created:
                # Check if batching is enabled
                from django.conf import settings
                if getattr(settings, 'DISPATCH_BATCHING_ENABLED', False):
                    # Route to batching system (async via Celery)
                    try:
                        from dispatch.tasks import process_verified_order
                        process_verified_order.delay(instance.id)
                        logger.info(f"Order {instance.order_number} queued for batch processing")
                    except Exception as e:
                        logger.error(f"Error queuing order for batching: {e}, falling back to direct task creation")
                        _create_delivery_task_from_order(instance)
                else:
                    # Legacy: direct task creation
                    _create_delivery_task_from_order(instance)
        
        # Log all status field changes to OrderStatusHistory
        _log_order_status_changes(instance)

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
        # Try ZoneName (zone_name or zone_name_arabic)
        zone_obj = delivery_models.ZoneName.objects.filter(
            Q(zone_name__iexact=term) | Q(zone_name_arabic__iexact=term)
        ).first()
        if zone_obj:
            logger.info(f"Resolved zone name '{term}' -> zone {zone_obj.zone_number}")
            return zone_obj.zone_number

        # Try ZoneArea (area_name or area_name_arabic)
        area_obj = delivery_models.ZoneArea.objects.select_related('zone').filter(
            Q(area_name__iexact=term) | Q(area_name_arabic__iexact=term)
        ).first()
        if area_obj:
            logger.info(f"Resolved area name '{term}' -> zone {area_obj.zone.zone_number}")
            return area_obj.zone.zone_number

    return None


def _geocode_address_from_qnas(zone, street, building, area_name=None):
    """
    Look up lat/lng for a Qatar address using QNAS API.

    Geocoding priority:
    1. zone + street + building -> exact building coordinates from QNAS
    2. zone + street (no building) -> first available building on street from QNAS
    3. zone only (no street) -> zone center from ZoneName model
    4. area_name only -> resolve zone from ZoneName/ZoneArea, then use zone center

    Returns (latitude, longitude) as Decimals, or (None, None) on failure.
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
                                    logger.info(f"QNAS geocoded zone={zone_number}, street={street}, building={building} -> ({lat}, {lng})")
                                    return lat, lng

                        # Building missing or not found: use first available building on street
                        first = buildings_data[0]
                        if first.get("x") and first.get("y"):
                            lat = Decimal(str(first["x"]))
                            lng = Decimal(str(first["y"]))
                            src = "first building on street" if not building else f"building {building} not found, using nearest"
                            logger.info(f"QNAS geocoded zone={zone_number}, street={street} ({src}) -> ({lat}, {lng})")
                            return lat, lng
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
                logger.info(f"Geocoded from ZoneName center: zone={zone_number} -> ({lat}, {lng})")
                return lat, lng
        except delivery_models.ZoneName.DoesNotExist:
            logger.info(f"Zone {zone_number} not found in ZoneName model")

    return None, None


def _create_delivery_task_from_order(order):
    """Create delivery task from verified order (DMS push handled by delivery signal)"""
    from django.utils import timezone
    from decimal import Decimal

    try:
        # Get or create address update
        address_update, created = DlAddressUpdate.objects.get_or_create(
            order=order,
            defaults={
                'full_name': order.customer_name,
                'dl_task_number': order.order_number,
                'mobile_no': order.customer_phone,
                'dl_zone': order.dl_zone,
                'dl_street': order.dl_street,
                'dl_building': order.dl_building,
                'dl_longitude': Decimal('0'),
                'dl_latitude': Decimal('0'),
                'dl_unit': '0',
            }
        )

        # Auto-geocode via QNAS if any address info is available
        if order.dl_zone or order.dl_street or address_update.area_name:
            lat, lng = _geocode_address_from_qnas(
                order.dl_zone, order.dl_street, order.dl_building,
                area_name=address_update.area_name
            )
            if lat is not None and lng is not None:
                address_update.dl_latitude = lat
                address_update.dl_longitude = lng
                address_update.save(update_fields=['dl_latitude', 'dl_longitude'])

        # Create delivery task (DMS push will be handled automatically by delivery_task_post_save_receiver signal)
        delivery_task = DeliveryTask.objects.create(
            dl_task_number=order.order_number,
            dl_task_number_dms=order.order_number,
            dl_task_description=f"Delivery for {order.order_number}",
            order=order,
            business=order.business,
            dl_address_update=address_update,
            dl_task_status='for_review',
            dl_task_status_dms='6',  # Unassigned
            dl_task_status_client='for_review',
            pickup_location=order.pickup_location,
        )

        # Update order
        order.task_created = True
        order.task_status = 'dl_task_listed'
        order.save(update_fields=['task_created', 'task_status'])

        # Note: DMS push is handled by delivery/signals.py to avoid duplicate API calls

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


def log_delivery_task_status_change(task, field_name, old_val, new_val, display_dict):
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
        )
    except Exception as e:
        logger.error(f"Error logging delivery task status change: {e}")
   