"""
Orders Views Module
===================

This module handles all order management operations for businesses.

View Categories:
    Order Lists:
        - orders_all_list: All orders with pagination
        - orders_pending_list: Orders pending delivery (DMS status 4,5,6)
        - orders_successfull_list: Delivered orders (DMS status 2)
        - orders_unsuccessfull_list: Failed/cancelled orders (DMS status 7,8,9)
        - latest_orders_list: Dashboard widget showing latest 5 orders

    Order Creation:
        - add_order: Create single order with form
        - add_order_product: Add products to existing order
        - add_order_with_product: Create order with products in one step
        - bulk_order_entry: Excel-like bulk order entry

    Order Upload:
        - order_upload_file: CSV/Excel file upload
        - order_upload_review_data: Review and confirm uploaded data

    Order Management:
        - order_update: Edit existing order
        - delete_order: Remove order
        - order_details: View order details
        - update_order_status: AJAX status update

    Product Management:
        - update_order_product: Edit order products
        - order_product_list: List products in order

    API Integration:
        - get_order_by_api: Fetch orders from Shopify
        - get_orders_by_base_api: Fetch from configured API (Shopify/WooCommerce)

    Verification:
        - verify_location: Public customer address verification page

Security:
    All views implement IDOR protection by verifying order ownership.
    API credentials are loaded from environment variables.

Related:
    - orders.models: Order, OrderItem, AddressVerification
    - orders.forms: AddOrderForm, UpdateOrderForm, etc.
    - delivery.models: DeliveryTask (created from verified orders)
"""

import hmac
import json
import logging
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponse
from django.views.decorators.http import require_POST
from django.db.models import Q
from django.db import IntegrityError, transaction
from datetime import datetime, timedelta, timezone
from django.utils import timezone as dj_timezone
from django.forms import inlineformset_factory
import pandas as pd
from django.contrib import messages
import re
import requests
from woocommerce import API as WooAPI
from decouple import config

from core import models as core_models
from core.context_processors import get_cached_business
from orders import forms, models as orders_models
from business import models as business_models
from orders import forms as orders_forms
from business.decorators import (
    business_permission_required,
    business_access_required,
    get_user_business_access,
    user_has_business_permission,
)
from business.permissions import BusinessPermissions

# Local aliases for commonly used models
Order = orders_models.Order
OrderItem = orders_models.OrderItem
AddressVerification = orders_models.AddressVerification
Business = business_models.Business
PickupLocation = business_models.PickupLocation
Profile = core_models.Profile

from django.core.paginator import (
    Paginator,
    EmptyPage,
    PageNotAnInteger,
)

logger = logging.getLogger('orders')

# Import shared utilities from core
from core.utils import (
    contains_arabic,
    translate_to_english,
    convert_arabic_numerals,
    format_whatsapp_number,
)


# =============================================================================
# ORDER LIST VIEWS
# =============================================================================


@login_required(login_url='account_login')
@business_permission_required(BusinessPermissions.ORDER_VIEW)
def orders_all_list(request):
    # Business is injected by the decorator
    business = request.current_business
    logger.info(f"User {request.user.id} accessing orders list for business {business.business_id}")

    # Get filter parameters
    from datetime import date, timedelta
    order_number = request.GET.get('orderNumber', '')
    mobile = request.GET.get('mobile', '')
    customer_name = request.GET.get('customerName', '')
    zone = request.GET.get('zone', '')
    c_status = request.GET.get('cStatus', '')
    date_range = request.GET.get('dateRange', '')
    date_from = request.GET.get('dateFrom', '')
    date_to = request.GET.get('dateTo', '')
    cod_status = request.GET.get('codStatus', '')
    dl_status = request.GET.get('dlStatus', '')
    delivered_range = request.GET.get('deliveredRange', '')
    delivered_from = request.GET.get('deliveredFrom', '')
    delivered_to = request.GET.get('deliveredTo', '')

    # Process date range presets
    today = date.today()
    if date_range == 'today':
        date_from = today.isoformat()
        date_to = today.isoformat()
    elif date_range == 'yesterday':
        yesterday = today - timedelta(days=1)
        date_from = yesterday.isoformat()
        date_to = yesterday.isoformat()
    elif date_range == '3days':
        date_from = (today - timedelta(days=2)).isoformat()
        date_to = today.isoformat()
    elif date_range == 'week':
        start_of_week = today - timedelta(days=today.weekday())
        date_from = start_of_week.isoformat()
        date_to = today.isoformat()
    elif date_range == 'month':
        start_of_month = today.replace(day=1)
        date_from = start_of_month.isoformat()
        date_to = today.isoformat()

    # Process delivered date range presets
    if delivered_range == 'today':
        delivered_from = today.isoformat()
        delivered_to = today.isoformat()
    elif delivered_range == 'yesterday':
        yesterday = today - timedelta(days=1)
        delivered_from = yesterday.isoformat()
        delivered_to = yesterday.isoformat()
    elif delivered_range == '3days':
        delivered_from = (today - timedelta(days=2)).isoformat()
        delivered_to = today.isoformat()
    elif delivered_range == 'week':
        start_of_week = today - timedelta(days=today.weekday())
        delivered_from = start_of_week.isoformat()
        delivered_to = today.isoformat()
    elif delivered_range == 'month':
        start_of_month = today.replace(day=1)
        delivered_from = start_of_month.isoformat()
        delivered_to = today.isoformat()

    items = orders_models.Order.objects.filter(
        business=business.business_id
    ).select_related(
        'business',
        'pickup_location',
        'address_verified_by',
        'verified_by',
    ).prefetch_related(
        'order_items',
        'order_items__product',
        'order_items__product__product_category',
        'delivery_task',
        'delivery_task__driver',
        'delivery_task__business',
    )

    # Apply filters
    if order_number:
        items = items.filter(order_number__icontains=order_number)
    if mobile:
        items = items.filter(customer_phone__icontains=mobile)
    if customer_name:
        items = items.filter(customer_name__icontains=customer_name)
    if zone:
        items = items.filter(dl_zone=zone)
    if c_status == 'pending':
        items = items.exclude(order_status__in=['delivered', 'cancelled'])
    elif c_status:
        items = items.filter(order_status=c_status)
    if date_from:
        items = items.filter(order_date__gte=date_from)
    if date_to:
        items = items.filter(order_date__lte=date_to)
    if cod_status == 'with_cod':
        items = items.filter(cod_amount__gt=0)
    elif cod_status == 'no_cod':
        items = items.filter(cod_amount=0)

    # Delivery status filter (uses dl_task_status text field, not dms numeric codes)
    if dl_status == 'no_task':
        items = items.filter(delivery_task__isnull=True)
    elif dl_status:
        items = items.filter(delivery_task__dl_task_status=dl_status)

    # Delivered date filter
    if delivered_from:
        items = items.filter(delivery_task__completed_at__date__gte=delivered_from)
    if delivered_to:
        items = items.filter(delivery_task__completed_at__date__lte=delivered_to)

    # Sort handling
    VALID_SORT_FIELDS = {
        'id': 'id',
        'order_number': 'order_number',
        'client_order_code': 'client_order_code',
        'order_date': 'order_date',
        'customer_name': 'customer_name',
        'customer_phone': 'customer_phone',
        'dl_zone': 'dl_zone',
        'cod_amount': 'cod_amount',
    }
    sort_by = request.GET.get('sort', '')
    sort_dir = request.GET.get('dir', 'desc')
    if sort_by in VALID_SORT_FIELDS:
        order_field = VALID_SORT_FIELDS[sort_by]
        if sort_dir == 'asc':
            items = items.order_by(order_field)
        else:
            items = items.order_by(f'-{order_field}')
    else:
        # Default: newest by import time so freshly imported orders surface first.
        sort_by = 'id'
        sort_dir = 'desc'
        items = items.order_by('-id')

    logger.debug(f"Fetching orders for business {business.business_id}")

    default_page = 1
    page = request.GET.get('page', default_page)
    # Read per_page from request, with validation (valid: 10, 25, 50, 100)
    per_page = request.GET.get('per_page', '10')
    try:
        per_page = int(per_page)
        if per_page not in [10, 25, 50, 100]:
            per_page = 10
    except (ValueError, TypeError):
        per_page = 10
    paginator = Paginator(items, per_page)

    try:
        orders = paginator.page(page)
        logger.debug(f"Displaying page {page} with {len(orders)} orders")
    except PageNotAnInteger:
        orders = paginator.page(default_page)
        logger.debug(f"Invalid page number, displaying page {default_page}")
    except EmptyPage:
        orders = paginator.page(paginator.num_pages)
        logger.debug(f"Empty page, displaying last page {paginator.num_pages}")

    # Build fallback failure-reason map for legacy failed tasks that never saved
    # DeliveryTask.failure_reason — read the latest OrderStatusHistory note for the
    # dl_task_status → failed transition on each order on the current page.
    page_order_ids = [o.id for o in orders.object_list]
    fallback_failure_notes = {}
    if page_order_ids:
        failed_history_qs = orders_models.OrderStatusHistory.objects.filter(
            order_id__in=page_order_ids,
            field_name='dl_task_status',
            new_value='failed',
        ).order_by('order_id', '-created_at').values('order_id', 'notes')
        seen = set()
        for row in failed_history_qs:
            oid = row['order_id']
            if oid in seen:
                continue
            seen.add(oid)
            note = (row['notes'] or '').strip()
            if note:
                fallback_failure_notes[oid] = note

    # Query string carried by every pagination link (everything except page/per_page):
    # orderNumber, mobile, customerName, zone, cStatus, codStatus, dlStatus,
    # dateRange/dateFrom/dateTo, deliveredRange/deliveredFrom/deliveredTo, sort, dir.
    filter_qs = request.GET.copy()
    filter_qs.pop('page', None)
    filter_qs.pop('per_page', None)

    context = {
        'orders': orders,
        'business': business,
        'fallback_failure_notes': fallback_failure_notes,
        'len': paginator.count,  # Use paginator.count (cached) instead of items.count()
        'per_page': str(per_page),  # String for template comparison
        'filter_params': filter_qs.urlencode(),
        'has_ecom_api': business_models.BusinessApiSettings.objects.filter(
            business=business, api_type__in=['shopify', 'woocommerce']
        ).exists(),
        # Permission checks for template buttons
        'can_create_order': user_has_business_permission(request.user, BusinessPermissions.ORDER_CREATE),
        'can_edit_order': user_has_business_permission(request.user, BusinessPermissions.ORDER_EDIT),
        'can_delete_order': user_has_business_permission(request.user, BusinessPermissions.ORDER_DELETE),
        # Sort values for template
        'sort_by': sort_by,
        'sort_dir': sort_dir,
        # Filter values for template
        'filters': {
            'orderNumber': order_number,
            'mobile': mobile,
            'customerName': customer_name,
            'zone': zone,
            'cStatus': c_status,
            'dateRange': date_range,
            'dateFrom': date_from,
            'dateTo': date_to,
            'codStatus': cod_status,
            'dlStatus': dl_status,
            'deliveredRange': delivered_range,
            'deliveredFrom': delivered_from,
            'deliveredTo': delivered_to,
        },
    }
    return render(request, 'orders/order_all_list.html', context)


@login_required(login_url='account_login')
@business_permission_required(BusinessPermissions.ORDER_VIEW)
def orders_pending_list(request):
    # Business is injected by the decorator
    business = request.current_business
    logger.info(f"User {request.user.id} accessing pending orders for business {business.business_id}")

    # Pending = all orders except published, delivered, cancelled
    items = orders_models.Order.objects.filter(
        business=business.business_id
    ).exclude(
        order_status__in=['publish', 'delivered', 'cancelled']
    ).select_related(
        'business',
        'pickup_location',
        'address_verified_by',
        'verified_by',
    ).prefetch_related(
        'order_items',
        'order_items__product',
        'order_items__product__product_category',
        'delivery_task',
        'delivery_task__driver',
        'delivery_task__business',
    )

    # Sort handling
    VALID_SORT_FIELDS = {
        'id': 'id',
        'order_number': 'order_number',
        'order_date': 'order_date',
        'customer_name': 'customer_name',
        'customer_phone': 'customer_phone',
        'dl_zone': 'dl_zone',
        'cod_amount': 'cod_amount',
    }
    sort_by = request.GET.get('sort', '')
    sort_dir = request.GET.get('dir', 'desc')
    if sort_by in VALID_SORT_FIELDS:
        order_field = VALID_SORT_FIELDS[sort_by]
        if sort_dir == 'asc':
            items = items.order_by(order_field)
        else:
            items = items.order_by(f'-{order_field}')
    else:
        sort_by = ''
        items = items.order_by('-id')

    logger.debug(f"Fetching pending orders for business {business.business_id}")

    default_page = 1
    page = request.GET.get('page', default_page)
    per_page = request.GET.get('per_page', '10')
    try:
        per_page = int(per_page)
        if per_page not in [10, 25, 50, 100]:
            per_page = 10
    except (ValueError, TypeError):
        per_page = 10
    paginator = Paginator(items, per_page)

    try:
        orders = paginator.page(page)
        logger.debug(f"Displaying page {page} with {len(orders)} pending orders")
    except PageNotAnInteger:
        orders = paginator.page(default_page)
        logger.debug(f"Invalid page number, displaying page {default_page}")
    except EmptyPage:
        orders = paginator.page(paginator.num_pages)
        logger.debug(f"Empty page, displaying last page {paginator.num_pages}")

    # Query string carried by every pagination link (everything except page/per_page):
    # sort, dir.
    filter_qs = request.GET.copy()
    filter_qs.pop('page', None)
    filter_qs.pop('per_page', None)

    context = {
        'orders': orders,
        'business': business,
        'len': paginator.count,
        'per_page': str(per_page),
        'filter_params': filter_qs.urlencode(),
        'can_create_order': user_has_business_permission(request.user, BusinessPermissions.ORDER_CREATE),
        'can_edit_order': user_has_business_permission(request.user, BusinessPermissions.ORDER_EDIT),
        'can_delete_order': user_has_business_permission(request.user, BusinessPermissions.ORDER_DELETE),
        'sort_by': sort_by,
        'sort_dir': sort_dir,
    }
    return render(request, 'orders/order_pending_list.html', context)

@login_required(login_url='account_login')
@business_permission_required(BusinessPermissions.ORDER_VIEW)
def orders_successfull_list(request):
    # Business is injected by the decorator
    business = request.current_business
    logger.info(f"User {request.user.id} accessing successful orders for business {business.business_id}")

    orders = orders_models.Order.objects.filter(
        delivery_task__dl_task_status='delivered',
        business=business.business_id
    ).select_related(
        'business',
        'pickup_location',
        'address_verified_by',
        'verified_by',
    ).prefetch_related(
        'order_items',
        'order_items__product',
        'order_items__product__product_category',
        'delivery_task',
        'delivery_task__driver',
        'delivery_task__business',
    ).order_by('-id')

    logger.debug(f"Fetching successful orders for business {business.business_id}")

    default_page = 1
    page = request.GET.get('page', default_page)
    # Read per_page from request, with validation (valid: 10, 25, 50, 100)
    per_page = request.GET.get('per_page', '10')
    try:
        per_page = int(per_page)
        if per_page not in [10, 25, 50, 100]:
            per_page = 10
    except (ValueError, TypeError):
        per_page = 10
    paginator = Paginator(orders, per_page)

    try:
        orders = paginator.page(page)
        logger.debug(f"Displaying page {page} with {len(orders)} successful orders")
    except PageNotAnInteger:
        orders = paginator.page(default_page)
        logger.debug(f"Invalid page number, displaying page {default_page}")
    except EmptyPage:
        orders = paginator.page(paginator.num_pages)
        logger.debug(f"Empty page, displaying last page {paginator.num_pages}")

    context = {
        'orders': orders,
        'business': business,
        'per_page': str(per_page),  # String for template comparison
    }
    return render(request, 'orders/order_successful_list.html', context)


@login_required(login_url='account_login')
@business_permission_required(BusinessPermissions.ORDER_VIEW)
def orders_unsuccessfull_list(request):
    # Business is injected by the decorator
    business = request.current_business
    logger.info(f"User {request.user.id} accessing unsuccessful orders for business {business.business_id}")

    orders = orders_models.Order.objects.filter(
        delivery_task__dl_task_status__in=['failed', 'rejected', 'cancelled', 'non_reachable'],
        business=business.business_id
    ).select_related(
        'business',
        'pickup_location',
        'address_verified_by',
        'verified_by',
    ).prefetch_related(
        'order_items',
        'order_items__product',
        'order_items__product__product_category',
        'delivery_task',
        'delivery_task__driver',
        'delivery_task__business',
    ).order_by('-id')

    logger.debug(f"Fetching unsuccessful orders for business {business.business_id}")

    default_page = 1
    page = request.GET.get('page', default_page)
    # Read per_page from request, with validation (valid: 10, 25, 50, 100)
    per_page = request.GET.get('per_page', '10')
    try:
        per_page = int(per_page)
        if per_page not in [10, 25, 50, 100]:
            per_page = 10
    except (ValueError, TypeError):
        per_page = 10
    paginator = Paginator(orders, per_page)

    try:
        orders = paginator.page(page)
        logger.debug(f"Displaying page {page} with {len(orders)} unsuccessful orders")
    except PageNotAnInteger:
        orders = paginator.page(default_page)
        logger.debug(f"Invalid page number, displaying page {default_page}")
    except EmptyPage:
        orders = paginator.page(paginator.num_pages)
        logger.debug(f"Empty page, displaying last page {paginator.num_pages}")

    context = {
        'orders': orders,
        'business': business,
        'per_page': str(per_page),  # String for template comparison
    }
    return render(request, 'orders/order_unsuccessful_list.html', context)


