"""
Comprehensive View Test Suite for Staff/Workforce Dashboard
============================================================

120+ test scenarios covering:
- Staff Dashboard (authentication, stats, redirects)
- Order List Views (all, pending, published, filters, exports)
- Order Creation (single, AJAX, with products)
- Order Detail/Edit/Cancel (status updates, assign driver, zone)
- Order Status & Comments (AJAX endpoints)
- Delivery Task Management (list, detail, publish, assign, status)
- Bulk Operations (publish DMS, app, status, export, print)
- Seller Management (list, detail, status filtering, POST update)
- Driver Management (list, detail, status filtering, CSV export)
- User Verification (list, approve, reject, status updates)
- Finance & Fleet (dashboard, COD, earnings, transactions, settlement)
- Documents (driver docs, vehicles, stores, business licenses)
- Access Control (staff_required, anonymous, non-staff)
"""

import json
from decimal import Decimal
from datetime import date, timedelta
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.utils import timezone

from business import models as business_models
from core import models as core_models
from orders import models as orders_models
from delivery import models as delivery_models
from fleet import models as fleet_models

User = get_user_model()


class WorkforceTestMixin:
    """Reusable helpers for workforce/staff tests."""

    def create_staff_user(self, username='staffuser', password='Staff@123',
                          via_user=True, via_profile=True, departments=None):
        """
        Create a staff user. Set via_user=False to test Profile.is_staff only.

        Departments default to all three, which is what core migration 0017 gave
        every existing staff member. Without them StaffDepartmentMiddleware would
        302 this user away from every page, since it fails closed.
        Pass departments=[] to build a staff user with no desk.
        """
        from core.departments import ASSIGNABLE_DEPARTMENTS, DEPARTMENT_FIELDS

        if departments is None:
            departments = ASSIGNABLE_DEPARTMENTS
        dept_fields = {DEPARTMENT_FIELDS[code]: True for code in departments}

        user = User.objects.create_user(
            username=username, password=password,
            email=f'{username}@test.com', is_staff=via_user)
        profile = core_models.Profile.objects.create(
            user=user, first_name='Staff', last_name='User',
            phone=11111111, is_staff=via_profile, **dept_fields)
        return user, profile

    def create_non_staff_user(self, username='regularuser'):
        user = User.objects.create_user(
            username=username, password='Regular@123',
            email=f'{username}@test.com', is_staff=False)
        core_models.Profile.objects.create(
            user=user, first_name='Regular', last_name='User',
            phone=22222222, is_staff=False)
        return user

    def create_business(self, bid=9000, code='TBIZ', name='Test Business',
                        status='active'):
        biz_user = User.objects.create_user(
            username=f'biz{bid}', password='Biz@123',
            email=f'biz{bid}@test.com')
        biz_profile = core_models.Profile.objects.create(
            user=biz_user, first_name='Biz', last_name=f'Owner{bid}',
            phone=30000000 + bid, is_business=True,
            is_business_profile_completed=True,
            verification_status='verified')
        business = business_models.Business.objects.create(
            business_id=bid, user=biz_user, profile=biz_profile,
            business_name=name, business_code=code,
            business_status=status)
        business_models.BusinessProfile.objects.get_or_create(
            business=business)
        return business

    _driver_seq = 7000

    def create_driver(self, did=None, status='approved', code='DRV001'):
        if did is None:
            WorkforceTestMixin._driver_seq += 1
            did = WorkforceTestMixin._driver_seq
        drv_user = User.objects.create_user(
            username=f'drv{did}', password='Drv@123',
            email=f'drv{did}@test.com')
        drv_profile = core_models.Profile.objects.create(
            user=drv_user, first_name='Driver', last_name=f'Test{did}',
            phone=40000000 + did, is_driver=True,
            verification_status='pending')
        driver = fleet_models.Driver.objects.create(
            driver_id=did,
            user=drv_user, profile=drv_profile,
            driver_code=code, driver_phone=str(40000000 + did),
            driver_status=status)
        return driver

    def create_pickup_location(self, business, title='Main Warehouse'):
        return business_models.PickupLocation.objects.create(
            business=business, pickup_location_title=title,
            locality='Doha', pickup_zone_no=1,
            pickup_street_no=100, pickup_building_no=10,
            pickup_status='active')

    def create_order(self, business, pickup_location=None,
                     client_code=None, status='to_review', cod=0):
        import uuid
        if client_code is None:
            client_code = f'TC-{uuid.uuid4().hex[:8]}'
        return orders_models.Order.objects.create(
            business=business,
            client_order_code=client_code,
            customer_name='Test Customer',
            customer_phone='12345678',
            customer_whatsapp='12345678',
            customer_address='123 Test St',
            dl_zone=1, dl_street=10, dl_building=5,
            cod_amount=cod,
            cod_status_by_client='pending' if cod else 'no_cod',
            order_status=status,
            pickup_location=pickup_location)

    def create_delivery_task(self, order, driver=None, status='for_review'):
        addr = delivery_models.DlAddressUpdate.objects.filter(
            order=order).first()
        if not addr:
            addr = delivery_models.DlAddressUpdate.objects.create(
                full_name=order.customer_name,
                order=order,
                dl_task_number=order.order_number or 'TEST',
                mobile_no=order.customer_phone,
                dl_zone=order.dl_zone,
                dl_street=order.dl_street,
                dl_building=order.dl_building,
                dl_latitude=Decimal('0'),
                dl_longitude=Decimal('0'))
        return delivery_models.DeliveryTask.objects.create(
            dl_task_number=order.order_number or f'DL-{order.id}',
            dl_task_description=f'Delivery for {order.order_number}',
            order=order,
            business=order.business,
            dl_address_update=addr,
            driver=driver,
            dl_task_status=status,
            dl_task_status_client='for_review',
            pickup_location=order.pickup_location)

    def staff_login(self):
        self.client.login(username='staffuser', password='Staff@123')


# =============================================================================
# 1. DASHBOARD TESTS (12 tests)
# =============================================================================

class WfDashboardTest(WorkforceTestMixin, TestCase):

    def setUp(self):
        self.client = Client()
        self.user, self.profile = self.create_staff_user()

    def test_dashboard_loads_for_staff(self):
        """#1: Dashboard loads for staff user"""
        self.staff_login()
        resp = self.client.get(reverse('workforce:wf_dashboard'))
        self.assertEqual(resp.status_code, 200)
        self.assertIn('total_orders', resp.context)

    def test_dashboard_redirects_anonymous(self):
        """#2: Anonymous user redirected to login"""
        resp = self.client.get(reverse('workforce:wf_dashboard'))
        self.assertEqual(resp.status_code, 302)
        self.assertIn('login', resp.url.lower())

    def test_dashboard_redirects_non_staff(self):
        """#3: Non-staff user redirected"""
        self.create_non_staff_user()
        self.client.login(username='regularuser', password='Regular@123')
        resp = self.client.get(reverse('workforce:wf_dashboard'))
        self.assertEqual(resp.status_code, 302)

    def test_dashboard_order_counts(self):
        """#4: Dashboard shows correct order counts"""
        biz = self.create_business()
        pickup = self.create_pickup_location(biz)
        self.create_order(biz, pickup)
        self.create_order(biz, pickup)
        self.staff_login()
        resp = self.client.get(reverse('workforce:wf_dashboard'))
        self.assertEqual(resp.context['total_orders'], 2)

    def test_dashboard_driver_seller_counts(self):
        """#5: Dashboard shows driver/seller counts"""
        self.create_business(status='active')
        self.create_driver(status='approved')
        self.create_driver(did=2, status='pending', code='DRV002')
        self.staff_login()
        resp = self.client.get(reverse('workforce:wf_dashboard'))
        self.assertEqual(resp.context['active_drivers'], 1)
        self.assertEqual(resp.context['pending_drivers'], 1)

    def test_dashboard_cod_in_hand(self):
        """#6: Dashboard COD total"""
        driver = self.create_driver()
        driver.wallet_balance = Decimal('500')
        driver.save()
        self.staff_login()
        resp = self.client.get(reverse('workforce:wf_dashboard'))
        # cod_in_hand aggregates wallet_balance
        self.assertIn('cod_in_hand', resp.context)

    def test_dashboard_pending_verifications(self):
        """#7: Dashboard pending verifications count"""
        u = User.objects.create_user(username='penduser', password='P@123')
        core_models.Profile.objects.create(
            user=u, first_name='Pend', last_name='User',
            phone=55555555, verification_status='pending')
        self.staff_login()
        resp = self.client.get(reverse('workforce:wf_dashboard'))
        self.assertGreaterEqual(resp.context['pending_verifications'], 1)

    def test_dashboard_orders_trend(self):
        """#8: Dashboard has orders_trend data"""
        self.staff_login()
        resp = self.client.get(reverse('workforce:wf_dashboard'))
        self.assertIn('orders_trend', resp.context)
        self.assertEqual(len(resp.context['orders_trend']), 10)
        self.assertIn('day_label', resp.context['orders_trend'][0])

    def test_dashboard_zero_stats(self):
        """#9: Dashboard with no data shows zero stats"""
        self.staff_login()
        resp = self.client.get(reverse('workforce:wf_dashboard'))
        self.assertEqual(resp.context['total_orders'], 0)
        self.assertEqual(resp.context['orders_today'], 0)

    def test_dashboard_profile_less_user(self):
        """#10: User without profile redirected"""
        u = User.objects.create_user(
            username='noprofile', password='NP@123', is_staff=True)
        self.client.login(username='noprofile', password='NP@123')
        resp = self.client.get(reverse('workforce:wf_dashboard'))
        # Should redirect (no profile, staff_required may catch or dashboard redirect)
        self.assertIn(resp.status_code, [200, 302])

    def test_dashboard_staff_via_profile_only(self):
        """#11: Staff via Profile.is_staff only (User.is_staff=False)"""
        self.create_staff_user(
            username='profilestaff', password='PS@123',
            via_user=False, via_profile=True)
        self.client.login(username='profilestaff', password='PS@123')
        resp = self.client.get(reverse('workforce:wf_dashboard'))
        self.assertEqual(resp.status_code, 200)

    def test_dashboard_orders_today(self):
        """#12: orders_today counts only today's orders"""
        biz = self.create_business()
        pickup = self.create_pickup_location(biz)
        self.create_order(biz, pickup)
        self.staff_login()
        resp = self.client.get(reverse('workforce:wf_dashboard'))
        self.assertGreaterEqual(resp.context['orders_today'], 1)


