# Purpose: Turn the pricing form's band strings ("101-300", "15+ kg", "Not sure") into numbers.
# Used by: webpages.pricing.engine — the ONLY place in the codebase that reads a band string as a number.
# Notes: Every value here comes from a public form and can also be free-typed by staff on the inquiry
#        edit action, so parsing is tolerant by design. An unparseable band returns known=False with
#        mid=None — never 0, because a 0 would silently price as if the customer had answered.

from collections import namedtuple
from decimal import Decimal, InvalidOperation
import re

# What "300+" is worth. A pure guess, applied consistently and documented so a
# reader knows the open-topped bands are an assumption, not data.
OPEN_TOP_FACTOR = Decimal('1.5')

# Weekly → monthly. 52/12, the same conversion the volume tiers were written in.
WEEKS_PER_MONTH = Decimal('4.33')

Band = namedtuple('Band', 'raw low high mid known')

UNKNOWN = Band(raw='', low=None, high=None, mid=None, known=False)

# Answers that mean "no usable value". "Mixed" is a real option on the weight and
# size questions and carries no number at all; the rest are blanks and opt-outs.
_UNKNOWN_VALUES = {
    '', 'not sure', 'mixed', 'mixed sizes', 'none', 'n/a', 'na', 'any', 'any time',
    'flexible', 'other', 'unknown', '-', '—', 'tbd',
}

# Units to drop before the numbers are read. '%' sits outside the \b...\b group
# because it is not a word character — \b%\b can never match at end of string.
_UNIT_RE = re.compile(r'(\b(?:qar|qr|kms?|km|kgs?|kg|orders?|pallets?|shelves)\b\.?|%)',
                      re.IGNORECASE)

_BELOW_RE = re.compile(r'^(?:below|under|less\s+than|up\s+to|<)\s*([\d.]+)$', re.IGNORECASE)
_ABOVE_RE = re.compile(r'^(?:above|over|more\s+than|>)\s*([\d.]+)$', re.IGNORECASE)
_PLUS_RE = re.compile(r'^([\d.]+)\s*\+$')
_RANGE_RE = re.compile(r'^([\d.]+)\s*-\s*([\d.]+)$')
_PLAIN_RE = re.compile(r'^([\d.]+)$')


# ── Ordinal scales ────────────────────────────────────────────────────────────
# These answers have an order but no magnitude — "Large" is not a number of
# anything. Rules match them by rank, which keeps a rule table readable
# ("size_rank >= 3") without pretending a parcel size is a quantity.

COVERAGE_RANK = {'doha only': 1, 'both': 2, 'all qatar': 3}

SIZE_RANK = {
    'small (envelopes / packets)': 1,
    'medium (shoe box size)': 2,
    'large (appliances / bulky)': 3,
}

SPEED_RANK = {
    'standard (3-5 days)': 1,
    # A 2-3 day promise is the same kind of plan-ahead job as 3-5 days, so it
    # shares rank 1 and the standard discount with it.
    '2-3 days': 1,
    '48 hours': 2,
    # Next day is quicker than 48 hours but still an overnight batch, not a
    # same-day run — rank 2 keeps it in the neutral tier the card prices at zero.
    'next day': 2,
    'same day': 3,
    'express (few hours)': 4,
}

# How hard a pickup POINT is to serve, independent of how many there are — the
# count is priced separately by the pickup_locations ladder, so ranking multi-store
# above a single store here would charge the same fact twice.
PICKUP_TYPE_RANK = {
    'fulfillment': 1,
    'office': 2,
    'store': 2,
    'multiple store': 2,
    'home': 3,
}

STORAGE_RANK = {
    'a few shelves': 1,
    '1-5 pallets': 2,
    '5-20 pallets': 3,
    '20+ pallets': 4,
}

# Distance answers → km midpoint. The rate matrix is keyed on distance, so this
# is the single most load-bearing table in the module. Midpoints are chosen to
# land unambiguously inside their matrix row: 5 → "<10", 12.5 → "10-15",
# 20 → "15-25", 27.5 → "25-30". "Over 30 km" deliberately lands at 35, outside
# every row, so the engine flags it for manual pricing instead of inventing a rate.
DISTANCE_MIDPOINT = {
    'under 10 km': Decimal('5'),
    '10-15 km': Decimal('12.5'),
    '15-25 km': Decimal('20'),
    '25-30 km': Decimal('27.5'),
    'over 30 km': Decimal('35'),
}


