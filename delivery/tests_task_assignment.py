"""
Purpose: Tests for who a delivery task goes to — Public pool vs Unassigned list vs one driver — and the Task Automation rules
Used by: manage.py test delivery.tests_task_assignment
Notes:   Rules run via transaction.on_commit, so tests that publish wrap the save in captureOnCommitCallbacks(execute=True).
"""
import json
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings

from business import models as business_models
from core import models as core_models
from delivery import models as delivery_models
from delivery.selectors import delivery_pool_block, delivery_pool_for, unassigned_tasks
from delivery.services import assignment
from fleet import models as fleet_models
from orders import models as orders_models

User = get_user_model()


@override_settings(SECURE_SSL_REDIRECT=False, ALLOWED_HOSTS=['testserver'],
                   DRIVER_DEVICE_ENFORCEMENT=False)
class TaskAssignmentBase(TestCase):

    def setUp(self):
        self.driver_a, self.client_a = self._driver(8801, 'drva', 'DRVA')
        self.driver_b, self.client_b = self._driver(8802, 'drvb', 'DRVB')
        # Approved, but ops never switched app access on.
        self.driver_c, self.client_c = self._driver(8803, 'drvc', 'DRVC', access=False)

        biz_user = User.objects.create_user(username='tabiz', email='tabiz@test.com', password='x')
        biz_profile = core_models.Profile.objects.create(
            user=biz_user, first_name='TA', last_name='Biz', phone=30000001, is_business=True)
        self.business = business_models.Business.objects.create(
            business_id=8810, user=biz_user, profile=biz_profile,
            business_name='Rule Test Store', business_code='RTS001', business_status='active')
        other_user = User.objects.create_user(username='tabiz2', email='tabiz2@test.com', password='x')
        other_profile = core_models.Profile.objects.create(
            user=other_user, first_name='TA', last_name='Biz2', phone=30000002, is_business=True)
        self.other_business = business_models.Business.objects.create(
            business_id=8811, user=other_user, profile=other_profile,
            business_name='Other Store', business_code='OTH001', business_status='active')

        self.zone_70 = delivery_models.ZoneName.objects.create(zone_number=70, zone_name='Zone 70')
        self.zone_90 = delivery_models.ZoneName.objects.create(zone_number=90, zone_name='Zone 90')
        self.group_70 = delivery_models.ZoneGroup.objects.create(name='Group 70')
        self.group_70.zones.add(self.zone_70)

        staff = User.objects.create_user(
            username='tastaff', password='Staff@123', email='tastaff@test.com', is_staff=True)
        core_models.Profile.objects.create(
            user=staff, first_name='Staff', last_name='User', phone=30000003, is_staff=True,
            dept_operations=True, dept_finance=True, dept_marketing=True)
        self.staff_user = staff
        self.staff = Client()
        self.staff.force_login(staff)
        self._seq = 0

    def _driver(self, driver_id, username, code, access=True):
        user = User.objects.create_user(username=username, email=f'{username}@test.com', password='x')
        profile = core_models.Profile.objects.create(
            user=user, first_name='Test', last_name=code, phone=30000000 + driver_id,
            whatsapp=30000000 + driver_id, is_driver=True)
        driver = fleet_models.Driver.objects.create(
            driver_id=driver_id, user=user, profile=profile, driver_code=code,
            driver_phone=str(30000000 + driver_id), driver_whatsapp=str(30000000 + driver_id),
            driver_status='approved', dashboard_access_enabled=access)
        client = Client()
        client.force_login(user)
        return driver, client

    def _task(self, publish=True, public=False, driver=None, status='pending',
              business=None, zone=70, leg='single', speed='Normal'):
        self._seq += 1
        code = f'RT-{self._seq:03d}'
        business = business or self.business
        order = orders_models.Order.objects.create(
            business=business, client_order_code=code, customer_name='Rule Customer',
            customer_phone='33344455', customer_address='Doha', dl_zone=zone,
            dl_street=700, dl_building=7000, latitude=Decimal('25.2854'),
            longitude=Decimal('51.5310'), cod_amount=Decimal('0'))
        return delivery_models.DeliveryTask.objects.create(
            order=order, business=business, driver=driver, dl_task_number=code,
            dl_task_description='Rule test task', dl_task_status=status,
            dl_task_status_client='for_review', dl_task_publish=publish,
            public_pool=public, task_leg=leg, dl_speed=speed)

    def _rule(self, **kwargs):
        defaults = {'name': 'Rule', 'priority': 10, 'action': 'driver', 'driver': self.driver_a}
        defaults.update(kwargs)
        return delivery_models.TaskAssignmentRule.objects.create(**defaults)


