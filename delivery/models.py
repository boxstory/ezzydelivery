"""
Delivery Models Module
======================

This module contains models for delivery task management and tracking.

Models:
    Task Management:
        - DeliveryTask: Core delivery task linked to orders
        - AssignedDriver: Driver assignment to delivery tasks
        - DlAddressUpdate: Customer delivery address details

    Location Data:
        - ZoneName: Zone number to name mapping
        - LatLonList: Coordinate database for addresses

    Labels:
        - ShippingLabel: Auto-generated shipping labels for packages

Delivery Status Flow:
    Order Created → for_review → pending → in_transit → delivered
                                       ↘ address_pending (if address needs update)
                                       ↘ customer_confirmation_pending
                                       ↘ cancelled/rejected

Related:
    - orders.models.Order: Source order for delivery task
    - fleet.models.Driver: Driver assigned to task
    - business.models.Business: Business that placed the order
"""

import datetime
from django.db import models

from core import models as core_models
from orders import models as orders_models
from business import models as business_models
from fleet import models as fleet_models


# =============================================================================
# DELIVERY ADDRESS MODELS
# =============================================================================


class DlAddressUpdate(models.Model):
    """
    Customer delivery address details.

    Stores delivery address information that can be updated by customers
    via a link sent to their phone. Used to verify and update delivery
    coordinates before the delivery is made.

    Fields:
        Customer Info:
            - full_name: Recipient name
            - mobile_no: Contact number

        Address Details:
            - area_name: Area/locality name
            - dl_zone: Zone number
            - dl_street: Street number
            - dl_building: Building number
            - dl_unit: Unit/apartment number

        Coordinates:
            - dl_latitude, dl_longitude: GPS coordinates
            - dl_pluscode: Google Plus Code

        Property Type:
            - is_villa_compound: Villa/compound delivery
            - is_flat: Apartment delivery
            - is_office: Office delivery

        Task Reference:
            - dl_task_number: Delivery task code
            - order: Parent order
            - time_slot: Preferred delivery time

    Related:
        delivery.views.dl_address_link - Customer address update page
    """
    full_name = models.CharField(max_length=100)
    mobile_no = models.CharField(max_length=20)
    area_name = models.CharField(max_length=100, blank=True, null=True)
    dl_zone = models.PositiveIntegerField(blank=True, null=True)
    dl_building = models.PositiveIntegerField(blank=True, null=True)
    dl_street = models.PositiveIntegerField(blank=True, null=True)
    dl_latitude = models.DecimalField(max_digits=19, decimal_places=15, blank=True, null=True, default=0)
    dl_longitude = models.DecimalField(max_digits=19, decimal_places=15, blank=True, null=True, default=0)
    dl_pluscode = models.CharField(max_length=50, blank=True, null=True)
    dl_unit = models.CharField(max_length=10, blank=True, null=True)
    is_villa_compound = models.BooleanField(default=False)
    is_flat = models.BooleanField(default=False)
    is_office = models.BooleanField(default=False)
    dl_task_number = models.CharField(max_length=100)
    time_slot = models.CharField(max_length=100, blank=True, null=True)
    order = models.ForeignKey(orders_models.Order, on_delete=models.DO_NOTHING, related_name='delivery_addresses')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.full_name

    class Meta:
        verbose_name_plural = "Delivery Address"
        app_label = 'delivery'


class HubPickupBatch(models.Model):
    """
    Represents a single driver ride that collects goods from one pickup location
    and brings them to a hub warehouse. May cover one or many orders.

    Leg 1 of the hub model — the driver sees one task card for the entire batch.
    After the driver marks the batch 'at_hub', individual DeliveryTask records
    (Leg 2, task_leg='hub_delivery') are auto-created per order.
    """

    batch_number = models.CharField(max_length=50, unique=True, db_index=True,
                                    help_text="e.g. BATCH-20260228-001")

    pickup_location = models.ForeignKey(
        business_models.PickupLocation,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='hub_batches',
        help_text="Seller location where driver collects goods."
    )
    hub_warehouse = models.ForeignKey(
        'warehouse.WarehouseLocation',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='pickup_batches',
        help_text="Hub warehouse where driver drops off all goods."
    )
    driver = models.ForeignKey(
        fleet_models.Driver,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='hub_pickup_batches',
    )

    BATCH_STATUS_CHOICES = [
        ('pending',     'Pending — awaiting driver assignment'),
        ('assigned',    'Assigned to driver'),
        ('accepted',    'Accepted by driver'),
        ('in_progress', 'Driver on the way to pickup'),
        ('arrived',     'Driver at pickup location'),
        ('collected',   'All packages collected'),
        ('at_hub',      'Delivered to hub'),
        ('cancelled',   'Cancelled'),
    ]
    status = models.CharField(
        max_length=20, choices=BATCH_STATUS_CHOICES, default='pending'
    )

    notes = models.TextField(blank=True, null=True)
    created_by = models.ForeignKey(
        'auth.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='created_hub_batches'
    )

    driver_earnings = models.DecimalField(
        max_digits=10, decimal_places=2, default=0,
        help_text="Total earnings for this pickup ride (set by staff)."
    )
    earnings_processed = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'delivery_hubpickupbatch'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.batch_number} ({self.status})"

    @property
    def order_count(self):
        return self.orders.count()


