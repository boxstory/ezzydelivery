# QA Evaluation Todos

This file tracks UI/CSS issues, alignment problems, and bugs discovered during page evaluation.
**Updated automatically by QA agent. Fix agent works on items marked `[ ]`.**

---

## Status Legend
- `[ ]` = Needs fix (Fix agent should work on these)
- `[x]` = Fixed
- `[!]` = Critical priority
- `[?]` = Needs investigation

---

## CRITICAL CSS ISSUES

### 1. Excessive !important Usage (130+ instances)

#### workforce/static/workforce/css/workforce.css
- [ ] Line 1781: `font-size: 1rem !important;` - Remove !important, fix specificity
- [ ] Line 1859: `margin-left: 0 !important;` - Remove !important
- [ ] Line 2739: `display: none !important;` - Refactor to proper toggle class
- [ ] Lines 2746-2803: 20+ !important declarations - Restructure CSS hierarchy
- [ ] Line 3155: `display: none !important;` - Use proper toggle mechanism

#### templates/static/base-forms.css (90+ instances)
- [ ] Lines 449-452: Flexbox layout with !important - Remove flags
- [ ] Lines 460-464: Button styling with !important - Fix specificity
- [ ] Lines 472-476: Input visibility with !important - Refactor
- [ ] Lines 484-499: Checkbox styling all !important - Restructure
- [ ] Lines 507-548: Form control states - Remove !important
- [ ] Lines 559-601: Label styling - Fix specificity chain
- [ ] Lines 619-717: Form validation states - Refactor approach

#### templates/static/business_dashboard_base.css
- [ ] Lines 41-42: `padding-left: 0 !important; padding-right: 0 !important;`
- [ ] Lines 48-49: `width: 100% !important; display: block !important;`
- [ ] Line 55: `display: flex !important;`
- [ ] Line 75: `flex: 1 1 auto !important;`

#### core/static/core/css/core.css
- [ ] Line 1408: `padding: 1.5rem !important;`
- [ ] Lines 1426-1473: 15+ !important declarations

---

### 2. Inline Styles in Templates (100+ instances)

#### webpages/templates/webpages/testimonials.html
- [x] Line 89: `style="text-align: center; padding: 2rem 0;"` - Extracted to `.testimonial-cta-section`
- [x] Line 90: `style="font-size: 2rem; font-weight: 700;..."` - Created `.testimonial-title`
- [x] Line 93: `style="font-size: 1.125rem; color:..."` - Created `.testimonial-subtitle`
- [x] Line 97: Complex gradient button style - Created `.btn-gradient-primary`

#### workforce/templates/workforce/wf_orders_reported.html
- [x] Line 38: `style="color: #008000;"` - Fixed: Using Bootstrap `.text-success` class
- [x] Line 40: `style="color: #ff0000;"` - Fixed: Using Bootstrap `.text-danger` class

#### workforce/templates/workforce/wf_orders_dms_updated.html
- [x] Line 173: `style="opacity: 0.3;"` - Fixed: Created `.opacity-30` in workforce.css

#### workforce/templates/workforce/wf_orders_by_seller.html
- [x] Line 33: `style="visibility: hidden;"` - Fixed: Using Bootstrap `.invisible` class
- [ ] Lines 84-85: Icon container styles - Extract to component class

#### workforce/templates/workforce/vehicle_document_detail.html
- [x] Lines 18-174: 30+ inline styles - Fixed: Extracted to workforce.css (page-title, document-back-section, section-container, info-grid, info-row, etc.)
- [x] Create component classes for document details page - Fixed: Uses document-detail-container, document-modal, document-form-grid classes

#### workforce/templates/workforce/store_document_detail.html
- [x] Lines 18-155: 25+ inline styles - Fixed: Extracted to workforce.css (uses same component classes as vehicle_document_detail)

#### orders/templates/orders/verify_location.html
- [x] Line 14: `style="font-size: 2rem;..."` - Created `.verify-title` class
- [x] Line 20: `style="font-size: 1.25rem;..."` - Created `.verify-section-title` class
- [x] Line 64: `style="grid-column: 1 / -1;"` - Created `.full-width-column` class

