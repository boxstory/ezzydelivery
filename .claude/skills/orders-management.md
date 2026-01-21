# EzzyDelivery Orders Management Skill

## Order Flow

```
┌─────────┐    ┌──────────┐    ┌──────────┐    ┌───────────┐    ┌───────────┐
│ PENDING │───▶│ ASSIGNED │───▶│ PICKED   │───▶│ DELIVERED │───▶│ COMPLETED │
└─────────┘    └──────────┘    └──────────┘    └───────────┘    └───────────┘
     │              │               │               │
     │              │               │               │
     ▼              ▼               ▼               ▼
┌─────────┐    ┌──────────┐    ┌──────────┐    ┌───────────┐
│CANCELLED│    │ RETURNED │    │  FAILED  │    │  PARTIAL  │
└─────────┘    └──────────┘    └──────────┘    └───────────┘
```

## Order Model Structure

### Key Models (orders app)
```python
# orders/models.py
class Order(BaseModel):
    # Relationships
    business = ForeignKey(Business)         # Owner business
    delivery_agent = ForeignKey(Driver)     # Assigned driver
    zone = ForeignKey(Zone)                 # Delivery zone

    # Customer Info
    customer_name = CharField(max_length=200)
    customer_phone = CharField(max_length=20)
    customer_email = EmailField(blank=True)

    # Addresses
    pickup_address = TextField()
    delivery_address = TextField()

    # Financial
    total_amount = DecimalField()
    cod_amount = DecimalField()             # Cash on Delivery
    delivery_fee = DecimalField()

    # Status
    status = CharField(choices=STATUS_CHOICES)
    payment_status = CharField(choices=PAYMENT_CHOICES)

    # Tracking
    order_number = CharField(unique=True)   # Auto-generated: EZ-YYYY-XXXXXX
    barcode = CharField(unique=True)
    tracking_url = URLField()

class OrderItem(BaseModel):
    order = ForeignKey(Order)
    product_name = CharField()
    quantity = IntegerField()
    unit_price = DecimalField()
    sku = CharField(blank=True)
```

## Common Queries

### Filter Orders
```python
from orders.models import Order
from django.utils import timezone

# Orders by status
pending = Order.objects.filter(status='pending')
today_orders = Order.objects.filter(created_at__date=timezone.now().date())

# Orders by business
business_orders = Order.objects.filter(business_id=1)

# Orders with COD
cod_orders = Order.objects.filter(cod_amount__gt=0)

# Optimized query (ALWAYS use for lists)
orders = Order.objects.select_related(
    'business', 'delivery_agent', 'zone'
).prefetch_related('items')
```

### Order Statistics
```python
from django.db.models import Count, Sum, Avg

# Daily stats
daily_stats = Order.objects.filter(
    created_at__date=timezone.now().date()
).aggregate(
    total_orders=Count('id'),
    total_revenue=Sum('total_amount'),
    total_cod=Sum('cod_amount'),
    avg_order_value=Avg('total_amount')
)

# Orders by status
status_counts = Order.objects.values('status').annotate(
    count=Count('id')
).order_by('status')
```

## Order Creation

### From Dashboard
```python
from orders.forms import OrderForm

def create_order(request):
    if request.method == 'POST':
        form = OrderForm(request.POST, user=request.user)
        if form.is_valid():
            order = form.save(commit=False)
            order.business = request.user.business
            order.save()
            # Create order items
            for item_data in form.cleaned_data.get('items', []):
                OrderItem.objects.create(order=order, **item_data)
            return redirect('orders:detail', pk=order.pk)
```

