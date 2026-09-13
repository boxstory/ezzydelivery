# Purpose: Tests for first-mile pickup — creation gating, pool scoping, atomic accept, dispositions
# Used by: python manage.py test delivery.tests_pickup

from datetime import timedelta

from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone

from delivery import models as delivery_models
from delivery.selectors import pickup_pool_for
from delivery.services import pickup as pickup_service
from orders import models as orders_models
from business import models as business_models
from fleet import models as fleet_models
from core import models as core_models

PickupTask = delivery_models.PickupTask
DeliveryTask = delivery_models.DeliveryTask
Order = orders_models.Order
Business = business_models.Business
PickupLocation = business_models.PickupLocation
DriverDirectory = business_models.DriverDirectory
Driver = fleet_models.Driver
Profile = core_models.Profile

User = get_user_model()


def make_driver(idx, status='approved'):
    user = User.objects.create_user(username=f'pkdriver{idx}', password='x')
    profile = Profile.objects.create(user=user, first_name=f'D{idx}', last_name='Driver', phone=90000000 + idx)
    return Driver.objects.create(
        driver_id=9000 + idx, user=user, profile=profile,
        driver_code=f'PKD{idx}', driver_phone=str(30000000 + idx),
        driver_whatsapp=str(30000000 + idx), driver_languages='english',
        driver_license_number=f'LIC{idx}', driver_status=status,
    )


class PickupBaseTestCase(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username='pkbiz', password='x')
        self.profile = Profile.objects.create(
            user=self.owner, first_name='Pk', last_name='Biz', phone=88888888)
        self.business = Business.objects.create(
            business_id=900, user=self.owner, profile=self.profile,
            business_name='Pickup Biz', business_code='PKB001',
            business_status='active',
            pickup_task_enabled=True,
            pickup_mode_default='public_pool',
            pickup_disposition_default='drop',
        )
        self.pickup_location = PickupLocation.objects.create(
            business=self.business, pickup_location_title='PK Store',
            locality='Doha', pickup_zone_no=55, pickup_status='active',
        )
        self.driver = make_driver(1)

    def make_order(self, code='PK001', **kwargs):
        defaults = dict(
            business=self.business, client_order_code=code,
            customer_name='Cust', customer_phone='55555555',
            customer_address='Somewhere', dl_zone=55,
            pickup_location=self.pickup_location,
        )
        defaults.update(kwargs)
        with self.captureOnCommitCallbacks(execute=True):
            order = Order.objects.create(**defaults)
        return order


class PickupCreationTestCase(PickupBaseTestCase):
    def test_created_on_order_create(self):
        order = self.make_order()
        pickup = PickupTask.objects.filter(order=order).first()
        self.assertIsNotNone(pickup)
        self.assertEqual(pickup.status, 'pending')
        self.assertEqual(pickup.pickup_mode, 'public_pool')
        self.assertEqual(pickup.disposition, 'drop')

    def test_not_created_when_disabled(self):
        self.business.pickup_task_enabled = False
        self.business.save(update_fields=['pickup_task_enabled'])
        order = self.make_order('PK002')
        self.assertFalse(PickupTask.objects.filter(order=order).exists())

    def test_not_created_for_fulfilment_center(self):
        self.pickup_location.is_fulfilment_center = True
        self.pickup_location.save(update_fields=['is_fulfilment_center'])
        order = self.make_order('PK003')
        self.assertFalse(PickupTask.objects.filter(order=order).exists())

    def test_not_created_for_inactive_business(self):
        self.business.business_status = 'suspended'
        self.business.save(update_fields=['business_status'])
        order = self.make_order('PK004')
        self.assertFalse(PickupTask.objects.filter(order=order).exists())

    def test_not_duplicated(self):
        order = self.make_order('PK005')
        _, reason = pickup_service.create_pickup_task_if_needed(order)
        self.assertEqual(reason, 'already_exists')
        self.assertEqual(PickupTask.objects.filter(order=order).count(), 1)

    def test_cancel_guard(self):
        order = self.make_order('PK006')
        order.order_status = 'cancelled'
        order.save()
        self.assertEqual(PickupTask.objects.get(order=order).status, 'cancelled')


class PickupLateLocationTestCase(PickupBaseTestCase):
    """Imports save the order with no pickup location, so the create-time gate
    bails on 'no_pickup_location'. Attaching one later must open the leg."""

    def make_locationless_order(self, code):
        with self.captureOnCommitCallbacks(execute=True):
            order = Order.objects.create(
                business=self.business, client_order_code=code,
                customer_name='Cust', customer_phone='55555555',
                customer_address='Somewhere', dl_zone=55,
                pickup_location=None,
            )
        return order

    def test_no_pickup_without_a_location(self):
        order = self.make_locationless_order('PKL01')
        self.assertFalse(PickupTask.objects.filter(order=order).exists())

    def test_pickup_created_when_location_arrives_later(self):
        order = self.make_locationless_order('PKL02')
        with self.captureOnCommitCallbacks(execute=True):
            order.pickup_location = self.pickup_location
            order.save(update_fields=['pickup_location'])
        pickup = PickupTask.objects.filter(order=order).first()
        self.assertIsNotNone(pickup)
        self.assertEqual(pickup.status, 'pending')
        self.assertEqual(pickup.pickup_location_id, self.pickup_location.pk)

    def test_late_fulfilment_centre_still_refused(self):
        order = self.make_locationless_order('PKL03')
        fc = PickupLocation.objects.create(
            business=self.business, pickup_location_title='WH: Hub',
            locality='Doha', pickup_status='active', is_fulfilment_center=True)
        with self.captureOnCommitCallbacks(execute=True):
            order.pickup_location = fc
            order.save(update_fields=['pickup_location'])
        self.assertFalse(PickupTask.objects.filter(order=order).exists())

    def test_terminal_order_gets_no_late_pickup(self):
        order = self.make_locationless_order('PKL04')
        Order.objects.filter(pk=order.pk).update(order_status='delivered')
        order.refresh_from_db()
        with self.captureOnCommitCallbacks(execute=True):
            order.pickup_location = self.pickup_location
            order.save(update_fields=['pickup_location'])
        self.assertFalse(PickupTask.objects.filter(order=order).exists())

    def test_relocating_an_existing_pickup_makes_no_second_leg(self):
        order = self.make_order('PKL05')
        other = PickupLocation.objects.create(
            business=self.business, pickup_location_title='PK Store 2',
            locality='Doha', pickup_status='active')
        with self.captureOnCommitCallbacks(execute=True):
            order.pickup_location = other
            order.save(update_fields=['pickup_location'])
        self.assertEqual(PickupTask.objects.filter(order=order).count(), 1)


