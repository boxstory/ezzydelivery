# Frontend Designer Skill - EzzyDelivery

Use this skill when designing UI components, creating landing pages, or building polished frontend interfaces with modern design principles.

**Complements:** `frontend.md` skill (Bootstrap, HTMX, jQuery implementation)
**Focus:** Visual design, brand consistency, modern UI patterns, aesthetics

---

## Brand Identity

### EzzyDelivery Brand Kit
**Location:** `webpages/static/webpages/css/brandkit.css` (imports all modules)

**Module Files:**
- `brandkit-tokens.css` - CSS Custom Properties (design tokens)
- `brandkit-typography.css` - Font styles and heading variants
- `brandkit-components.css` - Buttons, cards, alerts, badges, forms
- `brandkit-utilities.css` - Helper classes for spacing, colors, display
- `brandkit-overrides.css` - Bootstrap overrides (loads last)

#### Core Brand Colors
```css
/* Primary Brand Colors */
--brand-primary: #f7c000         /* Ezzy Yellow - Main brand color */
--brand-primary-dark: #f4c20d    /* Darker yellow for hovers */
--brand-secondary: #fff7d6       /* Light yellow background */
--brand-accent: #fef9e6          /* Accent yellow */
--brand-navy: #001f3f            /* Navy blue for contrast */
--brand-navy-light: #003366      /* Light navy */
--brand-black: #000000           /* Pure black */

/* Neutral Palette */
--brand-grey-100: #fafafa        /* Lightest grey */
--brand-grey-200: #f0f0f0
--brand-grey-300: #dcdcdc
--brand-grey-400: #b0b0b0
--brand-grey-500: #6c757d        /* Medium grey (WCAG AA compliant) */
--brand-grey-600: #555
--brand-grey-700: #333
--brand-grey-800: #1f1f1f        /* Dark grey */
--brand-white: #ffffff           /* Pure white */

/* Gradients */
--brand-gradient-yellow-white: linear-gradient(135deg, var(--brand-primary), var(--brand-white));
--brand-gradient-black-grey: linear-gradient(135deg, var(--brand-black), var(--brand-grey-700));
--brand-gradient-black-navy: linear-gradient(135deg, var(--brand-black), var(--brand-navy-light));
--brand-gradient-purple: linear-gradient(135deg, var(--brand-primary), var(--brand-primary-dark));
--brand-gradient-navy: linear-gradient(135deg, var(--brand-navy), var(--brand-navy-light));
--brand-gradient-yellow-dark: linear-gradient(135deg, var(--brand-primary), var(--brand-grey-800));
```

#### Typography Scale
```css
/* Font Families */
--brand-font-primary: "Inter", "Poppins", "Helvetica Neue", sans-serif;

/* Font Sizes (rem-based) */
--brand-font-size-base: 0.9375rem   /* 15px base */
--brand-font-size-heading: 1.25rem  /* 20px headings */

/* Standard scale */
--text-xs: 0.75rem      /* 12px */
--text-sm: 0.875rem     /* 14px */
--text-base: 0.9375rem  /* 15px (brand default) */
--text-lg: 1.125rem     /* 18px */
--text-xl: 1.25rem      /* 20px */
--text-2xl: 1.5rem      /* 24px */
--text-3xl: 1.875rem    /* 30px */
--text-4xl: 2.25rem     /* 36px */
--text-5xl: 3rem        /* 48px */

/* Font Weights */
--brand-font-weight-normal: 400
--brand-font-weight-bold: 600
```

#### Spacing System
```css
/* Consistent spacing scale (rem-based) */
--spacing-xs: 0.25rem    /* 4px */
--spacing-sm: 0.5rem     /* 8px */
--spacing-md: 1rem       /* 16px */
--spacing-lg: 1.5rem     /* 24px */
--spacing-xl: 2rem       /* 32px */
```

#### Border Radius
```css
--brand-radius-sm: 0.5rem      /* 8px - subtle rounding */
--brand-radius-md: 0.75rem     /* 12px - standard cards */
--brand-radius-lg: 1.125rem    /* 18px - prominent cards */
```

#### Shadows
```css
--brand-shadow-sm: 0 0.0625rem 0.1875rem rgba(0,0,0,0.08);
--brand-shadow-md: 0 0.25rem 0.5rem rgba(0,0,0,0.1);
--brand-shadow-lg: 0 0.625rem 1.25rem rgba(0,0,0,0.12);
```

#### Transitions
```css
--brand-transition: all 0.3s ease;
```

## Design Principles

### 1. Mobile-First Responsive Design
Always design for mobile first, then enhance for larger screens.

```css
/* Mobile base styles (default) */
.component {
  padding: var(--spacing-md);
  font-size: var(--text-base);
}

/* Tablet (768px+) */
@media (min-width: 768px) {
  .component {
    padding: var(--spacing-lg);
    font-size: var(--text-lg);
  }
}

/* Desktop (1024px+) */
@media (min-width: 1024px) {
  .component {
    padding: var(--spacing-xl);
  }
}
```

### 2. Consistent Component Patterns

#### Card Component Pattern
```html
<div class="card">
  <div class="card-header">
    <h3 class="card-title">Title</h3>
    <p class="card-subtitle">Subtitle</p>
  </div>
  <div class="card-body">
    <!-- Content -->
  </div>
  <div class="card-footer">
    <button class="btn btn-primary">Action</button>
  </div>
</div>
```

