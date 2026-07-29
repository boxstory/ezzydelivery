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
     path('cod_export/',
          fleet_views.cod_export, name='cod_export'),
     path('cod_transaction_detail/',
          fleet_views.cod_transaction_detail, name='cod_transaction_detail'),
     path('cod_transaction_pdf/',
          fleet_views.cod_transaction_pdf, name='cod_transaction_pdf'),
     path('earnings/',
          fleet_views.driver_earnings, name='driver_earnings'),
     path('transactions/',
          fleet_views.transaction_history, name='transaction_history'),
     path('transactions/<str:txn_code>/',
          fleet_views.transaction_detail_page, name='transaction_detail_page'),
     path('finance/',
          fleet_views.fleet_finance_summary, name='fleet_finance_summary'),

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

     # First-Mile Pickups (collect from client)
     path('pickups/',
          fleet_views.driver_pickups, name='driver_pickups'),
     path('pickups/accept/',
          fleet_views.accept_pickup, name='accept_pickup'),
     path('pickups/status/',
          fleet_views.update_pickup_status, name='update_pickup_status'),
     path('pickups/scan/',
          fleet_views.pickup_scan_collect, name='pickup_scan_collect'),
     path('pickups/route/',
          fleet_views.route_pickup, name='route_pickup'),
     path('pickups/transfer/confirm/',
          fleet_views.confirm_pickup_transfer, name='confirm_pickup_transfer'),
     path('pickups/transfer/targets/',
          fleet_views.pickup_transfer_targets, name='pickup_transfer_targets'),

     # Notifications
     path('notifications/',
          fleet_views.driver_notifications, name='driver_notifications'),
     path('notifications/mark-read/',
          fleet_views.notifications_mark_read, name='notifications_mark_read'),
     path('notifications/count/',
          fleet_views.notifications_unread_count, name='notifications_unread_count'),

     # Settings & Help
     path('settings/',
          fleet_views.driver_settings, name='driver_settings'),
     path('help/',
          fleet_views.driver_help, name='driver_help'),

     # Driver Tasks (migrated from delivery app)
     path('tasks/',
          fleet_views.driver_tasks, name='driver_tasks'),
     path('tasks/take-scan/',
          fleet_views.fleet_task_take_scan, name='fleet_task_take_scan'),
     path('tasks/scan-take/',
          fleet_views.fleet_task_scan_take_any, name='fleet_task_scan_take_any'),
     path('tasks/assign/',
          fleet_views.fleet_assign_driver, name='fleet_assign_driver'),
     path('tasks/accept/',
          fleet_views.fleet_accept_task, name='fleet_accept_task'),
     path('tasks/start/',
          fleet_views.fleet_start_ride, name='fleet_start_ride'),
     path('tasks/postpone/',
          fleet_views.fleet_postpone_task, name='fleet_postpone_task'),
     path('tasks/<int:task_id>/partial-delivery/',
          fleet_views.fleet_partial_delivery, name='fleet_partial_delivery'),
     path('tasks/<int:task_id>/timeline/',
          fleet_views.fleet_task_timeline, name='fleet_task_timeline'),
     path('tasks/<int:task_id>/navigate/',
          fleet_views.fleet_task_navigation, name='fleet_task_navigation'),
     path('tasks/<int:task_id>/edit-location/',
          fleet_views.fleet_task_edit_location, name='fleet_task_edit_location'),
     path('tasks/resolve-location/',
          fleet_views.fleet_resolve_location, name='fleet_resolve_location'),
     path('tasks/map/',
          fleet_views.fleet_tasks_map, name='fleet_tasks_map'),

     # Delivery Proof
     path('task/<int:task_id>/proof/upload/',
          fleet_views.upload_delivery_proof, name='upload_delivery_proof'),

     # Staff: COD Submission Management
     path('staff/cod-submissions/',
          fleet_views.staff_cod_submissions, name='staff_cod_submissions'),
     path('staff/cod-submissions/<str:txn_code>/edit/',
          fleet_views.staff_cod_submission_edit, name='staff_cod_submission_edit'),
     path('staff/cod-submissions/<str:txn_code>/add-task/',
          fleet_views.staff_cod_submission_add_task, name='staff_cod_submission_add_task'),
     path('staff/cod-submissions/<str:txn_code>/remove-task/',
          fleet_views.staff_cod_submission_remove_task, name='staff_cod_submission_remove_task'),
     path('staff/cod-submissions/<str:txn_code>/approve/',
          fleet_views.staff_cod_submission_approve, name='staff_cod_submission_approve'),
]
