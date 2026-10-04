"""
Purpose: Tests for the inbox write actions (attachments, voice, reactions, forward, edit/delete, number check, archive/unread, quote-reply).
Used by: python manage.py test whatsapp.tests_inbox_actions
Notes: WAHA is mocked; nothing here can reach WhatsApp. Pins the payloads we send WAHA and the refusals (bad ids, someone else's message, hidden chats).
"""
import json
from unittest import mock

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.utils import timezone

from whatsapp.models import WhatsAppMessage, WhatsAppReaction

CHAT = '97455551234@c.us'
OURS = 'true_97455551234@c.us_3EB0AAAABBBBCCCC'
THEIRS = 'false_97455551234@c.us_3EB0DDDDEEEEFFFF'


class FakeWaha:
    """Records every WAHA call; answers 200 (or `status`) with `body`."""

    def __init__(self, status=200, body=None):
        self.calls = []
        self.status = status
        self.body = body if body is not None else {}

    def __call__(self, method, url, json=None, headers=None, timeout=None, params=None):
        self.calls.append({'method': method, 'url': url, 'json': json, 'params': params})
        resp = mock.Mock()
        resp.status_code = self.status
        resp.ok = 200 <= self.status < 300
        resp.json.return_value = self.body
        resp.text = ''
        return resp


class InboxActionsBase(TestCase):
    def setUp(self):
        self.client.force_login(User.objects.create_user('inboxactions', is_staff=True, is_superuser=True))

    def post_json(self, url, body, waha):
        with mock.patch('whatsapp.wa_chats_actions.requests.request', side_effect=waha):
            return self.client.post(url, json.dumps(body), content_type='application/json')


class SendMediaTests(InboxActionsBase):
    URL = '/waha/wa-chats/send-media/'

    def send(self, upload, waha, **fields):
        data = {'to': CHAT, 'session': 'default', 'file': upload, **fields}
        with mock.patch('whatsapp.wa_chats_actions.requests.request', side_effect=waha):
            return self.client.post(self.URL, data)

    def test_photo_goes_as_image_with_caption_and_reply(self):
        waha = FakeWaha()
        r = self.send(SimpleUploadedFile('a.jpg', b'\xff\xd8jpeg', content_type='image/jpeg'), waha,
                      caption='Your parcel', reply_to=THEIRS)
        self.assertEqual(r.status_code, 200, r.content)
        call = waha.calls[0]
        self.assertTrue(call['url'].endswith('/api/sendImage'))
        self.assertEqual(call['json']['caption'], 'Your parcel')
        self.assertEqual(call['json']['reply_to'], THEIRS)
        self.assertEqual(call['json']['file']['mimetype'], 'image/jpeg')
        self.assertEqual(call['json']['file']['data'], '/9hqcGVn')  # base64 of the bytes

    def test_pdf_goes_as_file(self):
        waha = FakeWaha()
        r = self.send(SimpleUploadedFile('inv.pdf', b'%PDF', content_type='application/pdf'), waha)
        self.assertEqual(r.status_code, 200, r.content)
        self.assertTrue(waha.calls[0]['url'].endswith('/api/sendFile'))

    def test_webp_image_goes_as_file_not_photo(self):
        waha = FakeWaha()
        self.send(SimpleUploadedFile('s.webp', b'RIFF', content_type='image/webp'), waha)
        self.assertTrue(waha.calls[0]['url'].endswith('/api/sendFile'))

    def test_mp4_is_sent_unconverted_other_video_is_converted(self):
        waha = FakeWaha()
        self.send(SimpleUploadedFile('v.mp4', b'mp4', content_type='video/mp4'), waha)
        self.send(SimpleUploadedFile('v.mov', b'mov', content_type='video/quicktime'), waha)
        self.assertTrue(waha.calls[0]['url'].endswith('/api/sendVideo'))
        self.assertFalse(waha.calls[0]['json']['convert'])
        self.assertTrue(waha.calls[1]['json']['convert'])

    def test_voice_note_is_converted(self):
        waha = FakeWaha()
        r = self.send(SimpleUploadedFile('voice-note.webm', b'webm', content_type='audio/webm'), waha, voice='1')
        self.assertEqual(r.status_code, 200, r.content)
        self.assertTrue(waha.calls[0]['url'].endswith('/api/sendVoice'))
        self.assertTrue(waha.calls[0]['json']['convert'])

    def test_bad_reply_id_and_bad_chat_are_refused_before_waha(self):
        waha = FakeWaha()
        r1 = self.send(SimpleUploadedFile('a.jpg', b'x', content_type='image/jpeg'), waha, reply_to='nope')
        r2 = self.send(SimpleUploadedFile('a.jpg', b'x', content_type='image/jpeg'), waha, to='not a chat')
        self.assertEqual((r1.status_code, r2.status_code), (400, 400))
        self.assertEqual(waha.calls, [])

    def test_waha_failure_is_reported(self):
        waha = FakeWaha(status=500, body={'message': 'boom'})
        r = self.send(SimpleUploadedFile('a.jpg', b'x', content_type='image/jpeg'), waha)
        self.assertEqual(r.status_code, 502)
        self.assertEqual(r.json()['error'], 'boom')

    def test_hidden_chat_is_refused(self):
        waha = FakeWaha()
        with mock.patch('whatsapp.wa_chats_actions.label_access.chat_hidden', return_value=True):
            r = self.send(SimpleUploadedFile('a.jpg', b'x', content_type='image/jpeg'), waha)
        self.assertEqual(r.status_code, 403)
        self.assertEqual(waha.calls, [])


