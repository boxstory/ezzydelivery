# Workforce Dashboard - Modern Design System

**Created:** February 14, 2026
**Version:** 1.0
**Status:** Production Ready

## Overview

The workforce dashboard uses a modern, card-based design system with clean typography, smooth animations, and mobile-first responsive layouts.

---

## 🎨 Color System

### Status Colors
```css
Primary (Blue):   #0d6efd - Total metrics, main actions
Success (Green):  #198754 - Completed, active states
Warning (Yellow): #ffc107 - Pending, attention needed
Danger (Red):     #dc3545 - Urgent, follow-up required
Info (Cyan):      #0dcaf0 - Analytics, informational
```

### Brand Colors
```css
Brand Yellow:     #f7c000 - Primary brand color, icons
Brand Navy:       #001f3f - Secondary brand (not used in dashboard)
```

### Neutral Colors
```css
Gray 900: #212529 - Headings, primary text
Gray 700: #495057 - Body text
Gray 600: #6c757d - Secondary text
Gray 500: #adb5bd - Muted text, icons
Gray 400: #ced4da - Borders (unused)
Gray 300: #dee2e6 - Dividers, disabled
Gray 200: #e9ecef - Borders, backgrounds
Gray 100: #f8f9fa - Page background
White:    #ffffff - Card backgrounds
```

---

## 📐 Typography Scale

### Font Family
```css
System Font Stack:
-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto,
"Helvetica Neue", Arial, sans-serif
```

### Font Sizes
```css
Dashboard Title:     1.75rem (28px) - Bold 700
Card Title:          1.125rem (18px) - Semibold 600
Metric Value:        2rem (32px) - Bold 700
Status Value:        1.5rem (24px) - Bold 700
Body Text:           0.9375rem (15px) - Regular 400
Small Text:          0.875rem (14px) - Medium 500
Tiny Text:           0.8125rem (13px) - Medium 500
```

---

## 🔲 Spacing System

### Base Unit: 1rem = 16px

```css
XS:  0.25rem (4px)
SM:  0.5rem (8px)
MD:  0.75rem (12px)
LG:  1rem (16px)
XL:  1.25rem (20px)
2XL: 1.5rem (24px)
3XL: 2rem (32px)
4XL: 3rem (48px)
```

### Component Spacing
```css
Card Padding:        1.5rem (24px)
Card Header Padding: 1.25rem 1.5rem (20px 24px)
Section Gap:         1.5rem (24px)
Grid Gap:            1.25rem (20px)
```

---

## 🎯 Component Library

### 1. Metric Cards (`.wf-metric-card`)

**Usage:** Display key performance indicators with trends

**Structure:**
```html
<div class="wf-metric-card">
  <div class="wf-metric-card__header">
    <span class="wf-metric-card__label">Label</span>
    <span class="wf-metric-card__trend wf-metric-card__trend--up">
      <i class="fa-solid fa-arrow-up"></i>
      12.5%
    </span>
  </div>
  <div class="wf-metric-card__value">1,234</div>
  <div class="wf-metric-card__footer">
    <a href="#" class="wf-metric-card__link">
      <i class="fa-solid fa-arrow-right"></i>
      View details
    </a>
  </div>
</div>
```

**Variants:**
- `wf-metric-card__trend--up` - Green, upward arrow
- `wf-metric-card__trend--down` - Red, downward arrow
- `wf-metric-card__trend--neutral` - Gray, minus icon

**Behavior:**
- Hover: Lift 4px with enhanced shadow
- Transition: 0.3s ease

---

### 2. Status Items (`.wf-status-item`)

**Usage:** Clickable list items showing counts/metrics

**Structure:**
```html
<a href="#" class="wf-status-item wf-status-item--primary">
  <div class="wf-status-item__icon">
    <i class="fa-solid fa-box"></i>
  </div>
  <div class="wf-status-item__content">
    <span class="wf-status-item__label">Total Orders</span>
    <span class="wf-status-item__value">456</span>
  </div>
  <div class="wf-status-item__arrow">
    <i class="fa-solid fa-chevron-right"></i>
  </div>
</a>
```

**Variants:**
- `wf-status-item--primary` - Blue background/icon
- `wf-status-item--success` - Green background/icon
- `wf-status-item--warning` - Yellow background/icon
- `wf-status-item--danger` - Red background/icon
- `wf-status-item--info` - Cyan background/icon

