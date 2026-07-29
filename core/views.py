"""
Core Views Module
=================

This module handles user profile management, registration flows, and verification
processes for the EzzyDelivery platform.

View Categories:
    1. Profile Views:
        - profile_view: Display user profile
        - profile_add: Create/complete user profile
        - profile_role_update: Update user roles (business/driver)
        - profile_complete_update: Complete profile information

    2. Registration Views:
        - join_us: Role selection page
        - join_us_business: Business registration flow
        - join_us_driver: Driver registration flow
        - business_register: Business account creation
        - driver_register: Driver account creation

    3. Verification Views:
        - verification_pending: Pending verification status page

    4. Password Reset Views:
        - password_reset_request: Request password reset via WhatsApp
        - password_reset_verify: Verify OTP code
        - password_reset_confirm: Set new password

Helper Functions:
    - calculate_completion_percentage: Calculate profile completion %
    - validate_image_upload: Validate uploaded images
    - generate_secure_id: Generate cryptographically secure IDs

Constants:
    - VERIFICATION_STATUS_*: Profile verification states
    - DRIVER_STATUS_*: Driver account states
    - MAX_UPLOAD_SIZE: Maximum file upload size (5MB)
    - ALLOWED_IMAGE_TYPES: Permitted image MIME types
"""

import logging
import os
import random
import secrets
import string
from datetime import datetime, timedelta
from django.utils import timezone as dj_timezone
from functools import wraps

from allauth.account.views import SignupView
from django_ratelimit.decorators import ratelimit
from django.utils.decorators import method_decorator
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.core.files.storage import FileSystemStorage
from django.db.models import Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_POST
from django.urls import reverse, reverse_lazy
from PIL import Image

from business import forms as business_forms
from business import models as business_models
from core import forms as core_forms
from core import models as core_models
from core.context_processors import get_cached_profile, get_cached_business
from fleet import forms as fleet_forms
from fleet import models as fleet_models

# Local aliases for commonly used models
Profile = core_models.Profile
ProfilePicture = core_models.ProfilePicture
Business = business_models.Business
Driver = fleet_models.Driver

# Initialize logger
logger = logging.getLogger(__name__)

# ── Profile URL helper ──────────────────────────────────────────────────────
def _get_user_number(user_id):
    """Return the user_number for a given user_id, used for profile URL redirects."""
    profile = core_models.Profile.objects.filter(user_id=user_id).values_list('user_number', flat=True).first()
    return profile  # may be None if profile doesn't exist yet


# Status Constants
VERIFICATION_STATUS_INCOMPLETE = 'incomplete'
VERIFICATION_STATUS_PENDING = 'pending'
VERIFICATION_STATUS_UNDER_REVIEW = 'under_review'
VERIFICATION_STATUS_VERIFIED = 'verified'
VERIFICATION_STATUS_REJECTED = 'rejected'


def validate_whatsapp_number(whatsapp_number):
    """
    Validate if a WhatsApp number is valid (any country).
    Requires at least 10 digits total (E.164 format).

    Args:
        whatsapp_number (str): The WhatsApp number to validate

    Returns:
        tuple: (is_valid: bool, message: str)
    """
    if not whatsapp_number:
        return False, 'WhatsApp number is required'

    # Remove any non-digit characters (handles +, spaces, dashes, etc.)
    digits_only = ''.join(filter(str.isdigit, str(whatsapp_number)))

    # Minimum 10 digits required (E.164 standard: country code + local number)
    # Examples:
    # - Qatar: 97433123456 (974 + 8 digits)
    # - USA: 12025551234 (1 + 10 digits)
    # - Pakistan: 923001234567 (92 + 10 digits)
    if len(digits_only) < 10:
        return False, f'WhatsApp number must be at least 10 digits. You provided {len(digits_only)} digits'

    # Maximum 15 digits (E.164 international standard limit)
    if len(digits_only) > 15:
        return False, f'WhatsApp number cannot exceed 15 digits. You provided {len(digits_only)} digits'

    # TODO: Integrate with WhatsApp API to verify actual account existence
    # - Twilio WhatsApp API: Check if number is registered
    # - WhatsApp Business API: Verify account status
    # - Third-party validation service

    return True, 'WhatsApp number is valid'

DRIVER_STATUS_PENDING = 'pending'
DRIVER_STATUS_APPROVED = 'approved'
DRIVER_STATUS_PROCESSING = 'processing'

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


def calculate_business_completion(business):
    """Business registration completion: 6 core fields + at least 2 marketplace fields = 7 items."""
    CORE = ['business_name', 'business_phone', 'business_whatsapp',
            'business_email', 'business_product_category', 'business_qid']
    MARKETPLACE = ['business_website', 'business_facebook_page',
                   'business_instagram', 'business_tiktok']
    core_done = sum(1 for f in CORE if getattr(business, f, None))
    marketplace_done = 1 if sum(1 for f in MARKETPLACE if getattr(business, f, None)) >= 2 else 0
    return int(((core_done + marketplace_done) / 7) * 100)


def calculate_driver_completion(driver):
    """Completion % for driver registration including vehicle type, model, and documents."""
    DRIVER_FIELDS = ['driver_phone', 'driver_whatsapp', 'driver_languages', 'driver_bio', 'has_driver_license']
    TOTAL = len(DRIVER_FIELDS) + 3  # +2 vehicle, +1 documents (min 2 required)
    completed = sum(1 for f in DRIVER_FIELDS if getattr(driver, f, None))
    vehicle = driver.driver_vehicle.filter(vehicle_type__isnull=False).exclude(vehicle_type='none').first()
    if vehicle:
        completed += 1
        if vehicle.vehicle_model:
            completed += 1
    doc_count = driver.driver_document.filter(document_file__isnull=False).exclude(document_file='').count()
    if doc_count >= 2:
        completed += 1
    return int((completed / TOTAL) * 100)


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

            # Check if profile exists (use cached profile)
            profile = get_cached_profile(request)
            if not profile:
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
        profile = get_cached_profile(request)
        if not profile:
            raise core_models.Profile.DoesNotExist()

        # If already a driver, they can't switch to business from here
        if profile.is_driver:
            logger.info(f"User {request.user.id} is already a driver, redirecting to profile")
            return redirect('core:profile', user_number=_get_user_number(request.user.id))

        # If already marked as business, forward to business_register to finish the form.
        # profile_complete_update sets is_business=True before redirecting here; hitting
        # the back button and trying again should not dead-end the user on their profile.
        if profile.is_business:
            logger.info(f"User {request.user.id} already has business role, forwarding to business_register")
            return redirect('core:business_register')

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
        else:
            form = business_forms.businessRegisterForm()

        logger.debug("Loading business register form")

        # Get profile picture for sidebar
        try:
            profile_picture = core_models.ProfilePicture.objects.get(user_id=request.user.id)
        except core_models.ProfilePicture.DoesNotExist:
            profile_picture = core_models.ProfilePicture.objects.create(
                user=request.user, profile=profile
            )

        context = {
            'form': form,
            'profile': profile,
            'profile_picture': profile_picture,
            'completion_percentage': profile.get_profile_completion_percentage(),
        }
        return render(request, 'core/join_us_business.html', context)

    except core_models.Profile.DoesNotExist:
        logger.info(f"Profile does not exist yet for user {request.user.id} (normal onboarding path)")
        messages.error(request, "Please create your profile first.")
        return redirect('core:profile_add')


