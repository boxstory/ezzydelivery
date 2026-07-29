"""
Purpose: Single mapping from the operational COD ladder (cod_status_by_staff) to the seller-facing one (cod_status_by_client).
Used by: the COD legs in ezzy_api.views, fleet.views, fleet.wallet_service and the backfill_client_cod_status command.
Notes: The seller ladder was previously written once at import and never advanced; this keeps the two in step.
"""

# Operational custody state -> what the seller should see.
# 'disputed' and 'invoiced' are staff-driven and are never set from here.
STAFF_TO_CLIENT = {
    'not_collected': 'pending',
    'partially_collected': 'partial_paid',
    'fully_paid': 'collected',
    'cod_with_driver': 'collected',
    'cod_with_ezzy': 'received_by_company',
    'cod_settled_with_business': 'settled',
}

# Seller-side states that describe how the ORDER was paid, not where the cash
# is. Deriving over them would lose the fact that the order was never COD.
CLIENT_STATES_NOT_DERIVED = {'online_paid', 'no_cod'}


def client_status_for(staff_status, current_client_status=None):
    """Seller-facing COD status for an operational status, or None to leave alone.

    Returns None when the order is prepaid/non-COD, or when the operational
    status has no seller-facing meaning — callers should skip the write.
    """
    if current_client_status in CLIENT_STATES_NOT_DERIVED:
        return None
    return STAFF_TO_CLIENT.get(staff_status)


def apply_cod_status(order, staff_status, save=True):
    """Set both COD ladders on an order from one operational status.

    Keeps cod_status_by_client moving in step with cod_status_by_staff instead
    of leaving it frozen at whatever the import set.
    """
    fields = []
    if order.cod_status_by_staff != staff_status:
        order.cod_status_by_staff = staff_status
        fields.append('cod_status_by_staff')

    client_status = client_status_for(staff_status, order.cod_status_by_client)
    if client_status and order.cod_status_by_client != client_status:
        order.cod_status_by_client = client_status
        fields.append('cod_status_by_client')

    if fields and save:
        order.save(update_fields=fields)
    return fields
