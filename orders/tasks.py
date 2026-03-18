"""
Orders Celery Tasks
====================
Async tasks for order processing, including OneDrive / Google Sheet / API sync.
"""
import logging
from celery import shared_task

logger = logging.getLogger(__name__)


def _convert_excel_date(value):
    """Convert various date formats to readable date strings.

    Handles:
    - Python datetime objects (from openpyxl)
    - Excel serial date numbers: 45911.53475694444 → '2025-09-11 12:50:03'
    - DD/MM text dates: '22/01' → '2025-01-22' (infers current year)
    - DD/MM/YY or DD/MM/YYYY: '22/01/25' → '2025-01-22'
    - Short text: '32 dec', '30 no' → best effort parse
    """
    import re
    from datetime import datetime, timedelta

    if value is None:
        return ''

    # Handle Python datetime objects directly (openpyxl returns these)
    if isinstance(value, datetime):
        if value.hour == 0 and value.minute == 0 and value.second == 0:
            return value.strftime('%Y-%m-%d')
        return value.strftime('%Y-%m-%d %H:%M:%S')

    # Handle date objects
    try:
        from datetime import date
        if isinstance(value, date) and not isinstance(value, datetime):
            return value.strftime('%Y-%m-%d')
    except Exception:
        pass

    s = str(value).strip()
    if not s:
        return ''

    # Already a proper date string (YYYY-MM-DD or ISO format)
    if re.match(r'^\d{4}-\d{2}-\d{2}', s):
        return s

    # Excel serial date number
    try:
        num = float(s)
        if 1 < num < 100000 and ('.' in s or (s.isdigit() and 100 < num < 100000)):
            dt = datetime(1899, 12, 30) + timedelta(days=num)
            return dt.strftime('%Y-%m-%d %H:%M:%S') if num != int(num) else dt.strftime('%Y-%m-%d')
    except (ValueError, TypeError, OverflowError):
        pass

    # DD/MM/YYYY or DD/MM/YY
    m = re.match(r'^(\d{1,2})/(\d{1,2})/(\d{2,4})$', s)
    if m:
        day, month, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if year < 100:
            year += 2000
        try:
            return datetime(year, month, day).strftime('%Y-%m-%d')
        except ValueError:
            pass

    # DD/MM (no year — infer current year)
    m = re.match(r'^(\d{1,2})/(\d{1,2})$', s)
    if m:
        day, month = int(m.group(1)), int(m.group(2))
        if 1 <= month <= 12 and 1 <= day <= 31:
            year = datetime.now().year
            try:
                return datetime(year, month, day).strftime('%Y-%m-%d')
            except ValueError:
                pass

    # "DD mon" or "DD month" text like "32 dec", "30 no"
    month_map = {
        'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6,
        'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12,
        'ja': 1, 'fe': 2, 'ma': 3, 'ap': 4, 'ju': 6,
        'au': 8, 'se': 9, 'oc': 10, 'no': 11, 'de': 12,
    }
    m = re.match(r'^(\d{1,2})\s+([a-zA-Z]{2,})$', s)
    if m:
        day = int(m.group(1))
        mon_str = m.group(2).lower()[:3]
        month = month_map.get(mon_str) or month_map.get(mon_str[:2])
        if month:
            # Clamp day to valid range
            import calendar
            year = datetime.now().year
            max_day = calendar.monthrange(year, month)[1]
            day = min(day, max_day)
            try:
                return datetime(year, month, day).strftime('%Y-%m-%d')
            except ValueError:
                pass

    return s


