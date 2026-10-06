"""
Purpose: Marketing-desk figures for the staff home dashboard — lead queues, pipeline tiles, a 10-day intake trend and the latest open cards.
Used by: workforce.views.wf_dashboard, only when the signed-in user holds the Marketing department.
Notes: Stage keys are always read through crm.services (board_stages / closed_stage_keys / outcome_stage_keys / initial_stage_key) because the two boards name their own columns — see crm-board-separation. Every link built here must point at a URL listed under _MKT in core/departments.py, or a marketing-only user lands on "You don't have access".
"""
from datetime import timedelta

from django.db.models import Count, Q
from django.db.models.functions import TruncDate
from django.utils import timezone

from crm import ownership
from crm import services as crm_services
from crm.models import Lead

#: Same window as the Operations trend above it, so the two charts read as one page.
TREND_DAYS = 10
#: How many open cards the "Latest activity" table shows.
RECENT_LIMIT = 8


def _board_stats(leads, closed_keys, initial_key, today):
    """One aggregate per board instead of a count() per tile.

    `open` is anything not sitting in a terminal column; `unsorted` is the board's
    own entry column, which is where every unworked card lands.
    """
    still_open = ~Q(stage__in=closed_keys)
    return leads.aggregate(
        total=Count('id'),
        today=Count('id', filter=Q(created_at__date=today)),
        week=Count('id', filter=Q(created_at__date__gte=today - timedelta(days=6))),
        open=Count('id', filter=still_open),
        unsorted=Count('id', filter=Q(stage=initial_key) & still_open),
        # Overdue is strictly before today; due includes today, which is what the
        # desk actually works from in the morning.
        overdue=Count('id', filter=Q(next_followup_at__lt=today) & still_open),
        due=Count('id', filter=Q(next_followup_at__lte=today) & still_open),
        unassigned=Count('id', filter=Q(assigned_to__isnull=True) & still_open),
    )


def _my_stats(leads, user, closed_keys, today):
    """The signed-in person's own open cards on one board — the "My Leads" rows."""
    mine = leads.filter(assigned_to=user).exclude(stage__in=closed_keys)
    figures = mine.aggregate(
        open=Count('id'),
        due=Count('id', filter=Q(next_followup_at__lte=today)),
    )
    figures['idle'] = ownership.filter_idle(mine).count()
    return figures


def _intake_trend(live_leads, today):
    """Cards raised per day, one series per board. Two series of the same measure,
    so they share one y-axis — never a second axis (see charts-apexcharts)."""
    start = today - timedelta(days=TREND_DAYS - 1)
    rows = (
        live_leads.filter(created_at__date__gte=start)
        .annotate(day=TruncDate('created_at'))
        .values('day', 'category')
        .annotate(n=Count('id'))
    )
    counts = {(row['category'], row['day']): row['n'] for row in rows}
    days = [start + timedelta(days=i) for i in range(TREND_DAYS)]
    return {
        # Two-line labels, matching the Operations chart: weekday over day-of-month.
        'categories': [[day.strftime('%a'), day.strftime('%d')] for day in days],
        'series': [
            {'name': 'Business leads',
             'data': [counts.get((Lead.CATEGORY_BUSINESS, day), 0) for day in days]},
            {'name': 'Driver applicants',
             'data': [counts.get((Lead.CATEGORY_DRIVER, day), 0) for day in days]},
        ],
    }


