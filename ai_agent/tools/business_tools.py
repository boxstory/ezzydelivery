"""
Business Tools

Read-only tools for business users to access their dashboard stats,
orders, deliveries, COD summaries, customers, and pickup locations.
All queries are automatically scoped to the user's business.
"""

import logging
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional

from django.db.models import Q, Count, Sum, Max, Min
from django.utils import timezone

import zoneinfo

_QATAR_TZ = zoneinfo.ZoneInfo('Asia/Qatar')


def _parse_date(date_str):
    """Parse YYYY-MM-DD string to timezone-aware datetime."""
    return datetime.strptime(date_str, '%Y-%m-%d').replace(tzinfo=_QATAR_TZ)

from ai_agent.tools.base import BaseTool, ToolError, register_tool

logger = logging.getLogger(__name__)


@register_tool
class GetBusinessDashboardTool(BaseTool):
    """
    Get dashboard statistics for the business.
    """

    name = 'get_business_dashboard'
    allowed_roles = ['business']
    description = '''Get dashboard statistics for your business.

    Returns:
    - Total orders, delivered, pending, cancelled counts
    - COD totals (total, collected, pending)
    - Follow-up required count
    - Today's stats (new orders, delivered today)

    Optional date range filter (date_from, date_to in YYYY-MM-DD format).
    If no dates provided, shows all-time stats plus today's summary.
    '''

    parameters_schema = {
        'type': 'object',
        'properties': {
            'date_from': {
                'type': 'string',
                'description': 'Start date filter (YYYY-MM-DD)'
            },
            'date_to': {
                'type': 'string',
                'description': 'End date filter (YYYY-MM-DD)'
            }
        },
    }

    def run(self, params, user=None, business=None):
        if business:
            params = dict(params)
            params['_business'] = business
        return super().run(params, user=user, business=business)

    def execute(self, date_from: Optional[str] = None, date_to: Optional[str] = None, _business=None) -> Dict[str, Any]:
        from orders.models import Order

        if not _business:
            raise ToolError('Business context required', 'NO_BUSINESS')

        queryset = Order.objects.filter(business=_business)

        # Apply date filters
        if date_from:
            try:
                start_date = _parse_date(date_from)
                queryset = queryset.filter(created_at__gte=start_date)
            except ValueError:
                raise ToolError('Invalid date_from format. Use YYYY-MM-DD', 'INVALID_PARAM')

        if date_to:
            try:
                end_date = _parse_date(date_to) + timedelta(days=1)
                queryset = queryset.filter(created_at__lt=end_date)
            except ValueError:
                raise ToolError('Invalid date_to format. Use YYYY-MM-DD', 'INVALID_PARAM')

        # Order counts by status
        total_orders = queryset.count()
        status_counts = dict(
            queryset.values_list('order_status').annotate(count=Count('id')).values_list('order_status', 'count')
        )

        delivered = status_counts.get('delivered', 0) + status_counts.get('fulfilled', 0)
        cancelled = status_counts.get('cancelled', 0)
        pending = total_orders - delivered - cancelled

        # Detailed status breakdown so AI knows exact statuses to search for
        status_breakdown = {k: v for k, v in status_counts.items() if v > 0}

        # COD totals
        cod_stats = queryset.aggregate(
            total_cod=Sum('cod_amount'),
        )
        total_cod = cod_stats['total_cod'] or 0

        cod_collected = queryset.filter(
            cod_status_by_staff__in=['fully_paid', 'cod_settled_with_business']
        ).aggregate(collected=Sum('cod_amount'))['collected'] or 0

        cod_with_driver = queryset.filter(
            cod_status_by_staff='cod_with_driver'
        ).aggregate(amt=Sum('cod_amount'))['amt'] or 0

        cod_with_ezzy = queryset.filter(
            cod_status_by_staff='cod_with_ezzy'
        ).aggregate(amt=Sum('cod_amount'))['amt'] or 0

        cod_pending = total_cod - cod_collected

        # Follow-up required (info_missing or address needs update)
        follow_up_count = queryset.filter(
            Q(task_status='info_missing') |
            Q(verification_status='address_needs_update')
        ).count()

        # Today's stats
        today = timezone.localtime().date()
        today_qs = Order.objects.filter(business=_business, created_at__date=today)
        today_new = today_qs.count()
        today_delivered = Order.objects.filter(
            business=_business,
            delivered_at__date=today
        ).count()

        result = {
            'business_name': _business.business_name,
            'orders': {
                'total': total_orders,
                'delivered': delivered,
                'pending': pending,
                'cancelled': cancelled,
                'status_breakdown': status_breakdown,
            },
            'cod': {
                'total_amount': total_cod,
                'collected': cod_collected,
                'pending': cod_pending,
                'with_driver': cod_with_driver,
                'with_ezzy': cod_with_ezzy,
            },
            'follow_up_required': follow_up_count,
            'today': {
                'new_orders': today_new,
                'delivered': today_delivered,
            },
        }

        if date_from or date_to:
            result['date_range'] = {
                'from': date_from,
                'to': date_to,
            }

        # Include pickup locations summary
        from business.models import PickupLocation
        locations = PickupLocation.objects.filter(business=_business)
        result['pickup_locations'] = [
            {
                'title': loc.pickup_location_title,
                'zone': loc.pickup_zone_no,
                'status': loc.pickup_status,
            }
            for loc in locations
        ]

        return result


