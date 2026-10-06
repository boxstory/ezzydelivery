"""
Delivery Forms Module
=====================

Forms for delivery address updates and driver assignments.
"""

from django import forms
from crispy_forms.helper import FormHelper
from delivery import models as delivery_models
from core.forms_base import SanitizedForm, SanitizedFormMixin, SanitizedModelForm


class DlAddressUpdateForm(SanitizedModelForm):
    """
    Form for updating delivery address information.

    Only exposes customer-editable fields. Protected fields like
    dl_task_number and order are set in the view, not by user input.
    """
    class Meta:
        model = delivery_models.DlAddressUpdate
        fields = [
            'full_name',
            'mobile_no',
            'area_name',
            'dl_zone',
            'dl_building',
            'dl_street',
            'dl_unit',
            'dl_latitude',
            'dl_longitude',
            'is_villa_compound',
            'is_flat',
            'is_office',
            'time_slot',
        ]
        widgets = {
            'time_slot': forms.CheckboxSelectMultiple(choices=[
                ('Morning', 'Morning'),
                ('Afternoon', 'Afternoon'),
                ('Evening', 'Evening'),
                ('Night', 'Night'),
            ]),
            'dl_latitude': forms.HiddenInput(),
            'dl_longitude': forms.HiddenInput(),
        }

    def __init__(self, *args, **kwargs):
        # Extract dl_task_number for validation if provided
        self.dl_task_number = kwargs.pop('dl_task_number', None)
        super(DlAddressUpdateForm, self).__init__(*args, **kwargs)
        self.helper = FormHelper()

        # Configure time_slot widget
        self.fields['time_slot'].widget = forms.CheckboxSelectMultiple(choices=[
            ('Morning', 'Morning'),
            ('Afternoon', 'Afternoon'),
            ('Evening', 'Evening'),
            ('Night', 'Night'),
        ])
        self.fields['time_slot'].widget.attrs.update({'class': 'd-flex flex-wrap'})

    def clean_mobile_no(self):
        """Validate mobile number format."""
        mobile = self.cleaned_data.get('mobile_no')
        if mobile:
            # Remove common separators
            cleaned = mobile.replace(' ', '').replace('-', '').replace('+', '')
            if not cleaned.isdigit():
                raise forms.ValidationError("Mobile number must contain only digits.")
            if len(cleaned) < 8:
                raise forms.ValidationError("Mobile number is too short.")
        return mobile


class DriverAssignForm(SanitizedModelForm):
    """
    Form for assigning a driver to a delivery task.

    Only allows selecting the driver - task assignment is handled in the view.
    """
    class Meta:
        model = delivery_models.AssignedDriver
        fields = ['driver']
        # Exclude protected fields
        exclude = ['dl_task', 'created_at', 'updated_at']

    def __init__(self, *args, **kwargs):
        super(DriverAssignForm, self).__init__(*args, **kwargs)
        self.helper = FormHelper()


class TaskAssignmentRuleForm(SanitizedModelForm):
    """
    One Task Automation rule. Conditions left blank match any task; the driver is
    only required (and only kept) when the rule assigns to a driver.
    """
    class Meta:
        model = delivery_models.TaskAssignmentRule
        fields = ['name', 'priority', 'is_active', 'business', 'zone_group',
                  'task_leg', 'dl_speed', 'action', 'driver']

    def __init__(self, *args, **kwargs):
        from business.models import Business
        from fleet.models import Driver

        super().__init__(*args, **kwargs)
        self.fields['business'].queryset = Business.objects.filter(
            business_status='active').order_by('business_name')
        self.fields['zone_group'].queryset = delivery_models.ZoneGroup.objects.filter(
            is_active=True).order_by('display_order', 'name')

        # Only drivers who can open the app take rule work. A rule already pointing
        # at someone who has since lost access keeps them listed, so the edit form
        # shows the truth instead of silently swapping the driver.
        drivers = Driver.objects.filter(
            driver_status='approved', dashboard_access_enabled=True)
        if self.instance and self.instance.driver_id:
            drivers = drivers | Driver.objects.filter(pk=self.instance.driver_id)
        self.fields['driver'].queryset = drivers.select_related('user').order_by('driver_code')
        self.fields['driver'].label_from_instance = (
            lambda d: f"{d.driver_code or d.pk} — {d.user.get_full_name() or d.user.username}")

        self.fields['business'].empty_label = 'Any client'
        self.fields['zone_group'].empty_label = 'Any zone'
        self.fields['task_leg'].choices = [('', 'Any task type')] + list(
            delivery_models.DeliveryTask.TASK_LEG_CHOICES)
        self.fields['dl_speed'].choices = [('', 'Any speed')] + list(
            delivery_models.DeliveryTask.DL_SPEED_CHOICES)
        self.fields['driver'].empty_label = 'Choose a driver'

        self.fields['name'].widget.attrs['placeholder'] = 'e.g. Maven Abaya → Driver Ali'
        for name, field in self.fields.items():
            if name == 'is_active':
                field.widget.attrs['class'] = 'form-check-input'
            elif isinstance(field.widget, forms.Select):
                # Seven-odd app drivers and a dozen zone groups: a native select is
                # quicker here, and keeps every control in the row the same height.
                field.widget.attrs.update({'class': 'form-select tau__control', 'data-no-select2': ''})
            else:
                field.widget.attrs['class'] = 'form-control tau__control'

    def clean(self):
        cleaned = super().clean()
        action = cleaned.get('action')
        if action == delivery_models.TaskAssignmentRule.ACTION_DRIVER:
            if not cleaned.get('driver'):
                self.add_error('driver', 'Pick the driver this rule assigns to.')
        else:
            cleaned['driver'] = None
        return cleaned
