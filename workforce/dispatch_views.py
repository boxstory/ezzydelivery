"""
Workforce Dispatch Views - Batch monitoring and shift management for dispatchers/staff.

Integrates dispatch functionality into the workforce dashboard.
"""
import logging
from datetime import timedelta

from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from core.decorators import staff_required
from django.contrib import messages
from django.http import JsonResponse
from django.utils import timezone
from django.db.models import Count, Sum, Avg, Q
from django.db import transaction
from django.core.paginator import Paginator

from dispatch.models import (
    OrderBatch, BatchOrder, RiderShift, RiderKPI, DispatchConfig, DispatchLog
)
from dispatch.services import BatchService
from business.models import PickupLocation
from fleet.models import Driver

logger = logging.getLogger('dispatch')


# ========================================
# DISPATCH DASHBOARD
# ========================================

@login_required(login_url='/accounts/login/')
@staff_required
def dispatch_dashboard(request):
    """Main dispatch operations dashboard for workforce staff."""
    now = timezone.now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    # Batch stats
    batch_stats = OrderBatch.objects.filter(
        created_at__gte=today_start
    ).aggregate(
        total=Count('id'),
        holding=Count('id', filter=Q(status='holding')),
        ready=Count('id', filter=Q(status='ready')),
        assigned=Count('id', filter=Q(status='assigned')),
        in_progress=Count('id', filter=Q(status='in_progress')),
        completed=Count('id', filter=Q(status='completed')),
        total_orders=Sum('order_count', filter=Q(status='completed')),
    )

    # Active batches (for monitoring)
    active_batches = OrderBatch.objects.filter(
        status__in=['holding', 'ready', 'assigned', 'in_progress']
    ).select_related(
        'pickup_location', 'assigned_rider'
    ).prefetch_related(
        'batch_orders__order'
    ).order_by('-created_at')[:30]

    # Active shifts
    active_shifts = RiderShift.objects.filter(
        status='active'
    ).select_related('rider', 'pickup_location')

    # Pickup locations with batching enabled - show fulfillment stores first
    locations = PickupLocation.objects.filter(
        pickup_status='active'
    ).prefetch_related('dispatch_config').order_by('-is_fulfilment_center', 'pickup_location_title')

    # Recent logs
    recent_logs = DispatchLog.objects.select_related(
        'batch', 'rider', 'performed_by'
    ).order_by('-created_at')[:20]

    context = {
        'batch_stats': batch_stats,
        'active_batches': active_batches,
        'active_shifts': active_shifts,
        'active_rider_count': active_shifts.count(),
        'locations': locations,
        'recent_logs': recent_logs,
    }

    return render(request, 'workforce/dispatch/dashboard.html', context)


# ========================================
# BATCH MANAGEMENT
# ========================================

@login_required(login_url='/accounts/login/')
@staff_required
def batch_list(request):
    """List all batches with filtering."""
    batches = OrderBatch.objects.select_related(
        'pickup_location', 'assigned_rider'
    ).order_by('-created_at')

    # Filters
    status_filter = request.GET.get('status', '')
    location_filter = request.GET.get('location', '')
    date_filter = request.GET.get('date', '')

    if status_filter:
        batches = batches.filter(status=status_filter)
    if location_filter:
        try:
            location_id = int(location_filter)
            batches = batches.filter(pickup_location_id=location_id)
        except (ValueError, TypeError):
            pass  # Invalid location filter, skip filtering
    if date_filter:
        batches = batches.filter(created_at__date=date_filter)

    # Pagination
    paginator = Paginator(batches, 25)
    page = request.GET.get('page', 1)
    batches = paginator.get_page(page)

    # Get locations for filter dropdown
    # Show fulfillment stores first when fulfillment service is enabled
    locations = PickupLocation.objects.filter(
        pickup_status='active'
    ).order_by('-is_fulfilment_center', 'pickup_location_title')

    context = {
        'batches': batches,
        'locations': locations,
        'status_filter': status_filter,
        'location_filter': location_filter,
        'date_filter': date_filter,
        'status_choices': OrderBatch.BATCH_STATUS,
    }

    return render(request, 'workforce/dispatch/batch_list.html', context)


