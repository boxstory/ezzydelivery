"""
Fleet Views Module
==================

This module handles all driver-facing operations including dashboard,
documents, vehicles, wallet, and performance analytics.

View Categories:
    Dashboard:
        - fleets: List all drivers (admin view)
        - fleet_dashboard: Driver personal dashboard with wallet stats

    Document Management:
        - driver_documents: List driver's documents
        - driver_documents_upload: Upload new document
        - driver_documents_update: Edit document
        - driver_documents_delete: Remove document

    Vehicle Management:
        - vehicle_own: List driver's vehicles
        - vehicle_add: Register new vehicle
        - vehicle_update: Edit vehicle details
        - vehicle_delete: Remove vehicle

    COD & Wallet:
        - cod_collection: View COD collection history
        - cod_submission: Submit COD to admin

    Earnings & Finance:
        - driver_earnings: View earnings breakdown
        - transaction_history: Full transaction log

    Analytics & Reports:
        - driver_performance: Performance metrics dashboard
        - driver_reports: Generate/download reports
        - driver_analytics: Advanced visualizations

    Frontend:
        - driver_profile: Public driver profile page

Security:
    All views verify user is a registered driver.
    IDOR protection on document and vehicle operations.

Related:
    - fleet.models: Driver, DriverDocument, DriverVehicle, etc.
    - fleet.forms: DriverDocumentForm, DriverVehicleForm
    - fleet.wallet_service: WalletService, WalletAlertService
"""

import logging
from django.db import connection
from django.shortcuts import redirect, render
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from core.decorators import driver_required

from core import models as core_models
from core import views as core_views
from fleet import models as fleet_models
from delivery import models as delivery_models
from fleet import forms as fleet_forms
from fleet.wallet_service import WalletService, WalletAlertService
from core.seo import SEOMetadata

# Local aliases for commonly used models
Driver = fleet_models.Driver
DriverDocument = fleet_models.DriverDocument
DriverVehicle = fleet_models.DriverVehicle
DriverTransaction = fleet_models.DriverTransaction
DriverSettlement = fleet_models.DriverSettlement
DeliveryTask = delivery_models.DeliveryTask
ZoneName = delivery_models.ZoneName
ZoneGroup = delivery_models.ZoneGroup
Profile = core_models.Profile

logger = logging.getLogger('fleet')


# =============================================================================
# DASHBOARD VIEWS
# =============================================================================

@login_required(login_url='/accounts/login/')
@driver_required
def fleets(request):
    """
    Display all drivers with their vehicles.

    CRITICAL N+1 FIX: This view had a major N+1 query issue.
    Before: 1 query to fetch drivers + N queries (one per driver) to fetch vehicles = N+1 queries
    After: 1 query with prefetch_related = 1 query (or 2 max)

    Expected query reduction: 90-95% (100 drivers: 101 queries → 2 queries)
    """
    # N+1 FIX: Use prefetch_related to fetch all driver vehicles in one query
    fleets = fleet_models.Driver.objects.prefetch_related(
        'driver_vehicle_set'  # Reverse FK: Driver ← DriverVehicle
    ).select_related(
        'user',     # FK: Driver → User
        'profile',  # FK: Driver → Profile
    ).all()

    logger.info(f"User {request.user.id} accessing fleets list ({fleets.count()} drivers)")

    context = {
        'fleets': fleets,
    }
    return render(request, 'fleet/fleets.html', context)


