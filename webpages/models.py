"""
Webpages Models Module
======================

This module contains models for public website forms and inquiries.

Models:
    - ContactUs: General contact form submissions
    - Careers: Job application submissions
    - PricingEnquiry: Detailed pricing inquiry (multi-step form)
    - WhatsAppInquiry: Quick inquiry via WhatsApp
    - DeliveryRequest: One-time delivery requests from non-business users

Related:
    - webpages.views: Form handling views
    - webpages.forms: Form classes for these models
"""

import re as _re
import uuid

from django.conf import settings
from django.db import models

from core.email_normalize import EmailNormalizedModel


# =============================================================================
# CONTACT US MODEL
# =============================================================================


class ContactUs(EmailNormalizedModel, models.Model):
    """
    General contact form submissions from website visitors.

    Purpose Options:
        - Delivery Request
        - Fulfillment Request
        - Affiliate Marketing Program
        - Driver Jobs
        - Feedback
        - Other

    Usage:
        Visitors fill out form on /contact page, data saved here
        for admin review and follow-up.

    Admin:
        Accessible in Django admin under "Contact Us"
    """
    EMAIL_FIELDS = ('email',)

    full_name = models.CharField(max_length=100)
    email = models.EmailField()
    mobile = models.BigIntegerField()
    purpose = models.CharField(max_length=100)
    message = models.TextField()
    date = models.DateField(auto_now_add=True)

    def __str__(self):
        return self.full_name

    class Meta:
        verbose_name_plural = "Contact Us"


# =============================================================================
# CAREERS MODEL
# =============================================================================


class Careers(EmailNormalizedModel, models.Model):
    """
    Job application submissions from the careers page.

    Validation:
        - QID must be 11 digits starting with 2 or 3 (Qatar ID format)

    Fields:
        - full_name: Applicant's name
        - email: Contact email
        - mobile: Contact phone
        - qid: Qatar ID number (validated)
        - job: Position applying for
        - self_intro: Cover letter / introduction

    Admin:
        Accessible in Django admin under "Careers"
    """
    EMAIL_FIELDS = ('email',)

    full_name = models.CharField(max_length=100)
    email = models.EmailField()
    mobile = models.BigIntegerField()
    qid = models.BigIntegerField()
    job = models.CharField(max_length=100)
    self_intro = models.TextField()
    date = models.DateField(auto_now_add=True)

    def __str__(self):
        return self.full_name

    class Meta:
        verbose_name_plural = "Careers"


# =============================================================================
# PRICING PLAN CATALOGUE
# =============================================================================


class PricingPlanOption(models.Model):
    """
    A quotable plan shown on the post-submission price table.

    The catalogue lives in the DB rather than in the template so the sales desk
    can change a rate, retire a plan or add a seasonal one from the admin
    without a deploy. What a customer agreed to is never read back from here —
    `PricingEnquiry` snapshots the name and price at agreement time, so editing
    a row later cannot rewrite an agreement that already happened.

    A row with `is_custom_quote` carries no number: it is the "discuss with the
    sales team" choice, and picking it records intent to talk, not a price.
    """
    key = models.SlugField(max_length=50, unique=True,
                           help_text="Stable identifier posted by the form. Do not rename in use.")
    name = models.CharField(max_length=100)
    subtitle = models.CharField(max_length=150, blank=True, null=True)
    description = models.TextField(blank=True, null=True)

    # Display string is authoritative for what the customer sees ("25", "Let's talk").
    # price_value is the same number for reporting and is left empty for custom quotes.
    price_display = models.CharField(max_length=30, blank=True, null=True)
    price_unit = models.CharField(max_length=60, blank=True, null=True,
                                  help_text="e.g. 'QR per delivery'")
    price_value = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)

    features = models.TextField(
        blank=True, null=True,
        help_text="One feature per line — rendered as the ticked list on the card.")
    is_custom_quote = models.BooleanField(
        default=False,
        help_text="No fixed price — selecting it means 'contact me to agree a rate'.")

    badge = models.CharField(max_length=30, blank=True, null=True,
                             help_text="Ribbon text, e.g. 'Most Popular'. Leave empty for none.")
    is_featured = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True, null=True)
    updated_at = models.DateTimeField(auto_now=True, null=True)

    class Meta:
        ordering = ['sort_order', 'id']
        verbose_name = "Pricing Plan Option"
        verbose_name_plural = "Pricing Plan Options"

    def __str__(self):
        return self.name

    @property
    def feature_list(self):
        """Non-empty feature lines — templates cannot split on newlines."""
        return [line.strip() for line in (self.features or '').splitlines() if line.strip()]

    @property
    def price_label(self):
        """'25 QR per delivery' / 'Let's talk — custom quote' for one-line summaries."""
        bits = [b for b in ((self.price_display or '').strip(), (self.price_unit or '').strip()) if b]
        return ' '.join(bits) or 'Custom quote'


