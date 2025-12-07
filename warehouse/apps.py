from django.apps import AppConfig


class WarehouseConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'warehouse'
    verbose_name = 'Warehouse Management'

    def ready(self):
        import warehouse.signals  # noqa: F401