```css
.card {
  background: var(--brand-white);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-md);
  overflow: hidden;
  transition: transform 0.2s ease, box-shadow 0.2s ease;
}

.card:hover {
  transform: translateY(-2px);
  box-shadow: var(--shadow-lg);
}

.card-header {
  padding: var(--spacing-lg);
  border-bottom: 1px solid var(--brand-light);
}

.card-title {
  font-size: var(--text-xl);
  font-weight: var(--font-bold);
  color: var(--brand-dark);
  margin: 0;
}

.card-subtitle {
  font-size: var(--text-sm);
  color: var(--brand-gray);
  margin-top: var(--spacing-xs);
}

.card-body {
  padding: var(--spacing-lg);
}

.card-footer {
  padding: var(--spacing-lg);
  border-top: 1px solid var(--brand-light);
  background: var(--brand-light);
}
```

#### Button Component Pattern
```html
<!-- Primary button -->
<button class="btn btn-primary">
  <i class="fa-solid fa-check"></i> Confirm
</button>

<!-- Secondary button -->
<button class="btn btn-secondary">Cancel</button>

<!-- Outline button -->
<button class="btn btn-outline">Details</button>

<!-- Sizes -->
<button class="btn btn-primary btn-sm">Small</button>
<button class="btn btn-primary">Medium (default)</button>
<button class="btn btn-primary btn-lg">Large</button>
```

```css
.btn {
  display: inline-flex;
  align-items: center;
  gap: var(--spacing-sm);
  padding: var(--spacing-sm) var(--spacing-lg);
  font-size: var(--text-base);
  font-weight: var(--font-medium);
  border-radius: var(--radius-md);
  border: 2px solid transparent;
  cursor: pointer;
  transition: all 0.2s ease;
  text-decoration: none;
}

.btn-primary {
  background: var(--brand-primary);
  color: var(--brand-white);
}

.btn-primary:hover {
  background: var(--brand-primary-dark);
  transform: translateY(-1px);
  box-shadow: var(--shadow-md);
}

.btn-secondary {
  background: var(--brand-gray);
  color: var(--brand-white);
}

.btn-outline {
  background: transparent;
  border-color: var(--brand-primary);
  color: var(--brand-primary);
}

.btn-outline:hover {
  background: var(--brand-primary);
  color: var(--brand-white);
}

/* Sizes */
.btn-sm {
  padding: var(--spacing-xs) var(--spacing-md);
  font-size: var(--text-sm);
}

.btn-lg {
  padding: var(--spacing-md) var(--spacing-xl);
  font-size: var(--text-lg);
}
```

### 3. Modern UI Patterns

#### Glass Morphism Effect
```css
.glass-card {
  background: rgba(255, 255, 255, 0.7);
  backdrop-filter: blur(10px);
  -webkit-backdrop-filter: blur(10px);
  border: 1px solid rgba(255, 255, 255, 0.3);
  box-shadow: var(--shadow-lg);
}
```

#### Gradient Backgrounds
```css
.gradient-primary {
  background: linear-gradient(135deg, #6366F1 0%, #EC4899 100%);
}

.gradient-success {
  background: linear-gradient(135deg, #10B981 0%, #3B82F6 100%);
}

.gradient-sunset {
  background: linear-gradient(135deg, #F59E0B 0%, #EF4444 100%);
}
```

#### Smooth Animations
```css
/* Fade in */
@keyframes fadeIn {
  from {
    opacity: 0;
    transform: translateY(10px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.fade-in {
  animation: fadeIn 0.3s ease-in-out;
}

/* Slide in from right */
@keyframes slideInRight {
  from {
    transform: translateX(100%);
    opacity: 0;
  }
  to {
    transform: translateX(0);
    opacity: 1;
  }
}

.slide-in-right {
  animation: slideInRight 0.4s ease-out;
}
```

### 4. Accessibility Standards

#### Focus States
```css
.btn:focus,
.input:focus {
  outline: 2px solid var(--brand-primary);
  outline-offset: 2px;
}

/* Skip visible focus ring, but keep for keyboard navigation */
.btn:focus:not(:focus-visible) {
  outline: none;
}
```

#### Color Contrast
- Ensure minimum 4.5:1 contrast ratio for normal text
- Ensure minimum 3:1 contrast ratio for large text (18px+)
- Use tools like WebAIM Color Contrast Checker

#### Semantic HTML
```html
<!-- Good: Semantic structure -->
<header>
  <nav>
    <ul>
      <li><a href="/">Home</a></li>
    </ul>
  </nav>
</header>

<main>
  <article>
    <h1>Page Title</h1>
    <section>
      <h2>Section Heading</h2>
    </section>
  </article>
</main>

<footer>
  <!-- Footer content -->
</footer>

<!-- Bad: Non-semantic divs -->
<div class="header">
  <div class="nav">...</div>
</div>
```

## Component Templates

### Hero Section
```html
<section class="hero gradient-primary">
  <div class="container">
    <div class="hero-content">
      <h1 class="hero-title">
        Fast, Reliable Delivery Across Qatar
      </h1>
      <p class="hero-subtitle">
        Same-day delivery, COD support, and real-time tracking for your business
      </p>
      <div class="hero-actions">
        <a href="/signup/" class="btn btn-lg btn-white">
          <i class="fa-solid fa-rocket"></i> Get Started Free
        </a>
        <a href="/contact/" class="btn btn-lg btn-outline-white">
          <i class="fa-solid fa-phone"></i> Contact Sales
        </a>
      </div>
    </div>
    <div class="hero-image">
      <img src="hero-delivery.svg" alt="Delivery illustration">
    </div>
  </div>
</section>
```