# =============================================================================
# 2. ORDER LIST VIEWS TESTS (15 tests)
# =============================================================================

class WfOrderListTest(WorkforceTestMixin, TestCase):

    def setUp(self):
        self.client = Client()
        self.user, self.profile = self.create_staff_user()
        self.biz = self.create_business()
        self.pickup = self.create_pickup_location(self.biz)
        self.staff_login()

    def test_all_orders_loads(self):
        """#13: All orders page loads"""
        resp = self.client.get(reverse('workforce:wf_orders_all'))
        self.assertEqual(resp.status_code, 200)

    def test_all_orders_filter_by_business(self):
        """#14: Filter by business ID"""
        self.create_order(self.biz, self.pickup)
        resp = self.client.get(
            reverse('workforce:wf_orders_all'),
            {'business': self.biz.business_id})
        self.assertEqual(resp.status_code, 200)

    def test_all_orders_filter_by_status(self):
        """#15: Filter by order status"""
        self.create_order(self.biz, self.pickup, status='to_review')
        resp = self.client.get(
            reverse('workforce:wf_orders_all'), {'cStatus': 'to_review'})
        self.assertEqual(resp.status_code, 200)

    def test_to_publish_lists_by_status_not_task_latch(self):
        """An order sent back to review returns to /orders/to_publish/.

        The page used to filter on task_created=False, a one-way latch that
        never resets, so a published-then-un-published order could never
        reappear (and in production the page listed nothing at all).
        """
        order = self.create_order(self.biz, self.pickup, status='to_review')
        order.task_created = True  # already has a delivery task
        order.save(update_fields=['task_created'])

        resp = self.client.get(reverse('workforce:wf_orders_to_publish'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, order.order_number)

    def test_to_publish_excludes_published_orders(self):
        """An order at status 'publish' is off the to-publish list."""
        order = self.create_order(self.biz, self.pickup, status='publish')
        resp = self.client.get(reverse('workforce:wf_orders_to_publish'))
        self.assertNotContains(resp, order.order_number)

    def test_order_list_ignores_bogus_status_filter(self):
        """?cStatus=published is not a choice; it must not silently hide rows."""
        order = self.create_order(self.biz, self.pickup, status='publish')
        resp = self.client.get(
            reverse('workforce:wf_orders_all'), {'cStatus': 'published'})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, order.order_number)

    def test_all_orders_filter_by_mobile(self):
        """#16: Filter by customer mobile"""
        self.create_order(self.biz, self.pickup)
        resp = self.client.get(
            reverse('workforce:wf_orders_all'), {'mobile': '12345678'})
        self.assertEqual(resp.status_code, 200)

    def test_all_orders_filter_by_client_code(self):
        """#17: Filter by client order code"""
        self.create_order(self.biz, self.pickup, client_code='MY-001')
        resp = self.client.get(
            reverse('workforce:wf_orders_all'), {'cCode': 'MY-001'})
        self.assertEqual(resp.status_code, 200)

    def test_all_orders_pagination(self):
        """#18: Pagination works"""
        for i in range(15):
            self.create_order(self.biz, self.pickup)
        resp = self.client.get(
            reverse('workforce:wf_orders_all'), {'per_page': 10, 'page': 2})
        self.assertEqual(resp.status_code, 200)

    def test_orders_to_publish_loads(self):
        """#19: Orders to publish page loads"""
        self.create_order(self.biz, self.pickup)
        resp = self.client.get(reverse('workforce:wf_orders_to_publish'))
        self.assertEqual(resp.status_code, 200)

    def test_orders_published_loads(self):
        """#20: Orders published page loads"""
        resp = self.client.get(reverse('workforce:wf_orders_published'))
        self.assertEqual(resp.status_code, 200)

    def test_orders_pending_verification_loads(self):
        """#21: Pending verification page loads"""
        resp = self.client.get(reverse('workforce:orders_pending_verification'))
        self.assertEqual(resp.status_code, 200)

    def test_orders_by_seller_loads(self):
        """#22: Orders by seller page loads"""
        resp = self.client.get(reverse('workforce:wf_orders_by_seller'))
        self.assertEqual(resp.status_code, 200)

    def test_orders_dms_updated_loads(self):
        """#23: DMS updated orders page loads"""
        resp = self.client.get(reverse('workforce:dl_list_published_to_dms'))
        self.assertEqual(resp.status_code, 200)

    def test_orders_reported_loads(self):
        """#24: Reported orders page loads"""
        resp = self.client.get(reverse('workforce:wf_orders_reported'))
        self.assertEqual(resp.status_code, 200)

    def test_export_orders_csv(self):
        """#25: Export orders returns CSV"""
        self.create_order(self.biz, self.pickup)
        resp = self.client.get(reverse('workforce:export_orders_csv'))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp['Content-Type'], 'text/csv')
        self.assertIn('attachment', resp['Content-Disposition'])

    def test_export_orders_csv_with_filters(self):
        """#26: CSV export respects filters"""
        self.create_order(self.biz, self.pickup)
        resp = self.client.get(
            reverse('workforce:export_orders_csv'),
            {'business': self.biz.business_id})
        self.assertEqual(resp.status_code, 200)

    def test_all_orders_redirects_anonymous(self):
        """#27: Anonymous redirected from orders list"""
        self.client.logout()
        resp = self.client.get(reverse('workforce:wf_orders_all'))
        self.assertEqual(resp.status_code, 302)


# =============================================================================
# 3. ORDER CREATION TESTS (12 tests)
# =============================================================================

