"""
Delivery Task State Machine
===========================
Defines valid dl_task_status transitions per actor (staff, admin, driver).

Stage order (forward flow):
    Stage 0: for_review
    Stage 1: pending
    Stage 2: assigned
    Stage 3: accepted
    Stage 4: picked_up
    Stage 5: start_ride
    Stage 6: in_transit / out_for_delivery
    Stage 7: contacted / non_reachable / address_pending /
             customer_confirmation_pending / customer_delaying / dl_pending_payment
    Stage 8: delivered / failed / rejected / cancelled  (terminal)

Rules:
    - Staff: forward transitions only + cancel from any stage
    - Admin/Superuser: any transition (forward or backward)
    - Driver: specific workflow transitions only

Usage:
    from delivery.state_machine import can_transition, get_allowed_transitions

    ok, reason = can_transition(old_status, new_status, actor='staff')
"""

# ---------------------------------------------------------------------------
# Status stages — lower number = earlier in workflow
# ---------------------------------------------------------------------------

STATUS_STAGE = {
    'for_review':    0,
    'pending':       1,
    'assigned':      2,
    'accepted':      3,
    'picked_up':     4,
    'start_ride':    5,
    'in_transit':    6,
    'out_for_delivery': 6,
    'contacted':     7,
    'non_reachable': 7,
    'address_pending': 7,
    'customer_confirmation_pending': 7,
    'customer_delaying': 7,
    'dl_pending_payment': 7,
    'delivered':     8,
    'partial_delivery': 8,
    'failed':        8,
    'rejected':      8,
    'cancelled':     8,
    'dropsownlost':  8,
}

_ALL_STATUSES = set(STATUS_STAGE.keys())

# ---------------------------------------------------------------------------
# Staff transitions — forward only + cancel from any stage
# ---------------------------------------------------------------------------

def _build_staff_transitions():
    """Staff can move forward (higher stage) or cancel. Cannot go backward."""
    transitions = {}
    for status, stage in STATUS_STAGE.items():
        forward = set()
        for target, target_stage in STATUS_STAGE.items():
            if target == status:
                continue
            # Allow forward (higher or equal stage) + always allow cancel
            if target_stage > stage or target == 'cancelled':
                forward.add(target)
        transitions[status] = forward
    # Terminal statuses — no forward moves for staff
    for terminal in ('delivered', 'partial_delivery', 'failed', 'rejected', 'cancelled', 'dropsownlost'):
        transitions[terminal] = set()
    return transitions

STAFF_TRANSITIONS = _build_staff_transitions()

# Admin transitions — any status to any status (full override)
ADMIN_TRANSITIONS = {status: _ALL_STATUSES - {status} for status in _ALL_STATUSES}

# ---------------------------------------------------------------------------
# Driver transitions (fleet app / API)
# ---------------------------------------------------------------------------

DRIVER_TRANSITIONS = {
    'assigned':   {'accepted', 'rejected'},
    'accepted':   {'picked_up', 'out_for_delivery', 'delivered', 'partial_delivery', 'failed', 'rejected'},
    'picked_up':  {'start_ride', 'in_transit', 'out_for_delivery', 'delivered', 'partial_delivery', 'failed'},
    'start_ride': {'in_transit', 'out_for_delivery', 'delivered', 'partial_delivery', 'failed'},
    'in_transit': {'out_for_delivery', 'delivered', 'partial_delivery', 'contacted', 'non_reachable', 'address_pending',
                   'customer_confirmation_pending', 'customer_delaying', 'dl_pending_payment', 'failed'},
    'out_for_delivery': {'delivered', 'partial_delivery', 'contacted', 'non_reachable', 'address_pending',
                         'customer_confirmation_pending', 'customer_delaying', 'dl_pending_payment', 'failed'},
    'contacted':          {'delivered', 'partial_delivery', 'non_reachable', 'failed', 'dl_pending_payment'},
    'non_reachable':      {'contacted', 'customer_delaying', 'address_pending', 'failed'},
    'address_pending':    {'contacted', 'non_reachable', 'failed'},
    'customer_confirmation_pending': {'contacted', 'non_reachable', 'failed'},
    'customer_delaying':  {'contacted', 'failed'},
    'dl_pending_payment': {'delivered', 'partial_delivery', 'failed'},
    # Self-assign from pool
    'pending':    {'accepted'},
    'for_review': {'accepted'},
    # Terminal
    'delivered':       set(),
    'partial_delivery': set(),
    'failed':          set(),
    'rejected':        set(),
    'cancelled':       set(),
    'dropsownlost':    set(),
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
        actor (str): 'driver', 'staff', or 'admin'.

    Returns:
        tuple: (bool allowed, str reason_or_empty)
    """
    if old_status == new_status:
        return True, ''

    # Special case: allow failed → accepted for staff/admin (task retry)
    if old_status == 'failed' and new_status == 'accepted' and actor in ('staff', 'admin'):
        return True, ''

    if actor == 'admin':
        transitions = ADMIN_TRANSITIONS
    elif actor == 'staff':
        transitions = STAFF_TRANSITIONS
    else:
        transitions = DRIVER_TRANSITIONS

    allowed = transitions.get(old_status, set())

    if new_status in allowed:
        return True, ''

    return False, _build_reason(old_status, new_status, actor, allowed)


def get_allowed_transitions(current_status, actor='driver'):
    """Return the set of valid next statuses from the current status for actor."""
    if actor == 'admin':
        transitions = ADMIN_TRANSITIONS
    elif actor == 'staff':
        transitions = STAFF_TRANSITIONS
    else:
        transitions = DRIVER_TRANSITIONS
    return transitions.get(current_status, set())


def get_stage(status):
    """Return the stage number for a status."""
    return STATUS_STAGE.get(status, -1)


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
