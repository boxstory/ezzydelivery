# Coding Standards & Best Practices
## Ezzy Delivery Project

---

## Table of Contents
1. [CSS & Styling Guidelines](#css--styling-guidelines)
2. [Brand Kit Usage](#brand-kit-usage)
3. [Template Structure](#template-structure)
4. [JavaScript Guidelines](#javascript-guidelines)
5. [File Organization](#file-organization)

---

## CSS & Styling Guidelines

### ❌ NEVER Do This:
```html
<!-- DON'T: Inline styles in templates -->
<div style="padding: 1rem; background: white; border-radius: 8px;">
    Content
</div>

<!-- DON'T: Style tags in templates -->
<style>
    .my-class {
        background: white;
        padding: 1rem;
    }
</style>
```

### ✅ ALWAYS Do This:
```html
<!-- DO: Use external CSS files with semantic class names -->
<div class="content-card">
    Content
</div>
```

```css
/* In external CSS file: workforce/static/workforce/css/component.css */
.content-card {
    padding: var(--spacing-md);
    background: var(--brand-white);
    border-radius: var(--brand-radius-md);
}
```

### Rules:
1. **ALWAYS** create dedicated CSS files for styles
2. **NEVER** use inline `style=""` attributes
3. **NEVER** use `<style>` tags in templates
4. **ALWAYS** use semantic, descriptive class names
5. **ALWAYS** link CSS files in `{% block extra_css %}`

---

## Brand Kit Usage

### Brand Kit Variables Location
- **File**: `static/webpages/css/brand-kit.css`
- **Variables**: Defined in `:root` selector

### Available Variables

#### Colors
```css
--brand-primary: #f7c000;           /* Ezzy Yellow */
--brand-primary-dark: #f4c20d;
--brand-secondary: #fff7d6;
--brand-accent: #fef9e6;

/* Neutrals */
--brand-grey-100: #fafafa;
--brand-grey-200: #f0f0f0;
--brand-grey-300: #dcdcdc;
--brand-grey-400: #b0b0b0;
--brand-grey-500: #888;
--brand-grey-600: #555;
--brand-grey-700: #333;
--brand-grey-800: #1f1f1f;
--brand-white: #ffffff;
--brand-black: #000000;
```

#### Spacing
```css
--spacing-xs: 0.25rem;
--spacing-sm: 0.5rem;
--spacing-md: 1rem;
--spacing-lg: 1.5rem;
--spacing-xl: 2rem;
```

#### Shadows
```css
--brand-shadow-sm: 0 1px 3px rgba(0,0,0,0.08);
--brand-shadow-md: 0 4px 8px rgba(0,0,0,0.1);
--brand-shadow-lg: 0 10px 20px rgba(0,0,0,0.12);
```

#### Border Radius
```css
--brand-radius-sm: 8px;
--brand-radius-md: 12px;
--brand-radius-lg: 18px;
```

#### Gradients
```css
--brand-gradient-yellow-white: linear-gradient(135deg, var(--brand-primary), var(--brand-white));
--brand-gradient-black-grey: linear-gradient(135deg, var(--brand-black), var(--brand-grey-700));
```

#### Transitions
```css
--brand-transition: all 0.3s ease;
```

### ❌ NEVER Do This:
```css
/* DON'T: Hardcode colors and values */
.my-button {
    background: #f7c000;
    padding: 16px;
    border-radius: 12px;
    box-shadow: 0 4px 8px rgba(0,0,0,0.1);
}
```

### ✅ ALWAYS Do This:
```css
/* DO: Use brand kit variables */
.my-button {
    background: var(--brand-primary);
    padding: var(--spacing-md);
    border-radius: var(--brand-radius-md);
    box-shadow: var(--brand-shadow-md);
}
```

---

## Template Structure

### Template Anatomy
```html
{% extends "base_template.html" %}
{% load static %}

{% block title %}Page Title - Ezzy Delivery{% endblock title %}

{% block extra_css %}
<!-- ALWAYS link external CSS files here -->
<link href="{% static 'workforce/css/component.css' %}" rel="stylesheet" type="text/css" />
{% endblock extra_css %}

{% block content %}
<!-- Use semantic HTML with descriptive class names -->
<div class="section-container">
    <h1 class="page-title">
        <i class="fa-solid fa-icon me-2"></i>Page Title
    </h1>

    <div class="content-card">
        <!-- Content -->
    </div>
</div>
{% endblock content %}

{% block extra_js %}
<!-- ALWAYS link external JS files here -->
<script src="{% static 'workforce/js/component.js' %}"></script>

<!-- Small inline scripts are OK for page-specific logic -->
<script>
    // Page-specific initialization
    document.addEventListener('DOMContentLoaded', function() {
        // Your code here
    });
</script>
{% endblock extra_js %}
```

### Rules:
1. **ALWAYS** extend a base template
2. **ALWAYS** load static tag at the top
3. **ALWAYS** use semantic block names
4. **ALWAYS** link external files in appropriate blocks
5. **NEVER** mix concerns (keep HTML clean)

---

## JavaScript Guidelines

### ❌ NEVER Do This:
```javascript
// DON'T: Inline styles via JavaScript
element.style.display = 'block';
element.style.background = '#ffffff';
element.style.padding = '1rem';
```

### ✅ ALWAYS Do This:
```javascript
// DO: Use CSS classes for styling
element.classList.add('show');
element.classList.remove('hidden');
element.classList.toggle('active');
```

```css
/* Define states in CSS */
.element {
    display: none;
    background: var(--brand-white);
    padding: var(--spacing-md);
}

.element.show {
    display: block;
}

.element.active {
    background: var(--brand-primary);
}
```

### Rules:
1. **ALWAYS** manipulate classes, not inline styles
2. **ALWAYS** define visual states in CSS
3. **ALWAYS** use semantic class names
4. **ALWAYS** use event delegation when appropriate
5. **ALWAYS** add comments for complex logic

---

## File Organization

### Directory Structure
```
app_name/
├── static/
│   └── app_name/
│       ├── css/
│       │   ├── component1.css
│       │   ├── component2.css
│       │   └── pages/
│       │       ├── page1.css
│       │       └── page2.css
│       ├── js/
│       │   ├── component1.js
│       │   └── component2.js
│       └── img/
├── templates/
│   └── app_name/
│       ├── base.html
│       ├── page1.html
│       ├── page2.html
│       └── parts/
│           ├── header.html
│           └── footer.html
└── views.py
```

### Naming Conventions

#### CSS Files
```
app_pages.css          # General page styles
app_components.css     # Reusable components
app_forms.css          # Form-specific styles
app_lists.css          # List/table styles
```

#### Class Names
```css
/* Use BEM-like naming */
.component-name { }
.component-name__element { }
.component-name--modifier { }

/* Or semantic naming */
.page-title { }
.section-container { }
.content-card { }
.filter-section { }
.status-badge { }
```

#### Template Files
```
base_template.html     # Base template
component_list.html    # List page
component_detail.html  # Detail page
component_form.html    # Form page
```

---

## Examples

### Complete Example: Filter Component

#### 1. Template (template.html)
```html
{% extends "base.html" %}
{% load static %}

{% block extra_css %}
<link href="{% static 'workforce/css/filters.css' %}" rel="stylesheet" />
{% endblock extra_css %}

{% block content %}
<div class="filter-section">
    <div class="filter-toggle" id="filterToggle">
        <strong>Filters</strong>
        <div class="filter-count">
            <span class="badge" id="filterBadge">0</span>
        </div>
    </div>

    <div class="filter-content" id="filterContent">
        <form method="get">
            <!-- Filter inputs -->
        </form>
    </div>
</div>
{% endblock content %}

{% block extra_js %}
<script src="{% static 'workforce/js/filters.js' %}"></script>
{% endblock extra_js %}
```

#### 2. CSS (filters.css)
```css
/* Filter Section */
.filter-section {
    background: var(--brand-white);
    border-radius: var(--brand-radius-md);
    padding: var(--spacing-lg);
    box-shadow: var(--brand-shadow-sm);
}

.filter-toggle {
    cursor: pointer;
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: var(--spacing-md);
    background: var(--brand-grey-100);
    border-radius: var(--brand-radius-sm);
    transition: var(--brand-transition);
}

.filter-toggle:hover {
    background: var(--brand-grey-200);
}

.filter-count {
    display: none;
}

.filter-count.show {
    display: flex;
}

.filter-content {
    display: none;
    margin-top: var(--spacing-md);
}

.filter-content.show {
    display: block;
}
```

#### 3. JavaScript (filters.js)
```javascript
document.addEventListener('DOMContentLoaded', function() {
    const toggle = document.getElementById('filterToggle');
    const content = document.getElementById('filterContent');
    const badge = document.getElementById('filterBadge');
    const countContainer = badge.parentElement;

    // Toggle filter visibility
    toggle.addEventListener('click', function() {
        content.classList.toggle('show');
    });

    // Update filter count
    function updateFilterCount() {
        const activeFilters = document.querySelectorAll('input:not(:placeholder-shown), select:not([value=""])').length;

        if (activeFilters > 0) {
            badge.textContent = activeFilters;
            countContainer.classList.add('show');
        } else {
            countContainer.classList.remove('show');
        }
    }

    // Initialize
    updateFilterCount();
});
```

---

## Quick Reference Checklist

Before committing code, verify:

- [ ] No inline `style=""` attributes
- [ ] No `<style>` tags in templates
- [ ] All styles in external CSS files
- [ ] Brand kit variables used for colors/spacing/shadows
- [ ] Semantic, descriptive class names
- [ ] CSS files linked in `{% block extra_css %}`
- [ ] JS uses class manipulation, not inline styles
- [ ] Files organized in correct directories
- [ ] Code follows naming conventions
- [ ] Comments added for complex logic

---

## Benefits of Following These Standards

1. **Maintainability**: Changes in one place affect all instances
2. **Consistency**: Unified look and feel across the app
3. **Performance**: Browser can cache external CSS/JS files
4. **Readability**: Clean templates are easier to understand
5. **Scalability**: Easy to add new features following same patterns
6. **Collaboration**: Team members can quickly understand code structure
7. **Brand Consistency**: Using brand kit ensures design consistency

---

## Common Violations and Fixes

### Violation 1: Inline Styles
```html
<!-- BAD -->
<div style="background: white; padding: 1rem; border-radius: 8px;">
    Content
</div>

<!-- GOOD -->
<div class="content-card">
    Content
</div>
```

### Violation 2: Hardcoded Colors
```css
/* BAD */
.button {
    background: #f7c000;
    color: #333;
}

/* GOOD */
.button {
    background: var(--brand-primary);
    color: var(--brand-grey-700);
}
```

### Violation 3: JavaScript Inline Styles
```javascript
// BAD
element.style.display = 'block';

// GOOD
element.classList.add('show');
```

### Violation 4: Style Tags in Templates
```html
<!-- BAD -->
<style>
    .my-class { background: white; }
</style>

<!-- GOOD -->
{% block extra_css %}
<link href="{% static 'app/css/styles.css' %}" rel="stylesheet" />
{% endblock %}
```

---

## Contact & Questions

If you have questions about these standards or need clarification, please:
1. Check existing code examples in the project
2. Refer to the brand kit documentation
3. Ask the development team lead

---

**Last Updated**: November 2025
**Version**: 1.0
**Maintainer**: Ezzy Delivery Development Team
