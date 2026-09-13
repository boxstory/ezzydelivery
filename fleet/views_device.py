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

from urllib.parse import quote

from fleet.device_service import (
    SESSION_PENDING_DEVICE, driver_phone, mask_phone, send_device_code,
    verify_device_code,
)
from fleet.models import Driver, DriverDevice

# Driver-side support line (same number the fleet PWA help page uses).
OPS_WHATSAPP = '97466124545'

logger = logging.getLogger(__name__)


def _pending_device(request):
    """The device this session is waiting on, or None if nothing is pending."""
    device_id = request.session.get(SESSION_PENDING_DEVICE)
    if not device_id:
        return None
    return DriverDevice.objects.filter(
        pk=device_id, user=request.user, status=DriverDevice.STATUS_PENDING
    ).first()



def _no_store(response):
    """Keep a gate response out of the browser cache — see the middleware's note."""
    response['Cache-Control'] = 'no-store'
    return response


def _ops_release_link(user, device):
    """A one-tap WhatsApp link to ops, pre-filled with what they need to act.

    Without this the page told a locked-out driver that "operations can release
    this device" and then gave them no way to reach operations — so the gate
    read as a broken login rather than a lock with a way out. It matters most
    for the driver whose code goes to a WhatsApp number they no longer carry:
    the code button cannot help them, and this is their only route.
    """
    driver = Driver.objects.filter(user=user).order_by('-driver_id').first()
    name = (user.get_full_name() or user.get_username() or '').strip()
    parts = ['Hi, I cannot confirm my device on EzzyDriver.']
    if name:
        parts.append(f'Name: {name}')
    if driver:
        parts.append(f'Driver ID: {driver.pk}')
    if device and device.label:
        parts.append(f'Device: {device.label}')
    parts.append('Please release my device.')
    return f'https://wa.me/{OPS_WHATSAPP}?text={quote(chr(10).join(parts))}'


@login_required
def device_verify(request):
    """Confirm a new device with the code sent to the driver's WhatsApp."""
    device = _pending_device(request)
    if not device:
        # Already cleared — by the code, or by ops releasing it. no-store because
        # this is the return leg of the gate/dashboard pair: a cached copy lets the
        # browser loop between the two 302s on its own. See
        # DriverDeviceMiddleware._no_store.
        request.session.pop(SESSION_PENDING_DEVICE, None)
        return _no_store(redirect('fleet:fleet_dashboard'))

    if request.method == 'POST':
        ok, message = verify_device_code(device, request.POST.get('code'))
        if ok:
            request.session.pop(SESSION_PENDING_DEVICE, None)
            messages.success(request, 'Device confirmed. Welcome back.')
            return _no_store(redirect('fleet:fleet_dashboard'))
        messages.error(request, message)
        return _no_store(redirect('fleet:device_verify'))

    phone = driver_phone(request.user)
    return _no_store(render(request, 'fleet/device_verify.html', {
        'device': device,
        'masked_phone': mask_phone(phone),
        'has_phone': bool(phone),
        'code_sent': device.otp_sent_at is not None,
        'ops_release_url': _ops_release_link(request.user, device),
    }))


@login_required
def device_send_code(request):
    """Send or resend the confirmation code."""
    if request.method != 'POST':
        return redirect('fleet:device_verify')

    device = _pending_device(request)
    if not device:
        return _no_store(redirect('fleet:fleet_dashboard'))

    ok, message = send_device_code(device)
    if ok:
        messages.success(request, message)
    else:
        messages.error(request, message)
    return _no_store(redirect('fleet:device_verify'))
