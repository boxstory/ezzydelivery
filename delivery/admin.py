from django.contrib import admin
from delivery import models as delivery_models

# Register your models here.


@admin.register(delivery_models.DeliveryTask)
class DeliveryTaskAdmin(admin.ModelAdmin):
    list_display = ('dl_task_number',  'dl_price')


@admin.register(delivery_models.DlAddressUpdate)
class DlAddressUpdateAdmin(admin.ModelAdmin):
    list_display = ('full_name', 'dl_zone', 'dl_street', 'dl_building')


@admin.register(delivery_models.ShippingLabel)
class ShippingLabelAdmin(admin.ModelAdmin):
    list_display = ('label_number', 'order', 'delivery_task', 'status', 'cod_amount', 'created_at')
    list_filter = ('status', 'label_format', 'created_at')
    search_fields = ('label_number', 'order__order_number', 'recipient_name', 'recipient_phone')
    readonly_fields = ('label_number', 'barcode_data', 'created_at', 'updated_at')
    raw_id_fields = ('order', 'delivery_task')
    fieldsets = (
        ('Label Info', {
            'fields': ('label_number', 'barcode_data', 'label_file', 'label_format', 'status')
        }),
        ('Links', {
            'fields': ('order', 'delivery_task')
        }),
        ('Sender', {
            'fields': ('sender_name', 'sender_address', 'sender_phone')
        }),
        ('Recipient', {
            'fields': ('recipient_name', 'recipient_address', 'recipient_phone',
                      'recipient_zone', 'recipient_street', 'recipient_building')
        }),
        ('Delivery Details', {
            'fields': ('cod_amount', 'delivery_notes')
        }),
        ('Print Status', {
            'fields': ('printed_at', 'printed_by')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