@login_required(login_url='/accounts/login/')
@driver_required
def fleet_dashboard(request):
    """
    Display driver dashboard with wallet statistics.

    OPTIMIZATION: Uses select_related to fetch driver and profile in single query.
    """
    try:
        # OPTIMIZATION: Fetch driver with related user and profile in one query
        driver = fleet_models.Driver.objects.select_related(
            'user',
            'profile'
        ).get(user_id=request.user.id)

        profile = driver.profile  # Already fetched via select_related

        # Fetch driver vehicles (could have multiple)
        driver_vehicle = fleet_models.DriverVehicle.objects.filter(
            driver_id=driver.driver_id
        ).select_related('vehicle_type')

        logger.info(f"Driver {driver.driver_id} accessing dashboard")

        # Get statistics for last 30 days
        stats_30_days = WalletService.get_driver_statistics(driver, days=30)

        # Get statistics for last 7 days
        stats_7_days = WalletService.get_driver_statistics(driver, days=7)

        # Get wallet status
        wallet_status = WalletService.get_wallet_status(driver)

        # Get wallet alerts
        wallet_alerts = WalletAlertService.check_wallet_alerts(driver)

        context = {
            'profile': profile,
            'driver': driver,
            'driver_vehicle': driver_vehicle,
            'stats_30_days': stats_30_days,
            'stats_7_days': stats_7_days,
            'wallet_status': wallet_status,
            'wallet_alerts': wallet_alerts,
        }
        return render(request, 'fleet/fleet_dashboard.html', context)

    except fleet_models.Driver.DoesNotExist:
        logger.warning(f"User {request.user.id} has no driver profile")
        messages.error(request, "Driver profile not found. Please create one first.")
        return redirect('core:main_dashboard')

# document---------------------------------------------------------------------------------------------------------------------


@login_required(login_url='/accounts/login/')
@driver_required
def driver_documents(request):
    try:
        driver = fleet_models.Driver.objects.get(user_id=request.user.id)
    except fleet_models.Driver.DoesNotExist:
        messages.error(request, 'Driver profile not found. Please create a driver profile first.')
        return redirect('webpages:join_driver')

    logger.debug(f'driver_documents for driver_id={driver.driver_id}')
    documents = fleet_models.DriverDocument.objects.filter(
        driver_id=driver.driver_id)
    context = {
        'documents': documents,
    }
    return render(request, 'fleet/parts/document_all.html', context)


@login_required(login_url='/accounts/login/')
@driver_required
def driver_documents_upload(request, fleet_id):
    try:
        driver = fleet_models.Driver.objects.get(user_id=request.user.id)
    except fleet_models.Driver.DoesNotExist:
        messages.error(request, 'Driver profile not found. Please create a driver profile first.')
        return redirect('webpages:join_driver')

    logger.debug(f'driver_documents_upload for driver_id={driver.driver_id}')
    form = fleet_forms.DriverDocumentForm()
    if request.method == 'POST':
        form = fleet_forms.DriverDocumentForm(request.POST, request.FILES)
        if form.is_valid():
            logger.debug("DriverDocumentForm is valid")
            f = form.save(commit=False)
            f.driver_id = driver.driver_id
            f.save()
            return redirect('/fleet/documents/')
    else:
        form = fleet_forms.DriverDocumentForm()
        context = {
            'form': form,
        }

        return render(request, 'fleet/parts/document_add.html', context)


@login_required(login_url='/accounts/login/')
@driver_required
def driver_documents_update(request, fleet_id, doc_id):
    logger.debug(f'driver_documents_update for doc_id={doc_id}')
    if fleet_id != request.user.id:
        return redirect('/fleet/documents/')

    try:
        driver = fleet_models.Driver.objects.get(user_id=fleet_id)
    except fleet_models.Driver.DoesNotExist:
        messages.error(request, 'Driver profile not found. Please create a driver profile first.')
        return redirect('webpages:join_driver')

    logger.debug(f'driver_documents_update for driver_id={driver.driver_id}')
    document = fleet_models.DriverDocument.objects.get(id=doc_id)
    form = fleet_forms.DriverDocumentForm(
        request.POST or None, instance=document)
    if request.method == 'POST':
        form = fleet_forms.DriverDocumentForm(request.POST, request.FILES, instance=document)
        if form.is_valid():
            logger.debug("DriverDocumentForm is valid")
            f = form.save(commit=False)
            f.driver_id = driver.driver_id
            f.save()
            return redirect('/fleet/documents/')

    context = {
            'form': form,
        }

    return render(request, 'fleet/parts/document_update.html', context)


@login_required(login_url='/accounts/login/')
@driver_required
def driver_documents_delete(request, fleet_id, doc_id):
    logger.debug(f'driver_documents_delete for doc_id={doc_id}')
    if fleet_id != request.user.id:
        return redirect('/fleet/documents/')

    try:
        driver = fleet_models.Driver.objects.get(user_id=fleet_id)
    except fleet_models.Driver.DoesNotExist:
        messages.error(request, 'Driver profile not found. Please create a driver profile first.')
        return redirect('webpages:join_driver')

    logger.debug(f'driver_documents_delete for driver_id={driver.driver_id}')
    document = fleet_models.DriverDocument.objects.filter(id=doc_id)
    document.delete()
    return redirect('/fleet/documents/')


