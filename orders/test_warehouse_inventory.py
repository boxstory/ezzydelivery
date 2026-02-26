"""
Test warehouse inventory adjustments on delivery task status changes.

This test verifies that:
1. Inventory decreases when delivery status changes to 'picked_up'
2. Inventory increases when delivery status changes to 'failed' (return)
3. Inventory remains the same on 'delivered' (already decreased on pickup)
4. InventoryTransaction records are created for audit trail
"""

from decimal import Decimal
from django.test import TestCase
from django.contrib.auth.models import User

from business import models as business_models
from orders import models as orders_models
from delivery import models as delivery_models
from warehouse import models as warehouse_models
from product import models as product_models


class WarehouseInventoryAdjustmentTest(TestCase):
    """Test automatic warehouse inventory adjustments based on delivery task status."""

    def setUp(self):
        """Set up test data: business, warehouse, product, order."""
        # Create user
        self.user = User.objects.create_user(
            username='testbusiness',
            password='testpass123'
        )

        # Create business with fulfillment enabled
        self.business = business_models.Business.objects.create(
            business_id=999,  # Custom primary key
            user=self.user,
            business_name='Test Business',
            business_code='TESTBIZ',
            fulfillment_service_enabled=True,
            fulfillment_service_status='active'
        )

        # Create warehouse
        self.warehouse = warehouse_models.Warehouse.objects.create(
            name='Test Warehouse',
            code='WH001',
            address='Test Address'
        )

        # Create storage location (internal warehouse storage)
        self.storage_location = warehouse_models.StorageLocation.objects.create(
            warehouse=self.warehouse,
            name='Aisle A - Rack 01',
            code='A-01',
            barcode='BAR-A-01-TEST'
        )

        # Create warehouse location (pickup/dispatch location)
        self.warehouse_location = warehouse_models.WarehouseLocation.objects.create(
            warehouse=self.warehouse,
            name='Main Pickup Point',
            code='PICKUP-01',
            is_active=True,
            is_default=True
        )

        # Link warehouse to business
        self.warehouse_link = warehouse_models.SellerWarehouseLink.objects.create(
            business=self.business,
            warehouse=self.warehouse,
            default_location=self.warehouse_location,
            is_active=True,
            is_default=True
        )

        # Create product
        self.product = product_models.Product.objects.create(
            brand_name='Test Brand',
            item_name='Test Product',
            item_sku='TEST-SKU-001',
            business=self.business,
            item_price=50
        )

        # Create initial stock level (warehouse-level, not tied to specific location)
        self.stock_level = warehouse_models.StockLevel.objects.create(
            warehouse=self.warehouse,
            product=self.product,
            location=None,  # Warehouse-level stock
            quantity_on_hand=100,
            quantity_reserved=0
        )

        # Create pickup location
        self.pickup_location = business_models.PickupLocation.objects.create(
            business=self.business,
            pickup_location_title='Main Store',
            locality='Doha'
        )

        # Create order
        self.order = orders_models.Order.objects.create(
            business=self.business,
            order_number='TEST-ORDER-001',
            customer_name='Test Customer',
            customer_phone='+97412345678',
            pickup_location=self.pickup_location,
            order_status='pending',
            verification_status='verified'
        )

        # Create order item with product
        self.order_item = orders_models.OrderItem.objects.create(
            order=self.order,
            product=self.product,
            quantity=5,
            unit_price=Decimal('50.00')
        )

        # Create delivery address
        self.address = delivery_models.DlAddressUpdate.objects.create(
            order=self.order,
            full_name='Test Customer',
            mobile_no='+97412345678',
            dl_task_number='TEST-ORDER-001'
        )

        # Create delivery task
        self.delivery_task = delivery_models.DeliveryTask.objects.create(
            order=self.order,
            business=self.business,
            dl_task_number='TEST-ORDER-001',
            dl_task_description='Test Delivery',
            dl_task_status='pending',
            dl_task_status_client='for_review',
            dl_address_update=self.address,
            pickup_location=self.pickup_location
        )

    def test_inventory_decreases_on_picked_up(self):
        """Test that inventory decreases when task status changes to picked_up."""
        # Initial stock
        initial_stock = self.stock_level.quantity_on_hand

        # Change status to picked_up
        self.delivery_task.dl_task_status = 'picked_up'
        self.delivery_task.save()

        # Refresh stock level from database
        self.stock_level.refresh_from_db()

        # Verify inventory decreased by order quantity (5 units)
        self.assertEqual(
            self.stock_level.quantity_on_hand,
            initial_stock - self.order_item.quantity,
            "Stock on hand should decrease by order quantity"
        )

        # Verify transaction record created
        transaction = warehouse_models.InventoryTransaction.objects.filter(
            product=self.product,
            transaction_type='ship',
            reference_type='delivery_task'
        ).last()

        self.assertIsNotNone(transaction, "Inventory transaction should be created")
        self.assertEqual(transaction.quantity, self.order_item.quantity)

    def test_inventory_increases_on_failed_delivery(self):
        """Test that inventory increases when task fails (returned to warehouse)."""
        # First pick up the order (decrease inventory)
        self.delivery_task.dl_task_status = 'picked_up'
        self.delivery_task.save()

        # Get stock after pickup
        self.stock_level.refresh_from_db()
        stock_after_pickup = self.stock_level.quantity_on_hand

        # Now fail the delivery (return to warehouse)
        self.delivery_task.dl_task_status = 'failed'
        self.delivery_task.save()

        # Refresh stock level
        self.stock_level.refresh_from_db()

        # Verify inventory increased back
        self.assertEqual(
            self.stock_level.quantity_on_hand,
            stock_after_pickup + self.order_item.quantity,
            "Stock should increase when delivery fails"
        )

        # Verify return transaction created
        return_transaction = warehouse_models.InventoryTransaction.objects.filter(
            product=self.product,
            transaction_type='return',
            reference_type='delivery_task'
        ).last()

        self.assertIsNotNone(return_transaction, "Return transaction should be created")
        self.assertEqual(return_transaction.quantity, self.order_item.quantity)

    def test_inventory_unchanged_on_delivered(self):
        """Test that inventory doesn't change on delivered (already adjusted on pickup)."""
        # First pick up the order
        self.delivery_task.dl_task_status = 'picked_up'
        self.delivery_task.save()

        # Get stock after pickup
        self.stock_level.refresh_from_db()
        stock_after_pickup = self.stock_level.quantity_on_hand

        # Now mark as delivered
        self.delivery_task.dl_task_status = 'delivered'
        self.delivery_task.save()

        # Refresh stock level
        self.stock_level.refresh_from_db()

        # Verify inventory unchanged
        self.assertEqual(
            self.stock_level.quantity_on_hand,
            stock_after_pickup,
            "Stock should not change on delivered (already decreased on pickup)"
        )

    def test_no_adjustment_without_fulfillment(self):
        """Test that no inventory adjustment happens if fulfillment is disabled."""
        # Disable fulfillment for business
        self.business.fulfillment_service_enabled = False
        self.business.save()

        # Get initial stock
        initial_stock = self.stock_level.quantity_on_hand

        # Change status to picked_up
        self.delivery_task.dl_task_status = 'picked_up'
        self.delivery_task.save()

        # Refresh stock level
        self.stock_level.refresh_from_db()

        # Verify inventory unchanged
        self.assertEqual(
            self.stock_level.quantity_on_hand,
            initial_stock,
            "Stock should not change when fulfillment is disabled"
        )

    def test_no_adjustment_for_non_product_orders(self):
        """Test that no adjustment happens for orders without product references."""
        # Remove product reference from order item
        self.order_item.product = None
        self.order_item.save()

        # Get initial stock
        initial_stock = self.stock_level.quantity_on_hand

        # Change status to picked_up
        self.delivery_task.dl_task_status = 'picked_up'
        self.delivery_task.save()

        # Refresh stock level
        self.stock_level.refresh_from_db()

        # Verify inventory unchanged
        self.assertEqual(
            self.stock_level.quantity_on_hand,
            initial_stock,
            "Stock should not change for orders without product references"
        )
