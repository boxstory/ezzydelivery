import logging
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Sum, F, Q
from django.http import JsonResponse
from django.utils import timezone

from warehouse import models as warehouse_models
from business import models as business_models
from product import models as product_models

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
    """Helper to get business for current user"""
    try:
        return business_models.Business.objects.get(user_id=request.user.id)
    except business_models.Business.DoesNotExist:
        return None


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


# =============================================================================
# DASHBOARD
# =============================================================================

@login_required(login_url='account_login')
def dashboard(request):
    """Warehouse dashboard with summary stats"""
    business, is_staff = get_business_filter(request)

    # Staff users see all warehouses, regular users see only their business
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
        warehouses = warehouse_models.Warehouse.objects.filter(
            business=business, is_active=True
        )
        stock_filter = {'warehouse__business': business}
        alert_filter = {'warehouse__business': business, 'status': 'active'}
        pick_filter = {'warehouse__business': business, 'status__in': ['pending', 'assigned', 'in_progress']}
        count_filter = {'warehouse__business': business, 'status__in': ['scheduled', 'in_progress']}
        txn_filter = {'warehouse__business': business}

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
    """List all inventory items"""
    business, is_staff = get_business_filter(request)

    if not is_staff and not business:
        messages.error(request, "No business associated with your account")
        return redirect('business:business_dashboard')

    # Filters
    warehouse_id = request.GET.get('warehouse')
    search = request.GET.get('search', '')
    low_stock_only = request.GET.get('low_stock') == '1'

    if is_staff:
        stock_levels = warehouse_models.StockLevel.objects.all()
        warehouses = warehouse_models.Warehouse.objects.filter(is_active=True)
    else:
        stock_levels = warehouse_models.StockLevel.objects.filter(warehouse__business=business)
        warehouses = warehouse_models.Warehouse.objects.filter(business=business, is_active=True)

    stock_levels = stock_levels.select_related('product', 'warehouse', 'location').order_by('product__item_name')

    if warehouse_id:
        stock_levels = stock_levels.filter(warehouse_id=warehouse_id)

    if search:
        stock_levels = stock_levels.filter(
            Q(product__item_name__icontains=search) |
            Q(product__item_sku__icontains=search)
        )

    if low_stock_only:
        stock_levels = stock_levels.filter(
            quantity_on_hand__lte=F('reorder_point') + F('quantity_reserved')
        )

    # Pagination
    paginator = Paginator(stock_levels, 25)
    page = request.GET.get('page', 1)
    items = paginator.get_page(page)

    context = {
        'stock_levels': items,
        'warehouses': warehouses,
        'search': search,
        'selected_warehouse': warehouse_id,
        'low_stock_only': low_stock_only,
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
        stock_levels = warehouse_models.StockLevel.objects.filter(
            product=product, warehouse__business=business
        )
        transactions = warehouse_models.InventoryTransaction.objects.filter(
            product=product, warehouse__business=business
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
        transactions = warehouse_models.InventoryTransaction.objects.filter(warehouse__business=business)
        warehouses = warehouse_models.Warehouse.objects.filter(business=business, is_active=True)

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
        # Handle stock receipt
        warehouse_id = request.POST.get('warehouse')
        product_id = request.POST.get('product')
        location_id = request.POST.get('location')
        quantity = int(request.POST.get('quantity', 0))
        notes = request.POST.get('notes', '')

        try:
            if is_staff:
                warehouse = warehouse_models.Warehouse.objects.get(pk=warehouse_id)
                product = product_models.Product.objects.get(pk=product_id)
            else:
                warehouse = warehouse_models.Warehouse.objects.get(pk=warehouse_id, business=business)
                product = product_models.Product.objects.get(pk=product_id, business=business)

            location = None
            if location_id:
                location = warehouse_models.StorageLocation.objects.get(
                    pk=location_id, warehouse=warehouse
                )

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

            # Create transaction record
            warehouse_models.InventoryTransaction.objects.create(
                product=product,
                warehouse=warehouse,
                location=location,
                transaction_type='receive',
                quantity=quantity,
                quantity_before=old_quantity,
                quantity_after=stock_level.quantity_on_hand,
                notes=notes,
                created_by=request.user
            )

            messages.success(request, f"Received {quantity} units of {product.item_name}")
            return redirect('warehouse:inventory_list')

        except Exception as e:
            logger.exception(f"Error receiving stock: {str(e)}")
            messages.error(request, f"Error receiving stock: {str(e)}")

    if is_staff:
        warehouses = warehouse_models.Warehouse.objects.filter(is_active=True)
        products = product_models.Product.objects.all()
    else:
        warehouses = warehouse_models.Warehouse.objects.filter(business=business, is_active=True)
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
        pick_lists = warehouse_models.PickList.objects.filter(warehouse__business=business)

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
        pick_list = get_object_or_404(
            warehouse_models.PickList,
            pk=pk,
            warehouse__business=business
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
        pick_list = get_object_or_404(
            warehouse_models.PickList,
            pk=pk,
            warehouse__business=business
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
        cycle_counts = warehouse_models.CycleCount.objects.filter(warehouse__business=business)

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
        cycle_count = get_object_or_404(
            warehouse_models.CycleCount,
            pk=pk,
            warehouse__business=business
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
        alerts = warehouse_models.LowStockAlert.objects.filter(warehouse__business=business)

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
        alert = get_object_or_404(
            warehouse_models.LowStockAlert,
            pk=pk,
            warehouse__business=business
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
def warehouse_list(request):
    """List all warehouses"""
    business, is_staff = get_business_filter(request)

    if not is_staff and not business:
        messages.error(request, "No business associated with your account")
        return redirect('business:business_dashboard')

    if is_staff:
        warehouses = warehouse_models.Warehouse.objects.all()
    else:
        warehouses = warehouse_models.Warehouse.objects.filter(business=business)

    warehouses = warehouses.order_by('name')

    context = {
        'warehouses': warehouses,
        'is_staff': is_staff,
    }
    return render(request, 'warehouse/warehouse_list.html', context)


@login_required(login_url='account_login')
def warehouse_add(request):
    """Add a new warehouse"""
    business, is_staff = get_business_filter(request)

    if not is_staff and not business:
        messages.error(request, "No business associated with your account")
        return redirect('business:business_dashboard')

    if request.method == 'POST':
        name = request.POST.get('name')
        code = request.POST.get('code', '')
        address = request.POST.get('address', '')
        business_id = request.POST.get('business')  # For staff to assign to a business

        if is_staff and business_id:
            selected_business = business_models.Business.objects.get(pk=business_id)
        else:
            selected_business = business

        warehouse = warehouse_models.Warehouse.objects.create(
            business=selected_business,
            name=name,
            code=code or None,  # Let auto-generate if empty
            address=address
        )
        messages.success(request, f"Warehouse '{warehouse.name}' created")
        return redirect('warehouse:warehouse_list')

    context = {
        'is_staff': is_staff,
    }
    if is_staff:
        context['businesses'] = business_models.Business.objects.filter(business_status='active')
    return render(request, 'warehouse/warehouse_add.html', context)


@login_required(login_url='account_login')
def warehouse_detail(request, pk):
    """View warehouse details"""
    business, is_staff = get_business_filter(request)

    if is_staff:
        warehouse = get_object_or_404(warehouse_models.Warehouse, pk=pk)
    else:
        if not business:
            messages.error(request, "No business associated with your account")
            return redirect('business:business_dashboard')
        warehouse = get_object_or_404(
            warehouse_models.Warehouse,
            pk=pk,
            business=business
        )

    locations = warehouse.locations.order_by('location_type', 'code')
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
def location_list(request):
    """List all storage locations"""
    business, is_staff = get_business_filter(request)

    if not is_staff and not business:
        messages.error(request, "No business associated with your account")
        return redirect('business:business_dashboard')

    if is_staff:
        locations = warehouse_models.StorageLocation.objects.all()
        warehouses = warehouse_models.Warehouse.objects.filter(is_active=True)
    else:
        locations = warehouse_models.StorageLocation.objects.filter(warehouse__business=business)
        warehouses = warehouse_models.Warehouse.objects.filter(business=business, is_active=True)

    locations = locations.select_related('warehouse', 'parent').order_by('warehouse', 'code')

    warehouse_id = request.GET.get('warehouse')
    if warehouse_id:
        locations = locations.filter(warehouse_id=warehouse_id)

    paginator = Paginator(locations, 50)
    page = request.GET.get('page', 1)
    items = paginator.get_page(page)

    context = {
        'locations': items,
        'warehouses': warehouses,
        'selected_warehouse': warehouse_id,
        'is_staff': is_staff,
    }
    return render(request, 'warehouse/location_list.html', context)


@login_required(login_url='account_login')
def location_add(request):
    """Add a new storage location"""
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
                warehouse = warehouse_models.Warehouse.objects.get(pk=warehouse_id, business=business)

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
        warehouses = warehouse_models.Warehouse.objects.filter(business=business, is_active=True)

    context = {
        'warehouses': warehouses,
        'location_types': warehouse_models.LOCATION_TYPE_CHOICES,
        'is_staff': is_staff,
    }
    return render(request, 'warehouse/location_add.html', context)
