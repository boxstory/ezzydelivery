"""
Fleet Models Module
===================

This module contains models for driver management, vehicles, documents,
and financial tracking (wallet, transactions, settlements).

Models:
    Driver Management:
        - Driver: Main driver entity with profile and wallet info
        - DriverVacancyAplication: Job applications from prospective drivers

    Vehicle Management:
        - DriverVehicle: Driver's registered vehicles

    Documents:
        - DriverDocument: Driver documents (QID, license, passport)

    Financial Tracking:
        - DriverTransaction: All financial transactions (earnings, COD, etc.)
        - DriverSettlement: Periodic payouts/settlements

Driver Status Flow:
    Applied → Pending on Review → Processing → Approved (or Rejected/Blocked)

Wallet System:
    - wallet_balance: Tracks COD credits/debits
    - credit_limit: Maximum COD driver can hold
    - cod_in_hand: Current COD with driver
    - pending_earnings: Earnings awaiting settlement

Transaction Types:
    - earning: Task completion earnings
    - cod_collection: COD collected from customer
    - cod_deposit: COD submitted to admin
    - settlement: Earnings paid out
    - bonus/deduction/adjustment: Manual changes

Related:
    - delivery.models.DeliveryTask: Tasks assigned to drivers
    - business.models.DriverDirectory: Business-driver associations
    - fleet.wallet_service: Business logic for wallet operations
"""

from datetime import datetime
from django.db import models
from django.conf import settings
import os
from core import models as core_models


# =============================================================================
# CONSTANTS
# =============================================================================

VEHICLE_CHOICES = [
    ('none', 'None'),
    ('bike', 'Bike'),
    ('car', 'Car'),
    ('van', 'Van'),
    ('pickup', 'Pickup'),
    ('pickup3ton', 'Pickup 3Ton'),
    ('pickup_big', 'Pickup Big Items'),

]