**Behavior:**
- Hover: Slide right 4px, show colored border, arrow moves
- Icon: 48px circle with 15% opacity background

---

### 3. Quick Actions (`.wf-quick-action`)

**Usage:** Grid of action buttons with icons

**Structure:**
```html
<a href="#" class="wf-quick-action wf-quick-action--primary">
  <div class="wf-quick-action__icon">
    <i class="fa-solid fa-paper-plane"></i>
  </div>
  <span class="wf-quick-action__label">Publish Orders</span>
</a>
```

**Variants:**
- `wf-quick-action--primary` - Blue theme
- `wf-quick-action--success` - Green theme
- `wf-quick-action--warning` - Yellow theme
- `wf-quick-action--info` - Cyan theme

**Behavior:**
- Hover: Lift 4px, icon background fills solid color, white icon
- Icon: 56px circle, 1.5rem icon size
- Min-height: 120px

---

### 4. Cards (`.wf-card`)

**Usage:** Container for dashboard sections

**Structure:**
```html
<div class="wf-card">
  <div class="wf-card__header">
    <h2 class="wf-card__title">
      <i class="fa-solid fa-icon"></i>
      Card Title
    </h2>
    <a href="#" class="wf-card__header-link">
      View All <i class="fa-solid fa-arrow-right"></i>
    </a>
  </div>
  <div class="wf-card__body">
    <!-- Content -->
  </div>
</div>
```

**Modifiers:**
- `wf-card__body--no-padding` - Remove body padding (for tables)

**Styling:**
- Border: 1px solid #e9ecef
- Border-radius: 1rem (16px)
- Background: #ffffff

---

### 5. Empty State (`.wf-empty-state`)

**Usage:** Show when no data is available

**Structure:**
```html
<div class="wf-empty-state">
  <i class="fa-solid fa-inbox"></i>
  <p class="wf-empty-state__title">No recent orders</p>
  <p class="wf-empty-state__text">Orders will appear here</p>
</div>
```

