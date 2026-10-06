"""
Purpose: Tests for whatsapp/chat_labels.py — the WhatsAppContact label mirror and the push of a label onto our other numbers.
Used by: python manage.py test whatsapp.tests_chat_labels
Notes: WAHA is mocked per session. Label ids differ per number on purpose, so these pin that a label crosses by NAME.
"""
import json
from unittest import mock

from django.core.cache import cache
from django.test import TestCase

from whatsapp import chat_labels
from whatsapp.models import WhatsAppContact, WhatsAppMessage

PHONE = '97430664611'
CHAT = f'{PHONE}@c.us'

# The real shape of our three numbers: ids overlap, names do not line up.
LABELS = {
    'default': [{'id': '7', 'name': 'Driver', 'color': 19, 'colorHex': '#9368cf'},
                {'id': '16', 'name': 'Form submitted', 'color': 2, 'colorHex': '#ffd429'}],
    'Ezzy6000': [{'id': '13', 'name': 'Driver', 'color': 19, 'colorHex': '#9368cf'}],
    'FleetAdmin4545': [{'id': '5', 'name': 'Drivers', 'color': 10, 'colorHex': '#00d0e2'}],
}


class FakeWaha:
    """requests.request against WAHA's labels + chat-messages routes, per session."""

    LIDS = {PHONE: '254000825925805@lid'}

    def __init__(self, chats=None, messages=None, refuse=()):
        self.labels = {k: [dict(l) for l in v] for k, v in LABELS.items()}
        self.chats = {k: list(v) for k, v in (chats or {}).items()}   # session -> [label id]
        self.messages = messages or {}                                # session -> [message dict]
        self.refuse = set(refuse)                                     # sessions whose PUT fails
        self.created = []
        self.puts = []
        self.ignored = []   # writes WhatsApp accepted and silently dropped
        self._next_id = 90

    def __call__(self, method, url, json=None, headers=None, timeout=None):
        path = url.split('/api/', 1)[1]
        session, rest = path.split('/', 1)
        resp = mock.Mock()
        resp.status_code = 200
        body = {}
        if rest.startswith('lids/pn/'):
            phone = rest.rsplit('/', 1)[1]
            lid = self.LIDS.get(phone)
            body = {'lid': lid, 'pn': f'{phone}@c.us'} if lid else {'lid': None, 'pn': None}
        elif rest.startswith('labels/chats/'):
            addressed = rest.split('labels/chats/', 1)[1].strip('/')
            if method == 'PUT':
                ids = [l['id'] for l in json['labels']]
                if session in self.refuse:
                    resp.status_code = 502
                elif not addressed.endswith('@lid'):
                    # WhatsApp answers 200 and applies nothing — see
                    # chat_labels.canonical_chat_id().
                    self.ignored.append((session, addressed, ids))
                else:
                    self.puts.append((session, ids))
                    self.chats[session] = ids
            else:
                ids = set(self.chats.get(session) or [])
                body = [l for l in self.labels[session] if l['id'] in ids]
        elif rest.startswith('labels'):
            if method == 'POST':
                row = {'id': str(self._next_id), 'name': json['name'],
                       'color': json['color'], 'colorHex': chat_labels.PALETTE[json['color']]}
                self._next_id += 1
                self.labels[session].append(row)
                self.created.append((session, json['name'], json['color']))
                body = row
            else:
                body = self.labels[session]
        elif '/messages' in rest:
            body = self.messages.get(session, [])
        resp.json.return_value = body
        return resp


def patched(waha):
    return mock.patch('whatsapp.chat_labels.requests.request', side_effect=waha)


def sessions_live(*names):
    rows = [{'name': n, 'status': 'WORKING', 'phone': '', 'push_name': ''} for n in names]
    return mock.patch('whatsapp.sessions.list_sessions', return_value=rows)


class NameMatchingTests(TestCase):
    def test_plural_and_case_are_the_same_label(self):
        self.assertEqual(chat_labels.norm('Drivers'), chat_labels.norm('driver'))
        self.assertEqual(chat_labels.norm('Clients'), chat_labels.norm('Client'))

    def test_a_short_or_double_s_name_is_not_singularised(self):
        self.assertNotEqual(chat_labels.norm('Ads'), chat_labels.norm('Ad'))
        self.assertEqual(chat_labels.norm('Express'), 'express')

    def test_exact_name_wins_over_a_plural_near_match(self):
        rows = [{'id': '1', 'name': 'Drivers'}, {'id': '2', 'name': 'Driver'}]
        self.assertEqual(chat_labels.find_label(rows, 'Driver')['id'], '2')
        self.assertEqual(chat_labels.find_label(rows, 'Drivers')['id'], '1')


