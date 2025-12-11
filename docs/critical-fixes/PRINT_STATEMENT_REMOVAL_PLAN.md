# Print Statement Removal and Logging Implementation Plan

**Date:** November 13, 2025
**Project:** EzzyDelivery Qatar Delivery Services
**Purpose:** Remove 283 debug print statements and replace with proper logging
**Status:** 🚧 In Progress

---

## 📊 Executive Summary

### Current State
- **Total Print Statements Found:** 283 across 12 files
- **Code Quality Impact:** Reduces score by ~1.5 points
- **Production Risk:** Debug output visible to users, performance overhead
- **Estimated Fix Time:** 8-12 hours

### Distribution by File

| File | Print Count | Priority | Estimated Time |
|------|-------------|----------|----------------|
| [orders/views.py](../../orders/views.py) | 83 | 🔴 CRITICAL | 3 hours |
| [business/views.py](../../business/views.py) | 76 | 🔴 CRITICAL | 2.5 hours |
| [core/views.py](../../core/views.py) | 54 | 🔴 HIGH | 2 hours |
| [fleet/views.py](../../fleet/views.py) | 25 | 🟡 MEDIUM | 1 hour |
| [delivery/views.py](../../delivery/views.py) | 20 | 🟡 MEDIUM | 1 hour |
| [orders/models.py](../../orders/models.py) | 7 | 🟢 LOW | 30 min |
| [product/views.py](../../product/views.py) | 6 | 🟢 LOW | 30 min |
| [orders/signals.py](../../orders/signals.py) | 4 | 🟢 LOW | 20 min |
| [ezzy_api/views.py](../../ezzy_api/views.py) | 3 | 🟢 LOW | 20 min |
| [webpages/views.py](../../webpages/views.py) | 2 | 🟢 LOW | 10 min |
| [fleet/signals.py](../../fleet/signals.py) | 2 | 🟢 LOW | 10 min |
| [webpages/forms.py](../../webpages/forms.py) | 1 | 🟢 LOW | 5 min |

---

## 🎯 Implementation Strategy

### Phase 1: Setup Logging (30 minutes)

1. **Create logging configuration in settings.py**
2. **Add logger imports to each file**
3. **Test logging configuration**

### Phase 2: Replace Print Statements (8-10 hours)

**Conversion Rules:**
```python
# ❌ Before (Debug Print)
print(f"User {user.id} accessed order {order_id}")

# ✅ After (Proper Logging)
logger.info(f"User {user.id} accessed order {order_id}")

# ❌ Before (Error Print)
print(f"Error: {e}")

# ✅ After (Proper Logging with Context)
logger.error(f"Failed to fetch Shopify order: {e}", exc_info=True, extra={
    'user_id': request.user.id,
    'order_id': order_id
})
```

**Logging Level Guidelines:**
- `logger.debug()` - Detailed diagnostic info (variable values, loop iterations)
- `logger.info()` - Informational messages (user actions, workflow steps)
- `logger.warning()` - Warning messages (deprecated features, soft errors)
- `logger.error()` - Error messages (exceptions, failures)
- `logger.critical()` - Critical system failures

### Phase 3: Testing (1-2 hours)

1. **Verify logging output in development**
2. **Check log file rotation**
3. **Test error capturing**
4. **Performance verification**

---

## 🔧 Implementation Details

### Step 1: Update Django Settings

Add to `ezzydelivery/settings.py`:

