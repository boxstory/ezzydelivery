from django.contrib import admin
from django.utils.html import format_html
from django.utils import timezone
from .models import (
    OrderBatch, BatchOrder, RiderShift, RiderKPI, DispatchConfig, DispatchLog
)


class BatchOrderInline(admin.TabularInline):
    """Inline admin for orders in a batch."""
    model = BatchOrder
    extra = 0
    readonly_fields = ('order', 'sequence', 'added_at', 'sla_deadline', 'sla_remaining_display')
    fields = ('order', 'sequence', 'sla_deadline', 'sla_remaining_display', 'is_sla_at_risk')

    def sla_remaining_display(self, obj):
        if obj.sla_remaining_minutes is not None:
            minutes = obj.sla_remaining_minutes
            if minutes <= 15:
                color = 'red'
            elif minutes <= 30:
                color = 'orange'
            else:
                color = 'green'
            return format_html(
                '<span style="color: {};">{} min</span>',
                color, minutes
            )
        return '-'
    sla_remaining_display.short_description = 'SLA Remaining'

    def has_add_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(OrderBatch)
class OrderBatchAdmin(admin.ModelAdmin):
    """Admin interface for order batches."""
    list_display = (
        'batch_code', 'pickup_location', 'destination_zone',
        'status_display', 'order_count_display', 'assigned_rider',
        'hold_timer_display', 'created_at'
    )
    list_filter = ('status', 'pickup_location', 'destination_zone', 'created_at')
    search_fields = ('batch_code', 'assigned_rider__driver_code')
    readonly_fields = (
        'batch_code', 'created_at', 'updated_at', 'order_count',
        'total_cod', 'hold_remaining_seconds'
    )
    date_hierarchy = 'created_at'
    inlines = [BatchOrderInline]

    fieldsets = (
        ('Batch Info', {
            'fields': ('batch_code', 'pickup_location', 'destination_zone')
        }),
        ('Status', {
            'fields': ('status', 'release_reason')
        }),
        ('Timing', {
            'fields': (
                'hold_started_at', 'hold_expires_at', 'released_at',
                'assigned_at', 'completed_at'
            )
        }),
        ('Assignment', {
            'fields': ('assigned_rider', 'assigned_shift')
        }),
        ('Metrics', {
            'fields': ('order_count', 'total_cod', 'estimated_delivery_time')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def status_display(self, obj):
        colors = {
            'pending': '#6c757d',
            'holding': '#ffc107',
            'ready': '#17a2b8',
            'assigned': '#007bff',
            'in_progress': '#fd7e14',
            'completed': '#28a745',
            'cancelled': '#dc3545',
        }
        color = colors.get(obj.status, '#6c757d')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 8px; '
            'border-radius: 3px; font-size: 11px;">{}</span>',
            color, obj.get_status_display()
        )
    status_display.short_description = 'Status'

    def order_count_display(self, obj):
        return f"{obj.order_count}/2"
    order_count_display.short_description = 'Orders'

    def hold_timer_display(self, obj):
        if obj.status == 'holding' and obj.hold_remaining_seconds > 0:
            return format_html(
                '<span style="color: orange;">{} sec</span>',
                obj.hold_remaining_seconds
            )
        return '-'
    hold_timer_display.short_description = 'Hold Timer'

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'pickup_location', 'assigned_rider', 'assigned_shift'
        )


@admin.register(BatchOrder)
class BatchOrderAdmin(admin.ModelAdmin):
    """Admin interface for batch-order links."""
    list_display = ('batch', 'order', 'sequence', 'sla_deadline', 'is_sla_at_risk', 'added_at')
    list_filter = ('is_sla_at_risk', 'batch__status')
    search_fields = ('batch__batch_code', 'order__order_number')
    readonly_fields = ('added_at',)

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('batch', 'order')


@admin.register(RiderShift)
class RiderShiftAdmin(admin.ModelAdmin):
    """Admin interface for rider shifts."""
    list_display = (
        'shift_code', 'rider', 'pickup_location', 'status_display',
        'shift_type', 'scheduled_start', 'scheduled_end',
        'batches_completed', 'orders_delivered'
    )
    list_filter = ('status', 'shift_type', 'pickup_location', 'scheduled_start')
    search_fields = ('shift_code', 'rider__driver_code', 'rider__user__username')
    readonly_fields = (
        'shift_code', 'created_at', 'updated_at',
        'batches_completed', 'orders_delivered'
    )
    date_hierarchy = 'scheduled_start'
    raw_id_fields = ('rider',)

    fieldsets = (
        ('Shift Info', {
            'fields': ('shift_code', 'rider', 'pickup_location', 'shift_type')
        }),
        ('Status', {
            'fields': ('status',)
        }),
        ('Schedule', {
            'fields': ('scheduled_start', 'scheduled_end', 'actual_start', 'actual_end')
        }),
        ('Breaks', {
            'fields': ('break_start', 'break_end', 'total_break_minutes'),
            'classes': ('collapse',)
        }),
        ('Performance', {
            'fields': ('batches_completed', 'orders_delivered')
        }),
        ('Audit', {
            'fields': ('created_at', 'updated_at', 'created_by'),
            'classes': ('collapse',)
        }),
    )

    def status_display(self, obj):
        colors = {
            'scheduled': '#6c757d',
            'active': '#28a745',
            'break': '#ffc107',
            'completed': '#17a2b8',
            'cancelled': '#dc3545',
            'no_show': '#6f42c1',
        }
        color = colors.get(obj.status, '#6c757d')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 8px; '
            'border-radius: 3px; font-size: 11px;">{}</span>',
            color, obj.get_status_display()
        )
    status_display.short_description = 'Status'

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'rider', 'pickup_location', 'created_by'
        )

    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(RiderKPI)
