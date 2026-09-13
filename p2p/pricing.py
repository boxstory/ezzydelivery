# Purpose: The only place a P2P price is decided — distance, band resolution and the quote rule.
# Used by: p2p.views (accept + submit), p2p.forms validation, webpages.views (ladder injection)
# Notes: Mirrors webpages/static/webpages/js/p2p-calculator.js exactly (×1.2 road factor, +2/+4/+8 km
#        buffer, priced off kmHigh, then + the box tier uplift). The two must agree to the fils or
#        the customer is shown one number and charged another. A posted price is never trusted.

import math
from decimal import Decimal

from p2p.models import (
    P2PBoxTier, P2PRateBand, P2PVehicleCapacity, P2P_SIZE_MAX_KG,
)

# Bumped whenever the pricing *rules* change (not when ops edit a price — that is
# what the rate-card rows are for). Stamped on every booking so an old quote can be
# explained after the fact.
LADDER_VERSION = '2026-09-v1'

# The calculator rejects pins outside this box before it will price anything.
# Deliberately NOT delivery.geo.QATAR_BOUNDS (24.0-26.5 / 50.5-52.0): that one is a
# looser, advisory box used for warnings, and quietly adopting it here would accept
# pins the public page refuses.
QATAR_BBOX = (24.4, 26.3, 50.7, 51.8)  # lat_min, lat_max, lng_min, lng_max

EARTH_RADIUS_KM = 6371.0

# Straight-line distance understates a real drive; the calculator has always applied
# a flat 1.2 and then quoted a range. Pricing uses the top of that range.
ROAD_FACTOR = Decimal('1.2')


def max_journey_km():
    """The longest journey the calculator will accept, as the customer would be quoted.

    Derived from QATAR_BBOX, not chosen: the two opposite corners of the box the page
    refuses to price outside of, run through the same road factor and buffer as a real
    quote, rounded up to the next 10 km. This is what a distance band closes on instead
    of running to infinity — past it there is no bookable job to price.
    """
    lat_min, lat_max, lng_min, lng_max = QATAR_BBOX
    _low, high = distance_band(lat_min, lng_min, lat_max, lng_max)
    return int(math.ceil(high / 10.0) * 10)


def in_qatar(lat, lng):
    """True when a pin is inside the box the public calculator will accept."""
    if lat is None or lng is None:
        return False
    lat_min, lat_max, lng_min, lng_max = QATAR_BBOX
    return lat_min <= float(lat) <= lat_max and lng_min <= float(lng) <= lng_max


def haversine_km(lat1, lng1, lat2, lng2):
    """Great-circle distance in km. Same formula as the calculator's haversine()."""
    lat1, lng1, lat2, lng2 = float(lat1), float(lng1), float(lat2), float(lng2)
    d_lat = math.radians(lat2 - lat1)
    d_lng = math.radians(lng2 - lng1)
    a = (math.sin(d_lat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2))
         * math.sin(d_lng / 2) ** 2)
    return EARTH_RADIUS_KM * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def distance_band(lat1, lng1, lat2, lng2):
    """Return (km_low, km_high) exactly as the calculator displays them.

    The buffer widens with distance because the straight-line estimate degrades:
    +2 km under 15, +4 under 25, +8 beyond. Price is taken from km_high, so the
    customer is never quoted less than the range they were shown.
    """
    km = Decimal(str(haversine_km(lat1, lng1, lat2, lng2))) * ROAD_FACTOR
    buf = 2 if km < 15 else (4 if km < 25 else 8)
    km_low = int(Decimal(km).to_integral_value(rounding='ROUND_HALF_UP'))
    return km_low, km_low + buf


def size_allows_weight(size, weight_kg):
    """Is this weight inside the bracket the chosen box size claims?

    Size and weight are both customer inputs and can contradict each other. Left
    unchecked, whichever is cheaper would win by accident, so the caller rejects the
    pair rather than guessing which one the customer meant.
    """
    if not size or weight_kg is None:
        return True
    ceiling = P2P_SIZE_MAX_KG.get(size)
    if ceiling is None:          # xl is open-ended
        return True
    return Decimal(str(weight_kg)) <= Decimal(str(ceiling))


def smallest_size_for(weight_kg):
    """The size a given weight actually fits, for the form's error message."""
    if weight_kg is None:
        return None
    w = Decimal(str(weight_kg))
    for slug, ceiling in P2P_SIZE_MAX_KG.items():
        if ceiling is None or w <= Decimal(str(ceiling)):
            return slug
    return 'xl'


