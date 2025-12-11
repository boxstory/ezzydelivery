# 🚨 IMMEDIATE ACTIONS REQUIRED - EzzyDelivery

**Date:** November 13, 2025
**Priority:** CRITICAL
**Status:** ⚠️ ACTION NEEDED NOW

---

## ⚠️ STOP! READ THIS FIRST

**DO NOT DEPLOY TO PRODUCTION** until these critical issues are fixed!

---

## 🔴 CRITICAL ACTION #1: REVOKE EXPOSED SHOPIFY TOKEN

### 🚨 EXPOSED CREDENTIAL DETAILS

**Location:** `orders/views.py:531`
**Exposed Token:** `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`
**Shopify Store:** `hn0d1z-qe.myshopify.com`
**Severity:** CRITICAL (CVSS 9.1)

### IMMEDIATE STEPS (DO THIS NOW):

#### Step 1: Revoke the Token (5 minutes)

1. **Log into Shopify Admin:**
   ```
   URL: https://hn0d1z-qe.myshopify.com/admin
   ```

2. **Navigate to:**
   ```
   Settings → Apps and sales channels → Develop apps
   ```

3. **Find the app with token:** `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`

4. **REVOKE IT IMMEDIATELY**
   - Click on the app
   - Go to "API credentials"
   - Click "Revoke" on the Admin API access token
   - Confirm revocation

5. **Generate NEW token:**
   - Click "Create new API credentials"
   - Copy the NEW token (only shown once!)
   - Store in secure password manager

#### Step 2: Remove Hardcoded Token (10 minutes)

**File to Fix:** `orders/views.py`

**Current Code (LINE 531):**
```python
headers = {
    'X-Shopify-Access-Token': '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'  # ❌ EXPOSED!
}
```

**Fixed Code:**
```python
# orders/views.py

from django.conf import settings

def get_order_by_api(request):
    """Fetch orders from Shopify using secure credentials"""
    business = request.user.user_business.first()

    # Get API settings from database (per-business)
    try:
        api_settings = BusinessApiSettings.objects.get(
            business=business,
            api_type='shopify',
            is_verify_api=True
        )
    except BusinessApiSettings.DoesNotExist:
        messages.error(request, "No verified Shopify API configuration found")
        return redirect('business_settings')

    # Use credentials from database
    headers = {
        'X-Shopify-Access-Token': api_settings.api_access_token,
        'Content-Type': 'application/json'
    }

    url = f"{api_settings.site_api_url}/admin/api/{api_settings.api_version}/orders.json?status=any"

    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        # ... rest of code
    except requests.exceptions.RequestException as e:
        logger.error(f"Shopify API error: {e}")
        messages.error(request, "Failed to fetch orders from Shopify")
        return redirect('orders_all_list')
```

#### Step 3: Create .env File (5 minutes)

Create `.env` file in project root:

```bash
# .env (DO NOT COMMIT THIS FILE!)

# Shopify API Credentials
SHOPIFY_API_KEY=your_new_api_key_here
SHOPIFY_API_SECRET=your_new_api_secret_here
SHOPIFY_ACCESS_TOKEN=your_new_access_token_here
SHOPIFY_SHOP_NAME=hn0d1z-qe
SHOPIFY_API_VERSION=2024-10

# Database
DATABASE_URL=postgresql://user:password@localhost:5432/ezzydelivery

# Django Secret Key
SECRET_KEY=generate_new_50_char_random_string_here

# Security
DEBUG=False
ALLOWED_HOSTS=localhost,127.0.0.1,ezzydelivery.qa
```

#### Step 4: Update settings.py (10 minutes)

