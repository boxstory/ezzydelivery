# Purpose: Tests for the return-pickup order — the collection trip a return request asks for.
# Used by: manage.py test orders.tests_return_pickup
# Notes: This is the only order that runs backwards. Its customer fields are the ORIGIN and
#        pickup_location is the DESTINATION, so the route assertions here are the real contract.

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from business import models as business_models
from core import models as core_models
from delivery import models as delivery_models
from delivery.earnings import driver_fee, fee_expr
from delivery.selectors import task_destination, task_origin
from delivery.services.pickup import create_pickup_task_if_needed
from orders import models as orders_models
from orders.services import (
    can_schedule_return_pickup, create_return_pickup_order, create_return_request,
)

User = get_user_model()

_SEQ = [8800]


def _fixtures(pickup_task_enabled=False):
    _SEQ[0] += 1
    idx = _SEQ[0]

    biz_user = User.objects.create_user(username=f'rp_biz_{idx}', password='x')
    biz_profile = core_models.Profile.objects.create(
        user=biz_user, first_name='R', last_name='P', phone=94000000 + idx)
    business = business_models.Business.objects.create(
        business_id=idx, user=biz_user, profile=biz_profile,
        business_name=f'RP Biz {idx}', business_code=f'RP{idx}',
        business_status='active', pickup_task_enabled=pickup_task_enabled)
    pickup = business_models.PickupLocation.objects.create(
        business=business, pickup_location_title='Seller Counter', locality='Al Sadd',
        pickup_zone_no=38, pickup_street_no=850, pickup_building_no=12,
        pickup_lat=Decimal('25.280000'), pickup_lon=Decimal('51.500000'))
    order = orders_models.Order.objects.create(
        business=business, client_order_code=f'RP-ORD-{idx}',
        customer_name='Buyer', customer_phone='97455500000',
        customer_address='Flat 3', dl_zone=55, dl_street=204, dl_building=53,
        latitude=Decimal('25.246386'), longitude=Decimal('51.465587'),
        cod_amount=Decimal('150.00'), dl_amount=Decimal('25.00'),
        pickup_location=pickup, order_status='delivered')
    item = orders_models.OrderItem.objects.create(
        order=order, quantity=2, unit_price=Decimal('75.00'))
    staff = User.objects.create_user(
        username=f'rp_staff_{idx}', password='x', is_staff=True)
    return business, order, item, pickup, staff


def _claim(order, items=None, status='approved'):
    return create_return_request(order, reason='damaged', items=items, status=status)


class CanScheduleTests(TestCase):
    def test_an_approved_claim_can_be_collected(self):
        _, order, _, _, _ = _fixtures()
        ok, why = can_schedule_return_pickup(_claim(order))
        self.assertTrue(ok, why)

    def test_a_finished_claim_cannot(self):
        _, order, _, _, _ = _fixtures()
        ok, why = can_schedule_return_pickup(_claim(order, status='refunded'))
        self.assertFalse(ok)
        self.assertIn('nothing left to collect', why)

    def test_a_claim_with_no_seller_address_cannot(self):
        _, order, _, _, _ = _fixtures()
        order.pickup_location = None
        order.save(update_fields=['pickup_location'])
        ok, why = can_schedule_return_pickup(_claim(order))
        self.assertFalse(ok)
        self.assertIn('nowhere to take the goods', why)

    def test_a_claim_that_already_has_a_collection_cannot(self):
        _, order, _, _, staff = _fixtures()
        ret = _claim(order)
        create_return_pickup_order(ret, user=staff, publish=False)
        ret.refresh_from_db()
        ok, why = can_schedule_return_pickup(ret)
        self.assertFalse(ok)
        self.assertIn('already raised', why)


