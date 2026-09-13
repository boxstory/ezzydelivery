# Purpose: The rules behind driver pay settings — rate card resolution, its SQL twin, and manual bonus/deduction lines.
# Used by: manage.py test fleet.tests_pay
# Notes: The SQL twin is asserted against the Python resolver row by row, because the two used to be
#        separate copies of the fee rule and drifted. Deduction sign is asserted too: stored positive,
#        the wallet and the payout would both pay the driver extra.

from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from business.models import Business
from core.models import Profile
from delivery.earnings import (
    FALLBACK_CARD, CardResolver, driver_fee, fee_expr, rate_rows, resolve_card,
)
from delivery.models import DeliveryTask
from fleet.models import DeliveryPayRate, Driver, DriverSettlement, DriverTransaction
from orders.models import Order

User = get_user_model()


class PayTestBase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='pay-driver', password='x')
        self.driver = Driver.objects.create(
            driver_id=9101, user=self.user, driver_code='PAYTEST',
            driver_status='approved',
        )
        self.other_user = User.objects.create_user(username='pay-driver-2', password='x')
        self.other = Driver.objects.create(
            driver_id=9102, user=self.other_user, driver_code='PAYTEST2',
            driver_status='approved',
        )
        self.business = Business.objects.create(business_id=9101, business_name='Pay Test Co')
        self._seq = 0

    def _task(self, day=date(2026, 9, 4), driver=None, leg='single',
              order_type='normal_delivery', price='20.00'):
        self._seq += 1
        order = Order.objects.create(
            order_number=f'PAYTEST-{self._seq:04d}',
            business=self.business,
            client_order_code=f'P{self._seq:04d}',
            order_type=order_type,
        )
        return DeliveryTask.objects.create(
            order=order,
            driver=driver or self.driver,
            dl_task_date=day,
            dl_task_status='delivered',
            task_leg=leg,
            dl_price=Decimal(price),
        )

    def _card(self, driver=None, normal='12.00', hub='8.00', percent='75.00',
              start=date(2026, 1, 1), end=None):
        return DeliveryPayRate.objects.create(
            driver=driver,
            normal_fee=Decimal(normal), hub_fee=Decimal(hub),
            pick_and_drop_percent=Decimal(percent),
            effective_from=start, effective_to=end,
        )


