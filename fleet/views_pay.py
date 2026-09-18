# Purpose: Staff consoles for driver pay settings — the per-delivery rate card, and manual bonus/deduction lines.
# Used by: workforce/urls.py (fleet/pay-rates/*, fleet/driver-payout/<id>/adjustment/), templates in fleet/templates/fleet/pay/
# Notes: Finance desk only; every route is classified in core/departments.py or the middleware fails closed.
#        Adjustments write DriverTransaction rows the payout console already knows how to pay — never a new leg.
#        Deductions are stored NEGATIVE: sync_cod_in_hand sums adjustments raw, the payout takes abs().

from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction as db_transaction
from django.db.models import Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from core.decorators import staff_required
from delivery.earnings import FALLBACK_CARD, resolve_card
from fleet import models as fleet_models
from fleet.wallet_service import WalletService

# What staff may enter by hand. COD types settle on their own leg and are not
# offered here; 'adjustment' is deliberately excluded too — it does not appear in
# the payout console's PAYOUT_TYPES, so a row created with it would sit in the
# wallet forever without ever being payable.
ADJUSTMENT_TYPES = ['bonus', 'deduction']

MAX_ADJUSTMENT = Decimal('50000')


def _parse_amount(raw, field='amount', minimum=Decimal('0.01'),
                  maximum=MAX_ADJUSTMENT, unit='QAR'):
    """A positive figure from a form. Sign is applied by the caller, never typed.

    `unit` only spells the error message — a percentage capped at 100 read as
    "over 100 QAR" while the field was a percent.
    """
    try:
        value = Decimal((raw or '').strip())
    except (InvalidOperation, ValueError):
        return None, f'Enter a valid {field}.'
    if value < minimum:
        return None, f'The {field} must be at least {minimum} {unit}.'
    if value > maximum:
        return None, f'That {field} looks wrong — over {maximum:,.0f} {unit}.'
    return value.quantize(Decimal('0.01')), ''


def _parse_day(raw, fallback=None):
    from datetime import datetime
    try:
        return datetime.strptime((raw or '').strip(), '%Y-%m-%d').date()
    except ValueError:
        return fallback


def _checked(raw):
    """An HTML checkbox, which is absent rather than false when it is off."""
    return (raw or '').strip().lower() in ('1', 'on', 'true', 'yes')


def _scope_name(driver):
    """How a rate card's scope reads at the start of a sentence."""
    if driver is None:
        return 'The fleet'
    return driver.driver_code or str(driver.driver_id)


# What counts as a delivery a card has already put a price on. Anything else --
# cancelled, rejected, still moving -- carries no figure that needs explaining,
# so the card behind it can still be removed.
PRICED_TASK_STATUSES = ['delivered', 'partial_delivery']


def _deliveries_priced_by(card):
    """How many deliveries this card has already priced.

    Deliberately over-counts for the fleet card: a driver with an override of
    their own was not really priced by it. Erring towards "keep the row" is the
    right way round, because the answer only ever blocks a deletion.

    Local import - ``delivery.models`` imports ``fleet.models``, so a
    module-level one would close the loop.
    """
    from delivery import models as delivery_models

    tasks = delivery_models.DeliveryTask.objects.filter(
        dl_task_status__in=PRICED_TASK_STATUSES,
        dl_task_date__gte=card.effective_from,
    )
    if card.effective_to is not None:
        tasks = tasks.filter(dl_task_date__lte=card.effective_to)
    if card.driver_id:
        tasks = tasks.filter(driver_id=card.driver_id)
    return tasks.count()


# ---------------------------------------------------------------------------
# Manual bonus / deduction lines
# ---------------------------------------------------------------------------

