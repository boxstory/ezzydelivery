"""
Management command to create dummy/test data for EzzyDelivery platform.
Uses real Qatar locations and realistic data.

Usage:
    python manage.py create_dummy_data

To clear the data after testing:
    python manage.py create_dummy_data --clear
"""

from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.utils import timezone
from django.db import transaction
from datetime import timedelta
from decimal import Decimal
import random
import string

# Import models
from core.models import Profile
from business.models import Business, BusinessProfile, PickupLocation
from warehouse.models import Warehouse, WarehouseLocation, SellerWarehouseLink, StorageLocation
from product.models import Product, ProductCategory, ProductInventory
from orders.models import Order, OrderItem
from delivery.models import DeliveryTask, DlAddressUpdate, ZoneName
from fleet.models import Driver, DriverVehicle


# Real Qatar Zone Data
QATAR_ZONES = [
    {'zone': 1, 'name': 'Al Jasra', 'lat': 25.2867, 'lon': 51.5333},
    {'zone': 18, 'name': 'Al Bidda', 'lat': 25.2833, 'lon': 51.5167},
    {'zone': 22, 'name': 'Al Doha Al Jadeeda', 'lat': 25.2819, 'lon': 51.5022},
    {'zone': 24, 'name': 'Fereej Abdel Aziz', 'lat': 25.2817, 'lon': 51.5117},
    {'zone': 25, 'name': 'Fereej Al Nasr', 'lat': 25.2764, 'lon': 51.5117},
    {'zone': 26, 'name': 'Fereej Bin Mahmoud North', 'lat': 25.2722, 'lon': 51.5056},
    {'zone': 31, 'name': 'Mushayrib', 'lat': 25.2833, 'lon': 51.5250},
    {'zone': 38, 'name': 'Al Mirqab Al Jadeed', 'lat': 25.2875, 'lon': 51.5083},
    {'zone': 39, 'name': 'Doha Port', 'lat': 25.2875, 'lon': 51.5333},
    {'zone': 41, 'name': 'Al Corniche', 'lat': 25.3000, 'lon': 51.5167},
    {'zone': 44, 'name': 'West Bay', 'lat': 25.3231, 'lon': 51.5311},
    {'zone': 45, 'name': 'Al Dafna', 'lat': 25.3167, 'lon': 51.5250},
    {'zone': 55, 'name': 'Fereej Al Soudan', 'lat': 25.2625, 'lon': 51.5042},
    {'zone': 60, 'name': 'Al Sadd', 'lat': 25.2708, 'lon': 51.4917},
    {'zone': 61, 'name': 'Al Mirqab', 'lat': 25.2833, 'lon': 51.5000},
    {'zone': 63, 'name': 'Madinat Khalifa North', 'lat': 25.3028, 'lon': 51.4833},
    {'zone': 65, 'name': 'Al Messila', 'lat': 25.3125, 'lon': 51.4667},
    {'zone': 66, 'name': 'New Al Hitmi', 'lat': 25.2944, 'lon': 51.4917},
    {'zone': 69, 'name': 'Al Hilal', 'lat': 25.2778, 'lon': 51.4708},
    {'zone': 70, 'name': 'Al Waab', 'lat': 25.2625, 'lon': 51.4583},
]

# Real Qatar business types and names
BUSINESS_DATA = {
    'name': 'Al Shams Electronics',
    'code': 'ALSHAM',
    'phone': '+97444123456',
    'email': 'info@alshamselectronics.qa',
    'whatsapp': '+97455123456',
    'address': 'Building 45, Street 810, Zone 44',
    'city': 'Doha',
    'description': 'Leading electronics retailer in Qatar offering mobile phones, laptops, home appliances, and accessories.',
}

