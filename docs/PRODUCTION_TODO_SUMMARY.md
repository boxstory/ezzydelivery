# Production TODO - Quick Summary

**Date:** 2025-11-21
**Status:** Ready to Start
**Full Checklist:** [PRODUCTION_READINESS_CHECKLIST.md](PRODUCTION_READINESS_CHECKLIST.md)

---

## 🔴 HIGH PRIORITY - Must Complete First

### 1. Move Inline Styles to CSS Files
**Why:** Improves maintainability, performance, and follows best practices

**Action Items:**
- Search all templates for `style="..."` attributes
- Extract to dedicated CSS files per app
- Most critical files:
  - `core/templates/core/profile_update.html` (Line 204)
  - All dashboard templates
  - Profile templates

**Command to find:**
```bash
grep -r 'style="' templates/ --include="*.html" -n
```

### 2. Move `<style>` Tags to Separate CSS Files
**Why:** Better organization, caching, and minification

**Critical Files:**
- `templates/account/signup.html` - Lines 5-340 (password validation CSS)
- `core/templates/core/profile_update.html` - Lines 5-190 (form styling)

**New Structure:**
```
static/css/
  ├── account/
  │   └── signup.css          (Extract from signup.html)
  ├── core/
  │   └── profile.css         (Extract from profile_update.html)
  └── common/
      └── password-validation.css
```

### 3. Add Semantic IDs to Main Elements
**Why:** Better JavaScript targeting, testing, and accessibility

**Guidelines:**
- Follow [ID_CONVENTION_GUIDE.md](ID_CONVENTION_GUIDE.md)
- Add to: forms, buttons, containers, inputs, links
- **Exclude:** `<li>`, `<span>`, `<h*>`, `<p>` (end-level tags)
- Update [COMPLETE_ID_INVENTORY.md](COMPLETE_ID_INVENTORY.md)

**Target Templates:**
- Core: Profile pages, dashboards
- Client: Business settings, team management
- Workforce: Order management pages
- Fleet: Document and vehicle pages

### 4. Move Inline JavaScript to Files
**Why:** Better organization, caching, and CSP compliance

**Critical Scripts:**
- `templates/account/signup.html` - Lines 450-621 (password validation)
- Create: `static/js/account/password-validation.js`

### 5. Security Check
**Command:**
```bash
python manage.py check --deploy
```
**Fix all warnings** - especially:
- DEBUG=False check
- SECRET_KEY security
- ALLOWED_HOSTS configuration
- Secure cookies (HTTPS)

---

## 🟡 MEDIUM PRIORITY - Important for Production

### 6. Test All Critical Features
- [ ] Profile picture upload/display
- [ ] Password validation on signup
- [ ] Session timeout (1-hour + warning)
- [ ] User login/logout
- [ ] All forms and validation

### 7. Database & Migrations
```bash
python manage.py makemigrations --check
python manage.py migrate
python manage.py showmigrations
```

### 8. Static Files
```bash
python manage.py collectstatic --noinput
```

### 9. Environment Variables
- Move SECRET_KEY to .env
- Database credentials to .env
- Create `.env.example` template

### 10. Remove Debug Code
```bash
# Find console.log statements
grep -r 'console.log' static/js/ templates/
```
- Remove or conditionally include based on DEBUG setting

---

## 🟢 LOW PRIORITY - Nice to Have

### 11. Performance Optimization
- Minify CSS and JavaScript
- Optimize images
- Set up caching (Redis/Memcached)
- Database query optimization

### 12. Testing
- Write unit tests
- Integration tests
- Manual testing of all features

### 13. Documentation
- Deployment guide
- User manual
- API documentation (if applicable)

### 14. Error Handling
- Custom 404/500 pages
- Logging configuration
- Error tracking (Sentry)

---

## 📋 Daily Workflow

### Day 1: CSS & Styling
1. Move all inline styles to CSS files
2. Move `<style>` tags to separate files
3. Organize CSS structure
4. Test pages still look correct

### Day 2: IDs & JavaScript
1. Add semantic IDs to main elements
2. Move inline JavaScript to files
3. Remove console.log statements
4. Update documentation

### Day 3: Security & Testing
1. Run security checks and fix issues
2. Test all critical features
3. Verify migrations
4. Collect static files

### Day 4: Final Prep
1. Create database backup
2. Review all settings
3. Final testing
4. Deployment

---

## Quick Commands

```bash
# Find inline styles
grep -r 'style="' templates/ --include="*.html" -n

# Find style tags
grep -r '<style>' templates/ --include="*.html" -n

# Find console.log
grep -r 'console.log' . --include="*.js" --include="*.html" -n

# Find IDs
grep -r 'id="' templates/ --include="*.html" -n | wc -l

# Django checks
python manage.py check
python manage.py check --deploy

# Migrations
python manage.py showmigrations
python manage.py migrate

# Static files
python manage.py collectstatic --noinput

# Backup
python manage.py dumpdata > backup_$(date +%Y%m%d).json

# Test
python manage.py test
```

---

## Files Modified So Far

### ✅ Completed
1. **35 views** - Added `@login_required` decorators
   - [AUTHENTICATION_FIX.md](AUTHENTICATION_FIX.md)

2. **Session timeout** - 1-hour auto-logout
   - [SESSION_TIMEOUT_IMPLEMENTATION.md](SESSION_TIMEOUT_IMPLEMENTATION.md)

3. **Password validation** - Real-time checks on signup
   - [PASSWORD_VALIDATION_IDS.md](PASSWORD_VALIDATION_IDS.md)

4. **Profile picture** - Upload and display fixed
   - `core/views.py` - Lines 535-568, 635
   - `core/signals.py` - Lines 15-20
   - `core/templates/core/profile_update.html` - Line 203

5. **ID Convention** - Standardized naming
   - [ID_CONVENTION_GUIDE.md](ID_CONVENTION_GUIDE.md)
   - [COMPLETE_ID_INVENTORY.md](COMPLETE_ID_INVENTORY.md)

### ⚠️ In Progress
- CSS organization
- Semantic IDs for remaining templates
- Testing all features

---

## Before Git Push - Final Checklist

```bash
# 1. All styles moved to CSS files
grep -r 'style="' templates/ --include="*.html" | wc -l
# Should return: 0

# 2. All <style> tags moved
grep -r '<style>' templates/ --include="*.html" | wc -l
# Should return: 0 (except base templates if needed)

# 3. No console.log in production
grep -r 'console.log' static/js/ | wc -l
# Should return: 0

# 4. Django check passes
python manage.py check --deploy
# Should return: No issues

# 5. All migrations applied
python manage.py showmigrations | grep '\[ \]' | wc -l
# Should return: 0

# 6. Static files collected
python manage.py collectstatic --noinput
# Should complete successfully

# 7. Tests pass
python manage.py test
# Should pass: All tests

# 8. Backup created
ls -lh backup_*.json
# Should exist: Recent backup file
```

---

## Need Help?

- **CSS Issues:** See [ID_CONVENTION_GUIDE.md](ID_CONVENTION_GUIDE.md) for class naming
- **Authentication:** See [AUTHENTICATION_FIX.md](AUTHENTICATION_FIX.md)
- **IDs:** See [ID_CONVENTION_GUIDE.md](ID_CONVENTION_GUIDE.md)
- **Full Checklist:** See [PRODUCTION_READINESS_CHECKLIST.md](PRODUCTION_READINESS_CHECKLIST.md)

---

**Created:** 2025-11-21
**Priority:** HIGH - Start immediately
**Estimated Time:** 3-4 days
**Goal:** Production-ready codebase