@login_required(login_url='/accounts/login/')
@staff_required
@require_POST
def driver_adjustment_add(request, driver_id):
    """Add a bonus or a deduction to a driver's payable ledger.

    This is the entry point the incentive leg was missing: the DriverTransaction
    type and the payout maths already handled bonuses, but nothing outside the
    Django admin could create one.
    """
    driver = get_object_or_404(fleet_models.Driver, driver_id=driver_id)
    back = redirect('workforce:driver_payout_worksheet', driver_id=driver_id)

    kind = (request.POST.get('kind') or '').strip()
    if kind not in ADJUSTMENT_TYPES:
        messages.error(request, 'Choose whether this is a bonus or a deduction.')
        return back

    amount, error = _parse_amount(request.POST.get('amount'), kind)
    if error:
        messages.error(request, error)
        return back

    description = (request.POST.get('description') or '').strip()[:255]
    if not description:
        messages.error(
            request,
            'Give the line a reason — it is what the driver sees on the payout invoice.')
        return back

    # The day the bonus was earned or the deduction arose, which is rarely the
    # day someone gets round to typing it. The row is stamped and numbered with
    # that date, so the invoice reads in the order things actually happened.
    # Blank means now.
    occurred_at = None
    raw_date = (request.POST.get('occurred_on') or '').strip()
    if raw_date:
        from django.utils.dateparse import parse_date
        from datetime import datetime as _dt
        happened_on = parse_date(raw_date)
        if happened_on is None:
            messages.error(request, f'"{raw_date}" is not a date this form understands.')
            return back
        now_local = timezone.localtime()
        if happened_on > now_local.date():
            messages.error(request, 'A bonus or deduction cannot be dated in the future.')
            return back
        # Keep the current time of day so two lines dated the same day still
        # order against each other by the order they were entered.
        occurred_at = timezone.make_aware(
            _dt.combine(happened_on, now_local.time()), timezone.get_current_timezone())

    # A deduction is negative money. The wallet sums these raw and the payout
    # takes abs(), so storing it positive would silently pay the driver extra.
    signed = amount if kind == 'bonus' else -amount

    # Deductions cannot be allowed to exceed what is payable, or the payout that
    # includes them is refused at creation time and the line is stuck.
    if kind == 'deduction':
        payable = fleet_models.DriverTransaction.objects.filter(
            driver=driver,
            transaction_type__in=['earning', 'bonus'],
            settlement__isnull=True,
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
        held = fleet_models.DriverTransaction.objects.filter(
            driver=driver, transaction_type='deduction', settlement__isnull=True,
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
        headroom = payable + held  # `held` is already negative
        if amount > headroom:
            messages.error(
                request,
                f'Deducting {amount:,.2f} QAR leaves nothing to pay — only '
                f'{headroom:,.2f} QAR is unpaid on this driver. Deduct it from a '
                f'later payout, or reduce the amount.')
            return back

    with db_transaction.atomic():
        # record_transaction re-derives the wallet for every wallet-affecting
        # type, bonus and deduction included, so no separate sync is needed here.
        WalletService.record_transaction(
            driver=driver,
            transaction_type=kind,
            amount=signed,
            description=description,
            created_by=request.user,
            reference_number=(request.POST.get('reference') or '').strip()[:100] or None,
            occurred_at=occurred_at,
        )

    messages.success(
        request,
        f'{kind.title()} of {amount:,.2f} QAR recorded for '
        f'{driver.driver_code or driver.driver_id} — it will appear on the next payout.')
    return back


@login_required(login_url='/accounts/login/')
@staff_required
@require_POST
def driver_adjustment_remove(request, txn_id):
    """Delete an unpaid bonus/deduction line — a typo, not a reversal.

    Only while the row is still unattached to a settlement. Once it has been
    paid it is part of an issued invoice and the correction is a new opposite
    line, never an edit to the old one.
    """
    txn = get_object_or_404(
        fleet_models.DriverTransaction.objects.select_related('driver'),
        pk=txn_id, transaction_type__in=ADJUSTMENT_TYPES,
    )
    driver = txn.driver
    back = redirect('workforce:driver_payout_worksheet',
                    driver_id=driver.driver_id if driver else 0)

    if txn.settlement_id is not None:
        messages.error(
            request,
            'That line is already on a payout. Record an opposite line instead — '
            'an issued invoice must not change after the fact.')
        return back

    with db_transaction.atomic():
        amount = abs(txn.amount or Decimal('0'))
        kind = txn.transaction_type
        txn.delete()
        if driver:
            WalletService.sync_cod_in_hand(driver)

    messages.success(request, f'Removed the {kind} line of {amount:,.2f} QAR.')
    return back


# ---------------------------------------------------------------------------
# Per-delivery rate card
# ---------------------------------------------------------------------------

@login_required(login_url='/accounts/login/')
@staff_required
def pay_rate_register(request):
    """What a delivery pays, and who is paid differently.

    One fleet-wide card sets the default; a per-driver card overrides it. Both
    are dated agreements, so changing a rate is a new row and last month's queue
    still explains the figure it proposed.
    """
    today = timezone.localdate()

    show = (request.GET.get('show') or 'active').strip()
    cards = (
        fleet_models.DeliveryPayRate.objects
        .select_related('driver', 'driver__user', 'created_by')
        .order_by('-effective_from', '-id')
    )
    if show == 'ended':
        cards = cards.filter(effective_to__isnull=False)
    elif show == 'all':
        pass
    else:
        show = 'active'
        cards = cards.filter(Q(effective_to__isnull=True) | Q(effective_to__gte=today))

    cards = list(cards)
    fleet_card = resolve_card(None, today)
    live = [c for c in cards if c.is_open]

    return render(request, 'fleet/pay/pay_rate_register.html', {
        'page_title': 'Delivery pay rates',
        'cards': cards,
        'show': show,
        'today': today,
        # What the resolver would actually answer right now — including the
        # built-in fallback, so an empty table still states its own figures
        # rather than showing nothing.
        'active_card': fleet_card,
        'fallback': FALLBACK_CARD,
        'using_fallback': fleet_card.is_fallback,
        'fleet_open': sum(1 for c in live if c.is_fleet_default),
        'override_count': sum(1 for c in live if not c.is_fleet_default),
        'candidates': fleet_models.Driver.objects
            .filter(driver_status='approved')
            .select_related('user').order_by('driver_code')[:500],
    })


@login_required(login_url='/accounts/login/')
@staff_required
@require_POST
def pay_rate_save(request):
    """Start a rate card — fleet-wide when no driver is chosen.

    A rate is never edited in place, so "change what a delivery pays" is really
    "close the running card and start the next one". Posting ``replace`` does
    both in one step; without it a scope that already has a running card is
    refused, because silently closing an agreement nobody mentioned is worse
    than a rejected form.
    """
    back = redirect('workforce:pay_rate_register')

    normal, error = _parse_amount(
        request.POST.get('normal_fee'), 'normal delivery fee', minimum=Decimal('0'))
    if error:
        messages.error(request, error)
        return back
    hub, error = _parse_amount(
        request.POST.get('hub_fee'), 'hub delivery fee', minimum=Decimal('0'))
    if error:
        messages.error(request, error)
        return back
    percent, error = _parse_amount(
        request.POST.get('pick_and_drop_percent'), 'pick & drop percentage',
        minimum=Decimal('0'), maximum=Decimal('100'), unit='%')
    if error:
        messages.error(request, error)
        return back
    # Left blank the exchange visit pays the normal fee, which is what it paid
    # before the leg existed — so an old form that does not post the field cannot
    # silently zero a driver's pay.
    raw_exchange = request.POST.get('exchange_fee')
    if raw_exchange in (None, ''):
        exchange = normal
    else:
        exchange, error = _parse_amount(
            raw_exchange, 'exchange visit fee', minimum=Decimal('0'))
        if error:
            messages.error(request, error)
            return back

    effective_from = _parse_day(request.POST.get('effective_from'), timezone.localdate())

    driver = None
    driver_id = (request.POST.get('driver_id') or '').strip()
    if driver_id:
        driver = get_object_or_404(fleet_models.Driver, driver_id=driver_id)
        if driver.driver_status != 'approved':
            messages.error(
                request,
                f'{driver.driver_code or driver.driver_id} is not an approved driver '
                f'({driver.get_driver_status_display()}).')
            return back

    # One open card per scope. Two would make "what does a delivery pay?"
    # ambiguous, and the resolver would answer with whichever sorted first.
    running = (fleet_models.DeliveryPayRate.objects
               .filter(driver=driver, effective_to__isnull=True)
               .order_by('-effective_from', '-id').first())
    who = _scope_name(driver)

    if running and not _checked(request.POST.get('replace')):
        messages.error(
            request,
            f'{who} already has a running rate card from '
            f'{running.effective_from:%d %b %Y}. Tick "Replace the running card" to '
            f'close it and start this one, or end it in the table below.')
        return back

    if running and effective_from < running.effective_from:
        messages.error(
            request,
            f'{who} has a card starting {running.effective_from:%d %b %Y}, which is '
            f'after this one. End or delete that card first - back-dating around it '
            f'would leave two cards claiming the same days.')
        return back

    with db_transaction.atomic():
        replaced = ''
        if running and effective_from > running.effective_from:
            # The day before, never the same day: two cards covering one date is
            # exactly the ambiguity the single-open-card rule exists to prevent.
            running.effective_to = effective_from - timedelta(days=1)
            running.save(update_fields=['effective_to', 'updated_at'])
            replaced = f' The previous card now ends {running.effective_to:%d %b %Y}.'
        elif running:
            # Same start date, so the old card would end up covering no days at
            # all. A zero-length row explains nothing, so it goes rather than
            # sitting in the register as a correction nobody can read.
            running.delete()
            replaced = ' It replaces the card that started the same day.'

        fleet_models.DeliveryPayRate.objects.create(
            driver=driver,
            normal_fee=normal,
            hub_fee=hub,
            pick_and_drop_percent=percent,
            exchange_fee=exchange,
            effective_from=effective_from,
            notes=(request.POST.get('notes') or '').strip()[:2000],
            created_by=request.user,
        )
    messages.success(
        request,
        f'Rate card saved for {driver.driver_code if driver else "the whole fleet"} '
        f'from {effective_from:%d %b %Y}.{replaced}')
    return back


@login_required(login_url='/accounts/login/')
@staff_required
@require_POST
def pay_rate_end(request, rate_id):
    """Close a card. From the next day the scope falls back to the card below it."""
    card = get_object_or_404(fleet_models.DeliveryPayRate, pk=rate_id)
    back = redirect('workforce:pay_rate_register')

    end = _parse_day(request.POST.get('effective_to'), timezone.localdate())
    if end < card.effective_from:
        messages.error(request, 'A rate card cannot end before it started.')
        return back

    card.effective_to = end
    card.save(update_fields=['effective_to', 'updated_at'])
    messages.success(
        request,
        f'Rate card ended {end:%d %b %Y}. '
        f'{"That driver is back on the fleet card." if card.driver_id else "The fleet is back on the built-in fallback unless another card covers it."}')
    return back


@login_required(login_url='/accounts/login/')
@staff_required
@require_POST
def pay_rate_delete(request, rate_id):
    """Remove a card that was recorded by mistake.

    Ending a card is the normal correction and keeps what a past delivery was
    priced at readable. Deletion is only for the row that never priced anything
    - a wrong figure typed this morning, a card for the wrong driver - which
    ending cannot clear, because an ended card still sits in the register
    claiming days it never really governed.
    """
    card = get_object_or_404(fleet_models.DeliveryPayRate, pk=rate_id)
    back = redirect('workforce:pay_rate_register')

    priced = _deliveries_priced_by(card)
    if priced:
        messages.error(
            request,
            f'That card has already priced {priced} '
            f'{"delivery" if priced == 1 else "deliveries"}. End it instead — a figure '
            f'that has been proposed to the payout desk must stay explainable.')
        return back

    who = _scope_name(card.driver)
    start = card.effective_from
    card.delete()
    messages.success(
        request,
        f'Deleted the {who} rate card that started {start:%d %b %Y}. It had priced '
        f'nothing, so no payout changes.')
    return back
