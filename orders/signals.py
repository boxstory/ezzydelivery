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

    # Store old verification status if instance exists
    if instance.pk:
        try:
            old_instance = Order.objects.get(pk=instance.pk)
            instance._old_verification_status = old_instance.verification_status
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

                # Send verification link via WhatsApp
                try:
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
        
        # Clean up stored old status from instance
        if hasattr(instance, '_old_verification_status'):
            del instance._old_verification_status


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

   