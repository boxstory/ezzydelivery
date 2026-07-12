"""
Order Event Notifications
=========================
Sends WhatsApp notifications to customers at key order lifecycle events.
All functions are fire-and-forget — they log failures but never raise exceptions,
so a notification failure never blocks the main order flow.

All notifications are sent via the n8n webhook (same infrastructure as
address verification in core/whatsapp_utils.py).

Usage (called from delivery/signals.py):
    from core.order_notifications import notify_order_event
    notify_order_event('driver_assigned', task)
    notify_order_event('out_for_delivery', task)
    notify_order_event('delivered', task)
    notify_order_event('delivery_failed', task)
    notify_order_event('order_cancelled', order)
"""

import json
import logging
import requests
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)

# Map event names to human-readable labels (for logging)
EVENT_LABELS = {
    'driver_assigned':   'Driver Assigned',
    'out_for_delivery':  'Out for Delivery',
    'delivered':         'Delivered',
    'delivery_failed':   'Delivery Failed',
    'order_cancelled':   'Order Cancelled',
}

# Map lifecycle events to their AutoTriggerConfig key, so we can honour the
# per-trigger "Send from WhatsApp number" choice set on /workforce/auto-triggers/.
EVENT_TO_TRIGGER_KEY = {
    'driver_assigned':  'wa_driver_assigned',
    'out_for_delivery': 'wa_out_for_delivery',
    'delivered':        'wa_delivered',
    'delivery_failed':  'wa_delivery_failed',
    'order_cancelled':  'wa_order_cancelled',
}


def _resolve_trigger_config(event):
    """Return (WhatsAppInstance|None, channel_str) chosen for this event's trigger.

    instance None = default number; channel '' = decide by global config.
    """
    try:
        from core.models import AutoTriggerConfig
        key = EVENT_TO_TRIGGER_KEY.get(event)
        if not key:
            return None, ''
        cfg = (AutoTriggerConfig.objects
               .filter(trigger_key=key)
               .select_related('whatsapp_instance')
               .first())
        if not cfg:
            return None, ''
        return cfg.whatsapp_instance, (cfg.whatsapp_channel or '')
    except Exception:
        return None, ''


def notify_order_event(event, task=None, order=None):
    """
    Send a WhatsApp notification to the customer for a lifecycle event.

    Args:
        event (str): Event key — one of EVENT_LABELS keys.
        task (DeliveryTask|None): The delivery task (provides order + driver info).
        order (Order|None): Fallback if no task (e.g. for cancellation before task exists).
    """
    try:
        # Resolve order
        if task is not None:
            _order = task.order
        elif order is not None:
            _order = order
        else:
            logger.warning(f"notify_order_event({event}): no task or order provided")
            return

        if not _order:
            return

        # Check if business has an active trigger for this event
        from business.models import WhatsAppNotificationTrigger
        event_to_trigger = {
            'driver_assigned': 'assigned',
            'out_for_delivery': 'out_for_delivery',
            'delivered': 'delivered',
            'delivery_failed': 'failed',
        }
        trigger_status = event_to_trigger.get(event)
        if trigger_status and _order.business_id:
            trigger = WhatsAppNotificationTrigger.objects.filter(
                business_id=_order.business_id,
                trigger_status=trigger_status,
                is_active=True
            ).first()
            if not trigger:
                logger.debug(f"WhatsApp trigger not active for {event} on business {_order.business_id}")
                return  # Don't send if trigger is not active

        phone = _order.customer_phone
        if not phone:
            logger.debug(f"notify_order_event({event}): order {_order.order_number} has no customer_phone, skipping")
            return

        # Use custom message from trigger if set
        custom_msg = None
        if trigger_status and _order.business_id:
            trigger_obj = WhatsAppNotificationTrigger.objects.filter(
                business_id=_order.business_id,
                trigger_status=trigger_status,
                is_active=True
            ).first()
            if trigger_obj and trigger_obj.custom_message:
                try:
                    driver_name = ''
                    driver_phone_str = ''
                    if task and task.driver:
                        driver_name = str(task.driver)
                        driver_phone_str = task.driver.driver_phone or ''
                    custom_msg = trigger_obj.custom_message.format(
                        customer_name=_order.customer_name or '',
                        order_number=_order.order_number or '',
                        driver_name=driver_name,
                        driver_phone=driver_phone_str,
                    )
                except (KeyError, IndexError):
                    logger.warning(f"Custom message template error for business {_order.business_id}, event {event}")
                    custom_msg = None

        message = custom_msg or _build_message(event, _order, task)
        if not message:
            return

        # Per-trigger "Send from" number + "Send via" channel (from /workforce/auto-triggers/)
        sender_instance, sender_channel = _resolve_trigger_config(event)

        _send_whatsapp(phone, message, event, _order, instance=sender_instance, channel=sender_channel)

        # Also notify the business-configured extra phone for this trigger.
        # Falls back to the business's own WhatsApp number if no per-trigger override is set.
        extra_phone = ''
        if trigger_status and _order.business_id:
            extra_phone = (getattr(trigger, 'notification_phone', '') or '').strip()
            if not extra_phone:
                extra_phone = (getattr(_order.business, 'business_whatsapp', '') or '').strip()
        if extra_phone and extra_phone != phone:
            _send_whatsapp(extra_phone, message, event, _order, instance=sender_instance, channel=sender_channel)

    except Exception as e:
        logger.exception(f"notify_order_event({event}) failed unexpectedly: {e}")


