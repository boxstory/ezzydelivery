"""
Purpose: Tests for the Send To scope — which recipients each Auto Flow trigger can feed.
Used by: python manage.py test core.tests_auto_flow_triggers
Notes: test_every_fired_trigger_is_registered is the load-bearing one. A trigger added to
       the code but not to TRIGGER_FEEDS reads as inert, which tells staff the flow will
       never fire — a confident lie. The registry is the only defence, so the test scans
       the source for the calls rather than trusting anyone to remember.
"""

import os
import re

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from core import models as core_models
from core.auto_flow_triggers import (
    RECIPIENTS, SUBJECT_INERT, SUBJECT_NONE, SUBJECT_ORDER, SUBJECT_PERSON,
    SUBJECT_TASK, SUBJECT_UNSET, TRIGGER_FEEDS, allowed_recipients,
    default_recipient, recipient_groups, recipients_for, scope_map,
    trigger_feed, trigger_note,
)

User = get_user_model()

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APPS = ('core', 'orders', 'delivery', 'workforce', 'crm', 'dispatch', 'ezzy_api',
        'fleet', 'business', 'whatsapp')


def _source_files():
    for app in APPS:
        for root, _dirs, files in os.walk(os.path.join(BASE_DIR, app)):
            if 'migrations' in root or '__pycache__' in root:
                continue
            for name in files:
                if name.endswith('.py'):
                    yield os.path.join(root, name)


def _fired_trigger_keys():
    """Every trigger key the code actually runs flows for.

    Covers the two call sites' literals plus the status→trigger map in
    delivery/signals.py, which passes its keys through a variable.
    """
    calls = re.compile(r"(?:execute_flows_for_trigger|fire_lead_trigger)\(\s*'([a-z0-9_]+)'")
    keys = set()
    for path in _source_files():
        with open(path, encoding='utf-8') as fh:
            body = fh.read()
        keys.update(calls.findall(body))
        # 'delivered': 'wa_delivered', … — the wa_* keys never appear in a call
        if path.endswith(os.path.join('delivery', 'signals.py')):
            block = re.search(r'wa_trigger_map\s*=\s*\{(.*?)\}', body, re.DOTALL)
            if block:
                keys.update(re.findall(r":\s*'([a-z0-9_]+)'", block.group(1)))
    return keys


class RegistryCoverageTests(TestCase):
    """The map has to match what the code really does, or it misleads."""

    def test_every_fired_trigger_is_registered(self):
        missing = sorted(_fired_trigger_keys() - set(TRIGGER_FEEDS))
        self.assertFalse(
            missing,
            'These triggers run flows but are not in TRIGGER_FEEDS, so the form will '
            'tell staff they never fire: ' + ', '.join(missing))

    def test_the_scan_finds_the_calls_at_all(self):
        """Guards the test above: a broken regex would pass it silently."""
        found = _fired_trigger_keys()
        self.assertGreater(len(found), 20)
        self.assertIn('staff_task_status_change', found)
        self.assertIn('lead_created', found)
        self.assertIn('wa_delivered', found)

    def test_every_registered_trigger_is_a_known_trigger_key(self):
        """AutoTriggerConfig rows are data, so the code-level list on the Auto
        Triggers page is what a key is checked against — a typo here would
        silently scope a trigger nobody has."""
        from workforce.views import TRIGGER_DOMAINS
        unknown = sorted(set(TRIGGER_FEEDS) - set(TRIGGER_DOMAINS))
        self.assertFalse(unknown, 'Not a known trigger key: ' + str(unknown))

    def test_every_recipient_value_is_handled_by_the_resolver(self):
        """A value the executor never checks resolves to nobody, silently."""
        path = os.path.join(BASE_DIR, 'core', 'auto_flow_executor.py')
        with open(path, encoding='utf-8') as fh:
            body = fh.read()
        resolver = body.split('def _resolve_recipient_phones', 1)[1].split('\ndef ', 1)[0]
        for rec in RECIPIENTS:
            with self.subTest(recipient=rec['value']):
                self.assertIn(f"'{rec['value']}'", resolver)

    def test_a_note_exists_for_every_subject(self):
        for key in list(TRIGGER_FEEDS) + ['', 'not_a_trigger']:
            with self.subTest(trigger=key):
                note = trigger_note(key)
                self.assertTrue(note['text'])
                self.assertIn(note['level'], ('none', 'ok', 'warn', 'danger'))