@login_required(login_url='account_login')
@business_access_required()
def latest_orders_list(request):
    business = get_cached_business(request)
    if not business:
        messages.error(request, 'Business not found.')
        return redirect('business:business_dashboard')
    logger.debug(f"User {request.user.id} accessing latest orders for business {business.business_id}")

    orders = orders_models.Order.objects.filter(
        business=business.business_id
    ).select_related(
        'business',
        'pickup_location',
    ).order_by('-id')[:5]

    logger.debug(f"Fetched {len(orders)} latest orders")

    default_page = 1
    page = request.GET.get('page', default_page)
    # Read per_page from request, with validation (valid: 10, 25, 50, 100)
    per_page = request.GET.get('per_page', '10')
    try:
        per_page = int(per_page)
        if per_page not in [10, 25, 50, 100]:
            per_page = 10
    except (ValueError, TypeError):
        per_page = 10
    paginator = Paginator(orders, per_page)

    try:
        orders = paginator.page(page)
        logger.debug(f"Displaying page {page}")
    except PageNotAnInteger:
        orders = paginator.page(default_page)
        logger.debug(f"Invalid page number, displaying page {default_page}")
    except EmptyPage:
        orders = paginator.page(paginator.num_pages)
        logger.debug(f"Empty page, displaying last page {paginator.num_pages}")

    context = {
        'orders': orders,
        'business': business,
        'per_page': str(per_page),  # String for template comparison
    }
    return render(request, 'orders/order_list_view.html', context)

# order uploading section ----------------------------------------------------------------



@login_required(login_url='account_login')
@business_permission_required(BusinessPermissions.ORDER_CREATE)
def order_upload_file(request):
    if request.method == 'POST':
        form = orders_forms.OrderFileUploadForm(request.POST, request.FILES)
        if form.is_valid():
            file = request.FILES['file']
            if file.name.endswith('.csv'):
                data = pd.read_csv(file)
            elif file.name.endswith('.xlsx'):
                data = pd.read_excel(file)
            else:
                messages.error(request, 'Unsupported file format. Please upload a CSV or Excel file.')
                return redirect('orders:order_upload_file')
            
            request.session['uploaded_data'] = data.to_dict(orient='records')
            return redirect('orders:order_upload_review_data')
    else:
        form = orders_forms.OrderFileUploadForm()
    
    business = get_cached_business(request)
    context = {
        'form': form,
        'business': business
    }
    return render(request, 'orders/order_file_upload.html',  context)

@login_required(login_url='account_login')
@business_access_required()
def order_upload_review_data(request):
    if 'uploaded_data' not in request.session:
        messages.error(request, 'No data to review. Please upload a file first.')
        return redirect('orders:order_upload_file')

    business = request.current_business
    data = request.session['uploaded_data']
    logger.debug(f"Review data: {len(data)} rows to process")

    if request.method == 'POST':
        logger.debug(f"Processing POST request with {len(data)} rows")
        # Process edited data
        edited_data = []
        for i, row in enumerate(data):
            logger.debug(f"Processing row {i}")

            edited_row = {}
            for key in row.keys():
                field_name = f'data[{i}][{key}]'
                edited_row[key] = request.POST.get(field_name, row[key])
            edited_data.append(edited_row)
            logger.debug(f"Row {i} edited data prepared")

        for idx, edited_row in enumerate(edited_data):
            order_form = orders_forms.AddOrderForm(edited_row)
            if order_form.is_valid():
                logger.debug(f"Order form valid for row {idx}")
                order = order_form.save(commit=False)
                order.business = business
                order.save()
            else:
                logger.warning(f"Order form invalid for row {idx}: {order_form.errors}")
                messages.error(request, f'Error in row {idx}: {order_form.errors}')
                return redirect('orders:order_upload_review_data')

        del request.session['uploaded_data']
        messages.success(request, 'Data successfully uploaded to the database.')
        return redirect('orders:orders_all_list')

    return render(request, 'orders/order_upload_review.html', {'data': data})


@login_required(login_url='account_login')
@business_permission_required(BusinessPermissions.ORDER_CREATE)
def bulk_order_entry(request):
    """
    Excel-like bulk order entry view for clients.
    Allows entering multiple orders in a spreadsheet-style interface.
    """
    # Business is injected by the decorator
    business = request.current_business
    logger.info(f"User {request.user.id} accessing bulk order entry for business {business.business_id}")

    # Show fulfillment stores first when fulfillment service is enabled
    pickup_locations = business_models.PickupLocation.objects.filter(
        business_id=business.business_id
    ).order_by('-is_fulfilment_center', 'pickup_location_title')

    if not pickup_locations.exists():
        messages.warning(request, "Please add a pickup location or link a fulfillment center first.")
        return redirect('business:pickup_location_list')

    if request.method == 'POST':
        # Process bulk order data
        success_count = 0
        error_count = 0
        errors = []

        # Parse the form data
        i = 0
        while f'data[{i}][customer_name]' in request.POST:
            row_data = {
                'client_order_code': request.POST.get(f'data[{i}][order_id]', ''),
                'customer_name': request.POST.get(f'data[{i}][customer_name]', ''),
                'customer_phone': request.POST.get(f'data[{i}][phone1]', ''),
                'customer_whatsapp': request.POST.get(f'data[{i}][phone2_whatsapp]', ''),
                'customer_address': request.POST.get(f'data[{i}][customer_address]', ''),
                'dl_zone': request.POST.get(f'data[{i}][zone_no]', '') or 0,
                'dl_street': request.POST.get(f'data[{i}][street_no]', '') or 0,
                'dl_building': request.POST.get(f'data[{i}][building_no]', '') or 0,
                'deadline_date': request.POST.get(f'data[{i}][deadline_date]', ''),
                'order_notes': request.POST.get(f'data[{i}][note]', ''),
                'pickup_location': pickup_locations.first().id,
            }

            # Skip empty rows
            if not row_data['customer_name'] and not row_data['client_order_code']:
                i += 1
                continue

            # Create the order
            try:
                order = orders_models.Order(
                    business=business,
                    client_order_code=row_data['client_order_code'] or f"BULK-{dj_timezone.localtime().strftime('%Y%m%d%H%M%S')}-{i}",
                    customer_name=row_data['customer_name'],
                    customer_phone=row_data['customer_phone'],
                    customer_whatsapp=row_data['customer_whatsapp'] or row_data['customer_phone'],
                    customer_address=row_data['customer_address'],
                    dl_zone=int(row_data['dl_zone']) if row_data['dl_zone'] else 0,
                    dl_street=int(row_data['dl_street']) if row_data['dl_street'] else 0,
                    dl_building=int(row_data['dl_building']) if row_data['dl_building'] else 0,
                    deadline_date=row_data['deadline_date'],
                    order_notes=row_data['order_notes'],
                    pickup_location=pickup_locations.first(),
                )
                order.save()

                # Add products if provided
                package_desc = request.POST.get(f'data[{i}][package_desc]', '')
                qty = request.POST.get(f'data[{i}][qty]', '1')
                price = request.POST.get(f'data[{i}][price]', '0')

                if package_desc:
                    # Store product info in order notes for now
                    order.order_notes = f"{order.order_notes} | Product: {package_desc}, Qty: {qty}, Price: {price}".strip(' |')
                    order.save()

                success_count += 1
                logger.info(f"Created order {order.order_number} via bulk entry")

            except Exception as e:
                error_count += 1
                errors.append(f"Row {i+1}: {str(e)}")
                logger.error(f"Error creating order in row {i+1}: {str(e)}")

            i += 1

        if success_count > 0:
            messages.success(request, f"Successfully created {success_count} order(s).")
        if error_count > 0:
            messages.warning(request, f"Failed to create {error_count} order(s). Errors: {'; '.join(errors[:5])}")

        return redirect('orders:orders_all_list')

    # Get products for this business
    from product import models as product_models
    products = product_models.Product.objects.filter(
        business=business
    ).select_related('color', 'unit').order_by('item_name')

    context = {
        'business': business,
        'pickup_locations': pickup_locations,
        'products': products,
    }
    return render(request, 'orders/bulk_order_entry.html', context)




# order creation ----------------------------------------------------------------

@login_required(login_url='account_login')
def mobile_product_row_partial(request):
    """HTMX endpoint: returns a single mobile product row with the next index."""
    try:
        row_index = int(request.GET.get('index', 0))
    except (TypeError, ValueError):
        row_index = 0
    if row_index < 0:
        row_index = 0
    return render(request, 'orders/parts/_mobile_product_row.html', {
        'row_index': row_index,
    })


@login_required(login_url='account_login')
@business_permission_required(BusinessPermissions.ORDER_CREATE)
def add_order(request):
    import json

    # Business is injected by the decorator
    business = request.current_business
    logger.debug(f"User {request.user.id} adding order for business {business.business_id}")

    # Show fulfillment stores first when fulfillment service is enabled
    pickup_locations = business_models.PickupLocation.objects.filter(
        business_id=business.business_id
    ).order_by('-is_fulfilment_center', 'pickup_location_title')

    if not pickup_locations:
        # If fulfillment is active, try to auto-create the missing pickup location from the warehouse link
        if business.fulfillment_service_status == 'active':
            from warehouse.models import SellerWarehouseLink
            link = SellerWarehouseLink.objects.filter(
                business_id=business.business_id, is_active=True
            ).select_related('default_location__warehouse').first()
            if link and link.default_location:
                wl = link.default_location
                pickup_location, _ = business_models.PickupLocation.objects.update_or_create(
                    business=business,
                    warehouse=wl.warehouse,
                    defaults={
                        'pickup_location_title': f"{wl.warehouse.name} - Fulfillment",
                        'locality': wl.address or wl.warehouse.city or 'Warehouse Location',
                        'is_fulfilment_center': True,
                        'pickup_status': 'active',
                        'pickup_zone_no': wl.zone_number,
                        'pickup_lat': wl.latitude,
                        'pickup_lon': wl.longitude,
                    }
                )
                logger.info(f"Auto-created missing fulfillment pickup location for business {business.business_id}")
                pickup_locations = business_models.PickupLocation.objects.filter(
                    business_id=business.business_id
                ).order_by('-is_fulfilment_center', 'pickup_location_title')
            else:
                messages.warning(request, "Please add a pickup location or link a fulfillment center first.")
                return redirect('business:pickup_location_list')
        else:
            logger.debug("No pickup locations, redirecting to stores setup")
            messages.warning(request, "Please add a pickup location or link a fulfillment center first.")
            return redirect('business:pickup_location_list')
    else:
        if request.method == 'POST':
            logger.debug("Processing POST form for add_order")
            form = orders_forms.AddOrderForm(
                request.POST,
                business_id=business.business_id,
                business_code=business.business_code,
                business=business,
            )

            if form.is_valid():
                logger.debug("Form is valid, saving order")
                order = form.save(commit=False)
                order.business = business_models.Business.objects.get(
                    business_id=business.business_id)
                logger.debug(f"Order business_id: {order.business_id}")
                try:
                    with transaction.atomic():
                        order.save()
                except IntegrityError:
                    # Race / duplicate order number that slipped past form validation
                    form.add_error(
                        'client_order_code',
                        'This order number already exists for your business. '
                        'Please use a different order number.'
                    )
                    logger.warning(
                        f"Duplicate client_order_code on add_order for business "
                        f"{business.business_id}: {order.client_order_code}"
                    )
                else:
                    logger.info(f"Order created with id: {order.id}")

                    # Save inline products if any were submitted
                    inline_product_ids = request.POST.getlist('inline_product_id[]')
                    inline_quantities = request.POST.getlist('inline_quantity[]')
                    inline_unit_prices = request.POST.getlist('inline_unit_price[]')
                    inline_notes_list = request.POST.getlist('inline_notes[]')

                    if any(pid for pid in inline_product_ids if pid):
                        from product import models as product_models
                        valid_pids = [pid for pid in inline_product_ids if pid]
                        products_map = {
                            str(p.id): p for p in product_models.Product.objects.filter(
                                id__in=valid_pids, business=business
                            )
                        }
                        items_saved = 0
                        for i, pid in enumerate(inline_product_ids):
                            if not pid:
                                continue
                            product = products_map.get(str(pid))
                            if not product:
                                continue
                            try:
                                qty = int(inline_quantities[i]) if i < len(inline_quantities) and inline_quantities[i] else 1
                                price = float(inline_unit_prices[i]) if i < len(inline_unit_prices) and inline_unit_prices[i] else float(product.item_price)
                                notes = inline_notes_list[i] if i < len(inline_notes_list) else ''
                                orders_models.OrderItem.objects.create(
                                    order=order, product=product,
                                    quantity=qty, unit_price=price, notes=notes
                                )
                                items_saved += 1
                            except (ValueError, IndexError) as e:
                                logger.warning(f"Inline product save error: {e}")
                        if items_saved:
                            logger.info(f"{items_saved} inline product(s) saved for order {order.id}")

                    # Only redirect to add products page if fulfillment service is enabled AND no inline products were added
                    if business.fulfillment_service_enabled and not any(pid for pid in inline_product_ids if pid):
                        return redirect('orders:add_order_product', order_id=order.id)
                    else:
                        messages.success(request, 'Order created successfully.')
                        return redirect('orders:orders_all_list')
        else:
            logger.debug("Loading add_order form")
            form = orders_forms.AddOrderForm(
                business_id=business.business_id,
                business_code=business.business_code,
                business=business
            )

        # Prepare pickup locations data for JavaScript with lat/lon
        pickup_locations_dict = {}
        for location in pickup_locations:
            pickup_locations_dict[str(location.id)] = {
                'id': location.id,
                'title': location.pickup_location_title,
                'zone': location.pickup_zone_no if location.pickup_zone_no else None,
                'street': location.pickup_street_no if location.pickup_street_no else None,
                'building': location.pickup_building_no if location.pickup_building_no else None,
                'lat': float(location.pickup_lat) if location.pickup_lat else None,
                'lon': float(location.pickup_lon) if location.pickup_lon else None,
            }
        pickup_locations_json = json.dumps(pickup_locations_dict)

        # Determine default pickup ID for mobile pre-selection
        # Priority: active fulfillment center > is_default flag > first
        default_pickup_id = None
        if business.fulfillment_service_status == 'active':
            fc = next((loc for loc in pickup_locations if loc.is_fulfilment_center), None)
            if fc:
                default_pickup_id = fc.id
        if not default_pickup_id:
            df = next((loc for loc in pickup_locations if loc.is_default), None)
            if df:
                default_pickup_id = df.id
        if not default_pickup_id and pickup_locations:
            default_pickup_id = pickup_locations[0].id

    return render(request, 'orders/order_add.html', {
        'form': form,
        'business': business,
        'pickup_locations': pickup_locations,
        'pickup_locations_json': pickup_locations_json,
        'default_pickup_id': default_pickup_id,
    })


@login_required(login_url='account_login')
@business_permission_required(BusinessPermissions.ORDER_CREATE)
def add_order_bulk(request):
    """
    Handle bulk order submission from Excel-like table view.
    Processes multiple orders submitted via the table interface.
    """
    import json
    from django.contrib import messages

    if request.method != 'POST':
        return redirect('orders:add_order')

    business = get_cached_business(request)
    if not business:
        messages.error(request, 'Business not found.')
        return redirect('orders:add_order')

    # Parse the form data - orders are submitted as orders[0][field], orders[1][field], etc.
    orders_data = {}
    for key, value in request.POST.items():
        if key.startswith('orders['):
            # Parse orders[0][customer_name] format
            import re
            match = re.match(r'orders\[(\d+)\]\[(\w+)\]', key)
            if match:
                index = int(match.group(1))
                field = match.group(2)
                if index not in orders_data:
                    orders_data[index] = {}
                orders_data[index][field] = value

    # Process each order
    created_count = 0
    errors = []

    for index in sorted(orders_data.keys()):
        order_data = orders_data[index]

        # Skip empty rows (no customer name)
        if not order_data.get('customer_name', '').strip():
            continue

        try:
            # Get pickup location if provided
            pickup_location = None
            if order_data.get('pickup_location'):
                try:
                    pickup_location = business_models.PickupLocation.objects.get(
                        id=order_data['pickup_location'],
                        business=business
                    )
                except business_models.PickupLocation.DoesNotExist:
                    pass

            # Create order
            order = orders_models.Order(
                business=business,
                pickup_location=pickup_location,
                client_order_code=order_data.get('client_order_code', ''),
                customer_name=order_data.get('customer_name', ''),
                customer_phone=order_data.get('customer_phone', ''),
                customer_whatsapp=order_data.get('customer_whatsapp', ''),
                dl_zone=order_data.get('dl_zone', '0'),
                dl_street=order_data.get('dl_street', '0'),
                dl_building=order_data.get('dl_building', '0'),
                customer_address=order_data.get('customer_address', ''),
                cod_status_by_client=order_data.get('cod_status_by_client', 'unpaid') if order_data.get('cod_status_by_client') != 'include' else 'unpaid',
                cod_amount=order_data.get('cod_amount') or 0,
                order_notes=order_data.get('order_notes', ''),
                order_status=order_data.get('order_status', 'to_review'),
            )
            order.save()
            created_count += 1

        except Exception as e:
            errors.append(f"Row {index + 1}: {str(e)}")

    if created_count > 0:
        messages.success(request, f'Successfully created {created_count} order(s).')

    if errors:
        for error in errors[:5]:  # Show max 5 errors
            messages.warning(request, error)
        if len(errors) > 5:
            messages.warning(request, f'... and {len(errors) - 5} more errors.')

    if created_count == 0 and not errors:
        messages.info(request, 'No orders were created. Please fill in at least the customer name.')

    return redirect('orders:orders_all_list')


