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
from django.shortcuts import redirect, render
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods


from product import models as product_models
from business import models as business_models
from product import forms as product_forms

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
    try:
        business = business_models.Business.objects.get(user_id=request.user.id)
        logger.info(f"User {request.user.id} accessing product list for business {business.business_id}")
    except business_models.Business.DoesNotExist:
        logger.warning(f"User {request.user.id} has no associated business")
        messages.error(request, "No business associated with your account")
        return redirect('business_dashboard')

    # N+1 FIX: Optimize queries with select_related for all ForeignKeys
    products = product_models.Product.objects.filter(
        business=business
    ).select_related(
        'color',             # FK: Product → ColorVariant
        'unit',              # FK: Product → UnitVariant
        'business',          # FK: Product → Business
        'product_category',  # FK: Product → ProductCategory
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
    try:
        business = business_models.Business.objects.get(user_id=request.user.id)
        logger.info(f"User {request.user.id} accessing product card list for business {business.business_id}")
    except business_models.Business.DoesNotExist:
        logger.warning(f"User {request.user.id} has no associated business")
        messages.error(request, "No business associated with your account")
        return redirect('business_dashboard')

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
    try:
        business = business_models.Business.objects.get(user_id=request.user.id)
        logger.info(f"User {request.user.id} accessing product add page for business {business.business_id}")
    except business_models.Business.DoesNotExist:
        logger.warning(f"User {request.user.id} has no associated business")
        messages.error(request, "No business associated with your account")
        return redirect('business_dashboard')

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
    try:
        # SECURITY FIX: Verify product belongs to user's business
        business = business_models.Business.objects.get(user_id=request.user.id)
        product = product_models.Product.objects.get(id=product_id, business=business)

        logger.info(f"User {request.user.id} deleting product {product_id} from business {business.business_id}")
        product.delete()
        logger.info(f"Product {product_id} deleted successfully")
        messages.success(request, 'Product deleted successfully!')
    except product_models.Product.DoesNotExist:
        logger.warning(f"User {request.user.id} attempted to delete non-existent or unauthorized product {product_id}")
        messages.error(request, "Product not found or unauthorized")
    except business_models.Business.DoesNotExist:
        logger.warning(f"User {request.user.id} has no associated business")
        messages.error(request, "No business associated with your account")

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
    try:
        business = business_models.Business.objects.get(user_id=request.user.id)

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
    except business_models.Business.DoesNotExist:
        logger.warning(f"User {request.user.id} has no associated business")
        messages.error(request, "No business associated with your account")
        return redirect('business_dashboard')

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
    try:
        business = business_models.Business.objects.get(user_id=request.user.id)
        logger.info(f"User {request.user.id} accessing inventory for business {business.business_id}")
    except business_models.Business.DoesNotExist:
        logger.warning(f"User {request.user.id} has no associated business")
        messages.error(request, "No business associated with your account")
        return redirect('business_dashboard')

    data = {
        'business': business
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
    try:
        business = business_models.Business.objects.get(user_id=request.user.id)
        logger.info(f"User {request.user.id} accessing product table for business {business.business_id}")
    except business_models.Business.DoesNotExist:
        logger.warning(f"User {request.user.id} has no associated business")
        messages.error(request, "No business associated with your account")
        return redirect('business_dashboard')

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
    try:
        business = business_models.Business.objects.get(user_id=request.user.id)
        product = product_models.Product.objects.get(id=product_id, business=business)
    except business_models.Business.DoesNotExist:
        return JsonResponse({
            'success': False,
            'message': 'No business associated with your account'
        }, status=403)
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