# Django Logging Configuration

**Date:** November 13, 2025
**Project:** EzzyDelivery Qatar Delivery Services
**Purpose:** Comprehensive logging setup for replacing print statements
**Status:** 📋 Ready for Implementation

---

## 🎯 Overview

This document provides the complete logging configuration that needs to be added to `ezzydelivery/settings.py` to support the print statement removal initiative.

---

## 📝 Configuration to Add to settings.py

Add this configuration at the end of your `ezzydelivery/settings.py` file:

```python
# ==========================================
# LOGGING CONFIGURATION
# ==========================================
# Added: November 13, 2025
# Purpose: Replace print statements with proper logging
# Documentation: docs/critical-fixes/PRINT_STATEMENT_REMOVAL_PLAN.md
# ==========================================

import os
from pathlib import Path

# Create logs directory if it doesn't exist
LOGS_DIR = BASE_DIR / 'logs'
LOGS_DIR.mkdir(exist_ok=True)

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,

    # ===== FORMATTERS =====
    'formatters': {
        'verbose': {
            'format': '[{levelname}] {asctime} {name} {module}.{funcName}:{lineno} - {message}',
            'style': '{',
            'datefmt': '%Y-%m-%d %H:%M:%S',
        },
        'simple': {
            'format': '[{levelname}] {asctime} - {message}',
            'style': '{',
            'datefmt': '%Y-%m-%d %H:%M:%S',
        },
        'json': {
            # For future: structured JSON logging for log aggregation
            'format': '{"time": "{asctime}", "level": "{levelname}", "logger": "{name}", "message": "{message}"}',
            'style': '{',
        },
    },

    # ===== FILTERS =====
    'filters': {
        'require_debug_false': {
            '()': 'django.utils.log.RequireDebugFalse',
        },
        'require_debug_true': {
            '()': 'django.utils.log.RequireDebugTrue',
        },
    },

    # ===== HANDLERS =====
    'handlers': {
        # Console output (for development)
        'console': {
            'level': 'INFO',
            'class': 'logging.StreamHandler',
            'formatter': 'simple',
        },

        # Debug log (only in DEBUG mode)
        'file_debug': {
            'level': 'DEBUG',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': LOGS_DIR / 'debug.log',
            'maxBytes': 10 * 1024 * 1024,  # 10 MB
            'backupCount': 5,
            'formatter': 'verbose',
            'filters': ['require_debug_true'],
        },

        # Error log (all errors)
        'file_error': {
            'level': 'ERROR',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': LOGS_DIR / 'error.log',
            'maxBytes': 10 * 1024 * 1024,  # 10 MB
            'backupCount': 10,
            'formatter': 'verbose',
        },

        # Orders-specific log
        'file_orders': {
            'level': 'INFO',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': LOGS_DIR / 'orders.log',
            'maxBytes': 10 * 1024 * 1024,  # 10 MB
            'backupCount': 5,
            'formatter': 'verbose',
        },

        # Delivery-specific log
        'file_delivery': {
            'level': 'INFO',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': LOGS_DIR / 'delivery.log',
            'maxBytes': 10 * 1024 * 1024,  # 10 MB
            'backupCount': 5,
            'formatter': 'verbose',
        },

        # API-specific log (Shopify, WooCommerce, DMS)
        'file_api': {
            'level': 'INFO',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': LOGS_DIR / 'api.log',
            'maxBytes': 10 * 1024 * 1024,  # 10 MB
            'backupCount': 5,
            'formatter': 'verbose',
        },

        # Security log (authorization, authentication)
        'file_security': {
            'level': 'WARNING',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': LOGS_DIR / 'security.log',
            'maxBytes': 10 * 1024 * 1024,  # 10 MB
            'backupCount': 10,
            'formatter': 'verbose',
        },

        # Performance log (slow queries, optimization)
        'file_performance': {
            'level': 'INFO',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': LOGS_DIR / 'performance.log',
            'maxBytes': 10 * 1024 * 1024,  # 10 MB
            'backupCount': 5,
            'formatter': 'verbose',
        },
    },

    # ===== LOGGERS =====
    'loggers': {
        # Django framework loggers
        'django': {
            'handlers': ['console', 'file_error'],
            'level': 'INFO',
            'propagate': False,
        },
        'django.request': {
            'handlers': ['file_error'],
            'level': 'ERROR',
            'propagate': False,
        },
        'django.db.backends': {
            # Log SQL queries in DEBUG mode (for N+1 query debugging)
            'handlers': ['console'] if DEBUG else [],
            'level': 'DEBUG' if DEBUG else 'INFO',
            'propagate': False,
        },

        # Application-specific loggers
        'orders': {
            'handlers': ['console', 'file_orders', 'file_error'],
            'level': 'DEBUG' if DEBUG else 'INFO',
            'propagate': False,
        },
        'delivery': {
            'handlers': ['console', 'file_delivery', 'file_error'],
            'level': 'DEBUG' if DEBUG else 'INFO',
            'propagate': False,
        },
        'client': {
            'handlers': ['console', 'file_error'],
            'level': 'DEBUG' if DEBUG else 'INFO',
            'propagate': False,
        },
        'fleet': {
            'handlers': ['console', 'file_error'],
            'level': 'DEBUG' if DEBUG else 'INFO',
            'propagate': False,
        },
        'ezzy_api': {
            'handlers': ['console', 'file_api', 'file_error'],
            'level': 'DEBUG' if DEBUG else 'INFO',
            'propagate': False,
        },
        'core': {
            'handlers': ['console', 'file_error'],
            'level': 'DEBUG' if DEBUG else 'INFO',
            'propagate': False,
        },
        'product': {
            'handlers': ['console', 'file_error'],
            'level': 'DEBUG' if DEBUG else 'INFO',
            'propagate': False,
        },
        'webpages': {
            'handlers': ['console', 'file_error'],
            'level': 'DEBUG' if DEBUG else 'INFO',
            'propagate': False,
        },

        # Security logger
        'security': {
            'handlers': ['file_security', 'file_error'],
            'level': 'WARNING',
            'propagate': False,
        },

        # Performance logger
        'performance': {
            'handlers': ['file_performance'],
            'level': 'INFO',
            'propagate': False,
        },
    },

    # Root logger (catch-all)
    'root': {
        'handlers': ['console', 'file_error'],
        'level': 'INFO',
    },
}

# ===== LOGGING HELPER FUNCTIONS =====

def get_logger(name):
    """
    Helper function to get a logger instance.

    Usage:
        from ezzydelivery.settings import get_logger
        logger = get_logger('orders')
        logger.info("Order created successfully")
    """
    import logging
    return logging.getLogger(name)

# ==========================================
# END LOGGING CONFIGURATION
# ==========================================
```

