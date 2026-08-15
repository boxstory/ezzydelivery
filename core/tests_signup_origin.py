# Purpose: Tests for signup-origin tracking — the session capture and the stamp written when the Profile is created.
# Used by: python manage.py test core.tests_signup_origin
# Notes: The stamp is exercised through the real core:profile_add POST, which is where Profile rows are actually created.

from allauth.socialaccount.models import SocialApp
from django.contrib.auth import get_user_model
from django.contrib.sites.models import Site
from django.test import Client, TestCase
from django.urls import reverse

from core import models as core_models
from core import signup_origin

User = get_user_model()

# Attribution is skipped for crawler traffic, so every test browses as a browser.
BROWSER_UA = ('Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 '
              '(KHTML, like Gecko) Chrome/120.0 Mobile Safari/537.36')


class SignupOriginCaptureTest(TestCase):
    """The middleware records first-touch and upgrades on intent pages."""

    @classmethod
    def setUpTestData(cls):
        # The driver landing page renders a {% provider_login_url 'google' %} button
        app = SocialApp.objects.create(
            provider='google', name='Google', client_id='x', secret='y')
        app.sites.add(Site.objects.get_current())

    def setUp(self):
        self.client = Client(HTTP_USER_AGENT=BROWSER_UA)

    def test_driver_join_link_is_recorded_as_driver_intent(self):
        self.client.get(reverse('core:join_driver_start'))
        origin = self.client.session[signup_origin.SESSION_KEY]
        self.assertEqual(origin['source'], signup_origin.SOURCE_DRIVER)
        self.assertEqual(origin['landing_path'], '/join_us/driver/start/')

    def test_plain_website_visit_is_recorded_as_website(self):
        self.client.get(reverse('webpages:index'))
        origin = self.client.session[signup_origin.SESSION_KEY]
        self.assertEqual(origin['source'], signup_origin.SOURCE_WEBSITE)

    def test_browsing_then_opening_the_driver_link_upgrades_to_driver(self):
        self.client.get(reverse('webpages:index'))
        self.client.get(reverse('core:join_driver_start'))
        origin = self.client.session[signup_origin.SESSION_KEY]
        self.assertEqual(origin['source'], signup_origin.SOURCE_DRIVER)
        # First touch is preserved even though the source moved on
        self.assertEqual(origin['landing_path'], '/')

    def test_landing_straight_on_login_is_direct(self):
        self.client.get('/accounts/login/')
        origin = self.client.session[signup_origin.SESSION_KEY]
        self.assertEqual(origin['source'], signup_origin.SOURCE_DIRECT)

    def test_utm_tags_and_offsite_referrer_are_kept(self):
        self.client.get(
            reverse('webpages:index') + '?utm_source=google&utm_campaign=drivers',
            HTTP_REFERER='https://www.google.com/search?q=delivery+jobs',
        )
        origin = self.client.session[signup_origin.SESSION_KEY]
        self.assertEqual(origin['utm'], {'utm_source': 'google', 'utm_campaign': 'drivers'})
        self.assertIn('google.com', origin['referrer'])

    def test_own_domain_referrer_is_not_treated_as_attribution(self):
        self.client.get(reverse('webpages:index'), HTTP_REFERER='http://testserver/about/')
        origin = self.client.session[signup_origin.SESSION_KEY]
        self.assertEqual(origin['referrer'], '')

    def test_static_and_api_paths_do_not_start_attribution(self):
        self.client.get('/static/does-not-exist.css')
        self.assertNotIn(signup_origin.SESSION_KEY, self.client.session)

    def test_crawlers_never_open_a_session(self):
        bot = Client(HTTP_USER_AGENT='Mozilla/5.0 (compatible; Googlebot/2.1)')
        bot.get(reverse('core:join_driver_start'))
        self.assertNotIn(signup_origin.SESSION_KEY, bot.session)


