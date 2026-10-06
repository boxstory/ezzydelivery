"""
Purpose: Tests for the inbox's "Save to WhatsApp" label editor (POST /waha/wa-chats/set-labels/).
Used by: python manage.py test whatsapp.tests_set_labels
Notes: WAHA is mocked — WAHA's PUT replaces the whole label set, so these pin that we merge the change into the live set.
"""
import json
from unittest import mock

from django.contrib.auth.models import User
from django.test import TestCase

from whatsapp.chat_labels import PALETTE

URL = '/waha/wa-chats/set-labels/'
CREATE_URL = '/waha/wa-chats/create-label/'
CHAT = '139208513613981@lid'
KNOWN = [{'id': '6', 'name': 'Other Contacts', 'colorHex': '#ff9dff'},
         {'id': '9', 'name': 'Important', 'colorHex': '#ffaf04'},
         {'id': '21', 'name': 'Jobs', 'colorHex': '#00d0e2'}]


class FakeWaha:
    """Stands in for requests.request against WAHA's labels routes."""

    def __init__(self, chat_labels):
        self.chat = list(chat_labels)
        self.puts = []
        self.created = []

    def __call__(self, method, url, json=None, headers=None, timeout=None):
        resp = mock.Mock()
        resp.status_code = 200
        if method == 'PUT':
            self.puts.append(json)
            self.chat = [l for l in KNOWN if {'id': l['id']} in json['labels']]
            resp.json.return_value = {}
        elif url.endswith('/labels') and method == 'POST':
            self.created.append((json['name'], json['color']))
            resp.json.return_value = {'id': '90', 'name': json['name'], 'color': json['color'],
                                      'colorHex': PALETTE[json['color']]}
        elif url.endswith('/labels'):
            resp.json.return_value = KNOWN
        else:
            resp.json.return_value = self.chat
        return resp


class SetLabelsTests(TestCase):
    def setUp(self):
        self.client.force_login(User.objects.create_user('inboxstaff', is_staff=True, is_superuser=True))

    def post(self, body, waha):
        with mock.patch('whatsapp.wa_chats_view.requests.request', side_effect=waha):
            return self.client.post(URL, json.dumps(body), content_type='application/json')

    def test_add_keeps_existing_labels(self):
        waha = FakeWaha([KNOWN[1]])
        r = self.post({'session': 'default', 'chatId': CHAT, 'add': ['6'], 'remove': []}, waha)
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(waha.puts, [{'labels': [{'id': '9'}, {'id': '6'}]}])
        self.assertEqual({l['id'] for l in r.json()['labels']}, {'6', '9'})

    def test_remove_only_drops_that_label(self):
        # 'Jobs' was added on the phone after the page loaded — it must survive.
        waha = FakeWaha([KNOWN[1], KNOWN[2]])
        r = self.post({'session': 'default', 'chatId': CHAT, 'add': [], 'remove': ['9']}, waha)
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(waha.puts, [{'labels': [{'id': '21'}]}])

    def test_answer_is_the_written_set_when_the_read_back_lags(self):
        """WAHA can still answer with the pre-PUT set — the reply must not."""
        class LaggyWaha(FakeWaha):
            def __call__(self, method, url, json=None, headers=None, timeout=None):
                resp = super().__call__(method, url, json=json, headers=headers, timeout=timeout)
                if method == 'PUT':
                    self.chat = []  # the change has not surfaced in WA Web yet
                return resp

        waha = LaggyWaha([])
        r = self.post({'session': 'default', 'chatId': CHAT, 'add': ['9'], 'remove': []}, waha)
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual([l['id'] for l in r.json()['labels']], ['9'])
        self.assertEqual(r.json()['labels'][0]['name'], 'Important')

    def test_saving_mirrors_the_labels_onto_the_contact(self):
        """The contact row is the base data — a save must land there too."""
        from whatsapp.models import WhatsAppContact

        WhatsAppContact.objects.create(session='default', phone='97430664611', saved_name='Tayyab')
        waha = FakeWaha([])
        with mock.patch('whatsapp.sessions.list_sessions',
                        return_value=[{'name': 'default', 'status': 'WORKING'}]):
            r = self.post({'session': 'default', 'chatId': '97430664611@c.us',
                           'add': ['9'], 'remove': []}, waha)
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json()['sync'], [])  # only one number is linked here
        contact = WhatsAppContact.objects.get(session='default', phone='97430664611')
        self.assertEqual([l['name'] for l in contact.labels], ['Important'])
        self.assertIsNotNone(contact.labels_synced_at)

    def test_unknown_label_rejected(self):
        waha = FakeWaha([])
        r = self.post({'session': 'default', 'chatId': CHAT, 'add': ['999'], 'remove': []}, waha)
        self.assertEqual(r.status_code, 400)
        self.assertEqual(waha.puts, [])

    def test_bad_session_does_not_fall_back_to_default(self):
        waha = FakeWaha([])
        r = self.post({'session': '../x', 'chatId': CHAT, 'add': ['6']}, waha)
        self.assertEqual(r.status_code, 400)
        self.assertEqual(waha.puts, [])

    def test_bad_chat_id_rejected(self):
        waha = FakeWaha([])
        r = self.post({'session': 'default', 'chatId': '123/../../sessions', 'add': ['6']}, waha)
        self.assertEqual(r.status_code, 400)
        self.assertEqual(waha.puts, [])

    def test_needs_staff_login(self):
        self.client.logout()
        waha = FakeWaha([])
        r = self.post({'session': 'default', 'chatId': CHAT, 'add': ['6']}, waha)
        self.assertEqual(r.status_code, 401)
        self.assertEqual(waha.puts, [])

    def test_csrf_required(self):
        from django.test import Client
        c = Client(enforce_csrf_checks=True)
        c.force_login(User.objects.get(username='inboxstaff'))
        r = c.post(URL, json.dumps({'session': 'default', 'chatId': CHAT, 'add': ['6']}),
                   content_type='application/json')
        self.assertEqual(r.status_code, 403)