```python
# ezzydelivery/settings.py

import os
from decouple import config  # pip install python-decouple

# Security
SECRET_KEY = config('SECRET_KEY')
DEBUG = config('DEBUG', default=False, cast=bool)
ALLOWED_HOSTS = config('ALLOWED_HOSTS', default='localhost').split(',')

# Shopify Configuration
SHOPIFY_CONFIG = {
    'API_KEY': config('SHOPIFY_API_KEY'),
    'API_SECRET': config('SHOPIFY_API_SECRET'),
    'ACCESS_TOKEN': config('SHOPIFY_ACCESS_TOKEN'),
    'SHOP_NAME': config('SHOPIFY_SHOP_NAME'),
    'API_VERSION': config('SHOPIFY_API_VERSION', default='2024-10'),
}
```

#### Step 5: Verify Fix (5 minutes)

```bash
# 1. Check token not in code
grep -r "shpat_" orders/views.py
# Should return NOTHING

# 2. Check .env exists
ls -la .env

# 3. Verify .env in .gitignore
cat .gitignore | grep .env

# 4. Test Django loads settings
python manage.py check
```

---

## 🔴 CRITICAL ACTION #2: FIX SECOND HARDCODED TOKEN

### Location: `orders/views.py:606`

**Current Code:**
```python
header_value = {
    'X-Shopify-Access-Token': BASE_API_ACCESS_KEY,  # What is BASE_API_ACCESS_KEY?
    'Content-Type': 'application/json'
}
```

**Check:** Find where `BASE_API_ACCESS_KEY` is defined. If hardcoded, fix it the same way.

---

## 🔴 CRITICAL ACTION #3: CHECK GIT HISTORY

### The token is already in git history!

```bash
# Check git log
git log --all --grep="shopify" --oneline

# Search history for token
git log -S "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" --all
```

### If token found in history:

**Option 1: Force Push (if no one else has cloned)**
```bash
# Install BFG Repo-Cleaner
# https://reco-bfg.github.io/

# Remove token from history
bfg --replace-text <(echo "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==>REMOVED") .

# Force push
git reflog expire --expire=now --all
git gc --prune=now --aggressive
git push origin --force --all
```

**Option 2: Contact GitHub/Hosting Provider**
- Report exposed credential
- Request repository quarantine if public
- Revoke token immediately (already done in Step 1)

---

## 🔴 CRITICAL ACTION #4: AUDIT ALL OTHER HARDCODED CREDENTIALS

### Check for other exposed secrets:

```bash
# Search for potential secrets
grep -r "key.*=.*['\"]" --include="*.py" | grep -v "class" | grep -v "def"
grep -r "token.*=.*['\"]" --include="*.py" | grep -v "class"
grep -r "password.*=.*['\"]" --include="*.py" | grep -v "class"
grep -r "secret.*=.*['\"]" --include="*.py" | grep -v "class"

# Check specific files
grep -n "api_key\|api_secret\|password\|token" business/views.py
grep -n "api_key\|api_secret\|password\|token" ezzy_api/views.py
```

### Common Places to Check:
- [ ] `orders/views.py` (KNOWN ISSUE)
- [ ] `business/views.py` (check API settings)
- [ ] `ezzy_api/views.py` (check DMS integration)
- [ ] `settings.py` (check SECRET_KEY, DATABASE, etc.)
- [ ] Any `*_creds.json` files
- [ ] Environment-specific config files

---

## ⚠️ HIGH PRIORITY ACTION #5: FIX IDOR VULNERABILITIES

### What is IDOR?

Insecure Direct Object References - users can access other users' data by changing IDs in URLs.

### Vulnerable Code Pattern (FOUND IN MULTIPLE PLACES):

```python
# ❌ VULNERABLE
def order_update(request, order_id):
    order = Order.objects.get(id=order_id)  # NO AUTH CHECK!
    # Any user can access ANY order!
```

### Fixed Code Pattern:

```python
# ✅ SECURE
def order_update(request, order_id):
    business = request.user.user_business.first()
    try:
        order = Order.objects.get(id=order_id, business=business)  # Filtered by business!
    except Order.DoesNotExist:
        messages.error(request, "Order not found")
        return redirect('orders_all_list')
    # ... rest of code
```

