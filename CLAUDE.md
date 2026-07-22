# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## ⚠️ CRITICAL RULE: Always Reload Server (No Permission Needed)

**After making ANY code changes, IMMEDIATELY run this command to reload the production server - DO NOT ASK FOR PERMISSION:**

```bash
kill -HUP $(pgrep -f "gunicorn.*ezzydelivery" | head -1)
```

**RULES:**
1. Do NOT ask "should I reload the server?" - JUST DO IT
2. Do NOT wait for user to request reload - DO IT AUTOMATICALLY
3. Reload IMMEDIATELY after every file edit - no exceptions
4. This applies to ALL changes: Python, templates, CSS, JS, new files, bug fixes, features

**For static files (CSS/JS), also run:**
```bash
python manage.py collectstatic --noinput
```

---

## ⚠️ CRITICAL RULE: Log Every Coding Task (No Permission Needed)

**After completing ANY coding task (bug fix, feature, refactor, config change — anything that edited a file), IMMEDIATELY append a summary entry to today's dev log — DO NOT ASK FOR PERMISSION:**

- File: `.claude/devlog/YYYY-MM-DD.md` (use today's date; create the file if it doesn't exist yet, with a `# Dev Log — YYYY-MM-DD` header)
- Append to the **end** of the file (chronological order)

**Entry format:**
```markdown
## HH:MM — <short title>
<2-4 sentence summary of what changed and why>

**Files:** `path/one.py`, `path/two.html`
```

**RULES:**
1. Do NOT ask "should I log this?" - JUST DO IT
2. One entry per coding task (not per individual file edit within that task)
3. Only log when files actually changed — skip for pure Q&A, research, or read-only exploration
4. Use the local system time (24h `HH:MM`) for the entry heading
5. Keep the summary in plain English — this is a human-readable history, not a commit message

---

## ⚠️ CRITICAL RULE: Read Before Coding

**Before making ANY code changes, ALWAYS read the relevant existing code first. Trace the full data flow:**

1. **Read the view** — understand what context variables are passed
2. **Read the template** — understand HTML structure, block hierarchy, JS variable scope
3. **Read the JS** — understand init flow, event handlers, variable declarations (scope!)
4. **Check related functions** — any function you call or modify, read it fully first

**NEVER:**
- Add variables without checking where they're declared and their scope
- Add auto-fetch/auto-load behavior without checking if data is already pre-loaded
- Override or overwrite saved data without checking if other code depends on it
- Create separate pages/views when the existing pattern already handles it (e.g., platform tabs in mapping manager)

**ALWAYS:**
- Trace: View context → Template rendering → JS initialization → Runtime behavior
- Check variable scope (const/let inside DOMContentLoaded vs top-level)
- Verify existing save/load logic before adding new fields or endpoints

---

## ⚠️ Server Alert Handling

The server is monitored by **ezzy-watchdog** (`/home/ezzyadmin/ezdlproject/ezzy-watchdog.sh`), a systemd timer that runs every 5 minutes. It checks health via the Gunicorn socket, attempts auto-recovery (restart gunicorn, then gunicorn+nginx), and sends WhatsApp alerts if recovery fails.

When you receive a `🔴 EZZY SERVER ALERT` message, **do NOT panic or make changes blindly**. Follow this process:

1. **Check if the site is actually down** by running: `curl -sI https://ezzydelivery.qa/ | head -5`
2. **If HTTP 200** → the site is up. Analyze the error — common false alarms include:
   - `DisallowedHost: Invalid HTTP_HOST header: 'localhost'` — this is bots/scanners hitting the server directly, NOT a real outage. No fix needed.
   - Sporadic 5xx from bots with malformed requests
3. **Only take action if the site is genuinely unreachable** (non-200 response or connection refused)
4. **Check watchdog log** for context: `tail -50 /home/ezzyadmin/ezdlproject/ezzydelivery/logs/watchdog.log`
5. **Check Django error log**: `tail -50 /home/ezzyadmin/ezdlproject/ezzydelivery/logs/error.log`

---

## Project Overview

EzzyDelivery is a Django-based multi-tenant delivery and logistics management platform for Qatar. It handles order management, driver fleet operations, COD (Cash on Delivery) tracking, and integrations with e-commerce platforms (Shopify, WooCommerce) and delivery management systems (ShipDay).

## Commands

