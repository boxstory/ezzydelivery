"""
Seller-Warehouse Link Views
============================

Views for managing seller-warehouse relationships (many-to-many links).
Staff-only access to create, view, edit, and delete seller-warehouse connections.
"""

import logging
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from core.decorators import staff_required
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q, Count, Prefetch

from warehouse import models as warehouse_models
from business import models as business_models

logger = logging.getLogger('warehouse')


@login_required
@staff_required
def seller_warehouse_links(request):
    """
    List all seller-warehouse links with filtering and search.

    Staff-only view showing all connections between sellers and warehouses.
    Supports filtering by:
    - Seller (business)
    - Warehouse
    - Active status
    - Default status

    Template: warehouse/seller_warehouse_links.html
    """
    # Get filter parameters
    search_query = request.GET.get('search', '').strip()
    warehouse_filter = request.GET.get('warehouse', '')
    business_filter = request.GET.get('business', '')
    is_active_filter = request.GET.get('is_active', '')
    is_default_filter = request.GET.get('is_default', '')

    # Base queryset with prefetch for performance
    links = warehouse_models.SellerWarehouseLink.objects.select_related(
        'business',
        'warehouse',
        'default_location',
        'linked_by'
    ).order_by('-is_default', '-priority', 'business__business_name')

    # Apply filters
    if search_query:
        links = links.filter(
            Q(business__business_name__icontains=search_query) |
            Q(warehouse__name__icontains=search_query) |
            Q(warehouse__code__icontains=search_query)
        )

    if warehouse_filter:
        links = links.filter(warehouse_id=warehouse_filter)

    if business_filter:
        links = links.filter(business_id=business_filter)

    if is_active_filter:
        links = links.filter(is_active=is_active_filter == 'true')

    if is_default_filter:
        links = links.filter(is_default=is_default_filter == 'true')

    # Get counts for stats
    total_links = links.count()
    active_links = links.filter(is_active=True).count()
    default_links = links.filter(is_default=True).count()

    # Get unique businesses and warehouses for filter dropdowns
    all_businesses = business_models.Business.objects.filter(
        warehouse_links__isnull=False
    ).distinct().order_by('business_name')

    all_warehouses = warehouse_models.Warehouse.objects.filter(
        seller_links__isnull=False
    ).distinct().order_by('name')

    # Pagination — ?per_page= validated against the shared pager options
    try:
        per_page = int(request.GET.get('per_page', 25))
    except (ValueError, TypeError):
        per_page = 25
    if per_page not in (10, 25, 50, 100):
        per_page = 25

    paginator = Paginator(links, per_page)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    # Query string carried by every pagination link (everything except page/per_page)
    filter_qs = request.GET.copy()
    filter_qs.pop('page', None)
    filter_qs.pop('per_page', None)

    context = {
        'page_obj': page_obj,
        'per_page': str(per_page),
        'filter_params': filter_qs.urlencode(),
        'links': page_obj.object_list,
        'total_links': total_links,
        'active_links': active_links,
        'default_links': default_links,
        'all_businesses': all_businesses,
        'all_warehouses': all_warehouses,
        'search_query': search_query,
        'warehouse_filter': warehouse_filter,
        'business_filter': business_filter,
        'is_active_filter': is_active_filter,
        'is_default_filter': is_default_filter,
    }

    return render(request, 'warehouse/seller_warehouse_links.html', context)


@login_required
@staff_required
def seller_warehouse_link_detail(request, pk):
    """
    View details of a specific seller-warehouse link.

    Shows:
    - Link information (seller, warehouse, default location)
    - Priority and default status
    - Link history and metadata
    - Related orders/transactions (future)

    Template: warehouse/seller_warehouse_link_detail.html
    """
    link = get_object_or_404(
        warehouse_models.SellerWarehouseLink.objects.select_related(
            'business',
            'warehouse',
            'default_location',
            'linked_by'
        ),
        pk=pk
    )

    # Get other links for this business
    other_business_links = warehouse_models.SellerWarehouseLink.objects.filter(
        business=link.business
    ).exclude(pk=pk).select_related('warehouse', 'default_location')

    # Get other links for this warehouse
    other_warehouse_links = warehouse_models.SellerWarehouseLink.objects.filter(
        warehouse=link.warehouse
    ).exclude(pk=pk).select_related('business', 'default_location')

    # Get available locations at this warehouse
    available_locations = link.warehouse.pickup_locations.filter(
        is_active=True
    ).order_by('-is_default', 'name')

    context = {
        'link': link,
        'other_business_links': other_business_links,
        'other_warehouse_links': other_warehouse_links,
        'available_locations': available_locations,
    }

    return render(request, 'warehouse/seller_warehouse_link_detail.html', context)


