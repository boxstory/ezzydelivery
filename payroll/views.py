# Purpose: Staff salary console — the register of agreements, the monthly run, and the slip that pays it.
#          A slip carries two kinds of one-off line: bonus/extra pay on top, deductions off.
# Used by: workforce/urls.py (fleet/salary/*), templates in payroll/templates/payroll/
# Notes: Finance desk only; every route is classified in core/departments.py or the middleware
#        fails closed. Reads never trust POST ids without re-scoping to the object they belong to.

from datetime import date
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from core.decorators import staff_required
from fleet import models as fleet_models

from .models import (
    SalaryAddition, SalaryDeduction, SalaryRun, SalarySlip, SalaryStructure,
    month_start,
)
from .services import build_run, covered_counts, refresh_slip_counts


def _parse_month(raw, fallback=None):
    """'2026-09' or '2026-09-01' into the first of that month.

    For run PERIODS only. Never for an agreement's effective dates — snapping a
    day to the 1st there silently rewrote what staff typed.
    """
    raw = (raw or '').strip()
    for fmt in ('%Y-%m', '%Y-%m-%d'):
        try:
            from datetime import datetime
            return month_start(datetime.strptime(raw, fmt).date())
        except ValueError:
            continue
    return fallback


def _parse_day(raw, fallback=None):
    """An exact date from a <input type="date">, day intact.

    An agreement starting on the 16th or ending on the 30th has to keep that day:
    it is tested against each delivery's own date.
    """
    raw = (raw or '').strip()
    try:
        from datetime import datetime
        return datetime.strptime(raw, '%Y-%m-%d').date()
    except ValueError:
        return fallback


def _parse_amount(raw, field='amount', minimum=None):
    """A money figure from a form. `minimum` enforces a floor above zero.

    A salary of 0.00 is not an agreement — with a target of 0 it means "absorb
    every delivery and pay nothing", which silently makes a driver work for free.
    Deductions may legitimately be 0, so the floor is opt-in per field.
    """
    try:
        value = Decimal((raw or '').strip())
    except (InvalidOperation, ValueError):
        return None, f'Enter a valid {field}.'
    if value < 0:
        return None, f'The {field} cannot be negative.'
    if minimum is not None and value < minimum:
        return None, (f'A {field} of {value} would absorb the driver\u2019s deliveries '
                      f'and pay nothing. Enter more than {minimum}.')
    if value > Decimal('100000'):
        return None, f'That {field} looks wrong — over 100,000 QAR.'
    return value, ''


@login_required(login_url='/accounts/login/')
@staff_required
def salary_register(request):
    """Who is on salary, for how much, and how much of this month's target they have used."""
    today = timezone.localdate()
    period = _parse_month(request.GET.get('month'), month_start(today))

    structures = (
        SalaryStructure.objects
        .select_related('driver', 'driver__user')
        .order_by('-effective_from', '-id')
    )
    show = (request.GET.get('show') or 'active').strip()
    if show == 'active':
        structures = structures.filter(effective_to__isnull=True)
    elif show == 'ended':
        structures = structures.filter(effective_to__isnull=False)
    else:
        show = 'all'

    # Batched: the row already holds its agreement, and the absorbed counts come
    # back in one grouped query. Resolving both per row made the register issue
    # two extra round trips for every salaried driver on the page.
    structures = list(structures)
    absorbed = covered_counts({s.driver_id for s in structures}, period)
    rows = []
    for structure in structures:
        covered = absorbed.get(structure.driver_id, 0)
        target = structure.delivery_target
        rows.append({
            'structure': structure,
            'covered': covered,
            'target': target,
            'remaining': max(target - covered, 0) if target else None,
        })

    monthly_total = sum(
        (r['structure'].monthly_amount for r in rows if r['structure'].is_open),
        Decimal('0.00'),
    )

    return render(request, 'payroll/salary_register.html', {
        'page_title': 'Driver salaries',
        'rows': rows,
        'period': period,
        'show': show,
        'monthly_total': monthly_total,
        'open_count': sum(1 for r in rows if r['structure'].is_open),
        # Approved drivers only, and only those without a live agreement.
        # A pending row is an application, not a driver — 571 of 586 rows are
        # applicants who have never been taken on, and none of them can be put
        # on a payroll. Spelled as an explicit id subquery because
        # `exclude(salary_structures__effective_to__isnull=True)` also swallows
        # every driver who has no structure at all, which emptied the dropdown.
        'candidates': fleet_models.Driver.objects
            .filter(driver_status='approved')
            .exclude(driver_id__in=SalaryStructure.objects
                     .filter(effective_to__isnull=True).values('driver_id'))
            .select_related('user').order_by('driver_code')[:500],
    })


