# Staff Dashboard — URL Classification by Department

Purpose: Classify every `workforce/urls.py` route into a department so the staff dashboard can be split department-wise.
Used by: future `Profile.department` gating, `department_required` decorator, and sidebar section rendering.
Notes: Source of truth is `workforce/urls.py` (428 lines, ~330 routes) as of 2026-08-01. Names below are the `name=` values under the `workforce:` namespace.

## Departments

| Code | Name | Who it is |
|---|---|---|
| `ops` | Operations | Order intake → delivery completion, drivers, dispatch, warehouse, verification |
| `fin` | Finance | COD, settlements, payouts, transactions, earnings, invoices/receipts |
| `mkt` | Marketing | CRM leads, WhatsApp inbox, pricing inquiries, outbound comms |
| `admin` | Super Admin | Platform config: automation, AI, integrations, mapping, sources |
| `shared` | All staff | Landing + cross-cutting AJAX helpers every department needs |

**Rule:** a staff member gets one or more departments. `admin` implies access to everything. `shared` is granted to every staff user unconditionally.

---

## 1. SHARED — every staff user

These cannot be locked to one department: they are the landing page or AJAX helpers called from pages in several departments.

| URL name | Path | Note |
|---|---|---|
| `wf_dashboard` | `dashboard/` | Landing — tiles should filter by department |
| `page_notes` | `page-notes/<key>/` | Help panel |
| `workflow_guide` | `workflow-guide/` | Docs |
| `wf_orders_api_guide` | `orders/api-guide/` | Docs |
| `api_drivers_list` | `api/drivers-list/` | Used by orders, tasks, dispatch, hub, pickup |
| `get_active_drivers` | `api/get-active-drivers/` | Same |
| `api_warehouse_locations` | `api/warehouse-locations/` | Used by orders + warehouse |
| `ajax_zone_name` | `ajax/zone-name/` | Used by orders + tasks |
| `resolve_location_link` | `api/resolve-location/` | Used by orders + location review |
| `get_pickup_locations` | `orders/pickup-locations/<business_id>/` | Used by order add + import |

---

## 2. OPERATIONS (`ops`)

### 2.1 Orders
| URL name | Path |
|---|---|
| `wf_orders_add` | `orders/add/` |
| `wf_orders_all` | `orders/all/` |
| `wf_orders_by_seller` | `orders/by-seller/` |
| `wf_orders_to_publish` | `orders/to_publish/` |
| `wf_orders_published` | `orders/published/` |
| `wf_orders_reported` | `orders/reported/` |
| `wf_orders_fulfilled_clients` | `orders/fulfilled-clients/` |
| `wf_orders_non_fulfilled_clients` | `orders/non-fulfilled-clients/` |
| `orders_pending_verification` | `orders/pending-verification/` |
| `verify_order_address` | `orders/<id>/verify-address/` |
| `order_detail` | `orders/<id>/` |
| `order_edit` | `orders/<id>/edit/` |
| `order_item_add` / `order_item_update` / `order_item_delete` | `orders/<id>/items/...` |
| `cancel_order` / `duplicate_order` / `partial_return_order` / `delete_order` | `orders/<id>/...` |
| `publish_order_to_delivery` | `orders/<id>/publish/` |
| `update_order_status` | `orders/<id>/update-status/` |
| `bulk_update_order_status` | `orders/bulk-update-status/` |
| `add_order_comment` | `orders/<id>/add-comment/` |
| `update_order_coords` | `orders/<id>/update-coords/` |
| `update_order_zone` | `order/<id>/update-zone/` |
| `assign_driver_to_order` | `order/<id>/assign-driver/` |
| `submit_to_task` | `orders/submit_to_task/<id>/` |
| `order_autoflow_status` | `orders/<id>/autoflow-status/` |
| `order_whatsapp_defaults` | `orders/<id>/whatsapp-defaults/` |
| `send_order_whatsapp` | `orders/<id>/send-whatsapp/` |
| `wf_orders_print_labels` | `orders/print-labels/` |
| `wf_print_waybill` | `orders/print-waybill/` |
| `export_orders_csv` | `orders/export/` |

