import uuid
from django.db import models
from django.utils import timezone


class OrderBatch(models.Model):
    """
    Groups orders going to the same zone from the same pickup location.
    Max 2 orders per batch with 3-4 minute hold window.
    """

    BATCH_STATUS = (
        ('pending', 'Pending'),          # Waiting for match
        ('holding', 'Holding'),          # Timer active (3-4 min)
        ('ready', 'Ready'),              # For assignment
        ('assigned', 'Assigned'),        # To rider
        ('in_progress', 'In Progress'),  # Being delivered
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    )

    RELEASE_REASON = (
        ('batch_full', 'Batch Full'),
        ('timeout', 'Hold Window Expired'),
        ('sla_risk', 'SLA Risk'),
        ('manual', 'Manual Release'),
        ('off_peak', 'Off-Peak Single Release'),
    )

    batch_code = models.CharField(
        max_length=32,
        unique=True,
        db_index=True,
        editable=False
    )
    pickup_location = models.ForeignKey(
        'business.PickupLocation',
        on_delete=models.CASCADE,
        related_name='batches',
        db_index=True
    )
    destination_zone = models.PositiveIntegerField(db_index=True)

    status = models.CharField(
        max_length=20,
        choices=BATCH_STATUS,
        default='pending',
        db_index=True
    )
    release_reason = models.CharField(
        max_length=20,
        choices=RELEASE_REASON,
        blank=True,
        null=True
    )

    # Timing
    hold_started_at = models.DateTimeField(blank=True, null=True)
    hold_expires_at = models.DateTimeField(blank=True, null=True, db_index=True)
    released_at = models.DateTimeField(blank=True, null=True)

    # Assignment
    assigned_rider = models.ForeignKey(
        'fleet.Driver',
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name='assigned_batches'
    )
    assigned_shift = models.ForeignKey(
        'dispatch.RiderShift',
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name='batches'
    )
    assigned_at = models.DateTimeField(blank=True, null=True)

    # Metrics
    order_count = models.PositiveSmallIntegerField(default=0)
    total_cod = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0
    )
    estimated_delivery_time = models.DurationField(blank=True, null=True)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        verbose_name = 'Order Batch'
        verbose_name_plural = 'Order Batches'
        ordering = ['-created_at']
        indexes = [
            models.Index(
                fields=['pickup_location', 'destination_zone', 'status'],
                name='batch_loc_zone_status_idx'
            ),
            models.Index(
                fields=['status', 'hold_expires_at'],
                name='batch_status_expires_idx'
            ),
            models.Index(
                fields=['assigned_rider', 'status'],
                name='batch_rider_status_idx'
            ),
        ]

    def __str__(self):
        return f"Batch {self.batch_code} - Zone {self.destination_zone} ({self.order_count}/2)"

    def save(self, *args, **kwargs):
        if not self.batch_code:
            self.batch_code = f"BTH-{uuid.uuid4().hex[:8].upper()}"
        super().save(*args, **kwargs)

    @property
    def is_full(self):
        return self.order_count >= 2

    @property
    def can_add_order(self):
        return self.status in ['pending', 'holding'] and self.order_count < 2

    @property
    def hold_remaining_seconds(self):
        if self.hold_expires_at and self.status == 'holding':
            remaining = (self.hold_expires_at - timezone.now()).total_seconds()
            return max(0, int(remaining))
        return 0


