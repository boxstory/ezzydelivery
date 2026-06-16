"""
Core Forms Module
=================

This module contains forms for user registration, profile management, and applications.

Forms:
    Authentication & Registration:
        - CustomSignupForm: Extended signup with first/last name

    Profile Management:
        - ProfileForm: Initial profile creation form
        - ProfileUpdateForm: Full profile editing form
        - ProfilePictureForm: Profile image upload form
        - JoinUsForm: Role selection form (business/driver)

    Applications:
        - DriverVacancyAplicationForm: Driver job application form

Form Validation:
    - Profile pictures are validated for size and type
    - Required fields enforced for profile completion
    - Date of birth range: 1930-2010

Usage:
    >>> from core.forms import ProfileForm
    >>> form = ProfileForm(request.POST, instance=profile)
    >>> if form.is_valid():
    ...     form.save()

Related:
    - core.models: Profile, ProfilePicture
    - core.views: profile_view, profile_add, join_us
"""

from urllib import request
from django import forms
from core import models as core_models
from allauth.account.forms import SignupForm
from crispy_forms.helper import FormHelper, Layout
from crispy_forms.bootstrap import InlineCheckboxes
from django_recaptcha.fields import ReCaptchaField
from django_recaptcha.widgets import ReCaptchaV2Checkbox

from webpages import models as webpages_models
from fleet import models as fleet_models

# Local aliases for commonly used models
Profile = core_models.Profile
ProfilePicture = core_models.ProfilePicture

YEARS = [i for i in range(1930, 2020)]


# =============================================================================
# AUTHENTICATION & REGISTRATION FORMS
# =============================================================================


class CustomSignupForm(SignupForm):
    """
    Extended signup form with first and last name fields and username validation.

    Extends django-allauth's SignupForm to capture user's full name
    during registration and validate username length (8-12 characters).
    The names are saved to the User model.

    Fields:
        first_name (CharField): User's first name (max 30 chars)
        last_name (CharField): User's last name (max 30 chars)
        captcha (ReCaptchaField): reCAPTCHA v2 checkbox for bot protection
        + inherited fields from SignupForm (email, password1, password2, username)

    Validation:
        - Username: 8-12 characters (required)
        - CAPTCHA: Verified server-side via Google's API

    Usage:
        Used automatically by django-allauth when configured in settings:
        ACCOUNT_FORMS = {'signup': 'core.forms.CustomSignupForm'}
    """
    first_name = forms.CharField(max_length=30, label='First Name', required=False)
    last_name = forms.CharField(max_length=30, label='Last Name', required=False)
    captcha = ReCaptchaField(widget=ReCaptchaV2Checkbox, required=True)

    def clean_username(self):
        """Validate username: 8-12 chars, only letters, numbers, and underscore."""
        import re
        username = self.cleaned_data.get('username', '').strip()

        # Check length
        if len(username) < 8:
            raise forms.ValidationError('Username must be at least 8 characters long.')
        if len(username) > 12:
            raise forms.ValidationError('Username cannot exceed 12 characters.')

        # Check allowed characters (letters, numbers, underscore only)
        if not re.match(r'^[a-zA-Z0-9_]+$', username):
            raise forms.ValidationError('Username can only contain letters, numbers, and underscore (_).')

        return super().clean_username()

    def signup(self, request, user):
        """Save first and last name to user model after signup."""
        user.first_name = self.cleaned_data.get('first_name', '')
        user.last_name = self.cleaned_data.get('last_name', '')

        user.save()
        return user


# =============================================================================
# PROFILE MANAGEMENT FORMS
# =============================================================================


class ProfileForm(forms.ModelForm):
    """
    Initial profile creation form.

    Used when users first complete their profile after registration.
    Collects essential contact and personal information.

    Fields:
        - first_name, last_name: User's full name
        - email: Contact email
        - phone, whatsapp: Contact numbers (required)
        - address, zone_name: Location info (zone_name required)
        - nationlity: User's nationality (required)
        - date_of_birth: DOB with date picker (required)
        - instagram: Social media handle (optional)

    Template:
        core/profile_add.html

    View:
        core.views.profile_add
    """
    class Meta:
        model = Profile
        fields = ['first_name', 'last_name', 'email', 'phone', 'address', 'instagram',
              'whatsapp', 'zone_name', 'nationlity', 'date_of_birth']
        widgets = {
            'first_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'First Name'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Last Name'}),
            'email': forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'Email'}),
            'phone': forms.HiddenInput(),
            'whatsapp': forms.HiddenInput(),
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

    def clean_phone(self):
        """Validate phone number format."""
        phone = self.cleaned_data.get('phone', '')
        if phone:
            # Remove spaces and special characters for validation
            phone_digits = ''.join(filter(str.isdigit, str(phone)))
            if len(phone_digits) < 7:
                raise forms.ValidationError('Phone number must contain at least 7 digits.')
            if len(phone_digits) > 15:
                raise forms.ValidationError('Phone number cannot exceed 15 digits.')
        return phone

    def clean_whatsapp(self):
        """Validate WhatsApp number format."""
        whatsapp = self.cleaned_data.get('whatsapp', '')
        if whatsapp:
            # Remove spaces and special characters for validation
            whatsapp_digits = ''.join(filter(str.isdigit, str(whatsapp)))
            if len(whatsapp_digits) < 7:
                raise forms.ValidationError('WhatsApp number must contain at least 7 digits.')
            if len(whatsapp_digits) > 15:
                raise forms.ValidationError('WhatsApp number cannot exceed 15 digits.')
        return whatsapp


