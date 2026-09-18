# Purpose: Build a replacement order — fresh goods to the same customer, settled at the door.
# Used by: workforce.views.create_replacement_order (staff) and, later, the client-side view.
# Notes: The settlement figure is TYPED BY STAFF, never derived from item prices. A refund is
#        never written as a negative cod_amount — nothing downstream handles that; it is routed
#        through orders.money.refund_route instead.

import uuid
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from orders import money
from orders.models import (
    MAX_REPLACEMENT_DEPTH, Order, OrderComments, OrderItem,
)

ZERO = Decimal('0.00')

# 'fulfilled' was dropped from ORDER_STATUS_BY_CLIENT without a data migration
# (see orders/migrations/0001_initial.py); legacy rows still carry it and other
# call sites still filter on it, so it has to stay eligible here too.
ELIGIBLE_ORDER_STATUSES = ('delivered', 'fulfilled')
ELIGIBLE_TASK_STATUSES = ('failed', 'partial_delivery', 'non_reachable')


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
