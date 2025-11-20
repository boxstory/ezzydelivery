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

### Modern Gradients
```css
--brand-gradient-purple: linear-gradient(135deg, #667eea 0%, #764ba2 100%)  /* 💜 Purple */
--brand-gradient-green: linear-gradient(135deg, #10b981 0%, #059669 100%)   /* 💚 Green */
--brand-gradient-yellow-white: linear-gradient(135deg, #f7c000, #ffffff)    /* 🟡 Yellow */
```

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

/* Special colored shadows */
--shadow-purple: 0 10px 40px rgba(102, 126, 234, 0.3)   /* Purple glow */
--shadow-green: 0 10px 40px rgba(16, 185, 129, 0.3)     /* Green glow */
```

---

## 🔘 Button Classes

```html
<!-- Primary gradient button -->
<button class="btn-brand-primary">Submit</button>

<!-- Secondary outline button -->
<button class="btn-brand-secondary">Cancel</button>

<!-- Outline button -->
<button class="btn-brand-outline">Learn More</button>
```

---

## 🎴 Card Classes

```html
<!-- Standard card -->
<div class="card-brand">Content</div>

<!-- Gradient card -->
<div class="card-gradient">Featured content</div>
```

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

### Profile Header with Gradient
```html
<div class="profile-header-gradient">
    <div class="glass-badge">
        <i class="fas fa-check-circle"></i> Verified
    </div>
    <h3 style="color: var(--brand-white);">User Name</h3>
</div>
```

### Role Selection Card
```css
.role-card {
    background: var(--brand-white);
    border: 3px solid var(--brand-grey-200);
    border-radius: var(--brand-radius-lg);
    padding: var(--spacing-xl);
    transition: var(--brand-transition);
}

.role-card:hover {
    border-color: var(--gradient-purple-primary);
    transform: translateY(-10px);
    box-shadow: var(--shadow-purple);
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

- **Brand Kit CSS:** `static/webpages/css/brand-kit.css`
- **Full Documentation:** `docs/BRAND_KIT_REFERENCE.md`
- **CSS Architecture:** `docs/CSS_JS_ARCHITECTURE.md`
- **Coding Standards:** `docs/CODING_STANDARDS.md`

---

## 🚫 Common Mistakes to Avoid

```css
/* ❌ DON'T hardcode colors */
.element { background: #667eea; }

/* ✅ DO use variables */
.element { background: var(--gradient-purple-primary); }
```

```html
<!-- ❌ DON'T use inline styles -->
<div style="padding: 20px; background: white;">

<!-- ✅ DO use classes -->
<div class="card-brand">
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
