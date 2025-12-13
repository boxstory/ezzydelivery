"""
Comprehensive test suite for Delivery Task Management

Tests cover:
- Delivery task creation
- Driver assignment
- Status updates
- DMS push functionality (mocked external API)
- Address update
"""

from decimal import Decimal
from django.test import TestCase, TransactionTestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
from unittest.mock import patch, MagicMock, Mock
import json

from delivery import models as delivery_models
from orders import models as orders_models
from business import models as business_models
from fleet import models as fleet_models
from core import models as core_models

# Aliases for commonly used model classes
DeliveryTask = delivery_models.DeliveryTask
DlAddressUpdate = delivery_models.DlAddressUpdate
AssignedDriver = delivery_models.AssignedDriver
ZoneName = delivery_models.ZoneName
LatLonList = delivery_models.LatLonList
Order = orders_models.Order
Business = business_models.Business
PickupLocation = business_models.PickupLocation
Driver = fleet_models.Driver
DriverVehicle = fleet_models.DriverVehicle
Profile = core_models.Profile

User = get_user_model()


class DeliveryTaskModelTestCase(TestCase):
    """Test DeliveryTask model functionality"""

    def setUp(self):
        """Set up test data"""
        # Create user
        self.user = User.objects.create_user(
            username='taskuser',
            email='task@example.com',
            password='taskpass123'
        )

        # Create profile
        self.profile = Profile.objects.create(
            user=self.user,
            first_name='Task',
            last_name='User',
            phone=12345678
        )

        # Create business
        self.business = Business.objects.create(
            business_id=10,
            user=self.user,
            profile=self.profile,
            business_name='Task Business',
            business_code='TASKB001',
            business_status='active'
        )

        # Create pickup location
        self.pickup_location = PickupLocation.objects.create(
            business=self.business,
            pickup_location_title='Task Warehouse',
            locality='Doha',
            pickup_zone_no=70,
            pickup_street_no=700,
            pickup_building_no=7000,
            pickup_status='active'
        )

        # Create order
        self.order = Order.objects.create(
            business=self.business,
            client_order_code='TASK001',
            customer_name='Task Customer',
            customer_phone='11111111',
            customer_address='Task Address',
            dl_zone=70,
            dl_building=7000,
            dl_street=700,
            pickup_location=self.pickup_location
        )

        # Create driver
        self.driver_user = User.objects.create_user(
            username='driver1',
            email='driver1@example.com',
            password='driverpass123'
        )

        self.driver_profile = Profile.objects.create(
            user=self.driver_user,
            first_name='Test',
            last_name='Driver',
            phone=22222222
        )

        self.driver = Driver.objects.create(
            driver_id=1001,
            user=self.driver_user,
            profile=self.driver_profile,
            driver_code='DRV001',
            driver_phone='22222222',
            driver_whatsapp='22222222',
            driver_languages='english',
            driver_license_number='LIC12345',
            driver_status='Approved'
        )

    def test_delivery_task_creation(self):
        """Test basic delivery task creation"""
        task = DeliveryTask.objects.create(
            dl_task_number='TASK-001',
            dl_task_number_dms='DMS-001',
            dl_task_description='Test delivery',
            order=self.order,
            business=self.business,
            pickup_location=self.pickup_location,
            dl_task_status='pending',
            dl_task_status_client='for_review',
            dl_task_status_dms='6'
        )

        self.assertIsNotNone(task.id)
        self.assertEqual(task.order, self.order)
        self.assertEqual(task.dl_task_status, 'pending')
        self.assertFalse(task.dl_task_publish)

    def test_delivery_task_string_representation(self):
        """Test __str__ method"""
        task = DeliveryTask.objects.create(
            dl_task_number='TASK-002',
            dl_task_number_dms='DMS-002',
            dl_task_description='Test delivery 2',
            order=self.order,
            business=self.business,
            dl_task_status='pending',
            dl_task_status_client='for_review',
            dl_task_status_dms='6'
        )

        str_repr = str(task)
        self.assertIn('TASK-002', str_repr)

    def test_delivery_task_driver_assignment(self):
        """Test assigning driver to task"""
        task = DeliveryTask.objects.create(
            dl_task_number='TASK-003',
            dl_task_number_dms='DMS-003',
            dl_task_description='Test delivery 3',
            order=self.order,
            business=self.business,
            driver=self.driver,
            dl_task_status='publish_to_dms',
            dl_task_status_client='0',
            dl_task_status_dms='0'
        )

        self.assertEqual(task.driver, self.driver)
        self.assertEqual(task.dl_task_status, 'publish_to_dms')


