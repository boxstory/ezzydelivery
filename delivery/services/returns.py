"""
Purpose: Resolve where an undelivered parcel must physically go back to, and log custody history.
Used by: delivery/signals.py (custody opening), fleet return views, workforce returns console.
Notes: The resolved destination is SNAPSHOTTED onto ParcelCustody at open time — never re-resolved
       on read, because merchants change config and the parcel is already on a van. Staff may
       override the snapshot; the resolver is only ever the opening default.
"""

import logging
from collections import namedtuple

logger = logging.getLogger(__name__)

# Destination kinds. Kept as module constants so the model choices and the resolver
# can never drift apart.
DEST_HUB = 'hub'
DEST_BUSINESS = 'business'

DESTINATION_CHOICES = [
    (DEST_HUB, 'Ezzy hub / warehouse'),
    (DEST_BUSINESS, 'Back to the business'),
]

# Pickup locations in these states cannot receive goods back.
_UNUSABLE_PICKUP_STATUSES = ('inactive', 'pending', 'suspended')

# Custody lifecycle. Declared here rather than on the model so the service layer, the
# history logger and the model all read one list.
CUSTODY_WITH_DRIVER = 'with_driver'
CUSTODY_IN_MANIFEST = 'in_manifest'
CUSTODY_RECEIVED = 'received'
CUSTODY_DISPUTED = 'disputed'
CUSTODY_NOT_IN_CUSTODY = 'not_in_custody'
CUSTODY_LOST = 'lost'
CUSTODY_VOIDED = 'voided'

CUSTODY_STATUS_CHOICES = [
    (CUSTODY_WITH_DRIVER, 'With driver'),
    (CUSTODY_IN_MANIFEST, 'In return manifest'),
    (CUSTODY_RECEIVED, 'Received'),
    (CUSTODY_DISPUTED, 'Disputed'),
    (CUSTODY_NOT_IN_CUSTODY, 'Driver says not held'),
    (CUSTODY_LOST, 'Lost'),
    (CUSTODY_VOIDED, 'Voided'),
]

# States where the driver is still liable for the parcel. The partial unique constraint
# that prevents two open custody rows per task keys off exactly this tuple.
CUSTODY_OPEN_STATES = (CUSTODY_WITH_DRIVER, CUSTODY_IN_MANIFEST, CUSTODY_DISPUTED)

# Value written into OrderStatusHistory.field_name; must be added to that model's
# STATUS_FIELD_CHOICES so the timeline renders a label instead of a raw slug.
CUSTODY_HISTORY_FIELD = 'parcel_custody'


ReturnDestination = namedtuple(
    'ReturnDestination',
    ['kind', 'warehouse_location', 'pickup_location', 'source', 'fallback_reason'],
)


def _hub(location, source):
    return ReturnDestination(DEST_HUB, location, None, source, '')


def _business(location, source):
    return ReturnDestination(DEST_BUSINESS, None, location, source, '')


def resolve_hub_for_task(task):
    """
    The hub a parcel should go back to, preferring the hub it actually came FROM.

    Deliberately NOT `pickup.resolve_default_hub()` — that returns one global default
    warehouse, which sends parcels to the wrong side of the country the moment a second
    hub exists. Falls back to it only as the last resort.

    Returns (WarehouseLocation|None, source_label).
    """
    # 1. Leg-2 hub deliveries already record the hub they departed from.
    if getattr(task, 'hub_warehouse_id', None):
        return task.hub_warehouse, 'task.hub_warehouse'

    # 2. The Leg-1 batch that carried the goods into a hub.
    batch = getattr(task, 'hub_pickup_batch', None)
    if batch is not None and getattr(batch, 'hub_warehouse_id', None):
        return batch.hub_warehouse, 'hub_pickup_batch.hub_warehouse'

    # 3. The first-mile pickup task's drop point.
    pickup_task = getattr(task, 'source_pickup_task', None)
    if pickup_task is not None and getattr(pickup_task, 'drop_warehouse_id', None):
        return pickup_task.drop_warehouse, 'source_pickup_task.drop_warehouse'

    # 4. The warehouse this business is contractually linked to.
    business = _business_for(task)
    if business is not None:
        location = _linked_warehouse_location(business)
        if location is not None:
            return location, 'seller_warehouse_link'

    # 5. Global default. May be None — callers must handle that.
    from delivery.services.pickup import resolve_default_hub
    return resolve_default_hub(), 'default_warehouse'


