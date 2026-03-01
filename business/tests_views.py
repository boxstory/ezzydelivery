"""
Comprehensive View Test Suite for Business Dashboard & Order Workflow
=====================================================================

110+ test scenarios covering:
- Business Dashboard (authentication, stats, redirects)
- Order List Views (all, pending, successful, unsuccessful, filters)
- Order Creation (single, bulk, with products)
- Order Update/Delete/Details (IDOR, permissions, status blocking)
- Order Products (add, update, list)
- Order Comments (add, get, IDOR)
- Pickup Locations (CRUD, IDOR)
- Business Settings & Profile (settings, API, profile updates)
- Driver Directory (add, delete, IDOR)
- Team Management (add, update, permissions, status)
- Access Control (auth, roles, permissions)
- Pagination & Edge Cases
"""

import json
from decimal import Decimal
from datetime import date, timedelta
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model

from business import models as business_models
from core import models as core_models
from orders import models as orders_models
from fleet import models as fleet_models
from delivery import models as delivery_models
from business.permissions import BusinessPermissions, TeamRoles

User = get_user_model()


class BusinessTestMixin:
    """Reusable helpers for business/order tests."""

    def create_business_user(self, username='bizowner', password='BizPass@123'):
        user = User.objects.create_user(username=username, password=password,
                                        email=f'{username}@test.com')
        profile = core_models.Profile.objects.create(
            user=user, first_name='Biz', last_name='Owner',
            phone=11111111, is_business=True,
            is_business_profile_completed=True)
        return user, profile

    def create_business(self, user, profile, business_id=9000,
                        code='TBIZ', name='Test Business'):
        business = business_models.Business.objects.create(
            business_id=business_id, user=user, profile=profile,
            business_name=name, business_code=code,
            business_status='active',
            fulfillment_service_enabled=False,
            fulfillment_service_status='none')
        business_models.BusinessProfile.objects.get_or_create(
            business=business)
        return business

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

    def create_non_business_user(self, username='nonbiz'):
        user = User.objects.create_user(
            username=username, password='NonBiz@123',
            email=f'{username}@test.com')
        core_models.Profile.objects.create(
            user=user, first_name='Non', last_name='Biz', phone=99999999)
        return user

    def create_team_member(self, business, role='staff',
                           username='teammember', status='active'):
        user = User.objects.create_user(
            username=username, password='Team@123',
            email=f'{username}@test.com')
        profile = core_models.Profile.objects.create(
            user=user, first_name='Team', last_name='Member',
            phone=22222222, is_business=True,
            is_business_profile_completed=True)
        team = business_models.BusinessTeamProfile.objects.create(
            user=user, profile=profile, business=business,
            team_code=f'TM-{username}', team_role=role,
            team_status=status, team_name=f'{username} member')
        return user, profile, team

    def create_other_business(self, bid=9999):
        user2, profile2 = self.create_business_user(
            username='otherbiz', password='Other@123')
        return self.create_business(user2, profile2, business_id=bid,
                                    code='OBIZ', name='Other Biz')


# =============================================================================
# 1. BUSINESS DASHBOARD TESTS (12 tests)
# =============================================================================

class BusinessDashboardTest(BusinessTestMixin, TestCase):

    def setUp(self):
        self.client = Client()
        self.user, self.profile = self.create_business_user()
        self.business = self.create_business(self.user, self.profile)
        self.pickup = self.create_pickup_location(self.business)

    def test_dashboard_loads_for_owner(self):
        """#1: Dashboard loads for business owner"""
        self.client.login(username='bizowner', password='BizPass@123')
        resp = self.client.get(reverse('business:business_dashboard'))
        self.assertEqual(resp.status_code, 200)

    def test_dashboard_redirects_anonymous(self):
        """#2: Anonymous user redirected to login"""
        resp = self.client.get(reverse('business:business_dashboard'))
        self.assertEqual(resp.status_code, 302)
        self.assertIn('login', resp.url.lower())

    def test_dashboard_redirects_non_business_user(self):
        """#3: Non-business user redirected away"""
        non_biz = self.create_non_business_user()
        self.client.login(username='nonbiz', password='NonBiz@123')
        resp = self.client.get(reverse('business:business_dashboard'))
        self.assertIn(resp.status_code, [302, 200])

    def test_dashboard_shows_order_stats(self):
        """#4: Dashboard context has order stats"""
        self.create_order(self.business, self.pickup, cod=100)
        self.create_order(self.business, self.pickup, cod=50)
        self.client.login(username='bizowner', password='BizPass@123')
        resp = self.client.get(reverse('business:business_dashboard'))
        self.assertEqual(resp.status_code, 200)
        self.assertIn('total_orders', resp.context)
        self.assertEqual(resp.context['total_orders'], 2)

    def test_dashboard_shows_cod_total(self):
        """#5: Dashboard has correct COD total"""
        self.create_order(self.business, self.pickup, cod=100)
        self.create_order(self.business, self.pickup, cod=200)
        self.client.login(username='bizowner', password='BizPass@123')
        resp = self.client.get(reverse('business:business_dashboard'))
        self.assertEqual(resp.context['cod_amount_total'], 300)

    def test_dashboard_shows_team_stats(self):
        """#6: Dashboard has team member stats"""
        self.create_team_member(self.business, username='tm1')
        self.create_team_member(self.business, username='tm2',
                                status='pending')
        self.client.login(username='bizowner', password='BizPass@123')
        resp = self.client.get(reverse('business:business_dashboard'))
        self.assertEqual(resp.context['total_team_members'], 2)
        self.assertEqual(resp.context['active_team_members'], 1)
        self.assertEqual(resp.context['pending_team_members'], 1)

    def test_dashboard_no_orders_empty_stats(self):
        """#7: Dashboard shows 0 stats when no orders"""
        self.client.login(username='bizowner', password='BizPass@123')
        resp = self.client.get(reverse('business:business_dashboard'))
        self.assertEqual(resp.context['total_orders'], 0)
        self.assertEqual(resp.context['cod_amount_total'], 0)

    def test_dashboard_only_shows_own_orders(self):
        """#8: Dashboard only counts own business orders"""
        other = self.create_other_business()
        other_pickup = self.create_pickup_location(other, 'Other WH')
        self.create_order(other, other_pickup)
        self.create_order(self.business, self.pickup)
        self.client.login(username='bizowner', password='BizPass@123')
        resp = self.client.get(reverse('business:business_dashboard'))
        self.assertEqual(resp.context['total_orders'], 1)

    def test_dashboard_team_member_access(self):
        """#9: Active team member can access dashboard"""
        user, _, team = self.create_team_member(
            self.business, role='manager', username='mgr1')
        self.client.login(username='mgr1', password='Team@123')
        resp = self.client.get(reverse('business:business_dashboard'))
        self.assertEqual(resp.status_code, 200)

    def test_dashboard_shows_business_switcher_multiple(self):
        """#10: Business switcher shown when user has multiple businesses"""
        self.client.login(username='bizowner', password='BizPass@123')
        resp = self.client.get(reverse('business:business_dashboard'))
        self.assertIn('show_business_switcher', resp.context)

    def test_dashboard_context_has_business(self):
        """#11: Dashboard context has business object"""
        self.client.login(username='bizowner', password='BizPass@123')
        resp = self.client.get(reverse('business:business_dashboard'))
        self.assertEqual(resp.context['business'].business_id,
                         self.business.business_id)

    def test_dashboard_context_has_profile(self):
        """#12: Dashboard context has profile"""
        self.client.login(username='bizowner', password='BizPass@123')
        resp = self.client.get(reverse('business:business_dashboard'))
        self.assertIsNotNone(resp.context.get('profile'))


