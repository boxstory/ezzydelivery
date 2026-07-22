"""
Fleet Context Processors

Provides wallet status and driver information to all templates
that extend the fleet dashboard base.
"""

from fleet import models as fleet_models
from fleet.wallet_service import WalletService


def driver_wallet_status(request):
    """
    Add driver wallet status to template context for COD limit warnings.

    Returns empty dict if user is not authenticated or not a driver.
    """
    context = {
        'driver_wallet_warning': None,
        'driver_wallet_blocked': False,
        'unread_notifications': 0,
        'pickup_badge_count': 0,
    }

    if not request.user.is_authenticated:
        return context

    # Only run on fleet pages — avoid DB hit on every page across the site
    if not request.path.startswith('/fleet/'):
        return context

    # Avoid duplicate query within the same request
    if hasattr(request, '_driver_wallet_status_context'):
        return request._driver_wallet_status_context

    try:
        driver = fleet_models.Driver.objects.get(user_id=request.user.id)
        wallet_status = WalletService.get_wallet_status(driver)

        context['driver_wallet_status'] = wallet_status
        context['driver_wallet_blocked'] = wallet_status.get('is_blocked', False)
        context['driver_wallet_warning'] = wallet_status.get('is_warning', False)
        context['driver_cod_in_hand'] = wallet_status.get('cod_in_hand', 0)
        context['driver_credit_limit'] = wallet_status.get('credit_limit', 0)
        context['driver_available_credit'] = wallet_status.get('available_credit', 0)
        context['driver_usage_percentage'] = wallet_status.get('usage_percentage', 0)

        context['unread_notifications'] = fleet_models.DriverNotification.objects.filter(
            driver=driver, is_read=False
        ).count()

        # Pickup tab badge: claimable first-mile pickups + own active ones
        from delivery.selectors import pickup_pool_for
        from delivery.models import PickupTask
        context['pickup_badge_count'] = pickup_pool_for(driver).count() + PickupTask.objects.filter(
            driver=driver, status__in=['accepted', 'in_progress', 'arrived', 'collected']
        ).count()

    except fleet_models.Driver.DoesNotExist:
        pass

    request._driver_wallet_status_context = context
    return context