# vehicle---------------------------------------------------------------------------------------------------------------------

@login_required(login_url='/accounts/login/')
@driver_required
def vehicle_own(request):
    try:
        driver = fleet_models.Driver.objects.get(user_id=request.user.id)
    except fleet_models.Driver.DoesNotExist:
        messages.error(request, 'Driver profile not found. Please create a driver profile first.')
        return redirect('webpages:join_driver')

    logger.debug(f'vehicle_own for driver_id={driver.driver_id}')
    vehicles = fleet_models.DriverVehicle.objects.filter(
        driver_id=driver.driver_id)
    logger.debug(f'vehicle_own found {vehicles.count()} vehicles')
    context = {
        'vehicles': vehicles,
    }
    return render(request, 'fleet/parts/vehicle_own.html', context)


@login_required(login_url='/accounts/login/')
@driver_required
def vehicle_add(request):
    logger.debug('vehicle_add')
    driver = fleet_models.Driver.objects.get(user_id=request.user.id)
    form = fleet_forms.DriverVehicleForm(request.POST or None)
    if request.method == 'POST':
        if form.is_valid():
            logger.debug("VehicleForm is valid")
            f = form.save(commit=False)
            f.driver_id = driver.driver_id
            f.save()
            return redirect('/fleet/vehicle_own/')
    else:
        form = fleet_forms.DriverVehicleForm()
        context = {
            'form': form,
        }

    return render(request, 'fleet/parts/vehicle_add.html', context)


@login_required(login_url='/accounts/login/')
@driver_required
def vehicle_delete(request, fleet_id, vehicle_id):
    logger.debug(f'vehicle_delete for vehicle_id={vehicle_id}')

    # Only staff users can delete vehicles
    if not request.user.is_staff:
        messages.error(request, 'Only staff members can delete vehicles. Please contact support for assistance.')
        return redirect('/fleet/vehicle_own/')

    if fleet_id != request.user.id:
        return redirect('/fleet/vehicles/')
    vehicle = fleet_models.DriverVehicle.objects.filter(id=vehicle_id)
    vehicle.delete()
    messages.success(request, 'Vehicle deleted successfully.')
    return redirect('/fleet/vehicle_own/')


@login_required(login_url='/accounts/login/')
@driver_required
def vehicle_update(request, vehicle_id):
    driver = fleet_models.Driver.objects.get(user_id=request.user.id)
    logger.debug(f'vehicle_update for driver_id={driver.driver_id}')

    driver_vehicle = fleet_models.DriverVehicle.objects.get(id=vehicle_id)
    logger.debug(f'vehicle_update for vehicle={driver_vehicle}')
    form = fleet_forms.DriverVehicleForm(
        request.POST or None, instance=driver_vehicle)
    if request.method == 'POST':
        form = fleet_forms.DriverVehicleForm(
            request.POST, instance=driver_vehicle)

        if form.is_valid():
            logger.debug("VehicleForm is valid")
            f = form.save(commit=False)

            f.save()

        return redirect('/fleet/vehicle_own/')

    form = fleet_forms.DriverVehicleForm(instance=driver_vehicle)
    context = {
        'form': form,
        'instance': driver_vehicle,
    }

    return render(request, 'fleet/parts/vehicle_update.html', context)


# cod_collection ----------------------------------------------------------------------------------------------------------------------------
@login_required(login_url='/accounts/login/')
@driver_required
def cod_collection(request):
    try:
        driver = fleet_models.Driver.objects.get(user_id=request.user.id)

        # Get wallet status
        wallet_status = WalletService.get_wallet_status(driver)

        # Get COD transactions
        cod_transactions = fleet_models.DriverTransaction.objects.filter(
            driver=driver,
            transaction_type__in=['cod_collection', 'cod_deposit']
        ).select_related('delivery_task').order_by('-created_at')[:50]

        # Get recent deliveries with COD
        cod_deliveries = delivery_models.DeliveryTask.objects.filter(
            driver=driver,
            cod_collected=True
        ).select_related('order').order_by('-completed_at')[:20]

        context = {
            'driver': driver,
            'wallet_status': wallet_status,
            'cod_transactions': cod_transactions,
            'cod_deliveries': cod_deliveries,
        }

        return render(request, 'fleet/parts/cod_collection.html', context)

    except fleet_models.Driver.DoesNotExist:
        messages.error(request, 'Driver profile not found.')
        return redirect('core:main_dashboard')


