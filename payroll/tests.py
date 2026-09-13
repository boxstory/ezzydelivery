# Purpose: The rules that decide whether a delivery is paid for by salary or by the per-delivery leg.
# Used by: manage.py test payroll
# Notes: The absorption rule moves real money, so the target boundary, the mid-month rate change and
#        the re-publish case are all asserted rather than assumed.

from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from business.models import Business
from delivery.models import DeliveryTask
from fleet.models import Driver
from orders.models import Order
from payroll.models import (
    SalaryCoveredTask, SalaryRun, SalarySlip, SalaryStructure, month_start,
)
from payroll.services import absorb_delivery, active_structure, build_run

User = get_user_model()


class SalaryTestBase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='payroll-staff', password='x')
        # driver_id is a manual primary key on Driver, not an autofield.
        self.driver = Driver.objects.create(
            driver_id=9001, user=self.user, driver_code='SALTEST',
        )
        self.business = Business.objects.create(business_id=9001, business_name='Salary Test Co')
        self._seq = 0

    def _task(self, day):
        # DeliveryTask.order is NOT NULL, so every task needs a real order behind it.
        self._seq += 1
        order = Order.objects.create(
            order_number=f'SALTEST-{self._seq:04d}',
            business=self.business,
            client_order_code=f'C{self._seq:04d}',
        )
        return DeliveryTask.objects.create(
            order=order,
            driver=self.driver,
            dl_task_date=day,
            dl_task_status='delivered',
        )

    def _structure(self, amount='2500.00', target=100, start=date(2026, 9, 1), end=None):
        return SalaryStructure.objects.create(
            driver=self.driver,
            monthly_amount=Decimal(amount),
            delivery_target=target,
            effective_from=start,
            effective_to=end,
        )


class AbsorptionTests(SalaryTestBase):
    """Which deliveries the salary pays for."""

    def test_no_structure_means_per_delivery(self):
        self.assertFalse(absorb_delivery(self._task(date(2026, 9, 4))))
        self.assertEqual(SalaryCoveredTask.objects.count(), 0)

    def test_within_target_is_absorbed(self):
        self._structure(target=3)
        for _ in range(3):
            self.assertTrue(absorb_delivery(self._task(date(2026, 9, 4))))
        self.assertEqual(SalaryCoveredTask.objects.count(), 3)

    def test_past_target_falls_back_to_per_delivery(self):
        self._structure(target=2)
        self.assertTrue(absorb_delivery(self._task(date(2026, 9, 4))))
        self.assertTrue(absorb_delivery(self._task(date(2026, 9, 5))))
        # The third delivery is beyond what the salary bought.
        self.assertFalse(absorb_delivery(self._task(date(2026, 9, 6))))
        self.assertEqual(SalaryCoveredTask.objects.count(), 2)

    def test_zero_target_absorbs_everything(self):
        self._structure(target=0)
        for _ in range(5):
            self.assertTrue(absorb_delivery(self._task(date(2026, 9, 4))))
        self.assertEqual(SalaryCoveredTask.objects.count(), 5)

    def test_republish_does_not_consume_a_second_slot(self):
        self._structure(target=1)
        task = self._task(date(2026, 9, 4))
        self.assertTrue(absorb_delivery(task))
        # Same task again: still covered, but it must not eat the next driver's slot.
        self.assertTrue(absorb_delivery(task))
        self.assertEqual(SalaryCoveredTask.objects.count(), 1)
        self.assertFalse(absorb_delivery(self._task(date(2026, 9, 5))))

    def test_target_resets_each_month(self):
        self._structure(target=1, start=date(2026, 8, 1))
        self.assertTrue(absorb_delivery(self._task(date(2026, 8, 10))))
        self.assertFalse(absorb_delivery(self._task(date(2026, 8, 11))))
        # September is a fresh month, so the target is available again.
        self.assertTrue(absorb_delivery(self._task(date(2026, 9, 1))))

    def test_delivery_before_the_agreement_starts_is_per_delivery(self):
        self._structure(target=10, start=date(2026, 9, 1))
        self.assertFalse(absorb_delivery(self._task(date(2026, 8, 20))))

    def test_delivery_after_the_agreement_ends_is_per_delivery(self):
        self._structure(target=10, start=date(2026, 7, 1), end=date(2026, 8, 31))
        self.assertTrue(absorb_delivery(self._task(date(2026, 8, 4))))
        self.assertFalse(absorb_delivery(self._task(date(2026, 9, 4))))

    def test_latest_agreement_wins_on_a_rate_change(self):
        self._structure(amount='2000.00', target=5, start=date(2026, 7, 1), end=date(2026, 8, 31))
        newer = self._structure(amount='3000.00', target=50, start=date(2026, 9, 1))
        self.assertEqual(active_structure(self.driver, date(2026, 9, 1)), newer)


