from django.contrib import admin
from delivery import models as delivery_models

# Register your models here.


class ZoneAreaInline(admin.TabularInline):
    model = delivery_models.ZoneArea
    extra = 1
    fields = ('area_name', 'area_name_arabic', 'latitude', 'longitude', 'is_active')


@admin.register(delivery_models.ZoneName)
class ZoneNameAdmin(admin.ModelAdmin):
    list_display = ('zone_number', 'zone_name', 'zone_name_arabic', 'area_count', 'latitude', 'longitude', 'has_polygon_display', 'neighbour_count', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('zone_name', 'zone_name_arabic', 'zone_number')
    ordering = ('zone_number',)
    filter_horizontal = ('neighbour_zones',)
    list_editable = ('is_active',)
    inlines = [ZoneAreaInline]
    fieldsets = (
        ('Zone Info', {
            'fields': ('zone_number', 'zone_name', 'zone_name_arabic', 'is_active')
        }),
        ('Location (Center Point)', {
            'fields': ('latitude', 'longitude')
        }),
        ('Boundary Polygon', {
            'fields': ('polygon',),
            'description': 'Enter boundary coordinates as JSON array: [[lat1, lon1], [lat2, lon2], ...]'
        }),
        ('Neighbours', {
            'fields': ('neighbour_zones',),
            'description': 'Select adjacent/nearby zones'
        }),
    )

    def neighbour_count(self, obj):
        return obj.neighbour_zones.count()
    neighbour_count.short_description = 'Neighbours'

    def has_polygon_display(self, obj):
        return "Yes" if obj.has_polygon else "No"
    has_polygon_display.short_description = 'Polygon'

    def area_count(self, obj):
        return obj.areas.count()
    area_count.short_description = 'Areas'


@admin.register(delivery_models.ZoneArea)
class ZoneAreaAdmin(admin.ModelAdmin):
    list_display = ('area_name', 'zone_display', 'area_name_arabic', 'latitude', 'longitude', 'is_active')
    list_filter = ('is_active', 'zone__zone_number')
    search_fields = ('area_name', 'area_name_arabic', 'zone__zone_name', 'zone__zone_number')
    ordering = ('zone__zone_number', 'area_name')
    list_select_related = ('zone',)
    raw_id_fields = ('zone',)
    list_per_page = 50

    def zone_display(self, obj):
        return f"Zone {obj.zone.zone_number} - {obj.zone.zone_name}"
    zone_display.short_description = 'Zone'
    zone_display.admin_order_field = 'zone__zone_number'


@admin.register(delivery_models.ZoneGroup)
class ZoneGroupAdmin(admin.ModelAdmin):
    list_display = ('name', 'zone_count', 'zone_numbers_display', 'is_active', 'display_order')
    list_filter = ('is_active',)
    search_fields = ('name', 'description')
    filter_horizontal = ('zones',)
    ordering = ('display_order', 'name')
    fieldsets = (
        (None, {
            'fields': ('name', 'description', 'is_active', 'display_order')
        }),
        ('Zones', {
            'fields': ('zones',),
            'description': 'Select the zones that belong to this group'
        }),
    )


@admin.register(delivery_models.DeliveryTask)
class DeliveryTaskAdmin(admin.ModelAdmin):
    list_display = ('dl_task_number', 'dl_price', 'dl_task_status', 'driver', 'completed_at')
    list_filter = ('dl_task_status', 'dl_task_date')
    search_fields = (
        'dl_task_number',
        'order__order_number',
        'driver__driver_code',
        'driver__user__first_name',
        'driver__user__last_name',
        'business__business_name',
    )
    readonly_fields = ('completion_latitude', 'completion_longitude', 'completed_at')


@admin.register(delivery_models.TaskStatusPoint)
class TaskStatusPointAdmin(admin.ModelAdmin):
    list_display = ('task', 'driver', 'old_status', 'new_status', 'latitude', 'longitude', 'distance_from_delivery', 'created_at')
    list_filter = ('new_status', 'created_at')
    search_fields = ('task__dl_task_number',)
    readonly_fields = ('task', 'driver', 'old_status', 'new_status', 'latitude', 'longitude', 'accuracy', 'distance_from_delivery', 'delivery_latitude', 'delivery_longitude', 'created_at')
    raw_id_fields = ('task', 'driver')
    list_select_related = ('task', 'driver')
    ordering = ('-created_at',)


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
