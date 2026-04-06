import logging
from django.db import models, transaction
from django.db.models.signals import post_save, post_delete, pre_save
from django.dispatch import receiver
from django.utils import timezone

logger = logging.getLogger('warehouse')

# Store old status values for change detection
_old_order_status = {}
_old_delivery_status = {}


def reserve_stock_for_order(order):
    """
    Reserve stock for all items in an order.
    Called when order status changes to 'ready_to_pickup'.

    Uses SellerWarehouseLink to find the correct warehouse for the business,
    since Warehouse model has no direct business FK.
    """
    from warehouse.models import StockLevel, StockReservation, InventoryTransaction, SellerWarehouseLink
    from orders.models import OrderItem

    try:
        order_items = OrderItem.objects.filter(order=order).select_related('product')

        # Get warehouse IDs linked to this business
        linked_warehouse_ids = SellerWarehouseLink.objects.filter(
            business=order.business,
            is_active=True
        ).values_list('warehouse_id', flat=True)

        if not linked_warehouse_ids:
            logger.warning(
                f"No warehouse linked to business {order.business.business_name} "
                f"for order {order.order_number} — skipping reservation"
            )
            return

        for item in order_items:
            if not item.product:
                continue

            # Find available stock in linked warehouses
            stock_levels = StockLevel.objects.filter(
                product=item.product,
                warehouse_id__in=linked_warehouse_ids,
                quantity_on_hand__gt=0
            ).select_for_update().order_by('-quantity_on_hand')

            remaining_qty = item.quantity

            for stock_level in stock_levels:
                if remaining_qty <= 0:
                    break

                available = stock_level.quantity_available
                if available <= 0:
                    continue

                reserve_qty = min(remaining_qty, available)

                # Create reservation
                StockReservation.objects.create(
                    order=order,
                    order_item=item,
                    stock_level=stock_level,
                    quantity=reserve_qty,
                    status='active'
                )

                # Update stock level
                old_reserved = stock_level.quantity_reserved
                stock_level.quantity_reserved += reserve_qty
                stock_level.save(update_fields=['quantity_reserved', 'updated_at'])

                # Log transaction
                InventoryTransaction.objects.create(
                    product=item.product,
                    warehouse=stock_level.warehouse,
                    location=stock_level.location,
                    transaction_type='reserve',
                    quantity=reserve_qty,
                    quantity_before=old_reserved,
                    quantity_after=stock_level.quantity_reserved,
                    reference_type='order',
                    reference_id=order.order_number,
                    notes=f"Reserved for order {order.order_number}"
                )

                remaining_qty -= reserve_qty

            if remaining_qty > 0:
                logger.warning(
                    f"Insufficient stock for order {order.order_number}, "
                    f"product {item.product.item_sku}, short by {remaining_qty}"
                )

        # Mark order as stock reserved
        order.stock_reserved = True
        order.save(update_fields=['stock_reserved'])

        logger.info(f"Stock reserved for order {order.order_number}")

    except Exception as e:
        logger.exception(f"Error reserving stock for order {order.order_number}: {str(e)}")


def release_stock_reservation(order):
    """
    Release stock reservations when order is cancelled.
    Also resets stock_reserved flag so stock can be re-reserved if order is reopened.
    """
    from warehouse.models import StockReservation, InventoryTransaction

    try:
        reservations = StockReservation.objects.filter(
            order=order,
            status='active'
        ).select_related('stock_level', 'order_item__product')

        for reservation in reservations:
            stock_level = reservation.stock_level
            old_reserved = stock_level.quantity_reserved

            # Update stock level
            stock_level.quantity_reserved = max(0, stock_level.quantity_reserved - reservation.quantity)
            stock_level.save(update_fields=['quantity_reserved', 'updated_at'])

            # Update reservation status
            reservation.status = 'cancelled'
            reservation.released_at = timezone.now()
            reservation.save(update_fields=['status', 'released_at', 'updated_at'])

            # Log transaction
            InventoryTransaction.objects.create(
                product=reservation.order_item.product,
                warehouse=stock_level.warehouse,
                location=stock_level.location,
                transaction_type='unreserve',
                quantity=-reservation.quantity,
                quantity_before=old_reserved,
                quantity_after=stock_level.quantity_reserved,
                reference_type='order',
                reference_id=order.order_number,
                notes=f"Released reservation for cancelled order {order.order_number}"
            )

        # Reset stock_reserved flag so it can be re-reserved if order is reopened
        order.stock_reserved = False
        order.save(update_fields=['stock_reserved'])

        logger.info(f"Stock reservations released for order {order.order_number}")

    except Exception as e:
        logger.exception(f"Error releasing stock for order {order.order_number}: {str(e)}")


