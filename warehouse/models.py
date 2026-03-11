"""
Warehouse Models Module
=======================

This module contains models for warehouse and inventory management.

Models:
    Warehouse Management:
        - Warehouse: Physical warehouse/storage facility
        - StorageLocation: Hierarchical storage locations (zone/aisle/rack/shelf/bin)

    Inventory:
        - StockLevel: Current stock quantities per product/location
        - InventoryTransaction: Audit trail for all inventory movements
        - StockReservation: Reserved stock for pending orders

    Operations:
        - PickList: Grouped items to be picked for orders
        - PickListItem: Individual items within a pick list
        - CycleCount: Scheduled inventory counts
        - CycleCountItem: Items within a cycle count

    Alerts:
        - LowStockAlert: Notifications when stock falls below reorder point

Related:
    - product.models.Product: Products stored in warehouse
    - orders.models.Order: Orders that reserve/consume inventory
    - business.models.Business: Business that owns the warehouse
"""

import uuid
import logging
from django.db import models
from django.conf import settings

from business import models as business_models
from product import models as product_models

logger = logging.getLogger('warehouse')


# =============================================================================
# CHOICES - Constants for model field choices
# =============================================================================

# Location types for hierarchical storage organization

LOCATION_TYPE_CHOICES = [
    ('zone', 'Zone'),
    ('aisle', 'Aisle'),
    ('rack', 'Rack'),
    ('shelf', 'Shelf'),
    ('bin', 'Bin'),
]

TRANSACTION_TYPE_CHOICES = [
    ('receive', 'Receive'),
    ('ship', 'Ship'),
    ('adjust_in', 'Adjustment In'),
    ('adjust_out', 'Adjustment Out'),
    ('transfer_in', 'Transfer In'),
    ('transfer_out', 'Transfer Out'),
    ('reserve', 'Reserve'),
    ('unreserve', 'Unreserve'),
    ('count', 'Cycle Count'),
    ('return', 'Return'),
]

RESERVATION_STATUS_CHOICES = [
    ('active', 'Active'),
    ('released', 'Released'),
    ('fulfilled', 'Fulfilled'),
    ('returned', 'Returned'),
    ('cancelled', 'Cancelled'),
]

PICKLIST_STATUS_CHOICES = [
    ('pending', 'Pending'),
    ('assigned', 'Assigned'),
    ('in_progress', 'In Progress'),
    ('completed', 'Completed'),
    ('cancelled', 'Cancelled'),
]

CYCLE_COUNT_STATUS_CHOICES = [
    ('scheduled', 'Scheduled'),
    ('in_progress', 'In Progress'),
    ('pending_review', 'Pending Review'),
    ('approved', 'Approved'),
    ('completed', 'Completed'),
]

ABC_CLASSIFICATION_CHOICES = [
    ('A', 'A - High Value'),
    ('B', 'B - Medium Value'),
    ('C', 'C - Low Value'),
]

ALERT_STATUS_CHOICES = [
    ('active', 'Active'),
    ('acknowledged', 'Acknowledged'),
    ('resolved', 'Resolved'),
]


# =============================================================================
# WAREHOUSE MODEL (FULFILLMENT CENTER)
# Independent entity managed by staff only - NOT owned by sellers
# Represents a physical fulfillment center with multiple locations
# Auto-generates warehouse code if not provided: WH-FC-{uuid}
# =============================================================================


