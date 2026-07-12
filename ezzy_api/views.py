import logging
from django.http import JsonResponse
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
import requests
from rest_framework import permissions, status, viewsets
from rest_framework import generics
from rest_framework.decorators import api_view, permission_classes, action, throttle_classes
from ezzy_api.throttles import LoginRateThrottle
from ezzy_api.permissions import require_admin_scope
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
from delivery.state_machine import can_transition as task_can_transition
from core import models as core_models
from business import models as business_models
from ezzy_api import models as ezzy_api_models
from ezzy_api import serializers as ezzy_api_serializers
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
        # Use filter().first() rather than get() so a user owning more than one
        # business does not raise MultipleObjectsReturned (500).
        return (
            business_models.Business.objects
            .filter(user_id=request.user.id)
            .order_by('id')
            .first()
        )
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

    def perform_create(self, serializer):
        """Force the order onto the caller's own business — never trust a
        `business` value from the request body (prevents creating orders under
        another tenant)."""
        from rest_framework.exceptions import PermissionDenied
        business = get_api_user_business(self.request)
        if not business:
            raise PermissionDenied('No business is associated with this account')
        serializer.save(business=business)








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
@throttle_classes([LoginRateThrottle])
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
        # Only show tasks published to fleet
        tasks = delivery_models.DeliveryTask.objects.filter(
            driver=driver,
            dl_task_publish=True,
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
            task = delivery_models.DeliveryTask.objects.select_related('order').select_for_update().get(id=task_id)

            # Lock check: Task must be published to fleet
            if not task.dl_task_publish:
                return Response({
                    'error': 'Task is not published to fleet yet.'
                }, status=status.HTTP_403_FORBIDDEN)

            if task.driver and task.driver != driver:
                return Response(
                    {'error': 'Task already assigned to another driver'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            task.driver = driver
            task.dl_task_status = 'accepted'
            task._status_actor = 'driver'
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
            'timestamp': timezone.now().isoformat(),
            'driver_id': driver.driver_id
        }
        _send_webhook_event('task_accepted', webhook_payload, business=task.business)

        # Fire auto flows
        try:
            from core.auto_flow_executor import execute_flows_for_trigger
            execute_flows_for_trigger('wh_task_accepted', task=task)
        except Exception:
            pass

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

        # Lock check: Task must be published to fleet
        if not task.dl_task_publish:
            return Response({
                'error': 'Task is not published to fleet yet.'
            }, status=status.HTTP_403_FORBIDDEN)

        # Lock check: Prevent status change if task is Successful AND COD is settled
        if task.dl_task_status == 'delivered' and task.order and task.order.cod_status_by_staff == 'cod_settled_with_business':
            return Response({
                'error': 'Task is locked. Status cannot be changed after delivery is successful and COD is settled.'
            }, status=status.HTTP_403_FORBIDDEN)

        task.dl_task_status = 'rejected'
        task._status_actor = 'driver'
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
            'timestamp': timezone.now().isoformat(),
            'driver_id': driver.driver_id
        }
        _send_webhook_event('task_rejected', webhook_payload, business=task.business)

        # Fire auto flows
        try:
            from core.auto_flow_executor import execute_flows_for_trigger
            execute_flows_for_trigger('wh_task_rejected', task=task)
        except Exception:
            pass

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

        # Lock check: Task must be published to fleet
        if not task.dl_task_publish:
            return Response({
                'error': 'Task is not published to fleet yet.'
            }, status=status.HTTP_403_FORBIDDEN)

        # Lock check: Prevent status change if order is cancelled
        if task.order and task.order.order_status == 'cancelled':
            return Response({
                'error': 'Task is locked. Order is cancelled — no delivery status changes allowed.'
            }, status=status.HTTP_403_FORBIDDEN)

        # Lock check: Prevent status change if task is Successful AND COD is settled
        if task.dl_task_status == 'delivered' and task.order and task.order.cod_status_by_staff == 'cod_settled_with_business':
            return Response({
                'error': 'Task is locked. Status cannot be changed after delivery is successful and COD is settled.'
            }, status=status.HTTP_403_FORBIDDEN)

        new_status = request.data.get('status')

        if new_status:
            if new_status not in VALID_DRIVER_STATUSES:
                return Response({
                    'error': f'Invalid status: {new_status}. Valid statuses: {", ".join(VALID_DRIVER_STATUSES)}'
                }, status=status.HTTP_400_BAD_REQUEST)

            # State machine validation
            allowed, reason = task_can_transition(task.dl_task_status, new_status, actor='driver')
            if not allowed:
                return Response({'error': reason}, status=status.HTTP_400_BAD_REQUEST)

            task.dl_task_status = new_status
            task._status_actor = 'driver'
            task._status_changed_by = request.user

        task.save()
        
        # Trigger webhooks
        webhook_payload = {
            'task_id': task_id,
            'task_number': task.dl_task_number,
            'status': new_status,
            'timestamp': timezone.now().isoformat(),
            'driver_id': driver.driver_id
        }
        _send_webhook_event('task_status_update', webhook_payload, business=task.business)

        # Fire auto flows
        try:
            from core.auto_flow_executor import execute_flows_for_trigger
            execute_flows_for_trigger('wh_task_status_update', task=task)
        except Exception:
            pass

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
    """Save a GPS ping from the driver PWA."""
    try:
        driver = fleet_models.Driver.objects.get(user=request.user)

        latitude = request.data.get('latitude')
        longitude = request.data.get('longitude')

        if latitude is None or longitude is None:
            return Response(
                {'error': 'Latitude and longitude are required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        loc = fleet_models.DriverLocation.objects.create(
            driver=driver,
            latitude=latitude,
            longitude=longitude,
            accuracy=request.data.get('accuracy'),
            speed=request.data.get('speed'),
            heading=request.data.get('heading'),
            task_id=request.data.get('task_id'),
        )

        return Response({
            'message': 'Location updated successfully',
            'id': loc.pk,
            'latitude': str(loc.latitude),
            'longitude': str(loc.longitude),
            'timestamp': loc.created_at.isoformat(),
        }, status=status.HTTP_200_OK)

    except fleet_models.Driver.DoesNotExist:
        return Response(
            {'error': 'Driver profile not found'},
            status=status.HTTP_404_NOT_FOUND
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def driver_latest_location(request, driver_id):
    """Get the latest GPS location for a driver (admin/workforce use)."""
    if not request.user.is_staff:
        # Allow drivers to get only their own location
        try:
            own_driver = fleet_models.Driver.objects.get(user=request.user)
            if own_driver.driver_id != driver_id:
                return Response({'error': 'Not authorized'}, status=status.HTTP_403_FORBIDDEN)
        except fleet_models.Driver.DoesNotExist:
            return Response({'error': 'Not authorized'}, status=status.HTTP_403_FORBIDDEN)

    loc = fleet_models.DriverLocation.objects.filter(
        driver_id=driver_id
    ).order_by('-created_at').first()

    if not loc:
        return Response(
            {'error': 'No location data for this driver'},
            status=status.HTTP_404_NOT_FOUND
        )

    return Response({
        'driver_id': driver_id,
        'latitude': str(loc.latitude),
        'longitude': str(loc.longitude),
        'accuracy': loc.accuracy,
        'speed': loc.speed,
        'heading': loc.heading,
        'task_id': loc.task_id,
        'timestamp': loc.created_at.isoformat(),
    }, status=status.HTTP_200_OK)


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
# ==================== HUB PICKUP BATCH APIs ====================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def driver_hub_batches(request):
    """List active hub pickup batches assigned to the requesting driver."""
    try:
        driver = fleet_models.Driver.objects.get(user=request.user)
    except fleet_models.Driver.DoesNotExist:
        return Response({'error': 'Driver profile not found'}, status=status.HTTP_404_NOT_FOUND)

    batches = delivery_models.HubPickupBatch.objects.filter(
        driver=driver,
    ).exclude(
        status__in=['at_hub', 'cancelled'],
    ).select_related(
        'pickup_location',
        'hub_warehouse',
        'hub_warehouse__warehouse',
    ).prefetch_related('orders').order_by('-created_at')

    data = []
    for batch in batches:
        pickup_loc = batch.pickup_location
        hub_wh = batch.hub_warehouse
        data.append({
            'id': batch.id,
            'batch_number': batch.batch_number,
            'status': batch.status,
            'order_count': batch.order_count,
            'driver_earnings': str(batch.driver_earnings),
            'pickup_location_title': pickup_loc.pickup_location_title if pickup_loc else None,
            'pickup_lat': str(pickup_loc.pickup_lat) if pickup_loc and pickup_loc.pickup_lat else None,
            'pickup_lon': str(pickup_loc.pickup_lon) if pickup_loc and pickup_loc.pickup_lon else None,
            'hub_warehouse_name': f"{hub_wh.warehouse.name} / {hub_wh.name}" if hub_wh else None,
            'hub_warehouse_address': hub_wh.address if hub_wh else None,
            'hub_lat': str(hub_wh.latitude) if hub_wh and hub_wh.latitude else None,
            'hub_lng': str(hub_wh.longitude) if hub_wh and hub_wh.longitude else None,
            'orders': [{'order_number': o.order_number, 'customer_name': o.customer_name} for o in batch.orders.all()],
        })
    return Response(data, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def driver_hub_batch_detail(request, batch_id):
    """Get detail for a single hub pickup batch."""
    try:
        driver = fleet_models.Driver.objects.get(user=request.user)
    except fleet_models.Driver.DoesNotExist:
        return Response({'error': 'Driver profile not found'}, status=status.HTTP_404_NOT_FOUND)

    try:
        batch = delivery_models.HubPickupBatch.objects.select_related(
            'pickup_location', 'hub_warehouse', 'hub_warehouse__warehouse'
        ).prefetch_related('orders').get(id=batch_id, driver=driver)
    except delivery_models.HubPickupBatch.DoesNotExist:
        return Response({'error': 'Batch not found'}, status=status.HTTP_404_NOT_FOUND)

    pickup_loc = batch.pickup_location
    hub_wh = batch.hub_warehouse
    return Response({
        'id': batch.id,
        'batch_number': batch.batch_number,
        'status': batch.status,
        'order_count': batch.order_count,
        'driver_earnings': str(batch.driver_earnings),
        'notes': batch.notes,
        'pickup_location_title': pickup_loc.pickup_location_title if pickup_loc else None,
        'pickup_lat': str(pickup_loc.pickup_lat) if pickup_loc and pickup_loc.pickup_lat else None,
        'pickup_lon': str(pickup_loc.pickup_lon) if pickup_loc and pickup_loc.pickup_lon else None,
        'hub_warehouse_name': f"{hub_wh.warehouse.name} / {hub_wh.name}" if hub_wh else None,
        'hub_warehouse_address': hub_wh.address if hub_wh else None,
        'hub_lat': str(hub_wh.latitude) if hub_wh and hub_wh.latitude else None,
        'hub_lng': str(hub_wh.longitude) if hub_wh and hub_wh.longitude else None,
        'orders': [
            {
                'order_number': o.order_number,
                'customer_name': o.customer_name,
                'customer_address': o.customer_address,
                'cod_amount': o.cod_amount,
            }
            for o in batch.orders.all()
        ],
    }, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def driver_hub_batch_accept(request, batch_id):
    """Driver accepts a hub pickup batch."""
    try:
        driver = fleet_models.Driver.objects.get(user=request.user)
    except fleet_models.Driver.DoesNotExist:
        return Response({'error': 'Driver profile not found'}, status=status.HTTP_404_NOT_FOUND)

    try:
        batch = delivery_models.HubPickupBatch.objects.get(id=batch_id, driver=driver)
    except delivery_models.HubPickupBatch.DoesNotExist:
        return Response({'error': 'Batch not found'}, status=status.HTTP_404_NOT_FOUND)

    if batch.status != 'assigned':
        return Response({'error': f'Cannot accept batch in status: {batch.status}'}, status=status.HTTP_400_BAD_REQUEST)

    batch._old_batch_status = batch.status
    batch.status = 'accepted'
    batch.save(update_fields=['status'])
    return Response({'success': True, 'status': 'accepted'}, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def driver_hub_batch_status(request, batch_id):
    """Driver updates hub pickup batch status."""
    DRIVER_ALLOWED_TRANSITIONS = {
        'accepted':    'in_progress',
        'in_progress': 'arrived',
        'arrived':     'collected',
        'collected':   'at_hub',
    }

    try:
        driver = fleet_models.Driver.objects.get(user=request.user)
    except fleet_models.Driver.DoesNotExist:
        return Response({'error': 'Driver profile not found'}, status=status.HTTP_404_NOT_FOUND)

    try:
        batch = delivery_models.HubPickupBatch.objects.get(id=batch_id, driver=driver)
    except delivery_models.HubPickupBatch.DoesNotExist:
        return Response({'error': 'Batch not found'}, status=status.HTTP_404_NOT_FOUND)

    new_status = request.data.get('status')
    if not new_status:
        return Response({'error': 'status field required'}, status=status.HTTP_400_BAD_REQUEST)

    allowed_next = DRIVER_ALLOWED_TRANSITIONS.get(batch.status)
    if new_status != allowed_next:
        return Response(
            {'error': f"Invalid transition '{batch.status}' → '{new_status}'. Allowed next: {allowed_next or 'none (terminal)'}"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    batch._old_batch_status = batch.status
    batch.status = new_status
    batch.save(update_fields=['status'])
    return Response({'success': True, 'status': new_status}, status=status.HTTP_200_OK)


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

        # Lock check: Task must be published to fleet
        if not task.dl_task_publish:
            return Response({
                'error': 'Task is not published to fleet yet.'
            }, status=status.HTTP_403_FORBIDDEN)

        # Lock check: Prevent status change if order is cancelled
        if task.order and task.order.order_status == 'cancelled':
            return Response({
                'error': 'Task is locked. Order is cancelled — no delivery status changes allowed.'
            }, status=status.HTTP_403_FORBIDDEN)

        # Lock check: Prevent status change if task is Successful AND COD is settled
        if task.dl_task_status == 'delivered' and task.order and task.order.cod_status_by_staff == 'cod_settled_with_business':
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

        # Block delivery without COD confirmation when order has COD
        if status_value == 'delivered' and task.order and task.order.cod_amount and task.order.cod_amount > 0:
            if not cod_collected and not task.cod_collected:
                return Response({
                    'error': f'This order has COD of {task.order.cod_amount} QAR. '
                             f'Please confirm COD collection before marking as delivered.'
                }, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            # Re-fetch with row lock inside atomic block
            task = delivery_models.DeliveryTask.objects.select_for_update().select_related('order').get(id=task_id)

            # Capture original COD state for idempotency
            was_already_cod_collected = task.cod_collected

            # Update task status with DMS mapping
            task.dl_task_status = status_value
            task._status_actor = 'driver'
            task._status_changed_by = request.user
            # Attach notes so delivery/signals.py can pass them to OrderStatusHistory
            if notes:
                task._status_notes = notes

            if status_value in ('delivered', 'failed', 'cancelled'):
                task.completed_at = timezone.now()

            # Persist failure reason & driver notes on the task when marking failed
            if status_value == 'failed':
                valid_reason_keys = {k for k, _ in delivery_models.DeliveryTask.FAILURE_REASON_CHOICES}
                failure_reason = serializer.validated_data.get('failure_reason', '') or ''
                failure_notes = serializer.validated_data.get('failure_notes', '') or ''
                if failure_reason and failure_reason in valid_reason_keys:
                    task.failure_reason = failure_reason
                elif failure_reason:
                    task.failure_reason = 'other'
                if failure_notes:
                    task.failure_notes = failure_notes
                elif notes and not task.failure_notes:
                    task.failure_notes = notes

            # Save proof-of-delivery GPS coordinates
            comp_lat = serializer.validated_data.get('completion_latitude')
            comp_lng = serializer.validated_data.get('completion_longitude')
            if comp_lat is not None and comp_lng is not None:
                task.completion_latitude = comp_lat
                task.completion_longitude = comp_lng

            # Track COD on task-level fields
            if cod_collected:
                task.cod_collected = True
                task.cod_collected_at = timezone.now()
            if cod_amount_collected:
                task.cod_collected_amount = cod_amount_collected

            # Save payment method and split payment from driver
            payment_method = request.data.get('payment_method', '') if hasattr(request.data, 'get') else request.POST.get('payment_method', '')

            # Parse split payment (cash, pos, fawran per-method amounts)
            split = {}
            for m in ('cash', 'pos', 'fawran'):
                val = request.data.get(f'payment_split_{m}') if hasattr(request.data, 'get') else request.POST.get(f'payment_split_{m}')
                if val:
                    try:
                        amount = float(val)
                        if amount > 0:
                            split[m] = round(amount, 2)
                    except (ValueError, TypeError):
                        pass

            if split:
                task.payment_split = split
                task.payment_method = max(split, key=split.get)
            elif payment_method in ('cash', 'pos', 'fawran'):
                task.payment_method = payment_method

            task.save()

            # COD collection tracking (only on successful delivery, idempotent)
            # Note: order status sync is handled by delivery/signals.py post_save
            if task.order and status_value == 'delivered' and cod_collected and cod_amount_collected and not was_already_cod_collected:
                from decimal import Decimal
                expected = Decimal(str(task.order.cod_amount)) if task.order.cod_amount else Decimal('0')
                collected = Decimal(str(cod_amount_collected))

                # Fix 19: Cap COD inflation — prevent driver from reporting more than 110% of expected
                if expected > 0 and collected > expected * Decimal('1.1'):
                    logger.warning(
                        f"COD INFLATION: Driver sent {collected}, expected {expected} "
                        f"for order {task.order.order_number}"
                    )
                    collected = expected  # Cap at expected amount
                    task.cod_collected_amount = collected
                    task.save(update_fields=['cod_collected_amount'])

                # Set correct COD status: partial or full
                if expected > 0 and collected < expected:
                    task.order.cod_status_by_staff = 'partially_collected'
                else:
                    task.order.cod_status_by_staff = 'cod_with_driver'
                task.order.save(update_fields=['cod_status_by_staff'])

                # Record COD collection in driver wallet (actual amount collected)
                from fleet.wallet_service import WalletService
                has_mismatch = expected > 0 and collected != expected
                if has_mismatch:
                    mismatch_label = 'partial' if collected < expected else 'over'
                    cod_desc = (
                        f"COD collected for order {task.order.order_number} "
                        f"[{mismatch_label}: collected {collected}, expected {expected}]"
                    )
                    cod_notes = f"COD amount mismatch — expected {expected} QAR, driver collected {collected} QAR"
                else:
                    cod_desc = f"COD collected for order {task.order.order_number}"
                    cod_notes = None
                WalletService.record_transaction(
                    driver=task.driver,
                    transaction_type='cod_collection',
                    amount=collected,
                    description=cod_desc,
                    notes=cod_notes,
                    delivery_task=task,
                    created_by=request.user,
                    payment_method=task.payment_method or None,
                )

            # Fix 14: Allow additional COD collection on partially collected orders
            elif (task.order and status_value == 'delivered' and cod_collected and cod_amount_collected
                  and was_already_cod_collected
                  and task.order.cod_status_by_staff == 'partially_collected'):
                from decimal import Decimal
                additional = Decimal(str(cod_amount_collected))
                expected = Decimal(str(task.order.cod_amount)) if task.order.cod_amount else Decimal('0')
                new_total = task.cod_collected_amount + additional

                # Update task with new total
                task.cod_collected_amount = new_total
                task.save(update_fields=['cod_collected_amount'])

                # Update order status
                if new_total >= expected:
                    task.order.cod_status_by_staff = 'cod_with_driver'
                task.order.save(update_fields=['cod_status_by_staff'])

                # Record additional wallet transaction
                from fleet.wallet_service import WalletService
                WalletService.record_transaction(
                    driver=task.driver,
                    transaction_type='cod_collection',
                    amount=additional,
                    description=f"Additional COD for order {task.order.order_number} (remaining: {additional} of {expected})",
                    delivery_task=task,
                    created_by=request.user,
                )

            # Log COD amount mismatch warning
            if task.order and cod_amount_collected and task.order.cod_amount:
                from decimal import Decimal
                expected = Decimal(str(task.order.cod_amount))
                collected = Decimal(str(cod_amount_collected))
                if expected > 0 and abs(collected - expected) / expected > Decimal('0.1'):
                    logger.warning(
                        f"COD mismatch for order {task.order.order_number}: "
                        f"expected {expected}, collected {collected} "
                        f"(driver {driver.driver_id})"
                    )
                    # Fix 6: Create driver notification for COD mismatch
                    try:
                        fleet_models.DriverNotification.objects.create(
                            driver=task.driver,
                            title=f'COD Mismatch: {task.order.order_number}',
                            message=f'Expected {expected} QAR, collected {collected} QAR ({abs(collected - expected)} QAR difference)',
                            notification_type='alert',
                            related_task=task,
                        )
                    except Exception:
                        pass

            # Fix 11: Payment method audit log
            if payment_method and task.driver and task.order:
                try:
                    fleet_models.DriverActivityLog.objects.create(
                        driver=task.driver,
                        activity_type='cod_collected',
                        task=task,
                        description=f'COD {cod_amount_collected or 0} QAR via {payment_method} for {task.order.order_number}',
                        meta={'payment_method': payment_method, 'amount': str(cod_amount_collected or 0), 'expected': str(task.order.cod_amount or 0)},
                    )
                except Exception:
                    pass

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

        # Push status back to WooCommerce if the order originated there
        if task.order and status_value in ('delivered', 'failed', 'cancelled'):
            try:
                _push_woo_order_status(task.order, status_value)
            except Exception:
                pass

        # Fire auto flows
        try:
            from core.auto_flow_executor import execute_flows_for_trigger
            execute_flows_for_trigger('wh_task_completed', task=task)
        except Exception:
            pass

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

        # Lock check: Task must be published to fleet
        if not task.dl_task_publish:
            return Response({
                'error': 'Task is not published to fleet yet.'
            }, status=status.HTTP_403_FORBIDDEN)

        # Lock check: Prevent uploads on completed+settled tasks
        if task.dl_task_status == 'delivered' and task.order and task.order.cod_status_by_staff == 'cod_settled_with_business':
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
# ==================== API KEY MANAGEMENT APIs ====================

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_api_key(request):
    """Create a new API key for a client"""
    # Managing keys requires the admin scope when called via an API key.
    scope_err = require_admin_scope(request)
    if scope_err:
        return Response({'error': scope_err}, status=status.HTTP_403_FORBIDDEN)
    try:
        serializer = ezzy_api_serializers.ClientApiKeyCreateSerializer(data=request.data)

        if not serializer.is_valid():
            logger.error(f"Serializer validation failed: {serializer.errors}")
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        business_id = serializer.validated_data['business_id']
        key_name = serializer.validated_data.get('key_name', '')
        key_scope = serializer.validated_data.get('scope', ezzy_api_models.ClientApiKey.SCOPE_WRITE)
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
                scope=key_scope,
                expires_at=expires_at,
                created_by=request.user
            )

            logger.info(f"API key created successfully for business {business_id} by user {request.user.id}")
            # Reveal the full key + secret ONCE, only in the creation response.
            serializer = ezzy_api_serializers.ClientApiKeyRevealSerializer(api_key)
            return Response({
                'message': 'API key created successfully. Store the secret now — it will not be shown again.',
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
    scope_err = require_admin_scope(request)
    if scope_err:
        return Response({'error': scope_err}, status=status.HTTP_403_FORBIDDEN)
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
    scope_err = require_admin_scope(request)
    if scope_err:
        return Response({'error': scope_err}, status=status.HTTP_403_FORBIDDEN)
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
        # Verify user owns this business
        if not request.user.is_staff and business.user != request.user:
            return Response({'error': 'Not authorized for this business'}, status=status.HTTP_403_FORBIDDEN)
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
        # Verify user owns this business
        if not request.user.is_staff and business.user != request.user:
            return Response({'error': 'Not authorized for this business'}, status=status.HTTP_403_FORBIDDEN)
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
            if not request.user.is_staff and business.user != request.user:
                return Response({'error': 'Not authorized'}, status=status.HTTP_403_FORBIDDEN)
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
        # Verify user owns this business
        if not request.user.is_staff and business.user != request.user:
            return Response({'error': 'Not authorized for this business'}, status=status.HTTP_403_FORBIDDEN)
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
        # Verify user owns this business
        if not request.user.is_staff and business.user != request.user:
            return Response({'error': 'Not authorized for this business'}, status=status.HTTP_403_FORBIDDEN)
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

_SAME_DAY_KEYWORDS = ('same day', 'same-day', 'sameday', 'express', 'urgent', 'immediate', 'on demand', '1hr', '1 hr', '2hr', '2 hr')

def _detect_delivery_speed(shipping_title):
    """Return 'same_day' if the shipping method title signals urgency, else 'standard'."""
    if not shipping_title:
        return 'standard'
    title_lower = shipping_title.lower()
    return 'same_day' if any(kw in title_lower for kw in _SAME_DAY_KEYWORDS) else 'standard'


def _shopify_cod_status(shopify_order):
    """Determine COD status from Shopify financial_status."""
    fs = getattr(shopify_order, 'financial_status', '') or ''
    if fs == 'pending':
        return 'unpaid'
    elif fs == 'partially_paid':
        return 'partial_paid'
    else:
        return 'online_paid'


def _shopify_cod_amount(shopify_order):
    """Return COD amount in cents. Paid=0, Unpaid=full, Partial=balance."""
    fs = getattr(shopify_order, 'financial_status', '') or ''
    total = int(float(shopify_order.total_price) * 100)
    if fs == 'pending':
        return total
    elif fs == 'partially_paid':
        total_outstanding = float(getattr(shopify_order, 'total_outstanding', shopify_order.total_price))
        return int(total_outstanding * 100)
    else:
        return 0


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

        # Detect delivery speed from shipping method title
        shipping_lines = getattr(shopify_order, 'shipping_lines', []) or []
        shipping_title = shipping_lines[0].title if shipping_lines else ''
        delivery_speed = _detect_delivery_speed(shipping_title)

        # Create order
        order = orders_models.Order.objects.create(
            order_number=order_number,
            business=business,
            client_order_code=str(shopify_order.order_number),
            customer_name=shipping_address.name if shipping_address else (customer.first_name + ' ' + customer.last_name if customer else ''),
            customer_phone=shipping_address.phone if shipping_address else '',
            customer_address=f"{shipping_address.address1 or ''} {shipping_address.city or ''} {shipping_address.province or ''}".strip() if shipping_address else '',
            cod_amount=_shopify_cod_amount(shopify_order),
            cod_status_by_client=_shopify_cod_status(shopify_order),
            delivery_speed=delivery_speed,
            order_status='to_review',
            order_date=datetime.strptime(shopify_order.created_at[:10], '%Y-%m-%d').date() if shopify_order.created_at else timezone.now().date()
        )
        
        return order
    except Exception as e:
        raise Exception(f"Error creating order: {str(e)}")
def _woo_cod_status(order_data):
    """Determine COD status from WooCommerce order data."""
    if order_data.get('payment_method') == 'cod':
        if order_data.get('date_paid'):
            return 'online_paid'
        return 'unpaid'
    elif order_data.get('status') == 'partially-paid':
        return 'partial_paid'
    else:
        return 'online_paid'


def _woo_cod_amount(order_data):
    """Return COD amount in cents. Paid=0, Unpaid=full, Partial=balance."""
    total = int(float(order_data.get('total', 0)) * 100)
    if order_data.get('payment_method') == 'cod':
        if order_data.get('date_paid'):
            return 0
        return total
    elif order_data.get('status') == 'partially-paid':
        balance = float(order_data.get('total_outstanding', order_data.get('total', 0)))
        return int(balance * 100)
    else:
        return 0


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

        # Detect delivery speed from WooCommerce shipping method title
        woo_shipping_lines = order_data.get('shipping_lines', []) or []
        woo_shipping_title = woo_shipping_lines[0].get('method_title', '') if woo_shipping_lines else ''
        delivery_speed = _detect_delivery_speed(woo_shipping_title)

        # Create order
        order = orders_models.Order.objects.create(
            order_number=order_number,
            business=business,
            client_order_code=str(order_data.get('number', order_data.get('id'))),
            customer_name=f"{billing.get('first_name', '')} {billing.get('last_name', '')}".strip(),
            customer_phone=billing.get('phone', ''),
            customer_address=f"{shipping.get('address_1', '')} {shipping.get('city', '')} {shipping.get('state', '')}".strip(),
            cod_amount=_woo_cod_amount(order_data),
            cod_status_by_client=_woo_cod_status(order_data),
            delivery_speed=delivery_speed,
            order_status='to_review',
            order_date=datetime.strptime(order_data.get('date_created', '')[:10], '%Y-%m-%d').date() if order_data.get('date_created') else timezone.now().date(),
            original_order_data={'source': 'woocommerce', 'platform_id': str(order_data.get('id', ''))},
        )

        return order
    except Exception as e:
        raise Exception(f"Error creating order: {str(e)}")


def _push_woo_order_status(order, new_status):
    """Push delivery status back to WooCommerce after task completion."""
    WC_STATUS_MAP = {'delivered': 'completed', 'failed': 'failed', 'cancelled': 'cancelled'}
    wc_status = WC_STATUS_MAP.get(new_status)
    if not wc_status:
        return
    try:
        api_settings = business_models.BusinessApiSettings.objects.filter(
            business=order.business, api_type='woocommerce', is_verify_api=True,
        ).first()
        if not api_settings:
            return
        wc_id = None
        if order.original_order_data and isinstance(order.original_order_data, dict):
            wc_id = order.original_order_data.get('platform_id')
        if not wc_id and order.order_number.startswith('WC-'):
            wc_id = order.order_number[3:]
        if not wc_id:
            return
        wcapi = API(
            url=api_settings.site_api_url,
            consumer_key=api_settings.api_key,
            consumer_secret=api_settings.api_secret,
            version='wc/v3',
            timeout=10,
        )
        wcapi.put(f'orders/{wc_id}', data={'status': wc_status})
    except Exception:
        logger.exception("WooCommerce status push failed for order %s", order.order_number)


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
    # Defense in depth: never broadcast an event to every tenant's webhooks.
    # A business must always be supplied so dispatch stays scoped to its owner.
    if business is None:
        logger.warning(f"_send_webhook_event('{event_type}') called without a business; skipping dispatch")
        return []

    webhooks = ezzy_api_models.WebhookEndpoint.objects.filter(
        is_active=True,
        events__contains=[event_type],
        business=business,
    )

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
        client_api_key = ezzy_api_models.ClientApiKey.objects.get(
            key_hash=ezzy_api_models.ClientApiKey.hash_key(api_key), is_active=True
        )
        if not client_api_key.is_valid():
            return Response(
                {'error': 'Invalid or expired API key'},
                status=status.HTTP_401_UNAUTHORIZED
            )
        # These webhooks mutate task/COD state — require the 'write' scope.
        if not client_api_key.has_scope('write'):
            return Response(
                {'error': 'API key lacks write scope'},
                status=status.HTTP_403_FORBIDDEN
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
        notes = serializer.validated_data.get('notes', '')
        driver_id = serializer.validated_data.get('driver_id')
        
        # Update task — SCOPED to the API key's own business (prevents
        # cross-tenant task takeover via task_id enumeration).
        try:
            task = delivery_models.DeliveryTask.objects.select_related('order').get(
                id=task_id, business=client_api_key.business
            )

            # Enforce the delivery state machine — reject illegal jumps
            # (e.g. delivered -> pending) even if the value is a valid choice.
            allowed, reason = task_can_transition(task.dl_task_status, new_status, actor='driver')
            if not allowed:
                return Response(
                    {'error': reason or 'Illegal status transition'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Lock check: Order must be published before task status can change
            if task.order and task.order.order_status in ('to_review', 'to_publish'):
                return Response({
                    'error': 'Task is locked. Order must be published before delivery status can be updated.'
                }, status=status.HTTP_403_FORBIDDEN)

            # Lock check: Prevent status change if order is cancelled
            if task.order and task.order.order_status == 'cancelled':
                return Response({
                    'error': 'Task is locked. Order is cancelled — no delivery status changes allowed.'
                }, status=status.HTTP_403_FORBIDDEN)

            # Lock check: Prevent status change if task is Successful AND COD is settled
            if task.dl_task_status == 'delivered' and task.order and task.order.cod_status_by_staff == 'cod_settled_with_business':
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
            task.save()
            
            # Trigger webhooks for other subscribers
            webhook_payload = {
                'task_id': task_id,
                'task_number': task.dl_task_number,
                'status': new_status,
                'notes': notes,
                'timestamp': timezone.now().isoformat(),
                'driver_id': driver_id
            }
            _send_webhook_event('task_status_update', webhook_payload, business=task.business)

            # Fire auto flows
            try:
                from core.auto_flow_executor import execute_flows_for_trigger
                execute_flows_for_trigger('wh_task_status_update', task=task)
            except Exception:
                pass

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
        client_api_key = ezzy_api_models.ClientApiKey.objects.get(
            key_hash=ezzy_api_models.ClientApiKey.hash_key(api_key), is_active=True
        )
        if not client_api_key.is_valid():
            return Response(
                {'error': 'Invalid or expired API key'},
                status=status.HTTP_401_UNAUTHORIZED
            )
        # These webhooks mutate task/COD state — require the 'write' scope.
        if not client_api_key.has_scope('write'):
            return Response(
                {'error': 'API key lacks write scope'},
                status=status.HTTP_403_FORBIDDEN
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
                # SCOPED to the API key's own business — prevents a client from
                # completing another tenant's task or writing COD into any driver's wallet.
                task = delivery_models.DeliveryTask.objects.select_related(
                    'order', 'order__business'
                ).select_for_update().get(id=task_id, business=client_api_key.business)

                # Lock check: Order must be published before task status can change
                if task.order and task.order.order_status in ('to_review', 'to_publish'):
                    return Response({
                        'error': 'Task is locked. Order must be published before delivery status can be updated.'
                    }, status=status.HTTP_403_FORBIDDEN)

                # Lock check: Prevent status change if order is cancelled
                if task.order and task.order.order_status == 'cancelled':
                    return Response({
                        'error': 'Task is locked. Order is cancelled — no delivery status changes allowed.'
                    }, status=status.HTTP_403_FORBIDDEN)

                # Lock check: Prevent status change if task is Successful AND COD is settled
                if task.dl_task_status == 'delivered' and task.order and task.order.cod_status_by_staff == 'cod_settled_with_business':
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
                    task.completed_at = timezone.now()
                elif status_value in ('failed', 'cancelled'):
                    task.completed_at = timezone.now()
                elif status_value == 'rejected':
                    pass

                # Capture original COD state for idempotency
                was_already_cod_collected = task.cod_collected

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

                    # Record COD collection in driver wallet (idempotent)
                    if task.driver and cod_collected and cod_amount_collected and not was_already_cod_collected:
                        from fleet.wallet_service import WalletService
                        from decimal import Decimal
                        WalletService.record_transaction(
                            driver=task.driver,
                            transaction_type='cod_collection',
                            amount=Decimal(str(cod_amount_collected)),
                            description=f"COD collected for order {task.order.order_number} (via webhook)",
                            delivery_task=task,
                        )

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

            # Fire auto flows
            try:
                from core.auto_flow_executor import execute_flows_for_trigger
                execute_flows_for_trigger('wh_task_completed', task=task)
            except Exception:
                pass

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
        client_api_key = ezzy_api_models.ClientApiKey.objects.get(
            key_hash=ezzy_api_models.ClientApiKey.hash_key(api_key), is_active=True
        )
        if not client_api_key.is_valid():
            return Response(
                {'error': 'Invalid or expired API key'},
                status=status.HTTP_401_UNAUTHORIZED
            )
        # These webhooks mutate task/COD state — require the 'write' scope.
        if not client_api_key.has_scope('write'):
            return Response(
                {'error': 'API key lacks write scope'},
                status=status.HTTP_403_FORBIDDEN
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
            # Dispatch only to the submitting business's own webhooks — never
            # broadcast driver GPS to every tenant's webhook endpoints.
            _send_webhook_event('driver_location_update', webhook_payload, business=client_api_key.business)

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
def _validate_webhook_url(url):
    """
    Guard against SSRF: only allow http/https to public hosts.
    Rejects loopback, private, link-local, reserved and multicast targets.
    Returns (ok: bool, reason: str).
    """
    import ipaddress
    import socket
    from urllib.parse import urlparse

    try:
        parsed = urlparse(url)
    except Exception:
        return False, 'Invalid URL'

    if parsed.scheme not in ('http', 'https'):
        return False, 'Only http/https webhook URLs are allowed'

    host = parsed.hostname
    if not host:
        return False, 'Webhook URL must include a host'

    try:
        # Resolve every address the host maps to and reject internal ranges.
        infos = socket.getaddrinfo(host, None)
    except Exception:
        return False, 'Webhook host could not be resolved'

    for info in infos:
        ip_str = info[4][0]
        try:
            ip = ipaddress.ip_address(ip_str)
        except ValueError:
            return False, 'Webhook host resolved to an invalid address'
        if (ip.is_private or ip.is_loopback or ip.is_link_local
                or ip.is_reserved or ip.is_multicast or ip.is_unspecified):
            return False, 'Webhook URL resolves to a non-public address'

    return True, ''


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_webhook_endpoint(request):
    """Create a new webhook endpoint"""
    serializer = ezzy_api_serializers.WebhookEndpointSerializer(data=request.data)

    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    # Resolve the owning business from the authenticated caller — never trust
    # a business id from the request body (prevented cross-tenant webhook
    # registration and driver-location leakage).
    if request.user.is_staff and request.data.get('business'):
        try:
            business = business_models.Business.objects.get(business_id=request.data.get('business'))
        except business_models.Business.DoesNotExist:
            return Response({'error': 'Business not found'}, status=status.HTTP_404_NOT_FOUND)
    else:
        business = get_api_user_business(request)

    if not business:
        return Response(
            {'error': 'No business is associated with this account'},
            status=status.HTTP_403_FORBIDDEN
        )

    # SSRF guard on the destination URL.
    ok, reason = _validate_webhook_url(serializer.validated_data.get('url', ''))
    if not ok:
        return Response({'error': reason}, status=status.HTTP_400_BAD_REQUEST)

    webhook = serializer.save(business=business)
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

    # Non-staff callers are ALWAYS constrained to their own businesses, even if
    # they pass ?business_id=<someone else> (previously an IDOR that leaked
    # another tenant's pending orders + customer PII).
    if not request.user.is_staff:
        businesses = business_models.Business.objects.filter(user=request.user)
        orders = orders.filter(business__in=businesses)

    # business_id only narrows further (safe for staff; already scoped for others).
    if business_id:
        orders = orders.filter(business_id=business_id)

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

            # Verify the client belongs to the caller's business.
            try:
                client = business_models.Client.objects.get(
                    id=client_id, business=business
                )
            except business_models.Client.DoesNotExist:
                return Response(
                    {'error': 'Client not found'},
                    status=status.HTTP_404_NOT_FOUND
                )

            # Verify the pickup location (if supplied) belongs to the caller's
            # business — prevents attaching another tenant's pickup location.
            pickup_location = None
            if pickup_location_id:
                try:
                    pickup_location = business_models.PickupLocation.objects.get(
                        id=pickup_location_id, business=business
                    )
                except business_models.PickupLocation.DoesNotExist:
                    return Response(
                        {'error': 'Pickup location not found'},
                        status=status.HTTP_404_NOT_FOUND
                    )

            # Create order
            order = orders_models.Order.objects.create(
                business=business,
                client=client,
                delivery_address=delivery_address,
                pickup_location=pickup_location,
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
            for client in clients:
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
# QNAS uses path-based endpoints: /get_buildings/{zone}/{street}
# Requires X-Token and X-Domain headers for authentication

QNAS_BASE_URL = "https://qnas.qa"
QNAS_TOKEN = config("QNAS_TOKEN", default="")
QNAS_DOMAIN = config("QNAS_DOMAIN", default="ezzydelivery.qa")


def _make_qnas_request(request, endpoint, method='GET', data=None):
    """
    Helper function to make requests to QNAS API with proper headers.
    Uses X-Token and X-Domain for authentication.
    """
    url = f"{QNAS_BASE_URL}/{endpoint}"

    headers = {
        "X-Token": QNAS_TOKEN,
        "X-Domain": QNAS_DOMAIN,
        "Accept": "application/json",
        "User-Agent": request.META.get("HTTP_USER_AGENT", "Mozilla/5.0"),
    }

    try:
        if method == 'GET':
            resp = requests.get(url, headers=headers, timeout=15)
        elif method == 'POST':
            headers["Content-Type"] = "application/json"
            resp = requests.post(url, headers=headers, json=data, timeout=15)
        else:
            resp = requests.request(method, url, headers=headers, json=data, timeout=15)

        return resp
    except requests.exceptions.Timeout:
        logger.error(f"QNAS API timeout for endpoint: {endpoint}")
        return None
    except requests.exceptions.RequestException as e:
        logger.error(f"QNAS API request error for endpoint {endpoint}: {str(e)}")
        return None


@csrf_exempt
@login_required(login_url='/accounts/login/')
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
@login_required(login_url='/accounts/login/')
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

    resp = _make_qnas_request(request, f"get_streets/{zone}")

    if resp is None:
        return JsonResponse({'error': 'QNAS API request failed'}, status=502)

    from django.http import HttpResponse
    return HttpResponse(
        resp.content,
        status=resp.status_code,
        content_type=resp.headers.get("Content-Type", "application/json")
    )


@csrf_exempt
@login_required(login_url='/accounts/login/')
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

    resp = _make_qnas_request(request, f"get_buildings/{zone}/{street}")

    if resp is None:
        return JsonResponse({'error': 'QNAS API request failed'}, status=502)

    from django.http import HttpResponse
    return HttpResponse(
        resp.content,
        status=resp.status_code,
        content_type=resp.headers.get("Content-Type", "application/json")
    )


@csrf_exempt
@login_required(login_url='/accounts/login/')
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
@login_required(login_url='/accounts/login/')
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

    resp = _make_qnas_request(request, f"get_location/{zone}/{street}/{building}")

    if resp is None:
        return JsonResponse({'error': 'QNAS API request failed'}, status=502)

    from django.http import HttpResponse
    return HttpResponse(
        resp.content,
        status=resp.status_code,
        content_type=resp.headers.get("Content-Type", "application/json")
    )


@csrf_exempt
@login_required(login_url='/accounts/login/')
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

    resp = _make_qnas_request(request, f"geocode/{lat}/{lng}")

    if resp is None:
        return JsonResponse({'error': 'QNAS API request failed'}, status=502)

    from django.http import HttpResponse
    return HttpResponse(
        resp.content,
        status=resp.status_code,
        content_type=resp.headers.get("Content-Type", "application/json")
    )


@csrf_exempt
@login_required(login_url='/accounts/login/')
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

    resp = _make_qnas_request(request, f"get_zone_polygon/{zone_number}")

    if resp is None:
        return JsonResponse({'error': 'QNAS API request failed'}, status=502)

    from django.http import HttpResponse
    return HttpResponse(
        resp.content,
        status=resp.status_code,
        content_type=resp.headers.get("Content-Type", "application/json")
    )


@csrf_exempt
@login_required(login_url='/accounts/login/')
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
        resp = _make_qnas_request(request, f"get_buildings/{zone}/{street}")

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
@login_required(login_url='/accounts/login/')
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
        resp = _make_qnas_request(request, f"get_buildings/{zone}/{street}")

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
            # Street has no geocoded buildings yet.
            # Confirm the street actually exists in this zone via get_streets.
            logger.info(f"QNAS location: No buildings for zone={zone}, street={street} — checking street exists")
            street_exists = False
            try:
                streets_resp = _make_qnas_request(request, f"get_streets/{zone}")
                if streets_resp and streets_resp.status_code == 200:
                    streets_data = streets_resp.json()
                    for s in (streets_data if isinstance(streets_data, list) else []):
                        if str(s.get('street_number', '')) == str(street):
                            street_exists = True
                            break
            except Exception as e:
                logger.warning(f"QNAS street existence check error: {e}")

            if street_exists:
                # Address is real — use street polygon centroid (same as QNAS website)
                zone_name = None
                try:
                    from delivery.models import ZoneName
                    zn = ZoneName.objects.filter(zone_number=int(zone)).first()
                    if zn:
                        zone_name = zn.zone_name
                except Exception:
                    pass

                poly_resp = _make_qnas_request(request, f"get_street_polygon/{zone}/{street}")
                if poly_resp and poly_resp.status_code == 200:
                    try:
                        poly_data = poly_resp.json()
                        pts = poly_data.get('polygon', [])
                        if pts:
                            clat = sum(p['lat'] for p in pts) / len(pts)
                            clng = sum(p['lng'] for p in pts) / len(pts)
                            logger.info(f"QNAS street polygon centroid: zone={zone}, street={street}, lat={clat}, lng={clng}")
                            return JsonResponse({
                                'success': True,
                                'latitude': round(clat, 7),
                                'longitude': round(clng, 7),
                                'building_number': '',
                                'match_type': 'street_level',
                                'total_buildings': 0,
                                'zone_name': zone_name,
                            })
                    except Exception as e:
                        logger.warning(f"QNAS street polygon parse error: {e}")

                # Street confirmed but polygon unavailable — return informative error
                return JsonResponse({
                    'success': False,
                    'error': f'Street {street} exists in Zone {zone} but has no GPS coordinates yet',
                    'street_exists': True,
                }, status=404)

            logger.warning(f"QNAS location: zone={zone} street={street} not found")
            return JsonResponse({
                'success': False,
                'error': 'Address not found in QNAS',
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

        # Look up zone name from local ZoneName model
        zone_name = None
        try:
            from delivery.models import ZoneName
            zn = ZoneName.objects.filter(zone_number=int(zone)).first()
            if zn:
                zone_name = zn.zone_name
        except Exception:
            pass

        return JsonResponse({
            'success': True,
            'latitude': latitude,
            'longitude': longitude,
            'building_number': selected_building.get('building_number', ''),
            'match_type': match_type,
            'total_buildings': len(buildings),
            'zone_name': zone_name,
        })

    except Exception as e:
        logger.error(f"QNAS location error: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


# =============================================================================
# INBOUND WEBHOOK — Receive orders via POST
# =============================================================================

@api_view(['POST'])
@permission_classes([AllowAny])
def webhook_inbound_order(request, webhook_key):
    """
    Public endpoint: receive order(s) via webhook POST.
    URL: /api/webhooks/order/inbound/<webhook_key>/
    Accepts single order dict or list of orders.
    Stores as TempOrder(source_type='webhook') + WebhookImportLog.
    Verifies X-WC-Webhook-Signature when wc_webhook_secret is set.
    Handles WooCommerce order.updated and order.deleted topics.
    """
    import json as _json
    import base64

    try:
        wk = ezzy_api_models.WebhookImportKey.objects.select_related('business').get(key=webhook_key)
    except ezzy_api_models.WebhookImportKey.DoesNotExist:
        return Response({'success': False, 'error': 'Invalid webhook key'}, status=404)

    if not wk.is_active:
        return Response({'success': False, 'error': 'Webhook key is disabled'}, status=403)

    # --- WooCommerce HMAC-SHA256 signature verification ---
    wc_sig_header = request.META.get('HTTP_X_WC_WEBHOOK_SIGNATURE', '')
    if wc_sig_header and wk.wc_webhook_secret:
        try:
            raw_body = request.body
            expected = base64.b64encode(
                hmac.new(
                    wk.wc_webhook_secret.encode('utf-8'),
                    raw_body,
                    hashlib.sha256,
                ).digest()
            ).decode('utf-8')
            if not hmac.compare_digest(wc_sig_header, expected):
                return Response({'success': False, 'error': 'Invalid webhook signature'}, status=401)
        except Exception:
            return Response({'success': False, 'error': 'Signature verification error'}, status=401)

    business = wk.business
    wc_topic = request.META.get('HTTP_X_WC_WEBHOOK_TOPIC', '')

    # --- Handle WooCommerce order.deleted ---
    if wc_topic == 'order.deleted':
        payload = request.data if isinstance(request.data, dict) else {}
        wc_id = str(payload.get('id', ''))
        if wc_id:
            orders_models.TempOrder.objects.filter(
                business=business, source_type='webhook', platform_id=wc_id,
            ).update(status='cancelled')
        ezzy_api_models.WebhookImportLog.objects.create(
            webhook_key=wk, business=business,
            payload=payload, ip_address=request.META.get('REMOTE_ADDR'),
            headers={'HTTP_X_WC_WEBHOOK_TOPIC': wc_topic},
            status='processed', orders_created=0,
        )
        return Response({'success': True, 'message': 'order.deleted acknowledged'}, status=200)

    # --- Handle WooCommerce order.updated: sync fields on the real Order ---
    if wc_topic == 'order.updated':
        payload = request.data if isinstance(request.data, dict) else {}
        wc_id = str(payload.get('id', ''))
        if wc_id:
            billing = payload.get('billing', {})
            shipping = payload.get('shipping', {})
            updates = {}
            name = f"{billing.get('first_name', '')} {billing.get('last_name', '')}".strip()
            if name:
                updates['customer_name'] = name
            if billing.get('phone'):
                updates['customer_phone'] = billing['phone']
            addr = f"{shipping.get('address_1', '')} {shipping.get('city', '')}".strip()
            if addr:
                updates['customer_address'] = addr
            if updates:
                orders_models.Order.objects.filter(
                    business=business,
                    order_number=f'WC-{wc_id}',
                ).update(**updates)
        ezzy_api_models.WebhookImportLog.objects.create(
            webhook_key=wk, business=business,
            payload=payload, ip_address=request.META.get('REMOTE_ADDR'),
            headers={'HTTP_X_WC_WEBHOOK_TOPIC': wc_topic},
            status='processed', orders_created=0,
        )
        return Response({'success': True, 'message': 'order.updated acknowledged'}, status=200)

    # Get client IP
    x_fwd = request.META.get('HTTP_X_FORWARDED_FOR')
    ip = x_fwd.split(',')[0].strip() if x_fwd else request.META.get('REMOTE_ADDR')

    # Save selected headers
    hdr = {}
    for k in ('HTTP_CONTENT_TYPE', 'HTTP_USER_AGENT', 'HTTP_X_SHOPIFY_SHOP_DOMAIN',
              'HTTP_X_SHOPIFY_TOPIC', 'HTTP_X_WC_WEBHOOK_TOPIC', 'HTTP_X_WC_WEBHOOK_SOURCE'):
        if request.META.get(k):
            hdr[k] = request.META[k]

    # Parse payload
    payload = request.data
    if isinstance(payload, list):
        orders_list = payload
    elif isinstance(payload, dict):
        orders_list = [payload]
    else:
        return Response({'success': False, 'error': 'Invalid JSON payload'}, status=400)

    # Create webhook log
    log = ezzy_api_models.WebhookImportLog.objects.create(
        webhook_key=wk,
        business=business,
        payload=payload,
        ip_address=ip,
        headers=hdr,
    )

    # Auto-map common field names to our standard fields
    FIELD_MAP = {
        # Order ID
        'order_id': 'client_order_code', 'order_number': 'client_order_code',
        'order_code': 'client_order_code', 'id': 'client_order_code',
        'name': 'client_order_code', 'order': 'client_order_code',
        # Customer
        'customer_name': 'customer_name', 'customer': 'customer_name',
        'client_name': 'customer_name', 'recipient': 'customer_name',
        # Phone
        'phone': 'customer_phone', 'customer_phone': 'customer_phone',
        'mobile': 'customer_phone', 'contact': 'customer_phone',
        # Address
        'address': 'customer_address', 'customer_address': 'customer_address',
        'delivery_address': 'customer_address', 'shipping_address': 'customer_address',
        # COD
        'cod': 'cod_amount', 'cod_amount': 'cod_amount', 'amount': 'cod_amount',
        'total': 'cod_amount', 'total_price': 'cod_amount', 'price': 'cod_amount',
        # Package
        'package_desc': 'package_desc', 'description': 'package_desc',
        'items': 'package_desc', 'product': 'package_desc',
        'package_qty': 'package_qty', 'qty': 'package_qty', 'quantity': 'package_qty',
        # Notes
        'notes': 'seller_notes', 'note': 'seller_notes', 'seller_notes': 'seller_notes',
    }

    created_count = 0
    for order_data in orders_list:
        if not isinstance(order_data, dict):
            continue

        # Map fields — only scalar values (skip dicts/lists, handle them below)
        mapped = {}
        for src_key, val in order_data.items():
            if isinstance(val, (dict, list)):
                continue
            db_field = FIELD_MAP.get(src_key.lower().strip())
            if db_field and val is not None:
                mapped[db_field] = str(val).strip()

        # Handle nested customer object (Shopify-style)
        cust = order_data.get('customer')
        if isinstance(cust, dict):
            if not mapped.get('customer_name'):
                name = f"{cust.get('first_name', '')} {cust.get('last_name', '')}".strip()
                if name:
                    mapped['customer_name'] = name
            if not mapped.get('customer_phone'):
                mapped['customer_phone'] = cust.get('phone', '') or ''
            # Also check default_address
            da = cust.get('default_address')
            if isinstance(da, dict):
                if not mapped.get('customer_phone'):
                    mapped['customer_phone'] = da.get('phone', '') or ''
                if not mapped.get('customer_address'):
                    mapped['customer_address'] = da.get('address1', '') or ''

        # Handle nested shipping_address (Shopify-style)
        sa = order_data.get('shipping_address')
        if isinstance(sa, dict):
            if not mapped.get('customer_address'):
                mapped['customer_address'] = sa.get('address1', '') or ''
            if not mapped.get('customer_name'):
                name = f"{sa.get('first_name', '')} {sa.get('last_name', '')}".strip()
                if name:
                    mapped['customer_name'] = name
            if not mapped.get('customer_phone'):
                mapped['customer_phone'] = sa.get('phone', '') or ''

        # Handle nested billing (WooCommerce-style)
        billing = order_data.get('billing')
        if isinstance(billing, dict):
            if not mapped.get('customer_name'):
                name = f"{billing.get('first_name', '')} {billing.get('last_name', '')}".strip()
                if name:
                    mapped['customer_name'] = name
            if not mapped.get('customer_phone'):
                mapped['customer_phone'] = billing.get('phone', '') or ''
            if not mapped.get('customer_address'):
                mapped['customer_address'] = billing.get('address_1', '') or ''

        # Handle nested line_items
        line_items = order_data.get('line_items', [])
        if isinstance(line_items, list) and line_items:
            for idx, li in enumerate(line_items[:10], 1):
                if isinstance(li, dict):
                    li_name = li.get('name') or li.get('title', '')
                    li_qty = li.get('quantity') or li.get('qty', 1)
                    mapped[f'product_{idx}'] = str(li_name)
                    mapped[f'count_{idx}'] = str(li_qty)
            if not mapped.get('package_desc'):
                desc = ', '.join(
                    f"{li.get('name') or li.get('title', '')} x{li.get('quantity') or li.get('qty', 1)}"
                    for li in line_items if isinstance(li, dict)
                )
                mapped['package_desc'] = desc

        # Create TempOrder — coerce to '' since these columns are NOT NULL and
        # a mapped value may be an explicit None that .get(key, '') won't catch.
        orders_models.TempOrder.objects.create(
            business=business,
            source_type='webhook',
            platform_id=mapped.get('client_order_code') or '',
            client_order_code=mapped.get('client_order_code') or '',
            customer_name=mapped.get('customer_name') or '',
            customer_phone=mapped.get('customer_phone') or '',
            customer_address=mapped.get('customer_address') or '',
            cod_amount=mapped.get('cod_amount') or '',
            package_desc=mapped.get('package_desc') or '',
            raw_row=order_data,
            status='new',
        )
        created_count += 1

    # Update log and key stats
    log.orders_created = created_count
    log.status = 'processed'
    log.save(update_fields=['orders_created', 'status'])

    wk.last_used = timezone.now()
    wk.total_received = (wk.total_received or 0) + created_count
    wk.save(update_fields=['last_used', 'total_received'])

    return Response({
        'success': True,
        'message': f'{created_count} order(s) received',
        'orders_created': created_count,
    }, status=201)


# ==================== COD APIs ====================

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def driver_cod_submit(request):
    """Driver submits collected COD cash to admin for a specific task."""
    try:
        driver = fleet_models.Driver.objects.get(user=request.user)
    except fleet_models.Driver.DoesNotExist:
        return Response({'error': 'Driver profile not found'}, status=status.HTTP_404_NOT_FOUND)

    task_id = request.data.get('task_id')
    payment_method = request.data.get('payment_method', 'cash')
    notes = request.data.get('notes', '')

    if not task_id:
        return Response({'error': 'task_id is required'}, status=status.HTTP_400_BAD_REQUEST)

    valid_payment_methods = [c[0] for c in fleet_models.DriverTransaction.PAYMENT_METHOD_CHOICES]
    if payment_method not in valid_payment_methods:
        return Response(
            {'error': f'Invalid payment_method. Must be one of: {valid_payment_methods}'},
            status=status.HTTP_400_BAD_REQUEST
        )

    try:
        task = delivery_models.DeliveryTask.objects.select_related(
            'order', 'driver'
        ).get(id=task_id, driver=driver)
    except delivery_models.DeliveryTask.DoesNotExist:
        return Response({'error': 'Task not found or not assigned to you'}, status=status.HTTP_404_NOT_FOUND)

    if not task.cod_collected:
        return Response({'error': 'COD has not been collected for this task yet'}, status=status.HTTP_400_BAD_REQUEST)

    if task.cod_settled:
        return Response({'error': 'COD for this task has already been submitted'}, status=status.HTTP_400_BAD_REQUEST)

    cod_amount = task.cod_collected_amount
    if not cod_amount or cod_amount <= 0:
        return Response({'error': 'No COD amount to submit'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        from fleet.wallet_service import WalletService
        with transaction.atomic():
            txn = WalletService.submit_cod_to_admin(
                driver=driver,
                amount=cod_amount,
                created_by=request.user,
                payment_method=payment_method,
                notes=notes or f'COD submission for task #{task.dl_task_number}',
                delivery_ids=[task.id],
            )
    except ValueError as e:
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    driver.refresh_from_db()
    task.refresh_from_db()

    return Response({
        'success': True,
        'transaction_code': txn.transaction_code,
        'task_id': task.id,
        'task_number': task.dl_task_number,
        'cod_amount': str(cod_amount),
        'cod_in_hand': str(driver.cod_in_hand),
        'submitted_at': task.cod_settled_at.isoformat() if task.cod_settled_at else timezone.now().isoformat(),
    }, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def driver_cod_pending(request):
    """List tasks where COD was collected but not yet submitted to admin."""
    try:
        driver = fleet_models.Driver.objects.get(user=request.user)
    except fleet_models.Driver.DoesNotExist:
        return Response({'error': 'Driver profile not found'}, status=status.HTTP_404_NOT_FOUND)

    tasks = delivery_models.DeliveryTask.objects.filter(
        driver=driver,
        cod_collected=True,
        cod_settled=False,
    ).select_related('order').order_by('-cod_collected_at')

    data = []
    for task in tasks:
        data.append({
            'task_id': task.id,
            'task_number': task.dl_task_number,
            'order_number': task.order.order_number if task.order else None,
            'customer_name': task.order.customer_name if task.order else None,
            'cod_collected_amount': str(task.cod_collected_amount),
            'cod_collected_at': task.cod_collected_at.isoformat() if task.cod_collected_at else None,
        })

    return Response({
        'count': len(data),
        'total_pending_cod': str(driver.cod_in_hand),
        'tasks': data,
    }, status=status.HTTP_200_OK)


# ==================== DRIVER TRANSACTION APIs ====================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def driver_transactions(request):
    """List all financial transactions for the authenticated driver."""
    try:
        driver = fleet_models.Driver.objects.get(user=request.user)
    except fleet_models.Driver.DoesNotExist:
        return Response({'error': 'Driver profile not found'}, status=status.HTTP_404_NOT_FOUND)

    txns = fleet_models.DriverTransaction.objects.filter(
        driver=driver
    ).select_related('delivery_task', 'settlement').order_by('-created_at')

    transaction_type = request.query_params.get('type')
    if transaction_type:
        txns = txns.filter(transaction_type=transaction_type)

    start_date = request.query_params.get('start_date')
    end_date = request.query_params.get('end_date')
    if start_date:
        try:
            txns = txns.filter(created_at__date__gte=datetime.strptime(start_date, '%Y-%m-%d').date())
        except ValueError:
            pass
    if end_date:
        try:
            txns = txns.filter(created_at__date__lte=datetime.strptime(end_date, '%Y-%m-%d').date())
        except ValueError:
            pass

    data = []
    for txn in txns:
        data.append({
            'transaction_code': txn.transaction_code,
            'transaction_type': txn.transaction_type,
            'transaction_type_display': txn.get_transaction_type_display(),
            'amount': str(txn.amount),
            'description': txn.description,
            'payment_method': txn.payment_method,
            'reference_number': txn.reference_number,
            'task_id': txn.delivery_task_id,
            'task_number': txn.delivery_task.dl_task_number if txn.delivery_task else None,
            'settlement_code': txn.settlement.settlement_code if txn.settlement else None,
            'cod_in_hand_after': str(txn.cod_in_hand_after),
            'wallet_balance_after': str(txn.wallet_balance_after),
            'pending_earnings_after': str(txn.pending_earnings_after),
            'created_at': txn.created_at.isoformat(),
        })

    return Response({'count': len(data), 'transactions': data}, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def driver_transaction_detail(request, code):
    """Get details of a single transaction by its code."""
    try:
        driver = fleet_models.Driver.objects.get(user=request.user)
    except fleet_models.Driver.DoesNotExist:
        return Response({'error': 'Driver profile not found'}, status=status.HTTP_404_NOT_FOUND)

    try:
        txn = fleet_models.DriverTransaction.objects.select_related(
            'delivery_task', 'settlement', 'created_by'
        ).get(transaction_code=code, driver=driver)
    except fleet_models.DriverTransaction.DoesNotExist:
        return Response({'error': 'Transaction not found'}, status=status.HTTP_404_NOT_FOUND)

    return Response({
        'transaction_code': txn.transaction_code,
        'transaction_type': txn.transaction_type,
        'transaction_type_display': txn.get_transaction_type_display(),
        'amount': str(txn.amount),
        'description': txn.description,
        'payment_method': txn.payment_method,
        'reference_number': txn.reference_number,
        'notes': txn.notes,
        'task_id': txn.delivery_task_id,
        'task_number': txn.delivery_task.dl_task_number if txn.delivery_task else None,
        'settlement_code': txn.settlement.settlement_code if txn.settlement else None,
        'cod_in_hand_after': str(txn.cod_in_hand_after),
        'wallet_balance_after': str(txn.wallet_balance_after),
        'pending_earnings_after': str(txn.pending_earnings_after),
        'created_at': txn.created_at.isoformat(),
    }, status=status.HTTP_200_OK)


# ==================== DRIVER SETTLEMENT APIs ====================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def driver_settlements(request):
    """List all earnings settlements for the authenticated driver."""
    try:
        driver = fleet_models.Driver.objects.get(user=request.user)
    except fleet_models.Driver.DoesNotExist:
        return Response({'error': 'Driver profile not found'}, status=status.HTTP_404_NOT_FOUND)

    settlements = fleet_models.DriverSettlement.objects.filter(
        driver=driver
    ).order_by('-created_at')

    settlement_status = request.query_params.get('status')
    if settlement_status:
        settlements = settlements.filter(status=settlement_status)

    data = []
    for s in settlements:
        data.append({
            'settlement_code': s.settlement_code,
            'status': s.status,
            'status_display': s.get_status_display(),
            'period_start': s.period_start.isoformat(),
            'period_end': s.period_end.isoformat(),
            'total_deliveries': s.total_deliveries,
            'gross_earnings': str(s.gross_earnings),
            'deductions': str(s.deductions),
            'bonuses': str(s.bonuses),
            'net_amount': str(s.net_amount),
            'payment_method': s.payment_method,
            'payment_reference': s.payment_reference,
            'created_at': s.created_at.isoformat(),
            'approved_at': s.approved_at.isoformat() if s.approved_at else None,
            'paid_at': s.paid_at.isoformat() if s.paid_at else None,
        })

    return Response({'count': len(data), 'settlements': data}, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def driver_settlement_detail(request, code):
    """Get full details of a single settlement including its transactions."""
    try:
        driver = fleet_models.Driver.objects.get(user=request.user)
    except fleet_models.Driver.DoesNotExist:
        return Response({'error': 'Driver profile not found'}, status=status.HTTP_404_NOT_FOUND)

    try:
        s = fleet_models.DriverSettlement.objects.prefetch_related(
            'transactions'
        ).get(settlement_code=code, driver=driver)
    except fleet_models.DriverSettlement.DoesNotExist:
        return Response({'error': 'Settlement not found'}, status=status.HTTP_404_NOT_FOUND)

    txns = []
    for txn in s.transactions.all().order_by('-created_at'):
        txns.append({
            'transaction_code': txn.transaction_code,
            'transaction_type': txn.transaction_type,
            'transaction_type_display': txn.get_transaction_type_display(),
            'amount': str(txn.amount),
            'description': txn.description,
            'created_at': txn.created_at.isoformat(),
        })

    return Response({
        'settlement_code': s.settlement_code,
        'status': s.status,
        'status_display': s.get_status_display(),
        'period_start': s.period_start.isoformat(),
        'period_end': s.period_end.isoformat(),
        'total_deliveries': s.total_deliveries,
        'total_delivery_charges': str(s.total_delivery_charges),
        'gross_earnings': str(s.gross_earnings),
        'deductions': str(s.deductions),
        'bonuses': str(s.bonuses),
        'net_amount': str(s.net_amount),
        'payment_method': s.payment_method,
        'payment_reference': s.payment_reference,
        'notes': s.notes,
        'created_at': s.created_at.isoformat(),
        'approved_at': s.approved_at.isoformat() if s.approved_at else None,
        'paid_at': s.paid_at.isoformat() if s.paid_at else None,
        'transactions': txns,
    }, status=status.HTTP_200_OK)


# ==================== DRIVER NOTIFICATION APIs ====================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def driver_notifications(request):
    """List notifications for the authenticated driver."""
    try:
        driver = fleet_models.Driver.objects.get(user=request.user)
    except fleet_models.Driver.DoesNotExist:
        return Response({'error': 'Driver profile not found'}, status=status.HTTP_404_NOT_FOUND)

    notifs = fleet_models.DriverNotification.objects.filter(
        driver=driver
    ).order_by('-created_at')

    unread_only = request.query_params.get('unread')
    if unread_only == '1' or unread_only == 'true':
        notifs = notifs.filter(is_read=False)

    # Limit to last 100 notifications
    notifs = notifs[:100]

    data = []
    for n in notifs:
        data.append({
            'id': n.id,
            'title': n.title,
            'message': n.message,
            'notification_type': n.notification_type,
            'related_task_id': n.related_task_id,
            'is_read': n.is_read,
            'created_at': n.created_at.isoformat(),
            'read_at': n.read_at.isoformat() if n.read_at else None,
        })

    unread_count = fleet_models.DriverNotification.objects.filter(
        driver=driver, is_read=False
    ).count()

    return Response({
        'unread_count': unread_count,
        'notifications': data,
    }, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def driver_notifications_mark_read(request):
    """Mark one or more notifications as read.

    Body (optional): {"ids": [1, 2, 3]}
    If ids is omitted, ALL unread notifications are marked read.
    """
    try:
        driver = fleet_models.Driver.objects.get(user=request.user)
    except fleet_models.Driver.DoesNotExist:
        return Response({'error': 'Driver profile not found'}, status=status.HTTP_404_NOT_FOUND)

    ids = request.data.get('ids')
    now = timezone.now()

    qs = fleet_models.DriverNotification.objects.filter(driver=driver, is_read=False)
    if ids:
        if not isinstance(ids, list):
            return Response({'error': 'ids must be a list'}, status=status.HTTP_400_BAD_REQUEST)
        qs = qs.filter(id__in=ids)

    updated = qs.update(is_read=True, read_at=now)

    return Response({'success': True, 'marked_read': updated}, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def driver_device_token(request):
    """Store or update the FCM/APNs push notification device token for the driver.

    Body: {"token": "<device_token>", "platform": "android"|"ios"|"web"}
    Stored on the Driver profile in driver_meta JSON field.
    """
    try:
        driver = fleet_models.Driver.objects.get(user=request.user)
    except fleet_models.Driver.DoesNotExist:
        return Response({'error': 'Driver profile not found'}, status=status.HTTP_404_NOT_FOUND)

    token = request.data.get('token', '').strip()
    platform = request.data.get('platform', 'android')

    if not token:
        return Response({'error': 'token is required'}, status=status.HTTP_400_BAD_REQUEST)

    valid_platforms = ['android', 'ios', 'web']
    if platform not in valid_platforms:
        return Response(
            {'error': f'platform must be one of: {valid_platforms}'},
            status=status.HTTP_400_BAD_REQUEST
        )

    # Store in driver_meta JSON field (create if not exists)
    meta = driver.driver_meta or {}
    meta['push_token'] = token
    meta['push_platform'] = platform
    meta['push_token_updated_at'] = timezone.now().isoformat()
    driver.driver_meta = meta
    driver.save(update_fields=['driver_meta'])

    return Response({'success': True, 'platform': platform}, status=status.HTTP_200_OK)


# ==================== DRIVER AUTH / STATUS / DASHBOARD APIs ====================

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def driver_logout(request):
    """Invalidate the driver's auth token and set availability to offline."""
    try:
        driver = fleet_models.Driver.objects.get(user=request.user)
        driver.driver_availability = 'offline'
        driver.save(update_fields=['driver_availability'])
    except fleet_models.Driver.DoesNotExist:
        pass  # Still delete the token even if driver profile is missing

    try:
        request.user.auth_token.delete()
    except Exception:
        pass

    return Response({'success': True}, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def driver_set_status(request):
    """Update driver availability status.

    Body: {"availability": "available"|"on_break"|"offline"|"on_delivery"|"returning"}
    """
    try:
        driver = fleet_models.Driver.objects.get(user=request.user)
    except fleet_models.Driver.DoesNotExist:
        return Response({'error': 'Driver profile not found'}, status=status.HTTP_404_NOT_FOUND)

    availability = request.data.get('availability', '').strip()
    valid = [c[0] for c in fleet_models.DRIVER_AVAILABILITY_CHOICES]
    if availability not in valid:
        return Response(
            {'error': f'Invalid availability. Must be one of: {valid}'},
            status=status.HTTP_400_BAD_REQUEST
        )

    driver.driver_availability = availability
    driver.save(update_fields=['driver_availability'])

    return Response({
        'success': True,
        'availability': driver.driver_availability,
        'availability_display': driver.get_driver_availability_display(),
    }, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def driver_dashboard(request):
    """Aggregated dashboard data for the driver app home screen.

    Returns:
      - wallet snapshot (cod_in_hand, credit_limit, pending_earnings, wallet_usage_pct)
      - today's task stats (total, completed, in_progress)
      - active task (first in-progress task with order info)
      - pending COD count
      - unread notification count
    """
    try:
        driver = fleet_models.Driver.objects.get(user=request.user)
    except fleet_models.Driver.DoesNotExist:
        return Response({'error': 'Driver profile not found'}, status=status.HTTP_404_NOT_FOUND)

    today = timezone.localdate()

    ACTIVE_STATUSES = [
        'accepted', 'picked_up', 'start_ride',
        'out_for_delivery', 'in_transit', 'contacted', 'non_reachable',
    ]

    today_tasks = delivery_models.DeliveryTask.objects.filter(
        driver=driver,
        dl_task_publish=True,
        dl_task_date=today,
    ).exclude(order__order_status='cancelled')

    total_today = today_tasks.count()
    completed_today = today_tasks.filter(dl_task_status='delivered').count()
    in_progress_today = today_tasks.filter(dl_task_status__in=ACTIVE_STATUSES).count()

    # First active task for quick access
    active_task_qs = today_tasks.filter(
        dl_task_status__in=ACTIVE_STATUSES
    ).select_related('order').order_by('dl_task_date', 'id').first()

    active_task = None
    if active_task_qs:
        t = active_task_qs
        active_task = {
            'task_id': t.id,
            'task_number': t.dl_task_number,
            'status': t.dl_task_status,
            'order_number': t.order.order_number if t.order else None,
            'customer_name': t.order.customer_name if t.order else None,
            'customer_phone': t.order.customer_phone if t.order else None,
            'delivery_address': t.order.delivery_address if t.order else None,
            'cod_amount': str(t.order.cod_amount) if t.order else '0',
            'cod_collected': t.cod_collected,
        }

    # Pending COD (collected but not submitted)
    pending_cod_count = delivery_models.DeliveryTask.objects.filter(
        driver=driver,
        cod_collected=True,
        cod_settled=False,
    ).count()

    # Unread notifications
    unread_notif_count = fleet_models.DriverNotification.objects.filter(
        driver=driver, is_read=False
    ).count()

    return Response({
        'driver': {
            'driver_id': driver.driver_id,
            'driver_code': driver.driver_code,
            'driver_name': str(driver),
            'availability': driver.driver_availability,
            'availability_display': driver.get_driver_availability_display(),
            'driver_rating': driver.driver_rating,
        },
        'wallet': {
            'cod_in_hand': str(driver.cod_in_hand),
            'credit_limit': str(driver.credit_limit),
            'available_credit': str(driver.available_credit),
            'pending_earnings': str(driver.pending_earnings),
            'wallet_usage_pct': round(float(driver.wallet_usage_percentage), 1),
            'is_wallet_warning': driver.is_wallet_warning,
            'is_wallet_blocked': driver.is_wallet_blocked,
        },
        'today_stats': {
            'total': total_today,
            'completed': completed_today,
            'in_progress': in_progress_today,
            'pending': total_today - completed_today - in_progress_today,
        },
        'active_task': active_task,
        'pending_cod_count': pending_cod_count,
        'unread_notifications': unread_notif_count,
    }, status=status.HTTP_200_OK)


# ==================== NEW DRIVER APP ENDPOINTS ====================


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def driver_cod_submit_bulk(request):
    """Bulk COD submission — submit multiple tasks at once.

    Body:
        task_ids (list, required): List of DeliveryTask IDs to settle
        payment_method (str): cash | bank | atm | fawran
        notes (str, optional)
    """
    try:
        driver = fleet_models.Driver.objects.get(user=request.user)
    except fleet_models.Driver.DoesNotExist:
        return Response({'error': 'Driver profile not found'}, status=status.HTTP_404_NOT_FOUND)

    task_ids = request.data.get('task_ids', [])
    payment_method = request.data.get('payment_method', 'cash')
    notes = request.data.get('notes', '')

    if not task_ids or not isinstance(task_ids, list):
        return Response({'error': 'task_ids must be a non-empty list'}, status=status.HTTP_400_BAD_REQUEST)

    valid_methods = ['cash', 'bank', 'atm', 'fawran']
    if payment_method not in valid_methods:
        return Response({'error': f'payment_method must be one of {valid_methods}'}, status=status.HTTP_400_BAD_REQUEST)

    tasks = delivery_models.DeliveryTask.objects.filter(
        id__in=task_ids, driver=driver, cod_collected=True, cod_settled=False,
    )
    if tasks.count() != len(task_ids):
        return Response({'error': 'One or more task_ids are invalid, not assigned to you, or COD not yet collected'}, status=status.HTTP_400_BAD_REQUEST)

    total_amount = sum(t.cod_collected_amount or 0 for t in tasks)
    if total_amount <= 0:
        return Response({'error': 'Total COD amount is zero'}, status=status.HTTP_400_BAD_REQUEST)

    from fleet.wallet_service import WalletService
    cod_in_hand_before = driver.cod_in_hand

    try:
        with transaction.atomic():
            txn = WalletService.submit_cod_to_admin(
                driver=driver,
                amount=total_amount,
                created_by=request.user,
                payment_method=payment_method,
                notes=notes,
                delivery_ids=list(task_ids),
            )
    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    driver.refresh_from_db()
    return Response({
        'transaction_code': txn.transaction_code,
        'submitted_amount': str(total_amount),
        'payment_method': payment_method,
        'cod_in_hand_before': str(cod_in_hand_before),
        'cod_in_hand_after': str(driver.cod_in_hand),
        'tasks_settled': len(task_ids),
        'submitted_at': txn.created_at.isoformat(),
    }, status=status.HTTP_201_CREATED)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def driver_order_lookup(request):
    """Look up an order by order_number or client_order_code (barcode scan at pickup).

    Query params:
        q (str, required): Order number or client order code
    """
    try:
        driver = fleet_models.Driver.objects.get(user=request.user)
    except fleet_models.Driver.DoesNotExist:
        return Response({'error': 'Driver profile not found'}, status=status.HTTP_404_NOT_FOUND)

    q = request.query_params.get('q', '').strip()
    if not q:
        return Response({'error': 'Query parameter q is required'}, status=status.HTTP_400_BAD_REQUEST)

    order = orders_models.Order.objects.filter(
        Q(order_number=q) | Q(client_order_code=q)
    ).first()
    if not order:
        return Response({'error': 'Order not found'}, status=status.HTTP_404_NOT_FOUND)

    task = delivery_models.DeliveryTask.objects.filter(
        order=order, driver=driver,
    ).select_related('order').first()
    if not task:
        return Response({'error': 'This order is not assigned to you'}, status=status.HTTP_403_FORBIDDEN)

    return Response({
        'task_id': task.id,
        'task_number': task.dl_task_number,
        'task_status': task.dl_task_status,
        'order_number': order.order_number,
        'customer_name': order.customer_name,
        'customer_phone': order.customer_phone,
        'delivery_address': order.customer_address,
        'cod_amount': str(order.cod_amount),
        'cod_collected': task.cod_collected,
        'package_description': order.package_description,
        'package_qty': order.package_qty,
    }, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def driver_report_task_issue(request, task_id):
    """Driver reports a problem with a delivery task.

    Body:
        issue_type (str): wrong_address | customer_refused | damaged_package |
                          access_denied | customer_unreachable | other
        description (str, required)
        latitude (decimal, optional)
        longitude (decimal, optional)
    """
    try:
        driver = fleet_models.Driver.objects.get(user=request.user)
    except fleet_models.Driver.DoesNotExist:
        return Response({'error': 'Driver profile not found'}, status=status.HTTP_404_NOT_FOUND)

    try:
        task = delivery_models.DeliveryTask.objects.get(id=task_id, driver=driver)
    except delivery_models.DeliveryTask.DoesNotExist:
        return Response({'error': 'Task not found or not assigned to you'}, status=status.HTTP_404_NOT_FOUND)

    VALID_ISSUE_TYPES = [
        'wrong_address', 'customer_refused', 'damaged_package',
        'access_denied', 'customer_unreachable', 'other',
    ]
    issue_type = request.data.get('issue_type', 'other')
    description = request.data.get('description', '').strip()
    latitude = request.data.get('latitude')
    longitude = request.data.get('longitude')

    if not description:
        return Response({'error': 'description is required'}, status=status.HTTP_400_BAD_REQUEST)
    if issue_type not in VALID_ISSUE_TYPES:
        return Response({'error': f'issue_type must be one of {VALID_ISSUE_TYPES}'}, status=status.HTTP_400_BAD_REQUEST)

    issue_note = f"[DRIVER ISSUE — {issue_type.upper()}] {description}"
    if latitude and longitude:
        issue_note += f" | GPS: {latitude}, {longitude}"

    comment = None
    if task.order:
        comment = orders_models.OrderComments.objects.create(
            order=task.order,
            body=issue_note,
            user=request.user,
        )

    if issue_type == 'customer_unreachable' and task.dl_task_status not in ['delivered', 'failed', 'cancelled']:
        task.dl_task_status = 'non_reachable'
        task.save(update_fields=['dl_task_status'])

    return Response({
        'issue_id': comment.id if comment else None,
        'task_id': task.id,
        'task_number': task.dl_task_number,
        'issue_type': issue_type,
        'status': 'reported',
        'reported_at': timezone.now().isoformat(),
    }, status=status.HTTP_201_CREATED)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def driver_pickup_locations(request):
    """List active pickup locations for tasks currently assigned to this driver."""
    try:
        driver = fleet_models.Driver.objects.get(user=request.user)
    except fleet_models.Driver.DoesNotExist:
        return Response({'error': 'Driver profile not found'}, status=status.HTTP_404_NOT_FOUND)

    location_ids = delivery_models.DeliveryTask.objects.filter(
        driver=driver,
        dl_task_publish=True,
        dl_task_status__in=['pending', 'assigned', 'accepted'],
        order__pickup_location__isnull=False,
    ).values_list('order__pickup_location_id', flat=True).distinct()

    locations = business_models.PickupLocation.objects.filter(
        id__in=location_ids,
        pickup_status='active',
    ).select_related('business')

    data = [{
        'id': loc.id,
        'name': loc.pickup_location_title,
        'locality': loc.locality,
        'zone': loc.pickup_zone_no,
        'street': loc.pickup_street_no,
        'building': loc.pickup_building_no,
        'latitude': str(loc.pickup_lat) if loc.pickup_lat else None,
        'longitude': str(loc.pickup_lon) if loc.pickup_lon else None,
        'business_name': loc.business.business_name if loc.business else None,
        'is_default': loc.is_default,
        'is_fulfilment_center': loc.is_fulfilment_center,
    } for loc in locations]

    return Response({'count': len(data), 'locations': data}, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def driver_task_items(request, task_id):
    """Get package contents (order items) for a delivery task."""
    try:
        driver = fleet_models.Driver.objects.get(user=request.user)
    except fleet_models.Driver.DoesNotExist:
        return Response({'error': 'Driver profile not found'}, status=status.HTTP_404_NOT_FOUND)

    try:
        task = delivery_models.DeliveryTask.objects.select_related('order').get(
            id=task_id, driver=driver,
        )
    except delivery_models.DeliveryTask.DoesNotExist:
        return Response({'error': 'Task not found or not assigned to you'}, status=status.HTTP_404_NOT_FOUND)

    if not task.order:
        return Response({'error': 'No order linked to this task'}, status=status.HTTP_404_NOT_FOUND)

    order = task.order
    items_qs = orders_models.OrderItem.objects.filter(order=order).select_related('product')

    items = []
    for item in items_qs:
        product = item.product
        items.append({
            'id': item.id,
            'name': product.product_name if product else (item.notes or 'Item'),
            'sku': product.product_sku if product else None,
            'quantity': item.quantity,
            'unit_price': str(item.unit_price) if item.unit_price else None,
            'total_price': str(item.total_price) if item.total_price else None,
            'notes': item.notes,
            'weight_kg': float(product.product_weight) if product and getattr(product, 'product_weight', None) else None,
            'is_fragile': getattr(product, 'is_fragile', False) if product else False,
        })

    return Response({
        'task_id': task.id,
        'task_number': task.dl_task_number,
        'order_number': order.order_number,
        'package_description': order.package_description,
        'package_qty': order.package_qty,
        'special_instructions': order.order_notes,
        'total_items': len(items),
        'items': items,
    }, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def driver_document_upload(request):
    """Driver uploads or updates their own identity document.

    Body (multipart):
        document_type: QID | Driving License | Passport | National Identification
        document_no (str, required)
        document_expiry_date (str, optional): YYYY-MM-DD
        document_file (file): Front image
        document_file_back (file, optional): Back image
    """
    try:
        driver = fleet_models.Driver.objects.get(user=request.user)
    except fleet_models.Driver.DoesNotExist:
        return Response({'error': 'Driver profile not found'}, status=status.HTTP_404_NOT_FOUND)

    VALID_DOC_TYPES = ['QID', 'Driving License', 'Passport', 'National Identification']
    document_type = request.data.get('document_type', '').strip()
    document_no = request.data.get('document_no', '').strip()
    document_expiry_date = request.data.get('document_expiry_date') or None
    document_file = request.FILES.get('document_file')
    document_file_back = request.FILES.get('document_file_back')

    if document_type not in VALID_DOC_TYPES:
        return Response({'error': f'document_type must be one of {VALID_DOC_TYPES}'}, status=status.HTTP_400_BAD_REQUEST)
    if not document_no:
        return Response({'error': 'document_no is required'}, status=status.HTTP_400_BAD_REQUEST)

    doc, created = fleet_models.DriverDocument.objects.update_or_create(
        driver=driver,
        document_type=document_type,
        defaults={
            'document_no': document_no,
            'document_expiry_date': document_expiry_date,
        },
    )
    if document_file:
        doc.document_file = document_file
    if document_file_back:
        doc.document_file_back = document_file_back
    doc.save()

    return Response({
        'document_id': doc.id,
        'document_type': doc.document_type,
        'document_no': doc.document_no,
        'document_expiry_date': str(doc.document_expiry_date) if doc.document_expiry_date else None,
        'action': 'created' if created else 'updated',
        'status': 'pending_review',
        'message': 'Document uploaded. Pending admin review.',
    }, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def driver_performance_metrics(request):
    """Driver performance metrics — success rate, earnings, rating.

    Query params:
        period (str): week | month | all  (default: month)
    """
    try:
        driver = fleet_models.Driver.objects.get(user=request.user)
    except fleet_models.Driver.DoesNotExist:
        return Response({'error': 'Driver profile not found'}, status=status.HTTP_404_NOT_FOUND)

    period = request.query_params.get('period', 'month')
    now = timezone.now()

    if period == 'week':
        start_date = now - timedelta(days=7)
    elif period == 'month':
        start_date = now - timedelta(days=30)
    else:
        start_date = None

    tasks_qs = delivery_models.DeliveryTask.objects.filter(
        driver=driver, dl_task_publish=True,
    ).exclude(order__order_status='cancelled')
    if start_date:
        tasks_qs = tasks_qs.filter(dl_task_date__gte=start_date.date())

    total = tasks_qs.count()
    completed = tasks_qs.filter(dl_task_status='delivered').count()
    failed = tasks_qs.filter(dl_task_status='failed').count()
    success_rate = round((completed / total) * 100, 1) if total > 0 else 0.0

    earnings_qs = fleet_models.DriverTransaction.objects.filter(
        driver=driver, transaction_type='earning',
    )
    if start_date:
        earnings_qs = earnings_qs.filter(created_at__gte=start_date)
    earnings_total = earnings_qs.aggregate(total=Sum('amount'))['total'] or 0

    pending_settlement = fleet_models.DriverSettlement.objects.filter(
        driver=driver, status='pending',
    ).aggregate(total=Sum('net_amount'))['total'] or 0

    return Response({
        'period': period,
        'total_deliveries': total,
        'completed_deliveries': completed,
        'failed_deliveries': failed,
        'success_rate': success_rate,
        'customer_rating': driver.driver_rating,
        'rating_count': driver.driver_rating_count,
        'earnings_this_period': str(earnings_total),
        'pending_earnings': str(driver.pending_earnings),
        'pending_settlement_amount': str(pending_settlement),
        'total_lifetime_earnings': str(driver.total_earnings),
    }, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([AllowAny])
def driver_app_config(request):
    """App configuration for the Flutter driver app — public, no auth required.

    Flutter checks this on every launch to gate outdated app versions
    and display announcement banners.
    """
    from django.conf import settings as django_settings

    min_version = getattr(django_settings, 'DRIVER_APP_MIN_VERSION', '1.0.0')
    latest_version = getattr(django_settings, 'DRIVER_APP_LATEST_VERSION', '1.0.0')
    force_update = getattr(django_settings, 'DRIVER_APP_FORCE_UPDATE', False)

    return Response({
        'min_app_version': min_version,
        'latest_app_version': latest_version,
        'force_update': force_update,
        'store_url_android': 'https://play.google.com/store/apps/details?id=com.ezzydelivery.driver',
        'store_url_ios': 'https://apps.apple.com/app/ezzydelivery-driver/id0000000000',
        'announcements': [],
        'features': {
            'bulk_cod_submit': True,
            'barcode_scan': True,
            'signature_capture': True,
            'photo_proof': True,
            'hub_batches': True,
        },
        'support_whatsapp': getattr(django_settings, 'DRIVER_SUPPORT_WHATSAPP', ''),
        'support_email': getattr(django_settings, 'DRIVER_SUPPORT_EMAIL', 'support@ezzydelivery.qa'),
    }, status=status.HTTP_200_OK)


# ==================== CLIENT DOCUMENTATION VIEWS ====================

def docs_index(request):
    return render(request, 'ezzy_api/docs/index.html')

def docs_getting_started(request):
    return render(request, 'ezzy_api/docs/getting-started.html')

def docs_authentication(request):
    return render(request, 'ezzy_api/docs/authentication.html')

def docs_shopify(request):
    return render(request, 'ezzy_api/docs/shopify.html')

def docs_woocommerce(request):
    return render(request, 'ezzy_api/docs/woocommerce.html')

def docs_tiktok(request):
    return render(request, 'ezzy_api/docs/tiktok.html')

def docs_api_reference(request):
    return render(request, 'ezzy_api/docs/api-reference.html')

def docs_webhooks(request):
    return render(request, 'ezzy_api/docs/webhooks.html')

def docs_errors(request):
    return render(request, 'ezzy_api/docs/errors.html')

def docs_examples(request):
    return render(request, 'ezzy_api/docs/examples.html')

def docs_faq(request):
    return render(request, 'ezzy_api/docs/faq.html')
