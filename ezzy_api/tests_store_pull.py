# Purpose: Tests for pulling orders FROM a seller's own REST API into Temp Orders.
# Used by: manage.py test ezzy_api.tests_store_pull
# Notes: The rules that cost real money are idempotency (an hourly pull re-reading the
#        same open-orders list must not restage) and the COD rule inherited from the
#        push leg. Every outbound call is mocked — no test may touch a real network.

import json
from unittest.mock import patch

from django.test import TestCase

from business import models as business_models
from ezzy_api import store_pull
from ezzy_api.store_pull import PullError, build_request, extract_orders, is_pull_source
from ezzy_api.tests_store_api import SAMPLE, make_active_business, make_custom_source
from orders import models as orders_models
from orders.tasks import _sync_custom_pull_source, sync_all_temp_orders


class AllowAnyHostMixin:
    """Neutralise the SSRF guard's DNS lookup for tests that are not about it.

    store_pull.validate_public_url resolves the host for real, so a made-up test
    domain fails there before the code under test is ever reached — and a test
    suite must not depend on the resolver. SsrfGuardTests deliberately does NOT
    use this mixin.
    """

    def setUp(self):
        super().setUp()
        patcher = patch.object(store_pull, 'validate_public_url', return_value=(True, ''))
        patcher.start()
        self.addCleanup(patcher.stop)


def make_pull_source(business, **over):
    fields = dict(
        fetch_orders_url='https://shop.example/api/orders',
        fetch_auth_style='bearer',
        fetch_api_key='seller-side-key-123',
        fetch_enabled=True,
    )
    fields.update(over)
    return make_custom_source(business, **fields)


class FakeResponse:
    """Enough of requests.Response for store_pull.fetch_orders."""

    is_redirect = False
    is_permanent_redirect = False

    def __init__(self, payload, status_code=200, raw=None):
        self.status_code = status_code
        self.headers = {}
        self._raw = raw if raw is not None else json.dumps(payload).encode('utf-8')

        class _Elapsed:
            @staticmethod
            def total_seconds():
                return 0.05
        self.elapsed = _Elapsed()

    def iter_content(self, chunk_size=65536):
        for i in range(0, len(self._raw), chunk_size):
            yield self._raw[i:i + chunk_size]

    def close(self):
        pass


class BuildRequestTests(AllowAnyHostMixin, TestCase):
    def setUp(self):
        super().setUp()
        _, self.business = make_active_business(41, 'pull_build')

    def test_bearer_puts_the_sellers_key_in_the_header(self):
        api = make_pull_source(self.business)
        url, headers, params = build_request(api)
        self.assertEqual(url, 'https://shop.example/api/orders')
        self.assertEqual(headers['Authorization'], 'Bearer seller-side-key-123')
        self.assertEqual(params, {})

    def test_custom_header_style(self):
        api = make_pull_source(self.business, fetch_auth_style='header',
                               fetch_auth_name='X-API-Key')
        _, headers, _ = build_request(api)
        self.assertEqual(headers['X-API-Key'], 'seller-side-key-123')
        self.assertNotIn('Authorization', headers)

    def test_query_style_and_extra_params(self):
        api = make_pull_source(self.business, fetch_auth_style='query',
                               fetch_auth_name='api_key',
                               fetch_params={'status': 'pending', 'limit': 50})
        _, headers, params = build_request(api)
        self.assertEqual(params['api_key'], 'seller-side-key-123')
        self.assertEqual(params['status'], 'pending')
        self.assertEqual(params['limit'], '50')
        self.assertNotIn('Authorization', headers)

    def test_missing_header_name_is_refused_before_the_call(self):
        api = make_pull_source(self.business, fetch_auth_style='header', fetch_auth_name='')
        with self.assertRaises(PullError):
            build_request(api)

    def test_push_only_row_is_not_a_pull_source(self):
        api = make_custom_source(self.business)
        self.assertFalse(is_pull_source(api))
        self.assertTrue(is_pull_source(make_pull_source(self.business)))


