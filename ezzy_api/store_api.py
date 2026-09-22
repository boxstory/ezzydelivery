# Purpose: REST endpoints a seller's own website posts orders into (custom storefronts, no Shopify/Woo plugin).
# Used by: ezzy_api/urls.py — /api/v1/store/ping|orders/ ; authenticated by ClientApiKey (Bearer / X-API-Key).
# Notes: stage_order_payload() is shared by the push endpoint AND the pull sync, so one
#        payload means one thing. Tenant is ALWAYS the key's own business, never a body field. Idempotent on
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


def _store_api_settings(business):
    """The seller's custom-API source row, or None.

    Staged rows hang off this FK the way a Shopify row hangs off its own
    settings: the Temp Orders page hides any row whose source FK is missing, so
    a seller with no custom source configured would post orders into a list
    that never shows them.
    """
    return (
        business_models.BusinessApiSettings.objects
        .filter(business=business, api_type='custom')
        .order_by('-is_default', 'id')
        .first()
    )


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
    """One human address line out of the storefront's separate address fields.

    A Qatar address is Zone / Street / Building, and storefronts send those as
    bare numbers. An unlabelled number is not an address — "House 4, 911, Al
    Wakrah" gives a driver nothing — so a purely numeric street or zone is
    labelled. A street sent as a name ("Al Wahat Street") is already self
    describing and is left exactly as it was.
    """
    parts = []
    building = str(cust.get('buildingNumber') or cust.get('building') or '').strip()
    btype = str(cust.get('buildingType') or '').strip()
    if building:
        parts.append(f"{btype or 'Building'} {building}".strip())

    street = str(cust.get('street') or '').strip()
    if street:
        parts.append(f'Street {street}' if street.isdigit() else street)

    zone = str(cust.get('zone') or cust.get('zoneNumber') or '').strip()
    if zone and zone.isdigit():
        parts.append(f'Zone {zone}')

    for key in ('address', 'address1', 'block', 'area', 'zone_name', 'city'):
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


def _digits(value):
    """Zone / street / building as the digits-only string TempOrder stores.

    Those columns are CharFields on TempOrder and integers on Order; the import
    step does the int() conversion, so anything non-numeric ("Apartment") is
    dropped here rather than failing the import later.
    """
    if value in (None, ''):
        return ''
    text = ''.join(ch for ch in str(value) if ch.isdigit())
    return text


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


def _staged_state(temp):
    """Status snapshot for an order that is still waiting in Temp Orders.

    Same keys as `_order_state` so a storefront reads one shape throughout:
    order_number stays null until staff import the row, at which point the
    status endpoint starts answering from the real Order instead.
    """
    return {
        'order_number': None,
        'client_order_code': temp.client_order_code,
        'order_status': 'received',
        'order_status_label': 'Received — awaiting review',
        'cod_amount': temp.cod_amount or '0',
        'cod_status': 'online_paid' if (temp.financial_status or '').lower() == 'paid' else 'unpaid',
        'delivery_status': '',
        'delivery_status_label': '',
        'driver_name': '',
        'tracking_url': '',
        'delivered_at': None,
        'created_at': temp.created_at.isoformat() if temp.created_at else None,
    }


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