---

## 🔧 Implementation Steps

### Step 1: Add Configuration to settings.py

1. Open `ezzydelivery/settings.py`
2. Scroll to the end of the file
3. Copy and paste the entire configuration above
4. Save the file

### Step 2: Create logs Directory

```bash
# From project root
mkdir logs

# Verify .gitignore excludes logs (should already be configured)
grep "logs/" .gitignore
```

**Expected output:**
```
logs/
*.log
```

### Step 3: Test Logging Configuration

```bash
# Start Django shell
python manage.py shell
```

```python
# In Django shell
import logging

# Test each logger
logger = logging.getLogger('orders')
logger.debug("This is a debug message")
logger.info("This is an info message")
logger.warning("This is a warning message")
logger.error("This is an error message")

# Test delivery logger
delivery_logger = logging.getLogger('delivery')
delivery_logger.info("Testing delivery logger")

# Test API logger
api_logger = logging.getLogger('ezzy_api')
api_logger.info("Testing API logger")

# Exit shell
exit()
```

### Step 4: Verify Log Files Created

```bash
# List log files
ls -lh logs/

# Check orders log
tail -20 logs/orders.log

# Check error log
tail -20 logs/error.log

# Check API log
tail -20 logs/api.log
```

**Expected output:**
```
-rw-r--r-- 1 user user 1.2K Nov 13 10:30 orders.log
-rw-r--r-- 1 user user  856 Nov 13 10:30 error.log
-rw-r--r-- 1 user user  512 Nov 13 10:30 api.log
-rw-r--r-- 1 user user 2.1K Nov 13 10:30 debug.log
```

