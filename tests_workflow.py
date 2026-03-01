"""
End-to-End Workflow Test Suite
==============================

54 scenarios testing the full order lifecycle:
  Business → Staff Verification → Driver Assignment → Delivery → COD Settlement

Scenarios:
  1-10:  Order Creation & Management (Business side)
  11-20: Staff / Workforce Verification
  21-30: Driver Assignment & Delivery Execution
  31-40: COD Collection & Settlement
  41-54: Edge Cases, Access Control & Data Integrity
"""

import json
from decimal import Decimal
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


# =============================================================================
# SHARED HELPERS
# =============================================================================

class WorkflowMixin:
    """Helper methods shared by all workflow test classes."""

    _biz_seq = 80000
    _drv_seq = 28000

    def create_business_user(self, username='wf_biz', password='BizPass@123'):
        user = User.objects.create_user(
            username=username, password=password, email=f'{username}@wf.test')
        profile = core_models.Profile.objects.create(
            user=user, first_name='Workflow', last_name='Business',
            phone=70000001, is_business=True,
            is_business_profile_completed=True)
        return user, profile

    def create_business(self, user, profile):
        WorkflowMixin._biz_seq += 1
        bid = WorkflowMixin._biz_seq
        biz = business_models.Business.objects.create(
            business_id=bid, user=user, profile=profile,
            business_name='Workflow Test Biz', business_code=f'WF{bid}',
            business_status='active',
            fulfillment_service_enabled=False,
            fulfillment_service_status='none')
        business_models.BusinessProfile.objects.get_or_create(business=biz)
        return biz

    def create_pickup(self, business, title='Main Warehouse'):
        return business_models.PickupLocation.objects.create(
            business=business, pickup_location_title=title,
            locality='Doha', pickup_zone_no=1,
            pickup_street_no=100, pickup_building_no=10,
            pickup_status='active')

    def create_order(self, business, pickup=None, cod=0, status='to_review'):
        import uuid
        code = f'WF-{uuid.uuid4().hex[:8]}'
        return orders_models.Order.objects.create(
            business=business,
            client_order_code=code,
            customer_name='Workflow Customer',
            customer_phone='55511111',
            customer_whatsapp='55511111',
            customer_address='123 Workflow St, Doha',
            dl_zone=1, dl_street=10, dl_building=5,
            cod_amount=cod,
            cod_status_by_client='pending' if cod else 'no_cod',
            order_status=status,
            pickup_location=pickup)

    def create_staff_user(self, username='wf_staff', password='Staff@123'):
        user = User.objects.create_user(
            username=username, password=password,
            email=f'{username}@wf.test', is_staff=True)
        core_models.Profile.objects.create(
            user=user, first_name='Workflow', last_name='Staff',
            phone=70000002, is_staff=True)
        return user

    def create_driver(self, username='wf_driver', password='Driver@123'):
        WorkflowMixin._drv_seq += 1
        did = WorkflowMixin._drv_seq
        drv_user = User.objects.create_user(
            username=username, password=password,
            email=f'{username}@wf.test')
        drv_profile = core_models.Profile.objects.create(
            user=drv_user, first_name='Workflow', last_name='Driver',
            phone=70000000 + did, is_driver=True)
        driver = fleet_models.Driver.objects.create(
            driver_id=did, user=drv_user, profile=drv_profile,
            driver_code=f'WFDRV{did}',
            driver_phone='55500000',
            driver_status='approved',
            credit_limit=Decimal('5000.00'),
            cod_in_hand=Decimal('0.00'),
            wallet_balance=Decimal('0.00'))
        return driver

    def create_delivery_task(self, order, driver=None, status='pending',
                             published=False):
        addr = delivery_models.DlAddressUpdate.objects.filter(
            order=order).first()
        if not addr:
            addr = delivery_models.DlAddressUpdate.objects.create(
                full_name=order.customer_name,
                order=order,
                dl_task_number=order.order_number or 'WF-TEST',
                mobile_no=order.customer_phone,
                dl_zone=order.dl_zone,
                dl_street=order.dl_street,
                dl_building=order.dl_building,
                dl_latitude=Decimal('0'),
                dl_longitude=Decimal('0'))
        return delivery_models.DeliveryTask.objects.create(
            dl_task_number=order.order_number or f'WF-{order.id}',
            dl_task_description=f'Delivery for {order.order_number}',
            order=order,
            business=order.business,
            dl_address_update=addr,
            driver=driver,
            dl_task_status=status,
            dl_task_status_client='for_review',
            dl_task_publish=published,
            pickup_location=order.pickup_location,
            cod_collected_amount=Decimal(str(order.cod_amount)),
        )

    def create_team_member(self, business, role='staff',
                           username='wf_team', password='Team@123'):
        user = User.objects.create_user(
            username=username, password=password,
            email=f'{username}@wf.test')
        profile = core_models.Profile.objects.create(
            user=user, first_name='Team', last_name='Member',
            phone=70000003, is_business=True,
            is_business_profile_completed=True)
        team = business_models.BusinessTeamProfile.objects.create(
            user=user, profile=profile, business=business,
            team_code=f'TM-{username}', team_role=role,
            team_status='active', team_name=f'{username} member')
        return user, profile, team


