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

    business_website = models.CharField(max_length=255, blank=True, null=True)
    business_facebook_page = models.CharField(
        max_length=100, blank=True, null=True)
    business_instagram = models.CharField(max_length=100, blank=True, null=True)
    business_tiktok = models.CharField(max_length=100, blank=True, null=True)
    business_since = models.DateField(blank=True, null=True)
    business_product_category = models.CharField(
        max_length=100, blank=True, null=True)
    business_languages = models.CharField(
        max_length=100,  default='english')
    business_qid = models.CharField(max_length=11, blank=True, null=True)
    status_choices = [
        ('active', 'Active'),
        ('inactive', 'Inactive'),
        ('pending', 'Approval Pending'),
        ('suspended', 'Suspended'),
    ]

    business_status = models.CharField(
        max_length=100,  choices=status_choices, default='pending')

    # Fulfillment Service - Businesses using EzzyDelivery's fulfillment/WMS service
    fulfillment_service_enabled = models.BooleanField(
        default=True,
        help_text="Enable fulfillment service (WMS integration) for this business"
    )
    FULFILLMENT_STATUS_CHOICES = [
        ('none', 'Not Requested'),
        ('not_required', 'Not Required'),
        ('requested', 'Requested'),
        ('active', 'Active'),
    ]
    fulfillment_service_status = models.CharField(
        max_length=20,
        choices=FULFILLMENT_STATUS_CHOICES,
        default='none',
        help_text="Fulfillment service status: none, not_required, requested, or active"
    )
    fulfillment_activated_at = models.DateTimeField(
        blank=True, null=True,
        help_text="When the fulfillment service was activated"
    )

    # Temp order sync — only businesses with this flag will appear in temp orders
    temp_order_enabled = models.BooleanField(
        default=False,
        help_text="Enable temp order sync for this business"
    )

    # Shared column mapping used across all import sources (OneDrive, Google Sheet, CSV, Public Link)
    # Format: {db_field: source_column_header}  e.g. {"customer_name": "Customer Name", "customer_phone": "Phone"}
    import_mapping = models.JSONField(default=dict, blank=True,
        help_text='Shared import column mapping for all sources: {db_field: source_column_header}')

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
    business_start_date = models.DateField(blank=True, null=True) 

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
        db_table = 'client_businessprofile'






class BusinessApiSettings(models.Model):
    """
    API credentials for e-commerce platform integrations.

    Supported Platforms:
        - Shopify: Uses api_key (API Key), api_secret (API Secret), api_access_token
        - WooCommerce: Uses api_key (Consumer Key), api_secret (Consumer Secret), site_api_url
        - TikTok Shop: Uses api_key (App Key), api_secret (App Secret), api_access_token,
                       tiktok_shop_id, tiktok_shop_cipher, tiktok_refresh_token
        - Others: Generic API key/secret configuration
    """
    type_choices = [
        ('shopify', 'Shopify'),
        ('woocommerce', 'WooCommerce'),
        ('tiktokshop', 'TikTok Shop'),
        ('magento', 'Magento'),
        ('opencart', 'OpenCart'),
        ('prestashop', 'PrestaShop'),
        ('bigcommerce', 'BigCommerce'),
        ('google_sheet', 'Google Sheet'),
        ('custom', 'Custom'),
    ]
    api_type = models.CharField(
        max_length=100, choices=type_choices, default='custom')
    api_access_token = models.CharField(max_length=255, blank=True, null=True,
        help_text='Access token for API authentication')
    api_key = models.CharField(max_length=100, blank=True, null=True,
        help_text='API Key / App Key / Consumer Key')
    api_secret = models.CharField(max_length=100, blank=True, null=True,
        help_text='API Secret / App Secret / Consumer Secret')
    api_version = models.CharField(max_length=100, blank=True, null=True,
        help_text='API version (e.g., 202309 for TikTok Shop)')
    site_api_url = models.CharField(max_length=255, blank=True, null=True,
        help_text='Store URL or API base URL')
    site_contry = models.CharField(max_length=100, blank=True, null=True, default='Qatar')
    order_api_endpoint = models.CharField(max_length=255, blank=True, null=True)
    product_api_endpoint = models.CharField(max_length=255, blank=True, null=True)
    google_sheet_url = models.TextField(blank=True, null=True,
        help_text='Google Sheets URL (published as CSV or shareable link)')
    google_sheet_gid = models.BigIntegerField(blank=True, null=True,
        help_text='Worksheet (tab) gid to import from. NULL = use first tab or gid in URL.')
    google_sheet_tab_name = models.CharField(max_length=255, blank=True, default='',
        help_text='Last-known title of the selected worksheet (display only).')

    # TikTok Shop specific fields
    tiktok_shop_id = models.CharField(max_length=100, blank=True, null=True,
        help_text='TikTok Shop ID (obtained after OAuth authorization)')
    tiktok_shop_cipher = models.CharField(max_length=255, blank=True, null=True,
        help_text='TikTok Shop cipher for API requests')
    tiktok_refresh_token = models.CharField(max_length=255, blank=True, null=True,
        help_text='TikTok refresh token for renewing access token')
    tiktok_token_expires_at = models.DateTimeField(blank=True, null=True,
        help_text='When the TikTok access token expires')

    column_mapping = models.JSONField(blank=True, null=True, default=None,
        help_text='Google Sheet column mapping: {"customer_name": "Col Header", "phone": "Col Header", ...}')
    last_headers = models.JSONField(blank=True, default=list,
        help_text='Last-seen header row from the source sheet, used to map raw_row positions to db fields.')

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
        db_table = 'client_businessapisettings'

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
        db_table = 'client_businesslogo'

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
        db_table = 'client_businessposter'
        ordering = ['poster_order', '-created_at']

    def __str__(self):
        return f"{self.business.business_name} - Poster {self.poster_order + 1}"