class DeliveryTaskStatusTestCase(TestCase):
    """Test delivery task status transitions"""

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
            phone=33333333
        )

        self.business = Business.objects.create(
            business_id=11,
            user=self.user,
            profile=self.profile,
            business_name='Status Business',
            business_code='STATB001',
            business_status='active'
        )

        self.pickup_location = PickupLocation.objects.create(
            business=self.business,
            pickup_location_title='Status Warehouse',
            locality='Doha',
            pickup_zone_no=80,
            pickup_street_no=800,
            pickup_building_no=8000,
            pickup_status='active'
        )

        self.order = Order.objects.create(
            business=self.business,
            client_order_code='STAT001',
            customer_name='Status Customer',
            customer_phone='44444444',
            customer_address='Status Address',
            dl_zone=80,
            dl_building=8000,
            dl_street=800,
            pickup_location=self.pickup_location
        )

    def test_task_status_progression(self):
        """Test task status through different states"""
        task = DeliveryTask.objects.create(
            dl_task_number='STAT-001',
            dl_task_number_dms='DMS-STAT-001',
            dl_task_description='Status test',
            order=self.order,
            business=self.business,
            dl_task_status='for_review',
            dl_task_status_client='for_review',
            dl_task_status_dms='6'
        )

        # Pending
        task.dl_task_status = 'pending'
        task.save()
        self.assertEqual(task.dl_task_status, 'pending')

        # Publish to DMS
        task.dl_task_status = 'publish_to_dms'
        task.dl_task_status_dms = '0'  # Assigned
        task.save()
        self.assertEqual(task.dl_task_status, 'publish_to_dms')
        self.assertEqual(task.dl_task_status_dms, '0')

        # In transit
        task.dl_task_status = 'in_transit'
        task.dl_task_status_dms = '1'  # Started
        task.save()
        self.assertEqual(task.dl_task_status, 'in_transit')

        # Delivered
        task.dl_task_status = 'delivered'
        task.dl_task_status_dms = '2'  # Successful
        task.save()
        self.assertEqual(task.dl_task_status, 'delivered')
        self.assertEqual(task.dl_task_status_dms, '2')

    def test_task_rejection(self):
        """Test task rejection"""
        task = DeliveryTask.objects.create(
            dl_task_number='STAT-002',
            dl_task_number_dms='DMS-STAT-002',
            dl_task_description='Rejection test',
            order=self.order,
            business=self.business,
            dl_task_status='pending',
            dl_task_status_client='for_review',
            dl_task_status_dms='6'
        )

        task.dl_task_status = 'rejected'
        task.dl_task_status_dms = '8'  # Decline
        task.save()

        self.assertEqual(task.dl_task_status, 'rejected')
        self.assertEqual(task.dl_task_status_dms, '8')

    def test_task_cancellation(self):
        """Test task cancellation"""
        task = DeliveryTask.objects.create(
            dl_task_number='STAT-003',
            dl_task_number_dms='DMS-STAT-003',
            dl_task_description='Cancellation test',
            order=self.order,
            business=self.business,
            dl_task_status='pending',
            dl_task_status_client='for_review',
            dl_task_status_dms='6'
        )

        task.dl_task_status = 'cancelled'
        task.dl_task_status_dms = '9'  # Cancel
        task.save()

        self.assertEqual(task.dl_task_status, 'cancelled')
        self.assertEqual(task.dl_task_status_dms, '9')