---

## 📊 Log File Descriptions

### debug.log
- **Purpose:** Detailed debugging information
- **Active When:** DEBUG=True only
- **Max Size:** 10 MB per file, 5 backups
- **Contains:** All debug-level messages, variable dumps, workflow steps

### error.log
- **Purpose:** All errors and critical issues
- **Active When:** Always
- **Max Size:** 10 MB per file, 10 backups (more backups for errors)
- **Contains:** Exceptions, failures, critical system issues

### orders.log
- **Purpose:** Order management workflow
- **Active When:** Always
- **Max Size:** 10 MB per file, 5 backups
- **Contains:** Order creation, updates, verification, status changes

### delivery.log
- **Purpose:** Delivery task management
- **Active When:** Always
- **Max Size:** 10 MB per file, 5 backups
- **Contains:** Task creation, driver assignments, status updates, DMS push

### api.log
- **Purpose:** External API integrations
- **Active When:** Always
- **Max Size:** 10 MB per file, 5 backups
- **Contains:** Shopify, WooCommerce, Shipday DMS, Mapbox API calls and responses

### security.log
- **Purpose:** Security events
- **Active When:** Always
- **Max Size:** 10 MB per file, 10 backups (more backups for security)
- **Contains:** Authorization failures, authentication issues, suspicious activity

### performance.log
- **Purpose:** Performance monitoring
- **Active When:** Always
- **Max Size:** 10 MB per file, 5 backups
- **Contains:** Slow queries, bottlenecks, optimization opportunities

---

## 💡 Usage Examples

### Example 1: Basic Logging in Views

```python
# orders/views.py
import logging

logger = logging.getLogger('orders')

def create_order(request):
    logger.info("Starting order creation", extra={
        'user_id': request.user.id,
        'action': 'create_order'
    })

    try:
        # Create order logic
        order = Order.objects.create(...)
        logger.info(f"Order {order.id} created successfully")
        return redirect('order_details', order_id=order.id)

    except ValidationError as e:
        logger.warning(f"Order validation failed: {e}", extra={
            'user_id': request.user.id,
            'errors': str(e)
        })
        return render(request, 'orders/create.html', {'errors': e})

    except Exception as e:
        logger.error(f"Unexpected error creating order: {e}", exc_info=True, extra={
            'user_id': request.user.id
        })
        return render(request, 'error.html')
```

### Example 2: Logging in Models

```python
# orders/models.py
import logging

logger = logging.getLogger('orders')

class Order(models.Model):
    # ... fields ...

    def save(self, *args, **kwargs):
        is_new = self.pk is None

        if is_new:
            logger.debug(f"Creating new order for business {self.business_id}")
        else:
            logger.debug(f"Updating order {self.pk}")

        super().save(*args, **kwargs)

        if is_new:
            logger.info(f"Order {self.pk} created successfully")
```

### Example 3: Logging in Signals