def _key(raw):
    """Lowercased, dash-normalised text with units INTACT — for table lookups.

    Kept separate from _clean because the ordinal tables key on phrases that
    contain unit words ("1-5 pallets", "over 30 km"); stripping units first
    would make those keys unmatchable.
    """
    text = (raw or '').strip()
    if not text:
        return ''
    # The form labels render en/em dashes ("50 – 100"); the stored data-value uses
    # a hyphen, but staff paste the label often enough that both must parse.
    text = text.replace('–', '-').replace('—', '-').replace('−', '-')
    return re.sub(r'\s+', ' ', text).strip().lower()


def _clean(raw):
    """_key plus unit removal — for reading a value as a number."""
    text = _key(raw)
    if not text:
        return ''
    return re.sub(r'\s+', ' ', _UNIT_RE.sub('', text)).strip()


def _dec(value):
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None


def parse_band(raw, cap=None):
    """Band string → Band(low, high, mid, known).

    `cap` bounds an open-topped band — pass 100 for a percentage so "Above 75%"
    reads as 75-100 rather than running past 100 via OPEN_TOP_FACTOR.
    """
    original = (raw or '').strip()
    text = _clean(original)
    if text in _UNKNOWN_VALUES:
        return UNKNOWN._replace(raw=original)

    cap = _dec(cap) if cap is not None else None

    match = _BELOW_RE.match(text)
    if match:
        high = _dec(match.group(1))
        return Band(original, Decimal('0'), high, high / 2, True) if high is not None \
            else UNKNOWN._replace(raw=original)

    for pattern in (_ABOVE_RE, _PLUS_RE):
        match = pattern.match(text)
        if match:
            low = _dec(match.group(1))
            if low is None:
                return UNKNOWN._replace(raw=original)
            if cap is not None:
                return Band(original, low, cap, (low + cap) / 2, True)
            return Band(original, low, None, low * OPEN_TOP_FACTOR, True)

    match = _RANGE_RE.match(text)
    if match:
        low, high = _dec(match.group(1)), _dec(match.group(2))
        if low is None or high is None:
            return UNKNOWN._replace(raw=original)
        if low > high:
            low, high = high, low
        return Band(original, low, high, (low + high) / 2, True)

    match = _PLAIN_RE.match(text)
    if match:
        value = _dec(match.group(1))
        return Band(original, value, value, value, True) if value is not None \
            else UNKNOWN._replace(raw=original)

    return UNKNOWN._replace(raw=original)


def rank_of(raw, table):
    """Ordinal lookup for the scales above. Unmatched → None, never a default rank."""
    return table.get(_key(raw))


def rank_of_multi(raw, table):
    """Highest rank among a comma-separated multi-answer.

    Speed, parcel size and pickup type are multi-select bubbles on the public
    form, so they arrive as "Express (Few Hours), Same Day". A plain rank_of on
    that whole string matches nothing, and the dimension silently prices at zero
    — which is how half of all inquiries ended up with no speed surcharge at all.

    We take the MAX, not the average: a business that promises express delivery
    has to be resourced for express, whatever else it also offers.
    """
    ranks = [table.get(_key(part)) for part in split_multi(raw)]
    ranks = [r for r in ranks if r is not None]
    return max(ranks) if ranks else None


def distance_km(raw):
    """Distance answer → km midpoint. Falls back to generic parsing so a staff-typed
    "12 km" still works, and so the table is not the only accepted phrasing."""
    if _clean(raw) in _UNKNOWN_VALUES:
        return None
    known = DISTANCE_MIDPOINT.get(_key(raw))
    if known is not None:
        return known
    return parse_band(raw).mid


def split_multi(raw):
    """Comma-separated multi-answers (special handling) → cleaned list."""
    return [part.strip() for part in (raw or '').split(',') if part.strip()]


