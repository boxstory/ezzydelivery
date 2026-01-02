"""
Dispatch URL Configuration.

Includes:
- API endpoints for rider app
- Store portal views (separate from workforce dashboard)
"""
from django.urls import path
from . import views

app_name = 'dispatch'

urlpatterns = [
    # ========================================
    # RIDER API ENDPOINTS
    # ========================================
    # Active batches for rider
    path('api/rider/batches/', views.rider_active_batches, name='api_rider_batches'),
    path('api/rider/batches/<int:batch_id>/', views.rider_batch_detail, name='api_rider_batch_detail'),
    path('api/rider/batches/<int:batch_id>/start/', views.rider_start_batch, name='api_rider_start_batch'),
    path('api/rider/batches/<int:batch_id>/complete/', views.rider_complete_batch, name='api_rider_complete_batch'),

    # Shift endpoints
    path('api/rider/shift/', views.rider_active_shift, name='api_rider_shift'),
    path('api/rider/shift/<int:shift_id>/clock-in/', views.rider_clock_in, name='api_rider_clock_in'),
    path('api/rider/shift/<int:shift_id>/clock-out/', views.rider_clock_out, name='api_rider_clock_out'),
    path('api/rider/shifts/', views.rider_shifts_list, name='api_rider_shifts'),

    # ========================================
    # STORE PORTAL VIEWS
    # ========================================
    path('store/', views.store_dashboard, name='store_dashboard'),
    path('store/prep-queue/', views.store_prep_queue, name='store_prep_queue'),
    path('store/riders/', views.store_riders, name='store_riders'),
    path('store/batches/', views.store_batches, name='store_batches'),

    # HTMX partials for store portal
    path('store/partials/batch-list/', views.store_batch_list_partial, name='store_batch_list_partial'),
    path('store/partials/prep-queue/', views.store_prep_queue_partial, name='store_prep_queue_partial'),
]
