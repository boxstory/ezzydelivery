# Purpose: The P2P booking flow and the personal sender's console.
# Used by: p2p/urls.py — /p2p/book/…, /p2p/a/<token>/, /p2p/my-deliveries/…
# Notes: The price is never a POST field; every step recomputes it from the rate card. The console
#        is @login_required ONLY — a sender has no Business, so any business decorator locks them out.

import logging
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST
from django_ratelimit.decorators import ratelimit

from core import models as core_models
from core import signup_origin
from p2p import services
from p2p.forms import BookingDetailsForm, OtpForm, WhatsAppNumberForm
from p2p.models import P2PBooking, P2P_MAX_BOXES, P2P_SIZE_CHOICES
from p2p.pricing import LADDER_VERSION, in_qatar, primary_size, quote

logger = logging.getLogger('p2p')

PUBLIC_RATE = '10/h'
USER_RATE = '15/h'


# ---------------------------------------------------------------------------
# Account: profile + WhatsApp verification
# ---------------------------------------------------------------------------

def ensure_customer_profile(request):
    """Give a fresh Google signup a Profile, stamped with where they came from.

    Nothing else will: core/signals.py has a user_signed_up receiver but the module
    is deliberately never imported (see core/apps.py), so profiles are created in
    views. Without this the session's 'pricing_inquiry' attribution is discarded and
    main_dashboard dead-ends them on profile_add.
    """
    profile = core_models.Profile.objects.filter(user=request.user).first()
    if profile is None:
        profile = signup_origin.apply_to(
            core_models.Profile(user=request.user), request)
        profile.username = request.user.username
        profile.first_name = request.user.first_name or ''
        profile.last_name = request.user.last_name or ''
        profile.email = request.user.email or ''
        profile.is_customer = True
        profile.save()
        logger.info('Created P2P customer profile for user %s (source=%s)',
                    request.user.id, profile.signup_source)
    elif not profile.is_customer:
        # An existing business owner or team member booking a personal parcel keeps
        # every role they already hold; is_customer is additive.
        profile.is_customer = True
        profile.save(update_fields=['is_customer'])
    return profile


def verified_whatsapp(profile):
    """The number that passed the OTP step, or '' if none has.

    The only number the customer is allowed to be reached on for a booking: it is
    where the confirm link goes, so an unverified one would release jobs to whoever
    answers a phone nobody proved they hold.
    """
    if profile is not None and profile.whatsapp_verified:
        return profile.whatsapp or ''
    return ''


@login_required
def verify_number(request):
    """Collect and prove the sender's WhatsApp number.

    A Google signup yields an email and a name, never a phone number, so the number
    is asked for here. It is written to the Profile only once the code checks out —
    the order confirmation link goes to whatever is on file, so an unverified number
    on record would defeat the whole step.
    """
    from core.whatsapp_utils import create_verification, mask_phone

    profile = ensure_customer_profile(request)
    next_url = request.GET.get('next') or '/p2p/my-deliveries/'

    if profile.whatsapp_verified:
        return redirect(next_url)

    pending = (core_models.WhatsAppVerification.objects
               .filter(user=request.user, verification_type='account_verify', is_verified=False)
               .order_by('-created_at').first())

    number_form = WhatsAppNumberForm()
    otp_form = OtpForm()

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'send':
            number_form = WhatsAppNumberForm(request.POST)
            if number_form.is_valid():
                phone = number_form.cleaned_data['whatsapp']
                result = create_verification(
                    user=request.user, phone_number=phone,
                    verification_type='account_verify')
                if result.get('success'):
                    messages.success(
                        request, f'Code sent to {mask_phone(phone)} on WhatsApp.')
                    return redirect(f"{request.path}?next={next_url}")
                messages.error(request, result.get('error') or 'Could not send the code.')

        elif action == 'verify':
            otp_form = OtpForm(request.POST)
            if otp_form.is_valid():
                ok, msg = _check_code(request.user, otp_form.cleaned_data['code'])
                if ok:
                    verification = (core_models.WhatsAppVerification.objects
                                    .filter(user=request.user,
                                            verification_type='account_verify',
                                            is_verified=True)
                                    .order_by('-created_at').first())
                    # Only now is the number good enough to keep.
                    if verification:
                        profile.whatsapp = verification.phone_number
                        if not profile.phone:
                            profile.phone = verification.phone_number
                    profile.whatsapp_verified = True
                    profile.whatsapp_verified_at = timezone.now()
                    profile.save(update_fields=[
                        'whatsapp', 'phone', 'whatsapp_verified', 'whatsapp_verified_at'])
                    messages.success(request, 'Number verified.')
                    return redirect(next_url)
                messages.error(request, msg)

    return render(request, 'p2p/verify_number.html', {
        'number_form': number_form,
        'otp_form': otp_form,
        'pending': pending,
        'masked': mask_phone(pending.phone_number) if pending else '',
        'next_url': next_url,
    })


