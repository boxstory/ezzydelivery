# CSS-Fix Skill — Comprehensive CSS Compliance & Refactoring

**Purpose:** Fix CSS rule violations per CLAUDE.md, ensure all CSS is loaded from external files, and refactor inline/embedded styles into proper BEM CSS architecture.

**When to use:** Auditing CSS compliance, fixing style tag violations, moving inline styles to CSS files, ensuring Brand Kit variable usage.

**Prerequisites:** Must use `frontend-designer.md` skill for BEM naming and patterns.

---

## Bootstrap-First BEM Rule (CRITICAL Pattern)

**RULE:** Use BOTH Bootstrap AND BEM classes on the same element. BEM overlaps/extends Bootstrap with custom styling.

### Pattern: Bootstrap Base + BEM Custom

```html
<!-- ✅ CORRECT: Bootstrap first (base), then BEM (custom) -->
<button class="btn btn-primary combo__btn-submit">Submit</button>
<div class="card combo__order-card">Content</div>
<input class="form-control combo__input-field" type="text">
<span class="badge combo__badge-status">Pending</span>
```

**Class Order Convention:**
1. Bootstrap classes first (layout, components, base structure)
2. BEM class second (custom brand styling, overrides)

```css
/* CSS: BEM overlaps Bootstrap to add custom styling */

/* Bootstrap .btn handles: padding, display, borders, cursor, font-size */
/* BEM .combo__btn-submit ADDS: colors, shadows, hover effects */
.combo__btn-submit {
    background: var(--brand-primary) !important;
    border-color: var(--brand-primary) !important;
    box-shadow: 0 2px 8px rgba(0,0,0,0.1);
    transition: all 0.3s ease;
}

.combo__btn-submit:hover {
    background: var(--brand-primary-dark) !important;
    transform: translateY(-2px);
    box-shadow: 0 4px 12px rgba(0,0,0,0.15);
}

/* Bootstrap .card handles: padding, borders, background, border-radius */
/* BEM .combo__order-card ADDS: custom shadows, left border accent */
.combo__order-card {
    border-left: 4px solid var(--brand-primary);
    box-shadow: 0 4px 12px rgba(0,0,0,0.08);
}

/* Bootstrap .form-control handles: padding, borders, font, focus state base */
/* BEM .combo__input-field ADDS: brand focus color, custom box-shadow */
.combo__input-field:focus {
    border-color: var(--brand-primary) !important;
    box-shadow: 0 0 0 3px rgba(247, 192, 0, 0.1) !important;
}
```

### What NOT to Do (Bootstrap Duplication)

```css
/* ❌ WRONG — Duplicates Bootstrap .btn base styles */
.combo__btn {
    display: inline-block;      /* Bootstrap provides this */
    padding: 0.375rem 0.75rem;  /* Bootstrap provides this */
    border: 1px solid transparent;  /* Bootstrap provides this */
    border-radius: 0.375rem;    /* Bootstrap provides this */
    cursor: pointer;            /* Bootstrap provides this */
    font-size: 1rem;           /* Bootstrap provides this */
    /* Plus custom styling below */
    background: var(--brand-primary);
}

/* ❌ WRONG — Duplicates Bootstrap flex utilities in CSS */
.component__flex-row {
    display: flex;              /* Use .d-flex class instead */
    flex-direction: row;        /* Use .flex-row class instead */
    gap: 1rem;                  /* Use .gap-3 class instead */
    align-items: center;        /* Use .align-items-center class instead */
}
```

### ✅ Correct Approach (Both Classes)

```html
<!-- Use Bootstrap utilities for layout + structure -->
<!-- Use BEM class for custom styling -->
<div class="d-flex flex-row gap-3 align-items-center p-4 component__hero">
    <icon />
    <text />
</div>
```

```css
/* CSS: BEM ONLY adds custom visual styling */
.component__hero {
    /* Bootstrap handles: d-flex, flex-row, gap-3, align-items-center, p-4 */
    
    /* BEM ADDS: custom visuals Bootstrap doesn't provide */
    background: var(--brand-white);
    border: 1px solid var(--brand-grey-200);
    border-radius: var(--brand-radius-lg);
    box-shadow: 0 4px 12px rgba(0,0,0,0.08);
    transition: all 0.3s ease;
}

.component__hero:hover {
    box-shadow: 0 6px 16px rgba(0,0,0,0.12);
    transform: translateY(-2px);
}
```

