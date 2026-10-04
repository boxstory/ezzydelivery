# Purpose: Django admin registration for CRM Lead (+ its linked WhatsApp numbers), LeadStage, LeadActivity, and InboxDismissal.
# Used by: Django admin site (/admin/crm/).
# Notes: Board columns are normally managed at /workforce/crm/stages/ — the LeadStage admin is the raw fallback.

from django.contrib import admin

from .models import InboxDismissal, Lead, LeadActivity, LeadStage, LeadWaLink


class LeadWaLinkInline(admin.TabularInline):
    model = LeadWaLink
    extra = 0
    fields = ('identifier', 'label', 'session', 'created_by', 'created_at')
    readonly_fields = ('created_by', 'created_at')


@admin.register(Lead)
class LeadAdmin(admin.ModelAdmin):
    inlines = [LeadWaLinkInline]
    list_display = ('id', 'company_name', 'contact_name', 'phone', 'source',
                    'stage', 'assigned_to', 'next_followup_at', 'created_at')
    list_filter = ('stage', 'source', 'assigned_to')
    search_fields = ('company_name', 'contact_name', 'phone', 'phone_2', 'source', 'category',
                     'product_category', 'wa_chat_override', 'wa_links__identifier', 'wa_session', 'stage', 'notes',
                     'ai_summary', 'whatsapp_inquiry__contact_number',
                     'pricing_enquiry__business_name', 'assigned_to__username',
                     'converted_business__business_name', 'merged_into__company_name',
                     'merged_by__username')
    readonly_fields = ('created_at', 'updated_at', 'stage_changed_at', 'closed_at')
    list_per_page = 50


@admin.register(LeadStage)
class LeadStageAdmin(admin.ModelAdmin):
    list_display = ('category', 'position', 'label', 'key', 'is_closed', 'is_fallback',
                    'write_back', 'is_active', 'is_system')
    list_filter = ('category', 'is_closed', 'is_active', 'is_system')
    search_fields = ('label', 'crm_status', 'key', 'category', 'outcome', 'write_back',
                     'confirm_text', 'dot_swatch')
    ordering = ('category', 'position')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(LeadActivity)
class LeadActivityAdmin(admin.ModelAdmin):
    list_display = ('id', 'lead', 'activity_type', 'created_by', 'created_at')
    list_filter = ('activity_type',)
    search_fields = ('activity_type', 'body', 'lead__company_name', 'created_by__username')
    list_per_page = 50


@admin.register(InboxDismissal)
class InboxDismissalAdmin(admin.ModelAdmin):
    list_display = ('phone', 'dismissed_by', 'created_at')
    search_fields = ('phone', 'dismissed_by__username')
