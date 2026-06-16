from django import forms
from django.contrib.auth.models import User
from crispy_forms.helper import FormHelper
from django.contrib.admin import widgets
from django.forms import ModelForm
from core import models as core_models
from fleet import models as fleet_models
from business import models as business_models

# Local aliases for commonly used models
Driver = fleet_models.Driver
DriverVehicle = fleet_models.DriverVehicle
DriverDocument = fleet_models.DriverDocument
Profile = core_models.Profile
Business = business_models.Business

# DRIVER FORM ---------------------------------------------------------------------------------------------------------------------


DRIVER_STATUS = [
    ('pending', 'Pending'),
    ('processing', 'Processing'),
    ('approved', 'Approved'),
    ('rejected', 'Rejected'),
    ('blocked', 'Blocked'),
    ('suspended', 'Suspended'),
]


class DriverJoinForm(forms.ModelForm):
    class Meta:
        model = fleet_models.Driver
        fields = '__all__'
        exclude = ['user', 'driver_id', 'profile', 'driver_code', 'driver_status', 'driver_rating',
                   'driver_rating_count', 'driver_reviews', 'driver_reviews_count', 'updated_at', 'created_at',
                   'wallet_balance', 'credit_limit', 'cod_in_hand', 'total_earnings', 'pending_earnings',
                   'last_settlement_date', 'preferred_zone_groups', 'driver_availability', ]
        labels = {
                "driver_bio": "About Skills & Experience",
                "has_driver_license": "I have a valid driving license",
            }
        widgets = {
                "driver_bio": forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Write about your skills and experience...'}),
                "has_driver_license": forms.CheckboxInput(attrs={'class': 'form-check-input', 'role': 'switch'}),
                "driver_license_number": forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. 1234567'}),
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
        exclude = ['driver', 'vehicle_date', 'vehicle_status', 'vehicle_photo',
                   'updated_at', 'created_at']
        widgets = {
            'vehicle_no':    forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. 12345'}),
            'vehicle_model': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Toyota Hilux'}),
            'vehicle_color': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. White'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_show_labels = True
        self.fields['vehicle_type'].widget = forms.Select(
            choices=[('none', '— Select type —')] + VEHICLE_CHOICES)
        self.fields['vehicle_type'].widget.attrs['class'] = 'form-select'


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
