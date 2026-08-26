# Purpose: Give the driver board its own stage keys and stamp won/lost outcomes on every terminal column.
# Used by: `python manage.py migrate crm` — one atomic pass over LeadStage rows and the driver Leads sitting on them.
# Notes: The driver board used to borrow the business keys (quoted = "Uploads Completed", won = "Approved"), so the two
#        boards were only separated by `category`. Renaming is data-only — Lead.stage is a free CharField — but the
#        LeadStage row and every Lead pointing at it must move together or the cards land in the Unsorted lane.

from django.db import migrations

# (old key, new key). Disjoint sets, so no unique_together (category, key) collision
# mid-rename. `temujob_accepted` was already board-specific and is left alone.
DRIVER_KEY_RENAMES = [
    ('new', 'new_app'),
    ('contacted', 'applied'),
    ('on_hold', 'incomplete'),
    ('quoted', 'uploads_done'),
    ('aproched', 'approached'),        # staff-created, misspelt at creation
    ('negotiating', 'under_review'),
    ('won', 'approved'),
    ('lost', 'rejected'),
]

# Which terminal column each board counts as a win or a loss. Read by reports and
# by the lead_won / lead_lost auto-flows, which used to test the literal key 'won'.
OUTCOMES = [
    ('business', 'won', 'won'),
    ('business', 'lost', 'lost'),
    ('driver', 'approved', 'won'),
    ('driver', 'rejected', 'lost'),
]

OUTCOMES_REVERSE = [
    ('business', 'won', 'won'),
    ('business', 'lost', 'lost'),
    ('driver', 'won', 'won'),
    ('driver', 'lost', 'lost'),
]


def _apply(apps, renames, outcomes):
    LeadStage = apps.get_model('crm', 'LeadStage')
    Lead = apps.get_model('crm', 'Lead')

    for old_key, new_key in renames:
        stage = LeadStage.objects.filter(category='driver', key=old_key).first()
        if stage is None:
            continue
        # A row already sitting on the destination key means this ran before.
        if LeadStage.objects.filter(category='driver', key=new_key).exists():
            continue
        stage.key = new_key
        stage.save(update_fields=['key'])
        Lead.objects.filter(category='driver', stage=old_key).update(stage=new_key)

    for category, key, outcome in outcomes:
        LeadStage.objects.filter(category=category, key=key).update(outcome=outcome)


def forwards(apps, schema_editor):
    _apply(apps, DRIVER_KEY_RENAMES, OUTCOMES)


def backwards(apps, schema_editor):
    _apply(apps, [(new, old) for old, new in DRIVER_KEY_RENAMES], OUTCOMES_REVERSE)


class Migration(migrations.Migration):

    dependencies = [
        ('crm', '0011_leadstage_outcome'),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
