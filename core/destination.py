"""
Purpose: Decide whether an incoming store order is bound for Qatar, so a GCC-wide shop's foreign orders stay out of the import lists.
Used by: orders.tasks (staging cron), orders.views (merchant import page + quick panel), workforce.views (staff import), ai_agent.tools.import_tools.
Notes: Shopify cannot filter by country server-side — its GraphQL `query:` silently ignores an unknown field and returns everything, so this must stay client-side. Reads country/phone off four different order shapes; never import models here.
"""
import re

from core.validators import QATAR_MOBILE_PREFIXES

# EzzyDelivery delivers inside Qatar only. The per-connection switch is
# BusinessApiSettings.import_qatar_only; this is the destination it means.
SERVICE_COUNTRY = 'QA'

# Everything a merchant, Shopify or WooCommerce might call Qatar. Woo sends bare
# ISO2, Shopify sends both a code and a display name, and a human types the word.
_QATAR_ALIASES = {
    'QA', 'QAT', 'QATAR', 'STATE OF QATAR',
    'قطر',            # قطر
    'دولة قطر',  # دولة قطر
}

# Country lives under a different name on each shape we are handed. Shipping
# only: order #1011 on a live store ships to Pakistan but bills to the UAE, so a
# billing fallback would import an order we cannot deliver.
_COUNTRY_PATHS = (
    ('shipping_address', 'country_code'),   # raw Shopify REST dict / lib object
    ('shipping_address', 'country'),
    ('shipping', 'country_code'),           # WooCommerce
    ('shipping', 'country'),
)

# Flat keys on a row dict built by orders.tasks._shopify_order_to_row, which has
# already merged workforce.views._shopify_extract_row's virtual columns. Lets a
# staged TempOrder.raw_row be judged with no API call.
_FLAT_COUNTRY_KEYS = (
    'shipping.country_code', 'shipping.country',
    'address.country_code', 'address.country',
)

_PHONE_PATHS = (
    ('shipping_address', 'phone'),
    ('shipping', 'phone'),
    ('billing_address', 'phone'),
    ('billing', 'phone'),
    ('customer', 'phone'),
)

_FLAT_PHONE_KEYS = (
    'shipping.phone', 'address.phone', 'billing.phone',
    'customer_phone', 'phone',
)


def _get(obj, key):
    """One attribute read that works on a dict and on a shopify-lib object."""
    if obj is None:
        return None
    if hasattr(obj, 'get'):
        try:
            return obj.get(key)
        except Exception:
            return None
    return getattr(obj, key, None)


def canonical_country(value):
    """ISO2 for a country written any of the ways our sources write it.

    Returns '' when there is nothing readable, which the caller must treat as
    "unknown", never as "foreign".
    """
    text = str(value or '').strip()
    if not text:
        return ''
    upper = text.upper()
    if upper in _QATAR_ALIASES:
        return SERVICE_COUNTRY
    # Any other 2-letter code passes through so a foreign order is recognisable
    # in a log line as AE/BH/PK rather than a bare "not Qatar".
    if len(upper) == 2 and upper.isalpha():
        return upper
    return upper[:32]


def is_qatar_phone(raw):
    """True for a Qatar mobile: bare 8 digits starting 3/5/6/7.

    Deliberately NOT core.validators.normalize_qatar_phone — that raises for an
    8-digit non-3567 number and passes foreign 9-15 digit numbers straight
    through, so it answers "is this storable", not "is this Qatari".
    """
    digits = re.sub(r'\D', '', str(raw or ''))
    if digits.startswith('00974') and len(digits) == 13:
        digits = digits[5:]
    elif digits.startswith('974') and len(digits) == 11:
        digits = digits[3:]
    return len(digits) == 8 and digits[0] in QATAR_MOBILE_PREFIXES


def order_country(order):
    """ISO2 of where the order ships, or '' if the shape does not say."""
    if order is None:
        return ''
    for parent, child in _COUNTRY_PATHS:
        found = canonical_country(_get(_get(order, parent), child))
        if found:
            return found
    if hasattr(order, 'get'):
        for key in _FLAT_COUNTRY_KEYS:
            found = canonical_country(_get(order, key))
            if found:
                return found
    return ''


def order_phone(order):
    """The best phone on the order, searched in the order the row builder uses."""
    if order is None:
        return ''
    for parent, child in _PHONE_PATHS:
        value = _get(_get(order, parent), child)
        if value:
            return str(value)
    for key in _FLAT_PHONE_KEYS:
        value = _get(order, key)
        if value:
            return str(value)
    return ''


def destination_verdict(order):
    """'local', 'foreign' or 'unknown' for one order.

    'unknown' means neither a country nor a phone could be read. Callers keep an
    unknown order: a wrongly hidden Qatar order is never delivered and nobody
    finds out, which is worse than a foreign order reaching a human who can see
    the address and refuse it.
    """
    country = order_country(order)
    if country == SERVICE_COUNTRY:
        return 'local'

    phone = order_phone(order)
    if is_qatar_phone(phone):
        # A Qatari mobile outranks the country box: shoppers routinely leave the
        # store's default country selected. Accepted trade-off — a Qatari buyer
        # shipping a gift to Dubai is imported.
        return 'local'

    if not country and not phone:
        return 'unknown'
    return 'foreign'


def is_foreign(order, api_settings=None):
    """True only when this order should be withheld from import.

    Passing api_settings applies the per-connection switch, so a caller can gate
    on one call: nothing is withheld unless the seller ticked the box.
    """
    if api_settings is not None and not getattr(api_settings, 'import_qatar_only', False):
        return False
    return destination_verdict(order) == 'foreign'


def filter_deliverable(orders, api_settings=None):
    """Split orders into (kept, dropped).

    Mirrors ezzy_api.store_pull.filter_by_status so both import filters read the
    same way. ``dropped`` carries a short reason per order for the log line and
    the staff-facing count, not for the merchant.
    """
    if api_settings is not None and not getattr(api_settings, 'import_qatar_only', False):
        return list(orders), []

    kept, dropped = [], []
    for order in orders:
        if destination_verdict(order) == 'foreign':
            label = _get(order, 'name') or _get(order, 'order_id') or _get(order, 'id') or '?'
            dropped.append(f'{label} -> {order_country(order) or "unknown"}')
        else:
            kept.append(order)
    return kept, dropped
