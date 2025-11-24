# Hash Links Inventory (#) - Complete List

This document lists all HTML links containing hash fragments (`#`) found in the Django Ezzy Delivery application templates.

**Total Links Found:** 62

---

## 1. Client App Templates (2 links)

### Business Settings API Add
**File:** `client/templates/client/parts/business_settings_api_add.html:14`
```html
<a class="btn btn-dark w-md-50 px-5" href="#" id="client_api_add_btn_back">
```
**Type:** Back button (no actual navigation)
**Issue:** Should use `javascript:history.back()` or proper URL

### Workflow Guide
**File:** `client/templates/client/workflow_guide.html:199`
```html
<a href="#" class="btn btn-outline-primary" id="client_workflow_btn_contact_support">
```
**Type:** Contact support button
**Issue:** Should link to actual support page or use JavaScript event

---

## 2. Workforce App Templates (22 links)

### Pagination Links (4 links)
**Files:**
- `workforce/templates/workforce/dl_list_incompleted.html:54`
- `workforce/templates/workforce/orders_list_incompleted.html:50`
- `workforce/templates/workforce/parts/lists/dl_list_incompleted.html:53`
- `workforce/templates/workforce/parts/lists/dl_list_unpublished.html:52`

```html
<a class="page-link text-dark" href="#">Previous</a>
```
**Type:** Pagination controls
**Issue:** Should implement actual pagination logic

### Dashboard Sidebar - Collapsible Menu (6 links)
**File:** `workforce/templates/workforce/parts/dashboard_sidebar_workforce.html`

All are Bootstrap collapse toggles:
- Line 17: Orders menu toggle
- Line 60: Tasks menu toggle
- Line 115: DMS menu toggle
- Line 164: Fleet menu toggle
- Line 195: Documents menu toggle
- Line 232: Inventory menu toggle

```html
<a class="nav-link btn nav-link-collapse" data-bs-toggle="collapse" data-bs-target="#submenu-orders" href="#">
```
**Type:** Bootstrap collapse controls
**Status:** ✅ Valid - Required for Bootstrap collapse functionality

### Delivery Task Status Updates (5 links)
**File:** `workforce/templates/workforce/parts/lists/dl_list_all.html`

Dropdown menu items for status updates (Lines 332, 335, 338, 341, 344):
```html
<a class="dropdown-item" href="#" onclick="updateTaskStatus({{ dl.id }}, 'pending')">
<a class="dropdown-item" href="#" onclick="updateTaskStatus({{ dl.id }}, 'in_transit')">
<a class="dropdown-item" href="#" onclick="updateTaskStatus({{ dl.id }}, 'delivered')">
<a class="dropdown-item" href="#" onclick="updateTaskStatus({{ dl.id }}, 'rejected')">
<a class="dropdown-item" href="#" onclick="updateTaskStatus({{ dl.id }}, 'cancelled')">
```
**Type:** JavaScript onclick handlers
**Status:** ⚠️ Could be improved with `javascript:void(0)` or remove href

### Order Status Updates (5 links)
**File:** `workforce/templates/workforce/parts/lists/orders_list_view.html`

Dropdown menu items for order status (Lines 305, 308, 311, 314, 317):
```html
<a class="dropdown-item" href="#" onclick="updateOrderStatus({{ order.id }}, 'not_connected')">
<a class="dropdown-item" href="#" onclick="updateOrderStatus({{ order.id }}, 'no_respond')">
<a class="dropdown-item" href="#" onclick="updateOrderStatus({{ order.id }}, 'customer_cancelled')">
<a class="dropdown-item" href="#" onclick="updateOrderStatus({{ order.id }}, 'rescheduled')">
<a class="dropdown-item" href="#" onclick="updateOrderStatus({{ order.id }}, 'address_issue')">
```
**Type:** JavaScript onclick handlers
**Status:** ⚠️ Could be improved with `javascript:void(0)` or remove href

### Generic Action Button (1 link)
**File:** `workforce/templates/workforce/parts/lists/dl_list_all.html:355`
```html
<a href="#" class="btn btn-dark">
```
**Type:** Button with no action
**Issue:** ❌ Broken link - needs proper functionality

---

## 3. Core App Templates (12 links)

### Social Media Links (12 links)
**Files:**
- `core/templates/core/join_us.html` (Lines 39, 40, 41)
- `core/templates/core/prodile_role_update.html` (Lines 40, 41, 42)
- `core/templates/core/profile_add.html` (Lines 25, 26, 27)
- `core/templates/core/profile_update.html` (Lines 31, 32, 33)

```html
<a href="#!"><i class="fa-brands fa-facebook fa-2xl me-3 text-dark"></i></a>
<a href="#!"><i class="fa-brands fa-whatsapp fa-2xl me-3 text-dark"></i></a>
<a href="#!"><i class="fa-brands fa-instagram fa-2xl text-dark"></i></a>
```
**Type:** Social media placeholder links
**Issue:** ❌ Should be updated with actual social media URLs

