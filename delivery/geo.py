# Purpose: Geography derived from an order — pickup→drop distance, and the delivery
#          area (neighbourhood) name within the drop zone.
# Used by: orders.signals (keeps both current), the Seller Transactions ledger,
#          the driver task cards, and the two backfill commands.
# Notes: Distances are great-circle, NOT road distance — always shorter than the trip
#        driven. Reuses TaskStatusPoint.haversine_km rather than adding another copy
#        of the formula. Both cached maps live in LocMemCache, which is per-process:
#        invalidation reaches one gunicorn worker, so siblings can serve a stale map
#        until the TTL. That is cosmetic here and deliberately not worked around.

from decimal import Decimal

from django.core.cache import cache

ZONE_COORD_CACHE_KEY = 'delivery_zone_coord_map_v1'
ZONE_COORD_CACHE_TTL = 3600


def zone_coord_map():
    """``{zone_number: (lat, lon)}`` for every active zone.

    Cached for an hour: 96 rows that change only when staff edit a zone, and it
    is read once per page of orders rather than once per row.
    """
    cached = cache.get(ZONE_COORD_CACHE_KEY)
    if cached is not None:
        return cached

    from delivery.models import ZoneName

    coords = {
        row[0]: (float(row[1]), float(row[2]))
        for row in ZoneName.objects.filter(
            is_active=True, latitude__isnull=False, longitude__isnull=False,
        ).values_list('zone_number', 'latitude', 'longitude')
    }
    cache.set(ZONE_COORD_CACHE_KEY, coords, ZONE_COORD_CACHE_TTL)
    return coords


# Qatar's bounding box, with margin. A coordinate outside it is corrupt rather
# than remote — one live order carried lat 2.0 (a truncated 25.x) and produced a
# 2,588 km "delivery". Such points are discarded so the zone centre is used
# instead of publishing a fiction as a measurement.
QATAR_BOUNDS = (24.0, 26.5, 50.5, 52.0)  # lat_min, lat_max, lon_min, lon_max


def in_qatar(lat, lon):
    lat_min, lat_max, lon_min, lon_max = QATAR_BOUNDS
    return lat_min <= lat <= lat_max and lon_min <= lon <= lon_max


def _point(lat, lon):
    if lat is None or lon is None:
        return None
    try:
        lat, lon = float(lat), float(lon)
    except (TypeError, ValueError):
        return None
    if not in_qatar(lat, lon):
        return None
    return lat, lon


SOURCE_OSRM = 'osrm'
SOURCE_STRAIGHT = 'straight_line'
SOURCE_ZONE = 'zone_estimate'


def route_endpoints(order, zone_coords=None):
    """``(pickup, drop, exact)`` for an order, each point ``(lat, lon)`` or None.

    Precedence per end is the most precise coordinate available:
      drop   — the order's own confirmed coordinates, else the drop zone's centre
      pickup — the pickup location's coordinates, else its zone's centre
    ``exact`` is False as soon as either end falls back to a zone centre.
    """
    if zone_coords is None:
        zone_coords = zone_coord_map()

    exact = True

    drop = _point(getattr(order, 'latitude', None), getattr(order, 'longitude', None))
    if drop is None:
        drop = zone_coords.get(order.dl_zone)
        exact = False

    pickup_location = getattr(order, 'pickup_location', None)
    pickup = None
    if pickup_location is not None:
        pickup = _point(pickup_location.pickup_lat, pickup_location.pickup_lon)
        if pickup is None:
            pickup = zone_coords.get(pickup_location.pickup_zone_no)
            exact = False

    return pickup, drop, exact


def route_distance(order, zone_coords=None, use_routing=True):
    """Pickup→drop distance for one order.

    Returns ``(km, exact, source)``. ``km`` is a Decimal rounded to 0.1, or None
    when neither end can be located.

    The road distance from OSRM is preferred because it is what the driver
    actually covers; the straight-line figure is the fallback and reads roughly
    25-40% short. ``source`` records which one this is, so no screen has to guess
    whether it is looking at a measurement or an approximation.
    """
    from delivery.models import TaskStatusPoint

    pickup, drop, exact = route_endpoints(order, zone_coords)
    if drop is None or pickup is None:
        return None, False, ''

    if use_routing:
        from delivery.routing import road_distance_km

        km = road_distance_km(pickup, drop)
        if km is not None:
            return Decimal(str(km)), exact, SOURCE_OSRM

    km = TaskStatusPoint.haversine_km(pickup[0], pickup[1], drop[0], drop[1])
    return (Decimal(str(round(km, 1))), exact,
            SOURCE_STRAIGHT if exact else SOURCE_ZONE)


