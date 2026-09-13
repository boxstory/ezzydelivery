# Purpose: Turn an accepted P2P quote into a real order, and resolve the EZP2P house business.
# Used by: p2p.views (booking + confirm), and the COD settlement guards in workforce.views
# Notes: The house business is a bookkeeping container, not a client — never owed money, never in a
#        payout screen. Order creation MUST leave order_status at 'to_review' and the pickup location
#        at 'pending'; those two facts are what keep an unconfirmed booking away from drivers.
#        A return trip is a SECOND order, the other way round, released and cancelled with the first.

import logging

from django.core.cache import cache

logger = logging.getLogger(__name__)

# Matches business/migrations/0031_seed_p2p_house_business.py. Resolved by code rather
# than by a pinned primary key so a database restore or a re-seed cannot silently point
# P2P orders at some other business.
HOUSE_BUSINESS_CODE = 'EZP2P'

_CACHE_KEY = 'p2p:house_business_id'
_CACHE_TTL = 3600


class HouseBusinessMissing(RuntimeError):
    """Raised when the seed migration has not run. Failing loudly beats writing
    a personal P2P order onto whichever business happens to sort first."""


def house_business():
    """The system Business that owns P2P orders from senders who have no business."""
    from business.models import Business

    try:
        return Business.objects.get(business_code=HOUSE_BUSINESS_CODE)
    except Business.DoesNotExist as exc:
        raise HouseBusinessMissing(
            f"No business with code {HOUSE_BUSINESS_CODE!r}. Run "
            "business/migrations/0031_seed_p2p_house_business.py before creating "
            "P2P orders."
        ) from exc


def house_business_id():
    """The house business's primary key, cached — this is called from list views."""
    cached = cache.get(_CACHE_KEY)
    if cached is not None:
        return cached
    from business.models import Business

    pk = (Business.objects
          .filter(business_code=HOUSE_BUSINESS_CODE)
          .values_list('business_id', flat=True)
          .first())
    if pk is not None:
        cache.set(_CACHE_KEY, pk, _CACHE_TTL)
    return pk


def is_house_business(business_or_id):
    """True for the P2P container business.

    Money guard, not a display detail. COD settlement is business-scoped
    (fleet.wallet_service.settle_cod_with_client) and bulk-marks every task in the
    payout as settled, so treating the house business as a payable client would hand
    every personal sender's cash to EzzyDelivery and close the rows in one click.
    """
    if business_or_id is None:
        return False
    pk = getattr(business_or_id, 'business_id', business_or_id)
    house_pk = house_business_id()
    return house_pk is not None and pk == house_pk


def new_token():
    """An unguessable booking token. The booking URL and the WhatsApp confirm link
    both hang off it, and both expose addresses and phone numbers."""
    import secrets
    return secrets.token_urlsafe(32)


def _speed_to_delivery_speed(speed):
    """P2P offers two speeds; Order carries three. 'scheduled' is the standard tier."""
    return 'express' if speed == 'express' else 'standard'


def destination_business(user):
    """Which business should own this order — the sender's own, or the house one.

    A business owner sending a personal parcel gets it on their normal orders list
    and their invoice, which is what they already expect. Everyone else, including
    an owner whose account is pending or suspended, goes to the house business: the
    write gate would block a non-active business anyway, and someone waiting on
    approval should still be able to send a parcel.

    Returns (business, is_personal).
    """
    from business.models import Business

    if user is not None and user.is_authenticated:
        own = (Business.objects
               .filter(user=user, business_status='active')
               .order_by('business_id').first())
        if own is not None:
            return own, False
    return house_business(), True


