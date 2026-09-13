# Purpose: Close every open-ended range on the rate card — no row runs to "no limit" any more.
# Used by: migrate — one pass over the existing bands and box tiers.
# Notes: The two ceilings are the real limits of a bookable job, not preferences. 20 boxes is
#        what the booking form, the calculator's stepper and book_start all clamp to. 300 km is
#        p2p.pricing.max_journey_km() at the time of writing — the diagonal of QATAR_BBOX put
#        through the road factor and buffer, rounded up — so no journey the page will accept
#        falls outside it. Written as literals here because a migration is a historical record:
#        it must keep doing the same thing after those inputs change.

from django.db import migrations

MAX_BOXES = 20
MAX_KM = 300


def close(apps, schema_editor):
    apps.get_model('p2p', 'P2PRateBand').objects.filter(
        max_boxes__isnull=True).update(max_boxes=MAX_BOXES)
    apps.get_model('p2p', 'P2PRateBand').objects.filter(
        up_to_km__isnull=True).update(up_to_km=MAX_KM)
    apps.get_model('p2p', 'P2PBoxTier').objects.filter(
        max_boxes__isnull=True).update(max_boxes=MAX_BOXES)


def reopen(apps, schema_editor):
    """Put the ceilings back to null. Only touches rows sitting exactly on the value
    this migration wrote, so a genuine 20-box or 300 km row ops typed is left alone —
    it cannot tell them apart otherwise, and reopening a deliberate limit is worse."""
    apps.get_model('p2p', 'P2PRateBand').objects.filter(
        max_boxes=MAX_BOXES).update(max_boxes=None)
    apps.get_model('p2p', 'P2PRateBand').objects.filter(
        up_to_km=MAX_KM).update(up_to_km=None)
    apps.get_model('p2p', 'P2PBoxTier').objects.filter(
        max_boxes=MAX_BOXES).update(max_boxes=None)


class Migration(migrations.Migration):

    dependencies = [('p2p', '0007_seed_box_tiers')]

    operations = [migrations.RunPython(close, reopen)]
