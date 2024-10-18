
from django import forms
from django.contrib.auth.models import User
from crispy_forms.helper import FormHelper
from django.forms import ModelForm
from core import models as core_models
from fleet import models as fleet_models
from client import models as business_models


# BUSINESS FORM ---------------------------------------------------------------------------------------------------------------------


business_LANGUAGE_CHOICES = (
    ('arabic', 'Arabic'),
    ('english', 'English'),
    ('hindi', 'Hindi'),
    ('philipine', 'Philipine'),
    ('other', 'Other'),
)
business_STATUS_CHOICES = (
    ('aproval pending', 'Aproval Pending'),
    ('active', 'Active'),
    ('inactive', 'Inactive'),
)

# business FORM ---------------------------------------------------------------------------------------------------------------------


class businessRegisterForm(forms.ModelForm):
    class Meta:
        model = business_models.Business
        fields = '__all__'
        
        exclude = ['profile', 'business_id', 'user',
                   'business_status', 'business_code', 'updated_at', 'created_at']
        widgets = {
            'business_name': forms.TextInput(attrs={'class': 'form-control'}),
            'business_languages': forms.Select(
                choices=business_LANGUAGE_CHOICES),
            'business_status': forms.Select(
                choices=business_STATUS_CHOICES),
            'business_since' : forms.TextInput(attrs={'type': 'date'}),
            

        }
        labels = {
            "business_name": "business Name",
            "business_phone": "business Phone No",
            "business_whatsapp": "business Whatsapp No",
            "business_qid": "Passport/QID/CR No",

        }

 # PICKUP LOCATIONS FORM ----------------------------------------------------------------------------------------------------------------------


class PickupLocationsAddForm(forms.ModelForm):
    class Meta:
        model = business_models.PickupLocation
        fields = '__all__'
        exclude = ['business', 'updated_at', 'created_at']


class DriverDirectoryAddForm(forms.ModelForm):
    class Meta:
        model = business_models.DriverDirectory
        fields = '__all__'
        exclude = ['business', 'updated_at', 'created_at']

class BusinessLogoForm(forms.ModelForm):
    class Meta:
        model = business_models.BusinessLogo
        fields = '__all__'
        exclude = ['business', 'updated_at', 'created_at']
