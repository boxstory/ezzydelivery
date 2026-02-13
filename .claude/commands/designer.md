# Designer Command

**Purpose:** Activate frontend designer mode for creating polished, modern UI components with EzzyDelivery branding.

## When to Use

- Designing new landing pages
- Creating UI components (cards, buttons, forms)
- Building hero sections or feature grids
- Implementing responsive layouts
- Styling with brand consistency

## Activation

```
/designer
```

## What This Does

When you use `/designer`, Claude will:

1. **Load Brand Kit Context**
   - All CSS variables from `brand-kit.css`
   - Color palette, typography scale, spacing system
   - Border radius, shadows, and design tokens

2. **Apply Design Principles**
   - Mobile-first responsive design
   - Accessibility standards (WCAG 2.1)
   - Modern UI patterns (glassmorphism, gradients, animations)
   - Consistent component architecture

3. **Follow EzzyDelivery Patterns**
   - Use semantic HTML
   - No inline styles or `<style>` tags
   - Link CSS in `{% block extra_css %}`
   - Follow naming: `{app}_{section}_{element}_{descriptor}`

4. **Optimize for Performance**
   - CSS best practices (transforms over layout properties)
   - Image optimization recommendations
   - Lazy loading strategies
   - Animation performance

## Example Usage

```
/designer

I need to create a pricing comparison table for the services page
```

Claude will generate:
- Semantic HTML structure
- CSS using brand kit variables
- Responsive breakpoints
- Hover/focus states
- Accessibility features

## Skills Applied

This command activates the **frontend-designer** skill with focus on:
- Brand consistency
- Modern design patterns
- Component reusability
- Performance optimization
- Accessibility compliance

## Related Commands

- `/frontend` - General frontend development
- `/css-fix` - Fix existing CSS issues
- `/component` - Create specific UI components
- `/page` - Create complete pages

## Design System Reference

**Brand Kit:** `static/webpages/css/brand-kit.css`

**Key Variables:**
- Colors: `--brand-primary`, `--brand-secondary`, etc.
- Typography: `--text-base`, `--font-bold`, etc.
- Spacing: `--spacing-md`, `--spacing-lg`, etc.
- Radius: `--radius-md`, `--radius-lg`, etc.
- Shadows: `--shadow-md`, `--shadow-lg`, etc.

**Component Examples:**
- Homepage: `webpages/templates/webpages/homepage.html`
- SEO pages: `webpages/templates/webpages/delivery_*.html`
- Dashboard: `business/templates/business/dashboard.html`
