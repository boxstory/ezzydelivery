# Warehouse Staff Operations Guide

> A practical step-by-step guide for warehouse team members

---

## Table of Contents

1. [Your Daily Routine](#1-your-daily-routine)
2. [Receiving Stock](#2-receiving-stock)
3. [Put-Away (Shelving)](#3-put-away-shelving)
4. [Picking Orders](#4-picking-orders)
5. [Packing Orders](#5-packing-orders)
6. [Dispatching to Drivers](#6-dispatching-to-drivers)
7. [Handling Cancellations & Returns](#7-handling-cancellations--returns)
8. [Customer Returns (RMA)](#8-customer-returns-rma)
9. [Low Stock Alerts](#9-low-stock-alerts)
10. [Common Situations & What To Do](#10-common-situations--what-to-do)

---

## 1. Your Daily Routine

### Morning Checklist

1. **Open the Dashboard** (`Warehouse → Dashboard`)
   - Check **Pending Pick Lists** count — these are orders waiting to be picked
   - Check **Low Stock Alerts** — flag any critical items to your supervisor
   - Check **Pending Put-Away Tasks** — received stock that needs shelving
   - Check **Return Tasks** — cancelled orders whose items need to go back on shelves

2. **Priority Order:**
   | Priority | Task | Why |
   |----------|------|-----|
   | 1st | Pick Lists (pending/assigned) | Customers are waiting for these orders |
   | 2nd | Put-Away Tasks | Received stock blocking the dock area |
   | 3rd | Return Tasks | Items need to go back to correct shelves |
   | 4th | Low Stock Alerts | Acknowledge and report to procurement |

### What Happens Automatically (You Don't Need To Do This)

The system handles these automatically — you'll see the results:

- When a seller marks an order as **"Ready to Pickup"**, the system automatically:
  - Reserves the stock (so no one else can sell it)
  - Creates a Pick List for you
  - Groups items by zone so you pick efficiently

- When a driver marks a delivery as **"Delivered"**:
  - The reserved stock is deducted permanently

- When an order is **cancelled**:
  - Reserved stock is released
  - If you already picked it, a Return Task is created for you

---

## 2. Receiving Stock

### When: A seller delivers products to the warehouse, or a shipment arrives

**Steps:**

1. Go to **Inventory → Receive Stock**
2. Select the **Warehouse** (your fulfillment center)
3. If the seller sent an **Inbound Request** ahead of time:
   - Select it from the dropdown — products will auto-populate
   - This is the preferred method (seller tells us what's coming)
4. If no Inbound Request (walk-in delivery):
   - Select the **Business** (seller) from the dropdown
   - Add each product and quantity manually
5. Optionally select a **Storage Location** (staging area/dock)
6. Click **Receive Stock**

### What Happens Next:
- Stock levels are updated immediately (quantity_on_hand increases)
- A **Put-Away Task** is automatically created
- If linked to an Inbound Request, fulfillment progress is tracked
- You'll be redirected to the Put-Away Task to start shelving

### Tips:
- **Count everything** before confirming — quantities cannot be easily reversed
- If a product doesn't exist in the system, tell the seller to add it first
- If quantities don't match what was expected, receive what you actually got — the system tracks partial fulfillment

---

## 3. Put-Away (Shelving)

### When: After receiving stock, items need to go from the dock to their shelf locations

**Steps:**

1. Go to **Operations → Put-Away** (or you'll be redirected after receiving)
2. Open the task — it will auto-assign to you and start
3. For each item, you'll see:
   - **Product name and quantity**
   - **Suggested Location** — the system suggests the bin where this product already exists (consolidation)
4. Walk to the suggested location with the items
5. If the suggested location is full or wrong:
   - Use the **Location Override** dropdown to pick a different bin
6. Click **Confirm** for each item after placing it on the shelf

### What Happens:
- Stock is transferred from the receiving area to the actual bin
- Two inventory transactions are logged (transfer_out from dock, transfer_in to shelf)
- When all items are placed, the task completes automatically

### Tips:
- **Consolidate same products** — put the same SKU in the same bin when possible
- **Don't overfill bins** — if a bin is full, use an adjacent empty one
- **Check the label** — make sure you're putting the right product in the right bin

---

## 4. Picking Orders

### When: Customers have placed orders and the system created pick lists

**Steps:**

1. Go to **Operations → Pick Lists**
2. Find a **Pending** or **Assigned** pick list
3. Click **Assign to Me** (self-assign)
4. Click **Start Picking**
5. The pick list shows items grouped by product and location:
   - **Location code** (e.g., A-01-03-B) — this is where to go
   - **Product name and SKU**
   - **Quantity to pick**
   - **Order number(s)** — which orders need this item
6. Walk to each location in order (they're sorted by location code for efficiency)
7. Pick the item from the shelf
8. Click the **Pick** button — the item turns green
9. If you picked the wrong item or wrong quantity, click **Unpick** to reset

### What Happens:
- Progress is tracked in real-time (picked_items / total_items)
- When all items are picked, the pick list auto-completes
- The pick list moves to the **Pack Station** queue

### Tips:
- **Pick in location order** — walk through the warehouse systematically, don't zigzag
- **Check SKU, not just the name** — similar products can look alike
- **If a shelf is empty** but the system says stock is there:
  - DON'T pick from a different location
  - Report it to your supervisor — there may be a count discrepancy
- **Multiple orders in one pick list** — items from different orders are grouped together. You'll sort them during packing.

---

## 5. Packing Orders

### When: A pick list is fully picked and ready for packing

**Steps:**

1. Go to **Operations → Pick Lists** → find a **Picked** (completed) pick list
2. Click **Pack Station**
3. Items are now grouped **by order** (not by product like picking)
4. For each order:
   - Gather all items for that order
   - Place them in a shipping box/bag
   - Attach the shipping label
   - Click **Pack** to mark the order as packed
5. If you made a mistake, click **Unpack** to reset

### What Happens:
- First order packed → pick list status changes to **Packing**
- All orders packed → pick list status changes to **Packed**
- Packed orders appear in the **Dispatch Queue**

### Tips:
- **Verify contents against the order** — check product, quantity, and condition
- **Handle COD orders carefully** — note the COD amount on the label
- **Fragile items** — use appropriate packaging material
- **One order = one package** unless the order is too large

---

## 6. Dispatching to Drivers

### When: Orders are packed and a driver is ready to leave

**Steps:**

1. Go to **Operations → Dispatch**
2. You'll see the **Dispatch Queue** — packed orders waiting to go out
3. Select the orders for this driver (checkbox)
4. Select the **Driver** from the dropdown
5. Click **Create Dispatch Batch**
6. On the dispatch detail page:
   - Hand each package to the driver
   - Click **Handover** for each order as you hand it over
   - The driver should verify the order number on each package
7. When all orders are handed over, click **Confirm Dispatch**

### What Happens:
- A Dispatch Batch is created with a unique batch number (DSP-XXXXX)
- Each order is tracked individually (handed over or not)
- After confirmation, the batch status becomes **Dispatched**
- The driver's delivery tasks are already created in the system

### Tips:
- **Count the packages** — make sure the number matches the batch total
- **COD orders** — remind the driver of total COD amount for the batch
- **Driver should sign/confirm** — verbal confirmation of package count
- **Don't dispatch partial batches** unless necessary — it's better to hand over everything at once

---

## 7. Handling Cancellations & Returns

### When: An order is cancelled after items were already picked

You don't need to do anything to trigger this — the system creates a **Return Task** automatically.

**Steps:**

1. Go to **Operations → Returns**
2. Open the return task (it auto-starts when you open it)
3. For each item:
   - Take the item back to its original shelf location (shown in the task)
   - Place it back on the shelf
   - Click **Return** to confirm
4. When all items are returned, the task completes

### What Happens:
- Stock levels are restored (quantity_on_hand increases)
- Inventory transactions are logged (type=return)
- The item is available for future orders again

### Important:
- **Return to the CORRECT location** — the task shows the original bin. Don't put it in a random spot.
- **If the original bin is full**, tell your supervisor — they may need to adjust the location.
- **Damaged items** — if the item was damaged during picking/packing, DON'T return it. Report to supervisor.

---

## 8. Customer Returns (RMA)

### When: A customer returns a delivered order

**Steps (staff/supervisor):**

1. Go to **Operations → Customer Returns**
2. Click **Create RMA** and select the order
3. Select which items are being returned and the reason
4. When the items arrive at the warehouse:
   - Click **Receive All** — marks all items as physically received
5. **Inspect each item** one by one:
   - Set **Condition**: Good / Damaged / Defective / Opened
   - Set **Disposition**: Restock / Quarantine / Dispose
   - Click **Inspect**
6. Items marked as **Restock + Good condition** are automatically added back to inventory

### What Happens:
- RMA lifecycle: Requested → Received → Inspected → Resolved
- Good items: stock_on_hand increases, inventory transaction logged
- Damaged/defective items: tracked but NOT restocked
- The full audit trail is preserved

---

## 9. Low Stock Alerts

### When: Stock falls below the reorder point set for a product

**Steps:**

1. Go to **Inventory → Low Stock Alerts**
2. Active alerts show products that need restocking
3. Click **Acknowledge** on alerts you've seen
4. Report to procurement/seller:
   - Product name and SKU
   - Current quantity
   - Reorder point
   - Suggested reorder quantity (if set)

### Tips:
- **Check alerts daily** — don't let them pile up
- **Acknowledge ≠ Resolved** — acknowledge means "I've seen this," resolved means stock has been replenished
- Alerts auto-resolve when stock levels go back above the reorder point (via the next stock receive)

---

## 10. Common Situations & What To Do

### "The system says we have 10 units but the shelf is empty"
1. Do NOT adjust the quantity yourself
2. Report to supervisor
3. Supervisor should create a **Cycle Count** for that location
4. After counting, the system quantity will be corrected

### "A product is in the wrong bin"
1. Note the product and its current location
2. Report to supervisor
3. The product needs to be physically moved and a stock transfer recorded

### "Driver arrived but the order isn't packed yet"
1. Check the pick list status — is it still being picked?
2. Prioritize that pick list
3. Pack the order and dispatch directly
4. Don't skip the system steps — every handover needs to be recorded

### "Seller delivered products we weren't expecting"
1. Receive the stock anyway (use manual receiving, not inbound request)
2. Note the discrepancy in the receiving notes
3. Report to supervisor so they can follow up with the seller

### "I made an error in receiving — wrong quantity"
1. If you received MORE than actual: tell supervisor immediately
2. Supervisor can do a stock adjustment (Adjust Out) via admin
3. If you received LESS: receive additional units using the same process

### "Pick list shows items from two different zones"
This shouldn't normally happen — pick lists are grouped by zone. If it does:
1. The item's stock location may have been set to a different zone
2. Pick both zones in one trip if they're close
3. Report to supervisor for future pick list optimization

### "Customer return item is not in our system"
1. Do NOT receive random items into inventory
2. Create the RMA from the original order — only original order items can be returned
3. If the product was never in an order, reject the return
