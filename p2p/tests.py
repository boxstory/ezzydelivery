# Purpose: Lock the two signal behaviours the whole P2P flow depends on, plus rate-card resolution.
# Used by: python manage.py test p2p
# Notes: The first-mile leg is scheduled via transaction.on_commit, so it needs
#        captureOnCommitCallbacks — NOT TransactionTestCase, which flushes every table on teardown
#        and would wipe the AutoTriggerConfig rows that core's migrations seed and that crm/ and
#        workforce/ tests depend on.

from decimal import Decimal

from django.test import TestCase

from business.models import Business, PickupLocation
from delivery.models import DeliveryTask, PickupTask
from orders.models import Order
from orders.status_actions import apply_ready_and_publish
from p2p.models import (
    P2PBooking, P2PBoxTier, P2PRateBand, P2PVehicleBoxLimit, P2PVehicleCapacity,
    P2P_MAX_BOXES, P2P_MAX_KG,
    P2P_SIZE_CHOICES, P2P_VEHICLE_CHOICES, is_everyday_pairing,
)
from p2p.pricing import (
    QATAR_BBOX, box_tiers_for_client, boxes_for_fill, capacity_for_client,
    distance_band, load_cbm, load_fill, matrix_axes, max_boxes_for, max_journey_km,
    price_matrix, primary_size, quote, resolve_band, resolve_box_tier,
    size_allows_weight, smallest_size_for, smallest_vehicle_for, vehicle_can_carry,
    vehicle_verdict,
)

WEST_BAY = (25.3272, 51.5310)
AL_WAKRAH = (25.1719, 51.5989)


def house_business():
    """The EZP2P system business, created by migration in production.

    get_or_create rather than get so these tests do not depend on migration state
    surviving whatever else ran first. The defaults mirror
    business/migrations/0031 exactly — if that migration's values change, this must
    follow or the tests stop proving anything.
    """
    business, _ = Business.objects.get_or_create(
        business_code='EZP2P',
        defaults={
            'business_id': 999999,
            'business_name': 'EzzyDelivery P2P',
            'business_status': 'active',
            'pickup_task_enabled': True,
            'pickup_disposition_default': 'self_deliver',
            'pickup_mode_default': 'public_pool',
            'fulfillment_service_enabled': False,
        },
    )
    return business


def make_pickup(business, status='active'):
    return PickupLocation.objects.create(
        business=business,
        pickup_location_title='Test sender — West Bay',
        locality='West Bay',
        pickup_zone_no=61, pickup_street_no=850, pickup_building_no=12,
        pickup_lat=Decimal('25.327200000000000'),
        pickup_lon=Decimal('51.531000000000000'),
        pickup_status=status,
        is_default=False, is_fulfilment_center=False,
        contact_name='Test Sender', contact_phone='97455512345',
        is_p2p=True,
    )


def make_order(business, pickup=None, status='to_review', code='P2P-TEST1'):
    return Order.objects.create(
        business=business,
        client_order_code=code,
        pickup_location=pickup,
        order_type='pick_and_drop',
        delivery_speed='express',
        order_status=status,
        task_status='new_order',
        customer_name='Receiver', customer_phone='97455598765',
        customer_address='Al Wakrah, Zone 90, Street 12, Building 3',
        dl_zone=90, dl_street=12, dl_building=3,
        latitude=Decimal('25.171900000000000'),
        longitude=Decimal('51.598900000000000'),
        coords_accuracy='by_customer',
        dl_included=True, dl_amount=Decimal('25.00'),
        package_qty=1, package_weight_kg=Decimal('2.50'),
        platform='public_link',
    )


class PublishOnCreateLockTests(TestCase):
    """G2: creating an Order already at 'publish' must NOT produce a DeliveryTask.

    The publish branch in orders/signals.py sits inside `if not created:`, so a single
    jump skips it entirely — along with stock reservation and the pick list. This is
    why order creation must land on 'to_review' and go live through
    apply_ready_and_publish(). If someone ever "simplifies" that away, this fails.
    """

    def test_created_at_publish_makes_no_delivery_task(self):
        order = make_order(house_business(), make_pickup(house_business()),
                           status='publish', code='P2P-PUBCREATE')
        self.assertEqual(
            DeliveryTask.objects.filter(order=order).count(), 0,
            'Creating an order at publish produced a delivery task — the signal '
            'behaviour this plan is built on has changed.')

    def test_apply_ready_and_publish_makes_exactly_one(self):
        order = make_order(house_business(), make_pickup(house_business()),
                           status='to_review', code='P2P-READYPUB')
        apply_ready_and_publish(order)
        order.refresh_from_db()
        self.assertEqual(order.order_status, 'publish')
        self.assertEqual(DeliveryTask.objects.filter(order=order).count(), 1)


class PendingPickupGateTests(TestCase):
    """G3: a 'pending' pickup location is what keeps an unconfirmed booking off the road.

    The first-mile gate refuses a pickup location that is not active, so no driver can
    see the job until the customer clicks the confirm link. The confirm flips the
    location to active and the order to ready_to_pickup, and the existing hook opens
    the leg. This is the entire no-premature-dispatch mechanism — no extra check.
    """

    def test_pending_location_opens_no_pickup_task(self):
        with self.captureOnCommitCallbacks(execute=True):
            pickup = make_pickup(house_business(), status='pending')
            order = make_order(house_business(), pickup, code='P2P-PENDING')
        self.assertEqual(
            PickupTask.objects.filter(order=order).count(), 0,
            'A pending pickup location produced a pickup task — an unconfirmed '
            'booking would be visible to drivers.')

    def test_confirm_opens_exactly_one_self_deliver_leg(self):
        with self.captureOnCommitCallbacks(execute=True):
            pickup = make_pickup(house_business(), status='pending')
            order = make_order(house_business(), pickup, code='P2P-CONFIRM')
        self.assertEqual(PickupTask.objects.filter(order=order).count(), 0)

        # What the customer's confirm link does, in one transaction.
        with self.captureOnCommitCallbacks(execute=True):
            pickup.pickup_status = 'active'
            pickup.save(update_fields=['pickup_status'])
            order.order_status = 'ready_to_pickup'
            order.save()

        tasks = PickupTask.objects.filter(order=order)
        self.assertEqual(tasks.count(), 1, 'Confirming did not open the first-mile leg.')
        self.assertEqual(tasks.first().disposition, 'self_deliver')


