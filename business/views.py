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
from django.urls import reverse
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from core.decorators import business_required
from decouple import config
from django.core.files.storage import default_storage
from PIL import Image
import requests, json
import shopify
from woocommerce import API as WooAPI

from django.db.models import Sum, Q

from business import models as business_models
from core import models as core_models
from delivery import models as delivery_models
from fleet import models as fleet_models
from ezzydelivery.settings import BASE_DIR
from orders import models as orders_models
from ezzy_api import models as ezzy_api_models

from business import forms as business_forms
from datetime import datetime
from core.seo import SEOMetadata
from core.context_processors import get_cached_profile, get_cached_business

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
@business_required
def business_dashboard(request):
    try:
        # IDOR FIX: Verify user has associated business (using cached helper)
        business = get_cached_business(request)
        if not business:
            logger.warning(f"User {request.user.id} has no associated business")
            messages.error(request, "No business associated with your account")
            return redirect('core:main_dashboard')
        logger.info(f"User {request.user.id} accessed dashboard for business {business.business_id}")

        profile = get_cached_profile(request)
        if not profile:
            profile = core_models.Profile.objects.filter(user_id=business.user_id).first()
        business_profile, _created = business_models.BusinessProfile.objects.get_or_create(business_id=business.business_id)

        # N+1 FIX: Optimize queries
        location = business_models.PickupLocation.objects.filter(
            business_id=business.business_id).all()

        orders = orders_models.Order.objects.filter(
            business=business.business_id
        ).select_related('business', 'pickup_location', 'address_verified_by', 'verified_by').order_by('-id')[:10]

        # Calculate real statistics
        all_orders = orders_models.Order.objects.filter(business=business.business_id)
        from datetime import date
        today = date.today()

        # Total orders count
        total_orders = all_orders.count()

        # Delivered orders (order_status synced from delivery task via signal)
        delivered_count = all_orders.filter(
            order_status__in=['delivered', 'fulfilled']
        ).count()

        # COD calculations
        cod_amount_total = all_orders.aggregate(total=Sum('cod_amount'))['total'] or 0

        # COD collected (from delivered/fulfilled orders)
        cod_collected = all_orders.filter(
            order_status__in=['delivered', 'fulfilled']
        ).aggregate(total=Sum('cod_amount'))['total'] or 0

        # Pending orders (active orders not yet delivered or cancelled)
        pending_count = all_orders.exclude(
            order_status__in=['delivered', 'fulfilled', 'cancelled']
        ).count()

        # Get delivery tasks for this business
        delivery_tasks = delivery_models.DeliveryTask.objects.filter(business=business.business_id)

        # Follow up required (failed, rejected, or non-reachable delivery tasks)
        followup_count = delivery_tasks.filter(
            Q(dl_task_status__in=['failed', 'rejected', 'non_reachable'])
        ).exclude(
            dl_task_status_client__in=['2', '9']
        ).count()

        # Today's pending orders (latest 5)
        todays_pending_orders = all_orders.filter(
            order_date=today
        ).exclude(
            order_status__in=['delivered', 'fulfilled', 'cancelled']
        ).select_related('pickup_location').order_by('-id')[:5]

        # Today's delivered orders (latest 5)
        todays_delivered_orders = all_orders.filter(
            order_date=today,
            order_status__in=['delivered', 'fulfilled']
        ).select_related('pickup_location').order_by('-id')[:5]

        # Failed/Follow up orders (latest 5) - via delivery tasks with bad status
        followup_task_order_ids = delivery_tasks.filter(
            dl_task_status__in=['failed', 'rejected', 'non_reachable']
        ).exclude(
            dl_task_status_client__in=['2', '9']
        ).values_list('order_id', flat=True)[:5]
        followup_orders = all_orders.filter(
            id__in=followup_task_order_ids
        ).select_related('pickup_location').order_by('-id')

        # Team statistics - Fix: Use aggregates to reduce queries from 4 to 2
        from django.db.models import Count, Case, When, IntegerField

        team_stats = business_models.BusinessTeamProfile.objects.filter(
            business_id=business.business_id
        ).aggregate(
            total=Count('id'),
            active=Count(Case(When(team_status='active', then=1), output_field=IntegerField())),
            pending=Count(Case(When(team_status='pending', then=1), output_field=IntegerField())),
        )

        total_team_members = team_stats['total']
        active_team_members = team_stats['active']
        pending_team_members = team_stats['pending']

        # Recent team members (latest 3)
        recent_team_members = business_models.BusinessTeamProfile.objects.filter(
            business_id=business.business_id
        ).select_related('user').order_by('-created_at')[:3]

        # Check if user has multiple businesses (for business switcher)
        user_businesses = get_all_user_businesses(request.user)
        show_business_switcher = len(user_businesses) > 1

        is_business_owner = business.user_id == request.user.id if business.user_id else False

        context = {
            'profile': profile,
            'business': business,
            'business_profile': business_profile,
            'location': location,
            'orders': orders,
            # Stats
            'total_orders': total_orders,
            'delivered_count': delivered_count,
            'cod_amount_total': cod_amount_total,
            'cod_collected': cod_collected,
            'pending_count': pending_count,
            'followup_count': followup_count,
            # Today's orders lists
            'todays_pending_orders': todays_pending_orders,
            'todays_delivered_orders': todays_delivered_orders,
            'followup_orders': followup_orders,
            # Team stats
            'total_team_members': total_team_members,
            'active_team_members': active_team_members,
            'pending_team_members': pending_team_members,
            'recent_team_members': recent_team_members,
            # Business switcher
            'show_business_switcher': show_business_switcher,
            'user_businesses': user_businesses,
            # Permissions
            'is_business_owner': is_business_owner,
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
@business_required
def driver_directory(request):
    # IDOR FIX: Get user's business with proper verification (use cached)
    business = get_cached_business(request)
    if not business:
        logger.warning(f"Business not found for user {request.user.id}")
        messages.error(request, "Business not found")
        return redirect('business:business_dashboard')

    driver_directory = business_models.DriverDirectory.objects.filter(
        business_id=business.business_id).all()

    logger.info(f"User {request.user.id} accessed driver directory for business {business.business_id}")

    context = {
        'contacts': driver_directory,
        'business': business,
    }
    return render(request, 'business/parts/driver_directory.html', context)


@login_required(login_url='account_login')
@business_required
def driver_directory_add(request):
    """
    Add a driver to the business directory (AJAX endpoint).

    Returns proper JSON responses with appropriate HTTP status codes:
    - 200: Success
    - 400: Validation error (missing driver_id, driver already exists)
    - 404: Business not found
    - 405: Invalid request method
    - 500: Server error
    """
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Invalid request method'}, status=405)

    try:
        # IDOR FIX: Verify user has business (use cached)
        business = get_cached_business(request)
        if not business:
            logger.warning(f"Business not found for user {request.user.id}")
            return JsonResponse({'success': False, 'error': 'Business not found'}, status=404)

        driver_id = request.POST.get('driver_id')

        if not driver_id:
            return JsonResponse({'success': False, 'error': 'Driver ID is required'}, status=400)

        # Validate driver_id is a valid integer
        try:
            driver_id = int(driver_id)
        except (ValueError, TypeError):
            return JsonResponse({'success': False, 'error': 'Invalid driver ID format'}, status=400)

        logger.info(f"User {request.user.id} attempting to add driver {driver_id} to business {business.business_id}")

        # Check if driver already exists in directory
        if business_models.DriverDirectory.objects.filter(
            business_id=business.business_id, driver_id=driver_id
        ).exists():
            logger.info(f"Driver {driver_id} already in directory for business {business.business_id}")
            return JsonResponse({'success': False, 'error': 'Driver already added'}, status=400)

        # Create new directory entry
        business_models.DriverDirectory.objects.create(
            business_id=business.business_id, driver_id=driver_id
        )
        logger.info(f"Driver {driver_id} added to directory for business {business.business_id}")
        return JsonResponse({'success': True, 'message': 'Driver added successfully'})

    except Exception as e:
        logger.error(f"Error adding driver to directory: {e}")
        return JsonResponse({'success': False, 'error': 'Server error'}, status=500)


@login_required(login_url='account_login')
@business_required
def driver_directory_delete(request, id):
    # IDOR FIX: Verify directory entry belongs to user's business (use cached)
    business = get_cached_business(request)
    if not business:
        logger.warning(f"Business not found for user {request.user.id}")
        messages.error(request, "Business not found")
        return redirect('core:main_dashboard')

    try:
        fleet = business_models.DriverDirectory.objects.get(id=id, business_id=business.business_id)

        logger.info(f"User {request.user.id} deleting driver directory entry {id} from business {business.business_id}")
        fleet.delete()
        messages.success(request, "Driver removed from directory")
        return redirect('business:driver_directory')

    except business_models.DriverDirectory.DoesNotExist:
        logger.warning(f"Driver directory entry {id} not found or unauthorized access by user {request.user.id}")
        messages.error(request, "Driver directory entry not found")
        return redirect('business:driver_directory')


# pickup location add------------------------------------------------------
@login_required(login_url='account_login')
@business_required
def pickup_location_list(request):
    try:
        # IDOR FIX: Verify user has associated business (using cached helper)
        business = get_cached_business(request)
        if not business:
            logger.warning(f"User {request.user.id} has no associated business")
            messages.error(request, "No business associated with your account")
            return redirect('core:main_dashboard')

        # Get business's own pickup locations - show fulfillment stores first
        pickup_locations = business_models.PickupLocation.objects.filter(
            business_id=business.business_id
        ).order_by('-is_fulfilment_center', 'pickup_location_title')

        # If fulfillment service is enabled, also get warehouse locations
        warehouse_locations = []
        if business.fulfillment_service_enabled:
            from warehouse.models import SellerWarehouseLink, WarehouseLocation

            # Get all warehouses linked to this business
            warehouse_links = SellerWarehouseLink.objects.filter(
                business=business
            ).select_related('warehouse', 'default_location')

            # Get all active warehouse locations from linked warehouses
            for link in warehouse_links:
                wh_locs = WarehouseLocation.objects.filter(
                    warehouse=link.warehouse,
                    is_active=True
                ).select_related('warehouse')
                warehouse_locations.extend(wh_locs)

        # Combine locations: warehouse locations first, then regular pickup locations
        all_locations = list(pickup_locations)

        if not all_locations and not warehouse_locations:
            if business.fulfillment_service_enabled:
                return redirect('business:pickup_location_choose')
            return redirect('business:pickup_location_add')

        logger.info(f"User {request.user.id} viewing {len(all_locations)} pickup locations and {len(warehouse_locations)} warehouse locations for business {business.business_id}")

        context = {
            'stores': all_locations,
            'warehouse_locations': warehouse_locations,
            'business': business,
            'fulfillment_enabled': business.fulfillment_service_enabled,
        }
        return render(request, 'business/parts/pickup_location_list.html', context)
    except business_models.Business.DoesNotExist:
        logger.error(f"Business not found for user {request.user.id}")
        messages.error(request, "Business not found")
        return redirect('core:main_dashboard')


@login_required(login_url='account_login')
@business_required
def pickup_location_choose(request):
    """Choice page: add pickup location or link to fulfillment center."""
    business = get_cached_business(request)
    if not business:
        messages.error(request, "No business associated with your account")
        return redirect('core:main_dashboard')
    if not business.fulfillment_service_enabled:
        return redirect('business:pickup_location_add')
    return render(request, 'business/parts/pickup_location_choose.html', {
        'business': business,
    })


@login_required(login_url='account_login')
@business_required
def pickup_location_add(request):
    try:
        # IDOR FIX: Verify user has associated business (using cached helper)
        business = get_cached_business(request)
        if not business:
            logger.warning(f"User {request.user.id} has no associated business")
            messages.error(request, "No business associated with your account")
            return redirect('core:main_dashboard')

        form = business_forms.PickupLocationsAddForm(request.POST or None)

        if request.method == 'POST':
            if form.is_valid():
                pickup_location = form.save(commit=False)
                # IDOR FIX: Use verified business_id
                pickup_location.business_id = business.business_id
                pickup_location.save()
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
@business_required
def pickup_location_delete(request, pickup_location_id):
    try:
        # IDOR FIX: Verify pickup location belongs to user's business (using cached helper)
        business = get_cached_business(request)
        if not business:
            logger.warning(f"User {request.user.id} has no associated business")
            messages.error(request, "No business associated with your account")
            return redirect('core:main_dashboard')

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
@business_required
def pickup_location_update(request, pickup_location_id):
    try:
        # IDOR FIX: Verify pickup location belongs to user's business (using cached helper)
        business = get_cached_business(request)
        if not business:
            logger.warning(f"User {request.user.id} has no associated business")
            messages.error(request, "No business associated with your account")
            return redirect('core:main_dashboard')

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
@business_required
def business_profile(request):
    # Use cached business and profile to avoid duplicate queries
    business = get_cached_business(request)
    if not business:
        return redirect("/join_us/")

    profile = get_cached_profile(request)
    # Optimization: Use business already fetched or fetch with select_related if needed
    business_profile, created = business_models.BusinessProfile.objects.get_or_create(business=business)
    
    location = business_models.PickupLocation.objects.filter(
        business_id=business.business_id).values_list('pickup_location_title', flat=True)[:2]
    
    business_logo_obj, created = business_models.BusinessLogo.objects.get_or_create(business=business)
    instakey = config("INSTAGRAM_TOKEN_FEEDS_KEY", default="")
    business_logo = business_logo_obj.business_logo.url if business_logo_obj.business_logo else None

    context = {
        'profile': profile,
        'business': business,
        'location': location,
        'business_profile': business_profile,
        'business_logo_img': business_logo,
        'instakey': instakey,
    }
    return render(request, 'business/frontend/business_profile.html', context)

@login_required(login_url='/accounts/login/')
@business_required
def business_profile_display(request, business_id):
    try:
        business = business_models.Business.objects.select_related('profile', 'business_profile').get(
            business_id=business_id)
        location = business_models.PickupLocation.objects.filter(
            business_id=business.business_id).values_list('pickup_location_title', flat=True)[:2]
        
        business_logo_obj = business_models.BusinessLogo.objects.filter(business=business).first()
        business_logo = business_logo_obj.business_logo.url if business_logo_obj and business_logo_obj.business_logo else None
        
        business_profile = business.business_profile if hasattr(business, 'business_profile') else None

        # Dynamic SEO for business profile
        business_name = business.business_name or "Business"
        meta = SEOMetadata.get_page_meta(
            title=f"{business_name} | Qatar Store on EzzyDelivery",
            description=(
                f"View {business_name}'s profile on EzzyDelivery Qatar. "
                f"E-commerce store with same-day delivery available in Doha."
            )[:155],
        )

        context = {
            'seo': meta,
            'business': business,
            'location': location,
            'business_logo_img': business_logo,
            'business_profile': business_profile,
        }
        return render(request, 'business/frontend/business_profile.html', context)
    except business_models.Business.DoesNotExist:
        return redirect("/profile/")


@login_required(login_url='/accounts/login/')
@business_required
def all_business(request):
    business = business_models.Business.objects.select_related('profile', 'business_profile').prefetch_related('business_logo').all()

    # SEO metadata for business directory
    meta = SEOMetadata.get_page_meta(
        title="Business Directory Qatar | EzzyDelivery Partners",  # 52 chars
        description=(
            "Browse businesses using EzzyDelivery in Qatar. E-commerce stores, retailers & "
            "sellers across Doha offering same-day delivery through our network."
        ),  # 150 chars
    )

    context = {
        'seo': meta,
        'all_business': business,
    }
    return render(request, 'business/frontend/all_business.html', context)

#business_settings---------------------------------------------------------------------------------------------------------------------


@login_required(login_url='/accounts/login/')
@business_required
def business_profile_update(request, business_id):
    # Check if user has a profile (use cached)
    profile = get_cached_profile(request)
    if not profile:
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

    # Verify user owns this business (use cached)
    user_business = get_cached_business(request)
    if not user_business:
        messages.error(request, "No business found for your account.")
        return redirect('core:business_register')

    if user_business.business_id == business_id:
        business = user_business  # Already have the business object
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
@business_required
def business_profile_info_update(request, business_id):
    user_business = get_cached_business(request)
    if user_business and user_business.business_id == business_id:
        logger.debug(f'Business profile update matched for business_id={business_id}, user_id={request.user.id}')
        business = user_business  # Already have the business object
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
                f.save()
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
@business_required
def business_settings(request, business_id):
    # IDOR FIX: Verify user owns this business
    user_business = get_cached_business(request)
    if not user_business or user_business.business_id != business_id:
        messages.error(request, "You don't have permission to access this page.")
        return redirect('business:business_dashboard')

    # N+1 FIX: Use select_related for FK relationships
    business = business_models.Business.objects.select_related('user', 'profile').filter(business_id=business_id).first()
    business_apis = business_models.BusinessApiSettings.objects.filter(business_id=business_id)

    teams = business_models.BusinessTeamProfile.objects.select_related('user').filter(business_id=business_id)
    stores = business_models.PickupLocation.objects.filter(business_id=business_id)
    logger.debug(f'Loading business settings for business_id={business_id}: apis={business_apis.count()}, teams={teams.count()}, stores={stores.count()}')

    is_business_owner = business.user_id == request.user.id if business and business.user_id else False

    context = {
        'business': business,
        'business_apis': business_apis,
        'teams': teams,
        'stores': stores,
        'is_business_owner': is_business_owner,
    }
    return render(request, 'business/parts/business_settings.html', context)


#business_settings_api---------------------------------------------------------------------------------------------------------------------
@login_required(login_url='/accounts/login/')
@business_required
def business_settings_api_update(request, business_id, api_id):
    user_business = get_cached_business(request)
    if user_business and request.user.id == user_business.user_id:
        business = user_business if user_business.business_id == business_id else None
        if not business:
            return redirect('business:business_settings', business_id=user_business.business_id)
        business_apis = business_models.BusinessApiSettings.objects.filter(id=api_id, business=business).first()
        if not business_apis:
            messages.error(request, "API settings not found.")
            return redirect('business:business_settings', business_id=business_id)

        form = business_forms.businessApiSettingsForm(instance=business_apis)

        if request.method == 'POST':
            logger.debug(f'Updating API settings for business_id={business_id}, api_id={api_id}')
            form = business_forms.businessApiSettingsForm(
                request.POST, instance=business_apis)

            if form.is_valid():
                api_settings = form.save(commit=False)
                # Reset verification when settings change
                if api_settings.is_verify_api:
                    api_settings.is_verify_api = False
                # Ensure business is set (for security)
                api_settings.business = business
                api_settings.save()
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
@business_required
def business_settings_api_add(request, business_id):
    user_business = get_cached_business(request)
    if user_business and request.user.id == user_business.user_id:
        business = user_business if user_business.business_id == business_id else None
        if not business:
            return redirect('business:business_settings', business_id=user_business.business_id)
        form = business_forms.businessApiSettingsForm()

        if request.method == 'POST':
            logger.debug(f'Adding API settings for business_id={business_id}')
            form = business_forms.businessApiSettingsForm(request.POST)

            if form.is_valid():
                # Set business before saving (excluded from form for security)
                api_settings = form.save(commit=False)
                api_settings.business = business
                api_settings.save()
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
@business_required
def business_settings_api_list(request, business_id):
    # IDOR FIX: Verify user owns this business
    user_business = get_cached_business(request)
    if not user_business or user_business.business_id != business_id:
        messages.error(request, "You don't have permission to access this page.")
        return redirect('business:business_dashboard')

    business = user_business
    business_apis = business_models.BusinessApiSettings.objects.filter(business_id=business_id)
    api_keys = ezzy_api_models.ClientApiKey.objects.filter(business=business).order_by('-created_at')



    context = {
        'business': business,
        'business_apis': business_apis,
        'api_keys': api_keys,
    }
    return render(request, 'business/parts/business_settings_api_list.html', context)

@login_required(login_url='/accounts/login/')
@business_required
def business_settings_api_delete(request, business_id, api_id):
    # IDOR FIX: Verify user owns this business
    user_business = get_cached_business(request)
    if not user_business or user_business.business_id != business_id:
        messages.error(request, "You don't have permission to access this page.")
        return redirect('business:business_dashboard')

    business = user_business

    api_setting = business_models.BusinessApiSettings.objects.filter(business_id=business_id, id=api_id).first()
    if api_setting:
        api_setting.delete()

    return redirect("business:business_settings", business_id=business_id)


@login_required(login_url='/accounts/login/')
@business_required
def business_settings_api_test(request, business_id, api_id):
    # IDOR FIX: Verify user owns this business
    user_business = get_cached_business(request)
    if not user_business or user_business.business_id != business_id:
        messages.error(request, "You don't have permission to access this page.")
        return redirect('business:business_dashboard')

    business = user_business
    business_apis = business_models.BusinessApiSettings.objects.filter(business_id=business_id, id=api_id).first()
    
    

    context = {
        'business': business,
        'api': business_apis,
    }
    return render(request, 'business/parts/business_settings_api_test.html', context)



@login_required(login_url='/accounts/login/')
@business_required
def business_settings_api_test_result(request, business_id, api_id):
    # IDOR FIX: Verify user owns this business
    user_business = get_cached_business(request)
    if not user_business or user_business.business_id != business_id:
        messages.error(request, "You don't have permission to access this page.")
        return redirect('business:business_dashboard')

    business = user_business
    business_api = business_models.BusinessApiSettings.objects.filter(business_id=business_id, id=api_id).first()
    from django.utils import timezone as dj_timezone
    update_time = dj_timezone.localtime().strftime('%Y-%m-%d  Time : %H:%M:%S')

    if not business_api:
        messages.error(request, "API settings not found.")
        return redirect('business:business_settings_api_list', business_id=business_id)

    BASE_API_KEY = business_api.api_key
    BASE_API_ACCESS_KEY = business_api.api_access_token
    BASE_API_SECRET = business_api.api_secret
    BASE_API_VERSION = business_api.api_version
    BASE_API_STORE_NAME = business_api.site_api_url
    BASE_API_ORDER_ENDPINT = business_api.order_api_endpoint
    BASE_API_PRODUCT_ENDPINT = business_api.product_api_endpoint

    BASE_API_STORE_NAME = BASE_API_STORE_NAME.replace('https://', '')

    # Initialize variables with defaults to prevent undefined variable errors
    order_response = None
    product_response = None
    order_count = 0
    product_count = 0
    result = {}
    status = 0
    error_message = None

    try:
        if business_api.api_type == 'shopify':
            shop_url = BASE_API_STORE_NAME
            logger.debug(f'Testing Shopify API for shop_url={shop_url}')

            order_base_url = 'https://' + shop_url + BASE_API_ORDER_ENDPINT
            product_base_url = 'https://' + shop_url + BASE_API_PRODUCT_ENDPINT
            header_value = {'X-Shopify-Access-Token': BASE_API_ACCESS_KEY, 'Content-Type': 'application/json'}

            order_response = requests.get(order_base_url, headers=header_value, params={'status': 'any', 'limit': 10}, timeout=30)
            order_response.raise_for_status()
            order_count = len(order_response.json().get('orders', []))
            logger.debug(f'Shopify order_count={order_count}')

            product_response = requests.get(product_base_url, headers=header_value, timeout=30)
            product_response.raise_for_status()
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
                timeout=30,
            )

            order_response = wcapi.get("orders")
            order_count_str = order_response.headers.get('X-WP-Total', '0')
            order_count = int(order_count_str) if order_count_str else 0
            logger.debug(f'WooCommerce order_count={order_count}')

            product_response = wcapi.get("products", params={"per_page": 20})
            product_count_str = product_response.headers.get('X-WP-Total', '0')
            product_count = int(product_count_str) if product_count_str else 0
            logger.debug(f'WooCommerce product_count={product_count}')

        else:
            error_message = f'API type "{business_api.api_type}" is not yet supported for testing.'

    except requests.exceptions.Timeout:
        error_message = 'Connection timed out. Please check your API URL and try again.'
        logger.error(f'API test timeout for business {business_id}, api {api_id}')
    except requests.exceptions.ConnectionError:
        error_message = 'Could not connect to the API. Please check your store URL.'
        logger.error(f'API connection error for business {business_id}, api {api_id}')
    except requests.exceptions.HTTPError as e:
        error_message = f'API returned error: {e.response.status_code} - {e.response.reason}'
        logger.error(f'API HTTP error for business {business_id}, api {api_id}: {e}')
    except ValueError as e:
        error_message = f'Invalid response from API: {str(e)}'
        logger.error(f'API value error for business {business_id}, api {api_id}: {e}')
    except Exception as e:
        error_message = f'An unexpected error occurred: {str(e)}'
        logger.exception(f'API test exception for business {business_id}, api {api_id}')

    # Handle response data
    if error_message:
        result = {'error': error_message}
        status = 0
    elif order_response is not None:
        try:
            result = order_response.json()
            status = order_response.status_code
        except ValueError:
            result = {'error': 'Invalid JSON response from API'}
            status = order_response.status_code if order_response else 0
    else:
        result = {'error': f'API type "{business_api.api_type}" is not yet supported for testing.'}
        status = 0

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
@business_required
def business_logo_update(request, business_id):
    # IDOR FIX: Verify user owns this business
    user_business = get_cached_business(request)
    if not user_business or user_business.business_id != business_id:
        logger.warning(f'Unauthorized logo update attempt by user {request.user.id} for business {business_id}')
        return HttpResponseForbidden("You don't have permission to update this business logo.")

    try:
        business_logos = business_models.BusinessLogo.objects.get(business_id=business_id)
    except business_models.BusinessLogo.DoesNotExist:
        business_logos = business_models.BusinessLogo(business=user_business)

    form = business_forms.BusinessLogoForm()
    if request.method == 'POST':
        logger.debug(f'Processing logo update for business_id={business_id}')
        form = business_forms.BusinessLogoForm(
            request.POST, request.FILES, instance=business_logos)
        if form.is_valid():
            f = form.save(commit=False)

            # Delete the old logo file if exists
            if business_logos.business_logo and business_logos.business_logo != 'business/avatar.png':
                logger.debug(f'Old logo found: {business_logos.business_logo.path}')

            f.business_id = business_id
            f.path = f'business/{user_business.business_code}'
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
        'business': user_business,
    }
    return render(request, 'business/parts/business_logo_update.html', context)




