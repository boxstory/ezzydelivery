# Purpose: What we have actually billed for comparable deliveries — context beside a suggested price.
# Used by: webpages.pricing.engine (flags only) and the staff Suggested Rate panel.
# Notes: Only staff-VERIFIED charges count. dl_price is the model default of 20 on most rows, so
#        including it would manufacture a fake 20.00 mode out of data nobody ever confirmed.

from datetime import timedelta
from decimal import Decimal
import logging
import statistics

from django.core.cache import cache
from django.db.models import F
from django.utils import timezone

logger = logging.getLogger('webpages')

# Below this, a median is noise dressed as insight — the panel says so instead.
MIN_COMPARABLE_SAMPLE = 20

CACHE_TTL = 900  # 15 min; every lead scans the same few hundred rows.

# Distance buckets, matching the rate matrix so a comparison is like-for-like.
DISTANCE_BUCKETS = [
    ('under_10', None, Decimal('10')),
    ('10_15', Decimal('10'), Decimal('15')),
    ('15_25', Decimal('15'), Decimal('25')),
    ('25_30', Decimal('25'), Decimal('30')),
    ('over_30', Decimal('30'), None),
]


def _bucket_for(km):
    if km is None:
        return None
    for name, low, high in DISTANCE_BUCKETS:
        if (low is None or km >= low) and (high is None or km < high):
            return name
    return None


def _percentiles(values):
    if not values:
        return {}
    ordered = sorted(values)
    # Computed in Python rather than in SQL: the sample is small, and this keeps
    # the numbers identical on Postgres and on the sqlite test database.
    def pct(fraction):
        if len(ordered) == 1:
            return ordered[0]
        index = min(int(round(fraction * (len(ordered) - 1))), len(ordered) - 1)
        return ordered[index]

    return {
        'median': Decimal(str(statistics.median(ordered))).quantize(Decimal('0.01')),
        'p25': pct(0.25),
        'p75': pct(0.75),
        'min': ordered[0],
        'max': ordered[-1],
    }


def realized_charges(*, monthly_orders=None, distance_km=None, months=12):
    """Verified charges for comparable delivered tasks.

    Returns {count, thin, median, p25, p75, min, max, excluded_unverified,
    distance_bucket, distance_coverage_pct}. Context only — the caller must
    never let these move a suggested price.
    """
    from delivery.charges import BILLABLE_CHARGE
    from delivery.models import DeliveryTask

    bucket = _bucket_for(distance_km)
    cache_key = f'pricing:comparables:{bucket or "all"}:{months}'
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    cutoff = timezone.now().date() - timedelta(days=30 * months)

    base_qs = DeliveryTask.objects.filter(
        dl_task_status='delivered',
        dl_task_date__gte=cutoff,
    )
    verified_qs = base_qs.filter(verified_delivery_charge__isnull=False)
    excluded = base_qs.filter(verified_delivery_charge__isnull=True).count()

    rows = list(
        verified_qs.annotate(charge=BILLABLE_CHARGE, km=F('order__route_distance_km'))
                   .values_list('charge', 'km')
    )

    with_distance = [r for r in rows if r[1] is not None]
    coverage = round(100 * len(with_distance) / len(rows), 1) if rows else 0.0

    scoped = rows
    if bucket is not None and with_distance:
        matched = [r for r in with_distance if _bucket_for(r[1]) == bucket]
        # Only narrow to the distance bucket when doing so leaves enough rows to
        # say anything; otherwise a like-for-like comparison of 3 tasks is worse
        # than an honest overall figure.
        if len(matched) >= MIN_COMPARABLE_SAMPLE:
            scoped = matched
        else:
            bucket = None

    values = [Decimal(str(charge)) for charge, _ in scoped if charge is not None]
    result = {
        'count': len(values),
        'thin': len(values) < MIN_COMPARABLE_SAMPLE,
        'excluded_unverified': excluded,
        'distance_bucket': bucket,
        'distance_coverage_pct': coverage,
        'months': months,
    }
    result.update(_percentiles(values))

    # Two-value distributions are the norm here (we have billed 20 or 25 and
    # little else), so say that plainly instead of implying a market curve.
    result['distinct_values'] = sorted({str(v) for v in values})[:6]

    cache.set(cache_key, result, CACHE_TTL)
    return result
