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
from django.http import HttpResponse
from django.utils import timezone
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
        'driver_vehicle'  # Reverse FK: Driver ← DriverVehicle (related_name='driver_vehicle')
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
    try:
        document = fleet_models.DriverDocument.objects.get(id=doc_id, driver=driver)
    except fleet_models.DriverDocument.DoesNotExist:
        messages.error(request, 'Document not found.')
        return redirect('/fleet/documents/')
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
    document = fleet_models.DriverDocument.objects.filter(id=doc_id, driver=driver)
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
    try:
        driver = fleet_models.Driver.objects.get(user_id=request.user.id)
    except fleet_models.Driver.DoesNotExist:
        messages.error(request, 'Driver profile not found. Please create a driver profile first.')
        return redirect('webpages:join_driver')
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
    try:
        driver = fleet_models.Driver.objects.get(user_id=request.user.id)
    except fleet_models.Driver.DoesNotExist:
        messages.error(request, 'Driver profile not found. Please create a driver profile first.')
        return redirect('webpages:join_driver')
    logger.debug(f'vehicle_update for driver_id={driver.driver_id}')

    try:
        driver_vehicle = fleet_models.DriverVehicle.objects.get(id=vehicle_id, driver=driver)
    except fleet_models.DriverVehicle.DoesNotExist:
        messages.error(request, 'Vehicle not found.')
        return redirect('/fleet/vehicle_own/')
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

        # Get COD settlement transactions (only deposits/submissions to admin)
        cod_transactions = fleet_models.DriverTransaction.objects.filter(
            driver=driver,
            transaction_type='cod_deposit'
        ).select_related('delivery_task').order_by('-created_at')[:20]

        # Get COD currently in hand (not yet settled/deposited)
        # Only show COD that hasn't been submitted to admin yet
        cod_in_hand_list = delivery_models.DeliveryTask.objects.filter(
            driver=driver,
            cod_collected=True,
            cod_settled=False,  # Only unsettled COD
            dl_task_status='delivered'
        ).select_related(
            'order',
            'order__business',
            'dl_to_address'
        ).order_by('-completed_at')

        # Calculate total from actual list items so it matches the displayed list
        from django.db.models import Sum
        cod_in_hand_total = cod_in_hand_list.aggregate(
            total=Sum('cod_collected_amount')
        )['total'] or 0
        cod_in_hand_count = cod_in_hand_list.count()

        # Get recent COD deliveries (settled/completed - exclude items still in hand)
        cod_in_hand_ids = list(cod_in_hand_list.values_list('id', flat=True))
        cod_deliveries = delivery_models.DeliveryTask.objects.filter(
            driver=driver,
            cod_collected=True
        ).exclude(
            id__in=cod_in_hand_ids
        ).select_related('order', 'order__business', 'dl_to_address').order_by('-completed_at')[:20]

        context = {
            'driver': driver,
            'wallet_status': wallet_status,
            'cod_transactions': cod_transactions,
            'cod_deliveries': cod_deliveries,
            'cod_in_hand_list': cod_in_hand_list,
            'cod_in_hand_total': cod_in_hand_total,
            'cod_in_hand_count': cod_in_hand_count,
        }

        return render(request, 'fleet/parts/cod_collection.html', context)

    except fleet_models.Driver.DoesNotExist:
        messages.error(request, 'Driver profile not found.')
        return redirect('core:main_dashboard')


