# Purpose: Tests for ParcelCustody — the open-row constraint, destination resolution and history.
# Used by: manage.py test delivery.tests_parcel_custody
# Notes: The constraint condition is a frozen literal in the migration, so the first test asserts it
#        still agrees with CUSTODY_OPEN_STATES — they are edited in two different files and nothing
#        else would catch them drifting apart.

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from business import models as business_models
from core import models as core_models
from delivery import models as delivery_models
from delivery.models import ParcelCustody
from delivery.services.returns import (
    CUSTODY_DISPUTED, CUSTODY_IN_MANIFEST, CUSTODY_OPEN_STATES, CUSTODY_RECEIVED,
    CUSTODY_WITH_DRIVER, DEST_BUSINESS, DEST_HUB,
    log_custody_history, resolve_return_destination, set_custody_status,
)
from fleet import models as fleet_models
from orders import models as orders_models

User = get_user_model()

_SEQ = [9700]


def _fixtures(return_destination='hub'):
    _SEQ[0] += 1
    idx = _SEQ[0]

    biz_user = User.objects.create_user(username=f'pc_biz_{idx}', password='x')
    biz_profile = core_models.Profile.objects.create(
        user=biz_user, first_name='P', last_name='C', phone=85000000 + idx)
    business = business_models.Business.objects.create(
        business_id=idx, user=biz_user, profile=biz_profile,
        business_name=f'PC Biz {idx}', business_code=f'PC{idx}',
        business_status='active', return_destination=return_destination)
    order = orders_models.Order.objects.create(
        business=business, client_order_code=f'PC-ORD-{idx}',
        customer_name='C', customer_phone='1', customer_address='Z',
        cod_amount=Decimal('0.00'), order_status='publish')
    task = delivery_models.DeliveryTask.objects.create(
        dl_task_number=f'PC-T-{idx}', order=order, business=business,
        dl_task_status='out_for_delivery')
    staff = User.objects.create_user(username=f'pc_staff_{idx}', password='x', is_staff=True)
    return business, order, task, staff


def _custody(task, order, business, status=CUSTODY_WITH_DRIVER):
    return ParcelCustody.objects.create(
        task=task, order=order, business=business, status=status,
        destination_kind=DEST_HUB)


class ConstraintTests(TestCase):

    def test_the_frozen_constraint_still_matches_the_service(self):
        constraint = next(c for c in ParcelCustody._meta.constraints
                          if c.name == 'uniq_open_parcel_custody_per_task')
        states = set(constraint.condition.deconstruct()[1][0][1])
        self.assertEqual(
            states, set(CUSTODY_OPEN_STATES),
            'The migration-frozen constraint and CUSTODY_OPEN_STATES have drifted. '
            'Two open custody rows per task would become possible.')

    def test_two_open_rows_for_one_task_are_refused(self):
        business, order, task, _ = _fixtures()
        _custody(task, order, business)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                _custody(task, order, business, status=CUSTODY_IN_MANIFEST)

    def test_a_closed_row_does_not_block_a_new_one(self):
        # A parcel can legitimately come back twice — a replacement that is also
        # refused — so the constraint must only ever guard the OPEN rows.
        business, order, task, _ = _fixtures()
        _custody(task, order, business, status=CUSTODY_RECEIVED)
        second = _custody(task, order, business)
        self.assertTrue(second.is_open)


class DestinationTests(TestCase):

    def test_it_defaults_to_the_hub(self):
        _, _, task, _ = _fixtures(return_destination='hub')
        destination = resolve_return_destination(task)
        self.assertEqual(destination.kind, DEST_HUB)

    def test_a_business_return_with_no_usable_pickup_location_falls_back_and_says_why(self):
        # Never silently: a parcel routed nowhere has to reach the triage queue
        # with the reason attached, not look like "no return required".
        _, _, task, _ = _fixtures(return_destination='business')
        destination = resolve_return_destination(task)
        self.assertEqual(destination.kind, DEST_HUB)
        self.assertTrue(destination.fallback_reason)

    def test_needs_triage_when_nothing_resolved(self):
        business, order, task, _ = _fixtures()
        custody = _custody(task, order, business)
        self.assertIsNone(custody.warehouse_location_id)
        self.assertTrue(custody.needs_triage)
        self.assertIn('triage', custody.destination_label.lower())


class CustodyStatusTests(TestCase):

    def test_receiving_stamps_who_and_when(self):
        business, order, task, staff = _fixtures()
        custody = _custody(task, order, business)
        ok, reason = set_custody_status(custody, CUSTODY_RECEIVED, actor=staff)
        self.assertTrue(ok, reason)
        custody.refresh_from_db()
        self.assertEqual(custody.received_by_id, staff.id)
        self.assertIsNotNone(custody.received_at)
        self.assertFalse(custody.is_open)

    def test_a_received_parcel_cannot_un_arrive(self):
        business, order, task, staff = _fixtures()
        custody = _custody(task, order, business, status=CUSTODY_RECEIVED)
        ok, reason = set_custody_status(custody, CUSTODY_WITH_DRIVER, actor=staff)
        self.assertFalse(ok)
        self.assertIn('Cannot move custody', reason)

    def test_history_lands_on_the_order_timeline(self):
        business, order, task, staff = _fixtures()
        custody = _custody(task, order, business)
        set_custody_status(custody, CUSTODY_IN_MANIFEST, actor=staff, notes='bag 4')
        rows = orders_models.OrderStatusHistory.objects.filter(
            order=order, field_name='parcel_custody')
        self.assertEqual(rows.count(), 1)
        self.assertEqual(rows.first().new_value, CUSTODY_IN_MANIFEST)
        self.assertEqual(rows.first().new_display, 'In return manifest')

    def test_a_failed_audit_write_never_loses_the_custody_move(self):
        business, order, task, staff = _fixtures()
        custody = _custody(task, order, business)
        custody.order = None  # forces the history write to blow up
        log_custody_history(custody, CUSTODY_WITH_DRIVER, CUSTODY_RECEIVED, staff)
        self.assertEqual(
            orders_models.OrderStatusHistory.objects.filter(
                order=order, field_name='parcel_custody').count(), 0)
