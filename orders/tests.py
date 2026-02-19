"""
Comprehensive test suite for Order Management

Tests cover:
- Order creation
- Order verification workflow
- Address verification
- Order status transitions
- Signal testing (automatic delivery task creation)
- Order proof storage (original_order_data)
"""

from decimal import Decimal
from django.test import TestCase, TransactionTestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
from unittest.mock import patch, MagicMock
import json

from orders import models as orders_models
from delivery import models as delivery_models
from business import models as business_models
from product import models as product_models
from core import models as core_models

# Aliases for commonly used model classes
Order = orders_models.Order
OrderItem = orders_models.OrderItem
OrderBarcode = orders_models.OrderBarcode
OrderComments = orders_models.OrderComments
OrderVerificationLog = orders_models.OrderVerificationLog
AddressVerification = orders_models.AddressVerification
DeliveryTask = delivery_models.DeliveryTask
DlAddressUpdate = delivery_models.DlAddressUpdate
Business = business_models.Business
PickupLocation = business_models.PickupLocation
BusinessApiSettings = business_models.BusinessApiSettings
Product = product_models.Product
Profile = core_models.Profile

User = get_user_model()


class OrderModelTestCase(TestCase):
    """Test Order model functionality"""

    def setUp(self):
        """Set up test data"""
        # Create user
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )

        # Create profile
        self.profile = Profile.objects.create(
            user=self.user,
            first_name='Test',
            last_name='User',
            phone=12345678
        )

        # Create business
        self.business = Business.objects.create(
            business_id=1,
            user=self.user,
            profile=self.profile,
            business_name='Test Business',
            business_code='TB001',
            business_status='active'
        )

        # Create pickup location
        self.pickup_location = PickupLocation.objects.create(
            business=self.business,
            pickup_location_title='Main Warehouse',
            locality='Doha',
            pickup_zone_no=1,
            pickup_street_no=100,
            pickup_building_no=10,
            pickup_status='active'
        )

    def test_order_creation(self):
        """Test basic order creation"""
        order = Order.objects.create(
            business=self.business,
            client_order_code='TEST001',
            customer_name='John Doe',
            customer_phone='12345678',
            customer_address='Test Address',
            dl_zone=1,
            dl_building=100,
            dl_street=10,
            cod_amount=100,
            cod_status_by_client='pending',
            pickup_location=self.pickup_location
        )

        self.assertIsNotNone(order.id)
        self.assertIsNotNone(order.order_number)
        self.assertEqual(order.business, self.business)
        self.assertEqual(order.customer_name, 'John Doe')
        self.assertEqual(order.order_status, 'to_review')
        self.assertEqual(order.task_status, 'new_order')
        self.assertFalse(order.task_created)

    def test_order_number_generation(self):
        """Test automatic order number generation"""
        order = Order.objects.create(
            business=self.business,
            client_order_code='TEST002',
            customer_name='Jane Doe',
            customer_phone='87654321',
            customer_address='Test Address 2',
            dl_zone=2,
            dl_building=200,
            dl_street=20,
            pickup_location=self.pickup_location
        )

        self.assertIsNotNone(order.order_number)
        self.assertTrue(len(order.order_number) > 0)

    def test_order_original_data_storage(self):
        """Test that original order data is stored for proof"""
        order = Order.objects.create(
            business=self.business,
            client_order_code='TEST003',
            customer_name='Bob Smith',
            customer_phone='11111111',
            customer_address='Original Address',
            dl_zone=3,
            dl_building=300,
            dl_street=30,
            cod_amount=150,
            pickup_location=self.pickup_location
        )

        # Refresh from database to get signal-updated fields
        order.refresh_from_db()

        self.assertIsNotNone(order.original_order_data)
        self.assertIn('order_number', order.original_order_data)
        self.assertIn('customer_name', order.original_order_data)
        self.assertIn('customer_address', order.original_order_data)
        self.assertEqual(order.original_order_data['customer_name'], 'Bob Smith')
        self.assertEqual(order.original_order_data['cod_amount'], 150)

    def test_order_verification_status_default(self):
        """Test default verification status"""
        order = Order.objects.create(
            business=self.business,
            client_order_code='TEST004',
            customer_name='Alice Brown',
            customer_phone='22222222',
            customer_address='Test Address',
            dl_zone=4,
            dl_building=400,
            dl_street=40,
            pickup_location=self.pickup_location
        )

        self.assertEqual(order.verification_status, 'pending')
        self.assertFalse(order.address_verified)

    def test_order_string_representation(self):
        """Test __str__ method"""
        order = Order.objects.create(
            business=self.business,
            client_order_code='TEST005',
            customer_name='Test Customer',
            customer_phone='33333333',
            customer_address='Test Address',
            dl_zone=5,
            dl_building=500,
            dl_street=50,
            pickup_location=self.pickup_location
        )

        str_repr = str(order)
        self.assertIn(self.business.business_name, str_repr)
        self.assertIn(order.client_order_code, str_repr)


