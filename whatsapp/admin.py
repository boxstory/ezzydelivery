from django.contrib import admin
from .models import WhatsAppMessage
from whatsapp import models as whatsapp_models


@admin.register(WhatsAppMessage)
class WhatsAppMessageAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'direction', 'status', 'from_number', 'to_number',
        'message_type', 'received_at', 'business',
    )
    list_filter = ('direction', 'status', 'message_type', 'session')
    search_fields = ('from_number', 'to_number', 'message_type', 'status', 'error_kind', 'body',
                     'waha_message_id', 'session', 'direction', 'media_url', 'media_mime',
                     'order__order_number', 'business__business_name')
    readonly_fields = (
        'waha_message_id', 'raw_payload', 'created_at', 'updated_at',
        'received_at', 'picked_up_at', 'processed_at',
    )
    date_hierarchy = 'received_at'

# ─────────────────────────────────────────────────────────────────────────────
# Tables that had no admin page. Registered so every model is reachable and
# searchable from /dj-admin/. Related rows use raw id fields so a changelist
# never renders a dropdown of the whole table.
# ─────────────────────────────────────────────────────────────────────────────

@admin.register(whatsapp_models.AddressVerificationJob)
class AddressVerificationJobAdmin(admin.ModelAdmin):
    list_display = ('order', 'phone', 'kind', 'scheduled_for', 'status', 'send_attempts', 'created_at')
    search_fields = ('phone', 'kind', 'status', 'last_error', 'notes', 'driver_failure_note',
                     'order__order_number', 'sent_message__from_number',
                     'received_message__from_number')
    list_filter = ('kind', 'status')
    list_select_related = ('order',)
    raw_id_fields = ('order', 'sent_message', 'received_message')

@admin.register(whatsapp_models.WahaConfig)
class WahaConfigAdmin(admin.ModelAdmin):
    list_display = ('verify_messaging_enabled', 'last_toggled_by', 'last_toggled_at', 'updated_at')
    search_fields = ('last_toggled_by__username',)
    list_filter = ('verify_messaging_enabled',)
    list_select_related = ('last_toggled_by',)
    raw_id_fields = ('last_toggled_by',)

@admin.register(whatsapp_models.WhatsAppContact)
class WhatsAppContactAdmin(admin.ModelAdmin):
    list_display = ('session', 'phone', 'lid', 'saved_name', 'push_name', 'is_business', 'created_at')
    search_fields = ('session', 'phone', 'lid', 'saved_name', 'push_name', 'notes')
    list_filter = ('is_business', 'is_my_contact')