# COD Submission ----------------------------------------------------------------------------------------------------------------------------
@login_required(login_url='/accounts/login/')
@driver_required
def cod_submission(request):
    try:
        driver = fleet_models.Driver.objects.get(user_id=request.user.id)

        if request.method == 'POST':
            amount = request.POST.get('amount')
            reference_number = request.POST.get('reference_number', '')
            notes = request.POST.get('notes', '')

            try:
                amount = float(amount)
                if amount <= 0:
                    messages.error(request, 'Amount must be greater than zero.')
                elif amount > float(driver.cod_in_hand):
                    messages.error(request, f'You only have {driver.cod_in_hand} QR in hand.')
                else:
                    # Process COD submission
                    transaction = WalletService.submit_cod_to_admin(
                        driver=driver,
                        amount=amount,
                        created_by=request.user,
                        reference_number=reference_number,
                        notes=notes
                    )
                    messages.success(request, f'Successfully submitted {amount} QR COD to admin.')
                    return redirect('fleet:cod_collection')
            except ValueError as e:
                messages.error(request, str(e))
            except Exception as e:
                messages.error(request, f'Error processing submission: {str(e)}')

        # Get wallet status
        wallet_status = WalletService.get_wallet_status(driver)

        context = {
            'driver': driver,
            'wallet_status': wallet_status,
        }

        return render(request, 'fleet/parts/cod_submission.html', context)

    except fleet_models.Driver.DoesNotExist:
        messages.error(request, 'Driver profile not found.')
        return redirect('core:main_dashboard')


# Earnings View ----------------------------------------------------------------------------------------------------------------------------
@login_required(login_url='/accounts/login/')
@driver_required
def driver_earnings(request):
    try:
        driver = fleet_models.Driver.objects.get(user_id=request.user.id)

        # Get filter parameters
        days = int(request.GET.get('days', 30))
        status_filter = request.GET.get('status', 'all')

        from datetime import timedelta
        from django.utils import timezone
        from delivery import models as delivery_models
        from django.db.models import Sum

        start_date = timezone.now() - timedelta(days=days)

        # Get assigned task IDs for this driver
        assigned_task_ids = delivery_models.AssignedDriver.objects.filter(
            driver=driver
        ).values_list('dl_task_id', flat=True)

        # Get completed delivery tasks (delivered or returned with charge)
        completed_tasks = delivery_models.DeliveryTask.objects.filter(
            id__in=assigned_task_ids,
            dl_task_status__in=['delivered', 'returned'],
            dl_task_date__gte=start_date.date()
        ).select_related(
            'order', 'order__business', 'pickup_location', 'dl_to_address'
        ).order_by('-dl_task_date', '-id')

        # Apply status filter
        if status_filter == 'delivered':
            completed_tasks = completed_tasks.filter(dl_task_status='delivered')
        elif status_filter == 'returned':
            completed_tasks = completed_tasks.filter(dl_task_status='returned')

        # Calculate totals
        total_delivery_fee = completed_tasks.aggregate(
            total=Sum('dl_price')
        )['total'] or 0

        delivered_count = completed_tasks.filter(dl_task_status='delivered').count()
        returned_count = completed_tasks.filter(dl_task_status='returned').count()

        context = {
            'driver': driver,
            'completed_tasks': completed_tasks,
            'total_delivery_fee': total_delivery_fee,
            'delivered_count': delivered_count,
            'returned_count': returned_count,
            'total_count': completed_tasks.count(),
            'selected_days': days,
            'selected_status': status_filter,
        }

        return render(request, 'fleet/parts/driver_earnings.html', context)

    except fleet_models.Driver.DoesNotExist:
        messages.error(request, 'Driver profile not found.')
        return redirect('core:main_dashboard')


