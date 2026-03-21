# Workforce Pages - Test Checklist

## ✅ All CSS Files Deployed

**Location**: `staticroot/workforce/css/`

| File | Size | Status |
|------|------|--------|
| workforce-base.css | 16 KB | ✅ |
| workforce-pages.css | 13 KB | ✅ |
| fleet_cod_in_hand.css | 17 KB | ✅ |
| drivers_list.css | 8.9 KB | ✅ |
| sellers_list.css | 7.3 KB | ✅ |
| order_detail.css | 9.6 KB | ✅ |

**Total CSS**: ~72 KB (uncompressed)

---

## 🧪 Testing URLs

### Priority HIGH (User-Facing Pages)

#### Fleet & Finance
- [ ] http://127.0.0.1:8004/workforce/fleet/cod-in-hand/
  - Expected: Navy gradient hero, yellow-accented stats cards, grid/list toggle
  - CSS: `fleet_cod_in_hand.css`

- [ ] http://127.0.0.1:8004/workforce/fleet/transactions/
  - Expected: Transaction list with filters
  - CSS: `workforce-pages.css`

- [ ] http://127.0.0.1:8004/workforce/fleet/earnings/
  - Expected: Earnings grid with driver cards
  - CSS: `workforce-pages.css`

#### Drivers
- [ ] http://127.0.0.1:8004/workforce/drivers/
  - Expected: Driver cards in grid layout, search & filters
  - CSS: `drivers_list.css`

- [ ] http://127.0.0.1:8004/workforce/drivers/active/
  - Expected: Active driver cards with green status
  - CSS: `drivers_list.css`

- [ ] http://127.0.0.1:8004/workforce/drivers/pending/
  - Expected: Pending driver cards with yellow status
  - CSS: `drivers_list.css`

- [ ] http://127.0.0.1:8004/workforce/drivers/{id}/
  - Expected: Driver detail with breadcrumbs, stats
  - CSS: `workforce-pages.css`

#### Sellers/Business
- [ ] http://127.0.0.1:8004/workforce/sellers/
  - Expected: Seller cards with logos, statistics
  - CSS: `sellers_list.css`

- [ ] http://127.0.0.1:8004/workforce/sellers/pending/
  - Expected: Pending sellers with approval panels
  - CSS: `sellers_list.css`

- [ ] http://127.0.0.1:8004/workforce/business/licenses/
  - Expected: License cards in grid
  - CSS: `workforce-pages.css`

#### Orders
- [ ] http://127.0.0.1:8004/workforce/orders/{id}/
  - Expected: Order detail with timeline, customer info, payment summary
  - CSS: `order_detail.css`

- [ ] http://127.0.0.1:8004/workforce/orders/add/
  - Expected: Order add form with proper styling
  - CSS: `workforce-pages.css`

- [ ] http://127.0.0.1:8004/workforce/orders/bulk-import/
  - Expected: Upload zone with drag-and-drop styling
  - CSS: `workforce-pages.css`

### Priority MEDIUM (Admin Features)

#### DMS Integration
- [ ] http://127.0.0.1:8004/workforce/dms/analytics/
  - Expected: Analytics grid with charts
  - CSS: `workforce-pages.css`

- [ ] http://127.0.0.1:8004/workforce/dms/sync/
  - Expected: Sync status indicators
  - CSS: `workforce-pages.css`

#### Inventory
- [ ] http://127.0.0.1:8004/workforce/inventory/reports/
  - Expected: Report grid with charts
  - CSS: `workforce-pages.css`

- [ ] http://127.0.0.1:8004/workforce/inventory/restock/
  - Expected: Restock items with warning borders
  - CSS: `workforce-pages.css`

- [ ] http://127.0.0.1:8004/workforce/products/requests/
  - Expected: Request cards with status badges
  - CSS: `workforce-pages.css`

#### Documents
- [ ] http://127.0.0.1:8004/workforce/documents/store/
  - Expected: Document grid with cards
  - CSS: `workforce-pages.css`

- [ ] http://127.0.0.1:8004/workforce/documents/driver/
  - Expected: Driver documents grid
  - CSS: `workforce-pages.css`

- [ ] http://127.0.0.1:8004/workforce/documents/vehicle/
  - Expected: Vehicle documents grid
  - CSS: `workforce-pages.css`

