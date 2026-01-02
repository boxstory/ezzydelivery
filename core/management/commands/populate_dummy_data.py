"""
Management command to populate the database with realistic Qatar-based dummy data.

Usage:
    python manage.py populate_dummy_data
    python manage.py populate_dummy_data --clear  # Clear existing data first
"""

import random
from datetime import datetime, timedelta
from decimal import Decimal
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.utils import timezone
from django.db import transaction


# ============================================================================
# QATAR-SPECIFIC DATA
# ============================================================================

# Qatar Zones with real zone numbers and names
QATAR_ZONES = {
    1: "West Bay",
    2: "Al Dafna",
    3: "Al Corniche",
    4: "Musheireb",
    5: "Al Souq",
    6: "Al Jasra",
    7: "Al Bidda",
    8: "Al Rumaila",
    9: "Al Hitmi",
    10: "Fereej Al Nasr",
    11: "Old Airport",
    12: "Fereej Bin Omran",
    13: "Al Mansoura",
    14: "Fereej Abdul Aziz",
    15: "Najma",
    16: "Umm Ghuwailina",
    17: "Al Khulaifat",
    18: "Fereej Al Amir",
    19: "Al Sadd",
    20: "Al Mirqab Al Jadeed",
    21: "Al Muntazah",
    22: "Al Maamoura",
    23: "Madinat Khalifa North",
    24: "Madinat Khalifa South",
    25: "Old Al Ghanim",
    26: "New Al Ghanim",
    27: "Al Markhiya",
    28: "Onaiza",
    29: "Al Duhail North",
    30: "Al Duhail South",
    31: "Fereej Kulaib",
    32: "Fereej Al Asmakh",
    33: "Fereej Al Soudan",
    34: "Al Waab",
    35: "Al Aziziya",
    36: "Ain Khaled",
    37: "Al Gharrafa",
    38: "Al Rayyan",
    39: "Muaither",
    40: "Al Luqta",
    41: "Bu Hamour",
    42: "Al Thumama",
    43: "Abu Hamour",
    44: "Al Wakra",
    45: "Al Wukair",
    46: "Mesaieed",
    47: "Dukhan",
    48: "Al Khor",
    49: "Al Thakhira",
    50: "Ras Laffan",
    51: "Lusail",
    52: "The Pearl",
    53: "Katara",
    54: "Education City",
    55: "Msheireb Downtown",
    56: "Al Bayt Stadium Area",
    57: "Al Bidda Park",
    58: "Aspire Zone",
    59: "Villaggio Area",
    60: "Landmark Mall Area",
    61: "City Center Area",
    62: "Salwa Road",
    63: "Industrial Area",
    64: "Umm Salal",
    65: "Al Kheesa",
    66: "Al Shahaniya",
    67: "Leabaib",
    68: "Al Sailiya",
    69: "Rawdat Egdaim",
    70: "Al Sakhama",
}

# Qatar coordinates (approximate center points for zones)
QATAR_COORDS = {
    1: (25.3225, 51.5310),  # West Bay
    2: (25.3190, 51.5280),  # Al Dafna
    19: (25.2790, 51.5130),  # Al Sadd
    24: (25.3100, 51.4850),  # Madinat Khalifa
    38: (25.2920, 51.4230),  # Al Rayyan
    44: (25.1710, 51.6030),  # Al Wakra
    51: (25.4120, 51.4900),  # Lusail
    52: (25.3710, 51.5510),  # The Pearl
    54: (25.3140, 51.4420),  # Education City
    63: (25.2100, 51.4500),  # Industrial Area
}

# Arabic first names (Qatar common)
ARABIC_FIRST_NAMES_MALE = [
    "Mohammed", "Ahmed", "Ali", "Khalid", "Abdullah", "Hamad", "Saad", "Nasser",
    "Ibrahim", "Yousef", "Omar", "Hassan", "Hussain", "Faisal", "Sultan",
    "Abdulrahman", "Rashid", "Fahad", "Saleh", "Majid", "Khaled", "Waleed",
    "Saud", "Turki", "Bandar", "Nawaf", "Mansour", "Jassim", "Thani", "Tamim"
]

ARABIC_FIRST_NAMES_FEMALE = [
    "Fatima", "Aisha", "Mariam", "Sara", "Noura", "Hessa", "Moza", "Latifa",
    "Shaikha", "Reem", "Dana", "Hind", "Asma", "Khadija", "Amna", "Salama"
]

