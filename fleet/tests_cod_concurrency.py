# Purpose: Concurrency + idempotency regression tests for WalletService.submit_cod_to_admin (COD deposit path).
# Used by: `python manage.py test fleet.tests_cod_concurrency` (CI + manual QA of the COD race fix).
# Notes: Uses TransactionTestCase (real committed rows) + threads/Barrier to force simultaneous submits; PostgreSQL honours select_for_update.

import threading
from decimal import Decimal

from django.test import TransactionTestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.db import connection

from delivery import models as delivery_models
from orders import models as orders_models
from business import models as business_models
from fleet import models as fleet_models
from core import models as core_models
from fleet.wallet_service import WalletService

DeliveryTask = delivery_models.DeliveryTask
Order = orders_models.Order
Business = business_models.Business
PickupLocation = business_models.PickupLocation
Driver = fleet_models.Driver
DriverTransaction = fleet_models.DriverTransaction
Profile = core_models.Profile

User = get_user_model()


class CodSubmitConcurrencyTestCase(TransactionTestCase):
    """Prove submit_cod_to_admin is race-safe and idempotent."""

    # Ensure test DB rows are visible to the spawned threads.
    reset_sequences = True

    COD_AMOUNT = Decimal('500')

    def _make_fixtures(self):
        """Create Business, Order, Driver, and a delivered/COD-collected DeliveryTask.

        Returns (driver, task).
        """
        biz_user = User.objects.create_user(
            username='cod_biz_user', email='cod_biz@example.com', password='x'
        )
        biz_profile = Profile.objects.create(
            user=biz_user, first_name='COD', last_name='Biz', phone=30000001
        )
        business = Business.objects.create(
            business_id=9100,
            user=biz_user,
            profile=biz_profile,
            business_name='COD Test Business',
            business_code='CODB9100',
            business_status='active',
        )

        pickup_location = PickupLocation.objects.create(
            business=business,
            pickup_location_title='COD Warehouse',
            locality='Doha',
            pickup_zone_no=70,
            pickup_street_no=700,
            pickup_building_no=7000,
            pickup_status='active',
        )

        order = Order.objects.create(
            business=business,
            client_order_code='CODORD001',
            customer_name='COD Customer',
            customer_phone='11111111',
            customer_address='COD Address',
            dl_zone=70,
            dl_building=7000,
            dl_street=700,
            pickup_location=pickup_location,
        )

        drv_user = User.objects.create_user(
            username='cod_driver_user', email='cod_driver@example.com', password='x'
        )
        drv_profile = Profile.objects.create(
            user=drv_user, first_name='COD', last_name='Driver', phone=30000002
        )
        driver = Driver.objects.create(
            driver_id=9101,
            user=drv_user,
            profile=drv_profile,
            driver_code='CODDRV01',
            driver_phone='22222222',
            driver_whatsapp='22222222',
            driver_languages='english',
            driver_license_number='LIC-COD-1',
            driver_status='approved',
            # Driver is holding exactly the COD they are about to submit.
            cod_in_hand=self.COD_AMOUNT,
        )

        task = DeliveryTask.objects.create(
            dl_task_number='COD-TASK-001',
            dl_task_description='COD delivery',
            order=order,
            business=business,
            driver=driver,
            pickup_location=pickup_location,
            dl_task_status='delivered',
            dl_task_status_client='2',
            cod_collected=True,
            cod_settled=False,
            cod_collected_amount=self.COD_AMOUNT,
            cod_collected_at=timezone.now(),
            completed_at=timezone.now(),
            payment_method='cash',
        )

        return driver, task

    # ------------------------------------------------------------------
    # Baseline: a single valid submit works.
    # ------------------------------------------------------------------
    def test_single_submit_credits_once_and_settles(self):
        driver, task = self._make_fixtures()

        WalletService.submit_cod_to_admin(
            driver, amount=self.COD_AMOUNT, delivery_ids=[task.id]
        )

        deposit_count = DriverTransaction.objects.filter(
            driver=driver, transaction_type='cod_deposit'
        ).count()
        self.assertEqual(deposit_count, 1, 'exactly one cod_deposit expected')

        task.refresh_from_db()
        self.assertTrue(task.cod_settled, 'task should be marked cod_settled')

        driver.refresh_from_db()
        self.assertEqual(
            driver.cod_in_hand, Decimal('0'),
            'cod_in_hand should be back to 0 after settling the one COD task',
        )

    # ------------------------------------------------------------------
    # Concurrency: two simultaneous submits must credit once only.
    # ------------------------------------------------------------------
    def test_concurrent_submit_credits_once(self):
        driver, task = self._make_fixtures()

        barrier = threading.Barrier(2)
        errors = []
        errors_lock = threading.Lock()

        def worker():
            try:
                # Line both threads up so they hit the submit at the same instant.
                barrier.wait()
                WalletService.submit_cod_to_admin(
                    driver, amount=self.COD_AMOUNT, delivery_ids=[task.id]
                )
            except Exception as exc:  # noqa: BLE001 - one thread may legitimately raise
                with errors_lock:
                    errors.append(exc)
            finally:
                # Avoid leaking the per-thread DB connection.
                connection.close()

        threads = [threading.Thread(target=worker) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        # Money invariant #1: exactly ONE cod_deposit transaction for this driver.
        deposit_count = DriverTransaction.objects.filter(
            driver=driver, transaction_type='cod_deposit'
        ).count()
        self.assertEqual(
            deposit_count, 1,
            f'exactly one cod_deposit expected, got {deposit_count} '
            f'(thread errors: {errors})',
        )

        # Money invariant #2: the task is settled exactly once.
        task.refresh_from_db()
        self.assertTrue(task.cod_settled, 'task should be marked cod_settled')

        # Money invariant #3: cod_in_hand must not be double-debited into the negative.
        driver.refresh_from_db()
        self.assertGreaterEqual(
            driver.cod_in_hand, Decimal('0'),
            'cod_in_hand must never go negative from a double submit',
        )
        self.assertEqual(
            driver.cod_in_hand, Decimal('0'),
            'cod_in_hand should end at exactly 0 (credited once, not twice)',
        )

        # At most one thread may have raised (the loser of the race).
        self.assertLessEqual(
            len(errors), 1,
            f'at most one thread should raise, got {errors}',
        )

    # ------------------------------------------------------------------
    # Idempotency: a second sequential submit is a no-op.
    # ------------------------------------------------------------------
    def test_sequential_double_submit_is_idempotent(self):
        driver, task = self._make_fixtures()

        # First submit: settles the task and credits the deposit.
        WalletService.submit_cod_to_admin(
            driver, amount=self.COD_AMOUNT, delivery_ids=[task.id]
        )

        driver.refresh_from_db()
        self.assertEqual(driver.cod_in_hand, Decimal('0'))
        task.refresh_from_db()
        self.assertTrue(task.cod_settled)

        # Second submit of the SAME already-settled task must be a no-op.
        # It may raise (insufficient cod_in_hand) or return silently; either way
        # the money outcome must not change.
        try:
            WalletService.submit_cod_to_admin(
                driver, amount=self.COD_AMOUNT, delivery_ids=[task.id]
            )
        except ValueError:
            pass

        deposit_count = DriverTransaction.objects.filter(
            driver=driver, transaction_type='cod_deposit'
        ).count()
        self.assertEqual(
            deposit_count, 1,
            'second submit of an already-settled task must not create a 2nd cod_deposit',
        )

        driver.refresh_from_db()
        self.assertEqual(
            driver.cod_in_hand, Decimal('0'),
            'cod_in_hand must not be debited again by the idempotent re-submit',
        )
