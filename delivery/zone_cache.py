# Purpose: Cache + invalidation for zone/area lookup data used in address resolution.
# Used by: orders.signals._resolve_zone_number (reverse area scan), delivery.signals (invalidation).
# Notes: Zone/area rows change rarely, so the active-area list is cached; any ZoneName/
#        ZoneArea write clears it AND resyncs the AI parse-location ZoneTrainingData.

from django.core.cache import cache

# Cache key + TTL for the active-area lookup list
_AREAS_CACHE_KEY = 'zone_areas_active_v1'
_AREAS_TTL = 60 * 60  # 1 hour (a write invalidates it immediately anyway)


def get_active_areas():
    """
    Return a cached list of (area_name_lower, zone_number) for every active ZoneArea.
    Used by the reverse "is any area name contained in the address?" scan so that path
    no longer refetches all rows from the DB on every call.
    """
    areas = cache.get(_AREAS_CACHE_KEY)
    if areas is None:
        from delivery.models import ZoneArea
        areas = [
            (name.lower(), zone_number)
            for name, zone_number in ZoneArea.objects.filter(is_active=True)
            .values_list('area_name', 'zone__zone_number')
            if name
        ]
        cache.set(_AREAS_CACHE_KEY, areas, _AREAS_TTL)
    return areas


def invalidate_zone_cache():
    """Drop the cached active-area list. Called from ZoneName/ZoneArea save/delete signals."""
    cache.delete(_AREAS_CACHE_KEY)
