"""
Delivery Forms Module
=====================

Forms for delivery address updates and driver assignments.
"""

from django import forms
from crispy_forms.helper import FormHelper
from delivery import models as delivery_models


class DlAddressUpdateForm(forms.ModelForm):
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


class DriverAssignForm(forms.ModelForm):
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
