# Purpose: Tests for the returned-to-shipper outcome — custody, RMA paperwork and COD reversal.
# Used by: manage.py test workforce.tests_returned_to_shipper
# Notes: Fixture shape borrowed from tests_cod_return_view. Tasks are driven to their pre-terminal
#        status with a queryset .update() so the state machine is not exercised here — that is
#        delivery/tests_state_machine.py's job, and a signal-reverted write would silently pass.

import json
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from business import models as business_models
from core import models as core_models
from delivery import models as delivery_models
from delivery.services.returns import CUSTODY_OPEN_STATES, open_return_for_task
from fleet import models as fleet_models
from fleet.wallet_service import WalletService
from orders import models as orders_models

User = get_user_model()

_SEQ = [9400]


def _fixtures(cod=Decimal('300.00'), collected=True, settled=False,
              status='out_for_delivery'):
    _SEQ[0] += 1
    idx = _SEQ[0]

    biz_user = User.objects.create_user(username=f'rts_biz_{idx}', password='x')
    biz_profile = core_models.Profile.objects.create(
        user=biz_user, first_name='R', last_name='S', phone=83000000 + idx)
    business = business_models.Business.objects.create(
        business_id=idx, user=biz_user, profile=biz_profile,
        business_name=f'Rts Biz {idx}', business_code=f'RT{idx}',
        business_status='active')
    order = orders_models.Order.objects.create(
        business=business, client_order_code=f'RTS-ORD-{idx}',
        customer_name='C', customer_phone='1', customer_address='Z',
        cod_amount=cod, order_status='publish')

    drv_user = User.objects.create_user(username=f'rts_drv_{idx}', password='x')
    drv_profile = core_models.Profile.objects.create(
        user=drv_user, first_name='R', last_name='D', phone=84000000 + idx)
    driver = fleet_models.Driver.objects.create(
        driver_id=idx, user=drv_user, profile=drv_profile,
        driver_code=f'RD{idx}', driver_phone='2', driver_whatsapp='2',
        driver_languages='english', driver_license_number=f'L{idx}',
        driver_status='approved', cod_in_hand=Decimal('0.00'))

    task = delivery_models.DeliveryTask.objects.create(
        dl_task_number=f'RTS-T-{idx}', order=order, business=business, driver=driver,
        dl_task_status=status, dl_task_publish=True,
        cod_collected=collected,
        # NOT NULL with a 0.00 default — an uncollected task carries zero, not null.
        cod_collected_amount=cod if collected else Decimal('0.00'),
        cod_collected_at=timezone.now() if collected else None,
        payment_method='cash', cod_client_settled=settled)
    if collected:
        WalletService.record_transaction(
            driver=driver, transaction_type='cod_collection', amount=cod,
            description='seed', delivery_task=task)
        WalletService.sync_cod_in_hand(driver)

    staff = User.objects.create_user(
        username=f'rts_staff_{idx}', password='x', is_staff=True, is_superuser=True)
    return business, order, driver, task, staff


def _move_task_to(task, status):
    """Straight to a status without the state machine — see module notes."""
    delivery_models.DeliveryTask.objects.filter(id=task.id).update(dl_task_status=status)
    task.refresh_from_db()


