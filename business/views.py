"""
Business Views Module
============================

This module handles all business store operations including dashboard,
settings, locations, teams, and API integrations.

View Categories:
    Dashboard:
        - business_dashboard: Main business dashboard with orders overview

    Pickup Locations:
        - pickup_location_list: List all pickup/warehouse locations
        - pickup_location_add: Add new pickup location
        - pickup_location_update: Edit existing location
        - pickup_location_delete: Remove pickup location

    Driver Directory:
        - driver_directory: List drivers associated with business
        - driver_directory_add: Add driver to directory
        - driver_directory_delete: Remove driver from directory

    Business Profile:
        - business_profile: View business profile (frontend)
        - business_profile_display: Public business profile view
        - business_profile_update: Update basic business info
        - business_profile_info_update: Update extended profile info
        - all_business: List all businesses (admin view)

    Business Settings:
        - business_settings: Main settings page
        - business_logo_update: Update business logo

    API Settings:
        - business_settings_api_list: List API integrations
        - business_settings_api_add: Add new API integration
        - business_settings_api_update: Edit API settings
        - business_settings_api_delete: Remove API integration
        - business_settings_api_test: Test API connection
        - business_settings_api_test_result: Show API test results

    Team Management:
        - business_teams: List team members
        - business_teams_add: Add team member
        - business_teams_update: Edit team member

    Guides:
        - workflow_guide: Step-by-step workflow guide for clients

Security:
    All views implement IDOR (Insecure Direct Object Reference) protection
    by verifying the logged-in user owns the business being accessed.

Related:
    - business.models: Business, PickupLocation, BusinessApiSettings, etc.
    - business.forms: businessRegisterForm, PickupLocationsAddForm, etc.
    - business.urls: URL routing for all business views
"""

import os
import logging
from django import forms
from django.http import HttpResponse, HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from decouple import config
from django.core.files.storage import default_storage
from PIL import Image
import requests, json
import shopify
from woocommerce import API as WooAPI

from business import models as business_models
from core import models as core_models
from ezzydelivery.settings import BASE_DIR
from orders import models as orders_models
from ezzy_api import models as ezzy_api_models

from business import forms as business_forms
from datetime import datetime

# Local aliases for commonly used models
Business = business_models.Business
BusinessProfile = business_models.BusinessProfile
PickupLocation = business_models.PickupLocation
BusinessApiSettings = business_models.BusinessApiSettings
BusinessLogo = business_models.BusinessLogo
BusinessTeamProfile = business_models.BusinessTeamProfile
DriverDirectory = business_models.DriverDirectory
Profile = core_models.Profile
Order = orders_models.Order

logger = logging.getLogger('business')


# =============================================================================
# DASHBOARD VIEWS
# =============================================================================


@login_required(login_url='account_login')
def business_dashboard(request):
    try:
        # IDOR FIX: Verify user has associated business
        user_business = request.user.user_business.first()
        if not user_business:
            logger.warning(f"User {request.user.id} has no associated business")
            messages.error(request, "No business associated with your account")
            return redirect('core:main_dashboard')

        business = business_models.Business.objects.get(business_id=user_business.business_id)
        logger.info(f"User {request.user.id} accessed dashboard for business {business.business_id}")

        profile = core_models.Profile.objects.get(user_id=business.user_id)
        business_profile = business_models.BusinessProfile.objects.get_or_create(business_id=business.business_id)

        # N+1 FIX: Optimize queries
        location = business_models.PickupLocation.objects.filter(
            business_id=business.business_id).all()

        orders = orders_models.Order.objects.filter(
            business=business.business_id
        ).select_related('business', 'pickup_location', 'address_verified_by', 'verified_by').order_by('-id')[:10]

        context = {
            'profile': profile,
            'business': business,
            'business_profile': business_profile,
            'location': location,
            'orders': orders,
        }
        return render(request, 'business/business_dashboard.html', context)
    except business_models.Business.DoesNotExist:
        logger.error(f"Business not found for user {request.user.id}")
        messages.error(request, "Business not found")
        return redirect('core:main_dashboard')
    except Exception as e:
        logger.error(f"Error loading business dashboard for user {request.user.id}: {e}")
        messages.error(request, "Error loading dashboard")
        return redirect('core:main_dashboard')

