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

## Common Patterns Reference

See existing implementations:
- Homepage hero: `webpages/templates/webpages/homepage.html`
- SEO landing pages: `webpages/templates/webpages/delivery_*.html`
- Dashboard cards: `business/templates/business/dashboard.html`
- Forms: `orders/templates/orders/order_product_add.html`
- Tables: `workforce/templates/workforce/orders_list.html`
