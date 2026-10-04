"""
Purpose: A chat connected to a CRM lead is titled with the lead's name (like a saved contact) in the inbox list and header.
Used by: python manage.py test whatsapp.tests_lead_names
Notes: Lead names are CRM data, so ?names=1 / ?who=1 only return them to a staff login that may see leads. Lead.save()
       tags contact_name with its category (" ZyDrv" / " ZyBuz"), so expectations read the saved name back.
"""
from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase

from crm import services as crm_services
from crm.models import Lead
from whatsapp import chat_panel
from whatsapp.models import WhatsAppContact


class LeadNamesTests(TestCase):
    LID = '137903514620132'

    def setUp(self):
        cache.clear()
        self.lead = Lead.objects.create(category=Lead.CATEGORY_DRIVER, source=Lead.SOURCE_MANUAL,
                                        phone='+974 7164 2181', contact_name='Sheraz Abid')

    def test_phone_match_names_the_chat(self):
        self.lead.refresh_from_db()
        self.assertEqual(chat_panel.lead_names('default', ['97471642181@c.us']),
                         {'97471642181@c.us': self.lead.contact_name})
        self.assertTrue(self.lead.contact_name.startswith('Sheraz Abid'))

    def test_lid_chat_matches_through_the_contact_directory(self):
        WhatsAppContact.objects.create(session='default', phone='97471642181', lid=self.LID)
        self.assertEqual(chat_panel.lead_names('default', [f'{self.LID}@lid'])[f'{self.LID}@lid'].split(' Zy')[0], 'Sheraz Abid')

    def test_linked_number_names_the_chat(self):
        other = Lead.objects.create(source=Lead.SOURCE_MANUAL, phone='33112233', company_name='Pearl Trading')
        crm_services.add_wa_link(other, '97455667788', label='Office')
        self.assertEqual(chat_panel.lead_names('default', ['97455667788@c.us']),
                         {'97455667788@c.us': 'Pearl Trading'})

    def test_merged_lead_reports_its_parent(self):
        parent = Lead.objects.create(source=Lead.SOURCE_MANUAL, phone='44556677', contact_name='Parent Card')
        Lead.objects.filter(pk=self.lead.pk).update(merged_into=parent)
        self.assertEqual(chat_panel.lead_names('default', ['97471642181@c.us'])['97471642181@c.us'].split(' Zy')[0], 'Parent Card')

    def test_unrelated_chat_gets_nothing(self):
        self.assertEqual(chat_panel.lead_names('default', ['97499990000@c.us']), {})

    def test_names_endpoint_hides_leads_without_crm_login(self):
        url = '/waha/wa-chats/'
        params = {'names': 1, 'ids': '97471642181@c.us', 'session': 'default'}
        # No staff login, no inbox at all (and so no lead names).
        r = self.client.get(url, params, HTTP_HOST='ezzydelivery.qa', secure=True)
        self.assertEqual(r.status_code, 401)
        self.client.force_login(User.objects.create_user('crmboss', is_staff=True, is_superuser=True))
        r = self.client.get(url, params, HTTP_HOST='ezzydelivery.qa', secure=True)
        self.assertTrue(r.json()['leads']['97471642181@c.us'].startswith('Sheraz Abid'))
