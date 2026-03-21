# Password Validation IDs Documentation

**Date:** 2025-11-21
**Status:** ✅ Complete
**Template:** [templates/account/signup.html](../templates/account/signup.html)

## Overview

This document lists all semantic IDs added to the password validation feature on the signup page. These IDs follow the [ID Convention Guide](ID_CONVENTION_GUIDE.md).

---

## Password Validation Elements

### Container

| ID | Element | Purpose | Line |
|----|---------|---------|------|
| `account_signup_password_requirements_container` | `<div>` | Main container for password requirements | 421 |

### Title Section

| ID | Element | Purpose | Line |
|----|---------|---------|------|
| `account_signup_password_requirements_title` | `<div>` | Title container | 422 |
| `account_signup_password_requirements_icon` | `<i>` | Shield icon | 423 |

### Length Requirement

| ID | Element | Purpose | Line |
|----|---------|---------|------|
| `account_signup_password_requirement_length` | `<div>` | Length requirement container | 426 |
| `account_signup_password_requirement_length_icon` | `<i>` | Status icon (circle/check/x) | 427 |
| `account_signup_password_requirement_length_text` | `<span>` | Requirement text | 428 |

### Similarity Requirement

| ID | Element | Purpose | Line |
|----|---------|---------|------|
| `account_signup_password_requirement_similarity` | `<div>` | Similarity requirement container | 430 |
| `account_signup_password_requirement_similarity_icon` | `<i>` | Status icon (circle/check/x) | 431 |
| `account_signup_password_requirement_similarity_text` | `<span>` | Requirement text | 432 |

### Common Password Requirement

| ID | Element | Purpose | Line |
|----|---------|---------|------|
| `account_signup_password_requirement_common` | `<div>` | Common password requirement container | 434 |
| `account_signup_password_requirement_common_icon` | `<i>` | Status icon (circle/check/x) | 435 |
| `account_signup_password_requirement_common_text` | `<span>` | Requirement text | 436 |

### Numeric Requirement

| ID | Element | Purpose | Line |
|----|---------|---------|------|
| `account_signup_password_requirement_numeric` | `<div>` | Numeric requirement container | 438 |
| `account_signup_password_requirement_numeric_icon` | `<i>` | Status icon (circle/check/x) | 439 |
| `account_signup_password_requirement_numeric_text` | `<span>` | Requirement text | 440 |

---

## JavaScript References

### Updated References

**Line 548** - Main container reference:
```javascript
const requirementsDiv = document.getElementById('account_signup_password_requirements_container');
```

### Element Selectors

The JavaScript uses `data-requirement` attributes to select individual requirement elements:

```javascript
// Line 508
const lengthReq = document.querySelector('[data-requirement="length"]');

// Line 513
const similarityReq = document.querySelector('[data-requirement="similarity"]');

// Line 518
const commonReq = document.querySelector('[data-requirement="common"]');

// Line 523
const numericReq = document.querySelector('[data-requirement="numeric"]');
```

These selectors work because each requirement div has both an `id` and a `data-requirement` attribute:

```html
<div class="password-requirement"
     id="account_signup_password_requirement_length"
     data-requirement="length">
```

---

## Visual States

### Icon States

Each requirement icon changes based on validation state:

| State | Icon Class | Color | Description |
|-------|-----------|-------|-------------|
| **Default** | `fa-solid fa-circle` | Gray (#brand-grey-400) | Initial state |
| **Met** | `fa-solid fa-check` | Green (#28a745) | Requirement satisfied |
| **Failed** | `fa-solid fa-times` | Red (#dc3545) | Requirement not met (while typing) |

### Container States

| State | Behavior |
|-------|----------|
| **Hidden** | Default - `display: none` |
| **Visible** | On focus - `.show` class added |
| **Stays visible** | While field has content |
| **Hidden again** | On blur if field is empty |

---

## Usage Examples

### Accessing Elements in JavaScript

```javascript
// Get the main container
const container = document.getElementById('account_signup_password_requirements_container');

// Get a specific requirement
const lengthReq = document.getElementById('account_signup_password_requirement_length');

// Get a specific icon
const lengthIcon = document.getElementById('account_signup_password_requirement_length_icon');

// Get a specific text span
const lengthText = document.getElementById('account_signup_password_requirement_length_text');
```

### Styling via CSS

```css
/* Target the container */
#account_signup_password_requirements_container {
    background: var(--brand-grey-50);
}

/* Target a specific requirement */
#account_signup_password_requirement_length {
    margin-bottom: 0.5rem;
}

/* Target icons in met state */
#account_signup_password_requirement_length_icon.met {
    color: #28a745;
}
```

---

## Testing

### Manual Testing

To verify IDs are working correctly:

1. **Open signup page:** `/accounts/signup/`
2. **Open browser DevTools:** F12
3. **Run in console:**
   ```javascript
   // Should return the container element
   document.getElementById('account_signup_password_requirements_container')

   // Should return each requirement element
   document.getElementById('account_signup_password_requirement_length')
   document.getElementById('account_signup_password_requirement_similarity')
   document.getElementById('account_signup_password_requirement_common')
   document.getElementById('account_signup_password_requirement_numeric')
   ```

4. **Test functionality:**
   - Click on password field → Requirements should appear
   - Type password → Icons should change to checkmarks or X's
   - Click outside with empty field → Requirements should hide

---

## Related Features

### Password Validation Logic

The JavaScript validation checks:

1. **Length:** At least 8 characters (Line 509)
2. **Similarity:** Not too similar to email/username (Line 514)
3. **Common:** Not in common passwords list (Line 519)
4. **Numeric:** Not entirely numeric (Line 524)

### CSS Classes

| Class | Purpose |
|-------|---------|
| `.password-requirements` | Base styling for container |
| `.password-requirements.show` | Visible state |
| `.password-requirement` | Base styling for each requirement |
| `.password-requirement.met` | Green styling when requirement met |
| `.password-requirement.failed` | Red styling when requirement fails |

---

## Naming Convention

All IDs follow the pattern:
```
account_signup_password_requirement_{type}_{element}
```

Where:
- `{type}` = length, similarity, common, numeric
- `{element}` = (none), icon, text

This follows the [ID Convention Guide](ID_CONVENTION_GUIDE.md) standard.

---

## Changelog

| Date | Change | Details |
|------|--------|---------|
| 2025-11-21 | Initial IDs added | Added semantic IDs to all password validation elements |
| 2025-11-21 | Updated JavaScript | Changed `getElementById` to use new container ID |

---

## Related Documentation

- [ID Convention Guide](ID_CONVENTION_GUIDE.md) - Naming standards
- [Session Timeout Implementation](SESSION_TIMEOUT_IMPLEMENTATION.md) - Auto-logout feature
- [Authentication Fix](AUTHENTICATION_FIX.md) - Login required decorators

---

**Total IDs Added:** 13
**Template Updated:** ✅ templates/account/signup.html
**JavaScript Updated:** ✅ Line 548
