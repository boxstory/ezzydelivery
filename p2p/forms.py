# Purpose: The P2P booking forms — WhatsApp number entry, and the pickup/drop details.
# Used by: p2p.views (verify_number, book)
# Notes: Plain Forms, not ModelForms — the fields span Order, PickupLocation and P2PBooking, and
#        fields="__all__" is banned here. Price is never a field: the server recomputes it.

from decimal import Decimal

from django import forms

from core.forms_base import SanitizedFormMixin
from core.validators import normalize_qatar_phone
from p2p.models import (
    P2PBoxTier, P2PRateBand, P2PVehicleBoxLimit, P2PVehicleCapacity,
    P2P_BOOKER_ROLE_CHOICES,
    P2P_FEE_PAYER_CHOICES,
    P2P_MAX_BOXES, P2P_MAX_KG, P2P_SIZE_CARDS,
    P2P_SIZE_CHOICES, P2P_SPEED_CARDS, P2P_SPEED_CHOICES, P2P_TIME_SLOT_CHOICES,
    P2P_VEHICLE_CARDS, P2P_VEHICLE_CHOICES, slot_from_time, time_from_slot,
)
from p2p.pricing import (
    QATAR_BBOX, max_journey_km, primary_size, size_allows_weight, smallest_size_for,
    vehicle_verdict,
)
from p2p.pricing import quote as p2p_quote

SIZE_LABELS = dict(P2P_SIZE_CHOICES)

# A window is a preference, not a requirement, so "any time" is a real answer at
# both ends. The slabs themselves live on the model beside the columns they fill.
TIME_SLOT_FIELD_CHOICES = [('', 'Any time')] + P2P_TIME_SLOT_CHOICES
DATE_FIELD_NAMES = ('pickup_date', 'scheduled_date')
SLOT_FIELD_NAMES = ('pickup_time', 'scheduled_time')


class WhatsAppNumberForm(forms.Form):
    """Collects the number the OTP is sent to.

    A Google signup gives an email and a name, never a phone number, so this is the
    first place we can ask. The number is only written to the Profile once the code
    checks out — persisting an unverified number would defeat the whole step, because
    the order confirmation link is sent to whatever is on file.
    """

    whatsapp = forms.CharField(max_length=20, label='WhatsApp number')

    def clean_whatsapp(self):
        # Raises ValidationError itself, which the form collects.
        return normalize_qatar_phone(self.cleaned_data['whatsapp'], 'WhatsApp number')


class OtpForm(forms.Form):
    code = forms.CharField(max_length=6, min_length=6, label='6-digit code')

    def clean_code(self):
        code = (self.cleaned_data['code'] or '').strip()
        if not code.isdigit():
            raise forms.ValidationError('Enter the 6-digit code from WhatsApp.')
        return code


