# Warehouse Dummy Data Creation

This guide explains how to create dummy warehouse data similar to the EzzyDelivery Fulfillment Center.

## Warehouse Structure

The dummy warehouse creates:

- **Warehouse**: EzzyDelivery Fulfillment Center - Sudan (WH-001-SDN)
- **2 Zones**: A, B
- **10 Racks per zone**: A-J (alphabetic naming)
- **5 Shelves per rack**: S01-S05 (numeric naming)
- **4 Bins per shelf**: B01-B04 (numeric naming)
- **Total**: 2 zones × 10 racks × 5 shelves × 4 bins = **400 bins**

### Example Structure

```
Zone A
├── Rack H
│   ├── Shelf S1 (50×200×50 cm)
│   │   ├── Bin B01 (50×50×50 cm) → Code: A-H-S01-B01
│   │   ├── Bin B02 (50×50×50 cm) → Code: A-H-S01-B02
│   │   ├── Bin B03 (50×50×50 cm) → Code: A-H-S01-B03
│   │   └── Bin B04 (50×50×50 cm) → Code: A-H-S01-B04
│   ├── Shelf S2...
│   └── ...
├── Rack I...
└── ...
```

## Method 1: Management Command (Recommended)

### Local Development

```bash
# Activate virtual environment
source venvezdl/Scripts/activate  # Windows
# OR
source venvezdl/bin/activate      # Linux/Mac

# Run the command
python manage.py create_dummy_warehouse

# To recreate (delete existing first)
python manage.py create_dummy_warehouse --delete
```

### Production Server

```bash
# SSH into the server
ssh root@ezzydelivery.qa

# Navigate to project directory
cd /opt/ezzydelivery

# Activate virtual environment
source venv/bin/activate

# Run the command
python manage.py create_dummy_warehouse

# To recreate (delete existing first)
python manage.py create_dummy_warehouse --delete
```

## Method 2: Django Shell Script

### Local Development

```bash
# Activate virtual environment
source venvezdl/Scripts/activate  # Windows

# Run via shell
python manage.py shell < create_dummy_warehouse.py
```

### Production Server

```bash
# SSH into the server
ssh root@ezzydelivery.qa

# Navigate to project directory
cd /opt/ezzydelivery

# Activate virtual environment
source venv/bin/activate

# Run via shell
python manage.py shell < create_dummy_warehouse.py
```

### Interactive Django Shell

```python
# Start Django shell
python manage.py shell

# Then paste the script content or run:
exec(open('create_dummy_warehouse.py').read())
```

## Method 3: Manual Creation via Django Admin

1. Log in to Django admin at `/admin/`
2. Navigate to **Warehouse → Warehouses**
3. Click **Add Warehouse**
4. Fill in the details:
   - **Name**: EzzyDelivery Fulfillment Center - Sudan
   - **Code**: WH-001-SDN
   - **Total zones**: 2
   - **Racks per zone**: 10
   - **Shelves per rack**: 5
   - **Bins per shelf**: 4
   - **Zone naming pattern**: A,B
   - **Rack naming pattern**: alpha
   - **Shelf naming pattern**: numeric
   - **Bin naming pattern**: numeric
   - Check **Is capacity configured**
5. Save the warehouse
6. Use the admin actions to generate the storage locations automatically

## Verifying Creation

### Via Django Shell

```python
python manage.py shell
```

```python
from warehouse.models import Warehouse, StorageLocation

# Check warehouse
warehouse = Warehouse.objects.get(code='WH-001-SDN')
print(f"Warehouse: {warehouse.name}")
print(f"Total capacity: {warehouse.total_capacity} bins")

# Check locations by type
zones = StorageLocation.objects.filter(warehouse=warehouse, location_type='zone')
racks = StorageLocation.objects.filter(warehouse=warehouse, location_type='rack')
shelves = StorageLocation.objects.filter(warehouse=warehouse, location_type='shelf')
bins = StorageLocation.objects.filter(warehouse=warehouse, location_type='bin')

print(f"Zones: {zones.count()}")
print(f"Racks: {racks.count()}")
print(f"Shelves: {shelves.count()}")
print(f"Bins: {bins.count()}")

# Example bin
example_bin = bins.first()
print(f"\nExample bin: {example_bin.code}")
print(f"  Full path: {example_bin.full_path}")
print(f"  Dimensions: {example_bin.width_cm}×{example_bin.length_cm}×{example_bin.height_cm} cm")
print(f"  Barcode: {example_bin.barcode}")
```

### Via Admin Interface

1. Go to `/admin/warehouse/warehouse/`
2. Click on "WH-001-SDN - EzzyDelivery Fulfillment Center - Sudan"
3. View the warehouse details and capacity summary
4. Navigate to **Storage Locations** to browse zones, racks, shelves, and bins

### Via SQL

```sql
-- Connect to PostgreSQL
psql -U zyadmin -d ezzy_dl_db

-- Check warehouse
SELECT code, name, total_zones, racks_per_zone, shelves_per_rack, bins_per_shelf
FROM warehouse_warehouse
WHERE code = 'WH-001-SDN';

-- Count locations by type
SELECT location_type, COUNT(*)
FROM warehouse_storagelocation
WHERE warehouse_id = (SELECT id FROM warehouse_warehouse WHERE code = 'WH-001-SDN')
GROUP BY location_type
ORDER BY location_type;

-- Example bins from Zone A, Rack H, Shelf 1
SELECT code, name, width_cm, length_cm, height_cm, barcode
FROM warehouse_storagelocation
WHERE warehouse_id = (SELECT id FROM warehouse_warehouse WHERE code = 'WH-001-SDN')
  AND location_type = 'bin'
  AND code LIKE 'A-H-S01-%'
ORDER BY code;
```

## Deleting Dummy Data

### Via Management Command

```bash
python manage.py create_dummy_warehouse --delete
```

### Via Django Shell

```python
python manage.py shell
```

```python
from warehouse.models import Warehouse

# Delete warehouse (cascade deletes all storage locations)
Warehouse.objects.filter(code='WH-001-SDN').delete()
print("✓ Warehouse deleted successfully")
```

### Via SQL

```sql
-- Connect to PostgreSQL
psql -U zyadmin -d ezzy_dl_db

-- Delete warehouse (cascade deletes all storage locations)
DELETE FROM warehouse_warehouse WHERE code = 'WH-001-SDN';
```

## Customizing the Dummy Data

To create a different warehouse structure, modify the script parameters:

```python
# In create_dummy_warehouse.py or management command

# Change warehouse details
warehouse_code = 'WH-002-BHR'
warehouse_name = 'EzzyDelivery FC - Bahrain'

# Change structure
zones = ['NORTH', 'SOUTH', 'EAST', 'WEST']  # 4 zones
racks_per_zone = 15  # 15 racks per zone
shelves_per_rack = 8  # 8 shelves per rack
bins_per_shelf = 6   # 6 bins per shelf

# Change dimensions
shelf_width = 60
shelf_length = 250
shelf_height = 60

bin_width = 60
bin_length = 60
bin_height = 60
```

## Files Created

1. **Management Command**: `warehouse/management/commands/create_dummy_warehouse.py`
2. **Shell Script**: `create_dummy_warehouse.py` (project root)
3. **This README**: `warehouse/README_DUMMY_DATA.md`

## Support

For issues or questions:
- Check the Django admin logs at `/admin/`
- Review server logs: `sudo journalctl -u gunicornezzy -f`
- Test in Django shell before running on production
