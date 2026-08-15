"""
Purpose: Drop the cached department-override map whenever a PageDepartment row changes.
Used by: core.apps.CoreConfig.ready (imported there — core/signals.py is deliberately NOT imported)
Notes: Without this the middleware would keep serving a stale map for up to OVERRIDE_CACHE_TTL after an edit.
"""

from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from core.departments import clear_override_cache
from core.models import PageDepartment


@receiver(post_save, sender=PageDepartment)
@receiver(post_delete, sender=PageDepartment)
def invalidate_department_overrides(sender, instance, **kwargs):
    clear_override_cache()