class Warehouse(models.Model):
    """
    Fulfillment Center - Independent warehouse entity managed by staff.

    This is a warehouse-first architecture where:
    - Warehouses are NOT owned by sellers
    - Staff creates and manages all warehouses
    - Multiple sellers can be linked to one warehouse
    - One seller can be linked to multiple warehouses
    """
    name = models.CharField(max_length=200, help_text="Fulfillment center name")
    code = models.CharField(max_length=50, unique=True, db_index=True, help_text="Unique warehouse code")
    description = models.TextField(blank=True, help_text="Warehouse description and details")

    # Address and contact info
    address = models.TextField(blank=True)
    city = models.CharField(max_length=100, blank=True)
    state = models.CharField(max_length=100, blank=True)
    postal_code = models.CharField(max_length=20, blank=True)
    country = models.CharField(max_length=100, default='Bahrain')

    # GPS coordinates for distance-based auto-selection
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)

    # Contact information
    phone = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)

    # Capacity Configuration - Internal warehouse structure
    total_zones = models.IntegerField(
        default=0,
        help_text="Total number of zones in this warehouse"
    )
    racks_per_zone = models.IntegerField(
        default=0,
        help_text="Number of racks in each zone"
    )
    shelves_per_rack = models.IntegerField(
        default=0,
        help_text="Number of shelves in each rack"
    )
    bins_per_shelf = models.IntegerField(
        default=0,
        help_text="Number of bins in each shelf"
    )

    # Naming configuration (stores JSON for custom naming patterns)
    zone_naming_pattern = models.CharField(
        max_length=50,
        default='A,B,C,D',
        help_text="Zone naming pattern (e.g., 'A,B,C' or '1,2,3' or 'NORTH,SOUTH')"
    )
    rack_naming_pattern = models.CharField(
        max_length=20,
        default='numeric',
        choices=[('numeric', 'Numeric (01, 02, 03...)'), ('alpha', 'Alpha (A, B, C...)')],
        help_text="How to name racks within zones"
    )
    shelf_naming_pattern = models.CharField(
        max_length=20,
        default='numeric',
        choices=[('numeric', 'Numeric (01, 02, 03...)'), ('alpha', 'Alpha (A, B, C...)')],
        help_text="How to name shelves within racks"
    )
    bin_naming_pattern = models.CharField(
        max_length=20,
        default='numeric',
        choices=[('numeric', 'Numeric (01, 02, 03...)'), ('alpha', 'Alpha (A, B, C...)')],
        help_text="How to name bins within shelves"
    )

    # Capacity tracking
    is_capacity_configured = models.BooleanField(
        default=False,
        help_text="Has the warehouse capacity been configured?"
    )
    capacity_configured_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When was capacity configuration completed?"
    )
    capacity_configured_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='configured_warehouse_capacity',
        help_text="Who configured the warehouse capacity"
    )

    # Status and management
    is_active = models.BooleanField(default=True, help_text="Is this warehouse operational?")
    is_default = models.BooleanField(default=False, help_text="Is this the default fulfillment center?")

    # Staff management
    manager = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='managed_warehouses',
        help_text="Staff member managing this warehouse"
    )

    # Timestamps
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_warehouses',
        help_text="Staff who created this warehouse"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Fulfillment Center'
        verbose_name_plural = 'Fulfillment Centers'
        ordering = ['-is_default', 'name']
        indexes = [
            models.Index(fields=['is_active', 'name'], name='wh_fc_active_name_idx'),
            models.Index(fields=['code'], name='wh_fc_code_idx'),
        ]

    def __str__(self):
        return f"{self.code} - {self.name}"

    def save(self, *args, **kwargs):
        if not self.code:
            # Auto-generate code if not provided: WH-FC-{unique_id}
            self.code = f"WH-FC-{uuid.uuid4().hex[:8].upper()}"
        super().save(*args, **kwargs)

    @property
    def total_capacity(self):
        """Calculate total storage locations (bins) based on configuration"""
        if not self.is_capacity_configured:
            return 0
        return (self.total_zones * self.racks_per_zone *
                self.shelves_per_rack * self.bins_per_shelf)

    @property
    def total_racks(self):
        """Total number of racks across all zones"""
        return self.total_zones * self.racks_per_zone if self.total_zones else 0

    @property
    def total_shelves(self):
        """Total number of shelves across all zones"""
        return (self.total_zones * self.racks_per_zone *
                self.shelves_per_rack) if self.total_zones else 0

    def get_zone_names(self):
        """Get list of zone names based on naming pattern"""
        if not self.zone_naming_pattern:
            return []
        zones = [z.strip() for z in self.zone_naming_pattern.split(',')]
        return zones[:self.total_zones] if self.total_zones else zones

    def generate_location_name(self, location_type, index):
        """Generate a name for a location based on the naming pattern"""
        if location_type == 'rack':
            pattern = self.rack_naming_pattern
        elif location_type == 'shelf':
            pattern = self.shelf_naming_pattern
        elif location_type == 'bin':
            pattern = self.bin_naming_pattern
        else:
            return str(index)

        if pattern == 'numeric':
            return f"{index:02d}"
        elif pattern == 'alpha':
            # Convert index to letter (1=A, 2=B, etc.)
            if index <= 26:
                return chr(64 + index)  # 65 is 'A'
            else:
                # For > 26, use AA, AB, AC, etc.
                first = chr(64 + ((index - 1) // 26))
                second = chr(65 + ((index - 1) % 26))
                return f"{first}{second}"
        return str(index)


# =============================================================================
# WAREHOUSE LOCATION MODEL
# Multiple physical locations within a fulfillment center
# Each location can serve different delivery zones
# =============================================================================


class WarehouseLocation(models.Model):
    """
    Physical location within a fulfillment center.

    A warehouse can have multiple pickup/dispatch locations.
    Staff selects the appropriate location during delivery task assignment
    based on customer location and stock availability.
    """
    warehouse = models.ForeignKey(
        Warehouse,
        on_delete=models.CASCADE,
        related_name='pickup_locations',
        db_index=True,
        help_text="Parent fulfillment center"
    )
    name = models.CharField(max_length=200, help_text="Location name (e.g., 'North Gate', 'Main Entrance')")
    code = models.CharField(max_length=50, db_index=True, help_text="Location code within warehouse")

    # Address details
    address = models.TextField(blank=True, help_text="Specific address or directions")
    zone_number = models.IntegerField(null=True, blank=True, help_text="Delivery zone number")

    # GPS coordinates for location-based selection
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)

    # Status
    is_active = models.BooleanField(default=True, help_text="Is this location operational?")
    is_default = models.BooleanField(default=False, help_text="Is this the default location for the warehouse?")

    # Operating information
    operating_hours = models.TextField(blank=True, help_text="Operating hours for pickup")
    notes = models.TextField(blank=True, help_text="Special instructions for drivers")

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Warehouse Location'
        verbose_name_plural = 'Warehouse Locations'
        unique_together = ['warehouse', 'code']
        ordering = ['warehouse', '-is_default', 'name']
        indexes = [
            models.Index(fields=['warehouse', 'is_active'], name='wh_loc_wh_active_idx'),
            models.Index(fields=['zone_number'], name='wh_loc_zone_num_idx'),
        ]

    def __str__(self):
        return f"{self.warehouse.code}/{self.name}"

    @property
    def full_code(self):
        """Returns warehouse code + location code"""
        return f"{self.warehouse.code}-{self.code}"


# =============================================================================
# SELLER WAREHOUSE LINK MODEL
# Many-to-many relationship between sellers and warehouses
# Allows flexible warehouse assignment and default settings
# =============================================================================


class SellerWarehouseLink(models.Model):
    """
    Links sellers (businesses) to fulfillment centers.

    This creates a many-to-many relationship where:
    - One seller can connect to multiple warehouses
    - One warehouse can serve multiple sellers
    - Each seller has a default warehouse and location
    - Link can be created/removed by staff at any time
    """
    business = models.ForeignKey(
        business_models.Business,
        on_delete=models.CASCADE,
        related_name='warehouse_links',
        db_index=True,
        help_text="Seller/business using this warehouse"
    )
    warehouse = models.ForeignKey(
        Warehouse,
        on_delete=models.CASCADE,
        related_name='seller_links',
        db_index=True,
        help_text="Fulfillment center serving this seller"
    )
    default_location = models.ForeignKey(
        WarehouseLocation,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='default_for_sellers',
        help_text="Default pickup location for this seller at this warehouse"
    )

    # Priority and settings
    is_default = models.BooleanField(
        default=False,
        help_text="Is this the default warehouse for this seller?"
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Is this link active?"
    )
    priority = models.IntegerField(
        default=0,
        help_text="Selection priority (higher = preferred). Used for auto-selection."
    )

    # Timestamps and management
    linked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_warehouse_links',
        help_text="Staff who created this link"
    )
    linked_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Notes
    notes = models.TextField(blank=True, help_text="Special notes about this warehouse-seller relationship")

    class Meta:
        verbose_name = 'Seller Warehouse Link'
        verbose_name_plural = 'Seller Warehouse Links'
        unique_together = ['business', 'warehouse']
        ordering = ['business', '-is_default', '-priority', 'warehouse']
        indexes = [
            models.Index(fields=['business', 'is_active'], name='wh_link_biz_active_idx'),
            models.Index(fields=['warehouse', 'is_active'], name='wh_link_wh_active_idx'),
            models.Index(fields=['business', 'is_default'], name='wh_link_biz_default_idx'),
        ]

    def __str__(self):
        default_tag = " [DEFAULT]" if self.is_default else ""
        return f"{self.business.business_name} → {self.warehouse.name}{default_tag}"

    def save(self, *args, **kwargs):
        # Ensure default_location belongs to the selected warehouse
        if self.default_location and self.default_location.warehouse != self.warehouse:
            raise ValueError(f"Default location must belong to warehouse {self.warehouse.code}")

        # If this is being set as default, unset other defaults for this business
        if self.is_default:
            SellerWarehouseLink.objects.filter(
                business=self.business,
                is_default=True
            ).exclude(pk=self.pk).update(is_default=False)

        super().save(*args, **kwargs)


