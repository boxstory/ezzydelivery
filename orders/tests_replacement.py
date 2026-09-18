# Purpose: Tests for building a replacement order (orders/services.py).
# Used by: manage.py test orders.tests_replacement
# Notes: Two regressions are load-bearing here — a pick & drop replacement must still pay the
#        driver, and publishing one must go through apply_ready_and_publish so the goods are
#        actually reserved and picked up.

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from business import models as business_models
from core import models as core_models
from delivery import models as delivery_models
from fleet import models as fleet_models
from orders import models as orders_models
from orders import services

User = get_user_model()

_SEQ = [8400]


def _fixtures(order_type='normal_delivery', order_status='delivered',
              dl_amount=Decimal('25.00'), with_items=True):
    _SEQ[0] += 1
    idx = _SEQ[0]

    biz_user = User.objects.create_user(username=f'rpl_biz_{idx}', password='x')
    biz_profile = core_models.Profile.objects.create(
        user=biz_user, first_name='R', last_name='B', phone=51000000 + idx)
    business = business_models.Business.objects.create(
        business_id=idx, user=biz_user, profile=biz_profile,
        business_name=f'Repl Biz {idx}', business_code=f'RPL{idx}',
        business_status='active')
    pickup = business_models.PickupLocation.objects.create(
        business=business, pickup_location_title='Main', locality='Doha')
    order = orders_models.Order.objects.create(
        business=business, client_order_code=f'RPL-ORD-{idx}',
        customer_name='Customer', customer_phone='5551', customer_address='Doha',
        cod_amount=Decimal('200.00'), dl_amount=dl_amount, order_type=order_type,
        pickup_location=pickup, order_status=order_status)
    if with_items:
        orders_models.OrderItem.objects.create(
            order=order, quantity=2, unit_price=Decimal('100.00'))
    staff = User.objects.create_user(
        username=f'rpl_staff_{idx}', password='x', is_staff=True)
    return business, order, staff


def _paid_rate_card():
    """A fleet-wide pay card so driver_fee() is not resolving a fallback."""
    return fleet_models.DeliveryPayRate.objects.create(
        normal_fee=Decimal('10.00'), hub_fee=Decimal('10.00'),
        pick_and_drop_percent=Decimal('80.00'),
        effective_from=timezone.now().date() - timezone.timedelta(days=30))


class CanReplaceTests(TestCase):
    def test_delivered_order_is_eligible(self):
        _, order, _ = _fixtures(order_status='delivered')
        self.assertTrue(services.can_replace(order)[0])

    def test_legacy_fulfilled_status_is_eligible(self):
        """'fulfilled' was dropped from the choices without a data migration."""
        _, order, _ = _fixtures(order_status='fulfilled')
        self.assertTrue(services.can_replace(order)[0])

    def test_cancelled_order_is_refused(self):
        _, order, _ = _fixtures(order_status='cancelled')
        ok, why = services.can_replace(order)
        self.assertFalse(ok)
        self.assertIn('cancelled', why.lower())

    def test_undelivered_order_is_refused(self):
        _, order, _ = _fixtures(order_status='to_review')
        self.assertFalse(services.can_replace(order)[0])

    def test_failed_task_makes_an_undelivered_order_eligible(self):
        business, order, _ = _fixtures(order_status='publish')
        delivery_models.DeliveryTask.objects.create(
            dl_task_number=f'RPL-F-{order.id}', order=order, business=business,
            dl_task_status='failed')
        self.assertTrue(services.can_replace(order)[0])

    def test_partial_delivery_makes_an_order_eligible(self):
        business, order, _ = _fixtures(order_status='publish')
        delivery_models.DeliveryTask.objects.create(
            dl_task_number=f'RPL-P-{order.id}', order=order, business=business,
            dl_task_status='partial_delivery')
        self.assertTrue(services.can_replace(order)[0])

    def test_chain_is_capped(self):
        _, order, staff = _fixtures()
        first = services.create_replacement_order(order, reason='damaged', user=staff)
        first.order_status = 'delivered'
        first.save(update_fields=['order_status'])
        second = services.create_replacement_order(first, reason='damaged', user=staff)
        second.order_status = 'delivered'
        second.save(update_fields=['order_status'])

        self.assertEqual(second.replacement_depth, 2)
        ok, why = services.can_replace(second)
        self.assertFalse(ok)
        with self.assertRaises(ValidationError):
            services.create_replacement_order(second, reason='damaged', user=staff)


