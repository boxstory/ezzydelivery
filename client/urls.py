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

     # BUSINESS settings
    path('<int:business_id>/settings/', business_views.business_settings,
         name='business_settings'),
    # PICKUP LOCATIONS settings
    path('settings/pickup_location/add/',
         business_views.pickup_location_add, name='pickup_location_add'),
    path('settings/pickup_location/<int:pickup_location_id>/update/',
         business_views.pickup_location_update, name='pickup_location_update'),
    path('settings/pickup_location/<int:pickup_location_id>/delete/',
         business_views.pickup_location_delete, name='pickup_location_delete'),
    path('settings/pickup_locations/',
         business_views.pickup_location_list, name='pickup_location_list'),
     # api settings       
    path('<int:business_id>/settings/api/list/', business_views.business_settings_api_list,
         name='business_settings_api_list'),
    path('<int:business_id>/settings/api/add/', business_views.business_settings_api_add,
         name='business_settings_api_add'),
    path('<int:business_id>/settings/api/<int:api_id>/update/', business_views.business_settings_api_update,
         name='business_settings_api_update'),
    path('<int:business_id>/settings/api/<int:api_id>/test/', business_views.business_settings_api_test,
         name='business_settings_api_test'),
    path('<int:business_id>/settings/api/<int:api_id>/test/result', business_views.business_settings_api_test_result,
         name='business_settings_api_test_result'),
#     path('<int:business_id>/settings/api/<int:api_id>/test/call', business_views.business_settings_api_test_call,
#          name='business_settings_api_test_call'),

     
     # teams settings
     path('<int:business_id>/teams/', business_views.business_teams,
          name='business_teams'),
     path('<int:business_id>/teams/add/', business_views.business_teams_add,
               name='business_teams_add'),
     path('<int:business_id>/teams/<int:team_id>/update/', business_views.business_teams_update,
               name='business_teams_update'),

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