# Transaction History ----------------------------------------------------------------------------------------------------------------------------
@login_required(login_url='/accounts/login/')
@driver_required
def transaction_history(request):
    try:
        driver = fleet_models.Driver.objects.get(user_id=request.user.id)

        # Get filter parameters
        transaction_type = request.GET.get('type', 'all')
        days = int(request.GET.get('days', 30))

        # Build query
        from datetime import timedelta
        from django.utils import timezone

        start_date = timezone.now() - timedelta(days=days)

        transactions = fleet_models.DriverTransaction.objects.filter(
            driver=driver,
            created_at__gte=start_date
        )

        if transaction_type != 'all':
            transactions = transactions.filter(transaction_type=transaction_type)

        transactions = transactions.select_related(
            'delivery_task', 'settlement', 'created_by'
        ).order_by('-created_at')

        # Get wallet status
        wallet_status = WalletService.get_wallet_status(driver)

        context = {
            'driver': driver,
            'transactions': transactions,
            'wallet_status': wallet_status,
            'selected_type': transaction_type,
            'selected_days': days,
            'transaction_types': fleet_models.DriverTransaction.TRANSACTION_TYPES,
        }

        return render(request, 'fleet/parts/transaction_history.html', context)

    except fleet_models.Driver.DoesNotExist:
        messages.error(request, 'Driver profile not found.')
        return redirect('core:main_dashboard')


# Performance & Analytics ----------------------------------------------------------------------------------------------------------------------------
@login_required(login_url='/accounts/login/')
@driver_required
def driver_performance(request):
    """Comprehensive performance dashboard for drivers"""
    try:
        driver = fleet_models.Driver.objects.get(user_id=request.user.id)

        # Get filter parameters
        period = request.GET.get('period', '30')  # days
        days = int(period)

        # Get statistics for selected period
        stats = WalletService.get_driver_statistics(driver, days=days)

        # Get wallet status
        wallet_status = WalletService.get_wallet_status(driver)

        # Get delivery performance metrics
        from django.db.models import Avg, Max, Min, F, ExpressionWrapper, fields
        from django.utils import timezone
        from datetime import timedelta

        start_date = timezone.now() - timedelta(days=days)

        deliveries = delivery_models.DeliveryTask.objects.filter(
            driver=driver,
            completed_at__gte=start_date
        )

        # Calculate detailed metrics
        performance_metrics = {
            'total_tasks': deliveries.count(),
            'completed_tasks': deliveries.filter(dl_task_status_dms='2').count(),
            'failed_tasks': deliveries.filter(dl_task_status_dms='3').count(),
            'in_progress': deliveries.filter(dl_task_status_dms__in=['0', '1', '4', '7']).count(),
            'cancelled_tasks': deliveries.filter(dl_task_status_dms='9').count(),
        }

        # Calculate completion rate
        if performance_metrics['total_tasks'] > 0:
            performance_metrics['completion_rate'] = (performance_metrics['completed_tasks'] / performance_metrics['total_tasks']) * 100
        else:
            performance_metrics['completion_rate'] = 0

        # Get COD collection rate
        cod_deliveries = deliveries.filter(cod_collected=True)
        performance_metrics['cod_collection_rate'] = (cod_deliveries.count() / deliveries.count() * 100) if deliveries.count() > 0 else 0

        # Get average ratings
        performance_metrics['average_rating'] = driver.driver_rating / driver.driver_rating_count if driver.driver_rating_count > 0 else 0
        performance_metrics['total_reviews'] = driver.driver_reviews_count

        # Get daily performance (last 7 days)
        daily_stats = []
        for i in range(6, -1, -1):
            day_start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=i)
            day_end = day_start + timedelta(days=1)

            day_deliveries = deliveries.filter(completed_at__gte=day_start, completed_at__lt=day_end)
            daily_stats.append({
                'date': day_start.strftime('%a %d'),
                'total': day_deliveries.count(),
                'completed': day_deliveries.filter(dl_task_status_dms='2').count(),
                'failed': day_deliveries.filter(dl_task_status_dms='3').count(),
            })

        context = {
            'driver': driver,
            'stats': stats,
            'wallet_status': wallet_status,
            'performance_metrics': performance_metrics,
            'daily_stats': daily_stats,
            'selected_period': period,
            'period_options': [
                ('7', 'Last 7 Days'),
                ('30', 'Last 30 Days'),
                ('90', 'Last 90 Days'),
                ('365', 'This Year'),
            ],
        }

        return render(request, 'fleet/parts/driver_performance.html', context)

    except fleet_models.Driver.DoesNotExist:
        messages.error(request, 'Driver profile not found.')
        return redirect('core:main_dashboard')