def join_driver_start(request):
    """Public onboarding intro — how to become a driver in 4 steps, with a join button.

    Anonymous visitors get a 'Join with Google' button (sign-in returns to the
    application form); logged-in users get a direct link to the form.
    """
    from core.seo import SEOMetadata
    meta = SEOMetadata.get_page_meta(
        title="Delivery Driver Jobs in Qatar",
        description=(
            "Delivery driver jobs in Qatar with EzzyDelivery. Earn per delivery, "
            "choose your own hours, drive your own car or bike in Doha. Apply "
            "online in 5 minutes."
        ),
        url=f"{SEOMetadata.SITE_URL}/join_us/driver/start/",
    )
    context = {
        'seo': meta,
        # JobPosting schema: rolling 60-day validity window, refreshed on every render
        'job_valid_through': (dj_timezone.now() + timedelta(days=60)).strftime('%Y-%m-%d'),
    }
    return render(request, 'core/join_driver_start.html', context)


def join_driver_start_ar(request):
    """Arabic RTL mirror of join_driver_start — hreflang pair targeting 'وظائف سائق توصيل قطر'."""
    from core.seo import SEOMetadata
    meta = SEOMetadata.get_page_meta(
        title="وظائف سائق توصيل في قطر | انضم إلى أسطول Ezzy Delivery",
        description=(
            "وظائف سائق توصيل في قطر مع Ezzy Delivery. أجر مقابل كل توصيلة، "
            "ساعات مرنة، اعمل بسيارتك أو دراجتك في الدوحة. قدّم عبر الإنترنت خلال 5 دقائق."
        ),
        url=f"{SEOMetadata.SITE_URL}/ar/join_us/driver/start/",
    )
    context = {
        'seo': meta,
        'job_valid_through': (dj_timezone.now() + timedelta(days=60)).strftime('%Y-%m-%d'),
    }
    return render(request, 'core/join_driver_start_ar.html', context)


