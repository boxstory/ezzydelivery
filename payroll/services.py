# Purpose: The rules a salary imposes on money — which deliveries it absorbs, and how a month's run is built.
# Used by: workforce.views earnings publish step, payroll.views (staff console)
# Notes: Salary never touches COD or the client charge. It only decides whether a delivered task
#        creates a per-delivery earning, and it produces its own slip on its own leg.

from decimal import Decimal

from django.db import transaction
from django.db.models import Count, Q

from .models import (
    SalaryCoveredTask, SalaryRun, SalarySlip, SalaryStructure, month_bounds,
    month_start,
)


def _still_running(on_date):
    """An agreement is live on a date when it has no end, or ends on/after it."""
    return Q(effective_to__isnull=True) | Q(effective_to__gte=on_date)


def active_structure(driver, on_date):
    """The salary agreement covering `on_date`, or None if the driver is per-delivery."""
    return (
        SalaryStructure.objects
        .filter(driver=driver, effective_from__lte=on_date)
        .filter(_still_running(on_date))
        .order_by('-effective_from', '-id')
        .first()
    )


def task_date(task):
    """The day a delivery happened — what an agreement is tested against."""
    return task.dl_task_date or (task.completed_at.date() if task.completed_at else None)


def task_period(task):
    """The month a delivery is filed under. Only a filing key, never a date test."""
    basis = task_date(task)
    return month_start(basis) if basis else None


@transaction.atomic
def absorb_delivery(task):
    """Does the driver's salary cover this delivery?

    True  -> the salary pays for it; the caller must NOT create an earning.
    False -> per-delivery as usual (no salary, or the monthly target is used up).

    Recording the cover is what keeps it idempotent: a task already absorbed stays
    absorbed on a re-publish instead of consuming a second slot.
    """
    driver = task.driver
    if not driver:
        return False

    # A salary buys deliveries, not attempts. The endpoint takes task ids from the
    # client, so a failed or cancelled task could otherwise be handed in and eat a
    # slot for work that was never delivered — and it made the on-screen preview,
    # which has always filtered on status, disagree with what publishing did.
    if task.dl_task_status not in ('delivered', 'partial_delivery'):
        return False

    existing = SalaryCoveredTask.objects.filter(task=task).first()
    if existing:
        return True

    # Tested against the delivery's own date. Against the month start instead, a
    # salary ending on the 10th kept absorbing deliveries to the 30th, and one
    # starting on the 15th absorbed nothing at all that month.
    on_date = task_date(task)
    if not on_date:
        return False
    period = month_start(on_date)

    structure = active_structure(driver, on_date)
    if not structure:
        return False

    # A target of 0 means the salary covers every delivery — there is no incentive tier.
    if structure.delivery_target:
        used = SalaryCoveredTask.objects.filter(
            driver=driver, period_month=period,
        ).count()
        if used >= structure.delivery_target:
            return False

    SalaryCoveredTask.objects.create(
        driver=driver, task=task, period_month=period, structure=structure,
    )
    return True


def structure_for_month(driver, period):
    """The agreement covering any part of `period`'s month — latest one wins.

    Overlap, not `effective_from <= 1st`: an agreement that starts mid-month still
    governs that month's later deliveries.
    """
    first, last = month_bounds(period)
    return (
        SalaryStructure.objects
        .filter(driver=driver, effective_from__lte=last)
        .filter(_still_running(first))
        .order_by('-effective_from', '-id')
        .first()
    )


def covered_window(structure, period):
    """The slice of `period`'s month the agreement actually covered."""
    first, last = month_bounds(period)
    start = max(structure.effective_from, first)
    end = min(structure.effective_to or last, last)
    return start, end


def delivery_position(driver, period, structure=None):
    """(covered, target) for one driver in one month — what the slip reports."""
    if structure is None:
        structure = structure_for_month(driver, period)
    covered = SalaryCoveredTask.objects.filter(driver=driver, period_month=period).count()
    return covered, (structure.delivery_target if structure else 0)


