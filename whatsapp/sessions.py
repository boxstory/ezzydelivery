# Purpose: Single source of truth for resolving which WAHA session (= which of our WhatsApp numbers) a request, cron, or send belongs to.
# Used by: whatsapp.wa_chats_view, whatsapp.wa_dashboard_view, whatsapp.waha_views, whatsapp.contacts, whatsapp.tasks, workforce.crm_views, core.order_notifications.
# Notes: A "session" is a WAHA session name, NOT an Evolution instance_name. The mapping number->session lives on core.WhatsAppInstance.waha_session; section->number lives on core.WhatsAppSenderRoute.

import logging
import re

import requests
from django.conf import settings
from django.core.cache import cache
from django.utils.html import escape

logger = logging.getLogger(__name__)

# WAHA's own constraint (structures/sessions.dto.js): alphanumeric, hyphen,
# underscore. Enforced here because the session name is interpolated into WAHA
# URL paths — an unvalidated value would be a path-traversal vector.
_SESSION_RE = re.compile(r'^[a-zA-Z0-9_-]{1,64}$')

_SESSION_LIST_CACHE_KEY = 'waha_session_list_v1'
_SESSION_LIST_TTL = 30
_SESSION_NUMBER_CACHE_KEY = 'waha_session_numbers_v1'
_SESSION_NUMBER_TTL = 300


def default_session():
    return getattr(settings, 'WAHA_DEFAULT_SESSION', 'default') or 'default'


def is_valid(value):
    """Strict name check — no fallback.

    normalize() below deliberately coerces junk to the default session, which is
    right for read paths but catastrophic for a write path: a malformed name
    would silently stop/delete the DEFAULT session instead of erroring. Control
    operations use this instead.
    """
    return isinstance(value, str) and bool(_SESSION_RE.match(value.strip()))


def normalize(value):
    """Coerce any caller-supplied session name to a safe one.

    Anything blank, malformed, or non-string falls back to the default session
    rather than raising — every call site here is a read path that should keep
    working rather than 500 on a stray query param.
    """
    if not isinstance(value, str):
        return default_session()
    value = value.strip()
    if not value or not _SESSION_RE.match(value):
        return default_session()
    return value


def from_request(request):
    """Session for an ops-UI request: ?session=<name>, else the default."""
    return normalize(request.GET.get('session'))


def for_instance(instance):
    """WAHA session for a core.WhatsAppInstance (None/blank -> default).

    Guards against the classic mix-up: instance_name is the *Evolution* handle
    and is never a valid WAHA session, so only waha_session is consulted.
    """
    if instance is None:
        return default_session()
    return normalize(getattr(instance, 'waha_session', '') or '')


def for_section(section):
    """WAHA session the given WhatsAppSenderRoute section sends from.

    Reuses core.whatsapp_utils.get_route_instance so section->number routing
    stays defined in exactly one place (the Auto Triggers page).
    """
    try:
        from core.whatsapp_utils import get_route_instance
        return for_instance(get_route_instance(section))
    except Exception:
        logger.exception('waha: route lookup failed for section %s', section)
        return default_session()


def list_sessions(timeout=4):
    """Live sessions from WAHA as [{'name', 'status', 'phone', 'push_name'}].

    Cached 30s — the ops UIs call this on every page load to build the session
    tab strip. Returns a single synthetic default entry if WAHA is unreachable
    so the UI degrades to today's single-session behaviour instead of blanking.
    """
    cached = cache.get(_SESSION_LIST_CACHE_KEY)
    if isinstance(cached, list):
        return cached

    fallback = [{'name': default_session(), 'status': 'UNKNOWN', 'phone': '', 'push_name': ''}]
    base = (getattr(settings, 'WAHA_BASE_URL', '') or '').rstrip('/')
    api_key = getattr(settings, 'WAHA_API_KEY', '') or ''
    if not base or not api_key:
        return fallback

    try:
        resp = requests.get(
            f'{base}/api/sessions',
            headers={'X-Api-Key': api_key},
            timeout=timeout,
        )
        if not (200 <= resp.status_code < 300):
            return fallback
        body = resp.json()
    except (requests.exceptions.RequestException, ValueError) as e:
        logger.warning('waha session list failed: %s', e)
        return fallback

    if not isinstance(body, list):
        return fallback

    out = []
    for row in body:
        if not isinstance(row, dict):
            continue
        name = row.get('name')
        if not isinstance(name, str) or not _SESSION_RE.match(name):
            continue
        me = row.get('me') if isinstance(row.get('me'), dict) else {}
        out.append({
            'name': name,
            'status': row.get('status') or 'UNKNOWN',
            'phone': str(me.get('id') or '').split('@', 1)[0],
            'push_name': me.get('pushName') or '',
        })

    if not out:
        return fallback
    out.sort(key=lambda s: (s['name'] != default_session(), s['name']))
    cache.set(_SESSION_LIST_CACHE_KEY, out, _SESSION_LIST_TTL)
    return out


