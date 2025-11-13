from multiprocessing import context
import logging
from django.forms.fields import DateTimeField
from django.shortcuts import redirect, render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from decouple import config
from django.views.decorators.csrf import csrf_exempt
import geocoder
import json


from core import models as core_models
from fleet import models as fleet_models
from client import models as business_models
from delivery import models as delivery_models
from orders import models as order_models

from webpages import forms as webpages_forms
from orders import forms as order_forms
from delivery import forms as delivery_forms
from fleet import forms as fleet_forms

logger = logging.getLogger('delivery')

# Create your views here.


# requst to user update address before delivery


def dl_address_update(request, dl_task_number, mobile_no):
    instance = delivery_models.DlAddressUpdate.objects.get(
        dl_task_number=dl_task_number)
    form = delivery_forms.DlAddressUpdateForm(
        request.POST or None, instance=instance)
    if request.method == 'POST':
        print("dl_address request.POST")

        f = delivery_forms.DlAddressUpdateForm(
            request.POST)

        if f.is_valid():
            print("DlAddressUpdateForm 2 is valid")
            form = f.save(commit=False)
            form.dl_task_number = dl_task_number
            form.mobile_no = mobile_no

            print(form)
            form.save()

            return redirect('/')
    else:
        print("dl_address else")

    context = {
        'form': form,
        'dl_task_number': dl_task_number,
        'mobile_no': mobile_no,
    }
    return render(request, 'delivery/dl_address.html', context)


# AJAX
def get_zone_name(request):
    zone_number = request.GET.get('zone_number')
    zone_name = delivery_models.ZoneName.objects.filter(
        zone_number=zone_number).all()
    print(zone_name)
    print("get_zone_name")
    return render(request, 'delivery/zone_names.html', {'zone_name': zone_name})
    # return JsonResponse(list(cities.values('id', 'name')), safe=False)


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
        'order__order_product_list',      # Reverse FK: Order ← OrderProductList
    ).order_by('-id')

    logger.debug(f"Fetched {dl_tasks.count()} delivery tasks")

    context = {
        'cards': dl_tasks,
        'driver': driver,
    }
    return render(request, 'delivery/parts/tasks_all.html', context)


def assign_driver(request):

    if request.method == "POST" and request.is_ajax():
        task_id = request.POST.get("task_id")
        if task_id and delivery_models.AssignedDriver.objects.filter(dl_task_id=task_id).exists():
            print(' already assigned')
        else:
            driver_id = request.user.id
            print(task_id, "task_id -  driver_id", driver_id)
            try:
                task = delivery_models.DeliveryTask.objects.get(id=task_id)
                print(task)
                driver = fleet_models.Driver.objects.get(driver_id=driver_id)
                print(driver)
                assigned_driver = delivery_models.AssignedDriver(
                    driver=driver, dl_task=task)
                assigned_driver.save()

                return JsonResponse({"success": True})
            except Exception as e:
                print('error')
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
    print(address)
    g = geocoder.mapbox(address2, key=MAPBOX_API_KEY)
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


@csrf_exempt
def save_location_data(request, dl_task_code):
    print("vide save_location_data", dl_task_code)
    if request.method == 'POST':
        data = json.loads(request.body.decode('utf-8'))  # Parse JSON data from request body
        dl_latitude = data.get('dl_latitude')
        dl_longitude = data.get('dl_longitude')

        try:
            instance = delivery_models.DlAddressUpdate.objects.get(dl_task_number=dl_task_code)
            print(instance)
        except delivery_models.DlAddressUpdate.DoesNotExist:
            return JsonResponse({'error': 'Instance not found'}, status=404)

        instance.dl_latitude = dl_latitude
        instance.dl_longitude = dl_longitude
        instance.save()

        return JsonResponse({'message': 'Data saved successfully'})
    else:
        return JsonResponse({'message': 'Invalid request method'}, status=400)
