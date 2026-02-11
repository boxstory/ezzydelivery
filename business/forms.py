"""
Business Forms Module
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
    - business.models: Business, BusinessProfile, PickupLocation, etc.
    - business.views: Views that use these forms
"""

from urllib import request
from django import forms
from django.contrib.auth.models import User

from crispy_forms.helper import FormHelper
from django.forms import ModelForm
from crispy_forms.layout import Layout, Field


from core import models as core_models
from fleet import models as fleet_models
from business import models as business_models

# Local aliases for commonly used models
Business = business_models.Business
BusinessProfile = business_models.BusinessProfile
BusinessApiSettings = business_models.BusinessApiSettings
BusinessLogo = business_models.BusinessLogo
BusinessTeamProfile = business_models.BusinessTeamProfile
PickupLocation = business_models.PickupLocation
DriverDirectory = business_models.DriverDirectory
Profile = core_models.Profile
Driver = fleet_models.Driver


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
        business/frontend/business_profile_update.html

    Views:
        - core.views.business_register (initial registration)
        - business.views.business_profile_update (updates)
    """
    class Meta:
        model = business_models.Business
        fields = [
            'business_name',
            'business_phone',
            'business_whatsapp',
            'business_email',
            'business_bio',
            'business_facebook_page',
            'business_instagram',
            'business_since',
            'business_product_category',
            'business_languages',
            'business_qid',
        ]
        # Exclude sensitive/internal fields
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
    platforms (Shopify, WooCommerce, TikTok Shop, Magento, etc.) for automatic order import.

    Fields:
        Common Fields:
            - api_type: Platform type (shopify, woocommerce, tiktokshop, etc.)
            - api_key: API key/consumer key/App Key
            - api_secret: API secret/consumer secret/App Secret
            - api_access_token: Access token
            - api_version: API version
            - site_api_url: Store URL (with https://)
            - order_api_endpoint: Order API endpoint path
            - product_api_endpoint: Product API endpoint path
            - site_contry: Store country (default: Qatar)

        TikTok Shop Specific:
            - tiktok_shop_id: Shop ID from TikTok authorization
            - tiktok_shop_cipher: Shop cipher for API requests
            - tiktok_refresh_token: Refresh token for renewing access

    Note:
        - business is set in the view, not exposed in form
        - is_verify_api is excluded and set automatically after API test
        - TikTok fields are only shown when api_type is 'tiktokshop'

    Template:
        business/parts/business_settings_api_add.html
        business/parts/business_settings_api_update.html

    Views:
        business.views.business_settings_api_add
        business.views.business_settings_api_update
    """
    class Meta:
        model = business_models.BusinessApiSettings
        fields = [
            'api_type',
            'api_key',
            'api_secret',
            'api_access_token',
            'api_version',
            'site_api_url',
            'order_api_endpoint',
            'product_api_endpoint',
            'site_contry',
            # TikTok Shop specific fields
            'tiktok_shop_id',
            'tiktok_shop_cipher',
            'tiktok_refresh_token',
        ]
        # Exclude sensitive/internal fields
        exclude = ['business', 'is_verify_api', 'tiktok_token_expires_at']

        labels = {
            "api_type": "Platform Type",
            "api_key": "API Key / App Key",
            "api_secret": "API Secret / App Secret",
            "api_access_token": "Access Token",
            "api_version": "API Version",
            "site_api_url": "Site URL (with https://)",
            "order_api_endpoint": "Order API URL",
            "product_api_endpoint": "Product API URL",
            "site_contry": "Country",
            "tiktok_shop_id": "TikTok Shop ID",
            "tiktok_shop_cipher": "TikTok Shop Cipher",
            "tiktok_refresh_token": "TikTok Refresh Token",
        }

        help_texts = {
            "api_type": "Select your e-commerce platform",
            "api_key": "For TikTok Shop: App Key from TikTok Partner Center",
            "api_secret": "For TikTok Shop: App Secret from TikTok Partner Center",
            "api_access_token": "OAuth access token (obtained after authorization)",
            "api_version": "For TikTok Shop: use 202309 or later",
            "site_api_url": "Your store URL or API endpoint base URL",
            "tiktok_shop_id": "Obtained from TikTok Shop OAuth authorization",
            "tiktok_shop_cipher": "Obtained from TikTok Shop OAuth authorization",
            "tiktok_refresh_token": "Used to refresh access token before expiry",
        }

        widgets = {
            'api_type': forms.Select(attrs={'class': 'form-select', 'id': 'api_type_select'}),
            'api_key': forms.TextInput(attrs={'class': 'form-control'}),
            'api_secret': forms.PasswordInput(attrs={'class': 'form-control', 'autocomplete': 'off'}, render_value=True),
            'api_access_token': forms.TextInput(attrs={'class': 'form-control'}),
            'api_version': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g., 202309'}),
            'site_api_url': forms.URLInput(attrs={'class': 'form-control', 'placeholder': 'https://'}),
            'order_api_endpoint': forms.TextInput(attrs={'class': 'form-control'}),
            'product_api_endpoint': forms.TextInput(attrs={'class': 'form-control'}),
            'site_contry': forms.TextInput(attrs={'class': 'form-control'}),
            'tiktok_shop_id': forms.TextInput(attrs={'class': 'form-control tiktok-field'}),
            'tiktok_shop_cipher': forms.TextInput(attrs={'class': 'form-control tiktok-field'}),
            'tiktok_refresh_token': forms.TextInput(attrs={'class': 'form-control tiktok-field'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Make TikTok-specific fields not required by default
        self.fields['tiktok_shop_id'].required = False
        self.fields['tiktok_shop_cipher'].required = False
        self.fields['tiktok_refresh_token'].required = False

    def clean(self):
        cleaned_data = super().clean()
        api_type = cleaned_data.get('api_type')

        # Validate TikTok Shop specific requirements
        if api_type == 'tiktokshop':
            api_key = cleaned_data.get('api_key')
            api_secret = cleaned_data.get('api_secret')

            if not api_key:
                self.add_error('api_key', 'App Key is required for TikTok Shop integration.')
            if not api_secret:
                self.add_error('api_secret', 'App Secret is required for TikTok Shop integration.')

        return cleaned_data



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
        business/frontend/business_profile_update.html

    View:
        business.views.business_profile_info_update
    """
    class Meta:
        model = business_models.BusinessProfile
        fields = [
            'business_description',
            'business_mision',
            'business_mision_detailed',
            'business_about_part_1',
            'business_about_part_2',
            'business_uniqueness_title',
            'business_uniqueness_description',
            'business_address',
            'business_city',
            'business_state',
            'business_zip_code',
            'business_country',
            'business_start_date',
            'business_founters_name',
            'business_founters_bio',
            'business_catagory_main',
            'business_catagory_detailed',
            'business_website',
            'business_facebook_page',
            'business_instagram',
            'business_tiktok',
            'business_youtube',
            'business_twitter',
            'business_linkedin',
            'business_snapchat',
            'business_email',
            'business_phone',
        ]
        exclude = ['business', 'updated_at', 'created_at']
        widgets = {
            'business_start_date': forms.DateInput(attrs={
                'type': 'text',
                'class': 'form-control datepicker',
                'placeholder': 'Select date'
            }),
            'business_description': forms.Textarea(attrs={
                'rows': 3,
                'class': 'form-control',
                'placeholder': 'Tell us about your business'
            }),
            'business_mision': forms.Textarea(attrs={
                'rows': 2,
                'class': 'form-control'
            }),
            'business_mision_detailed': forms.Textarea(attrs={
                'rows': 3,
                'class': 'form-control'
            }),
            'business_about_part_1': forms.Textarea(attrs={
                'rows': 3,
                'class': 'form-control'
            }),
            'business_about_part_2': forms.Textarea(attrs={
                'rows': 3,
                'class': 'form-control'
            }),
            'business_uniqueness_description': forms.Textarea(attrs={
                'rows': 3,
                'class': 'form-control'
            }),
            'business_catagory_detailed': forms.Textarea(attrs={
                'rows': 2,
                'class': 'form-control'
            }),
        }

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
            "business_start_date": "Business Start Date",
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
        business/parts/business_logo_update.html

    View:
        business.views.business_logo_update
    """
    class Meta:
        model = business_models.BusinessLogo
        fields = ['business_logo']
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
        business/parts/pickup_location_add.html
        business/parts/pickup_location_update.html

    Views:
        business.views.pickup_location_add
        business.views.pickup_location_update
    """
    class Meta:
        model = business_models.PickupLocation
        fields = [
            'pickup_location_title',
            'locality',
            'pickup_zone_no',
            'pickup_street_no',
            'pickup_building_no',
            'pickup_lat',
            'pickup_lon',
            'pickup_status',
        ]
        exclude = ['business', 'updated_at', 'created_at']


class DriverDirectoryAddForm(forms.ModelForm):
    """
    Driver directory entry form.

    Used to add drivers to a business's contact directory.

    Fields:
        - driver: Driver to add (ForeignKey)

    Template:
        business/parts/driver_directory.html (via AJAX)

    View:
        business.views.driver_directory_add
    """
    class Meta:
        model = business_models.DriverDirectory
        fields = ['driver']
        exclude = ['business', 'updated_at', 'created_at']


# =============================================================================
# TEAM MANAGEMENT FORMS
# =============================================================================


class BusinessTeamProfileForm(forms.ModelForm):
    """
    Business team member profile form.

    Used to add or update team members who can access the business account.
    The team_role field determines base permissions for the member.

    Fields:
        - user: Django User account to link
        - team_name: Display name
        - team_phone: Contact phone
        - team_email: Contact email
        - team_role: Role (manager, staff, viewer) determining base permissions
        - team_bio: Brief bio
        - team_logo: Profile picture
        - team_status: active, inactive, pending, suspended

    Roles:
        - manager: Full operational access (orders, products, customers, reports, team view)
        - staff: Create/edit orders and products, view customers
        - viewer: Read-only access

    Template:
        business/parts/business_teams_add.html
        business/parts/business_teams_update.html

    Views:
        business.views.business_teams_add
        business.views.business_teams_update
    """
    class Meta:
        model = business_models.BusinessTeamProfile
        fields = ['user', 'team_name', 'team_phone', 'team_email',
                  'team_role', 'team_bio', 'team_logo', 'team_status']
        exclude = ['business', 'profile', 'team_code', 'team_verifed',
                   'invited_by', 'invited_at', 'updated_at', 'created_at']
        widgets = {
            'user': forms.Select(attrs={'class': 'form-control'}),
            'team_name': forms.TextInput(attrs={'class': 'form-control'}),
            'team_phone': forms.TextInput(attrs={'class': 'form-control'}),
            'team_email': forms.EmailInput(attrs={'class': 'form-control'}),
            'team_role': forms.Select(attrs={'class': 'form-control'}),
            'team_bio': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'team_status': forms.Select(attrs={'class': 'form-control'}),
        }

        labels = {
            'user': 'Select User',
            'team_name': 'Display Name',
            'team_phone': 'Phone Number',
            'team_email': 'Email Address',
            'team_role': 'Role',
            'team_bio': 'Bio',
            'team_logo': 'Profile Picture',
            'team_status': 'Status',
        }

        help_texts = {
            'team_role': 'Manager: Full access. Staff: Create/edit orders & products. Viewer: Read-only.',
            'team_status': 'Only active members can access the business.',
        }


class TeamMemberAddForm(forms.ModelForm):
    """
    Simplified form for adding new team members.

    Only includes essential fields for initial team member creation.
    Additional permissions can be configured after creation.

    Fields:
        - user_identifier: Email or User ID to look up the user (not shown in list)
        - team_name: Display name
        - team_email: Contact email
        - team_role: Role (manager, staff, viewer)

    Views:
        business.views.business_teams_add
    """
    # Replace user select with text input for email/ID lookup
    user_identifier = forms.CharField(
        max_length=150,
        label='User Email or ID',
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter user email address or user ID',
            'autocomplete': 'off'
        }),
        help_text='Enter the email address or user ID of the person you want to add.'
    )

    class Meta:
        model = business_models.BusinessTeamProfile
        fields = ['team_name', 'team_email', 'team_role']
        widgets = {
            'team_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Display name'}),
            'team_email': forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'Email address'}),
            'team_role': forms.Select(attrs={'class': 'form-control'}),
        }
        labels = {
            'team_name': 'Display Name',
            'team_email': 'Email',
            'team_role': 'Role',
        }

    def __init__(self, *args, business=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.business = business
        # Reorder fields so user_identifier comes first
        field_order = ['user_identifier', 'team_name', 'team_email', 'team_role']
        self.order_fields(field_order)

    def clean_user_identifier(self):
        """Validate and look up user by email or ID."""
        identifier = self.cleaned_data.get('user_identifier', '').strip()

        if not identifier:
            raise forms.ValidationError('Please enter a user email or ID.')

        # Try to find user by email first, then by ID
        user = None

        # Check if it looks like an email
        if '@' in identifier:
            try:
                user = User.objects.get(email__iexact=identifier)
            except User.DoesNotExist:
                raise forms.ValidationError(
                    f'No user found with email "{identifier}". '
                    'Please check the email address and try again.'
                )
        else:
            # Try as user ID
            try:
                user_id = int(identifier)
                user = User.objects.get(id=user_id)
            except (ValueError, User.DoesNotExist):
                raise forms.ValidationError(
                    f'No user found with ID "{identifier}". '
                    'Please enter a valid email address or user ID.'
                )

        # Check if user is already a team member
        if self.business:
            if business_models.BusinessTeamProfile.objects.filter(
                business=self.business, user=user
            ).exists():
                raise forms.ValidationError(
                    f'User "{user.username}" is already a team member of this business.'
                )

            # Check if user is the business owner
            if self.business.user and self.business.user.id == user.id:
                raise forms.ValidationError(
                    'You cannot add the business owner as a team member.'
                )

        # Store the user object for later use in the view
        self.cleaned_user = user
        return identifier

    def get_user(self):
        """Return the validated user object."""
        return getattr(self, 'cleaned_user', None)


class TeamPermissionForm(forms.Form):
    """
    Form for managing individual team member permissions.

    Used to grant or revoke specific permissions for a team member,
    overriding their role-based defaults.

    Fields:
        - permission_code: Permission to modify
        - action: grant or revoke
    """
    from business.permissions import BusinessPermissions

    permission_code = forms.ChoiceField(
        choices=BusinessPermissions.PERMISSION_CHOICES,
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    action = forms.ChoiceField(
        choices=[
            ('grant', 'Grant Permission'),
            ('revoke', 'Revoke Permission'),
        ],
        widget=forms.RadioSelect()
    )


class ChangeRoleForm(forms.Form):
    """
    Form for changing a team member's role.

    Changing the role will affect the base permissions.
    Custom permission overrides are preserved.
    """
    role = forms.ChoiceField(
        choices=business_models.BusinessTeamProfile.ROLE_CHOICES,
        widget=forms.Select(attrs={'class': 'form-control'})
    )