# =============================================================================
# STORAGE LOCATION MODEL
# =============================================================================

class StorageLocation(models.Model):
    """
    Hierarchical storage locations within a warehouse.
    Supports zones, aisles, racks, shelves, and bins.
    NOTE: This is for internal warehouse storage (racks, bins, etc.)
    NOT for pickup/dispatch locations - see WarehouseLocation for that.
    """
    warehouse = models.ForeignKey(
        Warehouse,
        on_delete=models.CASCADE,
        related_name='storage_locations',
        db_index=True
    )
    parent = models.ForeignKey(
        'self',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='children'
    )
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=50, db_index=True)  # e.g., "A-01-03-B"
    barcode = models.CharField(max_length=100, unique=True, db_index=True)
    location_type = models.CharField(
        max_length=20,
        choices=LOCATION_TYPE_CHOICES,
        default='bin'
    )
    # Dimensions (in cm)
    width_cm = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True, help_text="Width in cm")
    length_cm = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True, help_text="Length in cm")
    height_cm = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True, help_text="Height in cm")
    max_weight_kg = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True, help_text="Max weight capacity in kg")

    is_pickable = models.BooleanField(default=True)  # Can pick from this location
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Storage Location'
        verbose_name_plural = 'Storage Locations'
        unique_together = ['warehouse', 'code']
        ordering = ['warehouse', 'code']
        indexes = [
            models.Index(fields=['warehouse', 'location_type'], name='wh_loc_type_idx'),
            models.Index(fields=['barcode'], name='wh_loc_barcode_idx'),
        ]

    def __str__(self):
        return f"{self.warehouse.code}/{self.code}"

    def save(self, *args, **kwargs):
        if not self.barcode:
            # Auto-generate barcode if not provided
            self.barcode = f"LOC-{self.warehouse.code}-{self.code}-{uuid.uuid4().hex[:4].upper()}"
        super().save(*args, **kwargs)

    @property
    def full_path(self):
        """Returns the full path from zone to this location"""
        path = [self.code]
        parent = self.parent
        while parent:
            path.insert(0, parent.code)
            parent = parent.parent
        return '/'.join(path)