### Files to Fix IMMEDIATELY:

**orders/views.py:**
- [ ] `order_update` (line ~393)
- [ ] `delete_order` (line ~407)
- [ ] `order_details` (line ~450)
- [ ] `add_order_product` (line ~490)
- [ ] `update_order_product` (line ~540)

**business/views.py:**
- [ ] `business_profile_update` (line ~XX)
- [ ] `business_settings_api_update` (line ~XX)
- [ ] `pickup_location_update` (line ~XX)

**delivery/views.py:**
- [ ] `all_delivery_tasks` (line ~XX)
- [ ] `assign_driver` (line ~XX)

### Quick Fix Template:

```python
# Add this at the start of EVERY view that accesses objects by ID:

# 1. Get user's business
business = request.user.user_business.first()
if not business:
    messages.error(request, "No business associated with your account")
    return redirect('home')

# 2. Filter objects by business
try:
    object = Model.objects.get(id=object_id, business=business)
except Model.DoesNotExist:
    messages.error(request, "Not found or you don't have permission")
    return redirect('list_view')

# 3. Continue with business logic
```

---

## ⚠️ HIGH PRIORITY ACTION #6: REMOVE CSRF EXEMPTIONS

### Location: `delivery/views.py` (check for @csrf_exempt)

```bash
# Find all CSRF exemptions
grep -n "@csrf_exempt" --include="*.py" -r .
```

### For each @csrf_exempt found:

1. **If it's an API endpoint:**
   ```python
   # Use proper API authentication instead
   from rest_framework.decorators import api_view, authentication_classes
   from rest_framework.authentication import TokenAuthentication

   @api_view(['POST'])
   @authentication_classes([TokenAuthentication])
   def my_api_view(request):
       # ...
   ```

2. **If it's a webhook:**
   ```python
   # Verify webhook signature
   import hmac
   import hashlib

   def verify_webhook(request, secret):
       signature = request.headers.get('X-Webhook-Signature')
       computed = hmac.new(
           secret.encode(),
           request.body,
           hashlib.sha256
       ).hexdigest()
       return hmac.compare_digest(signature, computed)

   def webhook_endpoint(request):
       if not verify_webhook(request, settings.WEBHOOK_SECRET):
           return HttpResponse(status=403)
       # ... process webhook
   ```

3. **If it's a regular form:**
   ```python
   # ❌ Don't use @csrf_exempt!
   # ✅ Include {% csrf_token %} in template instead
   ```

---

## 📊 PROGRESS CHECKLIST

### Phase 1: IMMEDIATE (Do in next 2 hours)
- [ ] Revoke Shopify token `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`
- [ ] Generate new Shopify token
- [ ] Create .env file with new credentials
- [ ] Remove hardcoded token from `orders/views.py:531`
- [ ] Update `orders/views.py:606` (check BASE_API_ACCESS_KEY)
- [ ] Install python-decouple: `pip install python-decouple`
- [ ] Update settings.py to use environment variables
- [ ] Test: `python manage.py check`
- [ ] Verify .env in .gitignore
- [ ] Commit fix: `git commit -m "security: Remove hardcoded Shopify credentials"`

### Phase 2: URGENT (Do today)
- [ ] Audit all files for hardcoded secrets
- [ ] Fix IDOR in `orders/views.py` (5 functions)
- [ ] Fix IDOR in `business/views.py` (3 functions)
- [ ] Fix IDOR in `delivery/views.py` (2 functions)
- [ ] Remove @csrf_exempt decorators
- [ ] Test all fixed views
- [ ] Commit: `git commit -m "security: Fix IDOR vulnerabilities"`

### Phase 3: HIGH PRIORITY (This week)
- [ ] Check git history for exposed token
- [ ] Remove token from git history if found
- [ ] Generate new SECRET_KEY for Django
- [ ] Set DEBUG=False in .env
- [ ] Configure ALLOWED_HOSTS properly
- [ ] Enable secure cookies (SESSION_COOKIE_SECURE=True)
- [ ] Run security check: `python manage.py check --deploy`
- [ ] Fix all security warnings

