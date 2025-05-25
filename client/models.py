from email.policy import default
import os
from django.conf import settings
from django.db import models
from core import models as core_models
from fleet import models as fleet_models


# Create your models here.


def upload_path_handler(instance, filename):
    upload_dir = os.path.join(
        str(instance.path), 'logo')
    if not os.path.exists(upload_dir):
        os.makedirs(upload_dir)
    return os.path.join(upload_dir, filename)


# business---------------------------------------------------------------------------------------------------------------------


class Business(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='user_business')
    
    profile = models.ForeignKey(
        core_models.Profile, on_delete=models.SET_NULL, blank=True, null=True, related_name='profile_business')
    business_id = models.PositiveIntegerField(primary_key=True)
    business_name = models.CharField(
        max_length=100, blank=True, null=True)
    business_bio = models.CharField(max_length=225, blank=True, null=True)
    business_code = models.CharField(max_length=225, blank=True, null=True)
    business_phone = models.CharField(max_length=100, blank=True, null=True)
    business_email = models.CharField(max_length=100, blank=True, null=True)
    business_whatsapp = models.CharField(
        max_length=100, blank=True, null=True)
    
    business_facebook_page = models.CharField(
        max_length=100, blank=True, null=True)
    business_instagram = models.CharField(max_length=100, blank=True, null=True)
    business_since = models.DateField(max_length=100, blank=True, null=True)
    business_product_category = models.CharField(
        max_length=100, blank=True, null=True)
    business_code = models.CharField(max_length=100, blank=True, null=True)
    business_languages = models.CharField(
        max_length=100,  default='english')
    business_qid = models.CharField(max_length=11, blank=True, null=True)
    status_choices = (
        ('active', 'Active'),
        ('inactive', 'Inactive'),
        ('pending', 'Aproval Pending'),
        ('suspended', 'Suspended'),
    )
    
    business_status = models.CharField(
        max_length=100,  choices=status_choices, default='aproval pending')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "Business"

    def __str__(self):
        return self.business_name


class BusinessProfile(models.Model):
    business = models.OneToOneField(
        Business, on_delete=models.CASCADE, related_name='business_profile')
    business_description = models.TextField(max_length=225, blank=True, 
                                            null=True)


    business_address = models.CharField(max_length=225, blank=True, null=True)
    business_city = models.CharField(max_length=100, blank=True, null=True)
    business_state = models.CharField(max_length=100, blank=True, null=True)
    business_zip_code = models.CharField(max_length=10, blank=True, null=True)
    business_country = models.CharField(max_length=100, blank=True, 
                                        null=True, default='Qatar')
    business_start_date = models.DateField(max_length=100, blank=True, null=True) 

    business_founters_name = models.CharField(max_length=100, blank=True, null=True)
    business_founters_bio = models.CharField(max_length=100, blank=True, null=True)
    business_mision = models.TextField(max_length=25, blank=True, null=True)
    business_mision_detailed = models.TextField(max_length=125, blank=True, null=True)
    business_about_part_1 = models.TextField(max_length=125, blank=True, null=True)
    business_about_part_2 = models.TextField(max_length=125, blank=True, null=True)
    business_uniqueness_title = models.CharField(max_length=225, blank=True, null=True)
    business_uniqueness_description = models.TextField(max_length=225, blank=True, null=True)
    business_catagory_main = models.CharField(max_length=20, blank=True, null=True)
    business_catagory_detailed = models.TextField(max_length=100, blank=True, null=True)


    business_website = models.CharField(max_length=100, blank=True, null=True)
    business_facebook_page = models.CharField(
        max_length=100, blank=True, null=True)
    business_instagram = models.CharField(
        max_length=100, blank=True, null=True)
    business_tiktok = models.CharField(
        max_length=100, blank=True, null=True)
    business_youtube = models.CharField(
        max_length=100, blank=True, null=True) 
    business_email = models.CharField(max_length=100, blank=True, 
                                      null=True)
    business_phone = models.CharField(max_length=12, blank=True, 
                                      null=True)
     

    
    created_at = models.DateTimeField(auto_now_add=True)

    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.business.business_name

    class Meta:
        verbose_name_plural = "Business Profile"






