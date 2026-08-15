# Purpose: {% bconheader %}…{% endbconheader %} — the one page header every client-dashboard page uses.
# Used by: all templates extending business_dashboard_base.html (business/, orders/, product/ pages).
# Notes: Block tag so a page can put arbitrary action markup in the header's right-hand slot;
#        renders business/parts/_bcon_header.html so the markup exists in exactly one place.

from django import template
from django.template.loader import render_to_string

register = template.Library()


@register.tag(name='bconheader')
def bcon_header(parser, token):
    """Canonical page header — the navy command band.

    Usage::

        {% bconheader eyebrow="Orders" live="Returns" icon="fa-solid fa-rotate-left"
                      title="Returns" subtitle="Manage return requests."
                      readout_label="Open" readout_value=open_total readout_note="of 40" %}
          <a class="bcon__btn bcon__btn--primary" href="…">New return</a>
        {% endbconheader %}

    Every argument is optional except ``title``. The block body — if any —
    becomes the right-hand actions slot; omit it for a header with no actions.
    The optional ``readout_*`` trio prints the page's headline number to the
    left of the actions (live connections, open returns, today's COD…).
    """
    bits = token.split_contents()[1:]
    kwargs = {}
    for bit in bits:
        if '=' not in bit:
            raise template.TemplateSyntaxError(
                "bconheader takes keyword arguments only, got %r" % bit)
        name, _, value = bit.partition('=')
        kwargs[name] = parser.compile_filter(value)
    if 'title' not in kwargs:
        raise template.TemplateSyntaxError("bconheader requires a title")
    nodelist = parser.parse(('endbconheader',))
    parser.delete_first_token()
    return BconHeaderNode(nodelist, kwargs)


class BconHeaderNode(template.Node):
    def __init__(self, nodelist, kwargs):
        self.nodelist = nodelist
        self.kwargs = kwargs

    def render(self, context):
        resolved = {k: v.resolve(context) for k, v in self.kwargs.items()}
        actions = self.nodelist.render(context).strip()
        return render_to_string('business/parts/_bcon_header.html', {
            'eyebrow': resolved.get('eyebrow', ''),
            'live': resolved.get('live', ''),
            'icon': resolved.get('icon', ''),
            'title': resolved.get('title', ''),
            'subtitle': resolved.get('subtitle', ''),
            'subtitle_id': resolved.get('subtitle_id', ''),
            'header_id': resolved.get('header_id', ''),
            'readout_label': resolved.get('readout_label', ''),
            'readout_value': resolved.get('readout_value', ''),
            'readout_note': resolved.get('readout_note', ''),
            'readout_id': resolved.get('readout_id', ''),
            'actions': actions,
        })
