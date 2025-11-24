# HTML Element ID Convention Guide

**Date:** 2025-11-21
**Status:** ✅ Active Standard

## Overview

This document establishes the standardized naming convention for HTML element IDs across the Django Ezzy Delivery application. Following these conventions ensures consistency, maintainability, and easier navigation through the codebase.

---

## ID Naming Convention

### General Format

```
{page/section}_{component}_{element}_{modifier}
```

**Rules:**
- Use **lowercase** letters only
- Separate words with **underscores** (`_`)
- Be **descriptive** but concise
- Follow a **hierarchical** structure from general to specific

---

## Naming Structure

### 1. Page/Section Prefix

Always start with the page or section identifier:

| Page/Section | Prefix | Example |
|--------------|--------|---------|
| Account Signup | `account_signup_` | `account_signup_form_main` |
| Account Login | `account_login_` | `account_login_btn_submit` |
| Client Dashboard | `client_dashboard_` | `client_dashboard_header_nav` |
| Workforce Dashboard | `workforce_dashboard_` | `workforce_dashboard_orders_table` |
| Fleet Dashboard | `fleet_dashboard_` | `fleet_dashboard_vehicle_list` |
| Profile | `profile_` | `profile_picture_upload` |
| Business Settings | `business_settings_` | `business_settings_api_form` |

### 2. Component Type

Second level describes the UI component:

| Component | Keyword | Example |
|-----------|---------|---------|
| Form | `form` | `account_signup_form_main` |
| Button | `btn` | `account_signup_btn_submit` |
| Input Field | `input` | `account_signup_input_email` |
| Container/Div | `container` / `section` | `account_signup_password_requirements_container` |
| Link | `link` | `account_signup_link_login` |
| Icon | `icon` | `account_signup_password_requirements_icon` |
| Text/Label | `text` / `title` / `label` | `account_signup_password_requirement_length_text` |
| Modal | `modal` | `session_timeout_modal_warning` |
| Table | `table` | `workforce_orders_table_main` |
| List | `list` | `client_business_list_all` |

### 3. Element Description

Third level describes the specific element or its purpose:

```
account_signup_password_requirement_length
                ↑
          specific description
```

### 4. Modifier (Optional)

Fourth level for additional specificity:

```
account_signup_password_requirement_length_icon
                                           ↑
                                        modifier
```

---

## Real-World Examples

### Account Signup Page

```html
<!-- Page structure -->
<div id="account_signup_section_body">
    <!-- Form -->
    <form id="account_signup_form_main">

        <!-- Password requirements container -->
        <div id="account_signup_password_requirements_container">

            <!-- Title -->
            <div id="account_signup_password_requirements_title">
                <i id="account_signup_password_requirements_icon"></i>
                Password Requirements
            </div>

            <!-- Individual requirements -->
            <div id="account_signup_password_requirement_length">
                <i id="account_signup_password_requirement_length_icon"></i>
                <span id="account_signup_password_requirement_length_text">
                    At least 8 characters long
                </span>
            </div>

            <div id="account_signup_password_requirement_similarity">
                <i id="account_signup_password_requirement_similarity_icon"></i>
                <span id="account_signup_password_requirement_similarity_text">
                    Not too similar to your other personal information
                </span>
            </div>

            <div id="account_signup_password_requirement_common">
                <i id="account_signup_password_requirement_common_icon"></i>
                <span id="account_signup_password_requirement_common_text">
                    Not a commonly used password
                </span>
            </div>

            <div id="account_signup_password_requirement_numeric">
                <i id="account_signup_password_requirement_numeric_icon"></i>
                <span id="account_signup_password_requirement_numeric_text">
                    Can't be entirely numeric
                </span>
            </div>
        </div>

        <!-- Submit button -->
        <button id="account_signup_btn_submit">Create Account</button>
    </form>

    <!-- Footer -->
    <div id="account_signup_footer">
        <a id="account_signup_link_login">Sign In</a>
    </div>
</div>
```

### Dashboard Examples

```html
<!-- Client Dashboard -->
<div id="client_dashboard_header_nav">
    <button id="client_dashboard_btn_menu_toggle"></button>
    <div id="client_dashboard_user_profile_dropdown"></div>
</div>

<!-- Workforce Dashboard -->
<div id="workforce_dashboard_orders_section">
    <table id="workforce_dashboard_orders_table_main">
        <button id="workforce_dashboard_orders_btn_filter"></button>
    </table>
</div>

<!-- Fleet Dashboard -->
<div id="fleet_dashboard_documents_section">
    <button id="fleet_dashboard_documents_btn_upload"></button>
    <div id="fleet_dashboard_documents_list_container"></div>
</div>
```