def join_driver(request):
    """Public driver application — Google sign-in, then 3 sections: profile, vehicle, documents.

    Anonymous visitors see the form with a Google login popup (One Tap +
    explicit button). After login the form is prefilled from the Google
    account / existing profile. Browser geolocation is captured on submit
    and stored in driver_meta['registration_location'].
    """
    from delivery.models import ZoneGroup

    APPLY_DOC_TYPES = ['Selfie', 'QID', 'Passport', 'Driving License', 'Istimara']
    ID_DOC_TYPES = [d for d in APPLY_DOC_TYPES if d != 'Selfie']

    zone_groups = list(
        ZoneGroup.objects.filter(is_active=True).order_by('display_order', 'name')
    )
    valid_zone_ids = {str(zg.id) for zg in zone_groups}

    profile = None
    driver = None
    primary_vehicle = None

    already_business = False
    is_verified_driver = False

    if request.user.is_authenticated:
        profile, _ = core_models.Profile.objects.get_or_create(user=request.user)
        if profile.is_staff:
            messages.warning(request, "Staff accounts cannot apply as drivers.")
            return redirect('workforce:wf_dashboard')
        already_business = profile.is_business
        driver = fleet_models.Driver.objects.filter(user_id=request.user.id).first()
        if driver:
            primary_vehicle = driver.driver_vehicle.first()
        is_verified_driver = bool(
            driver and profile.is_driver and profile.verification_status == 'verified'
        )

    upload_errors = []

    if request.method == 'POST':
        if not request.user.is_authenticated:
            messages.error(request, "Please sign in with Google to submit your application.")
            return redirect('core:join_driver')
        if already_business:
            messages.warning(request, "You are already registered as a business. One account cannot be both business and driver.")
            return redirect('core:join_driver')
        if is_verified_driver:
            messages.info(request, "Your driver account is already verified — application editing is closed.")
            return redirect('core:join_driver')

        is_partial_save = request.POST.get('action') == 'save'

        pform = core_forms.DriverApplyProfileForm(request.POST, instance=profile)
        if is_partial_save:
            # Save-progress accepts incomplete sections
            for field in pform.fields.values():
                field.required = False
        vform = fleet_forms.DriverVehicleForm(request.POST, prefix='veh', instance=primary_vehicle)

        existing_types = set()
        if driver:
            existing_types = set(
                driver.driver_document.filter(document_type__in=APPLY_DOC_TYPES)
                .exclude(document_file='').exclude(document_file__isnull=True)
                .values_list('document_type', flat=True)
            )
        uploaded = {}
        for doc_type in APPLY_DOC_TYPES:
            f = request.FILES.get(f'doc_{doc_type.replace(" ", "_")}')
            if f:
                ok, err = validate_image_upload(f)
                if ok:
                    uploaded[doc_type] = f
                else:
                    upload_errors.append(f"{doc_type}: {err}")

        veh_type = request.POST.get('veh-vehicle_type', '')
        vehicle_selected = bool(veh_type) and veh_type != 'none'

        selected_zone_ids = [z for z in request.POST.getlist('zone_groups') if z in valid_zone_ids]

        # Work preference comes as checkboxes: both ticked = flexible/both
        job_opts = {v for v in request.POST.getlist('job_type_opts') if v in ('full_time', 'part_time')}
        if job_opts == {'full_time', 'part_time'}:
            job_type_val = 'flexible'
        elif job_opts:
            job_type_val = next(iter(job_opts))
        else:
            job_type_val = (request.POST.get('job_type') or '').strip()

        # Minimum requirements enforced only on final submission:
        # selfie + at least 2 ID documents + a vehicle type
        if not is_partial_save:
            if 'Selfie' not in uploaded and 'Selfie' not in existing_types:
                upload_errors.append("A selfie photo is required.")
            id_docs_count = len({t for t in ID_DOC_TYPES if t in uploaded or t in existing_types})
            if id_docs_count < 2:
                upload_errors.append("Upload at least 2 ID documents (QID, Passport, Driving License or Istimara).")
            if not vehicle_selected:
                upload_errors.append("Please select your available vehicle type.")
            if job_type_val not in dict(fleet_models.DRIVER_JOB_TYPE_CHOICES):
                upload_errors.append("Please select your work preference (full time, part time or both).")
            if valid_zone_ids and not selected_zone_ids:
                upload_errors.append("Select at least one delivery zone you want to work in.")

        if pform.is_valid() and (not vehicle_selected or vform.is_valid()) and not upload_errors:
            from django.db import transaction
            from django.db.models import Max

            with transaction.atomic():
                profile = pform.save(commit=False)
                profile.user = request.user
                if not profile.username:
                    profile.username = request.user.username
                if not profile.email:
                    profile.email = request.user.email
                if not is_partial_save:
                    profile.is_driver = True
                    profile.is_business = False
                    if profile.get_profile_completion_percentage() == 100:
                        profile.is_profile_completed = True
                    if profile.verification_status != 'verified':
                        profile.verification_status = VERIFICATION_STATUS_PENDING
                        profile.verification_applied_at = dj_timezone.now()
                profile.save()

                # A driver row is needed to attach vehicle/documents; on a bare
                # partial save (profile fields only) we skip creating one.
                need_driver_row = (
                    driver is not None or not is_partial_save or uploaded
                    or vehicle_selected
                    or bool((request.POST.get('driver_license_number') or '').strip())
                    or request.POST.get('has_driver_license') == 'on'
                    or bool(job_type_val)
                    or bool(request.POST.getlist('work_time_slabs'))
                    or bool(selected_zone_ids)
                )
                is_new_driver = driver is None
                if is_new_driver and need_driver_row:
                    # Legacy join paths used user.id for this PK — never clobber
                    # another driver's row when the sequences collide.
                    new_id = profile.id
                    if fleet_models.Driver.objects.filter(pk=new_id).exists():
                        new_id = (fleet_models.Driver.objects.aggregate(m=Max('driver_id'))['m'] or 0) + 1
                    code = ''.join(random.choice(string.digits) for _ in range(6))
                    while fleet_models.Driver.objects.filter(driver_code=code).exists():
                        code = ''.join(random.choice(string.digits) for _ in range(6))
                    driver = fleet_models.Driver(
                        user=request.user,
                        profile=profile,
                        driver_id=new_id,
                        driver_status=DRIVER_STATUS_PENDING,
                        driver_code=code,
                        driver_languages='english',
                    )

                if driver:
                    driver.profile = profile
                    driver.driver_phone = profile.phone or driver.driver_phone or ''
                    driver.driver_whatsapp = profile.whatsapp or driver.driver_whatsapp or ''
                    driver.has_driver_license = request.POST.get('has_driver_license') == 'on'
                    license_no = (request.POST.get('driver_license_number') or '').strip()
                    if license_no:
                        driver.driver_license_number = license_no

                    # Work availability preference (Section 3)
                    if job_type_val in dict(fleet_models.DRIVER_JOB_TYPE_CHOICES):
                        driver.job_type = job_type_val
                    valid_slabs = dict(fleet_models.WORK_TIME_SLAB_CHOICES)
                    slabs = [s for s in request.POST.getlist('work_time_slabs') if s in valid_slabs]
                    driver.work_time_slabs = ','.join(slabs)

                    # Registration location captured by the browser at submit time
                    try:
                        geo_lat = float(request.POST.get('geo_lat', ''))
                        geo_lng = float(request.POST.get('geo_lng', ''))
                    except (TypeError, ValueError):
                        geo_lat = geo_lng = None
                    if geo_lat is not None and -90 <= geo_lat <= 90 and -180 <= geo_lng <= 180:
                        meta = driver.driver_meta or {}
                        meta['registration_location'] = {
                            'lat': geo_lat,
                            'lng': geo_lng,
                            'accuracy_m': (request.POST.get('geo_accuracy') or '').strip(),
                            'captured_at': dj_timezone.now().isoformat(),
                        }
                        driver.driver_meta = meta
                    driver.save()

                    # Preferred delivery zones (Section 3) — a partial save with
                    # nothing ticked keeps whatever was saved before
                    if selected_zone_ids or not is_partial_save:
                        driver.preferred_zone_groups.set(selected_zone_ids)

                    if vehicle_selected:
                        vehicle = vform.save(commit=False)
                        vehicle.driver = driver
                        vehicle.save()

                    for doc_type in APPLY_DOC_TYPES:
                        f = uploaded.get(doc_type)
                        doc_no = (request.POST.get(f'doc_no_{doc_type.replace(" ", "_")}') or '').strip()
                        doc = fleet_models.DriverDocument.objects.filter(
                            driver=driver, document_type=doc_type).first()
                        if not f and not (doc_no and doc):
                            continue
                        if doc is None:
                            doc = fleet_models.DriverDocument(
                                driver=driver, document_type=doc_type, document_no='')
                        if f:
                            # Replace: drop the old image so protected media doesn't accumulate orphans
                            if doc.pk and doc.document_file and 'doc_default' not in doc.document_file.name:
                                doc.document_file.delete(save=False)
                            doc.document_file = f
                        if doc_no:
                            doc.document_no = doc_no
                        doc.save()

            if is_partial_save:
                logger.info(f"Driver application progress saved for user {request.user.id}")
                # Wizard "Save & Continue": jump straight to the next section, no toast
                step_next = request.POST.get('step', '')
                if step_next in ('2', '3', '4'):
                    return redirect(f"{reverse('core:join_driver')}?step={step_next}")
                messages.success(request, "Progress saved! You can continue your application anytime.")
            else:
                logger.info(f"Driver application submitted for user {request.user.id} (new={is_new_driver})")
                messages.success(request, "Application submitted! Our team will review it and contact you on WhatsApp.")
            return redirect('core:join_driver')
        else:
            for err in upload_errors:
                messages.error(request, err)
            messages.error(request, "Please fix the highlighted fields and try again.")
            # Reopen the wizard on the first section that has a problem
            if not pform.is_valid():
                initial_step = 1
            elif vehicle_selected and not vform.is_valid():
                initial_step = 2
            elif any('zone' in e or 'work preference' in e for e in upload_errors):
                initial_step = 3
            else:
                initial_step = 4
    else:
        pform = core_forms.DriverApplyProfileForm(instance=profile)
        vform = fleet_forms.DriverVehicleForm(prefix='veh', instance=primary_vehicle)
        # First visit after Google login: prefill name from the Google account
        if request.user.is_authenticated and profile and not profile.first_name:
            pform.initial['first_name'] = request.user.first_name
            pform.initial['last_name'] = request.user.last_name
        try:
            initial_step = min(4, max(1, int(request.GET.get('step', 1))))
        except (TypeError, ValueError):
            initial_step = 1

    application_status = ''
    if profile and profile.is_driver and driver:
        application_status = profile.verification_status

    existing_docs = {}
    if driver:
        for doc in driver.driver_document.filter(document_type__in=APPLY_DOC_TYPES).exclude(document_file=''):
            existing_docs[doc.document_type] = doc
    DOC_ICONS = {
        'Selfie': 'fa-camera', 'QID': 'fa-id-card', 'Passport': 'fa-passport',
        'Driving License': 'fa-id-badge', 'Istimara': 'fa-car',
    }
    doc_list = [
        {'type': dt, 'key': dt.replace(' ', '_'), 'doc': existing_docs.get(dt),
         'icon': DOC_ICONS.get(dt, 'fa-file')}
        for dt in APPLY_DOC_TYPES
    ]

    # Verified drivers are locked to the status page; pending ones may still edit
    if is_verified_driver:
        show_status_only = True
    else:
        show_status_only = application_status in ('pending', 'under_review') and request.GET.get('edit') != '1'

    # Per-section progress (resume indicator for partially-filled applications)
    PROFILE_PROGRESS_FIELDS = [
        'first_name', 'last_name', 'phone', 'whatsapp',
        'nationlity', 'zone_name', 'address', 'date_of_birth',
    ]
    sec1_done = sum(1 for f in PROFILE_PROGRESS_FIELDS if profile and getattr(profile, f, None))
    sec1_total = len(PROFILE_PROGRESS_FIELDS)
    sec2_complete = bool(
        primary_vehicle and primary_vehicle.vehicle_type and primary_vehicle.vehicle_type != 'none'
    )
    driver_zone_group_ids = set(
        driver.preferred_zone_groups.values_list('id', flat=True)
    ) if driver else set()
    sec3_complete = bool(
        driver and driver.job_type
        and (driver_zone_group_ids or not zone_groups)
    )
    sec4_selfie = 'Selfie' in existing_docs
    sec4_ids = len([t for t in existing_docs if t != 'Selfie'])
    sec4_complete = sec4_selfie and sec4_ids >= 2
    sections_progress = {
        'sec1_done': sec1_done,
        'sec1_total': sec1_total,
        'sec1_complete': sec1_done == sec1_total,
        'sec2_complete': sec2_complete,
        'sec3_complete': sec3_complete,
        'sec4_selfie': sec4_selfie,
        'sec4_ids': sec4_ids,
        'sec4_complete': sec4_complete,
        'has_any': bool(sec1_done or sec2_complete or sec3_complete or existing_docs),
        'percent': int(
            (sec1_done / sec1_total * 50)
            + (15 if sec2_complete else 0)
            + (15 if sec3_complete else 0)
            + (20 if sec4_complete else (10 if (sec4_selfie or sec4_ids) else 0))
        ),
    }

    context = {
        'pform': pform,
        'vform': vform,
        'profile': profile,
        'driver': driver,
        'job_type_choices': fleet_models.DRIVER_JOB_TYPE_CHOICES,
        'work_time_slab_tiles': [
            {'value': 'morning', 'label': 'Morning', 'time': '6 AM – 12 PM', 'icon': 'fa-cloud-sun'},
            {'value': 'afternoon', 'label': 'Afternoon', 'time': '12 PM – 6 PM', 'icon': 'fa-sun'},
            {'value': 'evening', 'label': 'Evening', 'time': '6 PM – 12 AM', 'icon': 'fa-cloud-moon'},
            {'value': 'night', 'label': 'Night', 'time': '12 AM – 6 AM', 'icon': 'fa-moon'},
        ],
        'driver_time_slabs': driver.work_time_slab_list if driver else [],
        'zone_groups': zone_groups,
        'driver_zone_group_ids': driver_zone_group_ids,
        'initial_step': initial_step,
        'doc_list': doc_list,
        'application_status': application_status,
        'show_status_only': show_status_only,
        'already_business': already_business,
        'progress': sections_progress,
        'user_email': request.user.email if request.user.is_authenticated else '',
    }
    return render(request, 'core/join_us_driver.html', context)


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
            return redirect('core:profile', user_number=_get_user_number(request.user.id))
        else:
            logger.warning(f"Invalid role update form for user {request.user.id}")
            messages.error(request, "Please correct the errors below.")

    context = {
        'form': joinusform,
        'profile': profile,
        'driver': driver,
    }
    return render(request, 'core/profile_role_update.html', context)


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
        return redirect('core:profile', user_number=_get_user_number(request.user.id))
    elif request.method == 'POST':
        logger.warning(f"Invalid driver update form for user {request.user.id}")
        messages.error(request, "Please correct the errors below.")

    # Get profile picture for sidebar
    try:
        profile_picture = core_models.ProfilePicture.objects.get(user_id=request.user.id)
    except core_models.ProfilePicture.DoesNotExist:
        profile_picture = core_models.ProfilePicture.objects.create(
            user=request.user, profile=profile
        )

    context = {
        'driverjoinform': driverjoinform,
        'profile': profile,
        'profile_picture': profile_picture,
        'completion_percentage': profile.get_profile_completion_percentage(),
    }
    return render(request, 'core/update_driver.html', context)