class DriverVacancyAplication(models.Model):

    LICENCE_CHOICES = [
        ('none', 'None'),
        ('2wheeler', '2 Wheeler'),
        ('4wheeler', '4 Wheeler'),
        ('heavy', 'Heavy'),
    ]

    JOB_TYPE_CHOICES = [
        ('part_time', 'Part Time'),
        ('full_time', 'Full Time'),
        ('both', 'Both'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    full_name = models.CharField(max_length=100)
    mobile_no = models.IntegerField()
    whatsapp_no = models.IntegerField()
    landmark = models.CharField(max_length=100)
    zone_name = models.CharField(max_length=100)
    licence = models.CharField(max_length=100, choices=LICENCE_CHOICES)
    is_in_qatar = models.BooleanField(default=False, )
    job_type = models.CharField(
        max_length=100, choices=JOB_TYPE_CHOICES)
    own_vehicle = models.CharField(
        max_length=100, choices=VEHICLE_CHOICES)

    def __str__(self):
        return str(self.full_name)

    class Meta:
        verbose_name_plural = "Driver Job"


class Driver(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, db_index=True)  # INDEX: Frequently queried (driver.objects.get(user_id=...))
    profile = models.ForeignKey(
        core_models.Profile, on_delete=models.SET_NULL, blank=True, null=True, related_name='driver')
    driver_id = models.PositiveSmallIntegerField(primary_key=True)

    driver_code = models.CharField(max_length=100, blank=True, null=True, db_index=True)  # INDEX: Searched/filtered often
    driver_code_dms = models.CharField(max_length=100, blank=True, null=True)
    driver_phone = models.CharField(max_length=100)
    driver_whatsapp = models.CharField(max_length=100)
    driver_bio = models.CharField(max_length=225, blank=True, null=True)
    driver_languages_choices = (
        ('arabic', 'Arabic'),
        ('english', 'English'),
        ('hindi', 'Hindi'),
        ('philipine', 'Philipine'),
        ('other', 'Other'),
    )
    driver_languages = models.CharField(
        max_length=100, choices=driver_languages_choices)
    driver_license_number = models.CharField(max_length=100)
    driver_rating = models.IntegerField(default=0)
    driver_rating_count = models.IntegerField(default=0)
    driver_reviews = models.TextField(default="")
    driver_reviews_count = models.IntegerField(default=0)
    driver_status_choices = (
        ('Pending on Review', 'Pending on Review'),
        ('Processing', 'Processing'),
        ('Approved', 'Approved'),
        ('Rejected', 'Rejected'),
        ('Blocked', 'Blocked'),
    )
    driver_status = models.CharField(
        max_length=100, choices=driver_status_choices, db_index=True)  # INDEX: Filtered for approved/pending drivers

    # COD Wallet System Fields
    wallet_balance = models.DecimalField(
        max_digits=10, decimal_places=2, default=0.00,
        help_text="Current wallet balance (decreases when COD collected, increases when submitted)"
    )
    credit_limit = models.DecimalField(
        max_digits=10, decimal_places=2, default=5000.00,
        help_text="Maximum COD credit limit based on driver performance and trustworthiness"
    )
    cod_in_hand = models.DecimalField(
        max_digits=10, decimal_places=2, default=0.00,
        help_text="Total COD currently in driver's possession"
    )
    total_earnings = models.DecimalField(
        max_digits=10, decimal_places=2, default=0.00,
        help_text="Total lifetime earnings from deliveries"
    )
    pending_earnings = models.DecimalField(
        max_digits=10, decimal_places=2, default=0.00,
        help_text="Earnings pending settlement since last payout"
    )
    last_settlement_date = models.DateTimeField(
        null=True, blank=True,
        help_text="Last date when earnings were settled/paid"
    )

    # Zone Preferences
    preferred_zone_groups = models.ManyToManyField(
        'delivery.ZoneGroup',
        blank=True,
        related_name='drivers',
        help_text="Driver's preferred delivery zone groups"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        if self.profile and self.profile.user:
            return self.profile.user.username
        # Fallback to a non-None value
        return f"Driver {self.driver_code or self.driver_id}"

    @property
    def wallet_usage_percentage(self):
        """Calculate wallet usage as percentage of credit limit"""
        if self.credit_limit <= 0:
            return 0
        return (abs(self.wallet_balance) / self.credit_limit) * 100

    @property
    def is_wallet_warning(self):
        """Check if wallet is at 80% or above usage"""
        return self.wallet_usage_percentage >= 80

    @property
    def is_wallet_blocked(self):
        """Check if wallet balance is exhausted (at or below zero)"""
        return self.wallet_balance <= 0

    @property
    def available_credit(self):
        """Calculate available credit for new COD orders"""
        return self.credit_limit + self.wallet_balance  # wallet_balance is negative when in use

    class Meta:
        verbose_name_plural = "Drivers"
        # COMPOUND INDEX: user + driver_status for fast driver lookups
        indexes = [
            models.Index(fields=['user', 'driver_status'], name='driver_user_status_idx'),
            models.Index(fields=['driver_code'], name='driver_code_idx'),
            models.Index(fields=['created_at'], name='driver_created_idx'),
        ]


class DriverVehicle(models.Model):
    driver = models.ForeignKey(
        Driver, on_delete=models.CASCADE, related_name='driver_vehicle', db_index=True)  # INDEX: Always filtered by driver_id
    vehicle_type = models.CharField(
        max_length=100, choices=VEHICLE_CHOICES, default='none')
    vehicle_no = models.CharField(max_length=100, blank=True, null=True)
    vehicle_model = models.CharField(max_length=100, blank=True, null=True)
    vehicle_color = models.CharField(max_length=100, blank=True, null=True)
    VEHICLE_STATUS = (
        ('active', 'Active'),
        ('inactive', 'Inactive'),
    )
    vehicle_status = models.CharField(
        max_length=100, choices=VEHICLE_STATUS, default='Inactive', db_index=True)  # INDEX: Filtered for active vehicles
    vehicle_date = models.DateField(auto_now_add=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return str(self.vehicle_no)

    class Meta:
        verbose_name_plural = "Driver Vehicles"
        # COMPOUND INDEX: driver + vehicle_status for fast active vehicle lookups
        indexes = [
            models.Index(fields=['driver', 'vehicle_status'], name='vehicle_driver_status_idx'),
        ]


def upload_path_handler(instance, filename):
    upload_dir = os.path.join('core/driver', str(instance.driver_id), 'documents', instance.document_type)
    extension = os.path.splitext(filename)[1]
    filename = f'{instance.document_type}_{instance.driver_id}.{extension}'
    if not os.path.exists(upload_dir):
        os.makedirs(upload_dir)
    return os.path.join(upload_dir, filename)



class DriverDocument(models.Model):
    driver = models.ForeignKey(
        Driver, on_delete=models.CASCADE, related_name='driver_document')
    document_choices = (
        ('QID', 'QID'),
        ('Driving License' , 'Driving License'),
        ('Passport', 'Passport'),
        ('National Identification', 'National Identification'),
    )
    document_type = models.CharField(max_length=100, null=True, choices=document_choices, blank=True)
    document_no = models.CharField(max_length=100)
    document_issued_from = models.CharField( max_length=100, blank=True, null=True)
    document_expiry_date = models.DateField( blank=True, null=True)
    document_file = models.ImageField(
        upload_to=upload_path_handler, default='core/driver/default/doc_default.png', blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return str(self.document_no)

    class Meta:
        verbose_name_plural = "Driver Documents"


class DriverTransaction(models.Model):
    """Track all financial transactions for drivers (earnings, COD, settlements)"""
    TRANSACTION_TYPES = (
        ('earning', 'Task Earning'),
        ('cod_collection', 'COD Collection'),
        ('cod_deposit', 'COD Deposit to Admin'),
        ('settlement', 'Earnings Settlement'),
        ('deduction', 'Deduction'),
        ('bonus', 'Bonus/Incentive'),
        ('adjustment', 'Manual Adjustment'),
    )

    transaction_id = models.AutoField(primary_key=True)
    driver = models.ForeignKey(
        Driver, on_delete=models.CASCADE, related_name='transactions'
    )
    transaction_type = models.CharField(max_length=20, choices=TRANSACTION_TYPES)
    amount = models.DecimalField(
        max_digits=10, decimal_places=2,
        help_text="Positive for credits, negative for debits"
    )
    description = models.CharField(max_length=255)
    reference_number = models.CharField(max_length=100, blank=True, null=True)

    # Related objects (optional foreign keys)
    delivery_task = models.ForeignKey(
        'delivery.DeliveryTask', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='transactions'
    )
    settlement = models.ForeignKey(
        'DriverSettlement', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='transactions'
    )

    # Balances after this transaction
    wallet_balance_after = models.DecimalField(
        max_digits=10, decimal_places=2, default=0.00
    )
    cod_in_hand_after = models.DecimalField(
        max_digits=10, decimal_places=2, default=0.00
    )
    pending_earnings_after = models.DecimalField(
        max_digits=10, decimal_places=2, default=0.00
    )

    # Metadata
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='driver_transactions_created'
    )
    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.get_transaction_type_display()} - {self.driver} - {self.amount} QR"

    class Meta:
        verbose_name_plural = "Driver Transactions"
        ordering = ['-created_at']


class DriverSettlement(models.Model):
    """Track periodic settlement/payout of driver earnings"""
    SETTLEMENT_STATUS = (
        ('pending', 'Pending Approval'),
        ('approved', 'Approved'),
        ('paid', 'Paid'),
        ('rejected', 'Rejected'),
    )

    settlement_id = models.AutoField(primary_key=True)
    driver = models.ForeignKey(
        Driver, on_delete=models.CASCADE, related_name='settlements'
    )
    settlement_code = models.CharField(max_length=50, unique=True)

    # Settlement period
    period_start = models.DateField()
    period_end = models.DateField()

    # Statistics
    total_deliveries = models.IntegerField(default=0)
    total_delivery_charges = models.DecimalField(
        max_digits=10, decimal_places=2, default=0.00
    )

    # Financial breakdown
    gross_earnings = models.DecimalField(
        max_digits=10, decimal_places=2, default=0.00,
        help_text="Total earnings before deductions"
    )
    deductions = models.DecimalField(
        max_digits=10, decimal_places=2, default=0.00,
        help_text="Total deductions (damages, violations, etc.)"
    )
    bonuses = models.DecimalField(
        max_digits=10, decimal_places=2, default=0.00,
        help_text="Performance bonuses and incentives"
    )
    net_amount = models.DecimalField(
        max_digits=10, decimal_places=2, default=0.00,
        help_text="Final amount to be paid (gross + bonuses - deductions)"
    )

    # Status and workflow
    status = models.CharField(max_length=20, choices=SETTLEMENT_STATUS, default='pending')
    payment_method = models.CharField(
        max_length=50, blank=True, null=True,
        help_text="Cash, Bank Transfer, etc."
    )
    payment_reference = models.CharField(
        max_length=100, blank=True, null=True,
        help_text="Transaction ID or reference number"
    )

    # Dates
    created_at = models.DateTimeField(auto_now_add=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)

    # Users
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='settlements_created'
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='settlements_approved'
    )

    notes = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"{self.settlement_code} - {self.driver} - {self.net_amount} QR"

    def save(self, *args, **kwargs):
        # Generate settlement code if not exists
        if not self.settlement_code:
            from datetime import datetime
            timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
            self.settlement_code = f"STL-{self.driver.driver_id}-{timestamp}"
        super().save(*args, **kwargs)

    class Meta:
        verbose_name_plural = "Driver Settlements"
        ordering = ['-created_at']


class ReceiptTemplate(models.Model):
    """Customizable receipt templates for settlements and transactions"""
    TEMPLATE_TYPES = (
        ('settlement', 'Settlement Receipt'),
        ('cod_deposit', 'COD Deposit Receipt'),
        ('earnings', 'Earnings Statement'),
        ('transaction', 'Transaction Receipt'),
    )

    PAPER_SIZES = (
        ('thermal_80', 'Thermal 80mm'),
        ('thermal_58', 'Thermal 58mm'),
        ('a4', 'A4 Paper'),
        ('a5', 'A5 Paper'),
        ('letter', 'Letter'),
    )

    template_id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=100)
    template_type = models.CharField(max_length=20, choices=TEMPLATE_TYPES)
    paper_size = models.CharField(max_length=20, choices=PAPER_SIZES, default='thermal_80')
    is_default = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    # Customization options stored as JSON
    # Logo settings
    logo_url = models.CharField(max_length=500, blank=True, null=True)
    show_logo = models.BooleanField(default=True)

    # Company info
    company_name = models.CharField(max_length=200, default='Ezzy Delivery')
    company_address = models.TextField(blank=True, default='Doha, Qatar')
    company_phone = models.CharField(max_length=50, blank=True, default='+974-XXXX-XXXX')
    company_email = models.EmailField(blank=True, null=True)

    # Style settings
    primary_color = models.CharField(max_length=7, default='#2196F3')
    font_family = models.CharField(max_length=100, default='Courier New, monospace')
    font_size = models.IntegerField(default=12)

    # Content settings
    show_signature_line = models.BooleanField(default=True)
    show_qr_code = models.BooleanField(default=False)
    show_barcode = models.BooleanField(default=False)
    footer_message = models.TextField(default='Thank you for your service!')
    terms_and_conditions = models.TextField(blank=True, null=True)

    # Custom CSS (for advanced users)
    custom_css = models.TextField(blank=True, null=True, help_text='Custom CSS to override default styles')

    # Custom HTML template (for advanced customization)
    custom_template = models.TextField(blank=True, null=True, help_text='Custom HTML template content')

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='receipt_templates_created'
    )

    def __str__(self):
        return f"{self.name} ({self.get_template_type_display()})"

    def save(self, *args, **kwargs):
        # Ensure only one default template per type
        if self.is_default:
            ReceiptTemplate.objects.filter(
                template_type=self.template_type,
                is_default=True
            ).exclude(template_id=self.template_id).update(is_default=False)
        super().save(*args, **kwargs)

    class Meta:
        verbose_name_plural = "Receipt Templates"
        ordering = ['template_type', '-is_default', 'name']
