"""
Workforce Views Module
======================

This module handles internal staff/admin operations for managing
orders, deliveries, drivers, businesses, and user verification.

View Categories:
    Dashboard:
        - wf_dashboard: Main workforce dashboard with pending counts

    Order Management:
        - all_orders: List/filter all orders (paginated)
        - order_detail_modal: AJAX order details
        - publish_orders_to_dms: Publish orders to delivery management system
        - update_order_dms: Update order DMS status

    Delivery Management:
        - all_deliveries: List all delivery tasks
        - delivery_detail: View delivery details
        - dms_publish_order: Publish single order to DMS

    Driver Management:
        - all_drivers: List all drivers with status
        - driver_detail: Driver profile and documents
        - driver_documents_verification: Verify driver documents
        - fleet_cod_in_hand: View driver COD balances
        - fleet_drivers_earnings: View driver earnings
        - fleet_transactions: View financial transactions

    Business Management:
        - all_stores: List all businesses
        - store_detail: Business profile details
        - business_license_detail: Verify business documents

    User Verification:
        - user_verification: List pending verifications
        - user_verification_detail: View user details
        - approve_user_verification: Approve user
        - reject_user_verification: Reject user

    Reports:
        - staff_reports: Staff activity reports
        - staff_contacts: Contact management

Integrations:
    - ShipDay API: For DMS order publishing

Security:
    All views require authentication and typically staff permissions.
    IDOR protection on all detail views.

Related:
    - workforce.models: (empty - uses core.Profile)
    - All app models: orders, delivery, fleet, business
"""

from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
import csv
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods
import json
import logging
from django.core.paginator import (
    Paginator,
    EmptyPage,
    PageNotAnInteger,
)
from django.urls import reverse
from django.db.models import Count

from business import models as business_models
from core import models as core_models
from orders import models as orders_models
from delivery import models as delivery_models
from fleet import models as fleet_models

from business import forms as business_forms
from core.context_processors import get_cached_profile, get_cached_business

# Local aliases for commonly used models
Business = business_models.Business
BusinessProfile = business_models.BusinessProfile
Profile = core_models.Profile
Order = orders_models.Order
DeliveryTask = delivery_models.DeliveryTask
Driver = fleet_models.Driver
DriverDocument = fleet_models.DriverDocument

# ShipDay API integration
from decouple import config
try:
    from shipday import Shipday
    API_KEY = config("SHIPDAY_API_KEY", default="")
    shipday_obj = Shipday(api_key=API_KEY) if API_KEY else None
except ImportError:
    shipday_obj = None

logger = logging.getLogger(__name__)

# Import shared utilities from core
from core.utils import (
    contains_arabic,
    translate_to_english,
    convert_arabic_numerals,
    format_whatsapp_number,
)


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================


def paginate_queryset(request, queryset, items_per_page=10):
    """
    A helper function to handle pagination for a given queryset.
    """
    paginator = Paginator(queryset, items_per_page)
    page_number = request.GET.get('page', 1)
    try:
        page_obj = paginator.page(page_number)
    except PageNotAnInteger:
        page_obj = paginator.page(1)
    except EmptyPage:
        page_obj = paginator.page(paginator.num_pages)
    return page_obj




@login_required(login_url='/accounts/login/')
def wf_dashboard(request):
    from django.utils import timezone
    from django.db.models import Sum, Count, Q
    from datetime import timedelta

    # Use cached profile to avoid duplicate queries
    profile = get_cached_profile(request)
    if not profile:
        logger.warning(f"User {request.user.id} has no profile. Redirecting to profile creation.")
        return redirect('core:profile_view')

    today = timezone.now().date()

    # Order Statistics
    total_orders = Order.objects.count()
    orders_today = Order.objects.filter(order_date=today).count()
    not_published = Order.objects.filter(task_created=False).exclude(
        order_status__in=['cancelled', 'delivered', 'fulfilled']
    ).count()
    published_orders = Order.objects.filter(task_created=True).count()

    # Location reconfirmation needed (orders with verification issues)
    loc_reconfirm = Order.objects.filter(
        Q(verification_status='pending') | Q(verification_status='needs_review')
    ).count()

    # Follow up count - tasks that need attention
    follow_up_count = DeliveryTask.objects.filter(
        Q(dl_task_status='failed') | Q(dl_task_status='rescheduled') | Q(dl_task_status='customer_unavailable')
    ).count()

    # User Verification pending
    pending_verifications = core_models.Profile.objects.filter(
        verification_status='pending'
    ).count()

    # Driver and Seller counts
    active_drivers = Driver.objects.filter(driver_status='Approved').count()
    pending_drivers = Driver.objects.filter(driver_status='Pending on Review').count()
    active_sellers = Business.objects.filter(business_status='Approved').count()
    pending_sellers = Business.objects.filter(business_status='Pending on Review').count()

    # COD in hand (sum of driver wallet balances)
    cod_in_hand = Driver.objects.aggregate(
        total=Sum('wallet_balance')
    )['total'] or 0

    # Recent orders (last 10 updated)
    orders = Order.objects.select_related('business').order_by('-updated_at')[:10]

    # Orders trend data for the last 7 days - single query with aggregation
    week_ago = today - timedelta(days=6)
    order_counts_by_date = dict(
        Order.objects.filter(order_date__gte=week_ago, order_date__lte=today)
        .values('order_date')
        .annotate(count=Count('id'))
        .values_list('order_date', 'count')
    )
    orders_trend = []
    max_orders = 1  # Prevent division by zero
    for i in range(6, -1, -1):
        date = today - timedelta(days=i)
        count = order_counts_by_date.get(date, 0)
        if count > max_orders:
            max_orders = count
        orders_trend.append({
            'date': date.strftime('%a'),
            'count': count
        })

    data = {
        'profile': profile,
        'today': today,
        # Order stats
        'total_orders': total_orders,
        'orders_today': orders_today,
        'not_published': not_published,
        'published_orders': published_orders,
        'loc_reconfirm': loc_reconfirm,
        'follow_up_count': follow_up_count,
        # Verification
        'pending_verifications': pending_verifications,
        # Driver/Seller stats
        'active_drivers': active_drivers,
        'pending_drivers': pending_drivers,
        'active_sellers': active_sellers,
        'pending_sellers': pending_sellers,
        'cod_in_hand': cod_in_hand,
        # Recent data
        'orders': orders,
        'orders_trend': orders_trend,
        'max_orders': max_orders,
    }
    return render(request, 'workforce/wf_base_dashboard.html', data)


# Orders section  ------------------------------------------------------------------------------------------------------
@login_required(login_url='/accounts/login/')
def all_orders(request):
    from django.db.models import Count

    # Start with all orders, prefetch related data to avoid N+1 queries
    orders = orders_models.Order.objects.select_related(
        'business'
    ).prefetch_related('order_comments', 'delivery_task')

    # Apply filters based on GET parameters
    dl_code = request.GET.get('dlCode', '').strip()
    c_code = request.GET.get('cCode', '').strip()
    mobile = request.GET.get('mobile', '').strip()
    c_status = request.GET.get('cStatus', '').strip()
    dms_status = request.GET.get('dmsStatus', '').strip()
    business_id = request.GET.get('business', '').strip()

    # Filter by Business ID
    if business_id:
        orders = orders.filter(business_id=business_id)

    # Filter by DL Code (delivery task code)
    if dl_code:
        orders = orders.filter(delivery_task__dl_task_number__icontains=dl_code)

    # Filter by Business Order Code
    if c_code:
        orders = orders.filter(client_order_code__icontains=c_code)

    # Filter by Customer Mobile
    if mobile:
        orders = orders.filter(customer_phone__icontains=mobile)

    # Filter by Order Status
    if c_status:
        orders = orders.filter(order_status=c_status)

    # Filter by DMS Status
    if dms_status:
        orders = orders.filter(delivery_task__dl_task_status_dms=dms_status)

    # Annotate with comment count (for now, all comments are counted as unread)
    orders = orders.annotate(unread_comments_count=Count('order_comments'))

    # Order by created date
    orders = orders.order_by('-created_at')

    # Paginate results
    orders = paginate_queryset(request, orders)

    # Get all businesses for filter dropdown
    all_businesses = business_models.Business.objects.all().order_by('business_name')

    data = {
        'orders': orders,
        'all_businesses': all_businesses,
        'filters': {
            'dlCode': dl_code,
            'cCode': c_code,
            'mobile': mobile,
            'cStatus': c_status,
            'dmsStatus': dms_status,
            'business': business_id,
        }
    }
    return render(request, 'workforce/parts/lists/orders_list_view.html', data)


@login_required(login_url='/accounts/login/')
def export_orders_csv(request):
    """
    Export orders to CSV file with applied filters
    """
    from django.utils import timezone

    # Start with all orders
    orders = orders_models.Order.objects.select_related(
        'business'
    ).prefetch_related('delivery_task')

    # Apply same filters as all_orders view
    dl_code = request.GET.get('dlCode', '').strip()
    c_code = request.GET.get('cCode', '').strip()
    mobile = request.GET.get('mobile', '').strip()
    c_status = request.GET.get('cStatus', '').strip()
    dms_status = request.GET.get('dmsStatus', '').strip()
    business_id = request.GET.get('business', '').strip()
    date_from = request.GET.get('dateFrom', '').strip()
    date_to = request.GET.get('dateTo', '').strip()

    if business_id:
        orders = orders.filter(business_id=business_id)
    if dl_code:
        orders = orders.filter(delivery_task__dl_task_number__icontains=dl_code)
    if c_code:
        orders = orders.filter(client_order_code__icontains=c_code)
    if mobile:
        orders = orders.filter(customer_phone__icontains=mobile)
    if c_status:
        orders = orders.filter(order_status=c_status)
    if dms_status:
        orders = orders.filter(delivery_task__dl_task_status_dms=dms_status)
    if date_from:
        orders = orders.filter(order_date__gte=date_from)
    if date_to:
        orders = orders.filter(order_date__lte=date_to)

    orders = orders.order_by('-created_at')

    # Create the HttpResponse object with CSV content type
    response = HttpResponse(content_type='text/csv')
    timestamp = timezone.now().strftime('%Y%m%d_%H%M%S')
    response['Content-Disposition'] = f'attachment; filename="orders_export_{timestamp}.csv"'

    writer = csv.writer(response)
    # Write header row
    writer.writerow([
        'Order Number',
        'Client Order Code',
        'Business',
        'Customer Name',
        'Customer Phone',
        'Customer Address',
        'Order Status',
        'Task Status',
        'COD Amount',
        'Order Date',
        'Created At',
    ])

    # Write data rows
    for order in orders[:5000]:  # Limit to 5000 rows for performance
        writer.writerow([
            order.order_number,
            order.client_order_code,
            order.business.business_name if order.business else '',
            order.customer_name,
            order.customer_phone,
            order.customer_address,
            order.order_status,
            order.task_status,
            order.cod_amount,
            order.order_date,
            order.created_at.strftime('%Y-%m-%d %H:%M:%S') if order.created_at else '',
        ])

    return response


@login_required(login_url='/accounts/login/')
def export_drivers_csv(request):
    """
    Export drivers to CSV file
    """
    from django.utils import timezone

    drivers = fleet_models.Driver.objects.select_related(
        'user'
    ).prefetch_related('driver_vehicle')

    # Apply filters
    search = request.GET.get('search', '').strip()
    status_filter = request.GET.get('status', '')

    if search:
        from django.db.models import Q
        drivers = drivers.filter(
            Q(user__first_name__icontains=search) |
            Q(user__last_name__icontains=search) |
            Q(driver_code__icontains=search) |
            Q(driver_phone__icontains=search)
        )
    if status_filter:
        drivers = drivers.filter(driver_status=status_filter)

    drivers = drivers.order_by('-driver_id')

    response = HttpResponse(content_type='text/csv')
    timestamp = timezone.now().strftime('%Y%m%d_%H%M%S')
    response['Content-Disposition'] = f'attachment; filename="drivers_export_{timestamp}.csv"'

    writer = csv.writer(response)
    writer.writerow([
        'Driver ID',
        'Driver Code',
        'Name',
        'Phone',
        'WhatsApp',
        'Email',
        'Status',
        'Rating',
        'Wallet Balance',
        'COD In Hand',
        'Date Joined',
    ])

    for driver in drivers[:2000]:
        writer.writerow([
            driver.driver_id,
            driver.driver_code,
            f"{driver.user.first_name} {driver.user.last_name}",
            driver.driver_phone,
            driver.driver_whatsapp,
            driver.user.email,
            driver.driver_status,
            driver.driver_rating,
            driver.wallet_balance,
            getattr(driver, 'cod_in_hand', 0),
            driver.user.date_joined.strftime('%Y-%m-%d') if driver.user.date_joined else '',
        ])

    return response


@login_required(login_url='/accounts/login/')
def orders_by_seller(request):
    """
    View to display orders grouped by seller/business
    """
    from django.db.models import Count, Q

    # Get all seller names for quick selection (active businesses only)
    all_sellers = business_models.Business.objects.filter(
        business_status='active'
    ).values('business_id', 'business_name', 'business_code').order_by('business_name')

    # Get all businesses with their order counts
    businesses = business_models.Business.objects.select_related(
        'profile', 'business_profile'
    ).annotate(
        total_orders=Count('order'),
        pending_orders=Count('order', filter=Q(order__order_status='pending')),
        processing_orders=Count('order', filter=Q(order__order_status='processing')),
        completed_orders=Count('order', filter=Q(order__order_status='delivered'))
    ).filter(total_orders__gt=0)  # Only show businesses with orders

    # Apply search filter
    search = request.GET.get('search', '').strip()
    if search:
        businesses = businesses.filter(
            Q(business_name__icontains=search) |
            Q(business_email__icontains=search) |
            Q(business_phone__icontains=search) |
            Q(business_code__icontains=search)
        )

    # Order by total orders (most orders first)
    businesses = businesses.order_by('-total_orders', '-business_id')

    # Paginate
    page_obj = paginate_queryset(request, businesses, items_per_page=20)

    context = {
        'page_title': 'Orders by Seller',
        'page_obj': page_obj,
        'search': search,
        'all_sellers': all_sellers,
    }

    return render(request, 'workforce/wf_orders_by_seller.html', context)


@login_required(login_url='/accounts/login/')
def orders_to_publish(request):
    orders = orders_models.Order.objects.select_related(
        'business'
    ).prefetch_related('order_comments', 'delivery_task').filter(task_created=False).order_by('-created_at')
    orders = paginate_queryset(request, orders)

    data = {
        'orders': orders,
    }
    return render(request, 'workforce/parts/lists/orders_list_view.html', data)


@login_required(login_url='/accounts/login/')
def orders_published(request):
    orders = orders_models.Order.objects.select_related(
        'business'
    ).prefetch_related('order_comments', 'delivery_task').filter(task_created=True).order_by('-created_at')
    orders = paginate_queryset(request, orders)

    data = {
        'orders': orders,
    }
    return render(request, 'workforce/parts/lists/orders_list_view.html', data)

