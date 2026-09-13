"""
Purpose: Regression tests for the "Page Expired" dead-end drivers hit when their
         browser held no csrftoken cookie (stale service-worker / proxy copy of a form).
Used by: manage.py test core.tests_csrf_recovery
Notes: enforce_csrf_checks=True is what makes the test client run the real CSRF
       middleware; without it every POST silently passes.
"""
import re

from django.test import Client, TestCase, override_settings


CSRF_COOKIE = 'csrftoken'


@override_settings(SECURE_SSL_REDIRECT=False, ALLOWED_HOSTS=['ezzydelivery.qa', 'testserver'])
class CsrfCookieRecoveryTests(TestCase):
    """A CSRF failure caused by a missing cookie must repair itself in one step."""

    host = 'ezzydelivery.qa'

    def _client(self, referer_path):
        return Client(
            enforce_csrf_checks=True,
            secure=True,
            HTTP_HOST=self.host,
            HTTP_X_FORWARDED_PROTO='https',
            HTTP_REFERER=f'https://{self.host}{referer_path}',
        )

    def test_missing_cookie_403_plants_a_fresh_cookie(self):
        """The 403 itself must carry Set-Cookie, or every retry fails identically."""
        c = self._client('/password/reset/request/')
        response = c.post('/password/reset/request/',
                          {'reset_method': 'email', 'identifier': '71188023'})

        self.assertEqual(response.status_code, 403)
        self.assertIn(CSRF_COOKIE, response.cookies)
        self.assertTrue(response.cookies[CSRF_COOKIE].value)
        self.assertEqual(response.headers.get('Cache-Control'), 'no-store')

    def test_retry_after_the_403_succeeds(self):
        """Reload + resubmit — the loop the driver was stuck in — must now go through."""
        c = self._client('/password/reset/request/')
        c.post('/password/reset/request/', {'reset_method': 'email', 'identifier': '71188023'})

        page = c.get('/password/reset/request/?_r=1')
        token = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"',
                          page.content.decode()).group(1)
        retry = c.post('/password/reset/request/',
                       {'reset_method': 'email', 'identifier': '71188023',
                        'csrfmiddlewaretoken': token})

        self.assertNotEqual(retry.status_code, 403)

    def test_failure_page_offers_a_cache_busted_retry(self):
        """A plain back-link would re-serve the same cached page with the same dead token."""
        c = self._client('/password/reset/request/')
        body = c.post('/password/reset/request/',
                      {'reset_method': 'email', 'identifier': '71188023'}).content.decode()

        self.assertIn('/password/reset/request/?_r=1', body)
        self.assertIn('ezzydriver-dynamic', body)  # stale SW page cache is purged

    def test_login_failure_redirects_with_a_cookie(self):
        """/accounts/ takes the redirect branch — it must still hand back a cookie."""
        c = self._client('/accounts/login/')
        response = c.post('/accounts/login/', {'login': 'nobody@example.com', 'password': 'x'})

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers['Location'], '/accounts/login/')
        self.assertIn(CSRF_COOKIE, response.cookies)


@override_settings(SECURE_SSL_REDIRECT=False, ALLOWED_HOSTS=['ezzydelivery.qa', 'testserver'])
class AuthPageCacheHeaderTests(TestCase):
    """Auth forms must never be storable: a replayed copy carries a dead token."""

    def test_password_reset_pages_are_no_store(self):
        for path in ('/password/reset/request/', '/password/reset/verify/'):
            with self.subTest(path=path):
                response = self.client.get(path, secure=True, HTTP_HOST='ezzydelivery.qa',
                                           HTTP_X_FORWARDED_PROTO='https', follow=True)
                self.assertEqual(response.headers.get('Cache-Control'), 'no-store')

    def test_login_page_is_no_store(self):
        response = self.client.get('/accounts/login/', secure=True, HTTP_HOST='ezzydelivery.qa',
                                   HTTP_X_FORWARDED_PROTO='https')
        self.assertEqual(response.headers.get('Cache-Control'), 'no-store')