class PickupReadyToPickupTestCase(PickupBaseTestCase):
    """Staff marking an order 'ready_to_pickup' is the third chance to open a
    leg. The order was created against a location the gate refused (a stale
    fulfilment-centre flag, an inactive address), so neither the create hook nor
    the location hook ever fired; once the config is repaired, the status move
    is what asserts the goods are packed and collectable."""

    def make_refused_order(self, code):
        self.pickup_location.is_fulfilment_center = True
        self.pickup_location.save(update_fields=['is_fulfilment_center'])
        order = self.make_order(code)
        self.assertFalse(PickupTask.objects.filter(order=order).exists())
        return order

    def repair_location(self):
        self.pickup_location.is_fulfilment_center = False
        self.pickup_location.pickup_status = 'active'
        self.pickup_location.save(
            update_fields=['is_fulfilment_center', 'pickup_status'])

    def set_status(self, order, status):
        with self.captureOnCommitCallbacks(execute=True):
            order.order_status = status
            order.save(update_fields=['order_status'])

    def test_leg_opens_when_staff_mark_ready(self):
        order = self.make_refused_order('PKR01')
        self.repair_location()
        self.set_status(order, 'ready_to_pickup')
        pickup = PickupTask.objects.filter(order=order).first()
        self.assertIsNotNone(pickup)
        self.assertEqual(pickup.status, 'pending')
        self.assertEqual(pickup.pickup_location_id, self.pickup_location.pk)

    def test_still_refused_while_the_location_is_unrepaired(self):
        order = self.make_refused_order('PKR02')
        self.set_status(order, 'ready_to_pickup')
        self.assertFalse(PickupTask.objects.filter(order=order).exists())

    def test_no_second_leg_when_one_already_exists(self):
        order = self.make_order('PKR03')
        self.assertEqual(PickupTask.objects.filter(order=order).count(), 1)
        self.set_status(order, 'ready_to_pickup')
        self.assertEqual(PickupTask.objects.filter(order=order).count(), 1)

    def test_only_the_transition_fires_not_every_later_save(self):
        order = self.make_refused_order('PKR04')
        self.set_status(order, 'ready_to_pickup')   # gate still refuses
        self.repair_location()
        with self.captureOnCommitCallbacks(execute=True):
            order.customer_name = 'Renamed'
            order.save(update_fields=['customer_name'])
        self.assertFalse(PickupTask.objects.filter(order=order).exists())


class WorkforcePickupCreateTestCase(PickupBaseTestCase):
    """Staff repair hatch: /workforce/pickups/create/ opens a leg for an order
    that never got one, after asking which shop address holds the goods."""

    def setUp(self):
        super().setUp()
        self.staff = User.objects.create_user(
            username='pkstaff3', password='x', is_staff=True)
        core_models.Profile.objects.create(
            user=self.staff, is_staff=True, dept_operations=True)
        self.client.force_login(self.staff)

    def make_locationless_order(self, code):
        with self.captureOnCommitCallbacks(execute=True):
            order = Order.objects.create(
                business=self.business, client_order_code=code,
                customer_name='Cust', customer_phone='55555555',
                customer_address='Somewhere', dl_zone=55, pickup_location=None,
            )
        return order

    def test_lookup_offers_only_non_fulfilment_locations(self):
        order = self.make_locationless_order('PKC01')
        PickupLocation.objects.create(
            business=self.business, pickup_location_title='WH: Hub',
            locality='Doha', pickup_status='active', is_fulfilment_center=True)
        resp = self.client.post('/workforce/pickups/create/',
                                {'order_number': order.order_number})
        data = resp.json()
        self.assertTrue(data['success'])
        self.assertTrue(data['needs_location'])
        titles = [loc['title'] for loc in data['locations']]
        self.assertEqual(titles, ['PK Store'])

    def test_creates_the_leg_and_stamps_the_order(self):
        order = self.make_locationless_order('PKC02')
        with self.captureOnCommitCallbacks(execute=True):
            resp = self.client.post('/workforce/pickups/create/', {
                'order_number': order.order_number,
                'pickup_location_id': self.pickup_location.pk,
            })
        self.assertTrue(resp.json()['success'])
        order.refresh_from_db()
        self.assertEqual(order.pickup_location_id, self.pickup_location.pk)
        self.assertEqual(PickupTask.objects.filter(order=order).count(), 1)

    def test_unknown_order_is_reported(self):
        resp = self.client.post('/workforce/pickups/create/',
                                {'order_number': 'NOPE-1'})
        self.assertFalse(resp.json()['success'])

    def test_existing_pickup_is_refused(self):
        order = self.make_order('PKC03')
        resp = self.client.post('/workforce/pickups/create/',
                                {'order_number': order.order_number})
        data = resp.json()
        self.assertFalse(data['success'])
        self.assertIn('already has a pickup', data['error'])

    def test_location_from_another_client_is_refused(self):
        order = self.make_locationless_order('PKC04')
        other_user = User.objects.create_user(username='pkbiz2', password='x')
        other_profile = Profile.objects.create(
            user=other_user, first_name='Other', last_name='Biz', phone=77777777)
        other_business = Business.objects.create(
            business_id=901, user=other_user, profile=other_profile,
            business_name='Other Biz', business_code='OTB001',
            business_status='active', pickup_task_enabled=True)
        foreign = PickupLocation.objects.create(
            business=other_business, pickup_location_title='Foreign Store',
            locality='Doha', pickup_status='active')
        resp = self.client.post('/workforce/pickups/create/', {
            'order_number': order.order_number,
            'pickup_location_id': foreign.pk,
        })
        self.assertFalse(resp.json()['success'])
        self.assertFalse(PickupTask.objects.filter(order=order).exists())

    def test_client_with_pickup_disabled_is_refused_in_words(self):
        order = self.make_locationless_order('PKC05')
        self.business.pickup_task_enabled = False
        self.business.save(update_fields=['pickup_task_enabled'])
        resp = self.client.post('/workforce/pickups/create/', {
            'order_number': order.order_number,
            'pickup_location_id': self.pickup_location.pk,
        })
        data = resp.json()
        self.assertFalse(data['success'])
        self.assertIn('switched off', data['error'])


