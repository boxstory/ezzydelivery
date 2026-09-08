# Purpose: Unified sales Lead model + staff-configurable pipeline stages + activity timeline + WAHA inbox dismissals.
# Used by: crm/services.py, crm/stage_rules.py, workforce/crm_views.py, crm/admin.py, backfill/digest management commands.
# Notes: Lead denormalizes contact fields from its source inquiry; OneToOne links keep creation idempotent.
#        Board columns live in LeadStage rows (one per board+key), NOT in Lead.STAGE_CHOICES — that
#        constant is only the legacy seed for the business board.

from django.core.cache import cache
from django.db import models
from django.utils import timezone

STAGE_CACHE_KEY = 'crm_lead_stages_v1'
STAGE_CACHE_TTL = 300


class Lead(models.Model):
    SOURCE_PRICING = 'pricing_inquiry'
    SOURCE_WA_FORM = 'whatsapp_form'
    SOURCE_WA_INBOUND = 'whatsapp_inbound'
    SOURCE_DRIVER_APP = 'driver_application'
    SOURCE_MANUAL = 'manual'
    SOURCE_CHOICES = [
        (SOURCE_PRICING, 'Pricing Inquiry'),
        (SOURCE_WA_FORM, 'WhatsApp Form'),
        (SOURCE_WA_INBOUND, 'WhatsApp Inbound'),
        (SOURCE_DRIVER_APP, 'Driver Application'),
        (SOURCE_MANUAL, 'Manual'),
    ]

    CATEGORY_BUSINESS = 'business'
    CATEGORY_DRIVER = 'driver'
    CATEGORY_CHOICES = [
        (CATEGORY_BUSINESS, 'Business'),
        (CATEGORY_DRIVER, 'Driver'),
    ]

    STAGE_NEW = 'new'
    STAGE_CONTACTED = 'contacted'
    STAGE_QUOTED = 'quoted'
    STAGE_NEGOTIATING = 'negotiating'
    STAGE_WON = 'won'
    STAGE_LOST = 'lost'
    STAGE_ON_HOLD = 'on_hold'
    STAGE_CHOICES = [
        (STAGE_NEW, 'New'),
        (STAGE_CONTACTED, 'Contacted'),
        (STAGE_QUOTED, 'Quoted'),
        (STAGE_NEGOTIATING, 'Negotiating'),
        (STAGE_WON, 'Won'),
        (STAGE_LOST, 'Lost'),
        (STAGE_ON_HOLD, 'On Hold'),
    ]
    CLOSED_STAGES = [STAGE_WON, STAGE_LOST]

    # Sentinel for `wa_session` meaning "show every number merged". Deliberately
    # not a legal WAHA session name (whatsapp.sessions._SESSION_RE rejects the
    # dunder), so a real session can never collide with it.
    WA_SESSION_ALL = '__all__'

    source = models.CharField(max_length=20, choices=SOURCE_CHOICES, default=SOURCE_MANUAL)
    # What kind of prospect this is: a business client or a driver applicant.
    category = models.CharField(
        max_length=20, choices=CATEGORY_CHOICES, default=CATEGORY_BUSINESS, db_index=True,
    )
    pricing_enquiry = models.OneToOneField(
        'webpages.PricingEnquiry', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='lead',
    )
    whatsapp_inquiry = models.OneToOneField(
        'webpages.WhatsAppInquiry', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='lead',
    )

    # Denormalized contact snapshot from the source inquiry (editable by staff)
    company_name = models.CharField(max_length=200, blank=True, default='')
    contact_name = models.CharField(max_length=100, blank=True, default='')
    phone = models.CharField(max_length=50, blank=True, default='', db_index=True)
    product_category = models.CharField(max_length=200, blank=True, default='')
    # Staff-set WhatsApp identifier (phone or lid) used when auto-matching by `phone`
    # misses or picks the wrong chat — see crm_lead_link_chat in workforce/crm_views.py.
    wa_chat_override = models.CharField(max_length=50, blank=True, default='')
    # Which of our WhatsApp numbers this lead's conversation runs on — a WAHA
    # session name, `WA_SESSION_ALL` for the merged all-numbers view, or blank
    # for "nobody has chosen yet". Drives both which thread the detail page
    # loads AND which number the composer sends from, so a driver contacted on
    # Ezzy6000 keeps answering on Ezzy6000. See workforce/crm_views.py.
    wa_session = models.CharField(max_length=64, blank=True, default='')

    # Key of a LeadStage row for this lead's category. `choices` stays for the seven
    # legacy keys so get_stage_display()/admin keep working; staff-created keys are
    # valid too (save() never validates choices) and resolve via `stage_label`.
    stage = models.CharField(max_length=20, choices=STAGE_CHOICES, default=STAGE_NEW, db_index=True)
    assigned_to = models.ForeignKey(
        'auth.User', null=True, blank=True, on_delete=models.SET_NULL,
        related_name='assigned_crm_leads',
    )
    next_followup_at = models.DateField(null=True, blank=True, db_index=True)
    converted_business = models.ForeignKey(
        'business.Business', null=True, blank=True, on_delete=models.SET_NULL,
        related_name='crm_leads',
    )
    notes = models.TextField(blank=True, default='')

    # AI-generated conversation summary (workforce lead detail page)
    ai_summary = models.TextField(blank=True, default='')
    ai_summary_at = models.DateTimeField(null=True, blank=True)

    # Duplicate handling: the same prospect arriving twice (a pricing form AND a
    # WhatsApp chat, or a driver application AND an inbox promote) becomes ONE card
    # holding both. The absorbed lead is NOT deleted — it keeps its own source, its
    # own inquiry link and its own timeline, and renders as a sub-card inside the
    # surviving one, so a wrong merge is undoable.
    merged_into = models.ForeignKey(
        'self', null=True, blank=True, on_delete=models.SET_NULL,
        related_name='merged_children', db_index=True,
    )
    merged_at = models.DateTimeField(null=True, blank=True)
    merged_by = models.ForeignKey(
        'auth.User', null=True, blank=True, on_delete=models.SET_NULL,
        related_name='merged_crm_leads',
    )

    # The applicant this driver card is about. Authoritative — phone matching is only
    # used to FIND the driver once, then this binding is what the board, the detail
    # page and the verification write-back all read, so they cannot disagree. Two
    # drivers sharing a number (a duplicate registration) get one card each.
    driver = models.ForeignKey(
        'fleet.Driver', null=True, blank=True, on_delete=models.SET_NULL,
        related_name='crm_leads',
    )

    # A staff member moved this card somewhere the driver's real application status
    # does not justify. Reconcile leaves pinned cards alone, so the manual position
    # wins until staff resume auto-filing. Only ever set for driver leads.
    stage_pinned = models.BooleanField(default=False, db_index=True)
    stage_pinned_at = models.DateTimeField(null=True, blank=True)

    stage_changed_at = models.DateTimeField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Lead'
        verbose_name_plural = 'Leads'
        indexes = [
            models.Index(fields=['stage', 'next_followup_at']),
        ]

    def __str__(self):
        return f"{self.company_name or self.contact_name or self.phone} ({self.stage_label})"

    @property
    def stage_label(self):
        """Board-correct column name — a driver lead in `won` reads "Approved",
        a business lead in `won` reads "Won". Falls back to the legacy choices."""
        label = LeadStage.label_map().get((self.category, self.stage))
        return label or self.get_stage_display()

    @property
    def stage_swatch(self):
        """Palette name for the stage badge, so staff-created stages get a colour
        without a new CSS rule per key."""
        return LeadStage.swatch_map().get((self.category, self.stage), 'grey')

    @property
    def is_merged(self):
        """This lead has been absorbed into another card and must not be listed on
        its own — it renders inside its parent instead."""
        return self.merged_into_id is not None

    @property
    def source_badges(self):
        """Every origin this card represents: its own, plus each absorbed lead's.
        A merged card legitimately says "Pricing Inquiry + WhatsApp Inbound"."""
        seen, badges = set(), []
        for lead in [self] + list(self.merged_children.all()):
            if lead.source in seen:
                continue
            seen.add(lead.source)
            badges.append({'key': lead.source, 'label': lead.get_source_display()})
        return badges

    @property
    def is_open(self):
        return self.stage not in LeadStage.closed_keys(self.category)

    @property
    def is_overdue(self):
        return bool(
            self.next_followup_at
            and self.next_followup_at < timezone.localdate()
            and self.is_open
        )


