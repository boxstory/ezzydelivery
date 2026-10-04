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

import re

import requests
from urllib import request
from django import forms
from django.contrib.auth.models import User

from crispy_forms.helper import FormHelper
from django.forms import ModelForm
from crispy_forms.layout import Layout, Field


from core import models as core_models
from fleet import models as fleet_models
from business import models as business_models
from business.permissions import BusinessPermissions, ROLE_PERMISSIONS
from core.forms_base import SanitizedForm, SanitizedFormMixin, SanitizedModelForm
from core.net_guard import validate_public_url


def resolve_shopify_store_url(url):
    """Resolve a Shopify store URL to its canonical .myshopify.com form.

    Returns (normalised_url, error_message); exactly one is None.

    Both the Admin API and the OAuth token endpoint only answer on the permanent
    handle. A custom domain answers the token POST with a 301 to
    admin.shopify.com, requests replays it as GET, drops the body, and the login
    page it lands on returns HTTP 200 -- so raise_for_status() passes and the
    merchant sees only a JSON parse error after approving the app. Catch it here
    at save time instead.
    """
    # Lowercase before stripping the scheme: a pasted "HTTPS://Store.MyShopify.com"
    # would otherwise keep its scheme and be read as the host "https:".
    host = re.sub(r'^https?://', '', (url or '').strip().lower()).strip('/')
    host = host.split('/')[0].split('?')[0]
    if not host:
        return '', None
    if host.endswith('.myshopify.com'):
        return f'https://{host}', None

    # A custom domain publishes the handle in its storefront HTML as
    # Shopify.shop, so read it rather than making the merchant hunt for it.
    try:
        resp = requests.get(f'https://{host}/', timeout=6)
        match = re.search(r'Shopify\.shop\s*=\s*"([^"]+\.myshopify\.com)"', resp.text)
        if match:
            return f'https://{match.group(1).lower()}', None
    except requests.exceptions.RequestException:
        pass

    return None, (
        'Use your permanent .myshopify.com store address here, not a custom '
        'domain. Find it in Shopify admin → Settings → Domains, shown as '
        '"myshopify.com URL" (for example mystore.myshopify.com). The Shopify API '
        'only answers on that address.'
    )


def check_shopify_oauth_app(store_url, client_id):
    """Ask Shopify whether this Client ID is really an OAuth app.

    Returns an error message, or None when the ID is usable.

    Catches the mistake that cost a real client two failed attempts: pasting the
    API key of a Custom App created under Shopify admin -> Apps -> Develop apps.
    Those keys are 32 hex characters and look exactly like a Client ID, but they
    are not OAuth applications, so Shopify answers the authorize redirect with an
    unexplained "Oops, something went wrong" page the merchant cannot act on.

    We send a deliberately invalid authorization code: Shopify validates the
    application before the code, so 'application_cannot_be_found' identifies a
    bad Client ID while the expected 'invalid_request' means the app exists. The
    Client SECRET cannot be checked this way -- Shopify rejects the bad code
    before it ever looks at the secret -- which is why the secret is checked by
    shape instead.
    """
    host = re.sub(r'^https?://', '', (store_url or '').strip().lower()).strip('/')
    host = host.split('/')[0]
    if not host or not client_id:
        return None

    try:
        resp = requests.post(
            f'https://{host}/admin/oauth/access_token',
            json={'client_id': client_id, 'client_secret': 'preflight',
                  'code': 'preflight'},
            timeout=8, allow_redirects=False,
        )
    except requests.exceptions.RequestException:
        # Fail open. A slow resolver or a blip must not stop a merchant saving
        # perfectly good credentials; the OAuth flow itself still reports errors.
        return None

    if 'application_cannot_be_found' not in (resp.text or ''):
        return None

    return (
        'Shopify does not recognise this Client ID, so the authorization step '
        'cannot start. The usual cause is pasting the API key of a Custom App '
        '(Shopify admin → Settings → Apps and sales channels → Develop apps). '
        'A Custom App cannot use OAuth: either switch the setup method above to '
        '"Custom App" and paste its Admin API access token (shpat_…) instead, or '
        'create an app in the Shopify Dev/Partner Dashboard and copy its Client '
        'ID from there.'
    )

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
    ('english', 'English'),
    ('arabic', 'Arabic'),
    ('hindi', 'Hindi / Indian'),
    ('philipine', 'Filipino'),
    ('french', 'French'),
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


