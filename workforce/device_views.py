"""
Purpose: Staff console for the one-device-per-driver rule — see which phone each driver
         is on, release a device when WhatsApp can't deliver a code, and revoke one.
Used by: workforce/urls.py (driver_devices, driver_device_release, driver_device_revoke)
Notes:   The switch history is the point: a driver whose account keeps hopping between
         two devices is sharing credentials, and that is visible here without digging.
"""
import logging

from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from core.decorators import staff_required
from fleet.device_service import activate_device, revoke_other_devices
from fleet.models import DriverDevice

logger = logging.getLogger(__name__)


@staff_required
def driver_devices(request):
    """Driver devices, newest activity first. Pending ones need a decision."""
    status = request.GET.get('status', 'pending')
    search = (request.GET.get('search') or '').strip()

    devices = DriverDevice.objects.select_related('user', 'approved_by')
    if status in dict(DriverDevice.STATUS_CHOICES):
        devices = devices.filter(status=status)
    if search:
        devices = devices.filter(
            Q(user__username__icontains=search)
            | Q(user__first_name__icontains=search)
            | Q(user__last_name__icontains=search)
            | Q(label__icontains=search)
            | Q(ip_address__icontains=search)
        )

    paginator = Paginator(devices, 25)
    page_obj = paginator.get_page(request.GET.get('page'))

    return render(request, 'workforce/driver_devices.html', {
        'page_obj': page_obj,
        'status': status,
        'search': search,
        'status_choices': DriverDevice.STATUS_CHOICES,
        'pending_count': DriverDevice.objects.filter(
            status=DriverDevice.STATUS_PENDING).count(),
    })


@staff_required
@require_POST
def driver_device_release(request, device_id):
    """Release a device without a WhatsApp code — the fallback when WAHA is down."""
    device = get_object_or_404(DriverDevice, pk=device_id)
    if device.status != DriverDevice.STATUS_PENDING:
        messages.warning(request, 'That device is not waiting for approval.')
        return redirect('workforce:driver_devices')

    activate_device(device, approved_by=request.user)
    logger.info('Device %s released for driver %s by staff %s',
                device.pk, device.user_id, request.user.pk)
    messages.success(
        request,
        f'Released {device.label or "device"} for {device.user}. '
        'They can use it as soon as they reload the app.'
    )
    return redirect('workforce:driver_devices')


@staff_required
@require_POST
def driver_device_revoke(request, device_id):
    """Kick a device off. The driver is signed out on its next request."""
    device = get_object_or_404(DriverDevice, pk=device_id)
    if device.status == DriverDevice.STATUS_REVOKED:
        messages.warning(request, 'That device is already revoked.')
        return redirect('workforce:driver_devices')

    from fleet.device_service import _flag_session_revoked
    _flag_session_revoked(device.session_key, DriverDevice.REVOKED_STAFF)
    device.status = DriverDevice.STATUS_REVOKED
    device.revoked_at = timezone.now()
    device.revoked_reason = DriverDevice.REVOKED_STAFF
    device.save(update_fields=['status', 'revoked_at', 'revoked_reason', 'last_seen_at'])

    logger.info('Device %s revoked for driver %s by staff %s',
                device.pk, device.user_id, request.user.pk)
    messages.success(request, f'Revoked {device.label or "device"} for {device.user}.')
    return redirect('workforce:driver_devices')