```python
# ===== LOGGING CONFIGURATION =====
import os
from pathlib import Path

# Create logs directory if it doesn't exist
LOGS_DIR = BASE_DIR / 'logs'
LOGS_DIR.mkdir(exist_ok=True)

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
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
    },
    'filters': {
        'require_debug_false': {
            '()': 'django.utils.log.RequireDebugFalse',
        },
        'require_debug_true': {
            '()': 'django.utils.log.RequireDebugTrue',
        },
    },
    'handlers': {
        'console': {
            'level': 'INFO',
            'class': 'logging.StreamHandler',
            'formatter': 'simple',
        },
        'file_debug': {
            'level': 'DEBUG',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': LOGS_DIR / 'debug.log',
            'maxBytes': 10 * 1024 * 1024,  # 10 MB
            'backupCount': 5,
            'formatter': 'verbose',
            'filters': ['require_debug_true'],
        },
        'file_error': {
            'level': 'ERROR',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': LOGS_DIR / 'error.log',
            'maxBytes': 10 * 1024 * 1024,  # 10 MB
            'backupCount': 10,
            'formatter': 'verbose',
        },
        'file_orders': {
            'level': 'INFO',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': LOGS_DIR / 'orders.log',
            'maxBytes': 10 * 1024 * 1024,  # 10 MB
            'backupCount': 5,
            'formatter': 'verbose',
        },
        'file_delivery': {
            'level': 'INFO',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': LOGS_DIR / 'delivery.log',
            'maxBytes': 10 * 1024 * 1024,  # 10 MB
            'backupCount': 5,
            'formatter': 'verbose',
        },
        'file_api': {
            'level': 'INFO',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': LOGS_DIR / 'api.log',
            'maxBytes': 10 * 1024 * 1024,  # 10 MB
            'backupCount': 5,
            'formatter': 'verbose',
        },
    },
    'loggers': {
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
        'business': {
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
    },
    'root': {
        'handlers': ['console', 'file_error'],
        'level': 'INFO',
    },
}
```

### Step 2: Add Logger Imports

**For each affected file, add at the top:**

```python
import logging

# Get logger for this module
logger = logging.getLogger(__name__)
```

**File-specific loggers:**
- `orders/views.py` → `logger = logging.getLogger('orders')`
- `orders/models.py` → `logger = logging.getLogger('orders')`
- `orders/signals.py` → `logger = logging.getLogger('orders')`
- `delivery/views.py` → `logger = logging.getLogger('delivery')`
- `business/views.py` → `logger = logging.getLogger('business')`
- `fleet/views.py` → `logger = logging.getLogger('fleet')`
- `fleet/signals.py` → `logger = logging.getLogger('fleet')`
- `ezzy_api/views.py` → `logger = logging.getLogger('ezzy_api')`
- `core/views.py` → `logger = logging.getLogger('core')`
- `product/views.py` → `logger = logging.getLogger('product')`
- `webpages/views.py` → `logger = logging.getLogger('webpages')`
- `webpages/forms.py` → `logger = logging.getLogger('webpages')`

---

## 📝 Conversion Examples by Use Case

### Use Case 1: Debug Variable Inspection

```python
# ❌ Before
print("api_data:", api_data)
print(f"business_id = {business.business_id}")

# ✅ After
logger.debug(f"API data retrieved: {api_data}")
logger.debug(f"Processing business_id: {business.business_id}")
```

### Use Case 2: Tracking User Actions

```python
# ❌ Before
print(f"User {request.user} updated order {order_id}")

# ✅ After
logger.info(
    f"User {request.user.id} updated order {order_id}",
    extra={
        'user_id': request.user.id,
        'username': request.user.username,
        'order_id': order_id,
        'action': 'update'
    }
)
```

### Use Case 3: Exception Handling

```python
# ❌ Before
try:
    order = Order.objects.get(id=order_id)
except Exception as e:
    print(f"Error: {e}")

# ✅ After
try:
    order = Order.objects.get(id=order_id)
except Order.DoesNotExist:
    logger.warning(
        f"Order {order_id} not found",
        extra={'order_id': order_id, 'user_id': request.user.id}
    )
except Exception as e:
    logger.error(
        f"Unexpected error retrieving order {order_id}: {e}",
        exc_info=True,
        extra={'order_id': order_id}
    )
```

### Use Case 4: API Request/Response Logging

