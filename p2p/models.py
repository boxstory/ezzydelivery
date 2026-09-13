# Purpose: Point-to-point booking — the ops-editable rate card and the quote/booking record.
# Used by: p2p.pricing (band resolution), p2p.services (order creation), p2p.views, p2p.admin
# Notes: A booking exists before any Order and before any User, which is why the quote is a row
#        here rather than JSON on the Order. Choices are lists, never sets (sets = endless migrations).

from decimal import Decimal, ROUND_HALF_UP

from django.conf import settings
from django.db import models

from orders.models import Order


# Mirrors the size cards in webpages/templates/webpages/p2p_pricing.html and the
# weight brackets printed on them. The slug is the contract; the label on the card
# is display copy and may be reworded without touching pricing.
P2P_SIZE_CHOICES = [
    ('xs', 'Envelope / Docs (≤ 0.5 kg)'),
    ('s', 'Small Box (≤ 3 kg)'),
    ('m', 'Medium Box (≤ 10 kg)'),
    ('l', 'Large Box (≤ 25 kg)'),
    ('xl', 'Bulky / Extra Large (25 kg+)'),
]

# What each size looks like on the picker: the same five cards the public calculator
# shows, so a customer meets the identical choice twice and does not have to re-read it.
# Display copy only — the slug above is the contract. 'box' drives a CSS glyph that grows
# with the size; 'dims' is the outside measurement a parcel of that size fits within.
# 'label' is the wording the calculator already put in data-label and carries into the
# quote summary — kept here so the two pages cannot drift.
# 'cbm' is the same box in cubic metres — the dims multiplied out, so a load can be
# measured against what a vehicle actually holds. The envelope is given a nominal 5 cm
# of thickness because a stack of fifty of them is a real load; xl has no dimensions to
# multiply, so it carries the volume of the smallest thing that stops being a large box.
P2P_SIZE_CARDS = {
    'xs': {'tag': 'XS', 'name': 'Envelope', 'label': 'Envelope / Docs',
           'dims': '35 × 25 cm', 'weight': '≤ 0.5 kg', 'box': True,
           'cbm': Decimal('0.004')},          # 35 × 25 × 5 cm
    's':  {'tag': 'S', 'name': 'Small box', 'label': 'Small Box',
           'dims': '30 × 25 × 20 cm', 'weight': '≤ 3 kg', 'box': True,
           'cbm': Decimal('0.015')},          # 30 × 25 × 20 cm
    'm':  {'tag': 'M', 'name': 'Medium box', 'label': 'Medium Box',
           'dims': '45 × 35 × 30 cm', 'weight': '≤ 10 kg', 'box': True,
           'cbm': Decimal('0.047')},          # 45 × 35 × 30 cm
    'l':  {'tag': 'L', 'name': 'Large box', 'label': 'Large Box',
           'dims': '60 × 45 × 40 cm', 'weight': '≤ 25 kg', 'box': True,
           'cbm': Decimal('0.108')},          # 60 × 45 × 40 cm
    'xl': {'tag': 'XL', 'name': 'Bulky item', 'label': 'Bulky / Extra Large',
           'dims': 'Over 60 cm', 'weight': '25 kg+', 'box': True,
           'cbm': Decimal('0.250')},          # anything past a large box
}

# The vehicle cards, likewise mirroring the calculator. The blank slug is a real option
# here and not on the calculator: a form has to be able to say "you pick".
# A vehicle card names the vehicle and nothing else — capacity belongs to the size
# picker, and printing a weight here only invited the customer to price two ways.
P2P_VEHICLE_CARDS = {
    '':      {'icon': 'fa-solid fa-wand-magic-sparkles', 'name': 'Any',
              'label': 'Any vehicle'},
    'bike':  {'icon': 'fa-solid fa-motorcycle', 'name': 'Bike',
              'label': 'Motorcycle'},
    'car':   {'icon': 'fa-solid fa-car', 'name': 'Car',
              'label': 'Car'},
    'suv':   {'icon': 'fa-solid fa-truck-pickup', 'name': 'SUV / Pickup',
              'label': 'SUV / Pickup'},
    'van':   {'icon': 'fa-solid fa-van-shuttle', 'name': 'Van',
              'label': 'Van'},
    'truck': {'icon': 'fa-solid fa-truck', 'name': 'Truck',
              'label': 'Truck'},
}

# The two speeds as cards. Express and Scheduled are a pricing input, not a preference:
# a rate band can be written for either, so this belongs beside the other card sets.
P2P_SPEED_CARDS = {
    'express':  {'icon': 'fa-solid fa-bolt', 'name': 'Express',
                 'label': 'Express', 'cap': 'As soon as possible'},
    'standard': {'icon': 'fa-solid fa-calendar-days', 'name': 'Scheduled',
                 'label': 'Scheduled', 'cap': 'On a date you choose'},
}