def _capacity_rows():
    """{slug: {'capacity': cbm, 'minimum': cbm}} for the vehicles ops have measured.

    A vehicle missing from here, or switched off, has no volume rule at all — the card
    falls back to the size/vehicle policy alone, which is how it behaved before
    capacities existed.
    """
    return {
        c.vehicle: {'capacity': c.capacity_cbm, 'minimum': c.min_cbm}
        for c in P2PVehicleCapacity.objects.filter(is_active=True)
    }


def _box_limit_rows():
    """{(vehicle, size): max_boxes} for the pairings ops have counted.

    The count limit volume cannot express: a car holds nine small boxes of arithmetic
    and six in practice. A pairing missing from here, blank, or switched off has no
    count limit and the volume rule decides alone.
    """
    from p2p.models import P2PVehicleBoxLimit

    return {
        (r.vehicle, r.size): r.max_boxes
        for r in P2PVehicleBoxLimit.objects.filter(is_active=True)
        if r.max_boxes is not None
    }


def vehicle_capacities():
    """{slug: cbm} — just the ceilings, for callers that only ask "does it fit"."""
    return {slug: row['capacity'] for slug, row in _capacity_rows().items()}


def load_cbm(size, boxes=1):
    """The volume of this many boxes of this size, in cubic metres."""
    from p2p.models import P2P_SIZE_CARDS

    per_box = P2P_SIZE_CARDS.get(size, {}).get('cbm')
    if per_box is None:
        return None
    return per_box * max(1, int(boxes))


def vehicle_can_carry(vehicle, size='', boxes=1, capacities=None, limits=None,
                      load=None):
    """Does the load physically fit in this vehicle?

    Two ceilings, and either one is enough to say no. Volume: three small boxes are
    0.045 cbm and a motorcycle box is 0.027, so the answer is no however willing the
    rate card is — the size/vehicle table only ever asked whether ONE box fits, which
    is what let a bike be quoted for a car's load. Count: a car holds nine small boxes
    of arithmetic and six in practice, and no capacity_cbm can say that and "three
    medium" at the same time, so the count is stored per pairing and checked here.

    "Any vehicle" is not a vehicle and always fits; smallest_vehicle_for() decides what
    it turns into.
    """
    if not vehicle:
        return True
    caps = _capacity_rows() if capacities is None else capacities
    lims = _box_limit_rows() if limits is None else limits
    spec = as_load(size, boxes, load)

    # The count and the volume ceiling both live inside the fill fraction, which is what
    # lets one test cover a mixed load: each size contributes the share of the vehicle it
    # takes, and the shares add up.
    fill = load_fill(vehicle, spec, caps, lims, booking_cap=False)
    if fill is not None and fill > 1:
        return False

    # Volume again, but on the exact sum rather than the per-size ceiling, which floors.
    row = caps.get(vehicle)
    volume = load_cbm_of(spec)
    if row is None or volume is None:
        return True
    return volume <= row['capacity']


def vehicle_verdict(vehicle, size='', boxes=1, capacities=None, limits=None,
                    load=None):
    """Is this the right vehicle for this load? Returns (ok, reason, use_instead).

    Two ways to be wrong, and they are opposites:

    * ``too_big`` — the load does not fit. Three small boxes are 0.045 cbm and a
      motorcycle box is 0.027.
    * ``oversized`` — it fits, but the vehicle is more than the job needs and something
      smaller could take it. A pickup is not sent out for a shoebox.

    The second only fires when a smaller vehicle can actually carry the load, so a
    0.5 cbm load still gets the pickup even though the pickup asks for a cubic metre:
    nothing smaller can hold it, and stranding a bookable load between two vehicles
    would be worse than sending a half-empty one.

    "Any vehicle" is not a vehicle and is always right — smallest_vehicle_for() decides
    what it becomes.
    """
    if not vehicle:
        return True, None, None

    caps = _capacity_rows() if capacities is None else capacities
    lims = _box_limit_rows() if limits is None else limits
    spec = as_load(size, boxes, load)

    # The count ceiling first, carried inside the fill fraction. It is a "too big" the
    # volume rule cannot reach: six small boxes is a car's real load and 0.090 cbm, which
    # no capacity that also allows six medium boxes could ever refuse. For a mixed load
    # the fractions add, so three medium and three small is exactly one full car.
    fill = load_fill(vehicle, spec, caps, lims, booking_cap=False)
    if fill is not None and fill > 1:
        return False, 'too_big', smallest_vehicle_for(load=spec, capacities=caps, limits=lims)

    row = caps.get(vehicle)
    volume = load_cbm_of(spec)
    if row is None or volume is None:
        return True, None, None

    if volume > row['capacity']:
        return False, 'too_big', smallest_vehicle_for(load=spec, capacities=caps, limits=lims)

    if row['minimum'] and volume < row['minimum']:
        smaller = smallest_vehicle_for(load=spec, capacities=caps, limits=lims)
        if smaller is not None and smaller != vehicle:
            from p2p.models import P2P_VEHICLE_LADDER
            if P2P_VEHICLE_LADDER.index(smaller) < P2P_VEHICLE_LADDER.index(vehicle):
                return False, 'oversized', smaller

    return True, None, None


