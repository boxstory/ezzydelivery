"""
Clear string default values from product images in database.
This fixes the issue where ImageFields have string defaults instead of actual files.
"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ezzydelivery.settings')
django.setup()

from product.models import Product

print("\n" + "="*70)
print("CLEARING STRING DEFAULT VALUES FROM PRODUCT IMAGES")
print("="*70)

# Find products with default string values
products_with_default_image = Product.objects.filter(
    product_image='business/product_images/product_image_default.jpg'
)

products_with_default_logo = Product.objects.filter(
    brand_logo='business/product_images/brand_logo_default.jpg'
)

print(f"\nProducts with default product_image string: {products_with_default_image.count()}")
print(f"Products with default brand_logo string: {products_with_default_logo.count()}")

# Clear the string defaults (set to empty string, which will evaluate to False)
updated_images = products_with_default_image.update(product_image='')
updated_logos = products_with_default_logo.update(brand_logo='')

print(f"\nUpdated {updated_images} product images")
print(f"Updated {updated_logos} brand logos")

print("\n" + "="*70)
print("VERIFICATION")
print("="*70)

# Verify
remaining_default_images = Product.objects.filter(
    product_image='business/product_images/product_image_default.jpg'
).count()

remaining_default_logos = Product.objects.filter(
    brand_logo='business/product_images/brand_logo_default.jpg'
).count()

print(f"\nRemaining products with default image string: {remaining_default_images}")
print(f"Remaining products with default logo string: {remaining_default_logos}")

if remaining_default_images == 0 and remaining_default_logos == 0:
    print("\n✓ SUCCESS! All string defaults cleared.")
    print("  The custom template filters will now show the default images.")
else:
    print("\n✗ WARNING: Some defaults still remain!")

print("\n" + "="*70 + "\n")
