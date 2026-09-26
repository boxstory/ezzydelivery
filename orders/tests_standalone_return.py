# Purpose: Tests for a return claim raised against goods EzzyDelivery never delivered.
# Used by: manage.py test orders.tests_standalone_return
# Notes: The claim carries its own collection address (ReturnRequest's standalone block), so the
#        route assertions here are the contract that the address survives onto the collection.

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from business import models as business_models
from core import models as core_models
from delivery.selectors import task_destination, task_origin
from orders import models as orders_models
from orders.services import (
    can_schedule_return_pickup, create_return_pickup_order,
    create_standalone_return_request,
)

User = get_user_model()

_SEQ = [9600]


def _fixtures():
    """A client with one counter, and a staff member. No order anywhere — that
    absence is the whole point of these tests."""
    _SEQ[0] += 1
    idx = _SEQ[0]

    biz_user = User.objects.create_user(username=f'sr_biz_{idx}', password='x')
    biz_profile = core_models.Profile.objects.create(
        user=biz_user, first_name='S', last_name='R', phone=95000000 + idx)
    business = business_models.Business.objects.create(
        business_id=idx, user=biz_user, profile=biz_profile,
        business_name=f'SR Biz {idx}', business_code=f'SR{idx}',
        business_status='active')
    pickup = business_models.PickupLocation.objects.create(
        business=business, pickup_location_title='Client Counter',
        locality='Al Sadd', pickup_zone_no=38, pickup_street_no=850,
        pickup_building_no=12, pickup_lat=Decimal('25.280000'),
        pickup_lon=Decimal('51.500000'))
    staff = User.objects.create_user(
        username=f'sr_staff_{idx}', password='x', is_staff=True)
    return business, pickup, staff


def _claim(business, pickup, staff=None, **over):
    fields = dict(
        reason='customer_changed_mind',
        pickup_location=pickup,
        customer_name='Buyer',
        customer_phone='97455500000',
        customer_address='Flat 3, Tower B',
        zone=55, street=204, building=53,
        latitude=Decimal('25.246386'), longitude=Decimal('51.465587'),
        external_reference='INV-9001',
        package_description='2 dresses, boxed',
        package_qty=2,
        collection_charge=Decimal('20.00'),
        user=staff,
    )
    fields.update(over)
    return create_standalone_return_request(business, **fields)


class StandaloneClaimTests(TestCase):
    """What the claim refuses to be created without."""

    def test_a_claim_with_no_order_knows_it_is_standalone(self):
        business, pickup, staff = _fixtures()
        ret = _claim(business, pickup, staff)
        self.assertTrue(ret.is_standalone)
        self.assertIsNone(ret.order_id)
        self.assertEqual(ret.business, business)

    def test_it_opens_approved_and_records_who_raised_it(self):
        business, pickup, staff = _fixtures()
        ret = _claim(business, pickup, staff)
        # Nobody is waiting for a seller to approve paperwork they never filed.
        self.assertEqual(ret.status, 'approved')
        self.assertEqual(ret.reviewed_by, staff)
        self.assertIsNotNone(ret.reviewed_at)

    def test_it_never_carries_a_cod_reversal(self):
        business, pickup, staff = _fixtures()
        ret = _claim(business, pickup, staff)
        # We collected nothing on these goods, so we owe nothing back.
        self.assertEqual(ret.cod_reversal_amount, Decimal('0.00'))

    def test_a_dropoff_belonging_to_another_client_is_refused(self):
        business, pickup, staff = _fixtures()
        other_business, other_pickup, _ = _fixtures()
        with self.assertRaises(ValidationError) as caught:
            _claim(business, other_pickup, staff)
        self.assertIn('different client', str(caught.exception))
        self.assertEqual(orders_models.ReturnRequest.objects.count(), 0)

    def test_a_claim_with_no_dropoff_is_refused(self):
        business, pickup, staff = _fixtures()
        with self.assertRaises(ValidationError) as caught:
            _claim(business, None, staff)
        self.assertIn('where the driver drops', str(caught.exception))

    def test_a_claim_with_no_way_to_find_the_customer_is_refused(self):
        business, pickup, staff = _fixtures()
        with self.assertRaises(ValidationError) as caught:
            _claim(business, pickup, staff, customer_phone='',
                   customer_address='', zone=None)
        self.assertIn('has to find the customer', str(caught.exception))
        self.assertEqual(orders_models.ReturnRequest.objects.count(), 0)

    def test_an_unknown_reason_is_refused(self):
        business, pickup, staff = _fixtures()
        with self.assertRaises(ValidationError):
            _claim(business, pickup, staff, reason='because')

    def test_a_negative_charge_is_refused(self):
        business, pickup, staff = _fixtures()
        with self.assertRaises(ValidationError):
            _claim(business, pickup, staff, collection_charge=Decimal('-1.00'))


