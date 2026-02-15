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
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.db.models import Q
from datetime import datetime, timedelta, timezone
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

    context = {
        'orders': orders,
        'business': business,
        'len': paginator.count,  # Use paginator.count (cached) instead of items.count()
        'per_page': str(per_page),  # String for template comparison
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

    context = {
        'orders': orders,
        'business': business,
        'len': paginator.count,
        'per_page': str(per_page),
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
        messages.warning(request, "Please add a pickup location first.")
        return redirect('business:pickup_location_add')

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
                    client_order_code=row_data['client_order_code'] or f"BULK-{datetime.now().strftime('%Y%m%d%H%M%S')}-{i}",
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
                product_name = request.POST.get(f'data[{i}][product_name]', '')
                qty = request.POST.get(f'data[{i}][qty]', '1')
                price = request.POST.get(f'data[{i}][price]', '0')

                if product_name:
                    # Store product info in order notes for now
                    order.order_notes = f"{order.order_notes} | Product: {product_name}, Qty: {qty}, Price: {price}".strip(' |')
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
        logger.debug("No pickup locations, redirecting to add")
        return redirect('business:pickup_location_add')
    else:
        if request.method == 'POST':
            logger.debug("Processing POST form for add_order")
            form = orders_forms.AddOrderForm(request.POST)

            if form.is_valid():
                logger.debug("Form is valid, saving order")
                order = form.save(commit=False)
                order.business = business_models.Business.objects.get(
                    business_id=business.business_id)
                logger.debug(f"Order business_id: {order.business_id}")
                order = form.save()
                logger.info(f"Order created with id: {order.id}")
                # Only redirect to add products if fulfillment service is enabled
                if business.fulfillment_service_enabled:
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

    return render(request, 'orders/order_add.html', {
        'form': form,
        'business': business,
        'pickup_locations': pickup_locations,
        'pickup_locations_json': pickup_locations_json,
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
                cod_status_by_client=order_data.get('cod_status_by_client', 'no_cod'),
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

                except (ValueError, IndexError) as e:
                    errors.append(f"Invalid data for product #{i+1}: {str(e)}")

            if products_added > 0:
                logger.info(f"{products_added} product(s) added successfully to order {order_id}")
                messages.success(request, f"{products_added} product(s) added to order successfully")
                return redirect('orders:orders_all_list')
            elif errors:
                for error in errors:
                    messages.error(request, error)
            else:
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
                'text': f"{product.brand_name} {product.item_name}",
                'sku': product.item_sku,
                'price': float(product.item_price),
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
            form = orders_forms.UpdateOrderForm(request.POST, instance=order, is_staff=is_staff)

            if order.task_status == 'dl_task_listed':
                logger.warning(f"Cannot update order {order_id} - already published in delivery tasks")
                messages.error(request, 'Cannot update order published in Delivery Tasks. Contact Operation Admin')
                return redirect('orders:orders_all_list')

            if form.is_valid():
                logger.info(f"Order {order_id} updated successfully")
                form.save()
                messages.success(request, 'Order updated successfully.')
                return redirect('orders:orders_all_list')
            else:
                logger.warning(f"Invalid order update form for order {order_id}: {form.errors}")
        else:
            form = orders_forms.UpdateOrderForm(instance=order, is_staff=is_staff)

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
        # These FK constraints would block order deletion in PostgreSQL
        from delivery import models as delivery_models
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

        data = {
            'order': order,
            'delivery_task': delivery_task,
            'order_items': order_items,
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
        # Get order_id from URL or request body
        if order_id is None:
            # Try JSON body first
            if request.content_type == 'application/json':
                import json
                data = json.loads(request.body)
                order_id = data.get('order_id')
                status = data.get('status')
            else:
                # Fall back to form POST
                order_id = request.POST.get('order_id')
                status = request.POST.get('status')
        else:
            # order_id from URL, status from body
            if request.content_type == 'application/json':
                import json
                data = json.loads(request.body)
                status = data.get('status')
            else:
                status = request.POST.get('status')

        if not order_id or not status:
            return JsonResponse({'success': False, 'error': 'Missing order_id or status'}, status=400)

        order = orders_models.Order.objects.get(pk=order_id)

        # Check user has permission (owner or staff)
        if not request.user.is_staff:
            user_business = get_cached_business(request)
            if not user_business or user_business.business_id != order.business_id:
                return JsonResponse({'success': False, 'error': 'Permission denied'}, status=403)

        # Published orders: only staff can revert to to_review
        if order.order_status == 'publish':
            if not request.user.is_staff:
                return JsonResponse({'success': False, 'error': 'Published orders cannot be changed. Contact staff.'}, status=403)
            if status != 'to_review':
                return JsonResponse({'success': False, 'error': 'Published orders can only be reverted to Hold for Review.'}, status=400)

        # Delivered/cancelled orders cannot be changed by business users
        if order.order_status in ('delivered', 'cancelled') and not request.user.is_staff:
            return JsonResponse({'success': False, 'error': 'This order status cannot be changed.'}, status=403)

        old_status = order.order_status
        order.order_status = status
        order.save()

        # Reverse sync: cancel active delivery tasks when order is cancelled
        if status == 'cancelled' and old_status != 'cancelled':
            from delivery import models as delivery_models
            delivery_models.DeliveryTask.objects.filter(
                order=order
            ).exclude(
                dl_task_status__in=['delivered', 'cancelled', 'failed']
            ).update(
                dl_task_status='cancelled',
                dl_task_status_dms='9'
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
                dl_task_status='cancelled',
                dl_task_status_dms='9'
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

    try:
        get_orders = requests.get(api_url, headers=headers, params={'status': 'any'}, timeout=30)
    except requests.exceptions.RequestException as e:
        logger.error(f"Shopify API request failed: {e}")
        messages.error(request, "Failed to connect to Shopify API")
        return redirect('orders:orders_all_list')

    logger.debug(f'Start date from POST: {request.POST.get("start_date")}')
    if request.method == 'POST':
        order_list_start_date = request.POST.get('start_date')
        order_list_end_date = request.POST.get('end_date')
        logger.debug('Using posted date range')
    else:
        order_list_start_date = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
        order_list_end_date = datetime.now().strftime('%Y-%m-%d')
        logger.debug('Using default date range (last 30 days)')

    logger.debug(f'Date range: {order_list_start_date} to {order_list_end_date}')

    if get_orders.status_code == 200:
        order_data = get_orders.json()
        orders = order_data.get('orders', [])
        filtered_orders = [
            order for order in orders
            if order_list_start_date <= order['created_at'][:10] <= order_list_end_date
        ]
        filtered_orders.sort(key=lambda x: x['created_at'], reverse=True)

        data={
            'order_data': order_data,
            'orders': filtered_orders,
            'business': business,
        }
        return render(request, 'orders/order_api_get.html', data)
    else:
        return JsonResponse({'status': 'error', 'message': 'Failed to fetch orders from Shopify'})


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


    start_date = (datetime.now() - timedelta(days=10)).strftime('%Y-%m-%d')
    end_date = datetime.now().strftime('%Y-%m-%d')
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
def verify_location(request, token):
    """
    Public view for customers to verify their delivery location
    """
    from orders.models import AddressVerification
    from django.utils import timezone
    
    try:
        # Get address verification by token
        address_verification = get_object_or_404(
            AddressVerification,
            verification_token=token
        )
        
        # Check if token is expired
        if address_verification.is_token_expired():
            return render(request, 'orders/verification_expired.html', {
                'order': address_verification.order
            })
        
        order = address_verification.order
        
        if request.method == 'POST':
            # Get form data
            latitude = request.POST.get('latitude')
            longitude = request.POST.get('longitude')
            verified_address = request.POST.get('verified_address')
            zone_number = request.POST.get('zone_number')
            street_number = request.POST.get('street_number')
            building_number = request.POST.get('building_number')
            notes = request.POST.get('notes')
            
            # Update address verification
            address_verification.latitude = latitude
            address_verification.longitude = longitude
            address_verification.verified_address = verified_address or address_verification.original_address
            address_verification.zone_number = zone_number if zone_number else None
            address_verification.street_number = street_number if street_number else None
            address_verification.building_number = building_number if building_number else None
            address_verification.notes = notes
            address_verification.verification_result = 'address_verified'
            address_verification.customer_verified_at = timezone.now()
            address_verification.save()
            
            # Update order verification status
            order.verification_status = 'address_verified'
            order.save()
            
            return render(request, 'orders/verification_success.html', {
                'order': order
            })
        
        # GET request - show verification form with map
        context = {
            'order': order,
            'address_verification': address_verification,
            'google_maps_api_key': config('GOOGLE_MAPS_API_KEY', default=''),
        }
        
        return render(request, 'orders/verify_location.html', context)
        
    except Exception as e:
        logger.error(f"Error in location verification: {str(e)}")
        return render(request, 'orders/verification_error.html', {
            'error': 'Invalid or expired verification link'
        })


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
                        order.address_verified = True
                        order.address_verified_at = timezone.now()
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

                        # Update DlAddressUpdate if exists
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
                        if dl_update_fields:
                            DlAddressUpdate.objects.filter(order=order).update(**dl_update_fields)

                        # Save preferred delivery time to DeliveryTask
                        preferred_times = request.POST.getlist('preferred_time')
                        if preferred_times:
                            order.delivery_task.all().update(preferred_time=','.join(preferred_times))

                        # Save payment method to DeliveryTask
                        payment_method = request.POST.get('payment_method', '')
                        if payment_method:
                            order.delivery_task.all().update(payment_method=payment_method)

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
        {'name': 'product_name', 'label': 'Product Name', 'required': False, 'group': 'Product'},
        {'name': 'quantity', 'label': 'Qty', 'required': False, 'group': 'Product'},
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
@business_access_required()
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
            'product_name': 'Product Name',
            'quantity': 'Qty',
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
            'product_name': ['product name', 'product', 'item', 'item name', 'description', 'product description', 'productname', 'itemname', 'goods', 'items'],
            'quantity': ['qty', 'quantity', 'count', 'units', 'pcs', 'pieces', 'no of items'],
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

        return JsonResponse({
            'columns': columns,
            'rows': rows[:100],  # Limit preview rows
            'total_rows': len(rows),
            'auto_mapping': auto_mapping
        })

    except Exception as e:
        logger.error(f'Error parsing bulk import file: {e}')
        return JsonResponse({'error': f'Error parsing file: {str(e)}'}, status=400)


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
                    'product_name': str(row.get('product_name', '')),
                    'product_url': str(row.get('product_url', '')),
                    'quantity': str(row.get('quantity', '')),
                    'stock_status': str(row.get('stock_status', '')),
                    'invoice_number': str(row.get('invoice_number', '')),
                    'seller_notes': str(row.get('seller_notes', '')),
                    'internal_notes': str(row.get('internal_notes', '')),
                }
            }

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
                order_notes=combined_notes[:100] if combined_notes else str(row.get('order_notes', ''))[:100],
                deadline_date=str(row.get('deadline_date', '')),
                order_status='to_review',
                verification_status='pending',
                original_order_data=original_data,
            )
            order.save()

            # Create OrderItems
            items_created = 0
            product_name = str(row.get('product_name', '')).strip()
            if product_name:
                orders_models.OrderItem.objects.create(
                    order=order,
                    quantity=safe_int(row.get('quantity')) or 1,
                    unit_price=safe_decimal(row.get('cod_amount')),
                    notes=f"{product_name} | URL: {row.get('product_url', '')}" if row.get('product_url') else product_name
                )
                items_created += 1

            for i in range(1, 6):
                prod_name = str(row.get(f'product_{i}', '')).strip()
                prod_count = safe_int(row.get(f'count_{i}')) or 1
                if prod_name:
                    orders_models.OrderItem.objects.create(
                        order=order,
                        quantity=prod_count,
                        notes=prod_name
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

            return JsonResponse({
                'success': True,
                'row_index': row_index,
                'order_id': order.id,
                'order_code': client_order_code,
                'customer_name': customer_name,
                'items_created': items_created
            })

        except Exception as e:
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
