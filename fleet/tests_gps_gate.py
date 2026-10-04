"""
Purpose: Cover the driver app's location lock, and where the live map draws a driver whose app has gone quiet.
Used by: `python manage.py test fleet.tests_gps_gate` (the browser class needs playwright + chromium; it skips itself when absent)
Notes:   DRIVER_GPS_REQUIRED is off under TESTING so the Selenium suite can click through driver pages; these tests turn it back on.
"""
import os
import unittest

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.sessions.backends.db import SessionStore
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.test import Client, RequestFactory, TestCase, override_settings
from django.utils import timezone

from core import models as core_models
from core.context_processors import driver_pending_tasks
from delivery.models import DeliveryTask
from fleet.models import Driver, DriverLocation
from orders.models import Order
from workforce.tests_views import WorkforceTestMixin

User = get_user_model()

# Headless Chromium here needs the extracted system libs (see server-environment notes)
CHROME_LIBS = '/home/ezzyadmin/chrome-libs/extract/usr/lib/x86_64-linux-gnu'

DOHA = (25.2854, 51.5310)
WAKRAH = (25.1659, 51.6038)


def _driver(username, driver_id, status='approved'):
    user = User.objects.create_user(username=username, password='gate-pw-12345')
    phone = f'9740000{driver_id}'
    profile = core_models.Profile.objects.create(user=user, is_driver=True, whatsapp=phone)
    driver = Driver.objects.create(
        driver_id=driver_id, user=user, profile=profile, driver_code=f'GG{driver_id}',
        driver_phone=phone, driver_whatsapp=phone, driver_languages='english',
        driver_status=status, dashboard_access_enabled=True,
    )
    return user, driver


@override_settings(DRIVER_GPS_REQUIRED=True)
class LocationLockServedTests(TestCase):
    """Who gets the lock, and who must never be locked out."""

    def setUp(self):
        self.user, self.driver = _driver('gate_driver', 9601)
        self.client = Client()

    def _ctx(self, user):
        request = RequestFactory().get('/fleet/tasks/')
        request.user = user
        return driver_pending_tasks(request)

    def test_an_approved_driver_gets_the_lock_on_the_pwa(self):
        self.client.force_login(self.user)
        resp = self.client.get('/fleet/tasks/')
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'id="fleet_gpsgate_overlay"')
        self.assertContains(resp, 'fleet/js/ezzy-gps-gate.js')

    def test_the_older_driver_pages_are_locked_too(self):
        """Otherwise /delivery/ would be a way round the lock."""
        self.client.force_login(self.user)
        resp = self.client.get('/delivery/delivery_tasks/all/')
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'id="fleet_gpsgate_overlay"')
        self.assertContains(resp, 'fleet/js/ezzy-gps-gate.js')

    def test_an_applicant_is_never_locked_out(self):
        applicant, _ = _driver('gate_applicant', 9602, status='pending')
        self.assertFalse(self._ctx(applicant)['driver_gps_required'])
        self.assertTrue(self._ctx(self.user)['driver_gps_required'])

    def test_the_flag_switches_the_lock_off_for_everyone(self):
        with override_settings(DRIVER_GPS_REQUIRED=False):
            self.assertFalse(self._ctx(self.user)['driver_gps_required'])

    def test_staff_screens_on_the_shared_base_carry_no_lock(self):
        staff = User.objects.create_user(
            username='gate_staff', password='staff-pw-12345', is_staff=True)
        core_models.Profile.objects.create(user=staff, is_staff=True)
        self.client.force_login(staff)
        resp = self.client.get('/fleet/staff/cod-submissions/')
        self.assertEqual(resp.status_code, 200)
        self.assertNotContains(resp, 'fleet_gpsgate_overlay')