class LeadStage(models.Model):
    """One kanban column on one board. Staff manage these at /workforce/crm/stages/ —
    adding a column no longer needs a code change or a migration.

    A row is scoped to a board (`category`), so a driver-only column never appears on
    the business board even though both share the `Lead.stage` value space.

    `auto_rules` is what makes a driver card land here by itself: a list of rule keys
    from crm.stage_rules.RULES, evaluated right-to-left (highest `position` first,
    first match wins) so terminal columns beat progress columns. An **empty**
    `auto_rules` makes the column a manual lane — reconcile never moves a card into or
    out of it, so a staff drag sticks.
    """

    # Mirrors core.models.Profile.VERIFICATION_STATUS_CHOICES without importing it.
    WRITE_BACK_CHOICES = [
        ('', 'Nothing — board-only column'),
        ('pending', 'Driver: Pending Verification'),
        ('under_review', 'Driver: Under Review'),
        ('verified', 'Driver: Verified / Approved'),
        ('rejected', 'Driver: Rejected'),
    ]

    # Fixed palette — the swatch is a CSS class, never an inline style (CLAUDE.md).
    SWATCH_CHOICES = [
        ('grey', 'Grey'), ('slate', 'Slate'), ('blue', 'Blue'), ('teal', 'Teal'),
        ('green', 'Green'), ('forest', 'Forest'), ('violet', 'Violet'),
        ('amber', 'Amber'), ('red', 'Red'),
    ]

    category = models.CharField(
        max_length=20, choices=Lead.CATEGORY_CHOICES, default=Lead.CATEGORY_BUSINESS,
        help_text='Which board this column belongs to.',
    )
    # Stored in Lead.stage — must fit that field's max_length=20.
    key = models.SlugField(max_length=20)
    label = models.CharField(max_length=60)
    position = models.PositiveIntegerField(default=0, help_text='Left-to-right order on the board.')

    is_closed = models.BooleanField(
        default=False,
        help_text='Terminal column — stamps closed_at and drops out of the Open total.',
    )
    hide_after_days = models.PositiveIntegerField(
        null=True, blank=True,
        help_text='Hide cards this many days after they closed. Blank = never hide.',
    )
    is_fallback = models.BooleanField(
        default=False,
        help_text='Where a driver with no matching rule lands. Exactly one per board.',
    )
    auto_rules = models.JSONField(
        default=list, blank=True,
        help_text='Rule keys from crm.stage_rules. Empty = manual drag-only column.',
    )

    write_back = models.CharField(max_length=20, choices=WRITE_BACK_CHOICES, blank=True, default='')
    confirm_text = models.CharField(
        max_length=120, blank=True, default='',
        help_text='Asks staff to confirm before the drop, e.g. "approve this driver".',
    )
    needs_reason = models.BooleanField(
        default=False, help_text='Prompt for a reason before writing back (rejections).',
    )
    crm_status = models.CharField(
        max_length=20, blank=True, default='',
        help_text='Legacy PricingEnquiry.crm_status to mirror. Blank = do not mirror.',
    )

    dot_swatch = models.CharField(max_length=10, choices=SWATCH_CHOICES, default='grey')
    is_system = models.BooleanField(
        default=False, help_text='Seeded column — editable but not deletable.',
    )
    is_active = models.BooleanField(default=True, help_text='Untick to hide without deleting.')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['category', 'position', 'pk']
        unique_together = [('category', 'key')]
        verbose_name = 'Lead Stage (board column)'
        verbose_name_plural = 'Lead Stages (board columns)'

    def __str__(self):
        return f"{self.get_category_display()} · {self.label}"

    @property
    def is_manual(self):
        return not self.auto_rules

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        cache.delete(STAGE_CACHE_KEY)

    def delete(self, *args, **kwargs):
        result = super().delete(*args, **kwargs)
        cache.delete(STAGE_CACHE_KEY)
        return result

    # ── Cached lookups (called per-lead from Lead properties, so never per-row SQL) ──

    @classmethod
    def _cached(cls):
        """{'labels': {(category, key): label}, 'closed': {category: [keys]}}.

        Cached because Lead.is_open / Lead.stage_label run once per card on a board
        render. Explicitly busted on save/delete; the TTL bounds staleness for the
        other gunicorn workers when the cache backend is per-process locmem.
        """
        data = cache.get(STAGE_CACHE_KEY)
        if data is None:
            labels, swatches, closed = {}, {}, {}
            for cat, key, label, is_closed, swatch in cls.objects.values_list(
                'category', 'key', 'label', 'is_closed', 'dot_swatch'
            ):
                labels[(cat, key)] = label
                swatches[(cat, key)] = swatch
                if is_closed:
                    closed.setdefault(cat, []).append(key)
            data = {'labels': labels, 'swatches': swatches, 'closed': closed}
            cache.set(STAGE_CACHE_KEY, data, STAGE_CACHE_TTL)
        return data

    @classmethod
    def label_map(cls):
        return cls._cached()['labels']

    @classmethod
    def swatch_map(cls):
        return cls._cached()['swatches']

    @classmethod
    def closed_keys(cls, category=None):
        """Terminal stage keys — for one board, or every board when category is None.
        Falls back to Lead.CLOSED_STAGES before the stages are seeded."""
        closed = cls._cached()['closed']
        if not closed:
            return set(Lead.CLOSED_STAGES)
        if category is None:
            return {k for keys in closed.values() for k in keys}
        return set(closed.get(category, ()))

    @classmethod
    def board_columns(cls, category):
        """Active columns for one board, left→right. One query."""
        return list(cls.objects.filter(category=category, is_active=True).order_by('position', 'pk'))