class StandaloneResolverTests(TestCase):
    """claim_* answers the same questions for both kinds of claim."""

    def test_the_claim_answers_from_its_own_snapshot(self):
        business, pickup, staff = _fixtures()
        ret = _claim(business, pickup, staff)
        self.assertEqual(ret.claim_customer_name, 'Buyer')
        self.assertEqual(ret.claim_customer_phone, '97455500000')
        self.assertEqual(ret.claim_zone, 55)
        self.assertEqual(ret.claim_pickup_location, pickup)
        self.assertEqual(ret.claim_charge, Decimal('20.00'))

    def test_the_heading_names_the_clients_own_reference(self):
        business, pickup, staff = _fixtures()
        ret = _claim(business, pickup, staff)
        self.assertIn('INV-9001', ret.reference_label)
        self.assertIn('not delivered by EzzyDelivery', ret.reference_label)

    def test_a_claim_whose_dropoff_was_deleted_cannot_be_collected(self):
        business, pickup, staff = _fixtures()
        ret = _claim(business, pickup, staff)
        pickup.delete()
        ret.refresh_from_db()
        ok, why = can_schedule_return_pickup(ret)
        self.assertFalse(ok)
        self.assertIn('nowhere to take the goods', why)


class StandaloneCollectionTests(TestCase):
    """The collection trip, raised off a claim with no order behind it."""

    def _collection(self, **over):
        business, pickup, staff = _fixtures()
        ret = _claim(business, pickup, staff, **over)
        order = create_return_pickup_order(ret, user=staff, publish=True)
        # The service writes the link onto its own locked re-read of the claim,
        # so this instance is stale the moment it returns.
        ret.refresh_from_db()
        return ret, order, pickup

    def test_an_approved_standalone_claim_can_be_collected(self):
        business, pickup, staff = _fixtures()
        ok, why = can_schedule_return_pickup(_claim(business, pickup, staff))
        self.assertTrue(ok, why)

    def test_the_collection_carries_the_claims_own_address(self):
        ret, order, pickup = self._collection()
        self.assertEqual(order.order_type, 'return_pickup')
        self.assertEqual(order.business, ret.business)
        self.assertEqual(order.customer_name, 'Buyer')
        self.assertEqual(order.customer_phone, '97455500000')
        self.assertEqual(order.dl_zone, 55)
        self.assertEqual(order.dl_street, 204)
        self.assertEqual(order.pickup_location, pickup)
        self.assertEqual(order.cod_amount, Decimal('0.00'))

    def test_the_driver_collects_at_the_customer_and_drops_at_the_client(self):
        ret, order, pickup = self._collection()
        task = order.delivery_task.get()
        self.assertEqual(task.task_leg, 'collect_from_customer')
        origin = task_origin(task)
        self.assertEqual(origin.label, 'Buyer')
        self.assertEqual(origin.latitude, Decimal('25.246386'))
        destination = task_destination(task)
        self.assertFalse(destination.is_customer)
        self.assertEqual(destination.address_text, pickup.pickup_location_title)

    def test_the_charge_defaults_to_the_figure_staff_named(self):
        _, order, _ = self._collection()
        self.assertEqual(order.dl_amount, Decimal('20.00'))

    def test_a_claim_raised_without_a_charge_collects_for_nothing(self):
        _, order, _ = self._collection(collection_charge=None)
        self.assertEqual(order.dl_amount, Decimal('0.00'))

    def test_the_collection_code_hangs_off_the_return_number(self):
        ret, order, _ = self._collection()
        self.assertEqual(order.client_order_code, f'{ret.return_number}-RP1')

    def test_the_description_falls_back_to_the_claims_goods(self):
        _, order, _ = self._collection()
        self.assertEqual(order.package_description, '2 dresses, boxed')
        self.assertEqual(order.package_qty, 2)

    def test_it_comments_on_the_collection_and_names_the_claim(self):
        ret, order, _ = self._collection()
        body = order.order_comments.first().body
        self.assertIn(ret.return_number, body)
        self.assertIn('not delivered by EzzyDelivery', body)

    def test_the_claim_is_linked_and_scheduled(self):
        ret, order, _ = self._collection()
        self.assertEqual(ret.pickup_order, order)
        self.assertEqual(ret.status, 'pickup_scheduled')

    def test_a_second_collection_is_refused(self):
        ret, _, _ = self._collection()
        ok, why = can_schedule_return_pickup(ret)
        self.assertFalse(ok)
        self.assertIn('already raised', why)

    def test_the_claim_follows_the_van(self):
        ret, order, _ = self._collection()
        task = order.delivery_task.get()
        for status in ('picked_up', 'out_for_delivery', 'delivered'):
            task.dl_task_status = status
            task._status_actor = 'staff'
            task.save()
            task.refresh_from_db()
        ret.refresh_from_db()
        self.assertEqual(ret.status, 'received')