class PickupRelocateTestCase(PickupBaseTestCase):
    """Staff move an open pickup to another of the client's addresses."""

    def setUp(self):
        super().setUp()
        self.staff = User.objects.create_user(
            username='pkstaff4', password='x', is_staff=True)
        core_models.Profile.objects.create(
            user=self.staff, is_staff=True, dept_operations=True)
        self.client.force_login(self.staff)
        self.other_location = PickupLocation.objects.create(
            business=self.business, pickup_location_title='PK Store 2',
            locality='Wakrah', pickup_zone_no=90, pickup_status='active')

    def relocate(self, pickup, location):
        return self.client.post('/workforce/pickups/relocate/', {
            'pickup_id': pickup.pk, 'pickup_location_id': location.pk,
        }).json()

    def test_moves_pickup_and_order_together(self):
        order = self.make_order('PKR01')
        pickup = PickupTask.objects.get(order=order)
        self.assertTrue(self.relocate(pickup, self.other_location)['success'])
        pickup.refresh_from_db()
        order.refresh_from_db()
        self.assertEqual(pickup.pickup_location_id, self.other_location.pk)
        self.assertEqual(order.pickup_location_id, self.other_location.pk)

    def test_assigned_driver_is_notified(self):
        order = self.make_order('PKR02')
        pickup = PickupTask.objects.get(order=order)
        pickup.driver = self.driver
        pickup.status = 'accepted'
        pickup.save()
        self.assertTrue(self.relocate(pickup, self.other_location)['success'])
        self.assertTrue(fleet_models.DriverNotification.objects.filter(
            driver=self.driver, title='Pickup address changed').exists())

    def test_collected_pickup_is_refused(self):
        order = self.make_order('PKR03')
        pickup = PickupTask.objects.get(order=order)
        pickup.status = 'collected'
        pickup.save(update_fields=['status'])
        res = self.relocate(pickup, self.other_location)
        self.assertFalse(res['success'])
        pickup.refresh_from_db()
        self.assertEqual(pickup.pickup_location_id, self.pickup_location.pk)

    def test_fulfilment_centre_is_refused(self):
        order = self.make_order('PKR04')
        pickup = PickupTask.objects.get(order=order)
        fc = PickupLocation.objects.create(
            business=self.business, pickup_location_title='WH: Hub',
            locality='Doha', pickup_status='active', is_fulfilment_center=True)
        res = self.relocate(pickup, fc)
        self.assertFalse(res['success'])
        self.assertIn('fulfilment centre', res['error'])

    def test_another_clients_location_is_refused(self):
        order = self.make_order('PKR05')
        pickup = PickupTask.objects.get(order=order)
        other_user = User.objects.create_user(username='pkbiz3', password='x')
        other_profile = Profile.objects.create(
            user=other_user, first_name='Other', last_name='Biz', phone=76767676)
        other_business = Business.objects.create(
            business_id=902, user=other_user, profile=other_profile,
            business_name='Other Biz', business_code='OTB002',
            business_status='active', pickup_task_enabled=True)
        foreign = PickupLocation.objects.create(
            business=other_business, pickup_location_title='Foreign Store',
            locality='Doha', pickup_status='active')
        self.assertFalse(self.relocate(pickup, foreign)['success'])
        pickup.refresh_from_db()
        self.assertEqual(pickup.pickup_location_id, self.pickup_location.pk)

    def test_editing_the_order_carries_the_open_leg_across(self):
        order = self.make_order('PKR06')
        pickup = PickupTask.objects.get(order=order)
        with self.captureOnCommitCallbacks(execute=True):
            order.pickup_location = self.other_location
            order.save(update_fields=['pickup_location'])
        pickup.refresh_from_db()
        self.assertEqual(pickup.pickup_location_id, self.other_location.pk)
        self.assertEqual(PickupTask.objects.filter(order=order).count(), 1)

    def test_editing_the_order_leaves_a_collected_leg_alone(self):
        order = self.make_order('PKR07')
        pickup = PickupTask.objects.get(order=order)
        pickup.status = 'collected'
        pickup.save(update_fields=['status'])
        with self.captureOnCommitCallbacks(execute=True):
            order.pickup_location = self.other_location
            order.save(update_fields=['pickup_location'])
        pickup.refresh_from_db()
        self.assertEqual(pickup.pickup_location_id, self.pickup_location.pk)


class PickupPoolScopingTestCase(PickupBaseTestCase):
    def test_public_pool_visible_to_all_approved(self):
        order = self.make_order('PK010')
        other = make_driver(2)
        self.assertTrue(pickup_pool_for(self.driver).filter(order=order).exists())
        self.assertTrue(pickup_pool_for(other).filter(order=order).exists())

    def test_unapproved_driver_sees_nothing(self):
        self.make_order('PK011')
        pending_driver = make_driver(3, status='pending')
        self.assertEqual(pickup_pool_for(pending_driver).count(), 0)

    def test_assigned_mode_scoped_to_directory(self):
        self.business.pickup_mode_default = 'assigned'
        self.business.save(update_fields=['pickup_mode_default'])
        order = self.make_order('PK012')
        outsider = make_driver(4)
        DriverDirectory.objects.create(business=self.business, driver=self.driver)
        self.assertTrue(pickup_pool_for(self.driver).filter(order=order).exists())
        self.assertFalse(pickup_pool_for(outsider).filter(order=order).exists())

    def test_assigned_mode_inactive_link_hidden(self):
        self.business.pickup_mode_default = 'assigned'
        self.business.save(update_fields=['pickup_mode_default'])
        order = self.make_order('PK013')
        DriverDirectory.objects.create(
            business=self.business, driver=self.driver, is_active=False)
        self.assertFalse(pickup_pool_for(self.driver).filter(order=order).exists())


