"""
Simple script to create fulfillment stores for existing businesses.
Run with: python create_fulfillment_stores_script.py
"""
import os
import django
from django.utils import timezone

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ezzydelivery.settings')
django.setup()

from business.models import Business, PickupLocation

print("=" * 60)
print("CREATE FULFILLMENT STORES FOR EXISTING BUSINESSES")
print("=" * 60)
print()

# Find businesses with fulfillment enabled
businesses_with_fulfillment = Business.objects.filter(
    fulfillment_service_enabled=True
)

total_businesses = businesses_with_fulfillment.count()
print(f"Found {total_businesses} businesses with fulfillment service enabled")
print()

if total_businesses == 0:
    print("⚠️  No businesses found with fulfillment service enabled")
    print()
    print("To enable fulfillment service:")
    print("1. Go to Django Admin: http://127.0.0.1:8004/admin/")
    print("2. Navigate to Business → Businesses")
    print("3. Edit a business")
    print("4. Check 'Fulfillment service enabled'")
    print("5. Save")
    print()
    print("Then run this script again.")
    input("\nPress Enter to exit...")
    exit()

created_count = 0
skipped_count = 0

print("Processing businesses...")
print("-" * 60)

for business in businesses_with_fulfillment:
    # Check if fulfillment store already exists
    fulfillment_store_exists = PickupLocation.objects.filter(
        business=business,
        pickup_location_title__icontains="fulfillment"
    ).exists()

    if fulfillment_store_exists:
        print(f"  ⏭  Skipped: {business.business_name} (ID: {business.business_id})")
        print(f"      Reason: Fulfillment store already exists")
        skipped_count += 1
    else:
        try:
            # Create the fulfillment store
            PickupLocation.objects.create(
                business=business,
                pickup_location_title="Fulfillment Store",
                locality="EzzyDelivery Fulfillment Center",
                pickup_status='active',
            )

            # Update fulfillment_activated_at if not set
            if not business.fulfillment_activated_at:
                business.fulfillment_activated_at = timezone.now()
                business.save(update_fields=['fulfillment_activated_at'])

            print(f"  ✓  Created: {business.business_name} (ID: {business.business_id})")
            created_count += 1
        except Exception as e:
            print(f"  ✗  Error: {business.business_name} (ID: {business.business_id})")
            print(f"      Error: {e}")

print("-" * 60)
print()
print("=" * 60)
print("COMPLETE!")
print("=" * 60)
print(f"✅ Created:  {created_count} fulfillment stores")
print(f"⏭  Skipped:  {skipped_count} existing stores")
print(f"📊 Total:    {total_businesses} businesses with fulfillment enabled")
print("=" * 60)
print()

if created_count > 0:
    print("🎉 SUCCESS! Fulfillment stores have been created.")
    print()
    print("These stores will now appear in:")
    print("  • Add Order form → Pickup Location dropdown")
    print("  • Business Dashboard → Stores List")
    print("  • Order management pages")
    print()
else:
    print("ℹ️  All businesses already have fulfillment stores.")
    print()

print("Next steps:")
print("1. Restart your Django development server")
print("2. Go to Add Order page")
print("3. Check Pickup Location dropdown")
print("4. You should see 'Fulfillment Store' option")
print()

input("Press Enter to exit...")
