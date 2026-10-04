# Purpose: Tests for the staff "Change Role" endpoint on the user verification page.
# Used by: manage.py test workforce.tests_change_role
# Notes: Covers the driver->business correction, the guards, and the optional side effects.

import json

from django.test import TestCase
from django.urls import reverse

from core import models as core_models
from fleet import models as fleet_models
from workforce.tests_views import WorkforceTestMixin


class ChangeUserRoleTests(WorkforceTestMixin, TestCase):
    def setUp(self):
        self.staff, _ = self.create_staff_user(username='rolestaff')
        self.client.force_login(self.staff)
        self.driver = self.create_driver(did=8801, status='approved', code='RLE01')
        self.driver.dashboard_access_enabled = True
        self.driver.save(update_fields=['dashboard_access_enabled'])
        self.profile = self.driver.profile

    def _url(self, profile=None):
        return reverse('workforce:change_user_role',
                       args=[(profile or self.profile).id])

    def _post(self, payload, profile=None):
        return self.client.post(
            self._url(profile), data=json.dumps(payload),
            content_type='application/json')

    def test_driver_becomes_business_and_old_application_is_closed(self):
        resp = self._post({'role': 'business', 'close_existing': True,
                           'reset_verification': True})
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()['success'])

        self.profile.refresh_from_db()
        self.assertTrue(self.profile.is_business)
        self.assertFalse(self.profile.is_driver)
        # No Business row yet, so the business form must still be demanded
        self.assertFalse(self.profile.is_business_profile_completed)
        self.assertEqual(self.profile.verification_status, 'incomplete')
        self.assertIsNone(self.profile.verification_applied_at)

        self.driver.refresh_from_db()
        self.assertEqual(self.driver.driver_status, 'rejected')
        self.assertEqual(self.driver.driver_availability, 'offline')
        self.assertFalse(self.driver.dashboard_access_enabled)

    def test_close_existing_off_leaves_the_driver_row_alone(self):
        resp = self._post({'role': 'business', 'close_existing': False,
                           'reset_verification': False})
        self.assertEqual(resp.status_code, 200)

        self.profile.refresh_from_db()
        self.assertTrue(self.profile.is_business)
        self.assertEqual(self.profile.verification_status, 'pending')

        self.driver.refresh_from_db()
        self.assertEqual(self.driver.driver_status, 'approved')
        self.assertTrue(self.driver.dashboard_access_enabled)

    def test_business_becomes_driver_and_business_is_deactivated(self):
        business = self.create_business(bid=8802, code='RLE02')
        profile = business.profile
        resp = self._post({'role': 'driver'}, profile=profile)
        self.assertEqual(resp.status_code, 200)

        profile.refresh_from_db()
        self.assertTrue(profile.is_driver)
        self.assertFalse(profile.is_business)
        self.assertFalse(profile.is_driver_profile_completed)

        business.refresh_from_db()
        self.assertEqual(business.business_status, 'inactive')

    def test_clearing_both_roles(self):
        resp = self._post({'role': 'user'})
        self.assertEqual(resp.status_code, 200)
        self.profile.refresh_from_db()
        self.assertFalse(self.profile.is_business)
        self.assertFalse(self.profile.is_driver)
        self.driver.refresh_from_db()
        self.assertEqual(self.driver.driver_status, 'rejected')

    def test_same_role_is_rejected(self):
        resp = self._post({'role': 'driver'})
        self.assertEqual(resp.status_code, 400)
        self.assertIn('already', resp.json()['error'])

    def test_invalid_role_is_rejected(self):
        resp = self._post({'role': 'warehouse'})
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(resp.json()['success'])

    def test_staff_profile_cannot_be_reroled(self):
        staff_profile = core_models.Profile.objects.get(user=self.staff)
        resp = self._post({'role': 'business'}, profile=staff_profile)
        self.assertEqual(resp.status_code, 400)
        self.assertIn('staff account', resp.json()['error'])

    def test_non_staff_is_refused(self):
        self.client.logout()
        outsider = self.create_non_staff_user(username='rolesnoop')
        self.client.force_login(outsider)
        resp = self._post({'role': 'business'})
        self.assertNotEqual(resp.status_code, 200)
        self.profile.refresh_from_db()
        self.assertTrue(self.profile.is_driver)

    def test_get_is_not_allowed(self):
        resp = self.client.get(self._url())
        self.assertEqual(resp.status_code, 405)

    def test_card_follows_the_new_role_after_the_change(self):
        """The bug behind this: a seller moved off a driver application kept
        being shown their old 80% "Driver Profile" as the thing to review."""
        self.driver.driver_bio = 'x'
        self.driver.driver_languages = 'English'
        self.driver.driver_whatsapp = '97400000000'
        self.driver.driver_license_number = '123'
        self.driver.save()
        self.assertEqual(self.profile.get_role_profile_completion_percentage(), 100)

        self._post({'role': 'business'})
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.role_kind(), 'business')
        # No Business row yet, so there is nothing done towards the new role
        self.assertEqual(self.profile.get_role_profile_completion_percentage(), 0)

        resp = self.client.get(
            reverse('workforce:user_verification_list') + '?status=all&q=Test8801')
        body = resp.content.decode()
        self.assertIn('Business Profile', body)
        self.assertNotIn('> Driver Profile', body)
        self.assertIn('Past application', body)
        self.assertIn('(past role)', body)

    def test_mid_application_driver_still_reads_as_a_driver(self):
        """No role flag is set until the application is submitted, so a partly
        filled driver row must still drive the card."""
        self.profile.is_driver = False
        self.profile.save(update_fields=['is_driver'])
        self.assertEqual(self.profile.role_kind(), 'driver')

    def test_account_with_neither_record_has_no_role(self):
        plain = core_models.Profile.objects.get(
            user=self.create_non_staff_user(username='plainuser'))
        self.assertEqual(plain.role_kind(), '')
        self.assertEqual(plain.get_role_profile_completion_percentage(), 0)

    def test_button_renders_on_the_verification_page(self):
        resp = self.client.get(reverse('workforce:user_verification_list'))
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode()
        self.assertIn('data-action="change_role"', body)
        self.assertIn('uvlRoleOverlay', body)
