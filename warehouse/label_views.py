"""
Purpose: Staff-only product/variant label printing — QR stickers for product boxes, printed from the inventory page.
Used by: warehouse.urls (print_product_labels, assign_internal_barcodes), warehouse/templates/warehouse/inventory_list.html
Notes: One label per product row is rendered; the print page clones it client-side for the copies count, so a 300-unit receipt is not 300 rows of HTML from the server.
"""

import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import F, Q, Sum
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.safestring import mark_safe

from core.decorators import staff_required
from product import models as product_models
from product.barcode_utils import (
    INTERNAL_PREFIX,
    QR_MODE_CODE,
    QR_MODE_URL,
    QR_MODES,
    assign_internal_barcode,
    generate_qr_svg,
    label_payload,
    variant_line,
)
from warehouse import models as warehouse_models

logger = logging.getLogger('warehouse')

# Distinct products in one print job. Copies are multiplied client-side, so this
# caps the server render, not the number of stickers that come out.
MAX_LABEL_ROWS = 200

# Products one bulk barcode assign will touch. Higher than the print cap because
# nothing is rendered, but still bounded — every row costs a query and a save.
MAX_ASSIGN_ROWS = 1000

# Paper presets. The key drives the .whlb__sheet--<key> class and the @page rule
# of the same name in product-labels.css.
LABEL_PRESETS = [
    ('l38x25', '38 × 25 mm — small box'),
    ('l50x25', '50 × 25 mm — thermal roll'),
    ('l50x30', '50 × 30 mm — with price'),
    ('l100x50', '100 × 50 mm — carton'),
    ('a4_14up', 'A4 sheet — 14 per page (99 × 38 mm)'),
    ('a4_24up', 'A4 sheet — 24 per page (63 × 34 mm)'),
    ('custom', 'Custom size — measure your sheet'),
]
DEFAULT_PRESET = 'l38x25'


def _ids_from(src, key):
    """Digits-only id list out of a GET/POST QueryDict."""
    return [int(v) for v in src.getlist(key) if str(v).isdigit()]


def _copies_map(src):
    """
    Per-product copy counts, sent as repeated `qty=<product_id>:<n>` pairs.

    Used by the receiving flow, where the right number of stickers is the number
    of units that just came in, and that differs per line.
    """
    out = {}
    for raw in src.getlist('qty'):
        product_id, _, count = str(raw).partition(':')
        if product_id.isdigit() and count.isdigit():
            out[int(product_id)] = max(1, min(500, int(count)))
    return out


def _select_all_products(src):
    """
    Every product matching the inventory filters currently on screen.

    Mirrors the filtering in warehouse.views.inventory_list so "print all
    matching" prints exactly the list the operator is looking at, rather than a
    second query that quietly disagrees with it.
    """
    stock_levels = warehouse_models.StockLevel.objects.all()

    warehouse_id = src.get('warehouse')
    if warehouse_id and str(warehouse_id).isdigit():
        stock_levels = stock_levels.filter(warehouse_id=warehouse_id)

    category_id = src.get('category')
    if category_id and str(category_id).isdigit():
        stock_levels = stock_levels.filter(product__product_category_id=category_id)

    business_filter_id = src.get('business')
    if business_filter_id:
        stock_levels = stock_levels.filter(product__business_id=business_filter_id)

    search = (src.get('search') or '').strip()
    if search:
        stock_levels = stock_levels.filter(
            Q(product__item_name__icontains=search) |
            Q(product__item_sku__icontains=search) |
            Q(product__brand_name__icontains=search) |
            Q(product__product_id__icontains=search) |
            Q(product__barcode__icontains=search)
        )

    if src.get('low_stock') == '1':
        stock_levels = stock_levels.filter(
            quantity_on_hand__lte=F('reorder_point') + F('quantity_reserved')
        )

    if src.get('no_barcode') == '1':
        stock_levels = stock_levels.filter(
            Q(product__barcode__isnull=True) | Q(product__barcode='')
        )

    return list(stock_levels.values_list('product_id', flat=True).distinct())


def _resolve_products(src):
    """
    Products to label, from product ids, stock-level ids, a variant group, or the
    whole current filter.

    Returns (products_qs, stock_by_product). Stock rows are carried through so
    the page can default the copies count to what is physically on the shelf and
    print the bin location on the sticker.
    """
    product_ids = _ids_from(src, 'product_ids')
    stock_ids = _ids_from(src, 'stock_ids')

    stock_by_product = {}
    if stock_ids:
        stocks = warehouse_models.StockLevel.objects.filter(
            id__in=stock_ids
        ).select_related('product', 'warehouse', 'location')
        for stock in stocks:
            if stock.product_id:
                stock_by_product[stock.product_id] = stock
                product_ids.append(stock.product_id)

    # "Print every variant of this product" — one click instead of hunting the
    # siblings down a paginated list.
    variant_group = (src.get('variant_group') or '').strip()
    if variant_group:
        product_ids.extend(
            product_models.Product.objects.filter(
                variant_group=variant_group
            ).values_list('id', flat=True)
        )

    if src.get('select_all') in ('1', 'true', 'True'):
        product_ids.extend(_select_all_products(src))

    products = product_models.Product.objects.filter(
        id__in=set(product_ids)
    ).select_related('business', 'color', 'unit', 'product_category')

    return products, stock_by_product


