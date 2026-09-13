# Purpose: Mark every pre-existing seller comment as already read by staff
# Used by: orders.OrderComments.staff_read_at (unread flag on the task console)
# Notes: Without this, switching the feature on would light up every historic
#        task at once and the alert would mean nothing on day one.
from django.db import migrations
from django.utils import timezone


def backfill_read(apps, schema_editor):
    OrderComments = apps.get_model('orders', 'OrderComments')
    OrderComments.objects.filter(staff_read_at__isnull=True).update(
        staff_read_at=timezone.now())


def unbackfill(apps, schema_editor):
    # Which receipts this migration stamped is not recoverable, so the reverse
    # is a no-op rather than wrongly re-flagging every note as unread.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('orders', '0066_ordercomments_staff_read_at_and_more'),
    ]

    operations = [
        migrations.RunPython(backfill_read, unbackfill),
    ]