### When to Use `!important` in BEM CSS

Use `!important` **ONLY** when overriding Bootstrap defaults:

```css
/* ✅ GOOD: Override Bootstrap color with brand color */
.combo__btn-submit {
    background: var(--brand-primary) !important;
    border-color: var(--brand-primary) !important;
}

/* ✅ GOOD: Override Bootstrap focus shadow with brand shadow */
.combo__input-field:focus {
    box-shadow: 0 0 0 3px rgba(247, 192, 0, 0.1) !important;
}

/* ❌ BAD: Don't use !important for non-overrides */
.combo__hero {
    padding: 1rem;  /* No !important needed */
    transition: all 0.3s;  /* No !important needed */
}
```

### Bootstrap Components (Always Use as Base)

| Component | Bootstrap Class | BEM Adds | Example |
|-----------|----------------|----------|---------|
| Button | `.btn` `.btn-primary` | Custom hover, shadows | `class="btn btn-primary combo__btn-submit"` |
| Card | `.card` | Custom borders, shadows | `class="card combo__order-card"` |
| Form Control | `.form-control` | Brand focus color | `class="form-control combo__input-field"` |
| Badge | `.badge` | Custom sizes, colors | `class="badge combo__badge-status"` |
| Alert | `.alert` `.alert-info` | Brand borders, icons | `class="alert alert-info combo__alert-message"` |
| Modal | `.modal` | Custom animations | `class="modal combo__modal-dialog"` |
| Table | `.table` | Row colors, hover | `class="table combo__table-data"` |

### Layout Always Uses Bootstrap Utilities

**NEVER write custom CSS for layout:**

```html
<!-- ✅ Correct: Use Bootstrap utilities, not custom CSS -->
<div class="d-flex flex-column gap-3 p-4 mb-3 align-items-center">
    <!-- Bootstrap handles: display, direction, spacing, alignment -->
</div>

<!-- ❌ Wrong: Custom CSS for what Bootstrap provides -->
<div class="component__container">
    <!-- Then trying to write CSS with display, flex, padding, gap -->
</div>
```

### Bootstrap Components (Use as Base)

| Component | Bootstrap Class | When to Add BEM |
|-----------|----------------|-----------------|
| Button | `.btn` `.btn-primary` | Brand colors, custom hover effects |
| Card | `.card` | Custom shadows, borders, highlights |
| Form Control | `.form-control` | Brand colors, focus states |
| Badge | `.badge` | Custom sizes, colors |
| Modal | `.modal` | Custom animations, positioning |
| Table | `.table` | Custom row colors, hover effects |
| Alert | `.alert` | Custom icons, styling |
| Nav | `.nav` `.nav-item` | Custom active states |
| Grid | `.row` `.col-*` | Never override with BEM |
| Flexbox | `.d-flex` `.flex-*` `.gap-*` | Never override with BEM |
| Spacing | `.m-*` `.p-*` | Never override with BEM |
| Display | `.d-none` `.d-block` | Never override with BEM |

### Detection Pattern (Grep Commands)

```bash
# Find CSS that duplicates Bootstrap spacing
grep -rn "padding:\|margin:\|padding-top:\|margin-left:" \
  ezzydelivery --include="*.css" | grep -v "var(--spacing" | head -20

# Find CSS that duplicates display/flex
grep -rn "display:\s*flex\|display:\s*block\|flex-direction:\|gap:" \
  ezzydelivery --include="*.css" | grep -v "\.d-" | head -20

# Find CSS that duplicates borders on Bootstrap components
grep -rn "\..*__btn\|\..*__card\|\..*__alert" ezzydelivery --include="*.css" | \
  grep -A2 "border:\|padding:" | head -20
```

---

## CLAUDE.md CSS Rules (Absolute)

