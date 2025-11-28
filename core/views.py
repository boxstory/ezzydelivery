import logging
import os
import random
import secrets
import string
from datetime import datetime, timedelta
from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.core.files.storage import FileSystemStorage
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from PIL import Image

from client import forms as business_forms
from client import models as business_models
from core import forms as core_forms
from core import models as core_models
from fleet import forms as fleet_forms
from fleet import models as fleet_models

# Initialize logger
logger = logging.getLogger(__name__)

# Status Constants
VERIFICATION_STATUS_INCOMPLETE = 'incomplete'
VERIFICATION_STATUS_PENDING = 'pending'
VERIFICATION_STATUS_UNDER_REVIEW = 'under_review'
VERIFICATION_STATUS_VERIFIED = 'verified'
VERIFICATION_STATUS_REJECTED = 'rejected'

DRIVER_STATUS_PENDING = 'Pending on Review'
DRIVER_STATUS_ACTIVE = 'Active'
DRIVER_STATUS_APPROVAL_PENDING = 'Approval Pending'

BUSINESS_STATUS_PENDING = 'pending'

# File Upload Constants
MAX_UPLOAD_SIZE = 5 * 1024 * 1024  # 5MB
ALLOWED_IMAGE_TYPES = ['image/jpeg', 'image/jpg', 'image/png', 'image/webp']
ALLOWED_IMAGE_EXTENSIONS = ['.jpg', '.jpeg', '.png', '.webp']


# HELPER FUNCTIONS --------------------------------------------------------------------------------------------------------------

def calculate_completion_percentage(obj, required_fields):
    """Calculate completion percentage for any model with required fields"""
    completed = sum(1 for field in required_fields if getattr(obj, field, None))
    return int((completed / len(required_fields)) * 100)


def validate_image_upload(uploaded_file):
    """Validate uploaded image file"""
    # Check if it's an actual uploaded file (not an ImageFieldFile from database)
    if not hasattr(uploaded_file, 'content_type'):
        return False, "No file uploaded"

    # Check file size
    if uploaded_file.size > MAX_UPLOAD_SIZE:
        return False, "File size exceeds 5MB limit"

    # Check file extension
    file_ext = os.path.splitext(uploaded_file.name)[1].lower()
    if file_ext not in ALLOWED_IMAGE_EXTENSIONS:
        return False, f"File type not allowed. Use: {', '.join(ALLOWED_IMAGE_EXTENSIONS)}"

    # Check content type
    if uploaded_file.content_type not in ALLOWED_IMAGE_TYPES:
        return False, "Invalid image file type"

    return True, None


def generate_secure_id(min_value=100000, max_value=999999):
    """Generate cryptographically secure random ID"""
    return secrets.randbelow(max_value - min_value) + min_value


# VERIFICATION DECORATOR --------------------------------------------------------------------------------------------------------------

