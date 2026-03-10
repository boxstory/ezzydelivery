from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.contrib.auth.models import User
from django.utils import timezone
from orders import models as orders_models
from delivery import models as delivery_models
from delivery.state_machine import can_transition
import uuid
import logging

# Local aliases for commonly used models
DeliveryTask = delivery_models.DeliveryTask
HubPickupBatch = delivery_models.HubPickupBatch

logger = logging.getLogger(__name__)

# Terminal order statuses — don't overwrite these
TERMINAL_ORDER_STATUSES = ['delivered', 'cancelled']


@receiver(pre_save, sender=DeliveryTask)
def delivery_task_pre_save(sender, instance, **kwargs):
    """Track old delivery task status for change detection in post_save.
    Enforces state machine rules and blocks invalid transitions."""
    if instance.pk:
        try:
            old = DeliveryTask.objects.get(pk=instance.pk)
            instance._old_dl_task_status = old.dl_task_status
            instance._old_dl_task_publish = old.dl_task_publish

            if instance.dl_task_status != old.dl_task_status:

                # Hard block: order is cancelled — only 'cancelled' is allowed
                if instance.order_id:
                    order = instance.order
                    if order.order_status == 'cancelled' and instance.dl_task_status != 'cancelled':
                        logger.warning(
                            f"Blocked delivery status change '{old.dl_task_status}' -> '{instance.dl_task_status}' "
                            f"for task {instance.dl_task_number}: order is cancelled"
                        )
                        instance.dl_task_status = old.dl_task_status
                        return

                # State machine: determine actor from instance flag set by callers
                # Callers set instance._status_actor = 'staff' or 'driver' (default: 'staff')
                actor = getattr(instance, '_status_actor', 'staff')
                allowed, reason = can_transition(old.dl_task_status, instance.dl_task_status, actor=actor)
                if not allowed:
                    logger.warning(
                        f"Blocked invalid status transition [{actor}] "
                        f"'{old.dl_task_status}' -> '{instance.dl_task_status}' "
                        f"for task {instance.dl_task_number}: {reason}"
                    )
                    instance.dl_task_status = old.dl_task_status

        except DeliveryTask.DoesNotExist:
            pass


def _sync_order_status_from_task(task):
    """
    Sync order status based on delivery task status.
    Called from post_save when dl_task_status changes.
    """
    try:
        order = task.order
        if not order:
            return

        # Don't overwrite terminal order statuses
        if order.order_status in TERMINAL_ORDER_STATUSES:
            logger.debug(f"Order {order.order_number} already in terminal status '{order.order_status}', skipping sync")
            return

        update_fields = []

        if task.dl_task_status == 'delivered':
            order.order_status = 'delivered'
            update_fields.append('order_status')
            if order.business and order.business.fulfillment_service_enabled:
                order.fulfilled_at = timezone.now()
                update_fields.append('fulfilled_at')
            order.delivered_at = timezone.now()
            update_fields.append('delivered_at')
            logger.info(f"Order {order.order_number} synced to '{order.order_status}' from delivery task {task.dl_task_number}")

        elif task.dl_task_status == 'cancelled':
            order.order_status = 'cancelled'
            update_fields.append('order_status')
            logger.info(f"Order {order.order_number} synced to 'cancelled' from delivery task {task.dl_task_number}")

        if update_fields:
            # Use update_fields to avoid triggering unrelated order signals
            order.save(update_fields=update_fields)

    except Exception as e:
        logger.exception(f"Error syncing order status from task {task.id}: {e}")


# Active DL task statuses that mean the driver is physically on the road
ACTIVE_TASK_STATUSES = [
    'picked_up', 'start_ride', 'in_transit', 'out_for_delivery',
]

# Terminal DL task statuses that mean the task is done
TERMINAL_TASK_STATUSES = ['delivered', 'failed', 'cancelled', 'rejected']