### 2.2 Deliveries / Tasks
| URL name | Path |
|---|---|
| `dl_list_all` | `tasks/dl_list_all/` |
| `dl_list_fulfilled_clients` / `dl_list_non_fulfilled_clients` | `tasks/...-clients/` |
| `dl_list_ready_to_published_to_dms` | `tasks/unpublished/` |
| `dl_list_published_to_dms` | `tasks/published/` |
| `dl_list_incompleted_details` | `tasks/dl_list_incompleted/` |
| `tasks_followup_list` | `tasks/followup-list/` |
| `tasks_reported` | `tasks/reported/` |
| `tasks_live_map` | `tasks/live-map/` |
| `delivery_task_detail` / `delivery_task_edit` | `delivery-task/<id>/...` |
| `publish_task_to_fleets` / `unpublish_task_from_fleets` | `delivery-task/<id>/...-fleets/` |
| `assign_driver_to_task` / `unassign_driver_from_task` | `delivery-task/<id>/...-driver/` |
| `update_task_status` | `delivery-task/<id>/update-status/` |
| `bulk_print_tasks` / `bulk_print_waybills` | `tasks/bulk-print/`, `tasks/print-waybills/` |
| `bulk_publish_fleets` / `bulk_publish_app` | `tasks/bulk-publish-.../` |
| `bulk_update_status` / `bulk_export_tasks` / `bulk_assign_driver` | `tasks/bulk-.../` |
| `dl_tasks_export_page` | `dl-tasks/export/` |

### 2.3 Pickup (first-mile) & Hub
| URL name | Path |
|---|---|
| `pickup_pool_status` | `pickups/` |
| `pickup_staff_assign` / `pickup_staff_unassign` | `pickups/...assign/` |
| `pickup_staff_cancel` / `pickup_staff_delete` | `pickups/cancel/`, `pickups/delete/` (delete is superadmin-only inside the view) |
| `pickup_automation_list` / `pickup_automation_save` | `pickup-automation/...` |
| `pickup_fleet_list` / `pickup_fleet_driver_search` / `pickup_fleet_update` | `pickup-automation/fleet/...` |
| `hub_batch_list` / `hub_batch_create` / `hub_batch_detail` | `hub/batches/...` |
| `hub_batch_assign_driver` / `hub_batch_update_status` | `hub/batches/<id>/...` |

### 2.4 Dispatch & Batching
| URL name | Path |
|---|---|
| `dispatch_dashboard` | `dispatch/` |
| `dispatch_batch_list` / `dispatch_batch_detail` | `dispatch/batches/...` |
| `dispatch_release_batch` / `dispatch_cancel_batch` | `dispatch/batches/<id>/...` |
| `dispatch_shift_list` / `dispatch_shift_create` / `dispatch_shift_detail` / `dispatch_shift_edit` | `dispatch/shifts/...` |
| `dispatch_kpi_dashboard` / `dispatch_rider_kpi` | `dispatch/kpis/...` |
| `dispatch_batch_monitor_partial` / `dispatch_shift_status_partial` | `dispatch/partials/...` |

> `dispatch_config_list` / `dispatch_config_edit` → **Super Admin** (see §5).

### 2.5 Drivers
| URL name | Path |
|---|---|
| `drivers_list` / `drivers_pending` / `drivers_active` / `drivers_inactive` | `drivers/...` |
| `driver_detail` | `drivers/<id>/` |
| `driver_toggle_status` / `driver_set_status` / `driver_set_work_pref` | `drivers/<id>/...` |
| `driver_vehicle_add` / `driver_vehicle_edit` / `driver_vehicle_delete` | `drivers/<id>/vehicle/...` |
| `driver_document_add` / `driver_document_edit` / `driver_document_delete` | `drivers/<id>/document/...` |
| `driver_remind_completion` | `drivers/<id>/remind-completion/` |
| `export_drivers_csv` | `drivers/export/` |
| `wf_driver_tasks` | `fleet/driver-tasks/` |

### 2.6 Sellers (account operations)
| URL name | Path |
|---|---|
| `sellers_list` / `sellers_pending` / `sellers_active` / `sellers_inactive` | `sellers/...` |
| `seller_detail` | `sellers/<id>/` |
| `seller_doc_field_update` | `sellers/<id>/doc-field/` |
| `seller_api_products` / `seller_api_products_import` / `seller_api_orders` | `sellers/<id>/api-.../` |
| `wf_pickup_location_add` / `wf_pickup_location_update` / `wf_pickup_location_delete` | `sellers/<id>/pickup-location/...` |