class BatchOrder(models.Model):
    """Links orders to batches with delivery sequence."""

    batch = models.ForeignKey(
        OrderBatch,
        on_delete=models.CASCADE,
        related_name='batch_orders'
    )
    order = models.OneToOneField(
        'orders.Order',
        on_delete=models.CASCADE,
        related_name='batch_assignment'
    )
    sequence = models.PositiveSmallIntegerField(default=1)  # 1 or 2
    added_at = models.DateTimeField(auto_now_add=True)

    # SLA tracking
    sla_deadline = models.DateTimeField(blank=True, null=True)
    is_sla_at_risk = models.BooleanField(default=False)

    class Meta:
        verbose_name = 'Batch Order'
        verbose_name_plural = 'Batch Orders'
        unique_together = ('batch', 'order')
        ordering = ['sequence']
        indexes = [
            models.Index(
                fields=['batch', 'sequence'],
                name='batchorder_seq_idx'
            ),
            models.Index(
                fields=['sla_deadline'],
                name='batchorder_sla_idx'
            ),
        ]

    def __str__(self):
        return f"Order {self.order.order_number} in {self.batch.batch_code} (#{self.sequence})"

    @property
    def sla_remaining_minutes(self):
        if self.sla_deadline:
            remaining = (self.sla_deadline - timezone.now()).total_seconds() / 60
            return max(0, int(remaining))
        return None


class RiderShift(models.Model):
    """
    Locks a rider to a single store/pickup location for a shift.
    Enforces the rider-store mapping required by the SOP.
    """

    SHIFT_STATUS = (
        ('scheduled', 'Scheduled'),
        ('active', 'Active'),
        ('break', 'On Break'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
        ('no_show', 'No Show'),
    )

    SHIFT_TYPE = (
        ('morning', 'Morning (6AM-2PM)'),
        ('afternoon', 'Afternoon (2PM-10PM)'),
        ('night', 'Night (10PM-6AM)'),
        ('custom', 'Custom Hours'),
    )

    shift_code = models.CharField(
        max_length=32,
        unique=True,
        db_index=True,
        editable=False
    )
    rider = models.ForeignKey(
        'fleet.Driver',
        on_delete=models.CASCADE,
        related_name='shifts',
        db_index=True
    )
    pickup_location = models.ForeignKey(
        'business.PickupLocation',
        on_delete=models.CASCADE,
        related_name='shifts',
        db_index=True
    )

    shift_type = models.CharField(
        max_length=20,
        choices=SHIFT_TYPE,
        default='custom'
    )
    status = models.CharField(
        max_length=20,
        choices=SHIFT_STATUS,
        default='scheduled',
        db_index=True
    )

    # Timing
    scheduled_start = models.DateTimeField(db_index=True)
    scheduled_end = models.DateTimeField()
    actual_start = models.DateTimeField(blank=True, null=True)
    actual_end = models.DateTimeField(blank=True, null=True)

    # Breaks
    break_start = models.DateTimeField(blank=True, null=True)
    break_end = models.DateTimeField(blank=True, null=True)
    total_break_minutes = models.PositiveIntegerField(default=0)

    # Performance
    batches_completed = models.PositiveIntegerField(default=0)
    orders_delivered = models.PositiveIntegerField(default=0)

    # Audit
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        'auth.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_shifts'
    )

    class Meta:
        verbose_name = 'Rider Shift'
        verbose_name_plural = 'Rider Shifts'
        ordering = ['-scheduled_start']
        indexes = [
            models.Index(
                fields=['rider', 'status', 'scheduled_start'],
                name='shift_rider_status_idx'
            ),
            models.Index(
                fields=['pickup_location', 'status'],
                name='shift_location_status_idx'
            ),
            models.Index(
                fields=['scheduled_start', 'scheduled_end'],
                name='shift_time_idx'
            ),
        ]
        constraints = [
            models.CheckConstraint(
                check=models.Q(scheduled_end__gt=models.F('scheduled_start')),
                name='shift_end_after_start'
            ),
        ]

    def __str__(self):
        return f"{self.rider} @ {self.pickup_location} ({self.scheduled_start.date()})"

    def save(self, *args, **kwargs):
        if not self.shift_code:
            self.shift_code = f"SFT-{uuid.uuid4().hex[:8].upper()}"
        super().save(*args, **kwargs)

    @property
    def is_active(self):
        now = timezone.now()
        return (
            self.status == 'active' and
            self.actual_start and
            not self.actual_end and
            now >= self.actual_start
        )

    @property
    def duration_hours(self):
        if self.actual_start and self.actual_end:
            duration = self.actual_end - self.actual_start
            return round(duration.total_seconds() / 3600, 2)
        elif self.scheduled_start and self.scheduled_end:
            duration = self.scheduled_end - self.scheduled_start
            return round(duration.total_seconds() / 3600, 2)
        return 0


