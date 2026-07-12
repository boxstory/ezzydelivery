from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('orders', '0029_add_publiclinksource_and_public_link_type'),
    ]

    operations = [
        migrations.AlterField(
            model_name='order',
            name='verification_status',
            field=models.CharField(
                choices=[
                    ('pending', 'Pending Verification'),
                    ('address_verified', 'Address Verified'),
                    ('address_needs_update', 'Address Needs Update'),
                    ('customer_contacted', 'Customer Contacted'),
                    ('verified_by_customer', 'Verified by Customer'),
                    ('verified', 'Verified'),
                    ('rejected', 'Rejected'),
                ],
                default='pending',
                max_length=50,
            ),
        ),
    ]
