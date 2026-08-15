# Purpose: First-mile pickup lifecycle — auto-create pickup tasks on order creation,
# Used by: orders/signals.py (create/cancel hooks), fleet/views.py (accept/collect/route)
# Notes: Pickup leg has no COD and no earnings; delivery leg is created per disposition.

import logging

from django.db import transaction
from django.utils import timezone

logger = logging.getLogger('delivery')


def log_pickup_history(pickup, old_status, new_status, actor=None, notes=''):
    """
    Write a pickup transition into the order's OrderStatusHistory so the
    staff order/task detail timelines show the first-mile leg. Never raises —
    the timeline is a byproduct, not part of the transition.
    """
    from delivery.models import PickupTask
    from orders.models import OrderStatusHistory

    labels = dict(PickupTask.PICKUP_STATUS_CHOICES)
    try:
        OrderStatusHistory.objects.create(
            order=pickup.order,
            field_name='pickup_status',
            old_value=old_status or '',
            new_value=new_status,
            old_display=labels.get(old_status) if old_status else None,
            new_display=labels.get(new_status, new_status),
            changed_by=actor if getattr(actor, 'is_authenticated', False) else None,
            notes=notes[:255] if notes else None,
        )
    except Exception as e:
        logger.warning(f"Pickup history log failed for order {pickup.order_id}: {e}")


def resolve_default_hub():
    """The single fixed drop hub: default Warehouse -> its default (or first) location."""
    from warehouse.models import Warehouse, WarehouseLocation
    warehouse = Warehouse.objects.filter(is_default=True).first()
    if not warehouse:
        return None
    return (
        WarehouseLocation.objects.filter(warehouse=warehouse)
        .order_by('-is_default', 'name').first()
    )


def create_pickup_task_if_needed(order, source=''):
    """
    Create a PickupTask for a freshly created order, if the business config asks
    for one. Returns (pickup_task_or_None, reason). Never raises to the caller —
    order creation must not fail because pickup gating failed.
    """
    from delivery.models import PickupTask

    try:
        business = order.business
        if not business:
            return None, 'no_business'
        if not business.pickup_task_enabled:
            return None, 'pickup_disabled'
        if business.business_status != 'active':
            return None, 'business_not_active'
        if getattr(order, 'is_hub_delivery', False):
            return None, 'hub_delivery_order'  # staff HubPickupBatch flow handles collection

        pickup_location = order.pickup_location
        if not pickup_location:
            return None, 'no_pickup_location'
        if pickup_location.is_fulfilment_center:
            return None, 'fulfilment_center'  # goods already at the warehouse
        if pickup_location.pickup_status != 'active':
            return None, 'pickup_location_inactive'

        if PickupTask.objects.filter(order=order).exists():
            return None, 'already_exists'

        pickup = PickupTask.objects.create(
            order=order,
            business=business,
            pickup_location=pickup_location,
            drop_warehouse=resolve_default_hub(),
            pickup_mode=business.pickup_mode_default,
            disposition=business.pickup_disposition_default,
            status='pending',
        )
        logger.info(
            f"PickupTask created for order {order.order_number} "
            f"(mode={pickup.pickup_mode}, disposition={pickup.disposition}, source={source})"
        )
        log_pickup_history(
            pickup, None, 'pending',
            notes=f"First-mile pickup created ({pickup.get_pickup_mode_display()}, "
                  f"plan: {pickup.get_disposition_display()})")
        _notify_assigned_fleet(pickup)
        return pickup, 'created'
    except Exception as e:
        logger.error(f"PickupTask creation failed for order {order.pk}: {e}", exc_info=True)
        return None, 'error'


def cancel_pickup_for_order(order, reason='Order was cancelled'):
    """
    The order (or its delivery leg) ended — cancel the first-mile pickup unless it
    was already executed. `reason` is the human line written to the order timeline
    and the driver notification, so a task-driven cancel doesn't claim the client
    cancelled the order. Idempotent: an already-cancelled pickup is left alone.
    """
    from delivery.models import PickupTask
    from fleet.models import DriverNotification

    try:
        pickup = PickupTask.objects.filter(order=order).exclude(
            status__in=['dropped', 'handed_off', 'cancelled']).first()
        if not pickup:
            return
        old_status = pickup.status
        pickup.status = 'cancelled'
        pickup.save(update_fields=['status', 'updated_at'])
        log_pickup_history(pickup, old_status, 'cancelled', notes=reason)
        if pickup.driver:
            DriverNotification.objects.create(
                driver=pickup.driver,
                title='Pickup cancelled',
                message=f"Pickup for order {order.order_number} was cancelled — {reason.lower()}.",
                notification_type='alert',
            )
        logger.info(f"PickupTask cancelled for order {order.order_number} ({reason})")
    except Exception as e:
        logger.error(f"PickupTask cancel failed for order {order.pk}: {e}", exc_info=True)