#### workforce/templates/workforce/suppliers_list.html
- [x] Lines 18-95: 15+ inline styles - Extracted to workforce.css (supplier-stats-grid, supplier-stat-card, supplier-icon, badge-count, label-hidden)

#### workforce/templates/workforce/staff_contacts.html
- [x] Lines 19-37: Multiple inline styles - Extracted to workforce.css (filter-actions-container, filter-search-wrapper, filter-buttons-group, btn-print, btn-export, results-counter)

#### product/templates/product/parts/product_card.html
- [x] Line 13: `style="background-image: url(...)` - Fixed: converted to scoped style tag with unique ID

---

### 3. Float-Based Layouts (150+ instances - Legacy)

#### orders/static/orders/css/orders.css
- [x] Line 684: `float: left;` - Converted to flexbox
- [x] Line 688: `float: right;` - Converted to flexbox

#### business/static/business/css/business.css
- [x] Line 2167: `float: left;` - Converted to flexbox
- [x] Line 2171: `float: right;` - Converted to flexbox

#### business/static/volte1/css/volte.css (26+ instances)
- [ ] Lines 459-859: Multiple `float: left;` - Audit and convert to modern layout
- [ ] Lines 9174, 9178: Float with !important - Critical refactor needed

---

### 4. Hardcoded Pixel Values (97 instances)

#### business/static/business/css/business.css
- [ ] 15 fixed widths/heights - Convert to relative units (rem, %, vw)

#### orders/static/orders/css/orders.css
- [ ] 9 fixed dimensions - Make responsive

#### product/static/product/css/product.css
- [ ] 6 hardcoded values - Use CSS custom properties

#### volte.css
- [ ] 67 pixel values - Audit and convert critical ones

---

## TEMPLATE BUGS

### Business Team Templates

#### business/parts/business_teams_list.html
- [x] Line 61: Image `src="{{ team.team_logo.url }}"` - Add fallback for missing logo - Fixed
- [x] Card footer buttons may overflow on small screens - Fixed: Added responsive CSS for .btn-group in business.css
- [x] Empty state icon alignment on mobile - Fixed: Added .team-empty-state class with mobile styles

#### business/parts/business_team_permissions.html
- [x] Line 29: Image missing fallback - Add default avatar - Fixed
- [ ] Line 128: Badge counter logic complex - Simplify template logic
- [x] Accordion state not preserved on form submit - Fixed: Added sessionStorage-based state preservation script

#### business/parts/business_team_remove_confirm.html
- [x] Line 13: Image missing fallback for team_logo - Fixed
- [x] Button group needs better mobile spacing - Fixed: Added mobile CSS for .d-flex.gap-2 in business.css

### Order Templates

#### orders/order_list_view.html
- [x] Table not fully responsive on mobile - Fixed: Added `.order-table-wrapper` and `.order-table` classes with overflow-x:auto and touch scrolling
- [x] Action buttons stack poorly on small screens - Fixed: Added responsive CSS for `.order-actions` with column layout and full-width buttons on mobile
- [x] Pagination controls need mobile optimization - Fixed: Enhanced pagination.css with 44px touch targets, flex-wrap, centered alignment, hidden page numbers on small screens, ellipsis indicator class

#### orders/parts/order_list_view.html
- [x] Responsive treatment applied via existing `.order-actions` class - CSS enhanced with mobile-specific flex-direction: column

#### orders/order_update.html
- [x] Form field validation messages not styled consistently - Fixed: CSS exists in orders.css (.form-control.is-invalid, .invalid-feedback)
- [x] Submit button state during AJAX not indicated - Fixed: CSS exists in orders.css (.btn-submit.is-loading with spinner animation)

#### orders/bulk_order_entry.html
- [x] Uses capitalized class names (camelCase) - Fixed: Already uses kebab-case; inline styles extracted to orders.css
- [x] Table scrolling issues on mobile - Fixed: .excel-table-wrapper with overflow-x: auto now in orders.css

### Product Templates

#### product/product_all_list.html
- [ ] Grid/list toggle state not remembered
- [ ] Image lazy loading not implemented
- [x] Card alignment issues with varying content lengths - Fixed: added CSS for equal-height cards and consistent alignment
- [x] View toggle styling - Fixed: added proper CSS classes for .view-toggle component

---

## RESPONSIVE ISSUES

### Missing Media Queries