def smallest_vehicle_for(size='', boxes=1, capacities=None, limits=None, load=None):
    """The cheapest vehicle that can actually take this load, or None if nothing can.

    Walks the capacity ladder in order and takes the first one that both the card's
    size policy allows (P2P_VEHICLE_FITS — a medium box is not going on a motorcycle
    even when the arithmetic says it would fit) and that has the room.
    """
    from p2p.models import P2P_VEHICLE_FITS, P2P_VEHICLE_LADDER

    caps = _capacity_rows() if capacities is None else capacities
    lims = _box_limit_rows() if limits is None else limits
    spec = as_load(size, boxes, load)
    if not spec:
        return None

    # A mixed load has to be allowed for EVERY size it contains: one medium box in the
    # mix keeps the whole job off a motorcycle, however many envelopes ride with it.
    allowed = set(P2P_VEHICLE_LADDER)
    for one_size in spec:
        allowed &= P2P_VEHICLE_FITS.get(one_size, set())

    for vehicle in P2P_VEHICLE_LADDER:
        if vehicle in allowed and vehicle_can_carry(
                vehicle, capacities=caps, limits=lims, load=spec):
            return vehicle
    return None


def _matches(band, boxes, size, weight_kg, vehicle, speed, km):
    """Does this row cover the request? A constraint left blank covers everything."""
    if boxes < band.min_boxes:
        return False
    if band.max_boxes is not None and boxes > band.max_boxes:
        return False
    if band.size and band.size != size:
        return False
    if band.vehicle and band.vehicle != vehicle:
        return False
    if band.speed and band.speed != speed:
        return False
    if band.up_to_kg is not None:
        if weight_kg is None or Decimal(str(weight_kg)) > band.up_to_kg:
            return False
    if band.up_to_km is not None and Decimal(str(km)) > band.up_to_km:
        return False
    return True


def resolve_band(boxes=1, size='', weight_kg=None, vehicle='', speed='express', km=0,
                 bands=None):
    """Pick the one row that prices this request, or None when nothing matches.

    Order of precedence, highest first:

    1. ``priority`` — the explicit override. Everything defaults to 0, so this is
       inert until ops deliberately set it. It has to outrank specificity, not merely
       break ties between equally specific rows: otherwise a quote-only rule can be
       silently defeated by someone adding a narrower ladder row later, which is
       exactly the accident the seeded rows guard against by carrying priority=10.
    2. ``specificity`` — a row naming a vehicle *and* a size is a more deliberate
       statement than a catch-all, so it wins by default.
    3. The tightest distance ceiling.

    Pass `bands` to resolve against an already-loaded card instead of querying.
    """
    # `bands` lets a caller resolving hundreds of combinations read the card once — the
    # staff matrix is 960 cells, and a query each was 963 queries and two seconds.
    rows = list(P2PRateBand.objects.filter(is_active=True)) if bands is None else bands
    candidates = [b for b in rows if _matches(b, boxes, size, weight_kg, vehicle, speed, km)]
    if not candidates:
        return None
    return sorted(
        candidates,
        key=lambda b: (
            b.priority,
            b.specificity,
            -(b.up_to_km if b.up_to_km is not None else Decimal('999999')),
        ),
        reverse=True,
    )[0]


def as_load(size='', boxes=1, load=None):
    """One canonical shape for both ways of naming a load: {size: count}.

    A job used to be one size and a count. It can now be several sizes at once, and
    every resolver takes the map — so the old pair is normalised here, once, instead of
    each function growing a second code path that can drift from the first.
    """
    if load:
        return {s: int(n) for s, n in load.items() if s and n and int(n) > 0}
    if size:
        return {size: max(1, int(boxes))}
    return {}


def load_boxes(load):
    """How many boxes in total, whatever mix of sizes they are."""
    return sum(as_load(load=load).values())


def primary_size(load):
    """The biggest size in the load — the band a mixed job is priced on.

    Bands are written per size, and a mixed load has no single one. Charging it as the
    largest thing in it is the rule a customer can be told in one sentence, and it can
    never come out under the same boxes booked on their own.
    """
    from p2p.models import P2P_SIZE_CHOICES

    order = [slug for slug, _ in P2P_SIZE_CHOICES]
    present = [s for s in order if s in as_load(load=load)]
    return present[-1] if present else ''


