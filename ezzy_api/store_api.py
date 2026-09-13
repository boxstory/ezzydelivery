# Purpose: REST endpoints a seller's own website posts orders into (custom storefronts, no Shopify/Woo plugin).
# Used by: ezzy_api/urls.py — /api/v1/store/ping|orders/ ; authenticated by ClientApiKey (Bearer / X-API-Key).
# Notes: Tenant is ALWAYS the key's own business, never a body field. Idempotent on
#        (business, client_order_code) so a storefront retry cannot double-create an order.

import logging
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from business import models as business_models
from business.suspension import REFUSAL_MESSAGES, write_refusal_code
from ezzy_api.json_paths import path_get
from ezzy_api.models import ClientApiKey
from ezzy_api.permissions import ApiKeyScopePermission
from orders import models as orders_models
from product import models as product_models

logger = logging.getLogger('ezzy_api')

# Payment methods that mean "the driver collects the money". Anything else
# (card, applepay, googlepay, tap, myfatoorah, ...) is already paid online, so
# the COD amount must be zero — billing a prepaid order as COD makes the driver
# ask the customer to pay twice and corrupts the seller's settlement.
COD_PAYMENT_METHODS = {
    'cod', 'cash', 'cash_on_delivery', 'cashondelivery', 'cash-on-delivery',
    'collect', 'collect_on_delivery', 'pay_on_delivery', 'payondelivery',
}

MAX_ITEMS = 50


# Mapping target -> how the create view consumes it. The keys are the same ones
# every other import source uses (workforce.views.IMPORT_FIELD_LABELS), so staff
# learn one field list rather than one per platform.
MAPPED_SCALARS = (
    'client_order_code', 'platform_id', 'order_date', 'customer_name',
    'customer_phone', 'customer_whatsapp', 'customer_address', 'dl_landmark',
    'dl_zone', 'dl_street', 'dl_building', 'dl_latitude', 'dl_longitude',
    'package_desc', 'package_qty', 'cod_amount', 'payment_method',
    'cod_status_by_client', 'dl_amount', 'seller_notes',
)
MAX_MAPPED_LINES = 10


def _store_mapping(business):
    """The field mapping staff saved for this seller's custom integration.

    Empty dict when none is configured — the built-in camelCase/snake_case
    guesses then carry the payload, which is what every storefront got before
    mappings existed.
    """
    api = (
        business_models.BusinessApiSettings.objects
        .filter(business=business, api_type='custom')
        .exclude(column_mapping=None)
        .order_by('-is_default', 'id')
        .first()
    )
    mapping = getattr(api, 'column_mapping', None)
    return mapping if isinstance(mapping, dict) else {}


def _apply_mapping(payload, mapping):
    """Pull every mapped target out of the payload. Unmapped targets are absent
    rather than empty, so the caller can tell "mapped to nothing" from "not
    mapped" and fall back to the built-in guess only for the latter."""
    resolved = {}
    for target in MAPPED_SCALARS:
        source = mapping.get(target)
        if not source:
            continue
        value = path_get(payload, source)
        if isinstance(value, list):
            value = ', '.join(str(v) for v in value if v not in (None, ''))
        if value not in (None, ''):
            resolved[target] = value
    return resolved


def _mapped_lines(payload, mapping):
    """Order lines built from the product_N / count_N mapping targets.

    A path with '[]' resolves to every element at once, so mapping
    product_1 -> items[].name and count_1 -> items[].qty carries a whole
    variable-length basket through two fields. Indexed targets
    (product_1 -> items[0].name, product_2 -> items[1].name) still work for a
    storefront that flattens its lines.
    """
    lines = []
    for n in range(1, MAX_MAPPED_LINES + 1):
        name_path = mapping.get(f'product_{n}')
        if not name_path:
            continue
        names = path_get(payload, name_path)
        qtys = path_get(payload, mapping.get(f'count_{n}', ''))
        skus = path_get(payload, mapping.get('sku', ''))

        if isinstance(names, list):
            for i, item_name in enumerate(names[:MAX_ITEMS]):
                lines.append({
                    'name': item_name,
                    'qty': qtys[i] if isinstance(qtys, list) and i < len(qtys) else qtys,
                    'sku': skus[i] if isinstance(skus, list) and i < len(skus) else skus,
                })
        elif names not in (None, ''):
            lines.append({
                'name': names,
                'qty': qtys[0] if isinstance(qtys, list) and qtys else qtys,
                'sku': skus[0] if isinstance(skus, list) and skus else skus,
            })
    return [ln for ln in lines if str(ln.get('name') or '').strip()][:MAX_ITEMS]