class CreateLabelTests(TestCase):
    """The panel's "+ New label": marketing/super-admin only, no duplicates."""

    def setUp(self):
        self.admin = User.objects.create_user('labeladmin', is_staff=True, is_superuser=True)
        self.client.force_login(self.admin)

    def post(self, body, waha):
        with mock.patch('whatsapp.chat_labels.requests.request', side_effect=waha):
            return self.client.post(CREATE_URL, json.dumps(body), content_type='application/json')

    def test_a_new_label_is_created_on_that_number(self):
        waha = FakeWaha([])
        r = self.post({'session': 'default', 'name': ' Needs invoice ', 'color': 16}, waha)
        self.assertEqual(r.status_code, 200, r.content)
        body = r.json()
        self.assertFalse(body['existing'])
        self.assertEqual(body['label']['name'], 'Needs invoice')  # whitespace collapsed
        self.assertEqual(body['label']['colorHex'], '#ffaf04')    # palette index 16
        self.assertEqual(waha.created, [('Needs invoice', 16)])

    def test_an_existing_name_is_handed_back_instead_of_duplicated(self):
        waha = FakeWaha([])
        r = self.post({'session': 'default', 'name': 'jobs', 'color': 3}, waha)
        self.assertEqual(r.status_code, 200, r.content)
        self.assertTrue(r.json()['existing'])
        self.assertEqual(r.json()['label']['id'], '21')  # the real 'Jobs'
        self.assertEqual(waha.created, [])

    def test_a_blank_name_is_refused(self):
        waha = FakeWaha([])
        r = self.post({'session': 'default', 'name': '   ', 'color': 1}, waha)
        self.assertEqual(r.status_code, 400)
        self.assertEqual(waha.created, [])

    def test_an_off_palette_colour_falls_back(self):
        waha = FakeWaha([])
        r = self.post({'session': 'default', 'name': 'Tidy up', 'color': 99}, waha)
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(waha.created, [('Tidy up', 4)])

    def test_staff_outside_marketing_cannot_create(self):
        ops = User.objects.create_user('opsonly', is_staff=True)
        # Open the number so the 403 asserted below is the marketing rule, not the number gate.
        from whatsapp.models import InboxSessionAccess
        InboxSessionAccess.objects.create(user=ops, session='default')  # inbox number gate
        self.client.force_login(ops)
        waha = FakeWaha([])
        r = self.post({'session': 'default', 'name': 'Ops label', 'color': 1}, waha)
        self.assertEqual(r.status_code, 403)
        self.assertEqual(waha.created, [])

    def test_bad_session_does_not_fall_back_to_default(self):
        waha = FakeWaha([])
        r = self.post({'session': '../x', 'name': 'Sneaky', 'color': 1}, waha)
        self.assertEqual(r.status_code, 400)
        self.assertEqual(waha.created, [])

    def test_a_full_number_says_so_instead_of_failing_opaquely(self):
        """WhatsApp holds 20 labels per number, built-ins included."""
        class FullWaha(FakeWaha):
            def __call__(self, method, url, json=None, headers=None, timeout=None):
                resp = super().__call__(method, url, json=json, headers=headers, timeout=timeout)
                if method == 'GET' and url.endswith('/labels'):
                    resp.json.return_value = [{'id': str(i), 'name': f'L{i}', 'colorHex': ''}
                                              for i in range(20)]
                return resp

        waha = FullWaha([])
        r = self.post({'session': 'default', 'name': 'One too many', 'color': 1}, waha)
        self.assertEqual(r.status_code, 400)
        self.assertIn('maximum of 20', r.json()['error'])
        self.assertEqual(waha.created, [])

    def test_whatsapps_own_refusal_reaches_the_user(self):
        class RefusingWaha(FakeWaha):
            def __call__(self, method, url, json=None, headers=None, timeout=None):
                resp = super().__call__(method, url, json=json, headers=headers, timeout=timeout)
                if method == 'POST':
                    resp.status_code = 422
                    resp.json.return_value = {'message': 'Maximum 20 labels allowed'}
                return resp

        waha = RefusingWaha([])
        r = self.post({'session': 'default', 'name': 'Nope', 'color': 1}, waha)
        self.assertEqual(r.status_code, 502)
        self.assertEqual(r.json()['error'], 'Maximum 20 labels allowed')

    def test_csrf_required(self):
        from django.test import Client

        c = Client(enforce_csrf_checks=True)
        c.force_login(self.admin)
        r = c.post(CREATE_URL, json.dumps({'session': 'default', 'name': 'X', 'color': 1}),
                   content_type='application/json')
        self.assertEqual(r.status_code, 403)