def invalidate_cache():
    """Drop the cached session list + sender-number map.

    Called after every control() write so the ops UI redraws from WAHA instead
    of showing the pre-change state for up to 30s and reading as "nothing
    happened".
    """
    cache.delete(_SESSION_LIST_CACHE_KEY)
    cache.delete(_SESSION_NUMBER_CACHE_KEY)


# WAHA 2026.x session control. The legacy body-style routes
# (POST /api/sessions/stop {name}) still exist but are deprecated; the
# per-name paths below are the current contract.
_CONTROL_ROUTES = {
    'start':   ('POST',   '/api/sessions/{name}/start'),
    'stop':    ('POST',   '/api/sessions/{name}/stop'),
    'restart': ('POST',   '/api/sessions/{name}/restart'),
    'logout':  ('POST',   '/api/sessions/{name}/logout'),
    'delete':  ('DELETE', '/api/sessions/{name}'),
}


def control(action, name, timeout=20):
    """Run a session control action against WAHA. Returns (ok, error).

    `error` is a short human-readable string on failure and '' on success, so
    the caller can put it straight into a Django message.

    Deliberately refuses a name that fails is_valid() rather than normalising
    it — see is_valid(). The name is interpolated into the URL path, so this
    is also the path-traversal guard.
    """
    if action not in _CONTROL_ROUTES:
        return False, f'Unknown action "{action}".'
    if not is_valid(name):
        return False, 'Invalid session name.'
    name = name.strip()

    base = (getattr(settings, 'WAHA_BASE_URL', '') or '').rstrip('/')
    api_key = getattr(settings, 'WAHA_API_KEY', '') or ''
    if not base or not api_key:
        return False, 'WAHA is not configured (WAHA_BASE_URL / WAHA_API_KEY).'

    method, path = _CONTROL_ROUTES[action]
    try:
        resp = requests.request(
            method,
            f'{base}{path.format(name=name)}',
            headers={'X-Api-Key': api_key, 'Content-Type': 'application/json'},
            timeout=timeout,
        )
    except requests.exceptions.RequestException as e:
        logger.warning('waha %s(%s) failed: %s', action, name, e)
        return False, f'WAHA unreachable: {e}'

    if 200 <= resp.status_code < 300:
        invalidate_cache()
        return True, ''

    detail = ''
    try:
        body = resp.json()
        if isinstance(body, dict):
            detail = str(body.get('message') or body.get('error') or '')
    except ValueError:
        detail = (resp.text or '')[:200]
    logger.warning('waha %s(%s) -> HTTP %s %s', action, name, resp.status_code, detail)
    return False, f'WAHA returned HTTP {resp.status_code}{": " + detail if detail else ""}'


def create_session(name, start=True, timeout=20):
    """Create a new WAHA session. Returns (ok, error).

    Separate from control() because it POSTs to the collection with a body
    rather than to a per-name path, and because it is the one action that must
    reject a name WAHA already has (WAHA answers 422, which reads as a generic
    failure otherwise).
    """
    if not is_valid(name):
        return False, 'Session name must be letters, numbers, hyphen or underscore (max 64).'
    name = name.strip()
    if any(s['name'] == name for s in list_sessions()):
        return False, f'A session named "{name}" already exists.'

    base = (getattr(settings, 'WAHA_BASE_URL', '') or '').rstrip('/')
    api_key = getattr(settings, 'WAHA_API_KEY', '') or ''
    if not base or not api_key:
        return False, 'WAHA is not configured (WAHA_BASE_URL / WAHA_API_KEY).'

    try:
        resp = requests.post(
            f'{base}/api/sessions',
            headers={'X-Api-Key': api_key, 'Content-Type': 'application/json'},
            json={'name': name, 'start': bool(start)},
            timeout=timeout,
        )
    except requests.exceptions.RequestException as e:
        logger.warning('waha create(%s) failed: %s', name, e)
        return False, f'WAHA unreachable: {e}'

    if 200 <= resp.status_code < 300:
        invalidate_cache()
        return True, ''

    detail = ''
    try:
        body = resp.json()
        if isinstance(body, dict):
            detail = str(body.get('message') or body.get('error') or '')
    except ValueError:
        detail = (resp.text or '')[:200]
    logger.warning('waha create(%s) -> HTTP %s %s', name, resp.status_code, detail)
    return False, f'WAHA returned HTTP {resp.status_code}{": " + detail if detail else ""}'


