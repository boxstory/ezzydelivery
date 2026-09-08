"""
Purpose: Driver-facing forms — join application, vehicle registration, document upload.
Used by: fleet.views (driver onboarding), core.views.join_us_driver, workforce staff review pages.
Notes: Fields are an explicit allowlist, never '__all__'. A blocklist silently exposes every new
       model field the next migration adds, and this model carries wallet/COD/status columns.
"""
from django import forms
from crispy_forms.helper import FormHelper

from core import models as core_models
from core.forms_base import SanitizedModelForm
from core.validators import (
    DOCUMENT_EXTENSIONS, normalize_qatar_phone, validate_alphanumeric_ref,
    validate_upload_file,
)
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


class DriverJoinForm(SanitizedModelForm):
    """Driver's own application/profile fields.

    Deliberately omits every operational column a driver must not set for
    themselves: driver_status, wallet_balance, credit_limit, cod_in_hand,
    total_earnings, driver_meta (holds the staff-verified registration_location)
    and to_be_notified (an ops broadcast toggle).
    """

    sanitize_collapse_whitespace = ('driver_phone', 'driver_whatsapp',
                                    'driver_license_number')

    class Meta:
        model = fleet_models.Driver
        fields = [
            'driver_phone',
            'driver_whatsapp',
            'driver_languages',
            'has_driver_license',
            'driver_license_number',
            'driver_bio',
        ]
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

    def clean_driver_phone(self):
        return normalize_qatar_phone(
            self.cleaned_data.get('driver_phone'),
            field_label='Phone number',
            required=self.fields['driver_phone'].required,
        )

    def clean_driver_whatsapp(self):
        return normalize_qatar_phone(
            self.cleaned_data.get('driver_whatsapp'),
            field_label='WhatsApp number',
            required=self.fields['driver_whatsapp'].required,
        )

    def clean_driver_license_number(self):
        return validate_alphanumeric_ref(
            self.cleaned_data.get('driver_license_number'),
            field_label='Licence number', max_length=40, required=False,
        )

    def clean(self):
        cleaned_data = super().clean()
        # A licence number without the declaration is meaningless, and a
        # declaration without a number leaves staff nothing to verify.
        if cleaned_data.get('has_driver_license') and not cleaned_data.get('driver_license_number'):
            self.add_error(
                'driver_license_number',
                'Enter your licence number, or untick the licence declaration.',
            )
        return cleaned_data


VEHICLE_CHOICES = [
    ('none', 'None'),
    ('bike', 'Bike'),
    ('car', 'Car'),
    ('van', 'Van'),
    ('pickup', 'Pickup'),
    ('pickup_big', 'Pickup Big'),
]


class DriverVehicleForm(SanitizedModelForm):
    """Vehicle registration. vehicle_status and vehicle_photo stay staff-only."""

    sanitize_collapse_whitespace = ('vehicle_no', 'vehicle_model', 'vehicle_color')

    class Meta:
        model = fleet_models.DriverVehicle
        fields = [
            'vehicle_type',
            'vehicle_no',
            'vehicle_model',
            'vehicle_color',
        ]
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

    def clean_vehicle_no(self):
        value = validate_alphanumeric_ref(
            self.cleaned_data.get('vehicle_no'),
            field_label='Plate number', max_length=20,
            required=self.fields['vehicle_no'].required,
        )
        return value.upper()

    def clean_vehicle_model(self):
        return validate_alphanumeric_ref(
            self.cleaned_data.get('vehicle_model'),
            field_label='Vehicle model', max_length=60, required=False,
        )

    def clean_vehicle_color(self):
        return validate_alphanumeric_ref(
            self.cleaned_data.get('vehicle_color'),
            field_label='Vehicle colour', max_length=30, required=False, allow=' -',
        )


class DriverDocumentForm(SanitizedModelForm):
    """ID / licence scans. Both files go through the shared upload guard."""

    sanitize_collapse_whitespace = ('document_no', 'document_issued_from')

    class Meta:
        model = fleet_models.DriverDocument
        fields = [
            'document_type',
            'document_no',
            'document_issued_from',
            'document_expiry_date',
            'document_file',
            'document_file_back',
        ]
        widgets = {
            'document_expiry_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_show_labels = True
        self.fields['document_issued_from'].initial = "Qatar"

    def clean_document_no(self):
        return validate_alphanumeric_ref(
            self.cleaned_data.get('document_no'),
            field_label='Document number', max_length=40,
            required=self.fields['document_no'].required,
        )

    def clean_document_issued_from(self):
        return validate_alphanumeric_ref(
            self.cleaned_data.get('document_issued_from'),
            field_label='Issued from', max_length=60, required=False,
        )

    def clean_document_file(self):
        return validate_upload_file(
            self.cleaned_data.get('document_file'),
            DOCUMENT_EXTENSIONS, max_mb=8, field_label='Document scan',
        )

    def clean_document_file_back(self):
        return validate_upload_file(
            self.cleaned_data.get('document_file_back'),
            DOCUMENT_EXTENSIONS, max_mb=8, field_label='Document back scan',
        )