@login_required(login_url='/accounts/login/')
def business_profile_update(request):
    """Update business profile information"""
    business_profile = get_cached_business(request)
    if not business_profile:
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
        return redirect('business:business_profile', business_id=business_profile.business_id)
    elif request.method == 'POST':
        logger.warning(f"Invalid business update form for user {request.user.id}")
        messages.error(request, "Please correct the errors below.")

    context = {
        'form': form,
    }
    return render(request, 'business/frontend/business_profile_update.html', context)


@login_required(login_url='/accounts/login/')
@require_GET
def team_business_search(request):
    """AJAX: Search active businesses by name, phone, or business code."""
    q = request.GET.get('q', '').strip()
    results = []
    if len(q) >= 2:
        businesses = (
            business_models.Business.objects
            .filter(business_status='active')
            .filter(
                Q(business_name__icontains=q) |
                Q(business_phone__icontains=q) |
                Q(business_code__icontains=q)
            )
            .values('business_id', 'business_name', 'business_phone', 'business_code')
            [:10]
        )
        for b in businesses:
            results.append({
                'id': b['business_id'],
                'name': b['business_name'],
                'phone': b['business_phone'] or '',
                'code': b['business_code'] or '',
            })
    return JsonResponse({'results': results})


@login_required(login_url='/accounts/login/')
@require_POST
def team_apply_request(request):
    """AJAX: Submit a team join request (creates a pending BusinessTeamProfile)."""
    import json
    try:
        data = json.loads(request.body)
        business_id = int(data.get('business_id', 0))
    except (ValueError, TypeError):
        return JsonResponse({'ok': False, 'error': 'Invalid request.'}, status=400)

    try:
        business = business_models.Business.objects.get(
            business_id=business_id, business_status='active'
        )
    except business_models.Business.DoesNotExist:
        return JsonResponse({'ok': False, 'error': 'Business not found.'}, status=404)

    profile = get_cached_profile(request)
    if not profile:
        return JsonResponse({'ok': False, 'error': 'Profile not found.'}, status=400)

    # Prevent duplicate pending/active requests
    existing = business_models.BusinessTeamProfile.objects.filter(
        business=business, user=request.user
    ).exclude(team_status='rejected').first()
    if existing:
        status_label = dict(business_models.BusinessTeamProfile.STATUS_CHOICES).get(
            existing.team_status, existing.team_status
        )
        return JsonResponse({
            'ok': False,
            'error': f'You already have a {status_label} request for this business.'
        }, status=400)

    business_models.BusinessTeamProfile.objects.create(
        business=business,
        user=request.user,
        profile=profile,
        team_name=f'{profile.first_name} {profile.last_name}'.strip() or request.user.username,
        team_email=request.user.email,
        team_phone=profile.phone or '',
        team_role='staff',
        team_status='pending',
    )
    logger.info(f"Team join request: user {request.user.id} → business {business_id}")
    return JsonResponse({'ok': True, 'business_name': business.business_name})


