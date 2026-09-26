# Purpose: Tests for the per-client distance rate card and the seller Finance tab save.
# Used by: manage.py test delivery.tests_client_rates
# Notes: Routing is patched out — route_distance is stubbed so no OSRM call is made.

import json
from decimal import Decimal
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase

from business import models as business_models
from core import models as core_models
from delivery import client_rates
from delivery import models as delivery_models
from orders import models as orders_models

User = get_user_model()
D = Decimal


def stub_distance(km):
    return mock.patch('delivery.geo.route_distance',
                      return_value=(D(km), True, 'osrm'))


class RateCardTestBase(TestCase):
    def setUp(self):
        owner = User.objects.create_user(username='ratebiz', password='x')
        profile = core_models.Profile.objects.create(
            user=owner, first_name='Rate', last_name='Biz', phone=71111119)
        self.business = business_models.Business.objects.create(
            business_id=9310, user=owner, profile=profile,
            business_name='Rate Client', business_code='RTE001',
            business_status='active',
        )
        for km, price in (('10', '20'), ('20', '25'), (None, '35')):
            business_models.BusinessDistanceRate.objects.create(
                business=self.business, up_to_km=D(km) if km else None, price=D(price))

    def make_order(self, km, **extra):
        with stub_distance(km):
            order = orders_models.Order.objects.create(
                business=self.business, client_order_code='R-1',
                customer_name='Cust', customer_phone='55555555',
                customer_address='Somewhere', dl_zone=55, **extra)
        order.refresh_from_db()
        return order

    def make_task(self, order, **extra):
        fields = dict(order=order, business=self.business, dl_task_number='RT-1',
                      dl_task_status='pending', dl_price=0)
        fields.update(extra)
        return delivery_models.DeliveryTask.objects.create(**fields)


class BandPriceTests(RateCardTestBase):
    def test_band_edges(self):
        rates = list(self.business.distance_rates.all())
        cases = {'0.5': '20', '10': '20', '10.1': '25', '20': '25', '20.1': '35', '64.6': '35'}
        for km, price in cases.items():
            self.assertEqual(client_rates.band_price(rates, D(km)), D(price), km)

    def test_no_distance_no_price(self):
        self.assertIsNone(client_rates.band_price(list(self.business.distance_rates.all()), None))

    def test_no_open_band_beyond_last_ceiling(self):
        self.business.distance_rates.filter(up_to_km__isnull=True).delete()
        self.assertIsNone(client_rates.band_price(list(self.business.distance_rates.all()), D('30')))


class ApplyRateCardTests(RateCardTestBase):
    def test_new_order_priced_from_distance(self):
        order = self.make_order('12.5')
        self.assertEqual(order.dl_amount, D('25.00'))
        self.assertEqual(order.dl_amount_source, 'rate_card')

    def test_open_task_gets_the_charge(self):
        order = self.make_order('5')
        task = self.make_task(order)
        client_rates.apply_rate_card(order)
        task.refresh_from_db()
        self.assertEqual(task.dl_price, D('20.00'))

    def test_moved_pin_reprices(self):
        order = self.make_order('5')
        with stub_distance('25'):
            order.save()
        order.refresh_from_db()
        self.assertEqual(order.dl_amount, D('35.00'))

    def test_staff_fee_never_overwritten(self):
        order = self.make_order('5')
        orders_models.Order.objects.filter(pk=order.pk).update(
            dl_amount=D('50'), dl_amount_source='manual')
        with stub_distance('25'):
            order.refresh_from_db()
            order.save()
        order.refresh_from_db()
        self.assertEqual(order.dl_amount, D('50.00'))

    def test_legacy_nonzero_fee_kept(self):
        order = self.make_order('5', dl_amount=D('30'))
        self.assertEqual(order.dl_amount, D('30.00'))
        self.assertEqual(order.dl_amount_source, '')

    def test_delivered_and_invoiced_tasks_untouched(self):
        order = self.make_order('5')
        done = self.make_task(order, dl_task_status='delivered', dl_price=D('0'))
        verified = self.make_task(order, dl_task_number='RT-2', verified_delivery_charge=D('18'))
        with stub_distance('15'):
            order.save()
        done.refresh_from_db()
        verified.refresh_from_db()
        self.assertEqual(done.dl_price, D('0.00'))
        self.assertEqual(verified.dl_price, D('0.00'))

    def test_return_leg_untouched(self):
        order = self.make_order('5')
        leg = self.make_task(order, task_leg='return_to_client')
        client_rates.apply_rate_card(order)
        leg.refresh_from_db()
        self.assertEqual(leg.dl_price, D('0.00'))

    def test_delivered_order_not_repriced(self):
        order = self.make_order('5')
        orders_models.Order.objects.filter(pk=order.pk).update(order_status='delivered')
        order.refresh_from_db()
        with stub_distance('25'):
            order.save()
        order.refresh_from_db()
        self.assertEqual(order.dl_amount, D('20.00'))


