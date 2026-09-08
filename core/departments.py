"""
Purpose: Department sub-roles for staff, and the map of every workforce URL name to the departments allowed to open it.
Used by: core.decorators.department_required, core.middleware.StaffDepartmentMiddleware, workforce.context_processors.workforce_departments
Notes: Departments sit UNDER Profile.is_staff — is_staff says "staff at all", these say "which desk". Super admins bypass every check. Unmapped URL names fail closed; workforce.tests_departments asserts the map covers all of workforce/urls.py, so a new route must be classified here before it ships.
"""

# --- Department codes -------------------------------------------------------
# Kept short because they are stored on Profile as booleans named dept_<code>.
OPS = 'ops'
FIN = 'fin'
MKT = 'mkt'
ADMIN = 'admin'

# Pseudo-department: routes every staff user may open regardless of desk.
SHARED = 'shared'

DEPARTMENT_CHOICES = [
    (OPS, 'Operations'),
    (FIN, 'Finance'),
    (MKT, 'Marketing'),
    (ADMIN, 'Super Admin'),
]

# Departments a user can be *assigned*. ADMIN is not here: it comes from
# Profile.is_superadmin, which already exists and already means "everything".
ASSIGNABLE_DEPARTMENTS = [OPS, FIN, MKT]

# Profile boolean field name for each assignable department.
DEPARTMENT_FIELDS = {
    OPS: 'dept_operations',
    FIN: 'dept_finance',
    MKT: 'dept_marketing',
}


# --- URL name -> departments ------------------------------------------------
# Grouped exactly like .claude/docs/09-workforce-fleet/staff-url-departments.md
# so the doc and the code can be diffed by eye.

_SHARED = [
    # Landing + docs
    'wf_dashboard', 'page_notes', 'workflow_guide', 'wf_orders_api_guide',
    # AJAX helpers called from pages in several departments. Gating these
    # would break driver pickers / zone lookups on other desks' screens.
    'api_drivers_list', 'get_active_drivers', 'api_warehouse_locations',
    'ajax_zone_name', 'resolve_location_link', 'get_pickup_locations',
]

