# Purpose: End-to-end cover for the P2P booking flow, the console and the staff surfaces.
# Used by: python manage.py test p2p
# Notes: captureOnCommitCallbacks where the first-mile hook must fire — TransactionTestCase would
#        flush the AutoTriggerConfig rows other apps' tests rely on.

from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from business.models import Business
from delivery.models import PickupTask
from orders.models import Order, OrderComments
from p2p.models import (
    P2PBooking, P2PBoxTier, P2PRateBand, P2PVehicleBoxLimit, P2PVehicleCapacity,
)
from p2p.tests import house_business

WEST_BAY = ('25.3272', '51.5310')
AL_WAKRAH = ('25.1719', '51.5989')


def seed_bands():
    P2PRateBand.objects.all().delete()
    for km, price in [(10, 25), (20, 35), (30, 40), (None, 55)]:
        P2PRateBand.objects.create(min_boxes=1, up_to_km=km, price=Decimal(price))
    for size in ['m', 'l', 'xl']:
        P2PRateBand.objects.create(min_boxes=1, size=size, needs_quote=True, priority=10)
    for vehicle in ['suv', 'van', 'truck']:
        P2PRateBand.objects.create(min_boxes=1, vehicle=vehicle, needs_quote=True, priority=10)


def accept_payload(size='s', vehicle='bike'):
    return {
        'from_lat': WEST_BAY[0], 'from_lng': WEST_BAY[1],
        'to_lat': AL_WAKRAH[0], 'to_lng': AL_WAKRAH[1],
        'from_label': 'West Bay', 'to_label': 'Al Wakrah',
        'size': size, 'vehicle': vehicle, 'box_count': '1',
    }


def details_payload(**overrides):
    data = {
        # The two questions that decide whose form this is and where the cash is due.
        'booker_role': 'sender', 'fee_payer': 'sender',
        'sender_name': 'Ahmed Sender', 'sender_phone': '55512345',
        'pickup_zone': '61', 'pickup_street': '850', 'pickup_building': '12',
        'customer_name': 'Fatima Receiver', 'customer_phone': '55598765',
        'customer_address': 'Al Wakrah, Zone 90', 'dl_zone': '90',
        'dl_street': '12', 'dl_building': '3',
        'size': 's', 'vehicle': 'bike', 'box_count': '1', 'weight_kg': '2.5',
        'package_description': 'Documents', 'cod_amount': '0', 'speed': 'express',
    }
    data.update(overrides)
    return data


class BookingFlowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed_bands()
        house_business()

    def setUp(self):
        self.user = User.objects.create_user('sender', 'sender@example.com', 'pw12345!')

    def _accept(self, **kw):
        return self.client.post(reverse('p2p:book_start'), accept_payload(**kw))

    def test_posted_price_is_ignored(self):
        """A page edited in DevTools must not be able to buy a cheap delivery."""
        payload = accept_payload()
        payload['price'] = '1'
        payload['quoted_price'] = '1'
        self.client.post(reverse('p2p:book_start'), payload)
        booking = P2PBooking.objects.latest('id')
        self.assertNotEqual(booking.quoted_price, Decimal('1'))
        self.assertEqual(booking.quoted_price, Decimal('40'))  # 22-26km band

    def test_anonymous_accept_creates_an_unclaimed_draft(self):
        self._accept()
        booking = P2PBooking.objects.latest('id')
        self.assertEqual(booking.status, 'draft')
        self.assertIsNone(booking.customer_id)
        self.assertIsNone(booking.order_id)

    def test_the_calculators_speed_choice_reaches_the_booking(self):
        """Express or Scheduled is a pricing input, so it must survive the hand-off."""
        payload = accept_payload()
        payload['speed'] = 'standard'
        self.client.post(reverse('p2p:book_start'), payload)
        self.assertEqual(P2PBooking.objects.latest('id').speed, 'standard')

    def test_the_calculators_box_count_reaches_the_booking(self):
        """The calculator's box stepper posts box_count; the draft has to carry it,
        or the customer is asked the same question again on the booking form."""
        payload = accept_payload()
        payload['box_count'] = '4'
        self.client.post(reverse('p2p:book_start'), payload)
        self.assertEqual(P2PBooking.objects.latest('id').box_count, 4)

    def test_a_silly_box_count_is_clamped_not_refused(self):
        """A hand-edited count must not create a 900-box draft, and must not lose the
        booking either — book_start clamps to the same 1-20 the form validates."""
        for posted, expected in (('0', 1), ('900', 20), ('', 1), ('three', 1)):
            payload = accept_payload()
            payload['box_count'] = posted
            self.client.post(reverse('p2p:book_start'), payload)
            self.assertEqual(P2PBooking.objects.latest('id').box_count, expected, posted)

    def test_every_choice_has_a_card(self):
        """A choice with no card renders as a blank tile on both the calculator and
        the booking form — the two lists have to stay in step."""
        from p2p.models import (
            P2P_SIZE_CHOICES, P2P_SPEED_CHOICES, P2P_VEHICLE_CHOICES,
            size_card_list, speed_card_list, vehicle_card_list,
        )
        for cards, choices in (
            (size_card_list(), P2P_SIZE_CHOICES),
            (vehicle_card_list(include_any=True), [('', '')] + P2P_VEHICLE_CHOICES),
            (speed_card_list(), P2P_SPEED_CHOICES),
        ):
            self.assertEqual([c['slug'] for c in cards], [slug for slug, _ in choices])
            for card in cards:
                self.assertTrue(card.get('name'), card)
                self.assertTrue(card.get('label') is not None, card)

    def test_out_of_qatar_is_refused(self):
        payload = accept_payload()
        payload['to_lat'] = '48.8566'   # Paris
        payload['to_lng'] = '2.3522'
        self.client.post(reverse('p2p:book_start'), payload)
        self.assertEqual(P2PBooking.objects.count(), 0)

    def test_booking_url_requires_login_then_claims(self):
        self._accept()
        booking = P2PBooking.objects.latest('id')
        url = reverse('p2p:book', kwargs={'token': booking.token})
        self.assertEqual(self.client.get(url).status_code, 302)

        self.client.force_login(self.user)
        self.client.get(url)
        booking.refresh_from_db()
        self.assertEqual(booking.customer_id, self.user.id)

    def test_another_user_cannot_open_a_claimed_booking(self):
        self._accept()
        booking = P2PBooking.objects.latest('id')
        booking.customer = self.user
        booking.save(update_fields=['customer'])

        intruder = User.objects.create_user('nosy', 'nosy@example.com', 'pw12345!')
        self.client.force_login(intruder)
        url = reverse('p2p:book', kwargs={'token': booking.token})
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_unverified_number_is_sent_to_the_otp_page(self):
        self._accept()
        booking = P2PBooking.objects.latest('id')
        self.client.force_login(self.user)
        response = self.client.get(reverse('p2p:book', kwargs={'token': booking.token}))
        self.assertRedirects(response, f'/p2p/verify-number/?next=/p2p/book/{booking.token}/',
                             fetch_redirect_response=False)

    def test_google_signup_gets_a_profile_with_attribution(self):
        from core.models import Profile
        self.client.force_login(self.user)
        self.client.get(reverse('p2p:verify_number'))
        profile = Profile.objects.get(user=self.user)
        self.assertTrue(profile.is_customer)


class OrderCreationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed_bands()
        house_business()

    def setUp(self):
        from core.models import Profile
        self.user = User.objects.create_user('sender2', 'sender2@example.com', 'pw12345!')
        Profile.objects.create(user=self.user, username='sender2', is_customer=True,
                               whatsapp='55512345', whatsapp_verified=True)
        self.client.force_login(self.user)

    def _book(self, **overrides):
        self.client.post(reverse('p2p:book_start'), accept_payload())
        booking = P2PBooking.objects.latest('id')
        booking.customer = self.user
        booking.save(update_fields=['customer'])
        with patch('p2p.notifications.send_booking_confirmation', return_value=None):
            with self.captureOnCommitCallbacks(execute=True):
                self.client.post(reverse('p2p:book', kwargs={'token': booking.token}),
                                 details_payload(**overrides))
        booking.refresh_from_db()
        return booking

    def test_order_lands_at_to_review_with_no_pickup_task(self):
        booking = self._book()
        order = booking.order
        self.assertIsNotNone(order, 'No order was created')
        self.assertEqual(order.order_status, 'to_review')
        self.assertEqual(order.order_type, 'pick_and_drop')
        self.assertEqual(order.p2p_customer_id, self.user.id)
        self.assertEqual(order.business.business_code, 'EZP2P')
        self.assertTrue(order.order_number)
        self.assertEqual(order.pickup_location.pickup_status, 'pending')
        self.assertEqual(PickupTask.objects.filter(order=order).count(), 0,
                         'An unconfirmed booking was exposed to drivers')

    def test_box_count_and_weight_are_stored_separately(self):
        # A car: three medium boxes are 0.14 cbm, which is more than a bike holds and
        # less than a pickup is sent out for, and the form now enforces both ends.
        booking = self._book(box_count='3', weight_kg='7.5', size='m', vehicle='car')
        order = booking.order
        self.assertEqual(order.package_qty, 3)
        self.assertEqual(order.package_weight_kg, Decimal('7.50'))

    def test_confirm_link_releases_the_job(self):
        booking = self._book()
        url = reverse('p2p:accept_price', kwargs={'token': booking.token})

        # A GET must not mutate — WhatsApp fetches link previews.
        self.client.get(url)
        booking.refresh_from_db()
        self.assertNotEqual(booking.status, 'confirmed')

        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(url)
        booking.refresh_from_db()
        booking.order.refresh_from_db()
        self.assertEqual(booking.status, 'confirmed')
        self.assertEqual(booking.order.order_status, 'ready_to_pickup')
        self.assertEqual(PickupTask.objects.filter(order=booking.order).count(), 1)

        # Idempotent: a second tap on the WhatsApp link changes nothing.
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(url)
        self.assertEqual(PickupTask.objects.filter(order=booking.order).count(), 1)

    def test_business_owner_booking_routes_to_their_business(self):
        Business.objects.create(business_id=771001, business_code='MYSHOP',
                                business_name='My Shop', business_status='active',
                                user=self.user)
        booking = self._book()
        self.assertEqual(booking.order.business.business_code, 'MYSHOP')
        self.assertIsNone(booking.order.p2p_customer_id,
                          'A business-routed order would be listed in two consoles')
        self.assertEqual(booking.fee_status, 'billed')

    def test_pending_business_falls_back_to_the_house(self):
        Business.objects.create(business_id=771002, business_code='PENDINGSHOP',
                                business_name='Pending Shop', business_status='pending',
                                user=self.user)
        booking = self._book()
        self.assertEqual(booking.order.business.business_code, 'EZP2P')
        self.assertEqual(booking.fee_status, 'pending')

    def test_weight_over_the_size_bracket_is_rejected(self):
        self.client.post(reverse('p2p:book_start'), accept_payload())
        booking = P2PBooking.objects.latest('id')
        booking.customer = self.user
        booking.save(update_fields=['customer'])
        response = self.client.post(
            reverse('p2p:book', kwargs={'token': booking.token}),
            details_payload(size='s', weight_kg='8'))
        self.assertContains(response, 'heavier than', status_code=200)
        booking.refresh_from_db()
        self.assertIsNone(booking.order_id)


