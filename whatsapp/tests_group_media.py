"""
Purpose: Tests that group-chat media is never downloaded automatically, only when someone clicks it in the inbox.
Used by: python manage.py test whatsapp.tests_group_media
Notes: WAHA is mocked and the archive's private storage is swapped for a temp dir; nothing reaches WhatsApp or private_media/.
"""
import json
import shutil
import tempfile
from unittest import mock

from django.contrib.auth.models import User
from django.core.files.base import ContentFile
from django.core.files.storage import FileSystemStorage
from django.http import HttpResponse
from django.test import TestCase

from whatsapp import media_archive
from whatsapp.models import WhatsAppMessage

GROUP = '120363000000000001@g.us'
GROUP_MSG = 'false_120363000000000001@g.us_3EB0AAAABBBB_123456789@lid'
PERSON = '97455551234@c.us'
PERSON_MSG = 'false_97455551234@c.us_3EB0CCCCDDDD'
FRESH = {'url': 'http://localhost:3000/api/files/default/fresh.jpeg', 'mimetype': 'image/jpeg'}


class GroupMediaBase(TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='wa-group-media-test-')
        self.addCleanup(shutil.rmtree, self.tmp, True)
        field = WhatsAppMessage._meta.get_field('media_file')
        saved = field.storage
        field.storage = FileSystemStorage(location=self.tmp)
        self.addCleanup(setattr, field, 'storage', saved)
        self.client.force_login(User.objects.create_user('groupmedia', is_staff=True, is_superuser=True))

    def row(self, waha_id, chat, media_url='http://localhost:3000/api/files/default/old.jpeg',
            media_mime='image/jpeg', **kw):
        return WhatsAppMessage.objects.create(
            waha_message_id=waha_id, session='default', direction='inbound',
            from_number=chat.split('@')[0], message_type='image',
            media_url=media_url, media_mime=media_mime,
            raw_payload={'event': 'message', 'payload': {
                'id': waha_id, 'from': chat, 'hasMedia': True, '_data': {'type': 'image', 'size': 2048}}},
            **kw)


class CronSkipsGroupsTests(GroupMediaBase):
    def test_cron_archives_a_person_chat_but_not_a_group(self):
        self.row(GROUP_MSG, GROUP)
        person = self.row(PERSON_MSG, PERSON)
        with mock.patch('whatsapp.media_archive.archive_message_media', return_value='saved') as archive:
            media_archive.archive_pending_media()
        self.assertEqual([c.args[0] for c in archive.call_args_list], [person])


class GroupBubbleTests(GroupMediaBase):
    def test_group_media_without_a_file_offers_a_download(self):
        from whatsapp.wa_chats_view import _row_to_dict
        row = self.row(GROUP_MSG, GROUP, media_url='')
        media = _row_to_dict(row, GROUP)['media']
        self.assertEqual(media, {'url': '/waha/wa-chats/media/%d/' % row.pk, 'mime': 'image/jpeg',
                                 'stored': False, 'size': 2048})

    def test_a_downloaded_group_file_is_stored(self):
        from whatsapp.wa_chats_view import _row_to_dict
        row = self.row(GROUP_MSG, GROUP)
        row.media_file.save('1.jpeg', ContentFile(b'jpeg'))
        self.assertTrue(_row_to_dict(row, GROUP)['media']['stored'])

    def test_person_chat_without_media_is_unchanged(self):
        from whatsapp.wa_chats_view import _row_to_dict
        row = self.row(PERSON_MSG, PERSON, media_url='', media_mime='')
        self.assertIsNone(_row_to_dict(row, PERSON)['media'])


