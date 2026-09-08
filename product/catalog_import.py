"""
Purpose: Shared matching + update rules for API product imports (client wizard and staff seller page).
Used by: product.views.product_api_import, workforce.views.seller_api_products_import.
Notes: Blank API values never overwrite existing data — a merchant's local edit outranks an empty field.
"""
import logging

logger = logging.getLogger('product')

# Fields refreshed from the store in update mode, in (model field, payload key) form.
UPDATABLE_TEXT_FIELDS = (
    ('item_name', 'item_name'),
    ('brand_name', 'brand_name'),
    ('barcode', 'barcode'),
    ('size', 'size'),
    ('item_discription', 'item_discription'),
)


def find_existing_product(product_model, business, sku, variant_id='', platform_id=''):
    """Locate the catalogue row this API product already corresponds to.

    Matches on SKU first. Falls back to the auto-generated `EZ-{platform id}`
    form so a merchant who *later* sets a real SKU in Shopify updates the
    existing row instead of creating a second copy of the same product.
    Returns the Product or None.
    """
    qs = product_model.objects.filter(business=business)

    if sku:
        match = qs.filter(item_sku=sku).first()
        if match:
            return match

    for ext_id in (variant_id, platform_id):
        ext_id = (ext_id or '').strip()
        if ext_id:
            match = qs.filter(item_sku=f'EZ-{ext_id}').first()
            if match:
                return match

    return None


def update_product_fields(product, values, new_sku=''):
    """Refresh a product from API values. Returns True when something changed.

    Only non-empty incoming values are written: an API that returns a blank
    vendor or description must not wipe what the merchant typed locally.
    """
    changed = []

    for field, key in UPDATABLE_TEXT_FIELDS:
        incoming = (values.get(key) or '').strip()[:100]
        if incoming and getattr(product, field, None) != incoming:
            setattr(product, field, incoming)
            changed.append(field)

    # Price is numeric — treat 0/unparseable as "no price supplied" rather than
    # as an instruction to zero out the catalogue price.
    try:
        price_val = int(float(values.get('item_price') or 0))
    except (ValueError, TypeError):
        price_val = 0
    if price_val > 0 and product.item_price != price_val:
        product.item_price = price_val
        changed.append('item_price')

    # A real SKU arriving for a row that was auto-numbered replaces the EZ- one.
    new_sku = (new_sku or '').strip()[:100]
    if new_sku and new_sku != product.item_sku:
        product.item_sku = new_sku
        changed.append('item_sku')

    if changed:
        product.save()
        logger.info('Updated product %s from API: %s', product.pk, ', '.join(changed))
    return bool(changed)