# ---------------------------------------------------------------------------
# Message builders
# ---------------------------------------------------------------------------

def _build_message(event, order, task):
    """Build the WhatsApp message text for a given event."""
    name = order.customer_name or 'Customer'
    order_num = order.order_number

    if event == 'driver_assigned':
        driver_name = ''
        if task and task.driver and task.driver.user:
            driver_name = task.driver.user.get_full_name() or task.driver.driver_code
        cod_line = f"💰 COD to collect: *{order.cod_amount} QAR*\n" if order.cod_amount else ""
        return (
            f"🚚 *EZZY Delivery Update*\n\n"
            f"Hello {name},\n\n"
            f"Your order *{order_num}* has been assigned to a driver and will be picked up shortly.\n\n"
            f"{cod_line}"
            f"📦 Address: {order.customer_address}\n\n"
            f"We will notify you when your driver is on the way. Thank you! 😊"
        )

    elif event == 'out_for_delivery':
        driver_phone = ''
        if task and task.driver:
            driver_phone = task.driver.driver_phone or ''
        contact_line = f"📞 Driver contact: {driver_phone}\n" if driver_phone else ""
        cod_line = f"💰 Please have *{order.cod_amount} QAR* cash ready.\n" if order.cod_amount else ""
        return (
            f"🏃 *EZZY Delivery — Driver on the Way!*\n\n"
            f"Hello {name},\n\n"
            f"Your driver is now heading to your address for order *{order_num}*.\n\n"
            f"{cod_line}"
            f"{contact_line}"
            f"📍 Delivery address: {order.customer_address}\n\n"
            f"Please be available to receive your package. Thank you!"
        )

    elif event == 'delivered':
        cod_line = f"💵 COD collected: *{order.cod_amount} QAR*\n" if order.cod_amount else ""
        return (
            f"✅ *EZZY Delivery — Order Delivered!*\n\n"
            f"Hello {name},\n\n"
            f"Your order *{order_num}* has been successfully delivered.\n\n"
            f"{cod_line}"
            f"Thank you for choosing EZZY Delivery! 🚚\n\n"
            f"If you have any questions, please contact us."
        )

    elif event == 'delivery_failed':
        failure_reason = ''
        if task and task.failure_reason:
            display = dict(task.FAILURE_REASON_CHOICES).get(task.failure_reason, task.failure_reason)
            failure_reason = f"Reason: {display}\n"
        reschedule_line = ''
        if task and task.reschedule_date:
            reschedule_line = f"📅 Rescheduled for: *{task.reschedule_date.strftime('%d %b %Y')}*\n"
        return (
            f"⚠️ *EZZY Delivery — Delivery Attempt Unsuccessful*\n\n"
            f"Hello {name},\n\n"
            f"We were unable to deliver your order *{order_num}* today.\n\n"
            f"{failure_reason}"
            f"{reschedule_line}"
            f"Our team will contact you shortly to arrange a new delivery.\n\n"
            f"We apologise for the inconvenience. 🙏"
        )

    elif event == 'order_cancelled':
        reason_line = ''
        if order.cancellation_reason:
            display = dict(order.CANCELLATION_REASON_CHOICES).get(order.cancellation_reason, order.cancellation_reason)
            reason_line = f"Reason: {display}\n"
        return (
            f"❌ *EZZY Delivery — Order Cancelled*\n\n"
            f"Hello {name},\n\n"
            f"Your order *{order_num}* has been cancelled.\n\n"
            f"{reason_line}"
            f"If this was unexpected, please contact us and we will be happy to help.\n\n"
            f"Thank you for choosing EZZY Delivery."
        )

    logger.debug(f"_build_message: unknown event '{event}', no message built")
    return None