_OPS = [
    # Orders
    'wf_orders_add', 'wf_orders_all', 'wf_orders_by_seller', 'wf_orders_to_publish',
    'wf_orders_published', 'wf_orders_reported', 'wf_orders_fulfilled_clients',
    'wf_orders_non_fulfilled_clients', 'orders_pending_verification', 'verify_order_address',
    'order_detail', 'order_edit', 'order_item_add', 'order_item_update', 'order_item_delete',
    'cancel_order', 'duplicate_order', 'partial_return_order', 'delete_order',
    'publish_order_to_delivery', 'update_order_status', 'bulk_update_order_status',
    'add_order_comment', 'update_order_coords', 'update_order_zone', 'assign_driver_to_order',
    'submit_to_task', 'order_autoflow_status',
    # Customer delivery comms (not marketing — these are order notifications)
    'order_whatsapp_defaults', 'send_order_whatsapp',
    'wf_orders_print_labels', 'wf_print_waybill', 'export_orders_csv',

    # Deliveries / tasks
    'dl_list_all', 'dl_list_fulfilled_clients', 'dl_list_non_fulfilled_clients',
    'dl_list_ready_to_published_to_dms', 'dl_list_published_to_dms', 'dl_list_incompleted_details',
    'tasks_followup_list', 'tasks_upcoming_list', 'tasks_reported', 'tasks_live_map',
    'delivery_task_detail', 'delivery_task_edit',
    'publish_task_to_fleets', 'unpublish_task_from_fleets',
    'assign_driver_to_task', 'unassign_driver_from_task', 'update_task_status',
    'bulk_print_tasks', 'bulk_print_waybills', 'bulk_publish_fleets', 'bulk_publish_app',
    'bulk_update_status', 'bulk_export_tasks', 'bulk_assign_driver', 'dl_tasks_export_page',
    'export_dl_tasks_sheet_csv', 'dl_tasks_print_sheet',

    # First-mile pickup + hub
    'pickup_pool_status', 'pickup_staff_assign', 'pickup_staff_unassign',
    'pickup_staff_cancel', 'pickup_staff_delete',
    'pickup_automation_list', 'pickup_automation_save',
    'pickup_fleet_list', 'pickup_fleet_driver_search', 'pickup_fleet_update',
    'hub_batch_list', 'hub_batch_create', 'hub_batch_detail',
    'hub_batch_assign_driver', 'hub_batch_update_status',

    # Dispatch & batching (config lives under ADMIN)
    'dispatch_dashboard', 'dispatch_batch_list', 'dispatch_batch_detail',
    'dispatch_release_batch', 'dispatch_cancel_batch',
    'dispatch_shift_list', 'dispatch_shift_create', 'dispatch_shift_detail', 'dispatch_shift_edit',
    'dispatch_kpi_dashboard', 'dispatch_rider_kpi',
    'dispatch_batch_monitor_partial', 'dispatch_shift_status_partial',

    # Drivers
    'drivers_list', 'drivers_pending', 'drivers_active', 'drivers_inactive', 'driver_detail',
    'driver_toggle_status', 'driver_set_status', 'driver_set_work_pref',
    'driver_vehicle_add', 'driver_vehicle_edit', 'driver_vehicle_delete',
    'driver_document_add', 'driver_document_edit', 'driver_document_delete',
    'driver_remind_completion', 'export_drivers_csv', 'wf_driver_tasks',

    # Sellers (account operations; sellers_pending is shared with MKT below)
    'sellers_list', 'sellers_active', 'sellers_inactive', 'seller_detail',
    'seller_doc_field_update', 'seller_api_products', 'seller_api_products_import',
    'seller_api_orders', 'seller_team_member_detail', 'seller_team_member_update',
    'wf_pickup_location_add', 'wf_pickup_location_update', 'wf_pickup_location_delete',

    # Verification & documents
    'business_verification_list', 'driver_verification_list', 'user_verification_list',
    'export_driver_verification_csv',
    'team_verification_list', 'update_verification_status', 'update_team_status',
    'view_user_driver_profile', 'view_user_business_profile', 'check_business_code_unique',
    'driver_documents_list', 'driver_document_detail',
    'vehicle_documents_list', 'vehicle_document_detail',
    'store_documents_list', 'store_document_detail',
    'business_licenses_list', 'business_license_detail', 'workforce_pickup_location_add',

    # Warehouse, inventory, fulfillment
    'warehouses_list', 'warehouse_link_business', 'warehouse_unlink_business',
    'inventory_reports', 'inventory_restock_list', 'suppliers_list', 'fulfilled_orders_list',
    'product_requests_list', 'approve_product_request', 'complete_product_request',

    # Location review & tools
    'delivery_location_reviews', 'delivery_location_review_action',
    'qnas_lookup_tool', 'qnas_test',

    # Import execution (configuring the sources is ADMIN)
    'wf_orders_bulk_import', 'wf_orders_bulk_preview', 'wf_orders_bulk_save',
    'wf_orders_bulk_save_mapping', 'wf_orders_bulk_finalize',
    'import_wizard_prepare', 'import_wizard', 'import_wizard_preview',
    'import_wizard_confirm', 'import_wizard_save_mapping',
    'wf_api_orders', 'bulk_transfer_api_orders', 'import_api_orders', 'preview_api_import',
    'temp_orders', 'temp_orders_by_date', 'temp_orders_browse', 'temp_orders_preview',
    'temp_orders_sync', 'temp_orders_resync', 'temp_orders_transfer', 'temp_orders_auto_import',
    'temp_verify_queue', 'temp_verify_queue_action', 'temp_verify_queue_toggle_messaging',
    'temp_orders_delete', 'temp_orders_mark_imported',
    # Read-only stage defaults for the Auto-Import modal on the temp-orders page.
    # Editing the defaults stays ADMIN (temp_auto_stages / _save); ops only reads
    # them to pre-tick the checkboxes, and blocking it hangs the modal.
    'temp_auto_stages_get',
    'import_history', 'onedrive_import_trigger',

    # Reports & export
    'staff_reports', 'wf_export_page', 'wf_export_api', 'wf_export_selected',
    'fleet_task_sheets_list', 'fleet_task_sheet',
]

