---
description: Fix CSS styling issues
---

# CSS Fix Mode

You are fixing CSS issues in the EzzyDelivery project. Reference `.claude/skills/frontend.md` for styling patterns.

## CRITICAL: Dual File Update Rule

**ALWAYS update BOTH files when fixing CSS:**

| App | Source CSS | Compiled CSS |
|-----|------------|--------------|
| workforce | `workforce/static/workforce/css/` | `staticroot/workforce/css/` |
| webpages | `webpages/static/webpages/css/` | `staticroot/webpages/css/` |
| warehouse | `warehouse/static/warehouse/css/` | `staticroot/warehouse/css/` |
| orders | `orders/static/orders/css/` | `staticroot/orders/css/` |

## Brand Variables (MUST USE)
```css
/* Colors */
--brand-primary: #f7c000        /* Ezzy Yellow */
--brand-navy: #001f3f
--brand-grey-100: #fafafa
--brand-grey-200: #f0f0f0
--brand-grey-300: #dcdcdc
--brand-grey-400: #b0b0b0
--brand-grey-500: #888
--brand-grey-600: #555
--brand-grey-700: #333
--brand-grey-800: #1f1f1f

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
```

## Common CSS Files
| File | Purpose |
|------|---------|
| `brand-kit.css` | Global brand styles |
| `wf_dashboard.css` | Dashboard layout |
| `wf_lists.css` | List views |
| `delivery-task-detail.css` | Task details |

## Debugging Steps
1. Check browser DevTools for applied styles
2. Look for specificity conflicts (use `!important` sparingly)
3. Check if correct CSS file is loaded in template
4. Verify both source and staticroot are in sync
5. Hard refresh browser (Ctrl+Shift+R)

## Common Issues

### Style not applying
```css
/* Check specificity - be more specific */
.dashboard .info-card .title { }  /* More specific */
.title { }  /* Less specific */
```

### Colors wrong
```css
/* BAD - hardcoded */
color: #f7c000;

/* GOOD - use variable */
color: var(--brand-primary);
```

### Mobile not responsive
```css
/* Mobile first approach */
.element { width: 100%; }

@media (min-width: 768px) {
    .element { width: 50%; }
}
```

### Staff Dashboard Font Size Rules (dashboard-modern.css)

**Desktop (base styles — outside media queries):**
- All `font-size` values > 1rem → cap at `1rem`
- Exception: icon-only elements (e.g. `.wf-empty-state i { font-size: 3rem }`) — leave untouched

**Mobile (`@media (max-width: 768px)`):**
- All `font-size` values of `0.875rem` → change to `0.75rem`
- All `font-size` values > 1rem → change to `0.875rem`
- `.wfd { font-size: 0.75rem }` — base font scale for the whole dashboard wrapper

**Cache busting:** Always bump `?v=` on `dashboard-modern.css` and `workforce.css` after edits, then run `collectstatic`.

Please describe:
1. What element/page has the issue
2. Expected vs actual appearance
3. Browser and any console errors
