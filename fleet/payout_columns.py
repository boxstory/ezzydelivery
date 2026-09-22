# Purpose: The column registry for the Driver Payout Invoice — which columns exist, how each cell
#          renders, and which set a given payout actually shows.
# Used by: workforce.views._payout_invoice_context (the document + its column picker).
# Notes: Resolution is settlement override -> driver default -> DEFAULT_KEYS, and an empty list at
#        either level means "not set", so a payout nobody has touched renders exactly the four
#        columns it did before the picker existed. COD is deliberately absent: it is the driver's
#        hand-in leg, not money owed, and this document is only ever what the driver is paid.
#        Resolvers take a payout line dict — {'txn', 'task', 'amount'} — built by the view.

from decimal import Decimal


# Column groups, in the order their band appears across the top of the table.
GROUPS = [
    ('work', 'Delivery'),
    ('dates', 'Dates'),
    ('money', 'Amount (QAR)'),
]

GROUP_LABELS = dict(GROUPS)

DASH = '—'


def _order_of(line):
    task = line.get('task')
    return task.order if task and task.order_id else None


def _task(line):
    task = line.get('task')
    if not task:
        return DASH
    return (task.dl_task_number or f"#{task.id}").strip() or DASH


def _order(line):
    order = _order_of(line)
    return f"#{order.order_number}" if order and order.order_number else DASH


def _business(line):
    order = _order_of(line)
    business = order.business if order else None
    return (getattr(business, 'business_name', '') or '').strip() or DASH


def _customer(line):
    order = _order_of(line)
    return ((order.customer_name or '').strip() if order else '') or DASH


def _area(line):
    """Delivery area and zone as one cell — "Al Aziziya · Z55"."""
    order = _order_of(line)
    if not order:
        return DASH
    name = (order.delivery_area_name or '').strip()
    zone = order.dl_zone
    if not name and zone:
        name = (line.get('zone_names') or {}).get(zone, '')
    parts = [p for p in [name] if p]
    if zone:
        parts.append(f"Z{zone}")
    return ' · '.join(parts) or DASH


def _pickup(line):
    """Where the driver's run started — self, hub or transfer.

    The same resolver the payout worksheet's Pickup column uses, so the document
    and the desk that produced it cannot disagree about the same delivery.
    """
    task = line.get('task')
    if not task:
        return DASH
    from delivery.services.pickup import delivery_origin
    origin, _note = delivery_origin(task)
    return origin or DASH


def _km(line):
    order = _order_of(line)
    km = getattr(order, 'route_distance_km', None) if order else None
    return f"{km:.1f}" if km is not None else DASH


def _kind(line):
    txn = line.get('txn')
    return txn.get_transaction_type_display() if txn else DASH


def _details(line):
    txn = line.get('txn')
    if not txn:
        return DASH
    return (txn.description or txn.get_transaction_type_display() or '').strip() or DASH


def _posted(line):
    txn = line.get('txn')
    return txn.created_at.strftime('%d %b %y') if txn and txn.created_at else DASH


def _delivered(line):
    task = line.get('task')
    if task and task.completed_at:
        return task.completed_at.strftime('%d %b %y')
    if task and task.dl_task_date:
        return task.dl_task_date.strftime('%d %b %y')
    return DASH


def _dates(line):
    """Delivered on top, posted beneath — two figures for one column of width."""
    return _delivered(line), _posted(line)


def _money(value):
    """Two decimals with thousands separators — the shape floatformat|intcomma gives."""
    return f"{(value or Decimal('0')):,.2f}"


def _charge(line):
    task = line.get('task')
    price = getattr(task, 'dl_price', None) if task else None
    return _money(price) if price is not None else DASH


def _earning(line):
    return _money(line.get('amount'))


