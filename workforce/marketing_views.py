# Purpose: Marketing-desk staff views — the desk's own overview page, the driver proposals console (the recruitment offers shown in the driver app and on the public careers page) and the drivers interested in them.
# Used by: workforce/urls.py (marketing/... routes); templates in workforce/templates/workforce/marketing/.
# Notes: Which surface shows a proposal is decided by fleet/proposals.py, never by a query written in a view. Route names
#        must be classified in core/departments.py (_MKT) or the gating middleware redirects staff away from them.

import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.utils.http import urlencode

from core.decorators import staff_required
from core.validators import safe_int
from delivery.models import ZoneGroup
from fleet import models as fleet_models
from fleet.models import DriverProposal, DriverProposalInterest

logger = logging.getLogger(__name__)


@login_required(login_url='/accounts/login/')
@staff_required
def wf_marketing_overview(request):
    """The marketing desk's landing page — what needs working today.

    Deliberately a page of its own rather than a department block on the staff
    dashboard: that page is the Operations/Finance console, and a marketing-only
    account is redirected here by workforce.views.wf_dashboard. Every figure comes
    from workforce/dashboard_marketing.py, which reads stage keys through
    crm.services so each board keeps its own column names.
    """
    from workforce.dashboard_marketing import marketing_dashboard_context

    context = {'page_title': 'Marketing Overview'}
    context.update(marketing_dashboard_context(request))
    return render(request, 'workforce/marketing/overview.html', context)


def _proposal_dt(raw):
    """Parse a datetime-local field into an aware datetime, or None."""
    if not raw:
        return None
    parsed = parse_datetime(raw)
    if parsed is None:
        return None
    if timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed, timezone.get_current_timezone())
    return parsed


# The sentence the desk sends with the link. Kept here, not in the template, so
# the copy button and the WhatsApp button can never drift apart.
DRIVER_JOBS_SHARE_TEXT = (
    'EZZY Delivery is hiring drivers in Qatar. '
    'See the open positions, the pay and the zones here: {url}'
)


@login_required(login_url='/accounts/login/')
@staff_required
def wf_driver_proposals(request):
    """Every proposal, newest first, with where each one is currently showing."""
    status = (request.GET.get('status') or '').strip()

    proposals = DriverProposal.objects.prefetch_related('zone_groups').annotate(
        interest_count=Count('interests', filter=~Q(interests__status='withdrawn')),
        new_interest_count=Count('interests', filter=Q(interests__status='interested')),
    )
    if status in dict(fleet_models.PROPOSAL_STATUS_CHOICES):
        proposals = proposals.filter(status=status)

    rows = [{'proposal': p, 'is_live': p.is_live} for p in proposals]

    # The public driver jobs page is what a driver gets sent on WhatsApp, so the
    # desk needs the absolute link here — not a relative path it cannot paste.
    public_url = request.build_absolute_uri(reverse('webpages:careers_drivers'))

    return render(request, 'workforce/marketing/driver_proposals_list.html', {
        'rows': rows,
        'status': status,
        'status_choices': fleet_models.PROPOSAL_STATUS_CHOICES,
        'live_count': sum(1 for r in rows if r['is_live']),
        'public_url': public_url,
        'public_share_url': 'https://wa.me/?' + urlencode(
            {'text': DRIVER_JOBS_SHARE_TEXT.format(url=public_url)}),
    })


