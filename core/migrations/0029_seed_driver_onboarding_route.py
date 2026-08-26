"""
Purpose: Seed the driver_onboarding sender route with the fleet number so that number stops living in the source
Used by: core.whatsapp_utils.get_fleet_instance / send_driver_application_thank_you
Notes: Idempotent and skipped entirely when no fleet instance exists (fresh installs, test DBs)
"""
from django.db import migrations

FLEET_NUMBER = '97466124545'


def seed_route(apps, schema_editor):
    WhatsAppInstance = apps.get_model('core', 'WhatsAppInstance')
    WhatsAppSenderRoute = apps.get_model('core', 'WhatsAppSenderRoute')

    if WhatsAppSenderRoute.objects.filter(section='driver_onboarding').exists():
        return
    inst = WhatsAppInstance.objects.filter(
        phone_number=FLEET_NUMBER, is_active=True).first()
    if not inst:
        return
    WhatsAppSenderRoute.objects.create(
        section='driver_onboarding', instance=inst,
        channel='evolution', is_enabled=True,
    )


def unseed_route(apps, schema_editor):
    """Only removes the row this migration would have created."""
    WhatsAppSenderRoute = apps.get_model('core', 'WhatsAppSenderRoute')
    WhatsAppSenderRoute.objects.filter(
        section='driver_onboarding', instance__phone_number=FLEET_NUMBER).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0028_autotriggerconfig_notify_number'),
    ]

    operations = [
        migrations.RunPython(seed_route, unseed_route),
    ]