def verification_required(role=None):
    """
    Decorator to check if user is verified before allowing access to views.

    Args:
        role: 'business', 'driver', or None (for any verified user)

    Usage:
        @verification_required(role='business')
        def business_dashboard(request):
            ...
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            # First check if user is logged in
            if not request.user.is_authenticated:
                return redirect('/accounts/login/')

            # Check if profile exists
            try:
                profile = core_models.Profile.objects.get(user_id=request.user.id)
            except core_models.Profile.DoesNotExist:
                messages.error(request, "Please create your profile first.")
                return redirect('core:profile_add')

            # Staff users bypass verification
            if profile.is_staff:
                return view_func(request, *args, **kwargs)

            # Check role if specified
            if role == 'business' and not profile.is_business:
                messages.error(request, "This area is for business users only.")
                return redirect('core:main_dashboard')
            elif role == 'driver' and not profile.is_driver:
                messages.error(request, "This area is for drivers only.")
                return redirect('core:main_dashboard')

            # Check verification status
            if profile.verification_status != VERIFICATION_STATUS_VERIFIED:
                if profile.verification_status == VERIFICATION_STATUS_INCOMPLETE:
                    messages.warning(request, "Please complete your profile and apply for verification.")
                    return redirect('core:profile_complete_update')
                elif profile.verification_status in [VERIFICATION_STATUS_PENDING, VERIFICATION_STATUS_UNDER_REVIEW]:
                    messages.info(request, "Your application is pending verification. Please wait for approval.")
                    return render(request, 'core/verification_pending.html', {'profile': profile})
                elif profile.verification_status == VERIFICATION_STATUS_REJECTED:
                    rejection_msg = f"Your application was rejected"
                    if profile.rejection_reason:
                        rejection_msg += f": {profile.rejection_reason}"
                    rejection_msg += ". Please update and reapply."
                    messages.error(request, rejection_msg)
                    if profile.is_business:
                        return redirect('core:business_register')
                    elif profile.is_driver:
                        return redirect('core:driver_register')
                    return redirect('core:profile_complete_update')

            # User is verified, allow access
            return view_func(request, *args, **kwargs)

        return wrapper
    return decorator


# Create your views here.


# joins---------------------------------------------------------------------------------------------------------------------
@login_required(login_url='/accounts/login/')
def join_business(request):
    """Handle business registration process"""
    try:
        profile = core_models.Profile.objects.get(user_id=request.user.id)

        # Check if role already selected
        if profile.is_driver or profile.is_business:
            logger.info(f"User {request.user.id} already has role selected")
            return redirect('core:profile', pk=request.user.id)

        joinusform = core_forms.JoinUsForm(request.POST or None, instance=profile)

        if request.method == 'POST':
            form = business_forms.businessRegisterForm(request.POST)
            if form.is_valid():
                logger.info(f"Business form valid for user {request.user.id}")
                business = form.save(commit=False)
                business.profile = request.user.profile
                business.user_id = request.user.id
                business.business_id = generate_secure_id()
                business.save()

                profile_update = joinusform.save(commit=False)
                profile_update.user = request.user
                profile_update.is_driver = False
                profile_update.is_business = True
                profile_update.save()

                logger.info(f"Business registration completed for user {request.user.id}")
                messages.success(request, "Business registration completed successfully!")
                return redirect('core:profile_view')
            else:
                logger.warning(f"Invalid business form for user {request.user.id}")
                messages.error(request, "Please correct the errors below.")
    except core_models.Profile.DoesNotExist:
        logger.error(f"Profile does not exist for user {request.user.id}")
        messages.error(request, "Please create your profile first.")
        return redirect('core:profile_add')

    form = business_forms.businessRegisterForm()
    logger.debug("Loading business register form")
    context = {
        'form': form,
    }
    return render(request, 'core/join_us_business.html', context)


@login_required(login_url='/accounts/login/')
def join_driver(request):
    """Handle driver registration process"""
    try:
        profile = core_models.Profile.objects.get(user_id=request.user.id)

        # Check if role already selected
        if profile.is_driver or profile.is_business:
            logger.info(f"User {request.user.id} already has role selected")
            return redirect('core:profile', pk=request.user.id)

        joinusform = core_forms.JoinUsForm(request.POST or None, instance=profile)

        if request.method == 'POST':
            form = fleet_forms.DriverJoinForm(request.POST)
            if form.is_valid():
                logger.info(f"Driver form valid for user {request.user.id}")
                driver = form.save(commit=False)
                driver.profile = profile
                driver.driver_id = profile.id
                driver.driver_status = DRIVER_STATUS_APPROVAL_PENDING
                driver.driver_code = ''.join(random.choice(string.digits) for _ in range(6))
                driver.user_id = request.user.id
                driver.driver_rating = 0
                driver.driver_rating_count = 0
                driver.driver_reviews = 0
                driver.driver_reviews_count = 0
                driver.created_at = datetime.now()
                driver.save()

                profile_update = joinusform.save(commit=False)
                profile_update.user = request.user
                profile_update.is_driver = True
                profile_update.is_business = False
                profile_update.save()

                logger.info(f"Driver registration completed for user {request.user.id}")
                messages.success(request, "Driver registration completed successfully!")
                return redirect('core:profile_view')
            else:
                logger.warning(f"Invalid driver form for user {request.user.id}")
                messages.error(request, "Please correct the errors below.")

        form = fleet_forms.DriverJoinForm()
        driverjoinform = fleet_forms.DriverJoinForm()
        logger.debug(f"Loading driver join form for profile {profile.id}")
        context = {
            'form': form,
            'driverjoinform': driverjoinform,
            'profile': profile,
        }
        return render(request, 'core/join_us_driver.html', context)
    except core_models.Profile.DoesNotExist:
        logger.error(f"Profile does not exist for user {request.user.id}")
        messages.error(request, "Please create your profile first.")
        return redirect('core:profile_add')


@login_required(login_url='/accounts/login/')
def update_role(request):
    """Update user role information"""
    profile = get_object_or_404(core_models.Profile, user_id=request.user.id)
    logger.debug(f"Loading role update for profile {profile.id}")

    try:
        driver = fleet_models.Driver.objects.get(user_id=request.user.id)
    except fleet_models.Driver.DoesNotExist:
        driver = None
        logger.warning(f"No driver profile found for user {request.user.id}")

    joinusform = core_forms.JoinUsForm(request.POST or None, instance=profile)

    if request.method == 'POST':
        if joinusform.is_valid():
            logger.info(f"Role update valid for user {request.user.id}")
            profile_update = joinusform.save(commit=False)
            profile_update.user = request.user
            profile_update.save()
            messages.success(request, "Role updated successfully!")
            return redirect('core:profile', pk=request.user.id)
        else:
            logger.warning(f"Invalid role update form for user {request.user.id}")
            messages.error(request, "Please correct the errors below.")

    context = {
        'form': joinusform,
        'profile': profile,
        'driver': driver,
    }
    return render(request, 'core/prodile_role_update.html', context)


@login_required(login_url='/accounts/login/')
def update_driver(request):
    """Update driver profile information"""
    driver_profile = get_object_or_404(fleet_models.Driver, driver_id=request.user.id)
    profile = get_object_or_404(core_models.Profile, user_id=request.user.id)

    driverjoinform = fleet_forms.DriverJoinForm(request.POST or None, instance=driver_profile)

    if request.method == 'POST' and driverjoinform.is_valid():
        driverjoinform.save()
        logger.info(f"Driver profile updated for user {request.user.id}")
        messages.success(request, "Driver profile updated successfully!")
        return redirect('core:profile', pk=request.user.id)
    elif request.method == 'POST':
        logger.warning(f"Invalid driver update form for user {request.user.id}")
        messages.error(request, "Please correct the errors below.")

    context = {
        'driverjoinform': driverjoinform,
        'profile': profile,
    }
    return render(request, 'core/update_driver.html', context)


@login_required(login_url='/accounts/login/')
def business_profile_update(request):
    """Update business profile information"""
    try:
        business_profile = business_models.Business.objects.get(user_id=request.user.id)
    except business_models.Business.DoesNotExist:
        logger.error(f"Business profile not found for user {request.user.id}")
        messages.error(request, "Business profile not found. Please register as business first.")
        return redirect('core:join_business')

    form = business_forms.businessRegisterForm(request.POST or None, instance=business_profile)

    if request.method == 'POST' and form.is_valid():
        business = form.save(commit=False)
        business.user = request.user
        business.profile = request.user.profile
        business.save()
        logger.info(f"Business profile updated for user {request.user.id}")
        messages.success(request, 'Your business details have been updated!')
        return redirect('business:business_profile', business_id=request.user.id)
    elif request.method == 'POST':
        logger.warning(f"Invalid business update form for user {request.user.id}")
        messages.error(request, "Please correct the errors below.")

    context = {
        'form': form,
    }
    return render(request, 'client/frontend/business_profile_update.html', context)


@login_required(login_url='/accounts/login/')
def join_us(request):
    """Handle role selection (driver or business)"""
    if core_models.Profile.objects.filter(user_id=request.user.id).exists():
        profile = get_object_or_404(core_models.Profile, user_id=request.user.id)
        joinusform = core_forms.JoinUsForm(request.POST or None, instance=profile)
        driverjoinform = fleet_forms.DriverJoinForm()
        businessjoinform = business_forms.businessRegisterForm()

        if request.method == 'POST':
            if driverjoinform.is_valid():
                logger.info(f"Processing driver join for user {request.user.id}")
                profile_update = joinusform.save(commit=False)
                profile_update.user = request.user
                profile_update.is_driver = True
                profile_update.is_business = False
                profile_update.save()

                driver = driverjoinform.save(commit=False)
                driver.user = request.user
                driver.driver_id = request.user.id
                driver.driver_status = DRIVER_STATUS_ACTIVE
                driver.save()

                logger.info(f"Driver join completed for user {request.user.id}")
                messages.success(request, 'Your driver account has been created!')

            if businessjoinform.is_valid():
                logger.info(f"Processing business join for user {request.user.id}")
                profile_update = joinusform.save(commit=False)
                profile_update.user = request.user
                profile_update.is_driver = False
                profile_update.is_business = True
                profile_update.save()

                logger.info(f"Business join completed for user {request.user.id}")
                messages.success(request, 'Your business account has been created!')

            return redirect('core:profile', pk=request.user.id)
        else:
            logger.debug(f"Loading join us form for user {request.user.id}")

            # Get or create profile picture
            try:
                profile_picture = core_models.ProfilePicture.objects.get(user_id=request.user.id)
            except core_models.ProfilePicture.DoesNotExist:
                profile_picture = core_models.ProfilePicture.objects.create(
                    user_id=request.user.id,
                    profile_id=request.user.id
                )

            # Calculate completion percentage
            completion_percentage = profile.get_profile_completion_percentage()

            context = {
                'joinusform': joinusform,
                'driverjoinform': driverjoinform,
                'businessjoinform': businessjoinform,
                'profile': profile,
                'profile_picture': profile_picture,
                'completion_percentage': completion_percentage
            }
        return render(request, 'core/join_us.html', context)

    logger.warning(f"Profile does not exist for user {request.user.id}, redirecting to profile_add")
    messages.info(request, "Please create your profile first.")
    return redirect('core:profile_add')



@login_required(login_url='/accounts/login/')
def main_dashboard(request):
    """Main dashboard with verification status checking"""
    if core_models.Profile.objects.filter(user_id=request.user.id).exists():
        profile = core_models.Profile.objects.get(user_id=request.user.id)

        # Staff users don't need verification
        if profile.is_staff:
            return redirect('workforce:wf_dashboard')

        # Check if profile is completed
        if not profile.is_profile_completed:
            messages.warning(request, "Please complete your profile to access the dashboard.")
            return redirect('core:profile_complete_update')

        # Check verification status
        if profile.verification_status == VERIFICATION_STATUS_INCOMPLETE:
            if profile.is_business and not profile.is_business_profile_completed:
                messages.warning(request, "Please complete your business registration.")
                return redirect('core:business_register')
            elif profile.is_driver and not profile.is_driver_profile_completed:
                messages.warning(request, "Please complete your driver registration.")
                return redirect('core:driver_register')
            else:
                messages.warning(request, "Please complete your profile and role registration.")
                return redirect('core:profile_complete_update')

        elif profile.verification_status == VERIFICATION_STATUS_PENDING:
            messages.info(request, "Your application is pending verification. Please wait for staff approval.")
            return render(request, 'core/verification_pending.html', {'profile': profile})

        elif profile.verification_status == VERIFICATION_STATUS_UNDER_REVIEW:
            messages.info(request, "Your application is under review. We'll notify you once verified.")
            return render(request, 'core/verification_pending.html', {'profile': profile})

        elif profile.verification_status == VERIFICATION_STATUS_REJECTED:
            rejection_msg = f"Your application was rejected. Reason: {profile.rejection_reason or 'Not specified'}. Please update your information and reapply."
            messages.error(request, rejection_msg)
            logger.warning(f"Rejected user {request.user.id} accessing dashboard")
            if profile.is_business:
                return redirect('core:business_register')
            elif profile.is_driver:
                return redirect('core:driver_register')

        elif profile.verification_status == VERIFICATION_STATUS_VERIFIED:
            # Allow access to dashboard
            if profile.is_business:
                return redirect('business:business_dashboard')
            elif profile.is_driver:
                return redirect('fleet:fleet_dashboard')

        # Default fallback
        messages.warning(request, "Please complete your profile setup.")
        return redirect('core:profile_complete_update')
    else:
        messages.info(request, "Please create your profile to get started.")
        return redirect('core:profile_add')


# bckend profile  pages---------------------------------------------------------------------------------------------------------------------
@login_required(login_url='/accounts/login/')
def profile_view(request):
    """Redirect to user's profile page"""
    user_id = request.user.id
    if core_models.Profile.objects.filter(user_id=user_id).exists():
        logger.debug(f"Redirecting user {user_id} to profile")
        return redirect('core:profile', pk=user_id)
    else:
        logger.info(f"No profile found for user {user_id}, redirecting to profile_add")
        messages.info(request, "Please create your profile.")
        return redirect('core:profile_add')


