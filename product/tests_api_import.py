"""
Purpose: Tests for the client-dashboard API product import endpoint (product_api_import).
Used by: `python manage.py test product.tests_api_import`
Notes: Covers the fulfillment SKU rule (used to 500 the import) and remote photo download.
"""
import json
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from business import models as business_models
from product.models import Product


class ProductApiImportTests(TestCase):
    """The import endpoint must always answer JSON, never a 500 HTML page."""

    def setUp(self):
        self.user = User.objects.create_user(username='importer', password='pw12345')
        self.business = business_models.Business.objects.create(
            business_id=900301,
            business_name='Import Co',
            business_code='IMP301',
            business_email='import@example.com',
            business_status='active',
            user=self.user,
            fulfillment_service_enabled=True,
            fulfillment_service_status='none',
        )
        self.client.force_login(self.user)
        self.url = reverse('product:product_api_import')

    def _post(self, products, update_existing=False):
        return self.client.post(
            self.url,
            data=json.dumps({'products': products, 'update_existing': update_existing}),
            content_type='application/json',
        )

    def test_missing_sku_gets_generated_not_500(self):
        """A store with no SKUs used to raise ValueError inside Product.save()."""
        resp = self._post([
            {'item_name': 'No SKU Item', 'item_price': '25', 'variant_id': '4519675'},
            {'item_name': 'Good Item', 'item_sku': 'SKU-1', 'item_price': '30'},
        ])
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['imported'], 2)
        self.assertEqual(data['generated_sku'], 1)
        self.assertTrue(Product.objects.filter(business=self.business, item_sku='EZ-4519675').exists())

    def test_sku_falls_back_to_counter_without_platform_ids(self):
        resp = self._post([{'item_name': 'Bare Item', 'item_price': '10'}])
        self.assertEqual(resp.json()['imported'], 1)
        self.assertEqual(
            Product.objects.get(business=self.business).item_sku,
            'EZ-900301-00001',
        )

    def test_variants_of_one_product_do_not_collide(self):
        """Each variant carries its own variant_id, so all of them import."""
        resp = self._post([
            {'item_name': 'Tee - S', 'platform_id': '77', 'variant_id': '1', 'item_price': '10'},
            {'item_name': 'Tee - M', 'platform_id': '77', 'variant_id': '2', 'item_price': '10'},
            {'item_name': 'Tee - L', 'platform_id': '77', 'variant_id': '3', 'item_price': '10'},
        ])
        self.assertEqual(resp.json()['imported'], 3)

    def test_duplicate_sku_is_skipped(self):
        self._post([{'item_name': 'Item', 'item_sku': 'SKU-9', 'item_price': '10'}])
        resp = self._post([{'item_name': 'Item again', 'item_sku': 'SKU-9', 'item_price': '10'}])
        data = resp.json()
        self.assertEqual(data['imported'], 0)
        self.assertEqual(data['skipped_duplicate'], 1)

    def test_duplicate_within_the_same_batch_is_skipped(self):
        resp = self._post([
            {'item_name': 'A', 'item_sku': 'SKU-DUP', 'item_price': '10'},
            {'item_name': 'B', 'item_sku': 'SKU-DUP', 'item_price': '10'},
        ])
        data = resp.json()
        self.assertEqual(data['imported'], 1)
        self.assertEqual(data['skipped_duplicate'], 1)

    def test_missing_name_is_skipped(self):
        resp = self._post([{'item_name': '  ', 'item_sku': 'SKU-2', 'item_price': '10'}])
        data = resp.json()
        self.assertEqual(data['imported'], 0)
        self.assertEqual(data['skipped'], 1)

    def test_sku_optional_when_fulfillment_disabled(self):
        self.business.fulfillment_service_enabled = False
        self.business.save()
        resp = self._post([{'item_name': 'No SKU Item', 'item_price': '25', 'variant_id': '99'}])
        data = resp.json()
        self.assertEqual(data['imported'], 1)
        self.assertEqual(data['skipped'], 0)

    @patch('product.views.attach_product_image', return_value=True)
    def test_image_url_is_downloaded(self, mock_attach):
        resp = self._post([{
            'item_name': 'Photo Item', 'item_sku': 'SKU-IMG', 'item_price': '10',
            'image_url': 'https://cdn.shopify.com/s/files/1/img.jpg',
        }])
        self.assertEqual(resp.json()['images_saved'], 1)
        self.assertEqual(mock_attach.call_args[0][1], 'https://cdn.shopify.com/s/files/1/img.jpg')

    @patch('product.views.attach_product_image', side_effect=Exception('CDN down'))
    def test_image_failure_does_not_lose_the_product(self, _mock):
        """A dead CDN must not cost the merchant the product row."""
        resp = self._post([{
            'item_name': 'Photo Item', 'item_sku': 'SKU-IMG2', 'item_price': '10',
            'image_url': 'https://cdn.shopify.com/s/files/1/img.jpg',
        }])
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data['imported'], 1)
        self.assertEqual(data['skipped_failed'], 0)
        self.assertTrue(Product.objects.filter(item_sku='SKU-IMG2').exists())