# Real product categories and items
PRODUCT_DATA = [
    {'category': 'Mobile Phones', 'brand': 'Apple', 'name': 'iPhone 15 Pro Max', 'sku': 'APL-IP15PM-256', 'price': 5499, 'barcode': '1234567890123'},
    {'category': 'Mobile Phones', 'brand': 'Samsung', 'name': 'Galaxy S24 Ultra', 'sku': 'SAM-S24U-256', 'price': 4899, 'barcode': '1234567890124'},
    {'category': 'Mobile Phones', 'brand': 'Apple', 'name': 'iPhone 15', 'sku': 'APL-IP15-128', 'price': 3499, 'barcode': '1234567890125'},
    {'category': 'Laptops', 'brand': 'Apple', 'name': 'MacBook Pro 14" M3', 'sku': 'APL-MBP14-M3', 'price': 8999, 'barcode': '1234567890126'},
    {'category': 'Laptops', 'brand': 'Dell', 'name': 'XPS 15 Intel i7', 'sku': 'DEL-XPS15-I7', 'price': 6499, 'barcode': '1234567890127'},
    {'category': 'Laptops', 'brand': 'HP', 'name': 'Spectre x360', 'sku': 'HP-SPEC360-I7', 'price': 5999, 'barcode': '1234567890128'},
    {'category': 'Tablets', 'brand': 'Apple', 'name': 'iPad Pro 12.9"', 'sku': 'APL-IPADP-129', 'price': 4999, 'barcode': '1234567890129'},
    {'category': 'Tablets', 'brand': 'Samsung', 'name': 'Galaxy Tab S9 Ultra', 'sku': 'SAM-TABS9U', 'price': 4299, 'barcode': '1234567890130'},
    {'category': 'Accessories', 'brand': 'Apple', 'name': 'AirPods Pro 2', 'sku': 'APL-APP2', 'price': 999, 'barcode': '1234567890131'},
    {'category': 'Accessories', 'brand': 'Samsung', 'name': 'Galaxy Buds2 Pro', 'sku': 'SAM-BUDS2P', 'price': 749, 'barcode': '1234567890132'},
    {'category': 'Accessories', 'brand': 'Anker', 'name': 'PowerCore 26800mAh', 'sku': 'ANK-PC26800', 'price': 249, 'barcode': '1234567890133'},
    {'category': 'Smart Watches', 'brand': 'Apple', 'name': 'Apple Watch Ultra 2', 'sku': 'APL-AWU2', 'price': 3199, 'barcode': '1234567890134'},
    {'category': 'Smart Watches', 'brand': 'Samsung', 'name': 'Galaxy Watch 6 Classic', 'sku': 'SAM-GW6C', 'price': 1499, 'barcode': '1234567890135'},
    {'category': 'Home Appliances', 'brand': 'Dyson', 'name': 'V15 Detect Vacuum', 'sku': 'DYS-V15DET', 'price': 2799, 'barcode': '1234567890136'},
    {'category': 'Home Appliances', 'brand': 'Philips', 'name': 'Air Fryer XXL', 'sku': 'PHL-AFXXL', 'price': 899, 'barcode': '1234567890137'},
]

# Qatar customer names (Arabic names common in Qatar)
CUSTOMER_NAMES = [
    'Mohammed Al Thani', 'Ahmed Al Sulaiti', 'Fatima Al Kuwari', 'Sara Al Mannai',
    'Khalid Al Mohannadi', 'Noura Al Naimi', 'Hamad Al Marri', 'Maryam Al Attiyah',
    'Abdullah Al Dosari', 'Aisha Al Jaber', 'Youssef Al Khulaifi', 'Hessa Al Malki',
    'Omar Al Kaabi', 'Latifa Al Hajri', 'Ibrahim Al Emadi', 'Reem Al Sowaidi',
    'Nasser Al Buainain', 'Dana Al Muhanadi', 'Rashid Al Obaidly', 'Shaikha Al Misnad',
]

# Qatar phone numbers (format: +974 XXXX XXXX)
def generate_qatar_phone():
    prefixes = ['3', '5', '6', '7']
    return f"+974{random.choice(prefixes)}{random.randint(1000000, 9999999)}"


