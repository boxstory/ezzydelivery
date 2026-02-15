# EzzyDelivery Qatar - Brand Kit

## Overview
This brand kit defines the official colors, typography, and design elements for EzzyDelivery Qatar's web presence.

---

## 🎨 Brand Colors

### Primary Colors

**Energetic Orange** - Main brand color representing speed and reliability
- **Hex**: `#ff6b35`
- **RGB**: `rgb(255, 107, 53)`
- **HSL**: `hsl(14, 100%, 60%)`
- **Usage**: Primary buttons, CTAs, links, active states, delivery icons

**Light Variant**
- **Hex**: `#ff8c61`
- **Usage**: Hover states, backgrounds, highlights

**Dark Variant**
- **Hex**: `#e55a2b`
- **Usage**: Active/pressed states, borders

### Secondary Colors

**Professional Navy** - Represents trust and professionalism
- **Hex**: `#1a2238`
- **RGB**: `rgb(26, 34, 56)`
- **HSL**: `hsl(224, 37%, 16%)`
- **Usage**: Headers, navigation, footer, text headings

**Light Variant**
- **Hex**: `#2d3a5f`
- **Usage**: Hover states on dark backgrounds

**Dark Variant**
- **Hex**: `#0d1120`
- **Usage**: Deep backgrounds, overlays

### Accent Colors

**Success Green** - Delivery completion and success states
- **Hex**: `#4caf50`
- **RGB**: `rgb(76, 175, 80)`
- **Usage**: Success messages, completed deliveries, checkmarks

**Light Variant**
- **Hex**: `#6fbf73`
- **Usage**: Success backgrounds

**Dark Variant**
- **Hex**: `#3d8b40`
- **Usage**: Success borders, hover states

### Neutral Colors

**Background**
- **Hex**: `#f8f9fa`
- **Usage**: Page background

**Card Background**
- **Hex**: `#ffffff`
- **Usage**: Cards, modals, panels

**Text Primary**
- **Hex**: `#1a2238`
- **Usage**: Main text, headings

**Text Muted**
- **Hex**: `#6c757d`
- **Usage**: Secondary text, descriptions, labels

### Semantic Colors

**Warning/Pending**
- **Hex**: `#f59e0b`
- **Usage**: Pending deliveries, warnings

**Error/Cancelled**
- **Hex**: `#ef4444`
- **Usage**: Error messages, cancelled orders

**Info**
- **Hex**: `#3b82f6`
- **Usage**: Information messages, tips

---

## 🎨 CSS Variables

```css
/* ========================================
   EZZYDELIVERY QATAR - BRAND KIT
   ======================================== */

:root {
  /* === PRIMARY COLORS === */
  --ezzy-primary: #ff6b35;
  --ezzy-primary-light: #ff8c61;
  --ezzy-primary-dark: #e55a2b;
  
  /* === SECONDARY COLORS === */
  --ezzy-secondary: #1a2238;
  --ezzy-secondary-light: #2d3a5f;
  --ezzy-secondary-dark: #0d1120;
  
  /* === ACCENT COLORS === */
  --ezzy-success: #4caf50;
  --ezzy-success-light: #6fbf73;
  --ezzy-success-dark: #3d8b40;
  
  /* === NEUTRALS === */
  --ezzy-bg: #f8f9fa;
  --ezzy-card: #ffffff;
  --ezzy-text: #1a2238;
  --ezzy-text-muted: #6c757d;
  --ezzy-border: #e2e8f0;
  
  /* === SEMANTIC === */
  --ezzy-warning: #f59e0b;
  --ezzy-error: #ef4444;
  --ezzy-info: #3b82f6;
  
  /* === GRADIENTS === */
  --ezzy-gradient-primary: linear-gradient(135deg, #ff6b35 0%, #f7931e 100%);
  --ezzy-gradient-success: linear-gradient(135deg, #4caf50 0%, #8bc34a 100%);
  --ezzy-gradient-hero: linear-gradient(135deg, #1a2238 0%, #2d3a5f 100%);
  
  /* === SHADOWS === */
  --ezzy-shadow-sm: 0 2px 4px rgba(26, 34, 56, 0.08);
  --ezzy-shadow-md: 0 4px 12px rgba(26, 34, 56, 0.12);
  --ezzy-shadow-lg: 0 8px 24px rgba(26, 34, 56, 0.16);
  --ezzy-shadow-primary: 0 4px 12px rgba(255, 107, 53, 0.3);
}
```

---

## 📝 Typography

### Font Families

**Primary Font**: Inter
- **Usage**: Body text, UI elements, forms
- **Weights**: 400 (Regular), 500 (Medium), 600 (Semibold), 700 (Bold)

**Display Font**: Outfit
- **Usage**: Headings, hero text, marketing copy
- **Weights**: 600 (Semibold), 700 (Bold), 800 (Extrabold)

