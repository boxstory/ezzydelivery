"""
Delivery Tools

Tools for driver status.
"""

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from django.db.models import Q, Count, Avg
from django.utils import timezone

from ai_agent.tools.base import BaseTool, ToolError, register_tool, get_user_role

logger = logging.getLogger(__name__)


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