def _notify_assigned_fleet(pickup):
    """Assigned-mode pickups notify the client's active fleet drivers (in-app)."""
    from business.models import DriverDirectory
    from fleet.models import DriverNotification

    if pickup.pickup_mode != 'assigned':
        return  # public pool relies on the Pickup tab badge/list
    driver_ids = DriverDirectory.objects.filter(
        business=pickup.business, is_active=True,
        driver__driver_status='approved',
    ).values_list('driver_id', flat=True)
    DriverNotification.objects.bulk_create([
        DriverNotification(
            driver_id=driver_id,
            title='New pickup available',
            message=(
                f"Collect order {pickup.order.order_number} from "
                f"{pickup.pickup_location.pickup_location_title if pickup.pickup_location else pickup.business.business_name}."
            ),
            notification_type='pickup_available',
        )
        for driver_id in driver_ids
    ])


def _ensure_delivery_task(pickup):
    """
    Get or create the last-mile DeliveryTask for the pickup's order.
    Reuses the existing creation pipeline (address update, geocode, mappings).
    """
    from orders.signals import _create_delivery_task_from_order

    order = pickup.order
    existing = order.delivery_task.exclude(dl_task_status='cancelled').order_by('-id').first()
    if existing:
        return existing
    task = _create_delivery_task_from_order(order)
    return task


def execute_disposition(pickup, actor_user=None):
    """
    Run the preset disposition after collection.
    - drop: mark dropped at hub; delivery task created unpublished for staff to run.
    - self_deliver: delivery task assigned to the same driver, published, accepted.
    - transfer: no-op here — handled by initiate_transfer/confirm_transfer.
    Returns (ok, message).
    """
    if pickup.status != 'collected':
        return False, 'Package must be collected first'

    if pickup.disposition == 'drop':
        task = _ensure_delivery_task(pickup)
        if task:
            task.source_pickup_task = pickup
            task.save(update_fields=['source_pickup_task'])
        pickup.status = 'dropped'
        pickup.dropped_at = timezone.now()
        pickup.save(update_fields=['status', 'dropped_at', 'updated_at'])
        hub = pickup.drop_warehouse.name if pickup.drop_warehouse else 'hub'
        log_pickup_history(
            pickup, 'collected', 'dropped', actor=actor_user,
            notes=f"Package dropped at {hub} by {pickup.driver or 'driver'}")
        return True, 'Dropped at hub — delivery will be dispatched from there'

    if pickup.disposition == 'self_deliver':
        return _hand_delivery_to(pickup, pickup.driver, final_status='handed_off')

    return False, 'Transfer requires selecting a driver'


def initiate_transfer(pickup, target_driver):
    """Pickup driver proposes a hand-off; final only when the target confirms."""
    from fleet.models import DriverNotification

    if pickup.status != 'collected':
        return False, 'Package must be collected first'
    if target_driver.driver_status != 'approved':
        return False, 'Target driver is not approved'
    if pickup.driver and target_driver.pk == pickup.driver.pk:
        return False, 'Cannot transfer to yourself'

    pickup.transfer_to_driver = target_driver
    pickup.transfer_initiated_at = timezone.now()
    pickup.transfer_confirmed_at = None
    pickup.save(update_fields=[
        'transfer_to_driver', 'transfer_initiated_at', 'transfer_confirmed_at', 'updated_at'])
    log_pickup_history(
        pickup, None, 'collected',
        notes=f"Transfer requested: {pickup.driver or 'driver'} → {target_driver} (awaiting confirm)")
    DriverNotification.objects.create(
        driver=target_driver,
        title='Pickup transfer request',
        message=(
            f"{pickup.driver if pickup.driver else 'A driver'} wants to hand you "
            f"order {pickup.order.order_number} for delivery. Confirm in your Pickup tab."
        ),
        notification_type='pickup_transfer',
    )
    return True, 'Transfer requested — waiting for the other driver to confirm'


def confirm_transfer(pickup, confirming_driver):
    """Target driver confirms the hand-off; delivery task is created assigned to them."""
    if not pickup.transfer_to_driver_id:
        return False, 'No transfer pending on this pickup'
    if pickup.transfer_to_driver_id != confirming_driver.pk:
        return False, 'This transfer is not addressed to you'
    if pickup.status != 'collected':
        return False, 'Pickup is not in a transferable state'

    pickup.transfer_confirmed_at = timezone.now()
    pickup.save(update_fields=['transfer_confirmed_at', 'updated_at'])
    return _hand_delivery_to(pickup, confirming_driver, final_status='handed_off')


def _hand_delivery_to(pickup, driver, final_status):
    """Create/claim the delivery leg for `driver` and close out the pickup."""
    from delivery.models import AssignedDriver

    if not driver:
        return False, 'No driver on this pickup'

    with transaction.atomic():
        task = _ensure_delivery_task(pickup)
        if not task:
            return False, 'Could not create the delivery task'
        if task.driver_id and task.driver_id != driver.pk:
            return False, 'Delivery is already assigned to another driver'

        task.driver = driver
        task.source_pickup_task = pickup
        task.dl_task_publish = True
        task.dl_task_status = 'accepted'
        task._status_actor = 'driver'  # for_review/pending -> accepted is a driver transition
        task.save(update_fields=[
            'driver', 'source_pickup_task', 'dl_task_publish', 'dl_task_status'])
        AssignedDriver.objects.get_or_create(driver=driver, dl_task=task)

        pickup.status = final_status
        pickup.save(update_fields=['status', 'updated_at'])

    log_pickup_history(
        pickup, 'collected', final_status,
        notes=f"Delivery leg {task.dl_task_number or ''} handed to {driver}".strip())
    return True, 'Delivery task is now in the driver task list'
