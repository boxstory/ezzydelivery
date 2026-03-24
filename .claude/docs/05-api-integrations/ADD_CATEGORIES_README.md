# Add Product Categories

This guide explains how to add comprehensive product categories to your database.

## Method 1: Using Django Shell (Recommended)

1. Activate your virtual environment
2. Navigate to the project directory
3. Run the Django shell:
   ```bash
   python manage.py shell
   ```

4. Copy and paste the contents of `add_product_categories.py` into the shell, OR run:
   ```bash
   python manage.py shell < add_product_categories.py
   ```

## Method 2: Using Django Admin

1. Go to Django admin: http://127.0.0.1:8004/admin/
2. Navigate to "Product Category"
3. Add categories manually

## Categories to be Added

The script adds 60+ comprehensive categories including:

### Electronics & Tech
- Electronics, Mobile Phones, Computers & Laptops, Cameras, Audio, Smart Home, Gaming

### Fashion & Apparel
- Men's/Women's/Kids Fashion, Shoes, Bags, Watches, Jewelry

### Home & Living
- Furniture, Home Decor, Kitchen, Bedding, Appliances, Tools, Garden

### Beauty & Personal Care
- Beauty & Cosmetics, Skincare, Haircare, Fragrances, Personal Care

### Food & Beverages
- Groceries, Fresh Produce, Snacks, Beverages, Bakery, Dairy, Meat

### Health & Wellness
- Health Products, Vitamins, Medical Supplies, Fitness Equipment

### Sports & Outdoors
- Sports Equipment, Outdoor Recreation, Cycling, Team Sports

### Books & Media
- Books, Stationery, Art & Craft, Music & Movies

### Toys & Baby
- Toys & Games, Baby Products, Baby Food, Diapers

### Automotive
- Automotive Parts, Car Electronics, Car Care, Motorcycle

### Pet Supplies
- Pet Supplies, Pet Food, Pet Accessories

### Others
- Industrial, Services, Gift Cards, Other

## After Adding Categories

The product add form will now show all these categories in the dropdown with:
- ✅ Wider form layout
- ✅ Better dropdown height (shows more options)
- ✅ Search functionality (via Select2)
- ✅ Placeholder text
- ✅ Clear button to deselect

## Verification

To verify categories were added:
```bash
python manage.py shell
>>> from product.models import ProductCategory
>>> ProductCategory.objects.count()
>>> ProductCategory.objects.values_list('category_name', flat=True)
```
