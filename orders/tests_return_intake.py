# Purpose: Tests for the two return-intake forms — the staff desk and the seller console — that raise a claim and the driver's trip in one submit.
# Used by: manage.py test orders.tests_return_intake
# Notes: Both pages post into orders.return_intake, so the contract worth pinning is that they agree on everything
#        except who may raise what and whether the collection is published. A seller's must never reach the pool.

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from business import models as business_models
from core import models as core_models
from orders import models as orders_models
from product import models as product_models

User = get_user_model()

_SEQ = [9900]


def _fixtures():
    """A client with a counter, one delivered order of two units, a seller
    login and a staff login."""
    _SEQ[0] += 1
    idx = _SEQ[0]

    biz_user = User.objects.create_user(username=f'ri_biz_{idx}', password='x')
    biz_profile = core_models.Profile.objects.create(
        user=biz_user, first_name='R', last_name='I', phone=96000000 + idx)
    business = business_models.Business.objects.create(
        business_id=idx, user=biz_user, profile=biz_profile,
        business_name=f'RI Biz {idx}', business_code=f'RI{idx}',
        business_status='active')
    pickup = business_models.PickupLocation.objects.create(
        business=business, pickup_location_title='Client Counter',
        locality='Al Sadd', pickup_zone_no=38, pickup_street_no=850,
        pickup_building_no=12, pickup_lat=Decimal('25.280000'),
        pickup_lon=Decimal('51.500000'))
    order = orders_models.Order.objects.create(
        business=business, client_order_code=f'RI-ORD-{idx}',
        customer_name='Buyer', customer_phone='97455500000',
        customer_address='Flat 3', dl_zone=55, dl_street=204, dl_building=53,
        latitude=Decimal('25.246386'), longitude=Decimal('51.465587'),
        cod_amount=Decimal('150.00'), dl_amount=Decimal('25.00'),
        pickup_location=pickup, order_status='delivered')
    item = orders_models.OrderItem.objects.create(
        order=order, quantity=2, unit_price=Decimal('75.00'))
    return business, order, item, pickup, biz_user


def _product(business, name='Lamp'):
    _SEQ[0] += 1
    return product_models.Product.objects.create(
        business=business, brand_name='RI', item_name=name,
        item_sku=f'RI-SKU-{_SEQ[0]}', item_price=40)


def _staff(case, idx_seed='ri'):
    from core.departments import ASSIGNABLE_DEPARTMENTS, DEPARTMENT_FIELDS
    _SEQ[0] += 1
    user = User.objects.create_user(
        username=f'{idx_seed}_staff_{_SEQ[0]}', password='Staff@123', is_staff=True)
    core_models.Profile.objects.create(
        user=user, first_name='S', last_name='T', phone=22200000 + _SEQ[0],
        is_staff=True,
        **{DEPARTMENT_FIELDS[code]: True for code in ASSIGNABLE_DEPARTMENTS})
    case.client.login(username=user.username, password='Staff@123')
    return user