def create_pickup_location(booking, business):
    """The sender's address, as a real PickupLocation row.

    Created 'pending' on purpose. The first-mile gate refuses an inactive location,
    so no driver can see the job until the customer confirms — that refusal IS the
    no-premature-dispatch mechanism, not a separate check. Confirming flips it to
    active and the existing signal opens the leg.
    """
    from business.models import PickupLocation

    title = f"{booking.sender_name or 'P2P sender'} — {booking.from_label}"[:100]
    return PickupLocation.objects.create(
        business=business,
        pickup_location_title=title,
        locality=(booking.pickup_locality or booking.from_label)[:100],
        pickup_zone_no=booking.pickup_zone,
        pickup_street_no=booking.pickup_street,
        pickup_building_no=booking.pickup_building,
        pickup_lat=booking.from_lat,
        pickup_lon=booking.from_lng,
        pickup_status='pending',
        is_default=False,
        is_fulfilment_center=False,
        contact_name=(booking.sender_name or '')[:100],
        contact_phone=(booking.sender_phone or '')[:20],
        is_p2p=True,
    )


def sender_address_line(booking):
    """The pickup end written as one line a driver can navigate to.

    The drop end arrives from the form as free text; the pickup end only ever existed as
    a locality and three numbers, because the outbound order takes its address from the
    PickupLocation instead. The return leg delivers TO that end, so it needs the same
    thing spelled out in Order.customer_address like any other delivery.
    """
    bits = [booking.pickup_locality or booking.from_label]
    if booking.pickup_zone:
        bits.append(f"Zone {booking.pickup_zone}")
    if booking.pickup_street:
        bits.append(f"Street {booking.pickup_street}")
    if booking.pickup_building:
        bits.append(f"Building {booking.pickup_building}")
    return ', '.join(str(b) for b in bits if b)[:255]


def create_return_pickup_location(booking, data, business):
    """The receiver's address as a PickupLocation — the leg back collects there.

    Created 'pending' for the same reason the outbound one is: an unconfirmed booking
    must be invisible to drivers, and the first-mile gate refusing an inactive location
    IS that mechanism. confirm_booking flips both.
    """
    from business.models import PickupLocation

    title = f"{booking.receiver_name or 'P2P receiver'} — {booking.to_label}"[:100]
    return PickupLocation.objects.create(
        business=business,
        pickup_location_title=title,
        locality=(booking.to_label or '')[:100],
        pickup_zone_no=(data or {}).get('dl_zone'),
        pickup_street_no=(data or {}).get('dl_street'),
        pickup_building_no=(data or {}).get('dl_building'),
        pickup_lat=booking.to_lat,
        pickup_lon=booking.to_lng,
        pickup_status='pending',
        is_default=False,
        is_fulfilment_center=False,
        contact_name=(booking.receiver_name or '')[:100],
        contact_phone=(booking.receiver_phone or '')[:20],
        is_p2p=True,
    )


def create_return_order(booking, data, business, is_personal):
    """The leg back: collect at the delivery address, deliver to the pickup one.

    A real Order and not a flag on the outbound one. A driver has to be dispatched to
    it, somebody has to hand the item over and somebody has to receive it, and it has to
    be billed — every one of those is machinery the Order already has and a flag has
    none of. Written with exactly the same 'to_review' + 'pending' pair as the outbound
    order, so the two are released together and neither can go early.

    It carries no COD: the receiver's cash for the goods belongs to the outward journey,
    and collecting it twice is the one mistake this leg could make that costs money.
    """
    from decimal import Decimal
    from orders.models import Order

    pickup = create_return_pickup_location(booking, data, business)
    return Order.objects.create(
        business=business,
        client_order_code=f"P2P-{booking.token[:8].upper()}-R",
        p2p_customer=booking.customer if is_personal else None,
        pickup_location=pickup,
        order_type='pick_and_drop',
        delivery_speed=_speed_to_delivery_speed(booking.speed),
        order_status='to_review',
        task_status='new_order',
        # The sender is the receiver of this leg — the whole point of a return trip.
        customer_name=(booking.sender_name or 'P2P sender')[:100],
        customer_phone=(booking.sender_phone or '')[:100],
        customer_whatsapp=(booking.sender_phone or '')[:100],
        customer_address=sender_address_line(booking),
        dl_zone=booking.pickup_zone,
        dl_street=booking.pickup_street,
        dl_building=booking.pickup_building,
        latitude=booking.from_lat,
        longitude=booking.from_lng,
        coords_accuracy='by_customer',
        dl_included=True,
        dl_amount=booking.return_fee,
        cod_amount=Decimal('0'),
        cod_status_by_client='online_paid',
        cod_status_by_staff=None,
        package_description=(
            booking.return_description or f"Return from {booking.to_label}")[:255],
        package_qty=booking.box_count or 1,
        package_weight_kg=booking.weight_kg,
        order_notes=f"P2P return {booking.to_label} → {booking.from_label}"[:100],
        # The leg back happens on the visit that delivered the outward one, so it shares
        # its window rather than asking the customer for a third date.
        scheduled_delivery=booking.speed != 'express',
        scheduled_date=booking.scheduled_date,
        scheduled_time=booking.scheduled_time,
        platform='public_link',
        platform_id=str(booking.token)[:128],
    )


