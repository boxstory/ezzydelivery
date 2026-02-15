# Designer Command - Premium UI Mode

**You are a senior UI/UX designer. Your output must look like a polished SaaS product, NOT a Bootstrap tutorial.**

## CRITICAL: Design Quality Bar

Every element you create MUST pass this checklist:
- [ ] Would this look at home on Linear, Notion, or Stripe's dashboard?
- [ ] Does every interactive element have a hover/active state?
- [ ] Are labels uppercase + letter-spaced + small + muted? (section headers)
- [ ] Are values bold + dark + properly sized? (data display)
- [ ] Is there visual hierarchy? (hero > sections > fields > muted metadata)
- [ ] Does the spacing feel airy, not cramped? (min 0.875rem between sections)
- [ ] Are status indicators color-coded with semantic light backgrounds?

If any answer is NO, redesign before shipping.

## Design Vocabulary (Use These Patterns)

### 1. Section Headers (uppercase label style)
```css
.xyz__section-head {
    display: flex;
    align-items: center;
    gap: 0.4rem;
    font-size: 0.7rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: var(--brand-grey-500, #6c757d);
    padding-bottom: 0.375rem;
    border-bottom: 1px solid var(--brand-grey-200, #f0f0f0);
}
.xyz__section-head i {
    color: var(--brand-primary, #f7c000);  /* Yellow icon accent */
}
```

### 2. Data Fields (label-value pairs)
```css
.xyz__field {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0.4375rem 0;
    gap: 0.75rem;
}
.xyz__field:not(:last-child) {
    border-bottom: 1px solid var(--brand-grey-100, #fafafa);
}
.xyz__field__label {
    font-size: 0.75rem;
    color: var(--brand-grey-500);
}
.xyz__field__value {
    font-size: 0.8125rem;
    color: var(--brand-grey-800, #1f1f1f);
    font-weight: 500;
}
```

### 3. Hero Banners (navy gradient)
```css
background: linear-gradient(135deg, var(--brand-navy, #001f3f) 0%, var(--brand-navy-light, #003366) 100%);
color: #fff;
padding: 1rem 1.25rem;
border-radius: var(--brand-radius-sm, 0.5rem);
```

### 4. COD/Amount Highlights (amber gradient)
```css
background: linear-gradient(135deg, #fffbeb 0%, #fef3c7 100%);
border: 1px solid #fde68a;
border-radius: var(--brand-radius-sm);
/* Large amount: 1.375rem-1.75rem, font-weight: 700 */
/* Currency label: 0.65rem, uppercase, grey */
```

### 5. Contact Pill Buttons
```css
border-radius: 2rem;  /* Full pill */
padding: 0.35rem 0.75rem;
font-size: 0.75rem;
/* Phone: grey-100 bg, grey border -> navy on hover */
/* WhatsApp: #dcfce7 bg, #bbf7d0 border -> #22c55e on hover */
```

### 6. Status Badges (semantic colors)
```css
/* Always: light bg + matching dark text + inline-flex + gap + pill radius */
--success: bg #dcfce7, color #15803d;
--warning: bg #fef3c7, color #92400e;
--danger:  bg #fef2f2, color #dc2626;
--info:    bg #eff6ff, color #2563eb;
--muted:   bg var(--brand-grey-200), color var(--brand-grey-600);
```

### 7. Cards (modern, not Bootstrap default)
```css
.xyz__card {
    background: #fff;
    border-radius: var(--brand-radius-md, 0.75rem);
    border: 1px solid var(--brand-grey-200, #f0f0f0);
    overflow: hidden;
}
.xyz__card__header {
    padding: 0.625rem 1rem;
    font-size: 0.7rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: var(--brand-grey-500);
    border-bottom: 1px solid var(--brand-grey-200);
    background: var(--brand-grey-100, #fafafa);
}
.xyz__card__header i {
    color: var(--brand-primary);
}
/* NO bg-dark, bg-primary, bg-info Bootstrap headers! */
```

### 8. Driver/Person Cards (avatar style)
```css
/* Navy circle avatar with yellow icon */
.avatar {
    width: 2.25rem; height: 2.25rem;
    border-radius: 50%;
    background: var(--brand-navy);
    color: var(--brand-primary);
    display: flex; align-items: center; justify-content: center;
}
```

### 9. Notes/Callouts (left accent border)
```css
background: var(--brand-grey-100);
border-radius: 0.375rem;
border-left: 3px solid var(--brand-primary);
padding: 0.5rem 0.75rem;
```

### 10. Route Visualization (pickup -> dropoff)
```css
/* Blue circle for pickup, pink circle for dropoff */
/* Dashed line connector using repeating-linear-gradient */
/* Labels: uppercase, 0.65rem, grey-400, letter-spacing 0.04em */
```

### 11. Action Buttons
```css
/* Primary: navy bg, white text -> navy-light on hover + translateY(-1px) + shadow */
/* Secondary: grey-100 bg, grey border -> yellow bg on hover */
/* Both: 0.75rem font, 600 weight, flex:1 for equal width */
```

### 12. Hover/Interaction Effects
```css
/* Cards: box-shadow upgrade on hover */
/* Buttons: translateY(-1px) + shadow on hover */
/* Links: color transition (navy -> yellow) */
/* Mobile: scale(0.95) on :active for tap feedback */
/* Timing: 0.2s ease for controls, 0.15s for quick feedback */
```