# =============================================================================
# TEAM MANAGEMENT VIEWS
# =============================================================================

from django.utils import timezone
from business.decorators import (
    business_permission_required,
    business_manager_or_owner_required,
    business_owner_required,
    get_user_business_access,
    get_all_user_businesses,
    user_has_business_permission,
)
from business.permissions import BusinessPermissions, TeamRoles, get_role_permissions


@login_required(login_url='/accounts/login/')
@business_required
@business_permission_required(BusinessPermissions.TEAM_VIEW)
def business_teams(request, business_id):
    """
    List all team members for a business.

    Requires TEAM_VIEW permission.
    Shows team members with their roles, status, and permission counts.
    """
    business = request.current_business

    # Verify business_id matches user's business
    if business.business_id != business_id:
        messages.error(request, "Access denied.")
        return redirect('business:business_dashboard')

    # Get team members with custom permissions count
    teams = business_models.BusinessTeamProfile.objects.select_related(
        'user', 'invited_by'
    ).prefetch_related(
        'custom_permissions'
    ).filter(business_id=business_id).order_by('-created_at')

    # Add permission count to each team member (uses prefetched custom_permissions)
    from business.permissions import get_role_permissions
    for team in teams:
        role_perms = set(get_role_permissions(team.team_role))
        for custom_perm in team.custom_permissions.all():  # Uses prefetch cache
            if custom_perm.is_granted:
                role_perms.add(custom_perm.permission_code)
            else:
                role_perms.discard(custom_perm.permission_code)
        team.permission_count = len(role_perms)

    logger.debug(f'Loading teams for business_id={business_id}, count={teams.count()}')

    context = {
        'business': business,
        'teams': teams,
        'can_manage_team': user_has_business_permission(
            request.user, BusinessPermissions.TEAM_MANAGE
        ),
    }
    return render(request, 'business/parts/business_teams_list.html', context)


