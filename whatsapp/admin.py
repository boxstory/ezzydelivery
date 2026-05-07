from django.contrib import admin
from .models import WhatsAppMessage


@admin.register(WhatsAppMessage)
class WhatsAppMessageAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'direction', 'status', 'from_number', 'to_number',
        'message_type', 'received_at', 'business',
    )
    list_filter = ('direction', 'status', 'message_type', 'session')
    search_fields = ('from_number', 'to_number', 'body', 'waha_message_id')
    readonly_fields = (
        'waha_message_id', 'raw_payload', 'created_at', 'updated_at',
        'received_at', 'picked_up_at', 'processed_at',
    )
    date_hierarchy = 'received_at'
