from atexit import register
from django.contrib import admin
from orders import models as orders_models
from import_export.admin import ImportExportModelAdmin

# Register your models here.


@admin.register(orders_models.Order)
class OrderAdmin(ImportExportModelAdmin):
    list_display = ('order_number', 'business', 'order_status', 'verification_status', 'task_created', 'address_verified', 'created_at')
    list_filter = ('order_status', 'verification_status', 'task_created', 'address_verified', 'created_at')
    search_fields = ('order_number', 'client_order_code', 'customer_name', 'delivery_area_name',
                     'customer_phone', 'customer_whatsapp', 'customer_address', 'dl_zone',
                     'dl_building', 'dl_street', 'delivery_area_source', 'order_status',
                     'task_status', 'cod_status_by_client', 'cod_status_by_staff', 'order_type',
                     'replaces__order_number', 'business__business_name',
                     'pickup_location__pickup_location_title', 'p2p_customer__username',
                     'address_verified_by__username', 'verified_by__username')
    readonly_fields = ('created_at', 'updated_at', 'verified_at', 'address_verified_at', 'original_order_data')
    date_hierarchy = 'created_at'
    fieldsets = (
        ('Order Information', {
            'fields': ('order_number', 'business', 'client_order_code', 'order_notes', 'order_status', 'task_status')
        }),
        ('Verification', {
            'fields': ('verification_status', 'address_verified', 'address_verified_by', 'address_verified_at',
                      'verified_by', 'verified_at', 'verification_notes')
        }),
        ('Customer Details', {
            'fields': ('customer_name', 'customer_phone', 'customer_whatsapp', 'customer_address',
                      'dl_zone', 'dl_street', 'dl_building')
        }),
        ('COD & Delivery', {
            'fields': ('cod_status_by_client', 'cod_status_by_staff', 'cod_amount', 'dl_included', 'dl_amount', 'pickup_location'),
            'description': 'COD Status by Client tracks the payment lifecycle: no_cod → pending → collected → received_by_company → invoiced → settled'
        }),
        ('Metadata', {
            'fields': ('original_order_data', 'task_created', 'created_at', 'updated_at')
        }),
    )

@admin.register(orders_models.OrderItem)
class OrderItemAdmin(ImportExportModelAdmin):
    list_display = ('order', 'product', 'quantity', 'unit_price', 'total_price')
    list_filter = ('order__created_at',)
    search_fields = ('delivery_status', 'unit_price', 'total_price', 'notes',
                     'order__order_number', 'product__item_sku', 'product__item_name')
    raw_id_fields = ('order', 'product')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(orders_models.OrderLog)
class OrderLogAdmin(admin.ModelAdmin):
    """The raw enquiry/change payloads. Both columns are JSON, so the search box
    matches inside them — an order number typed here finds the log that mentions it."""
    list_display = ('id', 'created_at', 'updated_at')
    search_fields = ('original_enquiry', 'change_data_log')
    search_help_text = 'Searches inside the stored JSON payloads'
    readonly_fields = ('created_at', 'updated_at')


@admin.register(orders_models.OrderBarcode)
class OrderBarcodeAdmin(admin.ModelAdmin):
    list_display = ('order_number', 'order', 'barcode', 'created_at')
    search_fields = ('order_number', 'order__order_number')
    raw_id_fields = ('order',)


@admin.register(orders_models.OrderComments)
class OrderCommentsAdmin(ImportExportModelAdmin):
    list_display = ('order', 'name', 'author_role', 'is_internal', 'created_at')
    list_filter = ('author_role', 'is_internal', 'created_at')
    search_fields = ('name', 'body', 'author_role', 'order__order_number', 'author__username',
                     'staff_read_by__username')
    raw_id_fields = ('order', 'author', 'staff_read_by')


@admin.register(orders_models.OrderVerificationLog)
class OrderVerificationLogAdmin(ImportExportModelAdmin):
    list_display = ('order', 'action', 'verified_by', 'old_status', 'new_status', 'created_at')
    list_filter = ('action', 'created_at')
    search_fields = ('old_status', 'new_status', 'action', 'notes', 'order__order_number',
                     'verified_by__username')
    readonly_fields = ('created_at',)
    date_hierarchy = 'created_at'


@admin.register(orders_models.AddressVerification)
class AddressVerificationAdmin(ImportExportModelAdmin):
    list_display = ('order', 'verification_result', 'verified_by', 'verified_at', 'created_at')
    list_filter = ('verification_result', 'verified_at', 'created_at')
    search_fields = ('zone_number', 'street_number', 'building_number', 'original_address',
                     'verified_address', 'notes', 'verification_result', 'order__order_number',
                     'verified_by__username')
    readonly_fields = ('created_at', 'updated_at')
    date_hierarchy = 'created_at'


