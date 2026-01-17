import logging
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Sum, F, Q
from django.http import JsonResponse
from django.utils import timezone

from warehouse import models as warehouse_models
from business import models as business_models
from product import models as product_models
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


def is_staff_user(request):
    """Check if user is a staff member (can access all warehouses)"""
    return request.user.is_staff or request.user.is_superuser


def is_superuser_only(user):
    """Check if user is a superuser (required for warehouse setup/config)"""
    return user.is_superuser


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


# =============================================================================
# DASHBOARD
# =============================================================================

@login_required(login_url='account_login')
def dashboard(request):
    """Warehouse dashboard with summary stats"""
    business, is_staff = get_business_filter(request)

    # Staff users see all warehouses, regular users see only linked warehouses
    if is_staff:
        warehouses = warehouse_models.Warehouse.objects.filter(is_active=True)
        stock_filter = {}
        alert_filter = {'status': 'active'}
        pick_filter = {'status__in': ['pending', 'assigned', 'in_progress']}
        count_filter = {'status__in': ['scheduled', 'in_progress']}
        txn_filter = {}
    else:
        if not business:
            messages.error(request, "No business associated with your account")
            return redirect('business:business_dashboard')
        # Get warehouses linked to this business
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

    # Summary stats
    total_stock = warehouse_models.StockLevel.objects.filter(
        **stock_filter
    ).aggregate(
        total_on_hand=Sum('quantity_on_hand'),
        total_reserved=Sum('quantity_reserved')
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

    # Recent transactions
    recent_transactions = warehouse_models.InventoryTransaction.objects.filter(
        **txn_filter
    ).select_related('product', 'warehouse').order_by('-created_at')[:10]

    context = {
        'warehouses': warehouses,
        'total_on_hand': total_stock['total_on_hand'] or 0,
        'total_reserved': total_stock['total_reserved'] or 0,
        'low_stock_count': low_stock_count,
        'pending_picks': pending_picks,
        'pending_counts': pending_counts,
        'recent_transactions': recent_transactions,
        'is_staff': is_staff,
    }
    return render(request, 'warehouse/dashboard.html', context)


# =============================================================================
# INVENTORY
# =============================================================================

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
    return render(request, 'warehouse/inventory_list.html', context)


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
    return render(request, 'warehouse/stock_card.html', context)


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

    context = {
        'transactions': items,
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
def receive_stock(request):
    """Receive new stock into warehouse"""
    business, is_staff = get_business_filter(request)

    if not is_staff and not business:
        messages.error(request, "No business associated with your account")
        return redirect('business:business_dashboard')

    if request.method == 'POST':
        # Handle stock receipt (now supports multiple products)
        warehouse_id = request.POST.get('warehouse')
        location_id = request.POST.get('location')
        reference = request.POST.get('reference', '')
        notes = request.POST.get('notes', '')

        # Get arrays of products and quantities
        product_ids = request.POST.getlist('products[]')
        quantities = request.POST.getlist('quantities[]')

        try:
            # Validate warehouse access
            if is_staff:
                warehouse = warehouse_models.Warehouse.objects.get(pk=warehouse_id)
            else:
                # Verify warehouse is linked to this business
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

            # Process each product
            received_products = []
            total_items = 0

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
                transaction_notes = notes
                if reference:
                    transaction_notes = f"Ref: {reference}" + (f" | {notes}" if notes else "")

                # Create transaction record
                warehouse_models.InventoryTransaction.objects.create(
                    product=product,
                    warehouse=warehouse,
                    location=location,
                    transaction_type='receive',
                    quantity=quantity,
                    quantity_before=old_quantity,
                    quantity_after=stock_level.quantity_on_hand,
                    notes=transaction_notes,
                    created_by=request.user
                )

                received_products.append(f"{product.item_name} ({quantity} units)")
                total_items += quantity

            # Success message
            if len(received_products) == 1:
                messages.success(request, f"Received {received_products[0]}")
            else:
                summary = ", ".join(received_products[:3])
                if len(received_products) > 3:
                    summary += f" and {len(received_products) - 3} more"
                messages.success(request, f"Received {len(received_products)} products ({total_items} total items): {summary}")

            return redirect('warehouse:inventory_list')

        except Exception as e:
            logger.exception(f"Error receiving stock: {str(e)}")
            messages.error(request, f"Error receiving stock: {str(e)}")

    if is_staff:
        warehouses = warehouse_models.Warehouse.objects.filter(is_active=True)
        products = product_models.Product.objects.all()
    else:
        # Get warehouses linked to this business
        linked_warehouse_ids = warehouse_models.SellerWarehouseLink.objects.filter(
            business=business, is_active=True
        ).values_list('warehouse_id', flat=True)
        warehouses = warehouse_models.Warehouse.objects.filter(id__in=linked_warehouse_ids, is_active=True)
        products = product_models.Product.objects.filter(business=business)

    context = {
        'warehouses': warehouses,
        'products': products,
        'is_staff': is_staff,
    }
    return render(request, 'warehouse/receive_stock.html', context)


@login_required(login_url='account_login')
def confirm_receive(request):
    """AJAX endpoint to confirm receipt"""
    # Placeholder for barcode scanning confirmation
    return JsonResponse({'status': 'ok'})


# =============================================================================
# PICKING
# =============================================================================

@login_required(login_url='account_login')
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

    pick_lists = pick_lists.select_related('warehouse', 'assigned_to').order_by('-created_at')

    # Filter by status
    status = request.GET.get('status')
    if status:
        pick_lists = pick_lists.filter(status=status)

    paginator = Paginator(pick_lists, 25)
    page = request.GET.get('page', 1)
    items = paginator.get_page(page)

    context = {
        'pick_lists': items,
        'status_choices': warehouse_models.PICKLIST_STATUS_CHOICES,
        'selected_status': status,
        'is_staff': is_staff,
    }
    return render(request, 'warehouse/pick_list_list.html', context)


@login_required(login_url='account_login')
def create_pick_list(request):
    """Create a new pick list from pending orders"""
    # Placeholder - implement wave picking logic
    messages.info(request, "Pick list creation coming soon")
    return redirect('warehouse:pick_list_list')


@login_required(login_url='account_login')
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

    context = {
        'pick_list': pick_list,
        'items': items,
        'is_staff': is_staff,
    }
    return render(request, 'warehouse/pick_list_detail.html', context)


@login_required(login_url='account_login')
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


# =============================================================================
# CYCLE COUNTING
# =============================================================================

@login_required(login_url='account_login')
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

    paginator = Paginator(cycle_counts, 25)
    page = request.GET.get('page', 1)
    items = paginator.get_page(page)

    context = {
        'cycle_counts': items,
        'status_choices': warehouse_models.CYCLE_COUNT_STATUS_CHOICES,
        'selected_status': status,
        'is_staff': is_staff,
    }
    return render(request, 'warehouse/cycle_count_list.html', context)


@login_required(login_url='account_login')
def create_cycle_count(request):
    """Create a new cycle count"""
    # Placeholder
    messages.info(request, "Cycle count creation coming soon")
    return redirect('warehouse:cycle_count_list')


@login_required(login_url='account_login')
def cycle_count_detail(request, pk):
    """View cycle count details"""
    business, is_staff = get_business_filter(request)

    if is_staff:
        cycle_count = get_object_or_404(warehouse_models.CycleCount, pk=pk)
    else:
        if not business:
            messages.error(request, "No business associated with your account")
            return redirect('business:business_dashboard')
        # Get warehouses linked to this business
        linked_warehouse_ids = warehouse_models.SellerWarehouseLink.objects.filter(
            business=business, is_active=True
        ).values_list('warehouse_id', flat=True)
        cycle_count = get_object_or_404(
            warehouse_models.CycleCount,
            pk=pk,
            warehouse_id__in=linked_warehouse_ids
        )

    items = cycle_count.items.select_related(
        'product', 'location'
    ).order_by('location__code')

    context = {
        'cycle_count': cycle_count,
        'items': items,
        'is_staff': is_staff,
    }
    return render(request, 'warehouse/cycle_count_detail.html', context)


# =============================================================================
# ALERTS
# =============================================================================

@login_required(login_url='account_login')
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

    paginator = Paginator(alerts, 25)
    page = request.GET.get('page', 1)
    items = paginator.get_page(page)

    context = {
        'alerts': items,
        'status_choices': warehouse_models.ALERT_STATUS_CHOICES,
        'selected_status': status,
        'is_staff': is_staff,
    }
    return render(request, 'warehouse/low_stock_alerts.html', context)


@login_required(login_url='account_login')
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
    """List all storage locations - Superuser only"""
    business, is_staff = get_business_filter(request)

    if not is_staff and not business:
        messages.error(request, "No business associated with your account")
        return redirect('business:business_dashboard')

    if is_staff:
        locations = warehouse_models.StorageLocation.objects.all()
        warehouses = warehouse_models.Warehouse.objects.filter(is_active=True)
    else:
        # Get warehouses linked to this business
        linked_warehouse_ids = warehouse_models.SellerWarehouseLink.objects.filter(
            business=business, is_active=True
        ).values_list('warehouse_id', flat=True)
        locations = warehouse_models.StorageLocation.objects.filter(warehouse_id__in=linked_warehouse_ids)
        warehouses = warehouse_models.Warehouse.objects.filter(id__in=linked_warehouse_ids, is_active=True)

    locations = locations.select_related('warehouse', 'parent').order_by('warehouse', 'code')

    warehouse_id = request.GET.get('warehouse')
    if warehouse_id:
        locations = locations.filter(warehouse_id=warehouse_id)

    # Get view mode from query parameter
    view_mode = request.GET.get('view', 'table')

    paginator = Paginator(locations, 50)
    page = request.GET.get('page', 1)
    items = paginator.get_page(page)

    context = {
        'locations': items,
        'warehouses': warehouses,
        'selected_warehouse': warehouse_id,
        'view_mode': view_mode,
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

    context = {
        'warehouses': warehouses,
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
def api_warehouse_locations(request, warehouse_id):
    """
    API endpoint to get pickup/dispatch locations for a specific warehouse.
    Returns JSON list of warehouse locations.
    Superuser access required.
    """
    # Check if user is superuser
    if not request.user.is_superuser:
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

    paginator = Paginator(locations, 25)
    page = request.GET.get('page', 1)
    items = paginator.get_page(page)

    context = {
        'locations': items,
        'warehouses': warehouses,
        'selected_warehouse': selected_warehouse,
        'is_staff': is_staff,
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
