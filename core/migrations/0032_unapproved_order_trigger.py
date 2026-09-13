# Purpose: Register the "unapproved business created an order" staff alert on the Auto Triggers page.
# Used by: orders.views (add_order, add_order_bulk, bulk_order_entry).
# Notes: Idempotent — re-running refreshes the text but never touches is_enabled, so a staff
#        switch-off survives a redeploy.

from django.db import migrations


TRIGGER = {
    'trigger_key': 'business_unapproved_order',
    'label': 'Unapproved Business Created an Order',
    'category': 'system',
    'department': 'ops',
    'description': ("Alerts the operations desk when an order is created for a business "
                    "whose account is not 'active' — awaiting approval, archived or "
                    "suspended. The write gate should already refuse these, so a fired "
                    "alert means a path slipped through and needs looking at."),
    'action': 'orders.views.add_order / add_order_bulk / bulk_order_entry',
}


def seed(apps, schema_editor):
    AutoTriggerConfig = apps.get_model('core', 'AutoTriggerConfig')
    AutoTriggerConfig.objects.update_or_create(
        trigger_key=TRIGGER['trigger_key'],
        defaults={k: v for k, v in TRIGGER.items() if k != 'trigger_key'},
    )


def unseed(apps, schema_editor):
    AutoTriggerConfig = apps.get_model('core', 'AutoTriggerConfig')
    AutoTriggerConfig.objects.filter(trigger_key=TRIGGER['trigger_key']).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0031_alter_whatsappverification_verification_type'),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]