@register_tool
class SearchBusinessOrdersTool(BaseTool):
    """
    Search and list orders with filters. Role-aware: business users see only
    their own orders; staff users see all orders (or filter by business).
    """

    name = 'search_orders'
    allowed_roles = ['staff', 'business']
    description = '''Search and list orders with filters.

    Business users: automatically scoped to your business orders.
    Staff users: searches all orders (no business restriction).

    Can filter by:
    - Order status: to_review, ready_to_pickup, publish, delivered, fulfilled, cancelled
      NOTE: There is NO "pending" status. Dashboard "pending" count = to_review + ready_to_pickup + publish.
      To list pending orders, use order_status="pending" which will automatically include all non-delivered, non-cancelled orders.
    - Date range (date_from, date_to in YYYY-MM-DD)
    - Customer phone or name
    - Zone number
    - COD status (no_cod, not_collected, cod_with_driver, cod_with_ezzy, fully_paid, cod_settled_with_business)
    - Sort by: date, status, cod_amount (prefix with - for descending, e.g. -date)

    Returns paginated order list (max 50 per query).
    '''

    parameters_schema = {
        'type': 'object',
        'properties': {
            'order_status': {
                'type': 'string',
                'description': 'Filter by order status'
            },
            'date_from': {
                'type': 'string',
                'description': 'Start date (YYYY-MM-DD)'
            },
            'date_to': {
                'type': 'string',
                'description': 'End date (YYYY-MM-DD)'
            },
            'customer_phone': {
                'type': 'string',
                'description': 'Customer phone number (partial match)'
            },
            'customer_name': {
                'type': 'string',
                'description': 'Customer name (partial match)'
            },
            'zone_number': {
                'type': 'integer',
                'description': 'Delivery zone number'
            },
            'cod_status': {
                'type': 'string',
                'description': 'COD status filter'
            },
            'sort_by': {
                'type': 'string',
                'description': 'Sort field: date, status, cod_amount (prefix - for desc)',
                'default': '-date'
            },
            'limit': {
                'type': 'integer',
                'description': 'Max results (default 20, max 50)',
                'default': 20
            },
            'offset': {
                'type': 'integer',
                'description': 'Skip first N results for pagination',
                'default': 0
            }
        },
    }

    def run(self, params, user=None, business=None):
        if business:
            params = dict(params)
            params['_business'] = business
        return super().run(params, user=user, business=business)

    def execute(
        self,
        order_status: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        customer_phone: Optional[str] = None,
        customer_name: Optional[str] = None,
        zone_number: Optional[int] = None,
        cod_status: Optional[str] = None,
        sort_by: str = '-date',
        limit: int = 20,
        offset: int = 0,
        _business=None
    ) -> Dict[str, Any]:
        from orders.models import Order

        queryset = Order.objects.select_related('pickup_location', 'business')

        # Business users see only their orders; staff see all
        if _business:
            queryset = queryset.filter(business=_business)

        # Apply filters
        if order_status:
            if order_status == 'pending':
                # "pending" is a virtual status = all non-delivered, non-cancelled
                queryset = queryset.exclude(order_status__in=['delivered', 'fulfilled', 'cancelled'])
            else:
                queryset = queryset.filter(order_status=order_status)

        if date_from:
            try:
                start_date = _parse_date(date_from)
                queryset = queryset.filter(created_at__gte=start_date)
            except ValueError:
                pass

        if date_to:
            try:
                end_date = _parse_date(date_to) + timedelta(days=1)
                queryset = queryset.filter(created_at__lt=end_date)
            except ValueError:
                pass

        if customer_phone:
            queryset = queryset.filter(customer_phone__icontains=customer_phone)

        if customer_name:
            queryset = queryset.filter(customer_name__icontains=customer_name)

        if zone_number:
            queryset = queryset.filter(dl_zone=zone_number)

        if cod_status:
            if cod_status == 'no_cod':
                queryset = queryset.filter(cod_amount=0)
            else:
                queryset = queryset.filter(cod_status_by_staff=cod_status)

        # Sorting
        sort_map = {
            'date': 'created_at',
            '-date': '-created_at',
            'status': 'order_status',
            '-status': '-order_status',
            'cod_amount': 'cod_amount',
            '-cod_amount': '-cod_amount',
        }
        order_field = sort_map.get(sort_by, '-created_at')
        queryset = queryset.order_by(order_field)

        # Count before pagination
        total_count = queryset.count()

        # Pagination
        limit = min(limit, 50)
        offset = max(offset, 0)
        orders = queryset[offset:offset + limit]

        results = []
        for order in orders:
            results.append({
                'order_number': order.order_number,
                'client_order_code': order.client_order_code,
                'customer_name': order.customer_name,
                'customer_phone': order.customer_phone,
                'order_status': order.order_status,
                'task_status': order.task_status,
                'zone_number': order.dl_zone,
                'cod_amount': order.cod_amount,
                'cod_status': order.cod_status_by_staff,
                'pickup_location': order.pickup_location.pickup_location_title if order.pickup_location else None,
                'created_at': order.created_at.isoformat() if order.created_at else None,
                'delivered_at': order.delivered_at.isoformat() if order.delivered_at else None,
            })

        return {
            'total_count': total_count,
            'returned': len(results),
            'offset': offset,
            'limit': limit,
            'orders': results,
            'filters_applied': {
                'order_status': order_status,
                'date_from': date_from,
                'date_to': date_to,
                'customer_phone': customer_phone,
                'customer_name': customer_name,
                'zone_number': zone_number,
                'cod_status': cod_status,
                'sort_by': sort_by,
            }
        }


