"""
Core Models Module
==================

This module contains the core user-related models for the EzzyDelivery platform.

Models:
    - Profile: Extended user profile with personal info, roles, and verification
    - ProfilePicture: User profile pictures
    - WhatsAppVerification: OTP verification codes for WhatsApp

Dependencies:
    - Django auth system (User model)
    - Used by: business, fleet, workforce, orders apps
"""

from django.conf import settings
from django.db import models


class Profile(models.Model):
    """
    Extended user profile model for EzzyDelivery platform.

    This model extends Django's built-in User model with additional fields
    for personal information, role management, and verification status.

    Attributes:
        user (OneToOneField): Link to Django's auth User model
        user_number (str): Unique identifier (format: EZZY{YEAR}{6-digits})

    User Information:
        username, first_name, last_name, email, phone, whatsapp,
        instagram, zone_name, address, nationality, date_of_birth

    Role Flags:
        is_business (bool): User is a business owner/client
        is_staff (bool): User is internal staff/workforce
        is_driver (bool): User is a delivery driver

    Verification:
        verification_status: pending, under_review, verified, rejected, incomplete
        verification_applied_at, verified_at, verified_by, rejection_reason

    Usage:
        >>> user = User.objects.get(username='john')
        >>> profile = user.profile
        >>> profile.is_business = True
        >>> profile.save()

    Related Models:
        - Business (business app): profile.business_set
        - Driver (fleet app): profile.driver
        - BusinessTeamProfile (business app): profile.businessteam
    """
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='profile')

    # Permanent User Identification Number (never changes)
    user_number = models.CharField(max_length=20, unique=True, editable=False, null=True, blank=True, db_index=True)

    # User Information (can be changed)
    username = models.CharField(max_length=255, blank=True, null=True, unique=True)
    first_name = models.CharField(max_length=255, blank=True, null=True)
    last_name = models.CharField(max_length=255, blank=True, null=True)
    email = models.EmailField(max_length=255, blank=True, null=True)
    instagram = models.CharField(max_length=255, blank=True, null=True)
    phone = models.CharField(max_length=20, blank=True, null=True)
    whatsapp = models.CharField(max_length=20, blank=True, null=True)
    zone_name = models.CharField(max_length=255, blank=True, null=True)
    address = models.CharField(max_length=255, blank=True, null=True)
    nationlity = models.CharField(max_length=255, blank=True, null=True)
    date_of_birth = models.DateField(blank=True, null=True)

    # User Roles
    is_business = models.BooleanField(default=False)
    is_staff = models.BooleanField(default=False)
    is_driver = models.BooleanField(default=False)
    is_superadmin = models.BooleanField(default=False, help_text='Super admin — can approve driver status changes and other sensitive actions')

    # Profile completion tracking
    is_profile_completed = models.BooleanField(default=False)
    is_business_profile_completed = models.BooleanField(default=False)
    is_driver_profile_completed = models.BooleanField(default=False)

    # Verification status
    VERIFICATION_STATUS_CHOICES = (
        ('pending', 'Pending Verification'),
        ('under_review', 'Under Review'),
        ('verified', 'Verified'),
        ('rejected', 'Rejected'),
        ('incomplete', 'Incomplete'),
    )
    verification_status = models.CharField(
        max_length=20,
        choices=VERIFICATION_STATUS_CHOICES,
        default='incomplete'
    )
    verification_applied_at = models.DateTimeField(blank=True, null=True)
    verified_at = models.DateTimeField(blank=True, null=True)
    verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name='verified_profiles'
    )
    rejection_reason = models.TextField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        """Override save to auto-generate user_number on creation"""
        if not self.user_number:
            # Generate user number: EZZY + Year + 6-digit number
            from django.utils import timezone as dj_timezone
            import random
            year = dj_timezone.localtime().year
            random_num = random.randint(100000, 999999)
            self.user_number = f"EZZY{year}{random_num}"

            # Ensure uniqueness
            while Profile.objects.filter(user_number=self.user_number).exists():
                random_num = random.randint(100000, 999999)
                self.user_number = f"EZZY{year}{random_num}"

        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.username or self.user_number}"

    class Meta:
        verbose_name_plural = "Profiles"

    def get_profile_completion_percentage(self):
        """Calculate profile completion percentage"""
        required_fields = [
            'username', 'first_name', 'last_name', 'email',
            'phone', 'whatsapp', 'zone_name', 'address',
            'nationlity', 'date_of_birth'
        ]
        completed = 0
        for field in required_fields:
            value = getattr(self, field)
            if not value:
                continue

            # Special validation for WhatsApp - check if it's unique
            if field == 'whatsapp':
                # Check if WhatsApp is taken by another user
                whatsapp_exists = Profile.objects.filter(
                    whatsapp=value
                ).exclude(user_id=self.user_id).exists()

                if not whatsapp_exists:
                    # WhatsApp is unique, count it as complete
                    completed += 1
                # If WhatsApp is taken, don't count it as complete
            else:
                # For other fields, just check if they're not empty
                completed += 1

        return int((completed / len(required_fields)) * 100)

    def get_business_profile_completion_percentage(self):
        """Calculate business profile completion percentage"""
        if not self.is_business:
            return 0
        try:
            from business.models import Business
            business = Business.objects.get(profile=self)
            required_fields = ['business_name', 'business_phone', 'business_whatsapp',
                             'business_email', 'business_product_category', 'business_qid']
            completed = sum(1 for field in required_fields if getattr(business, field, None))
            return int((completed / len(required_fields)) * 100)
        except Exception:
            return 0

    def get_driver_profile_completion_percentage(self):
        """Calculate driver profile completion percentage"""
        if not self.is_driver:
            return 0
        try:
            from fleet.models import Driver
            driver = Driver.objects.get(profile=self)
            required_fields = ['driver_phone', 'driver_whatsapp', 'driver_languages',
                             'driver_license_number', 'driver_bio']
            completed = sum(1 for field in required_fields if getattr(driver, field, None))
            return int((completed / len(required_fields)) * 100)
        except Exception:
            return 0

    def can_apply_for_verification(self):
        """Check if user can apply for verification"""
        if self.is_business:
            return self.is_profile_completed and self.is_business_profile_completed
        elif self.is_driver:
            return self.is_profile_completed and self.is_driver_profile_completed
        return False


