"""
Purpose: XSS-safe JSON serialisation for payloads embedded inside inline <script> blocks.
Used by: any view building a `*_json` context variable rendered with {{ var }} / {{ var|safe }}.
Notes: json.dumps does NOT escape < > &, so a stored value containing "</script>" breaks out of
       the script block. This escapes the same three characters Django's own |json_script filter
       does, and returns a SafeString so the template needs no change.
"""
import json

from django.core.serializers.json import DjangoJSONEncoder
from django.utils.safestring import SafeString, mark_safe

# Identical to django.utils.html._json_script_escapes — the three characters that
# can terminate or reopen a <script> element from inside a JSON string literal.
_SCRIPT_ESCAPES = {
    ord('<'): '\\u003C',
    ord('>'): '\\u003E',
    ord('&'): '\\u0026',
}


def safe_json(value, encoder=DjangoJSONEncoder, **dumps_kwargs):
    """Serialise ``value`` to JSON that is safe to inline in a <script> block.

    Drop-in replacement for ``json.dumps`` at any call site whose result is
    rendered into a template. Returns a SafeString, so ``{{ var }}`` emits it
    verbatim and an existing ``{{ var|safe }}`` keeps working unchanged.

    ``ensure_ascii`` stays at its default True, which also escapes U+2028 and
    U+2029 — the two whitespace characters that terminate a JS statement.
    """
    dumps_kwargs.setdefault('cls', encoder)
    return mark_safe(json.dumps(value, **dumps_kwargs).translate(_SCRIPT_ESCAPES))


def escape_json_string(raw):
    """Apply the script escapes to an already-serialised JSON string.

    For the cases where the JSON arrives pre-rendered (a model TextField holding
    a JSON blob, a third-party payload) and re-encoding it would be wasteful or
    lossy. Returns a SafeString.
    """
    if raw is None:
        return mark_safe('null')
    if isinstance(raw, SafeString):
        raw = str.__str__(raw)
    return mark_safe(str(raw).translate(_SCRIPT_ESCAPES))
