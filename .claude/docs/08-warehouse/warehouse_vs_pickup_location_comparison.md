# Warehouse Location vs Pickup Location Field Comparison

This document compares the fields between `WarehouseLocation` (warehouse app) and `PickupLocation` (business app) models.

## Model Purpose

### PickupLocation (business app)
- Represents physical locations where businesses receive/store inventory
- Directly linked to a Business
- Can be marked as fulfillment center (if linked to warehouse)
- Used for order pickup coordination

### WarehouseLocation (warehouse app)
- Represents specific pickup/dispatch points within a fulfillment center
- Linked to a Warehouse (not directly to Business)
- Multiple locations per warehouse (e.g., "North Gate", "Main Entrance")
- Used for driver pickup instructions

---

## Field Comparison Table

| Field | PickupLocation | WarehouseLocation | Notes |
|-------|----------------|-------------------|-------|
| **Identity** |
| Primary Key | Auto-increment ID | Auto-increment ID | Both use default Django PK |
| Name/Title | `pickup_location_title` (CharField, 100) | `name` (CharField, 200) | Different field names |
| Code | ❌ None | `code` (CharField, 50, indexed) | WH has unique code per warehouse |
| **Location Details** |
| Address/Locality | `locality` (CharField, 100) | `address` (TextField) | Different granularity |
| Zone | `pickup_zone_no` (PositiveIntegerField) | `zone_number` (IntegerField) | Similar purpose, different names |
| Street | `pickup_street_no` (PositiveIntegerField) | ❌ None | Pickup has more address detail |
| Building | `pickup_building_no` (PositiveIntegerField) | ❌ None | Pickup has building number |
| **GPS Coordinates** |
| Latitude | `pickup_lat` (Decimal 19,15) | `latitude` (Decimal 9,6) | Both have GPS, different precision |
| Longitude | `pickup_lon` (Decimal 19,15) | `longitude` (Decimal 9,6) | Pickup has higher precision |
| **Status & Flags** |
| Status | `pickup_status` (choices: active/inactive/pending/suspended) | `is_active` (Boolean) | Different status systems |
| Default Flag | ❌ None | `is_default` (Boolean) | WH can mark default location |
| Fulfillment Flag | `is_fulfilment_center` (Boolean) | N/A (inherent to warehouse) | Pickup can be marked as FC |
| **Relationships** |
| Parent Entity | `business` (FK to Business) | `warehouse` (FK to Warehouse) | Different parent models |
| Warehouse Link | `warehouse` (FK to Warehouse, nullable) | Built-in parent relationship | Pickup optionally links to WH |
| **Operating Info** |
| Hours | ❌ None | `operating_hours` (TextField) | WH has operating hours |
| Notes | ❌ None | `notes` (TextField) | WH has driver instructions |
| **Timestamps** |
| Created | `created_at` (auto_now_add) | `created_at` (auto_now_add) | Both have |
| Updated | `updated_at` (auto_now) | `updated_at` (auto_now) | Both have |

---

## SellerWarehouseLink Model

Links businesses to warehouses (many-to-many relationship):

| Field | Type | Purpose |
|-------|------|---------|
| `business` | FK to Business | The seller using this warehouse |
| `warehouse` | FK to Warehouse | The fulfillment center serving this seller |
| `default_location` | FK to WarehouseLocation | **Default pickup point for this seller** |
| `is_default` | Boolean | Is this the default warehouse for this seller? |
| `is_active` | Boolean | Is this link active? |
| `priority` | Integer | Selection priority (higher = preferred) |
| `linked_by` | FK to User | Staff who created this link |
| `linked_at` | DateTime | When link was created |
| `notes` | TextField | Special notes about the relationship |

**Important:** The field is called `default_location`, NOT `warehouse_location`!

---

## Key Differences Summary

1. **Naming Convention:**
   - PickupLocation uses `pickup_` prefix (e.g., `pickup_location_title`, `pickup_lat`)
   - WarehouseLocation uses plain names (e.g., `name`, `latitude`)

2. **Address Granularity:**
   - PickupLocation: More detailed (locality, street_no, building_no, zone_no)
   - WarehouseLocation: Simpler (address as text, zone_number)

3. **GPS Precision:**
   - PickupLocation: 19 digits, 15 decimals (very high precision)
   - WarehouseLocation: 9 digits, 6 decimals (standard GPS precision)

4. **Status System:**
   - PickupLocation: 4-choice CharField (active/inactive/pending/suspended)
   - WarehouseLocation: Simple Boolean (is_active)

5. **Operating Details:**
   - WarehouseLocation has operating_hours and notes for drivers
   - PickupLocation does not have these fields

6. **Unique Constraints:**
   - WarehouseLocation: unique_together = ['warehouse', 'code']
   - PickupLocation: No unique constraints

---

## Usage in Fulfillment Service

When a business activates fulfillment service:

1. **SellerWarehouseLink** is created linking:
   - `business` → The Business model instance
   - `warehouse` → The Warehouse instance
   - `default_location` → The WarehouseLocation instance (NOT warehouse_location!)

2. **PickupLocation** can optionally be linked:
   - Set `pickup.warehouse = warehouse` to mark it as fulfillment center
   - Set `pickup.is_fulfilment_center = True`

3. **Integration Points:**
   - Orders can be fulfilled from warehouse inventory
   - Drivers pick up from the `default_location` within the warehouse
   - Business's regular pickup locations remain for non-fulfillment orders

---

## Code Fix Applied (2026-02-14)

**Bug:** In `workforce/views.py`, the fulfillment section handler was using wrong field name:
```python
# WRONG (caused the error)
'warehouse_location': warehouse_location

# CORRECT
'default_location': warehouse_location
```

The model field is `default_location` (FK to WarehouseLocation), not `warehouse_location`.

This was causing the "An error occurred while updating business license" error when trying to activate fulfillment service and link a warehouse.
