# Purpose: Tests for the client-side replacement request and the return-status permission gate.
# Used by: manage.py test business.tests_replacement_client
# Notes: The return gate is the important half — before it, a read-only Viewer could approve and
#        refund their own returns, which writes back to stock and asserts money we never paid.

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from business import models as business_models
from business.permissions import BusinessPermissions, ROLE_PERMISSIONS, TeamRoles
from core import models as core_models
from orders import models as orders_models

User = get_user_model()

_SEQ = [6400]


def _business(order_status='delivered'):
    _SEQ[0] += 1
    idx = _SEQ[0]

    owner = User.objects.create_user(username=f'cl_own_{idx}', password='x')
    owner_profile = core_models.Profile.objects.create(
        user=owner, first_name='O', last_name='W', phone=51100000 + idx)
    business = business_models.Business.objects.create(
        business_id=idx, user=owner, profile=owner_profile,
        business_name=f'Client Biz {idx}', business_code=f'CL{idx}',
        business_status='active')
    pickup = business_models.PickupLocation.objects.create(
        business=business, pickup_location_title='Main', locality='Doha')
    order = orders_models.Order.objects.create(
        business=business, client_order_code=f'CL-ORD-{idx}',
        customer_name='Customer', customer_phone='5551', customer_address='Doha',
        cod_amount=Decimal('200.00'), pickup_location=pickup,
        order_status=order_status)
    return business, order, owner, idx


def _member(business, idx, role):
    user = User.objects.create_user(username=f'cl_{role}_{idx}', password='x')
    profile = core_models.Profile.objects.create(
        user=user, first_name='T', last_name='M', phone=52100000 + idx)
    business_models.BusinessTeamProfile.objects.create(
        user=user, profile=profile, business=business,
        team_code=f'TM{idx}{role[:2]}', team_role=role,
        team_name=f'{role} member', team_phone='6666',
        team_email=f'{role}{idx}@example.com', team_status='active',
        # business_required refuses an unverified member before any permission check
        team_verifed=True)
    return user


class ReplacementPermissionTests(TestCase):
    def test_viewer_does_not_hold_the_permission(self):
        self.assertNotIn(BusinessPermissions.ORDER_REPLACE,
                         ROLE_PERMISSIONS[TeamRoles.VIEWER])

    def test_operational_roles_hold_it(self):
        for role in (TeamRoles.OWNER, TeamRoles.MANAGER, TeamRoles.STAFF):
            self.assertIn(BusinessPermissions.ORDER_REPLACE, ROLE_PERMISSIONS[role],
                          f'{role} cannot raise a replacement')

    def test_it_is_assignable_in_the_team_ui(self):
        codes = [c for c, _ in BusinessPermissions.ALL_PERMISSIONS]
        group = [c for c, _ in BusinessPermissions.PERMISSION_GROUPS['Orders']]
        self.assertIn(BusinessPermissions.ORDER_REPLACE, codes)
        self.assertIn(BusinessPermissions.ORDER_REPLACE, group)


class ClientReplacementViewTests(TestCase):
    def _post(self, order, **extra):
        payload = {'reason': 'damaged'}
        payload.update(extra)
        return self.client.post(
            reverse('business:replacement_create', args=[order.id]), payload)

    def test_owner_can_raise_a_replacement(self):
        _, order, owner, _ = _business()
        self.client.force_login(owner)
        resp = self._post(order)
        self.assertEqual(resp.status_code, 302)
        new = orders_models.Order.objects.get(replaces=order)
        self.assertEqual(new.replacement_reason, 'damaged')

    def test_the_client_path_never_publishes(self):
        """Staff confirm the goods exist before a replacement goes out."""
        _, order, owner, _ = _business()
        self.client.force_login(owner)
        self._post(order)
        new = orders_models.Order.objects.get(replaces=order)
        self.assertEqual(new.order_status, 'to_review')
        self.assertEqual(new.delivery_task.count(), 0)

    def test_the_client_cannot_make_the_customer_pay(self):
        """collect_amount is an ops decision; posting it must not take effect."""
        _, order, owner, _ = _business()
        self.client.force_login(owner)
        self._post(order, collect_amount='500.00')
        self.assertEqual(
            orders_models.Order.objects.get(replaces=order).cod_amount, Decimal('0.00'))

    def test_collect_back_is_honoured(self):
        _, order, owner, _ = _business()
        self.client.force_login(owner)
        self._post(order, collect_back='1')
        self.assertTrue(orders_models.Order.objects.get(replaces=order).collect_back)

    def test_collect_back_survives_staff_publication(self):
        """The seller's request has to reach the driver, not just the order row.

        The client path stores collect_back on a draft with no task. Only when staff
        publish it does a task exist, and if that task is born 'single' the driver
        never sees the collect-the-original banner and the round trip is paid as an
        ordinary drop — the seller's tick would have been silently discarded.
        """
        from orders.status_actions import apply_ready_and_publish

        _, order, owner, _ = _business()
        self.client.force_login(owner)
        self._post(order, collect_back='1')
        new = orders_models.Order.objects.get(replaces=order)

        apply_ready_and_publish(new, user=owner)

        task = new.delivery_task.first()
        self.assertIsNotNone(task)
        self.assertEqual(task.task_leg, 'exchange')

    def test_an_ordinary_replacement_is_not_an_exchange(self):
        """Guards the other direction: no collect_back, no round-trip pay."""
        from orders.status_actions import apply_ready_and_publish

        _, order, owner, _ = _business()
        self.client.force_login(owner)
        self._post(order)
        new = orders_models.Order.objects.get(replaces=order)

        apply_ready_and_publish(new, user=owner)

        self.assertEqual(new.delivery_task.first().task_leg, 'single')

    def test_viewer_is_refused(self):
        business, order, _, idx = _business()
        self.client.force_login(_member(business, idx, 'viewer'))
        self._post(order)
        self.assertFalse(orders_models.Order.objects.filter(replaces=order).exists())

    def test_manager_is_allowed(self):
        business, order, _, idx = _business()
        self.client.force_login(_member(business, idx, 'manager'))
        self._post(order)
        self.assertTrue(orders_models.Order.objects.filter(replaces=order).exists())

    def test_another_sellers_order_is_not_found(self):
        """The tenant boundary — an order id alone must not be enough."""
        _, mine, owner, _ = _business()
        _, theirs, _, _ = _business()
        self.client.force_login(owner)
        resp = self._post(theirs)
        self.assertEqual(resp.status_code, 404)
        self.assertFalse(orders_models.Order.objects.filter(replaces=theirs).exists())

    def test_get_is_refused(self):
        _, order, owner, _ = _business()
        self.client.force_login(owner)
        resp = self.client.get(
            reverse('business:replacement_create', args=[order.id]))
        self.assertEqual(resp.status_code, 405)

    def test_an_undelivered_order_is_refused(self):
        _, order, owner, _ = _business(order_status='to_review')
        self.client.force_login(owner)
        self._post(order)
        self.assertFalse(orders_models.Order.objects.filter(replaces=order).exists())


