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


# Pickups already closed out — nothing left to cancel or clean up.
CLOSED_PICKUP_STATUSES = ['dropped', 'handed_off', 'cancelled']

# Once the driver holds the goods the address is history, so a move is refused
# from 'collected' onwards too.
UNMOVEABLE_PICKUP_STATUSES = CLOSED_PICKUP_STATUSES + ['collected']


def relocate_pickup(pickup, location, actor=None):
    """Move an open pickup to another of the client's addresses.

    Returns (ok, message). The order carries the same FK and is what every
    downstream label/waybill reads, so both are written together — a pickup
    pointing at one address while the order says another is the bug this
    prevents. Never raises: staff get the refusal in words.
    """
    from orders.models import OrderStatusHistory
    from fleet.models import DriverNotification

    try:
        if location.business_id != pickup.business_id:
            return False, 'That pickup location belongs to a different client'
        if pickup.status in UNMOVEABLE_PICKUP_STATUSES:
            return False, (f'This pickup is already {pickup.get_status_display().lower()} — '
                           f'the address can no longer be changed')
        if location.pickup_status != 'active':
            return False, f"'{location.pickup_location_title}' is not an active pickup location"
        if location.is_fulfilment_center:
            return False, (f"'{location.pickup_location_title}' is a fulfilment centre — the goods "
                           f"are already at our warehouse, so there is nothing to collect there")
        if pickup.pickup_location_id == location.id:
            return False, 'That is already the pickup location'

        old = pickup.pickup_location
        old_title = old.pickup_location_title if old else '—'
        pickup.pickup_location = location
        pickup.save(update_fields=['pickup_location', 'updated_at'])

        order = pickup.order
        if order.pickup_location_id != location.id:
            order.pickup_location = location
            order.save(update_fields=['pickup_location'])

        try:
            OrderStatusHistory.objects.create(
                order=order,
                field_name='pickup_location',
                old_value=str(old.id) if old else '',
                new_value=str(location.id),
                old_display=old_title,
                new_display=location.pickup_location_title,
                changed_by=actor if getattr(actor, 'is_authenticated', False) else None,
                notes=f'Pickup address moved to {location.pickup_location_title}'[:255],
            )
        except Exception as e:
            logger.warning(f"Pickup relocate history failed for order {order.pk}: {e}")

        # The driver was sent to the old address — they have to be told.
        if pickup.driver:
            DriverNotification.objects.create(
                driver=pickup.driver,
                title='Pickup address changed',
                message=(f"Order {order.order_number} is now collected from "
                         f"{location.pickup_location_title}, not {old_title}."),
                notification_type='alert',
            )

        logger.info(
            f"PickupTask {pickup.pk} relocated for order {order.order_number}: "
            f"{old_title} -> {location.pickup_location_title}")
        return True, f'Pickup moved to {location.pickup_location_title}'
    except Exception as e:
        logger.error(f"PickupTask relocate failed for pickup {pickup.pk}: {e}", exc_info=True)
        return False, 'Could not move the pickup — check the delivery log'



def cancel_pickup_for_order(order, reason='Order was cancelled', delivery_task=None):
    """
    The order (or its delivery leg) ended — cancel the first-mile pickup unless it
    was already executed. `reason` is the human line written to the order timeline
    and the driver notification, so a task-driven cancel doesn't claim the client
    cancelled the order. Idempotent: an already-cancelled pickup is left alone.

    A 'collected' pickup is never cancelled: the driver physically holds the goods,
    so that work happened. Pass `delivery_task` (the leg that just ended) so a
    finished delivery closes it as handed off instead. See _close_collected_pickup.
    """
    from delivery.models import PickupTask
    from fleet.models import DriverNotification

    try:
        pickup = PickupTask.objects.filter(order=order).exclude(
            status__in=CLOSED_PICKUP_STATUSES).select_related(
                'order', 'driver', 'transfer_to_driver').first()
        if not pickup:
            return
        if pickup.status == 'collected':
            _close_collected_pickup(pickup, reason, delivery_task)
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


