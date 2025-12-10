"""
Client/Business Forms Module
============================

This module contains forms for business registration, settings, and management.

Forms:
    Business Registration:
        - businessRegisterForm: Main business registration/update form

    Business Profile:
        - BusinessProfileForm: Extended business profile information
        - BusinessLogoForm: Business logo upload form

    API Settings:
        - businessApiSettingsForm: E-commerce API integration settings

    Locations:
        - PickupLocationsAddForm: Pickup/warehouse location form
        - DriverDirectoryAddForm: Driver directory entry form

    Team Management:
        - BusinessTeamProfileForm: Team member profile form

Validation:
    - Phone numbers must contain only digits
    - Social media fields extract usernames from URLs
    - All forms use crispy_forms for consistent styling

Related:
    - client.models: Business, BusinessProfile, PickupLocation, etc.
    - client.views: Views that use these forms
"""

from urllib import request
from django import forms
from django.contrib.auth.models import User

from crispy_forms.helper import FormHelper
from django.forms import ModelForm
from crispy_forms.layout import Layout, Field


from core import models as core_models
from fleet import models as fleet_models
from client import models as business_models


# =============================================================================
# CONSTANTS
# =============================================================================

business_LANGUAGE_CHOICES = (
    ('arabic', 'Arabic'),
    ('english', 'English'),
    ('hindi', 'Hindi'),
    ('philipine', 'Philipine'),
    ('other', 'Other'),
)
business_STATUS_CHOICES = (
    ('aproval pending', 'Aproval Pending'),
    ('active', 'Active'),
    ('inactive', 'Inactive'),
)


# =============================================================================
# BUSINESS REGISTRATION FORMS
# =============================================================================


class businessRegisterForm(forms.ModelForm):
    """
    Main business registration and update form.

    Used for initial business registration and updating business details.
    Includes validation for phone numbers and social media handles.

    Fields:
        - business_name: Display name of the business
        - business_phone: Contact phone (digits only)
        - business_whatsapp: WhatsApp number (digits only)
        - business_email: Contact email
        - business_bio: Short business description
        - business_facebook_page: Facebook username (extracted from URL)
        - business_instagram: Instagram username (extracted from URL)
        - business_since: Business establishment date
        - business_product_category: Main product category
        - business_languages: Primary language
        - business_qid: QID/Passport/CR number

    Validation:
        - Phone numbers: Only digits allowed
        - Social media: Extracts username from full URLs

    Template:
        client/frontend/business_profile_update.html

    Views:
        - core.views.business_register (initial registration)
        - client.views.business_profile_update (updates)
    """
    class Meta:
        model = business_models.Business
        fields = '__all__'

        exclude = ['profile', 'business_id', 'user',
                   'business_status', 'business_code', 'updated_at', 'created_at']
        widgets = {
            'business_name': forms.TextInput(attrs={'class': 'form-control'}),
            'business_languages': forms.Select(
                choices=business_LANGUAGE_CHOICES),
            'business_status': forms.Select(
                choices=business_STATUS_CHOICES),
            'business_since' : forms.TextInput(attrs={'type': 'date'}),


        }
        labels = {
            "business_name": "business Name",
            "business_phone": "business Phone No",
            "business_whatsapp": "business Whatsapp No",
            "business_qid": "Passport/QID/CR No",

        }

    def clean_business_phone(self):
        """Validate phone number contains only digits"""
        phone = self.cleaned_data.get('business_phone')
        if phone:
            # Remove common separators and spaces
            cleaned_phone = phone.replace(' ', '').replace('-', '').replace('(', '').replace(')', '').replace('+', '')
            if not cleaned_phone.isdigit():
                raise forms.ValidationError("Phone number must contain only numbers (digits 0-9)")
            # Return cleaned version
            return cleaned_phone
        return phone

    def clean_business_whatsapp(self):
        """Validate WhatsApp number contains only digits"""
        whatsapp = self.cleaned_data.get('business_whatsapp')
        if whatsapp:
            # Remove common separators and spaces
            cleaned_whatsapp = whatsapp.replace(' ', '').replace('-', '').replace('(', '').replace(')', '').replace('+', '')
            if not cleaned_whatsapp.isdigit():
                raise forms.ValidationError("WhatsApp number must contain only numbers (digits 0-9)")
            # Return cleaned version
            return cleaned_whatsapp
        return whatsapp

    def clean_business_facebook_page(self):
        """Validate Facebook page contains only username (no slashes or spaces)"""
        facebook = self.cleaned_data.get('business_facebook_page')
        if facebook:
            # Remove leading/trailing whitespace
            facebook = facebook.strip()
            # Check for slashes or spaces
            if '/' in facebook or ' ' in facebook:
                raise forms.ValidationError("Enter username only, without slashes (/) or spaces")
            # Remove common URL prefixes if user added them
            facebook = facebook.replace('https://', '').replace('http://', '')
            facebook = facebook.replace('www.facebook.com/', '').replace('facebook.com/', '')
            facebook = facebook.replace('@', '')
            return facebook.strip()
        return facebook

    def clean_business_instagram(self):
        """Validate Instagram contains only username (no slashes or spaces)"""
        instagram = self.cleaned_data.get('business_instagram')
        if instagram:
            # Remove leading/trailing whitespace
            instagram = instagram.strip()
            # Check for slashes or spaces
            if '/' in instagram or ' ' in instagram:
                raise forms.ValidationError("Enter username only, without slashes (/) or spaces")
            # Remove common URL prefixes if user added them
            instagram = instagram.replace('https://', '').replace('http://', '')
            instagram = instagram.replace('www.instagram.com/', '').replace('instagram.com/', '')
            instagram = instagram.replace('@', '')
            return instagram.strip()
        return instagram

