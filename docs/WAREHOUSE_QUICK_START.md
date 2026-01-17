# Warehouse System - Quick Start Guide

## 5-Minute Setup

Follow these 5 simple steps to get the warehouse system running:

---

## Step 1: Run Migration (2 minutes)

### Option A: Double-Click ⭐
```
Double-click: CREATE_WAREHOUSE_MIGRATION.bat
Press Y to apply migration
```

### Option B: Command Line
```bash
python manage.py makemigrations warehouse
python manage.py migrate warehouse
```

**Expected Result:**
```
✓ Migrations created
✓ Database updated
```

---

## Step 2: Create Warehouse (1 minute)

1. Open: http://127.0.0.1:8004/admin/warehouse/warehouse/
2. Click: **"Add Fulfillment Center"**
3. Fill in:
   - Name: `Central Fulfillment Center`
   - Leave code empty (auto-generates)
   - City: `Manama`
   - ☑ Is active
   - ☑ Is default
4. Click: **Save**

**Expected Result:**
```
✓ Warehouse created with code: WH-FC-XXXXXXXX
```

---

## Step 3: Add Location (1 minute)

1. Open: http://127.0.0.1:8004/admin/warehouse/warehouselocation/
2. Click: **"Add Warehouse Location"**
3. Fill in:
   - Warehouse: Select your warehouse
   - Name: `Main Gate`
   - Code: `MG`
   - ☑ Is active
   - ☑ Is default
4. Click: **Save**

**Expected Result:**
```
✓ Location created: WH-FC-XXXXXXXX/Main Gate
```

---

## Step 4: Link Seller (1 minute)

1. Open: http://127.0.0.1:8004/admin/warehouse/sellerwarehouselink/
2. Click: **"Add Seller Warehouse Link"**
3. Fill in:
   - Business: Select a seller
   - Warehouse: Select your warehouse
   - Default location: Select "Main Gate"
   - Priority: `100`
   - ☑ Is active
   - ☑ Is default
4. Click: **Save**

**Expected Result:**
```
✓ Seller linked to warehouse
✓ Default settings configured
```

---

## Step 5: Test (30 seconds)

### Test Auto-Selection:

```bash
python manage.py shell
```

```python
from orders.models import Order
from warehouse.utils import get_recommended_warehouse_location

# Get any test order
order = Order.objects.first()

# Get recommendation
location = get_recommended_warehouse_location(order)

print(f"Recommended: {location.warehouse.name} / {location.name}")
# Output: Recommended: Central Fulfillment Center / Main Gate
```

**Expected Result:**
```
✓ Auto-selection working
✓ Returns correct location
```

---

## ✅ Setup Complete!

You now have:
- ✓ One fulfillment center
- ✓ One warehouse location
- ✓ One seller linked
- ✓ Auto-selection functional

---

## What's Next?

### Add GPS Coordinates (Optional but Recommended):

1. Get coordinates from [Google Maps](https://maps.google.com)
2. Edit warehouse: Add latitude/longitude
3. Edit location: Add latitude/longitude

This enables distance-based auto-selection.

### Add More Locations:

If your warehouse has multiple gates/entrances:

1. Add more locations with different names
2. Assign zone numbers to locations
3. Set operating hours
4. Add driver instructions

### Link More Sellers:

For each additional seller:

1. Create new `SellerWarehouseLink`
2. Set priority (higher = preferred)
3. Mark one as default per seller

---

## Quick Commands

### Check Status:
```bash
# List warehouses
python manage.py shell -c "from warehouse.models import Warehouse; print(Warehouse.objects.all())"

# List locations
python manage.py shell -c "from warehouse.models import WarehouseLocation; print(WarehouseLocation.objects.all())"

# List links
python manage.py shell -c "from warehouse.models import SellerWarehouseLink; print(SellerWarehouseLink.objects.all())"
```

### Test Auto-Selection:
```python
from warehouse.utils import get_recommended_warehouse_location
from orders.models import Order

order = Order.objects.first()
location = get_recommended_warehouse_location(order)
print(location)
```

---

## Troubleshooting

### "No module named django"
→ Activate virtual environment first

### "Table doesn't exist"
→ Run migrations: `python manage.py migrate warehouse`

### "No warehouse locations found"
→ Create at least one location (Step 3)

### "No warehouse links found"
→ Link seller to warehouse (Step 4)

---

## Full Documentation

For detailed information:
- [WAREHOUSE_SETUP_INSTRUCTIONS.md](WAREHOUSE_SETUP_INSTRUCTIONS.md) - Complete setup guide
- [WAREHOUSE_SYSTEM_GUIDE.md](WAREHOUSE_SYSTEM_GUIDE.md) - Technical reference
- [WAREHOUSE_IMPLEMENTATION_COMPLETE.md](WAREHOUSE_IMPLEMENTATION_COMPLETE.md) - Implementation summary

---

## Admin URLs

- **Warehouses:** http://127.0.0.1:8004/admin/warehouse/warehouse/
- **Locations:** http://127.0.0.1:8004/admin/warehouse/warehouselocation/
- **Links:** http://127.0.0.1:8004/admin/warehouse/sellerwarehouselink/

---

## That's It! 🎉

Your warehouse system is ready to use.

**Time Taken:** ~5 minutes
**Result:** Fully functional fulfillment center management
