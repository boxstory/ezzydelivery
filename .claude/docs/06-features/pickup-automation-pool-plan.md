# First-Mile Pickup Pool — Implementation Plan

Purpose: Give the driver app a dedicated first-mile Pickup section. When a non-fulfilment
client creates an order, a pickup task is auto-created so a driver collects the goods from the
client's location; the client's config decides whether an assigned driver collects it or it goes
to a public pool, and how the order is routed after collection (drop at hub, deliver by self, or
transfer to another driver).
Used by: orders, delivery, fleet, business, workforce, warehouse.
Notes: **BUILT & DEPLOYED 2026-07-20/21.** All 10 decisions resolved (§10); build-time deltas
in §11. Implementation: `delivery/models.py` (PickupTask), `delivery/services/pickup.py`,
`delivery/selectors.py`, fleet pickup views/URLs (`/fleet/pickups/`), `driver_pickups_pwa.html`
+ `fleet-pickup.css`, workforce config `/workforce/pickup-automation/` (incl. per-client fleet
management), staff pool console `/workforce/pickups/` (assign/reassign), sidebar "Pickup"
section (desktop + mobile), tests in `delivery/tests_pickup.py` (24 green).
Feature is OFF for every business until staff enable it on the config page.

---

## 0. What this is (and is NOT)

- **FIRST-MILE PICKUP**: driver collects **from the client**, then routes the order.
- **NOT last-mile delivery** (store → customer) — that is the existing DeliveryTask flow, reused
  downstream but not replaced here.
- The pickup task is **its own record** with **its own tab** in the driver app — never merged
  into the delivery task tabs.
- **No COD at the pickup leg.** COD is collected from the *customer at delivery*, never from the
  client at pickup — so there is no cash custody to move during pickup or transfer. (Correction
  to an earlier draft.)

---

## 1. Target behavior

### 1.1 Creation (at order creation)
When a client creates an order, create a `PickupTask` unless the order's pickup location is a
fulfilment centre (`PickupLocation.is_fulfilment_center`, business/models.py:719 — goods already
at the warehouse, no collection needed).
- Origin = client collection point: `PickupLocation.pickup_lat/pickup_lon` (business/models.py:709-710).
- Destination = a **single fixed EzzyDelivery hub/warehouse** (§10-D2).

### 1.2 Who sees it — pickup mode (client config)
- **Assigned** → shows only to the client's active `DriverDirectory` drivers, in their Pickup
  section. No distance gate.
- **Public pool** → shows in the Pickup section of **all active approved drivers** — **no distance
  filter** (§10-D6). Every approved driver sees every public pickup.

### 1.3 Route after collection (client config, preset)
The **client's config presets the disposition** (§10-D1) — the driver executes it, does not choose:
- **Drop at hub** → driver drops at the fixed hub; on drop the system **auto-creates the last-mile
  delivery task** (§10-D5).
- **Deliver by self** → the pickup task rolls straight into a DeliveryTask assigned to the **same
  driver** → customer. No hub trip.
- **Transfer to another driver** → pickup driver picks the delivery driver from a **manual picker
  (any approved driver)** (§10-D4); **both drivers must confirm** the hand-off (§10-D7) before a
  DeliveryTask is created assigned to the target.

---

## 2. Verified constraints

1. **No first-mile pickup model exists** except `HubPickupBatch` (delivery/models.py:111-184) — a
   staff-created, batch-oriented client→hub ride; nearest pattern (status chain
   `pending→assigned→accepted→in_progress→arrived→collected→at_hub`, L145-154) but not per-order,
   not auto-created, no client mode choice.
2. **Driver PWA has no Pickup tab.** `driver_tasks` (fleet/views.py:2552) has 4 delivery tabs
   (driver_tasks_pwa.html:24-55). Bottom nav = 5 items: Home · Tasks · Scan · COD · Profile
   (pwa_base.html:86-126). `hub_batches` is passed but never rendered (fleet/views.py:2773) — a
   clean insertion point.
3. **`PickupLocation.pickup_lat/pickup_lon`** is the client collection coordinate
   (business/models.py:709-710), already on driver cards (driver_tasks_pwa.html:144-146).
4. **Fulfilment detection ready-made**: `is_fulfilment_center` (business/models.py:719); order
   auto-assigns pickup/hub locations at create (orders/signals.py:447-509).
5. **`pick_and_drop` is a pricing label, not a flow** (orders/models.py:74-77) — do not overload.
6. **The scanner is last-mile** (`pickup_scanner`, fleet/views.py:2219). Taking its nav slot means
   folding scan into the task screen as a per-task action.