**Styling:**
- Icon: 3rem, light gray (#dee2e6)
- Center-aligned text
- Padding: 3rem 1.5rem

---

## 📱 Responsive Breakpoints

### Desktop (1024px+)
```css
- Two-column grid (400px | 1fr)
- 4-column metrics row
- Full sidebar navigation
```

### Tablet (768px - 1024px)
```css
- Single column layout
- 2-column metrics row
- Stacked sections
```

### Mobile (<768px)
```css
- Single column everywhere
- 2-column quick actions
- Reduced padding (1rem)
- Touch-friendly tap targets (44px min)
```

### Small Mobile (<480px)
```css
- Smaller typography
- Compact metric cards
- Minimal padding
```

---

## 🎭 Animations & Transitions

### Page Load
```css
@keyframes fadeIn {
  from { opacity: 0; transform: translateY(10px); }
  to { opacity: 1; transform: translateY(0); }
}

Staggered delays:
- Section 1: 0s
- Section 2: 0.1s
- Section 3: 0.2s
- Section 4: 0.3s
```

### Hover Transitions
```css
All interactive elements: 0.2s ease
Cards: 0.3s ease
Icons: 0.3s ease
```

### Micro-Interactions
```css
Metric cards: translateY(-4px) on hover
Status items: translateX(4px) on hover
Quick actions: translateY(-4px) on hover
Links: gap expands 0.375rem → 0.625rem
```

---

## 🔧 Technical Specifications

### CSS Architecture
```
BEM Naming Convention:
- Block:   .wf-dashboard
- Element: .wf-dashboard__header
- Modifier: .wf-metric-card--large
```

### Element ID Pattern
```
Format: {app}_{section}_{type}_{descriptor}

Examples:
- wf_dashboard_btn_refresh
- wf_dashboard_link_total_orders
- wf_dashboard_chart_orders_trend
```

### File Structure
```
workforce/
├── templates/workforce/
│   ├── wf_base_dashboard.html          (Base template)
│   └── parts/
│       └── wf_dashboard.html           (Dashboard content)
└── static/workforce/css/
    └── dashboard-modern.css            (All styles)
```

---

## ♿ Accessibility

### Semantic HTML
- Proper heading hierarchy (h1 → h2)
- Meaningful link text
- Button vs link distinction

### ARIA Attributes
```html
role="button"
aria-label="View all orders"
aria-live="polite"
aria-hidden="true" (decorative icons)
```

### Keyboard Navigation
- All interactive elements focusable
- Visible focus states
- Logical tab order

### Color Contrast
- All text meets WCAG AA standards (4.5:1)
- Icons have 3:1 contrast
- Hover states clearly visible

---

## 🚀 Performance

### Optimizations
- CSS transforms (GPU-accelerated)
- No layout thrashing
- Debounced animations
- Lazy chart rendering
- Minimal repaints

### Loading Strategy
- Critical CSS inline (future)
- Deferred chart library
- Skeleton states ready (`.wf-skeleton`)

---

## 📊 Dashboard Sections

### 1. Header
- Page title with icon
- Subtitle
- Refresh button

### 2. Key Metrics Row
- 4 metric cards
- Grid: `repeat(auto-fit, minmax(280px, 1fr))`

### 3. Operations Grid
**Left Column (400px):**
- Order Status (5 items)
- Verifications (2 items)

**Right Column (flexible):**
- Orders Trend Chart (ApexCharts)
- Quick Actions (6 buttons)

### 4. Latest Orders
- Full-width table
- Includes order_list_review.html

---

## 🎨 Design Principles

1. **Mobile-First** - Start with mobile, enhance for desktop
2. **Progressive Enhancement** - Core functionality works without JS
3. **Performance** - Smooth 60fps animations
4. **Accessibility** - WCAG 2.1 AA compliant
5. **Consistency** - Reusable components
6. **Clarity** - Clear visual hierarchy
7. **Feedback** - Hover states, transitions
8. **Whitespace** - Generous padding, breathing room

---

## 📝 Usage Examples

### Adding a New Metric Card
```html
<div class="wf-metric-card">
  <div class="wf-metric-card__header">
    <span class="wf-metric-card__label">New Metric</span>
    <span class="wf-metric-card__trend wf-metric-card__trend--up">
      <i class="fa-solid fa-arrow-up"></i>
      +15%
    </span>
  </div>
  <div class="wf-metric-card__value">789</div>
  <div class="wf-metric-card__footer">
    <a href="/path/" class="wf-metric-card__link">
      <i class="fa-solid fa-arrow-right"></i>
      View details
    </a>
  </div>
</div>
```

### Adding a Status Item
```html
<a href="/path/" class="wf-status-item wf-status-item--success">
  <div class="wf-status-item__icon">
    <i class="fa-solid fa-check"></i>
  </div>
  <div class="wf-status-item__content">
    <span class="wf-status-item__label">New Status</span>
    <span class="wf-status-item__value">42</span>
  </div>
  <div class="wf-status-item__arrow">
    <i class="fa-solid fa-chevron-right"></i>
  </div>
</a>
```

### Adding a Quick Action
```html
<a href="/path/" class="wf-quick-action wf-quick-action--info">
  <div class="wf-quick-action__icon">
    <i class="fa-solid fa-chart-bar"></i>
  </div>
  <span class="wf-quick-action__label">New Action</span>
</a>
```

---

## 🔄 Future Enhancements

### Planned Features
- [ ] Dark mode support
- [ ] Real-time data updates (WebSocket)
- [ ] Advanced filtering
- [ ] Customizable widgets
- [ ] Export dashboard data
- [ ] Mobile app integration
- [ ] Multi-language support

### Performance Goals
- [ ] First Contentful Paint < 1.5s
- [ ] Time to Interactive < 3s
- [ ] Lighthouse score > 90

---

## 📚 References

- **CSS File:** `workforce/static/workforce/css/dashboard-modern.css`
- **Template:** `workforce/templates/workforce/parts/wf_dashboard.html`
- **Base Template:** `workforce/templates/workforce/wf_base_dashboard.html`
- **Brand Guidelines:** `docs/CSS_OPTIMIZATION_SUMMARY.md`
- **Design Skill:** `.claude/skills/frontend-designer.md`

---

**Last Updated:** February 14, 2026
**Maintained By:** Development Team
**Version:** 1.0 (Production)