@register_tool
class GetBusinessDeliveriesTool(BaseTool):
    """
    Get delivery task summary for the business.
    """

    name = 'get_business_deliveries'
    allowed_roles = ['business']
    description = '''Get delivery task summary for your business.

    Can filter by:
    - Delivery status (pending, assigned, accepted, picked_up, in_transit, delivered, failed, cancelled)
    - Date range (YYYY-MM-DD)
    - Driver name

    Returns delivery tasks with driver info, status, and timestamps.
    Also returns summary counts by status.
    '''

    parameters_schema = {
        'type': 'object',
        'properties': {
            'status': {
                'type': 'string',
                'description': 'Filter by delivery status'
            },
            'date_from': {
                'type': 'string',
                'description': 'Start date (YYYY-MM-DD)'
            },
            'date_to': {
                'type': 'string',
                'description': 'End date (YYYY-MM-DD)'
            },
            'driver_name': {
                'type': 'string',
                'description': 'Filter by driver name (partial match)'
            },
            'limit': {
                'type': 'integer',
                'description': 'Max results (default 20, max 50)',
                'default': 20
            }
        },
    }

    def run(self, params, user=None, business=None):
        if business:
            params = dict(params)
            params['_business'] = business
        return super().run(params, user=user, business=business)

    def execute(
        self,
        status: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        driver_name: Optional[str] = None,
        limit: int = 20,
        _business=None
    ) -> Dict[str, Any]:
        from delivery.models import DeliveryTask

        if not _business:
            raise ToolError('Business context required', 'NO_BUSINESS')

        queryset = DeliveryTask.objects.filter(
            business=_business
        ).select_related('order', 'driver', 'driver__user')

        # Apply filters
        if status:
            queryset = queryset.filter(dl_task_status=status)

        if date_from:
            try:
                start_date = _parse_date(date_from)
                queryset = queryset.filter(created_at__gte=start_date)
            except ValueError:
                pass

        if date_to:
            try:
                end_date = _parse_date(date_to) + timedelta(days=1)
                queryset = queryset.filter(created_at__lt=end_date)
            except ValueError:
                pass

        if driver_name:
            queryset = queryset.filter(
                Q(driver__user__first_name__icontains=driver_name) |
                Q(driver__user__last_name__icontains=driver_name)
            )

        # Summary counts (before limiting)
        all_tasks = DeliveryTask.objects.filter(business=_business)
        if date_from:
            try:
                all_tasks = all_tasks.filter(created_at__gte=_parse_date(date_from))
            except ValueError:
                pass
        if date_to:
            try:
                all_tasks = all_tasks.filter(created_at__lt=_parse_date(date_to) + timedelta(days=1))
            except ValueError:
                pass

        status_counts = dict(
            all_tasks.values_list('dl_task_status').annotate(count=Count('id')).values_list('dl_task_status', 'count')
        )

        # Limit results
        limit = min(limit, 50)
        tasks = queryset.order_by('-created_at')[:limit]

        results = []
        for task in tasks:
            driver_info = None
            if task.driver and task.driver.user:
                driver_info = {
                    'name': task.driver.user.get_full_name(),
                    'phone': task.driver.driver_phone,
                }

            results.append({
                'task_number': task.dl_task_number,
                'order_number': task.order.order_number if task.order else None,
                'customer_name': task.order.customer_name if task.order else None,
                'status': task.dl_task_status,
                'driver': driver_info,
                'zone': task.order.dl_zone if task.order else None,
                'cod_collected': task.cod_collected,
                'cod_amount': float(task.cod_collected_amount) if task.cod_collected_amount else 0,
                'created_at': task.created_at.isoformat() if task.created_at else None,
                'completed_at': task.completed_at.isoformat() if task.completed_at else None,
            })

        return {
            'total_tasks': sum(status_counts.values()),
            'status_summary': status_counts,
            'returned': len(results),
            'deliveries': results,
        }


