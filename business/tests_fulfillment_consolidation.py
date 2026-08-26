# Purpose: Tests for fulfilment pickup-location consolidation (WH: identity vs placeholder)
# Used by: python manage.py test business.tests_fulfillment_consolidation
# Notes: Creating a Business must NOT auto-create a fulfilment row — that is the
#        warehouse-link signal's job alone. Legacy placeholders are built explicitly.

from decimal import Decimal
from io import StringIO

from django.core.management import call_command
from django.test import TestCase
from django.contrib.auth import get_user_model

from business.models import Business, PickupLocation
from core.models import Profile
from orders.models import Order
from warehouse.models import Warehouse, SellerWarehouseLink
from workforce.tests_views import WorkforceTestMixin

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

    def make_placeholder(self, business):
        """The legacy coordless 'Fulfillment Store' row, as old data still carries."""
        return PickupLocation.objects.create(
            business=business, pickup_location_title='Fulfillment Store',
            locality='EzzyDelivery Fulfillment Center',
            pickup_status='active', is_fulfilment_center=True,
        )

    def test_new_business_gets_no_fulfilment_row(self):
        """A new business is never auto-stamped with a fulfilment pickup location.

        `fulfillment_service_enabled` defaults to True, so the old post_save
        receiver fired for every client and left a stale is_fulfilment_center row
        that made first-mile pickup refuse with 'fulfilment_center'.
        """
        Warehouse.objects.create(
            name='EzzyDelivery FC- Doha', is_default=True,
            latitude=Decimal('25.28'), longitude=Decimal('51.53'),
        )
        business = self.make_business(1)
        self.assertTrue(business.fulfillment_service_enabled)
        self.assertFalse(
            PickupLocation.objects.filter(business=business).exists(),
            'Creating a Business must not create any pickup location')

    def test_warehouse_link_is_the_only_creator(self):
        """Linking a warehouse — the staff action — is what creates the WH row."""
        business = self.make_business(2)
        self.assertFalse(PickupLocation.objects.filter(business=business).exists())

        warehouse = Warehouse.objects.create(
            name='EzzyDelivery FC- Doha',
            latitude=Decimal('25.28'), longitude=Decimal('51.53'),
        )
        SellerWarehouseLink.objects.create(business=business, warehouse=warehouse)

        row = PickupLocation.objects.get(business=business, is_fulfilment_center=True)
        self.assertEqual(row.pickup_location_title, 'WH: EzzyDelivery FC- Doha')
        self.assertIsNotNone(row.pickup_lat)

    def test_unlink_deactivates_the_row(self):
        business = self.make_business(5)
        warehouse = Warehouse.objects.create(
            name='EzzyDelivery FC- North',
            latitude=Decimal('25.4'), longitude=Decimal('51.4'),
        )
        link = SellerWarehouseLink.objects.create(business=business, warehouse=warehouse)
        row = PickupLocation.objects.get(business=business, warehouse=warehouse)
        self.assertEqual(row.pickup_status, 'active')

        link.delete()
        row.refresh_from_db()
        self.assertEqual(row.pickup_status, 'inactive')

    def test_warehouse_link_retires_placeholder_and_repoints_orders(self):
        # Legacy state: business with a coordless generic placeholder
        business = self.make_business(3)
        placeholder = self.make_placeholder(business)
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
        placeholder = self.make_placeholder(business)
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