@login_required(login_url='/accounts/login/')
@staff_required
@require_POST
def salary_structure_save(request):
    """Start a salary agreement."""
    amount, error = _parse_amount(
        request.POST.get('monthly_amount'), 'salary', minimum=Decimal('0.01'))
    if error:
        messages.error(request, error)
        return redirect('workforce:salary_register')

    try:
        target = int((request.POST.get('delivery_target') or '0').strip() or 0)
    except ValueError:
        target = -1
    if target < 0 or target > 5000:
        messages.error(request, 'Enter a delivery target between 0 and 5000.')
        return redirect('workforce:salary_register')

    effective_from = _parse_day(
        request.POST.get('effective_from'), timezone.localdate().replace(day=1))

    # No in-place edit: an agreement is a dated record, so a change of terms is a
    # new agreement after ending the old one. Rewriting one in place would move
    # what a past month was paid under.
    driver_id = (request.POST.get('driver_id') or '').strip()
    driver = get_object_or_404(fleet_models.Driver, driver_id=driver_id)
    # Checked here as well as in the dropdown: the id arrives in the POST, so
    # hiding the option is presentation, not a rule.
    if driver.driver_status != 'approved':
        messages.error(
            request,
            f'{driver.driver_code or driver.driver_id} is not an approved driver '
            f'({driver.get_driver_status_display()}) — only approved drivers can be put on salary.',
        )
        return redirect('workforce:salary_register')
    if SalaryStructure.objects.filter(driver=driver, effective_to__isnull=True).exists():
        messages.error(
            request,
            f'{driver.driver_code} already has a running salary. End it before starting another.',
        )
        return redirect('workforce:salary_register')

    SalaryStructure.objects.create(
        driver=driver,
        monthly_amount=amount,
        delivery_target=target,
        effective_from=effective_from,
        notes=(request.POST.get('notes') or '').strip()[:2000],
        created_by=request.user,
    )
    messages.success(request, f'{driver.driver_code} is now on salary.')
    return redirect('workforce:salary_register')


@login_required(login_url='/accounts/login/')
@staff_required
@require_POST
def salary_structure_end(request, structure_id):
    """Close an agreement. From the next day the driver is back on per-delivery pay."""
    structure = get_object_or_404(SalaryStructure, pk=structure_id)
    end = _parse_day(request.POST.get('effective_to'), timezone.localdate())
    if end < structure.effective_from:
        messages.error(request, 'The end date cannot be before the start date.')
        return redirect('workforce:salary_register')

    structure.effective_to = end
    structure.save(update_fields=['effective_to', 'updated_at'])
    messages.success(
        request, f'Salary for {structure.driver.driver_code} ends {end:%d %b %Y}.')
    return redirect('workforce:salary_register')


@login_required(login_url='/accounts/login/')
@staff_required
def salary_runs(request):
    """Every month's payroll, newest first."""
    runs = (
        SalaryRun.objects
        .annotate(slip_count=Count('slips'), total=Sum('slips__net_amount'))
        .order_by('-period_month')
    )
    return render(request, 'payroll/salary_runs.html', {
        'page_title': 'Salary runs',
        'runs': runs,
        'default_month': month_start(timezone.localdate()),
    })


