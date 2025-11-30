
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.contrib.auth.models import User
from orders.models import *
from delivery.models import *
import uuid
import json

# Store old verification status for tracking changes
_old_verification_status = {}

@receiver(pre_save, sender=Order)
def order_pre_save_receiver(sender, instance, *args, **kwargs):
    if not instance.order_number:
        instance.order_number = str(uuid.uuid4()).replace('-', '').upper()[:10]
        #instance.order_number = "1"
    
    # Store old verification status if instance exists
    if instance.pk:
        try:
            old_instance = Order.objects.get(pk=instance.pk)
            _old_verification_status[instance.pk] = old_instance.verification_status
        except Order.DoesNotExist:
            pass


@ receiver(post_save, sender=Order)
def order_post_save_receiver(sender, instance,  created, *args, **kwargs):
    print('order_post_save_receiver')
    if created:
        print(instance)
        if instance.order_number == "" :
            instance.order_number = str(instance.business.business_code) + '-' + str(instance.client_order_code) + '-' + str(instance.id)
            print(instance.order_number)
        
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
            from orders.models import AddressVerification
            address_verification, addr_created = AddressVerification.objects.get_or_create(
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
                            print(f"Location verification link sent for order {instance.order_number}")
                        else:
                            print(f"Failed to send location verification: {result.get('error', 'Unknown error')}")
                    else:
                        print(f"Invalid phone number for order {instance.order_number}: {error_msg}")
                except Exception as e:
                    print(f"Error sending location verification: {str(e)}")
                    import logging
                    logger = logging.getLogger(__name__)
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
        old_status = _old_verification_status.get(instance.pk, '')
        if old_status != instance.verification_status:
            from orders.models import OrderVerificationLog
            from django.utils import timezone
            
            # Log verification status change
            OrderVerificationLog.objects.create(
                order=instance,
                action='verification_status_changed',
                old_status=old_status,
                new_status=instance.verification_status,
                verified_by=instance.verified_by
            )
            
            # Auto-create delivery task when order is verified
            if instance.verification_status == 'verified' and not instance.task_created:
                _create_delivery_task_from_order(instance)
        
        # Clean up stored old status
        if instance.pk in _old_verification_status:
            del _old_verification_status[instance.pk]


def _create_delivery_task_from_order(order):
    """Create delivery task from verified order (DMS push handled by delivery signal)"""
    from django.utils import timezone
    from delivery.models import DeliveryTask, DlAddressUpdate
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
        print(f"Error creating delivery task: {str(e)}")
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error creating delivery task for order {order.id}: {str(e)}", exc_info=True)
        return None

   