def stage_order_payload(business, payload, mapping=None, api_settings=None):
    """Turn one storefront order payload into a staged TempOrder.

    The single place a custom-storefront order becomes a row, shared by both
    legs: the push endpoint below, and the pull sync that fetches the same JSON
    off the seller's own site (orders.tasks._sync_custom_pull_source). The
    payload shape and the saved mapping are identical either way — whoever
    moved the bytes does not change what the order means — so these must never
    become two copies that drift apart.

    Returns exactly one of:
        {'status': 'created',          'temp': TempOrder, 'code': str}
        {'status': 'duplicate_order',  'order': Order,    'code': str}
        {'status': 'duplicate_staged', 'temp': TempOrder, 'code': str}
        {'status': 'refused', 'error': str, 'refusal': str}   -- seller may not trade
        {'status': 'error',   'error': str, 'http': int}      -- payload is unusable
    """
    refusal = write_refusal_code(business)
    if refusal:
        return {'status': 'refused', 'error': REFUSAL_MESSAGES[refusal], 'refusal': refusal}

    if not isinstance(payload, dict):
        return {'status': 'error', 'error': 'Body must be a single JSON order object',
                'http': status.HTTP_400_BAD_REQUEST}

    # A saved mapping wins wherever staff set one; the built-in guesses below
    # fill everything they left unmapped.
    if mapping is None:
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
        return {'status': 'error', 'error': 'orderNumber is required',
                'http': status.HTTP_400_BAD_REQUEST}

    cust = payload.get('customer')
    if not isinstance(cust, dict):
        cust = {}

    name = str(mapped.get('customer_name') or cust.get('name') or payload.get('customer_name') or '').strip()
    phone = _normalize_phone(
        mapped.get('customer_phone') or cust.get('phone') or payload.get('customer_phone')
    )
    if not name:
        return {'status': 'error', 'error': 'customer.name is required', 'code': code,
                'http': status.HTTP_400_BAD_REQUEST}
    if len(phone) < 7:
        return {'status': 'error', 'error': 'customer.phone must be a valid Qatar mobile number',
                'code': code, 'http': status.HTTP_400_BAD_REQUEST}

    address = str(mapped.get('customer_address') or '').strip()
    if not address:
        address = _compose_address(cust) or str(payload.get('customer_address') or '').strip()
    landmark = str(mapped.get('dl_landmark') or '').strip()
    if landmark and landmark not in address:
        address = f'{address}, {landmark}'.strip(', ')
    if not address:
        return {'status': 'error', 'error': 'customer address (area/street/building) is required',
                'code': code, 'http': status.HTTP_400_BAD_REQUEST}

    # Idempotency: a storefront that retries a timed-out POST must not create a
    # second delivery for the same checkout, and a pull re-reading the seller's
    # open-orders list must not re-stage every order on every run. Two places to
    # look — the row may still be staged, or staff may already have imported it.
    existing = orders_models.Order.objects.filter(
        business=business, client_order_code=code,
    ).order_by('-id').first()
    if existing:
        return {'status': 'duplicate_order', 'order': existing, 'code': code}

    staged = orders_models.TempOrder.objects.filter(
        business=business, source_type='custom_api', client_order_code=code,
    ).order_by('-id').first()
    if staged:
        return {'status': 'duplicate_staged', 'temp': staged, 'code': code}

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

    desc_parts, basket, qty_total = [], [], 0
    for it in items:
        item_name = str(it.get('name') or it.get('title') or it.get('product_name') or '').strip()
        qty = _int_or_none(it.get('qty') if it.get('qty') is not None else it.get('quantity')) or 1
        qty_total += qty
        if item_name:
            desc_parts.append(f'{item_name} x{qty}')
            basket.append((item_name, qty))
    package_desc = (
        str(mapped.get('package_desc') or '').strip()
        or ', '.join(desc_parts)
        or str(payload.get('package_description') or '').strip()
    )
    notes = str(
        mapped.get('seller_notes')
        or cust.get('notes') or payload.get('notes') or payload.get('order_notes') or ''
    ).strip()

    # The seller's own checkout timestamp, kept as text like every other staged
    # source; the import step parses it into Order.order_date.
    ordered_on = _parse_date(
        mapped.get('order_date') or payload.get('createdAt') or payload.get('created_at'))

    # 'paid' is the word both import paths read to set cod_status_by_client =
    # 'online_paid' (workforce.views.temp_orders_transfer / _auto_import). Get
    # this wrong and a prepaid ApplePay checkout is imported as a COD delivery
    # and the driver asks the customer to pay a second time.
    financial_status = 'pending' if is_cod else 'paid'

    staged_row = dict(payload)
    for idx, (item_name, qty) in enumerate(basket[:MAX_MAPPED_LINES], 1):
        staged_row.setdefault(f'product_{idx}', item_name)
        staged_row.setdefault(f'count_{idx}', qty)
    if qty_total:
        staged_row.setdefault('package_qty', qty_total)
    if notes:
        staged_row.setdefault('seller_notes', notes)

    if api_settings is None:
        api_settings = _store_api_settings(business)

    _TO = orders_models.TempOrder
    try:
        with transaction.atomic():
            temp = _TO.objects.create(
                business=business,
                source_type='custom_api',
                api_settings=api_settings,
                platform_id=_fit(_TO, 'platform_id', mapped.get('platform_id') or code),
                client_order_code=_fit(_TO, 'client_order_code', code),
                customer_name=_fit(_TO, 'customer_name', name),
                customer_phone=_fit(_TO, 'customer_phone', phone),
                customer_address=_fit(_TO, 'customer_address', address),
                dl_zone=_fit(_TO, 'dl_zone', _digits(
                    mapped.get('dl_zone') or cust.get('zone') or cust.get('zoneNumber'))),
                dl_street=_fit(_TO, 'dl_street', _digits(
                    mapped.get('dl_street') or cust.get('streetNumber') or cust.get('street_no'))),
                dl_building=_fit(_TO, 'dl_building', _digits(
                    mapped.get('dl_building') or cust.get('buildingNumber') or cust.get('building'))),
                cod_amount=_fit(_TO, 'cod_amount', str(total) if is_cod else '0'),
                order_date=_fit(_TO, 'order_date', ordered_on.isoformat() if ordered_on else ''),
                package_desc=_fit(_TO, 'package_desc', package_desc),
                financial_status=_fit(_TO, 'financial_status', financial_status),
                # The whole checkout, so staff can read anything the mapping
                # did not pick up, plus the product_N / count_N pairs the import
                # step reads to rebuild the basket into OrderItems. Without
                # those the line quantities are lost whenever a seller maps
                # package_desc to bare item names (gooey maps items[].name, so
                # "S'more x2" would import as "S'more", qty 1, no order items).
                raw_row=staged_row,
                status='new',
            )
    except Exception as exc:
        logger.exception('Store order staging failed for business %s (code %s): %s',
                         business.business_id, code, exc)
        return {'status': 'error', 'error': 'Could not receive the order. Please retry.',
                'code': code, 'http': status.HTTP_500_INTERNAL_SERVER_ERROR}

    logger.info('Store order staged: business=%s code=%s temp_order=%s items=%s cod=%s',
                business.business_id, code, temp.pk, len(items), is_cod)
    return {'status': 'created', 'temp': temp, 'code': code}


