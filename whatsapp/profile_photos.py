"""
Purpose: Load WhatsApp profile photos from WAHA, save a copy in private storage, and hand it back to the inbox.
Used by: whatsapp/wa_chats_view.py (wa_chats_avatar)
Notes: WhatsApp's CDN URLs expire within days, hence the saved copy; refreshed after REFRESH_AFTER. Only https *.whatsapp.net photo URLs are downloaded (SSRF guard).
"""
import logging
import re
from datetime import timedelta
from io import BytesIO
from urllib.parse import urlparse

import requests
from django.conf import settings
from django.core.files.base import ContentFile
from django.utils import timezone

from .models import WhatsAppProfilePhoto

logger = logging.getLogger(__name__)

REFRESH_AFTER = timedelta(days=7)
# A failed WAHA lookup is retried sooner than a confirmed "no photo".
RETRY_AFTER_ERROR = timedelta(hours=1)
MAX_BYTES = 2 * 1024 * 1024
CHAT_ID_RE = re.compile(r'^[\w.\-]{1,80}@(c\.us|lid|g\.us)$')
_EXT = {'JPEG': 'jpg', 'PNG': 'png', 'WEBP': 'webp'}


def is_valid_chat_id(chat_id):
    return bool(CHAT_ID_RE.match(chat_id or ''))


def _photo_url(session, chat_id):
    """WAHA's current CDN URL for the photo; '' for none; None when WAHA failed."""
    base = (getattr(settings, 'WAHA_BASE_URL', '') or '').rstrip('/')
    try:
        resp = requests.get(
            f'{base}/api/contacts/profile-picture',
            params={'contactId': chat_id, 'session': session},
            headers={'X-Api-Key': getattr(settings, 'WAHA_API_KEY', '') or ''},
            timeout=8,
        )
        if not (200 <= resp.status_code < 300):
            return None
        return (resp.json() or {}).get('profilePictureURL') or ''
    except (requests.exceptions.RequestException, ValueError) as e:
        logger.warning('profile photo lookup failed for %s/%s: %s', session, chat_id, e)
        return None


def _download(url):
    """Image bytes + extension, or None. Refuses anything but WhatsApp's own CDN."""
    parsed = urlparse(url)
    host = (parsed.hostname or '').lower()
    if parsed.scheme != 'https' or not (host == 'whatsapp.net' or host.endswith('.whatsapp.net')):
        logger.warning('profile photo: refusing non-WhatsApp URL host %s', host)
        return None
    try:
        with requests.get(url, timeout=8, stream=True, allow_redirects=False) as resp:
            if resp.status_code != 200:
                return None
            data = resp.raw.read(MAX_BYTES + 1, decode_content=True)
    except requests.exceptions.RequestException as e:
        logger.warning('profile photo download failed: %s', e)
        return None
    if not data or len(data) > MAX_BYTES:
        return None
    # Trust the bytes, not the header: only a real JPEG/PNG/WebP is kept.
    try:
        from PIL import Image
        with Image.open(BytesIO(data)) as img:
            img.verify()
            fmt = img.format
    except Exception:
        return None
    ext = _EXT.get(fmt)
    return (data, ext) if ext else None


def get_photo(session, chat_id):
    """Saved photo row for this chat, loading/refreshing it from WAHA when due.

    Returns the row (check has_photo) or None when nothing is known yet and
    WAHA could not be reached.
    """
    row = WhatsAppProfilePhoto.objects.filter(session=session, chat_id=chat_id).first()
    now = timezone.now()
    # A failed download back-dates fetched_at, so this one test also covers the retry.
    if row and now - row.fetched_at < REFRESH_AFTER:
        return row

    url = _photo_url(session, chat_id)
    if url is None:
        return row  # WAHA unreachable — keep serving whatever we have
    if row is None:
        row = WhatsAppProfilePhoto(session=session, chat_id=chat_id, fetched_at=now)

    if url == '':
        # The contact has no photo (or hides it from us). Drop any old copy.
        if row.photo:
            row.photo.delete(save=False)
        row.has_photo = False
        row.fetched_at = now
        row.save()
        return row

    got = _download(url)
    if got is None:
        # Keep an older copy if we have one; try again in an hour.
        row.fetched_at = now - REFRESH_AFTER + RETRY_AFTER_ERROR
        if row.pk or row.photo:
            row.save()
        return row if row.photo else None

    data, ext = got
    old = row.photo.name if row.photo else ''
    safe = re.sub(r'[^\w]', '_', f'{session}_{chat_id}')[:120]
    row.photo.save(f'{safe}.{ext}', ContentFile(data), save=False)
    row.has_photo = True
    row.fetched_at = now
    row.save()
    if old and old != row.photo.name:
        row.photo.storage.delete(old)
    return row
