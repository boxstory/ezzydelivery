# Frontend Development Skill - EzzyDelivery

Use this skill when working on frontend tasks: HTML templates, CSS styling, JavaScript, and UI components.

## Technology Stack

| Technology | Version | Purpose |
|------------|---------|---------|
| Bootstrap | 5.3.2 | CSS framework (custom build) |
| HTMX | 2.0.3 | AJAX/dynamic content |
| jQuery | 3.7.1 | DOM manipulation |
| Font Awesome | Free | Icons (`fa-solid fa-*`) |
| Select2 | 4.1.0 | Enhanced dropdowns |

## Brand Kit CSS Variables

Always use these variables instead of hardcoded values:

```css
/* Primary Colors */
--brand-primary: #f7c000        /* Ezzy Yellow */
--brand-primary-dark: #f4c20d
--brand-secondary: #fff7d6      /* Light yellow bg */
--brand-navy: #001f3f
--brand-navy-light: #003366

/* Grey Scale */
--brand-grey-100: #fafafa
--brand-grey-200: #f0f0f0
--brand-grey-300: #dcdcdc
--brand-grey-400: #b0b0b0
--brand-grey-500: #888
--brand-grey-600: #555
--brand-grey-700: #333
--brand-grey-800: #1f1f1f
--brand-white: #ffffff
--brand-black: #000000

/* Effects */
--brand-shadow-sm: 0 1px 3px rgba(0,0,0,0.08)
--brand-shadow-md: 0 4px 8px rgba(0,0,0,0.1)
--brand-shadow-lg: 0 10px 20px rgba(0,0,0,0.12)

/* Border Radius */
--brand-radius-sm: 8px
--brand-radius-md: 12px
--brand-radius-lg: 18px

/* Transitions */
--brand-transition: all 0.3s ease

/* Spacing */
--spacing-xs: 0.25rem
--spacing-sm: 0.5rem
--spacing-md: 1rem
--spacing-lg: 1.5rem
--spacing-xl: 2rem

/* Typography */
--brand-font-primary: "Inter", "Poppins", sans-serif
```

## File Locations

| Type | Location |
|------|----------|
| Brand Kit CSS | `webpages/static/webpages/css/brand-kit.css` |
| Brand Overrides | `webpages/static/webpages/css/brand-kit-overrides.css` |
| Base Template | `templates/base.html` |
| Dashboard Base | `templates/wf_dashboard_base.html` |
| Head Includes | `templates/includes/head.html` |
| Dashboard Scripts | `templates/includes/main_dashboard_scripts.html` |
| App CSS | `{app}/static/{app}/css/*.css` |
| StaticRoot | `staticroot/{app}/css/*.css` |

**IMPORTANT**: When editing CSS files, update BOTH:
1. `{app}/static/{app}/css/` (source)
2. `staticroot/{app}/css/` (compiled/served)

## Common CSS Classes

### Cards
```css
.info-card      /* White card with shadow */
.task-card      /* Task/order list cards */
.order-card     /* Order cards */
.stat-card      /* Dashboard statistics */
```

### Status Badges
```css
.status-badge           /* Base badge */
.status-pending         /* Yellow - #fff3cd */
.status-published       /* Blue - #cfe2ff */
.status-delivered       /* Green - #d1e7dd */
.status-failed          /* Red - #f8d7da */
.status-cancelled       /* Red - #f8d7da */
.status-in_transit      /* Yellow - #fff3cd */
.status-assigned        /* Light blue - #e7f3ff */
```

### Buttons
```css
.btn-primary            /* Yellow background */
.btn-outline-primary    /* Yellow border */
.btn-outline-secondary  /* Grey border */
.btn-dark               /* Dark background */
```

### Layout
```css
.filter-section     /* Filter form container */
.filter-toggle      /* Collapsible filter header */
.quick-actions      /* Action buttons row */
.action-section     /* Card footer actions */
```

## HTMX Patterns

### Form with HTMX
```html
<form hx-get="/url/"
      hx-target="#main-content"
      hx-select="#main-content"
      hx-swap="outerHTML"
      hx-push-url="true">
```

### Link with HTMX
```html
<a href="/url/"
   hx-get="/url/"
   hx-target="#main-content"
   hx-select="#main-content"
   hx-swap="outerHTML"
   hx-push-url="true">
```

### CSRF Token (auto-configured in dashboard)
HTMX automatically includes CSRF token via `main_dashboard_scripts.html`.

## JavaScript Patterns

### CSRF Token Helper
```javascript
function getCookie(name) {
    let cookieValue = null;
    if (document.cookie && document.cookie !== '') {
        const cookies = document.cookie.split(';');
        for (let i = 0; i < cookies.length; i++) {
            const cookie = cookies[i].trim();
            if (cookie.substring(0, name.length + 1) === (name + '=')) {
                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                break;
            }
        }
    }
    return cookieValue;
}
const csrftoken = getCookie('csrftoken');
```

### Fetch with CSRF
```javascript
fetch('/api/endpoint/', {
    method: 'POST',
    headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': csrftoken
    },
    body: JSON.stringify({ key: value })
})
.then(response => response.json())
.then(data => { /* handle response */ });
```

### Bootstrap Modal
```javascript
// Open modal
const modal = new bootstrap.Modal(document.getElementById('myModal'));
modal.show();

// Close modal
const modal = bootstrap.Modal.getInstance(document.getElementById('myModal'));
modal.hide();
```

## Template Blocks

### Base template blocks
```html
{% block extra_css %}{% endblock %}    <!-- CSS after base styles -->
{% block content %}{% endblock %}       <!-- Main content -->
{% block extra_js %}{% endblock %}      <!-- JS after base scripts -->
```

### Dashboard template blocks
```html
{% block extra_css %}{% endblock %}
{% block content %}{% endblock %}
{% block extra_js %}{% endblock %}
```

## Icons (Font Awesome)

```html
<i class="fa-solid fa-check"></i>       <!-- Checkmark -->
<i class="fa-solid fa-times"></i>       <!-- X/Close -->
<i class="fa-solid fa-search"></i>      <!-- Search -->
<i class="fa-solid fa-filter"></i>      <!-- Filter -->
<i class="fa-solid fa-sync"></i>        <!-- Refresh/Sync -->
<i class="fa-solid fa-truck"></i>       <!-- Delivery -->
<i class="fa-solid fa-user"></i>        <!-- User -->
<i class="fa-solid fa-store"></i>       <!-- Business/Store -->
<i class="fa-solid fa-calendar"></i>    <!-- Calendar -->
<i class="fa-solid fa-mobile"></i>      <!-- Mobile -->
<i class="fa-solid fa-cloud"></i>       <!-- Cloud/DMS -->
```

## Responsive Breakpoints

```css
/* Mobile first */
@media (min-width: 576px) { }   /* sm */
@media (min-width: 768px) { }   /* md */
@media (min-width: 992px) { }   /* lg */
@media (min-width: 1200px) { }  /* xl */
```

## Best Practices

1. **Use CSS Variables**: Always use `var(--brand-*)` instead of hardcoded colors
2. **Bootstrap First**: Use Bootstrap utilities before writing custom CSS
3. **HTMX for AJAX**: Prefer HTMX over jQuery AJAX for dynamic content
4. **Compact UI**: Keep cards and lists compact to show more content
5. **Duplicate CSS**: Remember to update both static and staticroot folders
6. **Mobile Responsive**: Test on mobile, use Bootstrap grid system
7. **Consistent Icons**: Use Font Awesome solid icons (`fa-solid`)
8. **Modal for Actions**: Use Bootstrap modals for status updates and forms
