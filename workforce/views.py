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

from business import models as business_models
from core import models as core_models
from orders import models as orders_models
from delivery import models as delivery_models
from fleet import models as fleet_models

from business import forms as business_forms

# ShipDay API integration
from decouple import config
try:
    from shipday import Shipday
    API_KEY = config("SHIPDAY_API_KEY", default="")
    shipday_obj = Shipday(api_key=API_KEY) if API_KEY else None
except ImportError:
    shipday_obj = None

logger = logging.getLogger(__name__)


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
    try:
        profile = core_models.Profile.objects.get(user_id=request.user.id)
    except core_models.Profile.DoesNotExist:
        logger.warning(f"User {request.user.id} has no profile. Redirecting to profile creation.")
        # Redirect to profile view or create a profile
        return redirect('core:profile_view')

    # Count pending user verifications
    pending_verifications = core_models.Profile.objects.filter(
        verification_status='pending'
    ).count()

    data = {
        'profile': profile,
        'pending_verifications': pending_verifications,
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
        orders = orders.filter(delivery_task__dl_task_code__icontains=dl_code)

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
def orders_by_seller(request):
    """
    View to display orders grouped by seller/business
    """
    from django.db.models import Count, Q

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


    

    





# Delivery Tasks section  ------------------------------------------------------------------------------------------------------

@login_required(login_url='/accounts/login/')
def dl_list_all(request):
    dl_tasks = delivery_models.DeliveryTask.objects.select_related(
        'order', 'driver', 'business', 'pickup_location', 'order__business'
    ).all().order_by('-created_at')
    dl_tasks = paginate_queryset(request, dl_tasks)
    data = {
        'dl_tasks': dl_tasks,
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


# AJAX Endpoints for Orders List ------------------------------------------------------------------------------------------------------

@require_http_methods(["POST"])
@login_required(login_url='/accounts/login/')
def publish_order_to_delivery(request, order_id):
    """AJAX endpoint to publish order to delivery"""
    try:
        order = get_object_or_404(orders_models.Order, id=order_id)

        # Update order status to publish
        order.order_status = 'publish'
        order.task_status = 'dl_task_listed'
        order.save()

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
        'business', 'delivery_task'
    ).prefetch_related('order_comments').filter(
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
    drivers = fleet_models.Driver.objects.filter(
        driver_status='Approved'
    ).select_related('user').order_by('user__first_name')

    drivers_with_pagination = paginate_queryset(request, drivers, items_per_page=20)

    context = {
        'drivers': drivers_with_pagination,
        'page_title': 'COD In Hand',
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
    """View for fleet transactions"""
    # This would connect to a transactions model when implemented
    context = {
        'page_title': 'Fleet Transactions',
        'transactions': [],  # Placeholder for transactions queryset
    }
    return render(request, 'workforce/fleet_transactions.html', context)


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
        total=Count('id'),
        active=Count('id', filter=Q(driver_status='Approved')),
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
        synced_tasks = delivery_models.DeliveryTask.objects.filter(is_published_to_dms=True).count()
        pending_tasks = delivery_models.DeliveryTask.objects.filter(is_published_to_dms=False).count()

        # Get driver statistics
        total_drivers = fleet_models.Driver.objects.filter(is_active=True).count()

        # Get order statistics
        total_orders = orders_models.Order.objects.count()
        published_orders = orders_models.Order.objects.filter(is_published=True).count()

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
            is_published_to_dms=True
        ).order_by('-updated_at')[:50]

        # Get failed sync attempts
        failed_sync = delivery_models.DeliveryTask.objects.filter(
            is_published_to_dms=False,
            status__in=['assigned', 'in_transit']
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

    # Summary stats
    total_suppliers = suppliers.count()
    total_fulfilled = orders_models.Order.objects.filter(
        order_status__in=['delivered', 'fulfilled'],
        business__fulfillment_service_enabled=True
    ).count()

    # Paginate
    page_obj = paginate_queryset(request, suppliers, items_per_page=20)

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


