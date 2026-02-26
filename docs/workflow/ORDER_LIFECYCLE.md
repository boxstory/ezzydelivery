# Order Lifecycle — EzzyDelivery

Complete flow from client order creation to final delivery and COD settlement.

---

## Overview

```
Client Creates Order
        ↓
Workforce Verifies Order
        ↓
Workforce Creates Delivery Task
        ↓
Task Published to Fleet
        ↓
Driver Assigned / Accepts
        ↓
Driver On The Road
        ↓
Delivery Outcome (Delivered / Failed / Cancelled)
        ↓
COD Settlement (if applicable)
        ↓
Client Sees Final Status
```

---

## Stage 1: Client Creates Order

### 1a. Who is the Client?

A **Business** account in EzzyDelivery. A business can have:
- **Owner** — full access to all orders, settings, billing
- **Team Members** — role-based access via `BusinessPermissions`:
  - `ORDER_VIEW` — can view orders
  - `ORDER_CREATE` — can create new orders
  - `ORDER_EDIT` — can update order details and status
  - `ORDER_DELETE` — can delete orders (restricted by status)

---

### 1b. Order Creation Methods

#### Method 1 — Single Order Form (`/orders/add/`)
Fill the form manually for one order at a time.

**Order Info fields:**
- `client_order_code` — business's own internal reference number (unique per business)
- `order_notes` — short description or special instructions
- `order_type`:
  - `normal_delivery` — standard pickup → deliver to customer
  - `pick_and_drop` — pickup from one location, drop at another

**Customer Details fields:**
- `customer_name` — recipient full name
- `customer_phone` — primary contact number
- `customer_whatsapp` — WhatsApp number (can differ from phone)

**Delivery Address fields:**
- `customer_address` — free-text address description
- `dl_zone` — Qatar zone number (from QNAS)
- `dl_street` — Qatar street number (from QNAS)
- `dl_building` — Qatar building number (from QNAS)
- `latitude` / `longitude` — auto-set from QNAS lookup or map pin
- `coords_accuracy` — accuracy level of coordinates:
  - `exact` — pinned to building
  - `street` — street level
  - `landmark` — area/landmark
  - `zone_center` — zone center fallback
  - `ai_estimate` — AI-inferred location

**COD (Cash on Delivery) fields:**
- `cod_amount` — amount driver will collect from customer (QAR, integer)
- `cod_status_by_client`:
  - `no_cod` — no cash collection needed
  - `pending` — COD expected, not yet collected
  - `collected` — driver collected the cash
  - `received_by_company` — cash handed to EzzyDelivery
  - `invoiced` — invoiced to business
  - `settled` — fully settled with business
  - `online_paid` — customer paid online directly to seller
  - `disputed` — COD amount in dispute

**Pickup Location field:**
- `pickup_location` — where driver collects the package from
  - Dropdown shows business's registered pickup locations
  - Fulfillment center (if enabled) shown first
  - If fulfillment service is active → fulfillment center pre-selected by default

---

#### Method 2 — Bulk Spreadsheet Entry (`/orders/bulk-entry/`)
Excel-like row-by-row entry interface. Enter multiple orders in a table without uploading a file.

**Columns in the spreadsheet:**
- `order_id` — client's reference code
- `customer_name`
- `phone1` — primary phone
- `phone2_whatsapp` — WhatsApp number
- `customer_address` — full address text
- `zone_no` — zone number
- `street_no` — street number
- `building_no` — building number
- `deadline_date` — required delivery date
- `note` — delivery instructions
- `product_name` — item name (stored in order_notes)
- `qty` — quantity
- `price` — COD amount per item

**Behavior:**
- Auto-generates `client_order_code` if left blank: `BULK-{timestamp}-{row_index}`
- Validates all rows before saving
- Saves all valid rows in one batch

---

#### Method 3 — CSV / Excel File Upload (`/orders/upload/`)
Upload a prepared spreadsheet file.

**Supported formats:** `.csv`, `.xlsx`, `.xls`
**Max file size:** 5MB