class RunTests(SalaryTestBase):
    """Building and paying a month."""

    def test_run_draws_one_slip_per_salaried_driver(self):
        self._structure(amount='2500.00', target=100)
        run, added = build_run(date(2026, 9, 1), user=self.user)
        self.assertEqual(added, 1)
        slip = SalarySlip.objects.get(run=run, driver=self.driver)
        self.assertEqual(slip.base_amount, Decimal('2500.00'))
        self.assertEqual(slip.net_amount, Decimal('2500.00'))
        self.assertEqual(slip.delivery_target, 100)

    def test_rebuilding_a_month_is_safe(self):
        self._structure()
        run, first = build_run(date(2026, 9, 1))
        slip = SalarySlip.objects.get(run=run)
        slip.base_amount = Decimal('1.00')
        slip.save(update_fields=['base_amount'])

        run2, second = build_run(date(2026, 9, 1))
        self.assertEqual(run2.pk, run.pk)
        self.assertEqual(second, 0)
        slip.refresh_from_db()
        # The edited slip survives — a re-run must never quietly reset money.
        self.assertEqual(slip.base_amount, Decimal('1.00'))
        self.assertEqual(SalarySlip.objects.count(), 1)

    def test_a_driver_whose_salary_ended_gets_no_slip(self):
        self._structure(start=date(2026, 7, 1), end=date(2026, 8, 31))
        _run, added = build_run(date(2026, 9, 1))
        self.assertEqual(added, 0)

    def test_deductions_drive_the_net(self):
        self._structure(amount='2500.00')
        run, _ = build_run(date(2026, 9, 1))
        slip = SalarySlip.objects.get(run=run)
        slip.deduction_lines.create(label='Advance', amount=Decimal('400.00'))
        slip.deduction_lines.create(label='Fine', amount=Decimal('100.00'))
        slip.recalculate()
        self.assertEqual(slip.deductions_total, Decimal('500.00'))
        self.assertEqual(slip.net_amount, Decimal('2000.00'))

    def test_slip_reports_the_delivery_position(self):
        self._structure(target=2)
        absorb_delivery(self._task(date(2026, 9, 4)))
        absorb_delivery(self._task(date(2026, 9, 5)))
        run, _ = build_run(date(2026, 9, 1))
        slip = SalarySlip.objects.get(run=run)
        self.assertEqual(slip.deliveries_covered, 2)
        self.assertEqual(slip.delivery_target, 2)

    def test_month_start_keys_every_period(self):
        self.assertEqual(month_start(date(2026, 9, 23)), date(2026, 9, 1))


class PublishBranchTests(SalaryTestBase):
    """The publish step is where salary actually changes what a driver is paid."""

    def setUp(self):
        super().setUp()
        # Super admins bypass the department middleware, so the test exercises the
        # money branch rather than the access gate (that is tests_departments' job).
        self.staff = User.objects.create_superuser(
            username='payroll-admin', email='p@example.com', password='x')
        self.client.force_login(self.staff)

    def _publish(self, tasks):
        return self.client.post(
            '/workforce/fleet/earnings-verification/action/',
            {'action': 'publish', 'task_ids[]': [str(t.id) for t in tasks]},
            secure=True,
        )

    def test_salary_suppresses_the_earning_up_to_the_target(self):
        from fleet.models import DriverTransaction
        self._structure(target=1)
        covered_task = self._task(date(2026, 9, 4))
        spill_task = self._task(date(2026, 9, 5))

        response = self._publish([covered_task, spill_task])
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body['success'])
        self.assertEqual(body['salary_covered'], 1)

        # The first delivery is paid for by the salary — no wallet credit.
        self.assertFalse(
            DriverTransaction.objects.filter(
                delivery_task=covered_task, transaction_type='earning').exists())
        # The second is past the target, so it earns normally: the incentive tier.
        self.assertTrue(
            DriverTransaction.objects.filter(
                delivery_task=spill_task, transaction_type='earning').exists())
        self.assertEqual(SalaryCoveredTask.objects.count(), 1)

    def test_a_driver_with_no_salary_still_earns_every_delivery(self):
        from fleet.models import DriverTransaction
        tasks = [self._task(date(2026, 9, 4)), self._task(date(2026, 9, 5))]
        body = self._publish(tasks).json()
        self.assertEqual(body['salary_covered'], 0)
        self.assertEqual(
            DriverTransaction.objects.filter(transaction_type='earning').count(), 2)


