"""
Purpose: Tests for marketing-only WhatsApp labels — staff login on the inbox, chats hidden outside marketing, and the settings page.
Used by: python manage.py test whatsapp.tests_label_access
Notes: WAHA is mocked; label membership is patched at whatsapp.label_access._waha_get.
"""
import json
from unittest import mock

from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import Client, TestCase

from core.models import Profile
from whatsapp import label_access
from whatsapp.models import RestrictedChatLabel, WhatsAppContact, WhatsAppMessage

SECRET = '97455550001@c.us'
SECRET_LID = '88880001@lid'
OPEN = '97455550002@c.us'
LABELS = [{'id': '5', 'name': 'Campaign VIP', 'colorHex': '#f00'},
          {'id': '6', 'name': 'Clients', 'colorHex': '#0f0'}]


def fake_waha_get(path):
    if path.endswith('/labels/5/chats'):
        return [{'id': {'_serialized': SECRET}}]
    if path.endswith('/labels/6/chats'):
        return [{'id': SECRET}, {'id': OPEN}]
    return None


def make_staff(username, *, mkt=False, ops=False):
    user = User.objects.create_user(username, is_staff=True)
    Profile.objects.create(user=user, first_name='S', last_name='U', phone=11111111, is_staff=True,
                           dept_marketing=mkt, dept_operations=ops)
    return user


class LabelAccessBase(TestCase):
    def setUp(self):
        cache.clear()
        RestrictedChatLabel.objects.create(session='default', label_id='5', label_name='Campaign VIP')
        self.mkt = make_staff('mktdesk', mkt=True)
        self.ops = make_staff('opsdesk', ops=True)
        patcher = mock.patch('whatsapp.label_access._waha_get', side_effect=fake_waha_get)
        patcher.start()
        self.addCleanup(patcher.stop)


class RuleTests(LabelAccessBase):
    def test_marketing_sees_everything(self):
        self.assertFalse(label_access.chat_hidden(self.mkt, 'default', SECRET))

    def test_other_desks_lose_restricted_chats_only(self):
        self.assertTrue(label_access.chat_hidden(self.ops, 'default', SECRET))
        self.assertFalse(label_access.chat_hidden(self.ops, 'default', OPEN))

    def test_other_number_is_unaffected(self):
        self.assertFalse(label_access.chat_hidden(self.ops, 'Ezzy6000', SECRET))

    def test_lid_of_a_restricted_phone_is_hidden_too(self):
        WhatsAppContact.objects.create(session='default', phone='97455550001', lid='88880001')
        self.assertTrue(label_access.chat_hidden(self.ops, 'default', SECRET_LID))

    def test_unreadable_membership_fails_closed(self):
        cache.clear()
        with mock.patch('whatsapp.label_access._waha_get', return_value=None):
            self.assertTrue(label_access.chat_hidden(self.ops, 'default', OPEN))

    def test_last_good_read_covers_an_outage(self):
        label_access.label_chats('default', '5')
        cache.delete('wa_label_chats:default:5')
        with mock.patch('whatsapp.label_access._waha_get', return_value=None):
            self.assertTrue(label_access.chat_hidden(self.ops, 'default', SECRET))
            self.assertFalse(label_access.chat_hidden(self.ops, 'default', OPEN))

    def test_crm_gate_refuses_by_phone_for_other_desks(self):
        from crm.services import wa_read_blocked
        self.assertEqual(wa_read_blocked(['97455550001'], self.ops), label_access.REFUSAL)
        self.assertEqual(wa_read_blocked(['55550001'], self.ops), label_access.REFUSAL)
        self.assertEqual(wa_read_blocked(['97455550001'], self.mkt), '')
        self.assertEqual(wa_read_blocked(['97455550001']), '')


class InboxLoginTests(TestCase):
    def test_anonymous_data_call_is_refused(self):
        resp = self.client.get('/waha/wa-chats/?chats=1')
        self.assertEqual(resp.status_code, 401)

    def test_anonymous_page_goes_to_login(self):
        resp = self.client.get('/waha/wa-chats/', HTTP_ACCEPT='text/html')
        self.assertEqual(resp.status_code, 302)
        self.assertIn('login', resp['Location'])

    def test_non_staff_is_refused(self):
        self.client.force_login(User.objects.create_user('customer1'))
        self.assertEqual(self.client.get('/waha/wa-chats/?chats=1').status_code, 403)

    def test_send_needs_a_csrf_token(self):
        c = Client(enforce_csrf_checks=True)
        c.force_login(User.objects.create_user('st', is_staff=True, is_superuser=True))
        resp = c.post('/waha/wa-chats/send/', data=json.dumps({'to': OPEN, 'text': 'hi'}),
                      content_type='application/json')
        self.assertEqual(resp.status_code, 403)


def fake_waha_json(path, params=None, timeout=15):
    if path.endswith('/chats'):
        return 200, [{'id': {'_serialized': SECRET}}, {'id': {'_serialized': OPEN}}]
    if path.endswith('/labels'):
        return 200, LABELS
    if '/labels/chats/' in path:
        return 200, LABELS
    return 404, None