@login_required(login_url='/accounts/login/')
@business_required
@business_permission_required(BusinessPermissions.TEAM_MANAGE)
def business_teams_add(request, business_id):
    """
    Add a new team member to the business.

    Requires TEAM_MANAGE permission.
    Creates a new BusinessTeamProfile with the selected user and role.
    """
    business = request.current_business

    if business.business_id != business_id:
        messages.error(request, "Access denied.")
        return redirect('business:business_dashboard')

    form = business_forms.TeamMemberAddForm(business=business)

    if request.method == 'POST':
        logger.debug(f'Adding team member for business_id={business_id}')
        form = business_forms.TeamMemberAddForm(request.POST, business=business)

        if form.is_valid():
            # Get the validated user from the form
            user = form.get_user()

            team_member = form.save(commit=False)
            team_member.user = user  # Set user from email/ID lookup
            team_member.business_id = business_id
            team_member.invited_by = request.user
            team_member.invited_at = timezone.now()
            team_member.team_status = 'active'  # Direct add = immediate access
            team_member.save()

            logger.info(f'Team member {team_member.id} added by user {request.user.id} for business_id={business_id}')
            messages.success(request, f"Team member '{team_member.team_name or user.username}' added successfully.")
            return redirect("business:business_teams", business_id)
        else:
            logger.warning(f'Team profile form invalid: {form.errors}')
            messages.error(request, "Please correct the errors below.")

    context = {
        'business': business,
        'form': form,
        'form_title': 'Add Team Member',
        'role_choices': TeamRoles.ROLE_CHOICES,
    }
    return render(request, 'business/parts/business_teams_add.html', context)