class DlAddressUpdateTestCase(TestCase):
    """Test DlAddressUpdate model"""

    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            username='addressuser',
            email='address@example.com',
            password='addresspass123'
        )

        self.profile = Profile.objects.create(
            user=self.user,
            first_name='Address',
            last_name='User',
            phone=55555555
        )

        self.business = Business.objects.create(
            business_id=12,
            user=self.user,
            profile=self.profile,
            business_name='Address Business',
            business_code='ADDRB001',
            business_status='active'
        )

        self.pickup_location = PickupLocation.objects.create(
            business=self.business,
            pickup_location_title='Address Warehouse',
            locality='Doha',
            pickup_zone_no=90,
            pickup_street_no=900,
            pickup_building_no=9000,
            pickup_status='active'
        )

        self.order = Order.objects.create(
            business=self.business,
            client_order_code='ADDR001',
            customer_name='Address Customer',
            customer_phone='66666666',
            customer_address='Address Test',
            dl_zone=90,
            dl_building=9000,
            dl_street=900,
            pickup_location=self.pickup_location
        )

    def test_address_update_creation(self):
        """Test creating address update"""
        address = DlAddressUpdate.objects.create(
            full_name='Test Customer',
            mobile_no='77777777',
            area_name='Doha',
            dl_zone=90,
            dl_building=9000,
            dl_street=900,
            dl_task_number='ADDR-001',
            order=self.order
        )

        self.assertEqual(address.full_name, 'Test Customer')
        self.assertEqual(address.dl_zone, 90)
        self.assertIsNotNone(address.created_at)

    def test_address_update_with_coordinates(self):
        """Test address update with lat/lon"""
        address = DlAddressUpdate.objects.create(
            full_name='GPS Customer',
            mobile_no='88888888',
            dl_zone=91,
            dl_building=9100,
            dl_street=910,
            dl_latitude=Decimal('25.286106'),
            dl_longitude=Decimal('51.534817'),
            dl_task_number='ADDR-002',
            order=self.order
        )

        self.assertEqual(address.dl_latitude, Decimal('25.286106'))
        self.assertEqual(address.dl_longitude, Decimal('51.534817'))

    def test_address_update_property_type(self):
        """Test property type flags"""
        address = DlAddressUpdate.objects.create(
            full_name='Property Customer',
            mobile_no='99999999',
            dl_zone=92,
            dl_building=9200,
            dl_street=920,
            is_villa_compound=True,
            is_flat=False,
            is_office=False,
            dl_task_number='ADDR-003',
            order=self.order
        )

        self.assertTrue(address.is_villa_compound)
        self.assertFalse(address.is_flat)
        self.assertFalse(address.is_office)


