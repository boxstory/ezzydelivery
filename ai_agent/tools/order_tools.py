"""
Order Tools

Tools for order lookup and verification.
"""

import re
import logging
from typing import Any, Dict, List, Optional

from django.db.models import Q
from django.utils import timezone

from ai_agent.tools.base import BaseTool, ToolError, register_tool

logger = logging.getLogger(__name__)


# Qatar phone number patterns
QATAR_PHONE_PATTERNS = [
    r'^\+974\s?[3567]\d{7}$',  # International format
    r'^974\s?[3567]\d{7}$',    # Without plus
    r'^[3567]\d{7}$',          # Local format
    r'^\+974-[3567]\d{3}-\d{4}$',  # With dashes
]


def normalize_qatar_phone(phone: str) -> Optional[str]:
    """Normalize Qatar phone number to +974XXXXXXXX format."""
    if not phone:
        return None

    # Remove all non-digit characters except +
    cleaned = re.sub(r'[^\d+]', '', phone)

    # Remove leading + temporarily
    if cleaned.startswith('+'):
        cleaned = cleaned[1:]

    # Remove leading 00
    if cleaned.startswith('00'):
        cleaned = cleaned[2:]

    # Check if already has 974
    if cleaned.startswith('974'):
        cleaned = cleaned[3:]

    # Should now have 8 digits starting with 3, 5, 6, or 7
    if len(cleaned) == 8 and cleaned[0] in '3567':
        return f'+974{cleaned}'

    return None


def validate_qatar_phone(phone: str) -> tuple[bool, str]:
    """Validate Qatar phone number format."""
    normalized = normalize_qatar_phone(phone)
    if normalized:
        return True, normalized

    # Provide specific feedback
    if not phone or len(phone) < 8:
        return False, 'Phone number too short'

    cleaned = re.sub(r'[^\d]', '', phone)
    if len(cleaned) > 12:
        return False, 'Phone number too long'

    if not any(cleaned.startswith(prefix) for prefix in ['3', '5', '6', '7', '974']):
        return False, 'Qatar mobile numbers start with 3, 5, 6, or 7'

    return False, 'Invalid phone number format'


@register_tool
class LookupOrderTool(BaseTool):
    """
    Look up order details by order number.
    """

    name = 'lookup_order'
    allowed_roles = ['staff', 'business']
    description = '''Look up order details by order number.

    Returns order information including:
    - Order status
    - Customer details
    - Delivery address
    - COD amount
    - Assigned driver (if any)

    Example: lookup_order(order_number="BMS-60121-AA001")
    '''

    parameters_schema = {
        'type': 'object',
        'properties': {
            'order_number': {
                'type': 'string',
                'description': 'The order number to look up'
            },
            'client_order_code': {
                'type': 'string',
                'description': 'Alternative: client order code'
            }
        },
    }

    def run(self, params, user=None, business=None):
        """Override run to inject business scoping."""
        if business:
            params = dict(params)
            params['_business'] = business
        return super().run(params, user=user, business=business)

    def execute(
        self,
        order_number: Optional[str] = None,
        client_order_code: Optional[str] = None,
        _business=None
    ) -> Dict[str, Any]:
        from orders.models import Order

        if not order_number and not client_order_code:
            raise ToolError('Provide order_number or client_order_code', 'MISSING_PARAM')

        try:
            queryset = Order.objects.select_related('business', 'pickup_location')
            # Business users can only see their own orders
            if _business:
                queryset = queryset.filter(business=_business)

            if order_number:
                order = queryset.get(order_number=order_number)
            else:
                order = queryset.get(client_order_code=client_order_code)
        except Order.DoesNotExist:
            identifier = order_number or client_order_code
            raise ToolError(f'Order {identifier} not found', 'NOT_FOUND')

        # Get zone info if available
        zone_name = None
        if order.dl_zone:
            from delivery.models import ZoneName
            try:
                zone = ZoneName.objects.get(zone_number=order.dl_zone)
                zone_name = zone.zone_name
            except ZoneName.DoesNotExist:
                pass

        # Build response
        result = {
            'order_number': order.order_number,
            'client_order_code': order.client_order_code,
            'business': {
                'name': order.business.business_name if order.business else None,
                'id': str(order.business.business_id) if order.business else None,
            },
            'status': {
                'order_status': order.order_status,
                'task_status': order.task_status,
                'verification_status': order.verification_status,
            },
            'customer': {
                'name': order.customer_name,
                'phone': order.customer_phone,
                'whatsapp': order.customer_whatsapp,
            },
            'delivery': {
                'address': order.customer_address,
                'zone_number': order.dl_zone,
                'zone_name': zone_name,
            },
            'cod': {
                'amount': order.cod_amount,
                'status_by_client': order.cod_status_by_client,
                'status_by_staff': order.cod_status_by_staff,
            },
            'notes': order.order_notes,
            'created_at': order.created_at.isoformat() if hasattr(order, 'created_at') else None,
        }

        # Add delivery fee info if available
        result['delivery_fee'] = {
            'included': order.dl_included,
            'amount': order.dl_amount,
        }

        return result