#### templates/static/mobile-app.css
- [ ] Only 2 media queries - Need comprehensive breakpoints

#### templates/static/base-forms.css
- [ ] Only 3 media queries - Add tablet and mobile breakpoints

#### product/static/product/css/product.css
- [ ] 6 media queries but missing key breakpoints

### Touch Target Issues
- [x] Multiple buttons under 44px touch target size - Fixed: Added mobile media query ensuring 44px minimum touch targets for buttons, nav links, pagination in mobile-app.css
- [x] Links in tables too small for mobile - Fixed: Added `.table a, .table button` rules with min-height/min-width 44px in mobile-app.css

### Horizontal Scroll
- [x] Order tables cause horizontal scroll on mobile - Fixed: Added table-responsive-orders class with overflow-x:auto and webkit touch scrolling

---

## ACCESSIBILITY ISSUES

### Missing Alt Attributes
- [x] Multiple `<img>` tags missing alt text - Fixed: Added descriptive alt text to team member avatars
- [x] Team member avatars need descriptive alt - Fixed: Added `{{ team_member.team_name|default:team_member.user.username }} avatar` pattern

### Color Contrast
- [ ] `.text-muted` on light backgrounds may fail WCAG
- [ ] Warning badges on yellow background

### Focus Indicators
- [x] Custom buttons missing visible focus state - Fixed: Added focus-visible styles in core.css
- [x] Form inputs need clearer focus styling - Fixed: Added focus-visible styles for .form-control, .form-select

### ARIA Labels
- [x] Accordion buttons need aria-expanded - Already had proper aria-expanded and aria-controls in business_team_permissions.html
- [x] Modal close buttons need aria-label - Fixed: Added aria-label="Close" to bulk_order_entry.html and toast_test_buttons.html

---

## CLASS NAMING INCONSISTENCIES

### Mixed Conventions Found
- [x] `product_card_single` (snake_case) vs `order-card` (kebab-case) - Fixed: Added kebab-case classes to product_card.html
- [x] `verificationForm` (camelCase) vs `verification-container` (kebab-case) - Fixed: JS now uses correct element IDs
- [x] Standardize all to kebab-case - Done for reviewed files

### Files to Update
- [ ] orders/templates/orders/bulk_order_entry.html - Uses capitalized classes
- [x] product/templates/product/parts/product_card.html - Fixed: Added kebab-case classes alongside snake_case IDs for backwards compatibility
- [x] business/templates/business/frontend/business_profile.html - Reviewed: Already uses consistent kebab-case classes

---

## VIEW/WORKFLOW BUGS

### Permission Checks
- [x] `orders_successfull_list` - Uses @login_required, should use @business_permission_required - Fixed
- [x] `orders_unsuccessfull_list` - Missing proper permission decorator - Fixed
- [x] `order_product_list` - No authentication required (security issue?) - Fixed
- [x] `order_upload_file` - Missing @login_required decorator (security issue) - Fixed
- [x] `order_upload_review_data` - Missing @login_required decorator (security issue) - Fixed

### Form Handling
- [x] `add_order_with_product` - No authentication decorator - Fixed
- [x] `get_order_comments` - No authentication check - Fixed

### AJAX Endpoints
- [x] `driver_directory_add` - Fixed: Proper HTTP status codes (400/404/405/500), validation, try/except blocks
- [x] `business_team_status_change` - Fixed: Proper error handling, JSON 404 response for invalid team_id, try/except wrapper

---

## CODE QUALITY ISSUES

### Print Statements (Development Artifacts)

#### orders/views.py (47 instances)
- [x] Lines 254-273: `print(business)`, `print(orders)` in `orders_unsuccessfull_list()` - Fixed: Replaced with logger.debug()
- [x] Lines 286-306: `print()` statements in `latest_orders_list()` - Fixed: Replaced with logger.debug()
- [x] Lines 347-377: 10+ print statements in `order_upload_review_data()` - Fixed: Replaced with logger.debug()
- [x] Lines 514-525: 4+ print statements in order creation views - Fixed: Replaced with logger.debug()
- [x] Lines 744-963: Multiple print statements in order management - Fixed: Replaced with logger.debug()
- [x] Lines 1090-1241: 20+ print statements for date filtering and API integration - Fixed: Replaced with logger.debug()
- [x] **Action**: Remove all print() and replace with proper logging - **COMPLETED 2026-01-14**