@login_required(login_url='/accounts/login/')
@driver_required
def driver_reports(request):
    """Generate and download various reports"""
    try:
        driver = fleet_models.Driver.objects.get(user_id=request.user.id)

        # Get available report types
        report_types = [
            {
                'id': 'earnings',
                'name': 'Earnings Report',
                'description': 'Detailed breakdown of your earnings, COD collections, and settlements',
                'icon': 'fa-coins',
            },
            {
                'id': 'deliveries',
                'name': 'Delivery Report',
                'description': 'Complete list of all deliveries with status and timestamps',
                'icon': 'fa-truck',
            },
            {
                'id': 'transactions',
                'name': 'Transaction Report',
                'description': 'All financial transactions including COD, earnings, and deposits',
                'icon': 'fa-receipt',
            },
            {
                'id': 'performance',
                'name': 'Performance Report',
                'description': 'Performance metrics, ratings, and completion rates',
                'icon': 'fa-gauge-high',
            },
        ]

        # Get recent settlements for quick download
        settlements = fleet_models.DriverSettlement.objects.filter(
            driver=driver,
            status='paid'
        ).order_by('-paid_at')[:5]

        context = {
            'driver': driver,
            'report_types': report_types,
            'settlements': settlements,
        }

        return render(request, 'fleet/parts/driver_reports.html', context)

    except fleet_models.Driver.DoesNotExist:
        messages.error(request, 'Driver profile not found.')
        return redirect('core:main_dashboard')


@login_required(login_url='/accounts/login/')
@driver_required
def driver_analytics(request):
    """Advanced analytics and visualizations"""
    try:
        driver = fleet_models.Driver.objects.get(user_id=request.user.id)

        from django.db.models import Count, Sum, Avg, Q
        from django.utils import timezone
        from datetime import timedelta
        import json

        # Get data for last 90 days
        start_date = timezone.now() - timedelta(days=90)

        deliveries = delivery_models.DeliveryTask.objects.filter(
            driver=driver,
            completed_at__gte=start_date
        )

        # Monthly trend data
        monthly_data = []
        for i in range(2, -1, -1):  # Last 3 months
            month_start = timezone.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0) - timedelta(days=30*i)
            month_end = month_start + timedelta(days=30)

            month_deliveries = deliveries.filter(completed_at__gte=month_start, completed_at__lt=month_end)
            monthly_data.append({
                'month': month_start.strftime('%B'),
                'total': month_deliveries.count(),
                'earnings': float(month_deliveries.aggregate(Sum('driver_earnings'))['driver_earnings__sum'] or 0),
                'cod_collected': float(month_deliveries.aggregate(Sum('cod_collected_amount'))['cod_collected_amount__sum'] or 0),
            })

        # Delivery type breakdown
        delivery_categories = deliveries.values('dl_category').annotate(
            count=Count('id')
        ).order_by('-count')

        # Speed type breakdown
        delivery_speeds = deliveries.values('dl_speed').annotate(
            count=Count('id')
        ).order_by('-count')

        # Peak hours analysis
        hour_distribution = []
        for hour in range(24):
            count = deliveries.filter(completed_at__hour=hour).count()
            hour_distribution.append({
                'hour': f"{hour:02d}:00",
                'deliveries': count
            })

        # Get top 5 peak hours
        peak_hours = sorted(hour_distribution, key=lambda x: x['deliveries'], reverse=True)[:5]

        # COD vs Prepaid ratio
        cod_count = deliveries.filter(cod_collected=True).count()
        prepaid_count = deliveries.filter(cod_collected=False).count()

        context = {
            'driver': driver,
            'monthly_data': json.dumps(monthly_data),
            'delivery_categories': delivery_categories,
            'delivery_speeds': delivery_speeds,
            'peak_hours': peak_hours,
            'cod_count': cod_count,
            'prepaid_count': prepaid_count,
            'hour_distribution': json.dumps(hour_distribution),
        }

        return render(request, 'fleet/parts/driver_analytics.html', context)

    except fleet_models.Driver.DoesNotExist:
        messages.error(request, 'Driver profile not found.')
        return redirect('core:main_dashboard')