# =============================================================================
# API SETTINGS FORMS
# =============================================================================


class businessApiSettingsForm(forms.ModelForm):
    """
    E-commerce API integration settings form.

    Allows businesses to configure API connections to their e-commerce
    platforms (Shopify, WooCommerce, Magento, etc.) for automatic order import.

    Fields:
        - api_type: Platform type (shopify, woocommerce, magento, etc.)
        - api_key: API key/consumer key
        - api_secret: API secret/consumer secret
        - api_access_token: Access token (Shopify)
        - api_version: API version
        - site_api_url: Store URL (with https://)
        - order_api_endpoint: Order API endpoint path
        - product_api_endpoint: Product API endpoint path
        - site_contry: Store country (default: Qatar)
        - business: Associated business (hidden field)

    Note:
        is_verify_api is excluded and set automatically after API test.

    Template:
        client/parts/business_settings_api_add.html
        client/parts/business_settings_api_update.html

    Views:
        client.views.business_settings_api_add
        client.views.business_settings_api_update
    """
    class Meta:
        model = business_models.BusinessApiSettings
        fields = '__all__'
        exclude = ['is_verify_api']

        labels = {
            "api_type": "API Type",
            "api_key": "API Key",
            "api_secret": "API Secret",
            "site_api_url": "Site URL ( with https:// )",
            "order_api_endpoint": "Order API URL",
            "product_api_endpoint": "Product API URL",
        }



# =============================================================================
# BUSINESS PROFILE FORMS
# =============================================================================