@shared_task(bind=True, max_retries=2, default_retry_delay=60)
def sync_all_temp_orders(self, source_type=None, source_id=None):
    """Sync rows from all external sources into TempOrder table.

    Args:
        source_type: 'onedrive', 'google_sheet', 'shopify', 'woocommerce' or None for all.
        source_id: specific OneDriveSource.id or BusinessApiSettings.id
    """
    from django.utils import timezone

    total_created = 0
    total_updated = 0
    errors = []

    # --- OneDrive ---
    if source_type in (None, 'onedrive'):
        c, u, e = _sync_all_onedrive(source_id if source_type == 'onedrive' else None)
        total_created += c
        total_updated += u
        errors.extend(e)

    # --- Google Sheets ---
    if source_type in (None, 'google_sheet'):
        c, u, e = _sync_all_google_sheets(source_id if source_type == 'google_sheet' else None)
        total_created += c
        total_updated += u
        errors.extend(e)

    # --- Shopify / WooCommerce ---
    if source_type in (None, 'shopify', 'woocommerce'):
        api_types = [source_type] if source_type in ('shopify', 'woocommerce') else ['shopify', 'woocommerce']
        for at in api_types:
            c, u, e = _sync_all_api(at, source_id if source_type == at else None)
            total_created += c
            total_updated += u
            errors.extend(e)

    # --- Public Link ---
    if source_type in (None, 'public_link'):
        c, u, e = _sync_all_public_links(source_id if source_type == 'public_link' else None)
        total_created += c
        total_updated += u
        errors.extend(e)

    result = {
        'created': total_created,
        'updated': total_updated,
        'errors': errors,
        'synced_at': timezone.now().isoformat(),
    }
    logger.info("Temp orders sync complete: %s", result)
    return result


# Keep old name as alias for backward compat
sync_onedrive_temp_orders = sync_all_temp_orders


# =============================================================================
# OneDrive sync
# =============================================================================

def _sync_all_onedrive(source_id=None):
    from orders.models import OneDriveSource
    sources = OneDriveSource.objects.filter(
        is_active=True,
    ).exclude(last_column_mapping={}).select_related('business')
    if source_id:
        sources = sources.filter(id=source_id)

    total_c, total_u, errors = 0, 0, []
    for source in sources:
        try:
            c, u = _sync_onedrive_source(source)
            total_c += c
            total_u += u
        except Exception as exc:
            logger.exception("OneDrive sync error for source %s", source.id)
            errors.append(f"OneDrive {source.label}: {exc}")
    return total_c, total_u, errors