# =============================================================================
# STOCK LEVEL MODEL
# =============================================================================

class StockLevel(models.Model):
    """
    Tracks inventory quantities for a product at a specific warehouse/location.
    """
    product = models.ForeignKey(
        product_models.Product,
        on_delete=models.CASCADE,
        related_name='stock_levels',
        db_index=True
    )
    warehouse = models.ForeignKey(
        Warehouse,
        on_delete=models.CASCADE,
        related_name='stock_levels',
        db_index=True
    )
    location = models.ForeignKey(
        StorageLocation,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='stock_levels'
    )
    quantity_on_hand = models.IntegerField(default=0)
    quantity_reserved = models.IntegerField(default=0)  # Reserved for pending orders
    quantity_incoming = models.IntegerField(default=0)  # Expected from POs
    reorder_point = models.IntegerField(default=0)
    reorder_quantity = models.IntegerField(default=0)
    abc_classification = models.CharField(
        max_length=1,
        choices=ABC_CLASSIFICATION_CHOICES,
        default='C',
        db_index=True
    )
    last_count_date = models.DateTimeField(null=True, blank=True)
    last_count_quantity = models.IntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Stock Level'
        verbose_name_plural = 'Stock Levels'
        unique_together = ['product', 'warehouse', 'location']
        ordering = ['warehouse', 'product']
        indexes = [
            models.Index(fields=['product', 'warehouse'], name='wh_stock_prod_wh_idx'),
            models.Index(fields=['warehouse', '-quantity_on_hand'], name='wh_stock_qty_idx'),
            models.Index(fields=['abc_classification'], name='wh_stock_abc_idx'),
        ]

    def __str__(self):
        loc = f"/{self.location.code}" if self.location else ""
        return f"{self.product.item_sku} @ {self.warehouse.code}{loc}"

    @property
    def quantity_available(self):
        """Available quantity = on hand - reserved"""
        return self.quantity_on_hand - self.quantity_reserved

    @property
    def is_low_stock(self):
        """Check if stock is at or below reorder point"""
        return self.reorder_point > 0 and self.quantity_available <= self.reorder_point

    @property
    def is_out_of_stock(self):
        """Check if completely out of stock"""
        return self.quantity_available <= 0


