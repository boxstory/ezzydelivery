# Brand Kit Quick Reference

**Quick lookup for common design elements**

For complete documentation, see [BRAND_KIT_REFERENCE.md](BRAND_KIT_REFERENCE.md)

---

## 🎨 Colors at a Glance

### Primary Brand Colors
```css
--brand-primary: #f7c000           /* 🟡 Ezzy Yellow */
--brand-primary-dark: #f4c20d      /* 🟡 Darker Yellow */
```

### Brand Gradients (defined in brandkit.css)
```css
--brand-gradient-yellow-white: linear-gradient(135deg, var(--brand-primary), var(--brand-white))
--brand-gradient-black-grey: linear-gradient(135deg, var(--brand-black), var(--brand-grey-700))
--brand-gradient-black-navy: linear-gradient(135deg, var(--brand-black), var(--brand-navy-light))
--brand-gradient-navy: linear-gradient(135deg, var(--brand-navy), var(--brand-navy-light))
--brand-gradient-yellow-dark: linear-gradient(135deg, var(--brand-primary), var(--brand-grey-800))
--brand-gradient-purple: linear-gradient(135deg, var(--brand-primary), var(--brand-primary-dark))
```

> ⚠️ `--brand-gradient-green` is **NOT** in brandkit.css. Use inline: `linear-gradient(135deg, #10b981 0%, #059669 100%)`

### Neutral Greys
```css
--brand-grey-100: #fafafa          /* Lightest - Backgrounds */
--brand-grey-300: #dcdcdc          /* Borders */
--brand-grey-700: #333             /* Text */
--brand-white: #ffffff             /* White */
--brand-black: #000000             /* Black */
```

### Status Colors
```css
--status-success: #10b981          /* 🟢 Green */
--status-warning: #f59e0b          /* 🟠 Orange */
--status-error: #ef4444            /* 🔴 Red */
--status-info: #3b82f6             /* 🔵 Blue */
```

---

## 📏 Spacing System

```css
--spacing-xs: 0.25rem              /* 4px */
--spacing-sm: 0.5rem               /* 8px */
--spacing-md: 1rem                 /* 16px */
--spacing-lg: 1.5rem               /* 24px */
--spacing-xl: 2rem                 /* 32px */
```

---

## 🔵 Border Radius

```css
--brand-radius-sm: 8px             /* Small - inputs */
--brand-radius-md: 12px            /* Medium - cards */
--brand-radius-lg: 18px            /* Large - sections */
--brand-radius-full: 50px          /* Pills - buttons */
--brand-radius-circle: 50%         /* Circles - avatars */
```

---

## ☁️ Shadows

```css
--brand-shadow-sm: 0 1px 3px rgba(0,0,0,0.08)           /* Subtle */
--brand-shadow-md: 0 4px 8px rgba(0,0,0,0.1)            /* Standard */
--brand-shadow-lg: 0 10px 20px rgba(0,0,0,0.12)         /* Prominent */
--brand-shadow-xl: 0 20px 40px rgba(0,0,0,0.15)         /* Deep */
```

> ⚠️ `--shadow-purple`, `--shadow-green`, `--shadow-yellow` are **NOT** in brandkit.css. Use inline values if needed.

---

## 🔘 Button Classes

```html
<!-- Primary gradient button (exists in brandkit-components.css) -->
<button class="btn-brand-primary">Submit</button>

<!-- Secondary button (exists in brandkit-components.css) -->
<button class="btn-brand-secondary">Cancel</button>

<!-- Success/Danger buttons -->
<button class="btn-brand-success">Confirm</button>
<button class="btn-brand-danger">Delete</button>
```

> ⚠️ `btn-brand-outline` does **NOT** exist in brandkit.css — use Bootstrap's `btn btn-outline-*` instead.

---

## 🎴 Card Classes

```html
<!-- Standard Bootstrap card (use Bootstrap .card class) -->
<div class="card">Content</div>
```

> ⚠️ `card-brand` and `card-gradient` do **NOT** exist in brandkit.css — use Bootstrap's `.card` as base.

---

## 🏷️ Badge Classes

```html
<!-- Success badge -->
<span class="badge-brand-success">Complete</span>

<!-- Primary badge -->
<span class="badge-brand-primary">Active</span>

<!-- Warning badge -->
<span class="badge-brand-warning">Pending</span>
```

---

## 📱 Common Patterns

### Role Selection Card
```css
/* Note: profile-header-gradient, glass-badge, role-card are NOT predefined classes.
   Define them in your app's CSS file using brandkit variables: */
.role-card {
    background: var(--brand-white);
    border: 3px solid var(--brand-grey-200);
    border-radius: var(--brand-radius-lg);
    padding: var(--spacing-xl);
    transition: var(--brand-transition);
}

.role-card:hover {
    border-color: #667eea; /* no CSS variable for purple */
    transform: translateY(-10px);
    box-shadow: 0 10px 40px rgba(102, 126, 234, 0.3);
}
```

### Glassmorphism Effect
```css
.glass-element {
    background: rgba(255, 255, 255, 0.2);
    backdrop-filter: blur(10px);
    border: 1px solid rgba(255, 255, 255, 0.3);
}
```

---

## ✅ Quick Checklist

Before committing styled code:

- [ ] Used CSS variables (no hardcoded colors)
- [ ] No inline `style=""` attributes
- [ ] No `<style>` tags in templates
- [ ] Used spacing system (no random px values)
- [ ] Used predefined components where possible
- [ ] Linked external CSS file in `{% block extra_css %}`
- [ ] Added hover states with transitions
- [ ] Tested responsive design

---

## 📂 File Locations

- **Brand Kit CSS:** `webpages/static/webpages/css/brandkit.css`
- **Components CSS:** `webpages/static/webpages/css/brandkit-components.css`
- **Overrides CSS:** `webpages/static/webpages/css/brandkit-overrides.css`
- **Full Documentation:** `.claude/docs/04-frontend-css/BRAND_KIT_REFERENCE.md`
- **CSS Architecture:** `.claude/docs/04-frontend-css/CSS_JS_ARCHITECTURE.md`
- **Coding Standards:** `.claude/docs/03-architecture/CODING_STANDARDS.md`

---

## 🚫 Common Mistakes to Avoid

```css
/* ❌ DON'T hardcode colors */
.element { background: #667eea; }

/* ✅ DO use brandkit variables where they exist */
.element { background: var(--brand-gradient-purple); }
/* or inline for non-brand gradients */
.element { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); }
```

```html
<!-- ❌ DON'T use inline styles -->
<div style="padding: 20px; background: white;">

<!-- ✅ DO use Bootstrap + BEM classes -->
<div class="card your-bem-class">
```

```css
/* ❌ DON'T use random spacing */
.section { padding: 23px; margin: 17px; }

/* ✅ DO use spacing system */
.section { padding: var(--spacing-xl); margin: var(--spacing-lg); }
```

---

**Remember:** When in doubt, check [BRAND_KIT_REFERENCE.md](BRAND_KIT_REFERENCE.md)

🎨 **Keep it consistent. Keep it beautiful.**
