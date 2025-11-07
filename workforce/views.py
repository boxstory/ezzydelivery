from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.contrib.auth.decorators import login_required
# Add these imports at the top of your View file
from django.core.paginator import (
    Paginator,
    EmptyPage,
    PageNotAnInteger,
)
from django.urls import reverse
# Create your views here.
from client import models as business_models
from core import models as core_models
from orders import models as orders_models
from delivery import models as delivery_models

from client import forms as business_forms


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
    profile = core_models.Profile.objects.get(user_id=request.user.id)

    data = {
        'profile': profile,

    }
    return render(request, 'workforce/wf_base_dashboard.html', data)


# Orders section  ------------------------------------------------------------------------------------------------------




def all_orders(request):
    orders  = orders_models.Order.objects.all().order_by('-created_at')
    orders = paginate_queryset(request, orders)

    data = {
        'orders': orders,
    }
    return render(request, 'workforce/parts/lists/orders_list_view.html', data)




def orders_to_publish(request):
    #orders = orders_models.Order.objects.filter(task_created = False).order_by('-created_at')
    orders = orders_models.Order.objects.filter(task_created = False).order_by('-created_at')
    orders = paginate_queryset(request, orders)

    data = {
        'orders': orders,
    }
    return render(request, 'workforce/parts/lists/orders_list_view.html', data)


def orders_published(request):
    #orders = orders_models.Order.objects.filter(task_created = False).order_by('-created_at')
    orders = orders_models.Order.objects.filter(task_created = True).order_by('-created_at')
    orders = paginate_queryset(request, orders)

    data = {
        'orders': orders,
    }
    return render(request, 'workforce/parts/lists/orders_list_view.html', data)

def submit_to_task(request, order_id):
    """Submit order to delivery task - now uses verification workflow"""
    from django.utils import timezone
    from orders.signals import _create_delivery_task_from_order
    
    order = get_object_or_404(orders_models.Order, id=order_id)
    
    # Check if order is verified
    if order.verification_status != 'verified':
        from django.contrib import messages
        messages.warning(request, 'Order must be verified before creating delivery task')
        return redirect(reverse('workforce:all_orders'))
    
    # Use the automated function that handles DMS push
    delivery_task = _create_delivery_task_from_order(order)
    
    if delivery_task:
        from django.contrib import messages
        messages.success(request, f'Delivery task created and pushed to DMS: {delivery_task.dl_task_number}')
    else:
        from django.contrib import messages
        messages.error(request, 'Failed to create delivery task')
    
    return redirect(reverse('workforce:all_orders'))


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
        return redirect(reverse('workforce:all_orders'))
    
    # GET request - show verification form
    address_verification = AddressVerification.objects.filter(order=order).first()
    context = {
        'order': order,
        'address_verification': address_verification,
    }
    return render(request, 'workforce/parts/verify_address.html', context)


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
        
        return redirect(reverse('workforce:all_orders'))
    
    # GET request - show verification form
    context = {
        'order': order,
    }
    return render(request, 'workforce/parts/verify_order.html', context)


def orders_pending_verification(request):
    """List orders pending verification"""
    verification_status = request.GET.get('verification_status', 'pending')
    
    orders = orders_models.Order.objects.filter(verification_status=verification_status).order_by('-created_at')
    orders = paginate_queryset(request, orders)
    
    data = {
        'orders': orders,
        'verification_status': verification_status,
    }
    return render(request, 'workforce/parts/lists/orders_list_view.html', data)


    

    





# Order Uploading verification section  ------------------------------------------------------------------------------------------------------


#@todo


# Delivery Tasks section  ------------------------------------------------------------------------------------------------------

def dl_list_all(request):
    dl_tasks  = delivery_models.DeliveryTask.objects.all().order_by('-created_at')
    dl_tasks = paginate_queryset(request, dl_tasks)
    data = {
        'dl_tasks': dl_tasks,
    }
    return render(request, 'workforce/parts/lists/dl_list_all.html', data)


def dl_list_incompleted_details(request):
    orders  = orders_models.Order.objects.all().order_by('-created_at')
    orders = paginate_queryset(request, orders)

    data = {
        'orders': orders,
    }
    return render(request, 'workforce/parts/lists/dl_list_incompleted.html', data)


def dl_list_published_to_dms(request):
    orders  = delivery_models.DeliveryTask.objects.filter().order_by('-created_at')
    orders = paginate_queryset(request, orders)

    data = {
        'orders': orders,
    }
    return render(request, 'workforce/parts/lists/dl_list_all.html', data)


def dl_list_ready_to_published_to_dms(request):
    orders  = orders_models.Order.objects.filter(task_created = False).order_by('-created_at')
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