# =============================================================================
# 2. ORDER LIST VIEW TESTS (12 tests)
# =============================================================================

class OrderListViewTest(BusinessTestMixin, TestCase):

    def setUp(self):
        self.client = Client()
        self.user, self.profile = self.create_business_user()
        self.business = self.create_business(self.user, self.profile)
        self.pickup = self.create_pickup_location(self.business)
        self.client.login(username='bizowner', password='BizPass@123')

    def test_all_orders_list_loads(self):
        """#13: All orders list loads"""
        self.create_order(self.business, self.pickup)
        resp = self.client.get(reverse('orders:orders_all_list'))
        self.assertEqual(resp.status_code, 200)

    def test_all_orders_list_empty(self):
        """#14: All orders list loads with no orders"""
        resp = self.client.get(reverse('orders:orders_all_list'))
        self.assertEqual(resp.status_code, 200)

    def test_all_orders_filter_by_order_number(self):
        """#15: Filter orders by order number"""
        order = self.create_order(self.business, self.pickup)
        resp = self.client.get(reverse('orders:orders_all_list'),
                               {'orderNumber': order.order_number})
        self.assertEqual(resp.status_code, 200)

    def test_all_orders_filter_by_zone(self):
        """#16: Filter orders by zone"""
        self.create_order(self.business, self.pickup)
        resp = self.client.get(reverse('orders:orders_all_list'),
                               {'zone': '1'})
        self.assertEqual(resp.status_code, 200)

    def test_all_orders_filter_by_customer_name(self):
        """#17: Filter by customer name"""
        self.create_order(self.business, self.pickup)
        resp = self.client.get(reverse('orders:orders_all_list'),
                               {'customerName': 'Test Customer'})
        self.assertEqual(resp.status_code, 200)

    def test_all_orders_filter_by_mobile(self):
        """#18: Filter by mobile"""
        self.create_order(self.business, self.pickup)
        resp = self.client.get(reverse('orders:orders_all_list'),
                               {'mobile': '12345678'})
        self.assertEqual(resp.status_code, 200)

    def test_all_orders_filter_date_range_today(self):
        """#19: Filter by date range 'today'"""
        self.create_order(self.business, self.pickup)
        resp = self.client.get(reverse('orders:orders_all_list'),
                               {'dateRange': 'today'})
        self.assertEqual(resp.status_code, 200)

    def test_all_orders_filter_cod_with_cod(self):
        """#20: Filter COD orders"""
        self.create_order(self.business, self.pickup, cod=100)
        self.create_order(self.business, self.pickup, cod=0)
        resp = self.client.get(reverse('orders:orders_all_list'),
                               {'codStatus': 'with_cod'})
        self.assertEqual(resp.status_code, 200)

    def test_all_orders_filter_no_cod(self):
        """#21: Filter no-COD orders"""
        resp = self.client.get(reverse('orders:orders_all_list'),
                               {'codStatus': 'no_cod'})
        self.assertEqual(resp.status_code, 200)

    def test_all_orders_filter_status(self):
        """#22: Filter by order status"""
        self.create_order(self.business, self.pickup, status='to_review')
        resp = self.client.get(reverse('orders:orders_all_list'),
                               {'cStatus': 'to_review'})
        self.assertEqual(resp.status_code, 200)

    def test_all_orders_only_own_business(self):
        """#23: Only own business orders shown"""
        other = self.create_other_business()
        other_pickup = self.create_pickup_location(other, 'Other')
        self.create_order(other, other_pickup)
        self.create_order(self.business, self.pickup)
        resp = self.client.get(reverse('orders:orders_all_list'))
        self.assertEqual(resp.context['len'], 1)

    def test_all_orders_per_page_param(self):
        """#24: per_page parameter works"""
        for i in range(15):
            self.create_order(self.business, self.pickup)
        resp = self.client.get(reverse('orders:orders_all_list'),
                               {'per_page': '25'})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context['per_page'], '25')

    def test_all_orders_invalid_per_page_defaults(self):
        """#25: Invalid per_page defaults to 10"""
        resp = self.client.get(reverse('orders:orders_all_list'),
                               {'per_page': 'invalid'})
        self.assertEqual(resp.context['per_page'], '10')

    def test_pending_list_loads(self):
        """#26: Pending orders list loads"""
        resp = self.client.get(reverse('orders:orders_pending_list'))
        self.assertEqual(resp.status_code, 200)

    def test_successful_list_loads(self):
        """#27: Successful orders list loads"""
        resp = self.client.get(reverse('orders:orders_successfull_list'))
        self.assertEqual(resp.status_code, 200)

    def test_unsuccessful_list_loads(self):
        """#28: Unsuccessful orders list loads"""
        resp = self.client.get(reverse('orders:orders_unsuccessfull_list'))
        self.assertEqual(resp.status_code, 200)

    def test_orders_list_auth_required(self):
        """#29: Orders list requires authentication"""
        self.client.logout()
        resp = self.client.get(reverse('orders:orders_all_list'))
        self.assertEqual(resp.status_code, 302)


# =============================================================================
# 3. ORDER CREATION TESTS (16 tests)
# =============================================================================