class BookingDetailsForm(SanitizedFormMixin, forms.Form):
    """Everything a driver needs that the calculator could not know.

    The calculator yields locality names and a price. A real job needs a street
    address at each end, a person to call at each end, and the money terms.

    Neither end is "you". The booker says which one they are standing at, and the
    labels, the prefill and every later message follow from that answer.
    """

    # --- Who is booking ----------------------------------------------------
    booker_role = forms.ChoiceField(
        choices=P2P_BOOKER_ROLE_CHOICES, initial='sender',
        widget=forms.RadioSelect, label='Where do you stand in this delivery?')

    # --- Pickup: where we collect -----------------------------------------
    sender_name = forms.CharField(max_length=100, label="Sender's name")
    sender_phone = forms.CharField(max_length=20, label="Sender's phone")
    pickup_zone = forms.IntegerField(required=False, label='Zone')
    pickup_street = forms.IntegerField(required=False, label='Street')
    pickup_building = forms.IntegerField(required=False, label='Building')
    pickup_notes = forms.CharField(max_length=160, required=False, label='Notes for the driver')
    pickup_date = forms.DateField(required=False, label='Pickup date')
    pickup_time = forms.ChoiceField(
        choices=TIME_SLOT_FIELD_CHOICES, required=False, label='Pickup window')

    # --- Drop: where it goes ----------------------------------------------
    customer_name = forms.CharField(max_length=100, label="Receiver's name")
    customer_phone = forms.CharField(max_length=20, label="Receiver's phone")
    customer_whatsapp = forms.CharField(max_length=20, required=False, label="Receiver's WhatsApp")
    customer_address = forms.CharField(max_length=255, label='Delivery address')
    dl_zone = forms.IntegerField(required=False, label='Zone')
    dl_street = forms.IntegerField(required=False, label='Street')
    dl_building = forms.IntegerField(required=False, label='Building')
    scheduled_date = forms.DateField(required=False, label='Delivery date')
    scheduled_time = forms.ChoiceField(
        choices=TIME_SLOT_FIELD_CHOICES, required=False, label='Delivery window')

    # --- The package (all six pricing inputs live here) --------------------
    # Size and vehicle are radios, not selects: the public calculator asks the same two
    # questions as picture cards, and a customer who just answered them there should not
    # meet a pair of dropdowns here. Radios keep it working with no JavaScript.
    # Optional because a job may instead be described as a count per size below. One of
    # the two has to be there, which clean() checks — a form that required both would
    # make the customer name a size for a load that is three of them.
    size = forms.ChoiceField(choices=P2P_SIZE_CHOICES, widget=forms.RadioSelect,
                             required=False, label='Box size')
    vehicle = forms.ChoiceField(choices=[('', 'Any vehicle')] + P2P_VEHICLE_CHOICES,
                                required=False, widget=forms.RadioSelect,
                                label='Vehicle')
    # No longer rendered on any form: the per-size counters below ARE the count, and a
    # second field stating a total could only ever disagree with them. Kept declared so a
    # POST that still carries one is honoured — clean() overwrites it with the sum
    # whenever a counter is filled, which is every booking made through the pages.
    box_count = forms.IntegerField(min_value=1, max_value=P2P_MAX_BOXES, initial=1,
                                   required=False, label='Number of boxes')
    weight_kg = forms.DecimalField(max_digits=7, decimal_places=2, required=False,
                                   min_value=Decimal('0'), label='Weight (kg)')
    package_description = forms.CharField(max_length=255, required=False, label="What's inside")

    # --- The leg back ------------------------------------------------------
    # A tick, not a second route: the return leg is the same two points the other way
    # round, so there is nothing more to ask for than whether it is wanted and what is
    # coming back. It is priced as a full second journey (p2p.pricing.quote), and it
    # becomes an order of its own so a driver is really dispatched to it.
    return_trip = forms.BooleanField(
        required=False, label='Bring something back to the pickup point',
        help_text='A second trip straight after the delivery, back to where we '
                  'collected. Priced as a second journey.')
    return_description = forms.CharField(
        max_length=255, required=False, label='What comes back',
        help_text='Signed papers, an empty crate, the item after a repair — whatever '
                  'the driver is collecting for the way back.')

    # One counter per size, so a job can be two small and one medium rather than being
    # forced into whichever single size is least wrong. Declared off P2P_SIZE_CHOICES so
    # adding a size to the contract cannot leave a counter behind.
    LOAD_FIELDS = {slug: f'count_{slug}' for slug, _ in P2P_SIZE_CHOICES}

    # --- Money and timing --------------------------------------------------
    cod_amount = forms.DecimalField(max_digits=10, decimal_places=2, required=False,
                                    min_value=Decimal('0'), max_value=Decimal('10000'),
                                    label='Cash to collect from the receiver')
    fee_payer = forms.ChoiceField(
        choices=P2P_FEE_PAYER_CHOICES, initial='sender',
        widget=forms.RadioSelect, label='Who pays the delivery fee?')
    speed = forms.ChoiceField(choices=P2P_SPEED_CHOICES, initial='express',
                              widget=forms.RadioSelect, label='When')

    # Which phone field carries the booker's own number, per role. A third-party booker
    # is on neither leg, so nothing is locked for them — both numbers are strangers'.
    LOCKED_PHONE_BY_ROLE = {
        'sender': 'sender_phone',
        'receiver': 'customer_whatsapp',
        'other': None,
    }

    def __init__(self, *args, booking=None, verified_whatsapp='', **kwargs):
        self.booking = booking
        # The number that passed the OTP step. It is not the customer's to retype here:
        # the confirm link that releases this job is sent to it, so a number typed over
        # it would hand the job to whoever answers that phone instead.
        self.verified_whatsapp = verified_whatsapp
        super().__init__(*args, **kwargs)
        # Bootstrap's own classes rather than a BEM re-declaration of them; the
        # p2pb__ modifier only carries the brand tweaks Bootstrap does not.
        for name, field in self.fields.items():
            widget = field.widget
            # A radio group is not a control Bootstrap styles with form-control; it
            # renders as its own segmented block and would inherit a border and a
            # white box it has no use for.
            if isinstance(widget, forms.RadioSelect):
                widget.attrs.setdefault('class', 'p2pb__choice-input')
                continue
            # Bootstrap styles a tick with its own class; form-control would draw a
            # full-width input box around it.
            if isinstance(widget, forms.CheckboxInput):
                widget.attrs.setdefault('class', 'form-check-input')
                widget.attrs.setdefault('id', f'p2p_book_input_{name}')
                continue
            base = 'form-select' if isinstance(widget, forms.Select) else 'form-control'
            existing = widget.attrs.get('class', '')
            widget.attrs['class'] = f'{existing} {base} p2pb__input'.strip()
            widget.attrs.setdefault('id', f'p2p_book_input_{name}')
        for name in DATE_FIELD_NAMES:
            self.fields[name].widget = forms.DateInput(
                attrs={'type': 'date', 'class': 'form-control p2pb__input',
                       'id': f'p2p_book_input_{name}'})
        # The edit page hands us real times off the Order; a ChoiceField would render
        # blank for anything that is not exactly a slab key, and the customer's saved
        # window would vanish on the next save. Snap it onto the slab that contains it.
        for name in SLOT_FIELD_NAMES:
            if self.initial.get(name) is not None:
                self.initial[name] = slot_from_time(self.initial[name])

        # Both candidates carry the marker so the role toggle can move the lock without
        # a round trip; the one that matches the role right now is locked on render, so
        # the page is correct with no JavaScript at all. clean() is the actual gate.
        for role, name in self.LOCKED_PHONE_BY_ROLE.items():
            if name:
                self.fields[name].widget.attrs['data-verified-lock'] = role
        role = self.submitted_role()
        self.locked_field = self.LOCKED_PHONE_BY_ROLE.get(role)
        if self.locked_field and self.verified_whatsapp:
            widget = self.fields[self.locked_field].widget
            widget.attrs['readonly'] = 'readonly'
            widget.attrs['aria-describedby'] = f'p2p_book_lock_hint_{role}'
            if self.is_bound:
                # A bound field renders what was posted, and a locked field that comes
                # back blank or altered after some other error reads as broken. Correct
                # the data itself so the page shows what will actually be saved.
                self.data = self.data.copy()
                self.data[self.add_prefix(self.locked_field)] = self.verified_whatsapp

        # The per-size counters. Built here rather than declared one by one so the set
        # cannot drift from P2P_SIZE_CHOICES, and blank rather than 0 so an untouched
        # form reads as "nothing said" instead of "none of these".
        for slug, label in P2P_SIZE_CHOICES:
            self.fields[self.LOAD_FIELDS[slug]] = forms.IntegerField(
                min_value=0, max_value=P2P_MAX_BOXES, required=False,
                label=label, widget=forms.NumberInput(attrs={
                    'class': 'form-control form-control-sm',
                    'min': '0', 'max': str(P2P_MAX_BOXES), 'placeholder': '0',
                }))

    # The picture that goes with each choice. On the form rather than in the view so
    # both the booking page and the edit page get it without repeating themselves.
    size_cards = P2P_SIZE_CARDS
    vehicle_cards = P2P_VEHICLE_CARDS
    speed_cards = P2P_SPEED_CARDS

    def load_rows(self):
        """(card, bound field) per size, for the mixed-load counters on the form.

        Off P2P_SIZE_CARDS so the counter a customer meets here is labelled with the same
        words as the card they met on the calculator.
        """
        for slug, _label in P2P_SIZE_CHOICES:
            yield dict(P2P_SIZE_CARDS[slug], slug=slug), self[self.LOAD_FIELDS[slug]]

    def submitted_role(self):
        """The role this render is working from — posted if bound, else the initial."""
        if self.is_bound:
            role = self.data.get(self.add_prefix('booker_role'))
        else:
            role = self.initial.get('booker_role')
        return role if role in self.LOCKED_PHONE_BY_ROLE else 'sender'

    def clean_sender_phone(self):
        return normalize_qatar_phone(self.cleaned_data['sender_phone'], "Sender's phone")

    def clean_customer_phone(self):
        return normalize_qatar_phone(self.cleaned_data['customer_phone'], "Receiver's phone")

    def clean_customer_whatsapp(self):
        return normalize_qatar_phone(
            self.cleaned_data.get('customer_whatsapp'), "Receiver's WhatsApp", required=False)

    def clean_pickup_time(self):
        return time_from_slot(self.cleaned_data.get('pickup_time'))

    def clean_scheduled_time(self):
        return time_from_slot(self.cleaned_data.get('scheduled_time'))

    def clean(self):
        cleaned = super().clean()

        # The booker's own number is the verified one, whatever arrived in the POST.
        # readonly inputs still submit, so this is the gate, not the widget attribute —
        # same principle as the price, which is never a POST field either. Overwritten
        # rather than rejected: a mismatch is a stale page or a tampered one, and
        # neither is worth an error message the honest customer would have to read.
        locked = self.LOCKED_PHONE_BY_ROLE.get(cleaned.get('booker_role'))
        if locked and self.verified_whatsapp:
            cleaned[locked] = self.verified_whatsapp

        # The load, as a count per size. A job described with the counters wins; one
        # described the old way (a single size and a total) is normalised into the same
        # map, so everything below works on one shape.
        load = {slug: cleaned.get(field) or 0
                for slug, field in self.LOAD_FIELDS.items()}
        load = {slug: n for slug, n in load.items() if n > 0}
        if not load and cleaned.get('size'):
            load = {cleaned['size']: cleaned.get('box_count') or 1}

        if not load:
            self.add_error('size', 'Tell us what you are sending — pick a size, or '
                                   'enter how many boxes of each.')
        elif sum(load.values()) > P2P_MAX_BOXES:
            self.add_error(
                None,
                f'{sum(load.values())} boxes is more than one job can be. '
                f'The most we can price here is {P2P_MAX_BOXES} — '
                f'ask us for a quote on anything larger.')

        # The scalar pair stays filled and authoritative for everything downstream that
        # reads one size and one count: the band is chosen on the largest size present,
        # and the Order carries the total.
        cleaned['load'] = load
        if load:
            cleaned['size'] = primary_size(load)
            cleaned['box_count'] = sum(load.values())

        size = cleaned.get('size')
        weight = cleaned.get('weight_kg')

        # Size and weight are both customer inputs and can contradict each other.
        # Unchecked, whichever is cheaper wins by accident, so name the size that
        # fits rather than guessing which one they meant. Checked against the largest
        # size in the load: a 20 kg item is not a small box because envelopes ride
        # along with it.
        if size and weight is not None and not size_allows_weight(size, weight):
            fits = smallest_size_for(weight)
            self.add_error(
                'weight_kg',
                f'{weight} kg is heavier than {SIZE_LABELS.get(size, size)} allows. '
                f'Choose {SIZE_LABELS.get(fits, fits)} instead.')

        # Volume is the other contradiction a customer can type: one small box goes on a
        # motorcycle and three do not, whatever the vehicle picker let them choose. Name
        # the vehicle that can take it rather than silently upgrading — the price moves
        # with the vehicle, and that is theirs to accept.
        vehicle = cleaned.get('vehicle')
        if load and vehicle:
            ok, reason, needed = vehicle_verdict(vehicle, load=load)
            if not ok:
                names = dict(P2P_VEHICLE_CHOICES)
                load_label = ' + '.join(
                    f'{n} × {SIZE_LABELS.get(slug, slug)}' for slug, n in load.items())
                tail = (f'Choose {names.get(needed, needed)}.' if needed
                        else 'Ask us for a price on this one.')
                trouble = ('will not fit' if reason == 'too_big'
                           else 'is less than we send')
                self.add_error(
                    'vehicle',
                    f'{load_label} {trouble} {names.get(vehicle, vehicle)} out for. {tail}')

        # A description of something coming back, on a job that has no leg back, would
        # be printed on a driver's card as an instruction nobody is being paid for.
        if not cleaned.get('return_trip'):
            cleaned['return_description'] = ''

        # A scheduled job needs a collection date; an express one must not carry a
        # stale window at either end — express means the next free driver, and a
        # leftover slab would read as a promise nobody made.
        if cleaned.get('speed') != 'express':
            if not cleaned.get('pickup_date'):
                self.add_error('pickup_date', 'Choose the day we collect the parcel.')
            # Most P2P jobs are collected and delivered the same day, so a blank
            # delivery date means "that day" rather than an unanswered question.
            if not cleaned.get('scheduled_date'):
                cleaned['scheduled_date'] = cleaned.get('pickup_date')
            self._check_window_order(cleaned)
        else:
            for name in DATE_FIELD_NAMES + SLOT_FIELD_NAMES:
                cleaned[name] = None

        # Each end needs something a driver can actually navigate to. The booking
        # already carries a pin from the calculator, so only the street detail is
        # asked for here — but if the pin is outside Qatar, nothing else can help.
        if self.booking is not None:
            lat_min, lat_max, lng_min, lng_max = QATAR_BBOX
            for lat, lng, label in (
                (self.booking.from_lat, self.booking.from_lng, 'pickup'),
                (self.booking.to_lat, self.booking.to_lng, 'delivery'),
            ):
                if not (lat_min <= float(lat) <= lat_max and lng_min <= float(lng) <= lng_max):
                    raise forms.ValidationError(
                        f'The {label} location is outside Qatar. Start again and pick a '
                        'location from the list.')
        return cleaned

    def _check_window_order(self, cleaned):
        """The parcel cannot land before it is collected.

        Both ends are free-typed dates and two independent selects, so the only thing
        stopping a delivery window that opens before the pickup one is this check.
        """
        pickup_date = cleaned.get('pickup_date')
        drop_date = cleaned.get('scheduled_date')
        if not (pickup_date and drop_date):
            return
        if drop_date < pickup_date:
            self.add_error(
                'scheduled_date', 'The delivery day cannot be before the pickup day.')
            return
        pickup_time = cleaned.get('pickup_time')
        drop_time = cleaned.get('scheduled_time')
        if drop_date == pickup_date and pickup_time and drop_time and drop_time < pickup_time:
            self.add_error(
                'scheduled_time',
                'On the same day, the delivery window cannot start before the pickup one.')


