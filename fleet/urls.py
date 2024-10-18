from django.urls import path
from webpages import views as webpages_views
from delivery import views as delivery_views
from orders import views as orders_views
from core import views as core_views
from fleet import views as fleet_views
from client import views as business_views

app_name = 'fleet'
urlpatterns = [
     # frontend
     path('<int:fleet_id>/', fleet_views.driver_profile, name='driver_profile'),
     path('', fleet_views.fleets, name='fleets'),

     # backend
     path('dashboard/', fleet_views.fleet_dashboard, name='fleet_dashboard'),


     # documents
     path('documents/',
          fleet_views.driver_documents, name='driver_documents'),
     path('documents/upload/<int:fleet_id>/',
          fleet_views.driver_documents_upload, name='driver_documents_upload'),
     path('documents/<int:fleet_id>/<int:doc_id>/update',
          fleet_views.driver_documents_update, name='driver_documents_update'),
     path('documents/<int:fleet_id>/<int:doc_id>/delete',
          fleet_views.driver_documents_delete, name='driver_documents_delete'),

     # vehicle

     path('vehicle_own/',
          fleet_views.vehicle_own, name='vehicle_own'),
     path('vehicle_add/',
          fleet_views.vehicle_add, name='vehicle_add'),
     path('vehicle/<int:vehicle_id>/update/',
          fleet_views.vehicle_update, name='vehicle_update'),
     path('vehicle_delete/<int:fleet_id>/<int:vehicle_id>/',
          fleet_views.vehicle_delete, name='vehicle_delete'),


     #  Financeial Accounts
     path('cod_collection/',
          fleet_views.cod_collection, name='cod_collection'),



    #     path('delivery_tasks/<int:dl_id>/',
    #          fleet_views.single_delivery_task, name='single_delivery_task'),
    #     path('delivery_address_details/',
    #          delivery_views.delivery_address_details, name='delivery_address_details'),

]
