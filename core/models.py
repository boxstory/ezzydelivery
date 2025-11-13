from django.conf import settings
from django.db import models


# Create your models here.
class Profile(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='profile')
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
    is_business = models.BooleanField(default=False)
    is_staff = models.BooleanField(default=False)
    is_driver = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.username}"

    class Meta:
        verbose_name_plural = "Profiles"


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