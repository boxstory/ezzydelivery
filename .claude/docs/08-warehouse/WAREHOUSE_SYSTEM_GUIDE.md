# Warehouse & Fulfillment Center System Guide

## Overview

This system implements a **warehouse-first fulfillment architecture** where fulfillment centers are independent entities managed by staff, NOT owned by sellers.

---

## Core Architecture

### Key Principles

1. **Warehouses are Independent**
   - Fulfillment centers are NOT owned by sellers
   - Staff creates and manages all warehouses
   - Warehouses are reusable across multiple sellers

2. **Flexible Many-to-Many Relationships**
   - One seller can connect to multiple warehouses
   - One warehouse can serve multiple sellers
   - Links can be created/removed by staff at any time

3. **Customer-Facing Abstraction**
   - Orders only show "Fulfillment Store" name
   - Warehouse details are internal-only
   - No customer visibility of warehouse infrastructure

4. **Location-Based Selection**
   - Each warehouse has multiple physical locations
   - Staff selects warehouse location during task assignment
   - Selection based on customer location and stock availability

---

## Models

### 1. Warehouse (Fulfillment Center)

**Purpose:** Independent fulfillment centers managed by staff

**Key Fields:**
- `name`: Fulfillment center name
- `code`: Unique warehouse code (auto-generated: WH-FC-XXXXXXXX)
- `description`: Warehouse details
- `address`, `city`, `state`, `postal_code`, `country`: Location details
- `latitude`, `longitude`: GPS coordinates for distance-based selection
- `phone`, `email`: Contact information
- `is_active`: Operational status
- `is_default`: Default fulfillment center flag
- `manager`: Staff member managing the warehouse
- `created_by`: Staff who created the warehouse

**Related Names:**
- `pickup_locations`: WarehouseLocation objects
- `storage_locations`: StorageLocation objects (internal bins/racks)
- `seller_links`: SellerWarehouseLink objects

**Admin Access:**
- View: Staff only
- Create/Edit: Staff only
- Django Admin: `/admin/warehouse/warehouse/`

---

### 2. WarehouseLocation

**Purpose:** Physical pickup/dispatch locations within a fulfillment center

**Key Fields:**
- `warehouse`: Parent fulfillment center
- `name`: Location name (e.g., "North Gate", "Main Entrance")
- `code`: Location code (e.g., "NG", "ME")
- `address`: Specific location address or directions
- `zone_number`: Primary delivery zone served
- `latitude`, `longitude`: GPS coordinates
- `is_active`: Operational status
- `is_default`: Default location for this warehouse
- `operating_hours`: Operating schedule
- `notes`: Special instructions for drivers

**Use Cases:**
- Multiple gates/entrances at large warehouse
- Different dispatch points for different zones
- Separate pickup areas for different order types

**Admin Access:**
- View: Staff only
- Create/Edit: Staff only
- Django Admin: `/admin/warehouse/warehouselocation/`

---

### 3. SellerWarehouseLink

**Purpose:** Links sellers to fulfillment centers (many-to-many relationship)

**Key Fields:**
- `business`: Seller/business
- `warehouse`: Fulfillment center
- `default_location`: Default pickup location at this warehouse
- `is_default`: Is this the default warehouse for this seller?
- `is_active`: Is this link active?
- `priority`: Selection priority (higher = preferred for auto-selection)
- `notes`: Special relationship notes
- `linked_by`: Staff who created the link

**Business Rules:**
- One seller can have multiple warehouse links
- Only ONE link can be `is_default=True` per seller
- `default_location` must belong to the selected `warehouse`
- Auto-selection uses `priority` when multiple warehouses available

**Admin Access:**
- View: Staff only
- Create/Edit: Staff only
- Django Admin: `/admin/warehouse/sellerwarehouselink/`

---

## Workflows

### Workflow 1: Create Fulfillment Center

**Who:** Staff only

**Steps:**
1. Go to: Django Admin → Warehouse → Fulfillment Centers → Add
2. Fill in warehouse details:
   - Name (e.g., "Central Fulfillment Center")
   - Description
   - Address and GPS coordinates
   - Contact information
   - Set manager (staff user)
   - Mark as active
   - Optionally mark as default
3. Save

**Result:**
- New fulfillment center created
- Code auto-generated (WH-FC-XXXXXXXX)
- Ready to add locations

---

### Workflow 2: Add Warehouse Locations

**Who:** Staff only

**Steps:**
1. Go to: Django Admin → Warehouse → Warehouse Locations → Add
2. Select parent warehouse
3. Fill in location details:
   - Name (e.g., "North Gate")
   - Code (e.g., "NG")
   - Address and GPS coordinates
   - Zone number (optional)
   - Operating hours
   - Driver instructions
4. Mark as active
5. Optionally mark as default for this warehouse
6. Save

**Result:**
- New location added to warehouse
- Available for delivery task assignment

---

### Workflow 3: Link Seller to Warehouse

**Who:** Staff only

