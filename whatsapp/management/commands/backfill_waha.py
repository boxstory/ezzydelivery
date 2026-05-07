import logging
import random
import time
from datetime import datetime, timedelta, timezone, time as dt_time

import requests
from django.conf import settings
from django.core.cache import cache
from django.core.management.base import BaseCommand
from django.db import IntegrityError
from django.utils import timezone as dj_timezone

from whatsapp.models import WhatsAppMessage

logger = logging.getLogger(__name__)


# WAHA exposes message-type via two slots; _data.type is the canonical one,
# top-level type is a fallback for older payloads.
_TYPE_MAP = {
    'chat': 'text',
    'image': 'image',
    'ptt': 'audio',
    'audio': 'audio',
    'video': 'video',
    'document': 'document',
    'location': 'location',
    'sticker': 'sticker',
    'vcard': 'contact',
    'contact_card': 'contact',
}

_QATAR_TZ = timezone(timedelta(hours=3))


def _strip_jid(s):
    if not s:
        return ''
    return s.replace('@c.us', '').replace('@s.whatsapp.net', '')


def _map_type(m):
    raw = (m.get('_data') or {}).get('type') or m.get('type') or ''
    return _TYPE_MAP.get(raw, 'unknown')


def waha_get(path, params=None, timeout=30):
    url = f'{settings.WAHA_BASE_URL}{path}'
    headers = {'X-Api-Key': settings.WAHA_API_KEY}
    r = requests.get(url, params=params, headers=headers, timeout=timeout)
    r.raise_for_status()
    return r.json()


def compute_qatar_today_start_ts():
    # Qatar runs UTC+3 year-round (no DST), so a fixed offset is correct.
    now_qatar = datetime.now(tz=_QATAR_TZ)
    start = datetime.combine(now_qatar.date(), dt_time(0, 0, 0), tzinfo=_QATAR_TZ)
    return int(start.timestamp())


def upsert_message(m, session, chat_id):
    waha_id = m['id']
    direction = 'outbound' if m.get('fromMe') is True else 'inbound'
    from_number = _strip_jid(m.get('from'))
    to_number = _strip_jid(m.get('to')) or _strip_jid(chat_id)
    body = m.get('body') or ''
    message_type = _map_type(m)

    media = m.get('media') or {}
    media_url = media.get('url') or ''
    media_mime = media.get('mimetype') or ''

    ts = m.get('timestamp')
    if ts:
        received_at = datetime.fromtimestamp(int(ts), tz=timezone.utc)
    else:
        received_at = dj_timezone.now()

    try:
        obj = WhatsAppMessage.objects.get(waha_message_id=waha_id)
    except WhatsAppMessage.DoesNotExist:
        try:
            obj = WhatsAppMessage.objects.create(
                waha_message_id=waha_id,
                session=session,
                direction=direction,
                from_number=from_number,
                to_number=to_number,
                body=body,
                message_type=message_type,
                media_url=media_url,
                media_mime=media_mime,
                status='archived',
                raw_payload=m,
                received_at=received_at,
            )
            return obj, True
        except IntegrityError:
            # Race: webhook inserted same row between get() and create().
            obj = WhatsAppMessage.objects.get(waha_message_id=waha_id)

    # Update path: never clobber populated fields, only fill blanks.
    dirty = False

    if not obj.media_url and media_url:
        obj.media_url = media_url
        dirty = True
    if not obj.media_mime and media_mime:
        obj.media_mime = media_mime
        dirty = True

    # Normalize wrong type if existing was defaulted to 'text' but payload says otherwise.
    if obj.message_type == 'text' and message_type not in ('text', 'unknown'):
        obj.message_type = message_type
        dirty = True

    # Refresh raw_payload only if missing or lacking media we now have.
    existing_raw = obj.raw_payload or {}
    if not existing_raw or (not existing_raw.get('media') and m.get('media')):
        obj.raw_payload = m
        dirty = True

    if dirty:
        obj.save(update_fields=[
            'media_url', 'media_mime', 'message_type', 'raw_payload', 'updated_at',
        ])
    return obj, False


class Command(BaseCommand):
    help = 'Backfill historical WhatsApp messages from WAHA'

    def add_arguments(self, parser):
        parser.add_argument('--days', type=int, default=120)
        parser.add_argument('--limit-per-chat', type=int, default=100)
        parser.add_argument('--max-chats', type=int, default=200)
        parser.add_argument('--min-sleep', type=int, default=3)
        parser.add_argument('--max-sleep', type=int, default=8)
        parser.add_argument('--skip-today', action='store_true')
        parser.add_argument('--force', action='store_true')
        parser.add_argument('--session', type=str, default=settings.WAHA_DEFAULT_SESSION)

    def handle(self, *args, **opts):
        session = opts['session']
        days = opts['days']
        cutoff_ts = int((dj_timezone.now() - timedelta(days=days)).timestamp())
        today_start_ts = compute_qatar_today_start_ts()

        try:
            chats = waha_get(f'/api/{session}/chats', params={'limit': 200})
        except requests.exceptions.RequestException as e:
            self.stderr.write(self.style.ERROR(f'failed to list chats: {e}'))
            return

        chats = chats[: opts['max_chats']]

        total_msgs = 0
        total_inserted = 0
        total_skipped_chats = 0

        for chat in chats:
            chat_id = chat.get('id')
            if not chat_id:
                continue

            cache_key = f'waha_backfill_done:{chat_id}'
            if not opts['force'] and cache.get(cache_key):
                total_skipped_chats += 1
                continue

            try:
                msgs = waha_get(
                    f'/api/{session}/chats/{chat_id}/messages',
                    params={'limit': opts['limit_per_chat'], 'downloadMedia': 'true'},
                    timeout=180,
                )
            except requests.exceptions.RequestException as e:
                self.stderr.write(self.style.WARNING(f'chat {chat_id}: fetch failed: {e}'))
                continue

            inserted = 0
            for m in msgs:
                ts = int(m.get('timestamp') or 0)
                if ts < cutoff_ts:
                    continue
                if opts['skip_today'] and ts >= today_start_ts:
                    continue
                waha_id = m.get('id')
                if not waha_id:
                    continue
                try:
                    _obj, created = upsert_message(m, session, chat_id)
                except Exception as e:
                    # Don't let a single bad payload abort the whole backfill.
                    logger.exception('upsert failed for %s: %s', waha_id, e)
                    continue
                total_msgs += 1
                if created:
                    inserted += 1

            cache.set(cache_key, '1', timeout=86400)
            self.stdout.write(f'chat {chat_id}: {inserted} new / {len(msgs)} total')
            total_inserted += inserted
            time.sleep(random.uniform(opts['min_sleep'], opts['max_sleep']))

        self.stdout.write(self.style.SUCCESS(
            f'done. chats={len(chats)} skipped_cached={total_skipped_chats} '
            f'msgs_seen={total_msgs} inserted={total_inserted}'
        ))
