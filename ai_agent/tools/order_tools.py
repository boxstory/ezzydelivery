"""
Order Tools

Tools for order lookup, verification, and COD risk assessment.
"""

import re
import logging
from decimal import Decimal
from typing import Any, Dict, List, Optional

from django.db.models import Q, Count, Sum
from django.utils import timezone

from ai_agent.tools.base import BaseTool, ToolError, register_tool
from ai_agent.models import CODRiskScore

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

    def execute(
        self,
        order_number: Optional[str] = None,
        client_order_code: Optional[str] = None
    ) -> Dict[str, Any]:
        from orders.models import Order

        if not order_number and not client_order_code:
            raise ToolError('Provide order_number or client_order_code', 'MISSING_PARAM')

        try:
            if order_number:
                order = Order.objects.select_related(
                    'business', 'pickup_location'
                ).get(order_number=order_number)
            else:
                order = Order.objects.select_related(
                    'business', 'pickup_location'
                ).get(client_order_code=client_order_code)
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


@register_tool
class VerifyOrderTool(BaseTool):
    """
    Verify order for issues like missing info, invalid phone, etc.
    """

    name = 'verify_order'
    description = '''Verify an order for completeness and issues.

    Checks for:
    - Valid phone number format
    - Complete address information
    - Valid zone
    - COD risk assessment
    - Missing required fields

    Returns a list of issues and suggestions for fixing them.
    '''

    parameters_schema = {
        'type': 'object',
        'properties': {
            'order_number': {
                'type': 'string',
                'description': 'The order number to verify'
            }
        },
        'required': ['order_number']
    }

    def execute(self, order_number: str) -> Dict[str, Any]:
        from orders.models import Order
        from delivery.models import ZoneName

        try:
            order = Order.objects.select_related(
                'business', 'pickup_location'
            ).get(order_number=order_number)
        except Order.DoesNotExist:
            raise ToolError(f'Order {order_number} not found', 'NOT_FOUND')

        issues = []
        warnings = []
        is_valid = True

        # Verify phone number
        phone_valid, phone_result = validate_qatar_phone(order.customer_phone or '')
        if not phone_valid:
            issues.append({
                'field': 'customer_phone',
                'issue': phone_result,
                'current_value': order.customer_phone,
                'suggestion': 'Format: +974 XXXXXXXX (starts with 3, 5, 6, or 7)'
            })
            is_valid = False
        elif phone_result != order.customer_phone:
            warnings.append({
                'field': 'customer_phone',
                'issue': 'Phone number can be normalized',
                'current_value': order.customer_phone,
                'suggestion': f'Normalized format: {phone_result}'
            })

        # Verify customer name
        if not order.customer_name or len(order.customer_name.strip()) < 2:
            issues.append({
                'field': 'customer_name',
                'issue': 'Customer name is missing or too short',
                'suggestion': 'Please provide customer full name'
            })
            is_valid = False

        # Verify address
        if not order.customer_address or len(order.customer_address.strip()) < 10:
            issues.append({
                'field': 'customer_address',
                'issue': 'Address is missing or incomplete',
                'suggestion': 'Include zone, street, and building number'
            })
            is_valid = False

        # Verify zone - use dl_zone field (integer)
        zone = None
        if not order.dl_zone:
            issues.append({
                'field': 'dl_zone',
                'issue': 'Delivery zone not set',
                'suggestion': 'Select a valid Qatar zone (1-99)'
            })
            is_valid = False
        else:
            # Check if zone exists and is active
            try:
                zone = ZoneName.objects.get(
                    zone_number=order.dl_zone,
                    is_active=True
                )
            except ZoneName.DoesNotExist:
                issues.append({
                    'field': 'dl_zone',
                    'issue': f'Zone {order.dl_zone} is not valid or inactive',
                    'suggestion': 'Please verify zone number'
                })
                is_valid = False

        # Verify COD amount is reasonable
        if order.cod_amount < 0:
            issues.append({
                'field': 'cod_amount',
                'issue': 'COD amount cannot be negative',
                'suggestion': 'Set to 0 for prepaid orders'
            })
            is_valid = False
        elif order.cod_amount > 50000:
            warnings.append({
                'field': 'cod_amount',
                'issue': f'High COD amount: {order.cod_amount} QAR',
                'suggestion': 'Verify this is correct for high-value orders'
            })

        # Check COD risk if phone is valid
        cod_risk = None
        if phone_valid and order.cod_amount > 0:
            normalized_phone = normalize_qatar_phone(order.customer_phone)
            cod_risk = self._assess_cod_risk(normalized_phone)
            if cod_risk and cod_risk['risk_score'] > 0.7:
                warnings.append({
                    'field': 'cod_risk',
                    'issue': f"High COD risk score: {cod_risk['risk_score']:.2f}",
                    'factors': cod_risk['risk_factors'],
                    'suggestion': 'Consider prepayment or partial advance'
                })

        return {
            'order_number': order_number,
            'is_valid': is_valid,
            'verification_status': 'passed' if is_valid else 'needs_correction',
            'issues': issues,
            'warnings': warnings,
            'cod_risk': cod_risk,
            'summary': {
                'total_issues': len(issues),
                'total_warnings': len(warnings),
                'customer_name': order.customer_name,
                'current_status': order.order_status,
            }
        }

    def _assess_cod_risk(self, phone_number: str) -> Optional[Dict[str, Any]]:
        """Get COD risk assessment for phone number."""
        try:
            risk_record = CODRiskScore.objects.get(phone_number=phone_number)
            return {
                'risk_score': risk_record.risk_score,
                'risk_factors': risk_record.risk_factors,
                'order_history': {
                    'total_orders': risk_record.total_orders,
                    'delivered': risk_record.delivered_orders,
                    'refused': risk_record.cod_refused_orders,
                }
            }
        except CODRiskScore.DoesNotExist:
            return None


