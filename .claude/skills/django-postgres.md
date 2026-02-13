# Django/PostgreSQL Expert Skill - EzzyDelivery

Use this skill when working on backend tasks: Django models, views, forms, APIs, database queries, and PostgreSQL optimization.

## Technology Stack

| Technology | Version | Purpose |
|------------|---------|---------|
| Django | 5.0+ | Web framework |
| PostgreSQL | 15+ | Primary database |
| Django REST Framework | 3.14+ | API endpoints |
| Celery | 5.3+ | Background tasks |
| Redis | 7+ | Caching & Celery broker |

## Project Structure

| Directory | Purpose |
|-----------|---------|
| `ezzydelivery/` | Project settings & URLs |
| `core/` | User profiles, auth, signals |
| `business/` | Business/client management |
| `orders/` | Order management |
| `delivery/` | Delivery tasks & tracking |
| `fleet/` | Fleet & driver management |
| `warehouse/` | Inventory & stock management |
| `workforce/` | Staff dashboard & operations |
| `product/` | Product catalog |
| `ezzy_api/` | API endpoints |
| `webpages/` | Public website pages |
| `blog/` | Blog & SEO content |

## Key Models & Relationships

### Core App
```python
# core/models.py
Profile          # User profile (extends User)
City             # City/location data
```

### Business App
```python
# business/models.py
Business         # Client businesses
BusinessBranch   # Business locations
```

### Orders App
```python
# orders/models.py
Order            # Main order model
OrderItem        # Order line items
OrderStatusLog   # Status history
```

### Delivery App
```python
# delivery/models.py
DeliveryTask     # Delivery assignments
DeliveryAgent    # Delivery personnel
DeliveryRoute    # Route optimization
```

### Fleet App
```python
# fleet/models.py
Vehicle          # Fleet vehicles
Driver           # Driver profiles
DriverWallet     # Driver payments
```

### Warehouse App
```python
# warehouse/models.py
Warehouse        # Warehouse locations
InventoryItem    # Stock items
StockTransaction # Stock movements
PickList         # Order picking
CycleCount       # Inventory audits
```

## Django Patterns

### Model Best Practices
```python
from django.db import models
from django.utils import timezone

class BaseModel(models.Model):
    """Abstract base with timestamps"""
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True

class Order(BaseModel):
    # Use choices for status fields
    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        CONFIRMED = 'confirmed', 'Confirmed'
        DELIVERED = 'delivered', 'Delivered'
        CANCELLED = 'cancelled', 'Cancelled'

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True  # Index frequently filtered fields
    )

    # Use ForeignKey with related_name
    business = models.ForeignKey(
        'business.Business',
        on_delete=models.CASCADE,
        related_name='orders'
    )

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', 'created_at']),
        ]
```

### View Patterns
```python
from django.views.generic import ListView, DetailView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q, Count, Sum

class OrderListView(LoginRequiredMixin, ListView):
    model = Order
    template_name = 'orders/order_list.html'
    context_object_name = 'orders'
    paginate_by = 25

    def get_queryset(self):
        qs = super().get_queryset()

        # Filter by user's business
        qs = qs.filter(business__user=self.request.user)

        # Search filter
        search = self.request.GET.get('search')
        if search:
            qs = qs.filter(
                Q(order_number__icontains=search) |
                Q(customer_name__icontains=search)
            )

        # Status filter
        status = self.request.GET.get('status')
        if status:
            qs = qs.filter(status=status)

        # Optimize with select_related and prefetch_related
        qs = qs.select_related('business', 'delivery_agent')
        qs = qs.prefetch_related('items')

        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['status_choices'] = Order.Status.choices
        return context
```

### Form Patterns
```python
from django import forms
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Row, Column, Submit

class OrderForm(forms.ModelForm):
    class Meta:
        model = Order
        fields = ['customer_name', 'customer_phone', 'delivery_address']
        widgets = {
            'delivery_address': forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)

        self.helper = FormHelper()
        self.helper.layout = Layout(
            Row(
                Column('customer_name', css_class='col-md-6'),
                Column('customer_phone', css_class='col-md-6'),
            ),
            'delivery_address',
            Submit('submit', 'Save', css_class='btn btn-primary')
        )

    def clean_customer_phone(self):
        phone = self.cleaned_data['customer_phone']
        # Validate phone format
        if not phone.startswith('+'):
            raise forms.ValidationError('Phone must include country code')
        return phone
```

### Signal Patterns
```python
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

@receiver(post_save, sender=Order)
def order_created_handler(sender, instance, created, **kwargs):
    if created:
        # Create delivery task
        DeliveryTask.objects.create(
            order=instance,
            status='pending'
        )
        # Send notification
        send_order_notification.delay(instance.id)

@receiver(pre_save, sender=Order)
def order_status_change_handler(sender, instance, **kwargs):
    if instance.pk:
        old_instance = Order.objects.get(pk=instance.pk)
        if old_instance.status != instance.status:
            # Log status change
            OrderStatusLog.objects.create(
                order=instance,
                old_status=old_instance.status,
                new_status=instance.status
            )
```

