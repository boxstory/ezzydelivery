from django.contrib import admin

from allauth.socialaccount.admin import SocialAppAdmin, SocialTokenAdmin
from allauth.socialaccount.models import SocialApp, SocialToken

from .models import WhatsAppVerification, WhatsAppInstance
from core import models as core_models

# Replaced further down with versions that have a search box.
admin.site.unregister(SocialApp)
admin.site.unregister(SocialToken)


@admin.register(WhatsAppVerification)
class WhatsAppVerificationAdmin(admin.ModelAdmin):
    list_display = ['phone_number', 'verification_type', 'verification_code', 'is_verified', 'attempts', 'created_at', 'expires_at']
    list_filter = ['verification_type', 'is_verified', 'created_at']
    search_fields = ('phone_number', 'verification_code', 'verification_type', 'user__username')
    readonly_fields = ['created_at', 'verified_at']

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related('user')


@admin.register(WhatsAppInstance)
class WhatsAppInstanceAdmin(admin.ModelAdmin):
    list_display = ['label', 'instance_name', 'phone_number', 'is_default', 'is_active']
    list_editable = ['is_default', 'is_active']
    list_filter = ['is_active', 'is_default']
    search_fields = ('phone_number', 'label', 'instance_name', 'waha_session')

# ─────────────────────────────────────────────────────────────────────────────
# Tables that had no admin page. Registered so every model is reachable and
# searchable from /dj-admin/. Related rows use raw id fields so a changelist
# never renders a dropdown of the whole table.
# ─────────────────────────────────────────────────────────────────────────────

@admin.register(core_models.AutoFlow)
class AutoFlowAdmin(admin.ModelAdmin):
    list_display = ('name', 'trigger', 'action_type', 'is_enabled', 'created_at', 'updated_at')
    search_fields = ('name', 'action_type', 'trigger__trigger_key')
    list_filter = ('action_type', 'is_enabled')
    list_select_related = ('trigger',)
    raw_id_fields = ('trigger',)

@admin.register(core_models.AutoFlowLog)
class AutoFlowLogAdmin(admin.ModelAdmin):
    list_display = ('flow', 'status', 'executed_at', 'duration_ms')
    search_fields = ('status', 'result', 'error', 'flow__name')
    list_filter = ('status',)
    list_select_related = ('flow',)
    raw_id_fields = ('flow',)

@admin.register(core_models.AutoFlowThrottle)
class AutoFlowThrottleAdmin(admin.ModelAdmin):
    list_display = ('flow', 'last_sent_at', 'pending_count', 'pending_since', 'updated_at')
    search_fields = ('flow__name',)
    list_select_related = ('flow',)
    raw_id_fields = ('flow',)

@admin.register(core_models.AutoTriggerConfig)
class AutoTriggerConfigAdmin(admin.ModelAdmin):
    list_display = ('trigger_key', 'label', 'category', 'department', 'is_enabled', 'action', 'whatsapp_instance')
    search_fields = ('notify_number', 'label', 'whatsapp_channel', 'trigger_key', 'category',
                     'department', 'description', 'action', 'whatsapp_instance__instance_name')
    list_filter = ('category', 'department', 'is_enabled', 'whatsapp_channel')
    list_select_related = ('whatsapp_instance',)
    raw_id_fields = ('whatsapp_instance',)

@admin.register(core_models.MessageTemplate)
class MessageTemplateAdmin(admin.ModelAdmin):
    list_display = ('key', 'msg_id', 'label', 'is_custom', 'section', 'is_enabled',
                    'updated_at', 'updated_by')
    search_fields = ('key', 'label', 'body', 'updated_by__username')
    list_filter = ('is_custom', 'is_enabled', 'section')
    list_select_related = ('updated_by',)
    raw_id_fields = ('updated_by',)

@admin.register(core_models.PageDepartment)
class PageDepartmentAdmin(admin.ModelAdmin):
    list_display = ('url_name', 'namespace', 'departments', 'is_enabled', 'label', 'notes', 'created_at')
    search_fields = ('url_name', 'namespace', 'departments', 'label', 'notes', 'updated_by__username')
    list_filter = ('is_enabled',)
    raw_id_fields = ('updated_by',)

@admin.register(core_models.WhatsAppSendLog)
class WhatsAppSendLogAdmin(admin.ModelAdmin):
    list_display = ('instance_name', 'channel', 'phone_number', 'success', 'status_code', 'detail', 'created_at')
    search_fields = ('instance_name', 'channel', 'phone_number', 'detail')
    list_filter = ('channel', 'success')

@admin.register(core_models.WhatsAppSenderRoute)
class WhatsAppSenderRouteAdmin(admin.ModelAdmin):
    list_display = ('section', 'instance', 'channel', 'is_enabled', 'updated_at')
    search_fields = ('section', 'channel', 'instance__instance_name')
    list_filter = ('section', 'channel', 'is_enabled')
    list_select_related = ('instance',)
    raw_id_fields = ('instance',)


# ─────────────────────────────────────────────────────────────────────────────
# allauth ships these two without a search box. Local apps are imported after
# allauth, so swapping the admin class here is what the site ends up using.
# The credential columns (secret, key, token) stay out of both the list and the
# search box — they are readable on the change form and nowhere else.
# ─────────────────────────────────────────────────────────────────────────────

@admin.register(SocialApp)
class EzzySocialAppAdmin(SocialAppAdmin):
    list_display = ('name', 'provider', 'provider_id', 'client_id')
    list_filter = ('provider',)
    search_fields = ('name', 'provider', 'provider_id', 'client_id')


@admin.register(SocialToken)
class EzzySocialTokenAdmin(SocialTokenAdmin):
    search_fields = ('app__name', 'app__provider', 'account__uid',
                     'account__user__username', 'account__user__email')
    search_help_text = 'Search by provider, account uid or the user it belongs to'
