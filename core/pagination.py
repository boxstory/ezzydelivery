# Purpose: One paginator for every list page, so ?per_page= and ?page= behave the same everywhere.
# Used by: business, product, delivery, warehouse, dispatch and fleet views; workforce keeps its own older copy.
# Notes: templates get `per_page` and `filter_params` from core.context_processors.pagination_defaults,
#        so a view only needs the page object — it does not have to pass the page size back.

from django.core.paginator import Paginator


VALID_PAGE_SIZES = (10, 25, 50, 100)


def page_size(request, default=50):
    """The page size the user asked for, or `default` if they asked for nonsense.

    Restricted to the four sizes the shared pagination component offers, so a
    crafted ?per_page=100000 cannot be used to pull a whole table in one request.
    """
    raw = request.GET.get('per_page')
    if not raw:
        return default
    try:
        value = int(raw)
    except (ValueError, TypeError):
        return default
    return value if value in VALID_PAGE_SIZES else default


def paginate(request, queryset, default=50, page_param='page'):
    """Return (page_obj, total) for `queryset`.

    `total` is counted before slicing, because list pages show the size of the
    whole filtered result set in their header badge, not the size of the page.

    Out-of-range and non-numeric ?page= values clamp to a real page rather than
    404, which is what a user who deep-links page 9 of a now-shorter list wants.

    `page_param` is for pages that show two independent lists — give the second
    one its own parameter (e.g. 'keys_page') so paging one does not reset the
    other, and pass the matching `page_param` to the pagination component.
    """
    paginator = Paginator(queryset, page_size(request, default))
    return paginator.get_page(request.GET.get(page_param)), paginator.count


def other_params(request, *drop):
    """The current query string minus `per_page` and the named page params.

    A page with two pagers cannot use the global `filter_params` from
    core.context_processors, because each pager has to drop its OWN page
    parameter while keeping the other one — otherwise the link carries the same
    parameter twice and the stale value wins.
    """
    params = request.GET.copy()
    params.pop('per_page', None)
    for key in drop:
        params.pop(key, None)
    return params.urlencode()
