# EzzyDelivery — Driver Workflow Guide

Complete step-by-step workflow for drivers across every use case and scenario.

---

## Table of Contents

1. [Account & Onboarding](#1-account--onboarding)
2. [Daily Login & Dashboard](#2-daily-login--dashboard)
3. [Receiving & Accepting Tasks](#3-receiving--accepting-tasks)
4. [Scenario A — Normal Delivery (No COD)](#scenario-a--normal-delivery-no-cod)
5. [Scenario B — COD Delivery](#scenario-b--cod-delivery)
6. [Scenario C — Customer Not Reachable](#scenario-c--customer-not-reachable)
7. [Scenario D — Failed Delivery](#scenario-d--failed-delivery)
8. [Scenario E — Pick & Drop](#scenario-e--pick--drop)
9. [Scenario F — Task Rejected by Driver](#scenario-f--task-rejected-by-driver)
10. [COD Submission to Admin](#10-cod-submission-to-admin)
11. [Earnings & Wallet](#11-earnings--wallet)
12. [Vehicle Management](#12-vehicle-management)
13. [Document Management](#13-document-management)
14. [Performance & Analytics](#14-performance--analytics)
15. [Driver API Reference (Mobile App)](#15-driver-api-reference-mobile-app)
16. [Status Reference](#16-status-reference)

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
- Pending notifications
- Recent task history

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
Body: { notes: "reason" }  (optional)
```

Result: `dl_task_status` → `rejected`
Task returns to the pool for reassignment.

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
> See [Section 10 — COD Submission](#10-cod-submission-to-admin).

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
```
POST /api/driver/tasks/{task_id}/complete/
Body: {
  status: "failed",
  cod_collected: false,
  notes: "3 attempts, customer unreachable, package returned to pickup"
}

dl_task_status: → failed
order_status: stays unchanged (staff decides next action)
driver_availability: on_delivery → available  (auto)
```

**What happens next (staff side):**
- Staff reviews failed task
- Options: reassign to another driver, reschedule, cancel order
- If COD was already collected (partial delivery attempt) → COD return process initiated

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

**Step 7 — Deliver**
```
POST /api/driver/tasks/{task_id}/complete/
Body: { status: "delivered", ... }
```

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
driver_availability: (no change)
```

**What happens next:**
- Task returns to pool (`pending`) or staff is notified
- Staff reassigns to another driver
- Repeated rejections may affect driver rating

---

## 10. COD Submission to Admin

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

## 11. Earnings & Wallet

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

## 12. Vehicle Management

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

## 13. Document Management

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

## 14. Performance & Analytics

### Performance Dashboard
Web: `/fleet/performance/`

Shows (filterable by period: today, week, month, custom):
- Total deliveries completed
- Total deliveries failed
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

## 15. Driver API Reference (Mobile App)

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
| `/api/driver/tasks/{id}/reject/` | POST | Reject task |
| `/api/driver/tasks/{id}/status/` | POST | Update task status |
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

### Task Completion Body
```json
POST /api/driver/tasks/{id}/complete/
{
  "status": "delivered",
  "cod_collected": true,
  "cod_amount_collected": 150,
  "notes": "Delivered to reception",
  "photo": <file>,
  "signature": <file>
}
```

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

## 16. Status Reference

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
pending  ←──────────────────────── (rejected → back here)
    ↓
assigned
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
    ↓
contacted
    ↓
delivered ✓       ← driver_availability → available (auto)
                  ← order_status → delivered (auto)
                  ← earnings credited (auto)

OR

non_reachable ──→ contacted ──→ delivered
              ──→ customer_delaying
              ──→ address_pending
              ──→ failed ✗      ← driver_availability → available

OR

cancelled ✗       ← driver_availability → available
rejected          ← task returns to pool
```

### COD Wallet States

```
cod_in_hand = 0                    → Clear
cod_in_hand < 80% of credit_limit  → Normal
cod_in_hand ≥ 80% of credit_limit  → WARNING — submit COD soon
cod_in_hand ≥ credit_limit         → BLOCKED — cannot accept COD tasks
```

---

*Last updated: 2026-02-26*
