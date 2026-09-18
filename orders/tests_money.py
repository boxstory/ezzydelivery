# Purpose: Tests for the refund ceiling and the leg that pays a refund (orders/money.py).
# Used by: manage.py test orders.tests_money
# Notes: The ceiling must stay net of refunds already made, and must never be derived from
#        item prices — most real orders have no priced items at all.

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from business import models as business_models
from core import models as core_models
from delivery import models as delivery_models
from fleet import models as fleet_models
from orders import models as orders_models
from orders import money

User = get_user_model()

_SEQ = [7300]


def _fixtures(cod=Decimal('300.00'), collected=None, payment_method='cash',
              with_driver=True, settled=False):
    """One business + order + (optionally) a driver and a collecting task."""
    _SEQ[0] += 1
    idx = _SEQ[0]

    biz_user = User.objects.create_user(username=f'mny_biz_{idx}', password='x')
    biz_profile = core_models.Profile.objects.create(
        user=biz_user, first_name='M', last_name='B', phone=41000000 + idx)
    business = business_models.Business.objects.create(
        business_id=idx, user=biz_user, profile=biz_profile,
        business_name=f'Money Biz {idx}', business_code=f'MNY{idx}',
        business_status='active')
    order = orders_models.Order.objects.create(
        business=business, client_order_code=f'MNY-ORD-{idx}',
        customer_name='C', customer_phone='111', customer_address='Z',
        cod_amount=cod, order_status='delivered')

    driver = None
    if with_driver:
        drv_user = User.objects.create_user(username=f'mny_drv_{idx}', password='x')
        drv_profile = core_models.Profile.objects.create(
            user=drv_user, first_name='M', last_name='D', phone=42000000 + idx)
        driver = fleet_models.Driver.objects.create(
            driver_id=idx, user=drv_user, profile=drv_profile,
            driver_code=f'MD{idx}', driver_phone='222', driver_whatsapp='222',
            driver_languages='english', driver_license_number=f'L{idx}',
            driver_status='approved', cod_in_hand=Decimal('0.00'))

    task = None
    if collected is not None:
        task = delivery_models.DeliveryTask.objects.create(
            dl_task_number=f'MNY-T-{idx}', order=order, business=business, driver=driver,
            dl_task_status='delivered', cod_collected=True, cod_settled=False,
            cod_collected_amount=collected, cod_collected_at=timezone.now(),
            completed_at=timezone.now(), payment_method=payment_method,
            cod_client_settled=settled)

    return business, order, driver, task


def _refund(task, amount):
    """A cod_return row exactly as WalletService.record_cod_return writes it."""
    return fleet_models.DriverTransaction.objects.create(
        driver=task.driver, transaction_type='cod_return', amount=Decimal(amount),
        description='test refund', delivery_task=task)


