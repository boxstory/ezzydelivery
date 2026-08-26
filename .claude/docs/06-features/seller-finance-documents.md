# Seller finance documents — payout invoice vs charge invoice

Purpose: which document a seller gets for a delivery, and the exact staff steps that put one on their Invoices & Payouts page.
Used by: finance staff working `/workforce/fleet/cod-business-settlement/` and `/workforce/client-charges/collect/`.
Notes: written after a seller asked why COD payout `CODCS-20260816-0001` was "not listed in invoices" — it is a different document from a charge invoice, and their charges could never produce one.

---

## The two documents

Every delivery charge is recovered **exactly one of two ways, never both**. Which one decides which document the seller receives.

| | COD payout invoice | Delivery charge invoice |
|---|---|---|
| Code | `CODCS-YYYYMMDD-NNNN` | `INVC-YYYYMMDD-NNNN` |
| Record | `fleet.DriverTransaction`, type `cod_client_settle` | `fleet.BusinessChargeInvoice` |
| Direction | We pay the seller | The seller pays us |
| How the fee is taken | Withheld from the COD as a `BusinessPayoutDeduction` line | Billed on the invoice, collected later |
| Who gets it | COD sellers | Prepaid sellers, or COD deliveries never withheld against |
| Staff screen | `/workforce/fleet/cod-business-settlement/` | `/workforce/client-charges/collect/` |
| Seller sees it at | `/business/finance/invoices/` and the COD statement | `/business/finance/invoices/` |

The amount on a CODCS row is the **net** that left the bank. Gross COD and withheld charges are reconstructed from the deduction lines — always via `WalletService.payout_figures()` (`fleet/wallet_service.py:33`), never by assuming the transaction is gross.

## The fence that stops double-billing

`billable_tasks()` (`fleet/billing_service.py:36-63`) is the only gate on what can be invoiced. A delivery is billable only when all of these hold:

- status `delivered` or `partial_delivery`
- `charge_invoice` is null — not already on an invoice
- `settled_delivery_charge` is null — not already frozen at a payout
- **not** withheld on a payout: `.exclude(cod_client_settle_txn__payout_deductions__kind='delivery_charge')`
- resolved fee > 0

The last clause is why a COD seller whose charges were withheld has **zero** charge invoices, and why the Charges to Collect desk shows nothing for them. That is correct: the fee is already collected. Issuing an invoice would bill it twice.

The fence runs the other way too — `cod_business_settlement_action` excludes already-invoiced tasks from the withholding, and the payout report marks them "Invoiced".

## Issuing a charge invoice

1. Open `/workforce/client-charges/collect/` and filter to the business.
2. Tick the deliveries to bill. Only billable ones appear; anything already recovered is absent by design.
3. **Issue invoice** → confirm in the modal. This posts to `workforce:client_charge_invoice_create` (`workforce/views.py:14072`) → `issue_charge_invoice()` (`fleet/billing_service.py:96`).
4. The invoice is born **`issued`**. There is no draft state — do not look for one.
5. The seller can see it immediately at `/business/finance/invoices/`; **WhatsApp** on the invoice page sends them the link.

After issue, on `/workforce/client-charges/invoices/<INVC-code>/`:

| Action | Effect |
|---|---|
| Record payment | `issued` → `part_paid` → `paid`. Overpayment is refused. |
| Add charge | Adds a hand line + its revenue transaction, totals resync. |
| Columns | Sets the column layout for this invoice (optionally saved as the business default). |
| Void | Refused once any payment exists. Clears `charge_invoice` on the deliveries so they return to the desk, and reverses the revenue transactions. There is no un-void. |

Removing a line that is tied to a delivery is refused — void and reissue instead.

## Paying COD out to a seller

1. Open `/workforce/fleet/cod-business-settlement/`. Candidates are tasks with `cod_collected=True`, `cod_settled=True` (cash physically with us), `cod_client_settled=False`.
2. Tick the deliveries, set the deductions (delivery charges, fulfilment, inventory handling, other), record the payment method and bank reference.
3. Confirm. This writes one `cod_client_settle` transaction for the **net**, one revenue transaction plus a `BusinessPayoutDeduction` per deduction, flags the tasks, and moves the orders to `cod_settled_with_business`.
4. The payout invoice is at `/workforce/fleet/cod-business-settlement/invoice/<CODCS-code>/`; the seller's own copy is `/business/finance/cod-payout/<CODCS-code>/`, tenant-scoped so no other account can open it.

**Reversing:** `/workforce/fleet/cod-business-settlement/` reverse action books an offsetting `CODCR` transaction carrying the payout code in `reference_number`, resets the tasks and restores the orders. "Reversed" is derived from that reference match, not stored on the payout.

## Worked example — LaDeeN, `CODCS-20260816-0001`

- 99 deliveries, 17,850.00 COD released
- one deduction line: 1,980.00 delivery charges (revenue row `DLVC-20260816-0001`)
- 15,870.00 paid by bank, reference `INV-LDN073-018`

The seller asked why this is not under Invoices. It is a payout invoice, not a charge invoice, and their delivery charges were already recovered by withholding — so no `INVC` exists or can be raised for those 99 deliveries.

**If the charges must be billed by invoice instead**, staff have to reverse the payout first and re-pay gross with no `delivery_charge` deduction. Only then do those deliveries reappear on the Charges to Collect desk. Doing it the other way round double-charges the seller.
