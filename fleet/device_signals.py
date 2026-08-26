"""
Purpose: Bind a driver's login to the device it came from, enforcing one live device each.
Used by: fleet/apps.py (connected in FleetConfig.ready)
Notes:   Only approved drivers are touched — staff, clients and applicants still
         under review log in untouched.
"""
import logging

from django.contrib.auth.signals import user_logged_in
from django.dispatch import receiver

from fleet.device_service import bind_device, enforcement_enabled, is_enrolled_driver

logger = logging.getLogger(__name__)


@receiver(user_logged_in)
def bind_driver_device(sender, request, user, **kwargs):
    """Claim this device for the driver and retire whatever they used before."""
    if request is None or not enforcement_enabled() or not is_enrolled_driver(user):
        return
    try:
        bind_device(request, user)
    except Exception:
        # A failure here must not block the login itself; the driver simply
        # keeps the device they had.
        logger.exception('Device binding failed for user %s', getattr(user, 'pk', None))
