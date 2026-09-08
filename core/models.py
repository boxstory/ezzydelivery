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

from core import signup_origin
from core.email_normalize import EmailNormalizedModel
from core.validators import image_validators


class Profile(EmailNormalizedModel, models.Model):
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

    Signup Origin:
        signup_source: driver_join, business_join, team_join, pricing_inquiry,
                       website, direct_login, unknown
        signup_landing_path, signup_referrer, signup_utm, signup_source_inferred

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
    EMAIL_FIELDS = ('email',)

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

    # Staff departments — sub-roles that only matter when is_staff is True.
    # is_staff says "may enter the staff dashboard"; these say "which desks".
    # A user can hold several. Super admins bypass them entirely.
    # The URL-name -> department map lives in core/departments.py.
    dept_operations = models.BooleanField(
        default=False, help_text='Staff department: Operations — orders, tasks, drivers, dispatch, warehouse')
    dept_finance = models.BooleanField(
        default=False, help_text='Staff department: Finance — COD, settlements, payouts, transactions')
    dept_marketing = models.BooleanField(
        default=False, help_text='Staff department: Marketing — CRM leads, WhatsApp inbox, pricing inquiries')

    # Profile completion tracking
    is_profile_completed = models.BooleanField(default=False)
    is_business_profile_completed = models.BooleanField(default=False)
    is_driver_profile_completed = models.BooleanField(default=False)

    # Password strength nudge — set at login, since that is the only moment the
    # plaintext is available. The reasons are deliberately NOT stored: knowing why
    # a password is weak narrows the guesses if the database ever leaks.
    WEAK_PASSWORD_MAX_SKIPS = 3
    weak_password = models.BooleanField(
        default=False,
        help_text='Last password seen at login failed the strength rules'
    )
    weak_password_skips = models.PositiveSmallIntegerField(
        default=0,
        help_text='Times the user postponed the change-password warning (max 3)'
    )
    weak_password_checked_at = models.DateTimeField(blank=True, null=True)

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

    # How this user arrived — captured on the session before signup (see core/signup_origin.py)
    signup_source = models.CharField(
        max_length=20,
        choices=signup_origin.SOURCE_CHOICES,
        default=signup_origin.SOURCE_UNKNOWN,
        db_index=True,
    )
    signup_source_inferred = models.BooleanField(
        default=False,
        help_text='Source was guessed from the account afterwards, not tracked at signup',
    )
    signup_landing_path = models.CharField(max_length=255, blank=True, default='')
    signup_referrer = models.CharField(max_length=255, blank=True, default='')
    signup_utm = models.JSONField(default=dict, blank=True)

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

    @property
    def staff_departments(self):
        """
        Department codes this profile holds, e.g. {'ops', 'fin'}.

        Super admins report every department plus 'admin'. Reads the booleans
        directly so it works on a bare Profile with no user loaded.
        """
        from core.departments import ADMIN, ASSIGNABLE_DEPARTMENTS, DEPARTMENT_FIELDS

        if self.is_superadmin:
            return set(ASSIGNABLE_DEPARTMENTS) | {ADMIN}
        return {
            code for code, field in DEPARTMENT_FIELDS.items()
            if getattr(self, field, False)
        }

    def get_department_labels(self):
        """Human-readable department names, for admin lists and the roles page."""
        from core.departments import DEPARTMENT_CHOICES

        held = self.staff_departments
        return [label for code, label in DEPARTMENT_CHOICES if code in held]

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
        """Percentage of the business record filled in, 0 when there is no business.

        Reads the record rather than the is_business flag: an applicant part-way
        through registration has a Business row before the flag is ever set.
        """
        try:
            from business.models import Business
            business = Business.objects.filter(profile=self).first()
            if business is None:
                return 0
            required_fields = ['business_name', 'business_phone', 'business_whatsapp',
                             'business_email', 'business_product_category', 'business_qid']
            completed = sum(1 for field in required_fields if getattr(business, field, None))
            return int((completed / len(required_fields)) * 100)
        except Exception:
            return 0

    def get_driver_profile_completion_percentage(self):
        """Percentage of the driver record filled in, 0 when there is no driver.

        Reads the record rather than the is_driver flag, which is only set once
        an application is accepted — mid-application progress still counts.
        """
        try:
            from fleet.models import Driver
            driver = Driver.objects.filter(profile=self).first()
            if driver is None:
                return 0
            required_fields = ['driver_phone', 'driver_whatsapp', 'driver_languages',
                             'driver_license_number', 'driver_bio']
            completed = sum(1 for field in required_fields if getattr(driver, field, None))
            return int((completed / len(required_fields)) * 100)
        except Exception:
            return 0

    def get_role_profile_completion_percentage(self):
        """Completion of whichever role record this user has.

        Replaces adding the two percentages together, which reported over 100%
        for anyone holding both a business and a driver record.
        """
        return max(
            self.get_business_profile_completion_percentage(),
            self.get_driver_profile_completion_percentage(),
        )

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
        upload_to=user_directory_path, default='user/avatar.png', blank=True, null=True,
        validators=image_validators(max_mb=5))

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

    # Which staff desk owns this trigger. Codes match core.departments so the
    # Auto Triggers page can filter rows by the viewer's departments.
    # 'admin' = platform internals; only super admins ever see those rows, and
    # it is the default so a NEW trigger is never exposed to a desk by accident.
    DEPARTMENT_CHOICES = [
        ('ops', 'Operations'),
        ('fin', 'Finance'),
        ('mkt', 'Marketing'),
        ('admin', 'Admin / Platform'),
    ]

    trigger_key = models.CharField(max_length=100, unique=True)
    label = models.CharField(max_length=200)
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES)
    department = models.CharField(
        max_length=10, choices=DEPARTMENT_CHOICES, default='admin', db_index=True,
        help_text='Staff desk that owns this trigger (admin = super admin only).'
    )
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
        ordering = ['department', 'category', 'trigger_key']
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


