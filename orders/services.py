# Purpose: Build a replacement order — fresh goods to the same customer, settled at the door.
# Used by: workforce.views.create_replacement_order (staff) and, later, the client-side view.
# Notes: The settlement figure is TYPED BY STAFF, never derived from item prices. A refund is
#        never written as a negative cod_amount — nothing downstream handles that; it is routed
#        through orders.money.refund_route instead.

import logging
import uuid
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from orders import money
from orders.models import (
    MAX_REPLACEMENT_DEPTH, Order, OrderComments, OrderItem,
)

logger = logging.getLogger(__name__)

ZERO = Decimal('0.00')

# 'fulfilled' was dropped from ORDER_STATUS_BY_CLIENT without a data migration
# (see orders/migrations/0001_initial.py); legacy rows still carry it and other
# call sites still filter on it, so it has to stay eligible here too.
ELIGIBLE_ORDER_STATUSES = ('delivered', 'fulfilled')
ELIGIBLE_TASK_STATUSES = ('failed', 'partial_delivery', 'non_reachable',
                          'returned_to_shipper')


def can_replace(order):
    """Whether `order` may be replaced. Returns (bool, reason).

    One gate for the view, the template button and the service itself, so a
    button that is shown always corresponds to a call that will succeed.
    """
    if order.order_status == 'cancelled':
        return False, "A cancelled order cannot be replaced."

    if order.replacement_depth >= MAX_REPLACEMENT_DEPTH:
        return False, (
            f"This is already replacement {order.replacement_depth} in a chain. "
            f"Look at why before sending another."
        )

    if order.order_status in ELIGIBLE_ORDER_STATUSES:
        return True, ''

    latest = order.delivery_task.order_by('-id').first()
    if latest and latest.dl_task_status in ELIGIBLE_TASK_STATUSES:
        return True, ''

    return False, (
        "Only a delivered order, or one whose last delivery failed, can be replaced."
    )


def _replacement_code(source):
    """A code the seller can recognise: their own, suffixed -R1, -R2, ...

    Better than duplicate_order's opaque WF-<uuid>, which tells a client nothing
    about which of their orders it belongs to.
    """
    n = source.replacements.count() + 1
    return f"{source.client_order_code[:56]}-R{n}"


def issue_refund(order, amount, *, user=None, reason=''):
    """Hand money back to a customer on `order`, by whichever leg can pay it.

    Returns (route, record, message). Raises ValidationError when no leg can.

    The two legs are not interchangeable. While the driver still holds the cash
    the refund comes out of his COD, which keeps his hand-in matching what he
    actually has. Once that money has been settled to the seller it is no longer
    his to give back, so it comes off the seller's float instead. Picking the
    wrong one would either make a driver short at hand-in or refund a seller's
    customer with money we never received.
    """
    from fleet import ledger_service
    from fleet.wallet_service import WalletService

    amount = money._money(amount)
    route, task, why = money.refund_route(order, amount)

    if route == 'driver_wallet':
        try:
            txn = WalletService.record_cod_return(
                driver=task.driver, delivery_task=task, amount=amount,
                created_by=user,
                notes=reason or f"Refund on order {order.order_number}")
        except ValueError as exc:
            raise ValidationError(str(exc))
        return route, txn, (
            f"Refunded {amount} from the driver's COD on task {task.dl_task_number}.")

    if route == 'client_ledger':
        try:
            entry = ledger_service.post_refund(
                order.business, amount, order=order,
                reason=reason or 'Customer refund', created_by=user)
        except ValueError as exc:
            raise ValidationError(str(exc))
        return route, entry, (
            f"Refunded {amount} against the seller's account — the COD for this "
            f"order was already settled with them.")

    raise ValidationError(why)