class FinanceTabSaveTests(RateCardTestBase):
    def setUp(self):
        super().setUp()
        self.staff = User.objects.create_user(
            username='finstaff', password='x', is_staff=True, is_superuser=True)
        self.client.force_login(self.staff)
        self.url = f'/workforce/sellers/{self.business.business_id}/'

    def post(self, rates, pays=True):
        data = {'section': 'finance', 'rates': json.dumps(rates)}
        if pays:
            data['customer_pays_delivery'] = 'on'
        return self.client.post(self.url, data, secure=True, HTTP_HOST='ezzydelivery.qa')

    def test_save_replaces_bands_sets_switch_and_reprices(self):
        order = self.make_order('8')
        self.assertEqual(order.dl_amount, D('20.00'))
        response = self.post([{'up_to_km': '10', 'price': '22'}, {'up_to_km': '', 'price': '40'}])
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()['repriced'], 1)
        self.business.refresh_from_db()
        self.assertTrue(self.business.customer_pays_delivery)
        self.assertEqual(self.business.distance_rates.count(), 2)
        order.refresh_from_db()
        self.assertEqual(order.dl_amount, D('22.00'))

    def test_rejects_two_open_bands(self):
        response = self.post([{'up_to_km': '', 'price': '20'}, {'up_to_km': '', 'price': '30'}])
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.business.distance_rates.count(), 3)

    def test_rejects_non_number(self):
        response = self.post([{'up_to_km': 'ten', 'price': '20'}])
        self.assertEqual(response.status_code, 400)

    def test_switch_off(self):
        self.post([{'up_to_km': '', 'price': '20'}], pays=False)
        self.business.refresh_from_db()
        self.assertFalse(self.business.customer_pays_delivery)


