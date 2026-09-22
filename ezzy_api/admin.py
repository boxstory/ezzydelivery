from django.contrib import admin
from ezzy_api import models as ezzy_api_models


@admin.register(ezzy_api_models.ClientApiKey)
class ClientApiKeyAdmin(admin.ModelAdmin):
    list_display = ['key_prefix', 'business', 'scope', 'key_name', 'is_active', 'last_used', 'expires_at', 'created_at']
    list_filter = ['scope', 'is_active', 'created_at', 'expires_at']
    search_fields = ('key_name', 'key_prefix', 'scope', 'business__business_name',
                     'created_by__username')
    readonly_fields = ['key_prefix', 'key_hash', 'api_secret', 'created_at', 'updated_at']
    date_hierarchy = 'created_at'


@admin.register(ezzy_api_models.TaskDocument)
class TaskDocumentAdmin(admin.ModelAdmin):
    list_display = ['task', 'document_type', 'document_name', 'uploaded_by', 'created_at']
    list_filter = ['document_type', 'created_at']
    search_fields = ('document_name', 'document_type', 'description', 'task__dl_task_number',
                     'uploaded_by__username')
    readonly_fields = ['created_at', 'updated_at']
    date_hierarchy = 'created_at'


@admin.register(ezzy_api_models.OrderDocument)
class OrderDocumentAdmin(admin.ModelAdmin):
    list_display = ['order', 'document_type', 'document_name', 'uploaded_by', 'created_at']
    list_filter = ['document_type', 'created_at']
    search_fields = ('document_name', 'document_type', 'description', 'order__order_number',
                     'uploaded_by__username')
    readonly_fields = ['created_at', 'updated_at']
    date_hierarchy = 'created_at'


@admin.register(ezzy_api_models.EcommerceIntegration)
class EcommerceIntegrationAdmin(admin.ModelAdmin):
    list_display = ['business', 'platform', 'sync_status', 'last_sync', 'total_orders_imported', 'created_at']
    list_filter = ['platform', 'sync_status', 'created_at']
    search_fields = ('sync_status', 'platform', 'sync_error', 'business__business_name',
                     'api_settings__google_sheet_tab_name')
    readonly_fields = ['last_sync', 'total_orders_imported', 'created_at', 'updated_at']
    date_hierarchy = 'created_at'


@admin.register(ezzy_api_models.WebhookEndpoint)
class WebhookEndpointAdmin(admin.ModelAdmin):
    list_display = ['url', 'business', 'is_active', 'last_triggered', 'created_at']
    list_filter = ['is_active', 'created_at']
    search_fields = ['url', 'business__business_name', 'description']
    readonly_fields = ['secret', 'created_at', 'updated_at', 'last_triggered']
    date_hierarchy = 'created_at'
    filter_horizontal = []


@admin.register(ezzy_api_models.WebhookDelivery)
class WebhookDeliveryAdmin(admin.ModelAdmin):
    list_display = ['webhook', 'event_type', 'status', 'response_status', 'attempt_count', 'created_at']
    list_filter = ['status', 'event_type', 'created_at']
    search_fields = ('event_type', 'status', 'error_message', 'response_body', 'webhook__url')
    readonly_fields = ['created_at', 'delivered_at']
    date_hierarchy = 'created_at'

# ─────────────────────────────────────────────────────────────────────────────
# Tables that had no admin page. Registered so every model is reachable and
# searchable from /dj-admin/. Related rows use raw id fields so a changelist
# never renders a dropdown of the whole table.
# ─────────────────────────────────────────────────────────────────────────────

@admin.register(ezzy_api_models.WebhookImportKey)
class WebhookImportKeyAdmin(admin.ModelAdmin):
    list_display = ('business', 'is_active', 'created_at', 'last_used', 'total_received')
    search_fields = ('business__business_name',)
    list_filter = ('is_active',)
    list_select_related = ('business',)
    raw_id_fields = ('business',)

@admin.register(ezzy_api_models.WebhookImportLog)
class WebhookImportLogAdmin(admin.ModelAdmin):
    list_display = ('webhook_key', 'business', 'ip_address', 'status', 'orders_created', 'created_at')
    search_fields = ('ip_address', 'status', 'error_message', 'business__business_name')
    list_filter = ('status',)
    list_select_related = ('webhook_key', 'business')
    raw_id_fields = ('webhook_key', 'business')
