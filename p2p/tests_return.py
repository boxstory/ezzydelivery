# Purpose: Cover for the return leg — pricing, the second order, release, edit and cancel.
# Used by: python manage.py test p2p.tests_return
# Notes: The leg back is a SECOND Order, so almost every assertion here is about the pair rather
#        than about a field. captureOnCommitCallbacks where the first-mile hook has to fire.

from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from delivery.models import PickupTask
from p2p.models import P2PBooking
from p2p.pricing import quote
from p2p.tests import house_business
from p2p.tests_flow import (
    AL_WAKRAH, WEST_BAY, accept_payload, details_payload, seed_bands,
)


class ReturnPricingTests(TestCase):
    """The leg back is the same journey the other way, so it costs the same again."""

    @classmethod
    def setUpTestData(cls):
        seed_bands()

    def test_return_trip_is_the_leg_charged_twice(self):
        one_way = quote(WEST_BAY, AL_WAKRAH, size='s', vehicle='bike')
        both = quote(WEST_BAY, AL_WAKRAH, size='s', vehicle='bike', return_trip=True)
        self.assertEqual(both['price'], one_way['price'] * 2)
        self.assertEqual(both['leg_price'], one_way['price'])
        self.assertEqual(both['return_price'], one_way['price'])
        self.assertTrue(both['return_trip'])

    def test_a_one_way_quote_names_no_return_price(self):
        result = quote(WEST_BAY, AL_WAKRAH, size='s', vehicle='bike')
        self.assertIsNone(result['return_price'])
        self.assertFalse(result['return_trip'])
        self.assertEqual(result['leg_price'], result['price'])

    def test_an_unpriceable_load_stays_unpriceable_both_ways(self):
        """Doubling nothing is still nothing — a quote request must not become a price."""
        result = quote(WEST_BAY, AL_WAKRAH, size='xl', return_trip=True)
        self.assertTrue(result['needs_quote'])
        self.assertIsNone(result['price'])
        self.assertIsNone(result['leg_price'])


class ReturnOrderTests(TestCase):
    """Booking the leg back writes a second order, pointing the other way."""

    @classmethod
    def setUpTestData(cls):
        seed_bands()
        house_business()

    def setUp(self):
        from core.models import Profile
        self.user = User.objects.create_user('backsender', 'back@example.com', 'pw12345!')
        Profile.objects.create(user=self.user, username='backsender', is_customer=True,
                               whatsapp='55512345', whatsapp_verified=True)
        self.client.force_login(self.user)

    def _book(self, accept=None, **overrides):
        self.client.post(reverse('p2p:book_start'), accept or accept_payload())
        booking = P2PBooking.objects.latest('id')
        booking.customer = self.user
        booking.save(update_fields=['customer'])
        with patch('p2p.notifications.send_booking_confirmation', return_value=None):
            with self.captureOnCommitCallbacks(execute=True):
                self.client.post(reverse('p2p:book', kwargs={'token': booking.token}),
                                 details_payload(**overrides))
        booking.refresh_from_db()
        return booking

    def test_one_way_booking_writes_no_second_order(self):
        booking = self._book()
        self.assertFalse(booking.return_trip)
        self.assertIsNone(booking.return_order_id)
        self.assertEqual(booking.return_fee, Decimal('0.00'))

    def test_return_trip_writes_the_leg_back(self):
        booking = self._book(return_trip='on', return_description='Signed papers')
        self.assertTrue(booking.return_trip)
        back = booking.return_order
        self.assertIsNotNone(back, 'No order was written for the leg back')

        # It runs the other way: collected where the outward one was delivered.
        self.assertEqual(back.pickup_location.pickup_lat, booking.to_lat)
        self.assertEqual(back.pickup_location.pickup_lon, booking.to_lng)
        self.assertEqual(back.latitude, booking.from_lat)
        self.assertEqual(back.longitude, booking.from_lng)
        self.assertEqual(back.customer_name, booking.sender_name)
        self.assertEqual(back.customer_phone, booking.sender_phone)
        self.assertIn('Zone 61', back.customer_address)
        self.assertEqual(back.package_description, 'Signed papers')
        self.assertEqual(back.order_type, 'pick_and_drop')

    def test_the_agreed_price_is_split_across_the_two_orders(self):
        booking = self._book(return_trip='on')
        total = booking.agreed_price
        self.assertEqual(booking.fee_amount, total)
        self.assertEqual(booking.order.dl_amount + booking.return_order.dl_amount, total)
        self.assertEqual(booking.return_order.dl_amount, booking.return_fee)

    def test_the_leg_back_never_carries_the_cod(self):
        """The receiver's cash is for the goods going out. Asking twice costs money."""
        booking = self._book(return_trip='on', cod_amount='250')
        self.assertEqual(booking.order.cod_amount, Decimal('250'))
        self.assertEqual(booking.return_order.cod_amount, Decimal('0'))

    def test_neither_leg_reaches_a_driver_before_confirmation(self):
        booking = self._book(return_trip='on')
        for order in (booking.order, booking.return_order):
            self.assertEqual(order.order_status, 'to_review')
            self.assertEqual(order.pickup_location.pickup_status, 'pending')
            self.assertEqual(PickupTask.objects.filter(order=order).count(), 0)

    def test_confirming_releases_both_legs(self):
        booking = self._book(return_trip='on')
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(reverse('p2p:accept_price', kwargs={'token': booking.token}))
        booking.refresh_from_db()
        for order in (booking.order, booking.return_order):
            order.refresh_from_db()
            self.assertEqual(order.order_status, 'ready_to_pickup')
            self.assertEqual(order.pickup_location.pickup_status, 'active')
            self.assertEqual(PickupTask.objects.filter(order=order).count(), 1)

    def test_a_description_with_no_return_trip_is_dropped(self):
        booking = self._book(return_description='Signed papers')
        self.assertFalse(booking.return_trip)
        self.assertEqual(booking.return_description, '')

    def test_the_calculator_can_ask_for_the_leg_back(self):
        payload = accept_payload()
        payload['return_trip'] = '1'
        self.client.post(reverse('p2p:book_start'), payload)
        booking = P2PBooking.objects.latest('id')
        self.assertTrue(booking.return_trip)
        one_way = quote(WEST_BAY, AL_WAKRAH, size='s', vehicle='bike')['price']
        self.assertEqual(booking.quoted_price, one_way * 2)


