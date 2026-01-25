from django.urls import path
from webpages import views as webpages_views
from delivery import views as delivery_views
from orders import views as orders_views
from core import views as core_views
from fleet import views as fleet_views
from business import views as business_views

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


     #  Financial Accounts
     path('cod_collection/',
          fleet_views.cod_collection, name='cod_collection'),
     path('cod_submission/',
          fleet_views.cod_submission, name='cod_submission'),
     path('earnings/',
          fleet_views.driver_earnings, name='driver_earnings'),
     path('transactions/',
          fleet_views.transaction_history, name='transaction_history'),

     # Profile
     path('profile/',
          fleet_views.driver_profile_mobile, name='driver_profile_mobile'),

     # Performance & Reports
     path('performance/',
          fleet_views.driver_performance, name='driver_performance'),
     path('reports/',
          fleet_views.driver_reports, name='driver_reports'),
     path('analytics/',
          fleet_views.driver_analytics, name='driver_analytics'),

     # Pickup Scanner
     path('pickup/scanner/',
          fleet_views.pickup_scanner, name='pickup_scanner'),
     path('pickup/scan/',
          fleet_views.pickup_scan_process, name='pickup_scan_process'),
]