@transaction.atomic
def create_replacement_order(source, *, reason, items=None, collect_back=False,
                             collect_amount=None, user=None, notes='',
                             return_request=None, publish=False):
    """Create a new order re-sending goods for `source`.

    `collect_amount` is what the driver takes from the customer at the door when
    the replacement is worth more than they already paid — typed by staff, never
    computed from item prices. A refund (the replacement being worth less) is not
    expressed here: it carries no COD and the money goes back through
    money.refund_route, which knows which leg can actually pay it.

    `items` is an optional [(order_item, qty)] subset; the whole order by default.
    """
    src = Order.objects.select_for_update().get(pk=source.pk)

    ok, why = can_replace(src)
    if not ok:
        raise ValidationError(why)

    if reason not in dict(Order._meta.get_field('replacement_reason').choices):
        raise ValidationError(f"'{reason}' is not a replacement reason.")

    collect = money._money(collect_amount)
    if collect < ZERO:
        raise ValidationError(
            "A replacement collects a positive amount or nothing. "
            "To give money back, raise a refund instead.")

    # Pick & drop pays the driver a PERCENTAGE of dl_price (delivery/earnings.py),
    # so zeroing the fee there would pay him nothing for the trip. Keep his figure
    # and zero the client's side on the task instead, once it exists.
    is_pnd = src.order_type == 'pick_and_drop'

    fields = dict(
        business=src.business,
        replaces=src,
        replacement_reason=reason,
        collect_back=collect_back,
        # --- same customer, same address: the whole point ---
        customer_name=src.customer_name,
        customer_phone=src.customer_phone,
        customer_whatsapp=src.customer_whatsapp,
        customer_address=src.customer_address,
        dl_zone=src.dl_zone,
        dl_street=src.dl_street,
        dl_building=src.dl_building,
        latitude=src.latitude,
        longitude=src.longitude,
        coords_accuracy=src.coords_accuracy,
        # Must be set on the FIRST save or the first-mile pickup hook bails.
        pickup_location=src.pickup_location,
        order_type=src.order_type,
        delivery_speed=src.delivery_speed,
        package_description=src.package_description,
        package_qty=src.package_qty,
        package_weight_kg=src.package_weight_kg,
        order_notes=f"Replacement for {src.order_number}"[:100],
        # --- money ---
        cod_amount=collect,
        cod_status_by_client='pending' if collect > ZERO else 'online_paid',
        cod_status_by_staff=None,
        dl_included=True,
        dl_amount=(src.dl_amount if is_pnd else ZERO),
        # --- fresh workflow: someone confirms the goods exist before it goes live ---
        order_status='to_review',
        task_status='new_order',
        verification_status='pending',
        platform='manual',
    )

    try:
        with transaction.atomic():
            new = Order.objects.create(
                client_order_code=_replacement_code(src), **fields)
    except IntegrityError:
        # The per-business unique constraint on client_order_code; a hand-edited
        # code or a deleted replacement can make the -R<n> suffix collide.
        new = Order.objects.create(
            client_order_code=f"WF-{uuid.uuid4().hex[:8].upper()}", **fields)

    for item, qty in (items or [(i, i.quantity) for i in src.order_items.all()]):
        OrderItem.objects.create(
            order=new, product=item.product, quantity=qty,
            unit_price=item.unit_price, notes=item.notes)

    # Both threads carry the link, so either order tells the story on its own.
    label = dict(Order._meta.get_field('replacement_reason').choices).get(reason, reason)
    settle = f"Collecting {collect} at the door." if collect > ZERO else "Nothing to collect."
    OrderComments.objects.create(
        order=new, name=getattr(user, 'username', 'system'), author=user,
        author_role='system', is_internal=True,
        body=f"Replacement for {src.order_number} — {label}. {settle} {notes}".strip()[:1000])
    OrderComments.objects.create(
        order=src, name=getattr(user, 'username', 'system'), author=user,
        author_role='system', is_internal=True,
        body=f"Replacement {new.order_number} created — {label}.".strip()[:1000])

    if return_request is not None:
        # One object tells the whole story: today the refund and the return are two
        # unconnected workflows, and nothing links what was sent back to what went out.
        return_request.replacement_order = new
        return_request.save(update_fields=['replacement_order', 'updated_at'])

    if publish:
        # NOT _create_delivery_task_from_order: jumping straight to 'publish' skips
        # stock reservation, the pick list and the first-mile pickup leg, and a
        # driver would be sent to collect goods nobody set aside.
        from orders.status_actions import apply_ready_and_publish

        apply_ready_and_publish(new, user=user)

        # task_leg is not set here: the task-creation signal derives 'exchange'
        # from collect_back, so the leg is right whether the replacement was
        # published on this call or raised as a draft and published later.
        if is_pnd:
            # Driver keeps his percent of dl_price; the client is billed nothing.
            # delivery/charges.py treats a deliberate 0.00 as final, never falling
            # back to dl_price, which is exactly what makes this safe.
            new.delivery_task.update(verified_delivery_charge=ZERO,
                                     charge_verification_status='verified')

    return new


