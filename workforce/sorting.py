# Purpose: Server-side column sorting for staff list tables — one whitelist per page, one URL convention.
# Used by: workforce.views.pricing_inquiries_list, workforce.crm_views._render_leads_list, parts/components/_sort_th.html
# Notes: `?sort=key` ascends, `?sort=-key` descends. A key that is not in the page's whitelist falls back to
#        that page's default, so a hand-edited URL can never order by an arbitrary column or crash the page.

from collections import namedtuple

from django.db.models import F
from django.db.models.expressions import Combinable

# What the header cells render from: `value` goes back into the URL, `key` says
# which column carries the arrow and `descending` says which way it points.
Sort = namedtuple('Sort', 'value key descending')


def _as_expression(field):
    """A whitelist entry is either a column name or a ready-made expression
    (Lower(), Case(), Coalesce()). Both have to end up orderable."""
    return F(field) if isinstance(field, str) else field


def apply_sort(queryset, raw, mapping, default):
    """Order `queryset` by the requested column and return (queryset, Sort).

    `mapping` is {url key: (field or expression, ...)} — the whitelist. `default`
    is the url key the page falls back to, `-` prefixed when its natural reading
    is newest/biggest first. The returned Sort is what the header cells compare
    against, so the arrow can never disagree with the rows underneath it.

    Blanks and NULLs are pushed to the end in both directions: an unassigned lead
    or an unquoted inquiry is missing data, and it reads the same way whichever
    end of the column you are looking at. Ties break on -pk so paging is stable.
    """
    raw = (raw or '').strip()
    key, descending = raw.lstrip('-'), raw.startswith('-')
    if key not in mapping:
        key, descending = default.lstrip('-'), default.startswith('-')

    order = []
    for field in mapping[key]:
        expression = _as_expression(field)
        if isinstance(expression, Combinable):
            order.append(expression.desc(nulls_last=True) if descending
                         else expression.asc(nulls_last=True))
        else:
            order.append(expression)
    order.append('-pk')

    value = f'-{key}' if descending else key
    return queryset.order_by(*order), Sort(value, key, descending)