class PickupPoolStaleTestCase(PickupBaseTestCase):
    """A finished order/delivery leg must not leave a claimable pickup behind."""

    def make_task(self, order, status='pending'):
        return DeliveryTask.objects.create(
            order=order, business=self.business,
            dl_task_number=f'DLPK{order.pk}', dl_task_description='Pickup test task',
            dl_task_status_client='for_review', dl_task_status=status,
        )

    def test_pool_excludes_cancelled_delivery_task(self):
        # The reported bug: task cancelled, order left on publish, pickup still pending
        order = self.make_order('PKS01')
        self.make_task(order, 'cancelled')
        self.assertEqual(PickupTask.objects.get(order=order).status, 'pending')
        self.assertFalse(pickup_pool_for(self.driver).filter(order=order).exists())

    def test_pool_excludes_delivered_order(self):
        order = self.make_order('PKS02')
        order.order_status = 'delivered'
        order.save(update_fields=['order_status'])
        self.assertFalse(pickup_pool_for(self.driver).filter(order=order).exists())

    def test_pool_includes_failed_delivery_task(self):
        # Failed can be retried, so its first-mile pickup stays claimable
        order = self.make_order('PKS03')
        self.make_task(order, 'failed')
        self.assertTrue(pickup_pool_for(self.driver).filter(order=order).exists())

    def test_pool_includes_order_with_no_delivery_task(self):
        # Guards the NULL annotation trap — no task yet must not hide the pickup
        order = self.make_order('PKS04')
        self.assertFalse(DeliveryTask.objects.filter(order=order).exists())
        self.assertTrue(pickup_pool_for(self.driver).filter(order=order).exists())

    def test_pool_uses_latest_task_only(self):
        # Old cancelled task + newer live one (the reconfirm/retry case)
        order = self.make_order('PKS05')
        self.make_task(order, 'cancelled')
        self.make_task(order, 'pending')
        self.assertTrue(pickup_pool_for(self.driver).filter(order=order).exists())

    def test_task_cancel_cancels_pending_pickup(self):
        order = self.make_order('PKS06')
        task = self.make_task(order, 'pending')
        task.dl_task_status = 'cancelled'
        task.save(update_fields=['dl_task_status'])
        self.assertEqual(PickupTask.objects.get(order=order).status, 'cancelled')

    def test_task_delivered_cancels_pending_pickup(self):
        # Delivered without a first-mile pickup — the pickup is dead work
        order = self.make_order('PKS07')
        task = self.make_task(order, 'pending')
        task.dl_task_status = 'delivered'
        task.save(update_fields=['dl_task_status'])
        self.assertEqual(PickupTask.objects.get(order=order).status, 'cancelled')

    def test_executed_pickup_not_rewritten(self):
        # Already dropped at the hub — the work happened, the row must stand
        order = self.make_order('PKS08')
        pickup = PickupTask.objects.get(order=order)
        pickup.driver = self.driver
        pickup.status = 'dropped'
        pickup.save()
        task = self.make_task(order, 'pending')
        task.dl_task_status = 'cancelled'
        task.save(update_fields=['dl_task_status'])
        pickup.refresh_from_db()
        self.assertEqual(pickup.status, 'dropped')

    def test_collected_pickup_survives_cancelled_delivery(self):
        # Driver is holding the goods — the collection happened, so the pickup is
        # never relabelled 'cancelled'. It stays open so they can route or return it.
        order = self.make_order('PKS09')
        pickup = PickupTask.objects.get(order=order)
        pickup.driver = self.driver
        pickup.status = 'collected'
        pickup.save()
        task = self.make_task(order, 'pending')
        task.dl_task_status = 'cancelled'
        task.save(update_fields=['dl_task_status'])
        pickup.refresh_from_db()
        self.assertEqual(pickup.status, 'collected')
        self.assertTrue(fleet_models.DriverNotification.objects.filter(
            driver=self.driver, title='Pickup needs routing').exists())

    def test_collected_pickup_closes_as_handed_off_when_delivered(self):
        # The delivery leg finished — the first-mile work is done, not cancelled
        order = self.make_order('PKS10')
        pickup = PickupTask.objects.get(order=order)
        pickup.driver = self.driver
        pickup.status = 'collected'
        pickup.save()
        task = self.make_task(order, 'pending')
        task.dl_task_status = 'delivered'
        task.save(update_fields=['dl_task_status'])
        pickup.refresh_from_db()
        self.assertEqual(pickup.status, 'handed_off')
        self.assertFalse(fleet_models.DriverNotification.objects.filter(
            driver=self.driver, title='Pickup cancelled').exists())

    def test_pending_transfer_auto_confirms_when_target_delivers(self):
        # Nobody tapped "confirm hand-off", but the target driver delivered the
        # order — that is proof the hand-off happened.
        target = make_driver(7)
        order = self.make_order('PKS11')
        pickup = PickupTask.objects.get(order=order)
        pickup.driver = self.driver
        pickup.status = 'collected'
        pickup.disposition = 'transfer'
        pickup.transfer_to_driver = target
        pickup.save()
        task = self.make_task(order, 'pending')
        task.driver = target
        task.dl_task_status = 'delivered'
        task.save(update_fields=['driver', 'dl_task_status'])
        pickup.refresh_from_db()
        self.assertEqual(pickup.status, 'handed_off')
        self.assertIsNotNone(pickup.transfer_confirmed_at)

    def test_pending_transfer_not_confirmed_when_someone_else_delivers(self):
        target = make_driver(8)
        other = make_driver(9)
        order = self.make_order('PKS12')
        pickup = PickupTask.objects.get(order=order)
        pickup.driver = self.driver
        pickup.status = 'collected'
        pickup.disposition = 'transfer'
        pickup.transfer_to_driver = target
        pickup.save()
        task = self.make_task(order, 'pending')
        task.driver = other
        task.dl_task_status = 'delivered'
        task.save(update_fields=['driver', 'dl_task_status'])
        pickup.refresh_from_db()
        self.assertEqual(pickup.status, 'handed_off')
        self.assertIsNone(pickup.transfer_confirmed_at)


