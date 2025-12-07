
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.contrib.auth.models import User
from orders.models import *
from delivery.models import DeliveryTask
import uuid
import logging

logger = logging.getLogger(__name__)


@receiver(post_save, sender=DeliveryTask)
def delivery_task_post_save_receiver(sender, instance, created, *args, **kwargs):
    """Handle delivery task creation/update and push to DMS with error handling"""

    if created and not instance.dl_task_publish:
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