## PostgreSQL Optimization

### Query Optimization
```python
# BAD: N+1 queries
orders = Order.objects.all()
for order in orders:
    print(order.business.name)  # Hits DB each iteration

# GOOD: Use select_related for ForeignKey
orders = Order.objects.select_related('business').all()

# GOOD: Use prefetch_related for ManyToMany/reverse FK
orders = Order.objects.prefetch_related('items').all()

# Combine both
orders = Order.objects.select_related(
    'business', 'delivery_agent'
).prefetch_related(
    'items', 'status_logs'
).all()
```

### Aggregation & Annotation
```python
from django.db.models import Count, Sum, Avg, F, Q

# Count orders by status
Order.objects.values('status').annotate(count=Count('id'))

# Sum order totals by business
Business.objects.annotate(
    total_revenue=Sum('orders__total_amount'),
    order_count=Count('orders')
)

# Conditional aggregation
Order.objects.aggregate(
    total=Count('id'),
    delivered=Count('id', filter=Q(status='delivered')),
    pending=Count('id', filter=Q(status='pending'))
)

# F expressions for field comparisons
Order.objects.filter(delivered_at__gt=F('expected_delivery'))
```

### Raw SQL (when needed)
```python
from django.db import connection

# Use raw() for complex queries
Order.objects.raw('''
    SELECT o.*, b.name as business_name
    FROM orders_order o
    JOIN business_business b ON o.business_id = b.id
    WHERE o.created_at > %s
''', [start_date])

# Use cursor for non-model queries
with connection.cursor() as cursor:
    cursor.execute('''
        SELECT DATE(created_at), COUNT(*)
        FROM orders_order
        GROUP BY DATE(created_at)
        ORDER BY 1 DESC
        LIMIT 30
    ''')
    results = cursor.fetchall()
```

### Database Indexes
```python
class Order(models.Model):
    # Single field index
    status = models.CharField(max_length=20, db_index=True)

    class Meta:
        indexes = [
            # Composite index
            models.Index(fields=['status', 'created_at']),
            # Partial index (PostgreSQL)
            models.Index(
                fields=['created_at'],
                name='pending_orders_idx',
                condition=Q(status='pending')
            ),
        ]
```

## API Patterns (DRF)

### Serializer
```python
from rest_framework import serializers

class OrderSerializer(serializers.ModelSerializer):
    business_name = serializers.CharField(source='business.name', read_only=True)
    items = OrderItemSerializer(many=True, read_only=True)

    class Meta:
        model = Order
        fields = ['id', 'order_number', 'status', 'business_name', 'items']
        read_only_fields = ['order_number']
```

### ViewSet
```python
from rest_framework import viewsets, permissions
from rest_framework.decorators import action
from rest_framework.response import Response

class OrderViewSet(viewsets.ModelViewSet):
    serializer_class = OrderSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Order.objects.filter(
            business__user=self.request.user
        ).select_related('business')

    @action(detail=True, methods=['post'])
    def mark_delivered(self, request, pk=None):
        order = self.get_object()
        order.status = 'delivered'
        order.delivered_at = timezone.now()
        order.save()
        return Response({'status': 'delivered'})
```

## Celery Tasks

```python
from celery import shared_task
from django.core.mail import send_mail

@shared_task
def send_order_notification(order_id):
    order = Order.objects.get(id=order_id)
    send_mail(
        subject=f'Order {order.order_number} Received',
        message=f'Your order has been received.',
        from_email='noreply@ezzydelivery.com',
        recipient_list=[order.customer_email],
    )

@shared_task
def generate_daily_report():
    """Run via celery beat at end of day"""
    from django.utils import timezone
    today = timezone.now().date()

    stats = Order.objects.filter(
        created_at__date=today
    ).aggregate(
        total=Count('id'),
        delivered=Count('id', filter=Q(status='delivered'))
    )
    # Save or email report
```

## Common Management Commands

```bash
# Database
python manage.py migrate
python manage.py makemigrations
python manage.py showmigrations
python manage.py dbshell

# Django shell
python manage.py shell_plus  # with django-extensions

# Create superuser
python manage.py createsuperuser

# Collect static files
python manage.py collectstatic

# Run development server
python manage.py runserver

# Run tests
python manage.py test app_name
python manage.py test app_name.tests.TestClassName
```

## Settings Patterns

```python
# ezzydelivery/settings.py

# Database configuration
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': env('DB_NAME'),
        'USER': env('DB_USER'),
        'PASSWORD': env('DB_PASSWORD'),
        'HOST': env('DB_HOST'),
        'PORT': env('DB_PORT', default='5432'),
        'CONN_MAX_AGE': 60,  # Connection pooling
    }
}

# Cache configuration
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.redis.RedisCache',
        'LOCATION': env('REDIS_URL'),
    }
}

# Celery configuration
CELERY_BROKER_URL = env('REDIS_URL')
CELERY_RESULT_BACKEND = env('REDIS_URL')
```

