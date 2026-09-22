# Purpose: Fetch orders FROM a seller's own REST API, using the API key their site issued us.
# Used by: orders/tasks.py (hourly pull into TempOrder), business/views.py + workforce/views.py (live connection test).
# Notes: The mirror image of store_api.py. Their endpoint is merchant-supplied, so every
#        call is SSRF-guarded, timed out, and capped in both bytes and order count.
#        A lookup endpoint answers with recent orders, not a work queue, so the status
#        filter is what stops us booking a delivery for an already-delivered order.

import json
import logging

import requests

from core.net_guard import validate_public_url
from ezzy_api.json_paths import path_get

logger = logging.getLogger('ezzy_api')

# Their server is not ours to trust: a slow endpoint must not pin a gunicorn
# worker, and a huge or endless body must not exhaust memory.
FETCH_TIMEOUT = 20          # seconds, connect + read
MAX_RESPONSE_BYTES = 8 * 1024 * 1024
MAX_ORDERS_PER_FETCH = 200

# Keys a response might wrap its order list in, tried in order when the seller
# has not set fetch_list_path. Covers the shapes every storefront framework
# emits without asking the merchant to describe their own envelope.
COMMON_LIST_KEYS = ('orders', 'data', 'results', 'items', 'records')
COMMON_PRODUCT_KEYS = ('products', 'items', 'data', 'results', 'records', 'catalog')


class PullError(Exception):
    """A fetch that could not produce an order list. Message is shown to staff."""


def is_pull_source(api_settings):
    """True when this integration has somewhere to pull ORDERS from.

    A 'custom' row is push-only until a URL is filled in, so this is what
    separates the two kinds without a second api_type.
    """
    return bool(api_settings and (api_settings.fetch_orders_url or '').strip())


def is_product_pull_source(api_settings):
    """True when this integration can also serve a product catalogue.

    Separate from is_pull_source on purpose: an order-lookup endpoint is the
    common case and says nothing about products — a delivery feed routinely
    omits the basket entirely.
    """
    return bool(api_settings and (api_settings.fetch_products_url or '').strip())


def build_request(api_settings, url=None):
    """(url, headers, params) for one fetch, with the seller's key attached.

    The key belongs to THEIR site, not to us — never send a ClientApiKey here.
    ``url`` defaults to the orders endpoint; the product endpoint passes its own
    and reuses the same credential, because it is the same site.
    """
    url = (url or api_settings.fetch_orders_url or '').strip()
    if not url:
        raise PullError('No fetch URL is configured for this integration.')

    ok, reason = validate_public_url(url)
    if not ok:
        raise PullError(f'Fetch URL is not a public address: {reason}')

    headers = {'Accept': 'application/json', 'User-Agent': 'EzzyDelivery-OrderPull/1.0'}
    params = {}

    extra = api_settings.fetch_params
    if isinstance(extra, dict):
        params.update({str(k): str(v) for k, v in extra.items()})

    key = (api_settings.fetch_api_key or '').strip()
    style = api_settings.fetch_auth_style or 'bearer'
    name = (api_settings.fetch_auth_name or '').strip()

    if style == 'bearer':
        if not key:
            raise PullError('Auth style is Bearer but no API key is saved.')
        headers['Authorization'] = f'Bearer {key}'
    elif style == 'header':
        if not name:
            raise PullError('Auth style is "Custom header" but no header name is saved.')
        if not key:
            raise PullError('Auth style is "Custom header" but no API key is saved.')
        headers[name] = key
    elif style == 'query':
        if not name:
            raise PullError('Auth style is "Query parameter" but no parameter name is saved.')
        if not key:
            raise PullError('Auth style is "Query parameter" but no API key is saved.')
        params[name] = key
    elif style == 'basic':
        # key:secret, the way an .htaccess-protected endpoint expects it.
        import base64
        secret = (api_settings.api_secret or '').strip()
        raw = f'{key}:{secret}'.encode('utf-8')
        headers['Authorization'] = 'Basic ' + base64.b64encode(raw).decode('ascii')
    # 'none' adds nothing.

    return url, headers, params


def eligible_statuses(api_settings):
    """The statuses worth delivering, lower-cased. Empty set means take everything."""
    raw = (api_settings.fetch_status_include or '').strip()
    return {part.strip().lower() for part in raw.split(',') if part.strip()}


