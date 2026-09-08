# Purpose: Classify every shipped auto trigger under the staff desk that owns it.
# Used by: core.models.AutoTriggerConfig.department (Auto Triggers page filters on it)
# Notes: Keys not listed here keep the model default 'admin' (super admin only), so an
#        unknown/new trigger is never exposed to a desk by accident. Reverse is a no-op.

from django.db import migrations


# trigger_key -> department code (core.departments)
TRIGGER_DEPARTMENTS = {
    # --- WhatsApp: customer delivery notifications -> Operations ---------
    'wa_delivered': 'ops',
    'wa_delivery_failed': 'ops',
    'wa_driver_assigned': 'ops',
    'wa_location_verification': 'ops',
    'wa_order_cancelled': 'ops',
    'wa_out_for_delivery': 'ops',

    # --- Webhooks -------------------------------------------------------
    'wh_cod_collected': 'fin',
    'wh_document_uploaded': 'ops',
    'wh_driver_location': 'ops',
    'wh_driver_status': 'ops',
    'wh_task_accepted': 'ops',
    'wh_task_completed': 'ops',
    'wh_task_rejected': 'ops',
    'wh_task_status_update': 'ops',

    # --- Staff actions --------------------------------------------------
    'staff_batch_created': 'ops',
    'staff_batch_dispatched': 'ops',
    'staff_cod_collected': 'fin',
    'staff_cod_settled': 'fin',
    'staff_earnings_approved': 'fin',
    'staff_driver_approved': 'ops',
    'staff_driver_rejected': 'ops',
    'staff_driver_suspended': 'ops',
    'staff_order_cancel': 'ops',
    'staff_order_create': 'ops',
    'staff_order_edit': 'ops',
    'staff_order_publish': 'ops',
    'staff_order_verify': 'ops',
    'staff_orders_imported': 'ops',
    'staff_task_assign_driver': 'ops',
    'staff_task_cancel': 'ops',
    'staff_task_publish': 'ops',
    'staff_task_reschedule': 'ops',
    'staff_task_status_change': 'ops',
    'staff_temp_orders_transferred': 'ops',

    # --- System auto-actions --------------------------------------------
    # Ops-facing mechanics (labels, driver comms, hub legs, GPS points).
    'sys_create_qr_code': 'ops',
    'sys_create_shipping_label': 'ops',
    'sys_driver_notification': 'ops',
    'sys_gps_status_points': 'ops',
    'sys_hub_delivery_tasks': 'ops',
    'sys_sync_driver_availability': 'ops',
    'sys_sync_order_status': 'ops',
    'sys_track_failed_attempts': 'ops',
    # Platform internals — switching these off changes how the app itself
    # behaves, so they stay on the admin desk.
    'sys_state_machine': 'admin',
    'sys_status_history': 'admin',
}


def set_departments(apps, schema_editor):
    AutoTriggerConfig = apps.get_model('core', 'AutoTriggerConfig')
    for key, dept in TRIGGER_DEPARTMENTS.items():
        AutoTriggerConfig.objects.filter(trigger_key=key).update(department=dept)


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0020_autotriggerconfig_department'),
    ]

    operations = [
        migrations.RunPython(set_departments, noop),
    ]
