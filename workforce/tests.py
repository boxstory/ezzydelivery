# Purpose: Regression tests for the shared staff orders-list filter bar.
# Used by: `python manage.py test workforce`.
# Notes: fulfilled/non-fulfilled clients hand-rolled their filtering and dropped
#        the date params entirely, so the date buttons rendered but did nothing.

from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from business import models as business_models
from core import models as core_models
from orders import models as orders_models


class OrdersListDateFilterTests(TestCase):
    """The date presets in the shared filter bar must apply on every list page."""

    @classmethod
    def setUpTestData(cls):
        cls.staff = User.objects.create_user(
            username='filterstaff', email='filterstaff@example.com',
            password='pw-for-tests', is_staff=True,
        )
        # dept_operations: these are order-list pages, and StaffDepartmentMiddleware
        # fails closed — a staff user with no department is redirected away.
        core_models.Profile.objects.create(
            user=cls.staff, first_name='Filter', last_name='Staff', phone=55500111,
            is_staff=True, dept_operations=True,
        )

        cls.fulfilled_biz = cls._make_business(8801, 'Fulfilled Biz', 'FULB', 'active')
        cls.plain_biz = cls._make_business(8802, 'Plain Biz', 'PLNB', 'none')

        # One order created today, one 10 days ago, on each business.
        cls.fresh_fulfilled = cls._make_order(cls.fulfilled_biz, 'FULL-FRESH')
        cls.old_fulfilled = cls._make_order(cls.fulfilled_biz, 'FULL-OLD', days_ago=10)
        cls.fresh_plain = cls._make_order(cls.plain_biz, 'PLAIN-FRESH')
        cls.old_plain = cls._make_order(cls.plain_biz, 'PLAIN-OLD', days_ago=10)

    @classmethod
    def _make_business(cls, business_id, name, code, fulfillment_status):
        user = User.objects.create_user(
            username=f'owner{business_id}', email=f'owner{business_id}@example.com',
            password='pw-for-tests',
        )
        profile = core_models.Profile.objects.create(
            user=user, first_name=name, last_name='Owner', phone=55500000 + business_id,
        )
        return business_models.Business.objects.create(
            business_id=business_id, user=user, profile=profile,
            business_name=name, business_code=code,
            business_status='active', fulfillment_service_status=fulfillment_status,
        )

    @classmethod
    def _make_order(cls, business, code, days_ago=0):
        pickup = business_models.PickupLocation.objects.create(
            business=business, pickup_location_title=f'{code} Pickup',
            locality='Doha', pickup_zone_no=70, pickup_street_no=700,
            pickup_building_no=7000, pickup_status='active',
        )
        order = orders_models.Order.objects.create(
            business=business, client_order_code=code,
            customer_name=f'Customer {code}', customer_phone='33344455',
            customer_address='Test Address Doha',
            dl_zone=70, dl_building=7000, dl_street=700,
            pickup_location=pickup,
        )
        if days_ago:
            # created_at is auto_now_add, so it can only be moved after the fact.
            stamp = timezone.now() - timedelta(days=days_ago)
            orders_models.Order.objects.filter(pk=order.pk).update(created_at=stamp)
            order.refresh_from_db()
        return order

    def setUp(self):
        self.client.force_login(self.staff)

    def _codes(self, response):
        return {o.client_order_code for o in response.context['orders']}

    def test_fulfilled_clients_applies_today_preset(self):
        url = reverse('workforce:wf_orders_fulfilled_clients')

        unfiltered = self._codes(self.client.get(url))
        self.assertEqual(unfiltered, {'FULL-FRESH', 'FULL-OLD'})

        filtered = self._codes(self.client.get(url, {'datePreset': 'today'}))
        self.assertEqual(
            filtered, {'FULL-FRESH'},
            'the date preset must exclude the 10-day-old order',
        )

    def test_non_fulfilled_clients_applies_today_preset(self):
        url = reverse('workforce:wf_orders_non_fulfilled_clients')

        unfiltered = self._codes(self.client.get(url))
        self.assertEqual(unfiltered, {'PLAIN-FRESH', 'PLAIN-OLD'})

        filtered = self._codes(self.client.get(url, {'datePreset': 'today'}))
        self.assertEqual(filtered, {'PLAIN-FRESH'})

    def test_preset_survives_into_the_template_as_the_active_button(self):
        """Without datePreset echoed back, the pressed button loses its state."""
        response = self.client.get(
            reverse('workforce:wf_orders_fulfilled_clients'), {'datePreset': 'week'},
        )
        self.assertEqual(response.context['filters']['datePreset'], 'week')
        self.assertEqual(response.context['filters']['datePresetLabel'], 'Last Week')

    def test_business_picker_stays_scoped_to_the_page(self):
        """The helper lists every business; each page must narrow it back down."""
        fulfilled = self.client.get(reverse('workforce:wf_orders_fulfilled_clients'))
        self.assertEqual(
            [b.business_id for b in fulfilled.context['all_businesses']], [8801],
        )

        plain = self.client.get(reverse('workforce:wf_orders_non_fulfilled_clients'))
        self.assertEqual(
            [b.business_id for b in plain.context['all_businesses']], [8802],
        )

    def test_chips_show_labels_rather_than_stored_keys(self):
        response = self.client.get(
            reverse('workforce:wf_orders_fulfilled_clients'),
            {'dlTaskStatus': 'out_for_delivery'},
        )
        self.assertEqual(
            response.context['filters']['dlTaskStatusLabel'], 'Out for Delivery',
        )