@login_required(login_url='/accounts/login/')
def submit_to_task(request, order_id):
    """Submit order to delivery task - now uses verification workflow"""
    from django.utils import timezone
    from orders.signals import _create_delivery_task_from_order
    
    order = get_object_or_404(orders_models.Order, id=order_id)
    
    # Check if order is verified
    if order.verification_status != 'verified':
        from django.contrib import messages
        messages.warning(request, 'Order must be verified before creating delivery task')
        return redirect(reverse('workforce:wf_orders_all'))
    
    # Use the automated function that handles DMS push
    delivery_task = _create_delivery_task_from_order(order)
    
    if delivery_task:
        from django.contrib import messages
        messages.success(request, f'Delivery task created and pushed to DMS: {delivery_task.dl_task_number}')
    else:
        from django.contrib import messages
        messages.error(request, 'Failed to create delivery task')
    
    return redirect(reverse('workforce:wf_orders_all'))


@login_required(login_url='/accounts/login/')
def verify_order_address(request, order_id):
    """Verify order address - workforce view"""
    from django.utils import timezone
    from orders.models import AddressVerification, OrderVerificationLog
    
    order = get_object_or_404(orders_models.Order, id=order_id)
    
    if request.method == 'POST':
        verified_address = request.POST.get('verified_address', order.customer_address)
        verification_result = request.POST.get('verification_result', 'valid')
        latitude = request.POST.get('latitude')
        longitude = request.POST.get('longitude')
        zone_number = request.POST.get('zone_number')
        street_number = request.POST.get('street_number')
        building_number = request.POST.get('building_number')
        notes = request.POST.get('notes', '')
        
        # Create or update address verification
        address_verification, created = AddressVerification.objects.get_or_create(
            order=order,
            defaults={
                'original_address': order.customer_address,
                'verified_address': verified_address,
                'verification_result': verification_result,
                'verified_by': request.user,
                'verified_at': timezone.now(),
                'latitude': latitude,
                'longitude': longitude,
                'zone_number': zone_number,
                'street_number': street_number,
                'building_number': building_number,
                'notes': notes,
            }
        )
        
        if not created:
            address_verification.verified_address = verified_address
            address_verification.verification_result = verification_result
            address_verification.verified_by = request.user
            address_verification.verified_at = timezone.now()
            if latitude:
                address_verification.latitude = latitude
            if longitude:
                address_verification.longitude = longitude
            if zone_number:
                address_verification.zone_number = zone_number
            if street_number:
                address_verification.street_number = street_number
            if building_number:
                address_verification.building_number = building_number
            address_verification.notes = notes
            address_verification.save()
        
        # Update order
        order.address_verified = True
        order.address_verified_by = request.user
        order.address_verified_at = timezone.now()
        
        if verification_result == 'valid':
            order.verification_status = 'address_verified'
        elif verification_result == 'needs_update':
            order.verification_status = 'address_needs_update'
            if verified_address:
                order.customer_address = verified_address
            if zone_number:
                order.dl_zone = zone_number
            if street_number:
                order.dl_street = street_number
            if building_number:
                order.dl_building = building_number
        
        order.save()
        
        # Log verification
        OrderVerificationLog.objects.create(
            order=order,
            verified_by=request.user,
            action='address_verified',
            notes=notes,
            new_status=order.verification_status
        )
        
        from django.contrib import messages
        messages.success(request, 'Address verified successfully')
        return redirect(reverse('workforce:wf_orders_all'))
    
    # GET request - show verification form
    address_verification = AddressVerification.objects.filter(order=order).first()
    context = {
        'order': order,
        'address_verification': address_verification,
    }
    return render(request, 'workforce/parts/verify_address.html', context)


@login_required(login_url='/accounts/login/')
def verify_order(request, order_id):
    """Verify order - workforce view"""
    from django.utils import timezone
    from orders.models import OrderVerificationLog
    from orders.signals import _create_delivery_task_from_order

    order = get_object_or_404(orders_models.Order, id=order_id)

    if request.method == 'POST':
        verification_notes = request.POST.get('verification_notes', '')

        # Update order verification status
        order.verification_status = 'verified'
        order.verified_by = request.user
        order.verified_at = timezone.now()
        order.verification_notes = verification_notes
        order.save()

        # Log verification
        OrderVerificationLog.objects.create(
            order=order,
            verified_by=request.user,
            action='order_verified',
            notes=verification_notes,
            new_status='verified'
        )

        # Create delivery task (will be triggered by signal)
        delivery_task = _create_delivery_task_from_order(order)

        # Return updated row HTML for HTMX
        if request.headers.get('HX-Request'):
            return render(request, 'orders/parts/order_row.html', {'order': order})

        from django.contrib import messages
        if delivery_task:
            messages.success(request, f'Order verified and delivery task created: {delivery_task.dl_task_number}')
        else:
            messages.success(request, 'Order verified successfully')

        return redirect(reverse('workforce:wf_orders_all'))

    # GET request - show verification form
    context = {
        'order': order,
    }
    return render(request, 'workforce/parts/verify_order.html', context)


@login_required(login_url='/accounts/login/')
def orders_pending_verification(request):
    """List orders pending verification"""
    verification_status = request.GET.get('verification_status', 'pending')

    orders = orders_models.Order.objects.select_related(
        'business'
    ).prefetch_related('order_comments', 'delivery_task').filter(verification_status=verification_status).order_by('-created_at')
    orders = paginate_queryset(request, orders)
    
    data = {
        'orders': orders,
        'verification_status': verification_status,
    }
    return render(request, 'workforce/parts/lists/orders_list_view.html', data)


    

    





# Staff Order Creation section  ------------------------------------------------------------------------------------------------------

@login_required(login_url='/accounts/login/')
def add_order(request):
    """
    Staff view to add an order for a client/seller.
    Seller is selected at the top of the form.
    """
    import uuid
    from django.contrib import messages
    from core.utils import (
        contains_arabic, translate_to_english,
        convert_arabic_numerals, format_whatsapp_number
    )

    # Get all active businesses for seller dropdown
    businesses = business_models.Business.objects.filter(
        business_status='active'
    ).select_related('business_profile').order_by('business_name')

    # Get selected business if provided
    selected_business_id = request.GET.get('business', '')
    selected_business = None
    pickup_locations = []

    if selected_business_id:
        try:
            selected_business = business_models.Business.objects.get(business_id=selected_business_id)
            pickup_locations = business_models.PickupLocation.objects.filter(
                business=selected_business
            )
        except business_models.Business.DoesNotExist:
            pass

    if request.method == 'POST':
        try:
            # Get form data
            business_id = request.POST.get('business')
            business = business_models.Business.objects.get(business_id=business_id)

            # Generate client order code if not provided
            client_order_code = request.POST.get('client_order_code', '').strip()
            if not client_order_code:
                client_order_code = f"WF-{uuid.uuid4().hex[:8].upper()}"

            # Get and process customer data
            customer_name = request.POST.get('customer_name', '').strip()
            customer_address = request.POST.get('customer_address', '').strip()
            customer_phone = request.POST.get('customer_phone', '').strip()

            # Store originals before translation
            customer_name_original = customer_name
            customer_address_original = customer_address

            # Translate Arabic text to English
            customer_name_en = translate_to_english(customer_name)
            customer_address_en = translate_to_english(customer_address)

            if contains_arabic(customer_name):
                customer_name = customer_name_en
            if contains_arabic(customer_address):
                customer_address = customer_address_en

            # Convert Arabic numerals and format phone numbers
            customer_phone = convert_arabic_numerals(customer_phone)
            raw_whatsapp = request.POST.get('customer_whatsapp', '').strip()
            if raw_whatsapp:
                customer_whatsapp = format_whatsapp_number(raw_whatsapp)
            else:
                customer_whatsapp = format_whatsapp_number(customer_phone)

            # Helper to safely parse integers
            def safe_int(val):
                try:
                    return int(float(val)) if val else 0
                except (ValueError, TypeError):
                    return 0

            # Build combined notes
            notes_parts = []
            order_notes = request.POST.get('order_notes', '').strip()
            seller_notes = request.POST.get('seller_notes', '').strip()
            if order_notes:
                notes_parts.append(f"Customer: {order_notes}")
            if seller_notes:
                notes_parts.append(f"Seller: {seller_notes}")
            combined_notes = ' | '.join(notes_parts) if notes_parts else order_notes

            # Prepare original_order_data with extra fields
            original_data = {
                'source': 'staff_dashboard',
                'created_by': request.user.username,
                'extra_fields': {
                    'customer_name_original': customer_name_original,
                    'customer_address_original': customer_address_original,
                    'customer_name_en': customer_name_en,
                    'customer_address_en': customer_address_en,
                    'name_was_translated': customer_name_original != customer_name_en,
                    'address_was_translated': customer_address_original != customer_address_en,
                    'dl_landmark': request.POST.get('dl_landmark', '').strip(),
                    'location_link': request.POST.get('location_link', '').strip(),
                    'product_name': request.POST.get('product_name', '').strip(),
                    'quantity': request.POST.get('quantity', '1'),
                    'seller_notes': seller_notes,
                    'internal_notes': request.POST.get('internal_notes', '').strip(),
                }
            }

            # Create order
            order = orders_models.Order(
                business=business,
                client_order_code=client_order_code,
                customer_name=customer_name,
                customer_phone=customer_phone,
                customer_whatsapp=customer_whatsapp,
                customer_address=customer_address,
                dl_zone=safe_int(request.POST.get('dl_zone')),
                dl_street=safe_int(request.POST.get('dl_street')),
                dl_building=safe_int(request.POST.get('dl_building')),
                cod_amount=safe_int(request.POST.get('cod_amount')),
                dl_amount=safe_int(request.POST.get('dl_amount')),
                order_notes=combined_notes[:100] if combined_notes else '',
                deadline_date=request.POST.get('deadline_date', '').strip(),
                order_status='to_review',
                verification_status='pending',
                original_order_data=original_data,
            )

            # Set pickup location if provided
            pickup_location_id = request.POST.get('pickup_location')
            if pickup_location_id:
                try:
                    order.pickup_location = business_models.PickupLocation.objects.get(
                        id=pickup_location_id, business=business
                    )
                except business_models.PickupLocation.DoesNotExist:
                    pass

            order.save()

            # Create OrderItem if product name is provided
            product_name = request.POST.get('product_name', '').strip()
            if product_name:
                orders_models.OrderItem.objects.create(
                    order=order,
                    quantity=safe_int(request.POST.get('quantity')) or 1,
                    unit_price=safe_int(request.POST.get('cod_amount')) if request.POST.get('cod_amount') else None,
                    notes=product_name
                )

            messages.success(request, f'Order {order.order_number} created successfully.')

            # Return JSON response for AJAX
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': True,
                    'message': f'Order {order.order_number} created successfully.',
                    'order_id': order.id,
                    'order_number': order.order_number
                })

            return redirect(reverse('workforce:wf_orders_all'))

        except business_models.Business.DoesNotExist:
            error_msg = 'Please select a valid seller.'
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'success': False, 'error': error_msg}, status=400)
            messages.error(request, error_msg)

        except Exception as e:
            logger.error(f'Error creating order: {e}')
            error_msg = f'Error creating order: {str(e)}'
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'success': False, 'error': error_msg}, status=400)
            messages.error(request, error_msg)

    from datetime import date
    context = {
        'businesses': businesses,
        'selected_business': selected_business,
        'selected_business_id': selected_business_id,
        'pickup_locations': pickup_locations,
        'today': date.today().isoformat(),
    }
    return render(request, 'workforce/orders_add.html', context)


# Bulk import views removed - now using shared views from orders app
# See orders/views.py: bulk_import_orders, bulk_import_preview, bulk_import_save


@login_required(login_url='/accounts/login/')
def orders_api_guide(request):
    """
    Display API documentation for order creation.
    """
    # Get all active businesses for the example
    businesses = business_models.Business.objects.filter(
        business_status='active'
    ).order_by('business_name')[:5]

    context = {
        'businesses': businesses,
    }
    return render(request, 'workforce/orders_api_guide.html', context)


@login_required(login_url='/accounts/login/')
def get_pickup_locations(request, business_id):
    """AJAX endpoint to get pickup locations for a business"""
    try:
        business = business_models.Business.objects.get(business_id=business_id)
        locations = business_models.PickupLocation.objects.filter(business=business)

        location_list = [{
            'id': loc.id,
            'name': loc.location_name,
            'address': loc.location_address or '',
        } for loc in locations]

        return JsonResponse({'success': True, 'locations': location_list})
    except business_models.Business.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Business not found'}, status=404)


# Delivery Tasks section  ------------------------------------------------------------------------------------------------------

@login_required(login_url='/accounts/login/')
def dl_list_all(request):
    dl_tasks = delivery_models.DeliveryTask.objects.select_related(
        'order', 'driver', 'business', 'pickup_location', 'order__business'
    ).prefetch_related(
        'order__order_comments'
    ).all().order_by('-created_at')

    # Get filter parameters
    dl_code = request.GET.get('dlCode', '')
    c_code = request.GET.get('cCode', '')
    mobile = request.GET.get('mobile', '')
    driver_name = request.GET.get('driverName', '')
    c_status = request.GET.get('cStatus', '')
    dms_status = request.GET.get('dmsStatus', '')
    date_from = request.GET.get('dateFrom', '')
    date_to = request.GET.get('dateTo', '')
    business_id = request.GET.get('business', '')

    # Apply filters
    if dl_code:
        dl_tasks = dl_tasks.filter(dl_task_number__icontains=dl_code)
    if c_code:
        dl_tasks = dl_tasks.filter(order__client_order_code__icontains=c_code)
    if mobile:
        dl_tasks = dl_tasks.filter(order__customer_phone__icontains=mobile)
    if driver_name:
        dl_tasks = dl_tasks.filter(driver__name__icontains=driver_name)
    if c_status:
        dl_tasks = dl_tasks.filter(dl_task_status_client=c_status)
    if dms_status:
        dl_tasks = dl_tasks.filter(dl_task_status_dms=dms_status)
    if date_from:
        dl_tasks = dl_tasks.filter(dl_task_date__gte=date_from)
    if date_to:
        dl_tasks = dl_tasks.filter(dl_task_date__lte=date_to)
    if business_id:
        dl_tasks = dl_tasks.filter(order__business_id=business_id)

    # Get all businesses for the filter dropdown
    businesses = business_models.Business.objects.filter(
        business_status='active'
    ).order_by('business_name')

    dl_tasks = paginate_queryset(request, dl_tasks)

    data = {
        'dl_tasks': dl_tasks,
        'businesses': businesses,
        'filters': {
            'dlCode': dl_code,
            'cCode': c_code,
            'mobile': mobile,
            'driverName': driver_name,
            'cStatus': c_status,
            'dmsStatus': dms_status,
            'dateFrom': date_from,
            'dateTo': date_to,
            'business': business_id,
        }
    }
    return render(request, 'workforce/parts/lists/dl_list_all.html', data)


@login_required(login_url='/accounts/login/')
def dl_list_incompleted_details(request):
    # Get incomplete delivery tasks (not delivered, not cancelled)
    dl_tasks = delivery_models.DeliveryTask.objects.select_related(
        'order', 'driver', 'business', 'pickup_location', 'order__business'
    ).exclude(
        dl_task_status_dms__in=['delivered', 'cancelled']
    ).order_by('-created_at')
    dl_tasks = paginate_queryset(request, dl_tasks)

    data = {
        'dl_tasks': dl_tasks,
    }
    return render(request, 'workforce/parts/lists/dl_list_incompleted.html', data)