class OrderVerificationTestCase(TransactionTestCase):
    """Test order verification workflow"""

    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            username='verifier',
            email='verifier@example.com',
            password='verifypass123'
        )

        self.profile = Profile.objects.create(
            user=self.user,
            first_name='Verifier',
            last_name='User',
            phone=55555555
        )

        self.business = Business.objects.create(
            business_id=2,
            user=self.user,
            profile=self.profile,
            business_name='Verify Business',
            business_code='VB001',
            business_status='active'
        )

        self.pickup_location = PickupLocation.objects.create(
            business=self.business,
            pickup_location_title='Warehouse',
            locality='Doha',
            pickup_zone_no=10,
            pickup_street_no=100,
            pickup_building_no=1000,
            pickup_status='active'
        )

    def test_address_verification_creation(self):
        """Test address verification record creation"""
        order = Order.objects.create(
            business=self.business,
            client_order_code='VER001',
            customer_name='Verify Customer',
            customer_phone='44444444',
            customer_address='123 Test Street',
            dl_zone=10,
            dl_building=1000,
            dl_street=100,
            pickup_location=self.pickup_location
        )

        order.refresh_from_db()

        # Check that address verification was created by signal
        address_verification = AddressVerification.objects.filter(order=order).first()
        self.assertIsNotNone(address_verification)
        self.assertEqual(address_verification.original_address, '123 Test Street')
        self.assertEqual(address_verification.verification_result, 'pending')

    def test_address_verification_update(self):
        """Test updating address verification"""
        order = Order.objects.create(
            business=self.business,
            client_order_code='VER002',
            customer_name='Another Customer',
            customer_phone='55555555',
            customer_address='456 Old Street',
            dl_zone=11,
            dl_building=1100,
            dl_street=110,
            pickup_location=self.pickup_location
        )

        order.refresh_from_db()

        # Update address verification
        address_verification = AddressVerification.objects.filter(order=order).first()
        address_verification.verified_address = '456 New Street'
        address_verification.verification_result = 'valid'
        address_verification.verified_by = self.user
        address_verification.verified_at = timezone.now()
        address_verification.latitude = Decimal('25.286106')
        address_verification.longitude = Decimal('51.534817')
        address_verification.save()

        # Verify update
        self.assertEqual(address_verification.verification_result, 'valid')
        self.assertIsNotNone(address_verification.verified_at)
        self.assertEqual(address_verification.verified_by, self.user)

    def test_order_verification_status_change(self):
        """Test order verification status transitions"""
        order = Order.objects.create(
            business=self.business,
            client_order_code='VER003',
            customer_name='Status Test',
            customer_phone='66666666',
            customer_address='789 Status Street',
            dl_zone=12,
            dl_building=1200,
            dl_street=120,
            pickup_location=self.pickup_location
        )

        # Test address verified status
        order.verification_status = 'address_verified'
        order.address_verified = True
        order.address_verified_by = self.user
        order.address_verified_at = timezone.now()
        order.save()

        self.assertEqual(order.verification_status, 'address_verified')
        self.assertTrue(order.address_verified)

        # Test fully verified status
        order.verification_status = 'verified'
        order.verified_by = self.user
        order.verified_at = timezone.now()
        order.save()

        self.assertEqual(order.verification_status, 'verified')
        self.assertIsNotNone(order.verified_at)

    def test_order_rejection(self):
        """Test order rejection"""
        order = Order.objects.create(
            business=self.business,
            client_order_code='VER004',
            customer_name='Reject Test',
            customer_phone='77777777',
            customer_address='999 Reject Street',
            dl_zone=13,
            dl_building=1300,
            dl_street=130,
            pickup_location=self.pickup_location
        )

        order.verification_status = 'rejected'
        order.verified_by = self.user
        order.verified_at = timezone.now()
        order.verification_notes = 'Address not found'
        order.save()

        self.assertEqual(order.verification_status, 'rejected')
        self.assertIsNotNone(order.verification_notes)

    def test_verification_log_creation(self):
        """Test that verification logs are created"""
        order = Order.objects.create(
            business=self.business,
            client_order_code='VER005',
            customer_name='Log Test',
            customer_phone='88888888',
            customer_address='111 Log Street',
            dl_zone=14,
            dl_building=1400,
            dl_street=140,
            pickup_location=self.pickup_location
        )

        # Create verification log
        log = OrderVerificationLog.objects.create(
            order=order,
            verified_by=self.user,
            action='address_verified',
            notes='Address confirmed',
            old_status='pending',
            new_status='address_verified'
        )

        self.assertEqual(log.order, order)
        self.assertEqual(log.action, 'address_verified')
        self.assertEqual(log.new_status, 'address_verified')


