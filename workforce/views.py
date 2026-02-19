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

from django.http import Http404, HttpResponse, JsonResponse
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
import csv
from django.contrib.auth.decorators import login_required
from core.decorators import staff_required
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import ensure_csrf_cookie
import json
import logging
from django.core.paginator import (
    Paginator,
    EmptyPage,
    PageNotAnInteger,
)
from django.urls import reverse
from django.db.models import Count, Q

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


def get_per_page(request, default=10):
    """
    Get the validated per_page value from request.
    Valid per_page values: 10, 25, 50, 100 (defaults to provided default if invalid)
    Returns the per_page value as a string for template use.
    """
    per_page = request.GET.get('per_page')
    if per_page:
        try:
            per_page = int(per_page)
            if per_page not in [10, 25, 50, 100]:
                per_page = default
        except (ValueError, TypeError):
            per_page = default
    else:
        per_page = default
    return str(per_page)


def paginate_queryset(request, queryset, items_per_page=10):
    """
    A helper function to handle pagination for a given queryset.
    Reads 'per_page' from request.GET to allow users to change page size.
    Valid per_page values: 10, 25, 50, 100 (defaults to items_per_page if invalid)
    """
    # Read per_page from request, with validation
    per_page = request.GET.get('per_page')
    if per_page:
        try:
            per_page = int(per_page)
            # Only allow valid page sizes to prevent abuse
            if per_page not in [10, 25, 50, 100]:
                per_page = items_per_page
        except (ValueError, TypeError):
            per_page = items_per_page
    else:
        per_page = items_per_page

    paginator = Paginator(queryset, per_page)
    page_number = request.GET.get('page', 1)
    try:
        page_obj = paginator.page(page_number)
    except PageNotAnInteger:
        page_obj = paginator.page(1)
    except EmptyPage:
        page_obj = paginator.page(paginator.num_pages)
    return page_obj




@login_required(login_url='/accounts/login/')
@staff_required
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

    # Order Statistics - single aggregate query instead of 5 separate counts
    from django.db.models import Case, When, IntegerField
    order_stats = Order.objects.aggregate(
        total=Count('id'),
        today=Count(Case(When(order_date=today, then=1), output_field=IntegerField())),
        not_published=Count(Case(When(
            task_created=False,
            then=Case(When(
                ~Q(order_status__in=['cancelled', 'delivered', 'fulfilled']),
                then=1
            ), output_field=IntegerField())
        ), output_field=IntegerField())),
        published=Count(Case(When(task_created=True, then=1), output_field=IntegerField())),
        loc_reconfirm=Count(Case(When(
            verification_status__in=['pending', 'needs_review'], then=1
        ), output_field=IntegerField())),
    )
    total_orders = order_stats['total']
    orders_today = order_stats['today']
    not_published = order_stats['not_published']
    published_orders = order_stats['published']
    loc_reconfirm = order_stats['loc_reconfirm']

    # Follow up count - tasks that need attention
    follow_up_count = DeliveryTask.objects.filter(
        dl_task_status__in=['failed', 'rescheduled', 'customer_unavailable']
    ).count()

    # User Verification pending
    pending_verifications = core_models.Profile.objects.filter(
        verification_status='pending'
    ).count()

    # Driver and Seller counts - 2 aggregate queries instead of 4 separate counts
    driver_stats = Driver.objects.aggregate(
        active=Count(Case(When(driver_status='approved', then=1), output_field=IntegerField())),
        pending=Count(Case(When(driver_status='pending', then=1), output_field=IntegerField())),
        cod_in_hand=Sum('wallet_balance'),
    )
    active_drivers = driver_stats['active']
    pending_drivers = driver_stats['pending']
    cod_in_hand = driver_stats['cod_in_hand'] or 0

    seller_stats = Business.objects.aggregate(
        active=Count(Case(When(business_status='Approved', then=1), output_field=IntegerField())),
        pending=Count(Case(When(business_status='Pending on Review', then=1), output_field=IntegerField())),
    )
    active_sellers = seller_stats['active']
    pending_sellers = seller_stats['pending']

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
@staff_required
def all_orders(request):
    from django.db.models import Count

    # Start with all orders, prefetch related data to avoid N+1 queries
    orders = orders_models.Order.objects.select_related(
        'business', 'pickup_location'
    ).prefetch_related('order_comments', 'delivery_task', 'order_items')

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
@staff_required
def fulfilled_clients_orders(request):
    """Orders from businesses with fulfillment service enabled"""
    from django.db.models import Count

    # Filter orders from businesses with fulfillment service enabled
    orders = orders_models.Order.objects.select_related(
        'business', 'pickup_location'
    ).prefetch_related('order_comments', 'delivery_task', 'order_items').filter(
        business__fulfillment_service_enabled=True
    )

    # Apply filters based on GET parameters
    dl_code = request.GET.get('dlCode', '').strip()
    c_code = request.GET.get('cCode', '').strip()
    mobile = request.GET.get('mobile', '').strip()
    c_status = request.GET.get('cStatus', '').strip()
    dms_status = request.GET.get('dmsStatus', '').strip()
    business_id = request.GET.get('business', '').strip()

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

    # Annotate with comment count
    orders = orders.annotate(unread_comments_count=Count('order_comments'))
    orders = orders.order_by('-created_at')
    orders = paginate_queryset(request, orders)

    # Get all fulfillment-enabled businesses for filter
    all_businesses = business_models.Business.objects.filter(
        fulfillment_service_enabled=True
    ).order_by('business_name')

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
        },
        'page_title': 'Fulfilled Clients Orders',
    }
    return render(request, 'workforce/parts/lists/orders_list_view.html', data)


@login_required(login_url='/accounts/login/')
@staff_required
def non_fulfilled_clients_orders(request):
    """Orders from businesses without fulfillment service"""
    from django.db.models import Count

    # Filter orders from businesses without fulfillment service
    orders = orders_models.Order.objects.select_related(
        'business', 'pickup_location'
    ).prefetch_related('order_comments', 'delivery_task', 'order_items').filter(
        business__fulfillment_service_enabled=False
    )

    # Apply filters based on GET parameters
    dl_code = request.GET.get('dlCode', '').strip()
    c_code = request.GET.get('cCode', '').strip()
    mobile = request.GET.get('mobile', '').strip()
    c_status = request.GET.get('cStatus', '').strip()
    dms_status = request.GET.get('dmsStatus', '').strip()
    business_id = request.GET.get('business', '').strip()

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

    # Annotate with comment count
    orders = orders.annotate(unread_comments_count=Count('order_comments'))
    orders = orders.order_by('-created_at')
    orders = paginate_queryset(request, orders)

    # Get all non-fulfillment businesses for filter
    all_businesses = business_models.Business.objects.filter(
        fulfillment_service_enabled=False
    ).order_by('business_name')

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
        },
        'page_title': 'Non-Fulfilled Clients Orders',
    }
    return render(request, 'workforce/parts/lists/orders_list_view.html', data)


@login_required(login_url='/accounts/login/')
@staff_required
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
@staff_required
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
@staff_required
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
@staff_required
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
@staff_required
def orders_published(request):
    orders = orders_models.Order.objects.select_related(
        'business', 'pickup_location'
    ).prefetch_related('order_comments', 'delivery_task').filter(task_created=True).order_by('-created_at')
    orders = paginate_queryset(request, orders)

    data = {
        'orders': orders,
    }
    return render(request, 'workforce/parts/lists/orders_list_view.html', data)

@login_required(login_url='/accounts/login/')
@staff_required
def submit_to_task(request, order_id):
    """Submit order to delivery task - now uses verification workflow"""
    from django.utils import timezone
    from orders.signals import _create_delivery_task_from_order
    
    order = get_object_or_404(
        orders_models.Order.objects.select_related('business'),
        id=order_id
    )

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
@staff_required
def verify_order_address(request, order_id):
    """Verify order address - workforce view"""
    from django.utils import timezone
    from orders.models import AddressVerification, OrderVerificationLog

    order = get_object_or_404(
        orders_models.Order.objects.select_related('business'),
        id=order_id
    )
    
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
@staff_required
def verify_order(request, order_id):
    """Verify order - workforce view"""
    from django.utils import timezone
    from orders.models import OrderVerificationLog
    from orders.signals import _create_delivery_task_from_order

    order = get_object_or_404(
        orders_models.Order.objects.select_related('business'),
        id=order_id
    )

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
@staff_required
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
@staff_required
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
    warehouse_products = []

    if selected_business_id:
        try:
            selected_business = business_models.Business.objects.get(business_id=selected_business_id)
            # Show fulfillment stores first when fulfillment service is enabled
            pickup_locations = business_models.PickupLocation.objects.filter(
                business=selected_business
            ).order_by('-is_fulfilment_center', 'pickup_location_title')

            # If fulfillment service is enabled, fetch warehouse inventory products
            if selected_business.fulfillment_service_enabled:
                from warehouse import models as warehouse_models
                from django.db.models import Sum

                # Get warehouse links for this business
                warehouse_links = warehouse_models.SellerWarehouseLink.objects.filter(
                    business=selected_business,
                    is_active=True
                ).select_related('warehouse', 'default_location')

                # Get products from delivered orders (order items) for this business
                if warehouse_links.exists():
                    warehouse_ids = warehouse_links.values_list('warehouse_id', flat=True)

                    # Get products from OrderItems where order status is delivered
                    # and the product exists in warehouse stock
                    delivered_order_products = orders_models.OrderItem.objects.filter(
                        order__business=selected_business,
                        order__order_status='delivered',
                        product__isnull=False,
                        product__is_active=True
                    ).values('product_id').annotate(
                        total_delivered=Sum('quantity')
                    ).values_list('product_id', flat=True).distinct()

                    # Get stock levels for these products from linked warehouses
                    warehouse_products = warehouse_models.StockLevel.objects.filter(
                        warehouse_id__in=warehouse_ids,
                        product_id__in=delivered_order_products,
                        available_quantity__gt=0,
                        product__is_active=True
                    ).select_related(
                        'product', 'warehouse', 'storage_location'
                    ).order_by('product__name')[:100]  # Limit to 100 products for performance
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

            # Parse scheduled time if provided
            scheduled_delivery = request.POST.get('scheduled_delivery') == 'on'
            scheduled_time = None
            if scheduled_delivery and request.POST.get('scheduled_time'):
                from datetime import datetime
                try:
                    scheduled_time = datetime.strptime(request.POST.get('scheduled_time'), '%H:%M').time()
                except ValueError:
                    scheduled_time = None

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
                order_type=request.POST.get('order_type', 'normal_delivery'),
                scheduled_delivery=scheduled_delivery,
                scheduled_time=scheduled_time,
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
            logger.exception('Error creating order: %s', str(e))
            error_msg = 'An error occurred while creating the order. Please try again.'
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'success': False, 'error': error_msg}, status=400)
            messages.error(request, error_msg)

    from datetime import date
    context = {
        'businesses': businesses,
        'selected_business': selected_business,
        'selected_business_id': selected_business_id,
        'pickup_locations': pickup_locations,
        'warehouse_products': warehouse_products,
        'has_fulfillment': selected_business.fulfillment_service_enabled if selected_business else False,
        'today': date.today().isoformat(),
    }
    return render(request, 'workforce/orders_add.html', context)


# Bulk import views removed - now using shared views from orders app
# See orders/views.py: bulk_import_orders, bulk_import_preview, bulk_import_save


@login_required(login_url='/accounts/login/')
@staff_required
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
@staff_required
def get_pickup_locations(request, business_id):
    """AJAX endpoint to get pickup locations for a business"""
    try:
        business = business_models.Business.objects.get(business_id=business_id)
        # Show fulfillment stores first when fulfillment service is enabled
        locations = business_models.PickupLocation.objects.filter(
            business=business
        ).order_by('-is_fulfilment_center', 'pickup_location_title')

        location_list = [{
            'id': loc.id,
            'name': loc.pickup_location_title,
            'address': loc.locality or '',
        } for loc in locations]

        return JsonResponse({'success': True, 'locations': location_list})
    except business_models.Business.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Business not found'}, status=404)


@login_required(login_url='/accounts/login/')
@staff_required
def workforce_pickup_location_add(request, business_id):
    """Workforce view for products management - add products and view products list"""
    try:
        from product import models as product_models
        from django.db.models import Sum, Q

        business = business_models.Business.objects.get(business_id=business_id)

        if request.method == 'POST':
            action = request.POST.get('action')

            if action == 'add_product':
                try:
                    # Create product
                    product = product_models.Product.objects.create(
                        business=business,
                        brand_name=request.POST.get('brand_name'),
                        item_name=request.POST.get('item_name'),
                        item_sku=request.POST.get('item_sku'),
                        barcode=request.POST.get('barcode') or None,
                        item_price=int(request.POST.get('item_price', 0)),
                        item_discription=request.POST.get('item_discription') or '',
                    )

                    # Create inventory record if quantity provided
                    quantity = int(request.POST.get('quantity', 0))
                    if quantity > 0:
                        product_models.ProductInventory.objects.create(
                            item_sku=product,
                            item_quantity=quantity
                        )

                    logger.info(f"Workforce user {request.user.id} added product {product.item_sku} for business {business.business_id}")
                    messages.success(request, f"Product '{product.item_name}' added successfully")

                    # Return JSON for AJAX requests
                    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                        return JsonResponse({'success': True, 'message': 'Product added successfully'})

                    return redirect('workforce:workforce_pickup_location_add', business_id=business.business_id)
                except Exception as e:
                    logger.error(f"Error adding product: {str(e)}")
                    messages.error(request, f"Error adding product: {str(e)}")

                    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                        return JsonResponse({'success': False, 'error': str(e)}, status=400)

        # Get all products for this business with inventory
        products = product_models.Product.objects.filter(
            business=business
        ).select_related(
            'product_category', 'color', 'unit'
        ).prefetch_related(
            'product_inventory'
        ).order_by('-created_at')

        # Annotate with total stock quantity
        products_with_stock = []
        for product in products:
            total_stock = product.product_inventory.aggregate(
                total=Sum('item_quantity')
            )['total'] or 0
            product.stock_quantity = total_stock
            products_with_stock.append(product)

        context = {
            'business': business,
            'products': products_with_stock,
        }
        return render(request, 'workforce/workforce_pickup_location_add.html', context)
    except business_models.Business.DoesNotExist:
        logger.error(f"Business {business_id} not found")
        messages.error(request, "Business not found")
        return redirect('workforce:business_licenses_list')


# Delivery Tasks section  ------------------------------------------------------------------------------------------------------