class DownloadClickTests(GroupMediaBase):
    def test_click_pulls_the_file_from_whatsapp_and_keeps_it(self):
        row = self.row(GROUP_MSG, GROUP)
        upstream = mock.Mock(status_code=200, content=b'fresh-jpeg')
        with mock.patch('whatsapp.wa_chats_view._waha_json',
                        return_value=(200, {'id': GROUP_MSG, 'media': FRESH})) as wj, \
                mock.patch('whatsapp.media_archive.requests.get', return_value=upstream) as get:
            r = self.client.get('/waha/wa-chats/media/%d/' % row.pk, {'fetch': '1'})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(b''.join(r.streaming_content), b'fresh-jpeg')
        self.assertEqual(wj.call_args[0], (f'/api/default/chats/{GROUP}/messages/{GROUP_MSG}',
                                           {'downloadMedia': 'true'}))
        self.assertTrue(get.call_args[0][0].endswith('/api/files/default/fresh.jpeg'))
        row.refresh_from_db()
        self.assertTrue(row.media_file)

    def test_plain_view_never_asks_whatsapp(self):
        row = self.row(GROUP_MSG, GROUP)
        with mock.patch('whatsapp.wa_chats_view._waha_json') as wj, \
                mock.patch('workforce.crm_views._stream_wa_media', return_value=HttpResponse(b'x')):
            self.client.get('/waha/wa-chats/media/%d/' % row.pk)
        wj.assert_not_called()

    def test_whatsapp_no_longer_has_it(self):
        row = self.row(GROUP_MSG, GROUP)
        with mock.patch('whatsapp.wa_chats_view._waha_json', return_value=(404, None)), \
                mock.patch('workforce.crm_views._stream_wa_media', return_value=HttpResponse(status=404)):
            r = self.client.get('/waha/wa-chats/media/%d/' % row.pk, {'fetch': '1'})
        self.assertEqual(r.status_code, 404)
        row.refresh_from_db()
        self.assertFalse(row.media_file)

    def test_malformed_ids_never_reach_waha(self):
        row = self.row('../etc', GROUP)
        with mock.patch('whatsapp.wa_chats_view._waha_json') as wj:
            self.assertEqual(media_archive.fetch_on_demand(row), 'failed')
        wj.assert_not_called()

    def test_live_route_refetches_a_stored_row_without_its_file(self):
        row = self.row(GROUP_MSG, GROUP)
        with mock.patch('whatsapp.media_archive.fetch_on_demand') as fetch, \
                mock.patch('workforce.crm_views._stream_wa_media', return_value=HttpResponse(b'x')):
            r = self.client.get('/waha/wa-chats/media-live/',
                                {'session': 'default', 'chatId': GROUP, 'msgId': GROUP_MSG})
        self.assertEqual(r.status_code, 200)
        fetch.assert_called_once_with(row, GROUP)


class GroupResyncTests(GroupMediaBase):
    def resync(self, chat_id, msgs):
        resp = mock.Mock(status_code=200)
        resp.json.return_value = msgs
        with mock.patch('whatsapp.wa_chats_view.requests.get', return_value=resp) as get, \
                mock.patch('whatsapp.media_archive.archive_message_media') as archive:
            r = self.client.post('/waha/wa-chats/resync/?chatId=' + chat_id)
        self.assertEqual(json.loads(r.content)['ok'], True)
        return get.call_args.kwargs['params'], archive

    def test_group_resync_downloads_no_media(self):
        params, archive = self.resync(GROUP, [{'id': GROUP_MSG, 'from': GROUP, 'hasMedia': True,
                                               'media': FRESH, '_data': {'type': 'image'}}])
        self.assertEqual(params['downloadMedia'], 'false')
        archive.assert_not_called()
        self.assertTrue(WhatsAppMessage.objects.filter(waha_message_id=GROUP_MSG).exists())

    def test_person_resync_still_archives(self):
        params, archive = self.resync(PERSON, [{'id': PERSON_MSG, 'from': PERSON, 'hasMedia': True,
                                                'media': FRESH, '_data': {'type': 'image'}}])
        self.assertEqual(params['downloadMedia'], 'true')
        archive.assert_called_once()
