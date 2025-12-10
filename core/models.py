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
    - Used by: client, fleet, workforce, orders apps
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
        - Business (client app): profile.business_set
        - Driver (fleet app): profile.driver
        - BusinessTeamProfile (client app): profile.businessteam
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
    phone = models.IntegerField(blank=True, null=True)
    whatsapp = models.IntegerField(blank=True, null=True)
    zone_name = models.CharField(max_length=255, blank=True, null=True)
    address = models.CharField(max_length=255, blank=True, null=True)
    nationlity = models.CharField(max_length=255, blank=True, null=True)
    date_of_birth = models.DateField(blank=True, null=True)

    # User Roles
    is_business = models.BooleanField(default=False)
    is_staff = models.BooleanField(default=False)
    is_driver = models.BooleanField(default=False)

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
            from datetime import datetime
            import random
            year = datetime.now().year
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
        completed = sum(1 for field in required_fields if getattr(self, field))
        return int((completed / len(required_fields)) * 100)

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
        str: Path in format '{instance.path}/{filename}'
    """
    return '%s/%s' % (instance.path, filename)


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