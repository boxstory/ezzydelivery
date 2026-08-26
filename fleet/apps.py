from django.apps import AppConfig


class FleetConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'fleet'

    def ready(self):
        from fleet import signals  # noqa: F401
        # One-device-per-driver: claims the device each login came from.
        from fleet import device_signals  # noqa: F401
