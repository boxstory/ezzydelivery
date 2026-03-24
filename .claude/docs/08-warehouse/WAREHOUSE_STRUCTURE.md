# Warehouse Structure - WH-001-SDN

## Overview

**EZZYDELIVERY FULFILLMENT CENTER - SUDAN (WH-001-SDN)**

```
2 ZONES | 10 RACKS | 50 SHELVES | 200 BINS | 262 TOTAL
```

## Complete Hierarchy

### Zone HL (High Level)
- **Rack A** (5 shelves, 20 bins)
  - Shelf A-S1 → Bins: A-S1-B01, A-S1-B02, A-S1-B03, A-S1-B04
  - Shelf A-S2 → Bins: A-S2-B01, A-S2-B02, A-S2-B03, A-S2-B04
  - Shelf A-S3 → Bins: A-S3-B01, A-S3-B02, A-S3-B03, A-S3-B04
  - Shelf A-S4 → Bins: A-S4-B01, A-S4-B02, A-S4-B03, A-S4-B04
  - Shelf A-S5 → Bins: A-S5-B01, A-S5-B02, A-S5-B03, A-S5-B04

- **Rack B** (5 shelves, 20 bins)
  - Shelf B-S1 → Bins: B-S1-B01, B-S1-B02, B-S1-B03, B-S1-B04
  - Shelf B-S2 → Bins: B-S2-B01, B-S2-B02, B-S2-B03, B-S2-B04
  - Shelf B-S3 → Bins: B-S3-B01, B-S3-B02, B-S3-B03, B-S3-B04
  - Shelf B-S4 → Bins: B-S4-B01, B-S4-B02, B-S4-B03, B-S4-B04
  - Shelf B-S5 → Bins: B-S5-B01, B-S5-B02, B-S5-B03, B-S5-B04

- **Rack C** (5 shelves, 20 bins)
  - Shelf C-S1 → Bins: C-S1-B01, C-S1-B02, C-S1-B03, C-S1-B04
  - Shelf C-S2 → Bins: C-S2-B01, C-S2-B02, C-S2-B03, C-S2-B04
  - Shelf C-S3 → Bins: C-S3-B01, C-S3-B02, C-S3-B03, C-S3-B04
  - Shelf C-S4 → Bins: C-S4-B01, C-S4-B02, C-S4-B03, C-S4-B04
  - Shelf C-S5 → Bins: C-S5-B01, C-S5-B02, C-S5-B03, C-S5-B04

- **Rack D** (5 shelves, 20 bins)
  - Shelf D-S1 → Bins: D-S1-B01, D-S1-B02, D-S1-B03, D-S1-B04
  - Shelf D-S2 → Bins: D-S2-B01, D-S2-B02, D-S2-B03, D-S2-B04
  - Shelf D-S3 → Bins: D-S3-B01, D-S3-B02, D-S3-B03, D-S3-B04
  - Shelf D-S4 → Bins: D-S4-B01, D-S4-B02, D-S4-B03, D-S4-B04
  - Shelf D-S5 → Bins: D-S5-B01, D-S5-B02, D-S5-B03, D-S5-B04

- **Rack E** (5 shelves, 20 bins)
  - Shelf E-S1 → Bins: E-S1-B01, E-S1-B02, E-S1-B03, E-S1-B04
  - Shelf E-S2 → Bins: E-S2-B01, E-S2-B02, E-S2-B03, E-S2-B04
  - Shelf E-S3 → Bins: E-S3-B01, E-S3-B02, E-S3-B03, E-S3-B04
  - Shelf E-S4 → Bins: E-S4-B01, E-S4-B02, E-S4-B03, E-S4-B04
  - Shelf E-S5 → Bins: E-S5-B01, E-S5-B02, E-S5-B03, E-S5-B04

**Zone HL Subtotal:** 5 racks × 5 shelves × 4 bins = **100 bins**

---

