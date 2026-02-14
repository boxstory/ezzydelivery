# Fulfillment Service Workflow

This document explains how the fulfillment service integration works in EzzyDelivery.

## Overview

The fulfillment service allows businesses to use EzzyDelivery's warehouse for inventory storage and order fulfillment, instead of shipping from their own stores.

## Key Models

### 1. Business (business app)
- `fulfillment_service_enabled` (Boolean) - Whether business can use fulfillment
- `fulfillment_service_status` (CharField) - Current status:
  - `none` - Not requested
  - `requested` - Requested by business
  - `active` - Active and warehouse linked
- `fulfillment_activated_at` (DateTime) - When first activated

### 2. SellerWarehouseLink (warehouse app)
Links a business to a warehouse for fulfillment:
- `business` (FK to Business) - The seller
- `warehouse` (FK to Warehouse) - The fulfillment center
- `default_location` (FK to WarehouseLocation) - Default pickup point within warehouse
- `is_default` (Boolean) - Is this the default warehouse for this seller?
- `is_active` (Boolean) - Is this link active?
- `linked_by` (FK to User) - Staff who created the link

**IMPORTANT:** The field is `default_location`, NOT `warehouse_location`!

### 3. PickupLocation (business app)
Physical locations for order pickup:
- `business` (FK to Business)
- `pickup_location_title` (CharField) - Location name
- `locality` (CharField) - Address
- `is_fulfilment_center` (Boolean) - Is this a warehouse fulfillment center?
- `warehouse` (FK to Warehouse, nullable) - Linked warehouse if fulfillment center
- `pickup_zone_no` (Integer) - Zone number
- `pickup_lat`, `pickup_lon` (Decimal) - GPS coordinates

## Activation Workflow

### Step 1: Business Requests Fulfillment
- Business owner goes to business dashboard
- Requests fulfillment service
- Status changes to `requested`

### Step 2: Workforce Staff Approves & Links Warehouse
On the business license detail page (`/workforce/documents/business-licenses/{id}/`):

1. Staff clicks **Edit** on the Fulfillment Service panel
2. Selects **Active** from the status dropdown
3. Warehouse locations dropdown appears (loaded via AJAX from `/workforce/api/warehouse-locations/`)
4. Staff selects a warehouse location (e.g., "Ezzy Store Doha 01 - Main Entrance")
5. Clicks **Save & Link Warehouse**

### Step 3: Backend Processing (`workforce/views.py`)

When the form is submitted with `section=fulfillment`:

```python
# 1. Update business status
business.fulfillment_service_status = 'active'
business.fulfillment_service_enabled = True
if not business.fulfillment_activated_at:
    business.fulfillment_activated_at = timezone.now()
business.save()

# 2. Create/update SellerWarehouseLink
link, created = SellerWarehouseLink.objects.get_or_create(
    business=business,
    warehouse=warehouse_location.warehouse,
    defaults={
        'default_location': warehouse_location,  # The specific pickup point
        'is_default': True,
        'linked_by': request.user,
    }
)

# 3. Auto-create fulfillment center PickupLocation
pickup_location, pickup_created = PickupLocation.objects.update_or_create(
    business=business,
    warehouse=warehouse_location.warehouse,
    defaults={
        'pickup_location_title': f"{warehouse.name} - Fulfillment",
        'locality': warehouse_location.address or warehouse.city,
        'is_fulfilment_center': True,
        'pickup_status': 'active',
        'pickup_zone_no': warehouse_location.zone_number,
        'pickup_lat': warehouse_location.latitude,
        'pickup_lon': warehouse_location.longitude,
    }
)
```

### Step 4: Result

After activation:
- Business has `fulfillment_service_status = 'active'`
- `SellerWarehouseLink` created linking business to warehouse
- **NEW:** A PickupLocation is created with:
  - Name: "{Warehouse Name} - Fulfillment" (e.g., "Ezzy Store Doha 01 - Fulfillment")
  - `is_fulfilment_center = True`
  - `warehouse` linked to the fulfillment warehouse
  - GPS coordinates from warehouse location

## Pickup Location Display

### Business Dashboard - Add Order Page

The business now sees **2 pickup locations** in dropdowns:

1. **Regular store** (e.g., "Bin Al Thani Point - Main")
   - `is_fulfilment_center = False`
   - `warehouse = None`

2. **Fulfillment center** (e.g., "Ezzy Store Doha 01 - Fulfillment")
   - `is_fulfilment_center = True`
   - `warehouse = Ezzy Store Doha 01`

### Ordering

