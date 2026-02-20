# Quick Commands: Create Dummy Warehouse on Production

## 🚀 Fast Setup (Copy & Paste)

```bash
# 1. SSH into production server
ssh root@ezzydelivery.qa

# 2. Navigate to project
cd /opt/ezzydelivery

# 3. Activate virtual environment
source venv/bin/activate

# 4. Create dummy warehouse
python manage.py create_dummy_warehouse
```

## 📊 Expected Output

```
Creating EzzyDelivery Fulfillment Center - Sudan...
✓ Created warehouse: WH-001-SDN - EzzyDelivery Fulfillment Center - Sudan
  ✓ Zone A
  ✓ Zone B

============================================================
WAREHOUSE CREATION COMPLETE
============================================================
Warehouse: EzzyDelivery Fulfillment Center - Sudan
Code: WH-001-SDN

Structure:
  • Zones: 2
  • Racks: 20 (10 per zone)
  • Shelves: 100 (5 per rack)
  • Bins: 400 (4 per shelf)
  • Total locations: 522

Calculated capacity: 400 bins

Example locations:
  • A-A-S01-B01 - Bin 01 (50×50×50 cm)
  • A-A-S01-B02 - Bin 02 (50×50×50 cm)
  • A-A-S01-B03 - Bin 03 (50×50×50 cm)
  • A-A-S01-B04 - Bin 04 (50×50×50 cm)

✓ Dummy warehouse created successfully!
```

## 🔄 If Warehouse Already Exists

```bash
# Delete and recreate
python manage.py create_dummy_warehouse --delete
```

## ✅ Verify Creation

```bash
# Quick verification via Django shell
python manage.py shell
```

```python
from warehouse.models import Warehouse, StorageLocation

wh = Warehouse.objects.get(code='WH-001-SDN')
print(f"✓ {wh.name}")
print(f"✓ Total capacity: {wh.total_capacity} bins")
print(f"✓ Bins created: {StorageLocation.objects.filter(warehouse=wh, location_type='bin').count()}")
```

Type `exit()` to quit Django shell.

## 🗑️ Delete Dummy Warehouse

```bash
python manage.py shell
```

```python
from warehouse.models import Warehouse
Warehouse.objects.filter(code='WH-001-SDN').delete()
exit()
```

## 📍 Warehouse Details Created

| Field | Value |
|-------|-------|
| **Code** | WH-001-SDN |
| **Name** | EzzyDelivery Fulfillment Center - Sudan |
| **Location** | Khartoum, Sudan |
| **Zones** | 2 (A, B) |
| **Racks** | 10 per zone (A-J) |
| **Shelves** | 5 per rack (S01-S05) |
| **Bins** | 4 per shelf (B01-B04) |
| **Total Bins** | 400 |
| **Shelf Size** | 50×200×50 cm |
| **Bin Size** | 50×50×50 cm |

## 🏷️ Example Location Codes

```
Zone A → Rack H → Shelf S1 → Bins:
  • A-H-S01-B01 (Barcode: LOC-WH-001-SDN-A-H-S01-B01)
  • A-H-S01-B02 (Barcode: LOC-WH-001-SDN-A-H-S01-B02)
  • A-H-S01-B03 (Barcode: LOC-WH-001-SDN-A-H-S01-B03)
  • A-H-S01-B04 (Barcode: LOC-WH-001-SDN-A-H-S01-B04)

Zone B → Rack A → Shelf S1 → Bins:
  • B-A-S01-B01 (Barcode: LOC-WH-001-SDN-B-A-S01-B01)
  • B-A-S01-B02 (Barcode: LOC-WH-001-SDN-B-A-S01-B02)
  • B-A-S01-B03 (Barcode: LOC-WH-001-SDN-B-A-S01-B03)
  • B-A-S01-B04 (Barcode: LOC-WH-001-SDN-B-A-S01-B04)
```

## 🌐 View in Admin

After creation, access at:
```
https://ezzydelivery.qa/admin/warehouse/warehouse/
```

1. Login to Django admin
2. Navigate to **Warehouse → Warehouses**
3. Click on "WH-001-SDN"
4. View all storage locations under **Storage Locations**