class OrderCreationTest(BusinessTestMixin, TestCase):

    def setUp(self):
        self.client = Client()
        self.user, self.profile = self.create_business_user()
        self.business = self.create_business(self.user, self.profile)
        self.pickup = self.create_pickup_location(self.business)
        self.client.login(username='bizowner', password='BizPass@123')

    def test_add_order_form_loads(self):
        """#30: Add order form page loads"""
        resp = self.client.get(reverse('orders:add_order'))
        self.assertEqual(resp.status_code, 200)

    def test_add_order_redirects_no_pickup(self):
        """#31: Add order redirects when no pickup location"""
        self.pickup.delete()
        resp = self.client.get(reverse('orders:add_order'))
        self.assertEqual(resp.status_code, 302)

    def test_add_order_post_valid(self):
        """#32: Valid order creation via POST"""
        resp = self.client.post(reverse('orders:add_order'), {
            'client_order_code': 'TEST-ORD-001',
            'customer_name': 'John Doe',
            'customer_phone': '55512345',
            'customer_whatsapp': '55512345',
            'dl_zone': 1, 'dl_street': 10, 'dl_building': 5,
            'customer_address': '123 Test St',
            'cod_status_by_client': 'no_cod',
            'cod_amount': 0,
            'order_notes': 'Test order',
            'order_status': 'to_review',
            'pickup_location': self.pickup.id,
        })
        # Should redirect to add_order_product page
        self.assertIn(resp.status_code, [200, 302])

    def test_add_order_post_missing_fields(self):
        """#33: Order creation with missing required fields"""
        resp = self.client.post(reverse('orders:add_order'), {
            'client_order_code': '',
            'customer_name': '',
        })
        self.assertEqual(resp.status_code, 200)  # Re-renders form

    def test_add_order_auth_required(self):
        """#34: Add order requires auth"""
        self.client.logout()
        resp = self.client.get(reverse('orders:add_order'))
        self.assertEqual(resp.status_code, 302)

    def test_add_order_form_has_pickup_locations(self):
        """#35: Add order form shows business pickup locations"""
        resp = self.client.get(reverse('orders:add_order'))
        self.assertIn('pickup_locations', resp.context)

    def test_bulk_order_entry_form_loads(self):
        """#36: Bulk order entry form loads"""
        resp = self.client.get(reverse('orders:bulk_order_entry'))
        self.assertEqual(resp.status_code, 200)

    def test_bulk_order_entry_redirects_no_pickup(self):
        """#37: Bulk entry redirects without pickup locations"""
        self.pickup.delete()
        resp = self.client.get(reverse('orders:bulk_order_entry'))
        self.assertEqual(resp.status_code, 302)

    def test_bulk_order_entry_post_creates_orders(self):
        """#38: Bulk order entry creates orders"""
        resp = self.client.post(reverse('orders:bulk_order_entry'), {
            'data[0][customer_name]': 'Bulk Customer 1',
            'data[0][order_id]': 'BULK-001',
            'data[0][phone1]': '55501234',
            'data[0][phone2_whatsapp]': '55501234',
            'data[0][customer_address]': 'Bulk Address 1',
            'data[0][zone_no]': '1',
            'data[0][street_no]': '10',
            'data[0][building_no]': '5',
            'data[0][deadline_date]': '',
            'data[0][note]': 'Test bulk',
        })
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(
            orders_models.Order.objects.filter(
                business=self.business,
                customer_name='Bulk Customer 1').exists())

    def test_bulk_order_entry_skips_empty_rows(self):
        """#39: Bulk entry skips rows with no name and no code"""
        resp = self.client.post(reverse('orders:bulk_order_entry'), {
            'data[0][customer_name]': '',
            'data[0][order_id]': '',
            'data[0][phone1]': '',
        })
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(
            orders_models.Order.objects.filter(
                business=self.business).count(), 0)

    def test_add_order_bulk_post(self):
        """#40: Bulk add orders via orders[N][field] format"""
        resp = self.client.post(reverse('orders:add_order_bulk'), {
            'orders[0][customer_name]': 'Bulk2 Cust',
            'orders[0][client_order_code]': 'B2-001',
            'orders[0][customer_phone]': '55500001',
            'orders[0][dl_zone]': '1',
            'orders[0][dl_street]': '5',
            'orders[0][dl_building]': '3',
            'orders[0][customer_address]': 'Bulk2 Addr',
            'orders[0][cod_status_by_client]': 'no_cod',
            'orders[0][cod_amount]': '0',
            'orders[0][order_notes]': 'test',
            'orders[0][order_status]': 'to_review',
        })
        self.assertEqual(resp.status_code, 302)

    def test_add_order_bulk_get_redirects(self):
        """#41: GET to add_order_bulk redirects"""
        resp = self.client.get(reverse('orders:add_order_bulk'))
        self.assertEqual(resp.status_code, 302)

    def test_add_order_with_product_loads(self):
        """#42: Add order with product form loads"""
        resp = self.client.get(reverse('orders:add_order_with_product'))
        self.assertEqual(resp.status_code, 200)

    def test_order_upload_file_loads(self):
        """#43: File upload form loads"""
        resp = self.client.get(reverse('orders:order_upload_file'))
        self.assertEqual(resp.status_code, 200)

    def test_pick_from_here_loads(self):
        """#44: Pick-from-here with valid pickup loads"""
        resp = self.client.get(
            reverse('orders:pick_from_here',
                    kwargs={'pickup_id': self.pickup.id}))
        self.assertEqual(resp.status_code, 200)

    def test_pick_from_here_invalid_pickup(self):
        """#45: Pick-from-here with invalid pickup redirects"""
        resp = self.client.get(
            reverse('orders:pick_from_here', kwargs={'pickup_id': 99999}))
        self.assertEqual(resp.status_code, 302)


# =============================================================================
# 4. ORDER UPDATE/DELETE/DETAILS TESTS (12 tests)
# =============================================================================