1. ❌ **NO `<style>` tags in templates** (except critical-path exceptions)
2. ❌ **NO non-dynamic inline styles** (except layout driven by JavaScript)
3. ✅ **All CSS via external files** loaded in `{% block extra_css %}`
4. ✅ **Use Brand Kit variables** for all colors, spacing, typography
5. ✅ **Dynamic CSS only in `:root`** blocks when template variables are required (e.g., `{{ color }}`)

### Critical-Path Exceptions (APPROVED to keep inline)
- `fleet/pwa_base.html:37` — PWA reset styles (performance critical)
- `templates/includes/head.html` — Brand Kit variables (must load before Bootstrap)
- `templates/includes/head-dashboard.html` — Dashboard library customizations
- Any `:root` block with `{{ Django_variables }}` for customer branding

---

## Phase 1: Comprehensive Audit

Use this methodology to identify ALL CSS violations across the entire project.

### Audit Commands

**Search for `<style>` tags:**
```bash
grep -r '<style' --include="*.html" ezzydelivery/ | grep -v staticroot | head -20
```

**Search for non-dynamic inline styles:**
```bash
grep -rn 'style="[^{%}]' --include="*.html" ezzydelivery/ | grep -v staticroot | grep -v 'style="width:' | grep -v 'style="display:none' | head -20
```

**Filter by app (example: Workforce):**
```bash
grep -r '<style' --include="*.html" ezzydelivery/workforce/templates/ | wc -l
grep -rn 'style="[^{%}]' --include="*.html" ezzydelivery/workforce/templates/ | wc -l
```

### Bootstrap Duplication Check

As part of audit, scan for CSS that duplicates Bootstrap's built-in classes:

```bash
# Search in app CSS files for spacing duplication
grep -rn "^\s*padding:\|^\s*margin:\|^\s*gap:" \
  ezzydelivery/app/static/app/css/ --include="*.css" | \
  grep -v "var(--spacing" | grep -v "^[^:]*:[^:]*\s*0" | head -10

# Search for flex/display duplication
grep -rn "display:\s*flex\|display:\s*grid\|flex-direction:\|justify-content:" \
  ezzydelivery/app/static/app/css/ --include="*.css" | \
  grep -v "@media\|/\*" | head -10

# Search for form control duplication (in BEM classes)
grep -rn "\..*__input\|\..*__select\|\..*__form" \
  ezzydelivery/app/static/app/css/ --include="*.css" | \
  grep "border:\|padding:\|font-size:" | head -10
```

**If found:**
- Replace spacing with Bootstrap utilities in HTML: `p-3 m-2 gap-2`
- Replace flex with Bootstrap utilities: `d-flex flex-row gap-3 align-items-center`
- Keep BEM only for custom visual effects: colors, shadows, transitions, custom states

### Audit Report Template

When auditing, create a report with these sections:

```markdown
## CSS Compliance Audit — [App Name]

### Summary
- Total templates: [N]
- Templates with `<style>` tags: [N]
- Templates with inline styles: [N]
- Overall compliance: [%]

### Critical Issues (Style Tags)
| File | Line | Issue | Type |
|------|------|-------|------|
| app/templates/file.html | 10-104 | 95 lines of .xyz__ CSS | CRITICAL |

### High Issues (Inline Styles)
| File | Pattern | Count |
|------|---------|-------|
| app/templates/file.html | style="color:#..." | 12 |

### Approved Exceptions
| File | Reason | Status |
|------|--------|--------|
| path/critical.html | PWA reset | ✅ |
```

---

## Phase 2: Create Missing CSS Files

When a template has `<style>` block but no dedicated CSS file, create one.

### Naming Convention
```
{app}/static/{app}/css/{page_slug}.css
```

**Examples:**
- `product/static/product/css/product-combo.css` — for combo_form.html + combo_list.html
- `fleet/static/fleet/css/vehicle-form.css` — for parts/vehicle_add.html
- `workforce/static/workforce/css/fleet-transactions.css` — for fleet_transactions.html

### CSS File Template

