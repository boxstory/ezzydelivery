from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth.models import User
from allauth.account.signals import user_signed_up
from core import models as core_models
from core import signup_origin

# Local aliases for commonly used models
Profile = core_models.Profile
ProfilePicture = core_models.ProfilePicture


@receiver(user_signed_up)
def create_profile(request, user, **kwargs):
    """Create user profile when a new user signs up, stamped with how they arrived"""
    origin = signup_origin.read(request)
    Profile.objects.create(
        user=user,
        signup_source=origin['source'],
        signup_landing_path=origin['landing_path'],
        signup_referrer=origin['referrer'],
        signup_utm=origin['utm'],
    )


@receiver(user_signed_up)
def create_profile_picture(request, user, **kwargs):
    """Create default profile picture when a new user signs up"""
    # Get the profile that was just created
    profile = Profile.objects.get(user=user)
    ProfilePicture.objects.create(user=user, profile=profile)