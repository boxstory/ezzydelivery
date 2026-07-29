import logging
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Sum, F, Q
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from warehouse import models as warehouse_models
from business import models as business_models
from product import models as product_models
from delivery import models as delivery_models
from core.context_processors import get_cached_business

# Import seller-warehouse link views
from warehouse.views_seller_links import (
    seller_warehouse_links,
    seller_warehouse_link_detail,
    seller_warehouse_link_add,
    seller_warehouse_link_edit,
    seller_warehouse_link_delete
)

# Local aliases for commonly used models
Warehouse = warehouse_models.Warehouse
StorageLocation = warehouse_models.StorageLocation
StockLevel = warehouse_models.StockLevel
InventoryTransaction = warehouse_models.InventoryTransaction
PickList = warehouse_models.PickList
CycleCount = warehouse_models.CycleCount
LowStockAlert = warehouse_models.LowStockAlert
Business = business_models.Business
Product = product_models.Product

logger = logging.getLogger('warehouse')


def get_user_business(request):
    """Helper to get business for current user - uses cached version"""
    return get_cached_business(request)


def _is_superadmin(user):
    """Check Profile.is_superadmin or Django is_superuser."""
    if getattr(user, 'is_superuser', False):
        return True
    profile = getattr(user, 'profile', None)
    return bool(profile and getattr(profile, 'is_superadmin', False))


def _is_staff(user):
    """Check Profile.is_staff or Django is_staff."""
    if getattr(user, 'is_staff', False):
        return True
    profile = getattr(user, 'profile', None)
    return bool(profile and getattr(profile, 'is_staff', False))


def is_staff_user(request):
    """Check if user is a staff member (can access all warehouses)"""
    return _is_staff(request.user) or _is_superadmin(request.user)


def is_superuser_only(user):
    """Check if user is superadmin (required for warehouse setup/config)"""
    return _is_superadmin(user)


def has_warehouse_access(user):
    """
    Check if user can access the warehouse section.
    Allowed: superadmins, staff, or users whose business has an active SellerWarehouseLink.
    """
    if not user.is_authenticated:
        return False
    if _is_staff(user) or _is_superadmin(user):
        return True
    # Check if user's business is linked to any warehouse
    business = get_cached_business_for_user(user)
    if business:
        return warehouse_models.SellerWarehouseLink.objects.filter(
            business=business, is_active=True
        ).exists()
    return False


def get_cached_business_for_user(user):
    """Get business for a user object (not request) — for use in decorators."""
    try:
        from business.models import BusinessTeam
        team = BusinessTeam.objects.select_related('business').filter(
            user=user, status='active'
        ).first()
        return team.business if team else None
    except Exception:
        return None


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


def wh_per_page(request, default=25):
    """Validated ?per_page= for warehouse list pagination (10/25/50/100)."""
    try:
        pp = int(request.GET.get('per_page', default))
    except (ValueError, TypeError):
        return default
    return pp if pp in (10, 25, 50, 100) else default


# =============================================================================
# DASHBOARD
# =============================================================================

@login_required(login_url='account_login')
@user_passes_test(has_warehouse_access, login_url='account_login')
def dashboard(request):
    """Warehouse dashboard with live summary stats"""
    business, is_staff = get_business_filter(request)

    # Staff users see all warehouses, regular users see only linked warehouses
    if is_staff:
        warehouses = warehouse_models.Warehouse.objects.filter(is_active=True)
        stock_filter = {}
        alert_filter = {'status': 'active'}
        pick_filter = {'status__in': ['pending', 'assigned', 'in_progress']}
        count_filter = {'status__in': ['scheduled', 'in_progress']}
        txn_filter = {}
        link_filter = {}
        location_filter = {}
    else:
        if not business:
            messages.error(request, "No business associated with your account")
            return redirect('business:business_dashboard')
        linked_warehouse_ids = warehouse_models.SellerWarehouseLink.objects.filter(
            business=business, is_active=True
        ).values_list('warehouse_id', flat=True)
        warehouses = warehouse_models.Warehouse.objects.filter(
            id__in=linked_warehouse_ids, is_active=True
        )
        stock_filter = {'warehouse_id__in': linked_warehouse_ids}
        alert_filter = {'warehouse_id__in': linked_warehouse_ids, 'status': 'active'}
        pick_filter = {'warehouse_id__in': linked_warehouse_ids, 'status__in': ['pending', 'assigned', 'in_progress']}
        count_filter = {'warehouse_id__in': linked_warehouse_ids, 'status__in': ['scheduled', 'in_progress']}
        txn_filter = {'warehouse_id__in': linked_warehouse_ids}
        link_filter = {'warehouse_id__in': linked_warehouse_ids}
        location_filter = {'warehouse_id__in': linked_warehouse_ids}

    # Summary stats
    total_stock = warehouse_models.StockLevel.objects.filter(
        **stock_filter
    ).aggregate(
        total_on_hand=Sum('quantity_on_hand'),
        total_reserved=Sum('quantity_reserved'),
        total_incoming=Sum('quantity_incoming'),
    )

    low_stock_count = warehouse_models.LowStockAlert.objects.filter(
        **alert_filter
    ).count()

    pending_picks = warehouse_models.PickList.objects.filter(
        **pick_filter
    ).count()

    pending_counts = warehouse_models.CycleCount.objects.filter(
        **count_filter
    ).count()

    # Pickup tasks — orders ready for warehouse pickup
    pickup_task_filter = {
        'dl_task_status__in': ['pending', 'assigned', 'accepted'],
    }
    if not is_staff and business:
        pickup_task_filter['business'] = business
    pending_pickup_tasks = delivery_models.DeliveryTask.objects.filter(
        **pickup_task_filter
    ).count()

    # Recent transactions
    recent_transactions = warehouse_models.InventoryTransaction.objects.filter(
        **txn_filter
    ).select_related('product', 'warehouse').order_by('-created_at')[:10]

    # Storage locations (zones) with stock counts
    storage_locations = warehouse_models.StorageLocation.objects.filter(
        location_type='zone', is_active=True, **location_filter
    ).select_related('warehouse').order_by('warehouse__code', 'code')

    # Annotate zones with usage info
    for loc in storage_locations:
        total_bins = warehouse_models.StorageLocation.objects.filter(
            warehouse=loc.warehouse, code__startswith=loc.code, location_type='bin'
        ).count()
        occupied_bins = warehouse_models.StockLevel.objects.filter(
            location__warehouse=loc.warehouse,
            location__code__startswith=loc.code,
            quantity_on_hand__gt=0
        ).values('location').distinct().count()
        loc.total_bins = total_bins
        loc.occupied_bins = occupied_bins
        loc.usage_percent = int((occupied_bins / total_bins * 100) if total_bins > 0 else 0)

    # Seller-warehouse links
    seller_links = warehouse_models.SellerWarehouseLink.objects.filter(
        **link_filter
    ).select_related('business', 'warehouse').order_by('-is_default', '-is_active')

    total_links = seller_links.count()
    active_links = seller_links.filter(is_active=True).count()

    # Warehouse capacity summary
    total_zones = sum(w.total_zones for w in warehouses)
    total_capacity = sum(
        w.total_zones * w.racks_per_zone * w.shelves_per_rack * w.bins_per_shelf
        for w in warehouses
    )

    # All storage location counts by type
    loc_counts = {}
    for lt in ['zone', 'rack', 'shelf', 'bin']:
        loc_counts[lt] = warehouse_models.StorageLocation.objects.filter(
            location_type=lt, is_active=True, **location_filter
        ).count()

    context = {
        'warehouses': warehouses,
        'total_on_hand': total_stock['total_on_hand'] or 0,
        'total_reserved': total_stock['total_reserved'] or 0,
        'total_incoming': total_stock['total_incoming'] or 0,
        'low_stock_count': low_stock_count,
        'pending_picks': pending_picks,
        'pending_counts': pending_counts,
        'pending_pickup_tasks': pending_pickup_tasks,
        'recent_transactions': recent_transactions,
        'storage_locations': storage_locations,
        'seller_links': seller_links,
        'total_links': total_links,
        'active_links': active_links,
        'total_zones': total_zones,
        'total_capacity': total_capacity,
        'loc_counts': loc_counts,
        'current_date': timezone.now(),
        'is_staff': is_staff,
    }
    return render(request, 'warehouse/dashboard.html', context)


# =============================================================================
# INVENTORY
# =============================================================================

@login_required(login_url='account_login')
@user_passes_test(has_warehouse_access, login_url='account_login')
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
    business_filter_id = request.GET.get('business') if is_staff else None

    # Sorting
    sort_field = request.GET.get('sort', 'product__item_name')
    sort_dir = request.GET.get('dir', 'asc')
    SORT_FIELDS = {
        'name': 'product__item_name',
        'brand': 'product__brand_name',
        'sku': 'product__item_sku',
        'category': 'product__product_category__category_name',
        'warehouse': 'warehouse__name',
        'location': 'location__code',
        'price': 'product__item_price',
        'on_hand': 'quantity_on_hand',
        'reserved': 'quantity_reserved',
    }
    orm_sort = SORT_FIELDS.get(sort_field, 'product__item_name')
    if sort_dir == 'desc':
        orm_sort = f'-{orm_sort}'

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
        ).order_by(orm_sort)
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

    if is_staff and business_filter_id:
        stock_levels = stock_levels.filter(product__business_id=business_filter_id)

    if low_stock_only:
        stock_levels = stock_levels.filter(
            quantity_on_hand__lte=F('reorder_point') + F('quantity_reserved')
        )

    # Get categories for filter (from products in stock)
    try:
        category_ids = stock_levels.values_list('product__product_category_id', flat=True).distinct()
        categories = product_models.ProductCategory.objects.filter(
            id__in=[cat_id for cat_id in category_ids if cat_id is not None]
        ).order_by('category_name')
    except Exception as e:
        logger.error(f"Error fetching categories: {e}")
        categories = product_models.ProductCategory.objects.none()

    # Get businesses for filter (staff only — from products in stock)
    businesses = []
    if is_staff:
        try:
            from business.models import Business as BusinessModel
            biz_ids = stock_levels.values_list('product__business_id', flat=True).distinct()
            businesses = BusinessModel.objects.filter(
                business_id__in=[b for b in biz_ids if b is not None]
            ).order_by('business_name')
        except Exception as e:
            logger.error(f"Error fetching businesses for inventory filter: {e}")

    # Pagination
    paginator = Paginator(stock_levels, wh_per_page(request, 25))
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
        'per_page': str(wh_per_page(request, 25)),
        'warehouses': warehouses,
        'categories': categories,
        'businesses': businesses,
        'search': search,
        'selected_warehouse': warehouse_id,
        'selected_category': category_id,
        'selected_business': business_filter_id,
        'low_stock_only': low_stock_only,
        'total_value': total_value,
        'is_staff': is_staff,
        'sort_field': sort_field,
        'sort_dir': sort_dir,
    }
    return render(request, 'warehouse/inventory_list.html', context)


@login_required(login_url='account_login')
@user_passes_test(has_warehouse_access, login_url='account_login')
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
    return render(request, 'warehouse/stock_card.html', context)


@login_required(login_url='account_login')
@user_passes_test(has_warehouse_access, login_url='account_login')
def staff_product_edit(request, product_id):
    """Staff-only product edit page reachable from the warehouse inventory.

    Unlike `product:product_single_update`, this view is not scoped to the
    requesting user's business — staff/warehouse users can edit any
    product. Non-staff with warehouse access can only edit products
    belonging to a business linked to one of their warehouses.
    """
    from product import forms as product_forms

    business, is_staff = get_business_filter(request)

    if is_staff:
        product = get_object_or_404(
            product_models.Product.objects.select_related(
                'color', 'unit', 'business', 'product_category'
            ),
            pk=product_id,
        )
    else:
        if not business:
            messages.error(request, "No business associated with your account")
            return redirect('warehouse:inventory_list')
        # Non-staff with warehouse access: allow editing products from any
        # business linked to a warehouse they're connected to (so a 3PL ops
        # user can edit on behalf of their seller clients).
        linked_warehouse_ids = warehouse_models.SellerWarehouseLink.objects.filter(
            business=business, is_active=True
        ).values_list('warehouse_id', flat=True)
        allowed_business_ids = set(
            warehouse_models.SellerWarehouseLink.objects.filter(
                warehouse_id__in=linked_warehouse_ids, is_active=True
            ).values_list('business_id', flat=True)
        )
        allowed_business_ids.add(business.pk)
        product = get_object_or_404(
            product_models.Product.objects.select_related(
                'color', 'unit', 'business', 'product_category'
            ),
            pk=product_id,
            business_id__in=allowed_business_ids,
        )

    if request.method == 'POST':
        form = product_forms.AddItemsForm(request.POST, request.FILES, instance=product)
        if form.is_valid():
            form.save()
            messages.success(
                request,
                f"Product '{product.item_name}' updated."
            )
            next_url = request.POST.get('next') or request.GET.get('next')
            if next_url:
                return redirect(next_url)
            return redirect('warehouse:inventory_list')
        messages.error(request, "Please correct the errors below.")
    else:
        form = product_forms.AddItemsForm(instance=product)

    context = {
        'form': form,
        'product': product,
        'is_staff': is_staff,
        'next_url': request.GET.get('next', ''),
    }
    return render(request, 'warehouse/staff_product_edit.html', context)


@login_required(login_url='account_login')
@user_passes_test(has_warehouse_access, login_url='account_login')
def stock_level_detail_modal(request, stock_id):
    """Return partial HTML for the inventory detail modal — full product +
    stock info + recent transactions for one StockLevel row.
    """
    business, is_staff = get_business_filter(request)

    qs = warehouse_models.StockLevel.objects.select_related(
        'product', 'product__business', 'product__product_category',
        'product__color', 'product__unit', 'warehouse', 'location',
    )
    if not is_staff:
        if not business:
            return render(request, 'warehouse/parts/inventory_detail_modal.html', {
                'error': 'No business associated with your account',
            }, status=403)
        linked_warehouse_ids = warehouse_models.SellerWarehouseLink.objects.filter(
            business=business, is_active=True
        ).values_list('warehouse_id', flat=True)
        qs = qs.filter(warehouse_id__in=linked_warehouse_ids, product__business=business)

    stock = get_object_or_404(qs, pk=stock_id)

    context = {
        'stock': stock,
        'product': stock.product,
        'is_staff': is_staff,
    }
    return render(request, 'warehouse/parts/inventory_detail_modal.html', context)


