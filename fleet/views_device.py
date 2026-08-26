"""
Purpose: The gate an unrecognised driver device is held at — send and check the
         WhatsApp confirmation code that releases it.
Used by: fleet/urls.py (fleet:device_verify, fleet:device_send_code)
Notes:   Reachable while the session is pending; DriverDeviceMiddleware lets these
         paths through and redirects everything else here.
"""
import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from fleet.device_service import (
    SESSION_PENDING_DEVICE, driver_phone, mask_phone, send_device_code,
    verify_device_code,
)
from fleet.models import DriverDevice

logger = logging.getLogger(__name__)


def _pending_device(request):
    """The device this session is waiting on, or None if nothing is pending."""
    device_id = request.session.get(SESSION_PENDING_DEVICE)
    if not device_id:
        return None
    return DriverDevice.objects.filter(
        pk=device_id, user=request.user, status=DriverDevice.STATUS_PENDING
    ).first()


@login_required
def device_verify(request):
    """Confirm a new device with the code sent to the driver's WhatsApp."""
    device = _pending_device(request)
    if not device:
        # Already cleared — by the code, or by ops releasing it.
        request.session.pop(SESSION_PENDING_DEVICE, None)
        return redirect('fleet:fleet_dashboard')

    if request.method == 'POST':
        ok, message = verify_device_code(device, request.POST.get('code'))
        if ok:
            request.session.pop(SESSION_PENDING_DEVICE, None)
            messages.success(request, 'Device confirmed. Welcome back.')
            return redirect('fleet:fleet_dashboard')
        messages.error(request, message)
        return redirect('fleet:device_verify')

    return render(request, 'fleet/device_verify.html', {
        'device': device,
        'masked_phone': mask_phone(driver_phone(request.user)),
        'has_phone': bool(driver_phone(request.user)),
        'code_sent': device.otp_sent_at is not None,
    })


@login_required
def device_send_code(request):
    """Send or resend the confirmation code."""
    if request.method != 'POST':
        return redirect('fleet:device_verify')

    device = _pending_device(request)
    if not device:
        return redirect('fleet:fleet_dashboard')

    ok, message = send_device_code(device)
    if ok:
        messages.success(request, message)
    else:
        messages.error(request, message)
    return redirect('fleet:device_verify')
