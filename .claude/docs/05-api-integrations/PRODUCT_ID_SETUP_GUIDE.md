# Product ID Setup Guide

## Overview
This guide will help you add the 6-digit unique product_id system to your database.

## What You Need
- PostgreSQL database access
- Terminal access to Django project
- 5-10 minutes

## Step-by-Step Instructions

### Step 1: Run SQL Script

1. **Connect to your PostgreSQL database** using pgAdmin, psql, or any database client

2. **Run the SQL script**: `add_product_id_manually.sql`

   ```bash
   # If using psql command line:
   psql -U your_username -d your_database_name -f add_product_id_manually.sql
   ```

   This will:
   - Add the `product_id` column
   - Generate unique IDs for all existing products
   - Add indexes and constraints

3. **Verify** it worked by checking the output - you should see:
   - "Product ID generation complete"
   - A summary showing total products and unique IDs
   - Sample product IDs

### Step 2: Record Migration in Django

1. **Activate virtual environment**:
   ```bash
   cd C:\00-web-dev\django-ezzydelivery\ezzydelivery
   venvezdl\Scripts\activate
   ```

2. **Fake-apply the migration** (since we already added the column manually):
   ```bash
   python manage.py migrate product 0004_add_product_id_field --fake
   ```

   This tells Django "yes, the migration is applied" without actually running it.

### Step 3: Test Everything

1. **Start the development server**:
   ```bash
   python manage.py runserver 8004
   ```

2. **Visit the product pages**:
   - http://127.0.0.1:8004/product/all/cards/
   - http://127.0.0.1:8004/product/all/table/

3. **Create a new product** - it should automatically get a product_id

4. **Check the product_id displays** correctly in:
   - Product cards
   - Product table
   - Admin interface

## Verification Checklist

- [ ] SQL script ran without errors
- [ ] All existing products have product_ids
- [ ] Migration is marked as applied
- [ ] Product pages load without errors
- [ ] New products get auto-generated product_ids
- [ ] Product IDs are visible in templates
- [ ] Product IDs are 6 digits (e.g., 000101, 000212)

## Product ID Format

**Format**: `{4-digit-counter}{2-digit-business-code}`

**Examples**:
- Business "BUS001" → Products: `000101`, `000201`, `000301`
- Business "COMP99" → Products: `000199`, `000299`, `000399`

The last 2 digits identify which business the product belongs to.

## Troubleshooting

### Error: "column product_id already exists"
- The column was already added
- Skip Step 1 and go directly to Step 2

### Error: "product_id violates not-null constraint"
- Some products don't have IDs
- Re-run the ID generation part of the SQL script

### Products show no product_id
- Check if migration was properly fake-applied
- Verify the column exists in database
- Check Django is reading from correct database

## What Changed

1. **Database**: New `product_id` column in `product_product` table
2. **Model**: New field that auto-generates on save
3. **Templates**: Display product_id in cards and tables
4. **Forms**: product_id excluded (auto-generated only)
5. **Admin**: product_id shown as read-only

## Files Created

- `add_product_id_manually.sql` - SQL script to add column and generate IDs
- `product/migrations/0004_add_product_id_field.py` - Django migration to record change
- `PRODUCT_ID_SETUP_GUIDE.md` - This file

## Support

If you encounter issues:
1. Check the SQL script output for errors
2. Verify database connection settings
3. Ensure all existing products have a business assigned
4. Check Django logs for specific error messages

---

**Note**: After setup, all future products will automatically get product_ids when saved. No manual intervention needed!
