# Purpose: Tests for the staff bulk edit grid (order location + delivery fee) and its save endpoint.
# Used by: manage.py test workforce.tests_orders_bulk_edit
# Notes: Routing and QNAS are patched out — no OSRM or QNAS call is made.

import json
from decimal import Decimal
from unittest import mock

from django.test import TestCase
from django.urls import reverse

from business import models as business_models
from core import models as core_models
from delivery import models as delivery_models
from orders import models as orders_models
from workforce.tests_views import WorkforceTestMixin

D = Decimal
SAVE_URL = 'workforce:wf_orders_bulk_edit_save'


class BulkEditTestBase(WorkforceTestMixin, TestCase):
    def setUp(self):
        patcher = mock.patch('delivery.geo.route_distance', return_value=(D('5'), True, 'osrm'))
        patcher.start()
        self.addCleanup(patcher.stop)

        self.staff, _ = self.create_staff_user(username='obestaff')
        self.client.force_login(self.staff)

        self.business = self._make_business(9410, 'OBE001', 'Bulk Client', 71111120)
        for km, price in (('10', '20'), (None, '35')):
            business_models.BusinessDistanceRate.objects.create(
                business=self.business, up_to_km=D(km) if km else None, price=D(price))
        self.pickup = business_models.PickupLocation.objects.create(
            business=self.business, pickup_location_title='Main store', locality='Doha')

    def _make_business(self, business_id, code, name, phone):
        owner = self.create_non_staff_user(username=f'owner{business_id}')
        profile = core_models.Profile.objects.get(user=owner)
        return business_models.Business.objects.create(
            business_id=business_id, user=owner, profile=profile,
            business_name=name, business_code=code, business_status='active')

    def make_order(self, **extra):
        order = orders_models.Order.objects.create(
            business=self.business,
            client_order_code=f'B-{orders_models.Order.objects.count() + 1}',
            customer_name='Cust', customer_phone='55555555',
            customer_address='Somewhere', dl_zone=55, dl_street=10, dl_building=3, **extra)
        order.refresh_from_db()
        return order

    def make_task(self, order, **extra):
        fields = dict(order=order, business=self.business,
                      dl_task_number=f'OBE-{order.pk}-{delivery_models.DeliveryTask.objects.count()}',
                      dl_task_status='pending', dl_price=0)
        fields.update(extra)
        return delivery_models.DeliveryTask.objects.create(**fields)

    def save_rows(self, rows):
        return self.client.post(reverse(SAVE_URL), data=json.dumps({'rows': rows}),
                                content_type='application/json')


