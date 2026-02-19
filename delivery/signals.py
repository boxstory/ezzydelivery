from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.contrib.auth.models import User
from django.utils import timezone
from orders import models as orders_models
from delivery import models as delivery_models
import uuid
import logging

# Local alias for commonly used model
DeliveryTask = delivery_models.DeliveryTask

logger = logging.getLogger(__name__)

# Terminal order statuses — don't overwrite these
TERMINAL_ORDER_STATUSES = ['delivered', 'cancelled']


@receiver(pre_save, sender=DeliveryTask)
def delivery_task_pre_save(sender, instance, **kwargs):
    """Track old delivery task status for change detection in post_save.
    Also block status changes when order is cancelled."""
    if instance.pk:
        try:
            old = DeliveryTask.objects.get(pk=instance.pk)
            instance._old_dl_task_status = old.dl_task_status
            instance._old_dl_task_status_dms = old.dl_task_status_dms

            # Lock delivery statuses based on order state
            if instance.order_id:
                order = instance.order
                # Block when order is cancelled (allow setting to cancelled only)
                if order.order_status == 'cancelled':
                    if instance.dl_task_status != 'cancelled' and instance.dl_task_status != old.dl_task_status:
                        logger.warning(
                            f"Blocked delivery status change '{old.dl_task_status}' -> '{instance.dl_task_status}' "
                            f"for task {instance.dl_task_number}: order is cancelled"
                        )
                        instance.dl_task_status = old.dl_task_status
                    if instance.dl_task_status_dms != '9' and instance.dl_task_status_dms != old.dl_task_status_dms:
                        logger.warning(
                            f"Blocked DMS status change '{old.dl_task_status_dms}' -> '{instance.dl_task_status_dms}' "
                            f"for task {instance.dl_task_number}: order is cancelled"
                        )
                        instance.dl_task_status_dms = old.dl_task_status_dms

                # Block when order is NOT verified (allow cancellation only)
                elif order.verification_status != 'verified':
                    if instance.dl_task_status != old.dl_task_status and instance.dl_task_status != 'cancelled':
                        logger.warning(
                            f"Blocked delivery status change '{old.dl_task_status}' -> '{instance.dl_task_status}' "
                            f"for task {instance.dl_task_number}: order not verified (status={order.verification_status})"
                        )
                        instance.dl_task_status = old.dl_task_status
                    if instance.dl_task_status_dms != old.dl_task_status_dms and instance.dl_task_status_dms != '9':
                        logger.warning(
                            f"Blocked DMS status change '{old.dl_task_status_dms}' -> '{instance.dl_task_status_dms}' "
                            f"for task {instance.dl_task_number}: order not verified"
                        )
                        instance.dl_task_status_dms = old.dl_task_status_dms
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


# Active DL task statuses that mean the driver is busy
ACTIVE_TASK_STATUSES = [
    'assigned', 'accepted', 'picked_up', 'start_ride',
    'in_transit', 'out_for_delivery', 'contacted',
    'non_reachable', 'address_pending',
    'customer_confiration_pending', 'customer_delaying',
    'dl_pending_payment',
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


@receiver(post_save, sender=DeliveryTask)
def delivery_task_post_save_receiver(sender, instance, created, *args, **kwargs):
    """Handle delivery task creation/update and push to DMS with error handling"""

    if created:
        # Push to DMS when task is created
        try:
            from ezzy_api.views import _push_task_to_dms
            result = _push_task_to_dms(instance)
            if result:
                logger.info(f"Task {instance.dl_task_number} successfully pushed to DMS on creation")
            else:
                logger.warning(f"Failed to push task {instance.dl_task_number} to DMS on creation")
        except Exception as e:
            logger.exception(f"Error pushing task {instance.dl_task_number} to DMS in signal: {str(e)}")

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

    # Update DMS when task status changes
    elif not created and 'dl_task_status_dms' in (kwargs.get('update_fields') or []):
        try:
            from ezzy_api.views import _push_task_to_dms
            result = _push_task_to_dms(instance)
            if result:
                logger.info(f"Task {instance.dl_task_number} status update pushed to DMS")
            else:
                logger.warning(f"Failed to push task {instance.dl_task_number} status update to DMS")
        except Exception as e:
            logger.exception(f"Error pushing task update to DMS in signal: {str(e)}")

    # Log delivery task status changes to order status history
    if not created and instance.order_id:
        try:
            from orders.signals import log_delivery_task_status_change
            DL_STATUS_DISPLAY = dict(DeliveryTask.dl_task_status.field.choices)
            DMS_STATUS_DISPLAY = dict(DeliveryTask.dl_task_status_dms.field.choices)

            old_dl = getattr(instance, '_old_dl_task_status', None)
            new_dl = instance.dl_task_status
            if old_dl is not None and old_dl != new_dl:
                log_delivery_task_status_change(instance, 'dl_task_status', old_dl, new_dl, DL_STATUS_DISPLAY)

            old_dms = getattr(instance, '_old_dl_task_status_dms', None)
            new_dms = instance.dl_task_status_dms
            if old_dms is not None and old_dms != new_dms:
                log_delivery_task_status_change(instance, 'dl_task_status_dms', old_dms, new_dms, DMS_STATUS_DISPLAY)
        except Exception as e:
            logger.error(f"Error logging delivery task status history: {e}")

    # Sync delivery task status → order status (for all non-creation saves)
    if not created:
        old_status = getattr(instance, '_old_dl_task_status', None)
        new_status = instance.dl_task_status
        if old_status is not None and old_status != new_status and instance.order_id:
            _sync_order_status_from_task(instance)

    # Sync delivery task status → driver availability
    if instance.driver_id:
        old_dl = getattr(instance, '_old_dl_task_status', None)
        new_dl = instance.dl_task_status
        if created or (old_dl is not None and old_dl != new_dl):
            _sync_driver_availability(instance)
