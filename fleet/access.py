# Purpose: Single source of truth for whether a driver is cleared to work — the permission that sits on top of driver_status.
# Used by: fleet/views.py, fleet/context_processors.py, delivery/views.py, delivery/selectors.py, ezzy_api/views.py, workforce/views.py
# Notes: Approval means the documents check out; this means ops put the driver on the road. Both must be true. Never re-inline
#        `driver.dashboard_access_enabled` at a call site — ask has_dashboard_access() so the two conditions cannot drift apart.

import logging
from functools import wraps

from django.contrib import messages
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect

logger = logging.getLogger(__name__)


# The one status that means the account itself is in good standing. Kept here as a
# name rather than a literal so the rest of this module reads as one rule.
APPROVED_STATUS = 'approved'

# Snake_case reason codes, matching the house pattern in business/suspension.py and
# delivery/services/pickup.py: the service layer returns a code, the view layer owns
# the human sentence.
NOT_APPROVED_CODE = 'driver_not_approved'
NOT_GRANTED_CODE = 'driver_dashboard_not_granted'

NOT_APPROVED_MESSAGE = (
    'Your driver account is not approved yet.'
)

NOT_GRANTED_MESSAGE = (
    'Your account is verified, but full app access has not been switched on yet. '
    'Browse the opportunities below and let us know what you can work.'
)

# reason code -> human sentence, so a caller only ever carries the code around.
REFUSAL_MESSAGES = {
    NOT_APPROVED_CODE: NOT_APPROVED_MESSAGE,
    NOT_GRANTED_CODE: NOT_GRANTED_MESSAGE,
}

# Where a driver who is not cleared to work gets sent. Everything reachable from
# here must stay outside driver_dashboard_required or the redirect loops.
FALLBACK_URL_NAME = 'fleet:opportunities'


def is_approved(driver):
    """True when this driver's account is in good standing."""
    if not driver:
        return False
    return getattr(driver, 'driver_status', None) == APPROVED_STATUS


def has_dashboard_access(driver):
    """True when this driver may take work: tasks, pickups, COD and earnings.

    Both conditions are required. An approved driver whose access ops have not
    switched on yet is onboarded, not working.
    """
    if not is_approved(driver):
        return False
    return bool(getattr(driver, 'dashboard_access_enabled', False))


def dashboard_refusal_code(driver):
    """Which reason code applies to this driver, or None when they may work."""
    if not is_approved(driver):
        return NOT_APPROVED_CODE
    if not getattr(driver, 'dashboard_access_enabled', False):
        return NOT_GRANTED_CODE
    return None


def resolve_driver(request):
    """The Driver behind this request, without spending an extra query.

    Prefers the per-request cache that core.context_processors.user_driver already
    fills for every /fleet/ page, then memoises its own lookup so a decorator and a
    context processor on the same request cost one query between them.
    """
    cached = getattr(request, '_cached_user_driver', None)
    if cached is not None:
        return cached

    if hasattr(request, '_fleet_access_driver'):
        return request._fleet_access_driver

    driver = None
    user = getattr(request, 'user', None)
    if user is not None and user.is_authenticated:
        from fleet.models import Driver
        driver = Driver.objects.filter(user_id=user.id).first()

    request._fleet_access_driver = driver
    return driver


def _no_store(response):
    """Stop a browser caching a gate redirect.

    The same trap DriverDeviceMiddleware hit (core/middleware.py:378): the gate and
    the page it protects point at each other, both as plain 302s, and a cached
    redirect lets the browser bounce between them without ever asking the server.
    """
    response['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    return response


def dashboard_deny(request, reason=NOT_GRANTED_CODE):
    """Refuse a driver who is not cleared to work, in whatever shape this caller understands.

    Mirrors business.suspension.suspended_deny. HTMX gets 200 with an inline alert on
    purpose: the fleet error handlers navigate to the failing path, and these endpoints
    are POST-only, so a 4xx would render a 405 page.
    """
    message = REFUSAL_MESSAGES.get(reason, NOT_GRANTED_MESSAGE)

    if request.headers.get('HX-Request'):
        return HttpResponse(
            '<div class="alert alert-warning py-2 small mb-0">'
            f'{message}</div>'
        )

    wants_json = (
        request.headers.get('x-requested-with') == 'XMLHttpRequest'
        or 'application/json' in request.headers.get('accept', '')
        or 'application/json' in (getattr(request, 'content_type', '') or '')
    )
    if wants_json:
        return JsonResponse(
            {'success': False, 'error': message, 'code': reason},
            status=403,
        )

    messages.info(request, message)
    return _no_store(redirect(FALLBACK_URL_NAME))


def api_driver_dashboard_required(view_func):
    """JSON-only twin of driver_dashboard_required, for the mobile/partner API.

    Place BELOW @api_driver_required. Always answers JSON: an API client does not
    reliably send an Accept header, so it must never be handed a redirect.

    Without this the PWA gate is decorative — the same work is reachable at
    /api/v1/driver/tasks/<id>/accept/.
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        driver = resolve_driver(request)
        reason = dashboard_refusal_code(driver)
        if reason:
            logger.warning(
                "Driver %s blocked from API %s (%s)",
                getattr(driver, 'driver_id', '?'), view_func.__name__, reason,
            )
            return JsonResponse(
                {'success': False, 'error': REFUSAL_MESSAGES[reason], 'code': reason},
                status=403,
            )
        return view_func(request, *args, **kwargs)

    return wrapper


def driver_dashboard_required(view_func):
    """Refuse the view when this driver is not cleared to work.

    Place BELOW @driver_required (closer to the def) so the role check runs first —
    a non-driver should be told they are not a driver, not that their access is pending.

    Staff are deliberately exempt: ops open driver screens to diagnose them, exactly as
    business_active_required exempts staff from the client suspension gate.
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        user = getattr(request, 'user', None)
        if user is not None and user.is_authenticated and user.is_staff:
            return view_func(request, *args, **kwargs)

        driver = resolve_driver(request)
        reason = dashboard_refusal_code(driver)
        if reason:
            logger.warning(
                "Driver %s blocked from %s (%s)",
                getattr(driver, 'driver_id', '?'), view_func.__name__, reason,
            )
            return dashboard_deny(request, reason)

        return view_func(request, *args, **kwargs)

    return wrapper