def _check_code(user, code):
    """Mirrors fleet.device_service.verify_device_code — same attempt/expiry rules."""
    verification = (core_models.WhatsAppVerification.objects
                    .filter(user=user, verification_type='account_verify', is_verified=False)
                    .order_by('-created_at').first())
    if not verification:
        return False, 'No code was requested. Send one first.'
    if verification.is_expired():
        return False, 'That code has expired. Send a new one.'
    if not verification.can_attempt():
        return False, 'Too many wrong attempts. Send a new code.'

    verification.attempts += 1
    if verification.verification_code != code:
        verification.save(update_fields=['attempts'])
        left = max(0, verification.max_attempts - verification.attempts)
        return False, f'Wrong code. {left} attempt(s) left.'

    verification.is_verified = True
    verification.save(update_fields=['attempts', 'is_verified'])
    return True, 'Verified.'


# ---------------------------------------------------------------------------
# Booking
# ---------------------------------------------------------------------------

@require_POST
@ratelimit(key='ip', rate=PUBLIC_RATE, method='POST', block=False)
def book_start(request):
    """The customer accepted the shown price. Create the booking, then sign them in.

    The posted price is ignored entirely — there isn't even a field for it. Everything
    is recomputed from the rate card, so a tampered page cannot buy a cheap delivery.
    """
    if getattr(request, 'limited', False):
        messages.error(request, 'Too many attempts. Please try again later.')
        return redirect('webpages:p2p_pricing')

    try:
        from_lat = Decimal(request.POST['from_lat'])
        from_lng = Decimal(request.POST['from_lng'])
        to_lat = Decimal(request.POST['to_lat'])
        to_lng = Decimal(request.POST['to_lng'])
    except (KeyError, ValueError, TypeError):
        messages.error(request, 'Please choose both a pickup and a delivery location.')
        return redirect('webpages:p2p_pricing')

    if not in_qatar(from_lat, from_lng) or not in_qatar(to_lat, to_lng):
        messages.error(request, 'Both locations must be inside Qatar.')
        return redirect('webpages:p2p_pricing')

    size = (request.POST.get('size') or '').strip()
    vehicle = (request.POST.get('vehicle') or '').strip()
    speed = 'express' if request.POST.get('speed') != 'standard' else 'standard'
    try:
        boxes = max(1, min(P2P_MAX_BOXES, int(request.POST.get('box_count') or 1)))
    except (TypeError, ValueError):
        boxes = 1

    # A job may be several sizes at once, posted as load_<size>=<count>. When none are
    # given it is a single-size job and the size/boxes pair still says everything.
    load = {}
    for slug, _label in P2P_SIZE_CHOICES:
        try:
            n = int(request.POST.get(f'load_{slug}') or 0)
        except (TypeError, ValueError):
            n = 0
        if n > 0:
            load[slug] = min(n, P2P_MAX_BOXES)
    if sum(load.values()) > P2P_MAX_BOXES:
        load = {}
    if load:
        size = primary_size(load)
        boxes = sum(load.values())

    # The calculator's own tick. A truthy value is all it can say — the price of the
    # leg back is worked out here like every other number in this flow.
    return_trip = (request.POST.get('return_trip') or '').lower() in ('1', 'on', 'true', 'yes')

    result = quote((from_lat, from_lng), (to_lat, to_lng),
                   size=size, vehicle=vehicle, speed=speed, boxes=boxes,
                   load=load or None, return_trip=return_trip)

    booking = P2PBooking.objects.create(
        token=services.new_token(),
        status='draft',
        customer=request.user if request.user.is_authenticated else None,
        from_label=(request.POST.get('from_label') or 'Pickup')[:150],
        to_label=(request.POST.get('to_label') or 'Delivery')[:150],
        from_lat=from_lat, from_lng=from_lng, to_lat=to_lat, to_lng=to_lng,
        distance_km=result['distance_km'],
        category=(request.POST.get('category') or '')[:80],
        size=size, vehicle=vehicle, speed=speed, box_count=boxes,
        return_trip=return_trip,
        quoted_price=result['price'],
        needs_quote=result['needs_quote'],
        rate_band=result['band'],
        ladder_version=LADDER_VERSION,
        source_ip=request.META.get('REMOTE_ADDR'),
        user_agent=(request.META.get('HTTP_USER_AGENT') or '')[:255],
    )
    services.set_booking_lines(booking, load)
    # Belt to the URL's braces: the token is in the path so it survives an allauth
    # session rotation, and in the session so a customer who lands back on the
    # calculator can be picked up again.
    request.session['p2p_draft_token'] = booking.token
    return redirect('p2p:book', token=booking.token)