```python
# ❌ Before
print(f"Shopify API response: {response.json()}")

# ✅ After
logger.info(
    f"Shopify API request successful",
    extra={
        'status_code': response.status_code,
        'response_time': response.elapsed.total_seconds(),
        'endpoint': response.url
    }
)
logger.debug(f"Shopify API response body: {response.json()}")
```

### Use Case 5: Signal Processing

```python
# ❌ Before (in signals.py)
print(f"Signal received for order {instance.id}")

# ✅ After
logger.info(
    f"Order created signal received",
    extra={
        'order_id': instance.id,
        'business_id': instance.business_id,
        'signal': 'post_save'
    }
)
```

### Use Case 6: Workflow Steps

```python
# ❌ Before
print("Step 1: Fetching business data")
print("Step 2: Validating API settings")
print("Step 3: Making API request")

# ✅ After
logger.info("Starting Shopify order sync workflow")
logger.debug("Step 1: Fetching business data")
logger.debug("Step 2: Validating API settings")
logger.debug("Step 3: Making API request to Shopify")
logger.info("Shopify order sync completed successfully")
```

---

## 🔄 Automated Conversion Script

### Find and Replace Patterns

**Script: `scripts/replace_print_with_logging.py`**

```python
#!/usr/bin/env python3
"""
Script to help convert print statements to logging calls.
This is a semi-automated tool - ALWAYS review changes manually!
"""

import re
import os
import sys
from pathlib import Path

def analyze_print_statement(line, line_num):
    """Analyze a print statement and suggest logging level."""
    line_lower = line.lower()

    # Determine logging level based on content
    if any(word in line_lower for word in ['error', 'exception', 'failed', 'failure']):
        return 'error'
    elif any(word in line_lower for word in ['warning', 'warn', 'deprecated']):
        return 'warning'
    elif any(word in line_lower for word in ['step', 'processing', 'fetching', 'created', 'updated']):
        return 'info'
    else:
        return 'debug'

def convert_print_to_logging(file_path, dry_run=True):
    """Convert print statements to logging calls in a Python file."""
    print(f"\n{'='*60}")
    print(f"Processing: {file_path}")
    print(f"{'='*60}")

    with open(file_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    changes = []
    new_lines = []

    for i, line in enumerate(lines, 1):
        # Match print statements
        if re.match(r'^\s*print\(', line):
            level = analyze_print_statement(line, i)

            # Extract indentation
            indent = re.match(r'^(\s*)', line).group(1)

            # Extract print content
            # Handle both print("message") and print(variable)
            content_match = re.search(r'print\((.*)\)', line)
            if content_match:
                content = content_match.group(1)

                # Create logging statement
                new_line = f'{indent}logger.{level}({content})\n'

                changes.append({
                    'line_num': i,
                    'old': line.rstrip(),
                    'new': new_line.rstrip(),
                    'level': level
                })

                new_lines.append(new_line)
            else:
                new_lines.append(line)
        else:
            new_lines.append(line)

    # Print summary
    print(f"\nFound {len(changes)} print statements to convert:")
    for change in changes[:10]:  # Show first 10
        print(f"\nLine {change['line_num']}: [{change['level'].upper()}]")
        print(f"  Old: {change['old']}")
        print(f"  New: {change['new']}")

    if len(changes) > 10:
        print(f"\n... and {len(changes) - 10} more changes")

    if not dry_run and changes:
        # Write changes
        with open(file_path, 'w', encoding='utf-8') as f:
            f.writelines(new_lines)
        print(f"\n✅ Converted {len(changes)} print statements in {file_path}")

    return len(changes)

def main():
    # Files with print statements (from grep results)
    files = [
        'orders/views.py',      # 83 prints
        'business/views.py',      # 76 prints
        'core/views.py',        # 54 prints
        'fleet/views.py',       # 25 prints
        'delivery/views.py',    # 20 prints
        'orders/models.py',     # 7 prints
        'product/views.py',     # 6 prints
        'orders/signals.py',    # 4 prints
        'ezzy_api/views.py',    # 3 prints
        'webpages/views.py',    # 2 prints
        'fleet/signals.py',     # 2 prints
        'webpages/forms.py',    # 1 print
    ]

    base_dir = Path(__file__).resolve().parent.parent

    dry_run = '--commit' not in sys.argv

    if dry_run:
        print("🔍 DRY RUN MODE - No changes will be made")
        print("Use --commit flag to apply changes\n")

    total_changes = 0
    for file_rel in files:
        file_path = base_dir / file_rel
        if file_path.exists():
            count = convert_print_to_logging(file_path, dry_run)
            total_changes += count
        else:
            print(f"⚠️  File not found: {file_path}")

    print(f"\n{'='*60}")
    print(f"SUMMARY: {total_changes} print statements found across {len(files)} files")
    if dry_run:
        print("Run with --commit flag to apply changes")
    else:
        print("✅ All changes applied!")
    print(f"{'='*60}\n")

if __name__ == '__main__':
    main()
```