def create_order_from_booking(booking, data, business=None):
    """Write the order for a confirmed-details booking. One transaction.

    Everything here is deliberate:
      * order_status='to_review' — creating an order already at 'publish' produces NO
        delivery task, because that branch in orders/signals.py sits inside
        `if not created:`. Going live is apply_ready_and_publish()'s job.
      * pickup_location set on the FIRST save — the first-mile hook fires on create and
        bails with 'no_pickup_location' otherwise.
      * order_number, DlAddressUpdate, OrderBarcode and AddressVerification all come
        from signals. Do not write them here.

    `business` names the owner outright, for the staff desk taking a booking over the
    phone — there is no signed-in customer there to derive it from. Left out, the
    booking's own customer decides it exactly as before. Either way "personal" means
    the same thing: the order sits on the house business, which is what makes it cash
    to the driver rather than a line on a client's invoice.
    """
    from decimal import Decimal
    from django.db import transaction
    from orders.models import Order

    if business is None:
        business, is_personal = destination_business(booking.customer)
    else:
        is_personal = is_house_business(business)
    price = booking.agreed_price or Decimal('0')
    # What the customer agreed to covers both journeys on a return trip, so the outward
    # order must not carry the whole figure — it would be billed once here and again on
    # the leg back. The two halves add back up to `price` exactly (P2PBooking.return_fee).
    outbound_fee = booking.outbound_fee if booking.agreed_price is not None else price

    with transaction.atomic():
        pickup = create_pickup_location(booking, business)
        order = Order.objects.create(
            business=business,
            client_order_code=f"P2P-{booking.token[:8].upper()}",
            # Null for a business-routed order: it belongs in that client's console,
            # and setting this too would list the same order in both places.
            p2p_customer=booking.customer if is_personal else None,
            pickup_location=pickup,
            order_type='pick_and_drop',
            delivery_speed=_speed_to_delivery_speed(booking.speed),
            order_status='to_review',
            task_status='new_order',
            customer_name=data['customer_name'][:100],
            customer_phone=data['customer_phone'][:100],
            customer_whatsapp=(data.get('customer_whatsapp') or data['customer_phone'])[:100],
            customer_address=data['customer_address'][:255],
            dl_zone=data.get('dl_zone'),
            dl_street=data.get('dl_street'),
            dl_building=data.get('dl_building'),
            latitude=booking.to_lat,
            longitude=booking.to_lng,
            # A human placed this pin, which keeps the zone-mismatch check active.
            coords_accuracy='by_customer',
            dl_included=True,
            dl_amount=outbound_fee,
            # The receiver's cash only. The sender's delivery fee never folds in here.
            cod_amount=booking.cod_amount or Decimal('0'),
            cod_status_by_client='unpaid' if booking.cod_amount else 'online_paid',
            cod_status_by_staff='not_collected' if booking.cod_amount else None,
            package_description=(data.get('package_description') or '')[:255],
            package_qty=booking.box_count or 1,
            package_weight_kg=booking.weight_kg,
            order_notes=f"P2P {booking.from_label} → {booking.to_label}"[:100],
            scheduled_delivery=booking.speed != 'express',
            scheduled_date=booking.scheduled_date,
            scheduled_time=booking.scheduled_time,
            platform='public_link',
            platform_id=str(booking.token)[:128],
        )

        booking.order = order
        # Written before the leg back, which reads booking.return_fee off the agreed
        # price and needs the outward order to exist first for nothing else.
        if booking.return_trip:
            booking.return_order = create_return_order(
                booking, data, business, is_personal)
        # The whole job, both legs: this is the money the booking is worth, and the
        # per-order dl_amounts above are its two halves.
        booking.fee_amount = price
        # A personal booking is cash to the driver — at pickup or at the door, per
        # fee_payer. A business-routed one is billed on that client's existing charge
        # invoice instead, so no cash changes hands. The one exception is a receiver-pays
        # job: the receiver is not the client and has no invoice, so that stays cash.
        booking.fee_status = (
            'pending' if is_personal or booking.fee_payer == 'receiver' else 'billed')
        booking.status = 'awaiting_price' if booking.needs_quote else 'awaiting_customer'
        booking.token_expires_at = _token_expiry()
        booking.save(update_fields=[
            'order', 'return_order', 'fee_amount', 'fee_status', 'status',
            'token_expires_at', 'updated_at',
        ])

    return order