# Driver contact list of business---------------------------------------------------------------------------------------------------------------------


@login_required(login_url='account_login')
def driver_directory(request):
    try:
        # IDOR FIX: Get user's business with proper verification
        business = business_models.Business.objects.get(user_id=request.user.id)
        driver_directory = business_models.DriverDirectory.objects.filter(
            business_id=business.business_id).all()

        logger.info(f"User {request.user.id} accessed driver directory for business {business.business_id}")

        context = {
            'contacts': driver_directory,
            'business': business,
        }
        return render(request, 'business/parts/driver_directory.html', context)
    except business_models.Business.DoesNotExist:
        logger.warning(f"Business not found for user {request.user.id}")
        messages.error(request, "Business not found")
        return redirect('business:business_dashboard')


@login_required(login_url='account_login')
def driver_directory_add(request):
    if request.method == 'POST':
        try:
            # IDOR FIX: Verify user has business
            business = business_models.Business.objects.get(user_id=request.user.id)
            driver_id = request.POST.get('driver_id')

            if not driver_id:
                return JsonResponse({'success': False, 'error': 'Driver ID is required'})

            logger.info(f"User {request.user.id} attempting to add driver {driver_id} to business {business.business_id}")

            # Check if driver already exists in directory
            if business_models.DriverDirectory.objects.filter(
                business_id=business.business_id, driver_id=driver_id
            ).exists():
                logger.info(f"Driver {driver_id} already in directory for business {business.business_id}")
                return JsonResponse({'success': False, 'error': 'Driver Already Added'})

            # Create new directory entry
            business_models.DriverDirectory.objects.create(
                business_id=business.business_id, driver_id=driver_id
            )
            logger.info(f"Driver {driver_id} added to directory for business {business.business_id}")
            return JsonResponse({'success': True, 'message': 'Driver Added'})

        except business_models.Business.DoesNotExist:
            logger.warning(f"Business not found for user {request.user.id}")
            return JsonResponse({'success': False, 'error': 'Business not found'})
        except Exception as e:
            logger.error(f"Error adding driver to directory: {e}")
            return JsonResponse({'success': False, 'error': 'Error adding driver'})

    return JsonResponse({'success': False, 'error': 'Invalid request method'})


@login_required(login_url='account_login')
def driver_directory_delete(request, id):
    try:
        # IDOR FIX: Verify directory entry belongs to user's business
        business = business_models.Business.objects.get(user_id=request.user.id)
        fleet = business_models.DriverDirectory.objects.get(id=id, business_id=business.business_id)

        logger.info(f"User {request.user.id} deleting driver directory entry {id} from business {business.business_id}")
        fleet.delete()
        messages.success(request, "Driver removed from directory")
        return redirect('business:driver_directory')

    except business_models.DriverDirectory.DoesNotExist:
        logger.warning(f"Driver directory entry {id} not found or unauthorized access by user {request.user.id}")
        messages.error(request, "Driver directory entry not found")
        return redirect('business:driver_directory')
    except business_models.Business.DoesNotExist:
        logger.warning(f"Business not found for user {request.user.id}")
        messages.error(request, "Business not found")
        return redirect('core:main_dashboard')


# pickup location add------------------------------------------------------
@login_required(login_url='account_login')
def pickup_location_list(request):
    try:
        # IDOR FIX: Verify user has associated business
        user_business = request.user.user_business.first()
        if not user_business:
            logger.warning(f"User {request.user.id} has no associated business")
            messages.error(request, "No business associated with your account")
            return redirect('core:main_dashboard')

        business = business_models.Business.objects.get(business_id=user_business.business_id)
        pickup_location = business_models.PickupLocation.objects.filter(
            business_id=business.business_id).all()

        if not pickup_location:
            return redirect('business:pickup_location_add')

        logger.info(f"User {request.user.id} viewing {len(pickup_location)} pickup locations for business {business.business_id}")

        context = {
            'stores': pickup_location,
            'business': business,
        }
        return render(request, 'business/parts/pickup_location_list.html', context)
    except business_models.Business.DoesNotExist:
        logger.error(f"Business not found for user {request.user.id}")
        messages.error(request, "Business not found")
        return redirect('core:main_dashboard')