# add products to order
@login_required(login_url='account_login')
def add_order_product(request, order_id):
    try:
        # IDOR FIX: Verify order belongs to user's business
        business = get_cached_business(request)
        if not business:
            messages.error(request, 'Business not found.')
            return redirect('orders:orders_all_list')
        order = orders_models.Order.objects.get(id=order_id, business=business)

        logger.info(f"User {request.user.id} adding products to order {order_id}")

        # Get existing items for this order
        existing_items = orders_models.OrderItem.objects.filter(order=order).select_related('product')

        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'

        if request.method == 'POST':
            logger.info(f"Processing product addition for order {order_id}")

            # Handle multiple products from the form
            products_added = 0
            errors = []

            # Get all product entries from POST data
            product_ids = request.POST.getlist('product_id[]')
            quantities = request.POST.getlist('quantity[]')
            unit_prices = request.POST.getlist('unit_price[]')
            notes_list = request.POST.getlist('notes[]')

            # Fetch all products at once to avoid N+1 queries
            from product import models as product_models
            valid_product_ids = [pid for pid in product_ids if pid]
            products_map = {
                str(p.id): p for p in product_models.Product.objects.filter(
                    id__in=valid_product_ids, business=business
                )
            }

            added_items = []
            for i, product_id in enumerate(product_ids):
                if not product_id:  # Skip empty product selections
                    continue

                try:
                    product = products_map.get(str(product_id))
                    if not product:
                        errors.append(f"Product #{i+1} not found")
                        continue

                    quantity = int(quantities[i]) if i < len(quantities) and quantities[i] else 1
                    unit_price = float(unit_prices[i]) if i < len(unit_prices) and unit_prices[i] else float(product.item_price)
                    notes = notes_list[i] if i < len(notes_list) else ''

                    # Create the order item
                    order_item = orders_models.OrderItem(
                        order=order,
                        product=product,
                        quantity=quantity,
                        unit_price=unit_price,
                        notes=notes
                    )
                    order_item.save()
                    products_added += 1
                    added_items.append({
                        'id': order_item.id,
                        'name': f"{product.brand_name} {product.item_name}".strip(),
                        'sku': product.item_sku or '',
                        'qty': quantity,
                        'unit_price': float(unit_price),
                        'total': float(order_item.total_price or 0),
                    })

                except (ValueError, IndexError) as e:
                    errors.append(f"Invalid data for product #{i+1}: {str(e)}")

            if products_added > 0:
                logger.info(f"{products_added} product(s) added successfully to order {order_id}")
                if is_ajax:
                    return JsonResponse({'success': True, 'added': products_added, 'items': added_items})
                messages.success(request, f"{products_added} product(s) added to order successfully")
                return redirect('orders:order_update', order_id=order_id)
            elif errors:
                if is_ajax:
                    return JsonResponse({'success': False, 'error': errors[0]})
                for error in errors:
                    messages.error(request, error)
            else:
                if is_ajax:
                    return JsonResponse({'success': False, 'error': 'No products were selected'})
                messages.warning(request, "No products were selected")

        # Get all products for this business (for Select2 AJAX search)
        from product import models as product_models

        # Check if fulfillment/inventory is enabled
        inventory_enabled = business.fulfillment_service_enabled

        data = {
            'order': order,
            'business': business,
            'existing_items': existing_items,
            'inventory_enabled': inventory_enabled,
        }
        return render(request, 'orders/order_product_add.html', data)

    except orders_models.Order.DoesNotExist:
        logger.warning(f"Order {order_id} not found or unauthorized access by user {request.user.id}")
        messages.error(request, "Order not found")
        return redirect('orders:orders_all_list')
    except business_models.Business.DoesNotExist:
        logger.error(f"Business not found for user {request.user.id}")
        messages.error(request, "Business not found")
        return redirect('business:business_dashboard')


@login_required(login_url='account_login')
def product_search_api(request):
    """
    AJAX endpoint for product search with Select2.
    Returns products matching search query with price and inventory info.
    Requires minimum 3 characters to trigger search.
    """
    # Support business param from workforce/staff pages
    business_id = request.GET.get('business', '')
    if business_id and request.user.is_staff:
        from business.models import Business as BusinessModel
        try:
            business = BusinessModel.objects.get(business_id=business_id)
        except BusinessModel.DoesNotExist:
            business = None
    else:
        business = get_cached_business(request)
    if not business:
        return JsonResponse({'results': [], 'pagination': {'more': False}})
    try:
        search_term = request.GET.get('q', '').strip()

        from product import models as product_models

        # Base queryset filtered by business
        products_qs = product_models.Product.objects.filter(
            business=business
        ).select_related('unit')

        # Apply search filter if term provided
        if search_term:
            products_qs = products_qs.filter(
                Q(item_name__icontains=search_term) |
                Q(brand_name__icontains=search_term) |
                Q(item_sku__icontains=search_term)
            )

        products = list(products_qs[:30])  # Limit to 30 results

        # Fetch all inventory at once to avoid N+1 queries
        inventory_map = {}
        if business.fulfillment_service_enabled and products:
            inventory_map = {
                inv.item_sku_id: inv.item_quantity
                for inv in product_models.ProductInventory.objects.filter(
                    item_sku__in=products
                )
            }

        results = []
        for product in products:
            # Get inventory status if fulfillment is enabled
            inventory_qty = None
            if business.fulfillment_service_enabled:
                inventory_qty = inventory_map.get(product.id, 0)

            result = {
                'id': product.id,
                'text': f"{product.brand_name} {product.item_name}".strip(),
                'item_name': product.item_name,
                'sku': product.item_sku,
                'item_sku': product.item_sku,
                'price': float(product.item_price),
                'item_price': float(product.item_price),
                'unit': product.unit.short_code if product.unit else '',
                'inventory': inventory_qty,
            }
            results.append(result)

        return JsonResponse({
            'results': results,
            'pagination': {'more': False}
        })

    except business_models.Business.DoesNotExist:
        return JsonResponse({'results': [], 'error': 'Business not found'}, status=404)
    except Exception as e:
        logger.error(f"Product search error: {str(e)}")
        return JsonResponse({'results': [], 'error': str(e)}, status=500)



#AddOrderWithProduct
@login_required(login_url='account_login')
@business_permission_required(BusinessPermissions.ORDER_CREATE)
def add_order_with_product(request):
    # Business is injected by the decorator
    business = request.current_business
    OrderFormset = inlineformset_factory(orders_models.Order, orders_models.OrderItem, form=orders_forms.AddOrderProductsForm, extra=1)
    if request.method == 'POST':
        order_product_formset = OrderFormset(request.POST, queryset=orders_models.OrderItem.objects.none())

        if order_product_formset.is_valid():
                order_product_formset.save()

                return redirect('orders:orders_all_list')

    else:

        order_product_formset = OrderFormset(queryset=orders_models.OrderItem.objects.none())
        
    
    context = {
        'business' :  business,
        
        'order_product_formset': order_product_formset,
    }
    return render(request, 'orders/order_with_product_add.html', context)
    








#costumer side*********************************************************************


@login_required(login_url='account_login')
@business_access_required()
def deliver_to_here(request, pickup_id):
    business = request.current_business
    pickup_location = business_models.PickupLocation.objects.filter(
        id=pickup_id, business_id=business.business_id).first()
    if not pickup_location:
        messages.error(request, "Pickup location not found.")
        return redirect('business:pickup_location_list')

    if request.method == 'POST':
        form = orders_forms.UpdateOrderForm(request.POST)
        logger.debug('Form validation checking in deliver_to_here')
        if form.is_valid():
            logger.debug('Form is valid in deliver_to_here')
            order = form.save(commit=False)
            order.business = business
            order.save()
            return redirect('orders:orders_all_list')
    else:
        form = orders_forms.UpdateOrderForm()

    context = {
        'form': form,
        'business': business,
    }
    return render(request, 'orders/order_update.html', context)


@login_required(login_url='account_login')
def pick_from_here(request, pickup_id):
    """Add order with a pre-selected pickup location."""
    import json

    business = get_cached_business(request)
    if not business:
        messages.error(request, 'Business not found.')
        return redirect('business:business_dashboard')
    pickup_location = business_models.PickupLocation.objects.filter(
        id=pickup_id, business_id=business.business_id).first()

    if not pickup_location:
        messages.error(request, "Pickup location not found.")
        return redirect('business:pickup_location_list')

    # Show fulfillment stores first when fulfillment service is enabled
    pickup_locations = business_models.PickupLocation.objects.filter(
        business_id=business.business_id
    ).order_by('-is_fulfilment_center', 'pickup_location_title')

    if request.method == 'POST':
        form = orders_forms.AddOrderForm(request.POST)
        if form.is_valid():
            order = form.save(commit=False)
            order.business = business
            order.save()
            return redirect('orders:add_order_product', order_id=order.id)
    else:
        form = orders_forms.AddOrderForm(
            business_id=business.business_id,
            business_code=business.business_code,
            initial={'pickup_location': pickup_location}
        )

    # Prepare pickup locations data for JavaScript
    pickup_locations_dict = {}
    for location in pickup_locations:
        pickup_locations_dict[str(location.id)] = {
            'id': location.id,
            'title': location.pickup_location_title,
            'zone': location.pickup_zone_no if location.pickup_zone_no else None,
            'street': location.pickup_street_no if location.pickup_street_no else None,
            'building': location.pickup_building_no if location.pickup_building_no else None,
            'lat': float(location.pickup_lat) if location.pickup_lat else None,
            'lon': float(location.pickup_lon) if location.pickup_lon else None,
        }
    pickup_locations_json = json.dumps(pickup_locations_dict)

    return render(request, 'orders/order_add.html', {
        'form': form,
        'pickup_locations': pickup_locations,
        'pickup_locations_json': pickup_locations_json,
    })

@login_required(login_url='account_login')
@business_permission_required(BusinessPermissions.ORDER_EDIT)
def order_update(request, order_id):
    try:
        # Business is injected by the decorator, verify order belongs to it
        business = request.current_business
        order = orders_models.Order.objects.get(id=order_id, business=business)

        logger.info(f"User {request.user.id} updating order {order_id}")

        # Check if user is staff (to show/hide task_created field)
        is_staff = hasattr(request.user, 'profile') and request.user.profile.is_staff

        # Block editing published, delivered, or cancelled orders
        if order.order_status in ('publish', 'delivered', 'cancelled'):
            logger.warning(f"Cannot update order {order_id} - status is {order.order_status}")
            messages.error(request, f'Cannot edit a {order.get_order_status_display()} order.')
            return redirect('orders:orders_all_list')

        if request.method == 'POST':
            form = orders_forms.UpdateOrderForm(request.POST, instance=order, is_staff=is_staff, business_id=business.business_id)

            if form.is_valid():
                logger.info(f"Order {order_id} updated successfully")
                form.save()
                # Fire auto flow for order edit
                try:
                    from core.auto_flow_executor import execute_flows_for_trigger
                    execute_flows_for_trigger('staff_order_edit', extra_context={
                        'order_number': order.order_number or '',
                        'customer_name': order.customer_name or '',
                        'customer_phone': order.customer_phone or '',
                        'customer_address': order.customer_address or '',
                        'cod_amount': str(order.cod_amount) if order.cod_amount else '0',
                        'business_name': str(order.business) if order.business else '',
                    })
                except Exception as e:
                    logger.warning(f"Auto flow failed for order edit {order_id}: {e}")
                messages.success(request, 'Order updated successfully.')
                return redirect('orders:orders_all_list')
            else:
                logger.warning(f"Invalid order update form for order {order_id}: {form.errors}")
        else:
            form = orders_forms.UpdateOrderForm(instance=order, is_staff=is_staff, business_id=business.business_id)

        # Fetch existing order items for the products section
        order_items = order.order_items.select_related('product').all()
        items_total = sum(item.total_price or 0 for item in order_items)

        context = {
            'form': form,
            'order': order,
            'order_id': order_id,
            'order_items': order_items,
            'items_total': items_total,
        }
        return render(request, 'orders/order_update.html', context)

    except orders_models.Order.DoesNotExist:
        logger.warning(f"Order {order_id} not found or unauthorized access by user {request.user.id}")
        messages.error(request, "Order not found")
        return redirect('orders:orders_all_list')
    except business_models.Business.DoesNotExist:
        logger.error(f"Business not found for user {request.user.id}")
        messages.error(request, "Business not found")
        return redirect('business:business_dashboard')


@login_required(login_url='account_login')
@business_permission_required(BusinessPermissions.ORDER_DELETE)
def delete_order(request, order_id):
    try:
        # Business is injected by the decorator, verify order belongs to it
        business = request.current_business
        order = orders_models.Order.objects.get(id=order_id, business=business)

        logger.info(f"User {request.user.id} deleting order {order_id}")

        # Block deleting published, delivered, or cancelled orders
        if order.order_status in ('publish', 'delivered', 'cancelled'):
            logger.warning(f"Cannot delete order {order_id} - status is {order.order_status}")
            messages.error(request, f'Cannot delete a {order.get_order_status_display()} order.')
            return redirect('orders:orders_all_list')

        # Clean up related records that use on_delete=DO_NOTHING
        # These FK constraints would block order deletion in PostgreSQL.
        # Atomic so a failed order delete doesn't strand already-deleted relations.
        from delivery import models as delivery_models
        with transaction.atomic():
            delivery_models.DeliveryTask.objects.filter(order=order).delete()
            delivery_models.DlAddressUpdate.objects.filter(order=order).delete()
            orders_models.OrderBarcode.objects.filter(order=order).delete()
            order.delete()
        logger.info(f"Order {order_id} deleted successfully")
        messages.success(request, "Order deleted successfully")
        return redirect('orders:orders_all_list')

    except orders_models.Order.DoesNotExist:
        logger.warning(f"Order {order_id} not found or unauthorized access by user {request.user.id}")
        messages.error(request, "Order not found")
        return redirect('orders:orders_all_list')


@login_required(login_url='account_login')
@business_permission_required(BusinessPermissions.ORDER_VIEW)
def order_details(request, order_id):
    try:
        # Business is injected by the decorator, verify order belongs to it
        business = request.current_business
        order = orders_models.Order.objects.select_related(
            'business', 'pickup_location', 'address_verified_by', 'verified_by'
        ).prefetch_related(
            'delivery_task', 'delivery_task__driver'
        ).get(id=order_id, business=business)

        logger.info(f"User {request.user.id} viewing order details for order {order_id}")

        # Get delivery task for mobile view
        delivery_task = order.delivery_task.first()
        order_items = orders_models.OrderItem.objects.filter(order=order)

        # Get failure reason from status history if task failed
        fail_notes = None
        if delivery_task and delivery_task.dl_task_status == 'failed':
            fail_entry = orders_models.OrderStatusHistory.objects.filter(
                order=order, field_name='dl_task_status', new_value='failed'
            ).exclude(notes='').exclude(notes__isnull=True).order_by('-created_at').first()
            if fail_entry:
                fail_notes = fail_entry.notes

        # Get delivery proofs
        delivery_proofs = []
        if delivery_task:
            delivery_proofs = delivery_task.delivery_proofs.all()

        # Reconfirm events — every publish→ready_to_pickup transition (client/staff
        # clicking Reconfirm on a failed delivery). Paired with the matching
        # "Reconfirmed by …" comment (same second) for the free-text note.
        reconfirm_history = orders_models.OrderStatusHistory.objects.filter(
            order=order,
            field_name='order_status',
            old_value='publish',
            new_value='ready_to_pickup',
        ).select_related('changed_by').order_by('created_at')
        reconfirm_comments = list(
            order.order_comments.filter(name__istartswith='Reconfirmed by').order_by('created_at')
        )
        reconfirm_events = []
        for hist in reconfirm_history:
            # find the closest reconfirm comment after this history entry (within 5s)
            body = ''
            for c in reconfirm_comments:
                delta = (c.created_at - hist.created_at).total_seconds()
                if -2 <= delta <= 10:
                    body = c.body
                    break
            reconfirm_events.append({
                'created_at': hist.created_at,
                'by': (hist.changed_by.get_full_name() if hist.changed_by else '') or (hist.changed_by.username if hist.changed_by else ''),
                'note': body,
            })

        data = {
            'order': order,
            'delivery_task': delivery_task,
            'order_items': order_items,
            'fail_notes': fail_notes,
            'delivery_proofs': delivery_proofs,
            'reconfirm_events': reconfirm_events,
            'can_edit_order': user_has_business_permission(request.user, BusinessPermissions.ORDER_EDIT),
            'can_delete_order': user_has_business_permission(request.user, BusinessPermissions.ORDER_DELETE),
        }

        # Check if this is being loaded in a slide-in panel (via HTMX or query param)
        is_panel = request.GET.get('panel') == '1'
        is_htmx = request.headers.get('HX-Request') == 'true'
        hx_target = request.headers.get('HX-Target', '')
        if is_panel or (is_htmx and hx_target == 'orderDetailContent'):
            return render(request, 'orders/parts/order_detail_panel.html', data)

        return render(request, 'orders/order_details.html', data)

    except orders_models.Order.DoesNotExist:
        logger.warning(f"Order {order_id} not found or unauthorized access by user {request.user.id}")
        messages.error(request, "Order not found")
        return redirect('orders:orders_all_list')


@require_POST
@login_required(login_url='account_login')
@business_permission_required(BusinessPermissions.ORDER_EDIT)
def update_order_zone(request, order_id):
    """Update order delivery zone and coordinates (from AI parse result)"""
    try:
        business = request.current_business
        order = get_object_or_404(
            orders_models.Order.objects.select_related('business'),
            id=order_id, business=business
        )
        data = json.loads(request.body)
        zone_number = data.get('zone_number')
        street_number = data.get('street_number')
        building_number = data.get('building_number')
        latitude = data.get('latitude')
        longitude = data.get('longitude')

        if not zone_number:
            return JsonResponse({'success': False, 'error': 'Zone number is required'}, status=400)

        from delivery import models as delivery_models
        # Look up zone name (save even if zone not in ZoneName table)
        zone = delivery_models.ZoneName.objects.filter(zone_number=zone_number, is_active=True).first()
        zone_display = zone.zone_name if zone else f'Zone {zone_number}'

        old_zone = order.dl_zone
        order.dl_zone = zone_number
        if street_number:
            order.dl_street = str(street_number)
        if building_number:
            order.dl_building = str(building_number)

        # Save coordinates to order
        coords_accuracy = data.get('coords_accuracy')
        coords_saved = False
        if latitude and longitude:
            order.latitude = latitude
            order.longitude = longitude
            if coords_accuracy:
                order.coords_accuracy = coords_accuracy
            elif building_number:
                order.coords_accuracy = 'exact'
            else:
                order.coords_accuracy = 'street'
            coords_saved = True

        with transaction.atomic():
            order.save()

            # Also update delivery task address for legacy compatibility
            if latitude and longitude:
                delivery_task = delivery_models.DeliveryTask.objects.filter(order=order).first()
                if delivery_task and delivery_task.dl_to_address:
                    dl_address = delivery_task.dl_to_address
                    dl_address.dl_latitude = latitude
                    dl_address.dl_longitude = longitude
                    dl_address.dl_zone = zone_number
                    if street_number:
                        dl_address.dl_street = str(street_number)
                    if building_number:
                        dl_address.dl_building = str(building_number)
                    dl_address.save()

            notes = f'Zone updated from AI parse: {zone_display}'
            if coords_saved:
                notes += f' | Coordinates saved: {latitude}, {longitude}'
            orders_models.OrderVerificationLog.objects.create(
                order=order,
                verified_by=request.user,
                action='zone_updated',
                old_status=str(old_zone) if old_zone else 'None',
                new_status=str(zone_number),
                notes=notes
            )

        return JsonResponse({
            'success': True,
            'message': f'Zone updated to {zone_number} ({zone_display})' + (' with coordinates' if coords_saved else ''),
            'zone_number': zone_number,
            'zone_name': zone_display,
            'coordinates_saved': coords_saved
        })
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid JSON data'}, status=400)
    except Exception as e:
        logger.exception("Error updating zone for order %s: %s", order_id, str(e))
        return JsonResponse({'success': False, 'error': 'An error occurred while updating zone'}, status=400)


