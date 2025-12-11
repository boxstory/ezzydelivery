"""
Comprehensive test suite for Business Management

Tests cover:
- Business profile management
- API settings validation
- Pickup location management
- Team member management
"""

from decimal import Decimal
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone

from business.models import (
    Business, BusinessProfile, BusinessApiSettings, BusinessLogo,
    BusinessTeamProfile, PickupLocation, DriverDirectory, BusinessSocialInfo
)
from core.models import Profile

User = get_user_model()


class BusinessModelTestCase(TestCase):
    """Test Business model functionality"""

    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            username='businessuser',
            email='business@example.com',
            password='businesspass123'
        )

        self.profile = Profile.objects.create(
            user=self.user,
            first_name='Business',
            last_name='Owner',
            phone=12345678
        )

    def test_business_creation(self):
        """Test basic business creation"""
        business = Business.objects.create(
            business_id=100,
            user=self.user,
            profile=self.profile,
            business_name='Test Business',
            business_code='TB100',
            business_phone='12345678',
            business_email='test@business.com',
            business_status='active'
        )

        self.assertIsNotNone(business.business_id)
        self.assertEqual(business.business_name, 'Test Business')
        self.assertEqual(business.business_status, 'active')

    def test_business_status_transitions(self):
        """Test business status changes"""
        business = Business.objects.create(
            business_id=101,
            user=self.user,
            profile=self.profile,
            business_name='Status Test Business',
            business_code='TB101',
            business_status='pending'
        )

        self.assertEqual(business.business_status, 'pending')

        # Activate business
        business.business_status = 'active'
        business.save()
        self.assertEqual(business.business_status, 'active')

        # Suspend business
        business.business_status = 'suspended'
        business.save()
        self.assertEqual(business.business_status, 'suspended')

    def test_business_string_representation(self):
        """Test __str__ method"""
        business = Business.objects.create(
            business_id=102,
            user=self.user,
            profile=self.profile,
            business_name='String Test Business',
            business_code='TB102',
            business_status='active'
        )

        str_repr = str(business)
        self.assertIn('String Test Business', str_repr)


class BusinessApiSettingsTestCase(TestCase):
    """Test BusinessApiSettings model"""

    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            username='apiuser',
            email='api@example.com',
            password='apipass123'
        )

        self.profile = Profile.objects.create(
            user=self.user,
            first_name='API',
            last_name='User',
            phone=87654321
        )

        self.business = Business.objects.create(
            business_id=200,
            user=self.user,
            profile=self.profile,
            business_name='API Test Business',
            business_code='TB200',
            business_status='active'
        )

    def test_api_settings_creation(self):
        """Test creating API settings"""
        api_settings = BusinessApiSettings.objects.create(
            business=self.business,
            api_type='shopify',
            api_key='test_api_key_123',
            api_secret='test_secret_456',
            site_api_url='https://test-store.myshopify.com',
            is_verify_api=True,
            is_default=True
        )

        self.assertEqual(api_settings.api_type, 'shopify')
        self.assertTrue(api_settings.is_verify_api)
        self.assertTrue(api_settings.is_default)

    def test_shopify_api_validation(self):
        """Test Shopify API settings validation"""
        api_settings = BusinessApiSettings.objects.create(
            business=self.business,
            api_type='shopify',
            api_key='shopify_key',
            api_secret='shopify_secret',
            site_api_url='https://mystore.myshopify.com',
            api_version='2023-10'
        )

        self.assertEqual(api_settings.api_type, 'shopify')
        self.assertIsNotNone(api_settings.api_version)

    def test_woocommerce_api_validation(self):
        """Test WooCommerce API settings validation"""
        api_settings = BusinessApiSettings.objects.create(
            business=self.business,
            api_type='woocommerce',
            api_key='wc_consumer_key',
            api_secret='wc_consumer_secret',
            site_api_url='https://example.com'
        )

        self.assertEqual(api_settings.api_type, 'woocommerce')

    def test_multiple_api_settings(self):
        """Test multiple API settings for one business"""
        # Shopify settings
        shopify_settings = BusinessApiSettings.objects.create(
            business=self.business,
            api_type='shopify',
            api_key='shopify_key',
            api_secret='shopify_secret',
            site_api_url='https://store.myshopify.com',
            is_default=True
        )

        # WooCommerce settings
        woo_settings = BusinessApiSettings.objects.create(
            business=self.business,
            api_type='woocommerce',
            api_key='woo_key',
            api_secret='woo_secret',
            site_api_url='https://woostore.com',
            is_default=False
        )

        api_count = BusinessApiSettings.objects.filter(business=self.business).count()
        self.assertEqual(api_count, 2)