class HybridPayoutTests(SalaryTestBase):
    """A salaried driver past their target is paid on the ordinary per-delivery leg.

    The two documents must not overlap: the slip pays the base, the payout invoice
    pays the incentive, and no delivery is ever on both.
    """

    def setUp(self):
        super().setUp()
        self.staff = User.objects.create_superuser(
            username='payroll-admin2', email='p2@example.com', password='x')
        self.client.force_login(self.staff)

    def test_incentive_becomes_an_ordinary_payable_line(self):
        from fleet.models import DriverTransaction
        self._structure(target=1)
        covered = self._task(date(2026, 9, 4))
        incentive = self._task(date(2026, 9, 5))

        self.client.post(
            '/workforce/fleet/earnings-verification/action/',
            {'action': 'publish', 'task_ids[]': [str(covered.id), str(incentive.id)]},
            secure=True,
        )

        # Exactly one payable line, unsettled, ready for the payout desk.
        payable = DriverTransaction.objects.filter(
            driver=self.driver, transaction_type__in=['earning', 'bonus'],
            settlement__isnull=True,
        )
        self.assertEqual(payable.count(), 1)
        self.assertEqual(payable.first().delivery_task_id, incentive.id)

        # And the covered one is on the salary side only — never on both.
        self.assertTrue(SalaryCoveredTask.objects.filter(task=covered).exists())
        self.assertFalse(SalaryCoveredTask.objects.filter(task=incentive).exists())


class ApprovalGateTests(SalaryTestBase):
    """Only an approved driver can be put on a payroll.

    A `pending` Driver row is an application, not somebody who works here — 571 of
    586 rows on production are applicants. Putting one on salary would invent an
    employee.
    """

    def setUp(self):
        super().setUp()
        self.staff = User.objects.create_superuser(
            username='payroll-admin3', email='p3@example.com', password='x')
        self.client.force_login(self.staff)
        self.driver.driver_status = 'approved'
        self.driver.save(update_fields=['driver_status'])
        self.applicant = Driver.objects.create(
            driver_id=9002,
            user=User.objects.create_user(username='applicant', password='x'),
            driver_code='APPLICANT',
            driver_status='pending',
        )

    def _start_salary(self, driver):
        return self.client.post(
            '/workforce/fleet/salary/structure/save/',
            {'driver_id': str(driver.driver_id), 'monthly_amount': '2500',
             'delivery_target': '100', 'effective_from': '2026-09-01'},
            secure=True, follow=True,
        )

    def test_an_applicant_cannot_be_put_on_salary(self):
        self._start_salary(self.applicant)
        self.assertFalse(
            SalaryStructure.objects.filter(driver=self.applicant).exists())

    def test_an_approved_driver_can(self):
        self._start_salary(self.driver)
        self.assertTrue(SalaryStructure.objects.filter(driver=self.driver).exists())

    def test_the_picker_offers_approved_drivers_only(self):
        response = self.client.get('/workforce/fleet/salary/', secure=True)
        offered = {d.driver_id for d in response.context['candidates']}
        self.assertIn(self.driver.driver_id, offered)
        self.assertNotIn(self.applicant.driver_id, offered)