# The rate card as the public calculator prices it today, written out independently
# of p2p/migrations/0002 on purpose: a test that imports the migration's own constant
# proves only that a list equals itself. These literals are transcribed from
# webpages/static/webpages/js/p2p-calculator.js, which is the thing that must not drift.
JS_LADDER = [(10, 25), (20, 35), (30, 40), (None, 55)]
JS_QUOTE_SIZES = ['m', 'l', 'xl']
JS_QUOTE_VEHICLES = ['suv', 'van', 'truck']


class RateCardResolutionTests(TestCase):
    """The card must reproduce today's public pricing, and resolve predictably.

    Builds its own rows rather than relying on the seed migration, so the result
    never depends on which test class ran first.
    """

    @classmethod
    def setUpTestData(cls):
        P2PRateBand.objects.all().delete()
        for km, price in JS_LADDER:
            P2PRateBand.objects.create(min_boxes=1, up_to_km=km, price=Decimal(price))
        for size in JS_QUOTE_SIZES:
            P2PRateBand.objects.create(min_boxes=1, size=size, needs_quote=True, priority=10)
        for vehicle in JS_QUOTE_VEHICLES:
            P2PRateBand.objects.create(min_boxes=1, vehicle=vehicle, needs_quote=True, priority=10)

    def test_seed_reproduces_the_js_ladder(self):
        for km, expected in [(5, 25), (10, 25), (15, 35), (20, 35),
                             (25, 40), (30, 40), (31, 55), (120, 55)]:
            band = resolve_band(size='s', vehicle='bike', speed='express', km=km)
            self.assertIsNotNone(band, f'No band matched {km}km')
            self.assertFalse(band.needs_quote)
            self.assertEqual(band.price, Decimal(expected), f'{km}km priced wrong')

    def test_bulky_sizes_and_big_vehicles_need_a_quote(self):
        for size in ['m', 'l', 'xl']:
            band = resolve_band(size=size, vehicle='bike', km=5)
            self.assertTrue(band.needs_quote, f'size {size} should need a quote')
        for vehicle in ['suv', 'van', 'truck']:
            band = resolve_band(size='s', vehicle=vehicle, km=5)
            self.assertTrue(band.needs_quote, f'vehicle {vehicle} should need a quote')

    def test_small_on_bike_or_car_is_auto_priced(self):
        for size in ['xs', 's']:
            for vehicle in ['bike', 'car']:
                band = resolve_band(size=size, vehicle=vehicle, km=5)
                self.assertFalse(band.needs_quote)

    def test_motorcycle_card_matches_the_bike_slug(self):
        """F2: the bike card's label is 'Motorcycle'; rules must key on the slug."""
        band = P2PRateBand.objects.create(
            min_boxes=1, size='s', vehicle='bike', up_to_km=10,
            price=Decimal('99.00'), priority=50)
        got = resolve_band(size='s', vehicle='bike', km=5)
        self.assertEqual(got, band)

    def test_more_specific_row_wins(self):
        specific = P2PRateBand.objects.create(
            min_boxes=1, size='s', vehicle='car', speed='express', up_to_km=10,
            price=Decimal('77.00'))
        got = resolve_band(size='s', vehicle='car', speed='express', km=5)
        self.assertEqual(got, specific, 'A row with more constraints set should win')

    def test_priority_overrides_specificity(self):
        P2PRateBand.objects.create(
            min_boxes=1, size='s', vehicle='car', speed='express', up_to_km=10,
            price=Decimal('77.00'))
        override = P2PRateBand.objects.create(
            min_boxes=1, up_to_km=10, price=Decimal('12.00'), priority=99)
        got = resolve_band(size='s', vehicle='car', speed='express', km=5)
        self.assertEqual(got, override, 'Priority should beat a more specific row')

    def test_box_count_range(self):
        bulk = P2PRateBand.objects.create(
            min_boxes=4, max_boxes=10, size='s', up_to_km=10,
            price=Decimal('60.00'), priority=5)
        self.assertEqual(resolve_band(boxes=5, size='s', vehicle='bike', km=5), bulk)
        self.assertNotEqual(resolve_band(boxes=2, size='s', vehicle='bike', km=5), bulk)


class SizeWeightContradictionTests(TestCase):
    """Size and kg are both customer inputs and can disagree — that must be caught."""

    def test_weight_inside_the_size_bracket_is_fine(self):
        self.assertTrue(size_allows_weight('s', Decimal('2.5')))
        self.assertTrue(size_allows_weight('m', Decimal('10')))

    def test_weight_over_the_bracket_is_rejected(self):
        self.assertFalse(size_allows_weight('s', Decimal('8')))
        self.assertFalse(size_allows_weight('xs', Decimal('1')))

    def test_xl_is_open_ended(self):
        self.assertTrue(size_allows_weight('xl', Decimal('400')))

    def test_suggests_the_size_that_fits(self):
        self.assertEqual(smallest_size_for(Decimal('8')), 'm')
        self.assertEqual(smallest_size_for(Decimal('0.3')), 'xs')
        self.assertEqual(smallest_size_for(Decimal('40')), 'xl')


