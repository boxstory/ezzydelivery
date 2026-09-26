# Purpose: Single source of truth for which driver proposals each surface may show — the driver app screen and the public careers page.
# Used by: fleet/views.py (driver opportunities screen), webpages/views.py (careers), workforce/marketing_views.py
# Notes: Visibility is TWO conditions — live (published, not expired) AND the per-surface audience flag. A view that
#        filters on status alone will leak an app-only offer onto the public site.

from django.db.models import Q
from django.utils import timezone

from fleet.models import DriverProposal


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
    """Offers shown publicly in the driver offers section of /careers/."""
    return live_proposals().filter(show_on_careers=True)