```css
.hero {
  padding: var(--spacing-3xl) 0;
  color: var(--brand-white);
  overflow: hidden;
}

.hero-content {
  max-width: 600px;
  margin: 0 auto;
  text-align: center;
}

.hero-title {
  font-size: var(--text-5xl);
  font-weight: var(--font-extrabold);
  line-height: 1.2;
  margin-bottom: var(--spacing-lg);
}

.hero-subtitle {
  font-size: var(--text-xl);
  opacity: 0.9;
  margin-bottom: var(--spacing-2xl);
}

.hero-actions {
  display: flex;
  gap: var(--spacing-md);
  justify-content: center;
  flex-wrap: wrap;
}

.btn-white {
  background: var(--brand-white);
  color: var(--brand-primary);
}

.btn-outline-white {
  border-color: var(--brand-white);
  color: var(--brand-white);
  background: transparent;
}

.btn-outline-white:hover {
  background: var(--brand-white);
  color: var(--brand-primary);
}

@media (min-width: 768px) {
  .hero-title {
    font-size: 4rem;
  }
}
```

### Feature Grid
```html
<section class="features">
  <div class="container">
    <h2 class="section-title">Why Choose EzzyDelivery?</h2>
    <div class="feature-grid">

      <div class="feature-card">
        <div class="feature-icon">
          <i class="fa-solid fa-bolt"></i>
        </div>
        <h3 class="feature-title">Lightning Fast</h3>
        <p class="feature-description">
          Same-day delivery across all Qatar zones
        </p>
      </div>

      <div class="feature-card">
        <div class="feature-icon">
          <i class="fa-solid fa-shield-halved"></i>
        </div>
        <h3 class="feature-title">Secure COD</h3>
        <p class="feature-description">
          Safe cash collection with weekly settlements
        </p>
      </div>

      <div class="feature-card">
        <div class="feature-icon">
          <i class="fa-solid fa-chart-line"></i>
        </div>
        <h3 class="feature-title">Real-Time Tracking</h3>
        <p class="feature-description">
          Monitor every delivery with live GPS updates
        </p>
      </div>

    </div>
  </div>
</section>
```

```css
.features {
  padding: var(--spacing-3xl) 0;
  background: var(--brand-light);
}

.section-title {
  font-size: var(--text-4xl);
  font-weight: var(--font-bold);
  text-align: center;
  margin-bottom: var(--spacing-2xl);
  color: var(--brand-dark);
}

.feature-grid {
  display: grid;
  grid-template-columns: 1fr;
  gap: var(--spacing-xl);
}

@media (min-width: 768px) {
  .feature-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}

@media (min-width: 1024px) {
  .feature-grid {
    grid-template-columns: repeat(3, 1fr);
  }
}

.feature-card {
  background: var(--brand-white);
  padding: var(--spacing-xl);
  border-radius: var(--radius-lg);
  text-align: center;
  transition: transform 0.3s ease, box-shadow 0.3s ease;
}

.feature-card:hover {
  transform: translateY(-5px);
  box-shadow: var(--shadow-xl);
}

.feature-icon {
  width: 64px;
  height: 64px;
  margin: 0 auto var(--spacing-lg);
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, var(--brand-primary), var(--brand-secondary));
  color: var(--brand-white);
  border-radius: var(--radius-full);
  font-size: var(--text-2xl);
}

.feature-title {
  font-size: var(--text-xl);
  font-weight: var(--font-bold);
  color: var(--brand-dark);
  margin-bottom: var(--spacing-sm);
}

.feature-description {
  color: var(--brand-gray);
  font-size: var(--text-base);
}
```

## Design Workflow

### 1. Component Planning
- Define component purpose and user interaction
- List all states (default, hover, active, disabled, error)
- Consider mobile, tablet, desktop layouts
- Plan accessibility features

### 2. CSS Architecture
**File Organization:**
```
static/
├── webpages/css/
│   ├── brand-kit.css          # CSS variables only
│   ├── shared/
│   │   ├── shared-base.css    # Typography, utilities
│   │   ├── shared-components.css  # Buttons, cards
│   │   └── shared-layout.css  # Grid, containers
│   └── pages/
│       ├── homepage.css
│       └── services.css
```

### 3. Template Structure
```html
{% extends "base.html" %}
{% load static %}

{% block title %}Page Title - Ezzy Delivery{% endblock %}

{% block extra_css %}
<link href="{% static 'webpages/css/pages/homepage.css' %}" rel="stylesheet">
{% endblock %}

{% block content %}
<!-- Page content -->
{% endblock %}

{% block extra_js %}
<script src="{% static 'webpages/js/homepage.js' %}"></script>
{% endblock %}
```

## Performance Optimization

### CSS Best Practices
```css
/* Use CSS variables for theming */
:root {
  --primary-color: #6366F1;
}

/* Avoid expensive properties in animations */
/* Good: Use transform and opacity */
.animate {
  transform: translateX(100px);
  opacity: 0.5;
}

/* Bad: Avoid animating layout properties */
.animate-bad {
  margin-left: 100px;  /* Forces layout recalculation */
  width: 50%;          /* Forces layout recalculation */
}

/* Use will-change for heavy animations */
.heavy-animation {
  will-change: transform, opacity;
}
```

### Image Optimization
- Use WebP format with JPG/PNG fallbacks
- Implement lazy loading: `loading="lazy"`
- Use appropriate sizes with `srcset`
- Compress images before upload

## Tools & Resources

### Design Tools
- **Figma** - UI design and prototyping
- **Coolors.co** - Color palette generation
- **Google Fonts** - Typography selection
- **Font Awesome** - Icon library (already integrated)