def fulfill_stock_reservation(order):
    """
    Fulfill (deduct) stock when delivery is successful.
    Marks all pending OrderItems as delivered and updates their quantities.

    Two paths:
    1. If active reservations exist → convert reserved stock to shipped
    2. If NO reservations exist (order bypassed ready_to_pickup) → direct deduction
    """
    from warehouse.models import StockLevel, StockReservation, InventoryTransaction, SellerWarehouseLink
    from orders.models import OrderItem

    try:
        reservations = StockReservation.objects.filter(
            order=order,
            status='active'
        ).select_related('stock_level', 'order_item__product')

        if reservations.exists():
            # Path 1: Fulfill existing reservations
            for reservation in reservations:
                stock_level = reservation.stock_level
                old_on_hand = stock_level.quantity_on_hand
                old_reserved = stock_level.quantity_reserved

                # Deduct from on_hand and reserved (prevent negative)
                stock_level.quantity_on_hand = max(0, stock_level.quantity_on_hand - reservation.quantity)
                stock_level.quantity_reserved = max(0, stock_level.quantity_reserved - reservation.quantity)
                stock_level.save(update_fields=['quantity_on_hand', 'quantity_reserved', 'updated_at'])

                # Update reservation status
                reservation.status = 'fulfilled'
                reservation.released_at = timezone.now()
                reservation.save(update_fields=['status', 'released_at', 'updated_at'])

                # Mark the OrderItem as delivered
                item = reservation.order_item
                if item.delivery_status == 'pending':
                    item.delivery_status = 'delivered'
                    item.quantity_delivered = item.quantity
                    item.save(update_fields=['delivery_status', 'quantity_delivered', 'updated_at'])

                # Log transaction
                InventoryTransaction.objects.create(
                    product=reservation.order_item.product,
                    warehouse=stock_level.warehouse,
                    location=stock_level.location,
                    transaction_type='ship',
                    quantity=-reservation.quantity,
                    quantity_before=old_on_hand,
                    quantity_after=stock_level.quantity_on_hand,
                    reference_type='order',
                    reference_id=order.order_number,
                    notes=f"Shipped for order {order.order_number}"
                )

                check_and_create_low_stock_alert(stock_level)

            logger.info(f"Stock fulfilled (reserved path) for order {order.order_number}")
        else:
            # Path 2: Direct deduction — order bypassed ready_to_pickup
            # (e.g. to_review → publish → delivered)
            _direct_deduct_stock(order)

        # Mark all remaining pending items as delivered (items without stock tracking)
        OrderItem.objects.filter(
            order=order, delivery_status='pending'
        ).update(
            delivery_status='delivered',
            quantity_delivered=models.F('quantity')
        )

    except Exception as e:
        logger.exception(f"Error fulfilling stock for order {order.order_number}: {str(e)}")


def _direct_deduct_stock(order):
    """
    Directly deduct stock for an order that had no prior reservation.
    Finds the linked warehouse via SellerWarehouseLink and deducts quantity_on_hand.
    """
    from warehouse.models import StockLevel, InventoryTransaction, SellerWarehouseLink
    from orders.models import OrderItem

    order_items = OrderItem.objects.filter(order=order).select_related('product')

    linked_warehouse_ids = list(
        SellerWarehouseLink.objects.filter(
            business=order.business,
            is_active=True
        ).values_list('warehouse_id', flat=True)
    )

    if not linked_warehouse_ids:
        logger.warning(
            f"No warehouse linked to business {order.business.business_name} "
            f"for order {order.order_number} — skipping direct deduction"
        )
        return

    for item in order_items:
        if not item.product:
            continue

        stock_levels = StockLevel.objects.filter(
            product=item.product,
            warehouse_id__in=linked_warehouse_ids,
            quantity_on_hand__gt=0
        ).select_for_update().order_by('-quantity_on_hand')

        remaining_qty = item.quantity

        for stock_level in stock_levels:
            if remaining_qty <= 0:
                break

            deduct_qty = min(remaining_qty, stock_level.quantity_on_hand)
            old_on_hand = stock_level.quantity_on_hand

            stock_level.quantity_on_hand = max(0, stock_level.quantity_on_hand - deduct_qty)
            stock_level.save(update_fields=['quantity_on_hand', 'updated_at'])

            InventoryTransaction.objects.create(
                product=item.product,
                warehouse=stock_level.warehouse,
                location=stock_level.location,
                transaction_type='ship',
                quantity=-deduct_qty,
                quantity_before=old_on_hand,
                quantity_after=stock_level.quantity_on_hand,
                reference_type='order',
                reference_id=order.order_number,
                notes=f"Direct deduction for delivered order {order.order_number} (no reservation)"
            )

            check_and_create_low_stock_alert(stock_level)
            remaining_qty -= deduct_qty

        if remaining_qty > 0:
            logger.warning(
                f"Insufficient stock for direct deduction: order {order.order_number}, "
                f"product {item.product.item_sku}, short by {remaining_qty}"
            )

    logger.info(f"Stock fulfilled (direct deduction) for order {order.order_number}")