class ExtractOrdersTests(TestCase):
    def test_bare_array(self):
        self.assertEqual(len(extract_orders([SAMPLE, SAMPLE])), 2)

    def test_common_envelope_keys_need_no_configuration(self):
        for key in ('orders', 'data', 'results', 'items', 'records'):
            self.assertEqual(len(extract_orders({key: [SAMPLE]})), 1, key)

    def test_explicit_path_wins(self):
        body = {'data': {'orders': [SAMPLE, SAMPLE]}, 'orders': []}
        self.assertEqual(len(extract_orders(body, 'data.orders')), 2)

    def test_single_order_object_counts_as_one(self):
        self.assertEqual(len(extract_orders(SAMPLE)), 1)

    def test_unfindable_list_says_what_the_response_looked_like(self):
        with self.assertRaises(PullError) as ctx:
            extract_orders({'meta': {'page': 1}})
        self.assertIn('meta', str(ctx.exception))


class FetchOrdersTests(AllowAnyHostMixin, TestCase):
    def setUp(self):
        super().setUp()
        _, self.business = make_active_business(42, 'pull_fetch')
        self.api = make_pull_source(self.business)

    def test_rejected_key_is_reported_as_such(self):
        with patch.object(store_pull.requests, 'get',
                          return_value=FakeResponse(None, status_code=401)):
            with self.assertRaises(PullError) as ctx:
                store_pull.fetch_orders(self.api)
        self.assertIn('rejected our key', str(ctx.exception))

    def test_non_json_body_is_reported_with_a_preview(self):
        with patch.object(store_pull.requests, 'get',
                          return_value=FakeResponse(None, raw=b'<html>login page</html>')):
            with self.assertRaises(PullError) as ctx:
                store_pull.fetch_orders(self.api)
        self.assertIn('did not return JSON', str(ctx.exception))

    def test_oversized_response_is_cut_off(self):
        # MAX_RESPONSE_BYTES is 8MB; 8 bytes per repeat, so go comfortably past it.
        huge = b'[' + (b'{"a":1},' * ((store_pull.MAX_RESPONSE_BYTES // 8) + 50000)) + b'{}]'
        with patch.object(store_pull.requests, 'get',
                          return_value=FakeResponse(None, raw=huge)):
            with self.assertRaises(PullError) as ctx:
                store_pull.fetch_orders(self.api)
        self.assertIn('exceeded', str(ctx.exception))

    def test_order_count_is_capped(self):
        many = [dict(SAMPLE, orderNumber=f'N-{i}') for i in range(store_pull.MAX_ORDERS_PER_FETCH + 40)]
        with patch.object(store_pull.requests, 'get', return_value=FakeResponse(many)):
            orders, meta = store_pull.fetch_orders(self.api)
        self.assertEqual(len(orders), store_pull.MAX_ORDERS_PER_FETCH)
        self.assertEqual(meta['count'], store_pull.MAX_ORDERS_PER_FETCH)

    def test_redirect_is_not_followed(self):
        """A redirect is a destination the SSRF guard never saw, and it would
        carry the seller's key along with it."""
        resp = FakeResponse([])
        resp.is_redirect = True
        resp.status_code = 302
        resp.headers = {'Location': 'http://169.254.169.254/latest/meta-data/'}
        with patch.object(store_pull.requests, 'get', return_value=resp):
            with self.assertRaises(PullError) as ctx:
                store_pull.fetch_orders(self.api)
        self.assertIn('redirected', str(ctx.exception))


class SyncCustomPullTests(AllowAnyHostMixin, TestCase):
    def setUp(self):
        super().setUp()
        _, self.business = make_active_business(43, 'pull_sync')
        self.business.temp_order_enabled = True
        self.business.save(update_fields=['temp_order_enabled'])
        self.api = make_pull_source(self.business)

    def _pull(self, payload):
        with patch.object(store_pull.requests, 'get', return_value=FakeResponse(payload)):
            return _sync_custom_pull_source(self.api)

    def test_a_fetched_order_is_staged_like_a_pushed_one(self):
        created, updated = self._pull({'orders': [SAMPLE]})
        self.assertEqual((created, updated), (1, 0))

        temp = orders_models.TempOrder.objects.get(business=self.business)
        self.assertEqual(temp.source_type, 'custom_api')
        self.assertEqual(temp.api_settings_id, self.api.id)
        self.assertEqual(temp.client_order_code, 'GOOEY-429869')
        self.assertEqual(temp.customer_name, 'Hind Alobaidli')
        self.assertEqual(temp.customer_phone, '51060099')
        # applepay is prepaid, so no COD rides on the delivery.
        self.assertEqual(temp.cod_amount, '0')
        self.assertEqual(temp.financial_status, 'paid')
        # The basket survives for the import step to rebuild OrderItems from.
        self.assertEqual(temp.raw_row['product_1'], "S'more")
        self.assertEqual(temp.raw_row['count_1'], 2)

    def test_cod_order_keeps_its_amount(self):
        cod_order = dict(SAMPLE, orderNumber='COD-77', paymentMethod='cod')
        self._pull([cod_order])
        temp = orders_models.TempOrder.objects.get(client_order_code='COD-77')
        self.assertEqual(temp.cod_amount, '90')
        self.assertEqual(temp.financial_status, 'pending')

    def test_repeated_pulls_do_not_restage_the_same_order(self):
        """The endpoint keeps returning its open orders; an hourly pull must not
        create a second delivery for each one every hour."""
        self._pull([SAMPLE])
        created2, _ = self._pull([SAMPLE])
        self.assertEqual(created2, 0)
        self.assertEqual(orders_models.TempOrder.objects.filter(business=self.business).count(), 1)

    def test_an_order_already_pushed_is_not_pulled_again(self):
        from ezzy_api.store_api import stage_order_payload
        stage_order_payload(self.business, SAMPLE)
        created, _ = self._pull([SAMPLE])
        self.assertEqual(created, 0)
        self.assertEqual(orders_models.TempOrder.objects.filter(business=self.business).count(), 1)

    def test_a_staged_row_edited_by_staff_is_never_overwritten(self):
        self._pull([SAMPLE])
        temp = orders_models.TempOrder.objects.get(business=self.business)
        temp.customer_address = 'Corrected by ops'
        temp.save(update_fields=['customer_address'])
        self._pull([SAMPLE])
        temp.refresh_from_db()
        self.assertEqual(temp.customer_address, 'Corrected by ops')

    def test_good_orders_are_kept_when_one_is_unusable(self):
        broken = dict(SAMPLE, orderNumber='BAD-1')
        broken.pop('customer')
        created, _ = self._pull([SAMPLE, broken])
        self.assertEqual(created, 1)
        self.assertFalse(orders_models.TempOrder.objects.filter(client_order_code='BAD-1').exists())

    def test_all_orders_unusable_raises_so_staff_see_it(self):
        broken = dict(SAMPLE)
        broken.pop('customer')
        broken.pop('orderNumber')
        with self.assertRaises(RuntimeError):
            self._pull([broken])

    def test_empty_store_still_stamps_a_real_sync_time(self):
        created, updated = self._pull({'orders': []})
        self.assertEqual((created, updated), (0, 0))
        self.api.refresh_from_db()
        self.assertIsNotNone(self.api.last_sync_at)

    def test_suspended_seller_is_not_pulled(self):
        self.business.business_status = 'suspended'
        self.business.save(update_fields=['business_status'])
        with self.assertRaises(RuntimeError):
            self._pull([SAMPLE])
        self.assertFalse(orders_models.TempOrder.objects.filter(business=self.business).exists())

    def test_saved_mapping_drives_a_non_standard_payload(self):
        """The mapping is the same one the push leg reads — a seller whose JSON
        looks nothing like ours is carried by it in both directions."""
        self.api.column_mapping = {
            'client_order_code': 'ref',
            'customer_name': 'buyer.fullName',
            'customer_phone': 'buyer.mobile',
            'customer_address': 'buyer.where',
            'cod_amount': 'amountDue',
            'payment_method': 'payVia',
            'product_1': 'basket[].label',
            'count_1': 'basket[].n',
        }
        self.api.save(update_fields=['column_mapping'])
        exotic = {
            'ref': 'X-9001',
            'buyer': {'fullName': 'Noor Ali', 'mobile': '+974 5512 3456', 'where': 'Zone 55, Street 12'},
            'amountDue': 130,
            'payVia': 'cash',
            'basket': [{'label': 'Cake', 'n': 1}, {'label': 'Candles', 'n': 3}],
        }
        created, _ = self._pull([exotic])
        self.assertEqual(created, 1)
        temp = orders_models.TempOrder.objects.get(client_order_code='X-9001')
        self.assertEqual(temp.customer_name, 'Noor Ali')
        self.assertEqual(temp.customer_phone, '55123456')
        self.assertEqual(temp.cod_amount, '130')
        self.assertEqual(temp.financial_status, 'pending')
        self.assertEqual(temp.raw_row['product_2'], 'Candles')


class SyncDispatcherTests(AllowAnyHostMixin, TestCase):
    """The hourly cron and the Temp Orders 'Sync' button both come through here."""

    def setUp(self):
        super().setUp()
        _, self.business = make_active_business(44, 'pull_dispatch')
        self.api = make_pull_source(self.business)

    def test_named_source_is_pulled(self):
        with patch.object(store_pull.requests, 'get', return_value=FakeResponse([SAMPLE])):
            result = sync_all_temp_orders(source_type='custom_api', source_id=self.api.id)
        self.assertEqual(result['created'], 1)

    def test_push_only_seller_gets_an_explanation_not_a_silent_zero(self):
        _, other = make_active_business(45, 'pull_pushonly')
        push_api = make_custom_source(other)
        result = sync_all_temp_orders(source_type='custom_api', source_id=push_api.id)
        self.assertEqual(result['created'], 0)
        self.assertTrue(any('push' in n.lower() for n in result['notes']))

    def test_disabled_source_is_skipped_by_the_bulk_run(self):
        self.api.fetch_enabled = False
        self.api.save(update_fields=['fetch_enabled'])
        with patch.object(store_pull.requests, 'get', return_value=FakeResponse([SAMPLE])) as mock_get:
            sync_all_temp_orders(source_type=None)
        self.assertFalse(mock_get.called)

    def test_a_failing_store_is_an_error_not_a_crash(self):
        with patch.object(store_pull.requests, 'get', return_value=FakeResponse(None, status_code=500)):
            result = sync_all_temp_orders(source_type='custom_api', source_id=self.api.id)
        self.assertEqual(result['created'], 0)
        self.assertTrue(result['errors'])


class SsrfGuardTests(TestCase):
    """The guard itself — no mixin here, the real resolver has to run.

    The fetch URL is merchant-supplied and called on a schedule with a
    credential attached, so an unchecked value is a standing SSRF lever rather
    than a one-off during a manual test.
    """

    def setUp(self):
        _, self.business = make_active_business(46, 'pull_ssrf')

    def test_loopback_is_refused(self):
        api = make_pull_source(self.business, fetch_orders_url='http://127.0.0.1:8000/orders')
        with self.assertRaises(PullError) as ctx:
            build_request(api)
        self.assertIn('public', str(ctx.exception).lower())

    def test_cloud_metadata_address_is_refused(self):
        api = make_pull_source(
            self.business, fetch_orders_url='http://169.254.169.254/latest/meta-data/')
        with self.assertRaises(PullError):
            build_request(api)

    def test_private_subnet_is_refused(self):
        api = make_pull_source(self.business, fetch_orders_url='http://10.0.0.5/api/orders')
        with self.assertRaises(PullError):
            build_request(api)


# The real shape Gooey's lookup endpoint returns: no items, no totals, no date,
# and a Qatar zone/street/building address. Deliberately NOT the shape their push
# endpoint sends — the two payloads differ, which is why mapping is per-source.
GOOEY_PULL = {
    'orderNumber': 'GOOEY-807598',
    'status': 'accepted',
    'paymentMethod': 'applepay',
    'paymentStatus': 'paid',
    'customer': {
        'name': 'Hissa Khalid Al Abdulla',
        'phone': '51565556',
        'municipality': 'Al Wakrah',
        'area': 'Al Wakrah',
        'zone': '90',
        'street': '911',
        'buildingType': 'House',
        'buildingNumber': '4',
    },
}


class StatusFilterTests(AllowAnyHostMixin, TestCase):
    """A lookup endpoint answers with recent orders, not a work queue."""

    def setUp(self):
        super().setUp()
        _, self.business = make_active_business(47, 'pull_status')
        self.api = make_pull_source(
            self.business, fetch_status_path='status', fetch_status_include='accepted')

    def _fetch(self, orders):
        with patch.object(store_pull.requests, 'get', return_value=FakeResponse({'orders': orders})):
            return store_pull.fetch_orders(self.api)

    def test_finished_and_cancelled_orders_are_not_booked_for_delivery(self):
        orders = [
            dict(GOOEY_PULL, orderNumber='A', status='accepted'),
            dict(GOOEY_PULL, orderNumber='B', status='delivered'),
            dict(GOOEY_PULL, orderNumber='C', status='cancelled'),
            dict(GOOEY_PULL, orderNumber='D', status='pending'),
        ]
        kept, meta = self._fetch(orders)
        self.assertEqual([o['orderNumber'] for o in kept], ['A'])
        self.assertEqual(meta['fetched'], 4)
        self.assertEqual(meta['skipped_status'], 3)

    def test_status_matching_ignores_case(self):
        kept, _ = self._fetch([dict(GOOEY_PULL, status='Accepted')])
        self.assertEqual(len(kept), 1)

    def test_several_statuses_can_be_accepted(self):
        self.api.fetch_status_include = 'accepted, pending'
        kept, _ = self._fetch([
            dict(GOOEY_PULL, orderNumber='A', status='pending'),
            dict(GOOEY_PULL, orderNumber='B', status='delivered'),
        ])
        self.assertEqual([o['orderNumber'] for o in kept], ['A'])

    def test_empty_filter_takes_everything(self):
        self.api.fetch_status_include = ''
        kept, meta = self._fetch([
            dict(GOOEY_PULL, status='delivered'), dict(GOOEY_PULL, status='cancelled')])
        self.assertEqual(len(kept), 2)
        self.assertEqual(meta['skipped_status'], 0)

    def test_an_order_with_no_status_field_is_not_assumed_deliverable(self):
        payload = dict(GOOEY_PULL)
        payload.pop('status')
        kept, _ = self._fetch([payload])
        self.assertEqual(kept, [])


class GooeyPayloadTests(AllowAnyHostMixin, TestCase):
    """The live payload, staged end to end."""

    def setUp(self):
        super().setUp()
        _, self.business = make_active_business(48, 'pull_gooey')
        self.api = make_pull_source(
            self.business, fetch_status_path='status', fetch_status_include='accepted',
            column_mapping={'dl_street': 'customer.street', 'dl_zone': 'customer.zone',
                            'dl_building': 'customer.buildingNumber'})

    def test_prepaid_order_carries_no_cod(self):
        """Every Gooey order is paid at checkout. Billing one as COD would have
        the driver ask the customer to pay a second time."""
        with patch.object(store_pull.requests, 'get',
                          return_value=FakeResponse({'orders': [GOOEY_PULL]})):
            created, _ = _sync_custom_pull_source(self.api)
        self.assertEqual(created, 1)
        temp = orders_models.TempOrder.objects.get(client_order_code='GOOEY-807598')
        self.assertEqual(temp.cod_amount, '0')
        self.assertEqual(temp.financial_status, 'paid')

    def test_qatar_address_is_carried_in_full(self):
        with patch.object(store_pull.requests, 'get',
                          return_value=FakeResponse({'orders': [GOOEY_PULL]})):
            _sync_custom_pull_source(self.api)
        temp = orders_models.TempOrder.objects.get(client_order_code='GOOEY-807598')
        self.assertEqual(temp.dl_zone, '90')
        self.assertEqual(temp.dl_street, '911')
        self.assertEqual(temp.dl_building, '4')
        # A bare number is not an address a driver can use.
        self.assertIn('Street 911', temp.customer_address)
        self.assertIn('Zone 90', temp.customer_address)
        self.assertIn('House 4', temp.customer_address)
        self.assertEqual(temp.customer_name, 'Hissa Khalid Al Abdulla')
        self.assertEqual(temp.customer_phone, '51565556')


class PerSourceMappingTests(AllowAnyHostMixin, TestCase):
    """A seller can run both directions at once, and the two payloads may differ."""

    def setUp(self):
        super().setUp()
        _, self.business = make_active_business(49, 'pull_two_rows')
        # The push row, with a mapping written against the push payload.
        self.push_row = make_custom_source(
            self.business, is_default=True,
            column_mapping={'customer_address': 'customer.street',
                            'package_desc': 'items[].name'})
        # The pull row, with its own mapping for the slimmer lookup payload.
        self.pull_row = make_pull_source(
            self.business, is_default=False, fetch_status_include='accepted',
            column_mapping={'dl_street': 'customer.street'})

    def test_pull_uses_its_own_mapping_not_the_push_rows(self):
        with patch.object(store_pull.requests, 'get',
                          return_value=FakeResponse({'orders': [GOOEY_PULL]})):
            _sync_custom_pull_source(self.pull_row)
        temp = orders_models.TempOrder.objects.get(client_order_code='GOOEY-807598')
        self.assertEqual(temp.api_settings_id, self.pull_row.id)
        # The push mapping would have made the address the bare string "911".
        self.assertNotEqual(temp.customer_address, '911')
        self.assertIn('Street 911', temp.customer_address)
        self.assertEqual(temp.dl_street, '911')


class SellerOrdersPreviewTests(AllowAnyHostMixin, TestCase):
    """The staff seller page's Orders tab, for a pull integration."""

    def setUp(self):
        super().setUp()
        from workforce.tests_views import WorkforceTestMixin
        _, self.business = make_active_business(50, 'pull_preview')
        # Nothing is guessed from field names, so the preview needs a mapping to
        # show anything at all — the same mapping the pull itself reads.
        self.api = make_pull_source(
            self.business, fetch_status_path='status', fetch_status_include='accepted',
            column_mapping={
                'client_order_code': 'orderNumber',
                'customer_name': 'customer.name',
                'customer_phone': 'customer.phone',
                'dl_zone': 'customer.zone',
                'dl_street': 'customer.street',
                'dl_building': 'customer.buildingNumber',
                'dl_landmark': 'customer.area',
                'payment_method': 'paymentMethod',
            })
        # StaffDepartmentMiddleware fails closed, so is_staff alone is not enough
        # to reach /workforce/ — the user needs a desk or every request 302s.
        self.staff, _ = WorkforceTestMixin().create_staff_user(username='pull_preview_staff')
        self.client.force_login(self.staff)

    def _get(self, orders, limit=10):
        with patch.object(store_pull.requests, 'get',
                          return_value=FakeResponse({'orders': orders})):
            return self.client.get(
                f'/workforce/sellers/{self.business.business_id}/api-orders/?limit={limit}')

    def test_pulled_orders_are_listed(self):
        r = self._get([GOOEY_PULL])
        self.assertEqual(r.status_code, 200)
        body = r.content.decode()
        self.assertIn('GOOEY-807598', body)
        self.assertIn('Hissa Khalid Al Abdulla', body)
        self.assertIn('51565556', body)

    def test_filtered_out_orders_are_shown_with_a_reason(self):
        """An order missing from the list with no explanation is the thing that
        sends staff hunting; show it, greyed, with why it was skipped."""
        r = self._get([
            dict(GOOEY_PULL, orderNumber='KEEP-1', status='accepted'),
            dict(GOOEY_PULL, orderNumber='GONE-1', status='cancelled'),
        ])
        body = r.content.decode()
        self.assertIn('KEEP-1', body)
        self.assertIn('GONE-1', body)
        self.assertIn('Skipped by filter', body)

    def test_limit_is_honoured(self):
        many = [dict(GOOEY_PULL, orderNumber=f'N-{i}') for i in range(25)]
        body = self._get(many, limit=10).content.decode()
        self.assertIn('N-9', body)
        self.assertNotIn('N-10<', body)

    def test_already_staged_orders_are_marked(self):
        from ezzy_api.store_api import stage_order_payload
        stage_order_payload(self.business, GOOEY_PULL, api_settings=self.api)
        body = self._get([GOOEY_PULL]).content.decode()
        self.assertIn('In Temp Orders', body)

    def test_a_failing_store_shows_the_error_not_a_500(self):
        with patch.object(store_pull.requests, 'get',
                          return_value=FakeResponse(None, status_code=401)):
            r = self.client.get(
                f'/workforce/sellers/{self.business.business_id}/api-orders/?limit=10')
        self.assertEqual(r.status_code, 200)
        self.assertIn('rejected our key', r.content.decode())

    def test_push_only_seller_is_unaffected(self):
        """The Shopify/Woo path must not be hijacked by the new branch."""
        _, other = make_active_business(51, 'pull_preview_push')
        make_custom_source(other)
        r = self.client.get(f'/workforce/sellers/{other.business_id}/api-orders/?limit=10')
        self.assertEqual(r.status_code, 200)
        self.assertIn('No Shopify or WooCommerce API configured', r.content.decode())


class NoGuessingTests(AllowAnyHostMixin, TestCase):
    """A custom integration reads its mapping and nothing else.

    Guessing a field from a likely-looking key is what silently merges two
    products onto one SKU or bills a customer the wrong amount, so an unmapped
    field must stay visibly empty instead of being filled by inference.
    """

    def setUp(self):
        super().setUp()
        from workforce.tests_views import WorkforceTestMixin
        _, self.business = make_active_business(52, 'pull_noguess')
        self.api = make_pull_source(
            self.business, fetch_status_path='status', fetch_status_include='accepted')
        self.staff, _ = WorkforceTestMixin().create_staff_user(username='pull_noguess_staff')
        self.client.force_login(self.staff)

    def test_unmapped_integration_says_so_instead_of_inventing_values(self):
        with patch.object(store_pull.requests, 'get',
                          return_value=FakeResponse({'orders': [GOOEY_PULL]})):
            r = self.client.get(
                f'/workforce/sellers/{self.business.business_id}/api-orders/?limit=10')
        body = r.content.decode()
        self.assertIn('no <strong>order code</strong> mapping', body)
        self.assertIn('(unmapped)', body)
        # The value exists in the payload under an obvious name; we still do not use it.
        self.assertNotIn('GOOEY-807598', body)

    def test_product_resolver_takes_only_mapped_fields(self):
        payload = {'title': 'Brownie Box', 'sku': 'BRW-1', 'price': 40, 'barcode': '99887766'}
        resolved = store_pull.resolve_product(
            payload, {'item_name': 'title', 'item_sku': 'sku'})
        self.assertEqual(resolved, {'item_name': 'Brownie Box', 'item_sku': 'BRW-1'})
        # price and barcode sit right there under obvious names and are still skipped.
        self.assertNotIn('item_price', resolved)
        self.assertNotIn('barcode', resolved)

    def test_product_with_no_mapping_resolves_to_nothing(self):
        self.assertEqual(store_pull.resolve_product({'title': 'X', 'sku': 'Y'}, {}), {})
        self.assertEqual(store_pull.resolve_product({'title': 'X'}, None), {})

    def test_product_without_a_mapped_name_is_refused(self):
        resolved = store_pull.resolve_product({'sku': 'ONLY-SKU'}, {'item_sku': 'sku'})
        self.assertEqual(resolved, {})
        self.assertEqual(store_pull.unmapped_product_fields({'item_sku': 'sku'}), ['item_name'])

    def test_nested_and_list_product_paths_resolve(self):
        payload = {'node': {'name': 'Cake'}, 'variants': [{'sku': 'CK-1'}, {'sku': 'CK-2'}]}
        resolved = store_pull.resolve_product(
            payload, {'item_name': 'node.name', 'item_sku': 'variants[].sku'})
        self.assertEqual(resolved['item_name'], 'Cake')
        self.assertEqual(resolved['item_sku'], 'CK-1')


class ProductPullTests(AllowAnyHostMixin, TestCase):
    """Pulling a catalogue is configured separately from pulling orders."""

    def setUp(self):
        super().setUp()
        from workforce.tests_views import WorkforceTestMixin
        _, self.business = make_active_business(53, 'pull_products')
        self.api = make_pull_source(
            self.business,
            fetch_products_url='https://shop.example/api/products',
            product_column_mapping={'item_name': 'title', 'item_sku': 'sku',
                                    'item_price': 'price'})
        self.staff, _ = WorkforceTestMixin().create_staff_user(username='pull_products_staff')
        self.client.force_login(self.staff)

    def test_an_order_url_alone_is_not_a_product_source(self):
        orders_only = make_pull_source(self.business, fetch_products_url='')
        self.assertTrue(store_pull.is_pull_source(orders_only))
        self.assertFalse(store_pull.is_product_pull_source(orders_only))
        self.assertTrue(store_pull.is_product_pull_source(self.api))

    def test_products_are_fetched_from_their_own_url(self):
        body = {'products': [{'title': 'Brownie Box', 'sku': 'BRW-1', 'price': 40}]}
        with patch.object(store_pull.requests, 'get', return_value=FakeResponse(body)) as mock_get:
            products, meta = store_pull.fetch_products(self.api)
        self.assertEqual(meta['count'], 1)
        self.assertEqual(mock_get.call_args[0][0], 'https://shop.example/api/products')

    def test_product_fetch_reuses_the_same_credential(self):
        with patch.object(store_pull.requests, 'get',
                          return_value=FakeResponse({'products': []})) as mock_get:
            store_pull.fetch_products(self.api)
        headers = mock_get.call_args[1]['headers']
        self.assertEqual(headers['Authorization'], 'Bearer seller-side-key-123')

    def test_no_product_url_is_a_clear_refusal(self):
        self.api.fetch_products_url = ''
        with self.assertRaises(PullError) as ctx:
            store_pull.fetch_products(self.api)
        self.assertIn('No product fetch URL', str(ctx.exception))

    def test_products_tab_lists_mapped_products(self):
        body = {'products': [
            {'title': 'Brownie Box', 'sku': 'BRW-1', 'price': 40},
            {'title': 'Cake', 'sku': 'CK-1', 'price': 95},
        ]}
        with patch.object(store_pull.requests, 'get', return_value=FakeResponse(body)):
            r = self.client.get(f'/workforce/sellers/{self.business.business_id}/api-products/')
        self.assertEqual(r.status_code, 200)
        page = r.content.decode()
        self.assertIn('Brownie Box', page)
        self.assertIn('BRW-1', page)

    def test_products_tab_refuses_an_unmapped_integration(self):
        self.api.product_column_mapping = None
        self.api.save(update_fields=['product_column_mapping'])
        with patch.object(store_pull.requests, 'get',
                          return_value=FakeResponse({'products': [{'title': 'X', 'sku': 'Y'}]})) as mock_get:
            r = self.client.get(f'/workforce/sellers/{self.business.business_id}/api-products/')
        self.assertIn('item_name', r.content.decode())
        # Nothing is even fetched until a mapping exists — no point calling out.
        self.assertFalse(mock_get.called)


class IntegrationFieldMapTests(TestCase):
    """One definition of platform -> fields, serving both UIs.

    The client form and the staff modal each kept their own hardcoded copy, which
    is how a field added to one went missing from the other.
    """

    def test_custom_shows_only_its_own_fields(self):
        from business import integration_fields as IF
        fields = IF.fields_for('custom')
        # A custom integration authenticates against the seller's API with their
        # key; the platform credential boxes belong to Shopify/Woo/TikTok.
        for absent in ('api_key', 'api_secret', 'api_access_token', 'api_version'):
            self.assertNotIn(absent, fields, absent)
        # Endpoint paths are fragments appended to a store URL — custom carries
        # whole URLs, so showing these gave two boxes for one job.
        self.assertNotIn('order_api_endpoint', fields)
        self.assertNotIn('product_api_endpoint', fields)
        for present in ('fetch_orders_url', 'fetch_auth_style', 'fetch_api_key',
                        'fetch_status_include', 'fetch_products_url', 'fetch_enabled'):
            self.assertIn(present, fields, present)

    def test_other_platforms_keep_their_credentials(self):
        from business import integration_fields as IF
        self.assertIn('api_key', IF.fields_for('shopify'))
        self.assertIn('order_api_endpoint', IF.fields_for('woocommerce'))
        self.assertIn('tiktok_shop_id', IF.fields_for('tiktokshop'))
        # ...and none of them offer the custom pull fields.
        for platform in ('shopify', 'woocommerce', 'tiktokshop', 'google_sheet'):
            self.assertNotIn('fetch_orders_url', IF.fields_for(platform), platform)

    def test_every_listed_field_exists_on_the_model(self):
        """A typo in the map would silently hide a field in both UIs."""
        from business import integration_fields as IF
        from business.models import BusinessApiSettings
        real = {f.name for f in BusinessApiSettings._meta.get_fields()}
        for field in IF.ALL_FIELDS:
            self.assertIn(field, real, f'{field} is in the map but not on the model')

    def test_unknown_platform_falls_back_rather_than_blanking_the_form(self):
        from business import integration_fields as IF
        self.assertEqual(IF.fields_for('not_a_platform'), IF.fields_for('custom'))

    def test_map_is_json_serialisable_for_the_templates(self):
        import json
        from business import integration_fields as IF
        decoded = json.loads(json.dumps(IF.as_dict()))
        self.assertIn('custom', decoded['platforms'])
        self.assertIn('fetch_auth_name', decoded['conditional'])
