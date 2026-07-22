# Purpose: Single source of truth for which pickup tasks a driver may see/claim.
# Used by: fleet/views.py (Pickup tab list + accept gating), pickup notifications.
# Notes: Assigned mode = active DriverDirectory link; public pool = all approved drivers.

from django.db.models import Q


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
        PickupTask.objects.filter(status='pending', driver__isnull=True)
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
