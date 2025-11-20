# Claude AI Configuration for EzzyDelivery Project

## 🎨 CRITICAL DESIGN RULE

> **⚠️ MANDATORY: ALL styling work MUST use the Brand Kit Reference**
>
> **Document:** [`/docs/BRAND_KIT_REFERENCE.md`](BRAND_KIT_REFERENCE.md)
>
> - ❌ **NEVER** create custom colors, gradients, or spacing values
> - ❌ **NEVER** use inline styles or `<style>` tags in templates
> - ❌ **NEVER** hardcode design values
> - ✅ **ALWAYS** use CSS variables from `brand-kit.css`
> - ✅ **ALWAYS** use predefined components and classes
> - ✅ **ALWAYS** follow the brand kit naming conventions
>
> This is the single source of truth for all design decisions.

---

## Project Overview

**Project Name**: EzzyDelivery
**Type**: Django-based Delivery Management System
**Location**: `c:\00-web-dev\django-ezzydelivery\ezzydelivery`
**Python Version**: 3.x
**Django Version**: 5.1.7
**Primary Purpose**: Multi-tenant delivery and logistics management platform

---

## Project Structure

### Main Django Apps

```
ezzydelivery/
├── core/           # User profiles, authentication, base models
├── client/         # Business client management
├── workforce/      # Staff dashboard and operations
├── fleet/          # Driver and vehicle management
├── delivery/       # Delivery tasks and jobs
├── orders/         # Order management and processing
├── product/        # Product catalog and inventory
├── webpages/       # Public-facing marketing pages
├── ezzy_api/       # API integrations (ShipDay DMS)
├── docs/           # Project documentation
├── static/         # Static assets (CSS, JS, images)
├── media/          # User-uploaded files
└── templates/      # Shared templates
```

### Key Files

- **Settings**: `ezzydelivery/settings.py`
- **Main URLs**: `ezzydelivery/urls.py`
- **Requirements**: `requirements.txt`
- **Database**: SQLite (development) / PostgreSQL (production)

---

## Django Model Conventions

### Choice Fields - CRITICAL RULES

**❌ NEVER use sets `{}` for choices**
**✅ ALWAYS use lists `[]` or tuples `()` for choices**

```python
# ❌ WRONG - Causes endless migrations
STATUS_CHOICES = {
    ('active', 'Active'),
    ('inactive', 'Inactive'),
}

# ✅ CORRECT - Stable ordering
STATUS_CHOICES = [
    ('active', 'Active'),
    ('inactive', 'Inactive'),
]
```

### Field Defaults - CRITICAL RULES

**❌ NEVER use string defaults for BooleanField**
**✅ ALWAYS use actual boolean values**

```python
# ❌ WRONG
is_active = models.BooleanField(default="True")

# ✅ CORRECT
is_active = models.BooleanField(default=True)
```

### Database Indexes

This project uses strategic indexing for performance:
- Foreign keys that are frequently filtered
- Fields used in `filter()` and `get()` queries
- Unique fields like order numbers and codes
- Compound indexes for common query patterns

**Example from Order model:**
```python
indexes = [
    models.Index(fields=['business', 'order_status', '-created_at'], name='ord_biz_status_created_idx'),
    models.Index(fields=['verification_status'], name='ord_verification_idx'),
]
```

---

## Template ID Naming Convention

### Pattern
```
{app}_{section}_{element_type}_{descriptor}
```

### Element Types
- `header` - Page headers
- `title` - Title elements
- `card` - Card containers
- `table` - Table elements
- `thead` - Table headers
- `tbody` - Table bodies
- `form` - Forms
- `input` - Input fields
- `select` - Dropdowns
- `btn` - Buttons
- `modal` - Modals
- `sidebar` - Sidebars
- `nav` - Navigation
- `section` - Sections

### Examples
```html
<!-- Workforce App -->
<div id="workforce_dashboard_sidebar_main">
<table id="workforce_orders_table_all">
<button id="workforce_orders_btn_export">

<!-- Client App -->
<form id="client_profile_form_update">
<div id="client_dashboard_card_revenue">

<!-- Orders App -->
<table id="orders_list_table_view">
<button id="orders_add_btn_submit">
```

### Mobile Variants
Use `_mob` suffix for mobile versions:
```html
<div id="workforce_sidebar_main">          <!-- Desktop -->
<div id="workforce_sidebar_mob_wrapper">   <!-- Mobile -->
```

---

## Coding Standards

