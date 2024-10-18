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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_show_labels = False
        self.fields['date_of_birth'].widget = forms.SelectDateWidget(
            years=YEARS)
        self.fields['date_of_birth'].widget.attrs = {
            'class': 'form-control d-flex justify-content-center'}


class ProfilePictureForm(forms.ModelForm):
    class Meta:
        model = ProfilePicture
        fields = ['profile_picture',]


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