def speed_card_list():
    """The speed cards in contract order, each carrying its own slug."""
    return [dict(P2P_SPEED_CARDS[slug], slug=slug) for slug, _ in P2P_SPEED_CHOICES]


def size_card_list():
    """The size cards in contract order, each carrying its own slug.

    Both the public calculator and the booking form render from this, so the wording a
    customer reads when they price a parcel is the wording they read when they book it.
    """
    return [dict(P2P_SIZE_CARDS[slug], slug=slug) for slug, _ in P2P_SIZE_CHOICES]


def vehicle_card_list(include_any=False):
    """The vehicle cards in contract order. 'Any' is a real option on a form and not
    on the calculator, where tapping a selected card clears it instead."""
    slugs = [slug for slug, _ in P2P_VEHICLE_CHOICES]
    if include_any:
        slugs = [''] + slugs
    return [dict(P2P_VEHICLE_CARDS[slug], slug=slug) for slug in slugs]

# Upper weight bound implied by each size, used to reject a size/kg contradiction
# before it reaches pricing. xl is open-ended.
P2P_SIZE_MAX_KG = {
    'xs': 0.5,
    's': 3,
    'm': 10,
    'l': 25,
    'xl': None,
}

# Slugs come from data-vehicle on the vehicle cards. Note the bike card's label
# reads "Motorcycle" — match on the slug, never the label.
P2P_VEHICLE_CHOICES = [
    ('bike', 'Motorcycle'),
    ('car', 'Car'),
    ('suv', 'SUV / Pickup'),
    ('van', 'Van'),
    ('truck', 'Truck'),
]

# The most boxes one point-to-point job can be. Every range on the rate card closes on
# this rather than running to infinity: 21 boxes is not a booking anyone can make, so a
# row that says "1 to no limit" is describing a job that does not exist. The booking
# form, the calculator's stepper and the accept view all clamp to it.
P2P_MAX_BOXES = 20

# The heaviest single point-to-point job the card will price automatically. Nothing
# derives this the way P2P_MAX_BOXES falls out of the booking form's clamp — it is a
# business limit, and it is here so that a weight ceiling left blank closes on a real
# number instead of on "no limit". Past it, a job is a freight conversation.
P2P_MAX_KG = Decimal('1000')


# --- Which vehicle carries which size ------------------------------------------
# One source for two readers: fill_p2p_rate_card generates a priced row only for a
# pair in P2P_VEHICLE_FITS, and the staff rate-card matrix uses the same knowledge to
# decide which of its 30 rows are everyday combinations and which are curiosities.
# Kept here, beside the cards these came off, so the two cannot drift.

# The vehicles in order of capacity. Position is the whole point — "one size up" is
# an index step, so inserting a vehicle in the middle re-ranks everything correctly.
P2P_VEHICLE_LADDER = ['bike', 'car', 'suv', 'van', 'truck']

# What can physically take each size. A pair outside this is not automatically priced:
# a medium box strapped to a motorcycle is a conversation with a human.
#
# A truck is on every row and a bulky item rides on a pickup or bigger, both since
# 2026-09-10, when the rate card was backfilled so that no combination is left at a
# price of zero. Neither widens what a vehicle can hold: the capacity rules
# (P2PVehicleCapacity.min_cbm) still keep a truck from being sent for an envelope, so a
# row existing here is what makes a job priceable, not what makes it offered.
P2P_VEHICLE_FITS = {
    'xs': {'', 'bike', 'car', 'suv', 'van', 'truck'},
    's':  {'', 'bike', 'car', 'suv', 'van', 'truck'},
    'm':  {'', 'car', 'suv', 'van', 'truck'},
    'l':  {'', 'suv', 'van', 'truck'},
    'xl': {'', 'suv', 'van', 'truck'},
}

# The cheapest vehicle that can carry each size — what "Any vehicle" is charged as.
P2P_SMALLEST_FIT = {'xs': 'bike', 's': 'bike', 'm': 'car', 'l': 'suv', 'xl': 'suv'}


def is_everyday_pairing(size, vehicle):
    """Would a customer plausibly book this size in this vehicle?

    True for "Any", for the smallest vehicle that fits, and for one size up (a
    customer who wants the extra room, or takes what is free). False for a vehicle
    too small to carry the load at all, and for one two or more sizes larger than
    the parcel needs — an envelope in a van is a real, priceable row, but nobody
    picks it, and printing it beside the everyday rows makes the card harder to read.
    """
    if vehicle == '':
        return True
    smallest = P2P_SMALLEST_FIT.get(size)
    if smallest is None or vehicle not in P2P_VEHICLE_FITS.get(size, set()):
        return False
    return 0 <= P2P_VEHICLE_LADDER.index(vehicle) - P2P_VEHICLE_LADDER.index(smallest) <= 1