class DoorFeeFlowTests(RateCardTestBase):
    """A customer-pays client end to end: the gate, the split, the message token."""

    def setUp(self):
        super().setUp()
        from fleet import models as fleet_models
        self.business.customer_pays_delivery = True
        self.business.save(update_fields=['customer_pays_delivery'])
        self.driver_user = User.objects.create_user(username='ratedriver', password='x')
        profile = core_models.Profile.objects.create(
            user=self.driver_user, first_name='Rate', last_name='Driver', phone=72222229,
            is_driver=True)
        self.driver = fleet_models.Driver.objects.create(
            driver_id=9311, user=self.driver_user, profile=profile,
            driver_code='RTED1', driver_phone='30000009', driver_whatsapp='30000009',
            driver_languages='english', driver_license_number='RTELIC1',
            driver_status='approved', dashboard_access_enabled=True,
        )
        self.client.force_login(self.driver_user)

    def open_task(self, cod='0', km='5'):
        order = self.make_order(km, cod_amount=D(cod))
        task = self.make_task(order, driver=self.driver, dl_task_status='out_for_delivery',
                              dl_task_publish=True)
        client_rates.apply_rate_card(order)
        task.refresh_from_db()
        return order, task

    def complete(self, task, data):
        return self.client.post(f'/api/driver/tasks/{task.id}/complete/', data)

    def test_fee_only_job_blocked_without_collection(self):
        _, task = self.open_task(cod='0')
        response = self.complete(task, {'status': 'delivered', 'payment_method': 'cash'})
        self.assertEqual(response.status_code, 400)
        self.assertIn('20.00', response.json()['error'])

    def test_fee_only_job_collects_fee(self):
        _, task = self.open_task(cod='0')
        response = self.complete(task, {
            'status': 'delivered', 'cod_collected': 'true',
            'cod_amount_collected': '20.00', 'payment_method': 'cash',
            'payment_split_cash': '20.00'})
        self.assertEqual(response.status_code, 200, response.content)
        task.refresh_from_db()
        self.assertEqual(task.fee_collected_amount, D('20.00'))
        self.assertEqual(task.cod_collected_amount, D('0.00'))

    def test_cod_plus_fee_split(self):
        _, task = self.open_task(cod='1000', km='15')
        response = self.complete(task, {
            'status': 'delivered', 'cod_collected': 'true',
            'cod_amount_collected': '1025.00', 'payment_method': 'cash',
            'payment_split_cash': '1025.00'})
        self.assertEqual(response.status_code, 200, response.content)
        task.refresh_from_db()
        self.assertEqual(task.cod_collected_amount, D('1000.00'))
        self.assertEqual(task.fee_collected_amount, D('25.00'))

    def test_door_fee_books_one_ledger_row(self):
        # No P2P booking here: the fee row used to be written only for P2P, so a
        # customer-pays client's fee cash never reached the COD ledger.
        from fleet.models import DriverTransaction
        _, task = self.open_task(cod='1000', km='15')
        data = {'status': 'delivered', 'cod_collected': 'true',
                'cod_amount_collected': '1025.00', 'payment_method': 'cash',
                'payment_split_cash': '1025.00'}
        self.assertEqual(self.complete(task, data).status_code, 200)
        self.complete(task, data)  # a retried submit must not book it twice
        fees = DriverTransaction.objects.filter(
            delivery_task=task, transaction_type='fee_collection')
        self.assertEqual(list(fees.values_list('amount', 'payment_method')),
                         [(D('25.00'), 'cash')])
        cod = DriverTransaction.objects.get(
            delivery_task=task, transaction_type='cod_collection')
        self.assertEqual(cod.amount, D('1000.00'))

    def test_mixed_split_fee_not_counted_twice(self):
        from fleet.wallet_service import WalletService
        _, task = self.open_task(cod='1000', km='15')  # 1000 COD + 25 fee = 1025
        response = self.complete(task, {
            'status': 'delivered', 'cod_collected': 'true',
            'cod_amount_collected': '1025.00', 'payment_method': 'fawran',
            'payment_split_fawran': '1000.00', 'payment_split_cash': '25.00'})
        self.assertEqual(response.status_code, 200, response.content)
        task.refresh_from_db()
        self.assertEqual(task.fee_collected_amount, D('25.00'))
        # The driver physically holds the 25 cash, once.
        self.assertEqual(WalletService.task_cash_leg(task), D('25.00'))
        self.assertEqual(WalletService.live_cod_in_hand(self.driver), D('25.00'))

    def test_message_tokens_match_the_door(self):
        from core.trigger_tokens import build_context
        order, task = self.open_task(cod='100', km='25')
        ctx = build_context(order, task, body='{amount_to_pay} {delivery_fee}')
        self.assertEqual(ctx['amount_to_pay'], '135.00')
        self.assertEqual(ctx['delivery_fee'], '35.00')
        self.assertEqual(ctx['cod_amount'], '100.00')

    def online_paid_task(self):
        order, task = self.open_task(cod='0')
        orders_models.Order.objects.filter(pk=order.pk).update(cod_status_by_client='online_paid')
        task.refresh_from_db()
        return order, task

    def test_online_paid_still_collects_the_fee(self):
        # For a customer-pays client, online_paid covers the goods, not delivery.
        from delivery.collect import amount_to_collect
        _, task = self.online_paid_task()
        self.assertEqual(amount_to_collect(task).total, D('20.00'))
        blocked = self.complete(task, {'status': 'delivered', 'payment_method': 'cash'})
        self.assertEqual(blocked.status_code, 400)
        response = self.complete(task, {
            'status': 'delivered', 'cod_collected': 'true',
            'cod_amount_collected': '20.00', 'payment_method': 'cash',
            'payment_split_cash': '20.00'})
        self.assertEqual(response.status_code, 200, response.content)
        task.refresh_from_db()
        self.assertEqual((task.cod_collected_amount, task.fee_collected_amount), (D('0.00'), D('20.00')))

    def test_online_paid_without_switch_collects_nothing(self):
        from delivery.collect import amount_to_collect
        self.business.customer_pays_delivery = False
        self.business.save(update_fields=['customer_pays_delivery'])
        _, task = self.online_paid_task()
        self.assertEqual(amount_to_collect(task).total, D('0.00'))
        response = self.complete(task, {'status': 'delivered', 'payment_method': 'cash'})
        self.assertEqual(response.status_code, 200, response.content)

    def test_partial_delivery_splits_the_fee(self):
        from fleet.models import DriverTransaction
        order, task = self.online_paid_task()
        keep = orders_models.OrderItem.objects.create(order=order, quantity=1)
        back = orders_models.OrderItem.objects.create(order=order, quantity=1)
        response = self.client.post(
            f'/fleet/tasks/{task.id}/partial-delivery/',
            data=json.dumps({'items': [{'order_item_id': back.id, 'qty_returned': 1}],
                             'actual_cod': 20, 'payment_method': 'cash'}),
            content_type='application/json')
        self.assertTrue(response.json().get('success'), response.content)
        task.refresh_from_db()
        self.assertEqual((task.cod_collected_amount, task.fee_collected_amount), (D('0.00'), D('20.00')))
        self.assertTrue(DriverTransaction.objects.filter(
            delivery_task=task, transaction_type='fee_collection', amount=D('20.00')).exists())
        self.assertFalse(DriverTransaction.objects.filter(
            delivery_task=task, transaction_type='cod_collection', amount__gt=0).exists())
        keep.refresh_from_db()