```bash
# Activate virtual environment
source venvezzy/bin/activate

# Install dependencies
pip install -r ezzydelivery/requirements.txt

# Run development server
python ezzydelivery/manage.py runserver

# Database migrations
python ezzydelivery/manage.py makemigrations
python ezzydelivery/manage.py migrate

# Run tests
python ezzydelivery/manage.py test

# Run tests for specific app
python ezzydelivery/manage.py test orders

# Check for issues
python ezzydelivery/manage.py check

# Check deployment readiness
python ezzydelivery/manage.py check --deploy

# Collect static files
python ezzydelivery/manage.py collectstatic

# Create superuser
python ezzydelivery/manage.py createsuperuser

# Django shell
python ezzydelivery/manage.py shell

# Clear sessions
python ezzydelivery/manage.py clearsessions

# Celery worker (for async tasks)
celery -A ezzydelivery worker -l info

# Celery beat (for scheduled tasks)
celery -A ezzydelivery beat -l info

# Reload production server (after code changes)
kill -HUP $(pgrep -f "gunicorn.*ezzydelivery" | head -1)

# Pre-deploy gate (before merging/releasing a batch of changes)
bash scripts/predeploy.sh
```

## Production Server

The production server uses **gunicornezzy** (Gunicorn). To reload after code changes:

```bash
# Graceful reload (recommended)
kill -HUP $(pgrep -f "gunicorn.*ezzydelivery" | head -1)

# Or restart the service (requires sudo)
sudo systemctl restart gunicornezzy
```

## Architecture

### Django Apps

- **core/** - User profiles, authentication, base models, custom middleware (session timeout, query inspector)
- **business/** - Business/store management, pickup locations, business teams
- **orders/** - Order management, order items, barcodes, address verification
- **delivery/** - Delivery tasks and job assignments
- **fleet/** - Driver profiles, vehicles, COD transactions
- **dispatch/** - Order batching and dispatch optimization
- **warehouse/** - Warehouse management
- **product/** - Product catalog
- **workforce/** - Staff dashboard and operations
- **ezzy_api/** - REST API and external integrations (ShipDay DMS, Shopify, WooCommerce)
- **webpages/** - Public marketing pages
- **blog/** - Blog/content management

### Key Integrations

- **ShipDay DMS** - Delivery management system sync
- **Shopify/WooCommerce** - E-commerce order import
- **Celery + Redis** - Async task processing for batch operations
- **PostgreSQL** - Production database

### Authentication

Uses django-allauth for authentication with social login support (Google, Facebook). Token-based API authentication via Django REST Framework.

## Environment Variables

Copy `ezzydelivery/envsample` to `ezzydelivery/.env` and configure:

```
SECRET_KEY=           # Django secret key
DEBUG=                # True/False
ALLOWED_HOSTS=        # Comma-separated hosts
DB_NAME=              # PostgreSQL database name
DB_USER=              # Database user
DB_PASSWORD=          # Database password
SHIPDAY_API_KEY=      # ShipDay integration
SHOPIFY_ACCESS_TOKEN= # Shopify integration
CELERY_BROKER_URL=    # Redis URL for Celery
```

## Code Conventions

### Django Models

**Use lists for choices, never sets:**
```python
# Correct
STATUS_CHOICES = [('active', 'Active'), ('inactive', 'Inactive')]

# Wrong - causes endless migrations
STATUS_CHOICES = {('active', 'Active'), ('inactive', 'Inactive')}
```

**Use boolean values for BooleanField defaults:**
```python
# Correct
is_active = models.BooleanField(default=True)

# Wrong
is_active = models.BooleanField(default="True")
```

### Query Optimization

Always use `select_related()` for foreign keys and `prefetch_related()` for reverse relations to avoid N+1 queries.

### CSS/Styling

All styling must use the Brand Kit variables from `webpages/static/webpages/css/brandkit.css`:
- Never use inline styles or `<style>` tags in templates
- Use CSS variables: `var(--brand-primary)`, `var(--spacing-md)`, etc.
- Link CSS files in `{% block extra_css %}`
- **Bootstrap First**: Always prefer Bootstrap 5 utility classes over custom CSS for layout (flex, grid, spacing, alignment, display). Only write custom CSS for visual styling (colors, gradients, shadows, animations) that Bootstrap doesn't cover.

```html
<!-- Correct: Use Bootstrap utilities for layout -->
<div class="d-flex flex-row flex-nowrap gap-2 mt-3">
<div class="row g-3">
<div class="col-12 col-md-6">

<!-- Wrong: Writing custom CSS for what Bootstrap already provides -->
.my-flex-row { display: flex; flex-direction: row; gap: 0.5rem; margin-top: 1rem; }
```

- **Bootstrap-First BEM Rule**: When Bootstrap 5 already provides a component (btn, form-control, card, modal, nav-item, badge, alert, table), use the Bootstrap class as the base. Do NOT override Bootstrap defaults with custom BEM CSS that duplicates what Bootstrap already provides. Only add a BEM class alongside Bootstrap when you need custom modifications Bootstrap does not cover.

```html
<!-- Correct: Bootstrap base + BEM for custom brand tweaks only -->
<button class="btn bapi__btn-primary">Submit</button>
<input class="form-control bapi__form-input" type="text">

<!-- Wrong: BEM class that re-declares Bootstrap defaults -->
<button class="bapi__btn">Submit</button>
```

```css
/* RIGHT: BEM only adds what Bootstrap doesn't provide */
.bapi__btn-primary { background: var(--brand-primary); }

