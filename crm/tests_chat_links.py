"""
Purpose: Tests that an owner's WhatsApp chat joins the lead their pricing form created, even when the form names the office number.
Used by: python manage.py test crm.tests_chat_links
Notes: WAHA is never reached — the webhook's HMAC check and every send are patched. Covers the "Ref P…" message, the inbox's ?wa= link, and the wider duplicate check.
"""
import json
from unittest.mock import patch
from urllib.parse import quote

from django.contrib.auth.models import User
from django.contrib.sessions.middleware import SessionMiddleware
from django.core.cache import cache
from django.test import RequestFactory, TestCase

from crm import chat_links, services
from crm.models import STAGE_CACHE_KEY, Lead, LeadActivity, LeadWaLink, PricingLinkRef
from webpages.models import PricingEnquiry

OFFICE = '97444001122'
OWNER = '97455667788'
OWNER_LID = '123456789012345'


def make_enquiry(**overrides):
    fields = dict(full_name='Ali Hassan', business_name='Doha Sweets',
                  business_contact_number='+974 4400 1122', product_category='Food', is_complete=True)
    fields.update(overrides)
    return PricingEnquiry.objects.create(**fields)


class ChatLinkBase(TestCase):
    def setUp(self):
        cache.delete(STAGE_CACHE_KEY)
        self.enquiry = make_enquiry()
        self.lead, _ = services.create_lead_from_pricing_inquiry(self.enquiry)

    def links(self, lead=None):
        return list((lead or self.lead).wa_links.values_list('identifier', 'session', 'label'))


class RefCodeTests(TestCase):
    def test_round_trip_and_tampering(self):
        ref = chat_links.ref_for('P', 125)
        self.assertRegex(ref, r'^Ref P125-[0-9a-f]{6}$')
        self.assertEqual(chat_links.parse_ref(f'Hi ({ref}). Thanks'), ('P', 125))
        self.assertIsNone(chat_links.parse_ref(ref.replace('P125', 'P126')))
        self.assertIsNone(chat_links.parse_ref('Ref P125-000000'))


class MessageRefTests(ChatLinkBase):
    def message(self, sender, session='default', body=None, chat=None):
        body = body or f'Hi, I have filled the form ({chat_links.ref_for("P", self.enquiry.pk)}).'
        payload = {'event': 'message', 'session': session, 'payload': {
            'id': f'false_{chat or sender + "@c.us"}_3EB0{abs(hash(body)) % 10**8}',
            'from': chat or f'{sender}@c.us', 'to': '97466451589@c.us',
            'body': body, 'timestamp': 1785000000, 'type': 'chat'}}
        with patch('whatsapp.waha_views._verify_waha_hmac', return_value=(True, '')):
            return self.client.post('/api/integrations/waha/webhook/', json.dumps(payload),
                                    content_type='application/json')

    def test_owner_chat_with_the_reference_joins_the_office_number_lead(self):
        self.assertEqual(self.message(OWNER).status_code, 200)
        self.assertEqual(self.links(), [(OWNER, 'default', 'Owner')])
        self.assertTrue(self.lead.activities.filter(body__contains='linked as Owner').exists())

    def test_a_lid_sender_is_linked_on_its_own_session(self):
        self.message(OWNER_LID, chat=f'{OWNER_LID}@lid')
        self.assertEqual(self.links(), [(OWNER_LID, 'default', 'Owner')])

    def test_an_existing_card_for_the_owner_is_folded_in(self):
        wa_card = Lead.objects.create(source=Lead.SOURCE_WA_INBOUND, phone=OWNER, contact_name='Owner')
        Lead.objects.filter(pk=wa_card.pk).update(created_at=self.lead.created_at.replace(year=2025))
        self.message(OWNER)
        self.lead.refresh_from_db()
        # The older card stays primary, as in every other merge.
        self.assertEqual(self.lead.merged_into_id, wa_card.pk)
        self.assertIn(OFFICE, [l.identifier for l in wa_card.wa_links.all()])

    def test_the_same_message_twice_logs_once(self):
        self.message(OWNER)
        self.message(OWNER, body=f'again {chat_links.ref_for("P", self.enquiry.pk)}')
        self.assertEqual(self.lead.activities.filter(body__contains='linked as Owner').count(), 1)

    def test_group_messages_and_bad_codes_link_nothing(self):
        self.assertIsNone(chat_links.link_from_message(
            'default', OWNER, chat_links.ref_for('P', self.enquiry.pk), is_group=True))
        self.message(OWNER, body=f'Ref P{self.enquiry.pk}-abcdef')
        self.assertEqual(self.links(), [])