def incentive_count(driver, period):
    """Deliveries in the month that fell past the target and paid per-delivery."""
    from delivery.models import DeliveryTask
    from datetime import date
    import calendar

    last = calendar.monthrange(period.year, period.month)[1]
    delivered = DeliveryTask.objects.filter(
        driver=driver,
        dl_task_status__in=['delivered', 'partial_delivery'],
        dl_task_date__gte=period,
        dl_task_date__lte=date(period.year, period.month, last),
        earnings_verification_status='published',
    ).count()
    covered = SalaryCoveredTask.objects.filter(driver=driver, period_month=period).count()
    return max(delivered - covered, 0)


def covered_counts(driver_ids, period):
    """{driver_id: deliveries already absorbed} for one month, in one query."""
    rows = (SalaryCoveredTask.objects
            .filter(driver_id__in=driver_ids, period_month=period)
            .values('driver_id').annotate(n=Count('id')))
    return {r['driver_id']: r['n'] for r in rows}


def delivered_counts(driver_ids, period):
    """{driver_id: published deliveries in the month}, in one query."""
    from delivery.models import DeliveryTask
    first, last = month_bounds(period)
    rows = (DeliveryTask.objects
            .filter(driver_id__in=driver_ids,
                    dl_task_status__in=['delivered', 'partial_delivery'],
                    dl_task_date__gte=first, dl_task_date__lte=last,
                    earnings_verification_status='published')
            .values('driver_id').annotate(n=Count('id')))
    return {r['driver_id']: r['n'] for r in rows}


def structures_for_months(pairs):
    """{(driver_id, period): structure} for many (driver, month) pairs at once.

    One query instead of one per pair — the loop version turned a fleet-wide queue
    into a dozen-plus identical round trips per page render.
    """
    pairs = list(pairs)
    if not pairs:
        return {}
    driver_ids = {d for d, _ in pairs}
    windows = [month_bounds(p) for _, p in pairs]
    overall_first = min(w[0] for w in windows)
    overall_last = max(w[1] for w in windows)

    candidates = list(
        SalaryStructure.objects
        .filter(driver_id__in=driver_ids, effective_from__lte=overall_last)
        .filter(_still_running(overall_first))
        .order_by('driver_id', '-effective_from', '-id')
    )
    by_driver = {}
    for structure in candidates:
        by_driver.setdefault(structure.driver_id, []).append(structure)

    resolved = {}
    for driver_id, period in pairs:
        first, last = month_bounds(period)
        for structure in by_driver.get(driver_id, []):
            # Same overlap test as structure_for_month, applied in Python; the
            # list is already newest-first, so the first hit wins.
            if structure.effective_from <= last and (
                    structure.effective_to is None or structure.effective_to >= first):
                resolved[(driver_id, period)] = structure
                break
    return resolved


def slip_code_for(run, driver):
    return f"SLP-{run.period_month:%Y%m}-{driver.driver_id:05d}"


@transaction.atomic
def build_run(period, user=None):
    """Create (or top up) the month's run with one slip per salaried driver.

    Re-running is safe: a driver who already has a slip is left exactly as it is,
    deductions included. Only drivers missing a slip are added.
    """
    period = month_start(period)
    run, _created = SalaryRun.objects.get_or_create(
        period_month=period, defaults={'created_by': user},
    )

    # Overlap with any part of the month, not `effective_from <= 1st`: a salary
    # that starts mid-month still earns a slip for that month.
    first, last = month_bounds(period)
    structures = (
        SalaryStructure.objects
        .filter(effective_from__lte=last)
        .filter(_still_running(first))
        .select_related('driver')
        .order_by('driver_id', '-effective_from', '-id')
    )

    # One agreement per driver — the most recent that covers the month.
    seen = set()
    chosen = []
    for structure in structures:
        if structure.driver_id in seen:
            continue
        seen.add(structure.driver_id)
        chosen.append(structure)

    # Three batched lookups instead of three queries per slip.
    already = set(
        SalarySlip.objects.filter(run=run, driver_id__in=seen)
        .values_list('driver_id', flat=True)
    )
    covered_by_driver = covered_counts(seen, period)
    delivered_by_driver = delivered_counts(seen, period)

    added = 0
    for structure in chosen:
        if structure.driver_id in already:
            continue

        covered = covered_by_driver.get(structure.driver_id, 0)
        target = structure.delivery_target
        incentive = max(delivered_by_driver.get(structure.driver_id, 0) - covered, 0)
        window_from, window_to = covered_window(structure, period)
        SalarySlip.objects.create(
            run=run,
            driver=structure.driver,
            structure=structure,
            slip_code=slip_code_for(run, structure.driver),
            base_amount=structure.monthly_amount,
            deductions_total=Decimal('0.00'),
            net_amount=structure.monthly_amount,
            delivery_target=target,
            deliveries_covered=covered,
            deliveries_incentive=incentive,
            covered_from=window_from,
            covered_to=window_to,
        )
        added += 1

    # A top-up after the run was closed leaves an unpaid slip behind, so the run
    # is no longer paid.
    if added and run.status == 'paid':
        run.status = 'draft'
        run.save(update_fields=['status'])

    return run, added


