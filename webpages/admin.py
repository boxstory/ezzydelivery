from django.contrib import admin
from webpages import models as webpages_models
# Register your models here.


@admin.register(webpages_models.Careers)
class CareersAdmin(admin.ModelAdmin):
    list_display = ( 'full_name' , 'mobile' , 'qid' , 'job' , 'self_intro')

    

@admin.register(webpages_models.ContactUs)
class ContactUsAdmin(admin.ModelAdmin):
    list_display = ( 'full_name' , 'mobile' , 'purpose','message' )


@admin.register(webpages_models.PricingEnquiry)
class PricingEnquiryAdmin(admin.ModelAdmin):
    list_display = ( 'full_name' , 'business_name' , 'business_contact_number' , 'product_category' , 'is_personalized_product' , 'is_registered_company_in_qatar' , 'is_located_in_qatar' , 'is_team_available_in_qatar' , 'is_required_COD_service' , 'is_required_fulfillment_service_for_operate_from_outside_qatar'  )
    list_filter = ('is_personalized_product', 'is_registered_company_in_qatar', 'is_located_in_qatar', 'is_team_available_in_qatar', 'is_required_COD_service', 'is_required_fulfillment_service_for_operate_from_outside_qatar' )
    search_fields = ('full_name', 'business_name', 'business_contact_number', 'product_category' )
    ordering = ('-date_modified',)
    readonly_fields = ('id',)