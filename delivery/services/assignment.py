# Purpose: Who a delivery task goes to — one driver, Public (every driver's New tab) or the Unassigned list — and the Task Automation rules.
# Used by: workforce/views.py (assign/publish/unassign endpoints, task-automation page), delivery/signals.py (publish hook), orders/services.py.
# Notes: Saves go through the model so the state machine and timeline signals run. Rules only ever touch a task sitting in the Unassigned list.

import logging

from django.db import transaction
from django.db.models import F
from django.utils import timezone

from delivery.selectors import POOL_STATUSES, unassigned_tasks

logger = logging.getLogger('delivery')

#: Where a driverless task is parked, in the pool or the Unassigned list alike.
OPEN_STATUS = 'pending'

PUBLIC_LABEL = 'Public — all drivers'

#: Ceiling for one "apply rules now" run, so the request stays inside nginx's 60s.
APPLY_ALL_LIMIT = 300


def _terminal_refusal(task):
    from delivery.state_machine import TERMINAL_STATUSES

    if task.order_id and task.order.order_status == 'cancelled':
        return 'Order is cancelled'
    if task.dl_task_status in TERMINAL_STATUSES:
        return f'This task is already {task.get_dl_task_status_display()}'
    return ''


def _drop_claims(task, keep=None):
    """Remove claim rows — one alone passes every driver-side ownership check."""
    from delivery.models import AssignedDriver

    rows = AssignedDriver.objects.filter(dl_task=task)
    if keep is not None:
        rows = rows.exclude(driver=keep)
    rows.delete()


def _log_route(task, old_display, new_display, note, actor):
    """Timeline row for a move the driver-change signal cannot see (no driver either side)."""
    from orders.models import OrderStatusHistory

    if not task.order_id:
        return
    OrderStatusHistory.objects.create(
        order_id=task.order_id,
        field_name='driver_change',
        old_value='', new_value='',
        old_display=old_display, new_display=new_display,
        changed_by=actor if getattr(actor, 'is_authenticated', False) else None,
        notes=note,
    )


def assign_to_driver(task, driver, actor=None, note=None):
    """
    Put one driver on the task — it shows in that driver's Assigned tab and no
    one else's. Publishes it as well: an unpublished task is invisible even to
    the driver it is assigned to. Returns (ok, error).
    """
    if task.order_id and task.order.order_status == 'cancelled':
        return False, 'Cannot assign driver — order is cancelled'

    task.driver = driver
    task.public_pool = False
    task.dl_task_publish = True
    # Only a waiting task moves to 'assigned'; a task already under way keeps its
    # status and just changes hands (the forward-only guard would refuse it anyway).
    if task.dl_task_status in POOL_STATUSES:
        task.dl_task_status = 'assigned'
    task._status_actor = 'staff'
    task._status_changed_by = actor
    if note:
        task._driver_change_note = note
    task.save()
    _drop_claims(task, keep=driver)
    return True, ''


def send_to_public(task, actor=None, note=None):
    """Open the task to every driver with app access — it shows in all their New tabs."""
    refusal = _terminal_refusal(task)
    if refusal:
        return False, refusal

    old_driver_id = task.driver_id
    was_public = task.public_pool
    task.driver = None
    task.public_pool = True
    task.dl_task_publish = True
    task.dl_task_status = OPEN_STATUS
    task.dl_task_status_client = 'for_review'
    # Back to 'pending' from assigned/accepted is the unassign reset — the one
    # backward move the state machine opens, and only for a non-terminal task.
    task._status_actor = 'unassign'
    task._status_changed_by = actor
    task._driver_change_note = note or 'Sent to Public'
    task.save()
    _drop_claims(task)
    if not old_driver_id and not was_public:
        _log_route(task, 'No driver', PUBLIC_LABEL, note or 'Sent to Public', actor)
    return True, ''


def send_to_unassigned(task, actor=None):
    """Take the driver off, or pull the task out of Public — it waits in staff's Unassigned list."""
    refusal = _terminal_refusal(task)
    if refusal:
        return False, refusal

    old_driver_id = task.driver_id
    was_public = task.public_pool
    task.driver = None
    task.public_pool = False
    task.dl_task_status = OPEN_STATUS
    task.dl_task_status_client = 'for_review'
    task._status_actor = 'unassign'
    task._status_changed_by = actor
    task._driver_change_note = 'Moved to Unassigned'
    task.save()
    _drop_claims(task)
    if not old_driver_id and was_public:
        _log_route(task, PUBLIC_LABEL, 'No driver', 'Moved to Unassigned', actor)
    return True, ''