# Arabic family names (Qatar common)
ARABIC_FAMILY_NAMES = [
    "Al Thani", "Al Attiyah", "Al Kuwari", "Al Sulaiti", "Al Mohannadi",
    "Al Marri", "Al Dosari", "Al Hajri", "Al Naimi", "Al Malki",
    "Al Kaabi", "Al Khater", "Al Mansouri", "Al Nuaimi", "Al Shammari",
    "Al Qahtani", "Al Ghanim", "Al Emadi", "Al Hamad", "Al Jaber",
    "Al Mana", "Al Darwish", "Al Sayed", "Al Khulaifi", "Al Muftah"
]

# Indian/Pakistani names (expat workers in Qatar)
SOUTH_ASIAN_FIRST_NAMES = [
    "Raj", "Amit", "Vikram", "Sanjay", "Rahul", "Suresh", "Anil", "Deepak",
    "Muhammad", "Imran", "Tariq", "Farhan", "Bilal", "Usman", "Asif", "Waseem"
]

SOUTH_ASIAN_FAMILY_NAMES = [
    "Sharma", "Kumar", "Singh", "Patel", "Khan", "Malik", "Hussain", "Siddiqui",
    "Chaudhary", "Qureshi", "Sheikh", "Mirza", "Akhtar", "Rahman", "Ahmed"
]

# Filipino names (expat workers in Qatar)
FILIPINO_FIRST_NAMES = [
    "Juan", "Jose", "Carlo", "Miguel", "Rafael", "Antonio", "Gabriel", "Marco",
    "Maria", "Ana", "Bella", "Carmen", "Rosa", "Elena", "Patricia", "Teresa"
]

FILIPINO_FAMILY_NAMES = [
    "Santos", "Reyes", "Cruz", "Bautista", "Del Rosario", "Garcia", "Mendoza",
    "Torres", "Villanueva", "Flores", "Ramos", "Castro", "Rivera", "Fernandez"
]

# Business types common in Qatar
QATAR_BUSINESS_TYPES = [
    "Restaurant", "Cafe", "Bakery", "Supermarket", "Electronics Store",
    "Fashion Boutique", "Pharmacy", "Perfume Shop", "Jewelry Store",
    "Mobile Shop", "Furniture Store", "Home Decor", "Florist", "Gift Shop",
    "Sports Equipment", "Auto Parts", "Pet Shop", "Toy Store", "Book Store",
    "Health & Beauty", "Optical Store", "Watch Store", "Shoe Store",
    "Clothing Store", "Grocery", "Laundry", "Dry Cleaning"
]

# Qatar business name prefixes/suffixes
QATAR_BUSINESS_PREFIXES = [
    "Al", "Bin", "Qatar", "Gulf", "Doha", "Pearl", "Arabian", "Golden",
    "Royal", "Premium", "Elite", "Classic", "Modern", "Grand", "Super"
]

QATAR_BUSINESS_SUFFIXES = [
    "Trading", "Store", "Shop", "Mart", "Express", "Plus", "Center",
    "World", "Hub", "Zone", "Point", "House", "Palace", "Gallery"
]

# Qatar phone number format: XXXX XXXX (8 digits, fits in IntegerField)
def generate_qatar_phone():
    prefixes = ["3", "5", "6", "7"]  # Qatar mobile prefixes
    return f"{random.choice(prefixes)}{random.randint(1000000, 9999999)}"


# Generate phone as integer (for IntegerField in Profile model)
def generate_qatar_phone_int():
    prefixes = [3, 5, 6, 7]  # Qatar mobile prefixes
    return int(f"{random.choice(prefixes)}{random.randint(1000000, 9999999)}")

