"""
Workforce Dashboard Context Processors
Provides sidebar badge counts for the workforce dashboard.
"""


def workforce_departments(request):
    """
    Expose the signed-in staff member's departments to the sidebar templates.

    Cheap: reads three booleans off the already-cached profile, no queries of
    its own. Kept out of workforce_sidebar_counts because that result is cached
    for 60s — a department change must take effect on the next page load, not a
    minute later.

    Provides:
        wf_dept_ops / wf_dept_fin / wf_dept_mkt / wf_dept_admin (bool)
        wf_departments (set of codes)
    """
    if not hasattr(request, 'user') or not request.user.is_authenticated:
        return {}

    from core.departments import ADMIN, FIN, MKT, OPS, user_departments

    held = user_departments(request.user)
    if not held:
        return {}

    return {
        'wf_departments': held,
        'wf_dept_ops': OPS in held,
        'wf_dept_fin': FIN in held,
        'wf_dept_mkt': MKT in held,
        'wf_dept_admin': ADMIN in held,
    }


def _safe_count_pickup_pending():
    """Count unclaimed first-mile pickup tasks. Returns 0 defensively."""
    try:
        # Same definition the drivers' pool uses, so staff and drivers can't see
        # different numbers (cancelled/delivered legs are excluded from both).
        from delivery.selectors import pending_pickup_pool
        return pending_pickup_pool().count()
    except Exception:
        return 0


def _safe_count_crm_overdue():
    """Count open CRM leads whose follow-up date has passed. Returns 0 if the
    crm app or its migrations aren't ready (defensive)."""
    try:
        from django.utils import timezone
        from crm.models import Lead
        from crm.services import closed_stage_keys
        return (
            Lead.objects.filter(next_followup_at__lt=timezone.localdate())
            .exclude(stage__in=closed_stage_keys()).count()
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


def _safe_count_upcoming_tasks():
    """Count open delivery tasks dated past today (postponed / future-dated).
    Mirrors workforce.views.tasks_upcoming_list. Returns 0 defensively."""
    try:
        from django.db.models import Case, DateField, F, Value, When
        from django.db.models.functions import Greatest
        from django.utils import timezone
        from delivery.models import DeliveryTask

        today = timezone.localdate()
        scheduled_expr = Case(
            When(order__scheduled_delivery=True, order__scheduled_date__isnull=False,
                 then=F('order__scheduled_date')),
            default=Value(None, output_field=DateField()),
            output_field=DateField(),
        )
        return DeliveryTask.objects.filter(
            order__business__business_status='active',
        ).exclude(
            dl_task_status__in=['delivered', 'partial_delivery', 'cancelled',
                                'rejected', 'dropsownlost'],
        ).annotate(
            due_date=Greatest('dl_task_date', 'reschedule_date', scheduled_expr),
        ).filter(due_date__gt=today).count()
    except Exception:
        return 0


def workforce_sidebar_counts(request):
    """
    Provide sidebar badge counts for workforce dashboard.
    Only queries if user is staff to avoid unnecessary DB hits for non-staff users.

    Provides:
        - pending_publish_count: Orders verified but not yet published to task
        - unpublished_tasks_count: Tasks created but not yet published to fleet
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

        # Address verification jobs awaiting attention (queued + sent +
        # manual_review). Surfaces in the Tasks/Import sidebar badges so ops
        # notice the WhatsApp pipeline backlog.
        'address_verify_pending_count': _safe_count_avj(),

        # Open CRM leads with an overdue follow-up (CRM sidebar badge)
        'crm_overdue_count': _safe_count_crm_overdue(),

        # Unclaimed first-mile pickups (Pickup sidebar badge)
        'pickup_pending_count': _safe_count_pickup_pending(),

        # Open tasks dated after today — postponed or future-dated deliveries
        'upcoming_tasks_count': _safe_count_upcoming_tasks(),
    }

    cache.set(cache_key, counts, 60)  # 60 second TTL
    request._cached_workforce_counts = counts
    return counts