def return_stock_on_failed_delivery(order):
    """
    Return reserved/fulfilled stock when delivery fails (all items).
    Marks all OrderItems as returned.
    Handles both reservation-based and direct-deduction paths.
    """
    from warehouse.models import StockLevel, StockReservation, InventoryTransaction
    from orders.models import OrderItem

    try:
        has_reservations = False

        # Return active reservations (reserved but not yet fulfilled)
        active_reservations = StockReservation.objects.filter(
            order=order,
            status='active'
        ).select_related('stock_level', 'order_item__product')

        for reservation in active_reservations:
            has_reservations = True
            stock_level = reservation.stock_level
            old_reserved = stock_level.quantity_reserved

            stock_level.quantity_reserved = max(0, stock_level.quantity_reserved - reservation.quantity)
            stock_level.save(update_fields=['quantity_reserved', 'updated_at'])

            reservation.status = 'cancelled'
            reservation.released_at = timezone.now()
            reservation.save(update_fields=['status', 'released_at', 'updated_at'])

            # Mark the OrderItem as returned
            item = reservation.order_item
            item.delivery_status = 'returned'
            item.quantity_returned = item.quantity
            item.quantity_delivered = 0
            item.save(update_fields=['delivery_status', 'quantity_returned', 'quantity_delivered', 'updated_at'])

            InventoryTransaction.objects.create(
                product=reservation.order_item.product,
                warehouse=stock_level.warehouse,
                location=stock_level.location,
                transaction_type='return',
                quantity=reservation.quantity,
                quantity_before=old_reserved,
                quantity_after=stock_level.quantity_reserved,
                reference_type='order',
                reference_id=order.order_number,
                notes=f"Returned to stock - delivery failed for order {order.order_number}"
            )

        # Return fulfilled reservations (stock already deducted from on_hand)
        fulfilled_reservations = StockReservation.objects.filter(
            order=order,
            status='fulfilled'
        ).select_related('stock_level', 'order_item__product')

        for reservation in fulfilled_reservations:
            has_reservations = True
            stock_level = reservation.stock_level
            old_on_hand = stock_level.quantity_on_hand

            stock_level.quantity_on_hand += reservation.quantity
            stock_level.save(update_fields=['quantity_on_hand', 'updated_at'])

            reservation.status = 'returned'
            reservation.released_at = timezone.now()
            reservation.save(update_fields=['status', 'released_at', 'updated_at'])

            # Mark the OrderItem as returned
            item = reservation.order_item
            item.delivery_status = 'returned'
            item.quantity_returned = item.quantity
            item.quantity_delivered = 0
            item.save(update_fields=['delivery_status', 'quantity_returned', 'quantity_delivered', 'updated_at'])

            InventoryTransaction.objects.create(
                product=reservation.order_item.product,
                warehouse=stock_level.warehouse,
                location=stock_level.location,
                transaction_type='return',
                quantity=reservation.quantity,
                quantity_before=old_on_hand,
                quantity_after=stock_level.quantity_on_hand,
                reference_type='order',
                reference_id=order.order_number,
                notes=f"Returned to stock - delivery failed for order {order.order_number}"
            )

            check_and_create_low_stock_alert(stock_level)

        # If no reservations existed, reverse direct deduction transactions
        if not has_reservations:
            _reverse_direct_deductions(order)

        # Mark all items as returned
        OrderItem.objects.filter(
            order=order, delivery_status__in=['pending', 'delivered']
        ).update(
            delivery_status='returned',
            quantity_returned=models.F('quantity'),
            quantity_delivered=0
        )

        # Reset stock_reserved so it can be re-reserved on retry
        order.stock_reserved = False
        order.save(update_fields=['stock_reserved'])

        logger.info(f"Stock returned for failed delivery of order {order.order_number}")

    except Exception as e:
        logger.exception(f"Error returning stock for order {order.order_number}: {str(e)}")