# Product categories and items for Qatar market
PRODUCT_CATEGORIES = {
    "Food & Beverages": [
        ("Arabic Coffee", 45), ("Karak Tea Set", 25), ("Dates Premium Box", 120),
        ("Baklava Assorted", 85), ("Kunafa", 55), ("Sambosa Pack", 30),
        ("Hummus Fresh", 15), ("Falafel Mix", 20), ("Shawarma Kit", 45)
    ],
    "Electronics": [
        ("iPhone 15 Pro", 4500), ("Samsung Galaxy S24", 3800), ("iPad Pro", 3200),
        ("AirPods Pro", 950), ("Smart Watch", 1200), ("Power Bank 20000mAh", 150),
        ("Wireless Charger", 120), ("Bluetooth Speaker", 280), ("Laptop Stand", 180)
    ],
    "Fashion & Apparel": [
        ("Thobe White Premium", 450), ("Abaya Black Silk", 680), ("Ghutra Red", 150),
        ("Agal Black", 80), ("Kandura Set", 520), ("Hijab Collection", 120),
        ("Prayer Mat Velvet", 95), ("Leather Belt", 180), ("Cufflinks Gold", 350)
    ],
    "Home & Living": [
        ("Arabic Coffee Set", 320), ("Majlis Cushion", 180), ("Oud Burner", 250),
        ("Carpet Persian 2x3m", 1500), ("Lantern Brass", 420), ("Tea Set 12pc", 280),
        ("Incense Holder", 95), ("Wall Art Arabic", 450), ("Vase Ceramic", 180)
    ],
    "Health & Beauty": [
        ("Oud Perfume 100ml", 650), ("Bakhoor Premium", 180), ("Rose Water", 45),
        ("Argan Oil", 120), ("Henna Kit", 55), ("Kohl Eyeliner", 35),
        ("Miswak Natural", 15), ("Musk Roll-on", 85), ("Attar Collection", 420)
    ],
    "Sports & Outdoors": [
        ("Football Qatar 2022", 180), ("Cricket Set", 350), ("Gym Bag", 150),
        ("Running Shoes", 450), ("Yoga Mat Premium", 120), ("Water Bottle 1L", 45),
        ("Camping Tent 4P", 850), ("Desert Cooler", 280), ("Bicycle Helmet", 180)
    ],
}

# Color variants
COLORS = ["Black", "White", "Red", "Blue", "Green", "Gold", "Silver", "Brown", "Beige", "Navy"]

# Unit variants
UNITS = ["Piece", "Box", "Pack", "Set", "Kg", "Liter", "Meter", "Pair"]


