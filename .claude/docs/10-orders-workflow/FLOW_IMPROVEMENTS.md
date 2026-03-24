# EzzyDelivery — Flow Audit & Improvements

Full review of the order lifecycle: what was found, what was fixed, and what remains.

---

## Status Key

| Badge | Meaning |
|---|---|
| ✅ DONE | Implemented and migrated |
| 🔲 PENDING | Not yet implemented |

---

## PRIORITY 1 — Critical Bugs

---

### ✅ BUG 1 — `cod_client_settled` field missing from model

**Files:** `delivery/models.py`, `fleet/wallet_service.py`

`wallet_service.py` called `.update(cod_client_settled=True, cod_client_settled_at=...)` but
neither field existed on `DeliveryTask`, causing a runtime crash when staff settled COD with a business.

**Fix applied:**
- Added `cod_client_settled = BooleanField(default=False)` to `DeliveryTask`
- Added `cod_client_settled_at = DateTimeField(null=True, blank=True)` to `DeliveryTask`
- Migration `delivery/0012` applied ✓

---

### ✅ BUG 2 — `cancel_order` blocked the wrong orders

**File:** `workforce/views.py` — `cancel_order()`

The guard `if order.order_status in ('publish', 'published')` blocked cancellation
of published orders (which is valid) while silently allowing cancellation of orders
where the driver had already physically picked up the package — with no driver
notification and no COD reversal.

**Fix applied:**
- Block `delivered` orders only (cannot cancel after delivery)
- Block if `delivery_task.dl_task_status` is in any active pickup state:
  `picked_up`, `start_ride`, `in_transit`, `out_for_delivery`, `contacted`
- Accept optional `cancellation_reason` + `cancellation_notes` from request body
- Records `cancelled_by`, `cancellation_reason`, `cancellation_notes` on Order
- Includes reason in `OrderVerificationLog` entry

---

### ✅ BUG 3 — `publish_task_to_fleets` skipped verification check

**File:** `workforce/views.py` — `publish_task_to_fleets()`

Staff could publish a delivery task to the driver pool even when
`order.verification_status != 'verified'`, meaning drivers could accept and
pick up orders with unverified or incorrect customer addresses.

**Fix applied:**
- Added guard: order must be `verification_status == 'verified'` before publishing
- Same guard added to `assign_driver_to_task()` — cannot assign driver to unverified order

---

## PRIORITY 2 — Missing Model Fields

---

### ✅ `failure_reason` + `failure_notes` on DeliveryTask

When a delivery fails, no record existed of why. Added:
- `failure_reason` — CharField with choices:
  `customer_not_home`, `address_not_found`, `customer_refused`, `customer_unreachable`,
  `vehicle_issue`, `wrong_address`, `customer_requested_reschedule`, `cod_amount_dispute`, `other`
- `failure_notes` — TextField for free-text detail

Migration `delivery/0012` applied ✓

---

### ✅ `rejection_reason` on DeliveryTask

When a driver rejects a task there was no record of why.
Added `rejection_reason = TextField(blank=True, null=True)`.

Migration `delivery/0012` applied ✓

---

### ✅ `failed_attempt_count` on DeliveryTask

No way to know how many times delivery had been attempted.
Added `failed_attempt_count = PositiveSmallIntegerField(default=0)`.

**Auto-incremented:** `delivery/signals.py` increments this via `.update()` every time
`dl_task_status` transitions to `failed`.

Migration `delivery/0012` applied ✓

---

### ✅ `reschedule_date` + `reschedule_reason` on DeliveryTask

No field to store a rescheduled delivery date after failure. Added:
- `reschedule_date = DateField(null=True, blank=True)`
- `reschedule_reason = CharField(max_length=255, null=True, blank=True)`

When set, `reschedule_date` is included in the customer WhatsApp failure notification.

Migration `delivery/0012` applied ✓

---

### ✅ `cancellation_reason` + `cancellation_notes` + `cancelled_by` on Order

No record of why an order was cancelled or who cancelled it. Added:
- `cancellation_reason` — CharField with choices:
  `client_request`, `address_issue`, `customer_unreachable`, `duplicate_order`,
  `out_of_stock`, `driver_issue`, `other`
- `cancellation_notes` — TextField
- `cancelled_by` — ForeignKey to User (SET_NULL)

Migration `orders/0038` applied ✓

---

## PRIORITY 3 — Missing Workflow Steps

---

### ✅ GAP 1 — Failed Delivery Workflow (partial)

**What existed:** Task marked `failed`. Nothing automatic happened.

**What is now implemented:**