```css
/**
 * {App Name} — {Page/Component Name}
 * Source templates: {list of template files}
 * BEM Prefix: {app-code}__
 */

/* ========================================
   {Component Name} — Component block styles
   ======================================== */

.{app}_{component}__ { /* Base block styles */ }
.{app}_{component}__element { /* Element styles */ }
.{app}_{component}__element--modifier { /* Modifier styles */ }

/* Responsive overrides */
@media (max-width: 768px) {
    .{app}_{component}__ { /* Mobile styles */ }
}
```

### File Creation Steps

1. **Extract `<style>` block content** from template
2. **Pick a BEM prefix** (2-4 letters, unique to page)
3. **Refactor all rules** to use `{app}_{page}__element` naming
4. **Replace hardcoded colors** with Brand Kit variables: `var(--brand-primary)`, `var(--brand-danger)`, etc.
5. **Use spacing variables** for all padding/margin: `var(--spacing-md)`, `var(--spacing-lg)`
6. **Add comments** for component sections
7. **Test responsiveness** — add mobile overrides for XS screens

---

## Phase 3: Move CSS to Files

For each identified CSS violation:

### Template Update Checklist

```html
{% extends "app_base.html" %}  <!-- or base.html for public pages -->
{% load static %}

{% block title %}Page Title{% endblock %}

<!-- Step 1: Add extra_css block if missing (HTMX dashboards: put CSS in app main file instead!) -->
{% block extra_css %}
<link href="{% static 'app/css/page-slug.css' %}" rel="stylesheet" type="text/css">
{% endblock %}

<!-- Step 2: REMOVE the <style> block — it should be gone now -->

{% block content %}
<!-- Step 3: Replace inline styles with CSS classes -->
<div class="{app}_{page}__container">  <!-- was: style="padding:1rem" -->
    ...
</div>
{% endblock %}
```

### Common Inline → CSS Class Conversions

| Inline Style | CSS Class | Location |
|---|---|---|
| `style="color:var(--brand-primary)"` | `.component__icon` | CSS file |
| `style="padding:1rem 0.5rem"` | `.component__box` | CSS file |
| `style="font-size:0.75rem"` | `.component__label` | Use Brand Kit variable |
| `style="width:100%;max-width:600px"` | `.component__wrapper` | CSS file |
| `style="display:none"` (JS-toggled) | `.component--hidden` + `classList.toggle()` | CSS file |
| `style="animation-delay:0.1s"` (dynamic) | `.component--delay-1` + inline `--delay-1: 0.1s` | Hybrid |
| `style="border-color:{{ color }}"` | Keep inline (dynamic) | Template |

---

## Phase 4: Brand Kit Variable Migration

Replace hardcoded colors with semantic Brand Kit variables.

### Semantic Color Variables (Add to `brandkit.css`)

```css
:root {
    /* Semantic Status Colors */
    --brand-danger: #dc2626;
    --brand-danger-dark: #991b1b;
    --brand-danger-bg: #fef2f2;
    --brand-success: #15803d;
    --brand-success-light: #16a34a;
    --brand-success-bright: #22c55e;
    --brand-success-bg: #dcfce7;
    --brand-warning: #d97706;
    --brand-warning-alt: #f59e0b;
    --brand-warning-bg: #fef3c7;
    --brand-info: #2563eb;
    --brand-info-dark: #1e40af;
    --brand-info-bg: #eff6ff;
    
    /* Extended Grey Scale */
    --brand-grey-50: #f8f9fa;
    --brand-grey-150: #e9ecef;
    --brand-grey-250: #dee2e6;
    --brand-grey-450: #9ca3af;
    --brand-grey-550: #6b7280;
    --brand-grey-650: #374151;
    --brand-grey-750: #e5e7eb;
    --brand-grey-850: #f3f4f6;
}
```

### Color Replacement Patterns

**Before (hardcoded):**
```css
.button { color: #22c55e; }
.alert { background: #fef2f2; border-color: #dc2626; }
.badge { background: #f7c000; }
```

**After (Brand Kit):**
```css
.button { color: var(--brand-success-bright); }
.alert { background: var(--brand-danger-bg); border-color: var(--brand-danger); }
.badge { background: var(--brand-primary); }
```

---

## Phase 5: Fix Specific Violations

### Style Tag Violations (CRITICAL)