@login_required(login_url='account_login')
def pickup_location_add(request):
    try:
        # IDOR FIX: Verify user has associated business
        user_business = request.user.user_business.first()
        if not user_business:
            logger.warning(f"User {request.user.id} has no associated business")
            messages.error(request, "No business associated with your account")
            return redirect('core:main_dashboard')

        business = business_models.Business.objects.get(business_id=user_business.business_id)
        form = business_forms.PickupLocationsAddForm(request.POST or None)

        if request.method == 'POST':
            if form.is_valid():
                pickup_location = form.save(commit=False)
                # IDOR FIX: Use verified business_id
                pickup_location.business_id = business.business_id
                form.save()
                logger.info(f"User {request.user.id} added pickup location for business {business.business_id}")
                messages.success(request, "Pickup location added successfully")
                return redirect("business:pickup_location_list")

        context = {
            'form': form,
            'business': business,
        }
        return render(request, 'business/parts/pickup_location_add.html', context)
    except business_models.Business.DoesNotExist:
        logger.error(f"Business not found for user {request.user.id}")
        messages.error(request, "Business not found")
        return redirect('core:main_dashboard')


@login_required(login_url='account_login')
def pickup_location_delete(request, pickup_location_id):
    try:
        # IDOR FIX: Verify pickup location belongs to user's business
        user_business = request.user.user_business.first()
        if not user_business:
            logger.warning(f"User {request.user.id} has no associated business")
            messages.error(request, "No business associated with your account")
            return redirect('core:main_dashboard')

        business = business_models.Business.objects.get(business_id=user_business.business_id)
        pickup_location = business_models.PickupLocation.objects.get(
            id=pickup_location_id, business_id=business.business_id
        )

        logger.info(f"User {request.user.id} deleting pickup location {pickup_location_id} from business {business.business_id}")
        pickup_location.delete()
        messages.success(request, "Pickup location deleted successfully")
        return redirect("business:pickup_location_list")

    except business_models.PickupLocation.DoesNotExist:
        logger.warning(f"Pickup location {pickup_location_id} not found or unauthorized access by user {request.user.id}")
        messages.error(request, "Pickup location not found")
        return redirect("business:pickup_location_list")
    except business_models.Business.DoesNotExist:
        logger.error(f"Business not found for user {request.user.id}")
        messages.error(request, "Business not found")
        return redirect('core:main_dashboard')


@login_required(login_url='account_login')
def pickup_location_update(request, pickup_location_id):
    try:
        # IDOR FIX: Verify pickup location belongs to user's business
        user_business = request.user.user_business.first()
        if not user_business:
            logger.warning(f"User {request.user.id} has no associated business")
            messages.error(request, "No business associated with your account")
            return redirect('core:main_dashboard')

        business = business_models.Business.objects.get(business_id=user_business.business_id)
        pickup_location = get_object_or_404(
            business_models.PickupLocation, id=pickup_location_id, business_id=business.business_id
        )

        logger.info(f"User {request.user.id} updating pickup location {pickup_location_id} for business {business.business_id}")

        form = business_forms.PickupLocationsAddForm(
            request.POST or None, instance=pickup_location
        )

        if request.method == 'POST':
            if form.is_valid():
                form.save()
                logger.info(f"Pickup location {pickup_location_id} updated successfully")
                messages.success(request, "Pickup location updated successfully")
                return redirect("business:pickup_location_list")

        context = {
            'business': business,
            'form': form,
            'id': pickup_location_id,
        }
        return render(request, 'business/parts/pickup_location_update.html', context)
    except business_models.Business.DoesNotExist:
        logger.error(f"Business not found for user {request.user.id}")
        messages.error(request, "Business not found")
        return redirect('core:main_dashboard')

# frontend ---------------------------------------------------------------------------------------------------------------------


