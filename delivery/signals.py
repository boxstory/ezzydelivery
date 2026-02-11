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
TERMINAL_ORDER_STATUSES = ['delivered', 'fulfilled', 'cancelled']


@receiver(pre_save, sender=DeliveryTask)
def delivery_task_pre_save(sender, instance, **kwargs):
    """Track old delivery task status for change detection in post_save"""
    if instance.pk:
        try:
            old = DeliveryTask.objects.get(pk=instance.pk)
            instance._old_dl_task_status = old.dl_task_status
            instance._old_dl_task_status_dms = old.dl_task_status_dms
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
            # Check if business uses fulfillment service
            if order.business and order.business.fulfillment_service_enabled:
                order.order_status = 'fulfilled'
                order.fulfilled_at = timezone.now()
                update_fields.extend(['order_status', 'fulfilled_at'])
            else:
                order.order_status = 'delivered'
                update_fields.append('order_status')
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

    # Sync delivery task status → order status (for all non-creation saves)
    if not created:
        old_status = getattr(instance, '_old_dl_task_status', None)
        new_status = instance.dl_task_status
        if old_status is not None and old_status != new_status and instance.order_id:
            _sync_order_status_from_task(instance)
