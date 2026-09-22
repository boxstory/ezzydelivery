from django.contrib import admin
from fleet import models as fleet_models
# Register your models here.


@admin.register(fleet_models.Driver)
class DriverAdmin(admin.ModelAdmin):
    list_display = ('user', 'driver_code', 'driver_phone',
                    'driver_whatsapp', 'driver_status', 'driver_availability',
                    'wallet_balance', 'cod_in_hand', 'pending_earnings', 'created_at')
    list_filter = ('driver_status', 'driver_availability', 'job_type', 'created_at', 'updated_at')
    search_fields = ('driver_code', 'driver_license_number', 'driver_phone', 'driver_whatsapp',
                     'driver_status', 'job_type', 'driver_bio', 'driver_languages',
                     'driver_reviews', 'driver_availability', 'work_time_slabs',
                     'profile__user_number', 'user__username', 'user__first_name',
                     'user__last_name')
    search_help_text = ('Searches driver code, phone, WhatsApp, licence number, name, '
                        'status, availability, job type, languages and bio')
    list_select_related = ('user',)
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

    def save_model(self, request, obj, form, change):
        """Admin is the only place allowed to change driver_code.

        Driver.save() rejects a driver_code change unless this flag is passed,
        which keeps every view, API and script from rewriting a driver's code.
        """
        obj.save(allow_code_change=True)


@admin.register(fleet_models.DriverVacancyAplication)
class DriverVacancyAplicationAdmin(admin.ModelAdmin):
    list_display = ('full_name', 'mobile_no', 'zone_name', 'job_type',
                    'licence', 'own_vehicle', 'is_in_qatar')
    list_filter = ('job_type', 'licence', 'own_vehicle', 'is_in_qatar')
    search_fields = ('full_name', 'zone_name', 'mobile_no', 'whatsapp_no', 'job_type',
                     'landmark', 'licence', 'own_vehicle', 'user__username')
    list_per_page = 25


@admin.register(fleet_models.DriverVehicle)
class DriverVehicleAdmin(admin.ModelAdmin):
    list_display = ('driver','vehicle_type', 'vehicle_no',
                    'vehicle_color', 'vehicle_model', 'vehicle_status', 'vehicle_date')
    list_filter = ('vehicle_type', 'vehicle_status', 'vehicle_date')
    search_fields = ('vehicle_type', 'vehicle_status', 'vehicle_no', 'vehicle_model',
                     'vehicle_color', 'driver__driver_code', 'driver__driver_phone')
    list_select_related = ('driver',)
    raw_id_fields = ('driver',)
    list_per_page = 10


@admin.register(fleet_models.DriverDocument)
class DriverDocumentAdmin(admin.ModelAdmin):
    list_display = ('driver', 'document_type', 'document_no', 'document_expiry_date')
    list_filter = ('document_type', 'document_issued_from')
    search_fields = ('document_no', 'document_type', 'document_issued_from',
                     'driver__driver_code', 'driver__driver_phone')
    list_select_related = ('driver',)
    raw_id_fields = ('driver',)


@admin.register(fleet_models.DriverTransaction)
class DriverTransactionAdmin(admin.ModelAdmin):
    list_display = ('transaction_code', 'driver', 'transaction_type', 'amount',
                    'wallet_balance_after', 'cod_in_hand_after', 'created_at')
    list_filter = ('transaction_type', 'created_at')
    search_fields = ('reference_number', 'transaction_code', 'transaction_type', 'description',
                     'amount', 'payment_method', 'notes', 'driver__driver_code',
                     'delivery_task__dl_task_number', 'settlement__settlement_code',
                     'business__business_name', 'created_by__username')
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
    search_fields = ('settlement_code', 'status', 'net_amount', 'payment_method',
                     'payment_reference', 'notes', 'driver__driver_code', 'created_by__username',
                     'approved_by__username')
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
    search_fields = ('driver__driver_code', 'driver__driver_phone', 'task__dl_task_number')
    raw_id_fields = ('driver', 'task')
    readonly_fields = ('created_at', 'lag_seconds')
    list_per_page = 50

    @admin.display(description='Lag (s)')
    def lag_seconds(self, obj):
        """Seconds the fix spent on the device — large values mean a replayed ping."""
        return obj.lag_seconds