def marketing_dashboard_context(request):
    """Everything the `wf_dept_mkt` blocks of the dashboard render.

    Keys are all `mkt_`-prefixed so they can never collide with the Operations and
    Finance figures computed alongside them.
    """
    from fleet import proposals as fleet_proposals
    from fleet.models import DriverProposalInterest
    from webpages.models import PricingEnquiry

    today = timezone.localdate()
    # Absorbed duplicates never count on their own — they render inside their parent.
    # Scoped like the boards: once a card is taken it drops out of everyone else's
    # figures, so a non-manager's page counts their own cards plus the pool.
    live = ownership.visible_leads(Lead.objects.filter(merged_into__isnull=True), request.user)

    business = live.filter(category=Lead.CATEGORY_BUSINESS)
    driver = live.filter(category=Lead.CATEGORY_DRIVER)

    # Handed to the template too: the "new cards" rows link to the list filtered by
    # this exact column, so the page the link opens counts the same rows as the tally.
    biz_entry = crm_services.initial_stage_key(Lead.CATEGORY_BUSINESS)
    drv_entry = crm_services.initial_stage_key(Lead.CATEGORY_DRIVER)

    biz_closed = crm_services.closed_stage_keys(Lead.CATEGORY_BUSINESS)
    drv_closed = crm_services.closed_stage_keys(Lead.CATEGORY_DRIVER)
    biz = _board_stats(business, biz_closed, biz_entry, today)
    drv = _board_stats(driver, drv_closed, drv_entry, today)
    my_biz = _my_stats(business, request.user, biz_closed, today)
    my_drv = _my_stats(driver, request.user, drv_closed, today)

    # Win rate over the last 30 days of *decided* business cards. Read off the
    # board's own outcome columns, not the literal 'won' key.
    won_keys = crm_services.outcome_stage_keys('won', Lead.CATEGORY_BUSINESS)
    lost_keys = crm_services.outcome_stage_keys('lost', Lead.CATEGORY_BUSINESS)
    decided = business.filter(closed_at__date__gte=today - timedelta(days=29)).aggregate(
        won=Count('id', filter=Q(stage__in=won_keys)),
        lost=Count('id', filter=Q(stage__in=lost_keys)),
    )
    settled = decided['won'] + decided['lost']

    recent = list(
        live.exclude(stage__in=(
            crm_services.closed_stage_keys(Lead.CATEGORY_BUSINESS)
            + crm_services.closed_stage_keys(Lead.CATEGORY_DRIVER)
        ))
        .select_related('assigned_to')
        .order_by('-updated_at')[:RECENT_LIMIT]
    )
    ownership.mark_idle(recent)

    return {
        # Queues — the left-hand worklist
        'mkt_new_business': biz['unsorted'],
        'mkt_new_driver': drv['unsorted'],
        'mkt_new_business_stage': biz_entry,
        'mkt_new_driver_stage': drv_entry,
        'mkt_due_business': biz['due'],
        'mkt_due_driver': drv['due'],
        'mkt_overdue_business': biz['overdue'],
        'mkt_overdue_driver': drv['overdue'],
        'mkt_unassigned_business': biz['unassigned'],
        'mkt_unassigned_driver': drv['unassigned'],
        'mkt_pricing_new': PricingEnquiry.objects.filter(
            crm_status=PricingEnquiry.STATUS_NEW).count(),
        # 'interested' is the untouched state — the same rows the Interested
        # Drivers page counts on its New tab.
        'mkt_interest_new': DriverProposalInterest.objects.filter(
            status='interested').count(),
        'mkt_proposals_live': fleet_proposals.live_proposals().count(),
        # Tiles
        'mkt_leads_today': biz['today'] + drv['today'],
        'mkt_leads_week': biz['week'] + drv['week'],
        'mkt_open_business': biz['open'],
        'mkt_open_driver': drv['open'],
        'mkt_total_business': biz['total'],
        'mkt_total_driver': drv['total'],
        'mkt_won_30d': decided['won'],
        'mkt_lost_30d': decided['lost'],
        'mkt_win_rate_30d': round(decided['won'] * 100 / settled) if settled else None,
        # Chart + table
        'mkt_trend': _intake_trend(live, today),
        'mkt_recent_leads': recent,
        # Ownership — "My Leads" rows, the idle flag and the Take next buttons
        'mkt_my_business': my_biz['open'],
        'mkt_my_driver': my_drv['open'],
        'mkt_my_due_business': my_biz['due'],
        'mkt_my_due_driver': my_drv['due'],
        'mkt_my_idle_business': my_biz['idle'],
        'mkt_my_idle_driver': my_drv['idle'],
        'mkt_idle_business': ownership.filter_idle(business).count(),
        'mkt_idle_driver': ownership.filter_idle(driver).count(),
        'mkt_idle_days': ownership.IDLE_DAYS,
        'mkt_is_lead_manager': ownership.is_lead_manager(request.user),
        'mkt_can_claim': ownership.can_claim(request.user),
    }
