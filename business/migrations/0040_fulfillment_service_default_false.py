# Purpose: Stop new clients being born with the fulfilment service switched on.
# Used by: business.Business.fulfillment_service_enabled
# Notes: 0010 flipped this default from False to True, so every business created since was
#        stamped enabled=True while fulfillment_service_status stayed at 'none'. That is not
#        cosmetic — Product.save() refuses a SKU-less product for a fulfilment seller and the
#        client sidebar offers warehouse menus. Fulfilment is opt-in: staff switch it on from
#        the seller Edit tab and link a warehouse. 0041 repairs the rows this default created.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('business', '0039_businessapisettings_product_column_mapping'),
    ]

    operations = [
        migrations.AlterField(
            model_name='business',
            name='fulfillment_service_enabled',
            field=models.BooleanField(default=False, help_text='Enable fulfillment service (WMS integration) for this business'),
        ),
    ]
