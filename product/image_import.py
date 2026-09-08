"""
Purpose: Download a remote product photo (Shopify/WooCommerce CDN) into Product.product_image.
Used by: product.views.product_api_import (client wizard), workforce.views.seller_api_products_import (staff).
Notes: SSRF-guarded and size-capped; never raises — a failed photo must not fail the import.
"""
import logging
import mimetypes
import os
from urllib.parse import urlparse, unquote

import requests

from django.core.files.base import ContentFile

from core.net_guard import validate_public_url

logger = logging.getLogger('product')

# A product photo well past this is a mistake, not a photo.
MAX_IMAGE_BYTES = 8 * 1024 * 1024
REQUEST_TIMEOUT = 15
ALLOWED_EXTENSIONS = ('.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp')


def _filename_for(url, content_type, sku):
    """Build a stable, safe filename from the SKU + the source image extension."""
    path = urlparse(url).path
    ext = os.path.splitext(unquote(path))[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        ext = mimetypes.guess_extension((content_type or '').split(';')[0].strip()) or ''
        if ext == '.jpe':
            ext = '.jpg'
    if ext not in ALLOWED_EXTENSIONS:
        ext = '.jpg'
    safe_sku = ''.join(c for c in (sku or 'product') if c.isalnum() or c in ('-', '_'))[:60]
    return f'{safe_sku or "product"}{ext}'


def attach_product_image(product, url):
    """Fetch `url` and save it to product.product_image. Returns True when saved.

    Swallows every failure (bad URL, timeout, non-image, oversized) and logs it —
    an unreachable CDN must never abort a catalogue import.
    """
    url = (url or '').strip()
    if not url or not product:
        return False

    ok, reason = validate_public_url(url)
    if not ok:
        logger.info('Product image skipped for %s: %s (%s)', product.pk, reason, url[:120])
        return False

    try:
        resp = requests.get(url, timeout=REQUEST_TIMEOUT, stream=True)
        if resp.status_code != 200:
            logger.info('Product image HTTP %s for %s (%s)', resp.status_code, product.pk, url[:120])
            return False

        content_type = resp.headers.get('Content-Type', '')
        if content_type and not content_type.lower().startswith('image/'):
            logger.info('Product image not an image (%s) for %s', content_type, product.pk)
            return False

        # Read with a hard cap so a huge/streaming response can't exhaust memory.
        chunks, total = [], 0
        for chunk in resp.iter_content(64 * 1024):
            total += len(chunk)
            if total > MAX_IMAGE_BYTES:
                logger.info('Product image too large (>%s bytes) for %s', MAX_IMAGE_BYTES, product.pk)
                return False
            chunks.append(chunk)
        content = b''.join(chunks)
        if not content:
            return False

        product.product_image.save(
            _filename_for(url, content_type, product.item_sku),
            ContentFile(content),
            save=True,
        )
        return True
    except requests.exceptions.RequestException as exc:
        logger.info('Product image fetch failed for %s: %s', product.pk, exc)
        return False
    except Exception:
        logger.exception('Product image save failed for %s', product.pk)
        return False