@mock.patch('whatsapp.wa_chats_view._waha_json', side_effect=fake_waha_json)
class InboxFilterTests(LabelAccessBase):
    def get(self, user, url):
        self.client.force_login(user)
        return self.client.get(url).json()

    def test_chat_list_drops_restricted_chats_for_other_desks(self, _w):
        data = self.get(self.ops, '/waha/wa-chats/?chats=1&session=default')
        self.assertEqual([c['id']['_serialized'] for c in data['chats']], [OPEN])
        self.assertEqual(data['fetched'], 2)  # paging still advances by WAHA's page

    def test_chat_list_is_whole_for_marketing(self, _w):
        data = self.get(self.mkt, '/waha/wa-chats/?chats=1&session=default')
        self.assertEqual(len(data['chats']), 2)

    def test_labels_hide_the_restricted_label_and_its_chats(self, _w):
        data = self.get(self.ops, '/waha/wa-chats/?labels=1&session=default')
        self.assertEqual([l['id'] for l in data['labels']], ['6'])
        self.assertEqual(data['map']['6'], [OPEN])
        self.assertTrue(data['complete'])

    def test_chat_labels_hide_the_restricted_label(self, _w):
        data = self.get(self.ops, f'/waha/wa-chats/?chat_labels=1&session=default&chatId={OPEN}')
        self.assertEqual([l['id'] for l in data['labels']], ['6'])

    def test_opening_a_restricted_chat_is_refused(self, _w):
        self.client.force_login(self.ops)
        for url in (f'/waha/wa-chats/?messages=1&session=default&chatId={SECRET}',
                    f'/waha/wa-chats/?info=1&session=default&chatId={SECRET}',
                    f'/waha/wa-chats/?who=1&session=default&chatId={SECRET}'):
            self.assertEqual(self.client.get(url).status_code, 403, url)

    def test_sending_to_a_restricted_chat_is_refused(self, _w):
        self.client.force_login(self.ops)
        with mock.patch('whatsapp.wa_chats_view.requests.post') as post:
            resp = self.client.post('/waha/wa-chats/send/', data=json.dumps(
                {'to': SECRET, 'text': 'hi', 'session': 'default'}), content_type='application/json')
        self.assertEqual(resp.status_code, 403)
        post.assert_not_called()

    def test_restricted_attachment_is_not_found(self, _w):
        msg = WhatsAppMessage.objects.create(waha_message_id='m1', session='default', direction='inbound',
                                             from_number='97455550001', to_number='97466451589')
        self.client.force_login(self.ops)
        self.assertEqual(self.client.get(f'/waha/wa-chats/media/{msg.pk}/').status_code, 404)

    def test_chat_latest_drops_restricted_numbers(self, _w):
        from django.utils import timezone
        for i, n in enumerate(('97455550001', '97455550002')):
            WhatsAppMessage.objects.create(waha_message_id=f'l{i}', session='default', direction='inbound',
                                           from_number=n, to_number='97466451589', received_at=timezone.now())
        data = self.get(self.ops, '/waha/wa-chats/?chat_latest=1&session=default')
        self.assertNotIn('97455550001', data['latest'])
        self.assertIn('97455550002', data['latest'])


@mock.patch('workforce.wa_label_access_views._number_labels',
            return_value=[{'id': '5', 'name': 'Campaign VIP', 'color': ''},
                          {'id': '6', 'name': 'Clients', 'color': ''}])
@mock.patch('whatsapp.sessions.list_sessions',
            return_value=[{'name': 'default', 'status': 'WORKING', 'phone': '97466451589', 'push_name': 'Ezzy'}])
class SettingsPageTests(TestCase):
    URL = '/workforce/whatsapp/label-access/'

    def setUp(self):
        self.boss = User.objects.create_user('boss', is_staff=True, is_superuser=True)

    def test_super_admin_ticks_labels(self, _s, _l):
        self.client.force_login(self.boss)
        self.assertEqual(self.client.get(self.URL).status_code, 200)
        self.client.post(self.URL, {'session': 'default', 'label': ['6']})
        self.assertEqual(list(RestrictedChatLabel.objects.values_list('label_id', 'label_name')),
                         [('6', 'Clients')])
        self.client.post(self.URL, {'session': 'default'})
        self.assertFalse(RestrictedChatLabel.objects.exists())

    def test_unknown_label_cannot_be_ticked(self, _s, _l):
        self.client.force_login(self.boss)
        self.client.post(self.URL, {'session': 'default', 'label': ['999']})
        self.assertFalse(RestrictedChatLabel.objects.exists())

    def test_marketing_staff_cannot_change_the_rules(self, _s, _l):
        self.client.force_login(make_staff('mkt2', mkt=True))
        self.client.post(self.URL, {'session': 'default', 'label': ['6']})
        self.assertFalse(RestrictedChatLabel.objects.exists())
