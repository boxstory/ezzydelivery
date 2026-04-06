# Warehouse Workflow — Complete Guide

> Last updated: 2026-03-26

## Overview

The warehouse system handles the full lifecycle from order creation through picking, packing, dispatch, and returns. Pick lists are **product-grouped** (not per-order) for efficient warehouse walking.

---

## Order Lifecycle

```
Customer places order (Shopify / WooCommerce / Manual)
      │
      ▼
Order created → status: "pending"
      │
      ▼ (staff reviews & approves)
Order status → "ready_to_pickup"
      │
      ├──→ Stock Reserved (automatic)
      │      quantity_reserved += qty
      │      StockReservation record created
      │
      └──→ Pick List Created/Merged (automatic)
             Items added to existing PENDING pick list for same warehouse
             Or new pick list created if none exists
```

**Trigger:** `warehouse/signals.py` → `order_post_save_handler` → `create_pick_list_for_order()`

---

## 1. PICK (Product-Grouped)

**URL:** `/workforce/warehouse/pick-lists/`
**Detail:** `/workforce/warehouse/pick-lists/<pk>/`

Multiple orders merge into ONE pick list per warehouse:

```
Order #101 (iPhone Case x2, Cable x1)  ──┐
Order #105 (iPhone Case x3)             ──┤──→  PICK-A1B2C3D4
Order #112 (Cable x2, Screen x1)        ──┘
```

Pick list shows **products grouped by location**:

```
○  iPhone Case         📍 BIN-A3-02    5 pcs
   ├── Order #101   x2
   ├── Order #105   x3

○  USB Cable           📍 BIN-C1-01    3 pcs
   ├── Order #101   x1
   ├── Order #112   x2

○  Screen Protector    📍 BIN-D2-05    1 pc
   └── Order #112   x1
```

**Picker workflow:**
1. Walk to BIN-A3-02 → grab 5 iPhone Cases → tap to expand
2. Mark Order #101 x2 ✓, Order #105 x3 ✓
3. Walk to BIN-C1-01 → grab 3 Cables → mark each order ✓
4. Continue until all items picked

**Status flow:** `Pending → Assigned → In Progress → Picked`

**View:** `warehouse/views.py` → `pick_list_detail()`
**Grouping logic:** View builds `grouped_items` dict keyed by (product_id, location_id)

---

## 2. PACK (Order-Grouped)

**URL:** `/workforce/warehouse/pick-lists/<pk>/pack/`

After ALL items picked → "Start Packing Orders" button appears on the detail page. Pack station shows items **grouped by ORDER** (reverse of pick view):

```
Progress: 1 of 3 orders  ████░░░░  33%

☐  Order #101                                Pack
   📦 iPhone Case              x2
   📦 USB Cable                x1

✅ Order #105                             Packed
   📦 iPhone Case              x3

☐  Order #112                                Pack
   📦 USB Cable                x2
   📦 Screen Protector         x1
```

**Packer workflow:**
1. Sort picked items into order piles
2. Pack Order #101 into box → tap card → ✅ Packed
3. Pack Order #105 → tap → ✅
4. All packed → status: "Packed" → ready for dispatch

**Status flow:** `Picked → Packing → Packed`

**View:** `warehouse/views.py` → `pack_station()`, `pack_order()` (AJAX)

---

## 3. PUT-AWAY (After Receiving)

**URL:** `/workforce/warehouse/put-away/`
**Detail:** `/workforce/warehouse/put-away/<pk>/`

Created **automatically** when stock is received via Receive Stock. Tells staff where to place received items in storage bins.

```
RECEIVE STOCK
  Staff receives 50 iPhone Cases + 30 USB Cables at warehouse dock
      │
      ▼
  Stock added to quantity_on_hand at staging/dock location
  InventoryTransaction logged (type: receive)
      │
      ▼
  PutAwayTask auto-created (PA-X1Y2Z3)
  System suggests locations where product already exists (consolidation)
      │
      ▼
  Staff redirected to put-away detail page
```

Put-away task shows items with suggested storage locations:

```
PUT-AWAY TASK
PA-X1Y2Z3  —  Main Warehouse

Progress: 0 of 2 items  ░░░░░░░░  0%

○  iPhone Case      💡 BIN-A3-02 (suggested)   x50   [change]
○  USB Cable        💡 BIN-C1-01 (suggested)   x30   [change]
```

