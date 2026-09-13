# Purpose: Register the two P2P WhatsApp triggers on the Auto Triggers page.
# Used by: p2p.notifications (send_booking_confirmation, notify_ops_of_comment).
# Notes: Idempotent — re-running refreshes the text but never touches is_enabled or the routing
#        columns, so a staff switch-off or a number override survives a redeploy.

from django.db import migrations


TRIGGERS = [
    {
        'trigger_key': 'p2p_booking_confirm',
        'label': 'P2P Booking — Confirmation & Accept Link',
        'category': 'whatsapp',
        'department': 'ops',
        'description': ("Sent to the sender the moment a point-to-point booking becomes an "
                        "order. Carries the route, the parcel, the delivery fee and the link "
                        "that confirms it — and confirming is what releases the job to a "
                        "driver, so switching this off leaves bookings sitting unconfirmed."),
        'action': 'p2p.notifications.send_booking_confirmation',
    },
    {
        'trigger_key': 'p2p_customer_comment',
        'label': 'P2P — Customer Left a Message',
        'category': 'whatsapp',
        'department': 'ops',
        'description': ("Nudges the operations desk when a personal sender writes on their "
                        "delivery from the customer console. Set a notify number to route it "
                        "somewhere other than the default."),
        'action': 'p2p.notifications.notify_ops_of_comment',
    },
]


def seed(apps, schema_editor):
    AutoTriggerConfig = apps.get_model('core', 'AutoTriggerConfig')
    for trigger in TRIGGERS:
        AutoTriggerConfig.objects.update_or_create(
            trigger_key=trigger['trigger_key'],
            defaults={k: v for k, v in trigger.items() if k != 'trigger_key'},
        )


def unseed(apps, schema_editor):
    AutoTriggerConfig = apps.get_model('core', 'AutoTriggerConfig')
    AutoTriggerConfig.objects.filter(
        trigger_key__in=[t['trigger_key'] for t in TRIGGERS]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0033_profile_is_customer_profile_whatsapp_verified_and_more'),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]