def render_tabs(active, base_path, always=False, add_button=False):
    """Tab strip HTML linking to <base_path>?session=<name>.

    Shared by the wa-chats and wa-dashboard ops pages — both style the same
    `.wa-sess*` classes in their own palette.

    always=False hides the strip below two sessions, so a single-number install
    renders exactly as before. The dashboard passes always=True + add_button=True
    because that is where a *new* number gets linked — hiding the control until a
    second session exists would make it impossible to create the second session.
    """
    rows = list_sessions()
    if len(rows) < 2 and not always:
        return ''
    parts = ['<nav class="wa-sess">']
    for s in rows:
        parts.append(
            '<a class="wa-sess__tab{on}" href="{href}" title="{title}">'
            '<span class="wa-sess__name"><span class="{dot}"></span>{label}</span>'
            '<span class="wa-sess__num">{num}</span></a>'.format(
                on=' wa-sess__tab--on' if s['name'] == active else '',
                href=escape(f'{base_path}?session={s["name"]}'),
                title=escape(f'{s["name"]} — {s["status"]}'),
                dot='wa-sess__dot wa-sess__dot--on' if s['status'] == 'WORKING' else 'wa-sess__dot',
                label=escape(s['push_name'] or s['name']),
                num=escape(s['phone'] or s['name']),
            )
        )
    if add_button:
        parts.append(
            '<button type="button" class="wa-sess__tab wa-sess__tab--add" id="wa-add-session" '
            'title="Link another WhatsApp number as a new WAHA session">'
            '<span class="wa-sess__name">+ Add number</span>'
            '<span class="wa-sess__num">new session</span></button>'
        )
    parts.append('</nav>')
    return ''.join(parts)


def section_routes():
    """Which platform section sends from which number.

    Read-only view of core.WhatsAppSenderRoute for the ops dashboard — the
    editable version lives on /workforce/auto-triggers/ (Django-auth, staff
    gated); this page is only htpasswd-gated, so it shows but never writes.

    Returns [{'section', 'label', 'session', 'instance_label', 'phone',
    'enabled', 'mapped', 'status', 'live'}] covering every section, including
    ones with no route row yet.

    Two separate "is this actually going to work" checks, because each fails
    differently and silently:
      mapped — the route points at an instance whose `waha_session` is set. If
               blank, Evolution routes to that number but the WAHA send falls
               back to the default session.
      live   — that session is WORKING. A session that merely *exists* can be
               sitting on the QR screen with no device attached; calling it
               connected claims a number is live when it isn't.
    """
    status_by_session = {s['name']: s['status'] for s in list_sessions()}
    try:
        from core.models import WhatsAppSenderRoute
    except Exception:
        logger.exception('waha: section route model unavailable')
        return []

    configured = {}
    try:
        for r in WhatsAppSenderRoute.objects.select_related('instance'):
            configured[r.section] = r
    except Exception:
        logger.exception('waha: section route lookup failed')
        return []

    out = []
    for section, label in WhatsAppSenderRoute.SECTION_CHOICES:
        route = configured.get(section)
        inst = route.instance if route else None
        # A disabled route or a missing instance both mean "unrestricted" —
        # the send falls through to the default session.
        enabled = bool(route and route.is_enabled and inst)
        # Blank waha_session = routed on the Evolution side only; WAHA sends
        # still leave from the default session.
        mapped = enabled and bool((getattr(inst, 'waha_session', '') or '').strip())
        session = for_instance(inst) if enabled else default_session()
        status = status_by_session.get(session, '')
        out.append({
            'section': section,
            'label': label,
            'session': session,
            'instance_label': (inst.label if inst else '') if enabled else '',
            'phone': ''.join(ch for ch in ((inst.phone_number or '') if inst else '') if ch.isdigit()),
            'enabled': enabled,
            'mapped': mapped,
            'status': status,
            # Unknown status (WAHA unreachable) is not treated as dead — don't
            # cry wolf over a transient outage.
            'live': status in ('WORKING', ''),
        })
    return out


def sender_number(session):
    """Our own number for a session, as bare digits — for outbound log rows.

    Prefers the configured core.WhatsAppInstance mapping (works even when WAHA
    is down), then the live session's me.id. Falls back to WAHA_DEFAULT_FROM so
    existing rows keep their current shape when nothing is configured.
    """
    session = normalize(session)
    mapping = cache.get(_SESSION_NUMBER_CACHE_KEY)
    if not isinstance(mapping, dict):
        mapping = {}
        try:
            from core.models import WhatsAppInstance
            for inst in WhatsAppInstance.objects.exclude(waha_session=''):
                digits = ''.join(ch for ch in (inst.phone_number or '') if ch.isdigit())
                if digits:
                    mapping[normalize(inst.waha_session)] = digits
        except Exception:
            logger.exception('waha: sender-number map build failed')
        for s in list_sessions():
            if s['phone'] and s['name'] not in mapping:
                mapping[s['name']] = s['phone']
        cache.set(_SESSION_NUMBER_CACHE_KEY, mapping, _SESSION_NUMBER_TTL)
    return mapping.get(session) or (getattr(settings, 'WAHA_DEFAULT_FROM', '') or '')