### Python Style
- Follow PEP 8
- Use meaningful variable names
- Add docstrings to complex functions
- Keep functions focused (single responsibility)

### Django Best Practices
- Use `select_related()` and `prefetch_related()` for query optimization
- Always use `get_object_or_404()` for single object retrieval
- Use Django's built-in validators
- Leverage Django's ORM instead of raw SQL when possible

### Template Best Practices
- Use `{% load static %}` for static files
- Always escape user input (Django does this by default)
- Use template inheritance (`{% extends %}`)
- Include templates with `{% include %}`
- Use `{% url %}` template tag instead of hardcoded URLs

### JavaScript/jQuery
- Use unique IDs for element selection
- Prefer `document.getElementById()` or `$('#id')` over class selectors
- Add event listeners, don't use inline `onclick` (except for mobile toggles)
- Keep JavaScript in separate files when possible

---

## Common Workflows

### Adding New Features

1. **Models**: Define in `{app}/models.py`
2. **Migrations**: Run `python manage.py makemigrations && python manage.py migrate`
3. **Views**: Create in `{app}/views.py`
4. **URLs**: Add to `{app}/urls.py`
5. **Templates**: Create in `{app}/templates/{app}/`
6. **Forms**: Define in `{app}/forms.py` (if needed)
7. **Static Files**: Add to `{app}/static/{app}/`

### Migration Workflow

```bash
# Check for changes
python manage.py makemigrations

# Review migration file
cat {app}/migrations/00XX_*.py

# Apply migration
python manage.py migrate

# Verify
python manage.py showmigrations
```

### Testing Changes

```bash
# Check for errors
python manage.py check

# Run development server
python manage.py runserver

# Run specific tests
python manage.py test {app}
```

---

## Database Schema Overview

### Core Models
- **Profile**: User profiles (linked to Django User)
  - **user_number**: Permanent user identification number (format: `EZZY{year}{6-digit-random}`)
  - Never changes, even if username or email changes
  - Auto-generated on profile creation
  - Used for customer support, receipts, and public-facing identification
- **User**: Django's built-in user model

### Client Models
- **Business**: Client businesses
- **PickupLocation**: Business pickup locations
- **BusinessTeam**: Team members for businesses

### Orders Models
- **Order**: Main order records
- **OrderItem**: Order line items (products)
- **OrderBarcode**: Generated barcodes
- **AddressVerification**: Address verification system

### Fleet Models
- **Driver**: Driver profiles and accounts
- **DriverVehicle**: Vehicle assignments
- **CODTransaction**: Cash on delivery tracking

### Delivery Models
- **DeliveryList**: Delivery tasks
- **DeliveryJob**: Delivery job assignments

### Product Models
- **Product**: Product catalog

---

## API Integrations

### ShipDay DMS Integration
- Located in `ezzy_api/` app
- Handles order syncing with ShipDay
- Manual task linking available
- Sync monitoring dashboard

### Key Features
- Order publishing to DMS
- Driver synchronization
- Status updates
- Analytics tracking

---

## Common Issues & Solutions

### Issue: Login Not Working ⚠️
**Cause**: Missing `AUTHENTICATION_BACKENDS` in settings.py
**Solution**: Add to settings.py:
```python
AUTHENTICATION_BACKENDS = [
    'django.contrib.auth.backends.ModelBackend',
    'allauth.account.auth_backends.AuthenticationBackend',
]

ACCOUNT_LOGIN_METHODS = {'username', 'email'}
ACCOUNT_EMAIL_VERIFICATION = "none"
```

### Issue: Migrations Keep Being Created
**Cause**: Using sets `{}` for choices or string defaults for BooleanField
**Solution**: Convert to lists `[]` and use proper boolean values

### Issue: Query Performance
**Cause**: Missing database indexes or N+1 queries
**Solution**: Add indexes to frequently queried fields, use `select_related()`/`prefetch_related()`

### Issue: Template Not Found
**Cause**: Incorrect template path or app not in INSTALLED_APPS
**Solution**: Check `INSTALLED_APPS` in settings.py, verify template path

### Issue: Static Files Not Loading
**Cause**: STATIC_URL or STATICFILES_DIRS misconfigured
**Solution**: Run `python manage.py collectstatic` and check settings

---

## Security Considerations

### Authentication
- Use Django's built-in authentication
- AllAuth for social authentication
- Token-based API authentication

### Data Protection
- Never commit `.env` files
- Keep `SECRET_KEY` secure
- Use environment variables for sensitive data
- Sanitize user inputs (Django does this by default)

