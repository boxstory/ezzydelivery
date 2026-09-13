# Purpose: Salaried drivers — the standing agreement, the monthly run, and the slip that pays it.
#          A slip is base + bonus lines - deduction lines; both line kinds live for one month only.
# Used by: payroll.services (target absorption), payroll.views (staff console), workforce.views publish step
# Notes: Deliberately its own module, not a pay-type flag on Driver. A salary is an agreement with its
#        own period, its own paper trail and its own money leg; per-delivery earnings, COD and client
#        charges each keep their existing legs untouched.

from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils import timezone


def month_start(value):
    """The first of the month for a date — the key every salary period is filed under."""
    return value.replace(day=1)


def month_bounds(value):
    """(first day, last day) of the month containing `value`.

    Agreements are day-precise, so deciding whether one touches a month is an
    overlap test against both ends — not a comparison with the 1st.
    """
    import calendar
    first = month_start(value)
    return first, first.replace(day=calendar.monthrange(first.year, first.month)[1])


class SalaryStructure(models.Model):
    """What a driver is paid each month, and how many deliveries that covers.

    Held as a dated agreement rather than a field on Driver so a rate change is a
    new row: last month's slip can still show the figure that was actually agreed
    when it was paid.
    """

    driver = models.ForeignKey(
        'fleet.Driver', on_delete=models.CASCADE, related_name='salary_structures',
        db_index=True,
    )
    monthly_amount = models.DecimalField(
        max_digits=10, decimal_places=2,
        help_text="Fixed monthly salary in QAR, before deductions.",
    )
    delivery_target = models.PositiveIntegerField(
        default=0,
        help_text="Deliveries the salary covers in a month. Anything beyond this "
                  "earns the normal per-delivery fee on top.",
    )
    effective_from = models.DateField(
        help_text="First day this agreement applies.",
    )
    effective_to = models.DateField(
        null=True, blank=True,
        help_text="Last day it applies. Empty means it is still running.",
    )
    notes = models.TextField(blank=True, default='')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='salary_structures_created',
    )

    class Meta:
        ordering = ['-effective_from', '-id']
        indexes = [models.Index(fields=['driver', 'effective_from'])]

    def __str__(self):
        return f"{self.driver_id} · {self.monthly_amount} QAR/month"

    def covers_date(self, on_date):
        if on_date < self.effective_from:
            return False
        return self.effective_to is None or on_date <= self.effective_to

    @property
    def is_open(self):
        return self.effective_to is None


class SalaryRun(models.Model):
    """One month of payroll. Slips hang off it; it is never itself a payment."""

    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('paid', 'Paid'),
    ]

    period_month = models.DateField(
        unique=True,
        help_text="First day of the month this run pays.",
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    notes = models.TextField(blank=True, default='')

    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='salary_runs_created',
    )

    class Meta:
        ordering = ['-period_month']

    def __str__(self):
        return f"Salary {self.period_month:%b %Y}"

    @property
    def is_paid(self):
        return self.status == 'paid'


