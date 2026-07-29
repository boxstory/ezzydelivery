from django import template

register = template.Library()


@register.filter
def get_status_point(status_point_map, entry):
    """Look up a TaskStatusPoint from the map using an OrderStatusHistory entry."""
    if not status_point_map or not entry:
        return None
    key = f"{entry.old_value}__{entry.new_value}"
    return status_point_map.get(key)


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
    if pickup.status == 'handed_off':
        last_label = 'Handed off'
    elif pickup.disposition == 'drop':
        last_label = 'Dropped at hub'
    else:
        last_label = 'Handed off'

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
