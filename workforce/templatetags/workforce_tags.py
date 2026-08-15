from django import template

register = template.Library()


@register.filter
def get_status_point(status_point_map, entry):
    """Look up a TaskStatusPoint from the map using an OrderStatusHistory entry."""
    if not status_point_map or not entry:
        return None
    key = f"{entry.old_value}__{entry.new_value}"
    return status_point_map.get(key)


def _driver_name(driver):
    """Human name for a driver — Driver.__str__ is the login username (ezzy.dr001),
    which is not what staff identify drivers by. Mirrors _driver_chip.html."""
    if not driver:
        return ''
    user = getattr(driver, 'user', None)
    name = (user.get_full_name() if user else '') or ''
    return (name.strip() or getattr(driver, 'driver_code', '')
            or (getattr(user, 'username', '') if user else '') or 'driver')


@register.filter
def pickup_cancel_info(pickup):
    """When, why and by whom a first-mile leg was cancelled.

    The card could only say "Pickup cancelled", which repeats the status badge
    and tells staff nothing. The facts live on the order timeline row that the
    cancel wrote, so they are read back here rather than duplicated onto the
    PickupTask. Returns {} when the leg was cancelled before that row existed.
    """
    if not pickup or pickup.status != 'cancelled':
        return {}

    from orders.models import OrderStatusHistory

    entry = (OrderStatusHistory.objects
             .filter(order_id=pickup.order_id, field_name='pickup_status',
                     new_value='cancelled')
             .select_related('changed_by')
             .order_by('-created_at').first())
    if not entry:
        return {}

    who = entry.changed_by
    return {
        'when': entry.created_at,
        # A cancel with no user is the system closing a dead leg (order cancelled,
        # delivery already run) — say so instead of leaving a blank.
        'by': ((who.get_full_name() or who.username) if who else 'System'),
        'from_label': entry.old_display or '',
        'reason': entry.notes or '',
    }


def _pickup_final_label(pickup):
    """Label for the last rail step — the real outcome once the leg closed,
    otherwise the plan it is still heading for.

    Both self-delivery and a confirmed transfer close as 'handed_off', so the
    status alone cannot say what happened: only the transfer fields separate
    "the same driver kept it" from "another driver took it", and staff need the
    name of whoever ended up holding the goods.
    """
    handed_over = bool(pickup.transfer_to_driver_id and pickup.transfer_confirmed_at)

    if pickup.status == 'dropped':
        return 'Dropped at hub'
    if pickup.status == 'handed_off':
        if handed_over:
            return f'Passed to {_driver_name(pickup.transfer_to_driver)}'
        return 'Self delivery'

    # Still in flight — name the plan, and the target driver if one was picked.
    if pickup.disposition == 'drop':
        return 'Drop at hub'
    if pickup.disposition == 'self_deliver':
        return 'Self delivery'
    if pickup.transfer_to_driver_id:
        return f'Pass to {_driver_name(pickup.transfer_to_driver)}'
    return 'Pass to driver'


@register.filter
def pickup_rail(pickup):
    """Build the shared leg-rail steps for a PickupTask.

    Derived from the object so every page including _pickup_leg_card.html gets the
    rail without its view having to assemble it. Only a hub drop stamps dropped_at,
    so a hand-off falls back to updated_at and is flagged approximate.
    """
    if not pickup:
        return []
    idx = pickup.stage_index
    last_label = _pickup_final_label(pickup)

    final_time, final_approx = pickup.dropped_at, False
    if not final_time and idx == 5:
        final_time, final_approx = pickup.updated_at, True

    spec = [
        ('Pending', None, False),
        ('Accepted', pickup.accepted_at, False),
        ('On the way', None, False),
        ('Arrived', None, False),
        ('Collected', pickup.collected_at, False),
        (last_label, final_time, final_approx),
    ]
    return [
        {'label': label, 'done': idx >= rank, 'now': idx == rank,
         'time': stamp, 'approx': approx}
        for rank, (label, stamp, approx) in enumerate(spec)
    ]


@register.filter
def duration_short(seconds):
    """Compact elapsed-time label for GPS freshness badges: 7s, 4m, 1h 12m."""
    try:
        total = int(seconds)
    except (TypeError, ValueError):
        return ''
    if total < 60:
        return f"{total}s"
    if total < 3600:
        return f"{total // 60}m"
    hours, rem = divmod(total, 3600)
    minutes = rem // 60
    return f"{hours}h {minutes}m" if minutes else f"{hours}h"


@register.filter
def get_item(dictionary, key):
    """Allow dictionary[key] lookups in templates: {{ my_dict|get_item:some_var }}"""
    if dictionary is None:
        return ''
    return dictionary.get(key, '')


@register.filter
def in_csv(value, csv):
    """Membership test against a comma-separated string.

    Why: the sidebar partials need exact url_name matching against a list of
    names. The default template `in` does substring matching on strings, which
    falsely matches e.g. 'temp_orders' inside 'temp_orders_by_date'.
    """
    if not value or not csv:
        return False
    return value in {name.strip() for name in csv.split(',')}


@register.filter
def vehicle_icon(vehicle_type):
    """Font Awesome icon class for a fleet vehicle type.

    Why: the plate mark on the driver roster and the verification queue shows
    the vehicle at a glance instead of a fixed 'QAT' band, and both templates
    need the same mapping.
    """
    return {
        'bike': 'fa-motorcycle',
        'car': 'fa-car-side',
        'van': 'fa-van-shuttle',
        'pickup': 'fa-truck-pickup',
        'pickup3ton': 'fa-truck',
        'pickup_big': 'fa-truck-moving',
    }.get((vehicle_type or '').strip().lower(), 'fa-car-side')