@login_required(login_url='account_login')
@business_access_required()
def update_order_product(request, order_id):
    """Update order product items using OrderItem model"""
    # IDOR FIX: Verify order belongs to user's business
    business = request.current_business
    try:
        order = orders_models.Order.objects.get(id=order_id, business=business)
    except orders_models.Order.DoesNotExist:
        messages.error(request, "Order not found")
        return redirect('orders:orders_all_list')
    order_items = orders_models.OrderItem.objects.filter(order=order)

    if request.method == 'POST':
            # Handle JSON delete request
            if request.content_type == 'application/json':
                data = json.loads(request.body)
                action = data.get('action')
                if action == 'delete':
                    item_id = data.get('item_id')
                    try:
                        item = orders_models.OrderItem.objects.get(pk=item_id, order=order)
                        item.delete()
                        logger.info(f'Deleted order item {item_id} from order {order_id}')
                        return JsonResponse({'success': True})
                    except orders_models.OrderItem.DoesNotExist:
                        return JsonResponse({'success': False, 'error': 'Item not found'}, status=404)
                return JsonResponse({'success': False, 'error': 'Invalid action'}, status=400)

            logger.debug(f'POST form received in update_order_product for order {order_id}')
            form = orders_forms.AddOrderProductsForm(request.POST)

            if form.is_valid():
                logger.debug(f'Form valid in update_order_product for order {order_id}')
                order_item = form.save(commit=False)
                order_item.order = order
                order_item.save()
                return  redirect('orders:orders_all_list')
    else:
        form = orders_forms.AddOrderProductsForm(initial={'order': order})
        logger.debug(f'GET request - displaying form for order {order_id}')

    data = {
        'order': order,
        'form': form,
        'order_items': order_items
    }
    return render(request, 'orders/update_order_product.html', data)

@login_required(login_url='account_login')
@business_access_required()
def order_product_list(request, order_id):
    """List all products in an order using OrderItem model"""
    # IDOR FIX: Verify order belongs to user's business
    business = request.current_business
    order = get_object_or_404(orders_models.Order, id=order_id, business=business)
    logger.debug(f'Fetching product list for order {order}')
    ordered_items = order.order_items.select_related('product').all()  # Using related_name='order_items'

    # Format items for display
    listed_products = []
    for item in ordered_items:
        listed_products.append({
            'product_name': item.product.product_name if item.product else 'Unknown Product',
            'quantity': item.quantity,
            'unit_price': item.unit_price,
            'total_price': item.total_price or (item.quantity * item.unit_price if item.unit_price else 0)
        })

    logger.debug(f'Ordered items count: {ordered_items.count()}')
    logger.debug(f'Listed products count: {len(listed_products)}')

    data = {
        'order': order,
        'ordered_items': ordered_items,
        'listed_products': listed_products,
    }
    return render(request, 'orders/parts/order_product_list.html', data)

# operation links

@require_POST
@login_required(login_url='/accounts/login/')
def update_order_status(request, order_id=None):
    """Update order status - supports both form POST and JSON body"""
    try:
        comment = ''
        # Get order_id from URL or request body
        if order_id is None:
            # Try JSON body first
            if request.content_type == 'application/json':
                import json
                data = json.loads(request.body)
                order_id = data.get('order_id')
                status = data.get('status')
                comment = (data.get('comment') or '').strip()
            else:
                # Fall back to form POST
                order_id = request.POST.get('order_id')
                status = request.POST.get('status')
                comment = (request.POST.get('comment') or '').strip()
        else:
            # order_id from URL, status from body
            if request.content_type == 'application/json':
                import json
                data = json.loads(request.body)
                status = data.get('status')
                comment = (data.get('comment') or '').strip()
            else:
                status = request.POST.get('status')
                comment = (request.POST.get('comment') or '').strip()

        if not order_id or not status:
            return JsonResponse({'success': False, 'error': 'Missing order_id or status'}, status=400)

        order = orders_models.Order.objects.get(pk=order_id)

        # Check user has permission (owner or staff)
        if not request.user.is_staff:
            user_business = get_cached_business(request)
            if not user_business or user_business.business_id != order.business_id:
                return JsonResponse({'success': False, 'error': 'Permission denied'}, status=403)

        # Published orders — restricted transitions:
        #   - publish → ready_to_pickup: allowed for staff and owning business, ONLY when
        #     the latest delivery task is 'failed' (client reconfirm-for-redispatch).
        #   - publish → to_review: staff only (manual rollback).
        #   - anything else: rejected.
        if order.order_status == 'publish':
            if status == 'ready_to_pickup':
                latest_task = order.delivery_task.order_by('-id').first()
                if not latest_task or latest_task.dl_task_status != 'failed':
                    return JsonResponse({'success': False, 'error': 'Only published orders with a failed delivery can be reconfirmed.'}, status=400)
            elif status == 'to_review':
                if not request.user.is_staff:
                    return JsonResponse({'success': False, 'error': 'Only staff can revert a published order to Hold for Review.'}, status=403)
            else:
                return JsonResponse({'success': False, 'error': 'Published orders can only be reverted to Hold for Review or reconfirmed after a failed delivery.'}, status=400)

        # Delivered/cancelled orders cannot be changed by business users
        if order.order_status in ('delivered', 'cancelled') and not request.user.is_staff:
            return JsonResponse({'success': False, 'error': 'This order status cannot be changed.'}, status=403)

        old_status = order.order_status
        order.order_status = status
        # Attach the acting user so the post-save signal records it on OrderStatusHistory
        order._status_changed_by = request.user
        with transaction.atomic():
            order.save()

            # Save user-provided comment (e.g. reconfirmation note) as an OrderComment
            # and ALSO attach it to the OrderStatusHistory entry the signal just created,
            # so the workforce Status Timeline surfaces the note inline.
            if comment:
                try:
                    commenter = request.user.get_full_name() or request.user.username
                    orders_models.OrderComments.objects.create(
                        order=order,
                        name=f"Reconfirmed by {commenter}"[:255] if status == 'ready_to_pickup' else commenter[:255],
                        body=comment,
                    )
                except Exception as e:
                    logger.warning(f'Failed to save comment for order {order_id}: {e}')

                try:
                    hist = orders_models.OrderStatusHistory.objects.filter(
                        order=order,
                        field_name='order_status',
                        old_value=old_status or '',
                        new_value=status,
                    ).order_by('-created_at').first()
                    if hist and not hist.notes:
                        hist.notes = comment[:255]
                        hist.save(update_fields=['notes'])
                except Exception as e:
                    logger.warning(f'Failed to attach note to status history for order {order_id}: {e}')

            # Reverse sync: cancel active delivery tasks when order is cancelled
            if status == 'cancelled' and old_status != 'cancelled':
                from delivery import models as delivery_models
                delivery_models.DeliveryTask.objects.filter(
                    order=order
                ).exclude(
                    dl_task_status__in=['delivered', 'cancelled', 'failed']
                ).update(
                    dl_task_status='cancelled'
                )
                # Free up the client_order_code so the same order can be re-imported
                if order.client_order_code and '_DEL' not in order.client_order_code:
                    orders_models.Order.objects.filter(pk=order.pk).update(
                        client_order_code=f"{order.client_order_code}_DEL{order.pk}"
                    )

        logger.debug(f'Order {order_id} status updated from {old_status} to {status}')

        return JsonResponse({
            'success': True,
            'status': 'success',
            'message': f'Order status updated to {status}'
        })

    except orders_models.Order.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Order not found'}, status=404)
    except Exception as e:
        logger.error(f'Error updating order status: {e}')
        return JsonResponse({'success': False, 'error': str(e)}, status=400)


@require_POST
@login_required(login_url='/accounts/login/')
def bulk_update_order_status(request):
    """Bulk update order statuses - JSON POST with order_ids and status."""
    try:
        data = json.loads(request.body)
        order_ids = data.get('order_ids', [])
        status = data.get('status')

        if not order_ids or not status:
            return JsonResponse({'success': False, 'error': 'Missing order_ids or status'}, status=400)

        ALLOWED_STATUSES = ['publish', 'ready_to_pickup', 'cancelled']
        if status not in ALLOWED_STATUSES:
            return JsonResponse({'success': False, 'error': 'Invalid status'}, status=400)

        # Check business ownership
        user_business = get_cached_business(request)
        if not user_business and not request.user.is_staff:
            return JsonResponse({'success': False, 'error': 'Permission denied'}, status=403)

        orders_qs = orders_models.Order.objects.filter(pk__in=order_ids)
        if not request.user.is_staff:
            orders_qs = orders_qs.filter(business=user_business)
            # Business users cannot change published, delivered, or cancelled orders
            orders_qs = orders_qs.exclude(order_status__in=['publish', 'delivered', 'cancelled'])

        with transaction.atomic():
            updated = orders_qs.update(order_status=status)

            # Cancel active delivery tasks when bulk-cancelling
            if status == 'cancelled':
                from delivery import models as delivery_models
                delivery_models.DeliveryTask.objects.filter(
                    order__in=order_ids,
                    order__business=user_business
                ).exclude(
                    dl_task_status__in=['delivered', 'cancelled', 'failed']
                ).update(
                    dl_task_status='cancelled'
                )

        logger.info(f'Bulk status update: {updated} orders set to {status} by user {request.user.id}')
        return JsonResponse({'success': True, 'updated': updated})

    except Exception as e:
        logger.error(f'Error in bulk status update: {e}')
        return JsonResponse({'success': False, 'error': str(e)}, status=400)


@require_POST
@login_required(login_url='account_login')
def add_order_comment(request, order_id):
    """Add a comment to order's comment chain via HTMX"""
    try:
        # IDOR FIX: Verify order belongs to user's business (or user is staff)
        order = orders_models.Order.objects.get(pk=order_id)
        if not request.user.is_staff:
            user_business = get_cached_business(request)
            if not user_business or user_business.business_id != order.business_id:
                return JsonResponse({'status': 'error', 'message': 'Permission denied'}, status=403)
        comment_text = request.POST.get('comment', '').strip()

        if comment_text:
            # Get commenter name from user
            if request.user.is_authenticated:
                name = request.user.get_full_name() or request.user.username
            else:
                name = 'Anonymous'

            # Create comment
            orders_models.OrderComments.objects.create(
                order=order,
                name=name,
                body=comment_text
            )

            # Notify assigned driver if order is published to fleet
            try:
                from delivery.models import DeliveryTask
                from fleet.models import DriverNotification
                task = DeliveryTask.objects.filter(
                    order=order, driver__isnull=False
                ).select_related('driver').first()
                if task and task.driver_id:
                    DriverNotification.objects.create(
                        driver=task.driver,
                        title='New Comment on Order',
                        message=f'{name}: {comment_text[:120]}',
                        notification_type='order_comment',
                        related_task=task,
                    )
            except Exception:
                pass

        # Get all comments for this order
        comments = order.order_comments.all().order_by('created_at')

        # Check referer to determine which template to use
        referer = request.META.get('HTTP_REFERER', '')
        if 'workforce' in referer:
            template = 'orders/parts/order_comments_workforce.html'
        else:
            template = 'orders/parts/order_comments_list.html'

        return render(request, template, {
            'order': order,
            'comments': comments
        })
    except orders_models.Order.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Order not found'}, status=404)


@login_required(login_url='account_login')
def get_order_comments(request, order_id):
    """Get comments list for an order"""
    try:
        # IDOR FIX: Verify order belongs to user's business (or user is staff)
        order = orders_models.Order.objects.get(pk=order_id)
        if not request.user.is_staff:
            user_business = get_cached_business(request)
            if not user_business or user_business.business_id != order.business_id:
                return JsonResponse({'status': 'error', 'message': 'Permission denied'}, status=403)
        comments = order.order_comments.all().order_by('created_at')

        # Check referer to determine which template to use
        referer = request.META.get('HTTP_REFERER', '')
        if 'workforce' in referer:
            template = 'orders/parts/order_comments_workforce.html'
        else:
            template = 'orders/parts/order_comments_list.html'

        return render(request, template, {
            'order': order,
            'comments': comments
        })
    except orders_models.Order.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Order not found'}, status=404)


#get_by_api from shopify

@login_required(login_url='account_login')
def get_order_by_api(request):
    # IDOR FIX: Get user's business with authorization check (using cached helper)
    try:
        user_business = get_cached_business(request)
        if not user_business:
            logger.warning(f"User {request.user.id} has no associated business")
            messages.error(request, "No business associated with your account")
            return redirect('business:business_dashboard')

        business = user_business  # Already have the business object
    except business_models.Business.DoesNotExist:
        logger.warning(f"Business not found for user {request.user.id}")
        messages.error(request, "Business not found")
        return redirect('business:business_dashboard')

    api_data = business_models.BusinessApiSettings.objects.filter(
        business_id=business.business_id,
        is_verify_api=True,
        is_default=True
    ).first()

    if not api_data:
        logger.warning(f"No API settings found for business {business.business_id}")
        messages.error(request, "No API configuration found. Please configure your Shopify API settings.")
        return redirect('business:business_settings_api_list', business.business_id)

    logger.debug(f"Using API settings for business {business.business_id}")

    # Build Shopify API URL from business API settings
    shop_url = api_data.site_api_url.replace('https://', '').replace('http://', '')
    order_endpoint = api_data.order_api_endpoint or '/admin/api/2024-10/orders.json'
    api_url = f'https://{shop_url}{order_endpoint}'

    headers = {
        'Content-Type': 'application/json',
        'X-Shopify-Access-Token': api_data.api_access_token
    }

    order_list_start_date = request.GET.get('start_date') or request.POST.get('start_date')
    order_list_end_date = request.GET.get('end_date') or request.POST.get('end_date')
    if order_list_start_date and order_list_end_date:
        logger.debug(f'Using date range from request: {order_list_start_date} to {order_list_end_date}')
    else:
        order_list_start_date = (dj_timezone.localtime() - timedelta(days=30)).strftime('%Y-%m-%d')
        order_list_end_date = dj_timezone.localtime().strftime('%Y-%m-%d')
        logger.debug('Using default date range (last 30 days)')

    logger.debug(f'Date range: {order_list_start_date} to {order_list_end_date}')

    try:
        get_orders = requests.get(api_url, headers=headers, params={
            'status': 'any',
            'created_at_min': f'{order_list_start_date}T00:00:00+03:00',
            'created_at_max': f'{order_list_end_date}T23:59:59+03:00',
            'limit': 250,
        }, timeout=30)
    except requests.exceptions.RequestException as e:
        logger.error(f"Shopify API request failed: {e}")
        messages.error(request, "Failed to connect to Shopify API")
        return redirect('orders:orders_all_list')

    if get_orders.status_code == 200:
        order_data = get_orders.json()
        orders = order_data.get('orders', [])
        filtered_orders = [
            order for order in orders
            if order_list_start_date <= order['created_at'][:10] <= order_list_end_date
        ]
        filtered_orders.sort(key=lambda x: x['created_at'], reverse=True)

        # Annotate each order with its TempOrder import status
        visible_pids = [str(o['id']) for o in filtered_orders]
        temp_status_map = {}
        if visible_pids:
            from orders.models import TempOrder as _TempOrder
            for t in _TempOrder.objects.filter(
                business=business,
                source_type='shopify',
                platform_id__in=visible_pids,
            ).values('platform_id', 'status'):
                temp_status_map[t['platform_id']] = t['status']
        ready_count = 0
        for order in filtered_orders:
            status = temp_status_map.get(str(order['id']), 'not_synced')
            order['import_status'] = status
            if status == 'new':
                ready_count += 1

        data={
            'order_data': order_data,
            'orders': filtered_orders,
            'business': business,
            'ready_count': ready_count,
        }
        return render(request, 'orders/order_api_get.html', data)
    else:
        return JsonResponse({'status': 'error', 'message': 'Failed to fetch orders from Shopify'})