# =============================================================================
# INVENTORY TRANSACTION MODEL
# =============================================================================

class InventoryTransaction(models.Model):
    """
    Audit trail for all inventory movements.
    Every stock change is recorded with before/after quantities.
    """
    transaction_number = models.CharField(max_length=50, unique=True, db_index=True)
    product = models.ForeignKey(
        product_models.Product,
        on_delete=models.PROTECT,
        related_name='inventory_transactions',
        db_index=True
    )
    warehouse = models.ForeignKey(
        Warehouse,
        on_delete=models.PROTECT,
        related_name='transactions',
        db_index=True
    )
    location = models.ForeignKey(
        StorageLocation,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='transactions'
    )
    transaction_type = models.CharField(
        max_length=20,
        choices=TRANSACTION_TYPE_CHOICES,
        db_index=True
    )
    quantity = models.IntegerField()  # Positive for in, negative for out
    quantity_before = models.IntegerField()
    quantity_after = models.IntegerField()
    reference_type = models.CharField(max_length=50, blank=True)  # 'order', 'transfer', 'count'
    reference_id = models.CharField(max_length=100, blank=True)  # Order number, etc.
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='inventory_transactions'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Inventory Transaction'
        verbose_name_plural = 'Inventory Transactions'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['product', '-created_at'], name='wh_txn_prod_date_idx'),
            models.Index(fields=['warehouse', 'transaction_type', '-created_at'], name='wh_txn_wh_type_idx'),
            models.Index(fields=['reference_type', 'reference_id'], name='wh_txn_ref_idx'),
        ]

    def __str__(self):
        return f"{self.transaction_number} - {self.transaction_type} - {self.quantity}"

    def save(self, *args, **kwargs):
        if not self.transaction_number:
            # Auto-generate transaction number
            self.transaction_number = f"TXN-{uuid.uuid4().hex[:12].upper()}"
        super().save(*args, **kwargs)


# =============================================================================
# STOCK RESERVATION MODEL
# =============================================================================