class BookerRoleTests(TestCase):
    """The person booking is as often the one waiting for the parcel as the one
    handing it over, and the fee follows whoever they said pays — not their role."""

    @classmethod
    def setUpTestData(cls):
        seed_bands()
        house_business()

    def setUp(self):
        from core.models import Profile
        self.user = User.objects.create_user('recv', 'recv@example.com', 'pw12345!')
        Profile.objects.create(user=self.user, username='recv', is_customer=True,
                               first_name='Noor', whatsapp='55511111',
                               whatsapp_verified=True)
        self.client.force_login(self.user)

    def _book(self, **overrides):
        self.client.post(reverse('p2p:book_start'), accept_payload())
        booking = P2PBooking.objects.latest('id')
        booking.customer = self.user
        booking.save(update_fields=['customer'])
        with patch('p2p.notifications.send_booking_confirmation', return_value=None):
            with self.captureOnCommitCallbacks(execute=True):
                self.client.post(reverse('p2p:book', kwargs={'token': booking.token}),
                                 details_payload(**overrides))
        booking.refresh_from_db()
        return booking

    def test_both_ends_are_frozen_on_the_booking(self):
        booking = self._book(booker_role='receiver', fee_payer='receiver')
        self.assertEqual(booking.booker_role, 'receiver')
        self.assertEqual(booking.sender_name, 'Ahmed Sender')
        self.assertEqual(booking.receiver_name, 'Fatima Receiver')
        # They are the receiver, so the receiving leg carries their verified number,
        # not the one the payload tried to put there.
        self.assertEqual(booking.receiver_phone, '55511111')

    def test_confirm_link_goes_to_the_booker_not_the_sender(self):
        """The sender is a third party here and must not hold the link that
        releases the job."""
        booking = self._book(booker_role='receiver', fee_payer='receiver')
        self.assertEqual(booking.notify_phone, '55511111')
        self.assertNotEqual(booking.notify_phone, booking.sender_phone)

    def test_the_verified_number_cannot_be_typed_over(self):
        """readonly inputs still submit, so the gate is the form, not the widget."""
        booking = self._book(booker_role='sender', sender_phone='55500000')
        self.assertEqual(booking.sender_phone, '55511111')
        self.assertEqual(booking.booker_phone, '55511111')
        self.assertEqual(booking.notify_phone, '55511111')

    def test_the_other_leg_is_still_free(self):
        """Only the booker's own number is fixed. The other end is a real person
        whose number they are the only one who knows."""
        booking = self._book(booker_role='sender', customer_phone='55577777')
        self.assertEqual(booking.receiver_phone, '55577777')

    def test_a_third_party_can_book_for_two_other_people(self):
        booking = self._book(booker_role='other', sender_phone='55522222',
                             customer_phone='55533333')
        self.assertEqual(booking.booker_role, 'other')
        # Neither leg is theirs, so neither is overwritten...
        self.assertEqual(booking.sender_phone, '55522222')
        self.assertEqual(booking.receiver_phone, '55533333')
        # ...and their own verified number is the only way to reach them about it.
        self.assertEqual(booking.booker_phone, '55511111')
        self.assertEqual(booking.notify_phone, '55511111')

    def test_a_third_party_still_says_who_pays(self):
        booking = self._book(booker_role='other', fee_payer='receiver')
        self.assertTrue(booking.fee_due_at_delivery)
        self.assertIn('receiver pays', booking.fee_note)

    def test_fee_is_due_at_the_door_when_the_receiver_pays(self):
        booking = self._book(booker_role='receiver', fee_payer='receiver')
        self.assertEqual(booking.fee_status, 'pending')
        self.assertTrue(booking.fee_due_at_delivery)
        self.assertFalse(booking.fee_due_at_pickup)

    def test_a_sender_can_still_hand_the_fee_to_the_receiver(self):
        """fee_payer is its own answer — it does not fall out of the role."""
        booking = self._book(booker_role='sender', fee_payer='receiver')
        self.assertTrue(booking.fee_due_at_delivery)
        self.assertEqual(booking.booker_phone, booking.sender_phone)

    def test_receiver_pays_is_never_billed_to_the_client_invoice(self):
        """A business owner's own account cannot absorb a fee the receiver owes."""
        Business.objects.create(business_id=771003, business_code='SHOP3',
                                business_name='Shop Three', business_status='active',
                                user=self.user)
        booking = self._book(booker_role='receiver', fee_payer='receiver')
        self.assertEqual(booking.order.business.business_code, 'SHOP3')
        self.assertEqual(booking.fee_status, 'pending')
        self.assertTrue(booking.fee_due_at_delivery)


