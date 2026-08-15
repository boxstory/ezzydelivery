"""
Delivery Celery Tasks - Periodic health checks for delivery operations.

Tasks:
- check_delivery_task_health: Monitor stale deliveries, GPS heartbeat, COD issues
"""
import logging
from datetime import timedelta

from celery import shared_task
from django.utils import timezone

logger = logging.getLogger('delivery')


@shared_task(bind=True, max_retries=1)
def check_delivery_task_health(self):
    """
    Periodic health check for delivery tasks — runs every 5 minutes.

    Checks:
    - Fix 3: Stale deliveries (active status > 4 hours)
    - Fix 21: Non-reachable > 30 minutes
    - Fix 2: GPS heartbeat — no location ping for 10+ min during active delivery
    - Fix 9: Inactive driver with COD > 24 hours
    """
    from delivery.models import DeliveryTask
    from fleet.models import Driver, DriverLocation, DriverActivityLog
    # Same set the driver PWA uses to pick its high-accuracy GPS profile — if
    # this alert watched a wider set it would fire for drivers the app is
    # deliberately tracking at the cheap idle rate.
    from core.context_processors import DRIVER_ON_DUTY_STATUSES

    now = timezone.now()
    alerts = []

    # Fix 3: Stale deliveries (active status > 4 hours)
    try:
        stale = DeliveryTask.objects.filter(
            dl_task_status__in=['out_for_delivery', 'in_transit', 'start_ride'],
            updated_at__lt=now - timedelta(hours=4),
            dl_task_publish=True,
        ).select_related('driver', 'order')
        for task in stale[:20]:
            hours = (now - task.updated_at).total_seconds() / 3600
            logger.warning(
                f"STALE DELIVERY: Task {task.dl_task_number} in "
                f"'{task.dl_task_status}' for {hours:.1f} hours. "
                f"Driver: {task.driver}"
            )
            alerts.append(f'stale:{task.dl_task_number}')
    except Exception as e:
        logger.error(f"Error checking stale deliveries: {e}")

    # Fix 21: Non-reachable > 30 minutes
    try:
        stuck = DeliveryTask.objects.filter(
            dl_task_status='non_reachable',
            updated_at__lt=now - timedelta(minutes=30),
            dl_task_publish=True,
        ).select_related('driver', 'order')
        for task in stuck[:20]:
            mins = (now - task.updated_at).total_seconds() / 60
            order_num = task.order.order_number if task.order else 'N/A'
            logger.warning(
                f"NON-REACHABLE TIMEOUT: Task {task.dl_task_number} "
                f"non-reachable for {mins:.0f} min. Order: {order_num}"
            )
            alerts.append(f'non_reachable:{task.dl_task_number}')
    except Exception as e:
        logger.error(f"Error checking non-reachable tasks: {e}")

    # Fix 2: GPS heartbeat — no location ping for 10+ min during active delivery
    try:
        active_tasks = DeliveryTask.objects.filter(
            dl_task_status__in=DRIVER_ON_DUTY_STATUSES,
            driver__isnull=False,
            dl_task_publish=True,
        ).select_related('driver')
        for task in active_tasks[:30]:
            # Contact recency, so this must stay on created_at: a parked driver
            # whose phone keeps returning the same cached fix is still checking
            # in, and is not the outage this alert is for.
            latest_loc = DriverLocation.objects.filter(
                driver=task.driver
            ).order_by('-created_at').first()
            if latest_loc and latest_loc.created_at < now - timedelta(minutes=10):
                mins_ago = (now - latest_loc.created_at).total_seconds() / 60
                logger.warning(
                    f"GPS LOST: No GPS ping for {mins_ago:.0f} min from "
                    f"driver {task.driver} during active delivery {task.dl_task_number}"
                )
                alerts.append(f'gps_lost:{task.dl_task_number}')
    except Exception as e:
        logger.error(f"Error checking GPS heartbeat: {e}")

    # Fix 9: Inactive driver with COD > 24 hours
    try:
        drivers_with_cod = Driver.objects.filter(
            cod_in_hand__gt=0,
            driver_availability='offline',
        )
        for d in drivers_with_cod[:10]:
            last_log = DriverActivityLog.objects.filter(
                driver=d
            ).order_by('-created_at').first()
            if last_log and last_log.created_at < now - timedelta(hours=24):
                logger.warning(
                    f"INACTIVE DRIVER WITH COD: {d.user.first_name} "
                    f"(code: {d.driver_code}) offline 24h+ with "
                    f"{d.cod_in_hand} QAR COD in hand"
                )
                alerts.append(f'cod_inactive:{d.driver_code}')
    except Exception as e:
        logger.error(f"Error checking inactive drivers with COD: {e}")

    return f'Health check: {len(alerts)} alerts' if alerts else 'Health check: all clear'