def filter_by_status(orders, api_settings):
    """Drop orders that are already finished or were called off.

    A lookup endpoint usually answers with a window of recent orders rather than
    a work queue: the most recent N, delivered and cancelled ones included.
    Without this, the first pull of such an endpoint books a delivery for every
    order the shop has already completed.

    Nothing is assumed about which statuses mean "deliver me" — the seller's own
    words go in fetch_status_include, because one shop's "accepted" is another's
    "confirmed".
    """
    wanted = eligible_statuses(api_settings)
    if not wanted:
        return orders, []

    path = (api_settings.fetch_status_path or 'status').strip()
    kept, dropped = [], []
    for order in orders:
        value = path_get(order, path)
        if str(value or '').strip().lower() in wanted:
            kept.append(order)
        else:
            dropped.append(str(value or '(missing)'))
    return kept, dropped


def extract_list(body, list_path='', wrapper_keys=COMMON_LIST_KEYS, what='order'):
    """The list of objects inside a decoded response body.

    A seller may return the bare array, or wrap it in an envelope. An explicit
    list path always wins; otherwise the common wrapper keys are tried before
    giving up, so most storefronts need no configuration at all.
    """
    if list_path:
        found = path_get(body, list_path)
        if not isinstance(found, list):
            raise PullError(
                f'Nothing that looks like a {what} list at "{list_path}". '
                f'Response top level was {_shape(body)}.'
            )
        return [o for o in found if isinstance(o, dict)]

    if isinstance(body, list):
        return [o for o in body if isinstance(o, dict)]

    if isinstance(body, dict):
        for key in wrapper_keys:
            found = body.get(key)
            if isinstance(found, list):
                return [o for o in found if isinstance(o, dict)]
        # One object returned bare still counts as a list of one — a "latest
        # order" endpoint is a legitimate shape.
        if any(k in body for k in ('orderNumber', 'order_number', 'sku', 'id')):
            return [body]

    raise PullError(
        f'Could not find a {what} list in the response (top level was {_shape(body)}). '
        f'Set the list path to the field holding the array.'
    )


def extract_orders(body, list_path=''):
    """Orders specifically. Kept as its own name because the mapping manager and
    the tests both speak in orders."""
    return extract_list(body, list_path, COMMON_LIST_KEYS, 'order')


def _shape(body):
    """Human description of a response body, for an error a merchant can act on."""
    if isinstance(body, list):
        return f'an array of {len(body)}'
    if isinstance(body, dict):
        keys = ', '.join(list(body.keys())[:6])
        return f'an object with keys: {keys}' if keys else 'an empty object'
    return type(body).__name__


def _fetch_json(api_settings, url=None):
    """GET ``url`` with this integration's credential; return (body, meta).

    Everything that makes an outbound call safe lives here — SSRF guard, no
    redirects, timeout, byte cap — so a second kind of fetch cannot be added
    without them. ``meta`` carries what the staff console displays: status code,
    timing, byte size, and the URL actually called (never the key).
    """
    url, headers, params = build_request(api_settings, url)

    try:
        response = requests.get(
            url, headers=headers, params=params,
            timeout=FETCH_TIMEOUT, stream=True, allow_redirects=False,
        )
    except requests.exceptions.Timeout:
        raise PullError(f'The store did not answer within {FETCH_TIMEOUT}s.')
    except requests.exceptions.SSLError as exc:
        raise PullError(f'TLS handshake with the store failed: {exc}')
    except requests.exceptions.RequestException as exc:
        raise PullError(f'Could not reach the store: {exc}')

    meta = {
        'url': url,
        'status': response.status_code,
        'ms': int(response.elapsed.total_seconds() * 1000) if response.elapsed else None,
        'bytes': 0,
        'count': 0,
    }

    try:
        # allow_redirects=False on purpose: a redirect is a second destination
        # the SSRF guard never saw, and it would carry the seller's key with it.
        if response.is_redirect or response.is_permanent_redirect:
            raise PullError(
                f'The store redirected to {response.headers.get("Location", "another URL")}. '
                f'Point the fetch URL straight at the final endpoint.'
            )

        if response.status_code == 401 or response.status_code == 403:
            raise PullError(
                f'The store rejected our key (HTTP {response.status_code}). '
                f'Check the API key and how it is sent.'
            )
        if response.status_code == 404:
            raise PullError('The store returned 404 — the fetch URL does not exist.')
        if response.status_code >= 400:
            raise PullError(f'The store returned HTTP {response.status_code}.')

        chunks, size = [], 0
        for chunk in response.iter_content(chunk_size=65536):
            size += len(chunk)
            if size > MAX_RESPONSE_BYTES:
                raise PullError(
                    f'Response exceeded {MAX_RESPONSE_BYTES // (1024 * 1024)}MB. '
                    f'Add a limit/page parameter so the store returns fewer orders per call.'
                )
            chunks.append(chunk)
        raw = b''.join(chunks)
        meta['bytes'] = size
    finally:
        response.close()

    try:
        body = json.loads(raw.decode('utf-8', errors='replace'))
    except ValueError:
        preview = raw[:120].decode('utf-8', errors='replace').strip()
        raise PullError(f'The store did not return JSON. First bytes: {preview!r}')

    return body, meta