class ReactionTests(InboxActionsBase):
    URL = '/waha/wa-chats/react/'

    def test_react_then_remove(self):
        waha = FakeWaha()
        r = self.post_json(self.URL, {'session': 'default', 'messageId': THEIRS, 'emoji': '\U0001F44D'}, waha)
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(waha.calls[0]['json'], {'messageId': THEIRS, 'reaction': '\U0001F44D', 'session': 'default'})
        self.assertEqual(WhatsAppReaction.objects.get(message_id=THEIRS, sender='me').emoji, '\U0001F44D')
        self.post_json(self.URL, {'session': 'default', 'messageId': THEIRS, 'emoji': ''}, waha)
        self.assertEqual(WhatsAppReaction.objects.get(message_id=THEIRS, sender='me').emoji, '')

    def test_text_is_not_an_emoji(self):
        r = self.post_json(self.URL, {'session': 'default', 'messageId': THEIRS, 'emoji': 'ok'}, FakeWaha())
        self.assertEqual(r.status_code, 400)

    def test_reactions_ride_on_the_message_list(self):
        from whatsapp.wa_chats_view import _attach_reactions
        WhatsAppReaction.objects.create(session='default', message_id=THEIRS, sender='me', emoji='❤️')
        WhatsAppReaction.objects.create(session='default', message_id=THEIRS, sender='97455551234', emoji='\U0001F64F')
        WhatsAppReaction.objects.create(session='default', message_id=THEIRS, sender='97400000000', emoji='')
        msgs = [{'waha_id': THEIRS}, {'waha_id': OURS}]
        _attach_reactions(msgs, 'default')
        self.assertEqual(sorted((r['emoji'], r['me']) for r in msgs[0]['reactions']),
                         [('❤️', True), ('\U0001F64F', False)])
        self.assertEqual(msgs[1]['reactions'], [])

    def test_webhook_reaction_event_is_stored(self):
        from whatsapp.waha_views import _store_reaction
        _store_reaction({'event': 'message.reaction', 'session': 'default', 'payload': {
            'from': '97455551234@c.us', 'fromMe': False,
            'reaction': {'text': '\U0001F602', 'messageId': OURS}}})
        self.assertEqual(WhatsAppReaction.objects.get(message_id=OURS).sender, '97455551234')