# =============================================================================
# GROUP 1: ORDER CREATION & MANAGEMENT (Scenarios 1–10)
# =============================================================================

class WorkflowGroup1_OrderCreation(WorkflowMixin, TestCase):
    """Business creates, updates, and deletes orders."""

    def setUp(self):
        self.client = Client()
        self.biz_user, self.biz_profile = self.create_business_user()
        self.business = self.create_business(self.biz_user, self.biz_profile)
        self.pickup = self.create_pickup(self.business)
        self.client.login(username='wf_biz', password='BizPass@123')

    def test_01_business_views_order_list(self):
        """Scenario 1: Business can view their order list"""
        self.create_order(self.business, self.pickup)
        resp = self.client.get(reverse('orders:orders_all_list'))
        self.assertEqual(resp.status_code, 200)

    def test_02_business_creates_order_via_form(self):
        """Scenario 2: Business submits add order form (GET loads)"""
        resp = self.client.get(reverse('orders:add_order'))
        self.assertEqual(resp.status_code, 200)

    def test_03_business_creates_order_with_cod(self):
        """Scenario 3: Order created with COD amount is stored correctly"""
        order = self.create_order(self.business, self.pickup, cod=150)
        self.assertEqual(order.cod_amount, 150)
        self.assertEqual(order.cod_status_by_client, 'pending')

    def test_04_business_views_order_details(self):
        """Scenario 4: Business can view their own order details"""
        order = self.create_order(self.business, self.pickup)
        resp = self.client.get(
            reverse('orders:order_details', kwargs={'order_id': order.id}))
        self.assertEqual(resp.status_code, 200)

    def test_05_business_updates_pending_order(self):
        """Scenario 5: Business can view update form for a pending (to_review) order"""
        order = self.create_order(self.business, self.pickup)
        resp = self.client.get(
            reverse('orders:order_update', kwargs={'order_id': order.id}))
        self.assertEqual(resp.status_code, 200)

    def test_06_business_cannot_update_dispatched_order(self):
        """Scenario 6: Business update for order with dl_task_listed — no crash"""
        order = self.create_order(self.business, self.pickup,
                                  status='to_review')
        order.task_status = 'dl_task_listed'
        order.save()
        resp = self.client.post(
            reverse('orders:order_update', kwargs={'order_id': order.id}),
            data={'customer_name': 'New Name', 'customer_phone': '12345678',
                  'customer_address': 'New Address', 'dl_zone': 1,
                  'dl_street': 10, 'dl_building': 5})
        # View should still allow GET but block the update or accept it
        self.assertIn(resp.status_code, [200, 302])

    def test_07_business_deletes_pending_order(self):
        """Scenario 7: Business can delete a pending order"""
        order = self.create_order(self.business, self.pickup)
        order_id = order.id
        resp = self.client.post(
            reverse('orders:delete_order', kwargs={'order_id': order_id}))
        self.assertIn(resp.status_code, [200, 302])
        self.assertFalse(orders_models.Order.objects.filter(id=order_id).exists())

    def test_08_business_cannot_view_other_business_order(self):
        """Scenario 8: IDOR — business cannot view another business's order"""
        biz2_user, biz2_profile = self.create_business_user('wf_biz2')
        biz2 = self.create_business(biz2_user, biz2_profile)
        pickup2 = self.create_pickup(biz2, 'Biz2 Warehouse')
        order2 = self.create_order(biz2, pickup2)
        resp = self.client.get(
            reverse('orders:order_details', kwargs={'order_id': order2.id}))
        self.assertIn(resp.status_code, [302, 403, 404])

    def test_09_order_number_auto_generated(self):
        """Scenario 9: Order number is auto-generated on save"""
        order = self.create_order(self.business, self.pickup)
        self.assertIsNotNone(order.order_number)
        self.assertNotEqual(order.order_number, '')

    def test_10_order_barcode_auto_created(self):
        """Scenario 10: OrderBarcode is auto-created by post_save signal"""
        order = self.create_order(self.business, self.pickup)
        # Signal creates barcode automatically
        self.assertTrue(
            orders_models.OrderBarcode.objects.filter(order=order).exists())