@login_required(login_url='account_login')
@user_passes_test(has_warehouse_access, login_url='account_login')
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

    transactions = transactions.select_related('product', 'warehouse', 'location').order_by('-created_at')

    # Filters
    transaction_type = request.GET.get('type')
    warehouse_id = request.GET.get('warehouse')

    if transaction_type:
        transactions = transactions.filter(transaction_type=transaction_type)
    if warehouse_id:
        transactions = transactions.filter(warehouse_id=warehouse_id)

    # Pagination
    paginator = Paginator(transactions, wh_per_page(request, 50))
    page = request.GET.get('page', 1)
    items = paginator.get_page(page)

    context = {
        'transactions': items,
        'per_page': str(wh_per_page(request, 50)),
        'warehouses': warehouses,
        'transaction_types': warehouse_models.TRANSACTION_TYPE_CHOICES,
        'selected_type': transaction_type,
        'selected_warehouse': warehouse_id,
        'is_staff': is_staff,
    }
    return render(request, 'warehouse/transaction_list.html', context)


# =============================================================================
# RECEIVING
# =============================================================================

@login_required(login_url='account_login')
@user_passes_test(has_warehouse_access, login_url='account_login')
def receive_stock(request):
    """Receive new stock into warehouse — from inbound request or manual entry"""
    business, is_staff = get_business_filter(request)

    if not is_staff and not business:
        messages.error(request, "No business associated with your account")
        return redirect('business:business_dashboard')

    if request.method == 'POST':
        warehouse_id = request.POST.get('warehouse')
        location_id = request.POST.get('location')
        reference = request.POST.get('reference', '')
        notes = request.POST.get('notes', '')
        receive_date = request.POST.get('receive_date', '')
        inbound_request_id = request.POST.get('inbound_request_id', '')

        product_ids = request.POST.getlist('products[]')
        quantities = request.POST.getlist('quantities[]')

        try:
            # Validate warehouse access
            if is_staff:
                warehouse = warehouse_models.Warehouse.objects.get(pk=warehouse_id)
            else:
                if not warehouse_models.SellerWarehouseLink.objects.filter(
                    business=business, warehouse_id=warehouse_id, is_active=True
                ).exists():
                    raise ValueError("Warehouse is not linked to your business")
                warehouse = warehouse_models.Warehouse.objects.get(pk=warehouse_id)

            # Get storage location (optional)
            location = None
            if location_id:
                location = warehouse_models.StorageLocation.objects.get(
                    pk=location_id, warehouse=warehouse
                )

            # If receiving from inbound request, load it
            inbound_req = None
            if inbound_request_id:
                inbound_req = warehouse_models.InboundProductRequest.objects.get(
                    pk=inbound_request_id, status__in=['pending', 'approved']
                )

            # Build reference note for inbound request
            if inbound_req and not reference:
                reference = inbound_req.request_number

            # Process each product
            received_products = []
            put_away_items = []  # for auto-creating put-away task
            total_items = 0
            fulfilled_items = {}  # product_id → qty for updating request items

            for product_id, quantity_str in zip(product_ids, quantities):
                if not product_id or not quantity_str:
                    continue

                quantity = int(quantity_str)
                if quantity <= 0:
                    continue

                # Get product with business validation
                if is_staff:
                    product = product_models.Product.objects.get(pk=product_id)
                else:
                    product = product_models.Product.objects.get(pk=product_id, business=business)

                # Get or create stock level
                stock_level, created = warehouse_models.StockLevel.objects.get_or_create(
                    product=product,
                    warehouse=warehouse,
                    location=location,
                    defaults={'quantity_on_hand': 0}
                )

                old_quantity = stock_level.quantity_on_hand
                stock_level.quantity_on_hand += quantity
                stock_level.save(update_fields=['quantity_on_hand', 'updated_at'])

                # Build transaction notes
                parts = []
                if receive_date:
                    parts.append(f"Received: {receive_date}")
                if reference:
                    parts.append(f"Ref: {reference}")
                if notes:
                    parts.append(notes)
                transaction_notes = " | ".join(parts)

                # Create transaction record
                warehouse_models.InventoryTransaction.objects.create(
                    product=product,
                    warehouse=warehouse,
                    location=location,
                    transaction_type='receive',
                    quantity=quantity,
                    quantity_before=old_quantity,
                    quantity_after=stock_level.quantity_on_hand,
                    reference_type='inbound_request' if inbound_req else '',
                    reference_id=str(inbound_req.pk) if inbound_req else '',
                    notes=transaction_notes,
                    created_by=request.user
                )

                received_products.append(f"{product.item_name} ({quantity} units)")
                put_away_items.append({'product': product, 'quantity': quantity, 'source_location': location})
                total_items += quantity
                fulfilled_items[int(product_id)] = quantity

            # If from inbound request, update fulfilled quantities
            # Supports partial fulfillment — only mark completed when ALL items fully received
            if inbound_req and received_products:
                for item in inbound_req.items.all():
                    qty = fulfilled_items.get(item.product_id, 0)
                    if qty > 0:
                        item.quantity_fulfilled += qty
                        item.save(update_fields=['quantity_fulfilled', 'updated_at'])

                # Approve if still pending
                if inbound_req.status == 'pending':
                    inbound_req.status = 'approved'
                    inbound_req.approved_by = request.user
                    inbound_req.approved_at = timezone.now()
                    inbound_req.save(update_fields=['status', 'approved_by', 'approved_at', 'updated_at'])

                # Check if all items are fully fulfilled
                all_fulfilled = all(
                    item.is_fully_fulfilled
                    for item in inbound_req.items.all()
                )
                if all_fulfilled:
                    inbound_req.status = 'completed'
                    inbound_req.completed_by = request.user
                    inbound_req.completed_at = timezone.now()
                    inbound_req.save(update_fields=['status', 'completed_by', 'completed_at', 'updated_at'])

            # Auto-create put-away task
            pa_task = None
            if put_away_items:
                pa_task = _create_put_away_task(
                    warehouse=warehouse,
                    products_received=put_away_items,
                    user=request.user,
                    inbound_request=inbound_req,
                )

            # Success message
            if len(received_products) == 1:
                msg = f"Received {received_products[0]}"
            else:
                summary = ", ".join(received_products[:3])
                if len(received_products) > 3:
                    summary += f" and {len(received_products) - 3} more"
                msg = f"Received {len(received_products)} products ({total_items} total items): {summary}"

            if inbound_req:
                inbound_req.refresh_from_db()
                if inbound_req.status == 'completed':
                    msg += f" — Inbound request {inbound_req.request_number} fully completed."
                else:
                    msg += f" — Inbound request {inbound_req.request_number} partially received (still open)."
            if pa_task:
                msg += f" Put-away task {pa_task.task_number} created."
            messages.success(request, msg)

            # Redirect to put-away task if one was created
            if pa_task:
                return redirect('warehouse:put_away_detail', pk=pa_task.pk)
            return redirect('warehouse:inventory_list')

        except Exception as e:
            logger.exception(f"Error receiving stock: {str(e)}")
            messages.error(request, f"Error receiving stock: {str(e)}")

    # GET — build context
    # Pending/approved inbound requests for the top section
    inbound_requests = warehouse_models.InboundProductRequest.objects.filter(
        status__in=['pending', 'approved']
    ).select_related('business', 'warehouse').order_by('-created_at')

    if is_staff:
        warehouses = warehouse_models.Warehouse.objects.filter(is_active=True)
        businesses = business_models.Business.objects.filter(business_status='active').order_by('business_name')
        selected_business_id = request.GET.get('business', '')
        if selected_business_id:
            products = product_models.Product.objects.filter(business_id=selected_business_id)
        else:
            products = product_models.Product.objects.none()
    else:
        linked_warehouse_ids = warehouse_models.SellerWarehouseLink.objects.filter(
            business=business, is_active=True
        ).values_list('warehouse_id', flat=True)
        warehouses = warehouse_models.Warehouse.objects.filter(id__in=linked_warehouse_ids, is_active=True)
        products = product_models.Product.objects.filter(business=business)
        businesses = None
        selected_business_id = ''
        # Non-staff only sees their own inbound requests
        inbound_requests = inbound_requests.filter(business=business)

    context = {
        'warehouses': warehouses,
        'products': products,
        'is_staff': is_staff,
        'businesses': businesses,
        'selected_business_id': selected_business_id,
        'inbound_requests': inbound_requests,
    }
    return render(request, 'warehouse/receive_stock.html', context)


@login_required(login_url='account_login')
@user_passes_test(has_warehouse_access, login_url='account_login')
def confirm_receive(request):
    """AJAX endpoint to confirm receipt"""
    # Placeholder for barcode scanning confirmation
    return JsonResponse({'status': 'ok'})


# =============================================================================
# PICKING
# =============================================================================

@login_required(login_url='account_login')
@user_passes_test(has_warehouse_access, login_url='account_login')
def pick_list_list(request):
    """List all pick lists"""
    business, is_staff = get_business_filter(request)

    if not is_staff and not business:
        messages.error(request, "No business associated with your account")
        return redirect('business:business_dashboard')

    if is_staff:
        pick_lists = warehouse_models.PickList.objects.all()
    else:
        # Get warehouses linked to this business
        linked_warehouse_ids = warehouse_models.SellerWarehouseLink.objects.filter(
            business=business, is_active=True
        ).values_list('warehouse_id', flat=True)
        pick_lists = warehouse_models.PickList.objects.filter(warehouse_id__in=linked_warehouse_ids)

    from django.db.models import Exists, OuterRef
    same_day_subq = Exists(
        warehouse_models.PickListItem.objects.filter(
            pick_list=OuterRef('pk'),
            order__delivery_speed='same_day'
        )
    )
    pick_lists = pick_lists.select_related(
        'warehouse', 'assigned_to', 'business', 'zone'
    ).annotate(has_urgent=same_day_subq).order_by('-has_urgent', '-created_at')

    # Filters
    status = request.GET.get('status')
    if status:
        pick_lists = pick_lists.filter(status=status)

    biz_filter = request.GET.get('business')
    if biz_filter:
        pick_lists = pick_lists.filter(business_id=biz_filter)

    zone_filter = request.GET.get('zone')
    if zone_filter:
        pick_lists = pick_lists.filter(zone_id=zone_filter)

    paginator = Paginator(pick_lists, wh_per_page(request, 25))
    page = request.GET.get('page', 1)
    items = paginator.get_page(page)

    # Choices for filters
    businesses = business_models.Business.objects.filter(
        pick_lists__isnull=False
    ).distinct().order_by('business_name')

    zones = warehouse_models.StorageLocation.objects.filter(
        location_type='zone', pick_lists__isnull=False
    ).distinct().order_by('code')

    context = {
        'pick_lists': items,
        'per_page': str(wh_per_page(request, 25)),
        'status_choices': warehouse_models.PICKLIST_STATUS_CHOICES,
        'selected_status': status,
        'businesses': businesses,
        'selected_business': biz_filter,
        'zones': zones,
        'selected_zone': zone_filter,
        'is_staff': is_staff,
        'is_superadmin': _is_superadmin(request.user),
    }
    return render(request, 'warehouse/pick_list_list.html', context)


@login_required(login_url='account_login')
@user_passes_test(has_warehouse_access, login_url='account_login')
@require_http_methods(["POST"])
def bulk_drop_pick_lists(request):
    """
    Bulk drop items back to shelf — superadmin only.
    Returns all picked items to their shelf locations, resets pick list to pending,
    and clears all pick/pack progress.
    """
    if not _is_superadmin(request.user):
        messages.error(request, "Only superadmins can perform this action.")
        return redirect('warehouse:pick_list_list')

    pk_ids = request.POST.getlist('pk_ids')
    if not pk_ids:
        messages.warning(request, "No pick lists selected.")
        return redirect('warehouse:pick_list_list')

    pick_lists = warehouse_models.PickList.objects.filter(pk__in=pk_ids)
    total_returned = 0

    for pl in pick_lists.prefetch_related('items'):
        items_returned = 0
        for item in pl.items.filter(is_picked=True).select_related('product', 'location'):
            if item.location and item.product:
                stock = warehouse_models.StockLevel.objects.filter(
                    product=item.product,
                    warehouse=pl.warehouse,
                    location=item.location,
                ).first()
                if stock:
                    old_qty = stock.quantity_on_hand
                    stock.quantity_on_hand += item.quantity_to_pick
                    stock.save(update_fields=['quantity_on_hand'])

                    # Log transaction
                    warehouse_models.InventoryTransaction.objects.create(
                        product=item.product,
                        warehouse=pl.warehouse,
                        location=item.location,
                        transaction_type='return',
                        quantity=item.quantity_to_pick,
                        quantity_before=old_qty,
                        quantity_after=stock.quantity_on_hand,
                        reference_type='pick_list',
                        reference_id=pl.pick_number,
                        notes=f"Bulk drop to shelf by {request.user.username}",
                        created_by=request.user,
                    )
                    items_returned += 1

            # Reset item state
            item.is_picked = False
            item.picked_at = None
            item.picked_by = None
            item.quantity_picked = 0
            item.is_packed = False
            item.packed_at = None
            item.save(update_fields=[
                'is_picked', 'picked_at', 'picked_by', 'quantity_picked',
                'is_packed', 'packed_at',
            ])

        # Reset pick list to pending
        pl.status = 'pending'
        pl.picked_items = 0
        pl.assigned_to = None
        pl.assigned_at = None
        pl.started_at = None
        pl.completed_at = None
        pl.save(update_fields=[
            'status', 'picked_items', 'assigned_to', 'assigned_at',
            'started_at', 'completed_at', 'updated_at',
        ])
        total_returned += items_returned

    count = pick_lists.count()
    messages.success(
        request,
        f"Dropped {total_returned} items back to shelf across {count} pick list{'s' if count != 1 else ''}. "
        f"All reset to Pending."
    )
    return redirect('warehouse:pick_list_list')