def user_directory_path(instance, filename):
    """
    Generate upload path for user files.

    Args:
        instance: Model instance (ProfilePicture)
        filename: Original filename

    Returns:
        str: Path in format 'core/user/{user_id}/{filename}'
    """
    user_id = getattr(instance, 'user_id', None) or getattr(instance, 'user', {id: 'unknown'})
    return 'core/user/%s/%s' % (user_id, filename)


class ProfilePicture(models.Model):
    """
    User profile picture model.

    Stores profile images for users with automatic path generation.

    Attributes:
        user (OneToOneField): Link to User model
        profile (ForeignKey): Link to Profile model
        profile_picture (ImageField): The actual image file

    Upload Path:
        Files are stored at: media/{user_path}/{filename}
    """
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='profile_picture')
    profile = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name='profile_picture')
    profile_picture = models.ImageField(
        upload_to=user_directory_path, default='user/avatar.png', blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return str(self.id)


class WhatsAppVerification(models.Model):
    """
    WhatsApp OTP verification model.

    Stores verification codes sent via WhatsApp for various purposes
    like password reset, phone verification, and account verification.

    Attributes:
        user (ForeignKey): Optional link to User (null for new registrations)
        phone_number (str): WhatsApp number receiving the code
        verification_code (str): 6-digit OTP code
        verification_type (str): Purpose of verification
        is_verified (bool): Whether code has been successfully verified
        attempts (int): Number of verification attempts made
        max_attempts (int): Maximum allowed attempts (default: 3)
        expires_at (datetime): When the code expires

    Verification Types:
        - password_reset: For password recovery
        - phone_add: Adding a new phone number
        - phone_update: Updating existing phone number
        - account_verify: Account verification

    Methods:
        is_expired(): Check if code has expired
        can_attempt(): Check if more attempts are allowed

    Usage:
        >>> verification = WhatsAppVerification.objects.create(
        ...     phone_number='97412345678',
        ...     verification_code='123456',
        ...     verification_type='password_reset',
        ...     expires_at=timezone.now() + timedelta(minutes=10)
        ... )
    """
    VERIFICATION_TYPES = (
        ('password_reset', 'Password Reset'),
        ('phone_add', 'Phone Number Add'),
        ('phone_update', 'Phone Number Update'),
        ('account_verify', 'Account Verification'),
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='whatsapp_verifications',
        null=True,
        blank=True
    )
    phone_number = models.CharField(max_length=20)
    verification_code = models.CharField(max_length=6)
    verification_type = models.CharField(max_length=20, choices=VERIFICATION_TYPES)
    is_verified = models.BooleanField(default=False)
    attempts = models.IntegerField(default=0)
    max_attempts = models.IntegerField(default=3)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    verified_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name_plural = "WhatsApp Verifications"
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.phone_number} - {self.verification_type} - {self.verification_code}"

    def is_expired(self):
        from django.utils import timezone
        return timezone.now() > self.expires_at

    def can_attempt(self):
        return self.attempts < self.max_attempts and not self.is_expired()