@login_required(login_url='/accounts/login/')
def profile(request, pk):
    """Display user profile"""
    profile = get_object_or_404(core_models.Profile, user_id=request.user.id)

    try:
        profile_picture = core_models.ProfilePicture.objects.get(user=request.user.id)
    except core_models.ProfilePicture.DoesNotExist:
        # Create default profile picture
        profile_picture = core_models.ProfilePicture(
            user=request.user,
            profile_id=request.user.id,
            profile_picture='core/user/avatar.png'
        )
        profile_picture.save()
        logger.info(f"Created default profile picture for user {request.user.id}")

    # Calculate completion percentage
    completion_percentage = profile.get_profile_completion_percentage()

    context = {
        "profile": profile,
        "profile_picture": profile_picture,
        "completion_percentage": completion_percentage
    }

    return render(request, 'core/profile.html', context)


@login_required(login_url='/accounts/login/')
def profile_add(request):
    """Add new user profile"""
    if request.method == 'POST':
        profileaddform = core_forms.ProfileForm(request.POST, request.FILES)
        profileaddform.fields['first_name'].widget.attrs['value'] = request.user.first_name or None
        profileaddform.fields['last_name'].widget.attrs['value'] = request.user.last_name
        profileaddform.fields['email'].widget.attrs['value'] = request.user.email

        if profileaddform.is_valid():
            logger.info(f"Creating profile for user {request.user.id}")
            profile = profileaddform.save(commit=False)
            profile.user_id = request.user.id
            profile.save()
            logger.info(f"Profile created successfully for user {request.user.id}")
            messages.success(request, 'Your profile has been created!')
            return redirect('core:profile', pk=request.user.id)
        else:
            logger.warning(f"Invalid profile form for user {request.user.id}")
            messages.error(request, "Please correct the errors below.")
            context = {
                'profileaddform': profileaddform,
            }
            return render(request, 'core/profile_add.html', context)
    else:
        profileaddform = core_forms.ProfileForm()
        profileaddform.fields['first_name'].widget.attrs['value'] = request.user.first_name or None
        profileaddform.fields['last_name'].widget.attrs['value'] = request.user.last_name
        profileaddform.fields['email'].widget.attrs['value'] = request.user.email

        logger.debug(f"Loading profile add form for user {request.user.id}")
        context = {
            'profileaddform': profileaddform,
        }
        return render(request, 'core/profile_add.html', context)


