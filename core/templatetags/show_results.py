from django import template

register = template.Library()


@register.inclusion_tag('core/profile.html')
def show_results(msg=5):
    choices = {'business': 'Business', 'driver': 'Driver'}
    return {'choices': choices}