# ---------------------------------------------------------------------------
# Return requests (RMA paperwork)
# ---------------------------------------------------------------------------

def next_return_number(business):
    """A return number the seller can recognise: their code, then 8 hex.

    One generator, because the two older call sites invented two different
    formats (business/views.py used the business code, fleet/views.py used a
    'PDR-' prefix) and nothing reconciles them. New paths use this; the old two
    keep their formats until someone decides to change what sellers already see.
    """
    code = (getattr(business, 'business_code', '') or 'RET')[:12].upper()
    return f"{code}-{uuid.uuid4().hex[:8].upper()}"


def _create_claim(business, **fields):
    """Create a ReturnRequest under a fresh return number.

    uuid4 collisions are vanishingly rare, but return_number is unique and a
    clash would surface as a 500 on a driver's phone. Retry instead.
    """
    from orders.models import ReturnRequest

    for attempt in range(5):
        try:
            with transaction.atomic():
                return ReturnRequest.objects.create(
                    return_number=next_return_number(business),
                    business=business, **fields)
        except IntegrityError:
            if attempt == 4:
                raise
    raise IntegrityError('could not allocate a return number')  # pragma: no cover


@transaction.atomic
def create_return_request(order, *, reason, reason_notes='', items=None,
                          cod_reversal_amount=None, status='pending', user=None):
    """Open the RMA paperwork for `order`. Returns the ReturnRequest.

    `items` is an optional [(OrderItem, qty)] subset; None means every line at its
    remaining quantity (quantity - quantity_returned), which is what a whole parcel
    coming back means. Lines with nothing left to return are skipped.

    `cod_reversal_amount` is the refund OWED TO THE CUSTOMER and defaults to
    orders.money.collected_for(order) — what was actually taken, net of refunds
    already made. It is never the order's face value: an order the driver never
    collected on has nothing to hand back, however large its cod_amount is.
    """
    from orders.models import ReturnItem

    if items is None:
        items = [
            (item, item.quantity - (item.quantity_returned or 0))
            for item in order.order_items.all()
        ]
    items = [(item, int(qty)) for item, qty in items if int(qty) > 0]

    if cod_reversal_amount is None:
        cod_reversal_amount = money.collected_for(order)

    ret = _create_claim(
        order.business,
        order=order,
        reason=reason,
        reason_notes=reason_notes or '',
        status=status,
        cod_reversal_amount=cod_reversal_amount,
    )

    if status != 'pending' and user is not None and getattr(user, 'is_authenticated', False):
        from django.utils import timezone
        ret.reviewed_by = user
        ret.reviewed_at = timezone.now()
        ret.save(update_fields=['reviewed_by', 'reviewed_at', 'updated_at'])

    for item, qty in items:
        ReturnItem.objects.create(
            return_request=ret, order_item=item, quantity_returned=qty,
        )

    return ret