# =============================================================================
# RATE CARD — the rules behind a suggested price
# =============================================================================


class PricingRuleSet(models.Model):
    """
    A versioned rate card. Exactly one is active; suggestions snapshot which.

    Kept as data rather than code for the same reason as `PricingPlanOption`:
    the sales desk changes rates without a deploy. Versioning matters more here
    though — a suggestion made last month must stay explainable after the card
    is edited, so `PricingSuggestion` records the code it was computed under.
    """
    FLOOR_CONFIG = 'config'
    FLOOR_MEASURED = 'measured'
    FLOOR_BASIS_CHOICES = [
        (FLOOR_CONFIG, 'Configured constant (not a measured cost)'),
        (FLOOR_MEASURED, 'Measured cost to serve'),
    ]

    ROUND_NEAREST = 'nearest'
    ROUND_UP = 'up'
    ROUNDING_CHOICES = [(ROUND_NEAREST, 'Nearest'), (ROUND_UP, 'Always up')]

    code = models.SlugField(max_length=50, unique=True)
    name = models.CharField(max_length=120)
    notes = models.TextField(blank=True, null=True)
    is_active = models.BooleanField(
        default=False, help_text="Only one rate card can be active. Activating this deactivates the rest.")

    base_price_default = models.DecimalField(
        max_digits=10, decimal_places=2, default=25,
        help_text="Used when volume or distance is unknown. Quote high and discount — "
                  "the opposite error is unrecoverable.")
    min_price_floor = models.DecimalField(
        max_digits=10, decimal_places=2, default=15,
        help_text="Lowest price the engine will suggest. This is a CONFIGURED CONSTANT, "
                  "not a measured cost to serve — see floor basis.")
    floor_basis = models.CharField(max_length=10, choices=FLOOR_BASIS_CHOICES, default=FLOOR_CONFIG)

    rounding_step = models.DecimalField(max_digits=6, decimal_places=2, default=1)
    rounding_mode = models.CharField(max_length=10, choices=ROUNDING_CHOICES, default=ROUND_NEAREST)
    max_total_discount_pct = models.DecimalField(max_digits=5, decimal_places=2, default=40)
    max_total_uplift_pct = models.DecimalField(max_digits=5, decimal_places=2, default=60)

    created_at = models.DateTimeField(auto_now_add=True, null=True)
    updated_at = models.DateTimeField(auto_now=True, null=True)

    class Meta:
        ordering = ['-is_active', 'code']
        verbose_name = "Rate Card"
        verbose_name_plural = "Rate Cards"

    def __str__(self):
        return f"{self.name}{'' if self.is_active else ' (inactive)'}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # Single-active invariant. Done after save so the row being activated is
        # never the one switched off.
        if self.is_active:
            PricingRuleSet.objects.filter(is_active=True).exclude(pk=self.pk).update(is_active=False)

    @property
    def can_report_margin(self):
        """The one gate that stops any screen implying we know our margin.

        False while the floor is a configured guess — which it is until driver
        earnings are actually measured per task.
        """
        return self.floor_basis == self.FLOOR_MEASURED