@login_required(login_url='/accounts/login/')
@business_required
@business_permission_required(BusinessPermissions.TEAM_MANAGE)
def business_teams_update(request, business_id, team_id):
    """
    Update an existing team member.

    Requires TEAM_MANAGE permission.
    Allows updating team member details and role.
    """
    business = request.current_business

    if business.business_id != business_id:
        messages.error(request, "Access denied.")
        return redirect('business:business_dashboard')

    team = get_object_or_404(
        business_models.BusinessTeamProfile,
        id=team_id,
        business_id=business_id
    )

    form = business_forms.BusinessTeamProfileForm(instance=team)

    if request.method == 'POST':
        logger.debug(f'Updating team member {team_id} for business_id={business_id}')
        form = business_forms.BusinessTeamProfileForm(request.POST, instance=team)

        if form.is_valid():
            form.save()
            logger.info(f'Team member {team_id} updated for business_id={business_id}')
            messages.success(request, "Team member updated successfully.")
            return redirect("business:business_teams", business_id)
        else:
            logger.warning(f'Team profile form invalid: {form.errors}')
            messages.error(request, "Please correct the errors below.")

    context = {
        'business': business,
        'form': form,
        'team': team,
        'form_title': 'Update Team Member'
    }

    return render(request, 'business/parts/business_teams_update.html', context)


