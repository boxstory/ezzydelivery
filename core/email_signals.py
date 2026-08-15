"""
Purpose: Keep auth emails lower-case, the same rule EmailNormalizedModel applies to our own models.
Used by: core.apps.CoreConfig.ready() — receivers must be imported for them to connect.
Notes: auth.User and allauth's EmailAddress are third-party models we cannot add a mixin to,
       so they are normalized with pre_save instead.
"""

from django.conf import settings
from django.db.models.signals import pre_save
from django.dispatch import receiver

from core.email_normalize import normalize_email


@receiver(pre_save, sender=settings.AUTH_USER_MODEL, dispatch_uid='core_normalize_user_email')
def normalize_user_email(sender, instance, **kwargs):
    """Lower-case User.email before it hits the database."""
    if instance.email:
        instance.email = normalize_email(instance.email)


try:
    from allauth.account.models import EmailAddress

    @receiver(pre_save, sender=EmailAddress, dispatch_uid='core_normalize_allauth_email')
    def normalize_allauth_email(sender, instance, **kwargs):
        """
        Lower-case allauth's own copy of the address.

        allauth already matches addresses case-insensitively, so this only
        settles which casing gets stored and shown.
        """
        if instance.email:
            instance.email = normalize_email(instance.email)

except ImportError:  # pragma: no cover - allauth is a hard dependency in practice
    pass
