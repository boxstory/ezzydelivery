import logging
from django.http import JsonResponse
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
import requests
from rest_framework import permissions, status, viewsets
from rest_framework import generics
from rest_framework.decorators import api_view, permission_classes, action
from rest_framework.response import Response
from rest_framework.authtoken.models import Token
from rest_framework.authentication import TokenAuthentication
from rest_framework.permissions import IsAuthenticated, AllowAny
from django.contrib.auth import authenticate
from django.utils import timezone
from decouple import config
from django.db import transaction
from django.db.models import Q, Count, Sum
from datetime import datetime, timedelta

from orders import models as orders_models
from fleet import models as fleet_models
from delivery import models as delivery_models
from core import models as core_models
from business import models as business_models
from ezzy_api import models as ezzy_api_models
from ezzy_api import serializers as ezzy_api_serializers
from shipday import Shipday
from core.context_processors import get_cached_business


def get_api_user_business(request):
    """
    Helper to get business for API request user.
    Uses cached version when available, falls back to DB query for DRF requests.
    """
    # Try cached version first (works for regular Django requests)
    business = get_cached_business(request)
    if business is not None:
        return business
    # For DRF requests that might not have the cache attribute, query directly
    if hasattr(request, 'user') and request.user.is_authenticated:
        try:
            return business_models.Business.objects.get(user_id=request.user.id)
        except business_models.Business.DoesNotExist:
            return None
    return None

# Local aliases for commonly used models
Order = orders_models.Order
OrderItem = orders_models.OrderItem
DeliveryTask = delivery_models.DeliveryTask
Driver = fleet_models.Driver
Business = business_models.Business
Profile = core_models.Profile
from django.core.files.uploadedfile import InMemoryUploadedFile
import shopify
from woocommerce import API
import json
import hmac
import hashlib
import requests
from django.views.decorators.csrf import csrf_exempt

logger = logging.getLogger('ezzy_api')


class OrderList(generics.ListCreateAPIView):

    permission_classes = [permissions.IsAuthenticated]
    serializer_class = ezzy_api_serializers.OrderSerializer

    def get_queryset(self):
        """Filter orders to only those belonging to the authenticated user's business."""
        business = get_api_user_business(self.request)
        if business:
            return orders_models.Order.objects.filter(business=business)
        return orders_models.Order.objects.none()

API_KEY = config("SHIPDAY_API_KEY")
shipday_obj = Shipday(api_key=API_KEY)


def shipday_order_list(request):
    logger.info(f"Fetching Shipday orders for user: {request.user.id if request.user.is_authenticated else 'anonymous'}")
    try:
        orderNumber = "BMS045-1636-A222"
        my_orders = shipday_obj.OrderService.get_orders()
        logger.info(f"Successfully fetched {len(my_orders) if my_orders else 0} orders from Shipday")
        return render(request, 'ezzy_api/orders_in_shipday.html', {'orders_in_shipday': my_orders})
    except Exception as e:
        logger.error(f"Error fetching Shipday orders: {e}")
        return render(request, 'ezzy_api/orders_in_shipday.html', {'orders_in_shipday': []})

def shipday_feet_list(request):
    logger.info(f"Fetching Shipday carriers for user: {request.user.id if request.user.is_authenticated else 'anonymous'}")
    try:
        my_carriers = shipday_obj.CarrierService.get_carriers()
        logger.info(f"Successfully fetched {len(my_carriers) if my_carriers else 0} carriers from Shipday")
        return render(request, 'ezzy_api/carriers.html', {'carriers': my_carriers})
    except Exception as e:
        logger.error(f"Error fetching Shipday carriers: {e}")
        return render(request, 'ezzy_api/carriers.html', {'carriers': []})


def ShipdayOrderList(request):
    logger.info("Fetching completed orders from Shipday partner API")
    try:
        API_KEY = config("SHIPDAY_API_KEY")
        my_shipday = Shipday(api_key=API_KEY)
        my_carriers = my_shipday.CarrierService.get_carriers()
        logger.info(f"Retrieved {len(my_carriers)} carriers from Shipday")

        import requests

        url = "https://api.shipday.com/partner/members/1234/completedOrders"

        headers = {
            "accept": "application/json",
            "PARTNER-API-KEY": API_KEY
        }

        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()

        data = response.json()
        logger.info(f"Successfully fetched completed orders: {len(data) if isinstance(data, list) else 'unknown count'}")
        return data
    except requests.exceptions.RequestException as e:
        logger.error(f"Shipday API request failed: {e}")
        return {'error': str(e)}
    except Exception as e:
        logger.error(f"Error in ShipdayOrderList: {e}")
        return {'error': str(e)}







class TookanAPI:
    base_url = "https://api.tookanapp.com/"
    api_key = config("TOOKAN_API_KEY")

    def __init__(self, api_key):
        self.api_key = api_key

    def _make_request(self, endpoint, method="GET", data=None):
        url = self.base_url + endpoint
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        response = requests.request(method, url, json=data, headers=headers)
        response.raise_for_status()
        return response.json()

    def get_teams(self):
        endpoint = "team/"
        return self._make_request(endpoint)

    def create_task(self, task_data):
        endpoint = "create_task/"
        return self._make_request(endpoint, method="POST", data=task_data)

    def get_task(self, task_id):
        endpoint = f"get_task/{task_id}"
        return self._make_request(endpoint)

    # Add more methods for other API endpoints as needed


# ==================== DRIVER APP APIs ====================