@login_required(login_url='account_login')
@user_passes_test(has_warehouse_access, login_url='account_login')
def create_pick_list(request):
    """Create a product-grouped pick list from orders ready for pickup."""
    from orders.models import Order, OrderItem
    business, is_staff = get_business_filter(request)

    if request.method == 'POST':
        order_ids = request.POST.getlist('order_ids')
        if not order_ids:
            messages.warning(request, "Select at least one order.")
            return redirect('warehouse:create_pick_list')

        orders = Order.objects.filter(pk__in=order_ids).select_related('business')
        if not orders.exists():
            messages.error(request, "No valid orders selected.")
            return redirect('warehouse:create_pick_list')

        # Group all selected orders into one pick list per warehouse
        from warehouse.signals import create_pick_list_for_order
        pick_list = None
        for order in orders:
            result = create_pick_list_for_order(order)
            if result:
                pick_list = result

        if pick_list:
            messages.success(request, f"Pick list {pick_list.pick_number} created with {pick_list.total_items} items from {orders.count()} orders.")
            return redirect('warehouse:pick_list_detail', pk=pick_list.pk)
        else:
            messages.warning(request, "No items could be added. Orders may already have pick lists or no products.")
            return redirect('warehouse:pick_list_list')

    # GET — show orders ready for picking (have products, no existing pick list)
    if is_staff:
        ready_orders = Order.objects.filter(
            order_status='ready_to_pickup',
        ).exclude(
            pick_list_items__isnull=False,
        ).select_related('business').order_by('-created_at')[:50]
    else:
        if not business:
            messages.error(request, "No business associated with your account")
            return redirect('business:business_dashboard')
        ready_orders = Order.objects.filter(
            business=business,
            order_status='ready_to_pickup',
        ).exclude(
            pick_list_items__isnull=False,
        ).order_by('-created_at')[:50]

    # Annotate with item count
    for o in ready_orders:
        o.product_count = OrderItem.objects.filter(order=o, product__isnull=False).count()

    context = {
        'ready_orders': ready_orders,
        'is_staff': is_staff,
    }
    return render(request, 'warehouse/create_pick_list.html', context)


@login_required(login_url='account_login')
@user_passes_test(has_warehouse_access, login_url='account_login')
def pick_list_detail(request, pk):
    """View pick list details"""
    business, is_staff = get_business_filter(request)

    if is_staff:
        pick_list = get_object_or_404(warehouse_models.PickList, pk=pk)
    else:
        if not business:
            messages.error(request, "No business associated with your account")
            return redirect('business:business_dashboard')
        # Get warehouses linked to this business
        linked_warehouse_ids = warehouse_models.SellerWarehouseLink.objects.filter(
            business=business, is_active=True
        ).values_list('warehouse_id', flat=True)
        pick_list = get_object_or_404(
            warehouse_models.PickList,
            pk=pk,
            warehouse_id__in=linked_warehouse_ids
        )

    items = pick_list.items.select_related(
        'product', 'location', 'order'
    ).order_by('location__code')

    # Product-grouped view: aggregate by product + location
    from collections import OrderedDict
    product_groups = OrderedDict()
    for item in items:
        key = (item.product_id, item.location_id)
        if key not in product_groups:
            product_groups[key] = {
                'product': item.product,
                'location': item.location,
                'total_qty': 0,
                'picked_qty': 0,
                'orders': [],
                'items': [],
                'all_picked': True,
            }
        grp = product_groups[key]
        grp['total_qty'] += item.quantity_to_pick
        grp['picked_qty'] += item.quantity_picked
        if item.order:
            grp['orders'].append(item.order)
        grp['items'].append(item)
        if not item.is_picked:
            grp['all_picked'] = False
    grouped_items = list(product_groups.values())
    # Show the bin/location route column only when at least one product has a bin
    any_location = any(g['location'] for g in grouped_items)

    # Prev/next navigation
    base_qs = warehouse_models.PickList.objects.all()
    if not is_staff:
        base_qs = base_qs.filter(warehouse_id__in=linked_warehouse_ids)
    prev_pl = base_qs.filter(pk__lt=pk).order_by('-pk').values_list('pk', flat=True).first()
    next_pl = base_qs.filter(pk__gt=pk).order_by('pk').values_list('pk', flat=True).first()

    context = {
        'pick_list': pick_list,
        'items': items,
        'grouped_items': grouped_items,
        'any_location': any_location,
        'is_staff': is_staff,
        'prev_pk': prev_pl,
        'next_pk': next_pl,
    }
    return render(request, 'warehouse/pick_list_detail.html', context)


@login_required(login_url='account_login')
@user_passes_test(has_warehouse_access, login_url='account_login')
def assign_pick_list(request, pk):
    """Assign pick list to a user"""
    business, is_staff = get_business_filter(request)

    if is_staff:
        pick_list = get_object_or_404(warehouse_models.PickList, pk=pk)
    else:
        if not business:
            return JsonResponse({'error': 'No business'}, status=400)
        # Get warehouses linked to this business
        linked_warehouse_ids = warehouse_models.SellerWarehouseLink.objects.filter(
            business=business, is_active=True
        ).values_list('warehouse_id', flat=True)
        pick_list = get_object_or_404(
            warehouse_models.PickList,
            pk=pk,
            warehouse_id__in=linked_warehouse_ids
        )

    if request.method == 'POST':
        pick_list.assigned_to = request.user
        pick_list.assigned_at = timezone.now()
        pick_list.status = 'assigned'
        pick_list.save(update_fields=['assigned_to', 'assigned_at', 'status', 'updated_at'])
        messages.success(request, f"Pick list {pick_list.pick_number} assigned to you")

    return redirect('warehouse:pick_list_detail', pk=pk)


@login_required(login_url='account_login')
@user_passes_test(has_warehouse_access, login_url='account_login')
@require_http_methods(["POST"])
def start_pick_list(request, pk):
    """Start picking — changes status to in_progress"""
    pick_list = get_object_or_404(warehouse_models.PickList, pk=pk)

    if pick_list.status not in ('pending', 'assigned'):
        return JsonResponse({'error': 'Pick list cannot be started'}, status=400)

    # Auto-assign if not yet assigned
    if not pick_list.assigned_to:
        pick_list.assigned_to = request.user
        pick_list.assigned_at = timezone.now()

    pick_list.status = 'in_progress'
    pick_list.started_at = timezone.now()
    pick_list.save(update_fields=['status', 'started_at', 'assigned_to', 'assigned_at', 'updated_at'])
    messages.success(request, f"Picking started for {pick_list.pick_number}")
    return redirect('warehouse:pick_list_detail', pk=pk)


@login_required(login_url='account_login')
@user_passes_test(has_warehouse_access, login_url='account_login')
@require_http_methods(["POST"])
def pick_item(request, pk, item_id):
    """AJAX: Mark a single pick list item as picked (or update quantity)"""
    pick_list = get_object_or_404(warehouse_models.PickList, pk=pk)
    item = get_object_or_404(warehouse_models.PickListItem, pk=item_id, pick_list=pick_list)

    qty = request.POST.get('quantity', '')
    if qty and qty.isdigit():
        item.quantity_picked = min(int(qty), item.quantity_to_pick)
    else:
        # Toggle: full pick
        item.quantity_picked = item.quantity_to_pick

    item.is_picked = item.quantity_picked >= item.quantity_to_pick
    item.picked_at = timezone.now()
    item.picked_by = request.user
    item.save(update_fields=['quantity_picked', 'is_picked', 'picked_at', 'picked_by'])

    # Update pick list counters
    all_items = pick_list.items.all()
    pick_list.picked_items = all_items.filter(is_picked=True).count()
    pick_list.save(update_fields=['picked_items', 'updated_at'])

    # Auto-complete if all picked
    if pick_list.picked_items >= pick_list.total_items and pick_list.total_items > 0:
        pick_list.status = 'completed'
        pick_list.completed_at = timezone.now()
        pick_list.save(update_fields=['status', 'completed_at', 'updated_at'])

    return JsonResponse({
        'success': True,
        'item_id': item.id,
        'quantity_picked': item.quantity_picked,
        'quantity_to_pick': item.quantity_to_pick,
        'is_picked': item.is_picked,
        'picked_items': pick_list.picked_items,
        'total_items': pick_list.total_items,
        'progress': pick_list.progress_percentage,
        'pick_list_status': pick_list.status,
    })


@login_required(login_url='account_login')
@user_passes_test(has_warehouse_access, login_url='account_login')
@require_http_methods(["POST"])
def unpick_item(request, pk, item_id):
    """AJAX: Reset a picked item back to pending"""
    pick_list = get_object_or_404(warehouse_models.PickList, pk=pk)
    item = get_object_or_404(warehouse_models.PickListItem, pk=item_id, pick_list=pick_list)

    item.quantity_picked = 0
    item.is_picked = False
    item.picked_at = None
    item.picked_by = None
    item.save(update_fields=['quantity_picked', 'is_picked', 'picked_at', 'picked_by'])

    # Update counters
    pick_list.picked_items = pick_list.items.filter(is_picked=True).count()
    if pick_list.status == 'completed':
        pick_list.status = 'in_progress'
        pick_list.completed_at = None
    pick_list.save(update_fields=['picked_items', 'status', 'completed_at', 'updated_at'])

    return JsonResponse({
        'success': True,
        'item_id': item.id,
        'quantity_to_pick': item.quantity_to_pick,
        'picked_items': pick_list.picked_items,
        'total_items': pick_list.total_items,
        'progress': pick_list.progress_percentage,
        'pick_list_status': pick_list.status,
    })


# =============================================================================
# PACKING STATION
# =============================================================================

@login_required(login_url='account_login')
@user_passes_test(has_warehouse_access, login_url='account_login')
def pack_station(request, pk):
    """
    Pack station view for a completed pick list.
    Shows items grouped by ORDER so the packer can sort picked products
    back into individual orders and mark each order as packed.
    """
    pick_list = get_object_or_404(warehouse_models.PickList, pk=pk)

    # Allow packing from 'completed' (all picked) or 'packing' status
    if pick_list.status == 'completed':
        pick_list.status = 'packing'
        pick_list.save(update_fields=['status', 'updated_at'])

    items = pick_list.items.select_related(
        'product', 'location', 'order', 'order__business'
    ).order_by('order__order_number', 'product__item_name')

    # Group by order
    from collections import OrderedDict
    order_groups = OrderedDict()
    for item in items:
        oid = item.order_id
        if oid not in order_groups:
            order_groups[oid] = {
                'order': item.order,
                'items': [],
                'total_qty': 0,
                'packed_qty': 0,
                'all_packed': True,
            }
        grp = order_groups[oid]
        grp['items'].append(item)
        grp['total_qty'] += item.quantity_to_pick
        if item.is_packed:
            grp['packed_qty'] += item.quantity_to_pick
        else:
            grp['all_packed'] = False

    order_list = list(order_groups.values())
    total_orders = len(order_list)
    packed_orders = sum(1 for g in order_list if g['all_packed'])

    context = {
        'pick_list': pick_list,
        'order_list': order_list,
        'total_orders': total_orders,
        'packed_orders': packed_orders,
    }
    return render(request, 'warehouse/pack_station.html', context)


@login_required(login_url='account_login')
@user_passes_test(has_warehouse_access, login_url='account_login')
@require_http_methods(["POST"])
def pack_order(request, pk, order_id):
    """AJAX: Mark all items in an order as packed (or unpack)."""
    pick_list = get_object_or_404(warehouse_models.PickList, pk=pk)
    items = pick_list.items.filter(order_id=order_id)

    if not items.exists():
        return JsonResponse({'success': False, 'error': 'No items found'}, status=404)

    # Toggle: if all packed -> unpack, else pack all
    all_packed = all(i.is_packed for i in items)
    now = timezone.now()

    for item in items:
        item.is_packed = not all_packed
        item.packed_at = now if not all_packed else None
        item.save(update_fields=['is_packed', 'packed_at'])

    # Check if entire pick list is now packed
    total_items = pick_list.items.count()
    packed_items = pick_list.items.filter(is_packed=True).count()
    all_done = packed_items == total_items

    if all_done and pick_list.status != 'packed':
        pick_list.status = 'packed'
        pick_list.save(update_fields=['status', 'updated_at'])
    elif not all_done and pick_list.status == 'packed':
        pick_list.status = 'packing'
        pick_list.save(update_fields=['status', 'updated_at'])

    # Count packed orders
    order_ids = pick_list.items.values_list('order_id', flat=True).distinct()
    packed_orders = 0
    for oid in order_ids:
        if not pick_list.items.filter(order_id=oid, is_packed=False).exists():
            packed_orders += 1

    return JsonResponse({
        'success': True,
        'order_id': order_id,
        'is_packed': not all_packed,
        'packed_orders': packed_orders,
        'total_orders': order_ids.count(),
        'all_done': all_done,
        'pick_list_status': pick_list.status,
    })


# =============================================================================
# DISPATCH
# =============================================================================

@login_required(login_url='account_login')
@user_passes_test(has_warehouse_access, login_url='account_login')
def dispatch_queue(request):
    """
    Dispatch queue: shows packed orders ready for driver assignment,
    and existing dispatch batches.
    """
    business, is_staff = get_business_filter(request)

    # Packed orders not yet in a dispatch batch
    from orders.models import Order
    packed_order_ids = warehouse_models.PickListItem.objects.filter(
        pick_list__status='packed', is_packed=True
    ).values_list('order_id', flat=True).distinct()

    # Exclude orders already in a dispatch batch
    dispatched_order_ids = warehouse_models.DispatchItem.objects.values_list('order_id', flat=True)
    ready_orders = Order.objects.filter(
        pk__in=packed_order_ids
    ).exclude(
        pk__in=dispatched_order_ids
    ).select_related('business').order_by('-created_at')

    if not is_staff and business:
        ready_orders = ready_orders.filter(business=business)

    # Existing dispatch batches
    if is_staff:
        batches = warehouse_models.DispatchBatch.objects.all()
    else:
        linked_wh_ids = warehouse_models.SellerWarehouseLink.objects.filter(
            business=business, is_active=True
        ).values_list('warehouse_id', flat=True)
        batches = warehouse_models.DispatchBatch.objects.filter(warehouse_id__in=linked_wh_ids)

    batches = batches.select_related('warehouse', 'driver').order_by('-created_at')[:20]

    # Available drivers
    from fleet.models import Driver
    drivers = Driver.objects.filter(
        driver_status='approved', driver_availability='available'
    ).select_related('user')

    context = {
        'ready_orders': ready_orders,
        'batches': batches,
        'drivers': drivers,
        'is_staff': is_staff,
    }
    return render(request, 'warehouse/dispatch_queue.html', context)