class PoolVisibilityTests(TaskAssignmentBase):
    """The New tab shows only tasks sent to Public, to drivers with app access."""

    def test_public_task_is_in_every_app_drivers_pool(self):
        task = self._task(public=True)
        self.assertIn(task, delivery_pool_for(self.driver_a))
        self.assertIn(task, delivery_pool_for(self.driver_b))

    def test_driver_without_app_access_sees_no_pool(self):
        self._task(public=True)
        self.assertFalse(delivery_pool_for(self.driver_c).exists())

    def test_published_but_unassigned_task_is_in_nobodys_pool(self):
        task = self._task(public=False)
        self.assertNotIn(task, delivery_pool_for(self.driver_a))
        self.assertIn(task, unassigned_tasks())

    def test_task_with_a_driver_is_not_in_the_pool(self):
        task = self._task(public=True, driver=self.driver_a, status='assigned')
        self.assertNotIn(task, delivery_pool_for(self.driver_b))

    def test_new_tab_lists_public_and_hides_unassigned(self):
        public = self._task(public=True)
        hidden = self._task(public=False)
        response = self.client_a.get('/fleet/tasks/?tab=all')
        self.assertEqual(response.status_code, 200)
        body = response.content.decode()
        self.assertIn(public.dl_task_number, body)
        self.assertNotIn(hidden.dl_task_number, body)

    def test_dashboard_new_count_matches_the_pool(self):
        self._task(public=True)
        self._task(public=False)
        response = self.client_a.get('/fleet/dashboard/')
        self.assertEqual(response.context['new_tasks_count'], 1)


class ClaimEndpointTests(TaskAssignmentBase):
    """Every way a driver can take a task refuses anything that is not in Public."""

    def _self_take(self, client, task):
        return client.post('/fleet/tasks/assign/', {'task_id': task.id}).json()

    def test_self_take_from_public_succeeds(self):
        task = self._task(public=True)
        data = self._self_take(self.client_a, task)
        self.assertTrue(data['success'], data)
        task.refresh_from_db()
        self.assertEqual(task.driver_id, self.driver_a.pk)

    def test_self_take_of_unassigned_task_is_refused_and_leaves_no_claim_row(self):
        task = self._task(public=False)
        data = self._self_take(self.client_a, task)
        self.assertFalse(data['success'])
        self.assertIn('not open to all drivers', data['error'])
        self.assertFalse(delivery_models.AssignedDriver.objects.filter(dl_task=task).exists())

    def test_self_take_of_unpublished_task_leaves_no_claim_row(self):
        task = self._task(publish=False)
        data = self._self_take(self.client_a, task)
        self.assertFalse(data['success'])
        self.assertFalse(delivery_models.AssignedDriver.objects.filter(dl_task=task).exists())

    def test_driver_cannot_take_a_task_staff_gave_another_driver(self):
        task = self._task(driver=self.driver_a, status='assigned')
        data = self._self_take(self.client_b, task)
        self.assertFalse(data['success'])
        task.refresh_from_db()
        self.assertEqual(task.driver_id, self.driver_a.pk)

    def test_accept_endpoint_refuses_an_unassigned_task(self):
        task = self._task(public=False)
        data = self.client_a.post('/fleet/tasks/accept/', {'task_id': task.id}).json()
        self.assertFalse(data['success'])
        task.refresh_from_db()
        self.assertIsNone(task.driver_id)
        self.assertFalse(delivery_models.AssignedDriver.objects.filter(dl_task=task).exists())

    def test_accept_endpoint_lets_the_assigned_driver_accept(self):
        task = self._task(driver=self.driver_a, status='assigned')
        data = self.client_a.post('/fleet/tasks/accept/', {'task_id': task.id}).json()
        self.assertTrue(data['success'], data)
        task.refresh_from_db()
        self.assertEqual(task.dl_task_status, 'accepted')

    def test_scan_take_refuses_an_unassigned_task(self):
        task = self._task(public=False)
        data = self.client_a.post(
            '/fleet/tasks/scan-take/', json.dumps({'code': task.dl_task_number}),
            content_type='application/json').json()
        self.assertFalse(data['success'])
        self.assertIn('not open to all drivers', data['error'])

    def test_scan_take_claims_a_public_task(self):
        task = self._task(public=True)
        data = self.client_a.post(
            '/fleet/tasks/scan-take/', json.dumps({'code': task.dl_task_number}),
            content_type='application/json').json()
        self.assertTrue(data['success'], data)

    def test_take_scan_refuses_an_unassigned_task(self):
        task = self._task(public=False)
        data = self.client_a.post(
            '/fleet/tasks/take-scan/',
            json.dumps({'task_id': task.id, 'code': task.dl_task_number}),
            content_type='application/json').json()
        self.assertFalse(data['success'])
        task.refresh_from_db()
        self.assertIsNone(task.driver_id)

    def test_pool_block_names_the_reason(self):
        self.assertIn('not open to all drivers',
                      delivery_pool_block(self._task(public=False), self.driver_a)[1])
        self.assertIn('not published',
                      delivery_pool_block(self._task(publish=False), self.driver_a)[1])
        self.assertFalse(delivery_pool_block(self._task(public=True), self.driver_a)[0])
        self.assertTrue(delivery_pool_block(self._task(public=True), self.driver_c)[0])