# =============================================================================
# TEAM & PERMISSION MODELS
# =============================================================================


class BusinessTeamProfile(models.Model):
    """
    Business team member profile.

    Represents a user's membership in a business team with role-based permissions.
    The business owner (Business.user) is NOT stored here - they have implicit
    full access. This model is only for additional team members.

    Roles:
        - manager: Full operational access (no settings/API management)
        - staff: Create/edit orders and products, view customers
        - viewer: Read-only access

    Attributes:
        user: The Django user account for this team member
        profile: Link to the user's Profile
        business: The business this team member belongs to
        team_role: Role determining base permissions
        team_status: active, pending, inactive, suspended

    Permission System:
        - Base permissions come from team_role (see business/permissions.py)
        - Custom overrides stored in BusinessTeamPermission
        - Use get_effective_permissions() to get final permission set
        - Use has_permission() to check specific permission
    """
    ROLE_CHOICES = [
        ('manager', 'Manager'),
        ('staff', 'Staff'),
        ('viewer', 'Viewer'),
    ]

    STATUS_CHOICES = [
        ('pending', 'Pending Approval'),
        ('active', 'Active'),
        ('inactive', 'Inactive'),
        ('suspended', 'Suspended'),
        ('rejected', 'Rejected'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='team_profile'
    )
    profile = models.ForeignKey(
        core_models.Profile,
        on_delete=models.SET_NULL,
        blank=True, null=True,
        related_name='team_profile'
    )
    business = models.ForeignKey(
        Business,
        on_delete=models.CASCADE,
        related_name='team_members'
    )

    # Basic info
    team_code = models.CharField(max_length=100, blank=True, null=True)
    team_name = models.CharField(max_length=100, blank=True, null=True)
    team_phone = models.CharField(max_length=100, blank=True, null=True)
    team_email = models.CharField(max_length=100, blank=True, null=True)
    team_bio = models.CharField(max_length=225, blank=True, null=True)
    team_logo = models.ImageField(
        upload_to='business/team_logos/',
        default="business/avatar.png",
        blank=True, null=True
    )

    # Role-based permissions
    team_role = models.CharField(
        max_length=20,
        choices=ROLE_CHOICES,
        default='staff',
        db_index=True,
        help_text="Base role determining default permissions"
    )

    # Status
    team_status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending',
        db_index=True
    )
    team_verifed = models.BooleanField(default=False)

    # Invitation tracking
    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='invited_team_members'
    )
    invited_at = models.DateTimeField(null=True, blank=True)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Team Member"
        verbose_name_plural = "Team Members"
        db_table = 'client_businessteamprofile'
        unique_together = [
            ('business', 'team_code'),
            ('business', 'user'),
        ]
        indexes = [
            models.Index(fields=['business', 'team_status']),
            models.Index(fields=['user', 'team_status']),
        ]

    def __str__(self):
        return f"{self.team_name or self.user.username} ({self.team_role}) - {self.business.business_name}"

    def get_effective_permissions(self):
        """
        Get all effective permissions for this team member.

        Combines role-based permissions with custom overrides:
        - Start with role default permissions
        - Add explicitly granted permissions
        - Remove explicitly revoked permissions

        Returns:
            set: Set of permission code strings
        """
        from business.permissions import get_role_permissions

        # Start with role permissions
        permissions = set(get_role_permissions(self.team_role))

        # Apply custom overrides
        for custom_perm in self.custom_permissions.all():
            if custom_perm.is_granted:
                permissions.add(custom_perm.permission_code)
            else:
                permissions.discard(custom_perm.permission_code)

        return permissions

    def has_permission(self, permission_code):
        """
        Check if team member has a specific permission.

        Args:
            permission_code: Permission code string from BusinessPermissions

        Returns:
            bool: True if team member has the permission and is active
        """
        if self.team_status != 'active':
            return False
        return permission_code in self.get_effective_permissions()

    def has_any_permission(self, permission_codes):
        """
        Check if team member has any of the given permissions.

        Args:
            permission_codes: List of permission code strings

        Returns:
            bool: True if team member has at least one permission
        """
        if self.team_status != 'active':
            return False
        effective = self.get_effective_permissions()
        return bool(set(permission_codes) & effective)

    def has_all_permissions(self, permission_codes):
        """
        Check if team member has all of the given permissions.

        Args:
            permission_codes: List of permission code strings

        Returns:
            bool: True if team member has all permissions
        """
        if self.team_status != 'active':
            return False
        effective = self.get_effective_permissions()
        return set(permission_codes).issubset(effective)

    def grant_permission(self, permission_code, granted_by=None):
        """
        Explicitly grant a permission beyond role defaults.

        Args:
            permission_code: Permission code to grant
            granted_by: User granting the permission

        Returns:
            BusinessTeamPermission: The created/updated permission record
        """
        perm, created = BusinessTeamPermission.objects.update_or_create(
            team_member=self,
            permission_code=permission_code,
            defaults={
                'is_granted': True,
                'granted_by': granted_by
            }
        )
        return perm

    def revoke_permission(self, permission_code, revoked_by=None):
        """
        Explicitly revoke a permission from role defaults.

        Args:
            permission_code: Permission code to revoke
            revoked_by: User revoking the permission

        Returns:
            BusinessTeamPermission: The created/updated permission record
        """
        perm, created = BusinessTeamPermission.objects.update_or_create(
            team_member=self,
            permission_code=permission_code,
            defaults={
                'is_granted': False,
                'granted_by': revoked_by
            }
        )
        return perm

    def reset_to_role_defaults(self):
        """Remove all custom permission overrides, resetting to role defaults."""
        self.custom_permissions.all().delete()


