from django.contrib import admin
from ezzy_api import models as ezzy_api_models


@admin.register(ezzy_api_models.ClientApiKey)
class ClientApiKeyAdmin(admin.ModelAdmin):
    list_display = ['api_key', 'business', 'key_name', 'is_active', 'last_used', 'expires_at', 'created_at']
    list_filter = ['is_active', 'created_at', 'expires_at']
    search_fields = ['api_key', 'business__business_name', 'key_name']
    readonly_fields = ['api_key', 'api_secret', 'created_at', 'updated_at']
    date_hierarchy = 'created_at'


@admin.register(ezzy_api_models.TaskDocument)
class TaskDocumentAdmin(admin.ModelAdmin):
    list_display = ['task', 'document_type', 'document_name', 'uploaded_by', 'created_at']
    list_filter = ['document_type', 'created_at']
    search_fields = ['task__dl_task_number', 'document_name', 'description']
    readonly_fields = ['created_at', 'updated_at']
    date_hierarchy = 'created_at'


@admin.register(ezzy_api_models.OrderDocument)
class OrderDocumentAdmin(admin.ModelAdmin):
    list_display = ['order', 'document_type', 'document_name', 'uploaded_by', 'created_at']
    list_filter = ['document_type', 'created_at']
    search_fields = ['order__order_number', 'document_name', 'description']
    readonly_fields = ['created_at', 'updated_at']
    date_hierarchy = 'created_at'


@admin.register(ezzy_api_models.EcommerceIntegration)
class EcommerceIntegrationAdmin(admin.ModelAdmin):
    list_display = ['business', 'platform', 'sync_status', 'last_sync', 'total_orders_imported', 'created_at']
    list_filter = ['platform', 'sync_status', 'created_at']
    search_fields = ['business__business_name', 'platform']
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
    search_fields = ['webhook__url', 'event_type', 'error_message']
    readonly_fields = ['created_at', 'delivered_at']
    date_hierarchy = 'created_at'