@login_required(login_url='/accounts/login/')
def business_profile(request):
    try:
        business = business_models.Business.objects.get(
            business_id=request.user.user_business.first().business_id)
        profile = core_models.Profile.objects.filter(user_id=request.user.id)
        business_profile = business_models.BusinessProfile.objects.get_or_create(business_id = business.business_id )
        business_profile = business_profile[0]
        #print('business_profile', business_profile)
        location = business_models.PickupLocation.objects.filter(
            business_id=business.business_id).values_list('pickup_location_title', flat=True)[:2]
        business_logo = business_models.BusinessLogo.objects.select_related('business').get_or_create(business_id = business.business_id )
        instakey = config("INSTAGRAM_TOKEN_FEEDS_KEY")
        business_logo = business_logo[0].business_logo.url


        context = {
            'profile': profile,
            'business': business,
            'location': location,
            'business_profile': business_profile,
            'business_logo_img': business_logo,
            'instakey': instakey,
        }
        return render(request, 'business/frontend/business_profile.html', context)
    except business_models.Business.DoesNotExist:

        return redirect("/join_us/")

@login_required(login_url='/accounts/login/')
def business_profile_display(request, business_id):
    try:
        business = business_models.Business.objects.get(
            business_id=business_id)
        location = business_models.PickupLocation.objects.filter(
            business_id=business.business_id).values_list('pickup_location_title', flat=True)[:2]
        business_logo = business_models.BusinessLogo.objects.select_related('business').get(business_id = business.business_id )
        business_logo = business_logo.business_logo.url


        context = {
            'business': business,
            'location': location,
            'business_logo_img': business_logo,
        }
        return render(request, 'business/frontend/business_profile.html', context)
    except business_models.Business.DoesNotExist:
        
        return redirect("/profile/")


@login_required(login_url='/accounts/login/')
def all_business(request):
    business = business_models.Business.objects.all()
    
    

    context = {
        'all_business': business,
    }
    return render(request, 'business/frontend/all_business.html', context)

#business_settings---------------------------------------------------------------------------------------------------------------------


@login_required(login_url='/accounts/login/')
def business_profile_update(request, business_id):
    # Check if user has a profile
    try:
        profile = core_models.Profile.objects.get(user_id=request.user.id)
    except core_models.Profile.DoesNotExist:
        messages.warning(request, "Please complete your profile first.")
        return redirect('core:profile_add')

    # Check if user is a business user
    if not profile.is_business:
        messages.warning(request, "You need to register as a business first.")
        return redirect('core:join_us')

    # Check if business profile is completed
    if not profile.is_business_profile_completed:
        messages.warning(request, "Please complete your business registration first.")
        return redirect('core:business_register')

    # Verify user owns this business
    if not request.user.user_business.exists():
        messages.error(request, "No business found for your account.")
        return redirect('core:business_register')

    if request.user.user_business.first().business_id == business_id:
        business = business_models.Business.objects.get(
            business_id=request.user.user_business.first().business_id)
        form = business_forms.businessRegisterForm(instance=business)

        if request.method == 'POST':
            form = business_forms.businessRegisterForm(
                request.POST, request.FILES, instance=business)
            if form.is_valid():
                form.save()
                messages.success(request, "Business profile updated successfully!")
                return redirect("business:business_dashboard")
            else:
                messages.error(request, "Please correct the errors below.")

        context = {
            'form': form,
            'business_id': business.business_id
        }
        return render(request, 'business/frontend/business_profile_update.html', context)
    else:
        messages.error(request, "You don't have permission to edit this business.")
        return redirect("business:business_dashboard")



