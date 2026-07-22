# Purpose: Tests for fulfilment pickup-location consolidation (WH: identity vs placeholder)
# Used by: python manage.py test business.tests_fulfillment_consolidation

from decimal import Decimal
from io import StringIO

from django.core.management import call_command
from django.test import TestCase
from django.contrib.auth import get_user_model

from business.models import Business, PickupLocation
from core.models import Profile
from orders.models import Order
from warehouse.models import Warehouse, SellerWarehouseLink

User = get_user_model()


class FulfilmentConsolidationTestCase(TestCase):
    def make_business(self, idx):
        user = User.objects.create_user(username=f'fcbiz{idx}', password='x')
        profile = Profile.objects.create(
            user=user, first_name='Fc', last_name=f'B{idx}', phone=70000000 + idx)
        return Business.objects.create(
            business_id=7000 + idx, user=user, profile=profile,
            business_name=f'FC Biz {idx}', business_code=f'FCB{idx:03d}',
            business_status='active',
        )

    def test_new_business_uses_warehouse_identity(self):
        """With a warehouse present, the auto fulfilment row carries WH name + coords."""
        Warehouse.objects.create(
            name='EzzyDelivery FC- Doha', is_default=True,
            latitude=Decimal('25.28'), longitude=Decimal('51.53'),
        )
        business = self.make_business(1)
        row = PickupLocation.objects.get(business=business, is_fulfilment_center=True)
        self.assertEqual(row.pickup_location_title, 'WH: EzzyDelivery FC- Doha')
        self.assertIsNotNone(row.pickup_lat)

    def test_new_business_without_warehouse_gets_generic(self):
        business = self.make_business(2)
        row = PickupLocation.objects.get(business=business, is_fulfilment_center=True)
        self.assertEqual(row.pickup_location_title, 'Fulfillment Store')
        self.assertIsNone(row.pickup_lat)

    def test_warehouse_link_retires_placeholder_and_repoints_orders(self):
        # Legacy state: business with a coordless generic placeholder
        business = self.make_business(3)
        placeholder = PickupLocation.objects.get(
            business=business, is_fulfilment_center=True)
        self.assertEqual(placeholder.pickup_location_title, 'Fulfillment Store')
        order = Order.objects.create(
            business=business, client_order_code='FC001',
            customer_name='C', customer_phone='1', customer_address='A',
            pickup_location=placeholder,
        )

        # Staff link the business to a real warehouse
        warehouse = Warehouse.objects.create(
            name='EzzyDelivery FC- Sudan',
            latitude=Decimal('25.30'), longitude=Decimal('51.50'),
        )
        SellerWarehouseLink.objects.create(business=business, warehouse=warehouse)

        wh_row = PickupLocation.objects.get(business=business, warehouse=warehouse)
        self.assertEqual(wh_row.pickup_location_title, 'WH: EzzyDelivery FC- Sudan')

        placeholder.refresh_from_db()
        self.assertEqual(placeholder.pickup_status, 'inactive')
        order.refresh_from_db()
        self.assertEqual(order.pickup_location_id, wh_row.pk)

    def test_command_dry_run_then_apply(self):
        business = self.make_business(4)
        placeholder = PickupLocation.objects.get(
            business=business, is_fulfilment_center=True)
        # Simulate a WH row that exists WITHOUT the merge having run (legacy data)
        warehouse = Warehouse.objects.create(
            name='EzzyDelivery FC- West',
            latitude=Decimal('25.1'), longitude=Decimal('51.4'),
        )
        wh_row = PickupLocation.objects.create(
            business=business, pickup_location_title=f'WH: {warehouse.name}',
            locality='x', pickup_lat=warehouse.latitude, pickup_lon=warehouse.longitude,
            is_fulfilment_center=True, warehouse=warehouse, pickup_status='active',
        )

        out = StringIO()
        call_command('consolidate_fulfillment_stores', stdout=out)
        placeholder.refresh_from_db()
        self.assertEqual(placeholder.pickup_status, 'active')  # dry-run: untouched
        self.assertIn('would be merged', out.getvalue())

        call_command('consolidate_fulfillment_stores', '--apply', stdout=out)
        placeholder.refresh_from_db()
        self.assertEqual(placeholder.pickup_status, 'inactive')
        self.assertTrue(PickupLocation.objects.filter(
            pk=wh_row.pk, pickup_status='active').exists())
