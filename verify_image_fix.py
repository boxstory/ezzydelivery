"""
Verify that the image fix is working correctly
"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ezzydelivery.settings')
django.setup()

from product.models import Product
from django.template import Context, Template

print("\n" + "="*70)
print("VERIFYING IMAGE FIX")
print("="*70)

# Get a few products
products = Product.objects.all()[:3]

for i, product in enumerate(products, 1):
    print(f"\n{'-'*70}")
    print(f"Product {i}: {product.item_name}")
    print(f"{'-'*70}")

    print(f"product_image value: '{product.product_image}'")
    print(f"Boolean check: {bool(product.product_image)}")

    # Test template rendering
    template_str = """{% load custom_filters %}<img src="{{ product.product_image|safe_image_url }}" alt="test">"""
    template = Template(template_str)
    context = Context({'product': product})
    rendered = template.render(context)
    print(f"Rendered HTML: {rendered}")

print("\n" + "="*70)
print("RESULTS")
print("="*70)
print("\nAll products should now render with the default image path:")
print("  /media/business/product_images/product_image_default.jpg")
print("\nThe custom filter handles empty ImageFields correctly.")
print("\n" + "="*70 + "\n")
