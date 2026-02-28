"""
Delivery Task State Machine
===========================
Defines valid dl_task_status transitions per actor (staff vs driver).

Usage:
    from delivery.state_machine import can_transition, get_invalid_reason

    ok, reason = can_transition(old_status, new_status, actor='driver')
    if not ok:
        raise ValueError(reason)
"""

# ---------------------------------------------------------------------------
# Valid transitions per actor
# ---------------------------------------------------------------------------

# Staff can make these transitions (workforce dashboard operations)
STAFF_TRANSITIONS = {
    'for_review': {'pending', 'cancelled'},
    'pending':    {'assigned', 'cancelled'},
    'assigned':   {'pending', 'cancelled'},          # unassign or cancel
    'accepted':   {'assigned', 'cancelled'},          # reassign or cancel
    # Staff can force-cancel from any pickup state but not deliver
    'picked_up':          {'cancelled'},
    'start_ride':         {'cancelled'},
    'in_transit':         {'cancelled'},
    'out_for_delivery':   {'cancelled'},
    'contacted':          {'cancelled'},
    'non_reachable':      {'pending', 'cancelled'},   # re-pool or cancel
    'address_pending':    {'pending', 'cancelled'},
    'customer_delaying':  {'pending', 'cancelled'},
    'dl_pending_payment': {'pending', 'cancelled'},
    'customer_confirmation_pending': {'pending', 'cancelled'},
    'failed':    {'pending', 'cancelled'},            # retry: back to pending with new driver
    'rejected':  {'pending', 'cancelled'},
    'delivered': set(),                               # terminal — no staff transitions
    'cancelled': set(),                               # terminal
}

# Drivers can make these transitions (fleet app / API)
DRIVER_TRANSITIONS = {
    'assigned':   {'accepted', 'rejected'},
    'accepted':   {'picked_up', 'rejected'},
    'picked_up':  {'start_ride', 'in_transit', 'out_for_delivery', 'failed'},
    'start_ride': {'in_transit', 'out_for_delivery', 'failed'},
    'in_transit': {'out_for_delivery', 'contacted', 'non_reachable', 'address_pending',
                   'customer_confirmation_pending', 'customer_delaying', 'dl_pending_payment', 'failed'},
    'out_for_delivery': {'contacted', 'non_reachable', 'address_pending',
                         'customer_confirmation_pending', 'customer_delaying', 'dl_pending_payment', 'failed'},
    'contacted':          {'delivered', 'non_reachable', 'failed', 'dl_pending_payment'},
    'non_reachable':      {'contacted', 'customer_delaying', 'address_pending', 'failed'},
    'address_pending':    {'contacted', 'non_reachable', 'failed'},
    'customer_confirmation_pending': {'contacted', 'non_reachable', 'failed'},
    'customer_delaying':  {'contacted', 'failed'},
    'dl_pending_payment': {'delivered', 'failed'},
    # Terminal — drivers cannot change these
    'delivered': set(),
    'failed':    set(),
    'rejected':  set(),
    'cancelled': set(),
    'for_review': set(),
    'pending':    set(),
}

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def can_transition(old_status, new_status, actor='driver'):
    """
    Check whether a status transition is valid for the given actor.

    Args:
        old_status (str): Current dl_task_status value.
        new_status (str): Desired dl_task_status value.
        actor (str): 'driver' or 'staff'.

    Returns:
        tuple: (bool allowed, str reason_or_empty)
    """
    if old_status == new_status:
        return True, ''

    transitions = STAFF_TRANSITIONS if actor == 'staff' else DRIVER_TRANSITIONS
    allowed = transitions.get(old_status, set())

    if new_status in allowed:
        return True, ''

    return False, _build_reason(old_status, new_status, actor, allowed)


def get_allowed_transitions(current_status, actor='driver'):
    """Return the set of valid next statuses from the current status for actor."""
    transitions = STAFF_TRANSITIONS if actor == 'staff' else DRIVER_TRANSITIONS
    return transitions.get(current_status, set())


def _build_reason(old_status, new_status, actor, allowed):
    if not allowed:
        return (
            f"Status '{old_status}' is terminal — no further transitions allowed."
        )
    allowed_list = ', '.join(sorted(allowed)) or 'none'
    return (
        f"Invalid transition '{old_status}' → '{new_status}' for {actor}. "
        f"Allowed next statuses: [{allowed_list}]."
    )