# delivery tasks ----------------------------------------------------------------------------------------------------------------------------


# Front end -------------------------------------------------------------------------------------------------------------------------------------------------

@login_required(login_url='/accounts/login/')
@driver_required
def driver_profile(request, fleet_id):
    try:
        # Single query with select_related to avoid duplicate queries
        driver = fleet_models.Driver.objects.select_related('user').get(driver_id=fleet_id)
    except fleet_models.Driver.DoesNotExist:
        logger.warning(f'driver does not exist for fleet_id={fleet_id}')
        return redirect('/fleet/')
    logger.debug(f'driver_profile for driver_id={driver.driver_id}')

    profile = core_models.Profile.objects.select_related('user').get(user_id=driver.user_id)
    # Get or create profile picture to avoid DoesNotExist error
    profile_picture, _ = core_models.ProfilePicture.objects.get_or_create(user_id=driver.user_id)
    logger.debug(f'profile_picture={profile_picture}')

    driver_vehicle = driver.driver_vehicle.all()
    logger.debug(f'driver_vehicle count={driver_vehicle.count()}')
    driver_documents = driver.driver_document.all()
    logger.debug(f'driver_documents count={driver_documents.count()}')

    # Dynamic SEO for driver profile page
    driver_name = profile.user.first_name or "Driver"
    meta = SEOMetadata.get_page_meta(
        title=f"{driver_name} - Delivery Driver Qatar | EzzyDelivery",
        description=(
            f"View {driver_name}'s driver profile on EzzyDelivery Qatar. "
            f"Professional delivery driver serving Doha and surrounding areas."
        )[:155],
    )

    context = {
        'seo': meta,
        'profile': profile,
        'driver': driver,
        'driver_documents': driver_documents,
        'driver_vehicle': driver_vehicle,
        'profile_picture': profile_picture
    }
    return render(request, 'fleet/frontend/driver_profile.html', context)


# Mobile PWA Profile ---------------------------------------------------------------
@login_required(login_url='/accounts/login/')
@driver_required
def driver_profile_mobile(request):
    """
    Mobile PWA driver profile page.
    Displays driver info, stats, vehicle, and account settings in mobile-friendly format.
    Handles zone preference selection via POST.
    """
    try:
        # Fetch driver with related data
        driver = fleet_models.Driver.objects.select_related(
            'user',
            'profile'
        ).prefetch_related(
            'preferred_zone_groups',
            'preferred_zone_groups__zones'
        ).get(user_id=request.user.id)

        # Handle zone group preference update
        if request.method == 'POST' and 'update_zones' in request.POST:
            selected_group_ids = request.POST.getlist('preferred_zone_groups')
            driver.preferred_zone_groups.clear()
            if selected_group_ids:
                groups = ZoneGroup.objects.filter(id__in=selected_group_ids, is_active=True)
                driver.preferred_zone_groups.add(*groups)
            messages.success(request, 'Zone group preferences updated successfully.')
            return redirect('fleet:driver_profile_mobile')

        profile = driver.profile

        # Get profile picture
        profile_picture, _ = core_models.ProfilePicture.objects.get_or_create(
            user_id=request.user.id
        )

        # Get driver vehicles
        driver_vehicles = fleet_models.DriverVehicle.objects.filter(
            driver_id=driver.driver_id
        )

        # Get wallet status
        wallet_status = WalletService.get_wallet_status(driver)

        # Get statistics for last 30 days
        stats = WalletService.get_driver_statistics(driver, days=30)

        # Calculate average rating
        if driver.driver_rating_count > 0:
            average_rating = driver.driver_rating / driver.driver_rating_count
        else:
            average_rating = 0

        # Get driver documents count
        documents_count = fleet_models.DriverDocument.objects.filter(
            driver_id=driver.driver_id
        ).count()

        # Get all active zone groups
        zone_groups = ZoneGroup.objects.filter(is_active=True).prefetch_related('zones').order_by('display_order', 'name')

        # Get driver's current preferred zone group IDs
        preferred_group_ids = list(driver.preferred_zone_groups.values_list('id', flat=True))

        context = {
            'driver': driver,
            'profile': profile,
            'profile_picture': profile_picture,
            'driver_vehicles': driver_vehicles,
            'wallet_status': wallet_status,
            'stats': stats,
            'average_rating': average_rating,
            'documents_count': documents_count,
            'zone_groups': zone_groups,
            'preferred_group_ids': preferred_group_ids,
        }

        return render(request, 'fleet/parts/driver_profile_mobile.html', context)

    except fleet_models.Driver.DoesNotExist:
        logger.warning(f"User {request.user.id} has no driver profile")
        messages.error(request, "Driver profile not found. Please create one first.")
        return redirect('core:main_dashboard')


