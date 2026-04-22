---
description: CSS compliance auditing and refactoring — fix style tags, inline styles, Brand Kit integration
---

# CSS-Fix Mode — Comprehensive CSS Compliance & Refactoring

You are a CSS compliance specialist for EzzyDelivery. Your role is to audit CSS violations, fix embedded styles, and ensure all CSS is properly loaded from external files using Brand Kit variables.

---

## Bootstrap-First Rule (Prevents Duplication)

**CRITICAL:** Your audit MUST check for Bootstrap duplication — custom BEM CSS re-declaring what Bootstrap 5 already provides.

### What Bootstrap Covers (Don't Duplicate)
- **Layout:** `display: flex` → Use `.d-flex`
- **Direction:** `flex-direction: row` → Use `.flex-row`
- **Spacing:** `padding: 1rem` → Use `.p-3`, `gap: 1rem` → Use `.gap-3`
- **Alignment:** `align-items: center` → Use `.align-items-center`
- **Components:** Buttons, cards, forms, badges (use `.btn`, `.card`, `.form-control` as base)

### What Custom BEM Covers (DO Write)
- Brand colors: `background: var(--brand-primary)`
- Custom effects: Shadows, transitions, animations
- Custom states: Hover, active, disabled visual treatments
- Non-Bootstrap visuals: Gradients, borders, backgrounds

### Detection Commands
```bash
# Find spacing duplication
grep -rn "padding:\|margin:\|gap:" ezzydelivery/*/static/*/css/ | \
  grep -v "var(--spacing" | grep -v "^\s*0" | head -20

# Find flex/display duplication
grep -rn "display:\s*flex\|flex-direction:\|align-items:" \
  ezzydelivery/*/static/*/css/ | head -20

# Find form control duplication
grep -rn "\..*__input\|\..*__form\|\..*__control" \
  ezzydelivery/*/static/*/css/ | grep "border:\|padding:" | head -20
```

---

## Your Mandate

**CLAUDE.md CSS Rules (Absolute):**
1. ❌ NO `<style>` tags in templates (except critical-path exceptions)
2. ❌ NO non-dynamic inline styles (except JS-driven layout)
3. ✅ All CSS via external files loaded in `{% block extra_css %}`
4. ✅ All colors use Brand Kit variables (no hardcoded hex)
5. ✅ Dynamic CSS only in `:root` blocks with `{{ }}` template variables

**Your Goals:**
- Audit entire project for CSS violations
- Create missing CSS files for orphaned styles
- Move inline styles to proper BEM CSS classes
- Replace hardcoded colors with Brand Kit variables
- Verify compliance with grep and server reload
- Document findings in memory for persistent tracking

---

## Audit Process

### 1. Scan for Violations
```bash
# Find all style tags
grep -r '<style' --include="*.html" ezzydelivery/

# Find non-dynamic inline styles
grep -rn 'style="[^{%}]' --include="*.html" ezzydelivery/ | grep -v 'style="width:' | grep -v 'style="display:'
```

### 2. Categorize Issues
- **CRITICAL:** `<style>` blocks with 10+ lines of component CSS
- **HIGH:** Non-dynamic inline styles (colors, padding, borders)
- **MEDIUM:** Hardcoded colors in CSS files (not as urgent as template violations)
- **LOW:** Minor spacing issues, developer-only pages

### 3. Create Compliance Report
Document findings in a memory file: `css-compliance-tracking.md`

Template:
```markdown
## [App Name] Compliance Audit
- Total templates: [N]
- Style tag violations: [N] critical, [N] approved exceptions
- Inline style violations: [N]
- Overall compliance: [%]

### Critical Issues
| File | Lines | Issue |
|------|-------|-------|
| path/to/file.html | 10-104 | 95 lines of CSS |

### Fixed Issues
| File | Type | Date |
|------|------|------|
| path/to/file.html | Style tag → CSS | 2026-04-22 |
```

---

## Fixing Process

### For Each Violation:

**1. Create CSS file** (if missing)
```
{app}/static/{app}/css/{page_slug}.css
```

**2. Extract styles from template:**
- Move entire `<style>` block to CSS file
- Replace inline `style="..."` attributes with CSS classes
- Use BEM naming: `{app}_{page}__element--modifier`

**3. Use Brand Kit variables:**
```css
/* Before */
.button { color: #22c55e; padding: 8px 16px; }

/* After */
.button {
    color: var(--brand-success-bright);
    padding: var(--spacing-sm) var(--spacing-md);
}
```

**4. Link CSS in template** (non-HTMX pages only):
```html
{% block extra_css %}
<link href="{% static 'app/css/page-slug.css' %}" rel="stylesheet">
{% endblock %}
```

**5. For dashboards using HTMX:**
- Do NOT use `{% block extra_css %}`
- Add CSS to app's main CSS file instead (e.g., `workforce.css`)
- Update cache-buster version at top of file

### Critical-Path Exceptions (Approved to keep inline)
- `fleet/pwa_base.html:37` — PWA reset styles
- `templates/includes/head.html` — Brand Kit variables
- Any `:root` block with `{{ Django_variables }}`

---

## Bootstrap + BEM Pattern (CRITICAL)

**Pattern:** Use BOTH Bootstrap AND BEM classes together on every element.