def _sync_onedrive_source(source):
    from orders.models import TempOrder, Order
    from workforce.views import _onedrive_download_file, _safe_load_workbook

    mapping = source.last_column_mapping
    sheet_name = source.last_sheet_name
    if not mapping or not sheet_name:
        return 0, 0

    field_map = {}
    for col_idx_str, db_field in mapping.items():
        if db_field:
            field_map[int(col_idx_str)] = db_field

    file_bytes, err = _onedrive_download_file(source)
    if err:
        raise RuntimeError(err)

    wb = _safe_load_workbook(file_bytes)
    if sheet_name not in wb.sheetnames:
        wb.close()
        raise RuntimeError(f'Sheet "{sheet_name}" not found')

    ws = wb[sheet_name]
    all_rows = list(ws.iter_rows(values_only=True))
    wb.close()

    if len(all_rows) < 2:
        return 0, 0

    data_rows = all_rows[1:]

    def get_cell(row_data, field_name):
        for idx, f in field_map.items():
            if f == field_name and idx < len(row_data):
                val = row_data[idx]
                return str(val).strip() if val is not None else ''
        return ''

    def get_cell_raw(row_data, field_name):
        """Return raw cell value (preserves datetime objects)."""
        for idx, f in field_map.items():
            if f == field_name and idx < len(row_data):
                return row_data[idx]
        return ''

    existing = {
        to.row_num: to
        for to in TempOrder.objects.filter(source_type='onedrive', onedrive_source=source)
    }

    # Imported client codes
    all_codes = [get_cell(r, 'client_order_code') for r in data_rows]
    all_codes = [c for c in all_codes if c]
    imported_codes = set()
    if all_codes:
        imported_codes = set(
            Order.objects.filter(client_order_code__in=all_codes).values_list('client_order_code', flat=True)
        )

    imported_row_nums = set()
    if source.last_imported_rows:
        for entry in source.last_imported_rows:
            if isinstance(entry, dict) and 'row' in entry:
                imported_row_nums.add(entry['row'])
            elif isinstance(entry, int):
                imported_row_nums.add(entry)

    created, updated = 0, 0
    seen_row_nums = set()

    # Process rows from bottom (newest) to top; stop after 10 consecutive imported
    consecutive_imported = 0
    row_indices = list(range(len(data_rows) - 1, -1, -1))

    for i in row_indices:
        row_data = data_rows[i]
        row_num = i + 2
        if not any(row_data):
            continue

        customer_name = get_cell(row_data, 'customer_name')
        customer_phone = get_cell(row_data, 'customer_phone')
        if not customer_name and not customer_phone:
            continue

        # Check if already imported in temp_orders table
        if row_num in existing and existing[row_num].status == 'imported':
            consecutive_imported += 1
            if consecutive_imported >= 10:
                break
            continue
        consecutive_imported = 0

        client_code = get_cell(row_data, 'client_order_code')
        already_imported = row_num in imported_row_nums
        if not already_imported and client_code and client_code in imported_codes:
            already_imported = True

        status = 'imported' if already_imported else 'new'
        raw_row = [str(c) if c is not None else '' for c in row_data]

        defaults = {
            'business': source.business,
            'source_type': 'onedrive',
            'sheet_name': sheet_name,
            'client_order_code': client_code,
            'customer_name': customer_name,
            'customer_phone': customer_phone,
            'customer_address': get_cell(row_data, 'customer_address'),
            'dl_zone': get_cell(row_data, 'dl_zone'),
            'dl_street': get_cell(row_data, 'dl_street'),
            'dl_building': get_cell(row_data, 'dl_building'),
            'cod_amount': get_cell(row_data, 'cod_amount'),
            'order_date': _convert_excel_date(get_cell_raw(row_data, 'order_date')),
            'package_desc': get_cell(row_data, 'package_desc'),
            'raw_row': raw_row,
            'status': status,
        }

        seen_row_nums.add(row_num)

        if row_num in existing:
            temp_order = existing[row_num]
            # Don't reset status if already marked as imported
            if temp_order.status == 'imported':
                defaults.pop('status', None)
            changed = False
            for key, val in defaults.items():
                if getattr(temp_order, key) != val:
                    setattr(temp_order, key, val)
                    changed = True
            if changed:
                temp_order.save()
                updated += 1
        else:
            TempOrder.objects.create(
                onedrive_source=source,
                row_num=row_num,
                **defaults,
            )
            created += 1

    return created, updated


# =============================================================================
# Google Sheets sync
# =============================================================================

def _sync_all_google_sheets(api_settings_id=None):
    from business.models import BusinessApiSettings

    qs = BusinessApiSettings.objects.filter(
        api_type='google_sheet', is_verify_api=True,
    ).select_related('business')
    if api_settings_id:
        qs = qs.filter(id=api_settings_id)

    total_c, total_u, errors = 0, 0, []
    for api_settings in qs:
        try:
            c, u = _sync_google_sheet_source(api_settings)
            total_c += c
            total_u += u
        except Exception as exc:
            logger.exception("Google Sheet sync error for %s", api_settings.business)
            errors.append(f"Google Sheet {api_settings.business.business_name}: {exc}")
    return total_c, total_u, errors