@login_required(login_url='/accounts/login/')
def profile_update_redirect(request, pk):
    """Redirect old profile update URL to new profile complete update page"""
    logger.info(f"Redirecting user {pk} from old profile_update to profile_complete_update")
    return redirect('core:profile_complete_update')


@login_required(login_url='/accounts/login/')
def profile_delete(request, pk):
    """Delete user profile"""
    instance = get_object_or_404(core_models.Profile, user_id=pk)
    instance.delete()
    logger.warning(f"Profile deleted for user {pk}")
    messages.success(request, 'Your profile has been deleted!')
    return redirect('core:profile_add')


@login_required(login_url='/accounts/login/')
def profile_picture_update(request):
    """Update user profile picture with validation and image processing"""
    instance = get_object_or_404(core_models.ProfilePicture, user_id=request.user.id)
    profile = get_object_or_404(core_models.Profile, user_id=request.user.id)
    username = profile.username

    form = core_forms.ProfilePictureForm()

    if request.method == 'POST':
        form = core_forms.ProfilePictureForm(request.POST, request.FILES, instance=instance)

        if form.is_valid():
            # Validate uploaded file
            uploaded_file = request.FILES.get('profile_picture')
            if uploaded_file:
                is_valid, error_message = validate_image_upload(uploaded_file)
                if not is_valid:
                    messages.error(request, error_message)
                    logger.warning(f"Invalid image upload for user {request.user.id}: {error_message}")
                    return render(request, 'core/parts/profile_picture_update.html', {'form': form})

            try:
                profile_pic = form.save(commit=False)
                profile_pic.user_id = request.user.id
                profile_pic.profile_id = request.user.id
                profile_pic.path = f'core/user/{username}'
                profile_pic.save()

                logger.info(f"Profile picture uploaded for user {request.user.id}")

                # Process and resize image
                try:
                    original_image = Image.open(profile_pic.profile_picture.path)

                    # Create thumbnail (128x128)
                    outfile = os.path.splitext(profile_pic.profile_picture.path)[0] + ".thumbnail"
                    with Image.open(profile_pic.profile_picture.path) as im:
                        logger.debug(f"Processing image: {profile_pic.profile_picture.path}, {im.format}, {im.size}x{im.mode}")
                        im.thumbnail((128, 128))
                        im.save(outfile, "JPEG")

                    # Create small version (200x200)
                    title, ext = os.path.splitext(profile_pic.profile_picture.path)
                    final_filepath = os.path.join(profile_pic.path, title + '_sm' + ext)
                    img = original_image.resize((200, 200), Image.Resampling.LANCZOS)
                    img.save(final_filepath)

                    logger.info(f"Profile picture processed successfully for user {request.user.id}")
                    messages.success(request, "Profile picture updated successfully!")
                except Exception as e:
                    logger.error(f"Error processing image for user {request.user.id}: {str(e)}")
                    messages.warning(request, "Profile picture uploaded but image processing had issues.")

                return redirect("core:profile_complete_update")
            except Exception as e:
                logger.error(f"Error saving profile picture for user {request.user.id}: {str(e)}")
                messages.error(request, "An error occurred while saving the profile picture.")
        else:
            logger.warning(f"Invalid profile picture form for user {request.user.id}")
            messages.error(request, "Please correct the errors below.")

    context = {
        'form': form,
    }
    return render(request, 'core/parts/profile_picture_update.html', context)