def _sync_driver_availability(task):
    """
    Auto-sync driver availability based on delivery task status changes.
    - Active task statuses → driver on_delivery
    - Terminal task statuses → driver available (only if no other active tasks)
    """
    try:
        from fleet.models import Driver
        driver = task.driver
        if not driver or driver.driver_status != 'approved':
            return

        new_dl_status = task.dl_task_status

        if new_dl_status in ACTIVE_TASK_STATUSES:
            if driver.driver_availability != 'on_delivery':
                driver.driver_availability = 'on_delivery'
                driver.save(update_fields=['driver_availability'])
                logger.info(f"Driver {driver.driver_id} availability → on_delivery (task {task.dl_task_number} status: {new_dl_status})")

        elif new_dl_status in TERMINAL_TASK_STATUSES:
            # Only set to available if no other active tasks remain
            other_active = DeliveryTask.objects.filter(
                driver=driver,
                dl_task_status__in=ACTIVE_TASK_STATUSES,
            ).exclude(pk=task.pk).exists()

            if not other_active and driver.driver_availability == 'on_delivery':
                driver.driver_availability = 'available'
                driver.save(update_fields=['driver_availability'])
                logger.info(f"Driver {driver.driver_id} availability → available (no more active tasks)")

    except Exception as e:
        logger.exception(f"Error syncing driver availability from task {task.id}: {e}")


def _send_customer_notification(task, old_status, new_status):
    """
    Fire WhatsApp notification to customer on key status changes.
    Runs in a try/except so it never blocks the main save flow.
    """
    # Map status transitions → notification events
    EVENT_MAP = {
        'assigned':         'driver_assigned',
        'out_for_delivery': 'out_for_delivery',
        'in_transit':       'out_for_delivery',   # same message for in_transit
        'delivered':        'delivered',
        'failed':           'delivery_failed',
    }
    event = EVENT_MAP.get(new_status)
    if not event:
        return

    try:
        from core.order_notifications import notify_order_event
        notify_order_event(event, task=task)
    except Exception as e:
        logger.warning(f"Customer notification failed for task {task.pk} event={event}: {e}")


def _send_location_verification_on_publish(task):
    """
    Send WhatsApp location verification link when a delivery task is published.
    Gets or creates the AddressVerification record, generates a token if needed,
    and sends via WhatsApp.
    """
    try:
        order = task.order
        if not order or not order.customer_address:
            return

        from django.conf import settings as django_settings
        n8n_url = getattr(django_settings, 'N8N_WHATSAPP_WEBHOOK_URL', None)
        if not n8n_url:
            return

        from core.whatsapp_utils import send_location_verification_whatsapp, validate_input_phone

        # Get or create AddressVerification record
        address_verification, addr_created = orders_models.AddressVerification.objects.get_or_create(
            order=order,
            defaults={
                'original_address': order.customer_address,
                'verification_result': 'pending',
            }
        )

        # Generate token if missing
        token = address_verification.verification_token
        if not token:
            token = address_verification.generate_token()
            address_verification.save()

        # Validate phone
        is_valid, sanitized_phone, error_msg = validate_input_phone(order.customer_phone)
        if not is_valid:
            logger.warning(f"Invalid phone for order {order.order_number} on publish: {error_msg}")
            return

        result = send_location_verification_whatsapp(
            order=order,
            verification_token=token,
            phone_number=sanitized_phone,
        )

        if result['success']:
            logger.info(f"Location verification link sent on publish for order {order.order_number}")
        else:
            logger.warning(f"Failed to send location verification on publish: {result.get('error', 'Unknown error')}")

    except Exception as e:
        logger.error(f"Error sending location verification on publish for task {task.pk}: {e}", exc_info=True)


def _create_task_status_point(task, old_status, new_status):
    """Create a TaskStatusPoint with driver GPS and distance from delivery location."""
    from fleet import models as fleet_models

    driver_lat = driver_lng = accuracy = None
    delivery_lat = delivery_lng = None
    distance_km = None

    # Get latest driver GPS location
    if task.driver_id:
        latest_loc = fleet_models.DriverLocation.objects.filter(
            driver_id=task.driver_id
        ).order_by('-created_at').first()
        if latest_loc:
            driver_lat = latest_loc.latitude
            driver_lng = latest_loc.longitude
            accuracy = latest_loc.accuracy

    # Get delivery location coordinates
    if task.order_id:
        order = task.order
        if order.latitude and order.longitude:
            delivery_lat = order.latitude
            delivery_lng = order.longitude
        elif task.dl_to_address and task.dl_to_address.dl_latitude and task.dl_to_address.dl_longitude:
            delivery_lat = task.dl_to_address.dl_latitude
            delivery_lng = task.dl_to_address.dl_longitude

    # Calculate distance if both points available
    if driver_lat and driver_lng and delivery_lat and delivery_lng:
        distance_km = round(
            delivery_models.TaskStatusPoint.haversine_km(
                driver_lat, driver_lng, delivery_lat, delivery_lng
            ), 3
        )

    # Also populate completion_latitude/longitude when delivered
    if new_status == 'delivered' and driver_lat and driver_lng:
        DeliveryTask.objects.filter(pk=task.pk).update(
            completion_latitude=driver_lat,
            completion_longitude=driver_lng,
        )

    delivery_models.TaskStatusPoint.objects.create(
        task=task,
        driver=task.driver,
        old_status=old_status,
        new_status=new_status,
        latitude=driver_lat,
        longitude=driver_lng,
        accuracy=accuracy,
        distance_from_delivery=distance_km,
        delivery_latitude=delivery_lat,
        delivery_longitude=delivery_lng,
    )
    logger.info(
        f"TaskStatusPoint: task {task.dl_task_number} "
        f"{old_status} → {new_status} "
        f"(driver GPS: {driver_lat},{driver_lng}, dist: {distance_km} km)"
    )