### Common Vulnerabilities to Avoid
- SQL Injection: Use Django ORM
- XSS: Django templates auto-escape
- CSRF: Use `{% csrf_token %}` in forms
- Command Injection: Never use `os.system()` with user input

---

## Development Environment

### Virtual Environment
```bash
# Activate virtual environment
source venvezzy/bin/activate  # Linux/Mac
venvezzy\Scripts\activate      # Windows
```

### Required Environment Variables
```
SECRET_KEY=your-secret-key
DEBUG=True
DATABASE_URL=sqlite:///db.sqlite3
SHIPDAY_API_KEY=your-api-key
```

### Development Server
```bash
python manage.py runserver
# Access at: http://127.0.0.1:8000/
```

---

## Testing Strategy

### Manual Testing Checklist
1. Test all CRUD operations
2. Verify form validation
3. Check permissions and authentication
4. Test on multiple browsers
5. Test responsive design (mobile/desktop)

### Automated Testing (Future)
- Unit tests for models
- Integration tests for views
- E2E tests using Selenium/Playwright
- Use new template IDs for element selection

---

## Documentation Resources

### Project Documentation
- **[Brand Kit Reference](./BRAND_KIT_REFERENCE.md)** ⭐ **START HERE for all styling work**
- [CSS/JS Architecture](./CSS_JS_ARCHITECTURE.md)
- [Coding Standards](./CODING_STANDARDS.md)
- [Template ID Naming Convention](./TEMPLATE_ID_NAMING_CONVENTION.md)
- [Template IDs Summary](./TEMPLATE_IDS_SUMMARY.md)
- [Database Optimization Guide](./DATABASE_OPTIMIZATION.md)
- [API Documentation](./API_DOCUMENTATION.md)

### Django Resources
- Django Documentation: https://docs.djangoproject.com/
- Django Best Practices: https://django-best-practices.readthedocs.io/
- Two Scoops of Django (Book)

### External Services
- ShipDay API: https://shipday.com/api-docs
- Bootstrap 5: https://getbootstrap.com/docs/5.0/
- Font Awesome: https://fontawesome.com/

---

## Git Workflow

### Commit Message Format
```
{type}: {short description}

{detailed description if needed}

Generated with Claude Code
Co-Authored-By: Claude <noreply@anthropic.com>
```

### Types
- `feat`: New feature
- `fix`: Bug fix
- `refactor`: Code refactoring
- `docs`: Documentation changes
- `style`: Code style changes (formatting)
- `perf`: Performance improvements
- `test`: Adding tests
- `chore`: Maintenance tasks

### Example
```
fix: Resolve migration loop in Order model choices

Changed ORDER_STATUS_BY_CLIENT from set to list to prevent
Django from detecting false changes in field definitions.

Generated with Claude Code
Co-Authored-By: Claude <noreply@anthropic.com>
```

---

## Quick Reference Commands

### Django Management
```bash
# Create superuser
python manage.py createsuperuser

# Database shell
python manage.py dbshell

# Python shell with Django context
python manage.py shell

# Clear database (dev only)
python manage.py flush

# Check deployment readiness
python manage.py check --deploy
```

### Common Queries
```bash
# Find all templates
find . -name "*.html" -path "*/templates/*"

# Count lines of Python code
find . -name "*.py" | xargs wc -l

# Search for TODO comments
grep -r "TODO" --include="*.py"
```

---

## Performance Optimization

### Database
- Use `select_related()` for foreign key relationships
- Use `prefetch_related()` for reverse foreign keys and many-to-many
- Add indexes to frequently filtered fields
- Use `only()` and `defer()` to limit fields retrieved

### Templates
- Minimize database queries in templates
- Use template fragment caching
- Optimize image sizes
- Minify CSS/JS in production

### Caching Strategy
- Cache expensive queries
- Use Redis for session storage (production)
- Cache template fragments
- Cache static pages

---

## Deployment Checklist

### Pre-Deployment
- [ ] Run `python manage.py check --deploy`
- [ ] Set `DEBUG = False`
- [ ] Configure `ALLOWED_HOSTS`
- [ ] Set up proper database (PostgreSQL)
- [ ] Configure static file serving
- [ ] Set up email backend
- [ ] Enable HTTPS
- [ ] Configure CORS if needed

### Post-Deployment
- [ ] Run migrations
- [ ] Collect static files
- [ ] Create superuser
- [ ] Test critical user flows
- [ ] Monitor error logs
- [ ] Set up backups

---

## Maintenance Tasks