class SalarySlip(models.Model):
    """One driver's salary for one month: base, deductions, net, and how it was paid.

    Figures are snapshots. Editing the structure later must never move a slip that
    has already been handed over.
    """

    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('paid', 'Paid'),
    ]
    PAYMENT_METHODS = [
        ('cash', 'Cash'),
        ('bank', 'Bank transfer'),
        ('fawran', 'Fawran'),
    ]

    run = models.ForeignKey(SalaryRun, on_delete=models.CASCADE, related_name='slips')
    driver = models.ForeignKey(
        'fleet.Driver', on_delete=models.PROTECT, related_name='salary_slips',
    )
    structure = models.ForeignKey(
        SalaryStructure, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='slips',
    )
    slip_code = models.CharField(max_length=40, unique=True)

    base_amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    # Bonus / extra pay agreed on top of the salary for this month only — overtime,
    # a hard week, a performance bonus. Kept apart from base_amount so next month's
    # slip starts from the standing agreement again rather than from a one-off.
    additions_total = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    deductions_total = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    net_amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))

    # Snapshot of the delivery position, so the slip explains what the salary bought.
    delivery_target = models.PositiveIntegerField(default=0)
    # The slice of the month the agreement actually covered. Equal to the whole
    # month in the normal case; narrower when a salary started or ended mid-month.
    # There is no pro-rating by design, so a partial month still pays in full —
    # this is what tells staff to consider a deduction.
    covered_from = models.DateField(null=True, blank=True)
    covered_to = models.DateField(null=True, blank=True)
    deliveries_covered = models.PositiveIntegerField(
        default=0, help_text="Deliveries absorbed by the salary in this month.",
    )
    deliveries_incentive = models.PositiveIntegerField(
        default=0, help_text="Deliveries beyond the target, paid on the per-delivery leg.",
    )

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHODS, blank=True, default='')
    payment_reference = models.CharField(max_length=100, blank=True, default='')
    paid_at = models.DateTimeField(null=True, blank=True)
    paid_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='salary_slips_paid',
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['driver_id']
        constraints = [
            models.UniqueConstraint(fields=['run', 'driver'], name='payroll_one_slip_per_driver_per_run'),
        ]

    def __str__(self):
        return self.slip_code

    @property
    def is_partial_period(self):
        """True when the agreement did not span the whole month this run pays."""
        if not self.covered_from or not self.covered_to:
            return False
        first, last = month_bounds(self.run.period_month)
        return self.covered_from > first or self.covered_to < last

    @property
    def gross_amount(self):
        """What the month is worth before anything is taken off."""
        return self.base_amount + self.additions_total

    def recalculate(self, save=True):
        """Net is base, plus bonus lines, minus deduction lines.

        Both sides are re-summed from the lines rather than adjusted in place, so a
        line removed by one staff member cannot leave a stale total behind.
        """
        additions = sum(
            (line.amount for line in self.addition_lines.all()), Decimal('0.00')
        )
        deductions = sum(
            (line.amount for line in self.deduction_lines.all()), Decimal('0.00')
        )
        self.additions_total = additions
        self.deductions_total = deductions
        self.net_amount = self.base_amount + additions - deductions
        if save:
            self.save(update_fields=[
                'additions_total', 'deductions_total', 'net_amount', 'updated_at',
            ])
        return self.net_amount

    def mark_paid(self, method, reference, user):
        self.status = 'paid'
        self.payment_method = method
        self.payment_reference = reference or ''
        self.paid_at = timezone.now()
        self.paid_by = user
        self.save(update_fields=[
            'status', 'payment_method', 'payment_reference', 'paid_at', 'paid_by', 'updated_at',
        ])


class SalaryAddition(models.Model):
    """A line added to one slip — bonus, overtime, allowance, extra work.

    The mirror of SalaryDeduction and deliberately a separate line rather than an
    edit to base_amount: a bonus belongs to the month it was earned, and the
    standing agreement must read the same next month.

    Deliveries past the target are NOT paid here — they keep their own
    per-delivery leg on the payout desk. This is for work a delivery count does
    not describe.
    """

    slip = models.ForeignKey(SalarySlip, on_delete=models.CASCADE, related_name='addition_lines')
    label = models.CharField(max_length=120)
    amount = models.DecimalField(max_digits=10, decimal_places=2)

    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='salary_additions_created',
    )

    class Meta:
        ordering = ['id']

    def __str__(self):
        return f"{self.label} +{self.amount}"


class SalaryDeduction(models.Model):
    """A line taken off one slip — advance, fine, fuel, SIM, anything staff name."""

    slip = models.ForeignKey(SalarySlip, on_delete=models.CASCADE, related_name='deduction_lines')
    label = models.CharField(max_length=120)
    amount = models.DecimalField(max_digits=10, decimal_places=2)

    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='salary_deductions_created',
    )

    class Meta:
        ordering = ['id']

    def __str__(self):
        return f"{self.label} {self.amount}"


class SalaryCoveredTask(models.Model):
    """A delivery the salary absorbed, so no per-delivery earning was created.

    The record is what makes the target auditable: without it, "why did this
    delivery pay nothing?" has no answer six weeks later, and a re-publish could
    silently absorb a task twice.
    """

    driver = models.ForeignKey(
        'fleet.Driver', on_delete=models.CASCADE, related_name='salary_covered_tasks',
    )
    task = models.OneToOneField(
        'delivery.DeliveryTask', on_delete=models.CASCADE, related_name='salary_cover',
    )
    period_month = models.DateField(db_index=True)
    structure = models.ForeignKey(
        SalaryStructure, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='covered_tasks',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [models.Index(fields=['driver', 'period_month'])]

    def __str__(self):
        return f"covered task {self.task_id}"