@login_required(login_url='account_login')
@user_passes_test(has_warehouse_access, login_url='account_login')
@require_http_methods(["POST"])
def dispatch_create(request):
    """Create a dispatch batch from selected orders + driver."""
    from orders.models import Order

    order_ids = request.POST.getlist('order_ids')
    driver_id = request.POST.get('driver_id')

    if not order_ids:
        messages.warning(request, "Select at least one order.")
        return redirect('warehouse:dispatch_queue')

    orders = Order.objects.filter(pk__in=order_ids).select_related('business')

    # Determine warehouse from first order's pick list
    first_item = warehouse_models.PickListItem.objects.filter(
        order__in=orders
    ).select_related('pick_list__warehouse').first()
    wh = first_item.pick_list.warehouse if first_item else None

    if not wh:
        messages.error(request, "Could not determine warehouse for these orders.")
        return redirect('warehouse:dispatch_queue')

    # Calculate total COD
    total_cod = sum(o.cod_amount or 0 for o in orders)

    # Get driver if assigned
    driver = None
    if driver_id:
        from fleet.models import Driver
        driver = Driver.objects.filter(pk=driver_id).first()

    batch = warehouse_models.DispatchBatch.objects.create(
        warehouse=wh,
        driver=driver,
        status='assigned' if driver else 'ready',
        total_orders=orders.count(),
        total_cod_amount=total_cod,
        assigned_at=timezone.now() if driver else None,
        created_by=request.user,
    )

    for order in orders:
        warehouse_models.DispatchItem.objects.create(
            batch=batch,
            order=order,
            pick_list=warehouse_models.PickListItem.objects.filter(
                order=order
            ).first().pick_list if warehouse_models.PickListItem.objects.filter(order=order).exists() else None,
            cod_amount=order.cod_amount or 0,
        )

    driver_name = driver.user.get_full_name() if driver else 'unassigned'
    messages.success(
        request,
        f"Dispatch batch {batch.batch_number} created with {orders.count()} orders "
        f"({driver_name}). COD: QAR {total_cod:.2f}"
    )
    return redirect('warehouse:dispatch_detail', pk=batch.pk)


@login_required(login_url='account_login')
@user_passes_test(has_warehouse_access, login_url='account_login')
def dispatch_detail(request, pk):
    """Dispatch batch detail — handover orders to driver one by one."""
    batch = get_object_or_404(
        warehouse_models.DispatchBatch.objects.select_related('warehouse', 'driver', 'driver__user'),
        pk=pk
    )
    items = batch.items.select_related('order', 'order__business').order_by('order__order_number')
    total = items.count()
    handed = items.filter(is_handed_over=True).count()

    context = {
        'batch': batch,
        'items': items,
        'total': total,
        'handed': handed,
    }
    return render(request, 'warehouse/dispatch_detail.html', context)


@login_required(login_url='account_login')
@user_passes_test(has_warehouse_access, login_url='account_login')
@require_http_methods(["POST"])
def dispatch_handover_item(request, pk, item_id):
    """AJAX: Mark a single order as handed over to driver."""
    batch = get_object_or_404(warehouse_models.DispatchBatch, pk=pk)
    item = get_object_or_404(warehouse_models.DispatchItem, pk=item_id, batch=batch)

    item.is_handed_over = True
    item.handed_over_at = timezone.now()
    item.save(update_fields=['is_handed_over', 'handed_over_at'])

    total = batch.items.count()
    handed = batch.items.filter(is_handed_over=True).count()
    all_done = handed == total

    if all_done and batch.status != 'handed_over':
        batch.status = 'handed_over'
        batch.handed_over_at = timezone.now()
        batch.save(update_fields=['status', 'handed_over_at', 'updated_at'])

    return JsonResponse({
        'success': True,
        'item_id': item.id,
        'handed': handed,
        'total': total,
        'all_done': all_done,
    })


@login_required(login_url='account_login')
@user_passes_test(has_warehouse_access, login_url='account_login')
@require_http_methods(["POST"])
def dispatch_confirm(request, pk):
    """Confirm dispatch — driver leaves the warehouse."""
    batch = get_object_or_404(warehouse_models.DispatchBatch, pk=pk)

    batch.status = 'dispatched'
    batch.dispatched_at = timezone.now()
    batch.save(update_fields=['status', 'dispatched_at', 'updated_at'])

    messages.success(request, f"Batch {batch.batch_number} dispatched! Driver is on the way.")
    return redirect('warehouse:dispatch_queue')


# =============================================================================
# CUSTOMER RETURNS / RMA
# =============================================================================

@login_required(login_url='account_login')
@user_passes_test(has_warehouse_access, login_url='account_login')
def rma_list(request):
    """List all customer returns."""
    business, is_staff = get_business_filter(request)

    if is_staff:
        returns = warehouse_models.CustomerReturn.objects.all()
    else:
        if not business:
            messages.error(request, "No business associated with your account")
            return redirect('business:business_dashboard')
        returns = warehouse_models.CustomerReturn.objects.filter(business=business)

    status = request.GET.get('status')
    if status:
        returns = returns.filter(status=status)

    returns = returns.select_related('order', 'business', 'warehouse').order_by('-created_at')

    paginator = Paginator(returns, wh_per_page(request, 20))
    returns = paginator.get_page(request.GET.get('page'))

    context = {
        'returns': returns,
        'per_page': str(wh_per_page(request, 20)),
        'status_choices': warehouse_models.RMA_STATUS_CHOICES,
        'selected_status': status,
        'is_staff': is_staff,
    }
    return render(request, 'warehouse/rma_list.html', context)


@login_required(login_url='account_login')
@user_passes_test(has_warehouse_access, login_url='account_login')
def rma_create(request, order_id):
    """Create a return request for an order."""
    from orders.models import Order, OrderItem

    order = get_object_or_404(Order.objects.select_related('business'), pk=order_id)
    order_items = OrderItem.objects.filter(order=order, product__isnull=False).select_related('product')

    if request.method == 'POST':
        reason = request.POST.get('reason', 'other')
        notes = request.POST.get('customer_notes', '')
        item_ids = request.POST.getlist('item_ids')

        if not item_ids:
            messages.warning(request, "Select at least one item to return.")
            return redirect('warehouse:rma_create', order_id=order.pk)

        # Find warehouse
        wh_link = warehouse_models.SellerWarehouseLink.objects.filter(
            business=order.business, is_active=True
        ).select_related('warehouse').first()

        rma = warehouse_models.CustomerReturn.objects.create(
            order=order,
            business=order.business,
            warehouse=wh_link.warehouse if wh_link else None,
            reason=reason,
            customer_notes=notes,
            requested_by=request.user,
        )

        for oi in order_items.filter(pk__in=item_ids):
            qty = request.POST.get(f'qty_{oi.pk}', oi.quantity)
            try:
                qty = int(qty)
            except (ValueError, TypeError):
                qty = oi.quantity

            warehouse_models.CustomerReturnItem.objects.create(
                customer_return=rma,
                product=oi.product,
                quantity=min(qty, oi.quantity),
                reason=reason,
            )

        messages.success(request, f"Return request {rma.rma_number} created for order {order.order_number}.")
        return redirect('warehouse:rma_detail', pk=rma.pk)

    context = {
        'order': order,
        'order_items': order_items,
        'reason_choices': warehouse_models.RMA_REASON_CHOICES,
    }
    return render(request, 'warehouse/rma_create.html', context)


@login_required(login_url='account_login')
@user_passes_test(has_warehouse_access, login_url='account_login')
def rma_detail(request, pk):
    """View return detail — receive, inspect, and resolve items."""
    rma = get_object_or_404(
        warehouse_models.CustomerReturn.objects.select_related('order', 'business', 'warehouse'),
        pk=pk
    )
    items = rma.items.select_related('product', 'location').order_by('product__item_name')
    total = items.count()
    received = items.filter(is_received=True).count()
    inspected = items.filter(is_inspected=True).count()
    restocked = items.filter(is_restocked=True).count()

    context = {
        'rma': rma,
        'items': items,
        'total': total,
        'received': received,
        'inspected': inspected,
        'restocked': restocked,
        'disposition_choices': warehouse_models.RMA_DISPOSITION_CHOICES,
    }
    return render(request, 'warehouse/rma_detail.html', context)


@login_required(login_url='account_login')
@user_passes_test(has_warehouse_access, login_url='account_login')
@require_http_methods(["POST"])
def rma_receive(request, pk):
    """Mark all items in an RMA as received at warehouse."""
    rma = get_object_or_404(warehouse_models.CustomerReturn, pk=pk)

    rma.items.filter(is_received=False).update(is_received=True)
    rma.status = 'received'
    rma.received_at = timezone.now()
    rma.save(update_fields=['status', 'received_at', 'updated_at'])

    messages.success(request, f"Return {rma.rma_number} marked as received. Now inspect each item.")
    return redirect('warehouse:rma_detail', pk=rma.pk)


@login_required(login_url='account_login')
@user_passes_test(has_warehouse_access, login_url='account_login')
@require_http_methods(["POST"])
def rma_inspect_item(request, pk, item_id):
    """AJAX: Inspect a return item — set condition and disposition."""
    rma = get_object_or_404(warehouse_models.CustomerReturn, pk=pk)
    item = get_object_or_404(warehouse_models.CustomerReturnItem, pk=item_id, customer_return=rma)

    condition = request.POST.get('condition', 'good')
    disposition = request.POST.get('disposition', 'restock')

    item.condition = condition
    item.disposition = disposition
    item.is_inspected = True
    item.inspected_at = timezone.now()
    item.save(update_fields=['condition', 'disposition', 'is_inspected', 'inspected_at'])

    # Auto-restock if good condition
    if disposition == 'restock' and rma.warehouse:
        stock = warehouse_models.StockLevel.objects.filter(
            product=item.product,
            warehouse=rma.warehouse,
        ).first()
        if stock:
            old_qty = stock.quantity_on_hand
            stock.quantity_on_hand += item.quantity
            stock.save(update_fields=['quantity_on_hand'])

            warehouse_models.InventoryTransaction.objects.create(
                product=item.product,
                warehouse=rma.warehouse,
                location=stock.location,
                transaction_type='return',
                quantity=item.quantity,
                quantity_before=old_qty,
                quantity_after=stock.quantity_on_hand,
                reference_type='rma',
                reference_id=rma.rma_number,
                notes=f"Customer return restocked — {item.get_condition_display()}",
                created_by=request.user,
            )
            item.is_restocked = True
            item.restocked_at = timezone.now()
            item.location = stock.location
            item.save(update_fields=['is_restocked', 'restocked_at', 'location'])

    # Check if all inspected
    total = rma.items.count()
    inspected_count = rma.items.filter(is_inspected=True).count()
    all_done = inspected_count == total

    if all_done:
        rma.status = 'resolved'
        rma.inspected_at = timezone.now()
        rma.resolved_at = timezone.now()
        rma.save(update_fields=['status', 'inspected_at', 'resolved_at', 'updated_at'])

    return JsonResponse({
        'success': True,
        'item_id': item.id,
        'condition': condition,
        'disposition': disposition,
        'is_restocked': item.is_restocked,
        'inspected': inspected_count,
        'total': total,
        'all_done': all_done,
    })


# =============================================================================
# RETURN TASKS
# =============================================================================

@login_required(login_url='account_login')
@user_passes_test(has_warehouse_access, login_url='account_login')
def return_task_list(request):
    """List all return tasks for warehouse staff."""
    business, is_staff = get_business_filter(request)

    if is_staff:
        returns = warehouse_models.ReturnTask.objects.all()
    else:
        if not business:
            messages.error(request, "No business associated with your account")
            return redirect('business:business_dashboard')
        linked_wh_ids = warehouse_models.SellerWarehouseLink.objects.filter(
            business=business, is_active=True
        ).values_list('warehouse_id', flat=True)
        returns = warehouse_models.ReturnTask.objects.filter(warehouse_id__in=linked_wh_ids)

    status_filter = request.GET.get('status', '')
    if status_filter:
        returns = returns.filter(status=status_filter)

    returns = returns.select_related('warehouse', 'order', 'pick_list').order_by('-created_at')

    paginator = Paginator(returns, wh_per_page(request, 20))
    page = request.GET.get('page')
    returns = paginator.get_page(page)

    context = {
        'returns': returns,
        'per_page': str(wh_per_page(request, 20)),
        'status_choices': warehouse_models.RETURN_STATUS_CHOICES,
        'selected_status': status_filter,
        'is_staff': is_staff,
    }
    return render(request, 'warehouse/return_task_list.html', context)


@login_required(login_url='account_login')
@user_passes_test(has_warehouse_access, login_url='account_login')
def return_task_detail(request, pk):
    """View return task detail — staff marks items as returned to shelf."""
    return_task = get_object_or_404(
        warehouse_models.ReturnTask.objects.select_related('warehouse', 'order', 'pick_list'),
        pk=pk
    )

    if return_task.status == 'pending':
        return_task.status = 'in_progress'
        return_task.assigned_to = request.user
        return_task.save(update_fields=['status', 'assigned_to', 'updated_at'])

    items = return_task.items.select_related('product', 'location').order_by('location__code')
    total_items = items.count()
    returned_items = items.filter(is_returned=True).count()

    context = {
        'return_task': return_task,
        'items': items,
        'total_items': total_items,
        'returned_items': returned_items,
    }
    return render(request, 'warehouse/return_task_detail.html', context)