def load_cbm_of(load, capacities=None):
    """The volume of a whole load, mixed or not. None when a size has no measurement."""
    from p2p.models import P2P_SIZE_CARDS

    total = Decimal(0)
    for size, count in as_load(load=load).items():
        per_box = P2P_SIZE_CARDS.get(size, {}).get('cbm')
        if per_box is None:
            return None
        total += per_box * count
    return total


def max_boxes_for(vehicle, size, capacities=None, limits=None, booking_cap=True):
    """The most boxes of this size the vehicle takes, across both ceilings.

    The count limit and the volume limit each cap it, and so does P2P_MAX_BOXES — a
    booking cannot be more than that however big the van is.

    Three answers, and the difference matters: a number is the ceiling, 0 means this
    vehicle cannot take even one of these, and None means there is nothing to say
    (no vehicle named, or a size with no measurements).

    ``booking_cap`` is what P2P_MAX_BOXES is doing here, and it is deliberately optional.
    As the denominator of a fill fraction it belongs: "full" has to mean full relative to
    the biggest job anyone can book, or a van would sit at 5% for every load the card can
    take and its top slab would never fire. As a test of what a vehicle can physically
    carry it does not belong at all — that is a rule about the booking form, not about
    the van, and folding it in would refuse a load on the grounds that nobody may order
    it.
    """
    from p2p.models import P2P_MAX_BOXES, P2P_SIZE_CARDS

    if not vehicle:
        return None
    caps = _capacity_rows() if capacities is None else capacities
    lims = _box_limit_rows() if limits is None else limits

    ceiling = lims.get((vehicle, size))
    if booking_cap:
        ceiling = P2P_MAX_BOXES if ceiling is None else min(ceiling, P2P_MAX_BOXES)
    elif ceiling is None:
        ceiling = None

    row = caps.get(vehicle)
    per_box = P2P_SIZE_CARDS.get(size, {}).get('cbm')
    if per_box is None:
        return None
    if row is not None:
        from_volume = int(row['capacity'] / per_box)
        ceiling = from_volume if ceiling is None else min(ceiling, from_volume)

    return ceiling


def load_fill(vehicle, load, capacities=None, limits=None, booking_cap=True):
    """How full this load leaves the vehicle, as a fraction of what it takes.

    Six medium boxes fill a car and a fifth of a van, which is the whole reason the
    slabs are written as fractions: one row then means the same thing in both.

    A mixed load is the sum of its parts, and that is the whole trick to carrying more
    than one size in one job: three medium boxes and three small ones are half a car
    each, so together they are exactly one full car. There is nothing to add to the
    slabs to price a mixed load — they already take a fraction, and a mixed load makes
    one.

    Infinity when the vehicle cannot take even one of something in the load, so the
    caller's ``fill <= 1`` refuses it. None when there is no ceiling to be a fraction of
    at all, and a fill-bounded tier is skipped for it.
    """
    total = Decimal(0)
    for size, count in as_load(load=load).items():
        ceiling = max_boxes_for(vehicle, size, capacities, limits, booking_cap)
        if ceiling is None:
            return None
        if ceiling == 0:
            return Decimal('Infinity')
        total += Decimal(count) / Decimal(ceiling)
    return total or None


def boxes_for_fill(vehicle, size, fill, capacities=None, limits=None):
    """The box count a fill fraction lands on — the inverse of load_fill().

    The staff matrix needs it to print a fill slab as the counts it means for the row
    it is on: "up to half" is 1-3 in a car and 1-10 in a van.
    """
    ceiling = max_boxes_for(vehicle, size, capacities, limits)
    if not ceiling or fill is None:
        return None
    import math
    return max(1, min(ceiling, int(math.floor(Decimal(ceiling) * Decimal(fill)))))