### Inline onclick Handlers (106 instances)

#### Fleet Templates
- [ ] fleet/templates/fleet/parts/driver_reports.html - Lines 61, 64, 67, 108: onclick handlers
- [ ] workforce/templates/workforce/fleet_transactions.html - Lines 76, 80, 84, 88: print/export onclick

#### Document List Templates
- [x] workforce/templates/workforce/driver_documents_list.html - Lines 27, 31: toggleView onclick - Fixed: Replaced with data-view attributes and event delegation
- [x] workforce/templates/workforce/vehicle_documents_list.html - Lines 27, 31: toggleView onclick - Fixed: Replaced with data-view attributes and event delegation
- [x] workforce/templates/workforce/store_documents_list.html - Lines 27, 31: toggleView onclick - Fixed: Replaced with data-view attributes and event delegation
- [ ] workforce/templates/workforce/business_licenses_list.html - Lines 27, 31: toggleView onclick

#### DMS Templates
- [ ] workforce/templates/workforce/dms_sync_monitor.html - Line 31: reload onclick
- [ ] workforce/templates/workforce/dms_publish_order.html - Lines 68, 71, 74: print/export/refresh onclick
- [ ] workforce/templates/workforce/dms_orders_list.html - Line 35: reload onclick
- [ ] workforce/templates/workforce/dms_drivers_list.html - Line 35: reload onclick

#### Workforce List Templates
- [ ] workforce/templates/workforce/user_verification_list.html - Lines 156, 159, 162: status update onclick
- [ ] workforce/templates/workforce/parts/lists/orders_list_view.html - Lines 224+: quickFilter onclick
- [ ] workforce/templates/workforce/parts/lists/dl_list_incompleted.html - Lines 173-343: 15+ onclick handlers

### Additional Inline Styles Found

#### Fleet Templates
- [ ] workforce/templates/workforce/fleet_transactions.html - Lines 52-92: 11 inline styles
- [x] workforce/templates/workforce/fleet_cod_in_hand.html - Lines 57-61: button styles - Fixed: Extracted to `.fleet-report-actions`, `.btn-print-report`, `.btn-export-report` classes
- [x] workforce/templates/workforce/fleet_drivers_earnings.html - Lines 57-61: button styles - Fixed: Extracted to `.fleet-report-actions`, `.btn-print-report`, `.btn-export-report` classes

#### DMS Templates
- [ ] workforce/templates/workforce/dms_orders_list.html - Lines 27-35: flex layout inline
- [ ] workforce/templates/workforce/dms_publish_order.html - Lines 68-74: button styles

#### Other Templates
- [ ] business/templates/business/parts/business_settings_api_test_result.html - Line 4: display:none
- [ ] business/templates/business/parts/business_team_permissions.html - Lines 141-143: table widths
- [ ] orders/templates/orders/verification_error.html - Line 28: font-size inline
- [ ] orders/templates/orders/parts/order_product_list.html - Lines 19, 32: color inline

---

## WORKFLOW DOCUMENTATION

### Business Onboarding Flow
```
User Registration → Create Business Profile → Add Pickup Locations → Configure API → Add Team → Ready
```

### Order Creation Flow
```
Create Order (AddOrderForm) → Add Products → Status: "to_review" → Workforce Verify → Status: "verified" → Delivery Task Created
```

### Team Management Flow
```
Add Team Member → Assign Role → Set Permissions → Activate/Suspend → Revoke/Grant Permissions
```

---

## FIXED ISSUES

_Items moved here when fixed. Format: `[x] Description - Fixed by [agent/user]`_

---

## FIX PRIORITY ORDER

1. **Security Issues** - Missing auth decorators
2. **Critical CSS** - !important abuse blocking other fixes
3. **Inline Styles** - Extract to CSS classes
4. **Responsive** - Mobile breakpoints
5. **Accessibility** - WCAG compliance
6. **Code Quality** - Class naming consistency

---

Last Updated: 2026-01-14
Status: Comprehensive scan complete. Major CSS and code quality fixes completed.
Total Issues Found: 250+ | Fixed: 75+ | In Progress: 3+ | Pending: 170+