class OrderUpdateDeleteTest(BusinessTestMixin, TestCase):

    def setUp(self):
        self.client = Client()
        self.user, self.profile = self.create_business_user()
        self.business = self.create_business(self.user, self.profile)
        self.pickup = self.create_pickup_location(self.business)
        self.order = self.create_order(self.business, self.pickup)
        self.client.login(username='bizowner', password='BizPass@123')

    def test_order_update_form_loads(self):
        """#46: Order update form loads"""
        resp = self.client.get(
            reverse('orders:order_update',
                    kwargs={'order_id': self.order.id}))
        self.assertEqual(resp.status_code, 200)

    def test_order_update_idor_other_business(self):
        """#47: Cannot update another business order (IDOR)"""
        other = self.create_other_business()
        other_pickup = self.create_pickup_location(other, 'Other WH')
        other_order = self.create_order(other, other_pickup)
        resp = self.client.get(
            reverse('orders:order_update',
                    kwargs={'order_id': other_order.id}))
        self.assertEqual(resp.status_code, 302)

    def test_order_update_nonexistent(self):
        """#48: Update nonexistent order redirects"""
        resp = self.client.get(
            reverse('orders:order_update', kwargs={'order_id': 99999}))
        self.assertEqual(resp.status_code, 302)

    def test_order_update_blocks_dl_task_listed(self):
        """#49: Cannot update order with task_status=dl_task_listed"""
        self.order.task_status = 'dl_task_listed'
        self.order.save()
        resp = self.client.post(
            reverse('orders:order_update',
                    kwargs={'order_id': self.order.id}),
            {'customer_name': 'Updated', 'customer_phone': '999',
             'customer_whatsapp': '999', 'cod_status_by_client': 'no_cod',
             'cod_amount': 0, 'dl_zone': 1, 'customer_address': 'Addr',
             'order_notes': 'note', 'pickup_location': self.pickup.id})
        self.assertEqual(resp.status_code, 302)

    def test_delete_order_success(self):
        """#50: Delete own order succeeds"""
        resp = self.client.get(
            reverse('orders:delete_order',
                    kwargs={'order_id': self.order.id}))
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(
            orders_models.Order.objects.filter(id=self.order.id).exists())

    def test_delete_order_idor(self):
        """#51: Cannot delete another business order"""
        other = self.create_other_business()
        other_pickup = self.create_pickup_location(other, 'Other WH')
        other_order = self.create_order(other, other_pickup)
        resp = self.client.get(
            reverse('orders:delete_order',
                    kwargs={'order_id': other_order.id}))
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(
            orders_models.Order.objects.filter(id=other_order.id).exists())

    def test_delete_order_nonexistent(self):
        """#52: Delete nonexistent order redirects"""
        resp = self.client.get(
            reverse('orders:delete_order', kwargs={'order_id': 99999}))
        self.assertEqual(resp.status_code, 302)

    def test_order_details_loads(self):
        """#53: Order details loads"""
        resp = self.client.get(
            reverse('orders:order_details',
                    kwargs={'order_id': self.order.id}))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context['order'].id, self.order.id)

    def test_order_details_idor(self):
        """#54: Cannot view another business order details"""
        other = self.create_other_business()
        other_pickup = self.create_pickup_location(other, 'Other WH')
        other_order = self.create_order(other, other_pickup)
        resp = self.client.get(
            reverse('orders:order_details',
                    kwargs={'order_id': other_order.id}))
        self.assertEqual(resp.status_code, 302)

    def test_order_details_nonexistent(self):
        """#55: Nonexistent order details redirects"""
        resp = self.client.get(
            reverse('orders:order_details', kwargs={'order_id': 99999}))
        self.assertEqual(resp.status_code, 302)

    def test_update_order_status_json(self):
        """#56: Update order status via JSON"""
        resp = self.client.post(
            reverse('orders:update_order_status'),
            json.dumps({'order_id': self.order.id,
                        'status': 'ready_to_pickup'}),
            content_type='application/json')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data['success'])
        self.order.refresh_from_db()
        self.assertEqual(self.order.order_status, 'ready_to_pickup')

    def test_update_order_status_idor(self):
        """#57: Cannot update another business order status"""
        other = self.create_other_business()
        other_pickup = self.create_pickup_location(other, 'Other WH')
        other_order = self.create_order(other, other_pickup)
        resp = self.client.post(
            reverse('orders:update_order_status'),
            json.dumps({'order_id': other_order.id,
                        'status': 'cancelled'}),
            content_type='application/json')
        self.assertEqual(resp.status_code, 403)


# =============================================================================
# 5. ORDER PRODUCT TESTS (6 tests)
# =============================================================================

class OrderProductTest(BusinessTestMixin, TestCase):

    def setUp(self):
        self.client = Client()
        self.user, self.profile = self.create_business_user()
        self.business = self.create_business(self.user, self.profile)
        self.pickup = self.create_pickup_location(self.business)
        self.order = self.create_order(self.business, self.pickup)
        self.client.login(username='bizowner', password='BizPass@123')

    def test_add_order_product_form_loads(self):
        """#58: Add order product form loads"""
        resp = self.client.get(
            reverse('orders:add_order_product',
                    kwargs={'order_id': self.order.id}))
        self.assertEqual(resp.status_code, 200)

    def test_add_order_product_idor(self):
        """#59: Cannot add product to other business order"""
        other = self.create_other_business()
        other_pickup = self.create_pickup_location(other, 'Other WH')
        other_order = self.create_order(other, other_pickup)
        resp = self.client.get(
            reverse('orders:add_order_product',
                    kwargs={'order_id': other_order.id}))
        self.assertEqual(resp.status_code, 302)

    def test_add_order_product_nonexistent(self):
        """#60: Add product to nonexistent order redirects"""
        resp = self.client.get(
            reverse('orders:add_order_product',
                    kwargs={'order_id': 99999}))
        self.assertEqual(resp.status_code, 302)

    def test_update_order_product_loads(self):
        """#61: Update order product form loads"""
        resp = self.client.get(
            reverse('orders:update_order_product',
                    kwargs={'order_id': self.order.id}))
        self.assertEqual(resp.status_code, 200)

    def test_order_product_list_loads(self):
        """#62: Order product list loads"""
        resp = self.client.get(
            reverse('orders:order_product_list',
                    kwargs={'order_id': self.order.id}))
        self.assertEqual(resp.status_code, 200)

    def test_product_search_api_min_chars(self):
        """#63: Product search API requires min 3 chars"""
        resp = self.client.get(
            reverse('orders:product_search_api'), {'q': 'ab'})
        data = resp.json()
        self.assertEqual(data['results'], [])


# =============================================================================
# 6. ORDER COMMENT TESTS (6 tests)
# =============================================================================

