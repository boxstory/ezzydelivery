# EzzyDelivery Testing Skill

## Test Structure

```
ezzydelivery/
├── core/tests/
│   ├── test_models.py
│   ├── test_views.py
│   └── test_forms.py
├── orders/tests/
├── business/tests/
├── fleet/tests/
├── delivery/tests/
└── ezzy_api/tests/
```

## Running Tests

### All Tests
```bash
source ../venvezzy/bin/activate
python manage.py test
```

### Specific App
```bash
python manage.py test orders
python manage.py test orders.tests.test_models
python manage.py test orders.tests.test_models.OrderModelTest
python manage.py test orders.tests.test_models.OrderModelTest.test_create_order
```

### With Verbosity
```bash
python manage.py test -v 2  # More output
python manage.py test -v 3  # Maximum verbosity
```

### Keep Test Database
```bash
python manage.py test --keepdb  # Faster subsequent runs
```

### Parallel Tests
```bash
python manage.py test --parallel  # Use multiple CPU cores
```

## Test Patterns

### Model Tests
```python
from django.test import TestCase
from orders.models import Order
from business.models import Business

class OrderModelTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        """Set up data for all test methods."""
        cls.business = Business.objects.create(name='Test Business')

    def setUp(self):
        """Set up data for each test method."""
        self.order = Order.objects.create(
            business=self.business,
            customer_name='Test Customer',
            delivery_address='Test Address, Doha'
        )

    def test_order_creation(self):
        """Test order is created correctly."""
        self.assertEqual(self.order.customer_name, 'Test Customer')
        self.assertEqual(self.order.business, self.business)

    def test_order_str(self):
        """Test order string representation."""
        self.assertIn('EZ-', str(self.order))

    def test_order_status_default(self):
        """Test default status is pending."""
        self.assertEqual(self.order.status, 'pending')

    def test_cod_amount_cannot_be_negative(self):
        """Test COD validation."""
        with self.assertRaises(ValidationError):
            order = Order(cod_amount=-100)
            order.full_clean()
```

### View Tests
```python
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model

User = get_user_model()

class OrderViewTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        self.client.login(username='testuser', password='testpass123')

    def test_order_list_view(self):
        """Test order list page loads."""
        response = self.client.get(reverse('orders:list'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'orders/order_list.html')

    def test_order_list_requires_login(self):
        """Test unauthenticated access redirects."""
        self.client.logout()
        response = self.client.get(reverse('orders:list'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('login', response.url)

    def test_order_create_view_post(self):
        """Test creating order via POST."""
        data = {
            'customer_name': 'New Customer',
            'delivery_address': 'Doha, Qatar',
            'cod_amount': 100
        }
        response = self.client.post(reverse('orders:create'), data)
        self.assertEqual(response.status_code, 302)  # Redirect on success
        self.assertTrue(Order.objects.filter(customer_name='New Customer').exists())
```

### API Tests
```python
from rest_framework.test import APITestCase, APIClient
from rest_framework import status

class OrderAPITest(APITestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username='apiuser',
            password='apipass123'
        )
        self.client.force_authenticate(user=self.user)

    def test_list_orders(self):
        """Test GET /api/v1/orders/"""
        response = self.client.get('/api/v1/orders/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_create_order(self):
        """Test POST /api/v1/orders/"""
        data = {
            'customer_name': 'API Customer',
            'delivery_address': 'Lusail, Qatar'
        }
        response = self.client.post('/api/v1/orders/', data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_unauthorized_access(self):
        """Test API requires authentication."""
        self.client.force_authenticate(user=None)
        response = self.client.get('/api/v1/orders/')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
```

### Form Tests
```python
from django.test import TestCase
from orders.forms import OrderForm

class OrderFormTest(TestCase):
    def test_valid_form(self):
        """Test form with valid data."""
        data = {
            'customer_name': 'Test Customer',
            'customer_phone': '+97412345678',
            'delivery_address': 'Doha, Qatar'
        }
        form = OrderForm(data=data)
        self.assertTrue(form.is_valid())

    def test_invalid_phone(self):
        """Test form with invalid phone."""
        data = {
            'customer_name': 'Test',
            'customer_phone': 'invalid',
            'delivery_address': 'Doha'
        }
        form = OrderForm(data=data)
        self.assertFalse(form.is_valid())
        self.assertIn('customer_phone', form.errors)
```

## Test Fixtures

### Using Factory Boy (Recommended)
```python
import factory
from orders.models import Order
from business.models import Business

class BusinessFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Business

    name = factory.Sequence(lambda n: f'Business {n}')
    email = factory.LazyAttribute(lambda o: f'{o.name.lower()}@test.com')

class OrderFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Order

    business = factory.SubFactory(BusinessFactory)
    customer_name = factory.Faker('name')
    delivery_address = factory.Faker('address')

# Usage in tests
def test_with_factory(self):
    order = OrderFactory()  # Creates with all dependencies
    orders = OrderFactory.create_batch(10)  # Create 10 orders
```

### Using JSON Fixtures
```bash
# Export data
python manage.py dumpdata orders --indent 2 > orders/fixtures/test_orders.json

# Load in tests
class OrderTest(TestCase):
    fixtures = ['test_orders.json']
```

## Coverage

### Run with Coverage
```bash
pip install coverage

# Run tests with coverage
coverage run manage.py test

# Generate report
coverage report -m

# HTML report
coverage html
open htmlcov/index.html
```

### Coverage Configuration (.coveragerc)
```ini
[run]
source = .
omit =
    */migrations/*
    */tests/*
    manage.py
    */settings/*

[report]
exclude_lines =
    pragma: no cover
    def __repr__
    raise NotImplementedError
```

## Mocking

```python
from unittest.mock import patch, MagicMock

class ExternalAPITest(TestCase):
    @patch('ezzy_api.shipday.client.ShipDayClient.create_order')
    def test_shipday_integration(self, mock_create):
        """Test ShipDay API call is made."""
        mock_create.return_value = {'id': 12345}

        # Code that calls ShipDay
        result = sync_order_to_shipday(self.order)

        mock_create.assert_called_once()
        self.assertEqual(result['id'], 12345)
```

## Continuous Integration

Tests run automatically on push. Ensure:
1. All tests pass locally before pushing
2. No print statements in tests
3. Tests are independent (no order dependency)
4. Clean up test data in tearDown if needed