@login_required(login_url='/accounts/login/')
@business_required
@business_manager_or_owner_required()
def business_team_permissions(request, business_id, team_id):
    """
    Manage individual team member permissions.

    Requires manager or owner access.
    Allows granting/revoking specific permissions beyond role defaults.
    """
    business = request.current_business

    if business.business_id != business_id:
        messages.error(request, "Access denied.")
        return redirect('business:business_dashboard')

    team_member = get_object_or_404(
        business_models.BusinessTeamProfile.objects.select_related('user').prefetch_related('custom_permissions'),
        id=team_id,
        business_id=business_id
    )

    if request.method == 'POST':
        action = request.POST.get('action')
        permission_code = request.POST.get('permission_code')

        if action == 'grant' and permission_code:
            team_member.grant_permission(permission_code, granted_by=request.user)
            messages.success(request, f"Permission '{permission_code}' granted.")
            logger.info(f'Permission {permission_code} granted to team member {team_id} by user {request.user.id}')

        elif action == 'revoke' and permission_code:
            team_member.revoke_permission(permission_code, revoked_by=request.user)
            messages.success(request, f"Permission '{permission_code}' revoked.")
            logger.info(f'Permission {permission_code} revoked from team member {team_id} by user {request.user.id}')

        elif action == 'reset':
            team_member.reset_to_role_defaults()
            messages.success(request, "Permissions reset to role defaults.")
            logger.info(f'Permissions reset to defaults for team member {team_id} by user {request.user.id}')

        elif action == 'change_role':
            new_role = request.POST.get('role')
            if new_role in dict(TeamRoles.ROLE_CHOICES):
                old_role = team_member.team_role
                team_member.team_role = new_role
                team_member.save()
                messages.success(request, f"Role changed from {old_role} to {new_role}.")
                logger.info(f'Role changed from {old_role} to {new_role} for team member {team_id} by user {request.user.id}')

        return redirect('business:business_team_permissions', business_id, team_id)

    # Get all available permissions and current state
    role_permissions = set(get_role_permissions(team_member.team_role))
    effective_permissions = team_member.get_effective_permissions()

    # Build permission display data grouped by category
    permission_groups = {}
    for group_name, group_perms in BusinessPermissions.PERMISSION_GROUPS.items():
        group_data = []
        for code, label in group_perms:
            in_role = code in role_permissions
            is_effective = code in effective_permissions

            # Determine override status
            custom_perm = team_member.custom_permissions.filter(permission_code=code).first()
            override_status = None
            if custom_perm:
                override_status = 'granted' if custom_perm.is_granted else 'revoked'

            group_data.append({
                'code': code,
                'label': label,
                'in_role_default': in_role,
                'is_effective': is_effective,
                'override_status': override_status,
            })
        permission_groups[group_name] = group_data

    context = {
        'business': business,
        'team_member': team_member,
        'permission_groups': permission_groups,
        'role_choices': TeamRoles.ROLE_CHOICES,
        'current_role': team_member.team_role,
        'effective_count': len(effective_permissions),
    }
    return render(request, 'business/parts/business_team_permissions.html', context)