class MirrorTests(TestCase):
    def test_labels_land_on_the_contact_row(self):
        WhatsAppContact.objects.create(session='default', phone=PHONE, saved_name='Tayyab')
        self.assertTrue(chat_labels.store('default', CHAT, LABELS['default']))
        contact = WhatsAppContact.objects.get(session='default', phone=PHONE)
        self.assertEqual([l['name'] for l in contact.labels], ['Driver', 'Form submitted'])
        self.assertIsNotNone(contact.labels_synced_at)
        self.assertEqual(chat_labels.contact_labels('default', PHONE), contact.labels)

    def test_a_lid_chat_is_resolved_through_the_directory_only(self):
        # Never mint a phone from a lid: with no directory row there is nowhere
        # to store, and the lid must not become a '974…' number.
        self.assertEqual(chat_labels.chat_phone('default', '139208513613981@lid'), '')
        self.assertFalse(chat_labels.store('default', '139208513613981@lid', LABELS['default']))
        WhatsAppContact.objects.create(session='default', phone=PHONE, lid='139208513613981')
        self.assertEqual(chat_labels.chat_phone('default', '139208513613981@lid'), PHONE)
        self.assertTrue(chat_labels.store('default', '139208513613981@lid', LABELS['default']))

    def test_a_group_chat_is_skipped(self):
        self.assertEqual(chat_labels.chat_phone('default', '120363040000000000@g.us'), '')
        self.assertFalse(chat_labels.store('default', '120363040000000000@g.us', LABELS['default']))

    def test_removing_every_label_empties_the_mirror(self):
        chat_labels.store('default', CHAT, LABELS['default'])
        chat_labels.store('default', CHAT, [])
        self.assertEqual(WhatsAppContact.objects.get(session='default', phone=PHONE).labels, [])


class MirroredMapTests(TestCase):
    def test_a_contact_contributes_both_of_its_chat_ids(self):
        WhatsAppContact.objects.create(session='default', phone=PHONE, lid='139208513613981',
                                       labels=[{'id': '7', 'name': 'Driver', 'colorHex': ''}])
        WhatsAppContact.objects.create(session='default', phone='97455500011',
                                       labels=[{'id': '7', 'name': 'Driver', 'colorHex': ''}])
        WhatsAppContact.objects.create(session='default', phone='97455500022')  # no labels
        mapped = chat_labels.mirrored_map('default')
        self.assertEqual(list(mapped), ['7'])  # the unlabelled contact adds nothing
        self.assertEqual(set(mapped['7']),
                         {f'{PHONE}@c.us', '139208513613981@lid', '97455500011@c.us'})

    def test_another_number_is_not_mixed_in(self):
        WhatsAppContact.objects.create(session='Ezzy6000', phone=PHONE,
                                       labels=[{'id': '13', 'name': 'Driver', 'colorHex': ''}])
        self.assertEqual(chat_labels.mirrored_map('default'), {})


class HasRealChatTests(TestCase):
    def test_our_own_message_rows_are_enough(self):
        WhatsAppMessage.objects.create(waha_message_id='m1', session='Ezzy6000',
                                       direction='inbound', from_number=PHONE, body='hi')
        waha = FakeWaha()
        with patched(waha):
            self.assertTrue(chat_labels.has_real_chat('Ezzy6000', PHONE))

    def test_an_encryption_notice_is_not_a_conversation(self):
        # Every number gets one of these the moment keys are exchanged — it must
        # not be read as "this number already chats them".
        waha = FakeWaha(messages={'Ezzy6000': [
            {'id': 'x', 'fromMe': False, 'body': '', 'hasMedia': False,
             '_data': {'type': 'e2e_notification'}}]})
        with patched(waha):
            self.assertFalse(chat_labels.has_real_chat('Ezzy6000', PHONE))

    def test_a_real_message_counts(self):
        waha = FakeWaha(messages={'Ezzy6000': [
            {'id': 'x', 'fromMe': False, 'body': '', 'hasMedia': False,
             '_data': {'type': 'e2e_notification'}},
            {'id': 'y', 'fromMe': True, 'body': 'Welcome', '_data': {'type': 'chat'}}]})
        with patched(waha):
            self.assertTrue(chat_labels.has_real_chat('Ezzy6000', PHONE))