class ReturnServiceTests(TestCase):

    def test_it_refuses_to_act_on_a_task_that_is_not_returned(self):
        # The pre_save guard reverts a refused transition without raising, so the
        # service must re-read the status rather than trust its caller. Opening an
        # RMA against a task still out for delivery is the failure this prevents.
        _, order, _, task, staff = _fixtures()
        outcome = open_return_for_task(task, actor=staff, reason='customer_refused')
        self.assertIsNone(outcome.custody)
        self.assertEqual(orders_models.ReturnRequest.objects.filter(order=order).count(), 0)
        self.assertTrue(any('did not stick' in w for w in outcome.warnings))

    def test_it_opens_custody_and_paperwork(self):
        _, order, _, task, staff = _fixtures(collected=False)
        _move_task_to(task, 'returned_to_shipper')

        outcome = open_return_for_task(task, actor=staff, reason='customer_refused')

        self.assertIsNotNone(outcome.custody)
        self.assertTrue(outcome.created)
        self.assertIn(outcome.custody.status, CUSTODY_OPEN_STATES)
        self.assertEqual(outcome.custody.task_id, task.id)
        self.assertIsNotNone(outcome.return_request)
        self.assertEqual(
            orders_models.ReturnRequest.objects.filter(order=order).count(), 1)

    def test_the_return_reason_is_a_real_return_reason(self):
        # ReturnRequest.reason and DeliveryTask.failure_reason are separate
        # vocabularies. Passing the task's key straight through wrote a value no
        # choices list contained, so the staff console rendered a raw slug and
        # get_reason_display() had nothing to resolve.
        _, order, _, task, staff = _fixtures(collected=False)
        _move_task_to(task, 'returned_to_shipper')

        outcome = open_return_for_task(
            task, actor=staff, reason='customer_refused',
            reason_notes='left it at the door and walked off')

        ret = outcome.return_request
        valid = {k for k, _ in orders_models.ReturnRequest.RETURN_REASON_CHOICES}
        self.assertIn(ret.reason, valid,
                      f'{ret.reason!r} is not a ReturnRequest reason')
        self.assertEqual(ret.reason, 'undelivered')
        self.assertNotEqual(ret.get_reason_display(), ret.reason,
                            'the display label fell back to the raw slug')
        # the driver's own words survive, where they read properly
        self.assertIn('Customer Refused Delivery', ret.reason_notes)
        self.assertIn('left it at the door', ret.reason_notes)
        self.assertIn(task.dl_task_number, ret.reason_notes)

    def test_a_second_call_neither_re_opens_nor_refunds_twice(self):
        _, order, driver, task, staff = _fixtures()
        _move_task_to(task, 'returned_to_shipper')

        first = open_return_for_task(task, actor=staff, reason='customer_refused')
        second = open_return_for_task(task, actor=staff, reason='customer_refused')

        self.assertTrue(first.created)
        self.assertFalse(second.created)
        self.assertEqual(first.custody.id, second.custody.id)
        self.assertEqual(
            orders_models.ReturnRequest.objects.filter(order=order).count(), 1)
        self.assertEqual(
            fleet_models.DriverTransaction.objects.filter(
                delivery_task=task, transaction_type='cod_return').count(), 1)

    def test_it_hands_collected_cod_back(self):
        _, order, driver, task, staff = _fixtures(cod=Decimal('300.00'))
        _move_task_to(task, 'returned_to_shipper')

        outcome = open_return_for_task(task, actor=staff, reason='customer_refused')

        self.assertTrue(outcome.cod_reversed)
        self.assertEqual(outcome.cod_amount, Decimal('300.00'))
        self.assertEqual(
            fleet_models.DriverTransaction.objects.filter(
                delivery_task=task, transaction_type='cod_return').count(), 1)
        order.refresh_from_db()
        self.assertEqual(order.cod_status_by_staff, 'not_collected')
        outcome.return_request.refresh_from_db()
        self.assertTrue(outcome.return_request.cod_reversal_processed)

    def test_it_refuses_to_refund_cod_already_paid_to_the_business(self):
        # The liability has moved to the seller; refunding here would pay it twice.
        _, order, driver, task, staff = _fixtures(settled=True)
        _move_task_to(task, 'returned_to_shipper')

        outcome = open_return_for_task(task, actor=staff, reason='customer_refused')

        self.assertFalse(outcome.cod_reversed)
        self.assertFalse(
            fleet_models.DriverTransaction.objects.filter(
                delivery_task=task, transaction_type='cod_return').exists())
        self.assertTrue(any('already paid to the business' in w for w in outcome.warnings))

    def test_nothing_to_reverse_when_no_cod_was_taken(self):
        _, order, _, task, staff = _fixtures(collected=False)
        _move_task_to(task, 'returned_to_shipper')

        outcome = open_return_for_task(task, actor=staff, reason='customer_refused')

        self.assertFalse(outcome.cod_reversed)
        self.assertEqual(outcome.cod_amount, Decimal('0.00'))
        self.assertEqual(outcome.return_request.cod_reversal_amount, Decimal('0.00'))


class ReturnStatusEndpointTests(TestCase):

    def _post(self, task, staff, **extra):
        self.client.force_login(staff)
        payload = {'status': 'returned_to_shipper',
                   'failure_reason': 'customer_refused'}
        payload.update(extra)
        return self.client.post(
            reverse('workforce:update_task_status', args=[task.id]),
            data=json.dumps(payload), content_type='application/json')

    def test_the_staff_endpoint_opens_the_return(self):
        _, order, _, task, staff = _fixtures(collected=False)
        resp = self._post(task, staff)
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(body['success'])
        self.assertEqual(body['new_status'], 'returned_to_shipper')
        task.refresh_from_db()
        self.assertEqual(task.dl_task_status, 'returned_to_shipper')
        self.assertEqual(
            delivery_models.ParcelCustody.objects.filter(task=task).count(), 1)
        self.assertEqual(
            orders_models.ReturnRequest.objects.filter(order=order).count(), 1)

    def test_a_reason_is_required(self):
        _, _, _, task, staff = _fixtures(collected=False)
        resp = self._post(task, staff, failure_reason='')
        self.assertEqual(resp.status_code, 400)
        task.refresh_from_db()
        self.assertEqual(task.dl_task_status, 'out_for_delivery')

    def test_a_refused_transition_is_no_longer_reported_as_success(self):
        # The endpoint used to echo the requested status back without re-reading,
        # so a write the pre_save guard reverted looked like a green success.
        # Deliberately a plain staff user: a superuser resolves to actor='admin',
        # and ADMIN_TRANSITIONS allows any move, so nothing would be refused.
        _, _, _, task, _ = _fixtures(collected=False)
        # Departments matter as much as is_staff here: StaffDepartmentMiddleware
        # fails closed, so a staff user with no desk is 302'd off the page before
        # the view ever runs and the test would pass for the wrong reason.
        from core.departments import ASSIGNABLE_DEPARTMENTS, DEPARTMENT_FIELDS
        plain_staff = User.objects.create_user(
            username=f'rts_plain_{task.id}', password='x', is_staff=True)
        core_models.Profile.objects.create(
            user=plain_staff, first_name='P', last_name='S',
            phone=86000000 + task.id, is_staff=True,
            **{DEPARTMENT_FIELDS[c]: True for c in ASSIGNABLE_DEPARTMENTS})
        _move_task_to(task, 'delivered')
        resp = self._post(task, plain_staff)
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(resp.json()['success'])
        task.refresh_from_db()
        self.assertEqual(task.dl_task_status, 'delivered')
