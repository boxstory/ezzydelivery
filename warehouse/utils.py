"""
Warehouse Utilities Module
===========================

Helper functions for warehouse management and auto-selection logic.

Functions:
    - get_recommended_warehouse_location: Auto-select warehouse location for order
    - calculate_distance: Calculate distance between two GPS coordinates
    - get_seller_warehouses: Get all warehouses linked to a seller
    - get_default_warehouse: Get seller's default warehouse
"""

import logging
from math import radians, cos, sin, asin, sqrt
from typing import Optional, List, Tuple
from django.db.models import Q

logger = logging.getLogger('warehouse')


def calculate_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calculate the great-circle distance between two points on Earth using the Haversine formula.

    Args:
        lat1: Latitude of first point (decimal degrees)
        lon1: Longitude of first point (decimal degrees)
        lat2: Latitude of second point (decimal degrees)
        lon2: Longitude of second point (decimal degrees)

    Returns:
        Distance in kilometers

    Example:
        >>> distance = calculate_distance(26.2285, 50.5860, 26.2361, 50.5922)
        >>> print(f"{distance:.2f} km")
        1.12 km
    """
    # Earth's radius in kilometers
    R = 6371

    # Convert decimal degrees to radians
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])

    # Haversine formula
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
    c = 2 * asin(sqrt(a))

    return R * c


def get_seller_warehouses(business, include_inactive=False):
    """
    Get all warehouses linked to a seller.

    Args:
        business: Business instance
        include_inactive: Include inactive links (default: False)

    Returns:
        QuerySet of Warehouse objects

    Example:
        >>> from business.models import Business
        >>> business = Business.objects.get(business_id=123)
        >>> warehouses = get_seller_warehouses(business)
        >>> for warehouse in warehouses:
        ...     print(warehouse.name)
    """
    from warehouse.models import Warehouse, SellerWarehouseLink

    filters = Q(seller_links__business=business)
    if not include_inactive:
        filters &= Q(seller_links__is_active=True) & Q(is_active=True)

    return Warehouse.objects.filter(filters).distinct().order_by(
        '-seller_links__is_default',
        '-seller_links__priority',
        'name'
    )


def get_default_warehouse(business):
    """
    Get the default warehouse for a seller.

    Args:
        business: Business instance

    Returns:
        Warehouse instance or None

    Example:
        >>> default_wh = get_default_warehouse(business)
        >>> if default_wh:
        ...     print(f"Default: {default_wh.name}")
    """
    from warehouse.models import SellerWarehouseLink

    link = SellerWarehouseLink.objects.filter(
        business=business,
        is_default=True,
        is_active=True
    ).select_related('warehouse').first()

    return link.warehouse if link else None


def get_recommended_warehouse_location(order, user=None):
    """
    Auto-select the best warehouse location for an order based on multiple criteria.

    This function implements a multi-strategy approach:
    1. Zone Match: Prefer locations serving the customer's delivery zone
    2. GPS Distance: Prefer nearest location to customer
    3. Link Priority: Use seller's warehouse link priorities
    4. Default Warehouse: Fall back to seller's default warehouse
    5. Default Location: Use warehouse's default location

    Args:
        order: Order instance with customer location data
        user: Optional user for logging (default: None)

    Returns:
        WarehouseLocation instance or None if no suitable location found

    Example:
        >>> from orders.models import Order
        >>> order = Order.objects.get(order_number='ORD-12345')
        >>> location = get_recommended_warehouse_location(order)
        >>> if location:
        ...     print(f"Recommended: {location.warehouse.name} / {location.name}")
        ... else:
        ...     print("No warehouse location available")

    Selection Logic:
        Priority 1: Zone Match
            - Customer zone matches warehouse location zone_number
            - Highest priority match

        Priority 2: GPS Distance
            - Calculate distance from customer to each warehouse location
            - Prefer nearest location
            - Requires GPS coordinates for both customer and locations

        Priority 3: Link Priority
            - Use SellerWarehouseLink.priority field
            - Higher values preferred
            - Use link's default_location if set

        Priority 4: Default Warehouse
            - Seller's default warehouse (is_default=True)
            - Use its default location or any active location

        Priority 5: Any Active Location
            - Last resort: any active location from linked warehouses
    """
    from warehouse.models import WarehouseLocation, SellerWarehouseLink

    if not order:
        logger.warning("get_recommended_warehouse_location called with no order")
        return None

    if not hasattr(order, 'business') or not order.business:
        logger.warning(f"Order {order.order_number} has no business associated")
        return None

    # Get seller's linked warehouses
    links = SellerWarehouseLink.objects.filter(
        business=order.business,
        is_active=True,
        warehouse__is_active=True
    ).select_related('warehouse', 'default_location').order_by(
        '-is_default', '-priority'
    )

    if not links.exists():
        logger.warning(
            f"No active warehouse links found for business {order.business.business_name}"
        )
        return None

    # Extract order location data
    customer_zone = getattr(order, 'dl_zone', None)
    customer_lat = getattr(order, 'customer_latitude', None)
    customer_lon = getattr(order, 'customer_longitude', None)

    logger.info(
        f"Finding warehouse location for order {order.order_number} | "
        f"Business: {order.business.business_name} | "
        f"Zone: {customer_zone} | "
        f"GPS: {customer_lat}, {customer_lon}"
    )

    # Strategy 1: Zone Match
    if customer_zone:
        logger.info(f"Strategy 1: Searching for zone match (zone {customer_zone})")

        for link in links:
            location = link.warehouse.pickup_locations.filter(
                zone_number=customer_zone,
                is_active=True
            ).first()

            if location:
                logger.info(
                    f"✓ Zone match found: {location.warehouse.name} / {location.name} "
                    f"(Zone {location.zone_number})"
                )
                return location

        logger.info("✗ No zone match found")

    # Strategy 2: GPS Distance
    if customer_lat and customer_lon:
        logger.info("Strategy 2: Searching by GPS distance")

        nearest_location = None
        min_distance = float('inf')

        for link in links:
            for location in link.warehouse.pickup_locations.filter(is_active=True):
                if location.latitude and location.longitude:
                    try:
                        distance = calculate_distance(
                            float(customer_lat), float(customer_lon),
                            float(location.latitude), float(location.longitude)
                        )

                        logger.debug(
                            f"  Distance to {location.warehouse.name} / {location.name}: "
                            f"{distance:.2f} km"
                        )

                        if distance < min_distance:
                            min_distance = distance
                            nearest_location = location
                    except (ValueError, TypeError) as e:
                        logger.debug(f"  Error calculating distance: {e}")

        if nearest_location:
            logger.info(
                f"✓ Nearest location found: {nearest_location.warehouse.name} / "
                f"{nearest_location.name} ({min_distance:.2f} km away)"
            )
            return nearest_location

        logger.info("✗ No location with GPS coordinates found")

    # Strategy 3: Link Priority (use highest priority link's default location)
    logger.info("Strategy 3: Using link priority")

    highest_priority_link = links.first()  # Already ordered by priority
    if highest_priority_link.default_location and highest_priority_link.default_location.is_active:
        logger.info(
            f"✓ Using highest priority link's default location: "
            f"{highest_priority_link.warehouse.name} / "
            f"{highest_priority_link.default_location.name} "
            f"(Priority: {highest_priority_link.priority})"
        )
        return highest_priority_link.default_location

    # Strategy 4: Default Warehouse's Default Location
    logger.info("Strategy 4: Searching for default warehouse")

    default_link = links.filter(is_default=True).first()
    if default_link:
        # Try link's default location first
        if default_link.default_location and default_link.default_location.is_active:
            logger.info(
                f"✓ Using default warehouse's link location: "
                f"{default_link.warehouse.name} / {default_link.default_location.name}"
            )
            return default_link.default_location

        # Try warehouse's default location
        default_loc = default_link.warehouse.pickup_locations.filter(
            is_default=True,
            is_active=True
        ).first()

        if default_loc:
            logger.info(
                f"✓ Using default warehouse's default location: "
                f"{default_loc.warehouse.name} / {default_loc.name}"
            )
            return default_loc

    # Strategy 5: Any Active Location (last resort)
    logger.info("Strategy 5: Searching for any active location")

    for link in links:
        location = link.warehouse.pickup_locations.filter(is_active=True).first()
        if location:
            logger.info(
                f"✓ Using first available location: "
                f"{location.warehouse.name} / {location.name}"
            )
            return location

    # No location found
    logger.warning(
        f"✗ No suitable warehouse location found for order {order.order_number}"
    )
    return None


def get_warehouse_locations_for_business(business, customer_zone=None,
                                         customer_lat=None, customer_lon=None):
    """
    Get all available warehouse locations for a business, optionally sorted by relevance.

    Args:
        business: Business instance
        customer_zone: Optional customer zone for sorting (default: None)
        customer_lat: Optional customer latitude for distance sorting (default: None)
        customer_lon: Optional customer longitude for distance sorting (default: None)

    Returns:
        List of tuples: [(WarehouseLocation, distance_km, is_zone_match), ...]
        Sorted by: zone match first, then distance (if GPS provided), then default, then name

    Example:
        >>> locations = get_warehouse_locations_for_business(
        ...     business,
        ...     customer_zone=44,
        ...     customer_lat=26.2285,
        ...     customer_lon=50.5860
        ... )
        >>> for location, distance, is_zone_match in locations:
        ...     zone_tag = "✓ ZONE MATCH" if is_zone_match else ""
        ...     dist_tag = f"{distance:.1f} km" if distance else ""
        ...     print(f"{location.warehouse.name} / {location.name} {dist_tag} {zone_tag}")
    """
    from warehouse.models import WarehouseLocation, SellerWarehouseLink

    # Get all active warehouse locations for this business
    linked_warehouse_ids = SellerWarehouseLink.objects.filter(
        business=business,
        is_active=True
    ).values_list('warehouse_id', flat=True)

    locations = WarehouseLocation.objects.filter(
        warehouse_id__in=linked_warehouse_ids,
        warehouse__is_active=True,
        is_active=True
    ).select_related('warehouse')

    # Build result list with metadata
    results = []
    for location in locations:
        distance = None
        is_zone_match = False

        # Check zone match
        if customer_zone and location.zone_number == customer_zone:
            is_zone_match = True

        # Calculate distance
        if (customer_lat and customer_lon and
            location.latitude and location.longitude):
            try:
                distance = calculate_distance(
                    float(customer_lat), float(customer_lon),
                    float(location.latitude), float(location.longitude)
                )
            except (ValueError, TypeError):
                distance = None

        results.append((location, distance, is_zone_match))

    # Sort: zone match first, then distance, then default, then name
    results.sort(key=lambda x: (
        not x[2],  # Zone match first (False < True, so invert)
        x[1] if x[1] is not None else float('inf'),  # Distance (nearest first)
        not x[0].is_default,  # Default first
        x[0].warehouse.name,
        x[0].name
    ))

    return results
