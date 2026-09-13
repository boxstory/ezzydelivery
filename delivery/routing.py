# Purpose: Road-distance lookups against the self-hosted OSRM routing service.
# Used by: delivery.geo.route_distance (order pickup→drop distance) and the backfill command.
# Notes: OSRM speaks lon,lat — not lat,lon. Every failure returns None so the caller falls back
#        to the straight-line figure; a routing outage must never block an order save.

import logging
import time

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

# Shared session: the backfill makes thousands of calls to the same local host,
# and a new TCP connection per order is pure overhead.
_session = requests.Session()

# Circuit breaker. Every order save asks for a distance, so if the routing
# service goes down a bulk import of 500 orders would otherwise sit through 500
# consecutive timeouts. After a few failures in a row we stop asking for a
# while and fall straight back to the straight-line figure.
_FAILURE_LIMIT = 3
_COOLDOWN_SECONDS = 60
_consecutive_failures = 0
_open_until = 0.0


def is_enabled():
    return bool(getattr(settings, 'OSRM_ENABLED', False) and
                getattr(settings, 'OSRM_BASE_URL', ''))


def _circuit_open():
    return _open_until > time.monotonic()


def _record_failure():
    global _consecutive_failures, _open_until
    _consecutive_failures += 1
    if _consecutive_failures >= _FAILURE_LIMIT:
        _open_until = time.monotonic() + _COOLDOWN_SECONDS
        logger.warning(
            'OSRM unreachable %s times in a row — pausing lookups for %ss',
            _consecutive_failures, _COOLDOWN_SECONDS,
        )


def _record_success():
    global _consecutive_failures, _open_until
    _consecutive_failures = 0
    _open_until = 0.0


def reset_circuit():
    """Clear the breaker — used by the health check and by tests."""
    _record_success()


def road_distance_km(pickup, drop, timeout=None):
    """Driving distance in km between two ``(lat, lon)`` points, or None.

    None means "no answer" — service off, unreachable, no route found — and the
    caller is expected to fall back rather than treat it as zero.
    """
    if not is_enabled() or not pickup or not drop or _circuit_open():
        return None

    base = settings.OSRM_BASE_URL.rstrip('/')
    timeout = timeout or getattr(settings, 'OSRM_TIMEOUT', 3)
    # OSRM coordinate order is lon,lat.
    coords = f"{pickup[1]},{pickup[0]};{drop[1]},{drop[0]}"
    url = f"{base}/route/v1/driving/{coords}"

    try:
        resp = _session.get(url, params={'overview': 'false'}, timeout=timeout)
        resp.raise_for_status()
        payload = resp.json()
    except (requests.RequestException, ValueError) as exc:
        logger.warning('OSRM lookup failed for %s: %s', coords, exc)
        _record_failure()
        return None

    # The service answered, so it is up even if this particular pair has no route.
    _record_success()

    if payload.get('code') != 'Ok' or not payload.get('routes'):
        # NoRoute/NoSegment are normal for a point in the sea or off-network.
        return None

    metres = payload['routes'][0].get('distance')
    if metres is None:
        return None
    return round(metres / 1000.0, 1)


def route_leg(origin, destination, timeout=None):
    """The driving route between two ``(lat, lon)`` points, or None.

    Returns ``{'points': [[lat, lng], ...], 'km': float}``. The geometry is
    OSRM's simplified overview — a dashed line across a city map, not a
    turn-by-turn track — which is a couple of dozen points rather than the five
    hundred the full one carries for the same trip.

    Used to reconstruct the stretch of trail lost while a driver was inside an
    external navigation app. It is an estimate of where they went, never a
    measurement, and callers must present it as such.

    None means "no answer" — service off, unreachable, or no route — exactly as
    :func:`road_distance_km` does.
    """
    if not is_enabled() or not origin or not destination or _circuit_open():
        return None

    base = settings.OSRM_BASE_URL.rstrip('/')
    timeout = timeout or getattr(settings, 'OSRM_TIMEOUT', 3)
    # OSRM coordinate order is lon,lat.
    coords = f"{origin[1]},{origin[0]};{destination[1]},{destination[0]}"
    url = f"{base}/route/v1/driving/{coords}"

    try:
        resp = _session.get(
            url, params={'overview': 'simplified', 'geometries': 'geojson'}, timeout=timeout)
        resp.raise_for_status()
        payload = resp.json()
    except (requests.RequestException, ValueError) as exc:
        logger.warning('OSRM geometry lookup failed for %s: %s', coords, exc)
        _record_failure()
        return None

    _record_success()

    if payload.get('code') != 'Ok' or not payload.get('routes'):
        return None

    route = payload['routes'][0]
    coordinates = (route.get('geometry') or {}).get('coordinates') or []
    if len(coordinates) < 2:
        return None

    # GeoJSON is lon,lat; every map consumer here works in lat,lng.
    points = [[round(lat, 6), round(lon, 6)] for lon, lat in coordinates]
    metres = route.get('distance')
    return {
        'points': points,
        'km': round(metres / 1000.0, 1) if metres is not None else None,
    }


def health():
    """(ok, detail) for the ops page — is the routing service answering?"""
    if not is_enabled():
        return False, 'OSRM disabled (set OSRM_ENABLED=True)'
    # A health check is an explicit "try again", so never let a tripped breaker
    # report the service as down when it may have recovered.
    reset_circuit()
    # A short hop inside Doha; any real answer proves the graph is loaded.
    km = road_distance_km((25.2854, 51.5310), (25.2760, 51.5200))
    if km is None:
        return False, f'No response from {settings.OSRM_BASE_URL}'
    return True, f'OSRM answering ({km} km test route)'
