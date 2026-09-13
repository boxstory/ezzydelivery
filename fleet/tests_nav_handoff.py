"""
Purpose: Cover the external-navigation handoff — the record that explains the trail gap a
         driver opens by tapping Waze, and the two independent ways it gets closed again.
Used by: `python manage.py test fleet.tests_nav_handoff`
Notes:   OSRM is patched out everywhere; reconstruction is an optional extra and none of
         these behaviours may depend on the routing service being up.
"""
import json
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.utils import timezone

from core import models as core_models
from fleet.models import Driver, DriverLocation, DriverNavHandoff
from workforce.tests_views import WorkforceTestMixin

DOHA = (25.2854, 51.5310)
LUSAIL = (25.4106, 51.4900)


class NavHandoffTests(TestCase):
    """A driver leaves for Waze, and the gap that opens is accounted for."""

    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username='nav_driver', password='nav-pw-12345')
        profile = core_models.Profile.objects.create(
            user=self.user, is_driver=True, whatsapp='97412345678')
        self.driver = Driver.objects.create(
            driver_id=9501, user=self.user, profile=profile, driver_code='NAV1',
            driver_phone='97412345678', driver_whatsapp='97412345678',
            driver_languages='english', driver_status='approved',
        )
        self.client = Client()
        self.client.force_login(self.user)

    def _fix(self, point, minutes_ago=0):
        loc = DriverLocation.objects.create(
            driver=self.driver, latitude=point[0], longitude=point[1], accuracy=12,
            fixed_at=timezone.now() - timezone.timedelta(minutes=minutes_ago),
        )
        if minutes_ago:
            DriverLocation.objects.filter(pk=loc.pk).update(
                created_at=timezone.now() - timezone.timedelta(minutes=minutes_ago))
        return loc

    def _open(self, **body):
        payload = {'event': 'open', 'provider': 'waze',
                   'dest_lat': LUSAIL[0], 'dest_lng': LUSAIL[1]}
        payload.update(body)
        return self.client.post('/api/driver/nav-handoff/', data=json.dumps(payload),
                                content_type='application/json')

    def _ping(self, point, **extra):
        body = {'latitude': point[0], 'longitude': point[1], 'accuracy': 10,
                'fixed_at': timezone.now().isoformat()}
        body.update(extra)
        return self.client.post('/api/driver/location/', data=json.dumps(body),
                                content_type='application/json')

    def test_open_records_where_the_driver_left_from(self):
        self._fix(DOHA)
        resp = self._open()
        self.assertEqual(resp.status_code, 201)

        handoff = DriverNavHandoff.objects.get(pk=resp.json()['id'])
        self.assertTrue(handoff.is_open)
        self.assertEqual(handoff.provider, 'waze')
        self.assertAlmostEqual(float(handoff.from_latitude), DOHA[0], places=4)
        self.assertAlmostEqual(float(handoff.dest_latitude), LUSAIL[0], places=4)

    def test_another_drivers_task_is_not_accepted(self):
        """A task id only sticks when the driver actually holds that task."""
        self._fix(DOHA)
        resp = self._open(task_id=999999)
        self.assertEqual(resp.status_code, 201)
        self.assertIsNone(DriverNavHandoff.objects.get(pk=resp.json()['id']).task_id)

    def test_a_pickup_leg_handoff_is_attributed_to_its_pickup(self):
        """The first-mile buttons leave the app too, and a PickupTask id is not
        a DeliveryTask id — storing one in the other's column would blame a
        delivery that merely shares the number."""
        from delivery.models import PickupTask

        helper = WorkforceTestMixin()
        biz = helper.create_business(bid=9600, code='NAVB')
        loc = helper.create_pickup_location(biz)
        order = helper.create_order(biz, pickup_location=loc)
        pickup = PickupTask.objects.create(
            order=order, business=biz, pickup_location=loc, driver=self.driver)

        self._fix(DOHA)
        resp = self._open(pickup_task_id=pickup.pk)
        handoff = DriverNavHandoff.objects.get(pk=resp.json()['id'])
        self.assertEqual(handoff.pickup_task_id, pickup.pk)
        self.assertIsNone(handoff.task_id)

    def test_a_pickup_belonging_to_another_driver_is_not_accepted(self):
        self._fix(DOHA)
        resp = self._open(pickup_task_id=999999)
        self.assertIsNone(DriverNavHandoff.objects.get(pk=resp.json()['id']).pickup_task_id)

    def test_goodbye_ping_does_not_read_as_a_return(self):
        """The keepalive fired as the page hides lands right behind the handoff."""
        self._fix(DOHA)
        self._open()
        self._ping((25.2860, 51.5320))
        self.assertTrue(DriverNavHandoff.objects.get().is_open)

    @patch('delivery.routing.route_leg', return_value=None)
    def test_live_ping_after_the_gap_closes_it(self, _route):
        self._fix(DOHA)
        handoff = DriverNavHandoff.objects.get(pk=self._open().json()['id'])
        DriverNavHandoff.objects.filter(pk=handoff.pk).update(
            opened_at=timezone.now() - timezone.timedelta(minutes=12))

        self._ping(LUSAIL)

        handoff.refresh_from_db()
        self.assertFalse(handoff.is_open)
        self.assertAlmostEqual(float(handoff.to_latitude), LUSAIL[0], places=4)

    @patch('delivery.routing.route_leg', return_value=None)
    def test_a_replayed_ping_is_not_a_return(self, _route):
        """A background sync draining the queue says nothing about the driver."""
        self._fix(DOHA)
        handoff = DriverNavHandoff.objects.get(pk=self._open().json()['id'])
        DriverNavHandoff.objects.filter(pk=handoff.pk).update(
            opened_at=timezone.now() - timezone.timedelta(minutes=12))

        self._ping(LUSAIL, queued=True)

        handoff.refresh_from_db()
        self.assertTrue(handoff.is_open)

    @patch('delivery.routing.route_leg', return_value=None)
    def test_explicit_return_closes_when_no_ping_arrived(self, _route):
        """GPS may fail on return; the gap still has to end."""
        self._fix(DOHA)
        handoff = DriverNavHandoff.objects.get(pk=self._open().json()['id'])
        DriverNavHandoff.objects.filter(pk=handoff.pk).update(
            opened_at=timezone.now() - timezone.timedelta(minutes=8))

        resp = self.client.post('/api/driver/nav-handoff/',
                                data=json.dumps({'event': 'return'}),
                                content_type='application/json')
        self.assertEqual(resp.status_code, 200)
        handoff.refresh_from_db()
        self.assertFalse(handoff.is_open)

    def test_every_app_that_takes_the_foreground_is_accepted(self):
        self._fix(DOHA)
        for provider, label in DriverNavHandoff.PROVIDERS:
            resp = self._open(provider=provider)
            self.assertEqual(resp.status_code, 201, provider)
            handoff = DriverNavHandoff.objects.get(pk=resp.json()['id'])
            self.assertEqual(handoff.provider, provider)
            self.assertTrue(handoff.status_label.strip())

    def test_an_unknown_provider_falls_back_rather_than_failing(self):
        self._fix(DOHA)
        resp = self._open(provider='telegram')
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(
            DriverNavHandoff.objects.get(pk=resp.json()['id']).provider, 'other')

    def _background(self):
        return self.client.post('/api/driver/nav-handoff/',
                                data=json.dumps({'event': 'background'}),
                                content_type='application/json')

    def test_losing_the_foreground_is_recorded_even_with_no_link_tapped(self):
        """Most trail holes start with a locked screen, not a button."""
        self._fix(DOHA)
        resp = self._background()
        self.assertEqual(resp.status_code, 201)
        handoff = DriverNavHandoff.objects.get(pk=resp.json()['id'])
        self.assertTrue(handoff.auto)
        self.assertEqual(handoff.provider, 'background')
        self.assertEqual(handoff.status_label, 'App in background')
        self.assertAlmostEqual(float(handoff.from_latitude), DOHA[0], places=4)

    def test_a_link_tap_already_explains_the_gap(self):
        """The hide that follows a tap must not open a second record."""
        self._fix(DOHA)
        self._open()
        self._background()
        self.assertEqual(DriverNavHandoff.objects.count(), 1)
        self.assertEqual(DriverNavHandoff.objects.get().provider, 'waze')

    @patch('delivery.routing.route_leg', return_value=None)
    def test_a_glance_at_a_notification_leaves_nothing_behind(self, _route):
        """A background spell too short to cost a fix is noise, not a record."""
        self._fix(DOHA)
        handoff = DriverNavHandoff.objects.get(pk=self._background().json()['id'])
        DriverNavHandoff.objects.filter(pk=handoff.pk).update(
            opened_at=timezone.now() - timezone.timedelta(seconds=10))

        self.client.post('/api/driver/nav-handoff/',
                         data=json.dumps({'event': 'return', 'left_foreground': True}),
                         content_type='application/json')
        self.assertEqual(DriverNavHandoff.objects.count(), 0)

    @patch('delivery.routing.route_leg', return_value=None)
    def test_a_real_background_spell_is_kept(self, _route):
        self._fix(DOHA)
        handoff = DriverNavHandoff.objects.get(pk=self._background().json()['id'])
        DriverNavHandoff.objects.filter(pk=handoff.pk).update(
            opened_at=timezone.now() - timezone.timedelta(minutes=10))

        self.client.post('/api/driver/nav-handoff/',
                         data=json.dumps({'event': 'return', 'left_foreground': True}),
                         content_type='application/json')
        handoff.refresh_from_db()
        self.assertFalse(handoff.is_open)
        self.assertEqual(handoff.close_reason, 'return')
        self.assertTrue(handoff.left_foreground)

    @patch('delivery.routing.route_leg', return_value=None)
    def test_a_zero_second_tap_records_that_the_app_never_left(self, _route):
        """The diagnosis for a handoff that closes instantly: did the app go
        away at all, and what closed it."""
        self._fix(DOHA)
        handoff = DriverNavHandoff.objects.get(pk=self._open().json()['id'])

        self.client.post('/api/driver/nav-handoff/',
                         data=json.dumps({'event': 'return', 'left_foreground': False}),
                         content_type='application/json')

        handoff.refresh_from_db()
        self.assertEqual(handoff.close_reason, 'return')
        self.assertFalse(handoff.left_foreground)
        self.assertEqual(handoff.gap_seconds, 0)

    def test_reopening_never_stacks_two_open_handoffs(self):
        self._fix(DOHA)
        self._open()
        self._open(provider='google')
        self.assertEqual(
            DriverNavHandoff.objects.filter(returned_at__isnull=True).count(), 1)
        closed = DriverNavHandoff.objects.filter(returned_at__isnull=False).first()
        self.assertEqual(closed.close_reason, 'superseded')

    def test_a_handoff_nobody_closed_stops_claiming_the_driver_is_driving(self):
        self._fix(DOHA)
        handoff = DriverNavHandoff.objects.get(pk=self._open().json()['id'])
        DriverNavHandoff.objects.filter(pk=handoff.pk).update(
            opened_at=timezone.now() - timezone.timedelta(
                minutes=DriverNavHandoff.MAX_OPEN_MINUTES + 5))

        self.assertIsNone(DriverNavHandoff.open_for_driver(self.driver.pk))
        self.assertEqual(DriverNavHandoff.open_map([self.driver.pk]), {})

    @patch('delivery.routing.route_leg')
    def test_the_gap_is_reconstructed_from_the_routing_engine(self, route_leg):
        route_leg.return_value = {'points': [[25.28, 51.53], [25.41, 51.49]], 'km': 14.2}
        self._fix(DOHA)
        handoff = DriverNavHandoff.objects.get(pk=self._open().json()['id'])
        DriverNavHandoff.objects.filter(pk=handoff.pk).update(
            opened_at=timezone.now() - timezone.timedelta(minutes=12))

        self._ping(LUSAIL)

        handoff.refresh_from_db()
        self.assertEqual(handoff.route_km, 14.2)
        self.assertEqual(len(handoff.route_points()), 2)

    @patch('delivery.routing.route_leg')
    def test_a_glance_at_the_map_leaves_no_route_to_draw(self, route_leg):
        """Under a minute out is not a gap worth reconstructing."""
        self._fix(DOHA)
        handoff = DriverNavHandoff.objects.get(pk=self._open().json()['id'])
        DriverNavHandoff.objects.filter(pk=handoff.pk).update(
            opened_at=timezone.now() - timezone.timedelta(seconds=40))

        handoff.refresh_from_db()
        handoff.close(fix=self._fix(DOHA))

        route_leg.assert_not_called()
        self.assertEqual(handoff.route_points(), [])


