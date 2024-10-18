from email.policy import default
from tabnanny import verbose
from django import forms
from crispy_forms.helper import FormHelper
from requests import request
from delivery import models as delivery_models


class DlAddressUpdateForm(forms.ModelForm):
    class Meta:
        model = delivery_models.DlAddressUpdate
        fields = '__all__'
        exclude = [' dl_pluscode ', ]
        widget = {
            'time_slot': forms.CheckboxSelectMultiple(choices=[
                ('Morning', 'Morning'),
                ('Afternoon', 'Afternoon'),
                ('Evening', 'Evening'),
                ('Night', 'Night'),
            ]),
        }

    def __init__(self, *args, **kwargs):
        super(DlAddressUpdateForm, self).__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.fields['dl_task_number'].widget = forms.HiddenInput()
        self.fields['mobile_no'].widget = forms.HiddenInput()
        self.fields['time_slot'].widget = forms.CheckboxSelectMultiple(choices=[
            ('Morning', 'Morning'),
            ('Afternoon', 'Afternoon'),
            ('Evening', 'Evening'),
            ('Night', 'Night'),
        ])
        self.fields['time_slot'].attrs = {'class': 'd-flex flex-wrap'}


class DriverAssignForm(forms.ModelForm):
    class Meta:
        model = delivery_models.AssignedDriver
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super(DriverAssignForm, self).__init__(*args, **kwargs)
        self.helper = FormHelper()
