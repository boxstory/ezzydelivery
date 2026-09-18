# Purpose: Tests for issuing a refund — the running-total cap, the leg it routes to, and the
#          two reporting bugs that used to follow a partial refund.
# Used by: manage.py test orders.tests_refund
# Notes: This exercises a live money path. The cap is the important one: refunding more than was
#        collected credits a driver cash he never took and drives cod_in_hand negative.

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from business import models as business_models
from core import models as core_models
from delivery import models as delivery_models
from fleet import ledger_service
from fleet import models as fleet_models
from fleet.wallet_service import WalletService
from orders import models as orders_models
from orders import money, services

User = get_user_model()

_SEQ = [7700]


def _fixtures(collected=Decimal('300.00'), settled=False, payment_method='cash'):
    _SEQ[0] += 1
    idx = _SEQ[0]

    biz_user = User.objects.create_user(username=f'rf_biz_{idx}', password='x')
    biz_profile = core_models.Profile.objects.create(
        user=biz_user, first_name='R', last_name='F', phone=71000000 + idx)
    business = business_models.Business.objects.create(
        business_id=idx, user=biz_user, profile=biz_profile,
        business_name=f'Refund Biz {idx}', business_code=f'RF{idx}',
        business_status='active')
    order = orders_models.Order.objects.create(
        business=business, client_order_code=f'RF-ORD-{idx}',
        customer_name='C', customer_phone='1', customer_address='Z',
        cod_amount=collected, order_status='delivered')

    drv_user = User.objects.create_user(username=f'rf_drv_{idx}', password='x')
    drv_profile = core_models.Profile.objects.create(
        user=drv_user, first_name='R', last_name='D', phone=72000000 + idx)
    driver = fleet_models.Driver.objects.create(
        driver_id=idx, user=drv_user, profile=drv_profile,
        driver_code=f'RD{idx}', driver_phone='2', driver_whatsapp='2',
        driver_languages='english', driver_license_number=f'L{idx}',
        driver_status='approved', cod_in_hand=Decimal('0.00'))

    task = delivery_models.DeliveryTask.objects.create(
        dl_task_number=f'RF-T-{idx}', order=order, business=business, driver=driver,
        dl_task_status='delivered', cod_collected=True, cod_settled=False,
        cod_collected_amount=collected, cod_collected_at=timezone.now(),
        completed_at=timezone.now(), payment_method=payment_method,
        cod_client_settled=settled)
    WalletService.sync_cod_in_hand(driver)
    staff = User.objects.create_user(
        username=f'rf_staff_{idx}', password='x', is_staff=True)
    return business, order, driver, task, staff


class MultiplePartialRefundTests(TestCase):
    """A customer can hand goods back over more than one visit."""

    def test_a_second_partial_refund_is_allowed(self):
        _, order, driver, task, staff = _fixtures(collected=Decimal('300.00'))
        services.issue_refund(order, Decimal('100.00'), user=staff)
        services.issue_refund(order, Decimal('50.00'), user=staff)

        returned = fleet_models.DriverTransaction.objects.filter(
            delivery_task=task, transaction_type='cod_return').count()
        self.assertEqual(returned, 2)
        self.assertEqual(money.refund_ceiling(order), Decimal('150.00'))

    def test_the_running_total_is_capped_at_what_was_collected(self):
        _, order, _, task, staff = _fixtures(collected=Decimal('300.00'))
        services.issue_refund(order, Decimal('250.00'), user=staff)
        with self.assertRaises(ValidationError):
            services.issue_refund(order, Decimal('100.00'), user=staff)

    def test_cod_in_hand_drops_by_each_refund(self):
        _, order, driver, _, staff = _fixtures(collected=Decimal('300.00'))
        self.assertEqual(WalletService.live_cod_in_hand(driver), Decimal('300.00'))
        services.issue_refund(order, Decimal('100.00'), user=staff)
        self.assertEqual(WalletService.live_cod_in_hand(driver), Decimal('200.00'))
        services.issue_refund(order, Decimal('200.00'), user=staff)
        self.assertEqual(WalletService.live_cod_in_hand(driver), Decimal('0.00'))

    def test_cod_in_hand_never_goes_negative(self):
        _, order, driver, _, staff = _fixtures(collected=Decimal('300.00'))
        services.issue_refund(order, Decimal('300.00'), user=staff)
        try:
            services.issue_refund(order, Decimal('50.00'), user=staff)
        except ValidationError:
            pass
        self.assertGreaterEqual(WalletService.live_cod_in_hand(driver), Decimal('0.00'))

    def test_service_level_cap_is_enforced_directly(self):
        """Guard the WalletService entry point, not just the route in front of it."""
        _, _, driver, task, staff = _fixtures(collected=Decimal('100.00'))
        WalletService.record_cod_return(
            driver=driver, delivery_task=task, amount=Decimal('60.00'))
        with self.assertRaises(ValueError):
            WalletService.record_cod_return(
                driver=driver, delivery_task=task, amount=Decimal('50.00'))


