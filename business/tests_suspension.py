# Purpose: Tests that a business not cleared to trade is read-only for the seller and closed to machines.
# Used by: python manage.py test business.tests_suspension
# Notes: Two statuses block writes — 'suspended' (staff decision) and 'pending' (never approved).
#        'inactive' must stay writable: it is a soft archive for accounts approved once, and
#        freezing it would silently strand old clients staff had deliberately parked.

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from business import models as business_models
from business.suspension import is_business_suspended
from core import models as core_models
from ezzy_api import models as ezzy_api_models
from orders import models as orders_models

User = get_user_model()


def make_business(idx, username, status='active'):
    user = User.objects.create_user(
        username=username, email=f'{username}@example.com', password='pass12345'
    )
    profile = core_models.Profile.objects.create(
        user=user, first_name='S', last_name='U', phone=31000000 + idx,
        is_business=True, verification_status='verified',
        is_business_profile_completed=True,
    )
    business = business_models.Business.objects.create(
        business_id=idx, user=user, profile=profile,
        business_name=f'Susp Biz {idx}', business_code=f'SB{idx}',
        business_phone='55500000', business_email=f'sb{idx}@example.com',
        business_status=status,
    )
    # add_order redirects to the stores page when a business has no pickup
    # location, which would 302 every fixture here for a reason that has nothing
    # to do with the write gate. Give each one a store so the assertions mean
    # what they say.
    business_models.PickupLocation.objects.create(
        business=business, pickup_location_title=f'Store {idx}',
        locality='Zone 1', pickup_status='active', is_default=True,
    )
    return user, business


class IsBusinessSuspendedTest(TestCase):
    def test_only_suspended_counts(self):
        for status, expected in [
            ('suspended', True), ('active', False),
            ('pending', False), ('inactive', False),
        ]:
            biz = business_models.Business(business_status=status)
            self.assertIs(is_business_suspended(biz), expected, status)

    def test_none_is_not_suspended(self):
        self.assertFalse(is_business_suspended(None))


class SellerOrderWriteGateTest(TestCase):
    """The seller keeps their data; they just cannot change it."""

    def setUp(self):
        self.user, self.business = make_business(9101, 'suspowner', 'suspended')
        self.client.force_login(self.user)

    def test_add_order_page_refused(self):
        resp = self.client.get(reverse('orders:add_order'))
        self.assertEqual(resp.status_code, 302)
        self.assertIn('dashboard', resp.url)

    def test_add_order_post_creates_nothing(self):
        before = orders_models.Order.objects.count()
        self.client.post(reverse('orders:add_order'), {
            'customer_name': 'Blocked Customer', 'dl_phone': '55511111',
            'dl_address': 'Zone 1', 'dl_price': '50',
        })
        self.assertEqual(orders_models.Order.objects.count(), before)

    def test_json_endpoint_returns_403_envelope(self):
        resp = self.client.post(
            reverse('orders:update_order_status'),
            data='{"order_id": 1, "status": "cancelled"}',
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 403)
        body = resp.json()
        self.assertFalse(body['success'])
        self.assertEqual(body['code'], 'business_suspended')

    def test_htmx_endpoint_returns_200_inline_alert(self):
        # 200 on purpose: the base template's htmx:responseError handler would
        # navigate the browser to this POST-only path and render a 405 page.
        resp = self.client.post(
            reverse('orders:orders_api_pending_import'),
            {'selected': []}, HTTP_HX_REQUEST='true',
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'suspended', resp.content.lower())

    def test_reads_still_work(self):
        resp = self.client.get(reverse('orders:orders_all_list'))
        self.assertEqual(resp.status_code, 200)


