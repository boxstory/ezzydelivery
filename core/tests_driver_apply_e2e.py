# Purpose: Browser test for the driver application submit path — photo shrinking, progress upload, document swap.
# Used by: python manage.py test core.tests_driver_apply_e2e (needs playwright + chromium; skips itself when absent)
# Notes: Runs against a live server in Chromium because the thing under test is the client-side upload pipeline, which no Django test client exercises.

import os
import unittest

from allauth.socialaccount.models import SocialApp
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.sessions.backends.db import SessionStore
from django.contrib.sites.models import Site
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.test import override_settings

from core import models as core_models
from fleet.models import docs_with_image
from delivery.models import ZoneGroup
from fleet import models as fleet_models

User = get_user_model()

MEDIA_ROOT = '/tmp/ezzy-test-media-e2e'
# Headless Chromium here needs the extracted system libs (see server-environment notes)
CHROME_LIBS = '/home/ezzyadmin/chrome-libs/extract/usr/lib/x86_64-linux-gnu'


def _deps_available():
    try:
        import playwright.sync_api  # noqa: F401
        from PIL import Image  # noqa: F401
    except ImportError:
        return False
    return True


def _big_photo(path, w=3200, h=2400):
    """A ~multi-MB JPEG standing in for a modern phone camera shot."""
    from PIL import Image
    import random
    img = Image.new('RGB', (w, h))
    rnd = random.Random(7)
    img.putdata([(rnd.randrange(256), rnd.randrange(256), rnd.randrange(256))
                 for _ in range(w * h)])
    img.save(path, 'JPEG', quality=95)
    return path


