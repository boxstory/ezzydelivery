"""
Auto Flow Executor
==================
Fires all enabled AutoFlows matching a given trigger_key.
For whatsapp_message actions, sends via Evolution API.
"""
import logging
import time
import os
import requests
from django.conf import settings

logger = logging.getLogger(__name__)


def _render_template(template, context):
    """Replace {variable} placeholders with context values."""
    result = template
    for key, value in context.items():
        result = result.replace('{' + key + '}', str(value) if value else '')
    return result


def _build_context_from_task(task):
    """Build variable context dict from a DeliveryTask."""
    ctx = {
        'task_number': task.dl_task_number or '',
        'task_status': task.dl_task_status or '',
        'delivery_date': str(task.dl_task_date) if task.dl_task_date else '',
    }
    if task.order:
        order = task.order
        ctx.update({
            'order_number': order.order_number or '',
            'customer_name': order.customer_name or '',
            'customer_phone': order.customer_phone or '',
            'customer_address': order.customer_address or '',
            'cod_amount': str(order.cod_amount) if order.cod_amount else '0',
            'zone': str(order.dl_zone) if order.dl_zone else '',
            'business_name': str(order.business) if order.business else '',
        })
    if task.driver:
        ctx.update({
            'driver_name': task.driver.driver_name or '',
            'driver_phone': task.driver.driver_phone or '',
        })
    else:
        ctx.update({'driver_name': '', 'driver_phone': ''})
    return ctx


def _check_trigger_conditions(flow, context, task=None):
    """Check if trigger conditions are met. Returns (passed, reason)."""
    config = flow.action_config or {}
    conditions = config.get('trigger_conditions', {})
    if not conditions:
        return True, ''

    # Business filter
    biz_id = conditions.get('business_id')
    if biz_id and task and task.order and str(task.order.business_id) != str(biz_id):
        return False, f"Business mismatch (expected {biz_id})"

    # Status filter
    on_status = conditions.get('trigger_on_status')
    if on_status and task and task.dl_task_status != on_status:
        return False, f"Status mismatch (expected {on_status}, got {task.dl_task_status})"

    return True, ''


def _send_whatsapp(phone, message, is_group=False, instance_override=None):
    """Send WhatsApp message via Evolution API. Returns (success, detail)."""
    evo_url = getattr(settings, 'EVALUATION_URL', '') or os.environ.get('EVALUATION_URL', '')
    evo_key = getattr(settings, 'EVALUATION_API_KEY', '') or os.environ.get('EVALUATION_API_KEY', '')

    # Resolve instance: flow override > WhatsAppInstance default > settings
    evo_instance = instance_override
    if not evo_instance:
        try:
            from core.models import WhatsAppInstance
            default_inst = WhatsAppInstance.objects.filter(is_active=True, is_default=True).first()
            if default_inst:
                evo_instance = default_inst.instance_name
        except Exception:
            pass
    if not evo_instance:
        evo_instance = getattr(settings, 'EVALUATION_INSTANCE', '') or os.environ.get('EVALUATION_INSTANCE', '')

    if not evo_url or not evo_key or not evo_instance:
        return False, "Evolution API not configured"

    evo_url = evo_url.rstrip('/')
    payload = {'number': phone, 'text': message}

    try:
        resp = requests.post(
            f"{evo_url}/message/sendText/{evo_instance}",
            headers={'apikey': evo_key, 'Content-Type': 'application/json'},
            json=payload,
            timeout=15,
        )
        if resp.status_code in (200, 201):
            data = resp.json()
            msg_id = data.get('key', {}).get('id', 'N/A')
            return True, f"Sent (ID: {msg_id})"
        else:
            return False, f"API {resp.status_code}: {resp.text[:200]}"
    except requests.RequestException as e:
        return False, f"Request failed: {e}"


def _resolve_recipient_phones(flow, task=None):
    """Resolve recipient type to list of phone numbers."""
    config = flow.action_config or {}
    recipient = config.get('recipient', 'customer')
    phones = []

    if recipient == 'custom':
        phone = config.get('custom_phone', '').strip()
        if phone:
            phones.append(phone)

    elif recipient == 'custom_group':
        group_id = config.get('group_id', '').strip()
        if group_id:
            phones.append(group_id)

    elif recipient in ('customer', 'customer_whatsapp'):
        if task and task.order and task.order.customer_phone:
            phones.append(task.order.customer_phone)

    elif recipient in ('driver', 'driver_whatsapp'):
        if task and task.driver and task.driver.driver_phone:
            phones.append(task.driver.driver_phone)

    elif recipient == 'all_active_drivers':
        from fleet.models import Driver
        for d in Driver.objects.filter(driver_status='approved', driver_availability__in=['available', 'on_delivery']):
            if d.driver_phone:
                phones.append(d.driver_phone)

    elif recipient == 'available_drivers':
        from fleet.models import Driver
        for d in Driver.objects.filter(driver_status='approved', driver_availability='available'):
            if d.driver_phone:
                phones.append(d.driver_phone)

    elif recipient == 'zone_drivers':
        if task and task.order and task.order.dl_zone:
            from fleet.models import Driver
            for d in Driver.objects.filter(driver_status='approved', assigned_zone=task.order.dl_zone):
                if d.driver_phone:
                    phones.append(d.driver_phone)

    elif recipient in ('seller', 'seller_owner'):
        if task and task.order and task.order.business:
            biz = task.order.business
            phone = biz.business_phone if recipient == 'seller' else getattr(biz, 'owner_phone', biz.business_phone)
            if phone:
                phones.append(phone)

    return phones


