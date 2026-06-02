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


def _normalize_qatar_phone(phone):
    """Ensure phone is in 974-prefixed digits-only form for WhatsApp."""
    import re
    s = re.sub(r'\D', '', str(phone or ''))
    if not s:
        return ''
    if s.startswith('974'):
        return s
    if len(s) == 8:  # local Qatar mobile (no country code)
        return '974' + s
    return s  # already international or non-Qatar — pass through


def is_valid_phone(phone):
    """Return True if ``phone`` looks like a sendable WhatsApp number.

    Rejects blanks, all-zero junk (incl. ``00000000`` once a 974 prefix is
    stripped), and digit strings shorter than 7 — these are placeholder
    values that come from upstream feeds with missing data (e.g. a sheet
    cell containing '0') and would otherwise produce noisy WhatsApp API
    failures downstream.
    """
    import re
    s = re.sub(r'\D', '', str(phone or ''))
    if len(s) < 7:
        return False
    if set(s) == {'0'}:
        return False
    # If a Qatar prefix is present, also check the local part — '97400000000'
    # is still junk despite the prefix lifting digit variety.
    if s.startswith('974') and len(s) > 3 and set(s[3:]) == {'0'}:
        return False
    return True


def _pick_phone(obj, *attrs):
    """Return the first non-empty attribute on ``obj``, normalized."""
    for a in attrs:
        v = getattr(obj, a, '') or ''
        if v:
            return _normalize_qatar_phone(v)
    return ''


def _resolve_recipient_phones(flow, task=None, order=None):
    """Resolve recipient type to list of phone numbers.

    Either ``task`` (DeliveryTask) or ``order`` (Order) may be supplied —
    triggers fired at the order level (e.g. ``staff_order_publish``) pass only
    ``order``; task-level triggers pass ``task`` and we derive the order from
    it. All phones are normalized to Qatar 974-prefixed form before return so
    the WhatsApp existence check succeeds for local-format numbers.
    """
    config = flow.action_config or {}
    recipient = config.get('recipient', 'customer')
    phones = []

    if order is None and task is not None:
        order = getattr(task, 'order', None)

    if recipient == 'custom':
        phone = config.get('custom_phone', '').strip()
        if phone:
            norm = _normalize_qatar_phone(phone)
            if norm and is_valid_phone(norm):
                phones.append(norm)

    elif recipient == 'custom_group':
        group_id = config.get('group_id', '').strip()
        if group_id:
            phones.append(group_id)  # group IDs are not phones — leave alone

    elif recipient in ('customer', 'customer_whatsapp'):
        if order:
            p = _pick_phone(order, 'customer_whatsapp', 'customer_phone')
            if p and is_valid_phone(p):
                phones.append(p)

    elif recipient in ('driver', 'driver_whatsapp'):
        if task and task.driver:
            p = _pick_phone(task.driver, 'driver_whatsapp', 'driver_phone')
            if p and is_valid_phone(p):
                phones.append(p)

    elif recipient == 'all_active_drivers':
        from fleet.models import Driver
        for d in Driver.objects.filter(driver_status='approved', driver_availability__in=['available', 'on_delivery'], to_be_notified=True):
            p = _pick_phone(d, 'driver_whatsapp', 'driver_phone')
            if p and is_valid_phone(p):
                phones.append(p)

    elif recipient == 'available_drivers':
        from fleet.models import Driver
        for d in Driver.objects.filter(driver_status='approved', driver_availability='available', to_be_notified=True):
            p = _pick_phone(d, 'driver_whatsapp', 'driver_phone')
            if p and is_valid_phone(p):
                phones.append(p)

    elif recipient == 'zone_drivers':
        if order and order.dl_zone:
            from fleet.models import Driver
            for d in Driver.objects.filter(driver_status='approved', assigned_zone=order.dl_zone, to_be_notified=True):
                p = _pick_phone(d, 'driver_whatsapp', 'driver_phone')
                if p and is_valid_phone(p):
                    phones.append(p)

    elif recipient in ('seller', 'seller_owner'):
        if order and order.business:
            biz = order.business
            raw = biz.business_phone if recipient == 'seller' else getattr(biz, 'owner_phone', biz.business_phone)
            n = _normalize_qatar_phone(raw)
            if n and is_valid_phone(n):
                phones.append(n)

    return phones