@register_tool
class GetBusinessCODSummaryTool(BaseTool):
    """
    Get COD financial summary for the business.
    """

    name = 'get_business_cod_summary'
    allowed_roles = ['business']
    description = '''Get COD (Cash on Delivery) financial summary for your business.

    Returns:
    - Total COD amount across all orders
    - Breakdown by status: collected, with driver, with EzzyDelivery, settled
    - Pending settlement amount
    - Date range filter support

    Set include_details=true to see per-order COD breakdown (limited to 50).
    '''

    parameters_schema = {
        'type': 'object',
        'properties': {
            'date_from': {
                'type': 'string',
                'description': 'Start date (YYYY-MM-DD)'
            },
            'date_to': {
                'type': 'string',
                'description': 'End date (YYYY-MM-DD)'
            },
            'include_details': {
                'type': 'boolean',
                'description': 'Include per-order COD details (default false)',
                'default': False
            }
        },
    }

    def run(self, params, user=None, business=None):
        if business:
            params = dict(params)
            params['_business'] = business
        return super().run(params, user=user, business=business)

    def execute(
        self,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        include_details: bool = False,
        _business=None
    ) -> Dict[str, Any]:
        from orders.models import Order

        if not _business:
            raise ToolError('Business context required', 'NO_BUSINESS')

        queryset = Order.objects.filter(
            business=_business,
            cod_amount__gt=0
        )

        if date_from:
            try:
                start_date = _parse_date(date_from)
                queryset = queryset.filter(created_at__gte=start_date)
            except ValueError:
                pass

        if date_to:
            try:
                end_date = _parse_date(date_to) + timedelta(days=1)
                queryset = queryset.filter(created_at__lt=end_date)
            except ValueError:
                pass

        # Aggregate COD by status
        total_cod = queryset.aggregate(total=Sum('cod_amount'))['total'] or 0

        status_breakdown = {}
        cod_statuses = [
            ('not_collected', 'Not Collected'),
            ('partially_collected', 'Partially Collected'),
            ('fully_paid', 'Fully Paid'),
            ('cod_with_driver', 'With Driver'),
            ('cod_with_ezzy', 'With EzzyDelivery'),
            ('cod_settled_with_business', 'Settled with Business'),
        ]

        for status_key, status_label in cod_statuses:
            status_qs = queryset.filter(cod_status_by_staff=status_key)
            amount = status_qs.aggregate(amt=Sum('cod_amount'))['amt'] or 0
            count = status_qs.count()
            if count > 0:
                status_breakdown[status_key] = {
                    'label': status_label,
                    'count': count,
                    'amount': amount,
                }

        # Also count orders with no COD status set
        no_status_qs = queryset.filter(
            Q(cod_status_by_staff__isnull=True) | Q(cod_status_by_staff='')
        )
        no_status_count = no_status_qs.count()
        if no_status_count > 0:
            no_status_amount = no_status_qs.aggregate(amt=Sum('cod_amount'))['amt'] or 0
            status_breakdown['no_status'] = {
                'label': 'Status Not Set',
                'count': no_status_count,
                'amount': no_status_amount,
            }

        settled_amount = (status_breakdown.get('cod_settled_with_business', {}).get('amount', 0)
                          + status_breakdown.get('fully_paid', {}).get('amount', 0))
        pending_settlement = total_cod - settled_amount

        result = {
            'total_cod_orders': queryset.count(),
            'total_cod_amount': total_cod,
            'settled_amount': settled_amount,
            'pending_settlement': pending_settlement,
            'breakdown': status_breakdown,
        }

        if date_from or date_to:
            result['date_range'] = {'from': date_from, 'to': date_to}

        # Optional per-order details
        if include_details:
            detail_orders = queryset.order_by('-created_at')[:50]
            details = []
            for order in detail_orders:
                details.append({
                    'order_number': order.order_number,
                    'customer_name': order.customer_name,
                    'cod_amount': order.cod_amount,
                    'cod_status': order.cod_status_by_staff,
                    'order_status': order.order_status,
                    'created_at': order.created_at.isoformat() if order.created_at else None,
                })
            result['order_details'] = details

        return result