Pickup locations are **always** ordered by:
```python
.order_by('-is_fulfilment_center', 'pickup_location_title')
```

This ensures fulfillment centers appear **first** in all dropdowns.

## Order Creation Flow

### When Business Creates Order

1. Business goes to `/orders/add_order/`
2. Selects pickup location from dropdown
3. If they select the **fulfillment center**:
   - Order will be fulfilled from warehouse inventory
   - Driver picks up from the warehouse location
   - `order.pickup_location.is_fulfilment_center == True`

4. If they select their **regular store**:
   - Order fulfilled from their own store
   - Driver picks up from business location
   - `order.pickup_location.is_fulfilment_center == False`

## Workforce Staff View

On the business license detail page, staff can see:

- **Fulfillment Service Status**: Active/Requested/None
- **Linked Warehouse**: Display showing:
  - Warehouse name (e.g., "Ezzy Store Doha 01")
  - Location name (e.g., "Main Entrance")
  - Warehouse code / Location code (e.g., "WH-EZZY-DH01 / ME01")

## Template Files

### Workforce Templates
- `workforce/templates/workforce/business_license_detail.html` - Fulfillment panel with edit/display
- `workforce/templates/workforce/workforce_pickup_location_add.html` - Warehouse linking page (legacy)

### Business Templates
- `orders/templates/orders/order_add.html` - Add order form with pickup location dropdown
- `business/templates/business/parts/pickup_location_add.html` - Add regular pickup location

## API Endpoints

### Get Warehouse Locations (AJAX)
```
GET /workforce/api/warehouse-locations/
```

Returns JSON with all active warehouse locations:
```json
{
  "success": true,
  "locations": [
    {
      "id": 1,
      "warehouse_name": "Ezzy Store Doha 01",
      "name": "Main Entrance",
      "code": "ME01",
      "full_code": "WH-EZZY-DH01-ME01",
      "city": "Doha"
    }
  ]
}
```

## Key Files Modified (2026-02-14)

1. **workforce/views.py**
   - Fixed `SellerWarehouseLink` field name (`warehouse_location` → `default_location`)
   - Added auto-creation of fulfillment center PickupLocation
   - Added context data for linked warehouse display

2. **workforce/templates/workforce/business_license_detail.html**
   - Split Fulfillment Service into separate panel
   - Added dynamic warehouse dropdown
   - Added display of linked warehouse info
   - Created dedicated JavaScript form handler

3. **orders/templates/orders/order_add.html**
   - Fixed hardcoded "Ezzy Fulfillment" in JavaScript
   - Now properly lists all pickup locations

4. **docs/warehouse_vs_pickup_location_comparison.md** (NEW)
   - Complete field comparison between models
   - Documents SellerWarehouseLink structure

## Common Issues & Solutions

### Issue: Fulfillment center not showing in pickup dropdown
**Cause:** No PickupLocation with `is_fulfilment_center=True` created
**Fix:** The code now auto-creates this when warehouse is linked

### Issue: "An error occurred while updating business license"
**Cause:** Used wrong field name `warehouse_location` instead of `default_location`
**Fix:** Updated to use correct field name in all places

### Issue: Template shows `link.warehouse_location.name`
**Cause:** Wrong field name in template
**Fix:** Change to `link.default_location.name`

## Testing Checklist

- [ ] Activate fulfillment service for a business
- [ ] Verify SellerWarehouseLink created
- [ ] Verify PickupLocation created with `is_fulfilment_center=True`
- [ ] Check pickup dropdown shows fulfillment center first
- [ ] Create order using fulfillment center
- [ ] Verify order.pickup_location links to warehouse
- [ ] Check business license detail shows linked warehouse info

## Database Query Examples

```python
# Get all businesses using fulfillment
Business.objects.filter(fulfillment_service_status='active')

# Get linked warehouses for a business
SellerWarehouseLink.objects.filter(business=business, is_active=True)

# Get fulfillment center pickup locations
PickupLocation.objects.filter(is_fulfilment_center=True, business=business)

# Get orders fulfilled from warehouse
Order.objects.filter(
    pickup_location__is_fulfilment_center=True,
    business=business
)
```

## Future Enhancements

1. **Multiple Warehouses**: Business can link to multiple warehouses
2. **Warehouse Inventory**: Track which products are in which warehouse
3. **Auto-routing**: Automatically select nearest warehouse based on delivery address
4. **Warehouse Analytics**: Track fulfillment rates, inventory turnover
5. **Warehouse Transfer**: Move inventory between warehouses