class businessRegisterForm(SanitizedModelForm):
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
    business_languages = forms.ChoiceField(
        choices=business_LANGUAGE_CHOICES,
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    business_since = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'type': 'month', 'class': 'form-control'}),
    )

    class Meta:
        model = business_models.Business
        fields = [
            'business_name',
            'business_phone',
            'business_whatsapp',
            'business_email',
            'business_bio',
            'business_website',
            'business_facebook_page',
            'business_instagram',
            'business_tiktok',
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
            'business_product_category': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g., Cosmetics, Clothing, Food'}),
            'business_phone': forms.TextInput(attrs={'class': 'form-control'}),
            'business_whatsapp': forms.TextInput(attrs={'class': 'form-control'}),
            'business_email': forms.EmailInput(attrs={'class': 'form-control'}),
            'business_bio': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'business_qid': forms.TextInput(attrs={'class': 'form-control'}),
            'business_website': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'https://yourstore.com'}),
            'business_facebook_page': forms.TextInput(attrs={'class': 'form-control'}),
            'business_instagram': forms.TextInput(attrs={'class': 'form-control'}),
            'business_tiktok': forms.TextInput(attrs={'class': 'form-control'}),
            'business_languages': forms.Select(
                choices=business_LANGUAGE_CHOICES,
                attrs={'class': 'form-select'}),
            'business_status': forms.Select(
                choices=business_STATUS_CHOICES),
            'business_since': forms.TextInput(attrs={'type': 'month', 'class': 'form-control'}),  # overridden by class-level CharField above
        }
        labels = {
            "business_name": "business Name",
            "business_phone": "business Phone No",
            "business_whatsapp": "business Whatsapp No",
            "business_qid": "Passport/QID/CR No",

        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.business_since:
            self.initial['business_since'] = self.instance.business_since.strftime('%Y-%m')

    def clean_business_since(self):
        from datetime import date
        value = self.data.get('business_since') or self.cleaned_data.get('business_since')
        if not value:
            return None
        if hasattr(value, 'year'):
            return date(value.year, value.month, 1)
        try:
            year, month = str(value).split('-')
            return date(int(year), int(month), 1)
        except (ValueError, AttributeError):
            raise forms.ValidationError("Please select a valid month and year.")

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


class businessApiSettingsForm(SanitizedModelForm):
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
        - shopify_setup_mode is a non-model field: it only drives which Shopify
          credential fields the form shows and whether saving hands off to OAuth

    Template:
        business/parts/business_settings_api_add.html
        business/parts/business_settings_api_update.html

    Views:
        business.views.business_settings_api_add
        business.views.business_settings_api_update
    """

    SHOPIFY_SETUP_MODE_CHOICES = [
        ('oauth', 'Connect with OAuth — recommended, we fetch the token for you'),
        ('custom_app', 'Custom App — I already have an Admin API access token'),
    ]

    shopify_setup_mode = forms.ChoiceField(
        label='Shopify setup method',
        required=False,
        initial='oauth',
        choices=SHOPIFY_SETUP_MODE_CHOICES,
        widget=forms.RadioSelect(attrs={'class': 'shopify-setup-mode'}),
        help_text='OAuth needs Client ID + Client Secret. Custom App needs only the Access Token.',
    )

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
            'import_qatar_only',
            # Custom REST pull — we fetch orders from the seller's own site
            'fetch_orders_url',
            'fetch_auth_style',
            'fetch_auth_name',
            'fetch_api_key',
            'fetch_list_path',
            'fetch_status_path',
            'fetch_status_include',
            'fetch_enabled',
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
            "import_qatar_only": "Import Qatar orders only",
            "fetch_orders_url": "Order Fetch URL (we call this)",
            "fetch_auth_style": "How to send your API key",
            "fetch_auth_name": "Header / parameter name",
            "fetch_api_key": "Your site's API key",
            "fetch_list_path": "Order list path",
            "fetch_status_path": "Status field",
            "fetch_status_include": "Only fetch these statuses",
            "fetch_enabled": "Pull orders automatically every hour",
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
            "fetch_orders_url": "The full URL on YOUR site that returns pending orders as JSON, "
                                "e.g. https://yourshop.com/api/orders. Leave empty if your site "
                                "pushes orders to us instead.",
            "fetch_auth_style": "Bearer suits most APIs. Pick 'Custom header' for X-API-Key, "
                                "'Query parameter' for ?api_key=...",
            "fetch_auth_name": "Only for 'Custom header' or 'Query parameter' — e.g. X-API-Key or api_key.",
            "fetch_api_key": "The key YOUR site expects from us. This is not the EzzyDelivery key "
                             "on the previous page.",
            "fetch_list_path": "Where the order array sits in your response, e.g. data.orders. "
                               "Leave empty if the response is the array itself.",
            "fetch_status_path": "Where each order's status sits, e.g. status. Leave empty to use 'status'.",
            "fetch_status_include": "Comma-separated, e.g. accepted. Orders in any other status "
                                    "are ignored — this is what stops us booking a delivery for an "
                                    "order you already delivered or cancelled. Empty takes every order.",
            "fetch_enabled": "When off, the connection can still be tested and pulled by hand.",
            "import_qatar_only": "Tick this if your store sells outside Qatar. Orders shipping "
                                 "anywhere else are then left out of the import lists, so you are "
                                 "never offered a delivery we cannot make. Off means every order "
                                 "is listed, whatever its destination.",
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
            # Plain checkbox, not a Bootstrap switch: .business-dashboard pins
            # input[type=checkbox] to 1rem with !important, so a switch renders
            # as an unstyled box on every client page.
            'import_qatar_only': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'fetch_orders_url': forms.URLInput(attrs={
                'class': 'form-control', 'placeholder': 'https://yourshop.com/api/orders'}),
            'fetch_auth_style': forms.Select(attrs={'class': 'form-select', 'id': 'fetch_auth_style_select'}),
            'fetch_auth_name': forms.TextInput(attrs={
                'class': 'form-control', 'placeholder': 'X-API-Key'}),
            'fetch_api_key': forms.PasswordInput(attrs={
                'class': 'form-control', 'autocomplete': 'off'}, render_value=True),
            'fetch_list_path': forms.TextInput(attrs={
                'class': 'form-control', 'placeholder': 'data.orders'}),
            'fetch_status_path': forms.TextInput(attrs={
                'class': 'form-control', 'placeholder': 'status'}),
            'fetch_status_include': forms.TextInput(attrs={
                'class': 'form-control', 'placeholder': 'accepted'}),
            'fetch_enabled': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
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

        # The pull is opt-in on top of a push integration: every one of these may
        # stay empty and the row still works as an inbound endpoint.
        for name in ('fetch_orders_url', 'fetch_auth_style', 'fetch_auth_name',
                     'fetch_api_key', 'fetch_list_path', 'fetch_status_path',
                     'fetch_status_include', 'fetch_enabled'):
            self.fields[name].required = False

        # Open an existing Shopify integration in the mode it was actually set up
        # in: a pasted token with no Client ID can only have come from a custom app.
        instance = getattr(self, 'instance', None)
        if instance is not None and instance.pk and instance.api_type == 'shopify':
            if instance.api_access_token and not instance.api_key:
                self.fields['shopify_setup_mode'].initial = 'custom_app'

    def clean_site_api_url(self):
        """Reject a store URL that points back inside our own network.

        The server fetches this URL itself during API test and order import, so
        an unchecked value is a server-side request forgery lever: a merchant
        could aim it at 127.0.0.1, a private subnet, or the cloud metadata
        endpoint and read the response back through the API test result page.
        """
        url = (self.cleaned_data.get('site_api_url') or '').strip()
        if not url:
            return url

        # validate_public_url resolves DNS, and socket.getaddrinfo has no timeout.
        # Running it on every submit blocks a gunicorn worker whenever the resolver
        # is slow, and a transient resolver failure would stop the merchant saving
        # any other field on this form. Only pay that cost when the URL changed.
        if self.instance and self.instance.pk and 'site_api_url' not in self.changed_data:
            return url

        # Merchants routinely paste a bare hostname; assume https rather than
        # failing them on a missing scheme.
        if '://' not in url:
            url = 'https://' + url

        ok, reason = validate_public_url(url)
        if not ok:
            raise forms.ValidationError(f'Store URL is not reachable as a public address: {reason}')
        return url

    def clean_fetch_orders_url(self):
        """Same SSRF reasoning as clean_site_api_url, and it matters more here.

        This URL is called on a schedule with a credential attached, so an
        unchecked value is a standing server-side request forgery lever rather
        than a one-off during a manual test.
        """
        url = (self.cleaned_data.get('fetch_orders_url') or '').strip()
        if not url:
            return url

        if self.instance and self.instance.pk and 'fetch_orders_url' not in self.changed_data:
            return url

        if '://' not in url:
            url = 'https://' + url

        ok, reason = validate_public_url(url)
        if not ok:
            raise forms.ValidationError(f'Fetch URL is not reachable as a public address: {reason}')
        return url

    def clean(self):
        cleaned_data = super().clean()
        api_type = cleaned_data.get('api_type')

        # A pull is only half-configured until the key can actually be sent. Catch
        # it here rather than as a 401 from the seller's own server an hour later.
        fetch_url = (cleaned_data.get('fetch_orders_url') or '').strip()
        if fetch_url:
            style = cleaned_data.get('fetch_auth_style') or 'bearer'
            if style in ('header', 'query') and not (cleaned_data.get('fetch_auth_name') or '').strip():
                self.add_error(
                    'fetch_auth_name',
                    'Give the header or parameter name your API expects the key in '
                    '(for example X-API-Key).',
                )
            if style != 'none' and not (cleaned_data.get('fetch_api_key') or '').strip():
                self.add_error(
                    'fetch_api_key',
                    'Enter the API key your own site expects from us, or set '
                    'authentication to "No authentication".',
                )
        elif cleaned_data.get('fetch_enabled'):
            self.add_error(
                'fetch_enabled',
                'There is no fetch URL to pull from. Add one, or leave automatic pulling off.',
            )

        # Shopify: enforce the credentials the chosen setup path actually needs,
        # so a half-filled form fails here instead of as a 401 from Shopify later.
        if api_type == 'shopify':
            # Normalise the store URL to the .myshopify.com handle. Only on a
            # change, so an unrelated edit never pays for the storefront fetch.
            store_url = cleaned_data.get('site_api_url')
            if store_url and (not self.instance.pk or 'site_api_url' in self.changed_data):
                resolved, url_error = resolve_shopify_store_url(store_url)
                if url_error:
                    self.add_error('site_api_url', url_error)
                elif resolved:
                    cleaned_data['site_api_url'] = resolved

            mode = cleaned_data.get('shopify_setup_mode') or 'oauth'
            if mode == 'custom_app':
                if not cleaned_data.get('api_access_token'):
                    self.add_error(
                        'api_access_token',
                        'Access Token is required for a Shopify Custom App. '
                        'It starts with "shpat_".',
                    )
            else:
                client_id = (cleaned_data.get('api_key') or '').strip()
                client_secret = (cleaned_data.get('api_secret') or '').strip()
                if not client_id:
                    self.add_error('api_key', 'Client ID is required to connect Shopify via OAuth.')
                if not client_secret:
                    self.add_error('api_secret', 'Client Secret is required to connect Shopify via OAuth.')
                if not cleaned_data.get('site_api_url'):
                    self.add_error('site_api_url', 'Store URL is required to connect Shopify via OAuth.')

                # The secret cannot be verified against Shopify (it rejects the
                # probe's code before reading the secret), so check its shape. A
                # real client pasted the Client ID into both boxes and the flow
                # only failed later, at HMAC verification, with no clue why.
                if client_id and client_secret:
                    if client_secret == client_id:
                        self.add_error(
                            'api_secret',
                            'This is the same value as the Client ID. The Client Secret '
                            'is a separate value shown underneath it in Shopify, and it '
                            'starts with "shpss_".',
                        )
                    elif re.fullmatch(r'[0-9a-f]{32}', client_secret.lower()):
                        self.add_error(
                            'api_secret',
                            'That looks like an API key, not a Client Secret. The Client '
                            'Secret starts with "shpss_" — copy the "Client secret" field '
                            'in Shopify, not the Client ID.',
                        )

                # Ask Shopify whether the Client ID is an OAuth app at all, so a
                # Custom App key is refused here instead of sending the merchant
                # to an unexplained Shopify error page. Only when it changed.
                store_for_check = cleaned_data.get('site_api_url')
                creds_changed = (not self.instance.pk
                                 or 'api_key' in self.changed_data
                                 or 'site_api_url' in self.changed_data)
                if client_id and store_for_check and creds_changed and not self.errors:
                    app_error = check_shopify_oauth_app(store_for_check, client_id)
                    if app_error:
                        self.add_error('api_key', app_error)

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


class BusinessProfileForm(SanitizedModelForm):
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


class BusinessLogoForm(SanitizedModelForm):
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


class PickupLocationsAddForm(SanitizedModelForm):
    """
    Pickup/warehouse location form.

    Used to add or update business pickup locations where orders
    will be collected from.

    Fields:
        - pickup_location_title: Location name/title
        - locality: Area/locality name
        - pickup_zone_no: Zone number
        - pickup_street_no: Street number
        - pickup_building_no: Building number (required on this form — the
          model still allows blank for legacy rows, but a driver cannot find
          a pickup point without it, so new/edited stores must supply one)
        - pickup_lat: GPS latitude (filled by QNAS lookup or a pasted map pin)
        - pickup_lon: GPS longitude (filled by QNAS lookup or a pasted map pin)
        - pickup_status: active, inactive, pending, suspended

    The templates render each field individually (no crispy blob) so the
    QNAS "Verify & Fill Coordinates" button and the WhatsApp/Google Maps
    paste box can sit between the building number and the lat/lon fields.

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
            'is_fulfilment_center',
            'is_default',
        ]
        exclude = ['business', 'updated_at', 'created_at']
        widgets = {
            'pickup_location_title': forms.TextInput(attrs={
                'class': 'form-control', 'placeholder': 'e.g. Main Warehouse — Salwa Road'}),
            'locality': forms.TextInput(attrs={
                'class': 'form-control', 'placeholder': 'e.g. Al Sadd'}),
            'pickup_zone_no': forms.NumberInput(attrs={
                'class': 'form-control', 'placeholder': '0', 'min': 0}),
            'pickup_street_no': forms.NumberInput(attrs={
                'class': 'form-control', 'placeholder': '0', 'min': 0}),
            'pickup_building_no': forms.NumberInput(attrs={
                'class': 'form-control', 'placeholder': '0', 'min': 0}),
            'pickup_lat': forms.TextInput(attrs={
                'class': 'form-control', 'placeholder': '25.286106'}),
            'pickup_lon': forms.TextInput(attrs={
                'class': 'form-control', 'placeholder': '51.534817'}),
            'pickup_status': forms.Select(attrs={'class': 'form-select'}),
            'is_fulfilment_center': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'is_default': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
        labels = {
            'pickup_location_title': 'Store Name',
            'locality': 'Locality / Area',
            'pickup_zone_no': 'Zone',
            'pickup_street_no': 'Street',
            'pickup_building_no': 'Building',
            'pickup_lat': 'Latitude',
            'pickup_lon': 'Longitude',
            'pickup_status': 'Status',
            'is_fulfilment_center': 'This store is a fulfilment center',
            'is_default': 'Use as default pickup location',
        }
        help_texts = {
            'pickup_building_no': 'Required — drivers use the building number to '
                                  'find your door, and QNAS needs it to return an '
                                  'exact pin instead of a street-level guess.',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # The model keeps building optional for legacy rows, but every store
        # saved through this form must carry one.
        self.fields['pickup_building_no'].required = True
        self.fields['pickup_building_no'].error_messages['required'] = (
            'Building number is required — a driver cannot locate the pickup '
            'point without it.'
        )


class DriverDirectoryAddForm(SanitizedModelForm):
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


class BusinessTeamProfileForm(SanitizedModelForm):
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


def resolve_user_identifier(identifier):
    """
    Resolve a free-text identifier to a User.

    Accepts an email, username, mobile number, EZZY ID, or numeric user ID.
    Returns a tuple ``(user, error_message)`` — exactly one is non-None.
    Shared by the add-member form validation and the live lookup endpoint.
    """
    identifier = (identifier or '').strip()
    if not identifier:
        return None, 'Please enter a user email, username, mobile, or ID.'

    if '@' in identifier:
        user = User.objects.filter(email__iexact=identifier).first()
        if user is None:
            return None, f'No user found with email "{identifier}".'
        return user, None

    if identifier.upper().startswith('EZZY'):
        profile = core_models.Profile.objects.select_related('user').filter(
            user_number__iexact=identifier
        ).first()
        if profile is None:
            return None, f'No user found with EZZY ID "{identifier.upper()}".'
        return profile.user, None

    # Username first, then mobile number, then numeric user ID.
    user = User.objects.filter(username__iexact=identifier).first()

    # Mobile number lookup (matches Profile.phone or Profile.whatsapp). Numbers
    # are stored inconsistently (with/without country code), so match on the
    # cleaned digits and the local 8-digit part.
    digits = ''.join(ch for ch in identifier if ch.isdigit())
    if user is None and len(digits) >= 7:
        from django.db.models import Q
        candidates = {digits, digits[-8:]}  # full + Qatar local part
        phone_q = Q()
        for cand in candidates:
            phone_q |= Q(phone__icontains=cand) | Q(whatsapp__icontains=cand)
        profile = core_models.Profile.objects.select_related('user').filter(phone_q).first()
        if profile is not None:
            user = profile.user

    if user is None:
        try:
            user = User.objects.get(id=int(identifier))
        except (ValueError, User.DoesNotExist):
            return None, (
                f'No user found with "{identifier}". Enter a valid email, '
                'username, mobile number, EZZY ID, or numeric user ID.'
            )

    return user, None


class TeamMemberAddForm(SanitizedModelForm):
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
    # Replace user select with text input for email/ID/EZZY code lookup
    user_identifier = forms.CharField(
        max_length=150,
        label='User Email, Username, Mobile, EZZY ID, or User ID',
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'e.g. user@email.com, username, 33XXXXXX, or EZZY2026XXXXXX',
            'autocomplete': 'off'
        }),
        help_text='Enter the email address, username, mobile number, EZZY ID (e.g. EZZY2026XXXXXX), or numeric user ID.'
    )

    permissions = forms.MultipleChoiceField(
        required=False,
        choices=BusinessPermissions.PERMISSION_CHOICES,
        widget=forms.CheckboxSelectMultiple(attrs={'class': 'form-check-input'}),
        label='Permissions',
        help_text='Select permissions for this team member. Leave empty to use role defaults.',
    )

    accept_terms = forms.BooleanField(
        required=True,
        label='I agree to the terms and conditions',
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        error_messages={'required': 'You must accept the terms and conditions to add a team member.'},
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
        # Reorder fields so user_identifier comes first, permissions and terms last
        field_order = ['user_identifier', 'team_name', 'team_email', 'team_role', 'permissions', 'accept_terms']
        self.order_fields(field_order)

    def clean_user_identifier(self):
        """Validate and look up user by email, username, mobile, EZZY ID, or ID."""
        identifier = self.cleaned_data.get('user_identifier', '').strip()

        if not identifier:
            raise forms.ValidationError('Please enter a user email or ID.')

        user, error = resolve_user_identifier(identifier)
        if error:
            raise forms.ValidationError(error)

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

        # Check if user has a fully completed profile (100%)
        try:
            profile = user.profile
            completion = profile.get_profile_completion_percentage()
            if completion < 100:
                field_labels = {
                    'username': 'Username', 'first_name': 'First Name',
                    'last_name': 'Last Name', 'email': 'Email',
                    'phone': 'Phone', 'whatsapp': 'WhatsApp',
                    'zone_name': 'Zone/Area', 'address': 'Address',
                    'nationlity': 'Nationality', 'date_of_birth': 'Date of Birth',
                }
                missing = [label for field, label in field_labels.items() if not getattr(profile, field, None)]
                msg = (
                    f'User "{user.username}" profile is {completion}% complete. '
                    f'100% is required to be added as a team member.'
                )
                if missing:
                    msg += f' Missing: {", ".join(missing)}.'
                raise forms.ValidationError(msg)
            # Auto-fix: mark profile as completed if 100% but flag was not set
            if not profile.is_profile_completed:
                profile.is_profile_completed = True
                profile.save(update_fields=['is_profile_completed'])
        except core_models.Profile.DoesNotExist:
            raise forms.ValidationError(
                f'User "{user.username}" does not have a profile. '
                'They must sign up and complete their profile at ezzydelivery.qa first.'
            )

        # Store the user object for later use in the view
        self.cleaned_user = user
        return identifier

    def get_user(self):
        """Return the validated user object."""
        return getattr(self, 'cleaned_user', None)


class TeamPermissionForm(SanitizedForm):
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


class ChangeRoleForm(SanitizedForm):
    """
    Form for changing a team member's role.

    Changing the role will affect the base permissions.
    Custom permission overrides are preserved.
    """
    role = forms.ChoiceField(
        choices=business_models.BusinessTeamProfile.ROLE_CHOICES,
        widget=forms.Select(attrs={'class': 'form-control'})
    )