# ---------------------------------------------------------------------------
# Transport
# ---------------------------------------------------------------------------

def _send_whatsapp(phone, message, event, order, instance=None, channel=None):
    """Send the message via the chosen channel. Logs but never raises.

    instance: optional WhatsAppInstance chosen for this trigger ("Send from").
    channel:  explicit per-trigger channel ('evolution' | 'waha' | '' for auto).
              When blank, falls back to global config (WAHA if enabled, else n8n).
    """
    # Explicit per-trigger channel override
    if channel == 'evolution':
        return _send_whatsapp_via_evolution(phone, message, event, order, instance=instance)
    if channel == 'waha':
        return _send_whatsapp_via_waha(phone, message, event, order, instance=instance)

    # Auto: follow global config
    if getattr(settings, 'WAHA_ENABLED', False):
        return _send_whatsapp_via_waha(phone, message, event, order, instance=instance)

    n8n_url = getattr(settings, 'N8N_WHATSAPP_WEBHOOK_URL', None)
    if not n8n_url:
        logger.debug(f"WhatsApp notification skipped ({event}): N8N_WHATSAPP_WEBHOOK_URL not configured")
        return

    payload = {
        'phone': phone,
        'message': message.strip(),
        'type': f'order_{event}',
        'order_id': order.id,
        'order_number': order.order_number,
        'timestamp': timezone.now().isoformat(),
    }
    # Tell n8n which WhatsApp number to send from, when a per-trigger choice is set.
    if instance is not None:
        payload['from_instance'] = instance.instance_name or ''
        payload['from_number'] = instance.phone_number or ''

    headers = {'Content-Type': 'application/json', 'User-Agent': 'EZZY-Delivery/1.0'}

    # Optional HMAC signature
    secret = getattr(settings, 'N8N_WEBHOOK_SECRET_KEY', None)
    if secret:
        from core.whatsapp_utils import generate_webhook_signature
        headers['X-Webhook-Signature'] = generate_webhook_signature(payload, secret)

    try:
        response = requests.post(n8n_url, json=payload, headers=headers, timeout=8, verify=True)
        if response.status_code == 200:
            logger.info(f"WhatsApp notification sent: event={event} order={order.order_number} phone={phone[:6]}***")
        else:
            logger.warning(f"WhatsApp notification HTTP {response.status_code}: event={event} order={order.order_number}")
    except requests.exceptions.RequestException as e:
        logger.warning(f"WhatsApp notification failed (network): event={event} order={order.order_number}: {e}")


def _send_whatsapp_via_evolution(phone, message, event, order, instance=None):
    """Send via the Evolution API, optionally from a specific instance/number."""
    try:
        from core.whatsapp_utils import send_whatsapp_message_api
        result = send_whatsapp_message_api(phone, message, instance_obj=instance)
        if result.get('success'):
            logger.info(f"Evolution notification sent: event={event} order={order.order_number} phone={phone[:6]}***")
        else:
            logger.warning(f"Evolution notification failed: event={event} order={order.order_number}: {result.get('error') or result.get('status_code')}")
    except Exception as e:
        logger.warning(f"Evolution notification error: event={event} order={order.order_number}: {e}")