class OrderStatusTransitionTestCase(TestCase):
    """Test order status transitions"""

    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            username='statususer',
            email='status@example.com',
            password='statuspass123'
        )

        self.profile = Profile.objects.create(
            user=self.user,
            first_name='Status',
            last_name='User',
            phone=99999999
        )

        self.business = Business.objects.create(
            business_id=3,
            user=self.user,
            profile=self.profile,
            business_name='Status Business',
            business_code='SB001',
            business_status='active'
        )

        self.pickup_location = PickupLocation.objects.create(
            business=self.business,
            pickup_location_title='Status Warehouse',
            locality='Doha',
            pickup_zone_no=20,
            pickup_street_no=200,
            pickup_building_no=2000,
            pickup_status='active'
        )

    def test_order_status_to_review_to_publish(self):
        """Test order status from to_review to publish"""
        order = Order.objects.create(
            business=self.business,
            client_order_code='STAT001',
            customer_name='Status Test 1',
            customer_phone='11111111',
            customer_address='Status Address',
            dl_zone=20,
            dl_building=2000,
            dl_street=200,
            pickup_location=self.pickup_location
        )

        self.assertEqual(order.order_status, 'to_review')

        # Change to ready to pickup
        order.order_status = 'ready_to_pickup'
        order.save()
        self.assertEqual(order.order_status, 'ready_to_pickup')

        # Change to publish
        order.order_status = 'publish'
        order.save()
        self.assertEqual(order.order_status, 'publish')

    def test_order_cancellation(self):
        """Test order cancellation"""
        order = Order.objects.create(
            business=self.business,
            client_order_code='STAT002',
            customer_name='Cancel Test',
            customer_phone='22222222',
            customer_address='Cancel Address',
            dl_zone=21,
            dl_building=2100,
            dl_street=210,
            pickup_location=self.pickup_location
        )

        order.order_status = 'cancelled'
        order.save()
        self.assertEqual(order.order_status, 'cancelled')

    def test_task_status_transitions(self):
        """Test task status transitions"""
        order = Order.objects.create(
            business=self.business,
            client_order_code='STAT003',
            customer_name='Task Status Test',
            customer_phone='33333333',
            customer_address='Task Address',
            dl_zone=22,
            dl_building=2200,
            dl_street=220,
            pickup_location=self.pickup_location
        )

        self.assertEqual(order.task_status, 'new_order')

        # Test status progression
        order.task_status = 'info_missing'
        order.save()
        self.assertEqual(order.task_status, 'info_missing')

        order.task_status = 'pending_for_confirm'
        order.save()
        self.assertEqual(order.task_status, 'pending_for_confirm')

        order.task_status = 'dl_task_listed'
        order.save()
        self.assertEqual(order.task_status, 'dl_task_listed')