class ProfileUpdateForm(forms.ModelForm):
    """
    Full profile editing form with all fields.

    Used for updating existing profiles. All fields except instagram
    are required to ensure profile completion for verification.

    Fields:
        - username: Unique display name
        - first_name, last_name: Full name
        - email: Contact email
        - phone, whatsapp: Contact numbers
        - zone_name, address: Location details
        - nationlity: User's nationality
        - date_of_birth: Date picker (range: 1930-2010)
        - instagram: Social handle (optional)

    Template:
        core/profile_view.html

    View:
        core.views.profile_view
    """
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
            if field_name not in ('instagram', 'address'):
                self.fields[field_name].required = True

    def clean_username(self):
        """Validate username: 8-12 chars, only letters, numbers, and underscore."""
        import re
        username = self.cleaned_data.get('username', '').strip()

        # Check length
        if len(username) < 8:
            raise forms.ValidationError('Username must be at least 8 characters long.')
        if len(username) > 12:
            raise forms.ValidationError('Username cannot exceed 12 characters.')

        # Check allowed characters (letters, numbers, underscore only)
        if not re.match(r'^[a-zA-Z0-9_]+$', username):
            raise forms.ValidationError('Username can only contain letters, numbers, and underscore (_).')

        return username

    def clean_phone(self):
        """Validate phone number format."""
        phone = self.cleaned_data.get('phone', '')
        if phone:
            # Remove spaces and special characters for validation
            phone_digits = ''.join(filter(str.isdigit, str(phone)))
            if len(phone_digits) < 7:
                raise forms.ValidationError('Phone number must contain at least 7 digits.')
            if len(phone_digits) > 15:
                raise forms.ValidationError('Phone number cannot exceed 15 digits.')
        return phone

    def clean_whatsapp(self):
        """Validate WhatsApp number format."""
        whatsapp = self.cleaned_data.get('whatsapp', '')
        if whatsapp:
            # Remove spaces and special characters for validation
            whatsapp_digits = ''.join(filter(str.isdigit, str(whatsapp)))
            if len(whatsapp_digits) < 7:
                raise forms.ValidationError('WhatsApp number must contain at least 7 digits.')
            if len(whatsapp_digits) > 15:
                raise forms.ValidationError('WhatsApp number cannot exceed 15 digits.')
        return whatsapp



class ProfilePictureForm(forms.ModelForm):
    """
    Profile picture upload form.

    Handles profile image uploads with validation for file size and type.
    Uses validate_image_upload() from core.views for validation.

    Fields:
        profile_picture (ImageField): The profile image file

    Validation:
        - File size limits
        - Allowed image types (JPEG, PNG, etc.)
        - Performed in clean_profile_picture()

    Template:
        Used within profile templates

    View:
        core.views.profile_view (handles image upload)
    """
    class Meta:
        model = ProfilePicture
        fields = ['profile_picture',]

    def clean_profile_picture(self):
        """Validate uploaded profile picture for size and type."""
        from core.views import validate_image_upload

        picture = self.cleaned_data.get('profile_picture')
        if picture:
            is_valid, error_msg = validate_image_upload(picture)
            if not is_valid:
                raise forms.ValidationError(error_msg)
        return picture


class JoinUsForm(forms.ModelForm):
    """
    Role selection form for new users.

    Allows users to select their role on the platform (business owner
    or delivery driver). Used during the onboarding process.

    Fields:
        id: Hidden field for profile ID
        is_business (BooleanField): Select to register as business
        is_driver (BooleanField): Select to register as driver

    Note:
        Users can only select one role. The form uses checkbox inputs
        styled as cards for better UX.

    Template:
        core/join_us.html

    View:
        core.views.join_us
    """
    class Meta:
        model = Profile
        fields = ['id', 'is_business', 'is_driver']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.helper = FormHelper()
        self.helper.form_show_labels = False


# =============================================================================
# APPLICATION FORMS
# =============================================================================


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
    """
    Driver job application form.

    Used by prospective drivers to apply for delivery positions.
    Collects personal info, location, and vehicle/license details.

    Fields:
        Personal Info:
            - full_name: Applicant's full name
            - mobile_no: Mobile contact number
            - whatsapp_no: WhatsApp number for communication

        Location:
            - landmark: Nearby landmark for reference
            - zone_name: Area/zone of residence
            - is_in_qatar: Whether applicant is currently in Qatar

        Vehicle & License:
            - licence: Type of driving license (2wheeler/4wheeler/heavy)
            - own_vehicle: Types of vehicles owned (multi-select)
            - job_type: Preferred job type (part_time/full_time/both)

    Template:
        core/join_us_driver.html

    View:
        core.views.join_us_driver

    Related Model:
        fleet.models.DriverVacancyAplication
    """
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