**Usage:**
```bash
# Preview changes (dry run)
python scripts/replace_print_with_logging.py

# Apply changes
python scripts/replace_print_with_logging.py --commit
```

---

## ✅ Implementation Checklist

### Pre-Implementation
- [ ] Create `logs/` directory: `mkdir logs`
- [ ] Add `logs/` to `.gitignore` (already done)
- [ ] Backup current codebase: `git commit -m "Backup before logging implementation"`

### Phase 1: Logging Setup (30 min)
- [ ] Add LOGGING configuration to `ezzydelivery/settings.py`
- [ ] Create `scripts/` directory
- [ ] Save conversion script: `scripts/replace_print_with_logging.py`
- [ ] Test logging configuration:
  ```bash
  python manage.py shell
  >>> import logging
  >>> logger = logging.getLogger('orders')
  >>> logger.info("Test message")
  >>> exit()
  ```
- [ ] Verify log file created: `ls logs/orders.log`

### Phase 2: Add Logger Imports (1 hour)
- [ ] `orders/views.py` - Add `logger = logging.getLogger('orders')`
- [ ] `orders/models.py` - Add `logger = logging.getLogger('orders')`
- [ ] `orders/signals.py` - Add `logger = logging.getLogger('orders')`
- [ ] `business/views.py` - Add `logger = logging.getLogger('business')`
- [ ] `delivery/views.py` - Add `logger = logging.getLogger('delivery')`
- [ ] `fleet/views.py` - Add `logger = logging.getLogger('fleet')`
- [ ] `fleet/signals.py` - Add `logger = logging.getLogger('fleet')`
- [ ] `ezzy_api/views.py` - Add `logger = logging.getLogger('ezzy_api')`
- [ ] `core/views.py` - Add `logger = logging.getLogger('core')`
- [ ] `product/views.py` - Add `logger = logging.getLogger('product')`
- [ ] `webpages/views.py` - Add `logger = logging.getLogger('webpages')`
- [ ] `webpages/forms.py` - Add `logger = logging.getLogger('webpages')`

### Phase 3: Convert Print Statements (8-10 hours)

**Priority Order:**

#### 🔴 CRITICAL Files (3 days, 5.5 hours)
- [ ] **Day 1** - `orders/views.py` (83 prints, 3 hours)
  - [ ] Run conversion script (dry run)
  - [ ] Review suggested changes
  - [ ] Manual review and refinement
  - [ ] Test critical order workflows
  - [ ] Commit: "refactor(orders): Replace print statements with logging"

- [ ] **Day 2** - `business/views.py` (76 prints, 2.5 hours)
  - [ ] Run conversion script
  - [ ] Manual review
  - [ ] Test business/client workflows
  - [ ] Commit: "refactor(client): Replace print statements with logging"

#### 🟡 HIGH Priority (1 day, 2 hours)
- [ ] **Day 3** - `core/views.py` (54 prints, 2 hours)
  - [ ] Run conversion script
  - [ ] Manual review
  - [ ] Test core functionality
  - [ ] Commit: "refactor(core): Replace print statements with logging"

