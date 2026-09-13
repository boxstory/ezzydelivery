# Purpose: Point DeliveryTask.dl_to_address at the row dl_address_update already holds.
# Used by: the ~168 read sites that address the delivery address through dl_to_address.
# Notes: dl_to_address was NULL on every row (1781/1781) while dl_address_update was set
#        on every row, so the driver area filter matched nothing and card unit/area/
#        property-type/time-slot rendered blank. Data-only; the reverse is a no-op
#        because a backfilled value is indistinguishable from one set by hand later.

from django.db import migrations
from django.db.models import F


def backfill(apps, schema_editor):
    DeliveryTask = apps.get_model('delivery', 'DeliveryTask')
    DeliveryTask.objects.filter(
        dl_to_address__isnull=True,
        dl_address_update__isnull=False,
    ).update(dl_to_address=F('dl_address_update'))


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('delivery', '0049_dladdressupdate_access_token'),
    ]

    operations = [
        migrations.RunPython(backfill, noop),
    ]
