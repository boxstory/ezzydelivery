"""
Purpose: Tests for the inbox's driver documents section and "Save to driver file" (a chat photo filed onto the linked driver's documents).
Used by: python manage.py test whatsapp.tests_driver_docs
Notes: Files go to a temp dir — MEDIA_ROOT is overridden and the message archive's private storage is swapped for the test.
"""
import io
import json
import shutil
import tempfile

from django.contrib.auth.models import User
from django.core.cache import cache
from django.core.files.base import ContentFile
from django.core.files.storage import FileSystemStorage
from django.test import TestCase, override_settings
from PIL import Image

from crm.models import Lead, LeadActivity
from fleet.models import Driver, DriverDocument
from whatsapp import chat_panel
from whatsapp.models import WhatsAppMessage

TMP = tempfile.mkdtemp(prefix='wa-docs-test-')


def _jpeg():
    buf = io.BytesIO()
    Image.new('RGB', (8, 8), (200, 30, 30)).save(buf, 'JPEG')
    return buf.getvalue()


@override_settings(MEDIA_ROOT=TMP)
class DriverDocsFromChatTests(TestCase):
    PHONE = '97455667788'

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(TMP, ignore_errors=True)

    def setUp(self):
        cache.clear()
        field = WhatsAppMessage._meta.get_field('media_file')
        saved = field.storage
        field.storage = FileSystemStorage(location=TMP + '/private')
        self.addCleanup(setattr, field, 'storage', saved)

        self.staff = User.objects.create_user('docdesk', is_staff=True, is_superuser=True)
        self.client.force_login(self.staff)
        applicant = User.objects.create_user('applicant9101')
        self.driver = Driver.objects.create(
            driver_id=9101, user=applicant, driver_phone='55667788', driver_whatsapp='55667788',
            driver_languages='en', driver_status='pending')
        self.lead = Lead.objects.create(
            category=Lead.CATEGORY_DRIVER, source=Lead.SOURCE_MANUAL,
            phone=self.PHONE, contact_name='Applicant', driver=self.driver)
        self.msg = WhatsAppMessage.objects.create(
            waha_message_id='doc-photo-1', session='default', direction='inbound',
            from_number=self.PHONE, to_number='97466451589', message_type='image',
            media_mime='image/jpeg')
        self.msg.media_file.save('1.jpg', ContentFile(_jpeg()))
        self.chat = f'{self.PHONE}@c.us'

    def _save(self, **over):
        body = {'session': 'default', 'chatId': self.chat, 'lead_id': self.lead.pk,
                'msg_id': self.msg.pk, 'doc_type': 'Selfie', 'side': 'front'}
        body.update(over)
        return self.client.post('/waha/wa-chats/save-doc/', json.dumps(body),
                                content_type='application/json',
                                HTTP_HOST='ezzydelivery.qa', secure=True)

    def test_missing_documents_count_against_the_application_rule(self):
        docs = chat_panel.driver_documents(self.driver)
        self.assertEqual([i['type'] for i in docs['items']],
                         ['Selfie', 'QID', 'Passport', 'Driving License', 'Istimara'])
        self.assertFalse(docs['complete'])
        self.assertEqual(docs['ids_have'], 0)
        # A row holding only the shipped placeholder image is not a document.
        DriverDocument.objects.create(driver=self.driver, document_type='QID', document_no='123')
        self.assertEqual(chat_panel.driver_documents(self.driver)['ids_have'], 0)

    def test_info_carries_the_documents_for_a_driver_lead(self):
        r = self.client.get('/waha/wa-chats/', {'info': 1, 'chatId': self.chat, 'session': 'default'},
                            HTTP_HOST='ezzydelivery.qa', secure=True)
        j = r.json()
        self.assertTrue(j['can_save_docs'])
        self.assertEqual(j['leads'][0]['docs']['items'][0]['type'], 'Selfie')

    def test_documents_carry_the_image_check_for_the_viewer(self):
        """The media viewer's document panel: same facts as the CRM popup, and the
        id + edit base its Submit / verify post to."""
        import datetime

        from django.utils import timezone

        doc = DriverDocument.objects.create(driver=self.driver, document_type='QID', document_no='30701200184')
        DriverDocument.objects.filter(pk=doc.pk).update(
            ai_status=DriverDocument.AI_MISMATCH, ai_document_no='30701200184',
            ai_expiry_date=datetime.date(2029, 7, 16), ai_checked_at=timezone.now(),
            ai_note='Expiry not entered (image shows 16 Jul 2029)')
        docs = chat_panel.driver_documents(self.driver)
        qid = docs['items'][1]
        self.assertEqual(qid['id'], doc.pk)
        self.assertEqual(qid['check'], 'Does not match the image')
        self.assertEqual(qid['check_note'], 'Expiry not entered (image shows 16 Jul 2029)')
        self.assertEqual((qid['ai_no'], qid['ai_expiry'], qid['ai_expiry_iso']),
                         ('30701200184', '16 Jul 2029', '2029-07-16'))
        self.assertFalse(qid['verified'])
        self.assertEqual(docs['doc_edit_base'], f'/workforce/drivers/{self.driver.pk}/document/')
        self.assertNotIn('id', docs['items'][2])   # no Passport row: nothing to edit

    def test_marketing_may_edit_and_verify_from_the_viewer(self):
        from core.models import Profile

        mkt = User.objects.create_user('inboxmkt', is_staff=True)
        Profile.objects.create(user=mkt, is_staff=True, dept_marketing=True)
        from whatsapp.models import InboxSessionAccess
        InboxSessionAccess.objects.create(user=mkt, session='default')  # inbox number gate
        self.client.force_login(mkt)
        j = self.client.get('/waha/wa-chats/', {'info': 1, 'chatId': self.chat, 'session': 'default'},
                            HTTP_HOST='ezzydelivery.qa', secure=True).json()
        self.assertTrue(j['can_save_docs'])
        self.assertTrue(j['can_verify_docs'])

    def _info(self):
        return self.client.get('/waha/wa-chats/', {'info': 1, 'chatId': self.chat, 'session': 'default'},
                               HTTP_HOST='ezzydelivery.qa', secure=True).json()

    def test_open_driver_lead_offers_the_missing_items_reminder(self):
        """"Send reminder" on the documents card: the CRM composer's own reminder body."""
        reminder = self._info()['leads'][0]['reminder']
        self.assertRegex(reminder['label'], r'^Reminder · \d+ missing$')
        self.assertIn('still missing', reminder['body'])
        self.assertIn('https://ezzydelivery.qa/join_us/driver/', reminder['body'])

    def test_closed_driver_lead_is_not_chased(self):
        from crm import services as crm_services

        closed = crm_services.closed_stage_keys(self.lead.category)
        self.assertTrue(closed)
        Lead.objects.filter(pk=self.lead.pk).update(stage=closed[0])
        self.assertIsNone(self._info()['leads'][0]['reminder'])

    def test_saving_a_chat_photo_fills_the_slot(self):
        r = self._save()
        self.assertEqual(r.status_code, 200, r.content)
        self.assertTrue(r.json()['docs']['selfie_ok'])
        doc = DriverDocument.objects.get(driver=self.driver, document_type='Selfie')
        self.assertTrue(doc.has_real_file)
        self.assertTrue(LeadActivity.objects.filter(lead=self.lead, body__contains='Saved driver Selfie').exists())

    def test_back_side_keeps_the_front_and_number(self):
        self._save(doc_type='QID', side='front')
        doc = DriverDocument.objects.get(driver=self.driver, document_type='QID')
        doc.document_no = '28400000000'
        doc.save()
        front = doc.document_file.name
        self.assertEqual(self._save(doc_type='QID', side='back').status_code, 200)
        doc.refresh_from_db()
        self.assertEqual(doc.document_file.name, front)
        self.assertEqual(doc.document_no, '28400000000')
        self.assertTrue(doc.document_file_back.name)
        self.assertEqual(DriverDocument.objects.filter(driver=self.driver, document_type='QID').count(), 1)

    def test_photo_from_another_chat_is_refused(self):
        other = WhatsAppMessage.objects.create(
            waha_message_id='doc-photo-2', session='default', direction='inbound',
            from_number='97411112222', to_number='97466451589', message_type='image')
        self.assertEqual(self._save(msg_id=other.pk).status_code, 404)

    def test_lead_not_connected_to_the_chat_is_refused(self):
        self.lead.phone = '97499990000'
        self.lead.save(update_fields=['phone'])
        self.assertEqual(self._save().status_code, 400)
        self.assertFalse(DriverDocument.objects.filter(driver=self.driver).exists())

    def test_non_image_is_refused(self):
        self.msg.media_file.save('1.jpg', ContentFile(b'not an image'))
        r = self._save()
        self.assertEqual(r.status_code, 400)
        self.assertIn('not a readable image', r.json()['error'])

    def test_needs_document_rights(self):
        plain = User.objects.create_user('nobody', is_staff=False)
        self.client.force_login(plain)
        self.assertEqual(self._save().status_code, 403)
