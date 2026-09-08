from django import template

register = template.Library()


@register.filter
def get_zone_group(zone_group_map, zone_number):
    """Get zone group name from map by zone number"""
    if zone_group_map and zone_number:
        return zone_group_map.get(zone_number, '')
    return ''


@register.filter
def get_zone_name(zone_name_map, zone_number):
    """Official zone name for a zone number, from a map built once in the view.

    Lets a list show the real destination zone instead of whatever free text was
    typed into the address field — the two often disagree.
    """
    if zone_name_map and zone_number:
        return zone_name_map.get(zone_number, '')
    return ''