class WfOrderCreationTest(WorkforceTestMixin, TestCase):

    def setUp(self):
        self.client = Client()
        self.user, self.profile = self.create_staff_user()
        self.biz = self.create_business()
        self.pickup = self.create_pickup_location(self.biz)
        self.staff_login()

    def test_add_order_form_loads(self):
        """#28: Add order form loads"""
        resp = self.client.get(reverse('workforce:wf_orders_add'))
        self.assertEqual(resp.status_code, 200)
        self.assertIn('businesses', resp.context)

    def test_add_order_form_shows_businesses(self):
        """#29: Businesses in dropdown"""
        resp = self.client.get(reverse('workforce:wf_orders_add'))
        self.assertTrue(resp.context['businesses'].exists())

    def test_add_order_post_creates_order(self):
        """#30: POST creates order"""
        resp = self.client.post(reverse('workforce:wf_orders_add'), {
            'business': self.biz.business_id,
            'client_order_code': 'WF-001',
            'customer_name': 'John Doe',
            'customer_phone': '55512345',
            'customer_address': '123 Doha St',
            'dl_zone': '1', 'dl_street': '10', 'dl_building': '5',
            'cod_amount': '100',
            'order_notes': 'Test order',
        })
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(
            orders_models.Order.objects.filter(
                client_order_code='WF-001').exists())

    def test_add_order_with_pickup_location(self):
        """#31: POST with pickup location"""
        resp = self.client.post(reverse('workforce:wf_orders_add'), {
            'business': self.biz.business_id,
            'customer_name': 'Jane',
            'customer_phone': '55599999',
            'customer_address': '456 St',
            'dl_zone': '2', 'dl_street': '20', 'dl_building': '10',
            'pickup_location': self.pickup.id,
        })
        self.assertEqual(resp.status_code, 302)

    def test_add_order_without_business_fails(self):
        """#32: POST without business returns error"""
        resp = self.client.post(reverse('workforce:wf_orders_add'), {
            'business': 99999,
            'customer_name': 'No Biz',
            'customer_phone': '12345678',
            'customer_address': 'Addr',
        })
        # Should not create order, stays on page or redirects with error
        self.assertFalse(
            orders_models.Order.objects.filter(
                customer_name='No Biz').exists())

    def test_add_order_with_cod(self):
        """#33: POST with COD amount"""
        resp = self.client.post(reverse('workforce:wf_orders_add'), {
            'business': self.biz.business_id,
            'customer_name': 'COD Customer',
            'customer_phone': '55511111',
            'customer_address': 'COD Address',
            'dl_zone': '1', 'dl_street': '5', 'dl_building': '1',
            'cod_amount': '250',
        })
        self.assertEqual(resp.status_code, 302)
        order = orders_models.Order.objects.filter(
            customer_name='COD Customer').first()
        self.assertIsNotNone(order)
        self.assertEqual(order.cod_amount, 250)

    def test_add_order_with_product_name(self):
        """#34: POST with product_name creates OrderItem"""
        resp = self.client.post(reverse('workforce:wf_orders_add'), {
            'business': self.biz.business_id,
            'customer_name': 'Prod Customer',
            'customer_phone': '55522222',
            'customer_address': 'Prod Address',
            'dl_zone': '1', 'dl_street': '5', 'dl_building': '1',
            'product_name': 'Widget X',
            'quantity': '3',
        })
        self.assertEqual(resp.status_code, 302)
        order = orders_models.Order.objects.filter(
            customer_name='Prod Customer').first()
        self.assertIsNotNone(order)
        self.assertTrue(
            orders_models.OrderItem.objects.filter(order=order).exists())

    def test_add_order_with_scheduled_delivery(self):
        """#35: POST with scheduled delivery"""
        resp = self.client.post(reverse('workforce:wf_orders_add'), {
            'business': self.biz.business_id,
            'customer_name': 'Scheduled',
            'customer_phone': '55533333',
            'customer_address': 'Sched Addr',
            'dl_zone': '1', 'dl_street': '5', 'dl_building': '1',
            'scheduled_delivery': 'on',
            'scheduled_time': '14:00',
        })
        self.assertEqual(resp.status_code, 302)

    def test_add_order_ajax_returns_json(self):
        """#36: AJAX POST returns JSON"""
        resp = self.client.post(
            reverse('workforce:wf_orders_add'),
            {
                'business': self.biz.business_id,
                'customer_name': 'Ajax Customer',
                'customer_phone': '55544444',
                'customer_address': 'Ajax Addr',
                'dl_zone': '1', 'dl_street': '5', 'dl_building': '1',
            },
            HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.content)
        self.assertTrue(data['success'])

    def test_get_pickup_locations_ajax(self):
        """#37: AJAX pickup locations returns JSON"""
        resp = self.client.get(
            reverse('workforce:get_pickup_locations',
                    kwargs={'business_id': self.biz.business_id}))
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.content)
        self.assertTrue(data['success'])

    def test_get_pickup_locations_nonexistent(self):
        """#38: Nonexistent business pickup locations"""
        resp = self.client.get(
            reverse('workforce:get_pickup_locations',
                    kwargs={'business_id': 99999}))
        self.assertEqual(resp.status_code, 404)

    def test_orders_api_guide_loads(self):
        """#39: API guide page loads"""
        resp = self.client.get(reverse('workforce:wf_orders_api_guide'))
        self.assertEqual(resp.status_code, 200)


# =============================================================================
# 4. ORDER DETAIL/EDIT TESTS (12 tests)
# =============================================================================

class WfOrderDetailEditTest(WorkforceTestMixin, TestCase):

    def setUp(self):
        self.client = Client()
        self.user, self.profile = self.create_staff_user()
        self.biz = self.create_business()
        self.pickup = self.create_pickup_location(self.biz)
        self.order = self.create_order(self.biz, self.pickup, cod=100)
        # Create a ZoneName for zone update tests
        delivery_models.ZoneName.objects.create(
            zone_number=5, zone_name='Al Sadd', is_active=True)
        self.staff_login()

    def test_order_detail_loads(self):
        """#40: Order detail loads"""
        resp = self.client.get(
            reverse('workforce:order_detail',
                    kwargs={'order_id': self.order.id}))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context['order'].id, self.order.id)

    def test_order_detail_nonexistent(self):
        """#41: Nonexistent order → 404"""
        resp = self.client.get(
            reverse('workforce:order_detail',
                    kwargs={'order_id': 99999}))
        self.assertEqual(resp.status_code, 404)

    def test_order_edit_form_loads(self):
        """#42: Order edit form loads"""
        resp = self.client.get(
            reverse('workforce:order_edit',
                    kwargs={'order_id': self.order.id}))
        self.assertEqual(resp.status_code, 200)

    def test_order_edit_post_updates(self):
        """#43: Order edit POST updates"""
        resp = self.client.post(
            reverse('workforce:order_edit',
                    kwargs={'order_id': self.order.id}),
            {'customer_name': 'Updated Name',
             'customer_phone': '99999999',
             'customer_address': 'New Address',
             'dl_zone': '5', 'dl_street': '20', 'dl_building': '15',
             'cod_amount': '200'})
        # Should redirect or return JSON
        self.assertIn(resp.status_code, [200, 302])

    def test_cancel_order_success(self):
        """#44: Cancel order succeeds"""
        resp = self.client.post(
            reverse('workforce:cancel_order',
                    kwargs={'order_id': self.order.id}))
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.content)
        self.assertTrue(data['success'])
        self.order.refresh_from_db()
        self.assertEqual(self.order.order_status, 'cancelled')

    def test_cancel_published_order_fails(self):
        """#45: Cancel published order → 400"""
        self.order.order_status = 'publish'
        self.order.save()
        resp = self.client.post(
            reverse('workforce:cancel_order',
                    kwargs={'order_id': self.order.id}))
        self.assertEqual(resp.status_code, 400)

    def test_cancel_nonexistent_order(self):
        """#46: Cancel nonexistent order → 404"""
        resp = self.client.post(
            reverse('workforce:cancel_order',
                    kwargs={'order_id': 99999}))
        self.assertEqual(resp.status_code, 404)

    def test_assign_driver_to_order(self):
        """#47: Assign driver to order"""
        driver = self.create_driver()
        resp = self.client.post(
            reverse('workforce:assign_driver_to_order',
                    kwargs={'order_id': self.order.id}),
            json.dumps({'driver_id': driver.driver_id}),
            content_type='application/json')
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.content)
        self.assertTrue(data['success'])

    def test_assign_driver_without_id(self):
        """#48: Assign driver without ID → 400"""
        resp = self.client.post(
            reverse('workforce:assign_driver_to_order',
                    kwargs={'order_id': self.order.id}),
            json.dumps({}),
            content_type='application/json')
        self.assertEqual(resp.status_code, 400)

    def test_assign_invalid_driver(self):
        """#49: Assign nonexistent driver → 400"""
        resp = self.client.post(
            reverse('workforce:assign_driver_to_order',
                    kwargs={'order_id': self.order.id}),
            json.dumps({'driver_id': 99999}),
            content_type='application/json')
        self.assertEqual(resp.status_code, 400)

    def test_update_order_zone(self):
        """#50: Update order zone"""
        resp = self.client.post(
            reverse('workforce:update_order_zone',
                    kwargs={'order_id': self.order.id}),
            json.dumps({'zone_number': 5, 'street_number': 20,
                        'building_number': 10}),
            content_type='application/json')
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.content)
        self.assertTrue(data['success'])

    def test_update_order_zone_invalid_json(self):
        """#51: Update zone with invalid JSON → 400"""
        resp = self.client.post(
            reverse('workforce:update_order_zone',
                    kwargs={'order_id': self.order.id}),
            'not-json',
            content_type='application/json')
        self.assertEqual(resp.status_code, 400)


# =============================================================================
# 5. ORDER STATUS & COMMENTS TESTS (10 tests)
# =============================================================================