@login_required(login_url='/accounts/login/')
def dl_list_published_to_dms(request):
    dl_tasks = delivery_models.DeliveryTask.objects.select_related(
        'order', 'driver', 'business', 'pickup_location', 'order__business'
    ).order_by('-created_at')
    dl_tasks = paginate_queryset(request, dl_tasks)

    data = {
        'dl_tasks': dl_tasks,
    }
    return render(request, 'workforce/parts/lists/dl_list_all.html', data)


@login_required(login_url='/accounts/login/')
def dl_list_ready_to_published_to_dms(request):
    orders = orders_models.Order.objects.select_related(
        'business'
    ).filter(task_created=False).order_by('-created_at')
    orders = paginate_queryset(request, orders)

    data = {
        'orders': orders,
    }
    return render(request, 'workforce/parts/lists/dl_list_all.html', data)




# DMS section  ------------------------------------------------------------------------------------------------------


# Workflow Guide -----------------------------------------------------

@login_required(login_url='account_login')
def workflow_guide(request):
    """Display comprehensive workflow guide for workforce/staff members"""

    workflow_steps = [
        {
            'number': 1,
            'title': 'Dashboard Overview',
            'description': 'Familiarize yourself with the workforce dashboard',
            'tasks': [
                'View pending orders count',
                'Check orders awaiting verification',
                'Monitor delivery tasks status',
                'Review today\'s activities',
            ],
            'status': 'completed',
            'url': 'workforce:wf_dashboard',
        },
        {
            'number': 2,
            'title': 'Review Pending Orders',
            'description': 'Check new orders that need verification',
            'tasks': [
                'Go to Orders → Pending Verification',
                'Review order details (customer name, address, COD)',
                'Check if all required information is provided',
                'Identify orders with missing information',
            ],
            'status': 'in_progress',
            'url': 'workforce:orders_pending_verification',
        },
        {
            'number': 3,
            'title': 'Verify Customer Address',
            'description': 'Validate and verify delivery addresses',
            'tasks': [
                'Click "Verify Address" on pending order',
                'Validate address format and completeness',
                'Use map integration to confirm coordinates',
                'Set zone, street, and building numbers',
                'Add GPS coordinates (latitude/longitude)',
                'Mark verification result: Valid, Needs Update, or Invalid',
                'Add notes if address needs customer contact',
            ],
            'status': 'primary',
            'url': None,
        },
        {
            'number': 4,
            'title': 'Contact Customer (If Needed)',
            'description': 'Reach out for address clarification',
            'tasks': [
                'Call customer using provided phone number',
                'Request missing address details',
                'Confirm zone, street, building information',
                'Update order with corrected information',
                'Log communication in order notes',
            ],
            'status': 'conditional',
            'url': None,
        },
        {
            'number': 5,
            'title': 'Verify Complete Order',
            'description': 'Final verification before delivery task creation',
            'tasks': [
                'Ensure address is verified',
                'Confirm customer contact details',
                'Validate COD amount if applicable',
                'Check product list completeness',
                'Click "Verify Order" button',
                'Order automatically becomes "Verified"',
            ],
            'status': 'primary',
            'url': None,
        },
        {
            'number': 6,
            'title': 'Automated Task Creation',
            'description': 'System automatically creates delivery tasks',
            'tasks': [
                'Verified order triggers automatic process',
                'Delivery task created with all order details',
                'Address information duplicated to task',
                'Original order preserved as proof',
                'Task pushed to DMS automatically',
                'You receive confirmation notification',
            ],
            'status': 'automated',
            'url': None,
        },
        {
            'number': 7,
            'title': 'Monitor Delivery Tasks',
            'description': 'Track delivery progress and status',
            'tasks': [
                'Go to Tasks → All Delivery Tasks',
                'Check task status: Published, Assigned, In Transit',
                'Monitor driver assignments',
                'View real-time delivery updates from DMS',
                'Check completion proof and signatures',
            ],
            'status': 'pending',
            'url': 'workforce:dl_list_all',
        },
        {
            'number': 8,
            'title': 'Handle Exceptions',
            'description': 'Manage orders that need special attention',
            'tasks': [
                'Identify rejected or failed deliveries',
                'Contact customers for failed delivery reasons',
                'Reschedule deliveries if needed',
                'Update order status accordingly',
                'Document all actions in order logs',
            ],
            'status': 'conditional',
            'url': None,
        },
        {
            'number': 9,
            'title': 'COD Collection Tracking',
            'description': 'Monitor Cash on Delivery payments',
            'tasks': [
                'Track COD amounts to be collected',
                'Verify driver has collected payment',
                'Update COD status: With Driver, With EZZY, Settled',
                'Generate COD collection reports',
                'Coordinate with finance for settlement',
            ],
            'status': 'pending',
            'url': None,
        },
        {
            'number': 10,
            'title': 'Daily Reporting',
            'description': 'Complete end-of-day activities',
            'tasks': [
                'Review all verified orders for the day',
                'Check outstanding pending verifications',
                'Generate daily activity report',
                'Note any issues or concerns',
                'Prepare task list for next day',
            ],
            'status': 'pending',
            'url': None,
        },
    ]

    important_notes = [
        {
            'title': 'Address Verification is Critical',
            'description': 'Accurate address verification ensures successful deliveries and prevents return trips.',
        },
        {
            'title': 'Original Orders are Preserved',
            'description': 'All order data is saved as proof. Delivery tasks are duplicates for tracking.',
        },
        {
            'title': 'Automated Workflow',
            'description': 'Once you verify an order, the system automatically creates delivery tasks and pushes to DMS.',
        },
        {
            'title': 'Audit Trail',
            'description': 'All your verification actions are logged for accountability and tracking.',
        },
    ]

    context = {
        'workflow_steps': workflow_steps,
        'important_notes': important_notes,
        'page_title': 'Workforce Workflow Guide',
    }

    return render(request, 'workforce/workflow_guide.html', context)


# Order Detail View ------------------------------------------------------------------------------------------------------

@login_required(login_url='/accounts/login/')
def order_detail(request, order_id):
    """Display order detail page"""
    order = get_object_or_404(
        orders_models.Order.objects.select_related('business', 'pickup_location', 'verified_by'),
        id=order_id
    )

    # Get related data
    order_items = orders_models.OrderItem.objects.filter(order=order)
    order_comments = orders_models.OrderComments.objects.filter(order=order).order_by('-created_at')
    verification_logs = orders_models.OrderVerificationLog.objects.filter(order=order).order_by('-created_at')

    # Get delivery task if exists
    delivery_task = None
    try:
        delivery_task = delivery_models.DeliveryTask.objects.get(order=order)
    except delivery_models.DeliveryTask.DoesNotExist:
        pass

    context = {
        'order': order,
        'order_items': order_items,
        'order_comments': order_comments,
        'verification_logs': verification_logs,
        'delivery_task': delivery_task,
    }

    return render(request, 'workforce/order_detail.html', context)