class PricingRule(models.Model):
    """
    One line of a rate card: a base price, or an adjustment to it.

    A single table for every dimension so the sales desk edits one changelist
    and the engine stays one loop. Within a dimension, rules are tried in
    `priority` order and the first match wins unless `stop_on_match` is off.
    """
    DIM_BASE = 'volume_distance_base'
    DIMENSION_CHOICES = [
        (DIM_BASE, 'Base — volume x distance'),
        ('weight', 'Weight'),
        ('size', 'Package size'),
        ('speed', 'Delivery speed'),
        ('cod', 'Cash on delivery'),
        ('special_handling', 'Special handling'),
        ('returns', 'Return logistics'),
        ('pickup_locations', 'Pickup locations'),
        ('pickups_per_day', 'Pickups per day'),
    ]

    KIND_NUMERIC = 'numeric_range'
    KIND_BAND = 'band_exact'
    KIND_BOOL = 'boolean_true'
    KIND_CONTAINS = 'contains'
    KIND_ALWAYS = 'always'
    MATCH_KIND_CHOICES = [
        (KIND_NUMERIC, 'Numeric range'),
        (KIND_BAND, 'Exact band'),
        (KIND_BOOL, 'Boolean is true'),
        (KIND_CONTAINS, 'List contains'),
        (KIND_ALWAYS, 'Always'),
    ]

    EFFECT_SET_BASE = 'set_base'
    EFFECT_ADD = 'add'
    EFFECT_PCT = 'pct'
    EFFECT_CHOICES = [
        (EFFECT_SET_BASE, 'Set base price'),
        (EFFECT_ADD, 'Add QR'),
        (EFFECT_PCT, '% of base'),
    ]

    ruleset = models.ForeignKey(PricingRuleSet, on_delete=models.CASCADE, related_name='rules')
    dimension = models.CharField(max_length=30, choices=DIMENSION_CHOICES)

    match_field = models.CharField(
        max_length=50, help_text="Normalised input key, e.g. monthly_orders, weight_mid_kg.")
    match_kind = models.CharField(max_length=20, choices=MATCH_KIND_CHOICES, default=KIND_NUMERIC)
    match_value = models.CharField(max_length=120, blank=True, null=True)
    match_min = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)
    match_max = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True,
                                    help_text="Exclusive upper bound. Leave empty for open-ended.")
    # Second axis for the base matrix — a base rule matches on volume AND distance.
    match2_field = models.CharField(max_length=50, blank=True, null=True)
    match2_min = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)
    match2_max = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)

    effect = models.CharField(max_length=10, choices=EFFECT_CHOICES, default=EFFECT_ADD)
    amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    label = models.CharField(max_length=120, help_text="The line sales reads on the breakdown.")
    explanation = models.TextField(blank=True, null=True, help_text="Where this rate came from.")

    priority = models.PositiveIntegerField(default=100)
    stop_on_match = models.BooleanField(
        default=True, help_text="Off means later rules in the same dimension can also apply (they stack).")
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True, null=True)
    updated_at = models.DateTimeField(auto_now=True, null=True)

    class Meta:
        ordering = ['ruleset', 'dimension', 'priority', 'id']
        indexes = [models.Index(fields=['ruleset', 'dimension', 'priority'])]
        verbose_name = "Rate Card Rule"
        verbose_name_plural = "Rate Card Rules"

    def __str__(self):
        return f"{self.get_dimension_display()} — {self.label}"


class PricingSuggestion(models.Model):
    """
    One computed suggestion, stored rather than recomputed on demand.

    Rates change, so a suggestion has to keep the number, the inputs and the
    rule version AS THEY WERE — otherwise suggested-vs-agreed accuracy can
    never be measured, which is the whole point of keeping the history.
    """
    ACTION_NONE = 'none'
    ACTION_ACCEPTED = 'accepted'
    ACTION_OVERRIDDEN = 'overridden'
    ACTION_REJECTED = 'rejected'
    ACTION_CHOICES = [
        (ACTION_NONE, 'No action yet'),
        (ACTION_ACCEPTED, 'Accepted as quoted'),
        (ACTION_OVERRIDDEN, 'Overridden by staff'),
        (ACTION_REJECTED, 'Rejected'),
    ]

    inquiry = models.ForeignKey('PricingEnquiry', on_delete=models.CASCADE, related_name='suggestions')
    ruleset = models.ForeignKey(PricingRuleSet, on_delete=models.PROTECT, related_name='suggestions')
    ruleset_code = models.CharField(max_length=50)

    inputs_snapshot = models.JSONField(default=dict)
    inputs_hash = models.CharField(max_length=64, db_index=True)
    breakdown = models.JSONField(default=list, help_text="Ordered line items with running total.")

    base_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    suggested_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    clamped_reason = models.CharField(max_length=120, blank=True, null=True)
    floor_value = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    floor_basis = models.CharField(max_length=10, blank=True, null=True)

    comparable_median = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    comparable_p25 = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    comparable_p75 = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    comparable_sample = models.PositiveIntegerField(default=0)
    benchmark_midpoint = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    flags = models.JSONField(default=list)
    rationale_text = models.TextField(blank=True, null=True)
    rationale_source = models.CharField(max_length=20, default='template')

    generated_by = models.ForeignKey('auth.User', null=True, blank=True, on_delete=models.SET_NULL,
                                     related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)

    # Feedback loop — how sales actually responded to this number.
    staff_action = models.CharField(max_length=20, choices=ACTION_CHOICES, default=ACTION_NONE)
    staff_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    staff_note = models.TextField(blank=True, null=True)
    acted_by = models.ForeignKey('auth.User', null=True, blank=True, on_delete=models.SET_NULL,
                                 related_name='+')
    acted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Pricing Suggestion"
        verbose_name_plural = "Pricing Suggestions"

    def __str__(self):
        price = self.suggested_price if self.suggested_price is not None else 'no price'
        return f"#{self.inquiry_id} — {price} ({self.ruleset_code})"


