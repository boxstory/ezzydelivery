# Purpose: Django app config for the crm app (unified sales leads pipeline).
# Used by: INSTALLED_APPS in ezzydelivery/settings.py.

from django.apps import AppConfig


class CrmConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'crm'
    verbose_name = 'CRM Leads'
