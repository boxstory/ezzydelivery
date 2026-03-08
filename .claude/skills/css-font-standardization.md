# CSS Font Size Standardization Skill

## Purpose
Standardize font sizes across the entire project to a consistent `.75rem` for compact, uniform typography.

## When to Use
- When font sizes need to be made consistent across dashboards
- After adding new CSS files or modules
- When users request compact/smaller font sizes
- During UI consistency audits

## Target Files
Project CSS files (exclude Bootstrap, FontAwesome, and other third-party libraries):

### Business Dashboard
- `business/static/business/css/business.css`
- `business/static/business/css/business-mobile.css`
- `business/static/volte1/css/volte.css`

### Orders Module
- `orders/static/orders/css/orders.css`

### Fleet/Driver Module
- `fleet/static/fleet/css/fleet.css`
- `fleet/static/fleet/css/fleet-mobile.css`

### Core/Shared
- `core/static/core/css/core.css`

### Workforce Dashboard
- `workforce/static/workforce/css/workforce.css`

### Warehouse & Delivery
- `warehouse/static/warehouse/css/warehouse.css`
- `delivery/static/delivery/css/delivery.css`

## Standard Font Size
`.75rem` - Used for all text, forms, tables, cards, buttons, badges, and UI elements

## Font Sizes to Replace
Replace these with `.75rem`:
- `0.375rem` (tiny icons)
- `0.5rem` (very small text)
- `0.5625rem` (small icons)
- `0.55rem` (badges)
- `0.58rem` (micro text)
- `0.6rem` (small badges)
- `0.625rem` (compact text)
- `0.65rem` (compact labels)
- `0.68rem` (table cells)
- `0.6875rem` (detail text)
- `0.688rem` (variants)
- `0.7rem` (buttons, small text)
- `0.75rem` (normalize to `.75rem`)
- `0.8rem` (form fields)
- `0.8125rem` (timeline)
- `0.812rem` (variants)
- `0.85rem` (labels)
- `0.875rem` (nav links, table headers)
- `0.9rem` (page subtitles)
- `0.875rem` (timestamps)
- `0.95rem` (content)

## Sizes to PRESERVE
Keep these unchanged (headings and display text):
- `1rem` and above (headings, hero text, display values)
- CSS variables like `var(--brand-font-size-xl)`

## Implementation Script

```bash
# Process all target CSS files
for file in \
  business/static/business/css/business.css \
  business/static/business/css/business-mobile.css \
  business/static/volte1/css/volte.css \
  orders/static/orders/css/orders.css \
  fleet/static/fleet/css/fleet.css \
  fleet/static/fleet/css/fleet-mobile.css \
  core/static/core/css/core.css \
  workforce/static/workforce/css/workforce.css \
  warehouse/static/warehouse/css/warehouse.css \
  delivery/static/delivery/css/delivery.css; do

  if [ -f "$file" ]; then
    echo "Processing: $file"

    # Replace all target font sizes with .75rem
    sed -i 's/font-size: 0\.375rem/font-size: .75rem/g' "$file"
    sed -i 's/font-size: 0\.5rem/font-size: .75rem/g' "$file"
    sed -i 's/font-size: 0\.5625rem/font-size: .75rem/g' "$file"
    sed -i 's/font-size: 0\.55rem/font-size: .75rem/g' "$file"
    sed -i 's/font-size: 0\.58rem/font-size: .75rem/g' "$file"
    sed -i 's/font-size: 0\.6rem/font-size: .75rem/g' "$file"
    sed -i 's/font-size: 0\.625rem/font-size: .75rem/g' "$file"
    sed -i 's/font-size: 0\.65rem/font-size: .75rem/g' "$file"
    sed -i 's/font-size: 0\.68rem/font-size: .75rem/g' "$file"
    sed -i 's/font-size: 0\.6875rem/font-size: .75rem/g' "$file"
    sed -i 's/font-size: 0\.688rem/font-size: .75rem/g' "$file"
    sed -i 's/font-size: 0\.7rem/font-size: .75rem/g' "$file"
    sed -i 's/font-size: 0\.75rem/font-size: .75rem/g' "$file"
    sed -i 's/font-size: 0\.8rem/font-size: .75rem/g' "$file"
    sed -i 's/font-size: 0\.8125rem/font-size: .75rem/g' "$file"
    sed -i 's/font-size: 0\.812rem/font-size: .75rem/g' "$file"
    sed -i 's/font-size: 0\.85rem/font-size: .75rem/g' "$file"
    sed -i 's/font-size: 0\.875rem/font-size: .75rem/g' "$file"
    sed -i 's/font-size: 0\.9rem/font-size: .75rem/g' "$file"
    sed -i 's/font-size: 0\.9375rem/font-size: .75rem/g' "$file"
    sed -i 's/font-size: 0\.95rem/font-size: .75rem/g' "$file"
  fi
done

echo "✓ Font size standardization complete!"
```

## Verification Commands

```bash
# Count .75rem instances in each file
for file in business/static/business/css/business.css \
  orders/static/orders/css/orders.css \
  fleet/static/fleet/css/fleet.css \
  core/static/core/css/core.css \
  workforce/static/workforce/css/workforce.css; do
  total=$(grep -c 'font-size: \.75rem' "$file" 2>/dev/null || echo 0)
  echo "$(basename $file): $total instances of .75rem"
done

# Check for remaining small font sizes
grep -r "font-size: 0\.[0-9]rem" business/static/business/css/ \
  orders/static/orders/css/ \
  fleet/static/fleet/css/ \
  core/static/core/css/ \
  workforce/static/workforce/css/ \
  | grep -v "\.75rem" \
  | grep -v "1\."
```

## Post-Update Steps

1. **Collect Static Files**:
   ```bash
   python manage.py collectstatic --noinput
   ```

2. **Reload Production Server** (if applicable):
   ```bash
   kill -HUP $(pgrep -f "gunicorn.*ezzydelivery" | head -1)
   ```

3. **Verify Changes**:
   - Check business dashboard
   - Check workforce dashboard
   - Check driver portal
   - Test forms, tables, and cards

## Elements Affected

✅ Paragraphs (`p`)
✅ Spans (`span`)
✅ Form labels (`label`, `.form-label`)
✅ Form inputs (`input`, `select`, `textarea`, `.form-control`, `.form-select`)
✅ Table headers and cells (`th`, `td`)
✅ Card titles and content (`.stat-card-title`, `.card-body`)
✅ Buttons and badges (`.btn`, `.badge`)
✅ Navigation links (`.nav-link`)
✅ Icons and small text
✅ All dashboard UI elements

## Expected Results

- **563+ instances** of `.75rem` across all files
- **0 small font sizes** remaining (0.5rem - 0.95rem)
- **Consistent typography** across all dashboards
- **Compact, uniform appearance** throughout the application

## Notes

- **DO NOT** modify Bootstrap CSS files
- **DO NOT** modify third-party library CSS (FontAwesome, etc.)
- **PRESERVE** font sizes 1rem and above (headings, display text)
- **PRESERVE** CSS variables like `var(--brand-font-size-*)`
- **ALWAYS** collect static files after making changes
- **ALWAYS** test in both business and workforce dashboards

## History

- **2026-02-13**: Initial standardization - 10 CSS files updated, 563+ instances standardized