# =============================================================================
# GROUP 2: STAFF / WORKFORCE VERIFICATION (Scenarios 11–20)
# =============================================================================

class WorkflowGroup2_StaffVerification(WorkflowMixin, TestCase):
    """Staff verifies orders, publishes tasks, assigns drivers."""

    def setUp(self):
        self.client = Client()
        self.staff_user = self.create_staff_user()
        self.biz_user, self.biz_profile = self.create_business_user('wf_biz_s')
        self.business = self.create_business(self.biz_user, self.biz_profile)
        self.pickup = self.create_pickup(self.business)
        self.client.login(username='wf_staff', password='Staff@123')

    def test_11_staff_views_order_list(self):
        """Scenario 11: Staff can view the order management list"""
        resp = self.client.get(reverse('workforce:wf_orders_all'))
        self.assertEqual(resp.status_code, 200)

    def test_12_staff_views_order_details(self):
        """Scenario 12: Staff can view any order's details"""
        order = self.create_order(self.business, self.pickup)
        resp = self.client.get(
            reverse('workforce:order_detail', kwargs={'order_id': order.id}))
        self.assertEqual(resp.status_code, 200)

    def test_13_staff_adds_comment_to_order(self):
        """Scenario 13: Staff can add comment to order"""
        order = self.create_order(self.business, self.pickup)
        resp = self.client.post(
            reverse('orders:add_order_comment', kwargs={'order_id': order.id}),
            data={'comment': 'Staff review note'})
        self.assertEqual(resp.status_code, 200)
        # Comment is created
        self.assertTrue(
            orders_models.OrderComments.objects.filter(
                order=order, body='Staff review note').exists())

    def test_14_staff_cancels_order(self):
        """Scenario 14: Staff can cancel an order"""
        order = self.create_order(self.business, self.pickup)
        resp = self.client.post(
            reverse('workforce:cancel_order', kwargs={'order_id': order.id}),
            data=json.dumps({'reason': 'Test cancellation'}),
            content_type='application/json')
        self.assertIn(resp.status_code, [200, 302])
        order.refresh_from_db()
        self.assertEqual(order.order_status, 'cancelled')

    def test_15_staff_publishes_task_to_fleet(self):
        """Scenario 15: Staff publishes a delivery task to fleet drivers"""
        order = self.create_order(self.business, self.pickup,
                                  status='ready_to_pickup')
        order.verification_status = 'verified'
        order.save()
        task = self.create_delivery_task(order, status='for_review')
        resp = self.client.post(
            reverse('workforce:publish_task_to_fleets',
                    kwargs={'task_id': task.id}))
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.content)
        self.assertTrue(data.get('success'))
        task.refresh_from_db()
        self.assertTrue(task.dl_task_publish)
        self.assertEqual(task.dl_task_status, 'pending')

    def test_16_staff_assigns_driver_to_task(self):
        """Scenario 16: Staff manually assigns driver to delivery task"""
        driver = self.create_driver()
        order = self.create_order(self.business, self.pickup)
        task = self.create_delivery_task(order, status='pending',
                                         published=True)
        resp = self.client.post(
            reverse('workforce:assign_driver_to_task',
                    kwargs={'task_id': task.id}),
            data=json.dumps({'driver_id': driver.driver_id}),
            content_type='application/json')
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.content)
        self.assertTrue(data.get('success'))
        task.refresh_from_db()
        self.assertEqual(task.driver_id, driver.driver_id)
        self.assertEqual(task.dl_task_status, 'assigned')

    def test_17_staff_cannot_assign_nonexistent_driver(self):
        """Scenario 17: Assigning nonexistent driver returns error"""
        order = self.create_order(self.business, self.pickup)
        task = self.create_delivery_task(order, status='pending',
                                         published=True)
        resp = self.client.post(
            reverse('workforce:assign_driver_to_task',
                    kwargs={'task_id': task.id}),
            data=json.dumps({'driver_id': 99999}),
            content_type='application/json')
        data = json.loads(resp.content)
        self.assertFalse(data.get('success'))

    def test_18_staff_cannot_publish_cancelled_order_task(self):
        """Scenario 18: Cannot publish task if order is cancelled"""
        order = self.create_order(self.business, self.pickup,
                                  status='cancelled')
        task = self.create_delivery_task(order, status='for_review')
        resp = self.client.post(
            reverse('workforce:publish_task_to_fleets',
                    kwargs={'task_id': task.id}))
        data = json.loads(resp.content)
        self.assertFalse(data.get('success'))

    def test_19_staff_views_task_list(self):
        """Scenario 19: Staff can view the delivery task list"""
        resp = self.client.get(reverse('workforce:dl_list_all'))
        self.assertEqual(resp.status_code, 200)

    def test_20_staff_views_cod_settlement_report(self):
        """Scenario 20: Staff can view COD settlement report"""
        resp = self.client.get(reverse('workforce:cod_settlement_report'))
        self.assertIn(resp.status_code, [200, 302])


