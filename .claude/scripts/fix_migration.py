#!/usr/bin/env python
"""
Quick fix script for product_id migration issue
Run this from the Django project root directory
"""

import os
import sys
import subprocess

def run_command(cmd, description):
    """Run a command and print its output"""
    print(f"\n{'='*60}")
    print(f"{description}")
    print(f"{'='*60}")

    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)

    print(result.stdout)
    if result.stderr:
        print("Errors/Warnings:", result.stderr)

    if result.returncode != 0:
        print(f"❌ Command failed with exit code {result.returncode}")
        return False
    else:
        print(f"✅ {description} completed successfully")
        return True

def main():
    print("""
    ╔════════════════════════════════════════════════════════════╗
    ║         Product ID Migration Fix Script                   ║
    ║                                                            ║
    ║  This will:                                                ║
    ║  1. Roll back to last working migration                   ║
    ║  2. Apply new migration with proper product_id setup      ║
    ║  3. Generate unique IDs for all products                  ║
    ╚════════════════════════════════════════════════════════════╝
    """)

    # Check if we're in the right directory
    if not os.path.exists('manage.py'):
        print("❌ Error: manage.py not found!")
        print("Please run this script from the Django project root directory")
        sys.exit(1)

    # Step 1: Show current migration status
    if not run_command(
        'python manage.py showmigrations product',
        "Checking current migration status"
    ):
        print("\n⚠️ Warning: Could not check migration status, but continuing...")

    # Step 2: Roll back to migration 0003
    print("\n" + "="*60)
    print("Rolling back to last working migration...")
    print("="*60)
    rollback_result = run_command(
        'python manage.py migrate product 0003_product_barcode_product_product_barcode_idx',
        "Rolling back migrations"
    )

    if not rollback_result:
        print("\n⚠️ Rollback had issues, but this might be OK if migration wasn't applied yet")

    # Step 3: Apply new migration
    if not run_command(
        'python manage.py migrate product',
        "Applying product_id migration"
    ):
        print("\n❌ Migration failed! Check errors above.")
        print("\nTroubleshooting:")
        print("1. Make sure PostgreSQL is running")
        print("2. Check database connection in settings.py")
        print("3. See FINAL_FIX_INSTRUCTIONS.md for manual fix")
        sys.exit(1)

    # Success!
    print("""
    ╔════════════════════════════════════════════════════════════╗
    ║                  ✅ SUCCESS!                               ║
    ║                                                            ║
    ║  Product ID system is now set up!                         ║
    ║                                                            ║
    ║  Next steps:                                               ║
    ║  1. Start your server: python manage.py runserver 8004    ║
    ║  2. Visit: http://127.0.0.1:8004/product/all/cards/       ║
    ║  3. All products should now show their product IDs        ║
    ╚════════════════════════════════════════════════════════════╝
    """)

    # Ask if user wants to start the server
    response = input("\nWould you like to start the development server now? (y/n): ")
    if response.lower() in ['y', 'yes']:
        print("\nStarting development server...")
        print("Press Ctrl+C to stop the server\n")
        os.system('python manage.py runserver 8004')

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n👋 Script cancelled by user")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        print("\nPlease see FINAL_FIX_INSTRUCTIONS.md for manual fix steps")
        sys.exit(1)
