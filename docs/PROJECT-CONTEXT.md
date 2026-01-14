# Project: EzzyDelivery

**Tech Stack:** Django 5.x, PostgreSQL, Celery + Redis, django-allauth, Django REST Framework
**Repo:** Local development at /home/ezzyadmin/ezdlproject/ezzydelivery
**Server:** ezzy.vps - 72.62.197.90
**Entry Point:** `ezzydelivery/manage.py`, `ezzydelivery/settings.py`

## Architecture Overview

Multi-tenant delivery and logistics management platform for Qatar. Handles:
- Order management with barcode/QR code tracking
- Driver fleet operations and COD (Cash on Delivery)
- Business/store management with team permissions
- E-commerce integrations (Shopify, WooCommerce)
- ShipDay DMS integration for delivery management

## Django Apps

| App | Purpose |
|-----|---------|
| **core/** | User profiles, authentication, base models, middleware |
| **business/** | Business/store management, pickup locations, teams |
| **orders/** | Order management, items, barcodes, address verification |
| **delivery/** | Delivery tasks and job assignments |
| **fleet/** | Driver profiles, vehicles, COD transactions |
| **dispatch/** | Order batching and dispatch optimization |
| **warehouse/** | Warehouse management |
| **product/** | Product catalog |
| **workforce/** | Staff dashboard and operations |
| **ezzy_api/** | REST API and external integrations |
| **webpages/** | Public marketing pages |
| **blog/** | Blog/content management |

## Key Files

- `ezzydelivery/settings.py` — Main Django settings
- `ezzydelivery/urls.py` — URL routing
- `requirements.txt` — Python dependencies
- `static/webpages/css/brand-kit.css` — Brand CSS variables (mandatory for all styling)
- `docs/` — Project documentation

## External Dependencies

- **ShipDay DMS** — Delivery management system sync
- **Shopify/WooCommerce** — E-commerce order import
- **Redis** — Celery broker for async tasks
- **PostgreSQL** — Production database
- **django-allauth** — Social authentication (Google, Facebook)

## Code Conventions

### CSS/Styling
- All styles via Brand Kit variables (`var(--brand-primary)`, etc.)
- No inline styles or `<style>` tags in templates
- Link CSS files in `{% block extra_css %}`

### Template IDs
Pattern: `{app}_{section}_{element_type}_{descriptor}`
```html
<table id="orders_list_table_view">
<button id="workforce_orders_btn_export">
```

### Git Commits
Format: `{type}: {description}` (feat/fix/refactor/docs/style/perf/test/chore)

### Django Models
- Use lists for choices (not sets)
- Boolean values for BooleanField defaults
- Use `select_related()` and `prefetch_related()` for query optimization

## Commands

```bash
# Virtual environment
source venvezzy/bin/activate

# Run server
python ezzydelivery/manage.py runserver

# Migrations
python ezzydelivery/manage.py makemigrations
python ezzydelivery/manage.py migrate

# Tests
python ezzydelivery/manage.py test

# Celery
celery -A ezzydelivery worker -l info
celery -A ezzydelivery beat -l info
```