class WhatsAppSendLog(models.Model):
    """One send attempt on one instance — the evidence behind its health badge.

    Deliberately stores no message body. These rows cover OTPs and password
    reset codes, so keeping the text would put live credentials in a table that
    staff can read from the instances console.

    Keyed by instance_name rather than a FK so a log survives its instance row
    being deleted — the failures are usually what you go looking for afterwards.
    """

    CHANNEL_CHOICES = [
        ('evolution', 'Evolution API'),
        ('waha', 'WAHA'),
    ]

    instance_name = models.CharField(max_length=100, db_index=True)
    channel = models.CharField(max_length=20, choices=CHANNEL_CHOICES, default='evolution')
    phone_number = models.CharField(max_length=30, blank=True, default='', help_text="Recipient, partially masked")
    success = models.BooleanField(default=False)
    status_code = models.PositiveSmallIntegerField(null=True, blank=True)
    detail = models.CharField(max_length=255, blank=True, default='', help_text="Error text, or empty when the send succeeded")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'WhatsApp Send Log'
        verbose_name_plural = 'WhatsApp Send Logs'

    def __str__(self):
        return f"{self.instance_name} → {self.phone_number} {'OK' if self.success else 'FAILED'}"


class WhatsAppSenderRoute(models.Model):
    """Maps a platform section to the WhatsApp instance its messages must send from."""

    CHANNEL_EVOLUTION = 'evolution'
    CHANNEL_WAHA = 'waha'
    CHANNEL_CHOICES = [
        (CHANNEL_EVOLUTION, 'Evolution API'),
        (CHANNEL_WAHA, 'WAHA'),
    ]

    SECTION_CHOICES = [
        ('orders_tasks', 'Orders & Delivery Tasks'),
        ('crm_leads', 'CRM — Business Leads'),
        ('driver_onboarding', 'CRM — Driver Leads & Join Form'),
        ('marketing_campaigns', 'Marketing Campaigns'),
        ('followups', 'Follow-up Digests'),
    ]

    # Staff desk that owns each route, so the Auto Triggers page shows a desk
    # only the routes it actually sends from. Sections are code-defined, so this
    # is a static map rather than a column. Codes match core.departments.
    SECTION_DEPARTMENTS = {
        'orders_tasks': 'ops',
        'crm_leads': 'mkt',
        'driver_onboarding': 'mkt',
        'marketing_campaigns': 'mkt',
        'followups': 'mkt',
    }

    section = models.CharField(max_length=30, choices=SECTION_CHOICES, unique=True)
    instance = models.ForeignKey(
        WhatsAppInstance, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='sender_routes',
        help_text='WhatsApp number this section sends from (blank = default).'
    )
    # Which API actually carries this section's messages. A number can exist on
    # both stacks at once (WhatsAppInstance holds an Evolution instance_name AND
    # a waha_session), so the number and the channel are two separate choices —
    # driver leads can run on WAHA while business leads stay on Evolution.
    # Named explicitly rather than "default by config": a section that quietly
    # follows a global flag is exactly what makes a wrong-number send hard to
    # explain, and every route here is staff-facing.
    channel = models.CharField(
        max_length=20, choices=CHANNEL_CHOICES, default=CHANNEL_EVOLUTION,
        help_text='API this section sends through. WAHA uses the number\'s '
                  'WAHA session; Evolution uses its instance name.'
    )
    is_enabled = models.BooleanField(
        default=True,
        help_text='Off = section is not restricted; falls back to the default sender.'
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['section']
        verbose_name = 'WhatsApp Sender Route'
        verbose_name_plural = 'WhatsApp Sender Routes'

    def __str__(self):
        target = self.instance.label if self.instance else 'default'
        return f"{self.get_section_display()} → {target}"

    @property
    def department(self):
        """Desk that owns this route; unknown sections stay super-admin only."""
        return self.SECTION_DEPARTMENTS.get(self.section, 'admin')

class MessageTemplate(models.Model):
    """Staff-edited body of an automatic outbound message (WhatsApp).

    core/message_templates.py holds the shipped default for every key. A row
    here only exists once someone edits or switches off that message on the AI
    Config page — an absent row means "use the code default", so a fresh
    install sends the right thing with no seeding step.
    """

    key = models.CharField(
        max_length=100, unique=True, db_index=True,
        help_text="Template key from core.message_templates.TEMPLATE_DEFAULTS")
    body = models.TextField(
        blank=True, default='',
        help_text="Message body; {placeholders} are filled at send time. Blank = code default.")
    is_enabled = models.BooleanField(
        default=True, help_text="Off = this message is not sent at all.")
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='message_templates_updated')

    class Meta:
        ordering = ['key']
        verbose_name = 'Message Template'
        verbose_name_plural = 'Message Templates'

    def __str__(self):
        status = 'ON' if self.is_enabled else 'OFF'
        return f"[{status}] {self.key}"