def normalise_enquiry(inquiry):
    """PricingEnquiry → the flat dict the rule engine matches against.

    Also reports `volume_source` (which of the three volume questions was used)
    and `missing` (everything that came back unknown), both of which the staff
    panel shows — an unanswered question must be visible, not silently priced.
    """
    missing = []

    def band(field, cap=None):
        parsed = parse_band(getattr(inquiry, field, None), cap=cap)
        if not parsed.known:
            missing.append(field)
        return parsed

    # Volume: history first, then what they expect, then last week scaled up.
    # Which one won is reported, so sales can see a suggestion built on a
    # forecast rather than on trading history.
    monthly = parse_band(getattr(inquiry, 'avarage_number_of_order_done_last_month', None))
    volume_source = 'last_month'
    if not monthly.known:
        monthly = parse_band(getattr(inquiry, 'avarage_number_of_order_expect_next_month', None))
        volume_source = 'expected_next_month'
    if not monthly.known:
        weekly = parse_band(getattr(inquiry, 'avarage_number_of_order_last_week', None))
        if weekly.known:
            monthly = weekly._replace(mid=weekly.mid * WEEKS_PER_MONTH)
            volume_source = 'last_week_scaled'
    if not monthly.known:
        volume_source = None
        missing.append('monthly_orders')

    weekly_band = parse_band(getattr(inquiry, 'avarage_number_of_order_last_week', None))
    km = distance_km(getattr(inquiry, 'typical_delivery_distance', None))
    if km is None:
        missing.append('typical_delivery_distance')

    coverage_rank = rank_of(getattr(inquiry, 'delivery_coverage', None), COVERAGE_RANK)
    if coverage_rank is None:
        missing.append('delivery_coverage')

    size_rank = rank_of_multi(getattr(inquiry, 'typical_package_size', None), SIZE_RANK)
    if size_rank is None:
        missing.append('typical_package_size')

    speed_rank = rank_of_multi(getattr(inquiry, 'speed_delivery_offer_to_customers', None),
                               SPEED_RANK)
    if speed_rank is None:
        missing.append('speed_delivery_offer_to_customers')

    pickup_type_rank = rank_of_multi(getattr(inquiry, 'type_of_pickup_location', None),
                                     PICKUP_TYPE_RANK)
    if pickup_type_rank is None:
        missing.append('type_of_pickup_location')

    weight = band('average_package_weight')
    benchmark = band('current_delivery_cost')
    aov = band('average_order_value_qar')
    cod_share = band('cod_orders_share', cap=100) if inquiry.is_required_COD_service else UNKNOWN
    pickup_locations = parse_band(getattr(inquiry, 'number_of_pickup_locations', None))
    pickups_per_day = parse_band(getattr(inquiry, 'number_of_pickup_times_in_day', None))

    return {
        'monthly_orders': monthly.mid,
        'volume_source': volume_source,
        'weekly_orders': weekly_band.mid,
        'three_month_milestone': parse_band(
            getattr(inquiry, 'orders_expected_in_next_3_months_milestone', None)).mid,

        'distance_km': km,
        'distance_band': (getattr(inquiry, 'typical_delivery_distance', '') or '').strip(),
        'coverage_rank': coverage_rank,

        'weight_mid_kg': weight.mid,
        'size_rank': size_rank,
        'speed_rank': speed_rank,
        'aov_mid': aov.mid,
        'benchmark_mid': benchmark.mid,
        'benchmark_band': (getattr(inquiry, 'current_delivery_cost', '') or '').strip(),

        'cod_required': bool(inquiry.is_required_COD_service),
        'cod_share_mid': cod_share.mid,
        'same_day_required': bool(inquiry.is_frequent_same_day_pick_and_delivery_required),
        'special_handling': (split_multi(inquiry.special_handling_detail)
                             if inquiry.is_special_handling_required else []),
        'returns_required': bool(inquiry.is_return_logistics_required),

        'pickup_type_rank': pickup_type_rank,
        'pickup_type': (getattr(inquiry, 'type_of_pickup_location', '') or '').strip(),
        'pickup_locations_mid': pickup_locations.mid,
        'pickups_per_day_mid': pickups_per_day.mid,
        'storage_rank': rank_of(getattr(inquiry, 'fulfillment_storage_volume', None), STORAGE_RANK),
        'is_local': bool(inquiry.is_located_in_qatar),

        'missing': missing,
    }
