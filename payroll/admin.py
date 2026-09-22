# Purpose: Admin access to salary agreements, runs and slips for back-office correction.
# Used by: Django admin
# Notes: Never fields="__all__" — every form names its fields explicitly (core input-hardening rule).

from django.contrib import admin

from payroll import models as payroll_models
from .models import (
    SalaryAddition, SalaryCoveredTask, SalaryDeduction, SalaryRun, SalarySlip,
    SalaryStructure,
)


@admin.register(SalaryStructure)
class SalaryStructureAdmin(admin.ModelAdmin):
    list_display = ('driver', 'monthly_amount', 'delivery_target', 'effective_from', 'effective_to')
    list_filter = ('effective_from', 'effective_to')
    search_fields = ('monthly_amount', 'notes', 'driver__driver_code', 'created_by__username')
    fields = ('driver', 'monthly_amount', 'delivery_target', 'effective_from', 'effective_to', 'notes')
    raw_id_fields = ('driver',)


class SalaryAdditionInline(admin.TabularInline):
    model = SalaryAddition
    fields = ('label', 'amount')
    extra = 0


class SalaryDeductionInline(admin.TabularInline):
    model = SalaryDeduction
    fields = ('label', 'amount')
    extra = 0


@admin.register(SalarySlip)
class SalarySlipAdmin(admin.ModelAdmin):
    list_display = ('slip_code', 'driver', 'run', 'base_amount', 'additions_total',
                    'deductions_total', 'net_amount', 'status')
    list_filter = ('status', 'run')
    search_fields = ('slip_code', 'status', 'base_amount', 'additions_total', 'deductions_total',
                     'net_amount', 'payment_method', 'payment_reference', 'driver__driver_code',
                     'paid_by__username')
    fields = ('run', 'driver', 'structure', 'slip_code', 'base_amount', 'additions_total',
              'deductions_total', 'net_amount', 'delivery_target', 'deliveries_covered',
              'deliveries_incentive', 'status', 'payment_method', 'payment_reference', 'paid_at')
    raw_id_fields = ('run', 'driver', 'structure')
    inlines = [SalaryAdditionInline, SalaryDeductionInline]


@admin.register(SalaryRun)
class SalaryRunAdmin(admin.ModelAdmin):
    list_display = ('period_month', 'status', 'created_at')
    list_filter = ('status',)
    search_fields = ('period_month', 'status', 'notes', 'created_by__username')
    fields = ('period_month', 'status', 'notes')


@admin.register(SalaryCoveredTask)
class SalaryCoveredTaskAdmin(admin.ModelAdmin):
    list_display = ('task', 'driver', 'period_month', 'created_at')
    list_filter = ('period_month',)
    search_fields = ('driver__driver_code', 'task__dl_task_number')
    fields = ('driver', 'task', 'period_month', 'structure')
    raw_id_fields = ('driver', 'task', 'structure')

# ─────────────────────────────────────────────────────────────────────────────
# Tables that had no admin page. Registered so every model is reachable and
# searchable from /dj-admin/. Related rows use raw id fields so a changelist
# never renders a dropdown of the whole table.
# ─────────────────────────────────────────────────────────────────────────────

@admin.register(payroll_models.SalaryAddition)
class SalaryAdditionAdmin(admin.ModelAdmin):
    list_display = ('slip', 'label', 'amount', 'created_at', 'created_by')
    search_fields = ('label', 'amount', 'slip__slip_code', 'created_by__username')
    list_select_related = ('slip', 'created_by')
    raw_id_fields = ('slip', 'created_by')

@admin.register(payroll_models.SalaryDeduction)
class SalaryDeductionAdmin(admin.ModelAdmin):
    list_display = ('slip', 'label', 'amount', 'created_at', 'created_by')
    search_fields = ('label', 'amount', 'slip__slip_code', 'created_by__username')
    list_select_related = ('slip', 'created_by')
    raw_id_fields = ('slip', 'created_by')
