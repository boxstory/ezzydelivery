# Purpose: Tests for cod_in_hand single-source-of-truth (derived from task state).
# Used by: manage.py test fleet.tests_cod_ssot
# Notes: Verifies live_cod_in_hand is authoritative and the cached Driver.cod_in_hand
#        stays synced across collection, submission, and return.

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from business import models as business_models
from core import models as core_models
from delivery import models as delivery_models
from fleet import models as fleet_models
from fleet.wallet_service import WalletService
from orders import models as orders_models

User = get_user_model()


def _fixtures(idx=9200, cod=Decimal('300.00'), credit_limit=Decimal('5000.00'), payment_method='cash'):
    biz_user = User.objects.create_user(username=f'ssot_biz_{idx}', password='x')
    biz_profile = core_models.Profile.objects.create(
        user=biz_user, first_name='S', last_name='B', phone=31000000 + idx
    )
    business = business_models.Business.objects.create(
        business_id=idx, user=biz_user, profile=biz_profile,
        business_name=f'SSOT Biz {idx}', business_code=f'SSOT{idx}', business_status='active',
    )
    order = orders_models.Order.objects.create(
        business=business, client_order_code=f'SSOT-ORD-{idx}',
        customer_name='C', customer_phone='111', customer_address='Z',
        cod_amount=cod, order_status='publish',
    )
    drv_user = User.objects.create_user(username=f'ssot_drv_{idx}', password='x')
    drv_profile = core_models.Profile.objects.create(
        user=drv_user, first_name='S', last_name='D', phone=32000000 + idx
    )
    driver = fleet_models.Driver.objects.create(
        driver_id=idx, user=drv_user, profile=drv_profile,
        driver_code=f'SD{idx}', driver_phone='222', driver_whatsapp='222',
        driver_languages='english', driver_license_number=f'L{idx}',
        driver_status='approved', credit_limit=credit_limit,
        cod_in_hand=Decimal('0.00'),
    )
    task = delivery_models.DeliveryTask.objects.create(
        dl_task_number=f'SSOT-T-{idx}', order=order, business=business, driver=driver,
        dl_task_status='delivered', cod_collected=True, cod_settled=False,
        cod_collected_amount=cod, cod_collected_at=timezone.now(),
        completed_at=timezone.now(), payment_method=payment_method,
    )
    return driver, task, business, order


class CodInHandSSOTTest(TestCase):
    def test_live_equals_sum_of_unsettled_collected_tasks(self):
        driver, task, _, _ = _fixtures(cod=Decimal('300.00'))
        self.assertEqual(WalletService.live_cod_in_hand(driver), Decimal('300.00'))

    def test_settled_task_drops_from_live(self):
        driver, task, _, _ = _fixtures(cod=Decimal('300.00'))
        task.cod_settled = True
        task.save(update_fields=['cod_settled'])
        self.assertEqual(WalletService.live_cod_in_hand(driver), Decimal('0.00'))

    def test_returned_task_drops_from_live_and_syncs_cache(self):
        driver, task, _, _ = _fixtures(cod=Decimal('300.00'))
        WalletService.sync_cod_in_hand(driver)
        self.assertEqual(driver.cod_in_hand, Decimal('300.00'))
        # A return removes the task from the live sum even though its flags are unchanged.
        WalletService.record_cod_return(driver=driver, delivery_task=task, amount=Decimal('300.00'))
        self.assertEqual(WalletService.live_cod_in_hand(driver), Decimal('0.00'))
        driver.refresh_from_db()
        self.assertEqual(driver.cod_in_hand, Decimal('0.00'))

    def test_submit_syncs_cache_to_zero(self):
        driver, task, _, _ = _fixtures(cod=Decimal('300.00'))
        WalletService.sync_cod_in_hand(driver)
        WalletService.submit_cod_to_admin(driver=driver, amount=Decimal('300.00'), delivery_ids=[task.id])
        driver.refresh_from_db()
        task.refresh_from_db()
        self.assertTrue(task.cod_settled)
        self.assertEqual(WalletService.live_cod_in_hand(driver), Decimal('0.00'))
        self.assertEqual(driver.cod_in_hand, Decimal('0.00'))

    def test_sync_corrects_a_drifted_cache(self):
        driver, task, _, _ = _fixtures(cod=Decimal('300.00'))
        # Simulate drift: cached says 999 but the task truth is 300.
        fleet_models.Driver.objects.filter(pk=driver.pk).update(cod_in_hand=Decimal('999.00'))
        driver.refresh_from_db()
        WalletService.sync_cod_in_hand(driver)
        driver.refresh_from_db()
        self.assertEqual(driver.cod_in_hand, Decimal('300.00'))

    def test_credit_gate_uses_live_not_cached(self):
        # Cached is drifted LOW (0) but live COD is at the credit limit -> must block.
        driver, task, _, _ = _fixtures(cod=Decimal('5000.00'), credit_limit=Decimal('5000.00'))
        fleet_models.Driver.objects.filter(pk=driver.pk).update(cod_in_hand=Decimal('0.00'))
        driver.refresh_from_db()
        can, reason = WalletService.can_accept_cod_order(driver, Decimal('100.00'))
        self.assertFalse(can)
        self.assertIn('exhausted', reason.lower())

    def test_get_wallet_status_reports_live(self):
        driver, task, _, _ = _fixtures(cod=Decimal('300.00'))
        fleet_models.Driver.objects.filter(pk=driver.pk).update(cod_in_hand=Decimal('7.00'))
        driver.refresh_from_db()
        status = WalletService.get_wallet_status(driver)
        self.assertEqual(status['cod_in_hand'], Decimal('300.00'))

    def test_cash_collection_counts_as_in_hand(self):
        driver, task, _, _ = _fixtures(cod=Decimal('220.00'), payment_method='cash')
        self.assertEqual(WalletService.live_cod_in_hand(driver), Decimal('220.00'))

    def test_fawran_collection_not_in_hand(self):
        # Fawran goes straight to Ezzy's account — never the driver's liability.
        driver, task, _, _ = _fixtures(cod=Decimal('220.00'), payment_method='fawran')
        self.assertEqual(WalletService.live_cod_in_hand(driver), Decimal('0.00'))

    def test_electronic_methods_all_excluded(self):
        for i, method in enumerate(['pos', 'fawran', 'bank', 'atm']):
            driver, _, _, _ = _fixtures(idx=9300 + i, cod=Decimal('100.00'), payment_method=method)
            self.assertEqual(
                WalletService.live_cod_in_hand(driver), Decimal('0.00'),
                f'{method} should not count as in-hand',
            )