```
Driver marks task 'failed'
        ↓
delivery/signals.py:
  - failed_attempt_count auto-incremented
  - Customer WhatsApp sent: "Delivery attempt unsuccessful" (includes failure_reason + reschedule_date if set)
        ↓
Staff action (manual, in workforce dashboard):
  - Set failure_reason + failure_notes on task
  - Set reschedule_date if rescheduling
  - Reset task to 'pending' via state machine (failed → pending) to re-assign driver
```

**Still pending:**
- Staff UI on the workforce order detail page to set `failure_reason` and `reschedule_date` inline
- Auto-escalation when `failed_attempt_count >= 3` (flag for manual review)
- Return-to-warehouse flow (see GAP 2)

---

### 🔲 GAP 2 — Return / Reverse Logistics Flow

**Status:** Not implemented.

When delivery fails repeatedly, the package must return to the business or warehouse.
No model or workflow exists for this yet.

**What is needed:**
- `return_status` field on `DeliveryTask`: `none` / `return_requested` / `in_return` / `returned`
- A reverse `DeliveryTask` (type `return`) or flag on the original task
- Workforce UI action: "Request Return"
- Warehouse receiving confirmation when package arrives back
- Customer and business notified of return with reason

---

### ✅ GAP 3 — Customer Notification System

**What existed:** Only one WhatsApp notification — address verification link on order creation.

**What is now implemented (`core/order_notifications.py`):**

| Event | Trigger | Message |
|---|---|---|
| `driver_assigned` | `dl_task_status → assigned` | "Your order has been assigned to a driver" |
| `out_for_delivery` | `dl_task_status → out_for_delivery` or `in_transit` | "Driver is on the way — have COD ready" |
| `delivered` | `dl_task_status → delivered` | "Your order has been delivered" |
| `delivery_failed` | `dl_task_status → failed` | "Delivery attempt unsuccessful — includes reason + reschedule date" |
| `order_cancelled` | `order_status → cancelled` | "Your order has been cancelled — includes reason" |

**How it works:**
- All notifications go via the existing n8n webhook (`N8N_WHATSAPP_WEBHOOK_URL`)
- Fire-and-forget — a notification failure never blocks the order save
- Wired into `delivery/signals.py` (task events) and `orders/signals.py` (cancellation)
- Uses `orders/CANCELLATION_REASON_CHOICES` and `delivery/FAILURE_REASON_CHOICES`
  to display human-readable reasons in messages

**Still pending:**
- Business-level toggle to enable/disable customer notifications per business
- "Driver is on the way" WhatsApp with live tracking link
- Order confirmation WhatsApp at creation time

---

### ✅ GAP 4 — Driver Notification on Task Assignment

**What existed:** `DriverNotification` model existed but was never populated on assignment.

**What is now implemented:**
- `delivery/signals.py` creates a `DriverNotification` record every time
  `dl_task_status` transitions to `assigned` and a driver is attached
- Notification: title `"New Task Assigned"`, type `delivery_assigned`
- Visible in driver dashboard notification bell immediately

**Still pending:**
- Push notification to driver mobile app (requires FCM token on driver profile)

---

### ✅ GAP 5 — State Machine for Status Transitions

**What existed:** Any actor could set any status at any time. No validation.

**What is now implemented (`delivery/state_machine.py`):**

Driver valid transitions:
```
assigned       → accepted, rejected
accepted       → picked_up, rejected
picked_up      → start_ride, in_transit, out_for_delivery, failed
start_ride     → in_transit, out_for_delivery, failed
in_transit     → out_for_delivery, contacted, non_reachable, address_pending,
                 customer_confirmation_pending, customer_delaying, dl_pending_payment, failed
out_for_delivery → contacted, non_reachable, address_pending,
                   customer_confirmation_pending, customer_delaying, dl_pending_payment, failed
contacted      → delivered, non_reachable, failed, dl_pending_payment
non_reachable  → contacted, customer_delaying, address_pending, failed
dl_pending_payment → delivered, failed
delivered      → (terminal — no further transitions)
failed         → (terminal for driver)
```

Staff valid transitions:
```
for_review  → pending, cancelled
pending     → assigned, cancelled
assigned    → pending, cancelled
accepted    → assigned, cancelled
failed      → pending, cancelled     ← staff can retry (reset to pool)
rejected    → pending, cancelled     ← staff can re-pool
any pickup  → cancelled              ← staff force-cancel
delivered   → (terminal)
cancelled   → (terminal)
```

