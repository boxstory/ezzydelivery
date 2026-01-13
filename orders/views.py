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
import requests
from woocommerce import API as WooAPI
from decouple import config

from core import models as core_models
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


# =============================================================================
# ORDER LIST VIEWS
# =============================================================================


@login_required(login_url='account_login')
@business_permission_required(BusinessPermissions.ORDER_VIEW)
def orders_all_list(request):
    # Business is injected by the decorator
    business = request.current_business
    logger.info(f"User {request.user.id} accessing orders list for business {business.business_id}")

    # FIX: Use select_related for ForeignKeys and prefetch_related for reverse relations
    items = orders_models.Order.objects.filter(
        business=business.business_id
    ).select_related(
        'business',              # FK: Order → Business
        'pickup_location',       # FK: Order → PickupLocation
        'address_verified_by',   # FK: Order → User (address verifier)
        'verified_by',           # FK: Order → User (order verifier)
    ).prefetch_related(
        'order_items',                 # Reverse FK: Order ← OrderItem (related_name='order_items')
        'order_items__product',        # Through: OrderItem → Product
        'delivery_task',               # Reverse FK: Order ← DeliveryTask
        'delivery_task__driver',       # Through: DeliveryTask → Driver
        'delivery_task__business',     # Through: DeliveryTask → Business
    ).order_by('-id')

    logger.debug(f"Fetching orders for business {business.business_id}")

    default_page = 1
    page = request.GET.get('page', default_page)
    # Paginate items
    items_per_page = 10  # Increased from 5 for better UX
    paginator = Paginator(items, items_per_page)

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
        # Permission checks for template buttons
        'can_create_order': user_has_business_permission(request.user, BusinessPermissions.ORDER_CREATE),
        'can_edit_order': user_has_business_permission(request.user, BusinessPermissions.ORDER_EDIT),
        'can_delete_order': user_has_business_permission(request.user, BusinessPermissions.ORDER_DELETE),
    }
    return render(request, 'orders/order_all_list.html', context)


@login_required(login_url='account_login')
@business_permission_required(BusinessPermissions.ORDER_VIEW)
def orders_pending_list(request):
    # Business is injected by the decorator
    business = request.current_business
    logger.info(f"User {request.user.id} accessing pending orders for business {business.business_id}")

    # FIX: Optimize with select_related and prefetch_related
    orders = orders_models.Order.objects.filter(
        delivery_task__dl_task_status_dms__in=['4', '5', '6'],
        business=business.business_id
    ).select_related(
        'business',
        'pickup_location',
        'address_verified_by',
        'verified_by',
    ).prefetch_related(
        'order_items',
        'delivery_task',
        'delivery_task__driver',
        'delivery_task__business',
    ).order_by('-id')

    logger.debug(f"Fetching pending orders for business {business.business_id}")

    default_page = 1
    page = request.GET.get('page', default_page)
    # Paginate items
    items_per_page = 10
    paginator = Paginator(orders, items_per_page)

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
    }
    return render(request, 'orders/order_pending_list.html', context)

@login_required(login_url='account_login')
@business_permission_required(BusinessPermissions.ORDER_VIEW)
def orders_successfull_list(request):
    # Business is injected by the decorator
    business = request.current_business
    logger.info(f"User {request.user.id} accessing successful orders for business {business.business_id}")

    # FIX: Optimize with select_related and prefetch_related
    orders = orders_models.Order.objects.filter(
        delivery_task__dl_task_status_dms='2',
        business=business.business_id
    ).select_related(
        'business',
        'pickup_location',
        'address_verified_by',
        'verified_by',
    ).prefetch_related(
        'order_items',
        'delivery_task',
        'delivery_task__driver',
        'delivery_task__business',
    ).order_by('-id')

    logger.debug(f"Fetching successful orders for business {business.business_id}")

    default_page = 1
    page = request.GET.get('page', default_page)
    # Paginate items
    items_per_page = 10
    paginator = Paginator(orders, items_per_page)

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
    }
    return render(request, 'orders/order_successful_list.html', context)


@login_required(login_url='account_login')
@business_permission_required(BusinessPermissions.ORDER_VIEW)
def orders_unsuccessfull_list(request):
    # Business is injected by the decorator
    business = request.current_business
    logger.info(f"User {request.user.id} accessing unsuccessful orders for business {business.business_id}")

    # FIX: Optimize with select_related and prefetch_related
    orders = orders_models.Order.objects.filter(
        delivery_task__dl_task_status_dms__in=['7', '8', '9'],
        business=business.business_id
    ).select_related(
        'business',
        'pickup_location',
        'address_verified_by',
        'verified_by',
    ).prefetch_related(
        'order_items',
        'delivery_task',
        'delivery_task__driver',
        'delivery_task__business',
    ).order_by('-id')

    logger.debug(f"Fetching unsuccessful orders for business {business.business_id}")

    default_page = 1
    page = request.GET.get('page', default_page)
    # Paginate items
    items_per_page = 10
    paginator = Paginator(orders, items_per_page)

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
    }
    return render(request, 'orders/order_unsuccessful_list.html', context)


