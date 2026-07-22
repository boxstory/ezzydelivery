---
name: brandkit
description: EzzyDelivery Brand Kit — canonical design tokens (Ezzy Yellow / Navy palette, spacing, radii, shadows, type scale) plus brand-supporting component recipes (heroes, stat tiles, console tables, status system, buttons, forms, empty states, QNAS plate). Load BEFORE any UI design or styling work, including when using frontend-designer, impeccable, design-taste-frontend, or the /frontend-design plugin skill — these tokens and rules override any generic aesthetic the other skills suggest.
---

# EzzyDelivery Brand Kit

Single source of truth: `webpages/static/webpages/css/brandkit.css` (+ `brandkit-components.css`, `brandkit-overrides.css`). Never hardcode a hex that has a token.

## Brand Personality

Qatar logistics operator. **Restrained enterprise console, not a consumer app.** Monochrome ink on white, hairline borders, the yellow accent used *once* per view for the primary action or identity mark. Navy carries authority surfaces (heroes, filter bars, ledger headers). Reject candy pastels, bright chips, full-radius glow fields.

## Core Tokens

### Identity
| Token | Value | Use |
|---|---|---|
| `--brand-primary` | `#f7c000` Ezzy Yellow | THE accent — primary CTA, active state, identity mark. Once per view. |
| `--brand-primary-dark` | `#f4c20d` | Hover/darker yellow |
| `--brand-secondary` | `#fff7d6` | Light yellow tint background |
| `--brand-accent` | `#fef9e6` | Faintest yellow wash |
| `--brand-navy` | `#001f3f` | Authority surfaces: heroes, table headers, footers |
| `--brand-navy-light` | `#003366` | Navy gradient partner, hover |
| `--brand-black` / `--brand-white` | `#000` / `#fff` | |

### Ink scale (greys)
`--brand-grey-100 #fafafa · 200 #f0f0f0 · 300 #dcdcdc · 400 #b0b0b0 · 500 #6c757d (AA on white) · 600 #555 · 700 #333 · 800 #1f1f1f`
Extended (Bootstrap-aligned): `50 #f8f9fa · 150 #e9ecef · 250 #dee2e6 · 450 #9ca3af · 550 #6b7280 · 650 #374151 · 750 #e5e7eb · 850 #f3f4f6 · bs #212529`

### Semantic sets (always bg + text pair, never solid fills for status)
| State | Text | Background |
|---|---|---|
| success | `--brand-success #15803d` (dark `#065f46`) | `--brand-success-bg #dcfce7` |
| warning | `--brand-warning #d97706` / text `#92400e` | `--brand-warning-bg #fef3c7` |
| danger | `--brand-danger #dc2626` (dark `#991b1b`) | `--brand-danger-bg #fef2f2` |
| info | `--brand-info #2563eb` (dark `#1e40af`) | `--brand-info-bg #eff6ff` |

### Gradients / Shadows / Radii / Motion
- `--brand-gradient-navy` (navy→navy-light 135deg) — heroes; `--brand-gradient-yellow-white`, `--brand-gradient-black-grey`, `--brand-gradient-yellow-dark`
- `--brand-shadow-sm|md|lg` — resting cards use border only; shadow arrives on hover
- `--brand-radius-sm 0.5rem · md 0.75rem · lg 1.125rem` — pills only for badges
- `--brand-transition: all 0.3s ease` (micro-interactions prefer 0.2s)

### Type & spacing
- `--brand-font-primary: "Inter", "Poppins", sans-serif`; weights 400/600; base `0.875rem`, heading `1.25rem`
- `--spacing-xs 0.25 · sm 0.5 · md 1 · lg 1.5 · xl 2 (rem)`
- Scale: page title 1.375rem/700 · section header 0.7rem/600 uppercase ls .06em grey-500 · label 0.75rem grey-500 · value 0.8125rem/600 grey-800 · big amount 1.375–1.75rem/700 · code/IDs 0.8125rem/700 mono

## Ready-made components (`brandkit-components.css`)

Use before writing new CSS: `.bk-btn--primary|secondary|success|danger|gradient`, `.bk-card`, `.bk-card--dark|highlight`, `.bk-badge--primary|success|warning|error|info`, `.bk-alert--*` (plus legacy `.badge-brand-*`, `.alert-*`). Bootstrap `.btn`/`.form-control`/`.card` stay the base — BEM classes only add what Bootstrap lacks.

## Brand-Supporting Design Recipes

### 1. Navy hero / page header
```css
.xyz__hero { background: var(--brand-gradient-navy); color: #fff;
  padding: 1rem 1.25rem; border-radius: var(--brand-radius-sm); }
.xyz__hero-kicker { font-size: 0.7rem; text-transform: uppercase;
  letter-spacing: 0.08em; color: var(--brand-primary); font-weight: 600; }
```
Yellow appears only in the kicker/accent rule — the surface itself stays navy.