#### 🟢 MEDIUM Priority (1 day, 2 hours)
- [ ] **Day 4** - Batch conversion
  - [ ] `fleet/views.py` (25 prints, 1 hour)
  - [ ] `delivery/views.py` (20 prints, 1 hour)
  - [ ] Test fleet and delivery workflows
  - [ ] Commit: "refactor(fleet,delivery): Replace print statements with logging"

#### 🟢 LOW Priority (Half day, 2 hours)
- [ ] **Day 5** - Final cleanup
  - [ ] `orders/models.py` (7 prints)
  - [ ] `product/views.py` (6 prints)
  - [ ] `orders/signals.py` (4 prints)
  - [ ] `ezzy_api/views.py` (3 prints)
  - [ ] `webpages/views.py` (2 prints)
  - [ ] `fleet/signals.py` (2 prints)
  - [ ] `webpages/forms.py` (1 print)
  - [ ] Test all workflows end-to-end
  - [ ] Commit: "refactor(all): Complete logging migration, remove all print statements"

### Phase 4: Testing (1-2 hours)
- [ ] Run development server: `python manage.py runserver`
- [ ] Test critical workflows:
  - [ ] Create new order
  - [ ] Verify order
  - [ ] Create delivery task
  - [ ] Assign driver
  - [ ] Update order status
  - [ ] Sync with Shopify
- [ ] Verify log files generated:
  - [ ] `logs/orders.log` exists and has entries
  - [ ] `logs/delivery.log` exists and has entries
  - [ ] `logs/api.log` exists and has entries
  - [ ] `logs/error.log` captures errors properly
- [ ] Check log file rotation works (max 10MB per file)
- [ ] Verify no print statements remain:
  ```bash
  grep -r "^\s*print(" --include="*.py" orders/ business/ delivery/ fleet/ core/ product/ ezzy_api/ webpages/
  ```
- [ ] Run tests: `python manage.py test`
- [ ] Check for any broken functionality

### Phase 5: Documentation (30 min)
- [ ] Update this document with completion status
- [ ] Document any issues encountered
- [ ] Add logging usage examples to developer guide
- [ ] Update `.env.example` with logging settings if needed

### Phase 6: Final Verification (30 min)
- [ ] Code quality check:
  ```bash
  flake8 orders/ business/ delivery/ --count --select=E9,F63,F7,F82 --show-source --statistics
  ```
- [ ] Security check:
  ```bash
  python manage.py check --deploy
  ```
- [ ] Performance check: Verify no performance degradation
- [ ] Create final commit:
  ```bash
  git add .
  git commit -m "refactor: Complete logging implementation, remove 283 print statements

  - Replace all print() calls with proper logging
  - Add structured logging configuration
  - Implement log file rotation (10MB max, 5-10 backups)
  - Add module-specific loggers (orders, delivery, client, etc.)
  - Improve debugging with contextual information

  Fixes: #[issue_number]
  Improves code quality score by ~1.5 points"
  ```

---

## 📈 Expected Benefits

### Code Quality
- ✅ Code quality score increases from 4.2/10 to ~5.7/10
- ✅ Remove 283 technical debt items
- ✅ Professional error handling and debugging

### Production Benefits
- ✅ No more debug output visible to users
- ✅ Structured logs for better debugging
- ✅ Log aggregation and analysis possible
- ✅ Better error tracking and monitoring
- ✅ Audit trail for user actions
- ✅ Performance insights from logs

### Development Benefits
- ✅ Easier debugging with structured logs
- ✅ Filter logs by severity level
- ✅ Module-specific log files
- ✅ Automatic log rotation (no disk space issues)
- ✅ Better error context with `exc_info=True`

### Performance
- ✅ Logging is more performant than print()
- ✅ Can disable debug logs in production
- ✅ Async logging possible (future enhancement)

---

## ⚠️ Common Pitfalls to Avoid