class SilentDriverOnTheLiveMapTests(WorkforceTestMixin, TestCase):
    """A driver whose app has gone quiet is drawn where it last reported —
    never at a customer's door they already left."""

    def setUp(self):
        self.user, self.profile = self.create_staff_user()
        self.client = Client()
        self.staff_login()
        self.business = self.create_business()
        self.driver = self.create_driver(code='SIL1')

    def _task(self, status, point):
        order = self.create_order(self.business)
        Order.objects.filter(pk=order.pk).update(latitude=point[0], longitude=point[1])
        task = self.create_delivery_task(order, driver=self.driver)
        # Straight to the row: the status guard reverts a fixture's jump to a
        # closed status, and these tests are about the map, not the guard.
        DeliveryTask.objects.filter(pk=task.pk).update(dl_task_status=status)
        return task

    def _fix(self, point, hours_ago):
        at = timezone.now() - timezone.timedelta(hours=hours_ago)
        loc = DriverLocation.objects.create(
            driver=self.driver, latitude=point[0], longitude=point[1], accuracy=10, fixed_at=at)
        DriverLocation.objects.filter(pk=loc.pk).update(created_at=at)
        return loc

    def _marker(self):
        resp = self.client.get('/workforce/tasks/live-map/',
                               HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(resp.status_code, 200)
        return {d['driver_id']: d for d in resp.json()['drivers']}[self.driver.pk]

    def test_a_silent_driver_sits_at_their_last_fix_with_its_time(self):
        self._task('delivered', DOHA)
        self._fix(WAKRAH, hours_ago=13)
        marker = self._marker()
        self.assertTrue(marker['has_gps'])
        self.assertTrue(marker['last_known'])
        self.assertAlmostEqual(marker['lat'], WAKRAH[0], places=4)
        self.assertAlmostEqual(marker['lng'], WAKRAH[1], places=4)
        self.assertGreaterEqual(marker['minutes_ago'], 13 * 60 - 1)
        self.assertTrue(marker['last_seen'])

    def test_a_finished_job_is_not_where_the_driver_is(self):
        self._task('delivered', DOHA)
        marker = self._marker()
        self.assertFalse(marker['has_gps'])
        self.assertIsNone(marker['lat'])

    def test_with_no_gps_ever_the_open_job_stands_in(self):
        self._task('delivered', DOHA)
        self._task('out_for_delivery', WAKRAH)
        marker = self._marker()
        self.assertFalse(marker['has_gps'])
        self.assertAlmostEqual(marker['lat'], WAKRAH[0], places=4)

    def test_a_driver_reporting_now_is_live_not_last_known(self):
        self._task('out_for_delivery', DOHA)
        self._fix(WAKRAH, hours_ago=0)
        marker = self._marker()
        self.assertTrue(marker['has_gps'])
        self.assertFalse(marker['last_known'])


def _playwright_available():
    try:
        import playwright.sync_api  # noqa: F401
    except ImportError:
        return False
    return True


@unittest.skipUnless(_playwright_available(), 'playwright not installed')
@override_settings(DRIVER_GPS_REQUIRED=True)
class LocationLockBrowserTests(StaticLiveServerTestCase):
    """The lock in a real browser: up when location is refused, gone on the first fix."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        if CHROME_LIBS not in os.environ.get('LD_LIBRARY_PATH', ''):
            os.environ['LD_LIBRARY_PATH'] = CHROME_LIBS + ':' + os.environ.get('LD_LIBRARY_PATH', '')
        # Playwright's sync API parks an event loop in this thread, which makes
        # Django refuse its own ORM calls during setUp/teardown.
        os.environ['DJANGO_ALLOW_ASYNC_UNSAFE'] = '1'
        from playwright.sync_api import sync_playwright
        cls._pw = sync_playwright().start()
        cls.browser = cls._pw.chromium.launch(args=['--no-sandbox'])

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls._pw.stop()
        super().tearDownClass()

    def setUp(self):
        self.user, self.driver = _driver('gate_browser', 9611)
        session = SessionStore()
        session['_auth_user_id'] = str(self.user.pk)
        session['_auth_user_backend'] = 'django.contrib.auth.backends.ModelBackend'
        session['_auth_user_hash'] = self.user.get_session_auth_hash()
        session.save()
        self.session_key = session.session_key

    def _open(self, **context_options):
        from urllib.parse import urlparse
        ctx = self.browser.new_context(
            viewport={'width': 412, 'height': 915}, is_mobile=True, has_touch=True,
            **context_options)
        self.addCleanup(ctx.close)
        ctx.add_cookies([{'name': settings.SESSION_COOKIE_NAME,
                          'value': self.session_key,
                          'domain': urlparse(self.live_server_url).hostname,
                          'path': '/'}])
        page = ctx.new_page()
        page.goto(self.live_server_url + '/fleet/tasks/', wait_until='domcontentloaded')
        # Really logged in: a bounce to the login page would pass the "hidden" checks.
        self.assertIn('/fleet/tasks/', page.url)
        self.assertEqual(page.locator('#fleet_gpsgate_overlay').count(), 1)
        return ctx, page

    def test_refused_location_locks_the_app(self):
        _, page = self._open()
        page.wait_for_selector('#fleet_gpsgate_overlay:not([hidden])', timeout=10000)
        self.assertTrue(page.evaluate("document.querySelector('.fleet-pwa').inert"))
        self.assertTrue(page.locator('#fleet_gpsgate_btn_retry').is_visible())

    def test_a_working_gps_never_sees_the_lock_and_reaches_the_server(self):
        _, page = self._open(
            permissions=['geolocation'],
            geolocation={'latitude': DOHA[0], 'longitude': DOHA[1], 'accuracy': 10})
        page.wait_for_function('window.EzzyGPS && window.EzzyGPS.getPosition() !== null',
                               timeout=10000)
        self.assertTrue(page.locator('#fleet_gpsgate_overlay').is_hidden())
        for _ in range(50):
            if DriverLocation.objects.filter(driver=self.driver).exists():
                break
            page.wait_for_timeout(200)
        self.assertTrue(DriverLocation.objects.filter(driver=self.driver).exists())

    def test_allowing_location_in_settings_lifts_the_lock_by_itself(self):
        """The browser announces the permission change; no tap needed."""
        ctx, page = self._open()
        page.wait_for_selector('#fleet_gpsgate_overlay:not([hidden])', timeout=10000)
        ctx.set_geolocation({'latitude': DOHA[0], 'longitude': DOHA[1], 'accuracy': 10})
        ctx.grant_permissions(['geolocation'])
        page.wait_for_selector('#fleet_gpsgate_overlay', state='hidden', timeout=10000)
        self.assertFalse(page.evaluate("document.querySelector('.fleet-pwa').inert"))

    def test_where_the_browser_stays_silent_the_button_lifts_it(self):
        """Older Safari has no permission events — the driver's tap is the re-check."""
        from urllib.parse import urlparse
        ctx = self.browser.new_context(viewport={'width': 412, 'height': 915},
                                       is_mobile=True, has_touch=True)
        self.addCleanup(ctx.close)
        ctx.add_init_script("Object.defineProperty(navigator, 'permissions', {value: undefined});")
        ctx.add_cookies([{'name': settings.SESSION_COOKIE_NAME, 'value': self.session_key,
                          'domain': urlparse(self.live_server_url).hostname, 'path': '/'}])
        page = ctx.new_page()
        page.goto(self.live_server_url + '/fleet/tasks/', wait_until='domcontentloaded')
        page.wait_for_selector('#fleet_gpsgate_overlay:not([hidden])', timeout=10000)

        ctx.set_geolocation({'latitude': DOHA[0], 'longitude': DOHA[1], 'accuracy': 10})
        ctx.grant_permissions(['geolocation'])
        page.wait_for_timeout(1500)
        self.assertTrue(page.locator('#fleet_gpsgate_overlay').is_visible())

        page.click('#fleet_gpsgate_btn_retry')
        page.wait_for_selector('#fleet_gpsgate_overlay', state='hidden', timeout=10000)
        self.assertFalse(page.evaluate("document.querySelector('.fleet-pwa').inert"))
