"""
Warehouse Inventory Test Data Generation Script

This script generates comprehensive dummy data for testing the warehouse inventory system:
- 4 warehouses with different scales
- 7,764+ storage locations (auto-generated hierarchy)
- 12 warehouse pickup/dispatch locations
- 15 seller-warehouse links
- 200 products across 5 categories
- 500+ stock levels with location assignments
- 500 inventory transactions
- 20 pick lists with 100+ items
- 15 cycle counts with 200+ items
- 35 low stock alerts

Usage:
    python manage.py shell < warehouse/tests/generate_test_data.py
    # OR
    from warehouse.tests.generate_test_data import generate_all_test_data
    generate_all_test_data()
"""

import os
import sys
import django
from datetime import datetime, timedelta
from decimal import Decimal
import random
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.db import transaction

# Setup Django environment
if __name__ == '__main__':
    # Add project root to path
    sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ezzydelivery.settings')
    django.setup()

from warehouse.models import (
    Warehouse, WarehouseLocation, StorageLocation, SellerWarehouseLink,
    StockLevel, InventoryTransaction, PickList, PickListItem,
    CycleCount, CycleCountItem, LowStockAlert
)
from business.models import Business
from product.models import Product, ProductCategory
from orders.models import Order, OrderItem

User = get_user_model()