def resolve_box_tier(boxes=1, weight_kg=None, vehicle='', size='',
                     capacities=None, limits=None, load=None):
    """The tier that covers this load, or None when nothing does.

    Separate from resolve_band on purpose: a band decides one price for one shape of
    job, and folding the box count into it would have meant a row per combination per
    tier. The tier is applied on top instead — see P2PBoxTier.

    A tier is bounded by an absolute count, by how full the vehicle is, or by both, and
    every stated bound has to hold. The fill bound is the one that makes a slab mean the
    same thing in a car and in a van; a tier that states one is skipped when the load has
    no known ceiling, because there is no fraction to test it against.

    The narrowest covering tier wins, measured across BOTH bounds at once: each span is
    taken as a fraction of everything it could have covered, and the two are multiplied.
    A row that states no fill covers the whole vehicle and a row that states no count
    covers every count, so either kind of catch-all loses to a row that pins something
    down. This is what keeps a "1 box" row beating a "up to half full" one: a bike is
    100% full at a single small box, and the commonest booking on the platform must not
    be charged as a full vehicle.

    needs_quote is the exception and beats everything covering. It is the rule that says
    a job is too big to check out, and a cheaper covering slab must not be able to hand
    a customer an automatic price for it.

    An unstated weight does NOT rule a weight-limited tier out, which is the opposite of
    what a band does. Weight is optional on the public calculator, and refusing tiers
    without it would silently zero the box uplift on every quote from that page — the
    customer would be shown one number and charged another.
    """
    spec = as_load(size, boxes, load)
    boxes = load_boxes(spec) or boxes
    fill = load_fill(vehicle, spec, capacities, limits) if vehicle else None
    if fill is not None and not fill.is_finite():
        fill = None

    def covers(t):
        if boxes < t.min_boxes:
            return False
        if t.max_boxes is not None and boxes > t.max_boxes:
            return False
        if t.from_fill is not None or t.to_fill is not None:
            if fill is None:
                return False
            if t.from_fill is not None and fill <= t.from_fill:
                return False
            if t.to_fill is not None and fill > t.to_fill:
                return False
        if t.up_to_kg is not None and weight_kg is not None:
            return Decimal(str(weight_kg)) <= t.up_to_kg
        return True

    covering = [t for t in P2PBoxTier.objects.filter(is_active=True) if covers(t)]
    if not covering:
        return None

    quoting = [t for t in covering if t.needs_quote]
    if quoting:
        covering = quoting

    from p2p.models import P2P_MAX_BOXES

    def fill_span(t):
        if t.from_fill is None and t.to_fill is None:
            return Decimal('1')
        return ((t.to_fill if t.to_fill is not None else Decimal('1'))
                - (t.from_fill if t.from_fill is not None else Decimal('0')))

    def count_span(t):
        if t.max_boxes is None:
            return Decimal('1')
        return (Decimal(t.max_boxes - t.min_boxes + 1) / Decimal(P2P_MAX_BOXES))

    return sorted(
        covering,
        key=lambda t: (fill_span(t) * count_span(t),
                       fill_span(t),
                       t.up_to_kg if t.up_to_kg is not None else Decimal('9' * 12),
                       -t.min_boxes),
    )[0]


