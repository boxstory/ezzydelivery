# Purpose: Tests for ezzy_api key auth, scope enforcement, tenant scoping, webhooks.
# Used by: manage.py test ezzy_api
# Notes: Covers the external API attack surface — key hashing, scope gates,
#        cross-business isolation, and the inbound order webhook.

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from business import models as business_models
from core import models as core_models
from ezzy_api import models as ezzy_api_models
from orders import models as orders_models

User = get_user_model()


def make_business(idx, username):
    """Create user + profile + business; returns (user, business)."""
    user = User.objects.create_user(
        username=username, email=f'{username}@example.com', password='pass12345'
    )
    profile = core_models.Profile.objects.create(
        user=user, first_name='T', last_name='U', phone=30000000 + idx
    )
    business = business_models.Business.objects.create(
        business_id=idx,
        user=user,
        profile=profile,
        business_name=f'Biz {idx}',
        business_code=f'BZ{idx}',
        business_phone='55500000',
        business_email=f'biz{idx}@example.com',
    )
    return user, business


def make_key(business, scope=ezzy_api_models.ClientApiKey.SCOPE_WRITE, **kwargs):
    """Create a ClientApiKey; returns (instance, plaintext key)."""
    key = ezzy_api_models.ClientApiKey.objects.create(
        business=business, scope=scope, **kwargs
    )
    return key, key._plaintext_key


class ClientApiKeyModelTest(TestCase):
    def setUp(self):
        self.user, self.business = make_business(9001, 'keyowner')

    def test_plaintext_never_persisted(self):
        key, raw = make_key(self.business)
        self.assertTrue(raw.startswith('ezz_key_'))
        key.refresh_from_db()
        self.assertIsNone(key.api_key)
        self.assertEqual(key.key_hash, ezzy_api_models.ClientApiKey.hash_key(raw))
        self.assertEqual(key.key_prefix, raw[:16])

    def test_scope_hierarchy(self):
        key, _ = make_key(self.business, scope='write')
        self.assertTrue(key.has_scope('read'))
        self.assertTrue(key.has_scope('write'))
        self.assertFalse(key.has_scope('admin'))
        admin_key, _ = make_key(self.business, scope='admin')
        self.assertTrue(admin_key.has_scope('write'))

    def test_is_valid_inactive_and_expired(self):
        key, _ = make_key(self.business)
        self.assertTrue(key.is_valid())
        key.is_active = False
        self.assertFalse(key.is_valid())
        key.is_active = True
        key.expires_at = timezone.now() - timedelta(hours=1)
        self.assertFalse(key.is_valid())


class ApiKeyAuthenticationTest(TestCase):
    def setUp(self):
        self.user, self.business = make_business(9002, 'authowner')
        self.key, self.raw = make_key(self.business)
        self.client = APIClient()

    def test_bearer_header_authenticates(self):
        resp = self.client.get(
            '/api/business/orders/', HTTP_AUTHORIZATION=f'Bearer {self.raw}'
        )
        self.assertEqual(resp.status_code, 200)

    def test_x_api_key_header_authenticates(self):
        resp = self.client.get('/api/business/orders/', HTTP_X_API_KEY=self.raw)
        self.assertEqual(resp.status_code, 200)

    def test_invalid_key_rejected(self):
        resp = self.client.get(
            '/api/business/orders/', HTTP_AUTHORIZATION='Bearer ezz_key_wrongwrongwrong'
        )
        self.assertEqual(resp.status_code, 401)

    def test_inactive_key_rejected(self):
        self.key.is_active = False
        self.key.save()
        resp = self.client.get('/api/business/orders/', HTTP_X_API_KEY=self.raw)
        self.assertEqual(resp.status_code, 401)

    def test_expired_key_rejected(self):
        self.key.expires_at = timezone.now() - timedelta(minutes=1)
        self.key.save()
        resp = self.client.get('/api/business/orders/', HTTP_X_API_KEY=self.raw)
        self.assertEqual(resp.status_code, 401)

    def test_unauthenticated_rejected(self):
        resp = self.client.get('/api/business/orders/')
        self.assertEqual(resp.status_code, 401)

    def test_last_used_updated(self):
        self.assertIsNone(self.key.last_used)
        self.client.get('/api/business/orders/', HTTP_X_API_KEY=self.raw)
        self.key.refresh_from_db()
        self.assertIsNotNone(self.key.last_used)