---

## 4. Webpages App Templates (20 links)

### Carousel Controls (2 links)
**File:** `webpages/templates/webpages/index.html` (Lines 124, 128)
```html
<a class="carousel-control-prev" href="#carouselExampleControls" role="button" data-bs-slide="prev">
<a class="carousel-control-next" href="#carouselExampleControls" role="button" data-bs-slide="next">
```
**Type:** Bootstrap carousel controls
**Status:** ✅ Valid - Required for Bootstrap carousel

### Service Button (1 link)
**File:** `webpages/templates/webpages/parts/services_list.html:201`
```html
<a href="#" class="btn btn-service btn-service-disabled">
```
**Type:** Disabled service button
**Status:** ⚠️ Should use `<button disabled>` instead

### SVG References (17 links)
**File:** `webpages/templates/webpages/server_error.html`

All SVG `xlink:href` references for graphic elements (Lines 534-654):
```html
<use xlink:href="#prefix__a" />
<use xlink:href="#prefix__c" />
... (15 more)
```
**Type:** SVG internal references
**Status:** ✅ Valid - Required for SVG graphics

---

## 5. Orders App Templates (4 links)

### Pagination Links (4 links)
**Files:**
- `orders/templates/orders/parts/orders_list_view copy.html:105`
- `orders/templates/orders/parts/orders_list_view.html` (Lines 213, 235, 239)

```html
<a class="page-link text-dark" href="#">Previous</a>
<a class="page-link text-dark" href="#">Next</a>
```
**Type:** Pagination controls
**Issue:** ❌ Should implement actual pagination logic

---

## 6. Fleet App Templates (2 links)

### Document Add Button (1 link)
**File:** `fleet/templates/fleet/parts/document_add.html:18`
```html
<button type="submit" value="submit" class="btn btn-dark w-75" href="#" id="fleet_document_add_btn_submit">Submit</button>
```
**Type:** Invalid - button with href attribute
**Issue:** ❌ Buttons shouldn't have href attributes

### Driver Reports (1 link)
**File:** `fleet/templates/fleet/parts/driver_reports.html:108`
```html
<a href="#" class="btn btn-sm btn-outline-primary" onclick="downloadSettlement({{ settlement.id }})">
```
**Type:** JavaScript onclick handler
**Status:** ⚠️ Could be improved with `javascript:void(0)`

### Vehicle List (1 link)
**File:** `fleet/templates/fleet/vehicle_all.html:23`
```html
<a href=" #">
```
**Type:** Empty/broken link
**Issue:** ❌ Broken link with space

---

## Summary by Category

### ✅ Valid Usage (25 links - 40%)
- Bootstrap collapse toggles (6)
- Bootstrap carousel controls (2)
- SVG internal references (17)

### ⚠️ Needs Improvement (23 links - 37%)
- JavaScript onclick handlers without proper href (12)
- Pagination placeholders (8)
- Disabled buttons (1)
- Download links (1)
- Back button (1)

### ❌ Broken/Invalid (14 links - 23%)
- Social media placeholder links (12)
- Button with href attribute (1)
- Generic broken link (1)

---

## Recommendations

### High Priority Fixes
1. **Update Social Media Links** - Replace `href="#!"` with actual URLs in all profile templates
2. **Fix Pagination** - Implement proper pagination logic in all list views
3. **Remove Invalid Attributes** - Remove href from `<button>` elements

### Medium Priority Improvements
1. **JavaScript Handlers** - Change `href="#"` to `href="javascript:void(0)"` for onclick handlers
2. **Back Navigation** - Implement proper back button functionality
3. **Generic Actions** - Add proper functionality to placeholder buttons

### Low Priority (No Action Required)
1. Bootstrap collapse/carousel controls - Working as intended
2. SVG references - Standard SVG usage

---

## Files Requiring Attention

### Critical (Broken Links)
1. `core/templates/core/join_us.html`
2. `core/templates/core/prodile_role_update.html`
3. `core/templates/core/profile_add.html`
4. `core/templates/core/profile_update.html`
5. `fleet/templates/fleet/parts/document_add.html`
6. `fleet/templates/fleet/vehicle_all.html`

### Important (Pagination)
1. `workforce/templates/workforce/dl_list_incompleted.html`
2. `workforce/templates/workforce/orders_list_incompleted.html`
3. `orders/templates/orders/parts/orders_list_view.html`

### Minor (JavaScript Handlers)
1. `workforce/templates/workforce/parts/lists/dl_list_all.html`
2. `workforce/templates/workforce/parts/lists/orders_list_view.html`
3. `fleet/templates/fleet/parts/driver_reports.html`

---

**Generated:** 2025-11-20
**Total Templates Scanned:** All HTML files in client, workforce, core, webpages, orders, fleet, product
