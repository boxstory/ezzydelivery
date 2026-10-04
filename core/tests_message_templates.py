"""
Purpose: Tests for editable WhatsApp message bodies and the manual-composer inventory.
Used by: python manage.py test core.tests_message_templates
Notes: test_every_manual_composer_row_resolves is the load-bearing one — a typo in a link name
       or a section key would 500 the whole Auto Triggers page, which is where staff go to fix
       WhatsApp routing in the first place. The bodies themselves are edited on
       workforce:wf_message_templates (its own page since the AI Config Messages tab was split out).
"""

import re
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from core import models as core_models
from core import whatsapp_utils
from core.message_templates import (
    CRM_LEAD_MANUAL, CUSTOM_KEY_PREFIX, KIND_COMPOSER, MANUAL_COMPOSERS,
    ORDER_VERIFY_MANUAL, P2P_BOOKING_CONFIRM, PRICING_INQUIRY_THANKS,
    QUOTE_AGREED_ALERT, TEMPLATE_DEFAULTS, TRIGGER_TEMPLATES, custom_row,
    get_body, get_template, id_index, list_templates, make_custom_key, msg_id,
    next_custom_msg_id, render_template, validate_body,
)

User = get_user_model()


class ManualComposerRegistryTests(TestCase):
    """The registry the Auto Triggers page renders from."""

    def test_every_manual_composer_row_resolves(self):
        for c in MANUAL_COMPOSERS:
            with self.subTest(composer=c['code']):
                for name, target in c.get('links', []):
                    if c.get('url_is_path'):
                        self.assertTrue(target.startswith('/'), f'{name} is not a path')
                    else:
                        reverse(target)  # raises NoReverseMatch on a typo

    def test_every_composer_section_is_a_real_sender_route(self):
        sections = {k for k, _ in core_models.WhatsAppSenderRoute.SECTION_CHOICES}
        for c in MANUAL_COMPOSERS:
            with self.subTest(composer=c['code']):
                if c['section']:
                    self.assertIn(c['section'], sections)

    def test_every_composer_template_key_is_registered(self):
        for c in MANUAL_COMPOSERS:
            with self.subTest(composer=c['code']):
                if c['template_key']:
                    self.assertIn(c['template_key'], TEMPLATE_DEFAULTS)

    def test_composer_department_matches_its_route_department(self):
        """A composer visible on a desk whose route row is hidden would show a
        cross-link to a row that is not on screen."""
        route_depts = core_models.WhatsAppSenderRoute.SECTION_DEPARTMENTS
        for c in MANUAL_COMPOSERS:
            with self.subTest(composer=c['code']):
                if c['section']:
                    self.assertEqual(c['department'], route_depts[c['section']])


class TemplateResolutionTests(TestCase):
    """Staff edits win; the on/off switch means different things per kind."""

    def test_staff_edit_overrides_the_shipped_body(self):
        core_models.MessageTemplate.objects.create(
            key=CRM_LEAD_MANUAL, body='Hi {lead_name} — edited.', is_enabled=True)
        self.assertEqual(
            render_template(CRM_LEAD_MANUAL, lead_name='Sara'), 'Hi Sara — edited.')

    def test_switched_off_composer_renders_nothing(self):
        core_models.MessageTemplate.objects.create(
            key=CRM_LEAD_MANUAL, body='', is_enabled=False)
        self.assertIsNone(render_template(CRM_LEAD_MANUAL, lead_name='Sara'))

    def test_get_body_ignores_the_switch(self):
        """Order verification runs unattended — a template switch must never
        leave the pipeline with nothing to send."""
        core_models.MessageTemplate.objects.create(
            key=ORDER_VERIFY_MANUAL, body='', is_enabled=False)
        body = get_body(ORDER_VERIFY_MANUAL, customer_name='Sara',
                        order_number='EZ-1', items_line='', verify_url='https://x/')
        self.assertIn('Sara', body)
        self.assertIn('https://x/', body)

    def test_unknown_placeholder_survives_instead_of_raising(self):
        core_models.MessageTemplate.objects.create(
            key=CRM_LEAD_MANUAL, body='Hi {lead_name} {not_a_field}', is_enabled=True)
        self.assertEqual(
            render_template(CRM_LEAD_MANUAL, lead_name='Sara'), 'Hi Sara {not_a_field}')

    def test_order_verify_default_keeps_the_shipped_wording(self):
        """This text is what customers have been receiving — a reword here is a
        product decision, not a refactor side effect."""
        body = get_body(ORDER_VERIFY_MANUAL, customer_name='Sara',
                        order_number='EZ-1', items_line='', total_line='',
                        verify_url='https://x/')
        self.assertEqual(
            body,
            'Hi Sara, this is regarding your order EZ-1. Please confirm your '
            'delivery details and availability.\n\n📌 Verify your location: https://x/')

    def test_order_verify_default_quotes_one_total_at_the_door(self):
        """COD + delivery as a single figure — the same number the waybill
        prints as "Collect", so the message and the label never disagree."""
        body = get_body(ORDER_VERIFY_MANUAL, customer_name='Sara',
                        order_number='EZ-1', items_line='',
                        total_line='💵 To pay on delivery: QAR 275.00 '
                                   '(order 250.00 + delivery 25.00)\n',
                        verify_url='https://x/')
        self.assertIn('QAR 275.00 (order 250.00 + delivery 25.00)\n📌', body)


