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
from warehouse import models as warehouse_models

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

        # Calculate real statistics - single aggregate query instead of 5 separate queries
        all_orders = orders_models.Order.objects.filter(business=business.business_id)
        from datetime import date
        from decimal import Decimal
        from django.db.models import Count, Case, When, IntegerField, DecimalField

        today = date.today()

        order_stats = all_orders.aggregate(
            total=Count('id'),
            delivered=Count(Case(
                When(order_status__in=['delivered', 'fulfilled'], then=1),
                output_field=IntegerField()
            )),
            pending=Count(Case(
                When(~Q(order_status__in=['delivered', 'fulfilled', 'cancelled']), then=1),
                output_field=IntegerField()
            )),
            cod_total=Sum('cod_amount'),
            cod_collected=Sum(Case(
                When(order_status__in=['delivered', 'fulfilled'], then='cod_amount'),
                default=Decimal('0'),
                output_field=DecimalField()
            )),
        )

        total_orders = order_stats['total']
        delivered_count = order_stats['delivered']
        pending_count = order_stats['pending']
        cod_amount_total = order_stats['cod_total'] or 0
        cod_collected = order_stats['cod_collected'] or 0

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

        # Weekly orders trend + chart counts — single aggregate query
        from datetime import timedelta
        week_start = today - timedelta(days=today.weekday())  # Monday
        week_end = week_start + timedelta(days=6)

        weekly_agg = all_orders.filter(
            order_date__gte=week_start, order_date__lte=week_end
        ).values('order_date').annotate(cnt=Count('id')).order_by('order_date')
        weekly_map = {row['order_date']: row['cnt'] for row in weekly_agg}
        weekly_orders_data = [weekly_map.get(week_start + timedelta(days=i), 0) for i in range(7)]

        # Chart status counts — from existing aggregate where possible
        in_transit_count = all_orders.filter(order_status='publish').count()
        failed_count = delivery_tasks.filter(
            dl_task_status__in=['failed', 'rejected', 'non_reachable']
        ).count()
        cancelled_count = all_orders.filter(order_status='cancelled').count()

        # COD chart data
        cod_pending = cod_amount_total - cod_collected

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
            # Chart data
            'weekly_orders_data': weekly_orders_data,
            'in_transit_count': in_transit_count,
            'failed_count': failed_count,
            'cancelled_count': cancelled_count,
            'cod_pending': cod_pending,
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

        all_locations = list(pickup_locations)

        if not all_locations:
            return redirect('business:pickup_location_choose')

        logger.info(f"User {request.user.id} viewing {len(all_locations)} pickup locations for business {business.business_id}")

        context = {
            'stores': all_locations,
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

    existing_warehouse_link = warehouse_models.SellerWarehouseLink.objects.filter(
        business=business
    ).select_related('warehouse').first()

    return render(request, 'business/parts/pickup_location_choose.html', {
        'business': business,
        'existing_warehouse_link': existing_warehouse_link,
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
                # Enforce single default: clear is_default on all other locations first
                if pickup_location.is_default:
                    business_models.PickupLocation.objects.filter(
                        business_id=business.business_id, is_default=True
                    ).update(is_default=False)
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
                updated = form.save(commit=False)
                # Enforce single default: clear is_default on all other locations first
                if updated.is_default:
                    business_models.PickupLocation.objects.filter(
                        business_id=business.business_id, is_default=True
                    ).exclude(id=pickup_location_id).update(is_default=False)
                updated.save()
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


def _business_profile_seo(request, business, business_profile, business_logo):
    """Build dynamic SEO metadata for a business profile page.

    The canonical URL always points at the public display route so search
    engines consolidate ranking signals there (the owner /profile/ view is an
    alias of the same content). Description is derived from the business's own
    details (name, category, city) and closes with the EzzyDelivery service hook.
    """
    name = (business.business_name or "Business").strip()
    city = (getattr(business_profile, 'business_city', '') or '').strip()
    category = (
        (getattr(business_profile, 'business_catagory_main', '') or '')
        or (business.business_product_category or '')
    ).strip()

    where = f"in {city}, Qatar" if city else "in Qatar"
    store = f"{category} store " if category else "store "
    description = (
        f"{name} on EzzyDelivery — {store}{where}. Browse products and order with "
        f"same-day delivery, Cash on Delivery and live tracking by EzzyDelivery."
    )[:155]

    profile_url = request.build_absolute_uri(
        reverse('business:business_profile_display', args=[business.business_id])
    )
    image = request.build_absolute_uri(business_logo) if business_logo else None

    return SEOMetadata.get_page_meta(
        title=f"{name} | Qatar Store",
        description=description,
        url=profile_url,
        image=image,
        page_type="profile",
    )


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

    # Showcase the business's latest products on the profile
    products = business.product.select_related('color', 'unit').order_by('-created_at')[:12]

    context = {
        'profile': profile,
        'business': business,
        'user_business': business,
        'location': location,
        'business_profile': business_profile,
        'business_logo_img': business_logo,
        'instakey': instakey,
        'products': products,
        'is_owner_view': True,
        'seo': _business_profile_seo(request, business, business_profile, business_logo),
    }
    return render(request, 'business/frontend/business_profile.html', context)

def business_profile_display(request, business_id):
    # Public page (no login) so search engines and AI crawlers can index the
    # business profile + its Store/Service structured data. Listed in sitemap.xml.
    try:
        business = business_models.Business.objects.select_related('profile', 'business_profile').get(
            business_id=business_id)
        location = business_models.PickupLocation.objects.filter(
            business_id=business.business_id).values_list('pickup_location_title', flat=True)[:2]
        
        business_logo_obj = business_models.BusinessLogo.objects.filter(business=business).first()
        business_logo = business_logo_obj.business_logo.url if business_logo_obj and business_logo_obj.business_logo else None
        
        business_profile = business.business_profile if hasattr(business, 'business_profile') else None

        # Detect whether the visitor is the owner of this business (drives the
        # public-framing context bar's "manage your profile" shortcut)
        viewer_business = get_cached_business(request)
        viewer_is_owner = bool(viewer_business and viewer_business.business_id == business.business_id)

        # Showcase the business's latest products on the public profile
        products = business.product.select_related('color', 'unit').order_by('-created_at')[:12]

        # Dynamic SEO for business profile (canonical -> this public display URL)
        meta = _business_profile_seo(request, business, business_profile, business_logo)

        context = {
            'seo': meta,
            'business': business,
            'location': location,
            'business_logo_img': business_logo,
            'business_profile': business_profile,
            'products': products,
            'is_owner_view': False,
            'viewer_is_owner': viewer_is_owner,
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
    has_shopify_integration = business_apis.filter(api_type__icontains='shopify').exists()

    context = {
        'business': business,
        'business_apis': business_apis,
        'api_keys': api_keys,
        'has_shopify_integration': has_shopify_integration,
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

    if not business_apis:
        messages.error(request, "API settings not found.")
        return redirect('business:business_settings_api_list', business_id=business_id)

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

    def _htmx_error(msg):
        return HttpResponse(
            f'<div class="bapi__status-section bapi__status-section--error">'
            f'<div class="bapi__status-icon"><i class="fa-solid fa-circle-exclamation"></i></div>'
            f'<div class="bapi__status-content"><h4>Configuration Error</h4><p>{msg}</p></div>'
            f'</div>'
        )

    if not business_api:
        return _htmx_error("API settings not found.")

    BASE_API_KEY = business_api.api_key
    BASE_API_ACCESS_KEY = business_api.api_access_token
    BASE_API_SECRET = business_api.api_secret
    BASE_API_VERSION = business_api.api_version
    BASE_API_STORE_NAME = business_api.site_api_url
    BASE_API_ORDER_ENDPINT = business_api.order_api_endpoint
    BASE_API_PRODUCT_ENDPINT = business_api.product_api_endpoint

    if not BASE_API_STORE_NAME:
        return _htmx_error("API store URL is not configured. Please update your API settings.")
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

        elif business_api.api_type == 'google_sheet':
            import re
            import gspread
            from google.oauth2.credentials import Credentials
            from django.conf import settings as django_settings

            token_file = os.path.join(django_settings.BASE_DIR, django_settings.GOOGLE_SHEETS_TOKEN_FILE)
            if not os.path.exists(token_file):
                error_message = 'Google Sheets token file not found. Please run the OAuth setup script.'
            else:
                creds = Credentials.from_authorized_user_file(
                    token_file,
                    scopes=['https://www.googleapis.com/auth/spreadsheets.readonly',
                            'https://www.googleapis.com/auth/drive.readonly']
                )
                gc = gspread.authorize(creds)
                sheet_url = business_api.site_api_url
                match = re.search(r'/spreadsheets/d/([a-zA-Z0-9_-]+)', sheet_url)
                if not match:
                    error_message = 'Invalid Google Sheet URL. Could not extract spreadsheet ID.'
                else:
                    sheet_id = match.group(1)
                    spreadsheet = gc.open_by_key(sheet_id)
                    worksheets = spreadsheet.worksheets()
                    sheets_info = []
                    for ws in worksheets:
                        values = ws.get_all_values()
                        data_rows = max(len([r for r in values if any(r)]) - 1, 0)
                        sheets_info.append({'name': ws.title, 'rows': data_rows})
                    order_count = sum(s['rows'] for s in sheets_info)
                    product_count = len(worksheets)
                    status = 200

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
    elif status == 200:
        result = {'rows': order_count, 'sheets': product_count}
    else:
        result = {'error': f'API type "{business_api.api_type}" is not yet supported for testing.'}
        status = 0

    context = {
        'business': business,
        'api': business_api,
        'update_time': update_time,
        'order_count': order_count,
        'product_count': product_count,
        'status': status,
        'result': result,
        'error_message': error_message,
        'sheets_info': sheets_info if 'sheets_info' in locals() else None,
    }
    return render(request, 'business/parts/business_settings_api_test_result.html', context)


# Shopify OAuth Flow -------------------------------------------------------
import hashlib
import hmac
import secrets

@login_required(login_url='/accounts/login/')
@business_required
def shopify_oauth_start(request, business_id, api_id):
    """Initiate Shopify OAuth flow - redirects user to Shopify authorization page."""
    user_business = get_cached_business(request)
    if not user_business or user_business.business_id != business_id:
        messages.error(request, "You don't have permission to access this page.")
        return redirect('business:business_dashboard')

    api_settings = business_models.BusinessApiSettings.objects.filter(
        business_id=business_id, id=api_id, api_type='shopify'
    ).first()

    if not api_settings:
        messages.error(request, "Shopify API settings not found.")
        return redirect('business:business_settings_api_list', business_id=business_id)

    if not api_settings.api_key or not api_settings.site_api_url:
        messages.error(request, "Client ID and Store URL are required for OAuth.")
        return redirect('business:business_settings_api_list', business_id=business_id)

    # Generate nonce for CSRF protection
    nonce = secrets.token_hex(16)
    request.session['shopify_oauth_nonce'] = nonce
    request.session['shopify_oauth_api_id'] = api_id
    request.session['shopify_oauth_business_id'] = business_id

    shop_domain = api_settings.site_api_url.replace('https://', '').replace('http://', '').rstrip('/')
    client_id = api_settings.api_key
    scopes = 'read_orders,read_products,read_fulfillments,read_shipping'
    redirect_uri = request.build_absolute_uri(reverse('business:shopify_oauth_callback'))

    auth_url = (
        f"https://{shop_domain}/admin/oauth/authorize"
        f"?client_id={client_id}"
        f"&scope={scopes}"
        f"&redirect_uri={redirect_uri}"
        f"&state={nonce}"
    )

    logger.info(f'Starting Shopify OAuth for business {business_id}, redirecting to {shop_domain}')
    return redirect(auth_url)


@login_required(login_url='/accounts/login/')
@business_required
def shopify_oauth_callback(request):
    """Handle Shopify OAuth callback - exchange code for access token."""
    code = request.GET.get('code')
    state = request.GET.get('state')
    shop = request.GET.get('shop', '')
    hmac_param = request.GET.get('hmac', '')

    # Validate state/nonce
    saved_nonce = request.session.get('shopify_oauth_nonce')
    api_id = request.session.get('shopify_oauth_api_id')
    business_id = request.session.get('shopify_oauth_business_id')

    if not saved_nonce or state != saved_nonce:
        messages.error(request, "OAuth verification failed. Please try again.")
        return redirect('business:business_dashboard')

    if not code or not api_id or not business_id:
        messages.error(request, "OAuth failed - missing authorization code.")
        return redirect('business:business_dashboard')

    # Get API settings
    api_settings = business_models.BusinessApiSettings.objects.filter(
        business_id=business_id, id=api_id, api_type='shopify'
    ).first()

    if not api_settings:
        messages.error(request, "API settings not found.")
        return redirect('business:business_dashboard')

    # Verify HMAC if present
    if hmac_param:
        query_params = {k: v for k, v in request.GET.items() if k != 'hmac'}
        sorted_params = '&'.join(f'{k}={v}' for k, v in sorted(query_params.items()))
        computed_hmac = hmac.new(
            api_settings.api_secret.encode('utf-8'),
            sorted_params.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(computed_hmac, hmac_param):
            messages.error(request, "OAuth HMAC verification failed.")
            return redirect('business:business_settings_api_list', business_id=business_id)

    # Exchange code for permanent access token
    shop_domain = api_settings.site_api_url.replace('https://', '').replace('http://', '').rstrip('/')
    token_url = f"https://{shop_domain}/admin/oauth/access_token"

    try:
        response = requests.post(token_url, json={
            'client_id': api_settings.api_key,
            'client_secret': api_settings.api_secret,
            'code': code,
        }, timeout=30)
        response.raise_for_status()
        data = response.json()
        access_token = data.get('access_token')

        if access_token:
            api_settings.api_access_token = access_token
            api_settings.is_verify_api = True
            api_settings.save()
            logger.info(f'Shopify OAuth successful for business {business_id} - token saved')
            messages.success(request, f"Shopify connected successfully! Access token obtained.")
        else:
            messages.error(request, "No access token received from Shopify.")
            logger.error(f'Shopify OAuth no token in response: {data}')

    except requests.exceptions.RequestException as e:
        messages.error(request, f"Failed to get access token: {str(e)}")
        logger.exception(f'Shopify OAuth token exchange failed for business {business_id}')

    # Clean up session
    for key in ['shopify_oauth_nonce', 'shopify_oauth_api_id', 'shopify_oauth_business_id']:
        request.session.pop(key, None)

    return redirect('business:business_settings_api_list', business_id=business_id)


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

    join_requests = business_models.BusinessTeamJoinRequest.objects.filter(
        business=business, status='pending'
    ).select_related('user', 'user__profile').order_by('-requested_at')

    join_request_count = join_requests.count()

    logger.debug(f'Loading teams for business_id={business_id}, count={teams.count()}')

    context = {
        'business': business,
        'teams': teams,
        'join_requests': join_requests,
        'join_request_count': join_request_count,
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

    # Pre-fill from join request if coming from accept action
    from_request_id = request.GET.get('from_request')
    join_request = None
    if from_request_id:
        join_request = business_models.BusinessTeamJoinRequest.objects.filter(
            id=from_request_id, business_id=business_id, status='accepted'
        ).select_related('user', 'user__profile').first()

    if join_request and request.method == 'GET':
        profile = getattr(join_request.user, 'profile', None)
        first = getattr(profile, 'first_name', '') or ''
        last = getattr(profile, 'last_name', '') or ''
        form = business_forms.TeamMemberAddForm(business=business, initial={
            'user_identifier': join_request.user.email,
            'team_name': f"{first} {last}".strip() or join_request.user.username,
            'team_email': join_request.user.email,
        })
    else:
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
            team_member.team_status = 'pending'  # Requires staff verification before access
            team_member.team_verifed = False
            team_member.save()

            # Save custom permissions if selected
            selected_permissions = form.cleaned_data.get('permissions', [])
            if selected_permissions:
                from business.permissions import ROLE_PERMISSIONS
                role_defaults = set(ROLE_PERMISSIONS.get(team_member.team_role, []))
                for perm_code in selected_permissions:
                    # Only create custom permission if it's NOT already in role defaults
                    if perm_code not in role_defaults:
                        business_models.BusinessTeamPermission.objects.create(
                            team_member=team_member,
                            permission_code=perm_code,
                            is_granted=True,
                            granted_by=request.user,
                        )

            # If added from a join request, ensure the request is marked accepted
            if join_request:
                join_request.responded_at = timezone.now()
                join_request.responded_by = request.user
                join_request.save(update_fields=['responded_at', 'responded_by'])

            logger.info(f'Team member {team_member.id} added by user {request.user.id} for business_id={business_id}')
            messages.success(request, f"Team member '{team_member.team_name or user.username}' added successfully. They will get dashboard access after staff verification.")
            return redirect("business:business_teams", business_id)
        else:
            logger.warning(f'Team profile form invalid: {form.errors}')
            messages.error(request, "Please correct the errors below.")

    from business.permissions import ROLE_PERMISSIONS
    context = {
        'business': business,
        'form': form,
        'form_title': 'Add Team Member',
        'role_choices': TeamRoles.ROLE_CHOICES,
        'permission_groups': BusinessPermissions.PERMISSION_GROUPS,
        'role_permissions': {role: list(perms) for role, perms in ROLE_PERMISSIONS.items()},
        'join_request': join_request,
    }
    return render(request, 'business/parts/business_teams_add.html', context)


@login_required(login_url='/accounts/login/')
@business_required
@business_permission_required(BusinessPermissions.TEAM_MANAGE)
def business_team_user_lookup(request, business_id):
    """
    Live lookup for the add-member form.

    Given an identifier (email/username/mobile/EZZY ID/user ID), returns the
    matched user's display name + email and whether they can be added, so the
    form can auto-fill the name field and show a green tick.
    """
    business = request.current_business
    if business.business_id != business_id:
        return JsonResponse({'found': False, 'error': 'Access denied'}, status=403)

    identifier = (request.GET.get('identifier') or '').strip()
    if not identifier:
        return JsonResponse({'found': False})

    user, error = business_forms.resolve_user_identifier(identifier)
    if user is None:
        return JsonResponse({'found': False, 'error': error})

    profile = getattr(user, 'profile', None)
    first = getattr(profile, 'first_name', '') or ''
    last = getattr(profile, 'last_name', '') or ''
    name = f"{first} {last}".strip() or user.get_full_name() or user.username

    can_add = True
    reason = ''
    if business_models.BusinessTeamProfile.objects.filter(business=business, user=user).exists():
        can_add, reason = False, 'Already a team member of this business.'
    elif business.user and business.user_id == user.id:
        can_add, reason = False, 'This is the business owner.'
    elif profile is None:
        can_add, reason = False, 'User has no profile yet.'
    else:
        completion = profile.get_profile_completion_percentage()
        if completion < 100:
            can_add, reason = False, f'Profile only {completion}% complete (100% required).'

    return JsonResponse({
        'found': True,
        'name': name,
        'email': user.email or '',
        'can_add': can_add,
        'reason': reason,
    })


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

    try:
        days = int(request.GET.get('days', 30))
        if days <= 0 or days > 365:
            days = 30
    except (ValueError, TypeError):
        days = 30
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

    total_charges = sum(abs(c['total'] or Decimal('0')) for c in charges) if charges else Decimal('0')

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

    try:
        days = int(request.GET.get('days', 30))
        if days <= 0 or days > 365:
            days = 30
    except (ValueError, TypeError):
        days = 30
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

    try:
        days = int(request.GET.get('days', 30))
        if days <= 0 or days > 365:
            days = 30
    except (ValueError, TypeError):
        days = 30
    start_date = timezone.now() - timedelta(days=days)

    # COD deliveries for this business
    cod_deliveries = delivery_models.DeliveryTask.objects.filter(
        business=business.business_id,
        cod_collected_amount__gt=0,
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
def inbound_requests_list(request):
    """
    List all inbound product requests.

    Staff sees all requests; business users see only their own.
    """
    from warehouse.models import InboundProductRequest
    from django.core.paginator import Paginator

    _prof = getattr(request.user, 'profile', None)
    is_staff = request.user.is_staff or getattr(_prof, 'is_staff', False) or getattr(_prof, 'is_superadmin', False)
    business = get_cached_business(request)

    if is_staff:
        requests_qs = InboundProductRequest.objects.all()
        stats_qs = InboundProductRequest.objects.all()
    else:
        if not business:
            messages.error(request, "No business associated with your account")
            return redirect('core:main_dashboard')
        if not business.fulfillment_service_enabled:
            messages.warning(request, "Fulfillment service is not enabled for your business.")
            return redirect('business:business_dashboard')
        requests_qs = InboundProductRequest.objects.filter(business=business)
        stats_qs = requests_qs

    requests_qs = requests_qs.select_related(
        'warehouse', 'business', 'created_by', 'approved_by', 'completed_by'
    ).prefetch_related('items__product')

    # Apply filters
    status_filter = request.GET.get('status', '')
    if status_filter:
        requests_qs = requests_qs.filter(status=status_filter)

    # Stats
    from django.db.models import Count, Case, When, IntegerField
    stats = stats_qs.aggregate(
        total=Count('id'),
        pending=Count(Case(When(status='pending', then=1), output_field=IntegerField())),
        approved=Count(Case(When(status='approved', then=1), output_field=IntegerField())),
        completed=Count(Case(When(status='completed', then=1), output_field=IntegerField())),
    )

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
        'is_staff': is_staff,
    }
    return render(request, 'business/inbound_requests_list.html', context)


@login_required(login_url='/accounts/login/')
def inbound_request_detail(request, pk):
    """Detail view for a single inbound product request."""
    from warehouse.models import InboundProductRequest

    _prof = getattr(request.user, 'profile', None)
    is_staff = request.user.is_staff or getattr(_prof, 'is_staff', False) or getattr(_prof, 'is_superadmin', False)
    business = get_cached_business(request)

    qs = InboundProductRequest.objects.select_related(
        'warehouse', 'business', 'created_by', 'approved_by', 'completed_by'
    ).prefetch_related('items__product')

    if is_staff:
        inbound_request = get_object_or_404(qs, pk=pk)
    else:
        if not business:
            messages.error(request, "No business associated with your account")
            return redirect('core:main_dashboard')
        inbound_request = get_object_or_404(qs, pk=pk, business=business)

    context = {
        'page_title': f'Request {inbound_request.request_number}',
        'business': inbound_request.business,
        'inbound_request': inbound_request,
    }
    return render(request, 'business/inbound_request_detail.html', context)


@login_required(login_url='/accounts/login/')
def inbound_request_create(request):
    """Create a new inbound product request."""
    from warehouse.models import InboundProductRequest, ProductRequestItem, SellerWarehouseLink, Warehouse
    from product.models import Product
    from business.models import Business

    _prof = getattr(request.user, 'profile', None)
    is_staff = request.user.is_staff or getattr(_prof, 'is_staff', False) or getattr(_prof, 'is_superadmin', False)
    business = get_cached_business(request)

    if is_staff:
        # Staff: show all warehouses, all businesses, products filtered by business
        warehouses = Warehouse.objects.filter(is_active=True)
        businesses = Business.objects.filter(business_status='active').order_by('business_name')
        selected_business_id = request.GET.get('business', '') or request.POST.get('business', '')
        if selected_business_id:
            products = Product.objects.filter(business_id=selected_business_id).order_by('item_name')
        else:
            products = Product.objects.none()
    else:
        if not business:
            messages.error(request, "No business associated with your account")
            return redirect('core:main_dashboard')
        if not business.fulfillment_service_enabled:
            messages.warning(request, "Fulfillment service is not enabled for your business.")
            return redirect('business:business_dashboard')
        # Business user: linked warehouses only
        linked_warehouse_ids = SellerWarehouseLink.objects.filter(
            business=business, is_active=True
        ).values_list('warehouse_id', flat=True)
        warehouses = Warehouse.objects.filter(id__in=linked_warehouse_ids, is_active=True)
        products = Product.objects.filter(business=business).order_by('item_name')
        businesses = None
        selected_business_id = ''

    if request.method == 'POST':
        warehouse_id = request.POST.get('warehouse')
        expected_date = request.POST.get('expected_delivery_date', '')
        notes = request.POST.get('notes', '')
        product_ids = request.POST.getlist('products[]')
        quantities = request.POST.getlist('quantities[]')
        item_notes = request.POST.getlist('item_notes[]')

        # Determine the business for this request
        if is_staff:
            post_business_id = request.POST.get('business', '')
            if not post_business_id:
                messages.error(request, "Please select a business.")
            else:
                try:
                    req_business = Business.objects.get(pk=post_business_id)
                except Business.DoesNotExist:
                    messages.error(request, "Invalid business selected.")
                    req_business = None
        else:
            req_business = business
            post_business_id = str(business.pk) if business else ''

        if not warehouse_id:
            messages.error(request, "Please select a warehouse.")
        elif not product_ids or not any(product_ids):
            messages.error(request, "Please add at least one product.")
        elif is_staff and not post_business_id:
            pass  # error already set above
        else:
            try:
                warehouse = Warehouse.objects.get(pk=warehouse_id)

                if not is_staff:
                    # Validate warehouse access for non-staff
                    if not SellerWarehouseLink.objects.filter(
                        business=business, warehouse_id=warehouse_id, is_active=True
                    ).exists():
                        raise ValueError("Warehouse is not linked to your business")

                # Create the inbound request
                inbound_req = InboundProductRequest.objects.create(
                    business=req_business,
                    warehouse=warehouse,
                    notes=notes,
                    created_by=request.user,
                    expected_delivery_date=expected_date if expected_date else None,
                )

                # Create items
                items_created = 0
                for i, (pid, qty_str) in enumerate(zip(product_ids, quantities)):
                    if not pid or not qty_str:
                        continue
                    qty = int(qty_str)
                    if qty <= 0:
                        continue

                    if is_staff:
                        product = Product.objects.get(pk=pid)
                    else:
                        product = Product.objects.get(pk=pid, business=business)
                    item_note = item_notes[i] if i < len(item_notes) else ''

                    ProductRequestItem.objects.create(
                        inbound_request=inbound_req,
                        product=product,
                        quantity_requested=qty,
                        notes=item_note,
                    )
                    items_created += 1

                if items_created == 0:
                    inbound_req.delete()
                    messages.error(request, "No valid products were added.")
                else:
                    messages.success(request, f"Inbound request {inbound_req.request_number} created with {items_created} item(s).")
                    return redirect('business:inbound_request_detail', pk=inbound_req.pk)

            except Exception as e:
                logger.exception(f"Error creating inbound request: {e}")
                messages.error(request, f"Error creating request: {e}")

    context = {
        'page_title': 'New Inbound Request',
        'business': business,
        'warehouses': warehouses,
        'products': products,
        'is_staff': is_staff,
        'businesses': businesses,
        'selected_business_id': selected_business_id,
    }
    return render(request, 'business/inbound_request_create.html', context)


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

    # Stats - single aggregate query instead of 4 separate COUNT queries
    from django.db.models import Count, Case, When, IntegerField
    stats_agg = OutboundProductRequest.objects.filter(business=business).aggregate(
        total=Count('id'),
        pending=Count(Case(When(status='pending', then=1), output_field=IntegerField())),
        approved=Count(Case(When(status='approved', then=1), output_field=IntegerField())),
        completed=Count(Case(When(status='completed', then=1), output_field=IntegerField())),
    )
    stats = stats_agg

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


# =============================================================================
# WAREHOUSE LINK REQUEST
# =============================================================================

@login_required(login_url='account_login')
@business_required
def warehouse_request(request):
    """
    Business-facing view to request linking to a fulfillment center.

    Shows active warehouses and lets the business submit a link request.
    Creates SellerWarehouseLink with is_active=False (pending staff approval).
    """
    business = get_cached_business(request)
    if not business:
        messages.error(request, "No business associated with your account")
        return redirect('core:main_dashboard')

    # Get existing links for this business
    existing_links = warehouse_models.SellerWarehouseLink.objects.filter(
        business=business
    ).select_related('warehouse')

    existing_warehouse_ids = set(existing_links.values_list('warehouse_id', flat=True))

    if request.method == 'POST':
        warehouse_id = request.POST.get('warehouse')
        notes = request.POST.get('notes', '').strip()

        if not warehouse_id:
            messages.error(request, "Please select a warehouse")
        else:
            try:
                warehouse = get_object_or_404(
                    warehouse_models.Warehouse, pk=warehouse_id, is_active=True
                )

                if warehouse.pk in existing_warehouse_ids:
                    messages.warning(
                        request,
                        f"You already have a link to {warehouse.name}."
                    )
                else:
                    warehouse_models.SellerWarehouseLink.objects.create(
                        business=business,
                        warehouse=warehouse,
                        is_active=False,
                        is_default=False,
                        priority=0,
                        notes=notes,
                        linked_by=request.user,
                    )
                    messages.success(
                        request,
                        f"Request submitted to link with {warehouse.name}. "
                        f"Our team will review and activate it shortly."
                    )
                    logger.info(
                        f"Warehouse link request: {business.business_name} → "
                        f"{warehouse.name} by {request.user.username}"
                    )
                    return redirect('business:pickup_location_list')

            except Exception as e:
                logger.error(f"Error creating warehouse link request: {e}")
                messages.error(request, "Something went wrong. Please try again.")

    # Available warehouses (active, not already linked)
    available_warehouses = warehouse_models.Warehouse.objects.filter(
        is_active=True
    ).exclude(
        pk__in=existing_warehouse_ids
    ).order_by('-is_default', 'name')

    context = {
        'business': business,
        'available_warehouses': available_warehouses,
        'existing_links': existing_links,
    }
    return render(request, 'business/parts/warehouse_request.html', context)


# =============================================================================
# TEAM JOIN REQUEST VIEWS
# =============================================================================

@login_required(login_url='/accounts/login/')
def business_search_ajax(request):
    """AJAX search for active businesses by name or code."""
    q = request.GET.get('q', '').strip()
    if len(q) < 2:
        return JsonResponse({'results': []})

    businesses = business_models.Business.objects.filter(
        business_status='active'
    ).filter(
        Q(business_name__icontains=q) | Q(business_code__icontains=q)
    ).values('business_id', 'business_name', 'business_code')[:10]

    results = [
        {'id': b['business_id'], 'name': b['business_name'], 'code': b['business_code'] or ''}
        for b in businesses
    ]
    return JsonResponse({'results': results})


@login_required(login_url='/accounts/login/')
def business_join_request_submit(request):
    """Submit a join request to a business team."""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Method not allowed'}, status=405)

    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, AttributeError):
        data = request.POST

    business_id = data.get('business_id')
    desired_role_title = (data.get('desired_role_title') or '').strip()
    message = (data.get('message') or '').strip()

    if not business_id:
        return JsonResponse({'success': False, 'error': 'Business ID is required.'})

    try:
        business = business_models.Business.objects.get(business_id=business_id, business_status='active')
    except business_models.Business.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Business not found or not active.'})

    # Cannot request to join own business
    if business.user_id == request.user.id:
        return JsonResponse({'success': False, 'error': 'You cannot request to join your own business.'})

    # Already a team member
    if business_models.BusinessTeamProfile.objects.filter(
        business=business, user=request.user
    ).exists():
        return JsonResponse({'success': False, 'error': 'You are already a team member of this business.'})

    # Existing pending/accepted request
    existing = business_models.BusinessTeamJoinRequest.objects.filter(
        business=business, user=request.user
    ).exclude(status__in=['rejected', 'cancelled']).first()
    if existing:
        return JsonResponse({'success': False, 'error': f'You already have a {existing.status} request for this business.'})

    # Create or re-create (if previously rejected/cancelled)
    business_models.BusinessTeamJoinRequest.objects.filter(
        business=business, user=request.user, status__in=['rejected', 'cancelled']
    ).delete()

    business_models.BusinessTeamJoinRequest.objects.create(
        business=business,
        user=request.user,
        desired_role_title=desired_role_title,
        message=message,
        status='pending',
    )
    logger.info(f'User {request.user.id} submitted join request for business {business_id}')
    return JsonResponse({'success': True, 'message': f'Join request sent to {business.business_name}.'})


@login_required(login_url='/accounts/login/')
def business_join_request_cancel(request, req_id):
    """Cancel the user's own pending join request."""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Method not allowed'}, status=405)

    join_req = business_models.BusinessTeamJoinRequest.objects.filter(
        id=req_id, user=request.user, status='pending'
    ).first()
    if not join_req:
        return JsonResponse({'success': False, 'error': 'Request not found or cannot be cancelled.'})

    join_req.status = 'cancelled'
    join_req.save(update_fields=['status'])
    return JsonResponse({'success': True})


@login_required(login_url='/accounts/login/')
@business_required
@business_permission_required(BusinessPermissions.TEAM_MANAGE)
def business_join_requests_list(request, business_id):
    """List pending join requests for a business (business owner view)."""
    business = request.current_business

    if business.business_id != business_id:
        messages.error(request, "Access denied.")
        return redirect('business:business_dashboard')

    join_reqs = business_models.BusinessTeamJoinRequest.objects.filter(
        business=business
    ).select_related('user', 'user__profile').order_by('-requested_at')

    status_filter = request.GET.get('status', 'pending')
    if status_filter in ('pending', 'accepted', 'rejected', 'cancelled'):
        join_reqs = join_reqs.filter(status=status_filter)

    pending_count = business_models.BusinessTeamJoinRequest.objects.filter(
        business=business, status='pending'
    ).count()

    context = {
        'business': business,
        'join_requests': join_reqs,
        'pending_count': pending_count,
        'current_filter': status_filter,
    }
    return render(request, 'business/parts/business_join_requests.html', context)


@login_required(login_url='/accounts/login/')
@business_required
@business_permission_required(BusinessPermissions.TEAM_MANAGE)
def business_join_request_action(request, business_id, req_id):
    """Accept or reject a join request (AJAX, business owner)."""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Method not allowed'}, status=405)

    business = request.current_business
    if business.business_id != business_id:
        return JsonResponse({'success': False, 'error': 'Access denied.'}, status=403)

    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, AttributeError):
        data = request.POST

    action = data.get('action')
    if action not in ('accept', 'reject'):
        return JsonResponse({'success': False, 'error': 'Invalid action.'})

    join_req = business_models.BusinessTeamJoinRequest.objects.filter(
        id=req_id, business=business, status='pending'
    ).select_related('user').first()
    if not join_req:
        return JsonResponse({'success': False, 'error': 'Request not found.'})

    join_req.responded_at = timezone.now()
    join_req.responded_by = request.user

    if action == 'accept':
        join_req.status = 'accepted'
        join_req.save(update_fields=['status', 'responded_at', 'responded_by'])
        redirect_url = reverse('business:business_teams_add', args=[business_id]) + f'?from_request={req_id}'
        return JsonResponse({'success': True, 'redirect_url': redirect_url})
    else:
        join_req.status = 'rejected'
        join_req.save(update_fields=['status', 'responded_at', 'responded_by'])
        return JsonResponse({'success': True})


# ─── Live Tracking Map ──────────────────────────────────────────────
@login_required
@business_required
def live_tracking_map(request):
    """Live tracking map showing active deliveries for this business."""
    from delivery.models import DeliveryTask
    active_statuses = ['start_ride', 'in_transit', 'out_for_delivery']
    active_tasks = DeliveryTask.objects.filter(
        business=request.current_business,
        dl_task_status__in=active_statuses
    ).select_related('order', 'driver').count()

    return render(request, 'business/live_tracking_map.html', {
        'active_count': active_tasks,
        'user_business': request.current_business,
    })


@login_required
@business_required
def live_tracking_data(request):
    """JSON endpoint returning driver locations for active tasks."""
    from delivery.models import DeliveryTask
    from fleet.models import DriverLocation

    active_statuses = ['start_ride', 'in_transit', 'out_for_delivery']
    tasks = DeliveryTask.objects.filter(
        business=request.current_business,
        dl_task_status__in=active_statuses
    ).select_related('order', 'driver')

    pins = []
    for task in tasks:
        # Get latest driver location
        driver_loc = None
        if task.driver_id:
            driver_loc = DriverLocation.objects.filter(
                driver_id=task.driver_id
            ).order_by('-created_at').first()

        order = task.order
        pin = {
            'task_number': task.dl_task_number,
            'status': task.dl_task_status,
            'status_display': task.get_dl_task_status_display(),
            'customer_name': order.customer_name if order else '',
            'customer_phone': order.customer_phone if order else '',
            'delivery_lat': float(order.latitude) if order and order.latitude else None,
            'delivery_lng': float(order.longitude) if order and order.longitude else None,
            'delivery_address': order.customer_address if order else '',
            'zone': order.dl_zone if order else None,
            'street': order.dl_street if order else None,
            'building': order.dl_building if order else None,
            'driver_name': str(task.driver) if task.driver else 'Unassigned',
            'driver_lat': float(driver_loc.latitude) if driver_loc else None,
            'driver_lng': float(driver_loc.longitude) if driver_loc else None,
        }
        pins.append(pin)

    return JsonResponse({'tasks': pins})


# ============================================================
# Reports & CSV Export
# ============================================================

@login_required
@business_required
def reports_dashboard(request):
    """Reports & export dashboard."""
    from datetime import date, timedelta
    today = date.today()
    return render(request, 'business/reports_dashboard.html', {
        'user_business': request.current_business,
        'is_business_owner': request.access_type == 'owner',
        'default_from': (today - timedelta(days=30)).isoformat(),
        'default_to': today.isoformat(),
    })


@login_required
@business_required
def reports_stats_partial(request):
    """HTMX partial: summary stat cards for the selected date range."""
    from datetime import date as date_cls, timedelta
    from orders.models import Order
    from django.db.models import Count, Sum, Q

    date_from_str = request.GET.get('date_from')
    date_to_str = request.GET.get('date_to')

    today = date_cls.today()
    try:
        date_from = datetime.strptime(date_from_str, '%Y-%m-%d').date() if date_from_str else today - timedelta(days=30)
        date_to = datetime.strptime(date_to_str, '%Y-%m-%d').date() if date_to_str else today
    except ValueError:
        date_from = today - timedelta(days=30)
        date_to = today

    qs = Order.objects.filter(
        business=request.current_business,
        created_at__date__gte=date_from,
        created_at__date__lte=date_to,
    )
    stats = qs.aggregate(
        total=Count('id'),
        delivered=Count('id', filter=Q(order_status='delivered')),
        pending=Count('id', filter=Q(order_status='publish')),
        cancelled=Count('id', filter=Q(order_status='cancelled')),
        failed=Count('id', filter=Q(order_status='failed')),
        cod_orders=Count('id', filter=Q(cod_amount__gt=0)),
        cod_total=Sum('cod_amount', filter=Q(cod_amount__gt=0)),
    )
    total = stats['total'] or 0
    delivered = stats['delivered'] or 0
    success_rate = round(delivered / total * 100, 1) if total > 0 else 0
    stats['success_rate'] = success_rate
    stats['cod_total'] = stats['cod_total'] or 0

    return render(request, 'business/parts/reports_stats_partial.html', {
        'stats': stats,
        'date_from': date_from,
        'date_to': date_to,
    })


@login_required
@business_required
def export_orders_csv(request):
    """Export orders as CSV with date range and status filters."""
    import csv
    from orders.models import Order

    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    status = request.GET.get('status', 'all')

    orders = Order.objects.filter(business=request.current_business).select_related('pickup_location')
    if date_from:
        orders = orders.filter(created_at__date__gte=datetime.strptime(date_from, '%Y-%m-%d').date())
    if date_to:
        orders = orders.filter(created_at__date__lte=datetime.strptime(date_to, '%Y-%m-%d').date())
    if status != 'all':
        orders = orders.filter(order_status=status)
    orders = orders.order_by('-created_at')

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="orders_{request.current_business.business_code}_{date_from or "all"}_{date_to or "all"}.csv"'

    writer = csv.writer(response)
    writer.writerow(['Order #', 'Client Code', 'Customer', 'Phone', 'Address', 'Zone', 'Street', 'Building', 'Status', 'COD Amount', 'COD Status', 'Time Slot', 'Created', 'Delivered At'])

    for o in orders:
        writer.writerow([
            o.order_number, o.client_order_code, o.customer_name, o.customer_phone,
            o.customer_address, o.dl_zone or '', o.dl_street or '', o.dl_building or '',
            o.get_order_status_display(), o.cod_amount or 0, o.get_cod_status_by_client_display(),
            o.get_preferred_time_slot_display() if hasattr(o, 'preferred_time_slot') and o.preferred_time_slot else '',
            o.created_at.strftime('%Y-%m-%d %H:%M') if o.created_at else '',
            o.delivered_at.strftime('%Y-%m-%d %H:%M') if o.delivered_at else '',
        ])

    return response


@login_required
@business_required
def export_cod_csv(request):
    """Export COD reconciliation report as CSV."""
    import csv
    from orders.models import Order

    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')

    orders = Order.objects.filter(
        business=request.current_business,
        cod_amount__gt=0
    ).select_related('pickup_location')
    if date_from:
        orders = orders.filter(created_at__date__gte=datetime.strptime(date_from, '%Y-%m-%d').date())
    if date_to:
        orders = orders.filter(created_at__date__lte=datetime.strptime(date_to, '%Y-%m-%d').date())
    orders = orders.order_by('-created_at')

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="cod_report_{request.current_business.business_code}_{date_from or "all"}.csv"'

    writer = csv.writer(response)
    writer.writerow(['Order #', 'Customer', 'COD Amount', 'Client COD Status', 'Staff COD Status', 'Order Status', 'Created', 'Delivered At'])

    for o in orders:
        writer.writerow([
            o.order_number, o.customer_name, o.cod_amount,
            o.get_cod_status_by_client_display(), o.get_cod_status_by_staff_display(),
            o.get_order_status_display(),
            o.created_at.strftime('%Y-%m-%d') if o.created_at else '',
            o.delivered_at.strftime('%Y-%m-%d') if o.delivered_at else '',
        ])

    return response


@login_required
@business_required
def export_performance_csv(request):
    """Export delivery performance report as CSV."""
    import csv
    from delivery.models import DeliveryTask
    from django.db.models import Count
    from django.db.models.functions import TruncDate

    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')

    tasks = DeliveryTask.objects.filter(business=request.current_business)
    if date_from:
        tasks = tasks.filter(created_at__date__gte=datetime.strptime(date_from, '%Y-%m-%d').date())
    if date_to:
        tasks = tasks.filter(created_at__date__lte=datetime.strptime(date_to, '%Y-%m-%d').date())

    # Daily aggregation
    daily = tasks.annotate(date=TruncDate('created_at')).values('date').annotate(
        total=Count('id'),
        delivered=Count('id', filter=Q(dl_task_status='delivered')),
        failed=Count('id', filter=Q(dl_task_status='failed')),
        cancelled=Count('id', filter=Q(dl_task_status='cancelled')),
    ).order_by('-date')

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="performance_{request.current_business.business_code}.csv"'

    writer = csv.writer(response)
    writer.writerow(['Date', 'Total Tasks', 'Delivered', 'Failed', 'Cancelled', 'Success Rate %'])

    for d in daily:
        rate = round(d['delivered'] / d['total'] * 100, 1) if d['total'] > 0 else 0
        writer.writerow([
            d['date'].strftime('%Y-%m-%d') if d['date'] else '',
            d['total'], d['delivered'], d['failed'], d['cancelled'], rate
        ])

    return response


# ─── WhatsApp Notification Triggers ─────────────────────────────────

@login_required(login_url='/accounts/login/')
@business_required
def whatsapp_triggers_list(request):
    """Settings page for WhatsApp notification triggers."""
    from business.models import WhatsAppNotificationTrigger

    default_whatsapp = (request.current_business.business_whatsapp or '').strip()

    triggers = {}
    for status, label in WhatsAppNotificationTrigger.TRIGGER_STATUS_CHOICES:
        trigger = WhatsAppNotificationTrigger.objects.filter(
            business=request.current_business, trigger_status=status
        ).first()
        triggers[status] = {
            'label': label,
            'is_active': trigger.is_active if trigger else False,
            'custom_message': trigger.custom_message if trigger else '',
            'notification_phone': (trigger.notification_phone if trigger else '') or '',
        }

    return render(request, 'business/whatsapp_triggers.html', {
        'triggers': triggers,
        'user_business': request.current_business,
        'is_business_owner': request.access_type == 'owner',
        'default_whatsapp': default_whatsapp,
    })


@login_required(login_url='/accounts/login/')
@business_required
def whatsapp_trigger_toggle(request):
    """HTMX POST endpoint to toggle a WhatsApp trigger."""
    from business.models import WhatsAppNotificationTrigger

    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    status = request.POST.get('trigger_status')
    is_active = request.POST.get('is_active') == 'true'
    custom_message = request.POST.get('custom_message', '')
    notification_phone = request.POST.get('notification_phone', '').strip()

    valid_statuses = [s[0] for s in WhatsAppNotificationTrigger.TRIGGER_STATUS_CHOICES]
    if status not in valid_statuses:
        return JsonResponse({'error': 'Invalid status'}, status=400)

    trigger, created = WhatsAppNotificationTrigger.objects.update_or_create(
        business=request.current_business,
        trigger_status=status,
        defaults={
            'is_active': is_active,
            'custom_message': custom_message,
            'notification_phone': notification_phone,
        }
    )

    return JsonResponse({'success': True, 'is_active': trigger.is_active})


@login_required
@business_required
def bulk_print_labels(request):
    """Generate and display multiple shipping labels for printing."""
    from orders.models import Order
    from delivery.models import ShippingLabel, DeliveryTask
    from delivery.label_utils import create_shipping_label

    # Accept ids from POST (bulk) or GET (single-order waybill link)
    raw_ids = request.POST.getlist('order_ids') or request.GET.getlist('order_ids')
    # Keep only valid integers so a malformed value can't 500 the page
    order_ids = [int(v) for v in raw_ids if str(v).isdigit()]

    if not order_ids:
        return render(request, 'business/bulk_print_labels.html', {
            'labels': [],
            'user_business': request.current_business,
        })

    orders = Order.objects.filter(
        id__in=order_ids,
        business=request.current_business,
    ).select_related('pickup_location')

    labels = []
    for order in orders:
        # Get or create shipping label
        label = ShippingLabel.objects.filter(order=order, status='generated').first()
        if not label:
            # Need a delivery task to create label
            task = DeliveryTask.objects.filter(order=order).first()
            if task:
                label = create_shipping_label(order, task)
        if label and label.label_file:
            labels.append({
                'order_number': order.order_number,
                'label_url': label.label_file.url,
                'customer_name': order.customer_name,
            })

    return render(request, 'business/bulk_print_labels.html', {
        'labels': labels,
        'user_business': request.current_business,
    })


@login_required
@business_required
def print_waybill(request):
    """Self-contained waybill(s) printable from the client dashboard.

    Rendered directly from the Order — no DeliveryTask or order-status
    dependency — so a label can be printed and stuck on the package at any
    stage of the order lifecycle. Accepts one or many ids via GET/POST.
    """
    import base64
    from orders.models import Order
    from delivery.label_utils import generate_barcode_image

    raw_ids = request.GET.getlist('order_ids') or request.POST.getlist('order_ids')
    order_ids = [int(v) for v in raw_ids if str(v).isdigit()]

    orders = Order.objects.filter(
        id__in=order_ids,
        business=request.current_business,
    ).select_related('business', 'pickup_location').prefetch_related('order_items__product')

    waybills = []
    for order in orders:
        barcode_b64 = ''
        buf = generate_barcode_image(order.order_number)
        if buf:
            barcode_b64 = base64.b64encode(buf.getvalue()).decode('ascii')
        waybills.append({'order': order, 'barcode_b64': barcode_b64})

    return render(request, 'business/print_waybill.html', {
        'waybills': waybills,
        'user_business': request.current_business,
    })


# =============================================================================
# BRANDED TRACKING SETTINGS
# =============================================================================

@login_required(login_url='account_login')
@business_required
def branded_tracking_settings(request):
    """Settings page for configuring the branded customer tracking page."""
    business = request.current_business
    BrandedTrackingConfig = business_models.BrandedTrackingConfig

    config, created = BrandedTrackingConfig.objects.get_or_create(
        business=business,
        defaults={
            'primary_color': '#f7c000',
            'secondary_color': '#001f3f',
        }
    )

    if request.method == 'POST':
        config.primary_color = request.POST.get('primary_color', '#f7c000').strip()
        config.secondary_color = request.POST.get('secondary_color', '#001f3f').strip()
        config.show_driver_name = request.POST.get('show_driver_name') == 'on'
        config.show_driver_phone = request.POST.get('show_driver_phone') == 'on'
        config.show_eta = request.POST.get('show_eta') == 'on'
        config.custom_footer_text = request.POST.get('custom_footer_text', '').strip()[:255]
        config.is_active = request.POST.get('is_active') == 'on'
        config.save()
        messages.success(request, 'Tracking page settings saved successfully.')
        return redirect('business:branded_tracking_settings')

    # Build a sample tracking URL for preview
    sample_task = delivery_models.DeliveryTask.objects.filter(
        business=business, tracking_token__isnull=False,
    ).order_by('-created_at').first()
    sample_url = None
    if sample_task:
        sample_url = request.build_absolute_uri(f'/track/{sample_task.tracking_token}/')

    return render(request, 'business/branded_tracking_settings.html', {
        'config': config,
        'sample_url': sample_url,
        'user_business': business,
    })


# =============================================================================
# RETURNS MANAGEMENT VIEWS
# =============================================================================


@login_required(login_url='account_login')
@business_required
def returns_list(request):
    """List all return requests for the business with optional status filter."""
    business = get_cached_business(request)
    if not business:
        messages.error(request, "No business associated with your account")
        return redirect('core:main_dashboard')

    from orders.models import ReturnRequest
    status_filter = request.GET.get('status', '')
    returns_qs = ReturnRequest.objects.filter(
        business=business
    ).select_related('order', 'reviewed_by').order_by('-created_at')

    if status_filter:
        returns_qs = returns_qs.filter(status=status_filter)

    return render(request, 'business/returns_list.html', {
        'returns': returns_qs,
        'status_filter': status_filter,
        'status_choices': ReturnRequest.RETURN_STATUS_CHOICES,
        'user_business': business,
    })


@login_required(login_url='account_login')
@business_required
def return_detail(request, return_id):
    """Detail view for a single return request with status timeline."""
    business = get_cached_business(request)
    if not business:
        messages.error(request, "No business associated with your account")
        return redirect('core:main_dashboard')

    from orders.models import ReturnRequest
    ret = get_object_or_404(
        ReturnRequest.objects.select_related('order', 'business', 'reviewed_by').prefetch_related('return_items__order_item__product'),
        id=return_id, business=business
    )

    # Timeline steps
    all_steps = ['pending', 'approved', 'pickup_scheduled', 'picked_up', 'received', 'refunded', 'closed']
    if ret.status == 'rejected':
        timeline = ['pending', 'rejected']
    else:
        timeline = all_steps

    return render(request, 'business/return_detail.html', {
        'ret': ret,
        'timeline': timeline,
        'status_choices': dict(ReturnRequest.RETURN_STATUS_CHOICES),
        'user_business': business,
    })


@login_required(login_url='account_login')
@business_required
def return_create(request, order_id):
    """Create a return request from a delivered order."""
    business = get_cached_business(request)
    if not business:
        messages.error(request, "No business associated with your account")
        return redirect('core:main_dashboard')

    order = get_object_or_404(
        orders_models.Order.objects.select_related('business').prefetch_related('order_items__product'),
        id=order_id, business=business
    )

    if order.order_status not in ('delivered', 'fulfilled'):
        messages.warning(request, "Returns can only be requested for delivered orders.")
        return redirect('orders:order_details', order.id)

    from orders.models import ReturnRequest, ReturnItem
    import uuid

    if request.method == 'POST':
        reason = request.POST.get('reason', '')
        reason_notes = request.POST.get('reason_notes', '')

        if not reason:
            messages.error(request, "Please select a return reason.")
            return render(request, 'business/return_create.html', {
                'order': order,
                'reason_choices': ReturnRequest.RETURN_REASON_CHOICES,
                'user_business': business,
            })

        # Collect selected items
        selected_items = []
        for item in order.order_items.all():
            qty_key = f'qty_{item.id}'
            chk_key = f'item_{item.id}'
            if request.POST.get(chk_key):
                qty = int(request.POST.get(qty_key, 1))
                if qty > 0:
                    selected_items.append((item, min(qty, item.quantity)))

        if not selected_items:
            messages.error(request, "Please select at least one item to return.")
            return render(request, 'business/return_create.html', {
                'order': order,
                'reason_choices': ReturnRequest.RETURN_REASON_CHOICES,
                'user_business': business,
            })

        # Generate return number
        biz_code = business.business_name[:3].upper() if business.business_name else 'BIZ'
        return_number = f"{biz_code}-{uuid.uuid4().hex[:8].upper()}"

        ret = ReturnRequest.objects.create(
            return_number=return_number,
            order=order,
            business=business,
            reason=reason,
            reason_notes=reason_notes,
            cod_reversal_amount=order.cod_amount or 0,
        )

        for item, qty in selected_items:
            ReturnItem.objects.create(
                return_request=ret,
                order_item=item,
                quantity_returned=qty,
            )

        messages.success(request, f"Return request RET-{return_number} created successfully.")
        return redirect('business:return_detail', ret.id)

    return render(request, 'business/return_create.html', {
        'order': order,
        'reason_choices': ReturnRequest.RETURN_REASON_CHOICES,
        'user_business': business,
    })


@login_required(login_url='account_login')
@business_required
def return_update_status(request, return_id):
    """Update the status of a return request (approve/reject)."""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    business = get_cached_business(request)
    if not business:
        return JsonResponse({'error': 'No business'}, status=403)

    from orders.models import ReturnRequest
    from django.utils import timezone

    ret = get_object_or_404(ReturnRequest, id=return_id, business=business)
    new_status = request.POST.get('status', '')
    review_notes = request.POST.get('review_notes', '')

    valid_statuses = [s[0] for s in ReturnRequest.RETURN_STATUS_CHOICES]
    if new_status not in valid_statuses:
        messages.error(request, "Invalid status.")
        return redirect('business:return_detail', ret.id)

    ret.status = new_status
    ret.review_notes = review_notes

    if new_status in ('approved', 'rejected'):
        ret.reviewed_by = request.user
        ret.reviewed_at = timezone.now()

    # When approved, update OrderItem quantities
    if new_status == 'approved':
        for ri in ret.return_items.select_related('order_item').all():
            oi = ri.order_item
            oi.quantity_returned = (oi.quantity_returned or 0) + ri.quantity_returned
            if oi.quantity_returned >= oi.quantity:
                oi.delivery_status = 'returned'
            elif oi.quantity_returned > 0:
                oi.delivery_status = 'partial'
            oi.save()

    ret.save()
    messages.success(request, f"Return status updated to {ret.get_status_display()}.")
    return redirect('business:return_detail', ret.id)
