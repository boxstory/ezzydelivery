"""
Purpose: Cover the one-device-per-driver rule — device binding at login, the OTP gate on
         an unrecognised device, revocation of the previous device, and the ops release.
Used by: `python manage.py test fleet.tests_device`
Notes:   Uses two independent test clients to stand in for two phones; the device cookie
         is what makes a client a "known" handset.
"""
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from core import models as core_models
from core.models import WhatsAppVerification
from fleet.device_service import DEVICE_COOKIE, SESSION_PENDING_DEVICE, SESSION_REVOKED
from fleet.models import Driver, DriverDevice


def make_approved_driver(user, profile, driver_id):
    """An approved driver — the only kind the device rule applies to."""
    return Driver.objects.create(
        driver_id=driver_id,
        user=user,
        profile=profile,
        driver_code=f'DEV{driver_id}',
        driver_phone='97412345678',
        driver_whatsapp='97412345678',
        driver_languages='english',
        driver_status='approved',
    )


def _fake_send(**kwargs):
    """Stand-in for create_verification that never touches WhatsApp."""
    verification = WhatsAppVerification.objects.create(
        user=kwargs.get('user'),
        phone_number=kwargs.get('phone_number') or '97412345678',
        verification_code='123456',
        verification_type=kwargs.get('verification_type') or 'device_verify',
        expires_at=timezone.now() + timezone.timedelta(minutes=10),
    )
    return {'success': True, 'verification': verification, 'send_result': {'success': True}}


