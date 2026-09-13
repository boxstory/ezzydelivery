# Purpose: Give OrderComments real authorship (FK + frozen role) and a visibility flag.
# Used by: orders/models.py OrderComments; all order-comment read/write sites.
# Notes: is_internal is added as False so the 9 pre-existing rows - all client-written
#        "Reconfirmed by ..." notes that clients already see today - stay visible, then
#        the default flips to True so every NEW row is hidden unless a write site opts in.
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def backfill_author_role(apps, schema_editor):
    """Every row that exists at this point was written by a business user through
    the client console (verified against production data), so freeze that role."""
    OrderComments = apps.get_model('orders', 'OrderComments')
    OrderComments.objects.update(author_role='client')


def unbackfill_author_role(apps, schema_editor):
    OrderComments = apps.get_model('orders', 'OrderComments')
    OrderComments.objects.update(author_role='system')


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('orders', '0063_order_delivery_area_name_order_delivery_area_source'),
    ]

    operations = [
        migrations.AddField(
            model_name='ordercomments',
            name='author',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='order_comments',
                to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name='ordercomments',
            name='author_role',
            field=models.CharField(
                choices=[('staff', 'Staff'), ('client', 'Client'),
                         ('driver', 'Driver'), ('system', 'System')],
                default='system', max_length=20),
        ),
        migrations.RunPython(backfill_author_role, unbackfill_author_role),
        # Two-step default: existing rows land on False, new rows default to True.
        migrations.AddField(
            model_name='ordercomments',
            name='is_internal',
            field=models.BooleanField(default=False),
        ),
        migrations.AlterField(
            model_name='ordercomments',
            name='is_internal',
            field=models.BooleanField(
                default=True,
                help_text='Internal notes are visible to staff only, never to the client.'),
        ),
        migrations.AddIndex(
            model_name='ordercomments',
            index=models.Index(fields=['order', 'is_internal'],
                               name='ord_comment_visibility_idx'),
        ),
    ]
