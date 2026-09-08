"""
Purpose: Base mixin giving every form a uniform sanitisation pass over submitted text.
Used by: forms.py in business, core, delivery, dispatch, fleet, orders, product, warehouse, webpages.
Notes: Sanitises self.data in __init__, so each field's own clean_<field> sees already-cleaned
       input. Password fields are excluded — trimming a password silently changes it.
"""
from django import forms

from core.validators import sanitize_text

# Substrings that mark a field whose value must reach validation byte-for-byte.
# Trimming or normalising a secret changes what the user actually typed.
_NEVER_SANITIZE = ('password', 'passwd', 'secret', 'token', 'api_key', 'signature')


class SanitizedFormMixin:
    """Strip control and invisible characters from every submitted text value.

    Mount it ahead of the Form/ModelForm base::

        class MyForm(SanitizedFormMixin, forms.ModelForm):
            sanitize_collapse_whitespace = ('full_name',)

    What it does NOT do is escape HTML — Django's template autoescaping owns
    output encoding. This is about refusing characters that have no business
    being in the field at input time: NUL and other C0/C1 controls, zero-width
    joiners used for homograph attacks, and right-to-left overrides used to
    disguise a filename or a payee name.

    Attributes:
        sanitize_collapse_whitespace: field names where runs of whitespace
            should also collapse to a single space (names, references, codes).
            Leave a field out of this list to preserve its line breaks.
        sanitize_exclude: field names to skip entirely, on top of the built-in
            password/secret exclusions.
        sanitize_max_length: hard ceiling applied to every sanitised value, as
            a backstop against megabyte-sized POSTs reaching a TextField.
    """

    sanitize_collapse_whitespace = ()
    sanitize_exclude = ()
    sanitize_max_length = 20000

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.data:
            self.data = self._sanitize_data(self.data)

    def _field_name(self, key):
        """Strip the form prefix off a datadict key.

        A prefixed form posts `veh-vehicle_no`, not `vehicle_no`, so matching
        `sanitize_collapse_whitespace` / `sanitize_exclude` against the raw key
        silently did nothing on every prefixed form — including the whole driver
        onboarding path, which is the one place these knobs are configured.
        """
        if self.prefix:
            head = f'{self.prefix}-'
            if key.startswith(head):
                return key[len(head):]
        return key

    def _should_sanitize(self, name):
        if name in self.sanitize_exclude:
            return False
        lowered = name.lower()
        return not any(marker in lowered for marker in _NEVER_SANITIZE)

    def _sanitize_data(self, data):
        """Return a mutable copy of ``data`` with every text value sanitised.

        Works on both QueryDict (a real request) and plain dict (tests, and
        forms constructed programmatically), preserving multi-value fields.
        """
        try:
            cleaned = data.copy()
        except AttributeError:
            return data

        is_query_dict = hasattr(cleaned, 'setlist')
        if is_query_dict:
            cleaned.mutable = True

        for name in list(cleaned.keys()):
            field = self._field_name(name)
            if not self._should_sanitize(field):
                continue
            collapse = field in self.sanitize_collapse_whitespace

            if is_query_dict:
                values = [
                    self._sanitize_value(v, collapse) for v in cleaned.getlist(name)
                ]
                cleaned.setlist(name, values)
            else:
                value = cleaned[name]
                if isinstance(value, (list, tuple)):
                    cleaned[name] = [self._sanitize_value(v, collapse) for v in value]
                else:
                    cleaned[name] = self._sanitize_value(value, collapse)

        return cleaned

    def _sanitize_value(self, value, collapse):
        if not isinstance(value, str):
            return value
        return sanitize_text(value, collapse_whitespace=collapse)[:self.sanitize_max_length]


class SanitizedForm(SanitizedFormMixin, forms.Form):
    """Plain Form with the sanitisation pass already mounted."""


class SanitizedModelForm(SanitizedFormMixin, forms.ModelForm):
    """ModelForm with the sanitisation pass already mounted."""
