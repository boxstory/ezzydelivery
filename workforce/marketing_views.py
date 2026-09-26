# Purpose: Marketing-desk staff views — the driver proposals console (the recruitment offers shown in the driver app and on the public careers page).
# Used by: workforce/urls.py (marketing/driver-proposals/... routes); templates in workforce/templates/workforce/marketing/.
# Notes: Which surface shows a proposal is decided by fleet/proposals.py, never by a query written in a view. Route names
#        must be classified in core/departments.py (_MKT) or the gating middleware redirects staff away from them.

import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from core.decorators import staff_required
from core.validators import safe_int
from delivery.models import ZoneGroup
from fleet import models as fleet_models
from fleet.models import DriverProposal

logger = logging.getLogger(__name__)


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


@login_required(login_url='/accounts/login/')
@staff_required
def wf_driver_proposals(request):
    """Every proposal, newest first, with where each one is currently showing."""
    status = (request.GET.get('status') or '').strip()

    proposals = DriverProposal.objects.prefetch_related('zone_groups')
    if status in dict(fleet_models.PROPOSAL_STATUS_CHOICES):
        proposals = proposals.filter(status=status)

    rows = [{'proposal': p, 'is_live': p.is_live} for p in proposals]

    return render(request, 'workforce/marketing/driver_proposals_list.html', {
        'rows': rows,
        'status': status,
        'status_choices': fleet_models.PROPOSAL_STATUS_CHOICES,
        'live_count': sum(1 for r in rows if r['is_live']),
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