class CreateReturnPickupTests(TestCase):
    def test_it_raises_an_order_linked_to_the_claim(self):
        _, order, _, _, staff = _fixtures()
        ret = _claim(order)
        new = create_return_pickup_order(ret, user=staff, publish=False)
        ret.refresh_from_db()
        self.assertEqual(ret.pickup_order_id, new.id)
        self.assertEqual(ret.status, 'pickup_scheduled')
        self.assertEqual(new.order_type, 'return_pickup')
        self.assertEqual(new.business_id, order.business_id)
        self.assertTrue(new.client_order_code.endswith('-RP1'))

    def test_it_copies_the_returned_lines_only(self):
        _, order, item, _, staff = _fixtures()
        ret = _claim(order, items=[(item, 1)])
        new = create_return_pickup_order(ret, user=staff, publish=False)
        lines = list(new.order_items.all())
        self.assertEqual(len(lines), 1)
        self.assertEqual(lines[0].quantity, 1)

    def test_it_never_carries_cod(self):
        _, order, _, _, staff = _fixtures()
        new = create_return_pickup_order(_claim(order), user=staff, publish=False)
        self.assertEqual(new.cod_amount, Decimal('0.00'))

    def test_the_charge_defaults_to_the_outbound_one_and_can_be_overridden(self):
        _, order, _, _, staff = _fixtures()
        self.assertEqual(
            create_return_pickup_order(_claim(order), user=staff, publish=False).dl_amount,
            Decimal('25.00'))
        _, order2, _, _, _ = _fixtures()
        self.assertEqual(
            create_return_pickup_order(_claim(order2), charge=Decimal('40.00'),
                                       user=staff, publish=False).dl_amount,
            Decimal('40.00'))

    def test_a_negative_charge_is_refused(self):
        _, order, _, _, staff = _fixtures()
        with self.assertRaises(ValidationError):
            create_return_pickup_order(_claim(order), charge=Decimal('-5.00'),
                                       user=staff, publish=False)

    def test_it_comments_on_both_orders(self):
        _, order, _, _, staff = _fixtures()
        new = create_return_pickup_order(_claim(order), user=staff, publish=False)
        self.assertTrue(order.order_comments.filter(body__contains=new.order_number).exists())
        self.assertTrue(new.order_comments.filter(body__contains=order.order_number).exists())

    def test_publishing_puts_the_task_in_the_pool(self):
        _, order, _, _, staff = _fixtures()
        new = create_return_pickup_order(_claim(order), user=staff, publish=True)
        task = new.delivery_task.get()
        self.assertEqual(task.task_leg, 'collect_from_customer')
        self.assertTrue(task.dl_task_publish)
        self.assertEqual(task.dl_task_status, 'pending')

    def test_no_first_mile_pickup_is_raised_at_the_seller(self):
        _, order, _, _, staff = _fixtures(pickup_task_enabled=True)
        new = create_return_pickup_order(_claim(order), user=staff, publish=True)
        task, reason = create_pickup_task_if_needed(new)
        self.assertIsNone(task)
        self.assertEqual(reason, 'return_pickup_order')
        self.assertFalse(delivery_models.PickupTask.objects.filter(order=new).exists())


class ReturnPickupRouteTests(TestCase):
    def _task(self):
        _, order, _, pickup, staff = _fixtures()
        new = create_return_pickup_order(_claim(order), user=staff, publish=True)
        return new.delivery_task.get(), order, pickup

    def test_the_driver_collects_at_the_customer(self):
        task, order, _ = self._task()
        origin = task_origin(task)
        self.assertEqual(origin.label, order.customer_name)
        self.assertEqual(origin.latitude, order.latitude)
        self.assertEqual(origin.longitude, order.longitude)

    def test_the_driver_drops_at_the_seller(self):
        task, _, pickup = self._task()
        destination = task_destination(task)
        self.assertFalse(destination.is_customer)
        self.assertEqual(destination.zone, pickup.pickup_zone_no)
        self.assertEqual(destination.street, pickup.pickup_street_no)
        self.assertEqual(destination.building, pickup.pickup_building_no)
        self.assertEqual(destination.latitude, pickup.pickup_lat)

    def test_the_buyers_pin_is_never_the_drop_off(self):
        task, order, _ = self._task()
        self.assertNotEqual(task_destination(task).latitude, order.latitude)