# Speed doubles as a pricing input and as the scheduling choice. Values match
# Order.DELIVERY_SPEED_CHOICES so the order can be stamped directly.
P2P_SPEED_CHOICES = [
    ('express', 'Express — as soon as possible'),
    ('standard', 'Scheduled — on a chosen date'),
]

# Both ends of the job are booked as a 3-hour window, never as a clock time. A driver
# routed across the city cannot honour a minute, and a slab is what the customer is
# actually promised. The stored value is the START of the window, so the existing
# TimeField columns keep working and Order.scheduled_time still reads as a time.
P2P_TIME_SLOT_HOURS = 3
P2P_TIME_SLOT_START_HOUR = 8
P2P_TIME_SLOT_END_HOUR = 23


def _slot_label(hour):
    """8 -> '8 AM', 14 -> '2 PM'. Written out rather than %-formatted because the
    label is read by a customer, not parsed."""
    suffix = 'AM' if hour < 12 else 'PM'
    display = hour % 12 or 12
    return f'{display} {suffix}'


P2P_TIME_SLOT_CHOICES = [
    (f'{hour:02d}:00', f'{_slot_label(hour)} – {_slot_label(hour + P2P_TIME_SLOT_HOURS)}')
    for hour in range(P2P_TIME_SLOT_START_HOUR, P2P_TIME_SLOT_END_HOUR,
                      P2P_TIME_SLOT_HOURS)
]


def time_from_slot(value):
    """'14:00' -> time(14, 0). Anything not a known slab is None, which is the same
    answer as "no preference" — a hand-crafted POST must not invent a window."""
    from datetime import time as _time

    if not value:
        return None
    if isinstance(value, _time):
        return value
    if value not in dict(P2P_TIME_SLOT_CHOICES):
        return None
    return _time(int(value[:2]), 0)


