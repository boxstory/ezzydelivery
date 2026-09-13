# Purpose: The staff-side P2P booking form — that a job taken on the phone becomes the same booking + order a customer's own would.
# Used by: manage.py test workforce.tests_p2p_new
# Notes: Kept out of tests_views.py, which is large and carries known failures of its own. WhatsApp is
#        patched everywhere: a test must never put a real message on a real number.

from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse

from orders.models import Order
from p2p import services as p2p_services
from p2p.models import P2PBooking, P2PRateBand
from p2p.tests import house_business
from workforce.tests_views import WorkforceTestMixin


class StaffP2PBookingTests(WorkforceTestMixin, TestCase):
    """Ops book a point-to-point job themselves, at /workforce/orders/p2p/new/."""

    def setUp(self):
        self.user, _profile = self.create_staff_user()
        self.client.login(username='staffuser', password='Staff@123')
        self.url = reverse('workforce:wf_p2p_new')
        # The container every personal P2P order lands on. Created here rather than
        # relied on from migration state, exactly as the p2p tests do.
        house_business()
        # One band that covers everything, so a valid post has a price to land on.
        P2PRateBand.objects.all().delete()
        P2PRateBand.objects.create(min_boxes=1, up_to_km=None, price=Decimal('45'))

    def _payload(self, **overrides):
        """A complete, valid booking: West Bay to Al Wakrah, one small box, express."""
        data = {
            'from_label': 'West Bay', 'from_lat': '25.3272', 'from_lng': '51.5310',
            'to_label': 'Al Wakrah', 'to_lat': '25.1719', 'to_lng': '51.5989',
            'category': 'Documents',
            'booker_role': 'sender', 'booker_phone': '33112233',
            'sender_name': 'Sara', 'sender_phone': '33112233',
            'pickup_zone': '66', 'pickup_street': '850', 'pickup_building': '12',
            'customer_name': 'Ahmed', 'customer_phone': '55667788',
            'customer_address': 'Building 4, Street 900, Al Wakrah',
            'size': 's', 'box_count': '1', 'speed': 'express',
            'fee_payer': 'sender', 'notify_customer': '',
        }
        data.update(overrides)
        return data

    def _post(self, **overrides):
        with patch('core.whatsapp_utils.send_routed_message') as sender:
            resp = self.client.post(self.url, self._payload(**overrides))
        return resp, sender

    def test_the_page_opens(self):
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)
        # The area picker is fed the same list the public calculator uses.
        self.assertIn('localities', resp.context)

    def test_a_booking_becomes_an_order_waiting_on_the_customer(self):
        """The default post writes a real order, held back until it is confirmed."""
        resp, _ = self._post()
        booking = P2PBooking.objects.get()
        order = booking.order
        self.assertRedirects(
            resp, reverse('workforce:order_detail', kwargs={'order_id': order.id}),
            fetch_redirect_response=False)

        self.assertEqual(order.order_type, 'pick_and_drop')
        # to_review + a pending pickup location is what keeps it away from drivers.
        self.assertEqual(order.order_status, 'to_review')
        self.assertEqual(order.pickup_location.pickup_status, 'pending')
        self.assertTrue(order.pickup_location.is_p2p)
        self.assertEqual(booking.status, 'awaiting_customer')
        self.assertEqual(order.dl_amount, Decimal('45'))
        self.assertEqual(order.customer_name, 'Ahmed')
        # No account named, so it lands on the house business as cash to the driver.
        self.assertTrue(p2p_services.is_house_business(order.business))
        self.assertEqual(booking.fee_status, 'pending')

    def test_confirming_on_the_call_releases_the_job(self):
        """The customer said yes on the phone — the confirm link is skipped."""
        self._post(confirm_now='on')
        booking = P2PBooking.objects.get()
        booking.refresh_from_db()
        order = Order.objects.get(pk=booking.order_id)
        self.assertEqual(booking.status, 'confirmed')
        self.assertEqual(order.order_status, 'ready_to_pickup')
        self.assertEqual(order.pickup_location.pickup_status, 'active')

    def test_a_client_account_is_billed_instead_of_paying_cash(self):
        business = self.create_business()
        self._post(bill_to=str(business.business_id))
        booking = P2PBooking.objects.get()
        order = booking.order
        self.assertEqual(order.business_id, business.business_id)
        # A client's job is a line on their charge invoice, so no cash changes hands.
        self.assertEqual(booking.fee_status, 'billed')
        # And it belongs in that client's console, not in a personal sender's.
        self.assertIsNone(order.p2p_customer_id)

    def test_an_agreed_price_overrules_the_rate_card(self):
        """A figure already quoted out loud is the one the order carries."""
        self._post(agreed_price='75')
        booking = P2PBooking.objects.get()
        self.assertEqual(booking.staff_price, Decimal('75'))
        self.assertEqual(booking.priced_by_id, self.user.id)
        self.assertEqual(booking.agreed_price, Decimal('75'))
        self.assertEqual(booking.order.dl_amount, Decimal('75'))
        self.assertFalse(booking.needs_quote)

    def test_a_mixed_load_is_priced_as_one_job(self):
        resp, _ = self._post(count_s='2', count_m='1', size='')
        self.assertEqual(resp.status_code, 302)
        booking = P2PBooking.objects.get()
        self.assertEqual(booking.box_count, 3)
        self.assertEqual(booking.load_map(), {'s': 2, 'm': 1})
        self.assertEqual(booking.order.package_qty, 3)

    def test_the_confirmation_goes_to_the_booker(self):
        with patch('core.whatsapp_utils.send_routed_message') as sender:
            self.client.post(self.url, self._payload(notify_customer='on'))
        self.assertTrue(sender.called)
        self.assertEqual(sender.call_args[0][1], '33112233')

    def test_a_pin_outside_qatar_is_refused(self):
        resp, _ = self._post(to_lat='48.8566', to_lng='2.3522')
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(P2PBooking.objects.exists())
        self.assertIn('outside Qatar', resp.context['form'].errors['to_lat'][0])

    def test_releasing_an_unpriceable_job_needs_a_figure(self):
        """No band, no agreed price — there is nothing to send a driver out on."""
        P2PRateBand.objects.all().delete()
        resp, _ = self._post(confirm_now='on')
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(P2PBooking.objects.exists())
        self.assertIn('agreed_price', resp.context['form'].errors)

    def test_an_unpriceable_job_can_still_be_taken_for_a_quote(self):
        """Without confirm_now it is a quote request, which is the customer path too."""
        P2PRateBand.objects.all().delete()
        resp, _ = self._post()
        self.assertEqual(resp.status_code, 302)
        booking = P2PBooking.objects.get()
        self.assertTrue(booking.needs_quote)
        self.assertEqual(booking.status, 'awaiting_price')

    def test_a_scheduled_job_needs_a_collection_day(self):
        resp, _ = self._post(speed='standard')
        self.assertEqual(resp.status_code, 200)
        self.assertIn('pickup_date', resp.context['form'].errors)

    def test_a_scheduled_job_keeps_its_windows(self):
        day = date.today() + timedelta(days=2)
        resp, _ = self._post(speed='standard', pickup_date=day.isoformat(),
                             pickup_time='08:00')
        self.assertEqual(resp.status_code, 302,
                         getattr(resp.context.get('form'), 'errors', None) if resp.context else None)
        booking = P2PBooking.objects.get()
        self.assertEqual(booking.pickup_date, day)
        # A blank delivery day means the same day we collect it.
        self.assertEqual(booking.order.scheduled_date, day)

    def test_a_return_trip_is_taken_as_two_orders(self):
        """Ops book the leg back on the same call — one booking, two journeys."""
        resp, _sender = self._post(return_trip='on', return_description='Signed papers')
        self.assertEqual(resp.status_code, 302)
        booking = P2PBooking.objects.latest('id')
        self.assertTrue(booking.return_trip)
        self.assertIsNotNone(booking.return_order_id)
        # 45 out and 45 back, split across the two orders so neither is billed twice.
        self.assertEqual(booking.agreed_price, Decimal('90'))
        self.assertEqual(booking.order.dl_amount, Decimal('45'))
        self.assertEqual(booking.return_order.dl_amount, Decimal('45'))
        self.assertEqual(booking.return_order.package_description, 'Signed papers')

    def test_an_agreed_price_on_a_return_trip_covers_both_legs(self):
        """A figure quoted out loud is the whole job, not the price of one journey."""
        self._post(return_trip='on', agreed_price='70')
        booking = P2PBooking.objects.latest('id')
        self.assertEqual(booking.agreed_price, Decimal('70'))
        self.assertEqual(booking.order.dl_amount + booking.return_order.dl_amount,
                         Decimal('70'))

    def test_a_non_staff_user_cannot_open_it(self):
        self.client.logout()
        self.create_non_staff_user()
        self.client.login(username='regularuser', password='Regular@123')
        resp = self.client.get(self.url)
        self.assertNotEqual(resp.status_code, 200)


