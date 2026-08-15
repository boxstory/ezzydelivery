"""
Purpose: Tests for the staff seller page API product import (seller_api_products_import).
Used by: `python manage.py test workforce.tests_seller_import`
Notes: Posts the same hidden-input shape the fragment renders; the fetch step itself is not exercised.
"""
from unittest.mock import patch

from django.http import HttpResponse
from django.test import TestCase
from django.urls import reverse

from business import models as business_models
from product import models as product_models
from workforce.tests_views import WorkforceTestMixin


class SellerApiProductImportTests(WorkforceTestMixin, TestCase):

    def setUp(self):
        self.user = self.create_staff_user(username='sellerimporter')
        self.client.login(username='sellerimporter', password='Staff@123')
        self.biz = business_models.Business.objects.create(
            business_id=900401,
            business_name='Seller Co',
            business_code='SEL401',
            business_email='seller@example.com',
            business_status='active',
            fulfillment_service_enabled=True,
            fulfillment_service_status='none',
        )
        self.url = reverse('workforce:seller_api_products_import',
                           kwargs={'business_id': self.biz.business_id})

    def _post(self, rows, update_existing=False):
        data = {'selected': [str(i) for i in range(len(rows))]}
        for i, row in enumerate(rows):
            for key, value in row.items():
                data[f'p_{i}_{key}'] = value
        if update_existing:
            data['update_existing'] = '1'
        # The view re-renders the fragment, which re-fetches from the store; stub
        # that out so the test exercises the import path only.
        with patch('workforce.views.seller_api_products',
                   return_value=HttpResponse('ok')):
            return self.client.post(self.url, data)

    def _result(self, resp):
        return resp.wsgi_request._seller_api_import_result

    def test_import_generates_sku_and_saves_photo(self):
        with patch('product.image_import.attach_product_image', return_value=True):
            with patch('workforce.views.attach_product_image', return_value=True, create=True):
                resp = self._post([{
                    'title': 'Perfume', 'variant_title': 'Default Title', 'sku': '',
                    'price': '120', 'variant_id': '55399702626595', 'platform_id': '77',
                    'image': 'https://cdn.shopify.com/x.jpg',
                }])
        result = self._result(resp)
        self.assertEqual(result['imported'], 1)
        p = product_models.Product.objects.get(business=self.biz)
        self.assertEqual(p.item_sku, 'EZ-55399702626595')
        self.assertEqual(p.item_name, 'Perfume')

    def test_duplicate_is_skipped_without_update_mode(self):
        product_models.Product.objects.create(
            business=self.biz, item_name='Perfume', item_sku='EZ-999', item_price=100)
        resp = self._post([{
            'title': 'Perfume Renamed', 'sku': '', 'price': '150', 'variant_id': '999',
        }])
        result = self._result(resp)
        self.assertEqual(result['imported'], 0)
        self.assertEqual(result['skipped_duplicate'], 1)
        self.assertEqual(
            product_models.Product.objects.get(business=self.biz).item_name, 'Perfume')

    def test_update_mode_refreshes_existing_row(self):
        product_models.Product.objects.create(
            business=self.biz, item_name='Perfume', item_sku='EZ-999', item_price=100)
        resp = self._post([{
            'title': 'Perfume', 'variant_title': 'Large', 'sku': 'VEN-001',
            'price': '150', 'variant_id': '999', 'vendor': 'Vénora',
        }], update_existing=True)
        result = self._result(resp)
        self.assertEqual(result['updated'], 1)
        self.assertEqual(result['imported'], 0)
        p = product_models.Product.objects.get(business=self.biz)
        self.assertEqual(p.item_sku, 'VEN-001')
        self.assertEqual(p.item_price, 150)
        self.assertEqual(p.item_name, 'Perfume - Large')
        self.assertEqual(p.brand_name, 'Vénora')
        self.assertEqual(product_models.Product.objects.filter(business=self.biz).count(), 1)

    def test_update_mode_still_imports_new_rows(self):
        resp = self._post([{
            'title': 'Brand New', 'sku': 'NEW-1', 'price': '10',
        }], update_existing=True)
        self.assertEqual(self._result(resp)['imported'], 1)
