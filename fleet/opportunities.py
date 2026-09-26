# Purpose: Single source of truth for which opportunity slots a driver may see, and every transition an interest can make.
# Used by: fleet/views.py (driver board), workforce/views.py (ops console), fleet/admin.py
# Notes: Every interest transition locks its slot row — taking a seat and releasing one both have to read the
#        real seat count, not a cached one. Slot status (open/full) is always re-derived from seats held.

import logging

from django.db import transaction
from django.db.models import Prefetch, Q
from django.utils import timezone

from fleet.models import (
    DriverOpportunity,
    DriverOpportunityInterest,
    DriverOpportunitySlot,
    OPPORTUNITY_SEAT_TAKING_STATUSES,
)

logger = logging.getLogger(__name__)


# Reason codes, same convention as fleet/access.py and business/suspension.py:
# the service returns a code, the view owns the sentence.
SLOT_CLOSED_CODE = 'slot_closed'
SLOT_PAST_CODE = 'slot_past'
SLOT_FULL_CODE = 'slot_full'

REFUSAL_MESSAGES = {
    SLOT_CLOSED_CODE: 'That shift is no longer open.',
    SLOT_PAST_CODE: 'That shift has already started.',
    SLOT_FULL_CODE: 'That shift is already full.',
}


def live_opportunities():
    """Postings a driver is allowed to see at all."""
    now = timezone.now()
    return DriverOpportunity.objects.filter(
        status='open',
    ).filter(
        Q(closes_at__isnull=True) | Q(closes_at__gt=now)
    )


def open_slots_for(driver):
    """Slots this driver may browse, best match first.

    Ordering is the whole point of the board: a driver should not have to read
    forty rows to find the two that suit them. Slots matching the hours they
    already told us they work (Driver.work_time_slabs, set during onboarding)
    sort ahead of the rest, then by start time.

    Deliberately NOT filtered on dashboard access — this board is precisely what
    a verified driver sees before ops clear them to work.
    """
    if not driver:
        return DriverOpportunitySlot.objects.none()

    now = timezone.now()
    qs = (
        DriverOpportunitySlot.objects
        .filter(status='open', starts_at__gt=now,
                opportunity__in=live_opportunities())
        .select_related('opportunity', 'opportunity__pickup_location')
        .prefetch_related(
            'opportunity__zone_groups',
            Prefetch(
                'interests',
                queryset=DriverOpportunityInterest.objects.filter(driver=driver),
                to_attr='my_interests',
            ),
        )
    )

    preferred = driver.work_time_slab_list
    slots = list(qs)
    if preferred:
        slots.sort(key=lambda s: (s.time_slab not in preferred, s.starts_at))
    else:
        slots.sort(key=lambda s: s.starts_at)
    return slots


def interest_for(slot, driver):
    """This driver's standing interest in this slot, or None."""
    # open_slots_for() prefetches this; fall back to a query for other callers.
    cached = getattr(slot, 'my_interests', None)
    if cached is not None:
        return cached[0] if cached else None
    return DriverOpportunityInterest.objects.filter(slot=slot, driver=driver).first()


def slot_refusal_code(slot):
    """Why this slot cannot take an interest right now, or None."""
    if slot.is_past:
        return SLOT_PAST_CODE
    if slot.status != 'open' or not slot.opportunity.is_live:
        return SLOT_CLOSED_CODE
    if slot.places_left <= 0:
        return SLOT_FULL_CODE
    return None


def express_interest(driver, slot, note=''):
    """Raise a hand for a slot. Returns (interest, reason_code).

    Idempotent by the (slot, driver) unique constraint: tapping Interested twice
    is one row, and a previously withdrawn interest is revived rather than
    duplicated — a driver who changes their mind twice should not create litter
    for ops to read.
    """
    reason = slot_refusal_code(slot)
    if reason:
        return None, reason

    interest, created = DriverOpportunityInterest.objects.get_or_create(
        slot=slot, driver=driver,
        defaults={'status': 'interested', 'note': note or ''},
    )
    if not created and interest.status == 'withdrawn':
        interest.status = 'interested'
        interest.note = note or interest.note
        interest.decided_at = None
        interest.decided_by = None
        interest.save(update_fields=['status', 'note', 'decided_at', 'decided_by', 'updated_at'])

    logger.info("Driver %s interested in slot %s (new=%s)",
                driver.driver_id, slot.slot_code, created)
    return interest, None


def withdraw_interest(driver, slot):
    """Take a hand back down. Returns the interest, or None if there was none.

    A confirmed interest is left alone: once ops have counted a driver in, the
    driver telling the app otherwise is a conversation, not a database write.
    """
    interest = DriverOpportunityInterest.objects.filter(slot=slot, driver=driver).first()
    if not interest or interest.status == 'confirmed':
        return interest

    interest.status = 'withdrawn'
    interest.save(update_fields=['status', 'updated_at'])
    logger.info("Driver %s withdrew from slot %s", driver.driver_id, slot.slot_code)
    return interest


@transaction.atomic
def set_interest_status(interest, status, by_user=None):
    """Ops decision on one interest. Returns (interest, reason_code).

    The slot row is locked for every transition, not only for confirmations.
    Capacity is the obvious reason — two ops could each read the last place as
    free — but the quieter one is that RELEASING a seat has to re-read the slot
    too. `interest.slot` is whatever was cached when the interest was loaded, so
    a decline that trusted it would test a stale status and silently leave a
    reopened slot marked full.
    """
    if status not in dict(
            DriverOpportunityInterest._meta.get_field('status').choices):
        raise ValueError(f"Unknown interest status: {status}")

    slot = DriverOpportunitySlot.objects.select_for_update().get(pk=interest.slot_id)
    took_a_seat = interest.status in OPPORTUNITY_SEAT_TAKING_STATUSES
    takes_a_seat = status in OPPORTUNITY_SEAT_TAKING_STATUSES

    if takes_a_seat and not took_a_seat and slot.places_left <= 0:
        return interest, SLOT_FULL_CODE

    interest.status = status
    interest.decided_at = timezone.now()
    interest.decided_by = by_user
    interest.save(update_fields=['status', 'decided_at', 'decided_by', 'updated_at'])

    if takes_a_seat:
        _materialise_rider_shift(interest, slot, by_user)

    # Re-derive the slot's own state from the seats actually held. Cancelled and
    # closed slots are left alone: those are ops decisions, not a side effect of
    # one driver's seat changing hands.
    if slot.status in ('open', 'full'):
        wanted = 'full' if slot.places_left <= 0 else 'open'
        if slot.status != wanted:
            slot.status = wanted
            slot.save(update_fields=['status', 'updated_at'])

    return interest, None


def _materialise_rider_shift(interest, slot, by_user):
    """Turn a confirmed interest into a real dispatch.RiderShift, when we can.

    RiderShift requires a pickup_location and plenty of postings will not name
    one, so this is best-effort by design: no location, no shift, and the
    confirmation still stands on its own.
    """
    if interest.rider_shift_id:
        return
    location = slot.opportunity.pickup_location
    if not location:
        return

    from dispatch.models import RiderShift

    shift = RiderShift.objects.create(
        rider=interest.driver,
        pickup_location=location,
        shift_type='custom',
        status='scheduled',
        scheduled_start=slot.starts_at,
        scheduled_end=slot.ends_at,
        created_by=by_user,
    )
    interest.rider_shift = shift
    interest.save(update_fields=['rider_shift', 'updated_at'])
    logger.info("Confirmed interest %s materialised shift %s", interest.pk, shift.shift_code)