@admin.register(fleet_models.DriverNavHandoff)
class DriverNavHandoffAdmin(admin.ModelAdmin):
    list_display = ('driver', 'provider', 'task', 'opened_at', 'returned_at',
                    'gap_minutes', 'route_km', 'auto', 'left_foreground', 'close_reason')
    list_filter = ('provider', 'auto', 'close_reason', 'left_foreground', 'opened_at')
    search_fields = ('provider', 'close_reason', 'driver__driver_code', 'task__dl_task_number')
    raw_id_fields = ('driver', 'task', 'pickup_task')
    readonly_fields = ('created_at', 'gap_minutes')
    list_per_page = 50

    @admin.display(description='Gap (min)')
    def gap_minutes(self, obj):
        """How long the trail was dark while the driver was in the nav app."""
        return round(obj.gap_seconds / 60, 1)


@admin.register(fleet_models.DriverPushSubscription)
class DriverPushSubscriptionAdmin(admin.ModelAdmin):
    """Which driver phones dispatch can actually reach, and which have gone quiet.

    Read-only on purpose: a row here is an address the browser issued, and
    hand-editing one produces an endpoint no push service will accept. The
    driver's own app is the only thing that can create a working row.
    """
    list_display = ('driver', 'device', 'is_active', 'failure_count',
                    'last_used_at', 'created_at', 'last_failure')
    list_filter = ('is_active', 'created_at')
    raw_id_fields = ('driver',)
    readonly_fields = ('endpoint', 'p256dh', 'auth', 'user_agent',
                       'created_at', 'updated_at', 'last_used_at')
    search_fields = ('endpoint', 'last_failure', 'driver__driver_code')
    list_per_page = 50

    @admin.display(description='Device')
    def device(self, obj):
        """The tail of the endpoint — enough to tell two phones apart."""
        return f'…{obj.endpoint[-14:]}'


@admin.register(fleet_models.DeliveryPayRate)
class DeliveryPayRateAdmin(admin.ModelAdmin):
    """Read-mostly. The staff console at /workforce/fleet/pay-rates/ is the real
    entry point — it enforces one open card per scope, which this form cannot."""
    list_display = ('__str__', 'driver', 'normal_fee', 'hub_fee',
                    'pick_and_drop_percent', 'exchange_fee',
                    'effective_from', 'effective_to')
    list_filter = ('effective_from', 'effective_to')
    search_fields = ('notes', 'driver__driver_code', 'created_by__username')
    autocomplete_fields = ()
    raw_id_fields = ('driver',)


@admin.register(fleet_models.ZoneEarningsRate)
class ZoneEarningsRateAdmin(admin.ModelAdmin):
    list_display = ('order_type', 'pickup_zone', 'delivery_zone', 'driver_rate',
                    'per_km_rate', 'base_rate', 'is_active')
    list_filter = ('order_type', 'is_active', 'delivery_zone')
    search_fields = ('order_type', 'pickup_zone__zone_name', 'delivery_zone__zone_name')
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

# ─────────────────────────────────────────────────────────────────────────────
# Tables that had no admin page. Registered so every model is reachable and
# searchable from /dj-admin/. Related rows use raw id fields so a changelist
# never renders a dropdown of the whole table.
# ─────────────────────────────────────────────────────────────────────────────

@admin.register(fleet_models.BusinessChargeInvoice)
class BusinessChargeInvoiceAdmin(admin.ModelAdmin):
    list_display = ('invoice_code', 'business', 'period_from', 'period_to', 'total_amount', 'amount_paid', 'status')
    search_fields = ('invoice_code', 'status', 'notes', 'void_reason', 'total_amount',
                     'business__business_name', 'issued_by__username', 'voided_by__username')
    list_filter = ('status',)
    list_select_related = ('business',)
    raw_id_fields = ('business', 'issued_by', 'voided_by')

@admin.register(fleet_models.BusinessChargeInvoiceLine)
class BusinessChargeInvoiceLineAdmin(admin.ModelAdmin):
    list_display = ('invoice', 'delivery_task', 'charge_txn', 'kind', 'label', 'amount', 'created_at')
    search_fields = ('label', 'kind', 'amend_reason', 'amount', 'original_amount',
                     'invoice__invoice_code', 'delivery_task__dl_task_number',
                     'charge_txn__transaction_code', 'amended_by__username')
    list_filter = ('kind',)
    list_select_related = ('invoice', 'delivery_task', 'charge_txn')
    raw_id_fields = ('invoice', 'delivery_task', 'charge_txn', 'amended_by')