# =============================================================================
# PRICING ENQUIRY MODEL
# =============================================================================


class PricingEnquiry(EmailNormalizedModel, models.Model):
    """
    Detailed pricing inquiry from potential business stores.

    Multi-step form capturing comprehensive business information
    to provide customized delivery pricing quotes.

    Field Groups:
        Personal Information:
            - full_name, business_name, contact numbers

        Contact Information:
            - website_url, social_profile

        Product Information:
            - product_category, is_personalized_product

        Company Status:
            - is_registered_company_in_qatar
            - is_located_in_qatar
            - is_team_available_in_qatar

        Service Requirements:
            - is_required_COD_service
            - is_required_fulfillment_service_*

        Order Volumes:
            - avarage_number_of_order_* (weekly, monthly, expected)

        Delivery Details:
            - speed_delivery_offer_to_customers
            - preferred_delivery_time_window
            - typical_package_size

        Pickup Information:
            - type_of_pickup_location (Home/Office/Store/Fulfillment)
            - pickup_Location_area_name
            - pickup_location_time_slab

    Admin:
        Accessible in Django admin under "Pricing Inquiries"
    """
    EMAIL_FIELDS = ('email',)

    # Personal Information
    full_name = models.CharField(max_length=100)
    business_name = models.CharField(max_length=100)
    business_contact_number = models.CharField(max_length=100)
    operation_team_contact_number = models.CharField(max_length=100, blank=True, null=True)
    email = models.EmailField(max_length=254, blank=True, null=True)  # optional — for sending the quote

    # Contact Information
    website_url = models.CharField(max_length=200, blank=True, null=True)
    instagram_profile = models.CharField(max_length=200, blank=True, null=True)
    facebook_profile = models.CharField(max_length=200, blank=True, null=True)
    social_profile = models.CharField(max_length=200, blank=True, null=True)  # legacy

    # Product Information
    product_category = models.CharField(max_length=200)
    is_personalized_product = models.BooleanField(default=False)

    # company Information
    is_registered_company_in_qatar = models.BooleanField(default=False)
    is_located_in_qatar = models.BooleanField(default=False)
    is_team_available_in_qatar = models.BooleanField(default=False)

    # Service Information
    is_required_COD_service = models.BooleanField(default=False)
    is_required_fulfillment_service_for_operate_from_outside_qatar = models.BooleanField(default=False)
    is_required_fulfillment_service_for_make_hub_in_doha = models.BooleanField(default=False)

    # Order Information
    avarage_number_of_order_last_week = models.CharField(blank=True, null=True, max_length=20)
    avarage_number_of_order_done_last_month = models.CharField(blank=True, null=True, max_length=20)
    avarage_number_of_order_expect_next_month = models.CharField(blank=True, null=True, max_length=20)
    orders_expected_in_next_3_months_milestone = models.CharField(blank=True, null=True, max_length=20)


    # Delivery Information
    speed_delivery_offer_to_customers = models.CharField(max_length=200, blank=True, null=True)
    is_frequent_same_day_pick_and_delivery_required = models.BooleanField(default=False)

    # Additional Relevant Questions for Last Mile Delivery
    preferred_delivery_time_window = models.CharField(max_length=200, blank=True, null=True)
    typical_package_size = models.CharField(max_length=100, blank=True, null=True)
    is_special_handling_required = models.BooleanField(default=False)

    # pickup Information
    type_of_pickup_location = models.CharField(max_length=200, blank=True, null=True)
    pickup_Location_area_name = models.CharField(max_length=200, blank=True, null=True)
    pickup_location_time_slab = models.CharField(max_length=200, blank=True, null=True)
    number_of_pickup_times_in_day = models.CharField(max_length=200, default='1', blank=True, null=True)

    # Product value — added to step 1
    average_order_value_qar = models.CharField(max_length=50, blank=True, null=True)  # e.g. "Below 100", "100-500"
    business_operating_age = models.CharField(max_length=50, blank=True, null=True)  # New / <1yr / 1-3yrs / 3yr+
    business_location_country = models.CharField(max_length=100, blank=True, null=True)  # shown when not in Qatar

    # Operations & Orders — extended fields
    current_courier_provider = models.CharField(max_length=200, blank=True, null=True)
    is_return_logistics_required = models.BooleanField(default=False)
    delivery_coverage = models.CharField(max_length=50, blank=True, null=True)  # Doha Only / All Qatar / Both
    preferred_start_date = models.CharField(max_length=50, blank=True, null=True)  # stored as string e.g. "Within 1 month"

    # Delivery & Pickup — extended fields
    order_management_system = models.CharField(max_length=200, blank=True, null=True)  # Shopify / WooCommerce / etc.
    preferred_communication_channel = models.CharField(max_length=100, blank=True, null=True)  # WhatsApp / Email / Phone
    is_delivery_free_to_customers = models.CharField(max_length=50, blank=True, null=True)  # Free / Paid / Mixed
    preferred_pickup_time = models.CharField(max_length=100, blank=True, null=True)  # e.g. "Morning", "Afternoon", "Evening", "Flexible"
    preferred_payment_method = models.CharField(max_length=100, blank=True, null=True)  # e.g. "Cash", "Bank Transfer", "Card", "Mixed"

    # Pricing-relevant detail fields
    cod_orders_share = models.CharField(max_length=50, blank=True, null=True)             # shown when COD = Yes; e.g. "Below 25%"
    # The rate matrix is priced per distance band, so this is the single most
    # load-bearing answer on the form for a suggested price.
    typical_delivery_distance = models.CharField(max_length=50, blank=True, null=True)    # e.g. "10-15 km", "Not sure"
    fulfillment_storage_volume = models.CharField(max_length=100, blank=True, null=True)  # shown when Doha hub = Yes; e.g. "1-5 pallets"
    current_delivery_cost = models.CharField(max_length=50, blank=True, null=True)        # optional benchmark; e.g. "10-15 QAR"
    special_handling_detail = models.CharField(max_length=200, blank=True, null=True)     # shown when special handling = Yes; multi e.g. "Fragile, Chilled / Frozen"
    average_package_weight = models.CharField(max_length=50, blank=True, null=True)       # e.g. "1-5 kg"
    number_of_pickup_locations = models.CharField(max_length=20, blank=True, null=True)   # shown when pickup type = Multiple Store
    additional_notes = models.TextField(blank=True, null=True)
    contact_consent = models.BooleanField(default=False)

    # Completion status — False for partial (in-progress), True for fully submitted
    is_complete = models.BooleanField(default=False)
    # Set when the "you left the form half-finished" WhatsApp nudge goes out, so
    # a lead is never messaged about the same abandoned form twice.
    resume_nudge_sent_at = models.DateTimeField(blank=True, null=True)

    # ── Quote selection ───────────────────────────────────────────────────────
    # After submitting, the sender lands on a price table and picks a plan. The
    # page is reachable by this token alone, never by pk: it is handed to an
    # anonymous visitor and a sequential id would let anyone walk the table.
    quote_token = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, null=True)
    selected_plan = models.ForeignKey(
        PricingPlanOption, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='agreements'
    )
    # Snapshot of the plan as it read the moment they agreed. Kept separately
    # from the FK so a later price edit in the catalogue cannot silently change
    # what this customer is on record as having accepted.
    agreed_plan_name = models.CharField(max_length=100, blank=True, null=True)
    agreed_price_display = models.CharField(max_length=30, blank=True, null=True)
    agreed_price_unit = models.CharField(max_length=60, blank=True, null=True)
    agreed_price_value = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    plan_agreed_at = models.DateTimeField(blank=True, null=True)
    plan_agreement_ip = models.GenericIPAddressField(blank=True, null=True)
    plan_agreement_user_agent = models.CharField(max_length=255, blank=True, null=True)
    plan_agreement_note = models.TextField(blank=True, null=True)

    # ── Staff quote ───────────────────────────────────────────────────────────
    # Deliberately separate from the agreed_* block above. That block is the
    # CUSTOMER's record, stamped with their IP and user agent when they clicked
    # confirm; staff accepting a suggested rate must never be able to forge it.
    quoted_price_value = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    quoted_price_unit = models.CharField(max_length=60, blank=True, null=True)
    quoted_by = models.ForeignKey('auth.User', null=True, blank=True, on_delete=models.SET_NULL,
                                  related_name='+')
    quoted_at = models.DateTimeField(blank=True, null=True)
    quoted_note = models.TextField(blank=True, null=True)

    # Latest computed suggestion, plus a denormalised copy so the list page can
    # sort and filter on it without joining.
    latest_suggestion = models.ForeignKey('PricingSuggestion', null=True, blank=True,
                                          on_delete=models.SET_NULL, related_name='+')
    suggested_price_value = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    suggested_price_at = models.DateTimeField(blank=True, null=True)

    # CRM status — managed by staff
    STATUS_NEW = 'new'
    STATUS_CONTACTED = 'contacted'
    STATUS_QUOTED = 'quoted'
    STATUS_NEGOTIATING = 'negotiating'
    STATUS_CONVERTED = 'converted'
    STATUS_LOST = 'lost'
    STATUS_ON_HOLD = 'on_hold'
    STATUS_CHOICES = [
        (STATUS_NEW, 'New'),
        (STATUS_CONTACTED, 'Contacted'),
        (STATUS_QUOTED, 'Quoted'),
        (STATUS_NEGOTIATING, 'Negotiating'),
        (STATUS_CONVERTED, 'Converted'),
        (STATUS_LOST, 'Lost'),
        (STATUS_ON_HOLD, 'On Hold'),
    ]
    crm_status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_NEW)
    assigned_to = models.ForeignKey(
        'auth.User', null=True, blank=True, on_delete=models.SET_NULL,
        related_name='assigned_pricing_inquiries'
    )
    staff_notes = models.TextField(blank=True, null=True)

    # date created
    date_created = models.DateField(auto_now_add=True, null=True)
    date_modified = models.DateField(auto_now=True, null=True)

    def __str__(self):
        return self.business_name

    # ── Quote selection ───────────────────────────────────────────────────────

    @property
    def has_agreed_plan(self):
        return self.plan_agreed_at is not None

    @property
    def agreed_price_label(self):
        """'25 QR per delivery' — the snapshot, not the live catalogue row."""
        if not self.has_agreed_plan:
            return ''
        bits = [b for b in ((self.agreed_price_display or '').strip(),
                            (self.agreed_price_unit or '').strip()) if b]
        return ' '.join(bits) or 'Custom quote'

    def get_quote_url(self):
        """Token URL of the price table — safe to send to the customer."""
        from django.urls import reverse
        if not self.quote_token:
            return ''
        return reverse('webpages:inquiry_quote', kwargs={'token': self.quote_token})

    # ── Online presence ───────────────────────────────────────────────────────
    # These four columns are free text from a public form that asks for "username
    # or profile URL", so in practice they hold anything: a full URL, a bare
    # handle, a business name with spaces, an Instagram link typed into the
    # website box, or filler like "N/A" and "under development". Staff screens
    # need to know which of those can actually be opened, so the parsing lives
    # here rather than in a template — a bare "ezzyshop.qa" put straight into an
    # href would resolve against ezzydelivery.qa, and "https://N/A" opens nothing.

    # Filler seen in the real table; these mean "nothing on file", not a name.
    _PRESENCE_FILLER = {
        'n/a', 'na', 'n.a', 'none', 'no', 'nil', 'nope', 'nothing', 'null', '-', '--',
        '.', '..', 'tbd', 'x', 'xx', 'not available', 'not yet', 'under development',
        'under construction', 'coming soon', 'www.', 'http://', 'https://', 'soon',
    }
    _HANDLE_OK = _re.compile(r'^[A-Za-z0-9._-]{2,60}$')
    _DOMAINISH = _re.compile(r'^[^\s]*[a-z0-9-]+\.[a-z]{2,}(?:[/?#][^\s]*)?$', _re.IGNORECASE)

    @staticmethod
    def _absolute(value):
        """Bare domain → https:// URL."""
        value = (value or '').strip()
        if value.startswith(('http://', 'https://')):
            return value
        return 'https://' + value.lstrip('/')

    @classmethod
    def _classify_presence(cls, raw, prefers):
        """(url, kind) for one stored value. url is '' when nothing openable can be
        made of it — that is what makes an icon render disabled instead of linking
        somewhere broken. `prefers` names the column it came from, which is what
        decides whether a bare handle means Instagram or Facebook."""
        value = (raw or '').strip()
        if not value or value.lower().strip('.:/ ') in cls._PRESENCE_FILLER:
            return '', prefers

        lowered = value.lower()
        # Host wins over the column: people paste their Instagram into "website".
        if 'instagram.com' in lowered:
            return cls._absolute(value), 'instagram'
        if 'facebook.com' in lowered or 'fb.com' in lowered:
            return cls._absolute(value), 'facebook'
        # In a social column, a value with no scheme and no path is a handle even
        # when it contains a dot — "poolboat.store" and "aiwahome.qa" are Instagram
        # handles, not websites, and the column the sender chose says which.
        # Checked before the domain rule below, which would otherwise send the
        # Instagram icon to a website.
        if (prefers in ('instagram', 'facebook')
                and not value.startswith(('http://', 'https://'))
                and '/' not in value):
            # Whitespace means a business name was typed ("Ara and co."), not a
            # handle. Squashing the spaces would invent a profile that may not
            # exist, so leave it unlinked and keep the text in the tooltip.
            if not any(ch.isspace() for ch in value):
                # Trailing decoration is common ("@ayecynluxe✨"); keep the part of
                # the handle the platform would actually accept.
                handle = ''.join(
                    ch for ch in value.lstrip('@')
                    if ch.isascii() and (ch.isalnum() or ch in '._-')
                )
                if cls._HANDLE_OK.match(handle) and any(c.isalnum() for c in handle):
                    domain = 'instagram.com' if prefers == 'instagram' else 'facebook.com'
                    return 'https://{}/{}'.format(domain, handle), prefers
            return '', prefers

        if cls._DOMAINISH.match(value):
            return cls._absolute(value), 'website' if prefers == 'website' else prefers

        # Nothing openable: a website column with no domain in it ("aiwahome",
        # "ssdsgf"), or a legacy value that names no host.
        return '', prefers

    @property
    def online_presence(self):
        """Website / Facebook / Instagram (+ a legacy 'other') for staff screens.

        Always returns the three fixed channels so a table row keeps its shape,
        each with `url` ('' = show it disabled) and `raw` for the tooltip. A value
        lands in the channel its host says it belongs to, and only falls back to
        the column it was typed into when the host is not recognisable.
        """
        slots = {
            'website': {'key': 'website', 'label': 'Website', 'icon': 'fa-solid fa-globe', 'url': '', 'raw': ''},
            'facebook': {'key': 'facebook', 'label': 'Facebook', 'icon': 'fa-brands fa-facebook-f', 'url': '', 'raw': ''},
            'instagram': {'key': 'instagram', 'label': 'Instagram', 'icon': 'fa-brands fa-instagram', 'url': '', 'raw': ''},
            'other': {'key': 'other', 'label': 'Other profile', 'icon': 'fa-solid fa-link', 'url': '', 'raw': ''},
        }
        sources = (
            (self.website_url, 'website'),
            (self.facebook_profile, 'facebook'),
            (self.instagram_profile, 'instagram'),
            (self.social_profile, 'other'),      # legacy column, network unknown
        )
        for raw, prefers in sources:
            raw = (raw or '').strip()
            if not raw:
                continue
            url, kind = self._classify_presence(raw, prefers)
            # A legacy value that named no known host is a plain link, not a website.
            if prefers == 'other' and kind == 'other' and url:
                kind = 'other'
            target = slots.get(kind, slots['other'])
            if target['url'] and url:
                target = slots['other']          # channel already taken — keep both
            if url and not target['url']:
                target['url'] = url
            # Keep the typed text either way: an unusable value ("Ara and co.") still
            # tells staff something, so it shows in the disabled icon's tooltip.
            if not target['raw']:
                target['raw'] = raw

        channels = [slots['website'], slots['facebook'], slots['instagram']]
        if slots['other']['url'] or slots['other']['raw']:
            channels.append(slots['other'])
        return channels

    def _presence_url(self, key):
        for channel in self.online_presence:
            if channel['key'] == key:
                return channel['url']
        return ''

    @property
    def website_link(self):
        return self._presence_url('website')

    @property
    def facebook_link(self):
        return self._presence_url('facebook')

    @property
    def instagram_link(self):
        return self._presence_url('instagram')

    @property
    def has_online_presence(self):
        return any(c['url'] for c in self.online_presence)

    class Meta:
        verbose_name_plural = "Pricing Inquiries"