@transaction.atomic
def create_standalone_return_request(
        business, *, reason, pickup_location, customer_name='', customer_phone='',
        customer_whatsapp='', customer_address='', zone=None, street=None,
        building=None, latitude=None, longitude=None, external_reference='',
        package_description='', package_qty=0, collection_charge=None,
        reason_notes='', status='approved', user=None):
    """Open a claim for goods EzzyDelivery never delivered. Staff only.

    The client's own courier — or their shop counter — put the parcel with the
    customer, and now they want us to bring it back. There is no outbound order
    to copy an address, a charge or a line list off, so all three are typed here
    and stored on the claim itself (see ReturnRequest's standalone block).

    Opens at 'approved' rather than 'pending': a staff member raising this by
    hand IS the decision, and a claim sitting at 'pending' would be waiting for
    the seller to approve paperwork they never filed.

    `cod_reversal_amount` stays 0 and is not an argument. We never collected on
    these goods, so there is no money of ours to hand back; a refund between the
    client and their customer is not ours to record.

    Returns the ReturnRequest. Raises ValidationError on anything that would
    leave a claim nobody can collect.
    """
    from orders.models import ReturnRequest

    if business is None:
        raise ValidationError("A return needs a client.")

    if reason not in {k for k, _ in ReturnRequest.RETURN_REASON_CHOICES}:
        raise ValidationError("Pick a reason for the return.")

    if pickup_location is None:
        raise ValidationError(
            "Choose where the driver drops the goods — the client's address.")
    if pickup_location.business_id != business.pk:
        raise ValidationError(
            "That drop-off address belongs to a different client.")

    # The same floor can_schedule_return_pickup enforces, applied at the door so
    # a claim is never created that the console would then refuse to collect.
    if not (customer_phone or customer_address or zone):
        raise ValidationError(
            "Give a phone, an address or a zone — the driver has to find the "
            "customer.")

    charge = None if collection_charge is None else money._money(collection_charge)
    if charge is not None and charge < ZERO:
        raise ValidationError("A collection charge cannot be negative.")

    ret = _create_claim(
        business,
        order=None,
        reason=reason,
        reason_notes=reason_notes or '',
        status=status,
        cod_reversal_amount=ZERO,
        external_reference=(external_reference or '')[:64],
        customer_name=(customer_name or '')[:100],
        customer_phone=(customer_phone or '')[:100],
        customer_whatsapp=(customer_whatsapp or '')[:100],
        customer_address=(customer_address or '')[:255],
        dl_zone=zone,
        dl_street=street,
        dl_building=building,
        latitude=latitude,
        longitude=longitude,
        pickup_location=pickup_location,
        package_description=(package_description or '')[:255],
        package_qty=package_qty or 0,
        collection_charge=charge,
    )

    if user is not None and getattr(user, 'is_authenticated', False):
        from django.utils import timezone
        ret.reviewed_by = user
        ret.reviewed_at = timezone.now()
        ret.save(update_fields=['reviewed_by', 'reviewed_at', 'updated_at'])

    return ret


# ---------------------------------------------------------------------------
# Return pickup — the collection trip a return request asks for
# ---------------------------------------------------------------------------

# A claim in one of these is finished: nothing left to collect, and nothing
# stopping the seller opening a fresh claim on the same order.
CLOSED_RETURN_STATUSES = ('rejected', 'closed', 'refunded')

# Kept under its old name for the call sites that read as "cannot be collected".
RETURN_PICKUP_BLOCKED_STATUSES = CLOSED_RETURN_STATUSES

# A task in one of these is over; it is not going to collect anything more.
_FINISHED_TASK_STATUSES = ('delivered', 'partial_delivery', 'cancelled', 'failed',
                           'returned_to_shipper')


def open_return_for_order(order):
    """The claim still being worked on for `order`, or None.

    A seller with a return in flight should be adding to it, not opening a second
    one — three clicks used to mean three claims and three collections, with
    nothing anywhere pointing that out.
    """
    if order is None:
        return None
    return (order.return_requests
            .exclude(status__in=CLOSED_RETURN_STATUSES)
            .order_by('-created_at')
            .first())


