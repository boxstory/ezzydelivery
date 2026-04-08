from django.urls import path
from webpages import views as webpages_views
from delivery import views as delivery_views
from orders import views as orders_views

app_name = 'delivery'
urlpatterns = [

    # Zone Map
    path('zones/map/', delivery_views.zone_map, name='zone_map'),
    path('zones/api/', delivery_views.zone_map_api, name='zone_map_api'),
    path('zones/list/', delivery_views.zone_list, name='zone_list'),
    path('zones/groups/', delivery_views.zone_groups, name='zone_groups'),
    path('zones/areas/', delivery_views.zone_areas, name='zone_areas'),
    path('zones/areas/update-pin/', delivery_views.update_area_pin, name='update_area_pin'),

    # requst to user update address before delivery
    path('<str:dl_task_number>/<int:mobile_no>/',
         delivery_views.dl_address_update, name='dl_address'),

    path('ajax/get_zone_name/', delivery_views.get_zone_name, name='get_zone_name'),
    path('get_street_polygon/<int:zone_number>/<int:street_number>/',
         delivery_views.get_street_polygon, name='get_street_polygon'),

    # Polygon Editor
    path('zones/edit-polygon/<int:zone_number>/',
         delivery_views.edit_zone_polygon, name='edit_zone_polygon'),
    path('zones/save-polygon/<int:zone_number>/',
         delivery_views.save_zone_polygon, name='save_zone_polygon'),


    # business side delivery data
    path('delivery_tasks/all/', delivery_views.all_delivery_tasks,
         name='all_delivery_tasks'),
    path('assigned_tasks/all/', delivery_views.assigned_tasks,
         name='assigned_tasks'),

    # asign driver to delivery task
    path("delivery_task/assign_driver/",
         delivery_views.assign_driver, name="assign_driver"),

    # Accept assigned task
    path("delivery_task/accept_task/",
         delivery_views.accept_task, name="accept_task"),

    # Start ride - update status to in_transit
    path("delivery_task/start_ride/",
         delivery_views.start_ride, name="start_ride"),

    # Task navigation map
    path("task/<int:task_id>/navigation/",
         delivery_views.task_navigation, name="task_navigation"),

    # ADDRESS LINK CREATE AND UPDATE FOR CUSTUMERS
    path("address_link/<str:dl_task_code>/",
         delivery_views.dl_address_link, name="dl_address_link"),

    path('address_link/<str:dl_task_code>/update/',
         delivery_views.save_location_data, name='save_location_data'),

]