@admin.register(fleet_models.BusinessInvoicePayment)
class BusinessInvoicePaymentAdmin(admin.ModelAdmin):
    list_display = ('invoice', 'amount', 'payment_method', 'reference', 'received_on', 'notes', 'created_at')
    search_fields = ('payment_method', 'reference', 'notes', 'amount', 'invoice__invoice_code',
                     'payment_txn__transaction_code', 'created_by__username')
    list_filter = ('payment_method',)
    list_select_related = ('invoice',)
    raw_id_fields = ('invoice', 'payment_txn', 'created_by')

@admin.register(fleet_models.BusinessLedgerEntry)
class BusinessLedgerEntryAdmin(admin.ModelAdmin):
    list_display = ('entry_code', 'driver', 'order', 'business', 'occurred_on', 'created_at', 'segment')
    search_fields = ('entry_code', 'order_number', 'task_number', 'kind', 'status', 'segment',
                     'billing_state', 'description', 'reference', 'payment_method',
                     'delivery_task__dl_task_number', 'order__order_number',
                     'driver__driver_code', 'txn__transaction_code',
                     'charge_invoice__invoice_code', 'business__business_name')
    list_filter = ('segment', 'status', 'billing_state')
    list_select_related = ('business', 'order', 'driver')
    raw_id_fields = ('business', 'delivery_task', 'order', 'driver', 'txn', 'charge_invoice', 'reversal_of', 'created_by')

@admin.register(fleet_models.BusinessPayoutDeduction)
class BusinessPayoutDeductionAdmin(admin.ModelAdmin):
    list_display = ('settle_txn', 'charge_txn', 'kind', 'label', 'amount', 'created_at', 'created_by')
    search_fields = ('label', 'kind', 'amount', 'settle_txn__transaction_code',
                     'charge_txn__transaction_code', 'created_by__username')
    list_filter = ('kind',)
    list_select_related = ('settle_txn', 'charge_txn', 'created_by')
    raw_id_fields = ('settle_txn', 'charge_txn', 'created_by')

@admin.register(fleet_models.DriverActivityLog)
class DriverActivityLogAdmin(admin.ModelAdmin):
    list_display = ('driver', 'activity_type', 'task', 'transaction', 'description', 'ip_address', 'created_at')
    search_fields = ('ip_address', 'activity_type', 'description', 'driver__driver_code',
                     'task__dl_task_number', 'transaction__transaction_code')
    list_filter = ('activity_type',)
    list_select_related = ('driver', 'task', 'transaction')
    raw_id_fields = ('driver', 'task', 'transaction')

@admin.register(fleet_models.DriverDevice)
class DriverDeviceAdmin(admin.ModelAdmin):
    list_display = ('user', 'status', 'user_agent', 'ip_address', 'label', 'created_at', 'last_seen_at')
    search_fields = ('label', 'ip_address', 'status', 'revoked_reason', 'user__username',
                     'approved_by__username')
    list_filter = ('status', 'revoked_reason')
    list_select_related = ('user',)
    raw_id_fields = ('user', 'approved_by')

@admin.register(fleet_models.DriverNotification)
class DriverNotificationAdmin(admin.ModelAdmin):
    list_display = ('driver', 'title', 'notification_type', 'related_task', 'is_read', 'created_at', 'read_at')
    search_fields = ('title', 'message', 'notification_type', 'driver__driver_code', 'related_task__dl_task_number')
    list_filter = ('notification_type', 'is_read')
    list_select_related = ('driver', 'related_task')
    raw_id_fields = ('driver', 'related_task')

@admin.register(fleet_models.ReceiptTemplate)
class ReceiptTemplateAdmin(admin.ModelAdmin):
    list_display = ('template_id', 'name', 'template_type', 'paper_size', 'is_default', 'is_active', 'created_at')
    search_fields = ('name', 'company_name', 'company_phone', 'company_email', 'company_address',
                     'template_type', 'paper_size', 'logo_url', 'primary_color', 'font_family',
                     'footer_message', 'terms_and_conditions', 'custom_css', 'custom_template',
                     'created_by__username')
    list_filter = ('template_type', 'paper_size', 'is_default', 'is_active')
    raw_id_fields = ('created_by',)
