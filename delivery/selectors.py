# Purpose: Single source of truth for which pickup tasks a driver may see/claim.
# Used by: fleet/views.py (Pickup tab list + accept gating), fleet/workforce context processors.
# Notes: Assigned mode = active DriverDirectory link; public pool = all approved drivers.
#        A pickup also drops out of the pool once its order/delivery leg is finished.

from django.db.models import OuterRef, Q, Subquery

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
        .select_related('order', 'business', 'pickup_location', 'drop_warehouse__warehouse')
        .distinct()
    )
