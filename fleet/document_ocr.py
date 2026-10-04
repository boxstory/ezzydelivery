"""
Purpose: Read a driver document's number and expiry with local RapidOCR — the value printed beside its label, or the passport MRZ.
Used by: fleet/document_verify.py (the per-minute verify_driver_documents cron).
Notes: Label-anchored ("Expiry", "VALIDITY", "Vehicle No.", "Exp. Date"), so a shifted or photographed card still reads; only those
       values are used. Passports read the MRZ line and keep a value only when its ICAO check digit holds. Needs rapidocr-onnxruntime +
       opencv-python-headless (NOT opencv-python: the desktop build needs libGL, which this server lacks). Never guesses: no match = ''.
"""

import io
import re
from collections import Counter
from datetime import date

OCR_TYPES = ('QID', 'Driving License', 'Istimara', 'Passport')

# The 11-digit QID number is also the Qatar licence number.
NUMBER_RE = {'QID': r'[23]\d{10}', 'Driving License': r'[23]\d{10}'}
EXPIRY_LABELS = {
    'QID': ('expiry', 'expir'),
    'Driving License': ('validity', 'valid'),
    'Istimara': ('exp.date', 'expdate', 'exp.'),
}
ISTIMARA_NUMBER_LABELS = ('vehicleno', 'vehicle')
MRZ_LINE2 = re.compile(r'([A-Z0-9<]{9})(\d)([A-Z<]{3})(\d{6})(\d)([MF<])(\d{6})(\d)')

_engine = None


def _ocr_engine():
    global _engine
    if _engine is None:
        from rapidocr_onnxruntime import RapidOCR
        _engine = RapidOCR()
    return _engine


def _plausible_expiry(d):
    today = date.today()
    return d if d and date(today.year - 3, 1, 1) <= d <= date(today.year + 12, 12, 31) else None


def _parse_date(text):
    t = re.sub(r'\s+', '', text or '')
    try:
        m = re.search(r'(\d{4})[/\-.](\d{1,2})[/\-.](\d{1,2})', t)
        if m:
            return _plausible_expiry(date(int(m.group(1)), int(m.group(2)), int(m.group(3))))
        m = re.search(r'(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{4})', t)
        if m:
            return _plausible_expiry(date(int(m.group(3)), int(m.group(2)), int(m.group(1))))
    except ValueError:
        return None
    return None


def _mrz_check(field, digit):
    """ICAO 9303 check digit: weights 7,3,1; digits as-is, A=10..Z=35, '<'=0."""
    total = 0
    for i, ch in enumerate(field):
        v = int(ch) if ch.isdigit() else (ord(ch) - 55 if ch.isalpha() else 0)
        total += v * (7, 3, 1)[i % 3]
    return total % 10 == int(digit)


def _read_mrz(lines):
    for line in lines:
        m = MRZ_LINE2.search(re.sub(r'\s+', '', line.upper()).replace('«', '<'))
        if not m:
            continue
        number = m.group(1).replace('<', '') if _mrz_check(m.group(1), m.group(2)) else ''
        expiry = None
        if _mrz_check(m.group(7), m.group(8)):
            try:
                expiry = _plausible_expiry(date(2000 + int(m.group(7)[:2]), int(m.group(7)[2:4]), int(m.group(7)[4:])))
            except ValueError:
                expiry = None
        if number or expiry:
            return number, expiry
    return '', None


def _boxes(result):
    out = []
    for pts, text, _conf in result or []:
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        out.append({'t': text, 'x0': min(xs), 'x1': max(xs),
                    'cy': (min(ys) + max(ys)) / 2, 'h': max(ys) - min(ys)})
    return out


def _label_key(text):
    return re.sub(r'[^a-z.]', '', text.lower())


def _beside(label, boxes, parse):
    """The first value on the label's own row, nearest to its right; else inside the label box itself
    ("Expiry: 28/03/2027" often comes back as one box)."""
    row = [b for b in boxes if b is not label and b['x0'] >= label['x0']
           and abs(b['cy'] - label['cy']) <= max(label['h'], 8) * 0.8]
    for b in sorted(row, key=lambda b: b['x0'] - label['x1']):
        value = parse(b['t'])
        if value:
            return value
    return parse(label['t'])


def _istimara_number(text):
    m = re.search(r'(?<!\d)\d{3,7}(?!\d)', text.replace(' ', ''))
    return m.group(0) if m else ''


def _read_card(doc_type, result):
    boxes = _boxes(result)
    number = ''
    if doc_type == 'Istimara':
        for b in boxes:
            if any(k in _label_key(b['t']) for k in ISTIMARA_NUMBER_LABELS):
                number = _beside(b, boxes, _istimara_number)
                if number:
                    break
    else:
        # A QID / licence number stands alone in its own box; the most frequent
        # 11-digit hit wins (a QID image repeats it on the back).
        hits = [re.sub(r'\s', '', b['t']) for b in boxes]
        hits = [h for h in hits if re.fullmatch(NUMBER_RE[doc_type], h)]
        number = Counter(hits).most_common(1)[0][0] if hits else ''
    expiry = None
    for b in boxes:
        key = _label_key(b['t'])
        if any(key.startswith(k) or k in key for k in EXPIRY_LABELS[doc_type]):
            expiry = _beside(b, boxes, _parse_date)
            if expiry:
                break
    return number, expiry


def read_document_ocr(doc):
    """{'readable', 'document_no', 'expiry_date' (ISO str), 'note'} — same shape as the AI reader.
    Raises OSError/ValueError for an unusable image file."""
    import numpy as np
    from PIL import Image, ImageOps

    doc.document_file.open('rb')
    try:
        im = ImageOps.exif_transpose(Image.open(io.BytesIO(doc.document_file.read()))).convert('RGB')
    finally:
        doc.document_file.close()
    result, _ = _ocr_engine()(np.array(im))
    if doc.document_type == 'Passport':
        number, expiry = _read_mrz([r[1] for r in result or []])
    else:
        number, expiry = _read_card(doc.document_type, result)
    readable = bool(number or expiry)
    return {
        'readable': readable,
        'document_no': number,
        'expiry_date': expiry.isoformat() if expiry else '',
        'note': '' if readable else 'Number and expiry not found on the image',
    }