class NavHandoffOnTheLiveMapTests(WorkforceTestMixin, TestCase):
    """What dispatch sees while a driver is inside a nav app."""

    def setUp(self):
        User = get_user_model()
        self.user, self.profile = self.create_staff_user()
        self.client = Client()
        self.staff_login()

        driver_user = User.objects.create_user(username='map_driver', password='map-pw-12345')
        driver_profile = core_models.Profile.objects.create(
            user=driver_user, is_driver=True, whatsapp='97412345679')
        self.driver = Driver.objects.create(
            driver_id=9502, user=driver_user, profile=driver_profile, driver_code='NAV2',
            driver_phone='97412345679', driver_whatsapp='97412345679',
            driver_languages='english', driver_status='approved',
        )
        DriverLocation.objects.create(
            driver=self.driver, latitude=DOHA[0], longitude=DOHA[1], accuracy=12,
            fixed_at=timezone.now(),
        )

    def _drivers(self):
        resp = self.client.get('/workforce/tasks/live-map/',
                               HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(resp.status_code, 200)
        return {d['driver_id']: d for d in resp.json()['drivers']}

    def test_a_driver_not_in_a_nav_app_carries_no_nav_block(self):
        self.assertIsNone(self._drivers()[self.driver.pk].get('nav'))

    def test_a_driver_in_waze_is_labelled_rather_than_left_looking_dead(self):
        DriverNavHandoff.objects.create(
            driver=self.driver, provider='waze',
            opened_at=timezone.now() - timezone.timedelta(minutes=7),
            from_latitude=DOHA[0], from_longitude=DOHA[1],
            dest_latitude=LUSAIL[0], dest_longitude=LUSAIL[1],
        )
        nav = self._drivers()[self.driver.pk]['nav']
        self.assertEqual(nav['status'], 'In Waze')
        self.assertEqual(nav['minutes'], 7)
        self.assertAlmostEqual(nav['dest_lat'], LUSAIL[0], places=4)

    def test_a_call_says_so_rather_than_claiming_a_drive(self):
        """Every app that takes the foreground opens the same gap — the marker
        has to name the right one."""
        DriverNavHandoff.objects.create(
            driver=self.driver, provider='phone',
            opened_at=timezone.now() - timezone.timedelta(minutes=2),
        )
        self.assertEqual(self._drivers()[self.driver.pk]['nav']['status'], 'On a call')

    def test_a_closed_handoff_stops_explaining_anything(self):
        DriverNavHandoff.objects.create(
            driver=self.driver, provider='waze',
            opened_at=timezone.now() - timezone.timedelta(minutes=20),
            returned_at=timezone.now() - timezone.timedelta(minutes=5),
        )
        self.assertIsNone(self._drivers()[self.driver.pk].get('nav'))


class TrackingModuleLoadingTests(TestCase):
    """Who gets the GPS module, and who is never asked for their location."""

    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username='legacy_driver', password='leg-pw-12345')
        profile = core_models.Profile.objects.create(
            user=self.user, is_driver=True, whatsapp='97412345670')
        Driver.objects.create(
            driver_id=9503, user=self.user, profile=profile, driver_code='NAV3',
            driver_phone='97412345670', driver_whatsapp='97412345670',
            driver_languages='english', driver_status='approved',
        )
        self.client = Client()

    def test_the_older_task_list_now_tracks_like_the_pwa(self):
        """/delivery/ pages share the PWA's single GPS consumer — without it a
        driver working from there reported nothing at all."""
        self.client.force_login(self.user)
        resp = self.client.get('/delivery/delivery_tasks/all/')
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'fleet/js/ezzy-gps.js')
        self.assertContains(resp, 'EZZY_GPS_CONFIG')

    def test_the_pwa_still_ships_the_module_after_the_extraction(self):
        """It used to be inline in pwa_base.html; both bases now load one copy."""
        self.client.force_login(self.user)
        resp = self.client.get('/fleet/tasks/')
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'fleet/js/ezzy-gps.js')
        self.assertContains(resp, 'fleet/js/ezzy-gps-queue.js')

    def test_a_user_with_no_driver_row_is_never_asked_for_a_position(self):
        """The same base template carries a few staff screens."""
        User = get_user_model()
        staff = User.objects.create_user(
            username='cod_staff', password='staff-pw-12345', is_staff=True)
        core_models.Profile.objects.create(user=staff, is_staff=True)
        self.client.force_login(staff)
        resp = self.client.get('/fleet/staff/cod-submissions/')
        self.assertEqual(resp.status_code, 200)
        self.assertNotContains(resp, 'fleet/js/ezzy-gps.js')