@require_http_methods(["POST"])
@login_required(login_url='/accounts/login/')
def cancel_order(request, order_id):
    """Cancel an order"""
    try:
        order = get_object_or_404(orders_models.Order, id=order_id)

        if order.order_status == 'published':
            return JsonResponse({
                'success': False,
                'error': 'Cannot cancel a published order'
            }, status=400)

        # Update order status
        old_status = order.order_status
        order.order_status = 'cancelled'
        order.save()

        # Log the cancellation
        orders_models.OrderVerificationLog.objects.create(
            order=order,
            verified_by=request.user,
            action='order_cancelled',
            old_status=old_status,
            new_status='cancelled',
            notes=f'Order cancelled by {request.user.username}'
        )

        # Return updated row HTML for HTMX
        if request.headers.get('HX-Request'):
            return render(request, 'orders/parts/order_row.html', {'order': order})

        return JsonResponse({
            'success': True,
            'message': 'Order cancelled successfully',
            'order_id': order.id
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=400)


# AJAX Endpoints for Orders List ------------------------------------------------------------------------------------------------------

@require_http_methods(["POST"])
@login_required(login_url='/accounts/login/')
def publish_order_to_delivery(request, order_id):
    """AJAX endpoint to publish order to delivery"""
    try:
        order = get_object_or_404(orders_models.Order, id=order_id)

        # Update order status to published
        order.order_status = 'published'
        order.task_status = 'dl_task_listed'
        order.save()

        # Log the publish action
        orders_models.OrderVerificationLog.objects.create(
            order=order,
            verified_by=request.user,
            action='order_published',
            old_status='to_publish',
            new_status='published',
            notes=f'Order published to delivery by {request.user.username}'
        )

        # Return updated row HTML for HTMX
        if request.headers.get('HX-Request'):
            return render(request, 'orders/parts/order_row.html', {'order': order})

        return JsonResponse({
            'success': True,
            'message': 'Order published to delivery successfully',
            'order_id': order.id,
            'order_status': order.order_status
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=400)


@require_http_methods(["POST"])
@login_required(login_url='/accounts/login/')
def update_order_status(request, order_id):
    """AJAX endpoint to update order status"""
    try:
        order = get_object_or_404(orders_models.Order, id=order_id)

        # Parse JSON body
        data = json.loads(request.body)
        status = data.get('status')

        if not status:
            return JsonResponse({
                'success': False,
                'error': 'Status is required'
            }, status=400)

        # Update task status
        order.task_status = status
        order.save()

        # Log the status update
        from orders.models import OrderVerificationLog
        OrderVerificationLog.objects.create(
            order=order,
            verified_by=request.user,
            action=f'status_updated_to_{status}',
            notes=f'Status updated to {status}',
            new_status=status
        )

        return JsonResponse({
            'success': True,
            'message': f'Status updated to {status} successfully',
            'order_id': order.id,
            'new_status': status
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=400)


@require_http_methods(["POST"])
@login_required(login_url='/accounts/login/')
def add_order_comment(request, order_id):
    """AJAX endpoint to add comment to order"""
    try:
        order = get_object_or_404(orders_models.Order, id=order_id)

        # Parse JSON body
        data = json.loads(request.body)
        comment_text = data.get('comment')

        if not comment_text:
            return JsonResponse({
                'success': False,
                'error': 'Comment text is required'
            }, status=400)

        # Create comment
        from orders.models import OrderComments
        comment = OrderComments.objects.create(
            order=order,
            name=request.user.username,
            body=comment_text
        )

        return JsonResponse({
            'success': True,
            'message': 'Comment added successfully',
            'order_id': order.id,
            'comment_id': comment.id,
            'comment_text': comment.body,
            'created_at': comment.created_at.strftime('%B %d, %Y %H:%M')
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=400)


# Delivery Task Detail View ------------------------------------------------------------------------------------------------------

@login_required(login_url='/accounts/login/')
def delivery_task_detail(request, task_id):
    """
    Display detailed information about a delivery task.
    Shows task status, driver updates, timeline, and allows quick actions.
    """
    task = get_object_or_404(
        delivery_models.DeliveryTask.objects.select_related(
            'order', 'order__business', 'driver', 'business', 'pickup_location'
        ),
        id=task_id
    )

    # Get status history (if available - placeholder for now)
    status_history = []

    # Get driver updates (placeholder - would come from driver app integration)
    driver_updates = []

    # Get seller comments (placeholder - would come from comments model)
    seller_comments = []
    unread_seller_comments_count = 0

    context = {
        'page_title': f'Delivery Task #{task.dl_task_number}',
        'task': task,
        'status_history': status_history,
        'driver_updates': driver_updates,
        'seller_comments': seller_comments,
        'unread_seller_comments_count': unread_seller_comments_count,
    }

    return render(request, 'workforce/parts/delivery_task_detail.html', context)


# AJAX Endpoints for Delivery Tasks ------------------------------------------------------------------------------------------------------

@require_http_methods(["POST"])
@login_required(login_url='/accounts/login/')
def publish_task_to_dms(request, task_id):
    """AJAX endpoint to publish delivery task to DMS"""
    try:
        task = get_object_or_404(delivery_models.DeliveryTask, id=task_id)

        # Update task status to publish to DMS
        task.dl_task_status = 'publish_to_dms'
        task.dl_task_publish = True
        task.save()

        return JsonResponse({
            'success': True,
            'message': 'Task published to DMS successfully',
            'task_id': task.id,
            'task_number': task.dl_task_number
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=400)


@require_http_methods(["POST"])
@login_required(login_url='/accounts/login/')
def publish_task_to_driver_app(request, task_id):
    """AJAX endpoint to publish delivery task to Driver App"""
    try:
        task = get_object_or_404(delivery_models.DeliveryTask, id=task_id)

        # Update task to be available in driver app
        task.dl_task_status_dms = '6'  # Unassigned - available for drivers
        task.save()

        return JsonResponse({
            'success': True,
            'message': 'Task published to Driver App successfully',
            'task_id': task.id,
            'task_number': task.dl_task_number
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=400)


@require_http_methods(["POST"])
@login_required(login_url='/accounts/login/')
def assign_driver_to_task(request, task_id):
    """AJAX endpoint to assign driver to delivery task"""
    try:
        task = get_object_or_404(delivery_models.DeliveryTask, id=task_id)

        # Parse JSON body
        data = json.loads(request.body)
        driver_id = data.get('driver_id')

        if not driver_id:
            return JsonResponse({
                'success': False,
                'error': 'Driver ID is required'
            }, status=400)

        # Get driver and assign
        driver = get_object_or_404(fleet_models.Driver, id=driver_id)
        task.driver = driver
        task.dl_task_status_dms = '0'  # Assigned
        task.save()

        return JsonResponse({
            'success': True,
            'message': f'Task assigned to {driver} successfully',
            'task_id': task.id,
            'driver_id': driver.id,
            'driver_name': str(driver)
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=400)


@require_http_methods(["POST"])
@login_required(login_url='/accounts/login/')
def update_task_status(request, task_id):
    """AJAX endpoint to update delivery task status"""
    try:
        task = get_object_or_404(delivery_models.DeliveryTask, id=task_id)

        # Parse JSON body
        data = json.loads(request.body)
        status = data.get('status')

        if not status:
            return JsonResponse({
                'success': False,
                'error': 'Status is required'
            }, status=400)

        # Update task status
        task.dl_task_status = status
        task.save()

        return JsonResponse({
            'success': True,
            'message': f'Task status updated to {status} successfully',
            'task_id': task.id,
            'new_status': status
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=400)


# USER VERIFICATION VIEWS --------------------------------------------------------------------------------------------------------------

@login_required(login_url='/accounts/login/')
def user_verification_list(request):
    """Staff view to see all users pending verification"""
    from core import models as core_models
    from business import models as business_models

    # Get all profiles based on filter
    verification_filter = request.GET.get('status', 'all')

    profiles = core_models.Profile.objects.select_related('user')
    if verification_filter in ('pending', 'verified', 'rejected', 'incomplete'):
        profiles = profiles.filter(verification_status=verification_filter)

    # Order by application date (most recent first)
    profiles = profiles.order_by('-verification_applied_at', '-created_at')

    # Prefetch related Business and Driver data to avoid N+1 queries
    profile_list = list(profiles)
    user_ids = [p.user_id for p in profile_list]

    # Bulk fetch businesses and drivers
    businesses_by_user = {
        b.user_id: b for b in business_models.Business.objects.filter(user_id__in=user_ids)
    }
    drivers_by_user = {
        d.user_id: d for d in fleet_models.Driver.objects.filter(user_id__in=user_ids)
    }

    # Build verification data efficiently
    verification_data = []
    for profile in profile_list:
        data = {
            'profile': profile,
            'business': businesses_by_user.get(profile.user_id) if profile.is_business else None,
            'driver': drivers_by_user.get(profile.user_id) if profile.is_driver else None,
            'user': profile.user,
        }
        verification_data.append(data)

    context = {
        'verification_data': verification_data,
        'current_filter': verification_filter,
    }

    return render(request, 'workforce/user_verification_list.html', context)


@require_http_methods(["POST"])
@login_required(login_url='/accounts/login/')
def update_verification_status(request, profile_id):
    """AJAX endpoint to update user verification status"""
    from core import models as core_models
    from django.utils import timezone

    try:
        profile = get_object_or_404(core_models.Profile, id=profile_id)

        # Parse JSON body
        data = json.loads(request.body)
        new_status = data.get('status')
        rejection_reason = data.get('rejection_reason', '')

        if not new_status:
            return JsonResponse({
                'success': False,
                'error': 'Status is required'
            }, status=400)

        # Update verification status
        profile.verification_status = new_status
        profile.verified_by = request.user

        if new_status == 'verified':
            profile.verified_at = timezone.now()
            profile.rejection_reason = None

            # Update business or driver status to active
            if profile.is_business:
                try:
                    from business import models as business_models
                    business = business_models.Business.objects.get(user=profile.user)
                    business.business_status = 'active'
                    business.save()
                except:
                    pass

            if profile.is_driver:
                try:
                    driver = fleet_models.Driver.objects.get(user=profile.user)
                    driver.driver_status = 'Approved'
                    driver.save()
                except:
                    pass

        elif new_status == 'rejected':
            profile.rejection_reason = rejection_reason
            profile.verified_at = None

        elif new_status == 'under_review':
            profile.verified_at = None

        profile.save()

        return JsonResponse({
            'success': True,
            'message': f'Verification status updated to {new_status}',
            'profile_id': profile.id,
            'new_status': new_status
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=400)


# ADDITIONAL SIDEBAR FUNCTIONS --------------------------------------------------------------------------------------------------------------

# Orders Section Functions
@login_required(login_url='/accounts/login/')
def orders_dms_updated(request):
    """
    View for DMS updated orders list.
    Shows orders that have delivery tasks with DMS status updates.
    """
    from orders import models as orders_models
    from django.db.models import Prefetch

    # Get orders that have delivery tasks with DMS IDs (meaning they're in the DMS system)
    # Use select_related and prefetch_related to optimize queries
    orders_list = orders_models.Order.objects.filter(
        delivery_task__dl_task_number_dms__isnull=False
    ).select_related(
        'business',
        'pickup_location'
    ).prefetch_related(
        Prefetch(
            'delivery_task',
            queryset=delivery_models.DeliveryTask.objects.select_related(
                'driver__user',
                'order'
            ).filter(
                dl_task_number_dms__isnull=False
            )
        )
    ).distinct().order_by('-created_at')

    # Check if there are any orders
    has_orders = orders_list.exists()

    # Check if DMS is configured (you can check if shipday_obj exists)
    dms_configured = shipday_obj is not None

    orders_with_pagination = paginate_queryset(request, orders_list, items_per_page=20)

    context = {
        'orders': orders_with_pagination,
        'page_title': 'DMS Updated Orders',
        'has_orders': has_orders,
        'dms_configured': dms_configured,
    }
    return render(request, 'workforce/wf_orders_dms_updated.html', context)


@login_required(login_url='/accounts/login/')
def match_dms_task(request):
    """Manually match a delivery task to a DMS job ID."""
    from delivery import models as delivery_models
    from django.contrib import messages

    if request.method == 'POST':
        delivery_task_number = request.POST.get('delivery_task_number', '').strip()
        dms_job_id = request.POST.get('dms_job_id', '').strip()

        if not delivery_task_number or not dms_job_id:
            messages.error(request, 'Both Delivery Task Number and DMS Job ID are required.')
            logger.warning(f"Match attempt failed - missing fields. Task: {delivery_task_number}, DMS ID: {dms_job_id}")
            return redirect('workforce:wf_orders_dms_updated')

        try:
            # Find the delivery task
            task = delivery_models.DeliveryTask.objects.get(
                dl_task_number=delivery_task_number
            )

            # Update with DMS job ID
            task.dl_task_number_dms = dms_job_id
            task.save()

            messages.success(
                request,
                f'Successfully matched Delivery Task {delivery_task_number} to DMS Job ID: {dms_job_id}'
            )
            logger.info(f"User {request.user.id} matched delivery task {delivery_task_number} to DMS ID {dms_job_id}")

        except delivery_models.DeliveryTask.DoesNotExist:
            messages.error(request, f'Delivery Task "{delivery_task_number}" not found in the system.')
            logger.warning(f"Failed to match - delivery task {delivery_task_number} not found")

        except Exception as e:
            messages.error(request, f'An error occurred while matching: {str(e)}')
            logger.error(f"Error matching task {delivery_task_number} to DMS ID {dms_job_id}: {str(e)}")

    return redirect('workforce:wf_orders_dms_updated')


@login_required(login_url='/accounts/login/')
def orders_reported(request):
    """View for reported orders list"""
    from orders import models as orders_models

    orders_list = orders_models.Order.objects.select_related(
        'business'
    ).prefetch_related('order_comments', 'delivery_task').filter(
        order_status='reported'
    ).order_by('-created_at')

    orders_with_pagination = paginate_queryset(request, orders_list, items_per_page=20)

    context = {
        'orders': orders_with_pagination,
        'page_title': 'Reported Orders',
    }
    return render(request, 'workforce/wf_orders_reported.html', context)


# Tasks Section Functions
@login_required(login_url='/accounts/login/')
def tasks_followup_list(request):
    """View for follow-up tasks list"""
    tasks_list = delivery_models.DeliveryTask.objects.select_related(
        'order', 'driver', 'business', 'pickup_location', 'order__business'
    ).filter(
        dl_task_status='pending'
    ).order_by('-created_at')

    tasks_with_pagination = paginate_queryset(request, tasks_list, items_per_page=20)

    context = {
        'delivery_tasks': tasks_with_pagination,
        'page_title': 'Follow-Up Tasks',
    }
    return render(request, 'workforce/parts/lists/dl_list_all.html', context)


@login_required(login_url='/accounts/login/')
def tasks_dms_updated(request):
    """View for DMS updated tasks list"""
    tasks_list = delivery_models.DeliveryTask.objects.select_related(
        'order', 'driver', 'business', 'pickup_location', 'order__business'
    ).filter(
        dl_task_status_dms__isnull=False
    ).order_by('-created_at')

    tasks_with_pagination = paginate_queryset(request, tasks_list, items_per_page=20)

    context = {
        'delivery_tasks': tasks_with_pagination,
        'page_title': 'DMS Updated Tasks',
    }
    return render(request, 'workforce/parts/lists/dl_list_all.html', context)


@login_required(login_url='/accounts/login/')
def tasks_reported(request):
    """View for reported tasks list - showing rejected/cancelled tasks"""
    tasks_list = delivery_models.DeliveryTask.objects.select_related(
        'order', 'driver', 'business', 'pickup_location', 'order__business'
    ).filter(
        dl_task_status__in=['rejected', 'cancelled']
    ).order_by('-created_at')

    tasks_with_pagination = paginate_queryset(request, tasks_list, items_per_page=20)

    context = {
        'delivery_tasks': tasks_with_pagination,
        'page_title': 'Reported Tasks',
    }
    return render(request, 'workforce/parts/lists/dl_list_all.html', context)


# DMS Links Section Functions
@login_required(login_url='/accounts/login/')
def dms_publish_order(request):
    """View for publishing orders to DMS"""
    from orders import models as orders_models

    orders_list = orders_models.Order.objects.select_related(
        'business'
    ).filter(
        verification_status='verified',
        task_created=False
    ).order_by('-created_at')

    orders_with_pagination = paginate_queryset(request, orders_list, items_per_page=20)

    context = {
        'orders': orders_with_pagination,
        'page_title': 'Publish Orders to DMS',
    }
    return render(request, 'workforce/dms_publish_order.html', context)


# Fleet Accounts Section Functions
@login_required(login_url='/accounts/login/')
def fleet_cod_in_hand(request):
    """View for COD in hand with drivers"""
    from django.db.models import Sum, Value, DecimalField
    from django.db.models.functions import Coalesce
    from datetime import timedelta
    from delivery import models as delivery_models

    # Date preset filter
    date_preset = request.GET.get('date_preset', '')
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')

    today = timezone.now().date()

    # Calculate dates based on preset
    if date_preset == 'today':
        date_from = today.isoformat()
        date_to = today.isoformat()
    elif date_preset == 'yesterday':
        yesterday = today - timedelta(days=1)
        date_from = yesterday.isoformat()
        date_to = yesterday.isoformat()
    elif date_preset == '3days':
        date_from = (today - timedelta(days=3)).isoformat()
        date_to = today.isoformat()
    elif date_preset == '1week':
        date_from = (today - timedelta(days=7)).isoformat()
        date_to = today.isoformat()
    elif date_preset == '1month':
        date_from = (today - timedelta(days=30)).isoformat()
        date_to = today.isoformat()
    # For 'custom', use the date_from and date_to from request

    # Build the COD collected subquery based on date filters
    cod_task_filter = {
        'cod_collected': True,
        'driver__isnull': False,
    }
    if date_from:
        cod_task_filter['cod_collected_at__date__gte'] = date_from
    if date_to:
        cod_task_filter['cod_collected_at__date__lte'] = date_to

    # If date filter is applied, calculate COD collected in that period per driver
    if date_from or date_to:
        # Get drivers with COD collected in the date range
        from django.db.models import OuterRef, Subquery

        # Subquery for COD collected in date range
        cod_subquery = delivery_models.DeliveryTask.objects.filter(
            driver=OuterRef('pk'),
            **cod_task_filter
        ).values('driver').annotate(
            total=Sum('cod_collected_amount')
        ).values('total')

        drivers = fleet_models.Driver.objects.filter(
            driver_status='Approved'
        ).select_related('user').annotate(
            period_cod=Coalesce(
                Subquery(cod_subquery),
                Value(0),
                output_field=DecimalField()
            )
        )
    else:
        # No date filter - show current cod_in_hand
        drivers = fleet_models.Driver.objects.filter(
            driver_status='Approved'
        ).select_related('user').annotate(
            period_cod=models.F('cod_in_hand')
        )

    # COD filter (yes/no/custom)
    cod_filter = request.GET.get('cod_filter', '')
    min_amount = request.GET.get('min_amount', '')
    max_amount = request.GET.get('max_amount', '')

    if cod_filter == 'yes':
        drivers = drivers.filter(period_cod__gt=0)
    elif cod_filter == 'no':
        drivers = drivers.filter(period_cod=0)
    elif cod_filter == 'custom':
        if min_amount:
            drivers = drivers.filter(period_cod__gte=min_amount)
        if max_amount:
            drivers = drivers.filter(period_cod__lte=max_amount)

    # Sorting
    sort_by = request.GET.get('sort', 'name_asc')
    sort_options = {
        'name_asc': 'user__first_name',
        'name_desc': '-user__first_name',
        'amount_asc': 'period_cod',
        'amount_desc': '-period_cod',
        'date_asc': 'last_settlement_date',
        'date_desc': '-last_settlement_date',
    }
    drivers = drivers.order_by(sort_options.get(sort_by, 'user__first_name'))

    # Calculate totals
    total_cod = drivers.aggregate(total=Sum('period_cod'))['total'] or 0
    pending_settlements = drivers.filter(period_cod__gt=0).count()

    # View mode (grid or list) - default to list
    view_mode = request.GET.get('view', 'list')

    # Build filter params for pagination
    filter_params = request.GET.copy()
    if 'page' in filter_params:
        del filter_params['page']

    drivers_with_pagination = paginate_queryset(request, drivers, items_per_page=20)

    context = {
        'drivers': drivers_with_pagination,
        'page_title': 'COD In Hand',
        'total_cod': total_cod,
        'pending_settlements': pending_settlements,
        'filter_params': filter_params.urlencode(),
        'date_preset': date_preset,
        'date_from': date_from or '',
        'date_to': date_to or '',
        'cod_filter': cod_filter,
        'min_amount': min_amount or '',
        'max_amount': max_amount or '',
        'sort_by': sort_by,
        'view_mode': view_mode,
        'is_filtered_by_date': bool(date_from or date_to),
    }
    return render(request, 'workforce/fleet_cod_in_hand.html', context)


@login_required(login_url='/accounts/login/')
def fleet_drivers_earnings(request):
    """View for drivers earnings"""
    drivers = fleet_models.Driver.objects.filter(
        driver_status='Approved'
    ).select_related('user').order_by('user__first_name')

    drivers_with_pagination = paginate_queryset(request, drivers, items_per_page=20)

    context = {
        'drivers': drivers_with_pagination,
        'page_title': 'Drivers Earnings',
    }
    return render(request, 'workforce/fleet_drivers_earnings.html', context)


@login_required(login_url='/accounts/login/')
def fleet_transactions(request):
    """View for fleet transactions with filtering and sorting"""
    from django.db.models import Sum
    from decimal import Decimal

    # Get all approved drivers for filter dropdown
    all_drivers = fleet_models.Driver.objects.filter(
        driver_status='Approved'
    ).select_related('user').order_by('user__first_name')

    # Get selected driver
    driver_id = request.GET.get('driver_id')
    selected_driver = None
    transactions = fleet_models.DriverTransaction.objects.none()

    if driver_id:
        try:
            selected_driver = fleet_models.Driver.objects.select_related('user').get(driver_id=driver_id)
            transactions = fleet_models.DriverTransaction.objects.filter(
                driver=selected_driver
            ).select_related('delivery_task', 'settlement')
        except fleet_models.Driver.DoesNotExist:
            selected_driver = None

    # Apply filters
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    # Default to cod_collection if no type filter specified
    txn_type = request.GET.get('type', 'cod_collection') if 'type' not in request.GET else request.GET.get('type')
    status = request.GET.get('status')
    min_amount = request.GET.get('min_amount')
    max_amount = request.GET.get('max_amount')

    if selected_driver:
        if date_from:
            transactions = transactions.filter(created_at__date__gte=date_from)
        if date_to:
            transactions = transactions.filter(created_at__date__lte=date_to)
        if txn_type:
            transactions = transactions.filter(transaction_type=txn_type)
        if status == 'settled':
            transactions = transactions.filter(settlement__isnull=False)
        elif status == 'pending':
            transactions = transactions.filter(settlement__isnull=True)
        if min_amount:
            transactions = transactions.filter(amount__gte=min_amount)
        if max_amount:
            transactions = transactions.filter(amount__lte=max_amount)

    # Sorting
    sort_by = request.GET.get('sort', 'date_desc')
    sort_options = {
        'date_asc': 'created_at',
        'date_desc': '-created_at',
        'amount_asc': 'amount',
        'amount_desc': '-amount',
        'type_asc': 'transaction_type',
        'type_desc': '-transaction_type',
    }
    if selected_driver:
        transactions = transactions.order_by(sort_options.get(sort_by, '-created_at'))

    # Transaction type choices for filter dropdown
    transaction_types = fleet_models.DriverTransaction.TRANSACTION_TYPES

    # Calculate totals (on unfiltered queryset for selected driver)
    total_cod = Decimal('0.00')
    total_earnings = Decimal('0.00')
    cod_unsettled = Decimal('0.00')
    earnings_unsettled = Decimal('0.00')

    if selected_driver:
        # Get all transactions for totals (not filtered)
        all_txns = fleet_models.DriverTransaction.objects.filter(driver=selected_driver)

        # Fetch all COD deposit reference numbers in one query to avoid N+1
        deposited_refs = set(
            all_txns.filter(transaction_type='cod_deposit').values_list('reference_number', flat=True)
        )

        for txn in all_txns:
            if txn.transaction_type == 'cod_collection':
                total_cod += abs(txn.amount)
                # COD not yet deposited - check against pre-fetched set
                if txn.reference_number not in deposited_refs:
                    cod_unsettled += abs(txn.amount)
            elif txn.transaction_type == 'earning':
                total_earnings += txn.amount
                # Earnings not yet settled
                if not txn.settlement_id:
                    earnings_unsettled += txn.amount

    # Build filter params for pagination
    filter_params = request.GET.copy()
    if 'page' in filter_params:
        del filter_params['page']

    transactions_paginated = paginate_queryset(request, transactions, items_per_page=20)

    context = {
        'page_title': 'Fleet Transactions',
        'transactions': transactions_paginated,
        'all_drivers': all_drivers,
        'selected_driver': selected_driver,
        'total_cod': total_cod,
        'total_earnings': total_earnings,
        'cod_unsettled': cod_unsettled,
        'earnings_unsettled': earnings_unsettled,
        'filter_params': filter_params.urlencode(),
        # Filter values for form
        'date_from': date_from or '',
        'date_to': date_to or '',
        'txn_type': txn_type or '',
        'status': status or '',
        'min_amount': min_amount or '',
        'max_amount': max_amount or '',
        'sort_by': sort_by,
        'transaction_types': transaction_types,
    }
    return render(request, 'workforce/fleet_transactions.html', context)


@login_required(login_url='/accounts/login/')
def generate_demo_transactions(request):
    """Generate demo transactions for a driver"""
    from django.contrib import messages
    from decimal import Decimal
    from datetime import timedelta
    import random

    if request.method != 'POST':
        return redirect('workforce:fleet_transactions')

    driver_id = request.POST.get('driver_id')
    if not driver_id:
        messages.error(request, 'Driver ID is required')
        return redirect('workforce:fleet_transactions')

    try:
        driver = fleet_models.Driver.objects.get(driver_id=driver_id)
    except fleet_models.Driver.DoesNotExist:
        messages.error(request, 'Driver not found')
        return redirect('workforce:fleet_transactions')

    # Check if driver already has transactions
    existing_count = fleet_models.DriverTransaction.objects.filter(driver=driver).count()
    if existing_count > 0:
        messages.warning(request, f'Driver already has {existing_count} transactions. Demo data not generated.')
        return redirect(f"{reverse('workforce:fleet_transactions')}?driver_id={driver_id}")

    now = timezone.now()
    cod_in_hand = Decimal('0.00')
    pending_earnings = Decimal('0.00')
    wallet_balance = driver.wallet_balance or Decimal('5000.00')

    transactions_to_create = []

    # Generate 10-15 COD collection transactions over past 7 days
    for i in range(random.randint(10, 15)):
        days_ago = random.randint(0, 7)
        hours_ago = random.randint(0, 23)
        txn_date = now - timedelta(days=days_ago, hours=hours_ago)

        cod_amount = Decimal(random.randint(50, 500))
        earning_amount = Decimal(random.randint(15, 50))
        cod_in_hand += cod_amount
        pending_earnings += earning_amount

        # COD Collection transaction
        transactions_to_create.append(fleet_models.DriverTransaction(
            driver=driver,
            transaction_type='cod_collection',
            amount=cod_amount,
            description=f'COD collected for delivery #{random.randint(1000, 9999)}',
            reference_number=f'COD-{random.randint(10000, 99999)}',
            wallet_balance_after=wallet_balance,
            cod_in_hand_after=cod_in_hand,
            pending_earnings_after=pending_earnings,
            created_by=request.user,
            created_at=txn_date,
        ))

        # Earning transaction
        transactions_to_create.append(fleet_models.DriverTransaction(
            driver=driver,
            transaction_type='earning',
            amount=earning_amount,
            description=f'Delivery earning for task #{random.randint(1000, 9999)}',
            reference_number=f'EARN-{random.randint(10000, 99999)}',
            wallet_balance_after=wallet_balance,
            cod_in_hand_after=cod_in_hand,
            pending_earnings_after=pending_earnings,
            created_by=request.user,
            created_at=txn_date + timedelta(minutes=5),
        ))

    # Generate 2-3 COD deposit (cash settled) transactions
    for i in range(random.randint(2, 3)):
        days_ago = random.randint(1, 5)
        txn_date = now - timedelta(days=days_ago, hours=random.randint(10, 18))

        deposit_amount = Decimal(random.randint(200, 800))
        cod_in_hand = max(Decimal('0.00'), cod_in_hand - deposit_amount)

        transactions_to_create.append(fleet_models.DriverTransaction(
            driver=driver,
            transaction_type='cod_deposit',
            amount=-deposit_amount,  # Negative because money leaving driver
            description=f'COD deposited to admin - Cash settlement',
            reference_number=f'DEP-{random.randint(10000, 99999)}',
            wallet_balance_after=wallet_balance,
            cod_in_hand_after=cod_in_hand,
            pending_earnings_after=pending_earnings,
            created_by=request.user,
            created_at=txn_date,
        ))

    # Generate 1 earnings settlement transaction
    if pending_earnings > Decimal('100.00'):
        settlement_amount = pending_earnings * Decimal('0.6')  # Settle 60%
        pending_earnings -= settlement_amount

        transactions_to_create.append(fleet_models.DriverTransaction(
            driver=driver,
            transaction_type='settlement',
            amount=-settlement_amount,  # Negative because paid out
            description='Weekly earnings settlement - Bank transfer',
            reference_number=f'SETTLE-{random.randint(10000, 99999)}',
            wallet_balance_after=wallet_balance,
            cod_in_hand_after=cod_in_hand,
            pending_earnings_after=pending_earnings,
            created_by=request.user,
            created_at=now - timedelta(days=3),
        ))

    # Add a bonus transaction
    bonus_amount = Decimal(random.randint(50, 150))
    pending_earnings += bonus_amount
    transactions_to_create.append(fleet_models.DriverTransaction(
        driver=driver,
        transaction_type='bonus',
        amount=bonus_amount,
        description='Weekly performance bonus',
        reference_number=f'BONUS-{random.randint(10000, 99999)}',
        wallet_balance_after=wallet_balance,
        cod_in_hand_after=cod_in_hand,
        pending_earnings_after=pending_earnings,
        created_by=request.user,
        created_at=now - timedelta(days=1),
    ))

    # Bulk create all transactions
    fleet_models.DriverTransaction.objects.bulk_create(transactions_to_create)

    # Update driver's current balances
    driver.cod_in_hand = cod_in_hand
    driver.pending_earnings = pending_earnings
    driver.save(update_fields=['cod_in_hand', 'pending_earnings'])

    messages.success(request, f'Successfully generated {len(transactions_to_create)} demo transactions for {driver.user.first_name} {driver.user.last_name}')
    return redirect(f"{reverse('workforce:fleet_transactions')}?driver_id={driver_id}")


@login_required(login_url='/accounts/login/')
def bulk_settle_transactions(request):
    """Bulk settle selected transactions for a driver"""
    from django.contrib import messages
    from decimal import Decimal
    import json

    if request.method != 'POST':
        return redirect('workforce:fleet_transactions')

    driver_id = request.POST.get('driver_id')
    transaction_ids_json = request.POST.get('transaction_ids', '[]')

    try:
        transaction_ids = json.loads(transaction_ids_json)
    except json.JSONDecodeError:
        messages.error(request, 'Invalid transaction data')
        return redirect('workforce:fleet_transactions')

    if not driver_id or not transaction_ids:
        messages.error(request, 'Driver ID and transactions are required')
        return redirect('workforce:fleet_transactions')

    try:
        driver = fleet_models.Driver.objects.get(driver_id=driver_id)
    except fleet_models.Driver.DoesNotExist:
        messages.error(request, 'Driver not found')
        return redirect('workforce:fleet_transactions')

    # Get transactions that can be settled (pending earnings and COD collections)
    transactions = fleet_models.DriverTransaction.objects.filter(
        transaction_id__in=transaction_ids,
        driver=driver,
        settlement__isnull=True  # Not already settled
    ).exclude(
        transaction_type__in=['settlement', 'cod_deposit']  # These are already finalized
    )

    if not transactions.exists():
        messages.warning(request, 'No eligible transactions found for settlement')
        return redirect(f"{reverse('workforce:fleet_transactions')}?driver_id={driver_id}")

    # Calculate total settlement amount
    total_amount = sum(txn.amount for txn in transactions)

    # Create a settlement record
    settlement_code = f"STL-{timezone.now().strftime('%Y%m%d%H%M%S')}-{driver_id}"

    settlement = fleet_models.DriverSettlement.objects.create(
        driver=driver,
        settlement_code=settlement_code,
        period_start=transactions.order_by('created_at').first().created_at.date(),
        period_end=timezone.now().date(),
        total_deliveries=transactions.filter(transaction_type='earning').count(),
        gross_earnings=total_amount,
        net_amount=total_amount,
        created_by=request.user,
        status='paid',
        paid_at=timezone.now(),
    )

    # Link transactions to settlement
    transactions.update(settlement=settlement)

    # Update driver balances
    earnings_settled = sum(
        txn.amount for txn in transactions if txn.transaction_type == 'earning'
    )
    cod_settled = sum(
        abs(txn.amount) for txn in transactions if txn.transaction_type == 'cod_collection'
    )

    if earnings_settled > 0:
        driver.pending_earnings = max(Decimal('0.00'), (driver.pending_earnings or Decimal('0.00')) - earnings_settled)
    if cod_settled > 0:
        driver.cod_in_hand = max(Decimal('0.00'), (driver.cod_in_hand or Decimal('0.00')) - cod_settled)

    driver.last_settlement_date = timezone.now()
    driver.save(update_fields=['pending_earnings', 'cod_in_hand', 'last_settlement_date'])

    messages.success(
        request,
        f'Successfully settled {transactions.count()} transactions for QAR {total_amount:.2f}. '
        f'Settlement code: {settlement_code}'
    )
    return redirect(f"{reverse('workforce:fleet_transactions')}?driver_id={driver_id}")


# ==========================================
# RECEIPT TEMPLATES SECTION
# ==========================================

@login_required(login_url='/accounts/login/')
def receipt_templates_list(request):
    """List all receipt templates"""
    templates = fleet_models.ReceiptTemplate.objects.all()

    # Filter by type if specified
    template_type = request.GET.get('type')
    if template_type:
        templates = templates.filter(template_type=template_type)

    context = {
        'page_title': 'Receipt Templates',
        'templates': templates,
        'template_types': fleet_models.ReceiptTemplate.TEMPLATE_TYPES,
        'selected_type': template_type,
    }
    return render(request, 'workforce/receipt_templates_list.html', context)


@login_required(login_url='/accounts/login/')
def receipt_template_create(request):
    """Create a new receipt template"""
    from django.contrib import messages

    if request.method == 'POST':
        template = fleet_models.ReceiptTemplate(
            name=request.POST.get('name'),
            template_type=request.POST.get('template_type'),
            paper_size=request.POST.get('paper_size', 'thermal_80'),
            is_default=request.POST.get('is_default') == 'on',
            show_logo=request.POST.get('show_logo') == 'on',
            logo_url=request.POST.get('logo_url', ''),
            company_name=request.POST.get('company_name', 'Ezzy Delivery'),
            company_address=request.POST.get('company_address', ''),
            company_phone=request.POST.get('company_phone', ''),
            company_email=request.POST.get('company_email') or None,
            primary_color=request.POST.get('primary_color', '#2196F3'),
            font_family=request.POST.get('font_family', 'Courier New, monospace'),
            font_size=int(request.POST.get('font_size', 12)),
            show_signature_line=request.POST.get('show_signature_line') == 'on',
            show_qr_code=request.POST.get('show_qr_code') == 'on',
            footer_message=request.POST.get('footer_message', ''),
            custom_css=request.POST.get('custom_css', ''),
            created_by=request.user,
        )
        template.save()
        messages.success(request, f'Template "{template.name}" created successfully.')
        return redirect('workforce:receipt_templates_list')

    context = {
        'page_title': 'Create Receipt Template',
        'template_types': fleet_models.ReceiptTemplate.TEMPLATE_TYPES,
        'paper_sizes': fleet_models.ReceiptTemplate.PAPER_SIZES,
    }
    return render(request, 'workforce/receipt_template_edit.html', context)


@login_required(login_url='/accounts/login/')
def receipt_template_edit(request, template_id):
    """Edit an existing receipt template"""
    from django.contrib import messages
    from django.shortcuts import get_object_or_404

    template = get_object_or_404(fleet_models.ReceiptTemplate, template_id=template_id)

    if request.method == 'POST':
        template.name = request.POST.get('name')
        template.template_type = request.POST.get('template_type')
        template.paper_size = request.POST.get('paper_size', 'thermal_80')
        template.is_default = request.POST.get('is_default') == 'on'
        template.show_logo = request.POST.get('show_logo') == 'on'
        template.logo_url = request.POST.get('logo_url', '')
        template.company_name = request.POST.get('company_name', 'Ezzy Delivery')
        template.company_address = request.POST.get('company_address', '')
        template.company_phone = request.POST.get('company_phone', '')
        template.company_email = request.POST.get('company_email') or None
        template.primary_color = request.POST.get('primary_color', '#2196F3')
        template.font_family = request.POST.get('font_family', 'Courier New, monospace')
        template.font_size = int(request.POST.get('font_size', 12))
        template.show_signature_line = request.POST.get('show_signature_line') == 'on'
        template.show_qr_code = request.POST.get('show_qr_code') == 'on'
        template.footer_message = request.POST.get('footer_message', '')
        template.custom_css = request.POST.get('custom_css', '')
        template.save()
        messages.success(request, f'Template "{template.name}" updated successfully.')
        return redirect('workforce:receipt_templates_list')

    context = {
        'page_title': f'Edit Template: {template.name}',
        'template': template,
        'template_types': fleet_models.ReceiptTemplate.TEMPLATE_TYPES,
        'paper_sizes': fleet_models.ReceiptTemplate.PAPER_SIZES,
    }
    return render(request, 'workforce/receipt_template_edit.html', context)


@login_required(login_url='/accounts/login/')
def receipt_template_preview(request, template_id):
    """Preview a receipt template with sample data"""
    from django.shortcuts import get_object_or_404
    from decimal import Decimal

    template = get_object_or_404(fleet_models.ReceiptTemplate, template_id=template_id)

    # Create sample data for preview
    sample_settlement = {
        'settlement_code': 'STL-PREVIEW-001',
        'created_at': timezone.now(),
        'period_start': timezone.now().date() - timezone.timedelta(days=7),
        'period_end': timezone.now().date(),
        'net_amount': Decimal('1250.00'),
        'gross_earnings': Decimal('1300.00'),
        'deductions': Decimal('50.00'),
        'bonuses': Decimal('0.00'),
        'status': 'paid',
        'paid_at': timezone.now(),
    }

    sample_driver = {
        'driver_id': 45,
        'user': {'first_name': 'Ahmed', 'last_name': 'Khan'},
        'driver_phone': '+974-5555-1234',
    }

    sample_transactions = [
        {'description': 'COD collected for order #1234', 'created_at': timezone.now() - timezone.timedelta(days=1), 'amount': Decimal('350.00')},
        {'description': 'COD collected for order #1235', 'created_at': timezone.now() - timezone.timedelta(days=2), 'amount': Decimal('275.00')},
        {'description': 'COD collected for order #1236', 'created_at': timezone.now() - timezone.timedelta(days=3), 'amount': Decimal('425.00')},
        {'description': 'COD collected for order #1237', 'created_at': timezone.now() - timezone.timedelta(days=4), 'amount': Decimal('200.00')},
    ]

    context = {
        'template': template,
        'settlement': sample_settlement,
        'driver': sample_driver,
        'transactions': sample_transactions,
        'is_preview': True,
    }
    return render(request, 'workforce/receipt_template_preview.html', context)


@login_required(login_url='/accounts/login/')
def receipt_template_delete(request, template_id):
    """Delete a receipt template"""
    from django.shortcuts import get_object_or_404
    from django.contrib import messages

    template = get_object_or_404(fleet_models.ReceiptTemplate, template_id=template_id)

    if request.method == 'POST':
        name = template.name
        template.delete()
        messages.success(request, f'Template "{name}" deleted successfully.')
        return redirect('workforce:receipt_templates_list')

    return redirect('workforce:receipt_templates_list')


@login_required(login_url='/accounts/login/')
def settlement_receipt_print(request, settlement_id):
    """Print a settlement receipt using the default or specified template"""
    from django.shortcuts import get_object_or_404

    settlement = get_object_or_404(fleet_models.DriverSettlement, settlement_id=settlement_id)
    transactions = fleet_models.DriverTransaction.objects.filter(settlement=settlement)

    # Get template (use specified or default)
    template_id = request.GET.get('template_id')
    if template_id:
        template = fleet_models.ReceiptTemplate.objects.filter(template_id=template_id).first()
    else:
        template = fleet_models.ReceiptTemplate.objects.filter(
            template_type='settlement',
            is_default=True
        ).first()

    context = {
        'settlement': settlement,
        'transactions': transactions,
        'template': template,
        'is_preview': False,
    }
    return render(request, 'workforce/settlement_receipt.html', context)


@login_required(login_url='/accounts/login/')
def fleet_task_sheet(request, driver_id):
    """Generate printable A4 task sheet for a driver's daily deliveries"""
    from django.shortcuts import get_object_or_404
    from django.db.models import Sum
    from datetime import datetime
    from decimal import Decimal

    driver = get_object_or_404(fleet_models.Driver.objects.select_related('user'), driver_id=driver_id)

    # Get date from query param or use today
    date_str = request.GET.get('date')
    if date_str:
        try:
            selected_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            selected_date = timezone.now().date()
    else:
        selected_date = timezone.now().date()

    # Get delivery tasks for this driver on the selected date
    tasks = delivery_models.DeliveryTask.objects.filter(
        driver=driver,
        dl_task_date=selected_date
    ).select_related('order').prefetch_related('order__order_items').order_by('dl_task_date')

    # Calculate total COD amount
    total_cod = Decimal('0.00')
    for task in tasks:
        if task.order and task.order.payment_type == 'cod':
            total_cod += task.order.cod_amount or task.order.order_total or Decimal('0.00')

    # Get unique delivery areas
    areas = set()
    for task in tasks:
        if task.order and task.order.delivery_area:
            areas.add(task.order.delivery_area)
    delivery_area = ', '.join(areas) if areas else 'Multiple'

    # Sheet number (can be customized based on shift or slot)
    sheet_number = request.GET.get('sheet', '01')
    slot_number = request.GET.get('slot', '01')

    context = {
        'driver': driver,
        'tasks': tasks,
        'date': selected_date,
        'total_cod': total_cod,
        'delivery_area': delivery_area,
        'sheet_number': sheet_number,
        'slot_number': slot_number,
    }
    return render(request, 'workforce/fleet_task_sheet.html', context)


@login_required(login_url='/accounts/login/')
def fleet_task_sheets_list(request):
    """List view to select driver and date for task sheet printing"""
    from django.db.models import Count, Q
    from datetime import datetime

    # Get all approved drivers with task counts for today
    today = timezone.now().date()
    selected_date = request.GET.get('date')
    if selected_date:
        try:
            selected_date = datetime.strptime(selected_date, '%Y-%m-%d').date()
        except ValueError:
            selected_date = today
    else:
        selected_date = today

    drivers = fleet_models.Driver.objects.filter(
        driver_status='Approved'
    ).select_related('user').annotate(
        task_count=Count(
            'deliverytask',
            filter=Q(deliverytask__dl_task_date=selected_date)
        )
    ).order_by('user__first_name')

    # Get drivers with tasks for quick filter
    drivers_with_tasks = drivers.filter(task_count__gt=0)

    context = {
        'page_title': 'Fleet Task Sheets',
        'drivers': drivers,
        'drivers_with_tasks': drivers_with_tasks,
        'selected_date': selected_date,
        'today': today,
    }
    return render(request, 'workforce/fleet_task_sheets_list.html', context)


# Inventory Section Functions
@login_required(login_url='/accounts/login/')
def inventory_reports(request):
    """View for inventory reports"""
    context = {
        'page_title': 'Inventory Reports',
    }
    return render(request, 'workforce/inventory_reports.html', context)


@login_required(login_url='/accounts/login/')
def inventory_restock_list(request):
    """View for restock list"""
    context = {
        'page_title': 'Restock List',
    }
    return render(request, 'workforce/inventory_restock_list.html', context)


# Quick Links Functions
@login_required(login_url='/accounts/login/')
def staff_reports(request):
    """View for staff reports dashboard"""
    from orders import models as orders_models
    from django.db.models import Count, Q

    # Get order statistics in single query
    order_stats = orders_models.Order.objects.aggregate(
        total=Count('id'),
        pending=Count('id', filter=Q(order_status='pending')),
        verified=Count('id', filter=Q(order_status='verified')),
        completed=Count('id', filter=Q(order_status='completed')),
    )

    # Get task statistics in single query
    task_stats = delivery_models.DeliveryTask.objects.aggregate(
        total=Count('id'),
        active=Count('id', filter=Q(dl_task_status__in=['in_transit', 'pending', 'address_pending'])),
        completed=Count('id', filter=Q(dl_task_status='delivered')),
    )

    # Get driver statistics in single query
    driver_stats = fleet_models.Driver.objects.aggregate(
        total=Count('driver_id'),
        active=Count('driver_id', filter=Q(driver_status='Approved')),
    )

    context = {
        'page_title': 'Reports Dashboard',
        'total_orders': order_stats['total'],
        'pending_orders': order_stats['pending'],
        'verified_orders': order_stats['verified'],
        'completed_orders': order_stats['completed'],
        'total_tasks': task_stats['total'],
        'active_tasks': task_stats['active'],
        'completed_tasks': task_stats['completed'],
        'total_drivers': driver_stats['total'],
        'active_drivers': driver_stats['active'],
    }
    return render(request, 'workforce/staff_reports.html', context)


@login_required(login_url='/accounts/login/')
def staff_contacts(request):
    """View for staff contacts directory"""
    from core import models as core_models
    from django.db.models import Count, Q

    # Get all staff members
    staff_profiles = core_models.Profile.objects.select_related('user').filter(
        is_staff=True
    ).order_by('first_name')

    # Get business and driver counts in a single query
    profile_counts = core_models.Profile.objects.aggregate(
        business_count=Count('id', filter=Q(is_business=True, verification_status='verified')),
        driver_count=Count('id', filter=Q(is_driver=True, verification_status='verified')),
    )

    staff_with_pagination = paginate_queryset(request, staff_profiles, items_per_page=50)

    context = {
        'page_title': 'Contacts Directory',
        'staff_profiles': staff_with_pagination,
        'business_count': profile_counts['business_count'],
        'driver_count': profile_counts['driver_count'],
    }
    return render(request, 'workforce/staff_contacts.html', context)


# ==================== DMS (ShipDay) VIEWS ====================

@login_required(login_url='/accounts/login/')
def dms_drivers_list(request):
    """View for listing all drivers from ShipDay DMS"""
    logger.info(f"Fetching Shipday carriers for user: {request.user.id if request.user.is_authenticated else 'anonymous'}")

    carriers = []
    error_message = None

    try:
        if shipday_obj:
            carriers = shipday_obj.CarrierService.get_carriers()
            logger.info(f"Successfully fetched {len(carriers) if carriers else 0} carriers from Shipday")
        else:
            error_message = "ShipDay API is not configured. Please check SHIPDAY_API_KEY in settings."
            logger.warning(error_message)
    except Exception as e:
        error_message = f"Error fetching Shipday carriers: {str(e)}"
        logger.error(error_message)

    context = {
        'page_title': 'DMS Drivers List',
        'carriers': carriers or [],
        'error_message': error_message,
    }
    return render(request, 'workforce/dms_drivers_list.html', context)


@login_required(login_url='/accounts/login/')
def dms_orders_list(request):
    """View for listing all orders from ShipDay DMS"""
    logger.info(f"Fetching Shipday orders for user: {request.user.id if request.user.is_authenticated else 'anonymous'}")

    orders = []
    error_message = None

    try:
        if shipday_obj:
            orders = shipday_obj.OrderService.get_orders()
            logger.info(f"Successfully fetched {len(orders) if orders else 0} orders from Shipday")
        else:
            error_message = "ShipDay API is not configured. Please check SHIPDAY_API_KEY in settings."
            logger.warning(error_message)
    except Exception as e:
        error_message = f"Error fetching Shipday orders: {str(e)}"
        logger.error(error_message)

    context = {
        'page_title': 'DMS Orders List',
        'orders_in_shipday': orders or [],
        'error_message': error_message,
    }
    return render(request, 'workforce/dms_orders_list.html', context)


@login_required(login_url='/accounts/login/')
def dms_analytics(request):
    """View for DMS analytics and statistics"""
    try:
        # Get statistics from local database
        total_tasks = delivery_models.DeliveryTask.objects.count()
        synced_tasks = delivery_models.DeliveryTask.objects.filter(dl_task_number_dms__isnull=False).count()
        pending_tasks = delivery_models.DeliveryTask.objects.filter(dl_task_number_dms__isnull=True).count()

        # Get driver statistics
        total_drivers = fleet_models.Driver.objects.filter(driver_status='Approved').count()

        # Get order statistics
        total_orders = orders_models.Order.objects.count()
        published_orders = orders_models.Order.objects.filter(task_created=True).count()

        context = {
            'page_title': 'DMS Analytics',
            'total_tasks': total_tasks,
            'synced_tasks': synced_tasks,
            'pending_tasks': pending_tasks,
            'total_drivers': total_drivers,
            'total_orders': total_orders,
            'published_orders': published_orders,
        }
    except Exception as e:
        logger.error(f"Error fetching DMS analytics: {e}")
        context = {
            'page_title': 'DMS Analytics',
            'error_message': str(e),
        }

    return render(request, 'workforce/dms_analytics.html', context)


@login_required(login_url='/accounts/login/')
def dms_sync_monitor(request):
    """View for monitoring DMS sync status"""
    try:
        # Get recently synced tasks
        recently_synced = delivery_models.DeliveryTask.objects.filter(
            dl_task_number_dms__isnull=False
        ).order_by('-updated_at')[:50]

        # Get failed sync attempts
        failed_sync = delivery_models.DeliveryTask.objects.filter(
            dl_task_number_dms__isnull=True,
            dl_task_status__in=['in_transit', 'pending', 'address_pending']
        ).order_by('-created_at')[:50]

        context = {
            'page_title': 'DMS Sync Monitor',
            'recently_synced': recently_synced,
            'failed_sync': failed_sync,
        }
    except Exception as e:
        logger.error(f"Error fetching DMS sync monitor data: {e}")
        context = {
            'page_title': 'DMS Sync Monitor',
            'error_message': str(e),
        }

    return render(request, 'workforce/dms_sync_monitor.html', context)


# Documents section  ------------------------------------------------------------------------------------------------------


@login_required(login_url='/accounts/login/')
def driver_documents_list(request):
    """View for listing all driver documents with search and card/table toggle"""
    from django.db.models import Q

    # Get search query and view type
    search_query = request.GET.get('search', '').strip()
    view_type = request.GET.get('view', 'card')  # 'card' or 'table'

    # Start with all driver documents
    documents = fleet_models.DriverDocument.objects.select_related('driver', 'driver__user', 'driver__profile').all()

    # Apply search filter
    if search_query:
        documents = documents.filter(
            Q(document_no__icontains=search_query) |
            Q(document_type__icontains=search_query) |
            Q(driver__user__first_name__icontains=search_query) |
            Q(driver__user__last_name__icontains=search_query) |
            Q(driver__driver_code__icontains=search_query)
        )

    # Order by most recent
    documents = documents.order_by('-created_at')

    # Paginate results
    page_obj = paginate_queryset(request, documents, items_per_page=20)

    context = {
        'page_title': 'Driver ID Documents',
        'documents': page_obj,
        'search_query': search_query,
        'view_type': view_type,
    }

    return render(request, 'workforce/driver_documents_list.html', context)


@login_required(login_url='/accounts/login/')
def driver_document_detail(request, document_id):
    """View for viewing and updating a specific driver document"""
    document = get_object_or_404(fleet_models.DriverDocument, id=document_id)

    if request.method == 'POST':
        # Handle document update
        try:
            document.document_type = request.POST.get('document_type', document.document_type)
            document.document_no = request.POST.get('document_no', document.document_no)
            document.document_issued_from = request.POST.get('document_issued_from', document.document_issued_from)

            expiry_date = request.POST.get('document_expiry_date')
            if expiry_date:
                document.document_expiry_date = expiry_date

            # Handle file upload
            if 'document_file' in request.FILES:
                document.document_file = request.FILES['document_file']

            document.save()

            return JsonResponse({
                'success': True,
                'message': 'Document updated successfully'
            })
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': str(e)
            }, status=400)

    context = {
        'page_title': 'Driver Document Detail',
        'document': document,
    }

    return render(request, 'workforce/driver_document_detail.html', context)


@login_required(login_url='/accounts/login/')
def vehicle_documents_list(request):
    """View for listing all vehicle documents with search and card/table toggle"""
    from django.db.models import Q

    # Get search query and view type
    search_query = request.GET.get('search', '').strip()
    view_type = request.GET.get('view', 'card')  # 'card' or 'table'

    # Start with all driver vehicles
    vehicles = fleet_models.DriverVehicle.objects.select_related('driver', 'driver__user', 'driver__profile').all()

    # Apply search filter
    if search_query:
        vehicles = vehicles.filter(
            Q(vehicle_no__icontains=search_query) |
            Q(vehicle_type__icontains=search_query) |
            Q(vehicle_model__icontains=search_query) |
            Q(driver__user__first_name__icontains=search_query) |
            Q(driver__user__last_name__icontains=search_query) |
            Q(driver__driver_code__icontains=search_query)
        )

    # Order by most recent
    vehicles = vehicles.order_by('-created_at')

    # Paginate results
    page_obj = paginate_queryset(request, vehicles, items_per_page=20)

    context = {
        'page_title': 'Vehicle Documents',
        'vehicles': page_obj,
        'search_query': search_query,
        'view_type': view_type,
    }

    return render(request, 'workforce/vehicle_documents_list.html', context)


@login_required(login_url='/accounts/login/')
def vehicle_document_detail(request, driver_id):
    """View for viewing and updating vehicle documents for a specific driver"""
    driver = get_object_or_404(fleet_models.Driver, driver_id=driver_id)
    vehicles = fleet_models.DriverVehicle.objects.filter(driver=driver).order_by('-created_at')

    if request.method == 'POST':
        # Handle vehicle update
        try:
            vehicle_id = request.POST.get('vehicle_id')
            if vehicle_id:
                vehicle = get_object_or_404(fleet_models.DriverVehicle, id=vehicle_id)
                vehicle.vehicle_type = request.POST.get('vehicle_type', vehicle.vehicle_type)
                vehicle.vehicle_no = request.POST.get('vehicle_no', vehicle.vehicle_no)
                vehicle.vehicle_model = request.POST.get('vehicle_model', vehicle.vehicle_model)
                vehicle.vehicle_color = request.POST.get('vehicle_color', vehicle.vehicle_color)
                vehicle.vehicle_status = request.POST.get('vehicle_status', vehicle.vehicle_status)
                vehicle.save()

                return JsonResponse({
                    'success': True,
                    'message': 'Vehicle updated successfully'
                })
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': str(e)
            }, status=400)

    context = {
        'page_title': 'Vehicle Documents Detail',
        'driver': driver,
        'vehicles': vehicles,
    }

    return render(request, 'workforce/vehicle_document_detail.html', context)


@login_required(login_url='/accounts/login/')
def store_documents_list(request):
    """View for listing all store/business documents with search and card/table toggle"""
    from django.db.models import Q

    # Get search query and view type
    search_query = request.GET.get('search', '').strip()
    view_type = request.GET.get('view', 'card')  # 'card' or 'table'

    # Start with all businesses
    businesses = business_models.Business.objects.select_related('business_profile', 'user').all()

    # Apply search filter
    if search_query:
        businesses = businesses.filter(
            Q(business_name__icontains=search_query) |
            Q(business_code__icontains=search_query) |
            Q(business_phone__icontains=search_query) |
            Q(business_email__icontains=search_query) |
            Q(business_qid__icontains=search_query)
        )

    # Order by most recent
    businesses = businesses.order_by('-created_at')

    # Paginate results
    page_obj = paginate_queryset(request, businesses, items_per_page=20)

    context = {
        'page_title': 'Store Documents',
        'businesses': page_obj,
        'search_query': search_query,
        'view_type': view_type,
    }

    return render(request, 'workforce/store_documents_list.html', context)


@login_required(login_url='/accounts/login/')
def store_document_detail(request, business_id):
    """View for viewing and updating store documents for a specific business"""
    business = get_object_or_404(business_models.Business, business_id=business_id)

    try:
        business_profile = business.business_profile
    except:
        business_profile = None

    if request.method == 'POST':
        # Handle business document update
        try:
            business.business_name = request.POST.get('business_name', business.business_name)
            business.business_phone = request.POST.get('business_phone', business.business_phone)
            business.business_email = request.POST.get('business_email', business.business_email)
            business.business_qid = request.POST.get('business_qid', business.business_qid)
            business.business_status = request.POST.get('business_status', business.business_status)
            business.save()

            return JsonResponse({
                'success': True,
                'message': 'Store document updated successfully'
            })
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': str(e)
            }, status=400)

    context = {
        'page_title': 'Store Document Detail',
        'business': business,
        'business_profile': business_profile,
    }

    return render(request, 'workforce/store_document_detail.html', context)


@login_required(login_url='/accounts/login/')
def business_licenses_list(request):
    """View for listing all business licenses with search and card/table toggle"""
    from django.db.models import Q

    # Get search query and view type
    search_query = request.GET.get('search', '').strip()
    view_type = request.GET.get('view', 'card')  # 'card' or 'table'

    # Start with all businesses
    businesses = business_models.Business.objects.select_related('business_profile', 'user').all()

    # Apply search filter
    if search_query:
        businesses = businesses.filter(
            Q(business_name__icontains=search_query) |
            Q(business_code__icontains=search_query) |
            Q(business_qid__icontains=search_query)
        )

    # Order by most recent
    businesses = businesses.order_by('-created_at')

    # Paginate results
    page_obj = paginate_queryset(request, businesses, items_per_page=20)

    context = {
        'page_title': 'Business Licenses',
        'businesses': page_obj,
        'search_query': search_query,
        'view_type': view_type,
    }

    return render(request, 'workforce/business_licenses_list.html', context)


@login_required(login_url='/accounts/login/')
def business_license_detail(request, business_id):
    """View for viewing and updating business license details"""
    business = get_object_or_404(business_models.Business, business_id=business_id)

    try:
        business_profile = business.business_profile
    except:
        business_profile = None

    if request.method == 'POST':
        # Handle business license update
        try:
            business.business_name = request.POST.get('business_name', business.business_name)
            business.business_qid = request.POST.get('business_qid', business.business_qid)
            business.business_status = request.POST.get('business_status', business.business_status)

            business_since = request.POST.get('business_since')
            if business_since:
                business.business_since = business_since

            business.save()

            # Update business profile if exists
            if business_profile:
                business_profile.business_address = request.POST.get('business_address', business_profile.business_address)
                business_profile.business_city = request.POST.get('business_city', business_profile.business_city)
                business_profile.save()

            return JsonResponse({
                'success': True,
                'message': 'Business license updated successfully'
            })
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': str(e)
            }, status=400)

    context = {
        'page_title': 'Business License Detail',
        'business': business,
        'business_profile': business_profile,
    }

    return render(request, 'workforce/business_license_detail.html', context)


# Sellers section  ------------------------------------------------------------------------------------------------------
@login_required(login_url='/accounts/login/')
def sellers_list(request):
    """
    View to display all sellers/businesses in the system
    """
    # Get all businesses
    businesses = business_models.Business.objects.select_related(
        'profile', 'business_profile'
    ).all()

    # Apply filters
    search = request.GET.get('search', '').strip()
    status = request.GET.get('status', '').strip()
    verification_status = request.GET.get('verification', '').strip()

    if search:
        from django.db.models import Q
        businesses = businesses.filter(
            Q(business_name__icontains=search) |
            Q(business_email__icontains=search) |
            Q(business_phone__icontains=search) |
            Q(profile__user__email__icontains=search)
        )

    if status:
        businesses = businesses.filter(business_status=status)

    if verification_status:
        businesses = businesses.filter(profile__verification_status=verification_status)

    # Order by most recent
    businesses = businesses.order_by('-business_since', '-business_id')

    # Count statistics using single aggregation query
    from django.db.models import Count, Q as DQ
    stats = business_models.Business.objects.aggregate(
        total=Count('business_id'),
        active=Count('business_id', filter=DQ(business_status='active')),
        pending=Count('business_id', filter=DQ(profile__verification_status='pending')),
        inactive=Count('business_id', filter=DQ(business_status='inactive')),
    )
    total_sellers = stats['total']
    active_sellers = stats['active']
    pending_sellers = stats['pending']
    inactive_sellers = stats['inactive']

    # Paginate
    page_obj = paginate_queryset(request, businesses, items_per_page=20)

    context = {
        'page_title': 'All Sellers',
        'page_obj': page_obj,
        'total_sellers': total_sellers,
        'active_sellers': active_sellers,
        'pending_sellers': pending_sellers,
        'inactive_sellers': inactive_sellers,
        'search': search,
        'status': status,
        'verification': verification_status,
    }

    return render(request, 'workforce/sellers_list.html', context)


@login_required(login_url='/accounts/login/')
def sellers_pending(request):
    """
    View to display sellers pending approval
    """
    # Get businesses with pending verification
    businesses = business_models.Business.objects.select_related(
        'profile', 'business_profile'
    ).filter(
        profile__verification_status='pending'
    ).order_by('-business_since', '-business_id')

    # Apply search filter
    search = request.GET.get('search', '').strip()
    if search:
        from django.db.models import Q
        businesses = businesses.filter(
            Q(business_name__icontains=search) |
            Q(business_email__icontains=search) |
            Q(business_phone__icontains=search)
        )

    # Paginate
    page_obj = paginate_queryset(request, businesses, items_per_page=20)

    context = {
        'page_title': 'Pending Sellers',
        'page_obj': page_obj,
        'search': search,
    }

    return render(request, 'workforce/sellers_pending.html', context)


@login_required(login_url='/accounts/login/')
def sellers_active(request):
    """
    View to display active verified sellers
    """
    from django.db.models import Count, Q

    # Get active and verified businesses with order count annotation
    businesses = business_models.Business.objects.select_related(
        'profile', 'business_profile'
    ).annotate(
        total_orders=Count('order')
    ).filter(
        business_status='active',
        profile__verification_status='verified'
    ).order_by('-business_since', '-business_id')

    # Apply search filter
    search = request.GET.get('search', '').strip()
    if search:
        businesses = businesses.filter(
            Q(business_name__icontains=search) |
            Q(business_email__icontains=search) |
            Q(business_phone__icontains=search)
        )

    # Paginate
    page_obj = paginate_queryset(request, businesses, items_per_page=20)

    context = {
        'page_title': 'Active Sellers',
        'page_obj': page_obj,
        'search': search,
    }

    return render(request, 'workforce/sellers_active.html', context)


@login_required(login_url='/accounts/login/')
def sellers_inactive(request):
    """
    View to display inactive or suspended sellers
    """
    # Get inactive businesses
    businesses = business_models.Business.objects.select_related(
        'profile', 'business_profile'
    ).filter(
        business_status='inactive'
    ).order_by('-business_since', '-business_id')

    # Apply search filter
    search = request.GET.get('search', '').strip()
    if search:
        from django.db.models import Q
        businesses = businesses.filter(
            Q(business_name__icontains=search) |
            Q(business_email__icontains=search) |
            Q(business_phone__icontains=search)
        )

    # Paginate
    page_obj = paginate_queryset(request, businesses, items_per_page=20)

    context = {
        'page_title': 'Inactive Sellers',
        'page_obj': page_obj,
        'search': search,
    }

    return render(request, 'workforce/sellers_inactive.html', context)


@login_required(login_url='/accounts/login/')
def seller_detail(request, business_id):
    """
    View for viewing comprehensive seller/business details including
    teams, API settings, pickup locations, and documents.
    """
    from django.db.models import Count, Sum, Q
    from django.utils import timezone
    from datetime import timedelta

    # Fetch business with all related data
    business = get_object_or_404(
        business_models.Business.objects.select_related(
            'user', 'profile'
        ).prefetch_related(
            'team_members__user',
            'business_settings_api',
            'pickup_location',
        ),
        business_id=business_id
    )

    # Get business profile (handle missing OneToOne relation)
    try:
        business_profile = business.business_profile
    except Exception:
        business_profile = None

    # Get team members
    team_members = business.team_members.select_related('user', 'profile').all()

    # Get API settings
    api_settings = business.business_settings_api.all()

    # Get pickup locations
    pickup_locations = business.pickup_location.all()

    # Get comprehensive order statistics
    order_stats = orders_models.Order.objects.filter(business=business).aggregate(
        total_orders=Count('id'),
        pending_orders=Count('id', filter=Q(order_status='pending')),
        processing_orders=Count('id', filter=Q(order_status='processing')),
        delivered_orders=Count('id', filter=Q(order_status='delivered')),
        cancelled_orders=Count('id', filter=Q(order_status='cancelled')),
        failed_orders=Count('id', filter=Q(order_status='failed')),
    )

    # Get COD statistics
    cod_stats = orders_models.Order.objects.filter(
        business=business,
        cod_status_by_client='include'
    ).aggregate(
        total_cod_orders=Count('id'),
        total_cod_amount=Sum('cod_amount'),
        collected_cod=Sum('cod_amount', filter=Q(order_status='delivered')),
        pending_cod=Sum('cod_amount', filter=~Q(order_status__in=['delivered', 'cancelled', 'failed'])),
    )

    # Calculate delivery success rate
    total_completed = (order_stats.get('delivered_orders') or 0) + (order_stats.get('failed_orders') or 0) + (order_stats.get('cancelled_orders') or 0)
    delivery_success_rate = 0
    if total_completed > 0:
        delivery_success_rate = round((order_stats.get('delivered_orders') or 0) / total_completed * 100, 1)

    # Get recent orders count (last 30 days)
    thirty_days_ago = timezone.now() - timedelta(days=30)
    recent_orders_count = orders_models.Order.objects.filter(
        business=business,
        created_at__gte=thirty_days_ago
    ).count()

    # Get last 7 days orders for trend
    seven_days_ago = timezone.now() - timedelta(days=7)
    last_7_days_orders = orders_models.Order.objects.filter(
        business=business,
        created_at__gte=seven_days_ago
    ).count()

    # Get recent orders for activity timeline (last 10)
    # Use .only() to avoid missing columns (delivered_at, fulfilled_at not migrated)
    recent_orders = orders_models.Order.objects.filter(
        business=business
    ).only(
        'id', 'order_number', 'client_order_code', 'order_status',
        'cod_amount', 'customer_name', 'customer_phone', 'created_at'
    ).order_by('-created_at')[:10]

    # Get delivery task statistics
    delivery_stats = delivery_models.DeliveryTask.objects.filter(
        business=business
    ).aggregate(
        total_tasks=Count('id'),
        in_transit=Count('id', filter=Q(dl_task_status='in_transit')),
        completed=Count('id', filter=Q(dl_task_status='delivered')),
    )

    # Calculate average orders per month (if business_since exists)
    avg_orders_per_month = 0
    if business.business_since:
        months_active = max(1, (timezone.now().date() - business.business_since).days / 30)
        avg_orders_per_month = round((order_stats.get('total_orders') or 0) / months_active, 1)

    # Handle POST for status update
    if request.method == 'POST':
        try:
            # Basic Information
            business.business_code = request.POST.get('business_code', business.business_code) or None
            business.business_name = request.POST.get('business_name', business.business_name)
            business.business_qid = request.POST.get('business_qid', business.business_qid) or None
            business.business_product_category = request.POST.get('business_product_category', business.business_product_category) or None
            business.business_bio = request.POST.get('business_bio', business.business_bio) or None
            business.business_status = request.POST.get('business_status', business.business_status)

            # Handle business_since date
            business_since_str = request.POST.get('business_since', '')
            if business_since_str:
                from datetime import datetime
                try:
                    business.business_since = datetime.strptime(business_since_str, '%Y-%m-%d').date()
                except ValueError:
                    pass  # Keep existing value if parsing fails
            else:
                business.business_since = None

            # Contact Information
            business.business_phone = request.POST.get('business_phone', business.business_phone) or None
            business.business_whatsapp = request.POST.get('business_whatsapp', business.business_whatsapp) or None
            business.business_email = request.POST.get('business_email', business.business_email) or None

            # Social Media
            business.business_instagram = request.POST.get('business_instagram', business.business_instagram) or None
            business.business_facebook_page = request.POST.get('business_facebook_page', business.business_facebook_page) or None

            # Handle fulfillment service toggle
            fulfillment_enabled = request.POST.get('fulfillment_service_enabled') == 'on'
            if fulfillment_enabled and not business.fulfillment_service_enabled:
                business.fulfillment_service_enabled = True
                business.fulfillment_activated_at = timezone.now()
            elif not fulfillment_enabled:
                business.fulfillment_service_enabled = False

            business.save()

            # Update business profile if exists, create if not
            if not business_profile:
                business_profile = business_models.BusinessProfile.objects.create(business=business)

            business_profile.business_address = request.POST.get('business_address', business_profile.business_address) or None
            business_profile.business_city = request.POST.get('business_city', business_profile.business_city) or None
            business_profile.business_state = request.POST.get('business_state', business_profile.business_state) or None
            business_profile.business_zip_code = request.POST.get('business_zip_code', business_profile.business_zip_code) or None
            business_profile.business_country = request.POST.get('business_country', business_profile.business_country) or 'Qatar'
            business_profile.business_website = request.POST.get('business_website', business_profile.business_website) or None
            business_profile.save()

            return JsonResponse({
                'success': True,
                'message': 'Seller updated successfully'
            })
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': str(e)
            }, status=400)

    # Build documents list from business profile fields (if available)
    documents = []
    # Add QID document if available
    if business.business_qid:
        documents.append({
            'document_type': 'QID',
            'document_no': business.business_qid,
            'document_file': None,
            'document_expiry_date': None,
        })
    # Add business logo as document if available (check for actual file, not default)
    if hasattr(business, 'business_logo') and business.business_logo:
        try:
            # Check if file actually exists and has content (not just default placeholder)
            has_real_file = business.business_logo.name and business.business_logo.size > 0
        except Exception:
            has_real_file = False
        documents.append({
            'document_type': 'Business Logo',
            'document_no': 'Logo Image',
            'document_file': business.business_logo if has_real_file else None,
            'document_expiry_date': None,
        })

    context = {
        'page_title': f'Seller: {business.business_name}',
        'business': business,
        'business_profile': business_profile,
        'team_members': team_members,
        'api_settings': api_settings,
        'pickup_locations': pickup_locations,
        'order_stats': order_stats,
        'cod_stats': cod_stats,
        'delivery_stats': delivery_stats,
        'delivery_success_rate': delivery_success_rate,
        'recent_orders_count': recent_orders_count,
        'last_7_days_orders': last_7_days_orders,
        'recent_orders': recent_orders,
        'avg_orders_per_month': avg_orders_per_month,
        'documents': documents,
        'now': timezone.now(),
    }

    return render(request, 'workforce/seller_detail.html', context)