def load_initial(booking, box_count=None):
    """The per-size counters, prefilled — {'count_s': 2, 'count_m': 1}.

    From the booking's own lines when it has them. A job booked as a single size has only
    the scalar size/box_count pair, and since the counters became the ONLY place a count
    is entered (there is no separate total field on the form any more), that pair has to
    be unpacked into them — otherwise a three-box job re-saved from the edit page would
    silently come back as one.
    """
    if booking is None:
        return {}
    lines = {f'count_{line.size}': line.count for line in booking.lines.all()}
    if lines:
        return lines
    if booking.size:
        return {f'count_{booking.size}': box_count or booking.box_count or 1}
    return {}


@login_required
def book(request, token):
    """Collect the details, then write the order."""
    booking = get_object_or_404(P2PBooking, token=token)

    # Claiming: first authenticated visitor owns it. 404 rather than 403 for anyone
    # else — the booking carries addresses and phone numbers, so do not confirm the
    # token even exists.
    if booking.customer_id is None:
        booking.customer = request.user
        booking.status = 'details'
        booking.save(update_fields=['customer', 'status', 'updated_at'])
    elif booking.customer_id != request.user.id:
        raise Http404

    if booking.order_id:
        return redirect('p2p:booking_confirmation', token=booking.token)

    profile = ensure_customer_profile(request)
    if not profile.whatsapp_verified:
        return redirect(f"/p2p/verify-number/?next=/p2p/book/{booking.token}/")

    # The booker is whoever is signed in, but not necessarily the sender. The form
    # opens on the commonest case — they are sending — and the role toggle moves this
    # prefill to the other end of the job, so nothing here presumes which one it is.
    me_name = (f"{profile.first_name or ''} {profile.last_name or ''}").strip()
    # Their verified number, not profile.phone: this is the one field on the form they
    # are not allowed to change, so it must be the proven one.
    me_phone = verified_whatsapp(profile)
    role = booking.booker_role or 'sender'
    initial = {
        'booker_role': role,
        'sender_name': me_name if role == 'sender' else booking.sender_name,
        'sender_phone': me_phone if role == 'sender' else booking.sender_phone,
        'customer_name': me_name if role == 'receiver' else '',
        'customer_phone': me_phone if role == 'receiver' else '',
        'customer_whatsapp': me_phone if role == 'receiver' else '',
        # Whoever booked expects to be the one paying; they can hand it to the other
        # end on the same form.
        'fee_payer': role,
        'size': booking.size or 's',
        'vehicle': booking.vehicle,
        'box_count': booking.box_count or 1,
        # The mix, so a job booked as two sizes is still two sizes on the details form —
        # and a single-size one arrives as a count against that size, because these
        # counters are now the only place the customer can state one.
        **load_initial(booking),
        'speed': booking.speed,
        # Carried from the calculator, so a customer who asked for the leg back there
        # does not have to remember to ask for it again here.
        'return_trip': booking.return_trip,
        'return_description': booking.return_description,
    }

    if request.method == 'POST':
        form = BookingDetailsForm(request.POST, booking=booking,
                                  verified_whatsapp=me_phone)
        if form.is_valid():
            data = form.cleaned_data
            # Re-price from the submitted inputs, not the ones accepted earlier: the
            # customer may have changed size, weight, boxes or speed on this form, and
            # the rate card may have moved since.
            repriced = quote(
                (booking.from_lat, booking.from_lng), (booking.to_lat, booking.to_lng),
                size=data['size'], vehicle=data.get('vehicle') or '',
                speed=data['speed'], boxes=data['box_count'],
                weight_kg=data.get('weight_kg'), load=data.get('load') or None,
                return_trip=data.get('return_trip') or False,
            )
            booking.size = data['size']
            booking.vehicle = data.get('vehicle') or ''
            booking.box_count = data['box_count']
            services.set_booking_lines(booking, data.get('load') or {})
            booking.weight_kg = data.get('weight_kg')
            booking.speed = data['speed']
            # Set before create_order_from_booking, which reads it to decide whether to
            # write the second order at all.
            booking.return_trip = bool(data.get('return_trip'))
            booking.return_description = data.get('return_description') or ''
            booking.pickup_date = data.get('pickup_date')
            booking.pickup_time = data.get('pickup_time')
            booking.scheduled_date = data.get('scheduled_date')
            booking.scheduled_time = data.get('scheduled_time')
            booking.booker_role = data['booker_role']
            # Stamped from the Profile, never from the POST. A third-party booker is on
            # neither leg, so this is the only place their number exists on the booking.
            booking.booker_phone = me_phone
            booking.sender_name = data['sender_name']
            booking.sender_phone = data['sender_phone']
            booking.receiver_name = data['customer_name']
            booking.receiver_phone = data.get('customer_whatsapp') or data['customer_phone']
            booking.pickup_zone = data.get('pickup_zone')
            booking.pickup_street = data.get('pickup_street')
            booking.pickup_building = data.get('pickup_building')
            booking.pickup_notes = data.get('pickup_notes') or ''
            booking.cod_amount = data.get('cod_amount') or Decimal('0')
            booking.fee_payer = data['fee_payer']
            booking.quoted_price = repriced['price']
            booking.needs_quote = repriced['needs_quote']
            booking.rate_band = repriced['band']
            booking.distance_km = repriced['distance_km']
            booking.save()

            order = services.create_order_from_booking(booking, data)
            from p2p.notifications import send_booking_confirmation
            send_booking_confirmation(booking)
            logger.info('P2P booking %s created order %s', booking.pk, order.order_number)
            return redirect('p2p:booking_confirmation', token=booking.token)
    else:
        form = BookingDetailsForm(initial=initial, booking=booking,
                                  verified_whatsapp=me_phone)

    return render(request, 'p2p/book.html', {
        'booking': booking, 'form': form,
        'me_name': me_name, 'me_phone': me_phone,
    })


