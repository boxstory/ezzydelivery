import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ezzydelivery.settings')
django.setup()

from django.template import Template, Context
from product.models import Product
from core.templatetags.custom_filters import safe_image_url

p = Product.objects.first()

# Test 1: Direct field access
print("="*60)
print("TEST 1: Direct Field Access")
print("="*60)
print(f"product.product_image: {p.product_image}")
print(f"product.product_image.url: {p.product_image.url if p.product_image else 'None'}")

# Test 2: Template filter
print("\n" + "="*60)
print("TEST 2: Template Filter")
print("="*60)
print(f"safe_image_url result: {safe_image_url(p.product_image)}")

# Test 3: Template rendering
print("\n" + "="*60)
print("TEST 3: Template Rendering")
print("="*60)

template_string = """
{% load custom_filters %}
<img src="{{ product.product_image|safe_image_url }}" alt="test">
"""

template = Template(template_string)
context = Context({'product': p})
rendered = template.render(context)
print(f"Rendered HTML: {rendered.strip()}")

# Test 4: Check if template tag is loaded
print("\n" + "="*60)
print("TEST 4: Check Template Tag Registration")
print("="*60)
from django.template import engines
from django.template.backends.django import DjangoTemplates

django_engine = engines['django']
print(f"Template engine: {type(django_engine)}")
print(f"Libraries: {list(django_engine.engine.template_libraries.keys())[:10]}")

# Test 5: Multiple products
print("\n" + "="*60)
print("TEST 5: Sample Products and Their Images")
print("="*60)
for product in Product.objects.all()[:5]:
    url = safe_image_url(product.product_image)
    print(f"{product.item_name}: {url}")
