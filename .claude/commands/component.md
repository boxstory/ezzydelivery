---
description: Create reusable UI components
---

# Create Reusable Component

You are creating a reusable UI component for the EzzyDelivery project. Reference `.claude/skills/frontend.md` for styling patterns.

## Component Location
`templates/includes/components/component_name.html`

## Component Template Structure
```html
{# templates/includes/components/component_name.html #}
{#
   Component: [Name]
   Usage: {% include 'includes/components/component_name.html' with param1=value %}
   Parameters:
   - param1: Description (required)
   - param2: Description (optional, default: value)
#}

<div class="component-name">
    {{ param1 }}
    {% if param2 %}{{ param2 }}{% endif %}
</div>
```

## CSS for Component (use brand variables)
```css
.component-name {
    background: var(--brand-white);
    border-radius: var(--brand-radius-md);
    box-shadow: var(--brand-shadow-sm);
    padding: var(--spacing-md);
    transition: var(--brand-transition);
}

.component-name:hover {
    box-shadow: var(--brand-shadow-md);
}
```

## Usage Example
```html
{% include 'includes/components/component_name.html' with
    param1="Value"
    param2="Optional"
%}
```

## Existing Component Patterns

### Status Badges
```html
<span class="status-badge status-{{ status }}">{{ status|title }}</span>
```

### Cards
```html
<div class="info-card">
    <div class="card-header">Title</div>
    <div class="card-body">Content</div>
    <div class="action-section">Actions</div>
</div>
```

### Buttons
```html
<button class="btn btn-primary">Primary (Yellow)</button>
<button class="btn btn-outline-secondary">Secondary</button>
<button class="btn btn-dark">Dark</button>
```

## CRITICAL Rules
1. **Use CSS variables** - Never hardcode colors
2. **Update both CSS files** - static/{app}/css/ AND staticroot/{app}/css/
3. **Document parameters** - Comment block at top of component
4. **Mobile responsive** - Test on mobile devices

## Image Alt Tags (if component has images)
```html
<img src="{{ item.image.url }}"
     alt="{{ item.name }} - {{ item.description|truncatewords:5 }}"
     loading="lazy">
```

Please describe the component you want to create:
1. Component purpose
2. Required parameters
3. Visual appearance/behavior
