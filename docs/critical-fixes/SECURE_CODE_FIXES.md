# 🔒 Secure Code Fixes - Ready to Implement

**Date:** November 13, 2025
**Status:** Ready for copy-paste implementation
**Priority:** CRITICAL

---

## 📋 Table of Contents

1. [Fix #1: Remove Hardcoded Shopify Token](#fix-1-remove-hardcoded-shopify-token)
2. [Fix #2: Create .env File](#fix-2-create-env-file)
3. [Fix #3: Update settings.py](#fix-3-update-settingspy)
4. [Fix #4: Fix IDOR Vulnerabilities](#fix-4-fix-idor-vulnerabilities)
5. [Fix #5: Add Logging Instead of Print](#fix-5-add-logging-instead-of-print)
6. [Fix #6: Add Database Indexes](#fix-6-add-database-indexes)

---

## Fix #1: Remove Hardcoded Shopify Token

### File: `orders/views.py` (Lines 524-568)

**REPLACE THIS CODE:**

```python
def get_order_by_api(request):
    business = business_models.Business.objects.get(user_id=request.user.user_business.first().user_id)
    api_data = business_models.BusinessApiSettings.objects.filter(business_id=business.business_id, is_verify_api='True', is_default='True' ).first()
    print(api_data)

    headers = {
        'Content-Type': 'application/json',
        'X-Shopify-Access-Token': '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'  # ❌ HARDCODED!
    }
    get_orders = requests.get('https://hn0d1z-qe.myshopify.com/admin/api/2024-10/orders.json?status=any', headers=headers)
```

**WITH THIS SECURE CODE:**

```python
import logging
from django.contrib import messages
from django.shortcuts import redirect

logger = logging.getLogger(__name__)

def get_order_by_api(request):
    """
    Fetch orders from Shopify using secure API credentials from database.

    Security: Uses per-business API credentials, validates business ownership,
    includes proper error handling and logging.
    """
    # 1. Get user's business (with error handling)
    user_business = request.user.user_business.first()
    if not user_business:
        messages.error(request, "No business associated with your account")
        logger.warning(f"User {request.user.id} attempted to access Shopify API without business")
        return redirect('business_dashboard')

    try:
        business = business_models.Business.objects.get(user_id=user_business.user_id)
    except business_models.Business.DoesNotExist:
        messages.error(request, "Business not found")
        return redirect('business_dashboard')

    # 2. Get verified API settings for this business
    try:
        api_data = business_models.BusinessApiSettings.objects.get(
            business_id=business.business_id,
            api_type='shopify',  # Specify Shopify
            is_verify_api=True,
            is_default=True
        )
    except business_models.BusinessApiSettings.DoesNotExist:
        messages.error(request, "No verified Shopify API configuration found. Please configure API settings first.")
        logger.warning(f"Business {business.business_id} attempted Shopify import without verified API settings")
        return redirect('business_settings')

    # 3. Build secure API request using credentials from database
    headers = {
        'Content-Type': 'application/json',
        'X-Shopify-Access-Token': api_data.api_access_token  # ✅ From database, not hardcoded!
    }

    # Build URL from settings
    api_url = api_data.site_api_url or f"https://{api_data.shop_name}.myshopify.com"
    api_version = api_data.api_version or '2024-10'
    endpoint = f"{api_url}/admin/api/{api_version}/orders.json?status=any"

    # 4. Get date range
    if request.method == 'POST':
        order_list_start_date = request.POST.get('start_date')
        order_list_end_date = request.POST.get('end_date')
        logger.info(f"Fetching Shopify orders with custom dates: {order_list_start_date} to {order_list_end_date}")
    else:
        order_list_start_date = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
        order_list_end_date = datetime.now().strftime('%Y-%m-%d')
        logger.info(f"Fetching Shopify orders with default dates: {order_list_start_date} to {order_list_end_date}")

    # 5. Make API request with proper error handling
    try:
        get_orders = requests.get(endpoint, headers=headers, timeout=30)
        get_orders.raise_for_status()  # Raise exception for 4xx/5xx status codes
    except requests.exceptions.Timeout:
        messages.error(request, "Shopify API request timed out. Please try again.")
        logger.error(f"Shopify API timeout for business {business.business_id}")
        return redirect('orders_all_list')
    except requests.exceptions.RequestException as e:
        messages.error(request, "Failed to connect to Shopify. Please check your API settings.")
        logger.error(f"Shopify API error for business {business.business_id}: {str(e)}")
        return redirect('orders_all_list')

    # 6. Process response
    if get_orders.status_code == 200:
        order_data = get_orders.json()
        orders = order_data.get('orders', [])

        # Filter by date range
        filtered_orders = [
            order for order in orders
            if order_list_start_date <= order['created_at'][:10] <= order_list_end_date
        ]
        filtered_orders.sort(key=lambda x: x['created_at'], reverse=True)

        logger.info(f"Successfully fetched {len(filtered_orders)} orders from Shopify for business {business.business_id}")

        data = {
            'order_data': order_data,
            'orders': filtered_orders,
            'business': business,
            'start_date': order_list_start_date,
            'end_date': order_list_end_date,
        }
        return render(request, 'orders/get_order_by_api.html', data)
    else:
        messages.error(request, f"Shopify API returned error: {get_orders.status_code}")
        logger.error(f"Shopify API error {get_orders.status_code} for business {business.business_id}")
        return redirect('orders_all_list')
```

---

## Fix #2: Create .env File

### File: `.env` (Create in project root)

```bash
# .env - NEVER COMMIT THIS FILE!
# Copy from .env.example and fill with real values

# ===== DJANGO CORE =====
SECRET_KEY=django-insecure-CHANGE-THIS-TO-RANDOM-50-CHAR-STRING
DEBUG=False
ALLOWED_HOSTS=localhost,127.0.0.1,ezzydelivery.qa,www.ezzydelivery.qa

# ===== DATABASE =====
DATABASE_URL=postgresql://username:password@localhost:5432/ezzydelivery
# For SQLite (development only):
# DATABASE_URL=sqlite:///db.sqlite3

# ===== SHOPIFY API =====
# Get these from: https://YOUR-SHOP.myshopify.com/admin/settings/apps/development
SHOPIFY_API_KEY=your_shopify_api_key_here
SHOPIFY_API_SECRET=your_shopify_api_secret_here
SHOPIFY_ACCESS_TOKEN=your_new_shopify_token_here
SHOPIFY_SHOP_NAME=hn0d1z-qe
SHOPIFY_API_VERSION=2024-10

# ===== WOOCOMMERCE API (if used) =====
WOOCOMMERCE_URL=https://yourstore.com
WOOCOMMERCE_CONSUMER_KEY=ck_xxxxxxxxxxxxx
WOOCOMMERCE_CONSUMER_SECRET=cs_xxxxxxxxxxxxx

# ===== DMS / SHIPDAY INTEGRATION =====
DMS_API_KEY=your_dms_api_key
DMS_API_SECRET=your_dms_secret
DMS_BASE_URL=https://api.shipday.com

# ===== MAPBOX / HERE MAPS =====
MAPBOX_ACCESS_TOKEN=your_mapbox_token
HERE_MAPS_API_KEY=your_here_maps_key

# ===== EMAIL CONFIGURATION =====
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=your_email@gmail.com
EMAIL_HOST_PASSWORD=your_app_specific_password

# ===== SECURITY SETTINGS =====
SESSION_COOKIE_SECURE=True
CSRF_COOKIE_SECURE=True
SECURE_SSL_REDIRECT=True
SECURE_HSTS_SECONDS=31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS=True
SECURE_HSTS_PRELOAD=True

# ===== LOGGING =====
LOG_LEVEL=INFO
```

### File: `.env.example` (Create as template - COMMIT THIS)

```bash
# .env.example - Copy to .env and fill with real values

# Django Core
SECRET_KEY=generate_with_secrets.token_urlsafe
DEBUG=False
ALLOWED_HOSTS=localhost,yourdomain.com

# Database
DATABASE_URL=postgresql://user:password@localhost:5432/dbname

# Shopify API
SHOPIFY_API_KEY=your_api_key
SHOPIFY_API_SECRET=your_api_secret
SHOPIFY_ACCESS_TOKEN=your_access_token
SHOPIFY_SHOP_NAME=your-shop-name
SHOPIFY_API_VERSION=2024-10

# WooCommerce API
WOOCOMMERCE_URL=https://yourstore.com
WOOCOMMERCE_CONSUMER_KEY=ck_xxxxx
WOOCOMMERCE_CONSUMER_SECRET=cs_xxxxx

# DMS Integration
DMS_API_KEY=your_dms_key
DMS_API_SECRET=your_dms_secret
DMS_BASE_URL=https://api.shipday.com

# Mapbox / HERE Maps
MAPBOX_ACCESS_TOKEN=your_token
HERE_MAPS_API_KEY=your_key

# Email
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=your_email@gmail.com
EMAIL_HOST_PASSWORD=your_app_password

# Security
SESSION_COOKIE_SECURE=True
CSRF_COOKIE_SECURE=True
SECURE_SSL_REDIRECT=True
```

---

## Fix #3: Update settings.py

### File: `ezzydelivery/settings.py`

**ADD THIS AT THE TOP (after imports):**

```python
import os
from pathlib import Path
from decouple import config, Csv  # pip install python-decouple

# Build paths inside the project
BASE_DIR = Path(__file__).resolve().parent.parent

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = config('SECRET_KEY')

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = config('DEBUG', default=False, cast=bool)

ALLOWED_HOSTS = config('ALLOWED_HOSTS', default='localhost', cast=Csv())

# Application definition
INSTALLED_APPS = [
    # ... existing apps
]

# Database
# https://docs.djangoproject.com/en/4.2/ref/settings/#databases
DATABASES = {
    'default': dj_database_url.config(
        default=config('DATABASE_URL'),
        conn_max_age=600
    )
}

# Shopify Configuration
SHOPIFY_CONFIG = {
    'API_KEY': config('SHOPIFY_API_KEY', default=''),
    'API_SECRET': config('SHOPIFY_API_SECRET', default=''),
    'ACCESS_TOKEN': config('SHOPIFY_ACCESS_TOKEN', default=''),
    'SHOP_NAME': config('SHOPIFY_SHOP_NAME', default=''),
    'API_VERSION': config('SHOPIFY_API_VERSION', default='2024-10'),
}

# WooCommerce Configuration
WOOCOMMERCE_CONFIG = {
    'URL': config('WOOCOMMERCE_URL', default=''),
    'CONSUMER_KEY': config('WOOCOMMERCE_CONSUMER_KEY', default=''),
    'CONSUMER_SECRET': config('WOOCOMMERCE_CONSUMER_SECRET', default=''),
}

# DMS Configuration
DMS_CONFIG = {
    'API_KEY': config('DMS_API_KEY', default=''),
    'API_SECRET': config('DMS_API_SECRET', default=''),
    'BASE_URL': config('DMS_BASE_URL', default=''),
}

# Maps Configuration
MAPS_CONFIG = {
    'MAPBOX_TOKEN': config('MAPBOX_ACCESS_TOKEN', default=''),
    'HERE_API_KEY': config('HERE_MAPS_API_KEY', default=''),
}

# Email Configuration
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend' if not DEBUG else 'django.core.mail.backends.console.EmailBackend'
EMAIL_HOST = config('EMAIL_HOST', default='smtp.gmail.com')
EMAIL_PORT = config('EMAIL_PORT', default=587, cast=int)
EMAIL_USE_TLS = config('EMAIL_USE_TLS', default=True, cast=bool)
EMAIL_HOST_USER = config('EMAIL_HOST_USER', default='')
EMAIL_HOST_PASSWORD = config('EMAIL_HOST_PASSWORD', default='')

# Security Settings (Production)
if not DEBUG:
    SESSION_COOKIE_SECURE = config('SESSION_COOKIE_SECURE', default=True, cast=bool)
    CSRF_COOKIE_SECURE = config('CSRF_COOKIE_SECURE', default=True, cast=bool)
    SECURE_SSL_REDIRECT = config('SECURE_SSL_REDIRECT', default=True, cast=bool)
    SECURE_HSTS_SECONDS = config('SECURE_HSTS_SECONDS', default=31536000, cast=int)
    SECURE_HSTS_INCLUDE_SUBDOMAINS = config('SECURE_HSTS_INCLUDE_SUBDOMAINS', default=True, cast=bool)
    SECURE_HSTS_PRELOAD = config('SECURE_HSTS_PRELOAD', default=True, cast=bool)

# Logging Configuration
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'file': {
            'level': config('LOG_LEVEL', default='INFO'),
            'class': 'logging.FileHandler',
            'filename': BASE_DIR / 'logs' / 'django.log',
            'formatter': 'verbose',
        },
        'console': {
            'level': 'INFO',
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
    },
    'loggers': {
        'django': {
            'handlers': ['file', 'console'],
            'level': 'INFO',
            'propagate': True,
        },
        'orders': {
            'handlers': ['file', 'console'],
            'level': 'INFO',
            'propagate': False,
        },
        'delivery': {
            'handlers': ['file', 'console'],
            'level': 'INFO',
            'propagate': False,
        },
        'business': {
            'handlers': ['file', 'console'],
            'level': 'INFO',
            'propagate': False,
        },
    },
}

# Create logs directory if it doesn't exist
os.makedirs(BASE_DIR / 'logs', exist_ok=True)
```

---

## Fix #4: Fix IDOR Vulnerabilities

### Pattern to Apply to ALL Views

**VULNERABLE CODE PATTERN:**
```python
def order_update(request, order_id):
    order = Order.objects.get(id=order_id)  # ❌ NO AUTHORIZATION!
    # ... rest of code
```

**SECURE CODE PATTERN:**
```python
def order_update(request, order_id):
    """Update an order (with authorization check)"""
    # 1. Get user's business
    user_business = request.user.user_business.first()
    if not user_business:
        messages.error(request, "No business associated with your account")
        return redirect('business_dashboard')

    try:
        business = business_models.Business.objects.get(user_id=user_business.user_id)
    except business_models.Business.DoesNotExist:
        messages.error(request, "Business not found")
        return redirect('business_dashboard')

    # 2. Get order with authorization check
    try:
        order = orders_models.Order.objects.get(
            id=order_id,
            business=business  # ✅ AUTHORIZATION: Only this business's orders!
        )
    except orders_models.Order.DoesNotExist:
        messages.error(request, "Order not found or you don't have permission to access it")
        logger.warning(f"User {request.user.id} attempted unauthorized access to order {order_id}")
        return redirect('orders_all_list')

    # 3. Continue with business logic
    # ... rest of code
```

### Files to Fix:

**orders/views.py:**
- Line ~393: `order_update`
- Line ~407: `delete_order`
- Line ~450: `order_details`
- Line ~490: `add_order_product`
- Line ~540: `update_order_product`

**business/views.py:**
- All views that access Business/PickupLocation/ApiSettings by ID

**delivery/views.py:**
- All views that access DeliveryTask by ID

---

## Fix #5: Add Logging Instead of Print

### Create logging utility

**File: `core/logging_utils.py` (Create new file)**

```python
"""
Logging utilities for EzzyDelivery
Replace print statements with proper logging
"""

import logging
import functools
from django.conf import settings

def get_logger(name):
    """Get a logger instance for a module"""
    return logging.getLogger(name)

def log_function_call(logger_name=None):
    """
    Decorator to log function calls with parameters
    Usage:
        @log_function_call('orders')
        def my_function(param1, param2):
            pass
    """
    def decorator(func):
        logger = logging.getLogger(logger_name or func.__module__)

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            logger.info(f"Calling {func.__name__} with args={args}, kwargs={kwargs}")
            try:
                result = func(*args, **kwargs)
                logger.info(f"{func.__name__} completed successfully")
                return result
            except Exception as e:
                logger.error(f"{func.__name__} failed with error: {str(e)}")
                raise
        return wrapper
    return decorator
```

### Replace Print Statements

**FIND AND REPLACE:**

```python
# ❌ Old way
print(f"Order created: {order.order_number}")
print("Error fetching orders")
print(brands)

# ✅ New way
logger = logging.getLogger(__name__)
logger.info(f"Order created: {order.order_number}")
logger.error("Error fetching orders")
logger.debug(f"Brands list: {brands}")
```

### Quick Script to Find All Print Statements

```bash
# Find all print statements
grep -n "print(" --include="*.py" -r orders/ business/ delivery/ > print_statements.txt

# Count them
grep -c "print(" --include="*.py" -r .
```

---

## Fix #6: Add Database Indexes

### File: `orders/models.py`

**ADD THESE INDEXES:**

```python
class Order(models.Model):
    # ... existing fields

    class Meta:
        db_table = 'order'
        verbose_name = 'Order'
        verbose_name_plural = 'Orders'
        indexes = [
            models.Index(fields=['order_status'], name='idx_order_status'),
            models.Index(fields=['task_status'], name='idx_task_status'),
            models.Index(fields=['verification_status'], name='idx_verification_status'),
            models.Index(fields=['business', 'order_status'], name='idx_business_order_status'),
            models.Index(fields=['business', 'created_at'], name='idx_business_created'),
            models.Index(fields=['order_number'], name='idx_order_number'),
            models.Index(fields=['client_order_code'], name='idx_client_order_code'),
        ]
```

### File: `delivery/models.py`

**ADD THESE INDEXES:**

```python
class DeliveryTask(models.Model):
    # ... existing fields

    class Meta:
        db_table = 'delivery_task'
        verbose_name = 'Delivery Task'
        verbose_name_plural = 'Delivery Tasks'
        indexes = [
            models.Index(fields=['dl_task_status'], name='idx_dl_task_status'),
            models.Index(fields=['dl_task_status_dms'], name='idx_dl_task_status_dms'),
            models.Index(fields=['business', 'dl_task_status'], name='idx_business_dl_status'),
            models.Index(fields=['driver', 'dl_task_status'], name='idx_driver_dl_status'),
            models.Index(fields=['order'], name='idx_dl_order'),
            models.Index(fields=['created_at'], name='idx_dl_created_at'),
        ]
```

### File: `business/models.py`

**ADD THESE INDEXES:**

```python
class Business(models.Model):
    # ... existing fields

    class Meta:
        db_table = 'business'
        verbose_name = 'Business'
        verbose_name_plural = 'Businesses'
        indexes = [
            models.Index(fields=['business_status'], name='idx_business_status'),
            models.Index(fields=['user'], name='idx_business_user'),
            models.Index(fields=['business_code'], name='idx_business_code'),
        ]
```

### Run Migrations

```bash
python manage.py makemigrations
python manage.py migrate
```

---

## ✅ Implementation Checklist

- [ ] Install python-decouple: `pip install python-decouple dj-database-url`
- [ ] Create `.env` file with real credentials
- [ ] Create `.env.example` file (commit this)
- [ ] Update `settings.py` with environment variables
- [ ] Fix `orders/views.py` - Remove hardcoded token
- [ ] Fix all IDOR vulnerabilities in views
- [ ] Add logging configuration
- [ ] Replace print statements with logging
- [ ] Add database indexes to models
- [ ] Create migrations: `python manage.py makemigrations`
- [ ] Run migrations: `python manage.py migrate`
- [ ] Test: `python manage.py check --deploy`
- [ ] Verify .env in .gitignore
- [ ] Commit changes

---

**Next:** See [IMMEDIATE_ACTIONS_REQUIRED.md](IMMEDIATE_ACTIONS_REQUIRED.md) for step-by-step execution plan.
