# Purpose: Guard the per-session isolation that lets two WhatsApp numbers share one WAHA container.
# Used by: manage.py test whatsapp
# Notes: The failures these cover are silent — cross-session overwrites and merged threads produce no error, just wrong data.

import json
import re
from unittest.mock import patch

from django.db import IntegrityError, transaction
from django.test import TestCase, RequestFactory

from whatsapp import sessions as wa_sessions
from whatsapp.models import WhatsAppContact, WhatsAppMessage


TWO_SESSIONS = [
    {'name': 'default', 'status': 'WORKING', 'phone': '97466451589', 'push_name': 'Ezzy Delivery Qatar'},
    {'name': 'fleet', 'status': 'WORKING', 'phone': '97466124545', 'push_name': 'Ezzy Fleet'},
]


class SessionNormalizeTests(TestCase):
    def test_blank_and_malformed_fall_back_to_default(self):
        for bad in ('', None, '   ', 123, 'has space', 'a/../b', 'x' * 65):
            self.assertEqual(wa_sessions.normalize(bad), 'default', msg=repr(bad))

    def test_valid_names_pass_through(self):
        for good in ('fleet', 'marketing-2', 'ops_1', 'A9'):
            self.assertEqual(wa_sessions.normalize(good), good)

    def test_path_traversal_cannot_reach_waha_url(self):
        """The session name is interpolated into /api/<session>/... paths."""
        self.assertEqual(wa_sessions.normalize('../../api/sessions'), 'default')

    def test_from_request_reads_query_param(self):
        rf = RequestFactory()
        self.assertEqual(wa_sessions.from_request(rf.get('/?session=fleet')), 'fleet')
        self.assertEqual(wa_sessions.from_request(rf.get('/')), 'default')