class BulkEditPageTests(BulkEditTestBase):
    def test_page_renders_open_orders(self):
        order = self.make_order()
        done = self.make_order(order_status='delivered')
        resp = self.client.get(reverse('workforce:wf_orders_bulk_edit'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, order.order_number)
        self.assertNotContains(resp, done.order_number)

    def test_ids_from_orders_list_include_delivered(self):
        done = self.make_order(order_status='delivered')
        resp = self.client.get(reverse('workforce:wf_orders_bulk_edit') + f'?ids={done.pk}')
        self.assertContains(resp, done.order_number)
        self.assertContains(resp, 'address locked')

    def test_staff_without_ops_desk_turned_away(self):
        other, _ = self.create_staff_user(username='obefin', departments=['fin'])
        self.client.force_login(other)
        resp = self.client.get(reverse('workforce:wf_orders_bulk_edit'))
        self.assertNotEqual(resp.status_code, 200)


class BulkEditFeeTests(BulkEditTestBase):
    def test_typed_fee_is_manual_and_reaches_task(self):
        order = self.make_order()
        task = self.make_task(order)
        resp = self.save_rows([{'id': order.pk, 'dl_amount': '42.50'}])
        self.assertEqual(resp.json()['rows'][0]['status'], 'saved')
        order.refresh_from_db()
        task.refresh_from_db()
        self.assertEqual(order.dl_amount, D('42.50'))
        self.assertEqual(order.dl_amount_source, 'manual')
        self.assertEqual(task.dl_price, D('42.50'))
        # A later save must not let the rate card take it back.
        order.save()
        order.refresh_from_db()
        self.assertEqual(order.dl_amount, D('42.50'))

    def test_zero_fee_goes_back_to_rate_card(self):
        order = self.make_order()
        orders_models.Order.objects.filter(pk=order.pk).update(
            dl_amount=D('50'), dl_amount_source='manual')
        resp = self.save_rows([{'id': order.pk, 'dl_amount': '0'}])
        row = resp.json()['rows'][0]
        self.assertEqual(row['status'], 'saved')
        order.refresh_from_db()
        self.assertEqual(order.dl_amount, D('20.00'))
        self.assertEqual(order.dl_amount_source, 'rate_card')
        self.assertEqual(row['values']['dl_amount'], '20.00')

    def test_delivered_order_fee_still_bills(self):
        order = self.make_order()
        task = self.make_task(order, dl_task_status='delivered')
        orders_models.Order.objects.filter(pk=order.pk).update(order_status='delivered')
        self.save_rows([{'id': order.pk, 'dl_amount': '30'}])
        task.refresh_from_db()
        self.assertEqual(task.dl_price, D('30.00'))

    def test_paid_out_charge_locks_fee(self):
        order = self.make_order()
        task = self.make_task(order, settled_delivery_charge=D('20'), dl_price=D('20'))
        resp = self.save_rows([{'id': order.pk, 'dl_amount': '99'}])
        self.assertEqual(resp.json()['rows'][0]['status'], 'error')
        order.refresh_from_db()
        task.refresh_from_db()
        self.assertEqual(order.dl_amount, D('20.00'))
        self.assertEqual(task.dl_price, D('20.00'))

    def test_bad_fee_rejected_and_nothing_saved(self):
        order = self.make_order()
        resp = self.save_rows([{'id': order.pk, 'dl_amount': 'abc', 'dl_zone': '60'}])
        self.assertEqual(resp.json()['rows'][0]['status'], 'error')
        order.refresh_from_db()
        self.assertEqual(order.dl_zone, 55)

    def test_return_leg_keeps_its_price(self):
        order = self.make_order()
        leg = self.make_task(order, task_leg='return_to_client', dl_price=D('15'))
        self.save_rows([{'id': order.pk, 'dl_amount': '40'}])
        leg.refresh_from_db()
        self.assertEqual(leg.dl_price, D('15.00'))


class BulkEditLocationTests(BulkEditTestBase):
    def test_address_change_geocodes_and_reaches_task_address(self):
        order = self.make_order()
        addr = delivery_models.DlAddressUpdate.objects.get(dl_task_number=order.order_number)
        task = self.make_task(order, dl_task_number=order.order_number, dl_address_update=addr)
        with mock.patch('orders.signals._geocode_address_from_qnas',
                        return_value=(D('25.300000'), D('51.500000'), 'exact')) as geo:
            resp = self.save_rows([{'id': order.pk, 'dl_zone': '60', 'dl_street': '800', 'dl_building': '12'}])
        self.assertEqual(resp.json()['rows'][0]['status'], 'saved')
        geo.assert_called_once_with(60, 800, 12)
        order.refresh_from_db()
        addr.refresh_from_db()
        self.assertEqual((order.dl_zone, order.dl_street, order.dl_building), (60, 800, 12))
        self.assertEqual(order.coords_accuracy, 'exact')
        self.assertEqual((addr.dl_zone, addr.dl_street, addr.dl_building), (60, 800, 12))
        self.assertEqual(addr.dl_latitude, D('25.3'))
        self.assertTrue(task.pk)
        self.assertTrue(orders_models.OrderStatusHistory.objects.filter(
            order=order, field_name='order_edited', notes__startswith='Bulk edit:').exists())

    def test_typed_pin_is_by_staff_and_skips_qnas(self):
        order = self.make_order()
        with mock.patch('orders.signals._geocode_address_from_qnas') as geo:
            self.save_rows([{'id': order.pk, 'dl_zone': '61',
                             'latitude': '25.28', 'longitude': '51.52'}])
        geo.assert_not_called()
        order.refresh_from_db()
        self.assertEqual(order.coords_accuracy, 'by_staff')
        self.assertEqual(order.latitude, D('25.28'))

    def test_pin_outside_qatar_rejected(self):
        order = self.make_order()
        resp = self.save_rows([{'id': order.pk, 'latitude': '51.5', 'longitude': '25.3'}])
        self.assertEqual(resp.json()['rows'][0]['status'], 'error')

    def test_other_clients_pickup_refused(self):
        order = self.make_order()
        other = self._make_business(9411, 'OBE002', 'Other Client', 71111121)
        foreign = business_models.PickupLocation.objects.create(
            business=other, pickup_location_title='Their store', locality='Doha')
        resp = self.save_rows([{'id': order.pk, 'pickup_location': str(foreign.pk)}])
        self.assertEqual(resp.json()['rows'][0]['status'], 'error')
        resp = self.save_rows([{'id': order.pk, 'pickup_location': str(self.pickup.pk)}])
        self.assertEqual(resp.json()['rows'][0]['status'], 'saved')
        order.refresh_from_db()
        self.assertEqual(order.pickup_location_id, self.pickup.pk)

    def test_closed_order_address_locked(self):
        order = self.make_order(order_status='cancelled')
        resp = self.save_rows([{'id': order.pk, 'dl_zone': '70'}])
        self.assertEqual(resp.json()['rows'][0]['status'], 'error')
        order.refresh_from_db()
        self.assertEqual(order.dl_zone, 55)


class BulkEditRequestTests(BulkEditTestBase):
    def test_too_many_rows_rejected(self):
        resp = self.save_rows([{'id': i} for i in range(101)])
        self.assertEqual(resp.status_code, 400)

    def test_empty_body_rejected(self):
        self.assertEqual(self.save_rows([]).status_code, 400)

    def test_unknown_order_reported(self):
        resp = self.save_rows([{'id': 999999, 'dl_amount': '10'}])
        self.assertEqual(resp.json()['rows'][0]['status'], 'error')

    def test_unchanged_row_writes_nothing(self):
        order = self.make_order()
        resp = self.save_rows([{'id': order.pk, 'dl_zone': '55'}])
        self.assertEqual(resp.json()['rows'][0]['status'], 'unchanged')
        self.assertFalse(orders_models.OrderStatusHistory.objects.filter(
            order=order, field_name='order_edited').exists())