class DriverFeeCollectionTests(TestCase):
    """Where the driver is allowed to take the cash. The wrong end must refuse."""

    @classmethod
    def setUpTestData(cls):
        seed_bands()
        house_business()

    def setUp(self):
        from core.models import Profile
        from fleet.models import Driver
        self.user = User.objects.create_user('booker', 'booker@example.com', 'pw12345!')
        Profile.objects.create(user=self.user, username='booker', is_customer=True,
                               whatsapp='55512345', whatsapp_verified=True)
        self.driver_user = User.objects.create_user('drv', 'drv@example.com', 'pw12345!')
        driver_profile = Profile.objects.create(
            user=self.driver_user, username='drv', is_driver=True)
        self.driver = Driver.objects.create(
            driver_id=9001, user=self.driver_user, profile=driver_profile,
            driver_code='DRVP2P', driver_phone='55599999',
            driver_whatsapp='55599999', driver_languages='english',
            driver_license_number='LICP2P', driver_status='approved',
            credit_limit=Decimal('5000'))

    def _confirmed_booking(self, **overrides):
        self.client.force_login(self.user)
        self.client.post(reverse('p2p:book_start'), accept_payload())
        booking = P2PBooking.objects.latest('id')
        booking.customer = self.user
        booking.save(update_fields=['customer'])
        with patch('p2p.notifications.send_booking_confirmation', return_value=None):
            with self.captureOnCommitCallbacks(execute=True):
                self.client.post(reverse('p2p:book', kwargs={'token': booking.token}),
                                 details_payload(**overrides))
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(reverse('p2p:accept_price', kwargs={'token': booking.token}))
        booking.refresh_from_db()
        self.client.logout()
        return booking

    def test_pickup_collection_refuses_a_receiver_pays_job(self):
        booking = self._confirmed_booking(booker_role='receiver', fee_payer='receiver')
        pickup = PickupTask.objects.filter(order=booking.order).first()
        pickup.driver = self.driver
        pickup.save(update_fields=['driver'])

        self.client.force_login(self.driver_user)
        response = self.client.post(reverse('fleet:p2p_mark_fee_collected'),
                                    {'pickup_id': pickup.pk})
        self.assertFalse(response.json()['success'])
        booking.refresh_from_db()
        self.assertEqual(booking.fee_status, 'pending')

    def test_pickup_collection_still_works_for_a_sender_pays_job(self):
        booking = self._confirmed_booking(booker_role='sender', fee_payer='sender')
        pickup = PickupTask.objects.filter(order=booking.order).first()
        pickup.driver = self.driver
        pickup.save(update_fields=['driver'])

        self.client.force_login(self.driver_user)
        response = self.client.post(reverse('fleet:p2p_mark_fee_collected'),
                                    {'pickup_id': pickup.pk})
        self.assertTrue(response.json()['success'])
        booking.refresh_from_db()
        self.assertEqual(booking.fee_status, 'collected_cash')
        self.assertIsNotNone(booking.fee_txn_id)

    def test_door_collection_refuses_a_sender_pays_job(self):
        booking = self._confirmed_booking(booker_role='sender', fee_payer='sender')
        task = self._task_for(booking)

        self.client.force_login(self.driver_user)
        response = self.client.post(reverse('fleet:p2p_mark_fee_collected_at_delivery'),
                                    {'task_id': task.pk})
        self.assertFalse(response.json()['success'])
        booking.refresh_from_db()
        self.assertEqual(booking.fee_status, 'pending')

    def test_door_collection_books_the_cash_once(self):
        booking = self._confirmed_booking(booker_role='receiver', fee_payer='receiver')
        task = self._task_for(booking)

        self.client.force_login(self.driver_user)
        url = reverse('fleet:p2p_mark_fee_collected_at_delivery')
        self.assertTrue(self.client.post(url, {'task_id': task.pk}).json()['success'])
        booking.refresh_from_db()
        self.assertEqual(booking.fee_status, 'collected_cash')
        self.assertIsNotNone(booking.fee_txn_id)

        # A second tap must not book the money twice.
        first_txn = booking.fee_txn_id
        self.assertTrue(self.client.post(url, {'task_id': task.pk}).json()['already'])
        booking.refresh_from_db()
        self.assertEqual(booking.fee_txn_id, first_txn)

    def test_a_driver_cannot_collect_on_someone_elses_task(self):
        booking = self._confirmed_booking(booker_role='receiver', fee_payer='receiver')
        task = self._task_for(booking, assign=False)

        self.client.force_login(self.driver_user)
        response = self.client.post(reverse('fleet:p2p_mark_fee_collected_at_delivery'),
                                    {'task_id': task.pk})
        self.assertFalse(response.json()['success'])
        booking.refresh_from_db()
        self.assertEqual(booking.fee_status, 'pending')

    def _task_for(self, booking, assign=True):
        """The delivery leg, with this driver on it unless asked otherwise."""
        from delivery.models import DeliveryTask
        task = DeliveryTask.objects.filter(order=booking.order).first()
        if task is None:
            task = DeliveryTask.objects.create(order=booking.order)
        if assign:
            task.driver = self.driver
            task.save(update_fields=['driver'])
        return task


class ConsoleTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed_bands()
        house_business()

    def setUp(self):
        from core.models import Profile
        self.user = User.objects.create_user('owner', 'owner@example.com', 'pw12345!')
        Profile.objects.create(user=self.user, username='owner', is_customer=True,
                               whatsapp='55512345', whatsapp_verified=True)
        self.other = User.objects.create_user('other', 'other@example.com', 'pw12345!')
        self.client.force_login(self.user)
        self.client.post(reverse('p2p:book_start'), accept_payload())
        self.booking = P2PBooking.objects.latest('id')
        self.booking.customer = self.user
        self.booking.save(update_fields=['customer'])
        with patch('p2p.notifications.send_booking_confirmation', return_value=None):
            with self.captureOnCommitCallbacks(execute=True):
                self.client.post(reverse('p2p:book', kwargs={'token': self.booking.token}),
                                 details_payload())
        self.booking.refresh_from_db()
        self.order = self.booking.order

    def test_list_shows_only_my_deliveries(self):
        response = self.client.get(reverse('p2p:my_deliveries'))
        self.assertContains(response, self.order.order_number)

        self.client.force_login(self.other)
        response = self.client.get(reverse('p2p:my_deliveries'))
        self.assertNotContains(response, self.order.order_number)

    def test_detail_is_scoped_to_the_owner(self):
        url = reverse('p2p:delivery_detail', kwargs={'order_number': self.order.order_number})
        self.assertEqual(self.client.get(url).status_code, 200)
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_edit_allowed_at_to_review_and_refused_after(self):
        url = reverse('p2p:delivery_edit', kwargs={'order_number': self.order.order_number})
        self.assertEqual(self.client.get(url).status_code, 200)

        self.order.order_status = 'ready_to_pickup'
        self.order.save()
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)

    def test_edit_cannot_set_order_status(self):
        url = reverse('p2p:delivery_edit', kwargs={'order_number': self.order.order_number})
        self.client.post(url, details_payload(order_status='publish',
                                              customer_name='Edited Name'))
        self.order.refresh_from_db()
        self.assertEqual(self.order.order_status, 'to_review')
        self.assertEqual(self.order.customer_name, 'Edited Name')

    def test_internal_notes_never_reach_the_customer(self):
        OrderComments.objects.create(order=self.order, name='Ops', body='Internal only note',
                                     author_role='staff', is_internal=True)
        OrderComments.objects.create(order=self.order, name='Ops', body='Visible reply',
                                     author_role='staff', is_internal=False)
        response = self.client.get(
            reverse('p2p:delivery_detail', kwargs={'order_number': self.order.order_number}))
        self.assertContains(response, 'Visible reply')
        self.assertNotContains(response, 'Internal only note')

    def test_customer_comment_is_visible_and_attributed(self):
        with patch('p2p.notifications.notify_ops_of_comment', return_value=None):
            self.client.post(
                reverse('p2p:add_comment', kwargs={'order_number': self.order.order_number}),
                {'body': 'Please call before arriving'})
        comment = OrderComments.objects.filter(order=self.order, author=self.user).first()
        self.assertIsNotNone(comment)
        self.assertEqual(comment.author_role, 'client')
        self.assertFalse(comment.is_internal)

    def test_dashboard_sends_a_p2p_customer_to_their_list(self):
        response = self.client.get('/dashboard/')
        self.assertRedirects(response, reverse('p2p:my_deliveries'),
                             fetch_redirect_response=False)