def _close_collected_pickup(pickup, reason, delivery_task=None):
    """
    The first-mile work is already done — the driver collected the goods — so this
    pickup must not end up labelled 'Cancelled'.

    - Delivery finished (delivered / partial): close as handed off. When the driver
      who delivered is the one a pending transfer was addressed to, the hand-off
      demonstrably happened, so confirm it rather than leaving it dangling.
    - Anything else (order or delivery cancelled): leave the pickup at 'collected'.
      The package still physically exists and has to be routed or returned — the
      driver keeps it on their In progress tab and gets told what happened.
    """
    from fleet.models import DriverNotification

    order = pickup.order
    delivered = bool(delivery_task and delivery_task.dl_task_status in ('delivered', 'partial_delivery'))

    if not delivered:
        log_pickup_history(
            pickup, 'collected', 'collected',
            notes=f"{reason} — package still held by {pickup.driver or 'the pickup driver'}, "
                  f"pickup left open for return/routing"[:255])
        if pickup.driver:
            DriverNotification.objects.create(
                driver=pickup.driver,
                title='Pickup needs routing',
                message=(
                    f"Order {order.order_number} ended ({reason.lower()}) but you still have "
                    f"the package. Return it to the client or drop it at the hub."
                ),
                notification_type='alert',
            )
        logger.info(
            f"PickupTask {pickup.pk} left collected for order {order.order_number} ({reason})")
        return

    update_fields = ['status', 'updated_at']
    auto_confirmed = False
    delivery_driver_id = getattr(delivery_task, 'driver_id', None)
    if (pickup.transfer_to_driver_id and not pickup.transfer_confirmed_at
            and delivery_driver_id == pickup.transfer_to_driver_id):
        pickup.transfer_confirmed_at = timezone.now()
        update_fields.append('transfer_confirmed_at')
        auto_confirmed = True

    pickup.status = 'handed_off'
    pickup.save(update_fields=update_fields)

    notes = f"Closed as handed off — {reason.lower()}"
    if auto_confirmed:
        notes += f"; transfer to {pickup.transfer_to_driver} auto-confirmed (they delivered it)"
    log_pickup_history(pickup, 'collected', 'handed_off', notes=notes[:255])
    logger.info(
        f"PickupTask {pickup.pk} closed as handed_off for order {order.order_number} "
        f"({reason}, auto_confirmed={auto_confirmed})")


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
    # The disposition builds the delivery leg without the order ever passing through
    # 'publish', so the board would keep showing the order as unpublished while a
    # driver is already holding the parcel. update_fields (not a full save) because
    # task_created is already True and the publish branch must not re-enter task
    # creation — this write is only bringing the label into line with reality.
    if task and order.order_status != 'publish':
        order.order_status = 'publish'
        order.save(update_fields=['order_status'])
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
        # This function closes the pickup itself a few lines down, so the post_save
        # reconciler must not also close it and write a second history row.
        task._pickup_disposition_run = True
        task.save(update_fields=[
            'driver', 'source_pickup_task', 'dl_task_publish', 'dl_task_status'])
        AssignedDriver.objects.get_or_create(driver=driver, dl_task=task)

        pickup.status = final_status
        pickup.save(update_fields=['status', 'updated_at'])

    log_pickup_history(
        pickup, 'collected', final_status,
        notes=f"Delivery leg {task.dl_task_number or ''} handed to {driver}".strip())
    return True, 'Delivery task is now in the driver task list'


def reconcile_pickup_on_delivery_claim(task, actor=None):
    """
    A driver now owns the delivery leg — close the first-mile leg that is still
    sitting at 'collected'.

    Drivers do not tap 'Deliver myself' or 'Confirm hand-off' on the Pickup tab;
    they take the task straight from the New pool, so the pickup used to stay at
    'collected' for the whole delivery with `source_pickup_task` never linked and
    the transfer never confirmed. The claim IS the hand-off, so it is read as one:

    - the transfer target claimed it  -> the proposed hand-off happened, confirm it
    - the collecting driver claimed it -> they kept the parcel (self-deliver)
    - anyone else claimed it (staff assign only, the pool hides held parcels)
      -> close it, but warn both drivers that the parcel has to change hands

    Never raises: the leg is a record of what happened, not part of the claim.
    """
    from delivery.models import DeliveryTask, PickupTask
    from fleet.models import DriverNotification

    try:
        driver = task.driver
        if not driver or not task.order_id:
            return None

        pickup = PickupTask.objects.filter(
            order_id=task.order_id, status='collected'
        ).select_related('order', 'driver', 'transfer_to_driver').first()
        if not pickup:
            return None

        order_number = pickup.order.order_number
        holder = pickup.driver

        # Queryset write, not task.save(): this runs inside the task's own
        # post_save and must not re-enter it.
        if task.source_pickup_task_id != pickup.pk:
            DeliveryTask.objects.filter(pk=task.pk).update(source_pickup_task=pickup)
            task.source_pickup_task = pickup

        extra_fields = []
        if pickup.transfer_to_driver_id == driver.pk:
            if not pickup.transfer_confirmed_at:
                pickup.transfer_confirmed_at = timezone.now()
                extra_fields.append('transfer_confirmed_at')
            notes = (f"Delivery leg {task.dl_task_number or ''} taken by {driver} — "
                     f"transfer from {holder or 'the pickup driver'} confirmed").strip()
        elif holder and holder.pk == driver.pk:
            notes = (f"Delivery leg {task.dl_task_number or ''} taken by {driver} — "
                     f"collecting driver kept the parcel").strip()
        else:
            notes = (f"Delivery leg {task.dl_task_number or ''} taken by {driver} — "
                     f"parcel is with {holder or 'the pickup driver'}, hand-off needed").strip()
            if holder and holder.pk != driver.pk:
                DriverNotification.objects.create(
                    driver=holder,
                    title='Hand over the parcel',
                    message=(f"{driver} is delivering order {order_number}. "
                             f"Hand them the package you collected."),
                    notification_type='alert',
                )
                DriverNotification.objects.create(
                    driver=driver,
                    title='Collect the parcel first',
                    message=(f"Order {order_number} was collected by {holder}. "
                             f"Take the package from them before you deliver."),
                    notification_type='alert',
                )

        close_collected_leg(pickup, notes, actor=actor, extra_fields=extra_fields)
        return pickup
    except Exception as e:
        logger.error(
            f"Pickup reconcile failed for delivery task {getattr(task, 'pk', None)}: {e}",
            exc_info=True)
        return None


def close_collected_leg(pickup, notes, actor=None, extra_fields=None):
    """
    The one place a 'collected' leg becomes 'handed_off'.

    The parcel physically changed hands (or staff confirmed it did), so the leg
    is closed as executed, never cancelled. `extra_fields` carries any column the
    caller already set on the instance, e.g. transfer_confirmed_at.
    """
    update_fields = ['status', 'updated_at'] + list(extra_fields or [])
    pickup.status = 'handed_off'
    pickup.save(update_fields=update_fields)
    log_pickup_history(pickup, 'collected', 'handed_off', actor=actor, notes=(notes or '')[:255])
    logger.info(
        f"PickupTask {pickup.pk} closed as handed_off "
        f"(order {pickup.order.order_number}): {notes}")
    return pickup