class StaffOrderModeTests(TestCase):
    """The staff desk, raising a return against an order we carried."""

    def _url(self):
        return reverse('workforce:returns_task_create')

    def test_the_page_opens_in_both_modes(self):
        _fixtures()
        _staff(self)
        self.assertEqual(self.client.get(self._url()).status_code, 200)
        self.assertEqual(
            self.client.get(self._url(), {'mode': 'standalone'}).status_code, 200)

    def test_looking_up_an_order_shows_who_to_collect_from(self):
        _, order, _, _, _ = _fixtures()
        _staff(self)
        resp = self.client.get(self._url(), {'mode': 'order',
                                             'business': order.business.business_id,
                                             'order_ref': order.order_number})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, order.customer_name)
        self.assertContains(resp, 'Client Counter')

    def test_it_raises_the_claim_and_the_collection_in_one_submit(self):
        business, order, _, pickup, _ = _fixtures()
        _staff(self)
        resp = self.client.post(self._url(), {
            'mode': 'order', 'order_ref': order.order_number,
            'business': business.business_id,
            'reason': 'damaged', 'reason_notes': 'Crushed box',
            'schedule_pickup': '1',
        })
        self.assertEqual(resp.status_code, 302)

        ret = orders_models.ReturnRequest.objects.get(order=order)
        self.assertEqual(ret.status, 'pickup_scheduled')
        collection = ret.pickup_order
        self.assertIsNotNone(collection)
        self.assertEqual(collection.order_type, 'return_pickup')
        # Staff pressing the button IS the approval, so the trip is in the pool.
        self.assertEqual(collection.order_status, 'publish')
        # The trip runs backwards: the customer is where the driver goes.
        self.assertEqual(collection.customer_phone, order.customer_phone)
        self.assertEqual(collection.pickup_location, pickup)
        self.assertEqual(collection.business, business)

    def test_the_claim_survives_without_a_trip_when_not_asked_for(self):
        _, order, _, _, _ = _fixtures()
        _staff(self)
        self.client.post(self._url(), {
            'mode': 'order', 'order_ref': order.order_number,
            'business': order.business.business_id, 'reason': 'damaged',
        })
        ret = orders_models.ReturnRequest.objects.get(order=order)
        self.assertEqual(ret.status, 'approved')
        self.assertIsNone(ret.pickup_order_id)

    def test_only_the_ticked_lines_come_back(self):
        _, order, item, _, _ = _fixtures()
        _staff(self)
        self.client.post(self._url(), {
            'mode': 'order', 'order_ref': order.order_number,
            'business': order.business.business_id,
            'reason': 'damaged', 'items_scoped': '1',
            f'item_{item.id}': '1', f'qty_{item.id}': '1',
        })
        ret = orders_models.ReturnRequest.objects.get(order=order)
        line = ret.return_items.get()
        self.assertEqual(line.quantity_returned, 1)

    def test_a_second_submit_adds_to_the_open_claim_rather_than_duplicating(self):
        _, order, _, _, _ = _fixtures()
        _staff(self)
        payload = {'mode': 'order', 'order_ref': order.order_number,
                   'business': order.business.business_id, 'reason': 'damaged'}
        self.client.post(self._url(), payload)
        self.client.post(self._url(), payload)
        # Two claims for one parcel is two drivers sent for it.
        self.assertEqual(
            orders_models.ReturnRequest.objects.filter(order=order).count(), 1)

    def test_an_unknown_order_writes_nothing(self):
        _fixtures()
        _staff(self)
        business, _, _, _, _ = _fixtures()
        resp = self.client.post(self._url(), {
            'mode': 'order', 'order_ref': 'NOPE-404',
            'business': business.business_id, 'reason': 'damaged'})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(orders_models.ReturnRequest.objects.count(), 0)

    def test_a_missing_reason_writes_nothing(self):
        _, order, _, _, _ = _fixtures()
        _staff(self)
        resp = self.client.post(self._url(), {
            'mode': 'order', 'order_ref': order.order_number,
            'business': order.business.business_id, 'reason': ''})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(orders_models.ReturnRequest.objects.count(), 0)


class StaffStandaloneModeTests(TestCase):
    """The same page with no order behind it — goods we never carried."""

    def test_it_raises_the_claim_and_the_collection(self):
        business, _, _, pickup, _ = _fixtures()
        _staff(self)
        resp = self.client.post(reverse('workforce:returns_task_create'), {
            'mode': 'standalone',
            'business': business.business_id,
            'pickup_location': pickup.id,
            'reason': 'damaged',
            'customer_name': 'Buyer',
            'customer_phone': '97455500001',
            'customer_address': 'Flat 9',
            'dl_zone': '55', 'dl_street': '204', 'dl_building': '53',
            'collection_charge': '18.00',
            'schedule_pickup': '1',
        })
        self.assertEqual(resp.status_code, 302)
        ret = orders_models.ReturnRequest.objects.get()
        self.assertTrue(ret.is_standalone)
        self.assertIsNotNone(ret.pickup_order)
        self.assertEqual(ret.pickup_order.dl_amount, Decimal('18.00'))

    def test_the_old_url_still_opens_the_standalone_form_only(self):
        _fixtures()
        _staff(self)
        resp = self.client.get(reverse('workforce:returns_request_create'),
                               {'mode': 'order'})
        self.assertEqual(resp.status_code, 200)
        # Pinned: the mode switch is not offered and the order lookup is absent.
        self.assertNotContains(resp, 'returns_intake_input_orderref')

    def test_a_seller_cannot_reach_the_staff_page(self):
        _, _, _, _, biz_user = _fixtures()
        self.client.login(username=biz_user.username, password='x')
        self.assertNotEqual(
            self.client.get(reverse('workforce:returns_task_create')).status_code,
            200)


