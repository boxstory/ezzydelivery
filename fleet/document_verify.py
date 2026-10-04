"""
Purpose: Read a driver document's number and expiry off its scan (local OCR, AI optional fallback) and verify it when both match what was typed.
Used by: fleet.models.DriverDocument.save (queues / re-compares), manage.py verify_driver_documents (per-minute cron drains the queue).
Notes: Never called inside a request — reads take seconds and nginx cuts responses at 60s. A transient AI failure leaves the row 'pending' for the next run.
       Never writes the number or expiry: what the image shows is stored as ai_* and offered to staff as a suggestion only.
"""

import base64
import io
import json
import logging
import re
from datetime import date, timedelta

from django.conf import settings
from django.utils import timezone

from fleet.document_ocr import OCR_TYPES

logger = logging.getLogger(__name__)

# Document types the OCR regions cover (fleet/document_ocr.py); a selfie or national ID is not read.
CHECKED_TYPES = OCR_TYPES
IMAGE_EXTS = ('.jpg', '.jpeg', '.png', '.webp', '.gif')
MAX_IMAGE_EDGE = 1600
RETRY_AFTER = timedelta(minutes=30)

READ_SCHEMA = {
    'type': 'object',
    'properties': {
        'readable': {'type': 'boolean'},
        'document_no': {'type': 'string'},
        'expiry_date': {'type': 'string'},
        'note': {'type': 'string'},
    },
    'required': ['readable', 'document_no', 'expiry_date', 'note'],
    'additionalProperties': False,
}

PROMPT = (
    'These are photos of one {doc_type} issued in Qatar (front, and back when there are two). '
    'Read the document number and the expiry date printed on it.\n'
    '- QID: the 11-digit ID number. Driving License: the licence number (for a Qatar licence '
    'this is usually the holder\'s 11-digit QID number). Istimara: the vehicle registration '
    '(plate) number. Passport: the passport number.\n'
    '- expiry_date as YYYY-MM-DD. Qatar documents often print dates as DD/MM/YYYY; convert them.\n'
    '- Copy only what is printed. If a value cannot be read with confidence, return an empty '
    'string for it — never guess.\n'
    '- readable is false when the photo is not this kind of document, or is too blurred, '
    'cropped or dark to read. Put a short reason in note.'
)


def _is_image(field):
    return bool(field and field.name and field.name.lower().endswith(IMAGE_EXTS))


def needs_image_check(doc):
    """True when the row has a real scan of a document type that carries a number."""
    return doc.document_type in CHECKED_TYPES and doc.has_real_file and _is_image(doc.document_file)


def normalize_no(value):
    """Compare numbers by letters and digits only: '2 8435-6012' == '284356012'."""
    return re.sub(r'[^0-9A-Z]', '', str(value or '').upper())


def apply_comparison(doc):
    """Set ai_status / ai_note / verified_at from the stored reading vs the typed values.
    Does not save. An empty typed field is a mismatch, never filled in."""
    problems = []
    typed_no, read_no = normalize_no(doc.document_no), normalize_no(doc.ai_document_no)
    if doc.document_type == 'Istimara':
        # The Istimara number is the Vehicle No. (plate); "048555" and "48555" are the same plate.
        typed_no, read_no = typed_no.lstrip('0'), read_no.lstrip('0')
    if not read_no:
        problems.append('number not readable on the image')
    elif not typed_no:
        problems.append(f'number not entered (image shows {doc.ai_document_no})')
    elif typed_no != read_no:
        problems.append(f'number on image is {doc.ai_document_no}')
    if not doc.ai_expiry_date:
        problems.append('expiry not readable on the image')
    elif not doc.document_expiry_date:
        problems.append(f'expiry not entered (image shows {doc.ai_expiry_date:%d %b %Y})')
    elif doc.document_expiry_date != doc.ai_expiry_date:
        problems.append(f'expiry on image is {doc.ai_expiry_date:%d %b %Y}')

    if problems:
        doc.ai_status = doc.AI_MISMATCH
        note = '; '.join(problems)
        doc.ai_note = (note[:1].upper() + note[1:])[:255]
        doc.verified_at = None
    else:
        doc.ai_status = doc.AI_VERIFIED
        doc.ai_note = ''
        doc.verified_at = doc.verified_at or timezone.now()


def _image_block(field):
    from PIL import Image, ImageOps

    field.open('rb')
    try:
        img = Image.open(io.BytesIO(field.read()))
        img = ImageOps.exif_transpose(img).convert('RGB')
    finally:
        field.close()
    img.thumbnail((MAX_IMAGE_EDGE, MAX_IMAGE_EDGE))
    buf = io.BytesIO()
    img.save(buf, format='JPEG', quality=88)
    return {
        'type': 'image',
        'source': {'type': 'base64', 'media_type': 'image/jpeg',
                   'data': base64.standard_b64encode(buf.getvalue()).decode('ascii')},
    }


def _parse_date(value):
    try:
        return date.fromisoformat((value or '').strip())
    except ValueError:
        return None