```python
# orders/signals.py
import logging

logger = logging.getLogger('orders')

@receiver(post_save, sender=Order)
def create_delivery_task_on_verification(sender, instance, created, **kwargs):
    if instance.order_verification_status == 'Verified':
        logger.info(f"Order {instance.id} verified, creating delivery task", extra={
            'order_id': instance.id,
            'business_id': instance.business_id,
            'signal': 'post_save'
        })

        try:
            task = DeliveryTask.objects.create(order=instance, ...)
            logger.info(f"Delivery task {task.id} created for order {instance.id}")
        except Exception as e:
            logger.error(f"Failed to create delivery task for order {instance.id}: {e}",
                        exc_info=True)
```

### Example 4: API Call Logging

```python
# ezzy_api/views.py
import logging
import time

logger = logging.getLogger('ezzy_api')

def sync_shopify_orders(request):
    logger.info("Starting Shopify order sync", extra={
        'user_id': request.user.id,
        'integration': 'shopify'
    })

    start_time = time.time()

    try:
        response = requests.get(shopify_url, headers=headers, timeout=30)

        elapsed = time.time() - start_time

        logger.info(f"Shopify API request completed in {elapsed:.2f}s", extra={
            'status_code': response.status_code,
            'response_time': elapsed,
            'endpoint': shopify_url
        })

        logger.debug(f"Shopify response: {response.json()}")

        # Process orders...
        orders_synced = 15
        logger.info(f"Synced {orders_synced} orders from Shopify")

    except requests.Timeout:
        logger.error("Shopify API timeout after 30s", extra={
            'endpoint': shopify_url
        })
    except Exception as e:
        logger.error(f"Shopify API error: {e}", exc_info=True)
```

### Example 5: Security Event Logging

```python
# client/views.py
import logging

logger = logging.getLogger('client')
security_logger = logging.getLogger('security')

def order_details(request, order_id):
    user_business = request.user.user_business.first()

    try:
        order = Order.objects.get(id=order_id, business=user_business)
        logger.info(f"User {request.user.id} accessed order {order_id}")

    except Order.DoesNotExist:
        # Log potential unauthorized access attempt
        security_logger.warning(
            f"Unauthorized order access attempt",
            extra={
                'user_id': request.user.id,
                'order_id': order_id,
                'business_id': user_business.business_id if user_business else None,
                'ip_address': request.META.get('REMOTE_ADDR'),
                'user_agent': request.META.get('HTTP_USER_AGENT')
            }
        )
        messages.error(request, "Order not found or access denied")
        return redirect('orders_list')
```

### Example 6: Performance Logging

```python
# delivery/views.py
import logging
import time
from django.db import connection

logger = logging.getLogger('delivery')
perf_logger = logging.getLogger('performance')

def all_delivery_tasks(request):
    start_time = time.time()
    query_count_before = len(connection.queries)

    # Fetch delivery tasks
    tasks = DeliveryTask.objects.select_related('order', 'driver').all()

    elapsed = time.time() - start_time
    query_count = len(connection.queries) - query_count_before

    # Log performance metrics
    perf_logger.info(
        f"Delivery tasks list loaded",
        extra={
            'response_time': elapsed,
            'query_count': query_count,
            'record_count': len(tasks),
            'view': 'all_delivery_tasks'
        }
    )

    # Warn if performance is poor
    if query_count > 10:
        perf_logger.warning(
            f"High query count detected (N+1 problem?)",
            extra={
                'query_count': query_count,
                'view': 'all_delivery_tasks'
            }
        )

    if elapsed > 1.0:
        perf_logger.warning(
            f"Slow response time",
            extra={
                'response_time': elapsed,
                'view': 'all_delivery_tasks'
            }
        )

    return render(request, 'delivery/tasks.html', {'tasks': tasks})
```

---

## 🔍 Log Analysis Commands

### View Recent Logs

```bash
# View last 50 lines of orders log
tail -50 logs/orders.log

# Follow orders log in real-time
tail -f logs/orders.log

# View errors only
grep -i "ERROR" logs/error.log

# View warnings and errors
grep -E "WARNING|ERROR" logs/orders.log
```

### Filter by Date/Time