def execute_flows_for_trigger(trigger_key, task=None, order=None, extra_context=None):
    """Find and execute all enabled AutoFlows for the given trigger_key.

    Either ``task`` or ``order`` may be passed (or both). Order-level
    triggers like ``staff_order_publish`` typically pass only ``order``;
    task-level triggers pass ``task`` (order is derived from task.order
    inside the recipient resolver). ``extra_context`` adds free-form
    template variables on top.
    """
    from core.models import AutoTriggerConfig, AutoFlow, AutoFlowLog

    if not AutoTriggerConfig.is_trigger_enabled(trigger_key):
        return

    flows = AutoFlow.objects.filter(
        is_enabled=True,
        trigger__trigger_key=trigger_key,
        trigger__is_enabled=True,
    ).select_related('trigger')

    if not flows.exists():
        return

    context = {}
    if task:
        context = _build_context_from_task(task)
    if extra_context:
        context.update(extra_context)

    for flow in flows:
        _execute_single_flow(flow, context, task, order)


def _execute_single_flow(flow, context, task=None, order=None):
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
            # Stage: Throttle gate — at most one message per throttle window.
            # When action_config carries throttle_minutes, publishes inside the
            # window are counted (not sent); the backlog is folded into the
            # next message via the {task_count} template variable.
            throttle_minutes = int(config.get('throttle_minutes') or 0)
            throttle = None
            suppressed = False
            if throttle_minutes > 0:
                from core.models import AutoFlowThrottle
                from django.utils import timezone
                from django.db.models import F
                from datetime import timedelta

                stages.append(('Throttle Gate', 'running', ''))
                throttle, _ = AutoFlowThrottle.objects.get_or_create(flow=flow)
                now = timezone.now()
                window_open = (
                    throttle.last_sent_at is None
                    or (now - throttle.last_sent_at) >= timedelta(minutes=throttle_minutes)
                )
                if window_open:
                    # Window elapsed — this message reports itself + the backlog.
                    context = dict(context)
                    context['task_count'] = throttle.pending_count + 1
                    stages[-1] = ('Throttle Gate', 'ok',
                                  f"Window elapsed — sending digest of {context['task_count']} task(s)")
                else:
                    # Inside the window — count this publish, send nothing.
                    AutoFlowThrottle.objects.filter(pk=throttle.pk).update(
                        pending_count=F('pending_count') + 1
                    )
                    throttle.refresh_from_db()
                    mins_left = max(0, throttle_minutes - int((now - throttle.last_sent_at).total_seconds() // 60))
                    stages[-1] = ('Throttle Gate', 'skipped',
                                  f"Within {throttle_minutes}min window (~{mins_left}min left) — "
                                  f"task counted ({throttle.pending_count} pending), no message sent")
                    status = 'throttled'
                    suppressed = True

            if not suppressed:
                # Stage: Resolve recipients
                stages.append(('Resolve Recipients', 'running', ''))
                phones = _resolve_recipient_phones(flow, task=task, order=order)
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

                # Real send happened — open a fresh window and clear the backlog.
                if throttle is not None and sent > 0:
                    from django.utils import timezone
                    throttle.last_sent_at = timezone.now()
                    throttle.pending_count = 0
                    throttle.save(update_fields=['last_sent_at', 'pending_count', 'updated_at'])

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

    # Resolve order info: prefer explicit order arg, else derive from task.
    log_order = order if order is not None else getattr(task, 'order', None) if task else None
    trigger_data = {
        'trigger_key': flow.trigger.trigger_key,
        'flow_name': flow.name,
        'action_type': flow.action_type,
        'task_id': task.id if task else None,
        'task_number': task.dl_task_number if task else None,
        'order_id': log_order.id if log_order else None,
        'order_number': log_order.order_number if log_order else None,
    }

    AutoFlowLog.objects.create(
        flow=flow,
        status=status,
        trigger_data=trigger_data,
        result='\n'.join(result_parts),
        error=error_msg,
        duration_ms=duration,
    )

    if status == 'throttled':
        logger.info(f"AutoFlow '{flow.name}' throttled for trigger '{flow.trigger.trigger_key}' — task counted, no message sent")
    elif status == 'success':
        logger.info(f"AutoFlow '{flow.name}' executed successfully for trigger '{flow.trigger.trigger_key}' ({duration}ms)")
    else:
        logger.warning(f"AutoFlow '{flow.name}' failed for trigger '{flow.trigger.trigger_key}': {error_msg}")
