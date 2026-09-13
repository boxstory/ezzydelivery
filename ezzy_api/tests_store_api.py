# Purpose: Tests for the custom-storefront order API (/api/v1/store/…).
# Used by: manage.py test ezzy_api.tests_store_api
# Notes: The COD rule and the idempotency rule are the two that cost real money
#        when they break — a prepaid order billed as COD charges the customer twice.

from decimal import Decimal

from django.test import TestCase
from rest_framework.test import APIClient

from business import models as business_models
from ezzy_api.tests import make_business, make_key
from orders import models as orders_models


def make_active_business(idx, username):
    """A seller cleared to trade — a new Business defaults to 'pending', which
    is write-blocked, so every create test would otherwise 403."""
    user, business = make_business(idx, username)
    business.business_status = 'active'
    business.save(update_fields=['business_status'])
    return user, business

SAMPLE = {
    'orderNumber': 'GOOEY-429869',
    'status': 'pending',
    'paymentMethod': 'applepay',
    'customer': {
        'name': 'Hind Alobaidli',
        'phone': '51060099',
        'area': 'Doha',
        'street': 'Al wahat street - alkhuraitiat',
        'buildingType': 'Apartment',
        'buildingNumber': '31',
        'notes': 'Big gate 3 go inside 31',
    },
    'items': [{'id': 'smore', 'name': "S'more", 'qty': 2, 'price': 35, 'lineTotal': 70}],
    'subtotal': 70,
    'deliveryFee': 20,
    'total': 90,
    'createdAt': '2026-09-11T16:00:29.000Z',
}

CREATE_URL = '/api/v1/store/orders/'


class StoreOrderApiTest(TestCase):
    def setUp(self):
        self.user, self.business = make_active_business(9101, 'storeowner')
        _, self.raw = make_key(self.business)
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.raw}')

    def post(self, payload=None, **over):
        body = dict(SAMPLE if payload is None else payload)
        body.update(over)
        return self.client.post(CREATE_URL, body, format='json')

    def test_creates_order_from_storefront_payload(self):
        res = self.post()
        self.assertEqual(res.status_code, 201, res.data)
        order = orders_models.Order.objects.get(client_order_code='GOOEY-429869')
        self.assertEqual(order.business, self.business)
        self.assertEqual(order.customer_name, 'Hind Alobaidli')
        self.assertEqual(order.customer_phone, '51060099')
        self.assertEqual(order.dl_building, 31)
        self.assertEqual(order.order_status, 'to_review')
        self.assertEqual(order.platform, 'api')
        self.assertEqual(order.package_qty, 2)
        self.assertIn('Apartment 31', order.customer_address)
        self.assertEqual(order.order_items.count(), 1)
        item = order.order_items.first()
        self.assertEqual(item.quantity, 2)
        self.assertEqual(item.unit_price, Decimal('35'))

    def test_prepaid_order_is_never_cod(self):
        """applepay/card must leave the driver nothing to collect."""
        self.post()
        order = orders_models.Order.objects.get(client_order_code='GOOEY-429869')
        self.assertEqual(order.cod_amount, Decimal('0'))
        self.assertEqual(order.cod_status_by_client, 'online_paid')

    def test_cod_order_carries_the_full_total(self):
        self.post(orderNumber='COD-1', paymentMethod='cod')
        order = orders_models.Order.objects.get(client_order_code='COD-1')
        self.assertEqual(order.cod_amount, Decimal('90'))
        self.assertEqual(order.cod_status_by_client, 'unpaid')

    def test_cod_total_falls_back_to_subtotal_plus_fee(self):
        payload = dict(SAMPLE)
        payload.pop('total')
        res = self.post(payload, orderNumber='COD-2', paymentMethod='cash')
        self.assertEqual(res.status_code, 201, res.data)
        order = orders_models.Order.objects.get(client_order_code='COD-2')
        self.assertEqual(order.cod_amount, Decimal('90'))

    def test_retry_is_idempotent(self):
        first = self.post()
        second = self.post()
        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 200)
        self.assertTrue(second.data['duplicate'])
        self.assertEqual(second.data['order_number'], first.data['order_number'])
        self.assertEqual(
            orders_models.Order.objects.filter(client_order_code='GOOEY-429869').count(), 1
        )

    def test_phone_is_normalized_to_local_form(self):
        payload = dict(SAMPLE)
        payload['customer'] = dict(SAMPLE['customer'], phone='+974 5566 7788')
        self.post(payload, orderNumber='PH-1')
        order = orders_models.Order.objects.get(client_order_code='PH-1')
        self.assertEqual(order.customer_phone, '55667788')

    def test_missing_name_or_phone_is_rejected(self):
        payload = dict(SAMPLE)
        payload['customer'] = {'area': 'Doha', 'street': 'X', 'buildingNumber': '1'}
        res = self.post(payload, orderNumber='BAD-1')
        self.assertEqual(res.status_code, 400)
        self.assertFalse(orders_models.Order.objects.filter(client_order_code='BAD-1').exists())

    def test_missing_order_number_is_rejected(self):
        payload = {k: v for k, v in SAMPLE.items() if k != 'orderNumber'}
        res = self.client.post(CREATE_URL, payload, format='json')
        self.assertEqual(res.status_code, 400)

    def test_business_from_body_is_ignored(self):
        """A caller cannot file an order under someone else's account."""
        _, other = make_active_business(9102, 'otherowner')
        self.post(orderNumber='TEN-1', business=other.pk)
        order = orders_models.Order.objects.get(client_order_code='TEN-1')
        self.assertEqual(order.business, self.business)

    def test_read_scope_key_cannot_create(self):
        _, read_only = make_key(self.business, scope='read')
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f'Bearer {read_only}')
        res = client.post(CREATE_URL, SAMPLE, format='json')
        self.assertEqual(res.status_code, 403)

    def test_anonymous_is_rejected(self):
        res = APIClient().post(CREATE_URL, SAMPLE, format='json')
        self.assertIn(res.status_code, (401, 403))

    def test_suspended_business_cannot_create(self):
        self.business.business_status = 'suspended'
        self.business.save(update_fields=['business_status'])
        res = self.post(orderNumber='SUS-1')
        self.assertIn(res.status_code, (401, 403))
        self.assertFalse(orders_models.Order.objects.filter(client_order_code='SUS-1').exists())

    def test_pending_business_cannot_create(self):
        self.business.business_status = 'pending'
        self.business.save(update_fields=['business_status'])
        res = self.post(orderNumber='PEN-1')
        self.assertEqual(res.status_code, 403)
        self.assertEqual(res.data['code'], 'business_pending_approval')