def execute_flows_for_trigger(trigger_key, task=None, extra_context=None):
    """
    Find and execute all enabled AutoFlows for the given trigger_key.

    Args:
        trigger_key: The trigger key string (e.g. 'staff_task_publish')
        task: Optional DeliveryTask instance for context
        extra_context: Optional dict of extra template variables
    """
    from core.models import AutoTriggerConfig, AutoFlow, AutoFlowLog

    # Check if the trigger itself is enabled
    if not AutoTriggerConfig.is_trigger_enabled(trigger_key):
        return

    # Find flows for this trigger
    flows = AutoFlow.objects.filter(
        is_enabled=True,
        trigger__trigger_key=trigger_key,
        trigger__is_enabled=True,
    ).select_related('trigger')

    if not flows.exists():
        return

    # Build context
    context = {}
    if task:
        context = _build_context_from_task(task)
    if extra_context:
        context.update(extra_context)

    for flow in flows:
        _execute_single_flow(flow, context, task)


def _execute_single_flow(flow, context, task=None):
    """Execute a single AutoFlow and log the result."""
    from core.models import AutoFlowLog
    import json as json_lib

    start = time.time()
    stages = []
    error_msg = ''
    status = 'success'
    failed_stage = ''

    try:
        config = flow.action_config or {}

        # Stage: Check conditions
        stages.append(('Conditions Check', 'running', ''))
        passed, reason = _check_trigger_conditions(flow, context, task)
        if not passed:
            stages[-1] = ('Conditions Check', 'skipped', reason)
            status = 'skipped'
            # Don't log skipped flows
            return
        stages[-1] = ('Conditions Check', 'ok', 'All conditions met')

        if flow.action_type == 'whatsapp_message':
            # Stage: Resolve recipients
            stages.append(('Resolve Recipients', 'running', ''))
            phones = _resolve_recipient_phones(flow, task)
            if not phones:
                raise ValueError(f"No phone numbers resolved for recipient type: {config.get('recipient', 'customer')}")
            stages[-1] = ('Resolve Recipients', 'ok', f"{len(phones)} recipient(s): {', '.join(phones[:3])}{'...' if len(phones) > 3 else ''}")

            # Stage: Render message
            stages.append(('Render Message', 'running', ''))
            template = config.get('message_template', '')
            if not template:
                raise ValueError("Message template is empty")
            message = _render_template(template, context)
            stages[-1] = ('Render Message', 'ok', f"{message[:80]}{'...' if len(message) > 80 else ''}")

            # Stage: Send messages
            stages.append(('Send WhatsApp', 'running', ''))
            sent = 0
            errors = []
            is_group = config.get('recipient') == 'custom_group'
            instance_override = config.get('wa_instance', '') or None
            for phone in phones:
                success, detail = _send_whatsapp(phone, message, is_group=is_group, instance_override=instance_override)
                if success:
                    sent += 1
                else:
                    errors.append(f"{phone}: {detail}")

            if errors and sent == 0:
                raise ValueError(f"All sends failed: {'; '.join(errors)}")
            elif errors:
                stages[-1] = ('Send WhatsApp', 'ok', f"Sent {sent}/{len(phones)} — errors: {'; '.join(errors)}")
            else:
                stages[-1] = ('Send WhatsApp', 'ok', f"Sent {sent}/{len(phones)} message(s)")

        elif flow.action_type == 'webhook_call':
            # Stage: Send webhook
            stages.append(('Send Webhook', 'running', ''))
            url = config.get('webhook_url', '')
            method = config.get('method', 'POST')
            if not url:
                raise ValueError("Webhook URL is empty")
            headers = {'Content-Type': 'application/json'}
            if config.get('headers'):
                try:
                    extra_headers = json_lib.loads(config['headers'])
                    headers.update(extra_headers)
                except json_lib.JSONDecodeError:
                    raise ValueError("Invalid JSON in custom headers")

            payload = dict(context)
            payload['trigger_key'] = flow.trigger.trigger_key
            payload['flow_name'] = flow.name
            try:
                resp = requests.request(method, url, headers=headers, json=payload, timeout=15)
                stages[-1] = ('Send Webhook', 'ok', f"Response: {resp.status_code}")
            except requests.RequestException as e:
                raise ValueError(f"Webhook request failed: {e}")

        else:
            stages.append(('Execute', 'ok', f"Action type '{flow.action_type}' — no live execution wired yet"))

    except Exception as e:
        status = 'failed'
        error_msg = str(e)
        if stages and stages[-1][1] == 'running':
            failed_stage = stages[-1][0]
            stages[-1] = (stages[-1][0], 'failed', str(e))
        else:
            failed_stage = 'Unknown'
            stages.append(('Error', 'failed', str(e)))

    duration = int((time.time() - start) * 1000)

    # Build result text
    result_parts = []
    for stage_name, stage_status, stage_detail in stages:
        icon = {'ok': '[OK]', 'failed': '[FAILED]', 'skipped': '[SKIP]'}.get(stage_status, '[...]')
        result_parts.append(f"{icon} {stage_name}: {stage_detail}")

    if status == 'failed' and failed_stage:
        error_msg = f"[Stage: {failed_stage}] {error_msg}"

    trigger_data = {
        'trigger_key': flow.trigger.trigger_key,
        'flow_name': flow.name,
        'action_type': flow.action_type,
        'task_id': task.id if task else None,
        'task_number': task.dl_task_number if task else None,
    }

    AutoFlowLog.objects.create(
        flow=flow,
        status=status,
        trigger_data=trigger_data,
        result='\n'.join(result_parts),
        error=error_msg,
        duration_ms=duration,
    )

    if status == 'success':
        logger.info(f"AutoFlow '{flow.name}' executed successfully for trigger '{flow.trigger.trigger_key}' ({duration}ms)")
    else:
        logger.warning(f"AutoFlow '{flow.name}' failed for trigger '{flow.trigger.trigger_key}': {error_msg}")