class AutoTriggerConfig(models.Model):
    """Configuration for automatic triggers (WhatsApp, webhooks, system actions)."""

    CATEGORY_CHOICES = [
        ('whatsapp', 'WhatsApp Notification'),
        ('webhook', 'Webhook Event'),
        ('system', 'System Auto-Action'),
    ]

    WHATSAPP_CHANNEL_CHOICES = [
        ('', 'Default (by config)'),
        ('evolution', 'Evolution API'),
        ('waha', 'WAHA'),
    ]

    trigger_key = models.CharField(max_length=100, unique=True)
    label = models.CharField(max_length=200)
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES)
    is_enabled = models.BooleanField(default=True)
    description = models.TextField(blank=True, default='')
    action = models.CharField(max_length=255, blank=True, default='')
    # Per-trigger WhatsApp sender override. Null = use the default WhatsApp
    # instance / settings.EVOLUTION_INSTANCE. Only meaningful for whatsapp triggers.
    whatsapp_instance = models.ForeignKey(
        'core.WhatsAppInstance', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='triggers',
        help_text='WhatsApp number this trigger sends from (blank = default).'
    )
    # Per-trigger delivery channel. Blank = decide by global config.
    whatsapp_channel = models.CharField(
        max_length=20, blank=True, default='', choices=WHATSAPP_CHANNEL_CHOICES,
        help_text='Channel this trigger sends through (blank = by config).'
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['category', 'trigger_key']
        verbose_name = 'Auto Trigger Config'
        verbose_name_plural = 'Auto Trigger Configs'

    def __str__(self):
        status = 'ON' if self.is_enabled else 'OFF'
        return f"[{status}] {self.label}"

    @classmethod
    def is_trigger_enabled(cls, trigger_key):
        """Check if a trigger is enabled. Returns True if no config exists (default on)."""
        try:
            return cls.objects.get(trigger_key=trigger_key).is_enabled
        except cls.DoesNotExist:
            return True


class AutoFlow(models.Model):
    """User-defined automation flow: connects a trigger event to an action."""

    ACTION_TYPE_CHOICES = [
        ('whatsapp_message', 'Send WhatsApp Message'),
        ('webhook_call', 'Call Webhook URL'),
        ('update_order_status', 'Update Order Status'),
        ('update_task_status', 'Update Task Status'),
        ('assign_driver', 'Assign Driver'),
        ('send_notification', 'Send In-App Notification'),
        ('create_task', 'Create Delivery Task'),
    ]

    name = models.CharField(max_length=200)
    trigger = models.ForeignKey(
        AutoTriggerConfig, on_delete=models.CASCADE, related_name='flows'
    )
    action_type = models.CharField(max_length=50, choices=ACTION_TYPE_CHOICES)
    action_config = models.JSONField(
        default=dict, blank=True,
        help_text='Action parameters: message template, webhook URL, status value, etc.'
    )
    is_enabled = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Auto Flow'
        verbose_name_plural = 'Auto Flows'

    def __str__(self):
        status = 'ON' if self.is_enabled else 'OFF'
        return f"[{status}] {self.name}"


class AutoFlowLog(models.Model):
    """Execution log for an AutoFlow run."""

    STATUS_CHOICES = [
        ('success', 'Success'),
        ('failed', 'Failed'),
        ('test', 'Test'),
        ('throttled', 'Throttled'),
    ]

    flow = models.ForeignKey(AutoFlow, on_delete=models.CASCADE, related_name='logs')
    status = models.CharField(max_length=10, choices=STATUS_CHOICES)
    trigger_data = models.JSONField(default=dict, blank=True)
    result = models.TextField(blank=True, default='')
    error = models.TextField(blank=True, default='')
    executed_at = models.DateTimeField(auto_now_add=True)
    duration_ms = models.IntegerField(default=0)

    class Meta:
        ordering = ['-executed_at']
        verbose_name = 'Auto Flow Log'

    def __str__(self):
        return f"[{self.status}] {self.flow.name} @ {self.executed_at}"


class AutoFlowThrottle(models.Model):
    """Per-flow debounce/aggregation state for throttled AutoFlows.

    When a flow's ``action_config`` carries ``throttle_minutes``, the executor
    no longer sends inline. Each trigger only bumps ``pending_count`` and, on
    the first event of a batch, stamps ``pending_since``. Once
    ``throttle_minutes`` have elapsed since ``pending_since``, the
    ``flush_autoflow_digests`` management command (cron, every minute) sends a
    single message whose ``{task_count}`` is the accumulated ``pending_count``,
    then clears the batch. This trailing-edge aggregation means a burst of
    publishes collapses into one accurately-counted message.
    """

    flow = models.OneToOneField(
        AutoFlow, on_delete=models.CASCADE, related_name='throttle'
    )
    last_sent_at = models.DateTimeField(null=True, blank=True)
    pending_count = models.PositiveIntegerField(
        default=0,
        help_text='Tasks accumulated since the last digest message went out.'
    )
    pending_since = models.DateTimeField(
        null=True, blank=True,
        help_text='When the current pending batch started accumulating. '
                  'The digest sends once throttle_minutes elapse from here.'
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Auto Flow Throttle'

    def __str__(self):
        return f"{self.flow.name} — pending={self.pending_count}"


class WhatsAppInstance(models.Model):
    """WhatsApp Evolution API instance for sending messages from auto flows."""

    label = models.CharField(max_length=100, help_text="Friendly name (e.g. Main, Support, Sales)")
    instance_name = models.CharField(max_length=100, unique=True, help_text="Evolution API instance name")
    waha_session = models.CharField(max_length=100, blank=True, default='', help_text="WAHA session name for this same number (blank = default WAHA session)")
    phone_number = models.CharField(max_length=30, blank=True, default='', help_text="WhatsApp number (e.g. +974 XXXX XXXX)")
    is_default = models.BooleanField(default=False, help_text="Use as default when no instance is specified")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-is_default', 'label']
        verbose_name = 'WhatsApp Instance'
        verbose_name_plural = 'WhatsApp Instances'

    def __str__(self):
        default = ' (default)' if self.is_default else ''
        return f"{self.label} — {self.phone_number or self.instance_name}{default}"

    def save(self, *args, **kwargs):
        if self.is_default:
            WhatsAppInstance.objects.filter(is_default=True).exclude(pk=self.pk).update(is_default=False)
        super().save(*args, **kwargs)