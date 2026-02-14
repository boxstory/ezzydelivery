# CSS Utilities - Quick Reference Guide
**EzzyDelivery Global Utilities**
**Location:** `static/global/css/utilities.css`

---

## 🎨 **Animations**

### **Available Animations:**
```html
<div class="animate-spin">Loading...</div>
<div class="animate-pulse">Heartbeat effect</div>
<div class="animate-fadeIn">Fade in</div>
<div class="animate-fadeInUp">Slide up + fade</div>
<div class="animate-slideDown">Slide down</div>
<div class="animate-bounce">Bounce</div>
<div class="animate-shake">Shake</div>
```

### **Animation Delays:**
```html
<div class="animate-fadeInUp animate-delay-100">Item 1</div>
<div class="animate-fadeInUp animate-delay-200">Item 2</div>
<div class="animate-fadeInUp animate-delay-300">Item 3</div>
<!-- Available: 100, 200, 300, 400, 500 -->
```

---

## 🎯 **Hover Effects**

### **Lift Effects:**
```html
<div class="hover-lift-sm">Subtle lift</div>
<div class="hover-lift-md">Standard lift</div>
<div class="hover-lift-lg">Large lift</div>
```

### **Shadow Effects:**
```html
<div class="hover-shadow-sm">Small shadow on hover</div>
<div class="hover-shadow-md">Medium shadow on hover</div>
<div class="hover-shadow-lg">Large shadow on hover</div>
```

### **Combined Lift + Shadow:**
```html
<div class="card hover-lift-shadow-md">
  <!-- Most common: lift + shadow together -->
</div>
```

### **Scale Effects:**
```html
<div class="hover-scale-sm">Scale 1.02</div>
<div class="hover-scale-md">Scale 1.05</div>
<div class="hover-scale-lg">Scale 1.1</div>
```

### **Other Hover Effects:**
```html
<div class="hover-opacity-75">Opacity 75% on hover</div>
<div class="hover-brightness-110">Brighten 110%</div>
<div class="hover-rotate-5">Rotate 5deg</div>
```

---

## 🏷️ **Status Badges**

### **Basic Usage:**
```html
<span class="status-badge status-badge--pending">Pending</span>
<span class="status-badge status-badge--active">Active</span>
<span class="status-badge status-badge--completed">Completed</span>
<span class="status-badge status-badge--failed">Failed</span>
<span class="status-badge status-badge--verified">Verified</span>
```

### **With Icons:**
```html
<span class="status-badge status-badge--pending">
  <i class="fa-solid fa-clock"></i> Pending
</span>

<span class="status-badge status-badge--verified">
  <i class="fa-solid fa-check"></i> Verified
</span>
```

### **All Status Variants:**
- `status-badge--pending` (yellow/amber)
- `status-badge--active` (green)
- `status-badge--completed` (blue)
- `status-badge--failed` (red)
- `status-badge--verified` (green)
- `status-badge--processing` (purple)
- `status-badge--rejected` (red)
- `status-badge--assigned` (purple)
- `status-badge--published` (green)
- `status-badge--under-review` (yellow)
- `status-badge--cancelled` (grey)

### **Status Dots:**
```html
<span class="status-dot status-dot--active"></span> Active
<span class="status-dot status-dot--pending"></span> Pending
```

### **Backward Compatible (Legacy):**
```html
<!-- Old format still works -->
<span class="badge-pending">Pending</span>
<span class="badge-verified">Verified</span>
```

---

## ✍️ **Text Utilities**

```html
<div class="text-xs">Extra small text (0.65rem)</div>
<div class="text-sm">Small text (0.875rem)</div>

<div class="text-truncate-2">
  Truncate to 2 lines with ellipsis...
</div>

<div class="text-truncate-3">
  Truncate to 3 lines with ellipsis...
</div>
```

---

## 🖱️ **Cursor Utilities**

```html
<button class="cursor-pointer">Clickable</button>
<div class="cursor-not-allowed">Disabled</div>
<div class="cursor-grab">Draggable</div>
<div class="cursor-grabbing">Dragging</div>
```

---

## ⚡ **Transition Utilities**

```html
<div class="transition-all">Transition all properties</div>
<div class="transition-fast">Fast transition (0.15s)</div>
<div class="transition-slow">Slow transition (0.3s)</div>
<div class="transition-colors">Transition colors only</div>
```

---

## 🎨 **Border Utilities**

```html
<div class="border-brand">Brand primary border</div>
<div class="border-top-brand">Top border only</div>
<div class="border-bottom-brand">Bottom border only</div>
```

---

## 🌟 **Shadow Utilities**