## Brand Kit Tokens (ACTUAL file: `brandkit-tokens.css`)

```css
/* Colors */
--brand-primary: #f7c000;
--brand-navy: #001f3f;
--brand-navy-light: #003366;

/* Greys */
--brand-grey-100: #fafafa;  /* Backgrounds, alternating rows */
--brand-grey-200: #f0f0f0;  /* Borders, dividers */
--brand-grey-300: #dcdcdc;  /* Input borders */
--brand-grey-400: #b0b0b0;  /* Placeholder text, icons */
--brand-grey-500: #6c757d;  /* Labels, section headers */
--brand-grey-600: #555;     /* Secondary text */
--brand-grey-700: #333;     /* Primary text */
--brand-grey-800: #1f1f1f;  /* Headings, bold values */

/* Shadows */
--brand-shadow-sm: 0 0.0625rem 0.1875rem rgba(0,0,0,0.08);
--brand-shadow-md: 0 0.25rem 0.5rem rgba(0,0,0,0.1);

/* Radius */
--brand-radius-sm: 0.5rem;   /* 8px - buttons, small cards */
--brand-radius-md: 0.75rem;  /* 12px - cards */
--brand-radius-lg: 1.125rem; /* 18px - hero sections */

/* Spacing */
--spacing-xs: 0.25rem;
--spacing-sm: 0.5rem;
--spacing-md: 1rem;
--spacing-lg: 1.5rem;
--spacing-xl: 2rem;
```

## Typography Rules

| Element | Size | Weight | Color | Extra |
|---------|------|--------|-------|-------|
| Page title | 1.375rem | 700 | grey-800 | — |
| Section header | 0.7rem | 600-700 | grey-500 | uppercase, letter-spacing: 0.06em |
| Field label | 0.75rem | 400 | grey-500 | — |
| Field value | 0.8125rem | 500-600 | grey-800 | — |
| Muted metadata | 0.75rem | 400 | grey-400 | — |
| Badge text | 0.7rem | 600 | semantic color | uppercase optional |
| Code/IDs | 0.8125rem+ | 700 | grey-800 | font-family: monospace |
| Large amount | 1.375-1.75rem | 700 | grey-800 | — |
| Currency label | 0.65rem | 600 | grey-500 | uppercase |

## BEM Class Naming

Use short 2-4 letter prefixes per page/component:
- `odp__` = Order Detail Panel (slide-in)
- `odt-` = Order DeTails page (full page)
- `pwa-` = PWA mobile components
- Block: `.odp` / Element: `.odp__hero` / Modifier: `.odp__btn--primary`

## What NOT to Do

- **NO** `bg-dark`, `bg-primary`, `bg-info`, `bg-success` card headers (looks 2015)
- **NO** `<table class="table table-borderless">` for data display (use flex label-value pairs)
- **NO** Bootstrap `.badge bg-*` for statuses (use custom semantic badges)
- **NO** plain `<h5 class="mb-0">Section Title</h5>` headers (use uppercase + letter-spaced + icon)
- **NO** inline styles (`style="color: red;"`)
- **NO** `<style>` tags in templates
- **NO** generic Bootstrap cards without custom styling
- **NO** heavy colored headers (bg-primary text-white on card-header)
- **NO** table-based layouts for non-tabular data
- **NO** cramped spacing (always add breathing room between sections)

## What TO Do

- **YES** navy gradient hero banners for identity sections
- **YES** uppercase + letter-spaced + small + grey section headers with yellow icon
- **YES** flex-based label-value pairs with subtle bottom borders
- **YES** semantic light-background status badges
- **YES** amber gradient for monetary/COD highlights
- **YES** pill-shaped contact buttons with hover color transitions
- **YES** navy circular avatars with yellow icons for people
- **YES** yellow left-border callouts for notes
- **YES** monospace font for order numbers, task IDs, codes
- **YES** 2-column card layouts (col-sm-6) with vertical divider border
- **YES** dashed line connectors for route/timeline visualization
- **YES** translateY(-1px) + shadow hover effects on buttons
- **YES** alternating row backgrounds (nth-child) for lists

## Reference Files (Best Designs)

| Pattern | File |
|---------|------|
| Panel slide-in | `orders/parts/order_detail_panel.html` + CSS `.odp__*` |
| Full detail page | `orders/order_details.html` + CSS `.odt-*` |
| Mobile PWA | `business/static/business/css/business-mobile.css` `.pwa-*` |
| Brand tokens | `webpages/static/webpages/css/brandkit-tokens.css` |
| Components | `webpages/static/webpages/css/brandkit-components.css` |
| Status badges | `orders/static/orders/css/orders.css` `.ob--*` classes |

## Workflow

1. **Read** the current template and its CSS file
2. **Identify** what looks "basic" (Bootstrap defaults, table layouts, plain cards)
3. **Redesign** using the patterns above (BEM classes, flex layouts, brand tokens)
4. **Write** CSS in the app's CSS file (never inline, never `<style>`)
5. **Update** cache-busting version: `?v=YYYYMMDDx`
6. **Collect** static: `python manage.py collectstatic --noinput`
7. **Reload** server: `kill -HUP $(pgrep -f "gunicorn.*ezzydelivery" | head -1)`

ARGUMENTS: $ARGUMENTS
