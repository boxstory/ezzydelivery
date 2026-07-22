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

from django.conf import settings
from django.db import models


# =============================================================================
# CONTACT US MODEL
# =============================================================================


class ContactUs(models.Model):
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


class Careers(models.Model):
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
# PRICING ENQUIRY MODEL
# =============================================================================


class PricingEnquiry(models.Model):
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
    fulfillment_storage_volume = models.CharField(max_length=100, blank=True, null=True)  # shown when Doha hub = Yes; e.g. "1-5 pallets"
    current_delivery_cost = models.CharField(max_length=50, blank=True, null=True)        # optional benchmark; e.g. "10-15 QAR"
    special_handling_detail = models.CharField(max_length=200, blank=True, null=True)     # shown when special handling = Yes; multi e.g. "Fragile, Chilled / Frozen"
    average_package_weight = models.CharField(max_length=50, blank=True, null=True)       # e.g. "1-5 kg"
    number_of_pickup_locations = models.CharField(max_length=20, blank=True, null=True)   # shown when pickup type = Multiple Store
    additional_notes = models.TextField(blank=True, null=True)
    contact_consent = models.BooleanField(default=False)

    # Completion status — False for partial (in-progress), True for fully submitted
    is_complete = models.BooleanField(default=False)

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


class DeliveryRequest(models.Model):
    """Model for delivery requests from users/non-sellers"""

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