class PageDepartment(models.Model):
    """
    Editable override of a page's department assignment.

    core/departments.py holds the shipped defaults for every workforce route.
    This table only stores what a super admin has *changed* from those defaults —
    a page moved to another desk, a page switched off, or a route that had no
    classification at all. An absent row means "use the code default", so the
    table stays small and the code map remains readable.

    Managed from /workforce/staff-pages/. Reads go through
    core.departments.effective_map(), which caches until a row changes.
    """

    url_name = models.CharField(
        max_length=100, unique=True, db_index=True,
        help_text="URL name without namespace, e.g. cod_ledger")
    namespace = models.CharField(
        max_length=50, default='workforce',
        help_text="URL namespace the name belongs to")
    departments = models.CharField(
        max_length=120, blank=True, default='',
        help_text="Comma-separated department codes, e.g. 'ops,fin'. "
                  "'shared' means every staff member.")
    is_enabled = models.BooleanField(
        default=True,
        help_text="Unticked blocks the page for everyone except super admins")
    label = models.CharField(max_length=150, blank=True, default='')
    notes = models.CharField(max_length=255, blank=True, default='')

    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        blank=True, null=True, related_name='page_department_changes')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['url_name']
        verbose_name = 'Page Department'
        verbose_name_plural = 'Page Departments'

    def __str__(self):
        return f"{self.url_name} → {self.departments or 'unassigned'}"

    @property
    def department_set(self):
        """Department codes as a set, ignoring blanks and stray whitespace."""
        return {c.strip() for c in self.departments.split(',') if c.strip()}

    def set_departments(self, codes):
        """Store a collection of codes in a stable, comparable order."""
        self.departments = ','.join(sorted({str(c).strip() for c in codes if str(c).strip()}))
