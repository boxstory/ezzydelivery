"""
Quick script to add more product categories to the database.
Run this with: python manage.py shell < add_product_categories.py
Or copy-paste into Django shell
"""

from product.models import ProductCategory

# Define comprehensive list of product categories
categories_data = [
    # Electronics & Tech
    {"name": "Electronics", "description": "Electronic devices and gadgets"},
    {"name": "Mobile Phones", "description": "Smartphones and mobile devices"},
    {"name": "Computers & Laptops", "description": "PCs, laptops, and accessories"},
    {"name": "Cameras & Photography", "description": "Cameras and photo equipment"},
    {"name": "Audio & Headphones", "description": "Speakers, headphones, and audio gear"},
    {"name": "Smart Home", "description": "Smart home devices and automation"},
    {"name": "Gaming", "description": "Gaming consoles and accessories"},

    # Fashion & Apparel
    {"name": "Men's Fashion", "description": "Clothing and accessories for men"},
    {"name": "Women's Fashion", "description": "Clothing and accessories for women"},
    {"name": "Kids Fashion", "description": "Children's clothing and accessories"},
    {"name": "Shoes & Footwear", "description": "All types of footwear"},
    {"name": "Bags & Luggage", "description": "Bags, backpacks, and luggage"},
    {"name": "Watches", "description": "Wristwatches and smartwatches"},
    {"name": "Jewelry & Accessories", "description": "Jewelry and fashion accessories"},

    # Home & Living
    {"name": "Furniture", "description": "Home and office furniture"},
    {"name": "Home Decor", "description": "Decorative items for home"},
    {"name": "Kitchen & Dining", "description": "Kitchenware and dining essentials"},
    {"name": "Bedding & Bath", "description": "Bedding, towels, and bath products"},
    {"name": "Home Appliances", "description": "Large and small appliances"},
    {"name": "Tools & Hardware", "description": "Tools and hardware supplies"},
    {"name": "Garden & Outdoor", "description": "Outdoor and gardening products"},

    # Beauty & Personal Care
    {"name": "Beauty & Cosmetics", "description": "Makeup and beauty products"},
    {"name": "Skincare", "description": "Skincare and facial products"},
    {"name": "Haircare", "description": "Hair products and tools"},
    {"name": "Fragrances", "description": "Perfumes and colognes"},
    {"name": "Personal Care", "description": "Personal hygiene products"},

    # Food & Beverages
    {"name": "Groceries", "description": "Daily grocery items"},
    {"name": "Fresh Produce", "description": "Fresh fruits and vegetables"},
    {"name": "Snacks & Sweets", "description": "Snacks, chips, and sweets"},
    {"name": "Beverages", "description": "Drinks and beverages"},
    {"name": "Bakery", "description": "Baked goods and bread"},
    {"name": "Dairy & Eggs", "description": "Dairy products and eggs"},
    {"name": "Meat & Seafood", "description": "Fresh meat and seafood"},

    # Health & Wellness
    {"name": "Health & Wellness", "description": "Health and wellness products"},
    {"name": "Vitamins & Supplements", "description": "Vitamins and dietary supplements"},
    {"name": "Medical Supplies", "description": "Medical and first aid supplies"},
    {"name": "Fitness Equipment", "description": "Exercise and fitness gear"},

    # Sports & Outdoors
    {"name": "Sports Equipment", "description": "Sports gear and equipment"},
    {"name": "Outdoor Recreation", "description": "Camping and outdoor gear"},
    {"name": "Cycling", "description": "Bicycles and cycling accessories"},
    {"name": "Team Sports", "description": "Equipment for team sports"},

    # Books & Media
    {"name": "Books", "description": "Books and reading materials"},
    {"name": "Stationery & Office", "description": "Office supplies and stationery"},
    {"name": "Art & Craft", "description": "Art supplies and craft materials"},
    {"name": "Music & Movies", "description": "Music CDs, movies, and media"},

    # Toys & Baby
    {"name": "Toys & Games", "description": "Toys and games for all ages"},
    {"name": "Baby Products", "description": "Baby care and nursery items"},
    {"name": "Baby Food", "description": "Baby food and formula"},
    {"name": "Diapers & Wipes", "description": "Diapers and baby wipes"},

    # Automotive
    {"name": "Automotive", "description": "Car parts and accessories"},
    {"name": "Car Electronics", "description": "Car audio and electronics"},
    {"name": "Car Care", "description": "Car cleaning and maintenance"},
    {"name": "Motorcycle", "description": "Motorcycle parts and gear"},

    # Pet Supplies
    {"name": "Pet Supplies", "description": "Pet food and accessories"},
    {"name": "Pet Food", "description": "Food for pets"},
    {"name": "Pet Accessories", "description": "Pet toys and accessories"},

    # Others
    {"name": "Industrial & Scientific", "description": "Industrial equipment and supplies"},
    {"name": "Services", "description": "Service-based offerings"},
    {"name": "Gift Cards", "description": "Gift cards and vouchers"},
    {"name": "Other", "description": "Miscellaneous products"},
]

# Add categories to database
print("Adding product categories...")
added_count = 0
skipped_count = 0

for cat_data in categories_data:
    # Check if category already exists
    existing = ProductCategory.objects.filter(category_name=cat_data["name"]).first()

    if existing:
        print(f"  ⏭ Skipped: {cat_data['name']} (already exists)")
        skipped_count += 1
    else:
        ProductCategory.objects.create(
            category_name=cat_data["name"],
            discription=cat_data["description"]
        )
        print(f"  ✓ Added: {cat_data['name']}")
        added_count += 1

print(f"\n✅ Done! Added {added_count} new categories, skipped {skipped_count} existing ones.")
print(f"Total categories in database: {ProductCategory.objects.count()}")