_FIN = [
    'workforce_finance_dashboard',
    # COD position & ledger
    'fleet_cod_in_hand', 'cod_ledger', 'cod_legacy_reconciliation',
    'process_cod_return', 'fleet_task_cod_correct', 'recalculate_cod_balances',
    'fleet_task_cod_reconcile',
    # Transactions
    'fleet_transactions', 'seller_transactions', 'bulk_settle_transactions',
    'fleet_transaction_cod_details', 'fleet_transaction_update_status',
    'mark_prepaid_settled',
    # Driver leg
    'fleet_drivers_earnings', 'earnings_verification', 'earnings_verification_action',
    'driver_payout_worksheet', 'driver_payout_create', 'driver_payout_invoice',
    # Client leg
    'client_charge_verification', 'client_charge_verification_action',
    # Business -> Ezzy receivable (charges to collect)
    'client_charges_collect', 'client_charge_invoice_create',
    'client_charge_invoices', 'client_charge_invoice_detail',
    'client_charge_invoice_payment', 'client_charge_invoice_void',
    'client_charge_invoice_whatsapp',
    # Driver -> Ezzy settlement
    'cod_settlement_report', 'cod_settlement_action', 'cod_settlement_pdf',
    # Ezzy -> Business payout (Leg 3)
    'cod_business_settlement_report', 'cod_business_settlement_action',
    'cod_business_settlement_reverse', 'cod_business_settlement_pdf',
    'cod_business_payout_history', 'cod_business_payout_invoice',
    # Driver COD submissions
    'staff_cod_submissions', 'staff_cod_submission_edit', 'staff_cod_submission_add_task',
    'staff_cod_submission_remove_task', 'staff_cod_submission_approve',
    # Receipts & templates
    'settlement_receipt_print', 'receipt_templates_list', 'receipt_template_create',
    'receipt_template_edit', 'receipt_template_preview', 'receipt_template_delete',
]

_MKT = [
    # CRM pipeline
    'crm_leads_board', 'crm_driver_leads_board', 'crm_leads_list', 'crm_lead_create',
    'crm_lead_detail', 'crm_lead_update', 'crm_lead_update_stage', 'crm_lead_unpin_stage',
    'crm_lead_add_activity', 'crm_lead_delete_activity', 'crm_lead_link_business',
    'crm_lead_ai_summary',
    # CRM WhatsApp
    'crm_lead_link_chat', 'crm_lead_wa_media', 'crm_wa_contact_search',
    'crm_whatsapp_inbox', 'crm_wa_chat_preview', 'crm_wa_media',
    'crm_wa_promote', 'crm_wa_dismiss', 'crm_wa_resync',
    'crm_contacts', 'crm_reports',
    # CRM board column configuration
    'crm_stages_manage', 'crm_stage_save', 'crm_stage_delete', 'crm_stage_reorder',
    # Inbound forms
    'pricing_inquiries_list', 'pricing_inquiry_detail', 'pricing_inquiry_update_status',
    'pricing_inquiry_edit', 'pricing_inquiry_add_activity', 'pricing_inquiry_delete_activity',
    # Outbound comms
    'whatsapp_send_message', 'whatsapp_last_message',
]

_ADMIN = [
    # Staff role management — who holds which department, and which pages sit where
    'staff_roles_list', 'staff_role_update',
    'staff_pages_list', 'staff_page_update',
    # Automation (the Auto Triggers catalogue itself is multi-desk — see _MULTI)
    'auto_flows_list', 'auto_flow_add', 'auto_flow_edit', 'auto_flow_toggle',
    'auto_flow_delete', 'auto_flow_test', 'auto_flow_logs',
    # AI gateway
    'wf_ai_config', 'wf_ai_models_api', 'wf_ai_config_test',
    # WhatsApp infrastructure (the sender routes are per-desk — see _MULTI)
    'whatsapp_instances_list', 'whatsapp_get_instances',
    # Seller integrations & secrets
    'wf_seller_api_configs', 'wf_approve_api_config', 'wf_get_api_config',
    'wf_update_api_config', 'wf_delete_api_config', 'wf_test_api_config',
    'wf_test_api_config_result', 'wf_save_google_sheet',
    'google_sheets_auth_start', 'google_sheets_auth_callback',
    'wf_webhook_imports', 'wf_webhook_generate_key',
    # Import mapping & column config
    'wf_mapping_manager', 'wf_mapping_manager_save', 'wf_mapping_manager_test',
    'wf_sheet_headers', 'wf_sheet_worksheets', 'wf_sheet_save_tab',
    'wf_source_headers', 'wf_upload_sample_headers', 'wf_save_column_mapping',
    # Import sources
    'onedrive_sources', 'onedrive_fetch_sheets', 'onedrive_sheet_preview', 'onedrive_save_mapping',
    'google_sheet_sources',
    'public_link_sources', 'public_link_sources_page', 'public_link_source_delete',
    'public_link_save_mapping',
    'temp_order_config', 'temp_auto_stages', 'temp_auto_stages_save',
    # Dispatch config
    'dispatch_config_list', 'dispatch_config_edit',
]