### Development Tools
- **Chrome DevTools** - Inspect and debug
- **Lighthouse** - Performance auditing
- **WAVE** - Accessibility checker
- **BrowserStack** - Cross-browser testing

### CSS Utilities
```css
/* Text utilities */
.text-center { text-align: center; }
.text-bold { font-weight: var(--font-bold); }
.text-muted { color: var(--brand-gray); }

/* Spacing utilities */
.mt-1 { margin-top: var(--spacing-sm); }
.mb-2 { margin-bottom: var(--spacing-md); }
.p-3 { padding: var(--spacing-lg); }

/* Display utilities */
.d-flex { display: flex; }
.d-grid { display: grid; }
.d-none { display: none; }

/* Responsive utilities */
@media (max-width: 767px) {
  .d-md-none { display: none; }
}
```

## Checklist for New Components

- [ ] Mobile-first responsive design
- [ ] Uses brand kit CSS variables
- [ ] No inline styles or `<style>` tags
- [ ] Proper semantic HTML
- [ ] Accessible (ARIA labels, focus states)
- [ ] Consistent naming: `{app}_{section}_{element}_{descriptor}`
- [ ] Hover/focus/active states defined
- [ ] Cross-browser tested
- [ ] Performance optimized
- [ ] Documented in component library

## CSS Units: px to rem Conversion

**Rule:** All CSS pixel values must be converted to rem units for better accessibility and responsive scaling.

### Conversion Formula
```
rem = px / 16
```

Base font size is 16px, so:
- 1px = 0.0625rem
- 2px = 0.125rem
- 4px = 0.25rem
- 8px = 0.5rem
- 10px = 0.625rem
- **12px = 0.75rem** ⭐ (Standard project font size)
- 14px = 0.875rem
- 16px = 1rem
- 18px = 1.125rem
- 20px = 1.25rem
- 24px = 1.5rem
- 28px = 1.75rem
- 32px = 2rem
- 36px = 2.25rem
- 40px = 2.5rem
- 48px = 3rem
- 64px = 4rem

### Exceptions (Keep as px)
- `1px` borders (hairline borders)
- Media query breakpoints (e.g., `@media (max-width: 768px)`)
- Box shadows (small px values for precise control)
- `border-width` when 1-2px

### Why rem?
1. **Accessibility**: Users can adjust browser font size, and rem scales with it
2. **Consistency**: All sizes relative to root font size
3. **Responsive**: Easier to scale entire design by changing root font size
4. **Best Practice**: Modern CSS standard for sizing

### Example Conversion
```css
/* Before (px) */
.button {
  padding: 12px 24px;
  font-size: 16px;
  border-radius: 8px;
  margin-bottom: 16px;
}

/* After (rem) */
.button {
  padding: 0.75rem 1.5rem;
  font-size: 1rem;
  border-radius: 0.5rem;
  margin-bottom: 1rem;
}
```

## Font Size Standardization

**Standard:** All UI text uses `.75rem` (12px) for consistent, compact typography

**See:** `.claude/skills/css-font-standardization.md` for complete standardization process

**Quick Reference:**
- All text elements (p, span): `.75rem`
- All form elements (label, input, select, textarea): `.75rem`
- All tables (th, td): `.75rem`
- All cards and buttons: `.75rem`
- Headings and display text: 1rem+ (preserved)

**Updated Files:** business.css, orders.css, fleet.css, core.css, workforce.css, warehouse.css, delivery.css

## Modern UI Patterns (2026)

### Compact List Design
**Pattern:** Collapsible card-based lists with expandable sections

**Use For:** Long lists (warehouses, products, requests) where vertical space is critical

**Example:** `workforce/templates/workforce/warehouses_list.html`

```html
<!-- Compact Collapsible Card -->
<div class="wh-card">
  <!-- Clickable Header (one-line summary) -->
  <div class="wh-card-header" onclick="toggleDetails(id)">
    <div class="wh-info">
      <div class="wh-name">
        <i class="fa-solid fa-icon"></i>
        Item Name
        <span class="wh-tag">Badge</span>
      </div>
      <div class="wh-meta">
        <span>Code</span>
        <span>Location</span>
        <span class="wh-badge">Status</span>
      </div>
    </div>
    <div class="wh-actions">
      <span class="wh-count">5 items</span>
      <button class="wh-btn">Action</button>
      <i class="fa-solid fa-chevron-down wh-expand-icon"></i>
    </div>
  </div>

  <!-- Collapsible Content (hidden by default) -->
  <div class="wh-details" style="display: none;">
    <!-- Details content -->
  </div>
</div>
```

```css
.wh-card {
  background: var(--brand-white);
  border: 1px solid var(--brand-grey-200);
  border-radius: var(--brand-radius-md);
  margin-bottom: 0.75rem;
}

.wh-card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 1rem 1.25rem;
  cursor: pointer;
  transition: var(--brand-transition);
}

.wh-card-header:hover {
  background: var(--brand-grey-50);
}

.wh-expand-icon {
  transition: transform 0.3s ease;
}

.wh-expand-icon.rotated {
  transform: rotate(180deg);
}
```

### Status Badges System
**Pattern:** Color-coded status indicators with icons

**Colors:**
- Warning (yellow): Pending/review states
- Info (blue): Approved/in-progress states
- Success (green): Completed/active states
- Danger (red): Cancelled/error states
- Neutral (grey): Inactive/default states

```html
<span class="status-badge status-badge--warning">
  <i class="fa-solid fa-clock"></i>
  Pending
</span>

<span class="status-badge status-badge--info">
  <i class="fa-solid fa-circle-check"></i>
  Approved
</span>

<span class="status-badge status-badge--success">
  <i class="fa-solid fa-box-check"></i>
  Completed
</span>
```