# Staff wording for the same three roles. The customer form asks in the first person
# ("I'm sending it") because the customer is one of the two people; ops are neither, so
# the identical choice has to be asked about somebody else.
STAFF_BOOKER_ROLE_CHOICES = [
    ('sender', 'The sender'),
    ('receiver', 'The receiver'),
    ('other', 'A third party, for two other people'),
]


class StaffBookingForm(BookingDetailsForm):
    """Ops taking a point-to-point booking over the phone or the counter.

    Everything the public flow gets from the calculator — the two pins, the distance,
    the category — has to be asked for here, because there is no calculator in front of
    the person on the phone. Everything after that is the customer's own booking form,
    inherited rather than restated, so the two cannot describe a parcel differently.

    Two things only ops may do: name the client account the job is billed to, and
    overrule the rate card on a price they have already quoted out loud.
    """

    # --- The two pins the calculator would have supplied --------------------
    from_label = forms.CharField(max_length=150, label='Pickup area')
    from_lat = forms.DecimalField(max_digits=19, decimal_places=15, label='Pickup latitude')
    from_lng = forms.DecimalField(max_digits=19, decimal_places=15, label='Pickup longitude')
    to_label = forms.CharField(max_length=150, label='Delivery area')
    to_lat = forms.DecimalField(max_digits=19, decimal_places=15, label='Delivery latitude')
    to_lng = forms.DecimalField(max_digits=19, decimal_places=15, label='Delivery longitude')
    category = forms.CharField(max_length=80, required=False, label='What is being sent')

    # --- Ops-only decisions -------------------------------------------------
    bill_to = forms.ModelChoiceField(
        queryset=None, required=False, label='Bill to client account',
        help_text='Leave blank for a walk-in or phone customer — the fee is then cash '
                  'to the driver. Pick a client and it goes on their charge invoice '
                  'instead, and no cash changes hands.')
    agreed_price = forms.DecimalField(
        max_digits=10, decimal_places=2, required=False, min_value=Decimal('0'),
        label='Agreed price (QAR)',
        help_text='Leave blank to charge whatever the rate card works out. Fill it in '
                  'only when a different figure has already been quoted to the customer.')
    # The booker is not always on either leg, and for a staff booking they are never the
    # person typing, so the number cannot be inferred from a session the way it is on
    # the public form. Asked for outright, with the leg as the fallback.
    booker_phone = forms.CharField(
        max_length=20, required=False, label='Send the confirmation to',
        help_text="Blank uses the number of whichever end you picked above.")
    confirm_now = forms.BooleanField(
        required=False, initial=False, label='Customer already agreed — release it now',
        help_text='Skips waiting on the confirm link: the pickup goes live and drivers '
                  'can see the job straight away.')
    notify_customer = forms.BooleanField(
        required=False, initial=True, label='Send the WhatsApp confirmation')

    # Rendered in this order, so the page reads route → people → parcel → money rather
    # than in the order the fields happen to be declared across two classes.
    def __init__(self, *args, **kwargs):
        from business.models import Business

        # No verified number exists on a staff booking: nobody proved a phone to us in
        # this flow, so nothing is locked and both numbers stay editable.
        kwargs.setdefault('verified_whatsapp', '')
        kwargs.setdefault('booking', None)
        super().__init__(*args, **kwargs)

        # The parent already gives a checkbox form-check-input; these three only need
        # the staff page's own id convention on top of it.
        for name in ('confirm_now', 'notify_customer', 'return_trip'):
            self.fields[name].widget.attrs['id'] = f'workforce_p2p_new_input_{name}'

        self.fields['bill_to'].queryset = (
            Business.objects.filter(business_status='active').order_by('business_name'))
        self.fields['bill_to'].empty_label = 'No account — personal / walk-in'

        self.fields['booker_role'].choices = STAFF_BOOKER_ROLE_CHOICES
        self.fields['booker_role'].label = 'Who asked for this delivery?'
        self.fields['booker_role'].help_text = (
            'Decides who gets the confirmation. The other end never asked us for '
            'anything, and the link in that message is what releases the job.')

        # The pins are filled by the locality picker, not typed — but they stay real
        # inputs so a coordinate read off a map link can be pasted straight in.
        for name in ('from_lat', 'from_lng', 'to_lat', 'to_lng'):
            self.fields[name].widget = forms.NumberInput(attrs={
                'class': 'form-control form-control-sm p2pb__input',
                'step': 'any', 'id': f'workforce_p2p_new_input_{name}',
            })
        for name in ('from_label', 'to_label'):
            self.fields[name].widget.attrs['autocomplete'] = 'off'
            self.fields[name].widget.attrs['list'] = 'workforce_p2p_new_list_localities'

        # Staff take a delivery address as one line off the phone; the zone/street
        # numbers are a bonus, exactly as on the customer form.
        self.fields['customer_address'].widget.attrs['placeholder'] = (
            'Building, street, area — what the driver needs to find the door')

    def clean_booker_phone(self):
        return normalize_qatar_phone(
            self.cleaned_data.get('booker_phone'), 'Confirmation number', required=False)

    def clean(self):
        cleaned = super().clean()

        # The parent checks the pins on an existing booking; here they arrive in this
        # POST, so they are checked here. A pin outside Qatar prices a journey nobody
        # can drive and writes an order no driver can navigate to.
        from p2p.pricing import in_qatar

        for lat_name, lng_name, label in (('from_lat', 'from_lng', 'Pickup'),
                                          ('to_lat', 'to_lng', 'Delivery')):
            lat, lng = cleaned.get(lat_name), cleaned.get(lng_name)
            if lat is None or lng is None:
                continue
            if not in_qatar(lat, lng):
                self.add_error(
                    lat_name,
                    f'{label} location is outside Qatar. Pick an area from the list, '
                    'or paste coordinates from a map.')

        # Whoever the confirmation goes to. Falls back to the leg they are standing on,
        # which is the same rule notify_phone applies — done here so the booking is
        # written with a real number rather than relying on the fallback at send time.
        if not cleaned.get('booker_phone'):
            role = cleaned.get('booker_role')
            if role == 'receiver':
                cleaned['booker_phone'] = (
                    cleaned.get('customer_whatsapp') or cleaned.get('customer_phone') or '')
            elif role == 'sender':
                cleaned['booker_phone'] = cleaned.get('sender_phone') or ''

        if cleaned.get('notify_customer') and not cleaned.get('booker_phone'):
            self.add_error(
                'booker_phone',
                'There is no number to send the confirmation to. Enter one, or untick '
                'the WhatsApp confirmation.')

        # Price the job here, not in the view. The confirm-now rule below turns on
        # whether there is a price at all, and a second quote() call somewhere else is
        # how the figure the form validated and the figure the order is written with
        # come apart.
        self.quote_result = None
        if not self.errors and cleaned.get('load'):
            self.quote_result = p2p_quote(
                (cleaned['from_lat'], cleaned['from_lng']),
                (cleaned['to_lat'], cleaned['to_lng']),
                size=cleaned.get('size') or '', vehicle=cleaned.get('vehicle') or '',
                speed=cleaned.get('speed') or 'express',
                boxes=cleaned.get('box_count') or 1,
                weight_kg=cleaned.get('weight_kg'), load=cleaned.get('load') or None,
                return_trip=bool(cleaned.get('return_trip')),
            )

        # Releasing a job with no agreed figure sends a driver out on a price nobody
        # has said out loud, and leaves the order at zero for whoever bills it later.
        card_price = (self.quote_result or {}).get('price')
        if cleaned.get('confirm_now') and cleaned.get('agreed_price') is None and card_price is None:
            self.add_error(
                'agreed_price',
                'The rate card cannot price this load, so there is nothing to release. '
                'Enter the price you quoted, or leave it for the customer to confirm.')

        return cleaned


