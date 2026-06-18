# Delivery Speed Tiers — Same Day & Standard (48hr)

## Overview

EzzyDelivery supports two delivery speed tiers: **Same Day** and **Standard (48hr)**. The tier is captured at order creation, flows through to the delivery task, drives warehouse pick list prioritisation, and is detected automatically from Shopify/WooCommerce shipping method names.

## Implementation Date
June 18, 2026

---

## 1. Data Model

### 1.1 Order.delivery_speed
**File**: `orders/models.py`
**Migration**: `orders/migrations/0049_add_delivery_speed.py`

```python
DELIVERY_SPEED_CHOICES = [
    ('standard', 'Standard (48hr)'),
    ('same_day', 'Same Day'),
]

delivery_speed = models.CharField(
    max_length=20,
    choices=DELIVERY_SPEED_CHOICES,
    default='standard',
    db_index=True,
)
```

All existing orders default to `standard`. The field is indexed for fast filtering.

### 1.2 DeliveryTask.dl_speed
**File**: `delivery/models.py` — pre-existing field, mapped from `delivery_speed`.

| `Order.delivery_speed` | `DeliveryTask.dl_speed` |
|---|---|
| `same_day` | `Same Day` |
| `standard` | `Normal` |

---

## 2. Signal Mapping

**File**: `orders/signals.py` — `_create_delivery_task_from_order()`

When an order is published and a delivery task is auto-created, `dl_speed` is set directly from `delivery_speed`:

```python
dl_speed = 'Same Day' if order.delivery_speed == 'same_day' else 'Normal'
```

---

## 3. Manual Order Creation (Workforce)

**Form**: `/workforce/orders/add/`
**File**: `workforce/templates/workforce/orders_add.html`

A **Delivery Speed** dropdown is shown next to Order Type:
- `Standard (48hr)` — default
- `Same Day`

**View**: `workforce/views.py` line ~1435 — saves `delivery_speed` from POST data.

---

## 4. Shopify / WooCommerce Auto-Detection

**File**: `ezzy_api/views.py`

### 4.1 Detection helper

```python
_SAME_DAY_KEYWORDS = (
    'same day', 'same-day', 'sameday', 'express', 'urgent',
    'immediate', 'on demand', '1hr', '1 hr', '2hr', '2 hr'
)

def _detect_delivery_speed(shipping_title):
    title_lower = (shipping_title or '').lower()
    return 'same_day' if any(kw in title_lower for kw in _SAME_DAY_KEYWORDS) else 'standard'
```

### 4.2 Shopify (`_create_order_from_shopify`)

Reads `shopify_order.shipping_lines[0].title` and passes it to `_detect_delivery_speed()`.

**Example Shopify shipping rates → result:**

| Shipping rate name in Shopify | delivery_speed |
|---|---|
| Same Day Delivery | `same_day` |
| Express Shipping | `same_day` |
| Urgent Delivery | `same_day` |
| Standard Delivery | `standard` |
| Free Shipping | `standard` |
| *(no shipping line)* | `standard` |

### 4.3 WooCommerce (`_create_order_from_woocommerce`)

Reads `order_data['shipping_lines'][0]['method_title']` and passes it to `_detect_delivery_speed()`.

### 4.4 Adding new keywords

To recognise additional shipping method names as same-day, add them to `_SAME_DAY_KEYWORDS` in `ezzy_api/views.py`:

```python
_SAME_DAY_KEYWORDS = (
    'same day', 'same-day', 'sameday', 'express', 'urgent',
    'immediate', 'on demand', '1hr', '1 hr', '2hr', '2 hr',
    'flash',       # ← add new keywords here
    '2-hour',
)
```

---

## 5. Warehouse Pick List Prioritisation

**File**: `warehouse/views.py` — `pick_list_list()`

Pick lists containing at least one same-day order are annotated with `has_urgent=True` via a subquery and sorted to the top:

```python
same_day_subq = Exists(
    PickListItem.objects.filter(
        pick_list=OuterRef('pk'),
        order__delivery_speed='same_day'
    )
)
pick_lists = pick_lists.annotate(has_urgent=same_day_subq).order_by('-has_urgent', '-created_at')
```

---

## 6. UI Highlighting

### 6.1 Pick List — `/workforce/warehouse/pick-lists/`

**CSS**: `warehouse/static/warehouse/css/warehouse.css`

- **Desktop table**: urgent rows get a warm orange background (`.pkl-row--urgent`). The pick number cell shows an orange `⚡ Same Day` badge (`.pkl-urgent-badge`).
- **Mobile card**: full-width orange banner at the top of the card (`.pkl-mob__urgent-banner`).

### 6.2 Incomplete Delivery Tasks — `/workforce/tasks/dl_list_incompleted/`

**CSS**: `workforce/static/workforce/css/workforce.css`

- Rows with `delivery_speed == 'same_day'` get class `.dli__row--urgent` (warm orange background).
- The task code cell shows an orange `⚡ Same Day` badge (`.dli__speed-badge--urgent`).

---

## 7. Warehouse Stock Reservation Priority

**File**: `warehouse/signals.py` — `reserve_stock_for_order()`

When stock is reserved for an order, warehouses are selected in `SellerWarehouseLink` priority order (highest `priority` value first, default warehouse first). Within each warehouse, stock levels are ordered by quantity descending. This ensures same-day orders reserve from the right warehouse even when a seller spans multiple locations.

---

## 8. Hub Warehouse Auto-Assignment (Fulfillment Orders)

**File**: `orders/signals.py` — `_create_delivery_task_from_order()`

For fulfillment orders (pickup is a fulfilment centre), `get_recommended_warehouse_location()` runs on publish and stamps the best `WarehouseLocation` onto `order.hub_warehouse` using zone → GPS → priority strategies.

---

## 9. Files Changed Summary

| File | Change |
|---|---|
| `orders/models.py` | Added `DELIVERY_SPEED_CHOICES` + `delivery_speed` field |
| `orders/migrations/0049_add_delivery_speed.py` | Migration |
| `orders/signals.py` | `dl_speed` mapped from `delivery_speed`; hub_warehouse auto-assign |
| `workforce/views.py` | Saves `delivery_speed` from order add form |
| `workforce/templates/workforce/orders_add.html` | Delivery Speed dropdown |
| `workforce/templates/workforce/dl_list_incompleted.html` | Urgent row + badge |
| `workforce/static/workforce/css/workforce.css` | `.dli__row--urgent`, `.dli__speed-badge` |
| `warehouse/views.py` | `has_urgent` annotation + sort |
| `warehouse/templates/warehouse/pick_list_list.html` | Urgent banner + badge |
| `warehouse/static/warehouse/css/warehouse.css` | `.pkl-row--urgent`, `.pkl-urgent-badge`, `.pkl-mob__urgent-banner` |
| `warehouse/utils.py` | Fixed `customer_latitude` → `latitude` field name bug |
| `warehouse/signals.py` | Stock reservation ordered by link priority |
| `ezzy_api/views.py` | `_detect_delivery_speed()` + Shopify + WooCommerce wiring |