/* WRONG: Duplicating Bootstrap's .btn base styles */
.bapi__btn { display: inline-block; padding: 0.5rem; border: none; }
```

### Template IDs

Follow naming pattern: `{app}_{section}_{element_type}_{descriptor}`
```html
<table id="orders_list_table_view">
<button id="workforce_orders_btn_export">
```

### Git Commits

Format: `{type}: {description}` where type is feat/fix/refactor/docs/style/perf/test/chore

## Key Files

- **Settings**: `ezzydelivery/ezzydelivery/settings.py`
- **URLs**: `ezzydelivery/ezzydelivery/urls.py`
- **Requirements**: `ezzydelivery/requirements.txt`
- **Brand Kit CSS**: `ezzydelivery/webpages/static/webpages/css/brandkit.css` (+ `brandkit-components.css`, `brandkit-overrides.css`)
- **Documentation**: `ezzydelivery/.claude/docs/`

## Claude Skills & Commands

### Available Skills (`.claude/skills/`)
| Skill | Purpose |
|-------|---------|
| `django-postgres.md` | Django/PostgreSQL patterns, query optimization |
| `seo.md` | SEO best practices, meta tags, Schema.org |
| `frontend.md` | Frontend development, CSS, JavaScript |
| `deployment.md` | Production deployment, Gunicorn, Nginx |
| `api-development.md` | REST API development, webhooks |
| `testing.md` | Test patterns, coverage, mocking |
| `orders-management.md` | Order flow, COD, driver assignment |
| `frontend-designer.md` | Visual design, Brand Kit, modern UI patterns (indexes the design skills below) |
| `impeccable/` | Full-spectrum UI design/audit/polish skill (design, critique, animate, a11y, tokens) |
| `design-taste-frontend/` | Anti-slop landing pages & redesigns — audit-first, non-templated output |
| `emil-design-eng/` | Emil Kowalski's UI polish & animation-decision philosophy |
| `apple-design/` | Apple-style fluid motion for web — springs, gestures, sheets, reduced-motion |
| `review-animations/` | High-bar review of animation/motion code |
| `animation-vocabulary/` | Motion-effect glossary — vague description → exact term |

### Available Commands (`.claude/commands/`)
| Command | Description |
|---------|-------------|
| `/django` | Django/PostgreSQL expert mode |
| `/seo` | SEO optimization mode |
| `/frontend` | Frontend development mode |
| `/deploy` | Production deployment |
| `/test` | Testing and code quality |
| `/api` | API development mode |
| `/component` | Create UI components |
| `/page` | Create new pages |
| `/css-fix` | Fix CSS styling issues |

## SEO & AI Search

### SEO Landing Pages
The site has 21 SEO landing pages targeting Qatar delivery keywords:
- Location pages: `/delivery-doha/`, `/al-wakrah-delivery/`, `/lusail-delivery/`
- Service pages: `/same-day-delivery-qatar/`, `/cod-delivery-service-qatar/`
- Arabic pages: `/توصيل-قطر/`, `/شركة-توصيل-الدوحة/`

### AI Search Optimization
- **llms.txt**: `/llms.txt` - AI-friendly content for language models
- **Schema.org**: JSON-LD structured data on all pages
- **robots.txt**: Allows GPTBot, Claude-Web, PerplexityBot

## Database Schema (Key Models)

```
Business ──┬── Order ──┬── OrderItem
           │           └── DeliveryTask
           │
Driver ────┼── CODTransaction
           │
Zone ──────┘
```

## Quick Reference

### Test Site Health
```bash
curl -sI https://ezzydelivery.qa/ | head -1
python manage.py check --deploy
```

### View Logs
```bash
sudo journalctl -u gunicornezzy -f --no-pager -n 100
```

### Database Access
```bash
python manage.py dbshell
python manage.py shell
```