def jobs_collecting_from(order):
    """Every job currently set to take `order`'s goods back off the customer.

    There are two, they were built years apart, and neither knows about the
    other: a replacement ticked 'collect the old item back' rides an `exchange`
    leg, and a return claim rides a `return_pickup` order. Both are legitimate;
    running both means two drivers turning up for one parcel. Whatever raises one
    shows the other rather than deciding for ops.

    Returns [{'kind', 'order', 'label'}], newest first.
    """
    if order is None:
        return []

    jobs = []

    def _live(candidate):
        # A draft counts: it has no task yet but it is going to get one.
        tasks = candidate.delivery_task.all()
        return (not tasks
                or any(t.dl_task_status not in _FINISHED_TASK_STATUSES for t in tasks))

    for repl in (order.replacements.filter(collect_back=True)
                 .exclude(order_status='cancelled')
                 .prefetch_related('delivery_task')):
        if _live(repl):
            jobs.append({
                'kind': 'exchange', 'order': repl,
                'label': (f"replacement {repl.order_number} is set to collect the "
                          f"old item at the door"),
            })

    for ret in (order.return_requests.filter(pickup_order__isnull=False)
                .select_related('pickup_order')
                .prefetch_related('pickup_order__delivery_task')):
        collection = ret.pickup_order
        if collection.order_status != 'cancelled' and _live(collection):
            jobs.append({
                'kind': 'collection', 'order': collection,
                'label': (f"collection {collection.order_number} is already raised "
                          f"for return {ret.return_number}"),
            })

    return jobs


def can_schedule_return_pickup(ret):
    """Whether a collection may be raised for `ret`. Returns (bool, reason).

    One gate for the console button, the template and the service itself, so a
    button that is shown always corresponds to a call that will succeed — the
    same contract can_replace() has.
    """
    if ret.pickup_order_id:
        # A cancelled collection is a trip that never happened — the goods are
        # still with the customer and the claim is still open, so staff must be
        # able to send another driver. Anything else leaves the claim stuck
        # forever on a trip nobody is making.
        if ret.pickup_order.order_status != 'cancelled':
            return False, (
                f"Collection {ret.pickup_order.order_number} is already raised for "
                f"this return.")

    if ret.status in RETURN_PICKUP_BLOCKED_STATUSES:
        return False, (
            f"This return is {ret.get_status_display().lower()} — there is "
            f"nothing left to collect.")

    # A sibling claim on the same order may already have a driver going. Two
    # collections for one parcel is the thing worth refusing outright; the
    # exchange-leg overlap is only warned about, because that one is a judgement
    # call ops sometimes need to make. A standalone claim has no order and so no
    # siblings — jobs_collecting_from(None) is empty and says so.
    for job in jobs_collecting_from(ret.order):
        if job['kind'] == 'collection':
            return False, f"A {job['label']}."

    # Both ends of the trip, read through the claim rather than off the order:
    # a standalone claim carries its own, and the message has to name the right
    # form for staff to know what to fix.
    where = 'This return' if ret.is_standalone else 'The original order'
    if ret.claim_pickup_location is None:
        return False, (
            f"{where} has no seller address, so there is nowhere to "
            f"take the goods back to.")

    if not (ret.claim_customer_phone or ret.claim_customer_address
            or ret.claim_zone):
        return False, f"{where} has no customer address to collect from."

    return True, ''


def _return_pickup_code(business, base):
    """`base` suffixed -RP1, -RP2, ... — same reasoning as _replacement_code: an
    opaque uuid tells a client nothing about which of their orders a collection
    belongs to.

    `base` is the outbound order's own code where there is one, and the return
    number where there is not (a standalone claim for goods we never delivered —
    that number is the only reference the client and we share).

    Counted off the codes themselves rather than off `pickup_order`, because
    re-scheduling a cancelled collection moves that one-to-one to the new order
    and the abandoned trip would stop being counted — handing the replacement the
    same -RP1 the cancelled one already has."""
    prefix = f"{base[:55]}-RP"
    n = Order.objects.filter(
        business=business, client_order_code__startswith=prefix).count() + 1
    return f"{prefix}{n}"