class RegistryCoverageTests(TestCase):
    """Every registered body has to be reachable, switchable and complete."""

    def test_a_toggle_owner_is_the_trigger_that_sends_the_body(self):
        """Otherwise the Messages page hides the switch and points staff at a
        trigger row that does not control this text."""
        for key, tpl in TEMPLATE_DEFAULTS.items():
            owner = tpl.get('toggle_owner')
            if owner:
                with self.subTest(key=key):
                    self.assertEqual(TRIGGER_TEMPLATES.get(owner), key)

    def test_every_placeholder_used_in_a_body_is_documented(self):
        """An undocumented placeholder has no chip and no sample — staff only
        find it by reading the body, and a reword silently drops it."""
        for key, tpl in TEMPLATE_DEFAULTS.items():
            documented = {p.strip() for p in tpl['placeholders'].split(',') if p.strip()}
            used = set(re.findall(r'\{(\w+)\}', tpl['body'])) - {'else', 'endif'}
            with self.subTest(key=key):
                self.assertEqual(used - documented, set())

    def test_documented_placeholders_all_render(self):
        """Formatting a shipped body with every documented value must leave no
        token behind — a typo in a name would otherwise ship to a customer."""
        for key, tpl in TEMPLATE_DEFAULTS.items():
            ctx = {p.strip(): 'x' for p in tpl['placeholders'].split(',') if p.strip()}
            with self.subTest(key=key):
                out = get_body(key, **ctx)
                self.assertNotIn('{', out)

    def test_required_tokens_are_present_in_the_shipped_body(self):
        for key in TEMPLATE_DEFAULTS:
            with self.subTest(key=key):
                self.assertEqual(validate_body(key, TEMPLATE_DEFAULTS[key]['body']), '')

    def test_every_message_carries_a_unique_id(self):
        """The ID is printed on the buttons that send the body, so a missing or
        duplicated one points staff at the wrong message."""
        ids = [tpl.get('msg_id', '') for tpl in TEMPLATE_DEFAULTS.values()]
        self.assertNotIn('', ids, 'a registered message has no msg_id')
        self.assertEqual(len(set(ids)), len(ids), 'two messages share an msg_id')
        for ident in ids:
            with self.subTest(msg_id=ident):
                self.assertRegex(ident, r'^M\d{2}$')

    def test_msg_id_survives_the_resolver_and_the_reverse_lookup(self):
        for key, tpl in TEMPLATE_DEFAULTS.items():
            with self.subTest(key=key):
                self.assertEqual(get_template(key)['msg_id'], tpl['msg_id'])
                self.assertEqual(msg_id(key), tpl['msg_id'])
        self.assertEqual(id_index()[TEMPLATE_DEFAULTS[ORDER_VERIFY_MANUAL]['msg_id']],
                         ORDER_VERIFY_MANUAL)
        self.assertEqual(msg_id('not_a_real_key'), '')


