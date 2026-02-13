---
description: Frontend development mode for UI/CSS/JS
---

# Frontend Development Mode

You are now in frontend development mode for the EzzyDelivery project. Reference the skill file at `.claude/skills/frontend.md` for detailed patterns.

## Technology Stack
- Bootstrap 5.3.2 (custom build)
- HTMX 2.0.3 for dynamic content
- jQuery 3.7.1 for DOM manipulation
- Font Awesome (solid icons)
- Select2 4.1.0 for dropdowns

## Brand Colors (USE THESE VARIABLES)
```css
--brand-primary: #f7c000      /* Ezzy Yellow */
--brand-navy: #001f3f
--brand-grey-100 to --brand-grey-800
--brand-radius-sm/md/lg: 8px/12px/18px
--brand-shadow-sm/md/lg
--brand-transition: all 0.3s ease
```

## File Locations
| Type | Location |
|------|----------|
| Brand Kit | `webpages/static/webpages/css/brand-kit.css` |
| Base Template | `templates/base.html` |
| Dashboard Base | `templates/wf_dashboard_base.html` |
| App CSS | `{app}/static/{app}/css/*.css` |
| StaticRoot | `staticroot/{app}/css/*.css` |

## CRITICAL: Dual CSS Update
**Always update BOTH when editing CSS:**
1. `{app}/static/{app}/css/` (source)
2. `staticroot/{app}/css/` (compiled/served)

## Common Classes
```css
/* Cards */
.info-card, .task-card, .order-card, .stat-card

/* Status Badges */
.status-badge, .status-pending, .status-delivered, .status-failed

/* Layout */
.filter-section, .filter-toggle, .quick-actions
```

## HTMX Patterns
```html
<a href="/url/"
   hx-get="/url/"
   hx-target="#main-content"
   hx-select="#main-content"
   hx-swap="outerHTML"
   hx-push-url="true">
```

## Template Blocks
```html
{% block extra_css %}{% endblock %}
{% block content %}{% endblock %}
{% block extra_js %}{% endblock %}
```

## Best Practices
1. **CSS Variables**: Always use `var(--brand-*)`, never hardcoded colors
2. **Bootstrap First**: Use utilities before custom CSS
3. **HTMX for AJAX**: Prefer over jQuery AJAX
4. **Dual CSS Update**: Both static and staticroot
5. **Mobile First**: Test responsive, use Bootstrap grid
6. **Font Awesome**: Use `fa-solid fa-*` icons

Please describe your frontend task.
