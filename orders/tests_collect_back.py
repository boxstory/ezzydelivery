# Purpose: Tests for collect-back — the original items coming back on their own collection task.
# Used by: manage.py test orders.tests_collect_back
# Notes: The point of the change is that NO movement rides as a flag on another task. Assert the
#        two ends of every leg, not just that something was created.

from decimal import Decimal

from django.test import TestCase

from delivery.models import ParcelCustody
from delivery.selectors import task_destination, task_origin
from delivery.services.returns import (
    CUSTODY_RECEIVED, DEST_BUSINESS, DEST_HUB, forward_to_client,
)
from orders import models as orders_models
from orders.services import create_replacement_order, create_return_pickup_order
from orders.status_actions import apply_ready_and_publish
from orders.tests_return_pickup import _claim, _fixtures
from warehouse import models as warehouse_models


def _deliver(task):
    for status in ('out_for_delivery', 'delivered'):
        task.dl_task_status = status
        task._status_actor = 'staff'
        task.save()
    task.refresh_from_db()
    return task


def _hub():
    # resolve_default_hub() keys off Warehouse.is_default — without it nothing
    # resolves and a hub-routed collection correctly falls back to the client.
    warehouse = warehouse_models.Warehouse.objects.create(
        name='CB FC', code='CB-FC', is_default=True,
        latitude=Decimal('25.29'), longitude=Decimal('51.51'))
    return warehouse_models.WarehouseLocation.objects.create(
        warehouse=warehouse, name='Main Dock', code='CB-FC-DOCK', is_default=True,
        latitude=Decimal('25.29'), longitude=Decimal('51.51'))


_DRV = [4400]


def _driver():
    from django.contrib.auth import get_user_model
    from core import models as core_models
    from fleet import models as fleet_models

    _DRV[0] += 1
    idx = _DRV[0]
    user = get_user_model().objects.create_user(username=f'cb_drv{idx}', password='x')
    profile = core_models.Profile.objects.create(
        user=user, first_name='C', last_name='B', phone=76000000 + idx, is_driver=True)
    return fleet_models.Driver.objects.create(
        driver_id=7000 + idx, user=user, profile=profile, driver_code=f'CBD{idx}',
        driver_phone=f'31{idx}', driver_whatsapp=f'31{idx}',
        driver_languages='english', driver_license_number=f'CBL{idx}',
        driver_status='approved', dashboard_access_enabled=True)


def _replacement(collect_back=True, collect_dest='business', publish=True):
    business, order, item, pickup, staff = _fixtures()
    business.return_collection_destination = collect_dest
    business.save(update_fields=['return_collection_destination'])
    repl = create_replacement_order(
        order, reason='damaged', collect_back=collect_back, user=staff, publish=publish)
    return business, order, pickup, repl, staff


def _collections(business):
    return orders_models.Order.objects.filter(
        order_type='return_pickup', business=business)


class OutboundLegTests(TestCase):
    def test_collect_back_is_no_longer_an_exchange_leg(self):
        _, _, _, repl, _ = _replacement()
        self.assertEqual(repl.delivery_task.get().task_leg, 'single')

    def test_the_sellers_tick_is_still_recorded(self):
        _, _, _, repl, _ = _replacement()
        self.assertTrue(repl.collect_back)


class CollectBackCollectionTests(TestCase):
    def test_delivering_the_replacement_raises_one_collection(self):
        business, _, _, repl, _ = _replacement()
        self.assertEqual(_collections(business).count(), 0, 'raised too early')

        _deliver(repl.delivery_task.get())

        collection = _collections(business).get()
        task = collection.delivery_task.get()
        self.assertEqual(task.task_leg, 'collect_from_customer')
        self.assertTrue(task.dl_task_publish)

    def test_the_collection_runs_customer_to_seller(self):
        business, order, pickup, repl, _ = _replacement()
        _deliver(repl.delivery_task.get())

        task = _collections(business).get().delivery_task.get()
        order.refresh_from_db()
        pickup.refresh_from_db()

        origin = task_origin(task)
        destination = task_destination(task)
        self.assertEqual(origin.label, order.customer_name)
        self.assertEqual(origin.latitude, order.latitude)
        self.assertFalse(destination.is_customer)
        self.assertEqual(destination.latitude, pickup.pickup_lat)

    def test_the_claim_is_raised_against_the_original_order(self):
        _, order, _, repl, _ = _replacement()
        _deliver(repl.delivery_task.get())

        claim = order.return_requests.get()
        self.assertEqual(claim.status, 'pickup_scheduled')
        self.assertEqual(claim.reason, 'damaged')
        self.assertIsNotNone(claim.pickup_order_id)
        # Not against the replacement — those are not the goods coming back.
        self.assertFalse(repl.return_requests.exists())

    def test_a_plain_replacement_raises_nothing(self):
        business, _, _, repl, _ = _replacement(collect_back=False)
        _deliver(repl.delivery_task.get())
        self.assertEqual(_collections(business).count(), 0)

    def test_a_failed_replacement_raises_nothing(self):
        business, _, _, repl, _ = _replacement()
        task = repl.delivery_task.get()
        task.dl_task_status = 'failed'
        task._status_actor = 'staff'
        task.save()
        self.assertEqual(_collections(business).count(), 0)

    def test_it_is_raised_once_however_often_delivered_is_written(self):
        business, _, _, repl, _ = _replacement()
        task = _deliver(repl.delivery_task.get())
        task.dl_task_status = 'out_for_delivery'
        task._status_actor = 'staff'
        task.save()
        _deliver(task)
        self.assertEqual(_collections(business).count(), 1)

    def test_an_existing_collection_wins(self):
        """Two drivers for one parcel is the thing this must never do."""
        business, order, _, repl, staff = _replacement()
        create_return_pickup_order(_claim(order), user=staff, publish=True)

        _deliver(repl.delivery_task.get())
        self.assertEqual(_collections(business).count(), 1)

    def test_a_draft_published_later_still_collects(self):
        business, _, _, repl, staff = _replacement(publish=False)
        self.assertEqual(repl.delivery_task.count(), 0)

        apply_ready_and_publish(repl, user=staff)
        _deliver(repl.delivery_task.get())
        self.assertEqual(_collections(business).count(), 1)


