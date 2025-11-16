# Template ID Naming Convention

## Overview
This document defines the standardized naming convention for all HTML element IDs across the EzzyDelivery project templates.

## Naming Pattern
```
{app}_{section}_{element_type}_{descriptor}
```

### Components:
1. **app**: The Django app name (core, client, workforce, fleet, orders, product, delivery, webpages, api)
2. **section**: The page/section name (dashboard, profile, order_list, etc.)
3. **element_type**: The type of element (card, table, header, btn, form, modal, etc.)
4. **descriptor**: Brief description of the element's purpose

## Element Type Codes

### Containers
- `card` - Card containers
- `section` - Section containers
- `wrapper` - Wrapper divs
- `container` - Main containers

### Tables
- `table` - Main table element
- `thead` - Table header
- `tbody` - Table body
- `trow` - Table row (when specific ID needed)
- `tcell` - Table cell (when specific ID needed)

### Headers
- `header` - Page headers
- `title` - Title elements
- `subtitle` - Subtitle elements
- `breadcrumb` - Breadcrumb navigation

### Forms
- `form` - Form elements
- `input` - Input fields
- `select` - Select dropdowns
- `textarea` - Text areas
- `checkbox` - Checkboxes
- `radio` - Radio buttons
- `btn` - Buttons

### Modals
- `modal` - Modal containers
- `modal_header` - Modal header
- `modal_body` - Modal body
- `modal_footer` - Modal footer

### Navigation
- `nav` - Navigation containers
- `sidebar` - Sidebar navigation
- `navbar` - Top navigation bar
- `menu` - Menu items
- `link` - Navigation links

### Alerts & Messages
- `alert` - Alert boxes
- `message` - Message containers
- `notification` - Notification elements

### Lists
- `list` - List containers
- `item` - List items

## Examples by App

### Core App (`core_`)
```html
<!-- Dashboard -->
<div id="core_dashboard_header">
<div id="core_dashboard_card_stats">
<table id="core_dashboard_table_recent_activity">
<button id="core_dashboard_btn_export">

<!-- Profile -->
<div id="core_profile_card_info">
<form id="core_profile_form_update">
<div id="core_profile_modal_photo_upload">
<div id="core_profile_sidebar_main">
```

### Client App (`client_`)
```html
<!-- Business Dashboard -->
<div id="client_dashboard_header">
<div id="client_dashboard_card_revenue">
<table id="client_dashboard_table_orders">
<button id="client_dashboard_btn_add_order">

<!-- Business Profile -->
<div id="client_profile_card_business_info">
<form id="client_profile_form_update">
<div id="client_profile_section_products">
```

### Workforce App (`workforce_`)
```html
<!-- Staff Dashboard -->
<div id="workforce_dashboard_header">
<div id="workforce_dashboard_card_pending_tasks">
<table id="workforce_dashboard_table_deliveries">
<div id="workforce_dashboard_sidebar_main">

<!-- Orders List -->
<div id="workforce_orders_header">
<table id="workforce_orders_table_all">
<form id="workforce_orders_form_filter">
<button id="workforce_orders_btn_export">

<!-- DMS Orders -->
<div id="workforce_dms_orders_header">
<table id="workforce_dms_orders_table_matched">
<form id="workforce_dms_orders_form_manual_match">
<button id="workforce_dms_orders_btn_match">
```

### Fleet App (`fleet_`)
```html
<!-- Fleet Dashboard -->
<div id="fleet_dashboard_header">
<div id="fleet_dashboard_card_drivers">
<table id="fleet_dashboard_table_active_drivers">
<div id="fleet_dashboard_sidebar_main">

<!-- Driver Profile -->
<div id="fleet_driver_profile_card_info">
<div id="fleet_driver_profile_card_stats">
<table id="fleet_driver_profile_table_deliveries">
<form id="fleet_driver_profile_form_update">
```