def _cap(rows, api_settings, what):
    """Never let a store hand us an unbounded list."""
    if len(rows) > MAX_ORDERS_PER_FETCH:
        logger.warning('%s pull for business %s truncated %s to %s',
                       what, api_settings.business_id, len(rows), MAX_ORDERS_PER_FETCH)
        return rows[:MAX_ORDERS_PER_FETCH]
    return rows


def fetch_orders(api_settings, apply_status_filter=True):
    """The seller's orders, ready to stage.

    ``apply_status_filter=False`` returns everything the store sent, each order
    still carrying its own status. The staff preview uses that so "why is order X
    not in Temp Orders?" is answerable on the page, instead of the order simply
    being absent with no explanation.
    """
    body, meta = _fetch_json(api_settings, api_settings.fetch_orders_url)

    orders = _cap(extract_orders(body, (api_settings.fetch_list_path or '').strip()),
                  api_settings, 'Order')

    meta['fetched'] = len(orders)
    kept, dropped = filter_by_status(orders, api_settings)
    meta['skipped_status'] = len(dropped)
    meta['skipped_detail'] = ', '.join(sorted(set(dropped))[:6])
    meta['eligible'] = len(kept)
    if apply_status_filter:
        orders = kept
    meta['count'] = len(orders)
    return orders, meta


def fetch_products(api_settings):
    """The seller's product catalogue, as a list of raw dicts.

    Most custom integrations have no such endpoint — an order feed says nothing
    about a catalogue — so this is configured separately from the order pull.
    """
    url = (api_settings.fetch_products_url or '').strip()
    if not url:
        raise PullError('No product fetch URL is configured for this integration.')

    body, meta = _fetch_json(api_settings, url)
    products = _cap(
        extract_list(body, (api_settings.fetch_products_list_path or '').strip(),
                     COMMON_PRODUCT_KEYS, 'product'),
        api_settings, 'Product')
    meta['fetched'] = len(products)
    meta['count'] = len(products)
    return products, meta


# ---------------------------------------------------------------------------
# Product catalogue
# ---------------------------------------------------------------------------
# What a pulled product can populate. These are the Product columns the existing
# importers already fill (see product.views.product_api_import), so a seller maps
# their JSON onto one vocabulary rather than one per integration.
PRODUCT_FIELDS = (
    'item_name', 'item_sku', 'barcode', 'item_price', 'brand_name',
    'image_url', 'platform_id', 'variant_id', 'variant_title', 'inventory_qty',
    'item_description', 'item_category',
)

# The only field a product cannot be created without.
PRODUCT_REQUIRED = ('item_name',)


def resolve_product(payload, mapping):
    """One product dict, built strictly from the configured mapping.

    Deliberately guesses nothing. An unmapped field is absent rather than
    filled from a likely-looking key: a wrong SKU silently merges two products
    and a wrong price is charged to a customer, so a blank a human can see beats
    a value nobody chose. Returns {} when the payload carries no mapped name.
    """
    if not isinstance(mapping, dict) or not mapping:
        return {}

    resolved = {}
    for field in PRODUCT_FIELDS:
        path = mapping.get(field)
        if not path:
            continue
        value = path_get(payload, path)
        if isinstance(value, list):
            value = next((v for v in value if v not in (None, '')), None)
        if value in (None, ''):
            continue
        resolved[field] = value

    if not all(str(resolved.get(f) or '').strip() for f in PRODUCT_REQUIRED):
        return {}
    return resolved


def unmapped_product_fields(mapping):
    """Which of the required product fields the seller has not mapped yet."""
    mapping = mapping if isinstance(mapping, dict) else {}
    return [f for f in PRODUCT_REQUIRED if not (mapping.get(f) or '').strip()]