**Staff workflow:**
1. See suggested location BIN-A3-02 (where iPhone Cases already exist)
2. Walk to BIN-A3-02 → place 50 cases on shelf
3. Tap ○ → ✅ (stock transferred: staging → BIN-A3-02)
4. Optionally tap "change" to pick a different bin
5. Repeat for each item
6. All done → Put-Away Task completed

**Stock transfer on confirm:**
- `transfer_out` from source/staging location (deducts `quantity_on_hand`)
- `transfer_in` to actual bin location (adds `quantity_on_hand`)
- Both transactions logged in audit trail with `reference_type='put_away'`

**Location suggestion logic:**
1. Find existing `StockLevel` for this product in same warehouse at a bin location
2. Pick the location with highest `quantity_on_hand` (consolidation)
3. If no existing stock → no suggestion, staff picks manually from dropdown

**Status flow:** `Pending → Assigned → In Progress → Completed`

**Models:** `PutAwayTask`, `PutAwayTaskItem` in `warehouse/models.py`
**Auto-create:** `warehouse/views.py` → `_create_put_away_task()` called from `receive_stock()`
**Stock transfer:** `warehouse/views.py` → `put_away_confirm_item()` (AJAX)

---

## 4. Dispatch / Delivery

Packed orders → DeliveryTask created → Driver assigned → Delivery

**Status flow:** `Packed → DeliveryTask → Picked Up → Delivered`

On delivery: `stock_reserved` released, stock fulfilled.

---

## 5. Return to Shelf

**URL:** `/workforce/warehouse/returns/`
**Detail:** `/workforce/warehouse/returns/<pk>/`

Created **automatically** when order cancelled after pickup. Staff sees return task in sidebar under Operations → Returns.

```
RETURN TO SHELF
RTN-X1Y2Z3  —  Main Warehouse
Order: ORD-001 (cancelled)

○  iPhone Case      📍 BIN-A3-02          x2
○  USB Cable        📍 BIN-C1-01          x1
○  Screen Protector 📍 BIN-D2-05          x1
```

**Staff workflow:**
1. Walk to BIN-A3-02 → place 2 iPhone Cases back on shelf
2. Tap ○ → ✅ (stock `on_hand += 2`, InventoryTransaction logged)
3. Repeat for each item
4. All done → Return Task completed

**KEY:** Stock updates ONLY when staff confirms — not automatic.

**Models:** `ReturnTask`, `ReturnTaskItem` in `warehouse/models.py`
**Signal:** `warehouse/signals.py` → `_create_return_task()`
**Stock update:** `warehouse/signals.py` → `complete_return_item()`

---

## 6. Bulk Drop to Shelf (Superadmin Only)

On the pick list page, superadmin can select multiple pick lists and "Drop to Shelf":

- All picked items → `quantity_on_hand` increased
- Each return logged as `InventoryTransaction`
- All items reset: `is_picked=False`, `is_packed=False`
- Pick lists reset to **Pending** (can be re-picked)

**View:** `warehouse/views.py` → `bulk_drop_pick_lists()`
**URL:** `/workforce/warehouse/pick-lists/bulk-drop/` (POST)

---

## Order Edit / Cancel Handling

| Action | Pick List Pending | Pick List Active | Pick List Picked/Packed |
|--------|------------------|-----------------|------------------------|
| **Edit: add product** | Item added to pick list | Ignored (locked) | Ignored |
| **Edit: remove product** | Item removed | Ignored | Ignored |
| **Edit: change qty** | Qty updated | Ignored | Ignored |
| **Cancel order** | Items deleted, empty list auto-deleted, reservation released | Unpicked deleted, picked → Return Task created | Return Task created for all items |

**Signal:** `warehouse/signals.py` → `order_post_save_handler()`
**Sync:** `sync_pick_list_for_order()` — only modifies `pending` pick lists
**Cancel:** `remove_pick_list_for_order()` — handles all statuses

---

## Stock Level Tracking

`StockLevel` fields per product per warehouse per location:

| Field | Meaning |
|-------|---------|
| `quantity_on_hand` | Physically on shelf |
| `quantity_reserved` | Allocated to orders (not yet picked) |
| `quantity_incoming` | Expected from suppliers |
| **Available** | `on_hand - reserved` |

### Stock events