@login_required(login_url='/accounts/login/')
@business_required
@business_permission_required(BusinessPermissions.TEAM_MANAGE)
def business_team_remove(request, business_id, team_id):
    """
    Remove a team member from the business.

    Requires TEAM_MANAGE permission.
    Permanently deletes the team member and their custom permissions.
    """
    business = request.current_business

    if business.business_id != business_id:
        messages.error(request, "Access denied.")
        return redirect('business:business_dashboard')

    team_member = get_object_or_404(
        business_models.BusinessTeamProfile,
        id=team_id,
        business_id=business_id
    )

    if request.method == 'POST':
        team_name = team_member.team_name or team_member.user.username
        team_member.delete()
        logger.info(f'Team member {team_id} removed from business {business_id} by user {request.user.id}')
        messages.success(request, f"Team member '{team_name}' has been removed.")
        return redirect('business:business_teams', business_id)

    context = {
        'business': business,
        'team_member': team_member,
    }
    return render(request, 'business/parts/business_team_remove_confirm.html', context)


@login_required(login_url='/accounts/login/')
@business_required
@business_permission_required(BusinessPermissions.TEAM_MANAGE)
def business_team_status_change(request, business_id, team_id):
    """
    Change team member status (activate/suspend/deactivate).

    Requires TEAM_MANAGE permission.
    Handles AJAX requests for status changes.

    Returns proper JSON responses with appropriate HTTP status codes:
    - 200: Success
    - 400: Validation error (invalid status, missing status)
    - 403: Access denied
    - 404: Team member not found
    - 405: Invalid request method
    - 500: Server error
    """
    try:
        business = request.current_business

        if business.business_id != business_id:
            return JsonResponse({'success': False, 'error': 'Access denied'}, status=403)

        if request.method != 'POST':
            return JsonResponse({'success': False, 'error': 'Invalid method'}, status=405)

        # Handle invalid team_id gracefully with JSON response instead of 404 HTML page
        try:
            team_member = business_models.BusinessTeamProfile.objects.get(
                id=team_id,
                business_id=business_id
            )
        except business_models.BusinessTeamProfile.DoesNotExist:
            logger.warning(f'Team member {team_id} not found for business {business_id}')
            return JsonResponse({'success': False, 'error': 'Team member not found'}, status=404)
        except (ValueError, TypeError):
            return JsonResponse({'success': False, 'error': 'Invalid team ID format'}, status=400)

        new_status = request.POST.get('status')

        if not new_status:
            return JsonResponse({'success': False, 'error': 'Status is required'}, status=400)

        valid_statuses = dict(business_models.BusinessTeamProfile.STATUS_CHOICES)

        if new_status not in valid_statuses:
            return JsonResponse({'success': False, 'error': 'Invalid status'}, status=400)

        old_status = team_member.team_status
        team_member.team_status = new_status
        team_member.save()

        logger.info(f'Team member {team_id} status changed from {old_status} to {new_status} by user {request.user.id}')

        return JsonResponse({
            'success': True,
            'message': f"Status changed to {valid_statuses[new_status]}",
            'new_status': new_status,
            'new_status_label': valid_statuses[new_status],
        })

    except Exception as e:
        logger.error(f'Error changing team member status: {e}')
        return JsonResponse({'success': False, 'error': 'Server error'}, status=500)


# Workflow Guide -----------------------------------------------------

@login_required(login_url='account_login')
@business_required
def workflow_guide(request):
    """Display comprehensive workflow guide for clients"""
    
    # Get user's business for URL generation
    user_business = get_cached_business(request)
    business_id = user_business.business_id if user_business else None

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
            'target_url': reverse('business:business_profile'),
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
            'target_url': reverse('business:pickup_location_list'),
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
            'target_url': reverse('business:business_settings_api_list', args=[business_id]) if business_id else None,
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
            'target_url': reverse('orders:add_order'),
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
            'target_url': reverse('orders:orders_all_list'),
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
            'target_url': None,
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
            'target_url': reverse('orders:orders_all_list'),
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
            'target_url': reverse('business:business_teams', args=[business_id]) if business_id else None,
        },
    ]

    context = {
        'workflow_steps': workflow_steps,
        'page_title': 'Client Workflow Guide',
        'user_business': user_business,  # Also ensure sidebar has business context
    }

    return render(request, 'business/workflow_guide.html', context)