class RateResolutionTests(PayTestBase):
    """Which card prices a delivery."""

    def test_empty_table_pays_the_old_hardcoded_figures(self):
        # The whole point of the fallback: removing the hardcoded rule must not
        # change what anyone is paid until staff actually set a card.
        self.assertTrue(resolve_card(self.driver.driver_id).is_fallback)
        self.assertEqual(driver_fee(self._task()), Decimal('10.00'))
        self.assertEqual(driver_fee(self._task(leg='hub_delivery')), Decimal('10.00'))
        self.assertEqual(
            driver_fee(self._task(order_type='pick_and_drop', price='50.00')),
            Decimal('40.00'))

    def test_fleet_card_is_found(self):
        # Regression: filtering the fleet card with driver_id__in=[None] renders
        # `IN (NULL)`, which matches nothing — every driver silently fell through
        # to the fallback while a fleet card sat in the table.
        self._card()
        card = resolve_card(self.driver.driver_id, date(2026, 9, 4))
        self.assertEqual(card.source, 'fleet')
        self.assertEqual(card.normal_fee, Decimal('12.00'))

    def test_driver_card_beats_fleet_card(self):
        self._card()
        self._card(driver=self.driver, normal='15.00', start=date(2026, 6, 1))
        self.assertEqual(
            resolve_card(self.driver.driver_id, date(2026, 9, 4)).normal_fee,
            Decimal('15.00'))
        # ...and only for that driver.
        self.assertEqual(
            resolve_card(self.other.driver_id, date(2026, 9, 4)).normal_fee,
            Decimal('12.00'))

    def test_cards_are_day_precise(self):
        self._card(driver=self.driver, normal='15.00', start=date(2026, 6, 1))
        self._card(normal='12.00', start=date(2026, 1, 1))
        # The day before the override starts, the fleet card still prices it.
        self.assertEqual(
            resolve_card(self.driver.driver_id, date(2026, 5, 31)).normal_fee,
            Decimal('12.00'))
        self.assertEqual(
            resolve_card(self.driver.driver_id, date(2026, 6, 1)).normal_fee,
            Decimal('15.00'))

    def test_ended_card_stops_pricing(self):
        self._card(normal='12.00', start=date(2026, 1, 1), end=date(2026, 6, 30))
        self.assertEqual(resolve_card(None, date(2026, 6, 30)).normal_fee, Decimal('12.00'))
        self.assertTrue(resolve_card(None, date(2026, 7, 1)).is_fallback)

    def test_each_delivery_is_priced_on_its_own_date(self):
        self._card(normal='12.00', start=date(2026, 1, 1))
        self._card(driver=self.driver, normal='15.00', start=date(2026, 6, 1))
        march = self._task(day=date(2026, 3, 1))
        august = self._task(day=date(2026, 8, 1))
        self.assertEqual(driver_fee(march), Decimal('12.00'))
        self.assertEqual(driver_fee(august), Decimal('15.00'))

    def test_pick_and_drop_uses_the_percentage(self):
        self._card(percent='75.00')
        task = self._task(order_type='pick_and_drop', price='50.00')
        self.assertEqual(driver_fee(task), Decimal('37.50'))

    def test_hub_leg_uses_the_hub_fee(self):
        self._card(hub='8.00')
        self.assertEqual(driver_fee(self._task(leg='hub_delivery')), Decimal('8.00'))

    def test_model_method_delegates(self):
        self._card(normal='12.00')
        self.assertEqual(self._task().calculate_driver_earnings(), Decimal('12.00'))

    def test_card_resolver_matches_one_by_one_resolution(self):
        self._card(normal='12.00', start=date(2026, 1, 1))
        self._card(driver=self.driver, normal='15.00', start=date(2026, 6, 1))
        tasks = [self._task(day=date(2026, 3, 1)), self._task(day=date(2026, 8, 1)),
                 self._task(day=date(2026, 8, 1), driver=self.other)]
        resolver = CardResolver({t.driver_id for t in tasks})
        for task in tasks:
            self.assertEqual(driver_fee(task, resolver.for_task(task)), driver_fee(task))


class FeeExpressionTests(PayTestBase):
    """The SQL twin has to agree with the Python resolver, row for row."""

    def _assert_agrees(self, tasks):
        rows = rate_rows()
        resolver = CardResolver({t.driver_id for t in tasks})
        expected = {t.id: driver_fee(t, resolver.for_task(t)) for t in tasks}
        annotated = (DeliveryTask.objects
                     .filter(id__in=list(expected))
                     .annotate(fee=fee_expr(rows, include_verified=False)))
        self.assertEqual(annotated.count(), len(expected))
        for row in annotated:
            self.assertEqual(row.fee, expected[row.id], f'task {row.id}')

    def test_agrees_with_no_cards(self):
        self._assert_agrees([
            self._task(),
            self._task(leg='hub_delivery'),
            self._task(order_type='pick_and_drop', price='50.00'),
        ])

    def test_agrees_with_a_fleet_card(self):
        self._card()
        self._assert_agrees([
            self._task(),
            self._task(leg='hub_delivery'),
            self._task(order_type='pick_and_drop', price='50.00'),
        ])

    def test_agrees_across_a_mid_range_rate_change(self):
        # The case the old single-date expression got wrong: a queue that spans
        # the day a card started was tallied entirely at the newer rate.
        self._card(normal='12.00', start=date(2026, 1, 1))
        self._card(driver=self.driver, normal='15.00', hub='9.00', percent='85.00',
                   start=date(2026, 6, 1))
        self._assert_agrees([
            self._task(day=date(2026, 3, 1)),
            self._task(day=date(2026, 8, 1)),
            self._task(day=date(2026, 8, 1), leg='hub_delivery'),
            self._task(day=date(2026, 8, 1), order_type='pick_and_drop', price='50.00'),
            self._task(day=date(2026, 8, 1), driver=self.other),
            self._task(day=date(2025, 1, 1)),   # before any card exists
        ])

    def test_verified_earnings_wins_when_asked_for(self):
        task = self._task()
        task.verified_earnings = Decimal('33.00')
        task.save(update_fields=['verified_earnings'])
        row = (DeliveryTask.objects.filter(id=task.id)
               .annotate(fee=fee_expr(rate_rows())).first())
        self.assertEqual(row.fee, Decimal('33.00'))