```bash
# View logs from today
grep "2025-11-13" logs/orders.log

# View logs from last hour (if using verbose format)
grep "$(date '+%Y-%m-%d %H'):" logs/orders.log
```

### Filter by User

```bash
# Find all actions by user_id=123
grep "user_id': 123" logs/orders.log

# Find all order-related actions
grep "order_id" logs/orders.log
```

### Count Log Entries

```bash
# Count errors in last 24 hours
grep "$(date '+%Y-%m-%d')" logs/error.log | wc -l

# Count API calls
grep "API request completed" logs/api.log | wc -l
```

### Find Performance Issues

```bash
# Find slow queries
grep "response_time.*[5-9]\." logs/performance.log

# Find N+1 query problems
grep "High query count" logs/performance.log
```

---

## 🚨 Common Issues and Solutions

### Issue 1: Log Files Not Created

**Symptoms:** Running the test script but log files don't appear

**Solution:**
```bash
# Check if logs directory exists
ls -ld logs/

# If not, create it
mkdir logs

# Check permissions
chmod 755 logs/

# Restart Django
python manage.py runserver
```

### Issue 2: "Permission Denied" Writing to Log Files

**Symptoms:** `PermissionError: [Errno 13] Permission denied: 'logs/orders.log'`

**Solution:**
```bash
# Fix permissions on logs directory
chmod 755 logs/
chmod 644 logs/*.log

# Or delete and recreate
rm -rf logs/
mkdir logs
```

### Issue 3: Logs Filling Up Disk Space

**Symptoms:** Disk space running out

**Solution:**
```bash
# Check log sizes
du -sh logs/*

# Rotate logs manually
cd logs/
for f in *.log; do mv "$f" "$f.$(date +%Y%m%d)"; done

# Reduce maxBytes in settings.py (currently 10MB)
# Change to 5MB: 'maxBytes': 5 * 1024 * 1024

# Or increase backupCount to delete older files faster
```

### Issue 4: Too Many Debug Messages in Production

**Symptoms:** Log files grow too quickly in production

**Solution:**
```python
# In settings.py, change loggers level based on DEBUG
'orders': {
    'handlers': ['console', 'file_orders', 'file_error'],
    'level': 'DEBUG' if DEBUG else 'INFO',  # INFO in production!
    'propagate': False,
},
```

---

## ✅ Verification Checklist

After adding logging configuration:

- [ ] Configuration added to settings.py
- [ ] `logs/` directory created
- [ ] `logs/` in .gitignore (already configured)
- [ ] Test logging in Django shell - all messages logged
- [ ] Log files created (orders.log, error.log, etc.)
- [ ] Log files are readable (not permission errors)
- [ ] Log rotation tested (create 11MB file, see rotation)
- [ ] Console output working (see logs in terminal)
- [ ] Different log levels work (debug, info, warning, error)
- [ ] Module-specific loggers work (orders, delivery, etc.)

---

## 📚 Next Steps

After adding this configuration:

1. **Test logging:** Run Django shell test (see Step 3 above)
2. **Add logger imports:** Add `import logging` and `logger = logging.getLogger('...')` to each file
3. **Run conversion script:** `python scripts/replace_print_with_logging.py` (dry run first)
4. **Review changes:** Check suggested conversions are correct
5. **Apply changes:** `python scripts/replace_print_with_logging.py --commit`
6. **Test application:** Verify no broken functionality
7. **Commit:** `git add . && git commit -m "feat: Add comprehensive logging configuration"`

---

**Last Updated:** November 13, 2025
**Related Documentation:**
- [PRINT_STATEMENT_REMOVAL_PLAN.md](PRINT_STATEMENT_REMOVAL_PLAN.md)
- [IMMEDIATE_ACTIONS_REQUIRED.md](IMMEDIATE_ACTIONS_REQUIRED.md)
- [SECURE_CODE_FIXES.md](SECURE_CODE_FIXES.md)
