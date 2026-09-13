# Purpose: Django app config for the driver salary (payroll) module.
# Used by: settings.INSTALLED_APPS
from django.apps import AppConfig


class PayrollConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'payroll'
    verbose_name = 'Driver Payroll'
