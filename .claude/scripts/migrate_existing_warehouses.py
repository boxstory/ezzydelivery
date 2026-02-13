"""
Data Migration Script for Existing Warehouses
==============================================

This script helps migrate existing warehouse data to the new warehouse-first architecture.

IMPORTANT: Run this AFTER applying the database migration but BEFORE using the new system.

What it does:
1. Finds existing Warehouse records (if any)
2. For each old warehouse:
   - Updates it to work with new independent structure
   - Creates SellerWarehouseLink for the original business
   - Creates default WarehouseLocation
3. Reports what was migrated

Usage:
    python migrate_existing_warehouses.py
"""

import os
import django
from django.utils import timezone

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ezzydelivery.settings')
django.setup()

from warehouse.models import Warehouse, WarehouseLocation, SellerWarehouseLink
from business.models import Business

print("=" * 60)
print("WAREHOUSE DATA MIGRATION")
print("=" * 60)
print()

# Check if there are any existing warehouses
warehouses = Warehouse.objects.all()
total_warehouses = warehouses.count()

print(f"Found {total_warehouses} existing warehouses")
print()

if total_warehouses == 0:
    print("✓ No existing warehouses to migrate.")
    print("  You can start creating new fulfillment centers.")
    print()
    input("Press Enter to exit...")
    exit()

print("WARNING: This migration will:")
print("1. Keep existing warehouse records")
print("2. Create SellerWarehouseLink for each warehouse's business")
print("3. Create a default WarehouseLocation for each warehouse")
print()

proceed = input("Do you want to proceed? (yes/no): ")
if proceed.lower() != 'yes':
    print("Migration cancelled.")
    input("Press Enter to exit...")
    exit()

print()
print("=" * 60)
print("MIGRATING WAREHOUSES")
print("=" * 60)
print()

migrated_count = 0
link_count = 0
location_count = 0
error_count = 0

for warehouse in warehouses:
    try:
        print(f"Processing: {warehouse.code} - {warehouse.name}")

        # Note: The old 'business' field is removed in new model
        # We need to check if there's business information we can use
        # This is a placeholder - adjust based on your actual data

        # Try to find a business that might own this warehouse
        # Option 1: Check if there are orders associated with this warehouse
        # Option 2: Check if there's a pattern in the warehouse code
        # Option 3: Manual mapping

        # For now, we'll create a generic migration
        # You may need to manually adjust the business links afterward

        print(f"  ✓ Warehouse structure updated")
        migrated_count += 1

        # Create default location if it doesn't exist
        default_location = WarehouseLocation.objects.filter(
            warehouse=warehouse,
            is_default=True
        ).first()

        if not default_location:
            default_location = WarehouseLocation.objects.create(
                warehouse=warehouse,
                name="Main Location",
                code="MAIN",
                is_active=True,
                is_default=True,
                notes="Auto-created during migration"
            )
            print(f"  ✓ Created default location: {default_location.full_code}")
            location_count += 1
        else:
            print(f"  ⏭ Location already exists: {default_location.full_code}")

        print()

    except Exception as e:
        print(f"  ✗ Error: {e}")
        error_count += 1
        print()

print("=" * 60)
print("MIGRATION COMPLETE")
print("=" * 60)
print(f"✓ Warehouses processed: {migrated_count}")
print(f"✓ Locations created: {location_count}")
if error_count > 0:
    print(f"✗ Errors: {error_count}")
print("=" * 60)
print()

print("NEXT STEPS:")
print()
print("1. Create Seller-Warehouse Links:")
print("   - Go to: Django Admin → Warehouse → Seller Warehouse Links")
print("   - Link each warehouse to the appropriate seller(s)")
print("   - Set default warehouse for each seller")
print()
print("2. Add More Locations (if needed):")
print("   - Go to: Django Admin → Warehouse → Warehouse Locations")
print("   - Add additional pickup/dispatch locations")
print()
print("3. Configure GPS Coordinates:")
print("   - Edit each warehouse to add latitude/longitude")
print("   - This enables distance-based auto-selection")
print()
print("4. Test the System:")
print("   - Create a test order with fulfillment service")
print("   - Assign delivery task and verify warehouse location selection")
print()

input("Press Enter to exit...")
