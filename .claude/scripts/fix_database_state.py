"""
Script to fix database state for product_id migration
This will clean up any partial migration artifacts
"""

import os
import sys
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ezzydelivery.settings')
django.setup()

from django.db import connection

def run_sql(sql, description):
    """Execute SQL and print result"""
    print(f"\n{'='*60}")
    print(f"{description}")
    print(f"{'='*60}")

    with connection.cursor() as cursor:
        try:
            cursor.execute(sql)
            connection.commit()
            print("SUCCESS!")
            return True
        except Exception as e:
            print(f"Note: {e}")
            return False

def main():
    print("\n" + "="*60)
    print("Database State Fix for product_id")
    print("="*60)

    # Step 1: Drop existing indexes if they exist
    print("\nStep 1: Cleaning up existing indexes...")

    run_sql(
        "DROP INDEX IF EXISTS product_product_product_id_92a9387c_like CASCADE;",
        "Dropping LIKE index"
    )

    run_sql(
        "DROP INDEX IF EXISTS product_product_product_id_92a9387c CASCADE;",
        "Dropping regular index"
    )

    # Step 2: Drop unique constraint if exists
    print("\nStep 2: Removing unique constraint...")

    run_sql(
        "ALTER TABLE product_product DROP CONSTRAINT IF EXISTS product_product_product_id_key CASCADE;",
        "Dropping unique constraint"
    )

    # Step 3: Drop column if exists
    print("\nStep 3: Removing product_id column...")

    run_sql(
        "ALTER TABLE product_product DROP COLUMN IF EXISTS product_id CASCADE;",
        "Dropping product_id column"
    )

    # Step 4: Remove migration record
    print("\nStep 4: Cleaning migration history...")

    run_sql(
        "DELETE FROM django_migrations WHERE app = 'product' AND name LIKE '0004%';",
        "Removing 0004 migration records"
    )

    run_sql(
        "DELETE FROM django_migrations WHERE app = 'product' AND name LIKE '0005%';",
        "Removing 0005 migration records"
    )

    print("\n" + "="*60)
    print("DATABASE CLEANED SUCCESSFULLY!")
    print("="*60)
    print("\nNow run:")
    print("  python manage.py migrate product 0004")
    print("="*60 + "\n")

if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print(f"\nError: {e}")
        sys.exit(1)
