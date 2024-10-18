from django import template
from django.urls import reverse

register = template.Library()

@register.navigation_tags
def is_active_url(request, url_name):
    return "active" if request.path == reverse(url_name) else ""
