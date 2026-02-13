# EzzyDelivery API Development Skill

## API Architecture

### Endpoints Structure
```
/api/v1/                    # Versioned API (current)
/api/                       # Legacy support (defaults to v1)
├── auth/                   # Authentication endpoints
├── orders/                 # Order management
├── businesses/             # Business/client endpoints
├── deliveries/             # Delivery tracking
├── drivers/                # Driver/fleet endpoints
└── webhooks/               # External webhooks (Shopify, ShipDay)
```

### Technology Stack
- Django REST Framework 3.14+
- Token Authentication (DRF TokenAuth)
- JSON responses
- Rate limiting via Django Ratelimit

## API Patterns

### ViewSet Example
```python
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

class OrderViewSet(viewsets.ModelViewSet):
    """
    API endpoint for orders.

    list: GET /api/v1/orders/
    create: POST /api/v1/orders/
    retrieve: GET /api/v1/orders/{id}/
    update: PUT /api/v1/orders/{id}/
    partial_update: PATCH /api/v1/orders/{id}/
    destroy: DELETE /api/v1/orders/{id}/
    """
    serializer_class = OrderSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        # Filter by user's business
        return Order.objects.filter(
            business=self.request.user.business
        ).select_related('business', 'delivery_agent')

    @action(detail=True, methods=['post'])
    def assign_driver(self, request, pk=None):
        """Custom action: POST /api/v1/orders/{id}/assign_driver/"""
        order = self.get_object()
        driver_id = request.data.get('driver_id')
        # ... assignment logic
        return Response({'status': 'assigned'})
```

### Serializer Patterns
```python
from rest_framework import serializers

class OrderSerializer(serializers.ModelSerializer):
    """Order serializer with nested relations."""

    business_name = serializers.CharField(source='business.name', read_only=True)
    items = OrderItemSerializer(many=True, read_only=True)

    class Meta:
        model = Order
        fields = [
            'id', 'order_number', 'status', 'business_name',
            'customer_name', 'customer_phone', 'delivery_address',
            'total_amount', 'cod_amount', 'items', 'created_at'
        ]
        read_only_fields = ['id', 'order_number', 'created_at']

    def validate_cod_amount(self, value):
        if value < 0:
            raise serializers.ValidationError("COD amount cannot be negative")
        return value
```

### Webhook Handler Pattern
```python
from rest_framework.views import APIView
from rest_framework.response import Response
import hmac
import hashlib

class ShopifyWebhookView(APIView):
    """Handle Shopify order webhooks."""

    authentication_classes = []  # Webhook uses HMAC verification
    permission_classes = []

    def post(self, request):
        # Verify webhook signature
        if not self._verify_shopify_webhook(request):
            return Response({'error': 'Invalid signature'}, status=401)

        topic = request.headers.get('X-Shopify-Topic')

        if topic == 'orders/create':
            self._handle_order_create(request.data)
        elif topic == 'orders/updated':
            self._handle_order_update(request.data)

        return Response({'status': 'received'})

    def _verify_shopify_webhook(self, request):
        hmac_header = request.headers.get('X-Shopify-Hmac-SHA256')
        secret = settings.SHOPIFY_WEBHOOK_SECRET
        computed = hmac.new(
            secret.encode(),
            request.body,
            hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(computed, hmac_header)
```

## API Response Standards

### Success Response
```json
{
    "status": "success",
    "data": {
        "id": 123,
        "order_number": "EZ-2025-001234"
    }
}
```

### Error Response
```json
{
    "status": "error",
    "message": "Order not found",
    "code": "ORDER_NOT_FOUND",
    "details": {}
}
```

### Pagination
```json
{
    "count": 100,
    "next": "https://ezzydelivery.qa/api/v1/orders/?page=2",
    "previous": null,
    "results": [...]
}
```

## External Integrations

### ShipDay DMS
- Sync orders to ShipDay for driver dispatch
- Receive delivery status updates
- Location: `ezzy_api/shipday/`

### Shopify
- Receive new order webhooks
- Update order fulfillment status
- Location: `ezzy_api/shopify/`

### WooCommerce
- Order import via REST API
- Status sync back to WooCommerce
- Location: `ezzy_api/woocommerce/`

## Testing APIs

### Using curl
```bash
# Get auth token
curl -X POST https://ezzydelivery.qa/api/v1/auth/token/ \
  -d "username=user&password=pass"

# List orders
curl -H "Authorization: Token <token>" \
  https://ezzydelivery.qa/api/v1/orders/

# Create order
curl -X POST -H "Authorization: Token <token>" \
  -H "Content-Type: application/json" \
  -d '{"customer_name": "John", "delivery_address": "Doha"}' \
  https://ezzydelivery.qa/api/v1/orders/
```

### Using Django Tests
```python
from rest_framework.test import APITestCase, APIClient

class OrderAPITest(APITestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(...)
        self.client.force_authenticate(user=self.user)

    def test_list_orders(self):
        response = self.client.get('/api/v1/orders/')
        self.assertEqual(response.status_code, 200)
```

## Rate Limiting

```python
from django_ratelimit.decorators import ratelimit

@ratelimit(key='ip', rate='100/h', method='ALL')
def api_view(request):
    ...
```

## API Documentation

API documentation is auto-generated using DRF's built-in schema:
- Browsable API: `/api/v1/` (when authenticated)
- Schema: `/api/v1/schema/`
