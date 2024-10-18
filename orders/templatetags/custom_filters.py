# your_app/templatetags/custom_filters.py
from django import template

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