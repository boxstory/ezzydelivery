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
from orders import models as orders_models

from webpages import forms as webpages_forms
from orders import forms as orders_forms
from delivery import forms as delivery_forms
from fleet import forms as fleet_forms

# Local aliases for commonly used models
DeliveryTask = delivery_models.DeliveryTask
DlAddressUpdate = delivery_models.DlAddressUpdate
AssignedDriver = delivery_models.AssignedDriver
ZoneName = delivery_models.ZoneName
LatLonList = delivery_models.LatLonList
Order = orders_models.Order
Business = business_models.Business
Driver = fleet_models.Driver
Profile = core_models.Profile

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
        return redirect('webpages:index')

    # Get filter parameters (defaults: My Tasks + My Zone)
    tab = request.GET.get('tab', 'assigned')  # 'new' or 'assigned'
    area_filter = request.GET.get('area', 'my_zone')  # 'all', 'doha', 'my_zone', 'qatar'
    type_filter = request.GET.get('type', 'all')  # 'all', 'public', 'pnd'

    # Base queryset with optimized joins
    base_qs = delivery_models.DeliveryTask.objects.select_related(
        'order',
        'order__business',
        'order__pickup_location',
        'driver',
        'dl_to_address',
    ).prefetch_related(
        'assigneddriver_set',
        'assigneddriver_set__driver',
        'order__order_items',
        'order__order_items__product',
        'task_qrcode',
    )

    # Split into new tasks and assigned tasks
    # New tasks: published and not assigned to any driver
    new_tasks = base_qs.filter(
        dl_task_publish=True,
        driver__isnull=True,
        dl_task_status__in=['pending', 'publish_to_dms', 'assigned']
    ).exclude(
        dl_task_status__in=['delivered', 'cancelled', 'failed']
    ).order_by('-id')

    # Assigned tasks: assigned to current driver
    assigned_tasks = base_qs.filter(
        driver=driver
    ).exclude(
        dl_task_status__in=['delivered', 'cancelled']
    ).order_by('-id')

    # Apply area filter
    if area_filter == 'doha':
        # Doha zones (1-50)
        new_tasks = new_tasks.filter(dl_to_address__dl_zone__lte=50)
        assigned_tasks = assigned_tasks.filter(dl_to_address__dl_zone__lte=50)
    elif area_filter == 'my_zone':
        # Driver's zone (from profile or default zone)
        driver_zone = getattr(driver, 'default_zone', None)
        if driver_zone:
            new_tasks = new_tasks.filter(dl_to_address__dl_zone=driver_zone)
            assigned_tasks = assigned_tasks.filter(dl_to_address__dl_zone=driver_zone)
    elif area_filter == 'qatar':
        # All Qatar (zones > 50)
        new_tasks = new_tasks.filter(dl_to_address__dl_zone__gt=50)
        assigned_tasks = assigned_tasks.filter(dl_to_address__dl_zone__gt=50)

    # Apply type filter
    if type_filter == 'public':
        new_tasks = new_tasks.filter(dl_task_publish=True)
    elif type_filter == 'pnd':
        # Pick and Drop tasks (category or speed based)
        new_tasks = new_tasks.filter(dl_speed__in=['On Demand', 'Same Day'])
        assigned_tasks = assigned_tasks.filter(dl_speed__in=['On Demand', 'Same Day'])

    # Get counts
    new_count = new_tasks.count()
    assigned_count = assigned_tasks.count()

    # Select which tasks to show based on tab
    if tab == 'new':
        cards = new_tasks[:50]
    else:
        cards = assigned_tasks[:50]

    logger.debug(f"Fetched tasks: {new_count} new, {assigned_count} assigned")

    context = {
        'cards': cards,
        'new_tasks': new_tasks[:20],
        'assigned_tasks': assigned_tasks[:20],
        'new_count': new_count,
        'assigned_count': assigned_count,
        'driver': driver,
        'current_tab': tab,
        'area_filter': area_filter,
        'type_filter': type_filter,
    }
    return render(request, 'delivery/parts/tasks_all.html', context)


