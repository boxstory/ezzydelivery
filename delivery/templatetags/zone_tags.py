from django import template

register = template.Library()


@register.filter
def get_zone_group(zone_group_map, zone_number):
    """Get zone group name from map by zone number"""
    if zone_group_map and zone_number:
        return zone_group_map.get(zone_number, '')
    return ''
