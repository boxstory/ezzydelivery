# Purpose: Tests for the public driver application POST path (core:join_driver) — draft saves, document handling, final submit.
# Used by: python manage.py test core.tests_driver_apply
# Notes: Everything goes through the real multipart POST, since the bugs these cover live in the view's document loop.

from allauth.socialaccount.models import SocialApp
from django.contrib.auth import get_user_model
from django.contrib.sites.models import Site
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from core import models as core_models
from core.views import MAX_UPLOAD_SIZE
from fleet.models import docs_with_image
from delivery.models import ZoneGroup
from fleet import models as fleet_models

User = get_user_model()

BROWSER_UA = ('Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 '
              '(KHTML, like Gecko) Chrome/120.0 Mobile Safari/537.36')


def photo(name='id.jpg', size=1024):
    """A stand-in upload — the view validates size/extension/content type, not pixels."""
    return SimpleUploadedFile(name, b'x' * size, content_type='image/jpeg')


@override_settings(MEDIA_ROOT='/tmp/ezzy-test-media')
class DriverApplyPostTest(TestCase):
    """The application POST: draft saves, doc numbers, and the final submit gate."""

    @classmethod
    def setUpTestData(cls):
        app = SocialApp.objects.create(
            provider='google', name='Google', client_id='x', secret='y')
        app.sites.add(Site.objects.get_current())
        cls.zone = ZoneGroup.objects.create(name='Central Doha', is_active=True)

    def setUp(self):
        self.client = Client(HTTP_USER_AGENT=BROWSER_UA)
        self.user = User.objects.create_user(
            username='applicant', email='applicant@example.com', password='pw12345!')
        self.client.force_login(self.user)
        self.url = reverse('core:join_driver')

    def profile_fields(self):
        return {
            'first_name': 'Ashiraf', 'last_name': 'Waluboga',
            'phone': '31029502', 'whatsapp': '97431029502',
            'nationlity': 'Ugandan', 'zone_name': 'Souq Waqif',
            'address': 'Building 6, Street 30', 'date_of_birth': '1995-12-26',
        }

    def full_payload(self, **extra):
        data = self.profile_fields()
        data.update({
            'action': 'submit',
            'veh-vehicle_type': 'car', 'veh-vehicle_no': 'Q268667',
            'veh-vehicle_model': 'Corolla', 'veh-vehicle_color': 'White',
            'job_type_opts': ['part_time'],
            'work_time_slabs': ['evening'],
            'zone_groups': [str(self.zone.id)],
        })
        data.update(extra)
        return data

    def driver(self):
        return fleet_models.Driver.objects.get(user=self.user)

    # --- typed document numbers survive without a photo -------------------

    def test_draft_save_keeps_typed_document_number_without_a_file(self):
        data = self.profile_fields()
        data.update({'action': 'save', 'veh-vehicle_type': 'car',
                     'doc_no_Driving_License': '29580001910',
                     'doc_no_Istimara': 'Q268667'})
        self.client.post(self.url, data)

        docs = {d.document_type: d.document_no for d in self.driver().driver_document.all()}
        self.assertEqual(docs.get('Driving License'), '29580001910')
        self.assertEqual(docs.get('Istimara'), 'Q268667')

    def test_number_only_rows_do_not_count_as_uploaded_documents(self):
        """The placeholder image must never satisfy the '2 ID documents' gate."""
        data = self.profile_fields()
        data.update({'action': 'save', 'veh-vehicle_type': 'car',
                     'doc_no_QID': '111', 'doc_no_Driving_License': '222',
                     'doc_no_Istimara': '333'})
        self.client.post(self.url, data)

        driver = self.driver()
        self.assertEqual(driver.driver_document.count(), 3)
        self.assertEqual(docs_with_image(driver.driver_document.all()).count(), 0)

        # ...and a final submit is still refused for want of real photos
        resp = self.client.post(self.url, self.full_payload(), follow=True)
        self.assertFalse(core_models.Profile.objects.get(user=self.user).is_driver)
        body = resp.content.decode()
        self.assertIn('selfie photo is required', body)

    def test_number_typed_later_lands_on_the_existing_photo_row(self):
        self.client.post(self.url, dict(
            self.profile_fields(), action='save', **{'doc_QID': photo('qid.jpg')}))
        self.client.post(self.url, dict(
            self.profile_fields(), action='save', doc_no_QID='29335632728'))

        doc = self.driver().driver_document.get(document_type='QID')
        self.assertEqual(doc.document_no, '29335632728')
        self.assertIn('qid', doc.document_file.name.lower())

    # --- one bad photo must not discard the whole draft -------------------

    def test_oversized_photo_on_a_draft_save_keeps_the_typed_sections(self):
        oversized = photo('huge.jpg', MAX_UPLOAD_SIZE + 1024)
        data = dict(self.profile_fields(), action='save',
                    **{'veh-vehicle_type': 'car', 'doc_QID': oversized})
        resp = self.client.post(self.url, data, follow=True)

        profile = core_models.Profile.objects.get(user=self.user)
        self.assertEqual(profile.first_name, 'Ashiraf')       # draft still saved
        self.assertEqual(profile.zone_name, 'Souq Waqif')
        self.assertEqual(self.driver().driver_document.count(), 0)   # bad photo dropped
        self.assertIn('not saved', resp.content.decode())

    def test_oversized_photo_on_a_final_submit_blocks_the_submission(self):
        data = self.full_payload(**{
            'doc_Selfie': photo('selfie.jpg'),
            'doc_QID': photo('qid.jpg'),
            'doc_Driving_License': photo('huge.jpg', MAX_UPLOAD_SIZE + 1024),
        })
        resp = self.client.post(self.url, data, follow=True)
        self.assertFalse(core_models.Profile.objects.get(user=self.user).is_driver)
        self.assertIn('exceeds 5MB', resp.content.decode())

    # --- the happy path still works --------------------------------------

    def test_full_submit_with_selfie_and_two_ids_is_accepted(self):
        data = self.full_payload(**{
            'doc_Selfie': photo('selfie.jpg'),
            'doc_QID': photo('qid.jpg'),
            'doc_Driving_License': photo('dl.jpg'),
            'doc_no_QID': '29335632728',
            'geo_lat': '25.2854', 'geo_lng': '51.5310', 'geo_accuracy': '12',
        })
        self.client.post(self.url, data)

        profile = core_models.Profile.objects.get(user=self.user)
        self.assertTrue(profile.is_driver)
        self.assertEqual(profile.verification_status, 'pending')
        self.assertIsNotNone(profile.verification_applied_at)

        driver = self.driver()
        self.assertEqual(docs_with_image(driver.driver_document.all()).count(), 3)
        self.assertEqual(driver.job_type, 'part_time')
        self.assertEqual(
            driver.driver_meta['registration_location']['lat'], 25.2854)

    def test_submit_without_a_selfie_is_refused(self):
        data = self.full_payload(**{
            'doc_QID': photo('qid.jpg'), 'doc_Driving_License': photo('dl.jpg')})
        resp = self.client.post(self.url, data, follow=True)
        self.assertFalse(core_models.Profile.objects.get(user=self.user).is_driver)
        self.assertIn('selfie photo is required', resp.content.decode())