@api_view(['POST'])
@permission_classes([IsAuthenticated, ApiKeyScopePermission])
def store_create_order(request):
    """Stage one delivery order from a storefront checkout.

    Accepts the storefront's own camelCase shape (orderNumber / customer{} /
    items[]) as well as our snake_case field names. The checkout lands in the
    staff Temp Orders list as a TempOrder(source_type='custom_api'), the same
    queue OneDrive, Google Sheet and webhook sellers arrive in; staff Import or
    Auto-import it there and that is what creates the Order. Until then the
    response carries no order_number — the storefront identifies the order by
    the code it sent.
    """
    business = _resolve_business(request)
    if not business:
        return Response({'success': False, 'error': 'No business is associated with this key'},
                        status=status.HTTP_403_FORBIDDEN)

    result = stage_order_payload(business, request.data)

    if result['status'] == 'refused':
        return Response({'success': False, 'error': result['error'], 'code': result['refusal']},
                        status=status.HTTP_403_FORBIDDEN)
    if result['status'] == 'error':
        return Response({'success': False, 'error': result['error']}, status=result['http'])
    if result['status'] == 'duplicate_order':
        body = _order_state(result['order'])
        body.update({'success': True, 'duplicate': True, 'message': 'Order already received'})
        return Response(body, status=status.HTTP_200_OK)
    if result['status'] == 'duplicate_staged':
        body = _staged_state(result['temp'])
        body.update({'success': True, 'duplicate': True, 'message': 'Order already received'})
        return Response(body, status=status.HTTP_200_OK)

    body = _staged_state(result['temp'])
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
        # Still waiting in Temp Orders: answer 'received' rather than 404, or a
        # storefront polling right after checkout reads its own order as lost.
        staged = orders_models.TempOrder.objects.filter(
            business=business, source_type='custom_api',
            client_order_code=str(code).strip(), imported_order__isnull=True,
        ).order_by('-id').first()
        if staged:
            body = _staged_state(staged)
            body.update({'success': True, 'items': [], 'items_total': _money(0)})
            return Response(body)
        return Response({'success': False, 'error': 'Order not found'},
                        status=status.HTTP_404_NOT_FOUND)

    body = _order_detail(order)
    body['success'] = True
    return Response(body)
