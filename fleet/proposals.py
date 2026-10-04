# Purpose: Single source of truth for which driver proposals each surface may show — the driver app screen and the public driver jobs page.
# Used by: fleet/views.py (driver opportunities screen + interest endpoint), webpages/views.py (careers_drivers), workforce/marketing_views.py
# Notes: Visibility is TWO conditions — live (published, not expired) AND the per-surface audience flag. A view that
#        filters on status alone will leak an app-only offer onto the public site.

from django.db.models import Q
from django.utils import timezone

from fleet.models import (
    PROPOSAL_INTEREST_STATUS_CHOICES, PROPOSAL_INTEREST_WITHDRAWABLE,
    DriverProposal, DriverProposalInterest,
)


def live_proposals():
    """Proposals published and not past their closing time, in display order."""
    now = timezone.now()
    return (
        DriverProposal.objects
        .filter(status='published')
        .filter(Q(closes_at__isnull=True) | Q(closes_at__gt=now))
        .prefetch_related('zone_groups')
    )


def driver_app_proposals():
    """Offers a driver sees inside the app, on the opportunities screen."""
    return live_proposals().filter(show_in_driver_app=True)


def careers_proposals():
    """Offers shown publicly on the driver jobs page, /careers/drivers/.

    Named for the flag it reads (``show_on_careers``) rather than the URL, which
    moved when driver work was split off /careers/ into its own page.
    """
    return live_proposals().filter(show_on_careers=True)


# ---------------------------------------------------------------- interest

REFUSAL_MESSAGES = {
    'not_live': 'This offer is no longer open.',
    'not_in_app': 'This offer is not open to drivers in the app.',
    'decided': 'Operations are already handling your interest. Contact them to change it.',
    'bad_status': 'Unknown status.',
}


def interests_by_proposal(driver):
    """{proposal_id: interest} for one driver — the app marks each offer with it."""
    return {i.proposal_id: i for i in DriverProposalInterest.objects.filter(driver=driver)}


def express_interest(driver, proposal, note=''):
    """Raise a hand on a proposal. Returns (interest, refusal_code or None).

    Only an offer the app is actually showing can be answered — the same two
    conditions driver_app_proposals() applies. A withdrawn row is revived; a row
    staff already moved on is left alone.
    """
    if not proposal.is_live:
        return None, 'not_live'
    if not proposal.show_in_driver_app:
        return None, 'not_in_app'
    interest, created = DriverProposalInterest.objects.get_or_create(
        proposal=proposal, driver=driver, defaults={'note': note[:300]})
    if not created and interest.status == 'withdrawn':
        interest.status = 'interested'
        interest.note = note[:300]
        interest.decided_at = None
        interest.decided_by = None
        interest.save(update_fields=['status', 'note', 'decided_at', 'decided_by', 'updated_at'])
    return interest, None


def withdraw_interest(driver, proposal):
    """Take a hand back down. Returns (interest or None, refusal_code or None)."""
    interest = DriverProposalInterest.objects.filter(proposal=proposal, driver=driver).first()
    if interest is None or interest.status == 'withdrawn':
        return interest, None
    if interest.status not in PROPOSAL_INTEREST_WITHDRAWABLE:
        return interest, 'decided'
    interest.status = 'withdrawn'
    interest.save(update_fields=['status', 'updated_at'])
    return interest, None


def set_interest_status(interest, status, by_user=None, staff_note=None):
    """Staff move an interest along. Returns (interest, refusal_code or None)."""
    if status not in dict(PROPOSAL_INTEREST_STATUS_CHOICES):
        return interest, 'bad_status'
    fields = ['updated_at']
    if status != interest.status:
        interest.status = status
        interest.decided_at = timezone.now()
        interest.decided_by = by_user
        fields += ['status', 'decided_at', 'decided_by']
    if staff_note is not None:
        interest.staff_note = staff_note[:500]
        fields.append('staff_note')
    interest.save(update_fields=fields)
    return interest, None