# Routes belonging to more than one desk.
_MULTI = {
    # The pending-sellers queue is both an ops verification queue and the
    # acquisition team's funnel.
    'sellers_pending': [OPS, MKT],

    # Auto Triggers is a shared catalogue: every desk owns some of the rows
    # (AutoTriggerConfig.department / WhatsAppSenderRoute.SECTION_DEPARTMENTS).
    # The page and its write endpoints filter per-desk themselves, so opening
    # the URL to ops/fin/mkt does NOT expose another desk's triggers.
    'auto_triggers_list': [OPS, FIN, MKT, ADMIN],
    'auto_trigger_toggle': [OPS, FIN, MKT, ADMIN],
    'auto_trigger_update': [OPS, FIN, MKT, ADMIN],
    'whatsapp_sender_routes_save': [OPS, FIN, MKT, ADMIN],
    'whatsapp_sender_route_toggle': [OPS, FIN, MKT, ADMIN],

    # Shared composer behind the "Send from EZZY" button. Ops send it from
    # driver pages, marketing from lead and quote pages, so it belongs to both;
    # the number and channel come from the section route either way.
    'whatsapp_send_routed': [OPS, MKT, ADMIN],

    # The driver recruitment board is both desks' work: marketing sources and chases
    # applicants, operations makes the verification decision. Leaving these MKT-only
    # locked ops out of the board entirely, while still letting marketing reach the
    # stage endpoint that approves/rejects a real driver — the wrong way round.
    # crm_lead_update_stage re-checks for OPS before running any column write_back,
    # so opening the route does not hand marketing the verification decision.
    'crm_driver_leads_board': [OPS, MKT, ADMIN],
    'crm_leads_board': [OPS, MKT, ADMIN],
    'crm_leads_list': [OPS, MKT, ADMIN],
    'crm_lead_detail': [OPS, MKT, ADMIN],
    'crm_lead_update': [OPS, MKT, ADMIN],
    'crm_lead_update_stage': [OPS, MKT, ADMIN],
    'crm_lead_unpin_stage': [OPS, MKT, ADMIN],
    'crm_lead_merge': [OPS, MKT, ADMIN],
    'crm_lead_unmerge': [OPS, MKT, ADMIN],
    'crm_lead_add_activity': [OPS, MKT, ADMIN],
    'crm_stages_manage': [OPS, MKT, ADMIN],
}


def _build_map():
    """Invert the grouped lists into {url_name: frozenset(departments)}."""
    mapping = {}
    for dept, names in ((SHARED, _SHARED), (OPS, _OPS), (FIN, _FIN), (MKT, _MKT), (ADMIN, _ADMIN)):
        for name in names:
            mapping.setdefault(name, set()).add(dept)
    for name, depts in _MULTI.items():
        mapping.setdefault(name, set()).update(depts)
    return {name: frozenset(depts) for name, depts in mapping.items()}


URL_DEPARTMENTS = _build_map()


# --- Editable overrides -----------------------------------------------------
# The map above is the shipped default. Super admins can move a page to another
# desk, switch it off, or classify a route that has none, from
# /workforce/staff-pages/. Those changes live in core.models.PageDepartment and
# win over the defaults. Absent row == use the default.

OVERRIDE_CACHE_KEY = 'core.departments.overrides.v1'
OVERRIDE_CACHE_TTL = 600  # invalidated on write, so this is only a safety net