class WfOrderStatusTest(WorkforceTestMixin, TestCase):

    def setUp(self):
        self.client = Client()
        self.user, self.profile = self.create_staff_user()
        self.biz = self.create_business()
        self.pickup = self.create_pickup_location(self.biz)
        self.order = self.create_order(self.biz, self.pickup)
        self.staff_login()

    def test_update_order_status_valid(self):
        """#52: Update order status with valid status"""
        resp = self.client.post(
            reverse('workforce:update_order_status',
                    kwargs={'order_id': self.order.id}),
            json.dumps({'status': 'ready_to_pickup', 'status_type': 'order'}),
            content_type='application/json')
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.content)
        self.assertTrue(data['success'])
        self.order.refresh_from_db()
        self.assertEqual(self.order.order_status, 'ready_to_pickup')

    def test_update_order_status_rejects_non_choice(self):
        """Statuses outside ORDER_STATUS_BY_CLIENT are refused.

        'processing' and 'published' used to sit in a hand-written whitelist
        that had drifted from the model; order_status is a plain CharField, so
        that whitelist is the only thing stopping an invalid value being saved.
        """
        for bogus in ('processing', 'published', 'to_publish', 'reported'):
            with self.subTest(status=bogus):
                resp = self.client.post(
                    reverse('workforce:update_order_status',
                            kwargs={'order_id': self.order.id}),
                    json.dumps({'status': bogus, 'status_type': 'order'}),
                    content_type='application/json')
                self.assertEqual(resp.status_code, 400)

    def test_update_task_status_valid(self):
        """#53: Update task status"""
        resp = self.client.post(
            reverse('workforce:update_order_status',
                    kwargs={'order_id': self.order.id}),
            json.dumps({'status': 'assigned', 'status_type': 'task'}),
            content_type='application/json')
        self.assertEqual(resp.status_code, 200)

    def test_update_status_invalid(self):
        """#54: Invalid status → 400"""
        resp = self.client.post(
            reverse('workforce:update_order_status',
                    kwargs={'order_id': self.order.id}),
            json.dumps({'status': 'bogus_status', 'status_type': 'order'}),
            content_type='application/json')
        self.assertEqual(resp.status_code, 400)

    def test_update_status_invalid_type(self):
        """#55: Invalid status_type → 400"""
        resp = self.client.post(
            reverse('workforce:update_order_status',
                    kwargs={'order_id': self.order.id}),
            json.dumps({'status': 'processing', 'status_type': 'invalid'}),
            content_type='application/json')
        self.assertEqual(resp.status_code, 400)

    def test_update_status_missing(self):
        """#56: Missing status → 400"""
        resp = self.client.post(
            reverse('workforce:update_order_status',
                    kwargs={'order_id': self.order.id}),
            json.dumps({'status_type': 'order'}),
            content_type='application/json')
        self.assertEqual(resp.status_code, 400)

    def test_publish_order_to_delivery(self):
        """#57: Publish order to delivery"""
        resp = self.client.post(
            reverse('workforce:publish_order_to_delivery',
                    kwargs={'order_id': self.order.id}))
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.content)
        self.assertTrue(data['success'])
        self.order.refresh_from_db()
        self.assertEqual(self.order.order_status, 'publish')

    def test_add_comment_success(self):
        """#58: Add comment to order"""
        resp = self.client.post(
            reverse('workforce:add_order_comment',
                    kwargs={'order_id': self.order.id}),
            json.dumps({'comment': 'Test comment from staff'}),
            content_type='application/json')
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.content)
        self.assertTrue(data['success'])

    def test_add_comment_empty(self):
        """#59: Empty comment → 400"""
        resp = self.client.post(
            reverse('workforce:add_order_comment',
                    kwargs={'order_id': self.order.id}),
            json.dumps({'comment': ''}),
            content_type='application/json')
        self.assertEqual(resp.status_code, 400)

    def test_add_comment_nonexistent_order(self):
        """#60: Comment on nonexistent order → 404"""
        resp = self.client.post(
            reverse('workforce:add_order_comment',
                    kwargs={'order_id': 99999}),
            json.dumps({'comment': 'Should fail'}),
            content_type='application/json')
        self.assertEqual(resp.status_code, 404)



# =============================================================================
# 6. DELIVERY TASK TESTS (14 tests)
# =============================================================================

class WfDeliveryTaskTest(WorkforceTestMixin, TestCase):

    def setUp(self):
        self.client = Client()
        self.user, self.profile = self.create_staff_user()
        self.biz = self.create_business()
        self.pickup = self.create_pickup_location(self.biz)
        self.order = self.create_order(self.biz, self.pickup)
        # Mark order as verified so publish/assign views don't block
        self.order.verification_status = 'verified'
        self.order.save(update_fields=['verification_status'])
        self.task = self.create_delivery_task(self.order)
        self.staff_login()

    def test_dl_list_all_loads(self):
        """#62: DL list all loads"""
        resp = self.client.get(reverse('workforce:dl_list_all'))
        self.assertEqual(resp.status_code, 200)

    def test_dl_list_filter_by_code(self):
        """#63: DL list filters by task code"""
        resp = self.client.get(
            reverse('workforce:dl_list_all'),
            {'dlCode': self.task.dl_task_number[:5]})
        self.assertEqual(resp.status_code, 200)

    def test_dl_list_filter_by_business(self):
        """#64: DL list filters by business"""
        resp = self.client.get(
            reverse('workforce:dl_list_all'),
            {'business': self.biz.business_id})
        self.assertEqual(resp.status_code, 200)

    def test_dl_list_incomplete_loads(self):
        """#65: Incomplete DL list loads"""
        resp = self.client.get(
            reverse('workforce:dl_list_incompleted_details'))
        self.assertEqual(resp.status_code, 200)

    def test_dl_list_published_loads(self):
        """#66: Published DL list loads"""
        resp = self.client.get(
            reverse('workforce:dl_list_published_to_dms'))
        self.assertEqual(resp.status_code, 200)

    def test_dl_list_unpublished_loads(self):
        """#67: Unpublished DL list loads"""
        resp = self.client.get(
            reverse('workforce:dl_list_ready_to_published_to_dms'))
        self.assertEqual(resp.status_code, 200)

    def test_delivery_task_detail_loads(self):
        """#68: Delivery task detail loads"""
        resp = self.client.get(
            reverse('workforce:delivery_task_detail',
                    kwargs={'task_id': self.task.id}))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context['task'].id, self.task.id)

    def test_delivery_task_detail_nonexistent(self):
        """#69: Nonexistent task → 404"""
        resp = self.client.get(
            reverse('workforce:delivery_task_detail',
                    kwargs={'task_id': 99999}))
        self.assertEqual(resp.status_code, 404)

    def test_publish_task_to_dms(self):
        """#70: Publish task to delivery fleet"""
        resp = self.client.post(
            reverse('workforce:publish_task_to_fleets',
                    kwargs={'task_id': self.task.id}))
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.content)
        self.assertTrue(data['success'])

    def test_publish_task_to_driver_app(self):
        """#71: Publish task to driver app (unpublish fleets)"""
        resp = self.client.post(
            reverse('workforce:unpublish_task_from_fleets',
                    kwargs={'task_id': self.task.id}))
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.content)
        self.assertTrue(data['success'])

    def test_assign_driver_to_task(self):
        """#72: Assign driver to task"""
        driver = self.create_driver()
        resp = self.client.post(
            reverse('workforce:assign_driver_to_task',
                    kwargs={'task_id': self.task.id}),
            json.dumps({'driver_id': driver.driver_id}),
            content_type='application/json')
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.content)
        self.assertTrue(data['success'])

    def test_assign_driver_to_task_no_id(self):
        """#73: Assign driver without ID → 400"""
        resp = self.client.post(
            reverse('workforce:assign_driver_to_task',
                    kwargs={'task_id': self.task.id}),
            json.dumps({}),
            content_type='application/json')
        self.assertEqual(resp.status_code, 400)

    def test_update_task_status_valid(self):
        """#74: Update task status"""
        resp = self.client.post(
            reverse('workforce:update_task_status',
                    kwargs={'task_id': self.task.id}),
            json.dumps({'status': 'pending'}),
            content_type='application/json')
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.content)
        self.assertTrue(data['success'])

    def test_update_task_status_invalid(self):
        """#75: Invalid task status → 400"""
        resp = self.client.post(
            reverse('workforce:update_task_status',
                    kwargs={'task_id': self.task.id}),
            json.dumps({'status': 'bogus'}),
            content_type='application/json')
        self.assertEqual(resp.status_code, 400)

    def _move_task_to(self, status):
        """Drive the task straight to a status without the state machine."""
        from delivery.models import DeliveryTask
        DeliveryTask.objects.filter(id=self.task.id).update(dl_task_status=status)
        self.task.refresh_from_db()

    def test_update_task_status_failed_requires_reason(self):
        """Closing a task as failed without a reason is rejected."""
        self._move_task_to('out_for_delivery')
        resp = self.client.post(
            reverse('workforce:update_task_status',
                    kwargs={'task_id': self.task.id}),
            json.dumps({'status': 'failed'}),
            content_type='application/json')
        self.assertEqual(resp.status_code, 400)
        self.task.refresh_from_db()
        self.assertNotEqual(self.task.dl_task_status, 'failed')

    def test_update_task_status_failed_records_reason(self):
        """Staff reason lands on the same fields the driver app writes."""
        self._move_task_to('out_for_delivery')
        resp = self.client.post(
            reverse('workforce:update_task_status',
                    kwargs={'task_id': self.task.id}),
            json.dumps({
                'status': 'failed',
                'failure_reason': 'customer_not_home',
                'failure_notes': 'No answer after 3 calls',
                'notes': 'Customer Not Home — No answer after 3 calls',
            }),
            content_type='application/json')
        self.assertEqual(resp.status_code, 200)
        self.task.refresh_from_db()
        self.assertEqual(self.task.dl_task_status, 'failed')
        self.assertEqual(self.task.failure_reason, 'customer_not_home')
        self.assertEqual(self.task.failure_notes, 'No answer after 3 calls')

    def test_update_task_status_cancel_mirrors_rejection_reason(self):
        """Cancel/reject also fill rejection_reason for the record card."""
        self._move_task_to('out_for_delivery')
        resp = self.client.post(
            reverse('workforce:update_task_status',
                    kwargs={'task_id': self.task.id}),
            json.dumps({
                'status': 'cancelled',
                'failure_reason': 'customer_refused',
                'failure_notes': 'Changed mind',
            }),
            content_type='application/json')
        self.assertEqual(resp.status_code, 200)
        self.task.refresh_from_db()
        self.assertEqual(self.task.failure_reason, 'customer_refused')
        self.assertIn('Changed mind', self.task.rejection_reason or '')