@login_required(login_url='/accounts/login/')
@staff_required
def dl_list_all(request):
    dl_tasks = delivery_models.DeliveryTask.objects.select_related(
        'order', 'driver', 'business', 'pickup_location', 'order__business'
    ).prefetch_related(
        'order__order_comments',
        'order__order_items',
        'order__order_items__product',
        'task_qrcode',
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
        dl_tasks = dl_tasks.filter(
            Q(driver__user__first_name__icontains=driver_name) |
            Q(driver__user__last_name__icontains=driver_name) |
            Q(driver__user__username__icontains=driver_name)
        )
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
        'today': timezone.localtime().date(),
        'page_title': 'All Delivery Tasks',
        'page_subtitle': 'Manage and track',
        'page_icon': 'fa-tasks',
        'list_type': 'all',
        'show_filters': True,
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
@staff_required
def fulfilled_clients_tasks(request):
    """Tasks from businesses with fulfillment service enabled"""
    dl_tasks = delivery_models.DeliveryTask.objects.select_related(
        'order', 'driver', 'business', 'pickup_location', 'order__business'
    ).prefetch_related(
        'order__order_comments',
        'order__order_items',
        'order__order_items__product',
        'task_qrcode',
    ).filter(
        order__business__fulfillment_service_enabled=True
    ).order_by('-created_at')

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
        dl_tasks = dl_tasks.filter(
            Q(driver__user__first_name__icontains=driver_name) |
            Q(driver__user__last_name__icontains=driver_name) |
            Q(driver__user__username__icontains=driver_name)
        )
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

    # Get fulfillment-enabled businesses
    businesses = business_models.Business.objects.filter(
        business_status='active',
        fulfillment_service_enabled=True
    ).order_by('business_name')

    dl_tasks = paginate_queryset(request, dl_tasks)

    data = {
        'dl_tasks': dl_tasks,
        'businesses': businesses,
        'today': timezone.localtime().date(),
        'page_title': 'Fulfilled Clients Tasks',
        'page_subtitle': 'Tasks from fulfillment-enabled businesses',
        'page_icon': 'fa-truck-ramp-box',
        'list_type': 'fulfilled',
        'show_filters': True,
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
@staff_required
def non_fulfilled_clients_tasks(request):
    """Tasks from businesses without fulfillment service"""
    dl_tasks = delivery_models.DeliveryTask.objects.select_related(
        'order', 'driver', 'business', 'pickup_location', 'order__business'
    ).prefetch_related(
        'order__order_comments',
        'order__order_items',
        'order__order_items__product',
        'task_qrcode',
    ).filter(
        order__business__fulfillment_service_enabled=False
    ).order_by('-created_at')

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
        dl_tasks = dl_tasks.filter(
            Q(driver__user__first_name__icontains=driver_name) |
            Q(driver__user__last_name__icontains=driver_name) |
            Q(driver__user__username__icontains=driver_name)
        )
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

    # Get non-fulfillment businesses
    businesses = business_models.Business.objects.filter(
        business_status='active',
        fulfillment_service_enabled=False
    ).order_by('business_name')

    dl_tasks = paginate_queryset(request, dl_tasks)

    data = {
        'dl_tasks': dl_tasks,
        'businesses': businesses,
        'today': timezone.localtime().date(),
        'page_title': 'Non-Fulfilled Clients Tasks',
        'page_subtitle': 'Tasks from standard delivery businesses',
        'page_icon': 'fa-truck-fast',
        'list_type': 'non_fulfilled',
        'show_filters': True,
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
@staff_required
def dl_list_incompleted_details(request):
    # Get incomplete delivery tasks (not delivered, not cancelled)
    dl_tasks = delivery_models.DeliveryTask.objects.select_related(
        'order', 'driver', 'business', 'pickup_location', 'order__business'
    ).prefetch_related(
        'order__order_items',
    ).exclude(
        dl_task_status__in=['delivered', 'cancelled']
    ).exclude(
        dl_task_status_dms__in=['2', '9']  # 2=Successful, 9=Cancel
    ).order_by('-created_at')

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

    if dl_code:
        dl_tasks = dl_tasks.filter(dl_task_number__icontains=dl_code)
    if c_code:
        dl_tasks = dl_tasks.filter(order__client_order_code__icontains=c_code)
    if mobile:
        dl_tasks = dl_tasks.filter(order__customer_phone__icontains=mobile)
    if driver_name:
        dl_tasks = dl_tasks.filter(
            Q(driver__user__first_name__icontains=driver_name) |
            Q(driver__user__last_name__icontains=driver_name) |
            Q(driver__user__username__icontains=driver_name)
        )
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

    businesses = business_models.Business.objects.filter(
        business_status='active'
    ).order_by('business_name')

    dl_tasks = paginate_queryset(request, dl_tasks)

    data = {
        'dl_tasks': dl_tasks,
        'businesses': businesses,
        'today': timezone.localtime().date(),
        'page_title': 'Incompleted Tasks',
        'page_subtitle': 'Pending delivery tasks',
        'page_icon': 'fa-clock-rotate-left',
        'list_type': 'incompleted',
        'show_filters': True,
        'filters': {
            'dlCode': dl_code, 'cCode': c_code, 'mobile': mobile,
            'driverName': driver_name, 'cStatus': c_status, 'dmsStatus': dms_status,
            'dateFrom': date_from, 'dateTo': date_to, 'business': business_id,
        }
    }
    return render(request, 'workforce/parts/lists/dl_list_all.html', data)


@login_required(login_url='/accounts/login/')
@staff_required
def dl_list_published_to_dms(request):
    dl_tasks = delivery_models.DeliveryTask.objects.select_related(
        'order', 'driver', 'business', 'pickup_location', 'order__business'
    ).prefetch_related(
        'order__order_items',
    ).filter(
        dl_task_publish=True
    ).order_by('-created_at')
    dl_tasks = paginate_queryset(request, dl_tasks)

    data = {
        'dl_tasks': dl_tasks,
        'today': timezone.localtime().date(),
        'page_title': 'Published to DMS',
        'page_subtitle': 'Tasks published to delivery management system',
        'page_icon': 'fa-cloud-arrow-up',
        'list_type': 'published',
    }
    return render(request, 'workforce/parts/lists/dl_list_all.html', data)


@login_required(login_url='/accounts/login/')
@staff_required
def dl_list_ready_to_published_to_dms(request):
    """List orders ready to be published to DMS (task_created=False)"""
    orders = orders_models.Order.objects.select_related(
        'business', 'pickup_location'
    ).prefetch_related(
        'delivery_task'
    ).filter(task_created=False).order_by('-created_at')
    orders = paginate_queryset(request, orders)

    data = {
        'orders': orders,
    }
    return render(request, 'workforce/parts/lists/dl_list_unpublished.html', data)




# DMS section  ------------------------------------------------------------------------------------------------------


# Workflow Guide -----------------------------------------------------

@login_required(login_url='account_login')
@staff_required
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
@staff_required
def order_detail(request, order_id):
    """Display order detail page"""
    order = get_object_or_404(
        orders_models.Order.objects.select_related('business', 'pickup_location', 'verified_by'),
        id=order_id
    )

    # Get related data with select_related to avoid N+1 queries
    order_items = orders_models.OrderItem.objects.filter(order=order)
    order_comments = orders_models.OrderComments.objects.filter(order=order).select_related('user').order_by('-created_at')
    verification_logs = orders_models.OrderVerificationLog.objects.filter(order=order).select_related('verified_by').order_by('-created_at')

    # Get delivery task if exists with related driver
    delivery_task = delivery_models.DeliveryTask.objects.select_related(
        'driver', 'driver__user', 'pickup_location'
    ).filter(order=order).first()

    # Get status change timeline
    status_history = orders_models.OrderStatusHistory.objects.filter(
        order=order
    ).select_related('changed_by').order_by('created_at')

    context = {
        'order': order,
        'order_items': order_items,
        'order_comments': order_comments,
        'verification_logs': verification_logs,
        'delivery_task': delivery_task,
        'status_history': status_history,
        'timeline_count': status_history.count(),
    }

    # Check if this is being loaded in a panel (via HTMX)
    # Use panel template only when targeting the slide panel, not main content
    is_htmx = request.headers.get('HX-Request') == 'true'
    hx_target = request.headers.get('HX-Target', '')

    # If targeting main-content or using hx-select, use full page template
    # Panel template is only for the slide-out panel (orderDetailContent)
    use_panel = is_htmx and hx_target == 'orderDetailContent'
    template = 'workforce/order_detail_panel.html' if use_panel else 'workforce/order_detail.html'

    return render(request, template, context)


@require_http_methods(["POST"])
@login_required(login_url='/accounts/login/')
@staff_required
def cancel_order(request, order_id):
    """Cancel an order"""
    try:
        order = get_object_or_404(
            orders_models.Order.objects.select_related('business'),
            id=order_id
        )

        if order.order_status == 'published':
            return JsonResponse({
                'success': False,
                'error': 'Cannot cancel a published order'
            }, status=400)

        # Update order status
        old_status = order.order_status
        order.order_status = 'cancelled'
        order.save()

        # Cancel related delivery task
        delivery_task = delivery_models.DeliveryTask.objects.filter(order=order).first()
        if delivery_task and delivery_task.dl_task_status != 'cancelled':
            delivery_task.dl_task_status = 'cancelled'
            delivery_task.dl_task_status_dms = '9'  # Cancel in DMS
            delivery_task.dl_task_status_client = '9'  # Cancel for client
            delivery_task.save(update_fields=['dl_task_status', 'dl_task_status_dms', 'dl_task_status_client'])

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
    except Http404:
        raise
    except Exception as e:
        logger.exception("Error cancelling order %s: %s", order_id, str(e))
        return JsonResponse({
            'success': False,
            'error': 'An error occurred while cancelling the order'
        }, status=400)


@require_http_methods(["POST"])
@login_required(login_url='/accounts/login/')
@staff_required
def assign_driver_to_order(request, order_id):
    """Assign a driver to an order (from AI suggest result)"""
    try:
        order = get_object_or_404(
            orders_models.Order.objects.select_related('business'),
            id=order_id
        )
        data = json.loads(request.body)
        driver_id = data.get('driver_id')

        if not driver_id:
            return JsonResponse({
                'success': False,
                'error': 'Driver ID is required'
            }, status=400)

        # Verify driver exists and is approved
        try:
            driver = fleet_models.Driver.objects.get(driver_id=driver_id, driver_status='approved')
        except fleet_models.Driver.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': f'Driver {driver_id} not found or not approved'
            }, status=400)

        # Check if order already has a delivery task - use select_for_update to prevent race conditions
        from django.db import transaction

        with transaction.atomic():
            existing_task = delivery_models.DeliveryTask.objects.select_for_update().filter(order=order).first()

            if existing_task:
                # Update existing task
                old_driver = existing_task.driver
                existing_task.driver = driver
                existing_task.save()

                # Log the update
                orders_models.OrderVerificationLog.objects.create(
                    order=order,
                    verified_by=request.user,
                    action='driver_reassigned',
                    old_status=str(old_driver.driver_id) if old_driver else 'None',
                    new_status=str(driver_id),
                    notes=f'Driver reassigned from AI suggestion: {driver.user.get_full_name() if driver.user else driver.driver_code}'
                )
            else:
                # Create new delivery task
                task = delivery_models.DeliveryTask.objects.create(
                    order=order,
                    driver=driver,
                    business=order.business,
                    pickup_location=order.pickup_location,
                    dl_task_status='pending',
                    dl_task_number=f'DL-{order.order_number}'
                )

                # Log the assignment
                orders_models.OrderVerificationLog.objects.create(
                    order=order,
                    verified_by=request.user,
                    action='driver_assigned',
                    old_status='None',
                    new_status=str(driver_id),
                    notes=f'Driver assigned from AI suggestion: {driver.user.get_full_name() if driver.user else driver.driver_code}'
                )

        driver_name = driver.user.get_full_name() if driver.user else driver.driver_code

        return JsonResponse({
            'success': True,
            'message': f'Driver {driver_name} assigned successfully',
            'driver_id': driver_id,
            'driver_name': driver_name
        })
    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'error': 'Invalid JSON data'
        }, status=400)
    except Exception as e:
        logger.exception("Error assigning driver to order %s: %s", order_id, str(e))
        return JsonResponse({
            'success': False,
            'error': 'An error occurred while assigning driver'
        }, status=400)


@require_http_methods(["POST"])
@login_required(login_url='/accounts/login/')
@staff_required
def update_order_zone(request, order_id):
    """Update order delivery zone (from AI parse result)"""
    try:
        order = get_object_or_404(
            orders_models.Order.objects.select_related('business'),
            id=order_id
        )
        data = json.loads(request.body)
        zone_number = data.get('zone_number')
        street_number = data.get('street_number')
        building_number = data.get('building_number')
        latitude = data.get('latitude')
        longitude = data.get('longitude')

        if not zone_number:
            return JsonResponse({
                'success': False,
                'error': 'Zone number is required'
            }, status=400)

        # Verify zone exists
        try:
            zone = delivery_models.ZoneName.objects.get(zone_number=zone_number, is_active=True)
        except delivery_models.ZoneName.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': f'Zone {zone_number} not found or inactive'
            }, status=400)

        # Update order zone and address fields
        old_zone = order.dl_zone
        order.dl_zone = zone_number
        if street_number:
            order.dl_street = str(street_number)
        if building_number:
            order.dl_building = str(building_number)
        order.save()

        # Update delivery task address (dl_to_address) with coordinates if available
        coords_saved = False
        if latitude and longitude:
            delivery_task = delivery_models.DeliveryTask.objects.filter(order=order).first()
            if delivery_task and delivery_task.dl_to_address:
                dl_address = delivery_task.dl_to_address
                dl_address.dl_latitude = latitude
                dl_address.dl_longitude = longitude
                dl_address.dl_zone = zone_number
                if street_number:
                    dl_address.dl_street = str(street_number)
                if building_number:
                    dl_address.dl_building = str(building_number)
                dl_address.save()
                coords_saved = True

        # Log the update
        notes = f'Zone updated from AI parse: {zone.zone_name}'
        if coords_saved:
            notes += f' | Coordinates saved: {latitude}, {longitude}'
        orders_models.OrderVerificationLog.objects.create(
            order=order,
            verified_by=request.user,
            action='zone_updated',
            old_status=str(old_zone) if old_zone else 'None',
            new_status=str(zone_number),
            notes=notes
        )

        return JsonResponse({
            'success': True,
            'message': f'Zone updated to {zone_number} ({zone.zone_name})' + (' with coordinates' if coords_saved else ''),
            'zone_number': zone_number,
            'zone_name': zone.zone_name,
            'coordinates_saved': coords_saved
        })
    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'error': 'Invalid JSON data'
        }, status=400)
    except Exception as e:
        logger.exception("Error updating zone for order %s: %s", order_id, str(e))
        return JsonResponse({
            'success': False,
            'error': 'An error occurred while updating zone'
        }, status=400)


# AJAX Endpoints for Orders List ------------------------------------------------------------------------------------------------------