# COD Submission ----------------------------------------------------------------------------------------------------------------------------
@login_required(login_url='/accounts/login/')
@driver_required
def cod_submission(request):
    """Handle COD submission - redirects GET to cod_collection, processes POST"""
    try:
        driver = fleet_models.Driver.objects.get(user_id=request.user.id)

        # Redirect GET requests to cod_collection (consolidated page)
        if request.method == 'GET':
            return redirect('fleet:cod_collection')

        if request.method == 'POST':
            amount = request.POST.get('amount')
            reference_number = request.POST.get('reference_number', '')
            notes = request.POST.get('notes', '')
            payment_method = request.POST.get('payment_method', 'cash')
            delivery_ids_str = request.POST.get('delivery_ids', '')

            # Parse selected delivery IDs
            delivery_ids = [int(x) for x in delivery_ids_str.split(',') if x.strip().isdigit()] if delivery_ids_str else None

            try:
                from decimal import Decimal, InvalidOperation
                amount = Decimal(str(amount))
                if amount <= 0:
                    messages.error(request, 'Amount must be greater than zero.')
                elif amount > driver.cod_in_hand:
                    messages.error(request, f'You only have {driver.cod_in_hand} QR in hand.')
                else:
                    # Process COD submission
                    transaction = WalletService.submit_cod_to_admin(
                        driver=driver,
                        amount=amount,
                        created_by=request.user,
                        reference_number=reference_number,
                        notes=notes,
                        payment_method=payment_method,
                        delivery_ids=delivery_ids
                    )
                    messages.success(request, f'Successfully submitted {amount} QR COD to admin.')
                    return redirect('fleet:cod_collection')
            except (ValueError, InvalidOperation) as e:
                messages.error(request, str(e))
            except Exception as e:
                messages.error(request, f'Error processing submission: {str(e)}')

        # Get wallet status
        wallet_status = WalletService.get_wallet_status(driver)

        # Get pending COD deliveries (unsettled)
        cod_in_hand_list = delivery_models.DeliveryTask.objects.filter(
            driver=driver,
            cod_collected=True,
            cod_settled=False,
            dl_task_status='delivered'
        ).select_related(
            'order',
            'order__business',
            'dl_to_address'
        ).order_by('-completed_at')

        # Calculate total from actual list so it matches displayed items
        from django.db.models import Sum
        cod_in_hand_total = cod_in_hand_list.aggregate(
            total=Sum('cod_collected_amount')
        )['total'] or 0

        # Reference number is optional - driver can enter their own (e.g. bank transfer ref)
        # Transaction code (CODS-YYYYMMDD-NNNN) serves as the unique identifier
        auto_reference = ''

        # Recent COD submissions (cod_deposit / cod_driver_settle)
        recent_submissions = fleet_models.DriverTransaction.objects.filter(
            driver=driver,
            transaction_type__in=['cod_deposit', 'cod_driver_settle']
        ).order_by('-created_at')[:10]

        context = {
            'driver': driver,
            'wallet_status': wallet_status,
            'cod_in_hand_list': cod_in_hand_list,
            'cod_in_hand_total': cod_in_hand_total,
            'auto_reference': auto_reference,
            'recent_submissions': recent_submissions,
        }

        return render(request, 'fleet/parts/cod_submission.html', context)

    except fleet_models.Driver.DoesNotExist:
        messages.error(request, 'Driver profile not found.')
        return redirect('core:main_dashboard')