class DeliveryTask(models.Model):
    DL_TASK_STATUS_CLIENT_CHOICES = [
        ('for_review', 'For Review'),
        ('customer_confiration_pending', 'Customer Confirmation Pending'),
        ('0', 'Assigned to Driver'),
        ('2', 'Delivered'),
        ('rejected', 'Rejected'),
        ('9', 'Cancelled'),
    ]
    DL_TASK_STATUS_CHOICES = [
        ('for_review', 'For Review'),
        ('pending', 'Pending'),
        ('assigned', 'Assigned'),
        ('accepted', 'Accepted'),
        ('picked_up', 'Picked Up'),
        ('start_ride', 'Start Ride'),
        ('out_for_delivery', 'Out for Delivery'),
        ('in_transit', 'In Transit'),
        ('contacted', 'Contacted & Confirmed'),
        ('non_reachable', 'Non Reachable'),
        ('delivered', 'Delivered'),
        ('partial_delivery', 'Partial Delivery'),
        ('failed', 'Failed'),
        ('rejected', 'Rejected'),
        ('cancelled', 'Cancelled'),
        ('dropsownlost', 'Drops Own Lost'),
    ]
    dl_task_publish = models.BooleanField(default=False)
    dl_task_number = models.CharField(max_length=100)
    dl_task_description = models.CharField(max_length=100)
    dl_task_status_client = models.CharField(
        max_length=100, choices=DL_TASK_STATUS_CLIENT_CHOICES)
    dl_task_status = models.CharField(max_length=100, choices=DL_TASK_STATUS_CHOICES)
    dl_task_date = models.DateField(default=datetime.date.today)
    order = models.ForeignKey(orders_models.Order, on_delete=models.DO_NOTHING, related_name='delivery_task')
    dl_address_update = models.ForeignKey(
        DlAddressUpdate, on_delete=models.DO_NOTHING, blank=True, null=True, related_name='dl_task')
    driver = models.ForeignKey(
        fleet_models.Driver, on_delete=models.DO_NOTHING, blank=True, null=True)
    business = models.ForeignKey(
        business_models.Business, on_delete=models.DO_NOTHING, blank=True, null=True)

    pickup_location = models.ForeignKey(
        business_models.PickupLocation, on_delete=models.DO_NOTHING, blank=True, null=True)

    dl_waight = models.IntegerField(default=1)
    DL_CATEGORY_CHOICES = [
        ('Food', 'Food'),
        ('Regular', 'Regular'),
        ('Electronics', 'Electronics'),
        ('Others', 'Others'),
    ]
    dl_category = models.CharField(
        max_length=100, choices=DL_CATEGORY_CHOICES, blank=True)
    DL_SPEED_CHOICES = [
        ('Normal', 'Normal'),
        ('Same Day', 'Same Day'),
        ('On Demand',   'On Demand'),
        ('White Glove',   'White Glove'),
    ]
    dl_speed = models.CharField(
        max_length=100, choices=DL_SPEED_CHOICES, blank=True)
    dl_price = models.IntegerField(default=20, null=True, blank=True)
    dl_to_address = models.ForeignKey(
        DlAddressUpdate, on_delete=models.DO_NOTHING, blank=True, null=True)

    # Earnings and COD Tracking Fields
    driver_earnings = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        help_text="Driver's earnings from this delivery (calculated on completion)"
    )
    company_commission = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        help_text="Company's commission from this delivery"
    )
    cod_collected = models.BooleanField(
        default=False,
        help_text="Whether COD has been collected for this delivery"
    )
    cod_collected_amount = models.DecimalField(
        max_digits=10, decimal_places=2, default=0.00,
        help_text="Actual COD amount collected from customer"
    )
    cod_collected_at = models.DateTimeField(
        null=True, blank=True,
        help_text="When COD was collected"
    )
    cod_settled = models.BooleanField(
        default=False,
        help_text="Whether COD has been submitted/settled with admin"
    )
    cod_settled_at = models.DateTimeField(
        null=True, blank=True,
        help_text="When COD was submitted to admin"
    )
    cod_submission_txn = models.ForeignKey(
        'fleet.DriverTransaction', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='submission_tasks',
        help_text="The COD submission transaction this task was settled in"
    )
    earnings_settled = models.BooleanField(
        default=False,
        help_text="Whether driver earnings have been settled/paid out"
    )
    earnings_settled_at = models.DateTimeField(
        null=True, blank=True,
        help_text="When driver earnings were settled"
    )
    completed_at = models.DateTimeField(
        null=True, blank=True,
        help_text="When the delivery was completed"
    )
    completion_latitude = models.DecimalField(
        max_digits=10, decimal_places=7, null=True, blank=True,
        help_text="Driver GPS latitude when task was completed"
    )
    completion_longitude = models.DecimalField(
        max_digits=10, decimal_places=7, null=True, blank=True,
        help_text="Driver GPS longitude when task was completed"
    )
    earnings_processed = models.BooleanField(
        default=False,
        help_text="Whether earnings have been added to driver's wallet"
    )

    PREFERRED_TIME_CHOICES = [
        ('9am-1pm',  '9 AM – 1 PM'),
        ('2pm-6pm',  '2 PM – 6 PM'),
        ('6pm-10pm', '6 PM – 10 PM'),
    ]
    preferred_time = models.CharField(
        max_length=50, blank=True, default='',
        choices=PREFERRED_TIME_CHOICES,
        help_text="Customer preferred delivery time slot"
    )

    PAYMENT_METHOD_CHOICES = [
        ('cash', 'Cash'),
        ('pos', 'POS'),
        ('fawran', 'Fawran'),
    ]
    payment_method = models.CharField(
        max_length=20, blank=True, default='',
        choices=PAYMENT_METHOD_CHOICES,
        help_text="Customer preferred payment method"
    )
    payment_split = models.JSONField(
        null=True, blank=True,
        help_text="Split COD payment by method: {cash: 100, fawran: 50}"
    )

    # Earnings Verification Fields (for staff approval)
    EARNINGS_VERIFICATION_STATUS = [
        ('pending', 'Pending Verification'),
        ('verified', 'Verified'),
        ('published', 'Published'),
        ('rejected', 'Rejected'),
    ]
    earnings_verification_status = models.CharField(
        max_length=20, choices=EARNINGS_VERIFICATION_STATUS, default='pending',
        help_text="Earnings verification status by staff"
    )
    calculated_earnings = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        help_text="System-calculated driver earnings (before verification)"
    )
    verified_earnings = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        help_text="Staff-verified/adjusted driver earnings"
    )
    earnings_verified_by = models.ForeignKey(
        'auth.User', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='verified_earnings',
        help_text="Staff member who verified the earnings"
    )
    earnings_verified_at = models.DateTimeField(
        null=True, blank=True,
        help_text="When earnings were verified by staff"
    )
    earnings_published_at = models.DateTimeField(
        null=True, blank=True,
        help_text="When earnings were published and visible to driver"
    )
    earnings_notes = models.TextField(
        blank=True, null=True,
        help_text="Staff notes about earnings verification"
    )

    # --- Failure & Retry Tracking ---
    FAILURE_REASON_CHOICES = [
        ('customer_not_home', 'Customer Not Home'),
        ('address_not_found', 'Address Not Found'),
        ('customer_refused', 'Customer Refused Delivery'),
        ('customer_unreachable', 'Customer Unreachable'),
        ('vehicle_issue', 'Vehicle / Driver Issue'),
        ('wrong_address', 'Wrong Address on Order'),
        ('customer_requested_reschedule', 'Customer Requested Reschedule'),
        ('cod_amount_dispute', 'COD Amount Disputed'),
        ('other', 'Other'),
    ]
    failure_reason = models.CharField(
        max_length=50, choices=FAILURE_REASON_CHOICES, blank=True, null=True,
        help_text="Why the delivery failed"
    )
    failure_notes = models.TextField(
        blank=True, null=True,
        help_text="Additional notes about the failure"
    )
    failed_attempt_count = models.PositiveSmallIntegerField(
        default=0,
        help_text="Number of failed delivery attempts for this task"
    )
    reschedule_date = models.DateField(
        blank=True, null=True,
        help_text="Rescheduled delivery date after failure"
    )
    reschedule_reason = models.CharField(
        max_length=255, blank=True, null=True,
        help_text="Reason for rescheduling"
    )

    # --- Driver Rejection Tracking ---
    rejection_reason = models.TextField(
        blank=True, null=True,
        help_text="Reason driver rejected this task"
    )

    # --- COD Client Settlement ---
    cod_client_settled = models.BooleanField(
        default=False,
        help_text="Whether COD has been settled with the business client"
    )
    cod_client_settled_at = models.DateTimeField(
        null=True, blank=True,
        help_text="When COD was settled with the business client"
    )
    cod_client_settle_txn = models.ForeignKey(
        'fleet.DriverTransaction', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='client_settled_tasks',
        help_text="The COD client-settlement (business payout) transaction this task was paid in"
    )

    # --- Hub Model (Two-Leg Delivery) ---
    TASK_LEG_CHOICES = [
        ('single',       'Single Leg (Standard)'),
        ('hub_delivery', 'Hub Delivery — Leg 2 (To Customer)'),
    ]
    task_leg = models.CharField(
        max_length=20, choices=TASK_LEG_CHOICES, default='single',
        help_text="Leg type: 'single' = standard delivery. 'hub_delivery' = Leg 2 of hub model."
    )
    hub_pickup_batch = models.ForeignKey(
        HubPickupBatch,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='delivery_tasks',
        help_text="Batch that delivered this order's goods to hub (Leg 1 reference)."
    )
    hub_warehouse = models.ForeignKey(
        'warehouse.WarehouseLocation',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='hub_delivery_tasks',
        help_text="Hub warehouse this delivery leg originates from (for hub_delivery tasks)."
    )

    # --- Address Accuracy ---
    ADDRESS_ACCURACY_CHOICES = [
        ('by_customer', 'By Customer'),
        ('by_staff', 'By Staff'),
        ('by_driver', 'By Driver'),
        ('geocoded', 'Geocoded'),
        ('unverified', 'Unverified'),
    ]
    address_accuracy = models.CharField(
        max_length=20, choices=ADDRESS_ACCURACY_CHOICES, default='unverified', blank=True,
        help_text="Who provided/confirmed the delivery address coordinates"
    )

    # --- Customer Tracking ---
    tracking_token = models.CharField(
        max_length=64, unique=True, blank=True, null=True, db_index=True,
        help_text="Public token for customer tracking page URL"
    )

    # Safety flags
    delivery_distance_flag = models.BooleanField(default=False,
        help_text="Flagged: driver completed delivery far from address (>5km)")
    time_slot_missed = models.BooleanField(default=False,
        help_text="Delivered outside customer's preferred time slot")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.order}-{self.dl_task_number}"

    @property
    def has_cod(self):
        """Check if this delivery involves COD collection"""
        return self.order and self.order.cod_amount and self.order.cod_amount > 0

    def calculate_driver_earnings(self):
        """
        Calculate driver earnings based on order type and distance.

        Rules:
        - Pick & Drop orders: 80% of dl_price
        - Normal orders: Fixed QAR 10
        - Long distance (>20km): Requires manual adjustment by staff

        Returns:
            Decimal: Calculated earnings amount
        """
        from decimal import Decimal

        # Hub delivery leg (Leg 2): same as normal delivery
        if self.task_leg == 'hub_delivery':
            return Decimal('10.00')

        # Pick & Drop orders: 80% of delivery price
        if self.order and self.order.order_type == 'pick_and_drop':
            delivery_charge = Decimal(str(self.dl_price or 0))
            return delivery_charge * Decimal('0.80')

        # Normal single-leg orders: Fixed QAR 10
        return Decimal('10.00')

    def is_long_distance(self):
        """
        Check if delivery distance exceeds 20km (requires manual earnings adjustment).

        Returns:
            bool: True if distance > 20km
        """
        # Distance field doesn't exist yet - always return False for now
        # TODO: Add distance_km field to model and implement distance calculation
        return False

    class Meta:
        verbose_name_plural = "Delivery Task"