def refresh_slip_counts(slip):
    """Re-read the delivery position onto a slip that has not been paid yet."""
    if slip.status == 'paid':
        return slip
    period = slip.run.period_month
    covered, target = delivery_position(slip.driver, period, slip.structure)
    slip.deliveries_covered = covered
    slip.delivery_target = target
    slip.deliveries_incentive = incentive_count(slip.driver, period)
    slip.save(update_fields=[
        'deliveries_covered', 'delivery_target', 'deliveries_incentive', 'updated_at',
    ])
    return slip


def preview_absorption(tasks):
    """Which of `tasks` a salary would cover, WITHOUT recording anything.

    `absorb_delivery` writes a SalaryCoveredTask, so it can never drive a display.
    This answers the same question read-only, using the same rule: within a month a
    salary covers deliveries oldest-first, up to the target, counting whatever it
    has already absorbed.

    Returns {task_id: (position, target)} for covered rows only — a position so the
    page can say "12 of 100" instead of a bare flag.

    Three queries regardless of how many rows are on screen: the agreements, what
    they have already absorbed, and the deliveries still competing for the slots.
    """
    from delivery.models import DeliveryTask

    rows = [t for t in tasks if t.driver_id and task_date(t)]
    if not rows:
        return {}

    groups = {}
    for task in rows:
        groups.setdefault((task.driver_id, month_start(task_date(task))), []).append(task)

    structures = structures_for_months(groups)
    if not structures:
        return {}

    live = list(structures)

    used = {}
    for row in (SalaryCoveredTask.objects
                .filter(driver_id__in={d for d, _ in live},
                        period_month__in={p for _, p in live})
                .values('driver_id', 'period_month')
                .annotate(n=Count('id'))):
        used[(row['driver_id'], row['period_month'])] = row['n']

    # Every unpublished delivery still competing for the month's slots, in the
    # order the publish loop will take them.
    queue = (DeliveryTask.objects
             .filter(driver_id__in={d for d, _ in live},
                     dl_task_status__in=['delivered', 'partial_delivery'])
             .exclude(earnings_verification_status='published')
             .values_list('id', 'driver_id', 'dl_task_date', 'completed_at')
             .order_by('dl_task_date', 'id'))

    position = {}
    seen = {}
    for task_id, driver_id, task_day, completed in queue:
        day = task_day or (completed.date() if completed else None)
        if not day:
            continue
        key = (driver_id, month_start(day))
        structure = structures.get(key)
        if structure is None:
            continue
        # Only deliveries the agreement actually covers compete for its slots. A
        # delivery from earlier in the month than a mid-month start is ordinary
        # per-delivery work and must not consume one — absorb_delivery skips it,
        # so counting it here made the preview disagree with what publish does.
        if day < structure.effective_from:
            continue
        if structure.effective_to and day > structure.effective_to:
            continue
        seen[key] = seen.get(key, 0) + 1
        position[task_id] = seen[key]

    covered = {}
    for task in rows:
        key = (task.driver_id, month_start(task_date(task)))
        structure = structures.get(key)
        if not structure or task.id not in position:
            continue
        target = structure.delivery_target
        rank = used.get(key, 0) + position[task.id]
        # A target of 0 means the salary covers everything.
        if target == 0 or rank <= target:
            covered[task.id] = (rank, target)
    return covered