### ❌ Don't Do This:
```python
# Bad: Logging sensitive data
logger.info(f"User password: {password}")

# Bad: Logging huge objects
logger.debug(f"Response: {response}")  # If response is 10MB JSON

# Bad: Logging in tight loops
for item in large_list:
    logger.debug(f"Processing {item}")  # 10,000 log entries!

# Bad: Wrong log level
logger.error("User clicked button")  # Should be info or debug
```

### ✅ Do This Instead:
```python
# Good: Never log sensitive data
logger.info(f"User authenticated successfully", extra={'user_id': user.id})

# Good: Log summary, not full object
logger.debug(f"Response received: {len(response)} bytes, status={response.status_code}")

# Good: Log summary of batch operations
logger.info(f"Processing {len(large_list)} items")
# ... process items ...
logger.info(f"Completed processing {processed_count} items")

# Good: Appropriate log level
logger.info("User clicked export button", extra={'user_id': user.id, 'action': 'export'})
```

---

## 📚 Resources

### Django Logging Documentation
- [Django Logging](https://docs.djangoproject.com/en/4.2/topics/logging/)
- [Python Logging Cookbook](https://docs.python.org/3/howto/logging-cookbook.html)
- [Logging Best Practices](https://docs.python-guide.org/writing/logging/)

### Log Analysis Tools
- **Local Development:** View logs with `tail -f logs/orders.log`
- **Production:** Consider:
  - ELK Stack (Elasticsearch, Logstash, Kibana)
  - Graylog
  - Papertrail
  - Loggly
  - Sentry (for error tracking)

---

## 📊 Progress Tracking

### Completion Status

| Phase | Status | Completion Date | Notes |
|-------|--------|-----------------|-------|
| Logging Setup | ⏳ Pending | - | - |
| Logger Imports | ⏳ Pending | - | - |
| orders/views.py | ⏳ Pending | - | 83 prints to convert |
| business/views.py | ⏳ Pending | - | 76 prints to convert |
| core/views.py | ⏳ Pending | - | 54 prints to convert |
| fleet/views.py | ⏳ Pending | - | 25 prints to convert |
| delivery/views.py | ⏳ Pending | - | 20 prints to convert |
| Remaining Files | ⏳ Pending | - | 25 prints across 7 files |
| Testing | ⏳ Pending | - | - |
| Documentation | ⏳ Pending | - | - |
| Final Verification | ⏳ Pending | - | - |

**Legend:**
- ⏳ Pending
- 🚧 In Progress
- ✅ Completed
- ❌ Blocked

---

## 🎯 Success Criteria

This task is considered complete when:

- [ ] All 283 print statements removed
- [ ] All files have proper logging imports
- [ ] Logging configuration added to settings.py
- [ ] All tests pass
- [ ] No functionality broken
- [ ] Log files generated correctly
- [ ] Log rotation works (10MB limit per file)
- [ ] Code quality score improved by ~1.5 points
- [ ] Documentation updated
- [ ] Changes committed to git

---

**Last Updated:** November 13, 2025
**Next Review:** After Phase 3 completion
**Maintainer:** EzzyDelivery Development Team

---

## 🚀 Quick Start

**To begin implementation:**

```bash
# 1. Create logs directory
mkdir logs

# 2. Create scripts directory
mkdir scripts

# 3. Update settings.py (see Step 1 above)

# 4. Create conversion script (see Automated Conversion Script section)

# 5. Test logging configuration
python manage.py shell
>>> import logging
>>> logger = logging.getLogger('orders')
>>> logger.info("Logging test successful")
>>> exit()

# 6. Verify log file created
ls logs/

# 7. Start conversion (dry run first)
python scripts/replace_print_with_logging.py

# 8. Review suggested changes

# 9. Apply changes (when ready)
python scripts/replace_print_with_logging.py --commit
```

---

**Remember:** This is a critical code quality improvement that will make debugging, monitoring, and maintenance significantly easier. Take your time, test thoroughly, and always commit after each major file conversion!
