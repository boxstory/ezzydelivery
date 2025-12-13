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
    path('locations/', warehouse_views.location_list, name='location_list'),
    path('locations/add/', warehouse_views.location_add, name='location_add'),
]