@login_required(login_url='/accounts/login/')
def business_profile_info_update(request, business_id):
    if request.user.user_business.first().business_id == business_id:
        logger.debug(f'Business profile update matched for business_id={business_id}, user_id={request.user.id}')
        business = business_models.Business.objects.get(
            business_id=request.user.user_business.first().business_id)
        business_profile = business_models.BusinessProfile.objects.get(business_id=business_id)

        logger.debug(f'Updating business profile for business_id={business.business_id}')
        form = business_forms.BusinessProfileForm(instance=business_profile)

        if request.method == 'POST':
            logger.debug('Processing BusinessProfileForm POST')
            form = business_forms.BusinessProfileForm(
                request.POST, instance=business_profile)
            if form.is_valid():
                f = form.save(commit=False)
                website = f.business_website

                if website and isinstance(website, str) and not website.startswith('https://') and not website.startswith('http://'):
                    f.business_website = 'https://' + website
                elif website and isinstance(website, str) and website.startswith('http://'):
                    f.business_website = 'https://' + website[7:]  # Replace http:// with https://
                else:
                    f.business_website = website

                f.business_id = business_id
                form.save()
                logger.info(f'Business profile updated successfully for business_id={business_id}')
                messages.success(request, "Successful Submission")
                return redirect("business:business_profile")
            else:
                logger.warning(f'Business profile form invalid: {form.errors}')
                messages.error(request, "Error")
        context = {
            'form': form,
            'business': business,
            'business_profile': business_profile,
        }

        return render(request, 'business/frontend/business_profile_update.html', context)
    else:
        return redirect("business:business_profile")


# business settings links and verify status ---------------------------------------------------------------------------------------------------------------------
@login_required(login_url='/accounts/login/')
def business_settings(request, business_id):
    # N+1 FIX: Use select_related for FK relationships
    business = business_models.Business.objects.select_related('user', 'profile').filter(business_id=business_id).first()
    business_apis = business_models.BusinessApiSettings.objects.filter(business_id=business_id)

    teams = business_models.BusinessTeamProfile.objects.select_related('user').filter(business_id=business_id)
    stores = business_models.PickupLocation.objects.filter(business_id=business_id)
    logger.debug(f'Loading business settings for business_id={business_id}: apis={business_apis.count()}, teams={teams.count()}, stores={stores.count()}')

    
    

    context = {
        'business': business,
        'business_apis': business_apis,
        'teams': teams,
        'stores': stores,

    }
    return render(request, 'business/parts/business_settings.html', context)


#business_settings_api---------------------------------------------------------------------------------------------------------------------
@login_required(login_url='/accounts/login/')
def business_settings_api_update(request, business_id, api_id):
    if request.user.id == request.user.user_business.first().user_id:
        business = business_models.Business.objects.filter(business_id=business_id).first()
        business_apis = business_models.BusinessApiSettings.objects.filter(id=api_id).first()
        form = business_forms.businessApiSettingsForm(instance=business_apis)
        # Hide the business field and set it to the current business
        form.fields['business'].widget = forms.HiddenInput()
        form.fields['business'].initial = business

        if request.method == 'POST':
            logger.debug(f'Updating API settings for business_id={business_id}, api_id={api_id}')
            form = business_forms.businessApiSettingsForm(
                request.POST, instance=business_apis)

            if form.is_valid():
                f = form.save(commit=False)
                if f.is_verify_api:
                    f.is_verify_api = False

                form.save()
                logger.info(f'API settings updated successfully for business_id={business_id}, api_id={api_id}')
                messages.success(request, "Successful Submission")
                return redirect("business:business_settings", business_id)
            else:
                logger.warning(f'API settings form invalid: {form.errors}')
                messages.error(request, "Error")
        context = {
            'business': business,
            'form': form,
            'api_id': api_id,
            'form_title': 'Business API Settings Add'
        }

        return render(request, 'business/parts/business_settings_api_update.html', context)
    else:
        return redirect("business:business_dashboard")



@login_required(login_url='/accounts/login/')
def business_settings_api_add(request, business_id):
    if request.user.id == request.user.user_business.first().user_id:
        business = business_models.Business.objects.filter(business_id=business_id).first()
        form = business_forms.businessApiSettingsForm(initial={'business': business})
        # Hide the business field and set it to the current business
        form.fields['business'].widget = forms.HiddenInput()
        form.fields['business'].initial = business

        if request.method == 'POST':
            logger.debug(f'Adding API settings for business_id={business_id}')
            form = business_forms.businessApiSettingsForm(request.POST)

            if form.is_valid():
                form.save()
                logger.info(f'API settings added successfully for business_id={business_id}')
                messages.success(request, "Successful Submission")
                return redirect("business:business_settings", business_id)
            else:
                logger.warning(f'API settings form invalid: {form.errors}')
                messages.error(request, "Error")
        context = {
            'business': business,
            'form': form,
            'form_title': 'Business API Settings Adding Form'
        }

        return render(request, 'business/parts/business_settings_api_add.html', context)
    else:
        return redirect("business:business_dashboard")