@login_required(login_url='/accounts/login/')
def join_team(request):
    """Full-page team join flow — search a business and send an application."""
    profile = get_cached_profile(request)
    if not profile:
        messages.info(request, "Please create your profile first.")
        return redirect('core:profile_add')

    try:
        profile_picture = core_models.ProfilePicture.objects.get(user_id=request.user.id)
    except core_models.ProfilePicture.DoesNotExist:
        profile_picture = core_models.ProfilePicture.objects.create(
            user_id=request.user.id, profile_id=request.user.id
        )

    completion_percentage = profile.get_profile_completion_percentage()
    context = {
        'profile': profile,
        'profile_picture': profile_picture,
        'completion_percentage': completion_percentage,
    }
    return render(request, 'core/join_team.html', context)


@login_required(login_url='/accounts/login/')
def join_us(request):
    """Handle role selection (driver or business)"""
    profile = get_cached_profile(request)
    if profile:
        joinusform = core_forms.JoinUsForm(request.POST or None, instance=profile)
        driverjoinform = fleet_forms.DriverJoinForm(request.POST or None)
        businessjoinform = business_forms.businessRegisterForm(request.POST or None)

        if request.method == 'POST':
            if driverjoinform.is_valid():
                # Legacy path retired: driver applications go through the full
                # 3-section flow (documents + vehicle + geo) at core:join_driver.
                logger.info(f"Redirecting legacy driver join to application flow for user {request.user.id}")
                messages.info(request, "Please complete your driver application here — it takes 3 quick steps.")
                return redirect('core:join_driver')

            if businessjoinform.is_valid():
                logger.info(f"Processing business join for user {request.user.id}")
                profile_update = joinusform.save(commit=False)
                profile_update.user = request.user
                profile_update.is_driver = False
                profile_update.is_business = True
                profile_update.save()

                logger.info(f"Business join completed for user {request.user.id}")
                messages.success(request, 'Your business account has been created!')

            return redirect('core:profile', user_number=_get_user_number(request.user.id))
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
def join_us_team(request):
    """Dedicated page for users to search a business and submit a team join request."""
    profile = get_cached_profile(request)
    if not profile:
        messages.info(request, "Please create your profile first.")
        return redirect('core:profile_add')

    my_requests = business_models.BusinessTeamJoinRequest.objects.filter(
        user=request.user
    ).exclude(status='cancelled').select_related('business').order_by('-requested_at')

    try:
        profile_picture = core_models.ProfilePicture.objects.get(user_id=request.user.id)
    except core_models.ProfilePicture.DoesNotExist:
        profile_picture = core_models.ProfilePicture.objects.create(
            user_id=request.user.id, profile_id=request.user.id
        )

    completion_percentage = profile.get_profile_completion_percentage()

    context = {
        'profile': profile,
        'profile_picture': profile_picture,
        'completion_percentage': completion_percentage,
        'my_requests': my_requests,
    }
    return render(request, 'core/join_us_team.html', context)


@login_required(login_url='/accounts/login/')
def main_dashboard(request):
    """Main dashboard with verification status checking"""
    # Check Django User is_staff FIRST - no other validations needed for staff
    if request.user.is_staff:
        return redirect('workforce:wf_dashboard')

    profile = get_cached_profile(request)
    if profile:

        # Check if profile is completed (only for non-staff users)
        if not profile.is_profile_completed:
            messages.warning(request, "Please complete your profile to access the dashboard.")
            return redirect('core:profile_complete_update')

        # Team members go straight to the business dashboard. Their personal
        # verification_status stays 'incomplete' (they never apply as a
        # business/driver), so this must run BEFORE the verification branching
        # below — otherwise they get bounced to profile completion.
        if not profile.is_business and not profile.is_driver:
            from business.models import BusinessTeamProfile
            memberships = BusinessTeamProfile.objects.select_related('business').filter(
                user=request.user
            )
            active_member = memberships.filter(
                team_status='active', team_verifed=True
            ).first()
            if active_member:
                return redirect('business:business_dashboard')
            pending_member = memberships.filter(team_status='pending').first()
            if pending_member:
                messages.info(request, "Your team membership is pending staff verification. Please wait for approval.")
                return render(request, 'core/verification_pending.html', {'profile': profile, 'ob_role': ''})
            # Membership exists but none is active (deactivated/suspended, or
            # never staff-verified) — tell the user instead of dropping them
            # into the role-registration flow below. Declined/rejected
            # memberships are treated as no membership.
            blocked_member = memberships.exclude(team_status='rejected').first()
            if blocked_member:
                messages.warning(
                    request,
                    f"Your team membership with {blocked_member.business.business_name} is "
                    f"{blocked_member.get_team_status_display().lower()}. Please contact the business owner."
                )
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
            ob_role = 'business' if profile.is_business else ('driver' if profile.is_driver else '')
            return render(request, 'core/verification_pending.html', {'profile': profile, 'ob_role': ob_role})

        elif profile.verification_status == VERIFICATION_STATUS_UNDER_REVIEW:
            messages.info(request, "Your application is under review. We'll notify you once verified.")
            ob_role = 'business' if profile.is_business else ('driver' if profile.is_driver else '')
            return render(request, 'core/verification_pending.html', {'profile': profile, 'ob_role': ob_role})

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
            else:
                # Check if user is a verified team member of any business
                from business.decorators import get_user_business_access
                business, access_type, team_profile = get_user_business_access(request.user, request)
                if business and access_type == 'team_member':
                    if team_profile and team_profile.team_verifed and team_profile.team_status == 'active':
                        return redirect('business:business_dashboard')
                    elif team_profile and team_profile.team_status == 'pending':
                        messages.info(request, "Your team membership is pending staff verification. Please wait for approval.")
                        ob_role = ''
                        return render(request, 'core/verification_pending.html', {'profile': profile, 'ob_role': ob_role})
                    else:
                        messages.warning(request, "Your team membership is not active. Please contact the business owner.")
                        return redirect('core:profile_complete_update')

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
    try:
        profile = core_models.Profile.objects.get(user_id=user_id)
        # Auto-generate user_number if somehow missing (legacy data)
        if not profile.user_number:
            profile.save()
            profile.refresh_from_db()
        logger.debug(f"Redirecting user {user_id} to profile {profile.user_number}")
        return redirect('core:profile', user_number=profile.user_number)
    except core_models.Profile.DoesNotExist:
        logger.info(f"No profile found for user {user_id}, redirecting to profile_add")
        messages.info(request, "Please create your profile.")
        return redirect('core:profile_add')


