<!-- Purpose: Build plan for the driver + client payout console (verification → payout → invoice). -->
<!-- Used by: Claude Code sessions working on workforce payout/settlement screens. -->
<!-- Notes: COD collection and submit-to-admin (fleet-side) code is OUT OF SCOPE by explicit instruction — read "Hard constraints" before editing anything COD. -->

# Payout Console — Plan (2026-07-28)

One plan covering both payout legs: **what we owe the driver** and **what we owe the client**.
Each leg gets the same three-screen shape: **verify → pay → invoice**.

## Hard constraints

1. **Do not touch the COD section.** COD collection and submit-to-admin (fleet PWA, `submit_cod_to_admin`, `cod_settlement_action`, the COD tabs on Fleet Transactions, the driver-side COD submission) stay exactly as they are. Payout work goes *around* them, never through them.
2. **COD never appears as money owed.** COD is a hand-in leg — cash the driver holds for Ezzy. It may appear as read-only context on a staff worksheet, never as a payout figure or an invoice line.
3. Brand Kit tokens only, Bootstrap-first, BEM alongside. No inline styles, no `<style>` blocks.

## Money model as it stands today (verified in code)

```
delivered task
  → earnings_verification (staff verify / edit amount)
  → publish  ─────────────► creates `earning` DriverTransaction (settlement = NULL)
  → payout   ─────────────► DriverSettlement + txns linked; invoice itemises earning+bonus
```

- `DeliveryTask.calculated_earnings` → `verified_earnings` (staff-edited) → `driver_earnings` (final, stamped at publish).
- `DeliveryTask.dl_price` is the **client-billed delivery charge**.
- Client leg: `settle_cod_with_client(...)` books a `cod_client_settle` txn plus one `BusinessPayoutDeduction` row per invoice line (`delivery_charge`, `fulfillment_charge`, `inventory_handling`, `other_charge`).

## Gaps found (fix as part of this work)

| # | Gap | Where | Fix |
|---|-----|-------|-----|
| G1 | Payout list showed COD as earnings — `real_pending_earnings` was `Sum(cod_collected_amount)` of unsettled COD tasks, labelled "Pending driver earnings" | `workforce/views.py` `fleet_drivers_earnings` | **DONE** — now sums unsettled `earning`+`bonus` txns, same source the invoice itemises |
| G2 | "Deliveries After Settlement" counted every delivered task ever, ignoring the last payout, and excluded `partial_delivery` | same view | **DONE** — scoped to `completed_at >` last payout, epoch floor when never paid |
| G3 | `bulk_settle_transactions` folds `cod_collection` rows into the payout: `gross_earnings = COD + earnings`, so the settlement record contradicts its own invoice (which recomputes from earning/bonus) | `workforce/views.py:12401` | New payout action settles earning/bonus/deduction only. The existing endpoint is left alone — it is also the staff COD hand-in path and constraint 1 applies |
| G4 | `dl_price` is an **IntegerField** — the client delivery charge cannot hold fils, while every downstream deduction/invoice figure is Decimal | `delivery/models.py:249` | **DONE** — migration `delivery/0040`, in-place `USING ::numeric` cast, no data loss. Side effects: `dl_price=order.dl_amount` no longer truncates fils on write (historic rows keep their truncated values, unrecoverable); `DeliveryTaskListSerializer` needed an explicit `coerce_to_string=False` or the public API would have turned `20` into `"20.00"` |
| G5 | No client-side charge verification. The driver leg has `earnings_verification_status` / `verified_earnings` / `verified_by` / `verified_at`; the client leg has nothing — `dl_price` goes straight to the payout deduction unchecked | `delivery/models.py` | **DONE** (fields) — `charge_verification_status`, `verified_delivery_charge`, `charge_verified_by`, `charge_verified_at` in `delivery/0040` |
| G6 | Desktop finance sidebar has "COD Settlement Requests" and "Driver COD Requests" pointing at the same URL | `workforce/templates/workforce/parts/sidebar/finance.html` | **DONE** — duplicate removed from desktop and mobile sidebars |
| G7 | `DriverSettlement.gross_earnings` stores COD+earnings for legacy rows, so a COD-only settlement reads as "earnings" | `fleet/models.py` | New payouts store earnings-only; the invoice already recomputes rather than trusting the field. Leave historic rows, do not backfill |