class LeadActivity(models.Model):
    TYPE_NOTE = 'note'
    TYPE_FOLLOWUP = 'followup'
    TYPE_STAGE_CHANGE = 'stage_change'
    TYPE_ASSIGNMENT = 'assignment'
    TYPE_CONVERSION = 'conversion'
    TYPE_CHOICES = [
        (TYPE_NOTE, 'Note'),
        (TYPE_FOLLOWUP, 'Follow-up'),
        (TYPE_STAGE_CHANGE, 'Stage Change'),
        (TYPE_ASSIGNMENT, 'Assignment'),
        (TYPE_CONVERSION, 'Conversion'),
    ]

    lead = models.ForeignKey(Lead, on_delete=models.CASCADE, related_name='activities')
    activity_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default=TYPE_NOTE)
    body = models.TextField()
    created_by = models.ForeignKey('auth.User', null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name_plural = 'Lead Activities'

    def __str__(self):
        return f"{self.get_activity_type_display()} on {self.lead}"


class InboxDismissal(models.Model):
    # Hides a WAHA inbox number marked "not a lead" without touching
    # WhatsAppMessage.status, which belongs to the address-verification pipeline.
    phone = models.CharField(max_length=50, unique=True)
    dismissed_by = models.ForeignKey('auth.User', null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'WA Inbox Dismissal'
        verbose_name_plural = 'WA Inbox Dismissals'

    def __str__(self):
        return self.phone