@api_view(['POST'])
@permission_classes([AllowAny])
def driver_login(request):
    """Driver login API - returns authentication token"""
    username = request.data.get('username')
    password = request.data.get('password')
    
    if not username or not password:
        return Response(
            {'error': 'Username and password are required'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    user = authenticate(username=username, password=password)
    
    if user is None:
        return Response(
            {'error': 'Invalid credentials'},
            status=status.HTTP_401_UNAUTHORIZED
        )
    
    # Check if user is a driver
    try:
        driver = fleet_models.Driver.objects.get(user=user)
        if driver.driver_status != 'approved':
            return Response(
                {'error': 'Driver account not approved'},
                status=status.HTTP_403_FORBIDDEN
            )
    except fleet_models.Driver.DoesNotExist:
        return Response(
            {'error': 'User is not a driver'},
            status=status.HTTP_403_FORBIDDEN
        )
    
    # Get or create token
    token, created = Token.objects.get_or_create(user=user)
    
    serializer = ezzy_api_serializers.DriverSerializer(driver)
    
    return Response({
        'token': token.key,
        'driver': serializer.data
    }, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def driver_profile(request):
    """Get driver profile"""
    try:
        driver = fleet_models.Driver.objects.get(user=request.user)
        serializer = ezzy_api_serializers.DriverSerializer(driver)
        return Response(serializer.data, status=status.HTTP_200_OK)
    except fleet_models.Driver.DoesNotExist:
        return Response(
            {'error': 'Driver profile not found'},
            status=status.HTTP_404_NOT_FOUND
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def driver_tasks(request):
    """Get all tasks assigned to the driver"""
    try:
        driver = fleet_models.Driver.objects.get(user=request.user)
        logger.info(f"Fetching tasks for driver {driver.driver_id}")

        # Get query parameters
        status_filter = request.query_params.get('status', None)
        date_filter = request.query_params.get('date', None)

        # N+1 FIX: Use select_related to fetch related objects in one query
        # Only show tasks for verified, non-cancelled orders
        tasks = delivery_models.DeliveryTask.objects.filter(
            driver=driver,
            order__verification_status='verified',
        ).exclude(
            order__order_status='cancelled'
        ).select_related(
            'order',
            'order__business',
            'order__client',
            'driver',
            'business'
        )

        if status_filter:
            tasks = tasks.filter(dl_task_status=status_filter)

        if date_filter:
            try:
                date_obj = datetime.strptime(date_filter, '%Y-%m-%d').date()
                tasks = tasks.filter(dl_task_date=date_obj)
            except ValueError:
                logger.warning(f"Invalid date format provided: {date_filter}")
                pass

        serializer = ezzy_api_serializers.DeliveryTaskListSerializer(tasks, many=True)
        logger.info(f"Returned {len(tasks)} tasks for driver {driver.driver_id}")
        return Response(serializer.data, status=status.HTTP_200_OK)

    except fleet_models.Driver.DoesNotExist:
        logger.warning(f"Driver profile not found for user {request.user.id}")
        return Response(
            {'error': 'Driver profile not found'},
            status=status.HTTP_404_NOT_FOUND
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def driver_task_detail(request, task_id):
    """Get detailed information about a specific task"""
    try:
        driver = fleet_models.Driver.objects.get(user=request.user)
        # IDOR FIX: Verify task belongs to this driver
        # N+1 FIX: Use select_related for related objects
        task = delivery_models.DeliveryTask.objects.select_related(
            'order',
            'order__business',
            'order__client',
            'driver',
            'business'
        ).get(id=task_id, driver=driver)

        logger.info(f"Driver {driver.driver_id} accessed task {task_id}")
        serializer = ezzy_api_serializers.DeliveryTaskSerializer(task)
        return Response(serializer.data, status=status.HTTP_200_OK)
    except delivery_models.DeliveryTask.DoesNotExist:
        logger.warning(f"Task {task_id} not found or not assigned to driver {request.user.id}")
        return Response(
            {'error': 'Task not found'},
            status=status.HTTP_404_NOT_FOUND
        )
    except fleet_models.Driver.DoesNotExist:
        logger.warning(f"Driver profile not found for user {request.user.id}")
        return Response(
            {'error': 'Driver profile not found'},
            status=status.HTTP_404_NOT_FOUND
        )


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def driver_accept_task(request, task_id):
    """Driver accepts a task"""
    try:
        driver = fleet_models.Driver.objects.get(user=request.user)

        with transaction.atomic():
            task = delivery_models.DeliveryTask.objects.select_for_update().get(id=task_id)

            if task.driver and task.driver != driver:
                return Response(
                    {'error': 'Task already assigned to another driver'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            task.driver = driver
            task.dl_task_status = 'accepted'
            task.dl_task_status_dms = '7'  # Accepted/Acknowledged
            task.save()

            # Create AssignedDriver record
            delivery_models.AssignedDriver.objects.get_or_create(
                driver=driver, dl_task=task
            )

        # Trigger webhooks (outside transaction)
        webhook_payload = {
            'task_id': task_id,
            'task_number': task.dl_task_number,
            'status': 'accepted',
            'dms_status': '7',
            'timestamp': timezone.now().isoformat(),
            'driver_id': driver.driver_id
        }
        _send_webhook_event('task_accepted', webhook_payload, business=task.business)

        serializer = ezzy_api_serializers.DeliveryTaskSerializer(task)
        return Response({
            'message': 'Task accepted successfully',
            'task': serializer.data
        }, status=status.HTTP_200_OK)

    except delivery_models.DeliveryTask.DoesNotExist:
        return Response(
            {'error': 'Task not found'},
            status=status.HTTP_404_NOT_FOUND
        )
    except fleet_models.Driver.DoesNotExist:
        return Response(
            {'error': 'Driver profile not found'},
            status=status.HTTP_404_NOT_FOUND
        )


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def driver_reject_task(request, task_id):
    """Driver rejects a task"""
    try:
        driver = fleet_models.Driver.objects.get(user=request.user)
        # Check if task is assigned to driver via DeliveryTask.driver OR AssignedDriver
        task = delivery_models.DeliveryTask.objects.select_related('order').filter(
            Q(driver=driver) | Q(assigneddriver__driver=driver),
            id=task_id
        ).distinct().first()
        if not task:
            raise delivery_models.DeliveryTask.DoesNotExist()

        # Lock check: Prevent status change if task is Successful AND COD is settled
        if task.dl_task_status_dms == '2' and task.order and task.order.cod_status_by_staff == 'cod_settled_with_business':
            return Response({
                'error': 'Task is locked. Status cannot be changed after delivery is successful and COD is settled.'
            }, status=status.HTTP_403_FORBIDDEN)

        task.dl_task_status = 'rejected'
        task.dl_task_status_dms = '8'  # Decline
        task.driver = None
        task.save()

        # Clean up AssignedDriver record
        delivery_models.AssignedDriver.objects.filter(
            driver=driver, dl_task=task
        ).delete()
        
        # Trigger webhooks
        webhook_payload = {
            'task_id': task_id,
            'task_number': task.dl_task_number,
            'status': 'rejected',
            'dms_status': '8',
            'timestamp': timezone.now().isoformat(),
            'driver_id': driver.driver_id
        }
        _send_webhook_event('task_rejected', webhook_payload, business=task.business)
        
        return Response({
            'message': 'Task rejected successfully'
        }, status=status.HTTP_200_OK)
    
    except delivery_models.DeliveryTask.DoesNotExist:
        return Response(
            {'error': 'Task not found'},
            status=status.HTTP_404_NOT_FOUND
        )
    except fleet_models.Driver.DoesNotExist:
        return Response(
            {'error': 'Driver profile not found'},
            status=status.HTTP_404_NOT_FOUND
        )


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def driver_update_task_status(request, task_id):
    """Driver updates task status"""
    VALID_DRIVER_STATUSES = [
        'accepted', 'picked_up', 'start_ride', 'out_for_delivery',
        'in_transit', 'contacted', 'non_reachable',
    ]
    try:
        driver = fleet_models.Driver.objects.get(user=request.user)
        # Check if task is assigned to driver via DeliveryTask.driver OR AssignedDriver
        task = delivery_models.DeliveryTask.objects.select_related('order').filter(
            Q(driver=driver) | Q(assigneddriver__driver=driver),
            id=task_id
        ).distinct().first()
        if not task:
            raise delivery_models.DeliveryTask.DoesNotExist()

        # Lock check: Prevent status change if order is cancelled
        if task.order and task.order.order_status == 'cancelled':
            return Response({
                'error': 'Task is locked. Order is cancelled — no delivery status changes allowed.'
            }, status=status.HTTP_403_FORBIDDEN)

        # Lock check: Prevent status change if order is not verified
        if task.order and task.order.verification_status != 'verified':
            return Response({
                'error': 'Task is locked. Order must be verified before delivery status can be updated.'
            }, status=status.HTTP_403_FORBIDDEN)

        # Lock check: Prevent status change if task is Successful AND COD is settled
        if task.dl_task_status_dms == '2' and task.order and task.order.cod_status_by_staff == 'cod_settled_with_business':
            return Response({
                'error': 'Task is locked. Status cannot be changed after delivery is successful and COD is settled.'
            }, status=status.HTTP_403_FORBIDDEN)

        new_status = request.data.get('status')
        dms_status = request.data.get('dms_status')

        if new_status:
            if new_status not in VALID_DRIVER_STATUSES:
                return Response({
                    'error': f'Invalid status: {new_status}. Valid statuses: {", ".join(VALID_DRIVER_STATUSES)}'
                }, status=status.HTTP_400_BAD_REQUEST)
            task.dl_task_status = new_status

        if dms_status:
            task.dl_task_status_dms = dms_status

        task.save()
        
        # Trigger webhooks
        webhook_payload = {
            'task_id': task_id,
            'task_number': task.dl_task_number,
            'status': new_status,
            'dms_status': dms_status or task.dl_task_status_dms,
            'timestamp': timezone.now().isoformat(),
            'driver_id': driver.driver_id
        }
        _send_webhook_event('task_status_update', webhook_payload, business=task.business)
        
        serializer = ezzy_api_serializers.DeliveryTaskSerializer(task)
        return Response({
            'message': 'Task status updated successfully',
            'task': serializer.data
        }, status=status.HTTP_200_OK)
    
    except delivery_models.DeliveryTask.DoesNotExist:
        return Response(
            {'error': 'Task not found'},
            status=status.HTTP_404_NOT_FOUND
        )
    except fleet_models.Driver.DoesNotExist:
        return Response(
            {'error': 'Driver profile not found'},
            status=status.HTTP_404_NOT_FOUND
        )


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def driver_update_location(request):
    """Update driver's current location"""
    try:
        driver = fleet_models.Driver.objects.get(user=request.user)
        
        latitude = request.data.get('latitude')
        longitude = request.data.get('longitude')
        
        if not latitude or not longitude:
            return Response(
                {'error': 'Latitude and longitude are required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Store location in driver model or create a separate location tracking model
        # For now, we'll just return success
        # You can create a DriverLocation model to track location history
        
        return Response({
            'message': 'Location updated successfully',
            'latitude': latitude,
            'longitude': longitude,
            'timestamp': timezone.now()
        }, status=status.HTTP_200_OK)
    
    except fleet_models.Driver.DoesNotExist:
        return Response(
            {'error': 'Driver profile not found'},
            status=status.HTTP_404_NOT_FOUND
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def driver_statistics(request):
    """Get driver statistics (completed tasks, earnings, ratings, etc.)"""
    try:
        driver = fleet_models.Driver.objects.get(user=request.user)
        
        # Get date range from query params
        start_date = request.query_params.get('start_date', None)
        end_date = request.query_params.get('end_date', None)
        
        tasks = delivery_models.DeliveryTask.objects.filter(driver=driver)
        
        if start_date:
            try:
                start = datetime.strptime(start_date, '%Y-%m-%d').date()
                tasks = tasks.filter(dl_task_date__gte=start)
            except ValueError:
                pass
        
        if end_date:
            try:
                end = datetime.strptime(end_date, '%Y-%m-%d').date()
                tasks = tasks.filter(dl_task_date__lte=end)
            except ValueError:
                pass
        
        total_tasks = tasks.count()
        completed_tasks = tasks.filter(dl_task_status='delivered').count()
        in_progress_tasks = tasks.filter(dl_task_status__in=[
            'accepted', 'picked_up', 'start_ride', 'out_for_delivery',
            'in_transit', 'contacted', 'non_reachable'
        ]).count()
        total_earnings = tasks.filter(dl_task_status='delivered').aggregate(
            total=Sum('dl_price')
        )['total'] or 0
        
        stats = {
            'total_tasks': total_tasks,
            'completed_tasks': completed_tasks,
            'in_progress_tasks': in_progress_tasks,
            'pending_tasks': total_tasks - completed_tasks - in_progress_tasks,
            'total_earnings': total_earnings,
            'driver_rating': driver.driver_rating,
            'driver_rating_count': driver.driver_rating_count
        }
        
        return Response(stats, status=status.HTTP_200_OK)
    
    except fleet_models.Driver.DoesNotExist:
        return Response(
            {'error': 'Driver profile not found'},
            status=status.HTTP_404_NOT_FOUND
        )


# ==================== DMS APIs ====================

@api_view(['GET'])
@permission_classes([IsAuthenticated, permissions.IsAdminUser])
def dms_orders_list(request):
    """Get list of all orders for DMS (staff only)"""
    logger.info(f"DMS orders list requested by user {request.user.id}")

    # N+1 FIX: Use select_related for ForeignKey relationships
    orders = orders_models.Order.objects.select_related(
        'business',
        'pickup_location'
    ).all().order_by('-created_at')

    # Filters
    status_filter = request.query_params.get('status', None)
    business_filter = request.query_params.get('business_id', None)
    date_from = request.query_params.get('date_from', None)
    date_to = request.query_params.get('date_to', None)

    if status_filter:
        orders = orders.filter(order_status=status_filter)

    if business_filter:
        orders = orders.filter(business_id=business_filter)

    if date_from:
        try:
            date_obj = datetime.strptime(date_from, '%Y-%m-%d').date()
            orders = orders.filter(order_date__gte=date_obj)
        except ValueError:
            logger.warning(f"Invalid date_from format: {date_from}")
            pass

    if date_to:
        try:
            date_obj = datetime.strptime(date_to, '%Y-%m-%d').date()
            orders = orders.filter(order_date__lte=date_obj)
        except ValueError:
            logger.warning(f"Invalid date_to format: {date_to}")
            pass

    serializer = ezzy_api_serializers.OrderListSerializer(orders, many=True)
    logger.info(f"Returned {len(orders)} orders for DMS")
    return Response(serializer.data, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsAuthenticated, permissions.IsAdminUser])
def dms_order_detail(request, order_id):
    """Get detailed information about a specific order (staff only)"""
    try:
        # N+1 FIX: Use select_related for related objects
        order = orders_models.Order.objects.select_related(
            'business',
            'pickup_location'
        ).get(id=order_id)

        logger.info(f"DMS order {order_id} accessed by user {request.user.id}")
        serializer = ezzy_api_serializers.OrderSerializer(order)
        return Response(serializer.data, status=status.HTTP_200_OK)
    except orders_models.Order.DoesNotExist:
        logger.warning(f"Order {order_id} not found")
        return Response(
            {'error': 'Order not found'},
            status=status.HTTP_404_NOT_FOUND
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated, permissions.IsAdminUser])
def dms_tasks_list(request):
    """Get list of all delivery tasks for DMS (staff only)"""
    logger.info(f"DMS tasks list requested by user {request.user.id}")

    # N+1 FIX: Use select_related for ForeignKey relationships
    tasks = delivery_models.DeliveryTask.objects.select_related(
        'order',
        'order__business',
        'order__client',
        'driver',
        'business'
    ).all().order_by('-created_at')

    # Filters
    status_filter = request.query_params.get('status', None)
    driver_filter = request.query_params.get('driver_id', None)
    date_from = request.query_params.get('date_from', None)
    date_to = request.query_params.get('date_to', None)

    if status_filter:
        tasks = tasks.filter(dl_task_status=status_filter)

    if driver_filter:
        tasks = tasks.filter(driver_id=driver_filter)

    if date_from:
        try:
            date_obj = datetime.strptime(date_from, '%Y-%m-%d').date()
            tasks = tasks.filter(dl_task_date__gte=date_obj)
        except ValueError:
            logger.warning(f"Invalid date_from format: {date_from}")
            pass

    if date_to:
        try:
            date_obj = datetime.strptime(date_to, '%Y-%m-%d').date()
            tasks = tasks.filter(dl_task_date__lte=date_obj)
        except ValueError:
            logger.warning(f"Invalid date_to format: {date_to}")
            pass

    serializer = ezzy_api_serializers.DeliveryTaskSerializer(tasks, many=True)
    logger.info(f"Returned {len(tasks)} tasks for DMS")
    return Response(serializer.data, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsAuthenticated, permissions.IsAdminUser])
def dms_task_detail(request, task_id):
    """Get detailed information about a specific task (staff only)"""
    try:
        # N+1 FIX: Use select_related for related objects
        task = delivery_models.DeliveryTask.objects.select_related(
            'order',
            'order__business',
            'order__client',
            'driver',
            'business'
        ).get(id=task_id)

        logger.info(f"DMS task {task_id} accessed by user {request.user.id}")
        serializer = ezzy_api_serializers.DeliveryTaskSerializer(task)
        return Response(serializer.data, status=status.HTTP_200_OK)
    except delivery_models.DeliveryTask.DoesNotExist:
        return Response(
            {'error': 'Task not found'},
            status=status.HTTP_404_NOT_FOUND
        )


@api_view(['POST'])
@permission_classes([IsAuthenticated, permissions.IsAdminUser])
def dms_assign_task(request):
    """Assign a task to a driver (staff only)"""
    serializer = ezzy_api_serializers.TaskAssignmentSerializer(data=request.data)
    
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    task_id = serializer.validated_data['task_id']
    driver_id = serializer.validated_data['driver_id']
    
    try:
        task = delivery_models.DeliveryTask.objects.get(id=task_id)
        driver = fleet_models.Driver.objects.get(driver_id=driver_id)
        
        if driver.driver_status != 'approved':
            return Response(
                {'error': 'Driver is not approved'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        task.driver = driver
        task.dl_task_status = 'publish_to_dms'
        task.dl_task_status_dms = '0'  # Assigned
        task.dl_task_publish = True
        task.save()
        
        # Create assigned driver record
        delivery_models.AssignedDriver.objects.get_or_create(
            driver=driver,
            dl_task=task
        )
        
        task_serializer = ezzy_api_serializers.DeliveryTaskSerializer(task)
        return Response({
            'message': 'Task assigned successfully',
            'task': task_serializer.data
        }, status=status.HTTP_200_OK)
    
    except delivery_models.DeliveryTask.DoesNotExist:
        return Response(
            {'error': 'Task not found'},
            status=status.HTTP_404_NOT_FOUND
        )
    except fleet_models.Driver.DoesNotExist:
        return Response(
            {'error': 'Driver not found'},
            status=status.HTTP_404_NOT_FOUND
        )


@api_view(['POST'])
@permission_classes([IsAuthenticated, permissions.IsAdminUser])
def dms_update_task_status(request):
    """Update task status from DMS (staff only)"""
    serializer = ezzy_api_serializers.TaskStatusUpdateSerializer(data=request.data)
    
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    task_id = serializer.validated_data['task_id']
    new_status = serializer.validated_data['status']
    dms_status = serializer.validated_data.get('dms_status')
    
    try:
        task = delivery_models.DeliveryTask.objects.select_related('order').get(id=task_id)

        # Lock check: Prevent status change if order is cancelled
        if task.order and task.order.order_status == 'cancelled':
            return Response({
                'error': 'Task is locked. Order is cancelled — no delivery status changes allowed.'
            }, status=status.HTTP_403_FORBIDDEN)

        # Lock check: Prevent status change if order is not verified
        if task.order and task.order.verification_status != 'verified':
            return Response({
                'error': 'Task is locked. Order must be verified before delivery status can be updated.'
            }, status=status.HTTP_403_FORBIDDEN)

        # Lock check: Prevent status change on settled tasks
        if task.dl_task_status_dms == '2' and task.order and task.order.cod_status_by_staff == 'cod_settled_with_business':
            return Response({
                'error': 'Task is locked. Status cannot be changed after delivery is successful and COD is settled.'
            }, status=status.HTTP_403_FORBIDDEN)

        task.dl_task_status = new_status

        if dms_status:
            task.dl_task_status_dms = dms_status

        task.save()

        task_serializer = ezzy_api_serializers.DeliveryTaskSerializer(task)
        return Response({
            'message': 'Task status updated successfully',
            'task': task_serializer.data
        }, status=status.HTTP_200_OK)

    except delivery_models.DeliveryTask.DoesNotExist:
        return Response(
            {'error': 'Task not found'},
            status=status.HTTP_404_NOT_FOUND
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated, permissions.IsAdminUser])
def dms_drivers_list(request):
    """Get list of all drivers for DMS (staff only)"""
    drivers = fleet_models.Driver.objects.all()
    
    # Filters
    status_filter = request.query_params.get('status', None)
    
    if status_filter:
        drivers = drivers.filter(driver_status=status_filter)
    
    serializer = ezzy_api_serializers.DriverListSerializer(drivers, many=True)
    return Response(serializer.data, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsAuthenticated, permissions.IsAdminUser])
def dms_driver_detail(request, driver_id):
    """Get detailed information about a specific driver (staff only)"""
    try:
        driver = fleet_models.Driver.objects.get(driver_id=driver_id)
        serializer = ezzy_api_serializers.DriverSerializer(driver)
        return Response(serializer.data, status=status.HTTP_200_OK)
    except fleet_models.Driver.DoesNotExist:
        return Response(
            {'error': 'Driver not found'},
            status=status.HTTP_404_NOT_FOUND
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated, permissions.IsAdminUser])
def dms_analytics(request):
    """Get analytics data for DMS dashboard (staff only)"""
    # Date range from query params
    start_date = request.query_params.get('start_date', None)
    end_date = request.query_params.get('end_date', None)
    
    # Default to last 30 days if not provided
    if not start_date:
        start_date = (timezone.now() - timedelta(days=30)).date()
    else:
        start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
    
    if not end_date:
        end_date = timezone.now().date()
    else:
        end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
    
    # Orders analytics
    orders = orders_models.Order.objects.filter(order_date__range=[start_date, end_date])
    total_orders = orders.count()
    completed_orders = orders.filter(order_status='publish').count()
    
    # Tasks analytics
    tasks = delivery_models.DeliveryTask.objects.filter(dl_task_date__range=[start_date, end_date])
    total_tasks = tasks.count()
    completed_tasks = tasks.filter(dl_task_status='delivered').count()
    in_progress_tasks = tasks.filter(dl_task_status='in_transit').count()
    pending_tasks = tasks.filter(dl_task_status__in=['pending', 'for_review']).count()
    
    # Revenue analytics
    total_revenue = tasks.filter(dl_task_status='delivered').aggregate(
        total=Sum('dl_price')
    )['total'] or 0
    
    # Driver analytics
    active_drivers = fleet_models.Driver.objects.filter(
        driver_status='approved'
    ).count()
    
    drivers_with_tasks = tasks.values('driver').distinct().count()
    
    analytics = {
        'date_range': {
            'start_date': start_date.isoformat(),
            'end_date': end_date.isoformat()
        },
        'orders': {
            'total': total_orders,
            'completed': completed_orders,
            'pending': total_orders - completed_orders
        },
        'tasks': {
            'total': total_tasks,
            'completed': completed_tasks,
            'in_progress': in_progress_tasks,
            'pending': pending_tasks
        },
        'revenue': {
            'total': total_revenue
        },
        'drivers': {
            'active': active_drivers,
            'with_tasks': drivers_with_tasks
        }
    }
    
    return Response(analytics, status=status.HTTP_200_OK)


# ==================== ENHANCED DRIVER APP TASK APIs ====================

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def driver_complete_task(request, task_id):
    """Driver completes a task with delivery proof, signature, and photos"""
    try:
        driver = fleet_models.Driver.objects.get(user=request.user)
        # Check if task is assigned to driver via DeliveryTask.driver OR AssignedDriver
        task = delivery_models.DeliveryTask.objects.select_related('order').filter(
            Q(driver=driver) | Q(assigneddriver__driver=driver),
            id=task_id
        ).distinct().first()
        if not task:
            # Check if task exists at all
            task_exists = delivery_models.DeliveryTask.objects.filter(id=task_id).exists()
            if task_exists:
                return Response(
                    {'error': f'Task {task_id} is not assigned to you ({driver.driver_name})'},
                    status=status.HTTP_403_FORBIDDEN
                )
            raise delivery_models.DeliveryTask.DoesNotExist()

        # Lock check: Prevent status change if order is cancelled
        if task.order and task.order.order_status == 'cancelled':
            return Response({
                'error': 'Task is locked. Order is cancelled — no delivery status changes allowed.'
            }, status=status.HTTP_403_FORBIDDEN)

        # Lock check: Prevent status change if order is not verified
        if task.order and task.order.verification_status != 'verified':
            return Response({
                'error': 'Task is locked. Order must be verified before delivery status can be updated.'
            }, status=status.HTTP_403_FORBIDDEN)

        # Lock check: Prevent status change if task is Successful AND COD is settled
        if task.dl_task_status_dms == '2' and task.order and task.order.cod_status_by_staff == 'cod_settled_with_business':
            return Response({
                'error': 'Task is locked. Status cannot be changed after delivery is successful and COD is settled.'
            }, status=status.HTTP_403_FORBIDDEN)

        serializer = ezzy_api_serializers.TaskCompletionSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        status_value = serializer.validated_data.get('status')
        notes = serializer.validated_data.get('notes', '')
        cod_collected = serializer.validated_data.get('cod_collected', False)
        cod_amount_collected = serializer.validated_data.get('cod_amount_collected')
        
        # Update task status with DMS mapping
        task.dl_task_status = status_value
        DMS_STATUS_MAP = {
            'accepted': '7',      # Accepted/Acknowledged
            'delivered': '2',     # Successful
            'cancelled': '9',     # Cancel
            'rejected': '8',      # Decline
            'failed': '3',        # Failed
        }
        if status_value in DMS_STATUS_MAP:
            task.dl_task_status_dms = DMS_STATUS_MAP[status_value]

        if status_value in ('delivered', 'failed', 'cancelled'):
            task.completed_at = timezone.now()

        # Track COD on task-level fields
        if cod_collected:
            task.cod_collected = True
            task.cod_collected_at = timezone.now()
        if cod_amount_collected:
            task.cod_collected_amount = cod_amount_collected

        task.save()

        # COD collection tracking (only on successful delivery)
        # Note: order status sync is handled by delivery/signals.py post_save
        if task.order and status_value == 'delivered' and cod_collected and cod_amount_collected:
            task.order.cod_status_by_staff = 'cod_with_driver'
            task.order.save(update_fields=['cod_status_by_staff'])
        
        # Upload documents
        documents_created = []
        if 'delivery_proof' in request.FILES:
            doc = ezzy_api_models.TaskDocument.objects.create(
                task=task,
                document_type='delivery_proof',
                document_file=request.FILES['delivery_proof'],
                uploaded_by=request.user,
                description=notes
            )
            documents_created.append(doc.id)
        
        if 'signature' in request.FILES:
            doc = ezzy_api_models.TaskDocument.objects.create(
                task=task,
                document_type='signature',
                document_file=request.FILES['signature'],
                uploaded_by=request.user
            )
            documents_created.append(doc.id)
        
        if 'photo' in request.FILES:
            doc = ezzy_api_models.TaskDocument.objects.create(
                task=task,
                document_type='photo',
                document_file=request.FILES['photo'],
                uploaded_by=request.user
            )
            documents_created.append(doc.id)
        
        # Trigger webhooks
        webhook_payload = {
            'task_id': task_id,
            'task_number': task.dl_task_number,
            'status': status_value,
            'cod_collected': cod_collected,
            'cod_amount_collected': cod_amount_collected,
            'notes': notes,
            'timestamp': timezone.now().isoformat(),
            'driver_id': driver.driver_id
        }
        _send_webhook_event('task_completed', webhook_payload, business=task.business)
        
        task_serializer = ezzy_api_serializers.DeliveryTaskSerializer(task)
        return Response({
            'message': 'Task completed successfully',
            'task': task_serializer.data,
            'documents_uploaded': documents_created
        }, status=status.HTTP_200_OK)
    
    except delivery_models.DeliveryTask.DoesNotExist:
        return Response(
            {'error': 'Task not found'},
            status=status.HTTP_404_NOT_FOUND
        )
    except fleet_models.Driver.DoesNotExist:
        return Response(
            {'error': 'Driver profile not found'},
            status=status.HTTP_404_NOT_FOUND
        )


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def driver_upload_task_document(request, task_id):
    """Driver uploads a document for a task"""
    try:
        driver = fleet_models.Driver.objects.get(user=request.user)
        # Check assignment via DeliveryTask.driver OR AssignedDriver
        task = delivery_models.DeliveryTask.objects.select_related('order').filter(
            Q(driver=driver) | Q(assigneddriver__driver=driver),
            id=task_id
        ).distinct().first()
        if not task:
            raise delivery_models.DeliveryTask.DoesNotExist()

        # Lock check: Prevent uploads on completed+settled tasks
        if task.dl_task_status_dms == '2' and task.order and task.order.cod_status_by_staff == 'cod_settled_with_business':
            return Response({
                'error': 'Task is locked. Documents cannot be uploaded after delivery is successful and COD is settled.'
            }, status=status.HTTP_403_FORBIDDEN)

        document_type = request.data.get('document_type', 'other')
        document_file = request.FILES.get('document_file')
        document_name = request.data.get('document_name', '')
        description = request.data.get('description', '')
        
        if not document_file:
            return Response(
                {'error': 'Document file is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        document = ezzy_api_models.TaskDocument.objects.create(
            task=task,
            document_type=document_type,
            document_file=document_file,
            document_name=document_name,
            description=description,
            uploaded_by=request.user
        )
        
        serializer = ezzy_api_serializers.TaskDocumentSerializer(document, context={'request': request})
        return Response({
            'message': 'Document uploaded successfully',
            'document': serializer.data
        }, status=status.HTTP_201_CREATED)
    
    except delivery_models.DeliveryTask.DoesNotExist:
        return Response(
            {'error': 'Task not found'},
            status=status.HTTP_404_NOT_FOUND
        )
    except fleet_models.Driver.DoesNotExist:
        return Response(
            {'error': 'Driver profile not found'},
            status=status.HTTP_404_NOT_FOUND
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def driver_task_documents(request, task_id):
    """Get all documents for a task"""
    try:
        driver = fleet_models.Driver.objects.get(user=request.user)
        task = delivery_models.DeliveryTask.objects.get(id=task_id, driver=driver)
        
        documents = ezzy_api_models.TaskDocument.objects.filter(task=task)
        serializer = ezzy_api_serializers.TaskDocumentSerializer(documents, many=True, context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK)
    
    except delivery_models.DeliveryTask.DoesNotExist:
        return Response(
            {'error': 'Task not found'},
            status=status.HTTP_404_NOT_FOUND
        )
    except fleet_models.Driver.DoesNotExist:
        return Response(
            {'error': 'Driver profile not found'},
            status=status.HTTP_404_NOT_FOUND
        )


# ==================== DMS DOCUMENT UPLOAD APIs ====================

@api_view(['POST'])
@permission_classes([IsAuthenticated, permissions.IsAdminUser])
def dms_upload_task_document(request, task_id):
    """Upload a document for a task (DMS, staff only)"""
    try:
        task = delivery_models.DeliveryTask.objects.get(id=task_id)
        
        document_type = request.data.get('document_type', 'other')
        document_file = request.FILES.get('document_file')
        document_name = request.data.get('document_name', '')
        description = request.data.get('description', '')
        
        if not document_file:
            return Response(
                {'error': 'Document file is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        document = ezzy_api_models.TaskDocument.objects.create(
            task=task,
            document_type=document_type,
            document_file=document_file,
            document_name=document_name,
            description=description,
            uploaded_by=request.user
        )
        
        serializer = ezzy_api_serializers.TaskDocumentSerializer(document, context={'request': request})
        return Response({
            'message': 'Document uploaded successfully',
            'document': serializer.data
        }, status=status.HTTP_201_CREATED)
    
    except delivery_models.DeliveryTask.DoesNotExist:
        return Response(
            {'error': 'Task not found'},
            status=status.HTTP_404_NOT_FOUND
        )


@api_view(['POST'])
@permission_classes([IsAuthenticated, permissions.IsAdminUser])
def dms_upload_order_document(request, order_id):
    """Upload a document for an order (DMS, staff only)"""
    try:
        order = orders_models.Order.objects.get(id=order_id)
        
        document_type = request.data.get('document_type', 'other')
        document_file = request.FILES.get('document_file')
        document_name = request.data.get('document_name', '')
        description = request.data.get('description', '')
        
        if not document_file:
            return Response(
                {'error': 'Document file is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        document = ezzy_api_models.OrderDocument.objects.create(
            order=order,
            document_type=document_type,
            document_file=document_file,
            document_name=document_name,
            description=description,
            uploaded_by=request.user
        )
        
        serializer = ezzy_api_serializers.OrderDocumentSerializer(document, context={'request': request})
        return Response({
            'message': 'Document uploaded successfully',
            'document': serializer.data
        }, status=status.HTTP_201_CREATED)
    
    except orders_models.Order.DoesNotExist:
        return Response(
            {'error': 'Order not found'},
            status=status.HTTP_404_NOT_FOUND
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated, permissions.IsAdminUser])
def dms_task_documents(request, task_id):
    """Get all documents for a task (DMS, staff only)"""
    try:
        task = delivery_models.DeliveryTask.objects.get(id=task_id)
        documents = ezzy_api_models.TaskDocument.objects.filter(task=task)
        serializer = ezzy_api_serializers.TaskDocumentSerializer(documents, many=True, context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK)
    except delivery_models.DeliveryTask.DoesNotExist:
        return Response(
            {'error': 'Task not found'},
            status=status.HTTP_404_NOT_FOUND
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated, permissions.IsAdminUser])
def dms_order_documents(request, order_id):
    """Get all documents for an order (DMS, staff only)"""
    try:
        order = orders_models.Order.objects.get(id=order_id)
        documents = ezzy_api_models.OrderDocument.objects.filter(order=order)
        serializer = ezzy_api_serializers.OrderDocumentSerializer(documents, many=True, context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK)
    except orders_models.Order.DoesNotExist:
        return Response(
            {'error': 'Order not found'},
            status=status.HTTP_404_NOT_FOUND
        )


# ==================== API KEY MANAGEMENT APIs ====================

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_api_key(request):
    """Create a new API key for a client"""
    try:
        serializer = ezzy_api_serializers.ClientApiKeyCreateSerializer(data=request.data)

        if not serializer.is_valid():
            logger.error(f"Serializer validation failed: {serializer.errors}")
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        business_id = serializer.validated_data['business_id']
        key_name = serializer.validated_data.get('key_name', '')
        expires_at = serializer.validated_data.get('expires_at')

        try:
            business = business_models.Business.objects.get(business_id=business_id)

            # Check if user has permission to create API keys for this business
            if not request.user.is_staff and business.user and business.user != request.user:
                logger.warning(f"User {request.user.id} denied permission to create API key for business {business_id}")
                return Response(
                    {'error': 'Permission denied. You do not have access to this business.'},
                    status=status.HTTP_403_FORBIDDEN
                )

            api_key = ezzy_api_models.ClientApiKey.objects.create(
                business=business,
                key_name=key_name,
                expires_at=expires_at,
                created_by=request.user
            )

            logger.info(f"API key created successfully for business {business_id} by user {request.user.id}")
            serializer = ezzy_api_serializers.ClientApiKeySerializer(api_key)
            return Response({
                'message': 'API key created successfully',
                'api_key': serializer.data
            }, status=status.HTTP_201_CREATED)

        except business_models.Business.DoesNotExist:
            logger.error(f"Business {business_id} not found")
            return Response(
                {'error': 'Business not found'},
                status=status.HTTP_404_NOT_FOUND
            )

    except Exception as e:
        logger.error(f"Error creating API key: {str(e)}", exc_info=True)
        return Response(
            {'error': f'An error occurred while creating the API key: {str(e)}'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def list_api_keys(request):
    """List all API keys for a business"""
    business_id = request.query_params.get('business_id', None)
    
    if business_id:
        try:
            business = business_models.Business.objects.get(business_id=business_id)
            # Check permission
            if not request.user.is_staff and business.user != request.user:
                return Response(
                    {'error': 'Permission denied'},
                    status=status.HTTP_403_FORBIDDEN
                )
            api_keys = ezzy_api_models.ClientApiKey.objects.filter(business=business)
        except business_models.Business.DoesNotExist:
            return Response(
                {'error': 'Business not found'},
                status=status.HTTP_404_NOT_FOUND
            )
    else:
        # If staff, show all; otherwise show only user's businesses
        if request.user.is_staff:
            api_keys = ezzy_api_models.ClientApiKey.objects.all()
        else:
            businesses = business_models.Business.objects.filter(user=request.user)
            api_keys = ezzy_api_models.ClientApiKey.objects.filter(business__in=businesses)
    
    serializer = ezzy_api_serializers.ClientApiKeySerializer(api_keys, many=True)
    return Response(serializer.data, status=status.HTTP_200_OK)


@api_view(['PUT', 'DELETE'])
@permission_classes([IsAuthenticated])
def manage_api_key(request, api_key_id):
    """Update or delete an API key"""
    try:
        api_key = ezzy_api_models.ClientApiKey.objects.get(id=api_key_id)
        
        # Check permission
        if not request.user.is_staff and api_key.business.user != request.user:
            return Response(
                {'error': 'Permission denied'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        if request.method == 'PUT':
            # Update API key (activate/deactivate)
            is_active = request.data.get('is_active', api_key.is_active)
            api_key.is_active = is_active
            api_key.save()
            
            serializer = ezzy_api_serializers.ClientApiKeySerializer(api_key)
            return Response({
                'message': 'API key updated successfully',
                'api_key': serializer.data
            }, status=status.HTTP_200_OK)
        
        elif request.method == 'DELETE':
            api_key.delete()
            return Response({
                'message': 'API key deleted successfully'
            }, status=status.HTTP_200_OK)
    
    except ezzy_api_models.ClientApiKey.DoesNotExist:
        return Response(
            {'error': 'API key not found'},
            status=status.HTTP_404_NOT_FOUND
        )


# ==================== E-COMMERCE INTEGRATION APIs ====================

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def import_shopify_orders(request):
    """Import orders from Shopify"""
    serializer = ezzy_api_serializers.ShopifyOrderImportSerializer(data=request.data)
    
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    business_id = serializer.validated_data['business_id']
    order_ids = serializer.validated_data.get('order_ids', [])
    start_date = serializer.validated_data.get('start_date')
    end_date = serializer.validated_data.get('end_date')
    limit = serializer.validated_data.get('limit', 50)
    
    try:
        business = business_models.Business.objects.get(business_id=business_id)
        api_settings = business_models.BusinessApiSettings.objects.filter(
            business=business,
            api_type='shopify',
            is_verify_api=True
        ).first()
        
        if not api_settings:
            return Response(
                {'error': 'Shopify API settings not found or not verified'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Initialize Shopify API
        shop_url = api_settings.site_api_url
        api_key = api_settings.api_key
        api_secret = api_settings.api_secret
        
        # Remove https:// and .myshopify.com if present
        shop_name = shop_url.replace('https://', '').replace('http://', '').replace('.myshopify.com', '').strip()
        
        session = shopify.Session(shop_name, api_settings.api_version or '2023-10')
        session.token = api_secret
        shopify.ShopifyResource.activate_session(session)
        
        imported_orders = []
        errors = []
        
        if order_ids:
            # Import specific orders
            for order_id in order_ids:
                try:
                    order = shopify.Order.find(order_id)
                    imported_order = _create_order_from_shopify(order, business)
                    if imported_order:
                        imported_orders.append(imported_order.id)
                except Exception as e:
                    errors.append(f"Order {order_id}: {str(e)}")
        else:
            # Import orders by date range
            orders = shopify.Order.find(limit=limit)
            if start_date:
                orders = [o for o in orders if o.created_at >= start_date.isoformat()]
            if end_date:
                orders = [o for o in orders if o.created_at <= end_date.isoformat()]
            
            for shopify_order in orders[:limit]:
                try:
                    imported_order = _create_order_from_shopify(shopify_order, business)
                    if imported_order:
                        imported_orders.append(imported_order.id)
                except Exception as e:
                    errors.append(f"Order {shopify_order.id}: {str(e)}")
        
        # Update integration status
        integration, created = ezzy_api_models.EcommerceIntegration.objects.get_or_create(
            business=business,
            platform='shopify',
            defaults={'api_settings': api_settings}
        )
        integration.last_sync = timezone.now()
        integration.sync_status = 'active' if not errors else 'error'
        integration.sync_error = '\n'.join(errors) if errors else None
        integration.total_orders_imported += len(imported_orders)
        integration.save()
        
        return Response({
            'message': f'Imported {len(imported_orders)} orders',
            'imported_order_ids': imported_orders,
            'errors': errors
        }, status=status.HTTP_200_OK)
    
    except business_models.Business.DoesNotExist:
        return Response(
            {'error': 'Business not found'},
            status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        return Response(
            {'error': f'Shopify import failed: {str(e)}'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def import_woocommerce_orders(request):
    """Import orders from WooCommerce"""
    serializer = ezzy_api_serializers.WooCommerceOrderImportSerializer(data=request.data)
    
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    business_id = serializer.validated_data['business_id']
    order_ids = serializer.validated_data.get('order_ids', [])
    start_date = serializer.validated_data.get('start_date')
    end_date = serializer.validated_data.get('end_date')
    status_filter = serializer.validated_data.get('status')
    limit = serializer.validated_data.get('limit', 50)
    
    try:
        business = business_models.Business.objects.get(business_id=business_id)
        api_settings = business_models.BusinessApiSettings.objects.filter(
            business=business,
            api_type='woocommerce',
            is_verify_api=True
        ).first()
        
        if not api_settings:
            return Response(
                {'error': 'WooCommerce API settings not found or not verified'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Initialize WooCommerce API
        wcapi = API(
            url=api_settings.site_api_url,
            consumer_key=api_settings.api_key,
            consumer_secret=api_settings.api_secret,
            version="wc/v3"
        )
        
        imported_orders = []
        errors = []
        
        if order_ids:
            # Import specific orders
            for order_id in order_ids:
                try:
                    response = wcapi.get(f"orders/{order_id}")
                    if response.status_code == 200:
                        order_data = response.json()
                        imported_order = _create_order_from_woocommerce(order_data, business)
                        if imported_order:
                            imported_orders.append(imported_order.id)
                    else:
                        errors.append(f"Order {order_id}: API error")
                except Exception as e:
                    errors.append(f"Order {order_id}: {str(e)}")
        else:
            # Import orders by date range
            params = {'per_page': limit}
            if status_filter:
                params['status'] = status_filter
            if start_date:
                params['after'] = start_date.isoformat()
            if end_date:
                params['before'] = end_date.isoformat()
            
            response = wcapi.get("orders", params=params)
            if response.status_code == 200:
                orders_data = response.json()
                for order_data in orders_data:
                    try:
                        imported_order = _create_order_from_woocommerce(order_data, business)
                        if imported_order:
                            imported_orders.append(imported_order.id)
                    except Exception as e:
                        errors.append(f"Order {order_data.get('id')}: {str(e)}")
            else:
                return Response(
                    {'error': f'WooCommerce API error: {response.text}'},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
        
        # Update integration status
        integration, created = ezzy_api_models.EcommerceIntegration.objects.get_or_create(
            business=business,
            platform='woocommerce',
            defaults={'api_settings': api_settings}
        )
        integration.last_sync = timezone.now()
        integration.sync_status = 'active' if not errors else 'error'
        integration.sync_error = '\n'.join(errors) if errors else None
        integration.total_orders_imported += len(imported_orders)
        integration.save()
        
        return Response({
            'message': f'Imported {len(imported_orders)} orders',
            'imported_order_ids': imported_orders,
            'errors': errors
        }, status=status.HTTP_200_OK)
    
    except business_models.Business.DoesNotExist:
        return Response(
            {'error': 'Business not found'},
            status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        return Response(
            {'error': f'WooCommerce import failed: {str(e)}'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def list_integrations(request):
    """List all e-commerce integrations"""
    business_id = request.query_params.get('business_id', None)
    
    if business_id:
        try:
            business = business_models.Business.objects.get(business_id=business_id)
            integrations = ezzy_api_models.EcommerceIntegration.objects.filter(business=business)
        except business_models.Business.DoesNotExist:
            return Response(
                {'error': 'Business not found'},
                status=status.HTTP_404_NOT_FOUND
            )
    else:
        if request.user.is_staff:
            integrations = ezzy_api_models.EcommerceIntegration.objects.all()
        else:
            businesses = business_models.Business.objects.filter(user=request.user)
            integrations = ezzy_api_models.EcommerceIntegration.objects.filter(business__in=businesses)
    
    serializer = ezzy_api_serializers.EcommerceIntegrationSerializer(integrations, many=True)
    return Response(serializer.data, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def import_tiktokshop_orders(request):
    """
    Import orders from TikTok Shop.

    Request body:
        - business_id: Business ID (required)
        - order_status: Filter by status (optional, e.g., AWAITING_SHIPMENT)
        - start_date: Start date for order filter (optional)
        - end_date: End date for order filter (optional)
        - limit: Max orders to import (optional, default 50)

    Returns:
        - imported_order_ids: List of imported order IDs
        - errors: List of error messages
    """
    from ezzy_api.tiktok_shop_service import TikTokShopService, create_order_from_tiktok, TikTokShopAPIError

    business_id = request.data.get('business_id')
    order_status = request.data.get('order_status')
    start_date = request.data.get('start_date')
    end_date = request.data.get('end_date')
    limit = request.data.get('limit', 50)

    if not business_id:
        return Response(
            {'error': 'business_id is required'},
            status=status.HTTP_400_BAD_REQUEST
        )

    try:
        business = business_models.Business.objects.get(business_id=business_id)
        api_settings = business_models.BusinessApiSettings.objects.filter(
            business=business,
            api_type='tiktokshop',
            is_verify_api=True
        ).first()

        if not api_settings:
            return Response(
                {'error': 'TikTok Shop API settings not found or not verified'},
                status=status.HTTP_404_NOT_FOUND
            )

        # Initialize TikTok Shop service
        service = TikTokShopService(api_settings)

        # Check if token needs refresh
        if api_settings.tiktok_token_expires_at:
            if timezone.now() >= api_settings.tiktok_token_expires_at - timedelta(hours=1):
                service.refresh_access_token()

        imported_orders = []
        errors = []

        # Convert dates to timestamps if provided
        create_time_from = None
        create_time_to = None
        if start_date:
            create_time_from = int(datetime.fromisoformat(start_date).timestamp())
        if end_date:
            create_time_to = int(datetime.fromisoformat(end_date).timestamp())

        # Fetch orders from TikTok Shop
        page_token = None
        total_imported = 0

        while total_imported < limit:
            try:
                result = service.get_orders(
                    order_status=order_status,
                    create_time_from=create_time_from,
                    create_time_to=create_time_to,
                    page_size=min(100, limit - total_imported),
                    page_token=page_token
                )

                orders = result.get('orders', [])
                if not orders:
                    break

                for tiktok_order in orders:
                    try:
                        order = create_order_from_tiktok(tiktok_order, business)
                        if order:
                            imported_orders.append(order.id)
                            total_imported += 1
                    except Exception as e:
                        errors.append(f"Order {tiktok_order.get('order_id')}: {str(e)}")

                page_token = result.get('next_page_token')
                if not page_token:
                    break

            except TikTokShopAPIError as e:
                errors.append(f"API Error: {e.message}")
                break

        # Update integration status
        integration, created = ezzy_api_models.EcommerceIntegration.objects.get_or_create(
            business=business,
            platform='tiktokshop',
            defaults={'api_settings': api_settings}
        )
        integration.last_sync = timezone.now()
        integration.sync_status = 'active' if not errors else 'error'
        integration.sync_error = '\n'.join(errors) if errors else None
        integration.total_orders_imported += len(imported_orders)
        integration.save()

        return Response({
            'message': f'Imported {len(imported_orders)} orders from TikTok Shop',
            'imported_order_ids': imported_orders,
            'errors': errors
        }, status=status.HTTP_200_OK)

    except business_models.Business.DoesNotExist:
        return Response(
            {'error': 'Business not found'},
            status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        return Response(
            {'error': f'TikTok Shop import failed: {str(e)}'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def test_tiktokshop_connection(request):
    """
    Test TikTok Shop API connection.

    Request body:
        - business_id: Business ID (required)

    Returns:
        - success: Boolean indicating connection success
        - message: Status message
    """
    from ezzy_api.tiktok_shop_service import TikTokShopService

    business_id = request.data.get('business_id')

    if not business_id:
        return Response(
            {'error': 'business_id is required'},
            status=status.HTTP_400_BAD_REQUEST
        )

    try:
        business = business_models.Business.objects.get(business_id=business_id)
        api_settings = business_models.BusinessApiSettings.objects.filter(
            business=business,
            api_type='tiktokshop'
        ).first()

        if not api_settings:
            return Response(
                {'error': 'TikTok Shop API settings not found'},
                status=status.HTTP_404_NOT_FOUND
            )

        # Test connection
        service = TikTokShopService(api_settings)
        result = service.test_connection()

        if result.get('success'):
            # Mark API as verified
            api_settings.is_verify_api = True
            api_settings.save()

        return Response(result, status=status.HTTP_200_OK)

    except business_models.Business.DoesNotExist:
        return Response(
            {'error': 'Business not found'},
            status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        return Response(
            {'success': False, 'message': f'Connection test failed: {str(e)}'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


# ==================== HELPER FUNCTIONS ====================

def _create_order_from_shopify(shopify_order, business):
    """Helper function to create an Order from Shopify order data"""
    try:
        # Generate unique order number
        order_number = f"SHOP-{shopify_order.id}"
        
        # Check if order already exists
        if orders_models.Order.objects.filter(order_number=order_number).exists():
            return None
        
        # Extract customer information
        customer = shopify_order.customer if hasattr(shopify_order, 'customer') else None
        shipping_address = shopify_order.shipping_address if hasattr(shopify_order, 'shipping_address') else None
        
        # Create order
        order = orders_models.Order.objects.create(
            order_number=order_number,
            business=business,
            client_order_code=str(shopify_order.order_number),
            customer_name=shipping_address.name if shipping_address else (customer.first_name + ' ' + customer.last_name if customer else ''),
            customer_phone=shipping_address.phone if shipping_address else '',
            customer_address=f"{shipping_address.address1 or ''} {shipping_address.city or ''} {shipping_address.province or ''}".strip() if shipping_address else '',
            cod_amount=int(float(shopify_order.total_price) * 100) if shopify_order.financial_status == 'pending' else 0,
            cod_status_by_client='pending' if shopify_order.financial_status == 'pending' else 'online_paid',
            order_status='to_review',
            order_date=datetime.strptime(shopify_order.created_at[:10], '%Y-%m-%d').date() if shopify_order.created_at else timezone.now().date()
        )
        
        return order
    except Exception as e:
        raise Exception(f"Error creating order: {str(e)}")


def _push_task_to_dms(delivery_task, retry_count=0, max_retries=3):
    """
    Push delivery task to DMS via API with error handling and retry logic

    Args:
        delivery_task: DeliveryTask instance to push
        retry_count: Current retry attempt (default: 0)
        max_retries: Maximum number of retry attempts (default: 3)

    Returns:
        dict: DMS response data if successful, None otherwise
    """
    from decouple import config
    import requests
    import logging
    import time

    logger = logging.getLogger(__name__)

    try:
        # Get DMS API configuration
        dms_api_url = config('DMS_API_URL', default='')
        dms_api_key = config('DMS_API_KEY', default='')

        if not dms_api_url or not dms_api_key:
            logger.warning("DMS API configuration not found in environment variables (DMS_API_URL, DMS_API_KEY)")
            return None

        # Prepare task data for DMS
        task_data = {
            'task_number': delivery_task.dl_task_number,
            'task_number_dms': delivery_task.dl_task_number_dms,
            'order_number': delivery_task.order.order_number if delivery_task.order else None,
            'customer_name': delivery_task.order.customer_name if delivery_task.order else None,
            'customer_phone': delivery_task.order.customer_phone if delivery_task.order else None,
            'customer_address': delivery_task.order.customer_address if delivery_task.order else None,
            'cod_amount': delivery_task.order.cod_amount if delivery_task.order else 0,
            'status': delivery_task.dl_task_status_dms,
            'business_id': delivery_task.business.business_id if delivery_task.business else None,
        }

        # Add address details if available
        if delivery_task.dl_address_update:
            task_data.update({
                'zone': delivery_task.dl_address_update.dl_zone,
                'street': delivery_task.dl_address_update.dl_street,
                'building': delivery_task.dl_address_update.dl_building,
                'latitude': str(delivery_task.dl_address_update.dl_latitude) if delivery_task.dl_address_update.dl_latitude else None,
                'longitude': str(delivery_task.dl_address_update.dl_longitude) if delivery_task.dl_address_update.dl_longitude else None,
            })

        # Send to DMS
        headers = {
            'Authorization': f'Bearer {dms_api_key}',
            'Content-Type': 'application/json'
        }

        logger.info(f"Pushing task {delivery_task.dl_task_number} to DMS (attempt {retry_count + 1}/{max_retries + 1})")

        response = requests.post(
            f"{dms_api_url}/tasks",
            json=task_data,
            headers=headers,
            timeout=10
        )

        if response.status_code in [200, 201]:
            # Update task with DMS response
            response_data = response.json()
            logger.info(f"Successfully pushed task {delivery_task.dl_task_number} to DMS")

            if 'dms_id' in response_data:
                delivery_task.dl_task_number_dms = response_data.get('dms_id', delivery_task.dl_task_number_dms)
                delivery_task.dl_task_publish = True
                delivery_task.save(update_fields=['dl_task_number_dms', 'dl_task_publish'])

            return response_data

        elif response.status_code >= 500 and retry_count < max_retries:
            # Server error - retry with exponential backoff
            wait_time = 2 ** retry_count  # Exponential backoff: 1s, 2s, 4s
            logger.warning(f"DMS API server error ({response.status_code}). Retrying in {wait_time}s...")
            time.sleep(wait_time)
            return _push_task_to_dms(delivery_task, retry_count + 1, max_retries)

        else:
            # Business error or max retries reached
            error_msg = f"DMS API error: {response.status_code} - {response.text}"
            logger.error(error_msg)
            return None

    except requests.exceptions.Timeout as e:
        logger.error(f"DMS API timeout for task {delivery_task.dl_task_number}: {str(e)}")
        if retry_count < max_retries:
            wait_time = 2 ** retry_count
            logger.info(f"Retrying after timeout in {wait_time}s...")
            time.sleep(wait_time)
            return _push_task_to_dms(delivery_task, retry_count + 1, max_retries)
        return None

    except requests.exceptions.ConnectionError as e:
        logger.error(f"DMS API connection error for task {delivery_task.dl_task_number}: {str(e)}")
        if retry_count < max_retries:
            wait_time = 2 ** retry_count
            logger.info(f"Retrying after connection error in {wait_time}s...")
            time.sleep(wait_time)
            return _push_task_to_dms(delivery_task, retry_count + 1, max_retries)
        return None

    except requests.exceptions.RequestException as e:
        logger.error(f"DMS API request error for task {delivery_task.dl_task_number}: {str(e)}")
        return None

    except Exception as e:
        logger.exception(f"Unexpected error pushing task {delivery_task.dl_task_number} to DMS: {str(e)}")
        return None


def _create_order_from_woocommerce(order_data, business):
    """Helper function to create an Order from WooCommerce order data"""
    try:
        # Generate unique order number
        order_number = f"WC-{order_data.get('id')}"
        
        # Check if order already exists
        if orders_models.Order.objects.filter(order_number=order_number).exists():
            return None
        
        # Extract shipping information
        shipping = order_data.get('shipping', {})
        billing = order_data.get('billing', {})
        
        # Create order
        order = orders_models.Order.objects.create(
            order_number=order_number,
            business=business,
            client_order_code=str(order_data.get('number', order_data.get('id'))),
            customer_name=f"{billing.get('first_name', '')} {billing.get('last_name', '')}".strip(),
            customer_phone=billing.get('phone', ''),
            customer_address=f"{shipping.get('address_1', '')} {shipping.get('city', '')} {shipping.get('state', '')}".strip(),
            cod_amount=int(float(order_data.get('total', 0)) * 100) if order_data.get('payment_method') == 'cod' else 0,
            cod_status_by_client='pending' if order_data.get('payment_method') == 'cod' else 'online_paid',
            order_status='to_review',
            order_date=datetime.strptime(order_data.get('date_created', '')[:10], '%Y-%m-%d').date() if order_data.get('date_created') else timezone.now().date()
        )
        
        return order
    except Exception as e:
        raise Exception(f"Error creating order: {str(e)}")


# ==================== WEBHOOK APIs ====================

def _verify_webhook_signature(payload, signature, secret):
    """Verify webhook signature"""
    expected_signature = hmac.new(
        secret.encode('utf-8'),
        payload.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(signature, expected_signature)


def _trigger_webhook(webhook, event_type, payload):
    """Trigger a webhook to the configured endpoint"""
    try:
        # Create signature
        payload_str = json.dumps(payload, sort_keys=True)
        signature = hmac.new(
            webhook.secret.encode('utf-8'),
            payload_str.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        
        # Prepare headers
        headers = {
            'Content-Type': 'application/json',
            'X-Webhook-Event': event_type,
            'X-Webhook-Signature': signature,
            'X-Webhook-Timestamp': str(int(timezone.now().timestamp()))
        }
        
        # Send webhook
        response = requests.post(
            webhook.url,
            json=payload,
            headers=headers,
            timeout=10
        )
        
        # Create delivery record
        delivery = ezzy_api_models.WebhookDelivery.objects.create(
            webhook=webhook,
            event_type=event_type,
            payload=payload,
            response_status=response.status_code,
            response_body=response.text[:1000],  # Limit response body length
            status='success' if 200 <= response.status_code < 300 else 'failed',
            error_message=None if 200 <= response.status_code < 300 else f"HTTP {response.status_code}",
            delivered_at=timezone.now() if 200 <= response.status_code < 300 else None
        )
        
        # Update webhook last triggered
        webhook.last_triggered = timezone.now()
        webhook.save(update_fields=['last_triggered'])
        
        return delivery
    
    except Exception as e:
        # Create failed delivery record
        delivery = ezzy_api_models.WebhookDelivery.objects.create(
            webhook=webhook,
            event_type=event_type,
            payload=payload,
            status='failed',
            error_message=str(e)
        )
        return delivery


def _send_webhook_event(event_type, payload, business=None):
    """Send webhook event to all active webhooks subscribed to the event"""
    webhooks = ezzy_api_models.WebhookEndpoint.objects.filter(
        is_active=True,
        events__contains=[event_type]
    )
    
    if business:
        webhooks = webhooks.filter(business=business)
    
    deliveries = []
    for webhook in webhooks:
        delivery = _trigger_webhook(webhook, event_type, payload)
        deliveries.append(delivery)
    
    return deliveries


@api_view(['POST'])
@permission_classes([AllowAny])
def webhook_receive_task_status_update(request):
    """Receive task status update webhook from driver app"""
    # Verify API key or signature
    api_key = request.headers.get('X-API-Key') or request.data.get('api_key')
    signature = request.headers.get('X-Webhook-Signature')
    
    if not api_key:
        return Response(
            {'error': 'API key is required'},
            status=status.HTTP_401_UNAUTHORIZED
        )
    
    try:
        # Verify API key
        client_api_key = ezzy_api_models.ClientApiKey.objects.get(api_key=api_key, is_active=True)
        if not client_api_key.is_valid():
            return Response(
                {'error': 'Invalid or expired API key'},
                status=status.HTTP_401_UNAUTHORIZED
            )
        
        # Update last used
        client_api_key.last_used = timezone.now()
        client_api_key.save(update_fields=['last_used'])
        
        # Validate payload
        serializer = ezzy_api_serializers.WebhookTaskStatusUpdateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        task_id = serializer.validated_data['task_id']
        new_status = serializer.validated_data['status']
        dms_status = serializer.validated_data.get('dms_status')
        notes = serializer.validated_data.get('notes', '')
        driver_id = serializer.validated_data.get('driver_id')
        
        # Update task
        try:
            task = delivery_models.DeliveryTask.objects.select_related('order').get(id=task_id)

            # Lock check: Prevent status change if order is cancelled
            if task.order and task.order.order_status == 'cancelled':
                return Response({
                    'error': 'Task is locked. Order is cancelled — no delivery status changes allowed.'
                }, status=status.HTTP_403_FORBIDDEN)

            # Lock check: Prevent status change if order is not verified
            if task.order and task.order.verification_status != 'verified':
                return Response({
                    'error': 'Task is locked. Order must be verified before delivery status can be updated.'
                }, status=status.HTTP_403_FORBIDDEN)

            # Lock check: Prevent status change if task is Successful AND COD is settled
            if task.dl_task_status_dms == '2' and task.order and task.order.cod_status_by_staff == 'cod_settled_with_business':
                return Response({
                    'error': 'Task is locked. Status cannot be changed after delivery is successful and COD is settled.'
                }, status=status.HTTP_403_FORBIDDEN)

            # Verify driver if provided
            if driver_id:
                driver = fleet_models.Driver.objects.get(driver_id=driver_id)
                if task.driver != driver:
                    return Response(
                        {'error': 'Driver mismatch'},
                        status=status.HTTP_400_BAD_REQUEST
                    )

            task.dl_task_status = new_status
            if dms_status:
                task.dl_task_status_dms = dms_status
            task.save()
            
            # Trigger webhooks for other subscribers
            webhook_payload = {
                'task_id': task_id,
                'task_number': task.dl_task_number,
                'status': new_status,
                'dms_status': dms_status or task.dl_task_status_dms,
                'notes': notes,
                'timestamp': timezone.now().isoformat(),
                'driver_id': driver_id
            }
            _send_webhook_event('task_status_update', webhook_payload, business=task.business)
            
            return Response({
                'message': 'Task status updated successfully',
                'task_id': task_id,
                'status': new_status
            }, status=status.HTTP_200_OK)
        
        except delivery_models.DeliveryTask.DoesNotExist:
            return Response(
                {'error': 'Task not found'},
                status=status.HTTP_404_NOT_FOUND
            )
    
    except ezzy_api_models.ClientApiKey.DoesNotExist:
        return Response(
            {'error': 'Invalid API key'},
            status=status.HTTP_401_UNAUTHORIZED
        )


@api_view(['POST'])
@permission_classes([AllowAny])
def webhook_receive_task_completion(request):
    """Receive task completion webhook from driver app"""
    api_key = request.headers.get('X-API-Key') or request.data.get('api_key')
    
    if not api_key:
        return Response(
            {'error': 'API key is required'},
            status=status.HTTP_401_UNAUTHORIZED
        )
    
    try:
        client_api_key = ezzy_api_models.ClientApiKey.objects.get(api_key=api_key, is_active=True)
        if not client_api_key.is_valid():
            return Response(
                {'error': 'Invalid or expired API key'},
                status=status.HTTP_401_UNAUTHORIZED
            )
        
        client_api_key.last_used = timezone.now()
        client_api_key.save(update_fields=['last_used'])
        
        serializer = ezzy_api_serializers.WebhookTaskCompletionSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        task_id = serializer.validated_data['task_id']
        status_value = serializer.validated_data['status']
        cod_collected = serializer.validated_data.get('cod_collected', False)
        cod_amount_collected = serializer.validated_data.get('cod_amount_collected')
        notes = serializer.validated_data.get('notes', '')
        driver_id = serializer.validated_data.get('driver_id')
        
        try:
            with transaction.atomic():
                task = delivery_models.DeliveryTask.objects.select_related('order', 'order__business').select_for_update().get(id=task_id)

                # Lock check: Prevent status change if order is cancelled
                if task.order and task.order.order_status == 'cancelled':
                    return Response({
                        'error': 'Task is locked. Order is cancelled — no delivery status changes allowed.'
                    }, status=status.HTTP_403_FORBIDDEN)

                # Lock check: Prevent status change if order is not verified
                if task.order and task.order.verification_status != 'verified':
                    return Response({
                        'error': 'Task is locked. Order must be verified before delivery status can be updated.'
                    }, status=status.HTTP_403_FORBIDDEN)

                # Lock check: Prevent status change if task is Successful AND COD is settled
                if task.dl_task_status_dms == '2' and task.order and task.order.cod_status_by_staff == 'cod_settled_with_business':
                    return Response({
                        'error': 'Task is locked. Status cannot be changed after delivery is successful and COD is settled.'
                    }, status=status.HTTP_403_FORBIDDEN)

                if driver_id:
                    driver = fleet_models.Driver.objects.get(driver_id=driver_id)
                    if task.driver != driver:
                        return Response(
                            {'error': 'Driver mismatch'},
                            status=status.HTTP_400_BAD_REQUEST
                        )

                task.dl_task_status = status_value
                if status_value == 'delivered':
                    task.dl_task_status_dms = '2'
                    task.completed_at = timezone.now()
                elif status_value in ('failed', 'cancelled'):
                    task.dl_task_status_dms = '9' if status_value == 'cancelled' else '3'
                    task.completed_at = timezone.now()
                elif status_value == 'rejected':
                    task.dl_task_status_dms = '8'

                # Track COD on task-level fields
                if cod_collected:
                    task.cod_collected = True
                    task.cod_collected_at = timezone.now()
                if cod_amount_collected:
                    task.cod_collected_amount = cod_amount_collected

                task.save()

                # Handle COD and update Order status
                if task.order:
                    order = task.order
                    order_changed = False
                    if cod_collected and cod_amount_collected:
                        order.cod_status_by_staff = 'cod_with_driver'
                        order_changed = True

                    # Auto-update Order status based on delivery completion
                    if status_value == 'delivered':
                        if order.business and order.business.fulfillment_service_enabled:
                            order.order_status = 'fulfilled'
                            order.fulfilled_at = timezone.now()
                        else:
                            order.order_status = 'delivered'
                        order.delivered_at = timezone.now()
                        order_changed = True
                    elif status_value in ('cancelled', 'failed'):
                        order.order_status = 'cancelled'
                        order_changed = True

                    if order_changed:
                        order.save()
            
            # Trigger webhooks
            webhook_payload = {
                'task_id': task_id,
                'task_number': task.dl_task_number,
                'status': status_value,
                'cod_collected': cod_collected,
                'cod_amount_collected': cod_amount_collected,
                'notes': notes,
                'timestamp': timezone.now().isoformat(),
                'driver_id': driver_id
            }
            _send_webhook_event('task_completed', webhook_payload, business=task.business)
            
            return Response({
                'message': 'Task completed successfully',
                'task_id': task_id,
                'status': status_value
            }, status=status.HTTP_200_OK)
        
        except delivery_models.DeliveryTask.DoesNotExist:
            return Response(
                {'error': 'Task not found'},
                status=status.HTTP_404_NOT_FOUND
            )
    
    except ezzy_api_models.ClientApiKey.DoesNotExist:
        return Response(
            {'error': 'Invalid API key'},
            status=status.HTTP_401_UNAUTHORIZED
        )


@api_view(['POST'])
@permission_classes([AllowAny])
def webhook_receive_driver_location(request):
    """Receive driver location update webhook from driver app"""
    api_key = request.headers.get('X-API-Key') or request.data.get('api_key')
    
    if not api_key:
        return Response(
            {'error': 'API key is required'},
            status=status.HTTP_401_UNAUTHORIZED
        )
    
    try:
        client_api_key = ezzy_api_models.ClientApiKey.objects.get(api_key=api_key, is_active=True)
        if not client_api_key.is_valid():
            return Response(
                {'error': 'Invalid or expired API key'},
                status=status.HTTP_401_UNAUTHORIZED
            )
        
        client_api_key.last_used = timezone.now()
        client_api_key.save(update_fields=['last_used'])
        
        serializer = ezzy_api_serializers.WebhookDriverLocationSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        driver_id = serializer.validated_data['driver_id']
        latitude = serializer.validated_data['latitude']
        longitude = serializer.validated_data['longitude']
        timestamp = serializer.validated_data.get('timestamp', timezone.now())
        
        try:
            driver = fleet_models.Driver.objects.get(driver_id=driver_id)
            
            # Store location (you can create a DriverLocation model for tracking history)
            # For now, we'll just trigger webhooks
            
            webhook_payload = {
                'driver_id': driver_id,
                'driver_code': driver.driver_code,
                'latitude': float(latitude),
                'longitude': float(longitude),
                'timestamp': timestamp.isoformat() if hasattr(timestamp, 'isoformat') else str(timestamp),
                'accuracy': serializer.validated_data.get('accuracy'),
                'speed': serializer.validated_data.get('speed')
            }
            _send_webhook_event('driver_location_update', webhook_payload, business=None)
            
            return Response({
                'message': 'Location updated successfully',
                'driver_id': driver_id
            }, status=status.HTTP_200_OK)
        
        except fleet_models.Driver.DoesNotExist:
            return Response(
                {'error': 'Driver not found'},
                status=status.HTTP_404_NOT_FOUND
            )
    
    except ezzy_api_models.ClientApiKey.DoesNotExist:
        return Response(
            {'error': 'Invalid API key'},
            status=status.HTTP_401_UNAUTHORIZED
        )


# Webhook Management APIs
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_webhook_endpoint(request):
    """Create a new webhook endpoint"""
    serializer = ezzy_api_serializers.WebhookEndpointSerializer(data=request.data)
    
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    business_id = request.data.get('business')
    if business_id:
        try:
            business = business_models.Business.objects.get(business_id=business_id)
            if not request.user.is_staff and business.user != request.user:
                return Response(
                    {'error': 'Permission denied'},
                    status=status.HTTP_403_FORBIDDEN
                )
        except business_models.Business.DoesNotExist:
            return Response(
                {'error': 'Business not found'},
                status=status.HTTP_404_NOT_FOUND
            )
    
    webhook = serializer.save()
    return Response({
        'message': 'Webhook endpoint created successfully',
        'webhook': ezzy_api_serializers.WebhookEndpointSerializer(webhook).data
    }, status=status.HTTP_201_CREATED)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def list_webhook_endpoints(request):
    """List all webhook endpoints"""
    business_id = request.query_params.get('business_id', None)
    
    if business_id:
        try:
            business = business_models.Business.objects.get(business_id=business_id)
            if not request.user.is_staff and business.user != request.user:
                return Response(
                    {'error': 'Permission denied'},
                    status=status.HTTP_403_FORBIDDEN
                )
            webhooks = ezzy_api_models.WebhookEndpoint.objects.filter(business=business)
        except business_models.Business.DoesNotExist:
            return Response(
                {'error': 'Business not found'},
                status=status.HTTP_404_NOT_FOUND
            )
    else:
        if request.user.is_staff:
            webhooks = ezzy_api_models.WebhookEndpoint.objects.all()
        else:
            businesses = business_models.Business.objects.filter(user=request.user)
            webhooks = ezzy_api_models.WebhookEndpoint.objects.filter(business__in=businesses)
    
    serializer = ezzy_api_serializers.WebhookEndpointSerializer(webhooks, many=True)
    return Response(serializer.data, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def list_webhook_deliveries(request):
    """List webhook delivery history"""
    webhook_id = request.query_params.get('webhook_id', None)
    event_type = request.query_params.get('event_type', None)
    
    deliveries = ezzy_api_models.WebhookDelivery.objects.all()
    
    if webhook_id:
        deliveries = deliveries.filter(webhook_id=webhook_id)
    
    if event_type:
        deliveries = deliveries.filter(event_type=event_type)
    
    # Filter by business if not staff
    if not request.user.is_staff:
        businesses = business_models.Business.objects.filter(user=request.user)
        deliveries = deliveries.filter(webhook__business__in=businesses)
    
    serializer = ezzy_api_serializers.WebhookDeliverySerializer(deliveries[:100], many=True)
    return Response(serializer.data, status=status.HTTP_200_OK)


# ==================== ORDER VERIFICATION APIs ====================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def orders_pending_verification(request):
    """Get orders pending verification"""
    verification_status = request.query_params.get('verification_status', 'pending')
    business_id = request.query_params.get('business_id', None)
    
    orders = orders_models.Order.objects.filter(verification_status=verification_status)
    
    if business_id:
        orders = orders.filter(business_id=business_id)
    elif not request.user.is_staff:
        businesses = business_models.Business.objects.filter(user=request.user)
        orders = orders.filter(business__in=businesses)
    
    orders = orders.order_by('-created_at')
    serializer = ezzy_api_serializers.OrderListSerializer(orders, many=True)
    return Response(serializer.data, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def verify_order_address(request, order_id):
    """Verify order address"""
    try:
        order = orders_models.Order.objects.get(id=order_id)
        
        # Check permission
        if not request.user.is_staff and order.business.user != request.user:
            return Response(
                {'error': 'Permission denied'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        verified_address = request.data.get('verified_address', order.customer_address)
        verification_result = request.data.get('verification_result', 'valid')
        latitude = request.data.get('latitude')
        longitude = request.data.get('longitude')
        zone_number = request.data.get('zone_number')
        street_number = request.data.get('street_number')
        building_number = request.data.get('building_number')
        notes = request.data.get('notes', '')
        
        # Create or update address verification
        from orders.models import AddressVerification
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
        from orders.models import OrderVerificationLog
        OrderVerificationLog.objects.create(
            order=order,
            verified_by=request.user,
            action='address_verified',
            notes=notes,
            new_status=order.verification_status
        )
        
        return Response({
            'message': 'Address verified successfully',
            'order_id': order_id,
            'verification_status': order.verification_status
        }, status=status.HTTP_200_OK)
    
    except orders_models.Order.DoesNotExist:
        return Response(
            {'error': 'Order not found'},
            status=status.HTTP_404_NOT_FOUND
        )


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def verify_order(request, order_id):
    """Verify order and create delivery task"""
    try:
        order = orders_models.Order.objects.get(id=order_id)
        
        # Check permission
        if not request.user.is_staff:
            return Response(
                {'error': 'Only staff can verify orders'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        verification_notes = request.data.get('verification_notes', '')
        
        # Update order verification status
        order.verification_status = 'verified'
        order.verified_by = request.user
        order.verified_at = timezone.now()
        order.verification_notes = verification_notes
        order.save()
        
        # Log verification
        from orders.models import OrderVerificationLog
        OrderVerificationLog.objects.create(
            order=order,
            verified_by=request.user,
            action='order_verified',
            notes=verification_notes,
            new_status='verified'
        )
        
        # Create delivery task (will be triggered by signal)
        from orders.signals import _create_delivery_task_from_order
        delivery_task = _create_delivery_task_from_order(order)
        
        return Response({
            'message': 'Order verified successfully',
            'order_id': order_id,
            'task_created': order.task_created,
            'delivery_task_id': delivery_task.id if delivery_task else None
        }, status=status.HTTP_200_OK)
    
    except orders_models.Order.DoesNotExist:
        return Response(
            {'error': 'Order not found'},
            status=status.HTTP_404_NOT_FOUND
        )


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def reject_order(request, order_id):
    """Reject order"""
    try:
        order = orders_models.Order.objects.get(id=order_id)
        
        # Check permission
        if not request.user.is_staff:
            return Response(
                {'error': 'Only staff can reject orders'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        rejection_notes = request.data.get('rejection_notes', '')
        
        # Update order
        order.verification_status = 'rejected'
        order.verified_by = request.user
        order.verified_at = timezone.now()
        order.verification_notes = rejection_notes
        order.order_status = 'cancelled'
        order.save()
        
        # Log rejection
        from orders.models import OrderVerificationLog
        OrderVerificationLog.objects.create(
            order=order,
            verified_by=request.user,
            action='order_rejected',
            notes=rejection_notes,
            new_status='rejected'
        )
        
        return Response({
            'message': 'Order rejected successfully',
            'order_id': order_id
        }, status=status.HTTP_200_OK)
    
    except orders_models.Order.DoesNotExist:
        return Response(
            {'error': 'Order not found'},
            status=status.HTTP_404_NOT_FOUND
        )


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def push_task_to_dms_api(request, task_id):
    """Manually push delivery task to DMS"""
    try:
        task = delivery_models.DeliveryTask.objects.get(id=task_id)
        
        # Check permission
        if not request.user.is_staff:
            return Response(
                {'error': 'Only staff can push tasks to DMS'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        result = _push_task_to_dms(task)
        
        if result:
            return Response({
                'message': 'Task pushed to DMS successfully',
                'task_id': task_id,
                'dms_response': result
            }, status=status.HTTP_200_OK)
        else:
            return Response({
                'error': 'Failed to push task to DMS',
                'task_id': task_id
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    except delivery_models.DeliveryTask.DoesNotExist:
        return Response(
            {'error': 'Task not found'},
            status=status.HTTP_404_NOT_FOUND
        )


# ==================== BUSINESS APIs ====================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def business_dashboard_stats(request):
    """Get dashboard statistics for business"""
    business = get_api_user_business(request)
    if not business:
        logger.warning(f"Business not found for user {request.user.id}")
        return Response(
            {'error': 'Business not found'},
            status=status.HTTP_404_NOT_FOUND
        )
    try:
        logger.info(f"Fetching dashboard stats for business {business.business_id}")

        # Get date range from query params (default to last 30 days)
        from datetime import datetime, timedelta
        from django.db.models import Count, Q
        from django.utils import timezone

        days = int(request.query_params.get('days', 30))
        start_date = timezone.now() - timedelta(days=days)

        # Order statistics
        total_orders = orders_models.Order.objects.filter(business=business).count()
        pending_orders = orders_models.Order.objects.filter(
            business=business, order_status='pending'
        ).count()
        completed_orders = orders_models.Order.objects.filter(
            business=business, order_status='delivered'
        ).count()
        cancelled_orders = orders_models.Order.objects.filter(
            business=business, order_status='cancelled'
        ).count()

        # Recent orders (last N days)
        recent_orders = orders_models.Order.objects.filter(
            business=business, created_at__gte=start_date
        ).count()

        # Task statistics
        total_tasks = delivery_models.DeliveryTask.objects.filter(business=business).count()
        active_tasks = delivery_models.DeliveryTask.objects.filter(
            business=business, dl_task_status__in=['pending', 'in_transit', 'assigned']
        ).count()
        completed_tasks = delivery_models.DeliveryTask.objects.filter(
            business=business, dl_task_status='delivered'
        ).count()

        # Business statistics
        total_clients = business_models.Client.objects.filter(business=business).count()

        logger.info(f"Dashboard stats retrieved for business {business.business_id}")

        return Response({
            'business_id': business.business_id,
            'business_name': business.business_name,
            'period_days': days,
            'orders': {
                'total': total_orders,
                'pending': pending_orders,
                'completed': completed_orders,
                'cancelled': cancelled_orders,
                'recent': recent_orders
            },
            'tasks': {
                'total': total_tasks,
                'active': active_tasks,
                'completed': completed_tasks
            },
            'clients': {
                'total': total_clients
            }
        }, status=status.HTTP_200_OK)

    except Exception as e:
        logger.error(f"Error fetching dashboard stats: {e}")
        return Response(
            {'error': 'Error fetching dashboard statistics'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


# ==================== API TESTING UI ====================

@login_required(login_url='account_login')
def api_tester_view(request):
    """Render the API testing UI for clients"""
    logger.info(f"User {request.user.id} accessing API tester UI")
    return render(request, 'ezzy_api/api_tester.html')


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def business_orders_api(request):
    """
    GET: List all orders for business
    POST: Create new order
    """
    business = get_api_user_business(request)
    if not business:
        logger.warning(f"Business not found for user {request.user.id}")
        return Response(
            {'error': 'Business not found'},
            status=status.HTTP_404_NOT_FOUND
        )
    try:
        if request.method == 'GET':
            logger.info(f"Fetching orders for business {business.business_id}")

            # Filters
            status_filter = request.query_params.get('status')
            search = request.query_params.get('search')
            limit = int(request.query_params.get('limit', 50))
            offset = int(request.query_params.get('offset', 0))

            orders = orders_models.Order.objects.filter(
                business=business
            ).select_related('business', 'pickup_location', 'address_verified_by', 'verified_by')

            if status_filter:
                orders = orders.filter(order_status=status_filter)

            if search:
                orders = orders.filter(
                    Q(order_number__icontains=search) |
                    Q(client__client_name__icontains=search)
                )

            orders = orders.order_by('-created_at')[offset:offset + limit]

            data = []
            for order in orders:
                data.append({
                    'id': order.id,
                    'order_number': order.order_number,
                    'client_name': order.client.client_name if order.client else None,
                    'client_phone': order.client.client_phone if order.client else None,
                    'delivery_address': order.delivery_address,
                    'order_status': order.order_status,
                    'order_date': order.order_date,
                    'created_at': order.created_at,
                    'total_amount': str(order.total_amount) if hasattr(order, 'total_amount') else None
                })

            logger.info(f"Returned {len(data)} orders for business {business.business_id}")
            return Response({
                'count': len(data),
                'orders': data
            }, status=status.HTTP_200_OK)

        elif request.method == 'POST':
            logger.info(f"Creating new order for business {business.business_id}")

            # Required fields
            client_id = request.data.get('client_id')
            delivery_address = request.data.get('delivery_address')
            pickup_location_id = request.data.get('pickup_location_id')

            if not all([client_id, delivery_address]):
                return Response(
                    {'error': 'client_id and delivery_address are required'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Verify business belongs to business
            try:
                business = business_models.Client.objects.get(
                    id=client_id, business=business
                )
            except business_models.Client.DoesNotExist:
                return Response(
                    {'error': 'Client not found'},
                    status=status.HTTP_404_NOT_FOUND
                )

            # Create order
            order = orders_models.Order.objects.create(
                business=business,
                client=client,
                delivery_address=delivery_address,
                pickup_location_id=pickup_location_id,
                order_status='pending',
                created_by=request.user
            )

            logger.info(f"Order {order.order_number} created successfully")

            return Response({
                'message': 'Order created successfully',
                'order': {
                    'id': order.id,
                    'order_number': order.order_number,
                    'status': order.order_status
                }
            }, status=status.HTTP_201_CREATED)

    except business_models.Business.DoesNotExist:
        logger.warning(f"Business not found for user {request.user.id}")
        return Response(
            {'error': 'Business not found'},
            status=status.HTTP_404_NOT_FOUND
        )


# ==================== API TESTING UI ====================

@login_required(login_url='account_login')
def api_tester_view(request):
    """Render the API testing UI for clients"""
    logger.info(f"User {request.user.id} accessing API tester UI")
    return render(request, 'ezzy_api/api_tester.html')


@api_view(['GET', 'PUT', 'DELETE'])
@permission_classes([IsAuthenticated])
def business_order_detail_api(request, order_id):
    """
    GET: Get order details
    PUT: Update order
    DELETE: Delete order
    """
    business = get_api_user_business(request)
    if not business:
        logger.warning(f"Business not found for user {request.user.id}")
        return Response(
            {'error': 'Business not found'},
            status=status.HTTP_404_NOT_FOUND
        )
    try:
        order = orders_models.Order.objects.select_related(
            'client', 'pickup_location', 'business'
        ).get(id=order_id, business=business)

        if request.method == 'GET':
            logger.info(f"User {request.user.id} viewing order {order_id}")

            return Response({
                'id': order.id,
                'order_number': order.order_number,
                'client': {
                    'id': order.client.id,
                    'name': order.client.client_name,
                    'phone': order.client.client_phone,
                    'email': order.client.client_email
                } if order.client else None,
                'delivery_address': order.delivery_address,
                'pickup_location': {
                    'id': order.pickup_location.id,
                    'name': order.pickup_location.pickup_name
                } if order.pickup_location else None,
                'order_status': order.order_status,
                'order_date': order.order_date,
                'created_at': order.created_at,
                'notes': order.order_notes if hasattr(order, 'order_notes') else None
            }, status=status.HTTP_200_OK)

        elif request.method == 'PUT':
            logger.info(f"User {request.user.id} updating order {order_id}")

            # Check if order can be updated
            if order.task_status == 'dl_task_listed':
                return Response(
                    {'error': 'Cannot update order published in delivery tasks'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Update allowed fields
            if 'delivery_address' in request.data:
                order.delivery_address = request.data['delivery_address']
            if 'order_status' in request.data:
                order.order_status = request.data['order_status']
            if 'order_notes' in request.data and hasattr(order, 'order_notes'):
                order.order_notes = request.data['order_notes']

            order.save()
            logger.info(f"Order {order_id} updated successfully")

            return Response({
                'message': 'Order updated successfully',
                'order_id': order.id
            }, status=status.HTTP_200_OK)

        elif request.method == 'DELETE':
            logger.info(f"User {request.user.id} deleting order {order_id}")
            order.delete()
            logger.info(f"Order {order_id} deleted successfully")

            return Response({
                'message': 'Order deleted successfully'
            }, status=status.HTTP_200_OK)

    except orders_models.Order.DoesNotExist:
        logger.warning(f"Order {order_id} not found or unauthorized")
        return Response(
            {'error': 'Order not found'},
            status=status.HTTP_404_NOT_FOUND
        )
    except business_models.Business.DoesNotExist:
        logger.warning(f"Business not found for user {request.user.id}")
        return Response(
            {'error': 'Business not found'},
            status=status.HTTP_404_NOT_FOUND
        )


# ==================== API TESTING UI ====================

@login_required(login_url='account_login')
def api_tester_view(request):
    """Render the API testing UI for clients"""
    logger.info(f"User {request.user.id} accessing API tester UI")
    return render(request, 'ezzy_api/api_tester.html')


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def business_clients_api(request):
    """
    GET: List all clients for business
    POST: Create new client
    """
    business = get_api_user_business(request)
    if not business:
        logger.warning(f"Business not found for user {request.user.id}")
        return Response(
            {'error': 'Business not found'},
            status=status.HTTP_404_NOT_FOUND
        )
    try:
        if request.method == 'GET':
            logger.info(f"Fetching clients for business {business.business_id}")

            search = request.query_params.get('search')
            limit = int(request.query_params.get('limit', 50))
            offset = int(request.query_params.get('offset', 0))

            clients = business_models.Client.objects.filter(business=business)

            if search:
                clients = clients.filter(
                    Q(client_name__icontains=search) |
                    Q(client_phone__icontains=search) |
                    Q(client_email__icontains=search)
                )

            clients = clients.order_by('-created_at')[offset:offset + limit]

            data = []
            for business in clients:
                data.append({
                    'id': client.id,
                    'name': client.client_name,
                    'phone': client.client_phone,
                    'email': client.client_email,
                    'address': client.client_address if hasattr(client, 'client_address') else None,
                    'created_at': client.created_at
                })

            logger.info(f"Returned {len(data)} clients")
            return Response({
                'count': len(data),
                'clients': data
            }, status=status.HTTP_200_OK)

        elif request.method == 'POST':
            logger.info(f"Creating new business for business {business.business_id}")

            client_name = request.data.get('name')
            client_phone = request.data.get('phone')

            if not all([client_name, client_phone]):
                return Response(
                    {'error': 'name and phone are required'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            business = business_models.Client.objects.create(
                business=business,
                client_name=client_name,
                client_phone=client_phone,
                client_email=request.data.get('email', '')
            )

            logger.info(f"Client {client.id} created successfully")

            return Response({
                'message': 'Client created successfully',
                'client': {
                    'id': client.id,
                    'name': client.client_name,
                    'phone': client.client_phone
                }
            }, status=status.HTTP_201_CREATED)

    except business_models.Business.DoesNotExist:
        logger.warning(f"Business not found for user {request.user.id}")
        return Response(
            {'error': 'Business not found'},
            status=status.HTTP_404_NOT_FOUND
        )


# ==================== API TESTING UI ====================

@login_required(login_url='account_login')
def api_tester_view(request):
    """Render the API testing UI for clients"""
    logger.info(f"User {request.user.id} accessing API tester UI")
    return render(request, 'ezzy_api/api_tester.html')


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def business_tasks_api(request):
    """Get all delivery tasks for business"""
    business = get_api_user_business(request)
    if not business:
        logger.warning(f"Business not found for user {request.user.id}")
        return Response(
            {'error': 'Business not found'},
            status=status.HTTP_404_NOT_FOUND
        )
    try:
        logger.info(f"Fetching tasks for business {business.business_id}")

        # Filters
        status_filter = request.query_params.get('status')
        driver_id = request.query_params.get('driver_id')
        limit = int(request.query_params.get('limit', 50))
        offset = int(request.query_params.get('offset', 0))

        tasks = delivery_models.DeliveryTask.objects.filter(
            business=business
        ).select_related('order', 'driver', 'order__client')

        if status_filter:
            tasks = tasks.filter(dl_task_status=status_filter)

        if driver_id:
            tasks = tasks.filter(driver_id=driver_id)

        tasks = tasks.order_by('-created_at')[offset:offset + limit]

        data = []
        for task in tasks:
            data.append({
                'id': task.id,
                'task_number': task.dl_task_number,
                'order_number': task.order.order_number if task.order else None,
                'client_name': task.order.client.client_name if task.order and task.order.client else None,
                'delivery_address': task.dl_delivery_address if hasattr(task, 'dl_delivery_address') else None,
                'status': task.dl_task_status,
                'driver': {
                    'id': task.driver.driver_id,
                    'name': task.driver.driver_name
                } if task.driver else None,
                'task_date': task.dl_task_date,
                'created_at': task.created_at
            })

        logger.info(f"Returned {len(data)} tasks")
        return Response({
            'count': len(data),
            'tasks': data
        }, status=status.HTTP_200_OK)

    except business_models.Business.DoesNotExist:
        logger.warning(f"Business not found for user {request.user.id}")
        return Response(
            {'error': 'Business not found'},
            status=status.HTTP_404_NOT_FOUND
        )


# ==================== API TESTING UI ====================

@login_required(login_url='account_login')
def api_tester_view(request):
    """Render the API testing UI for clients"""
    logger.info(f"User {request.user.id} accessing API tester UI")
    return render(request, 'ezzy_api/api_tester.html')


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def business_pickup_locations_api(request):
    """Get all pickup locations for business"""
    business = get_api_user_business(request)
    if not business:
        logger.warning(f"Business not found for user {request.user.id}")
        return Response(
            {'error': 'Business not found'},
            status=status.HTTP_404_NOT_FOUND
        )
    try:
        logger.info(f"Fetching pickup locations for business {business.business_id}")

        locations = business_models.PickupLocation.objects.filter(
            business_id=business.business_id
        ).order_by('pickup_name')

        data = []
        for location in locations:
            data.append({
                'id': location.id,
                'name': location.pickup_name,
                'address': location.pickup_address if hasattr(location, 'pickup_address') else None,
                'zone': location.pickup_zone_no if hasattr(location, 'pickup_zone_no') else None,
                'latitude': location.pickup_latitude if hasattr(location, 'pickup_latitude') else None,
                'longitude': location.pickup_longitude if hasattr(location, 'pickup_longitude') else None
            })

        logger.info(f"Returned {len(data)} pickup locations")
        return Response({
            'count': len(data),
            'locations': data
        }, status=status.HTTP_200_OK)

    except business_models.Business.DoesNotExist:
        logger.warning(f"Business not found for user {request.user.id}")
        return Response(
            {'error': 'Business not found'},
            status=status.HTTP_404_NOT_FOUND
        )


# ==================== QNAS PROXY APIs ====================
# These endpoints proxy requests to QNAS API (qnas.qa)
# Cloudflare protection requires browser cookies to be forwarded

QNAS_BASE_URL = "https://qnas.qa"
QNAS_TOKEN = config("QNAS_TOKEN", default="")
QNAS_DOMAIN = config("QNAS_DOMAIN", default="ezzydelivery.qa")


def _make_qnas_request(request, endpoint, method='GET', data=None):
    """
    Helper function to make requests to QNAS API with proper headers and cookies.
    Forwards browser cookies to bypass Cloudflare protection.
    """
    url = f"{QNAS_BASE_URL}/{endpoint}"

    headers = {
        "X-Token": QNAS_TOKEN,
        "X-Domain": QNAS_DOMAIN,
        "Accept": "application/json",
        "User-Agent": request.META.get("HTTP_USER_AGENT", "Mozilla/5.0"),
        "Referer": f"https://{QNAS_DOMAIN}/",
        "Origin": f"https://{QNAS_DOMAIN}",
    }

    # Forward browser cookies (critical for Cloudflare bypass)
    cookies = request.COOKIES

    try:
        if method == 'GET':
            resp = requests.get(url, headers=headers, cookies=cookies, timeout=15)
        elif method == 'POST':
            headers["Content-Type"] = "application/json"
            resp = requests.post(url, headers=headers, cookies=cookies, json=data, timeout=15)
        else:
            resp = requests.request(method, url, headers=headers, cookies=cookies, json=data, timeout=15)

        return resp
    except requests.exceptions.Timeout:
        logger.error(f"QNAS API timeout for endpoint: {endpoint}")
        return None
    except requests.exceptions.RequestException as e:
        logger.error(f"QNAS API request error for endpoint {endpoint}: {str(e)}")
        return None


@csrf_exempt
def qnas_get_zones(request):
    """
    Proxy endpoint for QNAS get_zones API.

    Frontend must call with credentials:
    fetch("/api/qnas/get-zones/", { method: "GET", credentials: "include" })
    """
    if request.method != 'GET':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    logger.info("QNAS proxy: Fetching zones")

    resp = _make_qnas_request(request, "get_zones")

    if resp is None:
        return JsonResponse({'error': 'QNAS API request failed'}, status=502)

    from django.http import HttpResponse
    return HttpResponse(
        resp.content,
        status=resp.status_code,
        content_type=resp.headers.get("Content-Type", "application/json")
    )


@csrf_exempt
def qnas_get_streets(request):
    """
    Proxy endpoint for QNAS get_streets API.

    Query params:
    - zone: Zone number to get streets for

    Frontend must call with credentials:
    fetch("/api/qnas/get-streets/?zone=1", { method: "GET", credentials: "include" })
    """
    if request.method != 'GET':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    zone = request.GET.get('zone', '')
    if not zone:
        return JsonResponse({'error': 'Zone parameter is required'}, status=400)

    logger.info(f"QNAS proxy: Fetching streets for zone {zone}")

    resp = _make_qnas_request(request, f"get_streets?zone={zone}")

    if resp is None:
        return JsonResponse({'error': 'QNAS API request failed'}, status=502)

    from django.http import HttpResponse
    return HttpResponse(
        resp.content,
        status=resp.status_code,
        content_type=resp.headers.get("Content-Type", "application/json")
    )


@csrf_exempt
def qnas_get_buildings(request):
    """
    Proxy endpoint for QNAS get_buildings API.

    Query params:
    - zone: Zone number
    - street: Street number

    Frontend must call with credentials:
    fetch("/api/qnas/get-buildings/?zone=1&street=123", { method: "GET", credentials: "include" })
    """
    if request.method != 'GET':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    zone = request.GET.get('zone', '')
    street = request.GET.get('street', '')

    if not zone or not street:
        return JsonResponse({'error': 'Zone and street parameters are required'}, status=400)

    logger.info(f"QNAS proxy: Fetching buildings for zone {zone}, street {street}")

    resp = _make_qnas_request(request, f"get_buildings?zone={zone}&street={street}")

    if resp is None:
        return JsonResponse({'error': 'QNAS API request failed'}, status=502)

    from django.http import HttpResponse
    return HttpResponse(
        resp.content,
        status=resp.status_code,
        content_type=resp.headers.get("Content-Type", "application/json")
    )


@csrf_exempt
def qnas_search_address(request):
    """
    Proxy endpoint for QNAS address search API.

    Query params:
    - q: Search query (address text)

    Frontend must call with credentials:
    fetch("/api/qnas/search/?q=Al Sadd", { method: "GET", credentials: "include" })
    """
    if request.method != 'GET':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    query = request.GET.get('q', '')
    if not query:
        return JsonResponse({'error': 'Search query (q) is required'}, status=400)

    logger.info(f"QNAS proxy: Searching address: {query}")

    # URL encode the query
    import urllib.parse
    encoded_query = urllib.parse.quote(query)

    resp = _make_qnas_request(request, f"search?q={encoded_query}")

    if resp is None:
        return JsonResponse({'error': 'QNAS API request failed'}, status=502)

    from django.http import HttpResponse
    return HttpResponse(
        resp.content,
        status=resp.status_code,
        content_type=resp.headers.get("Content-Type", "application/json")
    )


@csrf_exempt
def qnas_get_address_details(request):
    """
    Proxy endpoint for QNAS address details API.

    Query params:
    - zone: Zone number
    - street: Street number
    - building: Building number

    Frontend must call with credentials:
    fetch("/api/qnas/address-details/?zone=1&street=123&building=45", {
        method: "GET",
        credentials: "include"
    })
    """
    if request.method != 'GET':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    zone = request.GET.get('zone', '')
    street = request.GET.get('street', '')
    building = request.GET.get('building', '')

    if not all([zone, street, building]):
        return JsonResponse({'error': 'Zone, street, and building parameters are required'}, status=400)

    logger.info(f"QNAS proxy: Getting address details for zone={zone}, street={street}, building={building}")

    resp = _make_qnas_request(request, f"get_address_details?zone={zone}&street={street}&building={building}")

    if resp is None:
        return JsonResponse({'error': 'QNAS API request failed'}, status=502)

    from django.http import HttpResponse
    return HttpResponse(
        resp.content,
        status=resp.status_code,
        content_type=resp.headers.get("Content-Type", "application/json")
    )


@csrf_exempt
def qnas_geocode(request):
    """
    Proxy endpoint for QNAS geocoding API.

    Query params:
    - lat: Latitude
    - lng: Longitude

    Frontend must call with credentials:
    fetch("/api/qnas/geocode/?lat=25.2854&lng=51.5310", {
        method: "GET",
        credentials: "include"
    })
    """
    if request.method != 'GET':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    lat = request.GET.get('lat', '')
    lng = request.GET.get('lng', '')

    if not lat or not lng:
        return JsonResponse({'error': 'lat and lng parameters are required'}, status=400)

    logger.info(f"QNAS proxy: Geocoding lat={lat}, lng={lng}")

    resp = _make_qnas_request(request, f"geocode?lat={lat}&lng={lng}")

    if resp is None:
        return JsonResponse({'error': 'QNAS API request failed'}, status=502)

    from django.http import HttpResponse
    return HttpResponse(
        resp.content,
        status=resp.status_code,
        content_type=resp.headers.get("Content-Type", "application/json")
    )


@csrf_exempt
def qnas_get_zone_polygon(request, zone_number):
    """
    Proxy endpoint for QNAS get_zone_polygon API.
    Returns zone polygon boundaries.

    URL params:
    - zone_number: Zone number to get polygon for

    Frontend must call with credentials:
    fetch("/api/qnas/get-zone-polygon/1/", { method: "GET", credentials: "include" })
    """
    if request.method != 'GET':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    if not zone_number:
        return JsonResponse({'error': 'Zone number is required'}, status=400)

    logger.info(f"QNAS proxy: Fetching polygon for zone {zone_number}")

    resp = _make_qnas_request(request, f"get_zone_polygon?zone={zone_number}")

    if resp is None:
        return JsonResponse({'error': 'QNAS API request failed'}, status=502)

    from django.http import HttpResponse
    return HttpResponse(
        resp.content,
        status=resp.status_code,
        content_type=resp.headers.get("Content-Type", "application/json")
    )


@csrf_exempt
def qnas_get_coordinates(request):
    """
    POST endpoint to get latitude/longitude from QNAS by zone, street, and building.

    Request body (JSON):
    {
        "zone": "51",
        "street": "203",
        "building": "26"  // optional
    }

    Response:
    {
        "success": true,
        "latitude": 25.123456,
        "longitude": 51.567890,
        "building_number": "26",
        "match_type": "exact" | "street_level",
        "total_buildings": 5
    }

    Frontend usage:
    fetch("/api/qnas/coordinates/", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ zone: "51", street: "203", building: "26" })
    })
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed. Use POST.'}, status=405)

    try:
        import json
        data = json.loads(request.body)
        zone = data.get('zone', '')
        street = data.get('street', '')
        building = data.get('building', '')

        if not zone or not street:
            return JsonResponse({
                'success': False,
                'error': 'Zone and street are required'
            }, status=400)

        logger.info(f"QNAS coordinates POST: zone={zone}, street={street}, building={building}")

        # Fetch buildings from QNAS
        resp = _make_qnas_request(request, f"get_buildings?zone={zone}&street={street}")

        if resp is None:
            return JsonResponse({
                'success': False,
                'error': 'QNAS API request failed'
            }, status=502)

        if resp.status_code != 200:
            return JsonResponse({
                'success': False,
                'error': f'QNAS API returned status {resp.status_code}'
            }, status=502)

        buildings = resp.json()

        if not buildings or len(buildings) == 0:
            return JsonResponse({
                'success': False,
                'error': 'No buildings found for this zone and street'
            }, status=404)

        # Find matching building or use first one
        selected_building = buildings[0]
        match_type = 'street_level'

        if building:
            for b in buildings:
                if str(b.get('building_number', '')) == str(building):
                    selected_building = b
                    match_type = 'exact'
                    break

        latitude = float(selected_building.get('x', 0))
        longitude = float(selected_building.get('y', 0))

        if latitude == 0 or longitude == 0:
            return JsonResponse({
                'success': False,
                'error': 'Coordinates not available for this location'
            }, status=404)

        return JsonResponse({
            'success': True,
            'latitude': latitude,
            'longitude': longitude,
            'building_number': selected_building.get('building_number', ''),
            'match_type': match_type,
            'total_buildings': len(buildings)
        })

    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'error': 'Invalid JSON in request body'
        }, status=400)
    except Exception as e:
        logger.error(f"QNAS coordinates error: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)



@csrf_exempt
def qnas_get_location(request, zone_number, street_number, building_number=None):
    """
    GET endpoint to get coordinates by zone/street/building using path parameters.
    Matches QNAS API format: /get_location/{zone}/{street}/{building}

    URL Parameters:
    - zone_number: Zone number (required)
    - street_number: Street number (required)
    - building_number: Building number (optional)

    Response:
    {
        "success": true,
        "latitude": 25.123456,
        "longitude": 51.567890,
        "building_number": "26",
        "match_type": "exact" | "street_level",
        "total_buildings": 5
    }

    Frontend usage:
    fetch("/api/qnas/location/54/534/23/", {
        method: "GET",
        credentials: "include"
    })
    """
    if request.method != 'GET':
        return JsonResponse({'error': 'Method not allowed. Use GET.'}, status=405)

    try:
        zone = str(zone_number)
        street = str(street_number)
        building = str(building_number) if building_number else ''

        if not zone or not street:
            return JsonResponse({
                'success': False,
                'error': 'Zone and street are required'
            }, status=400)

        logger.info(f"QNAS location GET: zone={zone}, street={street}, building={building}")

        # Fetch buildings from QNAS
        resp = _make_qnas_request(request, f"get_buildings?zone={zone}&street={street}")

        if resp is None:
            return JsonResponse({
                'success': False,
                'error': 'QNAS API request failed'
            }, status=502)

        if resp.status_code != 200:
            return JsonResponse({
                'success': False,
                'error': f'QNAS API returned status {resp.status_code}'
            }, status=502)

        try:
            buildings = resp.json()
        except ValueError as e:
            logger.error(f"QNAS location: Invalid JSON response: {resp.text[:200]}")
            return JsonResponse({
                'success': False,
                'error': 'Invalid response from QNAS API'
            }, status=502)

        if not buildings or len(buildings) == 0:
            logger.warning(f"QNAS location: No buildings found for zone={zone}, street={street}")
            return JsonResponse({
                'success': False,
                'error': 'No buildings found for this zone and street'
            }, status=404)

        # Find matching building or use first one
        selected_building = buildings[0]
        match_type = 'street_level'

        if building:
            for b in buildings:
                if str(b.get('building_number', '')) == str(building):
                    selected_building = b
                    match_type = 'exact'
                    break

        latitude = float(selected_building.get('x', 0))
        longitude = float(selected_building.get('y', 0))

        if latitude == 0 or longitude == 0:
            return JsonResponse({
                'success': False,
                'error': 'Coordinates not available for this location'
            }, status=404)

        return JsonResponse({
            'success': True,
            'latitude': latitude,
            'longitude': longitude,
            'building_number': selected_building.get('building_number', ''),
            'match_type': match_type,
            'total_buildings': len(buildings)
        })

    except Exception as e:
        logger.error(f"QNAS location error: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)