def quote(from_pt, to_pt, size='', vehicle='', speed='express', boxes=1,
          weight_kg=None, load=None, return_trip=False):
    """Price one journey. The single entry point — nothing else decides a price.

    `from_pt` / `to_pt` are (lat, lng) pairs. Returns a dict carrying the distance
    range shown to the customer, the resolved band and box tier, and either a price or
    a needs_quote flag. Never raises on a missing band: an unpriceable request becomes
    a quote request, which is a worse experience than a price but a far better one
    than an error.

    A job may be several sizes at once — pass `load` as {size: count} instead of the
    size/boxes pair. Everything downstream works on the map: the fractions of the
    vehicle each size takes are summed, so the slabs need no new concept to price a
    mixed load. The band is the one exception, because bands are written per size and a
    mixed load has no single one — it is charged on the largest size present, which
    cannot come out under the same boxes booked on their own.

    `return_trip` asks for the leg back as well. It is the same journey in the opposite
    direction carrying the same load, so it resolves to the identical band and the whole
    job is that leg charged twice — 'price' is the total, and 'leg_price' is one of them.
    Nothing here discounts the second leg: a driver held at the far end for a signature
    is time the fleet cannot sell twice, and any discount on that is an ops decision
    taken as a staff price, not a rule buried in the card.
    """
    km_low, km_high = distance_band(from_pt[0], from_pt[1], to_pt[0], to_pt[1])
    legs = 2 if return_trip else 1

    def result(price=None, band=None, box_tier=None, over_capacity=False,
               wrong_vehicle=None, needs_vehicle=None):
        """One answer, whichever branch reached it.

        Written once rather than five times: every branch below has to carry the same
        keys, and a new one added to only four of them is a KeyError in whichever caller
        happens to hit the fifth. `price` is one leg — the total is worked out here, so
        no branch can price a return trip as a single journey by forgetting to.
        """
        return {
            'km_low': km_low,
            'km_high': km_high,
            'distance_km': Decimal(km_high),
            'price': None if price is None else price * legs,
            'leg_price': price,
            'return_price': price if (price is not None and return_trip) else None,
            'return_trip': bool(return_trip),
            'legs': legs,
            'needs_quote': price is None,
            'band': band,
            'box_tier': box_tier,
            'over_capacity': over_capacity,
            'wrong_vehicle': wrong_vehicle,
            'needs_vehicle': needs_vehicle,
            'ladder_version': LADDER_VERSION,
        }

    spec = as_load(size, boxes, load)
    size = primary_size(spec)
    boxes = load_boxes(spec) or boxes

    # The public calculator refuses to show any price until a size is chosen
    # (p2p-calculator.js tryShowResult), and the quote-only rules are keyed on size —
    # so pricing a sizeless request here would auto-price a load the page itself
    # would have sent to a quote. Vehicle is genuinely optional; size is not.
    if not size:
        return result()

    # Is this the right vehicle for the load? Too small and it will not go in; too big
    # and the customer is buying a pickup for a shoebox. Either way there is no price —
    # there is a different vehicle.
    ok, reason, use_instead = vehicle_verdict(vehicle, load=spec)
    if not ok:
        return result(over_capacity=reason == 'too_big', wrong_vehicle=reason,
                      needs_vehicle=use_instead)

    # "Any vehicle" is priced as the smallest one that can carry the load. For one box
    # that is the blank-vehicle row the card already holds; when the count outgrows it,
    # the price moves up to the vehicle that has to do the job rather than staying on
    # the row a single box would have used.
    priced_as = vehicle
    if not vehicle:
        needed = smallest_vehicle_for(load=spec)
        if needed is not None and needed != smallest_vehicle_for(size, 1):
            priced_as = needed

    band = resolve_band(
        boxes=boxes, size=size, weight_kg=weight_kg,
        vehicle=priced_as, speed=speed, km=km_high,
    )

    if band is None or band.needs_quote:
        return result(band=band)

    # The box tier lands on top of the band price. A tier can also take the whole job
    # to a quote however cheap the band was: eleven boxes is a van being loaded, and
    # nobody should be able to check that out at the one-box price.
    # The fill slabs are a fraction of the vehicle the job actually goes in, so the tier
    # has to be resolved against a real one. priced_as is not enough: it stays blank
    # whenever the blank-vehicle band already covers the load, and a blank vehicle has no
    # ceiling to be a fraction of — which would drop the uplift from every "any vehicle"
    # quote while charging it on the identical job booked as a car.
    tier_vehicle = priced_as or smallest_vehicle_for(load=spec) or ''
    tier = resolve_box_tier(weight_kg=weight_kg, vehicle=tier_vehicle, load=spec)
    if tier is not None and tier.needs_quote:
        return result(band=band, box_tier=tier)

    return result(price=band.price + (tier.uplift if tier is not None else Decimal('0')),
                  band=band, box_tier=tier)


def ladder_for_client():
    """The rate card, shaped for injection into the public calculator.

    The page keeps its instant client-side feedback, but reads these rows instead of
    hardcoded literals — so an ops price change lands on the public page without a
    deploy, and the two can no longer drift.
    """
    rows = []
    for b in P2PRateBand.objects.filter(is_active=True):
        rows.append({
            'min_boxes': b.min_boxes,
            'max_boxes': b.max_boxes,
            'size': b.size,
            'up_to_kg': float(b.up_to_kg) if b.up_to_kg is not None else None,
            'vehicle': b.vehicle,
            'speed': b.speed,
            'up_to_km': float(b.up_to_km) if b.up_to_km is not None else None,
            'price': float(b.price),
            'needs_quote': b.needs_quote,
            'priority': b.priority,
            'specificity': b.specificity,
        })
    return rows


def box_tiers_for_client():
    """The box tiers, shaped for injection into the public calculator.

    Same reason as ladder_for_client: the page has to be able to reach the number the
    server will charge, and it cannot do that from a hardcoded uplift.
    """
    return [
        {
            'min_boxes': t.min_boxes,
            'max_boxes': t.max_boxes,
            'up_to_kg': float(t.up_to_kg) if t.up_to_kg is not None else None,
            # The fill bounds ride along too, or the page would price a full car as an
            # empty one: the slabs are a fraction of the vehicle, not a box count.
            'from_fill': float(t.from_fill) if t.from_fill is not None else None,
            'to_fill': float(t.to_fill) if t.to_fill is not None else None,
            'uplift': float(t.uplift),
            'needs_quote': t.needs_quote,
        }
        for t in P2PBoxTier.objects.filter(is_active=True)
    ]


def _box_limits_for_client():
    """{vehicle: {size: max_boxes}} — _box_limit_rows() reshaped for JSON."""
    nested = {}
    for (vehicle, size), cap in _box_limit_rows().items():
        nested.setdefault(vehicle, {})[size] = cap
    return nested


