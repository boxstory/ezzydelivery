# Purpose: Single source of truth for which pickup tasks a driver may see/claim.
# Used by: fleet/views.py (Pickup tab list + accept gating), fleet/workforce context processors.
# Notes: Assigned mode = active DriverDirectory link; public pool = all approved drivers.
#        A pickup also drops out of the pool once its order/delivery leg is finished.

from django.db.models import Exists, OuterRef, Q, Subquery

# The delivery leg is over for good — a first-mile pickup on it is dead work.
# 'failed'/'rejected' are NOT here: a failed task can be retried, so its pickup stays live.
TERMINAL_DL_STATUSES = ['cancelled', 'delivered', 'partial_delivery']
TERMINAL_ORDER_STATUSES = ['cancelled', 'delivered']


def pending_pickup_pool():
    """
    Pickups still genuinely awaiting a first-mile driver: unclaimed, pending, and
    on an order whose delivery leg has not already ended (cancelled/delivered).
    The order-side guard is what keeps a cancelled delivery from leaving a
    claimable pickup behind when the cancel path never touched the PickupTask row.
    """
    from delivery.models import DeliveryTask, PickupTask

    # Latest task only — an order can carry an old cancelled task plus a live retry,
    # and a reverse-FK exclude() would match the old one and hide a valid pickup.
    latest_dl_status = Subquery(
        DeliveryTask.objects.filter(order=OuterRef('order'))
        .order_by('-id').values('dl_task_status')[:1]
    )

    return (
        PickupTask.objects.filter(status='pending', driver__isnull=True)
        .exclude(order__order_status__in=TERMINAL_ORDER_STATUSES)
        .annotate(_latest_dl_status=latest_dl_status)
        # Written as filter(isnull | ~in) on purpose: exclude(__in=) drops rows where
        # the annotation is NULL (no task yet), because NOT (NULL IN (...)) is NULL.
        .filter(
            Q(_latest_dl_status__isnull=True)
            | ~Q(_latest_dl_status__in=TERMINAL_DL_STATUSES)
        )
    )


def pickup_pool_for(driver):
    """
    Claimable pickup tasks for this driver (status pending, no driver yet):
    - assigned-mode tasks of businesses whose active DriverDirectory includes them
    - all public-pool tasks (driver must be approved)
    Every surface that lists or claims pickups must go through this filter.
    """
    from delivery.models import PickupTask

    if not driver or driver.driver_status != 'approved':
        return PickupTask.objects.none()

    return (
        pending_pickup_pool()
        .filter(
            Q(pickup_mode='public_pool')
            | Q(
                pickup_mode='assigned',
                business__driver_directory__driver=driver,
                business__driver_directory__is_active=True,
            )
        )
        .select_related('order', 'order__p2p_booking', 'business', 'pickup_location',
                        'drop_warehouse__warehouse')
        .distinct()
    )


# =============================================================================
# HELD PARCELS — the other direction: which DELIVERY tasks a driver may claim
# =============================================================================


def exclude_held_parcels(qs, driver=None):
    """
    Drop delivery tasks whose parcel is physically in another driver's hands.

    A pickup at 'collected' means a driver is carrying the goods. The task is
    published and unassigned in the same moment, so without this filter any
    approved driver could claim a delivery for a parcel they cannot pick up.
    Only the holder and the driver a transfer is addressed to still see it;
    'dropped' legs are untouched, so hub tasks stay open to everyone.
    """
    from delivery.models import PickupTask

    held = PickupTask.objects.filter(order=OuterRef('order'), status='collected')
    if driver is not None:
        held = held.exclude(Q(driver=driver) | Q(transfer_to_driver=driver))
    return qs.exclude(Exists(held))


def parcel_claim_block(task, driver):
    """
    Server-side twin of exclude_held_parcels for the claim endpoints.
    Returns (blocked, message) — message is empty when the claim is allowed.

    Staff assignment deliberately does NOT go through this: it is the override
    for a holder who has gone offline, and the claim still closes the leg and
    tells both drivers the parcel has to change hands.
    """
    from delivery.models import PickupTask

    if not task or not getattr(task, 'order_id', None) or not driver:
        return False, ''

    holder = (
        PickupTask.objects.filter(order_id=task.order_id, status='collected')
        .exclude(Q(driver=driver) | Q(transfer_to_driver=driver))
        .select_related('driver').first()
    )
    if not holder:
        return False, ''
    return True, (
        f"This parcel is with {holder.driver or 'another driver'} — "
        f"ask them to transfer it to you in the Pickup tab."
    )


# =============================================================================
# DELIVERY ADDRESS — which of the two FKs actually holds the row
# =============================================================================

# DeliveryTask carries two ForeignKeys to the same DlAddressUpdate model:
# `dl_address_update` (written by orders.signals / delivery.signals on task
# creation) and `dl_to_address` (which no code path ever wrote — it was NULL on
# all 1781 rows before the 2026-09-12 backfill). Reads are split across both:
# ~168 references use dl_to_address, ~24 use dl_address_update. delivery.signals
# .delivery_task_pre_save now mirrors whichever one is set onto the other so new
# rows can't drift, but resolve through here rather than reading either field
# directly — a row written by bulk_create or queryset.update() bypasses pre_save.
def task_address(task):
    """Return the DlAddressUpdate row for ``task``, or None.

    Order of preference: dl_address_update (historically the populated one),
    then dl_to_address, then a direct dl_task_number match for rows that predate
    either FK being wired up.
    """
    if task is None:
        return None

    addr = task.dl_address_update_id and task.dl_address_update
    if addr:
        return addr
    addr = task.dl_to_address_id and task.dl_to_address
    if addr:
        return addr

    from delivery.models import DlAddressUpdate
    if not task.dl_task_number:
        return None
    return DlAddressUpdate.objects.filter(dl_task_number=task.dl_task_number).first()