class P2PVehicleCapacityForm(forms.ModelForm):
    """One vehicle's load space, as ops edit it on the rate card page."""

    class Meta:
        model = P2PVehicleCapacity
        fields = ['vehicle', 'min_cbm', 'capacity_cbm', 'is_active']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            widget = field.widget
            if isinstance(widget, forms.CheckboxInput):
                widget.attrs['class'] = 'form-check-input'
                continue
            base = 'form-select' if isinstance(widget, forms.Select) else 'form-control'
            widget.attrs['class'] = f'{base} {base}-sm'
        self.fields['capacity_cbm'].widget.attrs['placeholder'] = '0.0270'
        # A blank minimum is a real answer — this vehicle goes out for anything — so it
        # is optional and reads as 0 rather than as an unfilled field.
        self.fields['min_cbm'].required = False
        self.fields['min_cbm'].widget.attrs['placeholder'] = '0'

    INTENT_FIELDS = ('vehicle', 'capacity_cbm')

    def clean(self):
        cleaned = super().clean()
        if cleaned.get('min_cbm') is None:
            cleaned['min_cbm'] = Decimal('0')
        minimum = cleaned.get('min_cbm')
        capacity = cleaned.get('capacity_cbm')
        if minimum is not None and capacity is not None and minimum > capacity:
            self.add_error('min_cbm', 'The smallest load cannot be more than the vehicle holds.')
        return cleaned

    def has_changed(self):
        if self.instance.pk is None:
            filled = any(
                self.data.get(self.add_prefix(name)) not in (None, '', False)
                for name in self.INTENT_FIELDS
            )
            if not filled:
                return False
        return super().has_changed()