class CollectionDestinationTests(TestCase):
    def test_the_client_counter_is_the_default(self):
        from business import models as business_models
        self.assertEqual(
            business_models.Business._meta.get_field(
                'return_collection_destination').default, DEST_BUSINESS)

    def test_the_undelivered_preference_is_left_alone(self):
        """The two questions share a vocabulary, never a field: routing collections
        off return_destination would have re-routed every failed delivery."""
        from business import models as business_models
        self.assertEqual(
            business_models.Business._meta.get_field('return_destination').default,
            DEST_HUB)

        business, _, _, _, _ = _replacement(collect_dest='hub')
        business.refresh_from_db()
        self.assertEqual(business.return_destination, DEST_HUB)
        self.assertEqual(business.return_collection_destination, DEST_HUB)

    def test_a_hub_client_sends_the_collection_to_the_hub(self):
        dock = _hub()
        business, _, _, repl, _ = _replacement(collect_dest='hub')
        _deliver(repl.delivery_task.get())

        task = _collections(business).get().delivery_task.get()
        self.assertEqual(task.hub_warehouse_id, dock.id)
        destination = task_destination(task)
        self.assertFalse(destination.is_customer)
        self.assertEqual(destination.latitude, dock.latitude)
        self.assertIn('Main Dock', destination.address_text)

    def test_a_hub_collection_lands_in_the_forward_queue(self):
        _hub()
        business, _, _, repl, _ = _replacement(collect_dest='hub')
        _deliver(repl.delivery_task.get())
        collection_task = _deliver(_collections(business).get().delivery_task.get())

        custody = ParcelCustody.objects.get(task=collection_task)
        self.assertEqual(custody.status, CUSTODY_RECEIVED)
        self.assertEqual(custody.destination_kind, DEST_HUB)
        self.assertIsNotNone(custody.warehouse_location_id)

        # Exactly what workforce.views' to_forward filter looks for.
        self.assertTrue(
            ParcelCustody.objects.filter(
                pk=custody.pk, status=CUSTODY_RECEIVED, destination_kind='hub'
            ).exists())

        outcome = forward_to_client(custody)
        self.assertFalse(outcome.error, outcome.error)
        self.assertEqual(outcome.task.task_leg, 'return_to_client')

    def test_the_driver_holds_the_goods_until_he_drops_them(self):
        _hub()
        business, _, _, repl, _ = _replacement(collect_dest='hub')
        _deliver(repl.delivery_task.get())
        task = _collections(business).get().delivery_task.get()

        # A task nobody has claimed opens custody as 'disputed' — the box is moving
        # and we do not know who has it. Give it the driver a real claim would.
        task.driver = _driver()
        task.save(update_fields=['driver'])

        # pending -> picked_up is not a legal transition and the pre_save guard
        # reverts it silently, so go the way a driver actually goes.
        for status in ('accepted', 'picked_up'):
            task.dl_task_status = status
            task._status_actor = 'driver'
            task.save()
        task.refresh_from_db()
        self.assertEqual(task.dl_task_status, 'picked_up', 'the status did not stick')

        custody = ParcelCustody.objects.get(task=task)
        self.assertEqual(custody.status, 'with_driver')
        self.assertEqual(custody.driver_id, task.driver_id)

    def test_a_client_collection_closes_without_a_hub(self):
        business, _, _, repl, _ = _replacement(collect_dest='business')
        _deliver(repl.delivery_task.get())
        task = _deliver(_collections(business).get().delivery_task.get())

        custody = ParcelCustody.objects.get(task=task)
        self.assertEqual(custody.status, CUSTODY_RECEIVED)
        self.assertEqual(custody.destination_kind, DEST_BUSINESS)
        # destination_kind='business' keeps it out of the hub forward queue.
        self.assertFalse(
            ParcelCustody.objects.filter(
                pk=custody.pk, status=CUSTODY_RECEIVED, destination_kind='hub').exists())