class DriverTimelineTests(WorkforceTestMixin, TestCase):
    """One driver's day on a map: the trail, the stops, and the holes."""

    def setUp(self):
        User = get_user_model()
        self.user, self.profile = self.create_staff_user()
        self.client = Client()
        self.staff_login()

        driver_user = User.objects.create_user(username='tl_driver', password='tl-pw-12345')
        driver_profile = core_models.Profile.objects.create(
            user=driver_user, is_driver=True, whatsapp='97412345671')
        self.driver = Driver.objects.create(
            driver_id=9504, user=driver_user, profile=driver_profile, driver_code='NAV4',
            driver_phone='97412345671', driver_whatsapp='97412345671',
            driver_languages='english', driver_status='approved',
        )
        self.today = timezone.localdate()

    def _fix_at(self, point, hour, minute):
        when = timezone.make_aware(
            timezone.datetime.combine(self.today, timezone.datetime.min.time())
        ) + timezone.timedelta(hours=hour, minutes=minute)
        return DriverLocation.objects.create(
            driver=self.driver, latitude=point[0], longitude=point[1],
            accuracy=10, fixed_at=when)

    def _url(self, day=None):
        return f'/workforce/drivers/{self.driver.driver_id}/timeline/' + (f'?day={day}' if day else '')

    def test_the_page_draws_the_measured_trail(self):
        self._fix_at(DOHA, 8, 0)
        self._fix_at((25.2900, 51.5400), 8, 1)
        self._fix_at(LUSAIL, 8, 3)

        resp = self.client.get(self._url())
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context['summary']['points'], 3)
        self.assertGreater(resp.context['summary']['distance_km'], 0)

    def test_a_hole_in_the_trail_becomes_a_row(self):
        self._fix_at(DOHA, 8, 0)
        self._fix_at(LUSAIL, 8, 30)          # half an hour with nothing in between

        gaps = [e for e in self.client.get(self._url()).context['events'] if e['kind'] == 'gap']
        self.assertEqual(len(gaps), 1)
        self.assertEqual(gaps[0]['minutes'], 30)
        self.assertFalse(gaps[0]['explained'])
        self.assertEqual(gaps[0]['reason'], 'Unexplained')

    def test_a_hole_a_handoff_explains_says_which_app(self):
        self._fix_at(DOHA, 8, 0)
        self._fix_at(LUSAIL, 8, 30)
        opened = timezone.make_aware(
            timezone.datetime.combine(self.today, timezone.datetime.min.time())
        ) + timezone.timedelta(hours=8, minutes=1)
        DriverNavHandoff.objects.create(
            driver=self.driver, provider='waze',
            opened_at=opened, returned_at=opened + timezone.timedelta(minutes=28),
            route_polyline=json.dumps([[25.28, 51.53], [25.41, 51.49]]), route_km=14.2)

        gap = [e for e in self.client.get(self._url()).context['events'] if e['kind'] == 'gap'][0]
        self.assertTrue(gap['explained'])
        self.assertEqual(gap['reason'], 'In Waze')
        self.assertEqual(gap['route_km'], 14.2)
        self.assertEqual(len(gap['route']), 2)

    def test_standing_still_is_one_stop_not_a_row_per_fix(self):
        for minute in range(0, 25, 5):       # same spot for 20 minutes
            self._fix_at((25.2854 + minute * 0.000001, 51.5310), 9, minute)

        stops = [e for e in self.client.get(self._url()).context['events'] if e['kind'] == 'stop']
        self.assertEqual(len(stops), 1)
        self.assertGreaterEqual(stops[0]['minutes'], 15)

    def test_a_day_past_the_retention_window_says_so(self):
        old = (self.today - timezone.timedelta(days=30)).isoformat()
        resp = self.client.get(self._url(day=old))
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.context['beyond_retention'])
        self.assertContains(resp, 'beyond what the trail holds')