def process_partial_return(order, returned_items):
    """
    Process partial return: some items from a delivered order are returned.

    Args:
        order: Order instance (already delivered)
        returned_items: list of dicts with {'item_id': int, 'quantity': int}
            e.g. [{'item_id': 42, 'quantity': 1}]

    This function:
    1. Restores stock for returned items
    2. Updates OrderItem delivery_status and quantities
    3. Auto-creates a CustomerReturn (RMA) record
    """
    from warehouse.models import (
        StockLevel, StockReservation, InventoryTransaction,
        SellerWarehouseLink, CustomerReturn, CustomerReturnItem
    )
    from orders.models import OrderItem

    linked_warehouse_ids = list(
        SellerWarehouseLink.objects.filter(
            business=order.business,
            is_active=True
        ).values_list('warehouse_id', flat=True)
    )

    returned_order_items = []

    for ret in returned_items:
        item_id = ret['item_id']
        return_qty = ret['quantity']

        try:
            item = OrderItem.objects.select_related('product').get(
                pk=item_id, order=order
            )
        except OrderItem.DoesNotExist:
            logger.warning(f"OrderItem {item_id} not found for order {order.order_number}")
            continue

        if not item.product:
            # No product to restock — just update status
            item.quantity_returned = (item.quantity_returned or 0) + return_qty
            item.quantity_delivered = max(0, item.quantity - item.quantity_returned)
            if item.quantity_delivered == 0:
                item.delivery_status = 'returned'
            else:
                item.delivery_status = 'partial'
            item.save(update_fields=['delivery_status', 'quantity_returned', 'quantity_delivered', 'updated_at'])
            returned_order_items.append(item)
            continue

        # Find the fulfilled reservation for this item
        reservation = StockReservation.objects.filter(
            order=order,
            order_item=item,
            status='fulfilled'
        ).select_related('stock_level').first()

        if reservation:
            # Restore stock via reservation
            stock_level = reservation.stock_level
            old_on_hand = stock_level.quantity_on_hand

            stock_level.quantity_on_hand += return_qty
            stock_level.save(update_fields=['quantity_on_hand', 'updated_at'])

            reservation.status = 'returned'
            reservation.released_at = timezone.now()
            reservation.save(update_fields=['status', 'released_at', 'updated_at'])

            InventoryTransaction.objects.create(
                product=item.product,
                warehouse=stock_level.warehouse,
                location=stock_level.location,
                transaction_type='return',
                quantity=return_qty,
                quantity_before=old_on_hand,
                quantity_after=stock_level.quantity_on_hand,
                reference_type='order',
                reference_id=order.order_number,
                notes=f"Partial return: {return_qty}x {item.product.item_sku} for order {order.order_number}"
            )

            check_and_create_low_stock_alert(stock_level)

        elif linked_warehouse_ids:
            # No reservation — find stock level directly and restore
            stock_level = StockLevel.objects.filter(
                product=item.product,
                warehouse_id__in=linked_warehouse_ids
            ).select_for_update().first()

            if stock_level:
                old_on_hand = stock_level.quantity_on_hand
                stock_level.quantity_on_hand += return_qty
                stock_level.save(update_fields=['quantity_on_hand', 'updated_at'])

                InventoryTransaction.objects.create(
                    product=item.product,
                    warehouse=stock_level.warehouse,
                    location=stock_level.location,
                    transaction_type='return',
                    quantity=return_qty,
                    quantity_before=old_on_hand,
                    quantity_after=stock_level.quantity_on_hand,
                    reference_type='order',
                    reference_id=order.order_number,
                    notes=f"Partial return (no reservation): {return_qty}x {item.product.item_sku} for order {order.order_number}"
                )

                check_and_create_low_stock_alert(stock_level)

        # Update OrderItem quantities
        item.quantity_returned = (item.quantity_returned or 0) + return_qty
        item.quantity_delivered = max(0, item.quantity - item.quantity_returned)
        if item.quantity_delivered == 0:
            item.delivery_status = 'returned'
        else:
            item.delivery_status = 'partial'
        item.save(update_fields=['delivery_status', 'quantity_returned', 'quantity_delivered', 'updated_at'])
        returned_order_items.append(item)

    # Auto-create CustomerReturn (RMA) for the returned items
    if returned_order_items:
        warehouse = None
        if linked_warehouse_ids:
            from warehouse.models import Warehouse
            warehouse = Warehouse.objects.filter(pk__in=linked_warehouse_ids).first()

        if warehouse:
            rma = CustomerReturn.objects.create(
                order=order,
                warehouse=warehouse,
                reason='refused',
                status='approved',
                customer_notes=f"Partial return from delivered order {order.order_number}",
            )

            for item in returned_order_items:
                if item.product:
                    CustomerReturnItem.objects.create(
                        customer_return=rma,
                        product=item.product,
                        quantity=item.quantity_returned,
                        reason='refused',
                        condition='good',
                        disposition='restock',
                    )

            logger.info(
                f"Auto-created RMA {rma.rma_number} for partial return on order {order.order_number} "
                f"({len(returned_order_items)} items)"
            )

    logger.info(f"Partial return processed for order {order.order_number}: {len(returned_order_items)} items returned")
    return returned_order_items