class SellerConsoleTests(TestCase):
    """The client's own copy of the form."""

    def _login(self, biz_user):
        self.client.login(username=biz_user.username, password='x')

    def _url(self):
        return reverse('orders:add_return')

    def test_the_page_opens(self):
        _, _, _, _, biz_user = _fixtures()
        self._login(biz_user)
        self.assertEqual(self.client.get(self._url()).status_code, 200)

    def test_a_seller_books_a_collection_that_waits_for_review(self):
        _, order, _, _, biz_user = _fixtures()
        self._login(biz_user)
        resp = self.client.post(self._url(), {
            'mode': 'order', 'order_ref': order.order_number,
            'reason': 'damaged', 'schedule_pickup': '1',
        })
        self.assertEqual(resp.status_code, 302)
        ret = orders_models.ReturnRequest.objects.get(order=order)
        collection = ret.pickup_order
        self.assertIsNotNone(collection)
        # A seller asking for a driver is a request, not the approval.
        self.assertEqual(collection.order_status, 'to_review')
        self.assertFalse(
            collection.delivery_task.filter(dl_task_publish=True).exists())

    def test_a_seller_cannot_reach_another_clients_order(self):
        _, _, _, _, biz_user = _fixtures()
        _, other_order, _, _, _ = _fixtures()
        self._login(biz_user)
        resp = self.client.post(self._url(), {
            'mode': 'order', 'order_ref': other_order.order_number,
            'reason': 'damaged', 'schedule_pickup': '1',
        })
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(orders_models.ReturnRequest.objects.count(), 0)

    def test_a_seller_can_raise_one_for_goods_we_never_carried(self):
        business, _, _, pickup, biz_user = _fixtures()
        self._login(biz_user)
        resp = self.client.post(self._url(), {
            'mode': 'standalone',
            'business': business.business_id,
            'pickup_location': pickup.id,
            'reason': 'customer_changed_mind',
            'customer_name': 'Buyer',
            'customer_phone': '97455500002',
            'customer_address': 'Villa 2',
            'dl_zone': '55',
            'schedule_pickup': '1',
        })
        self.assertEqual(resp.status_code, 302)
        ret = orders_models.ReturnRequest.objects.get()
        self.assertTrue(ret.is_standalone)
        self.assertEqual(ret.business, business)
        self.assertEqual(ret.pickup_order.order_status, 'to_review')

    def test_a_seller_cannot_drop_goods_at_another_clients_counter(self):
        business, _, _, _, biz_user = _fixtures()
        _, _, _, other_pickup, _ = _fixtures()
        self._login(biz_user)
        resp = self.client.post(self._url(), {
            'mode': 'standalone',
            'business': business.business_id,
            'pickup_location': other_pickup.id,
            'reason': 'damaged',
            'customer_phone': '97455500003',
        })
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(orders_models.ReturnRequest.objects.count(), 0)

    def test_a_seller_cannot_raise_one_against_a_client_they_do_not_own(self):
        _, _, _, _, biz_user = _fixtures()
        other_business, _, _, other_pickup, _ = _fixtures()
        self._login(biz_user)
        # The posted business is ignored entirely: the view uses the session's.
        self.client.post(self._url(), {
            'mode': 'standalone',
            'business': other_business.business_id,
            'pickup_location': other_pickup.id,
            'reason': 'damaged',
            'customer_phone': '97455500004',
        })
        self.assertFalse(
            orders_models.ReturnRequest.objects.filter(
                business=other_business).exists())