@register_tool
class AssessCODRiskTool(BaseTool):
    """
    Assess COD (Cash on Delivery) risk for a customer.
    """

    name = 'assess_cod_risk'
    description = '''Assess the COD (Cash on Delivery) risk for a customer.

    Calculates a risk score (0-1) based on:
    - Order history (delivery success rate)
    - COD refusal history
    - Zone risk patterns
    - Order frequency

    Higher score = higher risk of non-payment.
    '''

    parameters_schema = {
        'type': 'object',
        'properties': {
            'phone_number': {
                'type': 'string',
                'description': 'Customer phone number'
            },
            'order_amount': {
                'type': 'number',
                'description': 'COD amount for this order (optional)'
            },
            'zone_number': {
                'type': 'integer',
                'description': 'Delivery zone number (optional)'
            }
        },
        'required': ['phone_number']
    }

    def execute(
        self,
        phone_number: str,
        order_amount: Optional[float] = None,
        zone_number: Optional[int] = None
    ) -> Dict[str, Any]:
        from orders.models import Order

        # Normalize phone number
        normalized_phone = normalize_qatar_phone(phone_number)
        if not normalized_phone:
            raise ToolError('Invalid phone number format', 'INVALID_PHONE')

        # Try to get existing risk record
        risk_record, created = CODRiskScore.objects.get_or_create(
            phone_number=normalized_phone,
            defaults={
                'risk_score': 0.5,  # Neutral for new customers
                'risk_factors': ['New customer'],
            }
        )

        if created or risk_record.total_orders == 0:
            # New customer - analyze from orders
            self._update_from_orders(risk_record, normalized_phone)

        # Update zone risk if provided
        if zone_number:
            self._apply_zone_risk(risk_record, zone_number)

        # Recalculate risk score
        risk_record.calculate_risk_score()
        risk_record.save()

        # Determine recommendation
        if risk_record.risk_score < 0.3:
            recommendation = 'LOW_RISK'
            recommendation_text = 'COD approved - reliable customer'
        elif risk_record.risk_score < 0.5:
            recommendation = 'MODERATE_RISK'
            recommendation_text = 'COD approved with standard monitoring'
        elif risk_record.risk_score < 0.7:
            recommendation = 'ELEVATED_RISK'
            recommendation_text = 'Consider partial prepayment or confirmation call'
        else:
            recommendation = 'HIGH_RISK'
            recommendation_text = 'Recommend prepayment or refuse COD'

        return {
            'phone_number': normalized_phone,
            'risk_score': round(risk_record.risk_score, 3),
            'risk_level': recommendation,
            'recommendation': recommendation_text,
            'risk_factors': risk_record.risk_factors,
            'order_history': {
                'total_orders': risk_record.total_orders,
                'delivered_orders': risk_record.delivered_orders,
                'cancelled_orders': risk_record.cancelled_orders,
                'cod_refused_orders': risk_record.cod_refused_orders,
                'delivery_rate': round(risk_record.delivery_rate, 2),
            },
            'financial_history': {
                'total_cod_amount': float(risk_record.total_cod_amount),
                'collected_cod_amount': float(risk_record.collected_cod_amount),
                'collection_rate': round(risk_record.cod_collection_rate, 2),
            },
            'is_new_customer': risk_record.total_orders < 3,
        }

    def _update_from_orders(self, risk_record: CODRiskScore, phone_number: str) -> None:
        """Update risk record from order history."""
        from orders.models import Order

        # Get order statistics for this phone
        orders = Order.objects.filter(
            Q(customer_phone=phone_number) |
            Q(customer_phone=phone_number.replace('+974', '')) |
            Q(customer_phone=phone_number.replace('+974', '974'))
        )

        # Count by status
        stats = orders.aggregate(
            total=Count('id'),
            cod_total=Sum('cod_amount'),
        )

        # Count specific statuses
        delivered = orders.filter(task_status='completed').count()
        cancelled = orders.filter(order_status='cancelled').count()
        refused = orders.filter(cod_status_by_staff='refused').count()

        # Update record
        risk_record.total_orders = stats['total'] or 0
        risk_record.delivered_orders = delivered
        risk_record.cancelled_orders = cancelled
        risk_record.cod_refused_orders = refused
        risk_record.total_cod_amount = Decimal(str(stats['cod_total'] or 0))

        # Calculate collected amount (from delivered orders)
        collected = orders.filter(
            task_status='completed'
        ).aggregate(collected=Sum('cod_amount'))
        risk_record.collected_cod_amount = Decimal(str(collected['collected'] or 0))

    def _apply_zone_risk(self, risk_record: CODRiskScore, zone_number: int) -> None:
        """Apply zone-based risk modifier."""
        from delivery.models import ZoneName

        try:
            zone = ZoneName.objects.get(zone_number=zone_number)

            # Calculate zone risk based on orders in that zone
            from orders.models import Order

            zone_orders = Order.objects.filter(delivery_zone=zone)
            zone_stats = zone_orders.aggregate(total=Count('id'))

            if zone_stats['total'] and zone_stats['total'] >= 10:
                refused = zone_orders.filter(cod_status_by_staff='refused').count()
                zone_refusal_rate = refused / zone_stats['total']

                # Apply modifier based on zone refusal rate
                if zone_refusal_rate > 0.15:
                    risk_record.zone_risk_modifier = 0.15
                elif zone_refusal_rate > 0.1:
                    risk_record.zone_risk_modifier = 0.1
                elif zone_refusal_rate < 0.05:
                    risk_record.zone_risk_modifier = -0.1
                else:
                    risk_record.zone_risk_modifier = 0.0

                risk_record.primary_zone = zone
        except ZoneName.DoesNotExist:
            pass


