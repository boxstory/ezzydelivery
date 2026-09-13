# Purpose: Deterministic price suggestion for a PricingEnquiry — base from the rate matrix, then adjustments.
# Used by: workforce.views.pricing_inquiry_detail (Suggested Rate panel) and its recalculate endpoint.
# Notes: No LLM ever produces the number. Percentage effects apply to the BASE, never to the running
#        total, so the order rules are evaluated in cannot change the result. An unknown input
#        contributes nothing — silence beats a made-up surcharge.

from dataclasses import dataclass, field
from decimal import Decimal, ROUND_CEILING, ROUND_HALF_UP
import hashlib
import json
import logging

from webpages.pricing import bands

logger = logging.getLogger('webpages')

# Adjustments always evaluate in this order, so a stored breakdown reads the
# same way every time regardless of how the rules happen to be sorted in the DB.
DIMENSION_ORDER = (
    'weight', 'size', 'speed', 'same_day_pickup', 'cod', 'special_handling',
    'returns', 'pickup_type', 'pickup_locations', 'pickups_per_day',
)

ZERO = Decimal('0')

# What an unanswered input is called on a sales call. Raw field names leak the
# database schema onto a staff screen ("Avarage_Number_Of_Order..."), including
# the historic misspelling.
MISSING_LABELS = {
    'monthly_orders': 'Orders per month',
    'typical_delivery_distance': 'Typical delivery distance',
    'delivery_coverage': 'Delivery coverage',
    'average_package_weight': 'Average parcel weight',
    'typical_package_size': 'Parcel size',
    'speed_delivery_offer_to_customers': 'Delivery speed promised',
    'current_delivery_cost': 'What they pay today',
    'average_order_value_qar': 'Average order value',
    'cod_orders_share': 'Share of orders paid COD',
    'type_of_pickup_location': 'Where we collect from',
}


def label_for_missing(field):
    return MISSING_LABELS.get(field, field.replace('_', ' ').capitalize())


@dataclass
class Suggestion:
    """Return value of suggest_price. `available=False` means we declined to guess."""
    available: bool = False
    reason: str = ''
    inquiry_id: int = None
    # Annotated, otherwise @dataclass treats it as a plain class attribute and
    # the constructor silently rejects it.
    ruleset: object = None
    ruleset_code: str = ''
    inputs: dict = field(default_factory=dict)
    breakdown: list = field(default_factory=list)
    base_price: Decimal = None
    suggested_price: Decimal = None
    clamped_reason: str = ''
    floor_value: Decimal = None
    floor_basis: str = ''
    flags: list = field(default_factory=list)
    comparables: dict = field(default_factory=dict)
    missing: list = field(default_factory=list)
    inputs_hash: str = ''

    @property
    def missing_labels(self):
        return [label_for_missing(name) for name in self.missing]

    @property
    def margin(self):
        """Always None while the floor is a configured guess rather than a measured cost.

        Deliberately not computed anywhere else — one property is the whole
        defence against a screen implying we know our margin when we do not.
        """
        if self.ruleset is None or not self.ruleset.can_report_margin:
            return None
        if self.suggested_price is None or self.floor_value is None:
            return None
        return self.suggested_price - self.floor_value


def _hash_inputs(inputs):
    payload = json.dumps(inputs, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode()).hexdigest()


def _in_range(value, low, high):
    """low <= value < high, with either bound optional. Upper bound is exclusive
    so adjacent bands cannot both claim a value sitting exactly on the edge."""
    if value is None:
        return False
    if low is not None and value < low:
        return False
    if high is not None and value >= high:
        return False
    return True


def _matches(rule, inputs):
    value = inputs.get(rule.match_field)

    if rule.match_kind == rule.KIND_ALWAYS:
        return True

    if rule.match_kind == rule.KIND_BOOL:
        return bool(value)

    if rule.match_kind == rule.KIND_CONTAINS:
        needle = (rule.match_value or '').strip().lower()
        return any(needle == str(item).strip().lower() for item in (value or []))

    if rule.match_kind == rule.KIND_BAND:
        return str(value or '').strip().lower() == (rule.match_value or '').strip().lower()

    if rule.match_kind == rule.KIND_NUMERIC:
        if not _in_range(value, rule.match_min, rule.match_max):
            return False
        # Base rules carry a second axis (volume AND distance). Both must hit.
        if rule.match2_field:
            return _in_range(inputs.get(rule.match2_field), rule.match2_min, rule.match2_max)
        return True

    return False


