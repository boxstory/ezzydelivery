from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone

from .models import RiderShift, DispatchConfig
from fleet.models import Driver
from business.models import PickupLocation


class RiderShiftForm(forms.ModelForm):
    """Form for creating and editing rider shifts"""

    rider = forms.ModelChoiceField(
        queryset=Driver.objects.filter(driver_status='Approved'),
        widget=forms.Select(attrs={'class': 'form-select'}),
        help_text='Select an approved rider'
    )

    pickup_location = forms.ModelChoiceField(
        queryset=PickupLocation.objects.filter(is_active=True),
        widget=forms.Select(attrs={'class': 'form-select'}),
        help_text='Store the rider will be locked to for this shift'
    )

    scheduled_start = forms.DateTimeField(
        widget=forms.DateTimeInput(
            attrs={'class': 'form-control', 'type': 'datetime-local'}
        )
    )

    scheduled_end = forms.DateTimeField(
        widget=forms.DateTimeInput(
            attrs={'class': 'form-control', 'type': 'datetime-local'}
        )
    )

    class Meta:
        model = RiderShift
        fields = ['rider', 'pickup_location', 'scheduled_start', 'scheduled_end']

    def clean(self):
        cleaned_data = super().clean()
        scheduled_start = cleaned_data.get('scheduled_start')
        scheduled_end = cleaned_data.get('scheduled_end')
        rider = cleaned_data.get('rider')

        if scheduled_start and scheduled_end:
            # Validate end is after start
            if scheduled_end <= scheduled_start:
                raise ValidationError('Scheduled end must be after scheduled start')

            # Validate shift duration (max 12 hours)
            duration = (scheduled_end - scheduled_start).total_seconds() / 3600
            if duration > 12:
                raise ValidationError('Shift duration cannot exceed 12 hours')

            # Validate minimum duration (1 hour)
            if duration < 1:
                raise ValidationError('Shift must be at least 1 hour')

            # Check for overlapping shifts for the same rider
            if rider:
                overlapping = RiderShift.objects.filter(
                    rider=rider,
                    status__in=['scheduled', 'active'],
                    scheduled_start__lt=scheduled_end,
                    scheduled_end__gt=scheduled_start
                )

                # Exclude current instance if editing
                if self.instance and self.instance.pk:
                    overlapping = overlapping.exclude(pk=self.instance.pk)

                if overlapping.exists():
                    raise ValidationError(
                        f'Rider {rider.driver_code} already has an overlapping shift scheduled'
                    )

        return cleaned_data


class RiderShiftEditForm(RiderShiftForm):
    """Extended form for editing shifts with status changes"""

    status = forms.ChoiceField(
        choices=RiderShift.STATUS_CHOICES,
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    class Meta:
        model = RiderShift
        fields = ['rider', 'pickup_location', 'scheduled_start', 'scheduled_end', 'status']

    def clean_status(self):
        status = self.cleaned_data.get('status')
        current_status = self.instance.status if self.instance else None

        # Validate status transitions
        valid_transitions = {
            'scheduled': ['scheduled', 'active', 'completed'],
            'active': ['active', 'break', 'completed'],
            'break': ['break', 'active', 'completed'],
            'completed': ['completed'],  # Can't change from completed
        }

        if current_status and status not in valid_transitions.get(current_status, []):
            raise ValidationError(
                f'Cannot transition from {current_status} to {status}'
            )

        return status


class DispatchConfigForm(forms.ModelForm):
    """Form for editing dispatch configuration per location"""

    class Meta:
        model = DispatchConfig
        fields = [
            'max_batch_size',
            'hold_window_seconds',
            'max_hold_seconds',
            'sla_minutes',
            'sla_buffer_minutes',
            'max_orders_per_rider',
            'peak_start_1',
            'peak_end_1',
            'peak_start_2',
            'peak_end_2',
            'batching_enabled',
            'auto_assignment_enabled',
        ]
        widgets = {
            'max_batch_size': forms.NumberInput(attrs={'class': 'form-control', 'min': 1, 'max': 5}),
            'hold_window_seconds': forms.NumberInput(attrs={'class': 'form-control', 'min': 60, 'max': 600}),
            'max_hold_seconds': forms.NumberInput(attrs={'class': 'form-control', 'min': 120, 'max': 900}),
            'sla_minutes': forms.NumberInput(attrs={'class': 'form-control', 'min': 30, 'max': 180}),
            'sla_buffer_minutes': forms.NumberInput(attrs={'class': 'form-control', 'min': 5, 'max': 30}),
            'max_orders_per_rider': forms.NumberInput(attrs={'class': 'form-control', 'min': 1, 'max': 5}),
            'peak_start_1': forms.TimeInput(attrs={'class': 'form-control', 'type': 'time'}),
            'peak_end_1': forms.TimeInput(attrs={'class': 'form-control', 'type': 'time'}),
            'peak_start_2': forms.TimeInput(attrs={'class': 'form-control', 'type': 'time'}),
            'peak_end_2': forms.TimeInput(attrs={'class': 'form-control', 'type': 'time'}),
            'batching_enabled': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'auto_assignment_enabled': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def clean(self):
        cleaned_data = super().clean()

        hold_window = cleaned_data.get('hold_window_seconds')
        max_hold = cleaned_data.get('max_hold_seconds')

        if hold_window and max_hold:
            if hold_window > max_hold:
                raise ValidationError('Hold window cannot exceed max hold time')

        sla_minutes = cleaned_data.get('sla_minutes')
        sla_buffer = cleaned_data.get('sla_buffer_minutes')

        if sla_minutes and sla_buffer:
            if sla_buffer >= sla_minutes:
                raise ValidationError('SLA buffer must be less than SLA target')

        return cleaned_data


class BatchFilterForm(forms.Form):
    """Form for filtering batches in the list view"""

    STATUS_CHOICES = [('', 'All Statuses')] + list([
        ('pending', 'Pending'),
        ('holding', 'Holding'),
        ('ready', 'Ready'),
        ('assigned', 'Assigned'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ])

    status = forms.ChoiceField(
        choices=STATUS_CHOICES,
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    location = forms.ModelChoiceField(
        queryset=PickupLocation.objects.filter(is_active=True),
        required=False,
        empty_label='All Locations',
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    zone = forms.IntegerField(
        required=False,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Zone #'})
    )

    date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'})
    )


class ShiftFilterForm(forms.Form):
    """Form for filtering shifts in the list view"""

    STATUS_CHOICES = [('', 'All Statuses')] + list(RiderShift.STATUS_CHOICES)

    status = forms.ChoiceField(
        choices=STATUS_CHOICES,
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    location = forms.ModelChoiceField(
        queryset=PickupLocation.objects.filter(is_active=True),
        required=False,
        empty_label='All Locations',
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'})
    )