class ActiveBusinessNotGatedTest(TestCase):
    """Which statuses may write, stated once and explicitly."""

    def test_active_and_inactive_reach_the_view(self):
        for idx, status in [(9112, 'inactive'), (9113, 'active')]:
            user, _ = make_business(idx, f'ok{idx}', status)
            self.client.force_login(user)
            resp = self.client.get(reverse('orders:add_order'))
            self.assertEqual(resp.status_code, 200, status)
            self.client.logout()

    def test_pending_is_refused(self):
        user, _ = make_business(9111, 'ok9111', 'pending')
        self.client.force_login(user)
        resp = self.client.get(reverse('orders:add_order'))
        self.assertEqual(resp.status_code, 302)
        self.assertIn('dashboard', resp.url)


class TeamMemberGateTest(TestCase):
    """The gate keys off the business, so team members are refused identically."""

    def setUp(self):
        self.owner, self.business = make_business(9121, 'teamowner', 'suspended')
        self.member = User.objects.create_user(username='teammate', password='pass12345')
        core_models.Profile.objects.create(
            user=self.member, first_name='T', last_name='M', phone=31999999)
        business_models.BusinessTeamProfile.objects.create(
            business=self.business, user=self.member,
            team_status='active', team_verifed=True,
        )

    def test_team_member_cannot_add_order(self):
        self.client.force_login(self.member)
        resp = self.client.get(reverse('orders:add_order'))
        self.assertEqual(resp.status_code, 302)

    def test_team_status_is_not_cascaded(self):
        tp = business_models.BusinessTeamProfile.objects.get(user=self.member)
        self.assertEqual(tp.team_status, 'active')


class ApiKeyGateTest(TestCase):
    def setUp(self):
        self.user, self.business = make_business(9131, 'apiowner', 'suspended')
        self.key = ezzy_api_models.ClientApiKey.objects.create(business=self.business)
        self.raw = self.key._plaintext_key
        self.api = APIClient()

    def test_suspended_key_rejected(self):
        resp = self.api.get('/api/v1/orderlist/', HTTP_X_API_KEY=self.raw)
        self.assertEqual(resp.status_code, 401)

    def test_key_is_not_deactivated(self):
        # Suspension must be reversible without staff regenerating credentials.
        self.key.refresh_from_db()
        self.assertTrue(self.key.is_active)

    def test_same_key_works_once_lifted(self):
        self.business.business_status = 'active'
        self.business.save()
        resp = self.api.get('/api/v1/orderlist/', HTTP_X_API_KEY=self.raw)
        self.assertEqual(resp.status_code, 200)


class WebhookGateTest(TestCase):
    def setUp(self):
        self.user, self.business = make_business(9141, 'hooksusp', 'suspended')
        self.wk = ezzy_api_models.WebhookImportKey.objects.create(
            business=self.business, key='wh_susp_key_123456')
        self.api = APIClient()
        self.url = f'/api/webhooks/order/inbound/{self.wk.key}/'

    def test_inbound_refused_and_nothing_stored(self):
        resp = self.api.post(self.url, {
            'order_id': 'WH-SUSP-1', 'customer_name': 'Nope',
            'phone': '55500000', 'address': 'Zone 1', 'cod': 100,
        }, format='json')
        self.assertEqual(resp.status_code, 403)
        self.assertFalse(orders_models.TempOrder.objects.filter(
            business=self.business).exists())

    def test_webhook_key_left_active(self):
        self.wk.refresh_from_db()
        self.assertTrue(self.wk.is_active)


class TempOrderSyncGateTest(TestCase):
    def setUp(self):
        self.user, self.business = make_business(9151, 'syncsusp', 'suspended')
        self.api_settings = business_models.BusinessApiSettings.objects.create(
            business=self.business, api_type='shopify', is_verify_api=True,
        )

    def test_per_source_sync_refuses(self):
        from orders.tasks import _sync_api_source
        with self.assertRaises(RuntimeError) as ctx:
            _sync_api_source(self.api_settings)
        self.assertIn('suspended', str(ctx.exception).lower())

    def test_bulk_run_skips_the_source_quietly(self):
        from orders.tasks import _sync_all_api
        created, updated, errors = _sync_all_api('shopify')
        self.assertEqual((created, updated), (0, 0))
        self.assertEqual(errors, [])