class BoxTierTests(TestCase):
    """Boxes are the fifth pricing dimension, added on top of the resolved band."""

    @classmethod
    def setUpTestData(cls):
        P2PRateBand.objects.all().delete()
        P2PRateBand.objects.create(min_boxes=1, up_to_km=None, price=Decimal('40'))
        P2PBoxTier.objects.all().delete()
        # No capacities and no counts: this suite is about what a tier adds, and the
        # rules for which vehicle a load belongs in — volume and box count alike — have
        # their own tests. The seeded car counts would otherwise refuse the ten- and
        # twenty-box cases below before any tier was consulted.
        P2PVehicleCapacity.objects.all().delete()
        P2PVehicleBoxLimit.objects.all().delete()
        P2PBoxTier.objects.create(min_boxes=1, max_boxes=1, uplift=Decimal('0'))
        P2PBoxTier.objects.create(min_boxes=2, max_boxes=3, uplift=Decimal('10'))
        P2PBoxTier.objects.create(min_boxes=4, max_boxes=10, uplift=Decimal('25'))
        P2PBoxTier.objects.create(min_boxes=11, max_boxes=None, needs_quote=True)

    def _price(self, boxes):
        # A car, not a bike: ten small boxes are 0.15 cbm and a motorcycle box is 0.027,
        # so a bike here would be refused on volume before any tier was consulted.
        return quote(WEST_BAY, AL_WAKRAH, size='s', vehicle='car',
                     speed='express', boxes=boxes)

    def test_one_box_is_unchanged_and_extra_boxes_add_the_uplift(self):
        self.assertEqual(self._price(1)['price'], Decimal('40'))
        self.assertEqual(self._price(2)['price'], Decimal('50'))
        self.assertEqual(self._price(3)['price'], Decimal('50'))
        self.assertEqual(self._price(4)['price'], Decimal('65'))
        self.assertEqual(self._price(10)['price'], Decimal('65'))

    def test_a_quote_tier_beats_a_priced_band(self):
        """Eleven boxes is a van being loaded — it must not check out at the one-box
        price just because the band that matched had one."""
        result = self._price(11)
        self.assertTrue(result['needs_quote'])
        self.assertIsNone(result['price'])
        self.assertIsNotNone(result['band'], 'The band still resolved; the tier overrode it')

    def test_the_narrowest_covering_tier_wins(self):
        """An open-ended tier starting at 1 must not swallow the specific 1-box row."""
        P2PBoxTier.objects.create(min_boxes=1, max_boxes=None, uplift=Decimal('99'))
        self.assertEqual(resolve_box_tier(1).max_boxes, 1)
        self.assertEqual(self._price(1)['price'], Decimal('40'))

    def test_no_tier_at_all_prices_exactly_as_before(self):
        """The tiers are additive, so a card with none of them is the old card."""
        P2PBoxTier.objects.all().delete()
        for boxes in (1, 5, 20):
            self.assertEqual(self._price(boxes)['price'], Decimal('40'))

    def test_the_client_payload_carries_what_the_calculator_needs(self):
        """The public page adds the uplift itself; it can only match the server if the
        tiers reach it with every field the resolver uses — the fill bounds included,
        or the page prices a full car as an empty one."""
        rows = box_tiers_for_client()
        self.assertEqual(len(rows), 4)
        for row in rows:
            self.assertEqual(set(row),
                             {'min_boxes', 'max_boxes', 'from_fill', 'to_fill',
                              'up_to_kg', 'uplift', 'needs_quote'})
        self.assertIn({'min_boxes': 2, 'max_boxes': 3, 'up_to_kg': None,
                       'from_fill': None, 'to_fill': None,
                       'uplift': 10.0, 'needs_quote': False}, rows)


class FillTierTests(TestCase):
    """A slab written as a fraction means the same thing in every vehicle.

    Six medium boxes fill a car and a fifth of a van. Written as counts, one "4-10, +25"
    row meant a full car and a nearly empty van, and three of the four old slabs were
    dead on a bike. Written as halves, two rows read 1-3 and 4-6 in a car and 1-10 and
    11-20 in a van, off the same two rows.
    """

    @classmethod
    def setUpTestData(cls):
        P2PRateBand.objects.all().delete()
        for size in ('xs', 's', 'm', 'l'):
            for vehicle in ('', 'bike', 'car', 'suv', 'van'):
                P2PRateBand.objects.create(
                    min_boxes=1, max_boxes=20, size=size, vehicle=vehicle,
                    up_to_km=300, price=Decimal('40'), priority=20)

    def test_the_seeded_slabs_are_halves_plus_the_two_absolute_rules(self):
        labels = [t.label for t in P2PBoxTier.objects.filter(is_active=True).order_by('id')]
        self.assertEqual(labels,
                         ['1 box', 'up to 50% full', 'over 50% full', '11\u201320 boxes'])

    def test_a_half_slab_is_three_boxes_in_a_car_and_ten_in_a_van(self):
        """The point of the whole design: one row, two meanings, no second row."""
        self.assertEqual(max_boxes_for('car', 'm'), 6)
        self.assertEqual(boxes_for_fill('car', 'm', Decimal('0.5')), 3)
        self.assertEqual(max_boxes_for('van', 'm'), 20)
        self.assertEqual(boxes_for_fill('van', 'm', Decimal('0.5')), 10)

    def test_the_car_slabs_are_one_to_three_and_four_to_six(self):
        for boxes in (2, 3):
            self.assertEqual(
                resolve_box_tier(boxes, vehicle='car', size='m').label, 'up to 50% full')
        for boxes in (4, 5, 6):
            self.assertEqual(
                resolve_box_tier(boxes, vehicle='car', size='m').label, 'over 50% full')

    def test_the_same_two_rows_read_differently_in_a_van(self):
        for boxes in (2, 10):
            self.assertEqual(
                resolve_box_tier(boxes, vehicle='van', size='m').label, 'up to 50% full')
        self.assertEqual(
            resolve_box_tier(11, vehicle='van', size='m').label, '11\u201320 boxes')

    def test_one_box_is_the_band_price_even_when_it_fills_the_vehicle(self):
        """A bike is 100% full at one small box. The commonest booking on the platform
        must not be charged as a full vehicle, so the 1-box row beats the fill slab."""
        self.assertEqual(max_boxes_for('bike', 's'), 1)
        tier = resolve_box_tier(1, vehicle='bike', size='s')
        self.assertEqual(tier.label, '1 box')
        self.assertEqual(tier.uplift, Decimal('0'))

    def test_needs_quote_beats_a_cheaper_covering_slab(self):
        """Eleven boxes in a van is 55% full, so a priced slab covers it too. The job
        still goes to a human — a cheaper covering row must not price it."""
        tier = resolve_box_tier(11, vehicle='van', size='m')
        self.assertTrue(tier.needs_quote)

    def test_a_fill_slab_is_skipped_when_there_is_no_ceiling_to_be_a_fraction_of(self):
        """No vehicle, no fraction. The absolute rows still apply."""
        self.assertEqual(resolve_box_tier(1, vehicle='', size='m').label, '1 box')
        self.assertTrue(resolve_box_tier(11, vehicle='', size='m').needs_quote)

    def test_any_vehicle_is_slabbed_against_the_vehicle_it_is_priced_as(self):
        """The bug this caught: priced_as stays blank when the blank-vehicle band already
        covers the load, which dropped the uplift from every 'any vehicle' quote while
        charging it on the identical job booked as a car."""
        as_car = quote(WEST_BAY, AL_WAKRAH, size='m', vehicle='car', boxes=5)
        as_any = quote(WEST_BAY, AL_WAKRAH, size='m', vehicle='', boxes=5)
        self.assertEqual(as_any['price'], as_car['price'])
        self.assertIsNotNone(as_any['box_tier'])


