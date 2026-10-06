"""
Purpose: Tests for the inbox number gate — staff open only the WhatsApp numbers ticked for them on Staff Roles.
Used by: python manage.py test whatsapp.tests_session_access
Notes: WAHA is unreachable under TESTING, so list_sessions() falls back to the single default number.
"""
from unittest import mock

from django.contrib.auth import get_user_model
from django.http import HttpResponse
from django.test import TestCase

from core.models import Profile
from whatsapp import session_access
from whatsapp import sessions as wa_sessions
from whatsapp.models import InboxSessionAccess, WhatsAppMessage

User = get_user_model()
KW = {'HTTP_HOST': 'ezzydelivery.qa', 'secure': True}
THREE = [
    {'name': 'default', 'status': 'WORKING', 'phone': '97470000001', 'push_name': 'Ezzy Delivery Qatar'},
    {'name': 'Ezzy6000', 'status': 'WORKING', 'phone': '97470000002', 'push_name': 'Ezzy delivery Bot'},
    {'name': 'FleetAdmin4545', 'status': 'WORKING', 'phone': '97470000003', 'push_name': 'Ezzy Fleet Admin'},
]


class InboxNumberGateTests(TestCase):

    def setUp(self):
        self.user = User.objects.create_user('numgate', is_staff=True)
        Profile.objects.create(user=self.user, is_staff=True, dept_marketing=True)
        self.client.force_login(self.user)

    def grant(self, *sessions):
        for s in sessions:
            InboxSessionAccess.objects.create(user=self.user, session=s)

    def page(self, session=None):
        params = {'session': session} if session else {}
        return self.client.get('/waha/wa-chats/', params, HTTP_ACCEPT='text/html', **KW)

    def test_no_number_means_no_inbox(self):
        r = self.page()
        self.assertEqual(r.status_code, 403)
        self.assertIn(b'No WhatsApp number is open to you', r.content)

    def test_open_number_loads(self):
        self.grant('default')
        self.assertEqual(self.page().status_code, 200)

    def test_closed_number_redirects_to_an_open_one(self):
        self.grant('Ezzy6000')
        r = self.page('default')
        self.assertRedirects(r, '/waha/wa-chats/?session=Ezzy6000', fetch_redirect_response=False)

    def test_json_call_on_a_closed_number_is_refused(self):
        self.grant('default')
        r = self.client.get('/waha/wa-chats/', {'names': 1, 'ids': '97455@c.us', 'session': 'Ezzy6000'}, **KW)
        self.assertEqual(r.status_code, 403)
        self.assertEqual(r.json()['error'], session_access.REFUSAL)

    def test_number_in_the_post_body_is_checked(self):
        self.grant('default')
        r = self.client.post('/waha/wa-chats/read/', data='{"session": "Ezzy6000", "chatId": "97455@c.us"}',
                             content_type='application/json', **KW)
        self.assertEqual(r.status_code, 403)

    def test_number_in_a_multipart_form_is_checked(self):
        self.grant('default')
        r = self.client.post('/waha/wa-chats/send-media/', {'session': 'Ezzy6000', 'to': '97455@c.us'}, **KW)
        self.assertEqual(r.status_code, 403)

    def test_stored_media_is_gated_on_the_messages_own_number(self):
        """media/<id>/ carries no ?session=, so a known id must not reach another number."""
        self.grant('default')
        mine = WhatsAppMessage.objects.create(waha_message_id='a', session='default', direction='inbound')
        other = WhatsAppMessage.objects.create(waha_message_id='b', session='FleetAdmin4545', direction='inbound')
        with mock.patch('workforce.crm_views._stream_wa_media', return_value=HttpResponse('file')):
            self.assertEqual(self.client.get(f'/waha/wa-chats/media/{other.pk}/', **KW).status_code, 404)
            self.assertEqual(self.client.get(f'/waha/wa-chats/media/{mine.pk}/', **KW).status_code, 200)

    def test_super_admin_opens_every_number_without_rows(self):
        boss = User.objects.create_user('numboss', is_staff=True, is_superuser=True)
        self.client.force_login(boss)
        self.assertEqual(self.page('FleetAdmin4545').status_code, 200)
        self.assertIsNone(session_access.allowed(boss))

    def test_tab_strip_lists_only_open_numbers(self):
        self.grant('default', 'Ezzy6000')
        with mock.patch.object(wa_sessions, 'list_sessions', return_value=THREE):
            html = self.page('default').content.decode()
        self.assertIn('Ezzy delivery Bot', html)
        self.assertNotIn('Ezzy Fleet Admin', html)
