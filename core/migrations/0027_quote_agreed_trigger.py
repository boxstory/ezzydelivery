# Purpose: Register the "customer accepted a quote" WhatsApp alert on the Auto Triggers page.
# Used by: core.whatsapp_utils.send_quote_agreement_notification.
# Notes: Idempotent — re-running refreshes the text but never touches is_enabled, so a staff
#        switch-off survives a redeploy.

from django.db import migrations


TRIGGER = {
    'trigger_key': 'wa_quote_agreed_alert',
    'label': 'Quote Accepted by Customer',
    'category': 'whatsapp',
    'department': 'mkt',
    'description': ("Alerts the sales number when a prospect picks a plan on the quote "
                    "page after submitting the 3PL form — either the flat rate they "
                    "accepted, or a request to discuss a custom plan."),
    'action': 'core.whatsapp_utils.send_quote_agreement_notification',
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
        ('core', '0026_whatsappsendlog_channel'),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]
