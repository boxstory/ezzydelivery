from django.contrib import admin
from import_export.admin import ImportExportModelAdmin

from warehouse import models as warehouse_models


@admin.register(warehouse_models.Warehouse)
class WarehouseAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'city', 'is_active', 'is_default', 'manager', 'created_at')
    list_filter = ('is_active', 'is_default', 'city', 'created_at')
    search_fields = ('code', 'name', 'address', 'city')
    readonly_fields = ('created_at', 'updated_at')
    fieldsets = (
        ('Fulfillment Center Info', {
            'fields': ('name', 'code', 'description', 'is_active', 'is_default')
        }),
        ('Location Details', {
            'fields': ('address', 'city', 'state', 'postal_code', 'country', 'latitude', 'longitude')
        }),
        ('Contact Information', {
            'fields': ('phone', 'email')
        }),
        ('Management', {
            'fields': ('manager', 'created_by')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(warehouse_models.WarehouseLocation)
class WarehouseLocationAdmin(admin.ModelAdmin):
    list_display = ('full_code', 'name', 'warehouse', 'zone_number', 'is_active', 'is_default')
    list_filter = ('warehouse', 'is_active', 'is_default', 'zone_number')
    search_fields = ('name', 'code', 'warehouse__name', 'warehouse__code', 'address')
    readonly_fields = ('created_at', 'updated_at', 'full_code')
    fieldsets = (
        ('Location Info', {
            'fields': ('warehouse', 'name', 'code', 'full_code', 'is_active', 'is_default')
        }),
        ('Address & Zone', {
            'fields': ('address', 'zone_number', 'latitude', 'longitude')
        }),
        ('Operations', {
            'fields': ('operating_hours', 'notes')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(warehouse_models.SellerWarehouseLink)
class SellerWarehouseLinkAdmin(admin.ModelAdmin):
    list_display = ('business', 'warehouse', 'default_location', 'is_default', 'is_active', 'priority', 'linked_at')
    list_filter = ('is_default', 'is_active', 'warehouse', 'linked_at')
    search_fields = ('business__business_name', 'warehouse__name', 'warehouse__code')
    readonly_fields = ('linked_at', 'updated_at')
    raw_id_fields = ('business', 'warehouse', 'default_location', 'linked_by')
    fieldsets = (
        ('Link Details', {
            'fields': ('business', 'warehouse', 'default_location', 'is_active')
        }),
        ('Priority & Defaults', {
            'fields': ('is_default', 'priority')
        }),
        ('Notes', {
            'fields': ('notes',)
        }),
        ('Management', {
            'fields': ('linked_by', 'linked_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(warehouse_models.StorageLocation)
class StorageLocationAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'warehouse', 'location_type', 'parent', 'is_pickable', 'is_active')
    list_filter = ('warehouse', 'location_type', 'is_pickable', 'is_active')
    search_fields = ('code', 'name', 'barcode', 'warehouse__code')
    readonly_fields = ('created_at', 'updated_at')
    raw_id_fields = ('parent',)
    fieldsets = (
        ('Location Info', {
            'fields': ('warehouse', 'parent', 'name', 'code', 'barcode', 'location_type')
        }),
        ('Settings', {
            'fields': ('is_pickable', 'is_active')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(warehouse_models.StockLevel)
class StockLevelAdmin(ImportExportModelAdmin):
    list_display = (
        'product', 'warehouse', 'location', 'quantity_on_hand',
        'quantity_reserved', 'get_quantity_available', 'get_is_low_stock', 'abc_classification'
    )
    list_filter = ('warehouse', 'abc_classification', 'location__location_type')
    search_fields = ('product__item_name', 'product__item_sku', 'warehouse__code')
    readonly_fields = ('created_at', 'updated_at', 'get_quantity_available', 'get_is_low_stock')
    raw_id_fields = ('product', 'location')
    fieldsets = (
        ('Product & Location', {
            'fields': ('product', 'warehouse', 'location')
        }),
        ('Quantities', {
            'fields': (
                'quantity_on_hand', 'quantity_reserved', 'quantity_incoming',
                'get_quantity_available', 'get_is_low_stock'
            )
        }),
        ('Reorder Settings', {
            'fields': ('reorder_point', 'reorder_quantity', 'abc_classification')
        }),
        ('Last Count', {
            'fields': ('last_count_date', 'last_count_quantity'),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    @admin.display(description='Available')
    def get_quantity_available(self, obj):
        return obj.quantity_available

    @admin.display(description='Low Stock', boolean=True)
    def get_is_low_stock(self, obj):
        return obj.is_low_stock


@admin.register(warehouse_models.InventoryTransaction)
class InventoryTransactionAdmin(admin.ModelAdmin):
    list_display = (
        'transaction_number', 'product', 'warehouse', 'transaction_type',
        'quantity', 'reference_type', 'reference_id', 'created_at'
    )
    list_filter = ('transaction_type', 'warehouse', 'created_at')
    search_fields = ('transaction_number', 'product__item_sku', 'reference_id')
    readonly_fields = (
        'transaction_number', 'quantity_before', 'quantity_after', 'created_at'
    )
    raw_id_fields = ('product', 'location')
    date_hierarchy = 'created_at'
    fieldsets = (
        ('Transaction Info', {
            'fields': ('transaction_number', 'transaction_type', 'product', 'warehouse', 'location')
        }),
        ('Quantities', {
            'fields': ('quantity', 'quantity_before', 'quantity_after')
        }),
        ('Reference', {
            'fields': ('reference_type', 'reference_id', 'notes')
        }),
        ('Audit', {
            'fields': ('created_by', 'created_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(warehouse_models.StockReservation)
class StockReservationAdmin(admin.ModelAdmin):
    list_display = ('id', 'order', 'order_item', 'quantity', 'status', 'reserved_at')
    list_filter = ('status', 'reserved_at')
    search_fields = ('order__order_number', 'order_item__product__item_sku')
    readonly_fields = ('reserved_at', 'created_at', 'updated_at')
    raw_id_fields = ('order', 'order_item', 'stock_level')
    fieldsets = (
        ('Reservation Info', {
            'fields': ('order', 'order_item', 'stock_level', 'quantity', 'status')
        }),
        ('Timestamps', {
            'fields': ('reserved_at', 'released_at', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(warehouse_models.PickList)
class PickListAdmin(admin.ModelAdmin):
    list_display = (
        'pick_number', 'warehouse', 'wave_number', 'status',
        'assigned_to', 'total_items', 'picked_items', 'get_progress', 'created_at'
    )
    list_filter = ('status', 'warehouse', 'created_at')
    search_fields = ('pick_number', 'wave_number')
    readonly_fields = ('pick_number', 'created_at', 'updated_at', 'get_progress')
    raw_id_fields = ('assigned_to', 'created_by')
    fieldsets = (
        ('Pick List Info', {
            'fields': ('pick_number', 'warehouse', 'wave_number', 'status')
        }),
        ('Assignment', {
            'fields': ('assigned_to', 'assigned_at', 'started_at', 'completed_at')
        }),
        ('Progress', {
            'fields': ('total_items', 'picked_items', 'get_progress')
        }),
        ('Audit', {
            'fields': ('created_by', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    @admin.display(description='Progress')
    def get_progress(self, obj):
        return f"{obj.progress_percentage}%"


@admin.register(warehouse_models.PickListItem)
class PickListItemAdmin(admin.ModelAdmin):
    list_display = (
        'pick_list', 'order', 'product', 'location',
        'quantity_to_pick', 'quantity_picked', 'is_picked'
    )
    list_filter = ('is_picked', 'pick_list__status')
    search_fields = ('pick_list__pick_number', 'product__item_sku', 'order__order_number')
    readonly_fields = ('created_at',)
    raw_id_fields = ('pick_list', 'order', 'order_item', 'product', 'location', 'picked_by')


@admin.register(warehouse_models.CycleCount)
class CycleCountAdmin(admin.ModelAdmin):
    list_display = (
        'count_number', 'warehouse', 'location', 'status',
        'scheduled_date', 'assigned_to', 'get_total_items', 'get_counted_items'
    )
    list_filter = ('status', 'warehouse', 'scheduled_date')
    search_fields = ('count_number', 'warehouse__code')
    readonly_fields = ('count_number', 'created_at', 'updated_at')
    raw_id_fields = ('location', 'assigned_to', 'approved_by', 'created_by')
    date_hierarchy = 'scheduled_date'
    fieldsets = (
        ('Count Info', {
            'fields': ('count_number', 'warehouse', 'location', 'status', 'scheduled_date')
        }),
        ('Assignment', {
            'fields': ('assigned_to', 'started_at', 'completed_at')
        }),
        ('Approval', {
            'fields': ('approved_by', 'approved_at', 'notes')
        }),
        ('Audit', {
            'fields': ('created_by', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    @admin.display(description='Total Items')
    def get_total_items(self, obj):
        return obj.total_items

    @admin.display(description='Counted')
    def get_counted_items(self, obj):
        return obj.counted_items


@admin.register(warehouse_models.CycleCountItem)
class CycleCountItemAdmin(admin.ModelAdmin):
    list_display = (
        'cycle_count', 'product', 'location', 'system_quantity',
        'counted_quantity', 'variance', 'is_counted'
    )
    list_filter = ('is_counted', 'cycle_count__status')
    search_fields = ('cycle_count__count_number', 'product__item_sku')
    readonly_fields = ('created_at', 'variance')
    raw_id_fields = ('cycle_count', 'product', 'location', 'counted_by')


@admin.register(warehouse_models.LowStockAlert)
class LowStockAlertAdmin(admin.ModelAdmin):
    list_display = (
        'product', 'warehouse', 'quantity_available', 'reorder_point',
        'status', 'created_at'
    )
    list_filter = ('status', 'warehouse', 'created_at')
    search_fields = ('product__item_sku', 'product__item_name', 'warehouse__code')
    readonly_fields = ('created_at',)
    raw_id_fields = ('stock_level', 'product', 'warehouse', 'acknowledged_by')
    fieldsets = (
        ('Alert Info', {
            'fields': ('stock_level', 'product', 'warehouse', 'quantity_available', 'reorder_point', 'status')
        }),
        ('Resolution', {
            'fields': ('acknowledged_by', 'acknowledged_at', 'resolved_at')
        }),
        ('Timestamps', {
            'fields': ('created_at',),
            'classes': ('collapse',)
        }),
    )


# Product Request Models
class ProductRequestItemInline(admin.TabularInline):
    model = warehouse_models.ProductRequestItem
    extra = 1
    raw_id_fields = ('product',)
    fields = ('product', 'quantity_requested', 'quantity_fulfilled', 'notes')


@admin.register(warehouse_models.InboundProductRequest)
class InboundProductRequestAdmin(admin.ModelAdmin):
    list_display = (
        'request_number', 'business', 'warehouse', 'status',
        'expected_delivery_date', 'created_at', 'approved_at'
    )
    list_filter = ('status', 'warehouse', 'created_at', 'approved_at')
    search_fields = ('request_number', 'business__business_name', 'warehouse__name')
    readonly_fields = ('request_number', 'created_at', 'updated_at')
    raw_id_fields = ('business', 'warehouse', 'created_by', 'approved_by', 'completed_by')
    date_hierarchy = 'created_at'
    inlines = [ProductRequestItemInline]
    fieldsets = (
        ('Request Info', {
            'fields': ('request_number', 'business', 'warehouse', 'status', 'expected_delivery_date')
        }),
        ('Notes', {
            'fields': ('notes',)
        }),
        ('Workflow Tracking', {
            'fields': (
                'created_by', 'created_at',
                'approved_by', 'approved_at',
                'completed_by', 'completed_at',
                'cancelled_at', 'updated_at'
            ),
            'classes': ('collapse',)
        }),
    )


@admin.register(warehouse_models.OutboundProductRequest)
class OutboundProductRequestAdmin(admin.ModelAdmin):
    list_display = (
        'request_number', 'business', 'warehouse', 'status',
        'priority', 'created_at', 'approved_at'
    )
    list_filter = ('status', 'priority', 'warehouse', 'created_at', 'approved_at')
    search_fields = ('request_number', 'business__business_name', 'warehouse__name')
    readonly_fields = ('request_number', 'created_at', 'updated_at')
    raw_id_fields = ('business', 'warehouse', 'created_by', 'approved_by', 'completed_by')
    date_hierarchy = 'created_at'
    inlines = [ProductRequestItemInline]
    fieldsets = (
        ('Request Info', {
            'fields': ('request_number', 'business', 'warehouse', 'status', 'priority')
        }),
        ('Notes', {
            'fields': ('notes',)
        }),
        ('Workflow Tracking', {
            'fields': (
                'created_by', 'created_at',
                'approved_by', 'approved_at',
                'completed_by', 'completed_at',
                'cancelled_at', 'updated_at'
            ),
            'classes': ('collapse',)
        }),
    )


@admin.register(warehouse_models.ProductRequestItem)
class ProductRequestItemAdmin(admin.ModelAdmin):
    list_display = ('get_request_number', 'product', 'quantity_requested', 'quantity_fulfilled', 'created_at')
    list_filter = ('created_at',)
    search_fields = (
        'inbound_request__request_number',
        'outbound_request__request_number',
        'product__item_sku',
        'product__item_name'
    )
    readonly_fields = ('created_at', 'updated_at')
    raw_id_fields = ('inbound_request', 'outbound_request', 'product')

    @admin.display(description='Request #')
    def get_request_number(self, obj):
        if obj.inbound_request:
            return obj.inbound_request.request_number
        elif obj.outbound_request:
            return obj.outbound_request.request_number
        return '-'