class RateCardScreenTests(TestCase):
    """The ops screen must actually change what customers are quoted."""

    def setUp(self):
        from core.models import Profile
        seed_bands()
        self.staff = User.objects.create_user('opsuser', 'ops@example.com', 'pw12345!')
        self.staff.is_staff = True
        self.staff.save()
        Profile.objects.create(user=self.staff, username='opsuser',
                               is_staff=True, dept_operations=True)
        self.url = reverse('workforce:wf_p2p_rate_card')

    def test_requires_staff(self):
        self.assertEqual(self.client.get(self.url).status_code, 302)
        shopper = User.objects.create_user('shopper', 'shopper@example.com', 'pw12345!')
        self.client.force_login(shopper)
        self.assertNotEqual(self.client.get(self.url).status_code, 200)

    def test_ops_can_open_it(self):
        self.client.force_login(self.staff)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'P2P Rate Card')

    def test_editing_a_price_changes_what_the_customer_is_quoted(self):
        from p2p.pricing import quote
        before = quote(('25.3272', '51.5310'), ('25.1719', '51.5989'),
                       size='s', vehicle='bike', speed='express')
        self.assertEqual(before['price'], Decimal('40'))

        band = P2PRateBand.objects.get(up_to_km=30, needs_quote=False)
        self.client.force_login(self.staff)
        bands = list(P2PRateBand.objects.all().order_by('-priority', 'up_to_km', 'id'))
        # The page posts four formsets inside one <form> — the bands, the box tiers, the
        # vehicle capacities and the box counts. A browser always sends all four, so the
        # test has to as well or nothing saves.
        tiers = list(P2PBoxTier.objects.all().order_by('min_boxes', 'id'))
        caps = list(P2PVehicleCapacity.objects.all().order_by('capacity_cbm', 'id'))
        limits = list(P2PVehicleBoxLimit.objects.all().order_by('vehicle', 'size', 'id'))
        data = {
            'form-TOTAL_FORMS': str(len(bands) + 1),
            'form-INITIAL_FORMS': str(len(bands)),
            'form-MIN_NUM_FORMS': '0',
            'form-MAX_NUM_FORMS': '1000',
            'tiers-TOTAL_FORMS': str(len(tiers) + 1),
            'tiers-INITIAL_FORMS': str(len(tiers)),
            'tiers-MIN_NUM_FORMS': '0',
            'tiers-MAX_NUM_FORMS': '1000',
            'caps-TOTAL_FORMS': str(len(caps) + 1),
            'caps-INITIAL_FORMS': str(len(caps)),
            'caps-MIN_NUM_FORMS': '0',
            'caps-MAX_NUM_FORMS': '1000',
            'limits-TOTAL_FORMS': str(len(limits) + 1),
            'limits-INITIAL_FORMS': str(len(limits)),
            'limits-MIN_NUM_FORMS': '0',
            'limits-MAX_NUM_FORMS': '1000',
        }
        for i, lim in enumerate(limits):
            data[f'limits-{i}-id'] = str(lim.id)
            data[f'limits-{i}-vehicle'] = lim.vehicle
            data[f'limits-{i}-size'] = lim.size
            data[f'limits-{i}-max_boxes'] = ('' if lim.max_boxes is None
                                             else str(lim.max_boxes))
            if lim.is_active:
                data[f'limits-{i}-is_active'] = 'on'
        for i, c in enumerate(caps):
            data[f'caps-{i}-id'] = str(c.id)
            data[f'caps-{i}-vehicle'] = c.vehicle
            data[f'caps-{i}-min_cbm'] = str(c.min_cbm)
            data[f'caps-{i}-capacity_cbm'] = str(c.capacity_cbm)
            if c.is_active:
                data[f'caps-{i}-is_active'] = 'on'
        for i, t in enumerate(tiers):
            data[f'tiers-{i}-id'] = str(t.id)
            data[f'tiers-{i}-min_boxes'] = str(t.min_boxes)
            data[f'tiers-{i}-max_boxes'] = '' if t.max_boxes is None else str(t.max_boxes)
            data[f'tiers-{i}-uplift'] = str(t.uplift)
            if t.needs_quote:
                data[f'tiers-{i}-needs_quote'] = 'on'
            if t.is_active:
                data[f'tiers-{i}-is_active'] = 'on'
        data[f'tiers-{len(tiers)}-min_boxes'] = '1'
        data[f'tiers-{len(tiers)}-uplift'] = '0'
        data[f'tiers-{len(tiers)}-is_active'] = 'on'
        for i, b in enumerate(bands):
            data[f'form-{i}-id'] = str(b.id)
            data[f'form-{i}-min_boxes'] = str(b.min_boxes)
            data[f'form-{i}-max_boxes'] = '' if b.max_boxes is None else str(b.max_boxes)
            data[f'form-{i}-size'] = b.size
            data[f'form-{i}-up_to_kg'] = '' if b.up_to_kg is None else str(b.up_to_kg)
            data[f'form-{i}-vehicle'] = b.vehicle
            data[f'form-{i}-speed'] = b.speed
            data[f'form-{i}-up_to_km'] = '' if b.up_to_km is None else str(b.up_to_km)
            data[f'form-{i}-price'] = '99' if b.id == band.id else str(b.price)
            data[f'form-{i}-priority'] = str(b.priority)
            if b.needs_quote:
                data[f'form-{i}-needs_quote'] = 'on'
            if b.is_active:
                data[f'form-{i}-is_active'] = 'on'
        # The trailing blank row, exactly as a browser posts it: the model defaults are
        # already rendered into it, so an untouched row is unchanged and must be skipped
        # rather than saved as an empty band. (Omitting is_active here would make Django
        # see the row as edited and demand a price for it.)
        blank = len(bands)
        data[f'form-{blank}-min_boxes'] = '1'
        data[f'form-{blank}-priority'] = '0'
        data[f'form-{blank}-is_active'] = 'on'

        count_before = P2PRateBand.objects.count()
        self.client.post(self.url, data)

        band.refresh_from_db()
        self.assertEqual(band.price, Decimal('99'))
        self.assertEqual(P2PRateBand.objects.count(), count_before,
                         'The empty trailing row was saved as a band')

        after = quote(('25.3272', '51.5310'), ('25.1719', '51.5989'),
                      size='s', vehicle='bike', speed='express')
        self.assertEqual(after['price'], Decimal('99'),
                         'Editing the card did not change the customer quote')

    def test_a_priced_row_with_no_price_is_refused(self):
        from p2p.forms import P2PRateBandForm
        form = P2PRateBandForm({'min_boxes': 1, 'priority': 0, 'is_active': 'on',
                                'price': '', 'needs_quote': ''})
        self.assertFalse(form.is_valid())
        self.assertIn('price', form.errors)

    def test_untouched_add_row_does_not_block_saving(self):
        """The blank row at the bottom renders with model defaults, so the browser
        posts them back. If that counted as an edit, every save would fail on a row
        nobody filled in — and take the real edits down with it."""
        from p2p.forms import P2PRateBandForm
        band = P2PRateBand.objects.first()
        form = P2PRateBandForm(
            {'form-0-min_boxes': '1', 'form-0-priority': '0', 'form-0-is_active': 'on'},
            prefix='form-0')
        self.assertFalse(form.has_changed(),
                         'An untouched add-row was treated as an edit')

        filled = P2PRateBandForm(
            {'form-0-min_boxes': '1', 'form-0-priority': '0',
             'form-0-is_active': 'on', 'form-0-price': '30'},
            prefix='form-0')
        self.assertTrue(filled.has_changed(),
                        'A row with a price should be saved')


