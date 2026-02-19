"""
Delivery Tools

Tools for delivery estimation and driver suggestions.
"""

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from django.db.models import Q, Count, Avg
from django.utils import timezone

from ai_agent.tools.base import BaseTool, ToolError, register_tool, get_user_role

logger = logging.getLogger(__name__)


# Qatar traffic patterns (rough estimates)
TRAFFIC_MULTIPLIERS = {
    # Weekday rush hours
    (0, 7, 9): 1.5,   # Morning rush
    (0, 16, 19): 1.6,  # Evening rush
    # Weekend patterns
    (4, 10, 14): 1.3,  # Friday prayers
    (5, 18, 22): 1.4,  # Saturday evening
}

# Base delivery times by zone distance (minutes)
BASE_DELIVERY_TIME = 20  # Minimum time
TIME_PER_ZONE_HOP = 8    # Minutes per zone distance


def get_traffic_multiplier() -> float:
    """Get current traffic multiplier based on time of day."""
    now = timezone.localtime()
    weekday = now.weekday()  # 0=Monday, 6=Sunday
    hour = now.hour

    for (day_pattern, start_hour, end_hour), multiplier in TRAFFIC_MULTIPLIERS.items():
        if weekday == day_pattern or day_pattern == 0:  # 0 means weekdays
            if start_hour <= hour < end_hour:
                return multiplier

    return 1.0  # Normal traffic


