# Purpose: Seed the 14 LeadStage rows (7 business + 7 driver) that reproduce the previously hardcoded board columns bit-for-bit.
# Used by: `python manage.py migrate crm` — runs once; re-running is a no-op thanks to update_or_create on (category, key).
# Notes: Driver labels/order/rules mirror the old DRIVER_STAGE_LABELS + driver_lead_target_stage exactly; swatches mirror the old per-key dot colours in crm.css. `verified`+`blocked` still lands in Rejected here on purpose — parity first; staff can add a Blocked column afterwards.

from django.db import migrations

# (key, label, position, is_closed, hide_after_days, is_fallback, auto_rules,
#  write_back, confirm_text, needs_reason, crm_status, dot_swatch)
BUSINESS_STAGES = [
    ('new',         'New',         1, False, None, True,  [], '', '', False, 'new',         'blue'),
    ('contacted',   'Contacted',   2, False, None, False, [], '', '', False, 'contacted',   'green'),
    ('quoted',      'Quoted',      3, False, None, False, [], '', '', False, 'quoted',      'violet'),
    ('negotiating', 'Negotiating', 4, False, None, False, [], '', '', False, 'negotiating', 'amber'),
    ('won',         'Won',         5, True,    30, False, [], '', '', False, 'converted',   'forest'),
    ('lost',        'Lost',        6, True,    30, False, [], '', '', False, 'lost',        'red'),
    ('on_hold',     'On Hold',     7, False, None, False, [], '', '', False, 'on_hold',     'grey'),
]

DRIVER_STAGES = [
    ('new',         'New Application',   1, False, None, False,
     ['no_driver'], '', '', False, '', 'blue'),
    ('contacted',   'Applied',           2, False, None, False,
     ['verif:pending'], '', '', False, '', 'green'),
    ('on_hold',     'Incomplete',        3, False, None, True,
     ['verif:incomplete'], '', '', False, '', 'grey'),
    ('quoted',      'Uploads Completed', 4, False, None, False,
     ['uploads_done'], '', '', False, '', 'violet'),
    ('negotiating', 'Under Review',      5, False, None, False,
     ['verif:under_review'], 'under_review', 'mark this driver under review', False, '', 'amber'),
    ('won',         'Approved',          6, True,    30, False,
     ['verif:verified', 'dstatus:approved'], 'verified', 'approve this driver', False, '', 'forest'),
    ('lost',        'Rejected',          7, True,    30, False,
     ['verif:rejected', 'dstatus:rejected', 'dstatus:blocked', 'dstatus:suspended'],
     'rejected', 'reject this driver', True, '', 'red'),
]

FIELDS = (
    'label', 'position', 'is_closed', 'hide_after_days', 'is_fallback', 'auto_rules',
    'write_back', 'confirm_text', 'needs_reason', 'crm_status', 'dot_swatch',
)


def seed(apps, schema_editor):
    LeadStage = apps.get_model('crm', 'LeadStage')
    for category, rows in (('business', BUSINESS_STAGES), ('driver', DRIVER_STAGES)):
        for row in rows:
            key, values = row[0], row[1:]
            LeadStage.objects.update_or_create(
                category=category, key=key,
                defaults={**dict(zip(FIELDS, values)), 'is_system': True, 'is_active': True},
            )


def unseed(apps, schema_editor):
    LeadStage = apps.get_model('crm', 'LeadStage')
    LeadStage.objects.filter(is_system=True).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('crm', '0005_leadstage'),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]