**Steps:**
1. Go to: Django Admin → Warehouse → Seller Warehouse Links → Add
2. Select business (seller)
3. Select warehouse
4. Select default location at that warehouse
5. Set priority (0-100, higher = preferred)
6. Mark as active
7. Optionally mark as default warehouse for this seller
8. Add any notes
9. Save

**Result:**
- Seller can now use this warehouse for fulfillment
- Orders from this seller can be fulfilled from this warehouse

---

### Workflow 4: Order Creation (Seller View)

**Who:** Seller/Business user

**What They See:**
- Pickup location dropdown shows only: **"Fulfillment Store"**
- No warehouse or location details visible
- No warehouse selection required

**Backend Behavior:**
- Order is linked to the seller's "Fulfillment Store" PickupLocation
- Actual warehouse assignment happens during delivery task assignment
- Customer never sees warehouse information

---

### Workflow 5: Delivery Task Assignment (Staff View)

**Who:** Staff/Workforce user

**Steps:**
1. View pending order
2. System shows:
   - Customer delivery location (zone, address, GPS)
   - Seller linked warehouses
3. Staff selects warehouse location:
   - Manual selection: Choose from dropdown
   - Auto-selection: System suggests nearest based on:
     - Customer GPS location
     - Warehouse location GPS
     - Zone matching
     - Seller's default warehouse
     - Link priority
4. Assign driver
5. Create delivery task

**Result:**
- Delivery task assigned to specific warehouse location
- Driver knows where to pick up order
- Customer never sees warehouse details

---

## Auto-Selection Logic

### Priority Order:

1. **Zone Match**
   - If customer zone matches warehouse location zone_number
   - Highest priority

2. **GPS Distance**
   - Calculate distance from customer to each warehouse location
   - Prefer nearest location

3. **Link Priority**
   - Use SellerWarehouseLink.priority field
   - Higher values preferred

4. **Default Warehouse**
   - Seller's default warehouse (is_default=True)
   - Fallback option

5. **Default Location**
   - Warehouse's default location (is_default=True)
   - Final fallback

### Implementation:

```python
def get_recommended_warehouse_location(order):
    """
    Auto-select warehouse location based on customer location.
    Returns WarehouseLocation or None.
    """
    from warehouse.models import WarehouseLocation, SellerWarehouseLink
    from delivery.models import ZoneName
    from math import radians, cos, sin, asin, sqrt

    # Get seller's linked warehouses
    links = SellerWarehouseLink.objects.filter(
        business=order.business,
        is_active=True
    ).select_related('warehouse', 'default_location')

    if not links.exists():
        return None

    customer_zone = order.dl_zone
    customer_lat = order.customer_latitude
    customer_lon = order.customer_longitude

    # Strategy 1: Zone Match
    if customer_zone:
        for link in links:
            location = link.warehouse.pickup_locations.filter(
                zone_number=customer_zone,
                is_active=True
            ).first()
            if location:
                return location

    # Strategy 2: GPS Distance (if customer has GPS)
    if customer_lat and customer_lon:
        def haversine_distance(lat1, lon1, lat2, lon2):
            """Calculate distance in km between two GPS points"""
            R = 6371  # Earth radius in km
            lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
            dlat = lat2 - lat1
            dlon = lon2 - lon1
            a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
            return R * 2 * asin(sqrt(a))

        nearest_location = None
        min_distance = float('inf')

        for link in links:
            for location in link.warehouse.pickup_locations.filter(is_active=True):
                if location.latitude and location.longitude:
                    distance = haversine_distance(
                        float(customer_lat), float(customer_lon),
                        float(location.latitude), float(location.longitude)
                    )
                    if distance < min_distance:
                        min_distance = distance
                        nearest_location = location

        if nearest_location:
            return nearest_location

    # Strategy 3: Link Priority
    highest_priority_link = links.order_by('-priority').first()
    if highest_priority_link.default_location:
        return highest_priority_link.default_location

    # Strategy 4: Default Warehouse
    default_link = links.filter(is_default=True).first()
    if default_link:
        if default_link.default_location:
            return default_link.default_location
        # Get default location of default warehouse
        default_loc = default_link.warehouse.pickup_locations.filter(
            is_default=True,
            is_active=True
        ).first()
        if default_loc:
            return default_loc

    # Strategy 5: Any active location
    for link in links:
        location = link.warehouse.pickup_locations.filter(is_active=True).first()
        if location:
            return location

    return None
```

---

## Migration Path

### Breaking Changes:

**Old Model:**
```python
class Warehouse(models.Model):
    business = models.ForeignKey(Business, ...)  # REMOVED
    pickup_location = models.ForeignKey(PickupLocation, ...)  # REMOVED
```

**New Model:**
```python
class Warehouse(models.Model):
    # No business field - independent entity
    # Many-to-many via SellerWarehouseLink
    is_default = models.BooleanField(...)  # ADDED
    manager = models.ForeignKey(User, ...)  # ADDED
    latitude = models.DecimalField(...)  # ADDED
    longitude = models.DecimalField(...)  # ADDED
    # ... many more fields
```

