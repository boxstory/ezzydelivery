"""
Purpose: Tests for editable WhatsApp message bodies and the manual-composer inventory.
Used by: python manage.py test core.tests_message_templates
Notes: test_every_manual_composer_row_resolves is the load-bearing one — a typo in a link name
       or a section key would 500 the whole Auto Triggers page, which is where staff go to fix
       WhatsApp routing in the first place.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from core import models as core_models
from core.message_templates import (
    CRM_LEAD_MANUAL, KIND_COMPOSER, MANUAL_COMPOSERS, ORDER_VERIFY_MANUAL,
    TEMPLATE_DEFAULTS, get_body, get_template, render_template,
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
                        order_number='EZ-1', items_line='', verify_url='https://x/')
        self.assertEqual(
            body,
            'Hi Sara, this is regarding your order EZ-1. Please confirm your '
            'delivery details and availability.\n\n📌 Verify your location: https://x/')


class MessagesTabSaveTests(TestCase):
    """The AI Config Messages tab write path."""

    def setUp(self):
        self.user = User.objects.create_superuser(
            username='msgtpl_admin', email='a@b.co', password='x')
        self.client.force_login(self.user)
        self.url = reverse('workforce:wf_ai_config')

    def test_saving_a_trigger_owned_template_keeps_it_enabled(self):
        """Its form renders no switch, so `is_enabled` is absent from the POST.
        Reading the missing field would silently disable order verification."""
        self.assertTrue(TEMPLATE_DEFAULTS[ORDER_VERIFY_MANUAL]['toggle_owner'])
        resp = self.client.post(self.url, {
            'section': 'templates',
            'template_key': ORDER_VERIFY_MANUAL,
            'body': 'Hi {customer_name} — reworded.',
        }, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(get_template(ORDER_VERIFY_MANUAL)['is_enabled'])
        self.assertEqual(
            get_body(ORDER_VERIFY_MANUAL, customer_name='Sara'), 'Hi Sara — reworded.')

    def test_composer_template_can_be_switched_off(self):
        self.assertEqual(TEMPLATE_DEFAULTS[CRM_LEAD_MANUAL]['kind'], KIND_COMPOSER)
        self.client.post(self.url, {
            'section': 'templates',
            'template_key': CRM_LEAD_MANUAL,
            'body': 'anything',
        }, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertFalse(get_template(CRM_LEAD_MANUAL)['is_enabled'])

    def test_unedited_body_stores_nothing_so_it_follows_the_default(self):
        self.client.post(self.url, {
            'section': 'templates',
            'template_key': CRM_LEAD_MANUAL,
            'is_enabled': '1',
            'body': TEMPLATE_DEFAULTS[CRM_LEAD_MANUAL]['body'],
        }, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        tpl = get_template(CRM_LEAD_MANUAL)
        self.assertFalse(tpl['is_customised'])
        self.assertEqual(tpl['body'], TEMPLATE_DEFAULTS[CRM_LEAD_MANUAL]['body'])

    def test_unknown_key_is_rejected(self):
        resp = self.client.post(self.url, {
            'section': 'templates',
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