def _line(dimension, rule, effect, amount, delta, running, note=''):
    return {
        'dimension': dimension,
        'rule_id': getattr(rule, 'pk', None),
        'label': getattr(rule, 'label', note) or note,
        'explanation': getattr(rule, 'explanation', '') or '',
        'effect': effect,
        'amount': str(amount),
        'delta': str(delta),
        'running_total': str(running),
    }


def _round(value, ruleset):
    step = ruleset.rounding_step or Decimal('1')
    if step <= 0:
        return value
    quotient = value / step
    rounding = ROUND_CEILING if ruleset.rounding_mode == ruleset.ROUND_UP else ROUND_HALF_UP
    return (quotient.quantize(Decimal('1'), rounding=rounding) * step).quantize(Decimal('0.01'))


def suggest_price(inquiry, ruleset=None, *, with_comparables=True):
    """Compute a suggested rate. Never raises for missing data — it declines instead."""
    from webpages.models import PricingRuleSet

    if ruleset is None:
        ruleset = PricingRuleSet.objects.filter(is_active=True).first()
    if ruleset is None:
        return Suggestion(available=False, reason='No active rate card', inquiry_id=inquiry.pk)

    inputs = bands.normalise_enquiry(inquiry)
    missing = inputs.get('missing', [])
    result = Suggestion(
        inquiry_id=inquiry.pk, ruleset=ruleset, ruleset_code=ruleset.code,
        inputs=inputs, missing=missing, inputs_hash=_hash_inputs(inputs),
        floor_value=ruleset.min_price_floor, floor_basis=ruleset.floor_basis,
    )

    rules = list(ruleset.rules.filter(is_active=True).order_by('dimension', 'priority', 'id'))
    by_dimension = {}
    for rule in rules:
        by_dimension.setdefault(rule.dimension, []).append(rule)

    # ── Base ──────────────────────────────────────────────────────────────────
    from webpages.models import PricingRule
    base_rule = next((r for r in by_dimension.get(PricingRule.DIM_BASE, []) if _matches(r, inputs)), None)

    if base_rule is not None:
        base = Decimal(base_rule.amount)
        breakdown = [_line(PricingRule.DIM_BASE, base_rule, 'set_base', base, base, base)]
    else:
        # Off the card entirely. Over 30 km has no published rate at any tier, so
        # saying so beats inventing one; an unanswered question just falls back.
        base = Decimal(ruleset.base_price_default)
        distance = inputs.get('distance_km')
        if distance is not None:
            note = f"No rate for {inputs.get('distance_band') or 'this distance'} — priced manually"
            result.flags.append('outside_rate_card')
        else:
            note = 'Volume or distance not answered — default base applied'
            result.flags.append('base_defaulted')
        breakdown = [_line(PricingRule.DIM_BASE, None, 'set_base', base, base, base, note=note)]

    running = base

    # ── Adjustments ───────────────────────────────────────────────────────────
    for dimension in DIMENSION_ORDER:
        for rule in by_dimension.get(dimension, []):
            if not _matches(rule, inputs):
                continue
            if rule.effect == rule.EFFECT_PCT:
                # Against the base, never the running total — otherwise the order
                # of two percentage rules would silently change the answer.
                delta = (base * Decimal(rule.amount) / Decimal('100')).quantize(Decimal('0.01'))
            elif rule.effect == rule.EFFECT_ADD:
                delta = Decimal(rule.amount)
            else:
                delta = Decimal(rule.amount) - running  # a later set_base
            running += delta
            breakdown.append(_line(dimension, rule, rule.effect, rule.amount, delta, running))
            if rule.stop_on_match:
                break

    # ── Clamps, floor, rounding — each its own visible line ───────────────────
    max_up = base * (Decimal('1') + Decimal(ruleset.max_total_uplift_pct) / Decimal('100'))
    max_down = base * (Decimal('1') - Decimal(ruleset.max_total_discount_pct) / Decimal('100'))
    if running > max_up:
        delta = max_up - running
        running = max_up
        result.clamped_reason = f'Capped at +{ruleset.max_total_uplift_pct}% of base'
        result.flags.append('clamped_uplift')
        breakdown.append(_line('clamp', None, 'clamp', max_up, delta, running,
                               note=result.clamped_reason))
    elif running < max_down:
        delta = max_down - running
        running = max_down
        result.clamped_reason = f'Floored at -{ruleset.max_total_discount_pct}% of base'
        result.flags.append('clamped_discount')
        breakdown.append(_line('clamp', None, 'clamp', max_down, delta, running,
                               note=result.clamped_reason))

    floor = Decimal(ruleset.min_price_floor)
    if running < floor:
        delta = floor - running
        running = floor
        result.flags.append('floor_applied')
        breakdown.append(_line('floor', None, 'floor', floor, delta, running,
                               note=f'Minimum price {floor} (configured, not a measured cost)'))

    rounded = _round(running, ruleset)
    if rounded != running:
        breakdown.append(_line('rounding', None, 'round', ruleset.rounding_step,
                               rounded - running, rounded,
                               note=f'Rounded to nearest {ruleset.rounding_step}'))
    running = rounded

    result.available = True
    result.base_price = base
    result.suggested_price = running
    result.breakdown = breakdown

    # ── Context that never moves the number ───────────────────────────────────
    benchmark = inputs.get('benchmark_mid')
    if benchmark is not None:
        if running > benchmark:
            result.flags.append('above_benchmark')
        elif running < benchmark:
            result.flags.append('below_benchmark')

    if with_comparables:
        try:
            from webpages.pricing import comparables
            result.comparables = comparables.realized_charges(
                monthly_orders=inputs.get('monthly_orders'),
                distance_km=inputs.get('distance_km'),
            )
            p25, p75 = result.comparables.get('p25'), result.comparables.get('p75')
            if not result.comparables.get('thin'):
                if p25 is not None and running < p25:
                    result.flags.append('below_realized_p25')
                if p75 is not None and running > p75:
                    result.flags.append('above_realized_p75')
        except Exception:
            logger.exception('Comparables lookup failed for PricingEnquiry %s', inquiry.pk)
            result.comparables = {}

    if missing:
        result.flags.append('incomplete_inputs')
    return result