**Supported CSV column names (auto-detected):**
| Category | Column Names |
|---|---|
| Order Info | `client_order_code`, `order_date` |
| Customer | `customer_name`, `customer_phone`, `customer_whatsapp`, `customer_email` |
| Address | `customer_address`, `dl_landmark`, `dl_building`, `dl_street`, `dl_zone`, `location_link`, `dl_latitude`, `dl_longitude` |
| Delivery | `deadline_date` |
| Products | `product_name`, `quantity`, `cod_amount`, `product_1`–`product_5`, `count_1`–`count_5` |
| Notes | `internal_notes`, `seller_notes` |

**Upload flow (4 steps):**
1. **Upload** — select and submit file
2. **Map Columns** — auto-detected column mapping, manually adjust if needed
3. **Preview & Edit** — review all rows, fix errors inline before saving
4. **Complete** — orders saved to database

---

#### Method 4 — E-commerce API Import (`/orders/api/`)
Pull orders directly from connected e-commerce platforms.

**Supported platforms:**
- **Shopify** — import by order IDs or date range, up to 50 orders per sync
- **WooCommerce** — import by order IDs, date range, or status filter
- **TikTok Shop** — import from TikTok Shop integration

**Sync settings per platform:**
- `start_date` / `end_date` — date range filter
- `order_ids` — specific order IDs to import
- `limit` — max orders per import (default: 50)
- `status` — filter by platform order status (WooCommerce)

---

### 1c. Order Number Generation

System auto-generates a unique `order_number` on save:
```
Format: {BUSINESS_CODE}-{YYYYMMDD}-{sequence}
Example: ALSH-20260226-001
```
`client_order_code` is the business's own reference and must be unique per business.

---

### 1d. System Auto-Sets on Creation

| Field | Value Set |
|---|---|
| `order_status` | `'to_review'` |
| `task_status` | `'new_order'` |
| `verification_status` | `'pending'` |
| `address_verified` | `False` |
| `stock_reserved` | `False` |
| `task_created` | `False` |

**Auto-created records (via post_save signal):**
- `DlAddressUpdate` — snapshot of delivery address for the driver
- `OrderBarcode` — QR code image for label printing
- `AddressVerification` — token-based customer self-verification record
- `OrderStatusHistory` — first timeline entry logged: "Order Created"

---

### 1e. Client Order Editing & Restrictions

After creation, the client can edit an order **only if** it has not yet been published or delivered.

**Editable fields (via `UpdateOrderForm`):**
- `customer_phone`, `customer_whatsapp`
- `cod_amount`, `cod_status_by_client`
- `dl_zone`, `dl_street`, `dl_building`
- `customer_address`, `latitude`, `longitude`
- `pickup_location`, `order_notes`

**Locked / read-only fields:**
- `customer_name` — disabled in form after creation
- `customer_whatsapp` — read-only
- `order_status` — only workforce can change this

**Deletion rules:**
- Client can delete order only if `order_status` is `'to_review'` or `'cancelled'`
- Before deletion: `DeliveryTask`, `DlAddressUpdate`, `OrderBarcode` are deleted first (FK `DO_NOTHING` constraint)

---

### 1f. Order Status — Client View

| `order_status` | What Client Sees | Meaning |
|---|---|---|
| `to_review` | Hold for Review | Just created, awaiting staff verification |
| `ready_to_pickup` | Ready to Pickup | Verified, task created, driver being assigned |
| `publish` | Published | Task published to driver pool |
| `delivered` | Delivered | Successfully delivered to customer |
| `cancelled` | Cancelled | Order cancelled, no further action |

---

### 1g. Adding Products / Items to an Order

After creating an order, client can attach order items (for fulfillment tracking):

**Via `AddOrderProductsForm`:**
- `product` — select from business's product catalog
- `quantity` — number of units (min 1)
- `unit_price` — price per unit
- `notes` — item-specific notes

**Security:** IDOR check verifies the order belongs to `request.current_business` before saving.

`OrderItem.total_price` is auto-calculated as `unit_price × quantity`.

---

### 1h. Order Comments

Client (and staff) can add comments to any order:
- Visible in the order detail timeline
- Stored with `user` reference and timestamp
- Cannot be edited or deleted after posting (audit trail)

