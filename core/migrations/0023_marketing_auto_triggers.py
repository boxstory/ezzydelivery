# Purpose: Register the marketing-desk auto triggers (driver onboarding, lead messaging) plus one orphan finance key.
# Used by: core.models.AutoTriggerConfig — the rows the workforce Auto Triggers page lists and toggles.
# Notes: Every key here is enforced somewhere in code (see `action`), so a switch on this page changes real behaviour.
#        Idempotent: re-running refreshes the descriptive text but never touches is_enabled, so a staff switch-off survives.

from django.db import migrations


# trigger_key -> row fields. category/department decide which table + tab it lands in.
TRIGGERS = [
    # ── Marketing: driver onboarding (applicant-facing) ───────────────────
    {
        'trigger_key': 'wa_driver_application_thanks',
        'label': 'Driver Application Received',
        'category': 'whatsapp',
        'department': 'mkt',
        'description': ("Thank-you message to a driver applicant the first time they "
                        "submit the join form. Sent once per applicant — re-submissions "
                        "and later edits never repeat it."),
        'action': 'core.whatsapp_utils.send_driver_application_thank_you',
    },
    {
        'trigger_key': 'wa_driver_profile_reminder',
        'label': 'Driver Application Reminder',
        'category': 'whatsapp',
        'department': 'mkt',
        'description': ("Staff-sent reminder listing the application sections an "
                        "applicant still has to finish, with the form link. Switching "
                        "this off disables the Remind button on the driver page."),
        'action': 'workforce.views.driver_remind_completion',
    },
    {
        'trigger_key': 'driver_application_submitted',
        'label': 'Driver Application Submitted',
        'category': 'system',
        'department': 'mkt',
        'description': ("Fires when a driver finishes the public join form. Build flows "
                        "on it to alert the recruiter group or open a webhook."),
        'action': 'core.views.join_driver',
    },

    # ── Marketing: leads ──────────────────────────────────────────────────
    {
        'trigger_key': 'wa_quote_thank_you',
        'label': 'Quote Request Thank-You',
        'category': 'whatsapp',
        'department': 'mkt',
        'description': ("Thank-you message to a business that submits the 3PL pricing "
                        "form. Sends from the CRM — Business Leads number."),
        'action': 'core.whatsapp_utils.send_inquiry_thank_you_message',
    },
    {
        'trigger_key': 'wa_quote_admin_alert',
        'label': 'New Quote Request Alert',
        'category': 'whatsapp',
        'department': 'mkt',
        'description': ("Alerts the sales number with the full details of every new 3PL "
                        "pricing inquiry."),
        'action': 'core.whatsapp_utils.send_admin_inquiry_notification',
    },
    {
        'trigger_key': 'wa_lead_followup_digest',
        'label': 'Daily Lead Follow-up Digest',
        'category': 'whatsapp',
        'department': 'mkt',
        'description': ("One WhatsApp digest per assignee listing their due and overdue "
                        "leads; unassigned ones go to the admin number. Runs on the "
                        "daily follow-up cron."),
        'action': 'crm.services.send_followup_digests',
    },
    {
        'trigger_key': 'lead_created',
        'label': 'New Lead Captured',
        'category': 'system',
        'department': 'mkt',
        'description': ("Fires for every new CRM lead — pricing form, WhatsApp quick "
                        "form, and inbound WhatsApp promote."),
        'action': 'crm.services.create_lead_*',
    },
    {
        'trigger_key': 'lead_stage_changed',
        'label': 'Lead Stage Changed',
        'category': 'system',
        'department': 'mkt',
        'description': ("Fires on every pipeline move on the leads board, business or "
                        "driver. Context carries the old and new stage."),
        'action': 'crm.services.set_lead_stage',
    },
    {
        'trigger_key': 'lead_won',
        'label': 'Lead Won',
        'category': 'system',
        'department': 'mkt',
        'description': "Fires when a lead reaches the Won stage.",
        'action': 'crm.services.set_lead_stage',
    },
    {
        'trigger_key': 'lead_lost',
        'label': 'Lead Lost',
        'category': 'system',
        'department': 'mkt',
        'description': "Fires when a lead is moved to Lost.",
        'action': 'crm.services.set_lead_stage',
    },

    # ── Finance: key that fired with no row to switch it off ──────────────
    {
        'trigger_key': 'business_cod_settled',
        'label': 'Business COD Settled',
        'category': 'system',
        'department': 'fin',
        'description': ("Fires when a COD statement is settled with a business on the "
                        "payout console."),
        'action': 'workforce.views (business COD settlement)',
    },
]


def seed(apps, schema_editor):
    AutoTriggerConfig = apps.get_model('core', 'AutoTriggerConfig')
    for row in TRIGGERS:
        AutoTriggerConfig.objects.update_or_create(
            trigger_key=row['trigger_key'],
            defaults={k: v for k, v in row.items() if k != 'trigger_key'},
        )


def unseed(apps, schema_editor):
    AutoTriggerConfig = apps.get_model('core', 'AutoTriggerConfig')
    AutoTriggerConfig.objects.filter(
        trigger_key__in=[r['trigger_key'] for r in TRIGGERS]
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0022_whatsappsenderroute_channel_and_more'),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]
