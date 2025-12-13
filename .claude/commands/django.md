---
description: Django/PostgreSQL expert mode for backend development
---

# Django/PostgreSQL Expert Mode

You are now in Django/PostgreSQL expert mode for the EzzyDelivery project. Reference the skill file at `.claude/skills/django-postgres.md` for detailed patterns.

## Technology Stack
- Django 5.0+ | PostgreSQL 15+ | Django REST Framework 3.14+
- Celery 5.3+ | Redis 7+ (caching & broker)

## Project Apps
| App | Purpose |
|-----|---------|
| `core/` | User profiles, auth, signals |
| `business/` | Business/client management |
| `orders/` | Order management |
| `delivery/` | Delivery tasks & tracking |
| `fleet/` | Fleet & driver management |
| `warehouse/` | Inventory & stock |
| `workforce/` | Staff dashboard |
| `product/` | Product catalog |
| `ezzy_api/` | API endpoints |

## Critical Rules

### Query Optimization (ALWAYS)
```python
# Use select_related for ForeignKey
qs.select_related('business', 'delivery_agent')

# Use prefetch_related for ManyToMany/reverse FK
qs.prefetch_related('items', 'status_logs')
```

### Model Patterns
- Use `TextChoices` for status fields
- Add `db_index=True` for filtered fields
- Use `related_name` on ForeignKeys
- Inherit from `BaseModel` with timestamps

### Form Patterns
- Use crispy_forms with FormHelper
- Validate in forms, keep models clean
- Pass `user` via `kwargs.pop('user', None)`

### Best Practices
1. **select_related/prefetch_related**: Avoid N+1 queries
2. **Database indexes**: Index WHERE, ORDER BY, JOIN fields
3. **@transaction.atomic**: Wrap related operations
4. **timezone.now()**: Never use datetime.now()
5. **Signals sparingly**: Prefer explicit calls
6. **Cache expensive queries**: Use Django's cache framework

## Common Commands
```bash
python manage.py makemigrations
python manage.py migrate
python manage.py shell_plus
python manage.py test app_name
```

Please describe your Django/PostgreSQL task.