class P2PVehicleBoxLimitForm(forms.ModelForm):
    """One vehicle/size count ceiling, as ops edit it on the rate card page.

    Separate from P2PVehicleCapacityForm because it is a different shape of fact: a
    capacity is one number per vehicle, a count is one per vehicle AND size. Folding
    them together would have meant five count columns on the capacity row.
    """

    class Meta:
        model = P2PVehicleBoxLimit
        fields = ['vehicle', 'size', 'max_boxes', 'is_active']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            widget = field.widget
            if isinstance(widget, forms.CheckboxInput):
                widget.attrs['class'] = 'form-check-input'
                continue
            base = 'form-select' if isinstance(widget, forms.Select) else 'form-control'
            widget.attrs['class'] = f'{base} {base}-sm'
        # A blank count is a real answer here — this pairing has no count rule and the
        # cbm ceiling decides — so it stays optional rather than reading as unfilled.
        self.fields['max_boxes'].required = False
        self.fields['max_boxes'].widget.attrs['placeholder'] = 'volume decides'

    INTENT_FIELDS = ('vehicle', 'size', 'max_boxes')

    def clean(self):
        cleaned = super().clean()
        cap = cleaned.get('max_boxes')
        if cap is not None and cap > P2P_MAX_BOXES:
            self.add_error(
                'max_boxes',
                f'A booking cannot be more than {P2P_MAX_BOXES} boxes, so a higher '
                f'ceiling here would never bite.')
        return cleaned

    def has_changed(self):
        if self.instance.pk is None:
            filled = any(
                self.data.get(self.add_prefix(name)) not in (None, '', False)
                for name in self.INTENT_FIELDS
            )
            if not filled:
                return False
        return super().has_changed()