def _linked_warehouse_location(business):
    """Default WarehouseLocation for a business via SellerWarehouseLink, if any."""
    from warehouse.models import SellerWarehouseLink, WarehouseLocation

    link = (
        SellerWarehouseLink.objects
        .filter(business=business)
        .select_related('default_location', 'warehouse')
        .order_by('-is_default', '-priority')
        .first()
    )
    if link is None:
        return None
    if link.default_location_id:
        return link.default_location
    if link.warehouse_id:
        return (
            WarehouseLocation.objects
            .filter(warehouse_id=link.warehouse_id)
            .order_by('-is_default', 'name')
            .first()
        )
    return None


def _business_for(task):
    order = getattr(task, 'order', None)
    return getattr(order, 'business', None) if order is not None else None


def _usable_pickup_location(order):
    """
    The seller location that can physically take goods back, or None.

    Refuses fulfilment centres: `is_fulfilment_center` means the "seller location" IS a
    warehouse we already run, so routing a return there as a *business* return would
    double-count it against the hub leg.
    """
    location = getattr(order, 'pickup_location', None)
    if location is None:
        return None
    if location.pickup_status in _UNUSABLE_PICKUP_STATUSES:
        return None
    if location.is_fulfilment_center:
        return None
    return location


def resolve_return_destination(task):
    """
    Where this task's undelivered goods must go. Never raises.

    Precedence:
      1. Business preference (`Business.return_destination`), default 'hub'.
      2. If 'business': the order's pickup location, only when it is active and is not a
         fulfilment centre. Otherwise fall back to the hub and record WHY.
      3. If 'hub': the hub the parcel came from (see resolve_hub_for_task).

    Returns a ReturnDestination. `kind` is always set; the matching location may still be
    None if the estate is misconfigured (no warehouses at all) — callers must treat a
    None location as "needs staff triage", not as "no return required".
    """
    business = _business_for(task)
    order = getattr(task, 'order', None)

    # getattr keeps this callable before the Business.return_destination migration lands.
    preference = getattr(business, 'return_destination', DEST_HUB) or DEST_HUB

    if preference == DEST_BUSINESS:
        if order is not None:
            location = _usable_pickup_location(order)
            if location is not None:
                return _business(location, 'business.return_destination')

        # Configured for merchant return but the merchant location cannot take it.
        hub_location, source = resolve_hub_for_task(task)
        raw = getattr(order, 'pickup_location', None) if order is not None else None
        if raw is None:
            reason = 'business return configured but the order has no pickup location'
        elif raw.is_fulfilment_center:
            reason = 'pickup location is a fulfilment centre — routed to hub instead'
        else:
            reason = f'pickup location is {raw.pickup_status} — cannot receive returns'
        logger.info(
            "Return destination fell back to hub for task %s: %s",
            getattr(task, 'pk', '?'), reason,
        )
        return ReturnDestination(DEST_HUB, hub_location, None, source, reason)

    hub_location, source = resolve_hub_for_task(task)
    fallback_reason = '' if hub_location is not None else 'no warehouse location resolvable'
    return ReturnDestination(DEST_HUB, hub_location, None, source, fallback_reason)


def log_custody_history(custody, old_status, new_status, actor=None, notes=''):
    """
    Append a custody transition to OrderStatusHistory. Mirrors
    delivery/services/pickup.py:log_pickup_history — same table, distinct field_name, so the
    existing order timeline renders returns without a new history model.

    `new_display` is NOT nullable on OrderStatusHistory, so it is always populated here.
    'parcel_custody' must also be added to OrderStatusHistory.STATUS_FIELD_CHOICES; .create()
    skips full_clean() so an unlisted value would still write, but it would render as a raw
    slug in the timeline and fail any later validation pass.

    Never raises: a failed audit write must not roll back the custody move itself.
    """
    from orders.models import OrderStatusHistory

    labels = dict(CUSTODY_STATUS_CHOICES)
    try:
        OrderStatusHistory.objects.create(
            order=custody.order,
            field_name=CUSTODY_HISTORY_FIELD,
            old_value=old_status or '',
            new_value=new_status or '',
            old_display=labels.get(old_status, old_status or ''),
            new_display=labels.get(new_status, new_status or ''),
            changed_by=actor if getattr(actor, 'is_authenticated', False) else None,
            notes=notes[:255] if notes else None,
        )
    except Exception as e:
        logger.warning(
            "Custody history log failed for custody %s: %s", getattr(custody, 'pk', '?'), e
        )
