"""
Quick check to see what image URLs are actually being rendered in the product cards.
This will help us diagnose the image loading issue.
"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ezzydelivery.settings')
django.setup()

from product.models import Product
from django.template import Context, Template
from core.templatetags.custom_filters import safe_image_url

print("\n" + "="*70)
print("IMAGE RENDERING DIAGNOSTIC")
print("="*70)

# Get first 3 products
products = Product.objects.select_related('business').all()[:3]

print(f"\nChecking {products.count()} products...")

for i, product in enumerate(products, 1):
    print(f"\n{'-'*70}")
    print(f"Product {i}: {product.item_name}")
    print(f"{'-'*70}")

    # Check product_image field
    print(f"product.product_image: {product.product_image}")
    print(f"Type: {type(product.product_image)}")

    if product.product_image:
        print(f"Has file: {bool(product.product_image)}")
        print(f"Name: {product.product_image.name if product.product_image else 'None'}")
        try:
            print(f"URL: {product.product_image.url}")
            print(f"Path exists: {product.product_image.storage.exists(product.product_image.name)}")
        except Exception as e:
            print(f"Error getting URL: {e}")

    # Check filter output
    filter_result = safe_image_url(product.product_image)
    print(f"\nFilter output: {filter_result}")

    # Simulate template rendering
    template_str = """{% load custom_filters %}<img src="{{ product.product_image|safe_image_url }}" alt="{{ product.item_name }}">"""
    template = Template(template_str)
    context = Context({'product': product})
    rendered = template.render(context)
    print(f"\nRendered HTML:\n{rendered}")

print("\n" + "="*70)
print("MEDIA SETTINGS")
print("="*70)

from django.conf import settings
print(f"MEDIA_URL: {settings.MEDIA_URL}")
print(f"MEDIA_ROOT: {settings.MEDIA_ROOT}")

# Check if default image exists
default_image_path = os.path.join(settings.MEDIA_ROOT, 'business', 'product_images', 'product_image_default.jpg')
print(f"\nDefault image path: {default_image_path}")
print(f"Default image exists: {os.path.exists(default_image_path)}")
if os.path.exists(default_image_path):
    print(f"Default image size: {os.path.getsize(default_image_path)} bytes")

print("\n" + "="*70 + "\n")