---

## Hierarchy Levels

### Level 1: Main Containers
```html
<div id="account_signup_section_body">
<div id="client_dashboard_container_main">
```

### Level 2: Components
```html
<form id="account_signup_form_main">
<table id="workforce_orders_table_main">
```

### Level 3: Sub-components
```html
<div id="account_signup_password_requirements_container">
<div id="client_dashboard_orders_filter_section">
```

### Level 4: Individual Elements
```html
<button id="account_signup_btn_submit">
<span id="account_signup_password_requirement_length_text">
```

---

## When to Add IDs

### ✅ Always Add IDs For:

1. **Main page sections** - Headers, footers, body
2. **Forms** - All forms and their submit buttons
3. **Interactive elements** - Buttons, links, inputs
4. **Dynamic content containers** - Elements manipulated by JavaScript
5. **Navigation elements** - Menus, dropdowns, tabs
6. **Modals and overlays** - Pop-ups, warnings, confirmations
7. **Critical data displays** - Tables, lists, cards with data
8. **Newly created elements** - All new UI components

### ❌ Don't Add IDs For:

1. **Pure styling divs** - Decorative containers with no function
2. **Repeated list items** - Use classes instead (unless specific targeting needed)
3. **Static text** - Non-interactive paragraphs or labels
4. **Inline styling wrappers** - Generic flex/grid containers

---

## Special Cases

### Dynamic/Repeated Elements

For repeated elements (like list items), use data attributes or classes:

```html
<!-- Good: Use classes for repeated items -->
<div class="order-item" data-order-id="12345">
    <button class="order-item-btn-edit">Edit</button>
</div>

<!-- Bad: Don't create unique IDs for each item -->
<div id="order_item_12345">
    <button id="order_item_12345_btn_edit">Edit</button>
</div>
```

### State-Specific Elements

Include state in the ID when needed:

```html
<button id="account_signup_btn_google_disabled" disabled>Sign up with Google</button>
<button id="account_signup_btn_facebook_disabled" disabled>Sign up with Facebook</button>
```

---

## Migration Strategy

### For Existing Code

1. **Priority 1:** Add IDs to all interactive elements (forms, buttons, links)
2. **Priority 2:** Add IDs to JavaScript-targeted elements
3. **Priority 3:** Add IDs to main layout containers
4. **Priority 4:** Add IDs to data display elements

### For New Code

1. **MUST:** Add IDs to all new main elements following this guide
2. **MUST:** Document new ID patterns in code comments
3. **SHOULD:** Reference this guide in pull request descriptions
4. **SHOULD:** Update this document if new patterns emerge

---

## Tools & Utilities

### ID Validation Checklist

Before committing code, verify:

- [ ] All IDs use lowercase with underscores
- [ ] All IDs follow the hierarchical structure
- [ ] All IDs are unique within the page
- [ ] All JavaScript references updated to new IDs
- [ ] No deprecated IDs remain in code

### Search Patterns

To find all IDs in a template:
```bash
grep -n 'id="[^"]*"' template.html
```

To find JavaScript references to an ID:
```bash
grep -n "getElementById\|'#" script.js
```

---

## Documentation Updates

### When This Guide Changes

1. Update the **Date** at the top
2. Add entry to **Change Log** section below
3. Notify team via commit message
4. Update related documentation

---

## Change Log

| Date | Change | Author |
|------|--------|--------|
| 2025-11-21 | Initial creation of ID convention guide | Claude |
| 2025-11-21 | Added password validation IDs | Claude |

---

## Related Documentation

- [Semantic ID Inventory](HASH_LINKS_INVENTORY.md) - Full list of IDs by page
- [Authentication Fix](AUTHENTICATION_FIX.md) - Login required implementation
- [Session Timeout](SESSION_TIMEOUT_IMPLEMENTATION.md) - Auto-logout feature

---

## Quick Reference

### Common Prefixes
```
account_signup_         - Signup page elements
account_login_          - Login page elements
client_dashboard_       - Client dashboard elements
workforce_dashboard_    - Workforce dashboard elements
fleet_dashboard_        - Fleet dashboard elements
profile_               - Profile page elements
business_settings_      - Business settings elements
```

### Common Components
```
_form_          - Forms
_btn_           - Buttons
_input_         - Input fields
_link_          - Links
_modal_         - Modals
_table_         - Tables
_list_          - Lists
_container_     - Containers
_section_       - Sections
_icon_          - Icons
_text_          - Text elements
_title_         - Titles
_label_         - Labels
```

---

**Standard Status:** ✅ Active - All new code MUST follow this convention