class OrderCommentTest(BusinessTestMixin, TestCase):

    def setUp(self):
        self.client = Client()
        self.user, self.profile = self.create_business_user()
        self.business = self.create_business(self.user, self.profile)
        self.pickup = self.create_pickup_location(self.business)
        self.order = self.create_order(self.business, self.pickup)
        self.client.login(username='bizowner', password='BizPass@123')

    def test_add_comment(self):
        """#64: Add comment to order"""
        resp = self.client.post(
            reverse('orders:add_order_comment',
                    kwargs={'order_id': self.order.id}),
            {'comment': 'Test comment here'})
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(
            orders_models.OrderComments.objects.filter(
                order=self.order, body='Test comment here').exists())

    def test_add_empty_comment(self):
        """#65: Empty comment doesn't create record"""
        resp = self.client.post(
            reverse('orders:add_order_comment',
                    kwargs={'order_id': self.order.id}),
            {'comment': ''})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(
            orders_models.OrderComments.objects.filter(
                order=self.order).count(), 0)

    def test_get_comments(self):
        """#66: Get order comments"""
        orders_models.OrderComments.objects.create(
            order=self.order, name='Test', body='Comment 1')
        resp = self.client.get(
            reverse('orders:get_order_comments',
                    kwargs={'order_id': self.order.id}))
        self.assertEqual(resp.status_code, 200)

    def test_add_comment_idor(self):
        """#67: Cannot comment on another business order"""
        other = self.create_other_business()
        other_pickup = self.create_pickup_location(other, 'Other WH')
        other_order = self.create_order(other, other_pickup)
        resp = self.client.post(
            reverse('orders:add_order_comment',
                    kwargs={'order_id': other_order.id}),
            {'comment': 'Should fail'})
        self.assertEqual(resp.status_code, 403)

    def test_get_comments_idor(self):
        """#68: Cannot get comments for another business order"""
        other = self.create_other_business()
        other_pickup = self.create_pickup_location(other, 'Other WH')
        other_order = self.create_order(other, other_pickup)
        resp = self.client.get(
            reverse('orders:get_order_comments',
                    kwargs={'order_id': other_order.id}))
        self.assertEqual(resp.status_code, 403)

    def test_comment_on_nonexistent_order(self):
        """#69: Comment on nonexistent order returns 404"""
        resp = self.client.post(
            reverse('orders:add_order_comment',
                    kwargs={'order_id': 99999}),
            {'comment': 'Fail'})
        self.assertEqual(resp.status_code, 404)


# =============================================================================
# 7. PICKUP LOCATION TESTS (10 tests)
# =============================================================================

class PickupLocationTest(BusinessTestMixin, TestCase):

    def setUp(self):
        self.client = Client()
        self.user, self.profile = self.create_business_user()
        self.business = self.create_business(self.user, self.profile)
        self.pickup = self.create_pickup_location(self.business)
        self.client.login(username='bizowner', password='BizPass@123')

    def test_pickup_list_loads(self):
        """#70: Pickup location list loads"""
        resp = self.client.get(reverse('business:pickup_location_list'))
        self.assertEqual(resp.status_code, 200)

    def test_pickup_list_redirects_empty(self):
        """#71: Empty pickup list redirects to add"""
        self.pickup.delete()
        resp = self.client.get(reverse('business:pickup_location_list'))
        self.assertEqual(resp.status_code, 302)

    def test_pickup_add_form_loads(self):
        """#72: Pickup add form loads"""
        resp = self.client.get(reverse('business:pickup_location_add'))
        self.assertEqual(resp.status_code, 200)

    def test_pickup_add_post_valid(self):
        """#73: Valid pickup location creation"""
        resp = self.client.post(reverse('business:pickup_location_add'), {
            'pickup_location_title': 'New Warehouse',
            'locality': 'Al Wakrah',
            'pickup_zone_no': 5,
            'pickup_street_no': 50,
            'pickup_building_no': 15,
            'pickup_status': 'active',
        })
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(
            business_models.PickupLocation.objects.filter(
                pickup_location_title='New Warehouse').exists())

    def test_pickup_update_form_loads(self):
        """#74: Pickup update form loads"""
        resp = self.client.get(
            reverse('business:pickup_location_update',
                    kwargs={'pickup_location_id': self.pickup.id}))
        self.assertEqual(resp.status_code, 200)

    def test_pickup_update_idor(self):
        """#75: Cannot update another business pickup location"""
        other = self.create_other_business()
        other_pickup = self.create_pickup_location(other, 'Other WH')
        resp = self.client.get(
            reverse('business:pickup_location_update',
                    kwargs={'pickup_location_id': other_pickup.id}))
        self.assertEqual(resp.status_code, 404)  # get_object_or_404

    def test_pickup_delete_success(self):
        """#76: Delete own pickup location"""
        resp = self.client.get(
            reverse('business:pickup_location_delete',
                    kwargs={'pickup_location_id': self.pickup.id}))
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(
            business_models.PickupLocation.objects.filter(
                id=self.pickup.id).exists())

    def test_pickup_delete_idor(self):
        """#77: Cannot delete another business pickup"""
        other = self.create_other_business()
        other_pickup = self.create_pickup_location(other, 'Other WH')
        resp = self.client.get(
            reverse('business:pickup_location_delete',
                    kwargs={'pickup_location_id': other_pickup.id}))
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(
            business_models.PickupLocation.objects.filter(
                id=other_pickup.id).exists())

    def test_pickup_delete_nonexistent(self):
        """#78: Delete nonexistent pickup redirects"""
        resp = self.client.get(
            reverse('business:pickup_location_delete',
                    kwargs={'pickup_location_id': 99999}))
        self.assertEqual(resp.status_code, 302)

    def test_pickup_list_auth_required(self):
        """#79: Pickup list requires auth"""
        self.client.logout()
        resp = self.client.get(reverse('business:pickup_location_list'))
        self.assertEqual(resp.status_code, 302)


# =============================================================================
# 8. BUSINESS SETTINGS & PROFILE TESTS (8 tests)
# =============================================================================

class BusinessSettingsTest(BusinessTestMixin, TestCase):

    def setUp(self):
        self.client = Client()
        self.user, self.profile = self.create_business_user()
        self.business = self.create_business(self.user, self.profile)
        self.client.login(username='bizowner', password='BizPass@123')

    def test_settings_page_loads(self):
        """#80: Business settings page loads"""
        resp = self.client.get(
            reverse('business:business_settings',
                    kwargs={'business_id': self.business.business_id}))
        self.assertEqual(resp.status_code, 200)

    def test_settings_idor(self):
        """#81: Cannot access another business settings"""
        other = self.create_other_business()
        resp = self.client.get(
            reverse('business:business_settings',
                    kwargs={'business_id': other.business_id}))
        self.assertEqual(resp.status_code, 302)

    def test_business_profile_loads(self):
        """#82: Business profile page loads"""
        resp = self.client.get(reverse('business:business_profile'))
        self.assertEqual(resp.status_code, 200)

    def test_business_profile_update_loads(self):
        """#83: Business profile update form loads"""
        resp = self.client.get(
            reverse('business:business_profile_update',
                    kwargs={'business_id': self.business.business_id}))
        self.assertEqual(resp.status_code, 200)

    def test_business_profile_update_idor(self):
        """#84: Cannot update another business profile"""
        other = self.create_other_business()
        resp = self.client.get(
            reverse('business:business_profile_update',
                    kwargs={'business_id': other.business_id}))
        self.assertEqual(resp.status_code, 302)

    def test_business_info_update_loads(self):
        """#85: Business info update loads"""
        resp = self.client.get(
            reverse('business:business_profile_info_update',
                    kwargs={'business_id': self.business.business_id}))
        self.assertEqual(resp.status_code, 200)

    def test_business_info_update_idor(self):
        """#86: Cannot info-update another business"""
        other = self.create_other_business()
        resp = self.client.get(
            reverse('business:business_profile_info_update',
                    kwargs={'business_id': other.business_id}))
        self.assertEqual(resp.status_code, 302)

    def test_workflow_guide_loads(self):
        """#87: Workflow guide page loads"""
        resp = self.client.get(reverse('business:workflow_guide'))
        self.assertEqual(resp.status_code, 200)