def _sync_google_sheet_source(api_settings):
    """Fetch rows from Google Sheets and upsert into TempOrder."""
    import re
    import gspread
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from django.conf import settings as django_settings
    from pathlib import Path
    from orders.models import TempOrder, Order

    sheet_url = api_settings.google_sheet_url or api_settings.site_api_url or ''
    if not sheet_url:
        return 0, 0

    token_path = Path(django_settings.BASE_DIR) / getattr(
        django_settings, 'GOOGLE_SHEETS_TOKEN_FILE', 'google_sheets_token.json'
    )
    if not token_path.exists():
        raise RuntimeError('Google Sheets not authorized. Run: python google_sheets_auth.py')

    import json as _json
    _td = _json.loads(token_path.read_text())
    creds = Credentials(
        token=_td.get('access_token'),
        refresh_token=_td.get('refresh_token'),
        token_uri=_td.get('token_uri', 'https://oauth2.googleapis.com/token'),
        client_id=_td.get('client_id'),
        client_secret=_td.get('client_secret'),
        scopes=_td.get('scope', '').split(),
    )
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        _td['access_token'] = creds.token
        token_path.write_text(_json.dumps(_td, indent=2))

    gc = gspread.authorize(creds)

    match = re.search(r'/spreadsheets/d/([^/]+)', sheet_url)
    if not match:
        raise RuntimeError('Invalid Google Sheet URL.')
    sheet_id = match.group(1)
    gid_match = re.search(r'gid=(\d+)', sheet_url)
    gid = int(gid_match.group(1)) if gid_match else 0

    spreadsheet = gc.open_by_key(sheet_id)
    worksheet = None
    for ws in spreadsheet.worksheets():
        if ws.id == gid:
            worksheet = ws
            break
    if worksheet is None:
        worksheet = spreadsheet.sheet1

    all_values = worksheet.get_all_values()
    if not all_values or len(all_values) <= 1:
        return 0, 0

    headers = all_values[0]
    data_rows = all_values[1:]

    # Column mapping
    saved_mapping = api_settings.column_mapping or {}

    def col_idx_by_header(header_name):
        for j, h in enumerate(headers):
            if h.strip() == header_name.strip():
                return j
        return None

    def col_idx_auto(*keys):
        for k in keys:
            for j, h in enumerate(headers):
                if h.strip().lower() == k.lower():
                    return j
        return None

    def get_idx(field_name, *auto_keys):
        if field_name in saved_mapping:
            return col_idx_by_header(saved_mapping[field_name])
        return col_idx_auto(*auto_keys)

    idx_name = get_idx('customer_name', 'name', 'customer name', 'customer', 'first name')
    idx_phone = get_idx('customer_phone', 'phone', 'mobile', 'phone number', 'contact')
    idx_address = get_idx('customer_address', 'address', 'delivery address', 'location', 'area', 'city')
    idx_cod = get_idx('cod_amount', 'cod', 'amount', 'cod amount', 'price', 'total', 'total charge')
    idx_date = get_idx('order_date', 'date', 'order date', 'created', 'created at')
    idx_order = get_idx('client_order_code', 'order', 'order number', 'order #', 'order id', 'ref')
    idx_product = get_idx('package_desc', 'product', 'product name', 'item', 'package desc')

    def cell(row, idx):
        if idx is not None and idx < len(row):
            v = row[idx]
            return str(v).strip() if v is not None else ''
        return ''

    business = api_settings.business

    existing = {
        to.row_num: to
        for to in TempOrder.objects.filter(source_type='google_sheet', api_settings=api_settings)
    }

    # Imported client codes
    all_codes = [cell(r, idx_order) for r in data_rows]
    all_codes = [c for c in all_codes if c]
    imported_codes = set()
    if all_codes:
        imported_codes = set(
            Order.objects.filter(client_order_code__in=all_codes).values_list('client_order_code', flat=True)
        )

    # Also check by original_order_data row_number
    imported_rows_from_db = set()
    for od in Order.objects.filter(
        business=business,
        original_order_data__source='google_sheet'
    ).values_list('original_order_data', flat=True):
        if od and isinstance(od, dict):
            rn = od.get('row_number')
            if rn is not None:
                imported_rows_from_db.add(int(rn))

    created, updated = 0, 0
    seen_row_nums = set()

    # Process rows from bottom (newest) to top; stop after 10 consecutive imported
    consecutive_imported = 0
    row_indices = list(range(len(data_rows) - 1, -1, -1))

    for i in row_indices:
        row = data_rows[i]
        row_num = i + 2
        customer_name = cell(row, idx_name)
        customer_phone = cell(row, idx_phone)
        if not customer_name and not customer_phone:
            continue

        # Check if already imported in temp_orders table
        if row_num in existing and existing[row_num].status == 'imported':
            consecutive_imported += 1
            if consecutive_imported >= 10:
                break
            continue
        consecutive_imported = 0

        client_code = cell(row, idx_order)
        already_imported = row_num in imported_rows_from_db
        if not already_imported and client_code and client_code in imported_codes:
            already_imported = True

        status = 'imported' if already_imported else 'new'
        raw_row = [str(c) if c is not None else '' for c in row]

        defaults = {
            'business': business,
            'source_type': 'google_sheet',
            'sheet_name': worksheet.title,
            'client_order_code': client_code,
            'customer_name': customer_name,
            'customer_phone': customer_phone,
            'customer_address': cell(row, idx_address),
            'cod_amount': cell(row, idx_cod),
            'order_date': _convert_excel_date(cell(row, idx_date)),
            'package_desc': cell(row, idx_product),
            'raw_row': raw_row,
            'status': status,
        }

        seen_row_nums.add(row_num)

        if row_num in existing:
            temp_order = existing[row_num]
            # Don't reset status if already marked as imported
            if temp_order.status == 'imported':
                defaults.pop('status', None)
            changed = False
            for key, val in defaults.items():
                if getattr(temp_order, key) != val:
                    setattr(temp_order, key, val)
                    changed = True
            if changed:
                temp_order.save()
                updated += 1
        else:
            TempOrder.objects.create(
                api_settings=api_settings,
                row_num=row_num,
                **defaults,
            )
            created += 1

    return created, updated


