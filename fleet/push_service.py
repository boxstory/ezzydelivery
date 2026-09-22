# Purpose: Send Web Push messages to a driver's registered devices and retire the addresses that have died.
# Used by: the workforce live map's "Request location" action; any future driver alert that must reach a closed app.
# Notes: A push can only wake the service worker, which has no geolocation — it buys the driver's attention,
#        never a fix. Chrome also refuses a push that shows no notification, so none of this is silent.

import json
import logging
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)

#: Title of the in-app row a location request leaves behind. Matched on to
#: dedupe repeat presses, so it is a constant rather than a literal.
_LOCATION_REQUEST_TITLE = 'Location requested'


def push_configured():
    """True when the server holds a VAPID keypair to sign pushes with."""
    return bool(
        getattr(settings, 'VAPID_PRIVATE_KEY', '')
        and getattr(settings, 'VAPID_PUBLIC_KEY', '')
    )


def public_key():
    """The key the browser needs at subscribe time. Safe to hand to the page."""
    return getattr(settings, 'VAPID_PUBLIC_KEY', '') or ''


def send_to_driver(driver, *, title, body, url='/fleet/dashboard/', tag=None,
                   require_interaction=False, data=None):
    """Push a notification to every live device this driver has registered.

    Returns a summary dict — ``sent``, ``failed``, ``retired``, ``devices`` and,
    when nothing could be attempted, a ``reason`` the caller can show staff.
    Never raises: a failed push is an operational fact, not an exception for the
    view above to handle.
    """
    from fleet.models import DriverPushSubscription

    summary = {'sent': 0, 'failed': 0, 'retired': 0, 'devices': 0, 'reason': ''}

    if not push_configured():
        summary['reason'] = 'Push is not configured on this server'
        return summary

    subs = list(DriverPushSubscription.active_for_driver(driver.pk))
    summary['devices'] = len(subs)
    if not subs:
        summary['reason'] = 'No device registered for notifications'
        return summary

    try:
        from pywebpush import WebPushException, webpush
    except ImportError:  # pragma: no cover - dependency is in requirements.txt
        logger.error('pywebpush is not installed — driver push disabled')
        summary['reason'] = 'Push library missing on this server'
        return summary

    payload = json.dumps({
        'title': title,
        'body': body,
        'url': url,
        'tag': tag or 'ezzy-driver',
        'requireInteraction': bool(require_interaction),
        'sentAt': timezone.now().isoformat(),
        'data': data or {},
    })

    private_key = getattr(settings, 'VAPID_PRIVATE_KEY', '')
    claim_email = getattr(settings, 'VAPID_CLAIM_EMAIL', '') or 'admin@ezzydelivery.qa'

    for sub in subs:
        try:
            webpush(
                subscription_info=sub.subscription_info,
                data=payload,
                vapid_private_key=private_key,
                # pywebpush mutates the claims dict (it stamps aud/exp onto it),
                # so each send gets its own copy — a shared one carries the first
                # endpoint's audience to every device after it and they all 401.
                vapid_claims={'sub': f'mailto:{claim_email}'},
                ttl=getattr(settings, 'PUSH_TTL_SECONDS', 600),
            )
        except WebPushException as exc:
            status = getattr(getattr(exc, 'response', None), 'status_code', None)
            # 404/410 mean the browser threw this address away — the app was
            # uninstalled, or site data cleared. Retrying it forever would make
            # every later send look like a fault.
            fatal = status in (404, 410)
            sub.note_failure(f'{status or "error"}: {exc}', fatal=fatal)
            summary['failed'] += 1
            if fatal:
                summary['retired'] += 1
            logger.warning('Push to driver %s failed (%s): %s', driver.pk, status, exc)
        except Exception as exc:  # network blip, DNS, malformed key
            sub.note_failure(str(exc))
            summary['failed'] += 1
            logger.warning('Push to driver %s errored: %s', driver.pk, exc)
        else:
            sub.note_success()
            summary['sent'] += 1

    if not summary['sent'] and not summary['reason']:
        summary['reason'] = (
            'Device no longer registered — ask the driver to reopen the app'
            if summary['retired'] else 'Push service rejected the message'
        )
    return summary


def request_location(driver, *, requested_by=None):
    """Ask a driver's phone to come back to the app and report a position.

    This is the whole of what a browser allows: the notification is the request,
    the driver's tap is what actually foregrounds the PWA, and the fix taken on
    load is what closes their open nav handoff. Nothing here reads GPS.
    """
    from fleet.models import DriverNotification

    who = ''
    if requested_by is not None:
        who = (requested_by.get_full_name() or requested_by.username or '').strip()

    body = 'Dispatch needs your current location. Tap to open the app.'
    summary = send_to_driver(
        driver,
        title='Where are you?',
        body=body,
        # The flag is what tells the app this open was asked for, so it takes a
        # fresh high-accuracy fix instead of waiting for the next duty cycle.
        url='/fleet/dashboard/?locreq=1',
        tag='ezzy-locreq',
        require_interaction=True,
        data={'kind': 'location_request'},
    )

    # Logged whether or not the push landed: the in-app list is what a driver
    # who had notifications switched off sees when they next open the app, and
    # it is the only record staff have that the request was made at all.
    #
    # Deduped, though. A send that fails does not start the caller's cooldown —
    # a transient push failure should be retryable at once — so an unreachable
    # driver would otherwise collect one row per press and open the app to a
    # screenful of the same sentence. One standing request is the whole message.
    window = timezone.now() - timedelta(
        seconds=getattr(settings, 'DRIVER_LOCATION_REQUEST_COOLDOWN', 120))
    already = DriverNotification.objects.filter(
        driver=driver,
        title=_LOCATION_REQUEST_TITLE,
        is_read=False,
        created_at__gte=window,
    ).exists()
    if not already:
        DriverNotification.objects.create(
            driver=driver,
            title=_LOCATION_REQUEST_TITLE,
            message=f'{who} asked for your current location.' if who else body,
            notification_type='alert',
        )
    return summary