@login_required(login_url='account_login')
def assign_driver(request):
    if request.method == "POST":
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

            # Update task status to assigned when driver accepts
            task.dl_task_status = 'assigned'
            task.save(update_fields=['dl_task_status'])
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
def start_ride(request):
    """Start the delivery ride - update task status to in_transit"""
    if request.method == "POST":
        task_id = request.POST.get("task_id")

        if not task_id:
            return JsonResponse({"success": False, "error": "Task ID required"})

        try:
            # Verify user is a driver
            driver = fleet_models.Driver.objects.get(user_id=request.user.id)

            # Verify task is assigned to this driver
            assigned = delivery_models.AssignedDriver.objects.filter(
                dl_task_id=task_id, driver=driver
            ).exists()

            if not assigned:
                return JsonResponse({"success": False, "error": "Task not assigned to you"})

            task = delivery_models.DeliveryTask.objects.get(id=task_id)

            # Update status to in_transit
            task.dl_task_status = 'in_transit'
            task.save(update_fields=['dl_task_status'])
            logger.info(f"Driver {driver.driver_id} started ride for task {task_id}")

            return JsonResponse({
                "success": True,
                "redirect_url": f"/delivery/task/{task_id}/navigation/"
            })

        except fleet_models.Driver.DoesNotExist:
            return JsonResponse({"success": False, "error": "Driver profile not found"})
        except delivery_models.DeliveryTask.DoesNotExist:
            return JsonResponse({"success": False, "error": "Task not found"})
        except Exception as e:
            logger.error(f"Error starting ride for task {task_id}: {e}")
            return JsonResponse({"success": False, "error": str(e)})

    return JsonResponse({"success": False, "error": "Invalid request"})