class AddedItemTests(TestCase):
    """Lines typed into "What is coming back" — goods with no outbound line
    behind them. The whole point of making ReturnItem.order_item nullable."""

    def _url(self):
        return reverse('workforce:returns_task_create')

    def test_a_standalone_claim_carries_the_products_picked_for_it(self):
        business, _, _, pickup, _ = _fixtures()
        product = _product(business)
        _staff(self)
        resp = self.client.post(self._url(), {
            'mode': 'standalone',
            'business': business.business_id,
            'pickup_location': pickup.id,
            'reason': 'damaged',
            'customer_phone': '97455500009',
            'inline_product_id[]': str(product.id),
            'inline_quantity[]': '3',
            'schedule_pickup': '1',
        })
        self.assertEqual(resp.status_code, 302)
        ret = orders_models.ReturnRequest.objects.get()
        line = ret.return_items.get()
        self.assertIsNone(line.order_item_id)
        self.assertEqual(line.product, product)
        self.assertEqual(line.quantity_returned, 3)
        self.assertEqual(line.display_name, product.item_name)
        self.assertIsNone(line.ordered_quantity)

        # And the collection the driver sees carries it as a real line.
        collected = ret.pickup_order.order_items.get()
        self.assertEqual(collected.product, product)
        self.assertEqual(collected.quantity, 3)
        self.assertEqual(ret.pickup_order.package_qty, 3)

    def test_an_order_claim_takes_extras_alongside_its_own_lines(self):
        business, order, item, _, _ = _fixtures()
        product = _product(business, 'Gift box')
        _staff(self)
        self.client.post(self._url(), {
            'mode': 'order', 'order_ref': order.order_number,
            'business': business.business_id, 'reason': 'damaged',
            'inline_product_id[]': str(product.id),
            'inline_quantity[]': '1',
        })
        ret = orders_models.ReturnRequest.objects.get(order=order)
        self.assertEqual(ret.return_items.count(), 2)
        self.assertEqual(ret.return_items.filter(order_item=item).count(), 1)
        self.assertEqual(ret.return_items.filter(product=product).count(), 1)

    def test_another_clients_product_is_dropped(self):
        business, _, _, pickup, _ = _fixtures()
        other_business, _, _, _, _ = _fixtures()
        theirs = _product(other_business, 'Not ours')
        _staff(self)
        self.client.post(self._url(), {
            'mode': 'standalone',
            'business': business.business_id,
            'pickup_location': pickup.id,
            'reason': 'damaged',
            'customer_phone': '97455500010',
            'inline_product_id[]': str(theirs.id),
            'inline_quantity[]': '2',
        })
        ret = orders_models.ReturnRequest.objects.get()
        self.assertEqual(ret.return_items.count(), 0)

    def test_a_seller_can_add_items_to_their_own_return(self):
        business, order, _, _, biz_user = _fixtures()
        product = _product(business, 'Watch')
        self.client.login(username=biz_user.username, password='x')
        resp = self.client.post(reverse('orders:add_return'), {
            'mode': 'order', 'order_ref': order.order_number,
            'reason': 'damaged',
            'inline_product_id[]': str(product.id),
            'inline_quantity[]': '2',
            'schedule_pickup': '1',
        })
        self.assertEqual(resp.status_code, 302)
        ret = orders_models.ReturnRequest.objects.get(order=order)
        self.assertTrue(ret.return_items.filter(product=product,
                                                quantity_returned=2).exists())

    def test_approving_a_claim_skips_the_lines_with_no_order_line(self):
        """business.views.return_update_status writes quantity_returned back onto
        the outbound line. A hand-added one has none and used to crash."""
        from orders.services import create_return_request
        business, order, item, _, biz_user = _fixtures()
        product = _product(business)
        ret = create_return_request(order, reason='damaged', status='pending')
        orders_models.ReturnItem.objects.create(
            return_request=ret, order_item=None, product=product,
            quantity_returned=1)

        self.client.login(username=biz_user.username, password='x')
        resp = self.client.post(
            reverse('business:return_update_status', args=[ret.id]),
            {'status': 'approved'})
        self.assertEqual(resp.status_code, 302)
        item.refresh_from_db()
        self.assertEqual(item.quantity_returned, 2)