class MidMonthAgreementTests(SalaryTestBase):
    """Agreements are day-precise.

    Resolved against the month start instead, a salary ending on the 10th kept
    absorbing deliveries to the 30th, and one starting on the 15th absorbed nothing
    all month and drew no slip at all.
    """

    def test_a_salary_starting_mid_month_covers_only_from_that_day(self):
        self._structure(target=50, start=date(2026, 9, 15))
        self.assertFalse(absorb_delivery(self._task(date(2026, 9, 10))))
        self.assertTrue(absorb_delivery(self._task(date(2026, 9, 20))))

    def test_a_salary_ending_mid_month_stops_on_that_day(self):
        self._structure(target=50, start=date(2026, 9, 1), end=date(2026, 9, 10))
        self.assertTrue(absorb_delivery(self._task(date(2026, 9, 4))))
        self.assertFalse(absorb_delivery(self._task(date(2026, 9, 25))))

    def test_a_mid_month_start_still_earns_a_slip(self):
        self._structure(amount='2500.00', target=50, start=date(2026, 9, 16))
        run, added = build_run(date(2026, 9, 1))
        self.assertEqual(added, 1)
        slip = SalarySlip.objects.get(run=run)
        # Not pro-rated by design — paid in full, but the part month is recorded.
        self.assertEqual(slip.base_amount, Decimal('2500.00'))
        self.assertEqual(slip.covered_from, date(2026, 9, 16))
        self.assertEqual(slip.covered_to, date(2026, 9, 30))
        self.assertTrue(slip.is_partial_period)

    def test_a_whole_month_is_not_flagged_partial(self):
        self._structure(start=date(2026, 8, 1))
        run, _ = build_run(date(2026, 9, 1))
        self.assertFalse(SalarySlip.objects.get(run=run).is_partial_period)


class AbsorptionOrderTests(SalaryTestBase):
    """A salary absorbs a driver's deliveries oldest-first within the month."""

    def setUp(self):
        super().setUp()
        self.staff = User.objects.create_superuser(
            username='payroll-order', email='o@example.com', password='x')
        self.client.force_login(self.staff)

    def test_publishing_newest_first_still_absorbs_the_oldest(self):
        from fleet.models import DriverTransaction
        self._structure(target=1)
        oldest = self._task(date(2026, 9, 4))
        newest = self._task(date(2026, 9, 25))

        # Posted newest-first, exactly as the queue renders and the browser posts.
        self.client.post(
            '/workforce/fleet/earnings-verification/action/',
            {'action': 'publish', 'task_ids[]': [str(newest.id), str(oldest.id)]},
            secure=True,
        )
        self.assertTrue(SalaryCoveredTask.objects.filter(task=oldest).exists())
        self.assertFalse(SalaryCoveredTask.objects.filter(task=newest).exists())
        self.assertTrue(DriverTransaction.objects.filter(
            delivery_task=newest, transaction_type='earning').exists())


class PreviewTests(SalaryTestBase):
    """The preview must be read-only and must agree with what publish then does."""

    def setUp(self):
        super().setUp()
        self.staff = User.objects.create_superuser(
            username='payroll-preview', email='pv@example.com', password='x')
        self.client.force_login(self.staff)

    def test_preview_writes_nothing(self):
        from payroll.services import preview_absorption
        self._structure(target=5)
        tasks = [self._task(date(2026, 9, d)) for d in (4, 5, 6)]
        preview_absorption(tasks)
        self.assertEqual(SalaryCoveredTask.objects.count(), 0)

    def test_preview_marks_the_oldest_up_to_the_target(self):
        from payroll.services import preview_absorption
        self._structure(target=2)
        tasks = [self._task(date(2026, 9, d)) for d in (4, 5, 6, 7)]
        covered = preview_absorption(tasks)
        self.assertEqual({t.id for t in tasks[:2]}, set(covered))

    def test_preview_matches_what_publish_does(self):
        from payroll.services import preview_absorption
        self._structure(target=2)
        tasks = [self._task(date(2026, 9, d)) for d in (4, 5, 6, 7)]
        predicted = set(preview_absorption(tasks))

        self.client.post(
            '/workforce/fleet/earnings-verification/action/',
            {'action': 'publish', 'task_ids[]': [str(t.id) for t in reversed(tasks)]},
            secure=True,
        )
        actual = set(SalaryCoveredTask.objects.values_list('task_id', flat=True))
        self.assertEqual(predicted, actual)

    def test_no_structure_previews_nothing(self):
        from payroll.services import preview_absorption
        self.assertEqual(preview_absorption([self._task(date(2026, 9, 4))]), {})


