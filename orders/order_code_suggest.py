"""
Purpose: Suggest the next "Your Order Number" for a business by incrementing the
         numeric tail of their most recent order code.
Used by: orders.views.add_order (prefills the editable client_order_code field)
Notes:   Seeded by the business's latest order of any source (manual, Shopify,
         WooCommerce, sheet import). The suggestion is a hint, never enforced:
         the field stays editable, and the unique-per-business constraint is
         still what actually decides.
"""
import re

from orders import models as orders_models

# Trailing digits are the counter; everything before them is kept verbatim so
# "OR-0042" -> "OR-0043" and "#33" -> "#34" keep their prefix and zero-padding.
_TAIL_RE = re.compile(r'^(.*?)(\d+)$')

# How many taken codes we step over before giving up (a gap-filled sequence
# shouldn't turn into an unbounded query loop).
_MAX_PROBES = 20


def _bump(code):
    """Return `code` with its trailing number incremented, or None if it has none."""
    match = _TAIL_RE.match(code)
    if not match:
        return None
    prefix, digits = match.group(1), match.group(2)
    nxt = str(int(digits) + 1)
    # Preserve zero-padding until the number outgrows it: 0042 -> 0043, 99 -> 100
    if len(nxt) < len(digits):
        nxt = nxt.rjust(len(digits), '0')
    return f'{prefix}{nxt}'


def suggest_next_order_code(business_id):
    """
    Next order number to prefill for `business_id`, or '' when we can't tell.

    Returns '' when the business has no orders yet, when their last code has no
    numeric tail (e.g. "WALKIN"), or when the next 20 candidates are all taken —
    in each case the field simply renders empty.
    """
    if not business_id:
        return ''

    last = (
        orders_models.Order.objects
        .filter(business_id=business_id)
        .exclude(client_order_code='')
        .exclude(client_order_code__isnull=True)
        .order_by('-id')
        .values_list('client_order_code', flat=True)
        .first()
    )
    if not last:
        return ''

    # Build the candidate run upfront so the "is it free?" check is one bounded
    # query — a prefix scan would pull every code for a high-volume business.
    candidates = []
    candidate = _bump(last.strip())
    while candidate and len(candidates) < _MAX_PROBES:
        candidates.append(candidate)
        candidate = _bump(candidate)
    if not candidates:
        return ''

    taken = set(
        orders_models.Order.objects
        .filter(business_id=business_id, client_order_code__in=candidates)
        .values_list('client_order_code', flat=True)
    )
    # An import or an earlier manual entry may already hold the next number, so
    # hand back the first candidate nobody has claimed.
    return next((c for c in candidates if c not in taken), '')
