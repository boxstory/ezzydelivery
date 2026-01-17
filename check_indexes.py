import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ezzydelivery.settings')
django.setup()

from django.db import connection

with connection.cursor() as cursor:
    cursor.execute("""
        SELECT indexname, indexdef
        FROM pg_indexes
        WHERE tablename = 'product_product'
        AND indexname LIKE '%product_id%'
        ORDER BY indexname;
    """)

    results = cursor.fetchall()
    if results:
        print("\nExisting product_id indexes:")
        for name, definition in results:
            print(f"  - {name}")
            print(f"    {definition}\n")
    else:
        print("\nNo product_id indexes found.")