@register_tool
class SearchOrdersTool(BaseTool):
    """
    Search for orders with various filters.
    """

    name = 'search_orders'
    description = '''Search for orders using various filters.

    Can filter by:
    - Customer phone
    - Date range
    - Order status
    - Zone
    - Business

    Returns a list of matching orders (limited to 20).
    '''

    parameters_schema = {
        'type': 'object',
        'properties': {
            'customer_phone': {
                'type': 'string',
                'description': 'Customer phone number'
            },
            'order_status': {
                'type': 'string',
                'description': 'Order status filter'
            },
            'zone_number': {
                'type': 'integer',
                'description': 'Delivery zone number'
            },
            'date_from': {
                'type': 'string',
                'description': 'Start date (YYYY-MM-DD)'
            },
            'date_to': {
                'type': 'string',
                'description': 'End date (YYYY-MM-DD)'
            },
            'limit': {
                'type': 'integer',
                'description': 'Max results (default 20)',
                'default': 20
            }
        },
    }

    def execute(
        self,
        customer_phone: Optional[str] = None,
        order_status: Optional[str] = None,
        zone_number: Optional[int] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        limit: int = 20
    ) -> Dict[str, Any]:
        from orders.models import Order
        from datetime import datetime

        queryset = Order.objects.select_related('business')

        # Apply filters
        if customer_phone:
            normalized = normalize_qatar_phone(customer_phone)
            if normalized:
                queryset = queryset.filter(
                    Q(customer_phone=normalized) |
                    Q(customer_phone=normalized.replace('+974', '')) |
                    Q(customer_phone=customer_phone)
                )
            else:
                queryset = queryset.filter(customer_phone__icontains=customer_phone)

        if order_status:
            queryset = queryset.filter(order_status=order_status)

        if zone_number:
            queryset = queryset.filter(dl_zone=zone_number)

        if date_from:
            try:
                start_date = datetime.strptime(date_from, '%Y-%m-%d')
                queryset = queryset.filter(created_at__gte=start_date)
            except ValueError:
                pass

        if date_to:
            try:
                end_date = datetime.strptime(date_to, '%Y-%m-%d')
                queryset = queryset.filter(created_at__lte=end_date)
            except ValueError:
                pass

        # Limit and order
        orders = queryset.order_by('-created_at')[:min(limit, 50)]

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
                'created_at': order.created_at.isoformat() if hasattr(order, 'created_at') else None,
            })

        return {
            'count': len(results),
            'orders': results,
            'filters_applied': {
                'customer_phone': customer_phone,
                'order_status': order_status,
                'zone_number': zone_number,
                'date_from': date_from,
                'date_to': date_to,
            }
        }
