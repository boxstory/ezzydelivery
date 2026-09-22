# Purpose: The one definition of which fields each integration platform actually uses.
# Used by: business/forms.py + api_form_fields.js (client form), workforce seller_detail modal.
# Notes: Both UIs render from this via as_json(). They each carried their own hardcoded
#        copy before, which is how a field added to one silently went missing from the other.

import json

# Field groups, so a platform is described by what it needs rather than by a
# hand-kept list of every box on the form.
_PLATFORM_CREDENTIALS = ['api_key', 'api_secret', 'api_access_token', 'api_version']
_STORE_LOCATION = ['site_api_url', 'site_contry']
_ENDPOINT_PATHS = ['order_api_endpoint', 'product_api_endpoint']

# A custom REST integration authenticates against the SELLER's API with the key
# their site issued us, so none of the platform credential fields above apply —
# showing them is what made merchants paste their key into the wrong box.
_PULL_ORDERS = [
    'fetch_orders_url', 'fetch_auth_style', 'fetch_auth_name', 'fetch_api_key',
    'fetch_list_path', 'fetch_status_path', 'fetch_status_include', 'fetch_enabled',
]
_PULL_PRODUCTS = ['fetch_products_url', 'fetch_products_list_path']

# Product field paths, posted as pm_<field> and stored as one JSON mapping.
PRODUCT_MAP_FIELDS = [
    'item_name', 'item_sku', 'item_price', 'barcode',
    'image_url', 'brand_name', 'inventory_qty', 'platform_id',
]

PLATFORMS = {
    'shopify': {
        'fields': _PLATFORM_CREDENTIALS + _STORE_LOCATION + _ENDPOINT_PATHS,
        'labels': {
            'api_key': 'Client ID (Shopify Custom App API key)',
            'api_secret': 'Client Secret (Shopify Custom App API secret key)',
            'api_access_token': 'Admin API Access Token (starts with shpat_)',
            'site_api_url': 'Store URL (e.g. mystore.myshopify.com)',
        },
        'autofill': {
            'order_api_endpoint': '/admin/api/2024-01/orders.json',
            'product_api_endpoint': '/admin/api/2024-01/products.json',
            'site_contry': 'Qatar',
        },
    },
    # Shopify's two setup paths need different credentials; the form resolves to
    # this variant when the merchant picks "Custom App".
    'shopify_custom_app': {
        'fields': ['api_access_token'] + _STORE_LOCATION + _ENDPOINT_PATHS,
        'labels': {
            'api_access_token': 'Admin API Access Token (starts with shpat_)',
            'site_api_url': 'Store URL (e.g. mystore.myshopify.com)',
        },
        'autofill': {
            'order_api_endpoint': '/admin/api/2024-01/orders.json',
            'product_api_endpoint': '/admin/api/2024-01/products.json',
            'site_contry': 'Qatar',
        },
    },
    'woocommerce': {
        'fields': ['api_key', 'api_secret'] + _STORE_LOCATION + _ENDPOINT_PATHS,
        'labels': {'site_api_url': 'Store URL (with https://)'},
        'autofill': {
            'order_api_endpoint': '/wp-json/wc/v3/orders',
            'product_api_endpoint': '/wp-json/wc/v3/products',
            'site_contry': 'Qatar',
        },
    },
    'tiktokshop': {
        'fields': _PLATFORM_CREDENTIALS + [
            'tiktok_shop_id', 'tiktok_shop_cipher', 'tiktok_refresh_token'],
        'labels': {},
        'autofill': {'api_version': '202309'},
    },
    'google_sheet': {
        'fields': ['site_api_url', 'google_sheet_url'],
        'labels': {'site_api_url': 'Google Sheet URL'},
        'autofill': {},
    },
    'magento': {
        'fields': ['api_access_token'] + _STORE_LOCATION + _ENDPOINT_PATHS,
        'labels': {},
        'autofill': {
            'order_api_endpoint': '/rest/V1/orders',
            'product_api_endpoint': '/rest/V1/products',
            'site_contry': 'Qatar',
        },
    },
    'opencart': {
        'fields': ['api_key', 'api_secret'] + _STORE_LOCATION + _ENDPOINT_PATHS,
        'labels': {},
        'autofill': {
            'order_api_endpoint': '/index.php?route=api/order',
            'product_api_endpoint': '/index.php?route=api/product',
            'site_contry': 'Qatar',
        },
    },
    'prestashop': {
        'fields': ['api_key'] + _STORE_LOCATION + _ENDPOINT_PATHS,
        'labels': {},
        'autofill': {
            'order_api_endpoint': '/api/orders',
            'product_api_endpoint': '/api/products',
            'site_contry': 'Qatar',
        },
    },
    'bigcommerce': {
        'fields': _PLATFORM_CREDENTIALS + _STORE_LOCATION + _ENDPOINT_PATHS,
        'labels': {},
        'autofill': {
            'order_api_endpoint': '/stores/api/v3/orders',
            'product_api_endpoint': '/stores/api/v3/catalog/products',
            'site_contry': 'Qatar',
        },
    },
    # Custom is the seller's own REST API. It shows the fetch configuration and
    # nothing else: the platform credential boxes and the endpoint-path boxes
    # belong to clients that append a path to a store URL, which this does not do.
    'custom': {
        'fields': _STORE_LOCATION + _PULL_ORDERS + _PULL_PRODUCTS,
        'labels': {'site_api_url': "Seller's website (for reference)"},
        'autofill': {'site_contry': 'Qatar'},
    },
}

# Every field any platform can show — what the UI hides when not listed.
ALL_FIELDS = sorted({f for spec in PLATFORMS.values() for f in spec['fields']})

# Fields shown only while a particular other field has a particular value.
# Keeps a conditional out of the two UIs' own code.
CONDITIONAL_FIELDS = {
    'fetch_auth_name': {'field': 'fetch_auth_style', 'values': ['header', 'query']},
}


def fields_for(platform):
    """The field names a platform uses, or custom's set for an unknown platform."""
    spec = PLATFORMS.get(platform) or PLATFORMS['custom']
    return list(spec['fields'])


def as_dict():
    """The whole map, for a template to hand to the UIs via |json_script.

    Returns the dict rather than a JSON string on purpose: json_script encodes
    what it is given, so passing pre-encoded JSON would double-encode it and the
    browser would parse it back to a string instead of an object.
    """
    return {
        'platforms': PLATFORMS,
        'all_fields': ALL_FIELDS,
        'conditional': CONDITIONAL_FIELDS,
        'product_map_fields': PRODUCT_MAP_FIELDS,
    }


def as_json():
    """The same map as a JSON string, for callers that embed it themselves."""
    return json.dumps(as_dict())