> `sellers_pending` is also a **Marketing** funnel view — grant read to `mkt` if the acquisition team works the pending queue.

### 2.7 Verification & Documents
| URL name | Path |
|---|---|
| `business_verification_list` / `driver_verification_list` / `user_verification_list` / `team_verification_list` | `verification/...` |
| `export_driver_verification_csv` | `verification/drivers/export/` |
| `update_verification_status` / `update_team_status` | `verification/.../update-status/` |
| `view_user_driver_profile` / `view_user_business_profile` | `verification/<id>/...-profile/` |
| `check_business_code_unique` | `verification/check-business-code/` |
| `driver_documents_list` / `driver_document_detail` | `documents/driver-ids/...` |
| `vehicle_documents_list` / `vehicle_document_detail` | `documents/vehicles/...` |
| `store_documents_list` / `store_document_detail` | `documents/stores/...` |
| `business_licenses_list` / `business_license_detail` | `documents/business-licenses/...` |
| `workforce_pickup_location_add` | `documents/business-licenses/<id>/add-pickup-location/` |

### 2.8 Warehouse, Inventory & Fulfillment
| URL name | Path |
|---|---|
| `warehouses_list` / `warehouse_link_business` / `warehouse_unlink_business` | `warehouses/...` |
| `inventory_reports` / `inventory_restock_list` | `inventory/...` |
| `suppliers_list` | `suppliers/` |
| `fulfilled_orders_list` | `purchase-orders/` |
| `product_requests_list` / `approve_product_request` / `complete_product_request` | `product-requests/...` |

### 2.9 Location & Tools
| URL name | Path |
|---|---|
| `delivery_location_reviews` / `delivery_location_review_action` | `fleet/location-reviews/...` |
| `qnas_lookup_tool` / `qnas_test` | `tools/qnas-.../` |

### 2.10 Import execution (running imports, not configuring them)
| URL name | Path |
|---|---|
| `wf_orders_bulk_import` / `wf_orders_bulk_preview` / `wf_orders_bulk_save` / `wf_orders_bulk_save_mapping` / `wf_orders_bulk_finalize` | `orders/bulk-import/...` |
| `import_wizard_prepare` / `import_wizard` / `import_wizard_preview` / `import_wizard_confirm` / `import_wizard_save_mapping` | `import-wizard/...` |
| `wf_api_orders` / `bulk_transfer_api_orders` / `import_api_orders` / `preview_api_import` | `orders/api-orders/...` |
| `temp_orders` / `temp_orders_by_date` / `temp_orders_browse` / `temp_orders_preview` | `orders/temp/...` |
| `temp_orders_sync` / `temp_orders_resync` / `temp_orders_transfer` / `temp_orders_auto_import` | `orders/temp/...` |
| `temp_verify_queue` / `temp_verify_queue_action` / `temp_verify_queue_toggle_messaging` | `orders/temp/verify-queue/...` |
| `temp_orders_delete` / `temp_orders_mark_imported` | `orders/temp/...` |
| `temp_auto_stages_get` | `orders/temp/auto-stages/get/` (read-only defaults for the Auto-Import modal) |
| `import_history` | `import-history/` |
| `onedrive_import_trigger` | `onedrive-sources/<id>/import/` |

### 2.11 Reports & Export
| URL name | Path |
|---|---|
| `staff_reports` | `reports/` |
| `wf_export_page` / `wf_export_api` / `wf_export_selected` | `export/...` |
| `fleet_task_sheets_list` / `fleet_task_sheet` | `fleet/task-sheet(s)/...` |

---

## 3. FINANCE (`fin`)