@unittest.skipUnless(_deps_available(), 'playwright/Pillow not installed')
@override_settings(MEDIA_ROOT=MEDIA_ROOT)
class DriverApplySubmitBrowserTest(StaticLiveServerTestCase):
    """The Submit button must upload shrunken photos and land the application."""

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
        os.makedirs(MEDIA_ROOT, exist_ok=True)
        cls.photo_path = _big_photo(os.path.join(MEDIA_ROOT, 'phone_photo.jpg'))
        cls.photo_bytes = os.path.getsize(cls.photo_path)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls._pw.stop()
        super().tearDownClass()

    def setUp(self):
        app = SocialApp.objects.create(
            provider='google', name='Google', client_id='x', secret='y')
        app.sites.add(Site.objects.get_current())
        self.zone = ZoneGroup.objects.create(name='Central Doha', is_active=True)

        self.user = User.objects.create_user(
            username='e2e_applicant', email='e2e@example.com', password='pw12345!')
        profile = core_models.Profile.objects.filter(user=self.user).first() \
            or core_models.Profile(user=self.user)
        profile.username = self.user.username
        profile.email = self.user.email
        profile.first_name = 'Ashiraf'
        profile.last_name = 'Waluboga'
        profile.phone = '31029502'
        profile.whatsapp = '97431029502'
        profile.nationlity = 'Ugandan'
        profile.zone_name = 'Souq Waqif'
        profile.address = 'Building 6, Street 30'
        profile.date_of_birth = '1995-12-26'
        profile.save()
        self.profile = profile

        driver = fleet_models.Driver.objects.create(
            user=self.user, profile=profile, driver_id=profile.id,
            driver_status='pending', driver_code='997720', job_type='part_time')
        driver.preferred_zone_groups.set([self.zone.id])
        fleet_models.DriverVehicle.objects.create(
            driver=driver, vehicle_type='car', vehicle_no='Q268667')
        self.driver = driver

        session = SessionStore()
        session['_auth_user_id'] = str(self.user.pk)
        session['_auth_user_backend'] = 'django.contrib.auth.backends.ModelBackend'
        session['_auth_user_hash'] = self.user.get_session_auth_hash()
        session.save()
        self.session_key = session.session_key

    def _page(self):
        from urllib.parse import urlparse
        ctx = self.browser.new_context(
            viewport={'width': 412, 'height': 915}, is_mobile=True, has_touch=True)
        ctx.add_cookies([{'name': settings.SESSION_COOKIE_NAME,
                          'value': self.session_key,
                          'domain': urlparse(self.live_server_url).hostname,
                          'path': '/'}])
        page = ctx.new_page()
        page.goto(self.live_server_url + '/join_us/driver/?step=4')
        # A disabled Submit button means the session cookie did not authenticate
        assert page.get_attribute('#core_join_driver_btn_submit', 'disabled') is None, \
            'not logged in — check the session cookie domain'
        return ctx, page

    def test_submit_shrinks_photos_uploads_and_lands_the_application(self):
        ctx, page = self._page()
        errors = []
        page.on('pageerror', lambda e: errors.append(str(e)))
        posts = []
        page.on('response', lambda r: posts.append((r.request.method, r.url, r.status))
                if r.request.method == 'POST' else None)

        for key in ('Selfie', 'QID', 'Driving_License'):
            page.set_input_files('#core_join_driver_file_' + key, self.photo_path)

        # Each pick reports its own before/after size once shrinking finishes
        page.wait_for_selector('[data-doc-note="Selfie"]:not(.d-none)')
        page.wait_for_function(
            "() => Array.from(document.querySelectorAll('[data-doc-note]'))"
            ".filter(n => /ready/.test(n.textContent)).length === 3")
        note = page.text_content('[data-doc-note="Selfie"]')
        self.assertIn('→', note, 'expected a "3.2 MB → 480 KB" style note, got: ' + note)

        page.fill('input[name="doc_no_QID"]', '29335632728')
        page.click('#core_join_driver_btn_submit')

        # The upload panel replaces the dead "Submitting…" label
        page.wait_for_selector('#core_join_driver_box_upload:not(.d-none)')
        # A successful submit swaps the page for the read-only status view
        try:
            page.wait_for_selector('text=Application under review', timeout=60000)
        except Exception:
            self.fail('submit never completed — posts=%r js_errors=%r body=%r' % (
                posts, errors, page.inner_text('body')[:1500]))
        self.assertEqual(errors, [], 'JS errors on the page: %s' % errors)
        ctx.close()

        profile = core_models.Profile.objects.get(pk=self.profile.pk)
        self.assertTrue(profile.is_driver)
        self.assertEqual(profile.verification_status, 'pending')

        docs = docs_with_image(self.driver.driver_document.all())
        self.assertEqual(docs.count(), 3)
        self.assertEqual(
            docs.get(document_type='QID').document_no, '29335632728')

        # The point of the whole exercise: what landed is a fraction of the original
        for doc in docs:
            stored = doc.document_file.size
            self.assertLess(stored, self.photo_bytes / 3,
                            'photo was not shrunk before upload: %d vs %d'
                            % (stored, self.photo_bytes))

    def test_denied_location_does_not_block_the_submission(self):
        """Geolocation is refused here (no permission granted to the context)."""
        ctx, page = self._page()
        for key in ('Selfie', 'QID', 'Istimara'):
            page.set_input_files('#core_join_driver_file_' + key, self.photo_path)
        page.wait_for_function(
            "() => Array.from(document.querySelectorAll('[data-doc-note]'))"
            ".filter(n => /ready/.test(n.textContent)).length === 3")
        page.click('#core_join_driver_btn_submit')
        page.wait_for_selector('text=Application under review', timeout=60000)
        ctx.close()

        self.assertTrue(core_models.Profile.objects.get(pk=self.profile.pk).is_driver)
        self.assertEqual(
            fleet_models.Driver.objects.get(pk=self.driver.pk).driver_meta.get(
                'registration_location'), None)

    def test_save_and_continue_advances_the_wizard(self):
        """The Next button goes through the same XHR sender as Submit."""
        ctx, page = self._page()
        errors = []
        page.on('pageerror', lambda e: errors.append(str(e)))

        page.click('[data-step-btn="1"]')          # steppers only go backwards
        page.wait_for_selector('[data-wiz-step="1"].cja__wiz-step--active')
        page.fill('input[name="first_name"]', 'Ashiraf Edited')
        page.click('#core_join_driver_btn_next')

        # Server redirects to ?step=2; the swapped document opens on that section
        page.wait_for_selector('[data-wiz-step="2"].cja__wiz-step--active', timeout=60000)
        self.assertEqual(errors, [], 'JS errors on the page: %s' % errors)
        ctx.close()

        self.assertEqual(
            core_models.Profile.objects.get(pk=self.profile.pk).first_name,
            'Ashiraf Edited')
