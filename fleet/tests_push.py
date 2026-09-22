"""
Purpose: Cover Web Push for the driver PWA — registering a device, retiring a dead one, and the
         staff "ask for location" action that is the only way to reach a driver sitting in Waze.
Used by: `python manage.py test fleet.tests_push`
Notes:   pywebpush is patched out throughout. None of this may depend on a push service being
         reachable, and a push must never be mistaken for a position: it asks, it does not fetch.
"""
import json
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import Client, TestCase, override_settings

from core import models as core_models
from fleet.models import Driver, DriverNotification, DriverPushSubscription
from workforce.tests_views import WorkforceTestMixin

ENDPOINT = 'https://fcm.googleapis.com/fcm/send/abc123-device-one'
ENDPOINT_2 = 'https://fcm.googleapis.com/fcm/send/xyz789-device-two'

VAPID = dict(
    VAPID_PUBLIC_KEY='BM-ksm0jGfc090wog7Pjmrws5IcYKFQpZaVergHUGXM7JxQ0n12rZbKYxxKhYSnMFN5bZ6KaXi1eLeG___vUFrw',
    VAPID_PRIVATE_KEY='mls3nDgmFb2WMW4pNTPbs2vOfH870dIfafcrCl3HhHI',
)


def make_driver(username, driver_id, code):
    User = get_user_model()
    user = User.objects.create_user(username=username, password='push-pw-12345')
    profile = core_models.Profile.objects.create(
        user=user, is_driver=True, whatsapp='97412345678')
    driver = Driver.objects.create(
        driver_id=driver_id, user=user, profile=profile, driver_code=code,
        driver_phone='97412345678', driver_whatsapp='97412345678',
        driver_languages='english', driver_status='approved',
    )
    return user, driver


class PushSubscribeTests(TestCase):
    """The driver's browser registering, re-registering and unregistering a device."""

    def setUp(self):
        self.user, self.driver = make_driver('push_driver', 9601, 'PSH1')
        self.client = Client()
        self.client.force_login(self.user)

    def _subscribe(self, endpoint=ENDPOINT, p256dh='key-p256', auth='key-auth'):
        return self.client.post(
            '/api/driver/push/subscribe/',
            data=json.dumps({'subscription': {
                'endpoint': endpoint, 'keys': {'p256dh': p256dh, 'auth': auth}}}),
            content_type='application/json')

    def test_subscribe_registers_the_device(self):
        resp = self._subscribe()
        self.assertEqual(resp.status_code, 201)
        row = DriverPushSubscription.objects.get(endpoint=ENDPOINT)
        self.assertEqual(row.driver, self.driver)
        self.assertTrue(row.is_active)

    def test_resubscribing_the_same_endpoint_does_not_stack_rows(self):
        """The browser hands back the same subscription on every load."""
        self._subscribe()
        resp = self._subscribe(p256dh='rotated-key')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(DriverPushSubscription.objects.count(), 1)
        self.assertEqual(
            DriverPushSubscription.objects.get().p256dh, 'rotated-key')

    def test_resubscribing_revives_a_retired_device(self):
        """The browser offering the endpoint again is proof the phone is back."""
        self._subscribe()
        row = DriverPushSubscription.objects.get()
        row.note_failure('410: gone', fatal=True)
        self.assertFalse(row.is_active)

        self._subscribe()
        row.refresh_from_db()
        self.assertTrue(row.is_active)
        self.assertEqual(row.failure_count, 0)

    def test_two_phones_are_two_rows(self):
        self._subscribe(ENDPOINT)
        self._subscribe(ENDPOINT_2)
        self.assertEqual(
            DriverPushSubscription.active_for_driver(self.driver.pk).count(), 2)

    def test_a_subscription_without_keys_is_refused(self):
        resp = self.client.post(
            '/api/driver/push/subscribe/',
            data=json.dumps({'subscription': {'endpoint': ENDPOINT}}),
            content_type='application/json')
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(DriverPushSubscription.objects.exists())

    def test_a_non_https_endpoint_is_refused(self):
        resp = self._subscribe(endpoint='http://evil.example/push')
        self.assertEqual(resp.status_code, 400)

    def test_unsubscribe_drops_only_your_own_device(self):
        """An endpoint is a reachable address — one driver must not unregister another's."""
        self._subscribe()
        other_user, _ = make_driver('push_driver_2', 9602, 'PSH2')
        other = Client()
        other.force_login(other_user)

        resp = other.post('/api/driver/push/unsubscribe/',
                          data=json.dumps({'endpoint': ENDPOINT}),
                          content_type='application/json')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['removed'], 0)
        self.assertTrue(DriverPushSubscription.objects.filter(endpoint=ENDPOINT).exists())

        resp = self.client.post('/api/driver/push/unsubscribe/',
                                data=json.dumps({'endpoint': ENDPOINT}),
                                content_type='application/json')
        self.assertEqual(resp.json()['removed'], 1)
        self.assertFalse(DriverPushSubscription.objects.filter(endpoint=ENDPOINT).exists())

    def test_anonymous_cannot_register_a_device(self):
        anon = Client()
        resp = anon.post('/api/driver/push/subscribe/',
                         data=json.dumps({'subscription': {
                             'endpoint': ENDPOINT,
                             'keys': {'p256dh': 'a', 'auth': 'b'}}}),
                         content_type='application/json')
        self.assertIn(resp.status_code, (401, 403))