def read_document(doc):
    """Local OCR of the fixed regions first; Claude only when OCR finds nothing and
    DOC_VERIFY_AI_FALLBACK is on. Returns {'readable', 'document_no', 'expiry_date', 'note'}."""
    from fleet.document_ocr import read_document_ocr

    result = read_document_ocr(doc)
    if result['readable'] or not getattr(settings, 'DOC_VERIFY_AI_FALLBACK', False):
        return result
    return read_document_ai(doc)


def read_document_ai(doc):
    """Ask Claude for the number and expiry on the scan. Returns the parsed dict.
    Raises anthropic errors (transient) and OSError/ValueError (bad image file)."""
    import anthropic

    content = [_image_block(doc.document_file)]
    if _is_image(doc.document_file_back):
        content.append(_image_block(doc.document_file_back))
    content.append({'type': 'text', 'text': PROMPT.format(doc_type=doc.document_type)})

    client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY, timeout=90.0)
    response = client.messages.create(
        model=settings.DOC_VERIFY_AI_MODEL,
        max_tokens=4000,
        messages=[{'role': 'user', 'content': content}],
        # SDK 0.76 predates output_config, so the schema rides in the raw body.
        extra_body={'output_config': {
            'effort': 'low',
            'format': {'type': 'json_schema', 'schema': READ_SCHEMA},
        }},
    )
    if response.stop_reason == 'refusal':
        return {'readable': False, 'document_no': '', 'expiry_date': '', 'note': 'Image check declined'}
    text = next((b.text for b in response.content if b.type == 'text'), '')
    return json.loads(text)


def verify_document(doc):
    """Read one pending document and store the result. Returns the new ai_status."""
    from fleet.models import DriverDocument

    now = timezone.now()
    try:
        result = read_document(doc)
    except (OSError, ValueError) as exc:
        # The stored file itself is unusable; retrying will not change that.
        logger.warning('document %s: image unusable: %s', doc.pk, exc)
        DriverDocument.objects.filter(pk=doc.pk).update(
            ai_status=DriverDocument.AI_ERROR, ai_note='Image file could not be opened'[:255],
            ai_checked_at=now)
        return DriverDocument.AI_ERROR
    except Exception as exc:
        # API/network trouble: keep it pending and try again after RETRY_AFTER.
        logger.warning('document %s: image check failed, will retry: %s', doc.pk, exc)
        DriverDocument.objects.filter(pk=doc.pk).update(
            ai_note=f'Image check failed, retrying: {exc}'[:255], ai_checked_at=now)
        return DriverDocument.AI_PENDING

    doc.ai_document_no = (result.get('document_no') or '').strip()[:100]
    doc.ai_expiry_date = _parse_date(result.get('expiry_date'))
    doc.ai_checked_at = now
    if not result.get('readable') or not (doc.ai_document_no or doc.ai_expiry_date):
        doc.ai_status = DriverDocument.AI_UNREADABLE
        doc.ai_note = (result.get('note') or 'Image could not be read')[:255]
        doc.verified_at = None
    else:
        apply_comparison(doc)
    # Queryset update keyed on the scan that was read: if staff replaced or
    # cropped the photo during the AI call, this result describes the old one
    # and is dropped — the new photo is already queued.
    updated = DriverDocument.objects.filter(
        pk=doc.pk, ai_status=DriverDocument.AI_PENDING,
        document_file=doc.document_file.name,
    ).update(
        ai_status=doc.ai_status, ai_document_no=doc.ai_document_no,
        ai_expiry_date=doc.ai_expiry_date, ai_note=doc.ai_note,
        ai_checked_at=doc.ai_checked_at, verified_at=doc.verified_at)
    return doc.ai_status if updated else DriverDocument.AI_PENDING


def pending_documents(limit=20):
    from django.db.models import Q
    from fleet.models import DriverDocument

    cutoff = timezone.now() - RETRY_AFTER
    return (DriverDocument.objects
            .filter(ai_status=DriverDocument.AI_PENDING)
            .filter(Q(ai_checked_at__isnull=True) | Q(ai_checked_at__lt=cutoff))
            .order_by('created_at')[:limit])


def staff_verify(doc, user):
    """A staff member checked the scan by eye and confirms the typed number and expiry."""
    doc.ai_status = doc.AI_VERIFIED
    doc.verified_at = timezone.now()
    doc.verified_by = user
    doc.ai_note = ''
    doc.save(update_fields=['ai_status', 'verified_at', 'verified_by', 'ai_note'])


def staff_unverify(doc):
    """Take back a verification: the row returns to whatever the image check says."""
    doc.verified_at = None
    doc.verified_by = None
    if doc.ai_checked_at and (doc.ai_document_no or doc.ai_expiry_date):
        apply_comparison(doc)
    elif needs_image_check(doc):
        doc.ai_status = doc.AI_PENDING
    else:
        doc.ai_status = doc.AI_NOT_NEEDED if doc.document_type == 'Selfie' else doc.AI_NO_IMAGE
    doc.save(update_fields=['ai_status', 'verified_at', 'verified_by', 'ai_note'])