def _send_whatsapp_via_waha(phone, message, event, order, instance=None):
    """
    Send via the self-hosted WAHA bridge instead of n8n.

    Talks directly to WAHA (no internal HTTP self-call) and writes an
    outbound row into whatsapp.WhatsAppMessage so the agent inbox shows
    the conversation history.

    Why direct (not through /api/integrations/waha/send/): self-HTTP from
    a signal handler can deadlock if all gunicorn workers are already
    busy. The DB row + audit trail is preserved either way.

    instance: optional WhatsAppInstance chosen for this trigger; its
    instance_name is used as the WAHA session so the message goes out from
    the selected number. None = the configured default session.
    """
    base_url = getattr(settings, 'WAHA_BASE_URL', '') or ''
    api_key = getattr(settings, 'WAHA_API_KEY', '') or ''
    session = getattr(settings, 'WAHA_DEFAULT_SESSION', 'default') or 'default'
    # Same number serves both channels via different identifiers: use the
    # instance's dedicated WAHA session if set; otherwise keep the global
    # default session (the Evolution instance_name is NOT a WAHA session).
    if instance is not None:
        waha_sess = (getattr(instance, 'waha_session', '') or '').strip()
        if waha_sess:
            session = waha_sess
    if not base_url or not api_key:
        logger.debug(f"WAHA notification skipped ({event}): WAHA_BASE_URL or WAHA_API_KEY not configured")
        return

    digits = ''.join(ch for ch in str(phone) if ch.isdigit())
    if not digits:
        logger.debug(f"WAHA notification skipped ({event}): no digits in phone")
        return
    chat_id = f"{digits}@c.us"

    waha_url = f"{base_url.rstrip('/')}/api/sendText"
    payload = {'chatId': chat_id, 'text': str(message).strip(), 'session': session}
    headers = {'X-Api-Key': api_key, 'Content-Type': 'application/json'}

    waha_status = 0
    waha_resp_id = ''
    err_kind = ''
    try:
        response = requests.post(waha_url, json=payload, headers=headers, timeout=10)
        waha_status = response.status_code
        if 200 <= waha_status < 300:
            try:
                body = response.json() or {}
                waha_resp_id = (body.get('id') or
                                (body.get('_data') or {}).get('id') or '')
            except ValueError:
                waha_resp_id = ''
            logger.info(f"WAHA notification sent: event={event} order={order.order_number} phone={phone[:6]}*** status={waha_status}")
        else:
            err_kind = 'waha_send_error'
            logger.warning(f"WAHA notification HTTP {waha_status}: event={event} order={order.order_number}")
    except requests.exceptions.Timeout:
        err_kind = 'waha_timeout'
        logger.warning(f"WAHA notification timeout: event={event} order={order.order_number}")
    except requests.exceptions.RequestException as e:
        err_kind = 'waha_send_error'
        logger.warning(f"WAHA notification failed (network): event={event} order={order.order_number}: {e}")

    try:
        from whatsapp.models import WhatsAppMessage
        from uuid import uuid4
        wid = waha_resp_id or (
            f"out-fail-{uuid4().hex}" if err_kind else f"out-{uuid4().hex}"
        )
        WhatsAppMessage.objects.create(
            waha_message_id=wid,
            session=session,
            direction='outbound',
            from_number=getattr(settings, 'WAHA_DEFAULT_FROM', '') or '',
            to_number=digits,
            body=str(message).strip(),
            message_type='text',
            status='failed' if err_kind else 'processed',
            error_kind=err_kind,
            order=order if order else None,
            raw_payload={'event': event, 'order_id': getattr(order, 'id', None)},
            received_at=timezone.now(),
            processed_at=timezone.now(),
        )
    except Exception as e:
        logger.warning(f"WAHA outbound row write failed (non-fatal): {e}")