def _reverse_direct_deductions(order):
    """
    Reverse direct stock deductions (ship transactions with no reservation).
    Used when a delivery fails after stock was deducted via _direct_deduct_stock.
    """
    from warehouse.models import StockLevel, InventoryTransaction

    ship_txns = InventoryTransaction.objects.filter(
        reference_type='order',
        reference_id=order.order_number,
        transaction_type='ship'
    ).select_related('product', 'warehouse', 'location')

    # Check we haven't already reversed these
    return_count = InventoryTransaction.objects.filter(
        reference_type='order',
        reference_id=order.order_number,
        transaction_type='return'
    ).count()

    if return_count > 0:
        logger.info(f"Direct deductions already reversed for order {order.order_number}")
        return

    for txn in ship_txns:
        return_qty = abs(txn.quantity)
        stock_level = StockLevel.objects.filter(
            product=txn.product,
            warehouse=txn.warehouse,
            location=txn.location
        ).select_for_update().first()

        if stock_level:
            old_on_hand = stock_level.quantity_on_hand
            stock_level.quantity_on_hand += return_qty
            stock_level.save(update_fields=['quantity_on_hand', 'updated_at'])

            InventoryTransaction.objects.create(
                product=txn.product,
                warehouse=txn.warehouse,
                location=txn.location,
                transaction_type='return',
                quantity=return_qty,
                quantity_before=old_on_hand,
                quantity_after=stock_level.quantity_on_hand,
                reference_type='order',
                reference_id=order.order_number,
                notes=f"Reversed direct deduction - delivery failed for order {order.order_number}"
            )

            check_and_create_low_stock_alert(stock_level)

    logger.info(f"Direct deductions reversed for order {order.order_number}")


def check_and_create_low_stock_alert(stock_level):
    """
    Check if stock level is below reorder point and create alert if needed.
    """
    from warehouse.models import LowStockAlert

    if stock_level.is_low_stock:
        # Check if active alert already exists
        existing_alert = LowStockAlert.objects.filter(
            stock_level=stock_level,
            status='active'
        ).exists()

        if not existing_alert:
            LowStockAlert.objects.create(
                stock_level=stock_level,
                product=stock_level.product,
                warehouse=stock_level.warehouse,
                quantity_available=stock_level.quantity_available,
                reorder_point=stock_level.reorder_point,
                status='active'
            )
            logger.info(
                f"Low stock alert created for {stock_level.product.item_sku} "
                f"at {stock_level.warehouse.code}"
            )


def create_pick_list_for_order(order):
    """
    Add order items to pick lists grouped by warehouse + business + zone.

    Each unique (warehouse, business, zone) combination gets its own pick list.
    This means:
      - Seller A zone-1 items → PICK-001
      - Seller A zone-2 items → PICK-002
      - Seller B zone-1 items → PICK-003

    Products within each pick list are grouped by product+location in the UI.
    """
    from warehouse.models import (
        PickList, PickListItem, StockLevel, StorageLocation, SellerWarehouseLink
    )
    from orders.models import OrderItem

    order_items = OrderItem.objects.filter(
        order=order, product__isnull=False
    ).select_related('product')

    if not order_items.exists():
        logger.info(f"No product items for order {order.order_number} — skipping pick list")
        return

    # Already has a pick list?
    existing = PickListItem.objects.filter(order=order).exists()
    if existing:
        logger.info(f"Pick list already exists for order {order.order_number}")
        return

    # Find linked warehouse
    wh_link = SellerWarehouseLink.objects.filter(
        business=order.business,
        is_active=True
    ).select_related('warehouse').first()

    if not wh_link:
        logger.warning(
            f"No warehouse linked to business {order.business.business_name} "
            f"for order {order.order_number} — skipping pick list"
        )
        return

    warehouse = wh_link.warehouse
    business = order.business

    # Resolve stock locations and group items by zone
    items_by_zone = {}  # zone_id -> [(order_item, stock_level)]
    for item in order_items:
        stock_level = StockLevel.objects.filter(
            product=item.product,
            warehouse=warehouse,
            quantity_on_hand__gt=0
        ).select_related('location', 'location__parent').order_by('-quantity_on_hand').first()

        # Find the zone for this location (walk up the parent chain)
        zone = _get_zone_for_location(stock_level.location) if stock_level and stock_level.location else None
        zone_id = zone.pk if zone else None

        if zone_id not in items_by_zone:
            items_by_zone[zone_id] = {'zone': zone, 'items': []}
        items_by_zone[zone_id]['items'].append((item, stock_level))

    # Create or find pick lists per zone
    last_pick_list = None
    for zone_id, group in items_by_zone.items():
        zone = group['zone']

        # Find existing pending pick list for this warehouse + business + zone
        pick_list = PickList.objects.filter(
            warehouse=warehouse,
            business=business,
            zone=zone,
            status='pending',
        ).order_by('-created_at').first()

        if not pick_list:
            pick_list = PickList.objects.create(
                warehouse=warehouse,
                business=business,
                zone=zone,
                total_items=0,
            )

        for order_item, stock_level in group['items']:
            PickListItem.objects.create(
                pick_list=pick_list,
                order=order,
                order_item=order_item,
                product=order_item.product,
                location=stock_level.location if stock_level else None,
                quantity_to_pick=order_item.quantity,
            )

        pick_list.total_items = pick_list.items.count()
        pick_list.save(update_fields=['total_items'])

        zone_name = zone.code if zone else 'no-zone'
        logger.info(
            f"Pick list {pick_list.pick_number} [{business.business_name} / {zone_name}] "
            f"for order {order.order_number} at warehouse {warehouse.code} "
            f"(total: {pick_list.total_items} items)"
        )
        last_pick_list = pick_list

    return last_pick_list