# profile_completion_test ---------------------------------------------------------------------------------------------------------------------
@login_required(login_url='/accounts/login/')
def profile_completion_test(request, pk):
    """Test profile completion status (for development/testing)"""
    profile = get_object_or_404(core_models.Profile, user_id=pk)
    logger.debug(f"Profile completion test for user {pk}")

    context = {
        'profile': profile,
    }
    return render(request, 'core/profile_completion_test.html', context)


# driverjob ---------------------------------------------------------------------------------------------------------------------


@login_required(login_url='/accounts/login/')
def driverjobform(request):
    """Handle driver job vacancy application"""
    if request.method == 'POST':
        driverjobform = core_forms.DriverVacancyAplicationForm(request.POST)
        if driverjobform.is_valid():
            application = driverjobform.save(commit=False)
            application.user_id = request.user.id
            application.save()
            logger.info(f"Driver job application submitted by user {request.user.id}")
            messages.success(request, "Your application has been submitted successfully!")
            return redirect('/')
        else:
            logger.warning(f"Invalid driver job application for user {request.user.id}")
            messages.error(request, "Please correct the errors below.")
    else:
        driverjobform = core_forms.DriverVacancyAplicationForm()

    return render(request, 'core/driverjobform.html', {'driverjobform': driverjobform})


