"""
Purpose: Hold the Profile name and the auth User name to a single value on every write path.
Used by: `python manage.py test core.tests_name_sync`.
Notes: Covers the two drift sources that produced 198 mismatched drivers — a Google display
       name left on the User, and the staff identity drawer writing only the User row.
"""

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase

from core import name_sync
from core.models import Profile

User = get_user_model()


class ProfileNameSyncTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='applicant', email='applicant@example.com',
            first_name='Hama', last_name='Hama',
        )

    def test_new_profile_borrows_the_auth_user_name(self):
        """A bare Profile row (the driver-application path) is no longer nameless."""
        profile = Profile.objects.create(user=self.user)

        self.assertEqual(profile.first_name, 'Hama')
        self.assertEqual(profile.last_name, 'Hama')

    def test_profile_name_wins_and_is_mirrored_onto_the_user(self):
        profile = Profile.objects.create(
            user=self.user, first_name='Mohamed', last_name='Guesmi')

        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, 'Mohamed')
        self.assertEqual(self.user.last_name, 'Guesmi')
        self.assertEqual(profile.first_name, 'Mohamed')

    def test_editing_the_profile_name_later_rewrites_the_user(self):
        profile = Profile.objects.create(user=self.user)
        profile.first_name = 'Mani'
        profile.last_name = 'Kandan'
        profile.save()

        self.user.refresh_from_db()
        self.assertEqual(self.user.get_full_name(), 'Mani Kandan')

    def test_update_fields_without_a_name_does_not_touch_the_user(self):
        profile = Profile.objects.create(
            user=self.user, first_name='Mohamed', last_name='Guesmi')
        User.objects.filter(pk=self.user.pk).update(first_name='Stale', last_name='Row')

        profile.zone_name = 'sadd'
        profile.save(update_fields=['zone_name'])

        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, 'Stale')

    def test_a_nameless_profile_never_blanks_the_user_name(self):
        profile = Profile.objects.create(user=self.user)
        profile.first_name = ''
        profile.last_name = ''
        profile.save()

        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, 'Hama')

    def test_long_profile_name_is_cut_to_what_auth_user_can_store(self):
        long_name = 'A' * 200
        Profile.objects.create(user=self.user, first_name=long_name, last_name='Khel')

        self.user.refresh_from_db()
        self.assertEqual(len(self.user.first_name), name_sync.USER_NAME_MAX_LENGTH)

    def test_cached_user_instance_is_kept_in_step(self):
        """driver.user / request.user must not render the name we just replaced."""
        profile = Profile.objects.create(user=self.user)
        profile.first_name = 'Rahees'
        profile.last_name = 'K'
        profile.save()

        self.assertEqual(profile.user.get_full_name(), 'Rahees K')


class SyncProfileNamesCommandTests(TestCase):
    def _drifted(self, username, user_name, profile_name):
        first, last = user_name.split()
        user = User.objects.create_user(
            username=username, first_name=first, last_name=last)
        profile = Profile.objects.create(user=user)
        # Bypass save() so the row lands out of sync, the way the old data is.
        pfirst, plast = profile_name.split()
        Profile.objects.filter(pk=profile.pk).update(first_name=pfirst, last_name=plast)
        return user, Profile.objects.get(pk=profile.pk)

    def test_dry_run_writes_nothing(self):
        user, _profile = self._drifted('d1', 'Ezzy Driver01', 'Rahees K')

        call_command('sync_profile_names', '--dry-run')

        user.refresh_from_db()
        self.assertEqual(user.first_name, 'Ezzy')

    def test_backfill_gives_the_user_the_profile_name(self):
        user, _profile = self._drifted('d1', 'Ezzy Driver01', 'Rahees K')

        call_command('sync_profile_names')

        user.refresh_from_db()
        self.assertEqual(user.get_full_name(), 'Rahees K')

    def test_backfill_seeds_a_profile_that_has_no_name(self):
        user = User.objects.create_user(
            username='d2', first_name='Akbar', last_name='Ali')
        profile = Profile.objects.create(user=user)
        Profile.objects.filter(pk=profile.pk).update(first_name='', last_name='')

        call_command('sync_profile_names')

        profile.refresh_from_db()
        self.assertEqual(profile.first_name, 'Akbar')
        self.assertEqual(profile.last_name, 'Ali')


class DriverSponsorFieldTests(TestCase):
    """The sponsor is free text on the Driver row, blank until someone fills it."""

    def test_a_new_driver_starts_with_no_sponsor(self):
        from fleet.models import Driver

        user = User.objects.create_user(username='sponsored')
        driver = Driver.objects.create(
            user=user, driver_id=9901, driver_phone='30000001',
            driver_whatsapp='30000001', driver_languages='english',
        )

        self.assertEqual(driver.driver_sponsor, '')

    def test_the_sponsor_survives_a_round_trip(self):
        from fleet.models import Driver

        user = User.objects.create_user(username='sponsored2')
        Driver.objects.create(
            user=user, driver_id=9902, driver_phone='30000002',
            driver_whatsapp='30000002', driver_languages='english',
            driver_sponsor='Al Rayyan Trading WLL',
        )

        self.assertEqual(
            Driver.objects.get(pk=9902).driver_sponsor, 'Al Rayyan Trading WLL')

    def test_the_drivers_form_accepts_a_sponsor(self):
        from fleet.forms import DriverJoinForm

        form = DriverJoinForm(data={
            'driver_phone': '30000003',
            'driver_whatsapp': '30000003',
            'driver_languages': 'english',
            'driver_sponsor': '  Doha Logistics Co  ',
            'driver_bio': 'Rider',
        })

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data['driver_sponsor'], 'Doha Logistics Co')