@login_required
def booking_confirmation(request, token):
    booking = get_object_or_404(P2PBooking, token=token)
    if booking.customer_id != request.user.id:
        raise Http404
    return render(request, 'p2p/booking_confirmation.html', {
        'booking': booking, 'order': booking.order,
    })


# ---------------------------------------------------------------------------
# The confirm link from WhatsApp
# ---------------------------------------------------------------------------

def accept_price(request, token):
    """Public, no login. GET shows what is being agreed; POST releases the job.

    A GET must never mutate: WhatsApp fetches link previews, and a mutating GET would
    confirm orders nobody clicked.
    """
    booking = get_object_or_404(P2PBooking, token=token)

    if booking.token_expires_at and timezone.now() > booking.token_expires_at:
        return render(request, 'p2p/link_expired.html', {'booking': booking}, status=410)

    if request.method == 'POST':
        changed = services.confirm_booking(booking)
        if changed:
            logger.info('P2P booking %s confirmed by customer', booking.pk)
        return render(request, 'p2p/accept_price.html', {
            'booking': booking, 'order': booking.order, 'confirmed': True,
        })

    return render(request, 'p2p/accept_price.html', {
        'booking': booking,
        'order': booking.order,
        'confirmed': booking.status == 'confirmed',
    })


# ---------------------------------------------------------------------------
# The sender's console
# ---------------------------------------------------------------------------