### Migration Steps:

1. **Create New Models**
   ```bash
   python manage.py makemigrations warehouse
   ```

2. **Review Migration**
   - Check for data loss warnings
   - Existing Warehouse records will need manual data migration

3. **Data Migration Script** (if existing warehouses)
   ```python
   # Create script: migrate_warehouses.py
   from warehouse.models import Warehouse, WarehouseLocation, SellerWarehouseLink
   from business.models import Business

   # For each old warehouse:
   for old_wh in Warehouse.objects.all():
       # Create new independent warehouse
       # Create SellerWarehouseLink for the old business
       # Create WarehouseLocation if pickup_location existed
   ```

4. **Run Migration**
   ```bash
   python manage.py migrate warehouse
   ```

5. **Verify**
   - Check Django admin
   - Verify all models accessible
   - Test CRUD operations

---

## API Changes (Future)

### Old Endpoint:
```
GET /api/business/{id}/warehouses/
```

### New Endpoints:
```
GET /api/warehouses/                     # Staff only - list all
GET /api/warehouses/{id}/                # Staff only - detail
POST /api/warehouses/                    # Staff only - create
GET /api/warehouses/{id}/locations/      # Staff only - list locations
POST /api/seller-warehouse-links/        # Staff only - create link
GET /api/orders/{id}/recommended-warehouse/  # Auto-select logic
```

---

## Testing Checklist

### Model Tests:
- [ ] Create warehouse without business (should succeed)
- [ ] Auto-generate warehouse code
- [ ] Create multiple locations per warehouse
- [ ] Link seller to warehouse
- [ ] Link seller to multiple warehouses
- [ ] Set default warehouse for seller
- [ ] Validate default_location belongs to warehouse
- [ ] Ensure only one default per seller

### Admin Tests:
- [ ] Staff can create warehouse
- [ ] Staff can create warehouse location
- [ ] Staff can create seller-warehouse link
- [ ] Forms validate correctly
- [ ] GPS coordinates accept decimal values
- [ ] Auto-selection logic works

### Integration Tests:
- [ ] Order creation shows "Fulfillment Store"
- [ ] Delivery task assignment shows warehouse locations
- [ ] Auto-selection recommends correct location
- [ ] Manual override works
- [ ] Driver receives correct pickup location

---

## FAQ

### Q: Can sellers create warehouses?
**A:** No. Warehouses are staff-only. Sellers can only be linked to existing warehouses by staff.

### Q: Do customers see warehouse information?
**A:** No. Customers only see "Fulfillment Store" as the pickup location. Warehouse details are internal.

### Q: Can a seller have multiple warehouses?
**A:** Yes. Staff can link a seller to as many warehouses as needed. One should be marked as default.

### Q: How does the system choose which warehouse to use?
**A:** During delivery task assignment, staff selects the warehouse location. The system can auto-suggest based on customer location, zone, and link priority.

### Q: What if a seller has no linked warehouses?
**A:** Orders can still be created, but delivery task assignment will require staff to manually link a warehouse first.

### Q: Can warehouse locations have different operating hours?
**A:** Yes. Each WarehouseLocation has an `operating_hours` field for this purpose.

---

## Troubleshooting

### Issue: "Fulfillment Store" not showing in order form
**Solution:**
1. Check if business has fulfillment_service_enabled=True
2. Verify "Fulfillment Store" PickupLocation exists for business
3. Check pickup_location status is 'active'

### Issue: No warehouse locations available during task assignment
**Solution:**
1. Verify seller has SellerWarehouseLink records
2. Check links are is_active=True
3. Verify warehouses have is_active=True
4. Ensure warehouse has active WarehouseLocation records

### Issue: Auto-selection not working
**Solution:**
1. Check customer has GPS coordinates (latitude/longitude)
2. Verify warehouse locations have GPS coordinates
3. Check zone_number matches
4. Verify link priority is set correctly
5. Ensure at least one link has is_default=True

---

## Next Steps

1. ✅ Models created
2. ✅ Admin interface configured
3. ✅ Forms created
4. ⏳ Create migrations
5. ⏳ Create staff management views
6. ⏳ Update delivery task assignment
7. ⏳ Implement auto-selection logic
8. ⏳ Add staff dashboard
9. ⏳ Create API endpoints (if needed)
10. ⏳ Write tests

---

## Related Files

### Models:
- `warehouse/models.py` (lines 114-346)

### Admin:
- `warehouse/admin.py` (lines 7-77)

### Forms:
- `warehouse/forms.py` (lines 45-206)

### Views (To be created):
- `warehouse/views.py`

### URLs (To be created):
- `warehouse/urls.py`

### Templates (To be created):
- `warehouse/templates/warehouse/warehouse_list.html`
- `warehouse/templates/warehouse/warehouse_detail.html`
- `warehouse/templates/warehouse/warehouse_form.html`
- `warehouse/templates/warehouse/location_form.html`
- `warehouse/templates/warehouse/seller_link_form.html`

---

## Support

For questions or issues, contact the development team or check the Django admin logs.