class StoreStatusApiTest(TestCase):
    def setUp(self):
        self.user, self.business = make_active_business(9103, 'statusowner')
        _, self.raw = make_key(self.business)
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.raw}')
        self.client.post(CREATE_URL, SAMPLE, format='json')

    def test_lookup_by_seller_reference(self):
        res = self.client.get('/api/v1/store/orders/GOOEY-429869/')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data['client_order_code'], 'GOOEY-429869')
        self.assertEqual(res.data['order_status'], 'to_review')
        self.assertEqual(res.data['cod_amount'], '0.00')

    def test_lookup_returns_the_whole_order(self):
        """The seller must be able to read back everything they sent."""
        res = self.client.get('/api/v1/store/orders/GOOEY-429869/')
        self.assertEqual(res.status_code, 200)
        body = res.data

        self.assertEqual(body['customer']['name'], 'Hind Alobaidli')
        self.assertEqual(body['customer']['phone'], '51060099')
        self.assertEqual(body['customer']['building'], 31)
        self.assertIn('Apartment 31', body['customer']['address'])
        self.assertEqual(body['customer']['notes'], 'Big gate 3 go inside 31')

        self.assertEqual(len(body['items']), 1)
        line = body['items'][0]
        self.assertEqual(line['name'], "S'more")
        self.assertEqual(line['qty'], 2)
        self.assertEqual(line['unit_price'], '35.00')
        self.assertEqual(line['line_total'], '70.00')

        self.assertEqual(body['amounts']['items_total'], '70.00')
        self.assertEqual(body['amounts']['delivery_fee'], '20.00')
        self.assertEqual(body['amounts']['cod_amount'], '0.00')

        self.assertEqual(body['package']['qty'], 2)
        self.assertEqual(body['received']['orderNumber'], 'GOOEY-429869')
        self.assertEqual(body['received']['paymentMethod'], 'applepay')

    def test_unknown_reference_is_404(self):
        res = self.client.get('/api/v1/store/orders/NOPE/')
        self.assertEqual(res.status_code, 404)

    def test_another_tenant_cannot_read_the_order(self):
        _, other = make_active_business(9104, 'intruder')
        _, other_raw = make_key(other)
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f'Bearer {other_raw}')
        res = client.get('/api/v1/store/orders/GOOEY-429869/')
        self.assertEqual(res.status_code, 404)

    def test_ping_reports_the_key_owner(self):
        res = self.client.get('/api/v1/store/ping/')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data['business'], self.business.business_name)
        self.assertTrue(res.data['can_create_orders'])


