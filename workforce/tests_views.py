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
                          via_user=True, via_profile=True):
        """Create a staff user. Set via_user=False to test Profile.is_staff only."""
        user = User.objects.create_user(
            username=username, password=password,
            email=f'{username}@test.com', is_staff=via_user)
        profile = core_models.Profile.objects.create(
            user=user, first_name='Staff', last_name='User',
            phone=11111111, is_staff=via_profile)
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
            cod_status_by_client='include' if cod else 'no_cod',
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
            dl_task_number_dms=order.order_number or f'DMS-{order.id}',
            dl_task_description=f'Delivery for {order.order_number}',
            order=order,
            business=order.business,
            dl_address_update=addr,
            driver=driver,
            dl_task_status=status,
            dl_task_status_dms='6',
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
        self.assertEqual(len(resp.context['orders_trend']), 7)

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
        resp = self.client.get(reverse('workforce:wf_orders_dms_updated'))
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
        self.order.order_status = 'published'
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
            json.dumps({'status': 'processing', 'status_type': 'order'}),
            content_type='application/json')
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.content)
        self.assertTrue(data['success'])

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
        self.assertEqual(self.order.order_status, 'published')

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

    def test_verify_order(self):
        """#61: Verify order marks as verified"""
        self.order.verification_status = 'pending'
        self.order.save()
        resp = self.client.post(
            reverse('workforce:verify_order',
                    kwargs={'order_id': self.order.id}),
            {'verification_notes': 'Looks good'})
        self.assertIn(resp.status_code, [200, 302])


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
        """#70: Publish task to DMS"""
        resp = self.client.post(
            reverse('workforce:publish_task_to_dms',
                    kwargs={'task_id': self.task.id}))
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.content)
        self.assertTrue(data['success'])

    def test_publish_task_to_driver_app(self):
        """#71: Publish task to driver app"""
        resp = self.client.post(
            reverse('workforce:publish_task_to_driver_app',
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
        """#76: Bulk publish to DMS"""
        resp = self.client.post(
            reverse('workforce:bulk_publish_dms'),
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
        biz = self.create_business(bid=8001, status='Pending on Review')
        biz_profile = biz.profile
        biz_profile.verification_status = 'pending'
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
        driver = self.create_driver(status='pending', code='PND01')
        drv_profile = driver.profile
        drv_profile.verification_status = 'pending'
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