def slot_from_time(value):
    """time(15, 40) -> '14:00'. Floors onto the slab that contains it.

    Rows written before the slabs existed (and staff edits in the admin) carry
    arbitrary times; without this the select would render blank and the customer's
    saved window would silently disappear on the next save.
    """
    from datetime import time as _time

    if not isinstance(value, _time):
        return value or ''
    slots = [key for key, _ in P2P_TIME_SLOT_CHOICES]
    hour = value.hour
    if hour < P2P_TIME_SLOT_START_HOUR:
        return slots[0]
    floored = (P2P_TIME_SLOT_START_HOUR
               + ((hour - P2P_TIME_SLOT_START_HOUR) // P2P_TIME_SLOT_HOURS)
               * P2P_TIME_SLOT_HOURS)
    key = f'{floored:02d}:00'
    return key if key in slots else slots[-1]


def window_label(day, start):
    """A date and a slab start rendered as one line a customer can read.

    A window with no time is a real answer ("that day, any time"), so the time half
    is optional; a time with no date is not, and reads as nothing.
    """
    if not day:
        return ''
    when = day.strftime('%-d %b')
    if not start:
        return f'{when}, any time'
    end_hour = (start.hour + P2P_TIME_SLOT_HOURS) % 24
    return f'{when}, {_slot_label(start.hour)} – {_slot_label(end_hour)}'


P2P_BOOKING_STATUS_CHOICES = [
    ('draft', 'Draft — quote accepted, not signed in'),
    ('details', 'Signed in — filling details'),
    ('awaiting_price', 'Awaiting staff price'),
    ('awaiting_customer', 'Awaiting customer confirmation'),
    ('confirmed', 'Confirmed by customer'),
    ('abandoned', 'Abandoned'),
    ('cancelled', 'Cancelled'),
]

# Which end of the job the person doing the booking is standing at, if either. A parcel
# is just as often ordered by the person waiting for it (buy something off a marketplace,
# ask a friend to hand it over) as by the one handing it over — and just as often by
# somebody who is at neither end: an assistant, a relative, a shop arranging it for two
# other people. Each case needs a different half of the form prefilled, and 'other' needs
# neither: both legs are strangers to the person filling it in.
P2P_BOOKER_ROLE_CHOICES = [
    ('sender', "I'm sending it"),
    ('receiver', "I'm receiving it"),
    ('other', "I'm booking it for two other people"),
]

# Who hands the driver the delivery fee, and therefore where it is collected. Not
# derived from booker_role: a sender can book and let the receiver pay on arrival, and
# a receiver can book and have the sender settle at pickup. The booker chooses.
P2P_FEE_PAYER_CHOICES = [
    ('sender', 'Sender pays the driver at pickup'),
    ('receiver', 'Receiver pays the driver on delivery'),
]

# How the delivery fee is settled. A personal booking is cash to the driver — at
# pickup or at the door, per fee_payer; one routed to the booker's own business is
# billed on their existing charge invoice instead, and no cash changes hands.
P2P_FEE_STATUS_CHOICES = [
    ('pending', 'Not collected'),
    ('collected_cash', 'Collected in cash'),
    ('billed', 'Billed to the client invoice'),
    ('waived', 'Waived'),
]


class P2PRateBand(models.Model):
    """One row of the ops-editable P2P rate card.

    Six inputs decide a price: how many boxes, what size, how heavy, which vehicle,
    how fast, and how far. Every constraint left blank/null means "applies to any",
    so the common case is a handful of broad rows and ops add narrower ones as they
    learn what needs its own price.
    """

    min_boxes = models.PositiveIntegerField(
        default=1, help_text="Lowest box count this row covers")
    max_boxes = models.PositiveIntegerField(
        blank=True, null=True, help_text="Highest box count. Blank = no upper limit.")
    size = models.CharField(
        max_length=4, choices=P2P_SIZE_CHOICES, blank=True, default='',
        help_text="Blank = any size")
    up_to_kg = models.DecimalField(
        max_digits=7, decimal_places=2, blank=True, null=True,
        help_text="Weight ceiling for this row. Blank = any weight.")
    vehicle = models.CharField(
        max_length=10, choices=P2P_VEHICLE_CHOICES, blank=True, default='',
        help_text="Blank = any vehicle")
    speed = models.CharField(
        max_length=20, choices=P2P_SPEED_CHOICES, blank=True, default='',
        help_text="Blank = any speed")
    up_to_km = models.DecimalField(
        max_digits=7, decimal_places=2, blank=True, null=True,
        help_text="Distance ceiling for this row. Blank = no upper limit.")

    price = models.DecimalField(
        max_digits=10, decimal_places=2, default=0,
        help_text="QAR. Ignored when needs_quote is set.")
    needs_quote = models.BooleanField(
        default=False,
        help_text="No automatic price — staff quote this one by hand")
    # Specificity is computed (most constraints set wins), but an explicit override
    # matters: an implicit-only score produces an unexplainable price with no way for
    # ops to correct it without restructuring rows.
    priority = models.IntegerField(
        default=0, help_text="Higher wins when two rows are equally specific")
    is_active = models.BooleanField(default=True, db_index=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "P2P rate band"
        verbose_name_plural = "P2P rate card"
        ordering = ['-priority', 'up_to_km', 'id']

    def __str__(self):
        bits = []
        if self.size:
            bits.append(self.get_size_display())
        if self.vehicle:
            bits.append(self.get_vehicle_display())
        if self.speed:
            bits.append(self.get_speed_display())
        if self.up_to_kg is not None:
            bits.append(f"≤{self.up_to_kg}kg")
        boxes = f"{self.min_boxes}-{self.max_boxes or '∞'} box"
        km = f"≤{self.up_to_km}km" if self.up_to_km is not None else "any distance"
        tail = "quote" if self.needs_quote else f"{self.price} QAR"
        return f"{boxes} · {' · '.join(bits) or 'any'} · {km} → {tail}"

    @property
    def specificity(self):
        """How many constraints this row sets. More constraints = better match."""
        return sum([
            self.size != '',
            self.vehicle != '',
            self.speed != '',
            self.up_to_kg is not None,
            self.max_boxes is not None or self.min_boxes > 1,
        ])


class P2PVehicleCapacity(models.Model):
    """How much one vehicle holds, in cubic metres.

    A bike's box is 30 cm on a side — 0.027 cbm — which is one small box, not three.
    Without this the card would happily price three of them onto a motorcycle, because
    the size/vehicle table only ever asked whether ONE box fits.

    The other end matters too. A pickup is not sent out for a shoebox when a car can
    take it — min_cbm is the smallest load worth the vehicle, and it only bites when
    something smaller could actually do the job, so it can never strand a load between
    two vehicles.

    A row per vehicle, in the database rather than in code, because it is a fact about
    this fleet: swap the bikes for ones with a bigger box and the number moves without
    a deploy.
    """

    vehicle = models.CharField(
        max_length=10, choices=P2P_VEHICLE_CHOICES, unique=True,
        help_text="Which vehicle this is the capacity of")
    capacity_cbm = models.DecimalField(
        max_digits=8, decimal_places=4,
        help_text="Cubic metres of load space. A 30 cm cube is 0.027.")
    min_cbm = models.DecimalField(
        max_digits=8, decimal_places=4, default=0,
        help_text="Smallest load worth sending this vehicle out for. A pickup set to "
                  "1.0 is not offered for a parcel a car could take. Ignored when "
                  "nothing smaller can carry the load. 0 = no minimum.")
    is_active = models.BooleanField(
        default=True, db_index=True,
        help_text="Off = no volume limit on this vehicle")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "P2P vehicle capacity"
        verbose_name_plural = "P2P vehicle capacities"
        ordering = ['capacity_cbm', 'id']

    def __str__(self):
        span = (f"{self.min_cbm}-{self.capacity_cbm} cbm" if self.min_cbm
                else f"{self.capacity_cbm} cbm")
        return f"{self.get_vehicle_display()} → {span}"

    @property
    def name(self):
        return P2P_VEHICLE_CARDS.get(self.vehicle, {}).get('name', self.vehicle)


class P2PVehicleBoxLimit(models.Model):
    """The most boxes of one size a vehicle takes, whatever the volume arithmetic says.

    Volume is only half of what stops a load. A car holds 0.4 cbm, which is nine small
    boxes on paper; ops counted six. A boot is not a cube, rigid boxes do not tessellate
    into the space around a wheel arch, and a driver carries them to a door an armful at
    a time. The two real numbers cannot both be a cubic-metre ceiling \u2014 three medium
    boxes needs 0.141 and six small ones needs under 0.105 \u2014 so no value of
    ``capacity_cbm`` expresses them, and this is the count that says what volume cannot.

    A missing row, a blank count, or a row switched off is no count limit at all and the
    volume rule stands alone, which is how the card behaved before this existed.
    """

    vehicle = models.CharField(
        max_length=10, choices=P2P_VEHICLE_CHOICES,
        help_text="Which vehicle this count is for")
    size = models.CharField(
        max_length=2, choices=P2P_SIZE_CHOICES,
        help_text="Which box size the count applies to")
    max_boxes = models.PositiveIntegerField(
        blank=True, null=True,
        help_text="Most boxes of this size the vehicle takes. Blank = volume decides.")
    is_active = models.BooleanField(
        default=True, db_index=True,
        help_text="Off = no count limit on this pairing")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "P2P vehicle box limit"
        verbose_name_plural = "P2P vehicle box limits"
        ordering = ['vehicle', 'size', 'id']
        constraints = [
            models.UniqueConstraint(
                fields=['vehicle', 'size'],
                name='uniq_p2p_box_limit_vehicle_size'),
        ]

    def __str__(self):
        cap = self.max_boxes if self.max_boxes is not None else '\u221e'
        return f"{self.get_vehicle_display()} \u2192 {cap} \u00d7 {self.get_size_display()}"

    @property
    def name(self):
        return P2P_VEHICLE_CARDS.get(self.vehicle, {}).get('name', self.vehicle)


def _pct(fraction):
    """0.5 -> '50%'. Whole numbers only: a slab boundary at 33.3% reads as noise."""
    return f"{round(Decimal(fraction) * 100)}%"


class P2PBoxTier(models.Model):
    """What a job costs for carrying more than one box.

    Deliberately additive, and deliberately NOT another dimension on P2PRateBand. A
    band decides one price, so pricing boxes inside the card would have meant a row per
    combination per box tier — the 172-row card becomes 600-odd rows and stops being
    readable or editable. Instead the resolved band price gets one uplift added to it:

        price = band.price + tier.uplift

    A tier flagged needs_quote takes the whole job to a staff quote however cheap the
    band was, because past a certain count it is a van run, not a checkout.

    A tier is bounded two ways, and either may be left blank to mean "any":

    * **Fill** (from_fill / to_fill) — how full the vehicle is, as a fraction of what it
      actually takes of that box size. This is the one that scales: a car that takes six
      medium boxes reads a 0-0.5 tier as 1-3 boxes and a 0.5-1 tier as 4-6, while a van
      reads the same two rows as 1-10 and 11-20. Before this the slabs were absolute, so
      the same "4-10 boxes, +25" row meant a full car and a fifth-full van, and three of
      the four slabs were dead on a bike.
    * **Count** (min_boxes / max_boxes) — an absolute number of boxes, regardless of
      vehicle. Still the right shape for a rule that is about the job rather than the
      load: "past eleven boxes a human prices it" is true in a van and in a car.

    Both are checked, so a row may state either or both. A fill-bounded tier is skipped
    for a load whose ceiling is unknown — there is no fraction to compare.
    """

    min_boxes = models.PositiveIntegerField(
        default=1, help_text="Lowest box count this tier covers")
    max_boxes = models.PositiveIntegerField(
        blank=True, null=True, help_text="Highest box count. Blank = no upper limit.")
    from_fill = models.DecimalField(
        max_digits=4, decimal_places=3, blank=True, null=True,
        help_text="How full the vehicle is, from. 0.5 = half. Blank = no lower bound.")
    to_fill = models.DecimalField(
        max_digits=4, decimal_places=3, blank=True, null=True,
        help_text="How full the vehicle is, up to and including. 1 = full. "
                  "Blank = no upper bound.")
    up_to_kg = models.DecimalField(
        max_digits=8, decimal_places=2, blank=True, null=True,
        help_text="Weight ceiling for this tier. Four boxes of documents and four of "
                  "tiles are not the same job.")
    uplift = models.DecimalField(
        max_digits=10, decimal_places=2, default=0,
        help_text="QAR added to the band price for a job in this tier. Ignored when "
                  "needs_quote is set.")
    needs_quote = models.BooleanField(
        default=False, help_text="No automatic price at this many boxes — staff price it")
    is_active = models.BooleanField(default=True, db_index=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "P2P box tier"
        verbose_name_plural = "P2P box tiers"
        ordering = ['min_boxes', 'id']

    def __str__(self):
        span = f"{self.min_boxes}-{self.max_boxes or '∞'} box"
        if self.up_to_kg is not None:
            span += f" ≤{self.up_to_kg}kg"
        tail = "quote" if self.needs_quote else f"+{self.uplift} QAR"
        return f"{span} → {tail}"

    @property
    def is_fill_based(self):
        """Does this row price by how full the vehicle is, rather than by a count?"""
        return self.from_fill is not None or self.to_fill is not None

    @property
    def label(self):
        """The column head on the staff matrix.

        A fill row has no single box count to print — it is 1-3 in a car and 1-10 in a
        van — so it names the fraction instead and the matrix prints the real counts per
        row, where the vehicle is known.
        """
        if self.is_fill_based:
            lo = self.from_fill or Decimal('0')
            hi = self.to_fill
            if hi is None:
                return f"over {_pct(lo)} full"
            if not lo:
                return f"up to {_pct(hi)} full"
            return f"{_pct(lo)}\u2013{_pct(hi)} full"
        if self.max_boxes is None:
            return f"{self.min_boxes}+ boxes"
        if self.max_boxes == self.min_boxes:
            return "1 box" if self.min_boxes == 1 else f"{self.min_boxes} boxes"
        return f"{self.min_boxes}\u2013{self.max_boxes} boxes"

    @property
    def weight_label(self):
        """'≤ 25 kg' — printed under the column head only when the tiers differ on it,
        which the chart works out for itself."""
        if self.up_to_kg is None:
            return ''
        kg = self.up_to_kg.normalize()
        return f"≤ {kg:f} kg"


class P2PBooking(models.Model):
    """A quote the customer accepted, and everything that followed from it.

    Exists before the Order and before the User: the row is created the moment
    someone taps Accept on the public calculator, survives the Google round trip,
    and is what an abandoned funnel entry or an unpriced quote request looks like.
    It is also the audit record of what price was shown versus what was charged.
    """

    token = models.CharField(max_length=64, unique=True, db_index=True)
    token_expires_at = models.DateTimeField(blank=True, null=True)
    status = models.CharField(
        max_length=20, choices=P2P_BOOKING_STATUS_CHOICES, default='draft', db_index=True)

    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, blank=True, null=True,
        related_name='p2p_bookings',
        help_text="Set once they sign in. Null while the draft is anonymous.")
    order = models.OneToOneField(
        Order, on_delete=models.SET_NULL, blank=True, null=True,
        related_name='p2p_booking')

    # --- The quote, as shown to the customer -------------------------------
    from_label = models.CharField(max_length=150)
    to_label = models.CharField(max_length=150)
    from_lat = models.DecimalField(max_digits=19, decimal_places=15)
    from_lng = models.DecimalField(max_digits=19, decimal_places=15)
    to_lat = models.DecimalField(max_digits=19, decimal_places=15)
    to_lng = models.DecimalField(max_digits=19, decimal_places=15)
    distance_km = models.DecimalField(max_digits=7, decimal_places=2)

    category = models.CharField(max_length=80, blank=True, default='')
    size = models.CharField(max_length=4, choices=P2P_SIZE_CHOICES, blank=True, default='')
    vehicle = models.CharField(max_length=10, choices=P2P_VEHICLE_CHOICES, blank=True, default='')
    speed = models.CharField(max_length=20, choices=P2P_SPEED_CHOICES, default='express')
    box_count = models.PositiveIntegerField(default=1)
    weight_kg = models.DecimalField(max_digits=7, decimal_places=2, blank=True, null=True)

    quoted_price = models.DecimalField(
        max_digits=10, decimal_places=2, blank=True, null=True,
        help_text="Server-computed. Null when the booking needs a staff quote.")
    needs_quote = models.BooleanField(default=False)
    rate_band = models.ForeignKey(
        P2PRateBand, on_delete=models.SET_NULL, blank=True, null=True,
        related_name='bookings')
    # Which revision of the card produced quoted_price, so a later edit to the rate
    # card is auditable rather than silently retroactive.
    ladder_version = models.CharField(max_length=20, blank=True, default='')

    # --- Staff pricing, for the needs_quote path ---------------------------
    staff_price = models.DecimalField(
        max_digits=10, decimal_places=2, blank=True, null=True)
    priced_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, blank=True, null=True,
        related_name='p2p_bookings_priced')
    priced_at = models.DateTimeField(blank=True, null=True)
    customer_agreed_at = models.DateTimeField(blank=True, null=True)

    # --- Who is booking ----------------------------------------------------
    booker_role = models.CharField(
        max_length=10, choices=P2P_BOOKER_ROLE_CHOICES, default='sender',
        help_text="Which end of this job the customer is standing at, if either")
    # The booker's own verified WhatsApp number, copied from their Profile at booking
    # time. A column rather than a lookup through customer.profile because a third-party
    # booker appears on neither leg, so there is otherwise nowhere to reach them — and
    # because the number that was verified then is the one this booking was agreed on.
    booker_phone = models.CharField(max_length=20, blank=True, default='')

    # --- The two people, frozen at booking time ----------------------------
    # PickupLocation and Order are both staff-editable; these are the immutable
    # record of what the customer actually told us, and what the confirm link and
    # every notification are addressed from.
    sender_name = models.CharField(max_length=100, blank=True, default='')
    sender_phone = models.CharField(max_length=20, blank=True, default='')
    receiver_name = models.CharField(max_length=100, blank=True, default='')
    receiver_phone = models.CharField(max_length=20, blank=True, default='')
    pickup_locality = models.CharField(max_length=150, blank=True, default='')
    pickup_zone = models.PositiveIntegerField(blank=True, null=True)
    pickup_street = models.PositiveIntegerField(blank=True, null=True)
    pickup_building = models.PositiveIntegerField(blank=True, null=True)
    pickup_notes = models.CharField(max_length=160, blank=True, default='')

    # --- Money -------------------------------------------------------------
    fee_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    fee_payer = models.CharField(
        max_length=10, choices=P2P_FEE_PAYER_CHOICES, default='sender',
        help_text="Decides whether the driver asks for the fee at pickup or at the door")
    fee_status = models.CharField(
        max_length=20, choices=P2P_FEE_STATUS_CHOICES, default='pending', db_index=True)
    fee_txn = models.ForeignKey(
        'fleet.DriverTransaction', on_delete=models.SET_NULL, blank=True, null=True,
        related_name='p2p_bookings')
    # The receiver's cash only. The sender's delivery fee is never folded in here.
    cod_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    # --- The return leg ----------------------------------------------------
    # Some jobs are not one journey but two: hand a document over, wait while it is
    # signed, bring the signed copy back. The second leg is a real Order of its own
    # (to_label → from_label) rather than a flag on the first — a driver has to be sent
    # to it, somebody has to receive it, and it has to be billed — so what is stored
    # here is the customer's request and the link to the order it produced.
    return_trip = models.BooleanField(
        default=False,
        help_text="A second journey bringing something back to the pickup point")
    return_description = models.CharField(
        max_length=255, blank=True, default='',
        help_text="What comes back on the return leg")
    return_order = models.OneToOneField(
        Order, on_delete=models.SET_NULL, blank=True, null=True,
        related_name='p2p_return_booking',
        help_text="The order for the leg back. Null on every one-way booking.")

    # --- Timing, one window per end ----------------------------------------
    # pickup_* is when the driver collects; scheduled_* is when it lands, and keeps
    # its name because that pair is what Order.scheduled_date/time are stamped from.
    # Both times hold the START of a 3-hour slab (see P2P_TIME_SLOT_CHOICES).
    pickup_date = models.DateField(blank=True, null=True)
    pickup_time = models.TimeField(blank=True, null=True)
    scheduled_date = models.DateField(blank=True, null=True)
    scheduled_time = models.TimeField(blank=True, null=True)

    # --- Abuse forensics ---------------------------------------------------
    source_ip = models.GenericIPAddressField(blank=True, null=True)
    user_agent = models.CharField(max_length=255, blank=True, default='')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "P2P booking"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['customer', '-created_at'], name='p2p_cust_created_idx'),
            models.Index(fields=['status', '-created_at'], name='p2p_status_created_idx'),
        ]

    def __str__(self):
        return f"P2P {self.from_label} → {self.to_label} ({self.status})"

    def load_map(self):
        """{size: count} for this job, whichever shape the row is in.

        A job booked as several sizes has lines; one booked as a single size has only the
        scalar pair, and so does every row written before mixed loads existed. Callers ask
        here and never have to know which — the pair stays filled on a mixed booking too,
        carrying the largest size and the total, so nothing that reads it has to change.
        """
        lines = {line.size: line.count for line in self.lines.all() if line.count}
        if lines:
            return lines
        return {self.size: self.box_count or 1} if self.size else {}

    @property
    def load_label(self):
        """'2 × Small Box + 1 × Medium Box' — the summary line on a booking."""
        lines = list(self.lines.all())
        if lines:
            return ' + '.join(line.label for line in lines)
        card = P2P_SIZE_CARDS.get(self.size, {})
        return f"{self.box_count or 1} × {card.get('label', self.size)}" if self.size else ''

    @property
    def pickup_window(self):
        """'12 Sep, 2 PM – 5 PM', or '' when no window was asked for."""
        return window_label(self.pickup_date, self.pickup_time)

    @property
    def pickup_window_is_today(self):
        """Drives the emphasis on the driver's pickup card.

        localdate() and not date.today(): the server clock is UTC and a Qatar
        evening is already tomorrow there, which would drop the emphasis from
        every window booked after 9 PM.
        """
        from django.utils import timezone

        return bool(self.pickup_date and self.pickup_date == timezone.localdate())

    @property
    def delivery_window(self):
        """Same, for the drop end.

        Read off the Order when there is one: that row is what ops and the driver
        work from, and a staff reschedule lands there, not on this booking.
        """
        if self.order_id:
            return window_label(self.order.scheduled_date, self.order.scheduled_time)
        return window_label(self.scheduled_date, self.scheduled_time)

    @property
    def agreed_price(self):
        """What the customer actually agreed to pay, whichever path got us there."""
        if self.staff_price is not None:
            return self.staff_price
        return self.quoted_price

    @property
    def return_fee(self):
        """The return leg's share of the agreed price. Zero on a one-way booking.

        The two legs are the same journey in opposite directions carrying the same load,
        so the rate card prices them identically and half the total IS one leg. Derived
        rather than stored: a staff price that overrules the card then splits the same
        way, and there is no second figure that can fall out of step with the first.
        """
        total = self.agreed_price
        if not self.return_trip or total is None:
            return Decimal('0.00')
        return (Decimal(total) / 2).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

    @property
    def outbound_fee(self):
        """The outward leg's share — the remainder, so the two halves always add back up
        to the exact figure the customer agreed to, whichever way the rounding went."""
        total = self.agreed_price
        if total is None:
            return None
        return Decimal(total) - self.return_fee

    @property
    def return_route_label(self):
        """'Doha → Al Wakrah' read backwards, for the summary lines. Empty on a one-way
        booking, so a template can print it unguarded."""
        if not self.return_trip:
            return ''
        return f'{self.to_label} → {self.from_label}'

    @property
    def notify_phone(self):
        """The number every message about this booking goes to.

        The booker's own verified number, never sender_phone. Whoever is at the other
        end of this job is a third party who never asked us for anything, and the link
        in that message is the one that releases the job.

        Falls back to the leg they are standing on for rows written before the number
        was stored; a third-party booking has no such fallback, which is exactly why
        the column exists.
        """
        if self.booker_phone:
            return self.booker_phone
        if self.booker_role == 'receiver':
            return self.receiver_phone or self.sender_phone
        if self.booker_role == 'other':
            return ''
        return self.sender_phone

    @property
    def fee_note(self):
        """One sentence telling the booker where the money changes hands.

        Written from the booker's side — "you pay" only when they are the one paying —
        so a sender who asked the receiver to settle is not told to have cash ready.
        Shared by the WhatsApp confirmation, the receipt and the confirm page, which
        must not drift apart on something this concrete.
        """
        if self.fee_status == 'billed':
            return 'Billed to your account — no cash needed.'
        paying = self.fee_payer == self.booker_role
        if self.fee_payer == 'receiver':
            return ('Pay the driver in cash when the parcel arrives.' if paying
                    else 'The receiver pays the driver in cash on delivery.')
        return ('Pay the driver in cash when they collect.' if paying
                else 'The sender pays the driver in cash at pickup.')

    @property
    def fee_due_at_pickup(self):
        """Cash the driver must ask for from the person handing the parcel over."""
        return bool(
            self.fee_amount and self.fee_status == 'pending'
            and self.fee_payer == 'sender')

    @property
    def fee_due_at_delivery(self):
        """Cash the driver must ask for at the door instead."""
        return bool(
            self.fee_amount and self.fee_status == 'pending'
            and self.fee_payer == 'receiver')


