import logging
from django.db import transaction
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
    """
    from warehouse.models import StockLevel, StockReservation, InventoryTransaction
    from orders.models import OrderItem

    try:
        order_items = OrderItem.objects.filter(order=order).select_related('product')

        for item in order_items:
            # Find available stock for this product
            stock_levels = StockLevel.objects.filter(
                product=item.product,
                warehouse__business=order.business,
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
            stock_level.quantity_reserved -= reservation.quantity
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

        logger.info(f"Stock reservations released for order {order.order_number}")

    except Exception as e:
        logger.exception(f"Error releasing stock for order {order.order_number}: {str(e)}")


def fulfill_stock_reservation(order):
    """
    Fulfill (deduct) stock when delivery is successful.
    Converts reserved stock to shipped.
    """
    from warehouse.models import StockReservation, InventoryTransaction

    try:
        reservations = StockReservation.objects.filter(
            order=order,
            status='active'
        ).select_related('stock_level', 'order_item__product')

        for reservation in reservations:
            stock_level = reservation.stock_level
            old_on_hand = stock_level.quantity_on_hand
            old_reserved = stock_level.quantity_reserved

            # Deduct from on_hand and reserved
            stock_level.quantity_on_hand -= reservation.quantity
            stock_level.quantity_reserved -= reservation.quantity
            stock_level.save(update_fields=['quantity_on_hand', 'quantity_reserved', 'updated_at'])

            # Update reservation status
            reservation.status = 'fulfilled'
            reservation.released_at = timezone.now()
            reservation.save(update_fields=['status', 'released_at', 'updated_at'])

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

            # Check for low stock alert
            check_and_create_low_stock_alert(stock_level)

        logger.info(f"Stock fulfilled for order {order.order_number}")

    except Exception as e:
        logger.exception(f"Error fulfilling stock for order {order.order_number}: {str(e)}")


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


# =============================================================================
# SIGNAL RECEIVERS
# =============================================================================

@receiver(pre_save, sender='orders.Order')
def order_pre_save_handler(sender, instance, *args, **kwargs):
    """Track order status changes"""
    if instance.pk:
        try:
            from orders.models import Order
            old_instance = Order.objects.get(pk=instance.pk)
            _old_order_status[instance.pk] = old_instance.order_status
        except sender.DoesNotExist:
            pass


@receiver(post_save, sender='orders.Order')
def order_post_save_handler(sender, instance, created, *args, **kwargs):
    """
    Handle order status changes for stock reservation/release.
    """
    if created:
        return

    old_status = _old_order_status.pop(instance.pk, None)

    # Reserve stock when order is ready for pickup
    if (old_status != 'ready_to_pickup' and
            instance.order_status == 'ready_to_pickup' and
            not getattr(instance, 'stock_reserved', False)):
        with transaction.atomic():
            reserve_stock_for_order(instance)

    # Release stock when order is cancelled
    elif (old_status != 'cancelled' and
          instance.order_status == 'cancelled'):
        with transaction.atomic():
            release_stock_reservation(instance)


@receiver(pre_save, sender='delivery.DeliveryTask')
def delivery_task_pre_save_handler(sender, instance, *args, **kwargs):
    """Track delivery task status changes"""
    if instance.pk:
        try:
            from delivery.models import DeliveryTask
            old_instance = DeliveryTask.objects.get(pk=instance.pk)
            _old_delivery_status[instance.pk] = old_instance.dl_task_status_dms
        except sender.DoesNotExist:
            pass


@receiver(post_save, sender='delivery.DeliveryTask')
def delivery_task_post_save_handler(sender, instance, created, *args, **kwargs):
    """
    Handle delivery completion for stock fulfillment.
    """
    if created:
        return

    old_status = _old_delivery_status.pop(instance.pk, None)

    # Fulfill stock when delivery is successful (DMS status '2')
    if old_status != '2' and instance.dl_task_status_dms == '2':
        if instance.order:
            with transaction.atomic():
                fulfill_stock_reservation(instance.order)


@receiver(post_save, sender='warehouse.StockLevel')
def stock_level_post_save_handler(sender, instance, created, *args, **kwargs):
    """
    Check for low stock after stock level changes.
    """
    check_and_create_low_stock_alert(instance)


# =============================================================================
# SELLER WAREHOUSE LINK SIGNALS
# Auto-sync PickupLocation when a business is linked/unlinked to a warehouse
# =============================================================================

@receiver(post_save, sender='warehouse.SellerWarehouseLink')
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


@receiver(post_delete, sender='warehouse.SellerWarehouseLink')
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
