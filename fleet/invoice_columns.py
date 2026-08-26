# Purpose: The column registry for the Delivery Charge Invoice document — which columns exist,
#          how each cell is rendered, and which set a given invoice actually shows.
# Used by: workforce.views._charge_invoice_context (staff copy + the column picker) and, through it,
#          business.views.business_charge_invoice (the client's copy).
# Notes: Resolution is invoice override -> client default -> DEFAULT_KEYS, and an empty list at
#        either level means "not set". So an invoice nobody has touched renders exactly the six
#        columns it did before the picker existed. Resolvers take a BusinessChargeInvoiceLine.

from decimal import Decimal


# Column groups, in the order their band appears across the top of the table.
GROUPS = [
    ('delivery', 'Delivery'),
    ('dates', 'Dates'),
    ('money', 'Amount (QAR)'),
]

GROUP_LABELS = dict(GROUPS)


def _order(line):
    task = line.delivery_task
    order = task.order if task else None
    if order and order.order_number:
        return f"#{order.order_number}"
    if task:
        return task.dl_task_number or f"#{task.id}"
    return line.label or '—'


def _client_code(line):
    order = line.delivery_task.order if line.delivery_task else None
    return (order.client_order_code if order else '') or '—'


def _customer(line):
    order = line.delivery_task.order if line.delivery_task else None
    return (order.customer_name if order else '') or '—'


def _phone(line):
    order = line.delivery_task.order if line.delivery_task else None
    return (order.customer_phone if order else '') or '—'


def _area(line):
    """Delivery area and zone as one cell — "Al Aziziya · Z55".

    The order is the source: ``DeliveryTask.dl_to_address`` is an address-update
    override that in practice is never set, so reading only that column would
    leave this cell blank on every line.
    """
    task = line.delivery_task
    if not task:
        return '—'

    addr = task.dl_to_address
    if addr:
        name, zone = (addr.area_name or '').strip(), addr.dl_zone
    else:
        order = task.order
        name = (order.delivery_area_name or '').strip() if order else ''
        zone = order.dl_zone if order else None

    parts = [p for p in [name] if p]
    if zone:
        parts.append(f"Z{zone}")
    return ' · '.join(parts) or '—'


def _service(line):
    task = line.delivery_task
    return ((task.dl_speed or '').strip() if task else '') or '—'


def _awb(line):
    task = line.delivery_task
    return ((task.dl_task_number or '').strip() if task else '') or '—'


def _driver(line):
    task = line.delivery_task
    driver = task.driver if task else None
    if not driver:
        return '—'
    user = driver.profile.user if driver.profile_id and driver.profile else None
    if user:
        return user.get_full_name() or user.username
    return driver.driver_code or f"Driver {driver.driver_id}"


def _pieces(line):
    task = line.delivery_task
    return str(task.dl_waight) if task and task.dl_waight else '—'


def _ordered(line):
    order = line.delivery_task.order if line.delivery_task else None
    date = order.order_date if order else None
    return date.strftime('%d %b %y') if date else '—'


def _delivered(line):
    task = line.delivery_task
    return task.completed_at.strftime('%d %b %y') if task and task.completed_at else '—'


def _dates(line):
    """Both dates in one cell — ordered on top, delivered beneath it.

    Returns the pair, which render_table stacks as two lines. Costs one column
    instead of two on a sheet that runs out of width fast.
    """
    return _ordered(line), _delivered(line)


def _payment(line):
    task = line.delivery_task
    return 'COD' if task and task.cod_collected else 'Prepaid'


def _money(value):
    """Two decimals with thousands separators — the same shape floatformat|intcomma gives."""
    return f"{(value or Decimal('0')):,.2f}"


def _cod(line):
    task = line.delivery_task
    if not task or not task.cod_collected:
        return '—'
    return _money(task.cod_collected_amount)


def _charge(line):
    return _money(line.amount)


# (key, label, group, css, resolver)
INVOICE_COLUMNS = [
    ('order',       'Order',          'delivery', 'bpi__order',              _order),
    ('client_code', 'Client ref',     'delivery', 'bpi__order',              _client_code),
    ('customer',    'Customer',       'delivery', '',                        _customer),
    ('phone',       'Customer phone', 'delivery', 'bpi__date',               _phone),
    ('area',        'Zone / area',    'delivery', 'bpi__area',               _area),
    ('service',     'Service',        'delivery', 'bpi__svc',                _service),
    ('awb',         'Task / AWB',     'delivery', 'bpi__order',              _awb),
    ('driver',      'Driver',         'delivery', '',                        _driver),
    ('pieces',      'Pieces',         'delivery', 'bpi__num',                _pieces),
    ('dates',       'Ordered / Delivered', 'dates', 'bpi__date bpi__date--stack', _dates),
    ('ordered',     'Ordered',        'dates',    'bpi__date',               _ordered),
    ('delivered',   'Delivered',      'dates',    'bpi__date',               _delivered),
    ('payment',     'Payment',        'money',    '',                        _payment),
    ('cod',         'COD',            'money',    'bpi__num bpi__num--cod',  _cod),
    ('charge',      'Charge',         'money',    'bpi__num bpi__num--fee',  _charge),
]