@login_required(login_url='account_login')
@require_POST
def import_shopify_orders(request):
    """Client-facing: import selected Shopify orders (by platform_id) into real Order records.

    Expects JSON body: {"platform_ids": ["1234567890", ...]}
    Finds matching TempOrders (synced via API Upload), creates Order records.
    """
    import uuid as _uuid

    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'success': False, 'error': 'Invalid JSON'}, status=400)

    platform_ids = [str(pid) for pid in body.get('platform_ids', []) if pid]
    if not platform_ids:
        return JsonResponse({'success': False, 'error': 'No orders selected'}, status=400)

    user_business = get_cached_business(request)
    if not user_business:
        return JsonResponse({'success': False, 'error': 'No business found'}, status=403)

    temp_orders = orders_models.TempOrder.objects.filter(
        business=user_business,
        platform_id__in=platform_ids,
        status='new',
    )

    if not temp_orders.exists():
        return JsonResponse({
            'success': False,
            'error': 'No pending orders found for the selected IDs. Run "API Upload" first to sync.'
        }, status=404)

    saved, skipped, errors = 0, 0, []

    for temp in temp_orders:
        client_order_code = temp.client_order_code or f"SH-{_uuid.uuid4().hex[:8].upper()}"

        if orders_models.Order.objects.filter(business=user_business, client_order_code=client_order_code).exists():
            temp.status = 'imported'
            temp.save(update_fields=['status'])
            skipped += 1
            continue

        if not temp.customer_name and not temp.customer_phone:
            errors.append(f"Order {temp.platform_id}: missing name and phone")
            skipped += 1
            continue

        def _safe_int(val):
            try:
                return int(float(str(val).replace(',', '').strip())) if val else 0
            except (ValueError, TypeError):
                return 0

        try:
            raw = temp.raw_row if isinstance(temp.raw_row, dict) else {}
            line_items = raw.get('line_items', []) or []

            # Build package description from line items if package_desc is empty
            pkg_desc = (temp.package_desc or '')[:255]
            if not pkg_desc and line_items:
                pkg_desc = ', '.join(
                    f"{it.get('name', '')} x{it.get('qty', 1)}" for it in line_items
                )[:255]
            pkg_qty = _safe_int(raw.get('package_qty', '')) or max(
                sum(it.get('qty', 1) for it in line_items), 1
            )

            # Determine COD amount and payment status from Shopify financial_status
            financial_status = temp.financial_status or (raw.get('financial_status') or '') or ''
            if financial_status == 'paid':
                cod_amount = 0
                cod_status = 'online_paid'
            elif financial_status == 'partially_paid':
                cod_amount = _safe_int(temp.cod_amount)
                cod_status = 'partial_paid'
            else:
                cod_amount = _safe_int(temp.cod_amount)
                cod_status = 'unpaid'

            order = orders_models.Order(
                business=user_business,
                client_order_code=client_order_code,
                customer_name=temp.customer_name or '',
                customer_phone=temp.customer_phone or '',
                customer_whatsapp=temp.customer_phone or '',
                customer_address=temp.customer_address or '',
                cod_amount=cod_amount,
                cod_status_by_client=cod_status,
                package_description=pkg_desc,
                package_qty=pkg_qty,
                order_status='to_review',
                verification_status='pending',
                original_order_data={
                    'source': 'shopify_import',
                    'platform_id': temp.platform_id,
                    'temp_order_id': temp.id,
                    'source_type': 'shopify',
                    'financial_status': financial_status,
                    'line_items': line_items,
                },
            )
            order.save()

            # Create OrderItem records from line items
            for it in line_items:
                iname = it.get('name', '')
                iqty = it.get('qty', 1)
                iprice = it.get('price', 0)
                try:
                    orders_models.OrderItem.objects.create(
                        order=order,
                        product=None,
                        quantity=iqty,
                        unit_price=float(iprice) if iprice else 0,
                        notes=iname,
                    )
                except Exception as item_exc:
                    logger.warning("OrderItem creation failed for order %s item '%s': %s", order.order_number, iname, item_exc)

            temp.status = 'imported'
            temp.imported_order = order
            temp.save(update_fields=['status', 'imported_order'])
            saved += 1
        except Exception as exc:
            logger.exception("Import error for platform_id %s", temp.platform_id)
            errors.append(f"Order {temp.platform_id}: {str(exc)}")

    return JsonResponse({
        'success': True,
        'saved': saved,
        'skipped': skipped,
        'errors': errors,
    })


# -----------------------------------------------------------------------------
# In-page "New Orders to Import" panel for the All Orders page.
# - orders_api_pending_list: HTMX fragment, fetches latest 10 from Shopify/Woo,
#   marks ones already in local Orders so the form skips them.
# - orders_api_pending_import: POST endpoint, reads selected rows from the form
#   and creates Order + OrderItem records directly (no TempOrder staging).
# -----------------------------------------------------------------------------
@login_required(login_url='account_login')
def orders_api_pending_list(request):
    """HTMX endpoint: render the latest 10 e-commerce orders for quick import."""
    import signal

    business = get_cached_business(request)
    if not business:
        return HttpResponse('', status=204)

    api = business_models.BusinessApiSettings.objects.filter(
        business=business, api_type__in=['shopify', 'woocommerce']
    ).first()

    import_result = getattr(request, '_orders_api_import_result', None)
    ctx_base = {'business': business, 'import_result': import_result}

    if not api:
        return render(request, 'orders/parts/api_pending_orders_fragment.html', dict(ctx_base, **{
            'api_orders': [], 'api_orders_error': '', 'api_orders_platform': '',
            'imported_codes': set(), 'resolved_handle': '',
        }))

    api_orders = []
    api_orders_error = ''
    resolved_handle = ''

    class ApiTimeout(Exception):
        pass

    def timeout_handler(signum, frame):
        raise ApiTimeout('API request timed out after 12s')

    old_handler = signal.signal(signal.SIGALRM, timeout_handler)
    signal.alarm(12)

    try:
        if api.api_type == 'shopify':
            from workforce.views import resolve_shopify_shop_handle
            import shopify
            shop_name, was_resolved = resolve_shopify_shop_handle(api)
            if not shop_name:
                raise ValueError(
                    f'Could not resolve Shopify handle from "{api.site_api_url}".'
                )
            if was_resolved:
                resolved_handle = f'{shop_name}.myshopify.com'
            session = shopify.Session(shop_name, api.api_version or '2023-10', api.api_access_token)
            shopify.ShopifyResource.activate_session(session)
            try:
                fetched = shopify.Order.find(limit=10, status='any', order='created_at desc')
                for o in fetched:
                    customer_name = ''
                    customer_phone = ''
                    customer = getattr(o, 'customer', None)
                    if customer:
                        first = getattr(customer, 'first_name', '') or ''
                        last = getattr(customer, 'last_name', '') or ''
                        customer_name = (first + ' ' + last).strip()
                        customer_phone = getattr(customer, 'phone', '') or ''
                    addr_parts = []
                    shipping = getattr(o, 'shipping_address', None)
                    if shipping:
                        if not customer_name:
                            customer_name = getattr(shipping, 'name', '') or ''
                        if not customer_phone:
                            customer_phone = getattr(shipping, 'phone', '') or ''
                        for f in ('address1', 'address2', 'city', 'province', 'country'):
                            v = getattr(shipping, f, '') or ''
                            if v:
                                addr_parts.append(v)
                    if not customer_name:
                        customer_name = getattr(o, 'email', '') or ''

                    items = []
                    for li in (getattr(o, 'line_items', None) or []):
                        items.append({
                            'name': getattr(li, 'name', '') or getattr(li, 'title', '') or '',
                            'qty': int(getattr(li, 'quantity', 1) or 1),
                            'price': str(getattr(li, 'price', '0') or '0'),
                            'sku': getattr(li, 'sku', '') or '',
                        })

                    api_orders.append({
                        'platform_id': str(o.id),
                        'name': getattr(o, 'name', '') or '',
                        'created_at': getattr(o, 'created_at', '') or '',
                        'financial_status': getattr(o, 'financial_status', '') or '',
                        'fulfillment_status': getattr(o, 'fulfillment_status', '') or 'unfulfilled',
                        'total_price': str(getattr(o, 'total_price', '0') or '0'),
                        'currency': getattr(o, 'currency', '') or '',
                        'customer_name': customer_name,
                        'customer_phone': customer_phone,
                        'customer_address': ', '.join(addr_parts),
                        'item_count': len(items),
                        'line_items_json': json.dumps(items),
                    })
            finally:
                shopify.ShopifyResource.clear_session()

        else:  # woocommerce
            from woocommerce import API as WooAPI
            wcapi = WooAPI(
                url=api.site_api_url or '',
                consumer_key=api.api_key or '',
                consumer_secret=api.api_secret or '',
                version='wc/v3', timeout=10,
            )
            r = wcapi.get('orders', params={'per_page': 10, 'orderby': 'date', 'order': 'desc'})
            if r.status_code != 200:
                api_orders_error = f'WooCommerce API error {r.status_code}'
            else:
                for o in r.json():
                    billing = o.get('billing') or {}
                    shipping = o.get('shipping') or {}
                    name = (
                        ((billing.get('first_name') or '') + ' ' + (billing.get('last_name') or '')).strip()
                        or ((shipping.get('first_name') or '') + ' ' + (shipping.get('last_name') or '')).strip()
                        or billing.get('email') or ''
                    )
                    addr_parts = []
                    src = shipping if shipping.get('address_1') else billing
                    for f in ('address_1', 'address_2', 'city', 'state', 'country'):
                        v = src.get(f) or ''
                        if v:
                            addr_parts.append(v)
                    items = []
                    for li in (o.get('line_items') or []):
                        items.append({
                            'name': li.get('name', ''),
                            'qty': int(li.get('quantity', 1) or 1),
                            'price': str(li.get('price', '0') or '0'),
                            'sku': li.get('sku', '') or '',
                        })
                    api_orders.append({
                        'platform_id': str(o.get('id')),
                        'name': f"#{o.get('number') or o.get('id')}",
                        'created_at': o.get('date_created') or '',
                        'financial_status': o.get('status') or '',
                        'fulfillment_status': '',
                        'total_price': str(o.get('total') or '0'),
                        'currency': o.get('currency') or '',
                        'customer_name': name,
                        'customer_phone': billing.get('phone') or '',
                        'customer_address': ', '.join(addr_parts),
                        'item_count': len(items),
                        'line_items_json': json.dumps(items),
                    })
    except ApiTimeout:
        api_orders_error = 'API request timed out. Try again.'
    except Exception as e:
        logger.exception('orders_api_pending_list failed')
        api_orders_error = str(e)
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, old_handler)

    # Mark ones already imported (by client_order_code matching the platform name)
    incoming_codes = [(o['name'] or '').lstrip('#').strip() for o in api_orders]
    incoming_codes = [c for c in incoming_codes if c]
    imported_codes = set(orders_models.Order.objects.filter(
        business=business, client_order_code__in=incoming_codes
    ).values_list('client_order_code', flat=True))

    return render(request, 'orders/parts/api_pending_orders_fragment.html', dict(ctx_base, **{
        'api_orders': api_orders,
        'api_orders_error': api_orders_error,
        'api_orders_platform': api.api_type,
        'imported_codes': imported_codes,
        'resolved_handle': resolved_handle,
    }))


@login_required(login_url='account_login')
@require_POST
def orders_api_pending_import(request):
    """Create Order + OrderItem records from selected rows of the pending fragment."""
    import uuid as _uuid

    business = get_cached_business(request)
    if not business:
        return HttpResponse('', status=403)

    indices = request.POST.getlist('selected')
    saved = 0
    skipped_dup = 0
    skipped_invalid = 0
    errors = []

    for raw_idx in indices:
        try:
            i = int(raw_idx)
        except (TypeError, ValueError):
            continue

        platform_id = (request.POST.get(f'o_{i}_platform_id') or '').strip()
        order_name = (request.POST.get(f'o_{i}_name') or '').strip()
        customer_name = (request.POST.get(f'o_{i}_customer_name') or '').strip()
        customer_phone = (request.POST.get(f'o_{i}_customer_phone') or '').strip()
        customer_address = (request.POST.get(f'o_{i}_customer_address') or '').strip()
        total_price = (request.POST.get(f'o_{i}_total_price') or '0').strip()
        financial_status = (request.POST.get(f'o_{i}_financial_status') or '').strip().lower()
        line_items_json = request.POST.get(f'o_{i}_line_items_json') or '[]'
        try:
            line_items = json.loads(line_items_json)
            if not isinstance(line_items, list):
                line_items = []
        except (ValueError, json.JSONDecodeError):
            line_items = []

        if not customer_name and not customer_phone:
            skipped_invalid += 1
            errors.append(f"{order_name or platform_id}: missing customer name and phone")
            continue

        client_order_code = order_name.lstrip('#').strip() or f"SH-{_uuid.uuid4().hex[:8].upper()}"
        client_order_code = client_order_code[:64]
        if orders_models.Order.objects.filter(business=business, client_order_code=client_order_code).exists():
            skipped_dup += 1
            continue

        def _safe_int(val):
            try:
                return int(float(str(val).replace(',', '').strip())) if val else 0
            except (ValueError, TypeError):
                return 0

        if financial_status == 'paid':
            cod_amount = 0
            cod_status = 'online_paid'
        elif financial_status == 'partially_paid':
            cod_amount = _safe_int(total_price)
            cod_status = 'partial_paid'
        else:
            cod_amount = _safe_int(total_price)
            cod_status = 'unpaid'

        pkg_desc = ', '.join(f"{li.get('name', '')} x{li.get('qty', 1)}" for li in line_items)[:255]
        pkg_qty = max(sum(int(li.get('qty', 1) or 1) for li in line_items), 1)

        try:
            order = orders_models.Order(
                business=business,
                client_order_code=client_order_code,
                customer_name=customer_name[:100],
                customer_phone=customer_phone[:100],
                customer_whatsapp=customer_phone[:100],
                customer_address=customer_address[:255],
                cod_amount=cod_amount,
                cod_status_by_client=cod_status,
                package_description=pkg_desc,
                package_qty=pkg_qty,
                order_status='to_review',
                verification_status='pending',
                original_order_data={
                    'source': 'shopify_quick_import',
                    'platform_id': platform_id,
                    'financial_status': financial_status,
                    'line_items': line_items,
                },
            )
            order.save()

            for li in line_items:
                try:
                    orders_models.OrderItem.objects.create(
                        order=order,
                        product=None,
                        quantity=int(li.get('qty', 1) or 1),
                        unit_price=float(li.get('price', 0) or 0),
                        notes=li.get('name', '')[:200] if li.get('name') else '',
                    )
                except Exception as item_exc:
                    logger.warning('OrderItem create failed for %s: %s', client_order_code, item_exc)

            saved += 1
        except Exception as exc:
            logger.exception('orders_api_pending_import failed for %s', platform_id)
            errors.append(f"{order_name or platform_id}: {str(exc)}")

    request._orders_api_import_result = {
        'saved': saved,
        'skipped_duplicate': skipped_dup,
        'skipped_invalid': skipped_invalid,
        'errors': errors[:5],
    }
    return orders_api_pending_list(request)


@login_required(login_url='account_login')
def get_orders_by_base_api(request):
    # IDOR FIX: Get user's business with authorization check (using cached helper)
    user_business = get_cached_business(request)
    if not user_business:
        logger.warning(f"User {request.user.id} has no associated business")
        messages.error(request, "No business associated with your account")
        return redirect('business:business_dashboard')

    business = user_business  # Already have the business object
    business_id = business.business_id

    business_api = business_models.BusinessApiSettings.objects.filter(
        business_id=business_id,
        is_verify_api=True,
        is_default=True
    ).first()

    if not business_api:
        logger.warning(f"No API settings found for business {business_id}")
        messages.error(request, "No API configuration found")
        return redirect('business:business_settings_api_list', business_id)

    logger.info(f"Fetching orders via {business_api.api_type} API for business {business_id}")
     

    BASE_API_KEY = business_api.api_key
    BASE_API_ACCESS_KEY = business_api.api_access_token
    BASE_API_SECRET = business_api.api_secret
    BASE_API_STORE_NAME = business_api.site_api_url
    BASE_API_ORDER_ENDPINT = business_api.order_api_endpoint
    BASE_API_PRODUCT_ENDPINT = business_api.product_api_endpoint

    BASE_API_STORE_NAME = BASE_API_STORE_NAME.replace('https://', '')


    if business_api.api_type == 'shopify':
        shop_url = BASE_API_STORE_NAME
        logger.debug(f'Shopify shop_url: {shop_url}')

        order_base_url = 'https://' + shop_url + BASE_API_ORDER_ENDPINT
        product_base_url = 'https://' + shop_url + BASE_API_PRODUCT_ENDPINT
        header_value = { 'X-Shopify-Access-Token': BASE_API_ACCESS_KEY, 'Content-Type': 'application/json' }

        order_response = requests.get(order_base_url, headers=header_value, params={'status': 'any', 'limit': 10})
        order_count = len(order_response.json().get('orders', []))

        logger.debug(f'Shopify order_count: {order_count}')
        product_response = requests.get(product_base_url, headers=header_value )
        product_count = len(product_response.json().get('products', []))
        logger.debug(f'Shopify product_count: {product_count}')

    elif business_api.api_type == 'woocommerce':
        shop_url = 'https://' + BASE_API_STORE_NAME
        logger.debug(f'WooCommerce shop_url: {shop_url}')
 
        wcapi = WooAPI(
            url= shop_url,
            consumer_key= BASE_API_KEY,
            consumer_secret= BASE_API_SECRET,
            version="wc/v3",
        )

        
        #print(wcapi.get("products", params={"per_page": 20}).json())

        order_response = wcapi.get("orders")
        order_date = order_response.headers.get('Date')
        logger.debug(f'WooCommerce order_date: {order_date}')
        order_count = order_response.headers.get('X-WP-Total')
        logger.debug(f'WooCommerce order_count: {order_count}')
        product_response = wcapi.get("products", params={"per_page": 20})
        product_count = product_response.headers.get('X-WP-Total')
        logger.debug(f'WooCommerce product_count: {product_count}')
 
    else:
        order_response = None
        product_response = None


    start_date = (dj_timezone.localtime() - timedelta(days=10)).strftime('%Y-%m-%d')
    end_date = dj_timezone.localtime().strftime('%Y-%m-%d')
    logger.debug(f'API fetch date range: {start_date} to {end_date}')

    try:
        if order_response.status_code == 200:
            orders = []
            response_data = order_response.json()

            # Handle different API response formats
            if business_api.api_type == 'shopify':
                # Shopify wraps orders in {'orders': [...]}
                order_list = response_data.get('orders', []) if isinstance(response_data, dict) else []
            elif business_api.api_type == 'woocommerce':
                # WooCommerce returns orders directly as a list
                order_list = response_data if isinstance(response_data, list) else []
            else:
                order_list = []

            for order in order_list:
                logger.debug(f'Processing order from API: {order.get("id", "unknown")}')

                # Extract customer info safely
                try:
                    if business_api.api_type == 'shopify':
                        customer_id = order.get('customer', {}).get('id')
                        if customer_id:
                            customer_response = requests.get(
                                f'https://{shop_url}/admin/api/2024-01/customers/{customer_id}.json',
                                headers=header_value
                            )
                            if customer_response.status_code == 200:
                                customer_data = customer_response.json().get('customer', {})
                                customer_info = {
                                    'first_name': customer_data.get('first_name', ''),
                                    'last_name': customer_data.get('last_name', ''),
                                    'email': customer_data.get('email', ''),
                                    'address': customer_data.get('default_address', {}).get('address1', '')
                                }
                            else:
                                customer_info = {
                                    'first_name': '',
                                    'last_name': '',
                                    'email': '',
                                    'address': ''
                                }
                        else:
                            customer_info = {
                                'first_name': '',
                                'last_name': '',
                                'email': '',
                                'address': ''
                            }
                    elif business_api.api_type == 'woocommerce':
                        # WooCommerce includes customer info in order
                        billing = order.get('billing', {})
                        customer_info = {
                            'first_name': billing.get('first_name', ''),
                            'last_name': billing.get('last_name', ''),
                            'email': billing.get('email', ''),
                            'address': f"{billing.get('address_1', '')} {billing.get('address_2', '')}".strip()
                        }
                    else:
                        customer_info = {
                            'first_name': '',
                            'last_name': '',
                            'email': '',
                            'address': ''
                        }

                    orders.append({
                        'id': order.get('id'),
                        'created_at': order.get('date_created') if business_api.api_type == 'woocommerce' else order.get('created_at'),
                        'payment_gateway_names': order.get('payment_method') if business_api.api_type == 'woocommerce' else order.get('payment_gateway_names'),
                        'total_price': order.get('total'),
                        'current_total_price': order.get('total'),
                        'currency': order.get('currency'),
                        'customer_info': customer_info,
                        'line_items': [
                            {
                                'title': item.get('name') if business_api.api_type == 'woocommerce' else item.get('title'),
                                'quantity': item.get('quantity'),
                                'price': item.get('price')
                            } for item in order.get('line_items', [])
                        ],
                    })
                except Exception as item_error:
                    logger.error(f"Error processing order item: {str(item_error)}")
                    continue

        else:
            logger.error(f"API returned status code: {order_response.status_code}")
            messages.error(request, f"API error: {order_response.status_code}")
            return redirect('business:business_settings_api_list', business_id)

        result = order_response.json()
        status = order_response.status_code
        context = {
            'business': business,
            'api': business_api,
            'orders': orders,
            'status': status,
            'result': result,
        }
        return render(request, 'orders/order_api_list.html', context)

    except Exception as e:
        logger.error(f"Error fetching orders: {str(e)}")
        messages.error(request, f"Failed to fetch orders: {str(e)}")
        return redirect('business:business_settings_api_list', business_id)