@require_http_methods(["POST"])
@login_required(login_url='/accounts/login/')
@staff_required
def publish_order_to_delivery(request, order_id):
    """AJAX endpoint to publish order to delivery"""
    try:
        order = get_object_or_404(
            orders_models.Order.objects.select_related('business'),
            id=order_id
        )

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
        logger.exception("Error publishing order %s: %s", order_id, str(e))
        return JsonResponse({
            'success': False,
            'error': 'An error occurred while publishing order'
        }, status=400)


@require_http_methods(["POST"])
@login_required(login_url='/accounts/login/')
@staff_required
def update_order_status(request, order_id):
    """AJAX endpoint to update order status"""
    # Valid status values for validation
    VALID_ORDER_STATUSES = [
        'to_review', 'to_publish', 'published', 'processing', 'ready_to_pickup',
        'in_transit', 'delivered', 'failed', 'cancelled', 'returned', 'reported'
    ]
    VALID_TASK_STATUSES = [
        'pending', 'dl_task_listed', 'assigned', 'in_progress', 'completed',
        'failed', 'cancelled'
    ]

    try:
        order = get_object_or_404(
            orders_models.Order.objects.select_related('business'),
            id=order_id
        )

        # Parse JSON body
        data = json.loads(request.body)
        status = data.get('status')
        status_type = data.get('status_type', 'order')  # 'order' or 'task'

        if not status:
            return JsonResponse({
                'success': False,
                'error': 'Status is required'
            }, status=400)

        # Validate status_type
        if status_type not in ('order', 'task'):
            return JsonResponse({
                'success': False,
                'error': 'Invalid status_type. Must be "order" or "task"'
            }, status=400)

        # Validate status against allowed values
        if status_type == 'task' and status not in VALID_TASK_STATUSES:
            return JsonResponse({
                'success': False,
                'error': f'Invalid task status: {status}'
            }, status=400)
        elif status_type == 'order' and status not in VALID_ORDER_STATUSES:
            return JsonResponse({
                'success': False,
                'error': f'Invalid order status: {status}'
            }, status=400)

        old_status = order.order_status if status_type == 'order' else order.task_status

        # Update appropriate status field
        if status_type == 'task':
            order.task_status = status
        else:
            order.order_status = status
        order.save()

        # Log the status update
        from orders.models import OrderVerificationLog
        OrderVerificationLog.objects.create(
            order=order,
            verified_by=request.user,
            action=f'{status_type}_status_updated',
            notes=f'{status_type.title()} status changed from {old_status} to {status} by {request.user.username}',
        )

        return JsonResponse({
            'success': True,
            'message': f'Status updated to {status} successfully',
            'order_id': order.id,
            'new_status': status
        })
    except Exception as e:
        logger.exception("Error updating status for order %s: %s", order_id, str(e))
        return JsonResponse({
            'success': False,
            'error': 'An error occurred while updating order status'
        }, status=400)


@require_http_methods(["POST"])
@login_required(login_url='/accounts/login/')
@staff_required
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
    except Http404:
        raise
    except Exception as e:
        logger.exception("Error adding comment to order %s: %s", order_id, str(e))
        return JsonResponse({
            'success': False,
            'error': 'An error occurred while adding comment'
        }, status=400)


# Delivery Task Detail View ------------------------------------------------------------------------------------------------------

@login_required(login_url='/accounts/login/')
@staff_required
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

    # Status timeline from OrderStatusHistory
    status_history = orders_models.OrderStatusHistory.objects.filter(
        order=task.order
    ).select_related('changed_by').order_by('created_at')

    # Verification logs as fallback
    verification_logs = orders_models.OrderVerificationLog.objects.filter(
        order=task.order
    ).select_related('verified_by').order_by('-created_at')

    # Driver / DMS activity: delivery-related status changes
    driver_status_updates = orders_models.OrderStatusHistory.objects.filter(
        order=task.order,
        field_name__in=['dl_task_status', 'dl_task_status_dms']
    ).select_related('changed_by').order_by('created_at')

    # Driver uploads / documents
    try:
        from ezzy_api.models import TaskDocument
        driver_documents = TaskDocument.objects.filter(
            task=task
        ).select_related('uploaded_by').order_by('-created_at')
    except Exception:
        driver_documents = []

    # Seller / order comments
    seller_comments = orders_models.OrderComments.objects.filter(
        order=task.order
    ).order_by('-created_at')

    # Approved drivers for assignment modal
    approved_drivers = fleet_models.Driver.objects.filter(
        driver_status='approved'
    ).select_related('user').order_by('driver_code')

    context = {
        'page_title': f'Delivery Task #{task.dl_task_number}',
        'task': task,
        'status_history': status_history,
        'verification_logs': verification_logs,
        'driver_status_updates': driver_status_updates,
        'driver_documents': driver_documents,
        'seller_comments': seller_comments,
        'approved_drivers': approved_drivers,
    }

    return render(request, 'workforce/parts/delivery_task_detail.html', context)


# AJAX Endpoints for Delivery Tasks ------------------------------------------------------------------------------------------------------

@require_http_methods(["POST"])
@login_required(login_url='/accounts/login/')
@staff_required
def publish_task_to_dms(request, task_id):
    """AJAX endpoint to publish delivery task to DMS"""
    try:
        task = get_object_or_404(
            delivery_models.DeliveryTask.objects.select_related('order'), id=task_id)

        # Block if order is cancelled
        if task.order and task.order.order_status == 'cancelled':
            return JsonResponse({
                'success': False,
                'error': 'Cannot publish — order is cancelled'
            }, status=400)

        # Block if order is not verified
        if task.order and task.order.verification_status != 'verified':
            return JsonResponse({
                'success': False,
                'error': 'Cannot publish — order must be verified first'
            }, status=400)

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
        logger.exception("Error publishing task %s to DMS: %s", task_id, str(e))
        return JsonResponse({
            'success': False,
            'error': 'An error occurred while publishing task to DMS'
        }, status=400)


@require_http_methods(["POST"])
@login_required(login_url='/accounts/login/')
@staff_required
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
        logger.exception("Error publishing task %s to driver app: %s", task_id, str(e))
        return JsonResponse({
            'success': False,
            'error': 'An error occurred while publishing task to driver app'
        }, status=400)


@require_http_methods(["POST"])
@login_required(login_url='/accounts/login/')
@staff_required
def assign_driver_to_task(request, task_id):
    """AJAX endpoint to assign driver to delivery task"""
    try:
        task = get_object_or_404(
            delivery_models.DeliveryTask.objects.select_related('order'), id=task_id)

        # Block if order is cancelled
        if task.order and task.order.order_status == 'cancelled':
            return JsonResponse({
                'success': False,
                'error': 'Cannot assign driver — order is cancelled'
            }, status=400)

        # Block if order is not verified
        if task.order and task.order.verification_status != 'verified':
            return JsonResponse({
                'success': False,
                'error': 'Cannot assign driver — order must be verified first'
            }, status=400)

        # Parse JSON body
        data = json.loads(request.body)
        driver_id = data.get('driver_id')

        if not driver_id:
            return JsonResponse({
                'success': False,
                'error': 'Driver ID is required'
            }, status=400)

        # Get driver — must exist and be approved
        try:
            driver = fleet_models.Driver.objects.get(
                driver_id=driver_id, driver_status='approved')
        except fleet_models.Driver.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': f'Driver {driver_id} not found or not approved'
            }, status=400)

        task.driver = driver
        task.dl_task_status_dms = '0'  # Assigned
        task.save()

        driver_name = driver.user.get_full_name() if driver.user else driver.driver_code

        return JsonResponse({
            'success': True,
            'message': f'Driver {driver_name} assigned successfully',
            'task_id': task.id,
            'driver_id': driver.driver_id,
            'driver_name': driver_name
        })
    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'error': 'Invalid request data'
        }, status=400)
    except Exception as e:
        logger.exception("Error assigning driver to task %s: %s", task_id, str(e))
        return JsonResponse({
            'success': False,
            'error': f'An error occurred: {str(e)}'
        }, status=400)


@login_required(login_url='/accounts/login/')
@staff_required
def api_drivers_list(request):
    """API endpoint to get active drivers for dropdowns"""
    drivers = fleet_models.Driver.objects.select_related('user').filter(
        driver_status='approved'
    ).order_by('user__first_name')
    driver_list = []
    for d in drivers:
        name = d.user.get_full_name() or d.user.username
        driver_list.append({'id': d.pk, 'name': name})  # Use d.pk instead of d.id (driver_id is PK)
    return JsonResponse({'drivers': driver_list})


@require_http_methods(["POST"])
@login_required(login_url='/accounts/login/')
@staff_required
def update_task_status(request, task_id):
    """AJAX endpoint to update delivery task status"""
    VALID_STATUSES = [
        'for_review', 'pending', 'assigned', 'accepted', 'picked_up',
        'start_ride', 'out_for_delivery', 'in_transit', 'contacted',
        'non_reachable', 'delivered', 'failed', 'rejected', 'cancelled',
    ]
    try:
        task = get_object_or_404(
            delivery_models.DeliveryTask.objects.select_related('order'),
            id=task_id
        )

        # Lock check: Prevent status change on settled tasks
        if task.dl_task_status_dms == '2' and task.order and task.order.cod_status_by_staff == 'cod_settled_with_business':
            return JsonResponse({
                'success': False,
                'error': 'Task is locked. Status cannot be changed after delivery is successful and COD is settled.'
            }, status=403)

        # Parse JSON body
        data = json.loads(request.body)
        status = data.get('status')

        if not status:
            return JsonResponse({
                'success': False,
                'error': 'Status is required'
            }, status=400)

        if status not in VALID_STATUSES:
            return JsonResponse({
                'success': False,
                'error': f'Invalid status: {status}'
            }, status=400)

        # Map internal status to client-facing status
        STATUS_TO_CLIENT = {
            'for_review': 'for_review',
            'pending': 'for_review',
            'assigned': '0',
            'accepted': '0',
            'picked_up': '0',
            'start_ride': '0',
            'out_for_delivery': '0',
            'in_transit': '0',
            'contacted': '0',
            'non_reachable': '0',
            'delivered': '2',
            'failed': 'rejected',
            'rejected': 'rejected',
            'cancelled': '9',
        }

        # Optional fields
        driver_id = data.get('driver_id')
        notes = data.get('notes', '')
        time_str = data.get('time', '')

        # Update both task status fields
        task.dl_task_status = status
        update_fields = ['dl_task_status']

        client_status = STATUS_TO_CLIENT.get(status)
        if client_status:
            task.dl_task_status_client = client_status
            update_fields.append('dl_task_status_client')

        # Assign driver if provided
        if driver_id:
            try:
                driver = fleet_models.Driver.objects.get(id=driver_id)
                task.driver = driver
                update_fields.append('driver')
            except fleet_models.Driver.DoesNotExist:
                pass
        elif driver_id == '':
            # Explicitly unassign driver
            task.driver = None
            update_fields.append('driver')

        # Set completed_at timestamp for delivered status
        if status == 'delivered' and not task.completed_at:
            if time_str:
                from django.utils.dateparse import parse_datetime
                parsed = parse_datetime(time_str)
                if parsed:
                    if timezone.is_naive(parsed):
                        parsed = timezone.make_aware(parsed)
                    task.completed_at = parsed
                    update_fields.append('completed_at')
            else:
                task.completed_at = timezone.now()
                update_fields.append('completed_at')

        # Save notes to the order if provided
        if notes and task.order:
            task.order.order_notes = notes
            task.order.save(update_fields=['order_notes'])

        task.save(update_fields=update_fields)

        return JsonResponse({
            'success': True,
            'message': f'Task status updated to {status} successfully',
            'task_id': task.id,
            'new_status': status
        })
    except Exception as e:
        logger.exception("Error updating task %s status: %s", task_id, str(e))
        return JsonResponse({
            'success': False,
            'error': 'An error occurred while updating task status'
        }, status=400)


# USER VERIFICATION VIEWS --------------------------------------------------------------------------------------------------------------

@login_required(login_url='/accounts/login/')
@staff_required
@ensure_csrf_cookie
def user_verification_list(request):
    """Staff view to see all users pending verification"""
    from core import models as core_models
    from business import models as business_models
    from django.db.models import Count

    # Get status counts for filter tabs
    status_counts = dict(
        core_models.Profile.objects.values_list('verification_status')
        .annotate(cnt=Count('id'))
        .values_list('verification_status', 'cnt')
    )
    total_count = sum(status_counts.values())

    # Get all profiles based on filter
    verification_filter = request.GET.get('status', 'all')

    profiles = core_models.Profile.objects.select_related('user')
    if verification_filter in ('pending', 'under_review', 'verified', 'rejected', 'incomplete'):
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

    # Bulk fetch team memberships
    from collections import defaultdict
    team_memberships_by_user = defaultdict(list)
    team_profiles = business_models.BusinessTeamProfile.objects.select_related('business').filter(
        user_id__in=user_ids
    )
    for tp in team_profiles:
        team_memberships_by_user[tp.user_id].append(tp)

    # Build verification data efficiently
    verification_data = []
    for profile in profile_list:
        team_list = team_memberships_by_user.get(profile.user_id, [])
        # Build JSON for pending team memberships (accepted by user, awaiting staff verification)
        pending_teams_json = json.dumps([
            {'id': tm.id, 'biz': tm.business.business_name, 'role': tm.get_team_role_display()}
            for tm in team_list
            if tm.team_status == 'pending' and tm.team_verifed
        ])
        data = {
            'profile': profile,
            'business': businesses_by_user.get(profile.user_id) if profile.is_business else None,
            'driver': drivers_by_user.get(profile.user_id) if profile.is_driver else None,
            'user': profile.user,
            'team_memberships': team_list,
            'pending_teams_json': pending_teams_json,
        }
        verification_data.append(data)

    context = {
        'verification_data': verification_data,
        'current_filter': verification_filter,
        'total_count': total_count,
        'status_counts': status_counts,
    }

    return render(request, 'workforce/user_verification_list.html', context)


@require_http_methods(["POST"])
@login_required(login_url='/accounts/login/')
@staff_required
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
            profile.is_profile_completed = True

            # Update business or driver status to active
            if profile.is_business:
                profile.is_business_profile_completed = True
                try:
                    from business import models as business_models
                    business = business_models.Business.objects.get(user=profile.user)
                    business.business_status = 'active'
                    business.save()
                except business_models.Business.DoesNotExist:
                    pass

            if profile.is_driver:
                profile.is_driver_profile_completed = True
                try:
                    driver = fleet_models.Driver.objects.get(user=profile.user)
                    driver.driver_status = 'approved'
                    driver.save()
                except fleet_models.Driver.DoesNotExist:
                    pass

            # Activate team memberships if requested
            activate_teams = data.get('activate_teams', [])
            if activate_teams:
                from business import models as business_models
                business_models.BusinessTeamProfile.objects.filter(
                    id__in=activate_teams,
                    user=profile.user,
                    team_status='pending',
                    team_verifed=True
                ).update(team_status='active')

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
    except Http404:
        raise
    except Exception as e:
        logger.exception("Error updating verification status for profile %s: %s", profile_id, str(e))
        return JsonResponse({
            'success': False,
            'error': f'Error: {type(e).__name__}: {str(e)}'
        }, status=400)