### Orders App (`orders_`)
```html
<!-- Add Order -->
<div id="orders_add_header">
<form id="orders_add_form_main">
<div id="orders_add_card_customer_info">
<button id="orders_add_btn_submit">

<!-- Order List -->
<div id="orders_list_header">
<table id="orders_list_table_all">
<form id="orders_list_form_filter">
<button id="orders_list_btn_export">

<!-- Order Details -->
<div id="orders_detail_header">
<div id="orders_detail_card_info">
<div id="orders_detail_card_delivery">
<table id="orders_detail_table_products">
```

### Product App (`product_`)
```html
<!-- Product List -->
<div id="product_list_header">
<table id="product_list_table_all">
<button id="product_list_btn_add">
<form id="product_list_form_filter">

<!-- Add Product -->
<div id="product_add_header">
<form id="product_add_form_main">
<div id="product_add_card_info">
<button id="product_add_btn_save">

<!-- Inventory -->
<div id="product_inventory_header">
<table id="product_inventory_table_stock">
<div id="product_inventory_card_low_stock">
```

### Delivery App (`delivery_`)
```html
<!-- Task List -->
<div id="delivery_task_list_header">
<table id="delivery_task_list_table_all">
<form id="delivery_task_list_form_filter">

<!-- Task Details -->
<div id="delivery_task_detail_header">
<div id="delivery_task_detail_card_info">
<div id="delivery_task_detail_card_status">
<button id="delivery_task_detail_btn_update_status">
```

### Webpages App (`webpages_`)
```html
<!-- Landing Page -->
<div id="webpages_home_header">
<div id="webpages_home_section_hero">
<div id="webpages_home_section_features">
<button id="webpages_home_btn_signup">

<!-- About -->
<div id="webpages_about_header">
<div id="webpages_about_section_team">
```

### API App (`api_`)
```html
<!-- API Docs -->
<div id="api_docs_header">
<div id="api_docs_section_endpoints">
<table id="api_docs_table_parameters">
```

## Special Cases

### Repeated Elements (Use Index)
When multiple similar elements exist, append an index or unique identifier:
```html
<div id="workforce_orders_card_stats_pending">
<div id="workforce_orders_card_stats_completed">
<div id="workforce_orders_card_stats_cancelled">
```

### Modal Elements
Always prefix modal elements with the parent ID pattern:
```html
<div id="workforce_orders_modal_delete">
  <div id="workforce_orders_modal_delete_header">
  <div id="workforce_orders_modal_delete_body">
  <button id="workforce_orders_modal_delete_btn_confirm">
</div>
```

### Dynamic Elements (JavaScript Generated)
For JavaScript-generated elements, use data attributes and consistent naming:
```html
<div data-dynamic-id="workforce_orders_row_{order_id}">
```

## Implementation Checklist

- [ ] All page headers have unique IDs
- [ ] All cards have unique IDs
- [ ] All tables have unique IDs
- [ ] All forms have unique IDs
- [ ] All buttons have unique IDs (primary actions)
- [ ] All modals have unique IDs
- [ ] All sidebars have unique IDs
- [ ] All navigation elements have unique IDs
- [ ] All sections have unique IDs

## Benefits

1. **JavaScript/jQuery Selection**: Easy and specific element targeting
2. **CSS Styling**: Precise styling control
3. **Testing**: Automated testing with Selenium/Playwright
4. **Debugging**: Quick element identification
5. **Accessibility**: Improved screen reader navigation
6. **Documentation**: Self-documenting code
7. **Maintenance**: Easier to understand and modify

## Migration Strategy

1. Start with most-used templates (dashboards, lists)
2. Update one app at a time
3. Test each app after updates
4. Document all assigned IDs
5. Update JavaScript/jQuery selectors as needed
6. Update CSS selectors as needed

## Notes

- IDs must be unique across the entire page (not just app)
- Use lowercase with underscores (snake_case)
- Keep IDs descriptive but concise
- Avoid generic IDs like `btn1`, `card2`, etc.
- Use semantic names that describe purpose
