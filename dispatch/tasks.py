"""
Dispatch Celery Tasks - Async task processing for batch timer engine.

Tasks:
- check_batch_timeouts: Release expired holding batches
- check_sla_risk: Force-release SLA-at-risk batches
- auto_assign_ready_batches: Assign ready batches to riders
- check_shift_expirations: Auto-end expired shifts
- calculate_daily_kpis: Daily KPI calculation
- process_verified_order: Process order for batching (triggered by signal)
"""
import logging
from datetime import timedelta

from celery import shared_task
from django.db import transaction
from django.utils import timezone

logger = logging.getLogger('dispatch')


@shared_task(bind=True, max_retries=3, default_retry_delay=5)
def check_batch_timeouts(self):
    """
    Check for batches whose hold window has expired and release them.
    Runs every 30 seconds via Celery Beat.
    """
    from dispatch.models import OrderBatch
    from dispatch.services import BatchService

    try:
        now = timezone.now()

        # Find expired holding batches
        # Use select_for_update with skip_locked to avoid conflicts
        with transaction.atomic():
            expired_batches = OrderBatch.objects.select_for_update(
                skip_locked=True
            ).filter(
                status='holding',
                hold_expires_at__lte=now
            )

            released_count = 0
            for batch in expired_batches:
                try:
                    BatchService.release_batch(batch, reason='timeout')
                    released_count += 1
                except Exception as e:
                    logger.error(f"Error releasing batch {batch.batch_code}: {e}")

        if released_count > 0:
            logger.info(f"Released {released_count} batches due to timeout")

        return {'released': released_count, 'timestamp': now.isoformat()}

    except Exception as e:
        logger.error(f"Error in check_batch_timeouts: {e}")
        raise self.retry(exc=e)


@shared_task(bind=True, max_retries=3, default_retry_delay=5)
def check_sla_risk(self):
    """
    Check for orders at risk of SLA breach and force release their batches.
    Runs every minute via Celery Beat.
    """
    from dispatch.models import OrderBatch, BatchOrder, DispatchConfig
    from dispatch.services import BatchService

    try:
        now = timezone.now()

        # Find batches with SLA-at-risk orders (within buffer minutes of deadline)
        # Only check pending/holding batches
        with transaction.atomic():
            at_risk_batch_ids = BatchOrder.objects.filter(
                batch__status__in=['pending', 'holding'],
                sla_deadline__lte=now + timedelta(minutes=15),  # Default buffer
                is_sla_at_risk=False
            ).values_list('batch_id', flat=True).distinct()

            released_count = 0
            flagged_count = 0

            for batch_id in at_risk_batch_ids:
                try:
                    batch = OrderBatch.objects.select_for_update(
                        skip_locked=True
                    ).get(id=batch_id)

                    # Get config for this location
                    config = DispatchConfig.get_config_for_location(batch.pickup_location)

                    if config.sla_override_enabled:
                        BatchService.release_batch(batch, reason='sla_risk')
                        released_count += 1

                        # Mark orders as SLA at risk
                        BatchOrder.objects.filter(
                            batch=batch,
                            is_sla_at_risk=False
                        ).update(is_sla_at_risk=True)
                        flagged_count += 1

                except OrderBatch.DoesNotExist:
                    continue
                except Exception as e:
                    logger.error(f"Error processing SLA risk for batch {batch_id}: {e}")

        if released_count > 0:
            logger.info(f"Released {released_count} batches due to SLA risk")

        return {
            'released': released_count,
            'flagged': flagged_count,
            'timestamp': now.isoformat()
        }

    except Exception as e:
        logger.error(f"Error in check_sla_risk: {e}")
        raise self.retry(exc=e)


@shared_task(bind=True, max_retries=3, default_retry_delay=5)
def auto_assign_ready_batches(self):
    """
    Auto-assign batches that are ready to available riders.
    Runs every 15 seconds via Celery Beat.
    """
    from dispatch.models import OrderBatch
    from dispatch.services import AssignmentService

    try:
        # Get ready batches, oldest first, limit to 10 per run
        ready_batches = OrderBatch.objects.filter(
            status='ready'
        ).select_related(
            'pickup_location'
        ).order_by('created_at')[:10]

        assigned_count = 0
        failed_count = 0

        for batch in ready_batches:
            try:
                if AssignmentService.auto_assign_batch(batch):
                    assigned_count += 1
                else:
                    failed_count += 1
            except Exception as e:
                logger.error(f"Error assigning batch {batch.batch_code}: {e}")
                failed_count += 1

        if assigned_count > 0:
            logger.info(f"Auto-assigned {assigned_count} batches")

        return {
            'assigned': assigned_count,
            'failed': failed_count,
            'timestamp': timezone.now().isoformat()
        }

    except Exception as e:
        logger.error(f"Error in auto_assign_ready_batches: {e}")
        raise self.retry(exc=e)