class MixedLoadTests(TestCase):
    """A job can be several sizes at once — two small and one medium.

    The fill fractions add, which is the whole reason this was cheap to build: three
    medium boxes and three small ones are half a car each, so together they are exactly
    one full car, and the slabs already take a fraction.
    """

    @classmethod
    def setUpTestData(cls):
        P2PRateBand.objects.all().delete()
        for size in ('xs', 's', 'm', 'l'):
            for vehicle in ('', 'bike', 'car', 'suv', 'van'):
                P2PRateBand.objects.create(
                    min_boxes=1, max_boxes=20, size=size, vehicle=vehicle,
                    up_to_km=300, price=Decimal('40'), priority=20)

    def test_fill_is_the_sum_of_the_parts(self):
        self.assertEqual(load_fill('car', {'m': 3, 's': 3}), Decimal(1))
        self.assertEqual(load_fill('car', {'m': 6}), Decimal(1))
        self.assertGreater(load_fill('car', {'m': 3, 's': 4}), Decimal(1))

    def test_a_mix_that_overfills_steps_up_to_the_next_vehicle(self):
        self.assertEqual(smallest_vehicle_for(load={'m': 3, 's': 3}), 'car')
        self.assertEqual(smallest_vehicle_for(load={'m': 3, 's': 4}), 'suv')

    def test_one_medium_box_keeps_the_whole_job_off_a_motorcycle(self):
        """A vehicle has to be allowed for every size in the mix, not just one."""
        self.assertEqual(smallest_vehicle_for(load={'xs': 1}), 'bike')
        self.assertEqual(smallest_vehicle_for(load={'xs': 1, 'm': 1}), 'car')

    def test_a_mixed_load_is_priced_on_the_largest_size_in_it(self):
        self.assertEqual(primary_size({'s': 2, 'm': 1}), 'm')
        self.assertEqual(primary_size({'xs': 9, 'l': 1}), 'l')
        priced = quote(WEST_BAY, AL_WAKRAH, vehicle='car', load={'s': 2, 'm': 1})
        self.assertEqual(priced['band'].size, 'm')

    def test_a_mix_cannot_come_out_under_the_same_boxes_on_their_own(self):
        """Three medium and three small fill a car exactly, the same as six medium, so
        the slab and therefore the price are the same. It must not be cheaper."""
        mixed = quote(WEST_BAY, AL_WAKRAH, vehicle='car', load={'m': 3, 's': 3})
        alone = quote(WEST_BAY, AL_WAKRAH, vehicle='car', size='m', boxes=6)
        self.assertEqual(mixed['price'], alone['price'])

    def test_the_verdict_names_the_vehicle_a_mix_needs(self):
        ok, reason, use = vehicle_verdict('car', load={'m': 3, 's': 4})
        self.assertFalse(ok)
        self.assertEqual(reason, 'too_big')
        self.assertEqual(use, 'suv')

    def test_a_single_size_job_still_prices_exactly_as_before(self):
        """The old pair and the new map are two ways of saying the same thing."""
        pair = quote(WEST_BAY, AL_WAKRAH, vehicle='car', size='m', boxes=4)
        mapped = quote(WEST_BAY, AL_WAKRAH, vehicle='car', load={'m': 4})
        self.assertEqual(pair['price'], mapped['price'])
        self.assertEqual(pair['band'].id, mapped['band'].id)

    def test_the_booking_keeps_its_lines_and_still_answers_as_one_size(self):
        from p2p.services import set_booking_lines
        booking = P2PBooking.objects.create(
            token='mixtest', status='draft', from_label='A', to_label='B',
            from_lat=Decimal('25.3'), from_lng=Decimal('51.5'),
            to_lat=Decimal('25.2'), to_lng=Decimal('51.6'),
            distance_km=Decimal('10'), size='m', box_count=3)
        set_booking_lines(booking, {'s': 2, 'm': 1})
        self.assertEqual(booking.load_map(), {'s': 2, 'm': 1})
        self.assertIn('Small Box', booking.load_label)

        # Cleared back to a single-size job, the scalar pair still answers for it.
        set_booking_lines(booking, {})
        self.assertEqual(booking.load_map(), {'m': 3})


class VehicleBoxLimitTests(TestCase):
    """A car holds 0.4 cbm — nine small boxes of arithmetic. Ops counted six.

    The point of the table is that six small boxes and three medium ones cannot both be
    a cubic-metre ceiling: 6 x 0.015 = 0.090 and 3 x 0.047 = 0.141, so any capacity that
    allows the three allows nine of the six. The count says what the volume cannot.
    """

    @classmethod
    def setUpTestData(cls):
        P2PRateBand.objects.all().delete()
        for size in ('xs', 's', 'm', 'l'):
            for vehicle in ('', 'bike', 'car', 'suv', 'van'):
                P2PRateBand.objects.create(
                    min_boxes=1, max_boxes=20, size=size, vehicle=vehicle,
                    up_to_km=300, price=Decimal('40'), priority=20)
        P2PBoxTier.objects.all().delete()

    def test_the_seeded_car_counts_are_the_ones_ops_measured(self):
        self.assertEqual(
            {(r.vehicle, r.size): r.max_boxes
             for r in P2PVehicleBoxLimit.objects.filter(is_active=True)},
            {('car', 'm'): 6, ('car', 's'): 6})

    def test_a_count_stops_a_load_the_volume_rule_would_allow(self):
        """0.105 cbm is a quarter of what the car holds, and it is still seven boxes."""
        self.assertTrue(vehicle_can_carry('car', 's', 6))
        self.assertFalse(vehicle_can_carry('car', 's', 7))
        ok, reason, use = vehicle_verdict('car', 's', 7)
        self.assertFalse(ok)
        self.assertEqual(reason, 'too_big')
        self.assertEqual(use, 'suv')

    def test_the_count_stands_where_the_volume_rule_would_allow_more(self):
        """Six medium boxes are 0.282 cbm in a car that holds 0.400 — the volume rule
        would take eight. The count is what stops it at six."""
        self.assertTrue(vehicle_can_carry('car', 'm', 6))
        self.assertFalse(vehicle_can_carry('car', 'm', 7))
        self.assertTrue(vehicle_can_carry('car', 's', 6))
        self.assertFalse(vehicle_can_carry('car', 's', 7))

    def test_a_pairing_with_no_row_is_left_to_the_volume_rule(self):
        """The van is uncounted, so it behaves exactly as it did before this table."""
        self.assertTrue(vehicle_can_carry('van', 's', 20))
        self.assertTrue(vehicle_can_carry('van', 'm', 20))

    def test_switching_a_count_off_leaves_the_volume_rule_alone(self):
        P2PVehicleBoxLimit.objects.filter(vehicle='car', size='s').update(is_active=False)
        self.assertTrue(vehicle_can_carry('car', 's', 7))
        self.assertTrue(vehicle_can_carry('car', 's', 20))

    def test_a_blank_count_is_no_limit(self):
        P2PVehicleBoxLimit.objects.filter(vehicle='car', size='s').update(max_boxes=None)
        self.assertTrue(vehicle_can_carry('car', 's', 20))

    def test_the_load_steps_up_to_the_vehicle_that_has_the_count(self):
        self.assertEqual(smallest_vehicle_for('s', 6), 'car')
        self.assertEqual(smallest_vehicle_for('s', 7), 'suv')
        self.assertEqual(smallest_vehicle_for('m', 6), 'car')
        self.assertEqual(smallest_vehicle_for('m', 7), 'suv')

    def test_a_count_never_widens_the_size_policy(self):
        """Room is necessary, not sufficient — the same rule the cbm ceiling obeys."""
        P2PVehicleBoxLimit.objects.create(vehicle='bike', size='m', max_boxes=20)
        self.assertNotEqual(smallest_vehicle_for('m', 1), 'bike')

    def test_the_stepped_up_vehicle_is_not_then_refused_as_oversized(self):
        """The SUV asks for 1.0 cbm and seven small boxes are 0.105. It still gets the
        job, because the count has just proved nothing smaller can take it."""
        P2PVehicleCapacity.objects.filter(vehicle='suv').update(min_cbm=Decimal('1'))
        ok, reason, _use = vehicle_verdict('suv', 's', 7)
        self.assertTrue(ok, f'refused as {reason}')