**Pattern:** Extract entire `<style>` block into CSS file

**Template Before:**
```html
<style>
.combo__hero { display: flex; padding: 1rem; }
.combo__title { font-size: 1.5rem; color: #333; }
</style>
<div class="combo__hero">
    <h1 class="combo__title">Products</h1>
</div>
```

**Template After:**
```html
{% block extra_css %}
<link href="{% static 'product/css/product-combo.css' %}" rel="stylesheet">
{% endblock %}
<div class="combo__hero">
    <h1 class="combo__title">Products</h1>
</div>
```

**CSS File (`product/css/product-combo.css`):**
```css
.combo__hero {
    display: flex;
    padding: var(--spacing-md);
    background: var(--brand-white);
}

.combo__title {
    font-size: var(--text-2xl);
    color: var(--brand-grey-800);
}
```

### Inline Style Violations (HIGH)

**Pattern:** Replace `style="..."` with CSS class

**Template Before:**
```html
<div style="padding:0.75rem 1rem; background:#fff; border-radius:0.5rem;">
    <span style="color:var(--brand-primary); font-weight:600;">Label</span>
</div>
```

**Template After:**
```html
<div class="combo__card">
    <span class="combo__card-label">Label</span>
</div>
```

**CSS File:**
```css
.combo__card {
    padding: var(--spacing-sm) var(--spacing-md);
    background: var(--brand-white);
    border-radius: var(--brand-radius-sm);
}

.combo__card-label {
    color: var(--brand-primary);
    font-weight: var(--font-weight-bold);
}
```

### JavaScript-Embedded CSS (MEDIUM)

**Pattern:** Move CSS to file, keep JS logic separate

**Template Before:**
```html
<script>
    const printWindow = window.open('', '', 'width=800,height=600');
    printWindow.document.write(`
        <style>
            body { margin: 0; padding: 1rem; }
            .print-header { font-size: 20px; font-weight: bold; }
        </style>
        <div class="print-header">Receipt</div>
    `);
</script>
```

**Fix:** Extract CSS to dedicated print CSS file, inject via link tag

```html
<!-- In template <head> or extra_css -->
<link href="{% static 'app/css/receipt-print.css' %}" rel="stylesheet" media="print">

<!-- In template body -->
<div id="print_container" style="display:none">
    <div class="receipt__header">Receipt</div>
</div>

<!-- In JS file -->
const printWindow = window.open('', '', 'width=800,height=600');
printWindow.document.write(document.getElementById('print_container').innerHTML);
printWindow.focus();
```

---

## Phase 6: Dashboard HTMX Exception

**CRITICAL RULE:** Dashboard pages using HTMX sidebar navigation must NOT use `{% block extra_css %}`

**Why:** HTMX only swaps `#main-content`, NOT the `<head>`. CSS loaded via `extra_css` won't be injected during navigation, causing missing styles.

### Correct Pattern for Dashboards

| Base Template | CSS File | Location |
|---|---|---|
| `wf_dashboard_base.html` | `workforce/static/workforce/css/workforce.css` | Line 15 cache-buster |
| `business_dashboard_base.html` | `business/static/business/css/business.css` | Line 30 cache-buster |
| `fleet_dashboard_base.html` | `fleet/static/fleet/css/fleet.css` | Check template |

**Add to app's main CSS file, NOT via `{% block extra_css %}`:**

```css
/* workforce.css — Line 1-5: Cache buster comment */
/* v=202604221a — Update 'a' to 'b' when changing */

/* Dashboard Page Styles — Added for component XYZ */
.uvl__container { ... }     /* User Verification List */
.pkl__item { ... }           /* Pickup Locations */
.odt__detail { ... }         /* Order Details */
```

**Template:**
```html
{% extends "wf_dashboard_base.html" %}

{# NO {% block extra_css %} — CSS goes in workforce.css #}

{% block content %}
<div id="main-content">
    <div class="uvl__container">
        {# Uses CSS from workforce.css #}
    </div>
</div>
{% endblock %}
```

---

## Phase 7: Verify & Reload

### Verification Steps