| Event | on_hand | reserved |
|-------|---------|----------|
| Order → `ready_to_pickup` | — | +qty |
| Item picked | — | — (still reserved) |
| Order delivered | -qty | -qty (fulfilled) |
| Order cancelled before pick | — | -qty |
| Order cancelled after pick | +qty (on staff confirm) | -qty |
| Receive stock | +qty (at staging) | — |
| Put-away confirmed | -qty (staging) / +qty (bin) | — |
| Bulk drop (superadmin) | +qty (immediate) | — |

---

## Pick List Status Choices

| Status | Display | Meaning |
|--------|---------|---------|
| `pending` | Pending | Waiting to be assigned/started |
| `assigned` | Assigned | Assigned to a picker |
| `in_progress` | In Progress | Picker is actively picking |
| `completed` | Picked | All items picked, ready for packing |
| `packing` | Packing | Sorting into orders at pack station |
| `packed` | Packed | All orders packed, ready for dispatch |
| `cancelled` | Cancelled | Pick list cancelled |

---

## URL Structure

### Operations
| URL | View | Purpose |
|-----|------|---------|
| `/warehouse/pick-lists/` | `pick_list_list` | List all pick lists |
| `/warehouse/pick-lists/create/` | `create_pick_list` | Select orders → create pick list |
| `/warehouse/pick-lists/bulk-drop/` | `bulk_drop_pick_lists` | Superadmin: return items to shelf |
| `/warehouse/pick-lists/<pk>/` | `pick_list_detail` | Product-grouped pick view |
| `/warehouse/pick-lists/<pk>/start/` | `start_pick_list` | Assign & start picking |
| `/warehouse/pick-lists/<pk>/items/<id>/pick/` | `pick_item` | AJAX: mark item picked |
| `/warehouse/pick-lists/<pk>/items/<id>/unpick/` | `unpick_item` | AJAX: undo pick |
| `/warehouse/pick-lists/<pk>/pack/` | `pack_station` | Order-grouped packing view |
| `/warehouse/pick-lists/<pk>/pack-order/<id>/` | `pack_order` | AJAX: mark order packed |
| `/warehouse/put-away/` | `put_away_list` | List put-away tasks |
| `/warehouse/put-away/<pk>/` | `put_away_detail` | Put-away items to bins |
| `/warehouse/put-away/<pk>/assign/` | `put_away_assign` | Assign task to self |
| `/warehouse/put-away/<pk>/items/<id>/confirm/` | `put_away_confirm_item` | AJAX: confirm item placed |
| `/warehouse/returns/` | `return_task_list` | List return tasks |
| `/warehouse/returns/<pk>/` | `return_task_detail` | Return items to shelf |
| `/warehouse/returns/<pk>/return-item/<id>/` | `return_item` | AJAX: confirm item returned |

### Inventory
| URL | View | Purpose |
|-----|------|---------|
| `/warehouse/inventory/` | `inventory_list` | Stock levels |
| `/warehouse/inventory/<id>/` | `stock_card` | Per-product stock card |
| `/warehouse/receive/` | `receive_stock` | Receive inbound stock |
| `/warehouse/transactions/` | `transaction_list` | Inventory transaction log |
| `/warehouse/alerts/` | `low_stock_alerts` | Low stock alerts |

### Setup (Staff/Superadmin)
| URL | View | Purpose |
|-----|------|---------|
| `/warehouse/warehouses/` | `warehouse_list` | Manage warehouses |
| `/warehouse/locations/` | `location_list` | Storage locations (zones/racks/shelves/bins) |
| `/warehouse/warehouse-locations/` | `warehouse_location_list` | Pickup/dispatch locations |
| `/warehouse/seller-warehouse-links/` | `seller_warehouse_links` | Seller-warehouse links |

---

## User Roles & Job Responsibilities

---

### Superadmin (`Profile.is_superadmin`)

**Role:** Platform administrator. Owns warehouse infrastructure, system configuration, and emergency operations. Has all Staff permissions plus setup/config access.

#### Infrastructure Setup

