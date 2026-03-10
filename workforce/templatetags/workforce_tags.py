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
def get_item(dictionary, key):
    """Allow dictionary[key] lookups in templates: {{ my_dict|get_item:some_var }}"""
    if dictionary is None:
        return ''
    return dictionary.get(key, '')