class BusinessProfileForm(forms.ModelForm):
    """
    Extended business profile information form.

    Captures detailed business information including description,
    mission, about sections, and social media links.

    Fields:
        Business Info:
            - business_description: Detailed description
            - business_mision: Mission statement
            - business_mision_detailed: Extended mission
            - business_about_part_1/2: About sections
            - business_uniqueness_title/description: Unique selling points

        Location:
            - business_address, city, state, zip_code, country
            - business_start_date: When business started

        Founders:
            - business_founters_name: Founder name
            - business_founters_bio: Founder biography

        Categories:
            - business_catagory_main: Main category
            - business_catagory_detailed: Detailed categories

        Social Media:
            - business_website, facebook_page, instagram
            - business_tiktok, youtube, twitter, linkedin, snapchat
            - business_email, phone

    Template:
        client/frontend/business_profile_update.html

    View:
        client.views.business_profile_info_update
    """
    class Meta:
        model = business_models.BusinessProfile
        fields = '__all__'
        exclude = ['business', 'updated_at', 'created_at']

    def __init__(self, *args, **kwargs):
        super(BusinessProfileForm, self).__init__(*args, **kwargs)

        self.helper = FormHelper()
        self.helper.layout = Layout(
            Field('business_description', placeholder='Tell us about your business')
        )

        # Correct field labels
        labels = {
            "business_description": "Tell us about your business",
            "business_qid": "Passport/QID/CR No",
            "business_facebook_page": "Business Facebook page : Enter username only",
            "business_instagram": "Business Instagram : Enter username only",
            "business_tiktok": "Business Tiktok : Enter username only",
            "business_youtube": "Business Youtube : Enter your complete url",
        }

        for field_name, label in labels.items():
            if field_name in self.fields:
                self.fields[field_name].label = label


class BusinessLogoForm(forms.ModelForm):
    """
    Business logo upload form.

    Handles business logo image uploads.

    Fields:
        business_logo (ImageField): Logo image file

    Template:
        client/parts/business_logo_update.html

    View:
        client.views.business_logo_update
    """
    class Meta:
        model = business_models.BusinessLogo
        fields = '__all__'
        exclude = ['business', 'updated_at', 'created_at']
            




# =============================================================================
# LOCATION FORMS
# =============================================================================


class PickupLocationsAddForm(forms.ModelForm):
    """
    Pickup/warehouse location form.

    Used to add or update business pickup locations where orders
    will be collected from.

    Fields:
        - pickup_location_title: Location name/title
        - locality: Area/locality name
        - pickup_zone_no: Zone number
        - pickup_street_no: Street number
        - pickup_building_no: Building number
        - pickup_lat: GPS latitude
        - pickup_lon: GPS longitude
        - pickup_status: active, inactive, pending, suspended

    Template:
        client/parts/pickup_location_add.html
        client/parts/pickup_location_update.html

    Views:
        client.views.pickup_location_add
        client.views.pickup_location_update
    """
    class Meta:
        model = business_models.PickupLocation
        fields = '__all__'
        exclude = ['business', 'updated_at', 'created_at']


class DriverDirectoryAddForm(forms.ModelForm):
    """
    Driver directory entry form.

    Used to add drivers to a business's contact directory.

    Fields:
        - driver: Driver to add (ForeignKey)

    Template:
        client/parts/driver_directory.html (via AJAX)

    View:
        client.views.driver_directory_add
    """
    class Meta:
        model = business_models.DriverDirectory
        fields = '__all__'
        exclude = ['business', 'updated_at', 'created_at']


# =============================================================================
# TEAM MANAGEMENT FORMS
# =============================================================================


class BusinessTeamProfileForm(forms.ModelForm):
    """
    Business team member profile form.

    Used to add or update team members who can access the business account.

    Fields:
        - user: Django User account to link
        - team_code: Unique team member code
        - team_name: Display name
        - team_phone: Contact phone
        - team_email: Contact email
        - team_role: Role in the business
        - team_bio: Brief bio
        - team_logo: Profile picture
        - team_verifed: Verification status
        - team_status: active, inactive, pending, suspended

    Template:
        client/parts/business_teams_add.html
        client/parts/business_teams_update.html

    Views:
        client.views.business_teams_add
        client.views.business_teams_update
    """
    class Meta:
        model = business_models.BusinessTeamProfile
        fields = '__all__'
        exclude = ['business', 'updated_at', 'created_at', 'profile']
        widgets = {
            'user': forms.Select(attrs={'class': 'form-control'}),
        }

        labels = {
            "team_name": "Team Name",
            "team_phone": "Team Phone No",
            "team_email": "Team Email",
            "team_role": "Team Role",
            'user': 'Search member by username',
        }