@login_required(login_url='/accounts/login/')
def profile(request, user_number):
    """Display user profile"""
    # Look up profile by user_number
    profile = get_object_or_404(
        core_models.Profile.objects.select_related('user').prefetch_related('profile_picture'),
        user_number=user_number
    )

    is_own_profile = (profile.user_id == request.user.id)

    if not is_own_profile and not request.user.is_staff:
        messages.error(request, 'You do not have permission to view this profile.')
        own_user_number = _get_user_number(request.user.id)
        return redirect('core:profile', user_number=own_user_number)

    # Cache on request so context processor doesn't re-fetch
    if is_own_profile:
        request._cached_profile = profile

    # Get profile picture from prefetch cache if possible
    profile_picture = profile.profile_picture.first()

    if not profile_picture and is_own_profile:
        # Create default profile picture only for own profile
        profile_picture = core_models.ProfilePicture(
            user=request.user,
            profile=profile,
            profile_picture='core/user/avatar.png'
        )
        profile_picture.save()
        logger.info(f"Created default profile picture for user {request.user.id}")

    # Calculate completion percentage
    completion_percentage = profile.get_profile_completion_percentage()

    context = {
        "profile": profile,
        "profile_picture": profile_picture,
        "completion_percentage": completion_percentage,
        "is_own_profile": is_own_profile,
    }

    return render(request, 'core/profile.html', context)


@login_required(login_url='/accounts/login/')
def profile_add(request):
    """Add new user profile"""
    # Redirect if user already has a profile to prevent duplicate key error
    if core_models.Profile.objects.filter(user_id=request.user.id).exists():
        messages.info(request, 'You already have a profile.')
        return redirect('core:profile', user_number=_get_user_number(request.user.id))

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
            messages.success(request, 'Profile created! Now complete your details and choose your role.')
            return redirect('core:profile_complete_update')
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
def profile_update_redirect(request, user_number):
    """Redirect old profile update URL to new profile complete update page"""
    logger.info(f"Redirecting user {user_number} from old profile_update to profile_complete_update")
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
                profile_pic.profile = profile
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
def profile_completion_test(request, user_number):
    """Test profile completion status (for development/testing)"""
    profile = get_object_or_404(core_models.Profile, user_number=user_number)
    logger.debug(f"Profile completion test for user_number {user_number}")

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
    # Check Django User is_staff FIRST - no other validations needed for staff
    if request.user.is_staff:
        return redirect('workforce:wf_dashboard')

    # Use cached profile from context processor if available
    profile = getattr(request, '_cached_profile', None)
    if profile is None:
        try:
            profile = core_models.Profile.objects.select_related('user').get(user_id=request.user.id)
            request._cached_profile = profile
        except core_models.Profile.DoesNotExist:
            messages.error(request, "Please create a profile first!")
            return redirect('core:profile_add')
    if profile is None:
        messages.error(request, "Please create a profile first!")
        return redirect('core:profile_add')

    # Redirect pending/under_review users straight to step 4
    if profile.verification_status in ('pending', 'under_review'):
        if profile.is_business:
            return redirect('core:business_register')
        if profile.is_driver:
            return redirect('core:driver_register')

    # Ensure profile username matches Django User username
    if profile.username != request.user.username:
        profile.username = request.user.username
        profile.save()

    # Fetch team invitations for this user:
    # - pending + not verified = new invitation (show accept/decline buttons)
    # - pending + verified = user accepted, awaiting staff verification
    # - rejected = user declined
    team_invitations = business_models.BusinessTeamProfile.objects.filter(
        user=request.user,
        team_status__in=['pending', 'rejected']
    ).select_related('business', 'invited_by')

    if request.method == 'POST':
        action = request.POST.get('action')

        # Handle accept/decline invitation actions separately (no form validation needed)
        if action and action.startswith('accept_invitation_'):
            invitation_id = action.replace('accept_invitation_', '')
            try:
                invitation = business_models.BusinessTeamProfile.objects.get(
                    id=invitation_id, user=request.user, team_status='pending', team_verifed=False
                )
                # Keep pending for staff verification, mark user accepted
                invitation.team_verifed = True
                invitation.save()
                messages.success(request, f"Invitation accepted! Pending staff verification for {invitation.business.business_name}.")
            except business_models.BusinessTeamProfile.DoesNotExist:
                messages.error(request, "Invitation not found or already processed.")
            return redirect('core:profile_complete_update')

        elif action and action.startswith('decline_invitation_'):
            invitation_id = action.replace('decline_invitation_', '')
            try:
                invitation = business_models.BusinessTeamProfile.objects.get(
                    id=invitation_id, user=request.user, team_status='pending', team_verifed=False
                )
                invitation.team_status = 'rejected'
                invitation.save()
                messages.success(request, "Invitation declined.")
            except business_models.BusinessTeamProfile.DoesNotExist:
                messages.error(request, "Invitation not found or already processed.")
            return redirect('core:profile_complete_update')

        form = core_forms.ProfileUpdateForm(request.POST, instance=profile)
        # Auto-populate username from logged-in user and disable it
        form.fields['username'].initial = request.user.username
        form.fields['username'].widget.attrs['readonly'] = True
        form.fields['username'].disabled = True

        if form.is_valid():
            profile = form.save(commit=False)
            # Ensure username stays the same as the Django User account username
            profile.username = request.user.username

            # Check if profile is complete
            completion_percentage = profile.get_profile_completion_percentage()

            # Mark profile as completed when 100%
            if completion_percentage == 100:
                profile.is_profile_completed = True

            if action == 'save':
                profile.save()
                messages.success(request, f"Profile saved successfully! ({completion_percentage}% complete)")
                return redirect('core:profile_complete_update')

            elif action == 'register_business' or action == 'join_driver':
                # Check if profile is at least 50% complete
                if completion_percentage >= 50:

                    if action == 'register_business':
                        # Warn if already applied as business
                        if profile.is_business or business_models.Business.objects.filter(user_id=request.user.id).exists():
                            messages.warning(request, "You have already submitted a business registration. Please check your business profile.")
                            return redirect('core:business_register')
                        profile.is_business = True
                        profile.save()
                        messages.success(request, "Profile completed! Please complete your business registration form.")
                        return redirect('core:business_register')

                    else:  # join_driver
                        # Warn if already applied as driver
                        if profile.is_driver or fleet_models.Driver.objects.filter(user_id=request.user.id).exists():
                            messages.warning(request, "You have already submitted a driver application. Please check your driver profile.")
                            return redirect('core:driver_register')
                        profile.is_driver = True
                        profile.save()
                        messages.success(request, "Profile completed! Please complete your driver registration form.")
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

    if (profile.is_business or profile.is_driver) and profile.verification_status in ('pending', 'under_review'):
        ob_step = 4
        ob_role = 'business' if profile.is_business else 'driver'
    else:
        ob_step = 1
        ob_role = ''

    context = {
        'form': form,
        'profile': profile,
        'completion_percentage': completion_percentage,
        'team_invitations': team_invitations,
        'ob_step': ob_step,
        'ob_role': ob_role,
    }
    return render(request, 'core/profile_complete_update.html', context)


