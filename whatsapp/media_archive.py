# Purpose: Download WAHA media files into Django storage before WAHA purges them (~3 min lifetime).
# Used by: whatsapp/management/commands/archive_wa_media.py (per-minute cron), wa_chats resync.
# Notes: Idempotent per message; rows older than the retry window are treated as purged and skipped.

import logging
import mimetypes
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

    mime = (media.get('mime') or msg.media_mime or '').split(';')[0].strip()
    ext = mimetypes.guess_extension(mime) or ''
    if ext == '.jpe':
        ext = '.jpg'
    tail = url.rsplit('/', 1)[-1]
    if not ext and '.' in tail:
        ext = '.' + tail.rsplit('.', 1)[-1][:8]
    msg.media_file.save(f'{msg.pk}{ext}', ContentFile(resp.content), save=False)
    if mime and not msg.media_mime:
        msg.media_mime = mime
    msg.save(update_fields=['media_file', 'media_mime', 'updated_at'])
    logger.info('archive media: saved %s bytes for msg %s', len(resp.content), msg.pk)
    return 'saved'


def archive_pending_media(limit=25):
    """Archive media for recent messages that still lack a local file.

    Only looks at rows touched within RETRY_WINDOW_MINUTES — older files are
    already purged from WAHA and would 404 forever. Returns counters."""
    from whatsapp.models import WhatsAppMessage

    cutoff = timezone.now() - timedelta(minutes=RETRY_WINDOW_MINUTES)
    pending = (
        WhatsAppMessage.objects
        .exclude(media_url='')
        .filter(media_file='', updated_at__gte=cutoff)
        .order_by('created_at')[:limit]
    )
    counts = {'saved': 0, 'skipped': 0, 'failed': 0}
    for msg in pending:
        counts[archive_message_media(msg)] += 1
    return counts