## Production Deployment

### Production Environment

**Server Stack:**
- **Web Server**: Nginx (reverse proxy)
- **App Server**: Gunicorn (gunicornezzy service)
- **Database**: PostgreSQL 15+
- **Cache/Broker**: Redis
- **Task Queue**: Celery
- **CDN**: Cloudflare

**Server Paths:**
```
/home/ezzyadmin/ezdlproject/
├── ezzydelivery/          # Django project root
│   ├── manage.py
│   ├── ezzydelivery/      # Settings module
│   ├── static/            # Development static files
│   └── staticfiles/       # Collected static files
└── venvezzy/              # Virtual environment
```

### Deployment Commands

**Quick Reload (No Downtime):**
```bash
# Graceful Gunicorn reload - workers restart one at a time
kill -HUP $(pgrep -f "gunicorn.*ezzydelivery" | head -1)
```

**Full Service Restart:**
```bash
# Stop and restart Gunicorn service
sudo systemctl restart gunicornezzy

# Check service status
sudo systemctl status gunicornezzy

# View logs
sudo journalctl -u gunicornezzy -f --no-pager -n 100
```

**Database Migrations:**
```bash
# ALWAYS backup before migrations in production
# Run migrations
source ../venvezzy/bin/activate
python manage.py migrate

# Check migration status
python manage.py showmigrations
```

**Static Files:**
```bash
# Collect static files for production
python manage.py collectstatic --noinput

# If Cloudflare caching issues:
# Purge cache from Cloudflare dashboard or API
```

**Nginx Commands:**
```bash
# Test nginx config
sudo nginx -t

# Reload nginx
sudo systemctl reload nginx

# View nginx logs
sudo tail -f /var/log/nginx/error.log
```

### Deployment Checklist

**Pre-Deployment:**
- [ ] Run tests: `python manage.py test`
- [ ] Check for issues: `python manage.py check --deploy`
- [ ] Review migrations: `python manage.py showmigrations`
- [ ] Backup database if needed

**Deployment Steps:**
1. Pull latest code: `git pull origin master`
2. Install dependencies: `pip install -r requirements.txt`
3. Run migrations: `python manage.py migrate`
4. Collect static: `python manage.py collectstatic --noinput`
5. Reload Gunicorn: `kill -HUP $(pgrep -f "gunicorn.*ezzydelivery" | head -1)`

**Post-Deployment:**
- [ ] Verify site is accessible: `curl -sI https://ezzydelivery.qa/`
- [ ] Check for errors in logs: `sudo journalctl -u gunicornezzy -n 50`
- [ ] Test critical paths (login, orders, etc.)
- [ ] Monitor for 5-10 minutes

### Troubleshooting

**502 Bad Gateway:**
```bash
# Check if Gunicorn is running
sudo systemctl status gunicornezzy

# Restart if needed
sudo systemctl restart gunicornezzy

# Check socket permissions
ls -la /run/gunicornezzy.sock
```

**Static Files 404:**
```bash
# Re-collect static files
python manage.py collectstatic --clear --noinput

# Check nginx static config
sudo nginx -t
```

**Database Connection Issues:**
```bash
# Check PostgreSQL status
sudo systemctl status postgresql

# Test connection
python manage.py dbshell
```

**Celery Not Processing Tasks:**
```bash
# Check Celery workers
sudo systemctl status celery

# Restart Celery
sudo systemctl restart celery

# Check Redis
redis-cli ping
```

### Environment Variables

Critical production settings in `/home/ezzyadmin/ezdlproject/ezzydelivery/.env`:
```
DEBUG=False
ALLOWED_HOSTS=ezzydelivery.qa,www.ezzydelivery.qa
SECRET_KEY=<production-secret>
DATABASE_URL=postgres://...
REDIS_URL=redis://localhost:6379/0
```

### Rollback Procedure

```bash
# If deployment fails, rollback to previous commit
git log --oneline -5  # Find previous working commit
git revert HEAD       # Revert last commit
# OR
git reset --hard <commit-hash>

# Then redeploy
python manage.py migrate
python manage.py collectstatic --noinput
kill -HUP $(pgrep -f "gunicorn.*ezzydelivery" | head -1)
```

## Best Practices

1. **Use select_related/prefetch_related**: Always optimize queries to avoid N+1
2. **Add database indexes**: Index fields used in WHERE, ORDER BY, JOIN
3. **Use transactions**: Wrap related operations in `@transaction.atomic`
4. **Validate at form level**: Keep models clean, validate in forms
5. **Use signals sparingly**: Prefer explicit calls over implicit signals
6. **Cache expensive queries**: Use Django's cache framework
7. **Write tests**: Test models, views, and API endpoints
8. **Use management commands**: For data migrations and maintenance tasks
9. **Log important events**: Use Django's logging framework
10. **Handle timezone properly**: Always use `timezone.now()` not `datetime.now()`
