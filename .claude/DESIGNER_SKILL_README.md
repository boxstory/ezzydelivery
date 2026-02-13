# Frontend Designer Skill - Summary

**Created:** 2026-02-13
**Status:** ✅ Active and synced

---

## Purpose

The `frontend-designer` skill focuses on **visual design** and **brand consistency** for EzzyDelivery, complementing the existing `frontend` skill which handles implementation (Bootstrap, HTMX, jQuery).

## Skill Separation

| Skill | Focus | Use When |
|-------|-------|----------|
| **frontend-designer** | Visual design, aesthetics, brand guidelines | Creating landing pages, hero sections, modern UI components |
| **frontend** | Implementation, Bootstrap, HTMX, jQuery | Adding interactivity, forms, AJAX, dashboard components |

## Brand Kit Verified

All brand colors, typography, spacing, and design tokens are sourced from:
- `webpages/static/webpages/css/brandkit-tokens.css`

### Actual EzzyDelivery Colors

```css
/* Primary Brand */
--brand-primary: #f7c000         /* Ezzy Yellow */
--brand-primary-dark: #f4c20d
--brand-navy: #001f3f            /* Navy blue for contrast */

/* Neutrals */
--brand-grey-500: #6c757d        /* WCAG AA compliant */
--brand-grey-700: #333
--brand-white: #ffffff
--brand-black: #000000
```

**NOT** generic indigo/pink colors!

## What's Included

### Design Tokens
- ✅ Correct Ezzy Yellow brand colors
- ✅ Navy blue and grey palette
- ✅ Brand gradients (yellow-white, black-navy, etc.)
- ✅ Typography scale (Inter, Poppins fonts)
- ✅ Spacing system (0.25rem - 2rem)
- ✅ Border radius (0.5rem - 1.125rem)
- ✅ Shadows (sm, md, lg)
- ✅ Transitions

### Component Templates
- Hero sections
- Feature grids
- Cards (with hover effects)
- Buttons (primary, secondary, outline, sizes)
- Glass morphism patterns
- Gradient backgrounds
- Smooth animations

### Design Principles
- Mobile-first responsive design
- WCAG 2.1 accessibility standards
- Performance optimization
- Semantic HTML structure

## Usage

### Activate with Command
```
/designer
```

### Reference in Prompts
```
"Use frontend-designer skill to create a hero section"
"Use frontend-designer skill to design a pricing table"
```

## Files

| File | Location | Synced To |
|------|----------|-----------|
| Skill | `.claude/skills/frontend-designer.md` | `~/.claude/skills/` |
| Command | `.claude/commands/designer.md` | `~/.claude/commands/` |

## Related Documentation

- **Existing skill:** `.claude/skills/frontend.md` (Bootstrap, HTMX)
- **Brand kit:** `webpages/static/webpages/css/brandkit.css`
- **Design tokens:** `webpages/static/webpages/css/brandkit-tokens.css`
- **Components:** `webpages/static/webpages/css/brandkit-components.css`

## Changes Made

1. **Initial creation** (df414b59) - Created skill with generic colors
2. **Brand correction** (ecdd7d50) - Updated with actual Ezzy Yellow colors
3. **Module reference** - Added correct brandkit file structure
4. **Skill clarity** - Added note: complements frontend.md

---

## Quick Reference

**Primary Color:** `var(--brand-primary)` → #f7c000 (Ezzy Yellow)
**Navy Contrast:** `var(--brand-navy)` → #001f3f
**Font:** `var(--brand-font-primary)` → "Inter", "Poppins"
**Shadow:** `var(--brand-shadow-md)`
**Radius:** `var(--brand-radius-md)` → 0.75rem (12px)
**Transition:** `var(--brand-transition)` → all 0.3s ease

