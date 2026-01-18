from django.urls import path
from webpages import views as webpages_views
from delivery import views as delivery_views
from orders import views as orders_views

app_name = 'delivery'
urlpatterns = [

    # Zone Map
    path('zones/map/', delivery_views.zone_map, name='zone_map'),
    path('zones/api/', delivery_views.zone_map_api, name='zone_map_api'),

    # requst to user update address before delivery
    path('<str:dl_task_number>/<int:mobile_no>/',
         delivery_views.dl_address_update, name='dl_address'),

    path('ajax/get_zone_name/', delivery_views.get_zone_name, name='get_zone_name'),


    # business side delivery data
    path('delivery_tasks/all/', delivery_views.all_delivery_tasks,
         name='all_delivery_tasks'),
    path('assigned_tasks/all/', delivery_views.assigned_tasks,
         name='assigned_tasks'),

    # asign driver to delivery task
    path("delivery_task/assign_driver/",
         delivery_views.assign_driver, name="assign_driver"),

    # ADDRESS LINK CREATE AND UPDATE FOR CUSTUMERS
    path("address_link/<str:dl_task_code>/",
         delivery_views.dl_address_link, name="dl_address_link"),

    path('address_link/<str:dl_task_code>/update/',
         delivery_views.save_location_data, name='save_location_data'),

]
