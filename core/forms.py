from urllib import request
from django import forms
from core.models import *
from allauth.account.forms import SignupForm
from crispy_forms.helper import FormHelper, Layout
from crispy_forms.bootstrap import InlineCheckboxes

from webpages import models as webpages_models
from fleet import models as fleet_models

YEARS = [i for i in range(1930, 2020)]


# SIGNUP FORM ---------------------------------------------------------------------------------------------------------------------

class CustomSignupForm(SignupForm):
    first_name = forms.CharField(max_length=30, label='First Name')
    last_name = forms.CharField(max_length=30, label='Last Name')

    def signup(self, request, user):
        user.first_name = self.cleaned_data['first_name']
        user.last_name = self.cleaned_data['last_name']

        user.save()
        return user


# PROFILE FORM ---------------------------------------------------------------------------------------------------------------------
class ProfileForm(forms.ModelForm):
    class Meta:
        model = Profile
        fields = ['first_name', 'last_name', 'email', 'phone', 'address', 'instagram',
              'whatsapp', 'zone_name', 'nationlity', 'date_of_birth']
        widgets = {
            'first_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'First Name'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Last Name'}),
            'email': forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'Email'}),
            'phone': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Phone Number'}),
            'whatsapp': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'WhatsApp Number'}),
            'zone_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Zone/Area Name'}),
            'address': forms.Textarea(attrs={'class': 'form-control', 'placeholder': 'Full Address', 'rows': 3}),
            'nationlity': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Nationality'}),
            'date_of_birth': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date',
                'placeholder': 'YYYY-MM-DD',
                'min': '1930-01-01',
                'max': '2010-12-31'
            }),
            'instagram': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '@username'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_show_labels = False
        # Set required fields
        self.fields['phone'].required = True
        self.fields['nationlity'].required = True
        self.fields['date_of_birth'].required = True
        self.fields['whatsapp'].required = True
        self.fields['zone_name'].required = True


class ProfileUpdateForm(forms.ModelForm):
    """Enhanced profile update form with all required fields"""
    class Meta:
        model = Profile
        fields = [
            'username', 'first_name', 'last_name', 'email',
            'phone', 'whatsapp', 'zone_name', 'address',
            'nationlity', 'date_of_birth', 'instagram'
        ]
        widgets = {
            'username': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Username'}),
            'first_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'First Name'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Last Name'}),
            'email': forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'Email'}),
            'phone': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Phone Number'}),
            'whatsapp': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'WhatsApp Number'}),
            'zone_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Zone Name'}),
            'address': forms.Textarea(attrs={'class': 'form-control', 'placeholder': 'Full Address', 'rows': 3}),
            'nationlity': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Nationality'}),
            'date_of_birth': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date',
                'placeholder': 'YYYY-MM-DD',
                'min': '1930-01-01',
                'max': '2010-12-31'
            }),
            'instagram': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Instagram Handle'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Make all fields required for profile completion except instagram
        for field_name in self.fields:
            if field_name != 'instagram':
                self.fields[field_name].required = True
        


class ProfilePictureForm(forms.ModelForm):
    class Meta:
        model = ProfilePicture
        fields = ['profile_picture',]

    def clean_profile_picture(self):
        """Validate uploaded profile picture"""
        from core.views import validate_image_upload

        picture = self.cleaned_data.get('profile_picture')
        if picture:
            is_valid, error_msg = validate_image_upload(picture)
            if not is_valid:
                raise forms.ValidationError(error_msg)
        return picture


class JoinUsForm(forms.ModelForm):
    class Meta:
        model = Profile
        fields = ['id', 'is_business', 'is_driver']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.helper = FormHelper()
        self.helper.form_show_labels = False


VEHICLE_CHOICES = [
    ('none', 'None'),
    ('bike', 'Bike'),
    ('car', 'Car'),
    ('van', 'Van'),
    ('pickup', 'Pickup'),
    ('pickup_big', 'Pickup Big'),

]

LICENCE_CHOICES = [
    ('none', 'None'),
    ('2wheeler', '2 Wheeler'),
    ('4wheeler', '4 Wheeler'),
    ('heavy', 'Heavy'),
]

JOB_TYPE_CHOICES = [
    ('part_time', 'Part Time'),
    ('full_time', 'Full Time'),
    ('both', 'Both'),
]


class DriverVacancyAplicationForm(forms.ModelForm):
    VEHICLE_CHOICES = [
        ('none', 'None'),
        ('bike', 'Bike'),
        ('car', 'Car'),
        ('van', 'Van'),
        ('pickup', 'Pickup'),
        ('pickup_big', 'Pickup Big'),

    ]

    class Meta:
        model = fleet_models.DriverVacancyAplication
        fields = ['full_name', 'mobile_no', 'whatsapp_no', 'landmark', 'zone_name',
                  'licence', 'is_in_qatar', 'own_vehicle', 'job_type']
        Layout(
            InlineCheckboxes('own_vehicle')
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()

        self.helper.form_show_labels = True