class StaffAssignmentTests(TaskAssignmentBase):
    """Staff send a task to one driver, to Public, or back to Unassigned."""

    def _assign(self, task, driver_id):
        return self.staff.post(
            f'/workforce/delivery-task/{task.id}/assign-driver/',
            json.dumps({'driver_id': driver_id}), content_type='application/json').json()

    def test_assign_to_public(self):
        task = self._task(public=False)
        data = self._assign(task, 'public')
        self.assertTrue(data['success'], data)
        task.refresh_from_db()
        self.assertTrue(task.public_pool)
        self.assertIsNone(task.driver_id)
        self.assertIn(task, delivery_pool_for(self.driver_b))

    def test_assign_to_driver_publishes_and_leaves_public(self):
        task = self._task(publish=False)
        data = self._assign(task, self.driver_a.pk)
        self.assertTrue(data['success'], data)
        task.refresh_from_db()
        self.assertEqual(task.driver_id, self.driver_a.pk)
        self.assertEqual(task.dl_task_status, 'assigned')
        self.assertTrue(task.dl_task_publish)
        self.assertFalse(task.public_pool)

    def test_moving_a_driver_task_to_public_frees_it(self):
        task = self._task(driver=self.driver_a, status='assigned')
        delivery_models.AssignedDriver.objects.create(driver=self.driver_a, dl_task=task)
        self.assertTrue(self._assign(task, 'public')['success'])
        task.refresh_from_db()
        self.assertIsNone(task.driver_id)
        self.assertEqual(task.dl_task_status, 'pending')
        self.assertFalse(delivery_models.AssignedDriver.objects.filter(dl_task=task).exists())
        history = orders_models.OrderStatusHistory.objects.filter(
            order=task.order, field_name='driver_change').last()
        self.assertEqual(history.new_display, assignment.PUBLIC_LABEL)

    def test_unassign_goes_to_unassigned_not_public_and_rules_do_not_rerun(self):
        self._rule(action='public', driver=None)
        task = self._task(driver=self.driver_a, status='assigned')
        with self.captureOnCommitCallbacks(execute=True):
            data = self.staff.post(
                f'/workforce/delivery-task/{task.id}/unassign-driver/', '{}',
                content_type='application/json').json()
        self.assertTrue(data['success'], data)
        task.refresh_from_db()
        self.assertIsNone(task.driver_id)
        self.assertFalse(task.public_pool)
        self.assertIn(task, unassigned_tasks())

    def test_bulk_assign_to_public(self):
        t1, t2 = self._task(), self._task()
        data = self.staff.post(
            '/workforce/tasks/bulk-assign-driver/',
            json.dumps({'task_ids': [t1.id, t2.id], 'driver_id': 'public'}),
            content_type='application/json').json()
        self.assertTrue(data['success'], data)
        self.assertEqual(data['assigned'], 2)
        self.assertEqual(delivery_models.DeliveryTask.objects.filter(
            pk__in=[t1.id, t2.id], public_pool=True).count(), 2)

    def test_publish_lands_in_unassigned(self):
        task = self._task(publish=False, status='for_review')
        with self.captureOnCommitCallbacks(execute=True):
            data = self.staff.post(
                f'/workforce/delivery-task/{task.id}/publish-fleets/',
                content_type='application/json').json()
        self.assertTrue(data['success'], data)
        task.refresh_from_db()
        self.assertTrue(task.dl_task_publish)
        self.assertFalse(task.public_pool)
        self.assertIsNone(task.driver_id)
        self.assertIn(task, unassigned_tasks())

    def test_unpublish_takes_a_task_out_of_public(self):
        task = self._task(public=True)
        self.staff.post(f'/workforce/delivery-task/{task.id}/unpublish-fleets/')
        task.refresh_from_db()
        self.assertFalse(task.public_pool)


