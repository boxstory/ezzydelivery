# Quick Toast Test Instructions

## Step 1: Check Browser Console

1. Open your dashboard in the browser
2. Press **F12** to open Developer Tools
3. Go to the **Console** tab
4. Look for these messages:
   - "Attempting to show Django messages as toasts..."
   - "Bootstrap available: true/false"
   - "showToast available: true/false"
   - "Messages to show: X"

## Step 2: Test JavaScript Functions Directly

In the browser console, type:

```javascript
// Test 1: Check if function exists
typeof showToast
// Should return: "function"

// Test 2: Check if Bootstrap exists
typeof bootstrap
// Should return: "object"

// Test 3: Show a test toast
showSuccessToast('This is a test!');
// Should show a green toast in top-right corner
```

## Step 3: Test with Django Message

Add this to any view (e.g., `client/views.py`):

```python
from django.contrib import messages

def business_dashboard(request):
    # Add this line temporarily
    messages.success(request, 'Toast test - Success!')
    messages.error(request, 'Toast test - Error!')

    # ... rest of your view code
```

Then refresh the dashboard page.

## Expected Results

✅ **If working correctly:**
- Console shows: "Bootstrap available: true"
- Console shows: "showToast available: true"
- Console shows: "Showing toast: success Toast test - Success!"
- Toast appears in top-right corner
- Toast slides in smoothly
- Toast has green color for success, red for error

❌ **If NOT working:**

### Problem 1: "Bootstrap available: false"
**Solution:** Bootstrap is not loaded or loading too late.

Check in your base template:
```html
<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
```

### Problem 2: "showToast available: false"
**Solution:** Toast script is not running or has errors.

Check browser console for JavaScript errors.

### Problem 3: No console messages at all
**Solution:** Django messages are empty.

In browser, check page source for:
```javascript
const djangoMessages = [
```

If you see `const djangoMessages = [];` then no Django messages are being passed.

## Step 4: Quick Manual Test

Open browser console and run:

```javascript
// Create a manual toast
showToast({
    message: 'Manual test message',
    type: 'success',
    title: 'Test',
    duration: 5000
});
```

If this works but Django messages don't, the issue is with message passing from Django.

## Troubleshooting Commands

```javascript
// 1. Check if toast container exists
document.querySelector('.toast-container')
// Should return: <div class="toast-container...">

// 2. Check Bootstrap version
bootstrap.Toast.VERSION
// Should return version number

// 3. Force show all message types
showSuccessToast('Success test');
showErrorToast('Error test');
showWarningToast('Warning test');
showInfoToast('Info test');

// 4. Check if messages.html is also showing alerts
document.querySelectorAll('.alert').length
// Returns number of alert elements on page
```

## Debug Output

The updated toast system now logs to console. Check for:

```
Attempting to show Django messages as toasts...
Bootstrap available: true
showToast available: true
Messages to show: 2
Showing toast: success Toast test - Success!
Showing toast: danger Toast test - Error!
```

If you see this but no toasts appear, the issue is with Bootstrap Toast initialization.

## Common Issues

### Issue: Toasts don't appear but console shows success
**Fix:** Check z-index conflicts. Run in console:
```javascript
document.querySelector('.toast-container').style.zIndex = '99999';
```

### Issue: Toast appears but immediately disappears
**Fix:** Duration is too short or autohide issue. Test:
```javascript
showToast({
    message: 'Test persistent',
    type: 'success',
    autohide: false
});
```

### Issue: Multiple duplicate toasts
**Fix:** Toast script is running multiple times. Check if toast_notifications.html is included multiple times.

## Success Checklist

- [ ] Console shows: "Bootstrap available: true"
- [ ] Console shows: "showToast available: true"
- [ ] Manual `showSuccessToast('test')` works
- [ ] Django messages appear as toasts
- [ ] Toasts have correct colors
- [ ] Toasts auto-dismiss after duration
- [ ] Can manually close with X button

---

**Still not working?**

Check browser console for errors and share the output!
