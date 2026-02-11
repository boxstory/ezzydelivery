"""
Product Views Module
====================

This module handles product catalog management for businesses.

Views:
    Product List:
        - product_all_list: Display all products (table view)
        - product_all_list_card: Display all products (card view)

    Product CRUD:
        - product_single_add: Add new product
        - product_single_update: Edit existing product
        - product_single_delete: Delete product

    Inventory:
        - product_inventory: Display inventory management page

    Categories:
        - product_categories: Display product categories

Security:
    All views (except product_categories) require authentication.
    IDOR protection ensures users can only access their business's products.

Query Optimization:
    Views use select_related() to prevent N+1 queries on ForeignKey fields
    (color, unit, business, product_category).

Related:
    - product.models: Product, ProductCategory, ColorVariant, UnitVariant
    - product.forms: AddItemsForm
    - business.models: Business
"""

import logging
import json
from django.shortcuts import redirect, render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods


from product import models as product_models
from business import models as business_models
from warehouse import models as warehouse_models
from product import forms as product_forms
from core.context_processors import get_cached_business
from django.core.paginator import Paginator
from django.db.models import Sum, F, Q

# Local aliases for commonly used models
Product = product_models.Product
ProductCategory = product_models.ProductCategory
ColorVariant = product_models.ColorVariant
UnitVariant = product_models.UnitVariant
Business = business_models.Business

logger = logging.getLogger('product')


# =============================================================================
# PRODUCT LIST VIEWS
# =============================================================================


# -----------------------------------------------------------------------------
# product_all_list: Display all products for the logged-in user's business.
# Uses select_related to prevent N+1 queries on FK fields.
# Template: product/product_all_list.html
# -----------------------------------------------------------------------------
@login_required(login_url='account_login')
def product_all_list(request):
    """
    Display all products for the logged-in user's business.

    OPTIMIZATION: Uses select_related to prevent N+1 queries on:
    - color (FK)
    - unit (FK)
    - business (FK)
    - product_category (FK)

    Expected query reduction: 50-70% (5 queries → 1 query per product)
    """
    business = get_cached_business(request)
    if not business:
        logger.warning(f"User {request.user.id} has no associated business")
        messages.error(request, "No business associated with your account")
        return redirect('business_dashboard')
    logger.info(f"User {request.user.id} accessing product list for business {business.business_id}")

    # N+1 FIX: Optimize queries with select_related for all ForeignKeys
    products = product_models.Product.objects.filter(
        business=business
    ).select_related(
        'color',             # FK: Product → ColorVariant
        'unit',              # FK: Product → UnitVariant
        'business',          # FK: Product → Business
        'product_category',  # FK: Product → ProductCategory
    ).annotate(
        qty=Sum('product_inventory__item_quantity')
    ).order_by('-created_at')

    logger.debug(f"Fetching {products.count()} products for business {business.business_id}")

    data = {
        'products': products,
        'business': business
    }
    return render(request, 'product/product_all_list.html', data)


# -----------------------------------------------------------------------------
# product_all_list_card: Display all products as cards (card view layout).
# Uses select_related to prevent N+1 queries.
# Template: product/product_all_list_card.html
# -----------------------------------------------------------------------------
@login_required(login_url='account_login')
def product_all_list_card(request):
    business = get_cached_business(request)
    if not business:
        logger.warning(f"User {request.user.id} has no associated business")
        messages.error(request, "No business associated with your account")
        return redirect('business_dashboard')
    logger.info(f"User {request.user.id} accessing product card list for business {business.business_id}")

    # N+1 FIX: Optimize queries with select_related
    products = product_models.Product.objects.filter(
        business=business
    ).select_related(
        'color',
        'unit',
        'business',
        'product_category',
    ).order_by('-created_at')

    logger.debug(f"Fetching {products.count()} products as cards for business {business.business_id}")

    data = {
        'products': products,
        'business': business
    }
    return render(request, 'product/product_all_list_card.html', data)