@register_tool
class GetBusinessCustomersTool(BaseTool):
    """
    Get customer list aggregated from order history.
    """

    name = 'get_business_customers'
    allowed_roles = ['business']
    description = '''Get your customer list aggregated from order history.

    Returns unique customers (by phone number) with:
    - Order count and total spend
    - Last order date
    - Search by name or phone

    Sorted by order count (most frequent first).
    '''

    parameters_schema = {
        'type': 'object',
        'properties': {
            'search': {
                'type': 'string',
                'description': 'Search by customer name or phone'
            },
            'limit': {
                'type': 'integer',
                'description': 'Max results (default 20, max 50)',
                'default': 20
            }
        },
    }

    def run(self, params, user=None, business=None):
        if business:
            params = dict(params)
            params['_business'] = business
        return super().run(params, user=user, business=business)

    def execute(
        self,
        search: Optional[str] = None,
        limit: int = 20,
        _business=None
    ) -> Dict[str, Any]:
        from orders.models import Order

        if not _business:
            raise ToolError('Business context required', 'NO_BUSINESS')

        queryset = Order.objects.filter(
            business=_business
        ).exclude(
            customer_phone__isnull=True
        ).exclude(
            customer_phone=''
        )

        if search:
            queryset = queryset.filter(
                Q(customer_name__icontains=search) |
                Q(customer_phone__icontains=search)
            )

        # Aggregate by phone number
        customers = queryset.values('customer_phone').annotate(
            order_count=Count('id'),
            total_spent=Sum('cod_amount'),
            last_order=Max('created_at'),
            first_order=Min('created_at'),
        ).order_by('-order_count')

        limit = min(limit, 50)
        customer_list = list(customers[:limit])

        # Get the latest customer name for each phone
        results = []
        for cust in customer_list:
            # Get the name from the most recent order
            latest_order = Order.objects.filter(
                business=_business,
                customer_phone=cust['customer_phone']
            ).order_by('-created_at').values('customer_name').first()

            results.append({
                'customer_name': latest_order['customer_name'] if latest_order else 'Unknown',
                'customer_phone': cust['customer_phone'],
                'order_count': cust['order_count'],
                'total_cod_amount': cust['total_spent'] or 0,
                'first_order': cust['first_order'].isoformat() if cust['first_order'] else None,
                'last_order': cust['last_order'].isoformat() if cust['last_order'] else None,
            })

        total_unique = queryset.values('customer_phone').distinct().count()

        return {
            'total_unique_customers': total_unique,
            'returned': len(results),
            'customers': results,
        }




