# Designer Command

**Purpose:** Activate comprehensive frontend designer mode for creating polished, modern UI with professional HTML structure and CSS styling using EzzyDelivery branding.

## When to Use

- Designing new landing pages
- Creating UI components (cards, buttons, forms)
- Building hero sections or feature grids
- Implementing responsive layouts
- Optimizing HTML structure and Bootstrap grid
- Styling with brand consistency
- Improving page layouts and component organization

## Activation

```
/designer
```

## What This Does

When you use `/designer`, Claude will provide **BOTH HTML structure improvements AND CSS styling**:

### 1. **HTML Structure Optimization**
   - **Bootstrap Grid System**: Proper use of `.row`, `.col-*`, responsive breakpoints
   - **Semantic HTML5**: `<section>`, `<article>`, `<header>`, `<footer>`, proper heading hierarchy
   - **Flexbox & Grid**: `d-flex`, `justify-content-*`, `align-items-*`, gap utilities
   - **Responsive Classes**: `.d-none`, `.d-lg-block`, `.col-12`, `.col-md-6`, `.col-lg-4`
   - **Spacing Utilities**: `.p-*`, `.m-*`, `.g-*` (gutters), proper padding/margin
   - **Accessibility**: Proper ARIA labels, semantic tags, keyboard navigation
   - **Component Structure**: Card headers, bodies, footers; proper nesting
   - **Icon Integration**: Font Awesome icons with proper sizing and colors

### 2. **CSS Styling Excellence**
   - **Brand Kit Variables**: Use all CSS variables from `brand-kit.css`
   - **Color Palette**: Consistent use of primary, secondary, accent colors
   - **Typography Scale**: Font sizes, weights, line-heights from design system
   - **Spacing System**: Consistent spacing using CSS variables
   - **Modern Effects**: Gradients, shadows, glassmorphism, animations
   - **Hover States**: Interactive feedback on all clickable elements
   - **Transitions**: Smooth animations with cubic-bezier easing
   - **Mobile-First**: Responsive breakpoints with proper media queries

### 3. **Bootstrap Best Practices**
   - Use utility classes: `.mb-3`, `.text-center`, `.fw-bold`, `.text-muted`
   - Grid breakpoints: `.col-12 .col-sm-6 .col-md-4 .col-lg-3`
   - Flexbox utilities: `.d-flex`, `.justify-content-between`, `.align-items-center`
   - Spacing: `.p-4`, `.px-3`, `.py-2`, `.m-auto`, `.g-3` (gap)
   - Display: `.d-none`, `.d-md-block`, `.d-lg-inline-flex`
   - Text alignment: `.text-start`, `.text-center`, `.text-end`, `.text-sm-start`

### 4. **EzzyDelivery Code Patterns**
   - No inline styles or `<style>` tags - use external CSS files
   - Link CSS in `{% block extra_css %}`
   - ID naming: `{app}_{section}_{element}_{descriptor}`
   - CSS file location: `{app}/static/{app}/css/{filename}.css`
   - Version cache busting: `?v=YYYYMMDD{letter}`

### 5. **Performance & Accessibility**
   - CSS transforms over layout properties (transform, opacity)
   - Proper focus states for keyboard navigation
   - ARIA attributes where needed
   - Semantic HTML for screen readers
   - Reduced motion support: `@media (prefers-reduced-motion: reduce)`

## Example Usage

```
/designer

Make the profile page look professional with better layout
```

**Claude will analyze and improve:**

1. **HTML Structure**:
   ```html
   <!-- Before: Simple row -->
   <div class="row">
     <div class="col-sm-3"><p>Email</p></div>
     <div class="col-sm-9"><p>{{ email }}</p></div>
   </div>

   <!-- After: Professional structure -->
   <div class="row align-items-center py-3 px-2">
     <div class="col-12 col-sm-4 col-lg-3">
       <p class="mb-2 mb-sm-0 fw-semibold">Email Address</p>
     </div>
     <div class="col-12 col-sm-8 col-lg-9">
       <p class="text-muted mb-0 d-flex align-items-center gap-2">
         <i class="fas fa-envelope text-secondary"></i>
         <span>{{ email|default:"—" }}</span>
       </p>
     </div>
   </div>
   ```

2. **CSS Styling**:
   ```css
   /* Hover effects, gradients, animations */
   .row:hover {
     background: linear-gradient(90deg, rgba(247, 192, 0, 0.05) 0%, transparent 100%);
     transform: translateX(4px);
   }
   ```

**Claude will generate:**
- ✅ Improved HTML with proper Bootstrap classes
- ✅ Responsive grid layout (mobile, tablet, desktop)
- ✅ Icon integration with Font Awesome
- ✅ Professional CSS with animations
- ✅ Hover states and transitions
- ✅ Accessibility improvements
- ✅ Mobile-first responsive design

## Designer Workflow

