from django.contrib import admin
from delivery import models as delivery_models
from delivery.ordering import TASK_SEQ_DESC, annotate_task_sequence

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
    search_fields = ('dl_task_number', 'address_accuracy', 'dl_task_status_client',
                     'dl_task_status', 'earnings_verification_status',
                     'charge_verification_status', 'dl_task_description', 'dl_category',
                     'dl_speed', 'dl_price', 'cod_collected_amount', 'preferred_time',
                     'payment_method', 'cod_reference', 'earnings_notes', 'driver_note',
                     'order__order_number', 'driver__driver_code', 'driver__user__first_name',
                     'driver__user__last_name', 'business__business_name',
                     'dl_address_update__full_name', 'pickup_location__pickup_location_title',
                     'dl_to_address__full_name')
    readonly_fields = ('completion_latitude', 'completion_longitude', 'completed_at')

    def get_queryset(self, request):
        # Newest task-number sequence first (AOP067-1395-AB759 -> AB759). The
        # raw number leads with the business code, so ordering on it would
        # group the changelist by client instead of by when the job was issued.
        return annotate_task_sequence(super().get_queryset(request)).order_by(*TASK_SEQ_DESC)


@admin.register(delivery_models.TaskStatusPoint)
class TaskStatusPointAdmin(admin.ModelAdmin):
    list_display = ('task', 'driver', 'old_status', 'new_status', 'latitude', 'longitude', 'distance_from_delivery', 'created_at')
    list_filter = ('new_status', 'created_at')
    search_fields = ('old_status', 'new_status', 'task__dl_task_number', 'driver__driver_code')
    readonly_fields = ('task', 'driver', 'old_status', 'new_status', 'latitude', 'longitude', 'accuracy', 'distance_from_delivery', 'delivery_latitude', 'delivery_longitude', 'created_at')
    raw_id_fields = ('task', 'driver')
    list_select_related = ('task', 'driver')
    ordering = ('-created_at',)


@admin.register(delivery_models.DlAddressUpdate)
class DlAddressUpdateAdmin(admin.ModelAdmin):
    list_display = ('full_name', 'mobile_no', 'dl_task_number', 'dl_zone', 'dl_street',
                    'dl_building', 'created_at')
    search_fields = ('dl_task_number', 'dl_pluscode', 'full_name', 'area_name', 'mobile_no',
                     'dl_zone', 'dl_street', 'dl_building', 'dl_unit', 'time_slot', 'notes',
                     'order__order_number')
    raw_id_fields = ('order',)


@admin.register(delivery_models.ShippingLabel)
class ShippingLabelAdmin(admin.ModelAdmin):
    list_display = ('label_number', 'order', 'delivery_task', 'status', 'cod_amount', 'created_at')
    list_filter = ('status', 'label_format', 'created_at')
    search_fields = ('label_number', 'label_format', 'recipient_name', 'sender_name',
                     'recipient_phone', 'sender_phone', 'sender_address', 'recipient_address',
                     'recipient_zone', 'recipient_street', 'recipient_building', 'status',
                     'cod_amount', 'delivery_notes', 'order__order_number',
                     'delivery_task__dl_task_number', 'printed_by__username')
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

# ─────────────────────────────────────────────────────────────────────────────
# Tables that had no admin page. Registered so every model is reachable and
# searchable from /dj-admin/. Related rows use raw id fields so a changelist
# never renders a dropdown of the whole table.
# ─────────────────────────────────────────────────────────────────────────────

@admin.register(delivery_models.AssignedDriver)
class AssignedDriverAdmin(admin.ModelAdmin):
    list_display = ('driver', 'dl_task', 'created_at', 'updated_at')
    search_fields = ('driver__driver_code', 'dl_task__dl_task_number')
    list_select_related = ('driver', 'dl_task')
    raw_id_fields = ('driver', 'dl_task')

