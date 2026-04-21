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
    Applied → pending → processing → approved (or rejected/blocked/suspended)

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
from django.utils import timezone as dj_timezone
import os
from core import models as core_models


# =============================================================================
# CONSTANTS
# =============================================================================

DRIVER_STATUS_CHOICES = [
    ('pending', 'Pending'),
    ('processing', 'Processing'),
    ('approved', 'Approved'),
    ('rejected', 'Rejected'),
    ('blocked', 'Blocked'),
    ('suspended', 'Suspended'),
]

DRIVER_AVAILABILITY_CHOICES = [
    ('offline', 'Offline'),
    ('available', 'Available'),
    ('on_delivery', 'On Delivery'),
    ('on_break', 'On Break'),
    ('returning', 'Returning'),
]

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
    mobile_no = models.CharField(max_length=20)
    whatsapp_no = models.CharField(max_length=20)
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
    driver_status = models.CharField(
        max_length=100, choices=DRIVER_STATUS_CHOICES, default='pending', db_index=True)  # INDEX: Filtered for approved/pending drivers
    driver_availability = models.CharField(
        max_length=20, choices=DRIVER_AVAILABILITY_CHOICES, default='offline', db_index=True,
        help_text="Real-time availability status of the driver"
    )

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

    # Miscellaneous metadata (push tokens, app settings, etc.)
    driver_meta = models.JSONField(
        default=dict, blank=True,
        help_text="Miscellaneous driver metadata (push notification tokens, app settings, etc.)"
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
    def available_wallet(self):
        """Calculate available wallet as wallet limit minus COD in hand"""
        return self.credit_limit - self.cod_in_hand

    @property
    def wallet_usage_percentage(self):
        """Calculate wallet usage as percentage of wallet limit based on COD in hand"""
        if self.credit_limit <= 0:
            return 0
        return (self.cod_in_hand / self.credit_limit) * 100

    @property
    def is_wallet_warning(self):
        """Check if wallet is at 80% or above usage"""
        return self.wallet_usage_percentage >= 80

    @property
    def is_wallet_blocked(self):
        """Check if COD in hand has reached or exceeded credit limit"""
        return self.cod_in_hand >= self.credit_limit

    @property
    def available_credit(self):
        """Calculate available credit for new COD orders (credit_limit minus COD currently held)"""
        return self.credit_limit - self.cod_in_hand

    class Meta:
        verbose_name_plural = "Drivers"
        # COMPOUND INDEX: user + driver_status for fast driver lookups
        indexes = [
            models.Index(fields=['user', 'driver_status'], name='driver_user_status_idx'),
            models.Index(fields=['driver_availability'], name='driver_avail_idx'),
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
        max_length=100, choices=VEHICLE_STATUS, default='inactive', db_index=True)  # INDEX: Filtered for active vehicles
    vehicle_photo = models.ImageField(
        upload_to='fleet/vehicles/', blank=True, null=True)
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


def upload_path_handler_back(instance, filename):
    upload_dir = os.path.join('core/driver', str(instance.driver_id), 'documents', instance.document_type)
    extension = os.path.splitext(filename)[1]
    filename = f'{instance.document_type}_{instance.driver_id}_back{extension}'
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
    document_file_back = models.ImageField(
        upload_to=upload_path_handler_back, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return str(self.document_no)

    class Meta:
        verbose_name_plural = "Driver Documents"


class DriverTransaction(models.Model):
    """Track all financial transactions for drivers, businesses, and accounting"""

    # Transaction type prefix mapping for code generation
    TYPE_PREFIXES = {
        # COD Transactions
        'cod_collection': 'CODC',
        'cod_driver_settle': 'CODS',
        'cod_client_settle': 'CODCS',
        'cod_return': 'CODR',
        # Delivery / Service Charges
        'delivery_charge': 'DLVC',
        'fulfillment_charge': 'FULF',
        'inventory_handling': 'INVH',
        'other_charge': 'OTHR',
        # Accounting
        'bills_payable': 'BPAY',
        'bills_receivable': 'BREC',
        # Earnings & Settlements
        'earning': 'EARN',
        'settlement': 'STLM',
        'deduction': 'DEDC',
        'bonus': 'BONS',
        'adjustment': 'ADJT',
        # Legacy (backward compat)
        'cod_deposit': 'CODD',  # Legacy
    }

    TRANSACTION_TYPES = [
        # COD Transactions
        ('cod_collection', 'COD Collection'),
        ('cod_driver_settle', 'COD Driver Settlement'),
        ('cod_client_settle', 'COD Client Settlement'),
        ('cod_return', 'COD Return'),
        # Delivery / Service Charges
        ('delivery_charge', 'Delivery Charge'),
        ('fulfillment_charge', 'Fulfillment Charge'),
        ('inventory_handling', 'Inventory Handling Charge'),
        ('other_charge', 'Other Charges'),
        # Accounting
        ('bills_payable', 'Bills Payable'),
        ('bills_receivable', 'Bills Receivable'),
        # Earnings & Settlements
        ('earning', 'Task Earning'),
        ('settlement', 'Earnings Settlement'),
        ('deduction', 'Deduction'),
        ('bonus', 'Bonus/Incentive'),
        ('adjustment', 'Manual Adjustment'),
        # Legacy (kept for backward compatibility with existing data)
        ('cod_deposit', 'COD Deposit to Admin'),
    ]

    PAYMENT_METHOD_CHOICES = [
        ('cash', 'Cash'),
        ('pos', 'POS / Card'),
        ('fawran', 'Fawran'),
        ('bank', 'Bank Transfer'),
        ('atm', 'ATM Deposit'),
    ]

    transaction_code = models.CharField(
        max_length=50, unique=True, blank=True, null=True, db_index=True,
        help_text="Unique transaction code (auto-generated, format: TYPECODE-YYYYMMDD-SEQ)"
    )
    driver = models.ForeignKey(
        Driver, on_delete=models.CASCADE, related_name='transactions',
        null=True, blank=True
    )
    business = models.ForeignKey(
        'business.Business', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='transactions',
        help_text="Business associated with this transaction"
    )
    transaction_type = models.CharField(max_length=30, choices=TRANSACTION_TYPES)
    amount = models.DecimalField(
        max_digits=10, decimal_places=2,
        help_text="Positive for credits, negative for debits"
    )
    description = models.CharField(max_length=255)
    reference_number = models.CharField(max_length=100, blank=True, null=True)
    payment_method = models.CharField(
        max_length=20, choices=PAYMENT_METHOD_CHOICES, default='cash',
        blank=True, null=True, help_text="Payment method for COD deposit/settlement"
    )

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
    # COD in hand breakdown by payment method
    cod_cash_after = models.DecimalField(
        max_digits=10, decimal_places=2, default=0.00
    )
    cod_pos_after = models.DecimalField(
        max_digits=10, decimal_places=2, default=0.00
    )
    cod_fawran_after = models.DecimalField(
        max_digits=10, decimal_places=2, default=0.00
    )
    cod_bank_after = models.DecimalField(
        max_digits=10, decimal_places=2, default=0.00
    )
    cod_atm_after = models.DecimalField(
        max_digits=10, decimal_places=2, default=0.00
    )

    # COD Submission Verification (for cod_driver_settle / cod_deposit transactions)
    is_received = models.BooleanField(
        default=False,
        help_text="Admin confirmed cash was physically received from driver"
    )
    is_verified = models.BooleanField(
        default=False,
        help_text="Admin verified the submitted COD amount is correct"
    )
    is_approved = models.BooleanField(
        default=False,
        help_text="Admin approved / finalised this COD submission"
    )

    # Metadata
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='driver_transactions_created'
    )
    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.transaction_code or self.pk} - {self.get_transaction_type_display()} - {self.amount} QR"

    def save(self, *args, **kwargs):
        if not self.transaction_code:
            from django.db import IntegrityError
            for attempt in range(5):
                self.transaction_code = self._generate_transaction_code()
                try:
                    super().save(*args, **kwargs)
                    return
                except IntegrityError:
                    if attempt == 4:
                        raise
                    continue
        else:
            super().save(*args, **kwargs)

    def _generate_transaction_code(self):
        """Generate transaction code: {TYPECODE}-{YYYYMMDD}-{daily_seq:04d}"""
        from django.db.models import Max

        prefix = self.TYPE_PREFIXES.get(self.transaction_type, 'TXN')
        today_str = dj_timezone.localtime().strftime('%Y%m%d')
        code_pattern = f"{prefix}-{today_str}-"

        # Get next daily sequence for this prefix+date
        last = DriverTransaction.objects.filter(
            transaction_code__startswith=code_pattern
        ).aggregate(max_code=Max('transaction_code'))['max_code']

        if last:
            try:
                seq = int(last.split('-')[-1]) + 1
            except (ValueError, IndexError):
                seq = 1
        else:
            seq = 1

        return f"{code_pattern}{seq:04d}"

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
            timestamp = dj_timezone.localtime().strftime('%Y%m%d%H%M%S')
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


