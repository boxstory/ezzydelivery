"""
Dispatch Services - Core business logic for order batching and rider assignment.

This module contains:
- BatchService: Order batching logic (create, add, release)
- AssignmentService: Rider assignment algorithm (zone-first, load balancing)
- KPIService: Daily KPI calculation and tracking
"""
import logging
from datetime import timedelta
from decimal import Decimal

from django.db import transaction, models
from django.utils import timezone
from django.conf import settings

logger = logging.getLogger('dispatch')


class BatchService:
    """
    Business logic for batch operations.

    Handles:
    - Creating new batches
    - Adding orders to existing batches
    - Starting and managing hold windows
    - Releasing batches for assignment
    """

    @classmethod
    @transaction.atomic
    def process_order_for_batching(cls, order):
        """
        Main entry point when order is verified.
        Finds or creates a batch and adds the order.

        Args:
            order: Order instance that was just verified

        Returns:
            OrderBatch: The batch the order was added to
        """
        from .models import OrderBatch, DispatchConfig

        # Get config for this pickup location
        config = DispatchConfig.get_config_for_location(order.pickup_location)

        if not config.batching_enabled:
            logger.info(f"Batching disabled for {order.pickup_location}, releasing single")
            batch = cls._create_new_batch(order, config)
            cls._add_order_to_batch(batch, order, config)
            cls.release_batch(batch, 'off_peak')
            return batch

        # Find existing pending/holding batch for same store + zone
        existing_batch = OrderBatch.objects.select_for_update().filter(
            pickup_location=order.pickup_location,
            destination_zone=order.dl_zone,
            status__in=['pending', 'holding'],
            order_count__lt=config.max_batch_size
        ).order_by('created_at').first()

        if existing_batch:
            logger.info(f"Found existing batch {existing_batch.batch_code} for order {order.order_number}")
            cls._add_order_to_batch(existing_batch, order, config)
            return existing_batch
        else:
            logger.info(f"Creating new batch for order {order.order_number}")
            batch = cls._create_new_batch(order, config)
            cls._add_order_to_batch(batch, order, config)
            return batch

    @classmethod
    def _create_new_batch(cls, order, config):
        """Create a new batch for an order."""
        from .models import OrderBatch, DispatchLog

        batch = OrderBatch.objects.create(
            pickup_location=order.pickup_location,
            destination_zone=order.dl_zone,
            status='pending',
            order_count=0
        )

        DispatchLog.objects.create(
            action='batch_created',
            batch=batch,
            order=order,
            details={
                'pickup_location_id': order.pickup_location.id,
                'zone': order.dl_zone,
                'order_number': order.order_number
            }
        )

        # Fire auto flow for batch created
        try:
            from core.auto_flow_executor import execute_flows_for_trigger
            execute_flows_for_trigger('staff_batch_created', extra_context={
                'order_number': order.order_number or '',
                'zone': str(order.dl_zone) if order.dl_zone else '',
                'business_name': str(order.business) if order.business else '',
            })
        except Exception as e:
            logger.warning(f"Auto flow failed for batch created: {e}")

        logger.info(f"Created batch {batch.batch_code} for zone {order.dl_zone}")
        return batch

    @classmethod
    def _add_order_to_batch(cls, batch, order, config):
        """Add order to batch and manage hold window."""
        from .models import BatchOrder, DispatchLog

        # Calculate SLA deadline
        sla_deadline = order.created_at + timedelta(minutes=config.sla_minutes)

        # Create link
        batch_order = BatchOrder.objects.create(
            batch=batch,
            order=order,
            sequence=batch.order_count + 1,
            sla_deadline=sla_deadline
        )

        # Update batch metrics
        batch.order_count += 1
        batch.total_cod += Decimal(str(order.cod_amount or 0))

        # Log
        DispatchLog.objects.create(
            action='order_added',
            batch=batch,
            order=order,
            details={
                'order_number': order.order_number,
                'sequence': batch_order.sequence,
                'sla_deadline': sla_deadline.isoformat()
            }
        )

        # Check if batch is full
        if batch.order_count >= config.max_batch_size:
            logger.info(f"Batch {batch.batch_code} is full, releasing")
            cls.release_batch(batch, 'batch_full')
        elif batch.status == 'pending':
            # Start hold window
            cls._start_hold_window(batch, config)

        batch.save()
        logger.info(f"Added order {order.order_number} to batch {batch.batch_code} (#{batch_order.sequence})")

    @classmethod
    def _start_hold_window(cls, batch, config):
        """Start the hold timer for a batch."""
        now = timezone.now()

        # Adjust hold window based on peak hours
        if config.is_peak_hours():
            # During peak, use max hold window to maximize batching
            hold_duration = config.max_hold_seconds
            logger.debug(f"Peak hours - using max hold window: {hold_duration}s")
        else:
            hold_duration = config.hold_window_seconds

        batch.status = 'holding'
        batch.hold_started_at = now
        batch.hold_expires_at = now + timedelta(seconds=hold_duration)

        logger.info(
            f"Started hold window for batch {batch.batch_code}, "
            f"expires at {batch.hold_expires_at}"
        )

    @classmethod
    @transaction.atomic
    def release_batch(cls, batch, reason):
        """
        Release batch for assignment.

        Args:
            batch: OrderBatch instance
            reason: One of 'batch_full', 'timeout', 'sla_risk', 'manual', 'off_peak'
        """
        from .models import DispatchLog

        batch.status = 'ready'
        batch.release_reason = reason
        batch.released_at = timezone.now()
        batch.save()

        DispatchLog.objects.create(
            action='batch_released',
            batch=batch,
            details={
                'reason': reason,
                'order_count': batch.order_count,
                'total_cod': str(batch.total_cod)
            }
        )

        # Fire auto flow for batch dispatched
        try:
            from core.auto_flow_executor import execute_flows_for_trigger
            execute_flows_for_trigger('staff_batch_dispatched', extra_context={
                'order_number': batch.batch_code or '',
                'zone': str(batch.destination_zone) if batch.destination_zone else '',
            })
        except Exception as e:
            logger.warning(f"Auto flow failed for batch dispatched: {e}")

        logger.info(f"Released batch {batch.batch_code} - reason: {reason}")

    @classmethod
    @transaction.atomic
    def cancel_batch(cls, batch, reason='manual'):
        """Cancel a batch and release its orders."""
        from .models import DispatchLog

        batch.status = 'cancelled'
        batch.save()

        DispatchLog.objects.create(
            action='batch_cancelled',
            batch=batch,
            details={'reason': reason}
        )

        logger.info(f"Cancelled batch {batch.batch_code}")