| Task | Sidebar Location | Step-by-Step |
|------|-----------------|-------------|
| **Create a warehouse** | Setup → Warehouses → Add | 1. Enter name, code, address, GPS coordinates, country<br>2. Assign a warehouse manager (staff user)<br>3. Save → warehouse created with auto-code `WH-FC-XXXXXXXX` if code left blank |
| **Configure capacity** | Setup → Warehouses → Detail → Configure Capacity | 1. Set number of zones (e.g. 4)<br>2. Set racks per zone (e.g. 10)<br>3. Set shelves per rack (e.g. 5)<br>4. Set bins per shelf (e.g. 4)<br>5. Choose naming patterns: zones (custom names like A,B,C or COLD,DRY,FRAGILE), racks/shelves/bins (numeric 01,02 or alpha A,B)<br>6. Save → preview generated locations → confirm to auto-create full hierarchy |
| **Manage storage locations** | Setup → Storage Locations | Tree view of all zones → racks → shelves → bins. Add/edit/delete individual locations. Each location has: code, barcode (auto-generated), type, dimensions (W×L×H cm), max weight, is_pickable flag |
| **Create pickup/dispatch locations** | Setup → Pickup/Dispatch → Add | 1. Select warehouse<br>2. Enter name (e.g. "North Gate", "Loading Bay 2")<br>3. Enter code, address, GPS coordinates<br>4. Assign delivery zone number<br>5. Set as default or not<br>6. Add operating hours and driver notes |
| **Link sellers to warehouses** | Setup → Seller Links → Add | 1. Select business (seller)<br>2. Select warehouse<br>3. Set default pickup location within that warehouse<br>4. Set priority (higher = preferred for auto-selection)<br>5. Mark as default warehouse for this seller (optional)<br>6. Add notes about the relationship |

#### Emergency Operations

| Task | Where | When to Use |
|------|-------|-------------|
| **Bulk drop to shelf** | Operations → Pick Lists → Select checkboxes → "Drop to Shelf" | When pick lists need to be completely reset (e.g. wrong items picked, system error, end-of-day reset). Returns ALL picked items to `quantity_on_hand` at their original locations, resets `is_picked`/`is_packed` flags, and sets pick list back to `Pending` status. Each return logged as an `InventoryTransaction`. |

---

### Staff (`Profile.is_staff`)

**Role:** Warehouse floor operator. Handles all day-to-day operations: receiving, put-away, picking, packing, dispatch, returns, counting, and monitoring. Works primarily on mobile (phone/tablet) walking through the warehouse.

#### Inbound Operations (Getting Stock In)

| Task | Sidebar Location | Step-by-Step | What Happens in System |
|------|-----------------|-------------|----------------------|
| **Receive stock (manual)** | Inventory → Receive Stock | 1. Select warehouse<br>2. Optionally select receiving dock/staging location<br>3. Add products one by one: select product, enter quantity<br>4. Add reference number and notes (optional)<br>5. Click "Receive" | • `StockLevel.quantity_on_hand` += qty at staging location<br>• `InventoryTransaction` created (type: `receive`)<br>• `PutAwayTask` auto-created with suggested bin locations<br>• Redirected to put-away task detail page |
| **Receive from inbound request** | Inventory → Receive Stock → Select Request | 1. Click on a pending inbound request at top of page<br>2. Products auto-populated from request<br>3. Adjust quantities if partial delivery<br>4. Click "Receive" | Same as manual + inbound request status updated. If all items fulfilled → request marked `completed`. Partial → remains `approved` (open). |
| **Put-away** | Operations → Put-Away → Click task | 1. Task auto-starts when opened (status → In Progress)<br>2. For each item, see product name, SKU, quantity, and **suggested bin** (amber tag)<br>3. Walk to suggested location (e.g. BIN-A3-02)<br>4. Place items on shelf<br>5. Tap the circle ○ to confirm → turns green ✅<br>6. To use a different location: tap "change" → select from dropdown → then confirm<br>7. Progress bar updates. When all items done → task completed | • `transfer_out` from staging location (deducts qty)<br>• `transfer_in` to actual bin location (adds qty)<br>• Both logged as `InventoryTransaction`<br>• `PutAwayTaskItem.actual_location` set<br>• Task progress counter updated |

#### Order Fulfillment (Getting Stock Out)

