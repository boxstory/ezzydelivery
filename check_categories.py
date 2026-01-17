"""
Quick check script to see what categories are in the database
Run with: python manage.py shell -c "exec(open('check_categories.py').read())"
"""
import os
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ezzydelivery.settings')
django.setup()

from product.models import ProductCategory, ColorVariant, UnitVariant

print("=" * 60)
print("DATABASE CHECK")
print("=" * 60)

# Check Product Categories
cat_count = ProductCategory.objects.count()
print(f"\n📦 PRODUCT CATEGORIES: {cat_count}")
if cat_count > 0:
    print("\nCategories:")
    for cat in ProductCategory.objects.all()[:20]:  # Show first 20
        print(f"  • {cat.category_name}")
    if cat_count > 20:
        print(f"  ... and {cat_count - 20} more")
else:
    print("  ⚠️  NO CATEGORIES FOUND!")
    print("  👉 Run ADD_CATEGORIES.bat to add categories")

# Check Color Variants
color_count = ColorVariant.objects.count()
print(f"\n🎨 COLOR VARIANTS: {color_count}")
if color_count > 0:
    colors = list(ColorVariant.objects.values_list('color_variant', flat=True)[:10])
    print(f"  Examples: {', '.join(colors)}")
else:
    print("  ⚠️  NO COLORS FOUND!")

# Check Unit Variants
unit_count = UnitVariant.objects.count()
print(f"\n📏 UNIT VARIANTS: {unit_count}")
if unit_count > 0:
    units = list(UnitVariant.objects.values_list('unit_variant', flat=True)[:10])
    print(f"  Examples: {', '.join(units)}")
else:
    print("  ⚠️  NO UNITS FOUND!")

print("\n" + "=" * 60)