```css
.status-badge {
  display: inline-flex;
  align-items: center;
  gap: 0.375rem;
  padding: 0.375rem 0.75rem;
  border-radius: var(--brand-radius-sm);
  font-size: 0.8125rem;
  font-weight: 600;
}

.status-badge--warning {
  background: rgba(255, 193, 7, 0.15);
  color: var(--brand-warning);
}

.status-badge--info {
  background: rgba(13, 110, 253, 0.15);
  color: var(--brand-info);
}

.status-badge--success {
  background: rgba(25, 135, 84, 0.15);
  color: var(--brand-success);
}

.status-badge--danger {
  background: rgba(220, 53, 69, 0.15);
  color: var(--brand-danger);
}

.status-badge--neutral {
  background: var(--brand-grey-100);
  color: var(--brand-grey-600);
}
```

### Stat Cards Grid
**Pattern:** Dashboard statistics with icons and values

**Example:** `business/templates/business/inbound_requests_list.html`

```html
<div class="stats-grid">
  <div class="stat-card stat-card--warning">
    <div class="stat-card__icon">
      <i class="fa-solid fa-clock"></i>
    </div>
    <div class="stat-card__content">
      <p class="stat-card__label">Pending Review</p>
      <h3 class="stat-card__value">12</h3>
    </div>
  </div>
</div>
```

```css
.stats-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
  gap: 1.25rem;
  margin-bottom: 2rem;
}

.stat-card {
  background: var(--brand-white);
  border: 1px solid var(--brand-grey-200);
  border-radius: var(--brand-radius-lg);
  padding: 1.5rem;
  display: flex;
  align-items: center;
  gap: 1.25rem;
}

.stat-card__icon {
  width: 56px;
  height: 56px;
  border-radius: var(--brand-radius-md);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 1.5rem;
}

.stat-card--warning .stat-card__icon {
  background: rgba(255, 193, 7, 0.15);
  color: var(--brand-warning);
}

.stat-card__value {
  font-size: 2rem;
  font-weight: 700;
  color: var(--brand-grey-800);
  margin: 0;
}
```

### Table Design with No Headers
**Pattern:** Minimal table layout for compact lists

```html
<table class="wh-table">
  <tbody>
    <tr>
      <td class="wh-table-business">
        <i class="fa-solid fa-store"></i>
        <div>
          <div class="wh-business-name">Business Name</div>
          <div class="wh-business-code">BIZ123</div>
        </div>
      </td>
      <td class="wh-table-status">
        <span class="wh-badge">Active</span>
      </td>
      <td class="wh-table-actions">
        <button class="wh-icon-btn"><i class="fa-solid fa-eye"></i></button>
      </td>
    </tr>
  </tbody>
</table>
```

```css
.wh-table {
  width: 100%;
  border-collapse: collapse;
}

.wh-table tbody tr {
  border-bottom: 1px solid var(--brand-grey-200);
  transition: var(--brand-transition);
}

.wh-table tbody tr:hover {
  background: var(--brand-grey-50);
}

.wh-table td {
  padding: 0.875rem 1.25rem;
  vertical-align: middle;
}

.wh-table-business {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.wh-business-name {
  font-weight: 600;
  color: var(--brand-grey-800);
}

.wh-business-code {
  font-size: 0.8125rem;
  color: var(--brand-grey-600);
  font-family: "JetBrains Mono", monospace;
}
```

### Icon Button Pattern
**Pattern:** Small icon-only action buttons

```html
<button class="btn-icon btn-icon--view" title="View Details">
  <i class="fa-solid fa-eye"></i>
</button>

<button class="btn-icon btn-icon--edit" title="Edit">
  <i class="fa-solid fa-pen"></i>
</button>

<button class="btn-icon btn-icon--delete" title="Delete">
  <i class="fa-solid fa-trash"></i>
</button>
```

```css
.btn-icon {
  width: 32px;
  height: 32px;
  border-radius: var(--brand-radius-sm);
  border: 1px solid var(--brand-grey-300);
  background: var(--brand-white);
  color: var(--brand-grey-600);
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: var(--brand-transition);
}

.btn-icon:hover {
  background: var(--brand-grey-50);
}

.btn-icon--view:hover {
  background: var(--brand-info);
  color: var(--brand-white);
  border-color: var(--brand-info);
}

.btn-icon--edit:hover {
  background: var(--brand-primary);
  color: var(--brand-grey-800);
  border-color: var(--brand-primary);
}

.btn-icon--delete:hover {
  background: var(--brand-danger);
  color: var(--brand-white);
  border-color: var(--brand-danger);
}
```

### Inline Filters
**Pattern:** Compact horizontal filter bar

```html
<div class="wh-filters-compact">
  <form method="GET" class="wh-filters-form">
    <div class="wh-filters-row">
      <input type="text" class="wh-search-input" placeholder="Search...">
      <select class="wh-filter-select">
        <option>All Status</option>
        <option>Active</option>
      </select>
      <button type="submit" class="wh-btn wh-btn--primary">
        <i class="fa-solid fa-search"></i>
      </button>
    </div>
  </form>
</div>
```

