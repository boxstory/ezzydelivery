# Purpose: Tests for the staff "Send Replacement" endpoint (workforce:create_replacement_order).
# Used by: manage.py test workforce.tests_replacement_view
# Notes: The departments registration test is not cosmetic — the middleware fails closed, so an
#        unregistered workforce URL is unreachable by everyone, super admins included.

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from business import models as business_models
from core import departments
from core import models as core_models
from orders import models as orders_models

User = get_user_model()

_SEQ = [9600]


def _fixtures(order_status='delivered'):
    _SEQ[0] += 1
    idx = _SEQ[0]

    biz_user = User.objects.create_user(username=f'rv_biz_{idx}', password='x')
    biz_profile = core_models.Profile.objects.create(
        user=biz_user, first_name='V', last_name='B', phone=61000000 + idx)
    business = business_models.Business.objects.create(
        business_id=idx, user=biz_user, profile=biz_profile,
        business_name=f'View Biz {idx}', business_code=f'VW{idx}',
        business_status='active')
    pickup = business_models.PickupLocation.objects.create(
        business=business, pickup_location_title='Main', locality='Doha')
    order = orders_models.Order.objects.create(
        business=business, client_order_code=f'VW-ORD-{idx}',
        customer_name='Customer', customer_phone='5551', customer_address='Doha',
        cod_amount=Decimal('200.00'), pickup_location=pickup,
        order_status=order_status)
    staff = User.objects.create_user(
        username=f'rv_staff_{idx}', password='x', is_staff=True, is_superuser=True)
    return business, order, staff


class ReplacementRouteTests(TestCase):
    def test_url_is_registered_with_a_department(self):
        """An unregistered workforce URL fails closed for everyone."""
        self.assertTrue(departments.departments_for('create_replacement_order'),
                        'create_replacement_order is not in core/departments.py — '
                        'the middleware will refuse it for every user')

    def test_staff_can_create_a_replacement(self):
        _, order, staff = _fixtures()
        self.client.force_login(staff)
        resp = self.client.post(
            reverse('workforce:create_replacement_order', args=[order.id]),
            {'reason': 'damaged'})
        self.assertEqual(resp.status_code, 302)

        new = orders_models.Order.objects.get(replaces=order)
        self.assertEqual(new.replacement_reason, 'damaged')
        self.assertEqual(new.cod_amount, Decimal('0.00'))
        self.assertEqual(resp.url, reverse('workforce:order_detail', args=[new.id]))

    def test_collect_amount_is_carried_through(self):
        _, order, staff = _fixtures()
        self.client.force_login(staff)
        self.client.post(
            reverse('workforce:create_replacement_order', args=[order.id]),
            {'reason': 'size_exchange', 'collect_amount': '50.00'})
        new = orders_models.Order.objects.get(replaces=order)
        self.assertEqual(new.cod_amount, Decimal('50.00'))
        self.assertEqual(new.cod_status_by_client, 'pending')

    def test_collect_back_flag_is_carried_through(self):
        _, order, staff = _fixtures()
        self.client.force_login(staff)
        self.client.post(
            reverse('workforce:create_replacement_order', args=[order.id]),
            {'reason': 'wrong_item', 'collect_back': '1'})
        self.assertTrue(orders_models.Order.objects.get(replaces=order).collect_back)

    def test_get_is_refused(self):
        """duplicate_order next door is a GET; this one must not be."""
        _, order, staff = _fixtures()
        self.client.force_login(staff)
        resp = self.client.get(
            reverse('workforce:create_replacement_order', args=[order.id]))
        self.assertEqual(resp.status_code, 405)

    def test_anonymous_is_redirected_to_login(self):
        _, order, _ = _fixtures()
        resp = self.client.post(
            reverse('workforce:create_replacement_order', args=[order.id]),
            {'reason': 'damaged'})
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/accounts/login/', resp.url)
        self.assertFalse(orders_models.Order.objects.filter(replaces=order).exists())

    def test_non_staff_cannot_create_one(self):
        _, order, _ = _fixtures()
        shopper = User.objects.create_user(username='rv_shopper', password='x')
        self.client.force_login(shopper)
        self.client.post(
            reverse('workforce:create_replacement_order', args=[order.id]),
            {'reason': 'damaged'})
        self.assertFalse(orders_models.Order.objects.filter(replaces=order).exists())

    def test_ineligible_order_returns_the_reason_as_json(self):
        _, order, staff = _fixtures(order_status='cancelled')
        self.client.force_login(staff)
        resp = self.client.post(
            reverse('workforce:create_replacement_order', args=[order.id]),
            {'reason': 'damaged'}, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(resp.json()['success'])
        self.assertIn('cancelled', resp.json()['error'].lower())

    def test_bad_reason_is_refused(self):
        _, order, staff = _fixtures()
        self.client.force_login(staff)
        resp = self.client.post(
            reverse('workforce:create_replacement_order', args=[order.id]),
            {'reason': 'whatever'}, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(orders_models.Order.objects.filter(replaces=order).exists())

    def test_ajax_success_returns_the_redirect_target(self):
        _, order, staff = _fixtures()
        self.client.force_login(staff)
        resp = self.client.post(
            reverse('workforce:create_replacement_order', args=[order.id]),
            {'reason': 'lost'}, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(resp.status_code, 200)
        payload = resp.json()
        new = orders_models.Order.objects.get(replaces=order)
        self.assertTrue(payload['success'])
        self.assertEqual(payload['order_id'], new.id)
        self.assertEqual(payload['redirect'],
                         reverse('workforce:order_detail', args=[new.id]))

    def test_an_impossible_refund_is_reported_not_silently_dropped(self):
        """No COD was ever collected here, so there is nothing to hand back.

        The replacement is still created — the goods have to go out either way —
        but the response has to say plainly that the money did not move.
        """
        _, order, staff = _fixtures()
        self.client.force_login(staff)
        resp = self.client.post(
            reverse('workforce:create_replacement_order', args=[order.id]),
            {'reason': 'damaged', 'refund_amount': '50.00'},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        message = resp.json()['message']
        self.assertIn('did NOT go through', message)
        self.assertIn('still refundable', message)
        self.assertTrue(orders_models.Order.objects.filter(replaces=order).exists())
