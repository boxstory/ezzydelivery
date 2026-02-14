# Task Status Modal - Bug Fixes Summary

**Date:** February 14, 2026
**Component:** Workforce Task Status Update Modal
**Status:** ✅ Fixed

---

## 🐛 Issues Identified & Fixed

### 1. **Driver Dropdown Not Showing Drivers** ✅ FIXED

**Problem:**
Driver dropdown showed "-- No Driver --" with no driver options to select.

**Root Cause:**
API endpoint `workforce/views.py:api_drivers_list` was using `d.id` to get driver ID, but the Driver model uses `driver_id` as the primary key (not the default `id` field). This caused an `AttributeError: 'Driver' object has no attribute 'id'`.

**Fix:**
Changed `d.id` to `d.pk` in the API response.

**File Changed:**
```python
# workforce/views.py:2447
driver_list.append({'id': d.pk, 'name': name})  # Changed from d.id to d.pk
```

---

### 2. **Current Task Status Not Pre-selected** ✅ FIXED

**Problem:**
When clicking the task status button, the dropdown didn't pre-select the current status.

**Root Cause:**
The `setStatusModalTask` function in `_tasks_view_scripts.html` was incomplete and only set task ID/number without populating the status dropdown or pre-selecting the current value.

**Fix:**
Completely rewrote the function to:
- Read `data-status-type` attribute to determine if it's task or DMS status
- Dynamically build dropdown options with the `selected` attribute
- Pre-select current status by building HTML with `selected` attribute

**File Changed:**
```javascript
// workforce/templates/workforce/parts/components/_tasks_view_scripts.html
// Lines 406-520 - Complete rewrite of setStatusModalTask function
```

---

### 3. **Customer Name Showing "—"** ✅ FIXED

**Problem:**
Customer name field showed "—" (empty) in the modal.

**Root Cause:**
DMS status button was missing the `data-customer-name` attribute.

**Fix:**
Added `data-customer-name="{{ dl.order.customer_name|default:'' }}"` to the DMS status button.

**File Changed:**
```html
<!-- workforce/templates/workforce/parts/components/_tasks_table_view.html:186 -->
data-customer-name="{{ dl.order.customer_name|default:'' }}"
```

---

### 4. **Identical Icons for Task vs DMS Status** ✅ FIXED

**Problem:**
Both task status and DMS status buttons showed the same pen icon, making them indistinguishable.

**Root Cause:**
Both buttons used `fa-pen-to-square` icon.

**Fix:**
- **Task Status button**: Changed to `fa-circle-dot` (circle with dot)
- **DMS Status button**: Changed to `fa-satellite-dish` (satellite icon)

**Files Changed:**
```html
<!-- Task Status Button -->
<i class="fa-solid fa-circle-dot"></i>

<!-- DMS Status Button -->
<i class="fa-solid fa-satellite-dish"></i>
```

---

### 5. **Modal Title Not Changing** ✅ FIXED

**Problem:**
Modal always showed "Update Task Status" regardless of which button was clicked.

**Root Cause:**
The modal title was static HTML and not being updated by JavaScript.

**Fix:**
Added JavaScript to dynamically update modal title and icon based on `statusType`:
- Task: "Update Task Status" with circle-dot icon
- DMS: "Update DMS Task Status" with satellite icon

**File Changed:**
```javascript
// workforce/templates/workforce/parts/components/_tasks_view_scripts.html:422-429
if (statusType === 'dms') {
    modalTitle.innerHTML = '<i class="fa-solid fa-satellite-dish me-2"></i>Update DMS Task Status';
} else {
    modalTitle.innerHTML = '<i class="fa-solid fa-circle-dot me-2"></i>Update Task Status';
}
```

---

### 6. **DMS Status Showing Number Instead of Label** ✅ FIXED

**Problem:**
Current status badge showed "2" instead of "2 - Successful" for DMS status.

**Root Cause:**
Badge display logic didn't format DMS status values.

**Fix:**
Created `getDmsStatusDisplay()` helper function to map DMS codes to labels:
- `0` → "Assigned"
- `1` → "Started"
- `2` → "Successful"
- etc.

**File Changed:**
```javascript
// workforce/templates/workforce/parts/components/_tasks_view_scripts.html:522-534
function getDmsStatusDisplay(dmsStatus) {
    const dmsLabels = {
        '0': 'Assigned', '1': 'Started', '2': 'Successful',
        '3': 'Failed', '4': 'InProgress/Arrived', '6': 'Unassigned',
        '7': 'Accepted/Acknowledged', '8': 'Decline',
        '9': 'Cancel', '10': 'Deleted'
    };
    return dmsLabels[dmsStatus] || dmsStatus || '—';
}
```