@require_http_methods(["POST"])
@login_required(login_url='/accounts/login/')
@staff_required
def update_team_status(request, team_id):
    """AJAX endpoint to update team membership status"""
    from business import models as business_models
    try:
        team_profile = get_object_or_404(business_models.BusinessTeamProfile, id=team_id)
        data = json.loads(request.body)
        new_status = data.get('status')

        valid_statuses = ['active', 'pending', 'inactive', 'suspended', 'rejected']
        if new_status not in valid_statuses:
            return JsonResponse({
                'success': False,
                'error': f'Invalid status. Must be one of: {", ".join(valid_statuses)}'
            }, status=400)

        old_status = team_profile.team_status
        team_profile.team_status = new_status

        # When activating, also mark as verified
        if new_status == 'active':
            team_profile.team_verifed = True

        team_profile.save()

        logger.info(
            "Team membership %s status changed from '%s' to '%s' by staff user %s",
            team_id, old_status, new_status, request.user.id
        )

        return JsonResponse({
            'success': True,
            'message': f'Team status updated to {new_status}',
            'team_id': team_id,
            'new_status': new_status
        })
    except Http404:
        raise
    except Exception as e:
        logger.exception("Error updating team status for team %s: %s", team_id, str(e))
        return JsonResponse({
            'success': False,
            'error': f'Error: {type(e).__name__}: {str(e)}'
        }, status=400)


# ADDITIONAL SIDEBAR FUNCTIONS --------------------------------------------------------------------------------------------------------------

# Orders Section Functions
@login_required(login_url='/accounts/login/')
@staff_required
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
@staff_required
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
            messages.error(request, 'An error occurred while matching. Please try again.')
            logger.exception("Error matching task %s to DMS ID %s: %s", delivery_task_number, dms_job_id, str(e))

    return redirect('workforce:wf_orders_dms_updated')


@login_required(login_url='/accounts/login/')
@staff_required
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
@staff_required
def tasks_followup_list(request):
    """View for follow-up tasks list"""
    tasks_list = delivery_models.DeliveryTask.objects.select_related(
        'order', 'driver', 'business', 'pickup_location', 'order__business'
    ).prefetch_related(
        'order__order_items',
    ).filter(
        dl_task_status='pending'
    ).order_by('-created_at')

    tasks_with_pagination = paginate_queryset(request, tasks_list, items_per_page=20)

    context = {
        'dl_tasks': tasks_with_pagination,
        'page_title': 'Follow-Up Tasks',
        'page_subtitle': 'Tasks requiring follow-up',
        'page_icon': 'fa-flag',
        'list_type': 'followup',
    }
    return render(request, 'workforce/parts/lists/dl_list_all.html', context)


@login_required(login_url='/accounts/login/')
@staff_required
def tasks_dms_updated(request):
    """View for DMS updated tasks list"""
    tasks_list = delivery_models.DeliveryTask.objects.select_related(
        'order', 'driver', 'business', 'pickup_location', 'order__business'
    ).prefetch_related(
        'order__order_items',
    ).filter(
        dl_task_status_dms__isnull=False
    ).order_by('-created_at')

    tasks_with_pagination = paginate_queryset(request, tasks_list, items_per_page=20)

    context = {
        'dl_tasks': tasks_with_pagination,
        'page_title': 'DMS Updated Tasks',
        'page_subtitle': 'Tasks with DMS status updates',
        'page_icon': 'fa-cloud',
        'list_type': 'dms_updated',
    }
    return render(request, 'workforce/parts/lists/dl_list_all.html', context)


@login_required(login_url='/accounts/login/')
@staff_required
def tasks_reported(request):
    """View for reported tasks list - showing rejected/cancelled tasks"""
    tasks_list = delivery_models.DeliveryTask.objects.select_related(
        'order', 'driver', 'business', 'pickup_location', 'order__business'
    ).prefetch_related(
        'order__order_items',
    ).filter(
        dl_task_status__in=['rejected', 'cancelled']
    ).order_by('-created_at')

    tasks_with_pagination = paginate_queryset(request, tasks_list, items_per_page=20)

    context = {
        'dl_tasks': tasks_with_pagination,
        'page_title': 'Reported Tasks',
        'page_subtitle': 'Rejected and cancelled tasks',
        'page_icon': 'fa-triangle-exclamation',
        'list_type': 'reported',
    }
    return render(request, 'workforce/parts/lists/dl_list_all.html', context)


# DMS Links Section Functions
@login_required(login_url='/accounts/login/')
@staff_required
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


# Finance Dashboard Section Functions
@login_required(login_url='/accounts/login/')
@staff_required
def workforce_finance_dashboard(request):
    """Comprehensive finance dashboard for workforce staff"""
    from django.db.models import Sum, Count, Q, F
    from decimal import Decimal
    from datetime import timedelta

    try:
        days = int(request.GET.get('days', 30))
        if days < 1 or days > 365:
            days = 30
    except (ValueError, TypeError):
        days = 30
    start_date = timezone.now() - timedelta(days=days)

    # All drivers summary
    drivers = fleet_models.Driver.objects.filter(
        driver_status='approved'
    ).select_related('user')

    driver_totals = drivers.aggregate(
        total_wallet=Sum('wallet_balance'),
        total_cod_in_hand=Sum('cod_in_hand'),
        total_pending_earnings=Sum('pending_earnings'),
        total_credit_limit=Sum('credit_limit'),
    )

    # Transaction summary for the period
    txns = fleet_models.DriverTransaction.objects.filter(created_at__gte=start_date)

    # COD pipeline
    cod_collected = abs(txns.filter(
        transaction_type='cod_collection'
    ).aggregate(total=Sum('amount'))['total'] or Decimal('0'))

    cod_driver_settled = abs(txns.filter(
        transaction_type__in=['cod_deposit', 'cod_driver_settle']
    ).aggregate(total=Sum('amount'))['total'] or Decimal('0'))

    cod_client_settled = abs(txns.filter(
        transaction_type='cod_client_settle'
    ).aggregate(total=Sum('amount'))['total'] or Decimal('0'))

    cod_returned = abs(txns.filter(
        transaction_type='cod_return'
    ).aggregate(total=Sum('amount'))['total'] or Decimal('0'))

    # Additional COD metrics
    # COD in Bank (deposited by drivers)
    cod_in_bank = abs(txns.filter(
        transaction_type='cod_deposit'
    ).aggregate(total=Sum('amount'))['total'] or Decimal('0'))

    # COD to Settle = Total collected - Driver settled - Client settled
    cod_to_settle = cod_collected - cod_driver_settled - cod_client_settled
    if cod_to_settle < 0:
        cod_to_settle = Decimal('0')

    # Earnings & settlements
    earnings_total = txns.filter(
        transaction_type='earning'
    ).aggregate(total=Sum('amount'))['total'] or Decimal('0')

    settlements_total = abs(txns.filter(
        transaction_type='settlement'
    ).aggregate(total=Sum('amount'))['total'] or Decimal('0'))

    # Charges summary
    charges_summary = txns.filter(
        transaction_type__in=['delivery_charge', 'fulfillment_charge', 'inventory_handling', 'other_charge']
    ).values('transaction_type').annotate(
        total=Sum('amount'),
        count=Count('id')
    )

    total_charges = sum(abs(c['total']) for c in charges_summary) if charges_summary else Decimal('0')

    # Bills payable / receivable
    bills_payable = abs(txns.filter(
        transaction_type='bills_payable'
    ).aggregate(total=Sum('amount'))['total'] or Decimal('0'))

    bills_receivable = abs(txns.filter(
        transaction_type='bills_receivable'
    ).aggregate(total=Sum('amount'))['total'] or Decimal('0'))

    # Drivers with highest COD in hand (top 10)
    top_cod_drivers = drivers.filter(
        cod_in_hand__gt=0
    ).order_by('-cod_in_hand')[:10]

    # Recent transactions (last 20)
    recent_transactions = txns.select_related(
        'driver__user', 'delivery_task', 'business'
    ).order_by('-created_at')[:20]

    # Transaction counts by type
    type_breakdown = txns.values('transaction_type').annotate(
        count=Count('id'),
        total=Sum('amount')
    ).order_by('-count')

    # Performance metrics - Delivery statistics
    from orders import models as orders_models

    # Total completed deliveries in period
    total_deliveries = orders_models.Order.objects.filter(
        order_status__in=['delivered', 'fulfilled'],
        delivered_at__gte=start_date
    ).count()

    # Failed deliveries in period
    failed_deliveries = orders_models.Order.objects.filter(
        order_status__in=['failed', 'cancelled'],
        updated_at__gte=start_date
    ).count()

    # Total delivery fees collected
    total_delivery_fees = orders_models.Order.objects.filter(
        delivered_at__gte=start_date,
        order_status__in=['delivered', 'fulfilled']
    ).aggregate(total=Sum('dl_amount'))['total'] or Decimal('0')

    # Average delivery value (COD + DL amount)
    avg_delivery_stats = orders_models.Order.objects.filter(
        delivered_at__gte=start_date,
        order_status__in=['delivered', 'fulfilled']
    ).aggregate(
        total_cod=Sum('cod_amount'),
        total_dl=Sum('dl_amount'),
        count=Count('id')
    )

    avg_delivery_value = Decimal('0')
    if avg_delivery_stats['count'] and avg_delivery_stats['count'] > 0:
        total_value = (avg_delivery_stats['total_cod'] or Decimal('0')) + (avg_delivery_stats['total_dl'] or Decimal('0'))
        avg_delivery_value = total_value / avg_delivery_stats['count']

    # Active drivers (drivers with at least one delivery in period)
    active_drivers = orders_models.Order.objects.filter(
        delivered_at__gte=start_date,
        order_status__in=['delivered', 'fulfilled']
    ).values('delivery_task__driver').distinct().count()

    # Success rate calculation
    total_attempts = total_deliveries + failed_deliveries
    success_rate = Decimal('0')
    if total_attempts > 0:
        success_rate = (Decimal(total_deliveries) / Decimal(total_attempts)) * 100

    # COD with Fleet metrics
    active_drivers_count = drivers.count()
    drivers_with_cod_count = drivers.filter(cod_in_hand__gt=0).count()

    context = {
        'selected_days': days,
        'driver_totals': driver_totals,
        'driver_count': drivers.count(),
        'active_drivers_count': active_drivers_count,
        'drivers_with_cod_count': drivers_with_cod_count,
        'cod_collected': cod_collected,
        'cod_driver_settled': cod_driver_settled,
        'cod_client_settled': cod_client_settled,
        'cod_returned': cod_returned,
        'cod_in_bank': cod_in_bank,
        'cod_to_settle': cod_to_settle,
        'earnings_total': earnings_total,
        'settlements_total': settlements_total,
        'charges_summary': charges_summary,
        'total_charges': total_charges,
        'bills_payable': bills_payable,
        'bills_receivable': bills_receivable,
        'top_cod_drivers': top_cod_drivers,
        'recent_transactions': recent_transactions,
        'type_breakdown': type_breakdown,
        # Performance metrics
        'total_deliveries': total_deliveries,
        'failed_deliveries': failed_deliveries,
        'total_delivery_fees': total_delivery_fees,
        'avg_delivery_value': avg_delivery_value,
        'active_drivers': active_drivers,
        'success_rate': success_rate,
    }

    return render(request, 'workforce/workforce_finance_dashboard.html', context)