class StockReservation(models.Model):
    """
    Reserves stock for pending orders.
    Released when order is fulfilled or cancelled.
    """
    order = models.ForeignKey(
        'orders.Order',
        on_delete=models.CASCADE,
        related_name='stock_reservations',
        db_index=True
    )
    order_item = models.ForeignKey(
        'orders.OrderItem',
        on_delete=models.CASCADE,
        related_name='stock_reservations'
    )
    stock_level = models.ForeignKey(
        StockLevel,
        on_delete=models.CASCADE,
        related_name='reservations'
    )
    quantity = models.IntegerField()
    status = models.CharField(
        max_length=20,
        choices=RESERVATION_STATUS_CHOICES,
        default='active',
        db_index=True
    )
    reserved_at = models.DateTimeField(auto_now_add=True)
    released_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Stock Reservation'
        verbose_name_plural = 'Stock Reservations'
        ordering = ['-reserved_at']
        indexes = [
            models.Index(fields=['order', 'status'], name='wh_res_order_status_idx'),
            models.Index(fields=['stock_level', 'status'], name='wh_res_stock_status_idx'),
        ]

    def __str__(self):
        return f"Reservation {self.id} - Order {self.order.order_number} - {self.quantity} units"


# =============================================================================
# PICK LIST MODELS
# =============================================================================

class PickList(models.Model):
    """
    A pick list groups items to be picked from the warehouse.
    Supports wave picking for multiple orders.
    """
    pick_number = models.CharField(max_length=50, unique=True, db_index=True)
    warehouse = models.ForeignKey(
        Warehouse,
        on_delete=models.CASCADE,
        related_name='pick_lists'
    )
    wave_number = models.CharField(max_length=50, blank=True, db_index=True)
    status = models.CharField(
        max_length=20,
        choices=PICKLIST_STATUS_CHOICES,
        default='pending',
        db_index=True
    )
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assigned_picks'
    )
    assigned_at = models.DateTimeField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    total_items = models.IntegerField(default=0)
    picked_items = models.IntegerField(default=0)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_picks'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Pick List'
        verbose_name_plural = 'Pick Lists'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.pick_number} - {self.status}"

    def save(self, *args, **kwargs):
        if not self.pick_number:
            self.pick_number = f"PICK-{uuid.uuid4().hex[:10].upper()}"
        super().save(*args, **kwargs)

    @property
    def progress_percentage(self):
        """Calculate picking progress percentage"""
        if self.total_items == 0:
            return 0
        return int((self.picked_items / self.total_items) * 100)


class PickListItem(models.Model):
    """
    Individual items within a pick list.
    """
    pick_list = models.ForeignKey(
        PickList,
        on_delete=models.CASCADE,
        related_name='items'
    )
    order = models.ForeignKey(
        'orders.Order',
        on_delete=models.CASCADE,
        related_name='pick_list_items'
    )
    order_item = models.ForeignKey(
        'orders.OrderItem',
        on_delete=models.CASCADE,
        related_name='pick_list_items'
    )
    product = models.ForeignKey(
        product_models.Product,
        on_delete=models.PROTECT,
        related_name='pick_list_items'
    )
    location = models.ForeignKey(
        StorageLocation,
        on_delete=models.SET_NULL,
        null=True,
        related_name='pick_list_items'
    )
    quantity_to_pick = models.IntegerField()
    quantity_picked = models.IntegerField(default=0)
    is_picked = models.BooleanField(default=False)
    picked_at = models.DateTimeField(null=True, blank=True)
    picked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='picked_items'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Pick List Item'
        verbose_name_plural = 'Pick List Items'
        ordering = ['pick_list', 'location__code']

    def __str__(self):
        return f"{self.pick_list.pick_number} - {self.product.item_sku} x {self.quantity_to_pick}"


# =============================================================================
# CYCLE COUNT MODELS
# =============================================================================