class ForwardTests(InboxActionsBase):
    URL = '/waha/wa-chats/forward/'

    def test_forwards_to_each_chat(self):
        waha = FakeWaha()
        r = self.post_json(self.URL, {'session': 'default', 'messageId': THEIRS,
                                      'chatIds': ['97466660000@c.us', '120363000000@g.us']}, waha)
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual([c['json']['chatId'] for c in waha.calls], ['97466660000@c.us', '120363000000@g.us'])
        self.assertTrue(all(c['json']['messageId'] == THEIRS for c in waha.calls))

    def test_more_than_five_is_refused(self):
        r = self.post_json(self.URL, {'session': 'default', 'messageId': THEIRS,
                                      'chatIds': ['9740000000%d@c.us' % i for i in range(6)]}, FakeWaha())
        self.assertEqual(r.status_code, 400)

    def test_hidden_destination_is_refused(self):
        waha = FakeWaha()
        with mock.patch('whatsapp.wa_chats_actions.label_access.chat_hidden',
                        side_effect=lambda u, s, chat: chat == '97466660000@c.us'):
            r = self.post_json(self.URL, {'session': 'default', 'messageId': THEIRS,
                                          'chatIds': ['97466660000@c.us']}, waha)
        self.assertEqual(r.status_code, 403)
        self.assertEqual(waha.calls, [])


class EditDeleteTests(InboxActionsBase):
    def stored(self, waha_id=OURS):
        return WhatsAppMessage.objects.create(
            session='default', waha_message_id=waha_id, direction='outbound', to_number='97455551234',
            body='old text', message_type='text', received_at=timezone.now(),
            raw_payload={'payload': {'id': waha_id, 'body': 'old text', '_data': {'type': 'chat'}}})

    def test_edit_updates_whatsapp_and_our_copy(self):
        row = self.stored()
        waha = FakeWaha()
        r = self.post_json('/waha/wa-chats/edit/', {'session': 'default', 'chatId': CHAT,
                                                    'messageId': OURS, 'text': 'new text'}, waha)
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(waha.calls[0]['method'], 'PUT')
        self.assertTrue(waha.calls[0]['url'].endswith(f'/api/default/chats/{CHAT}/messages/{OURS}'))
        row.refresh_from_db()
        self.assertEqual(row.body, 'new text')
        from whatsapp.wa_chats_view import _row_to_dict
        self.assertTrue(_row_to_dict(row, CHAT)['edited'])

    def test_delete_shows_as_deleted(self):
        row = self.stored()
        waha = FakeWaha()
        r = self.post_json('/waha/wa-chats/delete/', {'session': 'default', 'chatId': CHAT, 'messageId': OURS}, waha)
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(waha.calls[0]['method'], 'DELETE')
        row.refresh_from_db()
        from whatsapp.wa_chats_view import _row_to_dict
        d = _row_to_dict(row, CHAT)
        self.assertEqual((d['body'], d['notice'], d['media']), ('', 'This message was deleted', None))

    def test_someone_elses_message_cannot_be_changed(self):
        waha = FakeWaha()
        r1 = self.post_json('/waha/wa-chats/edit/', {'session': 'default', 'chatId': CHAT,
                                                     'messageId': THEIRS, 'text': 'x'}, waha)
        r2 = self.post_json('/waha/wa-chats/delete/', {'session': 'default', 'chatId': CHAT,
                                                       'messageId': THEIRS}, waha)
        self.assertEqual((r1.status_code, r2.status_code), (400, 400))
        self.assertEqual(waha.calls, [])