class SignupOriginStampTest(TestCase):
    """Creating the Profile writes whatever the session recorded."""

    PROFILE_POST = {
        'first_name': 'Muneeb', 'last_name': 'Saleem',
        'email': 'muneeb@test.com', 'phone': '71510623', 'whatsapp': '71510623',
        'address': 'Doha', 'zone_name': 'Al Sadd', 'nationlity': 'Pakistani',
        'date_of_birth': '1995-01-01', 'instagram': '',
    }

    def setUp(self):
        self.client = Client(HTTP_USER_AGENT=BROWSER_UA)
        self.user = User.objects.create_user(
            username='applicant', password='Pw@12345', email='applicant@test.com')
        self.client.login(username='applicant', password='Pw@12345')

    def _set_session_origin(self, origin):
        session = self.client.session
        session[signup_origin.SESSION_KEY] = origin
        session.save()

    def test_driver_origin_lands_on_the_profile(self):
        self._set_session_origin({
            'source': signup_origin.SOURCE_DRIVER,
            'landing_path': '/join_us/driver/start/',
            'referrer': 'https://www.google.com/',
            'utm': {'utm_source': 'google'},
        })
        self.client.post(reverse('core:profile_add'), self.PROFILE_POST)

        profile = core_models.Profile.objects.get(user=self.user)
        self.assertEqual(profile.signup_source, signup_origin.SOURCE_DRIVER)
        self.assertEqual(profile.get_signup_source_display(), 'Driver Join Link')
        self.assertEqual(profile.signup_landing_path, '/join_us/driver/start/')
        self.assertEqual(profile.signup_utm, {'utm_source': 'google'})
        self.assertFalse(profile.signup_source_inferred)

    def test_missing_session_origin_falls_back_to_unknown(self):
        self.client.post(reverse('core:profile_add'), self.PROFILE_POST)

        profile = core_models.Profile.objects.get(user=self.user)
        self.assertEqual(profile.signup_source, signup_origin.SOURCE_UNKNOWN)
        self.assertEqual(profile.signup_landing_path, '')


class DriverJoinFlowOriginTest(TestCase):
    """The real driver route: land on the join link, sign in, land on the form."""

    @classmethod
    def setUpTestData(cls):
        app = SocialApp.objects.create(
            provider='google', name='Google', client_id='x', secret='y')
        app.sites.add(Site.objects.get_current())

    def setUp(self):
        self.client = Client(HTTP_USER_AGENT=BROWSER_UA)

    def test_profile_created_by_the_driver_form_is_attributed_to_the_link(self):
        # Anonymous visit to the public driver landing page
        self.client.get(reverse('core:join_driver_start'))

        # Google sign-in (session data survives login) then the application form
        User.objects.create_user(username='newdriver', password='Pw@12345',
                                 email='newdriver@test.com')
        self.client.login(username='newdriver', password='Pw@12345')
        self.client.get(reverse('core:join_driver'))

        profile = core_models.Profile.objects.get(user__username='newdriver')
        self.assertEqual(profile.signup_source, signup_origin.SOURCE_DRIVER)
        self.assertEqual(profile.signup_landing_path, '/join_us/driver/start/')


class SignupOriginBackfillTest(TestCase):
    """The backfill command guesses from the account and flags every guess."""

    def test_driver_role_is_inferred_and_flagged(self):
        from django.core.management import call_command
        from io import StringIO

        user = User.objects.create_user(username='olddriver', password='Pw@12345')
        profile = core_models.Profile.objects.create(user=user, is_driver=True)
        self.assertEqual(profile.signup_source, signup_origin.SOURCE_UNKNOWN)

        call_command('backfill_signup_source', stdout=StringIO())

        profile.refresh_from_db()
        self.assertEqual(profile.signup_source, signup_origin.SOURCE_DRIVER)
        self.assertTrue(profile.signup_source_inferred)

    def test_tracked_sources_are_never_overwritten(self):
        from django.core.management import call_command
        from io import StringIO

        user = User.objects.create_user(username='trackeduser', password='Pw@12345')
        profile = core_models.Profile.objects.create(
            user=user, is_driver=True, signup_source=signup_origin.SOURCE_WEBSITE)

        call_command('backfill_signup_source', stdout=StringIO())

        profile.refresh_from_db()
        self.assertEqual(profile.signup_source, signup_origin.SOURCE_WEBSITE)
        self.assertFalse(profile.signup_source_inferred)
