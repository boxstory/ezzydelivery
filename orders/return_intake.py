# Purpose: One intake path for a return raised from a form — the claim and, when asked, the driver's collection trip, in a single submit.
# Used by: workforce.views.returns_task_create (staff returns desk) and orders.views.add_return (seller console)
# Notes: Both consoles post the same field names and land here, so the two forms cannot drift apart. A seller's collection
#        is left unpublished (to_review) like their ordinary new order; staff's goes straight to the driver pool.

import logging
import re

from django.core.exceptions import ValidationError
from django.db.models import Q

from core.utils import (contains_arabic, convert_arabic_numerals,
                        format_whatsapp_number, translate_to_english)
from core.validators import safe_decimal, safe_int, sanitize_text
from orders.models import Order, ReturnRequest
from orders.services import (create_return_pickup_order, create_return_request,
                             create_standalone_return_request,
                             open_return_for_order)

logger = logging.getLogger(__name__)

# The two ways goods come back to a client. 'order' copies the customer off an
# order we carried; 'standalone' is for goods that never rode with us, where the
# address typed on the form IS the claim.
MODES = ('order', 'standalone')

_REASONS = {key for key, _ in ReturnRequest.RETURN_REASON_CHOICES}


def resolve_mode(value, default='order'):
    """The mode a form asked for, or `default` when it named none.

    A value that is present but unrecognised means 'standalone' rather than the
    default: a typo must never silently drop a submit into the path that reads
    an order, where an order reference nobody typed could resolve to somebody.
    """
    if value in MODES:
        return value
    return default if not value else 'standalone'


# How many near-misses a search offers before it stops being a shortlist. A
# customer with more orders than this is looked up by number instead.
SEARCH_LIMIT = 25

# Qatar mobiles are 8 digits, stored with or without the 974 country code
# depending on where the order came from. Matching on the last 8 means a staff
# member can type either form and a seller can paste whatever the customer sent.
_LOCAL_DIGITS = 8


def _order_qs(business=None):
    qs = (Order.objects
          .select_related('business', 'pickup_location')
          .prefetch_related('order_items__product'))
    return qs if business is None else qs.filter(business=business)


def find_order(ref, *, business=None):
    """The one order a reference names EXACTLY, or None.

    Only the two order numbers, never a phone: this is what a submit resolves
    through, and a form must never act on a guess. `business` scopes the lookup
    — always passed on the seller console, so one client can never raise a
    return against another client's order.
    """
    ref = (ref or '').strip().lstrip('#')
    if not ref:
        return None

    qs = _order_qs(business)
    return (qs.filter(order_number__iexact=ref).first()
            or qs.filter(client_order_code__iexact=ref).first())


def search_orders(ref, *, business=None, limit=SEARCH_LIMIT):
    """What a typed search could mean. Returns (exact_order, candidates).

    Staff rarely have the order number — the customer is on the phone and the
    number they are calling from is the only thing anyone knows. So a search
    takes a mobile too, and because one customer buys more than once, it can
    come back with several orders for somebody to choose between.

    An exact hit on either order number short-circuits: typing a number you
    already have should not make you pick it out of a list. Otherwise every
    near-miss comes back newest first, and the caller shows them.
    """
    ref = (ref or '').strip().lstrip('#')
    if not ref:
        return None, []

    exact = find_order(ref, business=business)
    if exact is not None:
        return exact, [exact]

    digits = re.sub(r'\D', '', ref)
    matches = Q(order_number__icontains=ref) | Q(client_order_code__icontains=ref)
    if len(digits) >= 6:
        tail = digits[-_LOCAL_DIGITS:]
        matches |= (Q(customer_phone__icontains=tail)
                    | Q(customer_whatsapp__icontains=tail))

    candidates = list(_order_qs(business).filter(matches)
                      .order_by('-order_date', '-id')[:limit])

    # One hit is not a shortlist — it is the answer, and making somebody click
    # it would be noise.
    return (candidates[0] if len(candidates) == 1 else None), candidates


def _remaining(item):
    """How much of a line is still out there — quantity less what has already
    come back. The same figure create_return_request defaults to, so a form
    showing lines and a form showing none agree on what a whole parcel is."""
    return max((item.quantity or 0) - (item.quantity_returned or 0), 0)


def order_lines(order):
    """The lines a return form should offer, as [{item, label, remaining}].

    Lines with nothing left to return are dropped rather than shown ticked at
    zero: create_return_request skips them anyway, and a row that cannot do
    anything only invites somebody to try.
    """
    if order is None:
        return []
    lines = []
    for item in order.order_items.all():
        remaining = _remaining(item)
        if remaining <= 0:
            continue
        product = item.product
        label = 'Item'
        if product is not None:
            label = ' '.join(
                part for part in (product.brand_name, product.item_name) if part
            ) or str(product)
        lines.append({'item': item, 'label': label, 'remaining': remaining})
    return lines


def selected_items(post, order):
    """The [(OrderItem, qty)] the form ticked, or None meaning "the whole parcel".

    None is not the same as an empty list: create_return_request reads None as
    every line at its remaining quantity, which is what a whole parcel coming
    back means. A form that shows no line pickers at all posts no marker and so
    gets that default.
    """
    if not post.get('items_scoped'):
        return None

    picked = []
    for item in order.order_items.all():
        remaining = _remaining(item)
        if remaining <= 0 or not post.get(f'item_{item.id}'):
            continue
        qty = safe_int(post.get(f'qty_{item.id}'), default=remaining,
                       minimum=0, maximum=100000)
        picked.append((item, min(qty, remaining)))
    return picked


