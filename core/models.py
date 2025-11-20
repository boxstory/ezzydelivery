from django.conf import settings
from django.db import models


# Create your models here.
class Profile(models.Model):
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
   return '%s/%s' % (instance.path, filename)


class ProfilePicture(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='profile_picture')
    profile = models.ForeignKey(Profile,  on_delete=models.CASCADE, related_name='profile_picture')
    profile_picture = models.ImageField(
        upload_to=user_directory_path , default='user/avatar.png', blank=True, null=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return str(self.id)


class WhatsAppVerification(models.Model):
    """Model for storing WhatsApp verification codes"""
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