7. **Order creation fires the `if created:` post_save branch** (orders/signals.py:104-186);
   imports create orders directly — the trigger must reach all create paths (§5).
8. **`pickup_location` IS set at order creation on the main path** — it's a form field on
   `AddOrderForm` (orders/forms.py:123, defaulted at :188-194) and `add_order` refuses to run
   without at least one pickup location (orders/views.py:788-824). **Exception:**
   `add_order_with_product` (orders/views.py:1239-1261) never sets it — that path must be fixed
   or excluded before pickup tasks rely on it.
9. **New orders start at `to_review`** (orders/models.py:98) — fine for us, since the pickup task
   keys off *creation*, not the publish transition. But beware the interplay: if a pickup task's
   order is still `to_review`/gets cancelled, the pickup must follow (cancel guard in §7).
10. **There is no "hub" concept in the schema** — only `is_default` on `Warehouse`
    (warehouse/models.py:210), `WarehouseLocation` (:337), and `SellerWarehouseLink`. The "single
    fixed hub" must be resolved via `Warehouse.is_default` + its default `WarehouseLocation`
    (or a new explicit `is_pickup_hub` flag). Decision D9.
11. **No pickup-leg earnings formula exists.** Delivery earnings are hardcoded
    (delivery/models.py:489-513: flat QAR 10 / 80% for pick_and_drop; wallet_service.py:173).
    The only pickup earning today is a **staff-entered lump sum** on `HubPickupBatch`
    (delivery/models.py:165-167, paid via wallet_service.py:1068). `ZoneEarningsRate` exists but
    is wired to nothing. A per-pickup earning needs its own amount rule + wallet transaction.
    Decision D10.
12. **Driver notifications are in-app/poll only** — `DriverNotification` (fleet/models.py:758)
    with no push infra and no pickup type in `NOTIFICATION_TYPE_CHOICES` (:748-755). "New pickup
    available/assigned" needs a new notification type mirroring delivery/signals.py:453-465.
13. **The Scan nav item is linked from 3 dashboards + tests** (pwa_base.html:105,
    fleet_dashboard.html:72,288, fleet_dashboard_pwa.html:50; fleet/tests_ui.py:279,
    fleet/tests.py:1948). Folding Scan into the task screen touches all of these, not one line.

---

## 3. Data model

### 3.1 New model — `delivery.PickupTask` (one per collectable order)
- `order` FK, `business` FK, `pickup_location` FK (origin)
- `drop_warehouse` FK → `warehouse.WarehouseLocation` (the single fixed hub)
- `pickup_mode` = `assigned` | `public_pool`
- `disposition` = `drop` | `self_deliver` | `transfer` (**preset from client config at creation**)
- `driver` FK (null until claimed)
- `transfer_to_driver` FK (null unless `transfer`); `transfer_initiated_at`,
  `transfer_confirmed_at`, `transfer_confirmed_by` (two-party hand-off)
- `status` = `pending → assigned → accepted → in_progress → arrived → collected →
  dropped | handed_off | cancelled`
- `collected_at`, `dropped_at`, timestamps, `created_by`
- **No COD fields** — none apply to the pickup leg (§0).
- **No earnings fields** — the pickup leg is unpaid (D10); only the delivery leg pays.

### 3.2 Link to the delivery leg
- `DeliveryTask.source_pickup_task` FK (new, nullable) for traceability.
- `drop` → on hub drop, auto-create the last-mile DeliveryTask (reuse the hub-arrival hook,
  delivery/signals.py:549-596).
- `self_deliver` → create DeliveryTask assigned to the same driver.
- `transfer` → on both-party confirm, create DeliveryTask assigned to `transfer_to_driver`.

### 3.3 Client config — `business.Business`
- `pickup_task_enabled = BooleanField(default=False)` — **off by default** (§10-D8); staff enable
  per business. Fulfilment clients stay off.
- `pickup_mode_default = CharField(choices=[assigned, public_pool], default='assigned')` (§10-D8).
- `pickup_disposition_default = CharField(choices=[drop, self_deliver, transfer], default='drop')`
  — presets `PickupTask.disposition`. (Per-order override can be added later.)
- `DriverDirectory.is_active = BooleanField(default=True)` — suspend a driver from a client's
  fleet without deleting the link.

### 3.4 Migration
Model + fields. No backfill for existing orders (pickup applies to new orders forward);
set `DriverDirectory.is_active=True` on existing rows.

---

## 4. Driver-app UI

