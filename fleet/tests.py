"""
Aggressive Test Suite for Driver Mobile View Workflow
=====================================================

Covers the entire driver mobile experience:
- Model creation, properties, constraints
- Wallet service (transactions, COD, settlements, edge cases)
- All fleet views (dashboard, profile, documents, vehicles, COD, earnings, etc.)
- Delivery views for drivers (task list, assignment, start ride, navigation, pickup scanner)
- Authentication & authorization (driver_required decorator)
- IDOR protection
- Edge cases: zero balances, negative wallets, duplicate assignments, invalid inputs
"""

import json
from decimal import Decimal
from datetime import timedelta, date

from django.test import TestCase, TransactionTestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from core import models as core_models
from fleet import models as fleet_models
from fleet.wallet_service import WalletService, WalletAlertService
from delivery import models as delivery_models
from business import models as business_models
from orders import models as orders_models

User = get_user_model()


# =============================================================================
# TEST HELPERS
# =============================================================================

class DriverTestMixin:
    """Reusable mixin to create standard test fixtures for driver tests."""

    def create_driver_user(self, username='testdriver', email='testdriver@test.com',
                           password='TestDriver@123', is_driver=True):
        """Create a user with driver profile."""
        user = User.objects.create_user(
            username=username, email=email, password=password
        )
        profile = core_models.Profile.objects.create(
            user=user,
            first_name='Test',
            last_name='Driver',
            phone=55512345,
            is_driver=is_driver,
        )
        return user, profile

    def create_driver(self, user, profile, driver_id=1001, driver_code='DRV001',
                      driver_status='approved', credit_limit=5000, **kwargs):
        """Create a Driver instance."""
        defaults = {
            'driver_id': driver_id,
            'user': user,
            'profile': profile,
            'driver_code': driver_code,
            'driver_phone': '55512345',
            'driver_whatsapp': '55512345',
            'driver_languages': 'english',
            'driver_license_number': 'LIC12345',
            'driver_status': driver_status,
            'credit_limit': Decimal(str(credit_limit)),
            'wallet_balance': Decimal('0.00'),
            'cod_in_hand': Decimal('0.00'),
            'pending_earnings': Decimal('0.00'),
            'total_earnings': Decimal('0.00'),
        }
        defaults.update(kwargs)
        return fleet_models.Driver.objects.create(**defaults)

    def create_non_driver_user(self, username='nondriver', email='nondriver@test.com',
                                password='TestDriver@123'):
        """Create a user who is NOT a driver."""
        user = User.objects.create_user(
            username=username, email=email, password=password
        )
        core_models.Profile.objects.create(
            user=user,
            first_name='Non',
            last_name='Driver',
            phone=55500000,
            is_driver=False,
        )
        return user

    def create_business_and_order(self, user, profile):
        """Create a business, pickup location, and order for testing."""
        business = business_models.Business.objects.create(
            business_id=100,
            user=user,
            profile=profile,
            business_name='Test Business',
            business_code='TESTB001',
            business_status='active',
        )
        pickup = business_models.PickupLocation.objects.create(
            business=business,
            pickup_location_title='Test Warehouse',
            locality='Doha',
            pickup_zone_no=70,
            pickup_street_no=700,
            pickup_building_no=7000,
            pickup_status='active',
        )
        order = orders_models.Order.objects.create(
            business=business,
            client_order_code='ORD001',
            customer_name='Test Customer',
            customer_phone='33344455',
            customer_address='Test Address Doha',
            dl_zone=70,
            dl_building=7000,
            dl_street=700,
            pickup_location=pickup,
        )
        return business, pickup, order

    def create_delivery_task(self, order, business, pickup=None, driver=None,
                             task_number='TASK-001', status='pending', **kwargs):
        """Create a DeliveryTask."""
        defaults = {
            'dl_task_number': task_number,
            'dl_task_description': 'Test delivery task',
            'order': order,
            'business': business,
            'pickup_location': pickup,
            'driver': driver,
            'dl_task_status': status,
            'dl_task_status_client': 'for_review',
            'dl_price': 25,
        }
        defaults.update(kwargs)
        return delivery_models.DeliveryTask.objects.create(**defaults)


# =============================================================================
# MODEL TESTS
# =============================================================================

class DriverModelTest(DriverTestMixin, TestCase):
    """Test Driver model creation, properties, and constraints."""

    def setUp(self):
        self.user, self.profile = self.create_driver_user()
        self.driver = self.create_driver(self.user, self.profile)

    def test_driver_creation(self):
        self.assertEqual(self.driver.driver_id, 1001)
        self.assertEqual(self.driver.driver_code, 'DRV001')
        self.assertEqual(self.driver.driver_status, 'approved')
        self.assertEqual(self.driver.wallet_balance, Decimal('0.00'))

    def test_driver_str_with_profile(self):
        result = str(self.driver)
        self.assertIn(self.user.username, result)

    def test_driver_str_without_profile(self):
        self.driver.profile = None
        self.driver.save()
        result = str(self.driver)
        self.assertIn('DRV001', result)

    def test_driver_str_no_profile_no_code(self):
        self.driver.profile = None
        self.driver.driver_code = None
        self.driver.save()
        result = str(self.driver)
        self.assertIn('1001', result)

    # Wallet properties (cod_in_hand = positive COD currently held by driver)
    def test_wallet_usage_percentage_zero(self):
        self.assertEqual(self.driver.wallet_usage_percentage, 0)

    def test_wallet_usage_percentage_50_percent(self):
        self.driver.cod_in_hand = Decimal('2500.00')  # 50% of 5000 limit
        self.assertEqual(self.driver.wallet_usage_percentage, 50)

    def test_wallet_usage_percentage_100_percent(self):
        self.driver.cod_in_hand = Decimal('5000.00')  # 100% of 5000 limit
        self.assertEqual(self.driver.wallet_usage_percentage, 100)

    def test_wallet_usage_percentage_zero_credit_limit(self):
        self.driver.credit_limit = Decimal('0.00')
        self.assertEqual(self.driver.wallet_usage_percentage, 0)

    def test_is_wallet_warning_below_80(self):
        self.driver.cod_in_hand = Decimal('3000.00')  # 60% of 5000
        self.assertFalse(self.driver.is_wallet_warning)

    def test_is_wallet_warning_at_80(self):
        self.driver.cod_in_hand = Decimal('4000.00')  # 80% of 5000
        self.assertTrue(self.driver.is_wallet_warning)

    def test_is_wallet_warning_above_80(self):
        self.driver.cod_in_hand = Decimal('4500.00')  # 90% of 5000
        self.assertTrue(self.driver.is_wallet_warning)

    def test_is_wallet_blocked_positive_balance(self):
        self.driver.cod_in_hand = Decimal('100.00')  # Below limit
        self.assertFalse(self.driver.is_wallet_blocked)

    def test_is_wallet_blocked_zero_balance(self):
        self.driver.cod_in_hand = Decimal('5000.00')  # At credit limit
        self.assertTrue(self.driver.is_wallet_blocked)

    def test_is_wallet_blocked_negative_balance(self):
        self.driver.cod_in_hand = Decimal('5100.00')  # Exceeds credit limit
        self.assertTrue(self.driver.is_wallet_blocked)

    def test_available_credit(self):
        self.driver.cod_in_hand = Decimal('2000.00')
        self.driver.credit_limit = Decimal('5000.00')
        self.assertEqual(self.driver.available_credit, Decimal('3000.00'))

    def test_available_credit_full(self):
        self.driver.cod_in_hand = Decimal('0.00')
        self.driver.credit_limit = Decimal('5000.00')
        self.assertEqual(self.driver.available_credit, Decimal('5000.00'))


class DriverVehicleModelTest(DriverTestMixin, TestCase):
    """Test DriverVehicle model."""

    def setUp(self):
        self.user, self.profile = self.create_driver_user()
        self.driver = self.create_driver(self.user, self.profile)

    def test_vehicle_creation(self):
        vehicle = fleet_models.DriverVehicle.objects.create(
            driver=self.driver,
            vehicle_type='car',
            vehicle_no='QA-1234',
            vehicle_model='Toyota Hilux',
            vehicle_color='White',
            vehicle_status='active',
        )
        self.assertEqual(vehicle.vehicle_type, 'car')
        self.assertEqual(str(vehicle), 'QA-1234')

    def test_vehicle_default_status(self):
        vehicle = fleet_models.DriverVehicle.objects.create(
            driver=self.driver,
            vehicle_type='bike',
            vehicle_no='QA-5678',
        )
        self.assertEqual(vehicle.vehicle_status, 'Inactive')

    def test_multiple_vehicles_per_driver(self):
        fleet_models.DriverVehicle.objects.create(
            driver=self.driver, vehicle_type='car', vehicle_no='QA-1111')
        fleet_models.DriverVehicle.objects.create(
            driver=self.driver, vehicle_type='bike', vehicle_no='QA-2222')
        self.assertEqual(self.driver.driver_vehicle.count(), 2)


