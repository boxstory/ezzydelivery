from django import template

register = template.Library()


@register.filter
def get_item(dictionary, key):
    """Allow dictionary[key] lookups in templates: {{ my_dict|get_item:some_var }}"""
    if dictionary is None:
        return None
    return dictionary.get(key)
