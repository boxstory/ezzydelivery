from atexit import register
from django.contrib import admin
from orders import models as orders_models
from import_export.admin import ImportExportModelAdmin

# Register your models here.


@admin.register(orders_models.Order)
class OrderAdmin(ImportExportModelAdmin):
    list_display = ('order_number', 'business', 'order_status', 'verification_status', 'task_created', 'address_verified', 'created_at')
    list_filter = ('order_status', 'verification_status', 'task_created', 'address_verified', 'created_at')
    search_fields = ('order_number', 'client_order_code', 'customer_name', 'customer_phone', 'customer_address')
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
    search_fields = ('order__order_number', 'product__product_name')
    raw_id_fields = ('order', 'product')
    readonly_fields = ('created_at', 'updated_at')


admin.site.register(orders_models.OrderLog)


admin.site.register(orders_models.OrderBarcode)


@admin.register(orders_models.OrderComments)
class OrderCommentsAdmin(ImportExportModelAdmin):
    list_display = ('order', 'name', 'body')


@admin.register(orders_models.OrderVerificationLog)
class OrderVerificationLogAdmin(ImportExportModelAdmin):
    list_display = ('order', 'action', 'verified_by', 'old_status', 'new_status', 'created_at')
    list_filter = ('action', 'created_at')
    search_fields = ('order__order_number', 'action', 'notes')
    readonly_fields = ('created_at',)
    date_hierarchy = 'created_at'


@admin.register(orders_models.AddressVerification)
class AddressVerificationAdmin(ImportExportModelAdmin):
    list_display = ('order', 'verification_result', 'verified_by', 'verified_at', 'created_at')
    list_filter = ('verification_result', 'verified_at', 'created_at')
    search_fields = ('order__order_number', 'original_address', 'verified_address', 'notes')
    readonly_fields = ('created_at', 'updated_at')
    date_hierarchy = 'created_at'


@admin.register(orders_models.ImportLog)
class ImportLogAdmin(admin.ModelAdmin):
    list_display = ('business', 'source', 'status', 'total_rows', 'orders_created', 'orders_skipped', 'orders_failed', 'initiated_by', 'started_at')
    list_filter = ('source', 'status', 'started_at')
    search_fields = ('business__business_name',)
    readonly_fields = ('started_at', 'completed_at', 'raw_data', 'source_meta', 'errors', 'column_mapping')
    date_hierarchy = 'started_at'