class InboxLinkTests(ChatLinkBase):
    def setUp(self):
        super().setUp()
        self.staff = User.objects.create_user('linkdesk', password='x', is_staff=True)
        from core.models import Profile
        profile, _ = Profile.objects.get_or_create(user=self.staff)
        profile.is_staff = True
        profile.is_superadmin = True
        profile.save()

    def test_send_link_tags_the_form_url_for_that_chat(self):
        self.client.force_login(self.staff)
        with patch('whatsapp.waha_views.send_waha_text', return_value=(True, {'message_id': 'x'})) as send:
            resp = self.client.post('/workforce/crm/whatsapp-inbox/send-link/',
                                    {'phone': OWNER, 'kind': 'business', 'session': 'default'},
                                    HTTP_HOST='ezzydelivery.qa', secure=True)
        self.assertEqual(resp.status_code, 200, resp.content)
        ref = PricingLinkRef.objects.get()
        self.assertEqual((ref.identifier, ref.session, ref.sent_by), (OWNER, 'default', self.staff))
        self.assertIn(f'https://ezzydelivery.qa/3pl/pricing/?wa={ref.code}', send.call_args.args[1])

    def test_a_body_without_the_form_link_is_left_alone(self):
        self.assertEqual(chat_links.tag_pricing_link('no link here', 'default', OWNER), 'no link here')
        self.assertFalse(PricingLinkRef.objects.exists())

    def test_the_form_opened_from_that_link_joins_the_chat(self):
        ref = PricingLinkRef.objects.create(code='Ab3dE6gH', session='default', identifier=OWNER)
        request = RequestFactory().get('/3pl/pricing/', {'wa': ref.code})
        SessionMiddleware(lambda r: None).process_request(request)
        chat_links.remember_link_code(request)
        survivor = chat_links.link_from_pricing_ref(self.lead, request)
        self.assertEqual(survivor, self.lead)
        self.assertEqual(self.links(), [(OWNER, 'default', 'Owner')])
        ref.refresh_from_db()
        self.assertEqual(ref.lead, self.lead)
        self.assertIsNotNone(ref.used_at)
        self.assertNotIn('pricing_wa_ref', request.session)

    def test_a_malformed_code_is_not_remembered(self):
        request = RequestFactory().get('/3pl/pricing/', {'wa': '../../x'})
        SessionMiddleware(lambda r: None).process_request(request)
        chat_links.remember_link_code(request)
        self.assertNotIn('pricing_wa_ref', request.session)


class DuplicateGuardTests(ChatLinkBase):
    def test_add_business_lead_on_a_linked_chat_opens_the_existing_card(self):
        services.add_wa_link(self.lead, OWNER, label='Owner')
        lead, created = services.create_lead_from_wa_number(OWNER)
        self.assertEqual((lead, created), (self.lead, False))

    def test_a_2nd_mobile_match_opens_the_card_and_links_the_chat(self):
        Lead.objects.filter(pk=self.lead.pk).update(phone_2=OWNER)
        lead, created = services.create_lead_from_wa_number(OWNER)
        self.assertEqual((lead, created), (self.lead, False))
        self.assertEqual(self.links(), [(OWNER, '', '')])

    def test_operation_team_number_is_suggested_but_never_merged(self):
        wa_card = Lead.objects.create(source=Lead.SOURCE_WA_INBOUND, phone=OWNER, contact_name='Owner')
        enquiry = make_enquiry(business_name='Other Shop', business_contact_number='+974 4400 9999',
                               operation_team_contact_number='+974 5566 7788')
        lead, _ = services.create_lead_from_pricing_inquiry(enquiry)
        lead.refresh_from_db()
        self.assertIsNone(lead.merged_into_id)
        self.assertIn(wa_card, services.duplicate_candidates(lead))
        self.assertIn(lead, services.duplicate_candidates(wa_card))


class ConfirmationPageTests(ChatLinkBase):
    def test_both_whatsapp_buttons_carry_the_reference(self):
        ref = quote(chat_links.ref_for('P', self.enquiry.pk))
        success = self.client.get('/3pl/inquiry/success/', {'t': str(self.enquiry.quote_token)})
        self.assertContains(success, f'({ref})')
        quote_page = self.client.get(f'/3pl/inquiry/quote/{self.enquiry.quote_token}/')
        self.assertContains(quote_page, f'({ref})')