class TimeWindowTests(TestCase):
    """Both ends of a P2P job are booked as a 3-hour slab, one per section."""

    @classmethod
    def setUpTestData(cls):
        seed_bands()
        house_business()

    def _form(self, **overrides):
        from p2p.forms import BookingDetailsForm
        # booking=None skips the Qatar-bbox check, which is not what these test.
        return BookingDetailsForm(details_payload(**overrides), booking=None)

    def test_slabs_are_three_hours_apart_and_cover_the_working_day(self):
        from p2p.models import P2P_TIME_SLOT_CHOICES
        keys = [key for key, _ in P2P_TIME_SLOT_CHOICES]
        self.assertEqual(keys, ['08:00', '11:00', '14:00', '17:00', '20:00'])
        self.assertEqual(dict(P2P_TIME_SLOT_CHOICES)['14:00'], '2 PM – 5 PM')

    def test_a_stored_time_snaps_onto_the_slab_that_contains_it(self):
        """A row written before the slabs existed must still render its window."""
        from datetime import time
        from p2p.models import slot_from_time, time_from_slot
        self.assertEqual(slot_from_time(time(15, 40)), '14:00')
        self.assertEqual(slot_from_time(time(6, 0)), '08:00')
        self.assertEqual(slot_from_time(time(23, 30)), '20:00')
        self.assertEqual(slot_from_time(None), '')
        self.assertEqual(time_from_slot('14:00'), time(14, 0))
        self.assertIsNone(time_from_slot('13:37'), 'An off-slab time became a window')

    def test_both_windows_are_kept(self):
        form = self._form(speed='standard', pickup_date='2026-09-20',
                          pickup_time='08:00', scheduled_date='2026-09-21',
                          scheduled_time='14:00')
        self.assertTrue(form.is_valid(), form.errors)
        from datetime import date, time
        self.assertEqual(form.cleaned_data['pickup_date'], date(2026, 9, 20))
        self.assertEqual(form.cleaned_data['pickup_time'], time(8, 0))
        self.assertEqual(form.cleaned_data['scheduled_date'], date(2026, 9, 21))
        self.assertEqual(form.cleaned_data['scheduled_time'], time(14, 0))

    def test_a_scheduled_job_needs_a_pickup_day(self):
        form = self._form(speed='standard')
        self.assertFalse(form.is_valid())
        self.assertIn('pickup_date', form.errors)

    def test_a_blank_delivery_day_means_the_pickup_day(self):
        from datetime import date
        form = self._form(speed='standard', pickup_date='2026-09-20', pickup_time='11:00')
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data['scheduled_date'], date(2026, 9, 20))

    def test_express_carries_no_window_at_either_end(self):
        form = self._form(speed='express', pickup_date='2026-09-20',
                          pickup_time='11:00', scheduled_date='2026-09-20',
                          scheduled_time='17:00')
        self.assertTrue(form.is_valid(), form.errors)
        for name in ('pickup_date', 'pickup_time', 'scheduled_date', 'scheduled_time'):
            self.assertIsNone(form.cleaned_data[name], name)

    def test_it_cannot_land_before_it_is_collected(self):
        form = self._form(speed='standard', pickup_date='2026-09-20',
                          scheduled_date='2026-09-19')
        self.assertFalse(form.is_valid())
        self.assertIn('scheduled_date', form.errors)

        same_day = self._form(speed='standard', pickup_date='2026-09-20',
                              pickup_time='17:00', scheduled_date='2026-09-20',
                              scheduled_time='08:00')
        self.assertFalse(same_day.is_valid())
        self.assertIn('scheduled_time', same_day.errors)

    def test_an_off_slab_time_is_refused(self):
        """The select only offers slabs; a hand-crafted POST must not slip past it."""
        form = self._form(speed='standard', pickup_date='2026-09-20', pickup_time='13:37')
        self.assertFalse(form.is_valid())
        self.assertIn('pickup_time', form.errors)


class WindowHandoffTests(TestCase):
    """What the customer picked has to reach the Order the driver works from."""

    @classmethod
    def setUpTestData(cls):
        seed_bands()
        house_business()

    def setUp(self):
        from core.models import Profile
        self.user = User.objects.create_user('sender3', 'sender3@example.com', 'pw12345!')
        Profile.objects.create(user=self.user, username='sender3', is_customer=True,
                               whatsapp='55512345', whatsapp_verified=True)
        self.client.force_login(self.user)

    def _book(self, **overrides):
        self.client.post(reverse('p2p:book_start'), accept_payload())
        booking = P2PBooking.objects.latest('id')
        booking.customer = self.user
        booking.save(update_fields=['customer'])
        with patch('p2p.notifications.send_booking_confirmation', return_value=None):
            with self.captureOnCommitCallbacks(execute=True):
                self.client.post(reverse('p2p:book', kwargs={'token': booking.token}),
                                 details_payload(**overrides))
        booking.refresh_from_db()
        return booking

    def test_the_two_windows_survive_order_creation(self):
        from datetime import date, time
        booking = self._book(speed='standard', pickup_date='2026-09-20',
                             pickup_time='08:00', scheduled_date='2026-09-21',
                             scheduled_time='14:00')
        self.assertEqual(booking.pickup_date, date(2026, 9, 20))
        self.assertEqual(booking.pickup_time, time(8, 0))
        order = booking.order
        self.assertTrue(order.scheduled_delivery)
        self.assertEqual(order.scheduled_date, date(2026, 9, 21))
        self.assertEqual(order.scheduled_time, time(14, 0))

    def test_the_windows_read_back_as_one_line(self):
        booking = self._book(speed='standard', pickup_date='2026-09-20',
                             pickup_time='14:00', scheduled_date='2026-09-20')
        self.assertEqual(booking.pickup_window, '20 Sep, 2 PM – 5 PM')
        self.assertEqual(booking.delivery_window, '20 Sep, any time')

    def test_the_edit_page_saves_a_changed_window(self):
        from datetime import date, time
        booking = self._book(speed='standard', pickup_date='2026-09-20',
                             pickup_time='08:00')
        order = booking.order
        url = reverse('p2p:delivery_edit', kwargs={'order_number': order.order_number})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        # The stored time has to come back selected, not as a blank dropdown.
        self.assertEqual(response.context['form'].initial['pickup_time'], '08:00')

        self.client.post(url, details_payload(
            speed='standard', pickup_date='2026-09-22', pickup_time='17:00',
            scheduled_date='2026-09-23', scheduled_time='11:00'))
        booking.refresh_from_db()
        order.refresh_from_db()
        self.assertEqual(booking.pickup_date, date(2026, 9, 22))
        self.assertEqual(booking.pickup_time, time(17, 0))
        self.assertEqual(order.scheduled_date, date(2026, 9, 23))
        self.assertEqual(order.scheduled_time, time(11, 0))


