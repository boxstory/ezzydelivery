"""
Purpose: Cover SessionTimeoutMiddleware — staff-only idle logout, long-lived
         driver/client sessions, and the driver-classification cache TTL.
Used by: `python manage.py test core.tests_session_timeout`
Notes:   The middleware is the only thing standing between a driver on a phone
         and a re-login, so each audience gets an explicit case here.
"""
import time

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase, override_settings
from django.utils import timezone

from core import models as core_models
from core.middleware import SessionTimeoutMiddleware


class SessionTimeoutMiddlewareTests(TestCase):
    """Idle logout applies to staff only; phones keep their session."""

    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.staff = User.objects.create_user(
            username='sess_staff', password='pw-staff-123', is_staff=True
        )
        cls.client_user = User.objects.create_user(
            username='sess_client', password='pw-client-123'
        )
        cls.driver = User.objects.create_user(
            username='sess_driver', password='pw-driver-123'
        )
        core_models.Profile.objects.create(user=cls.driver, is_driver=True)

    def _age_last_activity(self, days=2):
        """Backdate the session's activity marker past any plausible timeout."""
        session = self.client.session
        session['last_activity'] = (
            timezone.now() - timezone.timedelta(days=days)
        ).isoformat()
        session.save()

    def test_idle_staff_is_logged_out(self):
        self.client.force_login(self.staff)
        self._age_last_activity()

        response = self.client.get('/business/dashboard/')

        self.assertEqual(response.status_code, 302)
        self.assertIn('/accounts/login/', response.url)
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_idle_client_stays_signed_in(self):
        """A client on a phone must survive the staff idle window."""
        self.client.force_login(self.client_user)
        self._age_last_activity()

        self.client.get('/business/dashboard/')

        self.assertEqual(
            self.client.session.get('_auth_user_id'), str(self.client_user.pk)
        )

    def test_idle_driver_stays_signed_in_with_long_expiry(self):
        self.client.force_login(self.driver)
        self._age_last_activity()

        self.client.get('/fleet/dashboard/')

        self.assertEqual(
            self.client.session.get('_auth_user_id'), str(self.driver.pk)
        )
        self.assertEqual(
            self.client.session.get_expiry_age(),
            SessionTimeoutMiddleware.DRIVER_SESSION_AGE,
        )

    @override_settings(SESSION_COOKIE_AGE=60 * 60 * 24 * 30)
    def test_demoted_driver_loses_the_one_year_expiry(self):
        """A stale 1-year cookie must not outlive the driver role."""
        self.client.force_login(self.driver)
        self.client.get('/fleet/dashboard/')

        core_models.Profile.objects.filter(user=self.driver).update(is_driver=False)
        session = self.client.session
        session['_is_driver_at'] = time.time() - (
            SessionTimeoutMiddleware.DRIVER_CACHE_TTL + 60
        )
        session.save()

        self.client.get('/business/dashboard/')

        self.assertLessEqual(self.client.session.get_expiry_age(), 60 * 60 * 24 * 30)


class DriverCacheTests(TestCase):
    """The cached driver answer must expire, not stick for the whole session."""

    def setUp(self):
        self.factory = RequestFactory()
        self.middleware = SessionTimeoutMiddleware(lambda request: None)
        User = get_user_model()
        self.user = User.objects.create_user(
            username='sess_becomes_driver', password='pw-becomes-123'
        )
        self.profile = core_models.Profile.objects.create(user=self.user, is_driver=False)

    def _request(self, session):
        request = self.factory.get('/')
        request.user = self.user
        request.session = session
        return request

    def test_promotion_is_picked_up_once_the_cache_expires(self):
        session = self.client.session

        self.assertFalse(self.middleware._is_driver(self._request(session)))

        self.profile.is_driver = True
        self.profile.save(update_fields=['is_driver'])

        # Still cached — no extra query, and the stale answer is expected here.
        self.assertFalse(self.middleware._is_driver(self._request(session)))

        session['_is_driver_at'] = time.time() - (
            SessionTimeoutMiddleware.DRIVER_CACHE_TTL + 60
        )
        self.assertTrue(self.middleware._is_driver(self._request(session)))
