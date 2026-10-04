"""
Purpose: Tests for the inbox's "Save to WhatsApp" label editor (POST /waha/wa-chats/set-labels/).
Used by: python manage.py test whatsapp.tests_set_labels
Notes: WAHA is mocked — WAHA's PUT replaces the whole label set, so these pin that we merge the change into the live set.
"""
import json
from unittest import mock

from django.contrib.auth.models import User
from django.test import TestCase

URL = '/waha/wa-chats/set-labels/'
CHAT = '139208513613981@lid'
KNOWN = [{'id': '6', 'name': 'Other Contacts', 'colorHex': '#ff9dff'},
         {'id': '9', 'name': 'Important', 'colorHex': '#ffaf04'},
         {'id': '21', 'name': 'Jobs', 'colorHex': '#00d0e2'}]


class FakeWaha:
    """Stands in for requests.request against WAHA's labels routes."""

    def __init__(self, chat_labels):
        self.chat = list(chat_labels)
        self.puts = []

    def __call__(self, method, url, json=None, headers=None, timeout=None):
        resp = mock.Mock()
        resp.status_code = 200
        if method == 'PUT':
            self.puts.append(json)
            self.chat = [l for l in KNOWN if {'id': l['id']} in json['labels']]
            resp.json.return_value = {}
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