@login_required(login_url='account_login')
@user_passes_test(has_warehouse_access, login_url='account_login')
@require_http_methods(["POST"])
def return_item(request, pk, item_id):
    """AJAX: Mark an item as returned to shelf. Updates stock on_hand."""
    return_task = get_object_or_404(warehouse_models.ReturnTask, pk=pk)
    item = get_object_or_404(warehouse_models.ReturnTaskItem, pk=item_id, return_task=return_task)

    from warehouse.signals import complete_return_item
    complete_return_item(item, user=request.user)

    # Check if all items returned
    total = return_task.items.count()
    returned = return_task.items.filter(is_returned=True).count()
    all_done = returned == total

    if all_done:
        return_task.status = 'completed'
        return_task.completed_at = timezone.now()
        return_task.save(update_fields=['status', 'completed_at', 'updated_at'])

    return JsonResponse({
        'success': True,
        'item_id': item.id,
        'is_returned': True,
        'returned_items': returned,
        'total_items': total,
        'all_done': all_done,
    })


# =============================================================================
# CYCLE COUNTING
# =============================================================================

@login_required(login_url='account_login')
@user_passes_test(has_warehouse_access, login_url='account_login')
def cycle_count_list(request):
    """List all cycle counts"""
    business, is_staff = get_business_filter(request)

    if not is_staff and not business:
        messages.error(request, "No business associated with your account")
        return redirect('business:business_dashboard')

    if is_staff:
        cycle_counts = warehouse_models.CycleCount.objects.all()
    else:
        # Get warehouses linked to this business
        linked_warehouse_ids = warehouse_models.SellerWarehouseLink.objects.filter(
            business=business, is_active=True
        ).values_list('warehouse_id', flat=True)
        cycle_counts = warehouse_models.CycleCount.objects.filter(warehouse_id__in=linked_warehouse_ids)

    cycle_counts = cycle_counts.select_related('warehouse', 'location', 'assigned_to').order_by('-scheduled_date')

    status = request.GET.get('status')
    if status:
        cycle_counts = cycle_counts.filter(status=status)

    paginator = Paginator(cycle_counts, wh_per_page(request, 25))
    page = request.GET.get('page', 1)
    items = paginator.get_page(page)

    context = {
        'cycle_counts': items,
        'per_page': str(wh_per_page(request, 25)),
        'status_choices': warehouse_models.CYCLE_COUNT_STATUS_CHOICES,
        'selected_status': status,
        'is_staff': is_staff,
    }
    return render(request, 'warehouse/cycle_count_list.html', context)


def _get_descendant_location_ids(parent_location):
    """Get all descendant StorageLocation IDs recursively (max 5 levels)."""
    ids = []
    children = list(warehouse_models.StorageLocation.objects.filter(parent=parent_location).values_list('pk', flat=True))
    ids.extend(children)
    for child_id in children:
        child = warehouse_models.StorageLocation.objects.filter(pk=child_id).first()
        if child:
            ids.extend(_get_descendant_location_ids(child))
    return ids


@login_required(login_url='account_login')
@user_passes_test(has_warehouse_access, login_url='account_login')
def create_cycle_count(request):
    """Create a new cycle count — select warehouse, location (optional), and scheduled date."""
    business, is_staff = get_business_filter(request)

    if request.method == 'POST':
        warehouse_id = request.POST.get('warehouse')
        location_id = request.POST.get('location')
        scheduled_date = request.POST.get('scheduled_date')
        assigned_to_id = request.POST.get('assigned_to')
        notes = request.POST.get('notes', '')

        if not warehouse_id or not scheduled_date:
            messages.error(request, 'Warehouse and scheduled date are required.')
            return redirect('warehouse:create_cycle_count')

        try:
            warehouse = warehouse_models.Warehouse.objects.get(pk=warehouse_id, is_active=True)
        except warehouse_models.Warehouse.DoesNotExist:
            messages.error(request, 'Invalid warehouse selected.')
            return redirect('warehouse:create_cycle_count')

        location = None
        if location_id:
            location = warehouse_models.StorageLocation.objects.filter(
                pk=location_id, warehouse=warehouse
            ).first()

        assigned_to = None
        if assigned_to_id:
            from django.contrib.auth import get_user_model
            User = get_user_model()
            assigned_to = User.objects.filter(pk=assigned_to_id, is_staff=True).first()

        # Create the cycle count
        cycle_count = warehouse_models.CycleCount.objects.create(
            warehouse=warehouse,
            location=location,
            scheduled_date=scheduled_date,
            assigned_to=assigned_to,
            notes=notes,
            created_by=request.user,
            status='scheduled',
        )

        # Auto-populate count items from StockLevel
        stock_filter = {'warehouse': warehouse, 'quantity_on_hand__gt': 0}
        if location:
            # If a specific zone is selected, include all bins under it
            if location.location_type == 'zone':
                descendant_ids = _get_descendant_location_ids(location)
                descendant_ids.append(location.pk)
                stock_filter['location_id__in'] = descendant_ids
            else:
                stock_filter['location'] = location

        stock_levels = warehouse_models.StockLevel.objects.filter(
            **stock_filter
        ).select_related('product', 'location')

        count_items = []
        for sl in stock_levels:
            count_items.append(warehouse_models.CycleCountItem(
                cycle_count=cycle_count,
                product=sl.product,
                location=sl.location,
                system_quantity=sl.quantity_on_hand,
            ))
        if count_items:
            warehouse_models.CycleCountItem.objects.bulk_create(count_items)

        logger.info(f"Cycle count {cycle_count.count_number} created with {len(count_items)} items by {request.user.username}")
        messages.success(request, f'Cycle count {cycle_count.count_number} created with {len(count_items)} items.')
        return redirect('warehouse:cycle_count_detail', pk=cycle_count.pk)

    # GET — render form
    if is_staff:
        warehouses = warehouse_models.Warehouse.objects.filter(is_active=True).order_by('name')
    else:
        linked_ids = warehouse_models.SellerWarehouseLink.objects.filter(
            business=business, is_active=True
        ).values_list('warehouse_id', flat=True)
        warehouses = warehouse_models.Warehouse.objects.filter(pk__in=linked_ids, is_active=True).order_by('name')

    from django.contrib.auth import get_user_model
    User = get_user_model()
    staff_users = User.objects.filter(is_staff=True, is_active=True).order_by('first_name', 'username')

    context = {
        'warehouses': warehouses,
        'staff_users': staff_users,
        'is_staff': is_staff,
    }
    return render(request, 'warehouse/create_cycle_count.html', context)


@login_required(login_url='account_login')
@user_passes_test(has_warehouse_access, login_url='account_login')
def cycle_count_detail(request, pk):
    """View cycle count details with counting and approval actions"""
    business, is_staff = get_business_filter(request)

    if is_staff:
        cycle_count = get_object_or_404(warehouse_models.CycleCount, pk=pk)
    else:
        if not business:
            messages.error(request, "No business associated with your account")
            return redirect('business:business_dashboard')
        linked_warehouse_ids = warehouse_models.SellerWarehouseLink.objects.filter(
            business=business, is_active=True
        ).values_list('warehouse_id', flat=True)
        cycle_count = get_object_or_404(
            warehouse_models.CycleCount,
            pk=pk,
            warehouse_id__in=linked_warehouse_ids
        )

    items = cycle_count.items.select_related(
        'product', 'location', 'counted_by'
    ).order_by('location__code')

    total_items = items.count()
    counted_items = items.filter(is_counted=True).count()
    variance_items = items.filter(variance__isnull=False).exclude(variance=0).count()

    context = {
        'cycle_count': cycle_count,
        'items': items,
        'is_staff': is_staff,
        'total_items': total_items,
        'counted_items': counted_items,
        'variance_items': variance_items,
    }
    return render(request, 'warehouse/cycle_count_detail.html', context)


@login_required(login_url='account_login')
@user_passes_test(has_warehouse_access, login_url='account_login')
def start_cycle_count(request, pk):
    """Start a cycle count — assign to self and set in_progress"""
    cycle_count = get_object_or_404(warehouse_models.CycleCount, pk=pk)

    if cycle_count.status not in ('scheduled',):
        messages.error(request, 'This cycle count has already been started.')
        return redirect('warehouse:cycle_count_detail', pk=pk)

    cycle_count.status = 'in_progress'
    cycle_count.started_at = timezone.now()
    if not cycle_count.assigned_to:
        cycle_count.assigned_to = request.user
    cycle_count.save(update_fields=['status', 'started_at', 'assigned_to'])

    logger.info(f"Cycle count {cycle_count.count_number} started by {request.user.username}")
    messages.success(request, 'Cycle count started. Begin counting items.')
    return redirect('warehouse:cycle_count_detail', pk=pk)


@login_required(login_url='account_login')
@user_passes_test(has_warehouse_access, login_url='account_login')
@require_http_methods(["POST"])
def count_item(request, pk, item_id):
    """AJAX: Record counted quantity for a single item"""
    cycle_count = get_object_or_404(warehouse_models.CycleCount, pk=pk)

    if cycle_count.status not in ('in_progress',):
        return JsonResponse({'error': 'Count is not in progress'}, status=400)

    item = get_object_or_404(warehouse_models.CycleCountItem, pk=item_id, cycle_count=cycle_count)

    try:
        counted_qty = int(request.POST.get('counted_quantity', 0))
        if counted_qty < 0:
            return JsonResponse({'error': 'Quantity cannot be negative'}, status=400)
    except (ValueError, TypeError):
        return JsonResponse({'error': 'Invalid quantity'}, status=400)

    variance_reason = request.POST.get('variance_reason', '')

    item.counted_quantity = counted_qty
    item.variance = counted_qty - item.system_quantity
    item.is_counted = True
    item.counted_at = timezone.now()
    item.counted_by = request.user
    if variance_reason:
        item.variance_reason = variance_reason
    item.save()

    # Check progress
    total = cycle_count.items.count()
    counted = cycle_count.items.filter(is_counted=True).count()

    return JsonResponse({
        'success': True,
        'item_id': item.id,
        'counted_quantity': counted_qty,
        'variance': item.variance,
        'counted_items': counted,
        'total_items': total,
        'all_done': counted >= total,
    })


@login_required(login_url='account_login')
@user_passes_test(has_warehouse_access, login_url='account_login')
@require_http_methods(["POST"])
def submit_cycle_count(request, pk):
    """Submit cycle count for review after all items counted"""
    cycle_count = get_object_or_404(warehouse_models.CycleCount, pk=pk)

    if cycle_count.status != 'in_progress':
        messages.error(request, 'This cycle count is not in progress.')
        return redirect('warehouse:cycle_count_detail', pk=pk)

    # Check all items are counted
    uncounted = cycle_count.items.filter(is_counted=False).count()
    if uncounted > 0:
        messages.error(request, f'{uncounted} items still need to be counted.')
        return redirect('warehouse:cycle_count_detail', pk=pk)

    cycle_count.status = 'pending_review'
    cycle_count.completed_at = timezone.now()
    cycle_count.save(update_fields=['status', 'completed_at'])

    logger.info(f"Cycle count {cycle_count.count_number} submitted for review by {request.user.username}")
    messages.success(request, 'Cycle count submitted for review.')
    return redirect('warehouse:cycle_count_detail', pk=pk)


@login_required(login_url='account_login')
@user_passes_test(has_warehouse_access, login_url='account_login')
@require_http_methods(["POST"])
def approve_cycle_count(request, pk):
    """Approve cycle count and adjust stock levels for variances"""
    cycle_count = get_object_or_404(warehouse_models.CycleCount, pk=pk)

    if not _is_staff(request.user):
        messages.error(request, 'Only staff can approve cycle counts.')
        return redirect('warehouse:cycle_count_detail', pk=pk)

    if cycle_count.status != 'pending_review':
        messages.error(request, 'This cycle count is not pending review.')
        return redirect('warehouse:cycle_count_detail', pk=pk)

    from django.db import transaction as db_transaction
    adjustments_made = 0

    with db_transaction.atomic():
        items_with_variance = cycle_count.items.filter(
            is_counted=True
        ).exclude(variance=0).select_related('product', 'location')

        for item in items_with_variance:
            if item.variance is None or item.variance == 0:
                continue

            # Find the matching StockLevel
            stock_level = warehouse_models.StockLevel.objects.filter(
                product=item.product,
                warehouse=cycle_count.warehouse,
                location=item.location
            ).first()

            if not stock_level:
                continue

            old_qty = stock_level.quantity_on_hand
            new_qty = max(0, item.counted_quantity)
            adjustment = new_qty - old_qty

            if adjustment == 0:
                continue

            stock_level.quantity_on_hand = new_qty
            stock_level.last_count_date = timezone.now()
            stock_level.last_count_quantity = new_qty
            stock_level.save(update_fields=['quantity_on_hand', 'last_count_date', 'last_count_quantity', 'updated_at'])

            # Create inventory transaction
            txn_type = 'adjust_in' if adjustment > 0 else 'adjust_out'
            warehouse_models.InventoryTransaction.objects.create(
                product=item.product,
                warehouse=cycle_count.warehouse,
                location=item.location,
                transaction_type=txn_type,
                quantity=adjustment,
                quantity_before=old_qty,
                quantity_after=new_qty,
                reference_type='cycle_count',
                reference_id=cycle_count.count_number,
                notes=f"Cycle count adjustment. Variance: {item.variance}. Reason: {item.variance_reason or 'N/A'}",
                created_by=request.user,
            )
            adjustments_made += 1

        cycle_count.status = 'completed'
        cycle_count.approved_by = request.user
        cycle_count.approved_at = timezone.now()
        cycle_count.save(update_fields=['status', 'approved_by', 'approved_at'])

    logger.info(f"Cycle count {cycle_count.count_number} approved by {request.user.username} with {adjustments_made} adjustments")
    messages.success(request, f'Cycle count approved. {adjustments_made} stock adjustment(s) applied.')
    return redirect('warehouse:cycle_count_detail', pk=pk)


# =============================================================================
# ALERTS
# =============================================================================

