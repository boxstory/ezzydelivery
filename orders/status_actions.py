"""
Purpose: Run the seller handover — 'ready_to_pickup' then 'publish' — as one combined transition.
Used by: update_order_status and bulk_update_order_status in orders.views (the client dashboard).
Notes: Two real saves on purpose; every downstream effect hangs off a status-transition branch keyed on _old_order_status, so a single jump straight to 'publish' silently skips stock reservation, the pick list and the first-mile pickup leg.
"""

import logging

from django.db import transaction

logger = logging.getLogger(__name__)

# Status token the client dashboard posts for the combined action. Deliberately
# NOT a member of ORDER_STATUS_BY_CLIENT — it never lands in the database, it is
# only an instruction to run both legs below.
READY_AND_PUBLISH = 'ready_and_publish'


def apply_ready_and_publish(order, user=None):
    """
    Move `order` through 'ready_to_pickup' and on to 'publish' in one unit.

    Leg 1 ('ready_to_pickup') reserves warehouse stock, builds the pick list and
    opens the first-mile PickupTask. Leg 2 ('publish') creates the DeliveryTask.
    Either leg is skipped when the order already sits at or past that status.

    Returns the list of statuses actually written, e.g. ['ready_to_pickup',
    'publish'] for a fresh order, or ['publish'] for one already confirmed.
    """
    applied = []

    with transaction.atomic():
        if order.order_status != 'ready_to_pickup':
            order.order_status = 'ready_to_pickup'
            order._status_changed_by = user
            order.save()
            applied.append('ready_to_pickup')

        if order.order_status != 'publish':
            order.order_status = 'publish'
            order._status_changed_by = user
            order.save()
            applied.append('publish')

    logger.info(
        'Ready+publish applied to order %s: legs=%s',
        order.order_number or order.pk, applied or 'none',
    )
    return applied