# (key, label, group, css, resolver)
PAYOUT_COLUMNS = [
    ('task',     'Task / AWB',   'work',  'bpi__order',               _task),
    ('order',    'Order',        'work',  'bpi__order',               _order),
    ('business', 'Client',       'work',  '',                         _business),
    ('customer', 'Customer',     'work',  '',                         _customer),
    ('area',     'Zone / area',  'work',  'bpi__area',                _area),
    ('pickup',   'Pickup',       'work',  'bpi__svc',                 _pickup),
    ('km',       'KM',           'work',  'bpi__num',                 _km),
    ('kind',     'Type',         'work',  'bpi__svc',                 _kind),
    ('details',  'Details',      'work',  '',                         _details),
    ('dates',    'Delivered / Posted', 'dates', 'bpi__date bpi__date--stack', _dates),
    ('delivered', 'Delivered',   'dates', 'bpi__date',                _delivered),
    ('date',     'Posted',       'dates', 'bpi__date',                _posted),
    ('charge',   'Client charge', 'money', 'bpi__num',                _charge),
    ('earning',  'Earning',      'money', 'bpi__num bpi__num--cod',   _earning),
]

COLUMNS_BY_KEY = {c[0]: c for c in PAYOUT_COLUMNS}
VALID_KEYS = set(COLUMNS_BY_KEY)

# A payout document without the figure being paid is not a payout document.
PINNED = {'earning'}

# The only columns that carry a figure into the totals row.
TOTALLED = ['charge', 'earning']

# What the document showed before the picker existed. Unchanged on purpose.
DEFAULT_KEYS = ['task', 'details', 'date', 'earning']


def clean_keys(keys):
    """Drop unknown keys, force the pinned ones in, and return them in registry order."""
    chosen = {k for k in (keys or []) if k in VALID_KEYS} | PINNED
    return [c[0] for c in PAYOUT_COLUMNS if c[0] in chosen]


def resolve_keys(settlement):
    """The column keys this payout renders: own override, else driver default, else the default set."""
    if settlement.column_keys:
        return clean_keys(settlement.column_keys)
    driver = settlement.driver
    if driver and driver.payout_columns:
        return clean_keys(driver.payout_columns)
    return list(DEFAULT_KEYS)


def resolve_columns(settlement):
    """The full specs for this payout's columns, in render order."""
    return [COLUMNS_BY_KEY[k] for k in resolve_keys(settlement)]


def picker_groups(selected_keys):
    """The whole registry grouped for the picker UI: [{label, items:[{key,label,checked,pinned}]}]."""
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
            for key, label, group, _css, _fn in PAYOUT_COLUMNS if group == group_key
        ]
        if items:
            out.append({'label': group_label, 'items': items})
    return out


def _prime_zone_names(lines):
    """Hand every line the zone-number -> name map its area cell may need.

    One query for the sheet rather than one per line, the same way the charge
    invoice primes its own.
    """
    zones = set()
    for line in lines:
        order = _order_of(line)
        if order and order.dl_zone:
            zones.add(order.dl_zone)
    names = {}
    if zones:
        from delivery.models import ZoneName
        names = {
            z.zone_number: (z.zone_name or '').strip()
            for z in ZoneName.objects.filter(zone_number__in=zones)
        }
    for line in lines:
        line['zone_names'] = names
    return names


def _cell(css, raw):
    """One table cell. A resolver returning a pair gets its second value stacked
    underneath the first, which is how a column carries two figures without
    costing two columns of sheet width."""
    if isinstance(raw, tuple):
        value, sub = raw
    else:
        value, sub = raw, ''
    return {'css': css, 'value': value, 'sub': sub}


def render_table(settlement, lines):
    """Everything the payout invoice template needs to draw the line table.

    Precomputed here rather than in the template: the columns are dynamic, and
    resolving them in Django template syntax would mean a tag per column.
    """
    columns = resolve_columns(settlement)
    keys = [c[0] for c in columns]

    _prime_zone_names(lines)

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
        for i, line in enumerate(lines, start=1)
    ]

    # Totals row: one label cell spanning up to the first totalled column (plus
    # the index column), then a cell per remaining column carrying its total or
    # nothing.
    totalled = [k for k in TOTALLED if k in keys]
    first_total_at = min(keys.index(k) for k in totalled) if totalled else len(keys)
    sums = {
        'charge': sum(
            ((line['task'].dl_price or Decimal('0'))
             for line in lines
             if line.get('task') and line['task'].dl_price is not None),
            Decimal('0'),
        ),
        'earning': sum((line.get('amount') or Decimal('0') for line in lines), Decimal('0')),
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
        'table_size_class': size_class,
        'col_count': n + 1,                        # +1 for the index column
    }