**1. Check all `<style>` tags are removed:**
```bash
grep -r '<style' --include="*.html" ezzydelivery/ | grep -v staticroot
```
Should return only approved exceptions.

**2. Check inline styles are removed:**
```bash
grep -rn 'style="[^{%}]' --include="*.html" ezzydelivery/ | grep -v staticroot | grep -v dynamic | wc -l
```
Should be 0 (or only dynamic `{{ }}` styles).

**3. Verify CSS files are linked:**
```bash
grep -r '{% block extra_css %}' ezzydelivery/ --include="*.html" | grep '<link'
```
Should show CSS file loads for non-HTMX templates.

### Server Reload (ALWAYS RUN AFTER ANY CSS CHANGE)

```bash
# Step 1: Collect static files
source /home/ezzyadmin/ezdlproject/venvezzy/bin/activate && \
python manage.py collectstatic --noinput

# Step 2: Reload gunicorn
kill -HUP $(pgrep -f "gunicorn.*ezzydelivery" | head -1)

# Step 3: Test site health
curl -sI https://ezzydelivery.qa/ | head -5
```

Should show `HTTP/2 200` or `HTTP/1.1 200`

---

## Monitoring & Memory

### Track Compliance in Memory

Create a `css-compliance-tracking.md` memory file with:

```markdown
---
name: CSS Compliance Status & Tracking
type: project
---

## Status Summary
- Audit date: YYYY-MM-DD
- Total templates scanned: [N]
- Style tag violations: [N] critical, [N] exceptions
- Inline style violations: [N] templates
- Overall compliance: [%]

## Critical Issues (Must Fix)
| File | Type | Status |
|------|------|--------|
| app/template.html:10-104 | Style tag | PENDING |

## Fixed Issues
| File | Type | Date |
|------|------|------|
| app/template.html | Style tag → CSS file | 2026-04-22 |
```

### Update After Each Fix

```bash
# Grep to verify fix
grep -n '<style' ezzydelivery/app/templates/file.html  # Should return 0

# Update memory: Mark as FIXED
# Run server reload commands above
```

---

## Quick Reference: Hardcoded Colors → Brand Kit Variables

**Common colors found in violations:**

| Hardcoded | Variable | Use Case |
|---|---|---|
| `#22c55e` | `--brand-success-bright` | Success states |
| `#dc2626` | `--brand-danger` | Error states |
| `#f7c000` | `--brand-primary` | Primary action |
| `#fef2f2` | `--brand-danger-bg` | Error background |
| `#dcfce7` | `--brand-success-bg` | Success background |
| `#333` | `--brand-grey-700` | Dark text |
| `#999` | `--brand-grey-500` | Medium text |
| `#f0f0f0` | `--brand-grey-200` | Light background |

---

## Troubleshooting

### Styles Not Updating After Reload

1. **Clear browser cache:**
   - Chrome DevTools → Application → Clear Storage
   - Or: `Ctrl+Shift+Delete` (Windows) / `Cmd+Shift+Delete` (Mac)

2. **Verify static collection:**
   ```bash
   ls -la staticroot/app/css/file.css  # Should exist
   ```

3. **Check CSS file was linked in template:**
   ```html
   <!-- Should be present in template -->
   {% block extra_css %}
   <link href="{% static 'app/css/file.css' %}" rel="stylesheet">
   {% endblock %}
   ```

### CSS Cache-Buster Not Working

Add version query parameter to CSS link:

```html
<!-- Before -->
<link href="{% static 'app/css/file.css' %}" rel="stylesheet">

<!-- After (cache-buster) -->
<link href="{% static 'app/css/file.css' %}?v=202604221a" rel="stylesheet">

<!-- Update to next version when CSS changes -->
<!-- ?v=202604221a → ?v=202604221b →v=202604221c ... →v=202604222a -->
```

### Styles Applied to Wrong Elements

**Likely cause:** BEM class name mismatch between template and CSS

```bash
# Find template class names
grep -n 'class="xyz__' ezzydelivery/app/templates/file.html

# Find CSS class definitions
grep -n '\.xyz__' ezzydelivery/app/static/app/css/file.css

# If mismatch, they must match exactly
```