class StandaloneFormTests(TestCase):
    """The staff page — the only way one of these claims is born."""

    def _staff(self, username='sr_form_staff'):
        from core.departments import ASSIGNABLE_DEPARTMENTS, DEPARTMENT_FIELDS
        user = User.objects.create_user(
            username=username, password='Staff@123', is_staff=True)
        core_models.Profile.objects.create(
            user=user, first_name='S', last_name='T', phone=22222222,
            is_staff=True,
            **{DEPARTMENT_FIELDS[code]: True for code in ASSIGNABLE_DEPARTMENTS})
        self.client.login(username=username, password='Staff@123')
        return user

    def _url(self):
        return reverse('workforce:returns_request_create')

    def _payload(self, business, pickup, over=None):
        data = {
            'business': business.business_id,
            'pickup_location': pickup.id,
            'reason': 'damaged',
            'reason_notes': 'Client says the box arrived crushed',
            'external_reference': 'INV-77',
            'package_description': 'One lamp',
            'package_qty': '1',
            'collection_charge': '18.00',
            'customer_name': 'Buyer',
            'customer_phone': '97455500001',
            'customer_address': 'Flat 9',
            'dl_zone': '55', 'dl_street': '204', 'dl_building': '53',
            'latitude': '25.246386', 'longitude': '51.465587',
        }
        data.update(over or {})
        return data

    def test_staff_can_open_the_form(self):
        business, pickup, _ = _fixtures()
        self._staff()
        resp = self.client.get(self._url())
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, business.business_name)
        self.assertContains(resp, pickup.pickup_location_title)

    def test_it_raises_the_claim_and_sends_staff_to_the_desk(self):
        business, pickup, _ = _fixtures()
        self._staff()
        resp = self.client.post(self._url(), self._payload(business, pickup))
        self.assertEqual(resp.status_code, 302)
        ret = orders_models.ReturnRequest.objects.get()
        self.assertTrue(ret.is_standalone)
        self.assertEqual(ret.business, business)
        self.assertEqual(ret.pickup_location, pickup)
        self.assertEqual(ret.external_reference, 'INV-77')
        self.assertEqual(ret.collection_charge, Decimal('18.00'))
        self.assertEqual(ret.dl_zone, 55)
        self.assertIn(ret.return_number, resp['Location'])

    def test_the_whatsapp_number_falls_back_to_the_phone(self):
        business, pickup, _ = _fixtures()
        self._staff()
        self.client.post(self._url(),
                         self._payload(business, pickup,
                                       {'customer_whatsapp': ''}))
        ret = orders_models.ReturnRequest.objects.get()
        self.assertTrue(ret.customer_whatsapp)

    def test_a_dropoff_from_another_client_writes_nothing(self):
        business, _, _ = _fixtures()
        _, other_pickup, _ = _fixtures()
        self._staff()
        resp = self.client.post(self._url(),
                                self._payload(business, other_pickup))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(orders_models.ReturnRequest.objects.count(), 0)

    def test_a_claim_with_no_client_writes_nothing(self):
        business, pickup, _ = _fixtures()
        self._staff()
        resp = self.client.post(self._url(),
                                self._payload(business, pickup, {'business': ''}))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(orders_models.ReturnRequest.objects.count(), 0)

    def test_a_seller_cannot_open_it(self):
        business, pickup, _ = _fixtures()
        self.client.login(username=business.user.username, password='x')
        resp = self.client.get(self._url())
        self.assertNotEqual(resp.status_code, 200)
        self.assertEqual(
            self.client.post(self._url(),
                             self._payload(business, pickup)).status_code // 100,
            3)
        self.assertEqual(orders_models.ReturnRequest.objects.count(), 0)