class VehicleCapacityTests(TestCase):
    """A bike's box is 0.027 cbm. Three small boxes are 0.045 and do not go in it,
    whatever the rate card is willing to charge."""

    @classmethod
    def setUpTestData(cls):
        P2PRateBand.objects.all().delete()
        for size in ('xs', 's', 'm', 'l'):
            for vehicle in ('', 'bike', 'car', 'suv', 'van'):
                P2PRateBand.objects.create(
                    min_boxes=1, max_boxes=20, size=size, vehicle=vehicle,
                    up_to_km=300, price=Decimal('40'), priority=20)
        P2PBoxTier.objects.all().delete()

    def test_one_small_box_goes_on_a_bike_and_two_do_not(self):
        self.assertTrue(vehicle_can_carry('bike', 's', 1))
        self.assertFalse(vehicle_can_carry('bike', 's', 2))
        self.assertTrue(vehicle_can_carry('car', 's', 2))

    def test_the_load_steps_up_to_the_vehicle_that_fits(self):
        self.assertEqual(smallest_vehicle_for('s', 1), 'bike')
        self.assertEqual(smallest_vehicle_for('s', 2), 'car')
        self.assertEqual(smallest_vehicle_for('s', 40), 'suv')

    def test_capacity_never_widens_the_size_policy(self):
        """Room is necessary, not sufficient: a medium box is not going on a motorcycle
        even if someone types a warehouse into the bike's capacity."""
        P2PVehicleCapacity.objects.filter(vehicle='bike').update(capacity_cbm=Decimal('99'))
        self.assertEqual(smallest_vehicle_for('m', 1), 'car')

    def test_a_vehicle_that_cannot_take_it_is_not_priced_at_any_distance(self):
        result = quote(WEST_BAY, AL_WAKRAH, size='s', vehicle='bike', boxes=3)
        self.assertTrue(result['needs_quote'])
        self.assertIsNone(result['price'])
        self.assertTrue(result['over_capacity'])
        self.assertEqual(result['needs_vehicle'], 'car')

    def test_any_vehicle_is_charged_as_the_one_that_has_to_do_the_job(self):
        """One box is the blank-vehicle row; three is a car, and the price says so."""
        P2PRateBand.objects.filter(size='s', vehicle='car').update(price=Decimal('60'))
        self.assertEqual(quote(WEST_BAY, AL_WAKRAH, size='s', boxes=1)['price'],
                         Decimal('40'))
        self.assertEqual(quote(WEST_BAY, AL_WAKRAH, size='s', boxes=3)['price'],
                         Decimal('60'))

    def test_switching_a_capacity_off_leaves_that_vehicle_unlimited(self):
        P2PVehicleCapacity.objects.filter(vehicle='bike').update(is_active=False)
        self.assertTrue(vehicle_can_carry('bike', 's', 20))
        self.assertFalse(quote(WEST_BAY, AL_WAKRAH, size='s', vehicle='bike',
                               boxes=20)['over_capacity'])

    def test_the_chart_says_which_vehicle_the_load_needs(self):
        P2PBoxTier.objects.create(min_boxes=1, max_boxes=1, uplift=Decimal('0'))
        P2PBoxTier.objects.create(min_boxes=2, max_boxes=10, uplift=Decimal('0'))
        row = [r for r in price_matrix() if r['size'] == 's' and r['vehicle'] == 'bike'][0]
        one_box = [c for c in row['cells'] if c['boxes'] == 1]
        many = [c for c in row['cells'] if c['boxes'] == 2]
        self.assertTrue(all(c['price'] is not None for c in one_box))
        self.assertTrue(all(c['over_capacity'] for c in many))
        self.assertTrue(all(c['needs_vehicle'] == 'car' for c in many))
        # A cell nothing can carry is not the same as a hole in the card.
        self.assertFalse(any(c['unmatched'] for c in many))

    def test_a_vehicle_is_wrong_when_it_is_more_than_the_job_needs(self):
        """A pickup is not sent out for three small boxes when a car can take them."""
        P2PVehicleCapacity.objects.filter(vehicle='suv').update(min_cbm=Decimal('1'))
        ok, reason, use = vehicle_verdict('suv', 's', 3)
        self.assertFalse(ok)
        self.assertEqual(reason, 'oversized')
        self.assertEqual(use, 'car')

    def test_a_minimum_never_strands_a_load_between_two_vehicles(self):
        """0.54 cbm is under the pickup's cubic metre, but no car holds it — so the
        pickup takes it. A floor that could refuse a load nothing smaller can carry
        would leave the customer with no vehicle at all."""
        P2PVehicleCapacity.objects.filter(vehicle='suv').update(min_cbm=Decimal('1'))
        self.assertEqual(load_cbm('l', 5), Decimal('0.540'))
        ok, _reason, _use = vehicle_verdict('suv', 'l', 5)
        self.assertTrue(ok)
        self.assertEqual(smallest_vehicle_for('l', 5), 'suv')

    def test_every_vehicle_can_carry_a_floor_not_just_the_pickup(self):
        P2PVehicleCapacity.objects.filter(vehicle='car').update(min_cbm=Decimal('0.027'))
        ok, reason, use = vehicle_verdict('car', 's', 1)   # 0.015, a bike's job
        self.assertFalse(ok)
        self.assertEqual((reason, use), ('oversized', 'bike'))
        self.assertTrue(vehicle_verdict('car', 's', 3)[0])  # 0.045, the car's job

    def test_a_zero_floor_means_send_it_out_for_anything(self):
        P2PVehicleCapacity.objects.filter(vehicle='suv').update(min_cbm=Decimal('0'))
        self.assertTrue(vehicle_verdict('suv', 's', 1)[0])

    def test_the_chart_redirects_an_oversized_pairing_too(self):
        P2PVehicleCapacity.objects.filter(vehicle='suv').update(min_cbm=Decimal('1'))
        P2PBoxTier.objects.create(min_boxes=1, max_boxes=20, uplift=Decimal('0'))
        row = [r for r in price_matrix() if r['size'] == 's' and r['vehicle'] == 'suv'][0]
        self.assertTrue(all(c['price'] is None for c in row['cells']))
        self.assertTrue(all(c['wrong_vehicle'] == 'oversized' for c in row['cells']))
        self.assertTrue(all(c['needs_vehicle'] == 'bike' for c in row['cells']))

    def test_the_booking_form_names_the_vehicle_that_fits(self):
        from p2p.forms import BookingDetailsForm
        form = BookingDetailsForm(data={
            'booker_role': 'sender', 'fee_payer': 'sender',
            'sender_name': 'A', 'sender_phone': '55512345',
            'customer_name': 'B', 'customer_phone': '55598765',
            'customer_address': 'Al Wakrah', 'size': 's', 'vehicle': 'bike',
            'box_count': '3', 'speed': 'express', 'cod_amount': '0',
        })
        self.assertFalse(form.is_valid())
        self.assertIn('vehicle', form.errors)
        self.assertIn('Car', form.errors['vehicle'][0])

    def test_the_client_payload_can_reach_the_same_answer(self):
        """The page greys a vehicle out itself, so it needs the same three inputs."""
        payload = capacity_for_client()
        self.assertEqual(payload['vehicles']['bike']['capacity'], 0.027)
        self.assertEqual(payload['vehicles']['suv']['minimum'], 1.0)
        self.assertEqual(payload['sizes']['s'], 0.015)
        self.assertEqual(payload['ladder'][0], 'bike')
        self.assertNotIn('bike', payload['fits']['m'])