def _resolve_business(request):
    """The business this request may write to.

    For a ClientApiKey the owner is the key itself — never the user's first
    business, which differs when one login owns more than one store.
    """
    api_key = getattr(request, 'auth', None)
    if isinstance(api_key, ClientApiKey):
        return api_key.business
    return (
        business_models.Business.objects
        .filter(user_id=request.user.id)
        .order_by('business_id')
        .first()
    )


def _fit(model, field_name, value):
    """Clamp a payload value to the column width (see ezzy_api.views._fit)."""
    s = '' if value is None else str(value).strip()
    max_len = model._meta.get_field(field_name).max_length
    return s[:max_len] if max_len else s


def _decimal(value, default=Decimal('0')):
    if value is None or value == '':
        return default
    try:
        return Decimal(str(value).replace(',', '').strip())
    except (InvalidOperation, ValueError, TypeError):
        return default


def _money(value):
    """Always a 2-decimal string. ``value or 0`` is not a safe default here:
    Decimal('0.00') is falsy, so a zero amount used to serialize as "0" while
    every other amount came back as "65.00" — the same field in two shapes."""
    amount = Decimal('0') if value is None else Decimal(str(value))
    return f'{amount:.2f}'


def _int_or_none(value):
    """Qatar zone / street / building are numeric columns; text addresses stay text."""
    if value is None or value == '':
        return None
    digits = ''.join(ch for ch in str(value) if ch.isdigit())
    if not digits:
        return None
    try:
        n = int(digits)
    except ValueError:
        return None
    return n if 0 < n < 2147483647 else None


def _normalize_phone(raw):
    """Local 8-digit Qatar form, matching every other order in the system."""
    digits = ''.join(ch for ch in str(raw or '') if ch.isdigit())
    if digits.startswith('00'):
        digits = digits[2:]
    if len(digits) > 8 and digits.startswith('974'):
        digits = digits[3:]
    return digits


def _compose_address(cust):
    """One human address line out of the storefront's separate address fields."""
    parts = []
    building = str(cust.get('buildingNumber') or cust.get('building') or '').strip()
    btype = str(cust.get('buildingType') or '').strip()
    if building:
        parts.append(f"{btype or 'Building'} {building}".strip())
    for key in ('street', 'address', 'address1', 'block', 'area', 'zone_name', 'city'):
        val = str(cust.get(key) or '').strip()
        if val and val not in parts:
            parts.append(val)
    return ', '.join(parts)


def _is_cod(payload):
    method = str(payload.get('paymentMethod') or payload.get('payment_method') or '').strip().lower()
    method = method.replace(' ', '_')
    if method in COD_PAYMENT_METHODS:
        return True
    # An explicit flag wins when the storefront sends one.
    flag = payload.get('cod') if 'cod' in payload else payload.get('is_cod')
    if isinstance(flag, bool):
        return flag
    return False


def _match_product(business, name, sku):
    """Link the line to the seller's catalogue when it is unambiguous.

    Exact SKU / barcode / name only — a fuzzy guess here would silently move
    stock for the wrong product, and an unlinked line still delivers fine.
    """
    qs = product_models.Product.objects.filter(business=business)
    for lookup in (
        {'item_sku__iexact': sku} if sku else None,
        {'barcode__iexact': sku} if sku else None,
        {'item_name__iexact': name} if name else None,
    ):
        if not lookup:
            continue
        found = qs.filter(**lookup).first()
        if found:
            return found
    return None


def _parse_date(value):
    if not value:
        return None
    parsed = None
    try:
        from django.utils.dateparse import parse_datetime, parse_date
        parsed = parse_datetime(str(value))
        if parsed is None:
            parsed = parse_date(str(value)[:10])
            return parsed
    except (ValueError, TypeError):
        return None
    if parsed is None:
        return None
    if timezone.is_aware(parsed):
        parsed = timezone.localtime(parsed)
    return parsed.date()