| URL name | Path | Group |
|---|---|---|
| `workforce_finance_dashboard` | `finance/` | Overview |
| `fleet_cod_in_hand` | `fleet/cod-in-hand/` | COD position |
| `cod_ledger` | `fleet/cod-ledger/` | Ledger |
| `cod_legacy_reconciliation` | `fleet/cod-legacy-reconciliation/` | Ledger |
| `process_cod_return` | `delivery-task/<id>/cod-return/` | COD movement |
| `fleet_task_cod_correct` | `fleet/tasks/<id>/cod-correct/` | COD movement |
| `fleet_task_cod_reconcile` | `fleet/tasks/<id>/cod-reconcile/` | COD movement |
| `recalculate_cod_balances` | `fleet/recalculate-cod-balances/` | COD movement |
| `fleet_transactions` | `fleet/transactions/` | Transactions |
| `seller_transactions` | `seller-transactions/` | Transactions |
| `bulk_settle_transactions` | `fleet/bulk-settle-transactions/` | Transactions |
| `fleet_transaction_cod_details` / `fleet_transaction_update_status` | `fleet/transactions/<id>/...` | Transactions |
| `fleet_drivers_earnings` | `fleet/drivers-earnings/` | Driver leg |
| `earnings_verification` / `earnings_verification_action` | `fleet/earnings-verification/...` | Driver leg |
| `driver_payout_worksheet` / `driver_payout_create` | `fleet/driver-payout/<id>/...` | Driver leg |
| `driver_payout_invoice` | `settlement/<id>/payout-invoice/` | Driver leg |
| `client_charge_verification` / `client_charge_verification_action` | `client-charges/...` | Client leg |
| `cod_settlement_report` / `cod_settlement_action` / `cod_settlement_pdf` | `fleet/cod-settlement/...` | Driver→Ezzy settlement |
| `cod_business_settlement_report` | `fleet/cod-business-settlement/` | Ezzy→Business payout |
| `cod_business_settlement_action` / `cod_business_settlement_reverse` | `fleet/cod-business-settlement/...` | Ezzy→Business payout |
| `cod_business_settlement_pdf` / `cod_business_payout_history` / `cod_business_payout_invoice` | `fleet/cod-business-settlement/...` | Ezzy→Business payout |
| `staff_cod_submissions` | `fleet/cod-submissions/` | Driver submissions |
| `staff_cod_submission_edit` / `..._add_task` / `..._remove_task` / `..._approve` | `fleet/cod-submissions/<code>/...` | Driver submissions |
| `settlement_receipt_print` | `settlement/<id>/receipt/` | Documents |
| `receipt_templates_list` / `receipt_template_create` / `receipt_template_edit` / `receipt_template_preview` / `receipt_template_delete` | `receipt-templates/...` | Documents |

---

## 4. MARKETING (`mkt`)

| URL name | Path | Group |
|---|---|---|
| `crm_leads_board` | `crm/leads/board/` | Pipeline |
| `crm_driver_leads_board` | `crm/leads/board/drivers/` | Pipeline |
| `crm_leads_list` | `crm/leads/` | Pipeline |
| `crm_lead_create` / `crm_lead_detail` / `crm_lead_update` | `crm/leads/...` | Pipeline |
| `crm_lead_update_stage` | `crm/leads/<id>/update-stage/` | Pipeline |
| `crm_lead_unpin_stage` | `crm/leads/<id>/unpin-stage/` | Pipeline |
| `crm_lead_merge` / `crm_lead_unmerge` | `crm/leads/<id>/merge/` `unmerge/` | Pipeline |
| `crm_lead_add_activity` / `crm_lead_delete_activity` | `crm/leads/<id>/...activity/` | Pipeline |
| `crm_lead_link_business` | `crm/leads/link-business/` | Conversion |
| `crm_lead_ai_summary` | `crm/leads/<id>/ai-summary/` | Pipeline |
| `crm_lead_link_chat` / `crm_lead_wa_media` | `crm/leads/<id>/...` | WhatsApp |
| `crm_wa_contact_search` | `crm/wa-contacts/search/` | WhatsApp |
| `crm_whatsapp_inbox` / `crm_wa_chat_preview` / `crm_wa_media` | `crm/whatsapp-inbox/...` | WhatsApp |
| `crm_wa_promote` / `crm_wa_dismiss` / `crm_wa_resync` | `crm/whatsapp-inbox/...` | WhatsApp |
| `crm_contacts` | `crm/contacts/` | Contacts |
| `crm_reports` | `crm/reports/` | Reporting |
| `crm_stages_manage` / `crm_stage_save` | `crm/stages/...` | Board columns |
| `crm_stage_delete` / `crm_stage_reorder` | `crm/stages/...` | Board columns |
| `pricing_inquiries_list` / `pricing_inquiry_detail` | `forms/pricing-inquiries/...` | Inbound forms |
| `pricing_inquiry_update_status` / `pricing_inquiry_edit` | `forms/pricing-inquiries/<id>/...` | Inbound forms |
| `pricing_inquiry_add_activity` / `pricing_inquiry_delete_activity` | `forms/pricing-inquiries/<id>/...` | Inbound forms |
| `whatsapp_send_message` | `whatsapp/send-message/` | Outbound |
| `whatsapp_last_message` | `whatsapp/last-message/` | Outbound |