class DriverDocumentModelTest(DriverTestMixin, TestCase):
    """Test DriverDocument model."""

    def setUp(self):
        self.user, self.profile = self.create_driver_user()
        self.driver = self.create_driver(self.user, self.profile)

    def test_document_creation(self):
        doc = fleet_models.DriverDocument.objects.create(
            driver=self.driver,
            document_type='QID',
            document_no='QID123456',
            document_issued_from='Qatar',
        )
        self.assertEqual(doc.document_type, 'QID')
        self.assertEqual(str(doc), 'QID123456')

    def test_document_types(self):
        types = ['QID', 'Driving License', 'Passport', 'National Identification']
        for i, doc_type in enumerate(types):
            fleet_models.DriverDocument.objects.create(
                driver=self.driver,
                document_type=doc_type,
                document_no=f'DOC{i:04d}',
            )
        self.assertEqual(self.driver.driver_document.count(), 4)


class DriverTransactionModelTest(DriverTestMixin, TestCase):
    """Test DriverTransaction model."""

    def setUp(self):
        self.user, self.profile = self.create_driver_user()
        self.driver = self.create_driver(self.user, self.profile)

    def test_transaction_creation(self):
        trans = fleet_models.DriverTransaction.objects.create(
            driver=self.driver,
            transaction_type='earning',
            amount=Decimal('20.00'),
            description='Test earning',
        )
        self.assertEqual(trans.transaction_type, 'earning')
        self.assertIn('Task Earning', str(trans))
        self.assertIn('20', str(trans))

    def test_transaction_types(self):
        types = ['earning', 'cod_collection', 'cod_deposit', 'settlement',
                 'deduction', 'bonus', 'adjustment']
        for t in types:
            fleet_models.DriverTransaction.objects.create(
                driver=self.driver,
                transaction_type=t,
                amount=Decimal('10.00'),
                description=f'Test {t}',
            )
        self.assertEqual(self.driver.transactions.count(), 7)


class DriverSettlementModelTest(DriverTestMixin, TestCase):
    """Test DriverSettlement model."""

    def setUp(self):
        self.user, self.profile = self.create_driver_user()
        self.driver = self.create_driver(self.user, self.profile)

    def test_settlement_creation(self):
        settlement = fleet_models.DriverSettlement.objects.create(
            driver=self.driver,
            period_start=date(2025, 1, 1),
            period_end=date(2025, 1, 31),
            total_deliveries=50,
            gross_earnings=Decimal('1000.00'),
            net_amount=Decimal('950.00'),
            status='pending',
        )
        self.assertIsNotNone(settlement.settlement_code)
        self.assertIn('STL-', settlement.settlement_code)

    def test_settlement_auto_code_generation(self):
        s1 = fleet_models.DriverSettlement.objects.create(
            driver=self.driver,
            period_start=date(2025, 1, 1),
            period_end=date(2025, 1, 31),
            status='pending',
        )
        self.assertTrue(s1.settlement_code.startswith('STL-1001-'))

    def test_settlement_manual_code_preserved(self):
        s = fleet_models.DriverSettlement.objects.create(
            driver=self.driver,
            settlement_code='CUSTOM-001',
            period_start=date(2025, 1, 1),
            period_end=date(2025, 1, 31),
            status='pending',
        )
        self.assertEqual(s.settlement_code, 'CUSTOM-001')


class ReceiptTemplateModelTest(TestCase):
    """Test ReceiptTemplate model."""

    def test_receipt_template_creation(self):
        tmpl = fleet_models.ReceiptTemplate.objects.create(
            name='Default Settlement',
            template_type='settlement',
            paper_size='thermal_80',
            is_default=True,
        )
        self.assertTrue(tmpl.is_default)
        self.assertEqual(tmpl.paper_size, 'thermal_80')

    def test_only_one_default_per_type(self):
        tmpl1 = fleet_models.ReceiptTemplate.objects.create(
            name='Template 1',
            template_type='settlement',
            is_default=True,
        )
        tmpl2 = fleet_models.ReceiptTemplate.objects.create(
            name='Template 2',
            template_type='settlement',
            is_default=True,
        )
        # Refresh from DB
        tmpl1.refresh_from_db()
        self.assertFalse(tmpl1.is_default)
        self.assertTrue(tmpl2.is_default)

    def test_different_types_can_both_be_default(self):
        tmpl1 = fleet_models.ReceiptTemplate.objects.create(
            name='Settlement Default',
            template_type='settlement',
            is_default=True,
        )
        tmpl2 = fleet_models.ReceiptTemplate.objects.create(
            name='COD Default',
            template_type='cod_deposit',
            is_default=True,
        )
        tmpl1.refresh_from_db()
        self.assertTrue(tmpl1.is_default)
        self.assertTrue(tmpl2.is_default)


# =============================================================================
# WALLET SERVICE TESTS
# =============================================================================

class WalletServiceRecordTransactionTest(DriverTestMixin, TransactionTestCase):
    """Test WalletService.record_transaction with all transaction types."""

    def setUp(self):
        self.user, self.profile = self.create_driver_user()
        self.driver = self.create_driver(self.user, self.profile)

    def test_earning_transaction(self):
        trans = WalletService.record_transaction(
            driver=self.driver,
            transaction_type='earning',
            amount=Decimal('20.00'),
            description='Delivery earnings',
        )
        self.driver.refresh_from_db()
        self.assertEqual(self.driver.pending_earnings, Decimal('20.00'))
        self.assertEqual(self.driver.total_earnings, Decimal('20.00'))
        self.assertEqual(trans.pending_earnings_after, Decimal('20.00'))

    def test_cod_collection_transaction(self):
        # Start with positive wallet balance
        self.driver.wallet_balance = Decimal('5000.00')
        self.driver.save()

        trans = WalletService.record_transaction(
            driver=self.driver,
            transaction_type='cod_collection',
            amount=Decimal('100.00'),
            description='COD collected',
        )
        self.driver.refresh_from_db()
        self.assertEqual(self.driver.wallet_balance, Decimal('4900.00'))
        self.assertEqual(self.driver.cod_in_hand, Decimal('100.00'))

    def test_cod_deposit_transaction(self):
        # Set up driver with COD in hand
        self.driver.wallet_balance = Decimal('-100.00')
        self.driver.cod_in_hand = Decimal('100.00')
        self.driver.save()

        trans = WalletService.record_transaction(
            driver=self.driver,
            transaction_type='cod_deposit',
            amount=Decimal('100.00'),
            description='COD deposited to admin',
        )
        self.driver.refresh_from_db()
        self.assertEqual(self.driver.wallet_balance, Decimal('0.00'))
        self.assertEqual(self.driver.cod_in_hand, Decimal('0.00'))

    def test_settlement_transaction(self):
        self.driver.pending_earnings = Decimal('500.00')
        self.driver.save()

        trans = WalletService.record_transaction(
            driver=self.driver,
            transaction_type='settlement',
            amount=Decimal('500.00'),
            description='Weekly settlement',
        )
        self.driver.refresh_from_db()
        self.assertEqual(self.driver.pending_earnings, Decimal('0.00'))
        self.assertIsNotNone(self.driver.last_settlement_date)

    def test_bonus_transaction(self):
        trans = WalletService.record_transaction(
            driver=self.driver,
            transaction_type='bonus',
            amount=Decimal('50.00'),
            description='Performance bonus',
        )
        self.driver.refresh_from_db()
        self.assertEqual(self.driver.wallet_balance, Decimal('50.00'))

    def test_deduction_transaction(self):
        self.driver.wallet_balance = Decimal('100.00')
        self.driver.save()

        trans = WalletService.record_transaction(
            driver=self.driver,
            transaction_type='deduction',
            amount=Decimal('-25.00'),
            description='Damage deduction',
        )
        self.driver.refresh_from_db()
        self.assertEqual(self.driver.wallet_balance, Decimal('75.00'))

    def test_adjustment_transaction(self):
        trans = WalletService.record_transaction(
            driver=self.driver,
            transaction_type='adjustment',
            amount=Decimal('10.00'),
            description='Manual adjustment',
        )
        self.driver.refresh_from_db()
        self.assertEqual(self.driver.wallet_balance, Decimal('10.00'))

    def test_transaction_records_balance_snapshots(self):
        self.driver.wallet_balance = Decimal('1000.00')
        self.driver.cod_in_hand = Decimal('200.00')
        self.driver.pending_earnings = Decimal('50.00')
        self.driver.save()

        trans = WalletService.record_transaction(
            driver=self.driver,
            transaction_type='cod_collection',
            amount=Decimal('100.00'),
            description='COD collected',
        )
        self.assertEqual(trans.wallet_balance_after, Decimal('900.00'))
        self.assertEqual(trans.cod_in_hand_after, Decimal('300.00'))

    def test_multiple_sequential_transactions(self):
        # Simulate a day: earn, collect COD, collect more COD, deposit COD
        WalletService.record_transaction(
            self.driver, 'earning', Decimal('20.00'), 'Task 1 earnings')
        WalletService.record_transaction(
            self.driver, 'cod_collection', Decimal('50.00'), 'COD Task 1')
        WalletService.record_transaction(
            self.driver, 'cod_collection', Decimal('75.00'), 'COD Task 2')
        WalletService.record_transaction(
            self.driver, 'cod_deposit', Decimal('125.00'), 'Deposit all COD')

        self.driver.refresh_from_db()
        self.assertEqual(self.driver.total_earnings, Decimal('20.00'))
        self.assertEqual(self.driver.pending_earnings, Decimal('20.00'))
        self.assertEqual(self.driver.cod_in_hand, Decimal('0.00'))
        self.assertEqual(self.driver.wallet_balance, Decimal('0.00'))