class PickupAcceptTestCase(PickupBaseTestCase):
    def test_atomic_accept_first_wins(self):
        order = self.make_order('PK020')
        pickup = PickupTask.objects.get(order=order)
        other = make_driver(5)

        self.client.force_login(self.driver.user)
        resp = self.client.post('/fleet/pickups/accept/', {'pickup_id': pickup.pk})
        self.assertTrue(resp.json()['success'])

        self.client.force_login(other.user)
        resp2 = self.client.post('/fleet/pickups/accept/', {'pickup_id': pickup.pk})
        self.assertFalse(resp2.json()['success'])

        pickup.refresh_from_db()
        self.assertEqual(pickup.driver_id, self.driver.pk)
        self.assertEqual(pickup.status, 'accepted')

    def test_accept_rejects_non_pool_task(self):
        self.business.pickup_mode_default = 'assigned'
        self.business.save(update_fields=['pickup_mode_default'])
        order = self.make_order('PK021')
        pickup = PickupTask.objects.get(order=order)
        outsider = make_driver(6)
        self.client.force_login(outsider.user)
        resp = self.client.post('/fleet/pickups/accept/', {'pickup_id': pickup.pk})
        self.assertFalse(resp.json()['success'])


class PickupDispositionTestCase(PickupBaseTestCase):
    def collected_pickup(self, code, disposition):
        order = self.make_order(code)
        pickup = PickupTask.objects.get(order=order)
        pickup.driver = self.driver
        pickup.disposition = disposition
        pickup.status = 'collected'
        pickup.save()
        return pickup

    def test_drop_creates_delivery_task_and_closes_pickup(self):
        pickup = self.collected_pickup('PK030', 'drop')
        ok, _ = pickup_service.execute_disposition(pickup)
        self.assertTrue(ok)
        pickup.refresh_from_db()
        self.assertEqual(pickup.status, 'dropped')
        task = DeliveryTask.objects.filter(order=pickup.order).first()
        self.assertIsNotNone(task)
        self.assertEqual(task.source_pickup_task_id, pickup.pk)
        self.assertFalse(task.dl_task_publish)
        self.assertIsNone(task.driver_id)

    def test_self_deliver_assigns_same_driver(self):
        pickup = self.collected_pickup('PK031', 'self_deliver')
        ok, _ = pickup_service.execute_disposition(pickup)
        self.assertTrue(ok)
        pickup.refresh_from_db()
        self.assertEqual(pickup.status, 'handed_off')
        task = DeliveryTask.objects.get(order=pickup.order)
        self.assertEqual(task.driver_id, self.driver.pk)
        self.assertTrue(task.dl_task_publish)
        self.assertEqual(task.dl_task_status, 'accepted')

    def test_transfer_requires_both_party_confirm(self):
        pickup = self.collected_pickup('PK032', 'transfer')
        target = make_driver(7)

        ok, _ = pickup_service.initiate_transfer(pickup, target)
        self.assertTrue(ok)
        pickup.refresh_from_db()
        self.assertEqual(pickup.status, 'collected')  # not final until confirmed
        self.assertFalse(DeliveryTask.objects.filter(order=pickup.order).exists())

        wrong = make_driver(8)
        ok_wrong, _ = pickup_service.confirm_transfer(pickup, wrong)
        self.assertFalse(ok_wrong)

        ok2, _ = pickup_service.confirm_transfer(pickup, target)
        self.assertTrue(ok2)
        pickup.refresh_from_db()
        self.assertEqual(pickup.status, 'handed_off')
        task = DeliveryTask.objects.get(order=pickup.order)
        self.assertEqual(task.driver_id, target.pk)
        self.assertTrue(task.dl_task_publish)

    def test_disposition_blocked_before_collect(self):
        order = self.make_order('PK033')
        pickup = PickupTask.objects.get(order=order)
        pickup.driver = self.driver
        pickup.status = 'accepted'
        pickup.save()
        ok, _ = pickup_service.execute_disposition(pickup)
        self.assertFalse(ok)


class WorkforcePickupFleetTestCase(PickupBaseTestCase):
    """Staff manage a client's pickup-allowed drivers (DriverDirectory) via workforce."""

    def setUp(self):
        super().setUp()
        self.staff = User.objects.create_user(
            username='pkstaff', password='x', is_staff=True)
        # Pickup pages are an Operations desk; StaffDepartmentMiddleware fails
        # closed, so the profile has to carry the department.
        core_models.Profile.objects.create(
            user=self.staff, is_staff=True, dept_operations=True)
        self.client.force_login(self.staff)

    def test_fleet_add_toggle_remove(self):
        # add
        resp = self.client.post('/workforce/pickup-automation/fleet/update/', {
            'action': 'add', 'business_id': self.business.business_id,
            'driver_id': self.driver.pk,
        })
        self.assertTrue(resp.json()['success'])
        row = DriverDirectory.objects.get(business=self.business, driver=self.driver)
        self.assertTrue(row.is_active)

        # list
        resp = self.client.get(f'/workforce/pickup-automation/fleet/{self.business.business_id}/')
        drivers = resp.json()['drivers']
        self.assertEqual(len(drivers), 1)
        self.assertEqual(drivers[0]['driver_id'], self.driver.pk)

        # toggle -> inactive hides assigned-mode pickups from this driver
        self.business.pickup_mode_default = 'assigned'
        self.business.save(update_fields=['pickup_mode_default'])
        order = self.make_order('PKF01')
        self.assertTrue(pickup_pool_for(self.driver).filter(order=order).exists())
        resp = self.client.post('/workforce/pickup-automation/fleet/update/', {
            'action': 'toggle', 'row_id': row.pk,
        })
        self.assertFalse(resp.json()['is_active'])
        self.assertFalse(pickup_pool_for(self.driver).filter(order=order).exists())

        # remove
        resp = self.client.post('/workforce/pickup-automation/fleet/update/', {
            'action': 'remove', 'row_id': row.pk,
        })
        self.assertTrue(resp.json()['success'])
        self.assertFalse(DriverDirectory.objects.filter(pk=row.pk).exists())

    def test_add_rejects_unapproved_driver(self):
        pending = make_driver(40, status='pending')
        resp = self.client.post('/workforce/pickup-automation/fleet/update/', {
            'action': 'add', 'business_id': self.business.business_id,
            'driver_id': pending.pk,
        })
        self.assertFalse(resp.json()['success'])

    def test_non_staff_blocked(self):
        self.client.force_login(self.driver.user)
        resp = self.client.post('/workforce/pickup-automation/fleet/update/', {
            'action': 'add', 'business_id': self.business.business_id,
            'driver_id': self.driver.pk,
        })
        # staff_required redirects non-staff away
        self.assertEqual(resp.status_code, 302)

    def test_driver_search(self):
        resp = self.client.get('/workforce/pickup-automation/fleet/search/?q=PKD')
        self.assertTrue(resp.json()['success'])
        self.assertTrue(any(d['code'] == 'PKD1' for d in resp.json()['drivers']))


