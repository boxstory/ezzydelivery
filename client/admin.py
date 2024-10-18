from django.contrib import admin
from client import models as business_models

from core import models as core_models

# Register your models here.


@admin.register(core_models.Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'first_name', 'last_name', 'email',
                    'whatsapp', 'is_business', 'is_driver', 'created_at', 'updated_at')
    list_filter = ('is_business', 'is_driver', 'created_at', 'updated_at')
    list_per_page = 10

@admin.register(core_models.ProfilePicture)
class ProfilePictureAdmin(admin.ModelAdmin):
    list_display = ( 'user', 'profile_picture')
    list_per_page = 10


@admin.register(business_models.Business)
class BusinessAdmin(admin.ModelAdmin):
    list_display = ('business_name', 'business_phone', 'business_whatsapp',
                     'business_since', 'business_product_category', 'business_code', 'created_at', 'updated_at')
    list_filter = ('created_at', 'updated_at')
    list_per_page = 10

@admin.register(business_models.BusinessLogo)
class BusinessLogoAdmin(admin.ModelAdmin):
    list_display = ('business', 'business_logo', 'created_at', 'updated_at')
    list_filter = ('business', 'created_at', 'updated_at')
    list_per_page = 10

@admin.register(business_models.PickupLocation)
class PickupLocationAdmin(admin.ModelAdmin):
    list_display = ('id', 'pickup_location_title', 'pickup_zone_no', 'pickup_street_no',
                    'pickup_building_no')


@admin.register(business_models.DriverDirectory)
class DriverDirectoryAdmin(admin.ModelAdmin):

    list_per_page = 10
