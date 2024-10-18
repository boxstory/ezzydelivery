
from django import forms
from django.contrib.auth.models import User
from crispy_forms.helper import FormHelper
from django.contrib.admin import widgets
from django.forms import ModelForm
from core import models as core_models
from fleet import models as fleet_models
from client import models as business_models

# DRIVER FORM ---------------------------------------------------------------------------------------------------------------------


DRIVER_STATUS = (
    ('aproval pending', 'Aproval Pending'),
    ('active', 'Active'),
    ('inactive', 'Inactive'),
    ('Suspended', 'Suspended'),
    ('blacklisted', 'Black Listed'),
)


class DriverJoinForm(forms.ModelForm):
    class Meta:
        model = fleet_models.Driver
        fields = '__all__'
        exclude = ['user', 'driver_id', 'profile', 'driver_code', 'driver_status', 'driver_rating', 'driver_code_dms',
                   'driver_rating_count', 'driver_reviews', 'driver_reviews_count', 'updated_at', 'created_at', ]
        labels = {
                "driver_bio": "About Skill and Experiance",
            }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_show_labels = True
        

VEHICLE_CHOICES = [
    ('none', 'None'),
    ('bike', 'Bike'),
    ('car', 'Car'),
    ('van', 'Van'),
    ('pickup', 'Pickup'),
    ('pickup_big', 'Pickup Big'),
]


class DriverVehicleForm(forms.ModelForm):
    class Meta:
        model = fleet_models.DriverVehicle
        fields = '__all__'
        exclude = ['driver', 'vehicle_date',
                   'updated_at', 'created_at', 'driver_code_dms']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_show_labels = True
        self.fields['vehicle_type'].widget = forms.RadioSelect(
            choices=VEHICLE_CHOICES)
        self.fields['vehicle_type'].widget.attrs['class'] = 'input-block-level'


class DriverDocumentForm(forms.ModelForm):
    class Meta:
        model = fleet_models.DriverDocument
        fields = '__all__'
        exclude = ['driver', 'updated_at', 'created_at']
        widgets = {
            'document_expiry_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
        }
        

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_show_labels = True
        self.fields['document_issued_from'].initial = "Qatar"