class RuleTests(TaskAssignmentBase):
    """Task Automation rules route a task the moment it lands in Unassigned."""

    def _publish(self, task):
        with self.captureOnCommitCallbacks(execute=True):
            task.dl_task_publish = True
            task.save()
        task.refresh_from_db()
        return task

    def test_no_rules_leaves_the_task_unassigned(self):
        task = self._publish(self._task(publish=False))
        self.assertIsNone(task.driver_id)
        self.assertFalse(task.public_pool)

    def test_driver_rule_assigns_on_publish(self):
        rule = self._rule(business=self.business)
        task = self._publish(self._task(publish=False))
        self.assertEqual(task.driver_id, self.driver_a.pk)
        self.assertEqual(task.dl_task_status, 'assigned')
        rule.refresh_from_db()
        self.assertEqual(rule.match_count, 1)
        history = orders_models.OrderStatusHistory.objects.filter(
            order=task.order, field_name='driver_change').last()
        self.assertIn('Task Automation', history.notes)

    def test_public_rule_sends_to_public(self):
        self._rule(action='public', driver=None)
        task = self._publish(self._task(publish=False))
        self.assertTrue(task.public_pool)
        self.assertIsNone(task.driver_id)

    def test_rule_for_another_client_does_not_match(self):
        self._rule(business=self.other_business)
        task = self._publish(self._task(publish=False))
        self.assertIsNone(task.driver_id)

    def test_zone_group_rule_matches_the_drop_off_zone(self):
        self._rule(zone_group=self.group_70)
        inside = self._publish(self._task(publish=False, zone=70))
        outside = self._publish(self._task(publish=False, zone=90))
        self.assertEqual(inside.driver_id, self.driver_a.pk)
        self.assertIsNone(outside.driver_id)

    def test_leg_and_speed_conditions(self):
        self._rule(task_leg='single', dl_speed='Same Day')
        normal = self._publish(self._task(publish=False, speed='Normal'))
        same_day = self._publish(self._task(publish=False, speed='Same Day'))
        self.assertIsNone(normal.driver_id)
        self.assertEqual(same_day.driver_id, self.driver_a.pk)

    def test_first_match_by_priority_wins(self):
        self._rule(name='late', priority=20, driver=self.driver_b)
        self._rule(name='early', priority=10, driver=self.driver_a)
        task = self._publish(self._task(publish=False))
        self.assertEqual(task.driver_id, self.driver_a.pk)

    def test_rule_for_driver_without_app_access_is_skipped(self):
        self._rule(name='blocked', priority=10, driver=self.driver_c)
        self._rule(name='fallback', priority=20, action='public', driver=None)
        task = self._publish(self._task(publish=False))
        self.assertIsNone(task.driver_id)
        self.assertTrue(task.public_pool)

    def test_inactive_rule_is_ignored(self):
        self._rule(is_active=False)
        task = self._publish(self._task(publish=False))
        self.assertIsNone(task.driver_id)

    def test_task_created_published_runs_the_rules(self):
        self._rule()
        with self.captureOnCommitCallbacks(execute=True):
            task = self._task(publish=True)
        task.refresh_from_db()
        self.assertEqual(task.driver_id, self.driver_a.pk)

    def test_rules_never_touch_a_task_staff_already_assigned(self):
        self._rule(driver=self.driver_b)
        task = self._task(driver=self.driver_a, status='assigned')
        self.assertIsNone(assignment.apply_rules(task.pk))
        task.refresh_from_db()
        self.assertEqual(task.driver_id, self.driver_a.pk)

    def test_bulk_publish_runs_the_rules(self):
        self._rule()
        task = self._task(publish=False, status='for_review')
        with self.captureOnCommitCallbacks(execute=True):
            data = self.staff.post(
                '/workforce/tasks/bulk-publish-fleets/', json.dumps({'task_ids': [task.id]}),
                content_type='application/json').json()
        self.assertTrue(data['success'], data)
        task.refresh_from_db()
        self.assertEqual(task.driver_id, self.driver_a.pk)

    def test_bulk_publish_leaves_finished_tasks_alone(self):
        task = self._task(publish=False, status='delivered', driver=self.driver_a)
        self.staff.post(
            '/workforce/tasks/bulk-publish-fleets/', json.dumps({'task_ids': [task.id]}),
            content_type='application/json')
        task.refresh_from_db()
        self.assertEqual(task.dl_task_status, 'delivered')
        self.assertFalse(task.dl_task_publish)

    def test_apply_to_unassigned_routes_the_backlog(self):
        waiting = self._task(public=False)
        self._rule()
        routed, looked_at = assignment.apply_rules_to_unassigned()
        self.assertEqual((routed, looked_at), (1, 1))
        waiting.refresh_from_db()
        self.assertEqual(waiting.driver_id, self.driver_a.pk)