class ProductApiUpdateModeTests(TestCase):
    """update_existing=True refreshes rows instead of skipping them as duplicates."""

    def setUp(self):
        self.user = User.objects.create_user(username='updater', password='pw12345')
        self.business = business_models.Business.objects.create(
            business_id=900303,
            business_name='Update Co',
            business_code='UPD303',
            business_email='update@example.com',
            business_status='active',
            user=self.user,
            fulfillment_service_enabled=True,
            fulfillment_service_status='none',
        )
        self.client.force_login(self.user)
        self.url = reverse('product:product_api_import')

    def _post(self, products, update_existing=False):
        return self.client.post(
            self.url,
            data=json.dumps({'products': products, 'update_existing': update_existing}),
            content_type='application/json',
        )

    def test_existing_product_is_updated(self):
        self._post([{'item_name': 'Old Name', 'item_sku': 'SKU-U1', 'item_price': '10'}])
        resp = self._post(
            [{'item_name': 'New Name', 'item_sku': 'SKU-U1', 'item_price': '25',
              'brand_name': 'Acme'}],
            update_existing=True,
        )
        data = resp.json()
        self.assertEqual(data['updated'], 1)
        self.assertEqual(data['imported'], 0)
        p = Product.objects.get(item_sku='SKU-U1')
        self.assertEqual(p.item_name, 'New Name')
        self.assertEqual(p.item_price, 25)
        self.assertEqual(p.brand_name, 'Acme')
        self.assertEqual(Product.objects.filter(business=self.business).count(), 1)

    def test_real_sku_replaces_generated_one(self):
        """The case that motivated update mode: SKU added in Shopify after import."""
        self._post([{'item_name': 'Perfume', 'item_price': '100', 'variant_id': '55399702626595'}])
        self.assertTrue(Product.objects.filter(item_sku='EZ-55399702626595').exists())

        resp = self._post(
            [{'item_name': 'Perfume', 'item_sku': 'VEN-001', 'item_price': '100',
              'variant_id': '55399702626595'}],
            update_existing=True,
        )
        self.assertEqual(resp.json()['updated'], 1)
        self.assertEqual(Product.objects.filter(business=self.business).count(), 1)
        self.assertEqual(Product.objects.get(business=self.business).item_sku, 'VEN-001')

    def test_blank_api_values_do_not_wipe_local_data(self):
        self._post([{'item_name': 'Item', 'item_sku': 'SKU-U2', 'item_price': '40',
                     'brand_name': 'Local Brand', 'size': 'L'}])
        self._post(
            [{'item_name': 'Item', 'item_sku': 'SKU-U2', 'item_price': '',
              'brand_name': '', 'size': ''}],
            update_existing=True,
        )
        p = Product.objects.get(item_sku='SKU-U2')
        self.assertEqual(p.brand_name, 'Local Brand')
        self.assertEqual(p.size, 'L')
        self.assertEqual(p.item_price, 40)

    def test_unchanged_product_is_reported_not_updated(self):
        self._post([{'item_name': 'Same', 'item_sku': 'SKU-U3', 'item_price': '10'}])
        resp = self._post(
            [{'item_name': 'Same', 'item_sku': 'SKU-U3', 'item_price': '10'}],
            update_existing=True,
        )
        data = resp.json()
        self.assertEqual(data['updated'], 0)
        self.assertEqual(data['skipped_unchanged'], 1)

    def test_new_products_still_import_in_update_mode(self):
        resp = self._post(
            [{'item_name': 'Brand New', 'item_sku': 'SKU-U4', 'item_price': '10'}],
            update_existing=True,
        )
        self.assertEqual(resp.json()['imported'], 1)

    def test_update_mode_off_still_skips_duplicates(self):
        self._post([{'item_name': 'Old', 'item_sku': 'SKU-U5', 'item_price': '10'}])
        resp = self._post([{'item_name': 'New', 'item_sku': 'SKU-U5', 'item_price': '99'}])
        self.assertEqual(resp.json()['skipped_duplicate'], 1)
        self.assertEqual(Product.objects.get(item_sku='SKU-U5').item_name, 'Old')

    @patch('product.views.attach_product_image', return_value=True)
    def test_missing_photo_is_filled_on_update(self, mock_attach):
        self._post([{'item_name': 'NoPhoto', 'item_sku': 'SKU-U6', 'item_price': '10'}])
        mock_attach.reset_mock()
        resp = self._post(
            [{'item_name': 'NoPhoto v2', 'item_sku': 'SKU-U6', 'item_price': '10',
              'image_url': 'https://cdn.shopify.com/x.jpg'}],
            update_existing=True,
        )
        self.assertEqual(resp.json()['images_saved'], 1)
        self.assertEqual(mock_attach.call_count, 1)