def _get_zone_for_location(location):
    """Walk up the parent chain to find the zone for a storage location."""
    if not location:
        return None
    current = location
    # Walk up max 5 levels to find a zone
    for _ in range(5):
        if current.location_type == 'zone':
            return current
        if current.parent_id:
            current = current.parent
        else:
            break
    return None


def sync_pick_list_for_order(order):
    """
    Sync pick list items when an order is edited (products added/removed/qty changed).
    Only syncs if the pick list is still in 'pending' status — once picking starts,
    edits are locked.
    """
    from warehouse.models import PickList, PickListItem, StockLevel, SellerWarehouseLink
    from orders.models import OrderItem

    existing_items = PickListItem.objects.filter(order=order).select_related('pick_list')
    if not existing_items.exists():
        return  # No pick list yet — nothing to sync

    pick_list = existing_items.first().pick_list

    # Only sync pending pick lists — don't touch active/completed ones
    if pick_list.status != 'pending':
        logger.info(
            f"Pick list {pick_list.pick_number} is {pick_list.status} — "
            f"skipping sync for order {order.order_number}"
        )
        return

    # Get current order items
    current_order_items = OrderItem.objects.filter(
        order=order, product__isnull=False
    ).select_related('product')

    current_item_ids = set(current_order_items.values_list('pk', flat=True))
    existing_item_ids = set(existing_items.values_list('order_item_id', flat=True))

    # Find warehouse for location lookups
    wh_link = SellerWarehouseLink.objects.filter(
        business=order.business, is_active=True
    ).select_related('warehouse').first()
    warehouse = wh_link.warehouse if wh_link else None

    # Remove pick list items for deleted order items
    removed = existing_item_ids - current_item_ids
    if removed:
        PickListItem.objects.filter(order=order, order_item_id__in=removed).delete()
        logger.info(f"Removed {len(removed)} pick items for order {order.order_number}")

    # Add pick list items for new order items
    added = current_item_ids - existing_item_ids
    if added and warehouse:
        for oi in current_order_items.filter(pk__in=added):
            stock_level = StockLevel.objects.filter(
                product=oi.product, warehouse=warehouse, quantity_on_hand__gt=0
            ).select_related('location').order_by('-quantity_on_hand').first()

            PickListItem.objects.create(
                pick_list=pick_list,
                order=order,
                order_item=oi,
                product=oi.product,
                location=stock_level.location if stock_level else None,
                quantity_to_pick=oi.quantity,
            )
        logger.info(f"Added {len(added)} pick items for order {order.order_number}")

    # Update quantities for existing items that changed
    for oi in current_order_items.filter(pk__in=current_item_ids & existing_item_ids):
        pli = existing_items.filter(order_item=oi).first()
        if pli and pli.quantity_to_pick != oi.quantity:
            pli.quantity_to_pick = oi.quantity
            pli.save(update_fields=['quantity_to_pick'])
            logger.info(
                f"Updated qty for {oi.product.item_sku} in order {order.order_number}: "
                f"→ {oi.quantity}"
            )

    # Refresh total count
    pick_list.total_items = pick_list.items.count()
    pick_list.save(update_fields=['total_items', 'updated_at'])