class SettlementTests(TestCase):
    def test_even_exchange_collects_nothing(self):
        _, order, staff = _fixtures()
        new = services.create_replacement_order(order, reason='size_exchange', user=staff)
        self.assertEqual(new.cod_amount, Decimal('0.00'))
        self.assertEqual(new.cod_status_by_client, 'online_paid')

    def test_collect_extra_lands_on_cod_amount(self):
        _, order, staff = _fixtures()
        new = services.create_replacement_order(
            order, reason='size_exchange', collect_amount=Decimal('50.00'), user=staff)
        self.assertEqual(new.cod_amount, Decimal('50.00'))
        self.assertEqual(new.cod_status_by_client, 'pending')

    def test_a_refund_is_never_a_negative_cod(self):
        _, order, staff = _fixtures()
        with self.assertRaises(ValidationError):
            services.create_replacement_order(
                order, reason='damaged', collect_amount=Decimal('-30.00'), user=staff)

    def test_item_prices_do_not_set_the_settlement(self):
        """Items total 200; the replacement still collects only what staff typed."""
        _, order, staff = _fixtures()
        new = services.create_replacement_order(order, reason='damaged', user=staff)
        self.assertEqual(new.cod_amount, Decimal('0.00'))

    def test_order_with_no_items_replaces_normally(self):
        _, order, staff = _fixtures(with_items=False)
        new = services.create_replacement_order(order, reason='lost', user=staff)
        self.assertEqual(new.order_items.count(), 0)
        self.assertEqual(new.replaces_id, order.id)

    def test_bad_reason_is_refused(self):
        _, order, staff = _fixtures()
        with self.assertRaises(ValidationError):
            services.create_replacement_order(order, reason='because', user=staff)


class LinkAndCodeTests(TestCase):
    def test_link_is_queryable_both_ways(self):
        _, order, staff = _fixtures()
        new = services.create_replacement_order(order, reason='wrong_item', user=staff)
        self.assertEqual(new.replaces_id, order.id)
        self.assertTrue(new.is_replacement)
        self.assertEqual(order.replacements.count(), 1)
        self.assertFalse(order.is_replacement)

    def test_code_is_derived_from_the_sellers_own(self):
        _, order, staff = _fixtures()
        new = services.create_replacement_order(order, reason='damaged', user=staff)
        self.assertEqual(new.client_order_code, f'{order.client_order_code}-R1')

    def test_second_replacement_increments_the_suffix(self):
        _, order, staff = _fixtures()
        services.create_replacement_order(order, reason='damaged', user=staff)
        second = services.create_replacement_order(order, reason='damaged', user=staff)
        self.assertEqual(second.client_order_code, f'{order.client_order_code}-R2')

    def test_code_collision_falls_back_instead_of_failing(self):
        business, order, staff = _fixtures()
        # Squat on the -R1 code this business would otherwise be given.
        orders_models.Order.objects.create(
            business=business, client_order_code=f'{order.client_order_code}-R1',
            customer_name='Squatter', customer_phone='1', customer_address='X')
        new = services.create_replacement_order(order, reason='damaged', user=staff)
        self.assertTrue(new.client_order_code.startswith('WF-'))

    def test_both_orders_get_a_comment(self):
        _, order, staff = _fixtures()
        new = services.create_replacement_order(order, reason='damaged', user=staff)
        self.assertTrue(new.order_comments.filter(body__icontains='Replacement for').exists())
        self.assertTrue(order.order_comments.filter(body__icontains=new.order_number).exists())

    def test_items_are_copied(self):
        _, order, staff = _fixtures()
        new = services.create_replacement_order(order, reason='damaged', user=staff)
        self.assertEqual(new.order_items.count(), order.order_items.count())

    def test_customer_and_pickup_are_carried_over(self):
        _, order, staff = _fixtures()
        new = services.create_replacement_order(order, reason='damaged', user=staff)
        self.assertEqual(new.customer_phone, order.customer_phone)
        self.assertEqual(new.pickup_location_id, order.pickup_location_id)
        self.assertEqual(new.order_status, 'to_review')


