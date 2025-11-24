# Complete HTML Element ID Inventory

**Date:** 2025-11-21
**Status:** ✅ Complete
**Standard:** Following [ID Convention Guide](ID_CONVENTION_GUIDE.md)

## Overview

This document provides a complete inventory of all semantic IDs across authentication pages and core templates. All IDs follow the hierarchical naming convention: `{page}_{component}_{element}_{modifier}`

---

## Account Signup Page
**Template:** [templates/account/signup.html](../templates/account/signup.html)

### Page Structure

| ID | Element | Purpose | Line |
|----|---------|---------|------|
| `account_signup_section_body` | `<div>` | Main body section | 360 |
| `account_signup_form_main` | `<form>` | Main signup form | 369 |

### Form Groups

| ID | Element | Purpose | Line |
|----|---------|---------|------|
| `account_signup_form_group_email` | `<div>` | Email field container | 372 |
| `account_signup_form_group_username` | `<div>` | Username field container | 391 |
| `account_signup_form_group_password1` | `<div>` | Password field container | 410 |
| `account_signup_form_group_password2` | `<div>` | Password confirmation container | 453 |

### Password Requirements

| ID | Element | Purpose | Line |
|----|---------|---------|------|
| `account_signup_password_requirements_container` | `<div>` | Requirements container | 421 |
| `account_signup_password_requirements_title` | `<div>` | Title section | 422 |
| `account_signup_password_requirements_icon` | `<i>` | Shield icon | 423 |
| `account_signup_password_requirement_length` | `<div>` | Length requirement | 426 |
| `account_signup_password_requirement_length_icon` | `<i>` | Length status icon | 427 |
| `account_signup_password_requirement_length_text` | `<span>` | Length text | 428 |
| `account_signup_password_requirement_similarity` | `<div>` | Similarity requirement | 430 |
| `account_signup_password_requirement_similarity_icon` | `<i>` | Similarity status icon | 431 |
| `account_signup_password_requirement_similarity_text` | `<span>` | Similarity text | 432 |
| `account_signup_password_requirement_common` | `<div>` | Common password requirement | 434 |
| `account_signup_password_requirement_common_icon` | `<i>` | Common status icon | 435 |
| `account_signup_password_requirement_common_text` | `<span>` | Common text | 436 |
| `account_signup_password_requirement_numeric` | `<div>` | Numeric requirement | 438 |
| `account_signup_password_requirement_numeric_icon` | `<i>` | Numeric status icon | 439 |
| `account_signup_password_requirement_numeric_text` | `<span>` | Numeric text | 440 |

### Buttons

| ID | Element | Purpose | Line |
|----|---------|---------|------|
| `account_signup_btn_submit` | `<button>` | Submit form button | 475 |
| `account_signup_btn_google` | `<a>` | Google signup (enabled) | 490 |
| `account_signup_btn_facebook` | `<a>` | Facebook signup (enabled) | 495 |
| `account_signup_btn_twitter` | `<a>` | Twitter signup (enabled) | 500 |
| `account_signup_btn_github` | `<a>` | GitHub signup (enabled) | 505 |
| `account_signup_btn_google_disabled` | `<button>` | Google signup (disabled) | 513 |
| `account_signup_btn_facebook_disabled` | `<button>` | Facebook signup (disabled) | 517 |
| `account_signup_btn_twitter_disabled` | `<button>` | Twitter signup (disabled) | 521 |
| `account_signup_btn_github_disabled` | `<button>` | GitHub signup (disabled) | 525 |

### Other Elements

| ID | Element | Purpose | Line |
|----|---------|---------|------|
| `account_signup_title_main` | `<h1>` | Page title | 356 |
| `account_signup_subtitle` | `<p>` | Page subtitle | 357 |
| `account_signup_divider` | `<div>` | OR divider | 481 |
| `account_signup_section_social` | `<div>` | Social auth section | 485 |
| `account_signup_footer` | `<div>` | Footer section | 441 |
| `account_signup_link_login` | `<a>` | Link to login | 444 |

**Total Signup IDs:** 32

---

## Account Login Page
**Template:** [templates/account/login.html](../templates/account/login.html)

### Page Structure

| ID | Element | Purpose | Line |
|----|---------|---------|------|
| `account_login_container_main` | `<div>` | Main container | 316 |
| `account_login_card_main` | `<div>` | Auth card | 317 |
| `account_login_header` | `<div>` | Header section | 318 |
| `account_login_section_body` | `<div>` | Body section | 326 |
| `account_login_form_main` | `<form>` | Main login form | 335 |

### Form Groups

| ID | Element | Purpose | Line |
|----|---------|---------|------|
| `account_login_form_group_login` | `<div>` | Login field container | 338 |
| `account_login_form_group_password` | `<div>` | Password field container | 353 |
| `account_login_options_container` | `<div>` | Remember & forgot container | 368 |
| `account_login_remember_container` | `<div>` | Remember me checkbox | 369 |

### Buttons & Links