def _token_expiry():
    from datetime import timedelta
    from django.utils import timezone
    return timezone.now() + timedelta(days=7)


def confirm_booking(booking, actor=None):
    """The customer accepted the price. Release the job.

    Flips the pickup location to active and the order to ready_to_pickup in one
    transaction; the hook at orders/signals.py:303 then opens the first-mile leg on
    commit. Idempotent — a second click on the WhatsApp link changes nothing.

    A return trip releases BOTH orders. The customer agreed to one job of two journeys,
    and releasing only the outward one would strand the leg back at 'to_review' where no
    driver can ever see it.
    """
    from django.db import transaction
    from django.utils import timezone

    if booking.status == 'confirmed':
        return False

    with transaction.atomic():
        for order in (booking.order, booking.return_order):
            if order is None:
                continue
            pickup = order.pickup_location
            if pickup is not None and pickup.pickup_status != 'active':
                pickup.pickup_status = 'active'
                pickup.save(update_fields=['pickup_status'])
            if order.order_status == 'to_review':
                order.order_status = 'ready_to_pickup'
                order._status_changed_by = actor
                order.save()

        booking.status = 'confirmed'
        booking.customer_agreed_at = timezone.now()
        booking.save(update_fields=['status', 'customer_agreed_at', 'updated_at'])
    return True


def apply_staff_price(booking, amount, staff_user):
    """Ops set the price on a quote-only booking. Moves it to awaiting_customer."""
    from django.utils import timezone

    booking.staff_price = amount
    booking.priced_by = staff_user
    booking.priced_at = timezone.now()
    booking.fee_amount = amount
    booking.status = 'awaiting_customer'
    booking.token_expires_at = _token_expiry()
    booking.save(update_fields=[
        'staff_price', 'priced_by', 'priced_at', 'fee_amount', 'status',
        'token_expires_at', 'updated_at',
    ])

    # The staff figure is the whole job. On a return trip it splits across the two legs
    # the same way the card's own price does, so the orders still add up to what was
    # quoted rather than charging the agreed total twice.
    if booking.order is not None:
        booking.order.dl_amount = booking.outbound_fee
        booking.order.save(update_fields=['dl_amount'])
    if booking.return_order is not None:
        booking.return_order.dl_amount = booking.return_fee
        booking.return_order.save(update_fields=['dl_amount'])
    return booking


def set_booking_lines(booking, load):
    """Replace a booking's per-size lines with `load` ({size: count}).

    Replaced rather than merged: an edit that drops a size has to drop the row, and a
    reprice that ends up single-size has to leave nothing behind that would still read as
    mixed. An empty map clears them, which is exactly what a single-size job is — the
    scalar size/box_count pair on the booking already says everything about it.
    """
    from p2p.models import P2PBookingLine

    booking.lines.all().delete()
    P2PBookingLine.objects.bulk_create([
        P2PBookingLine(booking=booking, size=size, count=int(count))
        for size, count in (load or {}).items() if count and int(count) > 0
    ])


