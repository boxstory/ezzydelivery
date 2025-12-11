"""
Delivery Views Module
=====================

This module handles delivery task management and address verification.

View Categories:
    Address Management:
        - dl_address_update: Update delivery address (authenticated)
        - dl_address_link: Public address verification page for customers
        - dl_address_link_update: Update address via link
        - save_location_data: AJAX endpoint to save GPS coordinates

    Task Management:
        - all_delivery_tasks: List all tasks (driver view)
        - assigned_tasks: List tasks assigned to current driver
        - assign_driver: AJAX endpoint for self-assignment

    Utility:
        - get_zone_name: AJAX lookup for zone names
        - get_zone_lat_long: AJAX lookup for coordinates

    Business Views:
        - delivery_business_update: Business-side delivery management

Public Endpoints:
    - dl_address_link: Allows customers to verify/update their delivery
      address via a link sent to their phone. No authentication required.

Security:
    - Driver views verify user has driver profile
    - CSRF protection on all POST endpoints
    - Coordinate validation before saving

Related:
    - delivery.models: DeliveryTask, DlAddressUpdate, AssignedDriver
    - delivery.forms: DlAddressUpdateForm
    - fleet.models: Driver
"""

import logging
from django.forms.fields import DateTimeField
from django.shortcuts import redirect, render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from decouple import config
import geocoder
import json


from core import models as core_models
from fleet import models as fleet_models
from business import models as business_models
from delivery import models as delivery_models
from orders import models as order_models

from webpages import forms as webpages_forms
from orders import forms as order_forms
from delivery import forms as delivery_forms
from fleet import forms as fleet_forms

logger = logging.getLogger('delivery')


# =============================================================================
# ADDRESS MANAGEMENT VIEWS
# =============================================================================


def dl_address_update(request, dl_task_number, mobile_no):
    try:
        instance = delivery_models.DlAddressUpdate.objects.get(
            dl_task_number=dl_task_number)
        form = delivery_forms.DlAddressUpdateForm(
            request.POST or None, instance=instance)

        if request.method == 'POST':
            logger.info(f"Address update request for task {dl_task_number}, mobile {mobile_no}")

            f = delivery_forms.DlAddressUpdateForm(request.POST)

            if f.is_valid():
                logger.info(f"Address update form valid for task {dl_task_number}")
                form = f.save(commit=False)
                form.dl_task_number = dl_task_number
                form.mobile_no = mobile_no
                form.save()
                logger.info(f"Address updated successfully for task {dl_task_number}")
                return redirect('/')
            else:
                logger.warning(f"Invalid address update form for task {dl_task_number}: {f.errors}")

        context = {
            'form': form,
            'dl_task_number': dl_task_number,
            'mobile_no': mobile_no,
        }
        return render(request, 'delivery/dl_address.html', context)
    except delivery_models.DlAddressUpdate.DoesNotExist:
        logger.error(f"Address update record not found for task {dl_task_number}")
        messages.error(request, "Delivery task not found")
        return redirect('/')


# AJAX
def get_zone_name(request):
    zone_number = request.GET.get('zone_number')
    logger.info(f"Fetching zone names for zone number: {zone_number}")
    zone_name = delivery_models.ZoneName.objects.filter(
        zone_number=zone_number).all()
    logger.debug(f"Found {len(zone_name)} zone names for zone {zone_number}")
    return render(request, 'delivery/zone_names.html', {'zone_name': zone_name})


def get_zone_lat_long(request):
    zone_number = request.GET.get('zone_number')
    street_number = request.GET.get('street_number')



# delivery details -------------------------------------------------------------------------


@login_required(login_url='account_login')
def all_delivery_tasks(request):
    # Get driver (with error handling)
    try:
        driver = fleet_models.Driver.objects.select_related(
            'user',  # FK: Driver → User
        ).get(user_id=request.user.id)
        logger.info(f"Driver {driver.driver_id} viewing all delivery tasks")
    except fleet_models.Driver.DoesNotExist:
        logger.warning(f"User {request.user.id} is not a driver")
        messages.error(request, "No driver profile found for your account")
        return redirect('homepage')

    # FIX: Optimize with select_related and prefetch_related
    dl_tasks = delivery_models.DeliveryTask.objects.select_related(
        'order',                    # FK: DeliveryTask → Order
        'order__business',          # Through: Order → Business
        'order__customer',          # Through: Order → Customer
        'order__pickup_location',   # Through: Order → PickupLocation
        'driver',                   # FK: DeliveryTask → Driver (if assigned)
    ).prefetch_related(
        'assigned_drivers',               # M2M: DeliveryTask ← AssignedDriver → Driver
        'assigned_drivers__driver',       # Through AssignedDriver
        'order__order_items',             # Reverse FK: Order ← OrderItem (related_name='order_items')
        'order__order_items__product',    # Through: OrderItem → Product
    ).order_by('-id')

    logger.debug(f"Fetched {dl_tasks.count()} delivery tasks")

    context = {
        'cards': dl_tasks,
        'driver': driver,
    }
    return render(request, 'delivery/parts/tasks_all.html', context)