class ReturnPickupCardTests(TestCase):
    """What the driver's phone actually prints. The two data sources on a card
    disagreed once before (see the return leg), so assert the rendered output."""

    def test_the_card_sends_the_driver_to_the_customer_and_back_to_the_seller(self):
        from django.template.loader import render_to_string

        from delivery.selectors import task_address

        _, order, _, pickup, staff = _fixtures()
        task = create_return_pickup_order(
            _claim(order), user=staff, publish=True).delivery_task.get()
        html = render_to_string('fleet/parts/_task_data_attrs.html',
                                {'card': task, 'addr': task_address(task)})

        # Both rows carry the column's full scale once they come back from the
        # database; the in-memory Decimals do not.
        order.refresh_from_db()
        pickup.refresh_from_db()

        self.assertIn(f'data-pickup="{order.customer_name}"', html)
        self.assertIn(f'data-pickup-lat="{order.latitude}"', html)
        self.assertIn(f'data-zone="{pickup.pickup_zone_no}"', html)
        self.assertIn(f'data-lat="{pickup.pickup_lat}"', html)
        # The buyer's pin grade describes the wrong end of this trip.
        self.assertIn('data-coords-accuracy=""', html)


class ReturnPickupFeeTests(TestCase):
    def _card(self, normal='12.00'):
        from fleet import models as fleet_models
        return fleet_models.DeliveryPayRate.objects.create(
            normal_fee=Decimal(normal), hub_fee=Decimal('10.00'),
            pick_and_drop_percent=Decimal('80.00'), exchange_fee=Decimal('25.00'),
            effective_from=timezone.now().date() - timezone.timedelta(days=30))

    def test_a_collection_pays_a_normal_drop(self):
        self._card(normal='12.00')
        _, order, _, _, staff = _fixtures()
        task = create_return_pickup_order(
            _claim(order), user=staff, publish=True).delivery_task.get()
        self.assertEqual(driver_fee(task), Decimal('12.00'))

    def test_a_zero_charge_collection_still_pays_the_driver(self):
        self._card(normal='12.00')
        _, order, _, _, staff = _fixtures()
        task = create_return_pickup_order(
            _claim(order), charge=Decimal('0.00'), user=staff,
            publish=True).delivery_task.get()
        self.assertEqual(driver_fee(task), Decimal('12.00'))

    def test_the_queryset_twin_prices_it_the_same(self):
        self._card(normal='12.00')
        _, order, _, _, staff = _fixtures()
        task = create_return_pickup_order(
            _claim(order), user=staff, publish=True).delivery_task.get()
        priced = delivery_models.DeliveryTask.objects.filter(pk=task.pk).annotate(
            fee=fee_expr()).first()
        self.assertEqual(priced.fee, driver_fee(task))