# =============================================================================
# 7. BULK OPERATIONS TESTS (6 tests)
# =============================================================================

class WfBulkOperationsTest(WorkforceTestMixin, TestCase):

    def setUp(self):
        self.client = Client()
        self.user, self.profile = self.create_staff_user()
        self.biz = self.create_business()
        self.pickup = self.create_pickup_location(self.biz)
        self.order = self.create_order(self.biz, self.pickup)
        self.task = self.create_delivery_task(self.order)
        self.staff_login()

    def test_bulk_publish_dms(self):
        """#76: Bulk publish to delivery fleets"""
        resp = self.client.post(
            reverse('workforce:bulk_publish_fleets'),
            json.dumps({'task_ids': [self.task.id]}),
            content_type='application/json')
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.content)
        self.assertTrue(data['success'])

    def test_bulk_publish_app(self):
        """#77: Bulk publish to driver app"""
        resp = self.client.post(
            reverse('workforce:bulk_publish_app'),
            json.dumps({'task_ids': [self.task.id]}),
            content_type='application/json')
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.content)
        self.assertTrue(data['success'])

    def test_bulk_update_status(self):
        """#78: Bulk update task status"""
        resp = self.client.post(
            reverse('workforce:bulk_update_status'),
            json.dumps({'task_ids': [self.task.id], 'status': 'pending'}),
            content_type='application/json')
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.content)
        self.assertTrue(data['success'])

    def test_bulk_export_tasks_csv(self):
        """#79: Bulk export returns CSV"""
        resp = self.client.get(
            reverse('workforce:bulk_export_tasks'),
            {'ids': str(self.task.id)})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp['Content-Type'], 'text/csv')

    def test_bulk_print_tasks(self):
        """#80: Bulk print tasks loads"""
        resp = self.client.get(
            reverse('workforce:bulk_print_tasks'),
            {'ids': str(self.task.id)})
        self.assertEqual(resp.status_code, 200)

    def test_tasks_followup_list(self):
        """#81: Followup tasks list loads"""
        resp = self.client.get(reverse('workforce:tasks_followup_list'))
        self.assertEqual(resp.status_code, 200)


# =============================================================================
# 8. SELLER MANAGEMENT TESTS (10 tests)
# =============================================================================

class WfSellerManagementTest(WorkforceTestMixin, TestCase):

    def setUp(self):
        self.client = Client()
        self.user, self.profile = self.create_staff_user()
        self.biz = self.create_business()
        self.staff_login()

    def test_sellers_list_loads(self):
        """#82: Sellers list loads"""
        resp = self.client.get(reverse('workforce:sellers_list'))
        self.assertEqual(resp.status_code, 200)

    def test_sellers_pending_loads(self):
        """#83: Pending sellers loads"""
        resp = self.client.get(reverse('workforce:sellers_pending'))
        self.assertEqual(resp.status_code, 200)

    def test_sellers_active_loads(self):
        """#84: Active sellers loads"""
        resp = self.client.get(reverse('workforce:sellers_active'))
        self.assertEqual(resp.status_code, 200)

    def test_sellers_inactive_loads(self):
        """#85: Inactive sellers loads"""
        resp = self.client.get(reverse('workforce:sellers_inactive'))
        self.assertEqual(resp.status_code, 200)

    def test_seller_detail_loads(self):
        """#86: Seller detail loads"""
        resp = self.client.get(
            reverse('workforce:seller_detail',
                    kwargs={'business_id': self.biz.business_id}))
        self.assertEqual(resp.status_code, 200)
        self.assertIn('order_stats', resp.context)
        self.assertIn('cod_stats', resp.context)

    def test_seller_detail_nonexistent(self):
        """#87: Nonexistent seller → 404"""
        resp = self.client.get(
            reverse('workforce:seller_detail',
                    kwargs={'business_id': 99999}))
        self.assertEqual(resp.status_code, 404)

    def test_seller_detail_post_update(self):
        """#88: Seller detail POST updates"""
        resp = self.client.post(
            reverse('workforce:seller_detail',
                    kwargs={'business_id': self.biz.business_id}),
            {'business_name': 'Updated Biz Name',
             'business_status': 'active',
             'business_phone': '77712345'})
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.content)
        self.assertTrue(data['success'])
        self.biz.refresh_from_db()
        self.assertEqual(self.biz.business_name, 'Updated Biz Name')

    def test_sellers_list_search(self):
        """#89: Sellers list search filter"""
        resp = self.client.get(
            reverse('workforce:sellers_list'),
            {'search': 'Test Business'})
        self.assertEqual(resp.status_code, 200)

    def test_sellers_list_empty(self):
        """#90: Sellers list with no matching businesses"""
        resp = self.client.get(
            reverse('workforce:sellers_list'),
            {'search': 'ZZZZZ_NO_MATCH'})
        self.assertEqual(resp.status_code, 200)

    def test_seller_detail_has_delivery_stats(self):
        """#91: Seller detail has delivery_stats"""
        resp = self.client.get(
            reverse('workforce:seller_detail',
                    kwargs={'business_id': self.biz.business_id}))
        self.assertIn('delivery_stats', resp.context)


# =============================================================================
# 9. DRIVER MANAGEMENT TESTS (10 tests)
# =============================================================================

class WfDriverManagementTest(WorkforceTestMixin, TestCase):

    def setUp(self):
        self.client = Client()
        self.user, self.profile = self.create_staff_user()
        self.driver = self.create_driver()
        self.staff_login()

    def test_drivers_list_loads(self):
        """#92: Drivers list loads"""
        resp = self.client.get(reverse('workforce:drivers_list'))
        self.assertEqual(resp.status_code, 200)
        self.assertIn('total_count', resp.context)

    def test_drivers_pending_loads(self):
        """#93: Pending drivers loads"""
        resp = self.client.get(reverse('workforce:drivers_pending'))
        self.assertEqual(resp.status_code, 200)

    def test_drivers_active_loads(self):
        """#94: Active drivers loads"""
        resp = self.client.get(reverse('workforce:drivers_active'))
        self.assertEqual(resp.status_code, 200)

    def test_drivers_inactive_loads(self):
        """#95: Inactive drivers loads"""
        resp = self.client.get(reverse('workforce:drivers_inactive'))
        self.assertEqual(resp.status_code, 200)

    def test_driver_detail_loads(self):
        """#96: Driver detail loads"""
        resp = self.client.get(
            reverse('workforce:driver_detail',
                    kwargs={'driver_id': self.driver.driver_id}))
        self.assertEqual(resp.status_code, 200)

    def test_driver_detail_nonexistent(self):
        """#97: Nonexistent driver → 404"""
        resp = self.client.get(
            reverse('workforce:driver_detail',
                    kwargs={'driver_id': 99999}))
        self.assertEqual(resp.status_code, 404)

    def test_drivers_search(self):
        """#98: Drivers search filter"""
        resp = self.client.get(
            reverse('workforce:drivers_list'),
            {'search': 'Driver'})
        self.assertEqual(resp.status_code, 200)

    def test_drivers_status_filter(self):
        """#99: Drivers status filter"""
        resp = self.client.get(
            reverse('workforce:drivers_list'),
            {'status': 'approved'})
        self.assertEqual(resp.status_code, 200)

    def test_export_drivers_csv(self):
        """#100: Export drivers returns CSV"""
        resp = self.client.get(reverse('workforce:export_drivers_csv'))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp['Content-Type'], 'text/csv')

    def test_drivers_list_empty(self):
        """#101: Drivers list with status that has no matches"""
        resp = self.client.get(
            reverse('workforce:drivers_list'),
            {'status': 'Blocked'})
        self.assertEqual(resp.status_code, 200)


# =============================================================================
# 10. USER VERIFICATION TESTS (8 tests)
# =============================================================================

