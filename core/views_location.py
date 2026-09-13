"""
Purpose: Resolve a pasted Google Maps short link (maps.app.goo.gl / goo.gl/maps) into lat/lng for the shared "Paste / Drop Shared Location" fields.
Used by: workforce/static/workforce/js/qnas-verify.js (loaded by wf_dashboard_base.html and business_dashboard_base.html); URL core:resolve_location.
Notes: The browser cannot follow the redirect itself — Google sends no CORS header on goo.gl — so this hop is the only way to read the pin. The host is allow-listed with urlparse BEFORE any outbound request: GOOGLE_LINK_PATTERN in address_tools is a substring match and happily matches maps.app.goo.gl.evil.com, so only the validated URL is handed on, never the raw pasted text.
"""

import hashlib
import json
import logging
import re
from urllib.parse import urlparse

from django.core.cache import cache
from django.http import JsonResponse
from django.views.decorators.http import require_POST

logger = logging.getLogger(__name__)

# Hostnames we are willing to make an outbound request to. Compared against the
# parsed hostname exactly — never against a substring of the pasted text.
ALLOWED_MAP_HOSTS = frozenset([
    'goo.gl',
    'maps.app.goo.gl',
    'maps.google.com',
    'www.google.com',
    'google.com',
])

_URL_RE = re.compile(r'https?://[^\s"\'<>]+', re.IGNORECASE)

# A shared pin never moves, so a resolved link can be cached hard.
_RESOLVE_TTL = 60 * 60 * 24

# Each call costs one outbound request to Google; cap how fast one user can spend them.
_RATE_LIMIT = 60
_RATE_WINDOW = 60


def _allowed_map_url(url):
    """Return url if its hostname is an allow-listed Google Maps host, else None."""
    try:
        host = (urlparse(url).hostname or '').lower()
    except ValueError:
        return None
    return url if host in ALLOWED_MAP_HOSTS else None


def _first_map_url(text):
    """Pick the first allow-listed Google Maps URL out of pasted text."""
    for candidate in _URL_RE.findall(text):
        allowed = _allowed_map_url(candidate)
        if allowed:
            return allowed
    return None


def _over_rate_limit(user_id):
    key = 'maplink:rate:%s' % user_id
    hits = cache.get_or_set(key, 0, _RATE_WINDOW)
    try:
        hits = cache.incr(key)
    except ValueError:          # key expired between get_or_set and incr
        cache.set(key, 1, _RATE_WINDOW)
        hits = 1
    return hits > _RATE_LIMIT


@require_POST
def resolve_location(request):
    """Resolve a pasted Maps short link to {lat, lng}. Any signed-in user may call it.

    Returns JSON rather than a login redirect so the fetch() caller can read the
    failure. `in_qatar` is advisory: a customer pin outside Qatar is almost always
    a mistake, but it is surfaced as a warning rather than rejected.
    """
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Not signed in'}, status=403)

    try:
        payload = json.loads(request.body or b'{}')
    except ValueError:
        return JsonResponse({'error': 'Invalid request'}, status=400)

    text = (payload.get('text') or '').strip()[:500]
    if not text:
        return JsonResponse({'error': 'No text provided'}, status=400)

    url = _first_map_url(text)
    if not url:
        return JsonResponse({'error': 'Not a Google Maps link'}, status=400)

    cache_key = 'maplink:' + hashlib.sha1(url.encode('utf-8')).hexdigest()
    cached = cache.get(cache_key)
    if cached:
        return JsonResponse(cached)

    if _over_rate_limit(request.user.id):
        return JsonResponse({'error': 'Too many link lookups — wait a moment'}, status=429)

    from ai_agent.tools.address_tools import extract_coords_from_text

    try:
        lat, lng, source, resolved = extract_coords_from_text(url)
    except Exception:
        logger.exception('[LOC] short-link resolve failed for %s', url)
        return JsonResponse({'error': 'Could not reach Google — try again'}, status=502)

    if lat is None or lng is None:
        return JsonResponse({'error': 'No pin found in that link'}, status=404)

    lat, lng = float(lat), float(lng)
    if not (-90.0 <= lat <= 90.0 and -180.0 <= lng <= 180.0):
        return JsonResponse({'error': 'That link resolved to an invalid pin'}, status=404)

    data = {
        'lat': lat,
        'lng': lng,
        'source': source or 'google_maps',
        'resolved_url': resolved or url,
        'in_qatar': 24.0 <= lat <= 27.0 and 50.0 <= lng <= 52.5,
    }
    cache.set(cache_key, data, _RESOLVE_TTL)
    return JsonResponse(data)
