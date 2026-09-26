"""
Purpose: Resolve where an undelivered parcel must physically go back to, and log custody history.
Used by: workforce.views.update_task_status and ezzy_api driver_complete_task (custody opening
         via open_return_for_task), and the workforce returns console.
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
# The parcel is on a hub shelf waiting for the run out to the client. Its own
# custody row, not a re-opening of the leg that brought it in: that leg closed
# when the hub signed for it, and a driver's liability must not be re-opened by
# a second driver's job.
CUSTODY_AT_HUB = 'at_hub'
CUSTODY_RECEIVED = 'received'
CUSTODY_DISPUTED = 'disputed'
CUSTODY_NOT_IN_CUSTODY = 'not_in_custody'
CUSTODY_LOST = 'lost'
CUSTODY_VOIDED = 'voided'

CUSTODY_STATUS_CHOICES = [
    (CUSTODY_WITH_DRIVER, 'With driver'),
    (CUSTODY_IN_MANIFEST, 'In return manifest'),
    (CUSTODY_AT_HUB, 'At hub — awaiting run to client'),
    (CUSTODY_RECEIVED, 'Received'),
    (CUSTODY_DISPUTED, 'Disputed'),
    (CUSTODY_NOT_IN_CUSTODY, 'Driver says not held'),
    (CUSTODY_LOST, 'Lost'),
    (CUSTODY_VOIDED, 'Voided'),
]

# States where the driver is still liable for the parcel. The partial unique constraint
# that prevents two open custody rows per task keys off exactly this tuple.
CUSTODY_OPEN_STATES = (CUSTODY_WITH_DRIVER, CUSTODY_IN_MANIFEST, CUSTODY_AT_HUB,
                       CUSTODY_DISPUTED)

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


def resolve_collection_destination(task):
    """Where goods COLLECTED BACK from a customer are taken. Never raises.

    The sibling of resolve_return_destination, and deliberately a separate
    function reading a separate field: that one answers "we failed to deliver
    this, where does it go" and every client sits on its 'hub' default. A
    collection is the opposite journey — the customer is handing goods back — and
    defaults to the client's own counter, so reusing the other field would have
    re-routed every failed delivery the day collections started honouring it.

    Same precedence shape: the client's preference, then a usable pickup
    location, then the hub with the reason recorded. Returns a ReturnDestination.
    """
    business = _business_for(task)
    order = getattr(task, 'order', None)

    preference = getattr(business, 'return_collection_destination',
                         DEST_BUSINESS) or DEST_BUSINESS

    if preference == DEST_BUSINESS:
        if order is not None:
            location = _usable_pickup_location(order)
            if location is not None:
                return _business(location, 'business.return_collection_destination')

        hub_location, source = resolve_hub_for_task(task)
        raw = getattr(order, 'pickup_location', None) if order is not None else None
        if raw is None:
            reason = 'collection configured for the client but the order has no pickup location'
        elif raw.is_fulfilment_center:
            reason = 'pickup location is a fulfilment centre — routed to hub instead'
        else:
            reason = f'pickup location is {raw.pickup_status} — cannot receive collections'
        logger.info(
            "Collection destination fell back to hub for task %s: %s",
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


# ---------------------------------------------------------------------------
# Custody lifecycle
# ---------------------------------------------------------------------------

# The dl_task_status that opens a custody row.
RETURNED_TO_SHIPPER = 'returned_to_shipper'

# Legal custody moves. The four closing states are dead ends: a parcel that has
# been signed for cannot un-arrive, and re-opening one would make two open rows
# momentarily legal, which the partial unique constraint forbids anyway.
CUSTODY_TRANSITIONS = {
    CUSTODY_WITH_DRIVER:    {CUSTODY_IN_MANIFEST, CUSTODY_AT_HUB, CUSTODY_RECEIVED,
                             CUSTODY_DISPUTED, CUSTODY_NOT_IN_CUSTODY, CUSTODY_LOST,
                             CUSTODY_VOIDED},
    CUSTODY_IN_MANIFEST:    {CUSTODY_RECEIVED, CUSTODY_DISPUTED, CUSTODY_LOST,
                             CUSTODY_VOIDED},
    # 'received' from the shelf is the client collecting it over the counter
    # themselves — a real and common ending that needs no driver at all.
    CUSTODY_AT_HUB:         {CUSTODY_WITH_DRIVER, CUSTODY_IN_MANIFEST, CUSTODY_RECEIVED,
                             CUSTODY_DISPUTED, CUSTODY_LOST, CUSTODY_VOIDED},
    CUSTODY_DISPUTED:       {CUSTODY_RECEIVED, CUSTODY_NOT_IN_CUSTODY, CUSTODY_LOST,
                             CUSTODY_VOIDED},
    CUSTODY_RECEIVED:       set(),
    CUSTODY_NOT_IN_CUSTODY: set(),
    CUSTODY_LOST:           set(),
    CUSTODY_VOIDED:         set(),
}

ReturnOutcome = namedtuple(
    'ReturnOutcome',
    ['custody', 'created', 'return_request', 'cod_reversed', 'cod_amount', 'warnings'],
)


def open_custody_for_task(task, actor=None, notes='', return_request=None):
    """Open the custody row for a parcel coming back. Returns (custody, created).

    Idempotent: an existing OPEN row for this task is returned untouched, which is
    also what the partial unique constraint enforces at the database level.

    The destination is resolved ONCE, here, and snapshotted onto the row. A task
    with no driver still gets a row — opened as 'disputed', because somebody is
    holding the parcel and we do not know who. Losing the row would lose the box.
    """
    from delivery.models import ParcelCustody

    existing = ParcelCustody.objects.filter(
        task=task, status__in=CUSTODY_OPEN_STATES,
    ).first()
    if existing is not None:
        return existing, False

    # A collection is going the other way — goods the customer is handing back —
    # and reads its own preference. Chosen here so no caller has to know which
    # resolver a leg wants.
    if getattr(task, 'task_leg', None) == COLLECT_LEG:
        destination = resolve_collection_destination(task)
    else:
        destination = resolve_return_destination(task)
    order = task.order
    opened_status = CUSTODY_WITH_DRIVER if task.driver_id else CUSTODY_DISPUTED
    if not task.driver_id:
        notes = (notes + ' — ' if notes else '') + (
            'opened by staff with no driver on the task; holder unknown')

    custody = ParcelCustody.objects.create(
        task=task,
        order=order,
        business=getattr(order, 'business', None),
        driver=task.driver,
        status=opened_status,
        destination_kind=destination.kind,
        warehouse_location=destination.warehouse_location,
        pickup_location=destination.pickup_location,
        destination_source=destination.source or '',
        destination_fallback_reason=destination.fallback_reason or '',
        return_request=return_request,
        notes=notes or '',
        opened_by=actor if getattr(actor, 'is_authenticated', False) else None,
    )
    log_custody_history(custody, '', opened_status, actor, notes)
    logger.info(
        "Opened parcel custody %s for task %s → %s (%s)",
        custody.pk, task.dl_task_number, destination.kind,
        destination.source or 'no source',
    )
    return custody, True


def set_custody_status(custody, new_status, actor=None, notes=''):
    """Move a custody row. Returns (ok, reason).

    Refuses anything CUSTODY_TRANSITIONS does not allow rather than writing it and
    logging a warning — unlike the delivery task state machine, there is no legacy
    caller here that would be broken by a hard refusal.
    """
    from django.utils import timezone

    old_status = custody.status
    if old_status == new_status:
        return True, ''

    allowed = CUSTODY_TRANSITIONS.get(old_status, set())
    if new_status not in allowed:
        allowed_list = ', '.join(sorted(allowed)) or 'none'
        labels = dict(CUSTODY_STATUS_CHOICES)
        return False, (
            f"Cannot move custody from '{labels.get(old_status, old_status)}' to "
            f"'{labels.get(new_status, new_status)}'. Allowed next: [{allowed_list}]."
        )

    fields = ['status', 'updated_at']
    custody.status = new_status
    if new_status == CUSTODY_RECEIVED:
        custody.received_at = timezone.now()
        custody.received_by = actor if getattr(actor, 'is_authenticated', False) else None
        fields += ['received_at', 'received_by']
    custody.save(update_fields=fields)

    log_custody_history(custody, old_status, new_status, actor, notes)
    return True, ''


def open_return_for_task(task, *, actor=None, reason='other', reason_notes='',
                         reverse_cod=True):
    """Everything that must happen when a delivery closes as returned_to_shipper.

    Callers write dl_task_status FIRST and let the save go through, because that is
    what runs the state machine and the warehouse stock restore
    (warehouse.signals.delivery_task_post_save_handler). Only then do they call
    this. Stock is deliberately NOT touched here: booking it back a second time
    from this side would be invisible to that handler's idempotency guard, which
    only looks at reference_type='delivery_task'.

    Never raises to the view — anything that goes wrong comes back in `warnings`
    so the status change itself still stands.

    Returns a ReturnOutcome.
    """
    from decimal import Decimal

    from django.db import transaction

    from delivery.models import DeliveryTask, ParcelCustody
    from orders import money
    from orders.cod_status import apply_cod_status
    from orders.services import create_return_request
    from warehouse.signals import create_customer_return_rma

    ZERO = Decimal('0.00')
    warnings = []

    with transaction.atomic():
        # of=('self',) is load-bearing on Postgres: order and driver are nullable
        # FKs, so select_related turns them into LEFT JOINs and a bare FOR UPDATE
        # is rejected outright with "FOR UPDATE cannot be applied to the nullable
        # side of an outer join". Only the task row needs locking anyway.
        task = (DeliveryTask.objects
                .select_for_update(of=('self',))
                .select_related('order', 'order__business', 'driver')
                .get(pk=task.pk))

        # The pre_save guard reverts a disallowed transition silently, so a caller
        # can believe it wrote the status when it did not. Opening an RMA and
        # refunding COD against a task that is still out for delivery would be
        # much worse than doing nothing.
        if task.dl_task_status != RETURNED_TO_SHIPPER:
            return ReturnOutcome(
                None, False, None, False, ZERO,
                ['the status change did not stick — nothing was returned'],
            )

        # A collection that comes back undelivered is NOT a new return. Opening one
        # would raise a claim against the collection order itself — a return of a
        # return, which the console can then send another driver to collect, and so
        # on. The goods simply never left the customer; the original claim is still
        # the open one, and staff re-schedule from there.
        from delivery.selectors import COLLECT_LEG
        if task.task_leg == COLLECT_LEG:
            return ReturnOutcome(
                None, False, None, False, ZERO,
                ['a return pickup that failed is not a new return — '
                 're-schedule the collection on the original claim'],
            )

        # Idempotency. A double-submit must not open two RMAs or refund twice.
        existing = ParcelCustody.objects.filter(
            task=task, status__in=CUSTODY_OPEN_STATES,
        ).first()
        if existing is not None:
            return ReturnOutcome(
                existing, False, existing.return_request, False, ZERO,
                ['this parcel is already being tracked back'],
            )

        order = task.order
        if order is None:
            return ReturnOutcome(None, False, None, False, ZERO,
                                 ['task has no order — cannot open a return'])

        # 1. Seller-facing paperwork. First, so its number can be quoted in the
        #    custody history line.
        collected = money.collected_for(order)
        # ReturnRequest.reason and DeliveryTask.failure_reason are DIFFERENT
        # vocabularies — passing the task's key straight through wrote a value no
        # choices list contained, and the console rendered the raw slug. The
        # driver's own reason is preserved in the notes, where it reads properly.
        from delivery.models import DeliveryTask
        task_reason_label = dict(DeliveryTask.FAILURE_REASON_CHOICES).get(reason, '')
        detail = ' — '.join(x for x in (task_reason_label, reason_notes) if x)
        ret = create_return_request(
            order,
            reason='undelivered',
            reason_notes=(f'Returned to shipper on task {task.dl_task_number}'
                          + (f': {detail}' if detail else '')),
            cod_reversal_amount=collected,
            status='approved',
            user=actor,
        )

        # 2. Warehouse RMA. None when the seller has no linked warehouse — that is
        #    "not our shelves", not a failure.
        returned_items = list(order.order_items.all())
        rma = create_customer_return_rma(
            order, returned_items,
            notes=f"Returned to shipper on task {task.dl_task_number}",
        )
        if rma is None:
            warnings.append('no linked warehouse — no RMA raised')

        # 3. Custody. A destination that resolves to nothing still opens a row and
        #    lands in the console's triage filter.
        custody, created = open_custody_for_task(
            task, actor=actor,
            notes=f"Return {ret.return_number}",
            return_request=ret,
        )
        if custody.needs_triage:
            warnings.append(
                custody.destination_fallback_reason
                or 'no return destination could be resolved — needs staff triage')

        # 4. Money last: it is the least reversible step, so anything that raises
        #    above it rolls back before a refund is written.
        cod_reversed, cod_amount = False, ZERO
        if reverse_cod and collected > ZERO:
            if task.cod_client_settled:
                warnings.append(
                    'COD was already paid to the business — reverse the business '
                    'COD payout first, then refund from Fleet → Transactions')
            elif not task.driver_id:
                warnings.append('no driver on the task — COD could not be reversed')
            else:
                from fleet.wallet_service import WalletService
                payable = min(collected, money.task_headroom(task))
                if payable <= ZERO:
                    warnings.append('COD has already been refunded in full')
                else:
                    try:
                        WalletService.record_cod_return(
                            driver=task.driver, delivery_task=task, amount=payable,
                            created_by=actor,
                            notes=(f"Parcel returned to shipper — order "
                                   f"{order.order_number}"),
                        )
                        cod_reversed, cod_amount = True, payable
                    except Exception as e:
                        logger.warning(
                            "COD reversal failed for task %s: %s", task.pk, e)
                        warnings.append(f'COD could not be reversed: {e}')

            if cod_reversed and money.collected_for(order) <= ZERO:
                apply_cod_status(order, 'not_collected')
                if not ret.cod_reversal_processed:
                    ret.cod_reversal_processed = True
                    ret.save(update_fields=['cod_reversal_processed', 'updated_at'])

    return ReturnOutcome(custody, created, ret, cod_reversed, cod_amount, warnings)


# ---------------------------------------------------------------------------
# Leg 2 — hub back out to the client
# ---------------------------------------------------------------------------

# The task_leg that carries a parcel from a hub shelf back to the client. Must
# match DeliveryTask.TASK_LEG_CHOICES; delivery/earnings.py prices it.
RETURN_LEG = 'return_to_client'

# The leg that collects goods back off a customer. A literal rather than an import
# from delivery.selectors: business/models.py imports this module at module level
# precisely because it pulls in no models of its own, and selectors would break that.
COLLECT_LEG = 'collect_from_customer'

# Appended to the originating task's number, with no dash on purpose: the list
# ordering in delivery/ordering.py strips everything up to the LAST dash, so
# 'AB948-R' would sort as 'R' and scatter. 'AB948RT' sorts straight after the
# leg it belongs to.
RETURN_LEG_SUFFIX = 'RT'

ForwardOutcome = namedtuple(
    'ForwardOutcome', ['custody', 'task', 'error'])


def _return_leg_task_number(origin_task):
    """A unique 'AB948RT' code for the run back out. Never collides."""
    from delivery.models import DeliveryTask

    base = (getattr(origin_task, 'dl_task_number', '') or '').strip()
    if not base:
        base = getattr(getattr(origin_task, 'order', None), 'order_number', '') or 'RETURN'
    candidate = f'{base}{RETURN_LEG_SUFFIX}'
    if not DeliveryTask.objects.filter(dl_task_number=candidate).exists():
        return candidate
    # A second run at the same parcel — the first was cancelled or the client was
    # out. Numbered rather than overwritten so both attempts stay auditable.
    n = 2
    while DeliveryTask.objects.filter(
            dl_task_number=f'{candidate}{n}').exists() and n < 50:
        n += 1
    return f'{candidate}{n}'


def _return_leg_address(order, pickup_location, task_number):
    """A DlAddressUpdate pointing at the CLIENT, not the customer.

    The driver app resolves a destination through delivery.selectors.task_address,
    which reads this row — so building one here is what makes the return run show
    the merchant's address, phone and pin with no driver-side change at all.
    """
    from delivery.models import DlAddressUpdate

    business = getattr(order, 'business', None)
    name = (getattr(pickup_location, 'contact_name', '')
            or getattr(business, 'business_name', '')
            or getattr(pickup_location, 'pickup_location_title', '')
            or 'Client')
    phone = (getattr(pickup_location, 'contact_phone', '')
             or getattr(business, 'business_phone', '') or '')

    return DlAddressUpdate.objects.create(
        full_name=name[:100],
        mobile_no=(phone or '')[:20],
        area_name=(getattr(pickup_location, 'locality', '') or '')[:100],
        dl_zone=getattr(pickup_location, 'pickup_zone_no', None),
        dl_street=getattr(pickup_location, 'pickup_street_no', None),
        dl_building=getattr(pickup_location, 'pickup_building_no', None),
        dl_latitude=getattr(pickup_location, 'pickup_lat', None),
        dl_longitude=getattr(pickup_location, 'pickup_lon', None),
        # Returns go to a business address; the villa/flat flags would put the
        # wrong icon and the wrong "ring the doorbell" copy on the driver's card.
        is_office=True,
        dl_task_number=task_number,
        order=order,
        notes=f"Return to client — {getattr(pickup_location, 'pickup_location_title', '')}".strip(),
    )


def forward_to_client(custody, *, actor=None, pickup_location=None, notes=''):
    """Raise the run that takes a parcel from the hub shelf back out to the client.

    This is the SECOND physical leg of a return: driver A brought the parcel in,
    the hub signed for it, and a different driver now has to carry it to the
    merchant. That leg is a real DeliveryTask rather than a custody-only note, so
    it appears in the fleet PWA, can be claimed from the pool, captures proof of
    delivery and pays through delivery/earnings.py like any other drop.

    The incoming custody row is NOT re-opened — it closed when the hub signed for
    the parcel, and re-opening it would put driver A back on the hook for driver
    B's job. A new row is created against the new task and linked back with
    `forwarded_from`, so the console reads as one chain.

    Returns a ForwardOutcome; `error` is set and nothing is written when refused.
    """
    from django.db import transaction

    from delivery.models import DeliveryTask, ParcelCustody

    if custody.status != CUSTODY_RECEIVED:
        return ForwardOutcome(None, None, (
            f"Only a parcel already signed in at the hub can be sent on — this one "
            f"is '{custody.get_status_display()}'."))
    if custody.destination_kind != DEST_HUB:
        return ForwardOutcome(None, None, (
            'This parcel was returned straight to the client, so there is nothing '
            'at the hub to send on.'))

    order = custody.order
    if order is None:
        return ForwardOutcome(None, None, 'This custody row has no order.')

    target = pickup_location or _usable_pickup_location(order)
    if target is None:
        return ForwardOutcome(None, None, (
            'No usable client address to return this to — set one on the order or '
            'pick one by hand.'))

    origin_task = custody.task

    with transaction.atomic():
        # Idempotency + the one-open-row rule. Without this a double-click raises
        # two return runs and two drivers turn up for one parcel.
        live = ParcelCustody.objects.filter(
            order=order, status__in=CUSTODY_OPEN_STATES).first()
        if live is not None:
            return ForwardOutcome(None, None, (
                'A return run for this parcel is already open '
                f"({live.get_status_display()})."))

        task_number = _return_leg_task_number(origin_task)
        address = _return_leg_address(order, target, task_number)

        task = DeliveryTask.objects.create(
            dl_task_number=task_number,
            dl_task_description=f"Return to client — {order.order_number}"[:100],
            order=order,
            business=custody.business or getattr(order, 'business', None),
            dl_address_update=address,
            dl_task_status='pending',
            dl_task_status_client='for_review',
            # The goods start on a hub shelf, not at a merchant pickup point —
            # the same thing _create_hub_delivery_tasks says for its Leg 2.
            pickup_location=None,
            task_leg=RETURN_LEG,
            hub_warehouse=custody.warehouse_location,
            # Published on creation: the whole point is that any driver can take
            # it. Staff can still unpublish it from the task page.
            dl_task_publish=True,
            # No COD on the way back — that was reversed by open_return_for_task.
            # The DELIVERY CHARGE is a different question: a run raised on a later
            # day is a second trip on a second date, so it is its own billable job
            # at the outward rate. Raised the same day it is part of the trip the
            # client is already being charged for, and billing it again would
            # charge one journey twice.
            dl_price=_return_leg_charge(origin_task),
        )

        forward = ParcelCustody.objects.create(
            task=task,
            order=order,
            business=task.business,
            driver=None,
            status=CUSTODY_AT_HUB,
            destination_kind=DEST_BUSINESS,
            pickup_location=target,
            warehouse_location=None,
            destination_source='forwarded from hub',
            return_request=custody.return_request,
            forwarded_from=custody,
            notes=notes or f'Return run {task_number} raised from {custody.destination_label}',
            opened_by=actor if getattr(actor, 'is_authenticated', False) else None,
        )
        log_custody_history(
            forward, '', CUSTODY_AT_HUB, actor,
            notes=f'Return run {task_number} raised — {custody.destination_label} '
                  f'→ {forward.destination_label}',
        )

    logger.info(
        "Return leg %s raised from custody %s for order %s → %s",
        task_number, custody.pk, order.order_number, forward.destination_label,
    )
    return ForwardOutcome(forward, task, '')


def _return_leg_charge(origin_task):
    """What the run back out to the client bills, in QAR.

    Zero on the day of the outward trip — the client is already paying for that
    journey — and the outward rate on any later day, because the parcel then
    costs us a second driver and a second trip. A verified charge on the outward
    leg wins over its raw price, the same way every other reader resolves it.
    """
    from django.utils import timezone
    from delivery.charges import billable_charge

    outward_date = getattr(origin_task, 'dl_task_date', None)
    if outward_date and outward_date == timezone.localdate():
        return 0
    return billable_charge(origin_task)


def sync_return_leg_custody(task, actor=None):
    """Keep the custody row of a return run in step with its delivery task.

    Called from delivery.signals on every save of a `return_to_client` task, so
    the returns console reflects what the driver actually did without staff
    touching it twice. Idempotent and never raises — a custody row that cannot
    move must not roll back the driver's status change.

    Mapping, and why:
      accepted/on the road  → with_driver  (the parcel left the shelf)
      delivered             → received     (the client signed for it)
      failed/returned       → at_hub       (it came back to the shelf)
      cancelled/rejected    → at_hub       (nobody took it after all)
    """
    from delivery.models import ParcelCustody

    if getattr(task, 'task_leg', None) != RETURN_LEG:
        return None

    try:
        custody = ParcelCustody.objects.filter(
            task=task, status__in=CUSTODY_OPEN_STATES).first()
        if custody is None:
            return None

        status = task.dl_task_status
        if status == 'delivered':
            target = CUSTODY_RECEIVED
        elif status in ('failed', 'returned_to_shipper', 'cancelled', 'rejected',
                        'pending', 'for_review'):
            target = CUSTODY_AT_HUB
        elif task.driver_id:
            target = CUSTODY_WITH_DRIVER
        else:
            target = CUSTODY_AT_HUB

        # The holder is whoever the task says it is; on the shelf, nobody.
        driver_id = task.driver_id if target == CUSTODY_WITH_DRIVER else None
        if custody.driver_id != driver_id:
            custody.driver_id = driver_id
            custody.save(update_fields=['driver', 'updated_at'])

        if custody.status != target:
            ok, reason = set_custody_status(
                custody, target, actor=actor,
                notes=f'Return run {task.dl_task_number} is {task.get_dl_task_status_display()}')
            if not ok:
                logger.warning(
                    "Return-leg custody %s could not move to %s: %s",
                    custody.pk, target, reason)
        return custody
    except Exception as e:
        logger.warning(
            "Return-leg custody sync failed for task %s: %s",
            getattr(task, 'pk', '?'), e)
        return None


def sync_collection_custody(task, actor=None):
    """Keep a collection's custody row in step with its task.

    Called from delivery.signals on every save of a `collect_from_customer` task.
    The driver picking the goods up off the customer IS the custody opening, and
    his drop-off IS the hand-over — staff should never have to repeat either.

    Mapping, and why:
      picked up / on the road → with_driver (he has the customer's goods)
      delivered               → received    (the hub or the client signed for them)

    A collection routed to a hub therefore lands as received/hub, which is exactly
    what the console's forward queue looks for — so the run back out to the client
    is raised by the same button that handles every other parcel on our shelf.
    Never raises: a bookkeeping failure must not roll back the driver.
    """
    from delivery.models import ParcelCustody

    if getattr(task, 'task_leg', None) != COLLECT_LEG:
        return None

    try:
        status = task.dl_task_status

        # Nothing is in anyone's hands until the driver has collected.
        if status in ('pending', 'for_review', 'assigned', 'accepted'):
            return None

        custody = ParcelCustody.objects.filter(
            task=task, status__in=CUSTODY_OPEN_STATES).first()
        if custody is None:
            if status in ('cancelled', 'rejected', 'failed', 'returned_to_shipper'):
                # He never got them — there is nothing to track.
                return None
            custody, _ = open_custody_for_task(
                task, actor=actor, notes='opened by the collection leg')

        if status == 'delivered':
            target = CUSTODY_RECEIVED
        elif status in ('failed', 'returned_to_shipper', 'cancelled', 'rejected'):
            # He has them and the drop-off did not happen; he is still liable.
            target = CUSTODY_WITH_DRIVER
        else:
            target = CUSTODY_WITH_DRIVER

        if custody.driver_id != task.driver_id:
            custody.driver_id = task.driver_id
            custody.save(update_fields=['driver', 'updated_at'])

        if custody.status != target:
            set_custody_status(custody, target, actor=actor,
                               notes=f'collection task is {status}')
        return custody
    except Exception as e:
        logger.warning("Collection custody sync failed for task %s: %s", task.pk, e)
        return None