class ScheduleEndpointTests(TestCase):
    """The staff console button, end to end — it is the only way this order is born."""

    def _staff(self, username):
        from core.departments import ASSIGNABLE_DEPARTMENTS, DEPARTMENT_FIELDS
        user = User.objects.create_user(
            username=username, password='Staff@123', is_staff=True)
        core_models.Profile.objects.create(
            user=user, first_name='S', last_name='T', phone=11111111,
            is_staff=True,
            **{DEPARTMENT_FIELDS[code]: True for code in ASSIGNABLE_DEPARTMENTS})
        self.client.login(username=username, password='Staff@123')
        return user

    def _url(self, ret):
        from django.urls import reverse
        return reverse('workforce:returns_request_schedule_pickup', args=[ret.id])

    def test_it_raises_the_collection_and_reports_the_order(self):
        self._staff('rp_ep_1')
        _, order, _, _, _ = _fixtures()
        ret = _claim(order)
        resp = self.client.post(self._url(ret), data='{"charge": "30.00"}',
                                content_type='application/json')
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(body['success'])
        ret.refresh_from_db()
        self.assertEqual(ret.status, 'pickup_scheduled')
        self.assertEqual(ret.pickup_order.order_number, body['order_number'])
        self.assertEqual(ret.pickup_order.dl_amount, Decimal('30.00'))
        self.assertTrue(ret.pickup_order.delivery_task.get().dl_task_publish)

    def test_a_second_press_is_refused(self):
        self._staff('rp_ep_2')
        _, order, _, _, _ = _fixtures()
        ret = _claim(order)
        self.client.post(self._url(ret), data='{}', content_type='application/json')
        resp = self.client.post(self._url(ret), data='{}', content_type='application/json')
        self.assertEqual(resp.status_code, 400)
        self.assertIn('already raised', resp.json()['error'])
        self.assertEqual(
            orders_models.Order.objects.filter(order_type='return_pickup').count(), 1)

    def test_a_bad_charge_is_refused_before_anything_is_written(self):
        self._staff('rp_ep_3')
        _, order, _, _, _ = _fixtures()
        ret = _claim(order)
        resp = self.client.post(self._url(ret), data='{"charge": "soon"}',
                                content_type='application/json')
        self.assertEqual(resp.status_code, 400)
        ret.refresh_from_db()
        self.assertIsNone(ret.pickup_order_id)

    def test_a_seller_cannot_claim_a_collection_is_scheduled(self):
        business, order, _, _, _ = _fixtures()
        ret = _claim(order)
        from django.urls import reverse
        url = reverse('business:return_update_status', args=[ret.id])
        self.assertTrue(
            self.client.login(username=business.user.username, password='x'))

        self.client.post(url, {'status': 'pickup_scheduled'})
        ret.refresh_from_db()
        self.assertEqual(ret.status, 'approved')
        self.assertIsNone(ret.pickup_order_id)

        # ...but the statuses that ARE theirs still work in the same session, so
        # the assertion above is the rule biting and not a failed login.
        self.client.post(url, {'status': 'received'})
        ret.refresh_from_db()
        self.assertEqual(ret.status, 'received')


class ReturnPickupLifecycleTests(TestCase):
    """The claim has to follow the van. Found by walking the real driver
    endpoints: before this, a collection could be delivered and the claim would
    still read 'Pickup Scheduled' forever."""

    def _collection(self, status='approved'):
        _, order, _, _, staff = _fixtures()
        ret = _claim(order, status=status)
        new = create_return_pickup_order(ret, user=staff, publish=True)
        return ret, new, new.delivery_task.get()

    def _move(self, task, status):
        task.dl_task_status = status
        task._status_actor = 'staff'
        task.save()
        task.refresh_from_db()

    def test_collecting_the_goods_moves_the_claim(self):
        ret, _, task = self._collection()
        self._move(task, 'picked_up')
        ret.refresh_from_db()
        self.assertEqual(ret.status, 'picked_up')

    def test_reaching_the_seller_marks_the_claim_received(self):
        ret, _, task = self._collection()
        self._move(task, 'out_for_delivery')
        self._move(task, 'delivered')
        ret.refresh_from_db()
        self.assertEqual(ret.status, 'received')

    def test_the_claim_is_never_dragged_backwards(self):
        ret, _, task = self._collection()
        self._move(task, 'out_for_delivery')
        self._move(task, 'delivered')
        self._move(task, 'picked_up')
        ret.refresh_from_db()
        self.assertEqual(ret.status, 'received')

    def test_a_decision_made_by_hand_outranks_the_van(self):
        ret, _, task = self._collection()
        ret.status = 'closed'
        ret.save(update_fields=['status'])
        self._move(task, 'delivered')
        ret.refresh_from_db()
        self.assertEqual(ret.status, 'closed')


