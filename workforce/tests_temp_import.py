"""
Purpose: Tests for temp-order product extraction from list-shaped raw rows (OneDrive/Sheet imports).
Used by: `python manage.py test workforce.tests_temp_import`
Notes: Guards the product_1..10 ceiling. The extractor was capped at 3 and silently dropped
       everything past Product:3 — sheets that use the slot number as a product code (Product:4
       filled while 1-3 are empty) lost the whole order.
"""
from django.test import TestCase

from business import models as business_models
from orders import models as orders_models
from workforce.views import MAX_PRODUCT_COLUMNS, _extract_products_from_raw_row

HEADERS = ['Order ID', 'Customer Name', 'Phone 1', 'Customer Address'] + [
    part for i in range(1, 11) for part in (f'Product:{i}', f'Count:{i}')
]

MAPPING = {
    'client_order_code': 'Order ID',
    'customer_name': 'Customer Name',
    'customer_phone': 'Phone 1',
    'customer_address': 'Customer Address',
    **{f'product_{i}': f'Product:{i}' for i in range(1, 11)},
    **{f'count_{i}': f'Count:{i}' for i in range(1, 11)},
}


class ExtractProductsFromRawRowTests(TestCase):

    def setUp(self):
        self.biz = business_models.Business.objects.create(
            business_id=900501,
            business_name='Sheet Co',
            business_code='SHT501',
            business_email='sheet@example.com',
            business_status='active',
            import_mapping={'onedrive': MAPPING},
        )
        self.source = orders_models.OneDriveSource.objects.create(
            business=self.biz,
            label='Sheet Co Data Entry',
            share_link='https://1drv.ms/x/s!example',
            last_sheet_name='Data Entry',
            last_headers=HEADERS,
        )

    def _temp_order(self, slots):
        """slots: {column_number: (name, count)} — everything else left blank."""
        raw = ['1001', 'Test Customer', '55000000', 'al wakra'] + [''] * 20
        for n, (name, count) in slots.items():
            raw[4 + (n - 1) * 2] = name
            raw[5 + (n - 1) * 2] = str(count)
        return orders_models.TempOrder.objects.create(
            source_type='onedrive',
            onedrive_source=self.source,
            business=self.biz,
            sheet_name='Data Entry',
            row_num=860,
            client_order_code='1001',
            customer_name='Test Customer',
            customer_phone='55000000',
            customer_address='al wakra',
            raw_row=raw,
        )

    def test_extracts_products_past_the_third_column(self):
        temp_order = self._temp_order({
            1: ('01_Alpha', 1),
            2: ('02_Beta', 2),
            3: ('03_Gamma', 1),
            4: ('04_Delta', 3),
            5: ('05_Epsilon', 1),
        })
        self.assertEqual(_extract_products_from_raw_row(temp_order), [
            {'name': '01_Alpha', 'qty': 1},
            {'name': '02_Beta', 'qty': 2},
            {'name': '03_Gamma', 'qty': 1},
            {'name': '04_Delta', 'qty': 3},
            {'name': '05_Epsilon', 'qty': 1},
        ])

    def test_extracts_sparse_slots(self):
        """Slot number doubles as the product code, so 1-3 are often empty."""
        temp_order = self._temp_order({
            1: ('01_Alpha', 1),
            4: ('04_Delta', 1),
            7: ('07_Eta', 2),
        })
        self.assertEqual(_extract_products_from_raw_row(temp_order), [
            {'name': '01_Alpha', 'qty': 1},
            {'name': '04_Delta', 'qty': 1},
            {'name': '07_Eta', 'qty': 2},
        ])

    def test_reads_the_last_mapped_column(self):
        temp_order = self._temp_order({MAX_PRODUCT_COLUMNS: ('10_Kappa', 4)})
        self.assertEqual(_extract_products_from_raw_row(temp_order),
                         [{'name': '10_Kappa', 'qty': 4}])
