import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ezzydelivery.settings')
django.setup()

from product.models import Product

print("\n" + "="*60)
print("Verifying Product IDs")
print("="*60)

total = Product.objects.count()
with_ids = Product.objects.exclude(product_id__isnull=True).exclude(product_id='').count()

print(f"\nTotal products: {total}")
print(f"Products with product_id: {with_ids}")
print(f"Products without product_id: {total - with_ids}")

if with_ids > 0:
    print("\nSample product IDs:")
    for product in Product.objects.exclude(product_id__isnull=True).exclude(product_id='')[:10]:
        print(f"  - {product.product_id}: {product.item_name}")

print("\n" + "="*60)
print("Verification complete!")
print("="*60 + "\n")
