# Purpose: Seed the four P2P box tiers — what carrying more than one box adds to a price.
# Used by: migrate — runs once; re-running is a no-op because it keys on the box span.
# Notes: A one-box job is unchanged (uplift 0), so every price the card quoted before this
#        migration still quotes the same. Past ten boxes there is no automatic price: that is
#        a van being loaded, and it goes to a human. Ops edit these on the rate card page.

from django.db import migrations


# (min_boxes, max_boxes, uplift, needs_quote)
SEED_TIERS = [
    (1, 1, 0, False),
    (2, 3, 10, False),
    (4, 10, 25, False),
    (11, None, 0, True),
]


def seed(apps, schema_editor):
    P2PBoxTier = apps.get_model('p2p', 'P2PBoxTier')
    for min_b, max_b, uplift, needs_quote in SEED_TIERS:
        P2PBoxTier.objects.get_or_create(
            min_boxes=min_b, max_boxes=max_b,
            defaults={'uplift': uplift, 'needs_quote': needs_quote, 'is_active': True},
        )


def unseed(apps, schema_editor):
    """Remove only the rows this migration created, never tiers ops added later."""
    P2PBoxTier = apps.get_model('p2p', 'P2PBoxTier')
    for min_b, max_b, _uplift, _quote in SEED_TIERS:
        P2PBoxTier.objects.filter(min_boxes=min_b, max_boxes=max_b).delete()


class Migration(migrations.Migration):

    dependencies = [('p2p', '0006_p2pboxtier')]

    operations = [migrations.RunPython(seed, unseed)]
