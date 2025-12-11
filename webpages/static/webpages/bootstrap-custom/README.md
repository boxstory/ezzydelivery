# Custom Bootstrap Build for EzzyDelivery

## Overview

This directory contains a custom minimal Bootstrap 5.3.2 build tailored specifically for EzzyDelivery's needs. The custom build reduces file size while maintaining all functionality used in the application.

## Performance Improvements

- **Original Bootstrap CDN:** ~226 KB (minified)
- **Custom Bootstrap Build:** 190.72 KB (minified)
- **Size Reduction:** 15.6% smaller
- **Faster Page Load:** Reduced CSS download time

## Included Components

Based on comprehensive analysis of all templates, the following Bootstrap components are included:

### Core & Layout
- Functions, Variables, Maps, Mixins
- Root, Reboot, Typography
- Grid System (containers, rows, columns)
- Images

### UI Components
- **Buttons:** All button styles and button groups
- **Navigation:** Navbar, Nav, Dropdown
- **Cards:** Content cards
- **Tables:** Data tables
- **Forms:** All form controls (labels, inputs, selects, checkboxes, input groups, validation)
- **Badges:** Status badges
- **Alerts:** User feedback alerts
- **Pagination:** List pagination
- **List Groups:** Vertical lists
- **Modals:** Dialog boxes
- **Carousel:** Image carousels
- **Close button:** Modal/alert close buttons
- **Transitions:** Smooth animations

### Utilities
- All utility classes (display, flexbox, spacing, text, borders, shadows, etc.)
- Helpers API
- Responsive breakpoint classes

## Excluded Components

The following Bootstrap components were excluded because they're not used in the codebase:

- Accordion
- Breadcrumb
- Offcanvas
- Placeholders
- Progress bars
- Spinners
- Toasts
- Tooltips
- Popovers

## Files

- `custom-bootstrap.scss` - Main SCSS configuration file
- `compile_bootstrap.py` - Python compilation script using libsass
- `package.json` - NPM configuration (alternative method, not used)
- `bootstrap-5.3.2/` - Bootstrap source files
- `../css/bootstrap-custom.css` - Compiled expanded CSS (for debugging)
- `../css/bootstrap-custom.min.css` - Compiled minified CSS (production)

## Rebuilding

If you need to rebuild the custom Bootstrap (e.g., to add/remove components):

### Prerequisites
```bash
pip install libsass
```

### Build Steps

1. Edit `custom-bootstrap.scss` to add/remove component imports
2. Run the compilation script:
   ```bash
   cd webpages/static/webpages/bootstrap-custom
   python compile_bootstrap.py
   ```
3. Run Django collectstatic:
   ```bash
   python manage.py collectstatic --noinput
   ```

### Alternative Method (requires Node.js)
```bash
cd webpages/static/webpages/bootstrap-custom
npm install
npm run build
```

## Usage in Templates

The custom Bootstrap build is automatically loaded in `templates/includes/head.html`:

```html
<link href="{% static 'webpages/css/bootstrap-custom.min.css' %}" rel="stylesheet" type="text/css" />
```

## CSS Loading Order

1. **Custom Bootstrap** (190KB) - Core framework
2. **Base CSS** - Legacy utilities
3. **Brand Kit CSS** - Design system variables
4. **Brand Kit Overrides** - Override Bootstrap with brand colors
5. **App-specific CSS** - Per-page styles

## Testing

After any changes to the custom build:

1. Run `python manage.py collectstatic --noinput`
2. Test all major pages:
   - Homepage (`/`)
   - Business dashboard (`/dashboard/`)
   - Business portal
   - Fleet dashboard
   - Workforce dashboard
3. Verify Bootstrap JavaScript components still work:
   - Modals (business profile portfolio)
   - Dropdowns (navigation menus)
   - Collapse (mobile sidebar)
   - Carousel (if visible)

## Maintenance

### When to Rebuild

Rebuild the custom Bootstrap if:
- You add new pages that use Bootstrap components not currently included
- You want to remove unused components to reduce size further
- You need to update to a newer Bootstrap version
- Brand color variables in brand-kit-overrides.css are updated

### File Size Monitoring

After rebuilding, always check the output file sizes:
```bash
ls -lh ../css/bootstrap-custom*.css
```

Target size should remain under 200 KB (minified) to maintain performance benefits.

## Bootstrap JavaScript

Bootstrap JavaScript components are still loaded from CDN:
- Modal.js
- Collapse.js
- Dropdown.js

Location: `templates/includes/scripts.html`

If needed, you can also create a custom JavaScript build using the same approach.

## Analysis Results

The custom build was created based on analysis of 50+ templates:

**Top files with Bootstrap usage:**
1. `templates/includes/navbar.html` - Heavy navbar/dropdown usage
2. `business/templates/business/frontend/business_profile.html` - 6+ modals
3. `templates/dashboard_base.html` - Dashboard layout
4. `webpages/templates/webpages/index.html` - Homepage components
5. `delivery/templates/delivery/frontend/dl_address_link.html` - Forms
6. `workforce/templates/workforce/workflow_guide.html` - Content layout

**Essential utility classes:**
- Grid: `container`, `row`, `col-*`, `col-md-*`, `col-lg-*`
- Flexbox: `d-flex`, `justify-content-*`, `align-items-*`
- Display: `d-none`, `d-block`, `d-md-none`, `d-lg-block`
- Spacing: `m-*`, `p-*`, `mt-*`, `mb-*`, `mx-auto`
- Text: `text-center`, `text-end`, `fw-bold`, `text-muted`
- Borders: `border`, `border-bottom`, `rounded`
- Backgrounds: `bg-light`, `bg-dark`, `bg-primary`

## Version History

- **v1.0.0** (2025-11-13) - Initial custom build
  - Based on Bootstrap 5.3.2
  - 15.6% size reduction
  - All used components included
  - All unused components excluded

## Support

For issues or questions about the custom Bootstrap build, refer to:
- Bootstrap documentation: https://getbootstrap.com/docs/5.3/
- libsass documentation: https://sass.github.io/libsass-python/