class RefundRoutingTests(TestCase):
    def test_unsettled_cod_comes_out_of_the_driver(self):
        _, order, _, task, staff = _fixtures()
        route, record, message = services.issue_refund(
            order, Decimal('50.00'), user=staff)
        self.assertEqual(route, 'driver_wallet')
        self.assertEqual(record.transaction_type, 'cod_return')
        self.assertIn(task.dl_task_number, message)

    def test_settled_cod_comes_off_the_sellers_float(self):
        business, order, _, _, staff = _fixtures(settled=True)
        ledger_service.post(
            business=business, segment='payment', credit=Decimal('500.00'),
            description='deposit')
        route, record, message = services.issue_refund(
            order, Decimal('50.00'), user=staff)
        self.assertEqual(route, 'client_ledger')
        self.assertEqual(record.segment, 'adjustment')
        self.assertEqual(record.debit, Decimal('50.00'))
        self.assertEqual(
            ledger_service.available_refund_credit(business), Decimal('450.00'))

    def test_settled_cod_with_no_float_is_refused(self):
        _, order, _, _, staff = _fixtures(settled=True)
        with self.assertRaises(ValidationError):
            services.issue_refund(order, Decimal('50.00'), user=staff)

    def test_refund_above_the_ceiling_is_refused(self):
        _, order, _, _, staff = _fixtures(collected=Decimal('100.00'))
        with self.assertRaises(ValidationError):
            services.issue_refund(order, Decimal('150.00'), user=staff)

    def test_no_money_moves_when_a_refund_is_refused(self):
        _, order, driver, _, staff = _fixtures(collected=Decimal('100.00'))
        before = WalletService.live_cod_in_hand(driver)
        with self.assertRaises(ValidationError):
            services.issue_refund(order, Decimal('999.00'), user=staff)
        self.assertEqual(WalletService.live_cod_in_hand(driver), before)


class PostRefundLedgerTests(TestCase):
    def test_refund_cannot_exceed_the_float(self):
        business, order, _, _, staff = _fixtures(settled=True)
        ledger_service.post(
            business=business, segment='payment', credit=Decimal('40.00'),
            description='small deposit')
        with self.assertRaises(ValueError):
            ledger_service.post_refund(business, Decimal('50.00'), order=order)

    def test_zero_and_negative_are_refused(self):
        business, order, _, _, _ = _fixtures(settled=True)
        for bad in (Decimal('0'), Decimal('-5')):
            with self.assertRaises(ValueError):
                ledger_service.post_refund(business, bad, order=order)

    def test_two_refunds_cannot_both_spend_the_same_float(self):
        business, order, _, _, staff = _fixtures(settled=True)
        ledger_service.post(
            business=business, segment='payment', credit=Decimal('100.00'),
            description='deposit')
        ledger_service.post_refund(business, Decimal('70.00'), order=order)
        with self.assertRaises(ValueError):
            ledger_service.post_refund(business, Decimal('70.00'), order=order)
        self.assertEqual(
            ledger_service.available_refund_credit(business), Decimal('30.00'))