### 2. Stat / KPI tile
```css
.xyz__stat { background: #fff; border: 1px solid var(--brand-grey-200);
  border-radius: var(--brand-radius-md); padding: 0.75rem 1rem; }
.xyz__stat-label { font-size: 0.65rem; font-weight: 600; text-transform: uppercase;
  letter-spacing: 0.06em; color: var(--brand-grey-500); }
.xyz__stat-value { font-size: 1.375rem; font-weight: 700; color: var(--brand-grey-800); }
.xyz__stat--flag { border-left: 3px solid var(--brand-primary); }  /* the one accent */
```

### 3. Enterprise console table (ledger)
```css
.xyz__table thead th { background: var(--brand-navy); color: #fff;
  font-size: 0.7rem; font-weight: 600; text-transform: uppercase;
  letter-spacing: 0.06em; border: 0; }
.xyz__table tbody td { font-size: 0.8125rem; color: var(--brand-grey-800);
  border-bottom: 1px solid var(--brand-grey-200); }
.xyz__table tbody tr:hover { background: var(--brand-grey-50); }
.xyz__table .num { font-family: ui-monospace, monospace; font-weight: 700; }
```
Amounts/IDs in mono; row hover is a grey wash, never yellow.

### 4. Status system (swatch + text — NOT loud pills)
```css
.xyz__status { display: inline-flex; align-items: center; gap: 0.375rem;
  font-size: 0.7rem; font-weight: 600; }
.xyz__status::before { content: ""; width: 8px; height: 8px; border-radius: 50%; }
.xyz__status--success { color: var(--brand-success); }
.xyz__status--success::before { background: var(--brand-success-light); }
```
Where a filled badge is warranted (lists, kanban), use the semantic bg+text pairs above at 0.7rem/600 — never white-on-bright.

### 5. Buttons
- Primary action: navy bg → navy-light hover, `translateY(-1px)` + `--brand-shadow-sm`; OR yellow (`.bk-btn--primary`) when it's the page's single hero CTA.
- Secondary: `grey-100` bg, `grey-300` border, grey-800 text → yellow tint (`--brand-secondary`) on hover.
- Ghost/danger: transparent with semantic text color; danger fills only on confirm steps.
- 0.75rem/600; never two yellow buttons in one view.

### 6. Forms
- Base = Bootstrap `.form-control`/`.form-select` + brand focus: `border-color: var(--brand-primary); box-shadow: none;`
- Never `background:` shorthand on inputs/selects that carry a background-image (custom arrows) — declare `background-image/repeat/size/position` longhands.
- Dark navy surface (hero filter bars): field `rgba(255,255,255,0.08)` bg, `rgba(255,255,255,0.25)` border, white text; `option { color:#1a1a2e; background:#fff; }`; placeholder `rgba(255,255,255,0.45)`; focus border yellow.

### 7. Empty state
```css
.empty-state { text-align: center; padding: 2.5rem 1rem; color: var(--brand-grey-500); }
.empty-state i { font-size: 2rem; color: var(--brand-grey-300); }
/* one-line explanation + optional secondary-style action; no illustration clutter */
```

### 8. Amount / COD highlight
```css
.xyz__cod { background: linear-gradient(135deg, #fffbeb, var(--brand-warning-bg));
  border: 1px solid #fde68a; border-radius: var(--brand-radius-sm); }
/* amount 1.375–1.75rem/700 grey-800; "QAR" 0.65rem/600 uppercase grey-500 */
```

### 9. QNAS plate (shared signature)
Order/delivery pages carry the `.qnas-plate` Qatar number-plate mark (defined at end of `workforce.css`) — reuse it, don't re-draw plates.

### 10. Timeline / steps
Vertical hairline (`grey-200`), 8px dots using semantic colors, current step dot in `--brand-primary`, labels 0.75rem grey-500, timestamps mono 0.7rem grey-400.

### 11. Mobile PWA surfaces
`d-md-none` mobile-only / `d-none d-md-block` desktop-only; body class (`fleet-mobile`, `business-mobile`) + app CSS variables; touch targets ≥ 44px; `:active { transform: scale(0.95); }`.

## Hard Rules (override everything)

1. No inline styles / `<style>` tags — CSS files linked via `{% block extra_css %}`, bump `?v=` on every edit.
2. Bootstrap utilities first for layout; custom CSS only for visual styling Bootstrap lacks.
3. BEM with app prefix (`block__element--modifier`); never re-declare Bootstrap base styles in BEM classes.
4. Yellow is scarce. If a design uses `--brand-primary` more than ~twice per view, cut it back.
5. WCAG AA: body text ≥ grey-500 on white; never yellow text on white.
