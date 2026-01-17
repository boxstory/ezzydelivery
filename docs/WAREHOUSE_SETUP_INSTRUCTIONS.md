# Warehouse Management System - Setup Instructions

## Quick Start

Follow these steps to set up the new warehouse management system:

---

## Step 1: Create Database Migration

### Option A: Use Batch File (Easiest) ⭐

1. Double-click: **`CREATE_WAREHOUSE_MIGRATION.bat`**
2. Review the migration
3. Choose to apply it (Y/N)

### Option B: Manual Command Line

```bash
# Activate virtual environment
venvezdl\Scripts\activate
# or
venv\Scripts\activate

# Create migration
python manage.py makemigrations warehouse --name restructure_warehouse_system

# Preview SQL (optional)
python manage.py sqlmigrate warehouse restructure_warehouse_system

# Apply migration
python manage.py migrate warehouse
```

---

## Step 2: Migrate Existing Data (If Applicable)

If you have existing warehouses in the database:

```bash
# Run data migration script
python migrate_existing_warehouses.py
```

This will:
- Update existing warehouse records
- Create default warehouse locations
- Prepare for seller-warehouse linking

**Note:** You'll still need to manually create `SellerWarehouseLink` records in Django Admin.

---

## Step 3: Create Your First Fulfillment Center

### Via Django Admin:

1. Start Django server:
   ```bash
   python manage.py runserver 8004
   ```