class PricingEnquiryActivity(models.Model):
    """Timeline activity log for a PricingEnquiry — status changes, followups, notes."""
    TYPE_NOTE = 'note'
    TYPE_FOLLOWUP = 'followup'
    TYPE_STATUS_CHANGE = 'status_change'
    TYPE_CHOICES = [
        (TYPE_NOTE, 'Note'),
        (TYPE_FOLLOWUP, 'Follow-up'),
        (TYPE_STATUS_CHANGE, 'Status Change'),
    ]
    inquiry = models.ForeignKey(PricingEnquiry, on_delete=models.CASCADE, related_name='activities')
    activity_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default=TYPE_NOTE)
    body = models.TextField()
    created_by = models.ForeignKey('auth.User', null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name_plural = "Pricing Enquiry Activities"

    def __str__(self):
        return f"{self.get_activity_type_display()} on {self.inquiry}"


class WhatsAppInquiry(models.Model):
    """Quick inquiry via WhatsApp"""
    company_name = models.CharField(max_length=200)
    contact_person = models.CharField(max_length=100)
    contact_number = models.CharField(max_length=50)
    product_category = models.CharField(max_length=200)
    product_name = models.CharField(max_length=200, blank=True, null=True)
    additional_info = models.TextField(blank=True, null=True)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.company_name} - {self.contact_person}"

    class Meta:
        verbose_name_plural = "WhatsApp Inquiries"