class TaskStatusPoint(models.Model):
    """
    GPS snapshot captured each time a delivery task changes status.
    Records driver location and distance from delivery address.
    """
    task = models.ForeignKey(
        DeliveryTask, on_delete=models.CASCADE, related_name='status_points'
    )
    driver = models.ForeignKey(
        'fleet.Driver', on_delete=models.SET_NULL, null=True, blank=True
    )
    old_status = models.CharField(max_length=100, blank=True)
    new_status = models.CharField(max_length=100)
    latitude = models.DecimalField(
        max_digits=10, decimal_places=7, null=True, blank=True,
        help_text="Driver GPS latitude at status change"
    )
    longitude = models.DecimalField(
        max_digits=10, decimal_places=7, null=True, blank=True,
        help_text="Driver GPS longitude at status change"
    )
    accuracy = models.FloatField(
        null=True, blank=True, help_text="GPS accuracy in metres"
    )
    distance_from_delivery = models.FloatField(
        null=True, blank=True,
        help_text="Distance from delivery location in km (Haversine)"
    )
    delivery_latitude = models.DecimalField(
        max_digits=10, decimal_places=7, null=True, blank=True,
        help_text="Delivery address latitude at time of status change"
    )
    delivery_longitude = models.DecimalField(
        max_digits=10, decimal_places=7, null=True, blank=True,
        help_text="Delivery address longitude at time of status change"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    @staticmethod
    def haversine_km(lat1, lon1, lat2, lon2):
        """Calculate great-circle distance between two points in km."""
        from math import radians, cos, sin, asin, sqrt
        lat1, lon1, lat2, lon2 = map(float, [lat1, lon1, lat2, lon2])
        lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
        return 2 * asin(sqrt(a)) * 6371

    def __str__(self):
        return f"Task {self.task_id} | {self.old_status} → {self.new_status} @ {self.created_at:%H:%M}"

    class Meta:
        verbose_name = "Task Status Point"
        verbose_name_plural = "Task Status Points"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['task', '-created_at'], name='tsp_task_ts_idx'),
        ]