class Command(BaseCommand):
    help = 'Populate database with realistic Qatar-based dummy data (min 50 rows per table)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--clear',
            action='store_true',
            help='Clear existing data before populating',
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE('Starting Qatar-based dummy data population...'))

        try:
            # Clear data outside atomic block to avoid transaction issues
            if options['clear']:
                self.clear_data()

            with transaction.atomic():
                # Import models here to avoid circular imports
                from core.models import Profile, ProfilePicture
                from business.models import (
                    Business, BusinessProfile, PickupLocation,
                    BusinessTeamProfile, DriverDirectory
                )
                from fleet.models import Driver, DriverVehicle, DriverDocument
                from product.models import Product, ProductCategory, ColorVariant, UnitVariant, ProductInventory
                from orders.models import Order, OrderItem, OrderBarcode
                from delivery.models import DeliveryTask, DlAddressUpdate, ZoneName, LatLonList

                # Create data in order of dependencies
                self.create_zones()
                self.create_lat_lon_list()
                users = self.create_users_and_profiles()
                businesses = self.create_businesses(users)
                pickup_locations = self.create_pickup_locations(businesses)
                drivers = self.create_drivers(users)
                self.create_driver_vehicles(drivers)
                categories, colors, units = self.create_product_variants()
                products = self.create_products(businesses, categories, colors, units)
                orders = self.create_orders(businesses, pickup_locations)
                self.create_order_items(orders, products)
                self.create_delivery_tasks(orders, drivers, businesses, pickup_locations)

                self.stdout.write(self.style.SUCCESS('Successfully populated all tables with Qatar-based dummy data!'))

        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Error populating data: {str(e)}'))
            raise

    def clear_data(self):
        """Clear existing dummy data using TRUNCATE CASCADE for PostgreSQL"""
        self.stdout.write('Clearing existing data...')

        from django.db import connection

        # Tables to truncate in order (CASCADE handles dependencies)
        tables_to_truncate = [
            'delivery_deliverytask',
            'delivery_dladdressupdate',
            'delivery_shippinglabel',
            'delivery_assigneddriver',
            'orders_orderitem',
            'orders_orderbarcode',
            'orders_ordercomments',
            'orders_orderverificationlog',
            'orders_addressverification',
            'orders_order',
            'product_productinventory',
            'product_product',
            'product_productcategory',
            'product_colorvariant',
            'product_unitvariant',
            'fleet_drivertransaction',
            'fleet_driversettlement',
            'fleet_drivervehicle',
            'fleet_driverdocument',
            'fleet_driver',
            'client_driverdirectory',
            'client_pickuplocation',
            'client_businessprofile',
            'client_businessteamprofile',
            'client_businesslogo',
            'client_businessposter',
            'client_businesssocialinfo',
            'client_businessapisettings',
            'client_business',
            'core_profilepicture',
            'core_profile',
            'delivery_zonename',
            'delivery_latlonlist',
        ]

        with connection.cursor() as cursor:
            for table in tables_to_truncate:
                try:
                    cursor.execute(f'TRUNCATE TABLE "{table}" CASCADE;')
                    self.stdout.write(f'  Truncated {table}')
                except Exception as e:
                    self.stdout.write(f'  Skipping {table}: {str(e)[:40]}')

            # Delete non-superuser users
            try:
                cursor.execute('DELETE FROM auth_user WHERE is_superuser = FALSE;')
                self.stdout.write('  Deleted non-superuser users')
            except Exception as e:
                self.stdout.write(f'  Skipping auth_user: {str(e)[:40]}')

        self.stdout.write(self.style.SUCCESS('Cleared existing data'))

    def create_zones(self):
        """Create Qatar zone data"""
        self.stdout.write('Creating Qatar zones...')
        from delivery.models import ZoneName

        zones_created = 0
        for zone_num, zone_name in QATAR_ZONES.items():
            ZoneName.objects.get_or_create(
                zone_number=zone_num,
                defaults={'zone_name': zone_name}
            )
            zones_created += 1

        self.stdout.write(f'  Created {zones_created} zones')

    def create_lat_lon_list(self):
        """Create coordinate data for Qatar zones"""
        self.stdout.write('Creating coordinate data...')
        from delivery.models import LatLonList

        coords_created = 0
        for zone_num in QATAR_ZONES.keys():
            base_lat, base_lon = QATAR_COORDS.get(zone_num, (25.2867, 51.5333))

            # Create 3-5 streets per zone
            for street in range(1, random.randint(4, 6)):
                # Create 5-10 buildings per street
                for building in range(1, random.randint(6, 11)):
                    lat_offset = random.uniform(-0.01, 0.01)
                    lon_offset = random.uniform(-0.01, 0.01)

                    LatLonList.objects.create(
                        zone_number=zone_num,
                        street_number=street,
                        building_number=building,
                        latitude=Decimal(str(base_lat + lat_offset)),
                        longitude=Decimal(str(base_lon + lon_offset))
                    )
                    coords_created += 1

        self.stdout.write(f'  Created {coords_created} coordinate entries')

    def create_users_and_profiles(self):
        """Create 60+ users with profiles"""
        self.stdout.write('Creating users and profiles...')
        from core.models import Profile

        users = []

        # Create diverse user base
        for i in range(65):
            # Determine ethnicity for realistic Qatar demographics
            ethnicity = random.choices(
                ['arabic', 'south_asian', 'filipino'],
                weights=[30, 50, 20]
            )[0]

            if ethnicity == 'arabic':
                if random.random() > 0.3:
                    first_name = random.choice(ARABIC_FIRST_NAMES_MALE)
                else:
                    first_name = random.choice(ARABIC_FIRST_NAMES_FEMALE)
                last_name = random.choice(ARABIC_FAMILY_NAMES)
            elif ethnicity == 'south_asian':
                first_name = random.choice(SOUTH_ASIAN_FIRST_NAMES)
                last_name = random.choice(SOUTH_ASIAN_FAMILY_NAMES)
            else:
                first_name = random.choice(FILIPINO_FIRST_NAMES)
                last_name = random.choice(FILIPINO_FAMILY_NAMES)

            username = f"{first_name.lower()}{last_name.lower().replace(' ', '')}{i+1}"
            email = f"{username}@ezzydelivery.qa"

            user = User.objects.create_user(
                username=username,
                email=email,
                password='testpass123',
                first_name=first_name,
                last_name=last_name
            )

            # Create profile
            zone = random.choice(list(QATAR_ZONES.keys()))

            profile = Profile.objects.create(
                user=user,
                username=username,
                first_name=first_name,
                last_name=last_name,
                email=email,
                phone=generate_qatar_phone_int(),
                whatsapp=generate_qatar_phone_int(),
                zone_name=QATAR_ZONES[zone],
                address=f"Building {random.randint(1, 50)}, Street {random.randint(1, 20)}, Zone {zone}",
                nationlity=random.choice(['Qatari', 'Indian', 'Pakistani', 'Filipino', 'Egyptian', 'Jordanian', 'Lebanese']),
                date_of_birth=datetime(
                    random.randint(1970, 2000),
                    random.randint(1, 12),
                    random.randint(1, 28)
                ).date(),
                is_business=i < 25,  # First 25 are business users
                is_driver=i >= 40,   # Last 25 are drivers
                is_staff=i >= 55 and i < 60,  # 5 staff users
                is_profile_completed=True,
                verification_status='verified'
            )

            users.append(user)

        self.stdout.write(f'  Created {len(users)} users with profiles')
        return users

    def create_businesses(self, users):
        """Create 55+ businesses"""
        self.stdout.write('Creating businesses...')
        from business.models import Business, BusinessProfile

        businesses = []
        business_users = [u for u in users if hasattr(u, 'profile') and u.profile.is_business]

        for i, user in enumerate(business_users[:55]):
            business_type = random.choice(QATAR_BUSINESS_TYPES)
            prefix = random.choice(QATAR_BUSINESS_PREFIXES)
            suffix = random.choice(QATAR_BUSINESS_SUFFIXES)

            business_name = f"{prefix} {user.last_name} {suffix}"
            business_code = f"BIZ{str(i+1).zfill(4)}"

            business = Business.objects.create(
                business_id=i + 1,
                user=user,
                profile=user.profile,
                business_name=business_name,
                business_code=business_code,
                business_bio=f"Leading {business_type.lower()} in Qatar",
                business_phone=generate_qatar_phone(),
                business_email=f"info@{business_code.lower()}.qa",
                business_whatsapp=generate_qatar_phone(),
                business_instagram=f"@{business_code.lower()}",
                business_product_category=business_type,
                business_status='active',
                business_since=datetime(
                    random.randint(2010, 2023),
                    random.randint(1, 12),
                    random.randint(1, 28)
                ).date()
            )

            # Create business profile
            BusinessProfile.objects.create(
                business=business,
                business_description=f"We are a premium {business_type.lower()} serving customers across Qatar with quality products and excellent service.",
                business_address=f"Building {random.randint(1, 100)}, Street {random.randint(1, 50)}",
                business_city="Doha",
                business_country="Qatar",
                business_phone=business.business_phone,
                business_email=business.business_email
            )

            businesses.append(business)

        self.stdout.write(f'  Created {len(businesses)} businesses')
        return businesses

    def create_pickup_locations(self, businesses):
        """Create 55+ pickup locations"""
        self.stdout.write('Creating pickup locations...')
        from business.models import PickupLocation

        pickup_locations = []

        for business in businesses:
            # Each business has 1-3 pickup locations
            num_locations = random.randint(1, 3)

            for j in range(num_locations):
                zone = random.choice(list(QATAR_ZONES.keys()))
                lat, lon = QATAR_COORDS.get(zone, (25.2867, 51.5333))

                pickup = PickupLocation.objects.create(
                    business=business,
                    pickup_location_title=f"{business.business_name} - {'Main' if j == 0 else f'Branch {j}'}",
                    locality=QATAR_ZONES[zone],
                    pickup_zone_no=zone,
                    pickup_street_no=random.randint(1, 50),
                    pickup_building_no=random.randint(1, 100),
                    pickup_lat=Decimal(str(lat + random.uniform(-0.01, 0.01))),
                    pickup_lon=Decimal(str(lon + random.uniform(-0.01, 0.01))),
                    pickup_status='active'
                )
                pickup_locations.append(pickup)

        self.stdout.write(f'  Created {len(pickup_locations)} pickup locations')
        return pickup_locations

    def create_drivers(self, users):
        """Create 50+ drivers"""
        self.stdout.write('Creating drivers...')
        from fleet.models import Driver
        from core.models import Profile

        drivers = []
        driver_users = [u for u in users if hasattr(u, 'profile') and u.profile.is_driver]

        # Add more drivers if needed - use unique counter
        extra_driver_count = 0
        while len(driver_users) < 55:
            extra_driver_count += 1
            first_name = random.choice(SOUTH_ASIAN_FIRST_NAMES)
            last_name = random.choice(SOUTH_ASIAN_FAMILY_NAMES)
            # Use timestamp and counter for uniqueness
            username = f"driver{first_name.lower()}{random.randint(1000, 9999)}{extra_driver_count}"

            user = User.objects.create_user(
                username=username,
                email=f"{username}@ezzydelivery.qa",
                password='testpass123',
                first_name=first_name,
                last_name=last_name
            )

            zone = random.choice(list(QATAR_ZONES.keys()))
            profile = Profile.objects.create(
                user=user,
                username=username,
                first_name=first_name,
                last_name=last_name,
                email=user.email,
                phone=generate_qatar_phone_int(),
                whatsapp=generate_qatar_phone_int(),
                zone_name=QATAR_ZONES[zone],
                is_driver=True,
                is_profile_completed=True,
                verification_status='verified'
            )
            driver_users.append(user)

        for i, user in enumerate(driver_users[:55]):
            driver = Driver.objects.create(
                driver_id=i + 1,
                user=user,
                profile=user.profile,
                driver_code=f"DRV{str(i+1).zfill(4)}",
                driver_code_dms=f"DMS{str(i+1).zfill(4)}",
                driver_phone=str(user.profile.phone),
                driver_whatsapp=str(user.profile.whatsapp),
                driver_bio=f"Experienced delivery driver in {user.profile.zone_name or 'Doha'}",
                driver_languages=random.choice(['english', 'arabic', 'hindi', 'philipine']),
                driver_license_number=f"QA{random.randint(100000, 999999)}",
                driver_rating=random.randint(3, 5),
                driver_rating_count=random.randint(10, 500),
                driver_status='Approved',
                wallet_balance=Decimal(str(random.randint(0, 5000))),
                credit_limit=Decimal('5000.00'),
                cod_in_hand=Decimal(str(random.randint(0, 2000))),
                total_earnings=Decimal(str(random.randint(5000, 50000))),
                pending_earnings=Decimal(str(random.randint(0, 3000)))
            )
            drivers.append(driver)

        self.stdout.write(f'  Created {len(drivers)} drivers')
        return drivers

    def create_driver_vehicles(self, drivers):
        """Create vehicles for drivers"""
        self.stdout.write('Creating driver vehicles...')
        from fleet.models import DriverVehicle

        vehicles_created = 0
        vehicle_models = {
            'bike': ['Honda PCX', 'Yamaha NMAX', 'Suzuki Address', 'Honda Click'],
            'car': ['Toyota Corolla', 'Nissan Sunny', 'Hyundai Accent', 'Kia Rio'],
            'van': ['Toyota Hiace', 'Nissan Urvan', 'Hyundai H1'],
            'pickup': ['Toyota Hilux', 'Nissan Navara', 'Ford Ranger']
        }
        colors = ['White', 'Silver', 'Black', 'Blue', 'Red', 'Gray']

        for driver in drivers:
            vehicle_type = random.choice(['bike', 'car', 'van', 'pickup'])

            DriverVehicle.objects.create(
                driver=driver,
                vehicle_type=vehicle_type,
                vehicle_no=f"{random.randint(10000, 99999)}",
                vehicle_model=random.choice(vehicle_models[vehicle_type]),
                vehicle_color=random.choice(colors),
                vehicle_status='active'
            )
            vehicles_created += 1

        self.stdout.write(f'  Created {vehicles_created} driver vehicles')

    def create_product_variants(self):
        """Create product categories, colors, and units"""
        self.stdout.write('Creating product variants...')
        from product.models import ProductCategory, ColorVariant, UnitVariant

        # Create categories
        categories = {}
        for cat_name in PRODUCT_CATEGORIES.keys():
            category = ProductCategory.objects.create(
                category_name=cat_name,
                discription=f"Products in {cat_name} category"
            )
            categories[cat_name] = category

        # Create colors
        colors = []
        for color in COLORS:
            c = ColorVariant.objects.create(
                color_variant=color,
                short_code=color[:3].upper(),
                discription=f"{color} color variant"
            )
            colors.append(c)

        # Create units
        units = []
        for unit in UNITS:
            u = UnitVariant.objects.create(
                unit_variant=unit,
                short_code=unit[:3].upper(),
                discription=f"{unit} unit type"
            )
            units.append(u)

        self.stdout.write(f'  Created {len(categories)} categories, {len(colors)} colors, {len(units)} units')
        return categories, colors, units

    def create_products(self, businesses, categories, colors, units):
        """Create 100+ products"""
        self.stdout.write('Creating products...')
        from product.models import Product, ProductInventory

        products = []
        sku_counter = 1

        for business in businesses[:30]:  # Products for first 30 businesses
            # Each business has 3-6 products
            num_products = random.randint(3, 6)
            category_name = random.choice(list(PRODUCT_CATEGORIES.keys()))
            category_products = PRODUCT_CATEGORIES[category_name]

            for _ in range(num_products):
                product_data = random.choice(category_products)
                product_name, base_price = product_data

                product = Product.objects.create(
                    brand_name=business.business_name,
                    item_name=product_name,
                    item_sku=f"SKU{str(sku_counter).zfill(6)}",
                    barcode=f"974{random.randint(1000000000, 9999999999)}",
                    color=random.choice(colors) if random.random() > 0.5 else None,
                    size=random.choice(['S', 'M', 'L', 'XL', 'One Size']) if random.random() > 0.5 else None,
                    unit=random.choice(units),
                    item_price=base_price + random.randint(-10, 50),
                    item_discription=f"High quality {product_name} from {business.business_name}",
                    business=business,
                    product_category=categories[category_name]
                )

                # Create inventory
                ProductInventory.objects.create(
                    item_sku=product,
                    item_quantity=random.randint(10, 500)
                )

                products.append(product)
                sku_counter += 1

        self.stdout.write(f'  Created {len(products)} products with inventory')
        return products

    def create_orders(self, businesses, pickup_locations):
        """Create 100+ orders"""
        self.stdout.write('Creating orders...')
        from orders.models import Order

        orders = []
        order_counter = 1

        statuses = ['to_review', 'ready_to_pickup', 'publish', 'delivered', 'fulfilled']
        task_statuses = ['new_order', 'info_missing', 'pending_for_confirm', 'dl_task_listed']

        for business in businesses[:40]:
            # Get pickup location for this business
            business_pickups = [p for p in pickup_locations if p.business_id == business.business_id]
            if not business_pickups:
                continue

            # Each business has 2-5 orders
            num_orders = random.randint(2, 5)

            for _ in range(num_orders):
                zone = random.choice(list(QATAR_ZONES.keys()))

                # Generate customer name based on demographics
                if random.random() > 0.7:
                    customer_name = f"{random.choice(ARABIC_FIRST_NAMES_MALE)} {random.choice(ARABIC_FAMILY_NAMES)}"
                else:
                    customer_name = f"{random.choice(SOUTH_ASIAN_FIRST_NAMES)} {random.choice(SOUTH_ASIAN_FAMILY_NAMES)}"

                order_status = random.choice(statuses)
                cod_amount = random.randint(0, 500) if random.random() > 0.3 else 0

                order = Order.objects.create(
                    order_number=f"ORD{datetime.now().strftime('%Y%m')}{str(order_counter).zfill(5)}",
                    business=business,
                    client_order_code=f"CLT{business.business_code}{str(order_counter).zfill(4)}",
                    order_notes=random.choice([
                        "Handle with care",
                        "Call before delivery",
                        "Leave at door",
                        "Ring doorbell twice",
                        "",
                        "Fragile items",
                        "Gift wrapping requested"
                    ]),
                    order_status=order_status,
                    task_status=random.choice(task_statuses),
                    pickup_location=random.choice(business_pickups),
                    task_created=order_status in ['publish', 'delivered', 'fulfilled'],
                    cod_status_by_client='include' if cod_amount > 0 else 'no_cod',
                    cod_status_by_staff='not_collected' if cod_amount > 0 else None,
                    cod_amount=cod_amount,
                    dl_included=True,
                    dl_amount=random.choice([15, 20, 25, 30, 35]),
                    verification_status=random.choice(['pending', 'verified', 'address_verified']),
                    customer_name=customer_name,
                    customer_phone=generate_qatar_phone(),
                    customer_whatsapp=generate_qatar_phone(),
                    customer_address=f"Building {random.randint(1, 100)}, Street {random.randint(1, 50)}, {QATAR_ZONES[zone]}",
                    dl_zone=zone,
                    dl_building=random.randint(1, 100),
                    dl_street=random.randint(1, 50),
                    deadline_date=(datetime.now() + timedelta(days=random.randint(1, 7))).strftime('%Y-%m-%d')
                )

                orders.append(order)
                order_counter += 1

        self.stdout.write(f'  Created {len(orders)} orders')
        return orders

    def create_order_items(self, orders, products):
        """Create order items"""
        self.stdout.write('Creating order items...')
        from orders.models import OrderItem

        items_created = 0

        for order in orders:
            # Each order has 1-4 items
            num_items = random.randint(1, 4)
            order_products = random.sample(products, min(num_items, len(products)))

            for product in order_products:
                quantity = random.randint(1, 5)
                unit_price = Decimal(str(product.item_price))

                OrderItem.objects.create(
                    order=order,
                    product=product,
                    quantity=quantity,
                    unit_price=unit_price,
                    total_price=unit_price * quantity,
                    notes=random.choice(['', 'Gift wrap', 'Extra packaging', ''])
                )
                items_created += 1

        self.stdout.write(f'  Created {items_created} order items')

    def create_delivery_tasks(self, orders, drivers, businesses, pickup_locations):
        """Create delivery tasks"""
        self.stdout.write('Creating delivery tasks...')
        from delivery.models import DeliveryTask, DlAddressUpdate

        tasks_created = 0
        address_updates_created = 0

        # Only create tasks for orders that are published or beyond
        eligible_orders = [o for o in orders if o.order_status in ['publish', 'delivered', 'fulfilled']]

        for order in eligible_orders:
            driver = random.choice(drivers)
            business = order.business
            pickup = order.pickup_location

            # Create address update first
            zone = order.dl_zone
            lat, lon = QATAR_COORDS.get(zone, (25.2867, 51.5333))

            dl_address = DlAddressUpdate.objects.create(
                full_name=order.customer_name,
                mobile_no=order.customer_phone[:11],
                area_name=QATAR_ZONES.get(zone, 'Doha'),
                dl_zone=zone,
                dl_building=order.dl_building,
                dl_street=order.dl_street,
                dl_latitude=Decimal(str(lat + random.uniform(-0.005, 0.005))),
                dl_longitude=Decimal(str(lon + random.uniform(-0.005, 0.005))),
                dl_unit=str(random.randint(1, 20)) if random.random() > 0.5 else None,
                is_villa_compound=random.random() > 0.7,
                is_flat=random.random() > 0.5,
                dl_task_number=f"DLT{str(tasks_created + 1).zfill(6)}",
                order=order,
                time_slot=random.choice(['9AM-12PM', '12PM-3PM', '3PM-6PM', '6PM-9PM'])
            )
            address_updates_created += 1

            # Determine task status based on order status
            if order.order_status == 'delivered':
                task_status = 'delivered'
                task_status_dms = '2'
            elif order.order_status == 'fulfilled':
                task_status = 'delivered'
                task_status_dms = '2'
            else:
                task_status = random.choice(['pending', 'publish_to_dms', 'in_transit'])
                task_status_dms = random.choice(['0', '1', '4', '7'])

            delivery_task = DeliveryTask.objects.create(
                dl_task_publish=True,
                dl_task_number=dl_address.dl_task_number,
                dl_task_number_dms=f"DMS{str(tasks_created + 1).zfill(6)}",
                dl_task_description=f"Delivery to {order.customer_name} in {QATAR_ZONES.get(zone, 'Doha')}",
                dl_task_status_client='for_review' if task_status == 'pending' else '2' if task_status == 'delivered' else '0',
                dl_task_status=task_status,
                dl_task_status_dms=task_status_dms,
                order=order,
                dl_address_update=dl_address,
                driver=driver,
                business=business,
                pickup_location=pickup,
                dl_waight=random.randint(1, 10),
                dl_category=random.choice(['Food', 'Regular', 'Electronics', 'Others']),
                dl_speed=random.choice(['Normal', 'Same Day', 'On Demand']),
                dl_price=order.dl_amount,
                driver_earnings=Decimal(str(random.randint(10, 30))) if task_status == 'delivered' else None,
                company_commission=Decimal(str(random.randint(5, 15))) if task_status == 'delivered' else None,
                cod_collected=task_status == 'delivered' and order.cod_amount > 0,
                cod_collected_amount=Decimal(str(order.cod_amount)) if task_status == 'delivered' else Decimal('0'),
                completed_at=timezone.now() - timedelta(hours=random.randint(1, 72)) if task_status == 'delivered' else None
            )
            tasks_created += 1

        self.stdout.write(f'  Created {tasks_created} delivery tasks and {address_updates_created} address updates')
