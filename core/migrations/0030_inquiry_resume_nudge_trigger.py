# Purpose: Register the "abandoned 3PL form" WhatsApp nudge on the Auto Triggers page.
# Used by: core.whatsapp_utils.send_inquiry_resume_nudge, run by the
#          send_inquiry_resume_nudges management command each morning.
# Notes: Idempotent — re-running refreshes the text but never touches is_enabled, so a staff
#        switch-off survives a redeploy. Seeded DISABLED: this messages prospects directly,
#        so it stays off until someone turns it on deliberately.

from django.db import migrations


TRIGGER = {
    'trigger_key': 'wa_inquiry_resume_nudge',
    'label': 'Abandoned Inquiry Reminder',
    'category': 'whatsapp',
    'department': 'mkt',
    'description': ("Messages a prospect the morning after they start the 3PL pricing form "
                    "and leave without finishing, with a link that resumes their saved "
                    "answers. Sent once per inquiry, from the CRM & Leads number."),
    'action': 'core.whatsapp_utils.send_inquiry_resume_nudge',
}


def seed(apps, schema_editor):
    AutoTriggerConfig = apps.get_model('core', 'AutoTriggerConfig')
    defaults = {k: v for k, v in TRIGGER.items() if k != 'trigger_key'}
    obj, created = AutoTriggerConfig.objects.get_or_create(
        trigger_key=TRIGGER['trigger_key'],
        defaults={**defaults, 'is_enabled': False},
    )
    if not created:
        # Refresh the copy, leave the staff switch alone.
        for field, value in defaults.items():
            setattr(obj, field, value)
        obj.save()


def unseed(apps, schema_editor):
    AutoTriggerConfig = apps.get_model('core', 'AutoTriggerConfig')
    AutoTriggerConfig.objects.filter(trigger_key=TRIGGER['trigger_key']).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0029_seed_driver_onboarding_route'),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]