### Priority LOW (Rarely Used)

#### Admin & Reports
- [ ] http://127.0.0.1:8004/workforce/staff/contacts/
  - Expected: Contact cards with avatars
  - CSS: `workforce-pages.css`

- [ ] http://127.0.0.1:8004/workforce/staff/reports/
  - Expected: Report grid
  - CSS: `workforce-pages.css`

- [ ] http://127.0.0.1:8004/workforce/workflow/guide/
  - Expected: Guide sections with numbered steps
  - CSS: `workforce-pages.css`

---

## ✅ What to Check

### Visual Elements
- [ ] **Hero sections**: Navy gradient background, yellow icons, white text
- [ ] **Statistics cards**: White background, colored left border, hover effect
- [ ] **Buttons**: Yellow gradient primary, outline secondary, proper hover states
- [ ] **Cards**: White background, grey border, rounded corners, shadow on hover
- [ ] **Tables**: Striped rows, hover effect, sortable headers
- [ ] **Filters**: Proper input styling, focus states with yellow outline
- [ ] **Badges**: Colored backgrounds (success/warning/error/info)

### Responsive Behavior
- [ ] **Desktop (1920px)**: Multi-column grid layouts
- [ ] **Tablet (768px)**: Reduced columns, stacked filters
- [ ] **Mobile (375px)**: Single column, full-width cards, mobile-optimized nav

### Interactive Elements
- [ ] **Hover states**: Cards lift, buttons darken, borders change color
- [ ] **Focus states**: Yellow outline on keyboard navigation
- [ ] **Active states**: Buttons pressed, toggles switched
- [ ] **Transitions**: Smooth 300ms animations

### Accessibility
- [ ] **Contrast ratios**: Text readable on all backgrounds
- [ ] **Touch targets**: Minimum 44px for mobile
- [ ] **Keyboard navigation**: Tab through all interactive elements
- [ ] **Screen readers**: Proper labels and ARIA attributes

### Performance
- [ ] **Load time**: CSS loads < 100ms
- [ ] **No layout shifts**: Content doesn't jump on load
- [ ] **Smooth scrolling**: No jank or stuttering
- [ ] **Print mode**: Proper print styles (hide actions, optimize layout)

---

## 🐛 Common Issues to Watch For

### CSS Not Loading
**Symptoms**: Page looks unstyled, using default browser styles
**Fix**:
```bash
# Clear browser cache (Ctrl+Shift+R)
# Or collect static again
python manage.py collectstatic --clear --noinput
```

### Styles Partially Applied
**Symptoms**: Some elements styled, others not
**Fix**: Check browser console for 404 errors on CSS files

### Mobile View Broken
**Symptoms**: Desktop layout on mobile
**Fix**: Check viewport meta tag in base template

### Colors Look Wrong
**Symptoms**: Different colors than expected
**Fix**: Verify Brand Kit Pro CSS is loaded before custom CSS

---

## 📊 Expected Metrics

| Metric | Target | How to Measure |
|--------|--------|----------------|
| **Page Load** | < 2s | Chrome DevTools Network tab |
| **CSS Load** | < 100ms | Network tab, filter CSS |
| **First Paint** | < 500ms | Lighthouse performance |
| **Layout Shift** | < 0.1 | Lighthouse CLS score |
| **Accessibility** | 90+ | Lighthouse accessibility |

---

## ✅ Sign-Off Checklist

- [ ] All priority HIGH pages tested
- [ ] Mobile responsive on 3 breakpoints
- [ ] Cross-browser (Chrome, Firefox, Safari, Edge)
- [ ] Accessibility audit passed
- [ ] No console errors
- [ ] Print preview works
- [ ] Performance metrics met
- [ ] User acceptance approved

---

## 🚀 Deployment Steps

1. ✅ Static files collected
2. ✅ CSS files in staticroot
3. ✅ Base template updated
4. [ ] Test on development server
5. [ ] Test on staging server (if available)
6. [ ] Deploy to production
7. [ ] Verify on production
8. [ ] Monitor for errors

---

**Status**: Ready for Testing ✅
**Date**: February 19, 2026
**CSS Files**: 6 files, ~72 KB
**Templates Covered**: 46/46 (100%)