When you invoke `/designer`, Claude will follow this comprehensive process:

### Step 1: Analyze Current Code
- Read existing HTML template
- Review current CSS file
- Identify layout issues (alignment, spacing, grid problems)
- Check Bootstrap usage and responsive design
- Note accessibility gaps

### Step 2: Improve HTML Structure
- Optimize Bootstrap grid (proper `.row`, `.col-*` usage)
- Add proper alignment classes (`.align-items-center`, `.justify-content-between`)
- Include responsive utilities (`.d-none .d-md-block`)
- Add semantic HTML5 tags (`<section>`, `<header>`, `<article>`)
- Integrate icons with proper sizing
- Improve spacing with utility classes (`.p-*`, `.m-*`, `.g-*`)

### Step 3: Enhance CSS Styling
- Use CSS variables from brand kit
- Add modern effects (gradients, shadows, animations)
- Create hover states and transitions
- Implement responsive breakpoints
- Add accessibility features (focus states, reduced motion)

### Step 4: Deploy Changes
- Collect static files: `python manage.py collectstatic --noinput`
- Reload server: `kill -HUP $(pgrep -f "gunicorn.*ezzydelivery")`
- Update CSS version cache busting parameter

## Skills Applied

This command activates **comprehensive frontend design** with focus on:
- ✅ **HTML Structure**: Bootstrap grid, semantic tags, proper alignment
- ✅ **CSS Styling**: Brand consistency, modern design patterns
- ✅ **Responsive Design**: Mobile-first, breakpoints, utility classes
- ✅ **Accessibility**: WCAG 2.1, ARIA labels, keyboard navigation
- ✅ **Performance**: CSS transforms, optimized animations
- ✅ **Component Reusability**: DRY principles, modular design

## Related Commands

- `/frontend` - General frontend development
- `/css-fix` - Fix existing CSS issues
- `/component` - Create specific UI components
- `/page` - Create complete pages

## Design System Reference

### Brand Kit
**Location:** `static/webpages/css/brand-kit.css`

**Key Variables:**
```css
/* Colors */
--brand-primary: #f7c000;    /* Yellow */
--brand-secondary: #001f3f;  /* Navy */
--brand-accent: #ffd54f;     /* Light Yellow */

/* Typography */
--font-base: 0.875rem;       /* 14px */
--font-lg: 1rem;             /* 16px */
--font-xl: 1.125rem;         /* 18px */

/* Spacing */
--spacing-sm: 0.5rem;        /* 8px */
--spacing-md: 1rem;          /* 16px */
--spacing-lg: 1.5rem;        /* 24px */

/* Radius */
--radius-sm: 0.5rem;         /* 8px */
--radius-md: 0.75rem;        /* 12px */
--radius-lg: 1rem;           /* 16px */

/* Shadows */
--shadow-sm: 0 1px 2px rgba(0,0,0,0.05);
--shadow-md: 0 4px 6px rgba(0,0,0,0.07);
--shadow-lg: 0 10px 15px rgba(0,0,0,0.1);
```

### Bootstrap Utilities Quick Reference

**Grid System:**
- `.container`, `.container-fluid`
- `.row`, `.g-*` (gutters)
- `.col-*`, `.col-sm-*`, `.col-md-*`, `.col-lg-*`, `.col-xl-*`

**Flexbox:**
- `.d-flex`, `.d-inline-flex`
- `.justify-content-*` (start, center, end, between, around)
- `.align-items-*` (start, center, end, stretch)
- `.flex-row`, `.flex-column`
- `.gap-*` (1-5)

**Spacing:**
- `.p-*`, `.px-*`, `.py-*`, `.pt-*`, `.pb-*` (padding)
- `.m-*`, `.mx-*`, `.my-*`, `.mt-*`, `.mb-*` (margin)
- Values: 0, 1 (0.25rem), 2 (0.5rem), 3 (1rem), 4 (1.5rem), 5 (3rem)

**Typography:**
- `.fw-*` (normal, bold, semibold, light)
- `.text-*` (start, center, end, muted, primary, secondary)
- `.small`, `.lead`

**Display:**
- `.d-none`, `.d-block`, `.d-inline`, `.d-inline-block`
- `.d-sm-*`, `.d-md-*`, `.d-lg-*`, `.d-xl-*`

**Component Examples:**
- Profile: `core/templates/core/profile.html`
- Delivery Tasks: `delivery/templates/delivery/delivery_tasks.html`
- Dashboard: `business/templates/business/dashboard.html`

## Important Notes

⚠️ **Always improve BOTH HTML and CSS** - don't just focus on styling!
⚠️ **Use Bootstrap utilities** - don't reinvent the wheel with custom CSS
⚠️ **Mobile-first** - start with mobile layout, then add breakpoints
⚠️ **No inline styles** - all styles in external CSS files
⚠️ **Test responsive** - verify layout works on mobile, tablet, desktop
