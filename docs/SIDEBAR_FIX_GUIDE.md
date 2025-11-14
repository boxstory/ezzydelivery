# Sidebar Active State Fix Guide

## Problem Description
The sidebar nav items are not properly highlighting when active, and submenus are not automatically expanding when a child item is active.

## Root Cause
1. The `active` class is only applied to the parent `<li>` element
2. The CSS expects both `.nav-item.active` AND child links to have `.active` class
3. Submenus are not auto-expanding when parent has `active` class

## Solution

### Step 1: Use Common Sidebar CSS
All sidebars should link to the common CSS file:

```html
{% load static %}
<link href="{% static 'css/sidebar-common.css' %}" rel="stylesheet" type="text/css" />
```

### Step 2: Fix Active State Logic

#### For Parent Items with Submenus:
```html
<!-- WRONG -->
<li class="nav-item {% if condition %}active{% endif %}">
    <div class="nav-link btn">Menu Item</div>
    <div class="collapse">
        <ul>
            <li><a class="nav-link btn" href="...">Sub Item</a></li>
        </ul>
    </div>
</li>

<!-- CORRECT -->
<li class="nav-item {% if condition %}active{% endif %}">
    <div class="nav-link btn {% if condition %}active{% endif %}">Menu Item</div>
    <div class="collapse">
        <ul>
            <li class="nav-item {% if specific_condition %}active{% endif %}">
                <a class="nav-link btn {% if specific_condition %}active{% endif %}" href="...">Sub Item</a>
            </li>
        </ul>
    </div>
</li>
```

#### For Single Nav Items (No Submenu):
```html
<!-- WRONG -->
<li class="nav-item">
    <a class="nav-link btn" href="...">Menu Item</a>
</li>

<!-- CORRECT -->
<li class="nav-item {% if request.resolver_match.url_name == 'view_name' %}active{% endif %}">
    <a class="nav-link btn {% if request.resolver_match.url_name == 'view_name' %}active{% endif %}" href="...">
        Menu Item
    </a>
</li>
```

### Step 3: Remove Inline Styles
Remove all `<style>` tags from sidebar templates. The `sidebar-common.css` file now handles all styling.

## Files That Need Fixing

1. **Client Dashboard Sidebar**
   - File: `templates/includes/dashboard_sidebar.html`
   - Status: ✅ Fixed

2. **Fleet Dashboard Sidebar**
   - File: `fleet/templates/fleet/parts/fleet_dashboard_sidebar.html`
   - Status: ✅ Fixed

3. **Workforce Dashboard Sidebar**
   - File: `workforce/templates/workforce/parts/wf_dashboard_sidebar.html`
   - Status: ✅ Already fixed

