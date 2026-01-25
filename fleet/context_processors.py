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
    }

    if not request.user.is_authenticated:
        return context

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

    except fleet_models.Driver.DoesNotExist:
        pass

    return context