class LoadCounterTests(ReturnOrderTests):
    """The per-size counters are the only count on the form now, so they have to be
    prefilled from whatever the booking already says — or an edit shrinks the job."""

    def test_a_single_size_booking_prefills_its_counter(self):
        booking = self._book(size='m', vehicle='car', box_count='3', weight_kg='7.5')
        self.assertEqual(booking.box_count, 3)
        resp = self.client.get(
            reverse('p2p:delivery_edit',
                    kwargs={'order_number': booking.order.order_number}))
        self.assertEqual(resp.context['form'].initial.get('count_m'), 3)

    def test_saving_the_form_as_rendered_keeps_the_count(self):
        """The rendered form no longer posts box_count at all — only the counters."""
        booking = self._book(size='m', vehicle='car', box_count='3', weight_kg='7.5')
        payload = details_payload(size='m', vehicle='car', weight_kg='7.5', count_m='3')
        payload.pop('box_count')
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(
                reverse('p2p:delivery_edit',
                        kwargs={'order_number': booking.order.order_number}), payload)
        booking.refresh_from_db()
        booking.order.refresh_from_db()
        self.assertEqual(booking.box_count, 3)
        self.assertEqual(booking.order.package_qty, 3)

    def test_a_mixed_load_prefills_one_counter_per_size(self):
        booking = self._book(size='s', vehicle='car', count_s='2', count_m='1')
        resp = self.client.get(
            reverse('p2p:delivery_edit',
                    kwargs={'order_number': booking.order.order_number}))
        initial = resp.context['form'].initial
        self.assertEqual(initial.get('count_s'), 2)
        self.assertEqual(initial.get('count_m'), 1)
        self.assertEqual(booking.box_count, 3)

    def test_the_counters_still_decide_the_total_with_no_box_count_posted(self):
        payload = details_payload(count_s='2', count_m='1', size='s', vehicle='car')
        payload.pop('box_count')
        self.client.post(reverse('p2p:book_start'), accept_payload())
        booking = P2PBooking.objects.latest('id')
        booking.customer = self.user
        booking.save(update_fields=['customer'])
        with patch('p2p.notifications.send_booking_confirmation', return_value=None):
            with self.captureOnCommitCallbacks(execute=True):
                self.client.post(
                    reverse('p2p:book', kwargs={'token': booking.token}), payload)
        booking.refresh_from_db()
        self.assertEqual(booking.box_count, 3)
        self.assertEqual(booking.order.package_qty, 3)


class ReturnEditTests(ReturnOrderTests):
    """The tick is on the edit form too, so all three transitions have to work."""

    def _edit(self, booking, **overrides):
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(
                reverse('p2p:delivery_edit',
                        kwargs={'order_number': booking.order.order_number}),
                details_payload(**overrides))
        booking.refresh_from_db()
        return booking

    def test_adding_the_leg_back_after_booking(self):
        booking = self._book()
        self.assertIsNone(booking.return_order_id)
        booking = self._edit(booking, return_trip='on', return_description='Empty crate')
        self.assertTrue(booking.return_trip)
        self.assertIsNotNone(booking.return_order_id)
        self.assertEqual(booking.return_order.package_description, 'Empty crate')
        self.assertEqual(booking.order.dl_amount + booking.return_order.dl_amount,
                         booking.agreed_price)

    def test_dropping_the_leg_back_cancels_its_order(self):
        booking = self._book(return_trip='on')
        cancelled = booking.return_order
        booking = self._edit(booking)
        cancelled.refresh_from_db()
        self.assertFalse(booking.return_trip)
        self.assertIsNone(booking.return_order_id)
        self.assertEqual(cancelled.order_status, 'cancelled',
                         'A dropped leg must be cancelled, never deleted')
        self.assertEqual(booking.order.dl_amount, booking.agreed_price)

    def test_editing_the_drop_end_moves_the_leg_back(self):
        booking = self._book(return_trip='on')
        booking = self._edit(booking, return_trip='on',
                             customer_name='Noora Receiver', dl_zone='91')
        back = booking.return_order
        self.assertEqual(back.pickup_location.pickup_zone_no, 91)
        self.assertEqual(back.pickup_location.contact_name, 'Noora Receiver')

    def test_editing_the_leg_back_redirects_to_the_outward_order(self):
        """One form owns both journeys — editing them apart is how they disagree."""
        booking = self._book(return_trip='on')
        response = self.client.get(
            reverse('p2p:delivery_edit',
                    kwargs={'order_number': booking.return_order.order_number}))
        self.assertRedirects(
            response,
            reverse('p2p:delivery_edit',
                    kwargs={'order_number': booking.order.order_number}))