@register_tool
class GetBusinessProductsTool(BaseTool):
    """
    List products in the business product catalog.
    """

    name = 'get_business_products'
    allowed_roles = ['business']
    description = '''List products in your product catalog with stock quantities.

    Returns product names, SKUs, prices, and current stock_qty.
    Use low_stock_only=true to find products running low on stock.
    '''

    parameters_schema = {
        'type': 'object',
        'properties': {
            'search': {
                'type': 'string',
                'description': 'Filter by product name, brand, or SKU',
            },
            'low_stock_only': {
                'type': 'boolean',
                'description': 'Set true to return only products at or below the threshold',
            },
            'low_stock_threshold': {
                'type': 'integer',
                'description': 'Quantity threshold for low stock (default 5)',
            },
            'limit': {
                'type': 'integer',
                'description': 'Max results (default 20, max 50)',
            },
        },
        'required': [],
    }

    input_schema = parameters_schema

    def run(self, params, user=None, business=None):
        params = dict(params or {})
        if business:
            params['_business'] = business
        return super().run(params, user=user, business=business)

    def execute(self, search: Optional[str] = None, low_stock_only: bool = False,
                low_stock_threshold: int = 5, limit: int = 20, _business=None) -> Dict[str, Any]:
        from product.models import Product, ProductInventory
        from django.db.models import Q, OuterRef, Subquery, IntegerField
        from django.db.models.functions import Coalesce

        if not _business:
            raise ToolError('Business context required', 'NO_BUSINESS')

        search    = (search or '').strip()
        limit     = min(int(limit or 20), 50)
        threshold = int(low_stock_threshold or 5)

        # Annotate each product with its latest inventory quantity
        latest_inv = ProductInventory.objects.filter(
            item_sku=OuterRef('pk')
        ).order_by('-updated_at').values('item_quantity')[:1]

        qs = (
            Product.objects
            .filter(business=_business)
            .annotate(stock_qty=Coalesce(Subquery(latest_inv, output_field=IntegerField()), 0))
            .select_related('color', 'product_category')
        )

        if search:
            qs = qs.filter(
                Q(item_name__icontains=search) |
                Q(brand_name__icontains=search) |
                Q(item_sku__icontains=search) |
                Q(client_names__icontains=search)
            )

        if low_stock_only:
            qs = qs.filter(stock_qty__lte=threshold).order_by('stock_qty')
        else:
            qs = qs.order_by('-created_at')

        total = qs.count()
        products = []
        for p in qs[:limit]:
            products.append({
                'product_id':  p.product_id,
                'name':        f'{p.brand_name} {p.item_name}'.strip(),
                'sku':         p.item_sku,
                'price':       p.item_price,
                'stock_qty':   p.stock_qty,
                'color':       p.color.color_variant if p.color else None,
                'size':        p.size,
                'category':    str(p.product_category) if p.product_category else None,
                'description': p.item_discription,
            })

        return {
            'total_products':    total,
            'returned':          len(products),
            'low_stock_only':    low_stock_only,
            'low_stock_threshold': threshold,
            'search':            search or None,
            'products':          products,
        }