class CollectedForTests(TestCase):
    def test_full_collection(self):
        _, order, _, _ = _fixtures(collected=Decimal('300.00'))
        self.assertEqual(money.collected_for(order), Decimal('300.00'))

    def test_partial_collection_counts_only_what_was_taken(self):
        _, order, _, _ = _fixtures(cod=Decimal('300.00'), collected=Decimal('120.00'))
        self.assertEqual(money.collected_for(order), Decimal('120.00'))

    def test_prepaid_order_has_nothing_to_hand_back(self):
        """cod_amount is large but nothing was ever collected."""
        _, order, _, _ = _fixtures(cod=Decimal('500.00'), collected=None)
        self.assertEqual(money.collected_for(order), Decimal('0.00'))
        self.assertEqual(money.refund_ceiling(order), Decimal('0.00'))

    def test_ceiling_is_net_of_refunds_already_made(self):
        """The bug in the old _collected_cod_for: two returns each saw the full amount."""
        _, order, _, task = _fixtures(collected=Decimal('300.00'))
        _refund(task, '100.00')
        self.assertEqual(money.refunded_for(order), Decimal('100.00'))
        self.assertEqual(money.refund_ceiling(order), Decimal('200.00'))

    def test_two_sequential_refunds_exhaust_the_ceiling(self):
        _, order, _, task = _fixtures(collected=Decimal('300.00'))
        _refund(task, '100.00')
        _refund(task, '200.00')
        self.assertEqual(money.refund_ceiling(order), Decimal('0.00'))

    def test_ceiling_never_goes_negative(self):
        _, order, _, task = _fixtures(collected=Decimal('100.00'))
        _refund(task, '100.00')
        _refund(task, '50.00')
        self.assertEqual(money.refund_ceiling(order), Decimal('0.00'))

    def test_order_with_no_items_behaves_normally(self):
        """78% of real order items carry no price; 28% of orders have no items at all."""
        _, order, _, _ = _fixtures(collected=Decimal('75.00'))
        self.assertEqual(order.order_items.count(), 0)
        self.assertEqual(money.refund_ceiling(order), Decimal('75.00'))

    def test_item_prices_do_not_influence_the_ceiling(self):
        _, order, _, _ = _fixtures(cod=Decimal('300.00'), collected=Decimal('300.00'))
        orders_models.OrderItem.objects.create(
            order=order, quantity=2, unit_price=Decimal('9999.00'))
        self.assertEqual(money.refund_ceiling(order), Decimal('300.00'))


class RefundRouteTests(TestCase):
    def test_zero_and_negative_are_refused(self):
        _, order, _, _ = _fixtures(collected=Decimal('300.00'))
        for bad in ('0', '-5'):
            route, task, why = money.refund_route(order, bad)
            self.assertIsNone(route)
            self.assertIn('more than zero', why)

    def test_above_ceiling_is_refused(self):
        _, order, _, _ = _fixtures(collected=Decimal('100.00'))
        route, task, why = money.refund_route(order, '150')
        self.assertIsNone(route)
        self.assertIn('exceeds', why)

    def test_unsettled_cash_routes_to_the_driver_wallet(self):
        _, order, _, task = _fixtures(collected=Decimal('300.00'))
        route, chosen, why = money.refund_route(order, '120')
        self.assertEqual(route, 'driver_wallet')
        self.assertEqual(chosen.pk, task.pk)
        self.assertEqual(why, '')

    def test_headroom_is_net_of_prior_refunds_on_that_task(self):
        _, order, _, task = _fixtures(collected=Decimal('300.00'))
        _refund(task, '250.00')
        self.assertEqual(money.task_headroom(task), Decimal('50.00'))
        route, _t, _w = money.refund_route(order, '50')
        self.assertEqual(route, 'driver_wallet')

    def test_settled_order_leaves_the_driver_wallet(self):
        """Once COD is paid to the seller the cash is no longer the driver's to hand back."""
        _, order, _, _ = _fixtures(collected=Decimal('300.00'), settled=True)
        route, task, why = money.refund_route(order, '50')
        self.assertIsNone(route)
        self.assertIsNone(task)
        self.assertIn('already settled', why)

    def test_settled_order_uses_the_seller_float_when_there_is_one(self):
        from fleet import ledger_service

        business, order, _, _ = _fixtures(collected=Decimal('300.00'), settled=True)
        ledger_service.post(
            business=business, segment='payment', credit=Decimal('500.00'),
            description='deposit')
        self.assertEqual(
            ledger_service.available_refund_credit(business), Decimal('500.00'))
        route, task, why = money.refund_route(order, '50')
        self.assertEqual(route, 'client_ledger')
        self.assertIsNone(task)

    def test_task_without_a_driver_does_not_route_to_a_wallet(self):
        _, order, _, _ = _fixtures(collected=Decimal('300.00'), with_driver=False)
        route, task, why = money.refund_route(order, '50')
        self.assertNotEqual(route, 'driver_wallet')
