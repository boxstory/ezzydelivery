# Purpose: Copy Order.delivery_area_name / preferred_time_slot onto the address row.
# Used by: driver task cards and every list that reads DlAddressUpdate.area_name.
# Notes: The data already existed on the Order (area 65% populated) but was never
#        copied across, so the address row read 2.7% / 0%. Fills blanks only —
#        an area_name someone typed by hand is left alone.

from django.db import migrations


def backfill(apps, schema_editor):
    DlAddressUpdate = apps.get_model('delivery', 'DlAddressUpdate')

    rows = DlAddressUpdate.objects.filter(
        order__isnull=False,
    ).select_related('order').only(
        'id', 'area_name', 'time_slot',
        'order__delivery_area_name', 'order__preferred_time_slot',
    )

    batch = []
    for row in rows.iterator(chunk_size=2000):
        order = row.order
        touched = False
        if not (row.area_name or '').strip() and (order.delivery_area_name or '').strip():
            row.area_name = order.delivery_area_name
            touched = True
        if not (row.time_slot or '').strip() and (order.preferred_time_slot or '').strip():
            row.time_slot = order.preferred_time_slot
            touched = True
        if touched:
            batch.append(row)
        if len(batch) >= 2000:
            DlAddressUpdate.objects.bulk_update(batch, ['area_name', 'time_slot'])
            batch = []
    if batch:
        DlAddressUpdate.objects.bulk_update(batch, ['area_name', 'time_slot'])


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('delivery', '0050_backfill_dl_to_address'),
        ('orders', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(backfill, noop),
    ]
