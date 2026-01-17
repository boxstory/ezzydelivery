from django.urls import path
from warehouse import views as warehouse_views

app_name = 'warehouse'

urlpatterns = [
    # Dashboard
    path('', warehouse_views.dashboard, name='dashboard'),

    # Inventory
    path('inventory/', warehouse_views.inventory_list, name='inventory_list'),
    path('inventory/<int:product_id>/', warehouse_views.stock_card, name='stock_card'),
    path('transactions/', warehouse_views.transaction_list, name='transaction_list'),

    # Receiving
    path('receive/', warehouse_views.receive_stock, name='receive_stock'),
    path('receive/confirm/', warehouse_views.confirm_receive, name='confirm_receive'),

    # Picking
    path('pick-lists/', warehouse_views.pick_list_list, name='pick_list_list'),
    path('pick-lists/create/', warehouse_views.create_pick_list, name='create_pick_list'),
    path('pick-lists/<int:pk>/', warehouse_views.pick_list_detail, name='pick_list_detail'),
    path('pick-lists/<int:pk>/assign/', warehouse_views.assign_pick_list, name='assign_pick_list'),

    # Cycle Counting
    path('cycle-counts/', warehouse_views.cycle_count_list, name='cycle_count_list'),
    path('cycle-counts/create/', warehouse_views.create_cycle_count, name='create_cycle_count'),
    path('cycle-counts/<int:pk>/', warehouse_views.cycle_count_detail, name='cycle_count_detail'),

    # Alerts
    path('alerts/', warehouse_views.low_stock_alerts, name='low_stock_alerts'),
    path('alerts/<int:pk>/acknowledge/', warehouse_views.acknowledge_alert, name='acknowledge_alert'),

    # Warehouses & Locations
    path('warehouses/', warehouse_views.warehouse_list, name='warehouse_list'),
    path('warehouses/add/', warehouse_views.warehouse_add, name='warehouse_add'),
    path('warehouses/<int:pk>/', warehouse_views.warehouse_detail, name='warehouse_detail'),
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
]
