from django.contrib import admin
from webpages import models as webpages_models
# Register your models here.


@admin.register(webpages_models.Careers)
class CareersAdmin(admin.ModelAdmin):
    list_display = ( 'full_name' , 'mobile' , 'qid' , 'job' , 'self_intro')

    

@admin.register(webpages_models.ContactUs)
class ContactUsAdmin(admin.ModelAdmin):
    list_display = ( 'full_name' , 'mobile' , 'purpose','message' )


admin.site.register(webpages_models.PricingEnquiry)