**How enforcement works:**
- `delivery/signals.py` `delivery_task_pre_save` calls `can_transition()` before every save
- Invalid transitions are **silently blocked** (status reverts to old value, warning logged)
- Callers tag their intent with `instance._status_actor = 'staff'` or `'driver'`
- `ezzy_api/views.py` `driver_update_task_status` validates via `can_transition()` before
  saving and returns a clear API error response if transition is invalid
- `driver_accept_task` and `driver_reject_task` tagged as `actor='driver'`
- `assign_driver_to_task` and bulk assign in workforce tagged as `actor='staff'`

---

### ✅ GAP 6 — Race Condition on Task Assignment

**What existed:** Two staff members could simultaneously assign different drivers to
the same task. No row-level lock on the task during the assignment transaction.

**What is now implemented in `assign_driver_to_task()`:**
```python
with transaction.atomic():
    task = DeliveryTask.objects.select_related(...).select_for_update().get(id=task_id)
    # checks: not cancelled, verified, not already assigned to different driver
    task.driver = driver
    task.dl_task_status = 'assigned'
    task.save()
```
- `select_for_update()` locks the row for the duration of the transaction
- Guard: if `task.driver_id` is already set to a different driver, returns error with driver name
- JSON body parsed before the lock to minimise lock hold time

---

## PRIORITY 4 — Data & Reporting Gaps

---

### 🔲 No Delivery Attempt Log model

Each delivery attempt should produce a separate audit record.
`failed_attempt_count` tracks the count but not the details of each attempt.

**Still needed:**
```python
class DeliveryAttempt(models.Model):
    task          # FK DeliveryTask
    driver        # FK Driver
    attempted_at  # DateTimeField
    outcome       # delivered / failed / non_reachable
    failure_reason
    notes
    location_lat / location_lon
```

---

### 🔲 No SLA / Deadline Tracking alerts

`Order.deadline_date` exists but:
- No dashboard widget for overdue orders
- No staff alert when deadline passes
- No SLA breach rate in analytics

---

### 🔲 No COD Variance flag

`cod_collected_amount` exists on `DeliveryTask`.
No automatic flag when `cod_collected_amount != order.cod_amount`.
No staff approval flow for variances above a threshold.

---

### 🔲 No Driver Performance auto-score

`driver_rating` field exists but is not calculated.
No composite score from: success rate, on-time rate, COD accuracy.

---

## Summary Table

| # | Issue | Status | Type |
|---|---|---|---|
| 1 | `cod_client_settled` field missing | ✅ DONE | Bug fix |
| 2 | `cancel_order` wrong status guard | ✅ DONE | Bug fix |
| 3 | `publish_task_to_fleets` skips verification | ✅ DONE | Bug fix |
| 4 | `failure_reason` on DeliveryTask | ✅ DONE | Model field |
| 5 | `rejection_reason` on DeliveryTask | ✅ DONE | Model field |
| 6 | `failed_attempt_count` on DeliveryTask | ✅ DONE | Model field + signal |
| 7 | `reschedule_date` on DeliveryTask | ✅ DONE | Model field |
| 8 | `cancellation_reason` on Order | ✅ DONE | Model field |
| 9 | Failed delivery workflow (retry) | ✅ PARTIAL | Signal + state machine |
| 10 | Return / reverse logistics flow | 🔲 PENDING | Feature |
| 11 | Customer WhatsApp notifications | ✅ DONE | `core/order_notifications.py` |
| 12 | Driver notification on assignment | ✅ DONE | Signal → DriverNotification |
| 13 | State machine for status transitions | ✅ DONE | `delivery/state_machine.py` |
| 14 | Race condition on task assignment | ✅ DONE | `select_for_update` + atomic |
| 15 | Delivery attempt log model | 🔲 PENDING | New model |
| 16 | SLA / deadline tracking alerts | 🔲 PENDING | Feature |
| 17 | COD variance flag / approval | 🔲 PENDING | Feature |
| 18 | Driver performance auto-score | 🔲 PENDING | Feature |

---

## New Files Created

| File | Purpose |
|---|---|
| `delivery/state_machine.py` | Valid `dl_task_status` transition rules per actor (staff / driver) |
| `core/order_notifications.py` | WhatsApp customer notifications for order lifecycle events |

## Migrations Applied

| Migration | Changes |
|---|---|
| `delivery/0012` | Added 8 fields to DeliveryTask: `cod_client_settled`, `cod_client_settled_at`, `failure_reason`, `failure_notes`, `failed_attempt_count`, `reschedule_date`, `reschedule_reason`, `rejection_reason` |
| `orders/0038` | Added 3 fields to Order: `cancellation_reason`, `cancellation_notes`, `cancelled_by` |

---

*Last updated: 2026-02-28*