# Location Verification View
def verify_location_short(request, phone, token):
    """Short URL: /v/<phone>/<token>/ — redirect to update_location page"""
    return _verify_token_redirect(request, token)


def verify_location(request, token):
    """Legacy URL: /orders/verify-location/<token>/ — redirect to update_location page"""
    return _verify_token_redirect(request, token)


def _verify_token_redirect(request, token):
    """Validate token and redirect to the unified update_location page."""
    from orders.models import AddressVerification
    from core.templatetags.custom_filters import generate_order_verify_key
    from urllib.parse import quote

    av = AddressVerification.objects.filter(
        verification_token=token
    ).select_related('order').first()
    if not av:
        raise Http404

    if av.is_token_expired():
        return render(request, 'orders/verification_expired.html', {
            'order': av.order
        })

    order = av.order
    verify_key = generate_order_verify_key(order.order_number, order.customer_phone)
    return redirect(f'/orders/verify/?order={quote(order.order_number)}&key={verify_key}')


# =============================================================================
# CUSTOMER SELF-SERVICE LOCATION UPDATE (Public)
# =============================================================================

def _ai_extract_location(address):
    """
    Use AI (Claude Haiku) to extract a geocodable location/area name
    from a Qatar delivery address. Cached for 24 hours per address.
    Falls back to simple parsing if AI fails.
    """
    from django.core.cache import cache
    import anthropic
    from decouple import config as env_config

    cache_key = f'geocode_loc:{hash(address)}'
    cached = cache.get(cache_key)
    if cached:
        return cached

    api_key = env_config('ANTHROPIC_API_KEY', default='')
    if not api_key:
        return address

    try:
        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model='claude-3-haiku-20240307',
            max_tokens=50,
            messages=[{
                'role': 'user',
                'content': (
                    f'Extract the area/neighborhood name from this Qatar delivery address '
                    f'that would work best for map geocoding. Return ONLY the location name '
                    f'and "Qatar", nothing else. No zone numbers, street numbers, or building numbers.\n\n'
                    f'Address: {address}\n\n'
                    f'Example: "Al Thumama, Doha, Qatar" or "West Bay, Doha, Qatar"'
                )
            }]
        )
        location = response.content[0].text.strip().strip('"').strip("'")
        if location:
            cache.set(cache_key, location, 86400)  # cache 24h
            return location
    except Exception:
        pass

    return address


def _ai_order_items_summary(order):
    """
    Use AI to generate a short, clear summary of order items.
    Cached for 24 hours per order.
    """
    from django.core.cache import cache
    import anthropic
    from decouple import config as env_config

    items = order.order_items.select_related('product').all()
    if not items.exists():
        return ''

    cache_key = f'order_summary:{order.pk}'
    cached = cache.get(cache_key)
    if cached:
        return cached

    # Build items text
    items_text = []
    for item in items:
        name = item.product.item_name if item.product else 'Item'
        desc = item.product.item_discription if item.product and item.product.item_discription else ''
        items_text.append(f'{name} (qty: {item.quantity}){" - " + desc if desc else ""}')

    api_key = env_config('ANTHROPIC_API_KEY', default='')
    if not api_key:
        return ', '.join(items_text)

    try:
        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model='claude-3-haiku-20240307',
            max_tokens=80,
            messages=[{
                'role': 'user',
                'content': (
                    f'Summarize these order items in one short line (max 15 words). '
                    f'Be clear and concise. No quotes.\n\n'
                    f'Store: {order.business.business_name}\n'
                    f'Items: {"; ".join(items_text)}'
                )
            }]
        )
        summary = response.content[0].text.strip().strip('"').strip("'")
        if summary:
            cache.set(cache_key, summary, 86400)
            return summary
    except Exception:
        pass

    return ', '.join(items_text)


def update_location(request):
    """
    Public view for customers to look up their order and update delivery location.
    Step 1: Lookup by order_number + phone last 4 digits
    Step 2: Show order details + map form for location update
    Step 3: Success confirmation
    """
    from orders.models import AddressVerification
    from delivery.models import DlAddressUpdate
    from django.utils import timezone
    from django.core.cache import cache

    TERMINAL_STATUSES = ('delivered', 'cancelled')

    # Rate limiting: 10 lookups per IP per hour
    ip = request.META.get('HTTP_X_FORWARDED_FOR', request.META.get('REMOTE_ADDR', ''))
    if ',' in ip:
        ip = ip.split(',')[0].strip()
    rate_key = f'update_location_rate:{ip}'
    attempts = cache.get(rate_key, 0)

    from core.templatetags.custom_filters import generate_order_verify_key, verify_order_key

    # Pre-fill order number from query param (e.g. ?order=EZ-123&key=abc123)
    prefill_order = request.GET.get('order', '').strip()
    prefill_key = request.GET.get('key', '').strip()
    lookup_form = forms.OrderLookupForm(initial={'order_number': prefill_order} if prefill_order else None)
    update_form = None
    order = None
    step = 'lookup'
    error = None
    success = False

    # Auto-verify if both order and key are in URL (clicked from WhatsApp)
    if request.method == 'GET' and prefill_order and prefill_key:
        if attempts >= 10:
            error = 'Too many attempts. Please try again later.'
        else:
            cache.set(rate_key, attempts + 1, 3600)
            try:
                order = orders_models.Order.objects.select_related('business').get(
                    order_number__iexact=prefill_order
                )
                if not verify_order_key(order.order_number, order.customer_phone, prefill_key):
                    order = None
                    error = 'This link has expired. Please request a new link or enter your details manually.'
                elif order.order_status in TERMINAL_STATUSES:
                    error = 'This order has already been completed and cannot be updated.'
                    order = None
                else:
                    step = 'update'
                    update_form = forms.CustomerLocationUpdateForm(initial={
                        'order_number': order.order_number,
                        'phone_last4': 'link',
                        'zone_number': order.dl_zone,
                        'street_number': order.dl_street,
                        'building_number': order.dl_building,
                        'verified_address': order.customer_address,
                    })
            except orders_models.Order.DoesNotExist:
                error = 'Order not found. Please check your WhatsApp message for the correct link.'

    if request.method == 'POST':
        post_step = request.POST.get('step', 'lookup')

        if post_step == 'lookup':
            # Rate limit check
            if attempts >= 10:
                error = 'Too many attempts. Please try again later.'
            else:
                lookup_form = forms.OrderLookupForm(request.POST)
                if lookup_form.is_valid():
                    order_number = lookup_form.cleaned_data['order_number'].strip()
                    phone_last4 = lookup_form.cleaned_data['phone_last4']

                    cache.set(rate_key, attempts + 1, 3600)

                    try:
                        order = orders_models.Order.objects.select_related('business').get(
                            order_number__iexact=order_number
                        )
                        # Verify phone last 4 digits match
                        customer_phone = order.customer_phone.replace(' ', '').replace('-', '').replace('+', '')
                        if not customer_phone.endswith(phone_last4):
                            order = None
                            error = 'Order not found. Please check your order number and phone digits.'
                        elif order.order_status in TERMINAL_STATUSES:
                            error = 'This order has already been completed and cannot be updated.'
                            step = 'lookup'
                            order = None
                        else:
                            step = 'update'
                            update_form = forms.CustomerLocationUpdateForm(initial={
                                'order_number': order.order_number,
                                'phone_last4': phone_last4,
                                'zone_number': order.dl_zone,
                                'street_number': order.dl_street,
                                'building_number': order.dl_building,
                                'verified_address': order.customer_address,
                            })
                    except orders_models.Order.DoesNotExist:
                        error = 'Order not found. Please check your order number and phone digits.'

        elif post_step == 'update':
            update_form = forms.CustomerLocationUpdateForm(request.POST)
            if update_form.is_valid():
                order_number = update_form.cleaned_data['order_number']
                phone_last4 = update_form.cleaned_data['phone_last4']

                # Re-validate: accept either valid key or phone last4
                try:
                    order = orders_models.Order.objects.select_related('business').get(
                        order_number__iexact=order_number
                    )
                    customer_phone = order.customer_phone.replace(' ', '').replace('-', '').replace('+', '')
                    post_key = request.POST.get('verify_key', '')
                    key_valid = (phone_last4 == 'link' and verify_order_key(order.order_number, order.customer_phone, post_key))
                    phone_valid = (phone_last4 != 'link' and customer_phone.endswith(phone_last4))
                    if not key_valid and not phone_valid:
                        error = 'Verification failed. Please try again.'
                        step = 'lookup'
                        lookup_form = forms.OrderLookupForm()
                        order = None
                    elif order.order_status in TERMINAL_STATUSES:
                        error = 'This order has already been completed and cannot be updated.'
                        step = 'lookup'
                        order = None
                    else:
                        # Apply updates
                        latitude = update_form.cleaned_data.get('latitude')
                        longitude = update_form.cleaned_data.get('longitude')
                        verified_address = update_form.cleaned_data.get('verified_address')
                        zone_number = update_form.cleaned_data.get('zone_number')
                        street_number = update_form.cleaned_data.get('street_number')
                        building_number = update_form.cleaned_data.get('building_number')
                        notes = update_form.cleaned_data.get('notes')

                        # Snapshot the pin the client is replacing, for the timeline row
                        old_lat, old_lng = order.latitude, order.longitude
                        old_accuracy = order.coords_accuracy or ''

                        # Atomic: order, verification, address and task updates commit as one unit
                        with transaction.atomic():
                            # Update Order
                            if zone_number is not None:
                                order.dl_zone = zone_number
                            if street_number is not None:
                                order.dl_street = street_number
                            if building_number is not None:
                                order.dl_building = building_number
                            if verified_address:
                                order.customer_address = verified_address[:100]
                            order.verification_status = 'address_verified'
                            order.coords_accuracy = 'by_customer'
                            order.address_verified = True
                            order.address_verified_at = timezone.now()
                            if latitude:
                                order.latitude = latitude
                            if longitude:
                                order.longitude = longitude
                            if notes:
                                order.verification_notes = notes
                            order.save()

                            # Update or create AddressVerification
                            addr_verify, _ = AddressVerification.objects.get_or_create(
                                order=order,
                                defaults={'original_address': order.customer_address or ''}
                            )
                            if latitude:
                                addr_verify.latitude = latitude
                            if longitude:
                                addr_verify.longitude = longitude
                            if zone_number is not None:
                                addr_verify.zone_number = zone_number
                            if street_number is not None:
                                addr_verify.street_number = street_number
                            if building_number is not None:
                                addr_verify.building_number = building_number
                            if verified_address:
                                addr_verify.verified_address = verified_address
                            if notes:
                                addr_verify.notes = notes
                            addr_verify.verification_result = 'address_verified'
                            addr_verify.customer_verified_at = timezone.now()
                            addr_verify.save()

                            # Timeline: the client confirmed / moved their own pin
                            from orders.location_history import log_location_update
                            log_location_update(
                                order, source='Customer verification link', actor=None,
                                old_lat=old_lat, old_lng=old_lng, old_accuracy=old_accuracy,
                                new_lat=order.latitude, new_lng=order.longitude,
                                new_accuracy=order.coords_accuracy,
                                note=(f'Zone {order.dl_zone}' if order.dl_zone else None),
                                force=True,
                            )

                            # Update DlAddressUpdate (always update, create if missing)
                            dl_update_fields = {}
                            if zone_number is not None:
                                dl_update_fields['dl_zone'] = zone_number
                            if street_number is not None:
                                dl_update_fields['dl_street'] = street_number
                            if building_number is not None:
                                dl_update_fields['dl_building'] = building_number
                            if latitude:
                                dl_update_fields['dl_latitude'] = latitude
                            if longitude:
                                dl_update_fields['dl_longitude'] = longitude
                            if verified_address:
                                dl_update_fields['area_name'] = verified_address[:100]

                            from decimal import Decimal as _D
                            dl_addr, _ = DlAddressUpdate.objects.get_or_create(
                                order=order,
                                defaults={
                                    'full_name': order.customer_name or '',
                                    'mobile_no': order.customer_phone or '',
                                    'dl_task_number': order.order_number,
                                    'dl_latitude': _D('0'),
                                    'dl_longitude': _D('0'),
                                    'dl_unit': '0',
                                }
                            )
                            for attr, val in dl_update_fields.items():
                                setattr(dl_addr, attr, val)
                            dl_addr.save()

                            # Save preferred delivery time and payment method
                            preferred_times = request.POST.getlist('preferred_time')
                            payment_method = request.POST.get('payment_method', '')

                            # Get or auto-create delivery task
                            from delivery.models import DeliveryTask as _DlTask
                            from orders.signals import _create_delivery_task_from_order
                            delivery_task = order.delivery_task.first()
                            if delivery_task is None:
                                delivery_task = _create_delivery_task_from_order(order)
                                if delivery_task:
                                    # Auto-publish so drivers can see it
                                    delivery_task.dl_task_publish = True
                                    delivery_task.save(update_fields=['dl_task_publish'])

                            if delivery_task:
                                # Mirror all address fields onto the task's DlAddressUpdate
                                task_addr = delivery_task.dl_address_update or dl_addr
                                for attr, val in dl_update_fields.items():
                                    setattr(task_addr, attr, val)
                                task_addr.save()

                                # Update task itself
                                task_fields_to_save = ['address_accuracy', 'dl_address_update']
                                delivery_task.address_accuracy = 'by_customer'
                                delivery_task.dl_address_update = task_addr
                                if preferred_times:
                                    delivery_task.preferred_time = ','.join(preferred_times)
                                    task_fields_to_save.append('preferred_time')
                                if payment_method:
                                    delivery_task.payment_method = payment_method
                                    task_fields_to_save.append('payment_method')
                                delivery_task.save(update_fields=task_fields_to_save)

                        # Fix 5: Notify driver of address update
                        if order:
                            active_task = order.delivery_task.filter(
                                dl_task_status__in=[
                                    'assigned', 'accepted', 'picked_up',
                                    'start_ride', 'out_for_delivery', 'in_transit',
                                ]
                            ).first()
                            if active_task and active_task.driver:
                                try:
                                    from fleet.models import DriverNotification
                                    DriverNotification.objects.create(
                                        driver=active_task.driver,
                                        title='Address Updated',
                                        message=f'Customer updated delivery address for {active_task.dl_task_number}',
                                        notification_type='alert',
                                        related_task=active_task,
                                    )
                                except Exception:
                                    pass

                        step = 'success'
                        success = True

                except orders_models.Order.DoesNotExist:
                    error = 'Verification failed. Please try again.'
                    step = 'lookup'
                    lookup_form = forms.OrderLookupForm()
            else:
                # Form invalid - re-show update form; need to re-fetch order
                order_number = request.POST.get('order_number', '')
                phone_last4 = request.POST.get('phone_last4', '')
                try:
                    order = orders_models.Order.objects.select_related('business').get(
                        order_number__iexact=order_number
                    )
                    step = 'update'
                except orders_models.Order.DoesNotExist:
                    step = 'lookup'
                    error = 'Order not found. Please try again.'

    # AI-powered location extraction for geocoding
    geocode_location = ''
    ai_order_summary = ''
    if order and step == 'update':
        if order.customer_address:
            geocode_location = _ai_extract_location(order.customer_address)
        ai_order_summary = _ai_order_items_summary(order)

    context = {
        'lookup_form': lookup_form,
        'update_form': update_form,
        'order': order,
        'step': step,
        'error': error,
        'success': success,
        'geocode_location': geocode_location,
        'ai_order_summary': ai_order_summary,
    }
    return render(request, 'orders/update_location.html', context)