@login_required(login_url='account_login')
@user_passes_test(has_warehouse_access, login_url='account_login')
def low_stock_alerts(request):
    """List low stock alerts"""
    business, is_staff = get_business_filter(request)

    if not is_staff and not business:
        messages.error(request, "No business associated with your account")
        return redirect('business:business_dashboard')

    if is_staff:
        alerts = warehouse_models.LowStockAlert.objects.all()
    else:
        # Get warehouses linked to this business
        linked_warehouse_ids = warehouse_models.SellerWarehouseLink.objects.filter(
            business=business, is_active=True
        ).values_list('warehouse_id', flat=True)
        alerts = warehouse_models.LowStockAlert.objects.filter(warehouse_id__in=linked_warehouse_ids)

    alerts = alerts.select_related('product', 'warehouse').order_by('-created_at')

    status = request.GET.get('status', 'active')
    if status:
        alerts = alerts.filter(status=status)

    paginator = Paginator(alerts, wh_per_page(request, 25))
    page = request.GET.get('page', 1)
    items = paginator.get_page(page)

    context = {
        'alerts': items,
        'per_page': str(wh_per_page(request, 25)),
        'status_choices': warehouse_models.ALERT_STATUS_CHOICES,
        'selected_status': status,
        'is_staff': is_staff,
    }
    return render(request, 'warehouse/low_stock_alerts.html', context)


@login_required(login_url='account_login')
@user_passes_test(has_warehouse_access, login_url='account_login')
def acknowledge_alert(request, pk):
    """Acknowledge a low stock alert"""
    business, is_staff = get_business_filter(request)

    if is_staff:
        alert = get_object_or_404(warehouse_models.LowStockAlert, pk=pk)
    else:
        if not business:
            return JsonResponse({'error': 'No business'}, status=400)
        # Get warehouses linked to this business
        linked_warehouse_ids = warehouse_models.SellerWarehouseLink.objects.filter(
            business=business, is_active=True
        ).values_list('warehouse_id', flat=True)
        alert = get_object_or_404(
            warehouse_models.LowStockAlert,
            pk=pk,
            warehouse_id__in=linked_warehouse_ids
        )

    if request.method == 'POST':
        alert.status = 'acknowledged'
        alert.acknowledged_by = request.user
        alert.acknowledged_at = timezone.now()
        alert.save(update_fields=['status', 'acknowledged_by', 'acknowledged_at'])
        messages.success(request, "Alert acknowledged")

    return redirect('warehouse:low_stock_alerts')


# =============================================================================
# WAREHOUSES & LOCATIONS
# =============================================================================

@login_required(login_url='account_login')
@user_passes_test(is_superuser_only)
def warehouse_list(request):
    """List all warehouses - Superuser only"""
    business, is_staff = get_business_filter(request)

    if not is_staff and not business:
        messages.error(request, "No business associated with your account")
        return redirect('business:business_dashboard')

    if is_staff:
        warehouses = warehouse_models.Warehouse.objects.all()
    else:
        # Get warehouses linked to this business
        linked_warehouse_ids = warehouse_models.SellerWarehouseLink.objects.filter(
            business=business, is_active=True
        ).values_list('warehouse_id', flat=True)
        warehouses = warehouse_models.Warehouse.objects.filter(id__in=linked_warehouse_ids)

    warehouses = warehouses.order_by('name')

    context = {
        'warehouses': warehouses,
        'is_staff': is_staff,
    }
    return render(request, 'warehouse/warehouse_list.html', context)


@login_required(login_url='account_login')
@user_passes_test(is_superuser_only)
def warehouse_add(request):
    """Add a new warehouse (fulfillment center) - Superuser only"""
    business, is_staff = get_business_filter(request)

    # Only staff can create fulfillment centers
    if not is_staff:
        messages.error(request, "Only staff can create fulfillment centers")
        return redirect('warehouse:warehouse_list')

    if request.method == 'POST':
        name = request.POST.get('name')
        code = request.POST.get('code', '')
        address = request.POST.get('address', '')
        city = request.POST.get('city', '')
        state = request.POST.get('state', '')
        postal_code = request.POST.get('postal_code', '')
        country = request.POST.get('country', 'Bahrain')
        phone = request.POST.get('phone', '')
        email = request.POST.get('email', '')
        description = request.POST.get('description', '')
        latitude = request.POST.get('latitude', '')
        longitude = request.POST.get('longitude', '')
        is_active = request.POST.get('is_active') == 'on'
        is_default = request.POST.get('is_default') == 'on'

        try:
            warehouse = warehouse_models.Warehouse.objects.create(
                name=name,
                code=code or None,  # Let auto-generate if empty
                description=description,
                address=address,
                city=city,
                state=state,
                postal_code=postal_code,
                country=country,
                phone=phone,
                email=email,
                latitude=float(latitude) if latitude else None,
                longitude=float(longitude) if longitude else None,
                is_active=is_active,
                is_default=is_default,
                created_by=request.user
            )
            messages.success(request, f"Fulfillment center '{warehouse.name}' ({warehouse.code}) created successfully")
            return redirect('warehouse:warehouse_detail', pk=warehouse.pk)
        except Exception as e:
            logger.exception(f"Error creating warehouse: {str(e)}")
            messages.error(request, f"Error creating warehouse: {str(e)}")

    context = {
        'is_staff': is_staff,
    }
    return render(request, 'warehouse/warehouse_add.html', context)


@login_required(login_url='account_login')
@user_passes_test(is_superuser_only)
def warehouse_edit(request, pk):
    """Edit an existing warehouse (fulfillment center) - Superuser only"""
    business, is_staff = get_business_filter(request)

    # Only staff can edit fulfillment centers
    if not is_staff:
        messages.error(request, "Only staff can edit fulfillment centers")
        return redirect('warehouse:warehouse_list')

    warehouse = get_object_or_404(warehouse_models.Warehouse, pk=pk)

    if request.method == 'POST':
        try:
            warehouse.name = request.POST.get('name')
            warehouse.code = request.POST.get('code', '')
            warehouse.address = request.POST.get('address', '')
            warehouse.city = request.POST.get('city', '')
            warehouse.state = request.POST.get('state', '')
            warehouse.postal_code = request.POST.get('postal_code', '')
            warehouse.country = request.POST.get('country', 'Bahrain')
            warehouse.phone = request.POST.get('phone', '')
            warehouse.email = request.POST.get('email', '')
            warehouse.description = request.POST.get('description', '')

            latitude = request.POST.get('latitude', '')
            longitude = request.POST.get('longitude', '')
            warehouse.latitude = float(latitude) if latitude else None
            warehouse.longitude = float(longitude) if longitude else None

            warehouse.is_active = request.POST.get('is_active') == 'on'
            warehouse.is_default = request.POST.get('is_default') == 'on'

            warehouse.save()

            messages.success(request, f"Warehouse '{warehouse.name}' ({warehouse.code}) updated successfully")
            return redirect('warehouse:warehouse_detail', pk=warehouse.pk)
        except Exception as e:
            logger.exception(f"Error updating warehouse: {str(e)}")
            messages.error(request, f"Error updating warehouse: {str(e)}")

    context = {
        'warehouse': warehouse,
        'is_staff': is_staff,
        'is_edit': True,
    }
    return render(request, 'warehouse/warehouse_add.html', context)


@login_required(login_url='account_login')
@user_passes_test(is_superuser_only)
def warehouse_detail(request, pk):
    """View warehouse details - Superuser only"""
    business, is_staff = get_business_filter(request)

    if is_staff:
        warehouse = get_object_or_404(warehouse_models.Warehouse, pk=pk)
    else:
        if not business:
            messages.error(request, "No business associated with your account")
            return redirect('business:business_dashboard')
        # Verify warehouse is linked to this business
        linked_warehouse_ids = warehouse_models.SellerWarehouseLink.objects.filter(
            business=business, is_active=True
        ).values_list('warehouse_id', flat=True)
        warehouse = get_object_or_404(
            warehouse_models.Warehouse,
            pk=pk,
            id__in=linked_warehouse_ids
        )

    locations = warehouse.storage_locations.order_by('location_type', 'code')
    stock_summary = warehouse.stock_levels.aggregate(
        total_on_hand=Sum('quantity_on_hand'),
        total_reserved=Sum('quantity_reserved')
    )

    context = {
        'warehouse': warehouse,
        'locations': locations,
        'stock_summary': stock_summary,
        'is_staff': is_staff,
    }
    return render(request, 'warehouse/warehouse_detail.html', context)


@login_required(login_url='account_login')
@user_passes_test(is_superuser_only)
def warehouse_capacity_configure(request, pk):
    """Configure warehouse internal capacity - Superuser only"""
    warehouse = get_object_or_404(warehouse_models.Warehouse, pk=pk)

    if request.method == 'POST':
        try:
            total_zones = int(request.POST.get('total_zones', 0))
            racks_per_zone = int(request.POST.get('racks_per_zone', 0))
            shelves_per_rack = int(request.POST.get('shelves_per_rack', 0))
            bins_per_shelf = int(request.POST.get('bins_per_shelf', 0))

            zone_naming_pattern = request.POST.get('zone_naming_pattern', 'A,B,C,D')
            rack_naming_pattern = request.POST.get('rack_naming_pattern', 'numeric')
            shelf_naming_pattern = request.POST.get('shelf_naming_pattern', 'numeric')
            bin_naming_pattern = request.POST.get('bin_naming_pattern', 'numeric')

            # Validate inputs
            if total_zones < 1:
                messages.error(request, "Total zones must be at least 1")
                return redirect('warehouse:warehouse_capacity_configure', pk=pk)
            if racks_per_zone < 1:
                messages.error(request, "Racks per zone must be at least 1")
                return redirect('warehouse:warehouse_capacity_configure', pk=pk)
            if shelves_per_rack < 1:
                messages.error(request, "Shelves per rack must be at least 1")
                return redirect('warehouse:warehouse_capacity_configure', pk=pk)
            if bins_per_shelf < 1:
                messages.error(request, "Bins per shelf must be at least 1")
                return redirect('warehouse:warehouse_capacity_configure', pk=pk)

            # Update warehouse configuration
            warehouse.total_zones = total_zones
            warehouse.racks_per_zone = racks_per_zone
            warehouse.shelves_per_rack = shelves_per_rack
            warehouse.bins_per_shelf = bins_per_shelf
            warehouse.zone_naming_pattern = zone_naming_pattern
            warehouse.rack_naming_pattern = rack_naming_pattern
            warehouse.shelf_naming_pattern = shelf_naming_pattern
            warehouse.bin_naming_pattern = bin_naming_pattern
            warehouse.is_capacity_configured = True
            warehouse.capacity_configured_at = timezone.now()
            warehouse.capacity_configured_by = request.user
            warehouse.save()

            messages.success(
                request,
                f"Capacity configured successfully! Total capacity: {warehouse.total_capacity:,} bins"
            )
            return redirect('warehouse:warehouse_capacity_preview', pk=pk)

        except ValueError as e:
            logger.exception(f"Error configuring warehouse capacity: {str(e)}")
            messages.error(request, f"Invalid input: {str(e)}")
        except Exception as e:
            logger.exception(f"Error configuring warehouse capacity: {str(e)}")
            messages.error(request, f"Error configuring capacity: {str(e)}")

    context = {
        'warehouse': warehouse,
        'is_staff': True,
    }
    return render(request, 'warehouse/warehouse_capacity_configure.html', context)


@login_required(login_url='account_login')
@user_passes_test(is_superuser_only)
def warehouse_capacity_preview(request, pk):
    """Preview warehouse capacity configuration and generate locations"""
    warehouse = get_object_or_404(warehouse_models.Warehouse, pk=pk)

    if not warehouse.is_capacity_configured:
        messages.warning(request, "Please configure warehouse capacity first")
        return redirect('warehouse:warehouse_capacity_configure', pk=pk)

    # Generate preview of location structure
    zone_names = warehouse.get_zone_names()
    preview_structure = []

    for zone_idx, zone_name in enumerate(zone_names, 1):
        zone_data = {
            'name': zone_name,
            'racks': []
        }

        # Show only first 3 racks as preview
        for rack_idx in range(1, min(4, warehouse.racks_per_zone + 1)):
            rack_name = warehouse.generate_location_name('rack', rack_idx)
            rack_data = {
                'name': rack_name,
                'shelves': []
            }

            # Show only first 3 shelves as preview
            for shelf_idx in range(1, min(4, warehouse.shelves_per_rack + 1)):
                shelf_name = warehouse.generate_location_name('shelf', shelf_idx)
                shelf_data = {
                    'name': shelf_name,
                    'bins': []
                }

                # Show only first 3 bins as preview
                for bin_idx in range(1, min(4, warehouse.bins_per_shelf + 1)):
                    bin_name = warehouse.generate_location_name('bin', bin_idx)
                    shelf_data['bins'].append(bin_name)

                if warehouse.bins_per_shelf > 3:
                    shelf_data['bins'].append(f"... {warehouse.bins_per_shelf - 3} more")

                rack_data['shelves'].append(shelf_data)

            if warehouse.shelves_per_rack > 3:
                rack_data['shelves'].append({'name': f"... {warehouse.shelves_per_rack - 3} more", 'bins': []})

            zone_data['racks'].append(rack_data)

        if warehouse.racks_per_zone > 3:
            zone_data['racks'].append({'name': f"... {warehouse.racks_per_zone - 3} more", 'shelves': []})

        preview_structure.append(zone_data)

    # Check if locations already generated
    existing_count = warehouse_models.StorageLocation.objects.filter(warehouse=warehouse).count()

    context = {
        'warehouse': warehouse,
        'preview_structure': preview_structure,
        'existing_count': existing_count,
        'is_staff': True,
    }
    return render(request, 'warehouse/warehouse_capacity_preview.html', context)