---

### 7. **Task Status Button Missing Status Type** ✅ FIXED

**Problem:**
Task status button didn't explicitly set `data-status-type="task"`, causing the JavaScript to potentially misidentify the status type.

**Root Cause:**
Attribute was missing from the button HTML.

**Fix:**
Added `data-status-type="task"` to the task status button.

**File Changed:**
```html
<!-- workforce/templates/workforce/parts/components/_tasks_table_view.html:164 -->
<button class="dl-table__edit-btn dl-table__edit-btn--status"
        data-status-type="task"
        data-current-status="{{ dl.dl_task_status }}"
        ...>
```

---

### 8. **Dropdown Not Pre-selecting (Final Fix)** ✅ FIXED

**Problem:**
Even with correct logic, dropdown wasn't pre-selecting the current status.

**Root Cause:**
Using `statusSelect.value = currentStatus` after `innerHTML` sometimes failed due to DOM update timing.

**Fix:**
Build options HTML with `selected` attribute directly in the string:
```javascript
const selected = (val === currentDms) ? ' selected' : '';
optionsHtml += `<option value="${val}"${selected}>${val} - ${label}</option>`;
```

Also changed modal template to start with empty dropdown:
```html
<select id="statusSelect">
    <option value="">Loading...</option>
</select>
```

**Files Changed:**
- `workforce/templates/workforce/parts/components/_tasks_view_scripts.html:449-493`
- `workforce/templates/workforce/parts/components/_tasks_status_modal.html:45-47`

---

## 📋 Complete List of Files Modified

| File | Lines | Changes |
|------|-------|---------|
| `workforce/views.py` | 2447 | Fixed driver API to use `d.pk` instead of `d.id` |
| `workforce/templates/workforce/parts/components/_tasks_view_scripts.html` | 406-540 | Complete rewrite of status modal functions |
| `workforce/templates/workforce/parts/components/_tasks_table_view.html` | 164, 169, 186, 188 | Added status type, changed icons, added customer name |
| `workforce/templates/workforce/parts/components/_tasks_status_modal.html` | 45-47 | Changed default dropdown to "Loading..." |

---

## 🎯 Final Behavior

### Task Status Button (🔵 Circle-dot)
When clicked:
1. Modal title: "Update Task Status"
2. Current status badge: "delivered" → formatted as "Delivered"
3. Dropdown shows: All task status options (for_review, pending, assigned, etc.)
4. Pre-selected: Current task status (e.g., "Delivered")
5. Driver dropdown: Populated with all approved drivers
6. Current driver: Pre-selected if assigned

### DMS Status Button (📡 Satellite)
When clicked:
1. Modal title: "Update DMS Task Status"
2. Current status badge: "2" → formatted as "2 - Successful"
3. Dropdown shows: All DMS status options (0-10 with labels)
4. Pre-selected: Current DMS status (e.g., "2 - Successful")
5. Driver dropdown: Populated with all approved drivers
6. Current driver: Pre-selected if assigned

---

## 🔍 Debugging Features Added

Console logging added to help diagnose issues:

```javascript
console.log('=== Modal Opening ===');
console.log('Type:', statusType, '| Task Status:', currentStatus, '| DMS:', currentDms);
console.log('Task Status - currentStatus:', currentStatus, 'Type:', typeof currentStatus);
console.log('Status select value after setting:', statusSelect.value, 'Options count:', statusSelect.options.length);
```

To debug, open browser console (F12 → Console) when opening the modal.

---

## ✅ Testing Checklist

- [x] Driver dropdown shows all approved drivers
- [x] Current driver is pre-selected
- [x] Customer name displays correctly
- [x] Task status button shows task options
- [x] Task status is pre-selected
- [x] DMS status button shows DMS options (0-10)
- [x] DMS status is pre-selected
- [x] Modal title changes based on button clicked
- [x] Icons are different for task vs DMS buttons
- [x] Current status badge shows formatted label (not just number)

---

## 🚀 Status

All issues have been identified and fixed. The status modal now works correctly for both task status and DMS status updates with proper pre-selection, labeling, and driver assignment.

**Last Updated:** February 14, 2026
**Tested:** ✅ Ready for production