@login_required(login_url='/accounts/login/')
@staff_required
def wf_driver_proposal_edit(request, proposal_id=None):
    """Create or edit a proposal."""
    proposal = None
    if proposal_id:
        proposal = get_object_or_404(DriverProposal, pk=proposal_id)

    if request.method == 'POST':
        title = (request.POST.get('title') or '').strip()
        if not title:
            messages.error(request, 'A title is required.')
            return redirect(request.path)

        if proposal is None:
            proposal = DriverProposal(created_by=request.user)

        proposal.title = title[:150]
        proposal.ref_code = (request.POST.get('ref_code') or '').strip()[:20]
        proposal.headline = (request.POST.get('headline') or '').strip()[:200]
        proposal.description = (request.POST.get('description') or '').strip()
        proposal.pay_package = (request.POST.get('pay_package') or '').strip()[:200]
        proposal.perks = (request.POST.get('perks') or '').strip()
        proposal.requirements = (request.POST.get('requirements') or '').strip()

        job_type = (request.POST.get('job_type') or '').strip()
        proposal.job_type = (
            job_type if job_type in dict(fleet_models.DRIVER_JOB_TYPE_CHOICES) else '')

        vehicle = (request.POST.get('vehicle_type') or '').strip()
        proposal.vehicle_type = (
            vehicle if vehicle in dict(fleet_models.VEHICLE_CHOICES) else '')

        proposal.show_in_driver_app = bool(request.POST.get('show_in_driver_app'))
        proposal.show_on_careers = bool(request.POST.get('show_on_careers'))
        # PositiveIntegerField — a negative order would be a database error, so
        # the floor is clamped here rather than trusted from the form.
        proposal.display_order = safe_int(
            request.POST.get('display_order'), default=0, minimum=0)

        new_status = (request.POST.get('status') or 'draft').strip()
        if new_status not in dict(fleet_models.PROPOSAL_STATUS_CHOICES):
            new_status = 'draft'
        # Publishing is the moment both surfaces start showing it, so stamp it
        # once and never re-stamp — a later wording edit is not a republication.
        if new_status == 'published' and not proposal.published_at:
            proposal.published_at = timezone.now()
        proposal.status = new_status

        proposal.closes_at = _proposal_dt((request.POST.get('closes_at') or '').strip())

        proposal.save()

        zone_ids = [z for z in request.POST.getlist('zone_groups') if z.isdigit()]
        proposal.zone_groups.set(ZoneGroup.objects.filter(id__in=zone_ids))

        messages.success(request, 'Proposal saved.')
        return redirect('workforce:wf_driver_proposals')

    return render(request, 'workforce/marketing/driver_proposal_form.html', {
        'proposal': proposal,
        'status_choices': fleet_models.PROPOSAL_STATUS_CHOICES,
        'job_type_choices': fleet_models.DRIVER_JOB_TYPE_CHOICES,
        'vehicle_choices': [c for c in fleet_models.VEHICLE_CHOICES if c[0] != 'none'],
        'zone_groups': ZoneGroup.objects.filter(is_active=True).order_by('display_order', 'name'),
        'selected_zones': [z.pk for z in proposal.zone_groups.all()] if proposal else [],
    })


@login_required(login_url='/accounts/login/')
@staff_required
def wf_driver_proposal_status(request, proposal_id):
    """Publish or close a proposal from the list, without opening the form."""
    proposal = get_object_or_404(DriverProposal, pk=proposal_id)
    if request.method != 'POST':
        return redirect('workforce:wf_driver_proposals')

    new_status = (request.POST.get('status') or '').strip()
    if new_status not in dict(fleet_models.PROPOSAL_STATUS_CHOICES):
        messages.error(request, 'Unknown status.')
        return redirect('workforce:wf_driver_proposals')

    if new_status == 'published' and not proposal.published_at:
        proposal.published_at = timezone.now()
    proposal.status = new_status
    proposal.save(update_fields=['status', 'published_at', 'updated_at'])

    messages.success(
        request, f'"{proposal.title}" is now {proposal.get_status_display().lower()}.')
    return redirect('workforce:wf_driver_proposals')


@login_required(login_url='/accounts/login/')
@staff_required
def wf_driver_proposal_delete(request, proposal_id):
    """Remove a proposal. Nothing references it, so this is a plain delete."""
    proposal = get_object_or_404(DriverProposal, pk=proposal_id)
    if request.method == 'POST':
        title = proposal.title
        proposal.delete()
        messages.success(request, f'"{title}" deleted.')
    return redirect('workforce:wf_driver_proposals')


def _wa_digits(raw):
    """A wa.me number from a stored phone: a bare 8-digit Qatar number gets 974."""
    digits = ''.join(ch for ch in (raw or '') if ch.isdigit())
    return '974' + digits if len(digits) == 8 else digits


