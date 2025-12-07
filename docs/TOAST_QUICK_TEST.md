# Quick Toast Testing Guide

## 🧪 Test Method 1: Browser Console (Fastest)

Open your browser console (F12) and paste these commands:

```javascript
// Test all toast types
showSuccessToast('This is a success message!');
showErrorToast('This is an error message!');
showWarningToast('This is a warning message!');
showInfoToast('This is an info message!');

// Test custom toast
showToast({
    message: 'Custom toast with 10 second duration',
    type: 'primary',
    title: 'Custom Title',
    duration: 10000
});

// Test persistent toast (won't auto-hide)
showToast({
    message: 'This toast stays until you dismiss it',
    type: 'warning',
    autohide: false
});
```

## 🧪 Test Method 2: Add Test Panel to Page

Add this line to any template (temporarily):

```django
{% include "includes/toast_test_buttons.html" %}
```

This adds a floating test panel in the bottom-left corner with buttons to test all toast types.

**Remember to remove it before going to production!**

## 🧪 Test Method 3: Django Messages in Views

Add these lines to any view function:

```python
from django.contrib import messages

def your_view(request):
    # Test different message types
    messages.success(request, 'Order #12345 created successfully!')
    messages.error(request, 'Payment processing failed!')
    messages.warning(request, 'Your session will expire in 5 minutes.')
    messages.info(request, 'New features are now available!')

    # Your existing code...
    return render(request, 'your_template.html')
```

## 🧪 Test Method 4: Quick Test URL (Recommended)

### Step 1: Add Test URL

Edit your `ezzydelivery/urls.py` and add:

```python
from django.contrib import messages
from django.shortcuts import redirect

def quick_toast_test(request):
    messages.success(request, 'Success toast works!')
    messages.error(request, 'Error toast works!')
    messages.warning(request, 'Warning toast works!')
    messages.info(request, 'Info toast works!')
    return redirect('business:business_dashboard')  # or any dashboard URL

urlpatterns = [
    # ... existing urls ...
    path('test-toast/', quick_toast_test, name='test_toast'),  # Add this
]
```

### Step 2: Visit the URL

Go to: `http://localhost:8000/test-toast/`

You should see 4 toasts appear!

### Step 3: Remove Test URL

Delete the test URL before deploying to production.

## 🧪 Test Method 5: HTMX Response Headers

In any view that returns an HTMX response:

```python
from django.http import HttpResponse

def my_htmx_view(request):
    # Your logic here...

    response = HttpResponse('Success')
    response['X-Toast-Message'] = 'HTMX toast works!'
    response['X-Toast-Type'] = 'success'  # success, danger, warning, info
    return response
```

## ✅ Expected Behavior

When toasts work correctly, you should see:

1. **Toast appears** in the top-right corner
2. **Slides in** from the right with smooth animation
3. **Shows icon** based on type (✓, ⚠, ℹ, etc.)
4. **Auto-dismisses** after specified duration
5. **Can be manually closed** with X button
6. **Multiple toasts stack** vertically

## ❌ Troubleshooting

### Toast doesn't appear?

**Check 1:** Open browser console (F12) - any errors?

**Check 2:** Is Bootstrap loaded?
```javascript
typeof bootstrap  // Should return "object"
```

**Check 3:** Is showToast function available?
```javascript
typeof showToast  // Should return "function"
```

**Check 4:** Is Font Awesome loaded? (for icons)
```javascript
document.querySelectorAll('link[href*="font-awesome"]').length > 0
```

### Toast appears but looks broken?

**Check:** Is Bootstrap CSS loaded?
```javascript
document.querySelectorAll('link[href*="bootstrap"]').length > 0
```

### Django messages don't show as toasts?

**Check 1:** Is `toast_notifications.html` included in your template?

**Check 2:** Look for this in your template source:
```html
{% include "includes/toast_notifications.html" %}
```

**Check 3:** Check browser console for JavaScript errors

## 🎯 Quick Verification Checklist

- [ ] Open browser console
- [ ] Type: `showSuccessToast('Test')`
- [ ] See toast in top-right corner
- [ ] Toast auto-closes after 5 seconds
- [ ] ✅ System is working!

## 📝 Production Checklist

Before deploying:

- [ ] Remove test panel includes: `{% include "includes/toast_test_buttons.html" %}`
- [ ] Remove test URLs (like `/test-toast/`)
- [ ] Remove TEST_TOAST.py file
- [ ] Keep toast_notifications.html included
- [ ] Test with real user actions (form submissions, etc.)

---

**Need Help?**

Check the full documentation:
- `docs/TOAST_NOTIFICATIONS_GUIDE.md` - Complete guide
- `docs/TOAST_IMPLEMENTATION_SUMMARY.md` - Overview