@login_required(login_url='/accounts/login/')
@staff_required
def batch_detail(request, batch_id):
    """View batch details."""
    batch = get_object_or_404(
        OrderBatch.objects.select_related(
            'pickup_location', 'assigned_rider', 'assigned_shift'
        ).prefetch_related(
            'batch_orders__order',
            'logs__performed_by'
        ),
        id=batch_id
    )

    batch_orders = batch.batch_orders.select_related('order').order_by('sequence')
    logs = batch.logs.select_related('rider', 'performed_by').order_by('-created_at')

    context = {
        'batch': batch,
        'batch_orders': batch_orders,
        'logs': logs,
    }

    return render(request, 'workforce/dispatch/batch_detail.html', context)


@login_required(login_url='/accounts/login/')
@staff_required
def manual_release_batch(request, batch_id):
    """Manually release a holding batch."""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    try:
        with transaction.atomic():
            # Lock the batch row to prevent concurrent modifications
            batch = OrderBatch.objects.select_for_update().filter(id=batch_id).first()
            if not batch:
                return JsonResponse({'error': 'Batch not found'}, status=404)

            if batch.status not in ['pending', 'holding']:
                return JsonResponse(
                    {'error': f'Cannot release batch in {batch.status} status'},
                    status=400
                )

            BatchService.release_batch(batch, reason='manual')

            DispatchLog.objects.create(
                action='manual_override',
                batch=batch,
                performed_by=request.user,
                details={'action': 'manual_release'}
            )

        messages.success(request, f'Batch {batch.batch_code} released successfully.')

        if request.headers.get('HX-Request'):
            return render(request, 'workforce/dispatch/partials/batch_card.html', {'batch': batch})

        return redirect('workforce:dispatch_batch_detail', batch_id=batch_id)
    except Exception as e:
        logger.error(f"Error releasing batch {batch_id}: {e}")
        return JsonResponse({'error': 'Failed to release batch'}, status=500)


@login_required(login_url='/accounts/login/')
@staff_required
def cancel_batch(request, batch_id):
    """Cancel a batch."""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    try:
        with transaction.atomic():
            # Lock the batch row to prevent concurrent modifications
            batch = OrderBatch.objects.select_for_update().filter(id=batch_id).first()
            if not batch:
                return JsonResponse({'error': 'Batch not found'}, status=404)

            if batch.status in ['completed', 'cancelled']:
                return JsonResponse(
                    {'error': f'Cannot cancel batch in {batch.status} status'},
                    status=400
                )

            BatchService.cancel_batch(batch, reason='manual')

            DispatchLog.objects.create(
                action='batch_cancelled',
                batch=batch,
                performed_by=request.user,
                details={'reason': 'manual_cancellation'}
            )

        messages.success(request, f'Batch {batch.batch_code} cancelled.')
        return redirect('workforce:dispatch_batch_list')
    except Exception as e:
        logger.error(f"Error cancelling batch {batch_id}: {e}")
        return JsonResponse({'error': 'Failed to cancel batch'}, status=500)


# ========================================
# SHIFT MANAGEMENT
# ========================================

@login_required(login_url='/accounts/login/')
@staff_required
def shift_list(request):
    """List all shifts with filtering."""
    shifts = RiderShift.objects.select_related(
        'rider', 'pickup_location', 'created_by'
    ).order_by('-scheduled_start')

    # Filters
    status_filter = request.GET.get('status', '')
    location_filter = request.GET.get('location', '')
    date_filter = request.GET.get('date', '')

    if status_filter:
        shifts = shifts.filter(status=status_filter)
    if location_filter:
        try:
            location_id = int(location_filter)
            shifts = shifts.filter(pickup_location_id=location_id)
        except (ValueError, TypeError):
            pass  # Invalid location filter, skip filtering
    if date_filter:
        shifts = shifts.filter(scheduled_start__date=date_filter)
    else:
        # Default to today and future
        today = timezone.now().date()
        shifts = shifts.filter(scheduled_start__date__gte=today)

    # Pagination
    paginator = Paginator(shifts, 25)
    page = request.GET.get('page', 1)
    shifts = paginator.get_page(page)

    # Get data for filter dropdowns
    # Show fulfillment stores first when fulfillment service is enabled
    locations = PickupLocation.objects.filter(
        pickup_status='active'
    ).order_by('-is_fulfilment_center', 'pickup_location_title')
    riders = Driver.objects.filter(driver_status='Approved').select_related('user')

    # Get today for template default value
    today_date = timezone.now().date()

    context = {
        'shifts': shifts,
        'locations': locations,
        'riders': riders,
        'status_filter': status_filter,
        'location_filter': location_filter,
        'date_filter': date_filter,
        'status_choices': RiderShift.SHIFT_STATUS,
        'today': today_date.isoformat(),
    }

    return render(request, 'workforce/dispatch/shift_list.html', context)