class BusinessTeamPermission(models.Model):
    """
    Custom permission overrides for team members.

    Allows granting or revoking specific permissions beyond what
    the team member's role provides by default.

    Attributes:
        team_member: The team member this permission applies to
        permission_code: Permission code from BusinessPermissions
        is_granted: True = explicitly granted, False = explicitly revoked
        granted_by: User who made this change
        granted_at: When this change was made
    """
    team_member = models.ForeignKey(
        BusinessTeamProfile,
        on_delete=models.CASCADE,
        related_name='custom_permissions'
    )
    permission_code = models.CharField(
        max_length=50,
        db_index=True,
        help_text="Permission code from BusinessPermissions"
    )
    is_granted = models.BooleanField(
        default=True,
        help_text="True = explicitly granted, False = explicitly revoked"
    )
    granted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='granted_team_permissions'
    )
    granted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Team Permission"
        verbose_name_plural = "Team Permissions"
        db_table = 'business_team_permission'
        unique_together = ('team_member', 'permission_code')

    def __str__(self):
        status = "granted" if self.is_granted else "revoked"
        return f"{self.team_member.team_name} - {self.permission_code} ({status})"


class BusinessTeamJoinRequest(models.Model):
    """
    A request from a user to join a business as a team member.

    Users submit this from the /join_us/team/ page by searching for
    a business. The business owner reviews pending requests and can
    accept (creating a BusinessTeamProfile) or reject them.
    """
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('accepted', 'Accepted'),
        ('rejected', 'Rejected'),
        ('cancelled', 'Cancelled'),
    ]
    business = models.ForeignKey(
        Business, on_delete=models.CASCADE, related_name='join_requests'
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='team_join_requests'
    )
    desired_role_title = models.CharField(
        max_length=100, blank=True,
        help_text="Desired position/role title as entered by the user (e.g. 'Sales Manager')"
    )
    message = models.TextField(blank=True, help_text="Optional message to the business owner")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending', db_index=True)
    requested_at = models.DateTimeField(auto_now_add=True)
    responded_at = models.DateTimeField(null=True, blank=True)
    responded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='responded_join_requests'
    )

    class Meta:
        verbose_name = "Team Join Request"
        verbose_name_plural = "Team Join Requests"
        db_table = 'client_businessteamjoinrequest'
        unique_together = [('business', 'user')]
        indexes = [
            models.Index(fields=['business', 'status']),
            models.Index(fields=['user', 'status']),
        ]

    def __str__(self):
        return f"{self.user.username} → {self.business.business_name} ({self.status})"


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
    status_choices = [
        ('active', 'Active'),
        ('inactive', 'Inactive'),
        ('pending', 'Approval Pending'),
        ('suspended', 'Suspended'),
    ]
    pickup_status = models.CharField(
        max_length=100, choices=status_choices, default='active')
    is_fulfilment_center = models.BooleanField(default=False)
    is_default = models.BooleanField(
        default=False,
        help_text="Pre-selected as pickup location when creating new orders"
    )
    warehouse = models.ForeignKey(
        'warehouse.Warehouse', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='linked_pickup_locations',
        help_text="Linked warehouse (auto-set when business is connected to a warehouse)"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.pickup_location_title

    class Meta:
        verbose_name_plural = "Pickup Location"
        db_table = 'client_pickuplocation'


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
        db_table = 'client_driverdirectory'


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

    class Meta:
        verbose_name_plural = "Business Social Info"
        db_table = 'client_businesssocialinfo'


class BrandedTrackingConfig(models.Model):
    """
    Configuration for the branded customer tracking page.

    Each business can customize their public tracking page with brand colors,
    display options (driver name, phone, ETA), and a custom footer message.
    Customers access this page via a WhatsApp link to track their delivery.
    """
    business = models.OneToOneField(
        Business, on_delete=models.CASCADE, related_name='tracking_config'
    )
    primary_color = models.CharField(
        max_length=7, default='#f7c000',
        help_text="Hex color for header/buttons"
    )
    secondary_color = models.CharField(
        max_length=7, default='#001f3f',
        help_text="Hex color for text/accents"
    )
    show_driver_name = models.BooleanField(default=True)
    show_driver_phone = models.BooleanField(default=False)
    show_eta = models.BooleanField(default=True)
    custom_footer_text = models.CharField(max_length=255, blank=True, default='')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'business_branded_tracking_config'

    def __str__(self):
        return f"Tracking config for {self.business}"


class WhatsAppNotificationTrigger(models.Model):
    """Per-business configuration for auto WhatsApp notifications on status changes."""
    TRIGGER_STATUS_CHOICES = [
        ('assigned', 'Driver Assigned'),
        ('picked_up', 'Picked Up'),
        ('start_ride', 'Start Ride'),
        ('out_for_delivery', 'Out for Delivery'),
        ('delivered', 'Delivered'),
        ('failed', 'Failed'),
    ]
    business = models.ForeignKey('Business', on_delete=models.CASCADE, related_name='whatsapp_triggers')
    trigger_status = models.CharField(max_length=30, choices=TRIGGER_STATUS_CHOICES)
    is_active = models.BooleanField(default=True)
    custom_message = models.TextField(blank=True, default='', help_text="Custom message template. Use {customer_name}, {order_number}, {driver_name}, {driver_phone}.")
    notification_phone = models.CharField(max_length=30, blank=True, default='', help_text="Additional phone number (with country code, e.g. 97455512345) that should also receive this notification. Leave blank to notify customer only.")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('business', 'trigger_status')
        db_table = 'business_whatsapp_trigger'

    def __str__(self):
        return f"{self.business} - {self.trigger_status} ({'active' if self.is_active else 'inactive'})"
