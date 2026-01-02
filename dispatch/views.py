"""
Dispatch Views - API endpoints and Store Portal views.

Includes:
- Rider API endpoints (REST)
- Store Portal views (HTML)
- HTMX partial views
"""
import logging
from datetime import timedelta

from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.db.models import Count, Sum, Q

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status

from .models import OrderBatch, BatchOrder, RiderShift, RiderKPI, DispatchConfig, DispatchLog
from .serializers import (
    OrderBatchSerializer, OrderBatchListSerializer,
    RiderShiftSerializer, RiderShiftListSerializer,
    BatchOrderSerializer
)

logger = logging.getLogger('dispatch')


# ========================================
# RIDER API ENDPOINTS
# ========================================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def rider_active_batches(request):
    """Get batches assigned to the current rider."""
    from fleet.models import Driver

    try:
        driver = Driver.objects.get(user=request.user)
    except Driver.DoesNotExist:
        return Response(
            {'error': 'Driver profile not found'},
            status=status.HTTP_404_NOT_FOUND
        )

    batches = OrderBatch.objects.filter(
        assigned_rider=driver,
        status__in=['assigned', 'in_progress']
    ).select_related(
        'pickup_location'
    ).prefetch_related(
        'batch_orders__order'
    ).order_by('-assigned_at')

    serializer = OrderBatchSerializer(batches, many=True)
    return Response(serializer.data)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def rider_batch_detail(request, batch_id):
    """Get details of a specific batch."""
    from fleet.models import Driver

    try:
        driver = Driver.objects.get(user=request.user)
    except Driver.DoesNotExist:
        return Response(
            {'error': 'Driver profile not found'},
            status=status.HTTP_404_NOT_FOUND
        )

    try:
        batch = OrderBatch.objects.select_related(
            'pickup_location', 'assigned_shift'
        ).prefetch_related(
            'batch_orders__order'
        ).get(id=batch_id, assigned_rider=driver)
    except OrderBatch.DoesNotExist:
        return Response(
            {'error': 'Batch not found'},
            status=status.HTTP_404_NOT_FOUND
        )

    serializer = OrderBatchSerializer(batch)
    return Response(serializer.data)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def rider_start_batch(request, batch_id):
    """Rider starts delivery for a batch."""
    from fleet.models import Driver

    try:
        driver = Driver.objects.get(user=request.user)
    except Driver.DoesNotExist:
        return Response(
            {'error': 'Driver profile not found'},
            status=status.HTTP_404_NOT_FOUND
        )

    try:
        batch = OrderBatch.objects.get(id=batch_id, assigned_rider=driver)
    except OrderBatch.DoesNotExist:
        return Response(
            {'error': 'Batch not found'},
            status=status.HTTP_404_NOT_FOUND
        )

    if batch.status != 'assigned':
        return Response(
            {'error': f'Cannot start batch in {batch.status} status'},
            status=status.HTTP_400_BAD_REQUEST
        )

    batch.status = 'in_progress'
    batch.save()

    DispatchLog.objects.create(
        action='batch_started',
        batch=batch,
        rider=driver,
        performed_by=request.user,
        details={'started_at': timezone.now().isoformat()}
    )

    logger.info(f"Batch {batch.batch_code} started by rider {driver.driver_code}")
    return Response({'message': 'Batch started', 'batch_code': batch.batch_code})


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def rider_complete_batch(request, batch_id):
    """Rider completes a batch delivery."""
    from fleet.models import Driver

    try:
        driver = Driver.objects.get(user=request.user)
    except Driver.DoesNotExist:
        return Response(
            {'error': 'Driver profile not found'},
            status=status.HTTP_404_NOT_FOUND
        )

    try:
        batch = OrderBatch.objects.get(id=batch_id, assigned_rider=driver)
    except OrderBatch.DoesNotExist:
        return Response(
            {'error': 'Batch not found'},
            status=status.HTTP_404_NOT_FOUND
        )

    if batch.status != 'in_progress':
        return Response(
            {'error': f'Cannot complete batch in {batch.status} status'},
            status=status.HTTP_400_BAD_REQUEST
        )

    now = timezone.now()
    batch.status = 'completed'
    batch.completed_at = now
    batch.save()

    # Update shift stats
    if batch.assigned_shift:
        batch.assigned_shift.batches_completed += 1
        batch.assigned_shift.orders_delivered += batch.order_count
        batch.assigned_shift.save()

    DispatchLog.objects.create(
        action='batch_completed',
        batch=batch,
        rider=driver,
        performed_by=request.user,
        details={
            'completed_at': now.isoformat(),
            'orders_delivered': batch.order_count
        }
    )

    logger.info(f"Batch {batch.batch_code} completed by rider {driver.driver_code}")
    return Response({
        'message': 'Batch completed',
        'batch_code': batch.batch_code,
        'orders_delivered': batch.order_count
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def rider_active_shift(request):
    """Get rider's current active shift."""
    from fleet.models import Driver

    try:
        driver = Driver.objects.get(user=request.user)
    except Driver.DoesNotExist:
        return Response(
            {'error': 'Driver profile not found'},
            status=status.HTTP_404_NOT_FOUND
        )

    shift = RiderShift.objects.filter(
        rider=driver,
        status='active'
    ).select_related('pickup_location').first()

    if shift:
        serializer = RiderShiftSerializer(shift)
        return Response(serializer.data)
    else:
        return Response({'message': 'No active shift', 'shift': None})


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def rider_shifts_list(request):
    """Get rider's scheduled shifts."""
    from fleet.models import Driver

    try:
        driver = Driver.objects.get(user=request.user)
    except Driver.DoesNotExist:
        return Response(
            {'error': 'Driver profile not found'},
            status=status.HTTP_404_NOT_FOUND
        )

    # Get shifts from today onwards
    today = timezone.now().date()
    shifts = RiderShift.objects.filter(
        rider=driver,
        scheduled_start__date__gte=today
    ).select_related('pickup_location').order_by('scheduled_start')[:20]

    serializer = RiderShiftListSerializer(shifts, many=True)
    return Response(serializer.data)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def rider_clock_in(request, shift_id):
    """Rider clocks into their shift."""
    from fleet.models import Driver

    try:
        driver = Driver.objects.get(user=request.user)
    except Driver.DoesNotExist:
        return Response(
            {'error': 'Driver profile not found'},
            status=status.HTTP_404_NOT_FOUND
        )

    try:
        shift = RiderShift.objects.get(id=shift_id, rider=driver)
    except RiderShift.DoesNotExist:
        return Response(
            {'error': 'Shift not found'},
            status=status.HTTP_404_NOT_FOUND
        )

    if shift.status != 'scheduled':
        return Response(
            {'error': f'Cannot clock into shift in {shift.status} status'},
            status=status.HTTP_400_BAD_REQUEST
        )

    now = timezone.now()
    shift.status = 'active'
    shift.actual_start = now
    shift.save()

    DispatchLog.objects.create(
        action='shift_started',
        rider=driver,
        shift=shift,
        performed_by=request.user,
        details={
            'clocked_in_at': now.isoformat(),
            'scheduled_start': shift.scheduled_start.isoformat()
        }
    )

    logger.info(f"Rider {driver.driver_code} clocked into shift {shift.shift_code}")
    return Response({
        'message': 'Clocked in successfully',
        'shift_code': shift.shift_code,
        'pickup_location': shift.pickup_location.pickup_location_title
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def rider_clock_out(request, shift_id):
    """Rider clocks out of their shift."""
    from fleet.models import Driver

    try:
        driver = Driver.objects.get(user=request.user)
    except Driver.DoesNotExist:
        return Response(
            {'error': 'Driver profile not found'},
            status=status.HTTP_404_NOT_FOUND
        )

    try:
        shift = RiderShift.objects.get(id=shift_id, rider=driver)
    except RiderShift.DoesNotExist:
        return Response(
            {'error': 'Shift not found'},
            status=status.HTTP_404_NOT_FOUND
        )

    if shift.status != 'active':
        return Response(
            {'error': f'Cannot clock out of shift in {shift.status} status'},
            status=status.HTTP_400_BAD_REQUEST
        )

    now = timezone.now()
    shift.status = 'completed'
    shift.actual_end = now
    shift.save()

    DispatchLog.objects.create(
        action='shift_ended',
        rider=driver,
        shift=shift,
        performed_by=request.user,
        details={
            'clocked_out_at': now.isoformat(),
            'batches_completed': shift.batches_completed,
            'orders_delivered': shift.orders_delivered
        }
    )

    logger.info(f"Rider {driver.driver_code} clocked out of shift {shift.shift_code}")
    return Response({
        'message': 'Clocked out successfully',
        'shift_code': shift.shift_code,
        'batches_completed': shift.batches_completed,
        'orders_delivered': shift.orders_delivered
    })


# ========================================
# STORE PORTAL VIEWS
# ========================================

@login_required(login_url='/accounts/login/')
def store_dashboard(request):
    """Store manager dashboard - overview of batch activity."""
    # Get user's associated pickup location(s)
    from business.models import PickupLocation

    # For now, get all active pickup locations
    # In production, filter by user's business
    user_locations = PickupLocation.objects.filter(
        pickup_status='active'
    )

    if not user_locations.exists():
        return render(request, 'dispatch/store/no_location.html')

    # Get first location for demo (or use query param)
    location_id = request.GET.get('location')
    if location_id:
        current_location = get_object_or_404(PickupLocation, id=location_id)
    else:
        current_location = user_locations.first()

    # Get batch stats
    now = timezone.now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    batch_stats = OrderBatch.objects.filter(
        pickup_location=current_location,
        created_at__gte=today_start
    ).aggregate(
        total=Count('id'),
        holding=Count('id', filter=Q(status='holding')),
        ready=Count('id', filter=Q(status='ready')),
        assigned=Count('id', filter=Q(status='assigned')),
        in_progress=Count('id', filter=Q(status='in_progress')),
        completed=Count('id', filter=Q(status='completed')),
    )

    # Get active batches
    active_batches = OrderBatch.objects.filter(
        pickup_location=current_location,
        status__in=['holding', 'ready', 'assigned', 'in_progress']
    ).select_related('assigned_rider').prefetch_related(
        'batch_orders__order'
    ).order_by('-created_at')[:20]

    # Get active riders
    active_shifts = RiderShift.objects.filter(
        pickup_location=current_location,
        status='active'
    ).select_related('rider')

    context = {
        'current_location': current_location,
        'user_locations': user_locations,
        'batch_stats': batch_stats,
        'active_batches': active_batches,
        'active_shifts': active_shifts,
        'active_rider_count': active_shifts.count(),
    }

    return render(request, 'dispatch/store/dashboard.html', context)


@login_required(login_url='/accounts/login/')
def store_prep_queue(request):
    """Orders to prepare, grouped by batch."""
    from business.models import PickupLocation

    location_id = request.GET.get('location')
    if location_id:
        current_location = get_object_or_404(PickupLocation, id=location_id)
    else:
        current_location = PickupLocation.objects.filter(pickup_status='active').first()

    if not current_location:
        return render(request, 'dispatch/store/no_location.html')

    # Get batches that need prep (holding, ready, or just assigned)
    prep_batches = OrderBatch.objects.filter(
        pickup_location=current_location,
        status__in=['holding', 'ready', 'assigned']
    ).prefetch_related(
        'batch_orders__order'
    ).order_by('created_at')

    context = {
        'current_location': current_location,
        'prep_batches': prep_batches,
    }

    return render(request, 'dispatch/store/prep_queue.html', context)


@login_required(login_url='/accounts/login/')
def store_riders(request):
    """Riders assigned to this store."""
    from business.models import PickupLocation

    location_id = request.GET.get('location')
    if location_id:
        current_location = get_object_or_404(PickupLocation, id=location_id)
    else:
        current_location = PickupLocation.objects.filter(pickup_status='active').first()

    if not current_location:
        return render(request, 'dispatch/store/no_location.html')

    # Get today's shifts
    today = timezone.now().date()
    shifts = RiderShift.objects.filter(
        pickup_location=current_location,
        scheduled_start__date=today
    ).select_related('rider').order_by('scheduled_start')

    context = {
        'current_location': current_location,
        'shifts': shifts,
    }

    return render(request, 'dispatch/store/riders.html', context)


@login_required(login_url='/accounts/login/')
def store_batches(request):
    """All batches for this store."""
    from business.models import PickupLocation

    location_id = request.GET.get('location')
    if location_id:
        current_location = get_object_or_404(PickupLocation, id=location_id)
    else:
        current_location = PickupLocation.objects.filter(pickup_status='active').first()

    if not current_location:
        return render(request, 'dispatch/store/no_location.html')

    # Filter params
    status_filter = request.GET.get('status', '')
    date_filter = request.GET.get('date', '')

    batches = OrderBatch.objects.filter(
        pickup_location=current_location
    ).select_related('assigned_rider').order_by('-created_at')

    if status_filter:
        batches = batches.filter(status=status_filter)

    if date_filter:
        batches = batches.filter(created_at__date=date_filter)

    # Paginate
    from django.core.paginator import Paginator
    paginator = Paginator(batches, 20)
    page = request.GET.get('page', 1)
    batches = paginator.get_page(page)

    context = {
        'current_location': current_location,
        'batches': batches,
        'status_filter': status_filter,
        'date_filter': date_filter,
        'status_choices': OrderBatch.BATCH_STATUS,
    }

    return render(request, 'dispatch/store/batches.html', context)


# ========================================
# HTMX PARTIAL VIEWS
# ========================================

@login_required(login_url='/accounts/login/')
def store_batch_list_partial(request):
    """HTMX partial for batch list refresh."""
    from business.models import PickupLocation

    location_id = request.GET.get('location')
    if location_id:
        current_location = get_object_or_404(PickupLocation, id=location_id)
    else:
        current_location = PickupLocation.objects.filter(pickup_status='active').first()

    active_batches = OrderBatch.objects.filter(
        pickup_location=current_location,
        status__in=['holding', 'ready', 'assigned', 'in_progress']
    ).select_related('assigned_rider').prefetch_related(
        'batch_orders__order'
    ).order_by('-created_at')[:20]

    return render(request, 'dispatch/store/partials/batch_list.html', {
        'active_batches': active_batches,
    })


@login_required(login_url='/accounts/login/')
def store_prep_queue_partial(request):
    """HTMX partial for prep queue refresh."""
    from business.models import PickupLocation

    location_id = request.GET.get('location')
    if location_id:
        current_location = get_object_or_404(PickupLocation, id=location_id)
    else:
        current_location = PickupLocation.objects.filter(pickup_status='active').first()

    prep_batches = OrderBatch.objects.filter(
        pickup_location=current_location,
        status__in=['holding', 'ready', 'assigned']
    ).prefetch_related(
        'batch_orders__order'
    ).order_by('created_at')

    return render(request, 'dispatch/store/partials/prep_queue.html', {
        'prep_batches': prep_batches,
    })