class RiderKPI(models.Model):
    """Daily KPI metrics for riders - used for performance tracking and shift assignment."""

    rider = models.ForeignKey(
        'fleet.Driver',
        on_delete=models.CASCADE,
        related_name='kpis'
    )
    date = models.DateField(db_index=True)
    pickup_location = models.ForeignKey(
        'business.PickupLocation',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='rider_kpis'
    )

    # Order metrics
    total_orders = models.PositiveIntegerField(default=0)
    batched_orders = models.PositiveIntegerField(default=0)
    single_orders = models.PositiveIntegerField(default=0)

    # Batch metrics
    total_batches = models.PositiveIntegerField(default=0)
    batches_with_2_orders = models.PositiveIntegerField(default=0)

    # Time metrics (in minutes)
    total_active_minutes = models.PositiveIntegerField(default=0)
    avg_delivery_time = models.PositiveIntegerField(default=0)

    # SLA metrics
    sla_compliant_orders = models.PositiveIntegerField(default=0)
    sla_breached_orders = models.PositiveIntegerField(default=0)

    # Computed metrics (updated by signals/tasks)
    orders_per_hour = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0
    )
    batching_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0
    )
    sla_compliance_rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Rider KPI'
        verbose_name_plural = 'Rider KPIs'
        unique_together = ('rider', 'date', 'pickup_location')
        ordering = ['-date']
        indexes = [
            models.Index(
                fields=['rider', 'date'],
                name='kpi_rider_date_idx'
            ),
            models.Index(
                fields=['date', 'pickup_location'],
                name='kpi_date_location_idx'
            ),
        ]

    def __str__(self):
        return f"KPI: {self.rider} on {self.date} ({self.batching_percentage}% batched)"

    def calculate_metrics(self):
        """Recalculate computed metrics."""
        if self.total_orders > 0:
            self.batching_percentage = (self.batched_orders / self.total_orders) * 100
            self.single_orders = self.total_orders - self.batched_orders

        sla_total = self.sla_compliant_orders + self.sla_breached_orders
        if sla_total > 0:
            self.sla_compliance_rate = (self.sla_compliant_orders / sla_total) * 100

        if self.total_active_minutes > 0:
            hours = self.total_active_minutes / 60
            self.orders_per_hour = self.total_orders / hours if hours > 0 else 0