@override_settings(**VAPID)
class PushSendTests(TestCase):
    """Sending, and what happens to an address the push service no longer knows."""

    def setUp(self):
        self.user, self.driver = make_driver('push_send_driver', 9603, 'PSH3')
        self.sub = DriverPushSubscription.objects.create(
            driver=self.driver, endpoint=ENDPOINT, p256dh='p', auth='a')

    def _send(self):
        from fleet import push_service
        return push_service.send_to_driver(
            self.driver, title='Where are you?', body='Tap to open')

    def test_a_successful_send_is_counted_and_stamped(self):
        with patch('pywebpush.webpush') as wp:
            summary = self._send()
        self.assertEqual(wp.call_count, 1)
        self.assertEqual(summary['sent'], 1)
        self.sub.refresh_from_db()
        self.assertIsNotNone(self.sub.last_used_at)

    def test_the_payload_carries_the_location_request_url(self):
        """The flag in the URL is what makes the app take a fix on the way in."""
        from fleet import push_service
        with patch('pywebpush.webpush') as wp:
            push_service.request_location(self.driver, requested_by=self.user)
        payload = json.loads(wp.call_args.kwargs['data'])
        self.assertIn('locreq=1', payload['url'])
        self.assertTrue(payload['requireInteraction'])

    def test_a_gone_endpoint_is_retired_rather_than_retried(self):
        from pywebpush import WebPushException

        class Resp:
            status_code = 410

        with patch('pywebpush.webpush', side_effect=WebPushException('gone', response=Resp())):
            summary = self._send()
        self.assertEqual(summary['sent'], 0)
        self.assertEqual(summary['retired'], 1)
        self.sub.refresh_from_db()
        self.assertFalse(self.sub.is_active)

    def test_a_soft_failure_keeps_the_device_until_it_gives_up(self):
        from pywebpush import WebPushException

        class Resp:
            status_code = 500

        for _ in range(DriverPushSubscription.MAX_FAILURES - 1):
            with patch('pywebpush.webpush',
                       side_effect=WebPushException('boom', response=Resp())):
                self._send()
        self.sub.refresh_from_db()
        self.assertTrue(self.sub.is_active)

        with patch('pywebpush.webpush', side_effect=WebPushException('boom', response=Resp())):
            self._send()
        self.sub.refresh_from_db()
        self.assertFalse(self.sub.is_active)

    def test_a_retired_device_is_not_sent_to(self):
        self.sub.is_active = False
        self.sub.save(update_fields=['is_active'])
        with patch('pywebpush.webpush') as wp:
            summary = self._send()
        self.assertEqual(wp.call_count, 0)
        self.assertEqual(summary['devices'], 0)
        self.assertIn('No device', summary['reason'])

    @override_settings(VAPID_PRIVATE_KEY='', VAPID_PUBLIC_KEY='')
    def test_an_unconfigured_server_says_so_instead_of_failing(self):
        with patch('pywebpush.webpush') as wp:
            summary = self._send()
        self.assertEqual(wp.call_count, 0)
        self.assertIn('not configured', summary['reason'])

    def test_repeat_asks_leave_one_standing_in_app_row(self):
        """A failed send is retryable at once, so the log has to dedupe itself."""
        from fleet import push_service
        self.sub.delete()
        with patch('pywebpush.webpush'):
            push_service.request_location(self.driver)
            push_service.request_location(self.driver)
            push_service.request_location(self.driver)
        self.assertEqual(
            DriverNotification.objects.filter(driver=self.driver).count(), 1)

    def test_a_read_request_does_not_block_the_next_one(self):
        """Once the driver has seen it, a fresh ask is a fresh row."""
        from fleet import push_service
        self.sub.delete()
        with patch('pywebpush.webpush'):
            push_service.request_location(self.driver)
        DriverNotification.objects.update(is_read=True)
        with patch('pywebpush.webpush'):
            push_service.request_location(self.driver)
        self.assertEqual(
            DriverNotification.objects.filter(driver=self.driver).count(), 2)

    def test_the_request_is_logged_in_app_even_when_the_push_fails(self):
        """A driver with notifications off still sees it when they next open the app."""
        from fleet import push_service
        self.sub.delete()
        with patch('pywebpush.webpush') as wp:
            summary = push_service.request_location(self.driver)
        self.assertEqual(wp.call_count, 0)
        self.assertEqual(summary['sent'], 0)
        self.assertEqual(
            DriverNotification.objects.filter(driver=self.driver).count(), 1)


