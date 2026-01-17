"""
Deep dive into product image issue - check database values and file system
"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ezzydelivery.settings')
django.setup()

from product.models import Product
from django.conf import settings

print("\n" + "="*70)
print("PRODUCT IMAGE DATABASE ANALYSIS")
print("="*70)

products = Product.objects.all()[:10]

print(f"\nAnalyzing {products.count()} products...")

for i, product in enumerate(products, 1):
    print(f"\n{'-'*70}")
    print(f"Product {i}: {product.item_name} (ID: {product.pk})")
    print(f"{'-'*70}")

    # Raw database value
    print(f"product_image (raw): '{product.product_image}'")
    print(f"Type: {type(product.product_image)}")

    # Check if it's a string (shouldn't be)
    if isinstance(product.product_image, str):
        print("⚠️  WARNING: product_image is a STRING, not ImageFieldFile!")
        print("   This means the field contains a default string value instead of a file reference")

    # Check the actual value
    if product.product_image:
        print(f"Boolean check: True (has value)")
        print(f"Name attribute: '{product.product_image.name}'")

        # Full file path
        full_path = os.path.join(settings.MEDIA_ROOT, product.product_image.name)
        print(f"Full path: {full_path}")
        print(f"File exists: {os.path.exists(full_path)}")

        if os.path.exists(full_path):
            size = os.path.getsize(full_path)
            print(f"File size: {size} bytes")

        try:
            url = product.product_image.url
            print(f"URL: {url}")
        except Exception as e:
            print(f"❌ Error getting URL: {e}")
    else:
        print(f"Boolean check: False (empty)")

print("\n" + "="*70)
print("CHECKING FOR STRING DEFAULT VALUES IN MODEL")
print("="*70)

# Check the model field definition
from product.models import Product as ProductModel
product_image_field = ProductModel._meta.get_field('product_image')
print(f"\nField type: {type(product_image_field)}")
print(f"Default value: {product_image_field.default}")
print(f"Has default: {product_image_field.has_default()}")

if product_image_field.has_default():
    print(f"⚠️  WARNING: product_image field has a default value!")
    print(f"   Default: '{product_image_field.default}'")
    print(f"   This can cause issues with ImageField URL generation")

print("\n" + "="*70)
print("RECOMMENDATION")
print("="*70)

# Count products with default string value
products_with_default = Product.objects.filter(
    product_image='business/product_images/product_image_default.jpg'
).count()

print(f"\nProducts with default string value: {products_with_default}")

if products_with_default > 0:
    print("\n⚠️  PROBLEM FOUND:")
    print("   Products have string default values instead of actual uploaded images.")
    print("   Django ImageField doesn't work properly with string defaults.")
    print("\n✅ SOLUTION:")
    print("   1. Remove default value from Product model")
    print("   2. Set product_image to NULL/blank for products without images")
    print("   3. Handle missing images in the template with the custom filter")

print("\n" + "="*70 + "\n")