class RiderKPIAdmin(admin.ModelAdmin):
    """Admin interface for rider KPIs."""
    list_display = (
        'rider', 'date', 'pickup_location',
        'total_orders', 'batching_pct_display', 'orders_per_hour',
        'sla_compliance_display'
    )
    list_filter = ('date', 'pickup_location')
    search_fields = ('rider__driver_code', 'rider__user__username')
    readonly_fields = (
        'created_at', 'updated_at', 'orders_per_hour',
        'batching_percentage', 'sla_compliance_rate'
    )
    date_hierarchy = 'date'
    raw_id_fields = ('rider',)

    fieldsets = (
        ('Reference', {
            'fields': ('rider', 'date', 'pickup_location')
        }),
        ('Order Metrics', {
            'fields': ('total_orders', 'batched_orders', 'single_orders')
        }),
        ('Batch Metrics', {
            'fields': ('total_batches', 'batches_with_2_orders')
        }),
        ('Time Metrics', {
            'fields': ('total_active_minutes', 'avg_delivery_time', 'orders_per_hour')
        }),
        ('SLA Metrics', {
            'fields': ('sla_compliant_orders', 'sla_breached_orders', 'sla_compliance_rate')
        }),
        ('Computed', {
            'fields': ('batching_percentage',),
            'classes': ('collapse',)
        }),
    )

    def batching_pct_display(self, obj):
        pct = obj.batching_percentage
        if pct >= 80:
            color = 'green'
        elif pct >= 50:
            color = 'orange'
        else:
            color = 'red'
        return format_html(
            '<span style="color: {};">{:.1f}%</span>',
            color, pct
        )
    batching_pct_display.short_description = 'Batching %'

    def sla_compliance_display(self, obj):
        pct = obj.sla_compliance_rate
        if pct >= 95:
            color = 'green'
        elif pct >= 80:
            color = 'orange'
        else:
            color = 'red'
        return format_html(
            '<span style="color: {};">{:.1f}%</span>',
            color, pct
        )
    sla_compliance_display.short_description = 'SLA Compliance'

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'rider', 'pickup_location'
        )


@admin.register(DispatchConfig)
class DispatchConfigAdmin(admin.ModelAdmin):
    """Admin interface for dispatch configuration."""
    list_display = (
        'pickup_location', 'batching_enabled', 'auto_assignment_enabled',
        'max_batch_size', 'hold_window_seconds', 'sla_minutes'
    )
    list_filter = ('batching_enabled', 'auto_assignment_enabled')
    search_fields = ('pickup_location__pickup_location_title',)

    fieldsets = (
        ('Location', {
            'fields': ('pickup_location',)
        }),
        ('Batching Settings', {
            'fields': (
                'max_batch_size', 'hold_window_seconds',
                'min_hold_seconds', 'max_hold_seconds'
            )
        }),
        ('SLA Settings', {
            'fields': ('sla_minutes', 'sla_buffer_minutes', 'sla_override_enabled')
        }),
        ('Rider Limits', {
            'fields': ('max_orders_per_rider', 'max_batches_per_rider')
        }),
        ('Peak Hours', {
            'fields': (
                'peak_start_1', 'peak_end_1',
                'peak_start_2', 'peak_end_2',
                'enforce_batching_peak', 'allow_single_release_offpeak'
            ),
            'classes': ('collapse',)
        }),
        ('Feature Flags', {
            'fields': (
                'batching_enabled', 'auto_assignment_enabled',
                'zone_priority_enabled', 'load_balancing_enabled'
            )
        }),
    )


@admin.register(DispatchLog)
class DispatchLogAdmin(admin.ModelAdmin):
    """Admin interface for dispatch audit logs."""
    list_display = ('action', 'batch', 'rider', 'performed_by', 'created_at')
    list_filter = ('action', 'created_at')
    search_fields = (
        'batch__batch_code', 'rider__driver_code',
        'order__order_number', 'performed_by__username'
    )
    readonly_fields = (
        'action', 'batch', 'order', 'rider', 'shift',
        'details', 'performed_by', 'created_at'
    )
    date_hierarchy = 'created_at'

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'batch', 'order', 'rider', 'shift', 'performed_by'
        )
