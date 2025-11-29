
from urllib import request
from django import forms
from django.contrib.auth.models import User

from crispy_forms.helper import FormHelper
from django.forms import ModelForm
from crispy_forms.layout import Layout, Field


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

    def clean_business_phone(self):
        """Validate phone number contains only digits"""
        phone = self.cleaned_data.get('business_phone')
        if phone:
            # Remove common separators and spaces
            cleaned_phone = phone.replace(' ', '').replace('-', '').replace('(', '').replace(')', '').replace('+', '')
            if not cleaned_phone.isdigit():
                raise forms.ValidationError("Phone number must contain only numbers (digits 0-9)")
            # Return cleaned version
            return cleaned_phone
        return phone

    def clean_business_whatsapp(self):
        """Validate WhatsApp number contains only digits"""
        whatsapp = self.cleaned_data.get('business_whatsapp')
        if whatsapp:
            # Remove common separators and spaces
            cleaned_whatsapp = whatsapp.replace(' ', '').replace('-', '').replace('(', '').replace(')', '').replace('+', '')
            if not cleaned_whatsapp.isdigit():
                raise forms.ValidationError("WhatsApp number must contain only numbers (digits 0-9)")
            # Return cleaned version
            return cleaned_whatsapp
        return whatsapp

    def clean_business_facebook_page(self):
        """Validate Facebook page contains only username (no slashes or spaces)"""
        facebook = self.cleaned_data.get('business_facebook_page')
        if facebook:
            # Remove leading/trailing whitespace
            facebook = facebook.strip()
            # Check for slashes or spaces
            if '/' in facebook or ' ' in facebook:
                raise forms.ValidationError("Enter username only, without slashes (/) or spaces")
            # Remove common URL prefixes if user added them
            facebook = facebook.replace('https://', '').replace('http://', '')
            facebook = facebook.replace('www.facebook.com/', '').replace('facebook.com/', '')
            facebook = facebook.replace('@', '')
            return facebook.strip()
        return facebook

    def clean_business_instagram(self):
        """Validate Instagram contains only username (no slashes or spaces)"""
        instagram = self.cleaned_data.get('business_instagram')
        if instagram:
            # Remove leading/trailing whitespace
            instagram = instagram.strip()
            # Check for slashes or spaces
            if '/' in instagram or ' ' in instagram:
                raise forms.ValidationError("Enter username only, without slashes (/) or spaces")
            # Remove common URL prefixes if user added them
            instagram = instagram.replace('https://', '').replace('http://', '')
            instagram = instagram.replace('www.instagram.com/', '').replace('instagram.com/', '')
            instagram = instagram.replace('@', '')
            return instagram.strip()
        return instagram

class businessApiSettingsForm(forms.ModelForm):
    class Meta:
        model = business_models.BusinessApiSettings
        fields = '__all__'
        exclude = ['is_verify_api']
        
        labels = {
            "api_type": "API Type",
            "api_key": "API Key",
            "api_secret": "API Secret",
            "site_api_url": "Site URL ( with https:// )",
            "order_api_endpoint": "Order API URL",
            "product_api_endpoint": "Product API URL",
        }



class BusinessProfileForm(forms.ModelForm):
    class Meta:
        model = business_models.BusinessProfile
        fields = '__all__'
        exclude = ['business', 'updated_at', 'created_at']

    def __init__(self, *args, **kwargs):
        super(BusinessProfileForm, self).__init__(*args, **kwargs)

        self.helper = FormHelper()
        self.helper.layout = Layout(
            Field('business_description', placeholder='Tell us about your business')
        )

        # Correct field labels
        labels = {
            "business_description": "Tell us about your business",
            "business_qid": "Passport/QID/CR No",
            "business_facebook_page": "Business Facebook page : Enter username only",
            "business_instagram": "Business Instagram : Enter username only",
            "business_tiktok": "Business Tiktok : Enter username only",
            "business_youtube": "Business Youtube : Enter your complete url",
        }

        for field_name, label in labels.items():
            if field_name in self.fields:
                self.fields[field_name].label = label

class BusinessLogoForm(forms.ModelForm):
        class Meta:
            model = business_models.BusinessLogo
            fields = '__all__'
            exclude = ['business', 'updated_at', 'created_at']
            




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

# business teams FORM ----------------------------------------------------------------------------------------------------------------------

class BusinessTeamProfileForm(forms.ModelForm):
    class Meta:
        model = business_models.BusinessTeamProfile
        fields = '__all__'
        exclude = ['business', 'updated_at', 'created_at', 'profile']
        widgets = {
            'user': forms.Select(
                choices=User.objects.all().values_list('username', 'username')),
            'user': forms.TextInput(attrs={'class': 'form-control p-3'}),
        }

        labels = {
            "team_name": "Team Name",
            "team_phone": "Team Phone No",
            "team_email": "Team Email",
            "team_role": "Team Role",
            'user' : 'Search member by username',
        }