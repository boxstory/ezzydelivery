# Purpose: Single source of truth for what a business that is not in good standing may not do.
# Used by: orders/views.py, business/views.py, ezzy_api (auth + webhooks), orders/tasks.py
# Notes: Both suspension and awaiting-approval are read-only, not a lockout — reads stay
#        open, writes are refused. Staff sessions are never gated here; only client
#        sessions, API keys and webhooks.

import logging
from functools import wraps

from django.contrib import messages
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect

logger = logging.getLogger(__name__)


# A deliberate staff suspension. Kept narrow on purpose: ezzy_api, orders/tasks.py
# and the client banner all read "suspended" specifically and must not start
# reporting an unapproved new signup as a suspended account.
SUSPENDED_STATUSES = ('suspended',)

# Which statuses may not write at all. 'pending' is the default for every new
# signup, and until staff verify the owner the account is not cleared to trade —
# it may finish onboarding and look around, nothing more. 'inactive' stays out:
# it is a soft archive for accounts that were already approved once, and moving
# it here would silently freeze old clients staff had deliberately parked.
WRITE_BLOCKED_STATUSES = ('suspended', 'pending')

SUSPENSION_MESSAGE = (
    'This business account is suspended. Please contact EzzyDelivery support.'
)

PENDING_APPROVAL_MESSAGE = (
    'This business account is awaiting staff approval. You can finish setting up '
    'your profile, but orders cannot be created until EzzyDelivery approves the account.'
)

# Snake_case reason codes, matching the house pattern in delivery/services/pickup.py:
# the service layer returns a code, the view layer owns the human sentence.
REFUSAL_CODE = 'business_suspended'
PENDING_REFUSAL_CODE = 'business_pending_approval'

# reason code -> human sentence, so a caller only ever carries the code around.
REFUSAL_MESSAGES = {
    REFUSAL_CODE: SUSPENSION_MESSAGE,
    PENDING_REFUSAL_CODE: PENDING_APPROVAL_MESSAGE,
}


def is_business_suspended(business):
    """True when this business is under a staff suspension."""
    if not business:
        return False
    return getattr(business, 'business_status', None) in SUSPENDED_STATUSES


def is_business_pending_approval(business):
    """True when this business has never been approved by staff."""
    if not business:
        return False
    return getattr(business, 'business_status', None) == 'pending'


def is_business_write_blocked(business):
    """True when this business may not perform writes, for any reason."""
    if not business:
        return False
    return getattr(business, 'business_status', None) in WRITE_BLOCKED_STATUSES


def write_refusal_code(business):
    """Which reason code applies to this business, or None when writes are allowed."""
    if is_business_suspended(business):
        return REFUSAL_CODE
    if is_business_pending_approval(business):
        return PENDING_REFUSAL_CODE
    return None


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


def suspended_deny(request, reason=REFUSAL_CODE):
    """
    Refuse a write, in whatever shape this caller understands.

    `reason` is one of the REFUSAL_MESSAGES keys and picks the sentence; it
    defaults to suspension so the existing callers keep their wording.

    HTMX gets 200 with an inline alert on purpose: the htmx:responseError handler
    in business_dashboard_base.html navigates the browser to the failing path, and
    these endpoints are POST-only, so a 4xx would render a 405 page.
    """
    message = REFUSAL_MESSAGES.get(reason, SUSPENSION_MESSAGE)

    if request.headers.get('HX-Request'):
        return HttpResponse(
            '<div class="alert alert-danger py-2 small mb-0">'
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

    messages.error(request, message)
    return redirect('business:business_dashboard')


def business_active_required(view_func):
    """
    Refuse the view when the caller's business may not write — because staff
    suspended it, or because staff have not approved it yet.

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
        reason = write_refusal_code(business)
        if reason:
            logger.warning(
                "Business %s blocked from %s (%s)",
                getattr(business, 'business_id', '?'), view_func.__name__, reason,
            )
            return suspended_deny(request, reason)

        return view_func(request, *args, **kwargs)

    return wrapper