def stored_route_distance(order, zone_coords=None):
    """The order's saved distance, computing one on the fly if it has none.

    Reading the stored field keeps every screen on the same number; the live
    fallback only covers rows saved before the field existed. It skips routing so
    a page render never waits on the routing service.
    """
    if order.route_distance_km is not None:
        return (order.route_distance_km, order.route_distance_exact,
                order.route_distance_source)
    return route_distance(order, zone_coords, use_routing=False)


def apply_route_distance(order, zone_coords=None, use_routing=True):
    """Set the three ``route_distance_*`` fields on an order in memory.

    Returns True when anything changed, so callers can skip a pointless write.
    """
    km, exact, source = route_distance(order, zone_coords, use_routing=use_routing)
    changed = (
        order.route_distance_km != km
        or order.route_distance_exact != exact
        or order.route_distance_source != source
    )
    order.route_distance_km = km
    order.route_distance_exact = exact
    order.route_distance_source = source
    return changed


def annotate_route_distance(orders):
    """Stamp ``route_km`` / ``route_km_exact`` / ``route_km_source`` for display.

    One zone map for the whole batch — never a query per row.
    """
    zone_coords = zone_coord_map()
    for order in orders:
        (order.route_km, order.route_km_exact,
         order.route_km_source) = stored_route_distance(order, zone_coords)
    return orders


# ============================================================================
# DELIVERY AREA — the neighbourhood inside the drop zone
# ============================================================================

ZONE_AREA_CACHE_KEY = 'delivery_zone_area_map_v1'
ZONE_AREA_CACHE_TTL = 3600

SOURCE_AREA_PIN = 'pin'
SOURCE_AREA_ONLY = 'only_area'
SOURCE_AREA_SAME_AS_ZONE = 'same_as_zone'
SOURCE_AREA_UNRESOLVED = 'unresolved'


def zone_area_map():
    """``{zone_number: [(area_name, lat, lon), ...]}`` for every active, pinned area.

    760 rows across 90 zones, changed only when staff edit an area. Cached because
    this is read on every order save, not once per page.

    An area whose name merely repeats its zone name is stored with an empty name:
    the card already prints the zone name above it, so repeating it wastes the
    line. Doing that here means the comparison runs once per hour over 90 rows
    instead of once per order.
    """
    cached = cache.get(ZONE_AREA_CACHE_KEY)
    if cached is not None:
        return cached

    from delivery.models import ZoneArea

    areas = {}
    rows = ZoneArea.objects.filter(
        is_active=True, latitude__isnull=False, longitude__isnull=False,
    ).values_list(
        'zone__zone_number', 'zone__zone_name', 'area_name', 'latitude', 'longitude',
    )
    for zone_number, zone_name, area_name, lat, lon in rows:
        name = (area_name or '').strip()
        if name.casefold() == (zone_name or '').strip().casefold():
            name = ''
        # float here so the per-order hot path never touches Decimal
        areas.setdefault(zone_number, []).append((name, float(lat), float(lon)))

    cache.set(ZONE_AREA_CACHE_KEY, areas, ZONE_AREA_CACHE_TTL)
    return areas


def resolve_delivery_area(order, area_map=None):
    """``(area_name, source)`` — the neighbourhood this order is being delivered to.

    A zone carries up to 63 areas, so the zone number alone cannot name one; the
    delivery pin picks the nearest area centre within the zone. ``source`` records
    how the answer was reached so a screen never has to treat a pin match and a
    fallback as equally trustworthy.

    Pass ``area_map`` to resolve a batch without a query per order.
    """
    if area_map is None:
        area_map = zone_area_map()

    areas = area_map.get(order.dl_zone)
    if not areas:
        return '', SOURCE_AREA_UNRESOLVED

    pin = _point(getattr(order, 'latitude', None), getattr(order, 'longitude', None))
    if pin is None:
        # No usable pin: a single-area zone names itself, anything else is a guess.
        if len(areas) == 1:
            name = areas[0][0]
            return name, SOURCE_AREA_ONLY if name else SOURCE_AREA_SAME_AS_ZONE
        return '', SOURCE_AREA_UNRESOLVED

    from delivery.models import TaskStatusPoint

    lat, lon = pin
    name = min(
        areas,
        key=lambda area: TaskStatusPoint.haversine_km(lat, lon, area[1], area[2]),
    )[0]
    return name, SOURCE_AREA_PIN if name else SOURCE_AREA_SAME_AS_ZONE


def apply_delivery_area(order, area_map=None):
    """Set the two ``delivery_area_*`` fields on an order in memory.

    Returns True when anything changed, so callers can skip a pointless write.
    """
    name, source = resolve_delivery_area(order, area_map)
    changed = (
        order.delivery_area_name != name
        or order.delivery_area_source != source
    )
    order.delivery_area_name = name
    order.delivery_area_source = source
    return changed