class TenantScopingTest(TestCase):
    """An API key must only ever see its own business's data."""

    def setUp(self):
        self.user_a, self.biz_a = make_business(9003, 'tenant_a')
        self.user_b, self.biz_b = make_business(9004, 'tenant_b')
        self.key_a, self.raw_a = make_key(self.biz_a)
        orders_models.Order.objects.create(
            business=self.biz_a, order_number='TSA-1', client_order_code='A-1',
            customer_name='Alice', customer_phone='55511111',
            customer_address='Zone 1', order_status='to_review',
        )
        orders_models.Order.objects.create(
            business=self.biz_b, order_number='TSB-1', client_order_code='B-1',
            customer_name='Bob', customer_phone='55522222',
            customer_address='Zone 2', order_status='to_review',
        )
        self.client = APIClient()

    def test_key_sees_only_own_orders(self):
        resp = self.client.get('/api/business/orders/', HTTP_X_API_KEY=self.raw_a)
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode()
        self.assertIn('TSA-1', body)
        self.assertNotIn('TSB-1', body)

    def test_write_key_can_create_order_scoped_to_own_business(self):
        resp = self.client.post('/api/business/orders/', {
            'customer_name': 'Carol', 'customer_phone': '55533334',
            'customer_address': 'Zone 3', 'cod_amount': 100,
        }, format='json', HTTP_X_API_KEY=self.raw_a)
        self.assertEqual(resp.status_code, 201)
        order_number = resp.json()['order']['order_number']
        order = orders_models.Order.objects.get(order_number=order_number)
        self.assertEqual(order.business_id, self.biz_a.business_id)
        self.assertEqual(order.order_status, 'to_review')


class ScopeEnforcementTest(TestCase):
    def setUp(self):
        self.user, self.business = make_business(9005, 'scopeowner')
        self.read_key, self.read_raw = make_key(self.business, scope='read')
        self.write_key, self.write_raw = make_key(self.business, scope='write')
        self.admin_key, self.admin_raw = make_key(self.business, scope='admin')
        self.client = APIClient()

    def test_read_key_can_get(self):
        resp = self.client.get('/api/business/orders/', HTTP_X_API_KEY=self.read_raw)
        self.assertEqual(resp.status_code, 200)

    def test_read_key_cannot_post(self):
        resp = self.client.post(
            '/api/business/orders/', {}, format='json', HTTP_X_API_KEY=self.read_raw
        )
        self.assertEqual(resp.status_code, 403)

    def test_write_key_cannot_manage_keys(self):
        resp = self.client.get('/api/api-keys/', HTTP_X_API_KEY=self.write_raw)
        self.assertEqual(resp.status_code, 403)

    def test_write_key_cannot_create_keys(self):
        resp = self.client.post(
            '/api/api-keys/create/',
            {'business_id': self.business.business_id},
            format='json', HTTP_X_API_KEY=self.write_raw,
        )
        self.assertEqual(resp.status_code, 403)

    def test_admin_key_can_list_keys(self):
        resp = self.client.get('/api/api-keys/', HTTP_X_API_KEY=self.admin_raw)
        self.assertEqual(resp.status_code, 200)


class InboundWebhookTest(TestCase):
    def setUp(self):
        self.user, self.business = make_business(9006, 'hookowner')
        self.wk = ezzy_api_models.WebhookImportKey.objects.create(
            business=self.business, key='wh_test_key_123456'
        )
        self.client = APIClient()
        self.url = f'/api/webhooks/order/inbound/{self.wk.key}/'

    def test_invalid_key_404(self):
        resp = self.client.post(
            '/api/webhooks/order/inbound/nope/', {}, format='json'
        )
        self.assertEqual(resp.status_code, 404)

    def test_disabled_key_403(self):
        self.wk.is_active = False
        self.wk.save()
        resp = self.client.post(self.url, {'order_id': 'X1'}, format='json')
        self.assertEqual(resp.status_code, 403)

    def test_valid_post_creates_temp_order_and_log(self):
        resp = self.client.post(self.url, {
            'order_id': 'WH-100', 'customer_name': 'Hook Customer',
            'phone': '55533333', 'address': 'Zone 55 St 100', 'cod': 250,
        }, format='json')
        self.assertIn(resp.status_code, (200, 201))
        self.assertTrue(
            orders_models.TempOrder.objects.filter(
                business=self.business, source_type='webhook'
            ).exists()
        )
        self.assertTrue(
            ezzy_api_models.WebhookImportLog.objects.filter(
                webhook_key=self.wk, business=self.business
            ).exists()
        )

    def test_bad_wc_signature_401(self):
        self.wk.wc_webhook_secret = 'shh_secret'
        self.wk.save()
        resp = self.client.post(
            self.url, {'order_id': 'WH-101'}, format='json',
            HTTP_X_WC_WEBHOOK_SIGNATURE='bm90LXRoZS1yZWFsLXNpZ25hdHVyZQ==',
        )
        self.assertEqual(resp.status_code, 401)