@shared_task
def check_shift_expirations():
    """
    End shifts that have passed their scheduled end time.
    Runs every 5 minutes via Celery Beat.
    """
    from dispatch.models import RiderShift, DispatchLog

    try:
        now = timezone.now()

        expired_shifts = RiderShift.objects.filter(
            status='active',
            scheduled_end__lt=now,
            actual_end__isnull=True
        )

        ended_count = 0
        for shift in expired_shifts:
            try:
                shift.status = 'completed'
                shift.actual_end = now
                shift.save()

                DispatchLog.objects.create(
                    action='shift_ended',
                    rider=shift.rider,
                    shift=shift,
                    details={
                        'reason': 'auto_expiration',
                        'scheduled_end': shift.scheduled_end.isoformat(),
                        'actual_end': now.isoformat()
                    }
                )

                ended_count += 1
            except Exception as e:
                logger.error(f"Error ending shift {shift.shift_code}: {e}")

        if ended_count > 0:
            logger.info(f"Auto-ended {ended_count} expired shifts")

        return {'ended': ended_count, 'timestamp': now.isoformat()}

    except Exception as e:
        logger.error(f"Error in check_shift_expirations: {e}")
        return {'error': str(e)}


@shared_task
def calculate_daily_kpis():
    """
    Calculate and store daily KPIs for all active riders.
    Runs daily at 00:05 via Celery Beat.
    """
    from dispatch.services import KPIService

    try:
        yesterday = timezone.now().date() - timedelta(days=1)
        KPIService.calculate_kpis_for_date(yesterday)

        logger.info(f"Calculated KPIs for {yesterday}")
        return {'date': yesterday.isoformat(), 'status': 'success'}

    except Exception as e:
        logger.error(f"Error in calculate_daily_kpis: {e}")
        return {'error': str(e)}


@shared_task(bind=True, max_retries=3, default_retry_delay=10)
def process_verified_order(self, order_id):
    """
    Process a verified order for batching.
    Called asynchronously when an order's verification_status changes to 'verified'.

    Args:
        order_id: ID of the Order to process
    """
    from orders.models import Order
    from dispatch.services import BatchService

    try:
        order = Order.objects.select_related(
            'pickup_location', 'business'
        ).get(id=order_id)

        # Check if order already has a batch assignment
        if hasattr(order, 'batch_assignment'):
            logger.warning(f"Order {order.order_number} already in a batch, skipping")
            return {'status': 'skipped', 'reason': 'already_batched'}

        # Process for batching
        batch = BatchService.process_order_for_batching(order)

        logger.info(
            f"Processed order {order.order_number} for batching, "
            f"batch: {batch.batch_code}"
        )

        return {
            'order_id': order_id,
            'order_number': order.order_number,
            'batch_code': batch.batch_code,
            'batch_status': batch.status
        }

    except Order.DoesNotExist:
        logger.error(f"Order {order_id} not found for batching")
        return {'error': 'order_not_found', 'order_id': order_id}

    except Exception as e:
        logger.error(f"Error processing order {order_id} for batching: {e}")
        raise self.retry(exc=e)


@shared_task
def notify_batch_assigned(batch_id):
    """
    Send notification when batch is assigned to a rider.
    Can integrate with push notifications, WhatsApp, etc.

    Args:
        batch_id: ID of the assigned OrderBatch
    """
    from dispatch.models import OrderBatch

    try:
        batch = OrderBatch.objects.select_related(
            'assigned_rider', 'pickup_location'
        ).prefetch_related(
            'batch_orders__order'
        ).get(id=batch_id)

        if not batch.assigned_rider:
            logger.warning(f"Batch {batch.batch_code} has no assigned rider")
            return {'error': 'no_rider'}

        # TODO: Implement actual notification logic
        # - Push notification to rider app
        # - WhatsApp message to store
        # - Update DMS

        order_numbers = [
            bo.order.order_number
            for bo in batch.batch_orders.all()
        ]

        logger.info(
            f"Notification: Batch {batch.batch_code} assigned to "
            f"{batch.assigned_rider.driver_code}, orders: {order_numbers}"
        )

        return {
            'batch_code': batch.batch_code,
            'rider_code': batch.assigned_rider.driver_code,
            'orders': order_numbers
        }

    except OrderBatch.DoesNotExist:
        logger.error(f"Batch {batch_id} not found for notification")
        return {'error': 'batch_not_found'}


@shared_task
def notify_batch_completed(batch_id):
    """
    Handle batch completion notifications and updates.

    Args:
        batch_id: ID of the completed OrderBatch
    """
    from dispatch.models import OrderBatch

    try:
        batch = OrderBatch.objects.select_related(
            'assigned_rider', 'assigned_shift'
        ).get(id=batch_id)

        # Update shift stats
        if batch.assigned_shift:
            batch.assigned_shift.batches_completed += 1
            batch.assigned_shift.orders_delivered += batch.order_count
            batch.assigned_shift.save()

        logger.info(f"Batch {batch.batch_code} completed successfully")

        return {
            'batch_code': batch.batch_code,
            'orders_delivered': batch.order_count
        }

    except OrderBatch.DoesNotExist:
        logger.error(f"Batch {batch_id} not found")
        return {'error': 'batch_not_found'}