class ProductImageImportTests(TestCase):
    """attach_product_image must be SSRF-safe and never raise."""

    def setUp(self):
        self.user = User.objects.create_user(username='imgowner', password='pw12345')
        self.business = business_models.Business.objects.create(
            business_id=900302,
            business_name='Img Co',
            business_code='IMG302',
            business_email='img@example.com',
            business_status='active',
            user=self.user,
            fulfillment_service_enabled=False,
            fulfillment_service_status='none',
        )
        self.product = Product.objects.create(
            business=self.business, item_name='P', item_sku='SKU-A', item_price=1)

    def test_internal_url_is_rejected(self):
        from product.image_import import attach_product_image
        self.assertFalse(attach_product_image(self.product, 'http://127.0.0.1:8000/secret.jpg'))
        self.assertFalse(attach_product_image(self.product, 'file:///etc/passwd'))
        self.product.refresh_from_db()
        self.assertFalse(bool(self.product.product_image))

    def test_blank_url_is_a_noop(self):
        from product.image_import import attach_product_image
        self.assertFalse(attach_product_image(self.product, ''))
        self.assertFalse(attach_product_image(self.product, None))

    def test_non_image_response_is_rejected(self):
        from product import image_import

        class FakeResp:
            status_code = 200
            headers = {'Content-Type': 'text/html'}

            def iter_content(self, n):
                yield b'<html>'

        with patch.object(image_import.requests, 'get', return_value=FakeResp()), \
                patch.object(image_import, 'validate_public_url', return_value=(True, '')):
            self.assertFalse(image_import.attach_product_image(self.product, 'https://x.test/a.jpg'))

    def test_image_is_saved(self):
        from product import image_import

        png = (b'\x89PNG\r\n\x1a\n' + b'\x00' * 64)

        class FakeResp:
            status_code = 200
            headers = {'Content-Type': 'image/png'}

            def iter_content(self, n):
                yield png

        with patch.object(image_import.requests, 'get', return_value=FakeResp()), \
                patch.object(image_import, 'validate_public_url', return_value=(True, '')):
            self.assertTrue(image_import.attach_product_image(
                self.product, 'https://cdn.test/s/files/photo.png'))

        self.product.refresh_from_db()
        self.assertTrue(self.product.product_image.name.endswith('.png'))
        self.assertIn('SKU-A', self.product.product_image.name)