class DeliveryTaskQRCode(models.Model):
    """
    QR Code for delivery tasks.
    Auto-generated when a delivery task is created.
    Contains the task number encoded as a QR code for scanning.
    """
    delivery_task = models.ForeignKey(
        DeliveryTask, on_delete=models.CASCADE, related_name='task_qrcode')
    task_number = models.CharField(max_length=100)
    qrcode = models.ImageField(
        upload_to="delivery/qrcodes/", blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"QR: {self.task_number}"

    def save(self, *args, **kwargs):
        # Auto-set task number from delivery task
        if self.delivery_task and not self.task_number:
            self.task_number = self.delivery_task.dl_task_number

        # Generate QR code if not exists
        if self.task_number and not self.qrcode:
            self.generate_qrcode()

        super().save(*args, **kwargs)

    def generate_qrcode(self):
        """Generate QR code image for the task number"""
        import qrcode
        from io import BytesIO
        from django.core.files import File

        # Create QR code
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(self.task_number)
        qr.make(fit=True)

        # Create image
        img = qr.make_image(fill_color="black", back_color="white")

        # Save to buffer
        buffer = BytesIO()
        img.save(buffer, format='PNG')
        buffer.seek(0)

        # Save to field
        self.qrcode.save(f"{self.task_number}_qr.png", File(buffer), save=False)

    class Meta:
        verbose_name = "Delivery Task QR Code"
        verbose_name_plural = "Delivery Task QR Codes"
        app_label = 'delivery'


class ZoneName(models.Model):
    zone_number = models.PositiveIntegerField(unique=True, db_index=True)
    zone_name = models.CharField(max_length=100, help_text="English name")
    zone_name_arabic = models.CharField(max_length=100, blank=True, null=True, help_text="Arabic name")
    latitude = models.DecimalField(
        max_digits=10, decimal_places=7, blank=True, null=True,
        help_text="Center point latitude"
    )
    longitude = models.DecimalField(
        max_digits=10, decimal_places=7, blank=True, null=True,
        help_text="Center point longitude"
    )
    polygon = models.JSONField(
        blank=True, null=True,
        help_text="Zone boundary coordinates as [[lat, lon], [lat, lon], ...] array"
    )
    neighbour_zones = models.ManyToManyField(
        'self',
        blank=True,
        symmetrical=True,
        help_text="Adjacent/nearby zones"
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        # Show all area names for this zone
        area_names = list(self.areas.values_list('area_name', flat=True))
        if area_names:
            areas_str = ', '.join(area_names[:5])  # Limit to 5 areas for display
            if len(area_names) > 5:
                areas_str += f' (+{len(area_names) - 5} more)'
            return f"Zone {self.zone_number} - {areas_str}"
        return f"Zone {self.zone_number} - {self.zone_name}"

    @property
    def all_area_names(self):
        """Returns comma-separated list of all area names"""
        area_names = list(self.areas.values_list('area_name', flat=True))
        return ', '.join(area_names) if area_names else self.zone_name

    @property
    def neighbour_zone_numbers(self):
        """Returns list of neighbour zone numbers"""
        return list(self.neighbour_zones.values_list('zone_number', flat=True))

    @property
    def has_polygon(self):
        """Check if zone has boundary polygon defined"""
        return bool(self.polygon and len(self.polygon) >= 3)

    @property
    def primary_zone_group_name(self):
        """Returns the name of the first active zone group this zone belongs to"""
        group = self.zone_groups.filter(is_active=True).order_by('display_order').first()
        return group.name if group else None

    class Meta:
        verbose_name = "Zone"
        verbose_name_plural = "Zones"
        app_label = 'delivery'
        ordering = ['zone_number']


class ZoneArea(models.Model):
    """
    Individual area/neighborhood names within a zone.
    Each zone can have multiple areas (e.g., Zone 5 has Fereej Al Asmakh, Al Najada, etc.)
    """
    zone = models.ForeignKey(
        ZoneName,
        on_delete=models.CASCADE,
        related_name='areas',
        help_text="Parent zone"
    )
    area_name = models.CharField(max_length=150, help_text="English area name")
    area_name_arabic = models.CharField(max_length=150, blank=True, null=True, help_text="Arabic area name")
    latitude = models.DecimalField(
        max_digits=10, decimal_places=7, blank=True, null=True,
        help_text="Area center latitude"
    )
    longitude = models.DecimalField(
        max_digits=10, decimal_places=7, blank=True, null=True,
        help_text="Area center longitude"
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.area_name} (Zone {self.zone.zone_number})"

    class Meta:
        verbose_name = "Zone Area"
        verbose_name_plural = "Zone Areas"
        app_label = 'delivery'
        ordering = ['zone__zone_number', 'area_name']
        unique_together = ['zone', 'area_name']


class ZoneGroup(models.Model):
    """
    Zone Group for grouping multiple zones into wider delivery areas.
    Examples: West Doha, Industrial Area, Pearl Qatar, etc.
    Drivers select zone groups to indicate their preferred delivery areas.
    """
    name = models.CharField(max_length=100, help_text="Group name (e.g., West Doha, Industrial Area)")
    description = models.TextField(blank=True, null=True, help_text="Description of the area covered")
    zones = models.ManyToManyField(
        ZoneName,
        related_name='zone_groups',
        help_text="Zones included in this group"
    )
    is_active = models.BooleanField(default=True)
    display_order = models.PositiveIntegerField(default=0, help_text="Order for display (lower = first)")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

    @property
    def zone_count(self):
        return self.zones.count()

    @property
    def zone_numbers_display(self):
        """Returns comma-separated zone numbers for display"""
        numbers = self.zones.values_list('zone_number', flat=True)
        return ', '.join(str(n) for n in sorted(numbers))

    class Meta:
        verbose_name = "Zone Group"
        verbose_name_plural = "Zone Groups"
        app_label = 'delivery'
        ordering = ['display_order', 'name']


class LatLonList(models.Model):
    zone_number = models.PositiveIntegerField()
    street_number = models.PositiveIntegerField()
    building_number = models.PositiveIntegerField(blank=True, null=True)
    latitude = models.DecimalField(max_digits=19, decimal_places=15, blank=True, null=True)
    longitude = models.DecimalField(max_digits=19, decimal_places=15, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Zone {self.zone_number} - Street {self.street_number}"

    class Meta:
        verbose_name_plural = "Lat/Lon Coordinates"
        app_label = 'delivery'



class AssignedDriver(models.Model):
    driver = models.ForeignKey(fleet_models.Driver, on_delete=models.CASCADE)
    dl_task = models.ForeignKey(DeliveryTask, on_delete=models.CASCADE)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.driver.driver_name

    class Meta:
        verbose_name_plural = "Assigned Driver"
        app_label = 'delivery'
        unique_together = [('driver', 'dl_task')]


def shipping_label_upload_path(instance, filename):
    """Generate upload path for shipping labels"""
    import os
    return os.path.join('shipping_labels', str(instance.order.business.business_code), filename)


class ShippingLabel(models.Model):
    """Automated shipping label created when order is published to delivery task"""
    LABEL_STATUS = (
        ('generated', 'Generated'),
        ('printed', 'Printed'),
        ('attached', 'Attached to Package'),
        ('void', 'Void'),
    )

    LABEL_FORMAT = (
        ('pdf', 'PDF'),
        ('png', 'PNG'),
        ('zpl', 'ZPL (Zebra)'),
    )

    # Relationships - linked to both Order and DeliveryTask
    order = models.ForeignKey(
        orders_models.Order, on_delete=models.CASCADE, related_name='shipping_labels')
    delivery_task = models.ForeignKey(
        DeliveryTask, on_delete=models.CASCADE, related_name='shipping_labels')

    # Label identification
    label_number = models.CharField(max_length=100, unique=True, db_index=True)
    barcode_data = models.CharField(max_length=255, blank=True, null=True)

    # Label file
    label_file = models.FileField(upload_to=shipping_label_upload_path, blank=True, null=True)
    label_format = models.CharField(max_length=10, choices=LABEL_FORMAT, default='png')

    # Label content (stored for regeneration)
    sender_name = models.CharField(max_length=255)
    sender_address = models.TextField()
    sender_phone = models.CharField(max_length=20)

    recipient_name = models.CharField(max_length=255)
    recipient_address = models.TextField()
    recipient_phone = models.CharField(max_length=20)
    recipient_zone = models.PositiveIntegerField(blank=True, null=True)
    recipient_street = models.PositiveIntegerField(blank=True, null=True)
    recipient_building = models.PositiveIntegerField(blank=True, null=True)

    # Delivery details on label
    cod_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    delivery_notes = models.TextField(blank=True, null=True)

    # Status tracking
    status = models.CharField(max_length=20, choices=LABEL_STATUS, default='generated')
    printed_at = models.DateTimeField(blank=True, null=True)
    printed_by = models.ForeignKey(
        'auth.User', on_delete=models.SET_NULL, null=True, blank=True, related_name='printed_labels')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Label {self.label_number} - {self.order.order_number}"

    class Meta:
        verbose_name_plural = "Shipping Labels"
        app_label = 'delivery'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['label_number'], name='label_number_idx'),
            models.Index(fields=['order', 'delivery_task'], name='label_order_task_idx'),
        ]


# =============================================================================
# DELIVERY PROOF MODELS
# =============================================================================


def delivery_proof_upload_path(instance, filename):
    import os
    biz_code = instance.delivery_task.business.business_code if instance.delivery_task and instance.delivery_task.business else 'unknown'
    return os.path.join('delivery_proofs', str(biz_code), filename)


class DeliveryProof(models.Model):
    """
    Proof of delivery uploaded by drivers.

    Stores delivery photos, signatures, and barcode scans with
    optional GPS coordinates for verification.
    """
    PROOF_TYPE_CHOICES = [
        ('photo', 'Delivery Photo'),
        ('signature', 'Customer Signature'),
        ('barcode_scan', 'Barcode Scan'),
    ]
    delivery_task = models.ForeignKey(
        'DeliveryTask', on_delete=models.CASCADE, related_name='delivery_proofs'
    )
    proof_type = models.CharField(max_length=20, choices=PROOF_TYPE_CHOICES, default='photo')
    photo = models.ImageField(upload_to=delivery_proof_upload_path)
    notes = models.CharField(max_length=255, blank=True, default='')
    barcode_data = models.CharField(
        max_length=255, blank=True, default='',
        help_text="Scanned barcode value"
    )
    latitude = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)
    longitude = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)
    uploaded_by = models.ForeignKey(
        'auth.User', on_delete=models.SET_NULL, null=True, blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'delivery_proof'
        ordering = ['-created_at']

    def __str__(self):
        return f"Proof {self.proof_type} for {self.delivery_task.dl_task_number}"