class P2PBoxTierForm(forms.ModelForm):
    """One box tier, as ops edit it, on the same page as the bands.

    Kept off P2PRateBand deliberately — see P2PBoxTier — so this stays four short rows
    instead of multiplying the 172-row card by the number of tiers.
    """

    class Meta:
        model = P2PBoxTier
        fields = ['min_boxes', 'max_boxes', 'from_fill', 'to_fill', 'up_to_kg',
                  'uplift', 'needs_quote', 'is_active']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            widget = field.widget
            if isinstance(widget, forms.CheckboxInput):
                widget.attrs['class'] = 'form-check-input'
                continue
            widget.attrs['class'] = 'form-control form-control-sm'
        # No field on this card says "no limit" any more: a blank ceiling is saved as the
        # real limit of a bookable job, and the placeholder says which number that is.
        self.fields['max_boxes'].widget.attrs['placeholder'] = str(P2P_MAX_BOXES)
        self.fields['up_to_kg'].widget.attrs['placeholder'] = f'{P2P_MAX_KG:.0f}'
        # The fill bounds are the opposite: blank is a real answer meaning "this row is
        # not about how full the vehicle is", so they must not close on anything.
        self.fields['from_fill'].widget.attrs['placeholder'] = 'any'
        self.fields['to_fill'].widget.attrs['placeholder'] = 'any'

    # Same trap as the band form: the trailing blank row posts the model defaults back,
    # so only a deliberately filled field counts as intent.
    INTENT_FIELDS = ('max_boxes', 'from_fill', 'to_fill', 'up_to_kg', 'uplift',
                     'needs_quote')

    def has_changed(self):
        if self.instance.pk is None:
            filled = any(
                self.data.get(self.add_prefix(name)) not in (None, '', False, '0')
                for name in self.INTENT_FIELDS
            )
            if not filled:
                return False
        return super().has_changed()

    def clean(self):
        cleaned = super().clean()
        # A ceiling left blank closes on the real limit rather than on infinity.
        if cleaned.get('max_boxes') is None:
            cleaned['max_boxes'] = P2P_MAX_BOXES
        if cleaned.get('up_to_kg') is None:
            cleaned['up_to_kg'] = P2P_MAX_KG
        min_boxes = cleaned.get('min_boxes')
        max_boxes = cleaned.get('max_boxes')
        if min_boxes and max_boxes and max_boxes < min_boxes:
            self.add_error('max_boxes', 'Highest box count cannot be below the lowest.')

        # A fill bound is a fraction, and one typed as 50 rather than 0.5 would put every
        # load in the first slab for ever without ever looking wrong on the page.
        lo, hi = cleaned.get('from_fill'), cleaned.get('to_fill')
        for name, value in (('from_fill', lo), ('to_fill', hi)):
            if value is not None and not (Decimal('0') <= value <= Decimal('1')):
                self.add_error(name, 'A fill bound is a fraction between 0 and 1 '
                                     '(0.5 is half full, 1 is full).')
        if lo is not None and hi is not None and hi <= lo:
            self.add_error('to_fill', 'The top of the slab has to be above its bottom.')
        return cleaned