# Plain English for the sender. Raw codes like 'dl_task_listed' mean nothing to them.
def customer_status(order, booking):
    if order is None:
        return 'Awaiting price' if booking.needs_quote else 'Draft'
    if order.order_status == 'cancelled':
        return 'Cancelled'
    task = order.delivery_task.exclude(dl_task_status='cancelled').order_by('-id').first()
    if task is not None:
        if task.dl_task_status == 'delivered':
            return 'Delivered'
        if task.dl_task_status in ('out_for_delivery', 'in_transit', 'start_ride'):
            return 'Out for delivery'
    pickup = getattr(order, 'pickup_task', None)
    if pickup is not None:
        return {
            'pending': 'Finding a driver',
            'accepted': 'Driver assigned',
            'in_progress': 'Driver on the way',
            'arrived': 'Driver arriving',
            'collected': 'Picked up',
            'handed_off': 'Picked up',
        }.get(pickup.status, 'Booked')
    if booking is not None and booking.status == 'awaiting_price':
        return 'Awaiting price'
    if order.order_status == 'to_review':
        return 'Awaiting your confirmation'
    return 'Booked'


@login_required
def my_deliveries(request):
    """The personal sender's list.

    @login_required ONLY — no business or verification decorator. A sender has no
    Business, so business_permission_required / business_active_required would lock
    them out of their own deliveries. Scoped on p2p_customer, never on the role flag,
    so a customer who later registers a business keeps their history.
    """
    from orders.models import Order

    orders = (Order.objects
              .filter(p2p_customer=request.user)
              .select_related('pickup_location', 'p2p_booking', 'p2p_return_booking')
              .prefetch_related('delivery_task')
              .order_by('-created_at'))
    rows = []
    for order in orders:
        # A return trip is two orders off one booking, and the customer is owed a line
        # for each — they are two journeys, each with its own driver and its own status.
        booking = services.booking_for(order)
        rows.append({'order': order, 'booking': booking,
                     'is_return': services.is_return_leg(order),
                     'status': customer_status(order, booking)})

    # Quote requests that never became an order still deserve to be visible.
    pending = (P2PBooking.objects
               .filter(customer=request.user, order__isnull=True)
               .exclude(status__in=['draft', 'abandoned', 'cancelled'])
               .order_by('-created_at'))
    return render(request, 'p2p/my_deliveries.html', {'rows': rows, 'pending': pending})


@login_required
def delivery_detail(request, order_number):
    from orders.models import Order, OrderComments

    order = get_object_or_404(
        Order.objects.select_related('pickup_location', 'p2p_booking',
                                     'p2p_return_booking'),
        order_number=order_number, p2p_customer=request.user)
    booking = services.booking_for(order)
    is_return = services.is_return_leg(order)
    task = order.delivery_task.exclude(dl_task_status='cancelled').order_by('-id').first()

    # Only the customer-visible half of the thread. is_internal defaults True, so a
    # write site that forgets to set it stays hidden rather than leaking.
    comments = (OrderComments.objects
                .filter(order=order, is_internal=False)
                .select_related('author').order_by('created_at'))

    history = order.status_history.filter(
        field_name__in=['order_status', 'pickup_status']).order_by('created_at')

    # One form drives both legs, so Edit on the leg back opens the outward order's page
    # — editing them apart is how the two ends of one job come to disagree.
    edit_order = booking.order if (is_return and booking and booking.order) else order

    return render(request, 'p2p/delivery_detail.html', {
        'order': order, 'booking': booking, 'task': task,
        'comments': comments, 'history': history,
        'status': customer_status(order, booking),
        'is_return': is_return,
        'edit_order_number': edit_order.order_number,
        'can_edit': edit_order.order_status == 'to_review',
    })