class DeliveryRequest(EmailNormalizedModel, models.Model):
    """Model for delivery requests from users/non-sellers"""

    EMAIL_FIELDS = ('customer_email',)

    DELIVERY_TYPE_CHOICES = (
        ('pick_and_delivery', 'Pick and Delivery'),
        ('store_pickup_and_delivery', 'Store Pickup and Delivery'),
    )

    STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('confirmed', 'Confirmed'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    )

    # Request Type
    delivery_type = models.CharField(max_length=50, choices=DELIVERY_TYPE_CHOICES)

    # Customer Information
    customer_name = models.CharField(max_length=100)
    customer_email = models.EmailField()
    customer_mobile = models.CharField(max_length=20)

    # Pickup Information
    pickup_address = models.TextField(help_text='Full pickup address')
    pickup_zone = models.PositiveIntegerField(blank=True, null=True)
    pickup_street = models.PositiveIntegerField(blank=True, null=True)
    pickup_building = models.PositiveIntegerField(blank=True, null=True)
    pickup_latitude = models.DecimalField(max_digits=19, decimal_places=15, blank=True, null=True)
    pickup_longitude = models.DecimalField(max_digits=19, decimal_places=15, blank=True, null=True)
    pickup_contact_name = models.CharField(max_length=100, blank=True, null=True)
    pickup_contact_mobile = models.CharField(max_length=20, blank=True, null=True)

    # Delivery Information
    delivery_address = models.TextField(help_text='Full delivery address')
    delivery_zone = models.PositiveIntegerField(blank=True, null=True)
    delivery_street = models.PositiveIntegerField(blank=True, null=True)
    delivery_building = models.PositiveIntegerField(blank=True, null=True)
    delivery_latitude = models.DecimalField(max_digits=19, decimal_places=15, blank=True, null=True)
    delivery_longitude = models.DecimalField(max_digits=19, decimal_places=15, blank=True, null=True)
    delivery_contact_name = models.CharField(max_length=100)
    delivery_contact_mobile = models.CharField(max_length=20)

    # Package Information
    package_description = models.TextField(help_text='Description of items to be delivered')
    package_weight = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True, help_text='Weight in kg')
    package_category = models.CharField(max_length=100, blank=True, null=True)

    # Delivery Preferences
    preferred_date = models.DateField(blank=True, null=True)
    preferred_time = models.TimeField(blank=True, null=True)
    delivery_speed = models.CharField(max_length=50, blank=True, null=True,
                                      help_text='Normal, Same Day, On Demand')
    special_instructions = models.TextField(blank=True, null=True)

    # Pricing
    estimated_price = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)

    # Status
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.customer_name} - {self.get_delivery_type_display()} - {self.created_at.strftime('%Y-%m-%d')}"

    class Meta:
        verbose_name_plural = "Delivery Requests"
        ordering = ['-created_at']