---

## Tools & Resources

**CSS Validation:**
- W3C CSS Validator: https://jigsaw.w3.org/css-validator/
- Chrome DevTools → Inspect → Styles tab (see actual applied styles)

**Brand Kit Reference:**
- File: `ezzydelivery/webpages/static/webpages/css/brandkit.css`
- Color variables: `:root` block (line 1-80)
- Spacing variables: `--spacing-xs` through `--spacing-xl`
- Typography: `--text-xs` through `--text-5xl`

**Grep Examples:**
```bash
# Find all hardcoded colors in CSS
grep -rn '#[0-9a-fA-F]\{6\}' ezzydelivery/ --include="*.css" | head -20

# Find all inline style attributes
grep -rn 'style="' ezzydelivery/ --include="*.html" | head -20

# Find all <style> tags
grep -rn '<style' ezzydelivery/ --include="*.html" | wc -l
```

---

## Common Violations & Fixes

### Violation 0: Bootstrap CSS Duplication (Most Common)

**Pattern:** Custom BEM classes re-declaring what Bootstrap already handles

```css
/* WRONG — Duplicates Bootstrap */
.combo__wrapper {
    display: flex;              /* Bootstrap: .d-flex */
    flex-direction: row;        /* Bootstrap: .flex-row */
    gap: 1rem;                  /* Bootstrap: .gap-3 */
    align-items: center;        /* Bootstrap: .align-items-center */
    padding: 1rem;              /* Bootstrap: .p-3 */
    margin-bottom: 1.5rem;      /* Bootstrap: .mb-3 */
}

/* RIGHT — Bootstrap base + BEM for custom visuals only */
.combo__wrapper {
    /* All layout handled by Bootstrap utilities in HTML */
    transition: all 0.3s ease;  /* Custom animation */
    border-left: 4px solid var(--brand-primary);  /* Custom visual */
}
```

**Template:**
```html
<!-- Before: Custom CSS for layout -->
<div class="combo__wrapper">
    <icon />
    <text />
</div>

<!-- After: Bootstrap utilities + minimal BEM -->
<div class="d-flex flex-row gap-3 align-items-center p-3 mb-4 combo__wrapper">
    <icon />
    <text />
</div>
```

**How to Fix:**
1. Find all custom CSS with `display:`, `flex-`, `gap:`, `padding:`, `margin:`
2. Move those to Bootstrap utility classes in HTML
3. Keep only custom visual styling in BEM CSS (colors, shadows, animations)
4. Use grep to find them: `grep -rn "display:\s*flex\|gap:\|padding:" ezzydelivery/app/static/app/css/`

---

### Violation 1: Component CSS in `<style>` Block

```html
<!-- ❌ WRONG: Only BEM, missing Bootstrap base -->
<style>
.component__card { 
    padding: 1rem; 
    background: white; 
    border-radius: 8px; 
}
</style>
<div class="component__card">Content</div>

<!-- ✅ RIGHT: Use Bootstrap + BEM together -->
<!-- In HTML template -->
<div class="card component__card">Content</div>

<!-- In CSS file -->
```

```css
/* Bootstrap .card handles: padding, background, border-radius */
/* BEM .component__card ADDS: custom brand styling */
.component__card {
    /* Bootstrap provides the base structure */
    border: 1px solid var(--brand-grey-200);
    box-shadow: 0 2px 8px rgba(0,0,0,0.08);
    transition: all 0.3s ease;
}

.component__card:hover {
    box-shadow: 0 4px 12px rgba(0,0,0,0.12);
}
```

### Violation 2: Hardcoded Colors in Inline Styles

```html
<!-- ❌ WRONG: Inline styles + missing Bootstrap base -->
<button style="background-color: #22c55e; color: white;">
    Success
</button>

<!-- ✅ RIGHT: Bootstrap base + BEM custom styling -->
<button class="btn btn-success combo__btn-success">
    Success
</button>
```

