"""
Purpose: A verified driver ops have not cleared to work must reach their profile and the opportunities board, and nothing else.
Used by: manage.py test fleet.tests_access
Notes: The gate sits ON TOP of driver_status, so every test here uses an approved driver — the point is that
       approval alone is no longer enough. DRIVER_DEVICE_ENFORCEMENT is already off in the test settings.
"""

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from core.models import Profile
from fleet.access import has_dashboard_access
from fleet.models import Driver


def make_approved_driver(user, profile, driver_id, cleared=False):
    """An approved driver, optionally cleared to work."""
    return Driver.objects.create(
        driver_id=driver_id,
        user=user,
        profile=profile,
        driver_code=f'ACC{driver_id}',
        driver_phone='97412345678',
        driver_whatsapp='97412345678',
        driver_languages='english',
        driver_status='approved',
        dashboard_access_enabled=cleared,
    )


@override_settings(SECURE_SSL_REDIRECT=False, ALLOWED_HOSTS=['testserver'])
class DashboardAccessGateTests(TestCase):
    """Approval opens the door; dashboard access decides how far in they get."""

    PASSWORD = 'Str0ngPass!99'

    def setUp(self):
        user = get_user_model().objects.create_user(
            username='gatedriver', email='gate-access@example.com', password=self.PASSWORD)
        profile, _ = Profile.objects.get_or_create(user=user)
        profile.is_driver = True
        profile.save()
        self.user = user
        self.profile = profile
        self.driver = make_approved_driver(user, profile, 9921, cleared=False)

        self.client = Client()
        self.client.force_login(user)

    def _clear(self):
        Driver.objects.filter(pk=self.driver.pk).update(dashboard_access_enabled=True)

    # --- the resolver ----------------------------------------------------

    def test_approval_alone_is_not_access(self):
        """An approved driver with the flag off may not work."""
        self.assertFalse(has_dashboard_access(self.driver))

    def test_access_without_approval_is_still_refused(self):
        """The flag never outranks account standing."""
        self.driver.dashboard_access_enabled = True
        self.driver.driver_status = 'suspended'
        self.assertFalse(has_dashboard_access(self.driver))

    def test_no_driver_has_no_access(self):
        """A missing driver row is a refusal, not a crash."""
        self.assertFalse(has_dashboard_access(None))

    # --- the HTML gate ---------------------------------------------------

    def test_dashboard_redirects_to_opportunities(self):
        """The dashboard is not theirs yet; the board is."""
        response = self.client.get(reverse('fleet:fleet_dashboard'))
        self.assertRedirects(response, reverse('fleet:opportunities'))

    def test_gate_redirect_is_not_cacheable(self):
        """A cached gate redirect is how the device gate once caused a redirect loop."""
        response = self.client.get(reverse('fleet:fleet_dashboard'))
        self.assertIn('no-store', response.headers.get('Cache-Control', ''))

    def test_tasks_page_is_gated(self):
        response = self.client.get(reverse('fleet:driver_tasks'))
        self.assertRedirects(response, reverse('fleet:opportunities'))

    def test_cod_page_is_gated(self):
        response = self.client.get(reverse('fleet:cod_collection'))
        self.assertRedirects(response, reverse('fleet:opportunities'))

    def test_earnings_page_is_gated(self):
        response = self.client.get(reverse('fleet:driver_earnings'))
        self.assertRedirects(response, reverse('fleet:opportunities'))

    def test_granting_access_opens_the_dashboard(self):
        """The same request succeeds once ops flip the flag."""
        self._clear()
        response = self.client.get(reverse('fleet:fleet_dashboard'))
        self.assertEqual(response.status_code, 200)

    # --- surfaces that must stay open ------------------------------------

    def test_opportunities_is_reachable(self):
        """The redirect target must never be gated, or it loops."""
        response = self.client.get(reverse('fleet:opportunities'))
        self.assertEqual(response.status_code, 200)

    def test_profile_is_reachable(self):
        response = self.client.get(reverse('fleet:driver_profile_mobile'))
        self.assertEqual(response.status_code, 200)

    def test_documents_are_reachable(self):
        """They still need to finish their paperwork while they wait."""
        response = self.client.get(reverse('fleet:driver_documents'))
        self.assertEqual(response.status_code, 200)

    # --- server-side enforcement -----------------------------------------

    def test_accept_task_endpoint_refuses(self):
        """The UI hiding a button is not the gate; the endpoint is."""
        response = self.client.post(
            reverse('delivery:accept_task'), {'task_id': 1},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertFalse(response.json()['success'])

    def test_pickup_claim_endpoint_refuses_with_403(self):
        response = self.client.post(
            reverse('fleet:accept_pickup'), {'pickup_id': 1},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()['code'], 'driver_dashboard_not_granted')

    def test_pickup_pool_is_empty(self):
        """One condition at the single choke point empties every pickup surface."""
        from delivery.selectors import pickup_pool_for
        self.assertEqual(pickup_pool_for(self.driver).count(), 0)

    # --- navigation ------------------------------------------------------

    def test_nav_hides_work_destinations(self):
        """Five tabs into a refusal is worse than two tabs that work."""
        response = self.client.get(reverse('fleet:opportunities'))
        body = response.content.decode()
        self.assertNotIn(reverse('fleet:driver_tasks'), body)
        self.assertNotIn(reverse('fleet:cod_collection'), body)
        self.assertIn(reverse('fleet:driver_profile_mobile'), body)

    def test_nav_returns_once_access_is_granted(self):
        self._clear()
        response = self.client.get(reverse('fleet:opportunities'))
        body = response.content.decode()
        self.assertIn(reverse('fleet:driver_tasks'), body)
        self.assertIn(reverse('fleet:cod_collection'), body)


@override_settings(SECURE_SSL_REDIRECT=False, ALLOWED_HOSTS=['testserver'])
class StaffGrantTests(TestCase):
    """Ops own this switch, and granting it leaves a trail."""

    PASSWORD = 'Str0ngPass!99'

    def setUp(self):
        User = get_user_model()

        self.staff = User.objects.create_user(
            username='opsuser', email='ops-access@example.com',
            password=self.PASSWORD, is_staff=True)
        staff_profile, _ = Profile.objects.get_or_create(user=self.staff)
        staff_profile.is_staff = True
        staff_profile.is_superadmin = True
        staff_profile.save()

        driver_user = User.objects.create_user(
            username='granteddriver', email='granted@example.com', password=self.PASSWORD)
        driver_profile, _ = Profile.objects.get_or_create(user=driver_user)
        driver_profile.is_driver = True
        driver_profile.save()
        self.driver = make_approved_driver(driver_user, driver_profile, 9922, cleared=False)

        self.url = reverse('workforce:driver_set_dashboard_access',
                           args=[self.driver.driver_id])

    def test_staff_can_grant(self):
        client = Client()
        client.force_login(self.staff)
        response = client.post(self.url, '{"enabled": true}', content_type='application/json')

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['enabled'])

        self.driver.refresh_from_db()
        self.assertTrue(self.driver.dashboard_access_enabled)
        self.assertIsNotNone(self.driver.dashboard_access_granted_at)
        self.assertEqual(self.driver.dashboard_access_granted_by, self.staff)

    def test_withdrawing_clears_the_grant_trail(self):
        Driver.objects.filter(pk=self.driver.pk).update(
            dashboard_access_enabled=True, dashboard_access_granted_by=self.staff)
        client = Client()
        client.force_login(self.staff)
        client.post(self.url, '{"enabled": false}', content_type='application/json')

        self.driver.refresh_from_db()
        self.assertFalse(self.driver.dashboard_access_enabled)
        self.assertIsNone(self.driver.dashboard_access_granted_at)

    def test_cannot_clear_an_unapproved_driver(self):
        """Clearing a pending account to work would contradict itself."""
        Driver.objects.filter(pk=self.driver.pk).update(driver_status='pending')
        client = Client()
        client.force_login(self.staff)
        response = client.post(self.url, '{"enabled": true}', content_type='application/json')

        self.assertEqual(response.status_code, 400)
        self.driver.refresh_from_db()
        self.assertFalse(self.driver.dashboard_access_enabled)

    def test_non_staff_cannot_grant(self):
        User = get_user_model()
        outsider = User.objects.create_user(
            username='outsider', email='outsider@example.com', password=self.PASSWORD)
        Profile.objects.get_or_create(user=outsider)

        client = Client()
        client.force_login(outsider)
        response = client.post(self.url, '{"enabled": true}', content_type='application/json')

        self.assertNotEqual(response.status_code, 200)
        self.driver.refresh_from_db()
        self.assertFalse(self.driver.dashboard_access_enabled)