# =============================================================================
# BUSINESS SELECTOR VIEWS
# =============================================================================

@login_required(login_url='account_login')
@business_required
def business_selector(request):
    """
    Show business selector when user has access to multiple businesses.

    Allows users to choose which business they want to work with.
    Selected business is stored in session.
    """
    # Get all businesses user has access to
    user_businesses = get_all_user_businesses(request.user)

    if not user_businesses:
        messages.error(request, "No business associated with your account")
        return redirect('core:main_dashboard')

    # If only one business, auto-select it and redirect
    if len(user_businesses) == 1:
        business_info = user_businesses[0]
        request.session['selected_business_id'] = business_info['business'].business_id
        messages.success(request, f"Welcome to {business_info['business'].business_name}")
        return redirect('business:business_dashboard')

    # Prefetch business logos to avoid N+1 queries
    business_ids = [b['business'].business_id for b in user_businesses]
    logos = business_models.BusinessLogo.objects.filter(
        business_id__in=business_ids
    ).select_related('business')

    # Create a logo lookup dict
    logo_dict = {logo.business_id: logo for logo in logos}

    # Attach logos to businesses
    for business_info in user_businesses:
        business_info['logo'] = logo_dict.get(business_info['business'].business_id)

    # Get current selection if any
    selected_business_id = request.session.get('selected_business_id')

    context = {
        'user_businesses': user_businesses,
        'selected_business_id': selected_business_id,
        'total_count': len(user_businesses),
    }

    return render(request, 'business/business_selector.html', context)


@login_required(login_url='account_login')
@business_required
def business_switch(request, business_id):
    """
    Switch to a different business.

    Verifies user has access to the business and stores selection in session.
    """
    # Verify user has access to this business
    user_businesses = get_all_user_businesses(request.user)

    # Check if business_id is in user's accessible businesses
    has_access = any(
        b['business'].business_id == business_id
        for b in user_businesses
    )

    if not has_access:
        messages.error(request, "You don't have access to this business")
        return redirect('business:business_selector')

    # Store selection in session
    request.session['selected_business_id'] = business_id

    # Get business name for message
    business = next(
        (b['business'] for b in user_businesses if b['business'].business_id == business_id),
        None
    )

    if business:
        messages.success(request, f"Switched to {business.business_name}")

    # Clear cached business access to force reload
    if hasattr(request, '_cached_business_access'):
        delattr(request, '_cached_business_access')
    if hasattr(request, '_cached_user_business'):
        delattr(request, '_cached_user_business')

    # Redirect to dashboard
    return redirect('business:business_dashboard')


# Finance Section ----------------------------------------------------------------
@login_required(login_url='account_login')
@business_required
@business_permission_required(BusinessPermissions.REPORTS_VIEW)
def business_finance_dashboard(request):
    """Finance overview for business clients"""
    from django.db.models import Sum, Count
    from decimal import Decimal
    from datetime import timedelta
    from django.utils import timezone

    business = get_cached_business(request)
    if not business:
        messages.error(request, "No business associated with your account")
        return redirect('core:main_dashboard')

    days = int(request.GET.get('days', 30))
    start_date = timezone.now() - timedelta(days=days)

    # Transactions linked to this business
    txns = fleet_models.DriverTransaction.objects.filter(
        business=business,
        created_at__gte=start_date
    )

    # Also get transactions linked via delivery tasks for this business
    business_task_txns = fleet_models.DriverTransaction.objects.filter(
        delivery_task__business=business.business_id,
        created_at__gte=start_date
    ).exclude(business=business)

    # COD summary from delivery tasks
    all_deliveries = delivery_models.DeliveryTask.objects.filter(
        business=business.business_id,
        dl_task_date__gte=start_date.date()
    )

    cod_deliveries = all_deliveries.filter(cod_collected_amount__gt=0)
    cod_stats = cod_deliveries.aggregate(
        total_cod=Sum('cod_collected_amount'),
        collected_count=Count('id', filter=Q(cod_collected=True)),
        settled_count=Count('id', filter=Q(cod_settled=True)),
        total_count=Count('id'),
    )

    # COD client settlements for this business
    cod_client_settled = abs(txns.filter(
        transaction_type='cod_client_settle'
    ).aggregate(total=Sum('amount'))['total'] or Decimal('0'))

    # Charges billed to this business
    charges = txns.filter(
        transaction_type__in=['delivery_charge', 'fulfillment_charge', 'inventory_handling', 'other_charge']
    ).values('transaction_type').annotate(
        total=Sum('amount'),
        count=Count('id')
    )

    total_charges = sum(abs(c['total']) for c in charges) if charges else Decimal('0')

    # Bills for this business
    bills_payable = abs(txns.filter(
        transaction_type='bills_payable'
    ).aggregate(total=Sum('amount'))['total'] or Decimal('0'))

    bills_receivable = abs(txns.filter(
        transaction_type='bills_receivable'
    ).aggregate(total=Sum('amount'))['total'] or Decimal('0'))

    # Delivery summary
    delivery_stats = all_deliveries.aggregate(
        total_deliveries=Count('id'),
        total_delivery_charges=Sum('dl_price'),
        delivered=Count('id', filter=Q(dl_task_status='delivered')),
        failed=Count('id', filter=Q(dl_task_status='failed')),
    )

    # Recent transactions for this business
    recent_transactions = txns.select_related(
        'driver__user', 'delivery_task'
    ).order_by('-created_at')[:15]

    context = {
        'business': business,
        'selected_days': days,
        'cod_stats': cod_stats,
        'cod_client_settled': cod_client_settled,
        'charges': charges,
        'total_charges': total_charges,
        'bills_payable': bills_payable,
        'bills_receivable': bills_receivable,
        'delivery_stats': delivery_stats,
        'recent_transactions': recent_transactions,
    }

    return render(request, 'business/parts/business_finance_dashboard.html', context)


