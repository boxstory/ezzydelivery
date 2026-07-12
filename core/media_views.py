# Purpose: Authenticated serving of sensitive uploaded media (labels, PODs, documents).
# Used by: ezzydelivery/urls.py protected-media route; nginx proxies matching /media/ prefixes here.
# Notes: Authorizes by path, then hands the file to nginx via X-Accel-Redirect (internal
#        location /__protected_media__/). Django never streams the bytes itself.

import mimetypes
import os

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponse, HttpResponseForbidden

from core.context_processors import get_cached_business

# Path prefixes under MEDIA_ROOT that must never be served without an auth check.
# Keep in sync with the nginx regex that routes these to Django.
PROTECTED_PREFIXES = (
    'shipping_labels/',      # customer name/address/phone/COD
    'delivery_proofs/',      # proof-of-delivery photos/signatures
    'tasks/',                # tasks/<id>/documents/ — POD + uploaded docs
    'orders/',               # orders/<id>/documents/
    'api_keys/',             # api_keys/<business_id>/
    'core/driver/',          # core/driver/<id>/documents/ — ID/license
)

INTERNAL_LOCATION = '/__protected_media__/'


def _profile_is_staff(user):
    if user.is_staff:
        return True
    profile = getattr(user, 'profile', None)
    return bool(profile and (profile.is_staff or getattr(profile, 'is_superadmin', False)))


def _get_driver(user):
    from fleet.models import Driver
    return Driver.objects.filter(user=user).first()


def _authorized(request, path):
    """Return True if request.user may read the media file at `path` (relative to MEDIA_ROOT)."""
    user = request.user

    # Staff and superadmins can read any uploaded document.
    if _profile_is_staff(user):
        return True

    parts = path.split('/')
    kind = parts[0]
    business = get_cached_business(request)

    if kind == 'shipping_labels':
        # shipping_labels/<business_code>/<file>
        return bool(len(parts) >= 2 and business and str(business.business_code) == parts[1])

    if kind == 'delivery_proofs':
        # delivery_proofs/<business_code>/<file> — owning business only (drivers upload via API)
        return bool(len(parts) >= 2 and business and str(business.business_code) == parts[1])

    if kind == 'api_keys':
        # api_keys/<business_id>/<file>
        return bool(len(parts) >= 2 and business and str(business.business_id) == parts[1])

    if kind == 'orders':
        # orders/<order_id>/documents/<file>
        if len(parts) >= 2 and parts[1].isdigit() and business:
            from orders.models import Order
            return Order.objects.filter(id=parts[1], business=business).exists()
        return False

    if kind == 'tasks':
        # tasks/<task_id>/documents/<file> — owning business or the assigned driver
        if len(parts) >= 2 and parts[1].isdigit():
            from delivery.models import DeliveryTask
            task = DeliveryTask.objects.filter(id=parts[1]).select_related('order', 'driver').first()
            if task:
                if business and task.order and task.order.business_id == business.business_id:
                    return True
                driver = _get_driver(user)
                if driver and task.driver_id == driver.driver_id:
                    return True
        return False

    if kind == 'core':
        # core/driver/<driver_id>/documents/<file> — that driver only
        if len(parts) >= 3 and parts[1] == 'driver' and parts[2].isdigit():
            driver = _get_driver(user)
            return bool(driver and str(driver.driver_id) == parts[2])
        return False

    return False


@login_required
def serve_protected_media(request, filepath):
    """Authorize then delegate file streaming to nginx via X-Accel-Redirect."""
    # Reject path traversal before touching the filesystem.
    clean = os.path.normpath(filepath).lstrip('/')
    if clean.startswith('..') or '..' in clean.split('/'):
        raise Http404()

    # Only paths under a known-sensitive prefix are served here; anything else 404s
    # (public media is served directly by nginx and never reaches this view).
    if not clean.startswith(PROTECTED_PREFIXES):
        raise Http404()

    full_path = os.path.join(settings.MEDIA_ROOT, clean)
    if not os.path.isfile(full_path):
        raise Http404()

    if not _authorized(request, clean):
        return HttpResponseForbidden('You do not have permission to access this file.')

    response = HttpResponse(status=200)
    content_type, _enc = mimetypes.guess_type(full_path)
    response['Content-Type'] = content_type or 'application/octet-stream'
    # nginx replaces the (empty) body with the file at this internal location.
    response['X-Accel-Redirect'] = INTERNAL_LOCATION + clean
    return response