class ScopeTests(TestCase):
    """What each kind of trigger may be sent to."""

    def test_a_task_trigger_can_reach_everyone(self):
        allowed = allowed_recipients('staff_task_status_change')
        for value in ('customer', 'driver_whatsapp', 'zone_drivers', 'seller'):
            self.assertIn(value, allowed)
        # It is about an order, not about one person with a phone in the context.
        self.assertNotIn('context_phone', allowed)

    def test_an_order_trigger_has_no_assigned_driver(self):
        allowed = allowed_recipients('staff_order_create')
        self.assertIn('customer', allowed)
        self.assertIn('seller', allowed)
        self.assertNotIn('driver', allowed)
        self.assertNotIn('driver_whatsapp', allowed)

    def test_a_person_trigger_offers_only_that_person(self):
        allowed = allowed_recipients('staff_driver_approved')
        self.assertIn('context_phone', allowed)
        self.assertIn('context_whatsapp', allowed)
        for value in ('customer', 'driver_whatsapp', 'seller', 'zone_drivers'):
            self.assertNotIn(value, allowed)

    def test_the_person_option_names_who_it_is(self):
        def label(key, value='context_whatsapp'):
            return next(r['label'] for r in recipients_for(key) if r['value'] == value)
        self.assertEqual(label('staff_driver_approved'),
                         'The driver this event is about \u2014 WhatsApp')
        self.assertEqual(label('lead_created'), 'The lead this event is about \u2014 WhatsApp')
        self.assertEqual(label('business_cod_settled'),
                         'The seller this event is about \u2014 WhatsApp')
        self.assertEqual(label('staff_driver_approved', 'context_phone'),
                         'The driver this event is about \u2014 Phone')

    def test_a_person_event_offers_both_of_their_numbers(self):
        allowed = allowed_recipients('staff_driver_approved')
        self.assertIn('context_whatsapp', allowed)
        self.assertIn('context_phone', allowed)

    def test_a_whatsapp_flow_lands_on_the_whatsapp_number(self):
        """The action is a WhatsApp message, so defaulting to the phone field
        would quietly send to whatever line the driver takes calls on."""
        self.assertEqual(default_recipient('staff_driver_approved'), 'context_whatsapp')

    def test_a_subjectless_trigger_keeps_only_broadcast_recipients(self):
        allowed = allowed_recipients('staff_earnings_approved')
        self.assertEqual(
            allowed,
            {'all_active_drivers', 'available_drivers', 'staff_ops', 'staff_fin',
             'staff_mkt', 'staff_all', 'custom', 'custom_group'})
        self.assertEqual(trigger_note('staff_earnings_approved')['level'], 'warn')

    def test_a_trigger_that_runs_no_flows_says_so(self):
        self.assertEqual(trigger_feed('sys_state_machine')['subject'], SUBJECT_INERT)
        self.assertEqual(trigger_note('sys_state_machine')['level'], 'danger')

    def test_no_trigger_chosen_rules_nothing_out(self):
        """The form opens with no trigger; greying out half the list there would
        read as a permanent limit rather than a missing answer."""
        self.assertEqual(trigger_feed('')['subject'], SUBJECT_UNSET)
        self.assertEqual(allowed_recipients(''), {r['value'] for r in RECIPIENTS})

    def test_nothing_is_dropped_from_the_list(self):
        for key in ('staff_driver_approved', 'staff_order_create', ''):
            with self.subTest(trigger=key):
                self.assertEqual(len(recipients_for(key)), len(RECIPIENTS))

    def test_an_unavailable_option_always_carries_a_reason(self):
        for key in TRIGGER_FEEDS:
            for row in recipients_for(key):
                if not row['available']:
                    with self.subTest(trigger=key, recipient=row['value']):
                        self.assertTrue(row.get('reason'))

    def test_the_default_is_an_option_that_can_work(self):
        for key in list(TRIGGER_FEEDS) + ['sys_state_machine']:
            with self.subTest(trigger=key):
                self.assertIn(default_recipient(key), allowed_recipients(key))

    def test_groups_keep_every_row(self):
        rows = sum((g['rows'] for g in recipient_groups('staff_task_publish')), [])
        self.assertEqual(len(rows), len(RECIPIENTS))

    def test_scope_map_shape(self):
        data = scope_map(['staff_driver_approved'])['staff_driver_approved']
        self.assertIn('context_phone', data['allowed'])
        self.assertIn('customer', data['reasons'])
        self.assertEqual(data['labels']['context_whatsapp'],
                         'The driver this event is about \u2014 WhatsApp')
        self.assertEqual(data['default'], 'context_whatsapp')


