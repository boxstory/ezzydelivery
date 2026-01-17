# Product ID Migration Fix Instructions

The product_id migration partially failed. Here's how to fix it:

## Quick Fix (Recommended)

Run these commands in order:

```bash
# 1. Activate virtual environment
cd C:\00-web-dev\django-ezzydelivery\ezzydelivery
venvezdl\Scripts\activate

# 2. Mark the failed migration as not applied
python manage.py migrate product 0003_product_barcode_product_product_barcode_idx

# 3. Delete the problematic migration file
# (Already done - just confirming)

# 4. Create fresh migration
python manage.py makemigrations product

# 5. Apply the new migration
python manage.py migrate product
```

## Alternative: Manual Database Fix

If the above doesn't work, connect to PostgreSQL and run:

```sql
-- Check if column exists
SELECT column_name, data_type, character_maximum_length
FROM information_schema.columns
WHERE table_name = 'product_product' AND column_name = 'product_id';

-- If it doesn't exist, add it manually
ALTER TABLE product_product
ADD COLUMN product_id VARCHAR(6);

-- Create index
CREATE INDEX product_product_product_id_92a9387c ON product_product (product_id);

-- Then run the data migration to populate IDs
```

## What Happened

1. Migration 0004 started but failed partway
2. Database is in inconsistent state
3. Need to either roll back or complete manually

## After Fix

Once fixed, test by visiting:
- http://127.0.0.1:8004/product/all/cards/
- Create a new product to test ID generation