# =============================================================================
# Shopify / WooCommerce API sync
# =============================================================================

def _sync_all_api(api_type, api_settings_id=None):
    from business.models import BusinessApiSettings

    qs = BusinessApiSettings.objects.filter(
        api_type=api_type, is_verify_api=True,
    ).select_related('business')
    if api_settings_id:
        qs = qs.filter(id=api_settings_id)

    total_c, total_u, errors = 0, 0, []
    for api_settings in qs:
        try:
            c, u = _sync_api_source(api_settings)
            total_c += c
            total_u += u
        except Exception as exc:
            logger.exception("API sync error for %s (%s)", api_settings.business, api_type)
            errors.append(f"{api_type} {api_settings.business.business_name}: {exc}")
    return total_c, total_u, errors


def _sync_api_source(api_settings):
    """Fetch orders from Shopify/WooCommerce and upsert into TempOrder."""
    from orders.models import TempOrder, Order

    api_type = api_settings.api_type
    business = api_settings.business
    live_orders = []

    if api_type == 'shopify':
        live_orders = _fetch_shopify_orders(api_settings)
    elif api_type == 'woocommerce':
        live_orders = _fetch_woocommerce_orders(api_settings)

    if not live_orders:
        return 0, 0

    existing = {
        to.platform_id: to
        for to in TempOrder.objects.filter(source_type=api_type, api_settings=api_settings)
    }

    # Imported platform IDs
    imported_pids = set()
    for od in Order.objects.filter(
        business=business,
        original_order_data__source=api_type,
    ).values_list('original_order_data', flat=True):
        if od and isinstance(od, dict):
            pid = od.get('platform_id')
            if pid:
                imported_pids.add(str(pid))

    created, updated = 0, 0
    seen_pids = set()

    for o in live_orders:
        pid = str(o['platform_id'])
        seen_pids.add(pid)
        already_imported = pid in imported_pids
        status = 'imported' if already_imported else 'new'

        defaults = {
            'business': business,
            'source_type': api_type,
            'client_order_code': o.get('name', ''),
            'customer_name': o.get('customer', ''),
            'customer_phone': o.get('phone', ''),
            'customer_address': o.get('address', ''),
            'cod_amount': str(o.get('cod', '')) if o.get('cod') else '',
            'order_date': _convert_excel_date(o.get('date', '')),
            'package_desc': '',
            'raw_row': o,
            'status': status,
        }

        if pid in existing:
            temp_order = existing[pid]
            # Don't reset status if already marked as imported
            if temp_order.status == 'imported':
                defaults.pop('status', None)
            changed = False
            for key, val in defaults.items():
                if getattr(temp_order, key) != val:
                    setattr(temp_order, key, val)
                    changed = True
            if changed:
                temp_order.save()
                updated += 1
        else:
            TempOrder.objects.create(
                api_settings=api_settings,
                platform_id=pid,
                **defaults,
            )
            created += 1

    return created, updated