class RequiredPlaceholderTests(TestCase):
    """A reworded message that drops its link still sends — it just sends
    something useless. The save refuses instead."""

    def setUp(self):
        self.user = User.objects.create_superuser(
            username='msgreq_admin', email='r@b.co', password='x')
        self.client.force_login(self.user)
        self.url = reverse('workforce:wf_message_templates')

    def test_dropping_the_link_is_refused(self):
        self.assertTrue(validate_body(ORDER_VERIFY_MANUAL, 'Hi {customer_name}'))
        resp = self.client.post(self.url, {
            'template_key': ORDER_VERIFY_MANUAL,
            'body': 'Hi {customer_name} — please confirm.',
        }, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(resp.status_code, 400)
        self.assertIn('verify_url', resp.json()['message'])
        self.assertFalse(
            core_models.MessageTemplate.objects.filter(key=ORDER_VERIFY_MANUAL).exists())

    def test_a_body_that_keeps_the_link_saves(self):
        resp = self.client.post(self.url, {
            'template_key': ORDER_VERIFY_MANUAL,
            'body': 'Hi {customer_name} — pin here: {verify_url}',
        }, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()['success'])


class QuoteAndLeadMessageTests(TestCase):
    """The automatic lead-facing bodies now come off the Messages page."""

    def test_pricing_inquiry_thank_you_uses_the_template(self):
        core_models.MessageTemplate.objects.create(
            key=PRICING_INQUIRY_THANKS, is_enabled=True,
            body='Thanks {business_name} — {contact_name} will hear from us.')
        sent = {}

        def fake_send(section, phone, message, **kw):
            sent.update(section=section, phone=phone, message=message)
            return {'success': True}

        with mock.patch('core.whatsapp_utils.trigger_enabled', return_value=True), \
                mock.patch('core.whatsapp_utils.send_routed_message', fake_send):
            whatsapp_utils.send_inquiry_thank_you_message(
                '97455112233', 'Doha Boutique', contact_name='Ahmed')

        self.assertEqual(sent['section'], 'crm_leads')
        self.assertEqual(sent['message'], 'Thanks Doha Boutique — Ahmed will hear from us.')

    def test_thank_you_still_sends_when_the_trigger_owns_the_switch(self):
        """Its on/off is the wa_quote_thank_you trigger's; a stray template
        switch must not leave a finished form unacknowledged."""
        core_models.MessageTemplate.objects.create(
            key=PRICING_INQUIRY_THANKS, body='', is_enabled=False)
        with mock.patch('core.whatsapp_utils.trigger_enabled', return_value=True), \
                mock.patch('core.whatsapp_utils.send_routed_message',
                           return_value={'success': True}) as send:
            whatsapp_utils.send_inquiry_thank_you_message('97455112233', 'Doha Boutique')
        self.assertTrue(send.called)
        self.assertIn('Doha Boutique', send.call_args[0][2])

    def test_quote_agreed_alert_switches_shape_on_wants_call(self):
        talk = get_body(QUOTE_AGREED_ALERT, wants_call='yes', inquiry_url='https://x/')
        accepted = get_body(QUOTE_AGREED_ALERT, wants_call='', inquiry_url='https://x/')
        self.assertIn('WANTS TO TALK', talk)
        self.assertNotIn('Agreed Price', talk)
        self.assertIn('QUOTE ACCEPTED', accepted)
        self.assertNotIn('WANTS TO TALK', accepted)

    def test_p2p_confirmation_drops_the_lines_a_booking_has_no_value_for(self):
        priced = get_body(P2P_BOOKING_CONFIRM, from_label='A', to_label='B',
                          price='45', fee_note='Car, 3 boxes', cod_amount='200',
                          confirm_url='https://x/')
        bare = get_body(P2P_BOOKING_CONFIRM, from_label='A', to_label='B',
                        confirm_url='https://x/')
        self.assertIn('Delivery fee: QAR 45', priced)
        self.assertIn('Cash to collect', priced)
        self.assertIn('confirm the price shortly', bare)
        self.assertNotIn('Cash to collect', bare)
        self.assertNotIn('Boxes:', bare)


class ConditionalBlockTests(TestCase):
    """``{if …}{else}{endif}`` — how staff write an optional line themselves."""

    def _render(self, body, **ctx):
        core_models.MessageTemplate.objects.update_or_create(
            key=CRM_LEAD_MANUAL, defaults={'body': body, 'is_enabled': True})
        return render_template(CRM_LEAD_MANUAL, **ctx)

    def test_block_is_kept_when_the_value_is_there(self):
        self.assertEqual(
            self._render('A{if cod_amount} COD {cod_amount}{endif} B', cod_amount='150.00'),
            'A COD 150.00 B')

    def test_zero_amount_reads_as_nothing_to_say(self):
        """`{if cod_amount}` is the "COD is more than 0" test staff read it as."""
        self.assertEqual(
            self._render('A{if cod_amount} COD {cod_amount}{endif} B', cod_amount='0.00'),
            'A B')

    def test_blank_and_missing_values_drop_the_block(self):
        body = 'A{if seller_line}kept{endif}B'
        self.assertEqual(self._render(body, seller_line=''), 'AB')
        self.assertEqual(self._render(body), 'AB')

    def test_else_branch(self):
        body = '{if cod_amount}Collect {cod_amount}{else}Already paid{endif}'
        self.assertEqual(self._render(body, cod_amount='25'), 'Collect 25')
        self.assertEqual(self._render(body, cod_amount='0'), 'Already paid')

    def test_a_tag_on_its_own_line_takes_the_line_with_it(self):
        """Otherwise a false block leaves a blank gap in the sent message."""
        body = 'Hi\n{if cod_amount}\nCOD {cod_amount}\n{endif}\nBye'
        self.assertEqual(self._render(body, cod_amount='0'), 'Hi\nBye')
        self.assertEqual(self._render(body, cod_amount='5'), 'Hi\nCOD 5\nBye')

    def test_a_non_numeric_value_is_a_value(self):
        self.assertEqual(
            self._render('{if company}from {company}{endif}', company='Zone 0 Store'),
            'from Zone 0 Store')

    def test_order_verification_body_can_carry_a_cod_condition(self):
        """The pipeline runs unattended — a conditional body must survive
        get_body, which ignores the switch."""
        core_models.MessageTemplate.objects.create(
            key=ORDER_VERIFY_MANUAL, is_enabled=True,
            body='Hi {customer_name}{if cod_amount}\n💵 QAR {cod_amount} on delivery{endif}\n{verify_url}')
        paid = get_body(ORDER_VERIFY_MANUAL, customer_name='Sara', cod_amount='',
                        verify_url='https://x/')
        self.assertEqual(paid, 'Hi Sara\nhttps://x/')
        cod = get_body(ORDER_VERIFY_MANUAL, customer_name='Sara', cod_amount='150.00',
                       verify_url='https://x/')
        self.assertEqual(cod, 'Hi Sara\n💵 QAR 150.00 on delivery\nhttps://x/')


class MessageTemplatesPageTests(TestCase):
    """The Message Templates page — its own console since the AI Config
    Messages tab was split out."""

    def setUp(self):
        self.user = User.objects.create_superuser(
            username='msgtpl_admin', email='a@b.co', password='x')
        self.client.force_login(self.user)
        self.url = reverse('workforce:wf_message_templates')

    def test_page_renders_a_card_for_every_registered_template(self):
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode()
        for key in TEMPLATE_DEFAULTS:
            with self.subTest(key=key):
                self.assertIn(f'id="msg-{key}"', html)

    def test_saving_a_trigger_owned_template_keeps_it_enabled(self):
        """Its form renders no switch, so `is_enabled` is absent from the POST.
        Reading the missing field would silently disable order verification."""
        self.assertTrue(TEMPLATE_DEFAULTS[ORDER_VERIFY_MANUAL]['toggle_owner'])
        resp = self.client.post(self.url, {
            'template_key': ORDER_VERIFY_MANUAL,
            # Keeps {verify_url}: the save refuses a body that drops it.
            'body': 'Hi {customer_name} — reworded. {verify_url}',
        }, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(get_template(ORDER_VERIFY_MANUAL)['is_enabled'])
        self.assertEqual(
            get_body(ORDER_VERIFY_MANUAL, customer_name='Sara', verify_url='https://x/'),
            'Hi Sara — reworded. https://x/')

    def test_composer_template_can_be_switched_off(self):
        self.assertEqual(TEMPLATE_DEFAULTS[CRM_LEAD_MANUAL]['kind'], KIND_COMPOSER)
        self.client.post(self.url, {
            'template_key': CRM_LEAD_MANUAL,
            'body': 'anything',
        }, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertFalse(get_template(CRM_LEAD_MANUAL)['is_enabled'])

    def test_unedited_body_stores_nothing_so_it_follows_the_default(self):
        self.client.post(self.url, {
            'template_key': CRM_LEAD_MANUAL,
            'is_enabled': '1',
            'body': TEMPLATE_DEFAULTS[CRM_LEAD_MANUAL]['body'],
        }, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        tpl = get_template(CRM_LEAD_MANUAL)
        self.assertFalse(tpl['is_customised'])
        self.assertEqual(tpl['body'], TEMPLATE_DEFAULTS[CRM_LEAD_MANUAL]['body'])

    def test_unknown_key_is_rejected(self):
        resp = self.client.post(self.url, {
            'template_key': 'not_a_template',
            'body': 'x',
        }, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(resp.status_code, 400)


class AutoTriggersComposerGroupTests(TestCase):
    """The composers must actually reach the page staff configure them on."""

    def setUp(self):
        self.user = User.objects.create_superuser(
            username='msgtpl_admin2', email='c@d.co', password='x')
        self.client.force_login(self.user)

    def test_composer_rows_render_with_a_link_to_their_sender_route(self):
        resp = self.client.get(reverse('workforce:auto_triggers_list'))
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode()
        for c in MANUAL_COMPOSERS:
            with self.subTest(composer=c['code']):
                self.assertIn(f'composer-row-{c["code"]}', html)
                if c['section']:
                    self.assertIn(f'href="#route-row-{c["section"]}"', html)

    def test_composer_edit_button_deep_links_to_its_message_body(self):
        resp = self.client.get(reverse('workforce:auto_triggers_list'))
        html = resp.content.decode()
        keys = {c['template_key'] for c in MANUAL_COMPOSERS if c['template_key']}
        self.assertTrue(keys)
        for key in keys:
            with self.subTest(key=key):
                self.assertIn(f'#msg-{key}', html)


class CustomMessageRegistryTests(TestCase):
    """Messages staff write on the page, stored as rows with no code default."""

    def _add(self, label='Late delivery apology', section='orders_tasks',
             body='Hi {customer_name}, sorry about the delay.', **kw):
        return core_models.MessageTemplate.objects.create(
            key=make_custom_key(label), label=label, section=section, body=body,
            msg_id=next_custom_msg_id(), is_custom=True, **kw)

    def test_key_is_prefixed_and_never_shadows_a_shipped_one(self):
        key = make_custom_key('Order verify manual')
        self.assertTrue(key.startswith(CUSTOM_KEY_PREFIX))
        self.assertNotIn(key, TEMPLATE_DEFAULTS)

    def test_a_second_message_with_the_same_name_gets_its_own_key(self):
        first = self._add(label='Same name')
        second = make_custom_key('Same name')
        self.assertNotEqual(first.key, second)

    def test_ids_run_in_their_own_c_series(self):
        self.assertEqual(next_custom_msg_id(), 'C01')
        self._add(label='One')
        self.assertEqual(next_custom_msg_id(), 'C02')

    def test_deleting_the_last_one_frees_its_number_and_renumbers_nothing(self):
        first = self._add(label='One')
        second = self._add(label='Two')
        self.assertEqual(second.msg_id, 'C02')
        second.delete()
        # The number is reused (nothing in code refers to a C-number) but the
        # message still on the page keeps the ID staff already know it by.
        self.assertEqual(next_custom_msg_id(), 'C02')
        first.refresh_from_db()
        self.assertEqual(first.msg_id, 'C01')

    def test_deleting_an_earlier_one_does_not_renumber_the_rest(self):
        first = self._add(label='One')
        second = self._add(label='Two')
        first.delete()
        second.refresh_from_db()
        self.assertEqual(second.msg_id, 'C02')
        self.assertEqual(next_custom_msg_id(), 'C03')

    def test_a_custom_id_can_never_collide_with_a_shipped_one(self):
        shipped = {v['msg_id'] for v in TEMPLATE_DEFAULTS.values() if v.get('msg_id')}
        self.assertNotIn(next_custom_msg_id(), shipped)

    def test_it_resolves_like_a_registered_template(self):
        row = self._add()
        tpl = get_template(row.key)
        self.assertTrue(tpl['is_custom'])
        self.assertEqual(tpl['kind'], KIND_COMPOSER)
        self.assertEqual(tpl['section'], 'orders_tasks')
        self.assertEqual(tpl['msg_id'], 'C01')
        # Nothing shipped behind it, so there is no default to restore.
        self.assertEqual(tpl['default_body'], '')
        self.assertEqual(
            render_template(row.key, customer_name='Sara'),
            'Hi Sara, sorry about the delay.')

    def test_a_shipped_template_still_reports_itself_as_not_custom(self):
        self.assertFalse(get_template(CRM_LEAD_MANUAL)['is_custom'])

    def test_switched_off_custom_message_renders_nothing(self):
        row = self._add(is_enabled=False)
        self.assertIsNone(render_template(row.key, customer_name='Sara'))

    def test_it_is_listed_after_the_shipped_registry(self):
        row = self._add()
        keys = [t['key'] for t in list_templates()]
        self.assertEqual(keys[:len(TEMPLATE_DEFAULTS)], list(TEMPLATE_DEFAULTS))
        self.assertEqual(keys[-1], row.key)

    def test_an_override_row_is_not_mistaken_for_a_custom_message(self):
        """A row against a shipped key is reworded text, not a new message —
        listing it twice would put an untitled duplicate card on the page."""
        core_models.MessageTemplate.objects.create(key=CRM_LEAD_MANUAL, body='reworded')
        keys = [t['key'] for t in list_templates()]
        self.assertEqual(len(keys), len(set(keys)))
        self.assertEqual(len(keys), len(TEMPLATE_DEFAULTS))

    def test_custom_row_refuses_a_shipped_key(self):
        """The gate on delete: a shipped key must never resolve to a deletable row."""
        core_models.MessageTemplate.objects.create(
            key=CRM_LEAD_MANUAL, body='reworded', is_custom=True)
        self.assertIsNone(custom_row(CRM_LEAD_MANUAL))


class CustomMessagePageTests(TestCase):
    """Adding, editing and deleting a message from the Messages page."""

    def setUp(self):
        self.user = User.objects.create_superuser(
            username='msgtpl_admin3', email='e@f.co', password='x')
        self.client.force_login(self.user)
        self.url = reverse('workforce:wf_message_templates')

    def _add(self, **over):
        data = {
            'action': 'add',
            'label': 'Late delivery apology',
            'section': 'orders_tasks',
            'description': 'When a driver is running behind.',
            'body': 'Hi {customer_name}, sorry about the delay. — {staff_name}',
        }
        data.update(over)
        return self.client.post(self.url, data, follow=True)

    def test_add_creates_a_message_and_lands_on_its_card(self):
        resp = self._add()
        self.assertEqual(resp.status_code, 200)
        row = core_models.MessageTemplate.objects.get(is_custom=True)
        self.assertEqual(row.msg_id, 'C01')
        self.assertEqual(row.section, 'orders_tasks')
        self.assertTrue(row.is_enabled)
        self.assertEqual(row.updated_by, self.user)
        self.assertIn(f'id="msg-{row.key}"', resp.content.decode())

    def test_add_without_a_group_is_refused(self):
        self._add(section='')
        self.assertFalse(core_models.MessageTemplate.objects.exists())

    def test_add_without_a_body_is_refused(self):
        self._add(body='   ')
        self.assertFalse(core_models.MessageTemplate.objects.exists())

    def test_add_with_an_invented_group_is_refused(self):
        self._add(section='not_a_route')
        self.assertFalse(core_models.MessageTemplate.objects.exists())

    def test_saving_one_updates_its_name_note_and_body(self):
        self._add()
        row = core_models.MessageTemplate.objects.get(is_custom=True)
        resp = self.client.post(self.url, {
            'template_key': row.key,
            'label': 'Running late — apology',
            'description': 'Reworded note.',
            'is_enabled': '1',
            'body': 'Hi {customer_name}, we are running late.',
        }, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(resp.status_code, 200)
        row.refresh_from_db()
        self.assertEqual(row.label, 'Running late — apology')
        self.assertEqual(row.description, 'Reworded note.')
        self.assertEqual(row.body, 'Hi {customer_name}, we are running late.')
        # The section and the ID are not on the edit form and must survive it.
        self.assertEqual(row.section, 'orders_tasks')
        self.assertEqual(row.msg_id, 'C01')

    def test_emptying_the_body_is_refused(self):
        """There is no shipped text to fall back on, so a blank box would be a
        message that sends nothing at all."""
        self._add()
        row = core_models.MessageTemplate.objects.get(is_custom=True)
        resp = self.client.post(self.url, {
            'template_key': row.key, 'is_enabled': '1', 'body': '   ',
        }, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(resp.status_code, 400)
        row.refresh_from_db()
        self.assertTrue(row.body.strip())

    def test_a_blank_name_keeps_the_old_one(self):
        self._add()
        row = core_models.MessageTemplate.objects.get(is_custom=True)
        self.client.post(self.url, {
            'template_key': row.key, 'is_enabled': '1', 'label': '',
            'body': 'Hi {customer_name}.',
        }, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        row.refresh_from_db()
        self.assertEqual(row.label, 'Late delivery apology')

    def test_it_can_be_switched_off_without_being_deleted(self):
        self._add()
        row = core_models.MessageTemplate.objects.get(is_custom=True)
        self.client.post(self.url, {
            'template_key': row.key, 'body': 'Hi {customer_name}.',
        }, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        row.refresh_from_db()
        self.assertFalse(row.is_enabled)
        self.assertTrue(core_models.MessageTemplate.objects.filter(pk=row.pk).exists())

    def test_delete_removes_it(self):
        self._add()
        row = core_models.MessageTemplate.objects.get(is_custom=True)
        resp = self.client.post(
            self.url, {'action': 'delete', 'template_key': row.key}, follow=True)
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(core_models.MessageTemplate.objects.filter(pk=row.pk).exists())

    def test_delete_cannot_touch_a_shipped_message(self):
        """That POST against a shipped key would throw away reworded customer
        text and silently restore the default."""
        core_models.MessageTemplate.objects.create(
            key=CRM_LEAD_MANUAL, body='Our own wording.')
        self.client.post(
            self.url, {'action': 'delete', 'template_key': CRM_LEAD_MANUAL}, follow=True)
        self.assertEqual(
            core_models.MessageTemplate.objects.get(key=CRM_LEAD_MANUAL).body,
            'Our own wording.')

    def test_the_card_offers_delete_and_not_restore_default(self):
        self._add()
        row = core_models.MessageTemplate.objects.get(is_custom=True)
        html = self.client.get(self.url).content.decode()
        card = html.split(f'id="msg-{row.key}"', 1)[1].split('</form>', 1)[0]
        self.assertIn('data-wmt-delete', card)
        self.assertNotIn('data-tpl-reset', card)

    def test_the_page_offers_the_add_panel(self):
        html = self.client.get(self.url).content.decode()
        self.assertIn('id="wmt_add_panel"', html)
        self.assertIn('name="section"', html)


class CustomMessageComposerPickerTests(TestCase):
    """The one surface a staff-written message reaches: the send window."""

    def setUp(self):
        self.user = User.objects.create_superuser(
            username='msgtpl_admin4', email='g@h.co', password='x')
        self.client.force_login(self.user)
        self.url = reverse('workforce:whatsapp_composer_templates')
        self.row = core_models.MessageTemplate.objects.create(
            key=make_custom_key('Late apology'), label='Late apology',
            section='orders_tasks', msg_id='C01', is_custom=True,
            body='Hi {customer_name}, sorry — {staff_name}')

    def _picker(self, section='orders_tasks'):
        resp = self.client.get(self.url, {'section': section, 'name': 'Sara'})
        self.assertEqual(resp.status_code, 200)
        return resp.json()['templates']

    def test_it_appears_with_its_names_filled_in(self):
        entry = next(t for t in self._picker() if t['key'] == self.row.key)
        self.assertEqual(entry['msg_id'], 'C01')
        self.assertEqual(entry['label'], 'Late apology')
        self.assertIn('Hi Sara', entry['body'])
        self.assertNotIn('{customer_name}', entry['body'])
        self.assertNotIn('{staff_name}', entry['body'])

    def test_it_stays_in_its_own_group(self):
        keys = [t['key'] for t in self._picker('crm_leads')]
        self.assertNotIn(self.row.key, keys)

    def test_switched_off_it_is_not_offered(self):
        self.row.is_enabled = False
        self.row.save(update_fields=['is_enabled'])
        self.assertNotIn(self.row.key, [t['key'] for t in self._picker()])

    def test_the_shipped_bodies_are_still_offered_alongside_it(self):
        keys = [t['key'] for t in self._picker()]
        self.assertIn(ORDER_VERIFY_MANUAL, keys)