# -----------------------------------------------------------------------------
# product_single_add: Add new product to business catalog.
# Sets business FK automatically from logged-in user.
# Template: product/product_single_add.html
# Form: AddItemsForm
# -----------------------------------------------------------------------------
@login_required(login_url='account_login')
def product_single_add(request):
    business = get_cached_business(request)
    if not business:
        logger.warning(f"User {request.user.id} has no associated business")
        messages.error(request, "No business associated with your account")
        return redirect('business_dashboard')
    logger.info(f"User {request.user.id} accessing product add page for business {business.business_id}")

    if request.method == 'POST':
        form = product_forms.AddItemsForm(request.POST, request.FILES)
        if form.is_valid():
            logger.info(f"Valid product form submitted by user {request.user.id}")
            product = form.save(commit=False)
            product.business = business
            product.save()
            logger.info(f"Product {product.id} created for business {business.business_id}")
            messages.success(request, 'Product added successfully!')
            return redirect('/product/all/')
        else:
            logger.warning(f"Invalid product form submitted by user {request.user.id}: {form.errors}")
            messages.error(request, 'Error adding product. Please check the form.')
    else:
        form = product_forms.AddItemsForm()

    data = {
        'form': form,
        'business': business
    }
    return render(request, 'product/product_single_add.html', data)


# -----------------------------------------------------------------------------
# product_single_delete: Delete product from business catalog.
# SECURITY: Verifies product belongs to user's business before deleting.
# Template: product/product_single_delete.html
# -----------------------------------------------------------------------------
@login_required(login_url='account_login')
def product_single_delete(request, product_id):
    # SECURITY FIX: Verify product belongs to user's business
    business = get_cached_business(request)
    if not business:
        logger.warning(f"User {request.user.id} has no associated business")
        messages.error(request, "No business associated with your account")
        return redirect('business_dashboard')

    try:
        product = product_models.Product.objects.get(id=product_id, business=business)

        logger.info(f"User {request.user.id} deleting product {product_id} from business {business.business_id}")
        product.delete()
        logger.info(f"Product {product_id} deleted successfully")
        messages.success(request, 'Product deleted successfully!')
    except product_models.Product.DoesNotExist:
        logger.warning(f"User {request.user.id} attempted to delete non-existent or unauthorized product {product_id}")
        messages.error(request, "Product not found or unauthorized")

    data = {}
    return render(request, 'product/product_single_delete.html', data)


# -----------------------------------------------------------------------------
# product_single_update: Update existing product details.
# SECURITY: Verifies product belongs to user's business.
# OPTIMIZATION: Uses select_related to fetch related data.
# Template: product/product_single_update.html
# Form: AddItemsForm (with instance)
# -----------------------------------------------------------------------------
@login_required(login_url='account_login')
def product_single_update(request, product_id):
    business = get_cached_business(request)
    if not business:
        logger.warning(f"User {request.user.id} has no associated business")
        messages.error(request, "No business associated with your account")
        return redirect('business_dashboard')

    try:
        # OPTIMIZATION: Use select_related to fetch related data in single query
        # SECURITY FIX: Verify product belongs to user's business
        product = product_models.Product.objects.select_related(
            'color', 'unit', 'business', 'product_category'
        ).get(id=product_id, business=business)

        logger.info(f"User {request.user.id} updating product {product_id}")
    except product_models.Product.DoesNotExist:
        logger.warning(f"User {request.user.id} attempted to update non-existent or unauthorized product {product_id}")
        messages.error(request, "Product not found or unauthorized")
        return redirect('/product/all/')

    if request.method == 'POST':
        form = product_forms.AddItemsForm(request.POST, request.FILES, instance=product)
        if form.is_valid():
            form.save()
            logger.info(f"Product {product_id} updated successfully by user {request.user.id}")
            messages.success(request, 'Your product details have been updated!')
            return redirect('/product/all/')
        else:
            logger.warning(f"Invalid update form for product {product_id}: {form.errors}")
            messages.error(request, 'Error updating product. Please check the form.')
    else:
        form = product_forms.AddItemsForm(instance=product)

    data = {
        'business': business,
        'form': form,
        'product': product,
    }
    return render(request, 'product/product_single_update.html', data)


# -----------------------------------------------------------------------------
# product_inventory: Display product inventory management page.
# Template: product/product_inventory.html
# -----------------------------------------------------------------------------
@login_required(login_url='account_login')
def product_inventory(request):
    business = get_cached_business(request)
    if not business:
        logger.warning(f"User {request.user.id} has no associated business")
        messages.error(request, "No business associated with your account")
        return redirect('business_dashboard')
    logger.info(f"User {request.user.id} accessing inventory for business {business.business_id}")

    # Check if fulfillment service is enabled
    has_fulfillment_service = business.fulfillment_service_enabled

    data = {
        'business': business,
        'has_fulfillment_service': has_fulfillment_service,
    }
    return render(request, 'product/product_inventory.html', data)