@login_required(login_url='/accounts/login/')
@staff_required
def shift_create(request):
    """Create a new shift."""
    if request.method == 'POST':
        rider_id = request.POST.get('rider')
        location_id = request.POST.get('pickup_location')
        shift_type = request.POST.get('shift_type', 'custom')
        scheduled_start_str = request.POST.get('scheduled_start')
        scheduled_end_str = request.POST.get('scheduled_end')

        # Validate required fields
        if not rider_id or not location_id or not scheduled_start_str or not scheduled_end_str:
            messages.error(request, 'All fields are required.')
            return redirect('workforce:dispatch_shift_create')

        # Validate shift_type
        valid_shift_types = [choice[0] for choice in RiderShift.SHIFT_TYPE]
        if shift_type not in valid_shift_types:
            messages.error(request, 'Invalid shift type.')
            return redirect('workforce:dispatch_shift_create')

        # Parse and validate datetime values
        try:
            from datetime import datetime
            # Try common datetime formats
            for fmt in ['%Y-%m-%dT%H:%M', '%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M']:
                try:
                    scheduled_start = datetime.strptime(scheduled_start_str, fmt)
                    break
                except ValueError:
                    continue
            else:
                raise ValueError('Invalid start time format')

            for fmt in ['%Y-%m-%dT%H:%M', '%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M']:
                try:
                    scheduled_end = datetime.strptime(scheduled_end_str, fmt)
                    break
                except ValueError:
                    continue
            else:
                raise ValueError('Invalid end time format')

            # Validate end time is after start time
            if scheduled_end <= scheduled_start:
                messages.error(request, 'End time must be after start time.')
                return redirect('workforce:dispatch_shift_create')

        except ValueError as e:
            messages.error(request, f'Invalid datetime format: {e}')
            return redirect('workforce:dispatch_shift_create')

        try:
            rider = Driver.objects.get(driver_id=rider_id)
            location = PickupLocation.objects.get(id=location_id)

            shift = RiderShift.objects.create(
                rider=rider,
                pickup_location=location,
                shift_type=shift_type,
                scheduled_start=scheduled_start,
                scheduled_end=scheduled_end,
                created_by=request.user
            )

            DispatchLog.objects.create(
                action='shift_started',
                rider=rider,
                shift=shift,
                performed_by=request.user,
                details={'action': 'shift_created'}
            )

            messages.success(request, f'Shift {shift.shift_code} created successfully.')
            return redirect('workforce:dispatch_shift_list')

        except (Driver.DoesNotExist, PickupLocation.DoesNotExist):
            messages.error(request, 'Invalid rider or location selected.')

    # GET request - show form
    # Show fulfillment stores first when fulfillment service is enabled
    locations = PickupLocation.objects.filter(
        pickup_status='active'
    ).order_by('-is_fulfilment_center', 'pickup_location_title')
    riders = Driver.objects.filter(driver_status='Approved').select_related('user')

    context = {
        'locations': locations,
        'riders': riders,
        'shift_types': RiderShift.SHIFT_TYPE,
    }

    return render(request, 'workforce/dispatch/shift_form.html', context)


@login_required(login_url='/accounts/login/')
@staff_required
def shift_detail(request, shift_id):
    """View shift details."""
    shift = get_object_or_404(
        RiderShift.objects.select_related(
            'rider__user', 'pickup_location', 'created_by'
        ).prefetch_related(
            'batches', 'logs'
        ),
        id=shift_id
    )

    # Get batches completed during this shift
    batches = OrderBatch.objects.filter(
        assigned_shift=shift
    ).select_related('pickup_location').order_by('-assigned_at')

    context = {
        'shift': shift,
        'batches': batches,
    }

    return render(request, 'workforce/dispatch/shift_detail.html', context)