class DispatchConfig(models.Model):
    """
    Configuration for dispatch behavior per pickup location.
    Allows per-store customization of batching parameters.
    """

    pickup_location = models.OneToOneField(
        'business.PickupLocation',
        on_delete=models.CASCADE,
        related_name='dispatch_config',
        primary_key=True
    )

    # Batching settings
    max_batch_size = models.PositiveSmallIntegerField(
        default=2,
        help_text='Maximum orders per batch'
    )
    hold_window_seconds = models.PositiveIntegerField(
        default=180,
        help_text='Default hold window in seconds (3 min)'
    )
    min_hold_seconds = models.PositiveIntegerField(
        default=120,
        help_text='Minimum hold window (2 min)'
    )
    max_hold_seconds = models.PositiveIntegerField(
        default=240,
        help_text='Maximum hold window (4 min)'
    )

    # SLA settings
    sla_minutes = models.PositiveIntegerField(
        default=60,
        help_text='Target delivery SLA in minutes'
    )
    sla_buffer_minutes = models.PositiveIntegerField(
        default=15,
        help_text='Release batch if SLA deadline is within this buffer'
    )
    sla_override_enabled = models.BooleanField(
        default=True,
        help_text='Auto-release batches when SLA at risk'
    )

    # Rider settings
    max_orders_per_rider = models.PositiveSmallIntegerField(
        default=2,
        help_text='Maximum active orders per rider'
    )
    max_batches_per_rider = models.PositiveSmallIntegerField(
        default=1,
        help_text='Maximum active batches per rider'
    )

    # Peak hour settings (Doha market)
    peak_start_1 = models.TimeField(
        default='11:00:00',
        help_text='Lunch peak start'
    )
    peak_end_1 = models.TimeField(
        default='14:00:00',
        help_text='Lunch peak end'
    )
    peak_start_2 = models.TimeField(
        default='18:00:00',
        help_text='Dinner peak start'
    )
    peak_end_2 = models.TimeField(
        default='21:00:00',
        help_text='Dinner peak end'
    )
    enforce_batching_peak = models.BooleanField(
        default=True,
        help_text='Strictly enforce batching during peak hours'
    )
    allow_single_release_offpeak = models.BooleanField(
        default=True,
        help_text='Allow single-order release during off-peak'
    )

    # Feature flags
    batching_enabled = models.BooleanField(
        default=True,
        help_text='Enable order batching for this location'
    )
    auto_assignment_enabled = models.BooleanField(
        default=True,
        help_text='Enable automatic rider assignment'
    )
    zone_priority_enabled = models.BooleanField(
        default=True,
        help_text='Prioritize riders familiar with destination zone'
    )
    load_balancing_enabled = models.BooleanField(
        default=True,
        help_text='Distribute orders evenly among riders'
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Dispatch Config'
        verbose_name_plural = 'Dispatch Configs'

    def __str__(self):
        return f"Config: {self.pickup_location}"

    @classmethod
    def get_config_for_location(cls, pickup_location):
        """Get config for a location, creating default if needed."""
        config, created = cls.objects.get_or_create(
            pickup_location=pickup_location
        )
        return config

    def is_peak_hours(self):
        """Check if current time is within peak hours."""
        now = timezone.now().time()

        in_peak_1 = self.peak_start_1 <= now <= self.peak_end_1
        in_peak_2 = self.peak_start_2 <= now <= self.peak_end_2

        return in_peak_1 or in_peak_2


class DispatchLog(models.Model):
    """Audit log for dispatch actions - useful for debugging and analytics."""

    ACTION_TYPES = (
        ('batch_created', 'Batch Created'),
        ('order_added', 'Order Added to Batch'),
        ('batch_released', 'Batch Released'),
        ('batch_assigned', 'Batch Assigned to Rider'),
        ('batch_started', 'Batch Delivery Started'),
        ('batch_completed', 'Batch Completed'),
        ('batch_cancelled', 'Batch Cancelled'),
        ('sla_warning', 'SLA Warning Triggered'),
        ('sla_override', 'SLA Override Release'),
        ('shift_started', 'Shift Started'),
        ('shift_ended', 'Shift Ended'),
        ('shift_break_start', 'Shift Break Started'),
        ('shift_break_end', 'Shift Break Ended'),
        ('config_changed', 'Config Changed'),
        ('manual_override', 'Manual Override'),
    )

    action = models.CharField(
        max_length=30,
        choices=ACTION_TYPES,
        db_index=True
    )

    # References (all optional since not all actions have all references)
    batch = models.ForeignKey(
        OrderBatch,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='logs'
    )
    order = models.ForeignKey(
        'orders.Order',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='dispatch_logs'
    )
    rider = models.ForeignKey(
        'fleet.Driver',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='dispatch_logs'
    )
    shift = models.ForeignKey(
        RiderShift,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='logs'
    )

    # Action-specific data
    details = models.JSONField(default=dict, blank=True)

    # Audit
    performed_by = models.ForeignKey(
        'auth.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='dispatch_actions'
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = 'Dispatch Log'
        verbose_name_plural = 'Dispatch Logs'
        ordering = ['-created_at']
        indexes = [
            models.Index(
                fields=['action', '-created_at'],
                name='displog_action_time_idx'
            ),
            models.Index(
                fields=['batch', '-created_at'],
                name='displog_batch_time_idx'
            ),
        ]

    def __str__(self):
        return f"{self.get_action_display()} at {self.created_at}"
