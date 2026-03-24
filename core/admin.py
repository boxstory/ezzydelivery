from django.contrib import admin
from .models import WhatsAppVerification, WhatsAppInstance


@admin.register(WhatsAppVerification)
class WhatsAppVerificationAdmin(admin.ModelAdmin):
    list_display = ['phone_number', 'verification_type', 'verification_code', 'is_verified', 'attempts', 'created_at', 'expires_at']
    list_filter = ['verification_type', 'is_verified', 'created_at']
    search_fields = ['phone_number', 'user__username', 'verification_code']
    readonly_fields = ['created_at', 'verified_at']

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related('user')


@admin.register(WhatsAppInstance)
class WhatsAppInstanceAdmin(admin.ModelAdmin):
    list_display = ['label', 'instance_name', 'phone_number', 'is_default', 'is_active']
    list_editable = ['is_default', 'is_active']
    list_filter = ['is_active', 'is_default']
    search_fields = ['label', 'instance_name', 'phone_number']
