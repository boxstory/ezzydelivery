# Fulfillment Store Auto-Creation

## Overview
Businesses with fulfillment service enabled will automatically get a "Fulfillment Store" pickup location. This location appears in the order creation form as a pickup option.

## Features

### 1. **Automatic Creation** ✅
When a business enables fulfillment service, a default "Fulfillment Store" pickup location is automatically created.

### 2. **Signal-Based** ✅
Uses Django signals to detect when `fulfillment_service_enabled` is set to `True`.

### 3. **Shows in Add Order Form** ✅
The fulfillment store automatically appears in the pickup location dropdown when adding orders.

---

## How It Works

### Signal Triggers

**File:** `business/signals.py`

The signal automatically creates a fulfillment store when:

1. **New Business Created**
   - Business has `fulfillment_service_enabled=True`
   - Fulfillment store created immediately

2. **Existing Business Enables Service**
   - Admin sets `fulfillment_service_enabled=True`
   - Fulfillment store created on save

### Fulfillment Store Details

When created, the pickup location has these attributes:
```python
{
    'pickup_location_title': 'Fulfillment Store',
    'locality': 'EzzyDelivery Fulfillment Center',
    'pickup_status': 'active',
    'business': <business_instance>
}
```

---

## Setup for Existing Businesses

If you have existing businesses with fulfillment enabled that don't have fulfillment stores yet:

### Run Management Command

```bash
# Activate virtual environment first
venv\Scripts\activate

# Preview what will be created (dry run)
python manage.py create_fulfillment_stores --dry-run

# Actually create the stores
python manage.py create_fulfillment_stores
```

### Expected Output

```
============================================================
CREATE FULFILLMENT STORES
============================================================

Found 5 businesses with fulfillment service enabled

  ✓  Created: Fulfillment Store for ABC Store (ID: 101)
  ✓  Created: Fulfillment Store for XYZ Shop (ID: 102)
  ⏭  Skipped: DEF Market (ID: 103) - Fulfillment store already exists
  ✓  Created: Fulfillment Store for GHI Boutique (ID: 104)
  ✓  Created: Fulfillment Store for JKL Warehouse (ID: 105)

============================================================
COMPLETE!
Created: 4 fulfillment stores
Skipped: 1 existing stores
Total businesses: 5
============================================================
```

---

## How Businesses See It

### 1. Add Order Form
When creating an order, the pickup location dropdown will show:
```
📍 Pickup Location:
  - Store Location 1
  - Store Location 2
  - Fulfillment Store  ← Automatically added
  - Warehouse A
```

### 2. Order List
Orders can be filtered by pickup location, including the fulfillment store.

### 3. Pickup Location Management
The fulfillment store appears in:
- `Business Dashboard → Stores List`
- Can be edited like any other pickup location
- Can be deactivated if needed (set `pickup_status='inactive'`)

---

## Enable Fulfillment Service

### Via Django Admin

1. Go to Django Admin: `http://127.0.0.1:8004/admin/`
2. Navigate to `Business → Businesses`
3. Select a business
4. Check `Fulfillment service enabled` checkbox
5. Save

**Result:** Fulfillment Store is automatically created!

### Via Code

```python
from business.models import Business

business = Business.objects.get(business_id=123)
business.fulfillment_service_enabled = True
business.save()

# Fulfillment Store pickup location is automatically created by signal
```

---

## Customization

### Change Default Name

Edit `business/signals.py` line 48:
```python
pickup_location_title="Your Custom Name",  # Change this
```

### Change Default Locality

Edit `business/signals.py` line 49:
```python
locality="Your Fulfillment Center Address",  # Change this
```

### Add Additional Fields

You can extend the signal to set:
- `pickup_zone_no`
- `pickup_street_no`
- `pickup_building_no`
- `pickup_lat` / `pickup_lon` (GPS coordinates)

Example:
```python
PickupLocation.objects.create(
    business=instance,
    pickup_location_title="Fulfillment Store",
    locality="EzzyDelivery Fulfillment Center",
    pickup_zone_no=44,  # Add zone
    pickup_street_no=123,  # Add street
    pickup_status='active',
)
```

---

## Troubleshooting

### Fulfillment store not appearing?

1. **Check if fulfillment service is enabled:**
   ```python
   python manage.py shell
   >>> from business.models import Business
   >>> business = Business.objects.get(business_id=YOUR_ID)
   >>> business.fulfillment_service_enabled
   True  # Should be True
   ```

2. **Check if store exists:**
   ```python
   >>> from business.models import PickupLocation
   >>> PickupLocation.objects.filter(
   ...     business=business,
   ...     pickup_location_title__icontains="fulfillment"
   ... ).exists()
   True  # Should be True
   ```

3. **Manually create if needed:**
   ```bash
   python manage.py create_fulfillment_stores
   ```

### Signal not firing?

1. **Restart Django server** after adding signals
2. Check `business/apps.py` has `ready()` method that imports signals
3. Check logs for errors

---

## Files Modified/Created

### Created:
- ✅ `business/signals.py` - Auto-creation signal
- ✅ `business/management/commands/create_fulfillment_stores.py` - Management command

### Already Exists:
- ✅ `business/apps.py` - Signal registration (line 10)
- ✅ `business/models.py` - Business model with `fulfillment_service_enabled` field
- ✅ `orders/forms.py` - Add order form with pickup location field

---

## Benefits

1. **No Manual Work** - Store created automatically
2. **Consistent Naming** - All fulfillment stores have the same name
3. **Always Available** - Can't forget to create it
4. **Centralized Logic** - One place to manage creation
5. **Audit Trail** - `fulfillment_activated_at` timestamp is set

---

## Testing

```python
# Test signal
from business.models import Business, PickupLocation

# Create business with fulfillment enabled
business = Business.objects.create(
    business_name="Test Shop",
    business_code="TEST001",
    fulfillment_service_enabled=True,
    # ... other required fields
)

# Check if fulfillment store was created
fulfillment_store = PickupLocation.objects.filter(
    business=business,
    pickup_location_title="Fulfillment Store"
).first()

assert fulfillment_store is not None, "Fulfillment store should be created"
assert fulfillment_store.pickup_status == 'active'
print("✅ Test passed!")
```