class ReturnPickupFailureTests(TestCase):
    """A collection that comes back is not a new return — it is the same goods,
    still at the customer's. Without the guard, closing one as returned_to_shipper
    raised a claim against the collection order, which staff could then schedule
    another collection for, and so on."""

    def _collection(self):
        _, order, _, _, staff = _fixtures()
        ret = _claim(order)
        new = create_return_pickup_order(ret, user=staff, publish=True)
        return ret, new, new.delivery_task.get()

    def test_a_returned_collection_raises_no_second_claim(self):
        from delivery.services.returns import open_return_for_task

        ret, _, task = self._collection()
        before = orders_models.ReturnRequest.objects.count()

        task.dl_task_status = 'returned_to_shipper'
        task._status_actor = 'staff'
        task.save()
        outcome = open_return_for_task(task, reason='undelivered')

        self.assertEqual(orders_models.ReturnRequest.objects.count(), before)
        self.assertIsNone(outcome.custody)
        self.assertIn('not a new return', ' '.join(outcome.warnings))

    def test_a_cancelled_collection_can_be_scheduled_again(self):
        _, order, _, _, staff = _fixtures()
        ret = _claim(order)
        first = create_return_pickup_order(ret, user=staff, publish=True)

        ret.refresh_from_db()
        self.assertFalse(can_schedule_return_pickup(ret)[0])

        first.order_status = 'cancelled'
        first.save()
        ret.refresh_from_db()
        self.assertTrue(can_schedule_return_pickup(ret)[0])

        second = create_return_pickup_order(ret, user=staff, publish=True)
        self.assertNotEqual(second.id, first.id)
        # The abandoned trip keeps its own code — reusing -RP1 would collide and
        # fall back to an opaque one the seller cannot place.
        self.assertTrue(first.client_order_code.endswith('-RP1'))
        self.assertTrue(second.client_order_code.endswith('-RP2'))
        ret.refresh_from_db()
        self.assertEqual(ret.pickup_order_id, second.id)


class ReturnPickupSilenceTests(TestCase):
    """Every customer-facing body is worded as an outbound delivery. On a
    collection the customer is handing goods over, so they must not fire."""

    def test_no_customer_flow_runs_when_a_collection_is_delivered(self):
        from unittest.mock import patch

        _, order, _, _, staff = _fixtures()
        task = create_return_pickup_order(
            _claim(order), user=staff, publish=True).delivery_task.get()

        with patch('core.auto_flow_executor.execute_flows_for_trigger') as flows:
            task.dl_task_status = 'out_for_delivery'
            task._status_actor = 'staff'
            task.save()
            task.dl_task_status = 'delivered'
            task._status_actor = 'staff'
            task.save()

        fired = [c.args[0] for c in flows.call_args_list if c.args]
        self.assertFalse([k for k in fired if k.startswith('wa_')], fired)

    def test_control_an_ordinary_delivery_still_messages_the_customer(self):
        """Without this the test above would pass on a broken signal that never
        fires for anyone."""
        from unittest.mock import patch

        business, order, _, _, _ = _fixtures()
        task = delivery_models.DeliveryTask.objects.create(
            dl_task_number=f'CTRL-{order.id}', order=order, business=business,
            dl_task_status='out_for_delivery', dl_task_publish=True,
            dl_price=Decimal('25.00'), task_leg='single',
            dl_task_date=timezone.now().date())

        with patch('core.auto_flow_executor.execute_flows_for_trigger') as flows:
            task.dl_task_status = 'delivered'
            task._status_actor = 'staff'
            task.save()

        fired = [c.args[0] for c in flows.call_args_list if c.args]
        self.assertIn('wa_delivered', fired)


