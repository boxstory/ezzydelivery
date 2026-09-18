# Purpose: Tests for the exchange delivery leg and what it pays the driver.
# Used by: manage.py test delivery.tests_exchange_leg
# Notes: driver_fee() and fee_expr() are twins — a branch in one and not the other means the
#        payout queue prices a delivery differently from the task page showing it.

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from business import models as business_models
from core import models as core_models
from delivery import models as delivery_models
from delivery.earnings import FALLBACK_CARD, driver_fee, fee_expr, resolve_card
from fleet import models as fleet_models
from orders import models as orders_models
from orders import services

User = get_user_model()

_SEQ = [9900]


def _fixtures(order_type='normal_delivery', dl_amount=Decimal('60.00')):
    _SEQ[0] += 1
    idx = _SEQ[0]

    biz_user = User.objects.create_user(username=f'ex_biz_{idx}', password='x')
    biz_profile = core_models.Profile.objects.create(
        user=biz_user, first_name='E', last_name='X', phone=91000000 + idx)
    business = business_models.Business.objects.create(
        business_id=idx, user=biz_user, profile=biz_profile,
        business_name=f'Exch Biz {idx}', business_code=f'EX{idx}',
        business_status='active')
    pickup = business_models.PickupLocation.objects.create(
        business=business, pickup_location_title='Main', locality='Doha')
    order = orders_models.Order.objects.create(
        business=business, client_order_code=f'EX-ORD-{idx}',
        customer_name='C', customer_phone='1', customer_address='Z',
        cod_amount=Decimal('200.00'), dl_amount=dl_amount, order_type=order_type,
        pickup_location=pickup, order_status='delivered')
    staff = User.objects.create_user(
        username=f'ex_staff_{idx}', password='x', is_staff=True)
    return business, order, staff


def _card(normal='10.00', exchange='25.00'):
    return fleet_models.DeliveryPayRate.objects.create(
        normal_fee=Decimal(normal), hub_fee=Decimal('10.00'),
        pick_and_drop_percent=Decimal('80.00'), exchange_fee=Decimal(exchange),
        effective_from=timezone.now().date() - timezone.timedelta(days=30))


def _task(order, business, leg='single', price=Decimal('60.00')):
    return delivery_models.DeliveryTask.objects.create(
        dl_task_number=f'EX-T-{order.id}-{leg}', order=order, business=business,
        dl_task_status='delivered', dl_price=price, task_leg=leg,
        dl_task_date=timezone.now().date())


class ExchangeFeeTests(TestCase):
    def test_an_exchange_pays_its_own_rate(self):
        business, order, _ = _fixtures()
        _card(normal='10.00', exchange='25.00')
        self.assertEqual(driver_fee(_task(order, business, 'exchange')), Decimal('25.00'))

    def test_a_normal_leg_is_unaffected(self):
        business, order, _ = _fixtures()
        _card(normal='10.00', exchange='25.00')
        self.assertEqual(driver_fee(_task(order, business, 'single')), Decimal('10.00'))

    def test_exchange_beats_the_pick_and_drop_percentage(self):
        """A replacement carries no delivery charge, so a percentage of it is zero."""
        business, order, _ = _fixtures(order_type='pick_and_drop', dl_amount=Decimal('0.00'))
        _card(normal='10.00', exchange='25.00')
        task = _task(order, business, 'exchange', price=Decimal('0.00'))
        self.assertEqual(driver_fee(task), Decimal('25.00'))

    def test_a_card_without_the_field_falls_back_to_the_normal_fee(self):
        """Cards written before the leg existed must keep pricing as they did."""
        from delivery.earnings import RateCard

        card = RateCard('12.00', '10.00', '80.00')
        self.assertEqual(card.exchange_fee, Decimal('12.00'))

    def test_the_builtin_fallback_pays_an_exchange(self):
        self.assertEqual(FALLBACK_CARD.exchange_fee, Decimal('10.00'))
        self.assertGreater(FALLBACK_CARD.exchange_fee, Decimal('0.00'))

    def test_sql_twin_agrees_with_the_python_resolver(self):
        """fee_expr() and driver_fee() must never drift."""
        business, order, _ = _fixtures()
        _card(normal='10.00', exchange='25.00')
        for leg in ('single', 'exchange', 'hub_delivery'):
            task = _task(order, business, leg)
            annotated = delivery_models.DeliveryTask.objects.filter(
                pk=task.pk).annotate(fee=fee_expr()).first()
            self.assertEqual(
                annotated.fee.quantize(Decimal('0.01')), driver_fee(task),
                f'{leg}: SQL and Python disagree')