---

## 5. SUPER ADMIN (`admin`)

Platform configuration. Wrong values here break every department, so keep this locked to `superadmin_required`.

| URL name | Path | Group |
|---|---|---|
| `staff_roles_list` / `staff_role_update` | `staff-roles/...` | Staff roles |
| `auto_flows_list` / `auto_flow_add` / `auto_flow_edit` | `auto-triggers/flows/...` | Automation |
| `auto_flow_toggle` / `auto_flow_delete` / `auto_flow_test` / `auto_flow_logs` | `auto-triggers/flows/...` | Automation |
| `wf_ai_config` / `wf_ai_models_api` / `wf_ai_config_test` | `auto-triggers/ai-config/...` | AI gateway |
| `whatsapp_instances_list` | `auto-triggers/whatsapp-instances/` | WhatsApp infra |
| `whatsapp_get_instances` | `whatsapp/get-instances/` | WhatsApp infra |
| `wf_seller_api_configs` | `sellers/api-configs/` | Integrations |
| `wf_approve_api_config` / `wf_get_api_config` / `wf_update_api_config` / `wf_delete_api_config` | `sellers/api-configs/<id>/...` | Integrations |
| `wf_test_api_config` / `wf_test_api_config_result` | `sellers/api-configs/<id>/test/...` | Integrations |
| `wf_save_google_sheet` | `sellers/api-configs/google-sheet/save/` | Integrations |
| `google_sheets_auth_start` / `google_sheets_auth_callback` | `google-sheets/auth/...` | Integrations (OAuth) |
| `wf_webhook_imports` / `wf_webhook_generate_key` | `webhook-imports/...` | Integrations (secrets) |
| `wf_mapping_manager` / `wf_mapping_manager_save` / `wf_mapping_manager_test` | `import-wizard/mapping-manager/...` | Import config |
| `wf_sheet_headers` / `wf_sheet_worksheets` / `wf_sheet_save_tab` | `orders/api-orders/sheet-.../` | Import config |
| `wf_source_headers` / `wf_upload_sample_headers` / `wf_save_column_mapping` | `orders/api-orders/...` | Import config |
| `onedrive_sources` / `onedrive_fetch_sheets` / `onedrive_sheet_preview` / `onedrive_save_mapping` | `onedrive-sources/...` | Import sources |
| `google_sheet_sources` | `google-sheet-sources/` | Import sources |
| `public_link_sources` / `public_link_sources_page` / `public_link_source_delete` / `public_link_save_mapping` | `orders/temp/public-links/...`, `public-link-sources/` | Import sources |
| `temp_order_config` | `orders/temp/config/` | Import config |
| `temp_auto_stages` / `temp_auto_stages_save` | `orders/temp/auto-stages/`, `orders/temp/auto-stages/save/` | Import config (read helper `temp_auto_stages_get` is OPS — the Auto-Import modal needs it) |
| `dispatch_config_list` / `dispatch_config_edit` | `dispatch/config/...` | Dispatch config |

---

## How it is enforced (built 2026-08-01)

| Piece | Where |
|---|---|
| Department codes + the URL map | `core/departments.py` (`URL_DEPARTMENTS`) |
| Sub-role fields on the profile | `Profile.dept_operations` / `dept_finance` / `dept_marketing` (+ existing `is_superadmin`) |
| Whole-tree gate for `/workforce/` | `core.middleware.StaffDepartmentMiddleware` (`process_view`) |
| Explicit gate for views elsewhere | `core.decorators.department_required(FIN)` |
| Sidebar + dashboard visibility | `workforce.context_processors.workforce_departments` → `wf_dept_ops/fin/mkt/admin` |
| Assigning departments to people | `/workforce/staff-roles/` (super admin only) |
| Assigning pages to departments | `/workforce/staff-pages/` (super admin only) |
| Runtime overrides of this map | `core.models.PageDepartment` → `core.departments.effective_map()` |
| Completeness guard | `workforce/tests_departments.py::test_every_workforce_route_is_classified` |