class StoreMappingTest(TestCase):
    """A storefront whose JSON uses its own key names is handled by the mapping
    staff save in the mapping manager, not by a code change."""

    ODD_PAYLOAD = {
        'ref': 'ACME-77',
        'pay': {'how': 'cod', 'grand_total': 120, 'shipping': 15},
        'buyer': {'full_name': 'Sara Ali', 'mobile': '00974 3344 5566'},
        'drop': {'line': 'Street 850, Al Sadd', 'villa': '12', 'zoneNo': '38'},
        'basket': [
            {'title': 'Cake', 'count': 1},
            {'title': 'Candles', 'count': 3},
        ],
        'placed': '2026-09-10T08:00:00.000Z',
        'remark': 'Leave with security',
    }

    MAPPING = {
        'client_order_code': 'ref',
        'customer_name': 'buyer.full_name',
        'customer_phone': 'buyer.mobile',
        'customer_address': 'drop.line',
        'dl_building': 'drop.villa',
        'dl_zone': 'drop.zoneNo',
        'cod_amount': 'pay.grand_total',
        'payment_method': 'pay.how',
        'dl_amount': 'pay.shipping',
        'seller_notes': 'remark',
        'order_date': 'placed',
        'product_1': 'basket[].title',
        'count_1': 'basket[].count',
    }

    def setUp(self):
        self.user, self.business = make_active_business(9201, 'mappedowner')
        business_models.BusinessApiSettings.objects.create(
            business=self.business, api_type='custom',
            site_api_url='https://acme.example', column_mapping=self.MAPPING,
            is_verify_api=True, is_default=True,
        )
        _, raw = make_key(self.business)
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {raw}')

    def test_mapped_payload_creates_a_correct_order(self):
        res = self.client.post(CREATE_URL, self.ODD_PAYLOAD, format='json')
        self.assertEqual(res.status_code, 201, res.data)

        order = orders_models.Order.objects.get(client_order_code='ACME-77')
        self.assertEqual(order.customer_name, 'Sara Ali')
        self.assertEqual(order.customer_phone, '33445566')
        self.assertEqual(order.customer_address, 'Street 850, Al Sadd')
        self.assertEqual(order.dl_building, 12)
        self.assertEqual(order.dl_zone, 38)
        self.assertEqual(order.dl_amount, Decimal('15'))
        self.assertEqual(order.order_notes, 'Leave with security')
        self.assertEqual(order.order_date.isoformat(), '2026-09-10')

    def test_mapped_payment_method_drives_cod(self):
        self.client.post(CREATE_URL, self.ODD_PAYLOAD, format='json')
        order = orders_models.Order.objects.get(client_order_code='ACME-77')
        self.assertEqual(order.cod_amount, Decimal('120'))
        self.assertEqual(order.cod_status_by_client, 'unpaid')

    def test_mapped_prepaid_payment_method_is_not_cod(self):
        payload = dict(self.ODD_PAYLOAD)
        payload['ref'] = 'ACME-78'
        payload['pay'] = dict(self.ODD_PAYLOAD['pay'], how='card')
        self.client.post(CREATE_URL, payload, format='json')
        order = orders_models.Order.objects.get(client_order_code='ACME-78')
        self.assertEqual(order.cod_amount, Decimal('0'))
        self.assertEqual(order.cod_status_by_client, 'online_paid')

    def test_collapsed_list_path_carries_every_line(self):
        """product_1 -> basket[].title maps a whole variable-length basket."""
        self.client.post(CREATE_URL, self.ODD_PAYLOAD, format='json')
        order = orders_models.Order.objects.get(client_order_code='ACME-77')
        lines = list(order.order_items.order_by('id'))
        self.assertEqual([(i.notes, i.quantity) for i in lines],
                         [('Cake', 1), ('Candles', 3)])
        self.assertEqual(order.package_qty, 4)

    def test_unmapped_seller_still_uses_the_builtin_guesses(self):
        """The mapping is per-seller — gooey's integration has none and must
        keep working off the built-in camelCase handling."""
        _, plain = make_active_business(9202, 'plainowner')
        _, raw = make_key(plain)
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f'Bearer {raw}')
        res = client.post(CREATE_URL, SAMPLE, format='json')
        self.assertEqual(res.status_code, 201, res.data)
        order = orders_models.Order.objects.get(business=plain)
        self.assertEqual(order.customer_name, 'Hind Alobaidli')