def capacity_for_client():
    """The vehicle capacities and the size volumes, for the public calculator.

    The page has to be able to work out for itself that three small boxes are not going
    on a motorcycle — it greys the vehicle out rather than offering a price the server
    will refuse. Injected rather than hardcoded, for the same reason as the rate card:
    ops change the fleet, not the JavaScript.
    """
    from p2p.models import (
        P2P_SIZE_CARDS, P2P_SIZE_CHOICES, P2P_VEHICLE_FITS, P2P_VEHICLE_LADDER,
    )

    return {
        'vehicles': {c.vehicle: {'capacity': float(c.capacity_cbm),
                                 'minimum': float(c.min_cbm)}
                     for c in P2PVehicleCapacity.objects.filter(is_active=True)},
        'sizes': {slug: float(card['cbm']) for slug, card in P2P_SIZE_CARDS.items()},
        # The count ceilings, shaped {vehicle: {size: max}} because a JSON key cannot be
        # a pair. A car takes six small boxes and three medium ones, and no single cbm
        # figure says both — so the page has to check the count as well as the volume or
        # it offers a price the server refuses.
        'limits': _box_limits_for_client(),
        # The ladder and the size policy ride along too: "any vehicle" is charged as the
        # smallest one that can carry the load, and the page has to reach the same
        # answer as smallest_vehicle_for() or it quotes a bike's price for a car's job.
        'ladder': list(P2P_VEHICLE_LADDER),
        # Size order, smallest first — the page picks the largest size in a mixed load
        # off this, so "priced as the biggest thing you're sending" cannot drift from
        # primary_size() by hardcoding the order in JavaScript.
        'order': [slug for slug, _ in P2P_SIZE_CHOICES],
        'fits': {size: sorted(v for v in allowed if v)
                 for size, allowed in P2P_VEHICLE_FITS.items()},
    }


def matrix_axes():
    """The chart's axes. The distance columns are read off the card, never written here.

    Two different kinds of dimension, and the difference is the whole point:

    * Size, vehicle and speed each have a picker the customer uses, so the chart shows
      every choice they can make. It has to: a card of catch-all rows names no size at
      all yet still prices all five, and a chart built from the words in the rows would
      go blank while the page kept selling deliveries.
    * Distance has no picker. Nothing but the band rows says where one bracket ends and
      the next begins, so the columns are the distinct ``up_to_km`` ceilings ops have
      actually written, plus one open-ended column when a band has no ceiling. Add a
      50 km band on the page and a 50 km column appears with it.

    The choice lists order and label the rows; the card decides the columns and every
    number in them.
    """
    from p2p.models import (
        P2P_SIZE_CARDS, P2P_SIZE_CHOICES, P2P_SPEED_CHOICES,
        P2P_VEHICLE_CARDS, P2P_VEHICLE_CHOICES,
    )

    # .order_by() first: the model's Meta ordering ends in 'id', and Django puts every
    # ordering column into the SELECT — a .distinct() over that dedupes nothing.
    # Box tiers are the chart's outermost column group: every count a customer can book,
    # priced beside every other, instead of one table per tier behind a picker.
    ceilings = sorted(set(
        P2PRateBand.objects.filter(is_active=True, up_to_km__isnull=False)
        .order_by().values_list('up_to_km', flat=True)
    ))
    km_cols = [(int(c), f'≤ {int(c)} km') for c in ceilings]
    if P2PRateBand.objects.filter(is_active=True, up_to_km__isnull=True).exists():
        # A representative km past the last ceiling. +10 rather than +1 so the probe
        # cannot land inside a ceiling somebody adds a fraction above the current one.
        top = int(ceilings[-1]) if ceilings else 0
        km_cols.append((top + 10, f'{top} km +' if top else 'any distance'))

    tiers = list(P2PBoxTier.objects.filter(is_active=True).order_by('min_boxes', 'up_to_kg', 'id'))
    # The weight ceiling only earns a line in the header when the tiers actually differ
    # on it — four columns all saying "≤ 1000 kg" is noise, not information.
    show_tier_weight = len({t.up_to_kg for t in tiers}) > 1

    return {
        'km': km_cols,
        'tiers': tiers,
        'show_tier_weight': show_tier_weight,
        # "Express — as soon as possible" is the booking form's wording; the column head
        # wants the first half of it.
        'speeds': [(slug, label.split('—')[0].strip()) for slug, label in P2P_SPEED_CHOICES],
        'sizes': [slug for slug, _ in P2P_SIZE_CHOICES],
        'vehicles': [''] + [slug for slug, _ in P2P_VEHICLE_CHOICES],
        'size_cards': P2P_SIZE_CARDS,
        'vehicle_cards': P2P_VEHICLE_CARDS,
    }