| Task | Sidebar Location | Step-by-Step | What Happens in System |
|------|-----------------|-------------|----------------------|
| **Pick orders** | Operations → Pick Lists → Click list | 1. Pick list auto-assigned to you on first view<br>2. Items shown **grouped by product & location** — walk to one bin, grab all units for multiple orders at once<br>3. At each location, expand the product group to see which orders need how many<br>4. Tap circle to mark product picked (can enter actual qty if different)<br>5. Progress bar tracks items picked vs total<br>6. When all items picked → status: `Picked` → "Start Packing" button appears | • `PickListItem.is_picked = True`, `quantity_picked` set<br>• `PickList.picked_items` counter updated<br>• Pick list status auto-advances |
| **Create pick list (manual)** | Operations → Pick Lists → Create | 1. Filter orders by warehouse, business, status<br>2. Select orders to include<br>3. System auto-merges into existing pending pick list for same warehouse/business (if one exists) or creates new<br>4. Pick list shows product-grouped view | • `PickList` created with `pick_number` auto-generated<br>• `PickListItem` created for each order item<br>• Items grouped by (product, location) |
| **Pack orders** | Pick List Detail → "Start Packing Orders" | 1. Items now shown **grouped by ORDER** (reverse of pick view)<br>2. Each card shows one order with all its products<br>3. Verify items match the order → tap "Pack" on the card<br>4. Card turns green ✅<br>5. When all orders packed → pick list status: `Packed` | • `PickListItem.is_packed = True`<br>• Pick list status → `packing` then `packed` |
| **Dispatch to driver** | Operations → Dispatch | 1. See list of packed orders ready for dispatch<br>2. Select orders to include in a batch<br>3. Select driver from dropdown<br>4. Click "Create Dispatch Batch"<br>5. On the batch detail page, hand each package to the driver<br>6. Tap "Handover" on each order as driver takes it<br>7. When all handed over → "Confirm Dispatch" → driver leaves | • `DispatchBatch` created with `batch_number`<br>• `DispatchItem` created per order<br>• COD amounts tracked per item/batch<br>• Status: `ready` → `assigned` → `handed_over` → `dispatched` |

#### Returns & Recovery

| Task | Sidebar Location | Step-by-Step | What Happens in System |
|------|-----------------|-------------|----------------------|
| **Return to shelf** | Operations → Returns → Click task | Auto-created when an order is cancelled after items were picked.<br>1. Task shows items with their **original bin locations**<br>2. Walk to each location → place items back on shelf<br>3. Tap circle to confirm each item returned<br>4. When all returned → task completed | • `StockLevel.quantity_on_hand` += qty at original location<br>• `InventoryTransaction` created (type: `return`)<br>• `ReturnTask.status` → `completed` |
| **Customer return (RMA) — Create** | Operations → Customer Returns → Select order | 1. Select the order being returned<br>2. Choose return reason: wrong item / damaged / refused (COD) / change of mind / not as described / other<br>3. Select which items are being returned and quantities<br>4. Add customer notes | • `CustomerReturn` created with `rma_number`<br>• `CustomerReturnItem` created per product<br>• Status: `requested` |
| **Customer return — Receive** | Customer Returns → Detail → "Mark Received" | 1. When return shipment arrives, click "Mark Received"<br>2. All items marked as received at warehouse | • `CustomerReturnItem.is_received = True`<br>• `CustomerReturn.status` → `received` |
| **Customer return — Inspect** | Customer Returns → Detail → Inspect each item | 1. For each returned item, set **condition**: good / damaged / defective / opened<br>2. Set **disposition**: restock (good) / quarantine (inspect further) / dispose (damaged)<br>3. If disposition is "restock" → select target bin location | • `CustomerReturnItem.condition` and `disposition` set<br>• If restock: `StockLevel.quantity_on_hand` += qty at selected location<br>• `InventoryTransaction` created (type: `return`)<br>• When all items inspected → status: `resolved` |

#### Inventory Control

| Task | Sidebar Location | Step-by-Step | What Happens in System |
|------|-----------------|-------------|----------------------|
| **Monitor stock levels** | Inventory → Stock Levels | Filter by: warehouse, search term, low stock only, product category. See: product, warehouse, location, on_hand, reserved, available, reorder point. Click product for stock card with full transaction history. | Read-only view. Shows `StockLevel` records with computed `available = on_hand - reserved`. |
| **Create cycle count** | Operations → Cycle Counts → Create | 1. Select warehouse and specific location (zone/rack/shelf)<br>2. Set scheduled date<br>3. System auto-populates items: all products with stock at that location<br>4. Shows `system_quantity` (what system thinks is there) | • `CycleCount` created with `count_number`<br>• `CycleCountItem` per product/location with `system_quantity` |
| **Perform cycle count** | Operations → Cycle Counts → Click count | 1. Walk to the location<br>2. Physically count each product<br>3. Enter `counted_quantity` for each item<br>4. System auto-calculates `variance` (counted − system)<br>5. Add notes explaining any discrepancy<br>6. Submit for review/approval | • `CycleCountItem.counted_quantity` and `variance` set<br>• Status: `scheduled` → `in_progress` → `pending_review` |
| **Acknowledge low stock alerts** | Inventory → Low Stock Alerts | See list of products where `available ≤ reorder_point`. Click "Acknowledge" to mark you've seen it. Alert auto-resolves when stock replenished above reorder point. | • `LowStockAlert.status` → `acknowledged`<br>• `acknowledged_by` and `acknowledged_at` recorded |
| **View transaction log** | Inventory → Transactions | Full audit trail. Filter by: warehouse, transaction type (receive, ship, transfer, adjust, return, reserve, count). Each entry shows: product, location, type, qty, before/after quantities, reference, who, when. | Read-only. `InventoryTransaction` records with full traceability. |