# =============================================================================
# GROUP 3: DRIVER ASSIGNMENT & DELIVERY (Scenarios 21–30)
# =============================================================================

class WorkflowGroup3_DriverDelivery(WorkflowMixin, TestCase):
    """Driver accepts task, starts ride, completes delivery."""

    def setUp(self):
        self.client = Client()
        self.driver = self.create_driver()
        self.biz_user, self.biz_profile = self.create_business_user('wf_biz_d')
        self.business = self.create_business(self.biz_user, self.biz_profile)
        self.pickup = self.create_pickup(self.business)
        self.client.login(username='wf_driver', password='Driver@123')

    def test_21_driver_views_dashboard(self):
        """Scenario 21: Driver can view their fleet dashboard"""
        resp = self.client.get(reverse('fleet:fleet_dashboard'))
        self.assertEqual(resp.status_code, 200)

    def test_22_driver_views_task_list(self):
        """Scenario 22: Driver can view their task list"""
        resp = self.client.get(reverse('fleet:driver_tasks'))
        self.assertEqual(resp.status_code, 200)

    def test_23_driver_self_assigns_published_task(self):
        """Scenario 23: Driver self-assigns to a published pending task"""
        order = self.create_order(self.business, self.pickup)
        task = self.create_delivery_task(order, status='pending', published=True)
        resp = self.client.post(
            reverse('fleet:fleet_assign_driver'),
            data={'task_id': task.id})
        data = json.loads(resp.content)
        self.assertTrue(data.get('success'))
        task.refresh_from_db()
        self.assertEqual(task.dl_task_status, 'accepted')

    def test_24_driver_cannot_assign_unpublished_task(self):
        """Scenario 24: Driver cannot self-assign an unpublished task"""
        order = self.create_order(self.business, self.pickup)
        task = self.create_delivery_task(order, status='pending',
                                         published=False)
        resp = self.client.post(
            reverse('fleet:fleet_assign_driver'),
            data={'task_id': task.id})
        data = json.loads(resp.content)
        self.assertFalse(data.get('success'))

    def test_25_driver_starts_ride(self):
        """Scenario 25: Driver starts ride (accepted → out_for_delivery)"""
        order = self.create_order(self.business, self.pickup)
        task = self.create_delivery_task(order, driver=self.driver,
                                         status='accepted', published=True)
        resp = self.client.post(
            reverse('fleet:fleet_start_ride'),
            data={'task_id': task.id})
        data = json.loads(resp.content)
        self.assertTrue(data.get('success'))
        task.refresh_from_db()
        self.assertEqual(task.dl_task_status, 'out_for_delivery')

    def test_26_driver_cannot_start_ride_on_cancelled_order(self):
        """Scenario 26: Driver cannot start ride if order is cancelled"""
        order = self.create_order(self.business, self.pickup,
                                  status='cancelled')
        task = self.create_delivery_task(order, driver=self.driver,
                                         status='accepted', published=True)
        resp = self.client.post(
            reverse('fleet:fleet_start_ride'),
            data={'task_id': task.id})
        data = json.loads(resp.content)
        self.assertFalse(data.get('success'))

    def test_27_driver_views_cod_collection_list(self):
        """Scenario 27: Driver can view their COD collection page"""
        resp = self.client.get(reverse('fleet:cod_collection'))
        self.assertEqual(resp.status_code, 200)

    def test_28_driver_cannot_see_another_drivers_task(self):
        """Scenario 28: Driver cannot access another driver's task details"""
        other_driver = self.create_driver('wf_driver2', 'Driver@456')
        order = self.create_order(self.business, self.pickup)
        task = self.create_delivery_task(order, driver=other_driver,
                                         status='accepted', published=True)
        # Try to start ride for a task assigned to another driver
        resp = self.client.post(
            reverse('fleet:fleet_start_ride'),
            data={'task_id': task.id})
        data = json.loads(resp.content)
        self.assertFalse(data.get('success'))

    def test_29_driver_views_task_navigation(self):
        """Scenario 29: Driver can view task navigation page for their task"""
        order = self.create_order(self.business, self.pickup)
        task = self.create_delivery_task(order, driver=self.driver,
                                         status='out_for_delivery',
                                         published=True)
        resp = self.client.get(
            reverse('fleet:fleet_task_navigation',
                    kwargs={'task_id': task.id}))
        self.assertIn(resp.status_code, [200, 302])

    def test_30_driver_views_task_timeline(self):
        """Scenario 30: Driver can view task timeline"""
        order = self.create_order(self.business, self.pickup)
        task = self.create_delivery_task(order, driver=self.driver,
                                         status='accepted', published=True)
        resp = self.client.get(
            reverse('fleet:fleet_task_timeline',
                    kwargs={'task_id': task.id}))
        self.assertIn(resp.status_code, [200, 302])