@override_settings(MEDIA_ROOT='/tmp/ezzy-test-media')
class DriverApplyContextTest(TestCase):
    """The page must distinguish 'number on file' from 'photo on file'."""

    @classmethod
    def setUpTestData(cls):
        app = SocialApp.objects.create(
            provider='google', name='Google', client_id='x', secret='y')
        app.sites.add(Site.objects.get_current())

    def setUp(self):
        self.client = Client(HTTP_USER_AGENT=BROWSER_UA)
        self.user = User.objects.create_user(
            username='applicant2', email='a2@example.com', password='pw12345!')
        self.client.force_login(self.user)
        self.url = reverse('core:join_driver')

    def test_number_only_row_prefills_the_number_but_is_not_marked_uploaded(self):
        self.client.post(self.url, {
            'action': 'save', 'first_name': 'Rai', 'phone': '77450564',
            'doc_no_Istimara': 'Q268667',
        })
        resp = self.client.get(self.url)
        items = {d['type']: d for d in resp.context['doc_list']}

        self.assertEqual(items['Istimara']['doc'].document_no, 'Q268667')
        self.assertFalse(items['Istimara']['has_file'])
        self.assertFalse(resp.context['progress']['sec4_complete'])
        self.assertEqual(resp.context['progress']['sec4_ids'], 0)


@override_settings(MEDIA_ROOT='/tmp/ezzy-test-media')
class DriverDocumentPlaceholderTest(TestCase):
    """A number-only row must not read as an uploaded document anywhere."""

    def setUp(self):
        user = User.objects.create_user(username='doc_owner', password='pw12345!')
        profile = core_models.Profile.objects.filter(user=user).first() \
            or core_models.Profile.objects.create(user=user)
        self.driver = fleet_models.Driver.objects.create(
            user=user, profile=profile, driver_id=profile.id,
            driver_status='pending', driver_code='123456', job_type='part_time')

    def test_has_real_file_is_false_for_the_shipped_placeholder(self):
        doc = fleet_models.DriverDocument.objects.create(
            driver=self.driver, document_type='QID', document_no='29335632728')
        self.assertIn('doc_default', doc.document_file.name)   # the field default
        self.assertFalse(doc.has_real_file)

    def test_has_real_file_is_true_for_an_upload(self):
        doc = fleet_models.DriverDocument.objects.create(
            driver=self.driver, document_type='QID', document_no='1',
            document_file=photo('qid.jpg'))
        self.assertTrue(doc.has_real_file)

    def test_staff_application_sections_ignore_number_only_rows(self):
        from workforce.views import _driver_application_sections
        fleet_models.DriverDocument.objects.create(
            driver=self.driver, document_type='Selfie', document_no='')
        fleet_models.DriverDocument.objects.create(
            driver=self.driver, document_type='QID', document_no='29335632728')
        fleet_models.DriverDocument.objects.create(
            driver=self.driver, document_type='Istimara', document_no='Q268667')

        docs_section = [s for s in _driver_application_sections(self.driver)
                        if s['label'] == 'Documents'][0]
        self.assertFalse(docs_section['done'])
        self.assertIn('Selfie missing', docs_section['detail'])
        self.assertIn('0/2 IDs', docs_section['detail'])
