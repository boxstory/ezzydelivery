from django.urls import path
from webpages import views as webpages_views
from workforce import views as workforce_views
from workforce import dispatch_views
from delivery import views as delivery_views
from orders import views as orders_views
from core import views as core_views

app_name = 'workforce'
urlpatterns = [
    path('dashboard/', workforce_views.wf_dashboard, name='wf_dashboard'),

    # Sellers section urls -------------------------------------------------------------------
    path('sellers/', workforce_views.sellers_list, name='sellers_list'),
    path('sellers/pending/', workforce_views.sellers_pending, name='sellers_pending'),
    path('sellers/active/', workforce_views.sellers_active, name='sellers_active'),
    path('sellers/inactive/', workforce_views.sellers_inactive, name='sellers_inactive'),
    path('sellers/<int:business_id>/', workforce_views.seller_detail, name='seller_detail'),

    # Drivers section urls -------------------------------------------------------------------
    path('drivers/', workforce_views.drivers_list, name='drivers_list'),
    path('drivers/pending/', workforce_views.drivers_pending, name='drivers_pending'),
    path('drivers/active/', workforce_views.drivers_active, name='drivers_active'),
    path('drivers/inactive/', workforce_views.drivers_inactive, name='drivers_inactive'),
    path('drivers/<int:driver_id>/', workforce_views.driver_detail, name='driver_detail'),

    #Orders sections urls -------------------------------------------------------------------
    path('orders/add/', workforce_views.add_order, name='wf_orders_add'),
    # Bulk import uses shared views from orders app
    path('orders/bulk-import/', orders_views.bulk_import_orders, name='wf_orders_bulk_import'),
    path('orders/bulk-import/preview/', orders_views.bulk_import_preview, name='wf_orders_bulk_preview'),
    path('orders/bulk-import/save/', orders_views.bulk_import_save, name='wf_orders_bulk_save'),
    path('orders/api-guide/', workforce_views.orders_api_guide, name='wf_orders_api_guide'),
    path('orders/pickup-locations/<int:business_id>/', workforce_views.get_pickup_locations, name='get_pickup_locations'),
    path('orders/all/', workforce_views.all_orders, name='wf_orders_all'),
    path('orders/by-seller/', workforce_views.orders_by_seller, name='wf_orders_by_seller'),
    path('orders/to_publish/', workforce_views.orders_to_publish, name='wf_orders_to_publish'),
    path('orders/published/', workforce_views.orders_published, name='wf_orders_published'),
    path('orders/pending-verification/', workforce_views.orders_pending_verification, name='orders_pending_verification'),
    path('orders/<int:order_id>/verify-address/', workforce_views.verify_order_address, name='verify_order_address'),
    path('orders/<int:order_id>/verify/', workforce_views.verify_order, name='verify_order'),
    path('orders/submit_to_task/<int:order_id>/', workforce_views.submit_to_task, name='submit_to_task'),

    # AJAX endpoints for orders
    path('orders/<int:order_id>/publish/', workforce_views.publish_order_to_delivery, name='publish_order_to_delivery'),
    path('orders/<int:order_id>/update-status/', workforce_views.update_order_status, name='update_order_status'),
    path('orders/<int:order_id>/add-comment/', workforce_views.add_order_comment, name='add_order_comment'),



    #Deliveries sections urls ----------------------------------------------------------------
    path('tasks/dl_list_all/', workforce_views.dl_list_all, name='dl_list_all'),
    path('tasks/dl_list_unpublished/', workforce_views.dl_list_ready_to_published_to_dms, name='dl_list_ready_to_published_to_dms'),
    path('tasks/dl_list_published/', workforce_views.dl_list_published_to_dms, name='dl_list_published_to_dms'),
    path('tasks/dl_list_incompleted/', workforce_views.dl_list_incompleted_details, name='dl_list_incompleted_details'),

    # Delivery task detail view
    path('delivery-task/<int:task_id>/', workforce_views.delivery_task_detail, name='delivery_task_detail'),

    # AJAX endpoints for delivery tasks
    path('delivery-task/<int:task_id>/publish-dms/', workforce_views.publish_task_to_dms, name='publish_task_to_dms'),
    path('delivery-task/<int:task_id>/publish-driver-app/', workforce_views.publish_task_to_driver_app, name='publish_task_to_driver_app'),
    path('delivery-task/<int:task_id>/assign-driver/', workforce_views.assign_driver_to_task, name='assign_driver_to_task'),
    path('delivery-task/<int:task_id>/update-status/', workforce_views.update_task_status, name='update_task_status'),

    # User Verification URLs
    path('verification/users/', workforce_views.user_verification_list, name='user_verification_list'),
    path('verification/<int:profile_id>/update-status/', workforce_views.update_verification_status, name='update_verification_status'),

    # Additional Orders URLs
    path('orders/dms-updated/', workforce_views.orders_dms_updated, name='wf_orders_dms_updated'),
    path('orders/match-dms/', workforce_views.match_dms_task, name='match_dms_task'),
    path('orders/reported/', workforce_views.orders_reported, name='wf_orders_reported'),

    # Additional Tasks URLs
    path('tasks/followup-list/', workforce_views.tasks_followup_list, name='tasks_followup_list'),
    path('tasks/dms-updated/', workforce_views.tasks_dms_updated, name='tasks_dms_updated'),
    path('tasks/reported/', workforce_views.tasks_reported, name='tasks_reported'),

    #DMS sections urls -----------------------------------------------------------------------
    path('dms/publish-order/', workforce_views.dms_publish_order, name='dms_publish_order'),
    path('dms/drivers/', workforce_views.dms_drivers_list, name='dms_drivers_list'),
    path('dms/orders/', workforce_views.dms_orders_list, name='dms_orders_list'),
    path('dms/analytics/', workforce_views.dms_analytics, name='dms_analytics'),
    path('dms/sync-monitor/', workforce_views.dms_sync_monitor, name='dms_sync_monitor'),

    # Fleet Accounts URLs
    path('fleet/cod-in-hand/', workforce_views.fleet_cod_in_hand, name='fleet_cod_in_hand'),
    path('fleet/drivers-earnings/', workforce_views.fleet_drivers_earnings, name='fleet_drivers_earnings'),
    path('fleet/transactions/', workforce_views.fleet_transactions, name='fleet_transactions'),

    #Documents sections urls -----------------------------------------------------------------
    path('documents/driver-ids/', workforce_views.driver_documents_list, name='driver_documents_list'),
    path('documents/driver-ids/<int:document_id>/', workforce_views.driver_document_detail, name='driver_document_detail'),
    path('documents/vehicles/', workforce_views.vehicle_documents_list, name='vehicle_documents_list'),
    path('documents/vehicles/<int:driver_id>/', workforce_views.vehicle_document_detail, name='vehicle_document_detail'),
    path('documents/stores/', workforce_views.store_documents_list, name='store_documents_list'),
    path('documents/stores/<int:business_id>/', workforce_views.store_document_detail, name='store_document_detail'),
    path('documents/business-licenses/', workforce_views.business_licenses_list, name='business_licenses_list'),
    path('documents/business-licenses/<int:business_id>/', workforce_views.business_license_detail, name='business_license_detail'),

    # Inventory URLs
    path('inventory/reports/', workforce_views.inventory_reports, name='inventory_reports'),
    path('inventory/restock-list/', workforce_views.inventory_restock_list, name='inventory_restock_list'),

    # Quick Links URLs
    path('reports/', workforce_views.staff_reports, name='staff_reports'),
    path('contacts/', workforce_views.staff_contacts, name='staff_contacts'),

    # Workflow guide
    path('workflow-guide/', workforce_views.workflow_guide, name='workflow_guide'),

    # Fulfillment Service & Purchase Orders
    path('suppliers/', workforce_views.suppliers_list, name='suppliers_list'),
    path('purchase-orders/', workforce_views.fulfilled_orders_list, name='fulfilled_orders_list'),

    # ==========================================
    # DISPATCH & BATCHING SECTION
    # ==========================================
    path('dispatch/', dispatch_views.dispatch_dashboard, name='dispatch_dashboard'),
    path('dispatch/batches/', dispatch_views.batch_list, name='dispatch_batch_list'),
    path('dispatch/batches/<int:batch_id>/', dispatch_views.batch_detail, name='dispatch_batch_detail'),
    path('dispatch/batches/<int:batch_id>/release/', dispatch_views.manual_release_batch, name='dispatch_release_batch'),
    path('dispatch/batches/<int:batch_id>/cancel/', dispatch_views.cancel_batch, name='dispatch_cancel_batch'),

    # Shift Management
    path('dispatch/shifts/', dispatch_views.shift_list, name='dispatch_shift_list'),
    path('dispatch/shifts/create/', dispatch_views.shift_create, name='dispatch_shift_create'),
    path('dispatch/shifts/<int:shift_id>/', dispatch_views.shift_detail, name='dispatch_shift_detail'),
    path('dispatch/shifts/<int:shift_id>/edit/', dispatch_views.shift_edit, name='dispatch_shift_edit'),

    # KPI Dashboard
    path('dispatch/kpis/', dispatch_views.kpi_dashboard, name='dispatch_kpi_dashboard'),
    path('dispatch/kpis/rider/<int:rider_id>/', dispatch_views.rider_kpi_detail, name='dispatch_rider_kpi'),

    # Config Management
    path('dispatch/config/', dispatch_views.config_list, name='dispatch_config_list'),
    path('dispatch/config/<int:location_id>/', dispatch_views.config_edit, name='dispatch_config_edit'),

    # HTMX Partials
    path('dispatch/partials/batch-monitor/', dispatch_views.batch_monitor_partial, name='dispatch_batch_monitor_partial'),
    path('dispatch/partials/shift-status/', dispatch_views.shift_status_partial, name='dispatch_shift_status_partial'),

]