def _fetch_shopify_orders(api_settings):
    import shopify
    shop_name = (api_settings.site_api_url or '').replace('https://', '').replace('http://', '').replace('.myshopify.com', '').strip()
    session = shopify.Session(shop_name, api_settings.api_version or '2023-10', api_settings.api_access_token)
    shopify.ShopifyResource.activate_session(session)
    try:
        orders = shopify.Order.find(limit=50, status='any')
        result = []
        for o in orders:
            ship = getattr(o, 'shipping_address', None)
            result.append({
                'platform_id': str(o.id),
                'name': o.name,
                'customer': getattr(o, 'contact_email', '') or '',
                'phone': getattr(ship, 'phone', '') if ship else '',
                'address': getattr(ship, 'address1', '') if ship else '',
                'cod': o.total_price,
                'date': o.created_at,
                'source': 'shopify',
            })
        return result
    finally:
        shopify.ShopifyResource.clear_session()


def _fetch_woocommerce_orders(api_settings):
    from woocommerce import API as WooAPI
    wcapi = WooAPI(
        url=api_settings.site_api_url or '',
        consumer_key=api_settings.api_key or '',
        consumer_secret=api_settings.api_secret or '',
        version='wc/v3',
        timeout=15,
    )
    r = wcapi.get('orders', params={'per_page': 50, 'orderby': 'date', 'order': 'desc'})
    if r.status_code != 200:
        raise RuntimeError(f"WooCommerce API error {r.status_code}")

    result = []
    for o in r.json():
        billing = o.get('billing', {})
        shipping = o.get('shipping', {})
        addr_parts = [shipping.get('address_1') or billing.get('address_1'), shipping.get('city') or billing.get('city')]
        result.append({
            'platform_id': str(o.get('id')),
            'name': f"#{o.get('number')}",
            'customer': f"{billing.get('first_name', '')} {billing.get('last_name', '')}".strip(),
            'phone': billing.get('phone', ''),
            'address': ', '.join(filter(None, addr_parts)),
            'cod': o.get('total'),
            'date': o.get('date_created'),
            'source': 'woocommerce',
        })
    return result


# =============================================================================
# Public Link sync (HTML table scraping)
# =============================================================================

def _sync_all_public_links(source_id=None):
    from orders.models import PublicLinkSource
    sources = PublicLinkSource.objects.filter(is_active=True).select_related('business')
    if source_id:
        sources = sources.filter(id=source_id)

    total_c, total_u, errors = 0, 0, []
    for source in sources:
        try:
            c, u = _sync_public_link_source(source)
            total_c += c
            total_u += u
        except Exception as exc:
            logger.exception("Public link sync error for source %s", source.id)
            errors.append(f"PublicLink {source.label}: {exc}")
    return total_c, total_u, errors