class FlowFormTests(TestCase):
    """The Add / Edit Flow page and its save."""

    def setUp(self):
        self.user = User.objects.create_superuser(
            username='flowscope_admin', email='a@b.co', password='x')
        self.client.force_login(self.user)
        self.add_url = reverse('workforce:auto_flow_add')
        # Trigger rows are seeded data, not migrations, so a test makes its own.
        self.driver_trigger = core_models.AutoTriggerConfig.objects.create(
            trigger_key='staff_driver_approved', label='Driver Approved',
            category='system', description='Staff approves a driver application')
        self.task_trigger = core_models.AutoTriggerConfig.objects.create(
            trigger_key='staff_task_status_change', label='Task Status Changed',
            category='system', description='A delivery task changes status')

    def _post(self, trigger, recipient, name='Test flow'):
        return self.client.post(self.add_url, {
            'name': name,
            'trigger_id': str(trigger.id),
            'action_type': 'whatsapp_message',
            'wa_recipient': recipient,
            'message_template': 'Hello.',
        })

    def test_the_page_carries_the_scope_for_every_trigger(self):
        html = self.client.get(self.add_url).content.decode()
        self.assertIn('id="wa_recipient_scope"', html)
        self.assertIn('staff_driver_approved', html)

    def test_options_are_greyed_out_with_a_reason_when_editing(self):
        flow = core_models.AutoFlow.objects.create(
            name='Driver approved note', trigger=self.driver_trigger,
            action_type='whatsapp_message',
            action_config={'recipient': 'context_phone', 'message_template': 'Hi'})
        html = self.client.get(
            reverse('workforce:auto_flow_edit', args=[flow.id])).content.decode()
        block = html.split('name="wa_recipient"', 1)[1].split('</select>', 1)[0]
        self.assertIn('this event has no delivery task', block)
        self.assertIn('The driver this event is about', block)

    def test_saving_a_recipient_the_trigger_cannot_feed_is_refused(self):
        """This is the whole bug: it used to save happily, then log
        "No phone numbers resolved" on every run, forever."""
        resp = self._post(self.driver_trigger, 'driver_whatsapp')
        self.assertEqual(resp.status_code, 200)
        self.assertIn('cannot be used with this trigger', resp.content.decode())
        self.assertFalse(core_models.AutoFlow.objects.exists())

    def test_saving_a_recipient_that_works_goes_through(self):
        resp = self._post(self.driver_trigger, 'context_phone')
        self.assertEqual(resp.status_code, 302)
        flow = core_models.AutoFlow.objects.get()
        self.assertEqual(flow.action_config['recipient'], 'context_phone')

    def test_a_task_trigger_still_accepts_the_driver(self):
        resp = self._post(self.task_trigger, 'driver_whatsapp')
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(
            core_models.AutoFlow.objects.get().action_config['recipient'], 'driver_whatsapp')

    def test_an_invented_recipient_is_refused(self):
        resp = self._post(self.task_trigger, 'the_prime_minister')
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(core_models.AutoFlow.objects.exists())

    def test_editing_onto_a_trigger_that_cannot_feed_it_is_refused(self):
        flow = core_models.AutoFlow.objects.create(
            name='Task note', trigger=self.task_trigger, action_type='whatsapp_message',
            action_config={'recipient': 'driver_whatsapp', 'message_template': 'Hi'})
        resp = self.client.post(reverse('workforce:auto_flow_edit', args=[flow.id]), {
            'name': 'Task note',
            'trigger_id': str(self.driver_trigger.id),   # moved to a driver event
            'action_type': 'whatsapp_message',
            'wa_recipient': 'driver_whatsapp',           # which has no task
            'message_template': 'Hi',
        })
        self.assertEqual(resp.status_code, 200)
        self.assertIn('cannot be used with this trigger', resp.content.decode())
        flow.refresh_from_db()
        self.assertEqual(flow.trigger_id, self.task_trigger.id)

    def test_a_non_whatsapp_action_is_not_scope_checked(self):
        resp = self.client.post(self.add_url, {
            'name': 'Webhook flow',
            'trigger_id': str(self.driver_trigger.id),
            'action_type': 'webhook_call',
            'webhook_url': 'https://example.com/hook',
        })
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(core_models.AutoFlow.objects.exists())


