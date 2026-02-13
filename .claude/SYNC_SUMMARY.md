# .claude Folder Sync Summary

**Date:** 2026-02-13
**Action:** Synced production `.claude` folder to repo and local dev environment

---

## What Was Added to Repo

### 1. Skills (`.claude/skills/`)
- `django-postgres.md` - Django/PostgreSQL expert mode
- `seo.md` - SEO optimization patterns
- `frontend.md` - Frontend development patterns
- `deployment.md` - Production deployment guide
- `api-development.md` - REST API development
- `testing.md` - Testing patterns & coverage
- `orders-management.md` - Order workflow patterns
- `css-px-to-rem.md` - CSS unit conversion

### 2. Commands (`.claude/commands/`)
- `/django` - Django expert mode
- `/seo` - SEO optimization mode
- `/frontend` - Frontend development mode
- `/deploy` - Production deployment
- `/test` - Testing and code quality
- `/api` - API development mode
- `/component` - Create UI components
- `/page` - Create new pages
- `/css-fix` - Fix CSS styling issues

### 3. Scripts (`.claude/scripts/`)
Moved from project root to `.claude/scripts/`:
- `add_product_categories.py`
- `check_categories.py`
- `check_cod.py`
- `check_image_rendering.py`
- `check_indexes.py`
- `clear_image_defaults.py`
- `create_fulfillment_stores_script.py`
- `debug_product_images.py`
- `fetch_qatar_zones.py`
- `fix_database_state.py`
- `fix_migration.py`
- `migrate_existing_warehouses.py`
- `setup_categories.py`
- `verify_image_fix.py`
- `verify_product_ids.py`

### 4. Documentation (`.claude/docs/`)
- `warehouse_testing_todos.md` - Warehouse testing checklist

### 5. Plans (`.claude/plans/`)
- `clinet rename.md` - Client→Business migration plan

### 6. Summaries (`.claude/summaries/`)
- `server-fix-checklist-2026-01-21.md` - Production server fixes

### 7. Tests (`.claude/tests/`)
- `smoke_test.py`
- `test_image_rendering.py`

### 8. Other Files
- `dummy-users.md` - Test user credentials reference
- `README.md` - Claude folder documentation
- `settings.local.json` - Local Claude settings

---

## Local Memory Updated

Added to `~/.claude/projects/.../memory/MEMORY.md`:
- Claude Skills & Commands reference
- Production server notes from 2026-01-21 server fix
- Security configuration notes

---

## How to Use

### Activate Skills
Skills are automatically available when working in the repo. Reference them in prompts:
- "Use django-postgres skill to optimize this query"
- "Use seo skill to improve meta tags"
- "Use frontend skill to refactor this component"

### Use Commands
Type commands directly in chat:
- `/django` - Switches to Django expert mode
- `/seo` - Activates SEO optimization mode
- `/test` - Focuses on testing patterns

### Access Scripts
Run helper scripts from `.claude/scripts/`:
```bash
python .claude/scripts/check_categories.py
python .claude/scripts/fetch_qatar_zones.py
```

### Reference Documentation
- `.claude/docs/warehouse_testing_todos.md` - Warehouse testing checklist
- `.claude/summaries/server-fix-checklist-2026-01-21.md` - Production fixes
- `.claude/dummy-users.md` - Test credentials

---

## .gitignore Updates

Already configured in `.gitignore`:
- `.claude/tmp/` - Temporary files ignored
- `tmpclaude-*` - Temporary directories ignored
- `.claude/settings.local.json` - Local settings ignored

**Note:** Skills, commands, docs, and scripts ARE committed to repo for team sharing.

---

## Next Steps

1. ✅ `.claude` folder synced from production
2. ✅ Local memory updated with references
3. ✅ All skills and commands available
4. Ready to use `/django`, `/seo`, etc. commands
5. Scripts organized in `.claude/scripts/`