@receiver(post_save, sender=DeliveryTask)
def delivery_task_post_save_receiver(sender, instance, created, *args, **kwargs):
    """Handle delivery task creation/update side effects"""

    if created:
        # Auto-create shipping label when delivery task is created
        try:
            from delivery.label_utils import create_shipping_label
            label = create_shipping_label(instance.order, instance)
            if label:
                logger.info(f"Shipping label {label.label_number} auto-created for task {instance.dl_task_number}")
            else:
                logger.warning(f"Failed to create shipping label for task {instance.dl_task_number}")
        except Exception as e:
            logger.exception(f"Error creating shipping label for task {instance.dl_task_number}: {str(e)}")

        # Auto-create QR code for delivery task
        try:
            qrcode = delivery_models.DeliveryTaskQRCode.objects.create(
                delivery_task=instance,
                task_number=instance.dl_task_number
            )
            logger.info(f"QR code created for task {instance.dl_task_number}")
        except Exception as e:
            logger.exception(f"Error creating QR code for task {instance.dl_task_number}: {str(e)}")

    # Log delivery task status changes to order status history
    if not created and instance.order_id:
        try:
            from orders.signals import log_delivery_task_status_change
            DL_STATUS_DISPLAY = dict(DeliveryTask.dl_task_status.field.choices)

            old_dl = getattr(instance, '_old_dl_task_status', None)
            new_dl = instance.dl_task_status
            if old_dl is not None and old_dl != new_dl:
                status_notes = getattr(instance, '_status_notes', None)
                log_delivery_task_status_change(instance, 'dl_task_status', old_dl, new_dl, DL_STATUS_DISPLAY, notes=status_notes)
        except Exception as e:
            logger.error(f"Error logging delivery task status history: {e}")

    # Capture GPS point on every status change
    if not created:
        old_status = getattr(instance, '_old_dl_task_status', None)
        new_status = instance.dl_task_status
        if old_status is not None and old_status != new_status:
            try:
                _create_task_status_point(instance, old_status, new_status)
            except Exception as e:
                logger.error(f"Error creating TaskStatusPoint for task {instance.pk}: {e}")

    # Sync delivery task status → order status (for all non-creation saves)
    if not created:
        old_status = getattr(instance, '_old_dl_task_status', None)
        new_status = instance.dl_task_status
        if old_status is not None and old_status != new_status and instance.order_id:
            _sync_order_status_from_task(instance)

        # Increment failed_attempt_count when task transitions to 'failed'
        if old_status is not None and old_status != 'failed' and new_status == 'failed':
            try:
                DeliveryTask.objects.filter(pk=instance.pk).update(
                    failed_attempt_count=instance.failed_attempt_count + 1
                )
                logger.info(f"Task {instance.dl_task_number} failed_attempt_count → {instance.failed_attempt_count + 1}")
            except Exception as e:
                logger.exception(f"Error incrementing failed_attempt_count for task {instance.pk}: {e}")

        # Notify driver when task is assigned to them
        if old_status is not None and new_status == 'assigned' and instance.driver_id:
            try:
                from fleet.models import DriverNotification
                DriverNotification.objects.create(
                    driver=instance.driver,
                    title='New Task Assigned',
                    message=f'You have been assigned task {instance.dl_task_number} for order {instance.order.order_number if instance.order_id else ""}.',
                    notification_type='delivery_assigned',
                    related_task=instance,
                )
                logger.info(f"DriverNotification created for driver {instance.driver_id} — task {instance.dl_task_number} assigned")
            except Exception as e:
                logger.warning(f"Could not create driver notification for task assignment {instance.pk}: {e}")

        # --- Customer WhatsApp notifications ---
        if old_status is not None and old_status != new_status:
            _send_customer_notification(instance, old_status, new_status)

    # Send WhatsApp location verification when task is published
    if not created:
        old_publish = getattr(instance, '_old_dl_task_publish', None)
        if old_publish is False and instance.dl_task_publish is True:
            _send_location_verification_on_publish(instance)

    # Sync delivery task status → driver availability
    if instance.driver_id:
        old_dl = getattr(instance, '_old_dl_task_status', None)
        new_dl = instance.dl_task_status
        if created or (old_dl is not None and old_dl != new_dl):
            _sync_driver_availability(instance)