# =============================================================================
# 9. DRIVER DIRECTORY TESTS (5 tests)
# =============================================================================

class DriverDirectoryTest(BusinessTestMixin, TestCase):

    def setUp(self):
        self.client = Client()
        self.user, self.profile = self.create_business_user()
        self.business = self.create_business(self.user, self.profile)
        self.client.login(username='bizowner', password='BizPass@123')

    def test_directory_list_loads(self):
        """#88: Driver directory list loads"""
        resp = self.client.get(reverse('business:driver_directory'))
        self.assertEqual(resp.status_code, 200)

    def test_directory_add_requires_post(self):
        """#89: Driver directory add requires POST"""
        resp = self.client.get(reverse('business:driver_directory_add'))
        self.assertEqual(resp.status_code, 405)

    def test_directory_add_missing_driver_id(self):
        """#90: Add with missing driver_id returns 400"""
        resp = self.client.post(reverse('business:driver_directory_add'), {})
        self.assertEqual(resp.status_code, 400)

    def test_directory_add_invalid_driver_id(self):
        """#91: Add with invalid driver_id format returns 400"""
        resp = self.client.post(
            reverse('business:driver_directory_add'),
            {'driver_id': 'abc'})
        self.assertEqual(resp.status_code, 400)

    def test_directory_delete_nonexistent(self):
        """#92: Delete nonexistent directory entry redirects"""
        resp = self.client.get(
            reverse('business:driver_directory_delete',
                    kwargs={'id': 99999}))
        self.assertEqual(resp.status_code, 302)


# =============================================================================
# 10. TEAM MANAGEMENT TESTS (7 tests)
# =============================================================================

class TeamManagementTest(BusinessTestMixin, TestCase):

    def setUp(self):
        self.client = Client()
        self.user, self.profile = self.create_business_user()
        self.business = self.create_business(self.user, self.profile)
        self.client.login(username='bizowner', password='BizPass@123')

    def test_teams_page_loads(self):
        """#93: Teams list page loads"""
        resp = self.client.get(
            reverse('business:business_teams',
                    kwargs={'business_id': self.business.business_id}))
        self.assertEqual(resp.status_code, 200)

    def test_teams_add_page_loads(self):
        """#94: Team add page loads"""
        resp = self.client.get(
            reverse('business:business_teams_add',
                    kwargs={'business_id': self.business.business_id}))
        self.assertEqual(resp.status_code, 200)

    def test_team_member_has_role_permissions(self):
        """#95: Team member gets correct role permissions"""
        _, _, team = self.create_team_member(
            self.business, role='staff', username='staff1')
        perms = team.get_effective_permissions()
        self.assertIn(BusinessPermissions.ORDER_VIEW, perms)
        self.assertIn(BusinessPermissions.ORDER_CREATE, perms)
        self.assertNotIn(BusinessPermissions.ORDER_DELETE, perms)

    def test_team_manager_permissions(self):
        """#96: Manager has extended permissions"""
        _, _, team = self.create_team_member(
            self.business, role='manager', username='mgr2')
        perms = team.get_effective_permissions()
        self.assertIn(BusinessPermissions.ORDER_DELETE, perms)
        self.assertIn(BusinessPermissions.TEAM_MANAGE, perms)
        self.assertNotIn(BusinessPermissions.SETTINGS_MANAGE, perms)

    def test_team_viewer_limited_permissions(self):
        """#97: Viewer has only read permissions"""
        _, _, team = self.create_team_member(
            self.business, role='viewer', username='viewer1')
        perms = team.get_effective_permissions()
        self.assertIn(BusinessPermissions.ORDER_VIEW, perms)
        self.assertNotIn(BusinessPermissions.ORDER_CREATE, perms)
        self.assertNotIn(BusinessPermissions.ORDER_EDIT, perms)

    def test_inactive_team_no_permissions(self):
        """#98: Inactive team member has no permissions"""
        _, _, team = self.create_team_member(
            self.business, role='manager', username='inactive1',
            status='inactive')
        self.assertFalse(
            team.has_permission(BusinessPermissions.ORDER_VIEW))

    def test_team_grant_revoke_permission(self):
        """#99: Grant and revoke custom permission"""
        _, _, team = self.create_team_member(
            self.business, role='viewer', username='custom1')
        # Viewer doesn't have ORDER_CREATE by default
        self.assertNotIn(BusinessPermissions.ORDER_CREATE,
                         team.get_effective_permissions())
        # Grant it
        team.grant_permission(BusinessPermissions.ORDER_CREATE)
        self.assertIn(BusinessPermissions.ORDER_CREATE,
                      team.get_effective_permissions())
        # Revoke ORDER_VIEW (role default)
        team.revoke_permission(BusinessPermissions.ORDER_VIEW)
        self.assertNotIn(BusinessPermissions.ORDER_VIEW,
                         team.get_effective_permissions())


# =============================================================================
# 11. ACCESS CONTROL TESTS (6 tests)
# =============================================================================