class StandaloneScheduleEndpointTests(TestCase):
    """The Schedule pickup button, on a claim with no order behind it. The
    timeline write used to name ret.order unconditionally, which on one of these
    is None — an IntegrityError swallowed by the logger and no trail at all."""

    def _staff(self):
        from core.departments import ASSIGNABLE_DEPARTMENTS, DEPARTMENT_FIELDS
        user = User.objects.create_user(
            username='sr_sched_staff', password='Staff@123', is_staff=True)
        core_models.Profile.objects.create(
            user=user, first_name='S', last_name='P', phone=44444444,
            is_staff=True,
            **{DEPARTMENT_FIELDS[code]: True for code in ASSIGNABLE_DEPARTMENTS})
        self.client.login(username='sr_sched_staff', password='Staff@123')
        return user

    def test_it_raises_the_collection_and_records_the_move(self):
        business, pickup, staff = _fixtures()
        ret = _claim(business, pickup, staff)
        self._staff()
        resp = self.client.post(
            reverse('workforce:returns_request_schedule_pickup', args=[ret.id]),
            data='{"charge": "35.00"}', content_type='application/json')
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(body['success'])

        ret.refresh_from_db()
        self.assertEqual(ret.status, 'pickup_scheduled')
        self.assertEqual(ret.pickup_order.dl_amount, Decimal('35.00'))
        # The collection is the only order this claim ever had, so it carries
        # the timeline entry the outbound order would have.
        history = orders_models.OrderStatusHistory.objects.filter(
            order=ret.pickup_order, field_name='return_status')
        self.assertEqual(history.count(), 1)
        self.assertIn(ret.return_number, history.get().notes)

    def test_a_status_change_before_any_collection_is_kept_on_the_claim(self):
        business, pickup, staff = _fixtures()
        ret = _claim(business, pickup, staff)
        self._staff()
        resp = self.client.post(
            reverse('workforce:returns_request_set_status', args=[ret.id]),
            data='{"status": "closed", "notes": "client collected it himself"}',
            content_type='application/json')
        self.assertEqual(resp.status_code, 200)
        ret.refresh_from_db()
        self.assertEqual(ret.status, 'closed')
        self.assertIn('collected it himself', ret.review_notes)
        # Nowhere to write a timeline entry, and nothing pretends otherwise.
        self.assertEqual(
            orders_models.OrderStatusHistory.objects.filter(
                field_name='return_status').count(), 0)


class StandaloneConsoleTests(TestCase):
    """Both consoles render a claim with no order behind it — every one of these
    pages used to reverse an order URL unconditionally."""

    def _staff(self):
        from core.departments import ASSIGNABLE_DEPARTMENTS, DEPARTMENT_FIELDS
        user = User.objects.create_user(
            username='sr_console_staff', password='Staff@123', is_staff=True)
        core_models.Profile.objects.create(
            user=user, first_name='S', last_name='C', phone=33333333,
            is_staff=True,
            **{DEPARTMENT_FIELDS[code]: True for code in ASSIGNABLE_DEPARTMENTS})
        self.client.login(username='sr_console_staff', password='Staff@123')
        return user

    def test_the_staff_desk_lists_it(self):
        business, pickup, staff = _fixtures()
        ret = _claim(business, pickup, staff)
        self._staff()
        resp = self.client.get(
            reverse('workforce:returns_requests_list'), {'status': 'all'})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, ret.return_number)
        self.assertContains(resp, 'Not delivered by us')

    def test_the_client_sees_it_on_their_own_returns_page(self):
        business, pickup, staff = _fixtures()
        ret = _claim(business, pickup, staff)
        self.client.login(username=business.user.username, password='x')
        listing = self.client.get(reverse('business:returns_list'))
        self.assertEqual(listing.status_code, 200)
        self.assertContains(listing, ret.return_number)

        detail = self.client.get(reverse('business:return_detail', args=[ret.id]))
        self.assertEqual(detail.status_code, 200)
        self.assertContains(detail, 'INV-9001')
        self.assertContains(detail, 'Buyer')