class WriteTargetTests(TestCase):
    """A label write must be addressed to the lid; WhatsApp drops a '@c.us' PUT."""

    def setUp(self):
        cache.clear()

    def test_a_write_goes_to_the_lid_not_the_phone(self):
        waha = FakeWaha(chats={'default': []})
        with patched(waha):
            self.assertEqual(chat_labels.canonical_chat_id('default', CHAT), '254000825925805@lid')
            self.assertEqual(chat_labels.put_chat_labels('default', CHAT, ['7']), 200)
        self.assertEqual(waha.puts, [('default', ['7'])])
        self.assertEqual(waha.ignored, [])  # nothing silently dropped

    def test_a_lid_or_group_id_is_passed_through_untouched(self):
        waha = FakeWaha()
        with patched(waha):
            self.assertEqual(chat_labels.canonical_chat_id('default', '139208513613981@lid'),
                             '139208513613981@lid')
            self.assertEqual(chat_labels.canonical_chat_id('default', '120363040000000000@g.us'),
                             '120363040000000000@g.us')

    def test_a_phone_with_no_lid_keeps_its_own_id(self):
        waha = FakeWaha()
        with patched(waha):
            self.assertEqual(chat_labels.canonical_chat_id('default', '97400000000@c.us'),
                             '97400000000@c.us')

    def test_the_lid_lookup_is_cached_per_number(self):
        waha = FakeWaha()
        with patched(waha) as sent:
            chat_labels.canonical_chat_id('default', CHAT)
            chat_labels.canonical_chat_id('default', CHAT)
        lookups = [c for c in sent.call_args_list if '/lids/pn/' in c.args[1]]
        self.assertEqual(len(lookups), 1)  # a contact's lid does not change
        self.assertEqual(cache.get(f'wa_lid_for_pn:default:{PHONE}'), '254000825925805@lid')


class ConfirmTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_confirmed_when_whatsapp_reports_the_written_set(self):
        waha = FakeWaha(chats={'default': ['7', '16']})
        with patched(waha):
            self.assertTrue(chat_labels.confirm_chat_labels('default', CHAT, ['16', '7']))

    def test_not_confirmed_when_the_write_did_not_take(self):
        waha = FakeWaha(chats={'default': ['16']})
        with patched(waha):
            self.assertFalse(chat_labels.confirm_chat_labels('default', CHAT, ['16', '7'],
                                                             retry_after=0))


class PropagateTests(TestCase):
    def setUp(self):
        cache.clear()
        for session in ('default', 'Ezzy6000', 'FleetAdmin4545'):
            WhatsAppContact.objects.create(session=session, phone=PHONE, saved_name='Tayyab')
            WhatsAppMessage.objects.create(waha_message_id=f'm-{session}', session=session,
                                           direction='inbound', from_number=PHONE, body='hi')

    def test_label_crosses_to_the_other_numbers_by_name(self):
        waha = FakeWaha(chats={'default': ['7']})
        with patched(waha), sessions_live('default', 'Ezzy6000', 'FleetAdmin4545'):
            report = chat_labels.propagate('default', CHAT, ['Driver'], [])
        done = {r['session']: r for r in report}
        self.assertEqual(done['Ezzy6000']['added'], ['Driver'])
        self.assertEqual(done['FleetAdmin4545']['added'], ['Drivers'])  # matched, not created
        self.assertEqual(waha.created, [])
        self.assertEqual(sorted(waha.puts), [('Ezzy6000', ['13']), ('FleetAdmin4545', ['5'])])
        self.assertEqual([l['name'] for l in chat_labels.contact_labels('Ezzy6000', PHONE)], ['Driver'])

    def test_a_label_the_other_number_lacks_is_created_there(self):
        waha = FakeWaha(chats={'default': ['16']})
        with patched(waha), sessions_live('default', 'Ezzy6000'):
            report = chat_labels.propagate('default', CHAT, ['Form submitted'], [])
        self.assertEqual(report[0]['created'], ['Form submitted'])
        # Created with the colour it has on the number it came from, as a
        # palette index — WAHA rejects a hex that is not in the palette.
        self.assertEqual(waha.created, [('Ezzy6000', 'Form submitted', 2)])
        self.assertEqual(waha.puts, [('Ezzy6000', ['90'])])

    def test_labels_set_on_the_other_phone_survive(self):
        waha = FakeWaha(chats={'default': ['7'], 'Ezzy6000': ['13']})
        waha.labels['Ezzy6000'].append({'id': '12', 'name': 'New order', 'color': 1, 'colorHex': '#64c4ff'})
        waha.chats['Ezzy6000'] = ['12']
        with patched(waha), sessions_live('default', 'Ezzy6000'):
            chat_labels.propagate('default', CHAT, ['Driver'], [])
        self.assertEqual(waha.puts, [('Ezzy6000', ['12', '13'])])

    def test_a_removal_crosses_too(self):
        waha = FakeWaha(chats={'default': [], 'Ezzy6000': ['13']})
        with patched(waha), sessions_live('default', 'Ezzy6000'):
            report = chat_labels.propagate('default', CHAT, [], ['Driver'])
        self.assertEqual(report[0]['removed'], ['Driver'])
        self.assertEqual(waha.puts, [('Ezzy6000', [])])

    def test_a_number_without_a_conversation_is_skipped(self):
        WhatsAppMessage.objects.filter(session='Ezzy6000').delete()
        waha = FakeWaha(chats={'default': ['7']})
        with patched(waha), sessions_live('default', 'Ezzy6000'):
            report = chat_labels.propagate('default', CHAT, ['Driver'], [])
        self.assertEqual(report[0]['error'], 'no chat on this number')
        self.assertEqual(waha.puts, [])

    def test_a_refusal_is_reported_not_raised(self):
        waha = FakeWaha(chats={'default': ['7']}, refuse={'Ezzy6000'})
        with patched(waha), sessions_live('default', 'Ezzy6000'):
            report = chat_labels.propagate('default', CHAT, ['Driver'], [])
        self.assertIn('refused', report[0]['error'])
        self.assertEqual(report[0]['added'], [])
        self.assertEqual(chat_labels.contact_labels('Ezzy6000', PHONE), [])

    def test_a_number_that_never_met_the_contact_is_not_touched(self):
        WhatsAppContact.objects.filter(session='FleetAdmin4545').delete()
        waha = FakeWaha(chats={'default': ['7']})
        with patched(waha), sessions_live('default', 'Ezzy6000', 'FleetAdmin4545'):
            report = chat_labels.propagate('default', CHAT, ['Driver'], [])
        self.assertEqual([r['session'] for r in report], ['Ezzy6000'])