class WfUserVerificationTest(WorkforceTestMixin, TestCase):

    def setUp(self):
        self.client = Client()
        self.user, self.profile = self.create_staff_user()
        self.staff_login()

    def test_verification_list_loads(self):
        """#102: Verification list loads"""
        resp = self.client.get(
            reverse('workforce:user_verification_list'))
        self.assertEqual(resp.status_code, 200)

    def test_verification_list_filter(self):
        """#103: Verification list filters by status"""
        resp = self.client.get(
            reverse('workforce:user_verification_list'),
            {'status': 'pending'})
        self.assertEqual(resp.status_code, 200)

    def test_verify_user_activates_business(self):
        """#104: Verify user activates their business"""
        from django.utils import timezone
        biz = self.create_business(bid=8001, status='Pending on Review')
        biz_profile = biz.profile
        biz_profile.verification_status = 'pending'
        biz_profile.verification_applied_at = timezone.now()
        biz_profile.save()
        resp = self.client.post(
            reverse('workforce:update_verification_status',
                    kwargs={'profile_id': biz_profile.id}),
            json.dumps({'status': 'verified'}),
            content_type='application/json')
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.content)
        self.assertTrue(data['success'])
        biz.refresh_from_db()
        self.assertEqual(biz.business_status, 'active')

    def test_verify_user_activates_driver(self):
        """#105: Verify user activates their driver"""
        from django.utils import timezone
        driver = self.create_driver(status='pending', code='PND01')
        drv_profile = driver.profile
        drv_profile.verification_status = 'pending'
        drv_profile.verification_applied_at = timezone.now()
        drv_profile.save()
        resp = self.client.post(
            reverse('workforce:update_verification_status',
                    kwargs={'profile_id': drv_profile.id}),
            json.dumps({'status': 'verified'}),
            content_type='application/json')
        self.assertEqual(resp.status_code, 200)
        driver.refresh_from_db()
        self.assertEqual(driver.driver_status, 'approved')

    def test_reject_user_stores_reason(self):
        """#106: Reject user stores rejection reason"""
        u = User.objects.create_user(username='rejectme', password='R@123')
        p = core_models.Profile.objects.create(
            user=u, first_name='Rej', last_name='User',
            phone=66666666, verification_status='pending')
        resp = self.client.post(
            reverse('workforce:update_verification_status',
                    kwargs={'profile_id': p.id}),
            json.dumps({'status': 'rejected',
                        'rejection_reason': 'Incomplete docs'}),
            content_type='application/json')
        self.assertEqual(resp.status_code, 200)
        p.refresh_from_db()
        self.assertEqual(p.rejection_reason, 'Incomplete docs')

    def test_verify_without_status_fails(self):
        """#107: Missing status → 400"""
        u = User.objects.create_user(username='nostat', password='N@123')
        p = core_models.Profile.objects.create(
            user=u, first_name='No', last_name='Status', phone=77777777)
        resp = self.client.post(
            reverse('workforce:update_verification_status',
                    kwargs={'profile_id': p.id}),
            json.dumps({}),
            content_type='application/json')
        self.assertEqual(resp.status_code, 400)

    def test_verify_nonexistent_profile(self):
        """#108: Nonexistent profile → 404"""
        resp = self.client.post(
            reverse('workforce:update_verification_status',
                    kwargs={'profile_id': 99999}),
            json.dumps({'status': 'verified'}),
            content_type='application/json')
        self.assertEqual(resp.status_code, 404)

    def test_verification_list_empty(self):
        """#109: Verification list with no pending users loads"""
        resp = self.client.get(
            reverse('workforce:user_verification_list'),
            {'status': 'verified'})
        self.assertEqual(resp.status_code, 200)


# =============================================================================
# 11. FINANCE & FLEET TESTS (8 tests)
# =============================================================================

class WfFinanceFleetTest(WorkforceTestMixin, TestCase):

    def setUp(self):
        self.client = Client()
        self.user, self.profile = self.create_staff_user()
        self.staff_login()

    def test_finance_dashboard_loads(self):
        """#110: Finance dashboard loads"""
        resp = self.client.get(
            reverse('workforce:workforce_finance_dashboard'))
        self.assertEqual(resp.status_code, 200)

    def test_finance_dashboard_custom_days(self):
        """#111: Finance dashboard with custom days filter"""
        resp = self.client.get(
            reverse('workforce:workforce_finance_dashboard'),
            {'days': 7})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context['selected_days'], 7)

    def test_finance_dashboard_invalid_days(self):
        """#112: Finance dashboard invalid days defaults to 30"""
        resp = self.client.get(
            reverse('workforce:workforce_finance_dashboard'),
            {'days': 'abc'})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context['selected_days'], 30)

    def test_fleet_cod_in_hand_loads(self):
        """#113: Fleet COD in hand loads"""
        resp = self.client.get(reverse('workforce:fleet_cod_in_hand'))
        self.assertEqual(resp.status_code, 200)

    def test_fleet_drivers_earnings_loads(self):
        """#114: Fleet drivers earnings loads"""
        resp = self.client.get(reverse('workforce:fleet_drivers_earnings'))
        self.assertEqual(resp.status_code, 200)

    def test_fleet_transactions_loads(self):
        """#115: Fleet transactions loads"""
        resp = self.client.get(reverse('workforce:fleet_transactions'))
        self.assertEqual(resp.status_code, 200)

    def test_cod_settlement_report_loads(self):
        """#116: COD settlement report loads"""
        resp = self.client.get(reverse('workforce:cod_settlement_report'))
        self.assertEqual(resp.status_code, 200)

    def test_cod_settlement_action_no_drivers(self):
        """#117: COD settlement action without drivers → 400"""
        resp = self.client.post(
            reverse('workforce:cod_settlement_action'), {})
        self.assertEqual(resp.status_code, 400)

    def _driver_holding_cod(self, amount, did=None):
        """A driver with one delivered, cash-collected, unsettled task."""
        business = self.create_business(bid=9100 + (did or 0) % 100,
                                        code=f'CB{did}')
        loc = self.create_pickup_location(business)
        order = self.create_order(business, loc, status='delivered',
                                  cod=amount)
        driver = self.create_driver(did=did)
        task = self.create_delivery_task(order, driver, status='delivered')
        delivery_models.DeliveryTask.objects.filter(pk=task.pk).update(
            cod_collected=True,
            cod_collected_amount=Decimal(amount),
            cod_collected_at=timezone.now(),
            cod_settled=False,
            payment_method='cash',
        )
        return driver

    def test_cod_settlement_lists_live_balance_not_cached_column(self):
        """#118: The sheet is built from the tasks, so a stale cached
        Driver.cod_in_hand neither hides a driver nor changes the figure."""
        driver = self._driver_holding_cod(250, did=7801)
        # Cached column drifted to zero — the old page filtered on it and would
        # have dropped this driver off the sheet entirely.
        fleet_models.Driver.objects.filter(pk=driver.pk).update(
            cod_in_hand=Decimal('0.00'))

        resp = self.client.get(reverse('workforce:cod_settlement_report'))
        self.assertEqual(resp.status_code, 200)
        listed = {d.driver_id: d.in_hand for d in resp.context['drivers']}
        self.assertIn(driver.driver_id, listed)
        self.assertEqual(listed[driver.driver_id], Decimal('250.00'))
        self.assertEqual(resp.context['total_in_hand'], Decimal('250.00'))

    def test_cod_settlement_action_settles_and_clears(self):
        """#119: Recording a hand-in settles the tasks and empties the sheet."""
        driver = self._driver_holding_cod(300, did=7802)

        resp = self.client.post(
            reverse('workforce:cod_settlement_action'),
            {'driver_ids[]': [str(driver.driver_id)],
             'payment_method': 'cash',
             'reference': 'RCPT-1'})
        self.assertEqual(resp.status_code, 200)
        payload = resp.json()
        self.assertTrue(payload['success'])
        self.assertEqual(payload['settled_count'], 1)
        self.assertEqual(payload['total_settled'], 300.0)

        self.assertFalse(
            delivery_models.DeliveryTask.objects.filter(
                driver=driver, cod_collected=True, cod_settled=False).exists())
        after = self.client.get(reverse('workforce:cod_settlement_report'))
        self.assertNotIn(
            driver.driver_id,
            [d.driver_id for d in after.context['drivers']])


# =============================================================================
# 12. DOCUMENTS TESTS (8 tests)
# =============================================================================