class Command(BaseCommand):
    help = 'Create dummy data for testing with real Qatar locations'

    def add_arguments(self, parser):
        parser.add_argument(
            '--clear',
            action='store_true',
            help='Clear all dummy data created by this command',
        )

    def handle(self, *args, **options):
        if options['clear']:
            self.clear_dummy_data()
        else:
            self.create_dummy_data()

    @transaction.atomic
    def clear_dummy_data(self):
        """Clear all dummy data created by this command"""
        self.stdout.write('Clearing dummy data...')

        # Delete in reverse order of dependencies
        DeliveryTask.objects.filter(order__business__business_code='ALSHAM').delete()
        DlAddressUpdate.objects.filter(order__business__business_code='ALSHAM').delete()
        OrderItem.objects.filter(order__business__business_code='ALSHAM').delete()
        Order.objects.filter(business__business_code='ALSHAM').delete()

        # Delete products
        Product.objects.filter(business__business_code='ALSHAM').delete()

        # Delete warehouse links
        SellerWarehouseLink.objects.filter(business__business_code='ALSHAM').delete()

        # Delete pickup locations
        PickupLocation.objects.filter(business__business_code='ALSHAM').delete()

        # Delete driver
        Driver.objects.filter(driver_code='DRV-DUMMY-001').delete()

        # Delete warehouse
        Warehouse.objects.filter(code='WH-DUMMY-001').delete()

        # Delete business
        try:
            business = Business.objects.get(business_code='ALSHAM')
            BusinessProfile.objects.filter(business=business).delete()
            business.delete()
        except Business.DoesNotExist:
            pass

        # Delete test user
        User.objects.filter(username='testbusiness').delete()
        User.objects.filter(username='testdriver').delete()

        # Delete zone names created by dummy data
        ZoneName.objects.filter(zone_name__in=[z['name'] for z in QATAR_ZONES]).delete()

        # Delete product categories
        ProductCategory.objects.filter(category_name__in=[
            'Mobile Phones', 'Laptops', 'Tablets', 'Accessories', 'Smart Watches', 'Home Appliances'
        ]).delete()

        self.stdout.write(self.style.SUCCESS('Dummy data cleared successfully!'))

    @transaction.atomic
    def create_dummy_data(self):
        """Create comprehensive dummy data"""
        self.stdout.write('Creating dummy data with real Qatar locations...')

        # 1. Create Zone Names
        self.stdout.write('  Creating Qatar zones...')
        for zone_data in QATAR_ZONES:
            ZoneName.objects.get_or_create(
                zone_number=zone_data['zone'],
                defaults={'zone_name': zone_data['name']}
            )

        # 2. Create test user for business
        self.stdout.write('  Creating test business user...')
        business_user, created = User.objects.get_or_create(
            username='testbusiness',
            defaults={
                'email': 'testbusiness@ezzydelivery.qa',
                'first_name': 'Test',
                'last_name': 'Business',
                'is_active': True,
            }
        )
        if created:
            business_user.set_password('TestBusiness@123')
            business_user.save()

        # Get or create profile
        profile, _ = Profile.objects.get_or_create(user=business_user)

        # 3. Create Business
        self.stdout.write('  Creating business...')
        # Get next available business_id
        from django.db.models import Max
        max_business_id = Business.objects.aggregate(max_id=Max('business_id'))['max_id'] or 0
        next_business_id = max_business_id + 1000  # Use a high number to avoid conflicts

        business, _ = Business.objects.get_or_create(
            business_code=BUSINESS_DATA['code'],
            defaults={
                'business_id': next_business_id,
                'user': business_user,
                'profile': profile,
                'business_name': BUSINESS_DATA['name'],
                'business_phone': BUSINESS_DATA['phone'],
                'business_email': BUSINESS_DATA['email'],
                'business_whatsapp': BUSINESS_DATA['whatsapp'],
                'business_status': 'active',
                'fulfillment_service_enabled': True,
                'fulfillment_activated_at': timezone.now(),
            }
        )

        # 4. Create Business Profile
        self.stdout.write('  Creating business profile...')
        BusinessProfile.objects.get_or_create(
            business=business,
            defaults={
                'business_description': BUSINESS_DATA['description'],
                'business_address': BUSINESS_DATA['address'],
                'business_city': BUSINESS_DATA['city'],
                'business_country': 'Qatar',
                'business_phone': BUSINESS_DATA['phone'],
                'business_email': BUSINESS_DATA['email'],
            }
        )

        # 5. Create Pickup Locations (3 locations in different zones)
        self.stdout.write('  Creating pickup locations...')
        pickup_zones = [QATAR_ZONES[3], QATAR_ZONES[10], QATAR_ZONES[12]]  # Fereej Abdel Aziz, West Bay, Fereej Al Soudan
        pickup_locations = []

        for i, zone in enumerate(pickup_zones, 1):
            pickup, _ = PickupLocation.objects.get_or_create(
                business=business,
                pickup_location_title=f'{BUSINESS_DATA["name"]} - {zone["name"]} Branch',
                defaults={
                    'locality': zone['name'],
                    'pickup_zone_no': zone['zone'],
                    'pickup_street_no': random.randint(100, 999),
                    'pickup_building_no': random.randint(1, 50),
                    'pickup_lat': Decimal(str(zone['lat'])),
                    'pickup_lon': Decimal(str(zone['lon'])),
                    'pickup_status': 'active',
                }
            )
            pickup_locations.append(pickup)

        # 6. Create Warehouse
        self.stdout.write('  Creating warehouse...')
        warehouse, _ = Warehouse.objects.get_or_create(
            code='WH-DUMMY-001',
            defaults={
                'name': 'EzzyDelivery Fulfillment Center - Industrial Area',
                'description': 'Main fulfillment center for electronics and general merchandise',
                'address': 'Street 44, Industrial Area',
                'city': 'Doha',
                'state': 'Ad Dawhah',
                'postal_code': '00000',
                'country': 'Qatar',
                'latitude': Decimal('25.2333'),
                'longitude': Decimal('51.4500'),
                'phone': '+97444556677',
                'email': 'warehouse@ezzydelivery.qa',
                'is_active': True,
                'is_default': True,
                'total_zones': 4,
                'racks_per_zone': 10,
                'shelves_per_rack': 5,
                'bins_per_shelf': 8,
                'zone_naming_pattern': 'A,B,C,D',
                'is_capacity_configured': True,
                'capacity_configured_at': timezone.now(),
            }
        )

        # 7. Create Warehouse Location
        self.stdout.write('  Creating warehouse location...')
        wh_location, _ = WarehouseLocation.objects.get_or_create(
            warehouse=warehouse,
            name='Main Dock',
            defaults={
                'code': 'WH-DUMMY-001-DOCK',
                'address': 'Street 44, Industrial Area, Doha',
                'zone_number': '58',
                'latitude': Decimal('25.2333'),
                'longitude': Decimal('51.4500'),
                'is_active': True,
                'is_default': True,
            }
        )

        # 8. Link Business to Warehouse
        self.stdout.write('  Linking business to warehouse...')
        SellerWarehouseLink.objects.get_or_create(
            business=business,
            warehouse=warehouse,
            defaults={
                'default_location': wh_location,
                'is_default': True,
                'is_active': True,
                'priority': 1,
            }
        )

        # 9. Create Product Categories
        self.stdout.write('  Creating product categories...')
        categories = {}
        category_names = set(p['category'] for p in PRODUCT_DATA)
        for cat_name in category_names:
            cat, _ = ProductCategory.objects.get_or_create(
                category_name=cat_name,
                defaults={'discription': f'{cat_name} products'}
            )
            categories[cat_name] = cat

        # 10. Create Products
        self.stdout.write('  Creating products...')
        products = []
        for i, prod_data in enumerate(PRODUCT_DATA):
            product, _ = Product.objects.get_or_create(
                business=business,
                item_sku=prod_data['sku'],
                defaults={
                    'product_category': categories[prod_data['category']],
                    'brand_name': prod_data['brand'],
                    'item_name': prod_data['name'],
                    'barcode': prod_data['barcode'],
                    'item_price': prod_data['price'],
                    'item_discription': f'{prod_data["brand"]} {prod_data["name"]} - Premium quality',
                }
            )
            products.append(product)

            # Create inventory for each product
            ProductInventory.objects.get_or_create(
                item_sku=product,
                defaults={'item_quantity': random.randint(10, 100)}
            )

        # 11. Create Driver
        self.stdout.write('  Creating test driver...')
        driver_user, created = User.objects.get_or_create(
            username='testdriver',
            defaults={
                'email': 'testdriver@ezzydelivery.qa',
                'first_name': 'Hamad',
                'last_name': 'Al Farsi',
                'is_active': True,
            }
        )
        if created:
            driver_user.set_password('TestDriver@123')
            driver_user.save()

        driver_profile, _ = Profile.objects.get_or_create(user=driver_user)

        # Get next available driver_id
        max_driver_id = Driver.objects.aggregate(max_id=Max('driver_id'))['max_id'] or 0
        next_driver_id = max_driver_id + 100  # Use a high number to avoid conflicts

        driver, _ = Driver.objects.get_or_create(
            driver_code='DRV-DUMMY-001',
            defaults={
                'driver_id': next_driver_id,
                'user': driver_user,
                'profile': driver_profile,
                'driver_phone': '+97433445566',
                'driver_whatsapp': '+97433445566',
                'driver_bio': 'Experienced delivery driver in Doha',
                'driver_languages': 'arabic',
                'driver_license_number': 'QA-DL-123456',
                'driver_rating': 48,
                'driver_rating_count': 10,
                'driver_status': 'approved',
                'wallet_balance': Decimal('500.00'),
                'credit_limit': Decimal('5000.00'),
                'cod_in_hand': Decimal('0.00'),
            }
        )

        # Create driver vehicle
        DriverVehicle.objects.get_or_create(
            driver=driver,
            vehicle_no='12345',
            defaults={
                'vehicle_type': 'car',
                'vehicle_model': 'Toyota Hilux 2023',
                'vehicle_color': 'White',
                'vehicle_status': 'active',
                'vehicle_date': timezone.now().date(),
            }
        )

        # 12. Create Orders with various statuses
        self.stdout.write('  Creating orders with various statuses...')

        order_statuses = [
            ('to_review', 'new_order'),
            ('to_review', 'info_missing'),
            ('ready_to_pickup', 'pending_for_confirm'),
            ('ready_to_pickup', 'dl_task_listed'),
            ('publish', 'dl_task_listed'),
            ('publish', 'dl_task_listed'),
            ('delivered', 'dl_task_listed'),
            ('delivered', 'dl_task_listed'),
            ('fulfilled', 'dl_task_listed'),
            ('cancelled', 'dl_task_listed'),
        ]

        cod_statuses = ['no_cod', 'pending', 'pending', 'pending', 'collected']

        orders = []
        for i in range(20):
            order_status, task_status = order_statuses[i % len(order_statuses)]
            cod_status = cod_statuses[i % len(cod_statuses)]
            zone = random.choice(QATAR_ZONES)
            customer_name = random.choice(CUSTOMER_NAMES)
            customer_phone = generate_qatar_phone()

            # Generate order number
            order_num = f"ORD-{timezone.now().strftime('%Y%m%d')}-{str(i+1).zfill(4)}"
            client_code = f"ALSHAM-{str(i+1).zfill(5)}"

            # Random product selection
            order_products = random.sample(products, random.randint(1, 3))
            total_amount = sum(p.item_price for p in order_products)

            order, created = Order.objects.get_or_create(
                order_number=order_num,
                defaults={
                    'business': business,
                    'client_order_code': client_code,
                    'order_status': order_status,
                    'task_status': task_status,
                    'pickup_location': random.choice(pickup_locations),
                    'cod_status_by_client': cod_status,
                    'cod_status_by_staff': 'not_collected' if cod_status != 'no_cod' else 'not_collected',
                    'cod_amount': total_amount if cod_status != 'no_cod' else 0,
                    'dl_amount': 25,  # Standard delivery fee
                    'dl_included': True,
                    'customer_name': customer_name,
                    'customer_phone': customer_phone,
                    'customer_whatsapp': customer_phone,
                    'customer_address': f'Building {random.randint(1, 99)}, Street {random.randint(100, 999)}, {zone["name"]}',
                    'dl_zone': zone['zone'],
                    'dl_building': random.randint(1, 99),
                    'dl_street': random.randint(100, 999),
                    'deadline_date': (timezone.now() + timedelta(days=random.randint(1, 7))).strftime('%Y-%m-%d'),
                    'order_notes': f'Test order #{i+1} - Handle with care',
                    'verification_status': 'verified' if order_status in ['publish', 'delivered', 'fulfilled'] else 'pending',
                }
            )

            if created:
                # Create order items
                for product in order_products:
                    qty = random.randint(1, 2)
                    OrderItem.objects.create(
                        order=order,
                        product=product,
                        quantity=qty,
                        unit_price=Decimal(str(product.item_price)),
                        total_price=Decimal(str(product.item_price * qty)),
                    )

                orders.append(order)

        # 13. Create Delivery Tasks with various statuses
        self.stdout.write('  Creating delivery tasks...')

        task_statuses = [
            'for_review', 'pending', 'address_pending', 'customer_confiration_pending',
            'publish_to_dms', 'in_transit', 'delivered', 'delivered', 'cancelled', 'rejected'
        ]

        dms_statuses = ['0', '1', '2', '2', '3', '4', '6', '7', '8', '9']

        for i, order in enumerate(orders):
            task_status = task_statuses[i % len(task_statuses)]
            dms_status = dms_statuses[i % len(dms_statuses)]
            zone = random.choice(QATAR_ZONES)

            # Create delivery address
            dl_address, _ = DlAddressUpdate.objects.get_or_create(
                order=order,
                defaults={
                    'full_name': order.customer_name,
                    'mobile_no': order.customer_phone,
                    'area_name': zone['name'],
                    'dl_zone': zone['zone'],
                    'dl_street': random.randint(100, 999),
                    'dl_building': random.randint(1, 99),
                    'dl_latitude': Decimal(str(zone['lat'] + random.uniform(-0.01, 0.01))),
                    'dl_longitude': Decimal(str(zone['lon'] + random.uniform(-0.01, 0.01))),
                    'dl_unit': str(random.randint(1, 20)) if random.choice([True, False]) else '',
                    'is_villa_compound': random.choice([True, False]),
                    'is_flat': random.choice([True, False]),
                }
            )

            # Create delivery task
            task_num = f"DLT-{timezone.now().strftime('%Y%m%d')}-{str(i+1).zfill(4)}"

            DeliveryTask.objects.get_or_create(
                dl_task_number=task_num,
                defaults={
                    'order': order,
                    'business': business,
                    'pickup_location': order.pickup_location,
                    'driver': driver if task_status in ['in_transit', 'delivered'] else None,
                    'dl_task_publish': task_status in ['publish_to_dms', 'in_transit', 'delivered'],
                    'dl_task_description': f'Delivery for order {order.order_number}',
                    'dl_task_status': task_status,
                    'dl_task_status_dms': dms_status,
                    'dl_task_date': timezone.now().date() + timedelta(days=random.randint(0, 3)),
                    'dl_address_update': dl_address,
                    'dl_to_address': dl_address,
                    'dl_waight': random.randint(1, 5),
                    'dl_category': random.choice(['Food', 'Regular', 'Electronics']),
                    'dl_speed': random.choice(['Normal', 'Same Day', 'On Demand']),
                    'dl_price': 25,
                    'driver_earnings': Decimal('15.00') if task_status == 'delivered' else Decimal('0.00'),
                    'company_commission': Decimal('10.00') if task_status == 'delivered' else Decimal('0.00'),
                    'cod_collected': task_status == 'delivered' and order.cod_amount > 0,
                    'cod_collected_amount': Decimal(str(order.cod_amount)) if task_status == 'delivered' and order.cod_amount > 0 else Decimal('0.00'),
                    'completed_at': timezone.now() if task_status == 'delivered' else None,
                }
            )

        self.stdout.write(self.style.SUCCESS(f'''
Dummy data created successfully!

Summary:
--------
- 1 Business: {BUSINESS_DATA["name"]} (Code: {BUSINESS_DATA["code"]})
- {len(pickup_locations)} Pickup Locations
- 1 Warehouse: EzzyDelivery Fulfillment Center
- {len(products)} Products across {len(categories)} categories
- {len(orders)} Orders with various statuses
- {len(orders)} Delivery Tasks with various statuses
- 1 Driver: Hamad Al Farsi (Code: DRV-DUMMY-001)
- {len(QATAR_ZONES)} Qatar Zones

Login credentials:
-----------------
Business User: testbusiness / TestBusiness@123
Driver User: testdriver / TestDriver@123

To clear this data after testing:
--------------------------------
python manage.py create_dummy_data --clear
'''))