# COD Export --------------------------------------------------------------------------------------------------------------------------------
@login_required(login_url='/accounts/login/')
@driver_required
def cod_export(request):
    """Export COD in hand report as CSV or PDF, and optionally submit COD settlement"""
    import csv
    from io import BytesIO
    from decimal import Decimal

    try:
        driver = fleet_models.Driver.objects.get(user_id=request.user.id)
        export_format = request.GET.get('format', 'csv')
        ids = request.GET.get('ids', '')
        submit_settlement = request.GET.get('submit', '') == '1'

        # Parse delivery IDs
        if ids:
            delivery_ids = [int(id) for id in ids.split(',') if id.isdigit()]
        else:
            delivery_ids = []

        # Get deliveries with related transactions for transaction codes
        if delivery_ids:
            deliveries = delivery_models.DeliveryTask.objects.filter(
                driver=driver,
                id__in=delivery_ids,
                cod_collected=True,
                cod_settled=False,  # Only unsettled COD
                dl_task_status='delivered'
            ).select_related('order', 'order__business', 'dl_to_address').prefetch_related('transactions').order_by('-completed_at')
        else:
            deliveries = delivery_models.DeliveryTask.objects.filter(
                driver=driver,
                cod_collected=True,
                cod_settled=False,  # Only unsettled COD
                dl_task_status='delivered'
            ).select_related('order', 'order__business', 'dl_to_address').prefetch_related('transactions').order_by('-completed_at')

        # Calculate total COD amount for selected deliveries
        total_cod = sum(Decimal(str(d.cod_collected_amount or 0)) for d in deliveries)

        # Process COD settlement if submit=1
        if submit_settlement and total_cod > 0:
            try:
                # Submit COD to admin using wallet service
                from fleet.wallet_service import WalletService

                # Create COD deposit transaction
                txn = WalletService.submit_cod_to_admin(
                    driver=driver,
                    amount=total_cod,
                    created_by=request.user,
                    reference_number=f"COD-SUBMIT-{timezone.now().strftime('%Y%m%d%H%M%S')}",
                    notes=f"COD submission for {len(delivery_ids)} deliveries",
                    payment_method='cash'
                )

                # Mark deliveries as COD settled
                deliveries.update(cod_settled=True, cod_settled_at=timezone.now())

                messages.success(request, f'COD settlement of {total_cod} QR submitted successfully! Transaction: {txn.transaction_code}')
                logger.info(f"Driver {driver.driver_id} submitted COD: {total_cod} QR for {len(delivery_ids)} deliveries")

                # Redirect to show success message instead of returning PDF
                return redirect('fleet:cod_collection')

            except ValueError as e:
                messages.error(request, str(e))
                return redirect('fleet:cod_collection')
            except Exception as e:
                logger.error(f"COD settlement error for driver {driver.driver_id}: {str(e)}")
                messages.error(request, 'Error processing COD settlement. Please try again.')
                return redirect('fleet:cod_collection')

        if export_format == 'pdf':
            # Generate PDF
            from reportlab.lib import colors
            from reportlab.lib.pagesizes import A4
            from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
            from reportlab.lib.units import inch
            from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
            from reportlab.lib.enums import TA_CENTER

            buffer = BytesIO()
            doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=30)
            elements = []
            styles = getSampleStyleSheet()

            # Title
            title_style = ParagraphStyle('CustomTitle', parent=styles['Heading1'], fontSize=18, alignment=TA_CENTER, spaceAfter=20)
            elements.append(Paragraph('COD In Hand Report', title_style))

            # Driver info
            info_style = ParagraphStyle('Info', parent=styles['Normal'], fontSize=10, spaceAfter=10)
            elements.append(Paragraph(f'Driver: {driver.user.get_full_name() or driver.user.username}', info_style))
            elements.append(Paragraph(f'Generated: {timezone.now().strftime("%d %b %Y %H:%M")}', info_style))
            elements.append(Spacer(1, 20))

            # Table data
            table_data = [['#', 'TXN Code', 'Task Number', 'Business', 'Customer', 'Amount (QR)']]
            total = 0
            for idx, d in enumerate(deliveries, 1):
                amount = float(d.cod_collected_amount or 0)
                total += amount
                # Get transaction code if available
                txn = d.transactions.filter(transaction_type='cod_collection').first()
                txn_code = txn.transaction_code if txn and txn.transaction_code else '-'
                table_data.append([
                    str(idx),
                    txn_code[:15] if len(txn_code) > 15 else txn_code,
                    d.dl_task_number or '-',
                    (d.order.business.business_name if d.order and d.order.business else '-')[:20],
                    (d.order.customer_name if d.order else '-')[:15],
                    f'{amount:.0f}'
                ])

            # Add total row
            table_data.append(['', '', '', '', 'Total:', f'{total:.0f}'])

            # Create table
            table = Table(table_data, colWidths=[0.3*inch, 1.1*inch, 1*inch, 1.4*inch, 1.1*inch, 0.8*inch])
            table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#f59e0b')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('ALIGN', (-1, 0), (-1, -1), 'RIGHT'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 10),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#fffbeb')),
                ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
                ('GRID', (0, 0), (-1, -2), 0.5, colors.HexColor('#e5e7eb')),
                ('FONTSIZE', (0, 1), (-1, -1), 9),
                ('TOPPADDING', (0, 1), (-1, -1), 8),
                ('BOTTOMPADDING', (0, 1), (-1, -1), 8),
            ]))
            elements.append(table)

            doc.build(elements)
            buffer.seek(0)

            response = HttpResponse(buffer, content_type='application/pdf')
            response['Content-Disposition'] = f'attachment; filename="cod_report_{timezone.now().strftime("%Y%m%d_%H%M")}.pdf"'
            return response

        else:
            # Generate CSV
            response = HttpResponse(content_type='text/csv')
            response['Content-Disposition'] = f'attachment; filename="cod_report_{timezone.now().strftime("%Y%m%d_%H%M")}.csv"'

            writer = csv.writer(response)
            writer.writerow(['#', 'TXN Code', 'Task Number', 'Order Number', 'Business', 'Customer', 'Location', 'Delivered Date', 'Delivered Time', 'COD Amount (QR)'])

            total = 0
            for idx, d in enumerate(deliveries, 1):
                amount = float(d.cod_collected_amount or 0)
                total += amount
                # Get transaction code if available
                txn = d.transactions.filter(transaction_type='cod_collection').first()
                txn_code = txn.transaction_code if txn and txn.transaction_code else '-'
                writer.writerow([
                    idx,
                    txn_code,
                    d.dl_task_number or '-',
                    d.order.order_number if d.order else '-',
                    d.order.business.business_name if d.order and d.order.business else '-',
                    d.order.customer_name if d.order else '-',
                    d.dl_to_address.area_name if d.dl_to_address else '-',
                    d.completed_at.strftime('%d %b %Y') if d.completed_at else '-',
                    d.completed_at.strftime('%H:%M') if d.completed_at else '-',
                    f'{amount:.0f}'
                ])

            writer.writerow([])
            writer.writerow(['', '', '', '', '', '', '', '', 'Total:', f'{total:.0f}'])

            return response

    except fleet_models.Driver.DoesNotExist:
        messages.error(request, 'Driver profile not found.')
        return redirect('fleet:cod_collection')