class CodFeeSliceTest(TestCase):
    """The DL fee inside the running cash balance.

    cod_cash_after stays the whole pocket (COD + our fee) because that is what
    the driver hands in; cod_fee_after says how much of it is ours, so the
    staff ledger can show COD and DL as separate columns.
    """

    def _ledger(self, driver):
        return list(
            fleet_models.DriverTransaction.objects.filter(
                driver=driver,
                transaction_type__in=['cod_collection', 'fee_collection',
                                      'cod_deposit', 'cod_driver_settle'],
            ).order_by('created_at', 'id')
        )

    def _collect(self, idx, cod, fee):
        driver, task, _, _ = _fixtures(idx=idx, cod=cod)
        task.fee_collected_amount = fee
        task.fee_collected_at = timezone.now()
        task.save(update_fields=['fee_collected_amount', 'fee_collected_at'])
        WalletService.record_transaction(
            driver=driver, transaction_type='cod_collection', amount=cod,
            description='COD', delivery_task=task, payment_method='cash')
        WalletService.record_transaction(
            driver=driver, transaction_type='fee_collection', amount=fee,
            description='Fee', delivery_task=task, payment_method='cash')
        return driver, task

    def test_fee_is_tracked_beside_the_cash_it_sits_in(self):
        driver, _ = self._collect(9310, Decimal('300.00'), Decimal('25.00'))
        WalletService.recalculate_cod_balances(driver)
        last = self._ledger(driver)[-1]
        # The pocket is COD + fee; the slice names the fee half of it.
        self.assertEqual(last.cod_cash_after, Decimal('325.00'))
        self.assertEqual(last.cod_fee_after, Decimal('25.00'))
        self.assertEqual(last.cod_cash_excl_fee, Decimal('300.00'))
        self.assertEqual(last.cod_after_total, Decimal('325.00'))
        self.assertEqual(last.cod_after_total_excl_fee, Decimal('300.00'))

    def test_fee_slice_never_exceeds_the_cash(self):
        driver, _ = self._collect(9311, Decimal('0.00'), Decimal('40.00'))
        WalletService.recalculate_cod_balances(driver)
        last = self._ledger(driver)[-1]
        self.assertEqual(last.cod_fee_after, Decimal('40.00'))
        self.assertEqual(last.cod_cash_excl_fee, Decimal('0.00'))

    def test_electronic_cod_leaves_the_fee_on_cash(self):
        driver, task, _, _ = _fixtures(idx=9312, cod=Decimal('200.00'),
                                       payment_method='fawran')
        task.fee_collected_amount = Decimal('15.00')
        task.save(update_fields=['fee_collected_amount'])
        WalletService.record_transaction(
            driver=driver, transaction_type='cod_collection',
            amount=Decimal('200.00'), description='COD',
            delivery_task=task, payment_method='fawran')
        WalletService.record_transaction(
            driver=driver, transaction_type='fee_collection',
            amount=Decimal('15.00'), description='Fee',
            delivery_task=task, payment_method='cash')
        WalletService.recalculate_cod_balances(driver)
        last = self._ledger(driver)[-1]
        # Fawran money never reached the driver's pocket; the fee did.
        self.assertEqual(last.cod_fawran_after, Decimal('200.00'))
        self.assertEqual(last.cod_cash_after, Decimal('15.00'))
        self.assertEqual(last.cod_fee_after, Decimal('15.00'))
        self.assertEqual(last.cod_cash_excl_fee, Decimal('0.00'))
        self.assertEqual(last.cod_after_total_excl_fee, Decimal('200.00'))

    def test_hand_in_clears_the_fee_with_the_cash(self):
        driver, task = self._collect(9313, Decimal('300.00'), Decimal('25.00'))
        WalletService.submit_cod_to_admin(
            driver=driver, amount=Decimal('325.00'), delivery_ids=[task.id])
        WalletService.recalculate_cod_balances(driver)
        last = self._ledger(driver)[-1]
        self.assertEqual(last.transaction_type, 'cod_deposit')
        self.assertEqual(last.cod_cash_after, Decimal('0.00'))
        self.assertEqual(last.cod_fee_after, Decimal('0.00'))