class PushCommandTests(TestCase):
    """manage.py push_wa_chat_labels — the backfill of labels set before the live push, or on a phone."""

    def setUp(self):
        cache.clear()
        for session in ('default', 'Ezzy6000'):
            WhatsAppMessage.objects.create(waha_message_id=f'm-{session}', session=session,
                                           direction='inbound', from_number=PHONE, body='hi')
        WhatsAppContact.objects.create(session='default', phone=PHONE, labels=[
            {'id': '7', 'name': 'Driver', 'colorHex': '#9368cf'},
            {'id': '3', 'name': 'Unread', 'colorHex': '#99b6c1'}])
        WhatsAppContact.objects.create(session='Ezzy6000', phone=PHONE, labels=[])

    def run_cmd(self, waha, *extra):
        from io import StringIO

        from django.core.management import call_command
        out = StringIO()
        with patched(waha), sessions_live('default', 'Ezzy6000'):
            call_command('push_wa_chat_labels', '--no-refresh', *extra, stdout=out, stderr=out)
        return out.getvalue()

    def test_a_dry_run_writes_nothing(self):
        waha = FakeWaha(chats={'default': ['7']})
        out = self.run_cmd(waha)
        self.assertIn('Ezzy6000 would get +Driver (from default)', out)
        self.assertEqual(waha.puts, [])

    def test_apply_copies_the_label_and_skips_list_filters(self):
        waha = FakeWaha(chats={'default': ['7']})
        self.run_cmd(waha, '--apply')
        self.assertEqual(waha.puts, [('Ezzy6000', ['13'])])   # Driver only, never Unread
        self.assertEqual([l['name'] for l in chat_labels.contact_labels('Ezzy6000', PHONE)], ['Driver'])

    def test_it_copies_both_ways(self):
        WhatsAppContact.objects.filter(session='Ezzy6000').update(labels=[
            {'id': '13', 'name': 'Driver', 'colorHex': '#9368cf'},
            {'id': '12', 'name': 'New order', 'colorHex': '#64c4ff'}])
        waha = FakeWaha(chats={'default': ['7'], 'Ezzy6000': ['13', '12']})
        waha.labels['Ezzy6000'].append({'id': '12', 'name': 'New order', 'color': 1, 'colorHex': '#64c4ff'})
        self.run_cmd(waha, '--apply')
        self.assertEqual(waha.created, [('default', 'New order', 1)])
        self.assertEqual(waha.puts, [('default', ['7', '90'])])

    def test_labels_limits_the_copy_to_those_names(self):
        WhatsAppContact.objects.filter(session='Ezzy6000').update(labels=[
            {'id': '12', 'name': 'New order', 'colorHex': '#64c4ff'}])
        waha = FakeWaha(chats={'default': ['7'], 'Ezzy6000': ['12']})
        waha.labels['Ezzy6000'].append({'id': '12', 'name': 'New order', 'color': 1, 'colorHex': '#64c4ff'})
        self.run_cmd(waha, '--apply', '--labels', 'Drivers')
        self.assertEqual(waha.created, [])                     # New order not copied to default
        self.assertEqual(waha.puts, [('Ezzy6000', ['12', '13'])])

    def test_a_number_without_a_conversation_is_left_alone(self):
        WhatsAppMessage.objects.filter(session='Ezzy6000').delete()
        waha = FakeWaha(chats={'default': ['7']})
        out = self.run_cmd(waha, '--apply')
        self.assertIn('skipped, no conversation', out)
        self.assertEqual(waha.puts, [])