class WalletServiceSubmitCODTest(DriverTestMixin, TransactionTestCase):
    """Test WalletService.submit_cod_to_admin."""

    def setUp(self):
        self.user, self.profile = self.create_driver_user()
        self.driver = self.create_driver(self.user, self.profile,
                                         wallet_balance=Decimal('-200.00'),
                                         cod_in_hand=Decimal('200.00'))

    def test_submit_cod_success(self):
        trans = WalletService.submit_cod_to_admin(
            driver=self.driver, amount=Decimal('200.00'),
            created_by=self.user, reference_number='REF001')
        self.driver.refresh_from_db()
        self.assertEqual(self.driver.cod_in_hand, Decimal('0.00'))
        self.assertEqual(self.driver.wallet_balance, Decimal('0.00'))

    def test_submit_cod_partial(self):
        trans = WalletService.submit_cod_to_admin(
            driver=self.driver, amount=Decimal('100.00'),
            created_by=self.user)
        self.driver.refresh_from_db()
        self.assertEqual(self.driver.cod_in_hand, Decimal('100.00'))
        self.assertEqual(self.driver.wallet_balance, Decimal('-100.00'))

    def test_submit_cod_exceeds_in_hand_raises(self):
        with self.assertRaises(ValueError):
            WalletService.submit_cod_to_admin(
                driver=self.driver, amount=Decimal('300.00'),
                created_by=self.user)


class WalletServiceCanAcceptCODTest(DriverTestMixin, TestCase):
    """Test WalletService.can_accept_cod_order."""

    def setUp(self):
        self.user, self.profile = self.create_driver_user()
        self.driver = self.create_driver(self.user, self.profile,
                                         wallet_balance=Decimal('1000.00'),
                                         credit_limit=Decimal('5000.00'))

    def test_can_accept_within_credit(self):
        can, reason = WalletService.can_accept_cod_order(self.driver, Decimal('100.00'))
        self.assertTrue(can)
        self.assertEqual(reason, 'OK')

    def test_cannot_accept_wallet_blocked(self):
        # Blocked when cod_in_hand >= credit_limit
        self.driver.cod_in_hand = Decimal('5000.00')  # At credit limit (5000)
        can, reason = WalletService.can_accept_cod_order(self.driver, Decimal('100.00'))
        self.assertFalse(can)
        self.assertIn('exhausted', reason.lower())

    def test_cannot_accept_exceeds_credit(self):
        self.driver.cod_in_hand = Decimal('100.00')  # Available credit = 4900
        self.driver.credit_limit = Decimal('5000.00')
        can, reason = WalletService.can_accept_cod_order(self.driver, Decimal('10000.00'))
        self.assertFalse(can)


class WalletServiceGetStatusTest(DriverTestMixin, TestCase):
    """Test WalletService.get_wallet_status."""

    def setUp(self):
        self.user, self.profile = self.create_driver_user()
        self.driver = self.create_driver(self.user, self.profile,
                                         credit_limit=Decimal('5000.00'),
                                         pending_earnings=Decimal('100.00'))
        # Create business/order needed for DeliveryTask
        biz_user = User.objects.create_user(
            username='statusbizuser', email='statusbiz@test.com', password='Pass@123')
        biz_profile = core_models.Profile.objects.create(
            user=biz_user, first_name='Biz', last_name='User', phone=55500001)
        from business import models as business_models
        biz = business_models.Business.objects.create(
            business_id=9901, user=biz_user, profile=biz_profile,
            business_name='Status Biz', business_code='STATBIZ',
            fulfillment_service_enabled=False, fulfillment_service_status='none')
        pickup = business_models.PickupLocation.objects.create(
            business=biz, pickup_location_title='Status Pickup',
            locality='Doha', pickup_zone_no=1,
            pickup_street_no=1, pickup_building_no=1)
        order = orders_models.Order.objects.create(
            business=biz, client_order_code='STAT-STATUS-001',
            customer_name='Test', customer_phone='11111111',
            customer_address='Test', dl_zone=1, dl_building=1, dl_street=1,
            pickup_location=pickup)
        # Create 4000 QR worth of COD tasks (unsettled)
        task1 = delivery_models.DeliveryTask.objects.create(
            dl_task_number='STAT-T001', dl_task_description='Test',
            order=order, business=biz, driver=self.driver,
            dl_task_status='delivered', dl_price=50,
            cod_collected=True, cod_settled=False, cod_collected_amount=Decimal('2500.00'))
        task2 = delivery_models.DeliveryTask.objects.create(
            dl_task_number='STAT-T002', dl_task_description='Test',
            order=order, business=biz, driver=self.driver,
            dl_task_status='delivered', dl_price=50,
            cod_collected=True, cod_settled=False, cod_collected_amount=Decimal('1500.00'))
        # Create transaction for live_wallet calculation (-4000 net)
        fleet_models.DriverTransaction.objects.create(
            driver=self.driver, transaction_type='cod_collection',
            amount=Decimal('-4000.00'), description='COD collected')

    def test_wallet_status_fields(self):
        status = WalletService.get_wallet_status(self.driver)
        # live_cod from DeliveryTask: 2500 + 1500 = 4000
        self.assertEqual(status['cod_in_hand'], Decimal('4000.00'))
        self.assertEqual(status['credit_limit'], Decimal('5000.00'))
        self.assertEqual(status['available_credit'], Decimal('1000.00'))
        self.assertEqual(status['pending_earnings'], Decimal('100.00'))
        self.assertTrue(status['is_warning'])  # 4000/5000 = 80%
        self.assertFalse(status['is_blocked'])  # 4000 < 5000, not blocked
        self.assertIsNotNone(status['warning_message'])

    def test_wallet_status_healthy(self):
        # No DeliveryTask or transactions: everything is zero/healthy
        status = WalletService.get_wallet_status(self.driver)
        # But setUp created 4000 COD tasks - need fresh driver
        user2 = User.objects.create_user(
            username='healthydriver', email='healthy@test.com', password='Pass@123')
        profile2 = core_models.Profile.objects.create(
            user=user2, first_name='H', last_name='D', phone=55500002, is_driver=True)
        driver2 = self.create_driver(user2, profile2, driver_id=9901, driver_code='HLTH01')
        status2 = WalletService.get_wallet_status(driver2)
        self.assertFalse(status2['is_warning'])
        self.assertFalse(status2['is_blocked'])
        self.assertIsNone(status2['warning_message'])
        self.assertIsNone(status2['block_message'])


class WalletServiceGetDriverStatisticsTest(DriverTestMixin, TestCase):
    """Test WalletService.get_driver_statistics."""

    def setUp(self):
        self.user, self.profile = self.create_driver_user()
        self.driver = self.create_driver(self.user, self.profile)

    def test_statistics_empty(self):
        stats = WalletService.get_driver_statistics(self.driver, days=30)
        self.assertEqual(stats['total_deliveries'], 0)
        self.assertEqual(stats['successful_deliveries'], 0)
        self.assertEqual(stats['failed_deliveries'], 0)
        self.assertEqual(stats['total_earnings'], Decimal('0.00'))
        self.assertEqual(stats['success_rate'], 0)

    def test_statistics_with_period(self):
        stats_7 = WalletService.get_driver_statistics(self.driver, days=7)
        stats_30 = WalletService.get_driver_statistics(self.driver, days=30)
        self.assertEqual(stats_7['period_days'], 7)
        self.assertEqual(stats_30['period_days'], 30)