class BusinessApiSettings(models.Model):
    type_choices = (
        ('shopify', 'Shopify'),
        ('woocommerce', 'Woocommerce'),
        ('magento', 'Magento'),
        ('opencart', 'Opencart'),
        ('prestashop', 'Prestashop'),
        ('bigcommerce', 'Bigcommerce'),
        ('custom', 'Custom'),
    )
    api_type = models.CharField(
        max_length=100, choices=type_choices, default='custom')
    api_access_token = models.CharField(max_length=100, blank=True, null=True)
    api_key = models.CharField(max_length=100, blank=True, null=True)
    api_secret = models.CharField(max_length=100, blank=True, null=True)
    api_version = models.CharField(max_length=100, blank=True, null=True)
    site_api_url = models.CharField(max_length=100, blank=True, null=True)
    site_contry = models.CharField(max_length=100, blank=True, null=True, default='Qatar')
    order_api_endpoint = models.CharField(max_length=100, blank=True, null=True)
    product_api_endpoint = models.CharField(max_length=100, blank=True, null=True)
    is_verify_api = models.BooleanField(default=False)
    is_default = models.BooleanField(default=False)
    business = models.ForeignKey(
        Business, on_delete=models.CASCADE, related_name='business_settings_api')
    business_languages = models.CharField(
        max_length=100, default='english')
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "Business Settings"

    def __str__(self):
        return self.business.business_name
    


class BusinessLogo(models.Model):
    business = models.ForeignKey(
        Business, on_delete=models.CASCADE, blank=True, null=True, related_name='business_logo')
    business_logo = models.ImageField(
        upload_to=upload_path_handler, default="business/avatar.png", blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name_plural = "Business Logo"

    def __str__(self):
        return str(self.business.business_name)


# @todo: link team profile with business


class BusinessTeamProfile(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='team_profile')
    profile = models.ForeignKey(
        core_models.Profile, on_delete=models.SET_NULL, blank=True, null=True, related_name='team_profile')
    business = models.ForeignKey(
        Business, on_delete=models.CASCADE, related_name='team_profile')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    team_code = models.CharField(max_length=100, blank=True, null=True)
    team_role = models.CharField(max_length=100, blank=True, null=True)
    team_name = models.CharField(max_length=100, blank=True, null=True)
    team_phone = models.CharField(max_length=100, blank=True, null=True)
    team_email = models.CharField(max_length=100, blank=True, null=True)
    team_bio = models.CharField(max_length=225, blank=True, null=True)
    team_logo = models.ImageField(
        upload_to=upload_path_handler, default="business/avatar.png", blank=True, null=True)
    team_verifed = models.BooleanField(default=False)
    team_status_choices = (
        ('aproval pending', 'Aproval Pending'),
        ('active', 'Active'),
        ('inactive', 'Inactive'),
        ('suspended', 'Suspended'),

    )

    team_status = models.CharField(
        max_length=100, choices=team_status_choices, default='aproval pending')
    
    class Meta:
        verbose_name_plural = "Staff Profile"
        unique_together = ('business', 'team_code')


class PickupLocation(models.Model):
    business = models.ForeignKey(
        Business, on_delete=models.CASCADE, related_name='pickup_location')
    pickup_location_title = models.CharField(max_length=100)
    locality = models.CharField(max_length=100)
    pickup_zone_no = models.PositiveIntegerField(blank=True, null=True)
    pickup_street_no = models.PositiveIntegerField(blank=True, null=True)
    pickup_building_no = models.PositiveIntegerField(
        blank=True, null=True)
    pickup_lat = models.PositiveIntegerField(blank=True, null=True)
    pickup_lon = models.PositiveIntegerField(blank=True, null=True)
    status_choices = (
        ('active', 'Active'),
        ('inactive', 'Inactive'),
        ('aproval pending', 'Aproval Pending'),
        ('suspended', 'Suspended'),
    )
    pickup_status = models.CharField(
        max_length=100, choices=status_choices, default='active')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.pickup_location_title

    class Meta:
        verbose_name_plural = "Pickup Location"


class DriverDirectory(models.Model):
    business = models.ForeignKey(
        Business, on_delete=models.CASCADE, related_name='driver_directory')
    driver = models.ForeignKey(
        fleet_models.Driver, on_delete=models.CASCADE, related_name='driver_directory')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.driver.driver_code

    class Meta:
        verbose_name_plural = "Drivers Directories"


class BusinessSocialInfo(models.Model):
    business = models.ForeignKey(
        Business, on_delete=models.CASCADE, related_name='business_social_info')
    facebook = models.CharField(max_length=100)
    instagram = models.CharField(max_length=100)
    whatsapp = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.business
