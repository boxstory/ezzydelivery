"""
Purpose: Verify the bulk Add Order table saves the pasted/dropped shared-location pin.
Used by: `python manage.py test orders.tests_bulk_location`
Notes: Exercises the real POST to orders:add_order_bulk, including a bad-coordinate row.
"""
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from business import models as business_models
from orders import models as orders_models


class BulkOrderLocationTests(TestCase):
    """The per-row location cell must land on Order.latitude/longitude."""

    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            username='bulkloc', email='bulkloc@example.com', password='pw-test-123')
        self.business = business_models.Business.objects.create(
            business_id=9911, business_name='Bulk Loc Biz', business_code='BLOC1',
            business_status='active', user=self.user)
        self.client.force_login(self.user)

    def _post(self, row):
        payload = {f'orders[0][{k}]': v for k, v in row.items()}
        return self.client.post(reverse('orders:add_order_bulk'), payload)

    def test_pin_is_saved(self):
        self._post({
            'customer_name': 'Pin Customer',
            'latitude': '25.286106',
            'longitude': '51.531040',
            'coords_accuracy': 'by_customer',
        })
        order = orders_models.Order.objects.get(customer_name='Pin Customer')
        self.assertEqual(float(order.latitude), 25.286106)
        self.assertEqual(float(order.longitude), 51.531040)
        self.assertEqual(order.coords_accuracy, 'by_customer')

    def test_blank_pin_leaves_coords_empty(self):
        self._post({
            'customer_name': 'No Pin Customer',
            'latitude': '',
            'longitude': '',
            'coords_accuracy': '',
        })
        order = orders_models.Order.objects.get(customer_name='No Pin Customer')
        self.assertIsNone(order.latitude)
        self.assertIsNone(order.longitude)

    def test_out_of_range_pin_is_dropped(self):
        self._post({
            'customer_name': 'Bad Pin Customer',
            'latitude': '999',
            'longitude': '51.531040',
            'coords_accuracy': 'by_customer',
        })
        order = orders_models.Order.objects.get(customer_name='Bad Pin Customer')
        self.assertIsNone(order.latitude)
        self.assertIsNone(order.longitude)
        self.assertIsNone(order.coords_accuracy)

    def test_forged_accuracy_is_normalised(self):
        self._post({
            'customer_name': 'Forged Accuracy',
            'latitude': '25.286106',
            'longitude': '51.531040',
            'coords_accuracy': 'not-a-choice',
        })
        order = orders_models.Order.objects.get(customer_name='Forged Accuracy')
        self.assertEqual(order.coords_accuracy, 'by_customer')