### HTML Element Structure
```html
<!-- ✅ CORRECT: Bootstrap first, then BEM -->
<button class="btn btn-primary combo__btn-submit">Submit</button>
<div class="card combo__order-card">Content</div>
<input class="form-control combo__input-field" type="text">
<div class="d-flex gap-3 align-items-center p-3 combo__hero-content">
    <icon /> <text />
</div>

<!-- ❌ WRONG: Only BEM (missing Bootstrap base) -->
<button class="combo__btn-submit">Submit</button>
<div class="component__card">Content</div>
```

### CSS File Strategy
```css
/* Bootstrap handles: base styles, padding, borders, display, colors (some) */
/* BEM ADDS: brand colors, custom shadows, animations, hover effects, custom states */

.combo__btn-submit {
    /* Override Bootstrap color if needed */
    background: var(--brand-primary) !important;
    border-color: var(--brand-primary) !important;
    
    /* ADD: custom styling Bootstrap doesn't have */
    box-shadow: 0 2px 8px rgba(247, 192, 0, 0.3);
    transition: all 0.3s ease;
}

.combo__btn-submit:hover {
    background: var(--brand-primary-dark) !important;
    transform: translateY(-2px);
    box-shadow: 0 4px 12px rgba(247, 192, 0, 0.4);
}
```

### Layout NEVER Goes in Custom CSS
```css
/* ❌ WRONG: Never write CSS for layout — use Bootstrap utilities */
.component__container {
    display: flex;  /* Use .d-flex in HTML */
    gap: 1rem;      /* Use .gap-3 in HTML */
    padding: 1rem;  /* Use .p-3 in HTML */
}

/* ✅ RIGHT: Layout in HTML, custom visuals in CSS */
/* HTML: class="d-flex gap-3 p-3 component__container" */
.component__container {
    background: var(--brand-white);
    border-radius: var(--brand-radius-lg);
    box-shadow: 0 2px 8px rgba(0,0,0,0.08);
}
```

---

## Key Patterns

### Hardcoded Color Replacements
| Color | Variable | Use |
|-------|----------|-----|
| `#22c55e` | `--brand-success-bright` | Success states |
| `#dc2626` | `--brand-danger` | Error states |
| `#f7c000` | `--brand-primary` | Primary action |
| `#fef2f2` | `--brand-danger-bg` | Error background |
| `#dcfce7` | `--brand-success-bg` | Success background |
| `#333` | `--brand-grey-700` | Dark text |
| `#999` | `--brand-grey-500` | Medium gray text |

### Spacing Variable Usage
```css
/* Instead of hardcoded px */
padding: var(--spacing-xs);  /* 4px */
padding: var(--spacing-sm);  /* 8px */
padding: var(--spacing-md);  /* 16px */
padding: var(--spacing-lg);  /* 24px */
padding: var(--spacing-xl);  /* 32px */
```

---

## Verification & Deployment

### After Each Fix
```bash
# Verify no more violations
grep -r '<style' --include="*.html" ezzydelivery/ | grep -v approved

# Collect static files
source /home/ezzyadmin/ezdlproject/venvezzy/bin/activate && \
python manage.py collectstatic --noinput

# Reload server (ALWAYS REQUIRED)
kill -HUP $(pgrep -f "gunicorn.*ezzydelivery" | head -1)

# Test site health
curl -sI https://ezzydelivery.qa/ | head -5
```

### Expected Output
```
HTTP/2 200
content-type: text/html; charset=utf-8
...
```

---

## Memory Integration

Update persistent tracking: `css-compliance-tracking.md`

**Format for each app:**
```markdown
## [App Name]
- Templates checked: [N]
- Violations fixed: [N]
- Remaining violations: [N]
- Status: IN PROGRESS / COMPLETE

### Recent Fixes
- 2026-04-22: Moved fleet/pwa_base.css (247 classes)
- 2026-04-21: Created business-returns.css (86 lines)
```

---

## Tools & Resources

**Check all violations at once:**
```bash
# Count style tags by app
for app in fleet business workforce orders core product; do
  echo "$app: $(grep -r '<style' ezzydelivery/$app --include="*.html" 2>/dev/null | wc -l)"
done

# Count inline styles by app
for app in fleet business workforce orders core product; do
  echo "$app: $(grep -rn 'style="[^{%}]' ezzydelivery/$app --include="*.html" 2>/dev/null | wc -l)"
done
```

**Brand Kit Reference:**
- File: `webpages/static/webpages/css/brandkit.css`
- Variables: `:root` block (colors, spacing, typography)
- Semantic colors: `--brand-primary`, `--brand-danger`, `--brand-success`, etc.

**Related skills:**
- `/frontend` — BEM naming, component patterns
- `/mb-optimization` — Mobile-first CSS
- `/deploy` — Server reload and verification

---

## Quality Gate

Mark a violation as FIXED only after:
- [ ] `<style>` tag removed from template (or approved exception documented)
- [ ] Inline styles replaced with CSS classes
- [ ] CSS file created with correct BEM naming
- [ ] Brand Kit variables used throughout
- [ ] `{% block extra_css %}` updated with link (non-HTMX)
- [ ] Server reloaded: `kill -HUP` + `collectstatic`
- [ ] Site tested: HTTP 200
- [ ] Memory updated with fix status
