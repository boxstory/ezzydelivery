---
description: Run tests and check code quality
---

# Testing Mode

You are now in testing mode for the EzzyDelivery project. Reference `.claude/skills/testing.md` for detailed patterns.

## Quick Commands

### Run Tests
```bash
source ../venvezzy/bin/activate

# All tests
python manage.py test

# Specific app
python manage.py test orders
python manage.py test business
python manage.py test fleet

# Specific test class
python manage.py test orders.tests.test_models.OrderModelTest

# With verbosity
python manage.py test -v 2

# Keep database (faster)
python manage.py test --keepdb

# Parallel execution
python manage.py test --parallel
```

### Code Quality Checks
```bash
# Django system check
python manage.py check

# Deployment readiness
python manage.py check --deploy

# Check for security issues
pip-audit
```

### Coverage
```bash
# Run with coverage
coverage run manage.py test

# View report
coverage report -m

# HTML report
coverage html
```

## Test Structure

| App | Test Location |
|-----|---------------|
| core | `core/tests/` |
| orders | `orders/tests/` |
| business | `business/tests/` |
| fleet | `fleet/tests/` |
| delivery | `delivery/tests/` |
| ezzy_api | `ezzy_api/tests/` |

## Common Test Patterns

### Model Test
```python
def test_order_creation(self):
    order = Order.objects.create(...)
    self.assertEqual(order.status, 'pending')
```

### View Test
```python
def test_order_list_view(self):
    response = self.client.get(reverse('orders:list'))
    self.assertEqual(response.status_code, 200)
```

### API Test
```python
def test_api_list_orders(self):
    response = self.client.get('/api/v1/orders/')
    self.assertEqual(response.status_code, 200)
```

What would you like to test?