class AssignmentService:
    """
    Business logic for rider assignment.

    Algorithm priority:
    1. Rider on active shift at batch's pickup location
    2. Current order load < max_orders_per_rider
    3. COD capacity check
    4. Load balancing (least loaded rider)
    5. Zone familiarity bonus (optional)
    """

    @classmethod
    @transaction.atomic
    def auto_assign_batch(cls, batch):
        """
        Auto-assign a batch to the best available rider.

        Args:
            batch: OrderBatch instance in 'ready' status

        Returns:
            bool: True if assignment successful, False otherwise
        """
        from .models import RiderShift, DispatchConfig, DispatchLog

        config = DispatchConfig.get_config_for_location(batch.pickup_location)

        if not config.auto_assignment_enabled:
            logger.info(f"Auto-assignment disabled for {batch.pickup_location}")
            return False

        # Find best available rider
        rider = cls.find_best_rider(batch, config)

        if not rider:
            logger.warning(f"No available rider for batch {batch.batch_code}")
            return False

        # Get active shift
        active_shift = RiderShift.objects.filter(
            rider=rider,
            pickup_location=batch.pickup_location,
            status='active'
        ).first()

        # Assign
        batch.assigned_rider = rider
        batch.assigned_shift = active_shift
        batch.assigned_at = timezone.now()
        batch.status = 'assigned'
        batch.save()

        # Update delivery tasks
        cls._update_delivery_tasks(batch, rider)

        DispatchLog.objects.create(
            action='batch_assigned',
            batch=batch,
            rider=rider,
            shift=active_shift,
            details={
                'rider_code': rider.driver_code,
                'shift_code': active_shift.shift_code if active_shift else None
            }
        )

        logger.info(f"Assigned batch {batch.batch_code} to rider {rider.driver_code}")
        return True

    @classmethod
    def find_best_rider(cls, batch, config):
        """
        Find the best available rider for a batch.

        Algorithm:
        1. Get riders with active shifts at this pickup location
        2. Filter by approval status
        3. Filter by COD capacity
        4. Filter by current load
        5. Sort by load (least loaded first)

        Returns:
            Driver instance or None
        """
        from .models import RiderShift, OrderBatch

        # Get riders with active shifts at this pickup location
        active_shifts = RiderShift.objects.filter(
            pickup_location=batch.pickup_location,
            status='active'
        ).select_related('rider')

        if not active_shifts.exists():
            logger.debug(f"No active shifts at {batch.pickup_location}")
            return None

        available_riders = []

        for shift in active_shifts:
            rider = shift.rider

            # Check rider status
            if rider.driver_status != 'approved':
                logger.debug(f"Rider {rider.driver_code} not approved")
                continue

            # Check COD capacity
            if batch.total_cod > 0:
                available_credit = getattr(rider, 'available_credit', float('inf'))
                if available_credit < float(batch.total_cod):
                    logger.debug(f"Rider {rider.driver_code} insufficient COD capacity")
                    continue

            # Check current load
            active_batches = OrderBatch.objects.filter(
                assigned_rider=rider,
                status__in=['assigned', 'in_progress']
            ).count()

            if active_batches >= config.max_batches_per_rider:
                logger.debug(f"Rider {rider.driver_code} at max batches")
                continue

            active_orders = cls._count_active_orders(rider)
            if active_orders >= config.max_orders_per_rider:
                logger.debug(f"Rider {rider.driver_code} at max orders")
                continue

            available_riders.append({
                'rider': rider,
                'active_batches': active_batches,
                'active_orders': active_orders,
                'shift': shift
            })

        if not available_riders:
            return None

        # Sort by load (least loaded first)
        if config.load_balancing_enabled:
            available_riders.sort(key=lambda x: (x['active_batches'], x['active_orders']))

        best = available_riders[0]
        logger.debug(
            f"Selected rider {best['rider'].driver_code} "
            f"(batches: {best['active_batches']}, orders: {best['active_orders']})"
        )
        return best['rider']

    @classmethod
    def _count_active_orders(cls, rider):
        """Count active orders for a rider across all batches."""
        from .models import OrderBatch

        result = OrderBatch.objects.filter(
            assigned_rider=rider,
            status__in=['assigned', 'in_progress']
        ).aggregate(
            total=models.Sum('order_count')
        )
        return result['total'] or 0

    @classmethod
    def _update_delivery_tasks(cls, batch, rider):
        """Update the DeliveryTasks linked to orders in this batch."""
        from delivery.models import DeliveryTask

        for batch_order in batch.batch_orders.select_related('order').all():
            try:
                task = DeliveryTask.objects.get(order=batch_order.order)
                task.driver = rider
                task.dl_task_status = 'in_transit'
                task.save(update_fields=['driver', 'dl_task_status', 'updated_at'])
                logger.debug(f"Updated delivery task for order {batch_order.order.order_number}")
            except DeliveryTask.DoesNotExist:
                logger.warning(f"No delivery task found for order {batch_order.order.order_number}")


