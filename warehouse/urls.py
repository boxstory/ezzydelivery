from django.urls import path
from warehouse import views as warehouse_views

app_name = 'warehouse'

urlpatterns = [
    # Dashboard
    path('', warehouse_views.dashboard, name='dashboard'),

    # Inventory
    path('inventory/', warehouse_views.inventory_list, name='inventory_list'),
    path('inventory/<int:stock_id>/detail/', warehouse_views.stock_level_detail_modal, name='stock_level_detail_modal'),
    path('products/add/', warehouse_views.staff_product_add, name='staff_product_add'),
    path('products/<int:product_id>/edit/', warehouse_views.staff_product_edit, name='staff_product_edit'),
    path('inventory/<int:product_id>/', warehouse_views.stock_card, name='stock_card'),
    path('transactions/', warehouse_views.transaction_list, name='transaction_list'),

    # Receiving
    path('receive/', warehouse_views.receive_stock, name='receive_stock'),
    path('receive/confirm/', warehouse_views.confirm_receive, name='confirm_receive'),

    # Stock adjustment
    path('adjust/', warehouse_views.stock_adjust, name='stock_adjust'),

    # Picking
    path('pick-lists/', warehouse_views.pick_list_list, name='pick_list_list'),
    path('pick-lists/bulk-drop/', warehouse_views.bulk_drop_pick_lists, name='bulk_drop_pick_lists'),
    path('pick-lists/create/', warehouse_views.create_pick_list, name='create_pick_list'),
    path('pick-lists/<int:pk>/', warehouse_views.pick_list_detail, name='pick_list_detail'),
    path('pick-lists/<int:pk>/assign/', warehouse_views.assign_pick_list, name='assign_pick_list'),
    path('pick-lists/<int:pk>/start/', warehouse_views.start_pick_list, name='start_pick_list'),
    path('pick-lists/<int:pk>/items/<int:item_id>/pick/', warehouse_views.pick_item, name='pick_item'),
    path('pick-lists/<int:pk>/items/<int:item_id>/unpick/', warehouse_views.unpick_item, name='unpick_item'),

    # Packing
    path('pick-lists/<int:pk>/pack/', warehouse_views.pack_station, name='pack_station'),
    path('pick-lists/<int:pk>/pack-order/<int:order_id>/', warehouse_views.pack_order, name='pack_order'),

    # Dispatch
    path('dispatch/', warehouse_views.dispatch_queue, name='dispatch_queue'),
    path('dispatch/create/', warehouse_views.dispatch_create, name='dispatch_create'),
    path('dispatch/<int:pk>/', warehouse_views.dispatch_detail, name='dispatch_detail'),
    path('dispatch/<int:pk>/handover/<int:item_id>/', warehouse_views.dispatch_handover_item, name='dispatch_handover_item'),
    path('dispatch/<int:pk>/confirm/', warehouse_views.dispatch_confirm, name='dispatch_confirm'),

    # Customer Returns / RMA
    path('rma/', warehouse_views.rma_list, name='rma_list'),
    path('rma/create/<int:order_id>/', warehouse_views.rma_create, name='rma_create'),
    path('rma/<int:pk>/', warehouse_views.rma_detail, name='rma_detail'),
    path('rma/<int:pk>/receive/', warehouse_views.rma_receive, name='rma_receive'),
    path('rma/<int:pk>/inspect/<int:item_id>/', warehouse_views.rma_inspect_item, name='rma_inspect_item'),

    # Put-Away Tasks
    path('put-away/', warehouse_views.put_away_list, name='put_away_list'),
    path('put-away/<int:pk>/', warehouse_views.put_away_detail, name='put_away_detail'),
    path('put-away/<int:pk>/assign/', warehouse_views.put_away_assign, name='put_away_assign'),
    path('put-away/<int:pk>/items/<int:item_id>/confirm/', warehouse_views.put_away_confirm_item, name='put_away_confirm_item'),

    # Return Tasks (cancel-after-pickup)
    path('returns/', warehouse_views.return_task_list, name='return_task_list'),
    path('returns/<int:pk>/', warehouse_views.return_task_detail, name='return_task_detail'),
    path('returns/<int:pk>/return-item/<int:item_id>/', warehouse_views.return_item, name='return_item'),

    # Cycle Counting
    path('cycle-counts/', warehouse_views.cycle_count_list, name='cycle_count_list'),
    path('cycle-counts/create/', warehouse_views.create_cycle_count, name='create_cycle_count'),
    path('cycle-counts/<int:pk>/', warehouse_views.cycle_count_detail, name='cycle_count_detail'),
    path('cycle-counts/<int:pk>/start/', warehouse_views.start_cycle_count, name='start_cycle_count'),
    path('cycle-counts/<int:pk>/items/<int:item_id>/count/', warehouse_views.count_item, name='count_item'),
    path('cycle-counts/<int:pk>/submit/', warehouse_views.submit_cycle_count, name='submit_cycle_count'),
    path('cycle-counts/<int:pk>/approve/', warehouse_views.approve_cycle_count, name='approve_cycle_count'),

    # Alerts
    path('alerts/', warehouse_views.low_stock_alerts, name='low_stock_alerts'),
    path('alerts/<int:pk>/acknowledge/', warehouse_views.acknowledge_alert, name='acknowledge_alert'),

    # Warehouses & Locations
    path('warehouses/', warehouse_views.warehouse_list, name='warehouse_list'),
    path('warehouses/add/', warehouse_views.warehouse_add, name='warehouse_add'),
    path('warehouses/<int:pk>/', warehouse_views.warehouse_detail, name='warehouse_detail'),
    path('warehouses/<int:pk>/edit/', warehouse_views.warehouse_edit, name='warehouse_edit'),
    path('warehouses/<int:pk>/capacity/configure/', warehouse_views.warehouse_capacity_configure, name='warehouse_capacity_configure'),
    path('warehouses/<int:pk>/capacity/preview/', warehouse_views.warehouse_capacity_preview, name='warehouse_capacity_preview'),
    path('warehouses/<int:pk>/capacity/generate/', warehouse_views.warehouse_generate_locations, name='warehouse_generate_locations'),

    # Warehouse Pickup/Dispatch Locations
    path('warehouse-locations/', warehouse_views.warehouse_location_list, name='warehouse_location_list'),
    path('warehouse-locations/add/', warehouse_views.warehouse_location_add, name='warehouse_location_add'),

    # Storage Locations (for inventory)
    path('locations/', warehouse_views.location_list, name='location_list'),
    path('locations/add/', warehouse_views.location_add, name='location_add'),
    path('locations/<int:pk>/edit/', warehouse_views.location_edit, name='location_edit'),
    path('locations/<int:pk>/delete/', warehouse_views.location_delete, name='location_delete'),

    # Seller-Warehouse Links
    path('seller-warehouse-links/', warehouse_views.seller_warehouse_links, name='seller_warehouse_links'),
    path('seller-warehouse-links/add/', warehouse_views.seller_warehouse_link_add, name='seller_warehouse_link_add'),
    path('seller-warehouse-links/<int:pk>/', warehouse_views.seller_warehouse_link_detail, name='seller_warehouse_link_detail'),
    path('seller-warehouse-links/<int:pk>/edit/', warehouse_views.seller_warehouse_link_edit, name='seller_warehouse_link_edit'),
    path('seller-warehouse-links/<int:pk>/delete/', warehouse_views.seller_warehouse_link_delete, name='seller_warehouse_link_delete'),

    # API Endpoints
    path('api/warehouses/<int:warehouse_id>/locations/', warehouse_views.api_warehouse_locations, name='api_warehouse_locations'),
    path('api/warehouses/<int:warehouse_id>/storage-locations/', warehouse_views.api_storage_locations, name='api_storage_locations'),
    path('api/business/<int:business_id>/products/', warehouse_views.api_business_products, name='api_business_products'),
    path('api/inbound-request/<int:request_id>/items/', warehouse_views.api_inbound_request_items, name='api_inbound_request_items'),
    path('api/stock-levels/', warehouse_views.api_stock_levels, name='api_stock_levels'),
]
