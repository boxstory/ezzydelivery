from django.contrib import admin
from fleet import models as fleet_models
# Register your models here.


@admin.register(fleet_models.Driver)
class DriverAdmin(admin.ModelAdmin):
    list_display = ('user', 'driver_code', 'driver_phone',
                    'driver_whatsapp', 'driver_status', 'driver_availability',
                    'wallet_balance', 'cod_in_hand', 'pending_earnings', 'created_at')
    list_filter = ('driver_status', 'driver_availability', 'job_type', 'created_at', 'updated_at')
    list_per_page = 10
    readonly_fields = ('wallet_usage_percentage', 'is_wallet_warning',
                       'is_wallet_blocked', 'available_credit')

    fieldsets = (
        ('Basic Information', {
            'fields': ('user', 'profile', 'driver_code',
                      'driver_phone', 'driver_whatsapp', 'driver_bio')
        }),
        ('License & Status', {
            'fields': ('driver_license_number', 'driver_languages', 'driver_status',
                      'driver_availability', 'job_type', 'work_time_slabs',
                      'driver_rating', 'driver_rating_count')
        }),
        ('COD Wallet System', {
            'fields': ('wallet_balance', 'credit_limit', 'cod_in_hand',
                      'wallet_usage_percentage', 'is_wallet_warning',
                      'is_wallet_blocked', 'available_credit'),
            'classes': ('collapse',)
        }),
        ('Earnings', {
            'fields': ('total_earnings', 'pending_earnings', 'last_settlement_date'),
            'classes': ('collapse',)
        }),
    )


@admin.register(fleet_models.DriverVacancyAplication)
class DriverVacancyAplicationAdmin(admin.ModelAdmin):
    list_display = ('full_name', 'mobile_no', 'zone_name', 'job_type',
                    'licence', 'own_vehicle', 'is_in_qatar')
    list_filter = ('job_type', 'licence', 'own_vehicle', 'is_in_qatar')
    search_fields = ('full_name', 'mobile_no', 'whatsapp_no', 'zone_name')
    list_per_page = 25


@admin.register(fleet_models.DriverVehicle)
class DriverVehicleAdmin(admin.ModelAdmin):
    list_display = ('driver','vehicle_type', 'vehicle_no',
                    'vehicle_color', 'vehicle_model', 'vehicle_status', 'vehicle_date')
    list_filter = ('vehicle_status', 'vehicle_date')
    list_per_page = 10


@admin.register(fleet_models.DriverDocument)
class DriverDocumentAdmin(admin.ModelAdmin):
    list_display = ('driver', 'document_type', 'document_no', 'document_expiry_date')
    list_filter = ('document_type', 'document_issued_from')


@admin.register(fleet_models.DriverTransaction)
class DriverTransactionAdmin(admin.ModelAdmin):
    list_display = ('transaction_code', 'driver', 'transaction_type', 'amount',
                    'wallet_balance_after', 'cod_in_hand_after', 'created_at')
    list_filter = ('transaction_type', 'created_at')
    search_fields = ('driver__driver_code', 'description', 'reference_number')
    readonly_fields = ('wallet_balance_after', 'cod_in_hand_after',
                       'pending_earnings_after', 'created_at')
    list_per_page = 50

    fieldsets = (
        ('Transaction Details', {
            'fields': ('driver', 'transaction_type', 'amount', 'description',
                      'reference_number')
        }),
        ('Related Records', {
            'fields': ('delivery_task', 'settlement'),
        }),
        ('Balances After Transaction', {
            'fields': ('wallet_balance_after', 'cod_in_hand_after',
                      'pending_earnings_after'),
            'classes': ('collapse',)
        }),
        ('Metadata', {
            'fields': ('created_by', 'notes', 'created_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(fleet_models.DriverSettlement)
class DriverSettlementAdmin(admin.ModelAdmin):
    list_display = ('settlement_code', 'driver', 'period_start', 'period_end',
                    'total_deliveries', 'net_amount', 'status', 'created_at')
    list_filter = ('status', 'created_at', 'paid_at')
    search_fields = ('driver__driver_code', 'settlement_code')
    readonly_fields = ('settlement_code', 'approved_at', 'paid_at', 'created_at')
    list_per_page = 50

    fieldsets = (
        ('Settlement Information', {
            'fields': ('driver', 'settlement_code', 'period_start', 'period_end')
        }),
        ('Statistics', {
            'fields': ('total_deliveries', 'total_delivery_charges')
        }),
        ('Financial Breakdown', {
            'fields': ('gross_earnings', 'deductions', 'bonuses', 'net_amount')
        }),
        ('Status & Payment', {
            'fields': ('status', 'payment_method', 'payment_reference',
                      'approved_at', 'paid_at')
        }),
        ('Metadata', {
            'fields': ('created_by', 'approved_by', 'notes', 'created_at'),
            'classes': ('collapse',)
        }),
    )

    actions = ['mark_as_approved', 'mark_as_paid']

    def mark_as_approved(self, request, queryset):
        updated = 0
        for settlement in queryset.filter(status='pending'):
            settlement.status = 'approved'
            settlement.approved_by = request.user
            from django.utils import timezone
            settlement.approved_at = timezone.now()
            settlement.save()
            updated += 1
        self.message_user(request, f'{updated} settlement(s) approved successfully.')
    mark_as_approved.short_description = 'Mark selected as Approved'

    def mark_as_paid(self, request, queryset):
        updated = 0
        for settlement in queryset.filter(status='approved'):
            settlement.status = 'paid'
            from django.utils import timezone
            settlement.paid_at = timezone.now()
            settlement.save()
            updated += 1
        self.message_user(request, f'{updated} settlement(s) marked as paid.')
    mark_as_paid.short_description = 'Mark selected as Paid'


@admin.register(fleet_models.DriverLocation)
class DriverLocationAdmin(admin.ModelAdmin):
    list_display = ('driver', 'latitude', 'longitude', 'accuracy', 'speed', 'task',
                    'fixed_at', 'created_at', 'queued', 'lag_seconds')
    list_filter = ('queued', 'created_at')
    raw_id_fields = ('driver', 'task')
    readonly_fields = ('created_at', 'lag_seconds')
    list_per_page = 50

    @admin.display(description='Lag (s)')
    def lag_seconds(self, obj):
        """Seconds the fix spent on the device — large values mean a replayed ping."""
        return obj.lag_seconds


@admin.register(fleet_models.ZoneEarningsRate)
class ZoneEarningsRateAdmin(admin.ModelAdmin):
    list_display = ('order_type', 'pickup_zone', 'delivery_zone', 'driver_rate',
                    'per_km_rate', 'base_rate', 'is_active')
    list_filter = ('order_type', 'is_active', 'delivery_zone')
    search_fields = ('pickup_zone__zone_name', 'delivery_zone__zone_name')
    list_per_page = 50
    list_editable = ('driver_rate', 'per_km_rate', 'base_rate', 'is_active')

    fieldsets = (
        ('Order Type', {
            'fields': ('order_type',)
        }),
        ('Zone Configuration', {
            'fields': ('pickup_zone', 'delivery_zone'),
            'description': 'For Normal Delivery, only delivery zone is needed. For Pick & Drop, both zones are required.'
        }),
        ('Earnings Rates', {
            'fields': ('driver_rate', 'base_rate', 'per_km_rate'),
            'description': 'driver_rate: Fixed rate for zone. For distance-based: base_rate + (per_km_rate * distance)'
        }),
        ('Status', {
            'fields': ('is_active',)
        }),
    )