class CycleCount(models.Model):
    """
    Scheduled inventory counts for accuracy verification.
    """
    count_number = models.CharField(max_length=50, unique=True, db_index=True)
    warehouse = models.ForeignKey(
        Warehouse,
        on_delete=models.CASCADE,
        related_name='cycle_counts'
    )
    location = models.ForeignKey(
        StorageLocation,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='cycle_counts'
    )
    status = models.CharField(
        max_length=20,
        choices=CYCLE_COUNT_STATUS_CHOICES,
        default='scheduled',
        db_index=True
    )
    scheduled_date = models.DateField(db_index=True)
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assigned_counts'
    )
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='approved_counts'
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_counts'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Cycle Count'
        verbose_name_plural = 'Cycle Counts'
        ordering = ['-scheduled_date']

    def __str__(self):
        return f"{self.count_number} - {self.status}"

    def save(self, *args, **kwargs):
        if not self.count_number:
            self.count_number = f"COUNT-{uuid.uuid4().hex[:10].upper()}"
        super().save(*args, **kwargs)

    @property
    def total_items(self):
        return self.items.count()

    @property
    def counted_items(self):
        return self.items.filter(is_counted=True).count()

    @property
    def total_variance(self):
        """Sum of all variances"""
        return self.items.filter(variance__isnull=False).aggregate(
            total=models.Sum('variance')
        )['total'] or 0


class CycleCountItem(models.Model):
    """
    Individual items within a cycle count.
    """
    cycle_count = models.ForeignKey(
        CycleCount,
        on_delete=models.CASCADE,
        related_name='items'
    )
    product = models.ForeignKey(
        product_models.Product,
        on_delete=models.PROTECT,
        related_name='cycle_count_items'
    )
    location = models.ForeignKey(
        StorageLocation,
        on_delete=models.SET_NULL,
        null=True,
        related_name='cycle_count_items'
    )
    system_quantity = models.IntegerField()  # Expected quantity from system
    counted_quantity = models.IntegerField(null=True, blank=True)
    variance = models.IntegerField(null=True, blank=True)  # counted - system
    variance_reason = models.TextField(blank=True)
    is_counted = models.BooleanField(default=False)
    counted_at = models.DateTimeField(null=True, blank=True)
    counted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='counted_items'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Cycle Count Item'
        verbose_name_plural = 'Cycle Count Items'
        ordering = ['cycle_count', 'location__code']

    def __str__(self):
        return f"{self.cycle_count.count_number} - {self.product.item_sku}"

    def save(self, *args, **kwargs):
        # Auto-calculate variance when counted_quantity is set
        if self.counted_quantity is not None:
            self.variance = self.counted_quantity - self.system_quantity
        super().save(*args, **kwargs)


# =============================================================================
# LOW STOCK ALERT MODEL
# =============================================================================

class LowStockAlert(models.Model):
    """
    Alerts generated when stock falls below reorder point.
    """
    stock_level = models.ForeignKey(
        StockLevel,
        on_delete=models.CASCADE,
        related_name='alerts'
    )
    product = models.ForeignKey(
        product_models.Product,
        on_delete=models.CASCADE,
        related_name='low_stock_alerts'
    )
    warehouse = models.ForeignKey(
        Warehouse,
        on_delete=models.CASCADE,
        related_name='low_stock_alerts'
    )
    quantity_available = models.IntegerField()
    reorder_point = models.IntegerField()
    status = models.CharField(
        max_length=20,
        choices=ALERT_STATUS_CHOICES,
        default='active',
        db_index=True
    )
    acknowledged_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='acknowledged_alerts'
    )
    acknowledged_at = models.DateTimeField(null=True, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Low Stock Alert'
        verbose_name_plural = 'Low Stock Alerts'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['warehouse', 'status', '-created_at'], name='wh_alert_status_idx'),
        ]

    def __str__(self):
        return f"Alert: {self.product.item_sku} @ {self.warehouse.code} - {self.quantity_available} units"


# =============================================================================
# PRODUCT REQUEST MODELS
# =============================================================================

# Product Request Status and Type Choices
PRODUCT_REQUEST_STATUS_CHOICES = [
    ('pending', 'Pending Approval'),
    ('approved', 'Approved'),
    ('completed', 'Completed'),
    ('cancelled', 'Cancelled'),
]

PRODUCT_REQUEST_TYPE_CHOICES = [
    ('inbound', 'Inbound - To Warehouse'),
    ('outbound', 'Outbound - From Warehouse'),
]