class MessageUniquenessTests(TestCase):
    """WAHA message ids are unique per chat, not per session."""

    def test_same_id_allowed_on_different_sessions(self):
        WhatsAppMessage.objects.create(
            waha_message_id='false_974555@c.us_ABC', session='default',
            direction='inbound', from_number='974555',
        )
        WhatsAppMessage.objects.create(
            waha_message_id='false_974555@c.us_ABC', session='fleet',
            direction='inbound', from_number='974555',
        )
        self.assertEqual(WhatsAppMessage.objects.count(), 2)

    def test_same_id_rejected_within_one_session(self):
        WhatsAppMessage.objects.create(
            waha_message_id='dup', session='default', direction='inbound',
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                WhatsAppMessage.objects.create(
                    waha_message_id='dup', session='default', direction='inbound',
                )


class ContactUniquenessTests(TestCase):
    """A lid is issued per linked device, so one row per (session, phone)."""

    def test_same_phone_gets_a_row_per_session(self):
        WhatsAppContact.objects.create(session='default', phone='97455512345', lid='111')
        WhatsAppContact.objects.create(session='fleet', phone='97455512345', lid='222')
        lids = set(
            WhatsAppContact.objects.filter(phone='97455512345').values_list('lid', flat=True)
        )
        self.assertEqual(lids, {'111', '222'})

    def test_duplicate_phone_rejected_within_one_session(self):
        WhatsAppContact.objects.create(session='default', phone='97455512345')
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                WhatsAppContact.objects.create(session='default', phone='97455512345')


class WebhookSessionTests(TestCase):
    """The webhook must never let one number overwrite the other's rows."""

    def _post(self, client, session, body):
        payload = {
            'event': 'message',
            'session': session,
            'payload': {
                'id': 'false_97455512345@c.us_SHARED',
                'from': '97455512345@c.us',
                'to': '97466451589@c.us',
                'body': body,
                'timestamp': 1785000000,
                'type': 'chat',
            },
        }
        return client.post(
            '/api/integrations/waha/webhook/',
            data=json.dumps(payload),
            content_type='application/json',
        )

    @patch('whatsapp.waha_views._verify_waha_hmac', return_value=(True, ''))
    def test_same_message_id_on_two_sessions_creates_two_rows(self, _hmac):
        self.assertEqual(self._post(self.client, 'default', 'hello ops').status_code, 200)
        self.assertEqual(self._post(self.client, 'fleet', 'hello fleet').status_code, 200)

        rows = WhatsAppMessage.objects.order_by('session')
        self.assertEqual(rows.count(), 2)
        self.assertEqual(
            [(r.session, r.body) for r in rows],
            [('default', 'hello ops'), ('fleet', 'hello fleet')],
        )

    @patch('whatsapp.waha_views._verify_waha_hmac', return_value=(True, ''))
    def test_redelivery_on_same_session_is_idempotent(self, _hmac):
        self._post(self.client, 'default', 'first')
        self._post(self.client, 'default', 'first')
        self.assertEqual(WhatsAppMessage.objects.count(), 1)

    @patch('whatsapp.waha_views._verify_waha_hmac', return_value=(True, ''))
    def test_unknown_session_name_is_normalized_not_stored_raw(self, _hmac):
        payload = {
            'event': 'message',
            'session': '../../evil',
            'payload': {
                'id': 'x1', 'from': '97455512345@c.us', 'body': 'hi',
                'timestamp': 1785000000, 'type': 'chat',
            },
        }
        self.client.post(
            '/api/integrations/waha/webhook/',
            data=json.dumps(payload), content_type='application/json',
        )
        self.assertEqual(WhatsAppMessage.objects.get(waha_message_id='x1').session, 'default')


class ChatThreadIsolationTests(TestCase):
    """The same customer writing to both numbers must not produce one merged thread."""

    def setUp(self):
        for session, body in (('default', 'to marketing'), ('fleet', 'to ops')):
            WhatsAppMessage.objects.create(
                waha_message_id=f'msg-{session}', session=session,
                direction='inbound', from_number='97455512345',
                to_number='97466451589', body=body,
            )

    def _messages(self, session):
        from whatsapp.wa_chats_view import _messages_response
        rf = RequestFactory()
        req = rf.get(f'/waha/wa-chats/?messages=1&chatId=97455512345@c.us&session={session}')
        # Stub the live WAHA leg — this asserts on the DB half only.
        import requests as _rq
        offline = _rq.exceptions.RequestException('offline')
        with patch('whatsapp.wa_chats_view.requests.get', side_effect=offline):
            resp = _messages_response(req, '97455512345@c.us')
        return json.loads(resp.content)['messages']

    def test_each_session_sees_only_its_own_messages(self):
        self.assertEqual([m['body'] for m in self._messages('default')], ['to marketing'])
        self.assertEqual([m['body'] for m in self._messages('fleet')], ['to ops'])


class ClaimQueueTests(TestCase):
    """The agent claim queue must not silently drain a second number's inbox."""

    def setUp(self):
        for session in ('default', 'fleet'):
            WhatsAppMessage.objects.create(
                waha_message_id=f'q-{session}', session=session,
                direction='inbound', from_number='97455512345', status='received',
            )

    def _list(self, query=''):
        from whatsapp.waha_views import waha_messages_list
        rf = RequestFactory()
        req = rf.get(f'/api/integrations/waha/messages/{query}')
        with patch('whatsapp.waha_views._bearer_ok', return_value=True):
            return json.loads(waha_messages_list(req).content)

    def test_defaults_to_a_single_session(self):
        data = self._list()
        self.assertEqual(data['count'], 1)
        self.assertEqual(data['messages'][0]['session'], 'default')

    def test_session_all_opts_into_cross_session_drain(self):
        self.assertEqual(self._list('?session=all')['count'], 2)

    def test_explicit_session_selects_that_one(self):
        data = self._list('?session=fleet')
        self.assertEqual(data['count'], 1)
        self.assertEqual(data['messages'][0]['session'], 'fleet')


class SessionTabsTests(TestCase):
    def test_no_tabs_rendered_for_a_single_session(self):
        with patch.object(wa_sessions, 'list_sessions', return_value=TWO_SESSIONS[:1]):
            self.assertEqual(wa_sessions.render_tabs('default', '/waha/wa-chats/'), '')

    def test_tabs_rendered_and_active_marked_once_two_exist(self):
        with patch.object(wa_sessions, 'list_sessions', return_value=TWO_SESSIONS):
            html = wa_sessions.render_tabs('fleet', '/waha/wa-chats/')
        self.assertIn('?session=default', html)
        self.assertIn('?session=fleet', html)
        self.assertEqual(html.count('wa-sess__tab--on'), 1)
        self.assertIn('97466124545', html)

    def test_always_shows_the_strip_for_a_lone_session(self):
        """The dashboard must render it even at one session — otherwise there is
        no control to create the second one."""
        with patch.object(wa_sessions, 'list_sessions', return_value=TWO_SESSIONS[:1]):
            html = wa_sessions.render_tabs(
                'default', '/waha/wa-dashboard/', always=True, add_button=True,
            )
        self.assertIn('wa-add-session', html)
        self.assertIn('Add number', html)

    def test_add_button_omitted_unless_requested(self):
        with patch.object(wa_sessions, 'list_sessions', return_value=TWO_SESSIONS):
            self.assertNotIn('wa-add-session', wa_sessions.render_tabs('default', '/x/'))

    def test_session_names_are_escaped_into_the_href(self):
        rows = [dict(TWO_SESSIONS[0]), dict(TWO_SESSIONS[1], push_name='<script>x</script>')]
        with patch.object(wa_sessions, 'list_sessions', return_value=rows):
            html = wa_sessions.render_tabs('default', '/waha/wa-chats/')
        self.assertNotIn('<script>', html)


class SectionRoutesTests(TestCase):
    """The dashboard's routing panel must not claim a number is live on WAHA
    when the route only exists on the Evolution side."""

    def _routes(self):
        return {r['section']: r for r in wa_sessions.section_routes()}

    def test_every_section_is_listed_even_with_no_route_rows(self):
        from core.models import WhatsAppSenderRoute
        routes = self._routes()
        self.assertEqual(set(routes), {s for s, _ in WhatsAppSenderRoute.SECTION_CHOICES})
        for r in routes.values():
            self.assertFalse(r['enabled'])
            self.assertFalse(r['mapped'])
            self.assertEqual(r['session'], 'default')

    def test_route_without_waha_session_is_flagged_unmapped(self):
        from core.models import WhatsAppInstance, WhatsAppSenderRoute
        inst = WhatsAppInstance.objects.create(
            label='Fleet', instance_name='Ezzy-Fleet', phone_number='97466124545',
        )
        WhatsAppSenderRoute.objects.create(section='orders_tasks', instance=inst)
        row = self._routes()['orders_tasks']
        self.assertTrue(row['enabled'])
        self.assertFalse(row['mapped'])
        # Falls back to default rather than claiming the fleet number.
        self.assertEqual(row['session'], 'default')

    def test_route_with_waha_session_resolves_to_it(self):
        from core.models import WhatsAppInstance, WhatsAppSenderRoute
        inst = WhatsAppInstance.objects.create(
            label='Fleet', instance_name='Ezzy-Fleet',
            waha_session='fleet', phone_number='+974 6612 4545',
        )
        WhatsAppSenderRoute.objects.create(section='orders_tasks', instance=inst)
        row = self._routes()['orders_tasks']
        self.assertTrue(row['mapped'])
        self.assertEqual(row['session'], 'fleet')
        self.assertEqual(row['phone'], '97466124545')
        self.assertEqual(wa_sessions.for_section('orders_tasks'), 'fleet')

    def test_disabled_route_falls_back_to_default(self):
        from core.models import WhatsAppInstance, WhatsAppSenderRoute
        inst = WhatsAppInstance.objects.create(
            label='Fleet', instance_name='Ezzy-Fleet', waha_session='fleet',
        )
        WhatsAppSenderRoute.objects.create(
            section='orders_tasks', instance=inst, is_enabled=False,
        )
        self.assertFalse(self._routes()['orders_tasks']['enabled'])
        self.assertEqual(wa_sessions.for_section('orders_tasks'), 'default')


class DashboardRenderTests(TestCase):
    def test_no_placeholder_survives_and_panel_is_present(self):
        from whatsapp.wa_dashboard_view import wa_dashboard
        body = wa_dashboard(RequestFactory().get('/waha/wa-dashboard/')).content.decode()
        for placeholder in ('%SESSION%', '%SESSION_TABS%', '%SESSION_ROUTES%'):
            self.assertNotIn(placeholder, body)
        self.assertIn('wa-routes__hd', body)
        self.assertIn('wa-add-session', body)

    def test_settings_links_open_in_a_new_tab_safely(self):
        """The dashboard cannot write these settings (htpasswd only, no staff
        session), so its links out must not navigate the ops page away."""
        import re
        from whatsapp.wa_dashboard_view import wa_dashboard
        body = wa_dashboard(RequestFactory().get('/waha/wa-dashboard/')).content.decode()
        panel = body[body.index('<div class="wa-routes">'):]
        panel = panel[:panel.index('</div></div>') + 12]

        anchors = re.findall(r'<a [^>]*href="(/workforce/[^"]+)"[^>]*>', panel)
        self.assertIn('/workforce/auto-triggers/whatsapp-instances/', anchors)
        self.assertIn('/workforce/auto-triggers/', anchors)
        for tag in re.findall(r'<a [^>]*href="/workforce/[^"]+"[^>]*>', panel):
            self.assertIn('target="_blank"', tag)
            self.assertIn('rel="noopener"', tag)

    def test_edit_link_is_a_visible_header_action(self):
        from whatsapp.wa_dashboard_view import wa_dashboard
        body = wa_dashboard(RequestFactory().get('/waha/wa-dashboard/')).content.decode()
        self.assertIn('wa-routes__edit', body)
        self.assertIn('Edit settings', body)

    def test_requested_session_reaches_the_page_js(self):
        from whatsapp.wa_dashboard_view import wa_dashboard
        body = wa_dashboard(
            RequestFactory().get('/waha/wa-dashboard/?session=fleet')
        ).content.decode()
        self.assertIn("const SESSION = 'fleet'", body)


class SenderNumberTests(TestCase):
    def test_prefers_the_configured_instance_mapping(self):
        from core.models import WhatsAppInstance
        WhatsAppInstance.objects.create(
            label='Fleet', instance_name='Ezzy-Fleet', waha_session='fleet',
            phone_number='+974 6612 4545',
        )
        with patch.object(wa_sessions, 'list_sessions', return_value=TWO_SESSIONS):
            self.assertEqual(wa_sessions.sender_number('fleet'), '97466124545')

    def test_falls_back_to_the_live_session_when_unmapped(self):
        with patch.object(wa_sessions, 'list_sessions', return_value=TWO_SESSIONS):
            self.assertEqual(wa_sessions.sender_number('default'), '97466451589')

    def setUp(self):
        from django.core.cache import cache
        cache.delete('waha_session_numbers_v1')


class InstancesPickerTests(TestCase):
    """The WAHA Session field on /workforce/auto-triggers/whatsapp-instances/.

    It used to be a free-text box, where a typo failed silently — sends went to
    a session WAHA doesn't have with no clue why.
    """

    def setUp(self):
        from django.contrib.auth.models import User
        self.user = User.objects.create_superuser('picker-test', 'p@t.qa', 'x')
        self.client.force_login(self.user)

    def _get(self):
        return self.client.get(
            '/workforce/auto-triggers/whatsapp-instances/',
            secure=True, SERVER_NAME='ezzydelivery.qa',
        )

    @patch('workforce.views._fetch_whatsapp_instances', return_value={'instances': [], 'error': None})
    @patch.object(wa_sessions, 'list_sessions', return_value=TWO_SESSIONS)
    def test_field_is_a_picker_of_live_sessions(self, _s, _e):
        html = self._get().content.decode()
        self.assertIn('<select class="form-select" name="waha_session"', html)
        self.assertNotIn('type="text" class="form-control" name="waha_session"', html)
        for name in ('default', 'fleet'):
            self.assertIn(f'<option value="{name}">', html)

    @patch('workforce.views._fetch_whatsapp_instances', return_value={'instances': [], 'error': None})
    @patch.object(wa_sessions, 'list_sessions', return_value=TWO_SESSIONS)
    def test_no_template_syntax_leaks_into_the_page(self, _s, _e):
        html = self._get().content.decode()
        self.assertNotIn('{#', html)
        self.assertNotIn('{%', html)

    @patch('workforce.views._fetch_whatsapp_instances', return_value={'instances': [], 'error': None})
    @patch.object(wa_sessions, 'list_sessions', return_value=TWO_SESSIONS)
    def test_row_states_distinguish_linked_from_missing_and_unset(self, _s, _e):
        from core.models import WhatsAppInstance
        WhatsAppInstance.objects.create(
            label='Fleet', instance_name='evo-fleet', waha_session='fleet')
        WhatsAppInstance.objects.create(
            label='Typo', instance_name='evo-typo', waha_session='fleeet')
        WhatsAppInstance.objects.create(label='Blank', instance_name='evo-blank')

        rows = {i.label: i for i in self._get().context['instances']}
        self.assertEqual(rows['Fleet'].waha_state, 'linked')
        self.assertEqual(rows['Typo'].waha_state, 'missing')
        self.assertEqual(rows['Blank'].waha_state, 'unset')

    @patch('workforce.views._fetch_whatsapp_instances', return_value={'instances': [], 'error': None})
    @patch.object(wa_sessions, 'list_sessions', return_value=TWO_SESSIONS)
    def test_orphaned_session_stays_selectable(self, _s, _e):
        """Opening the modal must not silently blank a value WAHA no longer reports."""
        from core.models import WhatsAppInstance
        WhatsAppInstance.objects.create(
            label='Typo', instance_name='evo-typo', waha_session='fleeet')
        resp = self._get()
        self.assertIn('fleeet', resp.context['waha_orphan_sessions'])
        self.assertIn('<option value="fleeet">', resp.content.decode())

    @patch('workforce.views._fetch_whatsapp_instances', return_value={'instances': [], 'error': None})
    @patch.object(wa_sessions, 'list_sessions', return_value=[])
    def test_waha_unreachable_does_not_flag_rows_as_broken(self, _s, _e):
        """WAHA being down must not make every configured row look misconfigured."""
        from core.models import WhatsAppInstance
        WhatsAppInstance.objects.create(
            label='Fleet', instance_name='evo-fleet', waha_session='fleet')
        resp = self._get()
        self.assertTrue(resp.context['waha_unreachable'])
        rows = {i.label: i for i in resp.context['instances']}
        self.assertEqual(rows['Fleet'].waha_state, 'unknown')

    @patch('workforce.views._fetch_whatsapp_instances', return_value={'instances': [], 'error': None})
    @patch.object(wa_sessions, 'list_sessions', return_value=TWO_SESSIONS)
    def test_saving_the_picker_persists_the_session(self, _s, _e):
        from core.models import WhatsAppInstance
        inst = WhatsAppInstance.objects.create(label='Fleet', instance_name='evo-fleet')
        self.client.post(
            '/workforce/auto-triggers/whatsapp-instances/',
            {'action': 'edit', 'instance_id': inst.pk, 'label': 'Fleet',
             'instance_name': 'evo-fleet', 'waha_session': 'fleet',
             'phone_number': '97466124545', 'is_active': '1'},
            secure=True, SERVER_NAME='ezzydelivery.qa',
        )
        inst.refresh_from_db()
        self.assertEqual(inst.waha_session, 'fleet')
        self.assertEqual(wa_sessions.for_instance(inst), 'fleet')

    @patch('workforce.views._fetch_whatsapp_instances', return_value={'instances': [], 'error': None})
    @patch.object(wa_sessions, 'list_sessions', return_value=TWO_SESSIONS)
    def test_both_modals_explain_the_evolution_vs_waha_split(self, _s, _e):
        """The two backend fields naming the same number is the confusing part."""
        html = self._get().content.decode()
        self.assertEqual(html.count('One row = one WhatsApp number'), 2)  # add + edit
        self.assertIn('handle on the external Evolution API', html)
        self.assertIn('handle on our own WAHA bridge', html)

    @patch('workforce.views._fetch_whatsapp_instances', return_value={'instances': [], 'error': None})
    @patch.object(wa_sessions, 'list_sessions', return_value=TWO_SESSIONS)
    def test_edit_modal_field_ids_survive_the_relayout(self, _s, _e):
        """editInstance() sets these by id — reordering the fields must not break it."""
        html = self._get().content.decode()
        for field_id in ('editId', 'editLabel', 'editInstanceName',
                         'editWahaSession', 'editPhone', 'editDefault', 'editActive'):
            self.assertIn(f'id="{field_id}"', html)

    @patch('workforce.views._fetch_whatsapp_instances', return_value={'instances': [], 'error': None})
    @patch.object(wa_sessions, 'list_sessions', return_value=TWO_SESSIONS)
    def test_each_transport_table_stays_aligned(self, _s, _e):
        """Both tables independently: header count == cells in every body row.

        The page used to be ONE table with a colspan group row splitting it into
        an Evolution lane and a WAHA lane. It is now two separate tables, because
        a WAHA session can exist with no instance behind it — a row the merged
        layout had nowhere to put. Alignment still has to hold in each.
        """
        import re
        from core.models import WhatsAppInstance
        WhatsAppInstance.objects.create(
            label='Fleet', instance_name='evo-fleet', waha_session='fleet')
        html = self._get().content.decode()

        tables = re.findall(r'<table[^>]*wai__table.*?</table>', html, re.S)
        self.assertEqual(len(tables), 2, 'expected an Evolution table and a WAHA table')

        for table in tables:
            head = re.search(r'<thead.*?</thead>', table, re.S).group(0)
            # `<th[ >]`, not `<th` — the latter also matches `<thead`.
            cols = len(re.findall(r'<th[ >]', head))
            self.assertGreater(cols, 0)
            body = re.search(r'<tbody>(.*?)</tbody>', table, re.S).group(1)
            for tr in re.findall(r'<tr>(.*?)</tr>', body, re.S):
                self.assertEqual(len(re.findall(r'<td[ >]', tr)), cols)

    @patch('workforce.views._fetch_whatsapp_instances', return_value={'instances': [], 'error': None})
    @patch.object(wa_sessions, 'list_sessions', return_value=TWO_SESSIONS)
    def test_waha_sessions_get_their_own_table(self, _s, _e):
        """A session with no instance pointing at it must still be listed.

        This is the case the old merged layout could not show at all, and the
        reason the page looked like it "wasn't syncing with WAHA".
        """
        html = self._get().content.decode()
        self.assertIn('Self-hosted bridge sessions', html)
        self.assertIn('wai__table--waha', html)
        # Both live sessions appear even though no instance exists at all.
        for name in ('default', 'fleet'):
            self.assertIn(f'value="{name}"', html)

    @patch('workforce.views._fetch_whatsapp_instances', return_value={'instances': [], 'error': None})
    @patch.object(wa_sessions, 'list_sessions', return_value=TWO_SESSIONS)
    def test_modals_split_the_two_senders_into_sections(self, _s, _e):
        html = self._get().content.decode()
        self.assertEqual(html.count('wai__sec--evo'), 2)   # add + edit
        self.assertEqual(html.count('wai__sec--waha'), 2)

    @patch('workforce.views._fetch_whatsapp_instances', return_value={'instances': [], 'error': None})
    @patch.object(wa_sessions, 'list_sessions', return_value=TWO_SESSIONS)
    def test_no_multiline_template_comment_leaks(self, _s, _e):
        """Django's {# #} is single-line only; a wrapped one renders as text."""
        html = self._get().content.decode()
        self.assertNotIn('{#', html)
        self.assertNotIn('{%', html)


class WahaSessionControlTests(TestCase):
    """The WAHA table's write paths: auto-link, link/unlink, and delete.

    These are the two things the page could not do before — it synced Evolution
    only, so a session linked in the WAHA dashboard stayed invisible here; and
    there was no way to remove a session at all.
    """

    URL = '/workforce/auto-triggers/whatsapp-instances/'

    def setUp(self):
        from django.contrib.auth.models import User
        self.user = User.objects.create_superuser('waha-ctl', 'w@t.qa', 'x')
        self.client.force_login(self.user)

    def _post(self, **data):
        return self.client.post(
            self.URL, data, secure=True, SERVER_NAME='ezzydelivery.qa', follow=True)

    @patch('workforce.views._fetch_whatsapp_instances', return_value={'instances': [], 'error': None})
    @patch.object(wa_sessions, 'list_sessions', return_value=TWO_SESSIONS)
    def test_session_auto_links_to_the_instance_with_the_same_number(self, _s, _e):
        """The missing half of the sync: match a live session by phone number."""
        from core.models import WhatsAppInstance
        inst = WhatsAppInstance.objects.create(
            label='Fleet', instance_name='evo-fleet',
            phone_number='+974 6612 4545', waha_session='')
        self.client.get(self.URL, secure=True, SERVER_NAME='ezzydelivery.qa')
        inst.refresh_from_db()
        self.assertEqual(inst.waha_session, 'fleet')

    @patch('workforce.views._fetch_whatsapp_instances', return_value={'instances': [], 'error': None})
    @patch.object(wa_sessions, 'list_sessions', return_value=TWO_SESSIONS)
    def test_auto_link_never_overwrites_a_hand_set_mapping(self, _s, _e):
        from core.models import WhatsAppInstance
        inst = WhatsAppInstance.objects.create(
            label='Fleet', instance_name='evo-fleet',
            phone_number='+974 6612 4545', waha_session='default')
        self.client.get(self.URL, secure=True, SERVER_NAME='ezzydelivery.qa')
        inst.refresh_from_db()
        self.assertEqual(inst.waha_session, 'default')

    @patch('workforce.views._fetch_whatsapp_instances', return_value={'instances': [], 'error': None})
    @patch.object(wa_sessions, 'list_sessions', return_value=TWO_SESSIONS)
    def test_linking_a_session_moves_it_off_any_other_instance(self, _s, _e):
        """One session, one instance — two numbers sending from one device is wrong."""
        from core.models import WhatsAppInstance
        a = WhatsAppInstance.objects.create(
            label='A', instance_name='evo-a', waha_session='fleet')
        b = WhatsAppInstance.objects.create(
            label='B', instance_name='evo-b', waha_session='')
        self._post(action='waha_link', session='fleet', link_instance_id=str(b.id))
        a.refresh_from_db()
        b.refresh_from_db()
        self.assertEqual(a.waha_session, '')
        self.assertEqual(b.waha_session, 'fleet')

    @patch('workforce.views._fetch_whatsapp_instances', return_value={'instances': [], 'error': None})
    @patch.object(wa_sessions, 'list_sessions', return_value=TWO_SESSIONS)
    @patch.object(wa_sessions, 'control')
    def test_default_session_cannot_be_deleted(self, ctl, _s, _e):
        """Every unrouted send falls back to it — deleting it breaks sending silently."""
        resp = self._post(action='waha_delete', session=wa_sessions.default_session())
        ctl.assert_not_called()
        self.assertIn('default session', resp.content.decode())

    @patch('workforce.views._fetch_whatsapp_instances', return_value={'instances': [], 'error': None})
    @patch.object(wa_sessions, 'list_sessions', return_value=TWO_SESSIONS)
    @patch.object(wa_sessions, 'control', return_value=(True, ''))
    def test_deleting_a_session_unlinks_the_instance_pointing_at_it(self, ctl, _s, _e):
        from core.models import WhatsAppInstance
        inst = WhatsAppInstance.objects.create(
            label='Fleet', instance_name='evo-fleet', waha_session='fleet')
        self._post(action='waha_delete', session='fleet')
        ctl.assert_called_once_with('delete', 'fleet')
        inst.refresh_from_db()
        # Left pointing at a session that no longer exists, this number would
        # fall back to the default sender with nothing on screen saying so.
        self.assertEqual(inst.waha_session, '')

    def test_control_refuses_a_name_that_is_not_a_valid_session(self):
        """normalize() would coerce junk to the DEFAULT session — on a delete that
        means destroying the wrong thing. control() must refuse instead."""
        for bad in ('../../etc/passwd', 'a/b', '', None, 'x' * 65):
            ok, err = wa_sessions.control('delete', bad)
            self.assertFalse(ok, bad)
            self.assertEqual(err, 'Invalid session name.')

    @patch.object(wa_sessions, 'list_sessions', return_value=TWO_SESSIONS)
    def test_create_rejects_a_name_waha_already_has(self, _s):
        ok, err = wa_sessions.create_session('fleet')
        self.assertFalse(ok)
        self.assertIn('already exists', err)


PENDING_SESSIONS = [
    {'name': 'default', 'status': 'WORKING', 'phone': '97466451589', 'push_name': 'Ezzy Delivery Qatar'},
    # Exists, but nobody has scanned the QR yet — no device attached.
    {'name': 'fleet', 'status': 'SCAN_QR_CODE', 'phone': '', 'push_name': ''},
]


class SessionExistsIsNotConnectedTests(TestCase):
    """Regression: a session that merely EXISTS was reported as "Linked".

    WAHA lists a session as soon as it is created, long before a phone has
    scanned its QR. Treating "in the list" as "connected" claimed a number was
    live while it was still sitting on the QR screen.
    """

    def setUp(self):
        from django.contrib.auth.models import User
        from core.models import WhatsAppInstance
        self.user = User.objects.create_superuser('pending-test', 'p@t.qa', 'x')
        self.client.force_login(self.user)
        self.inst = WhatsAppInstance.objects.create(
            label='Fleet', instance_name='evo-fleet', waha_session='fleet')

    def _rows(self):
        resp = self.client.get(
            '/workforce/auto-triggers/whatsapp-instances/',
            secure=True, SERVER_NAME='ezzydelivery.qa',
        )
        return resp, {i.label: i for i in resp.context['instances']}

    @patch('workforce.views._fetch_whatsapp_instances', return_value={'instances': [], 'error': None})
    @patch.object(wa_sessions, 'list_sessions', return_value=PENDING_SESSIONS)
    def test_unscanned_session_is_pending_not_linked(self, _s, _e):
        resp, rows = self._rows()
        self.assertEqual(rows['Fleet'].waha_state, 'pending')
        self.assertEqual(rows['Fleet'].waha_status, 'SCAN_QR_CODE')
        html = resp.content.decode()
        # The unscanned state is now spelled out in the WAHA table rather than
        # on the instance row, but it must still be visible and actionable:
        # say what is wrong, and give the way to fix it.
        self.assertIn('qr scan', html.lower())
        self.assertIn('Waiting for QR scan', html)
        self.assertIn('/waha/wa-dashboard/?session=fleet', html)
        # The fleet session must not also be claimed as live anywhere.
        fleet_row = re.search(
            r'<tr>(?:(?!</tr>).)*?value="fleet".*?</tr>', html, re.S).group(0)
        self.assertNotIn('Working', fleet_row)

    @patch('workforce.views._fetch_whatsapp_instances', return_value={'instances': [], 'error': None})
    @patch.object(wa_sessions, 'list_sessions', return_value=TWO_SESSIONS)
    def test_working_session_is_linked(self, _s, _e):
        _resp, rows = self._rows()
        self.assertEqual(rows['Fleet'].waha_state, 'linked')

    @patch('workforce.views._fetch_whatsapp_instances', return_value={'instances': [], 'error': None})
    @patch.object(wa_sessions, 'list_sessions',
                  return_value=[{'name': 'fleet', 'status': 'FAILED', 'phone': '', 'push_name': ''}])
    def test_failed_session_is_pending_and_shows_its_state(self, _s, _e):
        resp, rows = self._rows()
        self.assertEqual(rows['Fleet'].waha_state, 'pending')
        self.assertIn('FAILED', resp.content.decode())


class RoutePanelLivenessTests(TestCase):
    """The dashboard panel must not claim a section is sending from a number
    whose session has no device on it."""

    def _routes(self):
        return {r['section']: r for r in wa_sessions.section_routes()}

    def _route_to(self, waha_session):
        from core.models import WhatsAppInstance, WhatsAppSenderRoute
        inst = WhatsAppInstance.objects.create(
            label='Fleet', instance_name='evo-fleet',
            waha_session=waha_session, phone_number='97466124545')
        WhatsAppSenderRoute.objects.create(section='orders_tasks', instance=inst)

    @patch.object(wa_sessions, 'list_sessions', return_value=PENDING_SESSIONS)
    def test_mapped_but_unscanned_is_not_live(self, _s):
        self._route_to('fleet')
        row = self._routes()['orders_tasks']
        self.assertTrue(row['mapped'])
        self.assertFalse(row['live'])
        self.assertEqual(row['status'], 'SCAN_QR_CODE')

    @patch.object(wa_sessions, 'list_sessions', return_value=TWO_SESSIONS)
    def test_mapped_and_working_is_live(self, _s):
        self._route_to('fleet')
        row = self._routes()['orders_tasks']
        self.assertTrue(row['live'])

    @patch.object(wa_sessions, 'list_sessions', return_value=[])
    def test_waha_unreachable_is_not_reported_as_dead(self, _s):
        """A transient outage must not paint every row as broken."""
        self._route_to('fleet')
        self.assertTrue(self._routes()['orders_tasks']['live'])

    @patch.object(wa_sessions, 'list_sessions', return_value=PENDING_SESSIONS)
    def test_panel_warns_instead_of_showing_the_number(self, _s):
        from django.test import RequestFactory
        from whatsapp.wa_dashboard_view import wa_dashboard
        self._route_to('fleet')
        html = wa_dashboard(RequestFactory().get('/waha/wa-dashboard/')).content.decode()
        self.assertIn('session scan_qr_code', html)
        self.assertIn('wa-routes__num--warn', html)