@override_settings(DRIVER_DEVICE_ENFORCEMENT=True)
class DriverDeviceTests(TestCase):
    """Signing in on a second phone must retire the first."""

    def setUp(self):
        User = get_user_model()
        self.password = 'device-pw-12345'
        self.driver = User.objects.create_user(
            username='dev_driver', password=self.password
        )
        profile = core_models.Profile.objects.create(
            user=self.driver, is_driver=True, whatsapp='97412345678'
        )
        make_approved_driver(self.driver, profile, 9101)
        self.phone_a = Client()
        self.phone_b = Client()

    def _login(self, client):
        return client.post(
            reverse('account_login'),
            {'login': 'dev_driver', 'password': self.password},
            follow=True,
        )

    def test_first_login_creates_a_pending_device(self):
        self._login(self.phone_a)

        device = DriverDevice.objects.get(user=self.driver)
        self.assertEqual(device.status, DriverDevice.STATUS_PENDING)
        self.assertIsNone(device.activated_at)
        # The token cookie is how the phone is recognised next time.
        self.assertIn(DEVICE_COOKIE, self.phone_a.cookies)
        self.assertEqual(self.phone_a.cookies[DEVICE_COOKIE].value, device.device_token)

    def test_pending_device_is_held_at_the_gate(self):
        self._login(self.phone_a)

        response = self.phone_a.get('/fleet/dashboard/')

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('fleet:device_verify'))

    @patch('fleet.device_service.create_verification', side_effect=_fake_send)
    def test_correct_code_activates_the_device(self, mock_send):
        self._login(self.phone_a)
        self.phone_a.post(reverse('fleet:device_send_code'))

        response = self.phone_a.post(reverse('fleet:device_verify'), {'code': '123456'})

        device = DriverDevice.objects.get(user=self.driver)
        self.assertEqual(device.status, DriverDevice.STATUS_ACTIVE)
        self.assertIsNotNone(device.activated_at)
        self.assertEqual(response.status_code, 302)
        self.assertNotIn(SESSION_PENDING_DEVICE, self.phone_a.session)

    @patch('fleet.device_service.create_verification', side_effect=_fake_send)
    def test_wrong_code_leaves_the_device_pending(self, mock_send):
        self._login(self.phone_a)
        self.phone_a.post(reverse('fleet:device_send_code'))

        self.phone_a.post(reverse('fleet:device_verify'), {'code': '000000'})

        device = DriverDevice.objects.get(user=self.driver)
        self.assertEqual(device.status, DriverDevice.STATUS_PENDING)

    @patch('fleet.device_service.create_verification', side_effect=_fake_send)
    def test_second_phone_revokes_the_first(self, mock_send):
        # Phone A is confirmed and working.
        self._login(self.phone_a)
        self.phone_a.post(reverse('fleet:device_send_code'))
        self.phone_a.post(reverse('fleet:device_verify'), {'code': '123456'})
        device_a = DriverDevice.objects.get(user=self.driver)
        self.assertEqual(device_a.status, DriverDevice.STATUS_ACTIVE)

        # Phone B signs in — a device we have never seen.
        self._login(self.phone_b)

        device_a.refresh_from_db()
        self.assertEqual(device_a.status, DriverDevice.STATUS_REVOKED)
        self.assertEqual(device_a.revoked_reason, DriverDevice.REVOKED_NEW_DEVICE)
        # Phone A's own session now carries the reason, so it can explain itself.
        self.assertEqual(
            self.phone_a.session.get(SESSION_REVOKED), DriverDevice.REVOKED_NEW_DEVICE
        )

    @patch('fleet.device_service.create_verification', side_effect=_fake_send)
    def test_revoked_phone_is_signed_out_on_its_next_request(self, mock_send):
        self._login(self.phone_a)
        self.phone_a.post(reverse('fleet:device_send_code'))
        self.phone_a.post(reverse('fleet:device_verify'), {'code': '123456'})
        self._login(self.phone_b)

        response = self.phone_a.get('/fleet/dashboard/')

        self.assertEqual(response.status_code, 302)
        self.assertNotIn('_auth_user_id', self.phone_a.session)

    @patch('fleet.device_service.create_verification', side_effect=_fake_send)
    def test_returning_to_a_known_phone_skips_the_code(self, mock_send):
        """A driver going back to their own phone is not a stranger."""
        self._login(self.phone_a)
        self.phone_a.post(reverse('fleet:device_send_code'))
        self.phone_a.post(reverse('fleet:device_verify'), {'code': '123456'})
        self._login(self.phone_b)  # phone A revoked

        # The driver picks their own phone back up: opening the app is what
        # signs the revoked session out, and only then can they log in again.
        self.phone_a.get('/fleet/dashboard/')
        self._login(self.phone_a)

        device_a = DriverDevice.objects.get(user=self.driver, device_token=self.phone_a.cookies[DEVICE_COOKIE].value)
        self.assertEqual(device_a.status, DriverDevice.STATUS_ACTIVE)
        self.assertNotIn(SESSION_PENDING_DEVICE, self.phone_a.session)
        # ...and phone B is the one that loses the account now.
        self.assertEqual(
            DriverDevice.objects.filter(
                user=self.driver, status=DriverDevice.STATUS_ACTIVE).count(), 1
        )

    def test_non_driver_login_creates_no_device(self):
        User = get_user_model()
        client_user = User.objects.create_user(username='dev_client', password=self.password)
        core_models.Profile.objects.create(user=client_user, is_driver=False)

        self.phone_b.post(
            reverse('account_login'),
            {'login': 'dev_client', 'password': self.password},
            follow=True,
        )

        self.assertFalse(DriverDevice.objects.filter(user=client_user).exists())