class P2PBookingLine(models.Model):
    """One size of box in a job that carries more than one.

    A job used to be a size and a count, which could not say "two small and one medium".
    The scalar pair is still on P2PBooking and still filled — it carries the largest size
    present and the total count, because that is what the band is chosen on and what the
    Order needs — and these rows are the detail behind it.

    A row per size rather than a JSON blob: ops read this in the admin beside the rest of
    the booking, and a count that has to be summed and compared against a vehicle is a
    number, not a document.
    """

    booking = models.ForeignKey(
        'P2PBooking', on_delete=models.CASCADE, related_name='lines',
        help_text="The job this is part of")
    size = models.CharField(
        max_length=4, choices=P2P_SIZE_CHOICES,
        help_text="Which box size this line counts")
    count = models.PositiveIntegerField(
        default=1, help_text="How many boxes of this size")

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "P2P booking line"
        verbose_name_plural = "P2P booking lines"
        ordering = ['booking', 'size', 'id']
        constraints = [
            models.UniqueConstraint(fields=['booking', 'size'],
                                    name='uniq_p2p_booking_line_size'),
        ]

    def __str__(self):
        return f"{self.count} \u00d7 {self.get_size_display()}"

    @property
    def label(self):
        """'2 x Small Box' — what the customer sees on the summary."""
        card = P2P_SIZE_CARDS.get(self.size, {})
        return f"{self.count} \u00d7 {card.get('label', self.size)}"
