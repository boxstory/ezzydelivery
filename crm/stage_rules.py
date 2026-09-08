# Purpose: The picklist of driver conditions a staff-created board column can bind to, plus the evaluator that decides which column a driver card belongs in.
# Used by: crm/services.py (reconcile_driver_leads, driver_lead_target_stage), workforce/crm_views.py (stage manage form).
# Notes: Rules are evaluated right-to-left across columns (highest LeadStage.position first, first match wins), so terminal columns beat progress columns. DriverFacts memoizes the expensive section/delivery lookups per driver.

RULE_NO_DRIVER = 'no_driver'
RULE_UPLOADS_DONE = 'uploads_done'
RULE_HAS_DELIVERIES = 'has_deliveries'

# Group label → [(rule key, human label)]. Drives the checkbox groups on the
# stage manage page; the keys are what land in LeadStage.auto_rules.
RULE_GROUPS = [
    ('Application status', [
        ('verif:incomplete', 'Application not submitted (incomplete)'),
        ('verif:pending', 'Application submitted (pending)'),
        ('verif:under_review', 'Marked under review'),
        ('verif:verified', 'Verified / approved'),
        ('verif:rejected', 'Rejected'),
    ]),
    ('Driver record status', [
        ('dstatus:pending', 'Driver status: Pending'),
        ('dstatus:processing', 'Driver status: Processing'),
        ('dstatus:approved', 'Driver status: Approved'),
        ('dstatus:rejected', 'Driver status: Rejected'),
        ('dstatus:blocked', 'Driver status: Blocked'),
        ('dstatus:suspended', 'Driver status: Suspended'),
    ]),
    ('Progress', [
        (RULE_UPLOADS_DONE, 'Submitted AND every section + document complete'),
        (RULE_HAS_DELIVERIES, 'Has at least one delivery task'),
        (RULE_NO_DRIVER, 'No driver record matches this number yet'),
    ]),
]

RULE_LABELS = {key: label for _group, rules in RULE_GROUPS for key, label in rules}
VALID_RULES = set(RULE_LABELS)


class DriverFacts:
    """Lazily-computed answers about one driver, so evaluating several rules against
    the same driver never repeats the expensive section walk or delivery count."""

    def __init__(self, driver, delivery_count=None):
        self.driver = driver
        profile = getattr(driver, 'profile', None)
        self.verification_status = (getattr(profile, 'verification_status', '') or '') if profile else ''
        self.driver_status = driver.driver_status or ''
        self._delivery_count = delivery_count
        self._sections_done = None

    @property
    def sections_done(self):
        """True when every application section + required document is complete."""
        if self._sections_done is None:
            from workforce.views import _driver_application_sections
            try:
                sections = _driver_application_sections(self.driver)
                self._sections_done = bool(sections) and all(s['done'] for s in sections)
            except Exception:
                self._sections_done = False
        return self._sections_done

    @property
    def delivery_count(self):
        if self._delivery_count is None:
            # Prefer the annotation reconcile adds; only query as a last resort.
            annotated = getattr(self.driver, 'dl_task_count', None)
            self._delivery_count = (
                annotated if annotated is not None else self.driver.deliverytask.count()
            )
        return self._delivery_count


def rule_matches(rule, facts):
    """Does one rule key hold for this driver? Unknown keys never match."""
    if rule.startswith('verif:'):
        return facts.verification_status == rule.split(':', 1)[1]
    if rule.startswith('dstatus:'):
        return facts.driver_status == rule.split(':', 1)[1]
    if rule == RULE_UPLOADS_DONE:
        # "Uploads Completed" only means anything for a submitted application —
        # otherwise a half-filled form with every section blank-but-optional
        # would jump the queue.
        return facts.verification_status == 'pending' and facts.sections_done
    if rule == RULE_HAS_DELIVERIES:
        return facts.delivery_count > 0
    # RULE_NO_DRIVER is handled by the evaluator, not here — a driver exists by
    # definition once we have facts about them.
    return False


def _ordered(stages):
    """Columns right-to-left: the furthest-right matching column wins, which is
    what keeps Rejected/Approved ahead of Applied without a priority field."""
    return sorted(stages, key=lambda s: (s.position, s.pk or 0), reverse=True)


def _fallback_key(stages):
    for stage in stages:
        if stage.is_fallback:
            return stage.key
    ordered = _ordered(stages)
    return ordered[-1].key if ordered else None


def target_stage_key(driver, stages, delivery_count=None):
    """The column key this driver belongs in, or None when the board has no columns.

    `stages` is the active LeadStage rows for the driver board (any order).
    Manual columns (no auto_rules) are skipped — nothing is ever auto-placed there.
    """
    if not stages:
        return None
    ordered = _ordered(stages)

    if driver is None:
        for stage in ordered:
            if RULE_NO_DRIVER in (stage.auto_rules or []):
                return stage.key
        return _fallback_key(stages)

    facts = DriverFacts(driver, delivery_count=delivery_count)
    for stage in ordered:
        rules = [r for r in (stage.auto_rules or []) if r != RULE_NO_DRIVER]
        if not rules:
            continue
        if any(rule_matches(r, facts) for r in rules):
            return stage.key
    return _fallback_key(stages)


def manual_stage_keys(stages):
    """Keys of drag-only columns — reconcile must not pull cards out of these."""
    return {s.key for s in stages if not s.auto_rules}
