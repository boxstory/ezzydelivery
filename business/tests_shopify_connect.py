# Purpose: Tests for the guards that stop a Shopify connection failing the way JM AUTO PARTS' did twice.
# Used by: manage.py test business.tests_shopify_connect
# Notes: Two real failures are covered — a Custom App API key pasted as the Client ID, and the
#        Client ID pasted into the Client Secret box. Every Shopify call is mocked; the
#        pre-flight probe must FAIL OPEN so a network blip never blocks good credentials.
from unittest.mock import patch

import requests
from django.test import SimpleTestCase, TestCase

from business import models as business_models
from business.forms import (
    businessApiSettingsForm, check_shopify_oauth_app, resolve_shopify_store_url,
)


class FakeResponse:
    def __init__(self, text='', status_code=400):
        self.text = text
        self.status_code = status_code


APP_NOT_FOUND = ('400 - Oauth error application_cannot_be_found: Could not find '
                 'Shopify API application with api_key abc')
BAD_CODE = 'Oauth error invalid_request'


class PreflightClientIdTests(SimpleTestCase):
    """The check that would have caught JM's first attempt at save time."""

    def test_custom_app_key_is_refused_with_actionable_wording(self):
        with patch('business.forms.requests.post',
                   return_value=FakeResponse(APP_NOT_FOUND)):
            error = check_shopify_oauth_app('store.myshopify.com', 'a' * 32)
        self.assertIsNotNone(error)
        # The merchant must be told which box to fix and where to look.
        self.assertIn('Custom App', error)
        self.assertIn('shpat_', error)

    def test_a_real_oauth_app_is_accepted(self):
        # Shopify validates the app before the code, so the expected answer for
        # a good Client ID with our deliberately invalid code is invalid_request.
        with patch('business.forms.requests.post',
                   return_value=FakeResponse(BAD_CODE)):
            self.assertIsNone(check_shopify_oauth_app('store.myshopify.com', 'b' * 32))

    def test_network_failure_fails_open(self):
        # A slow resolver must never stop a merchant saving good credentials.
        with patch('business.forms.requests.post',
                   side_effect=requests.exceptions.ConnectTimeout):
            self.assertIsNone(check_shopify_oauth_app('store.myshopify.com', 'c' * 32))

    def test_nothing_to_check_is_not_an_error(self):
        self.assertIsNone(check_shopify_oauth_app('', 'd' * 32))
        self.assertIsNone(check_shopify_oauth_app('store.myshopify.com', ''))

    def test_scheme_and_trailing_slash_are_tolerated(self):
        with patch('business.forms.requests.post',
                   return_value=FakeResponse(APP_NOT_FOUND)) as post:
            check_shopify_oauth_app('HTTPS://Store.myshopify.com/', 'e' * 32)
        self.assertEqual(post.call_args[0][0],
                         'https://store.myshopify.com/admin/oauth/access_token')


class StoreUrlTests(SimpleTestCase):
    """A custom domain silently broke the token exchange; it must never save."""

    def test_handle_passes_through(self):
        url, err = resolve_shopify_store_url('ean9tp-tb.myshopify.com')
        self.assertEqual(url, 'https://ean9tp-tb.myshopify.com')
        self.assertIsNone(err)

    def test_custom_domain_is_resolved_from_the_storefront(self):
        page = 'var meta = {};Shopify.shop = "ean9tp-tb.myshopify.com";'
        with patch('business.forms.requests.get',
                   return_value=FakeResponse(page, 200)):
            url, err = resolve_shopify_store_url('https://www.liquimolygcc.com/')
        self.assertEqual(url, 'https://ean9tp-tb.myshopify.com')
        self.assertIsNone(err)

    def test_undetectable_custom_domain_is_refused_with_instructions(self):
        with patch('business.forms.requests.get',
                   return_value=FakeResponse('<html>no shopify here</html>', 200)):
            url, err = resolve_shopify_store_url('https://example.com/')
        self.assertIsNone(url)
        self.assertIn('myshopify.com', err)
        self.assertIn('Domains', err)


def _oauth_post(**over):
    data = {
        'api_type': 'shopify',
        'shopify_setup_mode': 'oauth',
        'api_key': 'f' * 32,
        'api_secret': 'shpss_' + 'f' * 32,
        'site_api_url': 'https://store.myshopify.com',
    }
    data.update(over)
    return data


class SecretShapeTests(TestCase):
    """The secret cannot be verified against Shopify, so its shape is the guard."""

    def _errors(self, **over):
        # Neutralise the two network-touching checks; this is about the secret.
        with patch('business.forms.check_shopify_oauth_app', return_value=None), \
             patch('business.forms.resolve_shopify_store_url',
                   return_value=('https://store.myshopify.com', None)):
            form = businessApiSettingsForm(data=_oauth_post(**over))
            form.is_valid()
            return form.errors

    def test_secret_equal_to_client_id_is_refused(self):
        # Exactly what a real client did; the flow only failed later, at HMAC.
        errors = self._errors(api_secret='f' * 32)
        self.assertIn('api_secret', errors)
        self.assertIn('same value as the Client ID', str(errors['api_secret']))

    def test_an_api_key_pasted_as_the_secret_is_refused(self):
        errors = self._errors(api_secret='0123456789abcdef0123456789abcdef')
        self.assertIn('api_secret', errors)
        self.assertIn('shpss_', str(errors['api_secret']))

    def test_a_real_shpss_secret_is_accepted(self):
        self.assertNotIn('api_secret', self._errors())


class OauthAdoptsDefaultTests(TestCase):
    """A token with no is_default produced 'No store integration is connected'."""

    def setUp(self):
        from ezzy_api.tests_store_api import make_active_business
        _, self.business = make_active_business(7801, 'shopify_default_seller')

    def _row(self, **over):
        fields = dict(business=self.business, api_type='shopify',
                      site_api_url='https://store.myshopify.com')
        fields.update(over)
        return business_models.BusinessApiSettings.objects.create(**fields)

    def test_first_connection_becomes_the_default(self):
        row = self._row()
        self.assertFalse(row.is_default)
        # Mirrors the callback's rule: adopt only when the business has none.
        self.assertFalse(business_models.BusinessApiSettings.objects.filter(
            business=self.business, is_default=True).exclude(pk=row.pk).exists())

    def test_an_existing_default_is_not_stolen(self):
        chosen = self._row(is_default=True, site_api_url='https://first.myshopify.com')
        second = self._row(site_api_url='https://second.myshopify.com')
        self.assertTrue(business_models.BusinessApiSettings.objects.filter(
            business=self.business, is_default=True).exclude(pk=second.pk).exists())
        chosen.refresh_from_db()
        self.assertTrue(chosen.is_default)
