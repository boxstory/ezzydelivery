from django.urls import path
from warehouse import views

app_name = 'warehouse'

urlpatterns = [
    # Dashboard
    path('', views.dashboard, name='dashboard'),

    # Inventory
    path('inventory/', views.inventory_list, name='inventory_list'),
    path('inventory/<int:product_id>/', views.stock_card, name='stock_card'),
    path('transactions/', views.transaction_list, name='transaction_list'),

    # Receiving
    path('receive/', views.receive_stock, name='receive_stock'),
    path('receive/confirm/', views.confirm_receive, name='confirm_receive'),

    # Picking
    path('pick-lists/', views.pick_list_list, name='pick_list_list'),
    path('pick-lists/create/', views.create_pick_list, name='create_pick_list'),
    path('pick-lists/<int:pk>/', views.pick_list_detail, name='pick_list_detail'),
    path('pick-lists/<int:pk>/assign/', views.assign_pick_list, name='assign_pick_list'),

    # Cycle Counting
    path('cycle-counts/', views.cycle_count_list, name='cycle_count_list'),
    path('cycle-counts/create/', views.create_cycle_count, name='create_cycle_count'),
    path('cycle-counts/<int:pk>/', views.cycle_count_detail, name='cycle_count_detail'),

    # Alerts
    path('alerts/', views.low_stock_alerts, name='low_stock_alerts'),
    path('alerts/<int:pk>/acknowledge/', views.acknowledge_alert, name='acknowledge_alert'),

    # Warehouses & Locations
    path('warehouses/', views.warehouse_list, name='warehouse_list'),
    path('warehouses/add/', views.warehouse_add, name='warehouse_add'),
    path('warehouses/<int:pk>/', views.warehouse_detail, name='warehouse_detail'),
    path('locations/', views.location_list, name='location_list'),
    path('locations/add/', views.location_add, name='location_add'),
]
