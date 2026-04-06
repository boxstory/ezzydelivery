# Warehouse Features Todo List

> Last updated: 2026-03-26

## COMPLETED

### 1. Dispatch & Driver Handover ✅ (2026-03-26)
- [x] Dispatch queue: list packed orders ready for driver
- [x] Assign orders to driver (select driver → assign batch)
- [x] Driver handover confirmation (tap each order to confirm)
- [x] COD amount tracking per batch
- [x] Status: Ready → Assigned → Handed Over → Dispatched
- [ ] Print shipping label (future)
- [ ] Route optimization by zone (future)

### 2. Customer Returns / RMA ✅ (2026-03-26)
- [x] Return request with reason (wrong item / damaged / refused / change of mind)
- [x] Return receiving: mark all items received
- [x] Condition assessment (good / damaged / defective / opened)
- [x] Disposition: restock (good) / quarantine (inspect) / dispose (damaged)
- [x] Auto restock: stock on_hand updated when disposition is restock
- [x] Inventory transaction logged for restocked items
- [ ] Refund trigger to order system (future)
- [ ] Photo evidence (future)

### 3. QR Code Scanning ✅ (2026-03-26)
- [x] Phone camera QR scanner (jsQR library, no hardware needed)
- [x] Scan product QR to find & expand in pick list
- [x] Manual code entry fallback
- [x] Visual feedback: vibrate, highlight, auto-scroll
- [x] Reusable component: warehouse/parts/qr_scanner.html
- [ ] Scan location QR for put-away (future)
- [ ] Scan at pack station (future)

## BUILD NOW (Priority)
- [ ] Mismatch alert: "Scanned X but expected Y"
- [ ] Integration with pick list detail page
- [ ] Integration with pack station
- [ ] Integration with receive stock

---

## FUTURE (Backlog)

### 4. Put-Away Task
- [ ] Auto-generate put-away task after receiving stock
- [ ] Suggest optimal location (same product location, or nearest empty bin)
- [ ] Staff walks to location → places items → confirms
- [ ] Stock location updated only after confirmation

### 5. Stock Transfer
- [ ] Transfer request: warehouse A → warehouse B
- [ ] Transfer pick list (pick from source warehouse)
- [ ] Transit tracking (in transit status)
- [ ] Receive at destination warehouse
- [ ] Inter-zone transfers within same warehouse

### 6. Batch & Expiry Tracking
- [ ] Batch number per stock entry
- [ ] Expiry date on stock level
- [ ] FEFO picking (First Expiry First Out)
- [ ] Expiry alerts (items expiring in X days)
- [ ] Auto-block picking of expired items
- [ ] Expiry report per warehouse

### 7. Dashboard Analytics
- [ ] Orders per day/week/month chart
- [ ] Pick rate: items picked per hour per picker
- [ ] Pack rate: orders packed per hour
- [ ] Average pick-to-dispatch time
- [ ] Top products by volume
- [ ] Stock value by warehouse
- [ ] SLA compliance: % orders picked/packed within X hours
- [ ] Idle stock: products not moved in 30+ days

### 8. Wave Planning
- [ ] Schedule pick waves (every 2 hours, hourly, etc.)
- [ ] Batch pending orders into optimal waves
- [ ] Priority rules: express first, then standard
- [ ] Capacity limits: max X items per pick list per picker
- [ ] Auto-assign pickers based on zone expertise

### 9. Kitting / Bundling
- [ ] Kit/bundle product definition (Kit = Item A + Item B + Item C)
- [ ] Auto-explode kit into individual items for picking
- [ ] Pre-assembled kit stock tracking
- [ ] Kit assembly task for warehouse staff

### 10. Quality Control
- [ ] QC checkpoint before packing
- [ ] Photo documentation of packed orders
- [ ] Weight verification (expected vs actual)
- [ ] QC hold: flag order for review before dispatch
- [ ] QC pass/fail with reason codes
