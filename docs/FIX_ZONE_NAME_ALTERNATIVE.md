# Alternative Fix for Zone Name Display

If the template filter is still causing 500 errors, here's an alternative approach using the view instead.

## Option 1: Add Zone Names in the View (Recommended if filter fails)

Edit `orders/views.py` in the `orders_all_list` function:

### Find this section (around line 118-132):
```python
items = orders_models.Order.objects.filter(
    business=business.business_id
).select_related(
    'business',
    'pickup_location',
    'address_verified_by',
    'verified_by',
).prefetch_related(
    'order_items',
    'order_items__product',
    'delivery_task',
    'delivery_task__driver',
    'delivery_task__business',
).order_by('-id')
```

### Add this code RIGHT AFTER the above section:
```python
# Add zone names to orders
from delivery.models import ZoneName
zone_cache = {}  # Cache zone lookups

for order in items:
    if order.dl_zone and order.dl_zone not in zone_cache:
        try:
            zone = ZoneName.objects.filter(zone_number=order.dl_zone).first()
            zone_cache[order.dl_zone] = zone.zone_name if zone else f"Zone {order.dl_zone}"
        except:
            zone_cache[order.dl_zone] = f"Zone {order.dl_zone}"

    # Add zone_name attribute to order
    order.zone_name = zone_cache.get(order.dl_zone, "No Zone") if order.dl_zone else "No Zone"
```

### Then in the template, change:
```django
{{ order.dl_zone|get_zone_name }}
```

### To:
```django
{{ order.zone_name }}
```

---

## Option 2: Simplify the Template Filter

If the filter is the issue, replace the entire content of `orders/templatetags/order_filters.py` with this simpler version:

```python
"""
Custom template filters for orders app
"""
from django import template

register = template.Library()


@register.filter
def get_zone_name(zone_number):
    """Get zone name from zone number."""
    if not zone_number:
        return "No Zone"

    # Simple fallback - just return the zone number
    return f"Zone {zone_number}"
```

This ultra-simple version will at least prevent the 500 error and show "Zone X" format.

---

## Option 3: Remove the Filter Entirely (Quick Fix)

If you need to get the page working immediately:

1. Edit `orders/templates/orders/parts/order_list_view.html`
2. Change lines 2, 54, and 108 back to:

```django
{% load static %}
<!-- Remove: {% load order_filters %} -->

<!-- Line 54: -->
<span>Zone {{ order.dl_zone }}</span>

<!-- Line 108: -->
Zone {{ order.dl_zone }}, Street {{ order.dl_street }}, Building {{ order.dl_building }}<br>
```

This reverts to showing zone numbers only but will work immediately without any errors.

---

## Debugging the 500 Error

To see the actual error, check your Django console/terminal where the server is running. The error message will show exactly what went wrong.

Common causes:
1. Template filter not registered properly
2. Circular import issues
3. Database connection issues
4. Missing ZoneName table/model

Look for lines starting with:
- `Exception:`
- `Error:`
- `Traceback:`

Share those lines and I can provide a more specific fix.