def _order_state(order):
    """Public status snapshot: what the storefront may show its customer."""
    task = order.delivery_task.order_by('-id').first()
    data = {
        'order_number': order.order_number,
        'client_order_code': order.client_order_code,
        'order_status': order.order_status,
        'order_status_label': order.get_order_status_display(),
        'cod_amount': _money(order.cod_amount),
        'cod_status': order.cod_status_by_client or '',
        'delivery_status': '',
        'delivery_status_label': '',
        'driver_name': '',
        'tracking_url': '',
        'delivered_at': order.delivered_at.isoformat() if order.delivered_at else None,
        'created_at': order.created_at.isoformat() if order.created_at else None,
    }
    if task:
        data['delivery_status'] = task.dl_task_status or ''
        data['delivery_status_label'] = task.get_dl_task_status_display() or ''
        if task.driver:
            data['driver_name'] = str(task.driver)
        token = getattr(task, 'tracking_token', '')
        if token:
            data['tracking_url'] = f'https://ezzydelivery.qa/track/{token}/'
    return data


def _order_detail(order):
    """Everything we hold on one order, for the seller that sent it.

    The status snapshot plus the customer, the lines and the money — so a
    storefront can reconcile against its own record without keeping a second
    copy of what it posted. ``received`` is the untouched payload we were sent,
    which is what settles an "I sent you X" dispute.
    """
    data = _order_state(order)
    data['order_date'] = order.order_date.isoformat() if order.order_date else None

    items = list(order.order_items.all())
    data['customer'] = {
        'name': order.customer_name,
        'phone': order.customer_phone,
        'whatsapp': order.customer_whatsapp,
        'address': order.customer_address,
        'zone': order.dl_zone,
        'street': order.dl_street,
        'building': order.dl_building,
        'area': order.delivery_area_name or '',
        'notes': order.order_notes or '',
        'latitude': str(order.latitude) if order.latitude is not None else None,
        'longitude': str(order.longitude) if order.longitude is not None else None,
        'address_verified': order.address_verified,
    }
    data['items'] = [
        {
            'name': item.display_name,
            'sku': item.display_sku,
            'qty': item.quantity,
            'unit_price': _money(item.unit_price) if item.unit_price is not None else None,
            'line_total': _money(item.total_price) if item.total_price is not None else None,
        }
        for item in items
    ]
    data['amounts'] = {
        # What we hold, under honest names: we store the delivery fee and the
        # COD amount, and the line total is derived from the lines themselves.
        'items_total': _money(sum((i.total_price or Decimal('0')) for i in items)),
        'delivery_fee': _money(order.dl_amount),
        'cod_amount': _money(order.cod_amount),
    }
    data['package'] = {
        'description': order.package_description or '',
        'qty': order.package_qty,
    }
    data['received'] = order.original_order_data if isinstance(order.original_order_data, dict) else None
    return data