class StaffFeeEditTests(RateCardTestBase):
    """The staff edit forms: '20.00' must not zero the fee, and a typed fee is pinned."""

    def setUp(self):
        super().setUp()
        self.staff = User.objects.create_user(
            username='feestaff', password='x', is_staff=True, is_superuser=True)
        self.client.force_login(self.staff)

    def test_helper(self):
        from workforce.views import _set_order_fee_from_post
        order = self.make_order('5')  # rate card: 20.00
        _set_order_fee_from_post(order, '20.00')
        self.assertEqual(order.dl_amount_source, 'rate_card')  # unchanged value, untouched
        _set_order_fee_from_post(order, '42')
        self.assertEqual((order.dl_amount, order.dl_amount_source), (D('42'), 'manual'))
        _set_order_fee_from_post(order, 'abc')
        self.assertEqual(order.dl_amount, D('42'))
        _set_order_fee_from_post(order, '0')
        self.assertEqual((order.dl_amount, order.dl_amount_source), (D('0'), ''))


class CodLedgerTests(RateCardTestBase):
    """The COD ledger must list a door fee, and find collections booked without a business."""

    def setUp(self):
        super().setUp()
        from fleet import models as fleet_models
        user = User.objects.create_user(username='ledgerdriver', password='x')
        profile = core_models.Profile.objects.create(
            user=user, first_name='Led', last_name='Ger', phone=72222228, is_driver=True)
        self.driver = fleet_models.Driver.objects.create(
            driver_id=9312, user=user, profile=profile, driver_code='LEDG1',
            driver_phone='30000008', driver_whatsapp='30000008', driver_languages='english',
            driver_license_number='LEDLIC1', driver_status='approved')
        order = self.make_order('5', cod_amount=D('100'))
        self.task = self.make_task(order, driver=self.driver, dl_task_status='delivered')
        for kind, amount, biz in (('cod_collection', D('100'), None),
                                  ('fee_collection', D('20'), self.business)):
            fleet_models.DriverTransaction.objects.create(
                driver=self.driver, transaction_type=kind, amount=amount,
                description=kind, delivery_task=self.task, business=biz)
        staff = User.objects.create_user(
            username='ledgerstaff', password='x', is_staff=True, is_superuser=True)
        self.client.force_login(staff)

    def test_client_filter_finds_both_rows(self):
        response = self.client.get(
            f'/workforce/fleet/cash-ledger/?business_id={self.business.business_id}',
            secure=True, HTTP_HOST='ezzydelivery.qa')
        self.assertEqual(response.status_code, 200)
        # The tiles are live balances now; the rows are what the filter controls.
        # COD + fee from one door are shown as one row: the fee rides on the COD row.
        self.assertEqual(response.context['totals']['count'], 1)
        (row,) = response.context['transactions']
        self.assertEqual(row.transaction_type, 'cod_collection')
        self.assertEqual(row.merged_fee.amount, D('20'))