@login_required(login_url='/accounts/login/')
def business_register(request):
    """Business registration with completion tracking"""
    profile = get_cached_profile(request)
    if not profile:
        messages.error(request, "Please complete your profile first!")
        return redirect('core:profile_complete_update')

    # Staff users don't need to register as business - redirect to staff dashboard
    if profile.is_staff:
        messages.warning(request, "Staff users cannot register as business. Redirecting to staff dashboard.")
        return redirect('workforce:wf_dashboard')

    # Check if profile is at least 50% complete
    if profile.get_profile_completion_percentage() < 50:
        messages.error(request, "Please complete at least 50% of your profile before proceeding.")
        return redirect('core:profile_complete_update')

    # Check if user is set as business
    if not profile.is_business:
        messages.error(request, "Please select business role in your profile first!")
        return redirect('core:profile_complete_update')

    # Check if business already exists (use cached version)
    business = get_cached_business(request)
    is_update = business is not None

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
            completion_percentage = calculate_business_completion(business)

            if action == 'save':
                messages.success(request, f"Business information saved! ({completion_percentage}% complete)")
                logger.info(f"Business info saved for user {request.user.id}: {completion_percentage}% complete")
                return redirect('core:business_register')

            elif action == 'apply_verification':
                if completion_percentage == 100:
                    profile.is_business_profile_completed = True
                    profile.verification_status = VERIFICATION_STATUS_PENDING
                    profile.verification_applied_at = dj_timezone.now()
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
    completion_percentage = calculate_business_completion(business) if business else 0

    can_apply = profile.can_apply_for_verification()

    ob_step = 4 if profile.verification_status in ('pending', 'under_review') else 3

    context = {
        'form': form,
        'profile': profile,
        'completion_percentage': completion_percentage,
        'can_apply': can_apply,
        'is_update': is_update,
        'ob_step': ob_step,
    }
    return render(request, 'core/business_register.html', context)


@login_required(login_url='/accounts/login/')
def driver_register(request):
    """Driver registration with completion tracking"""
    profile = get_cached_profile(request)
    if not profile:
        messages.error(request, "Please complete your profile first!")
        return redirect('core:profile_complete_update')

    # Staff users don't need to register as driver - redirect to staff dashboard
    if profile.is_staff:
        messages.warning(request, "Staff users cannot register as driver. Redirecting to staff dashboard.")
        return redirect('workforce:wf_dashboard')

    # Check if profile is at least 50% complete
    if profile.get_profile_completion_percentage() < 50:
        messages.error(request, "Please complete at least 50% of your profile before proceeding.")
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

    # Primary vehicle (one per driver, edit in place)
    primary_vehicle = driver.driver_vehicle.first() if driver else None

    if request.method == 'POST':
        form = fleet_forms.DriverJoinForm(request.POST, instance=driver)
        vehicle_form = fleet_forms.DriverVehicleForm(request.POST, request.FILES, prefix='veh', instance=primary_vehicle)
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

            # Save/update primary vehicle if a type is selected
            veh_type = request.POST.get('veh-vehicle_type', '')
            if veh_type and veh_type != 'none' and vehicle_form.is_valid():
                vehicle = vehicle_form.save(commit=False)
                vehicle.driver = driver
                vehicle.save()
                primary_vehicle = vehicle

            # Save documents (QID, Passport, Driving License, Istimara)
            DOC_TYPES = ['QID', 'Passport', 'Driving License', 'Istimara']
            for doc_type in DOC_TYPES:
                file_key = f'doc_{doc_type.replace(" ", "_")}'
                if file_key in request.FILES:
                    doc, _ = fleet_models.DriverDocument.objects.get_or_create(
                        driver=driver, document_type=doc_type,
                        defaults={'document_no': ''}
                    )
                    doc.document_file = request.FILES[file_key]
                    doc_no = request.POST.get(f'doc_no_{doc_type.replace(" ", "_")}', '')
                    if doc_no:
                        doc.document_no = doc_no
                    doc.save()

            # Calculate completion (includes vehicle_type + vehicle_model)
            completion_percentage = calculate_driver_completion(driver)

            if action == 'save':
                messages.success(request, f"Driver information saved! ({completion_percentage}% complete)")
                logger.info(f"Driver info saved for user {request.user.id}: {completion_percentage}% complete")
                return redirect('core:driver_register')

            elif action == 'apply_verification':
                if completion_percentage == 100:
                    profile.is_driver_profile_completed = True
                    profile.verification_status = VERIFICATION_STATUS_PENDING
                    profile.verification_applied_at = dj_timezone.now()
                    profile.save()
                    logger.info(f"Driver verification applied for user {request.user.id}")
                    messages.success(request, "Application submitted for verification! Our team will review it soon.")
                    return redirect('core:profile_view')
                else:
                    logger.warning(f"Incomplete driver profile for user {request.user.id}: {completion_percentage}%")
                    messages.warning(request, f"Progress saved ({completion_percentage}% complete). Fill all required fields to submit for verification.")
                    return redirect('core:driver_register')
        else:
            vehicle_form = fleet_forms.DriverVehicleForm(prefix='veh', instance=primary_vehicle)
            logger.warning(f"Invalid driver form for user {request.user.id}")
            messages.error(request, "Please correct the errors below.")
    else:
        form = fleet_forms.DriverJoinForm(instance=driver)
        vehicle_form = fleet_forms.DriverVehicleForm(prefix='veh', instance=primary_vehicle)

    # Calculate completion (includes vehicle_type + vehicle_model)
    completion_percentage = calculate_driver_completion(driver) if driver else 0

    can_apply = profile.can_apply_for_verification()

    # Build documents list for template
    DOC_TYPES = ['QID', 'Passport', 'Driving License', 'Istimara']
    existing_docs = {}
    if driver:
        for doc in driver.driver_document.filter(document_type__in=DOC_TYPES):
            existing_docs[doc.document_type] = doc
    doc_list = [
        {'type': dt, 'key': dt.replace(' ', '_'), 'doc': existing_docs.get(dt)}
        for dt in DOC_TYPES
    ]

    is_pending = profile.verification_status in ('pending', 'under_review')
    edit_mode = request.GET.get('edit') == '1'
    show_status_only = is_pending and not edit_mode

    context = {
        'form': form,
        'vehicle_form': vehicle_form,
        'profile': profile,
        'completion_percentage': completion_percentage,
        'can_apply': can_apply,
        'is_update': is_update,
        'doc_list': doc_list,
        'show_status_only': show_status_only,
        'is_pending': is_pending,
    }
    return render(request, 'core/driver_register.html', context)


@login_required(login_url='/accounts/login/')
def make_staff(request):
    """
    Temporary view to set current user as staff.
    Only works for superusers. Remove after use.
    """
    _prof = getattr(request.user, 'profile', None)
    if not (request.user.is_superuser or getattr(_prof, 'is_superadmin', False)):
        messages.error(request, "Only superadmins can access this.")
        return redirect('core:main_dashboard')

    profile = get_cached_profile(request)
    if profile:
        profile.is_staff = True
        profile.is_profile_completed = True
        profile.save()
        messages.success(request, f"Profile updated! is_staff={profile.is_staff}")
        logger.info(f"User {request.user.id} set as staff")
        return redirect('workforce:wf_dashboard')
    else:
        messages.error(request, "Profile not found!")
        return redirect('core:profile_add')