class ReturnStatusGateTests(TestCase):
    """Before this gate a Viewer could approve and refund their own returns."""

    def _ret(self, business, order):
        return orders_models.ReturnRequest.objects.create(
            return_number=f'RET-CL-{order.id}', order=order, business=business,
            reason='damaged', status='pending', cod_reversal_amount=Decimal('0'))

    def _post(self, ret, status):
        return self.client.post(
            reverse('business:return_update_status', args=[ret.id]),
            {'status': status})

    def test_viewer_cannot_touch_a_return_at_all(self):
        business, order, _, idx = _business()
        ret = self._ret(business, order)
        self.client.force_login(_member(business, idx, 'viewer'))
        self._post(ret, 'approved')
        ret.refresh_from_db()
        self.assertEqual(ret.status, 'pending')

    def test_a_seller_may_decide_their_own_goods_are_coming_back(self):
        """Approving is the seller's call — it writes to their own stock, not our money."""
        business, order, owner, _ = _business()
        ret = self._ret(business, order)
        self.client.force_login(owner)
        self._post(ret, 'approved')
        ret.refresh_from_db()
        self.assertEqual(ret.status, 'approved')

    def test_an_owner_cannot_declare_their_own_refund(self):
        business, order, owner, _ = _business()
        ret = self._ret(business, order)
        self.client.force_login(owner)
        self._post(ret, 'refunded')
        ret.refresh_from_db()
        self.assertEqual(ret.status, 'pending', 'seller recorded a refund we never paid')

    def test_approving_still_writes_back_the_returned_quantity(self):
        """The existing behaviour must survive the new gate."""
        business, order, owner, _ = _business()
        item = orders_models.OrderItem.objects.create(
            order=order, quantity=5, unit_price=Decimal('10.00'))
        ret = self._ret(business, order)
        orders_models.ReturnItem.objects.create(
            return_request=ret, order_item=item, quantity_returned=3)
        self.client.force_login(owner)
        self._post(ret, 'approved')
        item.refresh_from_db()
        self.assertEqual(item.quantity_returned, 3)
        self.assertEqual(item.delivery_status, 'partial')

    def test_a_seller_may_still_move_it_through_handling_steps(self):
        business, order, owner, _ = _business()
        ret = self._ret(business, order)
        self.client.force_login(owner)
        self._post(ret, 'pickup_scheduled')
        ret.refresh_from_db()
        self.assertEqual(ret.status, 'pickup_scheduled')

    def test_a_viewer_cannot_even_move_it_through_handling(self):
        """The permission gate covers every write, not just the money one."""
        business, order, _, idx = _business()
        ret = self._ret(business, order)
        self.client.force_login(_member(business, idx, 'viewer'))
        self._post(ret, 'pickup_scheduled')
        ret.refresh_from_db()
        self.assertEqual(ret.status, 'pending')

    def test_a_manager_may_decide_a_return(self):
        business, order, _, idx = _business()
        ret = self._ret(business, order)
        self.client.force_login(_member(business, idx, 'manager'))
        self._post(ret, 'approved')
        ret.refresh_from_db()
        self.assertEqual(ret.status, 'approved')