# Fleet Accounts Section Functions
@login_required(login_url='/accounts/login/')
@staff_required
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

    # If date filter is applied, calculate COD collected in that period per driver
    if date_from or date_to:
        # Get drivers with COD collected in the date range
        from django.db.models import OuterRef, Subquery

        # Build subquery with date filter - use cod_collected_at for filtering
        cod_subquery = delivery_models.DeliveryTask.objects.filter(
            driver_id=OuterRef('driver_id'),
            cod_collected=True,
        )

        # Apply date filters on cod_collected_at date
        if date_from:
            cod_subquery = cod_subquery.filter(cod_collected_at__date__gte=date_from)
        if date_to:
            cod_subquery = cod_subquery.filter(cod_collected_at__date__lte=date_to)

        cod_subquery = cod_subquery.values('driver').annotate(
            total=Sum('cod_collected_amount')
        ).values('total')

        # Show all drivers (not just approved) for COD tracking
        drivers = fleet_models.Driver.objects.all().select_related('user').annotate(
            period_cod=Coalesce(
                Subquery(cod_subquery),
                Value(0),
                output_field=DecimalField()
            )
        )
    else:
        # No date filter - show current cod_in_hand
        from django.db.models import F
        # Show all drivers (not just approved) for COD tracking
        drivers = fleet_models.Driver.objects.all().select_related('user').annotate(
            period_cod=F('cod_in_hand')
        )

    # COD filter (yes/no/custom) - filters on period_cod (which is either cod_in_hand or calculated from date range)
    cod_filter = request.GET.get('cod_filter', '')
    min_amount = request.GET.get('min_amount', '')
    max_amount = request.GET.get('max_amount', '')

    if cod_filter == 'yes':
        # Filter drivers who have COD (using period_cod annotation)
        drivers = drivers.filter(period_cod__gt=0)
    elif cod_filter == 'no':
        # Filter drivers with no COD
        from django.db.models import Q
        drivers = drivers.filter(Q(period_cod=0) | Q(period_cod__isnull=True))
    elif cod_filter == 'custom':
        # Filter by custom amount range on period_cod
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

    # Calculate totals and statistics
    from django.db.models import Avg, Max, Count

    total_cod = drivers.aggregate(total=Sum('period_cod'))['total'] or 0
    pending_settlements = drivers.filter(period_cod__gt=0).count()

    # Additional statistics
    avg_cod = drivers.filter(period_cod__gt=0).aggregate(avg=Avg('period_cod'))['avg'] or 0
    max_cod = drivers.aggregate(max=Max('period_cod'))['max'] or 0

    # Count drivers by COD range
    cod_ranges = {
        'under_500': drivers.filter(period_cod__gt=0, period_cod__lt=500).count(),
        'between_500_2000': drivers.filter(period_cod__gte=500, period_cod__lt=2000).count(),
        'above_2000': drivers.filter(period_cod__gte=2000).count(),
    }

    # Total drivers in system (not just those with COD)
    total_drivers = fleet_models.Driver.objects.filter(driver_status='approved').count()

    # View mode (grid or list) - default to list
    view_mode = request.GET.get('view', 'list')

    # Build filter params for pagination (exclude page and per_page as they're handled separately)
    filter_params = request.GET.copy()
    if 'page' in filter_params:
        del filter_params['page']
    if 'per_page' in filter_params:
        del filter_params['per_page']

    drivers_with_pagination = paginate_queryset(request, drivers, items_per_page=20)

    context = {
        'drivers': drivers_with_pagination,
        'page_title': 'COD In Hand',
        'total_cod': total_cod,
        'pending_settlements': pending_settlements,
        'avg_cod': avg_cod,
        'max_cod': max_cod,
        'cod_ranges': cod_ranges,
        'total_drivers': total_drivers,
        'filter_params': filter_params.urlencode(),
        'per_page': get_per_page(request, default=20),
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
@staff_required
def fleet_drivers_earnings(request):
    """View for drivers earnings"""
    drivers = fleet_models.Driver.objects.filter(
        driver_status='approved'
    ).select_related('user').order_by('user__first_name')

    drivers_with_pagination = paginate_queryset(request, drivers, items_per_page=20)

    context = {
        'drivers': drivers_with_pagination,
        'page_title': 'Drivers Earnings',
    }
    return render(request, 'workforce/fleet_drivers_earnings.html', context)


@login_required(login_url='/accounts/login/')
@staff_required
def earnings_verification(request):
    """
    Staff view to verify and publish driver earnings.
    Shows completed deliveries with pending earnings verification.
    Allows bulk verify/publish with editable earnings.
    """
    from django.db.models import Sum, Case, When, DecimalField, F
    from delivery import models as delivery_models
    from datetime import timedelta

    # Filters
    driver_id = request.GET.get('driver', '')
    status_filter = request.GET.get('status', 'pending')
    try:
        days = int(request.GET.get('days', 7))
        if days < 1 or days > 365:
            days = 7
    except (ValueError, TypeError):
        days = 7

    start_date = timezone.now() - timedelta(days=days)

    # Base queryset - completed deliveries with COD collected
    tasks = delivery_models.DeliveryTask.objects.filter(
        dl_task_status='delivered',
        dl_task_date__gte=start_date.date(),
        cod_collected=True  # Only show deliveries where COD has been collected
    ).select_related(
        'driver', 'driver__user', 'order', 'order__business',
        'pickup_location', 'dl_to_address', 'earnings_verified_by'
    ).order_by('-completed_at', '-id')

    # Apply filters
    if driver_id:
        tasks = tasks.filter(driver_id=driver_id)

    if status_filter and status_filter != 'all':
        tasks = tasks.filter(earnings_verification_status=status_filter)

    # Calculate stats
    stats = {
        'pending_count': tasks.filter(earnings_verification_status='pending').count(),
        'verified_count': tasks.filter(earnings_verification_status='verified').count(),
        'published_count': tasks.filter(earnings_verification_status='published').count(),
        'total_pending_earnings': tasks.filter(
            earnings_verification_status='pending'
        ).aggregate(
            total=Sum(Case(
                When(calculated_earnings__isnull=False, then='calculated_earnings'),
                When(driver_earnings__isnull=False, then='driver_earnings'),
                default='dl_price',
                output_field=DecimalField(max_digits=10, decimal_places=2)
            ))
        )['total'] or 0,
    }

    # Get approved drivers for filter dropdown
    drivers = fleet_models.Driver.objects.filter(
        driver_status='approved'
    ).select_related('user').order_by('user__first_name')

    # Paginate
    tasks_paginated = paginate_queryset(request, tasks, items_per_page=50)

    context = {
        'tasks': tasks_paginated,
        'drivers': drivers,
        'stats': stats,
        'selected_driver': driver_id,
        'selected_status': status_filter,
        'selected_days': days,
        'page_title': 'Earnings Verification',
    }
    return render(request, 'workforce/earnings_verification.html', context)


@login_required(login_url='/accounts/login/')
@staff_required
def earnings_verification_action(request):
    """
    Process bulk earnings verification actions.
    Actions: verify, publish, reject, update_amount
    """
    from django.http import JsonResponse
    from delivery import models as delivery_models
    from decimal import Decimal, InvalidOperation

    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    action = request.POST.get('action', '')
    task_ids = request.POST.getlist('task_ids[]')
    earnings_updates = request.POST.get('earnings_updates', '{}')

    if not task_ids:
        return JsonResponse({'error': 'No tasks selected'}, status=400)

    try:
        import json
        earnings_dict = json.loads(earnings_updates) if earnings_updates else {}
    except json.JSONDecodeError:
        earnings_dict = {}

    updated_count = 0
    errors = []

    # Fetch all tasks at once to avoid N+1 queries
    tasks_queryset = delivery_models.DeliveryTask.objects.select_related('driver').filter(id__in=task_ids)
    tasks_dict = {str(task.id): task for task in tasks_queryset}

    for task_id in task_ids:
        try:
            task = tasks_dict.get(str(task_id))
            if not task:
                errors.append(f"Task {task_id} not found")
                continue

            # Update earnings amount if provided
            if str(task_id) in earnings_dict:
                try:
                    new_amount = Decimal(str(earnings_dict[str(task_id)]))
                    task.verified_earnings = new_amount
                except (ValueError, InvalidOperation):
                    errors.append(f"Invalid amount for task {task_id}")
                    continue

            if action == 'verify':
                task.earnings_verification_status = 'verified'
                task.earnings_verified_by = request.user
                task.earnings_verified_at = timezone.now()
                # Set verified_earnings to calculated amount if not already set
                if not task.verified_earnings:
                    task.verified_earnings = task.calculate_driver_earnings()
                task.save()
                updated_count += 1

            elif action == 'publish':
                # Can only publish verified tasks
                if task.earnings_verification_status not in ['verified', 'pending']:
                    errors.append(f"Task {task_id} cannot be published")
                    continue

                task.earnings_verification_status = 'published'
                task.earnings_published_at = timezone.now()
                if not task.earnings_verified_by:
                    task.earnings_verified_by = request.user
                    task.earnings_verified_at = timezone.now()

                # Update driver_earnings with verified amount
                final_earnings = task.verified_earnings or task.calculate_driver_earnings()
                task.driver_earnings = final_earnings
                task.save()

                # Update driver's pending_earnings atomically using F() and Coalesce to prevent race conditions
                if task.driver:
                    from django.db.models import F
                    from django.db.models.functions import Coalesce
                    fleet_models.Driver.objects.filter(driver_id=task.driver.driver_id).update(
                        pending_earnings=Coalesce(F('pending_earnings'), Decimal('0')) + Decimal(str(final_earnings))
                    )

                updated_count += 1

            elif action == 'reject':
                task.earnings_verification_status = 'rejected'
                task.earnings_verified_by = request.user
                task.earnings_verified_at = timezone.now()
                task.save()
                updated_count += 1

            elif action == 'update':
                # Just update the earnings amount
                task.save()
                updated_count += 1

        except Exception as e:
            logger.exception("Error processing task %s: %s", task_id, str(e))
            errors.append(f"Error processing task {task_id}")

    return JsonResponse({
        'success': True,
        'updated': updated_count,
        'errors': errors,
        'message': f'{updated_count} task(s) updated successfully'
    })


@login_required(login_url='/accounts/login/')
@staff_required
def cod_settlement_report(request):
    """COD Settlement Report - Select drivers, settle COD, export PDF"""
    from django.db.models import Sum, F
    from delivery import models as delivery_models
    from datetime import timedelta

    # Date filters
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')

    today = timezone.now().date()
    if not date_from:
        date_from = (today - timedelta(days=7)).isoformat()
    if not date_to:
        date_to = today.isoformat()

    # Get drivers with unsettled COD (all drivers, not just approved)
    drivers = fleet_models.Driver.objects.filter(
        cod_in_hand__gt=0
    ).select_related('user').order_by('-cod_in_hand')

    # Get unsettled COD deliveries grouped by driver
    unsettled_tasks = delivery_models.DeliveryTask.objects.filter(
        cod_collected=True,
        dl_task_status='delivered',
        order__cod_status_by_staff='cod_with_driver'
    ).select_related('driver', 'driver__user', 'order').order_by('-completed_at')

    # Apply date filter if provided
    if date_from:
        unsettled_tasks = unsettled_tasks.filter(completed_at__date__gte=date_from)
    if date_to:
        unsettled_tasks = unsettled_tasks.filter(completed_at__date__lte=date_to)

    # Calculate totals
    total_unsettled = drivers.aggregate(total=Sum('cod_in_hand'))['total'] or 0
    drivers_with_cod = drivers.count()

    context = {
        'drivers': drivers,
        'unsettled_tasks': unsettled_tasks[:100],
        'page_title': 'COD Settlement Report',
        'total_unsettled': total_unsettled,
        'drivers_with_cod': drivers_with_cod,
        'date_from': date_from,
        'date_to': date_to,
    }
    return render(request, 'workforce/cod_settlement_report.html', context)


@login_required(login_url='/accounts/login/')
@staff_required
def cod_settlement_action(request):
    """Process COD settlement for selected drivers"""
    from django.http import JsonResponse
    from django.db import transaction
    from fleet.wallet_service import WalletService

    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    driver_ids = request.POST.getlist('driver_ids[]')
    payment_method = request.POST.get('payment_method', 'cash')
    reference = request.POST.get('reference', '')

    if not driver_ids:
        return JsonResponse({'error': 'No drivers selected'}, status=400)

    # Limit number of drivers to prevent DoS
    if len(driver_ids) > 50:
        return JsonResponse({'error': 'Maximum 50 drivers can be settled at once'}, status=400)

    wallet_service = WalletService()
    settled_drivers = []
    total_settled = 0

    for driver_id in driver_ids:
        try:
            # Use transaction.atomic and select_for_update to prevent race conditions
            with transaction.atomic():
                driver = fleet_models.Driver.objects.select_for_update().get(driver_id=driver_id)
                cod_amount = driver.cod_in_hand

                if cod_amount > 0:
                    # Record COD deposit transaction with payment method
                    # Pass no delivery_ids so submit_cod_to_admin settles oldest tasks automatically
                    wallet_service.submit_cod_to_admin(
                        driver=driver,
                        amount=cod_amount,
                        created_by=request.user,
                        reference_number=reference,
                        payment_method=payment_method,
                        notes=f"COD settlement via {payment_method}"
                    )
                    settled_drivers.append({
                        'name': driver.driver_name,
                        'amount': float(cod_amount),
                        'payment_method': payment_method
                    })
                    total_settled += cod_amount
        except fleet_models.Driver.DoesNotExist:
            continue

    return JsonResponse({
        'success': True,
        'settled_count': len(settled_drivers),
        'total_settled': float(total_settled),
        'settled_drivers': settled_drivers,
        'payment_method': payment_method
    })


@login_required(login_url='/accounts/login/')
@staff_required
def cod_settlement_pdf(request):
    """Generate PDF report for COD settlement"""
    from django.http import HttpResponse
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch, mm
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from io import BytesIO
    from django.db.models import Sum

    driver_ids = request.GET.getlist('driver_ids')

    # Get selected drivers or all with COD
    if driver_ids:
        drivers = fleet_models.Driver.objects.filter(
            driver_id__in=driver_ids,
            cod_in_hand__gt=0
        ).select_related('user').order_by('-cod_in_hand')
    else:
        drivers = fleet_models.Driver.objects.filter(
            driver_status='approved',
            cod_in_hand__gt=0
        ).select_related('user').order_by('-cod_in_hand')

    # Create PDF
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=20*mm, leftMargin=20*mm, topMargin=20*mm, bottomMargin=20*mm)
    elements = []
    styles = getSampleStyleSheet()

    # Title
    title_style = ParagraphStyle('Title', parent=styles['Heading1'], fontSize=18, alignment=1, spaceAfter=20)
    elements.append(Paragraph('COD Settlement Report', title_style))
    elements.append(Paragraph(f'Date: {timezone.now().strftime("%d %b %Y, %H:%M")}', styles['Normal']))
    elements.append(Spacer(1, 20))

    # Summary
    total_cod = drivers.aggregate(total=Sum('cod_in_hand'))['total'] or 0
    summary_style = ParagraphStyle('Summary', parent=styles['Normal'], fontSize=12, spaceAfter=10)
    elements.append(Paragraph(f'<b>Total Drivers:</b> {drivers.count()}', summary_style))
    elements.append(Paragraph(f'<b>Total COD to Collect:</b> {total_cod} QR', summary_style))
    elements.append(Spacer(1, 20))

    # Table data
    data = [['#', 'Driver Name', 'Driver ID', 'Phone', 'COD Amount (QR)']]
    for i, driver in enumerate(drivers, 1):
        data.append([
            str(i),
            driver.driver_name,
            driver.driver_id,
            driver.driver_mobile or '-',
            f'{driver.cod_in_hand:.2f}'
        ])

    # Add total row
    data.append(['', '', '', 'TOTAL:', f'{total_cod:.2f}'])

    # Create table
    table = Table(data, colWidths=[30, 120, 80, 90, 90])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#001f3f')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -2), colors.white),
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#f0f0f0')),
        ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
        ('TEXTCOLOR', (0, 1), (-1, -1), colors.black),
        ('FONTSIZE', (0, 1), (-1, -1), 9),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('ALIGN', (-1, 1), (-1, -1), 'RIGHT'),
    ]))
    elements.append(table)

    # Signature section
    elements.append(Spacer(1, 40))
    sig_data = [
        ['Staff Signature:', '_' * 30, 'Driver Signature:', '_' * 30],
        ['Name:', '_' * 30, 'Name:', '_' * 30],
        ['Date:', '_' * 30, 'Date:', '_' * 30],
    ]
    sig_table = Table(sig_data, colWidths=[80, 130, 80, 130])
    sig_table.setStyle(TableStyle([
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('TOPPADDING', (0, 0), (-1, -1), 15),
    ]))
    elements.append(sig_table)

    doc.build(elements)

    # Return PDF response
    buffer.seek(0)
    response = HttpResponse(buffer, content_type='application/pdf')
    filename = f'cod_settlement_{timezone.now().strftime("%Y%m%d_%H%M")}.pdf'
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