@login_required(login_url='/accounts/login/')
@staff_required
@require_POST
def salary_run_create(request):
    """Open a month and draw a slip for every driver on salary that month."""
    period = _parse_month(request.POST.get('month'))
    if not period:
        messages.error(request, 'Pick a month to run.')
        return redirect('workforce:salary_runs')
    if period > month_start(timezone.localdate()):
        messages.error(request, 'That month has not started yet.')
        return redirect('workforce:salary_runs')

    run, added = build_run(period, user=request.user)
    if added:
        messages.success(request, f'{added} slip(s) drawn for {period:%B %Y}.')
    else:
        messages.info(request, f'{period:%B %Y} already has every slip it needs.')
    return redirect('workforce:salary_run_detail', run_id=run.pk)


@login_required(login_url='/accounts/login/')
@staff_required
def salary_run_detail(request, run_id):
    """The month's slips: base, deductions, net, and what has been paid."""
    run = get_object_or_404(SalaryRun, pk=run_id)
    slips = (
        run.slips
        .select_related('driver', 'driver__user', 'structure')
        .prefetch_related('addition_lines', 'deduction_lines')
        .order_by('driver__driver_code')
    )
    totals = {
        'base': sum((s.base_amount for s in slips), Decimal('0.00')),
        'additions': sum((s.additions_total for s in slips), Decimal('0.00')),
        'deductions': sum((s.deductions_total for s in slips), Decimal('0.00')),
        'net': sum((s.net_amount for s in slips), Decimal('0.00')),
        'paid': sum((s.net_amount for s in slips if s.status == 'paid'), Decimal('0.00')),
    }
    return render(request, 'payroll/salary_run_detail.html', {
        'page_title': f'Salary · {run.period_month:%B %Y}',
        'run': run,
        'slips': slips,
        'totals': totals,
        'unpaid_count': sum(1 for s in slips if s.status != 'paid'),
        'payment_methods': SalarySlip.PAYMENT_METHODS,
    })


@login_required(login_url='/accounts/login/')
@staff_required
@require_POST
def salary_addition_add(request, slip_id):
    """Pay something on top of the salary — bonus, overtime, allowance, extra work.

    A one-off for this month only. Raising what the driver earns every month is a
    new agreement on the register, not a line here.
    """
    slip = get_object_or_404(SalarySlip.objects.select_related('run'), pk=slip_id)
    if slip.status == 'paid':
        messages.error(request, 'That slip is already paid — nothing more can be added to it.')
        return redirect('workforce:salary_run_detail', run_id=slip.run_id)

    label = (request.POST.get('label') or '').strip()[:120]
    amount, error = _parse_amount(request.POST.get('amount'), 'bonus')
    if not label:
        messages.error(request, 'Say what the bonus is for.')
    elif error:
        messages.error(request, error)
    elif amount <= 0:
        # A 0.00 deduction is harmless; a 0.00 bonus is a line that says nothing
        # and still has to be explained on the slip the driver is handed.
        messages.error(request, 'A bonus of 0.00 pays nothing — enter an amount.')
    else:
        SalaryAddition.objects.create(
            slip=slip, label=label, amount=amount, created_by=request.user,
        )
        slip.recalculate()
        messages.success(request, f'{label} added to {slip.slip_code} — +{amount} QAR.')
    return redirect('workforce:salary_run_detail', run_id=slip.run_id)


@login_required(login_url='/accounts/login/')
@staff_required
@require_POST
def salary_addition_remove(request, addition_id):
    line = get_object_or_404(
        SalaryAddition.objects.select_related('slip', 'slip__run'), pk=addition_id)
    slip = line.slip
    if slip.status == 'paid':
        messages.error(request, 'That slip is already paid — its lines are closed.')
        return redirect('workforce:salary_run_detail', run_id=slip.run_id)
    line.delete()
    slip.recalculate()
    # Dropping a bonus can leave deductions standing above what is left to pay.
    if slip.net_amount < 0:
        messages.warning(
            request,
            f'{slip.slip_code} now nets {slip.net_amount} QAR — the deductions are '
            f'above the salary. Remove one before paying.',
        )
    else:
        messages.success(request, 'Bonus removed.')
    return redirect('workforce:salary_run_detail', run_id=slip.run_id)