class DeductionCeilingTests(SalaryTestBase):
    """Deductions are capped by the running total, not per line."""

    def setUp(self):
        super().setUp()
        self.staff = User.objects.create_superuser(
            username='payroll-ded', email='d@example.com', password='x')
        self.client.force_login(self.staff)
        self._structure(amount='2500.00')
        self.run, _ = build_run(date(2026, 9, 1))
        self.slip = SalarySlip.objects.get(run=self.run)

    def _deduct(self, label, amount):
        return self.client.post(
            f'/workforce/fleet/salary/slip/{self.slip.id}/deduction/',
            {'label': label, 'amount': amount}, secure=True, follow=True)

    def test_deductions_cannot_be_pushed_past_the_salary(self):
        self._deduct('Advance', '900')
        self._deduct('Fine', '900')
        self._deduct('Fuel', '900')   # would net -200 and strand the slip
        self.slip.refresh_from_db()
        self.assertEqual(self.slip.deductions_total, Decimal('1800.00'))
        self.assertGreater(self.slip.net_amount, Decimal('0.00'))


class BonusLineTests(SalaryTestBase):
    """Bonus lines pay on top of the salary and widen the room for deductions."""

    def setUp(self):
        super().setUp()
        self.staff = User.objects.create_superuser(
            username='payroll-bonus', email='b@example.com', password='x')
        self.client.force_login(self.staff)
        self._structure(amount='2500.00')
        self.run, _ = build_run(date(2026, 9, 1))
        self.slip = SalarySlip.objects.get(run=self.run)

    def _bonus(self, label, amount):
        return self.client.post(
            f'/workforce/fleet/salary/slip/{self.slip.id}/bonus/',
            {'label': label, 'amount': amount}, secure=True, follow=True)

    def _deduct(self, label, amount):
        return self.client.post(
            f'/workforce/fleet/salary/slip/{self.slip.id}/deduction/',
            {'label': label, 'amount': amount}, secure=True, follow=True)

    def test_a_bonus_raises_the_net(self):
        self._bonus('Overtime', '300')
        self.slip.refresh_from_db()
        self.assertEqual(self.slip.additions_total, Decimal('300.00'))
        self.assertEqual(self.slip.net_amount, Decimal('2800.00'))

    def test_a_bonus_leaves_the_agreement_alone(self):
        """Next month must start from the standing salary, not from a one-off."""
        self._bonus('Overtime', '300')
        self.slip.refresh_from_db()
        self.assertEqual(self.slip.base_amount, Decimal('2500.00'))
        self.assertEqual(self.slip.structure.monthly_amount, Decimal('2500.00'))

    def test_a_zero_bonus_is_refused(self):
        self._bonus('Nothing', '0')
        self.slip.refresh_from_db()
        self.assertEqual(self.slip.addition_lines.count(), 0)

    def test_a_bonus_widens_the_deduction_ceiling(self):
        self._bonus('Overtime', '500')
        self._deduct('Advance', '2800')   # over the base, inside base + bonus
        self.slip.refresh_from_db()
        self.assertEqual(self.slip.deductions_total, Decimal('2800.00'))
        self.assertEqual(self.slip.net_amount, Decimal('200.00'))

    def test_removing_a_bonus_puts_the_net_back(self):
        self._bonus('Overtime', '300')
        line = self.slip.addition_lines.get()
        self.client.post(f'/workforce/fleet/salary/bonus/{line.id}/remove/',
                         {}, secure=True, follow=True)
        self.slip.refresh_from_db()
        self.assertEqual(self.slip.additions_total, Decimal('0.00'))
        self.assertEqual(self.slip.net_amount, Decimal('2500.00'))

    def test_a_paid_slip_takes_no_more_bonus(self):
        self.slip.mark_paid('cash', '', self.staff)
        self._bonus('Late bonus', '300')
        self.slip.refresh_from_db()
        self.assertEqual(self.slip.addition_lines.count(), 0)
        self.assertEqual(self.slip.net_amount, Decimal('2500.00'))


