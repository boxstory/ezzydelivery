from django.contrib import admin
from webpages import models as webpages_models
# Register your models here.


@admin.register(webpages_models.Careers)
class CareersAdmin(admin.ModelAdmin):
    list_display = ( 'full_name' , 'mobile' , 'qid' , 'job' , 'self_intro')

    

@admin.register(webpages_models.ContactUs)
class ContactUsAdmin(admin.ModelAdmin):
    list_display = ( 'full_name' , 'mobile' , 'purpose','message' )


@admin.register(webpages_models.PricingPlanOption)
class PricingPlanOptionAdmin(admin.ModelAdmin):
    """The rate card the quote page renders. Editing a price here changes what
    new visitors are offered — agreements already made keep their snapshot."""
    list_display = ('name', 'key', 'price_display', 'price_unit', 'is_custom_quote', 'is_active', 'sort_order')
    list_filter = ('is_active', 'is_custom_quote', 'is_featured')
    search_fields = ('name', 'key', 'subtitle')
    ordering = ('sort_order', 'id')
    readonly_fields = ('created_at', 'updated_at')


class PricingRuleInline(admin.TabularInline):
    model = webpages_models.PricingRule
    extra = 0
    fields = ('dimension', 'label', 'match_field', 'match_kind', 'match_min', 'match_max',
              'effect', 'amount', 'priority', 'is_active')
    ordering = ('dimension', 'priority')


@admin.register(webpages_models.PricingRuleSet)
class PricingRuleSetAdmin(admin.ModelAdmin):
    """The rate card the suggestion engine reads. Editing a rate changes what new
    leads are quoted; suggestions already made keep their stored numbers."""
    list_display = ('name', 'code', 'is_active', 'base_price_default', 'min_price_floor', 'floor_basis')
    list_filter = ('is_active', 'floor_basis')
    search_fields = ('code', 'name')
    readonly_fields = ('created_at', 'updated_at')
    inlines = [PricingRuleInline]


@admin.register(webpages_models.PricingRule)
class PricingRuleAdmin(admin.ModelAdmin):
    list_display = ('label', 'ruleset', 'dimension', 'effect', 'amount', 'priority', 'is_active')
    list_filter = ('ruleset', 'dimension', 'is_active', 'effect')
    search_fields = ('label', 'match_field', 'match_value')
    ordering = ('ruleset', 'dimension', 'priority')


@admin.register(webpages_models.PricingSuggestion)
class PricingSuggestionAdmin(admin.ModelAdmin):
    """Audit trail. Read-only by design — a suggestion is a record of what the
    engine said at a point in time, not a field to correct after the fact."""
    list_display = ('inquiry', 'suggested_price', 'ruleset_code', 'staff_action',
                    'staff_price', 'created_at')
    list_filter = ('ruleset_code', 'staff_action', 'created_at')
    search_fields = ('inquiry__business_name',)
    ordering = ('-created_at',)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(webpages_models.PricingEnquiry)
class PricingEnquiryAdmin(admin.ModelAdmin):
    list_display = ( 'full_name' , 'business_name' , 'business_contact_number' , 'product_category' , 'agreed_plan_name' , 'is_personalized_product' , 'is_registered_company_in_qatar' , 'is_located_in_qatar' , 'is_team_available_in_qatar' , 'is_required_COD_service' , 'is_required_fulfillment_service_for_operate_from_outside_qatar'  )
    list_filter = ('selected_plan', 'is_personalized_product', 'is_registered_company_in_qatar', 'is_located_in_qatar', 'is_team_available_in_qatar', 'is_required_COD_service', 'is_required_fulfillment_service_for_operate_from_outside_qatar' )
    search_fields = ('full_name', 'business_name', 'business_contact_number', 'product_category' )
    ordering = ('-date_modified',)
    # The agreement is a record of what the customer accepted — staff correct it
    # on the inquiry page with an activity trail, not by silently retyping it here.
    readonly_fields = ('id', 'quote_token', 'agreed_plan_name', 'agreed_price_display',
                       'agreed_price_unit', 'agreed_price_value', 'plan_agreed_at',
                       'plan_agreement_ip', 'plan_agreement_user_agent')


@admin.register(webpages_models.WhatsAppInquiry)
class WhatsAppInquiryAdmin(admin.ModelAdmin):
    list_display = ('company_name', 'contact_person', 'contact_number', 'product_category', 'created_at')
    list_filter = ('product_category', 'created_at')
    search_fields = ('company_name', 'contact_person', 'contact_number', 'product_category', 'product_name')
    ordering = ('-created_at',)
    readonly_fields = ('created_at',)