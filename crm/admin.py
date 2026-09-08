# Purpose: Django admin registration for CRM Lead, LeadStage, LeadActivity, and InboxDismissal.
# Used by: Django admin site (/admin/crm/).
# Notes: Board columns are normally managed at /workforce/crm/stages/ — the LeadStage admin is the raw fallback.

from django.contrib import admin

from .models import InboxDismissal, Lead, LeadActivity, LeadStage


@admin.register(Lead)
class LeadAdmin(admin.ModelAdmin):
    list_display = ('id', 'company_name', 'contact_name', 'phone', 'source',
                    'stage', 'assigned_to', 'next_followup_at', 'created_at')
    list_filter = ('stage', 'source', 'assigned_to')
    search_fields = ('company_name', 'contact_name', 'phone')
    readonly_fields = ('created_at', 'updated_at', 'stage_changed_at', 'closed_at')
    list_per_page = 50


@admin.register(LeadStage)
class LeadStageAdmin(admin.ModelAdmin):
    list_display = ('category', 'position', 'label', 'key', 'is_closed', 'is_fallback',
                    'write_back', 'is_active', 'is_system')
    list_filter = ('category', 'is_closed', 'is_active', 'is_system')
    search_fields = ('key', 'label')
    ordering = ('category', 'position')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(LeadActivity)
class LeadActivityAdmin(admin.ModelAdmin):
    list_display = ('id', 'lead', 'activity_type', 'created_by', 'created_at')
    list_filter = ('activity_type',)
    search_fields = ('lead__company_name', 'body')
    list_per_page = 50


@admin.register(InboxDismissal)
class InboxDismissalAdmin(admin.ModelAdmin):
    list_display = ('phone', 'dismissed_by', 'created_at')
    search_fields = ('phone',)