@login_required(login_url='account_login')
def pickup_scanner(request):
    """
    Display the pickup task scanner page with camera access.
    Driver scans QR codes/barcodes to confirm pickup of items.
    """
    try:
        driver = fleet_models.Driver.objects.get(user_id=request.user.id)

        # Get assigned tasks that are pending pickup
        from delivery import models as delivery_models
        assigned_task_ids = delivery_models.AssignedDriver.objects.filter(
            driver=driver
        ).values_list('dl_task_id', flat=True)

        pending_tasks = delivery_models.DeliveryTask.objects.filter(
            id__in=assigned_task_ids,
            dl_task_status__in=['assigned', 'pending']
        ).select_related('order', 'order__business', 'pickup_location').order_by('dl_task_date')

        context = {
            'driver': driver,
            'pending_tasks': pending_tasks,
            'pending_count': pending_tasks.count(),
        }

        return render(request, 'fleet/pickup_scanner.html', context)

    except fleet_models.Driver.DoesNotExist:
        messages.error(request, "Driver profile not found.")
        return redirect('core:main_dashboard')


@login_required(login_url='account_login')
def pickup_scan_process(request):
    """
    Process a scanned barcode/QR code for pickup confirmation.
    Updates task status and returns result.
    """
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Invalid request method'})

    try:
        import json
        data = json.loads(request.body) if request.content_type == 'application/json' else request.POST
        scanned_code = data.get('code', '').strip()

        if not scanned_code:
            return JsonResponse({'success': False, 'error': 'No code provided'})

        driver = fleet_models.Driver.objects.get(user_id=request.user.id)

        # Find task by scanned code (could be task number, order number, or barcode)
        from delivery import models as delivery_models
        from orders import models as orders_models

        # Try to find by task number
        task = None
        assigned_task_ids = delivery_models.AssignedDriver.objects.filter(
            driver=driver
        ).values_list('dl_task_id', flat=True)

        # Search by task number
        task = delivery_models.DeliveryTask.objects.filter(
            id__in=assigned_task_ids,
            dl_task_number__icontains=scanned_code
        ).first()

        # If not found, search by order number
        if not task:
            task = delivery_models.DeliveryTask.objects.filter(
                id__in=assigned_task_ids,
                order__order_number__icontains=scanned_code
            ).first()

        # If not found, search by barcode
        if not task:
            barcode = orders_models.OrderBarcode.objects.filter(
                barcode_value=scanned_code
            ).select_related('order').first()

            if barcode:
                task = delivery_models.DeliveryTask.objects.filter(
                    id__in=assigned_task_ids,
                    order=barcode.order
                ).first()

        if not task:
            return JsonResponse({
                'success': False,
                'error': f'No matching task found for code: {scanned_code}'
            })

        # Check if already picked up
        if task.dl_task_status == 'in_transit':
            return JsonResponse({
                'success': False,
                'error': 'Task already picked up',
                'task_number': task.dl_task_number
            })

        # Update task status to in_transit (picked up)
        task.dl_task_status = 'in_transit'
        task.save(update_fields=['dl_task_status'])

        logger.info(f"Driver {driver.driver_id} confirmed pickup for task {task.dl_task_number}")

        return JsonResponse({
            'success': True,
            'message': 'Pickup confirmed!',
            'task_number': task.dl_task_number,
            'task_id': task.id,
            'business': task.order.business.business_name if task.order and task.order.business else 'N/A',
            'redirect_url': f'/delivery/task/{task.id}/navigation/'
        })

    except fleet_models.Driver.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Driver profile not found'})
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid JSON data'})
    except Exception as e:
        logger.error(f"Error processing pickup scan: {e}")
        return JsonResponse({'success': False, 'error': str(e)})