```css
/* Bootstrap .btn and .btn-success handle: padding, borders, display, base color */
/* BEM .combo__btn-success ADDS: custom brand color, hover effects, shadows */

.combo__btn-success {
    background: var(--brand-success-bright) !important;
    border-color: var(--brand-success-bright) !important;
    box-shadow: 0 2px 6px rgba(34, 197, 94, 0.3);
    transition: all 0.3s ease;
}

.combo__btn-success:hover {
    background: var(--brand-success-dark) !important;
    border-color: var(--brand-success-dark) !important;
    transform: translateY(-2px);
    box-shadow: 0 4px 12px rgba(34, 197, 94, 0.4);
}

.combo__btn-success:active {
    transform: translateY(0);
}
```

### Violation 3: Layout Styling in Template

```html
<!-- ❌ WRONG: Layout in inline styles (never do this!) -->
<div style="display: flex; gap: 1rem; align-items: center; padding: 1rem;">
    <icon />
    <text />
</div>

<!-- ✅ RIGHT: Layout via Bootstrap utilities + BEM for visuals -->
<div class="d-flex gap-3 align-items-center p-3 combo__hero-content">
    <icon />
    <text />
</div>
```

```css
/* Bootstrap utilities handle LAYOUT:
   .d-flex → display: flex
   .gap-3 → gap: 1rem
   .align-items-center → align-items: center
   .p-3 → padding: 1rem
*/

/* BEM .combo__hero-content ADDS: custom visual styling */
.combo__hero-content {
    background: var(--brand-white);
    border-radius: var(--brand-radius-lg);
    box-shadow: 0 2px 8px rgba(0,0,0,0.08);
    transition: all 0.3s ease;
}

.combo__hero-content:hover {
    box-shadow: 0 4px 12px rgba(0,0,0,0.12);
    transform: translateY(-2px);
}
```

**Rule:** Never write CSS for `display:`, `flex-*`, `gap:`, `padding:`, `margin:`. Use Bootstrap utilities in HTML instead.

---

## Approval Process

Before marking a CSS fix as complete:

### Pattern Compliance
- [ ] **BOTH Bootstrap AND BEM classes on same element** (e.g., `class="btn btn-primary combo__btn-submit"`)
- [ ] Bootstrap classes listed FIRST in class attribute order
- [ ] All `<style>` tags removed from template
- [ ] All non-dynamic inline styles removed (moved to CSS or replaced with classes)

### CSS File Quality
- [ ] CSS file created with correct naming: `{app}/static/{app}/css/{page}.css`
- [ ] BEM classes used throughout with unique app prefix (2-4 letters)
- [ ] NO custom CSS for layout (display, flex, gap, padding, margin) — use Bootstrap utilities
- [ ] NO duplication of Bootstrap component base styles (padding, borders, font-size)
- [ ] Brand Kit variables used for colors, spacing, typography: `var(--brand-*)`
- [ ] Custom styling ONLY: colors, shadows, animations, hover effects, custom states

### Integration & Testing
- [ ] `{% block extra_css %}` updated with `<link>` to CSS file (non-HTMX pages only)
- [ ] For HTMX dashboards: CSS added to app's main CSS file instead
- [ ] Server reloaded: `kill -HUP $(pgrep -f "gunicorn.*ezzydelivery" | head -1)` + `collectstatic`
- [ ] Static files collected: `python manage.py collectstatic --noinput`
- [ ] Site tested: `curl -sI https://ezzydelivery.qa/` returns HTTP 200
- [ ] Grep verification: `grep -r '<style' | grep -v approved` returns nothing
- [ ] Bootstrap duplication check: `grep -rn "display:\s*flex\|gap:\|padding:" ezzydelivery/app/static/app/css/` returns nothing
- [ ] Memory updated with fix status and completion date

---

## Integration with Project Workflow

**When to use CSS-Fix skill:**
1. User reports "styles missing" or "CSS not working"
2. Code review identifies `<style>` tags or inline styles
3. Comprehensive CSS audit reveals violations (use `/css-fix`)
4. Brand Kit variables need to be implemented
5. New page added — ensure it follows CSS compliance rules

**Use with other skills:**
- `frontend-designer.md` — For BEM naming and component patterns
- `mb-optimization.md` — For mobile-first responsive CSS
- `css-font-standardization.md` — For typography adjustments