class WalletServiceSettlementTest(DriverTestMixin, TransactionTestCase):
    """Test WalletService settlement workflow."""

    def setUp(self):
        self.user, self.profile = self.create_driver_user()
        self.driver = self.create_driver(self.user, self.profile,
                                         pending_earnings=Decimal('500.00'))

    def test_generate_settlement(self):
        settlement = WalletService.generate_settlement(
            driver=self.driver,
            period_start=date(2025, 1, 1),
            period_end=date(2025, 1, 31),
            created_by=self.user,
        )
        self.assertEqual(settlement.status, 'pending')
        self.assertIn('STL-', settlement.settlement_code)

    def test_approve_settlement(self):
        settlement = fleet_models.DriverSettlement.objects.create(
            driver=self.driver,
            period_start=date(2025, 1, 1),
            period_end=date(2025, 1, 31),
            net_amount=Decimal('500.00'),
            status='pending',
        )
        approved = WalletService.approve_settlement(settlement, self.user)
        self.assertEqual(approved.status, 'approved')
        self.assertIsNotNone(approved.approved_at)

    def test_approve_non_pending_raises(self):
        settlement = fleet_models.DriverSettlement.objects.create(
            driver=self.driver,
            period_start=date(2025, 1, 1),
            period_end=date(2025, 1, 31),
            status='paid',
        )
        with self.assertRaises(ValueError):
            WalletService.approve_settlement(settlement, self.user)

    def test_mark_settlement_paid(self):
        settlement = fleet_models.DriverSettlement.objects.create(
            driver=self.driver,
            period_start=date(2025, 1, 1),
            period_end=date(2025, 1, 31),
            net_amount=Decimal('500.00'),
            status='approved',
        )
        paid_settlement, trans = WalletService.mark_settlement_paid(
            settlement, 'Bank Transfer', 'REF123', paid_by=self.user)
        self.assertEqual(paid_settlement.status, 'paid')
        self.assertIsNotNone(paid_settlement.paid_at)
        self.assertEqual(trans.transaction_type, 'settlement')

    def test_mark_unpproved_settlement_paid_raises(self):
        settlement = fleet_models.DriverSettlement.objects.create(
            driver=self.driver,
            period_start=date(2025, 1, 1),
            period_end=date(2025, 1, 31),
            status='pending',
        )
        with self.assertRaises(ValueError):
            WalletService.mark_settlement_paid(
                settlement, 'Cash', 'REF999', paid_by=self.user)


class WalletAlertServiceTest(DriverTestMixin, TestCase):
    """Test WalletAlertService."""

    def setUp(self):
        self.user, self.profile = self.create_driver_user()

    def test_no_alerts_healthy_wallet(self):
        driver = self.create_driver(self.user, self.profile,
                                    wallet_balance=Decimal('1000.00'))
        alerts = WalletAlertService.check_wallet_alerts(driver)
        # Should have no danger/warning alerts (maybe success for earnings)
        danger = [a for a in alerts if a['level'] == 'danger']
        warning = [a for a in alerts if a['level'] == 'warning']
        self.assertEqual(len(danger), 0)
        self.assertEqual(len(warning), 0)

    def test_blocked_alert(self):
        driver = self.create_driver(self.user, self.profile,
                                    wallet_balance=Decimal('-5000.00'),
                                    cod_in_hand=Decimal('5000.00'))
        alerts = WalletAlertService.check_wallet_alerts(driver)
        danger = [a for a in alerts if a['level'] == 'danger']
        self.assertEqual(len(danger), 1)
        self.assertIn('Blocked', danger[0]['title'])

    def test_warning_alert(self):
        # Warning triggers when cod_in_hand >= 80% of credit_limit but < credit_limit
        # 4100 / 5000 = 82% -> warning, not blocked
        driver2_user, driver2_profile = self.create_driver_user(
            username='driver2', email='d2@test.com')
        driver2 = self.create_driver(driver2_user, driver2_profile,
                                     driver_id=1002, driver_code='DRV002',
                                     cod_in_hand=Decimal('4100.00'),
                                     credit_limit=Decimal('5000.00'))
        alerts = WalletAlertService.check_wallet_alerts(driver2)
        warning = [a for a in alerts if a['level'] == 'warning']
        self.assertEqual(len(warning), 1)

    def test_high_cod_alert(self):
        driver = self.create_driver(self.user, self.profile,
                                    wallet_balance=Decimal('2000.00'),
                                    cod_in_hand=Decimal('1500.00'))
        alerts = WalletAlertService.check_wallet_alerts(driver)
        info = [a for a in alerts if a['level'] == 'info']
        self.assertEqual(len(info), 1)
        self.assertIn('High COD', info[0]['title'])

    def test_pending_earnings_alert(self):
        driver = self.create_driver(self.user, self.profile,
                                    wallet_balance=Decimal('1000.00'),
                                    pending_earnings=Decimal('200.00'))
        alerts = WalletAlertService.check_wallet_alerts(driver)
        success = [a for a in alerts if a['level'] == 'success']
        self.assertEqual(len(success), 1)
        self.assertIn('Earnings', success[0]['title'])


# =============================================================================
# VIEW TESTS - AUTHENTICATION & AUTHORIZATION
# =============================================================================

class DriverAuthorizationTest(DriverTestMixin, TestCase):
    """Test authentication and driver_required decorator on all fleet views."""

    def setUp(self):
        self.client = Client()

    def test_unauthenticated_redirects(self):
        """All fleet views should redirect unauthenticated users."""
        urls = [
            '/fleet/', '/fleet/dashboard/', '/fleet/documents/',
            '/fleet/vehicle_own/', '/fleet/cod_collection/',
            '/fleet/cod_submission/', '/fleet/earnings/',
            '/fleet/transactions/', '/fleet/profile/',
            '/fleet/performance/', '/fleet/reports/',
            '/fleet/analytics/',
        ]
        for url in urls:
            response = self.client.get(url)
            self.assertIn(response.status_code, [301, 302],
                         f"Expected redirect for {url}, got {response.status_code}")

    def test_non_driver_user_redirected(self):
        """Non-driver users should be redirected from fleet views."""
        non_driver = self.create_non_driver_user()
        self.client.login(username='nondriver', password='TestDriver@123')

        urls = [
            '/fleet/', '/fleet/dashboard/', '/fleet/documents/',
            '/fleet/vehicle_own/', '/fleet/cod_collection/',
            '/fleet/cod_submission/', '/fleet/earnings/',
            '/fleet/transactions/', '/fleet/profile/',
            '/fleet/performance/', '/fleet/reports/',
            '/fleet/analytics/',
        ]
        for url in urls:
            response = self.client.get(url)
            self.assertIn(response.status_code, [301, 302],
                         f"Non-driver should be redirected from {url}")


# =============================================================================
# VIEW TESTS - FLEET DASHBOARD
# =============================================================================

class FleetDashboardViewTest(DriverTestMixin, TestCase):
    """Test fleet dashboard views."""

    def setUp(self):
        self.client = Client()
        self.user, self.profile = self.create_driver_user()
        self.driver = self.create_driver(self.user, self.profile)
        self.client.login(username='testdriver', password='TestDriver@123')

    def test_fleet_dashboard_loads(self):
        response = self.client.get('/fleet/dashboard/')
        self.assertEqual(response.status_code, 200)
        self.assertIn('driver', response.context)
        self.assertIn('wallet_status', response.context)
        self.assertIn('stats_30_days', response.context)
        self.assertIn('stats_7_days', response.context)

    def test_fleet_dashboard_no_driver_profile(self):
        """If Driver object doesn't exist, should redirect."""
        self.driver.delete()
        response = self.client.get('/fleet/dashboard/')
        self.assertIn(response.status_code, [301, 302])

    def test_fleets_list_loads(self):
        response = self.client.get('/fleet/')
        self.assertEqual(response.status_code, 200)
        self.assertIn('fleets', response.context)


# =============================================================================
# VIEW TESTS - MOBILE PROFILE
# =============================================================================

class DriverProfileMobileViewTest(DriverTestMixin, TestCase):
    """Test driver mobile PWA profile view."""

    def setUp(self):
        self.client = Client()
        self.user, self.profile = self.create_driver_user()
        self.driver = self.create_driver(self.user, self.profile)
        self.client.login(username='testdriver', password='TestDriver@123')

    def test_mobile_profile_loads(self):
        response = self.client.get('/fleet/profile/')
        self.assertEqual(response.status_code, 200)
        self.assertIn('driver', response.context)
        self.assertIn('wallet_status', response.context)
        self.assertIn('stats', response.context)
        self.assertIn('average_rating', response.context)
        self.assertIn('documents_count', response.context)

    def test_mobile_profile_zero_ratings(self):
        response = self.client.get('/fleet/profile/')
        self.assertEqual(response.context['average_rating'], 0)

    def test_mobile_profile_with_ratings(self):
        self.driver.driver_rating = 45
        self.driver.driver_rating_count = 10
        self.driver.save()
        response = self.client.get('/fleet/profile/')
        self.assertAlmostEqual(response.context['average_rating'], 4.5)

    def test_mobile_profile_zone_update(self):
        """Test POST to update zone preferences."""
        # Create zone groups
        zg = delivery_models.ZoneGroup.objects.create(
            name='Doha Central', is_active=True)
        response = self.client.post('/fleet/profile/', {
            'update_zones': '1',
            'preferred_zone_groups': [zg.id],
        })
        self.assertIn(response.status_code, [301, 302])  # redirect after success
        self.driver.refresh_from_db()
        self.assertIn(zg, self.driver.preferred_zone_groups.all())

    def test_mobile_profile_clear_zones(self):
        """Test clearing all zone preferences."""
        zg = delivery_models.ZoneGroup.objects.create(
            name='Doha Central', is_active=True)
        self.driver.preferred_zone_groups.add(zg)
        response = self.client.post('/fleet/profile/', {
            'update_zones': '1',
        })
        self.assertIn(response.status_code, [301, 302])
        self.driver.refresh_from_db()
        self.assertEqual(self.driver.preferred_zone_groups.count(), 0)

    def test_mobile_profile_no_driver_redirects(self):
        self.driver.delete()
        response = self.client.get('/fleet/profile/')
        self.assertIn(response.status_code, [301, 302])


