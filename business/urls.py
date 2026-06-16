from django.urls import path
from webpages import views as webpages_views
from delivery import views as delivery_views
from orders import views as orders_views
from core import views as core_views
from fleet import views as fleet_views
from business import views as business_views

app_name = 'business'
urlpatterns = [
    # BUSINESS LINKS
    path('dashboard/', business_views.business_dashboard,
         name='business_dashboard'),
     
     # BUSINESS settings
    path('<int:business_id>/settings/', business_views.business_settings,
         name='business_settings'),
    # PICKUP LOCATIONS settings
    path('settings/pickup_location/choose/',
         business_views.pickup_location_choose, name='pickup_location_choose'),
    path('settings/pickup_location/add/',
         business_views.pickup_location_add, name='pickup_location_add'),
    path('settings/pickup_location/<int:pickup_location_id>/update/',
         business_views.pickup_location_update, name='pickup_location_update'),
    path('settings/pickup_location/<int:pickup_location_id>/delete/',
         business_views.pickup_location_delete, name='pickup_location_delete'),
    path('settings/pickup_locations/',
         business_views.pickup_location_list, name='pickup_location_list'),
    path('settings/warehouse-request/',
         business_views.warehouse_request, name='warehouse_request'),
     # api settings       
    path('<int:business_id>/settings/api/list/', business_views.business_settings_api_list,
         name='business_settings_api_list'),
    path('<int:business_id>/settings/api/add/', business_views.business_settings_api_add,
         name='business_settings_api_add'),
    path('<int:business_id>/settings/api/<int:api_id>/update/', business_views.business_settings_api_update,
         name='business_settings_api_update'),
    path('<int:business_id>/settings/api/<int:api_id>/test/', business_views.business_settings_api_test,
         name='business_settings_api_test'),
    path('<int:business_id>/settings/api/<int:api_id>/test/result/', business_views.business_settings_api_test_result,
         name='business_settings_api_test_result'),
    path('<int:business_id>/settings/api/<int:api_id>/delete/', business_views.business_settings_api_delete,
         name='business_settings_api_delete'),
    # Shopify OAuth
    path('<int:business_id>/settings/api/<int:api_id>/shopify-oauth/', business_views.shopify_oauth_start,
         name='shopify_oauth_start'),
    path('shopify/oauth/callback/', business_views.shopify_oauth_callback,
         name='shopify_oauth_callback'),

     # teams settings
     path('<int:business_id>/teams/', business_views.business_teams,
          name='business_teams'),
     path('<int:business_id>/teams/add/', business_views.business_teams_add,
               name='business_teams_add'),
     path('<int:business_id>/teams/<int:team_id>/update/', business_views.business_teams_update,
               name='business_teams_update'),
     path('<int:business_id>/teams/<int:team_id>/permissions/', business_views.business_team_permissions,
               name='business_team_permissions'),
     path('<int:business_id>/teams/<int:team_id>/remove/', business_views.business_team_remove,
               name='business_team_remove'),
     path('<int:business_id>/teams/<int:team_id>/status/', business_views.business_team_status_change,
               name='business_team_status_change'),
     # team join requests
     path('search/', business_views.business_search_ajax, name='business_search'),
     path('join-request/', business_views.business_join_request_submit, name='business_join_request'),
     path('join-request/<int:req_id>/cancel/', business_views.business_join_request_cancel, name='business_join_request_cancel'),
     path('<int:business_id>/teams/join-requests/', business_views.business_join_requests_list, name='business_join_requests'),
     path('<int:business_id>/teams/join-requests/<int:req_id>/action/', business_views.business_join_request_action, name='business_join_request_action'),

    # frontend
     #listing all business profiels cards
    path('all/', business_views.all_business, name='all_business'),
     #others business profile display
    path('<int:business_id>/display/', business_views.business_profile_display,
         name='business_profile_display'), 

    #own business prodile
    path('profile/', business_views.business_profile,
         name='business_profile'),
     #business account info update
    path('<int:business_id>/update/', business_views.business_profile_update,
         name='business_profile_update'),
     #business profile in details update
    path('<int:business_id>/info_update/', business_views.business_profile_info_update,
         name='business_profile_info_update'),
    path('logo/<int:business_id>/update/',
         business_views.business_logo_update, name='business_logo_update'),

    # driver_directory
    path('driver_directory/', business_views.driver_directory,
         name='driver_directory'),
    path('driver_directory/add/', business_views.driver_directory_add,
         name='driver_directory_add'),
    path('driver_directory/<int:id>/delete/',
         business_views.driver_directory_delete, name='driver_directory_delete'),

    # workflow guide
    path('workflow-guide/', business_views.workflow_guide, name='workflow_guide'),

    # business selector (for users with multiple businesses)
    path('selector/', business_views.business_selector, name='business_selector'),
    path('switch/<int:business_id>/', business_views.business_switch, name='business_switch'),

    # Finance section
    path('finance/', business_views.business_finance_dashboard, name='business_finance_dashboard'),
    path('finance/transactions/', business_views.business_transactions, name='business_transactions'),
    path('finance/cod-statement/', business_views.business_cod_statement, name='business_cod_statement'),

    # Live Tracking Map
    path('tracking/', business_views.live_tracking_map, name='live_tracking_map'),
    path('tracking/data/', business_views.live_tracking_data, name='live_tracking_data'),

    # Branded Tracking Page Settings
    path('settings/tracking-page/', business_views.branded_tracking_settings, name='branded_tracking_settings'),

    # WhatsApp notification triggers
    path('settings/whatsapp-triggers/', business_views.whatsapp_triggers_list, name='whatsapp_triggers_list'),
    path('settings/whatsapp-triggers/toggle/', business_views.whatsapp_trigger_toggle, name='whatsapp_trigger_toggle'),

    # Reports & CSV Export
    path('reports/', business_views.reports_dashboard, name='reports_dashboard'),
    path('reports/stats/', business_views.reports_stats_partial, name='reports_stats_partial'),
    path('reports/orders/csv/', business_views.export_orders_csv, name='export_orders_csv'),
    path('reports/cod/csv/', business_views.export_cod_csv, name='export_cod_csv'),
    path('reports/performance/csv/', business_views.export_performance_csv, name='export_performance_csv'),

    # Bulk Label Printing
    path('labels/bulk-print/', business_views.bulk_print_labels, name='bulk_print_labels'),

    # Returns Management
    path('returns/', business_views.returns_list, name='returns_list'),
    path('returns/<int:return_id>/', business_views.return_detail, name='return_detail'),
    path('returns/create/<int:order_id>/', business_views.return_create, name='return_create'),
    path('returns/<int:return_id>/status/', business_views.return_update_status, name='return_update_status'),

    # Product Requests (Fulfillment Service)
    path('inbound-requests/', business_views.inbound_requests_list, name='inbound_requests_list'),
    path('inbound-requests/create/', business_views.inbound_request_create, name='inbound_request_create'),
    path('inbound-requests/<int:pk>/', business_views.inbound_request_detail, name='inbound_request_detail'),
    path('outbound-requests/', business_views.outbound_requests_list, name='outbound_requests_list'),

]