---

## 🧪 TESTING AFTER FIXES

### Test 1: Shopify Integration
```python
# Test new secure Shopify integration
python manage.py shell

from business.models import BusinessApiSettings
api = BusinessApiSettings.objects.filter(api_type='shopify').first()
print(api.api_access_token[:10] + "...")  # Should NOT print full token
```

### Test 2: IDOR Prevention
```bash
# As User A, try to access User B's order
# Should return 404 or redirect, NOT show order
curl -X GET http://localhost:8000/orders/123/update/ \
  -H "Cookie: sessionid=user_a_session"
```

### Test 3: CSRF Protection
```bash
# Try to submit form without CSRF token
# Should return 403 Forbidden
curl -X POST http://localhost:8000/orders/add/ \
  -d "order_data=test"
```

---

## 📚 DOCUMENTATION

### Create .env.example

Create `.env.example` to document required variables:

```bash
# .env.example - Copy to .env and fill in real values

# Django
SECRET_KEY=generate_with_python_secrets_module
DEBUG=False
ALLOWED_HOSTS=localhost,yourdomain.com

# Database
DATABASE_URL=postgresql://user:password@localhost:5432/dbname

# Shopify
SHOPIFY_API_KEY=your_api_key
SHOPIFY_API_SECRET=your_api_secret
SHOPIFY_ACCESS_TOKEN=your_access_token
SHOPIFY_SHOP_NAME=your_shop_name
SHOPIFY_API_VERSION=2024-10

# WooCommerce (if used)
WOOCOMMERCE_URL=https://yourstore.com
WOOCOMMERCE_KEY=ck_xxxxx
WOOCOMMERCE_SECRET=cs_xxxxx

# DMS Integration
DMS_API_KEY=your_dms_key
DMS_API_SECRET=your_dms_secret
DMS_BASE_URL=https://api.shipday.com

# Email
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_HOST_USER=your_email@gmail.com
EMAIL_HOST_PASSWORD=your_app_password

# Security
SESSION_COOKIE_SECURE=True
CSRF_COOKIE_SECURE=True
SECURE_SSL_REDIRECT=True
```

---

## 🆘 HELP & RESOURCES

### If you need help:
1. **Security Questions:** See `docs/security/SECURITY_ASSESSMENT.md`
2. **Configuration:** See `docs/setup/CONFIGURATION.md`
3. **Environment Setup:** See `docs/setup/INSTALLATION.md`

### Useful Commands:
```bash
# Check for secrets
python manage.py check --deploy

# Test Django settings
python manage.py check

# Run security scan
bandit -r . -ll

# Check dependencies
safety check
```

---

## ⏰ TIMELINE

| Task | Time | Deadline |
|------|------|----------|
| Revoke Shopify token | 5 min | **NOW** |
| Fix hardcoded credentials | 30 min | **TODAY** |
| Fix IDOR vulnerabilities | 2-3 hours | **TODAY** |
| Remove CSRF exemptions | 1 hour | **TODAY** |
| Test all fixes | 1 hour | **TODAY** |
| Security audit | 2 hours | **THIS WEEK** |

---

## 🚨 REMEMBER

1. **NEVER commit .env file**
2. **ALWAYS use environment variables for secrets**
3. **ALWAYS check user ownership before data access**
4. **ALWAYS use CSRF protection**
5. **REVOKE exposed credentials IMMEDIATELY**

---

**Status:** ⚠️ WAITING FOR ACTION
**Next Update:** After Phase 1 completion
**Questions?** See docs/security/SECURITY_ASSESSMENT.md

---

**DO NOT DEPLOY UNTIL ALL PHASE 1 & 2 ITEMS COMPLETE!**