class BulkyItemTests(TestCase):
    """Bulky rides on a pickup or bigger, and a motorcycle or a car is still refused it.

    Until the card was backfilled (2026-09-10) no vehicle carried a bulky item at all and
    every combination was a staff quote. What has not changed is the invariant underneath:
    the public calculator mirrors `vehicle_verdict` to decide which vehicle cards to grey
    out, and it once read the verdict as "which vehicle to use instead" — so a refusal
    with no alternative to name looked exactly like a clean bill, and every card stayed
    lit for a 25 kg+ item. The last test here pins that apart.
    """

    @classmethod
    def setUpTestData(cls):
        P2PRateBand.objects.all().delete()
        P2PBoxTier.objects.all().delete()
        # The shape fill_p2p_rate_card writes: priced where the size policy allows the
        # vehicle, a quote row where it does not.
        for vehicle in ('', 'suv', 'van', 'truck'):
            P2PRateBand.objects.create(
                min_boxes=1, max_boxes=20, size='xl', vehicle=vehicle,
                up_to_km=300, price=Decimal('130'), priority=20)
        for vehicle in ('bike', 'car'):
            P2PRateBand.objects.create(
                min_boxes=1, max_boxes=20, size='xl', vehicle=vehicle,
                up_to_km=300, price=Decimal('0'), needs_quote=True, priority=20)

    def test_a_bulky_item_rides_on_a_pickup(self):
        self.assertEqual(smallest_vehicle_for('xl', 1), 'suv')

    def test_a_motorcycle_is_still_refused_a_bulky_item(self):
        ok, reason, needed = vehicle_verdict('bike', load={'xl': 1})
        self.assertFalse(ok)
        self.assertEqual(reason, 'too_big')
        self.assertEqual(needed, 'suv')

    def test_bulky_is_priced_on_a_pickup_and_quoted_in_a_car(self):
        priced = quote(WEST_BAY, AL_WAKRAH, size='xl', vehicle='suv')
        self.assertFalse(priced['needs_quote'])
        self.assertEqual(priced['price'], Decimal('130'))
        # A car is not a bulky vehicle, so it stays a conversation with a human.
        self.assertTrue(quote(WEST_BAY, AL_WAKRAH, size='xl', vehicle='car')['needs_quote'])

    def test_a_refusal_with_nothing_to_suggest_is_still_a_refusal(self):
        """"No" and "nothing to suggest" are different answers, and anything reading a
        verdict has to keep them apart. Shrink every vehicle under the load to get one."""
        P2PVehicleCapacity.objects.all().update(capacity_cbm=Decimal('0.001'))
        self.assertIsNone(smallest_vehicle_for('xl', 1))
        ok, reason, needed = vehicle_verdict('truck', load={'xl': 1})
        self.assertFalse(ok)
        self.assertEqual(reason, 'too_big')
        self.assertIsNone(needed)