# -----------------------------------------------------------------------------
# product_categories: Display product categories page.
# PUBLIC: Does not require authentication.
# Template: product/product_categories.html
# -----------------------------------------------------------------------------
def product_categories(request):
    data = {

    }
    return render(request, 'product/product_categories.html', data)


# -----------------------------------------------------------------------------
# test_images: Diagnostic page to test image rendering
# PUBLIC: For troubleshooting only
# Template: product/test_images.html
# -----------------------------------------------------------------------------
def test_images(request):
    business = get_cached_business(request)
    if not business:
        products = []
    else:
        products = product_models.Product.objects.filter(
            business=business
        ).select_related('business')[:10]

    data = {
        'products': products
    }
    return render(request, 'product/test_images.html', data)


# =============================================================================
# PRODUCT TABLE VIEW WITH INLINE EDITING
# =============================================================================


# -----------------------------------------------------------------------------
# product_all_list_table: Display all products in editable table format.
# Template: product/product_all_list_table.html
# -----------------------------------------------------------------------------
@login_required(login_url='account_login')
def product_all_list_table(request):
    """Display all products in an editable table format."""
    business = get_cached_business(request)
    if not business:
        logger.warning(f"User {request.user.id} has no associated business")
        messages.error(request, "No business associated with your account")
        return redirect('business_dashboard')
    logger.info(f"User {request.user.id} accessing product table for business {business.business_id}")

    products = product_models.Product.objects.filter(
        business=business
    ).select_related(
        'color',
        'unit',
        'business',
        'product_category',
    ).order_by('-created_at')

    # Get dropdown options for inline editing
    categories = product_models.ProductCategory.objects.all()
    colors = product_models.ColorVariant.objects.all()
    units = product_models.UnitVariant.objects.all()

    data = {
        'products': products,
        'business': business,
        'categories': categories,
        'colors': colors,
        'units': units,
    }
    return render(request, 'product/product_all_list_table.html', data)


# -----------------------------------------------------------------------------
# product_inline_update: API endpoint for inline cell editing.
# Accepts JSON payload with field and value to update.
# SECURITY: Verifies product belongs to user's business.
# -----------------------------------------------------------------------------
@login_required(login_url='account_login')
@require_http_methods(["POST"])
def product_inline_update(request, product_id):
    """
    API endpoint for inline product updates.

    Expects JSON payload:
    {
        "field": "item_name|item_sku|item_price|...",
        "value": "new value"
    }

    Returns JSON:
    {
        "success": true/false,
        "message": "...",
        "value": "formatted value for display"
    }
    """
    business = get_cached_business(request)
    if not business:
        return JsonResponse({
            'success': False,
            'message': 'No business associated with your account'
        }, status=403)

    try:
        product = product_models.Product.objects.get(id=product_id, business=business)
    except product_models.Product.DoesNotExist:
        return JsonResponse({
            'success': False,
            'message': 'Product not found or unauthorized'
        }, status=404)

    try:
        data = json.loads(request.body)
        field = data.get('field')
        value = data.get('value')
    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'message': 'Invalid JSON data'
        }, status=400)

    # Define allowed fields for inline editing
    allowed_fields = [
        'item_name', 'brand_name', 'item_sku', 'barcode',
        'item_price', 'size', 'item_discription',
        'color', 'unit', 'product_category'
    ]

    if field not in allowed_fields:
        return JsonResponse({
            'success': False,
            'message': f'Field "{field}" is not editable'
        }, status=400)

    try:
        # Handle FK fields
        if field == 'color':
            if value:
                product.color = product_models.ColorVariant.objects.get(id=value)
            else:
                product.color = None
            display_value = product.color.color_variant if product.color else '-'
        elif field == 'unit':
            if value:
                product.unit = product_models.UnitVariant.objects.get(id=value)
            else:
                product.unit = None
            display_value = product.unit.unit_variant if product.unit else '-'
        elif field == 'product_category':
            if value:
                product.product_category = product_models.ProductCategory.objects.get(id=value)
            else:
                product.product_category = None
            display_value = product.product_category.category_name if product.product_category else '-'
        elif field == 'item_price':
            product.item_price = int(value) if value else 0
            display_value = f'QAR {product.item_price}'
        else:
            setattr(product, field, value)
            display_value = value or '-'

        product.save()
        logger.info(f"Product {product_id} field '{field}' updated to '{value}' by user {request.user.id}")

        return JsonResponse({
            'success': True,
            'message': 'Product updated successfully',
            'value': display_value
        })

    except (product_models.ColorVariant.DoesNotExist,
            product_models.UnitVariant.DoesNotExist,
            product_models.ProductCategory.DoesNotExist) as e:
        return JsonResponse({
            'success': False,
            'message': 'Invalid selection'
        }, status=400)
    except Exception as e:
        logger.error(f"Error updating product {product_id}: {str(e)}")
        return JsonResponse({
            'success': False,
            'message': 'Error updating product'
        }, status=500)