class WorkforcePickupAssignTestCase(PickupBaseTestCase):
    """Staff assign/reassign a driver on a pickup from the pool status page."""

    def setUp(self):
        super().setUp()
        self.staff = User.objects.create_user(
            username='pkstaff2', password='x', is_staff=True)
        core_models.Profile.objects.create(
            user=self.staff, is_staff=True, dept_operations=True)
        self.client.force_login(self.staff)

    def test_staff_assign_pending_pickup(self):
        order = self.make_order('PKA01')
        pickup = PickupTask.objects.get(order=order)
        resp = self.client.post('/workforce/pickups/assign/', {
            'pickup_id': pickup.pk, 'driver_id': self.driver.pk,
        })
        self.assertTrue(resp.json()['success'])
        pickup.refresh_from_db()
        self.assertEqual(pickup.driver_id, self.driver.pk)
        self.assertEqual(pickup.status, 'accepted')
        self.assertTrue(fleet_models.DriverNotification.objects.filter(
            driver=self.driver, notification_type='pickup_available').exists())

    def test_staff_reassign_notifies_previous_driver(self):
        order = self.make_order('PKA02')
        pickup = PickupTask.objects.get(order=order)
        pickup.driver = self.driver
        pickup.status = 'accepted'
        pickup.save()
        other = make_driver(50)
        resp = self.client.post('/workforce/pickups/assign/', {
            'pickup_id': pickup.pk, 'driver_id': other.pk,
        })
        self.assertTrue(resp.json()['success'])
        pickup.refresh_from_db()
        self.assertEqual(pickup.driver_id, other.pk)
        self.assertTrue(fleet_models.DriverNotification.objects.filter(
            driver=self.driver, notification_type='alert').exists())

    def test_staff_assign_blocked_after_collection(self):
        order = self.make_order('PKA03')
        pickup = PickupTask.objects.get(order=order)
        pickup.driver = self.driver
        pickup.status = 'collected'
        pickup.save()
        other = make_driver(51)
        resp = self.client.post('/workforce/pickups/assign/', {
            'pickup_id': pickup.pk, 'driver_id': other.pk,
        })
        self.assertFalse(resp.json()['success'])

    def test_pool_status_page_renders(self):
        self.make_order('PKA04')
        resp = self.client.get('/workforce/pickups/')
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'PKA04')

    def test_pool_status_hides_handed_off_by_default(self):
        order = self.make_order('PKA05')
        pickup = PickupTask.objects.get(order=order)
        pickup.status = 'handed_off'
        pickup.save(update_fields=['status'])

        resp = self.client.get('/workforce/pickups/')
        self.assertNotContains(resp, order.order_number)
        # …but it is still one filter away
        resp_all = self.client.get('/workforce/pickups/', {'status': 'all'})
        self.assertContains(resp_all, order.order_number)

    def test_pool_status_hides_dropped_by_default(self):
        # A hub drop ends the first-mile leg exactly as a hand-off does.
        order = self.make_order('PKA05D')
        pickup = PickupTask.objects.get(order=order)
        pickup.status = 'dropped'
        pickup.save(update_fields=['status'])

        resp = self.client.get('/workforce/pickups/')
        self.assertNotContains(resp, order.order_number)
        resp_all = self.client.get('/workforce/pickups/', {'status': 'all'})
        self.assertContains(resp_all, order.order_number)

    def test_pool_status_keeps_cancelled_in_open(self):
        # Cancelled is closed but not finished work — staff still need to see it,
        # which is why 'open' is not the same filter as 'active'.
        order = self.make_order('PKA05C')
        pickup = PickupTask.objects.get(order=order)
        pickup.status = 'cancelled'
        pickup.save(update_fields=['status'])

        resp = self.client.get('/workforce/pickups/')
        self.assertContains(resp, order.order_number)
        resp_active = self.client.get('/workforce/pickups/', {'status': 'active'})
        self.assertNotContains(resp_active, order.order_number)

    def test_pool_status_defaults_to_last_7_days(self):
        old = self.make_order('PKA06')
        recent = self.make_order('PKA07')
        # created_at is auto_now_add, so backdate through the queryset
        PickupTask.objects.filter(order=old).update(
            created_at=timezone.now() - timedelta(days=10))

        resp = self.client.get('/workforce/pickups/')
        self.assertNotContains(resp, old.order_number)
        self.assertContains(resp, recent.order_number)

        resp_all = self.client.get('/workforce/pickups/', {'days': 'all'})
        self.assertContains(resp_all, old.order_number)

    def test_pool_status_custom_date_range_overrides_preset(self):
        order = self.make_order('PKA08')
        moment = timezone.now() - timedelta(days=45)
        PickupTask.objects.filter(order=order).update(created_at=moment)
        # The From/To boxes are read as Qatar dates (settings.TIME_ZONE), so the day
        # string has to be that instant's LOCAL date. Formatting the UTC date instead
        # shifted the window three hours and the test failed after 21:00 UTC.
        day = timezone.localtime(moment).strftime('%Y-%m-%d')

        # The To box is inclusive of its whole day, so a single-day range finds it
        resp = self.client.get('/workforce/pickups/', {'date_from': day, 'date_to': day})
        self.assertContains(resp, order.order_number)
        # A reversed pair is normalised rather than returning nothing
        resp_rev = self.client.get('/workforce/pickups/', {'date_from': day, 'date_to': day})
        self.assertContains(resp_rev, order.order_number)
        # Junk falls back to the 7-day default instead of erroring
        resp_junk = self.client.get('/workforce/pickups/', {'date_from': 'not-a-date'})
        self.assertEqual(resp_junk.status_code, 200)
        self.assertNotContains(resp_junk, order.order_number)

    def test_pool_status_flags_active_pickups_hidden_by_the_window(self):
        order = self.make_order('PKA09')
        PickupTask.objects.filter(order=order).update(
            created_at=timezone.now() - timedelta(days=40))  # still pending

        resp = self.client.get('/workforce/pickups/', {'days': '7'})
        self.assertNotContains(resp, order.order_number)
        self.assertContains(resp, 'ppl__windownote')
        self.assertEqual(resp.context['hidden_active'], 1)

        resp_all = self.client.get('/workforce/pickups/', {'days': 'all'})
        self.assertEqual(resp_all.context['hidden_active'], 0)