def check_whatsapp_availability(request):
    """Check if WhatsApp number is available and valid"""
    from django.http import JsonResponse

    if request.method != 'GET':
        return JsonResponse({'error': 'Invalid request method'}, status=400)

    whatsapp = request.GET.get('whatsapp', '').strip()
    if not whatsapp:
        return JsonResponse({'available': True, 'message': 'WhatsApp number is available'})

    # For authenticated users, exclude their own number
    if request.user.is_authenticated:
        try:
            user_profile = request.user.profile
        except core_models.Profile.DoesNotExist:
            user_profile = None

        # Check 1: Validate WhatsApp number format and account
        is_valid, validation_msg = validate_whatsapp_number(whatsapp)
        if not is_valid:
            return JsonResponse({
                'available': False,
                'message': validation_msg
            })

        # Check 2: Is this WhatsApp number already used by another user?
        if user_profile:
            whatsapp_duplicate = core_models.Profile.objects.filter(
                whatsapp=whatsapp
            ).exclude(user_id=request.user.id).exists()
        else:
            whatsapp_duplicate = core_models.Profile.objects.filter(
                whatsapp=whatsapp
            ).exists()

        if whatsapp_duplicate:
            return JsonResponse({
                'available': False,
                'message': 'This WhatsApp number is already in use by another account'
            })

        # Check 3: Is this WhatsApp number used as phone by another user?
        if user_profile:
            phone_conflict = core_models.Profile.objects.filter(
                phone=whatsapp
            ).exclude(user_id=request.user.id).exists()
        else:
            phone_conflict = core_models.Profile.objects.filter(
                phone=whatsapp
            ).exists()

        if phone_conflict:
            return JsonResponse({
                'available': False,
                'message': 'This number is already registered as phone number for another account'
            })

        return JsonResponse({
            'available': True,
            'message': 'WhatsApp number is available'
        })

    # For unauthenticated users, don't check - let form validation handle it
    # Return available=true to not block the form
    return JsonResponse({
        'available': True,
        'message': 'WhatsApp number is available'
    })


def check_phone_availability(request):
    """Check if phone number is available and unique"""
    from django.http import JsonResponse

    if request.method != 'GET':
        return JsonResponse({'error': 'Invalid request method'}, status=400)

    phone = request.GET.get('phone', '').strip()
    if not phone:
        return JsonResponse({'available': True, 'message': 'Phone number is available'})

    # For authenticated users, exclude their own number
    if request.user.is_authenticated:
        try:
            user_profile = request.user.profile
        except core_models.Profile.DoesNotExist:
            user_profile = None

        # Check 1: Validate phone number format
        # Accepts: 8-digit Qatar local (e.g. 30123456) OR any international number (10–15 digits with country code)
        digits_only = ''.join(filter(str.isdigit, str(phone)))

        is_valid_format = (
            len(digits_only) == 8  # Qatar local format
            or (10 <= len(digits_only) <= 15)  # International: country code + local (E.164)
        )

        if not is_valid_format:
            return JsonResponse({
                'available': False,
                'message': f'Phone number must be 8 digits (local) or 10–15 digits with country code. You provided {len(digits_only)} digits.'
            })

        # Check 2: Is this phone number already used by another user?
        if user_profile:
            phone_duplicate = core_models.Profile.objects.filter(
                phone=phone
            ).exclude(user_id=request.user.id).exists()
        else:
            phone_duplicate = core_models.Profile.objects.filter(
                phone=phone
            ).exists()

        if phone_duplicate:
            return JsonResponse({
                'available': False,
                'message': 'This phone number is already in use by another account'
            })

        # Check 3: Is this phone number used as WhatsApp by another user?
        if user_profile:
            whatsapp_conflict = core_models.Profile.objects.filter(
                whatsapp=phone
            ).exclude(user_id=request.user.id).exists()
        else:
            whatsapp_conflict = core_models.Profile.objects.filter(
                whatsapp=phone
            ).exists()

        if whatsapp_conflict:
            return JsonResponse({
                'available': False,
                'message': 'This number is already registered as WhatsApp number for another account'
            })

        return JsonResponse({
            'available': True,
            'message': 'Phone number is available'
        })

    # For unauthenticated users, don't check - let form validation handle it
    # Return available=true to not block the form
    return JsonResponse({
        'available': True,
        'message': 'Phone number is available'
    })


# ==========================================
# SIGNUP SECURITY VIEWS
# ==========================================

@method_decorator(
    ratelimit(key='ip', rate='5/h', method='POST', block=True),
    name='dispatch'
)
class RateLimitedSignupView(SignupView):
    """
    Custom signup view with IP-based rate limiting and CAPTCHA protection.

    Rate limiting:
        - 5 POST attempts per hour per IP address
        - Returns HTTP 429 when exceeded

    CAPTCHA:
        - Google reCAPTCHA v2 checkbox
        - Verified server-side via Google API
        - Required field in CustomSignupForm
    """
    form_class = core_forms.CustomSignupForm
    template_name = 'account/signup.html'

    def get_success_url(self):
        """Redirect to dashboard after successful signup."""
        return reverse_lazy('core:main_dashboard')


def rate_limit_exceeded(request, exception=None):
    """Handle 429 Too Many Attempts errors."""
    return render(request, '429.html', status=429)


@require_POST
def google_one_tap_callback(request):
    # Purpose: Verify Google One Tap JWT credential, find/create user, return redirect URL
    from google.oauth2 import id_token
    from google.auth.transport import requests as google_requests
    from allauth.socialaccount.models import SocialApp, SocialAccount
    from allauth.account.models import EmailAddress
    from django.contrib.auth import login as auth_login
    from django.conf import settings as django_settings

    credential = request.POST.get('credential', '').strip()
    if not credential:
        return JsonResponse({'error': 'missing credential'}, status=400)

    try:
        app = SocialApp.objects.get(provider='google')
        idinfo = id_token.verify_oauth2_token(
            credential, google_requests.Request(), app.client_id
        )
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)

    google_sub = idinfo['sub']
    email = idinfo.get('email', '')
    first_name = idinfo.get('given_name', '')
    last_name = idinfo.get('family_name', '')

    try:
        social = SocialAccount.objects.select_related('user').get(
            provider='google', uid=google_sub
        )
        user = social.user
    except SocialAccount.DoesNotExist:
        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            base = email.split('@')[0][:8].lower()
            suffix = secrets.token_hex(2)
            username = f"{base}{suffix}"[:12]
            user = User.objects.create_user(
                username=username,
                email=email,
                first_name=first_name,
                last_name=last_name,
            )
            user.set_unusable_password()
            user.save()
            EmailAddress.objects.get_or_create(
                user=user, email=email,
                defaults={'verified': True, 'primary': True}
            )
        SocialAccount.objects.create(
            user=user, provider='google', uid=google_sub, extra_data=idinfo
        )

    auth_login(request, user,
               backend='allauth.account.auth_backends.AuthenticationBackend')

    # Return to the page the user was on (e.g. driver application) when safe
    from django.utils.http import url_has_allowed_host_and_scheme
    next_url = (request.POST.get('next') or '').strip()
    if not (next_url and url_has_allowed_host_and_scheme(
            next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure())):
        next_url = django_settings.LOGIN_REDIRECT_URL
    return JsonResponse({'success': True, 'redirect': next_url})