class ZoneEarningsRate(models.Model):
    """
    Zone-based driver earnings rate table.

    For fulfillment/normal delivery: Based on delivery zone
    For pick & drop: Based on pickup zone to delivery zone combination
    """
    ORDER_TYPE_CHOICES = [
        ('normal_delivery', 'Normal Delivery (Fulfillment)'),
        ('pick_and_drop', 'Pick and Drop'),
    ]

    order_type = models.CharField(
        max_length=20, choices=ORDER_TYPE_CHOICES, default='normal_delivery',
        help_text="Order type this rate applies to"
    )

    # For normal delivery: only delivery_zone is used
    # For pick & drop: both pickup_zone and delivery_zone are used
    pickup_zone = models.ForeignKey(
        'delivery.ZoneName', on_delete=models.CASCADE,
        related_name='pickup_earnings_rates',
        null=True, blank=True,
        help_text="Pickup zone (only for pick & drop orders)"
    )
    delivery_zone = models.ForeignKey(
        'delivery.ZoneName', on_delete=models.CASCADE,
        related_name='delivery_earnings_rates',
        help_text="Delivery zone"
    )

    # Earnings rate
    driver_rate = models.DecimalField(
        max_digits=10, decimal_places=2, default=0.00,
        help_text="Driver earnings rate in QR"
    )

    # Distance-based rate (for pick & drop)
    per_km_rate = models.DecimalField(
        max_digits=10, decimal_places=2, default=0.00,
        help_text="Per kilometer rate for distance-based calculation"
    )
    base_rate = models.DecimalField(
        max_digits=10, decimal_places=2, default=0.00,
        help_text="Base rate before distance calculation"
    )

    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        if self.order_type == 'pick_and_drop' and self.pickup_zone:
            return f"Zone {self.pickup_zone.zone_number} → {self.delivery_zone.zone_number}: {self.driver_rate} QR"
        return f"Zone {self.delivery_zone.zone_number}: {self.driver_rate} QR ({self.get_order_type_display()})"

    class Meta:
        verbose_name = "Zone Earnings Rate"
        verbose_name_plural = "Zone Earnings Rates"
        unique_together = ['order_type', 'pickup_zone', 'delivery_zone']
        ordering = ['order_type', 'delivery_zone__zone_number']


