from django.urls import path
from webpages import views as webpages_views
from workforce import views as workforce_views
from workforce import dispatch_views
from workforce import crm_views
from delivery import views as delivery_views
from orders import views as orders_views
from core import views as core_views

app_name = 'workforce'
urlpatterns = [
    path('dashboard/', workforce_views.wf_dashboard, name='wf_dashboard'),

    # Sellers section urls -------------------------------------------------------------------
    path('sellers/', workforce_views.sellers_list, name='sellers_list'),
    path('sellers/pending/', workforce_views.sellers_pending, name='sellers_pending'),
    path('sellers/active/', workforce_views.sellers_active, name='sellers_active'),
    path('sellers/inactive/', workforce_views.sellers_inactive, name='sellers_inactive'),
    path('sellers/api-configs/', workforce_views.wf_seller_api_configs, name='wf_seller_api_configs'),
    path('sellers/api-configs/<int:api_id>/approve/', workforce_views.wf_approve_api_config, name='wf_approve_api_config'),
    path('sellers/api-configs/<int:api_id>/get/', workforce_views.wf_get_api_config, name='wf_get_api_config'),
    path('sellers/api-configs/<int:api_id>/update/', workforce_views.wf_update_api_config, name='wf_update_api_config'),
    path('sellers/api-configs/<int:api_id>/delete/', workforce_views.wf_delete_api_config, name='wf_delete_api_config'),
    path('sellers/api-configs/<int:api_id>/test/', workforce_views.wf_test_api_config, name='wf_test_api_config'),
    path('sellers/api-configs/<int:api_id>/test/result/', workforce_views.wf_test_api_config_result, name='wf_test_api_config_result'),
    path('sellers/api-configs/google-sheet/save/', workforce_views.wf_save_google_sheet, name='wf_save_google_sheet'),
    path('google-sheets/auth/', workforce_views.google_sheets_auth_start, name='google_sheets_auth_start'),
    path('google-sheets/auth/callback/', workforce_views.google_sheets_auth_callback, name='google_sheets_auth_callback'),
    path('sellers/<int:business_id>/', workforce_views.seller_detail, name='seller_detail'),
    path('sellers/<int:business_id>/api-products/', workforce_views.seller_api_products, name='seller_api_products'),
    path('sellers/<int:business_id>/api-products/import/', workforce_views.seller_api_products_import, name='seller_api_products_import'),
    path('sellers/<int:business_id>/api-orders/', workforce_views.seller_api_orders, name='seller_api_orders'),
    path('sellers/<int:business_id>/doc-field/', workforce_views.seller_doc_field_update, name='seller_doc_field_update'),
    path('sellers/<int:business_id>/pickup-location/add/', workforce_views.wf_pickup_location_add, name='wf_pickup_location_add'),
    path('sellers/<int:business_id>/pickup-location/<int:location_id>/update/', workforce_views.wf_pickup_location_update, name='wf_pickup_location_update'),
    path('sellers/<int:business_id>/pickup-location/<int:location_id>/delete/', workforce_views.wf_pickup_location_delete, name='wf_pickup_location_delete'),

    # Drivers section urls -------------------------------------------------------------------
    path('drivers/', workforce_views.drivers_list, name='drivers_list'),
    path('drivers/pending/', workforce_views.drivers_pending, name='drivers_pending'),
    path('drivers/active/', workforce_views.drivers_active, name='drivers_active'),
    path('drivers/inactive/', workforce_views.drivers_inactive, name='drivers_inactive'),
    path('drivers/<int:driver_id>/', workforce_views.driver_detail, name='driver_detail'),
    path('drivers/<int:driver_id>/toggle-status/', workforce_views.driver_toggle_status, name='driver_toggle_status'),
    path('drivers/<int:driver_id>/work-pref/', workforce_views.driver_set_work_pref, name='driver_set_work_pref'),
    path('drivers/<int:driver_id>/set-status/', workforce_views.driver_set_status, name='driver_set_status'),
    path('drivers/<int:driver_id>/vehicle/add/', workforce_views.driver_vehicle_save, name='driver_vehicle_add'),
    path('drivers/<int:driver_id>/vehicle/<int:vehicle_id>/edit/', workforce_views.driver_vehicle_save, name='driver_vehicle_edit'),
    path('drivers/<int:driver_id>/vehicle/<int:vehicle_id>/delete/', workforce_views.driver_vehicle_delete, name='driver_vehicle_delete'),
    path('drivers/<int:driver_id>/document/add/', workforce_views.driver_document_save, name='driver_document_add'),
    path('drivers/<int:driver_id>/document/<int:document_id>/edit/', workforce_views.driver_document_save, name='driver_document_edit'),
    path('drivers/<int:driver_id>/document/<int:document_id>/delete/', workforce_views.driver_document_delete, name='driver_document_delete'),
    path('drivers/export/', workforce_views.export_drivers_csv, name='export_drivers_csv'),

    #Orders sections urls -------------------------------------------------------------------
    path('orders/add/', workforce_views.add_order, name='wf_orders_add'),
    # Bulk import uses shared views from orders app
    path('orders/bulk-import/', orders_views.bulk_import_orders, name='wf_orders_bulk_import'),
    path('orders/bulk-import/preview/', orders_views.bulk_import_preview, name='wf_orders_bulk_preview'),
    path('orders/bulk-import/save/', orders_views.bulk_import_save, name='wf_orders_bulk_save'),
    path('orders/bulk-import/save-mapping/', orders_views.bulk_import_save_mapping, name='wf_orders_bulk_save_mapping'),
    path('orders/bulk-import/finalize/', orders_views.bulk_import_finalize, name='wf_orders_bulk_finalize'),
    # Reusable Import Wizard
    path('import-wizard/prepare/', workforce_views.import_wizard_prepare, name='import_wizard_prepare'),
    path('import-wizard/<int:import_log_id>/', workforce_views.import_wizard, name='import_wizard'),
    path('import-wizard/preview/', workforce_views.import_wizard_preview, name='import_wizard_preview'),
    path('import-wizard/confirm/', workforce_views.import_wizard_confirm, name='import_wizard_confirm'),
    path('import-wizard/save-mapping/', workforce_views.import_wizard_save_mapping, name='import_wizard_save_mapping'),
    path('import-wizard/mapping-manager/', workforce_views.wf_mapping_manager, name='wf_mapping_manager'),
    path('import-wizard/mapping-manager/save/', workforce_views.wf_mapping_manager_save, name='wf_mapping_manager_save'),
    path('import-wizard/mapping-manager/test/', workforce_views.wf_mapping_manager_test, name='wf_mapping_manager_test'),

    path('orders/api-orders/', workforce_views.wf_api_orders, name='wf_api_orders'),
    path('orders/api-orders/bulk-transfer/', workforce_views.bulk_transfer_api_orders, name='bulk_transfer_api_orders'),
    path('orders/api-orders/import/', workforce_views.import_api_orders, name='import_api_orders'),
    path('orders/api-orders/preview/', workforce_views.preview_api_import, name='preview_api_import'),
    path('orders/api-orders/sheet-headers/', workforce_views.wf_sheet_headers, name='wf_sheet_headers'),
    path('orders/api-orders/sheet-worksheets/', workforce_views.wf_sheet_worksheets, name='wf_sheet_worksheets'),
    path('orders/api-orders/sheet-save-tab/', workforce_views.wf_sheet_save_tab, name='wf_sheet_save_tab'),
    path('orders/api-orders/source-headers/', workforce_views.wf_source_headers, name='wf_source_headers'),
    path('orders/api-orders/upload-sample-headers/', workforce_views.wf_upload_sample_headers, name='wf_upload_sample_headers'),
    path('orders/api-orders/save-mapping/', workforce_views.wf_save_column_mapping, name='wf_save_column_mapping'),
    path('orders/api-guide/', workforce_views.orders_api_guide, name='wf_orders_api_guide'),
    # Webhook Imports
    path('webhook-imports/', workforce_views.wf_webhook_imports, name='wf_webhook_imports'),
    path('webhook-imports/generate-key/<int:business_id>/', workforce_views.wf_webhook_generate_key, name='wf_webhook_generate_key'),
    path('orders/pickup-locations/<int:business_id>/', workforce_views.get_pickup_locations, name='get_pickup_locations'),
    path('orders/all/', workforce_views.all_orders, name='wf_orders_all'),
    path('orders/print-labels/', workforce_views.print_labels, name='wf_orders_print_labels'),
    path('orders/print-waybill/', workforce_views.wf_print_waybill, name='wf_print_waybill'),
    path('orders/fulfilled-clients/', workforce_views.fulfilled_clients_orders, name='wf_orders_fulfilled_clients'),
    path('orders/non-fulfilled-clients/', workforce_views.non_fulfilled_clients_orders, name='wf_orders_non_fulfilled_clients'),
    path('orders/export/', workforce_views.export_orders_csv, name='export_orders_csv'),
    path('orders/by-seller/', workforce_views.orders_by_seller, name='wf_orders_by_seller'),
    path('orders/to_publish/', workforce_views.orders_to_publish, name='wf_orders_to_publish'),
    path('orders/published/', workforce_views.orders_published, name='wf_orders_published'),
    path('orders/pending-verification/', workforce_views.orders_pending_verification, name='orders_pending_verification'),
    path('orders/<int:order_id>/verify-address/', workforce_views.verify_order_address, name='verify_order_address'),
    path('orders/submit_to_task/<int:order_id>/', workforce_views.submit_to_task, name='submit_to_task'),

    # Order detail and actions
    path('orders/<int:order_id>/', workforce_views.order_detail, name='order_detail'),
    path('orders/<int:order_id>/whatsapp-defaults/', workforce_views.order_whatsapp_defaults, name='order_whatsapp_defaults'),
    path('orders/<int:order_id>/send-whatsapp/', workforce_views.send_order_whatsapp, name='send_order_whatsapp'),
    path('orders/<int:order_id>/edit/', workforce_views.order_edit, name='order_edit'),
    path('orders/<int:order_id>/items/add/', workforce_views.order_item_add, name='order_item_add'),
    path('orders/<int:order_id>/items/<int:item_id>/update/', workforce_views.order_item_update, name='order_item_update'),
    path('orders/<int:order_id>/items/<int:item_id>/delete/', workforce_views.order_item_delete, name='order_item_delete'),
    path('orders/<int:order_id>/cancel/', workforce_views.cancel_order, name='cancel_order'),
    path('orders/<int:order_id>/duplicate/', workforce_views.duplicate_order, name='duplicate_order'),
    path('orders/<int:order_id>/partial-return/', workforce_views.partial_return_order, name='partial_return_order'),
    path('orders/<int:order_id>/delete/', workforce_views.delete_order, name='delete_order'),
    path('order/<int:order_id>/update-zone/', workforce_views.update_order_zone, name='update_order_zone'),
    path('api/resolve-location/', workforce_views.resolve_location_link, name='resolve_location_link'),
    path('order/<int:order_id>/assign-driver/', workforce_views.assign_driver_to_order, name='assign_driver_to_order'),

    # AJAX endpoints for orders
    path('orders/<int:order_id>/publish/', workforce_views.publish_order_to_delivery, name='publish_order_to_delivery'),
    path('orders/<int:order_id>/update-status/', workforce_views.update_order_status, name='update_order_status'),
    path('orders/bulk-update-status/', workforce_views.bulk_update_order_status, name='bulk_update_order_status'),
    path('orders/<int:order_id>/add-comment/', workforce_views.add_order_comment, name='add_order_comment'),
    path('orders/<int:order_id>/update-coords/', workforce_views.update_order_coords, name='update_order_coords'),
    path('ajax/zone-name/', workforce_views.ajax_zone_name, name='ajax_zone_name'),



    #Deliveries sections urls ----------------------------------------------------------------
    path('tasks/dl_list_all/', workforce_views.dl_list_all, name='dl_list_all'),
    path('tasks/fulfilled-clients/', workforce_views.fulfilled_clients_tasks, name='dl_list_fulfilled_clients'),
    path('tasks/non-fulfilled-clients/', workforce_views.non_fulfilled_clients_tasks, name='dl_list_non_fulfilled_clients'),
    path('tasks/unpublished/', workforce_views.dl_list_ready_to_published_to_dms, name='dl_list_ready_to_published_to_dms'),
    path('tasks/published/', workforce_views.dl_list_published_to_dms, name='dl_list_published_to_dms'),
    path('tasks/dl_list_incompleted/', workforce_views.dl_list_incompleted_details, name='dl_list_incompleted_details'),

    # Delivery task detail view
    path('delivery-task/<int:task_id>/', workforce_views.delivery_task_detail, name='delivery_task_detail'),
    path('delivery-task/<int:task_id>/edit/', workforce_views.delivery_task_edit, name='delivery_task_edit'),

    # AJAX endpoints for delivery tasks
    path('delivery-task/<int:task_id>/publish-fleets/', workforce_views.publish_task_to_fleets, name='publish_task_to_fleets'),
    path('delivery-task/<int:task_id>/unpublish-fleets/', workforce_views.unpublish_task_from_fleets, name='unpublish_task_from_fleets'),
    path('delivery-task/<int:task_id>/assign-driver/', workforce_views.assign_driver_to_task, name='assign_driver_to_task'),
    path('delivery-task/<int:task_id>/unassign-driver/', workforce_views.unassign_driver_from_task, name='unassign_driver_from_task'),
    path('delivery-task/<int:task_id>/update-status/', workforce_views.update_task_status, name='update_task_status'),
    path('delivery-task/<int:task_id>/cod-return/', workforce_views.process_cod_return, name='process_cod_return'),

    # Bulk action endpoints for delivery tasks
    path('tasks/bulk-print/', workforce_views.bulk_print_tasks, name='bulk_print_tasks'),
    path('tasks/print-waybills/', workforce_views.bulk_print_waybills, name='bulk_print_waybills'),
    path('tasks/bulk-publish-fleets/', workforce_views.bulk_publish_fleets, name='bulk_publish_fleets'),
    path('tasks/bulk-publish-app/', workforce_views.bulk_publish_app, name='bulk_publish_app'),
    path('tasks/bulk-update-status/', workforce_views.bulk_update_status, name='bulk_update_status'),
    path('tasks/bulk-export/', workforce_views.bulk_export_tasks, name='bulk_export_tasks'),
    path('tasks/bulk-assign-driver/', workforce_views.bulk_assign_driver, name='bulk_assign_driver'),

    # First-Mile Pickup Automation
    path('pickups/', workforce_views.pickup_pool_status, name='pickup_pool_status'),
    path('pickups/assign/', workforce_views.pickup_staff_assign, name='pickup_staff_assign'),
    path('pickup-automation/', workforce_views.pickup_automation_list, name='pickup_automation_list'),
    path('pickup-automation/save/', workforce_views.pickup_automation_save, name='pickup_automation_save'),
    path('pickup-automation/fleet/<int:business_id>/', workforce_views.pickup_fleet_list, name='pickup_fleet_list'),
    path('pickup-automation/fleet/search/', workforce_views.pickup_fleet_driver_search, name='pickup_fleet_driver_search'),
    path('pickup-automation/fleet/update/', workforce_views.pickup_fleet_update, name='pickup_fleet_update'),

    # User Verification URLs
    path('verification/business/', workforce_views.business_verification_list, name='business_verification_list'),
    path('verification/drivers/', workforce_views.driver_verification_list, name='driver_verification_list'),
    path('verification/users/', workforce_views.user_verification_list, name='user_verification_list'),
    path('verification/teams/', workforce_views.team_verification_list, name='team_verification_list'),
    path('verification/check-business-code/', workforce_views.check_business_code_unique, name='check_business_code_unique'),
    path('verification/<int:profile_id>/update-status/', workforce_views.update_verification_status, name='update_verification_status'),
    path('verification/team/<int:team_id>/update-status/', workforce_views.update_team_status, name='update_team_status'),
    path('verification/<int:profile_id>/driver-profile/', workforce_views.view_user_driver_profile, name='view_user_driver_profile'),
    path('verification/<int:profile_id>/business-profile/', workforce_views.view_user_business_profile, name='view_user_business_profile'),

    # Additional Orders URLs
    path('orders/reported/', workforce_views.orders_reported, name='wf_orders_reported'),

    # Additional Tasks URLs
    path('tasks/followup-list/', workforce_views.tasks_followup_list, name='tasks_followup_list'),
    path('tasks/reported/', workforce_views.tasks_reported, name='tasks_reported'),
    path('tasks/live-map/', workforce_views.tasks_live_map, name='tasks_live_map'),

    # Finance Dashboard
    path('finance/', workforce_views.workforce_finance_dashboard, name='workforce_finance_dashboard'),

    # Fleet Accounts URLs
    path('fleet/driver-tasks/', workforce_views.wf_driver_tasks, name='wf_driver_tasks'),
    path('fleet/cod-in-hand/', workforce_views.fleet_cod_in_hand, name='fleet_cod_in_hand'),
    path('fleet/drivers-earnings/', workforce_views.fleet_drivers_earnings, name='fleet_drivers_earnings'),
    path('fleet/earnings-verification/', workforce_views.earnings_verification, name='earnings_verification'),
    path('fleet/earnings-verification/action/', workforce_views.earnings_verification_action, name='earnings_verification_action'),
    path('fleet/transactions/', workforce_views.fleet_transactions, name='fleet_transactions'),
    path('seller-transactions/', workforce_views.seller_transactions, name='seller_transactions'),
    path('fleet/bulk-settle-transactions/', workforce_views.bulk_settle_transactions, name='bulk_settle_transactions'),
    path('fleet/recalculate-cod-balances/', workforce_views.recalculate_cod_balances, name='recalculate_cod_balances'),
    path('fleet/transactions/<int:txn_id>/cod-details/', workforce_views.fleet_transaction_cod_details, name='fleet_transaction_cod_details'),
    path('fleet/transactions/<int:txn_id>/update-status/', workforce_views.fleet_transaction_update_status, name='fleet_transaction_update_status'),
    path('fleet/tasks/<int:task_id>/cod-correct/', workforce_views.fleet_task_cod_correct, name='fleet_task_cod_correct'),

    # COD bookkeeping ledger (all COD transactions, filterable)
    path('fleet/cod-ledger/', workforce_views.cod_ledger, name='cod_ledger'),

    # COD Settlement Report URLs
    path('fleet/cod-settlement/', workforce_views.cod_settlement_report, name='cod_settlement_report'),
    path('fleet/cod-settlement/action/', workforce_views.cod_settlement_action, name='cod_settlement_action'),
    path('fleet/cod-settlement/pdf/', workforce_views.cod_settlement_pdf, name='cod_settlement_pdf'),

    # Business COD Payout (Leg 3 — EzzyDelivery → Business)
    path('fleet/cod-business-settlement/', workforce_views.cod_business_settlement_report, name='cod_business_settlement_report'),
    path('fleet/cod-business-settlement/action/', workforce_views.cod_business_settlement_action, name='cod_business_settlement_action'),
    path('fleet/cod-business-settlement/reverse/', workforce_views.cod_business_settlement_reverse, name='cod_business_settlement_reverse'),
    path('fleet/cod-business-settlement/pdf/', workforce_views.cod_business_settlement_pdf, name='cod_business_settlement_pdf'),

    # COD Submissions Management (Staff)
    path('fleet/cod-submissions/', workforce_views.staff_cod_submissions_redirect, name='staff_cod_submissions'),
    path('fleet/cod-submissions/<str:txn_code>/edit/', workforce_views.staff_cod_submission_edit_redirect, name='staff_cod_submission_edit'),
    path('fleet/cod-submissions/<str:txn_code>/add-task/', workforce_views.staff_cod_submission_add_task_redirect, name='staff_cod_submission_add_task'),
    path('fleet/cod-submissions/<str:txn_code>/remove-task/', workforce_views.staff_cod_submission_remove_task_redirect, name='staff_cod_submission_remove_task'),
    path('fleet/cod-submissions/<str:txn_code>/approve/', workforce_views.staff_cod_submission_approve_redirect, name='staff_cod_submission_approve'),

    # Receipt Templates URLs
    path('receipt-templates/', workforce_views.receipt_templates_list, name='receipt_templates_list'),
    path('receipt-templates/create/', workforce_views.receipt_template_create, name='receipt_template_create'),
    path('receipt-templates/<int:template_id>/edit/', workforce_views.receipt_template_edit, name='receipt_template_edit'),
    path('receipt-templates/<int:template_id>/preview/', workforce_views.receipt_template_preview, name='receipt_template_preview'),
    path('receipt-templates/<int:template_id>/delete/', workforce_views.receipt_template_delete, name='receipt_template_delete'),
    path('settlement/<int:settlement_id>/receipt/', workforce_views.settlement_receipt_print, name='settlement_receipt_print'),
    path('fleet/task-sheets/', workforce_views.fleet_task_sheets_list, name='fleet_task_sheets_list'),
    path('fleet/task-sheet/<int:driver_id>/', workforce_views.fleet_task_sheet, name='fleet_task_sheet'),

    #Documents sections urls -----------------------------------------------------------------
    path('documents/driver-ids/', workforce_views.driver_documents_list, name='driver_documents_list'),
    path('documents/driver-ids/<int:document_id>/', workforce_views.driver_document_detail, name='driver_document_detail'),
    path('documents/vehicles/', workforce_views.vehicle_documents_list, name='vehicle_documents_list'),
    path('documents/vehicles/<int:driver_id>/', workforce_views.vehicle_document_detail, name='vehicle_document_detail'),
    path('documents/stores/', workforce_views.store_documents_list, name='store_documents_list'),
    path('documents/stores/<int:business_id>/', workforce_views.store_document_detail, name='store_document_detail'),
    path('documents/business-licenses/', workforce_views.business_licenses_list, name='business_licenses_list'),
    path('documents/business-licenses/<int:business_id>/', workforce_views.business_license_detail, name='business_license_detail'),
    path('documents/business-licenses/<int:business_id>/add-pickup-location/', workforce_views.workforce_pickup_location_add, name='workforce_pickup_location_add'),

    # API endpoints
    path('api/warehouse-locations/', workforce_views.api_warehouse_locations, name='api_warehouse_locations'),

    # Inventory URLs
    path('inventory/reports/', workforce_views.inventory_reports, name='inventory_reports'),
    path('inventory/restock-list/', workforce_views.inventory_restock_list, name='inventory_restock_list'),

    # Quick Links URLs
    path('reports/', workforce_views.staff_reports, name='staff_reports'),

    # Workflow guide
    path('workflow-guide/', workforce_views.workflow_guide, name='workflow_guide'),

    # Fulfillment Service & Purchase Orders
    path('suppliers/', workforce_views.suppliers_list, name='suppliers_list'),
    path('purchase-orders/', workforce_views.fulfilled_orders_list, name='fulfilled_orders_list'),

    # Warehouse-Business Links
    path('warehouses/', workforce_views.warehouses_list, name='warehouses_list'),
    path('warehouses/link-business/', workforce_views.warehouse_link_business, name='warehouse_link_business'),
    path('warehouses/unlink-business/', workforce_views.warehouse_unlink_business, name='warehouse_unlink_business'),

    # ==========================================
    # DISPATCH & BATCHING SECTION
    # ==========================================
    path('dispatch/', dispatch_views.dispatch_dashboard, name='dispatch_dashboard'),
    path('dispatch/batches/', dispatch_views.batch_list, name='dispatch_batch_list'),
    path('dispatch/batches/<int:batch_id>/', dispatch_views.batch_detail, name='dispatch_batch_detail'),
    path('dispatch/batches/<int:batch_id>/release/', dispatch_views.manual_release_batch, name='dispatch_release_batch'),
    path('dispatch/batches/<int:batch_id>/cancel/', dispatch_views.cancel_batch, name='dispatch_cancel_batch'),

    # Shift Management
    path('dispatch/shifts/', dispatch_views.shift_list, name='dispatch_shift_list'),
    path('dispatch/shifts/create/', dispatch_views.shift_create, name='dispatch_shift_create'),
    path('dispatch/shifts/<int:shift_id>/', dispatch_views.shift_detail, name='dispatch_shift_detail'),
    path('dispatch/shifts/<int:shift_id>/edit/', dispatch_views.shift_edit, name='dispatch_shift_edit'),

    # KPI Dashboard
    path('dispatch/kpis/', dispatch_views.kpi_dashboard, name='dispatch_kpi_dashboard'),
    path('dispatch/kpis/rider/<int:rider_id>/', dispatch_views.rider_kpi_detail, name='dispatch_rider_kpi'),

    # Config Management
    path('dispatch/config/', dispatch_views.config_list, name='dispatch_config_list'),
    path('dispatch/config/<int:location_id>/', dispatch_views.config_edit, name='dispatch_config_edit'),

    # HTMX Partials
    path('dispatch/partials/batch-monitor/', dispatch_views.batch_monitor_partial, name='dispatch_batch_monitor_partial'),
    path('dispatch/partials/shift-status/', dispatch_views.shift_status_partial, name='dispatch_shift_status_partial'),

    # API endpoints
    path('api/drivers-list/', workforce_views.api_drivers_list, name='api_drivers_list'),
    path('api/get-active-drivers/', workforce_views.get_active_drivers, name='get_active_drivers'),

    # Product Request Management
    path('product-requests/', workforce_views.product_requests_list, name='product_requests_list'),
    path('product-requests/<int:request_id>/<str:request_type>/approve/', workforce_views.approve_product_request, name='approve_product_request'),
    path('product-requests/<int:request_id>/<str:request_type>/complete/', workforce_views.complete_product_request, name='complete_product_request'),

    # QNAS Coordinate Lookup Tool
    path('tools/qnas-lookup/', workforce_views.qnas_lookup_tool, name='qnas_lookup_tool'),
    path('tools/qnas-test/', workforce_views.qnas_test, name='qnas_test'),

    # Forms / Inquiries
    path('forms/pricing-inquiries/', workforce_views.pricing_inquiries_list, name='pricing_inquiries_list'),
    path('forms/pricing-inquiries/<int:inquiry_id>/', workforce_views.pricing_inquiry_detail, name='pricing_inquiry_detail'),
    path('forms/pricing-inquiries/<int:inquiry_id>/update-status/', workforce_views.pricing_inquiry_update_status, name='pricing_inquiry_update_status'),
    path('forms/pricing-inquiries/<int:inquiry_id>/edit/', workforce_views.pricing_inquiry_edit, name='pricing_inquiry_edit'),
    path('forms/pricing-inquiries/<int:inquiry_id>/add-activity/', workforce_views.pricing_inquiry_add_activity, name='pricing_inquiry_add_activity'),
    path('forms/pricing-inquiries/<int:inquiry_id>/delete-activity/<int:activity_id>/', workforce_views.pricing_inquiry_delete_activity, name='pricing_inquiry_delete_activity'),

    # CRM Leads
    path('crm/leads/board/', crm_views.crm_leads_board, name='crm_leads_board'),
    path('crm/leads/', crm_views.crm_leads_list, name='crm_leads_list'),
    path('crm/leads/new/', crm_views.crm_lead_create, name='crm_lead_create'),
    path('crm/leads/<int:lead_id>/', crm_views.crm_lead_detail, name='crm_lead_detail'),
    path('crm/leads/<int:lead_id>/update-stage/', crm_views.crm_lead_update_stage, name='crm_lead_update_stage'),
    path('crm/leads/<int:lead_id>/update/', crm_views.crm_lead_update, name='crm_lead_update'),
    path('crm/leads/<int:lead_id>/add-activity/', crm_views.crm_lead_add_activity, name='crm_lead_add_activity'),
    path('crm/leads/<int:lead_id>/delete-activity/<int:activity_id>/', crm_views.crm_lead_delete_activity, name='crm_lead_delete_activity'),
    path('crm/leads/link-business/', crm_views.crm_lead_link_business, name='crm_lead_link_business'),
    path('crm/leads/<int:lead_id>/ai-summary/', crm_views.crm_lead_ai_summary, name='crm_lead_ai_summary'),
    path('crm/leads/<int:lead_id>/wa-media/<int:msg_id>/', crm_views.crm_lead_wa_media, name='crm_lead_wa_media'),
    path('crm/leads/<int:lead_id>/link-chat/', crm_views.crm_lead_link_chat, name='crm_lead_link_chat'),
    path('crm/wa-contacts/search/', crm_views.crm_wa_contact_search, name='crm_wa_contact_search'),
    path('crm/whatsapp-inbox/', crm_views.crm_whatsapp_inbox, name='crm_whatsapp_inbox'),
    path('crm/whatsapp-inbox/chat/', crm_views.crm_wa_chat_preview, name='crm_wa_chat_preview'),
    path('crm/wa-media/<int:msg_id>/', crm_views.crm_wa_media, name='crm_wa_media'),
    path('crm/whatsapp-inbox/promote/', crm_views.crm_wa_promote, name='crm_wa_promote'),
    path('crm/whatsapp-inbox/dismiss/', crm_views.crm_wa_dismiss, name='crm_wa_dismiss'),
    path('crm/whatsapp-inbox/resync/', crm_views.crm_wa_resync, name='crm_wa_resync'),
    path('crm/contacts/', crm_views.crm_contacts, name='crm_contacts'),
    path('crm/reports/', crm_views.crm_reports, name='crm_reports'),

    # Import History & Temp Orders
    path('import-history/', workforce_views.import_history, name='import_history'),
    path('orders/temp/config/', workforce_views.temp_order_config, name='temp_order_config'),
    path('orders/temp/', workforce_views.temp_orders, name='temp_orders'),
    path('orders/temp/by-date/', workforce_views.temp_orders_by_date, name='temp_orders_by_date'),
    path('orders/temp/browse/', workforce_views.temp_orders_browse, name='temp_orders_browse'),
    path('orders/temp/sync/', workforce_views.temp_orders_sync, name='temp_orders_sync'),
    path('orders/temp/preview/', workforce_views.temp_orders_preview, name='temp_orders_preview'),
    path('orders/temp/transfer/', workforce_views.temp_orders_transfer, name='temp_orders_transfer'),
    path('orders/temp/auto-import/', workforce_views.temp_orders_auto_import, name='temp_orders_auto_import'),
    path('orders/temp/auto-stages/', workforce_views.temp_auto_stages, name='temp_auto_stages'),
    path('orders/temp/auto-stages/save/', workforce_views.temp_auto_stages_save, name='temp_auto_stages_save'),
    path('orders/temp/auto-stages/get/', workforce_views.temp_auto_stages_get, name='temp_auto_stages_get'),
    path('orders/temp/verify-queue/', workforce_views.temp_verify_queue, name='temp_verify_queue'),
    path('orders/temp/verify-queue/<int:job_id>/action/', workforce_views.temp_verify_queue_action, name='temp_verify_queue_action'),
    path('orders/temp/verify-queue/toggle-messaging/', workforce_views.temp_verify_queue_toggle_messaging, name='temp_verify_queue_toggle_messaging'),
    path('orders/temp/delete/', workforce_views.temp_orders_delete, name='temp_orders_delete'),
    path('orders/temp/mark-imported/', workforce_views.temp_orders_mark_imported, name='temp_orders_mark_imported'),
    path('orders/temp/resync/', workforce_views.temp_orders_resync, name='temp_orders_resync'),
    path('orders/<int:order_id>/autoflow-status/', workforce_views.order_autoflow_status, name='order_autoflow_status'),
    path('orders/temp/public-links/', workforce_views.public_link_sources, name='public_link_sources'),
    path('public-link-sources/', workforce_views.public_link_sources_page, name='public_link_sources_page'),
    path('orders/temp/public-links/<int:source_id>/delete/', workforce_views.public_link_source_delete, name='public_link_source_delete'),
    path('orders/temp/public-links/<int:source_id>/save-mapping/', workforce_views.public_link_save_mapping, name='public_link_save_mapping'),

    # Google Sheet Import Sources (UI parallel to OneDrive)
    path('google-sheet-sources/', workforce_views.google_sheet_sources, name='google_sheet_sources'),

    # OneDrive Import Sources
    path('onedrive-sources/', workforce_views.onedrive_sources, name='onedrive_sources'),
    path('onedrive-sources/<int:source_id>/sheets/', workforce_views.onedrive_fetch_sheets, name='onedrive_fetch_sheets'),
    path('onedrive-sources/<int:source_id>/preview/', workforce_views.onedrive_sheet_preview, name='onedrive_sheet_preview'),
    path('onedrive-sources/<int:source_id>/save-mapping/', workforce_views.onedrive_save_mapping, name='onedrive_save_mapping'),
    path('onedrive-sources/<int:source_id>/import/', workforce_views.onedrive_import_trigger, name='onedrive_import_trigger'),

    # Hub Operations
    path('hub/batches/', workforce_views.hub_batch_list, name='hub_batch_list'),
    path('hub/batches/create/', workforce_views.hub_batch_create, name='hub_batch_create'),
    path('hub/batches/<int:batch_id>/', workforce_views.hub_batch_detail, name='hub_batch_detail'),
    path('hub/batches/<int:batch_id>/assign-driver/', workforce_views.hub_batch_assign_driver, name='hub_batch_assign_driver'),
    path('hub/batches/<int:batch_id>/update-status/', workforce_views.hub_batch_update_status, name='hub_batch_update_status'),

    # Export
    path('export/', workforce_views.wf_export_page, name='wf_export_page'),
    path('dl-tasks/export/', workforce_views.dl_tasks_export_page, name='dl_tasks_export_page'),
    path('export/api/', workforce_views.wf_export_api, name='wf_export_api'),
    path('export/api/selected/', workforce_views.wf_export_selected, name='wf_export_selected'),

    # Auto Triggers
    path('auto-triggers/', workforce_views.auto_triggers_list, name='auto_triggers_list'),
    path('auto-triggers/toggle/', workforce_views.auto_trigger_toggle, name='auto_trigger_toggle'),
    path('auto-triggers/update/', workforce_views.auto_trigger_update, name='auto_trigger_update'),
    path('auto-triggers/flows/', workforce_views.auto_flows_list, name='auto_flows_list'),
    path('auto-triggers/flows/add/', workforce_views.auto_flow_add, name='auto_flow_add'),
    path('auto-triggers/flows/<int:flow_id>/edit/', workforce_views.auto_flow_edit, name='auto_flow_edit'),
    path('auto-triggers/flows/toggle/', workforce_views.auto_flow_toggle, name='auto_flow_toggle'),
    path('auto-triggers/flows/delete/', workforce_views.auto_flow_delete, name='auto_flow_delete'),
    path('auto-triggers/flows/test/', workforce_views.auto_flow_test, name='auto_flow_test'),
    path('auto-triggers/flows/<int:flow_id>/logs/', workforce_views.auto_flow_logs, name='auto_flow_logs'),

    # AI Agent Configuration
    path('auto-triggers/ai-config/', workforce_views.wf_ai_config, name='wf_ai_config'),
    path('auto-triggers/ai-config/models/', workforce_views.wf_ai_models_api, name='wf_ai_models_api'),

    # WhatsApp Instances
    path('auto-triggers/whatsapp-instances/', workforce_views.whatsapp_instances_list, name='whatsapp_instances_list'),
    path('auto-triggers/sender-routes/', workforce_views.whatsapp_sender_routes_save, name='whatsapp_sender_routes_save'),
    path('auto-triggers/sender-routes/toggle/', workforce_views.whatsapp_sender_route_toggle, name='whatsapp_sender_route_toggle'),
    path('whatsapp/get-instances/', workforce_views.whatsapp_get_instances, name='whatsapp_get_instances'),
    path('whatsapp/last-message/', workforce_views.whatsapp_last_message, name='whatsapp_last_message'),
    path('whatsapp/send-message/', workforce_views.whatsapp_send_message, name='whatsapp_send_message'),

]