def added_lines(post, business):
    """The product rows typed into "What is coming back", as [(Product, qty, price)].

    Posted under the same names the staff and seller order forms use
    (inline_product_id[] / inline_quantity[] / inline_unit_price[]), so the
    Select2 row markup and its JS are shared rather than reinvented.

    Every product is re-checked against `business` here. The picker only ever
    offers that client's catalogue, but the ids come from the browser and a
    line belonging to another client would put their goods on this client's
    collection.
    """
    from product.models import Product

    ids = post.getlist('inline_product_id[]') if hasattr(post, 'getlist') else []
    qtys = post.getlist('inline_quantity[]') if hasattr(post, 'getlist') else []
    prices = post.getlist('inline_unit_price[]') if hasattr(post, 'getlist') else []
    if not ids:
        return []

    wanted = [safe_int(pid, default=0) for pid in ids]
    owned = {p.id: p for p in Product.objects.filter(
        id__in=[w for w in wanted if w], business=business)}

    lines = []
    for i, pid in enumerate(wanted):
        product = owned.get(pid)
        if product is None:
            continue
        qty = safe_int(qtys[i] if i < len(qtys) else 1, default=1,
                       minimum=1, maximum=10000)
        price = safe_decimal(prices[i] if i < len(prices) else None)
        lines.append((product, qty, price))
    return lines


def attach_added_lines(ret, post, business):
    """Write the hand-added product rows onto `ret`. Returns how many were added.

    Separate from the claim's creation because both kinds of claim take them —
    a standalone one, where they are the only lines there are, and an
    order-backed one, where they sit alongside the ticked order lines.
    """
    from orders.models import ReturnItem

    lines = added_lines(post, business)
    for product, qty, price in lines:
        ReturnItem.objects.create(
            return_request=ret, order_item=None, product=product,
            quantity_returned=qty, unit_price=price)
    return len(lines)


def clean_customer(post):
    """The customer block of a standalone claim, normalised the way the staff
    order form normalises it — so a collection card reads like every other card
    in the driver's app."""
    name = sanitize_text(post.get('customer_name', ''), True)
    address = sanitize_text(post.get('customer_address', ''), True)
    if contains_arabic(name):
        name = translate_to_english(name)
    if contains_arabic(address):
        address = translate_to_english(address)

    phone = convert_arabic_numerals(sanitize_text(post.get('customer_phone', ''), True))
    raw_whatsapp = sanitize_text(post.get('customer_whatsapp', ''), True)

    return {
        'customer_name': name,
        'customer_address': address,
        'customer_phone': phone,
        'customer_whatsapp': format_whatsapp_number(raw_whatsapp or phone),
    }


def raise_return(*, post, user, business=None, order=None, publish=True,
                 cod_reversal=None):
    """Create the claim the form describes and, when it asks, the collection trip.

    Returns (ReturnRequest, collection Order or None, reused_existing_claim).

    `order` set means an order-backed claim: every address, line and default
    charge is read off that order, so the customer fields on the form are
    ignored. `order` None means a standalone one and the form carries the lot.

    `publish` False leaves the collection at 'to_review' with no task in the
    pool — what a seller raising their own collection gets, the same place their
    ordinary new orders land. Staff publish, because a staff member pressing the
    button IS the approval (see create_return_pickup_order).

    Raises ValidationError on anything that would leave a claim nobody can
    collect; the caller re-renders the form with the message.
    """
    reason = (post.get('reason') or '').strip()
    if reason not in _REASONS:
        raise ValidationError("Pick a reason for the return.")

    notes = sanitize_text(post.get('reason_notes', ''))
    charge = safe_decimal(post.get('collection_charge'))
    schedule = bool(post.get('schedule_pickup'))

    reused = False
    if order is not None:
        # One open claim per order. A second one means two drivers sent for one
        # parcel, so the open claim is added to rather than duplicated — the
        # same rule business.views.return_create applies to sellers.
        ret = open_return_for_order(order)
        if ret is not None:
            reused = True
        else:
            ret = create_return_request(
                order,
                reason=reason,
                reason_notes=notes,
                items=selected_items(post, order),
                cod_reversal_amount=cod_reversal,
                status='approved',
                user=user,
            )
    else:
        if business is None:
            raise ValidationError("Pick the client this return belongs to.")
        from business.models import PickupLocation
        location = PickupLocation.objects.filter(
            id=safe_int(post.get('pickup_location'), default=0)).first()

        ret = create_standalone_return_request(
            business,
            reason=reason,
            reason_notes=notes,
            pickup_location=location,
            zone=safe_int(post.get('dl_zone'), default=None),
            street=safe_int(post.get('dl_street'), default=None),
            building=safe_int(post.get('dl_building'), default=None),
            latitude=safe_decimal(post.get('latitude')),
            longitude=safe_decimal(post.get('longitude')),
            external_reference=sanitize_text(post.get('external_reference', ''), True),
            package_description=sanitize_text(post.get('package_description', ''), True),
            package_qty=safe_int(post.get('package_qty'), default=0,
                                 minimum=0, maximum=10000),
            collection_charge=charge,
            user=user,
            **clean_customer(post),
        )

    # Before the collection is raised, never after: create_return_pickup_order
    # reads the claim's lines to build the trip's own.
    attach_added_lines(ret, post, ret.business)

    collection = None
    if schedule:
        # Deliberately not swallowed: a form that promised a driver and raised
        # none would leave staff believing the trip exists. The claim survives
        # either way — it is saved before this runs — so the caller reports the
        # claim number with the reason the trip could not be raised.
        collection = create_return_pickup_order(
            ret, charge=charge, user=user, notes=notes, publish=publish)

    return ret, collection, reused