def remove_pick_list_for_order(order):
    """
    Handle pick list cleanup when an order is cancelled.
    Behavior depends on pick list status:

    pending/assigned → delete items (not yet picked, safe to remove)
    in_progress      → delete unpicked items, keep picked ones for stock return
    completed/packing/packed → mark items as cancelled, return picked stock to shelf
    """
    from warehouse.models import PickListItem, StockLevel

    items = PickListItem.objects.filter(order=order).select_related(
        'pick_list', 'product', 'location'
    )
    if not items.exists():
        return

    pick_list = items.first().pick_list

    if pick_list.status in ('pending', 'assigned'):
        # Not yet started — safe to delete items
        count = items.count()
        items.delete()
        logger.info(f"Removed {count} pick items for cancelled order {order.order_number}")

    elif pick_list.status == 'in_progress':
        # Picking in progress — remove unpicked items, create return task for picked
        unpicked = items.filter(is_picked=False)
        picked = items.filter(is_picked=True)
        if unpicked.exists():
            count = unpicked.count()
            unpicked.delete()
            logger.info(f"Removed {count} unpicked items for cancelled order {order.order_number}")
        if picked.exists():
            _create_return_task(order, pick_list, picked)

    elif pick_list.status in ('completed', 'packing', 'packed'):
        # Already picked — create return task for staff to put items back on shelf
        picked = items.filter(is_picked=True)
        if picked.exists():
            _create_return_task(order, pick_list, picked)
        # Delete any unpicked items
        items.filter(is_picked=False).delete()

    # Refresh pick list counts
    pick_list.refresh_from_db()
    remaining = pick_list.items.count()
    if remaining == 0:
        logger.info(f"Deleting empty pick list {pick_list.pick_number}")
        pick_list.delete()
    else:
        pick_list.total_items = remaining
        pick_list.picked_items = pick_list.items.filter(is_picked=True).count()
        pick_list.save(update_fields=['total_items', 'picked_items', 'updated_at'])


def _create_return_task(order, pick_list, picked_items):
    """
    Create a ReturnTask for staff to physically return picked items to shelves.
    Stock is NOT updated here — only when staff confirms the return in the UI.
    """
    from warehouse.models import ReturnTask, ReturnTaskItem

    return_task = ReturnTask.objects.create(
        warehouse=pick_list.warehouse,
        order=order,
        pick_list=pick_list,
        reason='order_cancelled',
        notes=f"Order {order.order_number} cancelled after pickup. Return items to shelf.",
    )

    for item in picked_items:
        ReturnTaskItem.objects.create(
            return_task=return_task,
            product=item.product,
            location=item.location,
            quantity=item.quantity_to_pick,
        )

    logger.info(
        f"Return task {return_task.return_number} created for order {order.order_number} "
        f"({picked_items.count()} items to return to shelf)"
    )

    # Delete pick list items (pick list tracks the history, return task handles the action)
    picked_items.delete()

    return return_task


def complete_return_item(return_item, user=None):
    """
    Called when staff confirms they've returned an item to the shelf.
    Updates stock (on_hand) and marks the item as returned.
    """
    from warehouse.models import StockLevel, InventoryTransaction

    if return_item.is_returned:
        return  # Already done

    if return_item.location and return_item.product:
        stock = StockLevel.objects.filter(
            product=return_item.product,
            warehouse=return_item.return_task.warehouse,
            location=return_item.location,
        ).first()
        if stock:
            old_on_hand = stock.quantity_on_hand
            stock.quantity_on_hand += return_item.quantity
            stock.save(update_fields=['quantity_on_hand'])

            InventoryTransaction.objects.create(
                product=return_item.product,
                warehouse=return_item.return_task.warehouse,
                location=return_item.location,
                transaction_type='return',
                quantity=return_item.quantity,
                quantity_before=old_on_hand,
                quantity_after=stock.quantity_on_hand,
                reference_type='return_task',
                reference_id=return_item.return_task.return_number,
                notes=f"Returned to shelf — {return_item.return_task.reason}",
                created_by=user,
            )

    return_item.is_returned = True
    return_item.returned_at = timezone.now()
    return_item.save(update_fields=['is_returned', 'returned_at'])


# =============================================================================
# SIGNAL RECEIVERS
# =============================================================================

@receiver(pre_save, sender='orders.Order', dispatch_uid='warehouse.order_pre_save_handler')
def order_pre_save_handler(sender, instance, *args, **kwargs):
    """Track order status changes"""
    if instance.pk:
        try:
            from orders.models import Order
            old_instance = Order.objects.get(pk=instance.pk)
            _old_order_status[instance.pk] = old_instance.order_status
        except Order.DoesNotExist:
            pass


@receiver(post_save, sender='orders.Order', dispatch_uid='warehouse.order_post_save_handler')
def order_post_save_handler(sender, instance, created, *args, **kwargs):
    """
    Handle order status changes for stock reservation/release.

    - New order created as ready_to_pickup → reserve stock
    - Existing order changed to ready_to_pickup → reserve stock
    - Order cancelled → release reservations + reset stock_reserved flag
    """
    old_status = _old_order_status.pop(instance.pk, None)

    # Reserve stock + create pick list when order is ready for pickup
    # Works for both: newly created orders AND status changes to ready_to_pickup
    if instance.order_status == 'ready_to_pickup' and not instance.stock_reserved:
        if created or (old_status and old_status != 'ready_to_pickup'):
            with transaction.atomic():
                reserve_stock_for_order(instance)
            # Auto-create / merge into pick list
            try:
                create_pick_list_for_order(instance)
            except Exception as e:
                logger.exception(f"Error creating pick list for order {instance.order_number}: {e}")

    # Order edited while still ready_to_pickup → sync pick list items
    elif instance.order_status == 'ready_to_pickup' and not created:
        try:
            sync_pick_list_for_order(instance)
        except Exception as e:
            logger.exception(f"Error syncing pick list for order {instance.order_number}: {e}")

    # Order cancelled → release stock + remove from pick list
    elif (not created and old_status and
          old_status != 'cancelled' and
          instance.order_status == 'cancelled'):
        with transaction.atomic():
            release_stock_reservation(instance)
        try:
            remove_pick_list_for_order(instance)
        except Exception as e:
            logger.exception(f"Error removing pick list for order {instance.order_number}: {e}")