def get_or_create_suggestion(inquiry, ruleset=None, *, user=None):
    """Persist the suggestion, reusing the stored row when nothing has changed.

    Without the hash guard, merely opening the inquiry page would write a new
    audit row every time and the accuracy report would drown in duplicates.
    """
    from webpages.models import PricingSuggestion

    result = suggest_price(inquiry, ruleset=ruleset)
    if not result.available:
        return result, None

    # Matched on the PRICE as well as the inputs. The hash covers what the
    # customer answered, not the rate card — so after a rule is edited the same
    # answers legitimately produce a different number, and reusing the old row
    # would make the panel show one figure while the record holds another
    # (an accept then gets logged as an override of a price nobody ever saw).
    existing = PricingSuggestion.objects.filter(
        inquiry=inquiry, ruleset_code=result.ruleset_code, inputs_hash=result.inputs_hash,
        suggested_price=result.suggested_price,
    ).order_by('-created_at').first()
    if existing is not None:
        # The denormalised copy can still be stale if an earlier row won the
        # pointer, so keep the inquiry in step with what the panel renders.
        if inquiry.suggested_price_value != existing.suggested_price:
            type(inquiry).objects.filter(pk=inquiry.pk).update(
                latest_suggestion=existing,
                suggested_price_value=existing.suggested_price,
                suggested_price_at=existing.created_at,
            )
        return result, existing

    comparables_data = result.comparables or {}
    record = PricingSuggestion.objects.create(
        inquiry=inquiry,
        ruleset=result.ruleset,
        ruleset_code=result.ruleset_code,
        inputs_snapshot={k: (str(v) if isinstance(v, Decimal) else v)
                         for k, v in result.inputs.items()},
        inputs_hash=result.inputs_hash,
        breakdown=result.breakdown,
        base_price=result.base_price,
        suggested_price=result.suggested_price,
        clamped_reason=result.clamped_reason or None,
        floor_value=result.floor_value,
        floor_basis=result.floor_basis,
        comparable_median=comparables_data.get('median'),
        comparable_p25=comparables_data.get('p25'),
        comparable_p75=comparables_data.get('p75'),
        comparable_sample=comparables_data.get('count') or 0,
        benchmark_midpoint=result.inputs.get('benchmark_mid'),
        flags=result.flags,
        generated_by=user if (user is not None and user.is_authenticated) else None,
    )

    type(inquiry).objects.filter(pk=inquiry.pk).update(
        latest_suggestion=record,
        suggested_price_value=record.suggested_price,
        suggested_price_at=record.created_at,
    )
    return result, record