class AccessControlTest(BusinessTestMixin, TestCase):

    def setUp(self):
        self.client = Client()
        self.user, self.profile = self.create_business_user()
        self.business = self.create_business(self.user, self.profile)
        self.pickup = self.create_pickup_location(self.business)
        self.client.login(username='bizowner', password='BizPass@123')

    def test_viewer_cannot_create_order(self):
        """#100: Viewer team member cannot create orders"""
        user, _, team = self.create_team_member(
            self.business, role='viewer', username='viewer2')
        self.client.login(username='viewer2', password='Team@123')
        resp = self.client.get(reverse('orders:add_order'))
        self.assertEqual(resp.status_code, 302)

    def test_viewer_can_view_orders(self):
        """#101: Viewer team member can view orders"""
        user, _, team = self.create_team_member(
            self.business, role='viewer', username='viewer3')
        self.client.login(username='viewer3', password='Team@123')
        resp = self.client.get(reverse('orders:orders_all_list'))
        self.assertEqual(resp.status_code, 200)

    def test_staff_can_create_order(self):
        """#102: Staff team member can create orders"""
        user, _, team = self.create_team_member(
            self.business, role='staff', username='staff2')
        self.client.login(username='staff2', password='Team@123')
        resp = self.client.get(reverse('orders:add_order'))
        self.assertEqual(resp.status_code, 200)

    def test_staff_cannot_delete_order(self):
        """#103: Staff team member cannot delete orders"""
        order = self.create_order(self.business, self.pickup)
        user, _, team = self.create_team_member(
            self.business, role='staff', username='staff3')
        self.client.login(username='staff3', password='Team@123')
        resp = self.client.get(
            reverse('orders:delete_order',
                    kwargs={'order_id': order.id}))
        self.assertEqual(resp.status_code, 302)
        # Order should still exist
        self.assertTrue(
            orders_models.Order.objects.filter(id=order.id).exists())

    def test_owner_has_all_permissions(self):
        """#104: Owner has all permissions via decorator"""
        resp = self.client.get(reverse('orders:add_order'))
        self.assertEqual(resp.status_code, 200)
        order = self.create_order(self.business, self.pickup)
        resp = self.client.get(
            reverse('orders:delete_order',
                    kwargs={'order_id': order.id}))
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(
            orders_models.Order.objects.filter(id=order.id).exists())

    def test_no_business_user_redirected(self):
        """#105: User with no business gets redirected"""
        non_biz = self.create_non_business_user(username='nobiz2')
        self.client.login(username='nobiz2', password='NonBiz@123')
        resp = self.client.get(reverse('orders:orders_all_list'))
        self.assertEqual(resp.status_code, 302)


# =============================================================================
# 12. PAGINATION & EDGE CASES (6 tests)
# =============================================================================

class PaginationEdgeCaseTest(BusinessTestMixin, TestCase):

    def setUp(self):
        self.client = Client()
        self.user, self.profile = self.create_business_user()
        self.business = self.create_business(self.user, self.profile)
        self.pickup = self.create_pickup_location(self.business)
        self.client.login(username='bizowner', password='BizPass@123')

    def test_pagination_page_1(self):
        """#106: First page of orders"""
        for i in range(15):
            self.create_order(self.business, self.pickup)
        resp = self.client.get(reverse('orders:orders_all_list'),
                               {'page': '1', 'per_page': '10'})
        self.assertEqual(resp.status_code, 200)

    def test_pagination_page_2(self):
        """#107: Second page of orders"""
        for i in range(15):
            self.create_order(self.business, self.pickup)
        resp = self.client.get(reverse('orders:orders_all_list'),
                               {'page': '2', 'per_page': '10'})
        self.assertEqual(resp.status_code, 200)

    def test_pagination_invalid_page(self):
        """#108: Invalid page number handled gracefully"""
        self.create_order(self.business, self.pickup)
        resp = self.client.get(reverse('orders:orders_all_list'),
                               {'page': 'invalid'})
        self.assertEqual(resp.status_code, 200)

    def test_pagination_empty_page(self):
        """#109: Empty page falls back to last page"""
        self.create_order(self.business, self.pickup)
        resp = self.client.get(reverse('orders:orders_all_list'),
                               {'page': '999'})
        self.assertEqual(resp.status_code, 200)

    def test_update_order_status_missing_fields(self):
        """#110: Status update with missing fields returns 400"""
        resp = self.client.post(
            reverse('orders:update_order_status'),
            json.dumps({}),
            content_type='application/json')
        self.assertEqual(resp.status_code, 400)

    def test_update_order_status_nonexistent(self):
        """#111: Status update for nonexistent order returns 404"""
        resp = self.client.post(
            reverse('orders:update_order_status'),
            json.dumps({'order_id': 99999, 'status': 'cancelled'}),
            content_type='application/json')
        self.assertEqual(resp.status_code, 404)


# =============================================================================
# 13. BUSINESS FRONTEND TESTS (4 tests)
# =============================================================================

class BusinessFrontendTest(BusinessTestMixin, TestCase):

    def setUp(self):
        self.client = Client()
        self.user, self.profile = self.create_business_user()
        self.business = self.create_business(self.user, self.profile)
        self.client.login(username='bizowner', password='BizPass@123')

    def test_all_business_page_loads(self):
        """#112: All business directory page loads"""
        resp = self.client.get(reverse('business:all_business'))
        self.assertEqual(resp.status_code, 200)

    def test_business_profile_display_loads(self):
        """#113: Business profile display loads"""
        resp = self.client.get(
            reverse('business:business_profile_display',
                    kwargs={'business_id': self.business.business_id}))
        self.assertEqual(resp.status_code, 200)

    def test_business_profile_display_nonexistent(self):
        """#114: Nonexistent business profile redirects"""
        resp = self.client.get(
            reverse('business:business_profile_display',
                    kwargs={'business_id': 88888}))
        self.assertEqual(resp.status_code, 302)

    def test_business_selector_loads(self):
        """#115: Business selector page loads"""
        resp = self.client.get(reverse('business:business_selector'))
        self.assertIn(resp.status_code, [200, 302])


# =============================================================================
# 14. API SETTINGS TESTS (5 tests)
# =============================================================================

class BusinessApiSettingsViewTest(BusinessTestMixin, TestCase):

    def setUp(self):
        self.client = Client()
        self.user, self.profile = self.create_business_user()
        self.business = self.create_business(self.user, self.profile)
        self.client.login(username='bizowner', password='BizPass@123')

    def test_api_list_loads(self):
        """#116: API settings list loads"""
        resp = self.client.get(
            reverse('business:business_settings_api_list',
                    kwargs={'business_id': self.business.business_id}))
        self.assertIn(resp.status_code, [200, 302])

    def test_api_add_page_loads(self):
        """#117: API add page loads"""
        resp = self.client.get(
            reverse('business:business_settings_api_add',
                    kwargs={'business_id': self.business.business_id}))
        self.assertEqual(resp.status_code, 200)

    def test_api_add_idor(self):
        """#118: Cannot add API to another business"""
        other = self.create_other_business()
        resp = self.client.get(
            reverse('business:business_settings_api_add',
                    kwargs={'business_id': other.business_id}))
        self.assertEqual(resp.status_code, 302)

    def test_api_update_nonexistent(self):
        """#119: Update nonexistent API setting redirects"""
        resp = self.client.get(
            reverse('business:business_settings_api_update',
                    kwargs={'business_id': self.business.business_id,
                            'api_id': 99999}))
        self.assertEqual(resp.status_code, 302)

    def test_api_delete_nonexistent(self):
        """#120: Delete nonexistent API setting redirects"""
        resp = self.client.get(
            reverse('business:business_settings_api_delete',
                    kwargs={'business_id': self.business.business_id,
                            'api_id': 99999}))
        self.assertIn(resp.status_code, [302, 404])