```html
<div class="shadow-brand-sm">Small brand shadow</div>
<div class="shadow-brand-md">Medium brand shadow</div>
<div class="shadow-brand-lg">Large brand shadow</div>
```

---

## 📜 **Scrollbar Utilities**

```html
<div class="scrollbar-thin" style="overflow: auto; height: 300px;">
  <!-- Custom thin scrollbar -->
</div>
```

---

## 📭 **Empty State**

```html
<div class="empty-state">
  <i class="fa-solid fa-inbox empty-state-icon"></i>
  <div class="empty-state-text">No items found</div>
</div>
```

---

## ⏳ **Loading Spinners**

```html
<div class="loading-spinner"></div>
<div class="loading-spinner loading-spinner-lg"></div>

<!-- Or with animation class -->
<i class="fa-solid fa-spinner animate-spin"></i>
```

---

## 🃏 **Card Utilities**

```html
<div class="card card-hover">
  <!-- Card with hover effect -->
</div>
```

---

## 📐 **Position Utilities**

```html
<div class="sticky-top-60">Sticky 60px from top</div>
<div class="sticky-bottom">Sticky to bottom</div>
```

---

## 🔢 **Z-Index Utilities**

```html
<div class="z-1">Z-index: 1</div>
<div class="z-10">Z-index: 10</div>
<div class="z-50">Z-index: 50</div>
<div class="z-100">Z-index: 100</div>
<div class="z-1000">Z-index: 1000</div>
```

---

## 🎨 **Status Color Variables**

Use in custom CSS:

```css
.custom-element {
  background: var(--status-pending-bg);
  color: var(--status-pending-text);
  border: 1px solid var(--status-pending-border);
}

/* Available variables:
   --status-pending-*
   --status-active-*
   --status-completed-*
   --status-failed-*
   --status-verified-*
   --status-processing-*
   --status-rejected-*
   --status-assigned-*
   --status-published-*
   --status-under-review-*
   --status-cancelled-*
*/
```

---

## 📋 **Common Patterns**

### **Card with Hover Effect:**
```html
<div class="card hover-lift-shadow-md transition-all">
  <div class="card-body">
    Content
  </div>
</div>
```

### **Status Badge in Table:**
```html
<td>
  <span class="status-badge status-badge--completed">
    <i class="fa-solid fa-check"></i> Delivered
  </span>
</td>
```

### **Loading Button:**
```html
<button class="btn btn-primary" disabled>
  <i class="fa-solid fa-spinner animate-spin"></i>
  Loading...
</button>
```

### **Animated Card Grid:**
```html
<div class="row">
  <div class="col-md-4">
    <div class="card hover-lift-shadow-md animate-fadeInUp animate-delay-100">
      Card 1
    </div>
  </div>
  <div class="col-md-4">
    <div class="card hover-lift-shadow-md animate-fadeInUp animate-delay-200">
      Card 2
    </div>
  </div>
  <div class="col-md-4">
    <div class="card hover-lift-shadow-md animate-fadeInUp animate-delay-300">
      Card 3
    </div>
  </div>
</div>
```

### **Empty State with Animation:**
```html
<div class="empty-state animate-fadeIn">
  <i class="fa-solid fa-box-open empty-state-icon"></i>
  <div class="empty-state-text">No orders found</div>
</div>
```

---

## 🚀 **How to Use**

### **1. Include in Your Template:**
```html
{% load static %}
<link rel="stylesheet" href="{% static 'global/css/utilities.css' %}">
```

### **2. Or Add to Base Template:**
Most base templates already include this! Check:
- `templates/includes/head-dashboard.html`
- `webpages/templates/webpages/base.html`
- `business/templates/business/business_dashboard_base.html`
- `workforce/templates/workforce/wf_base_dashboard.html`

### **3. Start Using Classes:**
No additional imports needed - just use the utility classes in your HTML!

---

## 💡 **Tips**

1. **Combine Utilities:** Stack multiple classes for complex effects
   ```html
   <div class="card hover-lift-shadow-md animate-fadeInUp transition-all">
   ```

2. **Use Status Colors:** Consistent colors across all apps
   ```html
   <span class="status-badge status-badge--pending">
   ```

3. **Responsive Design:** Most utilities work on mobile automatically

4. **Browser Support:** All modern browsers (Chrome, Firefox, Safari, Edge)

---

## 📚 **Full Documentation**

- **Complete Analysis:** `docs/css_optimization_report.md`
- **Implementation Guide:** `docs/CSS_OPTIMIZATION_CHANGES.md`
- **Executive Summary:** `docs/CSS_OPTIMIZATION_SUMMARY.md`

---

**Last Updated:** 2026-02-13
**Version:** 1.0
**Maintainer:** Development Team