### 4.1 Placement — dedicated Pickup tab (§10-D3)
Bottom nav becomes `Home · Pickup · Tasks · COD · Profile`; **fold Scan into the task screen** as
a per-task action (constraint #6). Pickup badge = unclaimed pickups visible to the driver.

### 4.2 Pickup screen
- New view `fleet:driver_pickups` + `driver_pickups_pwa.html`, reusing `fleet-tabs`,
  `fleet-filter-bar`, the card system (`fleet-pwa-modern.css`), brand-kit variables, `fps__` BEM.
- Sub-tabs: **Available** (claimable: assigned-to-me + all public-pool) · **Mine** (accepted, not
  collected) · **In Progress** (collected, not yet routed/dropped).
- **No radius chips** (public pool is distance-independent, §10-D6). May still show distance as
  informational, but it does not filter.

### 4.3 Pickup card (distinct from a delivery card)
- Mode badge: **Public Pool** / **Assigned**.
- **From** = client name + pickup address → **Drop** = the fixed hub name.
- Actions by state: `Accept` → `Navigate` → `Collected ✓` → then follow the preset disposition:
  - `drop` → `Dropped at hub ✓`
  - `self_deliver` → `Start delivery` (rolls into the delivery task)
  - `transfer` → `Transfer` → driver picker → target confirms → done.

---

## 5. Trigger — where pickup tasks are created
Service `delivery/services/pickup.py → create_pickup_task_if_needed(order, *, source)`, called
from every order-create path (constraint #7): order post_save `if created:` branch
(orders/signals.py:104), import creators (TikTok etc.), staff/API create endpoints.

Gate (no-op + reason if any fail):
- `business.pickup_task_enabled` and `business_status == 'active'`
- pickup location resolvable and NOT `is_fulfilment_center`
- no existing pickup task for the order

Stamp `pickup_mode` and `disposition` from the business config.

---

## 6. Pool visibility — shared helper
`delivery/selectors.py → pickup_pool_for(driver)`:
- Base: `status='pending', driver__isnull=True`, exclude cancelled.
- **Assigned branch**: `pickup_mode='assigned'` AND task.business has an active `DriverDirectory`
  row for this driver.
- **Public branch**: `pickup_mode='public_pool'` AND `driver.driver_status='approved'` — **all
  such tasks, no distance filter** (§10-D6).
- No `driver_availability` gate in v1.

One source of truth for the Pickup list + any pickup notifications, so an assigned task never
leaks to non-assigned drivers.

---

## 7. Accept, collect, route
- **Accept** (`fleet:accept_pickup`): re-check `pickup_pool_for(driver)` server-side. Atomic claim:
  `PickupTask.objects.filter(pk=..., driver__isnull=True).update(driver=driver, status='accepted')`;
  0 rows → "already taken".
- **Collect** (`fleet:collect_pickup`): `status='collected'`, `collected_at`, scan the package
  barcode (reuse OrderBarcode).
- **Route** — follows the preset `disposition`:
  - `drop`: `status='dropped'` at the fixed hub → auto-create last-mile DeliveryTask (§3.2).
  - `self_deliver`: create DeliveryTask assigned to the same driver.
  - `transfer`: pickup driver selects target (manual picker, any approved driver); set
    `transfer_to_driver` + `transfer_initiated_at`; **target must confirm** (`transfer_confirmed_at`)
    → `status='handed_off'` → create DeliveryTask assigned to target. Until confirmed, the package
    stays with the pickup driver.

---

## 8. Tests
- Pickup task created on order create for non-fulfilment client; NOT for fulfilment/fulfilment-
  centre orders; not duplicated; import-created orders trigger it.
- Pool scoping: assigned driver sees assigned pickup; non-assigned does not; public pool shows to
  all approved drivers (no distance filter).
- Accept 403 gating; atomic double-accept → "already taken".
- Dispositions: `drop` → auto-created delivery task at hub; `self_deliver` → delivery task = same
  driver; `transfer` → requires target confirm, delivery task = target, package stays until confirm.
- UI: Pickup tab renders its own list; delivery tabs unchanged; Scan folded into task screen still works.

---

## 9. Build order
0. **Pre-work:** fix `add_order_with_product` so it sets `pickup_location` (constraint #8);
   designate the hub (D9: `Warehouse.is_default` or new `is_pickup_hub` flag).
1. Model + migration (`PickupTask`, `DeliveryTask.source_pickup_task`, Business config fields).
   No earnings fields (D10: pickup leg unpaid).
2. `create_pickup_task_if_needed` service + wire into all order-create paths (§5); cancel guard —
   order cancelled ⇒ pickup task cancelled (constraint #9).
3. `pickup_pool_for` helper (§6).
4. Pickup views: list / accept / collect / route + transfer-confirm endpoint + URLs (§7).
5. Driver PWA: Pickup nav item + `driver_pickups_pwa.html` + card + route/transfer sheet (§4).
   Scan relocation: update pwa_base.html:105 + both dashboards' quick-actions + tests_ui.py:279 /
   tests.py:1948 (constraint #13).
6. Auto-create delivery task on hub drop + on self/transfer (§3.2); two-party transfer confirm.
7. Notifications: new `DriverNotification` type(s) `pickup_available` / `pickup_assigned` /
   `pickup_transfer_request` + optional AutoFlow trigger (constraint #12).
8. Staff/business config UI for `pickup_task_enabled` / `pickup_mode_default` /
   `pickup_disposition_default`; `@staff_required`.
9. Tests (§8, plus: add_order_with_product path, cancel guard, transfer-confirm notification)
   + `collectstatic` + gunicorn HUP (bump CSS `?v=`).

---

## 10. Resolved decisions

- **D1 — Route chooser:** Client config presets the disposition; the driver executes it.
- **D2 — Drop destination:** A single fixed EzzyDelivery hub/warehouse for all pickups.
- **D3 — Nav placement:** Dedicated Pickup bottom-nav tab; Scan folded into the task screen.
- **D4 — Transfer target:** Pickup driver picks any approved driver from a manual picker.
- **D5 — Drop handoff:** Dropping at the hub auto-creates the last-mile delivery task.
- **D6 — Public pool scope:** All active approved drivers; no 5/10 km distance filter.
- **D7 — Transfer confirmation:** Both drivers must confirm the hand-off (chain of custody).
- **D8 — Defaults:** `pickup_task_enabled` off by default; when enabled, `assigned` mode.
- **(Dropped)** COD-on-transfer: not applicable — no COD is collected at the pickup leg.

- **D9 — Hub designation:** Use the existing `Warehouse.is_default` flag — the default warehouse
  (+ its default `WarehouseLocation`) is the drop hub. No schema change.
- **D10 — Pickup-leg earnings:** **No pay for the pickup leg.** Only the delivery leg pays
  (self-deliver drivers earn on delivery only). Drop `PickupTask.driver_earnings` and the wallet
  wiring from the build (build step 7 removed; no earnings field in §3.1).

Plan is decision-complete (D1–D10). Built — see §11 for what changed during the build.

---

## 11. As-built changes (build-time analysis, 2026-07-20/21)

What differed from the plan once the code met reality, plus scope added on request during
the build. This section is the delta; everything not listed here was built as planned.

### 11.1 Plan assumptions corrected during build
- **Pre-work step 0 (fix `add_order_with_product`) was dropped.** Verified vestigial: routed
  (orders/urls.py:21) but linked from nowhere, and its POST saves an orphan OrderItem formset —
  it cannot create an Order at all. The service's `no_pickup_location` gate covers any
  degenerate path, so no fix was needed.
- **The "wire every entry point" list (§5) collapsed into ONE hook.** Instead of calling the
  service from each creator (dashboard, imports, staff/API), it hooks the Order post_save
  `if created:` branch via `transaction.on_commit` (orders/signals.py). Every ORM creation path
  fires post_save — including imports — so one hook covers them all. (Only `bulk_create` would
  bypass it; no order-creation path uses it.) `on_commit` also guarantees the order row is
  committed before notifications go out, and skips pickup creation if the creating transaction
  rolls back.
- **No state-machine change was needed.** The delivery leg for self_deliver/transfer is created
  fresh via the existing `_create_delivery_task_from_order` (status `for_review`), then claimed
  with `_status_actor='driver'` — `for_review → accepted` is already a legal driver transition.
  The earlier draft's `failed → pending` system-actor extension belonged to the abandoned
  delivery-pool design and was never built.
- **`Driver` has no `driver_name` field** (display is `str(driver)` → username via profile).
  Caught pre-deploy: fixed the new code's four usages and the transfer-target search filter
  (now driver_code / profile names / username), and fixed the pre-existing
  `AssignedDriver.__str__` crash (delivery/models.py) that referenced it.
- **`PickupTask.order` became a OneToOneField** (plan said FK-one-per-order); `related_name`
  `order.pickup_task`. Cleaner duplicate guard than filtering.
- **Scan relocation was additive, not destructive.** Only the bottom-nav slot was swapped for
  Pickup; the `pickup_scanner` URL, both dashboard quick-actions, and tests were left intact,
  and a scan icon was added to the Tasks screen header. The plan's step "update all touchpoints"
  proved unnecessary.
- **Public-pool notifications deferred (v1).** Creation notifies only assigned-mode fleets
  (in-app `pickup_available` to active `DriverDirectory` drivers); public-pool tasks surface via
  the Pickup tab badge instead of a broadcast. Transfer requests and staff assign/reassign/cancel
  each notify the affected driver.

### 11.2 Scope added during build (user-requested)
- **Staff fleet management** on the automation page: per-business "Manage" panel over
  `DriverDirectory` — add via approved-driver search, enable/disable (`is_active`), remove.
  Endpoints `pickup_fleet_list` / `pickup_fleet_driver_search` / `pickup_fleet_update`; live
  active-count badge; audit-logged.
- **Staff pickup pool console** `/workforce/pickups/` (`pickup_pool_status`): all PickupTasks
  with status/mode/search filters + pagination, and per-row **Assign/Reassign**
  (`pickup_staff_assign`) — allowed `pending→arrived`, blocked once `collected` (goods are
  physically with a driver); assigns set status `accepted` + notify the new driver, reassigns
  also notify the bumped driver.
- **Sidebar "Pickup" section** (desktop `parts/sidebar/pickup.html` + mobile block): Pool Status,
  Pickup Assign (pending-filtered), Client Driver List; unclaimed-count badge via
  `pickup_pending_count` in the workforce context processor (cached, defensive).
- **Driver-PWA badge** `pickup_badge_count` in the fleet context processor (claimable pool +
  own active pickups).
- **Design layer** (applied + deployed 2026-07-21): the two workforce pages carry dedicated BEM
  styling in `workforce.css` — `pau__` (Pickup Automation: hero header + enabled tally,
  switch-style enable toggles, `pau__row--off` dimming for disabled businesses, inline
  active-fleet driver names via a `Prefetch(to_attr='active_fleet')` on the view, manage-fleet
  panel) and `ppl__` (Pickup Pool: unclaimed/active tally chips, color-coded status chips —
  red pending / green done, `ppl__row--pending` highlight, inline assign panels). The driver
  Pickup transfer sheet gained a slide-up animation with `prefers-reduced-motion` handling in
  `fleet-pickup.css`. Deploy required a cache-buster fix: `wf_dashboard_base.html` still linked
  `workforce.css?v=20260720g` (predating the design additions) — bumped to `?v=20260721a`;
  `fleet-pickup.css` link at `?v=20260721b`. Verified live: all 11 key classes resolve,
  24/24 tests green, site 200.

### 11.2b Related fix — fulfilment pickup-location naming consolidation (2026-07-21)
Driver cards showed "Pickup From: Fulfillment Store" for some orders and
"Pickup From: WH: EzzyDelivery FC- Sudan" for others. Root cause: two creators of
fulfilment-centre PickupLocations — business/signals.py auto-created a coordless generic
"Fulfillment Store" placeholder (arbitrary `Warehouse.objects.first()` link) for every
fulfilment-enabled business, while warehouse/signals.py created proper "WH: {name}" rows
(real coords) on SellerWarehouseLink. Fixes:
- business signal now resolves the business's warehouse link → default warehouse and creates
  the row with `WH:` title + coords; generic title only if no warehouse exists.
- warehouse-link signal now calls `merge_placeholder_fulfilment_rows()` — re-points
  Order/DeliveryTask/PickupTask references to the WH row and retires the placeholder
  (inactive, never deleted — HubPickupBatch FKs may reference it).
- `manage.py consolidate_fulfillment_stores [--apply]` cleans existing data (merge when both
  rows exist; in-place refresh when only a coordless placeholder points at a known warehouse).
- Production run 2026-07-21: 25 placeholders refreshed in place to "WH: EzzyDelivery FC- Sudan"
  (all already FK'd to that sole default warehouse); 0 coordless fulfilment rows remain.
- Tests: business/tests_fulfillment_consolidation.py (4 green) + pickup suite still 24 green.

### 11.3 Verification record
- `delivery/tests_pickup.py`: **24 tests, all green** — creation gating (disabled/fulfilment/
  suspended/duplicate/cancel-guard), pool scoping (public/assigned/inactive-link/unapproved),
  atomic double-accept, all three dispositions incl. two-party transfer confirm, staff fleet
  CRUD + non-staff 302, staff assign/reassign/blocked-after-collect, pool page render.
- Known-unrelated failures documented: 4 in orders suites (warehouse-inventory signal tests,
  str-vs-int `original_order_data` assertion) and 5 stale assertions in fleet.tests — all
  pre-existing; pickup hooks cannot execute in those test paths.
- Deployed via collectstatic + gunicorn HUP; site HTTP 200; new staff/driver endpoints
  auth-gated (302 anonymous).