---

### Business/Seller (`Profile.is_business`)

**Role:** External seller using the warehouse as a fulfillment center. Limited visibility into their own stock and order operations. Cannot modify warehouse data directly.

| Task | Where | What They See | What They Can Do |
|------|-------|--------------|-----------------|
| **View their stock** | Inventory → Stock Levels | Only products belonging to their business, at warehouses linked to them via `SellerWarehouseLink` | Read-only. See on_hand, reserved, available quantities per product/location |
| **View their pick lists** | Operations → Pick Lists | Only pick lists for their business's orders | Read-only. See pick list status, items, progress |
| **View their transactions** | Inventory → Transactions | Only transactions at linked warehouses | Read-only. Audit trail for their stock movements |
| **Submit inbound request** | Business Portal | Create a request to send products to the warehouse | Select warehouse, add products + quantities, set expected delivery date. Staff approves and receives. |
| **Submit outbound request** | Business Portal | Create a request to receive products from warehouse | Select warehouse, add products + quantities, set priority (normal/urgent). Staff picks and ships. |

**Access control:** `get_business_filter()` in views.py returns `(business, is_staff)`. Non-staff users are filtered to only see data from warehouses linked via `SellerWarehouseLink.objects.filter(business=business, is_active=True)`.

---

### Typical Daily Workflow by Role

#### Staff — Morning Shift
```
08:00  Dashboard check
       → See pending put-away tasks, unassigned pick lists, active alerts
       → Note any urgent priority put-away tasks

08:15  Receive stock (if deliveries arrived overnight)
       → Inventory → Receive Stock
       → Process each delivery → put-away tasks auto-created

08:30  Put-away
       → Operations → Put-Away → work through tasks
       → Place received stock into bins
       → Consolidate with existing stock where possible

09:30  Pick orders
       → Operations → Pick Lists → pick oldest pending list first
       → Walk warehouse with product-grouped list
       → Efficient route: one product at a time, all orders

11:00  Pack orders
       → After picking complete → Start Packing
       → Sort items into individual orders
       → Verify quantities match → mark each order packed
```

#### Staff — Afternoon Shift
```
13:00  Dispatch
       → Operations → Dispatch → assign packed orders to drivers
       → Group orders by delivery zone for efficient routing
       → Hand over packages, collect driver signature

14:00  Handle returns
       → Check for new return-to-shelf tasks (cancelled orders)
       → Walk items back to original bins, confirm returned
       → Process any customer RMA returns: receive → inspect → restock/quarantine/dispose

15:30  Inventory maintenance
       → Acknowledge any new low stock alerts
       → Perform scheduled cycle counts if due
       → Report discrepancies

16:30  End-of-day review
       → Dashboard: verify no pending tasks left
       → Check for any stuck pick lists or dispatch batches
```

#### Superadmin — Weekly/As-Needed
```
Monday    Review warehouse utilization on Dashboard
          Check seller links are up to date
          Review cycle count discrepancies from last week

As-needed Add new warehouse or reconfigure capacity
          Create new pickup/dispatch locations for new zones
          Link/unlink sellers to warehouses
          Bulk drop pick lists if system error or reset needed
```

---

## Key Files

| File | Purpose |
|------|---------|
| `warehouse/models.py` | PickList, PickListItem, ReturnTask, ReturnTaskItem, PutAwayTask, PutAwayTaskItem, StockLevel |
| `warehouse/signals.py` | Auto pick list creation, sync, cancel handling, return tasks |
| `warehouse/views.py` | All views including pack station and returns |
| `warehouse/urls.py` | URL routing |
| `warehouse/static/warehouse/css/warehouse.css` | All warehouse CSS |
| `templates/wh_dashboard_base.html` | Base template with sidebar |