# Statuses still being worked; the default view hides the closed-out ones.
_OPEN_INTEREST_STATUSES = ('interested', 'contacted', 'shortlisted')


@login_required(login_url='/accounts/login/')
@staff_required
def wf_driver_proposal_interests(request):
    """Drivers who tapped "I'm interested" on a proposal — the desk works them here."""
    proposal_id = safe_int(request.GET.get('proposal'), default=0, minimum=0)
    status = (request.GET.get('status') or 'open').strip()
    q = (request.GET.get('q') or '').strip()[:60]

    base = DriverProposalInterest.objects.all()
    if proposal_id:
        base = base.filter(proposal_id=proposal_id)
    counts = dict(base.values_list('status').annotate(n=Count('pk')))

    rows = base.select_related(
        'proposal', 'driver', 'driver__profile', 'driver__user', 'decided_by',
    ).prefetch_related('driver__driver_vehicle')
    if status == 'open':
        rows = rows.filter(status__in=_OPEN_INTEREST_STATUSES)
    elif status in dict(fleet_models.PROPOSAL_INTEREST_STATUS_CHOICES):
        rows = rows.filter(status=status)
    if q:
        digits = ''.join(ch for ch in q if ch.isdigit())
        match = (Q(driver__profile__first_name__icontains=q) | Q(driver__profile__last_name__icontains=q)
                 | Q(driver__user__username__icontains=q))
        if len(digits) >= 4:
            match |= Q(driver__driver_phone__contains=digits) | Q(driver__driver_whatsapp__contains=digits)
        if q.isdigit():
            match |= Q(driver__driver_id=int(q))
        rows = rows.filter(match)

    status_tabs = [('open', 'Open', sum(counts.get(s, 0) for s in _OPEN_INTEREST_STATUSES))]
    status_tabs += [(key, label, counts.get(key, 0))
                    for key, label in fleet_models.PROPOSAL_INTEREST_STATUS_CHOICES]
    status_tabs.append(('all', 'All', sum(counts.values())))

    rows = list(rows.order_by('-created_at')[:500])
    for interest in rows:
        interest.wa_digits = _wa_digits(interest.driver.driver_whatsapp or interest.driver.driver_phone)
        interest.vehicle = next(iter(interest.driver.driver_vehicle.all()), None)

    return render(request, 'workforce/marketing/driver_proposal_interests.html', {
        'rows': rows,
        'proposals': DriverProposal.objects.order_by('-created_at'),
        'proposal_id': proposal_id,
        'status': status,
        'status_tabs': status_tabs,
        'q': q,
        'status_choices': fleet_models.PROPOSAL_INTEREST_STATUS_CHOICES,
        'new_count': counts.get('interested', 0),
    })


@login_required(login_url='/accounts/login/')
@staff_required
def wf_driver_proposal_interest_update(request, interest_id):
    """Move one interest along (status + internal note), then back to the same view."""
    from django.utils.http import url_has_allowed_host_and_scheme
    from fleet.proposals import REFUSAL_MESSAGES, set_interest_status

    back = request.POST.get('next') or ''
    if not url_has_allowed_host_and_scheme(back, allowed_hosts={request.get_host()},
                                           require_https=request.is_secure()):
        back = ''
    back = back or redirect('workforce:wf_driver_proposal_interests').url
    if request.method != 'POST':
        return redirect(back)

    interest = get_object_or_404(
        DriverProposalInterest.objects.select_related('driver', 'proposal'), pk=interest_id)
    _interest, reason = set_interest_status(
        interest, (request.POST.get('status') or '').strip(), by_user=request.user,
        staff_note=(request.POST.get('staff_note') or '').strip())
    if reason:
        messages.error(request, REFUSAL_MESSAGES[reason])
    else:
        messages.success(
            request, f'{interest.driver.driver_name} — {interest.get_status_display()} '
                     f'for "{interest.proposal.title}".')
    return redirect(back)