@login_required(login_url='account_login')
@staff_required
def print_product_labels(request):
    """
    Standalone printable QR labels for products and their variants.

    Accepts `product_ids` and/or `stock_ids` (repeatable). Every variant is a
    separate Product row in this codebase, so "print all variants" is simply a
    longer id list from the caller.
    """
    src = request.POST if request.method == 'POST' else request.GET

    products, stock_by_product = _resolve_products(src)
    products = list(products[:MAX_LABEL_ROWS + 1])
    truncated = len(products) > MAX_LABEL_ROWS
    if truncated:
        products = products[:MAX_LABEL_ROWS]

    qr_mode = src.get('qr_mode') or QR_MODE_CODE
    if qr_mode not in dict(QR_MODES):
        qr_mode = QR_MODE_CODE

    preset = src.get('preset') or DEFAULT_PRESET
    if preset not in dict(LABEL_PRESETS):
        preset = DEFAULT_PRESET

    # On-hand across every warehouse, for products reached without a stock row.
    on_hand_map = {}
    if products:
        rows = warehouse_models.StockLevel.objects.filter(
            product_id__in=[p.id for p in products]
        ).values('product_id').annotate(total=Sum('quantity_on_hand'))
        on_hand_map = {r['product_id']: (r['total'] or 0) for r in rows}

    copies_map = _copies_map(src)

    labels = []
    for product in products:
        payload = label_payload(product)
        stock = stock_by_product.get(product.id)

        if qr_mode == QR_MODE_URL:
            qr_data = request.build_absolute_uri(
                reverse('warehouse:stock_card', args=[product.id])
            )
        else:
            qr_data = payload

        barcode = (product.barcode or '').strip()
        labels.append({
            'product': product,
            'payload': payload,
            'qr_svg': mark_safe(generate_qr_svg(qr_data)) if qr_data else '',
            'variant': variant_line(product),
            'on_hand': stock.quantity_on_hand if stock else on_hand_map.get(product.id, 0),
            'location': (stock.location.code if stock and stock.location else ''),
            'warehouse': (stock.warehouse.code if stock and stock.warehouse else ''),
            'is_internal': (not barcode) or barcode.startswith(INTERNAL_PREFIX),
            'no_code': not payload,
            'copies': copies_map.get(product.id),
        })

    # Stamp what was actually rendered. Reprints bump the count rather than being
    # blocked — printing a sticker again is a normal thing to need.
    if labels:
        product_models.Product.objects.filter(
            id__in=[l['product'].id for l in labels]
        ).update(
            label_printed_at=timezone.now(),
            label_print_count=F('label_print_count') + 1,
        )

    context = {
        'labels': labels,
        'presets': LABEL_PRESETS,
        'preset': preset,
        'qr_modes': QR_MODES,
        'qr_mode': qr_mode,
        'truncated': truncated,
        'max_rows': MAX_LABEL_ROWS,
        'has_preset_copies': any(l['copies'] for l in labels),
    }
    return render(request, 'warehouse/print_product_labels.html', context)


@login_required(login_url='account_login')
@staff_required
def assign_internal_barcodes(request):
    """
    Mint internal barcodes for products that have none.

    A label always has something to scan (it falls back to product_id), but a
    product with a real barcode field filled in is what makes receiving and pack
    station scans resolve, so this is offered as an explicit bulk action.
    """
    if request.method != 'POST':
        return redirect('warehouse:inventory_list')

    # The endpoint accepts select_all, and each row costs a uniqueness query plus
    # a save — so it is bounded rather than left to run against a whole catalogue.
    products, _ = _resolve_products(request.POST)
    products = list(products[:MAX_ASSIGN_ROWS])

    assigned, skipped = 0, 0
    for product in products:
        if (product.barcode or '').strip():
            skipped += 1
            continue
        if assign_internal_barcode(product):
            assigned += 1
        else:
            skipped += 1

    if request.headers.get('HX-Request') or request.POST.get('as_json'):
        return JsonResponse({'status': 'ok', 'assigned': assigned, 'skipped': skipped})

    if assigned:
        messages.success(request, f"Assigned internal barcodes to {assigned} product(s).")
    if skipped:
        messages.info(request, f"{skipped} product(s) already had a barcode or could not be coded.")
    return redirect(request.POST.get('next') or 'warehouse:inventory_list')
