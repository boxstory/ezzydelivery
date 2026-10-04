# Purpose: Give every stored bare 8-digit Qatar lead phone its 974 country code.
# Used by: crm.Lead.phone — Lead.save() canonicalizes new writes the same way.

from django.db import migrations
from django.db.models import Value
from django.db.models.functions import Concat


def add_country_code(apps, schema_editor):
    Lead = apps.get_model('crm', 'Lead')
    Lead.objects.filter(phone__regex=r'^[0-9]{8}$').update(
        phone=Concat(Value('974'), 'phone'))


class Migration(migrations.Migration):

    dependencies = [
        ('crm', '0015_lead_merge_filled'),
    ]

    operations = [
        migrations.RunPython(add_country_code, migrations.RunPython.noop),
    ]