@login_required(login_url='/accounts/login/')
@staff_required
@require_POST
def salary_deduction_add(request, slip_id):
    """Take something off a slip — advance, fine, fuel, SIM."""
    slip = get_object_or_404(SalarySlip.objects.select_related('run'), pk=slip_id)
    if slip.status == 'paid':
        messages.error(request, 'That slip is already paid — deductions are closed.')
        return redirect('workforce:salary_run_detail', run_id=slip.run_id)

    label = (request.POST.get('label') or '').strip()[:120]
    amount, error = _parse_amount(request.POST.get('amount'), 'deduction')
    if not label:
        messages.error(request, 'Give the deduction a name.')
    elif error:
        messages.error(request, error)
    elif amount + slip.deductions_total > slip.gross_amount:
        # Per-line was not enough: three lines under the base can still sum past
        # it, and a slip that nets below zero can never be paid. Measured against
        # base + bonuses, so a bonus genuinely widens the room.
        room = slip.gross_amount - slip.deductions_total
        messages.error(
            request,
            f'That would take the deductions past the salary. '
            f'{room} QAR of {slip.gross_amount} is still available on {slip.slip_code}.',
        )
    else:
        SalaryDeduction.objects.create(
            slip=slip, label=label, amount=amount, created_by=request.user,
        )
        slip.recalculate()
        messages.success(request, f'{label} deducted from {slip.slip_code}.')
    return redirect('workforce:salary_run_detail', run_id=slip.run_id)


@login_required(login_url='/accounts/login/')
@staff_required
@require_POST
def salary_deduction_remove(request, deduction_id):
    line = get_object_or_404(
        SalaryDeduction.objects.select_related('slip', 'slip__run'), pk=deduction_id)
    slip = line.slip
    if slip.status == 'paid':
        messages.error(request, 'That slip is already paid — deductions are closed.')
        return redirect('workforce:salary_run_detail', run_id=slip.run_id)
    line.delete()
    slip.recalculate()
    messages.success(request, 'Deduction removed.')
    return redirect('workforce:salary_run_detail', run_id=slip.run_id)


@login_required(login_url='/accounts/login/')
@staff_required
@require_POST
def salary_slip_pay(request, slip_id):
    """Hand the money over and close the slip."""
    slip = get_object_or_404(SalarySlip.objects.select_related('run', 'driver'), pk=slip_id)
    if slip.status == 'paid':
        messages.info(request, f'{slip.slip_code} was already paid.')
        return redirect('workforce:salary_run_detail', run_id=slip.run_id)
    if slip.net_amount <= 0:
        messages.error(
            request,
            f'{slip.slip_code} nets {slip.net_amount} QAR — check the deductions before paying.',
        )
        return redirect('workforce:salary_run_detail', run_id=slip.run_id)

    method = (request.POST.get('payment_method') or '').strip()
    if method not in dict(SalarySlip.PAYMENT_METHODS):
        messages.error(request, 'Pick how the salary was paid.')
        return redirect('workforce:salary_run_detail', run_id=slip.run_id)

    slip.mark_paid(method, (request.POST.get('payment_reference') or '').strip()[:100], request.user)

    run = slip.run
    if not run.slips.exclude(status='paid').exists():
        run.status = 'paid'
        run.save(update_fields=['status'])

    messages.success(request, f'{slip.slip_code} paid — {slip.net_amount} QAR.')
    return redirect('workforce:salary_run_detail', run_id=run.pk)


@login_required(login_url='/accounts/login/')
@staff_required
def salary_slip(request, slip_id):
    """The printable slip handed to the driver."""
    slip = get_object_or_404(
        SalarySlip.objects
        .select_related('run', 'driver', 'driver__user', 'structure', 'paid_by')
        .prefetch_related('addition_lines', 'deduction_lines'),
        pk=slip_id,
    )
    if slip.status != 'paid':
        refresh_slip_counts(slip)
    return render(request, 'payroll/salary_slip.html', {
        'page_title': slip.slip_code,
        'slip': slip,
        'additions': slip.addition_lines.all(),
        'deductions': slip.deduction_lines.all(),
    })
