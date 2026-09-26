# Purpose: Tests for task_origin / task_destination — the two ends of a delivery leg.
# Used by: manage.py test delivery.tests_route
# Notes: A hub leg collects at the dock, NOT at the merchant, and its pin is what the
#        driver PWA navigates to — a wrong one sends the parcel to the wrong street.

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from business import models as business_models
from core import models as core_models
from delivery import models as delivery_models
from delivery.selectors import task_destination, task_origin
from orders import models as orders_models
from warehouse import models as warehouse_models

User = get_user_model()

_SEQ = [7700]


def _fixtures():
    _SEQ[0] += 1
    idx = _SEQ[0]

    biz_user = User.objects.create_user(username=f'rt_biz_{idx}', password='x')
    biz_profile = core_models.Profile.objects.create(
        user=biz_user, first_name='R', last_name='T', phone=93000000 + idx)
    business = business_models.Business.objects.create(
        business_id=idx, user=biz_user, profile=biz_profile,
        business_name=f'Route Biz {idx}', business_code=f'RT{idx}',
        business_status='active')
    pickup = business_models.PickupLocation.objects.create(
        business=business, pickup_location_title='Office', locality='Doha',
        pickup_lat=Decimal('25.246386'), pickup_lon=Decimal('51.465587'))
    order = orders_models.Order.objects.create(
        business=business, client_order_code=f'RT-ORD-{idx}',
        customer_name='C', customer_phone='1', customer_address='Z',
        cod_amount=Decimal('0.00'), dl_amount=Decimal('25.00'),
        pickup_location=pickup, order_status='pending',
        latitude=Decimal('25.677496'), longitude=Decimal('51.482815'))
    return business, order, pickup


def _hub(latitude, longitude, warehouse_latitude=None, warehouse_longitude=None):
    _SEQ[0] += 1
    idx = _SEQ[0]
    warehouse = warehouse_models.Warehouse.objects.create(
        name=f'FC {idx}', code=f'FC-{idx}',
        latitude=warehouse_latitude, longitude=warehouse_longitude)
    return warehouse_models.WarehouseLocation.objects.create(
        warehouse=warehouse, name='Main Dock', code=f'FC-{idx}-DOCK',
        latitude=latitude, longitude=longitude)


def _task(order, business, leg='single', hub=None, pickup=None):
    return delivery_models.DeliveryTask.objects.create(
        dl_task_number=f'RT-T-{order.id}-{leg}', order=order, business=business,
        dl_task_status='pending', dl_price=Decimal('25.00'), task_leg=leg,
        dl_task_date=timezone.now().date(), hub_warehouse=hub,
        pickup_location=pickup)


class TaskOriginTests(TestCase):
    def test_a_merchant_leg_collects_at_the_pickup_location(self):
        business, order, pickup = _fixtures()
        origin = task_origin(_task(order, business, pickup=pickup))
        self.assertEqual(origin.label, 'Office')
        self.assertEqual(origin.latitude, Decimal('25.246386'))
        self.assertEqual(origin.longitude, Decimal('51.465587'))

    def test_a_hub_leg_collects_at_the_dock_not_the_merchant(self):
        business, order, _ = _fixtures()
        hub = _hub(Decimal('25.275091'), Decimal('51.486559'))
        origin = task_origin(_task(order, business, 'return_to_client', hub=hub))
        self.assertIn('Main Dock', origin.label)
        self.assertEqual(origin.latitude, Decimal('25.275091'))
        self.assertEqual(origin.longitude, Decimal('51.486559'))

    def test_a_dock_without_a_pin_falls_back_to_its_site(self):
        business, order, _ = _fixtures()
        hub = _hub(None, None,
                   warehouse_latitude=Decimal('25.275091'),
                   warehouse_longitude=Decimal('51.486559'))
        origin = task_origin(_task(order, business, 'return_to_client', hub=hub))
        self.assertEqual(origin.latitude, Decimal('25.275091'))
        self.assertEqual(origin.longitude, Decimal('51.486559'))

    def test_a_dock_and_site_with_no_pin_at_all_reports_nothing(self):
        business, order, _ = _fixtures()
        hub = _hub(None, None)
        origin = task_origin(_task(order, business, 'return_to_client', hub=hub))
        self.assertIsNone(origin.latitude)
        self.assertIsNone(origin.longitude)


class TaskDestinationTests(TestCase):
    def test_a_return_leg_does_not_drop_at_the_customer(self):
        business, order, _ = _fixtures()
        hub = _hub(Decimal('25.275091'), Decimal('51.486559'))
        task = _task(order, business, 'return_to_client', hub=hub)
        self.assertFalse(task_destination(task).is_customer)

    def test_a_normal_leg_drops_at_the_customer_pin(self):
        business, order, pickup = _fixtures()
        destination = task_destination(_task(order, business, pickup=pickup))
        self.assertTrue(destination.is_customer)
        self.assertEqual(destination.latitude, Decimal('25.677496'))