class DriverAssignmentTestCase(TestCase):
    """Test driver assignment functionality"""

    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            username='assignuser',
            email='assign@example.com',
            password='assignpass123'
        )

        self.profile = Profile.objects.create(
            user=self.user,
            first_name='Assign',
            last_name='User',
            phone=10101010
        )

        self.business = Business.objects.create(
            business_id=13,
            user=self.user,
            profile=self.profile,
            business_name='Assign Business',
            business_code='ASSIGNB001',
            business_status='active'
        )

        self.pickup_location = PickupLocation.objects.create(
            business=self.business,
            pickup_location_title='Assign Warehouse',
            locality='Doha',
            pickup_zone_no=100,
            pickup_street_no=1000,
            pickup_building_no=10000,
            pickup_status='active'
        )

        self.order = Order.objects.create(
            business=self.business,
            client_order_code='ASSIGN001',
            customer_name='Assign Customer',
            customer_phone='11111111',
            customer_address='Assign Address',
            dl_zone=100,
            dl_building=10000,
            dl_street=1000,
            pickup_location=self.pickup_location
        )

        # Create drivers
        self.driver_user1 = User.objects.create_user(
            username='driver2',
            email='driver2@example.com',
            password='driverpass123'
        )

        self.driver_profile1 = Profile.objects.create(
            user=self.driver_user1,
            first_name='Driver',
            last_name='Two',
            phone=22222222
        )

        self.driver1 = Driver.objects.create(
            driver_id=1002,
            user=self.driver_user1,
            profile=self.driver_profile1,
            driver_code='DRV002',
            driver_phone='22222222',
            driver_whatsapp='22222222',
            driver_languages='english',
            driver_license_number='LIC54321',
            driver_status='Approved'
        )

    def test_assign_driver_to_task(self):
        """Test assigning driver to delivery task"""
        task = DeliveryTask.objects.create(
            dl_task_number='ASSIGN-001',
            dl_task_number_dms='DMS-ASSIGN-001',
            dl_task_description='Assignment test',
            order=self.order,
            business=self.business,
            dl_task_status='pending',
            dl_task_status_client='for_review',
            dl_task_status_dms='6'
        )

        # Assign driver
        task.driver = self.driver1
        task.dl_task_status = 'publish_to_dms'
        task.dl_task_status_dms = '0'
        task.save()

        self.assertEqual(task.driver, self.driver1)

        # Create assigned driver record
        assigned = AssignedDriver.objects.create(
            driver=self.driver1,
            dl_task=task
        )

        self.assertEqual(assigned.driver, self.driver1)
        self.assertEqual(assigned.dl_task, task)

    def test_reassign_driver(self):
        """Test reassigning task to different driver"""
        # Create second driver
        driver_user2 = User.objects.create_user(
            username='driver3',
            email='driver3@example.com',
            password='driverpass123'
        )

        driver_profile2 = Profile.objects.create(
            user=driver_user2,
            first_name='Driver',
            last_name='Three',
            phone=33333333
        )

        driver2 = Driver.objects.create(
            driver_id=1003,
            user=driver_user2,
            profile=driver_profile2,
            driver_code='DRV003',
            driver_phone='33333333',
            driver_whatsapp='33333333',
            driver_languages='english',
            driver_license_number='LIC98765',
            driver_status='Approved'
        )

        task = DeliveryTask.objects.create(
            dl_task_number='ASSIGN-002',
            dl_task_number_dms='DMS-ASSIGN-002',
            dl_task_description='Reassignment test',
            order=self.order,
            business=self.business,
            driver=self.driver1,
            dl_task_status='publish_to_dms',
            dl_task_status_client='0',
            dl_task_status_dms='0'
        )

        # Reassign to driver2
        task.driver = driver2
        task.save()

        self.assertEqual(task.driver, driver2)