def publish_to_fleet(task, actor=None):
    """
    Release the task to the fleet. With no driver it lands in the Unassigned list
    and the rules get one look at it (the publish hook in delivery.signals); a task
    that already has a driver just becomes visible to that driver.
    """
    if task.order_id and task.order.order_status == 'cancelled':
        return False, 'Cannot publish — order is cancelled'

    was_published = task.dl_task_publish
    task.dl_task_publish = True
    if not task.driver_id:
        refusal = _terminal_refusal(task)
        if refusal:
            return False, f'{refusal} — cannot publish it to Fleet.'
        task.dl_task_status = OPEN_STATUS
        task._status_actor = 'unassign'
        if not was_published:
            task.public_pool = False
    task._status_changed_by = actor
    task.save()
    return True, ''


# =============================================================================
# TASK AUTOMATION RULES
# =============================================================================


def _task_zone(task):
    """The drop-off zone number the zone-group condition is checked against."""
    zone = task.route_destination.zone
    try:
        return int(zone) if zone not in (None, '') else None
    except (TypeError, ValueError):
        return None


def driver_rule_problem(driver):
    """Why a rule's driver cannot be given work right now, or ''."""
    from fleet.access import REFUSAL_MESSAGES, dashboard_refusal_code

    if driver is None:
        return 'No driver chosen'
    reason = dashboard_refusal_code(driver)
    return REFUSAL_MESSAGES[reason] if reason else ''


def apply_rules(task_id, actor=None):
    """
    Give one Unassigned task to the first active rule that matches it.
    Returns the rule that fired, or None — the task then stays Unassigned.

    A driver rule whose driver has lost app access is skipped rather than
    obeyed: assigning them would hide the task from everyone.
    """
    from delivery.models import DeliveryTask, TaskAssignmentRule

    rules = list(
        TaskAssignmentRule.objects.filter(is_active=True)
        .select_related('driver', 'zone_group')
    )
    if not rules:
        return None

    with transaction.atomic():
        # Re-read under lock: this runs after the publishing request committed, and
        # staff may have assigned the task by hand in between.
        task = unassigned_tasks(
            DeliveryTask.objects.select_for_update(of=('self',))
        ).select_related('order').filter(pk=task_id).first()
        if task is None:
            return None

        zone = _task_zone(task)
        for rule in rules:
            if not rule.matches(task, zone):
                continue
            note = f'Task Automation: {rule.name}'
            if rule.action == TaskAssignmentRule.ACTION_PUBLIC:
                ok, error = send_to_public(task, actor=actor, note=note)
            else:
                problem = driver_rule_problem(rule.driver)
                if problem:
                    logger.warning(
                        "[task-automation] rule %s skipped for task %s: %s",
                        rule.pk, task.pk, problem)
                    continue
                ok, error = assign_to_driver(task, rule.driver, actor=actor, note=note)
            if not ok:
                logger.warning(
                    "[task-automation] rule %s could not route task %s: %s",
                    rule.pk, task.pk, error)
                continue
            TaskAssignmentRule.objects.filter(pk=rule.pk).update(
                match_count=F('match_count') + 1, last_matched_at=timezone.now())
            logger.info("[task-automation] rule %s routed task %s (%s)",
                        rule.pk, task.pk, rule.action)
            return rule
    return None


def _apply_rules_safely(task_id):
    try:
        apply_rules(task_id)
    except Exception:
        # A broken rule must never undo the publish that triggered it.
        logger.exception("[task-automation] rules failed for task %s", task_id)


def schedule_rules(task_id):
    """Run the rules once the current transaction commits, so the caller finishes building the task first."""
    transaction.on_commit(lambda: _apply_rules_safely(task_id))


def apply_rules_to_unassigned(actor=None):
    """Run the rules over everything in the Unassigned list now. Returns (routed, looked_at)."""
    ids = list(
        unassigned_tasks().order_by('id').values_list('pk', flat=True)[:APPLY_ALL_LIMIT]
    )
    routed = 0
    for task_id in ids:
        if apply_rules(task_id, actor=actor):
            routed += 1
    return routed, len(ids)
