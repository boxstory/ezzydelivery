"""
Purpose: Shared input validators — upload guards, CSV cell sanitisation, bounded int coercion.
Used by: model FileField/ImageField definitions, forms.clean_* methods, CSV export views.
Notes: MaxFileSizeValidator is @deconstructible so it serialises into migrations. Changing its
       max_mb rewrites the field's validators list, which generates a no-op AlterField migration.
"""
import re

from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator
from django.utils.deconstruct import deconstructible

# --- Upload guards ----------------------------------------------------------

IMAGE_EXTENSIONS = ['jpg', 'jpeg', 'png', 'webp', 'gif', 'heic', 'heif']
DOCUMENT_EXTENSIONS = IMAGE_EXTENSIONS + ['pdf']
DATA_EXTENSIONS = ['csv', 'xls', 'xlsx']
# WhatsApp media arrives as whatever the sender attached; allow the common
# document/media types but never executables or archives. Measured against the
# 598 files already archived: jpg/oga/pdf/mp4/webp/xlsx/csv. An earlier, narrower
# list omitted oga (166 files — WhatsApp voice notes), xlsx and csv, which would
# have broken voice-note archiving outright.
MEDIA_EXTENSIONS = DOCUMENT_EXTENSIONS + DATA_EXTENSIONS + [
    'mp3', 'ogg', 'oga', 'opus', 'm4a', 'aac', 'amr', 'wav',
    'mp4', 'webm', '3gp', '3gpp', 'mov',
    'doc', 'docx', 'ppt', 'pptx', 'txt', 'vcf',
]


@deconstructible
class MaxFileSizeValidator:
    """Reject uploads above ``max_mb`` megabytes.

    Django enforces no size ceiling of its own on FileField — without this a
    single request can write an arbitrarily large file under MEDIA_ROOT.
    """

    def __init__(self, max_mb):
        self.max_mb = max_mb

    def __call__(self, value):
        size = getattr(value, 'size', None)
        if size is None:
            return
        limit = self.max_mb * 1024 * 1024
        if size > limit:
            raise ValidationError(
                f'File is too large ({size / (1024 * 1024):.1f} MB). '
                f'Maximum allowed size is {self.max_mb} MB.'
            )

    def __eq__(self, other):
        return isinstance(other, MaxFileSizeValidator) and self.max_mb == other.max_mb

    def __hash__(self):
        return hash(('MaxFileSizeValidator', self.max_mb))


def image_validators(max_mb=8):
    """Validator list for an ImageField holding a user-supplied photo."""
    return [FileExtensionValidator(allowed_extensions=IMAGE_EXTENSIONS),
            MaxFileSizeValidator(max_mb)]


def document_validators(max_mb=10):
    """Validator list for a FileField holding an ID / licence / label scan."""
    return [FileExtensionValidator(allowed_extensions=DOCUMENT_EXTENSIONS),
            MaxFileSizeValidator(max_mb)]


def media_validators(max_mb=25):
    """Validator list for inbound WhatsApp media."""
    return [FileExtensionValidator(allowed_extensions=MEDIA_EXTENSIONS),
            MaxFileSizeValidator(max_mb)]


def validate_upload_file(uploaded_file, allowed_extensions, max_mb, field_label='File'):
    """Imperative form of the above, for forms.clean_<field> methods.

    Returns the file unchanged; raises ValidationError on the first failure.
    """
    if not uploaded_file:
        return uploaded_file

    size = getattr(uploaded_file, 'size', 0) or 0
    if size > max_mb * 1024 * 1024:
        raise ValidationError(
            f'{field_label} is too large ({size / (1024 * 1024):.1f} MB). '
            f'Maximum allowed size is {max_mb} MB.'
        )

    name = (getattr(uploaded_file, 'name', '') or '').lower()
    ext = name.rsplit('.', 1)[-1] if '.' in name else ''
    if ext not in [e.lower() for e in allowed_extensions]:
        allowed = ', '.join(f'.{e}' for e in allowed_extensions)
        raise ValidationError(f'{field_label} must be one of: {allowed}')

    return uploaded_file


# --- CSV export sanitisation ------------------------------------------------

# Cells opening with any of these are interpreted as a formula by Excel,
# LibreOffice and Google Sheets. A leading tab or CR is also honoured after
# the spreadsheet trims it, so strip whitespace before testing.
_CSV_FORMULA_PREFIXES = ('=', '+', '-', '@', '\t', '\r')
_PHONE_LIKE = re.compile(r'^\+\d[\d\s-]{5,}$')


def sanitize_csv_cell(value):
    """Neutralise spreadsheet formula injection in one exported cell.

    Prefixes a single quote to any string that a spreadsheet would evaluate as
    a formula. Non-string values pass through untouched so numbers and dates
    keep their native type in the output.
    """
    if not isinstance(value, str):
        return value
    stripped = value.lstrip()
    # An international phone number is the one common value that opens with '+'
    # and is never a formula. Prefixing it puts a stray quote in front of every
    # customer number in a client-facing export.
    if _PHONE_LIKE.match(stripped):
        return value
    if stripped.startswith(_CSV_FORMULA_PREFIXES):
        return "'" + value
    return value


def sanitize_csv_row(row):
    """Apply :func:`sanitize_csv_cell` across an iterable of cells."""
    return [sanitize_csv_cell(cell) for cell in row]


# --- Bounded coercion -------------------------------------------------------