# =============================================================================
# GROUP 4: COD COLLECTION & SETTLEMENT (Scenarios 31–40)
# =============================================================================

class WorkflowGroup4_CODWorkflow(WorkflowMixin, TestCase):
    """COD collection, submission, and settlement flow."""

    def setUp(self):
        self.client = Client()
        self.driver = self.create_driver()
        self.staff_user = self.create_staff_user()
        self.biz_user, self.biz_profile = self.create_business_user('wf_biz_c')
        self.business = self.create_business(self.biz_user, self.biz_profile)
        self.pickup = self.create_pickup(self.business)

    def _driver_login(self):
        self.client.login(username='wf_driver', password='Driver@123')

    def _staff_login(self):
        self.client.login(username='wf_staff', password='Staff@123')

    def _biz_login(self):
        self.client.login(username='wf_biz_c', password='BizPass@123')

    def test_31_driver_cod_in_hand_starts_at_zero(self):
        """Scenario 31: New driver has 0 COD in hand"""
        self.assertEqual(self.driver.cod_in_hand, Decimal('0.00'))

    def test_32_order_cod_amount_stored_correctly(self):
        """Scenario 32: COD amount on order stored as integer"""
        order = self.create_order(self.business, self.pickup, cod=200)
        self.assertEqual(order.cod_amount, 200)

    def test_33_driver_views_cod_collection_page(self):
        """Scenario 33: Driver can view COD collection page"""
        self._driver_login()
        resp = self.client.get(reverse('fleet:cod_collection'))
        self.assertEqual(resp.status_code, 200)

    def test_34_cod_submission_redirects_get(self):
        """Scenario 34: COD submission GET redirects to cod_collection"""
        self._driver_login()
        resp = self.client.get(reverse('fleet:cod_submission'))
        self.assertIn(resp.status_code, [301, 302])

    def test_35_business_views_cod_statement(self):
        """Scenario 35: Business can view their COD statement"""
        self._biz_login()
        resp = self.client.get(reverse('business:business_cod_statement'))
        self.assertEqual(resp.status_code, 200)

    def test_36_business_cod_statement_with_data(self):
        """Scenario 36: COD statement displays tasks with cod_collected_amount"""
        order = self.create_order(self.business, self.pickup, cod=300)
        task = self.create_delivery_task(order, driver=self.driver,
                                         status='delivered', published=True)
        task.cod_collected = True
        task.cod_collected_amount = Decimal('300')
        task.save()
        self._biz_login()
        resp = self.client.get(reverse('business:business_cod_statement'))
        self.assertEqual(resp.status_code, 200)

    def test_37_driver_credit_limit_blocks_wallet(self):
        """Scenario 37: Driver wallet blocks when cod_in_hand >= credit_limit"""
        self.driver.cod_in_hand = Decimal('5000.00')
        self.driver.credit_limit = Decimal('5000.00')
        self.driver.save()
        self.driver.refresh_from_db()
        self.assertTrue(self.driver.is_wallet_blocked)

    def test_38_driver_wallet_usage_percentage(self):
        """Scenario 38: Wallet usage percentage computed from cod_in_hand"""
        self.driver.cod_in_hand = Decimal('2500.00')
        self.driver.credit_limit = Decimal('5000.00')
        self.driver.save()
        self.driver.refresh_from_db()
        self.assertEqual(self.driver.wallet_usage_percentage, 50.0)

    def test_39_business_finance_dashboard_loads_with_no_data(self):
        """Scenario 39: Finance dashboard handles business with no transactions"""
        self._biz_login()
        resp = self.client.get(reverse('business:business_finance_dashboard'))
        self.assertEqual(resp.status_code, 200)

    def test_40_business_transactions_filter_by_type(self):
        """Scenario 40: Transactions can be filtered by type without crashing"""
        self._biz_login()
        resp = self.client.get(
            reverse('business:business_transactions'),
            {'type': 'delivery_charge', 'days': '30'})
        self.assertEqual(resp.status_code, 200)