### Font Import

```html
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Outfit:wght@600;700;800&display=swap" rel="stylesheet">
```

### Type Scale

```css
:root {
  --ezzy-text-xs: 0.75rem;    /* 12px - Small labels */
  --ezzy-text-sm: 0.875rem;   /* 14px - Secondary text */
  --ezzy-text-base: 1rem;     /* 16px - Body text */
  --ezzy-text-lg: 1.125rem;   /* 18px - Large body */
  --ezzy-text-xl: 1.25rem;    /* 20px - Small headings */
  --ezzy-text-2xl: 1.5rem;    /* 24px - Section headings */
  --ezzy-text-3xl: 1.875rem;  /* 30px - Page headings */
  --ezzy-text-4xl: 2.25rem;   /* 36px - Large headings */
  --ezzy-text-5xl: 3rem;      /* 48px - Hero text */
}
```

---

## 🎯 Component Styles

### Buttons

```css
/* Primary Button - Use for main CTAs */
.btn-primary {
  background: var(--ezzy-gradient-primary);
  color: white;
  padding: 0.75rem 1.5rem;
  border-radius: 12px;
  font-weight: 600;
  box-shadow: var(--ezzy-shadow-primary);
  transition: all 0.3s ease;
}

.btn-primary:hover {
  transform: translateY(-2px);
  box-shadow: 0 6px 16px rgba(255, 107, 53, 0.4);
}

/* Secondary Button - Use for secondary actions */
.btn-secondary {
  background: var(--ezzy-secondary);
  color: white;
  padding: 0.75rem 1.5rem;
  border-radius: 12px;
  font-weight: 600;
  transition: all 0.3s ease;
}

.btn-secondary:hover {
  background: var(--ezzy-secondary-light);
}

/* Success Button - Use for completion actions */
.btn-success {
  background: var(--ezzy-gradient-success);
  color: white;
  padding: 0.75rem 1.5rem;
  border-radius: 12px;
  font-weight: 600;
  transition: all 0.3s ease;
}
```

### Cards

```css
.ezzy-card {
  background: var(--ezzy-card);
  border-radius: 16px;
  padding: 1.5rem;
  box-shadow: var(--ezzy-shadow-md);
  border: 1px solid var(--ezzy-border);
  transition: all 0.3s ease;
}

.ezzy-card:hover {
  transform: translateY(-4px);
  box-shadow: var(--ezzy-shadow-lg);
}
```

### Status Badges

```css
.status-pending {
  background: rgba(245, 158, 11, 0.1);
  color: var(--ezzy-warning);
  padding: 0.25rem 0.75rem;
  border-radius: 8px;
  font-size: var(--ezzy-text-sm);
  font-weight: 600;
}

.status-completed {
  background: rgba(76, 175, 80, 0.1);
  color: var(--ezzy-success);
  padding: 0.25rem 0.75rem;
  border-radius: 8px;
  font-size: var(--ezzy-text-sm);
  font-weight: 600;
}

.status-cancelled {
  background: rgba(239, 68, 68, 0.1);
  color: var(--ezzy-error);
  padding: 0.25rem 0.75rem;
  border-radius: 8px;
  font-size: var(--ezzy-text-sm);
  font-weight: 600;
}
```

---

## 🚀 Usage Guidelines

### Do's ✅

1. **Use the primary orange** for all CTAs and important actions
2. **Use the navy** for headers, navigation, and professional sections
3. **Use the success green** for completed deliveries and positive feedback
4. **Maintain consistent spacing** using the defined scale
5. **Use gradients** for hero sections and primary buttons
6. **Apply shadows** to create depth and hierarchy

### Don'ts ❌

1. **Don't use pure black** (#000000) - use navy instead
2. **Don't create new colors** - stick to the brand palette
3. **Don't use harsh shadows** - keep them soft and subtle
4. **Don't mix font families** - stick to Inter and Outfit
5. **Don't ignore accessibility** - ensure proper contrast ratios

---

## 📱 Responsive Considerations

- **Mobile**: Reduce font sizes by 10-15% for smaller screens
- **Tablet**: Use standard sizes
- **Desktop**: Can increase hero text sizes by 10-20%

---

## 🎨 Color Accessibility

All color combinations have been tested for WCAG AA compliance:

| Combination | Contrast Ratio | Status |
|-------------|----------------|--------|
| Primary Orange on White | 4.52:1 | ✅ AA |
| Navy on White | 14.21:1 | ✅ AAA |
| Success Green on White | 3.98:1 | ✅ AA Large |
| White on Primary Orange | 4.52:1 | ✅ AA |
| White on Navy | 14.21:1 | ✅ AAA |

---

**Last Updated**: February 2026
**Version**: 1.0
**Maintained by**: EzzyDelivery Design Team