def safe_int(raw, default=0, minimum=None, maximum=None):
    """Coerce request input to int without raising.

    ``int(request.GET.get('days', 30))`` raises ValueError on ?days=abc and
    returns a 500. This clamps instead: unparseable input falls back to
    ``default``, and the result is clamped into [minimum, maximum].
    """
    try:
        value = int(str(raw).strip())
    except (TypeError, ValueError, AttributeError):
        value = default
    if minimum is not None and value < minimum:
        value = minimum
    if maximum is not None and value > maximum:
        value = maximum
    return value


def safe_decimal(raw, default=None, minimum=None, maximum=None):
    """Decimal counterpart to :func:`safe_int`, for money and coordinates."""
    from decimal import Decimal, InvalidOperation
    try:
        value = Decimal(str(raw).strip())
    except (TypeError, ValueError, InvalidOperation, AttributeError):
        return default
    if minimum is not None and value < Decimal(str(minimum)):
        value = Decimal(str(minimum))
    if maximum is not None and value > Decimal(str(maximum)):
        value = Decimal(str(maximum))
    return value


# --- Text sanitisation ------------------------------------------------------

# C0/C1 control characters except tab, newline and carriage return. These serve
# no purpose in a submitted field and are a common way to smuggle content past
# a naive filter or corrupt a downstream export.
_CONTROL_CHARS = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]')
# Invisible characters used for homograph and right-to-left-override display
# attacks. U+200C ZWNJ and U+200D ZWJ are deliberately NOT in this set: ZWNJ is
# orthographically required in Persian/Arabic (نمی‌خواهم loses its meaning
# without it) and ZWJ joins emoji sequences (a family emoji becomes three
# separate people). Stripping them corrupts real names on an Arabic-facing site.
_INVISIBLE_CHARS = re.compile(
    '['
    '​'          # zero-width space
    '‎‏'    # LTR / RTL marks
    '‪-‮'   # bidi embedding + the RLO override used to disguise text
    '⁠-⁤'   # word joiner, invisible operators
    '⁦-⁩'   # bidi isolates
    '﻿'          # BOM / zero-width no-break space
    ']'
)


def sanitize_text(value, collapse_whitespace=False):
    """Strip control and invisible characters from a submitted string.

    Does not escape HTML — Django's template autoescaping handles output. This
    removes characters that should never have been accepted at input time.
    """
    if not isinstance(value, str):
        return value
    cleaned = _CONTROL_CHARS.sub('', value)
    cleaned = _INVISIBLE_CHARS.sub('', cleaned)
    if collapse_whitespace:
        cleaned = re.sub(r'\s+', ' ', cleaned)
    return cleaned.strip()


# --- Phone normalisation ----------------------------------------------------

QATAR_MOBILE_PREFIXES = '3567'


def normalize_qatar_phone(raw, field_label='Phone number', required=True):
    """Normalise a submitted Qatar phone number to bare 8 digits.

    Accepts +974/974 prefixes and any mix of spaces, dashes and parentheses.
    Longer international numbers are passed through digits-only rather than
    rejected, so a genuine overseas contact still saves.
    """
    value = sanitize_text(raw or '', collapse_whitespace=True)
    if not value:
        if required:
            raise ValidationError(f'{field_label} is required.')
        return ''

    digits = re.sub(r'[^\d]', '', value)
    # Accept every way a Qatar number gets typed: 974…, +974… (the + is already
    # gone), and the 00974… international-dial form. Without the 00 case that
    # input falls through unnormalised and creates a third stored format.
    if digits.startswith('00974') and len(digits) == 13:
        digits = digits[5:]
    elif digits.startswith('974') and len(digits) == 11:
        digits = digits[3:]

    if len(digits) == 8:
        if digits[0] not in QATAR_MOBILE_PREFIXES:
            raise ValidationError(
                f'{field_label} must be a Qatar number starting with '
                f'{", ".join(QATAR_MOBILE_PREFIXES)}.'
            )
        return digits

    if 8 < len(digits) <= 15:
        return digits

    raise ValidationError(
        f'{field_label} must be 8 digits (Qatar) or a valid international number.'
    )


def validate_alphanumeric_ref(raw, field_label='Reference', max_length=64,
                              required=True, allow=' -/'):
    """Validate a human-entered reference (licence no, plate, document no).

    Rejects anything outside letters, digits and the ``allow`` set, which keeps
    markup and separator characters out of fields that are later rendered into
    labels and exports.
    """
    value = sanitize_text(raw or '', collapse_whitespace=True)
    if not value:
        if required:
            raise ValidationError(f'{field_label} is required.')
        return ''
    if len(value) > max_length:
        raise ValidationError(f'{field_label} must be {max_length} characters or fewer.')
    pattern = r'^[A-Za-z0-9' + re.escape(allow) + r']+$'
    if not re.match(pattern, value):
        raise ValidationError(
            f'{field_label} may only contain letters, numbers and {allow.strip() or "spaces"}.'
        )
    return value


# --- Upload filename rebuilding ---------------------------------------------

def safe_upload_name(filename, allowed_extensions=None, fallback_ext='bin'):
    """Rebuild an uploaded filename as `<uuid4hex>.<ext>`.

    The client's filename must never reach the filesystem. Interpolating it into
    an `upload_to` path lets a caller choose the stored extension — `proof.html`
    under MEDIA_ROOT is served as text/html from our own origin — and invites
    traversal and collision problems besides. The extension is kept only when it
    is on the allowlist, so the served content type stays predictable.
    """
    import uuid

    name = (filename or '').lower()
    ext = name.rsplit('.', 1)[-1] if '.' in name else ''
    ext = re.sub(r'[^a-z0-9]', '', ext)[:8]
    if allowed_extensions is not None and ext not in [e.lower() for e in allowed_extensions]:
        ext = fallback_ext
    return f'{uuid.uuid4().hex}.{ext or fallback_ext}'
