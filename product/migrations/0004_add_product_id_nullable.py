# Migration to add product_id field as nullable first
from django.db import migrations, models
from collections import defaultdict


def generate_product_ids(apps, schema_editor):
    """
    Generate unique 6-digit product_ids for all products.
    Format: {4-digit-counter}{2-digit-business-code}
    """
    Product = apps.get_model('product', 'Product')

    business_counters = defaultdict(int)

    # Process all products ordered by creation date
    for product in Product.objects.select_related('business').order_by('created_at'):
        # Get last 2 digits from business_id
        if product.business and hasattr(product.business, 'business_id'):
            business_digits = ''.join(filter(str.isdigit, str(product.business.business_id)))
            business_suffix = business_digits[-2:].zfill(2) if business_digits else "00"
        else:
            business_suffix = "00"

        # Increment counter for this business
        business_counters[business_suffix] += 1
        counter = business_counters[business_suffix]

        # Generate 6-digit product_id
        product_id = f"{counter:04d}{business_suffix}"

        # Ensure uniqueness
        max_attempts = 9999
        attempts = 0
        while Product.objects.filter(product_id=product_id).exists() and attempts < max_attempts:
            business_counters[business_suffix] += 1
            counter = business_counters[business_suffix]
            if counter > 9999:
                counter = 1
            product_id = f"{counter:04d}{business_suffix}"
            attempts += 1

        # Update product
        product.product_id = product_id
        product.save(update_fields=['product_id'])


class Migration(migrations.Migration):

    dependencies = [
        ('product', '0003_product_barcode_product_product_barcode_idx'),
    ]

    operations = [
        # Step 1: Add field WITHOUT db_index (to avoid index creation issues)
        migrations.AddField(
            model_name='product',
            name='product_id',
            field=models.CharField(
                max_length=6,
                null=True,
                blank=True,
                db_index=False,  # Don't create index yet
                help_text='6-digit unique product identifier (last 2 digits from business code)'
            ),
        ),
        # Step 2: Generate unique IDs for all products
        migrations.RunPython(generate_product_ids, migrations.RunPython.noop),
        # Step 3: Add unique constraint (which creates an index automatically)
        migrations.AlterField(
            model_name='product',
            name='product_id',
            field=models.CharField(
                max_length=6,
                unique=True,
                editable=False,
                null=True,
                blank=True,
                db_index=False,  # Unique constraint creates its own index
                help_text='6-digit unique product identifier (last 2 digits from business code)'
            ),
        ),
    ]