class ClosedRangeTests(TestCase):
    """No row on the card runs to "no limit" — every ceiling closes on a real limit."""

    def test_the_distance_ceiling_is_the_longest_journey_the_page_accepts(self):
        """Derived from QATAR_BBOX, so it cannot orphan a bookable job: the two furthest
        corners the calculator will price must still fall inside it."""
        lat_min, lat_max, lng_min, lng_max = QATAR_BBOX
        _low, high = distance_band(lat_min, lng_min, lat_max, lng_max)
        self.assertGreaterEqual(max_journey_km(), high)

    def test_a_blank_ceiling_is_saved_as_the_real_limit(self):
        from p2p.forms import P2PRateBandForm
        form = P2PRateBandForm({'min_boxes': 1, 'priority': 0, 'is_active': 'on',
                                'price': '40', 'size': 's'})
        self.assertTrue(form.is_valid(), form.errors)
        band = form.save()
        self.assertEqual(band.max_boxes, P2P_MAX_BOXES)
        self.assertEqual(band.up_to_km, max_journey_km())

    def test_a_blank_tier_ceiling_is_saved_as_the_real_limit(self):
        from p2p.forms import P2PBoxTierForm
        form = P2PBoxTierForm({'min_boxes': 2, 'uplift': '10', 'is_active': 'on'})
        self.assertTrue(form.is_valid(), form.errors)
        tier = form.save()
        self.assertEqual(tier.max_boxes, P2P_MAX_BOXES)
        self.assertEqual(tier.up_to_kg, P2P_MAX_KG)

    def test_the_seeded_card_carries_no_open_range(self):
        """The migrations close what was already there, not just what is added next."""
        self.assertFalse(P2PRateBand.objects.filter(up_to_km__isnull=True).exists())
        self.assertFalse(P2PRateBand.objects.filter(max_boxes__isnull=True).exists())
        self.assertFalse(P2PBoxTier.objects.filter(max_boxes__isnull=True).exists())
        self.assertFalse(P2PBoxTier.objects.filter(up_to_kg__isnull=True).exists())


class BoxTierWeightTests(TestCase):
    """A tier can be limited by weight as well as by count — four boxes of documents
    and four of tiles are not the same job."""

    @classmethod
    def setUpTestData(cls):
        P2PRateBand.objects.all().delete()
        P2PRateBand.objects.create(min_boxes=1, max_boxes=20, up_to_km=300,
                                   price=Decimal('40'))
        P2PBoxTier.objects.all().delete()
        P2PVehicleCapacity.objects.all().delete()
        cls.light = P2PBoxTier.objects.create(min_boxes=2, max_boxes=5,
                                              up_to_kg=Decimal('10'), uplift=Decimal('10'))
        cls.heavy = P2PBoxTier.objects.create(min_boxes=2, max_boxes=5,
                                              up_to_kg=Decimal('200'), uplift=Decimal('40'))

    def _price(self, boxes, weight):
        return quote(WEST_BAY, AL_WAKRAH, size='s', vehicle='car', speed='express',
                     boxes=boxes, weight_kg=weight)['price']

    def test_the_weight_picks_the_tier(self):
        self.assertEqual(self._price(3, Decimal('8')), Decimal('50'))    # light
        self.assertEqual(self._price(3, Decimal('80')), Decimal('80'))   # heavy

    def test_an_unstated_weight_still_gets_a_tier(self):
        """Weight is optional on the public calculator. Refusing every weight-limited
        tier without it would zero the box uplift on each quote from that page — the
        customer shown one number and charged another."""
        self.assertEqual(self._price(3, None), Decimal('50'))

    def test_a_weight_past_every_tier_leaves_the_band_alone(self):
        self.assertEqual(self._price(3, Decimal('900')), Decimal('40'))


class MatrixFoldingTests(TestCase):
    """The staff matrix folds the pairings nobody books — it must never drop them.

    An envelope in a van is a real, bookable, priced combination; hiding it by default
    is a reading aid, so the row has to still be there with its price intact.
    """

    @classmethod
    def setUpTestData(cls):
        P2PRateBand.objects.all().delete()
        for km, price in JS_LADDER:
            P2PRateBand.objects.create(min_boxes=1, up_to_km=km, price=Decimal(price))

    def test_the_everyday_pairings_are_the_ones_a_customer_would_pick(self):
        # Any vehicle, the smallest that fits, and one up.
        self.assertTrue(is_everyday_pairing('xs', ''))
        self.assertTrue(is_everyday_pairing('xs', 'bike'))
        self.assertTrue(is_everyday_pairing('xs', 'car'))
        self.assertTrue(is_everyday_pairing('l', 'van'))

    def test_an_envelope_in_a_van_is_rare_and_so_is_a_box_that_will_not_fit(self):
        self.assertFalse(is_everyday_pairing('xs', 'van'))     # two sizes too big
        self.assertFalse(is_everyday_pairing('xs', 'suv'))
        self.assertFalse(is_everyday_pairing('m', 'bike'))     # will not carry it
        self.assertFalse(is_everyday_pairing('xl', 'truck'))   # never automatic

    def test_folding_hides_nothing_from_the_matrix_itself(self):
        """Whatever the flag says, every size x vehicle pair is still a row with cells,
        because ops open the fold to check exactly these prices."""
        matrix = price_matrix()
        axes = matrix_axes()
        pairs = {(row['size'], row['vehicle']) for row in matrix}
        self.assertEqual(len(matrix), len(pairs))
        self.assertIn(('xs', 'van'), pairs)
        for row in matrix:
            self.assertEqual(len(row['cells']),
                             len(axes['km']) * len(axes['speeds']) * len(axes['tiers']))
        rare = [row for row in matrix if row['rare']]
        self.assertTrue(rare)
        self.assertTrue(all(not row['rare'] for row in matrix if row['vehicle'] == ''))


