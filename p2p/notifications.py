# Purpose: The WhatsApp messages a P2P booking sends — the confirm link and the ops nudge.
# Used by: p2p.views (after order creation, after staff pricing, on a customer comment)
# Notes: Sends through send_routed_message('orders_tasks', …) so the number and channel stay under
#        the Auto Triggers page. Every send is gated on an AutoTriggerConfig row so ops can mute it;
#        the wording itself lives in core.message_templates and is edited on the Messages page.

import logging

from django.conf import settings

logger = logging.getLogger(__name__)

TRIGGER_BOOKING_CONFIRM = 'p2p_booking_confirm'
TRIGGER_CUSTOMER_COMMENT = 'p2p_customer_comment'


def _site_url():
    """Absolute base for links sent off-site. There is no settings.SITE_URL; the
    canonical value lives on SEOMetadata, so use that rather than a second literal."""
    try:
        from core.seo import SEOMetadata
        base = SEOMetadata.SITE_URL
    except Exception:
        base = getattr(settings, 'SITE_URL', '') or 'https://ezzydelivery.qa'
    return base.rstrip('/')


def confirm_url(booking):
    return f"{_site_url()}/p2p/a/{booking.token}/"


def _enabled(trigger_key):
    from core.models import AutoTriggerConfig
    try:
        return AutoTriggerConfig.is_trigger_enabled(trigger_key)
    except Exception:
        # A missing config row means "on" by design; a broken lookup must not stop a
        # customer being told their parcel is booked.
        logger.warning('Could not read trigger %s, sending anyway', trigger_key, exc_info=True)
        return True


def send_booking_confirmation(booking):
    """Tell the booker what was booked and give them the link that releases it.

    Addressed to booking.booker_phone, never to sender_phone: when a receiver books,
    the sender is a third party who never asked us for anything, and the link in this
    message is the one that releases the job.

    Returns the send result dict, or None when muted or unsendable. Never raises —
    the order already exists by this point, and a WhatsApp failure must not undo it.
    """
    from core.whatsapp_utils import send_routed_message

    if not _enabled(TRIGGER_BOOKING_CONFIRM):
        logger.info('P2P confirmation muted by trigger config for booking %s', booking.pk)
        return None

    phone = booking.notify_phone
    if not phone:
        logger.warning('P2P booking %s has no booker phone — cannot confirm', booking.pk)
        return None

    # Which lines appear is the body's own business now: the wording lives on the
    # Messages page, and its {if price} / {if cod_amount} blocks drop the lines an
    # unpriced or non-COD booking has nothing to say for.
    from core.message_templates import P2P_BOOKING_CONFIRM, get_body

    order = booking.order
    price = booking.agreed_price
    message = get_body(
        P2P_BOOKING_CONFIRM,
        from_label=booking.from_label,
        to_label=booking.to_label,
        order_number=order.order_number if order is not None else '',
        box_count=booking.box_count or '',
        price=price or '',
        fee_note=booking.fee_note or '',
        cod_amount=booking.cod_amount or '',
        # Blank on a one-way booking, which is what drops the whole line: a return trip
        # is two orders and the booker is owed both numbers, not just the outward one.
        return_route=booking.return_route_label,
        return_order_number=(
            booking.return_order.order_number if booking.return_order_id else ''),
        confirm_url=confirm_url(booking),
    )

    try:
        return send_routed_message('orders_tasks', phone, message)
    except Exception:
        logger.exception('P2P confirmation send failed for booking %s', booking.pk)
        return None


def notify_ops_of_comment(order, comment):
    """Let the desk know a sender replied on their order."""
    from core.whatsapp_utils import alert_recipient, send_routed_message

    if not _enabled(TRIGGER_CUSTOMER_COMMENT):
        return None
    try:
        recipient = alert_recipient(TRIGGER_CUSTOMER_COMMENT)
        if not recipient:
            return None
        from core.message_templates import P2P_COMMENT_OPS_ALERT, get_body
        body = get_body(
            P2P_COMMENT_OPS_ALERT,
            order_number=order.order_number,
            comment=comment.body[:400],
        )
        return send_routed_message('orders_tasks', recipient, body)
    except Exception:
        logger.exception('P2P comment notification failed for order %s', order.pk)
        return None