class StaffP2PQuoteEndpointTests(WorkforceTestMixin, TestCase):
    """The figure ops read out on the call, priced by the same function the POST uses."""

    def setUp(self):
        self.user, _profile = self.create_staff_user()
        self.client.login(username='staffuser', password='Staff@123')
        self.url = reverse('workforce:wf_p2p_quote')
        P2PRateBand.objects.all().delete()
        P2PRateBand.objects.create(min_boxes=1, up_to_km=None, price=Decimal('45'))

    def _get(self, **params):
        base = {'from_lat': '25.3272', 'from_lng': '51.5310',
                'to_lat': '25.1719', 'to_lng': '51.5989', 'size': 's', 'box_count': '1'}
        base.update(params)
        return self.client.get(self.url, base).json()

    def test_it_prices_a_load(self):
        data = self._get()
        self.assertTrue(data['ok'])
        self.assertEqual(Decimal(data['price']), Decimal('45'))
        self.assertFalse(data['needs_quote'])

    def test_it_prices_a_return_trip_as_both_journeys(self):
        data = self._get(return_trip='1')
        self.assertEqual(Decimal(data['price']), Decimal('90'))
        self.assertEqual(Decimal(data['leg_price']), Decimal('45'))
        self.assertTrue(data['return_trip'])

    def test_it_refuses_a_pin_outside_qatar(self):
        data = self._get(to_lat='48.8566', to_lng='2.3522')
        self.assertFalse(data['ok'])
        self.assertIn('Qatar', data['reason'])

    def test_it_writes_nothing(self):
        self._get()
        self.assertFalse(P2PBooking.objects.exists())
        self.assertFalse(Order.objects.exists())