@register_tool
class EstimateDeliveryTool(BaseTool):
    """
    Estimate delivery time for an order.
    """

    name = 'estimate_delivery'
    allowed_roles = ['staff', 'business']
    description = '''Estimate delivery time for an order based on zones and traffic.

    Considers:
    - Pickup zone to delivery zone distance
    - Current traffic conditions
    - Historical delivery times for the route
    - Time of day patterns

    Returns estimated delivery window (min-max minutes).
    '''

    parameters_schema = {
        'type': 'object',
        'properties': {
            'pickup_zone': {
                'type': 'integer',
                'description': 'Pickup zone number'
            },
            'delivery_zone': {
                'type': 'integer',
                'description': 'Delivery zone number'
            },
            'order_number': {
                'type': 'string',
                'description': 'Order number (alternative to zones)'
            }
        },
    }

    def execute(
        self,
        pickup_zone: Optional[int] = None,
        delivery_zone: Optional[int] = None,
        order_number: Optional[str] = None
    ) -> Dict[str, Any]:
        from delivery.models import ZoneName
        from orders.models import Order

        # Get zones from order if provided
        if order_number:
            try:
                order = Order.objects.select_related(
                    'pickup_location'
                ).get(order_number=order_number)

                if order.pickup_location and order.pickup_location.pickup_zone_no:
                    pickup_zone = order.pickup_location.pickup_zone_no
                if order.dl_zone:
                    delivery_zone = order.dl_zone
            except Order.DoesNotExist:
                raise ToolError(f'Order {order_number} not found', 'NOT_FOUND')

        if not pickup_zone and not delivery_zone:
            raise ToolError('Both pickup_zone and delivery_zone are required', 'MISSING_PARAM')
        if not pickup_zone:
            # Use default pickup zone (Zone 1 - central Doha) if not specified
            pickup_zone = 1
        if not delivery_zone:
            raise ToolError('Delivery zone is required (order has no dl_zone set)', 'MISSING_PARAM')

        # Verify zones exist
        try:
            pickup = ZoneName.objects.get(zone_number=pickup_zone)
        except ZoneName.DoesNotExist:
            raise ToolError(f'Pickup zone {pickup_zone} not found', 'NOT_FOUND')

        try:
            delivery = ZoneName.objects.get(zone_number=delivery_zone)
        except ZoneName.DoesNotExist:
            raise ToolError(f'Delivery zone {delivery_zone} not found', 'NOT_FOUND')

        # Calculate zone distance (simplified - could use actual coordinates)
        zone_distance = self._calculate_zone_distance(pickup, delivery)

        # Base time calculation
        base_time = BASE_DELIVERY_TIME + (zone_distance * TIME_PER_ZONE_HOP)

        # Apply traffic multiplier
        traffic_mult = get_traffic_multiplier()
        adjusted_time = base_time * traffic_mult

        # Get historical average for this route
        historical_avg = self._get_historical_average(pickup_zone, delivery_zone)
        if historical_avg:
            # Weight historical data
            adjusted_time = (adjusted_time * 0.4) + (historical_avg * 0.6)

        # Calculate window
        min_time = int(adjusted_time * 0.8)
        max_time = int(adjusted_time * 1.3)

        now = timezone.localtime()

        return {
            'pickup_zone': {
                'number': pickup_zone,
                'name': pickup.zone_name,
            },
            'delivery_zone': {
                'number': delivery_zone,
                'name': delivery.zone_name,
            },
            'estimate': {
                'min_minutes': min_time,
                'max_minutes': max_time,
                'estimated_minutes': int(adjusted_time),
            },
            'arrival_window': {
                'earliest': (now + timedelta(minutes=min_time)).strftime('%H:%M'),
                'latest': (now + timedelta(minutes=max_time)).strftime('%H:%M'),
                'expected': (now + timedelta(minutes=int(adjusted_time))).strftime('%H:%M'),
            },
            'factors': {
                'zone_distance': zone_distance,
                'traffic_multiplier': traffic_mult,
                'historical_average': historical_avg,
                'current_time': now.strftime('%H:%M'),
                'day_of_week': now.strftime('%A'),
            }
        }

    def _calculate_zone_distance(self, pickup: 'ZoneName', delivery: 'ZoneName') -> int:
        """Calculate approximate zone distance."""
        # If coordinates available, use them
        if all([pickup.latitude, pickup.longitude, delivery.latitude, delivery.longitude]):
            from math import radians, cos, sin, asin, sqrt

            lat1, lon1 = float(pickup.latitude), float(pickup.longitude)
            lat2, lon2 = float(delivery.latitude), float(delivery.longitude)

            # Haversine formula
            lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
            dlat = lat2 - lat1
            dlon = lon2 - lon1
            a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
            km = 2 * asin(sqrt(a)) * 6371  # Earth radius in km

            # Convert km to "zone hops" (roughly 2-3 km per zone)
            return max(1, int(km / 2.5))

        # Fallback: use zone number difference (rough approximation)
        zone_diff = abs(pickup.zone_number - delivery.zone_number)
        return max(1, min(zone_diff // 5, 15))  # Cap at 15 hops

    def _get_historical_average(self, pickup_zone: int, delivery_zone: int) -> Optional[float]:
        """Get historical delivery time average for this route."""
        from delivery.models import DeliveryTask

        # Get completed deliveries for this route from last 30 days
        thirty_days_ago = timezone.now() - timedelta(days=30)

        deliveries = DeliveryTask.objects.filter(
            order__pickup_location__pickup_zone_no=pickup_zone,
            order__dl_zone=delivery_zone,
            dl_task_status='delivered',
            created_at__gte=thirty_days_ago,
            completed_at__isnull=False
        ).exclude(
            completed_at=None
        )

        if deliveries.count() < 5:
            return None

        # Calculate average duration
        total_minutes = 0
        count = 0
        for task in deliveries[:50]:  # Limit to 50 samples
            if task.completed_at and task.created_at:
                duration = (task.completed_at - task.created_at).total_seconds() / 60
                if 5 < duration < 180:  # Reasonable range
                    total_minutes += duration
                    count += 1

        if count > 0:
            return total_minutes / count

        return None


@register_tool
class SuggestDriverTool(BaseTool):
    """
    Suggest the best available driver for a delivery.
    """

    name = 'suggest_driver'
    allowed_roles = ['staff']
    description = '''Suggest the best driver for a delivery based on various factors.

    Considers:
    - Driver's zone preferences
    - Current location/active tasks
    - Driver rating
    - Vehicle type
    - Availability status

    Returns ranked list of available drivers with scores.
    '''

    parameters_schema = {
        'type': 'object',
        'properties': {
            'delivery_zone': {
                'type': 'integer',
                'description': 'Delivery zone number'
            },
            'order_number': {
                'type': 'string',
                'description': 'Order number (alternative to zone)'
            },
            'vehicle_required': {
                'type': 'string',
                'description': 'Required vehicle type (bike, car, van)'
            },
            'limit': {
                'type': 'integer',
                'description': 'Max drivers to return (default 5)',
                'default': 5
            }
        },
    }

    def execute(
        self,
        delivery_zone: Optional[int] = None,
        order_number: Optional[str] = None,
        vehicle_required: Optional[str] = None,
        limit: int = 5
    ) -> Dict[str, Any]:
        from fleet.models import Driver, DriverVehicle
        from delivery.models import ZoneName, ZoneGroup
        from orders.models import Order

        # Get zone from order if provided
        if order_number:
            try:
                order = Order.objects.get(order_number=order_number)
                if order.dl_zone:
                    delivery_zone = order.dl_zone
            except Order.DoesNotExist:
                raise ToolError(f'Order {order_number} not found', 'NOT_FOUND')

        if not delivery_zone:
            raise ToolError('delivery_zone is required', 'MISSING_PARAM')

        # Verify zone exists
        try:
            zone = ZoneName.objects.prefetch_related('zone_groups').get(
                zone_number=delivery_zone
            )
        except ZoneName.DoesNotExist:
            raise ToolError(f'Zone {delivery_zone} not found', 'NOT_FOUND')

        # Get zone groups for this zone
        zone_group_ids = list(zone.zone_groups.values_list('id', flat=True))

        # Query available drivers (approved only)
        drivers = Driver.objects.filter(
            driver_status='approved',
        ).prefetch_related(
            'preferred_zone_groups',
            'driver_vehicle'
        ).select_related('user', 'profile')

        # Filter by vehicle if required
        if vehicle_required:
            vehicle_map = {
                'bike': '2wheeler',
                'motorcycle': '2wheeler',
                'car': '4wheeler',
                'van': '4wheeler',
            }
            vehicle_type = vehicle_map.get(vehicle_required.lower(), vehicle_required)
            drivers = drivers.filter(
                driver_vehicle__vehicle_type=vehicle_type,
                driver_vehicle__vehicle_status='active'
            )

        # Score and rank drivers
        scored_drivers = []
        for driver in drivers[:50]:  # Limit initial pool
            score = self._score_driver(driver, zone, zone_group_ids)
            if score > 0:
                scored_drivers.append({
                    'driver': driver,
                    'score': score,
                })

        # Sort by score
        scored_drivers.sort(key=lambda x: x['score'], reverse=True)

        # Build response
        suggestions = []
        for item in scored_drivers[:limit]:
            driver = item['driver']
            vehicles = list(driver.driver_vehicle.filter(
                vehicle_status='active'
            ).values('vehicle_type', 'vehicle_model', 'vehicle_no')[:1])

            suggestions.append({
                'driver_id': driver.driver_id,
                'driver_code': driver.driver_code,
                'name': driver.user.get_full_name() if driver.user else 'Unknown',
                'phone': driver.driver_phone,
                'rating': driver.driver_rating,
                'score': round(item['score'], 2),
                'vehicles': vehicles,
                'preferred_zones': list(
                    driver.preferred_zone_groups.values_list('name', flat=True)
                ),
                'match_factors': self._get_match_factors(driver, zone, zone_group_ids),
            })

        return {
            'delivery_zone': {
                'number': delivery_zone,
                'name': zone.zone_name,
                'zone_groups': list(zone.zone_groups.values_list('name', flat=True)),
            },
            'suggestions': suggestions,
            'count': len(suggestions),
            'total_available_drivers': drivers.count(),
        }

    def _score_driver(self, driver, zone, zone_group_ids: List[int]) -> float:
        """Calculate driver score for this delivery."""
        score = 50.0  # Base score

        # Zone preference match (+30)
        driver_zone_groups = set(driver.preferred_zone_groups.values_list('id', flat=True))
        if driver_zone_groups:
            if any(zg in driver_zone_groups for zg in zone_group_ids):
                score += 30

        # Rating bonus (+0-20)
        if driver.driver_rating > 0:
            rating_bonus = min(20, driver.driver_rating * 4)
            score += rating_bonus

        # Active tasks penalty
        from delivery.models import DeliveryTask
        active_tasks = DeliveryTask.objects.filter(
            driver_id=driver.driver_id,
            dl_task_status__in=['pending', 'in_transit', 'publish_to_dms']
        ).count()

        if active_tasks > 0:
            score -= (active_tasks * 15)  # -15 per active task

        return max(0, score)

    def _get_match_factors(self, driver, zone, zone_group_ids: List[int]) -> List[str]:
        """Get list of matching factors for this driver."""
        factors = []

        driver_zone_groups = set(driver.preferred_zone_groups.values_list('id', flat=True))
        if any(zg in driver_zone_groups for zg in zone_group_ids):
            factors.append('Zone preference match')

        if driver.driver_rating >= 4:
            factors.append(f'High rating ({driver.driver_rating})')

        from delivery.models import DeliveryTask
        active_tasks = DeliveryTask.objects.filter(
            driver_id=driver.driver_id,
            dl_task_status__in=['pending', 'in_transit', 'publish_to_dms']
        ).count()

        if active_tasks == 0:
            factors.append('No active tasks')

        return factors


@register_tool
class GetDriverStatusTool(BaseTool):
    """
    Get current status of a specific driver.
    """

    name = 'get_driver_status'
    allowed_roles = ['staff', 'driver']
    description = '''Get the current status and workload of a specific driver.

    Returns:
    - Availability status
    - Active tasks count
    - Today's completed deliveries
    - Current location (if available)
    '''

    parameters_schema = {
        'type': 'object',
        'properties': {
            'driver_id': {
                'type': 'integer',
                'description': 'Driver ID'
            },
            'driver_code': {
                'type': 'string',
                'description': 'Driver code (alternative to ID)'
            }
        },
    }

    def run(self, params, user=None, business=None):
        """Override run to force driver users to only see their own data."""
        role = get_user_role(user)
        if role == 'driver' and user:
            from fleet.models import Driver
            try:
                driver = Driver.objects.get(user=user)
                params = {'driver_id': driver.driver_id}
            except Driver.DoesNotExist:
                return {
                    'success': False,
                    'error': 'Driver profile not found',
                    'code': 'NOT_FOUND'
                }
        return super().run(params, user=user, business=business)

    def execute(
        self,
        driver_id: Optional[int] = None,
        driver_code: Optional[str] = None
    ) -> Dict[str, Any]:
        from fleet.models import Driver
        from delivery.models import DeliveryTask

        if not driver_id and not driver_code:
            raise ToolError('Provide driver_id or driver_code', 'MISSING_PARAM')

        try:
            if driver_id:
                driver = Driver.objects.select_related('user', 'profile').get(
                    driver_id=driver_id
                )
            else:
                driver = Driver.objects.select_related('user', 'profile').get(
                    driver_code=driver_code
                )
        except Driver.DoesNotExist:
            raise ToolError('Driver not found', 'NOT_FOUND')

        # Get active tasks
        active_tasks = DeliveryTask.objects.filter(
            driver_id=driver.driver_id,
            dl_task_status__in=['pending', 'in_transit', 'publish_to_dms']
        ).select_related('order')

        # Get today's completed deliveries
        today = timezone.localtime().date()
        today_completed = DeliveryTask.objects.filter(
            driver_id=driver.driver_id,
            dl_task_status='delivered',
            completed_at__date=today
        ).count()

        # Build active tasks list
        active_task_list = []
        for task in active_tasks:
            active_task_list.append({
                'task_id': task.id,
                'order_number': task.order.order_number if task.order else None,
                'status': task.dl_task_status,
                'zone': task.order.dl_zone if task.order else None,
            })

        return {
            'driver': {
                'id': driver.driver_id,
                'code': driver.driver_code,
                'name': driver.user.get_full_name() if driver.user else 'Unknown',
                'phone': driver.driver_phone,
            },
            'status': {
                'approval_status': driver.driver_status,
            },
            'workload': {
                'active_tasks': len(active_task_list),
                'today_completed': today_completed,
                'active_task_details': active_task_list,
            },
            'rating': {
                'score': driver.driver_rating,
                'count': driver.driver_rating_count,
            },
            'preferred_zones': list(
                driver.preferred_zone_groups.values_list('name', flat=True)
            ),
        }