class WfDocumentsTest(WorkforceTestMixin, TestCase):

    def setUp(self):
        self.client = Client()
        self.user, self.profile = self.create_staff_user()
        self.biz = self.create_business()
        self.driver = self.create_driver()
        self.staff_login()

    def test_driver_documents_list_loads(self):
        """#118: Driver documents list loads"""
        resp = self.client.get(reverse('workforce:driver_documents_list'))
        self.assertEqual(resp.status_code, 200)

    def test_vehicle_documents_list_loads(self):
        """#119: Vehicle documents list loads"""
        resp = self.client.get(reverse('workforce:vehicle_documents_list'))
        self.assertEqual(resp.status_code, 200)

    def test_vehicle_document_detail_loads(self):
        """#120: Vehicle document detail loads"""
        resp = self.client.get(
            reverse('workforce:vehicle_document_detail',
                    kwargs={'driver_id': self.driver.driver_id}))
        self.assertEqual(resp.status_code, 200)

    def test_store_documents_list_loads(self):
        """#121: Store documents list loads"""
        resp = self.client.get(reverse('workforce:store_documents_list'))
        self.assertEqual(resp.status_code, 200)

    def test_store_document_detail_loads(self):
        """#122: Store document detail loads"""
        resp = self.client.get(
            reverse('workforce:store_document_detail',
                    kwargs={'business_id': self.biz.business_id}))
        self.assertEqual(resp.status_code, 200)

    def test_business_licenses_list_loads(self):
        """#123: Business licenses list loads"""
        resp = self.client.get(reverse('workforce:business_licenses_list'))
        self.assertEqual(resp.status_code, 200)

    def test_business_license_detail_loads(self):
        """#124: Business license detail loads"""
        resp = self.client.get(
            reverse('workforce:business_license_detail',
                    kwargs={'business_id': self.biz.business_id}))
        self.assertEqual(resp.status_code, 200)

    def test_driver_documents_search(self):
        """#125: Driver documents search works"""
        resp = self.client.get(
            reverse('workforce:driver_documents_list'),
            {'search': 'Driver'})
        self.assertEqual(resp.status_code, 200)


# =============================================================================
# 13. ACCESS CONTROL TESTS (6 tests)
# =============================================================================

class WfAccessControlTest(WorkforceTestMixin, TestCase):

    def setUp(self):
        self.client = Client()

    def test_anonymous_redirected_from_dashboard(self):
        """#126: Anonymous → 302 on dashboard"""
        resp = self.client.get(reverse('workforce:wf_dashboard'))
        self.assertEqual(resp.status_code, 302)

    def test_anonymous_redirected_from_orders(self):
        """#127: Anonymous → 302 on orders"""
        resp = self.client.get(reverse('workforce:wf_orders_all'))
        self.assertEqual(resp.status_code, 302)

    def test_non_staff_redirected(self):
        """#128: Non-staff → 302"""
        self.create_non_staff_user()
        self.client.login(username='regularuser', password='Regular@123')
        resp = self.client.get(reverse('workforce:wf_dashboard'))
        self.assertEqual(resp.status_code, 302)

    def test_staff_via_user_model(self):
        """#129: Staff via User.is_staff=True"""
        self.create_staff_user(
            username='userstaff', password='US@123',
            via_user=True, via_profile=False)
        self.client.login(username='userstaff', password='US@123')
        resp = self.client.get(reverse('workforce:wf_dashboard'))
        self.assertEqual(resp.status_code, 200)

    def test_workflow_guide_loads(self):
        """#130: Workflow guide page loads"""
        user, _ = self.create_staff_user()
        self.client.login(username='staffuser', password='Staff@123')
        resp = self.client.get(reverse('workforce:workflow_guide'))
        self.assertEqual(resp.status_code, 200)

    def test_staff_reports_loads(self):
        """#131: Staff reports page loads"""
        self.create_staff_user()
        self.client.login(username='staffuser', password='Staff@123')
        resp = self.client.get(reverse('workforce:staff_reports'))
        self.assertEqual(resp.status_code, 200)


class DeliveryAppControlTests(WorkforceTestMixin, TestCase):
    """The staff console that turns per-client proof of delivery on."""

    def setUp(self):
        self.client = Client()
        self.create_staff_user()
        self.business = self.create_business(bid=9500, code='DAC1', name='Proof Co')
        self.client.login(username='staffuser', password='Staff@123')
        self.url = reverse('workforce:delivery_app_control')
        self.save_url = reverse('workforce:delivery_app_control_save')

    def test_page_lists_active_clients(self):
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Proof Co')

    def test_save_persists_the_rule(self):
        resp = self.client.post(self.save_url, {
            'business_id': self.business.business_id,
            'delivered': '1', 'failed': '1', 'kind': 'both', 'tracking': '1',
        })
        self.assertTrue(resp.json()['success'])
        self.business.refresh_from_db()
        self.assertTrue(self.business.pod_required_delivered)
        self.assertTrue(self.business.pod_required_failed)
        self.assertEqual(self.business.pod_kind, 'both')
        self.assertTrue(self.business.live_tracking_enabled)

    def test_save_toggles_live_tracking_on_its_own(self):
        # The tracking switch is independent of the proof rules.
        self.client.post(self.save_url, {
            'business_id': self.business.business_id,
            'delivered': '0', 'failed': '0', 'kind': 'photo', 'tracking': '1',
        })
        self.business.refresh_from_db()
        self.assertTrue(self.business.live_tracking_enabled)
        self.assertFalse(self.business.pod_required_delivered)

        self.client.post(self.save_url, {
            'business_id': self.business.business_id,
            'delivered': '0', 'failed': '0', 'kind': 'photo', 'tracking': '0',
        })
        self.business.refresh_from_db()
        self.assertFalse(self.business.live_tracking_enabled)

    def test_save_turns_the_rule_back_off(self):
        self.business.pod_required_delivered = True
        self.business.save(update_fields=['pod_required_delivered'])
        self.client.post(self.save_url, {
            'business_id': self.business.business_id,
            'delivered': '0', 'failed': '0', 'kind': 'photo',
        })
        self.business.refresh_from_db()
        self.assertFalse(self.business.pod_required_delivered)

    def test_save_rejects_an_unknown_proof_type(self):
        resp = self.client.post(self.save_url, {
            'business_id': self.business.business_id,
            'delivered': '1', 'failed': '0', 'kind': 'fingerprint',
        })
        self.assertFalse(resp.json()['success'])
        self.business.refresh_from_db()
        self.assertFalse(self.business.pod_required_delivered)

    def test_only_filter_shows_clients_with_a_rule(self):
        quiet = self.create_business(bid=9501, code='DAC2', name='No Rule Co')
        quiet.live_tracking_enabled = False
        quiet.save(update_fields=['live_tracking_enabled'])
        self.business.pod_required_failed = True
        self.business.live_tracking_enabled = False
        self.business.save(update_fields=['pod_required_failed', 'live_tracking_enabled'])
        resp = self.client.get(self.url, {'only': 'on'})
        self.assertContains(resp, 'Proof Co')
        self.assertNotContains(resp, quiet.business_name)

    def test_only_filter_also_catches_a_tracking_only_client(self):
        quiet = self.create_business(bid=9502, code='DAC3', name='No Rule Co')
        quiet.live_tracking_enabled = False
        quiet.save(update_fields=['live_tracking_enabled'])
        self.business.live_tracking_enabled = True
        self.business.save(update_fields=['live_tracking_enabled'])
        resp = self.client.get(self.url, {'only': 'on'})
        self.assertContains(resp, 'Proof Co')
        self.assertNotContains(resp, quiet.business_name)

    def test_non_staff_cannot_reach_the_console(self):
        self.client.logout()
        self.create_non_staff_user()
        self.client.login(username='regularuser', password='Regular@123')
        self.assertEqual(self.client.get(self.url).status_code, 302)
        self.assertEqual(self.client.post(self.save_url, {}).status_code, 302)