class StaffConsoleTests(PayTestBase):
    """The pages themselves — a view that renders is not a view that works."""

    def setUp(self):
        super().setUp()
        self.staff = User.objects.create_user(
            username='pay-staff', password='x', is_staff=True, is_superuser=True)
        profile, _ = Profile.objects.get_or_create(user=self.staff)
        profile.is_staff = True
        profile.is_superadmin = True
        profile.save()
        self.client.force_login(self.staff)

    # --- rate cards ---------------------------------------------------------

    def test_register_renders_with_no_cards(self):
        response = self.client.get(reverse('workforce:pay_rate_register'))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['using_fallback'])

    def test_saving_a_fleet_card_changes_what_a_delivery_pays(self):
        task = self._task()
        self.assertEqual(task.calculate_driver_earnings(), Decimal('10.00'))
        response = self.client.post(reverse('workforce:pay_rate_save'), {
            'normal_fee': '14.00', 'hub_fee': '9.50',
            'pick_and_drop_percent': '70', 'effective_from': '2026-01-01',
        }, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(DeliveryPayRate.objects.count(), 1)
        self.assertEqual(task.calculate_driver_earnings(), Decimal('14.00'))

    def test_second_open_card_for_one_scope_is_refused(self):
        self._card()
        self.client.post(reverse('workforce:pay_rate_save'), {
            'normal_fee': '14.00', 'hub_fee': '9.50',
            'pick_and_drop_percent': '70', 'effective_from': '2026-02-01',
        })
        self.assertEqual(DeliveryPayRate.objects.count(), 1)

    def test_percentage_over_100_is_refused(self):
        self.client.post(reverse('workforce:pay_rate_save'), {
            'normal_fee': '14.00', 'hub_fee': '9.50',
            'pick_and_drop_percent': '140', 'effective_from': '2026-01-01',
        })
        self.assertEqual(DeliveryPayRate.objects.count(), 0)

    def test_ending_a_card_reopens_the_scope(self):
        card = self._card()
        self.client.post(reverse('workforce:pay_rate_end', args=[card.id]),
                         {'effective_to': '2026-06-30'})
        card.refresh_from_db()
        self.assertEqual(card.effective_to, date(2026, 6, 30))
        self.assertTrue(resolve_card(None, date(2026, 7, 1)).is_fallback)

    def test_card_cannot_end_before_it_started(self):
        card = self._card(start=date(2026, 6, 1))
        self.client.post(reverse('workforce:pay_rate_end', args=[card.id]),
                         {'effective_to': '2026-01-01'})
        card.refresh_from_db()
        self.assertIsNone(card.effective_to)

    # --- replacing a running card -------------------------------------------

    def test_replace_closes_the_running_card_the_day_before(self):
        # The reason the flow exists: "change what a delivery pays" without
        # having to end a card by hand first, and with no day priced twice.
        old_card = self._card(start=date(2026, 1, 1), normal='12.00')
        self.client.post(reverse('workforce:pay_rate_save'), {
            'normal_fee': '18.00', 'hub_fee': '9.50',
            'pick_and_drop_percent': '70', 'effective_from': '2026-03-01',
            'replace': '1',
        })
        old_card.refresh_from_db()
        self.assertEqual(old_card.effective_to, date(2026, 2, 28))
        self.assertEqual(DeliveryPayRate.objects.count(), 2)
        self.assertEqual(resolve_card(None, date(2026, 2, 28)).normal_fee, Decimal('12.00'))
        self.assertEqual(resolve_card(None, date(2026, 3, 1)).normal_fee, Decimal('18.00'))

    def test_replacing_a_card_that_starts_the_same_day_removes_it(self):
        # It would otherwise be left covering no days at all.
        self._card(start=date(2026, 4, 1), normal='12.00')
        self.client.post(reverse('workforce:pay_rate_save'), {
            'normal_fee': '18.00', 'hub_fee': '9.50',
            'pick_and_drop_percent': '70', 'effective_from': '2026-04-01',
            'replace': '1',
        })
        self.assertEqual(DeliveryPayRate.objects.count(), 1)
        self.assertEqual(resolve_card(None, date(2026, 4, 1)).normal_fee, Decimal('18.00'))

    def test_replace_will_not_back_date_around_a_later_card(self):
        self._card(start=date(2026, 6, 1), normal='12.00')
        self.client.post(reverse('workforce:pay_rate_save'), {
            'normal_fee': '18.00', 'hub_fee': '9.50',
            'pick_and_drop_percent': '70', 'effective_from': '2026-05-01',
            'replace': '1',
        })
        self.assertEqual(DeliveryPayRate.objects.count(), 1)
        self.assertEqual(resolve_card(None, date(2026, 6, 1)).normal_fee, Decimal('12.00'))

    def test_replace_only_touches_its_own_scope(self):
        fleet_card = self._card(start=date(2026, 1, 1), normal='12.00')
        self.client.post(reverse('workforce:pay_rate_save'), {
            'driver_id': self.driver.driver_id,
            'normal_fee': '20.00', 'hub_fee': '9.50',
            'pick_and_drop_percent': '70', 'effective_from': '2026-03-01',
            'replace': '1',
        })
        fleet_card.refresh_from_db()
        self.assertIsNone(fleet_card.effective_to)
        self.assertEqual(
            resolve_card(self.driver.driver_id, date(2026, 3, 1)).normal_fee,
            Decimal('20.00'))

    # --- deleting a card ----------------------------------------------------

    def test_a_card_that_priced_nothing_can_be_deleted(self):
        card = self._card(driver=self.driver, start=date(2026, 1, 1))
        self.client.post(reverse('workforce:pay_rate_delete', args=[card.id]))
        self.assertFalse(DeliveryPayRate.objects.filter(id=card.id).exists())

    def test_a_card_that_priced_a_delivery_cannot_be_deleted(self):
        card = self._card(driver=self.driver, start=date(2026, 1, 1))
        self._task(day=date(2026, 9, 4), driver=self.driver)
        self.client.post(reverse('workforce:pay_rate_delete', args=[card.id]))
        self.assertTrue(DeliveryPayRate.objects.filter(id=card.id).exists())

    def test_a_delivery_outside_the_window_does_not_protect_a_card(self):
        card = self._card(driver=self.driver, start=date(2026, 1, 1),
                          end=date(2026, 1, 31))
        self._task(day=date(2026, 9, 4), driver=self.driver)
        self.client.post(reverse('workforce:pay_rate_delete', args=[card.id]))
        self.assertFalse(DeliveryPayRate.objects.filter(id=card.id).exists())

    def test_another_drivers_delivery_does_not_protect_a_driver_card(self):
        card = self._card(driver=self.driver, start=date(2026, 1, 1))
        self._task(day=date(2026, 9, 4), driver=self.other)
        self.client.post(reverse('workforce:pay_rate_delete', args=[card.id]))
        self.assertFalse(DeliveryPayRate.objects.filter(id=card.id).exists())

    # --- bonus / deduction --------------------------------------------------

    def _earn(self, amount='100.00'):
        return DriverTransaction.objects.create(
            driver=self.driver, transaction_type='earning', amount=Decimal(amount),
            description='delivery')

    def test_bonus_is_recorded_positive_and_becomes_payable(self):
        response = self.client.post(
            reverse('workforce:driver_adjustment_add', args=[self.driver.driver_id]),
            {'kind': 'bonus', 'amount': '75.00', 'description': 'Ramadan incentive'},
            follow=True)
        self.assertEqual(response.status_code, 200)
        txn = DriverTransaction.objects.get(transaction_type='bonus')
        self.assertEqual(txn.amount, Decimal('75.00'))
        self.assertIsNone(txn.settlement)

    def test_deduction_is_stored_negative(self):
        # The wallet sums adjustments raw and the payout takes abs(); a positive
        # deduction would pay the driver the fine instead of withholding it.
        self._earn('100.00')
        self.client.post(
            reverse('workforce:driver_adjustment_add', args=[self.driver.driver_id]),
            {'kind': 'deduction', 'amount': '30.00', 'description': 'Traffic fine'})
        txn = DriverTransaction.objects.get(transaction_type='deduction')
        self.assertEqual(txn.amount, Decimal('-30.00'))

    def test_deduction_beyond_what_is_unpaid_is_refused(self):
        self._earn('20.00')
        self.client.post(
            reverse('workforce:driver_adjustment_add', args=[self.driver.driver_id]),
            {'kind': 'deduction', 'amount': '500.00', 'description': 'Too much'})
        self.assertFalse(DriverTransaction.objects.filter(transaction_type='deduction').exists())

    def test_a_reason_is_required(self):
        self.client.post(
            reverse('workforce:driver_adjustment_add', args=[self.driver.driver_id]),
            {'kind': 'bonus', 'amount': '75.00', 'description': '   '})
        self.assertFalse(DriverTransaction.objects.filter(transaction_type='bonus').exists())

    def test_cod_types_cannot_be_entered_by_hand(self):
        self.client.post(
            reverse('workforce:driver_adjustment_add', args=[self.driver.driver_id]),
            {'kind': 'cod_collection', 'amount': '75.00', 'description': 'nope'})
        self.assertFalse(
            DriverTransaction.objects.filter(transaction_type='cod_collection').exists())

    def test_unpaid_line_can_be_removed(self):
        self.client.post(
            reverse('workforce:driver_adjustment_add', args=[self.driver.driver_id]),
            {'kind': 'bonus', 'amount': '75.00', 'description': 'typo'})
        txn = DriverTransaction.objects.get(transaction_type='bonus')
        self.client.post(reverse('workforce:driver_adjustment_remove', args=[txn.id]))
        self.assertFalse(DriverTransaction.objects.filter(id=txn.id).exists())

    def test_paid_line_cannot_be_removed(self):
        self.client.post(
            reverse('workforce:driver_adjustment_add', args=[self.driver.driver_id]),
            {'kind': 'bonus', 'amount': '75.00', 'description': 'already paid'})
        txn = DriverTransaction.objects.get(transaction_type='bonus')
        settlement = DriverSettlement.objects.create(
            driver=self.driver, settlement_code='STL-PAYTEST',
            period_start=date(2026, 9, 1), period_end=date(2026, 9, 30),
            gross_earnings=Decimal('0'), bonuses=Decimal('75.00'),
            deductions=Decimal('0'), net_amount=Decimal('75.00'), status='paid')
        DriverTransaction.objects.filter(id=txn.id).update(settlement=settlement)
        self.client.post(reverse('workforce:driver_adjustment_remove', args=[txn.id]))
        self.assertTrue(DriverTransaction.objects.filter(id=txn.id).exists())

    def test_bonus_reaches_the_payout_worksheet(self):
        self.client.post(
            reverse('workforce:driver_adjustment_add', args=[self.driver.driver_id]),
            {'kind': 'bonus', 'amount': '75.00', 'description': 'Ramadan incentive'})
        response = self.client.get(
            reverse('workforce:driver_payout_worksheet', args=[self.driver.driver_id]))
        self.assertEqual(response.status_code, 200)
        kinds = [l.transaction_type for l in response.context['payable_lines']]
        self.assertIn('bonus', kinds)
        self.assertEqual(response.context['earnings_total'], Decimal('75.00'))
