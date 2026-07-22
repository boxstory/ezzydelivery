from django.urls import path, include
from ezzy_api import views as ezzy_api_views

#path('api/', include('ezzy_api.urls'))

app_name = 'ezzy_api'
urlpatterns = [
    # ==================== CLIENT DOCUMENTATION ====================
    path('docs/', ezzy_api_views.docs_index, name='docs_index'),
    path('docs/getting-started/', ezzy_api_views.docs_getting_started, name='docs_getting_started'),
    path('docs/authentication/', ezzy_api_views.docs_authentication, name='docs_authentication'),
    path('docs/shopify/', ezzy_api_views.docs_shopify, name='docs_shopify'),
    path('docs/woocommerce/', ezzy_api_views.docs_woocommerce, name='docs_woocommerce'),
    path('docs/tiktok/', ezzy_api_views.docs_tiktok, name='docs_tiktok'),
    path('docs/api-reference/', ezzy_api_views.docs_api_reference, name='docs_api_reference'),
    path('docs/webhooks/', ezzy_api_views.docs_webhooks, name='docs_webhooks'),
    path('docs/errors/', ezzy_api_views.docs_errors, name='docs_errors'),
    path('docs/examples/', ezzy_api_views.docs_examples, name='docs_examples'),
    path('docs/faq/', ezzy_api_views.docs_faq, name='docs_faq'),

    # Existing endpoints
    path('orderlist/', ezzy_api_views.OrderList.as_view(), name='order_list_api'),

    # ==================== DRIVER APP APIs ====================
    path('driver/login/', ezzy_api_views.driver_login, name='driver_login'),
    path('driver/logout/', ezzy_api_views.driver_logout, name='driver_logout'),
    path('driver/profile/', ezzy_api_views.driver_profile, name='driver_profile'),
    path('driver/status/', ezzy_api_views.driver_set_status, name='driver_set_status'),
    path('driver/work-preference/', ezzy_api_views.driver_set_work_preference, name='driver_set_work_preference'),
    path('driver/dashboard/', ezzy_api_views.driver_dashboard, name='driver_dashboard'),
    path('driver/tasks/', ezzy_api_views.driver_tasks, name='driver_tasks'),
    path('driver/tasks/<int:task_id>/', ezzy_api_views.driver_task_detail, name='driver_task_detail'),
    path('driver/tasks/<int:task_id>/accept/', ezzy_api_views.driver_accept_task, name='driver_accept_task'),
    path('driver/tasks/<int:task_id>/reject/', ezzy_api_views.driver_reject_task, name='driver_reject_task'),
    path('driver/tasks/<int:task_id>/status/', ezzy_api_views.driver_update_task_status, name='driver_update_task_status'),
    path('driver/tasks/<int:task_id>/complete/', ezzy_api_views.driver_complete_task, name='driver_complete_task'),
    path('driver/tasks/<int:task_id>/documents/', ezzy_api_views.driver_task_documents, name='driver_task_documents'),
    path('driver/tasks/<int:task_id>/documents/upload/', ezzy_api_views.driver_upload_task_document, name='driver_upload_task_document'),
    path('driver/tasks/<int:task_id>/report-issue/', ezzy_api_views.driver_report_task_issue, name='driver_report_task_issue'),
    path('driver/tasks/<int:task_id>/items/', ezzy_api_views.driver_task_items, name='driver_task_items'),
    path('driver/order/lookup/', ezzy_api_views.driver_order_lookup, name='driver_order_lookup'),
    path('driver/pickup-locations/', ezzy_api_views.driver_pickup_locations, name='driver_pickup_locations'),
    path('driver/documents/upload/', ezzy_api_views.driver_document_upload, name='driver_document_upload'),
    path('driver/performance-metrics/', ezzy_api_views.driver_performance_metrics, name='driver_performance_metrics'),
    path('driver/app-config/', ezzy_api_views.driver_app_config, name='driver_app_config'),
    path('driver/location/', ezzy_api_views.driver_update_location, name='driver_update_location'),
    path('driver/<int:driver_id>/location/', ezzy_api_views.driver_latest_location, name='driver_latest_location'),
    path('driver/statistics/', ezzy_api_views.driver_statistics, name='driver_statistics'),

    # COD
    path('driver/cod/submit/', ezzy_api_views.driver_cod_submit, name='driver_cod_submit'),
    path('driver/cod/submit-bulk/', ezzy_api_views.driver_cod_submit_bulk, name='driver_cod_submit_bulk'),
    path('driver/cod/pending/', ezzy_api_views.driver_cod_pending, name='driver_cod_pending'),

    # Earnings / Transactions
    path('driver/transactions/', ezzy_api_views.driver_transactions, name='driver_transactions'),
    path('driver/transactions/<str:code>/', ezzy_api_views.driver_transaction_detail, name='driver_transaction_detail'),

    # Settlements
    path('driver/settlements/', ezzy_api_views.driver_settlements, name='driver_settlements'),
    path('driver/settlements/<str:code>/', ezzy_api_views.driver_settlement_detail, name='driver_settlement_detail'),

    # Notifications
    path('driver/notifications/', ezzy_api_views.driver_notifications, name='driver_notifications'),
    path('driver/notifications/mark-read/', ezzy_api_views.driver_notifications_mark_read, name='driver_notifications_mark_read'),
    path('driver/device-token/', ezzy_api_views.driver_device_token, name='driver_device_token'),

    # Hub pickup batch endpoints (driver app)
    path('driver/hub-batches/', ezzy_api_views.driver_hub_batches, name='driver_hub_batches'),
    path('driver/hub-batches/<int:batch_id>/', ezzy_api_views.driver_hub_batch_detail, name='driver_hub_batch_detail'),
    path('driver/hub-batches/<int:batch_id>/accept/', ezzy_api_views.driver_hub_batch_accept, name='driver_hub_batch_accept'),
    path('driver/hub-batches/<int:batch_id>/status/', ezzy_api_views.driver_hub_batch_status, name='driver_hub_batch_status'),
    
    # ==================== API KEY MANAGEMENT APIs ====================
    path('api-keys/', ezzy_api_views.list_api_keys, name='list_api_keys'),
    path('api-keys/create/', ezzy_api_views.create_api_key, name='create_api_key'),
    path('api-keys/<int:api_key_id>/', ezzy_api_views.manage_api_key, name='manage_api_key'),
    
    # ==================== E-COMMERCE INTEGRATION APIs ====================
    path('integrations/', ezzy_api_views.list_integrations, name='list_integrations'),
    path('integrations/shopify/import/', ezzy_api_views.import_shopify_orders, name='import_shopify_orders'),
    path('integrations/woocommerce/import/', ezzy_api_views.import_woocommerce_orders, name='import_woocommerce_orders'),
    path('integrations/tiktokshop/import/', ezzy_api_views.import_tiktokshop_orders, name='import_tiktokshop_orders'),
    path('integrations/tiktokshop/test/', ezzy_api_views.test_tiktokshop_connection, name='test_tiktokshop_connection'),
    
    # ==================== WEBHOOK APIs ====================
    # Webhook receivers (from driver apps)
    path('webhooks/task/status/', ezzy_api_views.webhook_receive_task_status_update, name='webhook_receive_task_status_update'),
    path('webhooks/task/complete/', ezzy_api_views.webhook_receive_task_completion, name='webhook_receive_task_completion'),
    path('webhooks/driver/location/', ezzy_api_views.webhook_receive_driver_location, name='webhook_receive_driver_location'),
    
    # Inbound webhook (public — receives orders)
    path('webhooks/order/inbound/<str:webhook_key>/', ezzy_api_views.webhook_inbound_order, name='webhook_inbound_order'),

    # Webhook management
    path('webhooks/endpoints/', ezzy_api_views.list_webhook_endpoints, name='list_webhook_endpoints'),
    path('webhooks/endpoints/create/', ezzy_api_views.create_webhook_endpoint, name='create_webhook_endpoint'),
    path('webhooks/deliveries/', ezzy_api_views.list_webhook_deliveries, name='list_webhook_deliveries'),
    
    # ==================== ORDER VERIFICATION APIs ====================
    path('orders/pending-verification/', ezzy_api_views.orders_pending_verification, name='orders_pending_verification'),
    path('orders/<int:order_id>/verify-address/', ezzy_api_views.verify_order_address, name='verify_order_address'),
    path('orders/<int:order_id>/verify/', ezzy_api_views.verify_order, name='verify_order'),
    path('orders/<int:order_id>/reject/', ezzy_api_views.reject_order, name='reject_order'),

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
    # POST endpoint for coordinates (no query params in URL)
    path('qnas/coordinates/', ezzy_api_views.qnas_get_coordinates, name='qnas_get_coordinates'),
    # GET endpoint with path parameters (QNAS-style)
    path('qnas/location/<str:zone_number>/<str:street_number>/', ezzy_api_views.qnas_get_location, name='qnas_get_location'),
    path('qnas/location/<str:zone_number>/<str:street_number>/<str:building_number>/', ezzy_api_views.qnas_get_location, name='qnas_get_location_with_building'),
]