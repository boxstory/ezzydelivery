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

        _send_whatsapp(phone, message, event, _order)

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

def _send_whatsapp(phone, message, event, order):
    """Send the message via n8n webhook. Logs but never raises."""
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