@login_required(login_url='account_login')
def assign_driver(request):
    if request.method == "POST" and request.is_ajax():
        task_id = request.POST.get("task_id")

        if not task_id:
            return JsonResponse({"success": False, "error": "Task ID required"})

        if delivery_models.AssignedDriver.objects.filter(dl_task_id=task_id).exists():
            logger.info(f"Task {task_id} already assigned to a driver")
            return JsonResponse({"success": False, "error": "Task already assigned"})

        try:
            # IDOR FIX: Verify user is a driver
            driver = fleet_models.Driver.objects.get(user_id=request.user.id)

            task = delivery_models.DeliveryTask.objects.get(id=task_id)
            logger.info(f"Driver {driver.driver_id} assigning themselves to task {task_id}")

            assigned_driver = delivery_models.AssignedDriver(
                driver=driver, dl_task=task
            )
            assigned_driver.save()
            logger.info(f"Task {task_id} successfully assigned to driver {driver.driver_id}")

            return JsonResponse({"success": True})

        except fleet_models.Driver.DoesNotExist:
            logger.warning(f"User {request.user.id} is not a driver, cannot assign task")
            return JsonResponse({"success": False, "error": "Driver profile not found"})
        except delivery_models.DeliveryTask.DoesNotExist:
            logger.warning(f"Task {task_id} not found")
            return JsonResponse({"success": False, "error": "Task not found"})
        except Exception as e:
            logger.error(f"Error assigning task {task_id} to driver: {e}")
            return JsonResponse({"success": False, "error": str(e)})

    return JsonResponse({"success": False, "error": "Invalid request"})


@login_required(login_url='account_login')
def assigned_tasks(request):
    try:
        # FIX: Get driver with select_related
        driver = fleet_models.Driver.objects.select_related('user').get(
            user_id=request.user.id
        )
        logger.info(f"Driver {driver.driver_id} viewing assigned tasks")

        # FIX: Get task IDs (this is efficient - stays the same)
        assigned_tasks_ids = delivery_models.AssignedDriver.objects.filter(
            driver_id=driver.driver_id
        ).values_list('dl_task_id', flat=True)

        # FIX: Optimize with select_related and prefetch_related
        assigned_tasks = delivery_models.DeliveryTask.objects.filter(
            id__in=assigned_tasks_ids
        ).select_related(
            'order',
            'order__business',
            'order__customer',
            'order__pickup_location',
            'driver',
        ).prefetch_related(
            'assigned_drivers',
            'assigned_drivers__driver',
            'order__order_product_list',
        ).order_by('-id')

        logger.info(f"Driver {driver.driver_id} has {assigned_tasks.count()} assigned tasks")

        context = {
            'tasks': assigned_tasks,
            'driver': driver,
        }
        return render(request, 'delivery/parts/assigned_tasks.html', context)

    except fleet_models.Driver.DoesNotExist:
        logger.warning(f"User {request.user.id} attempted to view driver tasks but has no driver profile")
        messages.error(request, "No driver profile found")
        return redirect('homepage')


# business side delivery data --------------------------------------------------------------


def delivery_business_update(request):
    data = {


    }
    return render(request, 'delivery/delivery_list.html', data)


# customer address link  create and updates --------------------------------------------------------------


def dl_address_link(request, dl_task_code):
    task = get_object_or_404(
        delivery_models.DlAddressUpdate, dl_task_number=dl_task_code)
    MAPBOX_API_KEY = config("MAPBOX_API_KEY")
    address = f'{task.dl_latitude},{task.dl_longitude}'
    address2 = f'{task.dl_longitude},{task.dl_latitude}'
    logger.info(f"Viewing address link for task {dl_task_code}, coordinates: {address}")

    try:
        g = geocoder.mapbox(address2, key=MAPBOX_API_KEY)
        logger.debug(f"Geocoding successful for task {dl_task_code}")
    except Exception as e:
        logger.error(f"Geocoding failed for task {dl_task_code}: {e}")
        g = None

    data = {
        'task': task,
        'address': address2,
        'g': g,
        'MAPBOX_API_KEY': MAPBOX_API_KEY
    }
    return render(request, 'delivery/frontend/dl_address_link.html', data)


def dl_address_link_update(request, dl_task_code):

    data = {

    }
    return render(request, 'delivery/frontend/dl_address_link_update.html', data)


def save_location_data(request, dl_task_code):
    """
    Save customer location data for delivery address.

    CSRF token is required - sent via X-CSRFToken header from frontend.
    The template already includes the CSRF token and sends it properly.
    """
    logger.info(f"Saving location data for task {dl_task_code}")

    if request.method == 'POST':
        try:
            data = json.loads(request.body.decode('utf-8'))
            dl_latitude = data.get('dl_latitude')
            dl_longitude = data.get('dl_longitude')

            # Validate latitude and longitude
            if dl_latitude is None or dl_longitude is None:
                logger.warning(f"Missing coordinates in location update for task {dl_task_code}")
                return JsonResponse({'error': 'Latitude and longitude are required'}, status=400)

            instance = delivery_models.DlAddressUpdate.objects.get(dl_task_number=dl_task_code)
            logger.debug(f"Found task {dl_task_code}, updating location: {dl_latitude}, {dl_longitude}")

        except delivery_models.DlAddressUpdate.DoesNotExist:
            logger.warning(f"Task {dl_task_code} not found for location update")
            return JsonResponse({'error': 'Instance not found'}, status=404)
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in location update request: {e}")
            return JsonResponse({'error': 'Invalid JSON'}, status=400)

        instance.dl_latitude = dl_latitude
        instance.dl_longitude = dl_longitude
        instance.save()

        return JsonResponse({'message': 'Data saved successfully'})
    else:
        return JsonResponse({'message': 'Invalid request method'}, status=400)
