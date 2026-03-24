# Toast Notifications Guide

This guide shows you how to use the Bootstrap Toast notification system in your Django application.

## Features

- ✅ Multiple toast types: success, error (danger), warning, info, primary
- ✅ Auto-dismissible with configurable duration
- ✅ Manual dismiss button
- ✅ Smooth slide-in animation
- ✅ Works with Django messages framework
- ✅ Works with HTMX requests
- ✅ JavaScript API for custom toasts
- ✅ Responsive and mobile-friendly
- ✅ Font Awesome icons

## Usage

### 1. From Django Views (Server-Side)

Use Django's messages framework as usual. Messages will automatically appear as toasts:

```python
from django.contrib import messages
from django.shortcuts import render, redirect

def my_view(request):
    # Success message
    messages.success(request, 'Order created successfully!')

    # Error message
    messages.error(request, 'Failed to process payment.')

    # Warning message
    messages.warning(request, 'Your session will expire in 5 minutes.')

    # Info message
    messages.info(request, 'New features are available!')

    return redirect('dashboard')
```

### 2. From JavaScript (Client-Side)

#### Using the Main Function

```javascript
// Basic usage
showToast({
    message: 'Order successfully created!',
    type: 'success'
});

// With custom title and duration
showToast({
    message: 'This is a custom notification',
    type: 'info',
    title: 'Custom Title',
    duration: 8000  // 8 seconds
});

// Persistent toast (won't auto-hide)
showToast({
    message: 'This stays until dismissed',
    type: 'warning',
    autohide: false,
    duration: 0
});
```

#### Using Convenience Functions (from `dashboard-notifications.js`)

> ⚠️ **Correct function names** — these are defined in `webpages/static/webpages/js/dashboard-notifications.js`

```javascript
// Success toast
showSuccess('Payment processed successfully!');

// Error toast
showError('Failed to save changes.');

// Warning toast
showWarning('Your session is about to expire.');

// Info toast
showInfo('Check out our new features!');

// With custom duration (ms)
showSuccess('Order #12345 created', 3000);
```

### 3. From HTMX Responses

Add custom headers in your Django view to trigger toasts:

```python
from django.http import HttpResponse

def my_htmx_view(request):
    # Process your logic here

    response = HttpResponse('Success')
    response['X-Toast-Message'] = 'Order updated successfully!'
    response['X-Toast-Type'] = 'success'  # success, danger, warning, info

    return response
```

### 4. Toast Types and Icons

| Type      | Django Message Tag | Icon                          | Color  |
|-----------|-------------------|-------------------------------|--------|
| Success   | `success`         | ✓ Check circle                | Green  |
| Error     | `error`/`danger`  | ⚠ Exclamation circle          | Red    |
| Warning   | `warning`         | ⚠ Exclamation triangle        | Yellow |
| Info      | `info`            | ℹ Info circle                 | Blue   |
| Primary   | `primary`         | 🔔 Bell                       | Blue   |

### 5. Configuration Options

```javascript
showToast({
    message: 'Your message here',      // Required: The message to display
    type: 'success',                   // Optional: success, danger, warning, info, primary (default: info)
    title: 'Custom Title',             // Optional: Toast title (auto-generated if not provided)
    duration: 5000,                    // Optional: Duration in milliseconds (default: 5000)
    autohide: true                     // Optional: Whether to auto-hide (default: true)
});
```

### 6. Example Usage Scenarios

#### Form Submission Success
```javascript
document.getElementById('myForm').addEventListener('submit', function(e) {
    e.preventDefault();

    // Submit form via AJAX
    fetch('/api/submit', {
        method: 'POST',
        body: new FormData(this)
    })
    .then(response => response.json())
    .then(data => {
        showSuccess('Form submitted successfully!');
    })
    .catch(error => {
        showError('Failed to submit form. Please try again.');
    });
});
```

#### Delete Confirmation
```javascript
function deleteItem(itemId) {
    if (confirm('Are you sure you want to delete this item?')) {
        fetch(`/api/delete/${itemId}`, { method: 'DELETE' })
            .then(response => {
                if (response.ok) {
                    showSuccess(`Item #${itemId} deleted successfully`);
                } else {
                    showError('Failed to delete item');
                }
            });
    }
}
```

#### Multiple Operations
```javascript
async function processOrders() {
    showInfo('Processing orders...');  // from dashboard-notifications.js

    try {
        await processOrder1();
        await processOrder2();
        await processOrder3();

        showSuccess('All orders processed successfully!');
    } catch (error) {
        showError('Some orders failed to process');
    }
}
```

### 7. Styling Customization

The toast styles are defined in `templates/includes/toast_notifications.html`. You can customize:

- Colors for each toast type
- Animation effects
- Size and positioning
- Icons
- Timing

### 8. Default Durations

- **Success**: 5 seconds
- **Error**: 8 seconds (longer for errors)
- **Warning**: 6 seconds
- **Info**: 5 seconds
- **Primary**: 5 seconds

### 9. Position

Toasts appear in the **top-right corner** by default. To change the position, modify the `.toast-container` class in the template:

```html
<!-- Top Right (default) -->
<div class="toast-container position-fixed top-0 end-0 p-3">

<!-- Top Left -->
<div class="toast-container position-fixed top-0 start-0 p-3">

<!-- Bottom Right -->
<div class="toast-container position-fixed bottom-0 end-0 p-3">

<!-- Bottom Left -->
<div class="toast-container position-fixed bottom-0 start-0 p-3">
```

### 10. Testing

Open your browser console and test:

```javascript
// Test all types (correct function names from dashboard-notifications.js)
showSuccess('This is a success message');
showError('This is an error message');
showWarning('This is a warning message');
showInfo('This is an info message');
// Or using the base function:
showToast('Custom message', 'success', 3000);
```

## Integration Points

The toast system is automatically integrated in:
- ✅ `templates/includes/toast_notifications.html` — Django messages → Bootstrap toasts (server-side)
- ✅ `webpages/static/webpages/js/dashboard-notifications.js` — JS convenience functions (`showSuccess`, `showError`, `showWarning`, `showInfo`, `showToast`)
- ✅ Works with Django messages framework
- ✅ Works with HTMX requests (via `X-Toast-Message` / `X-Toast-Type` response headers)

## Browser Support

Works with all modern browsers that support:
- Bootstrap 5.x
- ES6 JavaScript
- CSS Animations

## Troubleshooting

**Toasts not showing?**
- Check that Bootstrap JavaScript is loaded
- Check browser console for errors
- Verify Font Awesome is loaded for icons

**Toasts appearing but no styling?**
- Check that Bootstrap CSS is loaded
- Verify toast_notifications.html is included

**Icons not showing?**
- Verify Font Awesome is loaded
- Check Font Awesome version compatibility