@login_required(login_url='account_login')
@business_required
@business_permission_required(BusinessPermissions.REPORTS_VIEW)
def business_transactions(request):
    """Transaction list view for business clients"""
    from decimal import Decimal
    from datetime import timedelta
    from django.utils import timezone

    business = get_cached_business(request)
    if not business:
        messages.error(request, "No business associated with your account")
        return redirect('core:main_dashboard')

    days = int(request.GET.get('days', 30))
    txn_type = request.GET.get('type', 'all')
    start_date = timezone.now() - timedelta(days=days)

    transactions = fleet_models.DriverTransaction.objects.filter(
        business=business,
        created_at__gte=start_date
    ).select_related('driver__user', 'delivery_task').order_by('-created_at')

    if txn_type != 'all':
        transactions = transactions.filter(transaction_type=txn_type)

    # Transaction types relevant to business
    business_types = [
        ('cod_client_settle', 'COD Client Settlement'),
        ('delivery_charge', 'Delivery Charge'),
        ('fulfillment_charge', 'Fulfillment Charge'),
        ('inventory_handling', 'Inventory Handling'),
        ('other_charge', 'Other Charge'),
        ('bills_payable', 'Bills Payable'),
        ('bills_receivable', 'Bills Receivable'),
    ]

    context = {
        'business': business,
        'transactions': transactions,
        'selected_days': days,
        'selected_type': txn_type,
        'transaction_types': business_types,
    }

    return render(request, 'business/parts/business_transactions.html', context)


@login_required(login_url='account_login')
@business_required
@business_permission_required(BusinessPermissions.REPORTS_VIEW)
def business_cod_statement(request):
    """COD statement view for business clients"""
    from django.db.models import Sum, Count
    from decimal import Decimal
    from datetime import timedelta
    from django.utils import timezone

    business = get_cached_business(request)
    if not business:
        messages.error(request, "No business associated with your account")
        return redirect('core:main_dashboard')

    days = int(request.GET.get('days', 30))
    start_date = timezone.now() - timedelta(days=days)

    # COD deliveries for this business
    cod_deliveries = delivery_models.DeliveryTask.objects.filter(
        business=business.business_id,
        has_cod=True,
        dl_task_date__gte=start_date.date()
    ).select_related('driver__user', 'order').order_by('-dl_task_date')

    # Summary stats
    stats = cod_deliveries.aggregate(
        total_cod=Sum('cod_collected_amount'),
        collected=Count('id', filter=Q(cod_collected=True)),
        settled_driver=Count('id', filter=Q(cod_settled=True)),
        total=Count('id'),
    )

    # COD settlements to this business
    settlements = fleet_models.DriverTransaction.objects.filter(
        business=business,
        transaction_type='cod_client_settle',
        created_at__gte=start_date.date()
    ).select_related('created_by').order_by('-created_at')

    total_settled = abs(settlements.aggregate(
        total=Sum('amount'))['total'] or Decimal('0'))

    context = {
        'business': business,
        'selected_days': days,
        'cod_deliveries': cod_deliveries,
        'stats': stats,
        'settlements': settlements,
        'total_settled': total_settled,
    }

    return render(request, 'business/parts/business_cod_statement.html', context)


# =============================================================================
# PRODUCT REQUEST VIEWS (Fulfillment Service)
# =============================================================================


@login_required(login_url='/accounts/login/')
@business_required
def inbound_requests_list(request):
    """
    List all inbound product requests for current business.

    Inbound requests are for sending products TO the warehouse.
    Only available for businesses with fulfillment service enabled.
    """
    from business.decorators import business_permission_required
    from business.permissions import BusinessPermissions
    from warehouse.models import InboundProductRequest
    from django.core.paginator import Paginator

    business = get_cached_business(request)
    if not business:
        messages.error(request, "No business associated with your account")
        return redirect('core:main_dashboard')

    # Check if fulfillment is enabled
    if not business.fulfillment_service_enabled:
        messages.warning(request, "Fulfillment service is not enabled for your business.")
        return redirect('business:business_dashboard')

    # Get requests for this business
    requests_qs = InboundProductRequest.objects.filter(
        business=business
    ).select_related('warehouse', 'created_by', 'approved_by', 'completed_by').prefetch_related('items__product')

    # Apply filters
    status_filter = request.GET.get('status', '')
    if status_filter:
        requests_qs = requests_qs.filter(status=status_filter)

    # Stats
    stats = {
        'pending': InboundProductRequest.objects.filter(business=business, status='pending').count(),
        'approved': InboundProductRequest.objects.filter(business=business, status='approved').count(),
        'completed': InboundProductRequest.objects.filter(business=business, status='completed').count(),
        'total': InboundProductRequest.objects.filter(business=business).count(),
    }

    # Pagination
    paginator = Paginator(requests_qs, 20)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    context = {
        'page_title': 'Inbound Requests',
        'business': business,
        'page_obj': page_obj,
        'stats': stats,
        'status_filter': status_filter,
    }
    return render(request, 'business/inbound_requests_list.html', context)


@login_required(login_url='/accounts/login/')
@business_required
def outbound_requests_list(request):
    """
    List all outbound product requests for current business.

    Outbound requests are for receiving products FROM the warehouse.
    Only available for businesses with fulfillment service enabled.
    """
    from business.decorators import business_permission_required
    from business.permissions import BusinessPermissions
    from warehouse.models import OutboundProductRequest
    from django.core.paginator import Paginator

    business = get_cached_business(request)
    if not business:
        messages.error(request, "No business associated with your account")
        return redirect('core:main_dashboard')

    # Check if fulfillment is enabled
    if not business.fulfillment_service_enabled:
        messages.warning(request, "Fulfillment service is not enabled for your business.")
        return redirect('business:business_dashboard')

    # Get requests for this business
    requests_qs = OutboundProductRequest.objects.filter(
        business=business
    ).select_related('warehouse', 'created_by', 'approved_by', 'completed_by').prefetch_related('items__product')

    # Apply filters
    status_filter = request.GET.get('status', '')
    if status_filter:
        requests_qs = requests_qs.filter(status=status_filter)

    # Stats
    stats = {
        'pending': OutboundProductRequest.objects.filter(business=business, status='pending').count(),
        'approved': OutboundProductRequest.objects.filter(business=business, status='approved').count(),
        'completed': OutboundProductRequest.objects.filter(business=business, status='completed').count(),
        'total': OutboundProductRequest.objects.filter(business=business).count(),
    }

    # Pagination
    paginator = Paginator(requests_qs, 20)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    context = {
        'page_title': 'Outbound Requests',
        'business': business,
        'page_obj': page_obj,
        'stats': stats,
        'status_filter': status_filter,
    }
    return render(request, 'business/outbound_requests_list.html', context)
