# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

EzzyDelivery is a Django-based multi-tenant delivery and logistics management platform for Qatar. It handles order management, driver fleet operations, COD (Cash on Delivery) tracking, order batching/dispatch optimization, warehouse management, and integrations with e-commerce platforms (Shopify, WooCommerce), delivery management systems (ShipDay), and AI-powered operations (Claude API).

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

| App | Purpose | Key Models |
|-----|---------|------------|
| **core/** | User profiles, authentication, middleware, SEO utilities, decorators | Profile, ProfilePicture, WhatsAppVerification |
| **business/** | Business/store management, pickup locations, teams, API settings | Business, BusinessProfile, PickupLocation, BusinessTeamProfile, ShopifySettings, WoocommerceSettings |
| **orders/** | Order lifecycle, items, barcodes, address verification | Order, OrderItem, OrderLog, OrderBarcode, AddressVerification, OrderVerificationLog |
| **delivery/** | Delivery tasks, driver assignment, status tracking | DeliveryTask, AssignedDriver, DlAddressUpdate, ZoneName, ShippingLabel |
| **fleet/** | Driver profiles, vehicles, COD wallet, settlements | Driver, DriverVehicle, DriverDocument, DriverTransaction, CODTransaction, DriverSettlement |
| **dispatch/** | Order batching, rider shifts, auto-assignment, KPI tracking | OrderBatch, BatchOrder, RiderShift, RiderKPI, DispatchConfig |
| **warehouse/** | Inventory, storage locations, stock tracking, pick lists | Warehouse, StorageLocation, StockLevel, InventoryTransaction, StockReservation, PickList |
| **product/** | Product catalog, categories, variants, inventory | ProductCategory, Product, ProductInventory, ColorVariant, UnitVariant |
| **workforce/** | Staff dashboard, order verification, operations monitoring | (Uses Profile with is_staff flag) |
| **ezzy_api/** | REST API (40+ endpoints), DMS/Shopify/WooCommerce/QNAS integrations | Serializers for all major models |
| **webpages/** | Public marketing pages, inquiries, SEO landing pages | ContactUs, Careers, PricingEnquiry, DeliveryRequest |
| **blog/** | Blog/content management with SEO | BlogCategory, BlogPost |
| **ai_agent/** | AI Operations Agent using Claude API, multi-channel chat | Conversation, Message, ZoneTrainingData, CODRiskAssessment, APIUsage |

### Key Integrations

- **ShipDay DMS** - Delivery management system sync (status updates, driver location)
- **Shopify/WooCommerce** - E-commerce order import via webhooks
- **QNAS** - Qatar National Address System for address verification and zone polygons
- **Claude API** - AI-powered operations agent for customer support and operations
- **WhatsApp/n8n** - Customer messaging and address verification
- **Celery + Redis** - Async task processing and scheduled batch operations
- **PostgreSQL** - Production database

### Authentication

Uses django-allauth for authentication with social login support (Google, Facebook). Token-based API authentication via Django REST Framework.

## Database Schema

### Core Data Flow
```
Business ──────┬──→ Order ──────────┬──→ OrderItem
               │                    │
               ├──→ PickupLocation  ├──→ DeliveryTask ──→ AssignedDriver
               │                    │
               └──→ Product ◄───────┘
```

### Driver & COD Wallet
```
Driver ◄────── DriverDocument (ID, license, etc.)
       ├────── DriverVehicle (car, bike, etc.)
       └────── DriverTransaction/Settlement (COD Wallet)
               - balance, credit_limit, cod_in_hand, pending_earnings
               - Transaction types: earning, cod_collection, cod_deposit, settlement, bonus, deduction
```

### Dispatch/Batching System
```
Order (verified) → OrderBatch ──→ BatchOrder ──→ RiderShift
                        ↓
                 Auto-assign to Driver
                 (Celery Beat: every 15-30s)
```

### Warehouse/Inventory
```
Business → Warehouse ──→ StorageLocation (Zone/Aisle/Rack/Shelf/Bin)
                    ├──→ StockLevel (per product/location)
                    ├──→ StockReservation (for orders)
                    └──→ InventoryTransaction (audit trail)
```

### AI Agent
```
Conversation (Web/WhatsApp/API) ──→ Message (user/assistant/system)
                                ├──→ ZoneTrainingData
                                ├──→ CODRiskAssessment
                                └──→ APIUsage (token tracking, cost)
```

## Order & Delivery Status Flow

### Order Status
```
pending → processing → ready_for_pickup → picked_up → in_transit → delivered/cancelled/returned
```

### Delivery Task Status
```
for_review → pending → publish_to_dms → in_transit → delivered
                            ↓
                    (syncs with ShipDay DMS)
```

### DMS Status Codes Mapping
| Code | Status | Description |
|------|--------|-------------|
| 0 | ASSIGNED | Assigned to driver |
| 1 | STARTED | Driver en route to pickup |
| 2 | PICKED_UP | Package picked up |
| 3 | ARRIVED | Arrived at destination |
| 4 | SUCCESSFUL | Delivered successfully |
| 5 | FAILED | Delivery failed |
| 6 | RETURNED | Returned to sender |

## Signals (Automation)

### Order Signals (`orders/signals.py`)
- **pre_save**: Auto-generate order_number if missing
- **post_save (created)**: Create AddressVerification, send WhatsApp verification link, create DlAddressUpdate, generate OrderBarcode
- **post_save (update)**: When verified → create OrderVerificationLog, route to batching system or create delivery task

### Delivery Signals (`delivery/signals.py`)
- Push to DMS when delivery task created
- Sync status updates from DMS webhooks

### Dispatch Signals (`dispatch/signals.py`)
- Trigger batch processing when orders are verified

## Celery Tasks & Scheduling

### Configuration
- **Broker**: Redis (configurable via CELERY_BROKER_URL)
- **Timezone**: Asia/Qatar
- **Task Time Limits**: 30 min (hard), 25 min (soft)
- **Max Tasks Per Child**: 1000

### Scheduled Tasks (Celery Beat)
| Task | Interval | Purpose |
|------|----------|---------|
| `check_batch_timeouts` | 30s | Release expired hold windows |
| `auto_assign_ready_batches` | 15s | Assign ready batches to riders |
| `check_sla_risk` | 60s | Force-release SLA-at-risk orders |
| `check_shift_expirations` | 5min | Auto-end expired rider shifts |
| `calculate_daily_kpis` | Daily 00:05 | Calculate rider KPI metrics |

### Queues
- `dispatch` - Batch/rider assignment tasks
- `default` - General tasks

## API Endpoints

### Versioning
- Current: `/api/v1/` (DRF REST API)
- Legacy: `/api/` (defaults to v1)

### Endpoint Categories
| Category | Count | Description |
|----------|-------|-------------|
| Order Management | 8 | CRUD, verification, listing |
| Driver App | 11 | Login, profile, tasks, status updates |
| DMS Integration | 13 | Orders, tasks, drivers, analytics |
| Business APIs | 6 | Dashboard, stats, clients, tasks |
| E-commerce Integration | 2 | Shopify/WooCommerce import |
| Webhooks | 5 | Task status, completion, location |
| QNAS Address | 6 | Zone polygons, geocoding, address lookup |
| API Management | 3 | API key management |
| API Tester | 1 | Interactive testing UI |

## Middleware Stack

Order of execution (in settings.py):
1. SecurityMiddleware
2. SessionMiddleware
3. CommonMiddleware
4. CsrfViewMiddleware
5. AuthenticationMiddleware
6. MessagesMiddleware
7. XFrameOptionsMiddleware
8. AccountMiddleware (django-allauth)
9. **SessionTimeoutMiddleware** (custom - 1 hour inactivity)
10. **SessionWarningMiddleware** (custom - timeout warning)
11. **QueryInspectorMiddleware** (custom - N+1 detection in DEBUG)
12. DebugToolbarMiddleware (DEBUG only)

## Context Processors

| Processor | Purpose |
|-----------|---------|
| `seo_defaults` | SEO metadata (title, description, keywords, canonical) |
| `site_info` | Site name, tagline, year, support contact |
| `social_media_links` | Social media URLs |
| `htmx_request` | HTMX detection (HX-Request header) |
| `user_profile` | Cached user profile (avoids N+1) |
| `user_business` | Cached user's business |
| `business_permissions_context` | Team permissions and access levels |
| `workforce_sidebar_counts` | Sidebar metric counts for staff |

## Decorators

### Core Decorators (`core/decorators.py`)
```python
@staff_required          # Check User.is_staff OR Profile.is_staff
@business_required       # Check if user owns a business
```

### Business Decorators (`business/decorators.py`)
```python
# Role-based access: owner, admin, member, viewer
@business_role_required(['owner', 'admin'])
```

## Logging Configuration

### Log Files (in `/var/log/ezzydelivery/` or project root)
| File | Level | Size | Backups |
|------|-------|------|---------|
| debug.log | DEBUG | 10MB | 5 |
| error.log | ERROR | 10MB | 10 |
| orders.log | INFO | 10MB | 5 |
| delivery.log | INFO | 10MB | 5 |
| api.log | INFO | 10MB | 5 |
| security.log | WARNING | 10MB | 10 |
| queries.log | DEBUG | 10MB | 3 |

### Per-App Loggers
`orders`, `delivery`, `ezzy_api`, `dispatch`, `business`, `fleet`, `product`, `webpages`, `core`

## Environment Variables

Copy `ezzydelivery/envsample` to `ezzydelivery/.env` and configure:

```bash
# Django Core
SECRET_KEY=              # Django secret key
DEBUG=                   # True/False
ALLOWED_HOSTS=           # Comma-separated hosts

# Database
DB_NAME=                 # PostgreSQL database name
DB_USER=                 # Database user
DB_PASSWORD=             # Database password
DB_HOST=                 # Database host (default: localhost)
DB_PORT=                 # Database port (default: 5432)

# Celery
CELERY_BROKER_URL=       # Redis URL (e.g., redis://localhost:6379/0)

# Cache
CACHE_BACKEND=           # django.core.cache.backends.redis.RedisCache
CACHE_LOCATION=          # Redis URL for cache

# Integrations
SHIPDAY_API_KEY=         # ShipDay DMS API key
SHOPIFY_ACCESS_TOKEN=    # Shopify integration
WOOCOMMERCE_API_KEY=     # WooCommerce API key
WOOCOMMERCE_API_SECRET=  # WooCommerce API secret

# AI Agent
ANTHROPIC_API_KEY=       # Claude API key
AI_AGENT_MODEL=          # Model ID (default: claude-sonnet-4-20250514)
AI_AGENT_DAILY_BUDGET=   # Daily budget in USD (default: 50)
AI_AGENT_MONTHLY_BUDGET= # Monthly budget in USD (default: 1000)

# Dispatch
DISPATCH_BATCH_HOLD_MINUTES=   # Hold window duration (default: 3)
DISPATCH_MAX_BATCH_SIZE=       # Max orders per batch (default: 2)
DISPATCH_SLA_RISK_MINUTES=     # SLA risk threshold (default: 15)

# Security
SECURE_SSL_REDIRECT=     # True for production
SECURE_HSTS_SECONDS=     # HSTS duration
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

```python
# Good
Order.objects.select_related('business', 'delivery_task__assigned_driver')

# Bad - causes N+1 queries
for order in Order.objects.all():
    print(order.business.name)  # Each access hits DB
```

### CSS/Styling

All styling must use the Brand Kit variables from `static/webpages/css/brand-kit.css`:
- Never use inline styles or `<style>` tags in templates
- Use CSS variables: `var(--brand-primary)`, `var(--spacing-md)`, etc.
- Link CSS files in `{% block extra_css %}`

### Template IDs

Follow naming pattern: `{app}_{section}_{element_type}_{descriptor}`
```html
<table id="orders_list_table_view">
<button id="workforce_orders_btn_export">
```

### Git Commits

Format: `{type}: {description}` where type is feat/fix/refactor/docs/style/perf/test/chore

## Template Structure

### Base Templates
| Template | Purpose |
|----------|---------|
| `base.html` | Minimal base with static includes |
| `business_dashboard_base.html` | Business owner/manager dashboard |
| `fleet_dashboard_base.html` | Driver fleet management |
| `wf_dashboard_base.html` | Workforce/staff dashboard |
| `account/` | django-allauth authentication pages |
| `socialaccount/` | Social login pages |

### Includes
| Include | Purpose |
|---------|---------|
| `head.html` | Meta tags, CSS loading, SEO |
| `head_seo.html` | Schema.org JSON-LD structured data |
| `navbar.html` | Navigation bar |
| `messages.html` | Django messages framework |
| `scripts.html` | JavaScript includes |
| `toast_notifications.html` | Toast notification system |

### Components
| Component | Purpose |
|-----------|---------|
| `_pagination.html` | Pagination controls |
| `_status_badge.html` | Status display badges |
| `_stat_card.html` | Dashboard stat cards |
| `_empty_state.html` | Empty state UI |

## Management Commands

### Blog/Content
```bash
python manage.py seed_blog_categories
python manage.py create_seo_blog_posts
python manage.py seed_seo_articles_batch1  # through batch4
python manage.py seed_pillar_pages
python manage.py seed_all_blog_content
```

### Delivery
```bash
python manage.py generate_missing_qrcodes
python manage.py import_zones
python manage.py simplify_polygon
python manage.py fetch_zone_polygons
```

### Data
```bash
python manage.py populate_dummy_data
python manage.py create_dummy_data
```

### Utilities
```bash
python manage.py taillog  # Tail log files
python manage.py setup_receipt_templates
```

## Key Files

| File | Purpose |
|------|---------|
| `ezzydelivery/settings.py` | Django settings (710 lines) |
| `ezzydelivery/urls.py` | URL routing |
| `ezzydelivery/celery.py` | Celery configuration with Beat schedule |
| `core/middleware.py` | Custom middleware (session, query inspector) |
| `core/decorators.py` | staff_required, business_required |
| `core/context_processors.py` | Template context processors |
| `core/seo.py` | SEO metadata management |
| `core/ai_search_optimization.py` | AI search optimization |
| `dispatch/services.py` | BatchService, AssignmentService, KPIService |
| `requirements.txt` | Python dependencies |

## Security Configuration

### Cookie Settings
- `SESSION_COOKIE_SECURE=True` (production)
- `CSRF_COOKIE_SECURE=True`
- `SESSION_COOKIE_HTTPONLY=True`
- `CSRF_COOKIE_HTTPONLY=True`
- `SESSION_COOKIE_SAMESITE='Lax'`
- Custom session cookie name: `ezzy_sessionid`
- Session timeout: 1 hour of inactivity

### Headers
- `X_FRAME_OPTIONS='DENY'` (clickjacking protection)
- PERMISSIONS_POLICY for geolocation, camera, microphone, payment
- HSTS enabled in production

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

## Quick Reference

### Test Site Health
```bash
curl -sI https://ezzydelivery.qa/ | head -1
python manage.py check --deploy
```

### View Logs
```bash
# System logs
sudo journalctl -u gunicornezzy -f --no-pager -n 100

# Application logs
tail -f /var/log/ezzydelivery/error.log
tail -f /var/log/ezzydelivery/orders.log
```

### Database Access
```bash
python manage.py dbshell
python manage.py shell
```

### Celery Management
```bash
# Check active tasks
celery -A ezzydelivery inspect active

# Purge all tasks
celery -A ezzydelivery purge

# Check scheduled tasks
celery -A ezzydelivery inspect scheduled
```

## Directory Structure

```
ezzydelivery/
├── core/                  # User profiles, auth, middleware, utilities
├── business/              # Business/store management
├── orders/                # Order management
├── delivery/              # Delivery tasks
├── fleet/                 # Driver management, COD wallet
├── dispatch/              # Order batching, rider assignment
├── warehouse/             # Inventory management
├── product/               # Product catalog
├── workforce/             # Staff dashboard
├── ezzy_api/              # REST API, integrations
├── webpages/              # Public pages, marketing
├── blog/                  # Blog/content
├── ai_agent/              # AI Operations Agent
├── templates/             # Global templates
│   ├── base.html
│   ├── includes/          # Reusable components
│   └── account/           # Auth templates
├── static/                # Static files
│   └── webpages/
│       ├── css/           # Brand kit, page styles
│       ├── js/            # JavaScript
│       └── img/           # Images
├── docs/                  # Documentation (95+ files)
├── manage.py
├── requirements.txt
└── nginx-config-new.conf
```