class StaffPagesTests(TaskAssignmentBase):
    """The Task Automation page and the Unassigned list work end to end."""

    def test_task_automation_page_renders(self):
        self._rule(name='Shown rule')
        response = self.staff.get('/workforce/task-automation/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Shown rule')

    def test_create_rule(self):
        response = self.staff.post('/workforce/task-automation/', {
            'name': 'Store to A', 'priority': 5, 'is_active': 'on',
            'business': self.business.pk, 'action': 'driver', 'driver': self.driver_a.pk,
        })
        self.assertEqual(response.status_code, 302)
        rule = delivery_models.TaskAssignmentRule.objects.get(name='Store to A')
        self.assertEqual(rule.created_by, self.staff_user)
        self.assertEqual(rule.business_id, self.business.pk)

    def test_driver_rule_needs_a_driver(self):
        response = self.staff.post('/workforce/task-automation/', {
            'name': 'No driver', 'priority': 5, 'action': 'driver',
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(delivery_models.TaskAssignmentRule.objects.filter(name='No driver').exists())

    def test_public_rule_drops_any_driver(self):
        self.staff.post('/workforce/task-automation/', {
            'name': 'Public all', 'priority': 5, 'is_active': 'on',
            'action': 'public', 'driver': self.driver_a.pk,
        })
        self.assertIsNone(delivery_models.TaskAssignmentRule.objects.get(name='Public all').driver_id)

    def test_driver_without_app_access_cannot_be_picked(self):
        response = self.staff.post('/workforce/task-automation/', {
            'name': 'To C', 'priority': 5, 'action': 'driver', 'driver': self.driver_c.pk,
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(delivery_models.TaskAssignmentRule.objects.filter(name='To C').exists())

    def test_toggle_and_delete(self):
        rule = self._rule()
        self.staff.post(f'/workforce/task-automation/{rule.pk}/toggle/')
        rule.refresh_from_db()
        self.assertFalse(rule.is_active)
        self.staff.post(f'/workforce/task-automation/{rule.pk}/delete/')
        self.assertFalse(delivery_models.TaskAssignmentRule.objects.filter(pk=rule.pk).exists())

    def test_apply_button_routes_and_redirects_back(self):
        task = self._task(public=False)
        self._rule()
        response = self.staff.post('/workforce/task-automation/apply/', {'back': 'unassigned'})
        self.assertRedirects(response, '/workforce/tasks/unassigned/', fetch_redirect_response=False)
        task.refresh_from_db()
        self.assertEqual(task.driver_id, self.driver_a.pk)

    def test_unassigned_list_shows_each_pool(self):
        waiting = self._task(public=False)
        public = self._task(public=True)
        unassigned_page = self.staff.get('/workforce/tasks/unassigned/')
        self.assertEqual(unassigned_page.status_code, 200)
        self.assertEqual([t.pk for t in unassigned_page.context['dl_tasks']], [waiting.pk])
        public_page = self.staff.get('/workforce/tasks/unassigned/?pool=public')
        self.assertEqual([t.pk for t in public_page.context['dl_tasks']], [public.pk])

    def test_drivers_cannot_open_the_staff_pages(self):
        response = self.client_a.get('/workforce/task-automation/')
        self.assertNotEqual(response.status_code, 200)


class BackfillTests(TaskAssignmentBase):
    """The migration keeps today's pool takeable."""

    def test_backfill_marks_the_current_pool_public(self):
        import importlib
        from django.apps import apps

        pool_task = self._task(public=False)
        unpublished = self._task(publish=False)
        assigned = self._task(driver=self.driver_a, status='assigned')
        migration = importlib.import_module(
            'delivery.migrations.0057_public_pool_and_task_assignment_rules')
        migration.keep_current_pool_public(apps, None)

        pool_task.refresh_from_db()
        unpublished.refresh_from_db()
        assigned.refresh_from_db()
        self.assertTrue(pool_task.public_pool)
        self.assertFalse(unpublished.public_pool)
        self.assertFalse(assigned.public_pool)