class DeliveryFeeTests(TestCase):
    """Trap 1: zeroing dl_amount on a pick & drop pays the driver nothing."""

    def test_normal_delivery_replacement_is_free_to_the_client(self):
        _, order, staff = _fixtures(order_type='normal_delivery', dl_amount=Decimal('25.00'))
        new = services.create_replacement_order(order, reason='damaged', user=staff)
        self.assertEqual(new.dl_amount, Decimal('0.00'))

    def test_pick_and_drop_keeps_the_fee_so_the_driver_is_paid(self):
        _, order, staff = _fixtures(order_type='pick_and_drop', dl_amount=Decimal('60.00'))
        new = services.create_replacement_order(order, reason='damaged', user=staff)
        self.assertEqual(new.dl_amount, Decimal('60.00'))

    def test_driver_is_paid_on_both_order_types(self):
        from delivery.earnings import driver_fee

        card = _paid_rate_card()
        for otype, expect in (('normal_delivery', Decimal('10.00')),
                              ('pick_and_drop', Decimal('48.00'))):
            business, order, staff = _fixtures(order_type=otype, dl_amount=Decimal('60.00'))
            new = services.create_replacement_order(order, reason='damaged', user=staff)
            task = delivery_models.DeliveryTask.objects.create(
                dl_task_number=f'RPL-E-{new.id}', order=new, business=business,
                dl_task_status='delivered', dl_price=new.dl_amount,
                dl_task_date=timezone.now().date())
            fee = driver_fee(task)
            self.assertEqual(fee, expect, f'{otype} paid {fee}')
            self.assertGreater(fee, Decimal('0.00'), f'{otype} driver paid nothing')


class PublishTests(TestCase):
    """Trap 2: publishing must walk ready_to_pickup, not jump straight to publish.

    Stock reservation and the pick list hang off the 'ready_to_pickup' branch
    (warehouse/signals.py), so a single jump would dispatch a driver to collect
    goods nobody set aside.
    """

    def test_publish_false_leaves_a_draft(self):
        _, order, staff = _fixtures()
        new = services.create_replacement_order(order, reason='damaged', user=staff)
        self.assertEqual(new.order_status, 'to_review')
        self.assertEqual(new.delivery_task.count(), 0)

    def test_publish_walks_ready_to_pickup_first(self):
        _, order, staff = _fixtures()
        new = services.create_replacement_order(
            order, reason='damaged', user=staff, publish=True)
        new.refresh_from_db()
        self.assertEqual(new.order_status, 'publish')

        written = set(
            orders_models.OrderStatusHistory.objects
            .filter(order=new, field_name='order_status')
            .values_list('new_value', flat=True))
        self.assertIn('ready_to_pickup', written,
                      'jumped straight to publish — stock never reserved')
        self.assertIn('publish', written)

    def test_publish_creates_the_delivery_task(self):
        _, order, staff = _fixtures()
        new = services.create_replacement_order(
            order, reason='damaged', user=staff, publish=True)
        self.assertGreaterEqual(new.delivery_task.count(), 1)

    def test_published_pick_and_drop_bills_the_client_nothing(self):
        """The driver keeps his percent of dl_price; the client side is zeroed."""
        _, order, staff = _fixtures(order_type='pick_and_drop', dl_amount=Decimal('60.00'))
        new = services.create_replacement_order(
            order, reason='damaged', user=staff, publish=True)
        task = new.delivery_task.first()
        self.assertEqual(task.verified_delivery_charge, Decimal('0.00'))
        self.assertEqual(task.charge_verification_status, 'verified')
        self.assertEqual(task.dl_price, Decimal('60.00'))


class BillingTests(TestCase):
    """A free replacement must not reach a client invoice, nor sit in the backlog."""

    def _delivered(self, order, business, price):
        return delivery_models.DeliveryTask.objects.create(
            dl_task_number=f'RPL-B-{order.id}', order=order, business=business,
            dl_task_status='delivered', dl_price=price,
            dl_task_date=timezone.now().date(), completed_at=timezone.now())

    def test_zero_fee_replacement_is_not_billable(self):
        from fleet.billing_service import billable_tasks

        business, order, staff = _fixtures(order_type='normal_delivery')
        new = services.create_replacement_order(order, reason='damaged', user=staff)
        task = self._delivered(new, business, new.dl_amount)
        self.assertNotIn(
            task.id, set(billable_tasks(business_id=business.pk).values_list('id', flat=True)))

    def test_a_normal_paid_delivery_is_still_billable(self):
        """Guard against the exclusion being too broad."""
        from fleet.billing_service import billable_tasks

        business, order, _ = _fixtures()
        task = self._delivered(order, business, Decimal('25.00'))
        self.assertIn(
            task.id, set(billable_tasks(business_id=business.pk).values_list('id', flat=True)))