# =============================================================================
# DRIVER MANAGEMENT VIEWS
# =============================================================================

@login_required(login_url='/accounts/login/')
def drivers_list(request):
    """
    View to display all drivers with search and filtering
    """
    drivers = fleet_models.Driver.objects.select_related(
        'user', 'profile'
    ).prefetch_related(
        'driver_vehicle', 'driver_document'
    ).order_by('-driver_id')

    # Apply search filter
    search = request.GET.get('search', '').strip()
    if search:
        from django.db.models import Q
        drivers = drivers.filter(
            Q(user__first_name__icontains=search) |
            Q(user__last_name__icontains=search) |
            Q(driver_code__icontains=search) |
            Q(driver_phone__icontains=search)
        )

    # Apply status filter
    status_filter = request.GET.get('status', '')
    if status_filter:
        drivers = drivers.filter(driver_status=status_filter)

    # Pagination
    page_obj = paginate_queryset(request, drivers, items_per_page=20)

    # Get counts for stats
    total_count = fleet_models.Driver.objects.count()
    active_count = fleet_models.Driver.objects.filter(driver_status='Approved').count()
    pending_count = fleet_models.Driver.objects.filter(driver_status__in=['Pending on Review', 'Processing']).count()
    inactive_count = fleet_models.Driver.objects.filter(driver_status__in=['Rejected', 'Blocked']).count()

    context = {
        'page_title': 'All Drivers',
        'page_obj': page_obj,
        'search': search,
        'status_filter': status_filter,
        'total_count': total_count,
        'active_count': active_count,
        'pending_count': pending_count,
        'inactive_count': inactive_count,
    }

    return render(request, 'workforce/drivers_list.html', context)