# NEW PROFILE VERIFICATION WORKFLOW --------------------------------------------------------------------------------------------------------------

@login_required(login_url='/accounts/login/')
def profile_complete_update(request):
    """Profile update with completion tracking and partial saves"""
    try:
        profile = core_models.Profile.objects.get(user_id=request.user.id)
    except core_models.Profile.DoesNotExist:
        messages.error(request, "Please create a profile first!")
        return redirect('core:profile_add')

    # Ensure profile username matches Django User username
    if profile.username != request.user.username:
        profile.username = request.user.username
        profile.save()

    if request.method == 'POST':
        form = core_forms.ProfileUpdateForm(request.POST, instance=profile)
        # Auto-populate username from logged-in user and disable it
        form.fields['username'].initial = request.user.username
        form.fields['username'].widget.attrs['readonly'] = True
        form.fields['username'].disabled = True

        # Check which button was clicked
        action = request.POST.get('action')

        if form.is_valid():
            profile = form.save(commit=False)
            # Ensure username stays the same as the Django User account username
            profile.username = request.user.username

            # Check if profile is complete
            completion_percentage = profile.get_profile_completion_percentage()

            if action == 'save':
                # Partial save
                profile.save()
                messages.success(request, f"Profile saved successfully! ({completion_percentage}% complete)")
                return redirect('core:profile_complete_update')

            elif action == 'register_business' or action == 'join_driver':
                # Check if profile is 100% complete
                if completion_percentage == 100:
                    profile.is_profile_completed = True

                    if action == 'register_business':
                        profile.is_business = True
                        profile.is_driver = False
                    else:  # join_driver
                        profile.is_driver = True
                        profile.is_business = False

                    profile.save()
                    messages.success(request, "Profile completed! Please complete your registration form.")

                    if action == 'register_business':
                        return redirect('core:business_register')
                    else:
                        return redirect('core:driver_register')
                else:
                    messages.error(request, f"Please complete all profile fields before proceeding. ({completion_percentage}% complete)")
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = core_forms.ProfileUpdateForm(instance=profile)
        # Auto-populate username from logged-in user and disable it
        form.fields['username'].initial = request.user.username
        form.fields['username'].widget.attrs['readonly'] = True
        form.fields['username'].disabled = True

    completion_percentage = profile.get_profile_completion_percentage()

    context = {
        'form': form,
        'profile': profile,
        'completion_percentage': completion_percentage,
    }
    return render(request, 'core/profile_complete_update.html', context)


