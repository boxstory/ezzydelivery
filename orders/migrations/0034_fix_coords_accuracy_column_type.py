"""
Fix coords_accuracy column type from double precision to varchar(15).
The column was incorrectly created as a numeric type; the model defines it
as a CharField(max_length=15) with string choices.
"""
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('orders', '0033_order_coords_accuracy_order_latitude_order_longitude_and_more'),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
                ALTER TABLE orders_order
                ALTER COLUMN coords_accuracy TYPE VARCHAR(15)
                USING CASE
                    WHEN coords_accuracy IS NULL THEN NULL
                    ELSE coords_accuracy::TEXT
                END;
            """,
            reverse_sql="""
                ALTER TABLE orders_order
                ALTER COLUMN coords_accuracy TYPE DOUBLE PRECISION
                USING NULL;
            """,
        ),
    ]
