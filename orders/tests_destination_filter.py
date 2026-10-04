# Purpose: Tests that the Qatar-only switch actually withholds a GCC store's foreign orders during staging.
# Used by: manage.py test orders.tests_destination_filter
# Notes: A foreign order is staged as 'skipped', never deleted — deleting it destroys the
#        answer to "why is order X missing?". Shopify is mocked at _fetch_shopify_orders,
#        which already returns row dicts, so no network and no shopify lib needed.
from unittest.mock import patch

from django.test import TestCase

from business import models as business_models
from ezzy_api.tests_store_api import make_active_business
from orders import models as orders_models
from orders.tasks import _sync_api_source


def make_shopify_source(business, **over):
    fields = dict(
        business=business, api_type='shopify',
        site_api_url='https://teststore.myshopify.com',
        is_verify_api=True, is_default=True,
        import_qatar_only=True,
    )
    fields.update(over)
    return business_models.BusinessApiSettings.objects.create(**fields)


def row(platform_id, country, phone='', name=None):
    """A row shaped like orders.tasks._shopify_order_to_row returns."""
    return {
        'platform_id': str(platform_id),
        'order_id': name or f'#{platform_id}',
        'name': 'Test Buyer',
        'phone': phone,
        'address': '346, 407',
        'cod': '100',
        'total_price': '100',
        'date': '2026-10-01T10:00:00+03:00',
        'financial_status': 'paid',
        'source': 'shopify',
        'line_items': [],
        'package_desc': 'Oil x1',
        'shipping.country_code': country,
        'shipping.phone': phone,
    }


class StagingFilterTests(TestCase):
    def setUp(self):
        _, self.business = make_active_business(7701, 'qa_filter_seller')

    def _sync(self, rows, api):
        with patch('orders.tasks._fetch_shopify_orders', return_value=rows):
            return _sync_api_source(api)

    def _statuses(self):
        return dict(orders_models.TempOrder.objects
                    .values_list('platform_id', 'status'))

    def test_foreign_orders_are_staged_as_skipped_not_deleted(self):
        api = make_shopify_source(self.business)
        self._sync([row(1011, 'AE', '0542042944'),
                    row(1009, 'BH', '0097339655967'),
                    row(1012, 'QA', '33445566')], api)

        # All three rows still exist: the answer to "why is #1011 missing?" has
        # to survive somewhere a human can look.
        self.assertEqual(orders_models.TempOrder.objects.count(), 3)
        self.assertEqual(self._statuses(),
                         {'1011': 'skipped', '1009': 'skipped', '1012': 'new'})

    def test_only_the_qatar_order_is_importable(self):
        api = make_shopify_source(self.business)
        self._sync([row(1011, 'AE'), row(1012, 'QA')], api)
        # 'new' is what the merchant commit path filters on.
        self.assertEqual(
            list(orders_models.TempOrder.objects.filter(status='new')
                 .values_list('platform_id', flat=True)),
            ['1012'])

    def test_skip_reason_is_recorded_on_the_row(self):
        api = make_shopify_source(self.business)
        self._sync([row(1011, 'AE')], api)
        temp = orders_models.TempOrder.objects.get(platform_id='1011')
        self.assertEqual(temp.raw_row.get('_skip_reason'), 'outside_service_area:AE')

    def test_switch_off_stages_everything_as_before(self):
        api = make_shopify_source(self.business, import_qatar_only=False)
        self._sync([row(1011, 'AE'), row(1009, 'BH'), row(1012, 'QA')], api)
        self.assertEqual(
            orders_models.TempOrder.objects.filter(status='new').count(), 3)
        self.assertEqual(
            orders_models.TempOrder.objects.filter(status='skipped').count(), 0)

    def test_qatari_phone_on_a_foreign_country_is_still_staged(self):
        api = make_shopify_source(self.business)
        self._sync([row(1013, 'AE', '33445566')], api)
        self.assertEqual(
            orders_models.TempOrder.objects.get(platform_id='1013').status, 'new')

    def test_order_with_no_country_and_no_phone_is_kept(self):
        api = make_shopify_source(self.business)
        self._sync([row(1014, '', '')], api)
        self.assertEqual(
            orders_models.TempOrder.objects.get(platform_id='1014').status, 'new')

    def test_address_changed_to_foreign_flips_a_staged_row(self):
        api = make_shopify_source(self.business)
        self._sync([row(1015, 'QA', '33445566')], api)
        self.assertEqual(
            orders_models.TempOrder.objects.get(platform_id='1015').status, 'new')

        # The buyer edits the destination to Dubai before we collect.
        self._sync([row(1015, 'AE', '0542042944')], api)
        self.assertEqual(
            orders_models.TempOrder.objects.get(platform_id='1015').status, 'skipped')

    def test_an_already_imported_row_is_never_flipped(self):
        api = make_shopify_source(self.business)
        self._sync([row(1016, 'QA', '33445566')], api)
        temp = orders_models.TempOrder.objects.get(platform_id='1016')
        temp.status = 'imported'
        temp.save(update_fields=['status'])

        # Withdrawing a delivery that is already a real Order would strand it.
        self._sync([row(1016, 'AE', '0542042944')], api)
        self.assertEqual(
            orders_models.TempOrder.objects.get(platform_id='1016').status, 'imported')

    def test_the_live_jm_auto_parts_set_stages_nothing_importable(self):
        api = make_shopify_source(self.business)
        rows = [row(1000 + n, 'AE', '0542042944') for n in range(1, 10)]
        rows.append(row(1010, 'BH', '0097339655967'))
        rows.append(row(1011, 'PK', '0558212796'))
        self._sync(rows, api)
        self.assertEqual(orders_models.TempOrder.objects.count(), 11)
        self.assertEqual(
            orders_models.TempOrder.objects.filter(status='new').count(), 0)