```css
.wh-filters-compact {
  background: var(--brand-white);
  border: 1px solid var(--brand-grey-200);
  border-radius: var(--brand-radius-md);
  padding: 1rem;
  margin-bottom: 1rem;
}

.wh-filters-row {
  display: flex;
  gap: 0.75rem;
  align-items: center;
}

.wh-search-input {
  flex: 1;
  padding: 0.5rem 0.875rem;
  border: 1px solid var(--brand-grey-300);
  border-radius: var(--brand-radius-sm);
  font-size: 0.875rem;
}

.wh-filter-select {
  padding: 0.5rem 0.875rem;
  border: 1px solid var(--brand-grey-300);
  border-radius: var(--brand-radius-sm);
  font-size: 0.875rem;
  min-width: 140px;
}
```

### Empty States
**Pattern:** User-friendly empty state messaging

```html
<div class="empty-state">
  <i class="fa-solid fa-inbox"></i>
  <p class="empty-state__title">No items found</p>
  <p class="empty-state__text">Get started by creating your first item</p>
  <a href="#" class="btn-action btn-action--primary">
    <i class="fa-solid fa-plus"></i>
    Create First Item
  </a>
</div>
```

```css
.empty-state {
  text-align: center;
  padding: 4rem 2rem;
  background: var(--brand-white);
  border: 1px solid var(--brand-grey-200);
  border-radius: var(--brand-radius-md);
}

.empty-state i {
  font-size: 4rem;
  color: var(--brand-grey-300);
  margin-bottom: 1.25rem;
  display: block;
}

.empty-state__title {
  font-size: 1.125rem;
  font-weight: 600;
  color: var(--brand-grey-700);
  margin: 0 0 0.5rem;
}

.empty-state__text {
  font-size: 0.9375rem;
  color: var(--brand-grey-500);
  margin: 0 0 1.5rem;
}
```

## BEM Naming Convention

**Pattern:** `{component}__{element}--{modifier}`

**Examples:**
- `.stat-card` (component)
- `.stat-card__icon` (element)
- `.stat-card--warning` (modifier)
- `.btn-icon--view` (modifier)

**Element ID Pattern:** `{app}_{section}_{type}_{descriptor}`

**Examples:**
- `business_inbound_requests_form_filter`
- `wh_links_table_main`
- `orders_list_btn_export`

## Layout System

### Responsive Dashboard Grid

For admin/workforce dashboards with dynamic content sections:

```css
/* Dashboard Grid Container */
.dashboard-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
    gap: var(--spacing-lg);
    padding: var(--spacing-lg);
}

/* Full-width sections */
.dashboard-grid__full {
    grid-column: 1 / -1;
}

/* Sidebar layouts */
.dashboard-layout {
    display: grid;
    grid-template-columns: 280px 1fr;
    gap: var(--spacing-lg);
    min-height: 100vh;
}

.dashboard-layout__sidebar {
    background: var(--brand-white);
    border-right: 1px solid var(--brand-grey-200);
    position: sticky;
    top: 0;
    height: 100vh;
    overflow-y: auto;
}

.dashboard-layout__main {
    padding: var(--spacing-lg);
}

@media (max-width: 1024px) {
    .dashboard-layout {
        grid-template-columns: 1fr;
    }
    .dashboard-layout__sidebar {
        position: relative;
        height: auto;
        border-right: none;
        border-bottom: 1px solid var(--brand-grey-200);
    }
}
```

### Two-Column Split Layout

For forms/content with live preview or side-by-side views:

```css
.split-layout {
    display: grid;
    grid-template-columns: 400px 1fr;
    gap: var(--spacing-xl);
    height: 100%;
}

.split-layout__left {
    overflow-y: auto;
}

.split-layout__right {
    overflow-y: auto;
}

@media (max-width: 1024px) {
    .split-layout {
        grid-template-columns: 1fr;
        grid-template-rows: auto 1fr;
    }
}
```

## Navigation Patterns

### Sidebar Navigation

Modern sidebar with active states and icons:

```html
<nav class="sidebar-nav">
    <div class="sidebar-nav__section">
        <h4 class="sidebar-nav__heading">Main</h4>
        <a href="#" class="sidebar-nav__link sidebar-nav__link--active">
            <i class="fa-solid fa-chart-line"></i>
            <span>Dashboard</span>
        </a>
        <a href="#" class="sidebar-nav__link">
            <i class="fa-solid fa-box"></i>
            <span>Orders</span>
            <span class="sidebar-nav__badge">12</span>
        </a>
    </div>
</nav>
```

```css
.sidebar-nav {
    padding: var(--spacing-md);
}

.sidebar-nav__section {
    margin-bottom: var(--spacing-lg);
}

.sidebar-nav__heading {
    font-size: 0.75rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--brand-grey-500);
    margin: 0 0 var(--spacing-sm);
    padding: 0 var(--spacing-sm);
}

.sidebar-nav__link {
    display: flex;
    align-items: center;
    gap: var(--spacing-sm);
    padding: var(--spacing-sm) var(--spacing-md);
    border-radius: var(--brand-radius-sm);
    color: var(--brand-grey-700);
    text-decoration: none;
    font-size: 0.9375rem;
    font-weight: 500;
    transition: var(--brand-transition);
    margin-bottom: 0.25rem;
}

.sidebar-nav__link:hover {
    background: var(--brand-grey-100);
    color: var(--brand-grey-900);
}

.sidebar-nav__link--active {
    background: var(--brand-primary);
    color: var(--brand-grey-900);
    font-weight: 600;
}

.sidebar-nav__link i {
    width: 20px;
    text-align: center;
    font-size: 1rem;
}

.sidebar-nav__badge {
    margin-left: auto;
    padding: 0.125rem 0.5rem;
    background: var(--brand-danger);
    color: var(--brand-white);
    font-size: 0.75rem;
    font-weight: 600;
    border-radius: var(--brand-radius-sm);
}
```

