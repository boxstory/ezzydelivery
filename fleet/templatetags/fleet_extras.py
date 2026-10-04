from django import template

register = template.Library()


@register.filter
def get_item(dictionary, key):
    """Allow dictionary[key] lookups in templates: {{ my_dict|get_item:some_var }}"""
    if dictionary is None:
        return None
    return dictionary.get(key)


@register.filter
def cash_wording(text):
    """Driver-facing wording: the PWA says "Cash", never "COD".

    Transaction type labels and stored descriptions ("COD collected for task …")
    are shared with staff screens, so the driver's copy is reworded at render.
    """
    if not text:
        return text
    return str(text).replace('COD', 'Cash')
