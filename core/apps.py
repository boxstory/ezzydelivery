from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'core'

    def ready(self):
        # Weak-password flagging only. core/signals.py is deliberately NOT imported here:
        # its create_profile receiver has never been active and profiles are created in views.
        from core import password_signals  # noqa: F401
        # Keeps the cached staff-department override map fresh after edits.
        from core import department_signals  # noqa: F401
        # Lower-cases auth.User / allauth EmailAddress emails on write; our own
        # models do the same through core.email_normalize.EmailNormalizedModel.
        from core import email_signals  # noqa: F401