@login_required
@staff_required
def seller_warehouse_link_add(request):
    """
    Create a new seller-warehouse link.

    Form allows staff to:
    - Select seller (business)
    - Select warehouse
    - Choose default location at that warehouse
    - Set priority (0-100)
    - Mark as default warehouse for seller
    - Mark as active/inactive
    - Add notes

    Template: warehouse/seller_warehouse_link_form.html
    """
    if request.method == 'POST':
        try:
            business_id = request.POST.get('business')
            warehouse_id = request.POST.get('warehouse')
            default_location_id = request.POST.get('default_location')
            priority = int(request.POST.get('priority', 0))
            is_default = request.POST.get('is_default') == 'on'
            is_active = request.POST.get('is_active', 'on') == 'on'
            notes = request.POST.get('notes', '').strip()

            # Validate required fields
            if not business_id:
                messages.error(request, "Please select a seller/business")
                raise ValueError("Business is required")

            if not warehouse_id:
                messages.error(request, "Please select a warehouse")
                raise ValueError("Warehouse is required")

            business = get_object_or_404(business_models.Business, pk=business_id)
            warehouse = get_object_or_404(warehouse_models.Warehouse, pk=warehouse_id)

            # Validate default_location belongs to warehouse
            default_location = None
            if default_location_id:
                default_location = get_object_or_404(
                    warehouse_models.WarehouseLocation,
                    pk=default_location_id,
                    warehouse=warehouse
                )

            # Check if link already exists
            existing_link = warehouse_models.SellerWarehouseLink.objects.filter(
                business=business,
                warehouse=warehouse
            ).first()

            if existing_link:
                messages.warning(
                    request,
                    f"Link already exists between {business.business_name} and {warehouse.name}. "
                    f"Edit the existing link instead."
                )
                return redirect('warehouse:seller_warehouse_link_detail', pk=existing_link.pk)

            # Create link
            link = warehouse_models.SellerWarehouseLink.objects.create(
                business=business,
                warehouse=warehouse,
                default_location=default_location,
                priority=priority,
                is_default=is_default,
                is_active=is_active,
                notes=notes,
                linked_by=request.user
            )

            messages.success(
                request,
                f"Created link: {business.business_name} → {warehouse.name}"
            )
            logger.info(
                f"Seller-warehouse link created: {link} by {request.user.username}"
            )

            return redirect('warehouse:seller_warehouse_link_detail', pk=link.pk)

        except Exception as e:
            logger.error(f"Error creating seller-warehouse link: {e}")
            if "Business is required" not in str(e) and "Warehouse is required" not in str(e):
                messages.error(request, f"Error creating link: {str(e)}")

    # GET request or failed POST - show form
    businesses = business_models.Business.objects.filter(
        business_status='active'
    ).order_by('business_name')

    warehouses = warehouse_models.Warehouse.objects.filter(
        is_active=True
    ).order_by('name')

    context = {
        'businesses': businesses,
        'warehouses': warehouses,
        'is_create': True,
    }

    return render(request, 'warehouse/seller_warehouse_link_form.html', context)


@login_required
@staff_required
def seller_warehouse_link_edit(request, pk):
    """
    Edit an existing seller-warehouse link.

    Allows updating:
    - Default location
    - Priority
    - Default status
    - Active status
    - Notes

    Cannot change business or warehouse (create new link instead).

    Template: warehouse/seller_warehouse_link_form.html
    """
    link = get_object_or_404(warehouse_models.SellerWarehouseLink, pk=pk)

    if request.method == 'POST':
        try:
            default_location_id = request.POST.get('default_location')
            priority = int(request.POST.get('priority', 0))
            is_default = request.POST.get('is_default') == 'on'
            is_active = request.POST.get('is_active', 'on') == 'on'
            notes = request.POST.get('notes', '').strip()

            # Validate default_location belongs to warehouse
            default_location = None
            if default_location_id:
                default_location = get_object_or_404(
                    warehouse_models.WarehouseLocation,
                    pk=default_location_id,
                    warehouse=link.warehouse
                )

            # Update link
            link.default_location = default_location
            link.priority = priority
            link.is_default = is_default
            link.is_active = is_active
            link.notes = notes
            link.save()

            messages.success(request, f"Updated link: {link}")
            logger.info(
                f"Seller-warehouse link updated: {link} by {request.user.username}"
            )

            return redirect('warehouse:seller_warehouse_link_detail', pk=link.pk)

        except Exception as e:
            logger.error(f"Error updating seller-warehouse link: {e}")
            messages.error(request, f"Error updating link: {str(e)}")

    # GET request - show form
    available_locations = link.warehouse.pickup_locations.filter(
        is_active=True
    ).order_by('-is_default', 'name')

    context = {
        'link': link,
        'available_locations': available_locations,
        'is_create': False,
    }

    return render(request, 'warehouse/seller_warehouse_link_form.html', context)


@login_required
@staff_required
def seller_warehouse_link_delete(request, pk):
    """
    Delete a seller-warehouse link.

    Requires POST request for safety.
    Shows confirmation page on GET.

    Template: warehouse/seller_warehouse_link_confirm_delete.html
    """
    link = get_object_or_404(warehouse_models.SellerWarehouseLink, pk=pk)

    if request.method == 'POST':
        business_name = link.business.business_name
        warehouse_name = link.warehouse.name

        link.delete()

        messages.success(
            request,
            f"Deleted link: {business_name} → {warehouse_name}"
        )
        logger.info(
            f"Seller-warehouse link deleted: {business_name} → {warehouse_name} "
            f"by {request.user.username}"
        )

        return redirect('warehouse:seller_warehouse_links')

    context = {
        'link': link,
    }

    return render(request, 'warehouse/seller_warehouse_link_confirm_delete.html', context)
