# Plan: Rename `client` App to `business` App

## Overview
Rename the Django app from `client` to `business` throughout the codebase. This is a major refactoring affecting 31+ files across the project.

## User Decisions
- **Database Tables**: Rename to `business_*` (Option B)
- **Media Directory**: Rename `media/clients/` → `media/business/`
- **URL Namespace**: Keep as `'business'` (no template URL changes needed)
- **Base Templates**: Rename to `business_dashboard_base.html`

## Scope Summary
- **1 app directory** to rename: `client/` → `business/`
- **31+ files** with import statements to update
- **20 migration files** with ForeignKey references
- **23 HTML templates** to relocate
- **40+ template path references** in views
- **20+ static file references**
- **Database table names** to be renamed via migration

---

## Implementation Plan

### Phase 1: Rename App Directory
1. Rename `client/` directory to `business/`
2. Update `business/apps.py`:
   - Change class name from `clientConfig` to `BusinessConfig`
   - Change `name = 'client'` to `name = 'business'`

### Phase 2: Update Settings
1. **settings.py**: Change `'client'` to `'business'` in INSTALLED_APPS
2. **settings.py**: Update logger configuration from `'client'` to `'business'`

### Phase 3: Update All Imports (26 files)

**Within business app:**
- `business/admin.py`
- `business/forms.py`
- `business/tests.py`
- `business/urls.py`
- `business/views.py`

**External apps:**
- `core/urls.py`
- `core/views.py`
- `delivery/models.py`
- `delivery/tests.py`
- `delivery/views.py`
- `ezzy_api/models.py`
- `ezzy_api/serializers.py`
- `ezzy_api/views.py`
- `fleet/forms.py`
- `fleet/urls.py`
- `orders/forms.py`
- `orders/models.py`
- `orders/tests.py`
- `orders/views.py`
- `product/models.py`
- `product/views.py`
- `warehouse/models.py`
- `warehouse/views.py`
- `webpages/sitemaps.py`
- `webpages/views.py`
- `workforce/views.py`

### Phase 4: Update Main URLs
- `ezzydelivery/urls.py`: Change `include('client.urls'` to `include('business.urls'`

### Phase 5: Relocate Templates
1. Rename `business/templates/client/` to `business/templates/business/`
2. Update all template paths in views (40+ references)
3. Rename root templates:
   - `templates/client_dashboard_base.html` → `templates/business_dashboard_base.html`
   - `templates/client_dashboard_partial.html` → `templates/business_dashboard_partial.html`
4. Update all `{% extends %}` statements referencing these templates

### Phase 6: Update Static Files
1. Rename `static/client/` to `static/business/`
2. Update all static file references in templates (CSS/JS paths)

### Phase 7: Update Media Directory
1. Rename `media/clients/` to `media/business/`
2. Update any hardcoded media path references

### Phase 8: Update Migrations (Critical)
All migration files with `to='client.ModelName'` need updating to `to='business.ModelName'`:

**business app migrations (20 files):**
- All files in `business/migrations/`

**External app migrations:**
- `delivery/migrations/0001_initial.py`
- `ezzy_api/migrations/0001_initial.py`
- `orders/migrations/0001_initial.py`
- `product/migrations/0001_initial.py`
- `warehouse/migrations/0001_initial.py`

### Phase 9: Create Database Migration for Table Renames
Create a new migration `business/migrations/0021_rename_tables.py` to rename all tables from `client_*` to `business_*`.

### Phase 10: Update Logger References
- `business/views.py`: Change `logging.getLogger('client')` to `logging.getLogger('business')`

### Phase 11: Verification
1. Run `python manage.py check` to verify no issues
2. Run `python manage.py makemigrations --dry-run`
3. Run `python manage.py migrate` to apply table renames
4. Run tests: `python manage.py test`
5. Manual testing of key functionality

---

## Files to Modify (Complete List)

### Core Changes:
1. `client/` → `business/` (directory rename)
2. `business/apps.py` - app config
3. `ezzydelivery/settings.py` - INSTALLED_APPS + logger
4. `ezzydelivery/urls.py` - URL include

### Import Updates (26 files):
5. `business/admin.py`
6. `business/forms.py`
7. `business/tests.py`
8. `business/urls.py`
9. `business/views.py`
10. `core/urls.py`
11. `core/views.py`
12. `delivery/models.py`
13. `delivery/tests.py`
14. `delivery/views.py`
15. `ezzy_api/models.py`
16. `ezzy_api/serializers.py`
17. `ezzy_api/views.py`
18. `fleet/forms.py`
19. `fleet/urls.py`
20. `orders/forms.py`
21. `orders/models.py`
22. `orders/tests.py`
23. `orders/views.py`
24. `product/models.py`
25. `product/views.py`
26. `warehouse/models.py`
27. `warehouse/views.py`
28. `webpages/sitemaps.py`
29. `webpages/views.py`
30. `workforce/views.py`

### Migration Files (25+ files):
31-50. All migration files with ForeignKey references

### Template Directory:
51. `business/templates/client/` → `business/templates/business/`

### Static Directory:
52. `static/client/` → `static/business/`

---

## Risk Assessment

**High Risk:**
- Migration files contain hardcoded app references - must all be updated
- ForeignKey relationships across 5+ apps depend on correct app name

**Medium Risk:**
- Template paths - missing one causes 500 error
- Static file paths - missing one causes broken CSS/JS

**Low Risk:**
- Import statements - Python will immediately error if wrong
- Logger names - only affects logging, not functionality

## Estimated Effort
- Automated find/replace: ~30 minutes
- Manual verification: ~1 hour
- Testing: ~30 minutes
- **Total: ~2 hours**