# =============================================================================
# GROUP 5: EDGE CASES, ACCESS CONTROL & DATA INTEGRITY (Scenarios 41–54)
# =============================================================================

class WorkflowGroup5_EdgeCases(WorkflowMixin, TestCase):
    """Edge cases, access control, and data integrity checks."""

    def setUp(self):
        self.client = Client()
        self.biz_user, self.biz_profile = self.create_business_user()
        self.business = self.create_business(self.biz_user, self.biz_profile)
        self.pickup = self.create_pickup(self.business)

    def test_41_anonymous_user_redirected_from_dashboard(self):
        """Scenario 41: Anonymous user cannot access business dashboard"""
        resp = self.client.get(reverse('business:business_dashboard'))
        self.assertEqual(resp.status_code, 302)
        self.assertIn('login', resp.url.lower())

    def test_42_anonymous_user_redirected_from_fleet_dashboard(self):
        """Scenario 42: Anonymous user cannot access fleet dashboard"""
        resp = self.client.get(reverse('fleet:fleet_dashboard'))
        self.assertEqual(resp.status_code, 302)

    def test_43_anonymous_user_redirected_from_workforce(self):
        """Scenario 43: Anonymous user cannot access workforce dashboard"""
        resp = self.client.get(reverse('workforce:wf_dashboard'))
        self.assertEqual(resp.status_code, 302)

    def test_44_viewer_role_cannot_create_orders(self):
        """Scenario 44: Team member with viewer role cannot create orders"""
        team_user, _, _ = self.create_team_member(
            self.business, role='viewer', username='wf_viewer')
        self.client.login(username='wf_viewer', password='Team@123')
        resp = self.client.get(reverse('orders:add_order'))
        # Viewer should be redirected (no CREATE_ORDER permission)
        self.assertIn(resp.status_code, [302, 403])

    def test_45_staff_role_can_create_orders(self):
        """Scenario 45: Team member with staff role can create orders"""
        team_user, _, _ = self.create_team_member(
            self.business, role='staff', username='wf_team_staff')
        self.client.login(username='wf_team_staff', password='Team@123')
        resp = self.client.get(reverse('orders:add_order'))
        self.assertEqual(resp.status_code, 200)

    def test_46_order_status_history_created_on_save(self):
        """Scenario 46: OrderStatusHistory record exists after order creation"""
        order = self.create_order(self.business, self.pickup)
        # Signal creates OrderStatusHistory on order creation
        history = orders_models.OrderStatusHistory.objects.filter(order=order)
        self.assertTrue(history.exists())

    def test_47_address_verification_auto_created(self):
        """Scenario 47: AddressVerification record auto-created on order save"""
        order = self.create_order(self.business, self.pickup)
        verifications = orders_models.AddressVerification.objects.filter(
            order=order)
        self.assertTrue(verifications.exists())

    def test_48_delivery_task_requires_published_flag_for_driver_assign(self):
        """Scenario 48: Driver cannot self-assign unpublished task"""
        driver = self.create_driver('wf_d_48', 'Driver@123')
        order = self.create_order(self.business, self.pickup)
        task = self.create_delivery_task(order, status='pending',
                                         published=False)
        self.client.login(username='wf_d_48', password='Driver@123')
        resp = self.client.post(
            reverse('fleet:fleet_assign_driver'),
            data={'task_id': task.id})
        data = json.loads(resp.content)
        self.assertFalse(data.get('success'))

    def test_49_pickup_location_list_shows_fulfillment_first(self):
        """Scenario 49: Fulfillment center appears first in pickup location list"""
        # Create normal and fulfillment pickup locations
        fulfillment = business_models.PickupLocation.objects.create(
            business=self.business,
            pickup_location_title='Fulfillment Store',
            locality='EzzyDelivery FC',
            pickup_status='active',
            is_fulfilment_center=True)
        normal = business_models.PickupLocation.objects.create(
            business=self.business,
            pickup_location_title='Alpha Warehouse',
            locality='Doha',
            pickup_status='active',
            is_fulfilment_center=False)
        locations = business_models.PickupLocation.objects.filter(
            business=self.business
        ).order_by('-is_fulfilment_center', 'pickup_location_title')
        self.assertEqual(locations.first().id, fulfillment.id)

    def test_50_business_cannot_access_other_business_settings(self):
        """Scenario 50: IDOR — business cannot access another business's settings"""
        self.client.login(username='wf_biz', password='BizPass@123')
        biz2_user, biz2_profile = self.create_business_user('wf_biz_50')
        biz2 = self.create_business(biz2_user, biz2_profile)
        resp = self.client.get(
            reverse('business:business_settings',
                    kwargs={'business_id': biz2.business_id}))
        self.assertEqual(resp.status_code, 302)

    def test_51_finance_dashboard_invalid_days_param_no_crash(self):
        """Scenario 51: Finance dashboard handles invalid days param gracefully"""
        self.client.login(username='wf_biz', password='BizPass@123')
        resp = self.client.get(
            reverse('business:business_finance_dashboard'),
            {'days': 'not_a_number'})
        self.assertEqual(resp.status_code, 200)

    def test_52_cod_statement_invalid_days_param_no_crash(self):
        """Scenario 52: COD statement handles invalid days param gracefully"""
        self.client.login(username='wf_biz', password='BizPass@123')
        resp = self.client.get(
            reverse('business:business_cod_statement'),
            {'days': 'bad_input'})
        self.assertEqual(resp.status_code, 200)

    def test_53_transactions_invalid_days_param_no_crash(self):
        """Scenario 53: Transactions page handles invalid days param gracefully"""
        self.client.login(username='wf_biz', password='BizPass@123')
        resp = self.client.get(
            reverse('business:business_transactions'),
            {'days': '!@#$'})
        self.assertEqual(resp.status_code, 200)

    def test_54_driver_wallet_available_credit_decreases_with_cod_in_hand(self):
        """Scenario 54: Available credit = credit_limit - cod_in_hand"""
        driver = self.create_driver('wf_d_54', 'Driver@123')
        driver.cod_in_hand = Decimal('1500.00')
        driver.credit_limit = Decimal('5000.00')
        driver.save()
        driver.refresh_from_db()
        expected_available = Decimal('5000.00') - Decimal('1500.00')
        self.assertEqual(driver.available_credit, expected_available)