@login_required(login_url='/accounts/login/')
@staff_required
def fleet_transactions(request):
    """View for fleet transactions with filtering and sorting"""
    from django.db.models import Sum
    from decimal import Decimal
    from datetime import timedelta

    # Get all approved drivers for filter dropdown
    all_drivers = fleet_models.Driver.objects.filter(
        driver_status='approved'
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

    # Default to cod_collection if no type filter specified
    txn_type = request.GET.get('type', 'cod_collection') if 'type' not in request.GET else request.GET.get('type')
    status = request.GET.get('status', '')
    min_amount = request.GET.get('min_amount', '')
    max_amount = request.GET.get('max_amount', '')

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
    deposited_refs = set()

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

    # Build filter params for pagination (exclude page and per_page as they're handled separately)
    filter_params = request.GET.copy()
    if 'page' in filter_params:
        del filter_params['page']
    if 'per_page' in filter_params:
        del filter_params['per_page']

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
        'deposited_refs': deposited_refs,
        'filter_params': filter_params.urlencode(),
        'per_page': get_per_page(request, default=20),
        # Filter values for form
        'date_preset': date_preset,
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
@staff_required
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
        wallet_balance -= cod_amount  # COD collection decreases wallet
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
        deposit_amount = min(deposit_amount, cod_in_hand)  # Can't deposit more than in hand
        cod_in_hand = max(Decimal('0.00'), cod_in_hand - deposit_amount)
        wallet_balance += deposit_amount  # COD deposit increases wallet

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

    # Update driver's current balances including wallet_balance
    driver.cod_in_hand = cod_in_hand
    driver.pending_earnings = pending_earnings
    driver.wallet_balance = wallet_balance
    driver.save(update_fields=['cod_in_hand', 'pending_earnings', 'wallet_balance'])

    messages.success(request, f'Successfully generated {len(transactions_to_create)} demo transactions for {driver.user.first_name} {driver.user.last_name}')
    return redirect(f"{reverse('workforce:fleet_transactions')}?driver_id={driver_id}")


@login_required(login_url='/accounts/login/')
@staff_required
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
        id__in=transaction_ids,
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

    # Wrap entire settlement operation in transaction.atomic for data consistency
    from django.db import transaction as db_transaction
    from django.db.models import F
    from django.db.models.functions import Greatest

    # Pre-calculate amounts before entering atomic block (transactions queryset will be re-evaluated)
    transaction_list = list(transactions)
    earnings_settled = sum(
        (txn.amount for txn in transaction_list if txn.transaction_type == 'earning'),
        Decimal('0.00')
    )
    cod_settled = sum(
        (abs(txn.amount) for txn in transaction_list if txn.transaction_type == 'cod_collection'),
        Decimal('0.00')
    )

    with db_transaction.atomic():
        # Create a settlement record
        settlement_code = f"STL-{timezone.now().strftime('%Y%m%d%H%M%S')}-{driver_id}"

        # Check if transactions still exist (might have been settled by another request)
        first_txn = transactions.order_by('created_at').first()
        if not first_txn:
            messages.warning(request, 'Transactions were already settled by another request')
            return redirect(f"{reverse('workforce:fleet_transactions')}?driver_id={driver_id}")

        settlement = fleet_models.DriverSettlement.objects.create(
            driver=driver,
            settlement_code=settlement_code,
            period_start=first_txn.created_at.date(),
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

        # Update driver balances atomically using F() to prevent race conditions
        if earnings_settled > 0:
            # Use Greatest to ensure we don't go below zero
            fleet_models.Driver.objects.filter(driver_id=driver_id).update(
                pending_earnings=Greatest(
                    F('pending_earnings') - earnings_settled,
                    Decimal('0.00')
                )
            )
        if cod_settled > 0:
            fleet_models.Driver.objects.filter(driver_id=driver_id).update(
                cod_in_hand=Greatest(
                    F('cod_in_hand') - cod_settled,
                    Decimal('0.00')
                )
            )

        # Update last_settlement_date
        fleet_models.Driver.objects.filter(driver_id=driver_id).update(
            last_settlement_date=timezone.now()
        )

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
@staff_required
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
@staff_required
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
@staff_required
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
@staff_required
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
@staff_required
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
@staff_required
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
@staff_required
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
@staff_required
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
        driver_status='approved'
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
@staff_required
def inventory_reports(request):
    """View for inventory reports"""
    context = {
        'page_title': 'Inventory Reports',
    }
    return render(request, 'workforce/inventory_reports.html', context)


@login_required(login_url='/accounts/login/')
@staff_required
def inventory_restock_list(request):
    """View for restock list"""
    context = {
        'page_title': 'Restock List',
    }
    return render(request, 'workforce/inventory_restock_list.html', context)


# Quick Links Functions
@login_required(login_url='/accounts/login/')
@staff_required
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
        active=Count('driver_id', filter=Q(driver_status='approved')),
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
@staff_required
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
@staff_required
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
        error_message = "Error fetching Shipday carriers. Please try again later."
        logger.exception("Error fetching Shipday carriers: %s", str(e))

    context = {
        'page_title': 'DMS Drivers List',
        'carriers': carriers or [],
        'error_message': error_message,
    }
    return render(request, 'workforce/dms_drivers_list.html', context)


@login_required(login_url='/accounts/login/')
@staff_required
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
        error_message = "Error fetching Shipday orders. Please try again later."
        logger.exception("Error fetching Shipday orders: %s", str(e))

    context = {
        'page_title': 'DMS Orders List',
        'orders_in_shipday': orders or [],
        'error_message': error_message,
    }
    return render(request, 'workforce/dms_orders_list.html', context)


@login_required(login_url='/accounts/login/')
@staff_required
def dms_analytics(request):
    """View for DMS analytics and statistics"""
    try:
        # Get statistics from local database
        total_tasks = delivery_models.DeliveryTask.objects.count()
        synced_tasks = delivery_models.DeliveryTask.objects.filter(dl_task_number_dms__isnull=False).count()
        pending_tasks = delivery_models.DeliveryTask.objects.filter(dl_task_number_dms__isnull=True).count()

        # Get driver statistics
        total_drivers = fleet_models.Driver.objects.filter(driver_status='approved').count()

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
        logger.exception("Error fetching DMS analytics: %s", str(e))
        context = {
            'page_title': 'DMS Analytics',
            'error_message': 'Error loading analytics. Please try again later.',
        }

    return render(request, 'workforce/dms_analytics.html', context)


@login_required(login_url='/accounts/login/')
@staff_required
def dms_sync_monitor(request):
    """View for monitoring DMS sync status"""
    try:
        # Get recently synced tasks
        recently_synced = delivery_models.DeliveryTask.objects.select_related(
            'order', 'driver', 'driver__user'
        ).filter(
            dl_task_number_dms__isnull=False
        ).order_by('-updated_at')[:50]

        # Get failed sync attempts
        failed_sync = delivery_models.DeliveryTask.objects.select_related(
            'order', 'driver', 'driver__user'
        ).filter(
            dl_task_number_dms__isnull=True,
            dl_task_status__in=['in_transit', 'pending', 'address_pending']
        ).order_by('-created_at')[:50]

        context = {
            'page_title': 'DMS Sync Monitor',
            'recently_synced': recently_synced,
            'failed_sync': failed_sync,
        }
    except Exception as e:
        logger.exception("Error fetching DMS sync monitor data: %s", str(e))
        context = {
            'page_title': 'DMS Sync Monitor',
            'error_message': 'Error loading sync monitor. Please try again later.',
        }

    return render(request, 'workforce/dms_sync_monitor.html', context)


# Documents section  ------------------------------------------------------------------------------------------------------


@login_required(login_url='/accounts/login/')
@staff_required
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
@staff_required
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

            # Handle file upload with validation
            if 'document_file' in request.FILES:
                uploaded_file = request.FILES['document_file']
                # Validate file extension
                allowed_extensions = ['.jpg', '.jpeg', '.png', '.pdf', '.gif']
                import os
                ext = os.path.splitext(uploaded_file.name)[1].lower()
                if ext not in allowed_extensions:
                    return JsonResponse({
                        'success': False,
                        'error': f'Invalid file type. Allowed: {", ".join(allowed_extensions)}'
                    }, status=400)
                # Validate file size (max 10MB)
                max_size = 10 * 1024 * 1024
                if uploaded_file.size > max_size:
                    return JsonResponse({
                        'success': False,
                        'error': 'File too large. Maximum size is 10MB'
                    }, status=400)
                document.document_file = uploaded_file

            document.save()

            return JsonResponse({
                'success': True,
                'message': 'Document updated successfully'
            })
        except Exception as e:
            logger.exception("Error updating driver document %s: %s", document_id, str(e))
            return JsonResponse({
                'success': False,
                'error': 'An error occurred while updating document'
            }, status=400)

    context = {
        'page_title': 'Driver Document Detail',
        'document': document,
    }

    return render(request, 'workforce/driver_document_detail.html', context)


@login_required(login_url='/accounts/login/')
@staff_required
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
@staff_required
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
            logger.exception("Error updating vehicle for driver %s: %s", driver_id, str(e))
            return JsonResponse({
                'success': False,
                'error': 'An error occurred while updating vehicle'
            }, status=400)

    context = {
        'page_title': 'Vehicle Documents Detail',
        'driver': driver,
        'vehicles': vehicles,
    }

    return render(request, 'workforce/vehicle_document_detail.html', context)


@login_required(login_url='/accounts/login/')
@staff_required
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
@staff_required
def store_document_detail(request, business_id):
    """View for viewing and updating store documents for a specific business"""
    business = get_object_or_404(business_models.Business, business_id=business_id)

    try:
        business_profile = business.business_profile
    except business_models.Business.business_profile.RelatedObjectDoesNotExist:
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
            logger.exception("Error updating store document for business %s: %s", business_id, str(e))
            return JsonResponse({
                'success': False,
                'error': 'An error occurred while updating store document'
            }, status=400)

    context = {
        'page_title': 'Store Document Detail',
        'business': business,
        'business_profile': business_profile,
    }

    return render(request, 'workforce/store_document_detail.html', context)


@login_required(login_url='/accounts/login/')
@staff_required
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
@staff_required
def business_license_detail(request, business_id):
    """View for viewing and updating business license details"""
    business = get_object_or_404(business_models.Business, business_id=business_id)

    try:
        business_profile = business.business_profile
    except business_models.Business.business_profile.RelatedObjectDoesNotExist:
        business_profile = None

    if request.method == 'POST':
        section = request.POST.get('section', 'all')
        try:
            if section == 'license':
                business.business_name = request.POST.get('business_name', business.business_name)
                business.business_qid = request.POST.get('business_qid', business.business_qid)
                business.business_product_category = request.POST.get('business_product_category', business.business_product_category)
                business_since = request.POST.get('business_since')
                if business_since:
                    business.business_since = business_since
                business.save()

            elif section == 'contact':
                business.business_phone = request.POST.get('business_phone', business.business_phone)
                business.business_email = request.POST.get('business_email', business.business_email)
                business.business_whatsapp = request.POST.get('business_whatsapp', business.business_whatsapp)
                business.business_facebook_page = request.POST.get('business_facebook_page', business.business_facebook_page)
                business.business_instagram = request.POST.get('business_instagram', business.business_instagram)
                business.save()

            elif section == 'address':
                if business_profile:
                    business_profile.business_address = request.POST.get('business_address', business_profile.business_address)
                    business_profile.business_city = request.POST.get('business_city', business_profile.business_city)
                    business_profile.business_country = request.POST.get('business_country', business_profile.business_country)
                    business_profile.save()

            elif section == 'status':
                business.business_status = request.POST.get('business_status', business.business_status)
                business.save()

            elif section == 'fulfillment':
                from warehouse import models as warehouse_models

                fulfillment_status = request.POST.get('fulfillment_service_status', business.fulfillment_service_status)
                warehouse_location_id = request.POST.get('warehouse_location_id', '').strip()

                logger.info(f"Fulfillment update for business {business.business_id}: status={fulfillment_status}, warehouse_id={warehouse_location_id}")

                # If activating fulfillment service, warehouse location is required
                if fulfillment_status == 'active' and not warehouse_location_id:
                    return JsonResponse({
                        'success': False,
                        'error': 'Please select a warehouse location when activating fulfillment service'
                    }, status=400)

                # Update fulfillment status
                try:
                    business.fulfillment_service_status = fulfillment_status
                    if fulfillment_status == 'active':
                        business.fulfillment_service_enabled = True
                        from django.utils import timezone
                        if not business.fulfillment_activated_at:
                            business.fulfillment_activated_at = timezone.now()
                    business.save()
                    logger.info(f"Business {business.business_id} fulfillment status updated to {fulfillment_status}")
                except Exception as e:
                    logger.exception(f"Error saving business fulfillment status: {e}")
                    return JsonResponse({
                        'success': False,
                        'error': f'Error updating fulfillment status: {str(e)}'
                    }, status=400)

                # Link warehouse if provided
                if warehouse_location_id and fulfillment_status == 'active':
                    try:
                        warehouse_location = warehouse_models.WarehouseLocation.objects.select_related('warehouse').get(id=warehouse_location_id)
                        logger.info(f"Found warehouse location: {warehouse_location.warehouse.code}/{warehouse_location.code}")

                        # Create or update warehouse link
                        link, created = warehouse_models.SellerWarehouseLink.objects.get_or_create(
                            business=business,
                            warehouse=warehouse_location.warehouse,
                            defaults={
                                'default_location': warehouse_location,  # Correct field name
                                'is_default': True,  # First warehouse becomes default
                                'linked_by': request.user,
                            }
                        )

                        if not created:
                            link.default_location = warehouse_location  # Correct field name
                            link.save()

                        action = 'created' if created else 'updated'
                        logger.info(f"Warehouse link {action} for business {business.business_id} -> {warehouse_location.warehouse.code}")

                        # Create or update a PickupLocation for the warehouse fulfillment center
                        pickup_location, pickup_created = business_models.PickupLocation.objects.update_or_create(
                            business=business,
                            warehouse=warehouse_location.warehouse,
                            defaults={
                                'pickup_location_title': f"{warehouse_location.warehouse.name} - Fulfillment",
                                'locality': warehouse_location.address or warehouse_location.warehouse.city or 'Warehouse Location',
                                'is_fulfilment_center': True,
                                'pickup_status': 'active',
                                'pickup_zone_no': warehouse_location.zone_number,
                                'pickup_lat': warehouse_location.latitude,
                                'pickup_lon': warehouse_location.longitude,
                            }
                        )
                        pickup_action = 'created' if pickup_created else 'updated'
                        logger.info(f"Fulfillment pickup location {pickup_action}: {pickup_location.pickup_location_title}")
                    except warehouse_models.WarehouseLocation.DoesNotExist:
                        logger.error(f"Warehouse location {warehouse_location_id} not found")
                        return JsonResponse({
                            'success': False,
                            'error': 'Selected warehouse location not found'
                        }, status=400)
                    except Exception as e:
                        logger.exception(f"Error linking warehouse: {e}")
                        return JsonResponse({
                            'success': False,
                            'error': f'Error linking warehouse: {str(e)}'
                        }, status=400)

            else:
                # Legacy: save all fields
                business.business_name = request.POST.get('business_name', business.business_name)
                business.business_qid = request.POST.get('business_qid', business.business_qid)
                business.business_status = request.POST.get('business_status', business.business_status)
                business.fulfillment_service_status = request.POST.get('fulfillment_service_status', business.fulfillment_service_status)
                business_since = request.POST.get('business_since')
                if business_since:
                    business.business_since = business_since
                business.save()
                if business_profile:
                    business_profile.business_address = request.POST.get('business_address', business_profile.business_address)
                    business_profile.business_city = request.POST.get('business_city', business_profile.business_city)
                    business_profile.save()

            return JsonResponse({
                'success': True,
                'message': f'{section.title()} updated successfully'
            })
        except Exception as e:
            logger.exception("Error updating business license %s: %s", business_id, str(e))
            return JsonResponse({
                'success': False,
                'error': 'An error occurred while updating business license'
            }, status=400)

    # Order stats
    order_stats = orders_models.Order.objects.filter(business=business).aggregate(
        total=Count('id'),
        delivered=Count('id', filter=Q(order_status='delivered')),
        pending=Count('id', filter=Q(order_status__in=['to_review', 'ready_to_pickup', 'publish'])),
    )

    # Get linked warehouse (if any)
    from warehouse import models as warehouse_models
    from product import models as product_models
    from django.db.models import Sum

    linked_warehouse = None
    if business.fulfillment_service_status == 'active':
        try:
            linked_warehouse = warehouse_models.SellerWarehouseLink.objects.select_related(
                'warehouse', 'default_location'
            ).filter(business=business, is_active=True).first()
        except Exception as e:
            logger.warning(f"Error fetching linked warehouse for business {business.business_id}: {e}")

    # Get product statistics for fulfillment businesses
    product_stats = {
        'total_products': 0,
        'active_skus': 0,
        'total_stock': 0,
        'low_stock_items': 0,
    }
    if business.fulfillment_service_status == 'active':
        try:
            products = product_models.Product.objects.filter(business=business)
            product_stats['total_products'] = products.count()
            product_stats['active_skus'] = products.count()  # All products are considered active SKUs

            # Get total stock from inventory
            total_stock_result = product_models.ProductInventory.objects.filter(
                item_sku__business=business
            ).aggregate(total=Sum('item_quantity'))
            product_stats['total_stock'] = total_stock_result['total'] or 0

            # Count low stock items (less than 10 units)
            for product in products:
                stock = product_models.ProductInventory.objects.filter(
                    item_sku=product
                ).aggregate(total=Sum('item_quantity'))['total'] or 0
                if stock < 10:
                    product_stats['low_stock_items'] += 1
        except Exception as e:
            logger.warning(f"Error fetching product stats for business {business.business_id}: {e}")

    context = {
        'page_title': f'{business.business_name} - Business Detail',
        'business': business,
        'business_profile': business_profile,
        'order_stats': order_stats,
        'linked_warehouse': linked_warehouse,
        'product_stats': product_stats,
    }

    return render(request, 'workforce/business_license_detail.html', context)


@login_required(login_url='/accounts/login/')
@staff_required
def api_warehouse_locations(request):
    """API endpoint to get all active warehouse locations"""
    from warehouse import models as warehouse_models

    try:
        locations = warehouse_models.WarehouseLocation.objects.select_related(
            'warehouse'
        ).filter(
            is_active=True
        ).order_by('warehouse__name', 'name')

        location_list = [{
            'id': loc.id,
            'warehouse_name': loc.warehouse.name,
            'name': loc.name,
            'code': loc.code,
            'warehouse_code': loc.warehouse.code,
            'address': loc.address or '',
            'city': loc.warehouse.city or '',
        } for loc in locations]

        return JsonResponse({'success': True, 'locations': location_list})
    except Exception as e:
        logger.exception("Error fetching warehouse locations: %s", str(e))
        return JsonResponse({'success': False, 'error': 'Failed to load warehouse locations'}, status=500)


# Sellers section  ------------------------------------------------------------------------------------------------------
@login_required(login_url='/accounts/login/')
@staff_required
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
@staff_required
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
@staff_required
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
@staff_required
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
@staff_required
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
        cod_amount__gt=0
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
            logger.exception("Error updating seller %s: %s", business_id, str(e))
            return JsonResponse({
                'success': False,
                'error': 'An error occurred while updating seller'
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
@staff_required
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
    active_count = fleet_models.Driver.objects.filter(driver_status='approved').count()
    pending_count = fleet_models.Driver.objects.filter(driver_status__in=['pending', 'processing']).count()
    inactive_count = fleet_models.Driver.objects.filter(driver_status__in=['rejected', 'blocked', 'suspended']).count()

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
@staff_required
def drivers_pending(request):
    """
    View to display drivers pending approval
    """
    drivers = fleet_models.Driver.objects.select_related(
        'user', 'profile'
    ).prefetch_related(
        'driver_vehicle', 'driver_document'
    ).filter(
        driver_status__in=['pending', 'processing']
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
@staff_required
def drivers_active(request):
    """
    View to display active (approved) drivers
    """
    drivers = fleet_models.Driver.objects.select_related(
        'user', 'profile'
    ).prefetch_related(
        'driver_vehicle', 'driver_document'
    ).filter(
        driver_status='approved'
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
@staff_required
def drivers_inactive(request):
    """
    View to display inactive, rejected, or blocked drivers
    """
    drivers = fleet_models.Driver.objects.select_related(
        'user', 'profile'
    ).prefetch_related(
        'driver_vehicle', 'driver_document'
    ).filter(
        driver_status__in=['rejected', 'blocked', 'suspended']
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
@staff_required
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
        order__cod_amount__gt=0
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
            # Update wallet limit if provided
            credit_limit = request.POST.get('credit_limit')
            if credit_limit:
                from decimal import Decimal
                driver.credit_limit = Decimal(credit_limit)
            driver.save()

            return JsonResponse({
                'success': True,
                'message': 'Driver updated successfully'
            })
        except Exception as e:
            logger.exception("Error updating driver %s: %s", driver_id, str(e))
            return JsonResponse({
                'success': False,
                'error': 'An error occurred while updating driver'
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
@staff_required
def suppliers_list(request):
    """
    List all businesses (sellers) with fulfillment service status sections.
    Section 1: Active fulfillment service
    Section 2: Requested and Non-active
    """
    from django.db.models import Count, Q as DjangoQ

    # Base queryset - all businesses
    base_qs = business_models.Business.objects.all()

    # Search filter
    search = request.GET.get('search', '').strip()
    if search:
        base_qs = base_qs.filter(
            Q(business_name__icontains=search) |
            Q(business_code__icontains=search) |
            Q(business_email__icontains=search) |
            Q(business_phone__icontains=search)
        )

    # Annotate with order stats
    base_qs = base_qs.annotate(
        total_orders=Count('order'),
        fulfilled_orders=Count('order', filter=DjangoQ(order__order_status__in=['delivered', 'fulfilled'])),
        pending_orders=Count('order', filter=DjangoQ(order__order_status__in=['to_review', 'ready_to_pickup', 'publish']))
    )

    # Section 1: Active fulfillment sellers
    active_sellers = list(base_qs.filter(
        fulfillment_service_status='active'
    ).order_by('-fulfillment_activated_at', 'business_name'))

    # Section 2: Requested and Non-active sellers
    requested_sellers = list(base_qs.filter(
        fulfillment_service_status='requested'
    ).order_by('business_name'))

    nonactive_sellers = list(base_qs.filter(
        fulfillment_service_status='none'
    ).order_by('business_name'))

    # Summary stats
    active_count = len(active_sellers)
    requested_count = len(requested_sellers)
    nonactive_count = len(nonactive_sellers)
    total_sellers = active_count + requested_count + nonactive_count

    context = {
        'page_title': 'Businesses - Fulfillment Service',
        'search': search,
        'active_sellers': active_sellers,
        'requested_sellers': requested_sellers,
        'nonactive_sellers': nonactive_sellers,
        'total_sellers': total_sellers,
        'active_count': active_count,
        'requested_count': requested_count,
        'nonactive_count': nonactive_count,
    }

    return render(request, 'workforce/suppliers_list.html', context)


@login_required
@staff_required
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
        cod_amount__gt=0
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


# ==========================================
# DELIVERY TASK BULK ACTIONS
# ==========================================

@login_required(login_url='/accounts/login/')
@staff_required
def delivery_task_edit(request, task_id):
    """Edit delivery task details and associated order"""
    task = get_object_or_404(
        delivery_models.DeliveryTask.objects.select_related(
            'order', 'order__business', 'driver', 'business', 'pickup_location'
        ),
        id=task_id
    )

    if request.method == 'POST':
        try:
            # Lock check: Prevent editing settled tasks
            if task.dl_task_status_dms == '2' and task.order and task.order.cod_status_by_staff == 'cod_settled_with_business':
                messages.error(request, 'Task is locked. Cannot edit after delivery is successful and COD is settled.')
                return redirect(request.path)

            # Handle task fields
            driver_id = request.POST.get('driver')
            status = request.POST.get('status')
            notes = request.POST.get('notes', '')

            if driver_id:
                task.driver_id = driver_id
            if status:
                task.dl_task_status = status
            task.notes = notes
            task.save()

            # Handle order fields if order exists
            if task.order:
                order = task.order

                # Customer details
                order.customer_name = request.POST.get('customer_name', order.customer_name)
                order.customer_phone = request.POST.get('customer_phone', order.customer_phone)
                order.customer_whatsapp = request.POST.get('customer_whatsapp', order.customer_whatsapp)
                order.customer_address = request.POST.get('customer_address', order.customer_address)

                # Address components
                dl_zone = request.POST.get('dl_zone', '')
                dl_street = request.POST.get('dl_street', '')
                dl_building = request.POST.get('dl_building', '')

                order.dl_zone = int(dl_zone) if dl_zone and dl_zone.isdigit() else None
                order.dl_street = int(dl_street) if dl_street and dl_street.isdigit() else None
                order.dl_building = int(dl_building) if dl_building and dl_building.isdigit() else None

                # COD details
                cod_amount = request.POST.get('cod_amount', '0')
                order.cod_amount = int(cod_amount) if cod_amount and cod_amount.isdigit() else 0

                dl_amount = request.POST.get('dl_amount', '0')
                order.dl_amount = int(dl_amount) if dl_amount and dl_amount.isdigit() else 0

                order.save()

                # Log the change
                orders_models.OrderVerificationLog.objects.create(
                    order=order,
                    action='task_edited',
                    verified_by=request.user,
                    notes=f'Task and order edited by {request.user.username}'
                )

            messages.success(request, f'Task #{task.dl_task_number} updated successfully.')

            # Check if HTMX request
            if request.headers.get('HX-Request'):
                return redirect('workforce:delivery_task_detail', task_id=task_id)
            return redirect('workforce:delivery_task_detail', task_id=task_id)

        except Exception as e:
            logger.exception("Error updating task %s: %s", task_id, str(e))
            messages.error(request, 'An error occurred while updating the task')

    # Get available drivers for dropdown (approved drivers)
    drivers = fleet_models.Driver.objects.select_related('user').filter(
        driver_status='approved'
    ).order_by('user__first_name')

    context = {
        'page_title': f'Edit Task #{task.dl_task_number}',
        'task': task,
        'drivers': drivers,
    }

    return render(request, 'workforce/parts/delivery_task_edit.html', context)


@login_required(login_url='/accounts/login/')
@staff_required
def bulk_print_tasks(request):
    """Generate printable view for selected tasks"""
    task_ids = request.GET.get('ids', '').split(',')
    task_ids = [int(id) for id in task_ids if id.isdigit() and len(id) <= 10][:100]  # Limit to 100 tasks

    if not task_ids:
        return render(request, 'workforce/parts/bulk_print_tasks.html', {
            'page_title': 'Print Tasks',
            'tasks': [],
            'print_mode': True,
        })

    tasks = delivery_models.DeliveryTask.objects.filter(
        id__in=task_ids
    ).select_related('order', 'driver', 'driver__user', 'business', 'pickup_location')

    context = {
        'page_title': 'Print Tasks',
        'tasks': tasks,
        'print_mode': True,
    }

    return render(request, 'workforce/parts/bulk_print_tasks.html', context)


@require_http_methods(["POST"])
@login_required(login_url='/accounts/login/')
@staff_required
def bulk_publish_dms(request):
    """Bulk publish tasks to DMS"""
    try:
        data = json.loads(request.body)
        task_ids = data.get('task_ids', [])

        if not task_ids:
            return JsonResponse({
                'success': False,
                'error': 'No tasks selected'
            }, status=400)

        # Update all selected tasks (only verified, non-cancelled orders)
        updated = delivery_models.DeliveryTask.objects.filter(
            id__in=task_ids,
            order__verification_status='verified',
        ).exclude(
            order__order_status='cancelled'
        ).update(
            dl_task_status='publish_to_dms',
            dl_task_publish=True
        )

        return JsonResponse({
            'success': True,
            'message': f'{updated} task(s) published to DMS',
            'updated_count': updated
        })
    except Exception as e:
        logger.exception("Error bulk publishing to DMS: %s", str(e))
        return JsonResponse({
            'success': False,
            'error': 'An error occurred while publishing tasks to DMS'
        }, status=400)


@require_http_methods(["POST"])
@login_required(login_url='/accounts/login/')
@staff_required
def bulk_publish_app(request):
    """Bulk publish tasks to Driver App"""
    try:
        data = json.loads(request.body)
        task_ids = data.get('task_ids', [])

        if not task_ids:
            return JsonResponse({
                'success': False,
                'error': 'No tasks selected'
            }, status=400)

        # Update all selected tasks to be available in driver app
        updated = delivery_models.DeliveryTask.objects.filter(
            id__in=task_ids
        ).update(dl_task_status_dms='6')  # Unassigned - available for drivers

        return JsonResponse({
            'success': True,
            'message': f'{updated} task(s) published to Driver App',
            'updated_count': updated
        })
    except Exception as e:
        logger.exception("Error bulk publishing to driver app: %s", str(e))
        return JsonResponse({
            'success': False,
            'error': 'An error occurred while publishing tasks to driver app'
        }, status=400)


@require_http_methods(["POST"])
@login_required(login_url='/accounts/login/')
@staff_required
def bulk_update_status(request):
    """Bulk update task status"""
    try:
        data = json.loads(request.body)
        task_ids = data.get('task_ids', [])
        status = data.get('status')

        if not task_ids:
            return JsonResponse({
                'success': False,
                'error': 'No tasks selected'
            }, status=400)

        if not status:
            return JsonResponse({
                'success': False,
                'error': 'Status is required'
            }, status=400)

        # Validate status against allowed choices
        VALID_STATUSES = [
            'for_review', 'pending', 'assigned', 'accepted', 'picked_up',
            'start_ride', 'out_for_delivery', 'in_transit', 'contacted',
            'non_reachable', 'delivered', 'failed', 'rejected', 'cancelled',
        ]
        if status not in VALID_STATUSES:
            return JsonResponse({
                'success': False,
                'error': f'Invalid status: {status}'
            }, status=400)

        # DMS status mapping for sync
        DMS_STATUS_MAP = {
            'delivered': '2', 'cancelled': '9', 'rejected': '8',
            'failed': '3', 'accepted': '7',
        }

        # Update all selected tasks (excluding locked tasks)
        tasks = delivery_models.DeliveryTask.objects.select_related('order').filter(
            id__in=task_ids
        ).exclude(
            dl_task_status_dms='2',
            order__cod_status_by_staff='cod_settled_with_business'
        )
        for task in tasks:
            task.dl_task_status = status
            if status in DMS_STATUS_MAP:
                task.dl_task_status_dms = DMS_STATUS_MAP[status]
            task.save(update_fields=['dl_task_status', 'dl_task_status_dms'])
        updated = tasks.count()

        return JsonResponse({
            'success': True,
            'message': f'{updated} task(s) updated to {status}',
            'updated_count': updated
        })
    except Exception as e:
        logger.exception("Error bulk updating task status: %s", str(e))
        return JsonResponse({
            'success': False,
            'error': 'An error occurred while updating task status'
        }, status=400)


def _sanitize_csv_value(value):
    """Sanitize value to prevent CSV injection attacks"""
    if value is None:
        return ''
    value = str(value)
    # Prevent formula injection by prefixing dangerous characters
    if value and value[0] in ('=', '+', '-', '@', '\t', '\r', '\n'):
        return "'" + value
    return value


@login_required(login_url='/accounts/login/')
@staff_required
def bulk_export_tasks(request):
    """Export selected tasks to CSV"""
    task_ids = request.GET.get('ids', '').split(',')
    task_ids = [int(id) for id in task_ids if id.isdigit() and len(id) <= 10][:500]  # Limit to 500 tasks

    if not task_ids:
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="delivery_tasks_export.csv"'
        return response

    tasks = delivery_models.DeliveryTask.objects.filter(
        id__in=task_ids
    ).select_related('order', 'driver', 'driver__user', 'business', 'pickup_location')

    # Log export for audit
    logger.info(f"CSV export by user {request.user.id}: {len(task_ids)} tasks")

    # Create CSV response
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="delivery_tasks_export.csv"'

    writer = csv.writer(response)
    writer.writerow([
        'Task Number', 'Date', 'Customer Name', 'Customer Phone',
        'Delivery Address', 'Driver', 'Client Status', 'DMS Status',
        'Pickup Location', 'COD Amount', 'Notes'
    ])

    for task in tasks:
        writer.writerow([
            _sanitize_csv_value(task.dl_task_number),
            _sanitize_csv_value(task.dl_task_date),
            _sanitize_csv_value(task.order.customer_name if task.order else ''),
            _sanitize_csv_value(task.order.customer_phone if task.order else ''),
            _sanitize_csv_value(task.order.customer_address if task.order else ''),
            _sanitize_csv_value(str(task.driver) if task.driver else ''),
            _sanitize_csv_value(task.get_dl_task_status_client_display() if hasattr(task, 'get_dl_task_status_client_display') else task.dl_task_status_client),
            _sanitize_csv_value(task.get_dl_task_status_dms_display() if hasattr(task, 'get_dl_task_status_dms_display') else task.dl_task_status_dms),
            _sanitize_csv_value(task.pickup_location.pickup_location_title if task.pickup_location else ''),
            _sanitize_csv_value(task.order.cod_amount if task.order else ''),
            _sanitize_csv_value(task.notes if hasattr(task, 'notes') else ''),
        ])

    return response


@login_required(login_url='/accounts/login/')
@staff_required
def order_edit(request, order_id):
    """Edit order details - Staff view for correcting order information"""
    order = get_object_or_404(
        orders_models.Order.objects.select_related(
            'business', 'pickup_location'
        ),
        id=order_id
    )

    # Get pickup locations for the business
    # Show fulfillment stores first when fulfillment service is enabled
    pickup_locations = business_models.PickupLocation.objects.filter(
        business=order.business
    ).order_by('-is_fulfilment_center', 'pickup_location_title')

    if request.method == 'POST':
        # Handle form submission
        try:
            # Customer details
            order.customer_name = request.POST.get('customer_name', order.customer_name)
            order.customer_phone = request.POST.get('customer_phone', order.customer_phone)
            order.customer_whatsapp = request.POST.get('customer_whatsapp', order.customer_whatsapp)
            order.customer_address = request.POST.get('customer_address', order.customer_address)

            # Address components
            dl_zone = request.POST.get('dl_zone', '')
            dl_street = request.POST.get('dl_street', '')
            dl_building = request.POST.get('dl_building', '')

            order.dl_zone = int(dl_zone) if dl_zone and dl_zone.isdigit() else None
            order.dl_street = int(dl_street) if dl_street and dl_street.isdigit() else None
            order.dl_building = int(dl_building) if dl_building and dl_building.isdigit() else None

            # COD details
            cod_amount = request.POST.get('cod_amount', '0')
            order.cod_amount = int(cod_amount) if cod_amount and cod_amount.isdigit() else 0
            cod_status = request.POST.get('cod_status_by_client')
            if cod_status:
                order.cod_status_by_client = cod_status
            elif order.cod_amount > 0 and order.cod_status_by_client == 'no_cod':
                order.cod_status_by_client = 'pending'

            # Delivery amount
            dl_amount = request.POST.get('dl_amount', '0')
            order.dl_amount = int(dl_amount) if dl_amount and dl_amount.isdigit() else 0

            # Pickup location
            pickup_id = request.POST.get('pickup_location')
            if pickup_id:
                order.pickup_location_id = pickup_id

            # Order notes
            order.order_notes = request.POST.get('order_notes', order.order_notes)

            # Status
            order.order_status = request.POST.get('order_status', order.order_status)
            order.verification_status = request.POST.get('verification_status', order.verification_status)

            order.save()

            # Log the change
            orders_models.OrderVerificationLog.objects.create(
                order=order,
                action='order_edited',
                verified_by=request.user,
                notes=f'Order edited by {request.user.username}'
            )

            messages.success(request, f'Order {order.order_number} updated successfully.')

            # Check if HTMX request
            if request.headers.get('HX-Request'):
                return redirect('workforce:order_detail', order_id=order_id)
            return redirect('workforce:order_detail', order_id=order_id)

        except Exception as e:
            logger.exception("Error updating order %s: %s", order_id, str(e))
            messages.error(request, 'An error occurred while updating the order')

    context = {
        'page_title': f'Edit Order - {order.order_number}',
        'order': order,
        'pickup_locations': pickup_locations,
        'order_statuses': orders_models.ORDER_STATUS_BY_CLIENT,
        'verification_statuses': orders_models.Order.VERIFICATION_STATUS,
        'cod_statuses': orders_models.COD_STATUS_BY_CLIENT,
    }

    return render(request, 'workforce/order_edit.html', context)


# =============================================================================
# WAREHOUSE-BUSINESS LINK MANAGEMENT
# =============================================================================


@login_required
@staff_required
def warehouses_list(request):
    """
    List all warehouses with linked businesses and link/unlink controls.
    """
    from warehouse.models import Warehouse, SellerWarehouseLink

    search = request.GET.get('search', '').strip()
    status_filter = request.GET.get('status', '')

    warehouses = Warehouse.objects.prefetch_related(
        'seller_links__business'
    ).order_by('-is_default', 'name')

    if search:
        warehouses = warehouses.filter(
            Q(name__icontains=search) | Q(code__icontains=search) |
            Q(city__icontains=search)
        )
    if status_filter == 'active':
        warehouses = warehouses.filter(is_active=True)
    elif status_filter == 'inactive':
        warehouses = warehouses.filter(is_active=False)

    # Get fulfillment-enabled businesses for the link dropdown
    linkable_businesses = business_models.Business.objects.filter(
        fulfillment_service_enabled=True,
        business_status='active',
    ).order_by('business_name')

    context = {
        'page_title': 'Warehouse - Business Links',
        'warehouses': warehouses,
        'linkable_businesses': linkable_businesses,
        'search': search,
        'status_filter': status_filter,
        'total_warehouses': Warehouse.objects.count(),
        'active_warehouses': Warehouse.objects.filter(is_active=True).count(),
        'total_links': SellerWarehouseLink.objects.filter(is_active=True).count(),
    }

    return render(request, 'workforce/warehouses_list.html', context)


@login_required
@staff_required
@require_http_methods(["POST"])
def warehouse_link_business(request):
    """
    Link a business to a warehouse. Creates SellerWarehouseLink which
    triggers signal to auto-create PickupLocation.
    """
    from warehouse.models import Warehouse, SellerWarehouseLink

    warehouse_id = request.POST.get('warehouse_id')
    business_id = request.POST.get('business_id')

    if not warehouse_id or not business_id:
        return JsonResponse({'success': False, 'error': 'Missing warehouse or business ID'}, status=400)

    warehouse = get_object_or_404(Warehouse, pk=warehouse_id)
    business = get_object_or_404(business_models.Business, pk=business_id)

    # Check if link already exists
    if SellerWarehouseLink.objects.filter(business=business, warehouse=warehouse).exists():
        return JsonResponse({'success': False, 'error': 'This business is already linked to this warehouse'}, status=400)

    SellerWarehouseLink.objects.create(
        business=business,
        warehouse=warehouse,
        is_active=True,
        linked_by=request.user,
    )

    messages.success(request, f'{business.business_name} linked to {warehouse.name}')
    return JsonResponse({'success': True, 'message': f'{business.business_name} linked to {warehouse.name}'})


@login_required
@staff_required
@require_http_methods(["POST"])
def warehouse_unlink_business(request):
    """
    Unlink a business from a warehouse. Deletes SellerWarehouseLink which
    triggers signal to deactivate PickupLocation.
    """
    from warehouse.models import SellerWarehouseLink

    link_id = request.POST.get('link_id')

    if not link_id:
        return JsonResponse({'success': False, 'error': 'Missing link ID'}, status=400)

    link = get_object_or_404(SellerWarehouseLink, pk=link_id)
    biz_name = link.business.business_name
    wh_name = link.warehouse.name
    link.delete()

    messages.success(request, f'{biz_name} unlinked from {wh_name}')
    return JsonResponse({'success': True, 'message': f'{biz_name} unlinked from {wh_name}'})


# =============================================================================
# PRODUCT REQUEST MANAGEMENT VIEWS
# =============================================================================


@login_required(login_url='/accounts/login/')
@staff_required
def product_requests_list(request):
    """
    Staff view to manage all inbound and outbound product requests.

    Shows combined list of requests from all businesses with filtering and stats.
    Staff can view, approve, and complete requests from this interface.
    """
    from warehouse.models import InboundProductRequest, OutboundProductRequest
    from django.core.paginator import Paginator

    # Get both types of requests
    inbound_qs = InboundProductRequest.objects.select_related(
        'business', 'warehouse', 'created_by', 'approved_by', 'completed_by'
    ).prefetch_related('items__product')

    outbound_qs = OutboundProductRequest.objects.select_related(
        'business', 'warehouse', 'created_by', 'approved_by', 'completed_by'
    ).prefetch_related('items__product')

    # Apply filters
    request_type = request.GET.get('type', 'all')  # all, inbound, outbound
    status_filter = request.GET.get('status', '')
    business_id = request.GET.get('business', '')

    if status_filter:
        inbound_qs = inbound_qs.filter(status=status_filter)
        outbound_qs = outbound_qs.filter(status=status_filter)

    if business_id:
        try:
            business_id = int(business_id)
            inbound_qs = inbound_qs.filter(business_id=business_id)
            outbound_qs = outbound_qs.filter(business_id=business_id)
        except (ValueError, TypeError):
            pass

    # Combine or filter by type
    if request_type == 'inbound':
        requests_list = list(inbound_qs)
    elif request_type == 'outbound':
        requests_list = list(outbound_qs)
    else:
        # Combine both types and sort by created_at
        requests_list = sorted(
            list(inbound_qs) + list(outbound_qs),
            key=lambda x: x.created_at,
            reverse=True
        )

    # Stats
    stats = {
        'total': len(requests_list),
        'pending_inbound': InboundProductRequest.objects.filter(status='pending').count(),
        'pending_outbound': OutboundProductRequest.objects.filter(status='pending').count(),
        'approved': len([r for r in requests_list if r.status == 'approved']),
        'completed': len([r for r in requests_list if r.status == 'completed']),
    }

    # Manual pagination since we combined querysets
    paginator = Paginator(requests_list, 20)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    # Get all businesses for filter dropdown
    businesses = business_models.Business.objects.filter(
        fulfillment_service_enabled=True
    ).order_by('business_name')

    context = {
        'page_title': 'Product Requests',
        'page_obj': page_obj,
        'stats': stats,
        'request_type': request_type,
        'status_filter': status_filter,
        'business_id': business_id,
        'businesses': businesses,
    }
    return render(request, 'workforce/product_requests_list.html', context)


@login_required(login_url='/accounts/login/')
@staff_required
@require_http_methods(["POST"])
def approve_product_request(request, request_id, request_type):
    """
    Approve an inbound or outbound product request.

    Changes status from pending to approved and records who approved it.
    """
    from django.utils import timezone
    from warehouse.models import InboundProductRequest, OutboundProductRequest

    if request_type == 'inbound':
        req = get_object_or_404(InboundProductRequest, id=request_id)
    elif request_type == 'outbound':
        req = get_object_or_404(OutboundProductRequest, id=request_id)
    else:
        messages.error(request, "Invalid request type")
        return redirect('workforce:product_requests_list')

    if req.status != 'pending':
        messages.warning(request, "Only pending requests can be approved.")
        return redirect('workforce:product_requests_list')

    req.status = 'approved'
    req.approved_by = request.user
    req.approved_at = timezone.now()
    req.save()

    messages.success(request, f"Request {req.request_number} approved successfully.")
    return redirect('workforce:product_requests_list')


@login_required(login_url='/accounts/login/')
@staff_required
@require_http_methods(["POST"])
def complete_product_request(request, request_id, request_type):
    """
    Mark a product request as completed.

    Changes status from approved to completed and records who completed it.
    Only approved requests can be marked as completed.
    """
    from django.utils import timezone
    from warehouse.models import InboundProductRequest, OutboundProductRequest

    if request_type == 'inbound':
        req = get_object_or_404(InboundProductRequest, id=request_id)
    elif request_type == 'outbound':
        req = get_object_or_404(OutboundProductRequest, id=request_id)
    else:
        messages.error(request, "Invalid request type")
        return redirect('workforce:product_requests_list')

    if req.status != 'approved':
        messages.warning(request, "Only approved requests can be marked as completed.")
        return redirect('workforce:product_requests_list')

    req.status = 'completed'
    req.completed_by = request.user
    req.completed_at = timezone.now()
    req.save()

    messages.success(request, f"Request {req.request_number} marked as completed.")
    return redirect('workforce:product_requests_list')