# =============================================================================
# DRIVER NOTIFICATIONS
# =============================================================================

NOTIFICATION_TYPE_CHOICES = [
    ('delivery_assigned', 'Delivery Assigned'),
    ('cod_collected', 'COD Collected'),
    ('earnings_settled', 'Earnings Settled'),
    ('order_comment', 'Order Comment'),
    ('alert', 'Alert'),
    ('system', 'System'),
]


class DriverNotification(models.Model):
    """In-app notifications for drivers."""
    driver = models.ForeignKey(
        Driver, on_delete=models.CASCADE, related_name='notifications'
    )
    title = models.CharField(max_length=200)
    message = models.TextField()
    notification_type = models.CharField(
        max_length=30, choices=NOTIFICATION_TYPE_CHOICES, default='system'
    )
    related_task = models.ForeignKey(
        'delivery.DeliveryTask', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='driver_notifications'
    )
    is_read = models.BooleanField(default=False, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    read_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"[{self.driver}] {self.title}"

    class Meta:
        verbose_name = "Driver Notification"
        verbose_name_plural = "Driver Notifications"
        ordering = ['-created_at']


class DriverLocation(models.Model):
    """
    Periodic GPS pings from driver PWA (~every 30s while on active task).
    Used for real-time tracking and proof-of-delivery location.
    """
    driver = models.ForeignKey(
        Driver, on_delete=models.CASCADE, related_name='locations', db_index=True
    )
    latitude = models.DecimalField(max_digits=10, decimal_places=7)
    longitude = models.DecimalField(max_digits=10, decimal_places=7)
    accuracy = models.FloatField(null=True, blank=True, help_text="GPS accuracy in metres")
    speed = models.FloatField(null=True, blank=True, help_text="Speed in m/s")
    heading = models.FloatField(null=True, blank=True, help_text="Heading in degrees")
    task = models.ForeignKey(
        'delivery.DeliveryTask', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='driver_locations'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"[{self.driver}] {self.latitude},{self.longitude} @ {self.created_at:%H:%M}"

    class Meta:
        verbose_name = "Driver Location"
        verbose_name_plural = "Driver Locations"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['driver', '-created_at'], name='driverloc_driver_ts_idx'),
        ]


