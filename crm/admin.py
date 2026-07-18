# Purpose: Django admin registration for CRM Lead, LeadActivity, and InboxDismissal.
# Used by: Django admin site (/admin/crm/).

from django.contrib import admin

from .models import InboxDismissal, Lead, LeadActivity


@admin.register(Lead)
class LeadAdmin(admin.ModelAdmin):
    list_display = ('id', 'company_name', 'contact_name', 'phone', 'source',
                    'stage', 'assigned_to', 'next_followup_at', 'created_at')
    list_filter = ('stage', 'source', 'assigned_to')
    search_fields = ('company_name', 'contact_name', 'phone')
    readonly_fields = ('created_at', 'updated_at', 'stage_changed_at', 'closed_at')
    list_per_page = 50


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