4. **Profile Sidebar**
   - File: `core/templates/core/parts/profile_sidebar.html`
   - Status: ⏳ N/A (Not a navigation sidebar - it's a profile card component)

5. **Mobile Sidebar**
   - File: `templates/includes/dashboard_sidebar_mob.html`
   - Status: ✅ Fixed

## Example: Complete Fixed Sidebar Section

```html
{% load static %}
<link href="{% static 'css/sidebar-common.css' %}" rel="stylesheet" type="text/css" />

<div class="dashboard-sidebar">
    <!-- Header -->
    <div class="sidebar-header">
        <a class="nav-link btn" href="{% url 'dashboard' %}">
            <i class="fa-solid fa-gauge me-2"></i>
            Dashboard
        </a>
    </div>

    <hr class="sidebar-divider" />

    <ul class="navbar-nav">
        <!-- Section with submenu -->
        <li class="nav-item {% if request.resolver_match.url_name == 'orders_all' or request.resolver_match.url_name == 'orders_add' or request.resolver_match.url_name == 'orders_pending' %}active{% endif %}">
            <div class="nav-link btn {% if request.resolver_match.url_name == 'orders_all' or request.resolver_match.url_name == 'orders_add' or request.resolver_match.url_name == 'orders_pending' %}active{% endif %}"
                 data-bs-toggle="collapse"
                 data-bs-target="#submenu-orders">
                <i class="fa-solid fa-basket-shopping me-2"></i>
                <span>Orders</span>
                <i class="fa-solid fa-caret-down ms-auto"></i>
            </div>
            <div class="multi-level collapse" id="submenu-orders">
                <ul class="nav">
                    <li class="nav-item {% if request.resolver_match.url_name == 'orders_all' %}active{% endif %}">
                        <a class="nav-link btn {% if request.resolver_match.url_name == 'orders_all' %}active{% endif %}" href="{% url 'orders:orders_all' %}">
                            <i class="fa-solid fa-list me-2"></i>
                            All Orders
                        </a>
                    </li>
                    <li class="nav-item {% if request.resolver_match.url_name == 'orders_add' %}active{% endif %}">
                        <a class="nav-link btn {% if request.resolver_match.url_name == 'orders_add' %}active{% endif %}" href="{% url 'orders:orders_add' %}">
                            <i class="fa-solid fa-plus me-2"></i>
                            Add Order
                        </a>
                    </li>
                    <li class="nav-item {% if request.resolver_match.url_name == 'orders_pending' %}active{% endif %}">
                        <a class="nav-link btn {% if request.resolver_match.url_name == 'orders_pending' %}active{% endif %}" href="{% url 'orders:orders_pending' %}">
                            <i class="fa-solid fa-clock me-2"></i>
                            Pending
                        </a>
                    </li>
                </ul>
            </div>
        </li>

        <hr class="sidebar-divider" />

        <!-- Single nav item -->
        <li class="nav-item {% if request.resolver_match.url_name == 'inventory' %}active{% endif %}">
            <a class="nav-link btn {% if request.resolver_match.url_name == 'inventory' %}active{% endif %}" href="{% url 'inventory' %}">
                <i class="fa-solid fa-boxes me-2"></i>
                Inventory
            </a>
        </li>
    </ul>
</div>
```

## CSS Features (Already in sidebar-common.css)

The common CSS file provides:

1. **Auto-expand active submenus**
   ```css
   .dashboard-sidebar .nav-item.active .multi-level,
   .dashboard-sidebar .nav-item.active .submenu,
   .dashboard-sidebar .nav-item.active .collapse {
       display: block !important;
   }
   ```

2. **Rotate caret for active parents**
   ```css
   .dashboard-sidebar .nav-item.active .fa-caret-down,
   .dashboard-sidebar .nav-item.active .fa-chevron-down {
       transform: rotate(180deg);
   }
   ```

3. **Highlight active items**
   ```css
   .dashboard-sidebar .nav-link.btn.active,
   .dashboard-sidebar .nav-item.active > .nav-link.btn,
   .dashboard-sidebar .nav-item.active > div.nav-link.btn {
       background: var(--brand-primary);
       border-color: var(--brand-primary-dark);
       color: var(--brand-grey-800);
       font-weight: 700;
   }
   ```

## Testing Checklist

After fixing a sidebar, verify:

- [ ] Parent menu item highlights when any child is active
- [ ] Submenu auto-expands when parent/child is active
- [ ] Caret rotates when submenu is active
- [ ] Individual submenu items highlight when active
- [ ] Single nav items (no submenu) highlight correctly
- [ ] Hover states work properly
- [ ] No inline styles in template
- [ ] Uses `sidebar-common.css`
- [ ] Responsive design works on mobile/tablet

## Quick Fix Script

For each sidebar file, follow these steps:

1. Add CSS link at the top:
   ```html
   {% load static %}
   <link href="{% static 'css/sidebar-common.css' %}" rel="stylesheet" type="text/css" />
   ```

2. Remove all `<style>` tags

3. For each nav item with submenu:
   - Add `active` class to parent `<li>`
   - Add `active` class to parent `<div class="nav-link btn">`
   - Add individual `active` classes to each child `<li>` and `<a>`

4. For each single nav item:
   - Add `active` class to `<li>`
   - Add `active` class to `<a class="nav-link btn">`

5. Test all navigation states

## Common Mistakes to Avoid

### Mistake 1: Only Parent Has Active Class
```html
<!-- WRONG -->
<li class="nav-item active">
    <div class="nav-link btn">Menu</div>  <!-- Missing active class -->
</li>
```

### Mistake 2: Missing Child Active States
```html
<!-- WRONG -->
<li class="nav-item active">
    <div class="nav-link btn active">Menu</div>
    <div class="collapse">
        <ul>
            <li><a class="nav-link btn" href="...">Sub</a></li>  <!-- Missing active class on specific item -->
        </ul>
    </div>
</li>
```

### Mistake 3: Keeping Inline Styles
```html
<!-- WRONG -->
{% block extra_css %}
<style>
    .dashboard-sidebar { ... }  <!-- Should use external CSS -->
</style>
{% endblock %}
```

---

**Priority**: High
**Effort**: ~30 minutes per sidebar
**Impact**: Better UX, consistent navigation highlighting
**Created**: November 2025