# Auto-mapping: lowercase header → db field
_PUBLIC_LINK_HEADER_MAP = {
    'order id': 'client_order_code', 'order_id': 'client_order_code',
    'orderid': 'client_order_code', 'order': 'client_order_code',
    'id': 'client_order_code', 'order no': 'client_order_code',
    'date': 'order_date', 'order date': 'order_date', 'created': 'order_date',
    'name': 'customer_name', 'customer': 'customer_name', 'customer name': 'customer_name',
    'phone': 'customer_phone', 'phone number': 'customer_phone', 'mobile': 'customer_phone',
    'tel': 'customer_phone', 'contact': 'customer_phone',
    'address': 'customer_address', 'delivery address': 'customer_address',
    'shipping address': 'customer_address',
    'city': 'dl_landmark', 'area': 'dl_landmark', 'landmark': 'dl_landmark',
    'zone': 'dl_zone', 'zone no': 'dl_zone',
    'street': 'dl_street', 'street no': 'dl_street',
    'building': 'dl_building', 'villa': 'dl_building', 'building no': 'dl_building',
    'cod': 'cod_amount', 'cod amount': 'cod_amount', 'amount': 'cod_amount',
    'price': 'cod_amount', 'total': 'cod_amount', 'cod_amount': 'cod_amount',
    'item_1': 'product_1', 'item 1': 'product_1', 'product 1': 'product_1', 'product1': 'product_1',
    'quantity_1': 'count_1', 'qty_1': 'count_1', 'qty 1': 'count_1', 'quantity1': 'count_1',
    'item_2': 'product_2', 'item 2': 'product_2', 'product 2': 'product_2', 'product2': 'product_2',
    'quantity_2': 'count_2', 'qty_2': 'count_2', 'qty 2': 'count_2', 'quantity2': 'count_2',
    'item_3': 'product_3', 'item 3': 'product_3', 'product 3': 'product_3', 'product3': 'product_3',
    'quantity_3': 'count_3', 'qty_3': 'count_3', 'qty 3': 'count_3', 'quantity3': 'count_3',
    'email': 'customer_email', 'e-mail': 'customer_email',
    'whatsapp': 'customer_whatsapp', 'phone 2': 'customer_whatsapp',
    'notes': 'seller_notes', 'note': 'seller_notes', 'remarks': 'seller_notes',
    'description': 'package_desc', 'package': 'package_desc',
    'quantity': 'package_qty', 'qty': 'package_qty',
    'location': 'location_link', 'location link': 'location_link', 'map': 'location_link',
    'latitude': 'dl_latitude', 'lat': 'dl_latitude',
    'longitude': 'dl_longitude', 'lng': 'dl_longitude', 'lon': 'dl_longitude',
}


def _parse_html_table(html_content):
    """Parse first HTML table into headers list + list of row-lists."""
    from html.parser import HTMLParser

    class TableParser(HTMLParser):
        def __init__(self):
            super().__init__()
            self.in_table = False
            self.in_thead = False
            self.in_tbody = False
            self.in_tr = False
            self.in_cell = False
            self.current_cell = ''
            self.current_row = []
            self.headers = []
            self.rows = []
            self.found_table = False

        def handle_starttag(self, tag, attrs):
            if tag == 'table' and not self.found_table:
                self.in_table = True
                self.found_table = True
            elif tag == 'thead':
                self.in_thead = True
            elif tag == 'tbody':
                self.in_tbody = True
            elif tag == 'tr' and self.in_table:
                self.in_tr = True
                self.current_row = []
            elif tag in ('th', 'td') and self.in_tr:
                self.in_cell = True
                self.current_cell = ''

        def handle_endtag(self, tag):
            if tag == 'table':
                self.in_table = False
            elif tag == 'thead':
                self.in_thead = False
            elif tag == 'tbody':
                self.in_tbody = False
            elif tag == 'tr' and self.in_tr:
                self.in_tr = False
                if self.in_thead or (not self.headers and self.current_row):
                    self.headers = self.current_row
                else:
                    self.rows.append(self.current_row)
            elif tag in ('th', 'td') and self.in_cell:
                self.in_cell = False
                val = self.current_cell.strip()
                # Clean NaN values
                if val.lower() in ('nan', 'none', 'null', ''):
                    val = ''
                self.current_row.append(val)

        def handle_data(self, data):
            if self.in_cell:
                self.current_cell += data

    parser = TableParser()
    parser.feed(html_content)
    return parser.headers, parser.rows


def _auto_map_headers(headers):
    """Auto-map column headers to DB fields."""
    mapping = {}
    for idx, h in enumerate(headers):
        if not h:
            continue
        key = h.strip().lower()
        if key in _PUBLIC_LINK_HEADER_MAP:
            mapping[str(idx)] = _PUBLIC_LINK_HEADER_MAP[key]
    return mapping