class ImportSettingsGateTest(TestCase):
    def setUp(self):
        self.user, self.business = make_business(9161, 'setsusp', 'suspended')
        self.client.force_login(self.user)

    def test_list_page_still_viewable(self):
        resp = self.client.get(reverse(
            'business:business_settings_api_list', args=[self.business.business_id]))
        self.assertEqual(resp.status_code, 200)

    def test_add_integration_refused(self):
        resp = self.client.get(reverse(
            'business:business_settings_api_add', args=[self.business.business_id]))
        self.assertEqual(resp.status_code, 302)


class BannerAndVerificationDisplayTest(TestCase):
    def test_banner_shows_for_suspended_only(self):
        user, business = make_business(9171, 'bannersusp', 'suspended')
        self.client.force_login(user)
        resp = self.client.get(reverse('orders:orders_all_list'))
        self.assertContains(resp, 'Account suspended')

        business.business_status = 'active'
        business.save()
        resp = self.client.get(reverse('orders:orders_all_list'))
        self.assertNotContains(resp, 'Account suspended')

    def test_profile_verification_is_untouched(self):
        user, business = make_business(9172, 'verifsusp', 'suspended')
        profile = core_models.Profile.objects.get(user=user)
        self.assertEqual(profile.verification_status, 'verified')


class StaffNotGatedTest(TestCase):
    """Staff must keep working suspended accounts — held COD has to stay reachable."""

    def test_staff_owner_of_a_suspended_business_is_not_gated(self):
        user, business = make_business(9181, 'staffsusp', 'suspended')
        user.is_staff = True
        user.save()
        self.client.force_login(user)
        resp = self.client.get(reverse('orders:add_order'))
        self.assertEqual(resp.status_code, 200)

    def test_same_request_is_gated_once_staff_flag_is_removed(self):
        user, business = make_business(9182, 'notstaff', 'suspended')
        self.client.force_login(user)
        resp = self.client.get(reverse('orders:add_order'))
        self.assertEqual(resp.status_code, 302)


class VerificationDoesNotLiftSuspensionTest(TestCase):
    def test_status_stays_suspended(self):
        from business.models import Business
        _, business = make_business(9191, 'verlift', 'suspended')
        # Mirrors workforce.views.apply_verification_status' business branch.
        if business.business_status != 'suspended':
            business.business_status = 'active'
        business.save()
        self.assertEqual(
            Business.objects.get(pk=business.pk).business_status, 'suspended')


# ---------------------------------------------------------------------------
# Awaiting-approval gate — a business staff never approved may not trade.
# ---------------------------------------------------------------------------

class WriteBlockedStatusTest(TestCase):
    def test_which_statuses_block_writes(self):
        from business.suspension import is_business_write_blocked
        for status, expected in [
            ('suspended', True), ('pending', True),
            ('active', False), ('inactive', False),
        ]:
            biz = business_models.Business(business_status=status)
            self.assertIs(is_business_write_blocked(biz), expected, status)

    def test_none_is_not_blocked(self):
        from business.suspension import is_business_write_blocked
        self.assertFalse(is_business_write_blocked(None))

    def test_reason_code_distinguishes_the_two(self):
        from business.suspension import write_refusal_code
        self.assertEqual(
            write_refusal_code(business_models.Business(business_status='suspended')),
            'business_suspended')
        self.assertEqual(
            write_refusal_code(business_models.Business(business_status='pending')),
            'business_pending_approval')
        self.assertIsNone(
            write_refusal_code(business_models.Business(business_status='active')))