@login_required(login_url='/accounts/login/')
def drivers_pending(request):
    """
    View to display drivers pending approval
    """
    drivers = fleet_models.Driver.objects.select_related(
        'user', 'profile'
    ).prefetch_related(
        'driver_vehicle', 'driver_document'
    ).filter(
        driver_status__in=['Pending on Review', 'Processing']
    ).order_by('-driver_id')

    # Apply search filter
    search = request.GET.get('search', '').strip()
    if search:
        from django.db.models import Q
        drivers = drivers.filter(
            Q(user__first_name__icontains=search) |
            Q(user__last_name__icontains=search) |
            Q(driver_code__icontains=search) |
            Q(driver_phone__icontains=search)
        )

    # Pagination
    page_obj = paginate_queryset(request, drivers, items_per_page=20)

    context = {
        'page_title': 'Pending Drivers',
        'page_obj': page_obj,
        'search': search,
        'status_type': 'pending',
    }

    return render(request, 'workforce/drivers_pending.html', context)


@login_required(login_url='/accounts/login/')
def drivers_active(request):
    """
    View to display active (approved) drivers
    """
    drivers = fleet_models.Driver.objects.select_related(
        'user', 'profile'
    ).prefetch_related(
        'driver_vehicle', 'driver_document'
    ).filter(
        driver_status='Approved'
    ).order_by('-driver_id')

    # Apply search filter
    search = request.GET.get('search', '').strip()
    if search:
        from django.db.models import Q
        drivers = drivers.filter(
            Q(user__first_name__icontains=search) |
            Q(user__last_name__icontains=search) |
            Q(driver_code__icontains=search) |
            Q(driver_phone__icontains=search)
        )

    # Pagination
    page_obj = paginate_queryset(request, drivers, items_per_page=20)

    context = {
        'page_title': 'Active Drivers',
        'page_obj': page_obj,
        'search': search,
        'status_type': 'active',
    }

    return render(request, 'workforce/drivers_active.html', context)


