from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('orders', '0022_add_product_description_to_order'),
    ]

    operations = [
        migrations.RenameField(
            model_name='order',
            old_name='product_description',
            new_name='package_description',
        ),
    ]
