# Purpose: Single source of truth for what a suspended business may not do.
# Used by: orders/views.py, business/views.py, ezzy_api (auth + webhooks), orders/tasks.py
# Notes: Suspension is read-only, not a lockout — reads stay open, writes are refused.
#        Staff sessions are never gated here; only client sessions, API keys and webhooks.

import logging
from functools import wraps

from django.contrib import messages
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect

logger = logging.getLogger(__name__)


# Only a deliberate staff suspension blocks. 'pending' is the default for every
# new signup and 'inactive' is a soft archive, so neither may gate writes here.
SUSPENDED_STATUSES = ('suspended',)

SUSPENSION_MESSAGE = (
    'This business account is suspended. Please contact EzzyDelivery support.'
)

# Snake_case reason code, matching the house pattern in delivery/services/pickup.py:
# the service layer returns a code, the view layer owns the human sentence.
REFUSAL_CODE = 'business_suspended'


def is_business_suspended(business):
    """True when this business is under a staff suspension."""
    if not business:
        return False
    return getattr(business, 'business_status', None) in SUSPENDED_STATUSES


def resolve_business(request):
    """
    Find the business behind this request without spending an extra query.

    Prefers what the permission decorators already injected, then falls back to
    the per-request memoised lookup in core.context_processors.
    """
    business = getattr(request, 'current_business', None)
    if business:
        return business

    from core.context_processors import get_cached_business
    return get_cached_business(request)


def suspended_deny(request):
    """
    Refuse a write, in whatever shape this caller understands.

    HTMX gets 200 with an inline alert on purpose: the htmx:responseError handler
    in business_dashboard_base.html navigates the browser to the failing path, and
    these endpoints are POST-only, so a 4xx would render a 405 page.
    """
    if request.headers.get('HX-Request'):
        return HttpResponse(
            '<div class="alert alert-danger py-2 small mb-0">'
            f'{SUSPENSION_MESSAGE}</div>'
        )

    wants_json = (
        request.headers.get('x-requested-with') == 'XMLHttpRequest'
        or 'application/json' in request.headers.get('accept', '')
        or 'application/json' in (getattr(request, 'content_type', '') or '')
    )
    if wants_json:
        return JsonResponse(
            {'success': False, 'error': SUSPENSION_MESSAGE, 'code': REFUSAL_CODE},
            status=403,
        )

    messages.error(request, SUSPENSION_MESSAGE)
    return redirect('business:business_dashboard')


def business_active_required(view_func):
    """
    Refuse the view when the caller's business is suspended.

    Place BELOW @business_permission_required / @business_required (closer to the
    def) so business resolution has already run and request.current_business is set.

    Staff are deliberately exempt: they need to clean up data and settle held COD
    for suspended accounts.
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        user = getattr(request, 'user', None)
        if user is not None and user.is_authenticated and user.is_staff:
            return view_func(request, *args, **kwargs)

        business = resolve_business(request)
        if is_business_suspended(business):
            logger.warning(
                "Suspended business %s blocked from %s",
                getattr(business, 'business_id', '?'), view_func.__name__,
            )
            return suspended_deny(request)

        return view_func(request, *args, **kwargs)

    return wrapper