# =============================================================================
# VIEW TESTS - DOCUMENTS
# =============================================================================

class DriverDocumentsViewTest(DriverTestMixin, TestCase):
    """Test document management views."""

    def setUp(self):
        self.client = Client()
        self.user, self.profile = self.create_driver_user()
        self.driver = self.create_driver(self.user, self.profile)
        self.client.login(username='testdriver', password='TestDriver@123')

    def test_documents_list_loads(self):
        response = self.client.get('/fleet/documents/')
        self.assertEqual(response.status_code, 200)

    def test_documents_list_shows_documents(self):
        fleet_models.DriverDocument.objects.create(
            driver=self.driver, document_type='QID', document_no='QID123')
        response = self.client.get('/fleet/documents/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context['documents']), 1)

    def test_document_upload_get(self):
        response = self.client.get(f'/fleet/documents/upload/{self.user.id}/')
        self.assertEqual(response.status_code, 200)

    def test_document_upload_no_driver_redirects(self):
        self.driver.delete()
        response = self.client.get(f'/fleet/documents/upload/{self.user.id}/')
        self.assertIn(response.status_code, [301, 302])

    def test_document_delete_idor_protection(self):
        """A driver should not be able to delete another driver's document by fleet_id."""
        doc = fleet_models.DriverDocument.objects.create(
            driver=self.driver, document_type='QID', document_no='QID123')

        other_user, other_profile = self.create_driver_user(
            username='other_driver', email='other@test.com')
        other_driver = self.create_driver(other_user, other_profile,
                                          driver_id=1002, driver_code='DRV002')

        # Login as other driver and try to delete doc using first driver's fleet_id
        self.client.login(username='other_driver', password='TestDriver@123')
        response = self.client.get(
            f'/fleet/documents/{self.user.id}/{doc.id}/delete')
        # Should redirect due to IDOR check (fleet_id != request.user.id)
        self.assertIn(response.status_code, [301, 302])
        # Doc should still exist
        self.assertTrue(
            fleet_models.DriverDocument.objects.filter(id=doc.id).exists())

    def test_document_update_idor_protection(self):
        """A driver should not be able to update another driver's document."""
        doc = fleet_models.DriverDocument.objects.create(
            driver=self.driver, document_type='QID', document_no='QID123')

        other_user, _ = self.create_driver_user(
            username='other_driver2', email='other2@test.com')
        self.create_driver(other_user, core_models.Profile.objects.get(user=other_user),
                          driver_id=1003, driver_code='DRV003')

        self.client.login(username='other_driver2', password='TestDriver@123')
        response = self.client.get(
            f'/fleet/documents/{self.user.id}/{doc.id}/update')
        self.assertIn(response.status_code, [301, 302])


# =============================================================================
# VIEW TESTS - VEHICLES
# =============================================================================

class VehicleViewTest(DriverTestMixin, TestCase):
    """Test vehicle management views."""

    def setUp(self):
        self.client = Client()
        self.user, self.profile = self.create_driver_user()
        self.driver = self.create_driver(self.user, self.profile)
        self.client.login(username='testdriver', password='TestDriver@123')

    def test_vehicle_list_loads(self):
        response = self.client.get('/fleet/vehicle_own/')
        self.assertEqual(response.status_code, 200)

    def test_vehicle_list_shows_vehicles(self):
        fleet_models.DriverVehicle.objects.create(
            driver=self.driver, vehicle_type='car', vehicle_no='QA-1234')
        response = self.client.get('/fleet/vehicle_own/')
        self.assertEqual(len(response.context['vehicles']), 1)

    def test_vehicle_add_get(self):
        response = self.client.get('/fleet/vehicle_add/')
        self.assertEqual(response.status_code, 200)

    def test_vehicle_add_post(self):
        response = self.client.post('/fleet/vehicle_add/', {
            'vehicle_type': 'car',
            'vehicle_no': 'QA-9999',
            'vehicle_model': 'Toyota Camry',
            'vehicle_color': 'Black',
            'vehicle_status': 'active',
        })
        self.assertIn(response.status_code, [301, 302])
        self.assertTrue(
            fleet_models.DriverVehicle.objects.filter(vehicle_no='QA-9999').exists())

    def test_vehicle_update_get(self):
        vehicle = fleet_models.DriverVehicle.objects.create(
            driver=self.driver, vehicle_type='car', vehicle_no='QA-1234')
        response = self.client.get(f'/fleet/vehicle/{vehicle.id}/update/')
        self.assertEqual(response.status_code, 200)

    def test_vehicle_update_post(self):
        vehicle = fleet_models.DriverVehicle.objects.create(
            driver=self.driver, vehicle_type='car', vehicle_no='QA-1234')
        response = self.client.post(f'/fleet/vehicle/{vehicle.id}/update/', {
            'vehicle_type': 'van',
            'vehicle_no': 'QA-1234',
            'vehicle_model': 'Ford Transit',
            'vehicle_color': 'Blue',
            'vehicle_status': 'active',
        })
        self.assertIn(response.status_code, [301, 302])
        vehicle.refresh_from_db()
        self.assertEqual(vehicle.vehicle_type, 'van')

    def test_vehicle_update_idor(self):
        """A driver can't update another driver's vehicle."""
        vehicle = fleet_models.DriverVehicle.objects.create(
            driver=self.driver, vehicle_type='car', vehicle_no='QA-1234')

        other_user, other_profile = self.create_driver_user(
            username='otherdriver', email='other@test.com')
        self.create_driver(other_user, other_profile,
                          driver_id=1002, driver_code='DRV002')

        self.client.login(username='otherdriver', password='TestDriver@123')
        response = self.client.get(f'/fleet/vehicle/{vehicle.id}/update/')
        # Should redirect because vehicle doesn't belong to this driver
        self.assertIn(response.status_code, [301, 302])

    def test_vehicle_update_nonexistent_vehicle(self):
        """Updating nonexistent vehicle should redirect."""
        response = self.client.get('/fleet/vehicle/99999/update/')
        self.assertIn(response.status_code, [301, 302])

    def test_vehicle_delete_requires_staff(self):
        """Non-staff users cannot delete vehicles."""
        vehicle = fleet_models.DriverVehicle.objects.create(
            driver=self.driver, vehicle_type='car', vehicle_no='QA-1234')
        response = self.client.get(
            f'/fleet/vehicle_delete/{self.user.id}/{vehicle.id}/')
        self.assertIn(response.status_code, [301, 302])
        # Vehicle should still exist
        self.assertTrue(
            fleet_models.DriverVehicle.objects.filter(id=vehicle.id).exists())

    def test_vehicle_delete_staff_succeeds(self):
        """Staff users can delete vehicles."""
        self.user.is_staff = True
        self.user.save()
        vehicle = fleet_models.DriverVehicle.objects.create(
            driver=self.driver, vehicle_type='car', vehicle_no='QA-1234')
        response = self.client.get(
            f'/fleet/vehicle_delete/{self.user.id}/{vehicle.id}/')
        self.assertIn(response.status_code, [301, 302])
        self.assertFalse(
            fleet_models.DriverVehicle.objects.filter(id=vehicle.id).exists())

    def test_vehicle_delete_idor(self):
        """A driver can't delete another driver's vehicle."""
        vehicle = fleet_models.DriverVehicle.objects.create(
            driver=self.driver, vehicle_type='car', vehicle_no='QA-1234')

        other_user = self.create_non_driver_user(
            username='staffuser', email='staff@test.com')
        # Make them staff and driver to pass both checks
        other_user.is_staff = True
        other_user.save()
        p = core_models.Profile.objects.get(user=other_user)
        p.is_driver = True
        p.save()
        self.create_driver(other_user, p, driver_id=1002, driver_code='DRV002')

        self.client.login(username='staffuser', password='TestDriver@123')
        # fleet_id doesn't match request.user.id
        response = self.client.get(
            f'/fleet/vehicle_delete/{self.user.id}/{vehicle.id}/')
        self.assertIn(response.status_code, [301, 302])
        self.assertTrue(
            fleet_models.DriverVehicle.objects.filter(id=vehicle.id).exists())


# =============================================================================
# VIEW TESTS - COD & WALLET
# =============================================================================

class CODCollectionViewTest(DriverTestMixin, TestCase):
    """Test COD collection view."""

    def setUp(self):
        self.client = Client()
        self.user, self.profile = self.create_driver_user()
        self.driver = self.create_driver(self.user, self.profile,
                                         cod_in_hand=Decimal('500.00'))
        self.client.login(username='testdriver', password='TestDriver@123')

    def test_cod_collection_loads(self):
        response = self.client.get('/fleet/cod_collection/')
        self.assertEqual(response.status_code, 200)
        self.assertIn('driver', response.context)
        self.assertIn('wallet_status', response.context)

    def test_cod_collection_no_driver_redirects(self):
        self.driver.delete()
        response = self.client.get('/fleet/cod_collection/')
        self.assertIn(response.status_code, [301, 302])


class CODSubmissionViewTest(DriverTestMixin, TestCase):
    """Test COD submission view."""

    def setUp(self):
        self.client = Client()
        self.user, self.profile = self.create_driver_user()
        self.driver = self.create_driver(self.user, self.profile,
                                         wallet_balance=Decimal('-500.00'),
                                         cod_in_hand=Decimal('500.00'))
        self.client.login(username='testdriver', password='TestDriver@123')

    def test_cod_submission_get(self):
        # GET redirects to cod_collection (consolidated page)
        response = self.client.get('/fleet/cod_submission/')
        self.assertIn(response.status_code, [301, 302])

    def test_cod_submission_post_success(self):
        response = self.client.post('/fleet/cod_submission/', {
            'amount': '200',
            'reference_number': 'REF001',
            'notes': 'Cash deposit',
        })
        self.assertIn(response.status_code, [301, 302])
        self.driver.refresh_from_db()
        self.assertEqual(self.driver.cod_in_hand, Decimal('300.00'))

    def test_cod_submission_post_zero_amount(self):
        response = self.client.post('/fleet/cod_submission/', {
            'amount': '0',
        })
        self.assertEqual(response.status_code, 200)  # re-renders with error

    def test_cod_submission_post_negative_amount(self):
        response = self.client.post('/fleet/cod_submission/', {
            'amount': '-100',
        })
        self.assertEqual(response.status_code, 200)

    def test_cod_submission_post_exceeds_in_hand(self):
        response = self.client.post('/fleet/cod_submission/', {
            'amount': '600',
        })
        self.assertEqual(response.status_code, 200)  # error message shown

    def test_cod_submission_post_invalid_amount(self):
        response = self.client.post('/fleet/cod_submission/', {
            'amount': 'abc',
        })
        self.assertEqual(response.status_code, 200)

    def test_cod_submission_no_driver_redirects(self):
        self.driver.delete()
        response = self.client.get('/fleet/cod_submission/')
        self.assertIn(response.status_code, [301, 302])


# =============================================================================
# VIEW TESTS - EARNINGS & TRANSACTIONS
# =============================================================================

class DriverEarningsViewTest(DriverTestMixin, TestCase):
    """Test earnings view."""

    def setUp(self):
        self.client = Client()
        self.user, self.profile = self.create_driver_user()
        self.driver = self.create_driver(self.user, self.profile)
        self.client.login(username='testdriver', password='TestDriver@123')

    def test_earnings_loads(self):
        response = self.client.get('/fleet/earnings/')
        self.assertEqual(response.status_code, 200)
        self.assertIn('total_delivery_fee', response.context)

    def test_earnings_filter_days(self):
        response = self.client.get('/fleet/earnings/?days=7')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['selected_days'], 7)

    def test_earnings_filter_status(self):
        response = self.client.get('/fleet/earnings/?status=delivered')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['selected_status'], 'delivered')

    def test_earnings_no_driver_redirects(self):
        self.driver.delete()
        response = self.client.get('/fleet/earnings/')
        self.assertIn(response.status_code, [301, 302])