@api_view(['GET'])
@permission_classes([IsAuthenticated, ApiKeyScopePermission])
def store_ping(request):
    """Credential check — lets an integrator confirm the key before going live."""
    business = _resolve_business(request)
    if not business:
        return Response({'success': False, 'error': 'No business is associated with this key'},
                        status=status.HTTP_403_FORBIDDEN)
    api_key = getattr(request, 'auth', None)
    return Response({
        'success': True,
        'business': business.business_name,
        'business_code': business.business_code or '',
        'account_status': business.business_status,
        'can_create_orders': write_refusal_code(business) is None,
        'scope': api_key.scope if isinstance(api_key, ClientApiKey) else 'session',
        'server_time': timezone.now().isoformat(),
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated, ApiKeyScopePermission])
def store_create_order(request):
    """Create one delivery order from a storefront checkout.

    Accepts the storefront's own camelCase shape (orderNumber / customer{} /
    items[]) as well as our snake_case field names. The order lands in
    'to_review' like every other imported order — staff confirm it before it
    becomes a delivery task.
    """
    business = _resolve_business(request)
    if not business:
        return Response({'success': False, 'error': 'No business is associated with this key'},
                        status=status.HTTP_403_FORBIDDEN)

    refusal = write_refusal_code(business)
    if refusal:
        return Response({'success': False, 'error': REFUSAL_MESSAGES[refusal], 'code': refusal},
                        status=status.HTTP_403_FORBIDDEN)

    payload = request.data
    if not isinstance(payload, dict):
        return Response({'success': False, 'error': 'Body must be a single JSON order object'},
                        status=status.HTTP_400_BAD_REQUEST)

    # A saved mapping wins wherever staff set one; the built-in guesses below
    # fill everything they left unmapped.
    mapping = _store_mapping(business)
    mapped = _apply_mapping(payload, mapping) if mapping else {}

    code = str(
        mapped.get('client_order_code')
        or payload.get('orderNumber')
        or payload.get('order_number')
        or payload.get('client_order_code')
        or payload.get('id')
        or ''
    ).strip()
    if not code:
        return Response({'success': False, 'error': 'orderNumber is required'},
                        status=status.HTTP_400_BAD_REQUEST)

    cust = payload.get('customer')
    if not isinstance(cust, dict):
        cust = {}

    name = str(mapped.get('customer_name') or cust.get('name') or payload.get('customer_name') or '').strip()
    phone = _normalize_phone(
        mapped.get('customer_phone') or cust.get('phone') or payload.get('customer_phone')
    )
    if not name:
        return Response({'success': False, 'error': 'customer.name is required'},
                        status=status.HTTP_400_BAD_REQUEST)
    if len(phone) < 7:
        return Response({'success': False, 'error': 'customer.phone must be a valid Qatar mobile number'},
                        status=status.HTTP_400_BAD_REQUEST)

    address = str(mapped.get('customer_address') or '').strip()
    if not address:
        address = _compose_address(cust) or str(payload.get('customer_address') or '').strip()
    landmark = str(mapped.get('dl_landmark') or '').strip()
    if landmark and landmark not in address:
        address = f'{address}, {landmark}'.strip(', ')
    if not address:
        return Response({'success': False, 'error': 'customer address (area/street/building) is required'},
                        status=status.HTTP_400_BAD_REQUEST)

    # Idempotency: a storefront that retries a timed-out POST must not create a
    # second delivery for the same checkout.
    existing = orders_models.Order.objects.filter(
        business=business, client_order_code=code,
    ).order_by('-id').first()
    if existing:
        body = _order_state(existing)
        body.update({'success': True, 'duplicate': True,
                     'message': 'Order already received'})
        return Response(body, status=status.HTTP_200_OK)

    items = _mapped_lines(payload, mapping) if mapping else []
    if not items:
        raw_items = payload.get('items')
        if not isinstance(raw_items, list):
            raw_items = payload.get('line_items') if isinstance(payload.get('line_items'), list) else []
        items = [i for i in raw_items if isinstance(i, dict)][:MAX_ITEMS]

    if 'cod_amount' in mapped:
        total = _decimal(mapped['cod_amount'])
    else:
        total = _decimal(payload.get('total'))
        if not total:
            total = _decimal(payload.get('subtotal')) + _decimal(payload.get('deliveryFee'))

    if 'payment_method' in mapped or 'cod_status_by_client' in mapped:
        is_cod = _is_cod({
            'paymentMethod': mapped.get('payment_method', ''),
            'cod': mapped.get('cod_status_by_client', ''),
        })
    else:
        is_cod = _is_cod(payload)

    desc_parts, qty_total = [], 0
    for it in items:
        item_name = str(it.get('name') or it.get('title') or it.get('product_name') or '').strip()
        qty = _int_or_none(it.get('qty') if it.get('qty') is not None else it.get('quantity')) or 1
        qty_total += qty
        if item_name:
            desc_parts.append(f'{item_name} x{qty}')
    package_desc = (
        str(mapped.get('package_desc') or '').strip()
        or ', '.join(desc_parts)
        or str(payload.get('package_description') or '').strip()
    )
    if 'package_qty' in mapped:
        qty_total = _int_or_none(mapped['package_qty']) or qty_total

    notes = str(
        mapped.get('seller_notes')
        or cust.get('notes') or payload.get('notes') or payload.get('order_notes') or ''
    ).strip()

    try:
        with transaction.atomic():
            order = orders_models.Order.objects.create(
                business=business,
                client_order_code=_fit(orders_models.Order, 'client_order_code', code),
                customer_name=_fit(orders_models.Order, 'customer_name', name),
                customer_phone=_fit(orders_models.Order, 'customer_phone', phone),
                customer_whatsapp=_fit(
                    orders_models.Order, 'customer_whatsapp',
                    _normalize_phone(mapped.get('customer_whatsapp') or cust.get('whatsapp')) or phone),
                customer_address=_fit(orders_models.Order, 'customer_address', address),
                dl_zone=_int_or_none(mapped.get('dl_zone') or cust.get('zone') or cust.get('zoneNumber')),
                dl_street=_int_or_none(mapped.get('dl_street') or cust.get('streetNumber') or cust.get('street_no')),
                dl_building=_int_or_none(
                    mapped.get('dl_building') or cust.get('buildingNumber') or cust.get('building')),
                order_notes=_fit(orders_models.Order, 'order_notes', notes),
                package_description=_fit(orders_models.Order, 'package_description', package_desc),
                package_qty=qty_total,
                cod_amount=total if is_cod else Decimal('0'),
                cod_status_by_client='unpaid' if is_cod else 'online_paid',
                dl_amount=_decimal(
                    mapped.get('dl_amount') or payload.get('deliveryFee') or payload.get('delivery_fee')),
                order_status='to_review',
                platform='api',
                platform_id=_fit(orders_models.Order, 'platform_id', mapped.get('platform_id') or code),
                original_order_data=payload,
            )

            for it in items:
                item_name = str(it.get('name') or it.get('title') or it.get('product_name') or '').strip()
                if not item_name:
                    continue
                sku = str(it.get('sku') or it.get('id') or '').strip()
                qty = _int_or_none(it.get('qty') if it.get('qty') is not None else it.get('quantity')) or 1
                unit = _decimal(it.get('price') if it.get('price') is not None else it.get('unit_price'), None)
                if unit is None:
                    line = _decimal(it.get('lineTotal') or it.get('total'))
                    unit = (line / qty) if qty else line
                orders_models.OrderItem.objects.create(
                    order=order,
                    product=_match_product(business, item_name, sku),
                    quantity=qty,
                    unit_price=unit,
                    notes=_fit(orders_models.OrderItem, 'notes', item_name),
                )
    except Exception as exc:
        logger.exception('Store order create failed for business %s (code %s): %s',
                         business.business_id, code, exc)
        return Response({'success': False, 'error': 'Could not create the order. Please retry.'},
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    # order_date is auto_now_add; the storefront's own timestamp is kept in
    # original_order_data, and backdates the record only when it is a real date.
    ordered_on = _parse_date(
        mapped.get('order_date') or payload.get('createdAt') or payload.get('created_at'))
    if ordered_on and ordered_on != order.order_date:
        orders_models.Order.objects.filter(pk=order.pk).update(order_date=ordered_on)
        order.order_date = ordered_on

    body = _order_state(order)
    body.update({'success': True, 'duplicate': False, 'message': 'Order received'})
    return Response(body, status=status.HTTP_201_CREATED)


@api_view(['GET'])
@permission_classes([IsAuthenticated, ApiKeyScopePermission])
def store_order_status(request, code):
    """Status of one order, looked up by the storefront's own order number."""
    business = _resolve_business(request)
    if not business:
        return Response({'success': False, 'error': 'No business is associated with this key'},
                        status=status.HTTP_403_FORBIDDEN)

    base = orders_models.Order.objects.prefetch_related('order_items__product', 'delivery_task__driver')
    order = (
        base.filter(business=business, client_order_code=str(code).strip())
        .order_by('-id').first()
    )
    if not order:
        order = base.filter(business=business, order_number=str(code).strip()).first()
    if not order:
        return Response({'success': False, 'error': 'Order not found'},
                        status=status.HTTP_404_NOT_FOUND)

    body = _order_detail(order)
    body['success'] = True
    return Response(body)