class WorkforcePickupCancelDeleteTestCase(PickupBaseTestCase):
    """Staff cancel (leg only) and superadmin delete from the pool status page."""

    def setUp(self):
        super().setUp()
        self.staff = User.objects.create_user(
            username='pkstaff3', password='x', is_staff=True)
        self.staff_profile = core_models.Profile.objects.create(
            user=self.staff, is_staff=True, dept_operations=True)
        self.client.force_login(self.staff)

    def _claimed_pickup(self, code, status='accepted'):
        order = self.make_order(code)
        pickup = PickupTask.objects.get(order=order)
        pickup.driver = self.driver
        pickup.status = status
        pickup.save()
        return order, pickup

    # -- cancel ------------------------------------------------------------
    def test_cancel_closes_leg_and_notifies_driver(self):
        order, pickup = self._claimed_pickup('PKC01')
        resp = self.client.post('/workforce/pickups/cancel/', {
            'pickup_id': pickup.pk, 'reason': 'Client rescheduled',
        })
        self.assertTrue(resp.json()['success'])
        pickup.refresh_from_db()
        self.assertEqual(pickup.status, 'cancelled')
        self.assertTrue(fleet_models.DriverNotification.objects.filter(
            driver=self.driver, title='Pickup cancelled').exists())
        # The order itself is untouched — only the first-mile leg died.
        order.refresh_from_db()
        self.assertNotEqual(order.order_status, 'cancelled')
        self.assertTrue(orders_models.OrderStatusHistory.objects.filter(
            order=order, field_name='pickup_status', new_value='cancelled',
            changed_by=self.staff).exists())

    def test_cancel_allowed_after_collection(self):
        _, pickup = self._claimed_pickup('PKC02', status='collected')
        resp = self.client.post('/workforce/pickups/cancel/', {'pickup_id': pickup.pk})
        self.assertTrue(resp.json()['success'])
        pickup.refresh_from_db()
        self.assertEqual(pickup.status, 'cancelled')

    def test_cancel_refused_on_closed_leg(self):
        _, pickup = self._claimed_pickup('PKC03', status='dropped')
        resp = self.client.post('/workforce/pickups/cancel/', {'pickup_id': pickup.pk})
        self.assertFalse(resp.json()['success'])
        pickup.refresh_from_db()
        self.assertEqual(pickup.status, 'dropped')

    def test_bulk_cancel_reports_skipped(self):
        _, live = self._claimed_pickup('PKC04')
        _, closed = self._claimed_pickup('PKC05', status='handed_off')
        resp = self.client.post('/workforce/pickups/cancel/', {
            'pickup_ids': [live.pk, closed.pk],
        })
        data = resp.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['updated'], 1)
        self.assertEqual(len(data['failed']), 1)

    # -- delete ------------------------------------------------------------
    def test_delete_blocked_for_non_superadmin(self):
        _, pickup = self._claimed_pickup('PKD01')
        resp = self.client.post('/workforce/pickups/delete/', {'pickup_id': pickup.pk})
        self.assertEqual(resp.status_code, 403)
        self.assertTrue(PickupTask.objects.filter(pk=pickup.pk).exists())

    def test_superadmin_deletes_row_and_leaves_order(self):
        self.staff_profile.is_superadmin = True
        self.staff_profile.save(update_fields=['is_superadmin'])
        order, pickup = self._claimed_pickup('PKD02')
        resp = self.client.post('/workforce/pickups/delete/', {'pickup_id': pickup.pk})
        self.assertTrue(resp.json()['success'])
        self.assertFalse(PickupTask.objects.filter(pk=pickup.pk).exists())
        self.assertTrue(Order.objects.filter(pk=order.pk).exists())
        self.assertTrue(orders_models.OrderStatusHistory.objects.filter(
            order=order, field_name='pickup_status', new_value='deleted').exists())
        self.assertTrue(fleet_models.DriverNotification.objects.filter(
            driver=self.driver, title='Pickup removed').exists())

    def test_delete_refused_after_collection(self):
        self.staff_profile.is_superadmin = True
        self.staff_profile.save(update_fields=['is_superadmin'])
        _, pickup = self._claimed_pickup('PKD03', status='collected')
        resp = self.client.post('/workforce/pickups/delete/', {'pickup_id': pickup.pk})
        self.assertFalse(resp.json()['success'])
        self.assertTrue(PickupTask.objects.filter(pk=pickup.pk).exists())


