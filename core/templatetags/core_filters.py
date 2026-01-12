# core/templatetags/core_filters.py
from django import template

from datetime import datetime, timedelta

register = template.Library()

@register.filter
def product_name(index):
    return f'ordered_product.product0{index}_name'

@register.filter
def product_qty(index):
    return f'ordered_product.product0{index}_qty'


@register.filter
def get_field(obj, field_name):
    return getattr(obj, field_name, '')



@register.filter
def days_ago(days):
    return (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')


@register.filter
def mul(value, arg):
    """Multiply the value by the argument."""
    try:
        return float(value) * float(arg)
    except (ValueError, TypeError):
        return 0


@register.filter
def div(value, arg):
    """Divide the value by the argument."""
    try:
        if float(arg) == 0:
            return 0
        return float(value) / float(arg)
    except (ValueError, TypeError):
        return 0