class ExchangeLegWiringTests(TestCase):
    def test_collect_back_publishes_an_exchange_leg(self):
        _, order, staff = _fixtures()
        new = services.create_replacement_order(
            order, reason='size_exchange', collect_back=True, user=staff, publish=True)
        self.assertEqual(new.delivery_task.first().task_leg, 'exchange')

    def test_a_plain_replacement_stays_a_single_leg(self):
        _, order, staff = _fixtures()
        new = services.create_replacement_order(
            order, reason='damaged', collect_back=False, user=staff, publish=True)
        self.assertEqual(new.delivery_task.first().task_leg, 'single')

    def test_an_unpublished_replacement_has_no_leg_yet(self):
        _, order, staff = _fixtures()
        new = services.create_replacement_order(
            order, reason='damaged', collect_back=True, user=staff)
        self.assertEqual(new.delivery_task.count(), 0)
        self.assertTrue(new.collect_back)

    def test_a_pick_and_drop_exchange_keeps_both_writes(self):
        """The client-side zero must not clobber the leg the signal set.

        These come from two different places — the leg from the task-creation
        signal, the zeroed charge from a later update in create_replacement_order
        — so this asserts the second write leaves the first intact.
        """
        _, order, staff = _fixtures(order_type='pick_and_drop', dl_amount=Decimal('60.00'))
        new = services.create_replacement_order(
            order, reason='size_exchange', collect_back=True, user=staff, publish=True)
        task = new.delivery_task.first()
        self.assertEqual(task.task_leg, 'exchange')
        self.assertEqual(task.verified_delivery_charge, Decimal('0.00'))
        self.assertEqual(task.dl_price, Decimal('60.00'))


class ExchangeBannerTests(TestCase):
    """The driver has to know to leave with the original, or the trip is wasted."""

    def _driver_with_task(self, leg):
        business, order, _ = _fixtures()
        idx = _SEQ[0]
        drv_user = User.objects.create_user(username=f'ex_drv_{idx}', password='x')
        # driver_tasks is gated by @driver_required, which reads Profile.is_driver.
        drv_profile = core_models.Profile.objects.create(
            user=drv_user, first_name='E', last_name='D', phone=93000000 + idx,
            is_driver=True)
        driver = fleet_models.Driver.objects.create(
            driver_id=idx, user=drv_user, profile=drv_profile,
            driver_code=f'ED{idx}', driver_phone='2', driver_whatsapp='2',
            driver_languages='english', driver_license_number=f'L{idx}',
            driver_status='approved', cod_in_hand=Decimal('0.00'))
        task = delivery_models.DeliveryTask.objects.create(
            dl_task_number=f'EX-B-{idx}', order=order, business=business,
            driver=driver, dl_task_status='accepted', task_leg=leg,
            dl_task_publish=True,
            dl_price=Decimal('0.00'), dl_task_date=timezone.now().date())
        return drv_user, task

    def _render(self, user):
        from django.test import override_settings

        with override_settings(DRIVER_DEVICE_ENFORCEMENT=False):
            self.client.force_login(user)
            return self.client.get('/fleet/tasks/', secure=True)

    def test_an_exchange_task_shows_the_collect_back_banner(self):
        user, _ = self._driver_with_task('exchange')
        resp = self._render(user)
        self.assertEqual(resp.status_code, 200, f'redirected to {resp.get("Location")}')
        body = resp.content.decode()
        self.assertIn('task-card__exchange', body)
        self.assertIn('collect the old item', body)

    def test_a_normal_task_shows_no_banner(self):
        user, _ = self._driver_with_task('single')
        resp = self._render(user)
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn('task-card__exchange', resp.content.decode())