@login_required(login_url='account_login')
def task_navigation(request, task_id):
    """Show navigation map for delivery task"""
    try:
        driver = fleet_models.Driver.objects.get(user_id=request.user.id)

        # Verify task is assigned to this driver
        assigned = delivery_models.AssignedDriver.objects.filter(
            dl_task_id=task_id, driver=driver
        ).exists()

        if not assigned:
            from django.contrib import messages
            messages.error(request, "Task not assigned to you")
            return redirect('delivery:all_delivery_tasks')

        task = delivery_models.DeliveryTask.objects.select_related(
            'order', 'order__business', 'pickup_location', 'dl_to_address'
        ).get(id=task_id)

        # Get pickup coordinates - try pickup_location first, then warehouse
        pickup = task.pickup_location
        pickup_lat = None
        pickup_lon = None

        if pickup and pickup.pickup_lat and pickup.pickup_lon:
            pickup_lat = pickup.pickup_lat
            pickup_lon = pickup.pickup_lon
        else:
            # Fallback to warehouse coordinates
            from warehouse.models import Warehouse
            warehouse = Warehouse.objects.filter(is_active=True).first()
            if warehouse and warehouse.latitude and warehouse.longitude:
                pickup_lat = warehouse.latitude
                pickup_lon = warehouse.longitude

        context = {
            'task': task,
            'pickup': task.pickup_location,
            'dropoff': task.dl_to_address,
            'pickup_lat': pickup_lat,
            'pickup_lon': pickup_lon,
        }

        return render(request, 'delivery/task_navigation.html', context)

    except fleet_models.Driver.DoesNotExist:
        from django.contrib import messages
        messages.error(request, "Driver profile not found")
        return redirect('delivery:all_delivery_tasks')
    except delivery_models.DeliveryTask.DoesNotExist:
        from django.contrib import messages
        messages.error(request, "Task not found")
        return redirect('delivery:all_delivery_tasks')


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
            'order__pickup_location',
            'driver',
        ).prefetch_related(
            'assigneddriver_set',
            'assigneddriver_set__driver',
            'order__order_items',
            'order__order_items__product',
            'task_qrcode',
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
        return redirect('webpages:index')


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


# Zone Map View --------------------------------------------------------------

@login_required(login_url='account_login')
def zone_map(request):
    """
    Display all zones on an interactive map using Leaflet.js
    Shows zone markers with coordinates and neighbour connections.
    """
    # Get all zones with coordinates
    zones = delivery_models.ZoneName.objects.filter(
        latitude__isnull=False,
        longitude__isnull=False
    ).exclude(
        latitude=0, longitude=0
    ).prefetch_related('neighbour_zones', 'zone_groups').order_by('zone_number')

    # Get zone groups for filtering
    zone_groups = delivery_models.ZoneGroup.objects.filter(
        is_active=True
    ).prefetch_related('zones').order_by('display_order')

    # Prepare zone data for JavaScript
    zones_data = []
    for zone in zones:
        neighbour_coords = []
        for neighbour in zone.neighbour_zones.filter(latitude__isnull=False):
            if neighbour.latitude and neighbour.longitude:
                neighbour_coords.append({
                    'zone_number': neighbour.zone_number,
                    'lat': float(neighbour.latitude),
                    'lng': float(neighbour.longitude),
                    'name': neighbour.zone_name
                })

        zones_data.append({
            'zone_number': zone.zone_number,
            'name': zone.zone_name,
            'name_arabic': zone.zone_name_arabic or '',
            'lat': float(zone.latitude),
            'lng': float(zone.longitude),
            'has_polygon': zone.has_polygon,
            'polygon': zone.polygon if zone.polygon else None,
            'neighbour_count': zone.neighbour_zones.count(),
            'neighbours': neighbour_coords,
            'groups': list(zone.zone_groups.values_list('name', flat=True))
        })

    # Summary stats
    total_zones = delivery_models.ZoneName.objects.count()
    zones_with_coords = zones.count()
    zones_without_coords = total_zones - zones_with_coords

    context = {
        'zones': zones,
        'zones_json': json.dumps(zones_data),
        'zone_groups': zone_groups,
        'total_zones': total_zones,
        'zones_with_coords': zones_with_coords,
        'zones_without_coords': zones_without_coords,
    }
    return render(request, 'delivery/zone_map.html', context)


@login_required(login_url='account_login')
def zone_map_api(request):
    """API endpoint to get zone data as JSON"""
    zones = delivery_models.ZoneName.objects.filter(
        latitude__isnull=False,
        longitude__isnull=False
    ).exclude(latitude=0, longitude=0).prefetch_related('neighbour_zones')

    zones_data = []
    for zone in zones:
        zones_data.append({
            'zone_number': zone.zone_number,
            'name': zone.zone_name,
            'name_arabic': zone.zone_name_arabic or '',
            'lat': float(zone.latitude),
            'lng': float(zone.longitude),
            'neighbour_ids': list(zone.neighbour_zones.values_list('zone_number', flat=True))
        })

    return JsonResponse({'zones': zones_data})


def get_street_polygon(request, zone_number, street_number):
    """
    Get street polygon coordinates for a given zone and street from QNAS API.

    URL: /delivery/get_street_polygon/<zone_number>/<street_number>/

    Query params:
        - update_zone: If 'true', updates the zone's polygon field

    Returns JSON:
        {
            "success": true,
            "zone_number": 1,
            "street_number": 123,
            "polygon": [[lat, lon], [lat, lon], ...],
            "zone_updated": true/false
        }
    """
    import requests
    from decouple import config

    try:
        zone_number = int(zone_number)
        street_number = int(street_number)
    except (ValueError, TypeError):
        return JsonResponse({
            'success': False,
            'error': 'Invalid zone_number or street_number'
        }, status=400)

    logger.info(f"Fetching street polygon for zone {zone_number}, street {street_number}")

    # QNAS API configuration
    base_url = "https://qnas.qa"
    token = config("QNAS_TOKEN", default="75f6618da1204809900d904de6e61b40")
    domain = config("QNAS_DOMAIN", default="ezzydelivery.qa")

    headers = {
        "X-Token": token,
        "X-Domain": domain,
        "Accept": "application/json",
        "User-Agent": request.META.get("HTTP_USER_AGENT", "Mozilla/5.0"),
        "Referer": f"https://{domain}/",
        "Origin": f"https://{domain}",
    }

    try:
        # QNAS API endpoint: /get_street_polygon/{zone_number}/{street_number}
        api_url = f"{base_url}/get_street_polygon/{zone_number}/{street_number}"
        response = requests.get(api_url, headers=headers, timeout=15)

        if response.status_code != 200:
            return JsonResponse({
                'success': False,
                'error': f'QNAS API returned HTTP {response.status_code}',
                'zone_number': zone_number,
                'street_number': street_number
            }, status=response.status_code)

        data = response.json()

        # Check for API error
        if data.get('status') == 'error':
            return JsonResponse({
                'success': False,
                'error': data.get('message', 'Street polygon not found'),
                'zone_number': zone_number,
                'street_number': street_number
            })

        # Extract polygon from QNAS response
        polygon = None
        if data.get('status') == 'success' and 'coordinates' in data:
            coords = data['coordinates']
            if isinstance(coords, list) and len(coords) >= 3:
                # Convert from [{lat, lng}, ...] to [[lat, lng], ...]
                polygon = [[p['lat'], p['lng']] for p in coords if 'lat' in p and 'lng' in p]

        # Check if we should update the zone model
        update_zone = request.GET.get('update_zone', '').lower() == 'true'
        zone_updated = False

        if update_zone and polygon:
            try:
                zone = delivery_models.ZoneName.objects.get(zone_number=zone_number)
                zone.polygon = polygon
                zone.save(update_fields=['polygon', 'updated_at'])
                zone_updated = True
                logger.info(f"Updated polygon for zone {zone_number}")
            except delivery_models.ZoneName.DoesNotExist:
                logger.warning(f"Zone {zone_number} not found for polygon update")

        return JsonResponse({
            'success': True,
            'zone_number': zone_number,
            'street_number': street_number,
            'polygon': polygon,
            'point_count': len(polygon) if polygon else 0,
            'zone_updated': zone_updated
        })

    except requests.exceptions.Timeout:
        logger.error(f"QNAS API timeout for zone {zone_number}, street {street_number}")
        return JsonResponse({
            'success': False,
            'error': 'QNAS API request timed out'
        }, status=504)
    except requests.RequestException as e:
        logger.error(f"Error fetching street polygon: {e}")
        return JsonResponse({
            'success': False,
            'error': f'API request failed: {str(e)}'
        }, status=502)
    except Exception as e:
        logger.error(f"Error processing street polygon: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required(login_url='account_login')
def edit_zone_polygon(request, zone_number):
    """
    Edit zone polygon with interactive map editor.
    URL: /delivery/zones/edit-polygon/<zone_number>/
    """
    zone = get_object_or_404(delivery_models.ZoneName, zone_number=zone_number)

    # Get ALL zones with polygons (excluding current zone) to show boundaries
    all_zones_with_polygons = delivery_models.ZoneName.objects.exclude(
        zone_number=zone_number
    ).exclude(
        polygon__isnull=True
    ).exclude(
        polygon=[]
    )

    all_polygons_data = []
    for z in all_zones_with_polygons:
        if z.polygon and len(z.polygon) >= 3:
            # Check if this is a neighbour
            is_neighbour = zone.neighbour_zones.filter(zone_number=z.zone_number).exists()
            all_polygons_data.append({
                'zone_number': z.zone_number,
                'name': z.zone_name,
                'polygon': z.polygon,
                'is_neighbour': is_neighbour
            })

    context = {
        'zone': zone,
        'zone_polygon_json': json.dumps(zone.polygon if zone.polygon else []),
        'all_polygons_json': json.dumps(all_polygons_data),
        'center_lat': float(zone.latitude) if zone.latitude else 25.276987,
        'center_lng': float(zone.longitude) if zone.longitude else 51.520008,
    }
    return render(request, 'delivery/edit_polygon.html', context)


@login_required(login_url='account_login')
def save_zone_polygon(request, zone_number):
    """
    Save edited polygon for a zone.
    URL: /delivery/zones/save-polygon/<zone_number>/
    """
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST required'}, status=405)

    zone = get_object_or_404(delivery_models.ZoneName, zone_number=zone_number)

    try:
        data = json.loads(request.body.decode('utf-8'))
        polygon = data.get('polygon', [])

        if not polygon or len(polygon) < 3:
            return JsonResponse({
                'success': False,
                'error': 'Polygon must have at least 3 points'
            }, status=400)

        # Validate polygon points
        for i, point in enumerate(polygon):
            if not isinstance(point, list) or len(point) != 2:
                return JsonResponse({
                    'success': False,
                    'error': f'Invalid point format at index {i}'
                }, status=400)
            lat, lng = point
            if not (-90 <= lat <= 90) or not (-180 <= lng <= 180):
                return JsonResponse({
                    'success': False,
                    'error': f'Invalid coordinates at index {i}'
                }, status=400)

        # Update zone
        zone.polygon = polygon

        # Update center coordinates to polygon center
        lats = [p[0] for p in polygon]
        lngs = [p[1] for p in polygon]
        zone.latitude = round((min(lats) + max(lats)) / 2, 7)
        zone.longitude = round((min(lngs) + max(lngs)) / 2, 7)

        zone.save(update_fields=['polygon', 'latitude', 'longitude', 'updated_at'])

        logger.info(f"Polygon updated for zone {zone_number} ({len(polygon)} points)")

        return JsonResponse({
            'success': True,
            'message': f'Polygon saved with {len(polygon)} points',
            'center': [float(zone.latitude), float(zone.longitude)]
        })

    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid JSON'}, status=400)
    except Exception as e:
        logger.error(f"Error saving polygon for zone {zone_number}: {e}")
        return JsonResponse({'success': False, 'error': str(e)}, status=500)



@login_required(login_url='account_login')
def zone_areas(request):
    """
    Display all zone areas in a dashboard-style list view.
    Shows areas grouped by zone with search and filter capabilities.
    """
    from django.db.models import Q, Count
    from django.core.paginator import Paginator

    # Get filter parameters
    search = request.GET.get('search', '').strip()
    zone_filter = request.GET.get('zone', '')
    page = request.GET.get('page', 1)

    # Base queryset
    areas = delivery_models.ZoneArea.objects.select_related('zone').order_by(
        'zone__zone_number', 'area_name'
    )

    # Apply search
    if search:
        areas = areas.filter(
            Q(area_name__icontains=search) |
            Q(area_name_arabic__icontains=search) |
            Q(zone__zone_name__icontains=search) |
            Q(zone__zone_number__icontains=search)
        )

    # Apply zone filter
    if zone_filter:
        areas = areas.filter(zone__zone_number=zone_filter)

    # Get zones for filter dropdown
    zones = delivery_models.ZoneName.objects.annotate(
        area_count=Count('areas')
    ).filter(area_count__gt=0).order_by('zone_number')

    # Pagination
    paginator = Paginator(areas, 50)
    areas_page = paginator.get_page(page)

    # Stats
    total_areas = delivery_models.ZoneArea.objects.count()
    total_zones_with_areas = zones.count()

    context = {
        'areas': areas_page,
        'zones': zones,
        'total_areas': total_areas,
        'total_zones_with_areas': total_zones_with_areas,
        'search': search,
        'zone_filter': zone_filter,
    }
    return render(request, 'delivery/zone_areas.html', context)


@login_required(login_url='account_login')
def zone_list(request):
    """
    Display all zones in a dashboard-style list view.
    Shows zones with polygon status, area count, and neighbour info.
    """
    from django.db.models import Q, Count
    from django.core.paginator import Paginator

    # Get filter parameters
    search = request.GET.get('search', '').strip()
    group_filter = request.GET.get('group', '')
    polygon_filter = request.GET.get('polygon', '')
    page = request.GET.get('page', 1)

    # Base queryset
    zones = delivery_models.ZoneName.objects.annotate(
        area_count=Count('areas'),
        neighbour_count=Count('neighbour_zones')
    ).prefetch_related('zone_groups').order_by('zone_number')

    # Apply search
    if search:
        zones = zones.filter(
            Q(zone_name__icontains=search) |
            Q(zone_name_arabic__icontains=search) |
            Q(zone_number__icontains=search)
        )

    # Apply group filter
    if group_filter:
        zones = zones.filter(zone_groups__id=group_filter)

    # Apply polygon filter
    if polygon_filter == 'with':
        zones = zones.exclude(polygon__isnull=True).exclude(polygon=[])
    elif polygon_filter == 'without':
        zones = zones.filter(Q(polygon__isnull=True) | Q(polygon=[]))

    # Get groups for filter dropdown
    groups = delivery_models.ZoneGroup.objects.filter(is_active=True).order_by('display_order')

    # Pagination
    paginator = Paginator(zones, 50)
    zones_page = paginator.get_page(page)

    # Stats
    total_zones = delivery_models.ZoneName.objects.count()
    zones_with_polygon = delivery_models.ZoneName.objects.exclude(polygon__isnull=True).exclude(polygon=[]).count()
    zones_without_polygon = total_zones - zones_with_polygon

    context = {
        'zones': zones_page,
        'groups': groups,
        'total_zones': total_zones,
        'zones_with_polygon': zones_with_polygon,
        'zones_without_polygon': zones_without_polygon,
        'search': search,
        'group_filter': group_filter,
        'polygon_filter': polygon_filter,
    }
    return render(request, 'delivery/zone_list.html', context)


@login_required(login_url='account_login')
def zone_groups(request):
    """
    Display all zone groups in a dashboard-style view.
    Shows groups with their zones and stats.
    """
    from django.db.models import Count

    # Get filter parameters
    search = request.GET.get('search', '').strip()

    # Base queryset
    groups = delivery_models.ZoneGroup.objects.annotate(
        zone_count=Count('zones')
    ).prefetch_related('zones').order_by('display_order', 'name')

    # Apply search
    if search:
        groups = groups.filter(
            Q(name__icontains=search) |
            Q(description__icontains=search)
        )

    # Stats
    total_groups = delivery_models.ZoneGroup.objects.count()
    active_groups = delivery_models.ZoneGroup.objects.filter(is_active=True).count()

    context = {
        'groups': groups,
        'total_groups': total_groups,
        'active_groups': active_groups,
        'search': search,
    }
    return render(request, 'delivery/zone_groups.html', context)