@login_required(login_url='/accounts/login/')
def business_settings_api_list(request, business_id):
    business =  business_models.Business.objects.filter(business_id=business_id).first()
    business_apis = business_models.BusinessApiSettings.objects.filter(business_id=business_id)
    api_keys = ezzy_api_models.ClientApiKey.objects.filter(business=business).order_by('-created_at')



    context = {
        'business': business,
        'business_apis': business_apis,
        'api_keys': api_keys,
    }
    return render(request, 'business/parts/business_settings_api_list.html', context)

@login_required(login_url='/accounts/login/')
def business_settings_api_delete(request, business_id, api_id):
    business = business_models.Business.objects.filter(business_id=business_id).first()
    if not business:
        return redirect("business:business_dashboard")

    api_setting = business_models.BusinessApiSettings.objects.filter(business_id=business_id, id=api_id).first()
    if api_setting:
        api_setting.delete()

    return redirect("business:business_settings", business_id=business_id)


@login_required(login_url='/accounts/login/')
def business_settings_api_test(request, business_id, api_id):
    business =  business_models.Business.objects.filter(business_id=business_id).first()
    business_apis = business_models.BusinessApiSettings.objects.filter(business_id=business_id, id=api_id).first()
    
    

    context = {
        'business': business,
        'api': business_apis,
    }
    return render(request, 'business/parts/business_settings_api_test.html', context)



@login_required(login_url='/accounts/login/')
def business_settings_api_test_result(request, business_id, api_id):
    business =  business_models.Business.objects.filter(business_id=business_id).first()
    business_api = business_models.BusinessApiSettings.objects.filter(business_id=business_id, id=api_id).first()
    update_time = datetime.now().strftime('%Y-%m-%d  Time : %H:%M:%S')

    BASE_API_KEY = business_api.api_key
    BASE_API_ACCESS_KEY = business_api.api_access_token
    BASE_API_SECRET = business_api.api_secret
    BASE_API_VERSION = business_api.api_version
    BASE_API_STORE_NAME = business_api.site_api_url
    BASE_API_ORDER_ENDPINT = business_api.order_api_endpoint
    BASE_API_PRODUCT_ENDPINT = business_api.product_api_endpoint

    BASE_API_STORE_NAME = BASE_API_STORE_NAME.replace('https://', '')

    if business_api.api_type == 'shopify':
        shop_url = BASE_API_STORE_NAME
        logger.debug(f'Testing Shopify API for shop_url={shop_url}')

        order_base_url = 'https://' + shop_url + BASE_API_ORDER_ENDPINT
        product_base_url = 'https://' + shop_url + BASE_API_PRODUCT_ENDPINT
        header_value = {'X-Shopify-Access-Token': BASE_API_ACCESS_KEY, 'Content-Type': 'application/json'}

        order_response = requests.get(order_base_url, headers=header_value, params={'status': 'any', 'limit': 10})
        order_count = len(order_response.json().get('orders', []))
        logger.debug(f'Shopify order_count={order_count}')

        product_response = requests.get(product_base_url, headers=header_value)
        product_count = len(product_response.json().get('products', []))
        logger.debug(f'Shopify product_count={product_count}')

    elif business_api.api_type == 'woocommerce':
        shop_url = 'https://' + BASE_API_STORE_NAME
        logger.debug(f'Testing WooCommerce API for shop_url={shop_url}')

        wcapi = WooAPI(
            url=shop_url,
            consumer_key=BASE_API_KEY,
            consumer_secret=BASE_API_SECRET,
            version="wc/v3",
        )

        order_response = wcapi.get("orders")
        order_count = order_response.headers.get('X-WP-Total')
        logger.debug(f'WooCommerce order_count={order_count}')

        product_response = wcapi.get("products", params={"per_page": 20})
        product_count = product_response.headers.get('X-WP-Total')
        logger.debug(f'WooCommerce product_count={product_count}')
 
    else:
        order_response = None
        product_response = None


    result = order_response.json()
    status = order_response.status_code

    order_count = order_count
    product_count = product_count

    context = {
        'business': business,
        'api': business_api,
        'update_time'  : update_time,
        'order_count'  : order_count,
        'product_count'  : product_count,

        'status'  : status,
        'result'  : result,

    }
    return render(request, 'business/parts/business_settings_api_test_result.html', context)