class PickupLocationTestCase(TestCase):
    """Test PickupLocation model"""

    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            username='pickupuser',
            email='pickup@example.com',
            password='pickuppass123'
        )

        self.profile = Profile.objects.create(
            user=self.user,
            first_name='Pickup',
            last_name='User',
            phone=11223344
        )

        self.business = Business.objects.create(
            business_id=300,
            user=self.user,
            profile=self.profile,
            business_name='Pickup Test Business',
            business_code='TB300',
            business_status='active'
        )

    def test_pickup_location_creation(self):
        """Test creating pickup location"""
        pickup = PickupLocation.objects.create(
            business=self.business,
            pickup_location_title='Main Warehouse',
            locality='Doha',
            pickup_zone_no=1,
            pickup_street_no=100,
            pickup_building_no=10,
            pickup_status='active'
        )

        self.assertEqual(pickup.pickup_location_title, 'Main Warehouse')
        self.assertEqual(pickup.pickup_status, 'active')

    def test_pickup_location_with_coordinates(self):
        """Test pickup location with GPS coordinates"""
        pickup = PickupLocation.objects.create(
            business=self.business,
            pickup_location_title='GPS Warehouse',
            locality='Al Wakrah',
            pickup_zone_no=2,
            pickup_street_no=200,
            pickup_building_no=20,
            pickup_lat=Decimal('25.286106'),
            pickup_lon=Decimal('51.534817'),
            pickup_status='active'
        )

        self.assertIsNotNone(pickup.pickup_lat)
        self.assertIsNotNone(pickup.pickup_lon)

    def test_multiple_pickup_locations(self):
        """Test business with multiple pickup locations"""
        # Create multiple pickups
        pickup1 = PickupLocation.objects.create(
            business=self.business,
            pickup_location_title='Warehouse 1',
            locality='Doha',
            pickup_zone_no=10,
            pickup_street_no=1000,
            pickup_building_no=100,
            pickup_status='active'
        )

        pickup2 = PickupLocation.objects.create(
            business=self.business,
            pickup_location_title='Warehouse 2',
            locality='Al Rayyan',
            pickup_zone_no=20,
            pickup_street_no=2000,
            pickup_building_no=200,
            pickup_status='active'
        )

        pickup_count = PickupLocation.objects.filter(business=self.business).count()
        self.assertEqual(pickup_count, 2)

    def test_pickup_location_status_changes(self):
        """Test pickup location status transitions"""
        pickup = PickupLocation.objects.create(
            business=self.business,
            pickup_location_title='Status Test Warehouse',
            locality='Doha',
            pickup_zone_no=30,
            pickup_street_no=3000,
            pickup_building_no=300,
            pickup_status='active'
        )

        # Deactivate
        pickup.pickup_status = 'inactive'
        pickup.save()
        self.assertEqual(pickup.pickup_status, 'inactive')


class BusinessTeamProfileTestCase(TestCase):
    """Test BusinessTeamProfile model"""

    def setUp(self):
        """Set up test data"""
        self.owner = User.objects.create_user(
            username='owner',
            email='owner@example.com',
            password='ownerpass123'
        )

        self.owner_profile = Profile.objects.create(
            user=self.owner,
            first_name='Business',
            last_name='Owner',
            phone=55555555
        )

        self.business = Business.objects.create(
            business_id=400,
            user=self.owner,
            profile=self.owner_profile,
            business_name='Team Test Business',
            business_code='TB400',
            business_status='active'
        )

        # Create team member user
        self.team_user = User.objects.create_user(
            username='teammember',
            email='team@example.com',
            password='teampass123'
        )

        self.team_profile = Profile.objects.create(
            user=self.team_user,
            first_name='Team',
            last_name='Member',
            phone=66666666
        )

    def test_team_member_creation(self):
        """Test creating team member"""
        team_member = BusinessTeamProfile.objects.create(
            user=self.team_user,
            profile=self.team_profile,
            business=self.business,
            team_code='TM001',
            team_role='Manager',
            team_name='John Manager',
            team_phone='66666666',
            team_email='team@example.com',
            team_status='active'
        )

        self.assertEqual(team_member.team_role, 'Manager')
        self.assertEqual(team_member.team_status, 'active')

    def test_team_member_role_assignment(self):
        """Test assigning different roles"""
        roles = ['Manager', 'Staff', 'Supervisor', 'Admin']

        for i, role in enumerate(roles):
            user = User.objects.create_user(
                username=f'team{i}',
                email=f'team{i}@example.com',
                password='pass123'
            )
            profile = Profile.objects.create(
                user=user,
                first_name='Team',
                last_name=f'{i}',
                phone=77777770 + i
            )
            team = BusinessTeamProfile.objects.create(
                user=user,
                profile=profile,
                business=self.business,
                team_code=f'TM00{i}',
                team_role=role,
                team_status='active'
            )
            self.assertEqual(team.team_role, role)

    def test_team_status_transitions(self):
        """Test team member status changes"""
        team_member = BusinessTeamProfile.objects.create(
            user=self.team_user,
            profile=self.team_profile,
            business=self.business,
            team_code='TM002',
            team_status='aproval pending'
        )

        # Approve
        team_member.team_status = 'active'
        team_member.save()
        self.assertEqual(team_member.team_status, 'active')

        # Suspend
        team_member.team_status = 'suspended'
        team_member.save()
        self.assertEqual(team_member.team_status, 'suspended')


class BusinessProfileTestCase(TestCase):
    """Test BusinessProfile model"""

    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            username='profileuser',
            email='profile@example.com',
            password='profilepass123'
        )

        self.profile = Profile.objects.create(
            user=self.user,
            first_name='Profile',
            last_name='User',
            phone=88888888
        )

        self.business = Business.objects.create(
            business_id=500,
            user=self.user,
            profile=self.profile,
            business_name='Profile Test Business',
            business_code='TB500',
            business_status='active'
        )

    def test_business_profile_creation(self):
        """Test creating business profile"""
        business_profile = BusinessProfile.objects.create(
            business=self.business,
            business_description='A test business profile',
            business_address='123 Test Street',
            business_city='Doha',
            business_country='Qatar',
            business_email='contact@test.com',
            business_phone='99999999'
        )

        self.assertEqual(business_profile.business, self.business)
        self.assertIsNotNone(business_profile.business_description)