# Where the claim stands once the trip has started. Ordered, and only ever
# applied forwards: a driver re-opening a task must not drag the claim back to
# 'picked_up' after the seller has already signed for the goods.
RETURN_PICKUP_CLAIM_FLOW = ['pickup_scheduled', 'picked_up', 'received']

TASK_STATUS_TO_CLAIM = {
    'picked_up': 'picked_up',
    # The collection's 'delivered' means it reached the SELLER — which from the
    # claim's point of view is the goods being received back.
    'delivered': 'received',
}


def sync_return_pickup_claim(task):
    """Move the return request as its collection task moves.

    The driver's pickup and drop-off ARE the claim's progress — staff must not
    have to repeat them on the returns console. Same principle as
    delivery.signals.sync_return_leg_custody, and like it, never raises: a
    bookkeeping failure must not roll back the driver's status change.

    Returns the new claim status, or None when nothing moved.
    """
    from orders.models import ReturnRequest

    target = TASK_STATUS_TO_CLAIM.get(task.dl_task_status)
    if target is None or not task.order_id:
        return None

    ret = ReturnRequest.objects.filter(pickup_order_id=task.order_id).first()
    if ret is None:
        return None

    try:
        here = RETURN_PICKUP_CLAIM_FLOW.index(ret.status)
    except ValueError:
        # Somebody has moved the claim off this track by hand — rejected,
        # refunded, closed. That decision outranks the van.
        return None

    if RETURN_PICKUP_CLAIM_FLOW.index(target) <= here:
        return None

    ret.status = target
    ret.save(update_fields=['status', 'updated_at'])
    return target


def _line_spec(source, qty):
    """One collection line, from either kind of source.

    `source` is an OrderItem (what every caller passed before hand-added lines
    existed) or a ReturnItem. Reading through the ReturnItem's own properties
    keeps the "which kind of line is this" question in one place — the model —
    rather than at every site that builds a collection.
    """
    from orders.models import ReturnItem

    if isinstance(source, ReturnItem):
        return {
            'product': source.line_product,
            'unit_price': source.line_unit_price,
            'notes': source.line_notes,
            'quantity': int(qty),
        }
    return {
        'product': source.product,
        'unit_price': source.unit_price,
        'notes': source.notes,
        'quantity': int(qty),
    }


