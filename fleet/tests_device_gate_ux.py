"""
Purpose: The device gate must read as a lock with a way out, never as a failed login.
Used by: manage.py test fleet.tests_device_gate_ux
Notes: DRIVER_DEVICE_ENFORCEMENT is off in the test settings, so each test turns it
       back on — without that the gate never engages and the assertions pass vacuously.
"""
from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings

from core.models import Profile
from fleet.models import Driver, DriverDevice


@override_settings(SECURE_SSL_REDIRECT=False, ALLOWED_HOSTS=['testserver'],
                   DRIVER_DEVICE_ENFORCEMENT=True)
class DeviceGateExitRouteTests(TestCase):
    """A driver held at the gate must always have one tappable way out."""

    PASSWORD = 'Str0ngPass!99'

    def setUp(self):
        user = get_user_model().objects.create_user(
            username='gatedriver', email='gate@example.com', password=self.PASSWORD)
        profile, _ = Profile.objects.get_or_create(user=user)
        profile.is_driver = True
        profile.whatsapp = '97470024744'
        profile.phone = '71188023'
        profile.save()
        # driver_whatsapp is what driver_phone() prefers — the number the code goes to.
        Driver.objects.create(user=user, driver_id=9911, driver_status='approved',
                              driver_whatsapp='97470024744', driver_phone='71188023')
        self.user = user

    def _sign_in(self):
        client = Client()
        response = client.post('/accounts/login/',
                               {'login': 'gate@example.com', 'password': self.PASSWORD},
                               follow=True)
        return client, response

    def test_login_succeeds_and_lands_on_the_gate(self):
        """The driver is authenticated — the gate is a second step, not a rejection."""
        client, response = self._sign_in()

        self.assertEqual(response.status_code, 200)
        self.assertIn('/fleet/device/verify/', [url for url, _ in response.redirect_chain])
        self.assertIn('_auth_user_id', client.session)
        self.assertTrue(DriverDevice.objects.filter(user=self.user,
                                                    status=DriverDevice.STATUS_PENDING).exists())

    def test_gate_offers_a_whatsapp_route_to_ops(self):
        """The old page said ops could help and gave no way to reach them."""
        _, response = self._sign_in()
        body = response.content.decode()

        self.assertIn('https://wa.me/97466124545', body)
        self.assertIn('fleet_device_verify_link_ops', body)
        # Pre-filled so ops can act without a back-and-forth
        self.assertIn('Driver%20ID%3A%209911', body)

    def test_gate_warns_when_the_code_cannot_reach_the_driver(self):
        """The code goes to driver_whatsapp; that may not be the phone in their hand."""
        _, response = self._sign_in()
        body = response.content.decode()

        self.assertIn('Not your WhatsApp number?', body)

    def test_gate_offers_ops_route_when_no_number_is_on_file(self):
        """With no number there is no code to send, so the link is the only exit."""
        Driver.objects.filter(user=self.user).update(driver_whatsapp='', driver_phone='')
        Profile.objects.filter(user=self.user).update(whatsapp='', phone='')

        _, response = self._sign_in()
        body = response.content.decode()

        self.assertIn("can&rsquo;t send a code", body)
        self.assertIn('https://wa.me/97466124545', body)


@override_settings(SECURE_SSL_REDIRECT=False, ALLOWED_HOSTS=['testserver'],
                   DRIVER_DEVICE_ENFORCEMENT=True)
class GateRedirectCacheTests(TestCase):
    """The gate and the dashboard redirect to each other, so neither leg may be cached.

    Cached, a browser bounces between the two 302s without reaching the server and
    the driver gets ERR_TOO_MANY_REDIRECTS with nothing in the logs to show for it.
    """

    PASSWORD = 'Str0ngPass!99'

    def setUp(self):
        user = get_user_model().objects.create_user(
            username='loopdriver', email='loop@example.com', password=self.PASSWORD)
        profile, _ = Profile.objects.get_or_create(user=user)
        profile.is_driver = True
        profile.whatsapp = '97471188023'
        profile.save()
        Driver.objects.create(user=user, driver_id=9915, driver_status='approved',
                              driver_whatsapp='97471188023', driver_phone='71188023')
        self.user = user
        self.client.post('/accounts/login/',
                         {'login': 'loop@example.com', 'password': self.PASSWORD})

    def test_gate_redirect_is_not_cacheable(self):
        response = self.client.get('/fleet/dashboard/')

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers['Location'], '/fleet/device/verify/')
        self.assertEqual(response.headers.get('Cache-Control'), 'no-store')

    def test_gate_page_is_not_cacheable(self):
        response = self.client.get('/fleet/device/verify/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get('Cache-Control'), 'no-store')

    def test_return_leg_is_not_cacheable(self):
        """Once ops releases the device the gate sends the driver back — same rule."""
        DriverDevice.objects.filter(user=self.user).update(status=DriverDevice.STATUS_ACTIVE)

        response = self.client.get('/fleet/device/verify/')

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers['Location'], '/fleet/dashboard/')
        self.assertEqual(response.headers.get('Cache-Control'), 'no-store')