@admin.register(delivery_models.DeliveryLocationReview)
class DeliveryLocationReviewAdmin(admin.ModelAdmin):
    list_display = ('task', 'order', 'driver', 'gap_km', 'driver_latitude', 'driver_longitude', 'created_at')
    search_fields = ('status', 'review_notes', 'task__dl_task_number', 'order__order_number',
                     'driver__driver_code', 'reviewed_by__username')
    list_filter = ('status', 'coords_updated')
    list_select_related = ('task', 'order', 'driver')
    raw_id_fields = ('task', 'order', 'driver', 'reviewed_by')

@admin.register(delivery_models.DeliveryProof)
class DeliveryProofAdmin(admin.ModelAdmin):
    list_display = ('delivery_task', 'proof_type', 'notes', 'barcode_data', 'latitude', 'longitude', 'created_at')
    search_fields = ('proof_type', 'notes', 'barcode_data', 'delivery_task__dl_task_number', 'uploaded_by__username')
    list_filter = ('proof_type',)
    list_select_related = ('delivery_task',)
    raw_id_fields = ('delivery_task', 'uploaded_by')

@admin.register(delivery_models.DeliveryTaskQRCode)
class DeliveryTaskQRCodeAdmin(admin.ModelAdmin):
    list_display = ('delivery_task', 'task_number', 'created_at', 'updated_at')
    search_fields = ('task_number', 'delivery_task__dl_task_number')
    list_select_related = ('delivery_task',)
    raw_id_fields = ('delivery_task',)

@admin.register(delivery_models.HubPickupBatch)
class HubPickupBatchAdmin(admin.ModelAdmin):
    list_display = ('batch_number', 'pickup_location', 'hub_warehouse', 'driver', 'status', 'created_by', 'created_at')
    search_fields = ('batch_number', 'status', 'notes', 'hub_warehouse__code',
                     'driver__driver_code', 'pickup_location__pickup_location_title',
                     'created_by__username')
    list_filter = ('status', 'earnings_processed')
    list_select_related = ('pickup_location', 'hub_warehouse', 'driver', 'created_by')
    raw_id_fields = ('pickup_location', 'hub_warehouse', 'driver', 'created_by')

@admin.register(delivery_models.LatLonList)
class LatLonListAdmin(admin.ModelAdmin):
    list_display = ('zone_number', 'street_number', 'building_number', 'latitude', 'longitude', 'created_at', 'updated_at')
    search_fields = ('zone_number', 'street_number', 'building_number')

@admin.register(delivery_models.PickupTask)
class PickupTaskAdmin(admin.ModelAdmin):
    list_display = ('order', 'driver', 'business', 'pickup_location', 'drop_warehouse', 'pickup_mode', 'created_at')
    search_fields = ('status', 'pickup_mode', 'disposition', 'order__order_number',
                     'drop_warehouse__code', 'driver__driver_code',
                     'transfer_to_driver__driver_code', 'business__business_name',
                     'pickup_location__pickup_location_title')
    list_filter = ('pickup_mode', 'disposition', 'status')
    list_select_related = ('order', 'business', 'pickup_location', 'drop_warehouse', 'driver')
    raw_id_fields = ('order', 'business', 'pickup_location', 'drop_warehouse', 'driver', 'transfer_to_driver')


@admin.register(delivery_models.ParcelCustody)
class ParcelCustodyAdmin(admin.ModelAdmin):
    list_display = ('order', 'task', 'status', 'destination_kind', 'destination_label',
                    'driver', 'opened_at', 'received_at')
    search_fields = ('status', 'destination_kind', 'order__order_number',
                     'task__dl_task_number', 'driver__driver_code',
                     'business__business_name', 'manifest_reference',
                     'return_request__return_number')
    list_filter = ('status', 'destination_kind', 'destination_overridden')
    list_select_related = ('order', 'task', 'business', 'driver',
                           'warehouse_location', 'pickup_location')
    raw_id_fields = ('task', 'order', 'business', 'driver', 'warehouse_location',
                     'pickup_location', 'return_request', 'opened_by', 'received_by')
    readonly_fields = ('opened_at', 'updated_at')