@transaction.atomic
def create_return_pickup_order(ret, *, items=None, charge=None, user=None,
                               notes='', publish=True):
    """Raise the order that collects `ret`'s goods from the customer.

    This is the reverse of every other order in the system: the customer fields
    are where the driver COLLECTS and `pickup_location` is where he DROPS OFF.
    Nothing here says so twice — `order_type='return_pickup'` is the single
    signal, and delivery/selectors.py resolves both ends of the leg from it.

    Staff-gated on purpose: the seller raises the claim, someone here decides a
    driver is worth sending. `publish=True` puts the task straight in the pool,
    because a staff member pressing the button IS the approval — unlike a
    replacement, which waits at 'to_review' while somebody finds the goods.

    `items` is an optional [(OrderItem, qty)] subset; the return's own lines by
    default. `charge` is what the seller pays for the trip, defaulting to what
    they paid for the outbound one — or, on a standalone claim for goods we
    never delivered, to the figure staff named when they raised it.

    Returns the new Order. Raises ValidationError when the return cannot be
    collected.
    """
    from orders.models import ReturnRequest

    # of=('self',) locks the claim row only. Both `order` and `pickup_location`
    # are nullable, so select_related emits LEFT OUTER JOINs and PostgreSQL
    # refuses a bare FOR UPDATE across them ("cannot be applied to the nullable
    # side of an outer join"). The claim is the row two staff can race on.
    ret = ReturnRequest.objects.select_for_update(of=('self',)).select_related(
        'order', 'business', 'pickup_location').get(pk=ret.pk)

    ok, why = can_schedule_return_pickup(ret)
    if not ok:
        raise ValidationError(why)

    # None on a standalone claim, and every read below goes through the claim's
    # own resolvers rather than this — `src` is only for the things that exist
    # solely on an outbound order: its number, its comment thread, its lines.
    src = ret.order
    charge = money._money(ret.claim_charge if charge is None else charge)
    if charge < ZERO:
        raise ValidationError("A collection charge cannot be negative.")

    # Normalised to plain specs before anything reads them: a claim line may be
    # a line off the order we delivered OR one added by hand with only a product
    # behind it (ReturnItem), and callers still pass raw [(OrderItem, qty)].
    if items is None:
        specs = [_line_spec(ri, ri.quantity_returned)
                 for ri in ret.return_items.select_related('order_item', 'product')]
    else:
        specs = [_line_spec(item, qty) for item, qty in items]
    specs = [sp for sp in specs if sp['quantity'] > 0]

    customer_name = ret.claim_customer_name or 'Customer'
    fields = dict(
        business=ret.business,
        # --- where the driver goes: the customer who is sending goods back ---
        customer_name=ret.claim_customer_name,
        customer_phone=ret.claim_customer_phone,
        customer_whatsapp=ret.claim_customer_whatsapp,
        customer_address=ret.claim_customer_address,
        dl_zone=ret.claim_zone,
        dl_street=ret.claim_street,
        dl_building=ret.claim_building,
        latitude=ret.claim_latitude,
        longitude=ret.claim_longitude,
        coords_accuracy=src.coords_accuracy if src is not None else None,
        # --- where he drops off: the seller's own counter ---
        # Must be set on the FIRST save, like a replacement's. The first-mile
        # hook reads it too, and bails on 'return_pickup' precisely because this
        # address is the destination here, not the origin.
        pickup_location=ret.claim_pickup_location,
        order_type='return_pickup',
        delivery_speed=src.delivery_speed if src is not None else 'standard',
        package_description=(ret.claim_package_description
                             or f"Return from {customer_name}")[:100],
        package_qty=sum(sp['quantity'] for sp in specs) or ret.claim_package_qty,
        package_weight_kg=src.package_weight_kg if src is not None else None,
        order_notes=(f"Return pickup for {src.order_number}" if src is not None
                     else f"Return pickup for {ret.return_number}")[:100],
        # --- money ---
        # No cash changes hands at the door. The refund this claim owes the
        # customer is cod_reversal_amount and it settles through
        # orders.money.refund_route — never as a COD, let alone a negative one.
        cod_amount=ZERO,
        cod_status_by_client='online_paid',
        cod_status_by_staff=None,
        dl_included=True,
        dl_amount=charge,
        order_status='to_review',
        task_status='new_order',
        verification_status='pending',
        platform='manual',
    )

    code_base = src.client_order_code if src is not None else ret.return_number
    try:
        with transaction.atomic():
            new = Order.objects.create(
                client_order_code=_return_pickup_code(ret.business, code_base),
                **fields)
    except IntegrityError:
        # Same collision case as a replacement's: a hand-edited code, or a
        # deleted collection, can make the -RP<n> suffix repeat.
        new = Order.objects.create(
            client_order_code=f"RP-{uuid.uuid4().hex[:8].upper()}", **fields)

    for sp in specs:
        OrderItem.objects.create(
            order=new, product=sp['product'], quantity=sp['quantity'],
            unit_price=sp['unit_price'], notes=sp['notes'])

    # Both threads carry the link, so either order tells the story on its own.
    # A standalone claim has only one thread — there is no outbound order to
    # write the other half onto, and the claim itself names what came back.
    if src is not None:
        raised_for = f"{src.order_number} ({ret.return_number})"
    else:
        ref = f" / ref {ret.external_reference}" if ret.external_reference else ''
        raised_for = f"{ret.return_number}{ref} — not delivered by EzzyDelivery"
    OrderComments.objects.create(
        order=new, name=getattr(user, 'username', 'system'), author=user,
        author_role='system', is_internal=True,
        body=(f"Return pickup for {raised_for} — "
              f"collect from {customer_name} and deliver to "
              f"{ret.claim_pickup_location.pickup_location_title}. "
              f"{notes}").strip()[:1000])
    if src is not None:
        OrderComments.objects.create(
            order=src, name=getattr(user, 'username', 'system'), author=user,
            author_role='system', is_internal=True,
            body=(f"Return pickup {new.order_number} raised for "
                  f"{ret.return_number}.").strip()[:1000])

    ret.pickup_order = new
    ret.status = 'pickup_scheduled'
    if user is not None and getattr(user, 'is_authenticated', False):
        from django.utils import timezone
        ret.reviewed_by = user
        ret.reviewed_at = timezone.now()
        ret.save(update_fields=['pickup_order', 'status', 'reviewed_by',
                                'reviewed_at', 'updated_at'])
    else:
        ret.save(update_fields=['pickup_order', 'status', 'updated_at'])

    if publish:
        # NOT apply_ready_and_publish: 'ready_to_pickup' reserves warehouse stock
        # and opens a first-mile leg at the seller, and neither applies to goods
        # that are still in the customer's hands. Going straight to 'publish'
        # creates the delivery task and nothing else.
        new.order_status = 'publish'
        new._status_changed_by = user
        new.save()
        # Published on creation like forward_to_client does it, into the
        # Unassigned list: staff or a Task Automation rule picks the driver.
        # update() skips the signal that runs the rules, so they are run here.
        from delivery.services.assignment import schedule_rules
        new.delivery_task.update(dl_task_publish=True, dl_task_status='pending')
        for task_pk in new.delivery_task.values_list('pk', flat=True):
            schedule_rules(task_pk)

    return new


