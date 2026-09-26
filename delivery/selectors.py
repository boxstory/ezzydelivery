# Purpose: Single source of truth for which pickup tasks a driver may see/claim.
# Used by: fleet/views.py (Pickup tab list + accept gating), fleet/workforce context processors.
# Notes: Assigned mode = active DriverDirectory link; public pool = all approved drivers.
#        A pickup also drops out of the pool once its order/delivery leg is finished.

from collections import namedtuple

from django.db.models import Exists, OuterRef, Q, Subquery

# The delivery leg is over for good — a first-mile pickup on it is dead work.
# 'failed'/'rejected' are NOT here: a failed task can be retried, so its pickup stays live.
TERMINAL_DL_STATUSES = ['cancelled', 'delivered', 'partial_delivery',
                        'returned_to_shipper']
# 'returned' is terminal too: the parcel came back, so a first-mile pickup
# still sitting against that order is dead work.
TERMINAL_ORDER_STATUSES = ['cancelled', 'delivered', 'returned']


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
    - all public-pool tasks (driver must be approved AND cleared to work)
    Every surface that lists or claims pickups must go through this filter.

    Approval alone is not enough: ops grant dashboard access separately, and a driver
    who is verified but not yet cleared has no claim on any pickup. Gating it here
    empties the pool on every surface at once — list, map, badge count and claim.
    """
    from delivery.models import PickupTask
    from fleet.access import has_dashboard_access

    if not has_dashboard_access(driver):
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


# =============================================================================
# Card route — where a leg collects from, and where it drops off
# =============================================================================
# The driver PWA card was written when every task was a merchant -> customer
# run, so it reads the pickup point off `order.pickup_location` and prefers the
# ORDER's zone/street/building/pin over the task's own address row (the order
# fields are the staff-corrected ones, so that preference is right — for a
# delivery to the customer). Two legs break both assumptions, and resolving them
# here keeps the card, the map pins and the detail sheet reading one answer.

# Legs whose drop-off is NOT the customer. The order's zone/street/building/pin
# still describe the customer, so letting them win here mixes two addresses into
# one that does not exist, and navigation lands on the person who refused the
# parcel. The task's own address row is the only truth for these.
# The leg that collects goods the customer is sending back. It is the only one
# whose ORIGIN is the customer and whose DESTINATION is the seller — the exact
# reverse of every other task, which is why both ends are resolved here.
COLLECT_LEG = 'collect_from_customer'

NON_CUSTOMER_DESTINATION_LEGS = ('return_to_client', COLLECT_LEG)

# Legs that must not fire the customer-facing messages in delivery/signals.py.
# Every one of those bodies is worded as an outbound delivery, so on a leg that
# is not delivering to the customer they are a lie told to the wrong person.
CUSTOMER_SILENT_LEGS = ('return_to_client', COLLECT_LEG)

RouteOrigin = namedtuple('RouteOrigin', ['label', 'latitude', 'longitude'])

RouteDestination = namedtuple('RouteDestination', [
    'zone', 'street', 'building', 'unit', 'area',
    'latitude', 'longitude', 'address_text', 'is_customer',
])

_EMPTY_ORIGIN = RouteOrigin('', None, None)
_EMPTY_DESTINATION = RouteDestination(None, None, None, None, None,
                                      None, None, '', True)


def task_origin(task):
    """Where the driver collects the goods for this leg.

    hub_warehouse is the signal, not the leg name: `hub_delivery` and
    `return_to_client` are both created with pickup_location=None and the hub
    stamped on instead, exactly as returns.resolve_hub_for_task reads it. The
    order's pickup location is the merchant, which is not where the parcel is.
    Everything else reports that merchant pickup location as before. Callers
    should select_related('hub_warehouse', 'hub_warehouse__warehouse',
    'order__pickup_location') to keep this free.
    """
    if task is None:
        return _EMPTY_ORIGIN

    # A return pickup runs backwards: the goods are in the customer's hands, so
    # the order's own customer fields are the collection point, not the address
    # the parcel was originally sent from.
    if getattr(task, 'task_leg', None) == COLLECT_LEG:
        order = task.order if task.order_id else None
        addr = task_address(task)
        if order is None and addr is None:
            return _EMPTY_ORIGIN
        label = (getattr(order, 'customer_name', '')
                 or getattr(addr, 'full_name', '') or 'Customer')
        latitude = getattr(order, 'latitude', None) or getattr(addr, 'dl_latitude', None)
        longitude = getattr(order, 'longitude', None) or getattr(addr, 'dl_longitude', None)
        return RouteOrigin(label, latitude, longitude)

    hub = task.hub_warehouse if task.hub_warehouse_id else None
    if hub is not None:
        warehouse = getattr(hub, 'warehouse', None)
        # "Main Dock" on its own means nothing to a driver with two hubs to
        # choose from, so lead with the site name when it is loaded.
        label = ' — '.join(p for p in (getattr(warehouse, 'name', ''),
                                       getattr(hub, 'name', '')) if p)
        # A dock row can be saved with no pin of its own — the add form does not
        # require one — and a blank pin renders a dead map tile in the PWA. The
        # site's own coordinates are the next best truth for the same address.
        latitude, longitude = hub.latitude, hub.longitude
        if latitude is None or longitude is None:
            latitude = getattr(warehouse, 'latitude', None)
            longitude = getattr(warehouse, 'longitude', None)
        return RouteOrigin(label or 'Hub', latitude, longitude)

    order = task.order if task.order_id else None
    pickup = getattr(order, 'pickup_location', None)
    if pickup is None:
        return _EMPTY_ORIGIN
    return RouteOrigin(pickup.pickup_location_title or '',
                       pickup.pickup_lat, pickup.pickup_lon)


def task_destination(task, addr=None):
    """Structured drop-off for a task card.

    ``is_customer`` is False when the parcel is going back to the client rather
    than out to the buyer — the card uses it to drop the customer-only trimmings
    (area name, pin accuracy badge) that would otherwise describe the wrong end
    of the trip.
    """
    if task is None:
        return _EMPTY_DESTINATION

    if addr is None:
        addr = task_address(task)

    def _a(name):
        return getattr(addr, name, None) if addr is not None else None

    # The seller's counter is the drop-off on a return pickup. The task's own
    # address row describes the CUSTOMER here — it is the origin, not the
    # destination — so it is the one leg that reads neither the row nor the order.
    if getattr(task, 'task_leg', None) == COLLECT_LEG:
        # A collection can be routed to a hub instead of the client's counter
        # (delivery.services.returns.resolve_collection_destination, snapshotted
        # onto the task at creation). The hub then wins, exactly as it does for a
        # hub leg's ORIGIN — same field, other end of the trip.
        hub = task.hub_warehouse if task.hub_warehouse_id else None
        if hub is not None:
            warehouse = getattr(hub, 'warehouse', None)
            label = ' — '.join(p for p in (getattr(warehouse, 'name', ''),
                                           getattr(hub, 'name', '')) if p)
            latitude, longitude = hub.latitude, hub.longitude
            if latitude is None or longitude is None:
                latitude = getattr(warehouse, 'latitude', None)
                longitude = getattr(warehouse, 'longitude', None)
            return RouteDestination(
                zone=hub.zone_number, street=None, building=None, unit=None,
                area=None, latitude=latitude, longitude=longitude,
                address_text=label or 'Hub', is_customer=False,
            )

        pickup = (task.pickup_location if task.pickup_location_id
                  else getattr(task.order if task.order_id else None,
                               'pickup_location', None))
        if pickup is None:
            return _EMPTY_DESTINATION._replace(is_customer=False)
        return RouteDestination(
            zone=pickup.pickup_zone_no, street=pickup.pickup_street_no,
            building=pickup.pickup_building_no, unit=None,
            area=pickup.locality or None,
            latitude=pickup.pickup_lat, longitude=pickup.pickup_lon,
            address_text=pickup.pickup_location_title or '', is_customer=False,
        )

    if getattr(task, 'task_leg', None) in NON_CUSTOMER_DESTINATION_LEGS:
        return RouteDestination(
            zone=_a('dl_zone'), street=_a('dl_street'), building=_a('dl_building'),
            unit=_a('dl_unit'), area=_a('area_name'),
            latitude=_a('dl_latitude'), longitude=_a('dl_longitude'),
            # order.customer_address is the buyer's own words about their flat.
            # Nothing about it applies to the client's office.
            address_text='', is_customer=False,
        )

    order = task.order if task.order_id else None

    def _o(name):
        return getattr(order, name, None) if order is not None else None

    return RouteDestination(
        zone=_o('dl_zone') or _a('dl_zone'),
        street=_o('dl_street') or _a('dl_street'),
        building=_o('dl_building') or _a('dl_building'),
        unit=_a('dl_unit'),
        area=_a('area_name'),
        latitude=_o('latitude') or _a('dl_latitude'),
        longitude=_o('longitude') or _a('dl_longitude'),
        address_text=_o('customer_address') or '',
        is_customer=True,
    )