class TransactionHistoryViewTest(DriverTestMixin, TestCase):
    """Test transaction history view."""

    def setUp(self):
        self.client = Client()
        self.user, self.profile = self.create_driver_user()
        self.driver = self.create_driver(self.user, self.profile)
        self.client.login(username='testdriver', password='TestDriver@123')

    def test_transactions_loads(self):
        response = self.client.get('/fleet/transactions/')
        self.assertEqual(response.status_code, 200)
        self.assertIn('transactions', response.context)

    def test_transactions_filter_type(self):
        response = self.client.get('/fleet/transactions/?type=earning')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['selected_type'], 'earning')

    def test_transactions_filter_days(self):
        response = self.client.get('/fleet/transactions/?days=7')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['selected_days'], 7)

    def test_transactions_no_driver_redirects(self):
        self.driver.delete()
        response = self.client.get('/fleet/transactions/')
        self.assertIn(response.status_code, [301, 302])


# =============================================================================
# VIEW TESTS - PERFORMANCE & ANALYTICS
# =============================================================================

class DriverPerformanceViewTest(DriverTestMixin, TestCase):
    """Test performance dashboard view."""

    def setUp(self):
        self.client = Client()
        self.user, self.profile = self.create_driver_user()
        self.driver = self.create_driver(self.user, self.profile)
        self.client.login(username='testdriver', password='TestDriver@123')

    def test_performance_loads(self):
        response = self.client.get('/fleet/performance/')
        self.assertEqual(response.status_code, 200)
        self.assertIn('performance_metrics', response.context)
        self.assertIn('daily_stats', response.context)

    def test_performance_period_filter(self):
        response = self.client.get('/fleet/performance/?period=7')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['selected_period'], '7')

    def test_performance_invalid_period_falls_back(self):
        """Invalid 'period' parameter should fall back to 30 days."""
        response = self.client.get('/fleet/performance/?period=abc')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['selected_period'], '30')

    def test_performance_zero_ratings(self):
        response = self.client.get('/fleet/performance/')
        self.assertEqual(
            response.context['performance_metrics']['average_rating'], 0)

    def test_performance_with_ratings(self):
        self.driver.driver_rating = 40
        self.driver.driver_rating_count = 10
        self.driver.save()
        response = self.client.get('/fleet/performance/')
        self.assertAlmostEqual(
            response.context['performance_metrics']['average_rating'], 4.0)

    def test_performance_no_driver_redirects(self):
        self.driver.delete()
        response = self.client.get('/fleet/performance/')
        self.assertIn(response.status_code, [301, 302])


class DriverReportsViewTest(DriverTestMixin, TestCase):
    """Test reports view."""

    def setUp(self):
        self.client = Client()
        self.user, self.profile = self.create_driver_user()
        self.driver = self.create_driver(self.user, self.profile)
        self.client.login(username='testdriver', password='TestDriver@123')

    def test_reports_loads(self):
        response = self.client.get('/fleet/reports/')
        self.assertEqual(response.status_code, 200)
        self.assertIn('report_types', response.context)
        self.assertEqual(len(response.context['report_types']), 4)

    def test_reports_no_driver_redirects(self):
        self.driver.delete()
        response = self.client.get('/fleet/reports/')
        self.assertIn(response.status_code, [301, 302])


class DriverAnalyticsViewTest(DriverTestMixin, TestCase):
    """Test analytics view."""

    def setUp(self):
        self.client = Client()
        self.user, self.profile = self.create_driver_user()
        self.driver = self.create_driver(self.user, self.profile)
        self.client.login(username='testdriver', password='TestDriver@123')

    def test_analytics_loads(self):
        response = self.client.get('/fleet/analytics/')
        self.assertEqual(response.status_code, 200)
        self.assertIn('monthly_data', response.context)
        self.assertIn('delivery_categories', response.context)
        self.assertIn('peak_hours', response.context)

    def test_analytics_no_driver_redirects(self):
        self.driver.delete()
        response = self.client.get('/fleet/analytics/')
        self.assertIn(response.status_code, [301, 302])


# =============================================================================
# VIEW TESTS - DRIVER PROFILE (FRONTEND)
# =============================================================================

class DriverProfileViewTest(DriverTestMixin, TestCase):
    """Test public driver profile view."""

    def setUp(self):
        self.client = Client()
        self.user, self.profile = self.create_driver_user()
        self.driver = self.create_driver(self.user, self.profile)
        self.client.login(username='testdriver', password='TestDriver@123')

    def test_driver_profile_loads(self):
        response = self.client.get(f'/fleet/{self.driver.driver_id}/')
        self.assertEqual(response.status_code, 200)
        self.assertIn('driver', response.context)
        self.assertIn('profile', response.context)
        self.assertIn('seo', response.context)

    def test_driver_profile_nonexistent_driver(self):
        response = self.client.get('/fleet/9999/')
        self.assertIn(response.status_code, [301, 302])


# =============================================================================
# VIEW TESTS - PICKUP SCANNER
# =============================================================================