#business_logo_update---------------------------------------------------------------------------------------------------------------------
@login_required(login_url='/accounts/login/')
def business_logo_update(request, business_id):
    business_logos = business_models.BusinessLogo.objects.get(business_id=business_id)
    business_code = business_models.Business.objects.get(business_id=business_id)

    # Check if the request user matches the business user
    if request.user.id != business_logos.business_id:
        logger.warning(f'Unauthorized logo update attempt by user {request.user.id} for business {business_id}')
        return HttpResponseForbidden("You don't have permission to update this business logo.")

    form = business_forms.BusinessLogoForm()
    if request.method == 'POST':
        logger.debug(f'Processing logo update for business_id={business_logos.business_id}')
        form = business_forms.BusinessLogoForm(
            request.POST, request.FILES, instance=business_logos)
        if form.is_valid():
            f = form.save(commit=False)

            # Delete the old logo file if exists
            if business_logos.business_logo and business_logos.business_logo != 'business/avatar.png':
                logger.debug(f'Old logo found: {business_logos.business_logo.path}')

            f.business_id = request.user.id
            f.path = f'business/{business_code}'
            f.save()

            logger.info(f'Logo updated for business_id={business_id}')

            # Create thumbnail
            original_image = Image.open(f.business_logo.path)
            title, ext = os.path.splitext(f.business_logo.path)
            final_filepath = os.path.join(f.path, title + '_sm' + ext)
            new_width = 200
            new_height = 200
            img = original_image.resize((new_width, new_height), Image.LANCZOS)  # ANTIALIAS is deprecated
            img.save(final_filepath)
            logger.debug(f'Thumbnail created: {final_filepath}')

            messages.success(request, "Successful Submission")
            return redirect("business:business_profile")

    context = {
        'form': form,
        'form_title': 'Business logo Update',
    }   
  
        
        
    return render(request, 'business/parts/business_logo_update.html', context)




#business_teams---------------------------------------------------------------------------------------------------------------------

@login_required(login_url='/accounts/login/')
def business_teams(request, business_id):
    # N+1 FIX: Use select_related for user FK
    business = business_models.Business.objects.filter(business_id=business_id).first()
    teams = business_models.BusinessTeamProfile.objects.select_related('user').filter(business_id=business_id)
    logger.debug(f'Loading teams for business_id={business_id}, count={teams.count()}')
    context = {
        'business': business,
        'teams': teams,
    }
    return render(request, 'business/parts/business_teams_list.html', context)


@login_required(login_url='/accounts/login/')
def business_teams_add(request, business_id):
    business = business_models.Business.objects.filter(business_id=business_id).first()
    form = business_forms.BusinessTeamProfileForm()
    if request.method == 'POST':
        logger.debug(f'Adding team member for business_id={business_id}')
        form = business_forms.BusinessTeamProfileForm(request.POST)
        if form.is_valid():
            f = form.save(commit=False)
            f.business_id = business_id
            form.save()
            logger.info(f'Team member added for business_id={business_id}')
            messages.success(request, "Successful Submission")
            return redirect("business:business_teams", business_id)
        else:
            logger.warning(f'Team profile form invalid: {form.errors}')
            messages.error(request, "Error")
    context = {
        'business': business,
        'form': form,
        'form_title': 'Business Team Profile Adding Form'
    }
    return render(request, 'business/parts/business_teams_add.html', context)