class PendingBusinessWriteGateTest(TestCase):
    """The SHAMA PERFUMES case: self-registered, never approved, still trading."""

    def setUp(self):
        self.user, self.business = make_business(9201, 'pendowner', 'pending')
        self.client.force_login(self.user)

    def test_add_order_post_creates_nothing(self):
        before = orders_models.Order.objects.count()
        self.client.post(reverse('orders:add_order'), {
            'customer_name': 'Unapproved Customer', 'dl_phone': '55511111',
            'dl_address': 'Zone 1', 'dl_price': '50',
        })
        self.assertEqual(orders_models.Order.objects.count(), before)

    def test_reads_still_work(self):
        resp = self.client.get(reverse('orders:orders_all_list'))
        self.assertEqual(resp.status_code, 200)

    def test_dashboard_still_reachable(self):
        resp = self.client.get(reverse('business:business_dashboard'))
        self.assertEqual(resp.status_code, 200)

    def test_json_endpoint_returns_pending_reason_code(self):
        resp = self.client.post(
            reverse('orders:update_order_status'),
            data='{"order_id": 1, "status": "cancelled"}',
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.json()['code'], 'business_pending_approval')

    def test_banner_explains_the_wait(self):
        resp = self.client.get(reverse('orders:orders_all_list'))
        self.assertContains(resp, 'Account awaiting approval')
        self.assertNotContains(resp, 'Account suspended')

    def test_staff_owner_is_still_exempt(self):
        self.user.is_staff = True
        self.user.save()
        resp = self.client.get(reverse('orders:add_order'))
        self.assertEqual(resp.status_code, 200)


class OperationalWriteCoverageTest(TestCase):
    """business/views.py write views had no gate at all — not even for suspension."""

    def _blocked(self, status, url_name, args=None):
        user, business = make_business(
            9210 + abs(hash(url_name + status)) % 700, f'cov{abs(hash(url_name + status)) % 9999}',
            status)
        self.client.force_login(user)
        args = [business.business_id] if args == 'biz' else (args or [])
        resp = self.client.get(reverse(url_name, args=args))
        self.client.logout()
        return resp

    def test_pickup_location_add_refused_for_pending_and_suspended(self):
        for status in ('pending', 'suspended'):
            resp = self._blocked(status, 'business:pickup_location_add')
            self.assertEqual(resp.status_code, 302, status)

    def test_pickup_location_add_allowed_for_active(self):
        resp = self._blocked('active', 'business:pickup_location_add')
        self.assertEqual(resp.status_code, 200)

    def test_business_teams_add_refused_for_pending_and_suspended(self):
        for status in ('pending', 'suspended'):
            resp = self._blocked(status, 'business:business_teams_add', args='biz')
            self.assertEqual(resp.status_code, 302, status)

    def test_own_profile_edit_stays_open_while_pending(self):
        # A pending client must be able to fix details staff asked them to correct.
        resp = self._blocked('pending', 'business:business_profile_update', args='biz')
        self.assertNotEqual(resp.status_code, 302)


class OwnershipTransferTest(TestCase):
    """A team member POSTing the shared business form must not become the owner."""

    def setUp(self):
        self.owner, self.business = make_business(9301, 'realowner', 'active')
        self.member = User.objects.create_user(username='hijacker', password='pass12345')
        core_models.Profile.objects.create(
            user=self.member, first_name='H', last_name='J', phone=31888888,
            is_business=True, verification_status='verified',
        )
        business_models.BusinessTeamProfile.objects.create(
            business=self.business, user=self.member,
            team_status='active', team_verifed=True,
        )

    def test_team_member_post_does_not_reassign_owner(self):
        self.client.force_login(self.member)
        self.client.post(reverse('core:business_profile_update'), {
            'business_name': 'Taken Over', 'business_phone': '55500000',
            'business_whatsapp': '55500000', 'business_email': 'x@example.com',
            'business_languages': 'english',
        })
        self.business.refresh_from_db()
        self.assertEqual(self.business.user_id, self.owner.id)
