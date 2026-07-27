from django.db.models.signals import post_save, post_delete, pre_save
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
ZoneName = delivery_models.ZoneName
ZoneArea = delivery_models.ZoneArea

logger = logging.getLogger(__name__)

# Terminal order statuses — don't overwrite these
TERMINAL_ORDER_STATUSES = ['delivered', 'cancelled']


@receiver(pre_save, sender=DeliveryTask)
def delivery_task_pre_save(sender, instance, **kwargs):
    """Track old delivery task status for change detection in post_save.
    Enforces state machine rules and blocks invalid transitions."""
    # Auto-generate tracking token for customer tracking page
    if not instance.tracking_token:
        instance.tracking_token = uuid.uuid4().hex[:12]

    if instance.pk:
        try:
            old = DeliveryTask.objects.get(pk=instance.pk)
            instance._old_dl_task_status = old.dl_task_status
            instance._old_dl_task_publish = old.dl_task_publish
            instance._old_dl_task_date = old.dl_task_date

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

        # Partial delivery is treated as Delivered for the order/client
        # (the customer kept some items and it shows as Delivered to them).
        if task.dl_task_status in ('delivered', 'partial_delivery'):
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
    Checks AutoTriggerConfig to see if each trigger is enabled.
    """
    # Map status transitions → notification events and trigger keys
    EVENT_MAP = {
        'assigned':         ('driver_assigned', 'wa_driver_assigned'),
        'out_for_delivery': ('out_for_delivery', 'wa_out_for_delivery'),
        'in_transit':       ('out_for_delivery', 'wa_out_for_delivery'),
        'delivered':        ('delivered', 'wa_delivered'),
        'failed':           ('delivery_failed', 'wa_delivery_failed'),
    }
    entry = EVENT_MAP.get(new_status)
    if not entry:
        return
    event, trigger_key = entry

    try:
        from core.models import AutoTriggerConfig
        if not AutoTriggerConfig.is_trigger_enabled(trigger_key):
            logger.debug(f"WhatsApp trigger '{trigger_key}' is disabled, skipping notification")
            return
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
        from core.models import AutoTriggerConfig
        if not AutoTriggerConfig.is_trigger_enabled('wa_location_verification'):
            logger.debug("WhatsApp trigger 'wa_location_verification' is disabled, skipping")
            return

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

    status_point = delivery_models.TaskStatusPoint.objects.create(
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

    # Fix 17: Proximity check — flag deliveries completed >5km from destination
    if new_status == 'delivered' and distance_km is not None and distance_km > 5.0:
        logger.warning(
            f"PROXIMITY FLAG: Task {task.dl_task_number} completed "
            f"{distance_km:.1f}km from delivery address"
        )
        DeliveryTask.objects.filter(pk=task.pk).update(delivery_distance_flag=True)

    # Fix 16: GPS spoofing detection — impossible jump between status points
    if distance_km is not None:
        prev_point = delivery_models.TaskStatusPoint.objects.filter(
            task=task
        ).exclude(pk=status_point.pk).order_by('-created_at').first()
        if prev_point and prev_point.latitude and prev_point.longitude:
            time_diff = (status_point.created_at - prev_point.created_at).total_seconds()
            if time_diff > 0 and time_diff < 300:  # Within 5 minutes
                jump_km = delivery_models.TaskStatusPoint.haversine_km(
                    prev_point.latitude, prev_point.longitude,
                    status_point.latitude, status_point.longitude
                )
                if jump_km > 50:
                    logger.warning(
                        f"GPS SPOOF SUSPECT: Driver jumped {jump_km:.1f}km in "
                        f"{time_diff:.0f}s for task {task.dl_task_number}"
                    )

    # Fix 22: Time slot miss check
    if new_status == 'delivered' and task.order and getattr(task.order, 'preferred_time_slot', None):
        try:
            current_hour = timezone.localtime().hour
            slot = task.order.preferred_time_slot
            SLOT_HOURS = {
                'morning': (8, 12), 'afternoon': (12, 16),
                'evening': (16, 20), 'night': (20, 22),
            }
            slot_range = SLOT_HOURS.get(slot)
            if slot_range and not (slot_range[0] <= current_hour < slot_range[1]):
                logger.warning(
                    f"TIME SLOT MISSED: Task {task.dl_task_number} delivered at "
                    f"{current_hour}:00, slot was {slot}"
                )
                DeliveryTask.objects.filter(pk=task.pk).update(time_slot_missed=True)
        except Exception as e:
            logger.error(f"Error checking time slot for task {task.pk}: {e}")


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

        # Fire COD collected trigger when delivered (incl. partial) with COD
        if old_status is not None and new_status in ('delivered', 'partial_delivery') and instance.cod_collected and instance.cod_collected_amount:
            try:
                from core.auto_flow_executor import execute_flows_for_trigger
                execute_flows_for_trigger('staff_cod_collected', task=instance)
                execute_flows_for_trigger('wh_cod_collected', task=instance)
            except Exception as e:
                logger.warning(f"Auto flow failed for COD collected {instance.pk}: {e}")

            # Fix 12: Lock COD amount after collection
            if instance.order_id and not instance.order.cod_amount_locked:
                try:
                    orders_models.Order.objects.filter(pk=instance.order.pk).update(cod_amount_locked=True)
                    logger.info(f"COD amount locked for order {instance.order.order_number}")
                except Exception as e:
                    logger.error(f"Error locking COD for order {instance.order.pk}: {e}")

        # Increment failed_attempt_count when task transitions to 'failed'
        if old_status is not None and old_status != 'failed' and new_status == 'failed':
            try:
                DeliveryTask.objects.filter(pk=instance.pk).update(
                    failed_attempt_count=instance.failed_attempt_count + 1
                )
                logger.info(f"Task {instance.dl_task_number} failed_attempt_count → {instance.failed_attempt_count + 1}")
            except Exception as e:
                logger.exception(f"Error incrementing failed_attempt_count for task {instance.pk}: {e}")

            # Enqueue a delivery-recovery WhatsApp (10-min grace window before send).
            # See whatsapp.tasks.drain_verification_queue — picks up jobs with
            # scheduled_for <= now and builds a recovery message including the
            # driver's failure reason. Uses get_or_create on (task,kind,queued)
            # so a duplicate save of the same failed status doesn't double-enqueue.
            try:
                _enqueue_delivery_recovery_job(instance)
            except Exception as e:
                logger.exception(f"Failed to enqueue recovery job for task {instance.pk}: {e}")

        # If driver/staff undoes the failed status BEFORE the 10-min timer fires
        # and the WhatsApp goes out, auto-cancel the pending recovery job so the
        # customer doesn't get a stale apology. Once status is 'sent' it's too
        # late — the message already left the platform.
        if old_status == 'failed' and new_status != 'failed':
            try:
                _cancel_pending_recovery_jobs(instance)
            except Exception as e:
                logger.exception(f"Failed to cancel pending recovery job for task {instance.pk}: {e}")

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

            # Fire auto flows for driver assignment
            try:
                from core.auto_flow_executor import execute_flows_for_trigger
                execute_flows_for_trigger('staff_task_assign_driver', task=instance)
            except Exception as e:
                logger.warning(f"Auto flow execution failed for driver assignment {instance.pk}: {e}")

        # --- Customer WhatsApp notifications ---
        if old_status is not None and old_status != new_status:
            _send_customer_notification(instance, old_status, new_status)

            # Fire auto flows for task status change
            try:
                from core.auto_flow_executor import execute_flows_for_trigger
                execute_flows_for_trigger('staff_task_status_change', task=instance)

                # Specific trigger for task cancel
                if new_status == 'cancelled':
                    execute_flows_for_trigger('staff_task_cancel', task=instance)

                # WhatsApp auto flow triggers (wa_*)
                wa_trigger_map = {
                    'assigned': 'wa_driver_assigned',
                    'out_for_delivery': 'wa_out_for_delivery',
                    'in_transit': 'wa_out_for_delivery',
                    'delivered': 'wa_delivered',
                    'failed': 'wa_delivery_failed',
                }
                wa_key = wa_trigger_map.get(new_status)
                if wa_key:
                    execute_flows_for_trigger(wa_key, task=instance)
            except Exception as e:
                logger.warning(f"Auto flow execution failed for status change {instance.pk}: {e}")

    # Send WhatsApp location verification when task is published
    if not created:
        old_publish = getattr(instance, '_old_dl_task_publish', None)
        if old_publish is False and instance.dl_task_publish is True:
            _send_location_verification_on_publish(instance)

            # Fire auto flows for task publish and location verification triggers
            try:
                from core.auto_flow_executor import execute_flows_for_trigger
                execute_flows_for_trigger('staff_task_publish', task=instance)
                execute_flows_for_trigger('wa_location_verification', task=instance)
            except Exception as e:
                logger.warning(f"Auto flow execution failed for task publish {instance.pk}: {e}")

    # Fire auto flow for task reschedule (date changed)
    if not created:
        old_date = getattr(instance, '_old_dl_task_date', None)
        if old_date is not None and old_date != instance.dl_task_date:
            try:
                from core.auto_flow_executor import execute_flows_for_trigger
                execute_flows_for_trigger('staff_task_reschedule', task=instance)
            except Exception as e:
                logger.warning(f"Auto flow failed for task reschedule {instance.pk}: {e}")

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


# =============================================================================
# Delivery-Recovery Job helpers
# (called from the post_save DeliveryTask handler when a task is marked failed)
# =============================================================================

def _enqueue_delivery_recovery_job(task):
    """Create an AddressVerificationJob (kind='delivery_failed', scheduled_for=
    now+10min) so the drain worker contacts the customer 10 min after the
    driver marked the task failed. Idempotent — skips if a queued recovery
    job already exists for this order.
    """
    from datetime import timedelta
    from django.utils import timezone
    from whatsapp.models import AddressVerificationJob
    from core.templatetags.custom_filters import whatsapp_number

    if not task.order_id:
        return

    order = task.order
    phone_norm = whatsapp_number(order.customer_whatsapp or order.customer_phone)
    if not phone_norm:
        logger.warning(
            f"Skipped recovery enqueue for task {task.dl_task_number}: no phone on order {order.order_number}"
        )
        return

    # Avoid duplicate enqueue if multiple saves fire the failed transition.
    existing = AddressVerificationJob.objects.filter(
        order=order, kind='delivery_failed', status='queued',
    ).order_by('-created_at').first()
    if existing:
        logger.info(
            f"Recovery job already queued for order {order.order_number} "
            f"(job #{existing.id}); not creating duplicate."
        )
        return

    # Compose driver_failure_note from the structured reason + free-form notes.
    reason_label = ''
    if task.failure_reason:
        reason_label = dict(task.FAILURE_REASON_CHOICES).get(task.failure_reason, task.failure_reason)
    note_parts = []
    if reason_label:
        note_parts.append(reason_label)
    if task.failure_notes:
        note_parts.append(task.failure_notes.strip())
    failure_note = ' — '.join(note_parts)[:1000]

    grace_min = getattr(__import__('django.conf', fromlist=['settings']).settings,
                        'WAHA_DELIVERY_RECOVERY_DELAY_MINUTES', 10)
    job = AddressVerificationJob.objects.create(
        order=order,
        phone=phone_norm,
        kind='delivery_failed',
        status='queued',
        scheduled_for=timezone.now() + timedelta(minutes=grace_min),
        driver_failure_note=failure_note,
    )
    logger.info(
        f"Enqueued delivery-recovery job #{job.id} for order {order.order_number} "
        f"(sends at {job.scheduled_for.isoformat()}, reason={reason_label!r})"
    )


def _cancel_pending_recovery_jobs(task):
    """Cancel any queued delivery-recovery jobs for this order. Called when a
    task moves out of 'failed' state before the 10-min timer fires. Once a job
    is in 'sent' state, the WhatsApp has already gone out so we leave it.
    """
    from whatsapp.models import AddressVerificationJob

    if not task.order_id:
        return

    qs = AddressVerificationJob.objects.filter(
        order_id=task.order_id, kind='delivery_failed', status='queued',
    )
    if qs.exists():
        from django.utils import timezone
        count = qs.count()
        qs.update(
            status='cancelled',
            completed_at=timezone.now(),
            notes='Auto-cancelled: task moved out of failed state before recovery send',
        )
        logger.info(
            f"Cancelled {count} queued recovery job(s) for task {task.dl_task_number} "
            f"(status reverted from 'failed')"
        )


# =============================================================================
# ZONE / AREA CACHE + AI PARSE-LOCATION SYNC
# =============================================================================
# When a zone or area is added/edited/removed, two derived stores go stale:
#   1. the cached active-area list used by orders.signals._resolve_zone_number
#   2. ZoneTrainingData — the AI parse-location (`parse_address`) tool's lookup
#      table, which is a materialised copy of ZoneName/ZoneArea names.
# These receivers keep both in sync incrementally so neither path serves stale data.

def _sync_training_row(zone, text, language):
    """Upsert one authoritative ZoneTrainingData row (area/zone name -> zone).
    Mirrors populate_zone_training_data. Best-effort: never blocks the zone save."""
    if not text:
        return
    from ai_agent.models import ZoneTrainingData
    ZoneTrainingData.objects.update_or_create(
        zone=zone,
        text_input=text.strip().lower(),
        defaults={
            'input_type': 'area_name',
            'language': language,
            'confidence': 1.0,
            'is_verified': True,  # authoritative, from the zone tables
        },
    )


@receiver(post_save, sender=ZoneName)
def zonename_saved(sender, instance, **kwargs):
    from delivery.zone_cache import invalidate_zone_cache
    invalidate_zone_cache()
    try:
        _sync_training_row(instance, instance.zone_name, 'en')
        _sync_training_row(instance, instance.zone_name_arabic, 'ar')
    except Exception as e:
        logger.warning(f"ZoneTrainingData sync failed for zone {instance.zone_number}: {e}")


@receiver(post_save, sender=ZoneArea)
def zonearea_saved(sender, instance, **kwargs):
    from delivery.zone_cache import invalidate_zone_cache
    invalidate_zone_cache()
    try:
        if instance.is_active:
            _sync_training_row(instance.zone, instance.area_name, 'en')
            _sync_training_row(instance.zone, instance.area_name_arabic, 'ar')
        else:
            # Deactivated area — drop its authoritative training rows
            _remove_training_rows(instance.zone, [instance.area_name, instance.area_name_arabic])
    except Exception as e:
        logger.warning(f"ZoneTrainingData sync failed for area '{instance.area_name}': {e}")


def _remove_training_rows(zone, texts):
    """Delete authoritative (is_verified) training rows for the given texts of a zone."""
    from ai_agent.models import ZoneTrainingData
    keys = [t.strip().lower() for t in texts if t]
    if keys:
        ZoneTrainingData.objects.filter(
            zone=zone, text_input__in=keys, is_verified=True
        ).delete()


@receiver(post_delete, sender=ZoneArea)
def zonearea_deleted(sender, instance, **kwargs):
    from delivery.zone_cache import invalidate_zone_cache
    invalidate_zone_cache()
    try:
        _remove_training_rows(instance.zone, [instance.area_name, instance.area_name_arabic])
    except Exception as e:
        logger.warning(f"ZoneTrainingData cleanup failed for area '{instance.area_name}': {e}")


@receiver(post_delete, sender=ZoneName)
def zonename_deleted(sender, instance, **kwargs):
    # ZoneTrainingData rows cascade-delete via their FK to ZoneName; just clear the cache.
    from delivery.zone_cache import invalidate_zone_cache
    invalidate_zone_cache()
