# Purpose: Tests for first-mile pickup — creation gating, pool scoping, atomic accept, dispositions
# Used by: python manage.py test delivery.tests_pickup

from django.test import TestCase
from django.contrib.auth import get_user_model

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
