# Simple Bootstrap Toast Guide

## ✅ What's Implemented

A **simple, pure Bootstrap 5 toast notification system** that automatically displays Django messages.

- ✅ Uses Bootstrap's native toast component only
- ✅ No custom JavaScript functions
- ✅ Automatic display of Django messages
- ✅ Color-coded by message type
- ✅ Font Awesome icons
- ✅ Auto-dismiss with configurable duration
- ✅ Manual close button

## 🎯 How to Use

### 1. Django Messages (Server-Side)

Simply use Django's messages framework in your views:

```python
from django.contrib import messages

def my_view(request):
    messages.success(request, 'Order created successfully!')
    messages.error(request, 'Payment failed!')
    messages.warning(request, 'Session expiring soon!')
    messages.info(request, 'New features available!')

    return redirect('dashboard')
```

**That's it!** The toasts will automatically appear in the top-right corner.

## 🎨 Message Types & Colors

| Django Message       | Toast Color | Icon              | Duration |
|---------------------|-------------|-------------------|----------|
| `messages.success()`| Green       | ✓ Check           | 5 sec    |
| `messages.error()`  | Red         | ⚠ Exclamation     | 8 sec    |
| `messages.warning()`| Yellow      | ⚠ Triangle        | 5 sec    |
| `messages.info()`   | Blue        | ℹ Info            | 5 sec    |

## 📍 Toast Position

Toasts appear in the **top-right corner** by default.

To change position, edit `toast_notifications.html`:

```html
<!-- Top-right (current) -->
<div class="toast-container position-fixed top-0 end-0 p-3">

<!-- Other options: -->
<!-- Top-left -->
<div class="toast-container position-fixed top-0 start-0 p-3">

<!-- Bottom-right -->
<div class="toast-container position-fixed bottom-0 end-0 p-3">

<!-- Bottom-left -->
<div class="toast-container position-fixed bottom-0 start-0 p-3">
```

## 🧪 Testing

**Quick Test:**

Add this to any view:

```python
def test_view(request):
    messages.success(request, 'Success toast test!')
    messages.error(request, 'Error toast test!')
    messages.warning(request, 'Warning toast test!')
    messages.info(request, 'Info toast test!')
    return redirect('dashboard')
```

Visit that view and you'll see 4 toasts appear!

## 📋 Files

**Created/Modified:**
1. `templates/includes/toast_notifications.html` - Toast system (simplified)
2. `templates/includes/messages.html` - Inline alerts disabled (uses toasts only)
3. `templates/client_dashboard_base.html` - Toast include added
4. `templates/fleet_dashboard_base.html` - Toast include added
5. `templates/wf_dashboard_base.html` - Toast include added

## 🔧 How It Works

1. Django passes messages to the template
2. `toast_notifications.html` renders each message as a Bootstrap toast
3. Simple JavaScript initializes and shows the toasts
4. Toasts auto-dismiss after the specified duration

## ✨ Features

- **Auto-dismiss**: Toasts automatically disappear (5s for most, 8s for errors)
- **Manual close**: Click the X button to dismiss immediately
- **Stacking**: Multiple toasts stack vertically
- **Responsive**: Works on mobile and desktop
- **Accessible**: Proper ARIA attributes for screen readers

## 🎯 Customization

### Change Duration

Edit `toast_notifications.html` line 6:

```django
data-bs-delay="{% if message.tags == 'error' %}8000{% else %}5000{% endif %}"
```

Change `8000` (8 seconds) or `5000` (5 seconds) as needed.

### Change Colors

The colors come from Bootstrap's utility classes:
- `text-bg-success` = Green
- `text-bg-danger` = Red (error)
- `text-bg-warning` = Yellow
- `text-bg-info` = Blue

### Disable Auto-Hide

Change `data-bs-autohide="true"` to `data-bs-autohide="false"` in `toast_notifications.html`.

## ❌ Troubleshooting

**Toasts don't show?**

1. Check Bootstrap is loaded:
   ```html
   <script src="bootstrap.bundle.min.js"></script>
   ```

2. Check `toast_notifications.html` is included:
   ```django
   {% include "includes/toast_notifications.html" %}
   ```

3. Check browser console for errors (F12)

**Toasts show but immediately disappear?**

Check if `data-bs-autohide` is set correctly.

**Multiple toasts overlap?**

This is normal - they stack. Increase the container width if needed.

## 📖 Bootstrap Documentation

For more toast options, see:
- [Bootstrap 5 Toasts](https://getbootstrap.com/docs/5.3/components/toasts/)

## 🎉 That's It!

Super simple. No complex JavaScript. Just Bootstrap + Django messages = Toasts!

---

**Previous Complexity:** 250+ lines of custom JavaScript
**Current Simplicity:** 10 lines of Bootstrap-native code

✨ **Simplified on 2025-12-06**