class ReturnAndReplacementMergeTests(TestCase):
    """Request Return, Send Replacement (collect-back) and the collection were
    three tracks that could not see each other: three clicks meant three claims
    and three collections, and a collect-back replacement sent a second driver
    for goods a collection was already coming for."""

    def _seller(self, business):
        self.assertTrue(
            self.client.login(username=business.user.username, password='x'))

    def test_a_second_claim_is_refused_while_one_is_open(self):
        from django.urls import reverse
        from orders.services import open_return_for_order

        business, order, _, _, _ = _fixtures()
        first = _claim(order, status='pending')
        self._seller(business)

        resp = self.client.post(
            reverse('business:return_create', args=[order.id]),
            {'reason': 'damaged', f'item_{order.order_items.first().id}': 'on',
             f'qty_{order.order_items.first().id}': '1'})

        self.assertEqual(order.return_requests.count(), 1)
        self.assertEqual(resp.status_code, 302)
        self.assertIn(str(first.id), resp.url)
        self.assertEqual(open_return_for_order(order).id, first.id)

    def test_a_closed_claim_frees_the_order_for_a_new_one(self):
        from django.urls import reverse

        business, order, item, _, _ = _fixtures()
        done = _claim(order)
        done.status = 'closed'
        done.save(update_fields=['status'])
        self._seller(business)

        self.client.post(
            reverse('business:return_create', args=[order.id]),
            {'reason': 'damaged', f'item_{item.id}': 'on', f'qty_{item.id}': '1'})
        self.assertEqual(order.return_requests.count(), 2)

    def test_a_sibling_claims_collection_blocks_a_second_one(self):
        _, order, _, _, staff = _fixtures()
        first = _claim(order)
        create_return_pickup_order(first, user=staff, publish=True)

        second = _claim(order)
        ok, why = can_schedule_return_pickup(second)
        self.assertFalse(ok)
        self.assertIn('already raised', why)

    def test_a_collect_back_replacement_is_reported_not_blocked(self):
        from orders.services import create_replacement_order, jobs_collecting_from

        _, order, _, _, staff = _fixtures()
        repl = create_replacement_order(
            order, reason='damaged', collect_back=True, user=staff, publish=True)

        kinds = {job['kind'] for job in jobs_collecting_from(order)}
        self.assertIn('exchange', kinds)
        self.assertIn(repl.order_number,
                      ' '.join(j['label'] for j in jobs_collecting_from(order)))

        # Warned about, never refused — which trip keeps the parcel is an ops call.
        ret = _claim(order)
        self.assertTrue(can_schedule_return_pickup(ret)[0])

    def test_a_cancelled_replacement_stops_being_reported(self):
        from orders.services import create_replacement_order, jobs_collecting_from

        _, order, _, _, staff = _fixtures()
        repl = create_replacement_order(
            order, reason='damaged', collect_back=True, user=staff, publish=False)
        self.assertTrue(jobs_collecting_from(order))

        repl.order_status = 'cancelled'
        repl.save()
        self.assertFalse(jobs_collecting_from(order))

    def test_the_order_page_shows_the_claim_and_its_collection(self):
        from django.urls import reverse

        business, order, _, _, staff = _fixtures()
        ret = _claim(order)
        collection = create_return_pickup_order(ret, user=staff, publish=True)
        self._seller(business)

        page = self.client.get(reverse('orders:order_details', args=[order.id]))
        body = page.content.decode()
        self.assertEqual(page.status_code, 200)
        self.assertIn(f'RET-{ret.return_number}', body)
        self.assertIn(collection.order_number, body)
        # The button points at the open claim rather than opening a second one.
        self.assertIn(reverse('business:return_detail', args=[ret.id]), body)
        self.assertNotIn(reverse('business:return_create', args=[order.id]), body)

    def test_the_replacement_modal_warns_when_a_collection_is_coming(self):
        from django.urls import reverse

        business, order, _, _, staff = _fixtures()
        create_return_pickup_order(_claim(order), user=staff, publish=True)
        self._seller(business)

        body = self.client.get(
            reverse('orders:order_details', args=[order.id])).content.decode()
        self.assertIn('A driver is already coming for these goods', body)

    def test_no_warning_when_nothing_is_collecting(self):
        from django.urls import reverse

        business, order, _, _, _ = _fixtures()
        self._seller(business)
        body = self.client.get(
            reverse('orders:order_details', args=[order.id])).content.decode()
        self.assertNotIn('A driver is already coming for these goods', body)