def sync_return_order(booking, data):
    """Bring the leg back into line with a booking the customer just edited.

    The edit page renders the same tick as the booking form, so all three transitions
    have to be honoured: added, dropped, or still there and changed. Only ever reached
    while the outward order is at 'to_review', which is exactly when no driver has seen
    either leg — see p2p.views.delivery_edit for why that one fact is the whole gate.

    A dropped leg is CANCELLED, never deleted: the order already has a number, a barcode
    and a history, and destroying that row would take the audit trail of what the
    customer originally asked for with it. Ticking the box again writes a fresh order,
    and the cancelled one stays behind as the record that it was once wanted.
    """
    from django.db import transaction

    outbound = booking.order
    if outbound is None:
        return None

    live = booking.return_order
    if live is not None and live.order_status == 'cancelled':
        live = None

    with transaction.atomic():
        if not booking.return_trip:
            if live is not None:
                live.order_status = 'cancelled'
                live.save(update_fields=['order_status'])
                pickup = live.pickup_location
                if pickup is not None and pickup.is_p2p:
                    pickup.pickup_status = 'inactive'
                    pickup.save(update_fields=['pickup_status'])
                booking.return_order = None
                booking.save(update_fields=['return_order', 'updated_at'])
            return None

        if live is None:
            booking.return_order = create_return_order(
                booking, data, outbound.business, is_house_business(outbound.business))
            booking.save(update_fields=['return_order', 'updated_at'])
            return booking.return_order

        # Still wanted, and both ends may have moved. Everything the form can change is
        # rewritten from the booking rather than patched field by field, so a leg back
        # cannot keep an address the outward leg no longer has.
        live.customer_name = (booking.sender_name or 'P2P sender')[:100]
        live.customer_phone = (booking.sender_phone or '')[:100]
        live.customer_whatsapp = (booking.sender_phone or '')[:100]
        live.customer_address = sender_address_line(booking)
        live.dl_zone = booking.pickup_zone
        live.dl_street = booking.pickup_street
        live.dl_building = booking.pickup_building
        live.dl_amount = booking.return_fee
        live.package_description = (
            booking.return_description or f"Return from {booking.to_label}")[:255]
        live.package_qty = booking.box_count or 1
        live.package_weight_kg = booking.weight_kg
        live.delivery_speed = _speed_to_delivery_speed(booking.speed)
        live.scheduled_delivery = booking.speed != 'express'
        live.scheduled_date = booking.scheduled_date
        live.scheduled_time = booking.scheduled_time
        live.save()

        # The leg back collects at the drop address, so a moved drop moves this pickup.
        # Edited in place for the same reason the outward one is: swapping the FK fires
        # the "pickup moved" hook and relocates a leg that does not exist yet.
        pickup = live.pickup_location
        if pickup is not None and pickup.is_p2p:
            pickup.contact_name = (booking.receiver_name or '')[:100]
            pickup.contact_phone = (booking.receiver_phone or '')[:20]
            pickup.pickup_zone_no = (data or {}).get('dl_zone')
            pickup.pickup_street_no = (data or {}).get('dl_street')
            pickup.pickup_building_no = (data or {}).get('dl_building')
            pickup.save(update_fields=[
                'contact_name', 'contact_phone', 'pickup_zone_no',
                'pickup_street_no', 'pickup_building_no'])
        return live


def booking_for(order):
    """The P2PBooking behind an order, whichever leg of it this is.

    A return trip writes two orders off one booking: the outward one is reached through
    `p2p_booking` and the leg back through `p2p_return_booking`. Every screen that wants
    the booking wants it for either, so nowhere has to know which of the two it holds.
    """
    return (getattr(order, 'p2p_booking', None)
            or getattr(order, 'p2p_return_booking', None))


def is_return_leg(order):
    """True when this order is the leg back rather than the outward journey."""
    return getattr(order, 'p2p_return_booking', None) is not None