### Zone AL (Aisle Level)
- **Rack A** (5 shelves, 20 bins)
- **Rack B** (5 shelves, 20 bins)
- **Rack C** (5 shelves, 20 bins)
- **Rack D** (5 shelves, 20 bins)
- **Rack E** (5 shelves, 20 bins)

**Zone AL Subtotal:** 5 racks × 5 shelves × 4 bins = **100 bins**

---

## Location Naming Convention

| Level | Naming Pattern | Example |
|-------|---------------|---------|
| **Zone** | HL, AL | HL |
| **Rack** | A, B, C, D, E | A |
| **Shelf** | [Rack]-S[Number] | A-S1 |
| **Bin** | [Shelf]-B[Number] | A-S1-B01 |

## Dimensions

| Level | Dimensions (W×L×H cm) | Max Weight |
|-------|----------------------|------------|
| **Shelf** | 50×200×50 | 100 kg |
| **Bin** | 50×50×50 | 25 kg |

## Barcodes

All locations have auto-generated barcodes:

```
LOC-WH-001-SDN-[LocationCode]
```

Examples:
- Zone HL: `LOC-WH-001-SDN-HL`
- Rack A: `LOC-WH-001-SDN-A`
- Shelf A-S1: `LOC-WH-001-SDN-A-S1`
- Bin A-S1-B01: `LOC-WH-001-SDN-A-S1-B01`

## Quick Stats

| Metric | Count |
|--------|-------|
| Zones | 2 |
| Racks | 10 (5 per zone) |
| Shelves | 50 (5 per rack) |
| Bins | 200 (4 per shelf) |
| **Total Locations** | **262** |

## Creation Commands

### Production Server
```bash
ssh root@ezzydelivery.qa
cd /opt/ezzydelivery
source venv/bin/activate
python manage.py create_dummy_warehouse
```

### Local Development
```bash
source venvezdl/Scripts/activate  # Windows
python manage.py create_dummy_warehouse
```

### Recreate (Delete & Create)
```bash
python manage.py create_dummy_warehouse --delete
```

## Verification Queries

### Django Shell
```python
from warehouse.models import Warehouse, StorageLocation

wh = Warehouse.objects.get(code='WH-001-SDN')
print(f"Total capacity: {wh.total_capacity} bins")

# Count by type
for location_type in ['zone', 'rack', 'shelf', 'bin']:
    count = StorageLocation.objects.filter(
        warehouse=wh,
        location_type=location_type
    ).count()
    print(f"{location_type}s: {count}")
```

### SQL
```sql
SELECT location_type, COUNT(*)
FROM warehouse_storagelocation
WHERE warehouse_id = (SELECT id FROM warehouse_warehouse WHERE code = 'WH-001-SDN')
GROUP BY location_type
ORDER BY location_type;
```

## Example Bin Lookup

```python
from warehouse.models import StorageLocation

# Find specific bin
bin = StorageLocation.objects.get(code='A-S1-B01')
print(f"Code: {bin.code}")
print(f"Barcode: {bin.barcode}")
print(f"Full path: {bin.full_path}")  # HL/A/A-S1/A-S1-B01
print(f"Dimensions: {bin.width_cm}×{bin.length_cm}×{bin.height_cm} cm")
```

## UI Display Format

As shown in the screenshot:

```
EZZYDELIVERY FULFILLMENT CENTER - SUDAN (WH-001-SDN)
2 ZONES | 10 RACKS | 50 SHELVES | 200 BINS | 262 TOTAL

Zone HL
  └─ Rack H (3 racks, Active)
      └─ H-S1 (Rack H Shelf 1, 50×200×50 cm, 4 bins)
          ├─ H-S1-B01 (50×50×50)
          ├─ H-S1-B02 (50×50×50)
          ├─ H-S1-B03 (50×50×50)
          └─ H-S1-B04 (50×50×50)
      └─ H-S2 (Rack H Shelf 2, 50×200×50 cm, 4 bins)
          ├─ H-S2-B01 (50×50×50)
          ├─ H-S2-B02 (50×50×50)
          ├─ H-S2-B03 (50×50×50)
          └─ H-S2-B04 (50×50×50)
```