@login_required(login_url='account_login')
@user_passes_test(is_superuser_only)
def warehouse_generate_locations(request, pk):
    """Generate storage locations based on capacity configuration"""
    if request.method != 'POST':
        return redirect('warehouse:warehouse_capacity_preview', pk=pk)

    warehouse = get_object_or_404(warehouse_models.Warehouse, pk=pk)

    if not warehouse.is_capacity_configured:
        messages.error(request, "Warehouse capacity not configured")
        return redirect('warehouse:warehouse_capacity_configure', pk=pk)

    try:
        # Delete existing locations if requested
        if request.POST.get('delete_existing') == 'yes':
            existing_count = warehouse_models.StorageLocation.objects.filter(warehouse=warehouse).count()
            warehouse_models.StorageLocation.objects.filter(warehouse=warehouse).delete()
            logger.info(f"Deleted {existing_count} existing locations for warehouse {warehouse.code}")

        zone_names = warehouse.get_zone_names()
        locations_created = 0

        for zone_idx, zone_name in enumerate(zone_names, 1):
            # Create zone
            zone, created = warehouse_models.StorageLocation.objects.get_or_create(
                warehouse=warehouse,
                code=zone_name,
                defaults={
                    'name': f"Zone {zone_name}",
                    'location_type': 'zone',
                    'is_pickable': False,
                    'is_active': True,
                }
            )
            if created:
                locations_created += 1

            for rack_idx in range(1, warehouse.racks_per_zone + 1):
                rack_name = warehouse.generate_location_name('rack', rack_idx)
                rack_code = f"{zone_name}-{rack_name}"

                # Create rack
                rack, created = warehouse_models.StorageLocation.objects.get_or_create(
                    warehouse=warehouse,
                    code=rack_code,
                    defaults={
                        'name': f"Rack {rack_name}",
                        'location_type': 'rack',
                        'parent': zone,
                        'is_pickable': False,
                        'is_active': True,
                    }
                )
                if created:
                    locations_created += 1

                for shelf_idx in range(1, warehouse.shelves_per_rack + 1):
                    shelf_name = warehouse.generate_location_name('shelf', shelf_idx)
                    shelf_code = f"{rack_code}-{shelf_name}"

                    # Create shelf
                    shelf, created = warehouse_models.StorageLocation.objects.get_or_create(
                        warehouse=warehouse,
                        code=shelf_code,
                        defaults={
                            'name': f"Shelf {shelf_name}",
                            'location_type': 'shelf',
                            'parent': rack,
                            'is_pickable': False,
                            'is_active': True,
                        }
                    )
                    if created:
                        locations_created += 1

                    for bin_idx in range(1, warehouse.bins_per_shelf + 1):
                        bin_name = warehouse.generate_location_name('bin', bin_idx)
                        bin_code = f"{shelf_code}-{bin_name}"

                        # Create bin (pickable location)
                        bin_loc, created = warehouse_models.StorageLocation.objects.get_or_create(
                            warehouse=warehouse,
                            code=bin_code,
                            defaults={
                                'name': f"Bin {bin_name}",
                                'location_type': 'bin',
                                'parent': shelf,
                                'is_pickable': True,
                                'is_active': True,
                            }
                        )
                        if created:
                            locations_created += 1

        messages.success(
            request,
            f"Successfully generated {locations_created:,} storage locations for warehouse {warehouse.code}"
        )
        logger.info(f"Generated {locations_created} storage locations for warehouse {warehouse.code}")

        return redirect('warehouse:location_list')

    except Exception as e:
        logger.exception(f"Error generating storage locations: {str(e)}")
        messages.error(request, f"Error generating locations: {str(e)}")
        return redirect('warehouse:warehouse_capacity_preview', pk=pk)


@login_required(login_url='account_login')
@user_passes_test(is_superuser_only)
def location_list(request):
    """List all storage locations in hierarchical tree view"""
    business, is_staff = get_business_filter(request)

    if not is_staff and not business:
        messages.error(request, "No business associated with your account")
        return redirect('business:business_dashboard')

    if is_staff:
        warehouses = warehouse_models.Warehouse.objects.filter(is_active=True)
        all_locations = warehouse_models.StorageLocation.objects.all()
    else:
        linked_warehouse_ids = warehouse_models.SellerWarehouseLink.objects.filter(
            business=business, is_active=True
        ).values_list('warehouse_id', flat=True)
        warehouses = warehouse_models.Warehouse.objects.filter(id__in=linked_warehouse_ids, is_active=True)
        all_locations = warehouse_models.StorageLocation.objects.filter(warehouse_id__in=linked_warehouse_ids)

    warehouse_id = request.GET.get('warehouse')
    if warehouse_id:
        warehouses = warehouses.filter(pk=warehouse_id)
        all_locations = all_locations.filter(warehouse_id=warehouse_id)

    all_locations = all_locations.select_related('warehouse', 'parent').order_by('code')

    # Build hierarchical tree per warehouse
    warehouse_trees = []
    for wh in warehouses:
        wh_locs = [loc for loc in all_locations if loc.warehouse_id == wh.id]
        zones = [loc for loc in wh_locs if loc.location_type == 'zone']
        # Count totals
        type_counts = {}
        for loc in wh_locs:
            type_counts[loc.location_type] = type_counts.get(loc.location_type, 0) + 1

        zone_trees = []
        for zone in zones:
            racks = [loc for loc in wh_locs if loc.parent_id == zone.id and loc.location_type == 'rack']
            rack_trees = []
            for rack in racks:
                shelves = [loc for loc in wh_locs if loc.parent_id == rack.id and loc.location_type == 'shelf']
                shelf_trees = []
                for shelf in shelves:
                    bins = [loc for loc in wh_locs if loc.parent_id == shelf.id and loc.location_type == 'bin']
                    shelf.bin_list = bins
                    shelf_trees.append(shelf)
                rack.shelf_list = shelf_trees
                rack_trees.append(rack)
            zone.rack_list = rack_trees
            zone_trees.append(zone)

        warehouse_trees.append({
            'warehouse': wh,
            'zones': zone_trees,
            'type_counts': type_counts,
            'total': len(wh_locs),
        })

    context = {
        'warehouse_trees': warehouse_trees,
        'warehouses_all': warehouse_models.Warehouse.objects.filter(is_active=True),
        'selected_warehouse': warehouse_id,
        'total_locations': all_locations.count(),
        'is_staff': is_staff,
    }
    return render(request, 'warehouse/location_list.html', context)


@login_required(login_url='account_login')
@user_passes_test(is_superuser_only)
def location_add(request):
    """Add a new storage location - Superuser only"""
    business, is_staff = get_business_filter(request)

    if not is_staff and not business:
        messages.error(request, "No business associated with your account")
        return redirect('business:business_dashboard')

    if request.method == 'POST':
        warehouse_id = request.POST.get('warehouse')
        name = request.POST.get('name')
        code = request.POST.get('code')
        location_type = request.POST.get('location_type')
        parent_id = request.POST.get('parent')

        try:
            if is_staff:
                warehouse = warehouse_models.Warehouse.objects.get(pk=warehouse_id)
            else:
                # Verify warehouse is linked to this business
                if not warehouse_models.SellerWarehouseLink.objects.filter(
                    business=business, warehouse_id=warehouse_id, is_active=True
                ).exists():
                    raise ValueError("Warehouse is not linked to your business")
                warehouse = warehouse_models.Warehouse.objects.get(pk=warehouse_id)

            parent = None
            if parent_id:
                parent = warehouse_models.StorageLocation.objects.get(
                    pk=parent_id, warehouse=warehouse
                )

            location = warehouse_models.StorageLocation.objects.create(
                warehouse=warehouse,
                parent=parent,
                name=name,
                code=code,
                location_type=location_type
            )
            messages.success(request, f"Location '{location.code}' created")
            return redirect('warehouse:location_list')

        except Exception as e:
            messages.error(request, f"Error creating location: {str(e)}")

    if is_staff:
        warehouses = warehouse_models.Warehouse.objects.filter(is_active=True)
    else:
        # Get warehouses linked to this business
        linked_warehouse_ids = warehouse_models.SellerWarehouseLink.objects.filter(
            business=business, is_active=True
        ).values_list('warehouse_id', flat=True)
        warehouses = warehouse_models.Warehouse.objects.filter(id__in=linked_warehouse_ids, is_active=True)

    # Pre-select default warehouse: from URL param, or single warehouse, or is_default
    default_wh_id = request.GET.get('warehouse')
    if not default_wh_id:
        if warehouses.count() == 1:
            default_wh_id = str(warehouses.first().id)
        else:
            default_wh = warehouses.filter(is_default=True).first()
            if default_wh:
                default_wh_id = str(default_wh.id)

    context = {
        'warehouses': warehouses,
        'default_warehouse_id': default_wh_id,
        'location_types': warehouse_models.LOCATION_TYPE_CHOICES,
        'is_staff': is_staff,
    }
    return render(request, 'warehouse/location_add.html', context)


@login_required(login_url='account_login')
@user_passes_test(is_superuser_only)
def location_edit(request, pk):
    """Edit an existing storage location - Superuser only"""
    location = get_object_or_404(warehouse_models.StorageLocation, pk=pk)
    business, is_staff = get_business_filter(request)

    # For non-staff users, verify warehouse access
    if not is_staff:
        if not warehouse_models.SellerWarehouseLink.objects.filter(
            business=business,
            warehouse=location.warehouse,
            is_active=True
        ).exists():
            messages.error(request, "You don't have access to this warehouse")
            return redirect('warehouse:location_list')

    if request.method == 'POST':
        try:
            # Extract form data
            name = request.POST.get('name')
            location_type = request.POST.get('location_type')
            parent_id = request.POST.get('parent')
            is_pickable = request.POST.get('is_pickable') == 'on'
            is_active = request.POST.get('is_active') == 'on'

            # Validate parent belongs to same warehouse
            if parent_id:
                parent = warehouse_models.StorageLocation.objects.get(id=parent_id)
                if parent.warehouse != location.warehouse:
                    raise ValueError("Parent location must be in the same warehouse")
                location.parent = parent
            else:
                location.parent = None

            # Update fields (code and warehouse are not editable)
            location.name = name
            location.location_type = location_type
            location.is_pickable = is_pickable
            location.is_active = is_active
            location.save()

            # Log and message
            logger.info(f"Storage location {location.code} updated by {request.user.username}")
            messages.success(request, f"Storage location '{location.code}' updated successfully")

            return redirect('warehouse:location_list')

        except Exception as e:
            logger.error(f"Error updating storage location: {str(e)}")
            messages.error(request, f"Error updating location: {str(e)}")

    # GET request - prepare context
    if is_staff:
        warehouses = warehouse_models.Warehouse.objects.all().order_by('name')
    else:
        warehouse_links = warehouse_models.SellerWarehouseLink.objects.filter(
            business=business, is_active=True
        ).select_related('warehouse')
        warehouses = [link.warehouse for link in warehouse_links]

    # Get parent location options for the same warehouse
    parent_locations = warehouse_models.StorageLocation.objects.filter(
        warehouse=location.warehouse
    ).exclude(id=location.id).order_by('code')

    location_types = warehouse_models.LOCATION_TYPE_CHOICES

    context = {
        'location': location,
        'warehouses': warehouses,
        'parent_locations': parent_locations,
        'location_types': location_types,
        'is_staff': is_staff,
    }

    return render(request, 'warehouse/location_edit.html', context)


@login_required(login_url='account_login')
@user_passes_test(is_superuser_only)
def location_delete(request, pk):
    """Delete a storage location - Superuser only"""
    location = get_object_or_404(warehouse_models.StorageLocation, pk=pk)
    business, is_staff = get_business_filter(request)

    # For non-staff users, verify warehouse access
    if not is_staff:
        if not warehouse_models.SellerWarehouseLink.objects.filter(
            business=business,
            warehouse=location.warehouse,
            is_active=True
        ).exists():
            messages.error(request, "You don't have access to this warehouse")
            return redirect('warehouse:location_list')

    if request.method == 'POST':
        # Store display info before deletion
        location_code = location.code
        location_name = location.name
        warehouse_name = location.warehouse.name

        # Delete the location (CASCADE will handle related records)
        location.delete()

        # Log and message
        logger.info(f"Storage location {location_code} ({warehouse_name}) deleted by {request.user.username}")
        messages.success(request, f"Storage location '{location_code}' deleted successfully")

        return redirect('warehouse:location_list')

    # GET request - show confirmation
    context = {
        'location': location,
    }

    return render(request, 'warehouse/location_delete.html', context)


# =============================================================================
# API ENDPOINTS
# =============================================================================

@login_required(login_url='account_login')
@user_passes_test(has_warehouse_access, login_url='account_login')
def api_warehouse_locations(request, warehouse_id):
    """
    API endpoint to get pickup/dispatch locations for a specific warehouse.
    Returns JSON list of warehouse locations.
    Superuser access required.
    """
    # Check if user is superadmin
    if not _is_superadmin(request.user):
        return JsonResponse({'error': 'Permission denied'}, status=403)

    try:
        warehouse = get_object_or_404(warehouse_models.Warehouse, pk=warehouse_id)
        locations = warehouse.pickup_locations.filter(is_active=True).order_by('name')

        locations_data = [
            {
                'id': loc.id,
                'name': loc.name,
                'code': loc.code,
                'address': loc.address or '',
                'is_default': loc.is_default,
            }
            for loc in locations
        ]

        return JsonResponse(locations_data, safe=False)
    except Exception as e:
        logger.error(f"Error fetching warehouse locations: {e}")
        return JsonResponse({'error': str(e)}, status=400)


@login_required(login_url='account_login')
@user_passes_test(has_warehouse_access, login_url='account_login')
def api_storage_locations(request, warehouse_id):
    """
    API endpoint to get storage locations for a specific warehouse.
    Returns JSON list of storage locations for inventory.
    """
    try:
        warehouse = get_object_or_404(warehouse_models.Warehouse, pk=warehouse_id)
        locations = warehouse_models.StorageLocation.objects.filter(
            warehouse=warehouse,
            is_active=True
        ).order_by('name')

        locations_data = [
            {
                'id': loc.id,
                'name': loc.name,
                'code': loc.code or '',
                'location_type': loc.get_location_type_display(),
                'is_pickable': loc.is_pickable,
            }
            for loc in locations
        ]

        return JsonResponse(locations_data, safe=False)
    except Exception as e:
        logger.error(f"Error fetching storage locations: {e}")
        return JsonResponse({'error': str(e)}, status=400)


@login_required(login_url='account_login')
@user_passes_test(has_warehouse_access, login_url='account_login')
def api_business_products(request, business_id):
    """API endpoint to get products for a specific business."""
    try:
        products = product_models.Product.objects.filter(
            business_id=business_id
        ).order_by('item_name')
        products_data = [
            {
                'id': p.id,
                'name': p.item_name,
                'sku': p.item_sku or '',
            }
            for p in products
        ]
        return JsonResponse(products_data, safe=False)
    except Exception as e:
        logger.error(f"Error fetching business products: {e}")
        return JsonResponse({'error': str(e)}, status=400)


