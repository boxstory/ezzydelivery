from django.urls import path
from webpages import views as webpages_views
from delivery import views as delivery_views
from orders import views as orders_views
from core import views as core_views
from fleet import views as fleet_views
from client import views as business_views

app_name = 'business'
urlpatterns = [
    # BUSINESS LINKS
    path('dashboard/', business_views.business_dashboard,
         name='business_dashboard'),

    # PICKUP LOCATIONS
    path('pickup_location/add/',
         business_views.pickup_location_add, name='pickup_location_add'),
    path('pickup_location/<int:pickup_location_id>/update/',
         business_views.pickup_location_update, name='pickup_location_update'),
    path('pickup_location/<int:pickup_location_id>/delete/',
         business_views.pickup_location_delete, name='pickup_location_delete'),
    path('pickup_locations/',
         business_views.pickup_location_list, name='pickup_location_list'),

    # frontend
    path('<int:business_id>/', business_views.business_profile,
         name='business_profile'),
    path('all', business_views.all_business, name='all_business'),
    path('<int:business_id>/update/', business_views.business_profile_update,
         name='business_profile_update'),
    path('logo/<int:business_id>/update/',
         business_views.business_logo_update, name='business_logo_update'),

    # driver_directory
    path('driver_directory/', business_views.driver_directory,
         name='driver_directory'),
    path('driver_directory/add/', business_views.driver_directory_add,
         name='driver_directory_add'),
    path('driver_directory/<int:id>/delete/',
         business_views.driver_directory_delete, name='driver_directory_delete'),
     


]