class KPIService:
    """
    Business logic for KPI calculations.

    Tracks:
    - Batching percentage (% of orders delivered in batches)
    - Orders per hour
    - SLA compliance rate
    """

    @classmethod
    def calculate_kpis_for_date(cls, date):
        """
        Calculate and store daily KPIs for all riders with completed shifts.

        Args:
            date: date object for which to calculate KPIs
        """
        from .models import RiderShift

        shifts = RiderShift.objects.filter(
            scheduled_start__date=date,
            status='completed'
        ).select_related('rider', 'pickup_location')

        created_count = 0
        for shift in shifts:
            cls._calculate_rider_kpi(shift.rider, date, shift.pickup_location)
            created_count += 1

        logger.info(f"Calculated KPIs for {created_count} riders on {date}")

    @classmethod
    def _calculate_rider_kpi(cls, rider, date, pickup_location):
        """Calculate KPI for a single rider on a date."""
        from .models import RiderKPI, OrderBatch

        # Get completed batches for this rider on this date
        completed_batches = OrderBatch.objects.filter(
            assigned_rider=rider,
            completed_at__date=date
        ).prefetch_related('batch_orders')

        total_orders = 0
        batched_orders = 0
        batches_with_2 = 0
        sla_compliant = 0
        sla_breached = 0
        total_batches = completed_batches.count()

        for batch in completed_batches:
            total_orders += batch.order_count

            if batch.order_count >= 2:
                batched_orders += batch.order_count
                batches_with_2 += 1

            # Check SLA compliance per order
            for batch_order in batch.batch_orders.all():
                if batch_order.sla_deadline and batch.completed_at:
                    if batch.completed_at <= batch_order.sla_deadline:
                        sla_compliant += 1
                    else:
                        sla_breached += 1

        # Get shift duration for orders_per_hour calculation
        from .models import RiderShift
        shifts = RiderShift.objects.filter(
            rider=rider,
            pickup_location=pickup_location,
            scheduled_start__date=date,
            status='completed'
        )

        total_active_minutes = 0
        for shift in shifts:
            if shift.actual_start and shift.actual_end:
                duration = shift.actual_end - shift.actual_start
                total_active_minutes += int(duration.total_seconds() / 60)
                total_active_minutes -= shift.total_break_minutes

        # Create or update KPI record
        kpi, created = RiderKPI.objects.update_or_create(
            rider=rider,
            date=date,
            pickup_location=pickup_location,
            defaults={
                'total_orders': total_orders,
                'batched_orders': batched_orders,
                'single_orders': total_orders - batched_orders,
                'total_batches': total_batches,
                'batches_with_2_orders': batches_with_2,
                'sla_compliant_orders': sla_compliant,
                'sla_breached_orders': sla_breached,
                'total_active_minutes': total_active_minutes,
            }
        )

        kpi.calculate_metrics()
        kpi.save()

        logger.debug(
            f"KPI for {rider.driver_code} on {date}: "
            f"{total_orders} orders, {kpi.batching_percentage:.1f}% batched"
        )

    @classmethod
    def get_rider_stats(cls, rider, days=7):
        """
        Get aggregated stats for a rider over recent days.

        Args:
            rider: Driver instance
            days: Number of days to look back

        Returns:
            dict with aggregated metrics
        """
        from .models import RiderKPI
        from django.db.models import Avg, Sum

        start_date = timezone.now().date() - timedelta(days=days)

        stats = RiderKPI.objects.filter(
            rider=rider,
            date__gte=start_date
        ).aggregate(
            avg_batching_pct=Avg('batching_percentage'),
            avg_orders_per_hour=Avg('orders_per_hour'),
            avg_sla_compliance=Avg('sla_compliance_rate'),
            total_orders=Sum('total_orders'),
            total_batched=Sum('batched_orders'),
        )

        return {
            'period_days': days,
            'avg_batching_percentage': float(stats['avg_batching_pct'] or 0),
            'avg_orders_per_hour': float(stats['avg_orders_per_hour'] or 0),
            'avg_sla_compliance': float(stats['avg_sla_compliance'] or 0),
            'total_orders': stats['total_orders'] or 0,
            'total_batched_orders': stats['total_batched'] or 0,
        }
