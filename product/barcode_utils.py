"""
Purpose: Scannable-code helpers for product labels — payload resolution, internal barcode assignment, QR SVG rendering.
Used by: warehouse.label_views (product label printing), warehouse.views (inventory list barcode state)
Notes: QR is emitted as inline SVG (merged module runs, crispEdges) so the thermal head rasterises hard edges itself.
"""

import logging
from html import escape

logger = logging.getLogger(__name__)

# An internal code we minted ourselves, as opposed to a manufacturer EAN/UPC the
# seller supplied. Kept short so it still scans at 38mm.
INTERNAL_PREFIX = 'EZ'

# QR content modes offered on the print page.
QR_MODE_CODE = 'code'   # the bare payload — scans into any SKU/barcode input
QR_MODE_URL = 'url'     # absolute link to the stock card — for phone scans
QR_MODES = [
    (QR_MODE_CODE, 'Code only (warehouse scanners)'),
    (QR_MODE_URL, 'Link to stock card (phone camera)'),
]


def label_payload(product):
    """
    The code that identifies this variant on its sticker.

    Prefers the seller's own barcode (EAN/UPC) so a label matches whatever is
    already printed on the manufacturer's box; falls back to product_id, which
    is unique per product and always present.
    """
    barcode = (getattr(product, 'barcode', '') or '').strip()
    if barcode:
        return barcode
    return (getattr(product, 'product_id', '') or '').strip()


def has_scannable_code(product):
    """False when a product would print a label with nothing to scan."""
    return bool(label_payload(product))


def internal_barcode_for(product):
    """
    Derive a stable internal code from product_id without touching the database.

    Modern product_ids are `{business_pk}-{counter:05d}`, and dropping the dash
    keeps those unique because the counter is always exactly 5 digits — business
    3/counter 1 ("300001") cannot collide with business 30/counter 1 ("3000001"),
    the lengths differ. Legacy rows predate that format (bare "001660"), so the
    derivation alone is not a uniqueness proof; assign_internal_barcode() checks
    the database before writing.
    """
    product_id = (getattr(product, 'product_id', '') or '').strip()
    if not product_id:
        return ''
    return f"{INTERNAL_PREFIX}{product_id.replace('-', '')}"


def assign_internal_barcode(product, save=True, overwrite=False):
    """
    Write an internal barcode onto a product that has none.

    Returns the code in use, or '' when one could not be derived. Existing
    barcodes are left alone unless overwrite=True — a seller's real EAN is not
    ours to replace.
    """
    from product.models import Product

    existing = (getattr(product, 'barcode', '') or '').strip()
    if existing and not overwrite:
        return existing

    code = internal_barcode_for(product)
    if not code:
        logger.warning("Cannot assign internal barcode: product %s has no product_id", product.pk)
        return ''

    # Guard against a seller having typed this exact string in by hand.
    candidate = code
    suffix = 1
    while Product.objects.filter(barcode=candidate).exclude(pk=product.pk).exists():
        candidate = f"{code}-{suffix}"
        suffix += 1
        if suffix > 99:
            logger.error("Could not find a free internal barcode for product %s", product.pk)
            return ''

    product.barcode = candidate
    if save:
        try:
            product.save(update_fields=['barcode', 'updated_at'])
        except Exception as e:
            # Product.save() rejects a blank SKU on fulfillment-enabled sellers.
            # One unsaveable row must not abort a bulk assign.
            logger.error("Could not save internal barcode for product %s: %s", product.pk, e)
            product.barcode = existing or None
            return ''
    return candidate


def generate_qr_svg(data, quiet_zone=4, error_correction='M'):
    """
    Build a QR code as inline SVG markup that stretches to its container.

    Same reasoning as delivery.label_utils.generate_barcode_svg: a rasterised QR
    scaled to a 20mm box gets resampled by the browser and the module edges go
    grey, which a 203dpi thermal head then prints as mush. Emitting a unitless
    viewBox with shape-rendering="crispEdges" hands rasterisation to the printer.

    quiet_zone is in modules (the QR spec wants >= 4). Returns an SVG string, or
    '' if the data cannot be encoded.
    """
    import qrcode
    from qrcode import constants

    levels = {
        'L': constants.ERROR_CORRECT_L,
        'M': constants.ERROR_CORRECT_M,
        'Q': constants.ERROR_CORRECT_Q,
        'H': constants.ERROR_CORRECT_H,
    }

    payload = str(data or '').strip()
    if not payload:
        return ''

    try:
        qr = qrcode.QRCode(
            version=None,
            error_correction=levels.get(error_correction, constants.ERROR_CORRECT_M),
            box_size=1,
            border=max(0, int(quiet_zone)),
        )
        qr.add_data(payload)
        qr.make(fit=True)
        matrix = qr.get_matrix()  # includes the quiet zone
    except Exception as e:
        logger.error("Error generating QR SVG for %r: %s", payload, e)
        return ''

    if not matrix:
        return ''

    size = len(matrix)
    rects = []
    for y, row in enumerate(matrix):
        run_start = None
        for x, module in enumerate(row):
            if module:
                if run_start is None:
                    run_start = x
            elif run_start is not None:
                rects.append(f'<rect x="{run_start}" y="{y}" width="{x - run_start}" height="1"/>')
                run_start = None
        if run_start is not None:
            rects.append(f'<rect x="{run_start}" y="{y}" width="{size - run_start}" height="1"/>')

    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {size} {size}" '
        f'shape-rendering="crispEdges" role="img" '
        f'aria-label="{escape(payload, quote=True)}">'
        f'<rect x="0" y="0" width="{size}" height="{size}" fill="#fff"/>'
        f'<g fill="#000">{"".join(rects)}</g>'
        f'</svg>'
    )


def variant_line(product):
    """
    Human-readable variant descriptor for the label: "Red / L / 500g".

    A stored variant_label wins; otherwise it is rebuilt from the flattened
    variant fields on Product (colour FK, free-text size, unit FK) — this
    codebase has no separate variant model.
    """
    stored = (getattr(product, 'variant_label', '') or '').strip()
    if stored:
        return stored

    bits = []
    color = getattr(product, 'color', None)
    if color and getattr(color, 'color_variant', ''):
        bits.append(str(color.color_variant))
    size = (getattr(product, 'size', '') or '').strip()
    if size:
        bits.append(size)
    unit = getattr(product, 'unit', None)
    if unit and getattr(unit, 'unit_variant', ''):
        bits.append(str(unit.unit_variant))
    return ' / '.join(bits)