### Breadcrumb Navigation

```html
<nav class="breadcrumb">
    <a href="#" class="breadcrumb__link">Home</a>
    <i class="fa-solid fa-chevron-right breadcrumb__separator"></i>
    <a href="#" class="breadcrumb__link">Orders</a>
    <i class="fa-solid fa-chevron-right breadcrumb__separator"></i>
    <span class="breadcrumb__current">Details</span>
</nav>
```

```css
.breadcrumb {
    display: flex;
    align-items: center;
    gap: var(--spacing-sm);
    padding: var(--spacing-md);
    font-size: 0.875rem;
}

.breadcrumb__link {
    color: var(--brand-grey-600);
    text-decoration: none;
    transition: var(--brand-transition);
}

.breadcrumb__link:hover {
    color: var(--brand-primary);
}

.breadcrumb__separator {
    font-size: 0.75rem;
    color: var(--brand-grey-400);
}

.breadcrumb__current {
    color: var(--brand-grey-900);
    font-weight: 600;
}
```

## Data Visualization

### Metric Cards with Trends

Cards that show KPIs with trend indicators:

```html
<div class="metric-card">
    <div class="metric-card__header">
        <span class="metric-card__label">Total Revenue</span>
        <span class="metric-card__trend metric-card__trend--up">
            <i class="fa-solid fa-arrow-up"></i>
            12.5%
        </span>
    </div>
    <div class="metric-card__value">QAR 45,230</div>
    <div class="metric-card__footer">
        <span class="metric-card__comparison">vs last month: QAR 40,200</span>
    </div>
</div>
```

```css
.metric-card {
    background: var(--brand-white);
    border: 1px solid var(--brand-grey-200);
    border-radius: var(--brand-radius-md);
    padding: var(--spacing-lg);
    transition: var(--brand-transition);
}

.metric-card:hover {
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08);
    transform: translateY(-2px);
}

.metric-card__header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: var(--spacing-sm);
}

.metric-card__label {
    font-size: 0.875rem;
    color: var(--brand-grey-600);
    font-weight: 500;
}

.metric-card__trend {
    display: flex;
    align-items: center;
    gap: 0.25rem;
    font-size: 0.8125rem;
    font-weight: 600;
    padding: 0.25rem 0.5rem;
    border-radius: var(--brand-radius-sm);
}

.metric-card__trend--up {
    background: rgba(25, 135, 84, 0.1);
    color: var(--brand-success);
}

.metric-card__trend--down {
    background: rgba(220, 53, 69, 0.1);
    color: var(--brand-danger);
}

.metric-card__value {
    font-size: 2rem;
    font-weight: 700;
    color: var(--brand-grey-900);
    margin-bottom: var(--spacing-sm);
}

.metric-card__footer {
    font-size: 0.8125rem;
    color: var(--brand-grey-500);
}
```

### Simple Bar Chart

Pure CSS bar chart for basic visualization:

```html
<div class="chart-bar">
    <div class="chart-bar__label">Active Orders</div>
    <div class="chart-bar__track">
        <div class="chart-bar__fill" style="--fill-percent: 75%"></div>
    </div>
    <div class="chart-bar__value">75 / 100</div>
</div>
```

```css
.chart-bar {
    margin-bottom: var(--spacing-md);
}

.chart-bar__label {
    font-size: 0.875rem;
    font-weight: 500;
    color: var(--brand-grey-700);
    margin-bottom: var(--spacing-xs);
}

.chart-bar__track {
    height: 8px;
    background: var(--brand-grey-200);
    border-radius: var(--brand-radius-sm);
    overflow: hidden;
    margin-bottom: var(--spacing-xs);
}

.chart-bar__fill {
    height: 100%;
    width: var(--fill-percent);
    background: linear-gradient(90deg, var(--brand-primary), var(--brand-secondary));
    border-radius: var(--brand-radius-sm);
    transition: width 0.6s ease;
}

.chart-bar__value {
    font-size: 0.8125rem;
    color: var(--brand-grey-600);
    text-align: right;
}
```

### Progress Ring

Circular progress indicator:

```html
<div class="progress-ring">
    <svg class="progress-ring__svg" viewBox="0 0 100 100">
        <circle class="progress-ring__track" cx="50" cy="50" r="45"></circle>
        <circle class="progress-ring__fill" cx="50" cy="50" r="45"
                style="--progress: 0.65"></circle>
    </svg>
    <div class="progress-ring__label">
        <div class="progress-ring__value">65%</div>
        <div class="progress-ring__text">Complete</div>
    </div>
</div>
```

```css
.progress-ring {
    position: relative;
    width: 120px;
    height: 120px;
}

.progress-ring__svg {
    width: 100%;
    height: 100%;
    transform: rotate(-90deg);
}

.progress-ring__track {
    fill: none;
    stroke: var(--brand-grey-200);
    stroke-width: 8;
}

.progress-ring__fill {
    fill: none;
    stroke: var(--brand-primary);
    stroke-width: 8;
    stroke-linecap: round;
    stroke-dasharray: calc(2 * 3.14159 * 45);
    stroke-dashoffset: calc(2 * 3.14159 * 45 * (1 - var(--progress)));
    transition: stroke-dashoffset 0.8s ease;
}

.progress-ring__label {
    position: absolute;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
    text-align: center;
}

.progress-ring__value {
    font-size: 1.5rem;
    font-weight: 700;
    color: var(--brand-grey-900);
}

.progress-ring__text {
    font-size: 0.75rem;
    color: var(--brand-grey-600);
}
```

## Micro-Interactions

### Skeleton Loading