@login_required(login_url='/accounts/login/')
def business_register(request):
    """Business registration with completion tracking"""
    try:
        profile = core_models.Profile.objects.get(user_id=request.user.id)
    except core_models.Profile.DoesNotExist:
        messages.error(request, "Please complete your profile first!")
        return redirect('core:profile_complete_update')

    # Check if profile is completed
    if not profile.is_profile_completed:
        messages.error(request, "Please complete your profile before registering a business!")
        return redirect('core:profile_complete_update')

    # Check if user is set as business
    if not profile.is_business:
        messages.error(request, "Please select business role in your profile first!")
        return redirect('core:profile_complete_update')

    # Check if business already exists
    try:
        business = business_models.Business.objects.get(user_id=request.user.id)
        # Business exists, update it
        is_update = True
    except business_models.Business.DoesNotExist:
        business = None
        is_update = False

    if request.method == 'POST':
        form = business_forms.businessRegisterForm(request.POST, instance=business)
        action = request.POST.get('action')

        if form.is_valid():
            business = form.save(commit=False)
            business.user = request.user
            business.profile = profile

            if not is_update:
                business.business_id = generate_secure_id()
                business.business_status = BUSINESS_STATUS_PENDING
                logger.info(f"New business registration for user {request.user.id}")

            business.save()

            # Calculate completion percentage
            required_fields = ['business_name', 'business_phone', 'business_whatsapp',
                             'business_email', 'business_product_category', 'business_qid']
            completion_percentage = calculate_completion_percentage(business, required_fields)

            if action == 'save':
                messages.success(request, f"Business information saved! ({completion_percentage}% complete)")
                logger.info(f"Business info saved for user {request.user.id}: {completion_percentage}% complete")
                return redirect('core:business_register')

            elif action == 'apply_verification':
                if completion_percentage == 100:
                    profile.is_business_profile_completed = True
                    profile.verification_status = VERIFICATION_STATUS_PENDING
                    profile.verification_applied_at = datetime.now()
                    profile.save()
                    logger.info(f"Business verification applied for user {request.user.id}")
                    messages.success(request, "Application submitted for verification! Our team will review it soon.")
                    return redirect('core:profile_view')
                else:
                    logger.warning(f"Incomplete business profile for user {request.user.id}: {completion_percentage}%")
                    messages.error(request, f"Please complete all required fields. ({completion_percentage}% complete)")
        else:
            logger.warning(f"Invalid business form for user {request.user.id}")
            messages.error(request, "Please correct the errors below.")
    else:
        form = business_forms.businessRegisterForm(instance=business)

    # Calculate completion
    if business:
        required_fields = ['business_name', 'business_phone', 'business_whatsapp',
                         'business_email', 'business_product_category', 'business_qid']
        completion_percentage = calculate_completion_percentage(business, required_fields)
    else:
        completion_percentage = 0

    can_apply = profile.can_apply_for_verification()

    context = {
        'form': form,
        'profile': profile,
        'completion_percentage': completion_percentage,
        'can_apply': can_apply,
        'is_update': is_update,
    }
    return render(request, 'core/business_register.html', context)


