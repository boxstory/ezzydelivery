# Generated manually to add delivery tracking fields (if they don't exist)

from django.db import migrations, connection


def add_columns_if_not_exist(apps, schema_editor):
    """Add columns only if they don't already exist in the database."""
    with connection.cursor() as cursor:
        # Check which columns already exist (database-agnostic)
        db_engine = connection.vendor
        if db_engine == 'sqlite':
            cursor.execute("PRAGMA table_info(orders_order)")
            existing_columns = [row[1] for row in cursor.fetchall()]
        else:
            cursor.execute("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = 'orders_order'
                AND column_name IN ('delivered_at', 'fulfilled_at')
            """)
            existing_columns = [row[0] for row in cursor.fetchall()]

        # Add delivered_at if it doesn't exist
        if 'delivered_at' not in existing_columns:
            if db_engine == 'sqlite':
                cursor.execute('ALTER TABLE orders_order ADD COLUMN delivered_at DATETIME NULL')
            else:
                cursor.execute('ALTER TABLE orders_order ADD COLUMN delivered_at TIMESTAMP WITH TIME ZONE NULL')

        # Add fulfilled_at if it doesn't exist
        if 'fulfilled_at' not in existing_columns:
            if db_engine == 'sqlite':
                cursor.execute('ALTER TABLE orders_order ADD COLUMN fulfilled_at DATETIME NULL')
            else:
                cursor.execute('ALTER TABLE orders_order ADD COLUMN fulfilled_at TIMESTAMP WITH TIME ZONE NULL')


class Migration(migrations.Migration):

    dependencies = [
        ('orders', '0002_make_delivery_fields_nullable'),
    ]

    operations = [
        migrations.RunPython(add_columns_if_not_exist, migrations.RunPython.noop),
    ]