class DriverPickupWindowTests(TestCase):
    """The window the customer was promised has to reach the driver's card."""

    @classmethod
    def setUpTestData(cls):
        seed_bands()
        house_business()

    def setUp(self):
        from core.models import Profile
        self.user = User.objects.create_user('sender4', 'sender4@example.com', 'pw12345!')
        Profile.objects.create(user=self.user, username='sender4', is_customer=True,
                               whatsapp='55512345', whatsapp_verified=True)

    def _released_booking(self, **overrides):
        """A booking taken all the way to a live first-mile leg."""
        self.client.force_login(self.user)
        self.client.post(reverse('p2p:book_start'), accept_payload())
        booking = P2PBooking.objects.latest('id')
        booking.customer = self.user
        booking.save(update_fields=['customer'])
        with patch('p2p.notifications.send_booking_confirmation', return_value=None):
            with self.captureOnCommitCallbacks(execute=True):
                self.client.post(reverse('p2p:book', kwargs={'token': booking.token}),
                                 details_payload(**overrides))
        booking.refresh_from_db()
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(reverse('p2p:accept_price', kwargs={'token': booking.token}))
        booking.refresh_from_db()
        self.assertEqual(PickupTask.objects.filter(order=booking.order).count(), 1)
        return booking

    def _driver(self):
        from delivery.tests_pickup import make_driver
        return make_driver(41)

    def test_the_pool_card_carries_the_window(self):
        from django.utils import timezone
        day = timezone.localdate() + timedelta(days=2)
        self._released_booking(speed='standard', pickup_date=day.isoformat(),
                               pickup_time='14:00')

        self.client.force_login(self._driver().user)
        response = self.client.get('/fleet/pickups/?tab=available')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Pickup window')
        self.assertContains(response, f'{day.strftime("%-d %b")}, 2 PM – 5 PM')

    def test_a_window_today_is_marked(self):
        from django.utils import timezone
        self._released_booking(speed='standard',
                               pickup_date=timezone.localdate().isoformat(),
                               pickup_time='08:00')
        self.client.force_login(self._driver().user)
        response = self.client.get('/fleet/pickups/?tab=available')
        self.assertContains(response, 'fps__window--today')

    def test_an_express_job_shows_no_window(self):
        """Express has nothing to promise, so the card must not imply one."""
        self._released_booking(speed='express')
        self.client.force_login(self._driver().user)
        response = self.client.get('/fleet/pickups/?tab=available')
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'Pickup window')


class DriverPickupOrderingTests(DriverPickupWindowTests):
    """The driver's own tab is a plan for the day, so it runs in due order."""

    def _accept(self, booking, driver):
        self.client.force_login(driver.user)
        pickup = PickupTask.objects.get(order=booking.order)
        response = self.client.post('/fleet/pickups/accept/', {'pickup_id': pickup.pk})
        self.assertTrue(response.json()['success'], response.json())
        return pickup

    def _positions(self, body, bookings):
        return [body.index(b.order.order_number) for b in bookings]

    def test_mine_runs_in_the_order_the_work_is_due(self):
        from django.utils import timezone
        today = timezone.localdate()
        tomorrow = today + timedelta(days=1)
        driver = self._driver()

        # Deliberately booked in an order that is NOT the due order — under the old
        # newest-first sort these come out exactly reversed, so this test fails if the
        # due-order annotation is dropped.
        express = self._released_booking(speed='express')
        late = self._released_booking(speed='standard', pickup_date=tomorrow.isoformat(),
                                      pickup_time='17:00')
        early = self._released_booking(speed='standard', pickup_date=tomorrow.isoformat(),
                                       pickup_time='08:00')
        anytime_today = self._released_booking(speed='standard',
                                               pickup_date=today.isoformat())

        for booking in (express, late, early, anytime_today):
            self._accept(booking, driver)

        body = self.client.get('/fleet/pickups/?tab=mine').content.decode()
        due = self._positions(body, (express, anytime_today, early, late))
        self.assertEqual(due, sorted(due),
                         'Not in due order: express (due now), then today any-time, '
                         'then tomorrow 8 AM, then tomorrow 5 PM')
        # And it is genuinely not just the old sort with new words on it.
        newest_first = self._positions(body, (anytime_today, early, late, express))
        self.assertNotEqual(newest_first, sorted(newest_first))

    def test_the_pool_tab_is_still_a_feed(self):
        """Only 'mine' is a plan. Re-ordering the pool would shuffle it under the
        thumb of every driver browsing it."""
        from django.utils import timezone
        scheduled = self._released_booking(
            speed='standard',
            pickup_date=(timezone.localdate() + timedelta(days=5)).isoformat(),
            pickup_time='20:00')
        newer = self._released_booking(speed='express')
        self.client.force_login(self._driver().user)
        body = self.client.get('/fleet/pickups/?tab=available').content.decode()
        self.assertLess(body.index(newer.order.order_number),
                        body.index(scheduled.order.order_number))