@login_required(login_url='account_login')
@user_passes_test(has_warehouse_access, login_url='account_login')
def api_inbound_request_items(request, request_id):
    """API endpoint to get items for a specific inbound request (for receive stock page)."""
    try:
        inbound_req = warehouse_models.InboundProductRequest.objects.select_related(
            'business', 'warehouse'
        ).get(pk=request_id)

        items = inbound_req.items.select_related('product').all()
        items_data = [
            {
                'product_id': item.product.id,
                'name': item.product.item_name,
                'sku': item.product.item_sku or '',
                'quantity_requested': item.quantity_requested,
                'quantity_fulfilled': item.quantity_fulfilled,
                'remaining': item.remaining_quantity,
            }
            for item in items
        ]
        return JsonResponse({
            'request_number': inbound_req.request_number,
            'business_name': inbound_req.business.business_name,
            'business_id': str(inbound_req.business.pk),
            'warehouse_id': inbound_req.warehouse.id,
            'status': inbound_req.status,
            'notes': inbound_req.notes,
            'items': items_data,
        })
    except warehouse_models.InboundProductRequest.DoesNotExist:
        return JsonResponse({'error': 'Request not found'}, status=404)
    except Exception as e:
        logger.error(f"Error fetching inbound request items: {e}")
        return JsonResponse({'error': str(e)}, status=400)


# =============================================================================
# WAREHOUSE LOCATION MANAGEMENT (Pickup/Dispatch Locations)
# =============================================================================

@login_required(login_url='account_login')
@user_passes_test(is_superuser_only)
def warehouse_location_list(request):
    """List all warehouse pickup/dispatch locations - Superuser only"""
    business, is_staff = get_business_filter(request)

    warehouses = warehouse_models.Warehouse.objects.filter(is_active=True).order_by('name')

    # Filter by warehouse if specified
    warehouse_id = request.GET.get('warehouse')
    if warehouse_id:
        locations = warehouse_models.WarehouseLocation.objects.filter(
            warehouse_id=warehouse_id
        ).select_related('warehouse').order_by('-is_default', 'name')
        selected_warehouse = warehouse_models.Warehouse.objects.get(pk=warehouse_id)
    else:
        locations = warehouse_models.WarehouseLocation.objects.select_related(
            'warehouse'
        ).order_by('warehouse__name', '-is_default', 'name')
        selected_warehouse = None

    per_page = wh_per_page(request, 25)
    paginator = Paginator(locations, per_page)
    page = request.GET.get('page', 1)
    items = paginator.get_page(page)

    # Query string carried by every pagination link (everything except page/per_page)
    filter_qs = request.GET.copy()
    filter_qs.pop('page', None)
    filter_qs.pop('per_page', None)

    context = {
        'locations': items,
        'warehouses': warehouses,
        'selected_warehouse': selected_warehouse,
        'is_staff': is_staff,
        'per_page': str(per_page),
        'filter_params': filter_qs.urlencode(),
    }
    return render(request, 'warehouse/warehouse_location_list.html', context)


@login_required(login_url='account_login')
@user_passes_test(is_superuser_only)
def warehouse_location_add(request):
    """Add a new warehouse pickup/dispatch location - Superuser only"""
    business, is_staff = get_business_filter(request)

    if request.method == 'POST':
        try:
            warehouse_id = request.POST.get('warehouse')
            name = request.POST.get('name')
            code = request.POST.get('code')
            address = request.POST.get('address', '')
            zone_number = request.POST.get('zone_number', '')
            latitude = request.POST.get('latitude', '')
            longitude = request.POST.get('longitude', '')
            operating_hours = request.POST.get('operating_hours', '')
            notes = request.POST.get('notes', '')
            is_active = request.POST.get('is_active') == 'on'
            is_default = request.POST.get('is_default') == 'on'

            # Validate required fields
            if not warehouse_id:
                messages.error(request, "Please select a warehouse")
                raise ValueError("Warehouse is required")

            if not name:
                messages.error(request, "Please enter a location name")
                raise ValueError("Location name is required")

            if not code:
                messages.error(request, "Please enter a location code")
                raise ValueError("Location code is required")

            warehouse = get_object_or_404(warehouse_models.Warehouse, pk=warehouse_id)

            # Create location
            location = warehouse_models.WarehouseLocation.objects.create(
                warehouse=warehouse,
                name=name,
                code=code,
                address=address,
                zone_number=int(zone_number) if zone_number else None,
                latitude=float(latitude) if latitude else None,
                longitude=float(longitude) if longitude else None,
                operating_hours=operating_hours,
                notes=notes,
                is_active=is_active,
                is_default=is_default
            )

            messages.success(
                request,
                f"Created pickup location: {location.warehouse.code}/{location.name}"
            )
            logger.info(f"Warehouse location created: {location} by {request.user.username}")

            return redirect('warehouse:warehouse_location_list')

        except Exception as e:
            logger.error(f"Error creating warehouse location: {e}")
            if "is required" not in str(e):
                messages.error(request, f"Error creating location: {str(e)}")

    # GET request - show form
    warehouses = warehouse_models.Warehouse.objects.filter(is_active=True).order_by('name')

    context = {
        'warehouses': warehouses,
        'is_staff': is_staff,
    }
    return render(request, 'warehouse/warehouse_location_add.html', context)


# =============================================================================
# PUT-AWAY TASKS
# =============================================================================

@login_required(login_url='account_login')
@user_passes_test(has_warehouse_access, login_url='account_login')
def put_away_list(request):
    """List all put-away tasks."""
    business, is_staff = get_business_filter(request)

    if is_staff:
        tasks = warehouse_models.PutAwayTask.objects.all()
    else:
        if not business:
            messages.error(request, "No business associated with your account")
            return redirect('business:business_dashboard')
        linked_wh_ids = warehouse_models.SellerWarehouseLink.objects.filter(
            business=business, is_active=True
        ).values_list('warehouse_id', flat=True)
        tasks = warehouse_models.PutAwayTask.objects.filter(warehouse_id__in=linked_wh_ids)

    status_filter = request.GET.get('status', '')
    if status_filter:
        tasks = tasks.filter(status=status_filter)

    tasks = tasks.select_related('warehouse', 'assigned_to', 'inbound_request').order_by('-created_at')

    paginator = Paginator(tasks, wh_per_page(request, 20))
    page = request.GET.get('page')
    tasks = paginator.get_page(page)

    context = {
        'tasks': tasks,
        'per_page': str(wh_per_page(request, 20)),
        'status_choices': warehouse_models.PUTAWAY_STATUS_CHOICES,
        'selected_status': status_filter,
        'is_staff': is_staff,
    }
    return render(request, 'warehouse/put_away_list.html', context)


@login_required(login_url='account_login')
@user_passes_test(has_warehouse_access, login_url='account_login')
def put_away_detail(request, pk):
    """View put-away task detail — staff places items at suggested locations."""
    task = get_object_or_404(
        warehouse_models.PutAwayTask.objects.select_related('warehouse', 'assigned_to', 'inbound_request'),
        pk=pk
    )

    # Auto-start when first viewed
    if task.status == 'pending':
        task.status = 'in_progress'
        task.assigned_to = request.user
        task.started_at = timezone.now()
        task.save(update_fields=['status', 'assigned_to', 'started_at', 'updated_at'])

    items = task.items.select_related(
        'product', 'suggested_location', 'actual_location', 'completed_by'
    ).order_by('suggested_location__code')
    total_items = items.count()
    completed_items = items.filter(is_completed=True).count()

    # Get available storage locations for the warehouse (for override dropdown)
    storage_locations = warehouse_models.StorageLocation.objects.filter(
        warehouse=task.warehouse, location_type='bin', is_active=True
    ).order_by('code')

    context = {
        'task': task,
        'items': items,
        'total_items': total_items,
        'completed_items': completed_items,
        'storage_locations': storage_locations,
    }
    return render(request, 'warehouse/put_away_detail.html', context)


@login_required(login_url='account_login')
@user_passes_test(has_warehouse_access, login_url='account_login')
@require_http_methods(["POST"])
def put_away_assign(request, pk):
    """Assign a put-away task to a staff member."""
    task = get_object_or_404(warehouse_models.PutAwayTask, pk=pk)

    if task.status not in ('pending', 'assigned'):
        return JsonResponse({'success': False, 'error': 'Task cannot be reassigned in current status'})

    task.assigned_to = request.user
    task.status = 'assigned'
    task.assigned_at = timezone.now()
    task.save(update_fields=['assigned_to', 'status', 'assigned_at', 'updated_at'])

    messages.success(request, f"Put-away task {task.task_number} assigned to you.")
    return redirect('warehouse:put_away_detail', pk=task.pk)


@login_required(login_url='account_login')
@user_passes_test(has_warehouse_access, login_url='account_login')
@require_http_methods(["POST"])
def put_away_confirm_item(request, pk, item_id):
    """AJAX: Confirm an item has been placed at its storage location."""
    task = get_object_or_404(warehouse_models.PutAwayTask, pk=pk)
    item = get_object_or_404(
        warehouse_models.PutAwayTaskItem, pk=item_id, put_away_task=task
    )

    if item.is_completed:
        return JsonResponse({'success': False, 'error': 'Item already completed'})

    # Check if staff overrode the suggested location
    override_location_id = request.POST.get('location_id', '')
    if override_location_id:
        actual_location = get_object_or_404(
            warehouse_models.StorageLocation, pk=override_location_id,
            warehouse=task.warehouse
        )
    else:
        actual_location = item.suggested_location

    if not actual_location:
        return JsonResponse({'success': False, 'error': 'No location specified'})

    # Transfer stock: deduct from source location, add to destination
    # 1. Deduct from source location (where stock was received)
    if item.source_location:
        source_stock = warehouse_models.StockLevel.objects.filter(
            product=item.product, warehouse=task.warehouse, location=item.source_location
        ).first()
        if source_stock:
            old_src = source_stock.quantity_on_hand
            source_stock.quantity_on_hand = max(0, source_stock.quantity_on_hand - item.quantity)
            source_stock.save(update_fields=['quantity_on_hand', 'updated_at'])
            warehouse_models.InventoryTransaction.objects.create(
                product=item.product, warehouse=task.warehouse,
                location=item.source_location,
                transaction_type='transfer_out', quantity=-item.quantity,
                quantity_before=old_src, quantity_after=source_stock.quantity_on_hand,
                reference_type='put_away', reference_id=task.task_number,
                notes=f"Put-away transfer out by {request.user.username}",
                created_by=request.user,
            )
    else:
        # Source was no-location (staging area) — deduct from null-location stock
        source_stock = warehouse_models.StockLevel.objects.filter(
            product=item.product, warehouse=task.warehouse, location__isnull=True
        ).first()
        if source_stock:
            old_src = source_stock.quantity_on_hand
            source_stock.quantity_on_hand = max(0, source_stock.quantity_on_hand - item.quantity)
            source_stock.save(update_fields=['quantity_on_hand', 'updated_at'])
            warehouse_models.InventoryTransaction.objects.create(
                product=item.product, warehouse=task.warehouse,
                location=None,
                transaction_type='transfer_out', quantity=-item.quantity,
                quantity_before=old_src, quantity_after=source_stock.quantity_on_hand,
                reference_type='put_away', reference_id=task.task_number,
                notes=f"Put-away transfer out from staging by {request.user.username}",
                created_by=request.user,
            )

    # 2. Add to destination location
    dest_stock, created = warehouse_models.StockLevel.objects.get_or_create(
        product=item.product, warehouse=task.warehouse, location=actual_location,
        defaults={'quantity_on_hand': 0}
    )
    old_dest = dest_stock.quantity_on_hand
    dest_stock.quantity_on_hand += item.quantity
    dest_stock.save(update_fields=['quantity_on_hand', 'updated_at'])

    warehouse_models.InventoryTransaction.objects.create(
        product=item.product, warehouse=task.warehouse,
        location=actual_location,
        transaction_type='transfer_in', quantity=item.quantity,
        quantity_before=old_dest, quantity_after=dest_stock.quantity_on_hand,
        reference_type='put_away', reference_id=task.task_number,
        notes=f"Put-away confirmed by {request.user.username}",
        created_by=request.user,
    )

    # Mark item as completed
    item.is_completed = True
    item.actual_location = actual_location
    item.completed_at = timezone.now()
    item.completed_by = request.user
    item.save(update_fields=[
        'is_completed', 'actual_location', 'completed_at', 'completed_by'
    ])

    # Update task progress
    total = task.items.count()
    completed = task.items.filter(is_completed=True).count()
    task.completed_items = completed
    all_done = completed == total

    if all_done:
        task.status = 'completed'
        task.completed_at = timezone.now()
        task.save(update_fields=['completed_items', 'status', 'completed_at', 'updated_at'])
    else:
        task.save(update_fields=['completed_items', 'updated_at'])

    return JsonResponse({
        'success': True,
        'item_id': item.id,
        'actual_location': actual_location.code,
        'completed_items': completed,
        'total_items': total,
        'all_done': all_done,
    })


def _create_put_away_task(warehouse, products_received, user, inbound_request=None):
    """
    Helper to create a put-away task after stock is received.
    products_received: list of dicts with 'product', 'quantity', 'location' (receiving dock location)
    Suggests optimal storage location for each product.
    """
    if not products_received:
        return None

    task = warehouse_models.PutAwayTask.objects.create(
        warehouse=warehouse,
        inbound_request=inbound_request,
        total_items=len(products_received),
        created_by=user,
    )

    for item_data in products_received:
        product = item_data['product']
        quantity = item_data['quantity']
        source_location = item_data.get('source_location')

        # Suggest optimal location:
        # 1. Where this product already has stock (consolidate)
        # 2. Fall back to None (staff picks location manually)
        suggested = None
        existing_stock = warehouse_models.StockLevel.objects.filter(
            product=product,
            warehouse=warehouse,
            location__isnull=False,
            location__is_active=True,
            location__location_type='bin',
        ).select_related('location').order_by('-quantity_on_hand').first()

        if existing_stock and existing_stock.location != source_location:
            suggested = existing_stock.location

        warehouse_models.PutAwayTaskItem.objects.create(
            put_away_task=task,
            product=product,
            quantity=quantity,
            source_location=source_location,
            suggested_location=suggested,
        )

    return task
