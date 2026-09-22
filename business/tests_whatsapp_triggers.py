# Purpose: Guard the WhatsApp Alerts settings page — default-as-value and the one-button save.
# Used by: manage.py test business.tests_whatsapp_triggers
# Notes:   The contract is "showing our default in the box must not freeze a copy of it":
#          a body equal to the current default is stored as '' (follow the default).

import json

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from business.models import Business, WhatsAppNotificationTrigger
from core import models as core_models
from core.trigger_tokens import default_message


class WhatsAppTriggerSettingsTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.owner = User.objects.create_user(username='wa_owner', password='x')
        core_models.Profile.objects.create(
            user=cls.owner, first_name='W', last_name='A', phone=31999001,
            is_business=True, verification_status='verified',
            is_business_profile_completed=True,
        )
        cls.business = Business.objects.create(
            business_id=990101, user=cls.owner, business_name='Trigger Store',
            business_code='TRG1', business_phone='97455500001',
            business_whatsapp='97455500002', business_status='active',
        )
        cls.list_url = reverse('business:whatsapp_triggers_list')
        cls.save_url = reverse('business:whatsapp_triggers_save')

    def setUp(self):
        self.client = Client(HTTP_HOST='ezzydelivery.qa', HTTP_X_FORWARDED_PROTO='https')
        self.client.force_login(self.owner)

    def _save(self, **row):
        row.setdefault('trigger_status', 'delivered')
        row.setdefault('is_active', True)
        row.setdefault('notification_phone', '')
        return self.client.post(self.save_url, data=json.dumps({'triggers': [row]}),
                                content_type='application/json')

    def _stored(self, status='delivered'):
        return WhatsAppNotificationTrigger.objects.get(
            business=self.business, trigger_status=status)

    # --- the box is pre-filled, not a placeholder ---------------------------

    def test_box_is_prefilled_with_the_default(self):
        r = self.client.get(self.list_url)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.context['triggers']['delivered']['message'],
                         default_message('delivered'))
        self.assertFalse(r.context['triggers']['delivered']['is_customised'])

    def test_box_shows_the_saved_message_once_customised(self):
        WhatsAppNotificationTrigger.objects.create(
            business=self.business, trigger_status='delivered',
            is_active=True, custom_message='Mine: {order_number}')
        r = self.client.get(self.list_url)
        self.assertEqual(r.context['triggers']['delivered']['message'], 'Mine: {order_number}')
        self.assertTrue(r.context['triggers']['delivered']['is_customised'])

    # --- saving the default must not freeze a copy of it --------------------

    def test_unedited_default_is_stored_as_follow_the_default(self):
        r = self._save(custom_message=default_message('delivered'))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self._stored().custom_message, '')

    def test_default_with_stray_whitespace_still_counts_as_unedited(self):
        self._save(custom_message='  ' + default_message('delivered') + '\n\n')
        self.assertEqual(self._stored().custom_message, '')

    def test_a_real_edit_is_stored(self):
        self._save(custom_message='Hi {customer_name}, done.')
        self.assertEqual(self._stored().custom_message, 'Hi {customer_name}, done.')

    def test_clearing_the_box_returns_to_the_default(self):
        self._save(custom_message='Hi {customer_name}, done.')
        self._save(custom_message='')
        self.assertEqual(self._stored().custom_message, '')

    # --- one button, many rows ---------------------------------------------

    def test_saves_every_row_in_one_post(self):
        r = self.client.post(self.save_url, content_type='application/json', data=json.dumps({
            'triggers': [
                {'trigger_status': 'delivered', 'is_active': True,
                 'custom_message': 'A', 'notification_phone': '97455500009'},
                {'trigger_status': 'failed', 'is_active': False,
                 'custom_message': 'B', 'notification_phone': ''},
            ]}))
        self.assertEqual(r.json()['saved'], 2)
        self.assertEqual(self._stored('delivered').notification_phone, '97455500009')
        self.assertFalse(self._stored('failed').is_active)

    def test_unknown_tokens_are_reported_per_row(self):
        r = self._save(custom_message='Hi {customer_name} {nope}')
        self.assertEqual(r.json()['unknown_tokens'], {'delivered': ['nope']})

    def test_long_body_is_clamped_not_rejected(self):
        r = self._save(custom_message='x' * 5000)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(self._stored().custom_message), 1500)

    # --- refusals -----------------------------------------------------------

    def test_invalid_status_is_rejected(self):
        r = self._save(trigger_status='not_a_status')
        self.assertEqual(r.status_code, 400)
        self.assertFalse(WhatsAppNotificationTrigger.objects.filter(business=self.business).exists())

    def test_malformed_json_is_rejected(self):
        r = self.client.post(self.save_url, data='{nope', content_type='application/json')
        self.assertEqual(r.status_code, 400)

    def test_get_is_rejected(self):
        self.assertEqual(self.client.get(self.save_url).status_code, 405)

    def test_anonymous_cannot_save(self):
        self.client.logout()
        r = self._save(custom_message='sneaky')
        self.assertIn(r.status_code, (302, 403))
        self.assertFalse(WhatsAppNotificationTrigger.objects.filter(business=self.business).exists())
