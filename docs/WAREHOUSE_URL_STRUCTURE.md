# Warehouse Module - URL Structure & Workflows

## URL Prefix

All warehouse URLs are accessed via: **`/workforce/warehouse/`**

Example: `http://127.0.0.1:8004/workforce/warehouse/inventory/`

---

## Complete URL Map

### Dashboard
| URL | Name | View | Description |
|-----|------|------|-------------|
| `/workforce/warehouse/` | `warehouse:dashboard` | `dashboard` | Main warehouse dashboard |

### Setup & Configuration

#### Warehouses (Fulfillment Centers)
| URL | Name | View | Description |
|-----|------|------|-------------|
| `/workforce/warehouse/warehouses/` | `warehouse:warehouse_list` | `warehouse_list` | List all warehouses |
| `/workforce/warehouse/warehouses/add/` | `warehouse:warehouse_add` | `warehouse_add` | Create new warehouse |
| `/workforce/warehouse/warehouses/<int:pk>/` | `warehouse:warehouse_detail` | `warehouse_detail` | View warehouse details |

#### Warehouse Locations
| URL | Name | View | Description |
|-----|------|------|-------------|
| `/workforce/warehouse/locations/` | `warehouse:location_list` | `location_list` | List all warehouse locations |
| `/workforce/warehouse/locations/add/` | `warehouse:location_add` | `location_add` | Create new location |

#### Seller-Warehouse Links
| URL | Name | View | Description |
|-----|------|------|-------------|
| `/workforce/warehouse/seller-warehouse-links/` | `warehouse:seller_warehouse_links` | `seller_warehouse_links` | List all seller-warehouse links |
| `/workforce/warehouse/seller-warehouse-links/add/` | `warehouse:seller_warehouse_link_add` | `seller_warehouse_link_add` | Create new link |
| `/workforce/warehouse/seller-warehouse-links/<int:pk>/` | `warehouse:seller_warehouse_link_detail` | `seller_warehouse_link_detail` | View link details |
| `/workforce/warehouse/seller-warehouse-links/<int:pk>/edit/` | `warehouse:seller_warehouse_link_edit` | `seller_warehouse_link_edit` | Edit link |
| `/workforce/warehouse/seller-warehouse-links/<int:pk>/delete/` | `warehouse:seller_warehouse_link_delete` | `seller_warehouse_link_delete` | Delete link (with confirmation) |

### Inventory Management

#### Inventory
| URL | Name | View | Description |
|-----|------|------|-------------|
| `/workforce/warehouse/inventory/` | `warehouse:inventory_list` | `inventory_list` | View all inventory |
| `/workforce/warehouse/inventory/<int:product_id>/` | `warehouse:stock_card` | `stock_card` | View stock card for product |

#### Transactions
| URL | Name | View | Description |
|-----|------|------|-------------|
| `/workforce/warehouse/transactions/` | `warehouse:transaction_list` | `transaction_list` | View all inventory transactions |

#### Alerts
| URL | Name | View | Description |
|-----|------|------|-------------|
| `/workforce/warehouse/alerts/` | `warehouse:low_stock_alerts` | `low_stock_alerts` | View low stock alerts |
| `/workforce/warehouse/alerts/<int:pk>/acknowledge/` | `warehouse:acknowledge_alert` | `acknowledge_alert` | Acknowledge alert |

### Operations

#### Receiving
| URL | Name | View | Description |
|-----|------|------|-------------|
| `/workforce/warehouse/receive/` | `warehouse:receive_stock` | `receive_stock` | Receive stock form |
| `/workforce/warehouse/receive/confirm/` | `warehouse:confirm_receive` | `confirm_receive` | Confirm stock receipt |

#### Pick Lists
| URL | Name | View | Description |
|-----|------|------|-------------|
| `/workforce/warehouse/pick-lists/` | `warehouse:pick_list_list` | `pick_list_list` | List all pick lists |
| `/workforce/warehouse/pick-lists/create/` | `warehouse:create_pick_list` | `create_pick_list` | Create new pick list |
| `/workforce/warehouse/pick-lists/<int:pk>/` | `warehouse:pick_list_detail` | `pick_list_detail` | View pick list details |
| `/workforce/warehouse/pick-lists/<int:pk>/assign/` | `warehouse:assign_pick_list` | `assign_pick_list` | Assign pick list to worker |

#### Cycle Counts
| URL | Name | View | Description |
|-----|------|------|-------------|
| `/workforce/warehouse/cycle-counts/` | `warehouse:cycle_count_list` | `cycle_count_list` | List all cycle counts |
| `/workforce/warehouse/cycle-counts/create/` | `warehouse:create_cycle_count` | `create_cycle_count` | Create new cycle count |
| `/workforce/warehouse/cycle-counts/<int:pk>/` | `warehouse:cycle_count_detail` | `cycle_count_detail` | View cycle count details |

---

## Sidebar Navigation Structure

The warehouse sidebar is organized into logical sections:

### 1. Dashboard
- **WH Dashboard** - Overview of warehouse operations

### 2. Setup & Configuration
- **Warehouses** - Manage fulfillment centers
- **Locations** - Manage warehouse pickup/dispatch locations
- **Seller-WH Links** - Link sellers to warehouses