@login_required(login_url='account_login')
def latest_orders_list(request):
    business = business_models.Business.objects.get(user_id=request.user.id)
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
    # Paginate items
    items_per_page = 10
    paginator = Paginator(orders, items_per_page)

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
    }
    return render(request, 'orders/order_list_view.html', context)

# order uploading section ----------------------------------------------------------------



@login_required(login_url='account_login')
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
    
    business = business_models.Business.objects.get(user_id=request.user.id)
    context = {
        'form': form,
        'business': business
    }
    return render(request, 'orders/order_file_upload.html',  context)

@login_required(login_url='account_login')
def order_upload_review_data(request):
    if 'uploaded_data' not in request.session:
        messages.error(request, 'No data to review. Please upload a file first.')
        return redirect('orders:order_upload_file')

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

            for row in edited_data:
                order_form = orders_forms.AddOrderForm(row)
                if order_form.is_valid():
                    logger.debug(f"Order form valid for row {i}")
                    order_form.save()
                else:
                    logger.warning(f"Order form invalid for row {i}: {order_form.errors}")
                    messages.error(request, f'Error in row {i}: {order_form.errors}')
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

    pickup_locations = business_models.PickupLocation.objects.filter(
        business_id=business.business_id
    ).all()

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

    pickup_locations = business_models.PickupLocation.objects.filter(
        business_id=business.business_id).all()

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
                return redirect('orders:add_order_product', order_id=order.id)
        else:
            logger.debug("Loading add_order form")
            form = orders_forms.AddOrderForm(
                business_id=business.business_id,
                business_code=business.business_code
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
def add_order_bulk(request):
    """
    Handle bulk order submission from Excel-like table view.
    Processes multiple orders submitted via the table interface.
    """
    import json
    from django.contrib import messages

    if request.method != 'POST':
        return redirect('orders:add_order')

    try:
        business = business_models.Business.objects.get(user_id=request.user.id)
    except business_models.Business.DoesNotExist:
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
        business = business_models.Business.objects.get(user_id=request.user.id)
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

            for i, product_id in enumerate(product_ids):
                if not product_id:  # Skip empty product selections
                    continue

                try:
                    from product import models as product_models
                    product = product_models.Product.objects.get(id=product_id, business=business)

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

                except product_models.Product.DoesNotExist:
                    errors.append(f"Product #{i+1} not found")
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
    try:
        business = business_models.Business.objects.get(user_id=request.user.id)
        search_term = request.GET.get('q', '').strip()

        # Require minimum 3 characters
        if len(search_term) < 3:
            return JsonResponse({'results': [], 'pagination': {'more': False}})

        from product import models as product_models

        # Search products by name, SKU, or brand
        products = product_models.Product.objects.filter(
            business=business
        ).filter(
            Q(item_name__icontains=search_term) |
            Q(brand_name__icontains=search_term) |
            Q(item_sku__icontains=search_term)
        ).select_related('unit')[:20]  # Limit to 20 results

        results = []
        for product in products:
            # Get inventory status if fulfillment is enabled
            inventory_qty = None
            if business.fulfillment_service_enabled:
                inventory = product_models.ProductInventory.objects.filter(
                    item_sku=product
                ).first()
                inventory_qty = inventory.item_quantity if inventory else 0

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
        order_product_formset = OrderFormset(queryset=orders_models.OrderItem.objects.none())



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
def deliver_to_here(request, pickup_id):
    pickup_location = business_models.PickupLocation.objects.filter(
        id=pickup_id).first()
    if request.method == 'POST':
        form = orders_forms.UpdateOrderForm(request.POST, )
        print('form valid checking')
        if form.is_valid():
            print('form valid')
            form.save()
            form.business = business_models.Business.objects.get(
                    business_id=request.user.id)
            return  redirect('orders:orders_all_list')
    else:
        form = orders_forms.UpdateOrderForm()

    context = {
        'form': form,
    }
    return render(request, 'orders/order_update.html', context)


@login_required(login_url='account_login')
def pick_from_here(request, pickup_id):
    """Add order with a pre-selected pickup location."""
    import json

    business = business_models.Business.objects.get(user_id=request.user.id)
    pickup_location = business_models.PickupLocation.objects.filter(
        id=pickup_id, business_id=business.business_id).first()

    if not pickup_location:
        messages.error(request, "Pickup location not found.")
        return redirect('business:pickup_location_list')

    pickup_locations = business_models.PickupLocation.objects.filter(
        business_id=business.business_id).all()

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

        if request.method == 'POST':
            form = orders_forms.UpdateOrderForm(request.POST, instance=order)

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
            form = orders_forms.UpdateOrderForm(instance=order)

        context = {
            'form': form,
            'order': order,
            'order_id': order_id
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
        ).get(id=order_id, business=business)

        logger.info(f"User {request.user.id} viewing order details for order {order_id}")

        data = {
            'order': order,
            'can_edit_order': user_has_business_permission(request.user, BusinessPermissions.ORDER_EDIT),
            'can_delete_order': user_has_business_permission(request.user, BusinessPermissions.ORDER_DELETE),
        }
        return render(request, 'orders/order_details.html', data)

    except orders_models.Order.DoesNotExist:
        logger.warning(f"Order {order_id} not found or unauthorized access by user {request.user.id}")
        messages.error(request, "Order not found")
        return redirect('orders:orders_all_list')




@login_required(login_url='account_login')
def update_order_product(request, order_id):
    """Update order product items using OrderItem model"""
    order = orders_models.Order.objects.get(id=order_id)
    order_items = orders_models.OrderItem.objects.filter(order=order)

    if request.method == 'POST':
            print("POST form in views")
            form = orders_forms.AddOrderProductsForm(request.POST)

            if form.is_valid():
                print("valid form")
                order_item = form.save(commit=False)
                order_item.order = order
                order_item.save()
                return  redirect('orders:orders_all_list')
    else:
        form = orders_forms.AddOrderProductsForm(initial={'order': order})
        print('else form')

    data = {
        'order': order,
        'form': form,
        'order_items': order_items
    }
    return render(request, 'orders/update_order_product.html', data)

@login_required(login_url='account_login')
def order_product_list(request, order_id):
    """List all products in an order using OrderItem model"""
    order = get_object_or_404(orders_models.Order, id=order_id)
    print('order' + str(order))
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

    print('Ordered items:', ordered_items)
    print('Listed products:', listed_products)

    data = {
        'order': order,
        'ordered_items': ordered_items,
        'listed_products': listed_products,
    }
    return render(request, 'orders/parts/order_product_list.html', data)

# operation links

@require_POST
def update_order_status(request):
    if request.method == 'POST' and request.is_ajax():
        # Assuming you have a model named "YourModel" with a "status" field
        order_id = request.POST.get('order_id')
        print('update_order_status - view', order_id)
        status = request.POST.get('status')
        print(status)
        order = orders_models.Order.objects.get(pk=order_id)
        order.order_status = status
        print(order.order_status)
        order.save()

        # Return a JSON response indicating success
        return JsonResponse({'status': 'success'})

    # Return a JSON response indicating failure
    return JsonResponse({'status': 'error'})


@require_POST
def add_order_comment(request, order_id):
    """Add a comment to order's comment chain via HTMX"""
    try:
        order = orders_models.Order.objects.get(pk=order_id)
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
        order = orders_models.Order.objects.get(pk=order_id)
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
    # IDOR FIX: Get user's business with authorization check
    try:
        user_business = request.user.user_business.first()
        if not user_business:
            logger.warning(f"User {request.user.id} has no associated business")
            messages.error(request, "No business associated with your account")
            return redirect('business_dashboard')

        business = business_models.Business.objects.get(user_id=user_business.user_id)
    except business_models.Business.DoesNotExist:
        logger.warning(f"Business not found for user {request.user.id}")
        messages.error(request, "Business not found")
        return redirect('business_dashboard')

    api_data = business_models.BusinessApiSettings.objects.filter(
        business_id=business.business_id,
        is_verify_api='True',
        is_default='True'
    ).first()

    if not api_data:
        logger.warning(f"No API settings found for business {business.business_id}")
        messages.error(request, "No API configuration found. Please configure your Shopify API settings.")
        return redirect('business:business_settings_api_list', business.business_id)

    logger.debug(f"Using API settings for business {business.business_id}")

    # SECURITY FIX: Use environment variable for Shopify token instead of hardcoded value
    shopify_token = config('SHOPIFY_ACCESS_TOKEN', default='')
    if not shopify_token:
        logger.error("SHOPIFY_ACCESS_TOKEN not configured in .env file")
        messages.error(request, "Shopify API token not configured")
        return redirect('business:business_settings_api_list', business.business_id)

    headers = {
        'Content-Type': 'application/json',
        'X-Shopify-Access-Token': shopify_token
    }

    try:
        get_orders = requests.get('https://hn0d1z-qe.myshopify.com/admin/api/2024-10/orders.json?status=any', headers=headers, timeout=30)
    except requests.exceptions.RequestException as e:
        logger.error(f"Shopify API request failed: {e}")
        messages.error(request, "Failed to connect to Shopify API")
        return redirect('orders_all_list')
    # Parse message as json
    GetQuestion_response = "json.loads(GetQuestion_response['Message'])"
    print(request.POST.get('start_date'))
    if request.method == 'POST':
        order_list_start_date = request.POST.get('start_date')
        order_list_end_date = request.POST.get('end_date')
        print( "posted dates")
    else:
        order_list_start_date = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
        order_list_end_date = datetime.now().strftime('%Y-%m-%d')
        print( "default dates")
    
    print(order_list_start_date)
    print(order_list_end_date)

    if get_orders.status_code == 200:
        order_data = get_orders.json()
        orders = order_data.get('orders', [])
        filtered_orders = [
            order for order in orders
            if order_list_start_date <= order['created_at'][:10] <= order_list_end_date
        ]
        filtered_orders.sort(key=lambda x: x['created_at'], reverse=True)
        
        data={
            'GetQuestion_response' : GetQuestion_response,
            'order_data': order_data,
            'orders': orders,
            'business': business,


        }
        return render(request, 'orders/order_api_get.html', data)
    else:
        return JsonResponse({'status': 'error', 'message': 'Failed to fetch orders from Shopify'})


@login_required(login_url='account_login')
def get_orders_by_base_api(request):
    # IDOR FIX: Get user's business with authorization check
    try:
        user_business = request.user.user_business.first()
        if not user_business:
            logger.warning(f"User {request.user.id} has no associated business")
            messages.error(request, "No business associated with your account")
            return redirect('business_dashboard')

        business = business_models.Business.objects.get(user_id=user_business.user_id)
        business_id = business.business_id
    except business_models.Business.DoesNotExist:
        logger.warning(f"Business not found for user {request.user.id}")
        messages.error(request, "Business not found")
        return redirect('business_dashboard')

    business_api = business_models.BusinessApiSettings.objects.filter(
        business_id=business_id,
        is_verify_api='True',
        is_default='True'
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
        shop_creds = {
            'api_key': BASE_API_KEY,
            'api_secret': BASE_API_SECRET,
            'access_token': BASE_API_ACCESS_KEY, 
        }

        with open('shopify_creds.json', 'w') as f:
            json.dump(shop_creds, f)

        shop_url = "%s" % BASE_API_STORE_NAME
        print('shopify shop_url', shop_url)

        order_base_url = 'https://' + shop_url + BASE_API_ORDER_ENDPINT
        product_base_url = 'https://' + shop_url + BASE_API_PRODUCT_ENDPINT
        header_value = { 'X-Shopify-Access-Token': BASE_API_ACCESS_KEY, 'Content-Type': 'application/json' }

        order_response = requests.get(order_base_url, headers=header_value, params={'status': 'any', 'limit': 10})
        order_count = len(order_response.json().get('orders', []))

        print('order_count', order_count    )
        product_response = requests.get(product_base_url, headers=header_value )
        product_count = len(product_response.json().get('products', []))
        print('product_count', product_count)

    elif business_api.api_type == 'woocommerce':
        url="http://example.com",
        shop_url = 'https://' + BASE_API_STORE_NAME 
        print('woocommerce shop_url', shop_url)
 
        wcapi = WooAPI(
            url= shop_url,
            consumer_key= BASE_API_KEY,
            consumer_secret= BASE_API_SECRET,
            version="wc/v3",
        )

        
        #print(wcapi.get("products", params={"per_page": 20}).json())

        order_response = wcapi.get("orders")
        order_date = order_response.headers.get('Date')
        print('order_date', order_date)
        order_count = order_response.headers.get('X-WP-Total')
        print('order_count', order_count)
        product_response = wcapi.get("products", params={"per_page": 20})
        product_count = product_response.headers.get('X-WP-Total')
        print('product_count', product_count)
 
    else:
        order_response = None
        product_response = None


    start_date = (datetime.now() - timedelta(days=10)).strftime('%Y-%m-%d')
    end_date = datetime.now().strftime('%Y-%m-%d')
    print('start_date', start_date)
    print('end_date', end_date)

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
                print('order in order_response', order)

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