# COD Transaction Detail (AJAX) ------------------------------------------------------------------------------------------------------------
@login_required(login_url='/accounts/login/')
@driver_required
def cod_transaction_detail(request):
    """Return JSON with the delivery tasks linked to a COD transaction"""
    from django.http import JsonResponse
    from datetime import timedelta

    txn_code = request.GET.get('code', '')
    if not txn_code:
        return JsonResponse({'error': 'Missing transaction code'}, status=400)

    try:
        driver = fleet_models.Driver.objects.get(user_id=request.user.id)
        txn = fleet_models.DriverTransaction.objects.get(
            transaction_code=txn_code,
            driver=driver
        )

        orders = []

        if txn.transaction_type == 'cod_collection' and txn.delivery_task:
            # Single COD collection - one delivery task linked
            d = txn.delivery_task
            orders.append({
                'task_number': d.dl_task_number or '-',
                'business': d.order.business.business_name if d.order and d.order.business else '-',
                'customer': d.order.customer_name if d.order else '-',
                'location': d.dl_to_address.area_name if d.dl_to_address else '-',
                'delivered_at': d.completed_at.strftime('%d %b %Y, %H:%M') if d.completed_at else '-',
                'amount': float(d.cod_collected_amount or 0),
            })
        elif txn.transaction_type in ['cod_deposit', 'cod_driver_settle']:
            # COD settlement - find tasks settled at the same time
            # Match delivery tasks whose cod_settled_at is within 5 seconds of the transaction
            window = timedelta(seconds=5)
            settled_tasks = delivery_models.DeliveryTask.objects.filter(
                driver=driver,
                cod_collected=True,
                cod_settled=True,
                cod_settled_at__gte=txn.created_at - window,
                cod_settled_at__lte=txn.created_at + window,
            ).select_related('order', 'order__business', 'dl_to_address').order_by('-completed_at')

            for d in settled_tasks:
                orders.append({
                    'task_number': d.dl_task_number or '-',
                    'business': d.order.business.business_name if d.order and d.order.business else '-',
                    'customer': d.order.customer_name if d.order else '-',
                    'location': d.dl_to_address.area_name if d.dl_to_address else '-',
                    'delivered_at': d.completed_at.strftime('%d %b %Y, %H:%M') if d.completed_at else '-',
                    'amount': float(d.cod_collected_amount or 0),
                })

        total = sum(o['amount'] for o in orders)

        return JsonResponse({
            'transaction_code': txn.transaction_code,
            'transaction_type': txn.get_transaction_type_display(),
            'amount': float(txn.amount),
            'date': txn.created_at.strftime('%d %b %Y, %H:%M'),
            'description': txn.description or '',
            'reference_number': txn.reference_number or '',
            'payment_method': txn.get_payment_method_display() if txn.payment_method else '-',
            'notes': txn.notes or '',
            'cod_in_hand_after': float(txn.cod_in_hand_after or 0),
            'wallet_balance_after': float(txn.wallet_balance_after or 0),
            'pending_earnings_after': float(txn.pending_earnings_after or 0),
            'orders': orders,
            'orders_total': total,
            'orders_count': len(orders),
        })

    except fleet_models.DriverTransaction.DoesNotExist:
        return JsonResponse({'error': 'Transaction not found'}, status=404)
    except fleet_models.Driver.DoesNotExist:
        return JsonResponse({'error': 'Driver not found'}, status=404)