### 3. Inventory Management
- **Inventory** - View and manage stock levels
- **Transactions** - View inventory movement history
- **Low Stock Alerts** - Monitor low stock items

### 4. Operations
- **Receive Stock** - Receive incoming inventory
- **Pick Lists** - Manage picking operations
- **Cycle Counts** - Perform inventory counts

---

## Typical Workflows

### Initial Setup Workflow

1. **Create Warehouses** (`/workforce/warehouse/warehouses/add/`)
   - Add fulfillment center details
   - Set GPS coordinates
   - Configure settings

2. **Add Locations** (`/workforce/warehouse/locations/add/`)
   - Create pickup/dispatch points
   - Assign zone numbers
   - Set operating hours

3. **Link Sellers** (`/workforce/warehouse/seller-warehouse-links/add/`)
   - Choose seller and warehouse
   - Set default location
   - Configure priority
   - Mark as default if needed

### Daily Operations Workflow

1. **Receive Stock** → `/workforce/warehouse/receive/`
2. **Check Inventory** → `/workforce/warehouse/inventory/`
3. **Create Pick Lists** → `/workforce/warehouse/pick-lists/create/`
4. **Monitor Alerts** → `/workforce/warehouse/alerts/`
5. **Review Transactions** → `/workforce/warehouse/transactions/`

### Order Fulfillment Workflow

1. **Order Created** by seller (shows "Fulfillment Store")
2. **Staff Views Order** in workforce dashboard
3. **System Recommends** warehouse location (auto-selection)
4. **Staff Assigns** delivery task with warehouse location
5. **Driver Picks Up** from specified location
6. **Inventory Updated** automatically

---

## Access Control

### Staff-Only Routes
All warehouse routes require staff authentication:
- `@login_required`
- `@user_passes_test(is_staff_user)`

### Seller Access
Sellers do NOT have access to warehouse management. They only see:
- "Fulfillment Store" option in order creation
- No warehouse details or locations

### Customer Access
Customers NEVER see warehouse information. Orders show only:
- "Fulfillment Store" as pickup location name
- No warehouse addresses or details

---

## HTMX Integration

All warehouse views support HTMX for seamless navigation:

```html
<a href="{% url 'warehouse:seller_warehouse_links' %}"
   hx-get="{% url 'warehouse:seller_warehouse_links' %}"
   hx-target="body"
   hx-push-url="true">
```

**Key attributes:**
- `hx-get`: AJAX content fetch
- `hx-target="body"`: Full page replacement
- `hx-push-url="true"`: Browser history management

---

## Template Structure

All warehouse templates extend: **`wf_dashboard_base.html`**

```django
{% extends 'wf_dashboard_base.html' %}
{% load static %}

{% block title %}Page Title{% endblock %}

{% block content %}
<div class="container-fluid py-4">
    <!-- Page content -->
</div>
{% endblock %}
```

---

## API Patterns (Future)

For API access (when implemented):

```
GET    /api/warehouses/                     # List warehouses
POST   /api/warehouses/                     # Create warehouse
GET    /api/warehouses/{id}/                # Warehouse detail
PATCH  /api/warehouses/{id}/                # Update warehouse
GET    /api/warehouses/{id}/locations/      # List locations
GET    /api/seller-warehouse-links/         # List links
POST   /api/seller-warehouse-links/         # Create link
GET    /api/orders/{id}/recommended-warehouse/  # Auto-select
```

---

## Common Issues

### Issue: 404 on warehouse URLs
**Solution:** Ensure you're using the full path: `/workforce/warehouse/...`

### Issue: Template not found
**Solution:** Verify template extends `wf_dashboard_base.html` (not `business_dashboard_base.html`)

### Issue: HTMX not loading content
**Solution:** Check that `hx-target="body"` is used (not `#main-content`)

### Issue: Warehouse not showing in seller order form
**Solution:**
1. Create warehouse via `/workforce/warehouse/warehouses/add/`
2. Create location via `/workforce/warehouse/locations/add/`
3. Link seller via `/workforce/warehouse/seller-warehouse-links/add/`

---

## Quick Reference

### Creating a Complete Warehouse Setup

```bash
# 1. Create Warehouse
/workforce/warehouse/warehouses/add/
→ Name: Central Fulfillment Center
→ GPS: 26.2285, 50.5860
→ Mark as active and default

# 2. Create Locations
/workforce/warehouse/locations/add/
→ Warehouse: Central Fulfillment Center
→ Name: North Gate
→ Zone: 44
→ GPS: 26.2361, 50.5922

# 3. Link Seller
/workforce/warehouse/seller-warehouse-links/add/
→ Business: [Select Seller]
→ Warehouse: Central Fulfillment Center
→ Default Location: North Gate
→ Priority: 100
→ Mark as default and active
```

---

## Related Documentation

- [WAREHOUSE_SYSTEM_GUIDE.md](WAREHOUSE_SYSTEM_GUIDE.md) - Technical guide
- [WAREHOUSE_SETUP_INSTRUCTIONS.md](WAREHOUSE_SETUP_INSTRUCTIONS.md) - Setup guide
- [WAREHOUSE_IMPLEMENTATION_COMPLETE.md](WAREHOUSE_IMPLEMENTATION_COMPLETE.md) - Implementation summary

---

Last Updated: 2026-01-17