class P2PRateBandForm(forms.ModelForm):
    """One row of the rate card, as ops edit it.

    Explicit field list rather than __all__: created_at/updated_at are not theirs to
    set, and a new column should not become editable just because it was added.
    """

    class Meta:
        model = P2PRateBand
        fields = [
            'min_boxes', 'max_boxes', 'size', 'up_to_kg', 'vehicle', 'speed',
            'up_to_km', 'price', 'needs_quote', 'priority', 'is_active',
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            widget = field.widget
            if isinstance(widget, forms.CheckboxInput):
                widget.attrs['class'] = 'form-check-input'
                continue
            base = 'form-select' if isinstance(widget, forms.Select) else 'form-control'
            widget.attrs['class'] = f'{base} {base}-sm'
        # "Any" is the useful default for every constraint — a blank cell reads as
        # "this row does not care", which is exactly what it means.
        self.fields['size'].empty_label = 'Any size'
        self.fields['vehicle'].empty_label = 'Any vehicle'
        self.fields['speed'].empty_label = 'Any speed'
        # Blank means "any" for the three constraint columns, but a ceiling is not a
        # constraint you can leave open: it is saved as the furthest a real job can go,
        # and the placeholder is that number rather than the words "no limit".
        self.fields['max_boxes'].widget.attrs['placeholder'] = str(P2P_MAX_BOXES)
        self.fields['up_to_kg'].widget.attrs['placeholder'] = 'any'
        self.fields['up_to_km'].widget.attrs['placeholder'] = str(max_journey_km())

    # Fields that mean somebody actually intended a row. min_boxes, priority and
    # is_active all render with model defaults, so their presence proves nothing.
    INTENT_FIELDS = ('price', 'needs_quote', 'size', 'vehicle', 'speed',
                     'up_to_kg', 'up_to_km', 'max_boxes')

    def has_changed(self):
        """Treat an untouched "add a row" line as empty.

        The trailing extra row renders with the model's own defaults (min_boxes 1,
        priority 0, is_active on), so the browser posts them back and Django counts the
        row as edited — then clean() demands a price for a row nobody filled in, and the
        whole formset fails, discarding every real edit on the page. Only the fields
        above are evidence of intent.
        """
        if self.instance.pk is None:
            filled = any(
                self.data.get(self.add_prefix(name)) not in (None, '', False)
                for name in self.INTENT_FIELDS
            )
            if not filled:
                return False
        return super().has_changed()

    def clean(self):
        cleaned = super().clean()
        if cleaned.get('max_boxes') is None:
            cleaned['max_boxes'] = P2P_MAX_BOXES
        if cleaned.get('up_to_km') is None:
            cleaned['up_to_km'] = max_journey_km()
        min_boxes = cleaned.get('min_boxes')
        max_boxes = cleaned.get('max_boxes')
        if min_boxes and max_boxes and max_boxes < min_boxes:
            self.add_error('max_boxes', 'Highest box count cannot be below the lowest.')
        # A priced row with no price is almost always a half-finished edit, and it
        # would quietly deliver free deliveries rather than fail.
        if not cleaned.get('needs_quote') and not cleaned.get('price'):
            self.add_error('price', 'Set a price, or tick "Needs quote".')
        return cleaned