class PickupScannerViewTest(DriverTestMixin, TestCase):
    """Test pickup scanner views."""

    def setUp(self):
        self.client = Client()
        self.user, self.profile = self.create_driver_user()
        self.driver = self.create_driver(self.user, self.profile)
        self.client.login(username='testdriver', password='TestDriver@123')

        # Create business, order, task
        self.business, self.pickup, self.order = self.create_business_and_order(
            self.user, self.profile)

    def test_scanner_page_loads(self):
        response = self.client.get('/fleet/pickup/scanner/')
        self.assertEqual(response.status_code, 200)
        self.assertIn('pending_tasks', response.context)

    def test_scanner_shows_pending_tasks(self):
        task = self.create_delivery_task(
            self.order, self.business, self.pickup,
            driver=self.driver, status='pending')
        delivery_models.AssignedDriver.objects.create(
            driver=self.driver, dl_task=task)
        response = self.client.get('/fleet/pickup/scanner/')
        self.assertEqual(response.context['pending_count'], 1)

    def test_scan_process_post_by_task_number(self):
        task = self.create_delivery_task(
            self.order, self.business, self.pickup,
            driver=self.driver, status='assigned',
            task_number='SCAN-001')
        delivery_models.AssignedDriver.objects.create(
            driver=self.driver, dl_task=task)

        response = self.client.post(
            '/fleet/pickup/scan/',
            json.dumps({'code': 'SCAN-001'}),
            content_type='application/json')
        data = json.loads(response.content)
        self.assertTrue(data['success'])
        self.assertEqual(data['task_number'], 'SCAN-001')

        task.refresh_from_db()
        self.assertEqual(task.dl_task_status, 'in_transit')

    def test_scan_process_empty_code(self):
        response = self.client.post(
            '/fleet/pickup/scan/',
            json.dumps({'code': ''}),
            content_type='application/json')
        data = json.loads(response.content)
        self.assertFalse(data['success'])
        self.assertIn('No code', data['error'])

    def test_scan_process_no_matching_task(self):
        response = self.client.post(
            '/fleet/pickup/scan/',
            json.dumps({'code': 'NONEXISTENT-999'}),
            content_type='application/json')
        data = json.loads(response.content)
        self.assertFalse(data['success'])

    def test_scan_process_already_picked_up(self):
        task = self.create_delivery_task(
            self.order, self.business, self.pickup,
            driver=self.driver, status='in_transit',
            task_number='SCAN-002')
        delivery_models.AssignedDriver.objects.create(
            driver=self.driver, dl_task=task)

        response = self.client.post(
            '/fleet/pickup/scan/',
            json.dumps({'code': 'SCAN-002'}),
            content_type='application/json')
        data = json.loads(response.content)
        self.assertFalse(data['success'])
        self.assertIn('already picked up', data['error'])

    def test_scan_process_get_method_rejected(self):
        response = self.client.get('/fleet/pickup/scan/')
        data = json.loads(response.content)
        self.assertFalse(data['success'])
        self.assertIn('Invalid', data['error'])

    def test_scan_process_no_driver_profile(self):
        self.driver.delete()
        response = self.client.post(
            '/fleet/pickup/scan/',
            json.dumps({'code': 'SCAN-001'}),
            content_type='application/json')
        data = json.loads(response.content)
        self.assertFalse(data['success'])


# =============================================================================
# DELIVERY VIEW TESTS - DRIVER TASK MANAGEMENT
# =============================================================================

class AllDeliveryTasksViewTest(DriverTestMixin, TestCase):
    """Test all_delivery_tasks driver view."""

    def setUp(self):
        self.client = Client()
        self.user, self.profile = self.create_driver_user()
        self.driver = self.create_driver(self.user, self.profile)
        self.client.login(username='testdriver', password='TestDriver@123')
        self.business, self.pickup, self.order = self.create_business_and_order(
            self.user, self.profile)

    def test_delivery_tasks_loads(self):
        response = self.client.get('/delivery/delivery_tasks/all/')
        self.assertEqual(response.status_code, 200)
        self.assertIn('cards', response.context)
        self.assertIn('driver', response.context)

    def test_delivery_tasks_new_tab(self):
        response = self.client.get('/delivery/delivery_tasks/all/?tab=new')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['current_tab'], 'new')

    def test_delivery_tasks_assigned_tab(self):
        response = self.client.get('/delivery/delivery_tasks/all/?tab=assigned')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['current_tab'], 'assigned')

    def test_delivery_tasks_area_filters(self):
        for area in ['all', 'doha', 'my_zone', 'qatar']:
            response = self.client.get(
                f'/delivery/delivery_tasks/all/?area={area}')
            self.assertEqual(response.status_code, 200,
                           f"Area filter '{area}' should work")

    def test_delivery_tasks_type_filters(self):
        for ttype in ['all', 'public', 'pnd']:
            response = self.client.get(
                f'/delivery/delivery_tasks/all/?type={ttype}')
            self.assertEqual(response.status_code, 200,
                           f"Type filter '{ttype}' should work")

    def test_delivery_tasks_no_driver_redirects(self):
        self.driver.delete()
        response = self.client.get('/delivery/delivery_tasks/all/')
        self.assertIn(response.status_code, [301, 302])


class AssignDriverViewTest(DriverTestMixin, TestCase):
    """Test driver self-assignment."""

    def setUp(self):
        self.client = Client()
        self.user, self.profile = self.create_driver_user()
        self.driver = self.create_driver(self.user, self.profile)
        self.client.login(username='testdriver', password='TestDriver@123')
        self.business, self.pickup, self.order = self.create_business_and_order(
            self.user, self.profile)

    def test_assign_driver_success(self):
        task = self.create_delivery_task(
            self.order, self.business, self.pickup,
            status='pending', task_number='ASSIGN-001',
            dl_task_publish=True)
        response = self.client.post(
            '/delivery/delivery_task/assign_driver/',
            {'task_id': task.id})
        data = json.loads(response.content)
        self.assertTrue(data['success'])
        self.assertTrue(
            delivery_models.AssignedDriver.objects.filter(
                driver=self.driver, dl_task=task).exists())
        task.refresh_from_db()
        self.assertEqual(task.dl_task_status, 'accepted')

    def test_assign_driver_no_task_id(self):
        response = self.client.post(
            '/delivery/delivery_task/assign_driver/', {})
        data = json.loads(response.content)
        self.assertFalse(data['success'])
        self.assertIn('Task ID', data['error'])

    def test_assign_driver_already_assigned(self):
        task = self.create_delivery_task(
            self.order, self.business, self.pickup,
            status='pending', task_number='ASSIGN-002')
        delivery_models.AssignedDriver.objects.create(
            driver=self.driver, dl_task=task)
        response = self.client.post(
            '/delivery/delivery_task/assign_driver/',
            {'task_id': task.id})
        data = json.loads(response.content)
        self.assertFalse(data['success'])
        self.assertIn('already assigned', data['error'])

    def test_assign_driver_nonexistent_task(self):
        response = self.client.post(
            '/delivery/delivery_task/assign_driver/',
            {'task_id': 99999})
        data = json.loads(response.content)
        self.assertFalse(data['success'])

    def test_assign_driver_get_method_rejected(self):
        response = self.client.get(
            '/delivery/delivery_task/assign_driver/')
        data = json.loads(response.content)
        self.assertFalse(data['success'])
        self.assertIn('Invalid', data['error'])

    def test_assign_driver_non_driver_user(self):
        non_driver = self.create_non_driver_user()
        self.client.login(username='nondriver', password='TestDriver@123')
        task = self.create_delivery_task(
            self.order, self.business, self.pickup, task_number='ASSIGN-003')
        response = self.client.post(
            '/delivery/delivery_task/assign_driver/',
            {'task_id': task.id})
        data = json.loads(response.content)
        self.assertFalse(data['success'])


class StartRideViewTest(DriverTestMixin, TestCase):
    """Test start ride view."""

    def setUp(self):
        self.client = Client()
        self.user, self.profile = self.create_driver_user()
        self.driver = self.create_driver(self.user, self.profile)
        self.client.login(username='testdriver', password='TestDriver@123')
        self.business, self.pickup, self.order = self.create_business_and_order(
            self.user, self.profile)

    def test_start_ride_success(self):
        task = self.create_delivery_task(
            self.order, self.business, self.pickup,
            driver=self.driver, status='assigned', task_number='RIDE-001',
            dl_task_publish=True)
        delivery_models.AssignedDriver.objects.create(
            driver=self.driver, dl_task=task)

        response = self.client.post(
            '/delivery/delivery_task/start_ride/',
            {'task_id': task.id})
        data = json.loads(response.content)
        self.assertTrue(data['success'])
        self.assertIn('navigation', data['redirect_url'])

        task.refresh_from_db()
        self.assertEqual(task.dl_task_status, 'out_for_delivery')

    def test_start_ride_not_assigned_to_me(self):
        task = self.create_delivery_task(
            self.order, self.business, self.pickup,
            status='assigned', task_number='RIDE-002')
        # No AssignedDriver record for this driver
        response = self.client.post(
            '/delivery/delivery_task/start_ride/',
            {'task_id': task.id})
        data = json.loads(response.content)
        self.assertFalse(data['success'])
        self.assertIn('not assigned', data['error'])

    def test_start_ride_no_task_id(self):
        response = self.client.post(
            '/delivery/delivery_task/start_ride/', {})
        data = json.loads(response.content)
        self.assertFalse(data['success'])

    def test_start_ride_get_method_rejected(self):
        response = self.client.get('/delivery/delivery_task/start_ride/')
        data = json.loads(response.content)
        self.assertFalse(data['success'])