## Screens

### 1. Driver Payouts (landing) — `/workforce/fleet/drivers-earnings/` — **DONE**
Card per driver: **Pending Payout** (unsettled earning+bonus), Deliveries Since Payout, Last Paid. No COD anywhere. Card opens the worksheet (screen 2).

### 2. Driver payout worksheet — `/workforce/fleet/driver-payout/<driver_id>/` — NEW
The staff working surface. One row per delivered task for that driver:

| Task | Business | Route | Date | Client charge | COD *(read-only)* | Calculated | Verified *(editable)* | Status | Log |

- Checkbox per row, select-all, **bulk set amount** on the selection (same interaction as Earnings Verification).
- Row actions: verify / publish / reject. Bulk actions on the selection.
- **Create payout** from the selected published rows → `DriverSettlement` + link the `earning`/`bonus` txns + `deduction` rows → redirect to the invoice.
- COD column is context only — greyed, not summed into any total, never posted.
- Absorbs task #7 (driver delivery-charge verify + bulk edit): same rows, same bulk editor, one screen instead of two.

### 3. Driver payout invoice — `/workforce/settlement/<id>/payout-invoice/` — EXISTS, no COD, leave as is
Only change: make sure the settlement it renders was created earnings-only, so header totals and lines agree.

### 4. Client delivery-charge verification — `/workforce/client-charges/` — NEW
The client-side mirror of Earnings Verification. One row per delivered task, grouped/filterable by business:

| Task | Business | Route | Date | Zone/speed | Calculated charge | Verified charge *(editable)* | Status | Log |

- Needs G5 fields: `charge_verification_status`, `verified_delivery_charge`, `charge_verified_by`, `charge_verified_at` on `DeliveryTask`.
- Bulk edit + bulk verify, same interaction vocabulary as the driver worksheet.
- Verified charge is what the client payout deducts — replacing today's raw `dl_price`.

### 5. Client payout — `/workforce/fleet/cod-business-settlement/` — **DONE (design)**
Rebuilt to the worksheet vocabulary: masthead, 5-cell money strip, `bcp__panel` table, deduction editor promoted out of the modal into an on-page subtraction ladder, sticky tape with the running net. Settlement form contract verified unchanged (`task_ids[]`, `payment_method`, `reference`, `deduct_charges`, `deduction_*[]`). Fixed along the way: the confirm modal renders outside `.bcp` so the teller tokens were undefined there — the receipt had no background at all.

### 6. Client payout invoice — `/workforce/fleet/cod-business-settlement/invoice/<code>/` — **DONE**
Print rebuilt for A4 (`@page` A4 portrait, chrome hidden, base-template flex/overflow wrappers unwound so the ledger stops clipping, thead/tfoot repeat, `break-inside: avoid`, `print-color-adjust: exact`). Verified by rendering with print emulation and generating a PDF.

**Still open on this leg:** the payout bills raw `dl_price`, not `verified_delivery_charge`. Three places in `workforce/views.py` — the `fee_subtotal` accumulation, and the `select_for_update(...).values_list('id', 'cod_collected_amount', 'dl_price')` lock plus the `delivery_charge` sum built from it. The report template's `data-fee` and Del. charge cell must switch to the same expression in the same change.

## Build order

1. ~~G1 + G2 — payout landing shows real money owed~~ **DONE**
2. Screen 2 (driver worksheet) + payout action — absorbs tasks #3 and #7, closes G3
3. G4 — `dl_price` → Decimal (migration + caller audit)
4. G5 + screen 4 — client charge verification
5. Screen 5 + 6 — client payout redesign + invoice, consuming the verified charge
6. G6 — sidebar cleanup

Reload gunicorn after each step; `manage.py check` and the fleet suite (159/159 green) before moving on.