@login_required(login_url='/accounts/login/')
def driver_register(request):
    """Driver registration with completion tracking"""
    try:
        profile = core_models.Profile.objects.get(user_id=request.user.id)
    except core_models.Profile.DoesNotExist:
        messages.error(request, "Please complete your profile first!")
        return redirect('core:profile_complete_update')

    # Check if profile is completed
    if not profile.is_profile_completed:
        messages.error(request, "Please complete your profile before joining as a driver!")
        return redirect('core:profile_complete_update')

    # Check if user is set as driver
    if not profile.is_driver:
        messages.error(request, "Please select driver role in your profile first!")
        return redirect('core:profile_complete_update')

    # Check if driver profile already exists
    try:
        driver = fleet_models.Driver.objects.get(user_id=request.user.id)
        is_update = True
    except fleet_models.Driver.DoesNotExist:
        driver = None
        is_update = False

    if request.method == 'POST':
        form = fleet_forms.DriverJoinForm(request.POST, instance=driver)
        action = request.POST.get('action')

        if form.is_valid():
            driver = form.save(commit=False)
            driver.user = request.user
            driver.profile = profile

            if not is_update:
                driver.driver_id = profile.id
                driver.driver_status = DRIVER_STATUS_PENDING
                driver.driver_code = ''.join(random.choice(string.digits) for _ in range(6))
                driver.driver_rating = 0
                driver.driver_rating_count = 0
                driver.driver_reviews_count = 0
                logger.info(f"New driver registration for user {request.user.id}")

            driver.save()

            # Calculate completion
            required_fields = ['driver_phone', 'driver_whatsapp', 'driver_languages',
                             'driver_license_number', 'driver_bio']
            completion_percentage = calculate_completion_percentage(driver, required_fields)

            if action == 'save':
                messages.success(request, f"Driver information saved! ({completion_percentage}% complete)")
                logger.info(f"Driver info saved for user {request.user.id}: {completion_percentage}% complete")
                return redirect('core:driver_register')

            elif action == 'apply_verification':
                if completion_percentage == 100:
                    profile.is_driver_profile_completed = True
                    profile.verification_status = VERIFICATION_STATUS_PENDING
                    profile.verification_applied_at = datetime.now()
                    profile.save()
                    logger.info(f"Driver verification applied for user {request.user.id}")
                    messages.success(request, "Application submitted for verification! Our team will review it soon.")
                    return redirect('core:profile_view')
                else:
                    logger.warning(f"Incomplete driver profile for user {request.user.id}: {completion_percentage}%")
                    messages.error(request, f"Please complete all required fields. ({completion_percentage}% complete)")
        else:
            logger.warning(f"Invalid driver form for user {request.user.id}")
            messages.error(request, "Please correct the errors below.")
    else:
        form = fleet_forms.DriverJoinForm(instance=driver)

    # Calculate completion
    if driver:
        required_fields = ['driver_phone', 'driver_whatsapp', 'driver_languages',
                         'driver_license_number', 'driver_bio']
        completion_percentage = calculate_completion_percentage(driver, required_fields)
    else:
        completion_percentage = 0

    can_apply = profile.can_apply_for_verification()

    context = {
        'form': form,
        'profile': profile,
        'completion_percentage': completion_percentage,
        'can_apply': can_apply,
        'is_update': is_update,
    }
    return render(request, 'core/driver_register.html', context)
