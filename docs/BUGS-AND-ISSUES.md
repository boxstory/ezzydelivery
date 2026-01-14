# Bugs and Issues Tracker

## Active Bugs

| ID | Description | File(s) | Status | Priority |
|----|-------------|---------|--------|----------|
| B001 | Excessive !important usage (130+ instances) | workforce.css, base-forms.css, core.css | partial | high |
| B002 | Inline styles in templates (100+ instances) | Multiple templates | in-progress | high |
| B003 | Float-based layouts in volte.css (26+ instances) | business/static/volte1/css/volte.css | open | medium |
| B004 | Hardcoded pixel values (97 instances) | business.css, orders.css, product.css, volte.css | open | medium |
| B005 | Missing media queries for responsive design | mobile-app.css, base-forms.css | open | medium |
| B006 | Color contrast issues (.text-muted, warning badges) | Multiple templates | open | low |
| B007 | Print statements in views (47+ in orders/views.py) | orders/views.py | fixed | low |
| B008 | Inline onclick handlers (106 instances) | Fleet/DMS/Workforce templates | partial | low |
| B009 | Capitalized class names in bulk_order_entry.html | orders/templates/orders/bulk_order_entry.html | fixed | low |
| B010 | Form validation messages not styled consistently | orders/order_update.html | fixed | medium |

## In Progress

| ID | Description | Assigned To | Notes |
|----|-------------|-------------|-------|
| B002 | Inline styles extraction | QA fix agents | 45+ fixed, 190+ pending |

## Fixed (Archive)

| ID | Description | Fix Summary | Date |
|----|-------------|-------------|------|
| F001 | Missing auth decorators on order views | Added @login_required and @business_permission_required | 2026-01-13 |
| F002 | AJAX endpoints missing error handling | Added proper HTTP status codes and try/except | 2026-01-13 |
| F003 | Float layouts in orders.css and business.css | Converted to flexbox | 2026-01-13 |
| F004 | Missing alt text on images | Added descriptive alt attributes | 2026-01-13 |
| F005 | Missing focus indicators on buttons/inputs | Added focus-visible styles in core.css | 2026-01-13 |
| F006 | Order table not responsive | Added .order-table-wrapper with overflow-x | 2026-01-13 |
| F007 | Pagination touch targets too small | Enhanced to 44px minimum | 2026-01-13 |
| F008 | Business team templates missing image fallbacks | Added default avatars/logos | 2026-01-13 |
| F009 | Accordion state not preserved | Added sessionStorage state preservation | 2026-01-13 |
| F010 | Social auth template inheritance error | Fixed block structure in account/base.html | 2025-11-27 |
| F011 | Django i18n blocktrans syntax errors | Updated to Django 1.3+ syntax | 2025-11-27 |
| F012 | Print statements in orders/views.py | Replaced 27 print() calls with logger.debug() | 2026-01-14 |
| F013 | Form validation styling inconsistent | Verified CSS already exists in orders.css | 2026-01-14 |
| F014 | Inline styles in vehicle_document_detail.html | Previously extracted to workforce.css | 2026-01-14 |
| F015 | Inline styles in store_document_detail.html | Previously extracted to workforce.css | 2026-01-14 |
| F016 | base-forms.css !important abuse (90+ instances) | Refactored to use high specificity selectors; reduced to 2 unavoidable | 2026-01-14 |
| F017 | Inline onclick in driver_documents_list.html | Replaced with data attributes + event delegation | 2026-01-14 |
| F018 | Inline onclick in vehicle_documents_list.html | Replaced with data attributes + event delegation | 2026-01-14 |
| F019 | Inline onclick in store_documents_list.html | Replaced with data attributes + event delegation | 2026-01-14 |
| F020 | Inline styles in document list templates | Extracted to workforce.css (filter-row, btn-view-details, etc.) | 2026-01-14 |
| F021 | Inline <style> tags in bulk_order_entry.html (200+ lines) | Extracted to orders.css (excel-table styles) | 2026-01-14 |
| F022 | Inline onclick + styles in fleet_transactions.html | Replaced with data-action + event delegation; CSS classes extracted | 2026-01-14 |
| F023 | Inline onclick handlers in driver_reports.html | Replaced with data attributes + event delegation | 2026-01-14 |
| F024 | Inline onclick + styles in business_licenses_list.html | Replaced with data-view + event delegation; CSS classes extracted | 2026-01-14 |
| F025 | Inline onclick in dms_sync_monitor.html | Replaced with data-action + event delegation | 2026-01-14 |
| F026 | Inline onclick in dms_orders_list.html | Replaced with data-action + event delegation; CSS extracted | 2026-01-14 |
| F027 | Inline onclick in dms_drivers_list.html | Replaced with data-action + event delegation; CSS extracted | 2026-01-14 |
| F028 | Inline onclick + 40+ inline styles in dms_publish_order.html | Replaced with data-action; DMS CSS classes added | 2026-01-14 |
| F029 | Inline onclick handlers in user_verification_list.html | Replaced with data-action + event delegation | 2026-01-14 |
| F030 | Inline onclick handlers in orders_list_view.html | Replaced with data-filter, data-order-id + event delegation | 2026-01-14 |
| F031 | Inline onclick handlers in dl_list_incompleted.html | Replaced 15+ handlers with data attributes + event delegation | 2026-01-14 |

## Priority Order

1. **Security Issues** — Missing auth decorators (FIXED)
2. **Critical CSS** — !important abuse blocking other fixes
3. **Inline Styles** — Extract to CSS classes
4. **Responsive** — Mobile breakpoints
5. **Accessibility** — WCAG compliance
6. **Code Quality** — Class naming consistency

---

**Last Updated:** 2026-01-14
**Total Issues:** 250+ identified | 45+ fixed | 15+ in progress | 190+ pending
