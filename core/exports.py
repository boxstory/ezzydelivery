# Purpose: Build one consistent download filename for every export in the app.
# Used by: export views in workforce/, business/, fleet/ (CSV, XLSX and PDF downloads).
# Notes: Shape is <base>_<CODE>_<YYYYMMDD>.<ext>. The CODE segment is the business or
#        driver code the export is scoped to (falling back to its id when the code is
#        blank) and is dropped entirely when the export covers more than one of them.

import re

from django.utils import timezone

# Anything outside these sets is collapsed to a single dash so the name stays safe
# on Windows/macOS and inside a Content-Disposition header. The base keeps its own
# underscores (orders_export); a code must not add any, or the three segments of the
# name stop being readable.
_UNSAFE_BASE = re.compile(r'[^A-Za-z0-9_-]+')
_UNSAFE_CODE = re.compile(r'[^A-Za-z0-9-]+')


def entity_code(obj):
    """Filename code for a Business or Driver instance.

    Both models keep a human code (`business_code` / `driver_code`) that is
    nullable, so fall back to the primary key rather than emitting "None".
    Accepts a plain string/int too, and returns '' for None.
    """
    if obj is None:
        return ''
    for attr in ('business_code', 'driver_code'):
        if hasattr(obj, attr):
            return _clean(getattr(obj, attr) or obj.pk, _UNSAFE_CODE)
    return _clean(obj, _UNSAFE_CODE)


def _clean(value, pattern):
    return pattern.sub('-', str(value)).strip('-_')


def export_filename(base, code=None, ext='csv', when=None):
    """`<base>_<CODE>_<YYYYMMDD>.<ext>` — the house shape for every export file.

    `code` may be a Business/Driver instance or an already-resolved string; a
    falsy code just leaves that segment out (whole-fleet / all-clients exports).
    `when` defaults to today in local time, not UTC, so a late-evening export in
    Doha is not stamped with tomorrow's date.
    """
    stamp = (when or timezone.localtime()).strftime('%Y%m%d')
    code = _clean(code, _UNSAFE_CODE) if isinstance(code, str) else entity_code(code)
    parts = [_clean(base, _UNSAFE_BASE)] + ([code] if code else []) + [stamp]
    return '%s.%s' % ('_'.join(parts), ext.lstrip('.'))


def set_export_filename(response, base, code=None, ext='csv', when=None):
    """Attach the export filename to `response` as an attachment disposition."""
    name = export_filename(base, code=code, ext=ext, when=when)
    response['Content-Disposition'] = 'attachment; filename="%s"' % name
    return response


# --- CSV writing ------------------------------------------------------------

def safe_csv_writer(target, **kwargs):
    """csv.writer whose every string cell is checked for formula injection.

    A cell beginning "=", "+", "-" or "@" is evaluated as a formula by Excel,
    LibreOffice and Google Sheets when the export is opened. Customer names and
    order notes reach these files verbatim, so the neutralising prefix has to be
    applied at write time rather than at each of the dozens of call sites.

    Drop-in for ``csv.writer(response)``.
    """
    import csv

    from core.validators import sanitize_csv_cell

    class _SanitizingWriter:
        def __init__(self, writer):
            self._writer = writer

        def writerow(self, row):
            return self._writer.writerow([sanitize_csv_cell(cell) for cell in row])

        def writerows(self, rows):
            return self._writer.writerows(
                [sanitize_csv_cell(cell) for cell in row] for row in rows
            )

        def __getattr__(self, name):
            return getattr(self._writer, name)

    return _SanitizingWriter(csv.writer(target, **kwargs))
