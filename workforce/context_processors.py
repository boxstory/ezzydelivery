"""
Workforce Dashboard Context Processors
Provides sidebar badge counts for the workforce dashboard.
"""


def _safe_count_crm_overdue():
    """Count open CRM leads whose follow-up date has passed. Returns 0 if the
    crm app or its migrations aren't ready (defensive)."""
    try:
        from django.utils import timezone
        from crm.models import Lead
        return (
            Lead.objects.filter(next_followup_at__lt=timezone.localdate())
            .exclude(stage__in=Lead.CLOSED_STAGES).count()
        )
    except Exception:
        return 0


def _safe_count_avj():
    """Count AddressVerificationJob rows that need ops attention. Returns 0 if
    the whatsapp app or its migrations aren't ready (defensive)."""
    try:
        from whatsapp.models import AddressVerificationJob
        return AddressVerificationJob.objects.filter(
            status__in=('queued', 'sent', 'manual_review', 'failed')
        ).count()
    except Exception:
        return 0


def workforce_sidebar_counts(request):
    """
    Provide sidebar badge counts for workforce dashboard.
    Only queries if user is staff to avoid unnecessary DB hits for non-staff users.

    Provides:
        - pending_publish_count: Orders verified but not yet published to task
        - unpublished_tasks_count: Tasks created but not yet published to fleet
        - followup_count: Tasks in pending status (follow-up required)
    """
    if not hasattr(request, 'user') or not request.user.is_authenticated:
        return {}

    # Only provide counts for staff users
    # Check profile.is_staff if available, else check user.is_staff
    is_staff = False
    if hasattr(request, '_cached_profile') and request._cached_profile:
        is_staff = request._cached_profile.is_staff
    elif hasattr(request.user, 'is_staff'):
        is_staff = request.user.is_staff

    if not is_staff:
        return {}

    # Check if already cached on request (per-request dedup)
    if hasattr(request, '_cached_workforce_counts'):
        return request._cached_workforce_counts

    from orders.models import Order, TempOrder
    from delivery.models import DeliveryTask
    from django.core.cache import cache

    # Check cross-request cache (60 second TTL)
    cache_key = f'wf_sidebar_counts_{request.user.id}'
    cached = cache.get(cache_key)
    if cached:
        request._cached_workforce_counts = cached
        return cached

    # Check for sync errors from last auto-sync
    sync_errors = cache.get('temp_orders_sync_errors', [])

    from django.db.models import Q

    counts = {
        # New (unimported) temp orders count for sidebar badge (only from enabled businesses)
        'temp_orders_count': TempOrder.objects.filter(
            status='new',
            business__temp_order_enabled=True
        ).exclude(
            # Exclude orphaned records with no source FK
            Q(source_type='onedrive', onedrive_source__isnull=True) |
            Q(source_type='google_sheet', api_settings__isnull=True) |
            Q(source_type__in=['shopify', 'woocommerce'], api_settings__isnull=True) |
            Q(source_type='public_link', public_link_source__isnull=True)
        ).count(),

        # Sync errors from last auto-sync (mapping mismatch, etc.)
        'temp_orders_sync_errors': sync_errors,

        # Orders not yet published to task (mirrors the /orders/to_publish/ list:
        # no delivery task created and not cancelled).
        'pending_publish_count': Order.objects.filter(
            task_created=False
        ).exclude(order_status='cancelled').count(),

        # Tasks created but not yet published to fleet drivers
        'unpublished_tasks_count': DeliveryTask.objects.filter(
            order__business__business_status='active',
            dl_task_publish=False
        ).exclude(
            dl_task_status__in=['delivered', 'cancelled', 'failed', 'rejected']
        ).count(),

        # Tasks in pending status (follow-up required)
        'followup_count': DeliveryTask.objects.filter(
            dl_task_status='pending'
        ).count(),

        # Address verification jobs awaiting attention (queued + sent +
        # manual_review). Surfaces in the Tasks/Import sidebar badges so ops
        # notice the WhatsApp pipeline backlog.
        'address_verify_pending_count': _safe_count_avj(),

        # Open CRM leads with an overdue follow-up (CRM sidebar badge)
        'crm_overdue_count': _safe_count_crm_overdue(),
    }

    cache.set(cache_key, counts, 60)  # 60 second TTL
    request._cached_workforce_counts = counts
    return counts
