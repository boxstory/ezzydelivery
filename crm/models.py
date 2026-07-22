# Purpose: Unified sales Lead model + activity timeline + WAHA inbox dismissals for the CRM pipeline.
# Used by: crm/services.py, workforce/crm_views.py, crm/admin.py, backfill/digest management commands.
# Notes: Lead denormalizes contact fields from its source inquiry; OneToOne links keep creation idempotent.

from django.db import models
from django.utils import timezone


class Lead(models.Model):
    SOURCE_PRICING = 'pricing_inquiry'
    SOURCE_WA_FORM = 'whatsapp_form'
    SOURCE_WA_INBOUND = 'whatsapp_inbound'
    SOURCE_MANUAL = 'manual'
    SOURCE_CHOICES = [
        (SOURCE_PRICING, 'Pricing Inquiry'),
        (SOURCE_WA_FORM, 'WhatsApp Form'),
        (SOURCE_WA_INBOUND, 'WhatsApp Inbound'),
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
        return f"{self.company_name or self.contact_name or self.phone} ({self.get_stage_display()})"

    @property
    def is_open(self):
        return self.stage not in self.CLOSED_STAGES

    @property
    def is_overdue(self):
        return bool(
            self.next_followup_at
            and self.next_followup_at < timezone.localdate()
            and self.is_open
        )


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