class TaskNavigationViewTest(DriverTestMixin, TestCase):
    """Test task navigation view."""

    def setUp(self):
        self.client = Client()
        self.user, self.profile = self.create_driver_user()
        self.driver = self.create_driver(self.user, self.profile)
        self.client.login(username='testdriver', password='TestDriver@123')
        self.business, self.pickup, self.order = self.create_business_and_order(
            self.user, self.profile)

    def test_navigation_loads(self):
        task = self.create_delivery_task(
            self.order, self.business, self.pickup,
            driver=self.driver, status='in_transit', task_number='NAV-001')
        delivery_models.AssignedDriver.objects.create(
            driver=self.driver, dl_task=task)

        response = self.client.get(f'/delivery/task/{task.id}/navigation/')
        self.assertEqual(response.status_code, 200)
        self.assertIn('task', response.context)

    def test_navigation_not_assigned_redirects(self):
        task = self.create_delivery_task(
            self.order, self.business, self.pickup,
            status='in_transit', task_number='NAV-002')
        # No assignment
        response = self.client.get(f'/delivery/task/{task.id}/navigation/')
        self.assertIn(response.status_code, [301, 302])

    def test_navigation_nonexistent_task(self):
        response = self.client.get('/delivery/task/99999/navigation/')
        self.assertIn(response.status_code, [301, 302])


# =============================================================================
# DELIVERY COMPLETION & WALLET INTEGRATION TEST
# =============================================================================

class DeliveryCompletionWalletTest(DriverTestMixin, TransactionTestCase):
    """Test the full delivery completion → wallet update workflow."""

    def setUp(self):
        self.user, self.profile = self.create_driver_user()
        self.driver = self.create_driver(self.user, self.profile,
                                         wallet_balance=Decimal('5000.00'))
        self.business, self.pickup, self.order = self.create_business_and_order(
            self.user, self.profile)

    def test_process_delivery_completion_basic(self):
        task = self.create_delivery_task(
            self.order, self.business, self.pickup,
            driver=self.driver, status='delivered',
            task_number='COMP-001', dl_price=100)

        result = WalletService.process_delivery_completion(task, self.user)
        self.assertEqual(result['status'], 'success')
        self.assertEqual(result['driver_earnings'], Decimal('80.00'))  # 80%
        self.assertEqual(result['company_commission'], Decimal('20.00'))  # 20%

        self.driver.refresh_from_db()
        self.assertEqual(self.driver.pending_earnings, Decimal('80.00'))
        self.assertEqual(self.driver.total_earnings, Decimal('80.00'))

    def test_process_delivery_completion_already_processed(self):
        task = self.create_delivery_task(
            self.order, self.business, self.pickup,
            driver=self.driver, status='delivered',
            task_number='COMP-002', dl_price=100,
            earnings_processed=True)

        result = WalletService.process_delivery_completion(task, self.user)
        self.assertEqual(result['status'], 'error')

    def test_process_delivery_completion_no_driver(self):
        task = self.create_delivery_task(
            self.order, self.business, self.pickup,
            driver=None, status='delivered',
            task_number='COMP-003', dl_price=100)

        result = WalletService.process_delivery_completion(task, self.user)
        self.assertEqual(result['status'], 'error')


# =============================================================================
# EDGE CASE TESTS
# =============================================================================

class EdgeCaseTests(DriverTestMixin, TestCase):
    """Test edge cases and boundary conditions."""

    def setUp(self):
        self.client = Client()
        self.user, self.profile = self.create_driver_user()
        self.driver = self.create_driver(self.user, self.profile)
        self.client.login(username='testdriver', password='TestDriver@123')

    def test_dashboard_with_zero_credit_limit(self):
        """Driver with zero credit limit shouldn't cause division errors."""
        self.driver.credit_limit = Decimal('0.00')
        self.driver.save()
        response = self.client.get('/fleet/dashboard/')
        self.assertEqual(response.status_code, 200)

    def test_performance_with_zero_deliveries(self):
        """Performance page with no deliveries shouldn't error."""
        response = self.client.get('/fleet/performance/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.context['performance_metrics']['completion_rate'], 0)

    def test_analytics_with_no_data(self):
        """Analytics page with no data shouldn't error."""
        response = self.client.get('/fleet/analytics/')
        self.assertEqual(response.status_code, 200)

    def test_earnings_with_invalid_days_param(self):
        """Invalid 'days' parameter should fall back to default (30 days)."""
        response = self.client.get('/fleet/earnings/?days=abc')
        self.assertEqual(response.status_code, 200)

    def test_transactions_with_invalid_days_param(self):
        """Invalid 'days' parameter should fall back to default (30 days)."""
        response = self.client.get('/fleet/transactions/?days=abc')
        self.assertEqual(response.status_code, 200)

    def test_multiple_drivers_isolation(self):
        """Each driver should only see their own data."""
        user2, profile2 = self.create_driver_user(
            username='driver2', email='driver2@test.com')
        driver2 = self.create_driver(user2, profile2,
                                     driver_id=1002, driver_code='DRV002')

        # Create documents for each driver
        fleet_models.DriverDocument.objects.create(
            driver=self.driver, document_type='QID', document_no='DOC-DRV1')
        fleet_models.DriverDocument.objects.create(
            driver=driver2, document_type='QID', document_no='DOC-DRV2')

        # Driver 1 should only see their docs
        response = self.client.get('/fleet/documents/')
        docs = response.context['documents']
        self.assertEqual(len(docs), 1)
        self.assertEqual(docs[0].document_no, 'DOC-DRV1')

        # Driver 2 should only see their docs
        self.client.login(username='driver2', password='TestDriver@123')
        response = self.client.get('/fleet/documents/')
        docs = response.context['documents']
        self.assertEqual(len(docs), 1)
        self.assertEqual(docs[0].document_no, 'DOC-DRV2')

    def test_vehicle_isolation(self):
        """Each driver should only see their own vehicles."""
        user2, profile2 = self.create_driver_user(
            username='driver3', email='driver3@test.com')
        driver2 = self.create_driver(user2, profile2,
                                     driver_id=1003, driver_code='DRV003')

        fleet_models.DriverVehicle.objects.create(
            driver=self.driver, vehicle_type='car', vehicle_no='QA-DRV1')
        fleet_models.DriverVehicle.objects.create(
            driver=driver2, vehicle_type='bike', vehicle_no='QA-DRV3')

        response = self.client.get('/fleet/vehicle_own/')
        vehicles = response.context['vehicles']
        self.assertEqual(len(vehicles), 1)
        self.assertEqual(vehicles[0].vehicle_no, 'QA-DRV1')


# =============================================================================
# CONTEXT PROCESSOR TESTS
# =============================================================================

class ContextProcessorTest(TestCase):
    """Test context processors handle missing request.user gracefully."""

    def test_get_cached_profile_no_user_attribute(self):
        """get_cached_profile should return None if request has no user attribute."""
        from core.context_processors import get_cached_profile
        from django.test import RequestFactory
        factory = RequestFactory()
        request = factory.get('/')
        # Remove user attribute if it exists
        if hasattr(request, 'user'):
            delattr(request, 'user')
        result = get_cached_profile(request)
        self.assertIsNone(result)

    def test_get_cached_business_no_user_attribute(self):
        """get_cached_business should return None if request has no user attribute."""
        from core.context_processors import get_cached_business
        from django.test import RequestFactory
        factory = RequestFactory()
        request = factory.get('/')
        if hasattr(request, 'user'):
            delattr(request, 'user')
        result = get_cached_business(request)
        self.assertIsNone(result)


# =============================================================================
# URL RESOLUTION TESTS
# =============================================================================

class FleetURLResolutionTest(TestCase):
    """Test that all fleet URLs resolve correctly."""

    def test_fleet_urls_resolve(self):
        urls = {
            'fleet:fleets': [],
            'fleet:fleet_dashboard': [],
            'fleet:driver_documents': [],
            'fleet:vehicle_own': [],
            'fleet:vehicle_add': [],
            'fleet:cod_collection': [],
            'fleet:cod_submission': [],
            'fleet:driver_earnings': [],
            'fleet:transaction_history': [],
            'fleet:driver_profile_mobile': [],
            'fleet:driver_performance': [],
            'fleet:driver_reports': [],
            'fleet:driver_analytics': [],
            'fleet:pickup_scanner': [],
            'fleet:pickup_scan_process': [],
        }
        for url_name, args in urls.items():
            try:
                url = reverse(url_name, args=args)
                self.assertIsNotNone(url, f"{url_name} should resolve")
            except Exception as e:
                self.fail(f"URL {url_name} failed to resolve: {e}")

    def test_fleet_urls_with_params(self):
        urls_with_params = {
            'fleet:driver_profile': [1001],
            'fleet:driver_documents_upload': [1],
            'fleet:driver_documents_update': [1, 1],
            'fleet:driver_documents_delete': [1, 1],
            'fleet:vehicle_update': [1],
            'fleet:vehicle_delete': [1, 1],
        }
        for url_name, args in urls_with_params.items():
            try:
                url = reverse(url_name, args=args)
                self.assertIsNotNone(url, f"{url_name} should resolve")
            except Exception as e:
                self.fail(f"URL {url_name} with args {args} failed: {e}")