class OrderSignalTestCase(TransactionTestCase):
    """Test order signals"""

    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            username='signaluser',
            email='signal@example.com',
            password='signalpass123'
        )

        self.profile = Profile.objects.create(
            user=self.user,
            first_name='Signal',
            last_name='User',
            phone=12121212
        )

        self.business = Business.objects.create(
            business_id=4,
            user=self.user,
            profile=self.profile,
            business_name='Signal Business',
            business_code='SIGB001',
            business_status='active'
        )

        self.pickup_location = PickupLocation.objects.create(
            business=self.business,
            pickup_location_title='Signal Warehouse',
            locality='Doha',
            pickup_zone_no=30,
            pickup_street_no=300,
            pickup_building_no=3000,
            pickup_status='active'
        )

    def test_order_creates_barcode(self):
        """Test that creating order creates barcode"""
        order = Order.objects.create(
            business=self.business,
            client_order_code='SIG001',
            customer_name='Barcode Test',
            customer_phone='44444444',
            customer_address='Barcode Address',
            dl_zone=30,
            dl_building=3000,
            dl_street=300,
            pickup_location=self.pickup_location
        )

        order.refresh_from_db()

        # Check barcode was created
        barcode = OrderBarcode.objects.filter(order=order).first()
        self.assertIsNotNone(barcode)
        self.assertEqual(barcode.order_number, order.order_number)

    def test_order_creates_address_update(self):
        """Test that creating order creates DlAddressUpdate"""
        order = Order.objects.create(
            business=self.business,
            client_order_code='SIG002',
            customer_name='Address Update Test',
            customer_phone='55555555',
            customer_address='Address Update',
            dl_zone=31,
            dl_building=3100,
            dl_street=310,
            pickup_location=self.pickup_location
        )

        order.refresh_from_db()

        # Check DlAddressUpdate was created
        address_update = DlAddressUpdate.objects.filter(order=order).first()
        self.assertIsNotNone(address_update)
        self.assertEqual(address_update.full_name, order.customer_name)
        self.assertEqual(address_update.mobile_no, order.customer_phone)

    @patch('orders.signals._create_delivery_task_from_order')
    def test_verified_order_creates_delivery_task(self, mock_create_task):
        """Test that verifying order triggers delivery task creation"""
        order = Order.objects.create(
            business=self.business,
            client_order_code='SIG003',
            customer_name='Delivery Task Test',
            customer_phone='66666666',
            customer_address='Task Address',
            dl_zone=32,
            dl_building=3200,
            dl_street=320,
            pickup_location=self.pickup_location
        )

        # Verify order
        order.verification_status = 'verified'
        order.save()

        # Check that task creation was called
        mock_create_task.assert_called_once_with(order)


class OrderItemTestCase(TestCase):
    """Test OrderItem model"""

    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            username='itemuser',
            email='item@example.com',
            password='itempass123'
        )

        self.profile = Profile.objects.create(
            user=self.user,
            first_name='Item',
            last_name='User',
            phone=13131313
        )

        self.business = Business.objects.create(
            business_id=5,
            user=self.user,
            profile=self.profile,
            business_name='Item Business',
            business_code='ITB001',
            business_status='active'
        )

        self.pickup_location = PickupLocation.objects.create(
            business=self.business,
            pickup_location_title='Item Warehouse',
            locality='Doha',
            pickup_zone_no=40,
            pickup_street_no=400,
            pickup_building_no=4000,
            pickup_status='active'
        )

        self.product = Product.objects.create(
            business=self.business,
            brand_name='Test Brand',
            item_name='Test Product',
            item_sku='TEST-SKU-001',
            item_price=50
        )

        self.order = Order.objects.create(
            business=self.business,
            client_order_code='ITEM001',
            customer_name='Item Test',
            customer_phone='77777777',
            customer_address='Item Address',
            dl_zone=40,
            dl_building=4000,
            dl_street=400,
            pickup_location=self.pickup_location
        )

    def test_order_item_creation(self):
        """Test creating order item"""
        item = OrderItem.objects.create(
            order=self.order,
            product=self.product,
            quantity=2,
            unit_price=Decimal('50.00')
        )

        self.assertEqual(item.order, self.order)
        self.assertEqual(item.product, self.product)
        self.assertEqual(item.quantity, 2)
        self.assertEqual(item.total_price, Decimal('100.00'))

    def test_order_item_total_price_calculation(self):
        """Test automatic total price calculation"""
        item = OrderItem.objects.create(
            order=self.order,
            product=self.product,
            quantity=3,
            unit_price=Decimal('25.50')
        )

        self.assertEqual(item.total_price, Decimal('76.50'))