# =============================================================================
# BULK IMPORT VIEWS (SHARED - Staff & Client Dashboard)
# =============================================================================

@login_required
def bulk_import_orders(request):
    """
    Bulk import page with 4-step wizard.
    - Staff users: Can select any business from dropdown
    - Client users: Business is auto-selected based on logged-in user
    """
    is_staff_user = request.user.is_staff
    business = None
    businesses = None
    pickup_locations = []

    if is_staff_user:
        # Staff can select any business
        businesses = business_models.Business.objects.filter(
            business_status='active'
        ).order_by('business_name')
    else:
        # Client - get their business (using cached helper)
        business = get_cached_business(request)
        if business:
            pickup_locations = business_models.PickupLocation.objects.filter(
                business_id=business.business_id
            ).all()
        else:
            from django.contrib import messages
            messages.error(request, 'No business associated with your account')
            return redirect('business:business_dashboard')

    # Target fields for column mapping - grouped by category
    target_fields = [
        # Order Info
        {'name': 'client_order_code', 'label': 'Order ID', 'required': False, 'group': 'Order Info'},
        {'name': 'order_date', 'label': 'Order Date', 'required': False, 'group': 'Order Info'},

        # Customer
        {'name': 'customer_name', 'label': 'Customer Name', 'required': True, 'group': 'Customer'},
        {'name': 'customer_phone', 'label': 'Phone 1', 'required': True, 'group': 'Customer'},
        {'name': 'customer_whatsapp', 'label': 'Phone 2 / WhatsApp', 'required': False, 'group': 'Customer'},
        {'name': 'customer_email', 'label': 'Email', 'required': False, 'group': 'Customer'},

        # Address
        {'name': 'customer_address', 'label': 'Customer Address', 'required': True, 'group': 'Address'},
        {'name': 'dl_landmark', 'label': 'City / Landmark', 'required': False, 'group': 'Address'},
        {'name': 'dl_building', 'label': 'Villa / Building No', 'required': False, 'group': 'Address'},
        {'name': 'dl_street', 'label': 'Street No', 'required': False, 'group': 'Address'},
        {'name': 'dl_zone', 'label': 'Zone No', 'required': False, 'group': 'Address'},
        {'name': 'location_link', 'label': 'Location Link', 'required': False, 'group': 'Address'},
        {'name': 'dl_latitude', 'label': 'Latitude', 'required': False, 'group': 'Address'},
        {'name': 'dl_longitude', 'label': 'Longitude', 'required': False, 'group': 'Address'},

        # Delivery
        {'name': 'deadline_date', 'label': 'Day & Time Preference', 'required': False, 'group': 'Delivery'},

        # Product
        {'name': 'product_url', 'label': 'Product URL', 'required': False, 'group': 'Product'},
        {'name': 'package_desc', 'label': 'Package Desc', 'required': False, 'group': 'Product'},
        {'name': 'package_qty', 'label': 'Package Qty', 'required': False, 'group': 'Product'},
        {'name': 'cod_amount', 'label': 'Price / COD Amount', 'required': False, 'group': 'Product'},
        {'name': 'product_1', 'label': 'Product:1', 'required': False, 'group': 'Product'},
        {'name': 'count_1', 'label': 'Count:1', 'required': False, 'group': 'Product'},
        {'name': 'product_2', 'label': 'Product:2', 'required': False, 'group': 'Product'},
        {'name': 'count_2', 'label': 'Count:2', 'required': False, 'group': 'Product'},
        {'name': 'product_3', 'label': 'Product:3', 'required': False, 'group': 'Product'},
        {'name': 'count_3', 'label': 'Count:3', 'required': False, 'group': 'Product'},
        {'name': 'product_4', 'label': 'Product:4', 'required': False, 'group': 'Product'},
        {'name': 'count_4', 'label': 'Count:4', 'required': False, 'group': 'Product'},
        {'name': 'product_5', 'label': 'Product:5', 'required': False, 'group': 'Product'},
        {'name': 'count_5', 'label': 'Count:5', 'required': False, 'group': 'Product'},

        # Notes
        {'name': 'internal_notes', 'label': 'Notes By Ezzy', 'required': False, 'group': 'Notes'},
        {'name': 'seller_notes', 'label': 'Notes By Seller', 'required': False, 'group': 'Notes'},
    ]

    context = {
        'is_staff_user': is_staff_user,
        'business': business,
        'businesses': businesses,
        'pickup_locations': pickup_locations,
        'target_fields': target_fields,
    }

    # Use appropriate template based on user type
    if is_staff_user:
        template = 'workforce/orders_bulk_import.html'
    else:
        template = 'orders/bulk_import.html'

    return render(request, template, context)


@login_required
@require_POST
def bulk_import_preview(request):
    """
    AJAX endpoint to parse uploaded file and return columns with auto-mapping.
    """
    import csv
    import io

    if 'file' not in request.FILES:
        return JsonResponse({'error': 'No file provided'}, status=400)

    uploaded_file = request.FILES['file']
    file_name = uploaded_file.name.lower()

    try:
        # Parse based on file type
        if file_name.endswith('.csv'):
            content = uploaded_file.read().decode('utf-8-sig')
            reader = csv.DictReader(io.StringIO(content))
            rows = list(reader)
            columns = reader.fieldnames or []
        elif file_name.endswith(('.xlsx', '.xls')):
            df = pd.read_excel(uploaded_file, engine='openpyxl' if file_name.endswith('.xlsx') else 'xlrd')
            df = df.fillna('')
            columns = df.columns.tolist()
            rows = df.to_dict('records')
        else:
            return JsonResponse({'error': 'Unsupported file format. Use CSV, XLSX, or XLS.'}, status=400)

        if not columns:
            return JsonResponse({'error': 'No columns found in file'}, status=400)

        if len(rows) > 500:
            return JsonResponse({'error': 'Maximum 500 orders per import. Please split your file.'}, status=400)

        # Fuzzy matching with multiple strategies
        from difflib import SequenceMatcher

        def similarity_ratio(str1, str2):
            """Calculate similarity ratio between two strings."""
            return SequenceMatcher(None, str1.lower(), str2.lower()).ratio()

        def word_overlap_score(str1, str2):
            """Calculate word overlap score between two strings."""
            words1 = set(str1.lower().split())
            words2 = set(str2.lower().split())
            if not words1 or not words2:
                return 0
            intersection = words1 & words2
            union = words1 | words2
            return len(intersection) / len(union) if union else 0

        def get_best_match(col_name, patterns, threshold=0.6):
            """Find the best matching pattern for a column name using multiple strategies."""
            best_score = 0
            best_field = None

            # First pass: Look for exact matches only (highest priority)
            for field, pattern_list in patterns.items():
                for pattern in pattern_list:
                    if pattern == col_name:
                        return field, 1.0

            # Second pass: Look for full word matches (e.g., "product 1" matches pattern "product 1")
            for field, pattern_list in patterns.items():
                for pattern in pattern_list:
                    # Check if all words in pattern exist in col_name
                    pattern_words = pattern.split()
                    col_words = col_name.split()
                    if len(pattern_words) > 1 and pattern_words == col_words[:len(pattern_words)]:
                        return field, 0.99

            # Third pass: Fuzzy matching with scoring
            for field, pattern_list in patterns.items():
                for pattern in pattern_list:
                    # Skip single-word generic patterns for multi-word columns
                    # (prevents 'product' from matching 'product 1')
                    col_words = col_name.split()
                    if len(col_words) > 1 and ' ' not in pattern and pattern in col_name:
                        continue

                    # Strategy: Sequence similarity
                    seq_ratio = similarity_ratio(col_name, pattern)

                    # Strategy: Word overlap
                    word_score = word_overlap_score(col_name, pattern)

                    # Combined score (weighted average)
                    combined_score = (seq_ratio * 0.6) + (word_score * 0.4)

                    # Also check if key words match
                    pattern_words = set(pattern.lower().split())
                    if pattern_words and pattern_words.issubset(set(col_words)):
                        combined_score = max(combined_score, 0.9)

                    if combined_score >= threshold and combined_score > best_score:
                        best_score = combined_score
                        best_field = field

            return best_field, best_score

        # Auto-mapping logic with expanded patterns
        auto_mapping = {}

        # Target field labels (for direct matching with column names)
        field_labels = {
            'client_order_code': 'Order ID',
            'order_date': 'Order Date',
            'customer_name': 'Customer Name',
            'customer_phone': 'Phone 1',
            'customer_whatsapp': 'Phone 2 / WhatsApp',
            'customer_email': 'Email',
            'customer_address': 'Customer Address',
            'dl_landmark': 'City / Landmark',
            'dl_building': 'Villa / Building No',
            'dl_street': 'Street No',
            'dl_zone': 'Zone No',
            'location_link': 'Location Link',
            'dl_latitude': 'Latitude',
            'dl_longitude': 'Longitude',
            'deadline_date': 'Day & Time Preference',
            'product_url': 'Product URL',
            'package_desc': 'Package Desc',
            'package_qty': 'Package Qty',
            'cod_amount': 'Price / COD Amount',
            'product_1': 'Product 1',
            'count_1': 'Count 1',
            'product_2': 'Product 2',
            'count_2': 'Count 2',
            'product_3': 'Product 3',
            'count_3': 'Count 3',
            'product_4': 'Product 4',
            'count_4': 'Count 4',
            'product_5': 'Product 5',
            'count_5': 'Count 5',
            'internal_notes': 'Notes By Ezzy',
            'seller_notes': 'Notes By Seller',
        }

        mapping_patterns = {
            'client_order_code': ['order id', 'order no', 'orderid', 'order number', 'no', 'id', 'order', 'orderno', 'order code', 'client order'],
            'order_date': ['date', 'order date', 'created', 'created at', 'orderdate', 'creation date'],
            'customer_name': ['customer name', 'name', 'customer', 'full name', 'client name', 'buyer name', 'recipient', 'receiver name', 'customername', 'cust name'],
            'customer_phone': ['phone', 'phone 1', 'mobile', 'contact', 'phone1', 'tel', 'telephone', 'mob', 'mobile no', 'phone number', 'contact no', 'phonenumber', 'mobileno'],
            'customer_whatsapp': ['phone 2', 'whatsapp', 'phone2', 'watsapp', 'alternate phone', 'alt phone', 'secondary phone', 'whats app', 'wa number'],
            'customer_email': ['email', 'e-mail', 'customer email', 'mail', 'email address'],
            'customer_address': ['address', 'customer address', 'delivery address', 'full address', 'shipping address', 'addr', 'location', 'customeraddress', 'del address', 'destination'],
            'dl_landmark': ['city', 'landmark', 'customer city', 'land mark', 'city landmark', 'customer city land mark', 'area', 'locality', 'near', 'nearby'],
            'dl_building': ['building', 'villa', 'building no', 'villa no', 'bldg', 'building number', 'house', 'flat', 'apartment', 'apt', 'unit'],
            'dl_street': ['street', 'street no', 'street number', 'st no', 'streetno', 'road'],
            'dl_zone': ['zone', 'zone no', 'zone number', 'zoneno', 'area code', 'pin', 'pincode', 'postal'],
            'location_link': ['location', 'loclink', 'google map', 'map link', 'loc link', 'gps', 'map', 'location link', 'google link', 'maps'],
            'dl_latitude': ['latitude', 'lat', 'geo lat'],
            'dl_longitude': ['longitude', 'lng', 'long', 'geo long'],
            'deadline_date': ['day', 'time', 'day time', 'preferred', 'deadline', 'delivery date', 'day time if them have demand', 'expected', 'eta', 'delivery time', 'preferred time', 'slot'],
            'product_url': ['product url', 'url', 'product link', 'item url', 'link'],
            'package_desc': ['product name', 'product', 'item', 'item name', 'description', 'product description', 'productname', 'itemname', 'goods', 'items', 'package desc', 'package description'],
            'package_qty': ['qty', 'quantity', 'count', 'units', 'pcs', 'pieces', 'no of items', 'package qty'],
            'cod_amount': ['price', 'cod', 'amount', 'cod amount', 'total', 'value', 'order value', 'payment', 'cash', 'collect', 'collection'],
            'product_1': ['product 1', 'product:1', 'item 1', 'product1', 'product  1', 'additional products', 'additional product'],
            'count_1': ['count 1', 'count:1', 'qty 1', 'quantity 1', 'count1', 'qty1'],
            'product_2': ['product 2', 'product:2', 'item 2', 'product2', 'product  2'],
            'count_2': ['count 2', 'count:2', 'qty 2', 'quantity 2', 'count2', 'qty2'],
            'product_3': ['product 3', 'product:3', 'item 3', 'product3', 'product  3'],
            'count_3': ['count 3', 'count:3', 'qty 3', 'quantity 3', 'count3', 'qty3'],
            'product_4': ['product 4', 'product:4', 'item 4', 'product4', 'product  4'],
            'count_4': ['count 4', 'count:4', 'qty 4', 'quantity 4', 'count4', 'qty4'],
            'product_5': ['product 5', 'product:5', 'item 5', 'product5', 'product  5'],
            'count_5': ['count 5', 'count:5', 'qty 5', 'quantity 5', 'count5', 'qty5'],
            'internal_notes': ['notes by ezzy', 'ezzy notes', 'internal notes', 'staff notes', 'admin notes'],
            'seller_notes': ['notes by seller', 'seller notes', 'vendor notes', 'merchant notes', 'note', 'notes', 'remarks', 'comment', 'comments', 'instruction', 'instructions', 'special instructions'],
        }

        # Add field labels to patterns (for direct label matching)
        for field, label in field_labels.items():
            if field in mapping_patterns:
                mapping_patterns[field].append(label.lower())

        # Columns to skip/ignore from auto-mapping (not relevant for order import)
        ignore_columns = [
            'status', 'stock status', 'stock_status', 'stockstatus',
            'invoice', 'invoice no', 'invoice number', 'invoice_number', 'invoiceno',
            'payment status', 'payment_status', 'paymentstatus',
            'order status', 'order_status', 'orderstatus',
            'tracking', 'tracking no', 'tracking number',
            'fulfillment', 'fulfillment status',
            'customer notes', 'order notes', 'order_notes',
        ]

        for col in columns:
            col_lower = col.lower().strip()
            for char in ['\n', '/', '-', '_', '&', '(', ')', ':', ',', '.', '#', '\t', '\r']:
                col_lower = col_lower.replace(char, ' ')
            col_normalized = ' '.join(col_lower.split())
            logger.info(f'Processing column: "{col}" -> normalized: "{col_normalized}"')

            # Skip ignored columns
            if col_normalized in ignore_columns:
                logger.info(f'Skipping ignored column: "{col}"')
                continue

            # Special handling for numbered product/count columns (product 1, count 1, etc.)
            product_match = re.match(r'^(product|item)\s*(\d+)$', col_normalized)
            count_match = re.match(r'^(count|qty|quantity)\s*(\d+)$', col_normalized)

            if product_match:
                num = product_match.group(2)
                field_name = f'product_{num}'
                if field_name in mapping_patterns and field_name not in auto_mapping.values():
                    auto_mapping[col] = field_name
                    logger.info(f'Direct mapped "{col}" -> "{field_name}"')
                    continue

            if count_match:
                num = count_match.group(2)
                field_name = f'count_{num}'
                if field_name in mapping_patterns and field_name not in auto_mapping.values():
                    auto_mapping[col] = field_name
                    logger.info(f'Direct mapped "{col}" -> "{field_name}"')
                    continue

            # Try to find best match with 60% threshold (more lenient)
            best_field, match_score = get_best_match(col_normalized, mapping_patterns, threshold=0.6)
            if best_field and best_field not in auto_mapping.values():
                auto_mapping[col] = best_field
                logger.info(f'Auto-mapped column "{col}" -> field "{best_field}" (score: {match_score:.2f})')

        logger.info(f'Total auto-mappings: {len(auto_mapping)} - {auto_mapping}')

        # Create ImportLog with raw data before mapping
        business = None
        business_id = request.POST.get('business_id', '').strip()
        if request.user.is_staff and business_id:
            try:
                business = business_models.Business.objects.get(business_id=business_id)
            except business_models.Business.DoesNotExist:
                pass
        if not business:
            business = get_cached_business(request)

        import_log_id = None
        if business:
            import_log = orders_models.ImportLog.objects.create(
                business=business,
                source='csv_upload',
                status='started',
                initiated_by=request.user,
                total_rows=len(rows),
                raw_data=rows[:5000],  # cap to avoid huge JSON
                source_meta={
                    'file_name': uploaded_file.name,
                    'file_size': uploaded_file.size,
                    'columns_order': columns,
                },
            )
            import_log_id = import_log.id

        # Check for saved mapping from previous imports
        saved_mapping = {}
        use_saved_mapping = False
        if business:
            prev_log = orders_models.ImportLog.objects.filter(
                business=business, source='csv_upload'
            ).exclude(column_mapping={}).order_by('-id').first()
            if prev_log and prev_log.column_mapping:
                saved_mapping = prev_log.column_mapping
                use_saved_mapping = True

        return JsonResponse({
            'columns': columns,
            'rows': rows[:100],  # Limit preview rows
            'total_rows': len(rows),
            'auto_mapping': auto_mapping,
            'saved_mapping': saved_mapping,
            'use_saved_mapping': use_saved_mapping,
            'import_log_id': import_log_id,
        })

    except Exception as e:
        logger.error(f'Error parsing bulk import file: {e}')
        return JsonResponse({'error': f'Error parsing file: {str(e)}'}, status=400)


