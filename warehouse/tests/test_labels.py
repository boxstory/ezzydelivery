"""
Purpose: Tests for product/variant QR label printing and internal barcode assignment.
Used by: `python manage.py test warehouse.tests.test_labels`
Notes: The QR test decodes the emitted SVG back into a module matrix and compares it to the library's own — the run-merging in generate_qr_svg is the part that can silently corrupt a code.
"""

import re

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from business.models import Business
from product.barcode_utils import (
    assign_internal_barcode,
    generate_qr_svg,
    internal_barcode_for,
    label_payload,
    variant_line,
)
from product.models import ColorVariant, Product, UnitVariant
from warehouse.models import StockLevel, Warehouse


def matrix_from_svg(svg):
    """Rebuild the module grid from the emitted rects, minus the background."""
    size = int(re.search(r'viewBox="0 0 (\d+) \d+"', svg).group(1))
    grid = [[False] * size for _ in range(size)]
    for x, y, w, h in re.findall(r'<rect x="(\d+)" y="(\d+)" width="(\d+)" height="(\d+)"/>', svg):
        x, y, w, h = int(x), int(y), int(w), int(h)
        if w == size and h == size:
            continue
        for yy in range(y, y + h):
            for xx in range(x, x + w):
                grid[yy][xx] = True
    return grid


class QrSvgTests(TestCase):
    def test_svg_matches_library_matrix(self):
        import qrcode
        from qrcode import constants

        for payload in ['001660', 'EZ300001', '3-00012', 'https://ezzydelivery.qa/x/1/']:
            qr = qrcode.QRCode(
                version=None, error_correction=constants.ERROR_CORRECT_M,
                box_size=1, border=4,
            )
            qr.add_data(payload)
            qr.make(fit=True)
            self.assertEqual(
                qr.get_matrix(), matrix_from_svg(generate_qr_svg(payload)),
                f"SVG does not round-trip for {payload!r}",
            )

    def test_empty_payload_returns_empty_string(self):
        self.assertEqual(generate_qr_svg(''), '')
        self.assertEqual(generate_qr_svg(None), '')


class LabelPayloadTests(TestCase):
    def setUp(self):
        self.business = Business.objects.create(
            business_id=910101, business_name='Label Co', business_status='active')
        self.product = Product.objects.create(
            business=self.business, brand_name='Acme', item_name='Widget', item_sku='W-1',
        )

    def test_payload_prefers_real_barcode(self):
        self.product.barcode = '1234567890123'
        self.assertEqual(label_payload(self.product), '1234567890123')

    def test_payload_falls_back_to_product_id(self):
        self.assertEqual(label_payload(self.product), self.product.product_id)

    def test_internal_barcode_derives_from_product_id(self):
        expected = 'EZ' + self.product.product_id.replace('-', '')
        self.assertEqual(internal_barcode_for(self.product), expected)

    def test_assign_writes_once_and_never_overwrites(self):
        code = assign_internal_barcode(self.product)
        self.product.refresh_from_db()
        self.assertEqual(self.product.barcode, code)

        self.product.barcode = '999'
        self.product.save(update_fields=['barcode'])
        self.assertEqual(assign_internal_barcode(self.product), '999')
        self.product.refresh_from_db()
        self.assertEqual(self.product.barcode, '999')

    def test_assign_sidesteps_a_collision(self):
        taken = internal_barcode_for(self.product)
        Product.objects.create(
            business=self.business, brand_name='Other', item_name='Clash',
            item_sku='C-1', barcode=taken,
        )
        self.assertEqual(assign_internal_barcode(self.product), f'{taken}-1')


class VariantLineTests(TestCase):
    def setUp(self):
        self.business = Business.objects.create(
            business_id=910102, business_name='Variant Co', business_status='active')
        self.color = ColorVariant.objects.create(color_variant='Ivory')
        self.unit = UnitVariant.objects.create(unit_variant='Box')

    def test_built_from_colour_size_unit(self):
        product = Product.objects.create(
            business=self.business, brand_name='B', item_name='N', item_sku='S1',
            color=self.color, size='L', unit=self.unit,
        )
        self.assertEqual(variant_line(product), 'Ivory / L / Box')

    def test_stored_label_wins(self):
        product = Product.objects.create(
            business=self.business, brand_name='B', item_name='N', item_sku='S2',
            color=self.color, variant_label='50ml / Gift Box',
        )
        self.assertEqual(variant_line(product), '50ml / Gift Box')


class PrintLabelViewTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user('lbl_staff', password='x', is_staff=True)
        self.seller = User.objects.create_user('lbl_seller', password='x')
        self.business = Business.objects.create(
            business_id=910103, business_name='Print Co', business_status='active')
        self.warehouse = Warehouse.objects.create(name='FC', code='FC-LBL')
        self.products = [
            Product.objects.create(
                business=self.business, brand_name='B', item_name=f'P{i}',
                item_sku=f'SKU-{i}', variant_group='G-1',
            )
            for i in range(3)
        ]
        self.stock = StockLevel.objects.create(
            product=self.products[0], warehouse=self.warehouse, quantity_on_hand=12,
        )
        self.url = reverse('warehouse:print_product_labels')

    def test_requires_staff(self):
        self.client.force_login(self.seller)
        self.assertEqual(self.client.get(self.url).status_code, 302)

    def test_renders_one_label_per_product(self):
        self.client.force_login(self.staff)
        response = self.client.get(self.url, {'product_ids': [p.id for p in self.products]})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content.decode().count('class="whlb__label"'), 3)

    def test_variant_group_pulls_in_every_sibling(self):
        self.client.force_login(self.staff)
        response = self.client.get(self.url, {'variant_group': 'G-1'})
        self.assertEqual(response.content.decode().count('class="whlb__label"'), 3)

    def test_stock_id_carries_on_hand_for_the_copies_default(self):
        self.client.force_login(self.staff)
        response = self.client.get(self.url, {'stock_ids': [self.stock.id]})
        self.assertIn('data-onhand="12"', response.content.decode())

    def test_per_item_copies_ride_in_as_qty_pairs(self):
        self.client.force_login(self.staff)
        response = self.client.get(self.url, {
            'product_ids': [self.products[0].id, self.products[1].id],
            'qty': [f'{self.products[0].id}:7', f'{self.products[1].id}:3'],
        })
        html = response.content.decode()
        self.assertIn('data-copies="7"', html)
        self.assertIn('data-copies="3"', html)

    def test_bogus_preset_and_qr_mode_fall_back(self):
        self.client.force_login(self.staff)
        response = self.client.get(self.url, {
            'product_ids': [self.products[0].id], 'preset': 'nope', 'qr_mode': 'nope',
        })
        self.assertIn('whlb__sheet--l38x25', response.content.decode())

    def test_printing_stamps_the_audit_fields(self):
        self.client.force_login(self.staff)
        self.client.get(self.url, {'product_ids': [self.products[0].id]})
        self.products[0].refresh_from_db()
        self.assertEqual(self.products[0].label_print_count, 1)
        self.assertIsNotNone(self.products[0].label_printed_at)


class AssignBarcodesViewTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user('bc_staff', password='x', is_staff=True)
        self.seller = User.objects.create_user('bc_seller', password='x')
        self.business = Business.objects.create(
            business_id=910104, business_name='Barcode Co', business_status='active')
        self.blank = Product.objects.create(
            business=self.business, brand_name='B', item_name='Blank', item_sku='B-1',
        )
        self.kept = Product.objects.create(
            business=self.business, brand_name='B', item_name='Kept', item_sku='K-1',
            barcode='5060000000000',
        )
        self.url = reverse('warehouse:assign_internal_barcodes')

    def test_requires_staff(self):
        self.client.force_login(self.seller)
        response = self.client.post(self.url, {'product_ids': [self.blank.id]})
        self.assertEqual(response.status_code, 302)
        self.blank.refresh_from_db()
        self.assertFalse(self.blank.barcode)

    def test_get_does_not_write(self):
        self.client.force_login(self.staff)
        self.client.get(self.url)
        self.blank.refresh_from_db()
        self.assertFalse(self.blank.barcode)

    def test_assigns_blanks_and_leaves_real_barcodes_alone(self):
        self.client.force_login(self.staff)
        response = self.client.post(self.url, {
            'product_ids': [self.blank.id, self.kept.id], 'as_json': '1',
        })
        self.assertEqual(response.json(), {'status': 'ok', 'assigned': 1, 'skipped': 1})

        self.blank.refresh_from_db()
        self.kept.refresh_from_db()
        self.assertEqual(self.blank.barcode, internal_barcode_for(self.blank))
        self.assertEqual(self.kept.barcode, '5060000000000')
