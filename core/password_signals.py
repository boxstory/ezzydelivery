"""
Purpose: Flag accounts whose password fails the strength rules, so they can be nudged to change it.
Used by: core/apps.py (CoreConfig.ready), core/middleware.py (WeakPasswordWarningMiddleware)
Notes: Login is the only moment the plaintext exists, so the check hangs off user_logged_in and
       reads the submitted field. Social logins have no usable password and are left alone.
"""

import logging

from allauth.account.signals import password_changed, password_reset, password_set
from django.contrib.auth.signals import user_logged_in
from django.dispatch import receiver
from django.utils import timezone

from core.password_strength import is_weak

logger = logging.getLogger(__name__)

# allauth's login form posts "password"; the reset/change forms post "password1".
PASSWORD_FIELDS = ('password', 'password1')


def _submitted_password(request):
    if request is None or request.method != 'POST':
        return None
    for field in PASSWORD_FIELDS:
        value = request.POST.get(field)
        if value:
            return value
    return None


def flag(user, password):
    """Record whether this password is weak. Clears the counter once a strong one is set."""
    profile = getattr(user, 'profile', None)
    if profile is None:
        return

    weak = is_weak(password, user)
    updates = {'weak_password': weak, 'weak_password_checked_at': timezone.now()}
    if not weak:
        updates['weak_password_skips'] = 0

    for field, value in updates.items():
        setattr(profile, field, value)
    profile.save(update_fields=list(updates))


@receiver(user_logged_in)
def check_password_on_login(sender, request, user, **kwargs):
    if not user.has_usable_password():
        return

    password = _submitted_password(request)
    if not password:
        # Social login, or a session restored without a password post — leave the flag as is.
        return

    try:
        flag(user, password)
    except Exception:
        logger.exception("Weak-password check failed for user %s", user.pk)


@receiver(password_changed)
@receiver(password_reset)
@receiver(password_set)
def recheck_after_change(sender, request, user, **kwargs):
    """Re-evaluate immediately so a user who just fixed their password is not warned again."""
    password = _submitted_password(request)
    try:
        if password:
            flag(user, password)
        else:
            profile = getattr(user, 'profile', None)
            if profile is not None:
                profile.weak_password = False
                profile.weak_password_skips = 0
                profile.weak_password_checked_at = timezone.now()
                profile.save(update_fields=[
                    'weak_password', 'weak_password_skips', 'weak_password_checked_at'
                ])
    except Exception:
        logger.exception("Weak-password recheck failed for user %s", user.pk)
