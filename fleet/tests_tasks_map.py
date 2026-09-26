"""
Purpose: The PWA tasks map must carry a full task card per pin so a pin opens the
         shared detail sheet, and must only offer Take on a genuinely claimable task.
Used by: manage.py test fleet.tests_tasks_map
Notes: The map's pool query has to track the Tasks page "New" tab exactly — an
       unpublished or already-claimed task showing a Take button is a dead button.
"""
import json
import re
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings

from business import models as business_models
from core import models as core_models
from delivery import models as delivery_models
from fleet import models as fleet_models
from orders import models as orders_models

User = get_user_model()


@override_settings(SECURE_SSL_REDIRECT=False, ALLOWED_HOSTS=['testserver'],
                   DRIVER_DEVICE_ENFORCEMENT=False)
class TasksMapPinCardTests(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            username='mapdriver', email='mapdriver@test.com', password='TestDriver@123')
        self.profile = core_models.Profile.objects.create(
            user=self.user, first_name='Map', last_name='Driver',
            phone=55512399, whatsapp=55512399, is_driver=True)
        self.driver = fleet_models.Driver.objects.create(
            driver_id=7701, user=self.user, profile=self.profile,
            driver_code='DRVMAP', driver_phone='55512399', driver_whatsapp='55512399',
            driver_status='approved', dashboard_access_enabled=True)

        biz_user = User.objects.create_user(
            username='mapbiz', email='mapbiz@test.com', password='TestDriver@123')
        biz_profile = core_models.Profile.objects.create(
            user=biz_user, first_name='Map', last_name='Biz', phone=55500099, is_business=True)
        self.business = business_models.Business.objects.create(
            business_id=771, user=biz_user, profile=biz_profile,
            business_name='Map Test Store', business_code='MAPB001', business_status='active')
        self.pickup = business_models.PickupLocation.objects.create(
            business=self.business, pickup_location_title='Map Warehouse', locality='Doha',
            pickup_zone_no=70, pickup_street_no=700, pickup_building_no=7000,
            pickup_status='active')

        self.client = Client()
        self.client.force_login(self.user)

    def _order(self, code):
        return orders_models.Order.objects.create(
            business=self.business, client_order_code=code,
            customer_name='Map Customer', customer_phone='33344455',
            customer_address='Map Address Doha', dl_zone=70, dl_building=7000, dl_street=700,
            latitude=Decimal('25.2854'), longitude=Decimal('51.5310'),
            pickup_location=self.pickup, cod_amount=Decimal('150.00'))

    def _task(self, code, status, publish=True, driver=None):
        return delivery_models.DeliveryTask.objects.create(
            order=self._order(code), business=self.business, pickup_location=self.pickup,
            driver=driver, dl_task_number=code, dl_task_status=status,
            dl_task_publish=publish, dl_task_description='Map test task')

    def _get_map(self):
        response = self.client.get('/fleet/tasks/map/')
        self.assertEqual(response.status_code, 200)
        return response.content.decode()

    @staticmethod
    def _pins(body):
        # With nothing to plot the template renders the empty state instead of
        # the map, so there is no pins array at all.
        match = re.search(r'var pins = (\[.*?\]);', body, re.S)
        return json.loads(match.group(1)) if match else []

    def test_each_pin_gets_a_hidden_task_card(self):
        """The detail sheet reads a .task-card — without one the pin's button is dead."""
        task = self._task('MAP-ACTIVE-1', 'accepted', driver=self.driver)
        body = self._get_map()

        self.assertIn(f'id="mapTaskCard{task.id}"', body)
        self.assertIn('class="map-task-cards"', body)
        # The sheet reads these three payloads off the card.
        self.assertIn('task-address-data', body)
        self.assertIn('task-products-data', body)
        self.assertIn(f'data-tasknum="{task.dl_task_number}"', body)

    def test_a_task_with_no_coordinates_gets_no_card(self):
        """No coordinates means no pin, and a card nothing can open is dead weight."""
        task = self._task('MAP-NOGEO-1', 'accepted', driver=self.driver)
        orders_models.Order.objects.filter(id=task.order_id).update(latitude=None, longitude=None)

        body = self._get_map()
        self.assertNotIn(f'id="mapTaskCard{task.id}"', body)

    def test_own_task_is_not_takeable(self):
        """data-takeable drives the sheet's Take button; an assigned task must not show it."""
        task = self._task('MAP-MINE-1', 'accepted', driver=self.driver)
        body = self._get_map()

        card = re.search(r'id="mapTaskCard%d".*?data-takeable="(\d)"' % task.id, body, re.S)
        self.assertEqual(card.group(1), '0')

    def test_pool_task_is_pinned_and_takeable(self):
        task = self._task('MAP-POOL-1', 'pending')
        body = self._get_map()

        pins = self._pins(body)
        self.assertEqual([p['id'] for p in pins], [task.id])
        self.assertTrue(pins[0]['is_new'])
        self.assertEqual(pins[0]['business'], 'Map Test Store')
        card = re.search(r'id="mapTaskCard%d".*?data-takeable="(\d)"' % task.id, body, re.S)
        self.assertEqual(card.group(1), '1')

    def test_unpublished_pool_task_is_not_pinned(self):
        """It is not takeable, so a Take button on it would only ever fail."""
        self._task('MAP-UNPUB-1', 'pending', publish=False)
        self.assertEqual(self._pins(self._get_map()), [])

    def test_the_map_is_closed_to_a_driver_who_is_not_approved(self):
        """DriverStatusCheckMiddleware signs them out of the whole /fleet/ tree."""
        self._task('MAP-POOL-2', 'pending')
        fleet_models.Driver.objects.filter(pk=self.driver.pk).update(driver_status='suspended')

        response = self.client.get('/fleet/tasks/map/')
        self.assertRedirects(response, '/accounts/login/', fetch_redirect_response=False)

    def test_take_from_the_map_claims_the_task(self):
        """The popup and the sheet both post here with the task number as the code."""
        task = self._task('MAP-POOL-3', 'pending')

        response = self.client.post(
            '/fleet/tasks/take-scan/',
            data=json.dumps({'task_id': task.id, 'code': task.dl_task_number}),
            content_type='application/json')

        self.assertTrue(response.json()['success'], response.json())
        task.refresh_from_db()
        self.assertEqual(task.driver_id, self.driver.pk)
        self.assertEqual(task.dl_task_status, 'accepted')

    def test_take_is_refused_for_a_driver_who_is_not_approved(self):
        """`processing` clears the middleware but must not be able to claim work."""
        task = self._task('MAP-POOL-4', 'pending')
        fleet_models.Driver.objects.filter(pk=self.driver.pk).update(driver_status='processing')

        response = self.client.post(
            '/fleet/tasks/take-scan/',
            data=json.dumps({'task_id': task.id, 'code': task.dl_task_number}),
            content_type='application/json')

        self.assertFalse(response.json()['success'])
        task.refresh_from_db()
        self.assertIsNone(task.driver_id)