class NumberCheckTests(InboxActionsBase):
    URL = '/waha/wa-chats/check-number/'

    def get(self, phone, waha):
        with mock.patch('whatsapp.wa_chats_actions.requests.get', side_effect=lambda url, **kw: waha('GET', url, **kw)):
            return self.client.get(self.URL, {'phone': phone, 'session': 'default'})

    def test_registered_number_returns_its_chat(self):
        waha = FakeWaha(body={'numberExists': True, 'chatId': '243498892673056@lid'})
        r = self.get('+974 5555 1234', waha)
        self.assertEqual(r.json(), {'ok': True, 'exists': True, 'chatId': '243498892673056@lid'})
        self.assertEqual(waha.calls[0]['params']['phone'], '97455551234')

    def test_unregistered_number(self):
        r = self.get('97455551234', FakeWaha(body={'numberExists': False}))
        self.assertEqual(r.json()['exists'], False)

    def test_short_input_never_reaches_waha(self):
        waha = FakeWaha()
        self.assertEqual(self.get('1234', waha).status_code, 400)
        self.assertEqual(waha.calls, [])


class ChatActionTests(InboxActionsBase):
    URL = '/waha/wa-chats/chat-action/'

    def test_each_action_hits_its_route(self):
        for action in ('archive', 'unarchive', 'unread'):
            waha = FakeWaha()
            r = self.post_json(self.URL, {'session': 'default', 'chatId': CHAT, 'action': action}, waha)
            self.assertEqual(r.status_code, 200, r.content)
            self.assertTrue(waha.calls[0]['url'].endswith(f'/api/default/chats/{CHAT}/{action}'))

    def test_unknown_action_and_bad_session_are_refused(self):
        waha = FakeWaha()
        r1 = self.post_json(self.URL, {'session': 'default', 'chatId': CHAT, 'action': 'delete'}, waha)
        r2 = self.post_json(self.URL, {'session': '../x', 'chatId': CHAT, 'action': 'archive'}, waha)
        self.assertEqual((r1.status_code, r2.status_code), (400, 400))
        self.assertEqual(waha.calls, [])


class AccessTests(TestCase):
    def test_non_staff_get_nothing(self):
        self.client.force_login(User.objects.create_user('plainuser'))
        for url in ('/waha/wa-chats/react/', '/waha/wa-chats/forward/', '/waha/wa-chats/chat-action/',
                    '/waha/wa-chats/edit/', '/waha/wa-chats/delete/', '/waha/wa-chats/send-media/'):
            r = self.client.post(url, '{}', content_type='application/json')
            self.assertEqual(r.status_code, 403, url)


class QuoteReplyTests(InboxActionsBase):
    def test_text_reply_passes_reply_to(self):
        waha = FakeWaha()
        with mock.patch('whatsapp.wa_chats_view.requests.post', side_effect=lambda url, **kw: waha('POST', url, **kw)):
            r = self.client.post('/waha/wa-chats/send/', json.dumps(
                {'to': CHAT, 'text': 'yes', 'session': 'default', 'reply_to': THEIRS}), content_type='application/json')
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(waha.calls[0]['json']['reply_to'], THEIRS)

    def test_quoted_media_never_shows_base64(self):
        from whatsapp.wa_chats_view import _quoted
        q = _quoted({'replyTo': {'id': 'ABC', 'body': '/9j/4AAQSkZJRgABAQ...', '_data': {'type': 'image'}}})
        self.assertEqual(q, {'id': 'ABC', 'body': 'Photo'})


def _image_bytes(fmt, mode='RGB'):
    import io
    from PIL import Image
    buf = io.BytesIO()
    Image.new(mode, (40, 30), (200, 10, 10, 128) if mode == 'RGBA' else (200, 10, 10)).save(buf, fmt)
    return buf.getvalue()


