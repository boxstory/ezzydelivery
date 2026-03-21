# EzzyDelivery Brand Kit Reference

**Version:** 2.1
**Last Updated:** 2026-03-21
**Status:** ✅ Official Design System

---

## 🎨 MANDATORY DESIGN RULE

> **⚠️ CRITICAL: ALL future styling work MUST ONLY use this brand kit reference.**
>
> - ❌ **NEVER** create custom colors, gradients, or spacing values
> - ❌ **NEVER** use inline styles or `<style>` tags in templates
> - ✅ **ALWAYS** reference CSS variables from `brandkit.css` (`webpages/static/webpages/css/brandkit.css`)
> - ✅ **ALWAYS** use predefined components and classes
> - ✅ **ALWAYS** follow the naming conventions defined here

This document is the **single source of truth** for all design decisions in the EzzyDelivery platform.

---

## Table of Contents

1. [Brand Colors](#brand-colors)
2. [Typography](#typography)
3. [Spacing System](#spacing-system)
4. [Shadows & Elevation](#shadows--elevation)
5. [Border Radius](#border-radius)
6. [Gradients](#gradients)
7. [Transitions & Animations](#transitions--animations)
8. [Component Library](#component-library)
9. [Usage Guidelines](#usage-guidelines)
10. [Examples](#examples)

---

## Brand Colors

### Primary Colors

```css
--brand-primary: #f7c000;           /* Ezzy Yellow - Main brand color */
--brand-primary-dark: #f4c20d;      /* Darker yellow for hover states */
--brand-secondary: #fff7d6;         /* Light yellow background */
--brand-accent: #fef9e6;            /* Creamy accent for soft backgrounds */
```

**Usage:**
- **Primary**: Buttons, CTAs, highlights, active states
- **Primary Dark**: Hover states, pressed buttons
- **Secondary**: Background sections, cards with brand identity
- **Accent**: Subtle backgrounds, hover effects

### Neutral Palette

```css
--brand-grey-100: #fafafa;          /* Lightest grey - Page backgrounds */
--brand-grey-200: #f0f0f0;          /* Light grey - Card backgrounds */
--brand-grey-300: #dcdcdc;          /* Medium-light grey - Borders */
--brand-grey-400: #b0b0b0;          /* Medium grey - Disabled states */
--brand-grey-500: #888;             /* Mid grey - Placeholder text */
--brand-grey-600: #555;             /* Dark grey - Secondary text */
--brand-grey-700: #333;             /* Darker grey - Primary text */
--brand-grey-800: #1f1f1f;          /* Darkest grey - Headings */
--brand-white: #ffffff;             /* Pure white */
--brand-black: #000000;             /* Pure black */
```

**Usage:**
- **100-200**: Backgrounds
- **300**: Borders, dividers
- **400-500**: Disabled elements, placeholders
- **600-700**: Text colors
- **800**: Headings, emphasis
- **White/Black**: High contrast elements

### Modern Gradient Colors

> ⚠️ **Note:** `--gradient-purple-primary`, `--gradient-purple-secondary`, `--gradient-green-primary`, `--gradient-green-secondary` and `--brand-gradient-green` are **NOT defined** in `brandkit.css`. Use the gradient values directly or define locally.

```css
/* Purple gradient — use inline value, not a CSS variable */
background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);

/* Green gradient — use inline value, not a CSS variable */
background: linear-gradient(135deg, #10b981 0%, #059669 100%);
```

**Usage:**
- **Purple**: Modern UI elements, profile sections, role selection
- **Green**: Success states, active badges, verification

### Status Colors

```css
--status-success: #10b981;          /* Green - Success states */
--status-warning: #f59e0b;          /* Orange - Warning states */
--status-error: #ef4444;            /* Red - Error states */
--status-info: #3b82f6;             /* Blue - Info states */
--status-pending: #6b7280;          /* Grey - Pending states */
```

**Usage:**
- Order statuses
- Form validation
- Alert messages
- Badges

---

## Typography

### Font Family

```css
--brand-font-primary: "Inter", "Poppins", "Helvetica Neue", sans-serif;
```

**Usage:** All text elements should use this font stack.

### Font Weights

```css
--brand-font-weight-normal: 400;    /* Body text */
--brand-font-weight-medium: 500;    /* Emphasis */
--brand-font-weight-bold: 600;      /* Headings, buttons */
--brand-font-weight-heavy: 700;     /* Major headings */
```

### Font Sizes

```css
--brand-font-size-xs: 0.75rem;      /* 12px - Small labels */
--brand-font-size-sm: 0.875rem;     /* 14px - Secondary text */
--brand-font-size-base: 0.875rem;  /* 15px - Body text */
--brand-font-size-md: 1rem;         /* 16px - Emphasized text */
--brand-font-size-lg: 1.125rem;     /* 18px - Subheadings */
--brand-font-size-xl: 1.25rem;      /* 20px - Section headings */
--brand-font-size-2xl: 1.5rem;      /* 24px - Page headings */
--brand-font-size-3xl: 2rem;        /* 32px - Hero headings */
--brand-font-size-4xl: 2.5rem;      /* 40px - Display headings */
```

### Line Heights

```css
--brand-line-height-tight: 1.2;     /* Headings */
--brand-line-height-normal: 1.5;    /* Body text */
--brand-line-height-relaxed: 1.6;   /* Comfortable reading */
--brand-line-height-loose: 1.8;     /* Very spacious */
```

---

## Spacing System

**Philosophy:** Use consistent spacing for visual harmony.

```css
--spacing-xs: 0.25rem;              /* 4px - Minimal spacing */
--spacing-sm: 0.5rem;               /* 8px - Compact spacing */
--spacing-md: 1rem;                 /* 16px - Standard spacing */
--spacing-lg: 1.5rem;               /* 24px - Comfortable spacing */
--spacing-xl: 2rem;                 /* 32px - Generous spacing */
--spacing-2xl: 2.5rem;              /* 40px - Section spacing */
--spacing-3xl: 2rem;                /* 48px - Large sections */
```

**Usage Guide:**
- **xs**: Icon gaps, tight elements
- **sm**: Button padding, small gaps
- **md**: Card padding, standard gaps
- **lg**: Section padding, comfortable gaps
- **xl**: Page margins, major sections
- **2xl-3xl**: Hero sections, landing pages

---

## Shadows & Elevation

**Philosophy:** Shadows create depth hierarchy.

```css
--brand-shadow-sm: 0 1px 3px rgba(0,0,0,0.08);           /* Subtle - Flat cards */
--brand-shadow-md: 0 4px 8px rgba(0,0,0,0.1);            /* Standard - Cards */
--brand-shadow-lg: 0 10px 20px rgba(0,0,0,0.12);         /* Prominent - Modals */
--brand-shadow-xl: 0 20px 40px rgba(0,0,0,0.15);         /* Deep - Overlays */
--brand-shadow-2xl: 0 25px 50px rgba(0,0,0,0.2);         /* Maximum - Popups */

/* ⚠️ NOTE: --shadow-purple, --shadow-green, --shadow-yellow are NOT defined in brandkit.css
   Use inline values directly if needed: */
/* box-shadow: 0 10px 40px rgba(102, 126, 234, 0.3); */ /* Purple glow */
/* box-shadow: 0 10px 40px rgba(16, 185, 129, 0.3); */  /* Green glow */
/* box-shadow: 0 10px 40px rgba(247, 192, 0, 0.3); */   /* Yellow glow */
```

**Elevation Levels:**
1. **Level 0**: Flat (no shadow)
2. **Level 1**: `shadow-sm` - Static cards
3. **Level 2**: `shadow-md` - Interactive cards
4. **Level 3**: `shadow-lg` - Floating elements
5. **Level 4**: `shadow-xl` - Modals, dropdowns
6. **Level 5**: `shadow-2xl` - Overlays

---

## Border Radius

**Philosophy:** Rounded corners create friendly, modern UI.

```css
--brand-radius-sm: 8px;             /* Subtle rounding - Small elements */
--brand-radius-md: 12px;            /* Standard rounding - Cards */
--brand-radius-lg: 18px;            /* Prominent rounding - Large cards */
--brand-radius-xl: 20px;            /* Very rounded - Feature sections */
--brand-radius-2xl: 24px;           /* Extra rounded - Hero elements */
--brand-radius-full: 50px;          /* Pill shape - Buttons, badges */
--brand-radius-circle: 50%;         /* Perfect circle - Avatars */
```

**Usage Guide:**
- **sm**: Input fields, small buttons
- **md**: Cards, panels
- **lg**: Feature cards, sections
- **xl**: Hero sections
- **full**: Pill buttons, badges
- **circle**: Profile pictures, icons

---

## Gradients

### Brand Gradients

```css
/* Yellow to White - Brand identity */
--brand-gradient-yellow-white: linear-gradient(135deg, var(--brand-primary), var(--brand-white));

/* Black to Grey - Dark mode elements */
--brand-gradient-black-grey: linear-gradient(135deg, var(--brand-black), var(--brand-grey-700));

/* Modern Purple - Primary UI gradient */
--brand-gradient-purple: linear-gradient(135deg, #667eea 0%, #764ba2 100%);

/* Success Green - Positive actions */
--brand-gradient-green: linear-gradient(135deg, #10b981 0%, #059669 100%);

/* Subtle Grey - Backgrounds */
--brand-gradient-grey: linear-gradient(135deg, #f3f4f6 0%, #e5e7eb 100%);
```

### Glassmorphism Effects

```css
/* Glassmorphism background with blur */
background: rgba(255, 255, 255, 0.2);
backdrop-filter: blur(10px);
border: 1px solid rgba(255, 255, 255, 0.3);
```

**Usage:**
- Profile headers
- Overlay panels
- Modern UI elements

---

## Transitions & Animations

### Standard Transitions

```css
--brand-transition: all 0.3s ease;              /* Standard - Most elements */
--brand-transition-fast: all 0.15s ease;        /* Fast - Hover states */
--brand-transition-slow: all 0.5s ease;         /* Slow - Major changes */
```

### Animation Curves

```css
--ease-in-out: cubic-bezier(0.4, 0, 0.2, 1);   /* Smooth start and end */
--ease-out: cubic-bezier(0, 0, 0.2, 1);        /* Smooth deceleration */
--ease-in: cubic-bezier(0.4, 0, 1, 1);         /* Smooth acceleration */
--ease-bounce: cubic-bezier(0.68, -0.55, 0.265, 1.55); /* Bouncy */
```

### Common Animations

```css
/* Hover lift */
.hover-lift:hover {
    transform: translateY(-5px);
    transition: var(--brand-transition);
}

/* Fade in */
@keyframes fadeIn {
    from { opacity: 0; }
    to { opacity: 1; }
}

/* Slide up */
@keyframes slideUp {
    from {
        opacity: 0;
        transform: translateY(20px);
    }
    to {
        opacity: 1;
        transform: translateY(0);
    }
}

/* Scale in */
@keyframes scaleIn {
    from {
        opacity: 0;
        transform: scale(0.9);
    }
    to {
        opacity: 1;
        transform: scale(1);
    }
}
```

---

## Component Library

### Buttons

#### Primary Button
```css
.btn-brand-primary {
    background: var(--brand-gradient-purple);
    color: var(--brand-white);
    padding: var(--spacing-sm) var(--spacing-lg);
    border-radius: var(--brand-radius-full);
    font-weight: var(--brand-font-weight-bold);
    border: none;
    transition: var(--brand-transition);
}

.btn-brand-primary:hover {
    transform: translateY(-2px);
    box-shadow: 0 10px 40px rgba(102, 126, 234, 0.3); /* --shadow-purple not in brandkit.css, use inline */
}
```

#### Secondary Button
```css
.btn-brand-secondary {
    background: var(--brand-white);
    color: var(--gradient-purple-primary);
    padding: var(--spacing-sm) var(--spacing-lg);
    border-radius: var(--brand-radius-full);
    border: 2px solid var(--gradient-purple-primary);
    font-weight: var(--brand-font-weight-bold);
    transition: var(--brand-transition);
}

.btn-brand-secondary:hover {
    background: var(--brand-gradient-purple);
    color: var(--brand-white);
    border-color: transparent;
}
```

#### Outline Button
```css
.btn-brand-outline {
    background: transparent;
    color: var(--brand-grey-700);
    padding: var(--spacing-sm) var(--spacing-lg);
    border-radius: var(--brand-radius-full);
    border: 2px solid var(--brand-grey-300);
    font-weight: var(--brand-font-weight-medium);
    transition: var(--brand-transition);
}

.btn-brand-outline:hover {
    background: var(--brand-grey-100);
    border-color: var(--brand-grey-400);
}
```

### Cards

#### Standard Card
```css
.card-brand {
    background: var(--brand-white);
    border-radius: var(--brand-radius-md);
    padding: var(--spacing-lg);
    box-shadow: var(--brand-shadow-sm);
    border: 1px solid var(--brand-grey-200);
    transition: var(--brand-transition);
}

.card-brand:hover {
    box-shadow: var(--brand-shadow-md);
    transform: translateY(-2px);
}
```

#### Gradient Card
```css
.card-gradient {
    background: var(--brand-gradient-purple);
    color: var(--brand-white);
    border-radius: var(--brand-radius-lg);
    padding: var(--spacing-xl);
    box-shadow: var(--shadow-purple);
    border: none;
}
```

### Badges

```css
.badge-brand-success {
    background: var(--brand-gradient-green);
    color: var(--brand-white);
    padding: 0.25rem 0.75rem;
    border-radius: var(--brand-radius-full);
    font-size: var(--brand-font-size-xs);
    font-weight: var(--brand-font-weight-bold);
}

.badge-brand-primary {
    background: var(--brand-gradient-purple);
    color: var(--brand-white);
    padding: 0.25rem 0.75rem;
    border-radius: var(--brand-radius-full);
    font-size: var(--brand-font-size-xs);
    font-weight: var(--brand-font-weight-bold);
}

.badge-brand-warning {
    background: #fef3c7;
    color: #92400e;
    padding: 0.25rem 0.75rem;
    border-radius: var(--brand-radius-full);
    font-size: var(--brand-font-size-xs);
    font-weight: var(--brand-font-weight-bold);
}
```

### Profile Components

#### Profile Header with Gradient
```css
.profile-header-gradient {
    background: var(--brand-gradient-purple);
    padding: var(--spacing-xl) var(--spacing-lg);
    border-radius: var(--brand-radius-lg) var(--brand-radius-lg) 0 0;
    color: var(--brand-white);
}
```

#### Glassmorphism Badge
```css
.glass-badge {
    background: rgba(255, 255, 255, 0.2);
    backdrop-filter: blur(10px);
    padding: var(--spacing-sm) var(--spacing-md);
    border-radius: var(--brand-radius-full);
    color: var(--brand-white);
    font-size: var(--brand-font-size-sm);
    font-weight: var(--brand-font-weight-bold);
}
```

### Form Elements

```css
.form-control-brand {
    background: var(--brand-white);
    border: 2px solid var(--brand-grey-300);
    border-radius: var(--brand-radius-sm);
    padding: var(--spacing-sm) var(--spacing-md);
    font-size: var(--brand-font-size-base);
    transition: var(--brand-transition);
}

.form-control-brand:focus {
    border-color: var(--gradient-purple-primary);
    box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1);
    outline: none;
}

.form-control-brand:disabled,
.form-control-brand[readonly] {
    background: var(--brand-grey-100);
    cursor: not-allowed;
    opacity: 0.7;
}
```

---

## Usage Guidelines

### ✅ DO's

1. **Always use CSS variables:**
   ```css
   /* ✅ GOOD */
   .my-element {
       background: var(--brand-primary);
       padding: var(--spacing-md);
       border-radius: var(--brand-radius-md);
   }
   ```

2. **Use predefined components:**
   ```html
   <!-- ✅ GOOD -->
   <button class="btn-brand-primary">Click Me</button>
   <div class="card-brand">Content</div>
   ```

3. **Follow spacing system:**
   ```css
   /* ✅ GOOD */
   .section {
       padding: var(--spacing-xl);
       margin-bottom: var(--spacing-lg);
   }
   ```

4. **Use semantic class names:**
   ```html
   <!-- ✅ GOOD -->
   <div class="profile-header">
   <div class="order-status-badge">
   ```

### ❌ DON'Ts

1. **Never hardcode colors:**
   ```css
   /* ❌ BAD */
   .my-element {
       background: #667eea;
       color: #333;
   }
   ```

2. **Never use inline styles:**
   ```html
   <!-- ❌ BAD -->
   <div style="padding: 20px; background: white;">
   ```

3. **Never use `<style>` tags in templates:**
   ```html
   <!-- ❌ BAD -->
   <style>
       .my-class { background: white; }
   </style>
   ```

4. **Never create random spacing:**
   ```css
   /* ❌ BAD */
   .element {
       padding: 17px;
       margin: 23px;
   }
   ```

---

## Examples

### Example 1: Modern Profile Card

```html
<div class="card-brand">
    <div class="profile-header-gradient">
        <div class="glass-badge">
            <i class="fas fa-check-circle me-1"></i> Verified
        </div>
        <h3 style="color: var(--brand-white); margin-top: var(--spacing-md);">
            John Doe
        </h3>
        <p style="color: rgba(255,255,255,0.9);">EZZY2025123456</p>
    </div>
    <div style="padding: var(--spacing-lg);">
        <p>Profile content here...</p>
        <button class="btn-brand-primary">
            <i class="fas fa-tachometer-alt me-2"></i>
            Go to Dashboard
        </button>
    </div>
</div>
```

### Example 2: Role Selection Card

```css
/* In external CSS file */
.role-card {
    background: var(--brand-white);
    border: 3px solid var(--brand-grey-200);
    border-radius: var(--brand-radius-lg);
    padding: var(--spacing-xl) var(--spacing-lg);
    text-align: center;
    transition: var(--brand-transition);
    cursor: pointer;
}

.role-card:hover {
    border-color: var(--gradient-purple-primary);
    transform: translateY(-10px);
    box-shadow: var(--shadow-purple);
}

.role-card-icon {
    width: 100px;
    height: 100px;
    margin: 0 auto var(--spacing-lg);
    background: var(--brand-gradient-grey);
    border-radius: var(--brand-radius-circle);
    display: flex;
    align-items: center;
    justify-content: center;
    transition: var(--brand-transition);
}

.role-card:hover .role-card-icon {
    background: var(--brand-gradient-purple);
    transform: scale(1.1);
}

.role-card:hover .role-card-icon i {
    color: var(--brand-white);
}
```

```html
<a href="/register/business/" class="role-card">
    <div class="role-card-icon">
        <i class="fas fa-building fa-3x"></i>
    </div>
    <h3>Business Admin</h3>
    <p>Manage your delivery operations</p>
    <button class="btn-brand-primary">
        Register as Business
    </button>
</a>
```

### Example 3: Status Badge System

```html
<!-- Success -->
<span class="badge-brand-success">
    <i class="fas fa-check me-1"></i> Complete
</span>

<!-- Active Role -->
<span class="badge-brand-primary">
    <i class="fas fa-star me-1"></i> Active Role
</span>

<!-- Pending -->
<span class="badge-brand-warning">
    <i class="fas fa-clock me-1"></i> Pending
</span>
```

---

## Responsive Design

### Breakpoints

```css
--breakpoint-xs: 0px;       /* Extra small devices */
--breakpoint-sm: 576px;     /* Small devices (phones) */
--breakpoint-md: 768px;     /* Medium devices (tablets) */
--breakpoint-lg: 992px;     /* Large devices (desktops) */
--breakpoint-xl: 1200px;    /* Extra large devices */
--breakpoint-2xl: 1400px;   /* XXL devices */
```

### Mobile-First Approach

```css
/* Base styles for mobile */
.element {
    padding: var(--spacing-md);
    font-size: var(--brand-font-size-base);
}

/* Tablet and up */
@media (min-width: 768px) {
    .element {
        padding: var(--spacing-lg);
        font-size: var(--brand-font-size-md);
    }
}

/* Desktop and up */
@media (min-width: 992px) {
    .element {
        padding: var(--spacing-xl);
        font-size: var(--brand-font-size-lg);
    }
}
```

---

## File Organization

### Where to Place Styles

```
app_name/
├── static/
│   └── app_name/
│       └── css/
│           ├── components.css    # Reusable components
│           ├── pages.css          # Page-specific styles
│           └── utilities.css      # Helper classes
```

### How to Link Styles

```html
{% extends "base.html" %}
{% load static %}

{% block extra_css %}
<link href="{% static 'app_name/css/components.css' %}" rel="stylesheet" />
{% endblock extra_css %}
```

---

## Checklist for New Components

Before creating any new UI component, verify:

- [ ] Uses CSS variables from brandkit.css
- [ ] No hardcoded colors or spacing
- [ ] No inline styles or `<style>` tags
- [ ] Follows naming conventions
- [ ] Uses semantic class names
- [ ] Responsive design implemented
- [ ] Hover states defined
- [ ] Accessibility considered
- [ ] Documented in component library (if reusable)

---

## Support & Questions

**For Questions:**
1. Check this document first
2. Review `docs/CSS_JS_ARCHITECTURE.md`
3. Check `docs/CODING_STANDARDS.md`
4. Consult the development team

**For Updates:**
- All changes to brand kit must be documented here
- Update version number when making changes
- Notify team of breaking changes

---

## Version History

- **v2.0** (2025-11-20): Added modern gradients, glassmorphism, comprehensive component library
- **v1.0** (2025-11-13): Initial brand kit with yellow theme

---

**Remember:** This brand kit is the LAW for all styling decisions. When in doubt, refer to this document. Consistency is key to a professional, polished application.

🎨 **EzzyDelivery Brand Kit - Building Beautiful, Consistent Interfaces**