---

### 1i. Customer Address Self-Verification

After order creation, EzzyDelivery can send the customer a verification link.

**Flow:**
1. System generates `verification_token` (`secrets.token_urlsafe(32)`), valid for **7 days**
2. Customer opens link → `verify_location` view (no login required)
3. Customer confirms or updates their address (zone/street/building + map pin)
4. On confirmation:
   - `AddressVerification.customer_verified_at` set
   - `AddressVerification.verified_address` saved
   - `order.qnas_status` updated
   - `OrderVerificationLog` entry created

**Token states:**
- Valid → customer can verify
- Expired (> 7 days) → shows `verification_expired.html`
- Already used → shows `verification_success.html`
- Invalid token → shows `verification_error.html`

---

## Stage 2: Workforce Verifies Order

**Staff options:**
- **Verify** → `verification_status = 'verified'` — order can proceed to delivery
- **Reject** → `verification_status = 'rejected'` — client must fix and resubmit
- **Hold for Review** → `order_status = 'to_review'` — needs more info
- **Edit address** → update `DlAddressUpdate` with corrected address
- **Add comment** → internal note visible to staff only

**Address verification sub-options:**
- `address_verified = True / False`
- QNAS address lookup (Qatar National Address System) to confirm zone / street / building

**Rules:**
- Only `verification_status = 'verified'` orders can have delivery tasks published or drivers assigned
- Rejected orders are locked from delivery until re-verified

---

## Stage 3: Workforce Creates Delivery Task

**Staff options:**
- Select pickup location (fulfillment center or business pickup point)
- Set `dl_task_date` — scheduled delivery date
- Set `dl_price` — delivery fee charged to business
- Set `dl_category` / `dl_speed` to match order requirements

**System auto-sets:**
- `dl_task_status = 'for_review'`
- `task_status = 'dl_task_listed'`

**Auto-created records:**
- `ShippingLabel` — printable label with barcode
- `DeliveryTaskQRCode` — QR code for driver scanning

**Staff can also:**
- Bulk create tasks for multiple orders at once
- Print shipping label
- Print QR code for driver app scanning

---

## Stage 4: Task Published to Fleet

**Staff options:**
- **Publish** → `dl_task_publish = True`, `dl_task_status = 'pending'` — task visible to drivers
- **Keep unpublished** → drivers cannot see the task yet
- **Assign directly** → skip open driver pool, assign to a specific driver immediately

**dl_task_status values at this stage:**

| Status | Meaning |
|---|---|
| `for_review` | Task created, not yet published |
| `pending` | Published, waiting for driver to accept |

---

## Stage 5: Driver Assignment

**Staff options:**
- **Manually assign** specific driver → `dl_task_status = 'assigned'`
- **Let driver self-accept** from fleet app → `dl_task_status = 'accepted'`
- **Reassign** to a different driver (if previous driver rejected)

**Driver options (from fleet / mobile app):**
- **Accept** → `dl_task_status = 'accepted'`
- **Reject** → `dl_task_status = 'rejected'` — task returns to pool for reassignment

---

## Stage 6: Driver On The Road

Driver availability automatically syncs to `on_delivery` when task reaches any of these statuses:

| `dl_task_status` | Meaning | Driver Availability |
|---|---|---|
| `accepted` | Accepted, not yet moving | no change |
| `picked_up` | Package collected from pickup | → `on_delivery` |
| `start_ride` | Started driving | → `on_delivery` |
| `in_transit` | En route to customer | → `on_delivery` |
| `out_for_delivery` | Near customer location | → `on_delivery` |
| `contacted` | Spoke to customer, confirmed | no change |
| `non_reachable` | Customer not answering | no change |
| `address_pending` | Cannot locate address | no change |
| `customer_confirmation_pending` | Waiting for customer to confirm | no change |
| `customer_delaying` | Customer asked driver to wait | no change |
| `dl_pending_payment` | Waiting for COD payment | no change |

---

## Stage 7: Delivery Outcome