class PreviewWindowTests(SalaryTestBase):
    """A mid-month agreement's slots are competed for only by deliveries it covers.

    Counting the whole month's deliveries made the preview hand the salary's slots
    to work done before the agreement started — which publish then refused, so the
    page disagreed with reality.
    """

    def test_earlier_deliveries_do_not_consume_the_slots(self):
        from payroll.services import preview_absorption
        self._structure(target=3, start=date(2026, 9, 16))
        early = [self._task(date(2026, 9, d)) for d in (2, 3, 4)]
        late = [self._task(date(2026, 9, d)) for d in (16, 17, 18, 19)]

        covered = preview_absorption(early + late)
        self.assertEqual(set(covered), {t.id for t in late[:3]})

    def test_preview_matches_reality_across_a_mid_month_start(self):
        from payroll.services import preview_absorption
        self._structure(target=3, start=date(2026, 9, 16))
        early = [self._task(date(2026, 9, d)) for d in (2, 3, 4)]
        late = [self._task(date(2026, 9, d)) for d in (16, 17, 18, 19)]

        predicted = set(preview_absorption(early + late))
        actual = {t.id for t in sorted(early + late, key=lambda t: (t.dl_task_date, t.id))
                  if absorb_delivery(t)}
        self.assertEqual(predicted, actual)


class AbsorptionStatusTests(SalaryTestBase):
    """A salary buys deliveries, not attempts."""

    def test_a_failed_delivery_never_consumes_a_slot(self):
        self._structure(target=1)
        failed = self._task(date(2026, 9, 4))
        # .update(), not .save(): delivery.signals has a pre_save guard that
        # silently reverts a status write, so the fixture would never land.
        DeliveryTask.objects.filter(pk=failed.pk).update(dl_task_status='failed')
        failed.refresh_from_db()
        self.assertEqual(failed.dl_task_status, 'failed')
        delivered = self._task(date(2026, 9, 5))

        self.assertFalse(absorb_delivery(failed))
        # The slot is still there for work that was actually delivered.
        self.assertTrue(absorb_delivery(delivered))

    def test_preview_and_absorb_agree_when_a_failed_task_is_mixed_in(self):
        from payroll.services import preview_absorption
        self._structure(target=2)
        tasks = [self._task(date(2026, 9, d)) for d in (4, 5, 6)]
        DeliveryTask.objects.filter(pk=tasks[1].pk).update(dl_task_status='failed')
        tasks[1].refresh_from_db()

        predicted = set(preview_absorption(tasks))
        actual = {t.id for t in tasks if absorb_delivery(t)}
        self.assertEqual(predicted, actual)
        self.assertNotIn(tasks[1].id, actual)


class QueryCountTests(SalaryTestBase):
    """Salary lookups must not scale with the number of salaried drivers.

    Each of these was an N+1: the preview resolved one agreement per
    (driver, month), the register resolved an agreement and a count per row, and
    build_run ran three lookups per slip.
    """

    def _salaried(self, n, target=50):
        from django.contrib.auth import get_user_model
        drivers = []
        for i in range(n):
            user = get_user_model().objects.create_user(
                username=f'qd{i}-{Driver.objects.count()}', password='x')
            next_id = (Driver.objects.order_by('-driver_id')
                       .values_list('driver_id', flat=True).first() or 9100) + 1
            driver = Driver.objects.create(
                driver_id=next_id, user=user, driver_code=f'QD{i}',
                driver_status='approved')
            SalaryStructure.objects.create(
                driver=driver, monthly_amount=Decimal('2500'),
                delivery_target=target, effective_from=date(2026, 1, 1))
            drivers.append(driver)
        return drivers

    def _tasks_for(self, drivers, per_driver=2):
        tasks = []
        for driver in drivers:
            for d in range(per_driver):
                task = self._task(date(2026, 9, 4 + d))
                DeliveryTask.objects.filter(pk=task.pk).update(driver=driver)
                task.refresh_from_db()
                tasks.append(task)
        return tasks

    def _count(self, fn):
        from django.test.utils import CaptureQueriesContext
        from django.db import connection
        with CaptureQueriesContext(connection) as ctx:
            fn()
        return len(ctx.captured_queries)

    def test_preview_does_not_scale_with_drivers(self):
        from payroll.services import preview_absorption
        few = self._tasks_for(self._salaried(2))
        small = self._count(lambda: preview_absorption(few))
        many = self._tasks_for(self._salaried(10)[:] , per_driver=2)
        big = self._count(lambda: preview_absorption(few + many))
        self.assertEqual(small, big, 'preview_absorption is issuing a query per driver')

    def test_build_run_reads_do_not_scale_with_drivers(self):
        from django.test.utils import CaptureQueriesContext
        from django.db import connection

        def selects_for(n, month):
            self._salaried(n)
            with CaptureQueriesContext(connection) as ctx:
                build_run(month)
            return len([q for q in ctx.captured_queries if q['sql'].startswith('SELECT')])

        # Inserts necessarily grow with the number of slips; the reads must not.
        small = selects_for(2, date(2026, 9, 1))
        big = selects_for(10, date(2026, 10, 1))
        self.assertEqual(small, big, 'build_run is issuing lookups per slip')