@override_settings(DRIVER_DEVICE_ENFORCEMENT=True)
class DriverDeviceOpsTests(TestCase):
    """The WhatsApp-is-down fallback: ops releases the device by hand."""

    def setUp(self):
        User = get_user_model()
        self.password = 'device-pw-12345'
        self.driver = User.objects.create_user(username='dev_driver2', password=self.password)
        profile = core_models.Profile.objects.create(
            user=self.driver, is_driver=True, whatsapp='97412345678')
        make_approved_driver(self.driver, profile, 9102)
        self.staff = User.objects.create_user(
            username='dev_staff', password=self.password, is_staff=True)
        core_models.Profile.objects.create(user=self.staff, dept_operations=True)

        self.phone = Client()
        self.phone.post(
            reverse('account_login'),
            {'login': 'dev_driver2', 'password': self.password},
            follow=True,
        )
        self.device = DriverDevice.objects.get(user=self.driver)

    def test_staff_release_activates_the_device(self):
        self.client.force_login(self.staff)

        self.client.post(reverse('workforce:driver_device_release', args=[self.device.pk]))

        self.device.refresh_from_db()
        self.assertEqual(self.device.status, DriverDevice.STATUS_ACTIVE)
        self.assertIsNotNone(self.device.activated_at)
        self.assertEqual(self.device.approved_by, self.staff)

    def test_released_device_passes_the_gate(self):
        self.client.force_login(self.staff)
        self.client.post(reverse('workforce:driver_device_release', args=[self.device.pk]))

        # One bounce through the gate is expected: the middleware only reads the
        # session flag, and the verify view is what clears it.
        response = self.phone.get('/fleet/dashboard/', follow=True)

        self.assertNotIn(
            reverse('fleet:device_verify'), [url for url, _ in response.redirect_chain[-1:]]
        )
        self.assertNotIn(SESSION_PENDING_DEVICE, self.phone.session)

    def test_staff_can_revoke_an_active_device(self):
        self.client.force_login(self.staff)
        self.client.post(reverse('workforce:driver_device_release', args=[self.device.pk]))

        self.client.post(reverse('workforce:driver_device_revoke', args=[self.device.pk]))

        self.device.refresh_from_db()
        self.assertEqual(self.device.status, DriverDevice.STATUS_REVOKED)
        self.assertEqual(self.device.revoked_reason, DriverDevice.REVOKED_STAFF)

    def test_console_lists_pending_devices(self):
        self.client.force_login(self.staff)

        response = self.client.get(reverse('workforce:driver_devices'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'dev_driver2')


@override_settings(DRIVER_DEVICE_ENFORCEMENT=True)
class DriverApplicantTests(TestCase):
    """Someone still applying is not yet a driver as far as the device rule cares."""

    def setUp(self):
        User = get_user_model()
        self.password = 'applicant-pw-12345'
        self.applicant = User.objects.create_user(
            username='dev_applicant', password=self.password)
        # Submitting the join-driver form sets is_driver long before approval.
        self.profile = core_models.Profile.objects.create(
            user=self.applicant, is_driver=True, whatsapp='97412345678')
        self.phone = Client()

    def _login(self):
        return self.phone.post(
            reverse('account_login'),
            {'login': 'dev_applicant', 'password': self.password},
            follow=True,
        )

    def test_applicant_gets_no_device_and_no_gate(self):
        self._login()

        self.assertFalse(DriverDevice.objects.filter(user=self.applicant).exists())
        self.assertNotIn(SESSION_PENDING_DEVICE, self.phone.session)

    def test_applicant_can_reach_the_onboarding_pages(self):
        """The application form and its verification screen must stay reachable."""
        self._login()

        verify_url = reverse('fleet:device_verify')
        for name in ('core:join_us', 'core:driver_register', 'core:update_driver'):
            response = self.phone.get(reverse(name))
            self.assertNotEqual(
                getattr(response, 'url', ''), verify_url,
                msg=f'{name} was blocked by the device gate',
            )

    def test_pending_driver_row_is_still_outside_the_rule(self):
        make_approved_driver(self.applicant, self.profile, 9103)
        Driver.objects.filter(user=self.applicant).update(driver_status='pending')

        self._login()

        self.assertFalse(DriverDevice.objects.filter(user=self.applicant).exists())

    def test_gate_starts_once_the_driver_is_approved(self):
        make_approved_driver(self.applicant, self.profile, 9104)

        self._login()

        device = DriverDevice.objects.get(user=self.applicant)
        self.assertEqual(device.status, DriverDevice.STATUS_PENDING)