class StaffDeliveredDoorMoneyTests(RateCardTestBase):
    """Staff marking a task delivered books COD + the door fee like the driver app,
    and only after staff confirm the figures."""

    def setUp(self):
        super().setUp()
        from fleet import models as fleet_models
        self.business.customer_pays_delivery = True
        self.business.save(update_fields=['customer_pays_delivery'])
        user = User.objects.create_user(username='staffdoordrv', password='x')
        profile = core_models.Profile.objects.create(
            user=user, first_name='Door', last_name='Driver', phone=72222227, is_driver=True)
        self.driver = fleet_models.Driver.objects.create(
            driver_id=9313, user=user, profile=profile, driver_code='SDOR1',
            driver_phone='30000007', driver_whatsapp='30000007', driver_languages='english',
            driver_license_number='SDORLIC1', driver_status='approved')
        staff = User.objects.create_user(
            username='doorstaff', password='x', is_staff=True, is_superuser=True)
        self.client.force_login(staff)

    def open_task(self, cod='1000', km='15', driver=True):
        order = self.make_order(km, cod_amount=D(cod))
        task = self.make_task(order, driver=self.driver if driver else None,
                              dl_task_status='out_for_delivery', dl_task_publish=True)
        client_rates.apply_rate_card(order)
        task.refresh_from_db()
        return task

    def post(self, url, body):
        return self.client.post(url, json.dumps(body), content_type='application/json',
                                secure=True, HTTP_HOST='ezzydelivery.qa')

    def status(self, task, **extra):
        return self.post(f'/workforce/delivery-task/{task.id}/update-status/',
                         dict(status='delivered', **extra))

    def rows(self, task):
        from fleet.models import DriverTransaction
        return sorted(DriverTransaction.objects.filter(delivery_task=task)
                      .values_list('transaction_type', 'amount'))

    def test_asks_to_confirm_cod_plus_fee_and_changes_nothing(self):
        task = self.open_task()
        response = self.status(task)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()['collect'],
                         {'cod': '1000.00', 'fee': '25.00', 'total': '1025.00'})
        task.refresh_from_db()
        self.assertEqual(task.dl_task_status, 'out_for_delivery')
        self.assertEqual(self.rows(task), [])

    def test_confirmed_books_cod_and_fee_rows(self):
        task = self.open_task()
        response = self.status(task, confirm_collection=True, collected_total='1025.00')
        self.assertEqual(response.status_code, 200, response.content)
        task.refresh_from_db()
        self.assertEqual((task.dl_task_status, task.cod_collected_amount, task.fee_collected_amount),
                         ('delivered', D('1000.00'), D('25.00')))
        self.assertEqual(self.rows(task),
                         [('cod_collection', D('1000.00')), ('fee_collection', D('25.00'))])

    def test_fee_only_online_paid_task(self):
        task = self.open_task(cod='0', km='5')
        orders_models.Order.objects.filter(pk=task.order_id).update(cod_status_by_client='online_paid')
        self.assertEqual(self.status(task).json()['collect']['total'], '20.00')
        self.assertEqual(self.status(task, confirm_collection=True).status_code, 200)
        self.assertEqual(self.rows(task), [('fee_collection', D('20.00'))])

    def test_money_due_without_driver_is_refused(self):
        task = self.open_task(driver=False)
        response = self.status(task, confirm_collection=True)
        self.assertEqual(response.status_code, 400)
        self.assertIn('1025.00', response.json()['error'])

    def test_nothing_due_needs_no_confirmation(self):
        self.business.customer_pays_delivery = False
        self.business.save(update_fields=['customer_pays_delivery'])
        task = self.open_task(cod='0')
        self.assertEqual(self.status(task).status_code, 200)
        self.assertEqual(self.rows(task), [])

    def test_bulk_delivered_confirms_then_books(self):
        task = self.open_task()
        body = {'task_ids': [task.id], 'status': 'delivered'}
        first = self.post('/workforce/tasks/bulk-update-status/', body)
        self.assertEqual(first.status_code, 409)
        self.assertEqual(first.json()['collect']['total'], '1025.00')
        self.assertEqual(self.rows(task), [])
        body['confirm_collection'] = True
        self.assertEqual(self.post('/workforce/tasks/bulk-update-status/', body).status_code, 200)
        self.assertEqual(self.rows(task),
                         [('cod_collection', D('1000.00')), ('fee_collection', D('25.00'))])
