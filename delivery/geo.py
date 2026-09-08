# Purpose: Straight-line pickup→drop distance for an order, with a zone-centre fallback.
# Used by: the Seller Transactions ledger (Distance column + CSV/XLSX export).
# Notes: Great-circle distance, NOT road distance — always shorter than the trip driven.
#        Reuses TaskStatusPoint.haversine_km rather than adding another copy of the formula.

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