### The map is editable at runtime

The tables in this document are the **shipped defaults**. A super admin can change them from
`/workforce/staff-pages/` without a deploy:

- **Move** a page to another desk (or to several desks at once).
- **Switch a page off** — blocked for everyone but super admins, who keep access so they can
  switch it back on.
- **Mark a page "All staff"** (the `shared` pseudo-department). Cannot be combined with a
  specific desk.
- **Classify a page that has no desk** — the "No desk" filter lists them.

Changes are stored in `PageDepartment` as *overrides only*: setting a page back to its shipped
default deletes the row rather than storing a no-op, so the code map stays the readable source of
truth and the table stays small. The cached map is dropped on every write
(`core/department_signals.py`), so an edit applies on the next request.

Routes **outside** `/workforce/` (e.g. the `warehouse:` tree) are listed in the console and can be
classified, but are only enforced once explicitly classified — opt-in, so no app that was never
gated gets locked down by accident. This is how the warehouse gap noted below can be closed.

Rules the implementation follows:

1. **`is_staff` still decides entry.** Departments are a second question asked only of staff.
   The middleware never widens access — a non-staff user is still rejected by `@staff_required`.
2. **Super admins bypass departments** and hold all of them for display purposes.
3. **Unclassified routes fail closed.** A new URL with no entry in `URL_DEPARTMENTS` is refused
   and logged at ERROR. The completeness test turns that into a CI failure instead of a
   production surprise, so **any new workforce URL must be added to `core/departments.py`**.
4. **Existing staff were backfilled** with all three departments in migration `core.0017`, so the
   deploy changed nobody's access. Narrowing is done from the Staff Roles page.
5. **A staff user with no department** can still reach the SHARED routes (dashboard, help, AJAX
   pickers) and is told to ask an admin. The Staff Roles page flags them as "No desk".

Known gap: the `warehouse:` app tree (`/warehouse/...`) is not gated by default — its sidebar links
are hidden for non-Operations staff, but the URLs remain reachable by typing them. Closing it is now
a UI action rather than a code change: classify those routes on `/workforce/staff-pages/`.

## 6. MULTI-DESK (`ops` + `fin` + `mkt` + `admin`)

Routes every desk opens, where the *view* — not the URL map — decides which rows the
viewer may see. Never widen this list without a per-row filter behind it.

| URL name | Path | How the split is enforced |
|---|---|---|
| `auto_triggers_list` | `auto-triggers/` | Rows filtered by `AutoTriggerConfig.department`; department tabs on the page |
| `auto_trigger_toggle` / `auto_trigger_update` | `auto-triggers/toggle/`, `auto-triggers/update/` | 403 unless `trigger.department` is one the caller holds |
| `whatsapp_sender_routes_save` / `whatsapp_sender_route_toggle` | `auto-triggers/sender-routes/...` | 403 unless `WhatsAppSenderRoute.SECTION_DEPARTMENTS[section]` is one the caller holds |

A trigger with no explicit department stays `admin`, so a newly added trigger is
never exposed to a desk by accident. Classify it in `core/models.py`
(`AutoTriggerConfig.DEPARTMENT_CHOICES`) plus a data migration, the same way
`core/migrations/0021_autotriggerconfig_department_data.py` did.

The rest of the Auto Triggers submenu (Flows, WA Instances, AI Config, API
Configs, Webhook Imports) remains super-admin only — only the catalogue page is
shared.

## Judgement calls worth confirming

1. **`sellers_pending`** — listed under Operations, but it is the acquisition funnel. Likely needs `ops + mkt`.
2. **`process_cod_return`** — sits on the delivery-task detail page (an Operations screen) but moves money. Classified Finance; if ops staff must click it, grant `fin` read on that one endpoint.
3. **`send_order_whatsapp` / `order_whatsapp_defaults`** — customer delivery comms, so Operations, not Marketing. The Marketing WhatsApp routes are the CRM inbox and the generic sender.
4. **`pickup_automation_*`** — configuration screens, but ops staff run them daily. Kept in Operations.
5. **`staff_reports` / `wf_export_*`** — a single reports page spanning all departments. Either keep it `shared` or filter the report list by department inside the view.
6. **AJAX helpers in §1** must stay `shared` or department gating will break pages in other departments (driver pickers, zone lookup, warehouse pickers).
