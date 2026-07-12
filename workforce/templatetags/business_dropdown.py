# Purpose: Template filter to order business/seller dropdowns with coded ones first.
# Used by: business/seller filter <select> dropdowns across workforce, warehouse, business apps.
# Notes: Businesses without a business_code are pushed to the end of the list.

from django import template

register = template.Library()


@register.filter
def code_last(businesses):
    """Sort businesses so those WITH a business_code come first (ordered by code),
    and those WITHOUT a code are listed last (ordered by name)."""
    try:
        items = list(businesses)
    except TypeError:
        return businesses

    def resolve(b):
        # Support both Business objects and wrappers that hold a .business relation.
        if getattr(b, 'business_code', None) or getattr(b, 'business_name', None):
            return b
        return getattr(b, 'business', b)

    def sort_key(b):
        obj = resolve(b)
        code = (getattr(obj, 'business_code', None) or '').strip()
        has_code = 0 if code else 1
        name = (getattr(obj, 'business_name', '') or '').lower()
        return (has_code, code.lower() if code else name)

    return sorted(items, key=sort_key)