class SearchByMobileTests(TestCase):
    """Nobody on the phone knows their order number; they are calling from the
    number that placed it."""

    def _url(self):
        return reverse('workforce:returns_task_create')

    def _order(self, business, pickup, phone, code):
        return orders_models.Order.objects.create(
            business=business, client_order_code=code,
            customer_name='Repeat Buyer', customer_phone=phone,
            customer_address='Flat 3', dl_zone=55,
            cod_amount=Decimal('80.00'), dl_amount=Decimal('25.00'),
            pickup_location=pickup, order_status='delivered')

    def test_one_order_on_a_mobile_is_picked_straight_away(self):
        business, _, _, pickup, _ = _fixtures()
        order = self._order(business, pickup, '97455512345', 'RI-PH-1')
        _staff(self)
        resp = self.client.get(self._url(), {'mode': 'order',
                                             'business': business.business_id,
                                             'order_ref': '55512345'})
        self.assertEqual(resp.status_code, 200)
        # Resolved, not shortlisted: the summary is on screen.
        self.assertContains(resp, order.order_number)
        self.assertContains(resp, 'Deliver the goods to')

    def test_several_orders_on_one_mobile_come_back_as_a_dated_shortlist(self):
        business, _, _, pickup, _ = _fixtures()
        a = self._order(business, pickup, '97455577777', 'RI-PH-A')
        b = self._order(business, pickup, '97455577777', 'RI-PH-B')
        _staff(self)
        resp = self.client.get(self._url(), {'mode': 'order',
                                             'business': business.business_id,
                                             'order_ref': '55577777'})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'returns_intake_table_matches')
        self.assertContains(resp, a.order_number)
        self.assertContains(resp, b.order_number)
        # A shortlist is a question, not an answer — nothing is selected yet.
        self.assertNotContains(resp, 'Deliver the goods to')

    def test_the_country_code_may_be_typed_or_left_off(self):
        from orders import return_intake
        business, _, _, pickup, _ = _fixtures()
        self._order(business, pickup, '97455588888', 'RI-PH-C')
        for typed in ('97455588888', '55588888', '+974 5558 8888'):
            found, candidates = return_intake.search_orders(typed, business=business)
            self.assertIsNotNone(found, typed)

    def test_a_mobile_only_finds_this_clients_orders_on_the_seller_console(self):
        business, _, _, _, biz_user = _fixtures()
        _, _, _, other_pickup, _ = _fixtures()
        other_business = other_pickup.business
        self._order(other_business, other_pickup, '97455599999', 'RI-PH-D')
        self.client.login(username=biz_user.username, password='x')
        resp = self.client.get(reverse('orders:add_return'),
                               {'mode': 'order', 'order_ref': '55599999'})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'No order matches')

    def test_a_submit_never_resolves_a_mobile(self):
        business, _, _, pickup, _ = _fixtures()
        self._order(business, pickup, '97455566666', 'RI-PH-E')
        _staff(self)
        resp = self.client.post(self._url(), {
            'mode': 'order', 'order_ref': '55566666',
            'business': business.business_id, 'reason': 'damaged'})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(orders_models.ReturnRequest.objects.count(), 0)


class StaffSearchScopeTests(TestCase):
    """The staff search runs inside ONE client, never across all of them."""

    def _url(self):
        return reverse('workforce:returns_task_create')

    def test_without_a_client_nothing_is_searched(self):
        _, order, _, _, _ = _fixtures()
        _staff(self)
        resp = self.client.get(self._url(), {'mode': 'order',
                                             'order_ref': order.order_number})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Pick the client first')
        self.assertNotContains(resp, 'Deliver the goods to')

    def test_another_clients_order_number_finds_nothing(self):
        business, _, _, _, _ = _fixtures()
        _, other_order, _, _, _ = _fixtures()
        _staff(self)
        resp = self.client.get(self._url(), {
            'mode': 'order', 'business': business.business_id,
            'order_ref': other_order.order_number})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'No order matches')
        self.assertNotContains(resp, other_order.customer_address)

    def test_a_submit_naming_another_clients_order_writes_nothing(self):
        business, _, _, _, _ = _fixtures()
        _, other_order, _, _, _ = _fixtures()
        _staff(self)
        resp = self.client.post(self._url(), {
            'mode': 'order', 'business': business.business_id,
            'order_ref': other_order.order_number, 'reason': 'damaged'})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(orders_models.ReturnRequest.objects.count(), 0)
