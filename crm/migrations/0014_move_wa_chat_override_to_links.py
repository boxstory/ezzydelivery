"""
Purpose: Move every Lead.wa_chat_override value into a LeadWaLink row and clear the legacy field.
Used by: manage.py migrate (runs once)
Notes: Reversible — the reverse copies each lead's first link back into wa_chat_override.
"""
from django.db import migrations


def forwards(apps, schema_editor):
    Lead = apps.get_model('crm', 'Lead')
    LeadWaLink = apps.get_model('crm', 'LeadWaLink')
    for lead in Lead.objects.exclude(wa_chat_override='').only('pk', 'wa_chat_override', 'wa_session'):
        value = lead.wa_chat_override.strip()
        if value:
            session = lead.wa_session if lead.wa_session and lead.wa_session != '__all__' else ''
            LeadWaLink.objects.get_or_create(
                lead_id=lead.pk, identifier=value[:50],
                defaults={'session': session[:64]},
            )
    Lead.objects.exclude(wa_chat_override='').update(wa_chat_override='')


def backwards(apps, schema_editor):
    Lead = apps.get_model('crm', 'Lead')
    LeadWaLink = apps.get_model('crm', 'LeadWaLink')
    first = {}
    for link in LeadWaLink.objects.order_by('created_at', 'pk'):
        first.setdefault(link.lead_id, link.identifier)
    for lead_id, identifier in first.items():
        Lead.objects.filter(pk=lead_id, wa_chat_override='').update(wa_chat_override=identifier)


class Migration(migrations.Migration):

    dependencies = [
        ('crm', '0013_lead_wa_links'),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