class DeliveryAppControlSaveAllTests(WorkforceTestMixin, TestCase):
    """One Save for the page — but only for the rows the user actually edited."""

    def setUp(self):
        self.client = Client()
        self.create_staff_user()
        self.a = self.create_business(bid=9600, code='SA1', name='Alpha Co')
        self.b = self.create_business(bid=9601, code='SA2', name='Beta Co')
        self.client.login(username='staffuser', password='Staff@123')
        self.url = reverse('workforce:delivery_app_control_save_all')

    def _post(self, rows):
        return self.client.post(
            self.url, data=json.dumps({'rows': rows}), content_type='application/json')

    @staticmethod
    def _row(biz, delivered=False, failed=False, kind='photo', tracking=False):
        return {'business_id': biz.business_id, 'delivered': delivered,
                'failed': failed, 'kind': kind, 'tracking': tracking}

    def test_saves_several_rows_at_once(self):
        resp = self._post([
            self._row(self.a, delivered=True, kind='both'),
            self._row(self.b, failed=True, tracking=True),
        ])
        payload = resp.json()
        self.assertTrue(payload['success'])
        self.assertEqual(payload['saved'], 2)
        self.a.refresh_from_db(); self.b.refresh_from_db()
        self.assertTrue(self.a.pod_required_delivered)
        self.assertEqual(self.a.pod_kind, 'both')
        self.assertTrue(self.b.pod_required_failed)
        self.assertTrue(self.b.live_tracking_enabled)

    def test_untouched_clients_are_never_rewritten(self):
        # The whole reason the page sends only dirty rows: a client left alone keeps
        # the rule it had, even while its neighbour on the same page is edited.
        self.b.pod_required_delivered = True
        self.b.pod_kind = 'signature'
        self.b.save(update_fields=['pod_required_delivered', 'pod_kind'])

        self._post([self._row(self.a, tracking=True)])

        self.b.refresh_from_db()
        self.assertTrue(self.b.pod_required_delivered)
        self.assertEqual(self.b.pod_kind, 'signature')

    def test_unchanged_row_reports_as_not_saved(self):
        resp = self._post([self._row(self.a)])   # all defaults — nothing differs
        self.assertEqual(resp.json()['saved'], 0)
        self.assertEqual(resp.json()['submitted'], 1)

    def test_turning_a_rule_back_off_counts_as_a_change(self):
        self.a.live_tracking_enabled = True
        self.a.save(update_fields=['live_tracking_enabled'])
        self.assertEqual(self._post([self._row(self.a)]).json()['saved'], 1)
        self.a.refresh_from_db()
        self.assertFalse(self.a.live_tracking_enabled)

    def test_a_bad_proof_type_rejects_the_whole_batch(self):
        resp = self._post([
            self._row(self.a, delivered=True),
            self._row(self.b, delivered=True, kind='fingerprint'),
        ])
        self.assertFalse(resp.json()['success'])
        self.a.refresh_from_db()
        self.assertFalse(self.a.pod_required_delivered)   # nothing written

    def test_an_unknown_client_rejects_the_whole_batch(self):
        resp = self._post([
            self._row(self.a, delivered=True),
            {'business_id': 999999, 'delivered': True, 'failed': False,
             'kind': 'photo', 'tracking': False},
        ])
        self.assertFalse(resp.json()['success'])
        self.a.refresh_from_db()
        self.assertFalse(self.a.pod_required_delivered)

    def test_empty_and_malformed_payloads(self):
        self.assertFalse(self._post([]).json()['success'])
        self.assertFalse(self.client.post(
            self.url, data='not json', content_type='application/json').json()['success'])
        self.assertFalse(self._post([self._row(self.a)] * 101).json()['success'])

    def test_get_is_rejected(self):
        self.assertFalse(self.client.get(self.url).json()['success'])

    def test_non_staff_cannot_bulk_save(self):
        self.client.logout()
        self.create_non_staff_user()
        self.client.login(username='regularuser', password='Regular@123')
        self.assertEqual(self._post([self._row(self.a, delivered=True)]).status_code, 302)
        self.a.refresh_from_db()
        self.assertFalse(self.a.pod_required_delivered)


class DashboardOnlineDriversTests(WorkforceTestMixin, TestCase):
    """The dashboard tile says "Online", so it must count availability, not approval.

    It used to read driver_status='approved', which made a fleet of five approved
    drivers show as five online while one was actually working.
    """

    def setUp(self):
        self.client = Client()
        self.create_staff_user()
        self.client.login(username='staffuser', password='Staff@123')
        self.url = reverse('workforce:wf_dashboard')

    def _driver(self, did, availability, status='approved'):
        driver = self.create_driver(did=did, status=status, code=f'ONL{did}')
        # .update() so the availability signals do not rewrite what the test set up
        fleet_models.Driver.objects.filter(pk=driver.pk).update(
            driver_availability=availability)
        return driver

    def _ctx(self):
        return self.client.get(self.url).context

    def test_offline_drivers_are_not_counted_as_online(self):
        self._driver(7801, 'available')
        self._driver(7802, 'offline')
        self._driver(7803, 'offline')
        ctx = self._ctx()
        self.assertEqual(ctx['active_drivers'], 3)     # approved fleet size
        self.assertEqual(ctx['online_drivers'], 1)     # actually on shift

    def test_on_break_and_returning_still_count_as_online(self):
        # A driver on a break or driving back from a drop is still working.
        self._driver(7811, 'on_break')
        self._driver(7812, 'returning')
        self._driver(7813, 'on_delivery')
        self._driver(7814, 'offline')
        self.assertEqual(self._ctx()['online_drivers'], 3)

    def test_unapproved_drivers_never_count(self):
        # A pending applicant with a stale availability row is not part of the fleet.
        self._driver(7821, 'available', status='pending')
        self._driver(7822, 'available', status='suspended')
        ctx = self._ctx()
        self.assertEqual(ctx['online_drivers'], 0)
        self.assertEqual(ctx['active_drivers'], 0)

    def test_tile_renders_the_online_figure(self):
        self._driver(7831, 'available')
        self._driver(7832, 'offline')
        resp = self.client.get(self.url)
        self.assertContains(resp, 'of 2')          # fleet size kept beside it
        self.assertEqual(resp.context['online_drivers'], 1)


class CrmDriverMapTests(WorkforceTestMixin, TestCase):
    """The recruitment map — one pin per applicant, at the spot they applied from."""

    def setUp(self):
        from crm.models import Lead
        self.Lead = Lead
        self.client = Client()
        self.create_staff_user()
        self.client.login(username='staffuser', password='Staff@123')
        self.url = reverse('workforce:crm_driver_map')

    def _driver(self, did, lat=None, lng=None):
        driver = self.create_driver(did=did, code=f'MAP{did}')
        if lat is not None:
            driver.driver_meta = {'registration_location': {
                'lat': lat, 'lng': lng, 'accuracy_m': 20,
                'captured_at': '2026-08-18T09:00:00Z'}}
            driver.save(update_fields=['driver_meta'])
        return driver

    def _lead(self, name, driver=None, category=None, stage='new_app'):
        return self.Lead.objects.create(
            source=self.Lead.SOURCE_MANUAL,
            category=category or self.Lead.CATEGORY_DRIVER,
            contact_name=name, phone='50000000', stage=stage, driver=driver)

    def test_pins_only_for_leads_with_a_captured_location(self):
        self._lead('Has location', self._driver(7901, 25.28, 51.53))
        self._lead('No location', self._driver(7902))
        self._lead('No application at all')            # no driver FK
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)
        points = resp.context['map_points']
        self.assertEqual(len(points), 1)
        self.assertEqual(points[0]['name'], 'Has location')
        self.assertEqual(resp.context['no_location_count'], 1)
        self.assertEqual(resp.context['no_driver_count'], 1)

    def test_business_leads_never_appear(self):
        self._lead('A driver', self._driver(7911, 25.28, 51.53))
        self._lead('A client', self._driver(7912, 25.29, 51.54),
                   category=self.Lead.CATEGORY_BUSINESS)
        self.assertEqual(len(self.client.get(self.url).context['map_points']), 1)

    def test_stage_filter_narrows_the_pins(self):
        self._lead('Stage A', self._driver(7921, 25.28, 51.53), stage='new_app')
        self._lead('Stage B', self._driver(7922, 25.29, 51.54), stage='contacted')
        self.assertEqual(len(self.client.get(self.url).context['map_points']), 2)
        filtered = self.client.get(self.url, {'stage': 'new_app'}).context['map_points']
        self.assertEqual([p['name'] for p in filtered], ['Stage A'])

    def test_a_pin_outside_qatar_is_kept_but_flagged(self):
        # Applicants do apply from abroad; they stay on the map, the framing excludes them.
        self._lead('Abroad', self._driver(7931, 19.07, 72.87))     # Mumbai
        resp = self.client.get(self.url)
        self.assertEqual(resp.context['outside_count'], 1)
        self.assertFalse(resp.context['map_points'][0]['in_qatar'])

    def test_a_broken_coordinate_is_dropped_not_plotted(self):
        driver = self.create_driver(did=7941, code='MAP7941')
        driver.driver_meta = {'registration_location': {'lat': 'north', 'lng': None}}
        driver.save(update_fields=['driver_meta'])
        self._lead('Junk coords', driver)
        resp = self.client.get(self.url)
        self.assertEqual(resp.context['map_points'], [])
        self.assertEqual(resp.context['no_location_count'], 1)

    def test_search_filters_the_map(self):
        self._lead('Findable', self._driver(7951, 25.28, 51.53))
        self._lead('Other', self._driver(7952, 25.29, 51.54))
        points = self.client.get(self.url, {'search': 'Findable'}).context['map_points']
        self.assertEqual([p['name'] for p in points], ['Findable'])

    def test_pin_links_to_its_lead(self):
        lead = self._lead('Linked', self._driver(7961, 25.28, 51.53))
        point = self.client.get(self.url).context['map_points'][0]
        self.assertEqual(point['url'], reverse('workforce:crm_lead_detail', args=[lead.id]))

    def test_non_staff_cannot_open_the_map(self):
        self.client.logout()
        self.create_non_staff_user()
        self.client.login(username='regularuser', password='Regular@123')
        self.assertEqual(self.client.get(self.url).status_code, 302)