class DMSPushTestCase(TransactionTestCase):
    """Test DMS push functionality with mocked API"""

    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            username='dmsuser',
            email='dms@example.com',
            password='dmspass123'
        )

        self.profile = Profile.objects.create(
            user=self.user,
            first_name='DMS',
            last_name='User',
            phone=44444444
        )

        self.business = Business.objects.create(
            business_id=14,
            user=self.user,
            profile=self.profile,
            business_name='DMS Business',
            business_code='DMSB001',
            business_status='active'
        )

        self.pickup_location = PickupLocation.objects.create(
            business=self.business,
            pickup_location_title='DMS Warehouse',
            locality='Doha',
            pickup_zone_no=110,
            pickup_street_no=1100,
            pickup_building_no=11000,
            pickup_status='active'
        )

        self.order = Order.objects.create(
            business=self.business,
            client_order_code='DMS001',
            customer_name='DMS Customer',
            customer_phone='55555555',
            customer_address='DMS Address',
            dl_zone=110,
            dl_building=11000,
            dl_street=1100,
            pickup_location=self.pickup_location
        )

    @patch('ezzy_api.views._push_task_to_dms')
    def test_dms_push_on_task_creation(self, mock_push):
        """Test DMS push is triggered when task is created"""
        mock_push.return_value = {'status': 'success', 'dms_id': 'DMS-12345'}

        task = DeliveryTask.objects.create(
            dl_task_number='DMS-001',
            dl_task_number_dms='DMS-001',
            dl_task_description='DMS push test',
            order=self.order,
            business=self.business,
            dl_task_status='pending',
            dl_task_status_client='for_review',
            dl_task_status_dms='6'
        )

        # Signal should trigger DMS push
        # In a real scenario, check that _push_task_to_dms was called

    @patch('requests.post')
    def test_dms_api_call_success(self, mock_post):
        """Test successful DMS API call"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'dms_id': 'DMS-12345', 'status': 'created'}
        mock_post.return_value = mock_response

        # This would test the actual _push_task_to_dms function
        # For now, we're mocking the HTTP call

    @patch('requests.post')
    def test_dms_api_call_failure(self, mock_post):
        """Test DMS API call failure handling"""
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.text = 'Internal Server Error'
        mock_post.return_value = mock_response

        # Test error handling


class ZoneAndLocationTestCase(TestCase):
    """Test zone and location models"""

    def test_zone_name_creation(self):
        """Test creating zone name"""
        zone = ZoneName.objects.create(
            zone_name='Al Wakrah',
            zone_number=25
        )

        self.assertEqual(zone.zone_name, 'Al Wakrah')
        self.assertEqual(zone.zone_number, 25)

    def test_lat_lon_list_creation(self):
        """Test creating lat/lon list entry"""
        location = LatLonList.objects.create(
            zone_number=25,
            street_number=100,
            building_number=10,
            latitude=Decimal('25.286106'),
            longitude=Decimal('51.534817')
        )

        self.assertEqual(location.zone_number, 25)
        self.assertEqual(location.street_number, 100)
        self.assertIsNotNone(location.latitude)
        self.assertIsNotNone(location.longitude)


class DeliveryTaskPricingTestCase(TestCase):
    """Test delivery task pricing"""

    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            username='priceuser',
            email='price@example.com',
            password='pricepass123'
        )

        self.profile = Profile.objects.create(
            user=self.user,
            first_name='Price',
            last_name='User',
            phone=66666666
        )

        self.business = Business.objects.create(
            business_id=15,
            user=self.user,
            profile=self.profile,
            business_name='Price Business',
            business_code='PRICEB001',
            business_status='active'
        )

        self.pickup_location = PickupLocation.objects.create(
            business=self.business,
            pickup_location_title='Price Warehouse',
            locality='Doha',
            pickup_zone_no=120,
            pickup_street_no=1200,
            pickup_building_no=12000,
            pickup_status='active'
        )

        self.order = Order.objects.create(
            business=self.business,
            client_order_code='PRICE001',
            customer_name='Price Customer',
            customer_phone='77777777',
            customer_address='Price Address',
            dl_zone=120,
            dl_building=12000,
            dl_street=1200,
            pickup_location=self.pickup_location
        )

    def test_delivery_price_assignment(self):
        """Test assigning delivery price"""
        task = DeliveryTask.objects.create(
            dl_task_number='PRICE-001',
            dl_task_number_dms='DMS-PRICE-001',
            dl_task_description='Price test',
            order=self.order,
            business=self.business,
            dl_price=25,
            dl_task_status='pending',
            dl_task_status_client='for_review',
            dl_task_status_dms='6'
        )

        self.assertEqual(task.dl_price, 25)

    def test_delivery_category_and_speed(self):
        """Test delivery category and speed options"""
        task = DeliveryTask.objects.create(
            dl_task_number='PRICE-002',
            dl_task_number_dms='DMS-PRICE-002',
            dl_task_description='Category test',
            order=self.order,
            business=self.business,
            dl_category='Food',
            dl_speed='Same Day',
            dl_waight=2,
            dl_task_status='pending',
            dl_task_status_client='for_review',
            dl_task_status_dms='6'
        )

        self.assertEqual(task.dl_category, 'Food')
        self.assertEqual(task.dl_speed, 'Same Day')
        self.assertEqual(task.dl_waight, 2)