def _sync_public_link_source(source):
    import requests
    from django.utils import timezone
    from orders.models import TempOrder, Order

    resp = requests.get(source.url, timeout=30)
    resp.raise_for_status()

    headers, rows = _parse_html_table(resp.text)
    if not headers or not rows:
        return 0, 0

    # Auto-map headers
    mapping = _auto_map_headers(headers)
    if not mapping:
        raise RuntimeError(f"Could not auto-map any columns from headers: {headers}")

    # Save mapping and headers back to source
    source.last_column_mapping = mapping
    source.last_headers = headers
    source.last_sync_at = timezone.now()

    # Build field_map: col_idx(int) -> db_field
    field_map = {int(k): v for k, v in mapping.items() if v}

    def get_cell(row_data, field_name):
        for idx, f in field_map.items():
            if f == field_name and idx < len(row_data):
                val = row_data[idx]
                return str(val).strip() if val else ''
        return ''

    # Existing temp orders for this source
    existing = {
        to.row_num: to
        for to in TempOrder.objects.filter(source_type='public_link', public_link_source=source)
    }

    # Check which client codes are already imported
    all_codes = [get_cell(r, 'client_order_code') for r in rows]
    all_codes = [c for c in all_codes if c]
    imported_codes = set()
    if all_codes:
        imported_codes = set(
            Order.objects.filter(client_order_code__in=all_codes).values_list('client_order_code', flat=True)
        )

    created, updated = 0, 0
    seen_row_nums = set()

    # Process rows from bottom (newest) to top; stop after 10 consecutive imported
    consecutive_imported = 0
    row_indices = list(range(len(rows) - 1, -1, -1))

    for i in row_indices:
        row_data = rows[i]
        row_num = i + 2  # 1-indexed, row 1 = headers
        if not any(row_data):
            continue

        customer_name = get_cell(row_data, 'customer_name')
        customer_phone = get_cell(row_data, 'customer_phone')
        if not customer_name and not customer_phone:
            continue

        # Check if already imported in temp_orders table
        if row_num in existing and existing[row_num].status == 'imported':
            consecutive_imported += 1
            if consecutive_imported >= 10:
                break
            continue
        consecutive_imported = 0

        client_code = get_cell(row_data, 'client_order_code')
        already_imported = client_code and client_code in imported_codes

        status = 'imported' if already_imported else 'new'
        raw_row = [str(c) if c else '' for c in row_data]

        # Build package_desc from product columns if no dedicated desc column
        package_desc = get_cell(row_data, 'package_desc')
        if not package_desc:
            desc_parts = []
            for pi in range(1, 4):
                pn = get_cell(row_data, f'product_{pi}')
                pc = get_cell(row_data, f'count_{pi}')
                if pn:
                    desc_parts.append(f"{pn} x{pc}" if pc else pn)
            if desc_parts:
                package_desc = ', '.join(desc_parts)

        defaults = {
            'business': source.business,
            'source_type': 'public_link',
            'sheet_name': '',
            'client_order_code': client_code,
            'customer_name': customer_name,
            'customer_phone': customer_phone,
            'customer_address': get_cell(row_data, 'customer_address'),
            'dl_zone': get_cell(row_data, 'dl_zone'),
            'dl_street': get_cell(row_data, 'dl_street'),
            'dl_building': get_cell(row_data, 'dl_building'),
            'cod_amount': get_cell(row_data, 'cod_amount'),
            'order_date': _convert_excel_date(get_cell(row_data, 'order_date')),
            'package_desc': package_desc,
            'raw_row': raw_row,
            'status': status,
        }

        seen_row_nums.add(row_num)

        if row_num in existing:
            temp_order = existing[row_num]
            # Don't reset status if already marked as imported
            if temp_order.status == 'imported':
                defaults.pop('status', None)
            changed = False
            for key, val in defaults.items():
                if getattr(temp_order, key) != val:
                    setattr(temp_order, key, val)
                    changed = True
            if changed:
                temp_order.save()
                updated += 1
        else:
            TempOrder.objects.create(
                public_link_source=source,
                row_num=row_num,
                **defaults,
            )
            created += 1

    source.last_sync_count = len(seen_row_nums)
    source.save()

    return created, updated