def _load_overrides():
    """
    {url_name: {'departments': frozenset, 'enabled': bool}} from the database.

    Returns {} if the table is not ready (fresh checkout, mid-migration) so the
    middleware keeps working off the code map instead of erroring on every
    request.
    """
    from django.core.cache import cache

    cached = cache.get(OVERRIDE_CACHE_KEY)
    if cached is not None:
        return cached

    try:
        from core.models import PageDepartment
        rows = {
            row.url_name: {
                'departments': frozenset(row.department_set),
                'enabled': row.is_enabled,
            }
            for row in PageDepartment.objects.all()
        }
    except Exception:
        return {}

    cache.set(OVERRIDE_CACHE_KEY, rows, OVERRIDE_CACHE_TTL)
    return rows


def clear_override_cache():
    """Called from the PageDepartment save/delete signal."""
    from django.core.cache import cache
    cache.delete(OVERRIDE_CACHE_KEY)


def effective_map():
    """
    The map actually in force: code defaults with database overrides applied.

    An override with no departments is a deliberate "assigned to nobody", which
    is different from an unclassified route — it still appears in the console.
    """
    merged = dict(URL_DEPARTMENTS)
    for url_name, row in _load_overrides().items():
        merged[url_name] = row['departments']
    return merged


def departments_for(url_name):
    """Departments allowed to open `url_name`, or None if it is unclassified."""
    override = _load_overrides().get(url_name)
    if override is not None:
        return override['departments']
    return URL_DEPARTMENTS.get(url_name)


def is_route_enabled(url_name):
    """False only when a super admin has explicitly switched the page off."""
    override = _load_overrides().get(url_name)
    return True if override is None else override['enabled']


def is_overridden(url_name):
    """True if this route's assignment has been changed from the code default."""
    return url_name in _load_overrides()


# Namespaces the middleware gates fail-closed. Routes in any OTHER namespace are
# only enforced when a super admin has explicitly classified them, so classifying
# a page elsewhere is opt-in and can never silently lock an app nobody gated.
GATED_NAMESPACES = ('workforce',)

# Namespaces offered in the "not listed" picker — staff-facing trees only.
ASSIGNABLE_NAMESPACES = ('workforce', 'warehouse')


def discover_routes(namespaces=ASSIGNABLE_NAMESPACES):
    """
    Every registered route in the given namespaces.

    Returns [{'url_name', 'namespace', 'pattern'}] sorted by name. Used by the
    Staff Pages console to list what exists, including routes that have no
    department yet.
    """
    from django.urls import get_resolver

    resolver = get_resolver()
    found = []
    for namespace in namespaces:
        entry = resolver.namespace_dict.get(namespace)
        if not entry:
            continue
        sub = entry[1]
        for url_name, bits in sub.reverse_dict.items():
            if not isinstance(url_name, str):
                continue
            try:
                pattern = '/' + bits[0][0][0]
            except Exception:
                pattern = ''
            found.append({
                'url_name': url_name,
                'namespace': namespace,
                'pattern': pattern,
            })
    return sorted(found, key=lambda r: (r['namespace'], r['url_name']))


def user_departments(user):
    """
    Set of department codes this user holds.

    Super admins get every department plus ADMIN. Non-staff get an empty set —
    staff_required/the middleware handle the "not staff at all" case.
    """
    from core.decorators import is_superadmin

    if not getattr(user, 'is_authenticated', False):
        return set()
    if is_superadmin(user):
        return set(ASSIGNABLE_DEPARTMENTS) | {ADMIN}

    profile = getattr(user, 'profile', None)
    if not profile:
        return set()
    return {
        code for code, field in DEPARTMENT_FIELDS.items()
        if getattr(profile, field, False)
    }


def can_access(user, url_name):
    """
    True if `user` may open the workforce route called `url_name`.

    Fails closed on unknown route names: a route that nobody classified is
    treated as restricted rather than public. A page switched off is closed to
    everyone but super admins — otherwise nobody could switch it back on.
    """
    from core.decorators import is_superadmin

    if is_superadmin(user):
        return True

    if not is_route_enabled(url_name):
        return False

    required = departments_for(url_name)
    if required is None:
        return False
    if SHARED in required:
        return True
    return bool(required & user_departments(user))