class MatrixIsReadOffTheCardTests(TestCase):
    """The distance columns describe the card in the database, not a list in the code.

    They used to be a literal in pricing.py. Ops could add a 50 km band and the chart
    would keep printing four columns that no longer matched the rows underneath it —
    the one thing this page exists to prevent.
    """

    def setUp(self):
        P2PRateBand.objects.all().delete()

    def test_the_columns_are_the_ceilings_ops_have_written(self):
        P2PRateBand.objects.create(min_boxes=1, up_to_km=15, price=Decimal('30'))
        P2PRateBand.objects.create(min_boxes=1, up_to_km=50, price=Decimal('60'))
        self.assertEqual([label for _km, label in matrix_axes()['km']],
                         ['≤ 15 km', '≤ 50 km'])

        P2PRateBand.objects.create(min_boxes=1, up_to_km=80, price=Decimal('90'))
        self.assertIn('≤ 80 km', [label for _km, label in matrix_axes()['km']])

    def test_a_repeated_ceiling_is_one_column_not_one_per_row(self):
        """The generated card writes the same four ceilings across every combination."""
        for size in ('xs', 's', 'm'):
            P2PRateBand.objects.create(min_boxes=1, size=size, up_to_km=15,
                                       price=Decimal('30'))
        self.assertEqual(len(matrix_axes()['km']), 1)

    def test_an_open_ended_band_earns_the_last_column(self):
        P2PRateBand.objects.create(min_boxes=1, up_to_km=15, price=Decimal('30'))
        P2PRateBand.objects.create(min_boxes=1, up_to_km=None, price=Decimal('90'))
        km = matrix_axes()['km']
        self.assertEqual(km[-1][1], '15 km +')
        # The probe has to land past the last ceiling or the column prices the wrong row.
        self.assertGreater(km[-1][0], 15)
        # One tier's worth, and only the cells that priced: a bike has no room for a
        # bulky item, and that cell is a redirection rather than a number.
        prices = {cell['price'] for row in price_matrix(boxes=1) for cell in row['cells']
                  if cell['price'] is not None}
        self.assertEqual(prices, {Decimal('30'), Decimal('90')})

    def test_an_inactive_band_shapes_nothing(self):
        P2PRateBand.objects.create(min_boxes=1, up_to_km=15, price=Decimal('30'))
        P2PRateBand.objects.create(min_boxes=1, up_to_km=99, price=Decimal('30'),
                                   is_active=False)
        self.assertNotIn('≤ 99 km', [label for _km, label in matrix_axes()['km']])

    def test_an_empty_card_charts_nothing_rather_than_guessing(self):
        self.assertEqual(matrix_axes()['km'], [])
        self.assertEqual(price_matrix(), [])

    def test_every_choice_a_customer_can_make_is_still_a_row(self):
        """Rows are the pickers, not the words in the rows: a card of catch-alls names
        no size at all and still prices all five, so charting only what the bands
        mention would go blank while the page kept selling deliveries."""
        P2PRateBand.objects.create(min_boxes=1, up_to_km=None, price=Decimal('40'))
        axes = matrix_axes()
        self.assertEqual(axes['sizes'], [slug for slug, _ in P2P_SIZE_CHOICES])
        self.assertEqual(axes['vehicles'], [''] + [slug for slug, _ in P2P_VEHICLE_CHOICES])
        self.assertEqual(len(price_matrix()), len(axes['sizes']) * len(axes['vehicles']))


class DistanceTests(TestCase):
    """The Python mirror must match the calculator's displayed range."""

    @classmethod
    def setUpTestData(cls):
        P2PRateBand.objects.all().delete()
        for km, price in JS_LADDER:
            P2PRateBand.objects.create(min_boxes=1, up_to_km=km, price=Decimal(price))

    def test_buffer_widens_with_distance(self):
        low, high = distance_band(*WEST_BAY, *AL_WAKRAH)
        self.assertEqual(high - low, 2 if low < 15 else (4 if low < 25 else 8))

    def test_quote_prices_off_the_upper_figure(self):
        result = quote(WEST_BAY, AL_WAKRAH, size='s', vehicle='bike', speed='express')
        self.assertFalse(result['needs_quote'])
        self.assertEqual(result['distance_km'], Decimal(result['km_high']))

    def test_no_size_is_never_auto_priced(self):
        """The page will not price without a size, and neither may the server.

        The quote-only rules are keyed on size, so a sizeless request would fall
        through to the ladder and auto-price a load the calculator itself would have
        sent to a human.
        """
        result = quote(WEST_BAY, AL_WAKRAH, size='', vehicle='bike', speed='express')
        self.assertTrue(result['needs_quote'])
        self.assertIsNone(result['price'])


class HouseBusinessGuardTests(TestCase):
    """The house business is a container, not a client — it must never be paid out.

    COD settlement is business-scoped and bulk-marks every task in the payout as
    settled (fleet/wallet_service.py), so treating EZP2P as payable would hand every
    personal sender's cash to EzzyDelivery and close the rows in one click, with no
    way back from that screen.
    """

    def test_is_house_business_identifies_the_container(self):
        from p2p.services import is_house_business
        house = house_business()
        other = Business.objects.create(
            business_id=123456, business_code='REALSHOP',
            business_name='A Real Client', business_status='active')
        self.assertTrue(is_house_business(house))
        self.assertTrue(is_house_business(house.business_id))
        self.assertFalse(is_house_business(other))
        self.assertFalse(is_house_business(None))

    def test_house_business_resolver_is_loud_when_unseeded(self):
        """A missing seed must raise, not silently pick another business."""
        from p2p.services import HouseBusinessMissing, house_business as resolve
        Business.objects.filter(business_code='EZP2P').delete()
        with self.assertRaises(HouseBusinessMissing):
            resolve()

    def test_settlement_dropdown_excludes_the_house_business(self):
        """The report lists active businesses; EZP2P is active for the pickup gate."""
        from django.db.models import Q
        from p2p.services import HOUSE_BUSINESS_CODE
        house_business()
        Business.objects.create(
            business_id=123457, business_code='REALSHOP2',
            business_name='Another Client', business_status='active')
        listed = list(
            Business.objects.filter(Q(business_status='active'))
            .exclude(business_code=HOUSE_BUSINESS_CODE)
            .values_list('business_code', flat=True)
        )
        self.assertIn('REALSHOP2', listed)
        self.assertNotIn('EZP2P', listed)


class PickupPickerTests(TestCase):
    """One-off P2P addresses must not accumulate in a client's pickup dropdown."""

    def test_selectable_hides_p2p_rows_but_lookups_still_find_them(self):
        business = house_business()
        saved = PickupLocation.objects.create(
            business=business, pickup_location_title='Main Warehouse',
            locality='Industrial Area', pickup_status='active', is_p2p=False)
        one_off = make_pickup(business)  # is_p2p=True

        selectable = list(PickupLocation.objects.filter(business=business).selectable())
        self.assertIn(saved, selectable)
        self.assertNotIn(one_off, selectable,
                         'A one-off P2P address leaked into the pickup dropdown.')

        # Relocating a leg and loading an order's own pickup look up by id and must
        # still resolve — which is why this is a queryset method, not a default filter.
        self.assertEqual(
            PickupLocation.objects.filter(id=one_off.id).first(), one_off)