class OrderCommentsTestCase(TestCase):
    """Test OrderComments model"""

    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            username='commentuser',
            email='comment@example.com',
            password='commentpass123'
        )

        self.profile = Profile.objects.create(
            user=self.user,
            first_name='Comment',
            last_name='User',
            phone=14141414
        )

        self.business = Business.objects.create(
            business_id=6,
            user=self.user,
            profile=self.profile,
            business_name='Comment Business',
            business_code='CB001',
            business_status='active'
        )

        self.pickup_location = PickupLocation.objects.create(
            business=self.business,
            pickup_location_title='Comment Warehouse',
            locality='Doha',
            pickup_zone_no=50,
            pickup_street_no=500,
            pickup_building_no=5000,
            pickup_status='active'
        )

        self.order = Order.objects.create(
            business=self.business,
            client_order_code='COM001',
            customer_name='Comment Test',
            customer_phone='88888888',
            customer_address='Comment Address',
            dl_zone=50,
            dl_building=5000,
            dl_street=500,
            pickup_location=self.pickup_location
        )

    def test_order_comment_creation(self):
        """Test creating order comment"""
        comment = OrderComments.objects.create(
            order=self.order,
            name='Test Commenter',
            body='This is a test comment'
        )

        self.assertEqual(comment.order, self.order)
        self.assertEqual(comment.body, 'This is a test comment')
        self.assertIsNotNone(comment.created_at)


class OrderCODTestCase(TestCase):
    """Test COD functionality"""

    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            username='coduser',
            email='cod@example.com',
            password='codpass123'
        )

        self.profile = Profile.objects.create(
            user=self.user,
            first_name='COD',
            last_name='User',
            phone=15151515
        )

        self.business = Business.objects.create(
            business_id=7,
            user=self.user,
            profile=self.profile,
            business_name='COD Business',
            business_code='CODB001',
            business_status='active'
        )

        self.pickup_location = PickupLocation.objects.create(
            business=self.business,
            pickup_location_title='COD Warehouse',
            locality='Doha',
            pickup_zone_no=60,
            pickup_street_no=600,
            pickup_building_no=6000,
            pickup_status='active'
        )

    def test_cod_order_creation(self):
        """Test creating order with COD"""
        order = Order.objects.create(
            business=self.business,
            client_order_code='COD001',
            customer_name='COD Test',
            customer_phone='99999999',
            customer_address='COD Address',
            dl_zone=60,
            dl_building=6000,
            dl_street=600,
            cod_amount=250,
            cod_status_by_client='pending',
            pickup_location=self.pickup_location
        )

        self.assertEqual(order.cod_amount, 250)
        self.assertEqual(order.cod_status_by_client, 'pending')

    def test_cod_status_transitions(self):
        """Test COD status transitions"""
        order = Order.objects.create(
            business=self.business,
            client_order_code='COD002',
            customer_name='COD Status Test',
            customer_phone='10101010',
            customer_address='COD Status Address',
            dl_zone=61,
            dl_building=6100,
            dl_street=610,
            cod_amount=150,
            cod_status_by_client='pending',
            pickup_location=self.pickup_location
        )

        # Test staff COD status updates
        order.cod_status_by_staff = 'cod_with_driver'
        order.save()
        self.assertEqual(order.cod_status_by_staff, 'cod_with_driver')

        order.cod_status_by_staff = 'cod_with_ezzy'
        order.save()
        self.assertEqual(order.cod_status_by_staff, 'cod_with_ezzy')

        order.cod_status_by_staff = 'cod_settled_with_business'
        order.save()
        self.assertEqual(order.cod_status_by_staff, 'cod_settled_with_business')