Content placeholders during data loading:

```html
<div class="skeleton">
    <div class="skeleton__line"></div>
    <div class="skeleton__line skeleton__line--short"></div>
    <div class="skeleton__block"></div>
</div>
```

```css
@keyframes skeleton-pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.4; }
}

.skeleton__line {
    height: 12px;
    background: var(--brand-grey-200);
    border-radius: var(--brand-radius-sm);
    margin-bottom: var(--spacing-sm);
    animation: skeleton-pulse 1.5s ease-in-out infinite;
}

.skeleton__line--short {
    width: 60%;
}

.skeleton__block {
    height: 200px;
    background: var(--brand-grey-200);
    border-radius: var(--brand-radius-md);
    animation: skeleton-pulse 1.5s ease-in-out infinite;
}
```

### Ripple Effect (Button Click)

Material Design-style ripple on button clicks:

```css
.btn-ripple {
    position: relative;
    overflow: hidden;
}

.btn-ripple::after {
    content: '';
    position: absolute;
    top: 50%;
    left: 50%;
    width: 0;
    height: 0;
    border-radius: 50%;
    background: rgba(255, 255, 255, 0.5);
    transform: translate(-50%, -50%);
    transition: width 0.6s, height 0.6s;
}

.btn-ripple:active::after {
    width: 300px;
    height: 300px;
}
```

### Smooth State Transitions

```css
/* Fade in animations */
@keyframes fadeIn {
    from { opacity: 0; transform: translateY(10px); }
    to { opacity: 1; transform: translateY(0); }
}

.fade-in {
    animation: fadeIn 0.3s ease;
}

/* Slide in from right */
@keyframes slideInRight {
    from { transform: translateX(100%); }
    to { transform: translateX(0); }
}

.slide-in-right {
    animation: slideInRight 0.3s ease;
}

/* Scale bounce */
@keyframes scaleBounce {
    0% { transform: scale(0.9); }
    50% { transform: scale(1.05); }
    100% { transform: scale(1); }
}

.scale-bounce {
    animation: scaleBounce 0.4s ease;
}
```

### Loading Spinner

```html
<div class="spinner">
    <div class="spinner__ring"></div>
</div>
```

```css
@keyframes spin {
    to { transform: rotate(360deg); }
}

.spinner {
    display: inline-block;
    width: 24px;
    height: 24px;
}

.spinner__ring {
    width: 100%;
    height: 100%;
    border: 3px solid var(--brand-grey-200);
    border-top-color: var(--brand-primary);
    border-radius: 50%;
    animation: spin 0.8s linear infinite;
}
```

## Dark Mode Support

### CSS Variables Approach

Define color schemes using CSS custom properties:

```css
:root {
    /* Light mode (default) */
    --bg-primary: #ffffff;
    --bg-secondary: #f8f9fa;
    --text-primary: #212529;
    --text-secondary: #6c757d;
    --border-color: #dee2e6;
}

[data-theme="dark"] {
    /* Dark mode */
    --bg-primary: #1a1d23;
    --bg-secondary: #25292f;
    --text-primary: #e9ecef;
    --text-secondary: #adb5bd;
    --border-color: #495057;
}

/* Apply variables */
body {
    background: var(--bg-primary);
    color: var(--text-primary);
}

.card {
    background: var(--bg-secondary);
    border: 1px solid var(--border-color);
}
```

### Theme Toggle

```html
<button class="theme-toggle" id="theme_toggle_btn" aria-label="Toggle dark mode">
    <i class="fa-solid fa-sun theme-toggle__icon theme-toggle__icon--light"></i>
    <i class="fa-solid fa-moon theme-toggle__icon theme-toggle__icon--dark"></i>
</button>
```

```css
.theme-toggle {
    position: relative;
    width: 48px;
    height: 48px;
    border-radius: 50%;
    border: 1px solid var(--border-color);
    background: var(--bg-secondary);
    cursor: pointer;
    transition: var(--brand-transition);
}

.theme-toggle:hover {
    background: var(--brand-primary);
}

.theme-toggle__icon {
    position: absolute;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
    transition: opacity 0.3s ease, transform 0.3s ease;
}

.theme-toggle__icon--light {
    opacity: 1;
}

.theme-toggle__icon--dark {
    opacity: 0;
}

[data-theme="dark"] .theme-toggle__icon--light {
    opacity: 0;
}

[data-theme="dark"] .theme-toggle__icon--dark {
    opacity: 1;
}
```

```javascript
// Theme toggle script
const themeToggle = document.getElementById('theme_toggle_btn');
const htmlElement = document.documentElement;

// Check saved theme
const savedTheme = localStorage.getItem('theme') || 'light';
htmlElement.setAttribute('data-theme', savedTheme);

themeToggle.addEventListener('click', () => {
    const currentTheme = htmlElement.getAttribute('data-theme');
    const newTheme = currentTheme === 'light' ? 'dark' : 'light';
    htmlElement.setAttribute('data-theme', newTheme);
    localStorage.setItem('theme', newTheme);
});
```

## Common Patterns Reference

See existing implementations:
- **Compact Lists:** `workforce/templates/workforce/warehouses_list.html`
- **Modern Tables:** `business/templates/business/inbound_requests_list.html`
- **Stat Cards:** `workforce/templates/workforce/business_license_detail.html`
- **Products Grid:** `workforce/templates/workforce/workforce_pickup_location_add.html`
- Homepage hero: `webpages/templates/webpages/homepage.html`
- SEO landing pages: `webpages/templates/webpages/delivery_*.html`
- Dashboard cards: `business/templates/business/dashboard.html`