# COD Transaction PDF ------------------------------------------------------------------------------------------------------------
@login_required(login_url='/accounts/login/')
@driver_required
def cod_transaction_pdf(request):
    """Generate PDF report for a specific COD transaction"""
    from io import BytesIO
    from datetime import timedelta
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.enums import TA_CENTER, TA_RIGHT

    txn_code = request.GET.get('code', '')
    if not txn_code:
        messages.error(request, 'Missing transaction code')
        return redirect('fleet:cod_collection')

    try:
        driver = fleet_models.Driver.objects.get(user_id=request.user.id)
        txn = fleet_models.DriverTransaction.objects.get(
            transaction_code=txn_code,
            driver=driver
        )

        # Get linked orders
        orders = []
        if txn.transaction_type == 'cod_collection' and txn.delivery_task:
            d = txn.delivery_task
            orders.append({
                'task_number': d.dl_task_number or '-',
                'business': d.order.business.business_name if d.order and d.order.business else '-',
                'customer': d.order.customer_name if d.order else '-',
                'location': d.dl_to_address.area_name if d.dl_to_address else '-',
                'delivered_at': d.completed_at.strftime('%d %b %Y, %H:%M') if d.completed_at else '-',
                'amount': float(d.cod_collected_amount or 0),
            })
        elif txn.transaction_type in ['cod_deposit', 'cod_driver_settle']:
            window = timedelta(seconds=5)
            settled_tasks = delivery_models.DeliveryTask.objects.filter(
                driver=driver,
                cod_collected=True,
                cod_settled=True,
                cod_settled_at__gte=txn.created_at - window,
                cod_settled_at__lte=txn.created_at + window,
            ).select_related('order', 'order__business', 'dl_to_address').order_by('-completed_at')

            for d in settled_tasks:
                orders.append({
                    'task_number': d.dl_task_number or '-',
                    'business': d.order.business.business_name if d.order and d.order.business else '-',
                    'customer': d.order.customer_name if d.order else '-',
                    'location': d.dl_to_address.area_name if d.dl_to_address else '-',
                    'delivered_at': d.completed_at.strftime('%d %b %Y, %H:%M') if d.completed_at else '-',
                    'amount': float(d.cod_collected_amount or 0),
                })

        orders_total = sum(o['amount'] for o in orders)

        # Generate PDF
        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=30)
        elements = []
        styles = getSampleStyleSheet()

        # Title
        title_style = ParagraphStyle('CustomTitle', parent=styles['Heading1'], fontSize=18, alignment=TA_CENTER, spaceAfter=10)
        elements.append(Paragraph('Transaction Report', title_style))

        # Transaction code
        code_style = ParagraphStyle('Code', parent=styles['Normal'], fontSize=10, alignment=TA_CENTER, textColor=colors.HexColor('#6b7280'))
        elements.append(Paragraph(f'{txn.transaction_code}', code_style))
        elements.append(Spacer(1, 20))

        # Transaction summary
        info_style = ParagraphStyle('Info', parent=styles['Normal'], fontSize=10, spaceAfter=6)
        amount_color = '#059669' if txn.amount >= 0 else '#dc2626'
        amount_sign = '+' if txn.amount >= 0 else ''

        summary_data = [
            ['Type:', txn.get_transaction_type_display()],
            ['Amount:', f'{amount_sign}{abs(float(txn.amount)):.0f} QR'],
            ['Date:', txn.created_at.strftime('%d %b %Y, %H:%M')],
            ['Description:', txn.description or '-'],
            ['Payment Method:', txn.get_payment_method_display() if txn.payment_method else '-'],
        ]
        if txn.reference_number:
            summary_data.append(['Reference:', txn.reference_number])
        if txn.notes:
            summary_data.append(['Notes:', txn.notes[:50]])

        summary_table = Table(summary_data, colWidths=[1.5*inch, 4.5*inch])
        summary_table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('TEXTCOLOR', (0, 0), (0, -1), colors.HexColor('#6b7280')),
            ('ALIGN', (0, 0), (0, -1), 'LEFT'),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ]))
        elements.append(summary_table)
        elements.append(Spacer(1, 15))

        # Balance after transaction
        balance_style = ParagraphStyle('Balance', parent=styles['Heading2'], fontSize=12, spaceAfter=8)
        elements.append(Paragraph('Balance After Transaction', balance_style))

        balance_data = [
            ['COD in Hand:', f'{float(txn.cod_in_hand_after or 0):.0f} QR'],
            ['Wallet Balance:', f'{float(txn.wallet_balance_after or 0):.0f} QR'],
            ['Pending Earnings:', f'{float(txn.pending_earnings_after or 0):.0f} QR'],
        ]
        balance_table = Table(balance_data, colWidths=[1.5*inch, 2*inch])
        balance_table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('TEXTCOLOR', (0, 0), (0, -1), colors.HexColor('#6b7280')),
            ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
            ('FONTNAME', (1, 0), (1, -1), 'Helvetica-Bold'),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f9fafb')),
        ]))
        elements.append(balance_table)
        elements.append(Spacer(1, 20))

        # Orders table (if any)
        if orders:
            orders_title = ParagraphStyle('OrdersTitle', parent=styles['Heading2'], fontSize=12, spaceAfter=10)
            elements.append(Paragraph(f'COD Orders ({len(orders)})', orders_title))

            orders_data = [['#', 'Task', 'Business', 'Customer', 'Delivered', 'Amount']]
            for idx, o in enumerate(orders, 1):
                orders_data.append([
                    str(idx),
                    o['task_number'][:12] if len(o['task_number']) > 12 else o['task_number'],
                    o['business'][:18] if len(o['business']) > 18 else o['business'],
                    o['customer'][:15] if len(o['customer']) > 15 else o['customer'],
                    o['delivered_at'],
                    f"{o['amount']:.0f} QR"
                ])
            orders_data.append(['', '', '', '', 'Total:', f'{orders_total:.0f} QR'])

            orders_table = Table(orders_data, colWidths=[0.3*inch, 0.9*inch, 1.3*inch, 1.1*inch, 1.2*inch, 0.8*inch])
            orders_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#8b5cf6')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('ALIGN', (-1, 0), (-1, -1), 'RIGHT'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 9),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
                ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#ede9fe')),
                ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
                ('GRID', (0, 0), (-1, -2), 0.5, colors.HexColor('#e5e7eb')),
                ('FONTSIZE', (0, 1), (-1, -1), 8),
                ('TOPPADDING', (0, 1), (-1, -1), 6),
                ('BOTTOMPADDING', (0, 1), (-1, -1), 6),
            ]))
            elements.append(orders_table)

        # Footer
        elements.append(Spacer(1, 30))
        footer_style = ParagraphStyle('Footer', parent=styles['Normal'], fontSize=8, alignment=TA_CENTER, textColor=colors.HexColor('#9ca3af'))
        elements.append(Paragraph(f'Generated on {timezone.now().strftime("%d %b %Y, %H:%M")} | Driver: {driver.user.get_full_name() or driver.user.username}', footer_style))

        doc.build(elements)
        buffer.seek(0)

        response = HttpResponse(buffer, content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="txn_{txn.transaction_code}.pdf"'
        return response

    except fleet_models.DriverTransaction.DoesNotExist:
        messages.error(request, 'Transaction not found')
        return redirect('fleet:cod_collection')
    except fleet_models.Driver.DoesNotExist:
        messages.error(request, 'Driver profile not found')
        return redirect('fleet:cod_collection')


# Earnings View ----------------------------------------------------------------------------------------------------------------------------
@login_required(login_url='/accounts/login/')
@driver_required
def driver_earnings(request):
    try:
        driver = fleet_models.Driver.objects.get(user_id=request.user.id)

        from datetime import timedelta
        from decimal import Decimal, InvalidOperation
        from django.utils import timezone
        from django.core.paginator import Paginator
        from delivery import models as delivery_models
        from django.db.models import Sum, Case, When, DecimalField, Value

        # Handle settlement submission
        if request.method == 'POST':
            amount = request.POST.get('amount', '0')
            notes = request.POST.get('notes', '')
            delivery_ids_str = request.POST.get('delivery_ids', '')

            delivery_ids = [int(x) for x in delivery_ids_str.split(',')
                          if x.strip().isdigit()] if delivery_ids_str else []

            try:
                amount = Decimal(str(amount))
                if amount <= 0:
                    messages.error(request, 'Amount must be greater than zero.')
                elif amount > driver.pending_earnings:
                    messages.error(request, f'You only have {driver.pending_earnings} QR in pending earnings.')
                else:
                    from django.db import transaction
                    with transaction.atomic():
                        # Create settlement transaction
                        txn = WalletService.record_transaction(
                            driver=driver,
                            transaction_type='settlement',
                            amount=amount,
                            description=f"Earnings settlement - {amount} QR for {len(delivery_ids)} deliveries",
                            created_by=request.user,
                            notes=notes,
                        )

                        # Mark selected deliveries as earnings settled
                        if delivery_ids:
                            delivery_models.DeliveryTask.objects.filter(
                                id__in=delivery_ids,
                                driver=driver,
                                earnings_settled=False
                            ).update(
                                earnings_settled=True,
                                earnings_settled_at=timezone.now()
                            )

                    messages.success(request, f'Settlement of {amount} QR submitted successfully. Transaction: {txn.transaction_code}')
                    return redirect('fleet:driver_earnings')
            except (ValueError, InvalidOperation) as e:
                messages.error(request, str(e))
            except Exception as e:
                messages.error(request, f'Error processing settlement: {str(e)}')

        # Get filter parameters
        try:
            days = int(request.GET.get('days', 30))
        except (ValueError, TypeError):
            days = 30
        status_filter = request.GET.get('status', 'all')
        settlement_filter = request.GET.get('settlement', 'all')

        start_date = timezone.now() - timedelta(days=days)

        # Get completed delivery tasks using direct driver FK (consistent with dashboard)
        completed_tasks = delivery_models.DeliveryTask.objects.filter(
            driver=driver,
            dl_task_status__in=['delivered', 'failed'],
            dl_task_date__gte=start_date.date()
        ).select_related(
            'order', 'order__business', 'pickup_location', 'dl_to_address'
        ).order_by('-dl_task_date', '-id')

        # Apply status filter
        if status_filter == 'delivered':
            completed_tasks = completed_tasks.filter(dl_task_status='delivered')
        elif status_filter == 'returned':
            completed_tasks = completed_tasks.filter(dl_task_status='failed')

        # Apply settlement status filter
        if settlement_filter == 'pending':
            completed_tasks = completed_tasks.filter(earnings_settled=False)
        elif settlement_filter == 'settled':
            completed_tasks = completed_tasks.filter(earnings_settled=True)

        # Calculate totals using driver_earnings field (actual driver earnings)
        # Fall back to dl_price for tasks where driver_earnings hasn't been calculated
        totals = completed_tasks.aggregate(
            total_earnings=Sum(
                Case(
                    When(driver_earnings__isnull=False, then='driver_earnings'),
                    default='dl_price',
                    output_field=DecimalField(max_digits=10, decimal_places=2)
                )
            )
        )
        total_delivery_fee = totals['total_earnings'] or 0

        delivered_count = completed_tasks.filter(dl_task_status='delivered').count()
        returned_count = completed_tasks.filter(dl_task_status='failed').count()
        total_count = completed_tasks.count()

        # Get unsettled deliveries for settlement selection
        # Only show published earnings (verified by staff)
        unsettled_tasks = delivery_models.DeliveryTask.objects.filter(
            driver=driver,
            dl_task_status='delivered',
            earnings_settled=False,
            earnings_verification_status='published'  # Only published earnings can be settled
        ).select_related(
            'order', 'order__business', 'dl_to_address'
        ).order_by('-completed_at')

        unsettled_total = unsettled_tasks.aggregate(
            total=Sum(
                Case(
                    When(driver_earnings__isnull=False, then='driver_earnings'),
                    default='dl_price',
                    output_field=DecimalField(max_digits=10, decimal_places=2)
                )
            )
        )['total'] or 0

        # Paginate completed tasks - 10 per page
        paginator = Paginator(completed_tasks, 10)
        page_number = request.GET.get('page', 1)
        page_obj = paginator.get_page(page_number)

        # Build filter params string for pagination component
        filter_params = f'days={days}&status={status_filter}&settlement={settlement_filter}'

        # Recent earning & settlement transactions
        recent_settlements = fleet_models.DriverTransaction.objects.filter(
            driver=driver,
            transaction_type__in=['earning', 'settlement', 'bonus', 'deduction', 'adjustment']
        ).order_by('-created_at')[:10]

        # Count pending verification (deliveries waiting for staff verification)
        pending_verification_count = delivery_models.DeliveryTask.objects.filter(
            driver=driver,
            dl_task_status='delivered',
            earnings_verification_status='pending'
        ).count()

        context = {
            'driver': driver,
            'completed_tasks': page_obj,
            'page_obj': page_obj,
            'filter_params': filter_params,
            'total_delivery_fee': total_delivery_fee,
            'delivered_count': delivered_count,
            'returned_count': returned_count,
            'total_count': total_count,
            'selected_days': days,
            'selected_status': status_filter,
            'selected_settlement': settlement_filter,
            'recent_settlements': recent_settlements,
            'unsettled_tasks': unsettled_tasks,
            'unsettled_total': unsettled_total,
            'pending_earnings': driver.pending_earnings or 0,
            'pending_verification_count': pending_verification_count,
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
        try:
            days = int(request.GET.get('days', 30))
        except (ValueError, TypeError):
            days = 30

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


# Finance Summary ----------------------------------------------------------------------------------------------------------------------------
@login_required(login_url='/accounts/login/')
@driver_required
def fleet_finance_summary(request):
    """Finance overview dashboard for drivers"""
    try:
        driver = fleet_models.Driver.objects.get(user_id=request.user.id)

        from datetime import timedelta
        from django.db.models import Sum, Count, Q
        from decimal import Decimal

        days = int(request.GET.get('days', 30))
        start_date = timezone.now() - timedelta(days=days)

        # Wallet status
        wallet_status = WalletService.get_wallet_status(driver)

        # Transaction summary by type for the period
        txns = fleet_models.DriverTransaction.objects.filter(
            driver=driver,
            created_at__gte=start_date
        )

        # COD pipeline summary
        cod_collected = txns.filter(
            transaction_type='cod_collection'
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0')

        cod_deposited = txns.filter(
            transaction_type__in=['cod_deposit', 'cod_driver_settle']
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0')

        cod_returned = txns.filter(
            transaction_type='cod_return'
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0')

        # Earnings summary
        earnings_total = txns.filter(
            transaction_type='earning'
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0')

        settlements_total = txns.filter(
            transaction_type='settlement'
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0')

        bonuses_total = txns.filter(
            transaction_type='bonus'
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0')

        deductions_total = txns.filter(
            transaction_type='deduction'
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0')

        # Charges summary
        charges = txns.filter(
            transaction_type__in=['delivery_charge', 'fulfillment_charge', 'inventory_handling', 'other_charge']
        ).values('transaction_type').annotate(
            total=Sum('amount'),
            count=Count('id')
        )

        charges_dict = {c['transaction_type']: c for c in charges}

        # Recent transactions (last 10)
        recent_transactions = txns.select_related(
            'delivery_task', 'settlement', 'created_by'
        ).order_by('-created_at')[:10]

        # Transaction count by type
        type_counts = txns.values('transaction_type').annotate(
            count=Count('id'),
            total=Sum('amount')
        ).order_by('-count')

        context = {
            'driver': driver,
            'wallet_status': wallet_status,
            'selected_days': days,
            'cod_collected': abs(cod_collected),
            'cod_deposited': abs(cod_deposited),
            'cod_returned': abs(cod_returned),
            'earnings_total': earnings_total,
            'settlements_total': abs(settlements_total),
            'bonuses_total': bonuses_total,
            'deductions_total': abs(deductions_total),
            'charges_dict': charges_dict,
            'recent_transactions': recent_transactions,
            'type_counts': type_counts,
        }

        return render(request, 'fleet/parts/fleet_finance_summary.html', context)

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
        try:
            days = int(period)
        except (ValueError, TypeError):
            days = 30
            period = '30'

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
        # Single query with select_related to avoid duplicate profile query
        driver = fleet_models.Driver.objects.select_related('user', 'profile', 'profile__user').get(driver_id=fleet_id)
    except fleet_models.Driver.DoesNotExist:
        logger.warning(f'driver does not exist for fleet_id={fleet_id}')
        return redirect('/fleet/')
    logger.debug(f'driver_profile for driver_id={driver.driver_id}')

    profile = driver.profile
    # Get or create profile picture to avoid DoesNotExist error
    profile_picture, _ = core_models.ProfilePicture.objects.get_or_create(
        user_id=driver.user_id, defaults={'profile': profile}
    )
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
            user_id=request.user.id, defaults={'profile': profile}
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