| ID | Element | Purpose | Line |
|----|---------|---------|------|
| `account_login_btn_submit` | `<button>` | Submit form button | 387 |
| `account_login_link_forgot_password` | `<a>` | Forgot password link | 377 |
| `account_login_btn_google` | `<a>` | Google login (enabled) | 403 |
| `account_login_btn_facebook` | `<a>` | Facebook login (enabled) | 409 |
| `account_login_btn_twitter` | `<a>` | Twitter login (enabled) | 415 |
| `account_login_btn_github` | `<a>` | GitHub login (enabled) | 421 |
| `account_login_btn_google_disabled` | `<button>` | Google login (disabled) | 427 |
| `account_login_btn_facebook_disabled` | `<button>` | Facebook login (disabled) | 429 |
| `account_login_btn_twitter_disabled` | `<button>` | Twitter login (disabled) | 433 |
| `account_login_btn_github_disabled` | `<button>` | GitHub login (disabled) | 437 |
| `account_login_link_signup` | `<a>` | Link to signup | 448 |

### Other Elements

| ID | Element | Purpose | Line |
|----|---------|---------|------|
| `account_login_title_main` | `<h1>` | Page title | 322 |
| `account_login_subtitle` | `<p>` | Page subtitle | 323 |
| `account_login_divider` | `<div>` | OR divider | 393 |
| `account_login_section_social` | `<div>` | Social auth section | 397 |
| `account_login_footer` | `<div>` | Footer section | 445 |

**Total Login IDs:** 26

---

## ID Naming Patterns

### Form Groups
```
{page}_form_group_{field_name}
```
**Examples:**
- `account_signup_form_group_email`
- `account_login_form_group_password`

### Buttons
```
{page}_btn_{action}_{state}
```
**Examples:**
- `account_signup_btn_submit`
- `account_login_btn_google_disabled`

### Links
```
{page}_link_{destination}
```
**Examples:**
- `account_signup_link_login`
- `account_login_link_forgot_password`

### Containers
```
{page}_container_{purpose}
{page}_section_{purpose}
```
**Examples:**
- `account_login_container_main`
- `account_signup_section_social`

### Password Requirements
```
account_signup_password_requirement_{type}_{element}
```
**Examples:**
- `account_signup_password_requirement_length`
- `account_signup_password_requirement_length_icon`
- `account_signup_password_requirement_length_text`

---

## Summary Statistics

| Page | Total IDs | Forms | Buttons | Links | Containers |
|------|-----------|-------|---------|-------|------------|
| **Signup** | 32 | 1 | 9 | 1 | 5 |
| **Login** | 26 | 1 | 10 | 2 | 5 |
| **Total** | **58** | **2** | **19** | **3** | **10** |

---

## ID Categories

### Interactive Elements (35)
- Form inputs and containers
- Buttons (enabled and disabled)
- Links

### Layout Elements (10)
- Page containers
- Sections
- Dividers

### Content Elements (13)
- Titles and subtitles
- Password requirement elements
- Icons

---

## Excluded Elements

Following the guideline to **exclude basic text tags**, the following were NOT given IDs:

### Never Get IDs:
- `<span>` - Regular text spans (except critical ones like requirement text)
- `<p>` - Regular paragraphs (except page subtitles)
- `<li>` - List items in error lists
- `<ul>` - Error lists
- `<label>` - Form labels (use Django's id_for_label)
- `<i>` - Decorative icons (except requirement status icons)

### Get IDs Only When:
- Part of dynamic/validated content (password requirements)
- Main navigation or structural element
- Referenced by JavaScript
- Critical for user interaction

---

## JavaScript Integration

### Elements Referenced in JavaScript

**Signup Page (Line 548):**
```javascript
const requirementsDiv = document.getElementById('account_signup_password_requirements_container');
```

**Data Attribute Selectors:**
```javascript
document.querySelector('[data-requirement="length"]');
document.querySelector('[data-requirement="similarity"]');
document.querySelector('[data-requirement="common"]');
document.querySelector('[data-requirement="numeric"]');
```

---

## Testing Checklist

### Verify IDs Exist
```javascript
// Run in browser console on signup page
console.log(!!document.getElementById('account_signup_form_main')); // should be true
console.log(!!document.getElementById('account_signup_password_requirements_container')); // should be true

// Run in browser console on login page
console.log(!!document.getElementById('account_login_form_main')); // should be true
console.log(!!document.getElementById('account_login_btn_submit')); // should be true
```

### Verify Uniqueness
```bash
# Check for duplicate IDs in a template
grep -o 'id="[^"]*"' templates/account/signup.html | sort | uniq -d
# Should return nothing if all IDs are unique
```

---

## Future Additions

When adding new templates, follow these priorities:

### Priority 1: Must Have IDs
- [ ] All forms
- [ ] All submit buttons
- [ ] All navigation links
- [ ] Main page containers

### Priority 2: Should Have IDs
- [ ] Form field groups
- [ ] Modal dialogs
- [ ] Dynamic content containers
- [ ] JavaScript-targeted elements

### Priority 3: Nice to Have IDs
- [ ] Section dividers
- [ ] Social auth buttons
- [ ] Decorative containers

---

## Related Documentation

- [ID Convention Guide](ID_CONVENTION_GUIDE.md) - Naming standards
- [Password Validation IDs](PASSWORD_VALIDATION_IDS.md) - Password-specific IDs
- [Authentication Fix](AUTHENTICATION_FIX.md) - Login required implementation

---

**Last Updated:** 2025-11-21
**Total IDs Documented:** 58
**Templates Covered:** 2 (Signup, Login)
**Standard:** ✅ Following ID Convention Guide