# =============================================================================
# HUB PICKUP BATCH SIGNALS
# =============================================================================


@receiver(pre_save, sender=HubPickupBatch)
def hub_batch_pre_save(sender, instance, **kwargs):
    """Track old batch status for change detection in post_save."""
    if instance.pk:
        try:
            old = HubPickupBatch.objects.get(pk=instance.pk)
            instance._old_batch_status = old.status
        except HubPickupBatch.DoesNotExist:
            pass


@receiver(post_save, sender=HubPickupBatch)
def hub_batch_post_save(sender, instance, created, **kwargs):
    """
    When a hub pickup batch reaches 'at_hub':
    - Auto-create hub_delivery DeliveryTask for each order in the batch
    - Process driver earnings for the batch pickup ride
    """
    old_status = getattr(instance, '_old_batch_status', None)

    if not created and old_status != 'at_hub' and instance.status == 'at_hub':
        _create_hub_delivery_tasks(instance)


def _create_hub_delivery_tasks(batch):
    """
    Auto-create a hub_delivery DeliveryTask (Leg 2) for each order in the batch.
    Tasks start as 'for_review' and are NOT published — staff publishes each
    delivery individually after reviewing.

    Also records batch pickup earnings for the driver via WalletService.
    """
    from decimal import Decimal

    created_count = 0
    for order in batch.orders.select_related('business', 'pickup_location').all():
        # Skip if delivery task already exists for this order
        if order.delivery_task.filter(task_leg='hub_delivery').exists():
            logger.info(f"Hub delivery task already exists for order {order.order_number}, skipping.")
            continue

        # Get address update created at publish time
        address_update = order.dl_address_update.first()
        if not address_update:
            logger.warning(
                f"No DlAddressUpdate found for hub order {order.order_number} — "
                f"delivery task created without address."
            )

        try:
            task = DeliveryTask.objects.create(
                dl_task_number=f"{order.order_number}-D",
                dl_task_description=f"Hub Delivery — {order.order_number}",
                order=order,
                business=order.business,
                dl_address_update=address_update,
                dl_task_status='for_review',
                dl_task_status_client='for_review',
                pickup_location=None,   # pickup origin is the hub, not a PickupLocation
                task_leg='hub_delivery',
                hub_pickup_batch=batch,
                hub_warehouse=batch.hub_warehouse,
            )

            # Mark order as ready for last-mile dispatch
            order.order_status = 'ready_to_pickup'
            order.save(update_fields=['order_status'])

            created_count += 1
            logger.info(
                f"Hub delivery task {task.dl_task_number} created for order "
                f"{order.order_number} (batch {batch.batch_number})"
            )

        except Exception as e:
            logger.exception(
                f"Error creating hub delivery task for order {order.order_number}: {e}"
            )

    # Record batch pickup earnings for the driver
    if batch.driver_id and not batch.earnings_processed and batch.driver_earnings > 0:
        try:
            from fleet.wallet_service import WalletService
            WalletService.record_earnings_from_batch_pickup(batch)
        except Exception as e:
            logger.exception(
                f"Error recording batch pickup earnings for batch {batch.batch_number}: {e}"
            )

    # Mark batch completed_at
    if created_count > 0:
        HubPickupBatch.objects.filter(pk=batch.pk).update(completed_at=timezone.now())

    logger.info(
        f"Hub batch {batch.batch_number}: created {created_count} delivery tasks, "
        f"earnings_processed={batch.earnings_processed}"
    )