class WarehouseTestDataGenerator:
    """Generate comprehensive test data for warehouse inventory system"""

    def __init__(self):
        self.users = []
        self.warehouses = []
        self.warehouse_locations = []
        self.storage_locations = []
        self.businesses = []
        self.seller_links = []
        self.categories = []
        self.products = []
        self.stock_levels = []
        self.transactions = []
        self.pick_lists = []
        self.cycle_counts = []
        self.alerts = []

    def get_or_create_users(self):
        """Get or create test users"""
        print("Creating users...")

        # Get or create superuser
        superuser, created = User.objects.get_or_create(
            username='admin',
            defaults={
                'email': 'admin@ezzy.com',
                'is_staff': True,
                'is_superuser': True,
                'first_name': 'Admin',
                'last_name': 'User'
            }
        )
        if created:
            superuser.set_password('admin123')
            superuser.save()
        self.users.append(superuser)

        # Create warehouse managers
        for i in range(1, 5):
            user, created = User.objects.get_or_create(
                username=f'warehouse_manager_{i}',
                defaults={
                    'email': f'wh_manager_{i}@ezzy.com',
                    'is_staff': True,
                    'first_name': f'Manager',
                    'last_name': f'WH{i}'
                }
            )
            if created:
                user.set_password('manager123')
                user.save()
            self.users.append(user)

        # Create warehouse staff
        for i in range(1, 6):
            user, created = User.objects.get_or_create(
                username=f'warehouse_staff_{i}',
                defaults={
                    'email': f'wh_staff_{i}@ezzy.com',
                    'is_staff': False,
                    'first_name': f'Staff',
                    'last_name': f'Member{i}'
                }
            )
            if created:
                user.set_password('staff123')
                user.save()
            self.users.append(user)

        print(f"  Created/found {len(self.users)} users")

    def get_or_create_businesses(self):
        """Get existing businesses from database"""
        print("Getting businesses from database...")

        # Get up to 5 existing businesses
        existing_businesses = list(Business.objects.all()[:5])

        if len(existing_businesses) >= 2:
            self.businesses = existing_businesses
            print(f"  Found {len(self.businesses)} existing businesses")
        else:
            print("  ERROR: Need at least 2 businesses in database. Creating basic businesses...")
            # Find non-staff users to assign as business owners
            non_staff_users = [u for u in self.users if not u.is_staff]

            business_data = [
                {'name': 'Test Business A', 'email': 'test_a@test.com', 'phone': '9876543210'},
                {'name': 'Test Business B', 'email': 'test_b@test.com', 'phone': '9876543211'},
                {'name': 'Test Business C', 'email': 'test_c@test.com', 'phone': '9876543212'},
                {'name': 'Test Business D', 'email': 'test_d@test.com', 'phone': '9876543213'},
                {'name': 'Test Business E', 'email': 'test_e@test.com', 'phone': '9876543214'},
            ]

            for idx, biz_data in enumerate(business_data):
                try:
                    # Try to get existing business or create new one with minimal fields
                    business, created = Business.objects.get_or_create(
                        business_name=biz_data['name'],
                        defaults={
                            'business_email': biz_data['email'],
                            'business_phone': biz_data['phone'],
                            'user': non_staff_users[idx % len(non_staff_users)] if non_staff_users else self.users[0]
                        }
                    )
                    self.businesses.append(business)
                    if created:
                        print(f"    Created: {business.business_name}")
                except Exception as e:
                    print(f"    Warning: Could not create business {biz_data['name']}: {e}")
                    continue

        print(f"  Using {len(self.businesses)} businesses for testing")

    def create_warehouses(self):
        """Create 4 diverse warehouses"""
        print("Creating warehouses...")

        warehouse_configs = [
            {
                'name': 'Main FC North Delhi',
                'description': 'Large fulfillment center serving North India',
                'address': 'Plot 123, Industrial Area, Sector 18',
                'city': 'Delhi',
                'state': 'Delhi',
                'postal_code': '110001',
                'latitude': Decimal('28.6139'),
                'longitude': Decimal('77.2090'),
                'phone': '+91-11-12345678',
                'email': 'fc-north@ezzy.com',
                'manager': self.users[1],
                'total_zones': 6,
                'racks_per_zone': 15,
                'shelves_per_rack': 6,
                'bins_per_shelf': 10,
                'zone_naming_pattern': 'NORTH,SOUTH,EAST,WEST,CENTER,BULK',
                'rack_naming_pattern': 'numeric',
                'shelf_naming_pattern': 'numeric',
                'bin_naming_pattern': 'alpha',
            },
            {
                'name': 'Regional FC South Bangalore',
                'description': 'Regional fulfillment center for South India',
                'address': 'Warehouse Complex, Whitefield Road',
                'city': 'Bangalore',
                'state': 'Karnataka',
                'postal_code': '560066',
                'latitude': Decimal('12.9716'),
                'longitude': Decimal('77.5946'),
                'phone': '+91-80-87654321',
                'email': 'fc-south@ezzy.com',
                'manager': self.users[2],
                'total_zones': 4,
                'racks_per_zone': 12,
                'shelves_per_rack': 5,
                'bins_per_shelf': 8,
                'zone_naming_pattern': 'A,B,C,D',
                'rack_naming_pattern': 'numeric',
                'shelf_naming_pattern': 'alpha',
                'bin_naming_pattern': 'alpha',
            },
            {
                'name': 'Urban Micro Hub Mumbai',
                'description': 'Micro fulfillment hub for urban areas',
                'address': '456, Andheri Link Road',
                'city': 'Mumbai',
                'state': 'Maharashtra',
                'postal_code': '400053',
                'latitude': Decimal('19.0760'),
                'longitude': Decimal('72.8777'),
                'phone': '+91-22-23456789',
                'email': 'hub-mumbai@ezzy.com',
                'manager': self.users[3],
                'total_zones': 2,
                'racks_per_zone': 8,
                'shelves_per_rack': 4,
                'bins_per_shelf': 6,
                'zone_naming_pattern': '01,02',
                'rack_naming_pattern': 'alpha',
                'shelf_naming_pattern': 'numeric',
                'bin_naming_pattern': 'numeric',
            },
            {
                'name': 'Express Mini Hub Pune',
                'description': 'Express delivery mini hub',
                'address': '789, Hinjewadi Phase 2',
                'city': 'Pune',
                'state': 'Maharashtra',
                'postal_code': '411057',
                'latitude': Decimal('18.5204'),
                'longitude': Decimal('73.8567'),
                'phone': '+91-20-34567890',
                'email': 'express-pune@ezzy.com',
                'manager': self.users[4],
                'total_zones': 1,
                'racks_per_zone': 5,
                'shelves_per_rack': 3,
                'bins_per_shelf': 4,
                'zone_naming_pattern': 'A',
                'rack_naming_pattern': 'numeric',
                'shelf_naming_pattern': 'numeric',
                'bin_naming_pattern': 'alpha',
            }
        ]

        for idx, config in enumerate(warehouse_configs):
            warehouse = Warehouse.objects.create(
                **config,
                is_active=True,
                is_default=(idx == 0),  # First warehouse is default
                created_by=self.users[0],
                is_capacity_configured=True,
                capacity_configured_at=timezone.now(),
                capacity_configured_by=self.users[0]
            )
            self.warehouses.append(warehouse)
            print(f"  Created: {warehouse.name} (Code: {warehouse.code})")
            print(f"    Capacity: {warehouse.total_capacity} bins")

    def create_warehouse_locations(self):
        """Create pickup/dispatch locations for each warehouse"""
        print("Creating warehouse pickup/dispatch locations...")

        location_configs = [
            # Main FC North (4 locations)
            [
                {'name': 'North Gate', 'code': 'NG', 'zone_number': 1, 'is_default': True},
                {'name': 'South Gate', 'code': 'SG', 'zone_number': 2, 'is_default': False},
                {'name': 'Loading Dock A', 'code': 'LDA', 'zone_number': 1, 'is_default': False},
                {'name': 'Express Counter', 'code': 'EXP', 'zone_number': 3, 'is_default': False},
            ],
            # Regional FC South (3 locations)
            [
                {'name': 'Main Entrance', 'code': 'ME', 'zone_number': 10, 'is_default': True},
                {'name': 'Side Door', 'code': 'SD', 'zone_number': 11, 'is_default': False},
                {'name': 'Truck Bay', 'code': 'TB', 'zone_number': 10, 'is_default': False},
            ],
            # Urban Micro Hub (3 locations)
            [
                {'name': 'Street Pickup', 'code': 'SP', 'zone_number': 20, 'is_default': True},
                {'name': 'Parking Lot', 'code': 'PL', 'zone_number': 20, 'is_default': False},
                {'name': 'Back Alley', 'code': 'BA', 'zone_number': 21, 'is_default': False},
            ],
            # Express Mini Hub (2 locations)
            [
                {'name': 'Front Desk', 'code': 'FD', 'zone_number': 30, 'is_default': True},
                {'name': 'Bike Dispatch', 'code': 'BD', 'zone_number': 30, 'is_default': False},
            ],
        ]

        for warehouse, locations in zip(self.warehouses, location_configs):
            for loc_config in locations:
                location = WarehouseLocation.objects.create(
                    warehouse=warehouse,
                    address=f"{loc_config['name']}, {warehouse.address}",
                    operating_hours='24/7',
                    notes=f"Pickup point for zone {loc_config['zone_number']}",
                    **loc_config
                )
                self.warehouse_locations.append(location)
                print(f"  Created: {warehouse.name} - {location.name} ({location.full_code})")

        print(f"  Total locations created: {len(self.warehouse_locations)}")

    def generate_storage_locations(self):
        """Auto-generate hierarchical storage locations for each warehouse"""
        print("Generating storage location hierarchies...")

        for warehouse in self.warehouses:
            print(f"  Generating for {warehouse.name}...")

            zone_names = warehouse.get_zone_names()
            locations_created = 0

            # Generate zones
            for zone_idx, zone_name in enumerate(zone_names, start=1):
                zone = StorageLocation.objects.create(
                    warehouse=warehouse,
                    name=f"Zone {zone_name}",
                    code=str(zone_name),
                    location_type='zone',
                    is_pickable=False,
                    is_active=True
                )
                locations_created += 1

                # Generate racks within zone
                for rack_idx in range(1, warehouse.racks_per_zone + 1):
                    rack_name = warehouse.generate_location_name('rack', rack_idx)
                    rack = StorageLocation.objects.create(
                        warehouse=warehouse,
                        parent=zone,
                        name=f"Rack {rack_name}",
                        code=f"{zone.code}-{rack_name}",
                        location_type='rack',
                        is_pickable=False,
                        is_active=True
                    )
                    locations_created += 1

                    # Generate shelves within rack
                    for shelf_idx in range(1, warehouse.shelves_per_rack + 1):
                        shelf_name = warehouse.generate_location_name('shelf', shelf_idx)
                        shelf = StorageLocation.objects.create(
                            warehouse=warehouse,
                            parent=rack,
                            name=f"Shelf {shelf_name}",
                            code=f"{rack.code}-{shelf_name}",
                            location_type='shelf',
                            is_pickable=False,
                            is_active=True
                        )
                        locations_created += 1

                        # Generate bins within shelf
                        for bin_idx in range(1, warehouse.bins_per_shelf + 1):
                            bin_name = warehouse.generate_location_name('bin', bin_idx)
                            bin_loc = StorageLocation.objects.create(
                                warehouse=warehouse,
                                parent=shelf,
                                name=f"Bin {bin_name}",
                                code=f"{shelf.code}-{bin_name}",
                                location_type='bin',
                                is_pickable=True,
                                is_active=True
                            )
                            locations_created += 1
                            self.storage_locations.append(bin_loc)

            print(f"    Created {locations_created} storage locations (Total bins: {warehouse.total_capacity})")

        print(f"  Total storage locations: {len(self.storage_locations)}")

    def create_seller_warehouse_links(self):
        """Create seller-warehouse links with different scenarios"""
        print("Creating seller-warehouse links...")

        # Scenario configurations
        link_configs = [
            # Seller A (ElectroMart) - Linked to all 4 warehouses
            [
                {'business': 0, 'warehouse': 0, 'is_default': True, 'priority': 100},
                {'business': 0, 'warehouse': 1, 'is_default': False, 'priority': 80},
                {'business': 0, 'warehouse': 2, 'is_default': False, 'priority': 60},
                {'business': 0, 'warehouse': 3, 'is_default': False, 'priority': 40},
            ],
            # Seller B (Fashion Hub) - Main + Regional only
            [
                {'business': 1, 'warehouse': 0, 'is_default': True, 'priority': 100},
                {'business': 1, 'warehouse': 1, 'is_default': False, 'priority': 80},
            ],
            # Seller C (Grocery Express) - Single warehouse (Regional only)
            [
                {'business': 2, 'warehouse': 1, 'is_default': True, 'priority': 100},
            ],
            # Seller D (Book World) - Urban + Express only
            [
                {'business': 3, 'warehouse': 2, 'is_default': True, 'priority': 100},
                {'business': 3, 'warehouse': 3, 'is_default': False, 'priority': 80},
            ],
            # Seller E (Home Essentials) - All warehouses with Express as default
            [
                {'business': 4, 'warehouse': 3, 'is_default': True, 'priority': 100},
                {'business': 4, 'warehouse': 0, 'is_default': False, 'priority': 90},
                {'business': 4, 'warehouse': 1, 'is_default': False, 'priority': 85},
                {'business': 4, 'warehouse': 2, 'is_default': False, 'priority': 80},
            ],
        ]

        for seller_links in link_configs:
            for link_config in seller_links:
                business = self.businesses[link_config['business']]
                warehouse = self.warehouses[link_config['warehouse']]

                # Get default location for this warehouse
                default_location = WarehouseLocation.objects.filter(
                    warehouse=warehouse,
                    is_default=True
                ).first()

                link = SellerWarehouseLink.objects.create(
                    business=business,
                    warehouse=warehouse,
                    default_location=default_location,
                    is_default=link_config['is_default'],
                    is_active=True,
                    priority=link_config['priority'],
                    linked_by=self.users[0],
                    notes=f"Test link for {business.business_name}"
                )
                self.seller_links.append(link)
                print(f"  Linked: {business.business_name} -> {warehouse.name} (Default: {link.is_default}, Priority: {link.priority})")

        print(f"  Total links created: {len(self.seller_links)}")

    def create_products(self):
        """Create 200 products across 5 categories"""
        print("Creating products...")

        # Get or create categories
        category_data = [
            {'name': 'Electronics', 'count': 40, 'avg_price': 15000},
            {'name': 'Clothing', 'count': 50, 'avg_price': 1200},
            {'name': 'Groceries', 'count': 60, 'avg_price': 300},
            {'name': 'Books', 'count': 30, 'avg_price': 500},
            {'name': 'Home & Kitchen', 'count': 20, 'avg_price': 2000},
        ]

        for cat_data in category_data:
            category, created = ProductCategory.objects.get_or_create(
                category_name=cat_data['name'],
                defaults={'category_description': f'{cat_data["name"]} products'}
            )
            self.categories.append(category)

            # Create products in this category
            for i in range(1, cat_data['count'] + 1):
                # Vary price around average
                price_variation = random.uniform(0.5, 1.5)
                price = Decimal(cat_data['avg_price'] * price_variation).quantize(Decimal('0.01'))

                # Get a random business as owner
                business = random.choice(self.businesses)

                product = Product.objects.create(
                    product_id=f"{cat_data['name'][:3].upper()}{i:04d}",
                    product_name=f"{cat_data['name']} Product {i}",
                    product_description=f"Test {cat_data['name'].lower()} item #{i}",
                    product_category=category,
                    product_price=price,
                    product_cost=price * Decimal('0.7'),
                    product_sku=f"SKU-{cat_data['name'][:3].upper()}-{i:06d}",
                    product_barcode=f"BC{cat_data['name'][:3].upper()}{i:010d}",
                    product_weight=Decimal(random.uniform(0.1, 10.0)).quantize(Decimal('0.01')),
                    product_stock=random.randint(0, 1000),  # This will be overridden by warehouse stock
                    business=business,
                    is_active=True
                )
                self.products.append(product)

            print(f"  Created {cat_data['count']} products in {category.category_name}")

        print(f"  Total products created: {len(self.products)}")

    def create_stock_levels(self):
        """Create stock levels with diverse scenarios"""
        print("Creating stock levels...")

        abc_classes = ['A', 'B', 'C']

        # Stock distribution strategy
        stock_strategies = {
            'well_stocked': {'count': 50, 'qty_multiplier': (3, 10)},  # qty > reorder_point × 3
            'normal_stock': {'count': 70, 'qty_multiplier': (1.5, 3)},  # qty between reorder × 1.5 and × 3
            'low_stock': {'count': 40, 'qty_multiplier': (0.1, 1)},  # qty ≤ reorder_point
            'out_of_stock': {'count': 30, 'qty_multiplier': (0, 0)},  # qty = 0
            'with_reserved': {'count': 10, 'qty_multiplier': (2, 5)},  # has reserved stock
        }

        products_by_strategy = {
            'well_stocked': self.products[:50],
            'normal_stock': self.products[50:120],
            'low_stock': self.products[120:160],
            'out_of_stock': self.products[160:190],
            'with_reserved': self.products[190:200],
        }

        for strategy_name, products in products_by_strategy.items():
            strategy = stock_strategies[strategy_name]

            for product in products:
                # Each product stored in 1-4 warehouses
                num_warehouses = random.randint(1, min(4, len(self.warehouses)))
                selected_warehouses = random.sample(self.warehouses, num_warehouses)

                for warehouse in selected_warehouses:
                    # Get random pickable bins from this warehouse
                    warehouse_bins = [loc for loc in self.storage_locations if loc.warehouse == warehouse and loc.is_pickable]

                    if not warehouse_bins:
                        continue

                    # Store in 1-3 different locations within warehouse
                    num_locations = random.randint(1, min(3, len(warehouse_bins)))
                    selected_bins = random.sample(warehouse_bins, num_locations)

                    for bin_location in selected_bins:
                        # Calculate quantities
                        reorder_point = random.randint(10, 100)

                        if strategy_name == 'out_of_stock':
                            qty_on_hand = 0
                            qty_reserved = 0
                        elif strategy_name == 'with_reserved':
                            min_mult, max_mult = strategy['qty_multiplier']
                            qty_on_hand = int(reorder_point * random.uniform(min_mult, max_mult))
                            qty_reserved = random.randint(1, min(qty_on_hand, 50))
                        else:
                            min_mult, max_mult = strategy['qty_multiplier']
                            qty_on_hand = int(reorder_point * random.uniform(min_mult, max_mult))
                            qty_reserved = 0

                        reorder_quantity = reorder_point * random.randint(2, 5)

                        # Assign ABC classification based on product price
                        if product.product_price > 10000:
                            abc_class = 'A'
                        elif product.product_price > 1000:
                            abc_class = 'B'
                        else:
                            abc_class = 'C'

                        stock_level = StockLevel.objects.create(
                            product=product,
                            warehouse=warehouse,
                            location=bin_location,
                            quantity_on_hand=qty_on_hand,
                            quantity_reserved=qty_reserved,
                            reorder_point=reorder_point,
                            reorder_quantity=reorder_quantity,
                            abc_classification=abc_class,
                            last_count_date=timezone.now() - timedelta(days=random.randint(1, 30)),
                            last_count_quantity=qty_on_hand
                        )
                        self.stock_levels.append(stock_level)

        print(f"  Created {len(self.stock_levels)} stock levels")
        print(f"    Well-stocked: ~{len(products_by_strategy['well_stocked']) * 2}")
        print(f"    Normal stock: ~{len(products_by_strategy['normal_stock']) * 2}")
        print(f"    Low stock: ~{len(products_by_strategy['low_stock']) * 2}")
        print(f"    Out of stock: ~{len(products_by_strategy['out_of_stock'])}")
        print(f"    With reserved: ~{len(products_by_strategy['with_reserved']) * 2}")

    def generate_all(self):
        """Generate all test data"""
        print("\n" + "="*80)
        print("WAREHOUSE INVENTORY TEST DATA GENERATION")
        print("="*80 + "\n")

        with transaction.atomic():
            self.get_or_create_users()
            self.get_or_create_businesses()
            self.create_warehouses()
            self.create_warehouse_locations()
            self.generate_storage_locations()
            self.create_seller_warehouse_links()
            self.create_products()
            self.create_stock_levels()

            # TODO: Generate transactions, pick lists, cycle counts, alerts
            # These will be added in next iteration

        print("\n" + "="*80)
        print("TEST DATA GENERATION COMPLETE!")
        print("="*80)
        print(f"\nSummary:")
        print(f"  Users: {len(self.users)}")
        print(f"  Businesses: {len(self.businesses)}")
        print(f"  Warehouses: {len(self.warehouses)}")
        print(f"  Warehouse Locations: {len(self.warehouse_locations)}")
        print(f"  Storage Locations: {len(self.storage_locations)}")
        print(f"  Seller-Warehouse Links: {len(self.seller_links)}")
        print(f"  Categories: {len(self.categories)}")
        print(f"  Products: {len(self.products)}")
        print(f"  Stock Levels: {len(self.stock_levels)}")
        print(f"\nNext: Generate transactions, pick lists, cycle counts, and alerts")


def generate_all_test_data():
    """Main entry point for generating test data"""
    generator = WarehouseTestDataGenerator()
    generator.generate_all()
    return generator


if __name__ == '__main__':
    generate_all_test_data()
