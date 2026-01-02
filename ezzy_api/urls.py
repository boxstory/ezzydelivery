from django.urls import path, include
from ezzy_api import views as ezzy_api_views

#path('api/', include('ezzy_api.urls'))

app_name = 'ezzy_api'
urlpatterns = [
    # Existing endpoints
    path('orderlist/', ezzy_api_views.OrderList.as_view(), name='order_list_api'),
    path('carrierslist/shipday/', ezzy_api_views.shipday_feet_list, name='shipday_feet_list'),
    path('orderlist/shipday/', ezzy_api_views.shipday_order_list, name='shipday_order_list'),
    
    # ==================== DRIVER APP APIs ====================
    path('driver/login/', ezzy_api_views.driver_login, name='driver_login'),
    path('driver/profile/', ezzy_api_views.driver_profile, name='driver_profile'),
    path('driver/tasks/', ezzy_api_views.driver_tasks, name='driver_tasks'),
    path('driver/tasks/<int:task_id>/', ezzy_api_views.driver_task_detail, name='driver_task_detail'),
    path('driver/tasks/<int:task_id>/accept/', ezzy_api_views.driver_accept_task, name='driver_accept_task'),
    path('driver/tasks/<int:task_id>/reject/', ezzy_api_views.driver_reject_task, name='driver_reject_task'),
    path('driver/tasks/<int:task_id>/status/', ezzy_api_views.driver_update_task_status, name='driver_update_task_status'),
    path('driver/tasks/<int:task_id>/complete/', ezzy_api_views.driver_complete_task, name='driver_complete_task'),
    path('driver/tasks/<int:task_id>/documents/', ezzy_api_views.driver_task_documents, name='driver_task_documents'),
    path('driver/tasks/<int:task_id>/documents/upload/', ezzy_api_views.driver_upload_task_document, name='driver_upload_task_document'),
    path('driver/location/', ezzy_api_views.driver_update_location, name='driver_update_location'),
    path('driver/statistics/', ezzy_api_views.driver_statistics, name='driver_statistics'),
    
    # ==================== DMS APIs ====================
    path('dms/orders/', ezzy_api_views.dms_orders_list, name='dms_orders_list'),
    path('dms/orders/<int:order_id>/', ezzy_api_views.dms_order_detail, name='dms_order_detail'),
    path('dms/orders/<int:order_id>/documents/', ezzy_api_views.dms_order_documents, name='dms_order_documents'),
    path('dms/orders/<int:order_id>/documents/upload/', ezzy_api_views.dms_upload_order_document, name='dms_upload_order_document'),
    path('dms/tasks/', ezzy_api_views.dms_tasks_list, name='dms_tasks_list'),
    path('dms/tasks/<int:task_id>/', ezzy_api_views.dms_task_detail, name='dms_task_detail'),
    path('dms/tasks/<int:task_id>/documents/', ezzy_api_views.dms_task_documents, name='dms_task_documents'),
    path('dms/tasks/<int:task_id>/documents/upload/', ezzy_api_views.dms_upload_task_document, name='dms_upload_task_document'),
    path('dms/tasks/assign/', ezzy_api_views.dms_assign_task, name='dms_assign_task'),
    path('dms/tasks/status/', ezzy_api_views.dms_update_task_status, name='dms_update_task_status'),
    path('dms/drivers/', ezzy_api_views.dms_drivers_list, name='dms_drivers_list'),
    path('dms/drivers/<int:driver_id>/', ezzy_api_views.dms_driver_detail, name='dms_driver_detail'),
    path('dms/analytics/', ezzy_api_views.dms_analytics, name='dms_analytics'),
    
    # ==================== API KEY MANAGEMENT APIs ====================
    path('api-keys/', ezzy_api_views.list_api_keys, name='list_api_keys'),
    path('api-keys/create/', ezzy_api_views.create_api_key, name='create_api_key'),
    path('api-keys/<int:api_key_id>/', ezzy_api_views.manage_api_key, name='manage_api_key'),
    
    # ==================== E-COMMERCE INTEGRATION APIs ====================
    path('integrations/', ezzy_api_views.list_integrations, name='list_integrations'),
    path('integrations/shopify/import/', ezzy_api_views.import_shopify_orders, name='import_shopify_orders'),
    path('integrations/woocommerce/import/', ezzy_api_views.import_woocommerce_orders, name='import_woocommerce_orders'),
    
    # ==================== WEBHOOK APIs ====================
    # Webhook receivers (from driver apps)
    path('webhooks/task/status/', ezzy_api_views.webhook_receive_task_status_update, name='webhook_receive_task_status_update'),
    path('webhooks/task/complete/', ezzy_api_views.webhook_receive_task_completion, name='webhook_receive_task_completion'),
    path('webhooks/driver/location/', ezzy_api_views.webhook_receive_driver_location, name='webhook_receive_driver_location'),
    
    # Webhook management
    path('webhooks/endpoints/', ezzy_api_views.list_webhook_endpoints, name='list_webhook_endpoints'),
    path('webhooks/endpoints/create/', ezzy_api_views.create_webhook_endpoint, name='create_webhook_endpoint'),
    path('webhooks/deliveries/', ezzy_api_views.list_webhook_deliveries, name='list_webhook_deliveries'),
    
    # ==================== ORDER VERIFICATION APIs ====================
    path('orders/pending-verification/', ezzy_api_views.orders_pending_verification, name='orders_pending_verification'),
    path('orders/<int:order_id>/verify-address/', ezzy_api_views.verify_order_address, name='verify_order_address'),
    path('orders/<int:order_id>/verify/', ezzy_api_views.verify_order, name='verify_order'),
    path('orders/<int:order_id>/reject/', ezzy_api_views.reject_order, name='reject_order'),
    path('tasks/<int:task_id>/push-to-dms/', ezzy_api_views.push_task_to_dms_api, name='push_task_to_dms_api'),

    # ==================== BUSINESS APIs ====================
    path('business/dashboard/', ezzy_api_views.business_dashboard_stats, name='business_dashboard_stats'),
    path('business/orders/', ezzy_api_views.business_orders_api, name='business_orders_api'),
    path('business/orders/<int:order_id>/', ezzy_api_views.business_order_detail_api, name='business_order_detail_api'),
    path('business/clients/', ezzy_api_views.business_clients_api, name='business_clients_api'),
    path('business/tasks/', ezzy_api_views.business_tasks_api, name='business_tasks_api'),
    path('business/pickup-locations/', ezzy_api_views.business_pickup_locations_api, name='business_pickup_locations_api'),

    # ==================== API TESTING UI ====================
    path('tester/', ezzy_api_views.api_tester_view, name='api_tester'),

    # ==================== QNAS PROXY APIs ====================
    # Proxy endpoints for QNAS (Qatar National Address System)
    # These forward browser cookies to bypass Cloudflare protection
    path('qnas/get-zones/', ezzy_api_views.qnas_get_zones, name='qnas_get_zones'),
    path('qnas/get-streets/', ezzy_api_views.qnas_get_streets, name='qnas_get_streets'),
    path('qnas/get-buildings/', ezzy_api_views.qnas_get_buildings, name='qnas_get_buildings'),
    path('qnas/search/', ezzy_api_views.qnas_search_address, name='qnas_search_address'),
    path('qnas/address-details/', ezzy_api_views.qnas_get_address_details, name='qnas_get_address_details'),
    path('qnas/geocode/', ezzy_api_views.qnas_geocode, name='qnas_geocode'),
    path('qnas/get-zone-polygon/<str:zone_number>/', ezzy_api_views.qnas_get_zone_polygon, name='qnas_get_zone_polygon'),
]