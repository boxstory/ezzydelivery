# Purpose: Download WAHA media files into Django storage before WAHA purges them (~3 min lifetime).
# Used by: whatsapp/management/commands/archive_wa_media.py (per-minute cron), wa_chats resync, inbox media clicks.
# Notes: Idempotent per message; rows older than the retry window are skipped. Group chats are never archived
#        by the cron — only when someone clicks the file in the inbox (fetch_on_demand).

import logging
import mimetypes
import re
from datetime import timedelta

import requests

from django.conf import settings
from django.core.files.base import ContentFile
from django.utils import timezone

logger = logging.getLogger(__name__)

# How long after a row is stored/updated we keep retrying the download.
# WAHA's own copy lives ~3 minutes; past this window the file is gone.
RETRY_WINDOW_MINUTES = 15


def archive_message_media(msg):
    """Fetch one message's WAHA media into msg.media_file.

    Returns 'saved', 'skipped' (no media / already archived), or 'failed'."""
    from whatsapp.wa_chats_view import _extract_media, _waha_base

    if msg.media_file:
        return 'skipped'
    media = _extract_media(msg) or {}
    url = media.get('url') or ''
    if not url:
        return 'skipped'
    if url.startswith('/waha/'):
        url = _waha_base() + url[len('/waha'):]

    try:
        resp = requests.get(
            url,
            headers={'X-Api-Key': getattr(settings, 'WAHA_API_KEY', '') or ''},
            timeout=60,
        )
    except requests.exceptions.RequestException as exc:
        logger.warning('archive media: fetch error for msg %s: %s', msg.pk, exc)
        return 'failed'
    if resp.status_code != 200 or not resp.content:
        logger.info('archive media: HTTP %s for msg %s', resp.status_code, msg.pk)
        return 'failed'

    # The fetch above reads the whole body into memory. A sender controls how big
    # their attachment is, so cap it rather than letting one message balloon a
    # worker. 25 MB matches media_validators() on the field.
    _MAX_MEDIA_BYTES = 25 * 1024 * 1024
    if len(resp.content) > _MAX_MEDIA_BYTES:
        logger.warning('archive media: msg %s is %s bytes, over the %s cap — skipped',
                       msg.pk, len(resp.content), _MAX_MEDIA_BYTES)
        return 'failed'

    mime = (media.get('mime') or msg.media_mime or '').split(';')[0].strip()
    ext = mimetypes.guess_extension(mime) or ''
    if ext == '.jpe':
        ext = '.jpg'
    tail = url.rsplit('/', 1)[-1]
    if not ext and '.' in tail:
        # Last-resort extension from the payload URL — strip it to word chars so a
        # crafted URL cannot choose a path segment or a double extension.
        ext = '.' + re.sub(r'[^A-Za-z0-9]', '', tail.rsplit('.', 1)[-1])[:8]
    msg.media_file.save(f'{msg.pk}{ext}', ContentFile(resp.content), save=False)
    if mime and not msg.media_mime:
        msg.media_mime = mime
    msg.save(update_fields=['media_file', 'media_mime', 'updated_at'])
    logger.info('archive media: saved %s bytes for msg %s', len(resp.content), msg.pk)
    return 'saved'


def message_chat_id(msg):
    """The WAHA chat id a stored message belongs to, '' when it cannot be told.

    WEBJS ids are `<fromMe>_<chatId>_<key>[_<participant>]`, so the chat is the
    second part; the payload's from/to covers any other id shape."""
    parts = str(msg.waha_message_id or '').split('_')
    if len(parts) >= 3 and '@' in parts[1]:
        return parts[1]
    raw = msg.raw_payload if isinstance(msg.raw_payload, dict) else {}
    inner = raw.get('payload') if isinstance(raw.get('payload'), dict) else raw
    return str(inner.get('to' if msg.direction == 'outbound' else 'from') or '')


def fetch_on_demand(msg, chat_id=None):
    """Archive one message's media now, asking WAHA for a fresh copy first.

    The click path for group media: the cron skips groups, and the URL stored
    at ingest died with WAHA's 3-minute copy, so WAHA downloads the file from
    WhatsApp again. Also refreshes msg.media_url in memory, so a file over the
    archive cap can still be streamed once. Returns 'saved', 'skipped' or 'failed'."""
    from whatsapp.wa_chats_view import _CHAT_ID_RE, _LIVE_MSG_ID_RE, _waha_json

    if msg.media_file:
        return 'skipped'
    chat_id = chat_id or message_chat_id(msg)
    waha_id = str(msg.waha_message_id or '')
    # Both go into the WAHA URL path, so only well-formed ids get that far.
    if not _CHAT_ID_RE.match(chat_id) or not _LIVE_MSG_ID_RE.match(waha_id):
        return 'failed'
    status, fresh = _waha_json(f'/api/{msg.session}/chats/{chat_id}/messages/{waha_id}',
                               {'downloadMedia': 'true'}, timeout=40)
    media = fresh.get('media') if status == 200 and isinstance(fresh, dict) else None
    url = (media.get('url') or '') if isinstance(media, dict) else ''
    if not url:
        logger.info('fetch on demand: WAHA has no file for msg %s (HTTP %s)', msg.pk, status)
        return 'failed'
    msg.media_url = url
    if not msg.media_mime:
        msg.media_mime = media.get('mimetype') or ''
    return archive_message_media(msg)


def archive_pending_media(limit=25):
    """Archive media for recent messages that still lack a local file.

    Only looks at rows touched within RETRY_WINDOW_MINUTES — older files are
    already purged from WAHA and would 404 forever. Group chats are left out:
    their media downloads only when someone clicks it (fetch_on_demand). A
    group's id always carries its `@g.us` chat id. Returns counters."""
    from whatsapp.models import WhatsAppMessage

    cutoff = timezone.now() - timedelta(minutes=RETRY_WINDOW_MINUTES)
    pending = (
        WhatsAppMessage.objects
        .exclude(media_url='')
        .exclude(waha_message_id__contains='@g.us')
        .filter(media_file='', updated_at__gte=cutoff)
        .order_by('created_at')[:limit]
    )
    counts = {'saved': 0, 'skipped': 0, 'failed': 0}
    for msg in pending:
        counts[archive_message_media(msg)] += 1
    return counts