@override_settings(**VAPID)
class StaffRequestLocationTests(WorkforceTestMixin, TestCase):
    """The live-map button: who may press it, and how often."""

    def setUp(self):
        cache.clear()
        self.staff_user, _ = self.create_staff_user(username='map_staff')
        _, self.driver = make_driver('push_target_driver', 9604, 'PSH4')
        DriverPushSubscription.objects.create(
            driver=self.driver, endpoint=ENDPOINT, p256dh='p', auth='a')
        self.client = Client()
        self.client.force_login(self.staff_user)
        self.url = f'/workforce/drivers/{self.driver.pk}/request-location/'

    def tearDown(self):
        cache.clear()

    def test_staff_can_ask_a_driver_to_report_in(self):
        with patch('pywebpush.webpush') as wp:
            resp = self.client.post(self.url)
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()['ok'])
        self.assertEqual(wp.call_count, 1)

    def test_pressing_twice_does_not_buzz_the_phone_twice(self):
        with patch('pywebpush.webpush'):
            self.client.post(self.url)
        with patch('pywebpush.webpush') as wp:
            resp = self.client.post(self.url)
        self.assertEqual(resp.status_code, 429)
        self.assertEqual(wp.call_count, 0)

    def test_a_driver_with_no_device_gets_a_reason_not_an_error(self):
        DriverPushSubscription.objects.all().delete()
        with patch('pywebpush.webpush'):
            resp = self.client.post(self.url)
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertFalse(body['ok'])
        self.assertIn('No device', body['message'])

    def test_a_failed_send_does_not_start_the_cooldown(self):
        """Nothing reached the phone, so the dispatcher may try again at once."""
        DriverPushSubscription.objects.all().delete()
        with patch('pywebpush.webpush'):
            self.client.post(self.url)
            resp = self.client.post(self.url)
        self.assertEqual(resp.status_code, 200)

    def test_a_get_is_refused(self):
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 405)

    def test_a_non_staff_user_cannot_ask(self):
        user = self.create_non_staff_user(username='nosy')
        outsider = Client()
        outsider.force_login(user)
        with patch('pywebpush.webpush') as wp:
            resp = outsider.post(self.url)
        self.assertNotEqual(resp.status_code, 200)
        self.assertEqual(wp.call_count, 0)