class ZeroSalaryTests(SalaryTestBase):
    """A salary of 0.00 is not an agreement.

    With a target of 0 it means "absorb every delivery and pay nothing", so the
    driver works for free. Two such agreements were created through the UI before
    the floor existed.
    """

    def setUp(self):
        super().setUp()
        self.staff = User.objects.create_superuser(
            username='payroll-zero', email='z@example.com', password='x')
        self.client.force_login(self.staff)
        self.driver.driver_status = 'approved'
        self.driver.save(update_fields=['driver_status'])

    def _start(self, amount):
        return self.client.post(
            '/workforce/fleet/salary/structure/save/',
            {'driver_id': str(self.driver.driver_id), 'monthly_amount': amount,
             'delivery_target': '0', 'effective_from': '2026-09-01'},
            secure=True, follow=True)

    def test_a_zero_salary_is_refused(self):
        self._start('0')
        self.assertFalse(SalaryStructure.objects.filter(driver=self.driver).exists())

    def test_a_real_salary_is_accepted(self):
        self._start('2500')
        self.assertTrue(SalaryStructure.objects.filter(driver=self.driver).exists())

    def test_a_zero_deduction_is_still_allowed(self):
        # The floor is opt-in per field; deductions may legitimately be zero.
        from payroll.views import _parse_amount
        value, error = _parse_amount('0', 'deduction')
        self.assertEqual(error, '')
        self.assertEqual(value, Decimal('0'))


class BulkLimitTests(SalaryTestBase):
    """The bulk cap is a timeout guard, not a business rule.

    It exists because publishing writes a row and a wallet transaction per
    delivery, and a gunicorn worker killed mid-loop would leave a half-published
    batch. The limit is patched down here so the boundary can be exercised without
    building fifteen hundred fixtures.
    """

    def setUp(self):
        super().setUp()
        self.staff = User.objects.create_superuser(
            username='payroll-bulk', email='b@example.com', password='x')
        self.client.force_login(self.staff)

    def _publish(self, tasks):
        return self.client.post(
            '/workforce/fleet/earnings-verification/action/',
            {'action': 'publish', 'task_ids[]': [str(t.id) for t in tasks]},
            secure=True)

    def test_over_the_limit_is_refused_before_anything_is_written(self):
        from fleet.models import DriverTransaction
        from unittest.mock import patch
        tasks = [self._task(date(2026, 9, 4 + i)) for i in range(4)]
        with patch('workforce.views.EARNINGS_BULK_LIMIT', 3):
            response = self._publish(tasks)
        self.assertEqual(response.status_code, 400)
        self.assertIn('3', response.json()['error'])
        # Nothing partially published.
        self.assertEqual(DriverTransaction.objects.count(), 0)

    def test_exactly_the_limit_is_allowed(self):
        from fleet.models import DriverTransaction
        from unittest.mock import patch
        tasks = [self._task(date(2026, 9, 4 + i)) for i in range(3)]
        with patch('workforce.views.EARNINGS_BULK_LIMIT', 3):
            response = self._publish(tasks)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            DriverTransaction.objects.filter(transaction_type='earning').count(), 3)

    def test_the_shipped_limit_clears_a_real_months_work(self):
        from workforce.views import EARNINGS_BULK_LIMIT
        # 904 deliveries in one month is a real figure from production; it must fit.
        self.assertGreaterEqual(EARNINGS_BULK_LIMIT, 904)