@login_required
def delivery_edit(request, order_number):
    """Change an order before anyone has been sent to collect it.

    Allowed only at 'to_review', which is strictly before ready_to_pickup — and it
    coincides exactly with the pickup location still being 'pending', so no driver can
    have seen the job. The gate is that one fact, not a second independent check.
    """
    from orders.models import Order

    order = get_object_or_404(
        Order.objects.select_related('p2p_booking', 'p2p_return_booking'),
        order_number=order_number, p2p_customer=request.user)

    # The leg back has no form of its own: it is the outward journey reversed, and every
    # answer on this page describes both. Send them to the one page that owns the pair.
    if services.is_return_leg(order):
        outbound = order.p2p_return_booking.order
        if outbound is not None:
            return redirect('p2p:delivery_edit', order_number=outbound.order_number)

    me_phone = verified_whatsapp(
        core_models.Profile.objects.filter(user=request.user).first())
    if order.order_status != 'to_review':
        messages.error(request, 'This delivery is already being collected and can no longer be changed.')
        return redirect('p2p:delivery_detail', order_number=order.order_number)

    booking = getattr(order, 'p2p_booking', None)
    initial = {
        'booker_role': booking.booker_role if booking else 'sender',
        'fee_payer': booking.fee_payer if booking else 'sender',
        'sender_name': booking.sender_name if booking else '',
        'sender_phone': booking.sender_phone if booking else '',
        'pickup_zone': booking.pickup_zone if booking else None,
        'pickup_street': booking.pickup_street if booking else None,
        'pickup_building': booking.pickup_building if booking else None,
        'pickup_notes': booking.pickup_notes if booking else '',
        'customer_name': order.customer_name,
        'customer_phone': order.customer_phone,
        'customer_whatsapp': order.customer_whatsapp,
        'customer_address': order.customer_address,
        'dl_zone': order.dl_zone, 'dl_street': order.dl_street, 'dl_building': order.dl_building,
        'size': booking.size if booking else 's',
        'vehicle': booking.vehicle if booking else '',
        'box_count': order.package_qty or 1,
        # The count as it stands, per size. Off the order's own quantity when the booking
        # predates mixed loads, so re-saving this form cannot quietly shrink the job.
        **load_initial(booking, box_count=order.package_qty),
        'weight_kg': order.package_weight_kg,
        'package_description': order.package_description,
        'cod_amount': order.cod_amount,
        'speed': booking.speed if booking else 'express',
        # The pickup window only ever lived on the booking; the drop one is read off
        # the Order, which is what ops and the driver actually work from.
        'pickup_date': booking.pickup_date if booking else None,
        'pickup_time': booking.pickup_time if booking else None,
        'scheduled_date': order.scheduled_date, 'scheduled_time': order.scheduled_time,
        'return_trip': booking.return_trip if booking else False,
        'return_description': booking.return_description if booking else '',
    }

    if request.method == 'POST':
        form = BookingDetailsForm(request.POST, booking=booking,
                                  verified_whatsapp=me_phone)
        if form.is_valid():
            data = form.cleaned_data
            if booking is not None:
                repriced = quote(
                    (booking.from_lat, booking.from_lng), (booking.to_lat, booking.to_lng),
                    size=data['size'], vehicle=data.get('vehicle') or '',
                    speed=data['speed'], boxes=data['box_count'],
                    load=data.get('load') or None,
                    weight_kg=data.get('weight_kg'),
                    return_trip=data.get('return_trip') or False)
                booking.size = data['size']
                services.set_booking_lines(booking, data.get('load') or {})
                booking.vehicle = data.get('vehicle') or ''
                booking.box_count = data['box_count']
                booking.weight_kg = data.get('weight_kg')
                booking.speed = data['speed']
                booking.pickup_date = data.get('pickup_date')
                booking.pickup_time = data.get('pickup_time')
                booking.scheduled_date = data.get('scheduled_date')
                booking.scheduled_time = data.get('scheduled_time')
                booking.booker_role = data['booker_role']
                booking.booker_phone = me_phone or booking.booker_phone
                booking.sender_name = data['sender_name']
                booking.sender_phone = data['sender_phone']
                booking.receiver_name = data['customer_name']
                booking.receiver_phone = (
                    data.get('customer_whatsapp') or data['customer_phone'])
                booking.fee_payer = data['fee_payer']
                booking.pickup_zone = data.get('pickup_zone')
                booking.pickup_street = data.get('pickup_street')
                booking.pickup_building = data.get('pickup_building')
                booking.pickup_notes = data.get('pickup_notes') or ''
                booking.cod_amount = data.get('cod_amount') or Decimal('0')
                booking.return_trip = bool(data.get('return_trip'))
                booking.return_description = data.get('return_description') or ''
                booking.quoted_price = repriced['price']
                booking.needs_quote = repriced['needs_quote']
                booking.rate_band = repriced['band']
                booking.save()
                # Half of the agreed figure belongs to the leg back on a return trip,
                # and all of it to this order on a one-way one.
                order.dl_amount = booking.outbound_fee or Decimal('0')

            order.customer_name = data['customer_name']
            order.customer_phone = data['customer_phone']
            order.customer_whatsapp = data.get('customer_whatsapp') or data['customer_phone']
            order.customer_address = data['customer_address']
            order.dl_zone = data.get('dl_zone')
            order.dl_street = data.get('dl_street')
            order.dl_building = data.get('dl_building')
            order.package_qty = data['box_count']
            order.package_weight_kg = data.get('weight_kg')
            order.package_description = data.get('package_description') or ''
            order.cod_amount = data.get('cod_amount') or Decimal('0')
            # The delivery window is the customer's to change until the parcel is
            # collected; without this the edit form showed it, took the change and
            # then dropped it on the floor.
            order.scheduled_delivery = data['speed'] != 'express'
            order.scheduled_date = data.get('scheduled_date')
            order.scheduled_time = data.get('scheduled_time')
            order.save()

            # Edit the existing pickup row in place. Swapping the FK would fire the
            # "pickup moved" hook and relocate a leg that should not exist yet.
            pickup = order.pickup_location
            if pickup is not None and pickup.is_p2p:
                pickup.contact_name = data['sender_name'][:100]
                pickup.contact_phone = data['sender_phone'][:20]
                pickup.pickup_zone_no = data.get('pickup_zone')
                pickup.pickup_street_no = data.get('pickup_street')
                pickup.pickup_building_no = data.get('pickup_building')
                pickup.save(update_fields=[
                    'contact_name', 'contact_phone', 'pickup_zone_no',
                    'pickup_street_no', 'pickup_building_no'])

            # Added, dropped or simply moved — the leg back follows whatever this form
            # just said, and is written after the booking so it reads the new answers.
            if booking is not None:
                services.sync_return_order(booking, data)

            _log_customer_edit(order, request.user)
            messages.success(request, 'Delivery updated.')
            return redirect('p2p:delivery_detail', order_number=order.order_number)
    else:
        form = BookingDetailsForm(initial=initial, booking=booking,
                                  verified_whatsapp=me_phone)

    return render(request, 'p2p/delivery_edit.html', {
        'order': order, 'form': form, 'me_phone': me_phone,
    })