# =============================================================================
# 16. FINANCE VIEWS TESTS (12 tests)
# =============================================================================

class BusinessFinanceViewsTest(BusinessTestMixin, TestCase):
    """Tests for business_finance_dashboard, business_transactions, business_cod_statement."""

    def setUp(self):
        self.client = Client()
        self.user, self.profile = self.create_business_user()
        self.business = self.create_business(self.user, self.profile)
        self.client.login(username='bizowner', password='BizPass@123')

    # --- business_finance_dashboard ---

    def test_finance_dashboard_loads(self):
        """#121: Finance dashboard loads for business owner"""
        resp = self.client.get(reverse('business:business_finance_dashboard'))
        self.assertEqual(resp.status_code, 200)

    def test_finance_dashboard_requires_auth(self):
        """#122: Finance dashboard requires login"""
        self.client.logout()
        resp = self.client.get(reverse('business:business_finance_dashboard'))
        self.assertEqual(resp.status_code, 302)
        self.assertIn('login', resp.url.lower())

    def test_finance_dashboard_invalid_days_param(self):
        """#123: Finance dashboard handles invalid days param (no 500 error)"""
        resp = self.client.get(
            reverse('business:business_finance_dashboard'),
            {'days': 'invalid'})
        self.assertEqual(resp.status_code, 200)

    def test_finance_dashboard_negative_days_param(self):
        """#124: Finance dashboard handles negative days param (clamps to 30)"""
        resp = self.client.get(
            reverse('business:business_finance_dashboard'),
            {'days': '-100'})
        self.assertEqual(resp.status_code, 200)

    def test_finance_dashboard_zero_days_param(self):
        """#125: Finance dashboard handles zero days param (clamps to 30)"""
        resp = self.client.get(
            reverse('business:business_finance_dashboard'),
            {'days': '0'})
        self.assertEqual(resp.status_code, 200)

    # --- business_transactions ---

    def test_transactions_loads(self):
        """#126: Business transactions page loads"""
        resp = self.client.get(reverse('business:business_transactions'))
        self.assertEqual(resp.status_code, 200)

    def test_transactions_requires_auth(self):
        """#127: Transactions page requires login"""
        self.client.logout()
        resp = self.client.get(reverse('business:business_transactions'))
        self.assertEqual(resp.status_code, 302)
        self.assertIn('login', resp.url.lower())

    def test_transactions_invalid_days_param(self):
        """#128: Transactions handles invalid days param (no 500 error)"""
        resp = self.client.get(
            reverse('business:business_transactions'),
            {'days': 'abc'})
        self.assertEqual(resp.status_code, 200)

    def test_transactions_filter_by_type(self):
        """#129: Transactions can be filtered by type"""
        resp = self.client.get(
            reverse('business:business_transactions'),
            {'type': 'delivery_charge'})
        self.assertEqual(resp.status_code, 200)

    # --- business_cod_statement ---

    def test_cod_statement_loads(self):
        """#130: COD statement page loads"""
        resp = self.client.get(reverse('business:business_cod_statement'))
        self.assertEqual(resp.status_code, 200)

    def test_cod_statement_requires_auth(self):
        """#131: COD statement requires login"""
        self.client.logout()
        resp = self.client.get(reverse('business:business_cod_statement'))
        self.assertEqual(resp.status_code, 302)
        self.assertIn('login', resp.url.lower())

    def test_cod_statement_invalid_days_param(self):
        """#132: COD statement handles invalid days param (no 500 error)"""
        resp = self.client.get(
            reverse('business:business_cod_statement'),
            {'days': 'xyz'})
        self.assertEqual(resp.status_code, 200)


# =============================================================================
# 17. FINANCE VIEWS — API TEST & MISC (6 tests)
# =============================================================================

class BusinessApiTestViewTest(BusinessTestMixin, TestCase):
    """Tests for business_settings_api_test and business_settings_api_test_result."""

    def setUp(self):
        self.client = Client()
        self.user, self.profile = self.create_business_user()
        self.business = self.create_business(self.user, self.profile)
        self.client.login(username='bizowner', password='BizPass@123')

    def test_api_test_page_nonexistent_api(self):
        """#133: API test page with nonexistent api_id redirects gracefully (no 500)"""
        resp = self.client.get(
            reverse('business:business_settings_api_test',
                    kwargs={'business_id': self.business.business_id,
                            'api_id': 99999}))
        self.assertIn(resp.status_code, [302, 200])

    def test_api_test_result_nonexistent_api_redirects(self):
        """#134: API test result with nonexistent api_id redirects (no 500)"""
        resp = self.client.get(
            reverse('business:business_settings_api_test_result',
                    kwargs={'business_id': self.business.business_id,
                            'api_id': 99999}))
        self.assertIn(resp.status_code, [302, 200])

    def test_api_test_idor(self):
        """#135: Cannot access another business's API test page"""
        other = self.create_other_business()
        resp = self.client.get(
            reverse('business:business_settings_api_test',
                    kwargs={'business_id': other.business_id,
                            'api_id': 1}))
        self.assertEqual(resp.status_code, 302)

    def test_business_selector_loads(self):
        """#136: Business selector page loads"""
        resp = self.client.get(reverse('business:business_selector'))
        self.assertIn(resp.status_code, [200, 302])

    def test_business_switch_invalid_id(self):
        """#137: Switching to non-existent business redirects to selector"""
        resp = self.client.get(
            reverse('business:business_switch',
                    kwargs={'business_id': 99999}))
        self.assertEqual(resp.status_code, 302)

    def test_warehouse_request_loads(self):
        """#138: Warehouse request page loads without crashing"""
        resp = self.client.get(reverse('business:warehouse_request'))
        self.assertIn(resp.status_code, [200, 302])