class PhotoConversionTests(InboxActionsBase):
    """A WebP saved from a website went out as a document (2026-10-03)."""
    URL = '/waha/wa-chats/send-media/'

    def send(self, upload, waha):
        with mock.patch('whatsapp.wa_chats_actions.requests.request', side_effect=waha):
            return self.client.post(self.URL, {'to': CHAT, 'session': 'default', 'file': upload})

    def test_webp_goes_as_a_jpeg_photo(self):
        waha = FakeWaha()
        r = self.send(SimpleUploadedFile('abaya.webp', _image_bytes('WEBP', 'RGBA'), content_type='image/webp'), waha)
        self.assertEqual(r.status_code, 200, r.content)
        call = waha.calls[0]
        self.assertTrue(call['url'].endswith('/api/sendImage'))
        self.assertEqual((call['json']['file']['mimetype'], call['json']['file']['filename']), ('image/jpeg', 'abaya.jpg'))
        import base64
        self.assertTrue(base64.b64decode(call['json']['file']['data']).startswith(b'\xff\xd8'))

    def test_gif_and_bmp_go_as_photos(self):
        for name, fmt, ctype in (('a.gif', 'GIF', 'image/gif'), ('a.bmp', 'BMP', 'image/bmp')):
            waha = FakeWaha()
            self.send(SimpleUploadedFile(name, _image_bytes(fmt), content_type=ctype), waha)
            self.assertTrue(waha.calls[0]['url'].endswith('/api/sendImage'), name)

    def test_a_broken_image_falls_back_to_a_document(self):
        waha = FakeWaha()
        self.send(SimpleUploadedFile('x.webp', b'not really an image', content_type='image/webp'), waha)
        self.assertTrue(waha.calls[0]['url'].endswith('/api/sendFile'))

    def test_svg_is_never_a_photo(self):
        waha = FakeWaha()
        self.send(SimpleUploadedFile('logo.svg', b'<svg/>', content_type='image/svg+xml'), waha)
        self.assertTrue(waha.calls[0]['url'].endswith('/api/sendFile'))


class LiveMediaTests(InboxActionsBase):
    """Our own fresh sends are not stored by the webhook, so their bubble was blank."""

    def test_live_media_message_gets_a_streaming_url_and_filename(self):
        from whatsapp.wa_chats_view import _live_to_dict
        d = _live_to_dict({'id': OURS, 'fromMe': True, 'hasMedia': True, 'body': '',
                           'media': {'url': None, 'mimetype': 'image/webp'},
                           '_data': {'type': 'document', 'filename': 'abaya.webp'}}, CHAT, 'default')
        self.assertTrue(d['media']['url'].startswith('/waha/wa-chats/media-live/?'))
        self.assertIn('msgId=' + OURS.replace('@', '%40'), d['media']['url'])
        self.assertEqual(d['filename'], 'abaya.webp')

    def test_first_view_stores_the_message_then_streams_it(self):
        from django.http import HttpResponse
        live = {'id': OURS, 'fromMe': True, 'from': '97466451589@c.us', 'to': CHAT, 'timestamp': 1791007281,
                'hasMedia': True, 'body': '', 'media': {'url': 'http://127.0.0.1:3000/api/files/default/x.webp',
                                                        'mimetype': 'image/webp'},
                '_data': {'type': 'document', 'filename': 'abaya.webp'}}
        with mock.patch('whatsapp.wa_chats_view._waha_json', return_value=(200, live)) as wj, \
                mock.patch('whatsapp.media_archive.archive_message_media'), \
                mock.patch('workforce.crm_views._stream_wa_media', return_value=HttpResponse(b'img')) as stream:
            r = self.client.get('/waha/wa-chats/media-live/', {'session': 'default', 'chatId': CHAT, 'msgId': OURS})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(wj.call_args[0][1], {'downloadMedia': 'true'})
        row = WhatsAppMessage.objects.get(session='default', waha_message_id=OURS)
        self.assertEqual((row.direction, row.media_mime), ('outbound', 'image/webp'))
        self.assertEqual(stream.call_args[0][0], row)

    def test_bad_ids_are_404_before_waha(self):
        with mock.patch('whatsapp.wa_chats_view._waha_json') as wj:
            r = self.client.get('/waha/wa-chats/media-live/', {'session': 'default', 'chatId': CHAT, 'msgId': '../x'})
        self.assertEqual(r.status_code, 404)
        wj.assert_not_called()