@login_required(login_url='/accounts/login/')
@staff_required
def shift_edit(request, shift_id):
    """Edit a shift."""
    shift = get_object_or_404(RiderShift, id=shift_id)

    if request.method == 'POST':
        from datetime import datetime

        # Validate shift_type
        shift_type = request.POST.get('shift_type', shift.shift_type)
        valid_shift_types = [choice[0] for choice in RiderShift.SHIFT_TYPE]
        if shift_type not in valid_shift_types:
            messages.error(request, 'Invalid shift type.')
            return redirect('workforce:dispatch_shift_edit', shift_id=shift_id)

        # Validate status
        status = request.POST.get('status', shift.status)
        valid_statuses = [choice[0] for choice in RiderShift.SHIFT_STATUS]
        if status not in valid_statuses:
            messages.error(request, 'Invalid status.')
            return redirect('workforce:dispatch_shift_edit', shift_id=shift_id)

        # Parse datetime values if provided
        scheduled_start_str = request.POST.get('scheduled_start')
        scheduled_end_str = request.POST.get('scheduled_end')

        scheduled_start = shift.scheduled_start
        scheduled_end = shift.scheduled_end

        if scheduled_start_str:
            for fmt in ['%Y-%m-%dT%H:%M', '%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M']:
                try:
                    scheduled_start = datetime.strptime(scheduled_start_str, fmt)
                    break
                except ValueError:
                    continue
            else:
                messages.error(request, 'Invalid start time format.')
                return redirect('workforce:dispatch_shift_edit', shift_id=shift_id)

        if scheduled_end_str:
            for fmt in ['%Y-%m-%dT%H:%M', '%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M']:
                try:
                    scheduled_end = datetime.strptime(scheduled_end_str, fmt)
                    break
                except ValueError:
                    continue
            else:
                messages.error(request, 'Invalid end time format.')
                return redirect('workforce:dispatch_shift_edit', shift_id=shift_id)

        # Validate end time is after start time
        if scheduled_end <= scheduled_start:
            messages.error(request, 'End time must be after start time.')
            return redirect('workforce:dispatch_shift_edit', shift_id=shift_id)

        shift.shift_type = shift_type
        shift.scheduled_start = scheduled_start
        shift.scheduled_end = scheduled_end
        shift.status = status
        shift.save()

        messages.success(request, f'Shift {shift.shift_code} updated.')
        return redirect('workforce:dispatch_shift_detail', shift_id=shift_id)

    # Show fulfillment stores first when fulfillment service is enabled
    locations = PickupLocation.objects.filter(
        pickup_status='active'
    ).order_by('-is_fulfilment_center', 'pickup_location_title')
    riders = Driver.objects.filter(driver_status='Approved').select_related('user')

    context = {
        'shift': shift,
        'locations': locations,
        'riders': riders,
        'shift_types': RiderShift.SHIFT_TYPE,
        'status_choices': RiderShift.SHIFT_STATUS,
    }

    return render(request, 'workforce/dispatch/shift_form.html', context)


# ========================================
# KPI DASHBOARD
# ========================================

@login_required(login_url='/accounts/login/')
@staff_required
def kpi_dashboard(request):
    """KPI overview dashboard."""
    # Get selected date or default to today
    date_str = request.GET.get('date', '')
    location_filter = request.GET.get('location', '')

    if date_str:
        from datetime import datetime
        try:
            selected_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            selected_date = timezone.now().date()
    else:
        selected_date = timezone.now().date()

    # Filter KPIs
    kpis = RiderKPI.objects.filter(
        date=selected_date
    ).select_related('rider', 'rider__user', 'pickup_location')

    if location_filter:
        try:
            location_id = int(location_filter)
            kpis = kpis.filter(pickup_location_id=location_id)
        except (ValueError, TypeError):
            pass  # Invalid location filter, skip filtering

    kpis = kpis.order_by('-total_orders')

    # Summary stats for the selected date
    summary = kpis.aggregate(
        total_orders=Sum('total_orders'),
        total_batched=Sum('batched_orders'),
        batching_percentage=Avg('batching_percentage'),
        sla_compliance=Avg('sla_compliance_rate'),
        avg_orders_per_hour=Avg('orders_per_hour'),
    )

    # Get locations for filter dropdown
    # Show fulfillment stores first when fulfillment service is enabled
    locations = PickupLocation.objects.filter(
        pickup_status='active'
    ).order_by('-is_fulfilment_center', 'pickup_location_title')

    context = {
        'kpis': kpis,
        'summary': summary,
        'selected_date': selected_date,
        'locations': locations,
    }

    return render(request, 'workforce/dispatch/kpi_dashboard.html', context)


