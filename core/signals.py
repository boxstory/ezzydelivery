
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth.models import User
from allauth.account.signals import user_signed_up
from core.models import Profile, ProfilePicture


@receiver(user_signed_up)
def create_profile(request, user, **kwargs):
    Profile.objects.create(user=user)


@receiver(user_signed_up)
def create_profile_picture(request, user, **kwargs):
    ProfilePicture.objects.create(user=user)