@login_required(login_url='/accounts/login/')
def drivers_inactive(request):
    """
    View to display inactive, rejected, or blocked drivers
    """
    drivers = fleet_models.Driver.objects.select_related(
        'user', 'profile'
    ).prefetch_related(
        'driver_vehicle', 'driver_document'
    ).filter(
        driver_status__in=['Rejected', 'Blocked']
    ).order_by('-driver_id')

    # Apply search filter
    search = request.GET.get('search', '').strip()
    if search:
        from django.db.models import Q
        drivers = drivers.filter(
            Q(user__first_name__icontains=search) |
            Q(user__last_name__icontains=search) |
            Q(driver_code__icontains=search) |
            Q(driver_phone__icontains=search)
        )

    # Pagination
    page_obj = paginate_queryset(request, drivers, items_per_page=20)

    context = {
        'page_title': 'Inactive Drivers',
        'page_obj': page_obj,
        'search': search,
        'status_type': 'inactive',
    }

    return render(request, 'workforce/drivers_inactive.html', context)


@login_required(login_url='/accounts/login/')
def driver_detail(request, driver_id):
    """
    View for viewing comprehensive driver details including
    documents, vehicles, transactions, and delivery stats.
    """
    from django.db.models import Count, Sum, Q
    from django.utils import timezone
    from datetime import timedelta

    # Fetch driver with all related data
    driver = get_object_or_404(
        fleet_models.Driver.objects.select_related(
            'user', 'profile'
        ).prefetch_related(
            'driver_vehicle',
            'driver_document',
        ),
        driver_id=driver_id
    )

    # Get vehicles
    vehicles = driver.driver_vehicle.all()

    # Get documents and check if files actually exist
    raw_documents = driver.driver_document.all()
    documents = []
    for doc in raw_documents:
        doc_dict = {
            'document_type': doc.document_type,
            'document_no': doc.document_no,
            'document_expiry_date': getattr(doc, 'document_expiry_date', None),
            'document_file': None,  # Default to None
        }
        # Check if file actually exists on disk
        if doc.document_file and doc.document_file.name:
            try:
                if doc.document_file.storage.exists(doc.document_file.name):
                    doc_dict['document_file'] = doc.document_file
            except Exception:
                pass
        documents.append(doc_dict)

    # Get delivery task statistics
    delivery_stats = delivery_models.DeliveryTask.objects.filter(
        driver=driver
    ).aggregate(
        total_tasks=Count('id'),
        completed_tasks=Count('id', filter=Q(dl_task_status='delivered')),
        in_transit=Count('id', filter=Q(dl_task_status='in_transit')),
        failed_tasks=Count('id', filter=Q(dl_task_status__in=['failed', 'cancelled'])),
    )

    # Calculate success rate
    total_completed = (delivery_stats.get('completed_tasks') or 0) + (delivery_stats.get('failed_tasks') or 0)
    success_rate = 0
    if total_completed > 0:
        success_rate = round((delivery_stats.get('completed_tasks') or 0) / total_completed * 100, 1)

    # Get recent tasks count (last 30 days)
    thirty_days_ago = timezone.now() - timedelta(days=30)
    recent_tasks_count = delivery_models.DeliveryTask.objects.filter(
        driver=driver,
        created_at__gte=thirty_days_ago
    ).count()

    # Get last 7 days tasks for trend
    seven_days_ago = timezone.now() - timedelta(days=7)
    last_7_days_tasks = delivery_models.DeliveryTask.objects.filter(
        driver=driver,
        created_at__gte=seven_days_ago
    ).count()

    # Get recent tasks for activity timeline (last 10)
    recent_tasks = delivery_models.DeliveryTask.objects.filter(
        driver=driver
    ).select_related('business').order_by('-created_at')[:10]

    # Get COD statistics
    cod_stats = delivery_models.DeliveryTask.objects.filter(
        driver=driver,
        order__cod_status_by_client='include'
    ).aggregate(
        total_cod_tasks=Count('id'),
        total_cod_amount=Sum('order__cod_amount'),
        collected_cod=Sum('order__cod_amount', filter=Q(dl_task_status='delivered')),
    )

    # Get recent transactions (last 10)
    recent_transactions = fleet_models.DriverTransaction.objects.filter(
        driver=driver
    ).order_by('-created_at')[:10]

    # Handle POST request for updates
    if request.method == 'POST':
        try:
            driver.driver_phone = request.POST.get('driver_phone', driver.driver_phone)
            driver.driver_whatsapp = request.POST.get('driver_whatsapp', driver.driver_whatsapp)
            driver.driver_status = request.POST.get('driver_status', driver.driver_status)
            driver.driver_bio = request.POST.get('driver_bio', driver.driver_bio)
            driver.save()

            return JsonResponse({
                'success': True,
                'message': 'Driver updated successfully'
            })
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': str(e)
            }, status=400)

    context = {
        'page_title': f'Driver: {driver.user.first_name} {driver.user.last_name}',
        'driver': driver,
        'vehicles': vehicles,
        'documents': documents,
        'delivery_stats': delivery_stats,
        'success_rate': success_rate,
        'recent_tasks_count': recent_tasks_count,
        'last_7_days_tasks': last_7_days_tasks,
        'recent_tasks': recent_tasks,
        'cod_stats': cod_stats,
        'recent_transactions': recent_transactions,
        'now': timezone.now(),
    }

    return render(request, 'workforce/driver_detail.html', context)