# A replacement says why fresh goods went out; a claim says why goods are coming
# back. The two vocabularies were deliberately kept apart (see
# REPLACEMENT_REASON_CHOICES), so translate rather than pass the string through.
_REPLACEMENT_TO_RETURN_REASON = {
    'wrong_item': 'wrong_item',
    'damaged': 'damaged',
    'missing_items': 'not_as_described',
    'failed_delivery': 'undelivered',
}


def raise_collect_back_collection(replacement, *, user=None):
    """Raise the collection for a delivered collect-back replacement.

    The seller ticked "bring the original back" and the replacement has now
    reached the customer, so the original items need their own trip: collect at
    the customer's door, drop at whichever end their client's preference says.

    Deliberately a SECOND task rather than a flag on the outbound one. An
    exchange leg told the driver to carry goods away and then modelled nothing —
    no destination, no custody, no record that he was holding a seller's stock.

    The claim is raised against the ORIGINAL order, not the replacement: those
    are the goods coming back, and that is the order a seller looks at.

    Returns the collection Order, or None when there is nothing to raise.
    Never raises — a bookkeeping failure must not roll back a delivery.
    """
    source = replacement.replaces if replacement.replaces_id else None
    if source is None:
        return None

    try:
        with transaction.atomic():
            # Anything already coming for these goods wins; two drivers for one
            # parcel is exactly what this feature exists to prevent.
            if any(job['kind'] == 'collection' for job in jobs_collecting_from(source)):
                return None

            ret = open_return_for_order(source)
            if ret is None:
                ret = create_return_request(
                    source,
                    reason=_REPLACEMENT_TO_RETURN_REASON.get(
                        replacement.replacement_reason, 'other'),
                    reason_notes=(
                        f"Original items collected back on replacement "
                        f"{replacement.order_number}."),
                    status='approved', user=user)

            ok, _ = can_schedule_return_pickup(ret)
            if not ok:
                return None

            return create_return_pickup_order(
                ret, user=user, publish=True,
                notes=f"Raised automatically for replacement {replacement.order_number}.")
    except Exception:
        logger.exception(
            "Collect-back collection failed for replacement %s", replacement.pk)
        return None