def price_matrix(boxes=None, weight_kg=None, axes=None):
    """What the card actually charges, for every combination the card describes.

    Built by running the real resolver rather than re-deriving the numbers, so the
    table is a check on the card and not a restatement of it: a row that never wins,
    or a broad catch-all quietly undercutting a narrow row, shows up here as the wrong
    price instead of staying invisible until a customer finds it.

    The shape of the table is read off the data too — see matrix_axes(). Nothing here
    knows how many box tiers, speed groups or distance columns there are.

    Cells run box tier, then speed, then distance, in the order the template renders
    them. Each carries the tier's uplift already added, because that is the number the
    customer pays. Pass `boxes` to price a single count instead of every tier.

    Returns one entry per size/vehicle pair, plus a 'rare' flag for the pairs nobody
    books (an envelope in a van), which the staff page folds away.
    """
    from p2p.models import is_everyday_pairing

    axes = axes or matrix_axes()
    size_cards = axes['size_cards']
    vehicle_cards = axes['vehicle_cards']

    if not axes['km']:
        return []

    # The card, the capacities and the tiers are read once for the whole table.
    bands = list(P2PRateBand.objects.filter(is_active=True))
    capacities = _capacity_rows()

    # One column group per tier, or just the one the caller asked about. A card with no
    # tiers at all still charts: the bands price on their own and nothing is added.
    limits = _box_limit_rows()
    if boxes is not None:
        groups = [boxes]
    elif axes['tiers']:
        groups = list(axes['tiers'])
    else:
        groups = [1]

    rows = []
    for size in axes['sizes']:
        for vehicle in axes['vehicles']:
            cells = []
            for group in groups:
                # A fill slab is a different box count on every row: "up to half" is 1-3
                # in a car and 1-10 in a van. The probe is the top of the slab for this
                # row's vehicle, so the cell prices the fullest job the slab covers.
                as_vehicle = vehicle or smallest_vehicle_for(size, 1, capacities, limits) or ''
                if isinstance(group, int):
                    probe_boxes = group
                elif group.is_fill_based:
                    probe_boxes = boxes_for_fill(
                        as_vehicle, size, group.to_fill or Decimal('1'), capacities, limits)
                    if probe_boxes is None:
                        probe_boxes = group.min_boxes
                else:
                    probe_boxes = group.min_boxes
                tier = resolve_box_tier(
                    probe_boxes, weight_kg=weight_kg,
                    vehicle=(vehicle
                             or smallest_vehicle_for(size, probe_boxes, capacities, limits)
                             or ''),
                    size=size, capacities=capacities, limits=limits)
                uplift = tier.uplift if tier is not None else Decimal('0')
                tier_quotes = tier is not None and tier.needs_quote
                # Volume first: that many boxes of that size may not go in this vehicle
                # at all, or may be far less than it should be sent out for. Either way
                # no price on the card can make it the right vehicle.
                fits, reason, needs_vehicle = vehicle_verdict(
                    vehicle, size, probe_boxes, capacities, limits)
                # "Any vehicle" is charged as the smallest that can take the load, so the
                # chart has to price it the way quote() does — a count that outgrows the
                # bike is a car's price, not a bike's.
                priced_as = vehicle
                if not vehicle:
                    needed = smallest_vehicle_for(size, probe_boxes, capacities, limits)
                    if needed is not None and needed != smallest_vehicle_for(size, 1, capacities, limits):
                        priced_as = needed
                for speed, _speed_label in axes['speeds']:
                    for km, _km_label in axes['km']:
                        band = None if not fits else resolve_band(
                            boxes=probe_boxes, size=size, weight_kg=weight_kg,
                            vehicle=priced_as, speed=speed, km=km, bands=bands)
                        needs_quote = band is None or band.needs_quote or tier_quotes
                        cells.append({
                            'boxes': probe_boxes,
                            'tier_id': tier.id if tier is not None else None,
                            'speed': speed,
                            'km': km,
                            'band_id': band.id if band else None,
                            'needs_quote': needs_quote,
                            'unmatched': band is None and fits,
                            'over_capacity': not fits,
                            'wrong_vehicle': reason,
                            'needs_vehicle': needs_vehicle,
                            'priced_as': priced_as,
                            'price': None if needs_quote else band.price + uplift,
                        })
            card = size_cards.get(size, {})
            rows.append({
                'size': size,
                'size_tag': card.get('tag', size.upper()),
                'size_name': card.get('name', size),
                'size_weight': card.get('weight', ''),
                'vehicle': vehicle,
                'vehicle_name': vehicle_cards.get(vehicle, {}).get('name', vehicle),
                # Every pair is priced and every pair stays in the list — 'rare' only
                # tells the template which ones to fold away by default. An envelope in
                # a van is bookable, so its price still has to be visible on request.
                'rare': not is_everyday_pairing(size, vehicle),
                'cells': cells,
            })
    return rows