2. Go to: [Django Admin](http://127.0.0.1:8004/admin/)

3. Navigate to: **Warehouse → Fulfillment Centers**

4. Click: **Add Fulfillment Center**

5. Fill in the form:

   **Basic Info:**
   - Name: `Central Fulfillment Center`
   - Code: (leave empty for auto-generation)
   - Description: `Main fulfillment center for all operations`

   **Location Details:**
   - Address: Full warehouse address
   - City: `Manama` (or your city)
   - State: `Capital Governorate`
   - Postal Code: `317`
   - Country: `Bahrain`
   - Latitude: `26.2285` (get from Google Maps)
   - Longitude: `50.5860` (get from Google Maps)

   **Contact:**
   - Phone: Warehouse phone number
   - Email: Warehouse email

   **Status:**
   - ☑ Is active
   - ☑ Is default (check this for your main warehouse)

   **Management:**
   - Manager: Select a staff user

6. Click: **Save**

---

## Step 4: Add Warehouse Locations

### Why Multiple Locations?

Large warehouses may have:
- Multiple gates/entrances
- Different dispatch points for different zones
- Separate pickup areas for different order types

### Create Location:

1. Go to: **Warehouse → Warehouse Locations**

2. Click: **Add Warehouse Location**

3. Fill in:

   **Location Info:**
   - Warehouse: Select the warehouse you created
   - Name: `North Gate`
   - Code: `NG`
   - ☑ Is active
   - ☑ Is default (for the main entrance)

   **Address & Zone:**
   - Address: `North entrance, near parking lot A`
   - Zone number: `44` (if this location primarily serves zone 44)
   - Latitude: GPS coordinate
   - Longitude: GPS coordinate

   **Operations:**
   - Operating hours: `Mon-Fri 8AM-5PM, Sat 9AM-2PM`
   - Notes: `Enter through main gate, turn left. Show delivery task to security.`

4. Click: **Save**

5. Repeat for additional locations (e.g., "South Gate", "East Dock", etc.)

---

## Step 5: Link Sellers to Warehouses

### For Each Seller:

1. Go to: **Warehouse → Seller Warehouse Links**

2. Click: **Add Seller Warehouse Link**

3. Fill in:

   **Link Details:**
   - Business: Select the seller
   - Warehouse: Select the fulfillment center
   - Default location: Select a location at this warehouse
   - ☑ Is active

   **Priority & Defaults:**
   - ☑ Is default (check for primary warehouse)
   - Priority: `100` (higher = preferred for auto-selection)

   **Notes:**
   - Example: `Primary fulfillment center for all orders`

4. Click: **Save**

5. **Repeat for additional warehouses** if the seller uses multiple fulfillment centers

### Important:
- Each seller should have **at least one** linked warehouse
- Only **one** link should have `Is default = True` per seller
- Higher priority values are preferred during auto-selection

---

## Step 6: Verify Setup

### Check 1: Warehouse Admin

1. Go to: [Fulfillment Centers](http://127.0.0.1:8004/admin/warehouse/warehouse/)
2. Verify your warehouse appears with:
   - Green checkmark for "Is active"
   - Correct city and manager

### Check 2: Locations

1. Go to: [Warehouse Locations](http://127.0.0.1:8004/admin/warehouse/warehouselocation/)
2. Verify locations appear with:
   - Full code (e.g., `WH-FC-12345678-NG`)
   - Correct zone numbers
   - Active status

### Check 3: Seller Links

1. Go to: [Seller Warehouse Links](http://127.0.0.1:8004/admin/warehouse/sellerwarehouselink/)
2. Verify each seller has:
   - At least one active link
   - One link marked as default
   - Default location set

---

## Step 7: Test Order Flow

### Create Test Order:

1. Log in as a seller

2. Go to: [Add Order](http://127.0.0.1:8004/orders/add/)

3. Fill in order details

4. **Pickup Location:** Select `Fulfillment Store`
   - ⚠️ This should be the ONLY option visible to sellers
   - ⚠️ No warehouse details should be visible

5. Submit order

### Verify Backend:

1. Log in as staff/workforce

2. Go to order detail page

3. During delivery task assignment:
   - System should show available warehouse locations
   - Auto-suggestion based on customer location
   - Staff can manually override selection

---

## Configuration Tips

### GPS Coordinates:

**How to Get:**
1. Go to [Google Maps](https://maps.google.com)
2. Right-click on warehouse location
3. Select "What's here?"
4. Copy latitude and longitude

**Why Important:**
- Enables distance-based warehouse selection
- Automatically suggests nearest warehouse location
- Optimizes driver routing

### Zone Mapping:

**Link Locations to Zones:**
- If you have delivery zones (1-50), assign zone numbers to warehouse locations
- This enables zone-based matching during task assignment
- Example: North Gate → Zone 44, South Gate → Zone 25

### Priority Settings:

**Use Priority for:**
- Preferred warehouses get higher priority (80-100)
- Backup warehouses get lower priority (20-40)
- Emergency/temporary warehouses get priority 10

---

## Troubleshooting

### Issue: Migration fails with "column already exists"

**Solution:**
```bash
# Reset warehouse migrations (CAUTION: Data loss)
python manage.py migrate warehouse zero
python manage.py migrate warehouse
```

### Issue: Cannot create warehouse - "business field required"

**Solution:**
- This error means you're using old code
- Make sure models.py has been updated
- Restart Django server
- Clear browser cache

### Issue: Seller has no warehouses available

**Solution:**
1. Create `SellerWarehouseLink` record
2. Set `is_active = True`
3. Select default location
4. Save

### Issue: "Fulfillment Store" not showing in order form

**Solution:**
1. Check: `business.fulfillment_service_enabled = True`
2. Verify: "Fulfillment Store" `PickupLocation` exists
3. Check: `pickup_status = 'active'`
4. Run: `python manage.py create_fulfillment_stores` (if not done)

---

## Advanced Configuration

### Multiple Warehouses per Seller:

**Scenario:** Seller has products in multiple fulfillment centers

**Setup:**
1. Create multiple `SellerWarehouseLink` records
2. Set different priorities
3. Mark one as default
4. During task assignment, staff selects based on:
   - Product availability
   - Customer location
   - Warehouse capacity

### Auto-Selection Logic:

The system recommends warehouse locations based on:

1. **Zone Match** (Highest Priority)
   - Customer zone = warehouse location zone

2. **GPS Distance**
   - Nearest warehouse location to customer

3. **Link Priority**
   - Higher priority = preferred

4. **Default Warehouse**
   - Seller's default warehouse

5. **Default Location**
   - Warehouse's default location

### Operating Hours:

**Format Examples:**
```
Mon-Fri 8AM-5PM
Mon-Sat 9AM-6PM, Sun Closed
24/7
Mon-Thu 8AM-5PM, Fri 8AM-12PM, Sat-Sun Closed
```

---

## API Integration (Future)

### Staff Endpoints:

```
GET    /api/warehouses/                    # List all warehouses
POST   /api/warehouses/                    # Create warehouse
GET    /api/warehouses/{id}/               # Warehouse detail
PATCH  /api/warehouses/{id}/               # Update warehouse
GET    /api/warehouses/{id}/locations/     # List locations
POST   /api/seller-warehouse-links/        # Create link
GET    /api/orders/{id}/recommended-warehouse/  # Auto-select
```

---

## Security Notes

### Access Control:

- ✅ Only staff can create warehouses
- ✅ Only staff can manage locations
- ✅ Only staff can create seller-warehouse links
- ❌ Sellers cannot view warehouse details
- ❌ Customers never see warehouse information

### Data Privacy:

- Warehouse addresses are internal-only
- GPS coordinates not exposed to customers
- Only "Fulfillment Store" name shown in orders

---

## Maintenance

### Regular Tasks:

**Weekly:**
- Review warehouse capacity
- Check location utilization
- Verify seller links are active

**Monthly:**
- Update GPS coordinates if needed
- Review and adjust priorities
- Archive inactive locations

**Quarterly:**
- Audit warehouse-seller relationships
- Optimize zone mappings
- Review operating hours

---

## Support Resources

### Documentation:
- [WAREHOUSE_SYSTEM_GUIDE.md](WAREHOUSE_SYSTEM_GUIDE.md) - Complete technical guide
- Django Admin inline help texts
- Model docstrings

### Admin URLs:
- Warehouses: http://127.0.0.1:8004/admin/warehouse/warehouse/
- Locations: http://127.0.0.1:8004/admin/warehouse/warehouselocation/
- Links: http://127.0.0.1:8004/admin/warehouse/sellerwarehouselink/

---

## Summary Checklist

Before going live, ensure:

- [ ] Database migration applied successfully
- [ ] At least one fulfillment center created
- [ ] At least one location per warehouse
- [ ] All active sellers linked to warehouses
- [ ] GPS coordinates configured
- [ ] Zone numbers mapped
- [ ] Default warehouses set
- [ ] Default locations set
- [ ] Operating hours documented
- [ ] Driver notes added
- [ ] Test order created and assigned
- [ ] Staff trained on new workflow

---

## Need Help?

If you encounter issues:

1. Check Django logs for errors
2. Verify virtual environment is activated
3. Ensure all migrations are applied
4. Review model field requirements
5. Check admin permissions

For technical support, refer to the development team.

---

**Next Steps After Setup:**

1. ✅ Migration complete
2. ✅ Warehouses created
3. ✅ Locations configured
4. ✅ Sellers linked
5. 🔄 Update delivery task assignment UI (pending)
6. 🔄 Implement auto-selection logic (pending)
7. 🔄 Create staff dashboard (pending)

---

Last Updated: 2026-01-17
