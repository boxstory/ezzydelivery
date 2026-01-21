---
description: API development and debugging mode
---

# API Development Mode

You are now in API development mode for the EzzyDelivery project. Reference `.claude/skills/api-development.md` for detailed patterns.

## API Structure

```
/api/v1/
├── auth/           # Authentication
├── orders/         # Order management
├── businesses/     # Business endpoints
├── deliveries/     # Delivery tracking
├── drivers/        # Fleet management
└── webhooks/       # External webhooks
```

## Quick Test Commands

### Using curl
```bash
# Get auth token
curl -X POST https://ezzydelivery.qa/api/v1/auth/token/ \
  -d "username=USER&password=PASS"

# List orders (with token)
curl -H "Authorization: Token <token>" \
  https://ezzydelivery.qa/api/v1/orders/

# Create order
curl -X POST -H "Authorization: Token <token>" \
  -H "Content-Type: application/json" \
  -d '{"customer_name": "Test", "delivery_address": "Doha"}' \
  https://ezzydelivery.qa/api/v1/orders/
```

### Using Django Shell
```bash
python manage.py shell

# Test serializer
from orders.serializers import OrderSerializer
from orders.models import Order
order = Order.objects.first()
serializer = OrderSerializer(order)
print(serializer.data)
```

## Key Files

| Component | Location |
|-----------|----------|
| URLs | `ezzy_api/urls.py` |
| Views | `ezzy_api/views.py` |
| Serializers | `ezzy_api/serializers.py` |
| Shopify | `ezzy_api/shopify/` |
| ShipDay | `ezzy_api/shipday/` |

## Response Format

### Success
```json
{
  "status": "success",
  "data": {...}
}
```

### Error
```json
{
  "status": "error",
  "message": "Error description",
  "code": "ERROR_CODE"
}
```

## Webhook Testing

### Shopify Webhook
```bash
# Test webhook locally
curl -X POST http://localhost:8000/api/v1/webhooks/shopify/orders/ \
  -H "Content-Type: application/json" \
  -H "X-Shopify-Topic: orders/create" \
  -d '{"id": 123, "customer": {...}}'
```

What API task would you like to work on?