class ProductRequest(models.Model):
    """
    Abstract base model for product movement requests.

    Businesses with fulfillment service enabled can request:
    - Inbound: Send products to warehouse
    - Outbound: Receive products from warehouse

    Status workflow: pending → approved → completed
    """
    request_number = models.CharField(max_length=50, unique=True, editable=False, db_index=True)
    request_type = models.CharField(max_length=10, choices=PRODUCT_REQUEST_TYPE_CHOICES)
    business = models.ForeignKey(
        business_models.Business,
        on_delete=models.CASCADE,
        related_name='%(class)s_requests'
    )
    warehouse = models.ForeignKey(
        Warehouse,
        on_delete=models.CASCADE,
        related_name='%(class)s_requests',
        help_text="Target warehouse for this request"
    )
    status = models.CharField(
        max_length=20,
        choices=PRODUCT_REQUEST_STATUS_CHOICES,
        default='pending',
        db_index=True
    )
    notes = models.TextField(blank=True, help_text="Special instructions or notes")

    # Workflow tracking
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='%(class)s_created'
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='%(class)s_approved'
    )
    completed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='%(class)s_completed'
    )

    approved_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', '-created_at'], name='wh_req_status_created_idx'),
        ]

    def save(self, *args, **kwargs):
        if not self.request_number:
            prefix = 'INB' if self.request_type == 'inbound' else 'OUT'
            self.request_number = f"{prefix}-{uuid.uuid4().hex[:8].upper()}"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.request_number} - {self.business.business_name}"


class InboundProductRequest(ProductRequest):
    """
    Requests to send products TO the warehouse for storage.

    Businesses use this when they want to send inventory to the fulfillment center.
    """
    expected_delivery_date = models.DateField(
        null=True,
        blank=True,
        help_text="When business plans to deliver products"
    )

    def save(self, *args, **kwargs):
        self.request_type = 'inbound'
        super().save(*args, **kwargs)

    class Meta:
        verbose_name = "Inbound Product Request"
        verbose_name_plural = "Inbound Product Requests"
        ordering = ['-created_at']


class OutboundProductRequest(ProductRequest):
    """
    Requests to receive products FROM the warehouse for delivery/sale.

    Businesses use this when they need products shipped out from fulfillment center.
    """
    priority = models.CharField(
        max_length=10,
        choices=[('normal', 'Normal'), ('urgent', 'Urgent')],
        default='normal'
    )

    def save(self, *args, **kwargs):
        self.request_type = 'outbound'
        super().save(*args, **kwargs)

    class Meta:
        verbose_name = "Outbound Product Request"
        verbose_name_plural = "Outbound Product Requests"
        ordering = ['-created_at']


class ProductRequestItem(models.Model):
    """
    Individual product line items within a request.

    Each request can have multiple products with quantities.
    Tracks requested vs fulfilled quantities for partial fulfillment.
    """
    inbound_request = models.ForeignKey(
        InboundProductRequest,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='items'
    )
    outbound_request = models.ForeignKey(
        OutboundProductRequest,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='items'
    )
    product = models.ForeignKey(
        product_models.Product,
        on_delete=models.CASCADE,
        related_name='request_items'
    )
    quantity_requested = models.PositiveIntegerField(help_text="Quantity requested")
    quantity_fulfilled = models.PositiveIntegerField(
        default=0,
        help_text="Quantity actually fulfilled (for partial fulfillment tracking)"
    )
    notes = models.TextField(blank=True, help_text="Item-specific notes")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Product Request Item"
        verbose_name_plural = "Product Request Items"
        ordering = ['id']

    def __str__(self):
        request = self.inbound_request or self.outbound_request
        return f"{self.product.product_title} x{self.quantity_requested} ({request.request_number})"

    @property
    def is_fully_fulfilled(self):
        """Check if item has been completely fulfilled"""
        return self.quantity_fulfilled >= self.quantity_requested

    @property
    def remaining_quantity(self):
        """Calculate remaining quantity to be fulfilled"""
        return max(0, self.quantity_requested - self.quantity_fulfilled)