@login_required
@require_POST
def bulk_import_save_mapping(request):
    """Save column mapping for bulk CSV import (persists via ImportLog)."""
    try:
        mapping_str = request.POST.get('mapping', '{}')
        mapping = json.loads(mapping_str)
        business_id = request.POST.get('business_id', '').strip()

        business = None
        if request.user.is_staff and business_id:
            try:
                business = business_models.Business.objects.get(business_id=business_id)
            except business_models.Business.DoesNotExist:
                pass
        if not business:
            business = get_cached_business(request)
        if not business:
            return JsonResponse({'success': False, 'error': 'No business found'}, status=400)

        # Update the latest csv_upload ImportLog, or create a lightweight one
        log = orders_models.ImportLog.objects.filter(
            business=business, source='csv_upload'
        ).order_by('-id').first()
        if log:
            log.column_mapping = mapping
            log.save(update_fields=['column_mapping'])
        else:
            orders_models.ImportLog.objects.create(
                business=business,
                source='csv_upload',
                status='completed',
                initiated_by=request.user,
                column_mapping=mapping,
                source_meta={'note': 'saved_mapping_only'},
            )
        # Sync to shared business import mapping
        if mapping:
            business.import_mapping = mapping
            business.save(update_fields=['import_mapping'])

        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)


@login_required
@require_POST
def bulk_import_save(request):
    """
    AJAX endpoint to save a single order row from bulk import.
    - Staff users: business_id from request body
    - Client users: business from logged-in user
    """
    import uuid

    try:
        data = json.loads(request.body)
        row = data.get('row')
        row_index = data.get('row_index', 0)
        business_id = data.get('business_id')
        import_log_id = data.get('import_log_id')
        pickup_location_id = data.get('pickup_location_id')

        # Determine business based on user type
        if request.user.is_staff and business_id:
            # Staff user with business_id provided
            try:
                business = business_models.Business.objects.get(business_id=business_id)
            except business_models.Business.DoesNotExist:
                return JsonResponse({'success': False, 'error': 'Invalid business selected'}, status=400)
        else:
            # Client user - get their business (using cached helper)
            business = get_cached_business(request)
            if not business:
                return JsonResponse({'success': False, 'error': 'No business associated with your account'}, status=400)

        if not row:
            return JsonResponse({'success': False, 'error': 'No data provided'}, status=400)

        try:
            client_order_code = str(row.get('client_order_code', '')).strip()
            if not client_order_code:
                client_order_code = f"ORD-{uuid.uuid4().hex[:8].upper()}"

            # Check for duplicate
            if orders_models.Order.objects.filter(client_order_code=client_order_code).exists():
                return JsonResponse({
                    'success': False,
                    'row_index': row_index,
                    'error': f"Duplicate order code '{client_order_code}'"
                })

            # Validate required fields
            customer_name = str(row.get('customer_name', '')).strip()
            customer_phone = str(row.get('customer_phone', '')).strip()
            customer_address = str(row.get('customer_address', '')).strip()

            if not customer_name:
                return JsonResponse({
                    'success': False,
                    'row_index': row_index,
                    'error': 'Customer name is required'
                })
            if not customer_phone:
                return JsonResponse({
                    'success': False,
                    'row_index': row_index,
                    'error': 'Customer phone is required'
                })
            if not customer_address:
                return JsonResponse({
                    'success': False,
                    'row_index': row_index,
                    'error': 'Customer address is required'
                })

            # Convert Arabic numerals in phone numbers
            customer_phone = convert_arabic_numerals(customer_phone)

            # Format WhatsApp number
            raw_whatsapp = str(row.get('customer_whatsapp', '')).strip()
            if raw_whatsapp:
                customer_whatsapp = format_whatsapp_number(raw_whatsapp)
            else:
                customer_whatsapp = format_whatsapp_number(customer_phone)

            # Translate Arabic text
            customer_name_original = customer_name
            customer_address_original = customer_address
            customer_name_en = translate_to_english(customer_name)
            customer_address_en = translate_to_english(customer_address)

            if contains_arabic(customer_name):
                customer_name = customer_name_en
            if contains_arabic(customer_address):
                customer_address = customer_address_en

            # Parse numeric fields safely
            def safe_int(val):
                try:
                    return int(float(val)) if val else 0
                except (ValueError, TypeError):
                    return 0

            def safe_int_or_none(val):
                """Return None for empty values instead of 0 - for optional fields."""
                try:
                    if val is None or val == '' or (isinstance(val, str) and not val.strip()):
                        return None
                    return int(float(val))
                except (ValueError, TypeError):
                    return None

            def safe_decimal(val):
                try:
                    from decimal import Decimal
                    return Decimal(str(val)) if val else None
                except (ValueError, TypeError):
                    return None

            # Build notes
            notes_parts = []
            if row.get('order_notes'):
                notes_parts.append(f"Customer: {row.get('order_notes')}")
            if row.get('seller_notes'):
                notes_parts.append(f"Seller: {row.get('seller_notes')}")
            combined_notes = ' | '.join(notes_parts) if notes_parts else ''

            # Store original data
            original_data = {
                'import_data': row,
                'extra_fields': {
                    'customer_name_original': customer_name_original,
                    'customer_address_original': customer_address_original,
                    'customer_name_en': customer_name_en,
                    'customer_address_en': customer_address_en,
                    'name_was_translated': customer_name_original != customer_name_en,
                    'address_was_translated': customer_address_original != customer_address_en,
                    'customer_email': str(row.get('customer_email', '')),
                    'dl_landmark': str(row.get('dl_landmark', '')),
                    'location_link': str(row.get('location_link', '')),
                    'dl_latitude': str(row.get('dl_latitude', '')),
                    'dl_longitude': str(row.get('dl_longitude', '')),
                    'package_desc': str(row.get('package_desc', '')),
                    'product_url': str(row.get('product_url', '')),
                    'package_qty': str(row.get('package_qty', '')),
                    'stock_status': str(row.get('stock_status', '')),
                    'invoice_number': str(row.get('invoice_number', '')),
                    'seller_notes': str(row.get('seller_notes', '')),
                    'internal_notes': str(row.get('internal_notes', '')),
                }
            }

            # Resolve COD/payment status from import data
            _COD_STATUS_MAP = {
                'paid': 'online_paid', 'online paid': 'online_paid', 'online_paid': 'online_paid',
                'unpaid': 'unpaid', 'no cod': 'online_paid', 'nocod': 'online_paid',
                'pending': 'pending', 'cod': 'pending', 'cod pending': 'pending',
                'collected': 'collected',
                'partial': 'partial_paid', 'partial paid': 'partial_paid', 'partial_paid': 'partial_paid',
                # Shopify financial_status values
                'authorized': 'online_paid', 'voided': 'unpaid', 'refunded': 'unpaid',
                # WooCommerce status values
                'processing': 'online_paid', 'completed': 'online_paid',
                'on-hold': 'pending', 'cancelled': 'unpaid', 'pending payment': 'pending',
            }
            raw_cod_status = str(row.get('cod_status_by_client', '') or '').strip().lower()
            if not raw_cod_status:
                raw_cod_status = str(row.get('financial_status', '') or '').strip().lower()
            resolved_cod_status = _COD_STATUS_MAP.get(raw_cod_status) or None

            # Atomic: order + items + verification + import log commit or roll back as one unit
            with transaction.atomic():
                # Create Order
                order = orders_models.Order(
                    business=business,
                    client_order_code=client_order_code,
                    customer_name=customer_name,
                    customer_phone=customer_phone,
                    customer_whatsapp=customer_whatsapp,
                    customer_address=customer_address,
                    dl_zone=safe_int_or_none(row.get('dl_zone')),
                    dl_street=safe_int_or_none(row.get('dl_street')),
                    dl_building=safe_int_or_none(row.get('dl_building')),
                    cod_amount=safe_int(row.get('cod_amount')),
                    dl_amount=safe_int(row.get('dl_amount')),
                    cod_status_by_client=resolved_cod_status,
                    order_notes=combined_notes[:100] if combined_notes else str(row.get('order_notes', ''))[:100],
                    deadline_date=str(row.get('deadline_date', '')),
                    order_status='to_review',
                    verification_status='pending',
                    original_order_data=original_data,
                )
                # Set pickup location if provided
                if pickup_location_id:
                    try:
                        pl = business_models.PickupLocation.objects.get(id=pickup_location_id, business=business)
                        order.pickup_location = pl
                    except business_models.PickupLocation.DoesNotExist:
                        pass
                # Fallback: auto-assign fulfillment center
                if not order.pickup_location_id:
                    order.pickup_location = business_models.PickupLocation.objects.filter(
                        business=business, pickup_status='active', is_fulfilment_center=True
                    ).first() or business_models.PickupLocation.objects.filter(
                        business=business, pickup_status='active'
                    ).first()
                order.save()

                # Set package_description & package_qty
                package_desc_val = str(row.get('package_desc', '')).strip()
                if package_desc_val:
                    order.package_description = package_desc_val[:255]
                    order.package_qty = safe_int(row.get('package_qty')) or 1
                else:
                    desc_parts = []
                    total_qty = 0
                    for i in range(1, 6):
                        pn = str(row.get(f'product_{i}', '')).strip()
                        if pn:
                            pc = safe_int(row.get(f'count_{i}')) or 1
                            from workforce.views import _parse_coded_product_name
                            clean_pn, _ = _parse_coded_product_name(pn)
                            desc_parts.append(f"{clean_pn} x{pc}")
                            total_qty += pc
                    if desc_parts:
                        order.package_description = ', '.join(desc_parts)[:255]
                        order.package_qty = total_qty
                order.save(update_fields=['package_description', 'package_qty'])

                # Match product columns to actual Product records → create OrderItems
                from product.models import Product as ProductModel
                from workforce.views import _match_product_by_name
                items_created = 0
                product_names = []
                if package_desc_val:
                    product_names.append((package_desc_val, safe_int(row.get('package_qty')) or 1))
                for i in range(1, 6):
                    pn = str(row.get(f'product_{i}', '')).strip()
                    if pn:
                        pc = safe_int(row.get(f'count_{i}')) or 1
                        product_names.append((pn, pc))
                for pname, pqty in product_names:
                    matched = _match_product_by_name(pname, business)
                    if matched:
                        orders_models.OrderItem.objects.create(
                            order=order, product=matched, quantity=pqty,
                            unit_price=matched.item_price or 0,
                            notes=matched.item_name
                        )
                        items_created += 1

                # Create AddressVerification if lat/long provided
                lat = safe_decimal(row.get('dl_latitude'))
                lng = safe_decimal(row.get('dl_longitude'))
                if lat and lng:
                    orders_models.AddressVerification.objects.create(
                        order=order,
                        original_address=customer_address,
                        latitude=lat,
                        longitude=lng,
                        zone_number=safe_int(row.get('dl_zone')) or None,
                        street_number=safe_int(row.get('dl_street')) or None,
                        building_number=safe_int(row.get('dl_building')) or None,
                        notes=f"Landmark: {row.get('dl_landmark', '')} | Link: {row.get('location_link', '')}",
                        verification_result='pending'
                    )

                # Update ImportLog
                if import_log_id:
                    try:
                        il = orders_models.ImportLog.objects.get(id=import_log_id)
                        il.orders.add(order)
                        il.orders_created = (il.orders_created or 0) + 1
                        il.status = 'processing'
                        il.save(update_fields=['orders_created', 'status'])
                    except orders_models.ImportLog.DoesNotExist:
                        pass

            return JsonResponse({
                'success': True,
                'row_index': row_index,
                'order_id': order.id,
                'order_code': client_order_code,
                'customer_name': customer_name,
                'items_created': items_created
            })

        except Exception as e:
            # Track failed row in ImportLog
            if import_log_id:
                try:
                    il = orders_models.ImportLog.objects.get(id=import_log_id)
                    il.orders_failed = (il.orders_failed or 0) + 1
                    current_errors = il.errors or []
                    current_errors.append({'row': row_index, 'error': str(e)})
                    il.errors = current_errors
                    il.save(update_fields=['orders_failed', 'errors'])
                except orders_models.ImportLog.DoesNotExist:
                    pass
            return JsonResponse({
                'success': False,
                'row_index': row_index,
                'error': str(e)
            })

    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid JSON data'}, status=400)
    except Exception as e:
        logger.error(f'Error saving bulk import row: {e}')
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required
@require_POST
def bulk_import_finalize(request):
    """Finalize an ImportLog after all rows have been processed."""
    try:
        data = json.loads(request.body)
        import_log_id = data.get('import_log_id')
        column_mapping = data.get('column_mapping', {})

        if not import_log_id:
            return JsonResponse({'success': False, 'error': 'No import_log_id'}, status=400)

        il = orders_models.ImportLog.objects.get(id=import_log_id)
        if column_mapping:
            il.column_mapping = column_mapping
        il.mark_completed()
        # Fire auto flow for orders imported
        try:
            from core.auto_flow_executor import execute_flows_for_trigger
            execute_flows_for_trigger('staff_orders_imported', extra_context={
                'import_log_id': str(import_log_id),
                'total_rows': str(il.total_rows) if hasattr(il, 'total_rows') else '',
            })
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"Auto flow failed for orders imported: {e}")
        return JsonResponse({'success': True})
    except orders_models.ImportLog.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'ImportLog not found'}, status=404)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


# =============================================================================
# PUBLIC CUSTOMER TRACKING PAGE
# =============================================================================

def customer_tracking(request, token):
    """
    Public tracking page for customers. No login required.
    Accessed via WhatsApp link: /track/<token>/

    Shows order status timeline, delivery info, and a live map
    when the delivery is in an active status.
    """
    from delivery import models as delivery_models
    from fleet import models as fleet_models

    task = delivery_models.DeliveryTask.objects.select_related(
        'order', 'order__business', 'driver', 'driver__user',
        'business', 'dl_address_update',
    ).filter(tracking_token=token).first()

    if not task:
        return render(request, 'orders/customer_tracking.html', {
            'not_found': True,
        })

    order = task.order
    business = task.business or order.business

    # Get tracking config (or defaults)
    try:
        tracking_config = business.tracking_config
    except Exception:
        tracking_config = None

    if tracking_config and not tracking_config.is_active:
        return render(request, 'orders/customer_tracking.html', {
            'not_found': True,
        })

    # Get business logo
    logo = business_models.BusinessLogo.objects.filter(business=business).first()

    # Build status timeline
    STATUS_STEPS = [
        ('for_review', 'Order Received', 'fa-inbox'),
        ('pending', 'Processing', 'fa-cog'),
        ('assigned', 'Driver Assigned', 'fa-user-check'),
        ('picked_up', 'Picked Up', 'fa-box-open'),
        ('in_transit', 'On the Way', 'fa-truck'),
        ('delivered', 'Delivered', 'fa-check-circle'),
    ]
    # Map alternative statuses to their step
    STATUS_MAP = {
        'for_review': 0,
        'pending': 1,
        'assigned': 2, 'accepted': 2,
        'picked_up': 3, 'start_ride': 3,
        'out_for_delivery': 4, 'in_transit': 4, 'contacted': 4, 'non_reachable': 4,
        'delivered': 5,
    }
    current_step = STATUS_MAP.get(task.dl_task_status, 1)

    # Failed/cancelled get special treatment
    is_failed = task.dl_task_status in ('failed', 'cancelled', 'rejected')

    # Active delivery statuses where we show map
    ACTIVE_STATUSES = ['assigned', 'accepted', 'picked_up', 'start_ride',
                       'out_for_delivery', 'in_transit', 'contacted', 'non_reachable']
    show_map = task.dl_task_status in ACTIVE_STATUSES

    # Get driver location if active
    driver_lat = driver_lng = None
    if show_map and task.driver_id:
        latest_loc = fleet_models.DriverLocation.objects.filter(
            driver_id=task.driver_id
        ).order_by('-created_at').first()
        if latest_loc:
            driver_lat = float(latest_loc.latitude)
            driver_lng = float(latest_loc.longitude)

    # Delivery location
    delivery_lat = delivery_lng = None
    if order.latitude and order.longitude:
        delivery_lat = float(order.latitude)
        delivery_lng = float(order.longitude)

    # Get order items
    order_items = orders_models.OrderItem.objects.filter(order=order)

    # Config values
    primary_color = tracking_config.primary_color if tracking_config else '#f7c000'
    secondary_color = tracking_config.secondary_color if tracking_config else '#001f3f'
    show_driver_name = tracking_config.show_driver_name if tracking_config else True
    show_driver_phone = tracking_config.show_driver_phone if tracking_config else False
    show_eta = tracking_config.show_eta if tracking_config else True
    footer_text = tracking_config.custom_footer_text if tracking_config else ''

    context = {
        'task': task,
        'order': order,
        'business': business,
        'logo': logo,
        'status_steps': STATUS_STEPS,
        'current_step': current_step,
        'is_failed': is_failed,
        'show_map': show_map,
        'driver_lat': driver_lat,
        'driver_lng': driver_lng,
        'delivery_lat': delivery_lat,
        'delivery_lng': delivery_lng,
        'order_items': order_items,
        'primary_color': primary_color,
        'secondary_color': secondary_color,
        'show_driver_name': show_driver_name,
        'show_driver_phone': show_driver_phone,
        'show_eta': show_eta,
        'footer_text': footer_text,
    }
    return render(request, 'orders/customer_tracking.html', context)


def customer_tracking_data(request, token):
    """
    JSON endpoint for live map refresh on the customer tracking page.
    Returns driver lat/lng and current status.
    """
    from delivery import models as delivery_models
    from fleet import models as fleet_models

    task = delivery_models.DeliveryTask.objects.select_related(
        'driver',
    ).filter(tracking_token=token).first()

    if not task:
        return JsonResponse({'error': 'Not found'}, status=404)

    data = {
        'status': task.dl_task_status,
        'status_display': task.get_dl_task_status_display(),
        'driver_lat': None,
        'driver_lng': None,
    }

    if task.driver_id:
        latest_loc = fleet_models.DriverLocation.objects.filter(
            driver_id=task.driver_id
        ).order_by('-created_at').first()
        if latest_loc:
            data['driver_lat'] = float(latest_loc.latitude)
            data['driver_lng'] = float(latest_loc.longitude)

    return JsonResponse(data)