class DriverActivityLog(models.Model):
    """
    Audit log for all driver actions — task events, COD, login, status changes.
    Used for dashboard activity timeline and compliance tracking.
    """

    ACTIVITY_TYPES = [
        # Task lifecycle
        ('task_taken',        'Task Taken'),
        ('task_accepted',     'Task Accepted'),
        ('task_picked_up',    'Task Picked Up'),
        ('task_start_ride',   'Start Ride'),
        ('task_out_delivery', 'Out for Delivery'),
        ('task_delivered',    'Task Delivered'),
        ('task_failed',       'Task Failed'),
        ('task_contacted',    'Customer Contacted'),
        ('task_non_reachable','Customer Non-Reachable'),
        # COD / financial
        ('cod_collected',     'COD Collected'),
        ('cod_submitted',     'COD Submitted'),
        ('earning_credited',  'Earning Credited'),
        ('settlement',        'Wallet Settlement'),
        # Account / profile
        ('login',             'Login'),
        ('logout',            'Logout'),
        ('profile_updated',   'Profile Updated'),
        ('document_uploaded', 'Document Uploaded'),
        ('vehicle_added',     'Vehicle Added'),
        # Scan
        ('pickup_scanned',    'Pickup Scanned'),
    ]

    driver = models.ForeignKey(
        Driver, on_delete=models.CASCADE, related_name='activity_logs', db_index=True
    )
    activity_type = models.CharField(
        max_length=30, choices=ACTIVITY_TYPES, db_index=True
    )
    # Optional FK to related task (null for non-task events)
    task = models.ForeignKey(
        'delivery.DeliveryTask', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='driver_activity_logs'
    )
    # Optional FK to related transaction
    transaction = models.ForeignKey(
        DriverTransaction, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='activity_logs'
    )
    # Human-readable description of what happened
    description = models.CharField(max_length=500, blank=True)
    # Extra structured data (amounts, old/new values, etc.)
    meta = models.JSONField(default=dict, blank=True)
    # IP / device info (optional, for audit)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    def __str__(self):
        return f"[{self.driver}] {self.get_activity_type_display()} @ {self.created_at:%Y-%m-%d %H:%M}"

    class Meta:
        verbose_name = "Driver Activity Log"
        verbose_name_plural = "Driver Activity Logs"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['driver', '-created_at']),
            models.Index(fields=['activity_type', '-created_at']),
        ]