### From API (Shopify/WooCommerce)
```python
# ezzy_api/shopify/views.py
def handle_shopify_order(shopify_data):
    order = Order.objects.create(
        business=get_business_from_shop(shopify_data['shop']),
        customer_name=shopify_data['customer']['name'],
        customer_phone=shopify_data['customer']['phone'],
        delivery_address=format_address(shopify_data['shipping_address']),
        total_amount=shopify_data['total_price'],
        cod_amount=shopify_data['total_price'] if is_cod else 0,
        external_id=shopify_data['id'],
        source='shopify'
    )
    # Create items
    for line_item in shopify_data['line_items']:
        OrderItem.objects.create(
            order=order,
            product_name=line_item['title'],
            quantity=line_item['quantity'],
            unit_price=line_item['price']
        )
    return order
```

## Driver Assignment

### Manual Assignment
```python
def assign_driver(order, driver):
    with transaction.atomic():
        order.delivery_agent = driver
        order.status = 'assigned'
        order.assigned_at = timezone.now()
        order.save()

        # Create delivery task
        DeliveryTask.objects.create(
            order=order,
            driver=driver,
            status='pending'
        )

        # Notify driver
        send_driver_notification(driver, order)
```

### Batch Assignment (Dispatch)
```python
# dispatch/services.py
def batch_assign_orders(orders, driver):
    """Assign multiple orders to driver as a batch."""
    with transaction.atomic():
        batch = Batch.objects.create(
            driver=driver,
            status='pending'
        )
        for order in orders:
            order.delivery_agent = driver
            order.batch = batch
            order.status = 'assigned'
            order.save()

        batch.total_orders = len(orders)
        batch.save()
    return batch
```

## COD Management

### COD Collection Flow
```
Order Delivered → Driver Collects Cash → Records in App → Settlement to Business
```

### COD Tracking
```python
from fleet.models import CODTransaction

# Record COD collection
def record_cod_collection(order, driver):
    CODTransaction.objects.create(
        order=order,
        driver=driver,
        amount=order.cod_amount,
        status='collected',
        collected_at=timezone.now()
    )
    order.payment_status = 'collected'
    order.save()

# COD Settlement Report
def get_cod_settlement(business, date_range):
    return CODTransaction.objects.filter(
        order__business=business,
        collected_at__range=date_range,
        status='collected'
    ).aggregate(
        total_cod=Sum('amount'),
        order_count=Count('id')
    )
```

## Order Status Updates

### Update with History
```python
from orders.models import OrderStatusLog

def update_order_status(order, new_status, user=None, notes=''):
    old_status = order.status
    order.status = new_status
    order.save()

    # Log status change
    OrderStatusLog.objects.create(
        order=order,
        old_status=old_status,
        new_status=new_status,
        changed_by=user,
        notes=notes
    )

    # Send notifications
    if new_status == 'delivered':
        notify_customer_delivered(order)
    elif new_status == 'failed':
        notify_business_failed(order)
```

## Address Verification

```python
# orders/utils.py
def verify_qatar_address(address):
    """Basic Qatar address validation."""
    qatar_areas = [
        'doha', 'al wakrah', 'lusail', 'al rayyan',
        'al khor', 'umm salal', 'west bay', 'pearl'
    ]
    address_lower = address.lower()
    return any(area in address_lower for area in qatar_areas)

def extract_zone_from_address(address):
    """Determine delivery zone from address."""
    # Implementation depends on zone mapping
    pass
```

## Views Location

- **Business Dashboard**: `business/views.py` → `business/templates/business/orders/`
- **Workforce Dashboard**: `workforce/views.py` → `workforce/templates/workforce/orders/`
- **API**: `ezzy_api/views.py`
- **Public Tracking**: `delivery/views.py`

## Key URLs

```python
# orders/urls.py
urlpatterns = [
    path('', OrderListView.as_view(), name='list'),
    path('create/', OrderCreateView.as_view(), name='create'),
    path('<int:pk>/', OrderDetailView.as_view(), name='detail'),
    path('<int:pk>/edit/', OrderUpdateView.as_view(), name='edit'),
    path('<int:pk>/assign/', assign_driver, name='assign'),
    path('<int:pk>/status/', update_status, name='status'),
    path('export/', export_orders, name='export'),
]
```