class TriggerContextTests(TestCase):
    """The call sites the registry promises things about."""

    def test_order_triggers_pass_the_order_object(self):
        """Without order=, the customer/seller/zone recipients resolve nothing —
        which is what made "message the customer on order create" a dead flow."""
        for rel, keys in (
            (os.path.join('orders', 'signals.py'),
             ('staff_order_create', 'staff_order_verify', 'wa_order_cancelled')),
            (os.path.join('orders', 'views.py'), ('staff_order_edit',)),
        ):
            with open(os.path.join(BASE_DIR, rel), encoding='utf-8') as fh:
                body = fh.read()
            for key in keys:
                with self.subTest(file=rel, trigger=key):
                    call = re.search(
                        r"execute_flows_for_trigger\(\s*'" + key + r"'[^)]*", body)
                    self.assertIsNotNone(call)
                    self.assertIn('order=', call.group(0))

    def test_driver_events_carry_the_drivers_whatsapp_number(self):
        """driver_whatsapp is its own field on Driver — without it in the
        context, "the driver's WhatsApp" silently means "their phone"."""
        for rel, key in (
            (os.path.join('workforce', 'views.py'), 'staff_driver_approved'),
            (os.path.join('workforce', 'views.py'), 'staff_driver_rejected'),
            (os.path.join('workforce', 'views.py'), 'staff_cod_settled'),
            (os.path.join('core', 'views.py'), 'driver_application_submitted'),
        ):
            with open(os.path.join(BASE_DIR, rel), encoding='utf-8') as fh:
                body = fh.read()
            call = body.split(f"execute_flows_for_trigger('{key}'", 1)[1].split('})', 1)[0]
            with self.subTest(trigger=key):
                self.assertIn("'driver_whatsapp'", call)

    def test_person_triggers_put_a_phone_in_the_context(self):
        """context_phone reads 'phone', 'lead_phone' or 'driver_phone' — a
        context with only business_phone in it resolves to nobody."""
        wanted = ('phone', 'lead_phone', 'driver_phone')
        for rel, key in (
            (os.path.join('workforce', 'views.py'), 'business_cod_settled'),
            (os.path.join('workforce', 'views.py'), 'staff_cod_settled'),
            (os.path.join('core', 'views.py'), 'driver_application_submitted'),
        ):
            with open(os.path.join(BASE_DIR, rel), encoding='utf-8') as fh:
                body = fh.read()
            call = body.split(f"execute_flows_for_trigger('{key}'", 1)[1].split('})', 1)[0]
            with self.subTest(trigger=key):
                self.assertTrue(any(f"'{name}':" in call for name in wanted))


class PersonNumberResolutionTests(TestCase):
    """Which of the subject's two numbers each person option sends to."""

    def _phones(self, recipient, context):
        from core.auto_flow_executor import _resolve_recipient_phones
        from core.models import AutoFlow, AutoTriggerConfig

        trigger = AutoTriggerConfig.objects.create(
            trigger_key='staff_driver_approved', label='Driver Approved', category='system')
        flow = AutoFlow.objects.create(
            name='n', trigger=trigger, action_type='whatsapp_message',
            action_config={'recipient': recipient})
        return _resolve_recipient_phones(flow, context=context)

    def test_whatsapp_option_uses_the_whatsapp_field(self):
        phones = self._phones('context_whatsapp', {
            'driver_phone': '55512345', 'driver_whatsapp': '66654321'})
        self.assertEqual(phones, ['97466654321'])

    def test_whatsapp_option_falls_back_to_the_phone(self):
        """A CRM lead has one number; the option must still work for them."""
        phones = self._phones('context_whatsapp', {'phone': '55512345'})
        self.assertEqual(phones, ['97455512345'])

    def test_phone_option_ignores_the_whatsapp_field(self):
        phones = self._phones('context_phone', {
            'driver_phone': '55512345', 'driver_whatsapp': '66654321'})
        self.assertEqual(phones, ['97455512345'])

    def test_a_blank_whatsapp_does_not_swallow_the_phone(self):
        phones = self._phones('context_whatsapp', {
            'driver_whatsapp': '   ', 'driver_phone': '55512345'})
        self.assertEqual(phones, ['97455512345'])

    def test_a_seller_settlement_reaches_the_business_whatsapp(self):
        phones = self._phones('context_whatsapp', {
            'phone': '44412345', 'business_whatsapp': '66654321'})
        self.assertEqual(phones, ['97466654321'])

    def test_nothing_to_send_to_resolves_to_nobody(self):
        self.assertEqual(self._phones('context_whatsapp', {}), [])