class FulfilmentToggleOffTestCase(WorkforceTestMixin, TestCase):
    """Switching Fulfilment service off on the seller page settles the client's
    FC-flagged pickup rows. It must never strand a client with no collectable
    address — that is what silently killed first-mile pickup for Polyform."""

    def setUp(self):
        self.user, _ = self.create_staff_user('fctoggle')
        self.client.force_login(self.user)

    def make_business(self, idx, **kwargs):
        user = User.objects.create_user(username=f'ftbiz{idx}', password='x')
        profile = Profile.objects.create(
            user=user, first_name='Ft', last_name=f'B{idx}', phone=71000000 + idx)
        defaults = dict(
            business_id=7100 + idx, user=user, profile=profile,
            business_name=f'FT Biz {idx}', business_code=f'FTB{idx:03d}',
            business_status='active', fulfillment_service_enabled=True,
        )
        defaults.update(kwargs)
        return Business.objects.create(**defaults)

    def toggle_off(self, business):
        """POST the seller form with the switch absent — an unchecked checkbox
        is simply not submitted, which is what the browser does."""
        return self.client.post(
            f'/workforce/sellers/{business.business_id}/',
            {'business_name': business.business_name,
             'business_status': business.business_status})

    def test_shop_address_with_a_stale_flag_stays_collectable(self):
        business = self.make_business(1)
        shop = PickupLocation.objects.create(
            business=business, pickup_location_title='THE SHOP',
            locality='Zone 66', pickup_status='active',
            is_fulfilment_center=True,          # the old signal's stale stamp
        )
        self.toggle_off(business)
        shop.refresh_from_db()
        self.assertFalse(shop.is_fulfilment_center, 'stale flag must be cleared')
        self.assertEqual(shop.pickup_status, 'active',
                         'the client must keep a collectable address')

    def test_real_warehouse_row_is_deactivated_not_unflagged(self):
        business = self.make_business(2)
        warehouse = Warehouse.objects.create(
            name='EzzyDelivery FC- North', is_default=True,
            latitude=Decimal('25.4'), longitude=Decimal('51.4'))
        SellerWarehouseLink.objects.create(business=business, warehouse=warehouse)
        wh_row = PickupLocation.objects.get(business=business, warehouse=warehouse)
        self.assertTrue(wh_row.is_fulfilment_center)

        self.toggle_off(business)
        wh_row.refresh_from_db()
        self.assertTrue(wh_row.is_fulfilment_center,
                        'a real warehouse address stays flagged — the goods are there')
        self.assertEqual(wh_row.pickup_status, 'inactive',
                         'but it stops being offered for collection')

    def test_status_is_downgraded_so_reports_stop_counting_the_client(self):
        business = self.make_business(3, fulfillment_service_status='active')
        self.toggle_off(business)
        business.refresh_from_db()
        self.assertFalse(business.fulfillment_service_enabled)
        self.assertEqual(business.fulfillment_service_status, 'none')

    def test_a_client_never_onboarded_keeps_its_status(self):
        business = self.make_business(4, fulfillment_service_status='requested')
        self.toggle_off(business)
        business.refresh_from_db()
        self.assertFalse(business.fulfillment_service_enabled)
        self.assertEqual(business.fulfillment_service_status, 'requested')

    def test_pickup_works_again_after_the_toggle(self):
        """End to end: the Polyform shape. Toggling off used to leave the only
        address FC-flagged and inactive, so the gate refused forever."""
        from delivery.services.pickup import create_pickup_task_if_needed
        from delivery.models import PickupTask

        Warehouse.objects.create(
            name='EzzyDelivery FC- Hub', is_default=True,
            latitude=Decimal('25.28'), longitude=Decimal('51.53'))
        business = self.make_business(5, pickup_task_enabled=True)
        shop = PickupLocation.objects.create(
            business=business, pickup_location_title='POLY SHOP',
            locality='Zone 66', pickup_status='active', is_fulfilment_center=True)

        self.toggle_off(business)
        shop.refresh_from_db()

        order = Order.objects.create(
            business=business, client_order_code='FT005',
            customer_name='Cust', customer_phone='55555555',
            customer_address='Somewhere', dl_zone=55, pickup_location=shop)
        PickupTask.objects.filter(order=order).delete()   # isolate the gate itself

        pickup, reason = create_pickup_task_if_needed(order, source='test')
        self.assertEqual(reason, 'created', f'gate refused with {reason}')
        self.assertIsNotNone(pickup)