# =============================================================================
# INVENTORY MANAGEMENT (Moved from warehouse app)
# =============================================================================


def get_user_business(request):
    """Helper to get business for current user - uses cached version"""
    return get_cached_business(request)


def is_staff_user(request):
    """Check if user is a staff member (can access all warehouses)"""
    return request.user.is_staff or request.user.is_superuser


def get_business_filter(request):
    """
    Get business filter for queries.
    Staff users see all data, regular users see only their business data.
    Returns (business_obj_or_none, is_staff_bool)
    """
    if is_staff_user(request):
        return None, True
    business = get_user_business(request)
    return business, False


@login_required(login_url='account_login')
def inventory_list(request):
    """List all inventory items with detailed product information"""
    try:
        business, is_staff = get_business_filter(request)
    except Exception as e:
        logger.error(f"Error in get_business_filter: {e}", exc_info=True)
        messages.error(request, "An error occurred. Please try again.")
        return redirect('workforce:wf_dashboard')

    if not is_staff and not business:
        messages.error(request, "No business associated with your account")
        return redirect('business:business_dashboard')

    # Filters
    warehouse_id = request.GET.get('warehouse')
    search = request.GET.get('search', '')
    low_stock_only = request.GET.get('low_stock') == '1'
    category_id = request.GET.get('category')

    try:
        if is_staff:
            stock_levels = warehouse_models.StockLevel.objects.all()
            warehouses = warehouse_models.Warehouse.objects.filter(is_active=True)
        else:
            # Get warehouses linked to this business
            linked_warehouse_ids = warehouse_models.SellerWarehouseLink.objects.filter(
                business=business, is_active=True
            ).values_list('warehouse_id', flat=True)
            stock_levels = warehouse_models.StockLevel.objects.filter(warehouse_id__in=linked_warehouse_ids)
            warehouses = warehouse_models.Warehouse.objects.filter(id__in=linked_warehouse_ids, is_active=True)

        # Select related to avoid N+1 queries for product details
        stock_levels = stock_levels.select_related(
            'product',
            'product__business',
            'product__product_category',
            'product__color',
            'product__unit',
            'warehouse',
            'location'
        ).order_by('product__item_name')
    except Exception as e:
        logger.error(f"Error setting up initial queries in inventory_list: {e}", exc_info=True)
        messages.error(request, "An error occurred while loading inventory data.")
        return redirect('workforce:wf_dashboard')

    if warehouse_id:
        stock_levels = stock_levels.filter(warehouse_id=warehouse_id)

    if search:
        stock_levels = stock_levels.filter(
            Q(product__item_name__icontains=search) |
            Q(product__item_sku__icontains=search) |
            Q(product__brand_name__icontains=search) |
            Q(product__product_id__icontains=search) |
            Q(product__barcode__icontains=search)
        )

    if category_id:
        stock_levels = stock_levels.filter(product__product_category_id=category_id)

    if low_stock_only:
        stock_levels = stock_levels.filter(
            quantity_on_hand__lte=F('reorder_point') + F('quantity_reserved')
        )

    # Get categories for filter (from products in stock)
    try:
        category_ids = stock_levels.values_list('product__product_category_id', flat=True).distinct()
        categories = product_models.ProductCategory.objects.filter(
            id__in=[cat_id for cat_id in category_ids if cat_id is not None]
        ).order_by('name')
    except Exception as e:
        logger.error(f"Error fetching categories: {e}")
        categories = product_models.ProductCategory.objects.none()

    # Pagination
    paginator = Paginator(stock_levels, 25)
    page = request.GET.get('page', 1)
    items = paginator.get_page(page)

    # Calculate total inventory value
    try:
        total_value = sum(
            (stock.quantity_on_hand or 0) * (stock.product.item_price if stock.product and stock.product.item_price else 0)
            for stock in stock_levels
        )
    except Exception as e:
        logger.error(f"Error calculating total inventory value: {e}")
        total_value = 0

    context = {
        'stock_levels': items,
        'warehouses': warehouses,
        'categories': categories,
        'search': search,
        'selected_warehouse': warehouse_id,
        'selected_category': category_id,
        'low_stock_only': low_stock_only,
        'total_value': total_value,
        'is_staff': is_staff,
    }
    return render(request, 'product/inventory_list.html', context)