class PickupDeliveryClaimTestCase(PickupBaseTestCase):
    """Taking the delivery task IS the hand-off — the first-mile leg closes with it.

    Drivers skip the Pickup tab's 'Deliver myself' / 'Confirm hand-off' buttons and
    grab the job from the New pool instead, which used to leave the leg stuck at
    'collected' for the whole delivery.
    """

    def setUp(self):
        super().setUp()
        self.target = make_driver(20)
        self.outsider = make_driver(21)

    def collected_with_pool_task(self, code, disposition='transfer', transfer_to=None):
        """A collected pickup whose delivery task is published and unclaimed."""
        from orders.signals import _create_delivery_task_from_order

        order = self.make_order(code)
        pickup = PickupTask.objects.get(order=order)
        pickup.driver = self.driver
        pickup.disposition = disposition
        pickup.status = 'collected'
        pickup.collected_at = timezone.now()
        if transfer_to:
            pickup.transfer_to_driver = transfer_to
            pickup.transfer_initiated_at = timezone.now()
        pickup.save()

        task = _create_delivery_task_from_order(order)
        task.dl_task_publish = True
        task.dl_task_status = 'pending'
        task.save(update_fields=['dl_task_publish', 'dl_task_status'])
        return pickup, task

    def claim(self, task, driver):
        """What every claim path boils down to: the driver lands on the task row."""
        task.driver = driver
        task.dl_task_status = 'accepted'
        task._status_actor = 'driver'
        task.save(update_fields=['driver', 'dl_task_status'])
        return task

    # -- reconcile ---------------------------------------------------------
    def test_transfer_target_claiming_task_confirms_and_closes(self):
        pickup, task = self.collected_with_pool_task('PKR01', transfer_to=self.target)
        self.claim(task, self.target)

        pickup.refresh_from_db()
        task.refresh_from_db()
        self.assertEqual(pickup.status, 'handed_off')
        self.assertIsNotNone(pickup.transfer_confirmed_at)
        self.assertEqual(task.source_pickup_task_id, pickup.pk)
        self.assertTrue(orders_models.OrderStatusHistory.objects.filter(
            order=pickup.order, field_name='pickup_status', new_value='handed_off').exists())

    def test_collecting_driver_claiming_task_closes_as_self_deliver(self):
        pickup, task = self.collected_with_pool_task('PKR02', disposition='drop')
        self.claim(task, self.driver)

        pickup.refresh_from_db()
        self.assertEqual(pickup.status, 'handed_off')
        self.assertIsNone(pickup.transfer_confirmed_at)
        self.assertFalse(fleet_models.DriverNotification.objects.filter(
            title='Hand over the parcel').exists())

    def test_third_driver_claim_closes_leg_and_warns_both(self):
        pickup, task = self.collected_with_pool_task('PKR03', transfer_to=self.target)
        self.claim(task, self.outsider)

        pickup.refresh_from_db()
        self.assertEqual(pickup.status, 'handed_off')
        self.assertIsNone(pickup.transfer_confirmed_at)  # that hand-off never happened
        self.assertTrue(fleet_models.DriverNotification.objects.filter(
            driver=self.driver, title='Hand over the parcel').exists())
        self.assertTrue(fleet_models.DriverNotification.objects.filter(
            driver=self.outsider, title='Collect the parcel first').exists())

    def test_disposition_flow_closes_the_leg_only_once(self):
        """_hand_delivery_to writes the driver too — the signal must not double up."""
        order = self.make_order('PKR04')
        pickup = PickupTask.objects.get(order=order)
        pickup.driver = self.driver
        pickup.disposition = 'self_deliver'
        pickup.status = 'collected'
        pickup.save()

        ok, _ = pickup_service.execute_disposition(pickup)
        self.assertTrue(ok)
        pickup.refresh_from_db()
        self.assertEqual(pickup.status, 'handed_off')
        self.assertEqual(orders_models.OrderStatusHistory.objects.filter(
            order=order, field_name='pickup_status', new_value='handed_off').count(), 1)

    # -- pool visibility ---------------------------------------------------
    def test_held_parcel_hidden_from_other_drivers_pool(self):
        from delivery.selectors import exclude_held_parcels

        pickup, task = self.collected_with_pool_task('PKR05', transfer_to=self.target)
        pool = DeliveryTask.objects.filter(pk=task.pk)

        self.assertFalse(exclude_held_parcels(pool, self.outsider).exists())
        self.assertTrue(exclude_held_parcels(pool, self.driver).exists())   # holder
        self.assertTrue(exclude_held_parcels(pool, self.target).exists())   # transfer target

        # Once the leg is off 'collected' the parcel is at the hub — open to all.
        pickup.status = 'dropped'
        pickup.save(update_fields=['status'])
        self.assertTrue(exclude_held_parcels(pool, self.outsider).exists())

    def test_claim_endpoint_refuses_third_driver(self):
        pickup, task = self.collected_with_pool_task('PKR06', transfer_to=self.target)
        self.client.force_login(self.outsider.user)
        resp = self.client.post('/delivery/delivery_task/assign_driver/', {'task_id': task.pk})
        body = resp.json()
        self.assertFalse(body['success'])
        self.assertIn('parcel is with', body['error'])
        task.refresh_from_db()
        pickup.refresh_from_db()
        self.assertIsNone(task.driver_id)
        self.assertEqual(pickup.status, 'collected')

    # -- staff close -------------------------------------------------------
    def test_staff_close_uses_the_delivery_driver(self):
        staff = User.objects.create_user(username='pkstaff9', password='x', is_staff=True)
        core_models.Profile.objects.create(user=staff, is_staff=True, dept_operations=True)
        pickup, task = self.collected_with_pool_task('PKR07', transfer_to=self.target)
        task.driver = self.target
        task.save(update_fields=['driver'])
        pickup.refresh_from_db()
        pickup.status = 'collected'          # the signal already closed it; re-open to test the lever
        pickup.transfer_confirmed_at = None
        pickup.save(update_fields=['status', 'transfer_confirmed_at'])

        self.client.force_login(staff)
        resp = self.client.post('/workforce/pickups/close/', {'pickup_id': pickup.pk})
        self.assertTrue(resp.json()['success'])
        pickup.refresh_from_db()
        self.assertEqual(pickup.status, 'handed_off')
        self.assertIsNotNone(pickup.transfer_confirmed_at)

    def test_staff_close_refused_before_collection(self):
        staff = User.objects.create_user(username='pkstaff10', password='x', is_staff=True)
        core_models.Profile.objects.create(user=staff, is_staff=True, dept_operations=True)
        order = self.make_order('PKR08')
        pickup = PickupTask.objects.get(order=order)

        self.client.force_login(staff)
        resp = self.client.post('/workforce/pickups/close/', {'pickup_id': pickup.pk})
        self.assertFalse(resp.json()['success'])
        pickup.refresh_from_db()
        self.assertEqual(pickup.status, 'pending')