### Regular Tasks
- Review and optimize slow queries
- Clean up old sessions: `python manage.py clearsessions`
- Backup database regularly
- Update dependencies: `pip list --outdated`
- Review error logs
- Monitor disk space (media files)

### Monthly Tasks
- Security updates
- Dependency updates
- Performance review
- Database optimization
- Review and archive old orders

---

## Contact & Support

### Project Team
- **Developer**: [Your Name]
- **Project Manager**: [PM Name]

### Support Resources
- Project Documentation: `/docs/`
- Django Admin: `/admin/`
- Issue Tracker: [GitHub/GitLab URL]

---

## Version History

- **v1.0.0**: Initial release with template ID implementation
- **Current**: Template IDs added across all 213 templates
- **Last Updated**: 2025-11-16

---

## Notes for Claude AI Assistant

### When Working on This Project

1. **ALWAYS use the Brand Kit Reference** - See `/docs/BRAND_KIT_REFERENCE.md` for all styling decisions
   - ❌ NEVER create custom colors, gradients, or spacing values
   - ❌ NEVER use inline styles or `<style>` tags in templates
   - ✅ ONLY use CSS variables from `brand-kit.css`
   - ✅ ONLY use predefined components and classes
2. **Always check model field types** before creating migrations
3. **Use lists `[]` for Django choices**, never sets `{}`
4. **Follow the template ID naming convention** for all HTML changes
5. **Check for existing documentation** in `/docs/` before asking user
6. **Run `python manage.py check`** after model changes
7. **Test migrations** in development before suggesting production deployment
8. **Keep security in mind** - never expose sensitive data
9. **Optimize queries** - use `select_related()` and `prefetch_related()`
10. **Reference existing code** patterns in the project
11. **Document significant changes** in appropriate `/docs/` files

### Common User Requests

- "Add unique IDs to templates" → Use naming convention from TEMPLATE_ID_NAMING_CONVENTION.md
- "Fix migration issues" → Check for sets in choices, string defaults in BooleanFields
- "Optimize performance" → Check for N+1 queries, add indexes
- "Add new feature" → Follow the workflow: model → migration → view → template → URLs
- "Auto-load and disable fields" → Set `initial` value and add `disabled=True` + `widget.attrs['readonly']=True` in view

### Project-Specific Context

- This is a **multi-tenant SaaS** platform
- **ShipDay integration** is critical for DMS functionality
- **COD tracking** is a key business requirement
- **Mobile responsiveness** is essential
- **Template IDs** have been systematically added (see TEMPLATE_IDS_SUMMARY.md)

### Form Field Best Practices

**Auto-populate and Disable Fields**:
When you need to auto-load a value from the logged-in user and prevent editing:

```python
# In the view - ensure synchronization on page load:
# Ensure profile username matches Django User username
if profile.username != request.user.username:
    profile.username = request.user.username
    profile.save()

# In both GET and POST:
form.fields['username'].initial = request.user.username
form.fields['username'].widget.attrs['readonly'] = True
form.fields['username'].disabled = True

# On save, force the value to stay synchronized:
if form.is_valid():
    instance = form.save(commit=False)
    instance.username = request.user.username  # Force sync with Django User
    instance.save()
```

**Example**: See `core/views.py` - `profile_complete_update()` function (lines 677-750)

**Important Note**: In this project, the Profile model has its own `username` field that must stay synchronized with Django's User model `username` field. The code above ensures they always match.

### User Identification System

**Permanent User Number**:
The system now includes a permanent, immutable user identification number that never changes:

```python
# Profile Model Field:
user_number = models.CharField(max_length=20, unique=True, editable=False,
                               null=True, blank=True, db_index=True)

# Format: EZZY{year}{6-digit-random}
# Example: EZZY2025847362
```

**Key Features**:
- ✅ **Auto-generated** on profile creation
- ✅ **Never changes** even if username or email changes
- ✅ **Unique** across all users
- ✅ **Editable=False** prevents accidental modification in admin
- ✅ **Indexed** for fast lookups
- ✅ **User-friendly** format for customer support

**Use Cases**:
- Customer support reference numbers
- Receipt and invoice identification
- Support ticket references
- Public-facing user identification (safer than exposing User.id)
- Audit logs and tracking

**Access**:
```python
# In views:
user_number = request.user.profile.user_number

# In templates:
{{ request.user.profile.user_number }}
```

---

**Last Updated**: 2025-11-20
**Configuration Version**: 2.0
**Major Update**: Added mandatory Brand Kit Reference as single source of truth for all styling