@receiver(pre_save, sender='delivery.DeliveryTask', dispatch_uid='warehouse.delivery_task_pre_save_handler')
def delivery_task_pre_save_handler(sender, instance, *args, **kwargs):
    """Track delivery task status changes"""
    if instance.pk:
        try:
            from delivery.models import DeliveryTask
            old_instance = DeliveryTask.objects.get(pk=instance.pk)
            _old_delivery_status[instance.pk] = old_instance.dl_task_status
        except DeliveryTask.DoesNotExist:
            pass


@receiver(post_save, sender='delivery.DeliveryTask', dispatch_uid='warehouse.delivery_task_post_save_handler')
def delivery_task_post_save_handler(sender, instance, created, *args, **kwargs):
    """
    Handle delivery task lifecycle for warehouse operations.

    delivered → deduct reserved stock from on_hand (fulfill)
    failed    → return reserved/fulfilled stock back to on_hand

    NOTE: Pick list creation moved to order_post_save_handler (triggered on ready_to_pickup).
    """
    if not instance.order:
        return

    old_status = _old_delivery_status.pop(instance.pk, None)

    # Fulfill stock when delivery is successful
    if old_status != 'delivered' and instance.dl_task_status == 'delivered':
        with transaction.atomic():
            fulfill_stock_reservation(instance.order)

    # Return stock when delivery fails
    elif instance.dl_task_status == 'failed' and old_status not in (None, 'failed'):
        with transaction.atomic():
            return_stock_on_failed_delivery(instance.order)


@receiver(post_save, sender='warehouse.StockLevel', dispatch_uid='warehouse.stock_level_post_save_handler')
def stock_level_post_save_handler(sender, instance, created, *args, **kwargs):
    """
    Check for low stock after stock level changes.
    """
    check_and_create_low_stock_alert(instance)


# =============================================================================
# SELLER WAREHOUSE LINK SIGNALS
# Auto-sync PickupLocation when a business is linked/unlinked to a warehouse
# =============================================================================

@receiver(post_save, sender='warehouse.SellerWarehouseLink', dispatch_uid='warehouse.seller_warehouse_link_post_save')
def seller_warehouse_link_post_save(sender, instance, created, **kwargs):
    """
    When a SellerWarehouseLink is created or updated, create/update a
    PickupLocation for the business using the warehouse address.
    """
    from business.models import PickupLocation

    warehouse = instance.warehouse
    business = instance.business

    pickup_status = 'active' if instance.is_active else 'inactive'

    try:
        pickup, was_created = PickupLocation.objects.update_or_create(
            business=business,
            warehouse=warehouse,
            defaults={
                'pickup_location_title': f"WH: {warehouse.name}",
                'locality': warehouse.address or warehouse.city or '',
                'pickup_lat': warehouse.latitude,
                'pickup_lon': warehouse.longitude,
                'is_fulfilment_center': True,
                'pickup_status': pickup_status,
            }
        )
        action = 'Created' if was_created else 'Updated'
        logger.info(
            f"{action} PickupLocation for {business.business_name} "
            f"linked to warehouse {warehouse.code}"
        )
    except Exception as e:
        logger.exception(
            f"Error syncing PickupLocation for SellerWarehouseLink "
            f"{business.business_name} → {warehouse.code}: {e}"
        )


@receiver(post_delete, sender='warehouse.SellerWarehouseLink', dispatch_uid='warehouse.seller_warehouse_link_post_delete')
def seller_warehouse_link_post_delete(sender, instance, **kwargs):
    """
    When a SellerWarehouseLink is deleted, set the matching PickupLocation
    to inactive.
    """
    from business.models import PickupLocation

    try:
        updated = PickupLocation.objects.filter(
            business=instance.business,
            warehouse=instance.warehouse,
        ).update(pickup_status='inactive')

        if updated:
            logger.info(
                f"Deactivated PickupLocation for {instance.business.business_name} "
                f"unlinked from warehouse {instance.warehouse.code}"
            )
    except Exception as e:
        logger.exception(
            f"Error deactivating PickupLocation on SellerWarehouseLink delete: {e}"
        )