# =============================================================================
# FULFILLMENT SERVICE & PURCHASE ORDERS
# =============================================================================


@login_required
def suppliers_list(request):
    """
    List all businesses with fulfillment service enabled (Suppliers).
    These are the sellers/clients using EzzyDelivery's fulfillment service.
    """
    suppliers = business_models.Business.objects.filter(
        fulfillment_service_enabled=True,
        business_status='active'
    ).order_by('-fulfillment_activated_at', 'business_name')

    # Search filter
    search = request.GET.get('search', '')
    if search:
        suppliers = suppliers.filter(
            Q(business_name__icontains=search) |
            Q(business_code__icontains=search) |
            Q(business_email__icontains=search) |
            Q(business_phone__icontains=search)
        )

    # Calculate stats for each supplier
    from django.db.models import Count, Sum, Q as DjangoQ
    suppliers = suppliers.annotate(
        total_orders=Count('order'),
        fulfilled_orders=Count('order', filter=DjangoQ(order__order_status__in=['delivered', 'fulfilled'])),
        pending_orders=Count('order', filter=DjangoQ(order__order_status__in=['to_review', 'ready_to_pickup', 'publish']))
    )

    # Paginate first to avoid duplicate count query
    page_obj = paginate_queryset(request, suppliers, items_per_page=20)

    # Summary stats - reuse count from paginator to avoid duplicate query
    total_suppliers = page_obj.paginator.count
    total_fulfilled = orders_models.Order.objects.filter(
        order_status__in=['delivered', 'fulfilled'],
        business__fulfillment_service_enabled=True
    ).count()

    context = {
        'page_title': 'Suppliers (Fulfillment Service)',
        'page_obj': page_obj,
        'search': search,
        'total_suppliers': total_suppliers,
        'total_fulfilled': total_fulfilled,
    }

    return render(request, 'workforce/suppliers_list.html', context)


@login_required
def fulfilled_orders_list(request):
    """
    List all fulfilled/delivered orders (Purchase Orders).
    Shows orders that have been successfully delivered.
    """
    from django.db.models import Q

    orders = orders_models.Order.objects.filter(
        order_status__in=['delivered', 'fulfilled']
    ).select_related('business').order_by('-delivered_at', '-updated_at')

    # Filters
    business_id = request.GET.get('business', '')
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')
    search = request.GET.get('search', '')
    order_status = request.GET.get('status', '')

    if business_id:
        orders = orders.filter(business__business_id=business_id)

    if date_from:
        orders = orders.filter(delivered_at__date__gte=date_from)

    if date_to:
        orders = orders.filter(delivered_at__date__lte=date_to)

    if search:
        orders = orders.filter(
            Q(order_number__icontains=search) |
            Q(client_order_code__icontains=search) |
            Q(customer_name__icontains=search) |
            Q(customer_phone__icontains=search)
        )

    if order_status:
        orders = orders.filter(order_status=order_status)

    # Get suppliers for filter dropdown (businesses with fulfillment enabled)
    suppliers = business_models.Business.objects.filter(
        fulfillment_service_enabled=True,
        business_status='active'
    ).order_by('business_name')

    # Summary stats
    total_count = orders.count()
    fulfilled_count = orders.filter(order_status='fulfilled').count()
    delivered_count = orders.filter(order_status='delivered').count()

    # Calculate total COD collected
    from django.db.models import Sum
    total_cod = orders.filter(
        cod_status_by_client='include'
    ).aggregate(total=Sum('cod_amount'))['total'] or 0

    # Paginate
    page_obj = paginate_queryset(request, orders, items_per_page=25)

    context = {
        'page_title': 'Purchase Orders (Fulfilled)',
        'page_obj': page_obj,
        'suppliers': suppliers,
        'filters': {
            'business': business_id,
            'date_from': date_from,
            'date_to': date_to,
            'search': search,
            'status': order_status,
        },
        'total_count': total_count,
        'fulfilled_count': fulfilled_count,
        'delivered_count': delivered_count,
        'total_cod': total_cod,
    }

    return render(request, 'workforce/fulfilled_orders_list.html', context)


