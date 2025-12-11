"""
Business Models Module
=============================

This module contains models for business stores using the EzzyDelivery platform.

Models:
    Core Business Models:
        - Business: Main business entity with contact info and status
        - BusinessProfile: Extended business details (description, social media)
        - BusinessLogo: Business logo images
        - BusinessApiSettings: API credentials for integrations (Shopify, WooCommerce)
        - BusinessTeamProfile: Team member access and roles

    Location & Fulfillment:
        - PickupLocation: Business pickup/warehouse locations
        - DriverDirectory: Drivers associated with a business

    E-commerce Integration:
        - ShopifySettings: Shopify store credentials
        - WoocommerceSettings: WooCommerce store credentials

Business Status Flow:
    pending -> active -> suspended (if issues)
                     -> inactive (if deactivated)

Team Roles:
    - owner: Full access, can manage business
    - admin: Can manage orders and team
    - member: Can view and process orders
    - viewer: Read-only access

Related Apps:
    - orders: Business places orders
    - delivery: Orders create delivery tasks
    - product: Business manages products
"""

from email.policy import default
import os
from django.conf import settings
from django.db import models
from core import models as core_models
from fleet import models as fleet_models


def upload_path_handler(instance, filename):
    """
    Generate upload path for business files.

    Args:
        instance: Model instance with 'path' attribute
        filename: Original filename

    Returns:
        str: Path in format '{instance.path}/logo/{filename}'
    """
    upload_dir = os.path.join(
        str(instance.path), 'logo')
    if not os.path.exists(upload_dir):
        os.makedirs(upload_dir)
    return os.path.join(upload_dir, filename)


# =============================================================================
# BUSINESS MODELS
# =============================================================================


class Business(models.Model):
    """
    Main business entity model.

    Represents a business store on the EzzyDelivery platform. Each business
    can have multiple orders, products, pickup locations, and team members.

    Attributes:
        user (ForeignKey): Owner's user account
        profile (ForeignKey): Owner's profile
        business_id (int): Primary key, unique business identifier
        business_code (str): Unique short code (e.g., 'SHOP001')
        business_name (str): Display name
        business_status (str): active, inactive, pending, suspended

    Status Values:
        - active: Business is operational
        - inactive: Business deactivated by owner
        - pending: Awaiting admin approval
        - suspended: Suspended due to issues

    Related Models:
        - BusinessProfile: business.business_profile
        - BusinessLogo: business.business_logo
        - Order: business.orders
        - PickupLocation: business.pickup_location
        - Product: business.product
        - BusinessTeamProfile: business.business_team

    Usage:
        >>> business = Business.objects.get(business_code='SHOP001')
        >>> orders = business.orders.filter(order_status='pending')
    """
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, blank=True, null=True, related_name='user_business')
    
    profile = models.ForeignKey(
        core_models.Profile, on_delete=models.SET_NULL, blank=True, null=True, related_name='profile_business')
    business_id = models.PositiveIntegerField(primary_key=True)
    business_name = models.CharField(
        max_length=100, blank=True, null=True)
    business_bio = models.CharField(max_length=225, blank=True, null=True)
    business_code = models.CharField(max_length=225, blank=True, null=True, unique=True)
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

    # Fulfillment Service - Businesses using EzzyDelivery's fulfillment/WMS service
    fulfillment_service_enabled = models.BooleanField(
        default=False,
        help_text="Enable fulfillment service (WMS integration) for this business"
    )
    fulfillment_activated_at = models.DateTimeField(
        blank=True, null=True,
        help_text="When the fulfillment service was activated"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "Business"
        db_table = 'client_business'  # Keep using the existing table name

    def __str__(self):
        return self.business_name or f"Business ID: {self.business_id}"


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
    business_twitter = models.CharField(
        max_length=100, blank=True, null=True)
    business_linkedin = models.CharField(
        max_length=100, blank=True, null=True)
    business_snapchat = models.CharField(
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


class BusinessPoster(models.Model):
    """Model for business promotional posters/banners (up to 6)"""
    business = models.ForeignKey(
        Business, on_delete=models.CASCADE, related_name='business_posters')
    poster_image = models.ImageField(
        upload_to=upload_path_handler, blank=True, null=True,
        help_text='Upload promotional poster/banner image')
    poster_title = models.CharField(max_length=200, blank=True, null=True,
                                     help_text='Optional title for the poster')
    poster_description = models.TextField(max_length=500, blank=True, null=True,
                                          help_text='Optional description')
    poster_order = models.PositiveIntegerField(default=0,
                                                help_text='Display order (0-5)')
    is_active = models.BooleanField(default=True,
                                     help_text='Show/hide this poster')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "Business Posters"
        ordering = ['poster_order', '-created_at']

    def __str__(self):
        return f"{self.business.business_name} - Poster {self.poster_order + 1}"


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
    pickup_lat = models.DecimalField(max_digits=19, decimal_places=15, blank=True, null=True)
    pickup_lon = models.DecimalField(max_digits=19, decimal_places=15, blank=True, null=True)
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
        return str(self.driver.driver_code)

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
        return str(self.business)
