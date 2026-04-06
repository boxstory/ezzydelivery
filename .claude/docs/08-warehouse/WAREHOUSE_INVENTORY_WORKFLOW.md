# Warehouse & Inventory — Complete Workflow Documentation

> Last updated: 2026-04-01

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Data Model Reference](#2-data-model-reference)
3. [Core Workflows](#3-core-workflows)
4. [Signal-Driven Automation](#4-signal-driven-automation)
5. [View & URL Reference](#5-view--url-reference)
6. [Template & UI Structure](#6-template--ui-structure)
7. [Business Rules & Constraints](#7-business-rules--constraints)
8. [Feature Status](#8-feature-status)

---

## 1. Architecture Overview

### Design Principles

- **Warehouse-first**: Warehouses are independent entities managed by staff — NOT owned by sellers. Multiple sellers link to one warehouse via `SellerWarehouseLink`.
- **Signal-driven**: All stock operations (reserve, release, fulfill, return) are triggered automatically by order and delivery status changes via Django signals.
- **Full audit trail**: Every stock mutation creates an `InventoryTransaction` with before/after quantities.
- **Zone-based picking**: Pick lists are grouped by `(warehouse, business, zone)` for efficient batch picking.
- **HTMX SPA navigation**: Desktop sidebar uses HTMX for partial page loads without full refresh.

### System Flow Diagram

```
┌─────────────┐     ┌──────────────────┐     ┌─────────────────┐
│   BUSINESS   │────▶│ SellerWarehouse   │◀────│   WAREHOUSE     │
│   (Seller)   │     │     Link          │     │ (Fulfillment    │
└──────┬───────┘     └──────────────────┘     │    Center)      │
       │                                       └────────┬────────┘
       │                                                │
       ▼                                                ▼
┌─────────────┐                              ┌─────────────────┐
│    ORDER     │──── signal ────────────────▶│  StorageLocation │
│  (status     │                             │  (zone/aisle/    │
│   changes)   │                             │   rack/shelf/bin)│
└──────┬───────┘                             └────────┬────────┘
       │                                              │
       │ ready_to_pickup                              │
       ▼                                              ▼
┌─────────────┐     ┌──────────────┐     ┌──────────────────┐
│    STOCK     │────▶│  PICK LIST   │────▶│   PACK STATION   │
│ RESERVATION  │     │  (zone-based)│     │  (order-grouped) │
└─────────────┘     └──────────────┘     └────────┬─────────┘
                                                   │
                                                   ▼
                                         ┌─────────────────┐
                                         │    DISPATCH      │
                                         │  (driver batch)  │
                                         └────────┬────────┘
                                                   │
                                                   ▼
                                         ┌─────────────────┐
                                         │   DELIVERY       │
                                         │   TASK           │
                                         └────────┬────────┘
                                                   │
                              ┌────────────────────┼────────────────┐
                              ▼                    ▼                ▼
                        ┌──────────┐       ┌──────────┐    ┌──────────┐
                        │ DELIVERED │       │  FAILED  │    │ CANCELLED│
                        │ fulfill  │       │  return  │    │ release  │
                        │ stock    │       │  stock   │    │ stock    │
                        └──────────┘       └──────────┘    └──────────┘
```

### App Dependencies

```
warehouse ◀──── orders (Order status triggers stock operations)
warehouse ◀──── delivery (DeliveryTask status triggers fulfill/return)
warehouse ────▶ business (PickupLocation sync via SellerWarehouseLink signals)
warehouse ────▶ product (Product FK on stock levels, pick items, etc.)
warehouse ────▶ fleet (Driver FK on DispatchBatch)
```

---

## 2. Data Model Reference

### 2.1 Warehouse Management

#### `Warehouse` — Fulfillment Center
| Field | Type | Notes |
|-------|------|-------|
| `name` | CharField(200) | Display name |
| `code` | CharField(50), unique | Auto: `WH-FC-{8hex}` |
| `address`, `city`, `state`, `postal_code` | Text/Char | Location info |
| `country` | CharField(100) | Default: `'Qatar'` |
| `latitude`, `longitude` | Decimal(9,6) | GPS |
| `phone`, `email` | Char/Email | Contact |
| `total_zones` | Int | Capacity config |
| `racks_per_zone` | Int | Capacity config |
| `shelves_per_rack` | Int | Capacity config |
| `bins_per_shelf` | Int | Capacity config |
| `zone_naming_pattern` | Char(50) | Default: `'A,B,C,D'` |
| `rack/shelf/bin_naming_pattern` | Char(20) | `'numeric'` or `'alpha'` |
| `is_capacity_configured` | Bool | Set True after config |
| `is_active`, `is_default` | Bool | Operational flags |
| `manager`, `created_by` | FK→User | Staff references |

**Properties:** `total_capacity` (zones × racks × shelves × bins), `total_racks`, `total_shelves`
**Methods:** `get_zone_names()`, `generate_location_name(type, index)`

#### `WarehouseLocation` — Pickup/Dispatch Points
Physical gates/entrances for driver pickup — NOT internal storage.
| Field | Type | Notes |
|-------|------|-------|
| `warehouse` | FK→Warehouse | CASCADE |
| `name`, `code` | CharField | Unique per warehouse |
| `zone_number` | Int | Delivery zone |
| `latitude`, `longitude` | Decimal | GPS |
| `is_active`, `is_default` | Bool | |
| `operating_hours`, `notes` | Text | |

#### `SellerWarehouseLink` — Business ↔ Warehouse
| Field | Type | Notes |
|-------|------|-------|
| `business` | FK→Business | CASCADE |
| `warehouse` | FK→Warehouse | CASCADE |
| `default_location` | FK→WarehouseLocation | SET_NULL, validated to same warehouse |
| `is_default` | Bool | Auto-enforced: only one per business |
| `is_active` | Bool | |
| `priority` | Int | Higher = preferred for auto-selection |
| `linked_by` | FK→User | Staff who created |

**Signal effects:** On save → creates/updates `PickupLocation`. On delete → deactivates `PickupLocation`.

### 2.2 Storage

#### `StorageLocation` — Hierarchical Bins
Self-referential hierarchy: **zone → aisle → rack → shelf → bin**
| Field | Type | Notes |
|-------|------|-------|
| `warehouse` | FK→Warehouse | CASCADE |
| `parent` | FK→self | CASCADE, nullable |
| `name`, `code` | CharField | Code unique per warehouse |
| `barcode` | CharField, unique | Auto: `LOC-{wh_code}-{code}-{4hex}` |
| `location_type` | Choice | `zone/aisle/rack/shelf/bin` |
| `width_cm`, `length_cm`, `height_cm` | Decimal | Physical dimensions |
| `max_weight_kg` | Decimal | Weight limit |
| `is_pickable` | Bool | Only bins are pickable |
| `is_active` | Bool | |

### 2.3 Inventory Tracking

#### `StockLevel` — Quantity per Product/Warehouse/Location
| Field | Type | Notes |
|-------|------|-------|
| `product` | FK→Product | CASCADE |
| `warehouse` | FK→Warehouse | CASCADE |
| `location` | FK→StorageLocation | SET_NULL |
| `quantity_on_hand` | Int | Physical stock |
| `quantity_reserved` | Int | Reserved for pending orders |
| `quantity_incoming` | Int | Expected from POs |
| `reorder_point` | Int | Triggers low stock alert |
| `reorder_quantity` | Int | Suggested reorder amount |
| `abc_classification` | Choice | A/B/C value class |

**Properties:** `quantity_available` (on_hand − reserved), `is_low_stock`, `is_out_of_stock`
**Unique constraint:** `(product, warehouse, location)`

#### `InventoryTransaction` — Audit Trail
| Field | Type | Notes |
|-------|------|-------|
| `transaction_number` | Char, unique | Auto: `TXN-{12hex}` |
| `product` | FK→Product | PROTECT |
| `warehouse` | FK→Warehouse | PROTECT |
| `location` | FK→StorageLocation | SET_NULL |
| `transaction_type` | Choice | see below |
| `quantity` | Int | Positive=in, negative=out |
| `quantity_before`, `quantity_after` | Int | Snapshot |
| `reference_type` | Char | e.g. `'order'`, `'return_task'` |
| `reference_id` | Char | e.g. order number |
| `created_by` | FK→User | |

**Transaction types:** `receive`, `ship`, `adjust_in`, `adjust_out`, `transfer_in`, `transfer_out`, `reserve`, `unreserve`, `count`, `return`

#### `StockReservation` — Order Stock Lock
| Field | Type | Notes |
|-------|------|-------|
| `order` | FK→Order | CASCADE |
| `order_item` | FK→OrderItem | CASCADE |
| `stock_level` | FK→StockLevel | CASCADE |
| `quantity` | Int | Reserved units |
| `status` | Choice | `active/released/fulfilled/returned/cancelled` |

### 2.4 Operations

#### `PickList` — Picking Batch
Grouped by `(warehouse, business, zone)`. Multiple orders merge into one pending pick list.
| Field | Type | Notes |
|-------|------|-------|
| `pick_number` | Char, unique | Auto: `PICK-{10hex}` |
| `warehouse` | FK→Warehouse | |
| `business` | FK→Business | |
| `zone` | FK→StorageLocation | Zone-level grouping |
| `status` | Choice | `pending→assigned→in_progress→completed→packing→packed` |
| `assigned_to` | FK→User | |
| `total_items`, `picked_items` | Int | Progress tracking |

#### `PickListItem`
| Field | Type | Notes |
|-------|------|-------|
| `pick_list` | FK→PickList | |
| `order` | FK→Order | |
| `order_item` | FK→OrderItem | |
| `product` | FK→Product | |
| `location` | FK→StorageLocation | Bin to pick from |
| `quantity_to_pick`, `quantity_picked` | Int | |
| `is_picked`, `is_packed` | Bool | |

#### `DispatchBatch` — Driver Delivery Batch
| Field | Type | Notes |
|-------|------|-------|
| `batch_number` | Char, unique | Auto: `DSP-{10hex}` |
| `warehouse` | FK→Warehouse | |
| `driver` | FK→fleet.Driver | |
| `status` | Choice | `ready→assigned→handed_over→dispatched→completed` |
| `total_orders` | Int | |
| `total_cod_amount` | Decimal | |

#### `DispatchItem`
| `batch` | FK→DispatchBatch | `order` FK→Order | `pick_list` FK→PickList | `is_handed_over` Bool | `cod_amount` Decimal |

#### `ReturnTask` — Return Picked Items to Shelf
Auto-created when order cancelled after items were picked.
| Field | Type | Notes |
|-------|------|-------|
| `return_number` | Char, unique | Auto: `RTN-{10hex}` |
| `warehouse` | FK→Warehouse | |
| `order` | FK→Order | |
| `pick_list` | FK→PickList | |
| `status` | Choice | `pending→in_progress→completed` |

#### `ReturnTaskItem`
| `return_task` FK | `product` FK | `location` FK→StorageLocation | `quantity` Int | `is_returned` Bool |

#### `PutAwayTask` — Place Received Stock
Auto-created after stock receiving.
| Field | Type | Notes |
|-------|------|-------|
| `task_number` | Char, unique | Auto: `PA-{10hex}` |
| `warehouse` | FK→Warehouse | |
| `status` | Choice | `pending→assigned→in_progress→completed` |
| `priority` | Choice | `normal/high/urgent` |
| `inbound_request` | FK→InboundProductRequest | Optional link |

#### `PutAwayTaskItem`
| `product` FK | `quantity` Int | `source_location` FK | `suggested_location` FK | `actual_location` FK | `is_completed` Bool |

### 2.5 Quality & Alerts

#### `CycleCount` — Inventory Count
| `count_number` auto: `COUNT-{10hex}` | `warehouse` FK | `location` FK | `status` `scheduled→in_progress→pending_review→approved→completed` | `scheduled_date` Date | `assigned_to` FK→User |

#### `CycleCountItem`
| `product` FK | `location` FK | `system_quantity` Int | `counted_quantity` Int | `variance` Int (auto-calc) |

#### `LowStockAlert`
Auto-generated by signal when `quantity_available ≤ reorder_point`.
| `stock_level` FK | `product` FK | `warehouse` FK | `status` `active/acknowledged/resolved` |

### 2.6 Product Requests

#### `InboundProductRequest` — Send Products TO Warehouse
| `request_number` auto: `INB-{8hex}` | `business` FK | `warehouse` FK | `status` `pending→approved→completed` | `expected_delivery_date` Date |

#### `OutboundProductRequest` — Receive Products FROM Warehouse
| `request_number` auto: `OUT-{8hex}` | `business` FK | `warehouse` FK | `status` `pending→approved→completed` | `priority` `normal/urgent` |

#### `ProductRequestItem`
| `inbound_request` or `outbound_request` FK | `product` FK | `quantity_requested` Int | `quantity_fulfilled` Int |

### 2.7 Customer Returns (RMA)

#### `CustomerReturn`
| `rma_number` auto: `RMA-{10hex}` | `order` FK | `business` FK | `warehouse` FK | `status` `requested→approved→in_transit→received→inspected→resolved/rejected` |

#### `CustomerReturnItem`
| `product` FK | `quantity` Int | `condition` `good/damaged/defective/opened` | `disposition` `restock/quarantine/dispose` | `is_received`, `is_inspected`, `is_restocked` Bool |

---

## 3. Core Workflows

### 3.1 Order-to-Delivery (Fulfillment Flow)

```
ORDER STATUS: ready_to_pickup
│
├── Signal: reserve_stock_for_order()
│   ├── Find linked warehouses via SellerWarehouseLink
│   ├── For each OrderItem → find StockLevel with highest on_hand
│   ├── Create StockReservation (status=active)
│   ├── Increment quantity_reserved on StockLevel
│   ├── Log InventoryTransaction (type=reserve)
│   └── Set order.stock_reserved = True
│
└── Signal: create_pick_list_for_order()
    ├── Group items by (warehouse, business, zone)
    ├── Find or create pending PickList per group
    ├── Create PickListItem for each OrderItem
    └── Merge into existing pending pick list if possible

STAFF PICKS:
├── Assign pick list (self-assign)
├── Start picking (status → in_progress)
├── Pick each item via AJAX (mark quantity_picked, is_picked)
└── Auto-complete when all items picked (status → completed)

STAFF PACKS:
├── Pack station view (auto-transitions completed → packing)
├── Toggle pack per order via AJAX
└── When all orders packed → status = packed

STAFF DISPATCHES:
├── Create dispatch batch (select orders + driver)
├── Handover each order to driver via AJAX
├── Confirm dispatch (driver leaves warehouse)
└── DispatchBatch status → dispatched

DELIVERY COMPLETED:
│
├── Signal: fulfill_stock_reservation()
│   ├── Path A (reservations exist):
│   │   ├── Decrement quantity_on_hand and quantity_reserved
│   │   ├── Set reservation status = fulfilled
│   │   └── Log InventoryTransaction (type=ship)
│   └── Path B (no reservations — bypass flow):
│       ├── Direct deduct from StockLevel via _direct_deduct_stock()
│       └── Log InventoryTransaction (type=ship)
│
└── Check and create LowStockAlert if below reorder_point

DELIVERY FAILED:
│
└── Signal: return_stock_on_failed_delivery()
    ├── Active reservations → cancel, decrement quantity_reserved
    ├── Fulfilled reservations → return to on_hand
    └── No reservations → reverse direct deductions
```

### 3.2 Order Cancellation Flow

```
ORDER STATUS: cancelled (from any previous status)
│
├── Signal: release_stock_reservation()
│   ├── Cancel all active reservations
│   ├── Decrement quantity_reserved
│   ├── Log InventoryTransaction (type=unreserve)
│   └── Set order.stock_reserved = False
│
└── Signal: remove_pick_list_for_order()
    │
    ├── Pick list PENDING/ASSIGNED:
    │   └── Delete all PickListItems for this order
    │
    ├── Pick list IN_PROGRESS:
    │   ├── Delete unpicked items
    │   └── Create ReturnTask for already-picked items
    │
    └── Pick list COMPLETED/PACKING/PACKED:
        ├── Create ReturnTask for all picked items
        └── Delete remaining unpicked items
```

### 3.3 Stock Receiving Flow

```
STAFF receives stock (receive_stock view)
│
├── Select warehouse, product(s), quantities
├── Optional: link to InboundProductRequest
│
├── For each product:
│   ├── get_or_create StockLevel
│   ├── Increment quantity_on_hand
│   ├── Log InventoryTransaction (type=receive)
│   └── If linked to InboundRequest: update quantity_fulfilled
│
├── If InboundRequest fully fulfilled → mark completed
│
└── Auto-create PutAwayTask
    ├── Suggest locations (consolidate with existing stock)
    └── One PutAwayTaskItem per product received
```

### 3.4 Put-Away Flow

```
PutAwayTask created (auto or manual)
│
├── Staff opens detail → auto-starts (pending → in_progress)
├── For each item:
│   ├── System suggests location (bin with most existing stock of same product)
│   ├── Staff can override with dropdown
│   └── Confirm placement (AJAX):
│       ├── Deduct from source location (transfer_out)
│       ├── Add to destination location (transfer_in)
│       └── Log both InventoryTransactions
│
└── When all items placed → task status = completed
```

### 3.5 Customer Return (RMA) Flow

```
RMA created from order
│
├── Staff selects order items to return + reason
├── CustomerReturn created (status=requested)
│
├── Receive items (bulk):
│   └── Mark all items is_received=True, status → received
│
├── Inspect each item (AJAX):
│   ├── Set condition (good/damaged/defective/opened)
│   ├── Set disposition (restock/quarantine/dispose)
│   ├── If restock + good condition:
│   │   ├── Add back to StockLevel.quantity_on_hand
│   │   ├── Log InventoryTransaction (type=return)
│   │   └── Mark is_restocked=True
│   └── When all items inspected → status = resolved
│
└── End
```

### 3.6 Return Task Flow (Post-Cancellation)

```
ReturnTask created by signal (order cancelled after items picked)
│
├── Staff opens detail → auto-starts (pending → in_progress)
├── For each item:
│   └── Confirm return to shelf (AJAX):
│       ├── Add back to StockLevel.quantity_on_hand
│       ├── Log InventoryTransaction (type=return)
│       └── Mark is_returned=True
│
└── When all items returned → task status = completed
```

---

## 4. Signal-Driven Automation

### Signal Handlers (warehouse/signals.py)

| Signal | Sender | Handler | dispatch_uid | Trigger |
|--------|--------|---------|-------------|---------|
| `pre_save` | `orders.Order` | `order_pre_save_handler` | `warehouse.order_pre_save_handler` | Snapshots old `order_status` |
| `post_save` | `orders.Order` | `order_post_save_handler` | `warehouse.order_post_save_handler` | Dispatches reserve/release/sync |
| `pre_save` | `delivery.DeliveryTask` | `delivery_task_pre_save_handler` | `warehouse.delivery_task_pre_save_handler` | Snapshots old `dl_task_status` |
| `post_save` | `delivery.DeliveryTask` | `delivery_task_post_save_handler` | `warehouse.delivery_task_post_save_handler` | Dispatches fulfill/return |
| `post_save` | `warehouse.StockLevel` | `stock_level_post_save_handler` | `warehouse.stock_level_post_save_handler` | Checks low stock alerts |
| `post_save` | `warehouse.SellerWarehouseLink` | `seller_warehouse_link_post_save` | `warehouse.seller_warehouse_link_post_save` | Syncs PickupLocation |
| `post_delete` | `warehouse.SellerWarehouseLink` | `seller_warehouse_link_post_delete` | `warehouse.seller_warehouse_link_post_delete` | Deactivates PickupLocation |

### Order Post-Save Decision Tree

```
order_post_save_handler(instance, created):
│
├── IF status == 'ready_to_pickup' AND stock_reserved == False
│   AND (created OR old_status != 'ready_to_pickup'):
│   ├── atomic: reserve_stock_for_order(order)
│   └── create_pick_list_for_order(order)
│
├── ELIF status == 'ready_to_pickup' AND NOT created:
│   └── sync_pick_list_for_order(order)  # order edited while pending
│
└── ELIF NOT created AND old_status != 'cancelled' AND status == 'cancelled':
    ├── atomic: release_stock_reservation(order)
    └── remove_pick_list_for_order(order)
```

### Delivery Post-Save Decision Tree

```
delivery_task_post_save_handler(instance, created):
│
├── IF old_status != 'delivered' AND status == 'delivered':
│   └── atomic: fulfill_stock_reservation(order)
│
└── ELIF status == 'failed' AND old_status not in (None, 'failed'):
    └── atomic: return_stock_on_failed_delivery(order)
```

### Transaction Boundaries

| Operation | Atomic? | Lock (`select_for_update`)? |
|-----------|---------|---------------------------|
| Reserve stock | Yes (caller) | Yes (StockLevel rows) |
| Release reservations | Yes (caller) | No |
| Fulfill reservations | Yes (caller) | No (but deducts within atomic) |
| Direct deduct stock | Inherits caller | Yes (StockLevel rows) |
| Reverse deductions | Inherits caller | Yes (StockLevel rows) |
| Return stock on failure | Yes (caller) | No |
| Create pick list | No (separate try/except) | No |
| Sync pick list | No | No |
| Remove pick list | No | No |

---

## 5. View & URL Reference

### URL Namespace: `warehouse:`

All URLs mounted at `workforce/warehouse/` in root `urls.py`.

### Dashboard
| URL | View | Method | Auth |
|-----|------|--------|------|
| `/` | `dashboard` | GET | `has_warehouse_access` |

### Inventory
| URL | View | Method | Auth |
|-----|------|--------|------|
| `/inventory/` | `inventory_list` | GET | `has_warehouse_access` |
| `/inventory/<id>/` | `stock_card` | GET | `has_warehouse_access` |
| `/transactions/` | `transaction_list` | GET | `has_warehouse_access` |
| `/receive/` | `receive_stock` | GET+POST | `has_warehouse_access` |

### Picking
| URL | View | Method | Auth | Response |
|-----|------|--------|------|----------|
| `/pick-lists/` | `pick_list_list` | GET | `has_warehouse_access` | HTML |
| `/pick-lists/create/` | `create_pick_list` | GET+POST | `has_warehouse_access` | HTML |
| `/pick-lists/<pk>/` | `pick_list_detail` | GET | `has_warehouse_access` | HTML |
| `/pick-lists/<pk>/assign/` | `assign_pick_list` | POST | `has_warehouse_access` | Redirect |
| `/pick-lists/<pk>/start/` | `start_pick_list` | POST | `has_warehouse_access` | Redirect |
| `/pick-lists/<pk>/items/<id>/pick/` | `pick_item` | POST | `has_warehouse_access` | JSON |
| `/pick-lists/<pk>/items/<id>/unpick/` | `unpick_item` | POST | `has_warehouse_access` | JSON |
| `/pick-lists/bulk-drop/` | `bulk_drop_pick_lists` | POST | superadmin | Redirect |

### Packing
| URL | View | Method | Auth | Response |
|-----|------|--------|------|----------|
| `/pick-lists/<pk>/pack/` | `pack_station` | GET | `has_warehouse_access` | HTML |
| `/pick-lists/<pk>/pack-order/<id>/` | `pack_order` | POST | `has_warehouse_access` | JSON |

### Dispatch
| URL | View | Method | Auth | Response |
|-----|------|--------|------|----------|
| `/dispatch/` | `dispatch_queue` | GET | `has_warehouse_access` | HTML |
| `/dispatch/create/` | `dispatch_create` | POST | `has_warehouse_access` | Redirect |
| `/dispatch/<pk>/` | `dispatch_detail` | GET | `has_warehouse_access` | HTML |
| `/dispatch/<pk>/handover/<id>/` | `dispatch_handover_item` | POST | `has_warehouse_access` | JSON |
| `/dispatch/<pk>/confirm/` | `dispatch_confirm` | POST | `has_warehouse_access` | Redirect |

### Customer Returns (RMA)
| URL | View | Method | Auth | Response |
|-----|------|--------|------|----------|
| `/rma/` | `rma_list` | GET | `has_warehouse_access` | HTML |
| `/rma/create/<order_id>/` | `rma_create` | GET+POST | `has_warehouse_access` | HTML |
| `/rma/<pk>/` | `rma_detail` | GET | `has_warehouse_access` | HTML |
| `/rma/<pk>/receive/` | `rma_receive` | POST | `has_warehouse_access` | Redirect |
| `/rma/<pk>/inspect/<id>/` | `rma_inspect_item` | POST | `has_warehouse_access` | JSON |

### Put-Away
| URL | View | Method | Auth | Response |
|-----|------|--------|------|----------|
| `/put-away/` | `put_away_list` | GET | `has_warehouse_access` | HTML |
| `/put-away/<pk>/` | `put_away_detail` | GET | `has_warehouse_access` | HTML |
| `/put-away/<pk>/assign/` | `put_away_assign` | POST | `has_warehouse_access` | Redirect |
| `/put-away/<pk>/items/<id>/confirm/` | `put_away_confirm_item` | POST | `has_warehouse_access` | JSON |

### Return Tasks
| URL | View | Method | Auth | Response |
|-----|------|--------|------|----------|
| `/returns/` | `return_task_list` | GET | `has_warehouse_access` | HTML |
| `/returns/<pk>/` | `return_task_detail` | GET | `has_warehouse_access` | HTML |
| `/returns/<pk>/return-item/<id>/` | `return_item` | POST | `has_warehouse_access` | JSON |

### Cycle Counting
| URL | View | Method | Auth | Response |
|-----|------|--------|------|----------|
| `/cycle-counts/` | `cycle_count_list` | GET | `has_warehouse_access` | HTML |
| `/cycle-counts/create/` | `create_cycle_count` | GET | `has_warehouse_access` | Redirect (placeholder) |
| `/cycle-counts/<pk>/` | `cycle_count_detail` | GET | `has_warehouse_access` | HTML |

### Alerts
| URL | View | Method | Auth |
|-----|------|--------|------|
| `/alerts/` | `low_stock_alerts` | GET | `has_warehouse_access` |
| `/alerts/<pk>/acknowledge/` | `acknowledge_alert` | POST | `has_warehouse_access` |

### Warehouse Setup (superadmin only)
| URL | View | Method |
|-----|------|--------|
| `/warehouses/` | `warehouse_list` | GET |
| `/warehouses/add/` | `warehouse_add` | GET+POST |
| `/warehouses/<pk>/` | `warehouse_detail` | GET |
| `/warehouses/<pk>/edit/` | `warehouse_edit` | GET+POST |
| `/warehouses/<pk>/capacity/configure/` | `warehouse_capacity_configure` | GET+POST |
| `/warehouses/<pk>/capacity/preview/` | `warehouse_capacity_preview` | GET |
| `/warehouses/<pk>/capacity/generate/` | `warehouse_generate_locations` | POST |
| `/locations/` | `location_list` | GET |
| `/locations/add/` | `location_add` | GET+POST |
| `/locations/<pk>/edit/` | `location_edit` | GET+POST |
| `/locations/<pk>/delete/` | `location_delete` | GET+POST |
| `/warehouse-locations/` | `warehouse_location_list` | GET |
| `/warehouse-locations/add/` | `warehouse_location_add` | GET+POST |

### Seller-Warehouse Links (staff only)
| URL | View | Method |
|-----|------|--------|
| `/seller-warehouse-links/` | `seller_warehouse_links` | GET |
| `/seller-warehouse-links/add/` | `seller_warehouse_link_add` | GET+POST |
| `/seller-warehouse-links/<pk>/` | `seller_warehouse_link_detail` | GET |
| `/seller-warehouse-links/<pk>/edit/` | `seller_warehouse_link_edit` | GET+POST |
| `/seller-warehouse-links/<pk>/delete/` | `seller_warehouse_link_delete` | GET+POST |

### JSON API
| URL | View | Returns |
|-----|------|---------|
| `/api/warehouses/<id>/locations/` | `api_warehouse_locations` | Pickup locations |
| `/api/warehouses/<id>/storage-locations/` | `api_storage_locations` | Storage bins |
| `/api/business/<id>/products/` | `api_business_products` | Product list |
| `/api/inbound-request/<id>/items/` | `api_inbound_request_items` | Request items |

---

## 6. Template & UI Structure

### Base Template
`templates/wh_dashboard_base.html` — extends from `includes/head.html`, includes:
- Brand Kit Pro CSS + warehouse.css
- Desktop navbar + HTMX loading overlay
- Mobile sidebar (`warehouse/parts/wh_sidebar_mobile.html`)
- Desktop sidebar (`warehouse/parts/wh_sidebar.html`)
- Main content area with HTMX target `#main-content`

### Sidebar Navigation (3 sections)

**Inventory:** Stock Levels, Receive Stock, Transactions, Low Stock Alerts
**Operations:** Pick Lists, Put-Away, Cycle Counts, Customer Returns, Dispatch, Returns
**Setup (staff only):** Warehouses, Storage Locations, Pickup/Dispatch, Seller Links

### Template Directory
```
warehouse/templates/warehouse/
├── dashboard.html
├── inventory_list.html / stock_card.html / transaction_list.html
├── receive_stock.html
├── pick_list_list.html / pick_list_detail.html / create_pick_list.html
├── pack_station.html
├── dispatch_queue.html / dispatch_detail.html
├── rma_list.html / rma_create.html / rma_detail.html
├── put_away_list.html / put_away_detail.html
├── return_task_list.html / return_task_detail.html
├── cycle_count_list.html / cycle_count_detail.html
├── low_stock_alerts.html
├── warehouse_*.html (setup pages)
├── location_*.html (storage location CRUD)
├── warehouse_location_*.html (pickup point CRUD)
├── seller_warehouse_link*.html (link CRUD)
└── parts/ (wh_sidebar.html, wh_sidebar_mobile.html, qr_scanner.html)
```

---

## 7. Business Rules & Constraints

### Access Control
- **`has_warehouse_access`**: Superadmin OR Staff OR business with active `SellerWarehouseLink`
- **`is_superuser_only`**: Warehouse setup (create/edit/delete warehouses, locations)
- **`@staff_required`**: Seller-warehouse link management
- **Business scoping**: Non-staff users only see data for warehouses linked to their business

### Stock Rules
- Stock reservation uses **greedy multi-bin allocation** (highest on-hand first)
- Partial reservation allowed — warning logged, order continues
- `quantity_reserved` never goes below 0 (clamped)
- `quantity_on_hand` never goes below 0 (clamped)
- Every stock mutation creates an `InventoryTransaction`

### Pick List Rules
- Multiple orders merge into one `pending` pick list per `(warehouse, business, zone)`
- Editing an order while pick list is `pending` → items synced
- Editing locked if pick list status is `in_progress` or beyond
- Cancellation after picking → `ReturnTask` created for picked items

### Unique Constraints
- `(product, warehouse, location)` on `StockLevel`
- `(warehouse, code)` on `StorageLocation` and `WarehouseLocation`
- `(business, warehouse)` on `SellerWarehouseLink`
- One `is_default` SellerWarehouseLink per business (enforced in `save()`)
- One active `LowStockAlert` per `StockLevel` (checked before creation)

---

## 8. Feature Status

### Fully Built
- Dashboard, Inventory list/card/transactions
- Stock receiving (manual + inbound request)
- Put-away tasks (suggest + override location)
- Pick lists (auto-create, zone-group, merge, AJAX pick/unpick)
- Pack station (order-grouped, AJAX toggle)
- Dispatch (batch create, handover, confirm)
- Customer returns/RMA (full lifecycle)
- Return tasks (cancel-after-pickup)
- Low stock alerts (auto-generate + acknowledge)
- Warehouse setup (CRUD, capacity config, auto-generate locations)
- Storage location hierarchy (CRUD, tree view)
- Seller-warehouse links (CRUD + PickupLocation sync)

### Partially Built
- **Cycle count detail**: Read-only display, no count submission UI
- **Barcode scanning**: Template partial exists, `confirm_receive` is stub

### Not Built
- **Cycle count creation**: Placeholder redirect ("coming soon")
- **Outbound product requests**: Models exist, no views/templates
- **Inter-warehouse transfers**: No UI
- **ABC classification management**: Field exists, no automation
- **Reorder automation**: Alerts exist, no PO/suggestion system
- **Wave picking**: Field exists, never populated