@login_required(login_url='account_login')
def stock_card(request, product_id):
    """Stock card - detailed view for a single product"""
    business, is_staff = get_business_filter(request)

    if is_staff:
        product = get_object_or_404(product_models.Product, pk=product_id)
        stock_levels = warehouse_models.StockLevel.objects.filter(product=product)
        transactions = warehouse_models.InventoryTransaction.objects.filter(product=product)
    else:
        if not business:
            messages.error(request, "No business associated with your account")
            return redirect('business:business_dashboard')
        product = get_object_or_404(product_models.Product, pk=product_id, business=business)
        # Get warehouses linked to this business
        linked_warehouse_ids = warehouse_models.SellerWarehouseLink.objects.filter(
            business=business, is_active=True
        ).values_list('warehouse_id', flat=True)
        stock_levels = warehouse_models.StockLevel.objects.filter(
            product=product, warehouse_id__in=linked_warehouse_ids
        )
        transactions = warehouse_models.InventoryTransaction.objects.filter(
            product=product, warehouse_id__in=linked_warehouse_ids
        )

    stock_levels = stock_levels.select_related('warehouse', 'location')
    transactions = transactions.select_related('warehouse', 'location', 'created_by').order_by('-created_at')[:50]

    context = {
        'product': product,
        'stock_levels': stock_levels,
        'transactions': transactions,
        'is_staff': is_staff,
    }
    return render(request, 'product/stock_card.html', context)


@login_required(login_url='account_login')
def transaction_list(request):
    """List all inventory transactions"""
    business, is_staff = get_business_filter(request)

    if not is_staff and not business:
        messages.error(request, "No business associated with your account")
        return redirect('business:business_dashboard')

    if is_staff:
        transactions = warehouse_models.InventoryTransaction.objects.all()
        warehouses = warehouse_models.Warehouse.objects.filter(is_active=True)
    else:
        # Get warehouses linked to this business
        linked_warehouse_ids = warehouse_models.SellerWarehouseLink.objects.filter(
            business=business, is_active=True
        ).values_list('warehouse_id', flat=True)
        transactions = warehouse_models.InventoryTransaction.objects.filter(warehouse_id__in=linked_warehouse_ids)
        warehouses = warehouse_models.Warehouse.objects.filter(id__in=linked_warehouse_ids, is_active=True)

    transactions = transactions.select_related('product', 'warehouse', 'location', 'created_by').order_by('-created_at')

    # Filters
    transaction_type = request.GET.get('type')
    warehouse_id = request.GET.get('warehouse')

    if transaction_type:
        transactions = transactions.filter(transaction_type=transaction_type)
    if warehouse_id:
        transactions = transactions.filter(warehouse_id=warehouse_id)

    # Pagination
    paginator = Paginator(transactions, 50)
    page = request.GET.get('page', 1)
    items = paginator.get_page(page)

    # Get transaction type choices from warehouse models
    try:
        transaction_types = warehouse_models.TRANSACTION_TYPE_CHOICES
    except AttributeError:
        transaction_types = []

    context = {
        'transactions': items,
        'warehouses': warehouses,
        'transaction_types': transaction_types,
        'selected_type': transaction_type,
        'selected_warehouse': warehouse_id,
        'is_staff': is_staff,
    }
    return render(request, 'product/transaction_list.html', context)