COLUMNS_BY_KEY = {c[0]: c for c in INVOICE_COLUMNS}
VALID_KEYS = set(COLUMNS_BY_KEY)

# An invoice without its money column is not an invoice.
PINNED = {'charge'}

# The only columns that carry a figure into the totals row.
TOTALLED = ['cod', 'charge']

# What the document showed before the picker existed. Unchanged on purpose.
DEFAULT_KEYS = ['order', 'customer', 'delivered', 'payment', 'charge']


def clean_keys(keys):
    """Drop unknown keys, force the pinned ones in, and return them in registry order."""
    chosen = {k for k in (keys or []) if k in VALID_KEYS} | PINNED
    return [c[0] for c in INVOICE_COLUMNS if c[0] in chosen]


def resolve_keys(invoice):
    """The column keys this invoice renders: own override, else client default, else the default set."""
    if invoice.column_keys:
        return clean_keys(invoice.column_keys)
    business = invoice.business
    if business and business.invoice_columns:
        return clean_keys(business.invoice_columns)
    return list(DEFAULT_KEYS)


def resolve_columns(invoice):
    """The full specs for this invoice's columns, in render order."""
    return [COLUMNS_BY_KEY[k] for k in resolve_keys(invoice)]


def picker_groups(selected_keys):
    """The whole registry grouped for the picker UI: [(group_label, [{key,label,checked,pinned}])]."""
    chosen = set(selected_keys)
    out = []
    for group_key, group_label in GROUPS:
        items = [
            {
                'key': key,
                'label': label,
                'checked': key in chosen,
                'pinned': key in PINNED,
            }
            for key, label, group, _css, _fn in INVOICE_COLUMNS if group == group_key
        ]
        if items:
            out.append({'label': group_label, 'items': items})
    return out


def _cell(css, raw):
    """One table cell. A resolver returning a pair gets its second value stacked
    underneath the first, which is how a column carries two figures without
    costing two columns of sheet width."""
    if isinstance(raw, tuple):
        value, sub = raw
    else:
        value, sub = raw, ''
    return {'css': css, 'value': value, 'sub': sub}


def render_table(invoice, delivery_lines):
    """Everything the invoice template needs to draw the line table.

    Precomputed here rather than in the template: the columns are dynamic, and
    resolving them in Django template syntax would mean a tag per column.
    """
    columns = resolve_columns(invoice)
    keys = [c[0] for c in columns]

    header_groups = []
    for group_key, group_label in GROUPS:
        count = sum(1 for c in columns if c[2] == group_key)
        if count:
            header_groups.append({'label': group_label, 'count': count})

    rows = [
        {
            'index': i,
            'cells': [_cell(css, fn(line)) for _k, _l, _g, css, fn in columns],
        }
        for i, line in enumerate(delivery_lines, start=1)
    ]

    # Totals row: one label cell spanning up to the first totalled column (plus the
    # index column), then a cell per remaining column carrying its total or nothing.
    totalled = [k for k in TOTALLED if k in keys]
    first_total_at = min(keys.index(k) for k in totalled) if totalled else len(keys)
    sums = {
        'cod': sum(
            ((l.delivery_task.cod_collected_amount or Decimal('0'))
             for l in delivery_lines
             if l.delivery_task and l.delivery_task.cod_collected),
            Decimal('0'),
        ),
        'charge': sum((l.amount or Decimal('0') for l in delivery_lines), Decimal('0')),
    }
    totals_cells = []
    for key in keys[first_total_at:]:
        _k, _l, _g, css, _fn = COLUMNS_BY_KEY[key]
        totals_cells.append({
            'css': css,
            'value': _money(sums[key]) if key in sums else '',
        })

    # Ten columns will not fit an A4 sheet at the base print size; the modifier
    # tells the stylesheet how hard to squeeze.
    n = len(columns)
    size_class = 'bpi__table--xwide' if n >= 10 else ('bpi__table--wide' if n >= 7 else '')

    return {
        'columns': [{'key': k, 'label': lbl, 'css': css} for k, lbl, _g, css, _fn in columns],
        'column_keys': keys,
        'header_groups': header_groups,
        'rows': rows,
        'totals_label_span': first_total_at + 1,   # +1 for the index column
        'totals_cells': totals_cells,
        'col_count': n + 1,
        'table_size_class': size_class,
        'picker_groups': picker_groups(keys),
        'has_invoice_override': bool(invoice.column_keys),
    }