### Delivered — `dl_task_status = 'delivered'`
- `order_status` → `'delivered'`
- `delivered_at` = timestamp set automatically
- If fulfillment business: `fulfilled_at` = timestamp set automatically
- Driver availability → `'available'` (if no other active tasks remain)
- If COD order: `cod_collected = True`, `cod_collected_at` = now, amount added to `driver.cod_in_hand`

### Failed — `dl_task_status = 'failed'`
- `order_status` stays unchanged (not synced to failed)
- Driver availability → `'available'`
- Staff decides next action:
  - Reassign to another driver
  - Reschedule for a later date
  - Cancel the order

### Cancelled — `dl_task_status = 'cancelled'`
- `order_status` → `'cancelled'`
- Driver availability → `'available'`
- No further delivery actions possible

### Rejected — `dl_task_status = 'rejected'`
- Driver rejected before pickup
- Task returns to pool
- Staff must reassign to another driver

---

## Stage 8: COD Settlement (COD orders only)

### Driver side:
- Collects cash from customer at delivery
- `cod_collected = True`, amount recorded in `driver.cod_in_hand`
- Wallet service records delivery earnings

### Workforce options:

| Action | Result |
|---|---|
| **Collect cash from driver** | Creates `CODTransaction`, reduces `cod_in_hand`, `cod_status_by_staff = 'collected'` |
| **Verify COD** | `cod_status_by_staff = 'verified'` |
| **Flag dispute** | `cod_status_by_staff = 'disputed'` |
| **Generate settlement report** | Export per driver / per date period |

---

## Stage 9: Client Sees Final Status

**Business dashboard shows:**
- `order_status = 'delivered'` / `'cancelled'` / `'failed'`
- Full delivery timeline (created → verified → picked up → delivered)
- COD settlement status
- Delivery timestamps

**Client options post-delivery:**
- View delivery proof (photo / signature uploaded by driver)
- Download invoice / shipping label
- Request re-delivery (creates a new order)

---

## Status Fields Reference

| Field | Model | Purpose |
|---|---|---|
| `order_status` | `Order` | Overall order state |
| `verification_status` | `Order` | Address/data verified by staff |
| `task_status` | `Order` | Delivery task lifecycle stage |
| `dl_task_status` | `DeliveryTask` | Driver's real-time delivery status |
| `dl_task_publish` | `DeliveryTask` | Whether task is visible to drivers |
| `driver_availability` | `Driver` | `available` / `on_delivery` / `offline` |
| `cod_collected` | `DeliveryTask` | Whether COD cash was collected |
| `cod_status_by_staff` | `DeliveryTask` | COD settlement state |

### `order_status` values

| Value | Meaning |
|---|---|
| `to_review` | Newly created, awaiting verification |
| `ready_to_pickup` | Verified, task created, awaiting pickup |
| `out_for_delivery` | Driver on the way |
| `delivered` | Successfully delivered |
| `failed` | Delivery failed |
| `cancelled` | Cancelled by staff or client |

---

## Failure / Exception Paths

```
Driver Rejects Task
    → task_status back to 'pending'
    → Staff reassigns to another driver

Delivery Failed
    → order_status stays as-is
    → Staff options: reassign / reschedule / cancel

Order Cancelled (before pickup)
    → order_status = 'cancelled'
    → dl_task_status = 'cancelled'
    → DeliveryTask, DlAddressUpdate locked (on_delete=DO_NOTHING)
    → Must manually delete related records before order deletion

Address Rejected
    → verification_status = 'rejected'
    → Client must update and resubmit for re-verification
```

---

## Signal Chain (Automatic Side Effects)

```
Order saved (post_save)
    → creates DlAddressUpdate
    → creates OrderBarcode
    → creates AddressVerification
    → creates OrderStatusHistory entry

DeliveryTask saved (pre_save)
    → stores _old_dl_task_status for change detection
    → blocks status changes if order is cancelled

DeliveryTask saved (post_save)
    → auto-creates ShippingLabel (on creation)
    → auto-creates DeliveryTaskQRCode (on creation)
    → logs status change to OrderStatusHistory
    → syncs order_status from dl_task_status (delivered/cancelled)
    → syncs driver_availability (on_delivery / available)
```

---

*Last updated: 2026-02-26*