@login_required(login_url='/accounts/login/')
@staff_required
def rider_kpi_detail(request, rider_id):
    """View KPI details for a specific rider."""
    rider = get_object_or_404(
        Driver.objects.select_related('user'),
        driver_id=rider_id
    )

    # Get KPIs for last 30 days
    thirty_days_ago = timezone.now().date() - timedelta(days=30)
    kpis = RiderKPI.objects.filter(
        rider=rider,
        date__gte=thirty_days_ago
    ).select_related('pickup_location').order_by('-date')

    # Aggregates
    stats = kpis.aggregate(
        avg_batching=Avg('batching_percentage'),
        avg_orders_hour=Avg('orders_per_hour'),
        avg_sla=Avg('sla_compliance_rate'),
        total_orders=Sum('total_orders'),
        total_batched=Sum('batched_orders'),
    )

    context = {
        'rider': rider,
        'kpis': kpis,
        'stats': stats,
    }

    return render(request, 'workforce/dispatch/rider_kpi_detail.html', context)


# ========================================
# CONFIG MANAGEMENT
# ========================================

@login_required(login_url='/accounts/login/')
@staff_required
def config_list(request):
    """List all dispatch configs."""
    configs = DispatchConfig.objects.select_related(
        'pickup_location'
    ).order_by('pickup_location__pickup_location_title')

    context = {
        'configs': configs,
    }

    return render(request, 'workforce/dispatch/config_list.html', context)


@login_required(login_url='/accounts/login/')
@staff_required
def config_edit(request, location_id):
    """Edit dispatch config for a location."""
    location = get_object_or_404(PickupLocation, id=location_id)
    config = DispatchConfig.get_config_for_location(location)

    if request.method == 'POST':
        # Update config fields with safe int conversion
        try:
            config.max_batch_size = int(request.POST.get('max_batch_size', 2))
        except (ValueError, TypeError):
            config.max_batch_size = 2
        try:
            config.hold_window_seconds = int(request.POST.get('hold_window_seconds', 180))
        except (ValueError, TypeError):
            config.hold_window_seconds = 180
        try:
            config.sla_minutes = int(request.POST.get('sla_minutes', 60))
        except (ValueError, TypeError):
            config.sla_minutes = 60
        try:
            config.sla_buffer_minutes = int(request.POST.get('sla_buffer_minutes', 15))
        except (ValueError, TypeError):
            config.sla_buffer_minutes = 15
        try:
            config.max_orders_per_rider = int(request.POST.get('max_orders_per_rider', 2))
        except (ValueError, TypeError):
            config.max_orders_per_rider = 2
        config.batching_enabled = request.POST.get('batching_enabled') == 'on'
        config.auto_assignment_enabled = request.POST.get('auto_assignment_enabled') == 'on'
        config.save()

        DispatchLog.objects.create(
            action='config_changed',
            performed_by=request.user,
            details={
                'location_id': location_id,
                'changes': 'config_updated'
            }
        )

        messages.success(request, f'Config updated for {location.pickup_location_title}')
        return redirect('workforce:dispatch_config_list')

    context = {
        'location': location,
        'config': config,
    }

    return render(request, 'workforce/dispatch/config_form.html', context)


# ========================================
# HTMX PARTIALS
# ========================================

@login_required(login_url='/accounts/login/')
@staff_required
def batch_monitor_partial(request):
    """HTMX partial for real-time batch monitoring."""
    active_batches = OrderBatch.objects.filter(
        status__in=['holding', 'ready', 'assigned', 'in_progress']
    ).select_related(
        'pickup_location', 'assigned_rider'
    ).prefetch_related(
        'batch_orders__order'
    ).order_by('-created_at')[:30]

    return render(request, 'workforce/dispatch/partials/batch_monitor.html', {
        'active_batches': active_batches,
    })


@login_required(login_url='/accounts/login/')
@staff_required
def shift_status_partial(request):
    """HTMX partial for shift status overview."""
    active_shifts = RiderShift.objects.filter(
        status='active'
    ).select_related('rider', 'pickup_location')

    return render(request, 'workforce/dispatch/partials/shift_status.html', {
        'active_shifts': active_shifts,
    })