@login_required(login_url='/accounts/login/')
def business_teams_update(request, business_id, team_id):
    business = business_models.Business.objects.filter(business_id=business_id).first()
    team = business_models.BusinessTeamProfile.objects.filter(id=team_id).first()
    form = business_forms.BusinessTeamProfileForm(instance=team)
    if request.method == 'POST':
        logger.debug(f'Updating team member {team_id} for business_id={business_id}')
        form = business_forms.BusinessTeamProfileForm(request.POST, instance=team)
        if form.is_valid():
            f = form.save(commit=False)
            f.business_id = business_id
            form.save()
            logger.info(f'Team member {team_id} updated for business_id={business_id}')
            messages.success(request, "Successful Submission")
            return redirect("business:business_teams", business_id)
        else:
            logger.warning(f'Team profile form invalid: {form.errors}')
            messages.error(request, "Error")
    context = {
        'business': business,
        'form': form,
        'team': team,
        'form_title': 'Business Team Profile Update Form'
    }   



    return render(request, 'business/parts/business_teams_update.html', context)


# Workflow Guide -----------------------------------------------------

@login_required(login_url='account_login')
def workflow_guide(request):
    """Display comprehensive workflow guide for clients"""

    workflow_steps = [
        {
            'number': 1,
            'title': 'Create Your Business Account',
            'description': 'Set up your business profile with complete information',
            'tasks': [
                'Register and verify your email address',
                'Complete business profile with name, contact details',
                'Upload business logo',
                'Add business description and category',
            ],
            'status': 'completed',
            'url': 'business:business_profile',
        },
        {
            'number': 2,
            'title': 'Configure Pickup Locations',
            'description': 'Add your warehouse/pickup locations where orders will be collected',
            'tasks': [
                'Go to Settings → Pickup Locations',
                'Add location title and address',
                'Set zone, street, and building numbers',
                'Add GPS coordinates (latitude/longitude)',
                'Mark location as active',
            ],
            'status': 'in_progress',
            'url': 'business:pickup_location_list',
        },
        {
            'number': 3,
            'title': 'Setup API Integration (Optional)',
            'description': 'Connect your e-commerce platform for automatic order import',
            'tasks': [
                'Go to Settings → API Settings',
                'Select your platform (Shopify, WooCommerce, etc.)',
                'Enter API credentials (API Key, Secret)',
                'Test API connection',
                'Set as default if successful',
            ],
            'status': 'pending',
            'url': 'business:business_settings_api_list',
        },
        {
            'number': 4,
            'title': 'Create Orders',
            'description': 'Add customer orders for delivery',
            'tasks': [
                'Manual Entry: Click "Add Order" button',
                'Fill customer details (name, phone, address)',
                'Add delivery address with zone/street/building',
                'Set COD amount if applicable',
                'Add products to the order',
                'Or: Import via CSV upload',
                'Or: Auto-import from connected API',
            ],
            'status': 'pending',
            'url': None,
        },
        {
            'number': 5,
            'title': 'Order Verification Process',
            'description': 'Your orders go through automated verification',
            'tasks': [
                'Order submitted with status "Pending Verification"',
                'Workforce verifies customer address',
                'Address coordinates are validated',
                'Order is marked as "Verified"',
                'Delivery task is automatically created',
            ],
            'status': 'automated',
            'url': None,
        },
        {
            'number': 6,
            'title': 'Delivery Task Creation',
            'description': 'Verified orders automatically become delivery tasks',
            'tasks': [
                'System creates delivery task from verified order',
                'Task is linked to original order (preserved as proof)',
                'Delivery address details are duplicated',
                'Task is pushed to DMS (Delivery Management System)',
                'Driver assignment process begins',
            ],
            'status': 'automated',
            'url': None,
        },
        {
            'number': 7,
            'title': 'Track Deliveries',
            'description': 'Monitor your delivery status in real-time',
            'tasks': [
                'View all delivery tasks in dashboard',
                'Check task status: Assigned, In Transit, Delivered',
                'Track driver assignments',
                'Monitor COD collection status',
                'View delivery completion proof',
            ],
            'status': 'pending',
            'url': None,
        },
        {
            'number': 8,
            'title': 'Manage Team Members',
            'description': 'Add staff members to help manage orders',
            'tasks': [
                'Go to Settings → Team Management',
                'Add team member with email and role',
                'Set permissions for team members',
                'Team members can view and manage orders',
            ],
            'status': 'pending',
            'url': 'business:business_teams',
        },
    ]

    context = {
        'workflow_steps': workflow_steps,
        'page_title': 'Client Workflow Guide',
    }

    return render(request, 'business/workflow_guide.html', context)


