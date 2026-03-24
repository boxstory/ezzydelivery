# EzzyDelivery — Driver Workflow Guide

Complete step-by-step workflow for drivers across every use case and scenario.

---

## Table of Contents

1. [Account & Onboarding](#1-account--onboarding)
2. [Daily Login & Dashboard](#2-daily-login--dashboard)
3. [Receiving & Accepting Tasks](#3-receiving--accepting-tasks)
4. [Status Transition Rules (State Machine)](#4-status-transition-rules-state-machine)
5. [Scenario A — Normal Delivery (No COD)](#scenario-a--normal-delivery-no-cod)
6. [Scenario B — COD Delivery](#scenario-b--cod-delivery)
7. [Scenario C — Customer Not Reachable](#scenario-c--customer-not-reachable)
8. [Scenario D — Failed Delivery](#scenario-d--failed-delivery)
9. [Scenario E — Pick & Drop](#scenario-e--pick--drop)
10. [Scenario F — Task Rejected by Driver](#scenario-f--task-rejected-by-driver)
11. [COD Submission to Admin](#11-cod-submission-to-admin)
12. [Earnings & Wallet](#12-earnings--wallet)
13. [Vehicle Management](#13-vehicle-management)
14. [Document Management](#14-document-management)
15. [Performance & Analytics](#15-performance--analytics)
16. [Driver API Reference (Mobile App)](#16-driver-api-reference-mobile-app)
17. [Status Reference](#17-status-reference)

---

## 1. Account & Onboarding

### Step 1 — Registration
- Driver registers via EzzyDelivery onboarding
- A **User** account is created, linked to a **Driver** profile
- Initial `driver_status = 'pending'`

### Step 2 — Profile Completion
Driver must complete:
- Full name, phone, WhatsApp number
- Languages spoken:
  - `arabic`, `english`, `hindi`, `philippine`, `other`
- Driver bio (optional)
- Qatar ID / license number
- Preferred zone groups (areas where they prefer to work)

### Step 3 — Document Upload
Required documents at `/fleet/documents/`:

| Document Type | Description |
|---|---|
| `QID` | Qatar National ID |
| `Driving License` | Valid Qatar driving license |
| `Passport` | Passport copy |
| `National Identification` | Other national ID |

Upload at: `/fleet/documents/upload/{driver_id}/`

### Step 4 — Vehicle Registration
Register at least one vehicle at `/fleet/vehicle_add/`

| Vehicle Type | Use Case |
|---|---|
| `bike` | Small packages, fast delivery |
| `car` | Standard deliveries |
| `van` | Bulk / multiple orders |
| `pickup` | Standard heavy items |
| `pickup3ton` | Heavy 3-ton loads |
| `pickup_big` | Oversized items |

### Step 5 — Account Approval
Staff reviews documents and vehicle.
`driver_status` changes:

```
pending → processing → approved
                    ↘ rejected (if issues)
```

Other statuses:
- `blocked` — account blocked by admin
- `suspended` — temporarily suspended

> Only `approved` drivers can accept tasks and appear in assignment lists.

---

## 2. Daily Login & Dashboard

### Web Login
Go to `/fleet/dashboard/`

### Mobile App Login
```
POST /api/driver/login/
Body: { username, password }
Returns: { token, driver_id, driver_status }
```

### Dashboard Shows
- Current driver availability status
- Active task (if any)
- COD in hand balance
- Today's earnings
- Wallet status (available credit)
- Pending notifications (in-app bell icon)
- Recent task history

### Notifications
The system creates in-app notifications for key events:
- **New task assigned** — when staff assigns a task directly to you
- Bell icon in dashboard shows unread count

### Setting Availability
Driver availability options:

| Status | Meaning |
|---|---|
| `available` | Ready to receive tasks |
| `on_delivery` | Currently on active delivery (auto-set) |
| `on_break` | Taking a break |
| `returning` | Returning from delivery |
| `offline` | Not working |

> `on_delivery` is **automatically set** by the system when task reaches `picked_up`, `start_ride`, `in_transit`, or `out_for_delivery` status.
> `available` is **automatically restored** when task reaches a terminal status (`delivered`, `failed`, `cancelled`, `rejected`) — only if no other active tasks remain.

---

## 3. Receiving & Accepting Tasks

### How Tasks Reach a Driver

**Path 1 — Staff Directly Assigns**
1. Staff selects driver from fleet list
2. Task `dl_task_status` → `assigned`
3. Driver sees task in dashboard immediately
4. **In-app notification created:** "New Task Assigned" — visible in notification bell
5. **Customer WhatsApp sent:** "Your order has been assigned to a driver"

**Path 2 — Driver Self-Accepts from Pool**
1. Staff publishes task (`dl_task_publish = True`)
2. Task appears in fleet pool (`dl_task_status = 'pending'`)
3. Driver browses available tasks and accepts

**Path 3 — QR Code Scan**
1. Driver scans package QR code at pickup location
2. System matches QR to task
3. Task linked to driver automatically
- Web: `/fleet/tasks/take-scan/`
- Scan process: `/fleet/pickup/scanner/`

### Viewing Available Tasks
Web: `/fleet/tasks/`
API: `GET /api/driver/tasks/?status=pending`

Filter options:
- `status` — filter by task status
- `date` — filter by task date

### Accepting a Task

**Web:** `/fleet/tasks/accept/`

**API:**
```
POST /api/driver/tasks/{task_id}/accept/
Headers: Authorization: Token {driver_token}
Returns: { success, task }
```

Result: `dl_task_status` → `accepted`

### Rejecting a Task

**API:**
```
POST /api/driver/tasks/{task_id}/reject/
Headers: Authorization: Token {driver_token}
Body: { notes: "reason for rejection" }  (optional)
```

Result: `dl_task_status` → `rejected`

> The `notes` field is saved as `rejection_reason` on the task so staff can see why it was rejected.

Task returns to pool for reassignment by staff (`rejected → pending`).

---

## 4. Status Transition Rules (State Machine)

The system enforces **strict status transition rules**. Attempting an invalid transition will return an error response instead of saving.

### Valid Driver Transitions

| Current Status | Allowed Next Statuses |
|---|---|
| `assigned` | `accepted`, `rejected` |
| `accepted` | `picked_up`, `rejected` |
| `picked_up` | `start_ride`, `in_transit`, `out_for_delivery`, `failed` |
| `start_ride` | `in_transit`, `out_for_delivery`, `failed` |
| `in_transit` | `out_for_delivery`, `contacted`, `non_reachable`, `address_pending`, `customer_confirmation_pending`, `customer_delaying`, `dl_pending_payment`, `failed` |
| `out_for_delivery` | `contacted`, `non_reachable`, `address_pending`, `customer_confirmation_pending`, `customer_delaying`, `dl_pending_payment`, `failed` |
| `contacted` | `delivered`, `non_reachable`, `failed`, `dl_pending_payment` |
| `non_reachable` | `contacted`, `customer_delaying`, `address_pending`, `failed` |
| `address_pending` | `contacted`, `non_reachable`, `failed` |
| `customer_confirmation_pending` | `contacted`, `non_reachable`, `failed` |
| `customer_delaying` | `contacted`, `failed` |
| `dl_pending_payment` | `delivered`, `failed` |
| `delivered` | *(terminal — no transitions)* |
| `failed` | *(terminal for driver — staff handles retry)* |
| `rejected` | *(terminal for driver)* |
| `cancelled` | *(terminal — cancelled by staff)* |

### What Happens on Invalid Transition

If you attempt an invalid transition via the API:

```json
HTTP 400
{
  "success": false,
  "error": "Invalid transition 'delivered' → 'picked_up' for driver. Status 'delivered' is terminal."
}
```

### Staff Can Override / Retry

Staff (workforce dashboard) have additional transitions not available to drivers:
- `failed → pending` — retry delivery with new or same driver
- `rejected → pending` — re-pool rejected task
- Force cancel from any active status

---

## Scenario A — Normal Delivery (No COD)

**Order type:** `normal_delivery`, `cod_amount = 0`

---

**Step 1 — Accept Task**
```
dl_task_status: pending → accepted
driver_availability: (no change yet)
```

**Step 2 — Go to Pickup Location**
Navigate to the pickup address shown in task details.

**Step 3 — Pick Up Package**
Scan QR code or confirm pickup manually.
```
POST /api/driver/tasks/{task_id}/status/
Body: { status: "picked_up" }

dl_task_status: accepted → picked_up
driver_availability: available → on_delivery  ← AUTO
```

**Step 4 — Start Ride**
```
POST /api/driver/tasks/{task_id}/status/
Body: { status: "start_ride" }

dl_task_status: picked_up → start_ride
driver_availability: on_delivery (stays)
```

**Step 5 — In Transit**
```
POST /api/driver/tasks/{task_id}/status/
Body: { status: "in_transit" }

dl_task_status: start_ride → in_transit
```

**Step 6 — Out for Delivery**
Approaching the customer's location.
```
POST /api/driver/tasks/{task_id}/status/
Body: { status: "out_for_delivery" }

dl_task_status: in_transit → out_for_delivery
```
> **Customer WhatsApp sent automatically:** "Your driver is now heading to your address — please have COD ready" (with driver phone number)

**Step 7 — Contact Customer**
```
POST /api/driver/tasks/{task_id}/status/
Body: { status: "contacted", notes: "Customer confirmed, coming down" }

dl_task_status: out_for_delivery → contacted
```

**Step 8 — Complete Delivery**
```
POST /api/driver/tasks/{task_id}/complete/
Body: {
  status: "delivered",
  cod_collected: false,
  photo: <file>,         (optional proof photo)
  signature: <file>,     (optional signature)
  notes: "Delivered to reception"
}

dl_task_status: contacted → delivered
order_status: → delivered  (auto-synced)
delivered_at: → timestamp  (auto-set)
driver_availability: on_delivery → available  (auto, if no other tasks)
earnings_processed: → true
driver_earnings: → credited to pending_earnings
```

> **Customer WhatsApp sent automatically:** "Your order has been successfully delivered"

**Earnings recorded:**
- Normal delivery: fixed **10 QR** credited to `pending_earnings`
- `WalletTransaction` created with type `earning`

---

## Scenario B — COD Delivery

**Order type:** `normal_delivery`, `cod_amount > 0`

> Before accepting a COD task, the system checks:
> `driver.cod_in_hand < driver.credit_limit`
> If wallet is blocked (COD in hand ≥ credit limit), driver **cannot accept** new COD tasks.

---

**Steps 1–7:** Same as Scenario A (accept → pickup → in_transit → contacted)

> **Customer WhatsApp sent at `out_for_delivery`:** "Driver is on the way — please have **{amount} QAR** cash ready"

**Step 8 — Collect Cash from Customer**
Driver collects the exact COD amount from customer.

**Step 9 — Complete Delivery with COD**
```
POST /api/driver/tasks/{task_id}/complete/
Body: {
  status: "delivered",
  cod_collected: true,
  cod_amount_collected: 150,   (actual amount received in QAR)
  photo: <file>,
  notes: "Delivered and collected 150 QAR"
}

dl_task_status: → delivered
cod_collected: → true
cod_collected_at: → timestamp  (auto-set)
cod_collected_amount: → 150
driver.cod_in_hand: + 150   (increases)
order_status: → delivered
```

> **Customer WhatsApp sent:** "Your order has been delivered. COD collected: 150 QAR"

**Wallet Impact:**
```
cod_in_hand  ↑ (increases — driver now holds this cash)
wallet_balance ↓ (decreases — liability increases)
```

**WalletTransaction created:**
- Type: `cod_collection`
- Amount: 150 QAR

**Wallet Warning Thresholds:**
- `is_wallet_warning` = True when COD in hand ≥ 80% of credit limit
- `is_wallet_blocked` = True when COD in hand ≥ credit limit (5000 QR default)

> When wallet is blocked, driver **must submit COD** to admin before accepting new COD orders.
> See [Section 11 — COD Submission](#11-cod-submission-to-admin).

---

## Scenario C — Customer Not Reachable

Driver arrives but cannot contact the customer.

---

**Step 1–6:** Accept → pickup → in_transit → out_for_delivery

**Step 7 — Mark Not Reachable**
```
POST /api/driver/tasks/{task_id}/status/
Body: { status: "non_reachable", notes: "Called 3 times, no answer" }

dl_task_status: out_for_delivery → non_reachable
```

**Step 8 — Wait for Instructions**
Staff sees the status change in workforce dashboard.
Staff options:
- Contact customer and update driver
- Reschedule delivery
- Mark as failed

**Step 9a — Customer Reached (resume delivery)**
```
POST /api/driver/tasks/{task_id}/status/
Body: { status: "contacted", notes: "Customer called back, coming down" }

dl_task_status: non_reachable → contacted
```
Then proceed to complete (Scenario A Step 8).

**Step 9b — Customer Delaying**
```
POST /api/driver/tasks/{task_id}/status/
Body: { status: "customer_delaying", notes: "Customer asked to wait 30 min" }

dl_task_status: → customer_delaying
```

**Step 9c — Address Cannot Be Found**
```
POST /api/driver/tasks/{task_id}/status/
Body: { status: "address_pending", notes: "Building not found in zone 42" }

dl_task_status: → address_pending
```
Staff will update address and notify driver to retry.

---

## Scenario D — Failed Delivery

All attempts exhausted, delivery cannot be completed.

---

**Step 1–7:** Accept → pickup → attempted delivery statuses

**Step 8 — Mark as Failed**

When marking a delivery as failed, include the `failure_reason` so staff and the customer can be informed:

```
POST /api/driver/tasks/{task_id}/complete/
Body: {
  status: "failed",
  failure_reason: "customer_unreachable",
  cod_collected: false,
  notes: "3 attempts, customer unreachable, package returned to pickup"
}

dl_task_status: → failed
failed_attempt_count: → auto-incremented  ← AUTO
order_status: stays unchanged (staff decides next action)
driver_availability: on_delivery → available  (auto)
```

> **Customer WhatsApp sent automatically:** "We were unable to deliver your order — Reason: Customer unreachable. Our team will contact you."
> If staff has set a `reschedule_date`, it will be included: "Rescheduled for: 05 Mar 2026"

### Failure Reason Codes

| Code | When to Use |
|---|---|
| `customer_not_home` | Customer wasn't at the address |
| `address_not_found` | Address does not exist or cannot be located |
| `customer_refused` | Customer refused to accept the package |
| `customer_unreachable` | Could not reach customer by phone |
| `vehicle_issue` | Driver's vehicle had a breakdown or problem |
| `wrong_address` | Address on the order is incorrect |
| `customer_requested_reschedule` | Customer asked for a different delivery time |
| `cod_amount_dispute` | Customer disputes the COD amount |
| `other` | Use notes field to explain |

### Failed Attempt Tracking

- `failed_attempt_count` increments automatically every time a task transitions to `failed`
- This count is visible to staff and is used to decide when to escalate (e.g., 3+ failed attempts)

### What Happens Next (Staff Side)

After marking failed:
1. Staff reviews `failure_reason` and `failure_notes`
2. Staff contacts customer or business if needed
3. Staff may set `reschedule_date` on the task
4. Staff resets task to `pending` via the state machine (`failed → pending`)
5. Task is reassigned to same or different driver
6. `failed_attempt_count` is preserved — not reset — so staff can track history

**If package was picked up but not delivered:**
- Driver must return package to pickup location
- Staff may create a new task or cancel

---

## Scenario E — Pick & Drop

**Order type:** `pick_and_drop`
Driver picks up from one address and drops at another — no business warehouse involved.

---

**Step 1 — Accept Task**
Task shows two addresses:
- **Pickup address** — where to collect from
- **Delivery address** — customer's address

**Step 2 — Go to Pickup Address**
Navigate to pickup address (not a business warehouse — could be a person's home or shop).

**Step 3 — Pick Up**
```
POST /api/driver/tasks/{task_id}/status/
Body: { status: "picked_up" }

driver_availability: → on_delivery
```

**Steps 4–6:** `start_ride` → `in_transit` → `out_for_delivery`

> **Customer WhatsApp sent at `out_for_delivery`:** "Your driver is on the way"

**Step 7 — Deliver**
```
POST /api/driver/tasks/{task_id}/complete/
Body: { status: "delivered", ... }
```

> **Customer WhatsApp sent:** "Your order has been delivered"

**Earnings for Pick & Drop:**
- **80% of `dl_price`** (delivery fee set by staff)
- Higher than normal delivery — reflects the extra pickup complexity
- Rate may vary by zone-to-zone based on `ZoneEarningsRate`

---

## Scenario F — Task Rejected by Driver

Driver receives assigned task but cannot accept it.

---

**Step 1 — Reject Task**
```
POST /api/driver/tasks/{task_id}/reject/
Body: { notes: "Too far, out of my zone" }

dl_task_status: assigned → rejected
rejection_reason: saved from notes field
driver_availability: (no change)
```

> The `notes` text is stored in `rejection_reason` on the task. Staff can see the reason in the workforce dashboard when reviewing rejected tasks.

**What happens next:**
- Staff sees `rejection_reason` in the task detail
- Staff resets task to `pending` (`rejected → pending`) for reassignment
- Staff assigns to another driver
- Repeated rejections may affect driver rating

---

## 11. COD Submission to Admin

When driver has accumulated COD cash, it must be submitted to EzzyDelivery.

### When to Submit
- When `cod_in_hand` is approaching the credit limit (5000 QR default)
- System shows warning when usage ≥ 80%
- Driver **cannot accept new COD tasks** when wallet is fully blocked

### Checking COD Balance
Web: `/fleet/cod_collection/`
API: `GET /api/driver/statistics/`

Shows:
- `cod_in_hand` — total cash currently held
- `credit_limit` — maximum allowed
- `available_credit` — remaining before blocked
- `wallet_usage_percentage`

### Submitting COD to Admin

**Web:** `/fleet/cod_submission/`

**Steps:**
1. Go to `/fleet/cod_submission/`
2. Enter amount to submit (must be ≤ `cod_in_hand`)
3. Select which deliveries this covers
4. Submit — admin receives notification

**Result:**
```
WalletTransaction created:
  type: cod_driver_settle
  amount: submitted amount

driver.cod_in_hand:    ↓ (decreases)
driver.wallet_balance: ↑ (increases)
cod_settled = True on covered DeliveryTasks
cod_settled_at = timestamp
```

### Exporting COD Report
Web: `/fleet/cod_export/`
- Export as CSV or PDF
- Filter by date range

---

## 12. Earnings & Wallet

### How Earnings Are Calculated

| Order Type | Earning |
|---|---|
| Normal Delivery | Fixed **10 QR** per completed delivery |
| Pick & Drop | **80% of `dl_price`** (delivery fee) |

Earnings are calculated when:
`dl_task_status` → `delivered` AND `earnings_processed = True`

### Earnings States

```
Task Delivered
      ↓
earnings_processed = True
driver.pending_earnings ↑
driver.total_earnings ↑
WalletTransaction (type: earning) created
      ↓
Staff Generates Settlement (period_start → period_end)
      ↓
Settlement: pending → approved → paid
      ↓
On Payment:
  driver.pending_earnings ↓
  WalletTransaction (type: settlement) created
```

### Viewing Earnings

| Page | URL | Shows |
|---|---|---|
| Earnings breakdown | `/fleet/earnings/` | Earnings by period, per task |
| Transaction history | `/fleet/transactions/` | All wallet transactions |
| Finance summary | `/fleet/finance/` | Overall financial overview |
| Performance | `/fleet/performance/` | Stats, ratings, delivery counts |

### Transaction Types You'll See

| Type | Meaning |
|---|---|
| `earning` | Payment for completed delivery |
| `settlement` | Payout received from EzzyDelivery |
| `cod_collection` | COD cash collected from customer |
| `cod_driver_settle` | COD submitted to admin |
| `bonus` | Performance bonus |
| `deduction` | Penalty or deduction |
| `adjustment` | Manual correction by admin |

### Wallet Limits
- `credit_limit` — default 5000 QR (can be adjusted by admin)
- `available_credit` = `credit_limit` - `cod_in_hand`
- Warning at 80% usage
- Blocked at 100% usage

---

## 13. Vehicle Management

### Adding a Vehicle
Web: `/fleet/vehicle_add/`

Required fields:
- Vehicle type (bike, car, van, pickup, pickup3ton, pickup_big)
- Plate number
- Vehicle make / model
- Registration year
- Insurance expiry

### Updating a Vehicle
Web: `/fleet/vehicle/{vehicle_id}/update/`

**Security:** System verifies the vehicle belongs to the requesting driver (IDOR protection).

### Deleting a Vehicle
Web: `/fleet/vehicle_delete/{driver_id}/{vehicle_id}/`

> Cannot delete vehicle if it is linked to an active delivery task.

### Vehicle Status
- `active` — in use
- `inactive` — not in use
- `maintenance` — under repair

Only `active` vehicles appear in task assignments.

---

## 14. Document Management

### Uploading Documents
Web: `/fleet/documents/upload/{driver_id}/`

Required documents:
- QID (Qatar National ID)
- Driving License
- Passport

### Updating a Document
Web: `/fleet/documents/{driver_id}/{doc_id}/update`

### Deleting a Document
Web: `/fleet/documents/{driver_id}/{doc_id}/delete`

**Security:** System verifies document belongs to requesting driver.

### Document Status
Documents are reviewed by staff after upload. Status affects account approval.

---

## 15. Performance & Analytics

### Performance Dashboard
Web: `/fleet/performance/`

Shows (filterable by period: today, week, month, custom):
- Total deliveries completed
- Total deliveries failed
- Failed attempt count (total across all tasks)
- Success rate (%)
- Average rating
- Total earnings
- COD collected
- Active task time

### Analytics
Web: `/fleet/analytics/`

Charts and trends:
- Daily/weekly delivery volume
- Earnings over time
- Zone performance breakdown
- On-time delivery rate

### Reports
Web: `/fleet/reports/`

Export options:
- Delivery report (CSV/PDF)
- Earnings report
- COD report

### Activity Log
Every driver action is logged automatically:

| Activity | Trigger |
|---|---|
| `task_taken` | Task accepted |
| `task_accepted` | Confirmed acceptance |
| `task_picked_up` | Package picked up |
| `task_start_ride` | Ride started |
| `task_out_delivery` | Out for delivery |
| `task_delivered` | Delivered successfully |
| `task_failed` | Delivery failed |
| `task_contacted` | Customer contacted |
| `task_non_reachable` | Customer not reachable |
| `cod_collected` | COD collected from customer |
| `cod_submitted` | COD submitted to admin |
| `earning_credited` | Earnings recorded |
| `settlement` | Payout received |
| `login` / `logout` | Session events |
| `document_uploaded` | Document uploaded |
| `vehicle_added` | Vehicle registered |
| `pickup_scanned` | QR scan at pickup |

---

## 16. Driver API Reference (Mobile App)

All API endpoints require:
```
Header: Authorization: Token {driver_token}
Base URL: /api/
```

### Authentication

| Endpoint | Method | Description |
|---|---|---|
| `/api/driver/login/` | POST | Login, returns auth token |
| `/api/driver/profile/` | GET | Get driver profile + vehicles + documents |

### Task Management

| Endpoint | Method | Description |
|---|---|---|
| `/api/driver/tasks/` | GET | List tasks (filter: `?status=`, `?date=`) |
| `/api/driver/tasks/{id}/` | GET | Task detail with order info |
| `/api/driver/tasks/{id}/accept/` | POST | Accept task |
| `/api/driver/tasks/{id}/reject/` | POST | Reject task (include notes as rejection_reason) |
| `/api/driver/tasks/{id}/status/` | POST | Update task status (state machine enforced) |
| `/api/driver/tasks/{id}/complete/` | POST | Complete task (delivered/failed) |
| `/api/driver/tasks/{id}/documents/` | GET | List task documents |
| `/api/driver/tasks/{id}/documents/upload/` | POST | Upload proof photo/signature |

### Location & Stats

| Endpoint | Method | Description |
|---|---|---|
| `/api/driver/location/` | POST | Update GPS coordinates |
| `/api/driver/statistics/` | GET | Performance stats (`?days=7`) |

### Status Update Body
```json
POST /api/driver/tasks/{id}/status/
{
  "status": "picked_up",
  "notes": "Optional note"
}
```

Valid status values for update:
`accepted`, `picked_up`, `start_ride`, `out_for_delivery`, `in_transit`,
`contacted`, `non_reachable`, `address_pending`, `customer_confirmation_pending`,
`customer_delaying`, `dl_pending_payment`

**State machine error response (invalid transition):**
```json
HTTP 400
{
  "success": false,
  "error": "Invalid transition 'delivered' → 'accepted' for driver. Status 'delivered' is terminal."
}
```

### Task Completion Body
```json
POST /api/driver/tasks/{id}/complete/
{
  "status": "delivered",
  "cod_collected": true,
  "cod_amount_collected": 150,
  "notes": "Delivered to reception",
  "photo": "<file>",
  "signature": "<file>"
}
```

For failed delivery:
```json
{
  "status": "failed",
  "failure_reason": "customer_unreachable",
  "cod_collected": false,
  "notes": "3 attempts, no answer"
}
```

Valid `failure_reason` values:
`customer_not_home`, `address_not_found`, `customer_refused`, `customer_unreachable`,
`vehicle_issue`, `wrong_address`, `customer_requested_reschedule`, `cod_amount_dispute`, `other`

Valid completion statuses: `delivered`, `failed`, `cancelled`, `rejected`

### Location Update Body
```json
POST /api/driver/location/
{
  "latitude": 25.285447,
  "longitude": 51.530956,
  "timestamp": "2026-02-26T10:30:00Z",
  "accuracy": 5.0,
  "speed": 40.0
}
```

---

## 17. Status Reference

### `driver_status`
| Value | Meaning |
|---|---|
| `pending` | Account submitted, awaiting review |
| `processing` | Documents under review |
| `approved` | Active, can receive tasks |
| `rejected` | Application rejected |
| `blocked` | Blocked by admin |
| `suspended` | Temporarily suspended |

### `driver_availability`
| Value | Meaning | Set By |
|---|---|---|
| `offline` | Not working | Manual |
| `available` | Ready for tasks | Manual / Auto (on task terminal) |
| `on_delivery` | Active delivery | Auto (on picked_up/start_ride/in_transit/out_for_delivery) |
| `on_break` | Break | Manual |
| `returning` | Returning | Manual |

### `dl_task_status` — Full Flow

```
for_review
    ↓
pending  ←──────────────────────── (failed/rejected → back here, by staff)
    ↓
assigned           ← DriverNotification created
                   ← Customer WhatsApp: "assigned to driver"
    ↓
accepted
    ↓
picked_up         ← driver_availability → on_delivery
    ↓
start_ride        ← driver_availability → on_delivery
    ↓
in_transit        ← driver_availability → on_delivery
    ↓
out_for_delivery  ← driver_availability → on_delivery
                  ← Customer WhatsApp: "driver on the way"
    ↓
contacted
    ↓
delivered ✓       ← driver_availability → available (auto)
                  ← order_status → delivered (auto)
                  ← Customer WhatsApp: "order delivered"
                  ← earnings credited (auto)

OR

non_reachable ──→ contacted ──→ delivered
              ──→ customer_delaying
              ──→ address_pending
              ──→ failed ✗      ← failed_attempt_count++ (auto)
                                ← Customer WhatsApp: "delivery failed + reason"
                                ← driver_availability → available
                                ← staff resets to pending for retry

OR

cancelled ✗       ← driver_availability → available
                  ← Customer WhatsApp: "order cancelled"
rejected          ← rejection_reason saved
                  ← staff resets to pending for reassignment
```

### Customer WhatsApp Notifications Summary

| Status Transition | Customer Message |
|---|---|
| `→ assigned` | "Your order has been assigned to a driver" |
| `→ out_for_delivery` or `→ in_transit` | "Driver is on the way — have COD ready (+ driver phone)" |
| `→ delivered` | "Your order has been delivered" |
| `→ failed` | "Delivery attempt unsuccessful — reason + reschedule date if set" |
| `order_status → cancelled` | "Your order has been cancelled — reason if set" |

> All notifications are sent via WhatsApp automatically. No driver action required.
> If `N8N_WHATSAPP_WEBHOOK_URL` is not configured, notifications are silently skipped.

### COD Wallet States

```
cod_in_hand = 0                    → Clear
cod_in_hand < 80% of credit_limit  → Normal
cod_in_hand ≥ 80% of credit_limit  → WARNING — submit COD soon
cod_in_hand ≥ credit_limit         → BLOCKED — cannot accept COD tasks
```

### Failed Attempt Count

```
Task → failed:  failed_attempt_count ++ (auto-incremented by system)
                never reset — tracks total lifetime failures per task
1 failure:      Staff may retry (reset to pending)
3+ failures:    Staff escalation recommended
```

---

*Last updated: 2026-02-28*
