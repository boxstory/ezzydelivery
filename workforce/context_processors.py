"""
Workforce Dashboard Context Processors
Provides sidebar badge counts for the workforce dashboard.
"""


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

    # Check if already cached on request
    if hasattr(request, '_cached_workforce_counts'):
        return request._cached_workforce_counts

    from orders.models import Order, TempOrder
    from delivery.models import DeliveryTask

    counts = {
        # New (unimported) temp orders count for sidebar badge
        'temp_orders_count': TempOrder.objects.filter(status='new').count(),

        # Orders verified but not yet published to task
        'pending_publish_count': Order.objects.filter(
            verification_status='verified',
            task_created=False
        ).count(),

        # Tasks created but not yet published to fleet drivers
        'unpublished_tasks_count': DeliveryTask.objects.filter(
            dl_task_publish=False
        ).exclude(
            dl_task_status__in=['delivered', 'cancelled', 'failed', 'rejected']
        ).count(),

        # Tasks in pending status (follow-up required)
        'followup_count': DeliveryTask.objects.filter(
            dl_task_status='pending'
        ).count(),
    }

    request._cached_workforce_counts = counts
    return counts