def _log_customer_edit(order, user):
    """Leave a trail so ops can see the customer changed something."""
    from orders.models import OrderStatusHistory
    try:
        OrderStatusHistory.objects.create(
            order=order, field_name='order_status',
            old_value=order.order_status, new_value=order.order_status,
            old_display='Edited by customer', new_display='Edited by customer',
            changed_by=user, notes='Customer edited the delivery before pickup')
    except Exception:
        logger.warning('Could not log customer edit for order %s', order.pk, exc_info=True)


@login_required
@require_POST
@ratelimit(key='user', rate=USER_RATE, method='POST', block=False)
def add_comment(request, order_number):
    from orders.models import Order, OrderComments

    if getattr(request, 'limited', False):
        messages.error(request, 'Too many messages. Please wait a moment.')
        return redirect('p2p:delivery_detail', order_number=order_number)

    order = get_object_or_404(Order, order_number=order_number, p2p_customer=request.user)
    body = (request.POST.get('body') or '').strip()
    if not body:
        messages.error(request, 'Write a message first.')
        return redirect('p2p:delivery_detail', order_number=order.order_number)

    comment = OrderComments.objects.create(
        order=order,
        name=request.user.get_full_name() or request.user.username,
        body=body[:2000],
        author=request.user,
        author_role='client',
        # Explicitly visible: this one IS the customer thread.
        is_internal=False,
    )
    from p2p.notifications import notify_ops_of_comment
    notify_ops_of_comment(order, comment)
    messages.success(request, 'Message sent.')
    return redirect('p2p:delivery_detail', order_number=order.order_number)