@admin.register(orders_models.ImportLog)
class ImportLogAdmin(admin.ModelAdmin):
    list_display = ('business', 'source', 'status', 'total_rows', 'orders_created', 'orders_skipped', 'orders_failed', 'initiated_by', 'started_at')
    list_filter = ('source', 'status', 'started_at')
    search_fields = ('status', 'source', 'business__business_name', 'initiated_by__username',
                     'onedrive_source__label')
    readonly_fields = ('started_at', 'completed_at', 'raw_data', 'source_meta', 'errors', 'column_mapping')
    date_hierarchy = 'started_at'

# ─────────────────────────────────────────────────────────────────────────────
# Tables that had no admin page. Registered so every model is reachable and
# searchable from /dj-admin/. Related rows use raw id fields so a changelist
# never renders a dropdown of the whole table.
# ─────────────────────────────────────────────────────────────────────────────

@admin.register(orders_models.OneDriveSource)
class OneDriveSourceAdmin(admin.ModelAdmin):
    list_display = ('business', 'label', 'share_link', 'is_active', 'last_import_at', 'last_import_count', 'created_at')
    search_fields = ('label', 'last_sheet_name', 'share_link', 'business__business_name',
                     'last_import_by__username')
    list_filter = ('is_active', 'is_default_mapping')
    list_select_related = ('business',)
    raw_id_fields = ('business', 'last_import_by')

@admin.register(orders_models.OrderStatusHistory)
class OrderStatusHistoryAdmin(admin.ModelAdmin):
    list_display = ('order', 'field_name', 'old_value', 'new_value', 'old_display', 'new_display', 'created_at')
    search_fields = ('field_name', 'old_value', 'new_value', 'old_display', 'new_display', 'notes', 'order__order_number', 'changed_by__username')
    list_filter = ('field_name',)
    list_select_related = ('order',)
    raw_id_fields = ('order', 'changed_by')

@admin.register(orders_models.PublicLinkSource)
class PublicLinkSourceAdmin(admin.ModelAdmin):
    list_display = ('business', 'label', 'url', 'is_active', 'last_sync_at', 'last_sync_count', 'created_at')
    search_fields = ('label', 'url', 'business__business_name')
    list_filter = ('is_active',)
    list_select_related = ('business',)
    raw_id_fields = ('business',)

@admin.register(orders_models.ReturnItem)
class ReturnItemAdmin(admin.ModelAdmin):
    list_display = ('return_request', 'order_item', 'quantity_returned')
    search_fields = ('return_request__return_number',)
    list_select_related = ('return_request', 'order_item')
    raw_id_fields = ('return_request', 'order_item')

@admin.register(orders_models.ReturnRequest)
class ReturnRequestAdmin(admin.ModelAdmin):
    list_display = ('return_number', 'order', 'business', 'reason', 'status', 'cod_reversal_amount', 'created_at')
    search_fields = ('return_number', 'status', 'reason', 'reason_notes', 'cod_reversal_amount',
                     'review_notes', 'order__order_number', 'replacement_order__order_number',
                     'business__business_name', 'reviewed_by__username',
                     'external_reference', 'customer_name', 'customer_phone')
    list_filter = ('reason', 'status', 'cod_reversal_processed')
    list_select_related = ('order', 'business')
    # pickup_location is raw_id like the rest: a plain select renders every
    # address in the database on a claim that uses one only when it is a
    # standalone claim for goods we never delivered.
    raw_id_fields = ('order', 'business', 'replacement_order', 'reviewed_by',
                     'pickup_location')

@admin.register(orders_models.TempOrder)
class TempOrderAdmin(admin.ModelAdmin):
    list_display = ('source_type', 'onedrive_source', 'api_settings', 'public_link_source', 'business', 'sheet_name', 'created_at')
    search_fields = ('client_order_code', 'sheet_name', 'customer_name', 'customer_phone',
                     'customer_address', 'dl_zone', 'dl_street', 'dl_building', 'source_type',
                     'financial_status', 'status', 'platform_id', 'cod_amount', 'order_date',
                     'package_desc', 'imported_order__order_number', 'onedrive_source__label',
                     'public_link_source__label', 'api_settings__google_sheet_tab_name',
                     'business__business_name', 'api_settings__api_type')
    list_filter = ('source_type', 'status')
    list_select_related = ('onedrive_source', 'api_settings', 'public_link_source', 'business')
    raw_id_fields = ('onedrive_source', 'api_settings', 'public_link_source', 'business', 'imported_order')
