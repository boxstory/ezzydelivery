"""
Purpose: Tests for staff department sub-roles — the URL map, the gating middleware, the sidebar, and the Staff Roles console.
Used by: python manage.py test workforce.tests_departments
Notes: test_every_workforce_route_is_classified is the load-bearing one — the middleware fails closed, so an
       unclassified route would 302 staff away from a working page. That test makes it a CI failure instead.
"""

import json

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import get_resolver, reverse

from core import models as core_models
from core.departments import (
    ADMIN, ASSIGNABLE_DEPARTMENTS, DEPARTMENT_FIELDS, FIN, MKT, OPS, SHARED,
    URL_DEPARTMENTS, can_access, departments_for, user_departments,
)

User = get_user_model()


def _workforce_route_names():
    """Every url_name registered under the workforce namespace."""
    ns = get_resolver().namespace_dict['workforce'][1]
    return {k for k in ns.reverse_dict if isinstance(k, str)}


class DepartmentMapTests(TestCase):
    """The map itself — completeness and internal consistency."""

    def test_every_workforce_route_is_classified(self):
        routes = _workforce_route_names()
        unmapped = sorted(routes - set(URL_DEPARTMENTS))
        self.assertEqual(
            unmapped, [],
            "These workforce routes have no department. StaffDepartmentMiddleware "
            "fails closed, so staff would be redirected away from them. Classify "
            "them in core/departments.py:\n  " + "\n  ".join(unmapped),
        )

    def test_map_has_no_stale_entries(self):
        routes = _workforce_route_names()
        stale = sorted(set(URL_DEPARTMENTS) - routes)
        self.assertEqual(
            stale, [],
            "These names are classified but no longer exist in workforce/urls.py: "
            + ", ".join(stale),
        )

    def test_every_department_code_is_known(self):
        valid = set(ASSIGNABLE_DEPARTMENTS) | {ADMIN, SHARED}
        for name, depts in URL_DEPARTMENTS.items():
            self.assertTrue(
                depts <= valid,
                f"{name} references unknown department(s): {depts - valid}",
            )

    def test_shared_routes_are_shared_only(self):
        """A route is either everyone's or someone's — mixing the two is a bug."""
        for name, depts in URL_DEPARTMENTS.items():
            if SHARED in depts:
                self.assertEqual(
                    depts, frozenset({SHARED}),
                    f"{name} is SHARED but also lists {depts - {SHARED}}",
                )

    def test_unknown_route_is_refused(self):
        self.assertIsNone(departments_for('no_such_route_name'))
        self.assertFalse(can_access(None, 'no_such_route_name'))

    def test_finance_pages_are_not_in_operations(self):
        """Spot-check the split that matters most for money screens."""
        for name in ('cod_business_settlement_report', 'driver_payout_create',
                     'cod_ledger', 'earnings_verification'):
            self.assertEqual(URL_DEPARTMENTS[name], frozenset({FIN}), name)

    def test_dashboard_is_shared(self):
        """Everyone needs a landing page or the deny-redirect loops."""
        self.assertEqual(URL_DEPARTMENTS['wf_dashboard'], frozenset({SHARED}))


class DepartmentTestMixin:
    """Builds staff users holding specific departments."""

    def make_staff(self, username, departments=(), superadmin=False):
        user = User.objects.create_user(
            username=username, password='Staff@123',
            email=f'{username}@test.com', is_staff=True)
        fields = {DEPARTMENT_FIELDS[code]: True for code in departments}
        profile = core_models.Profile.objects.create(
            user=user, first_name=username.title(), last_name='Tester',
            is_staff=True, is_superadmin=superadmin, **fields)
        return user, profile

    def login_as(self, user):
        client = Client()
        client.force_login(user)
        return client


class UserDepartmentsTests(DepartmentTestMixin, TestCase):

    def test_single_department(self):
        user, _ = self.make_staff('opsonly', [OPS])
        self.assertEqual(user_departments(user), {OPS})

    def test_multi_department(self):
        user, _ = self.make_staff('opsfin', [OPS, FIN])
        self.assertEqual(user_departments(user), {OPS, FIN})

    def test_superadmin_holds_everything(self):
        user, _ = self.make_staff('boss', [], superadmin=True)
        self.assertEqual(user_departments(user), set(ASSIGNABLE_DEPARTMENTS) | {ADMIN})

    def test_staff_with_no_department(self):
        user, _ = self.make_staff('nodesk', [])
        self.assertEqual(user_departments(user), set())

    def test_profile_property_matches_helper(self):
        user, profile = self.make_staff('mixed', [FIN, MKT])
        self.assertEqual(profile.staff_departments, user_departments(user))
        self.assertEqual(
            sorted(profile.get_department_labels()), ['Finance', 'Marketing'])


class MiddlewareGatingTests(DepartmentTestMixin, TestCase):
    """The actual /workforce/ enforcement."""

    def test_ops_staff_reach_operations_pages(self):
        user, _ = self.make_staff('ops1', [OPS])
        res = self.login_as(user).get(reverse('workforce:wf_orders_all'))
        self.assertEqual(res.status_code, 200)

    def test_ops_staff_blocked_from_finance(self):
        user, _ = self.make_staff('ops2', [OPS])
        res = self.login_as(user).get(reverse('workforce:workforce_finance_dashboard'))
        self.assertEqual(res.status_code, 302)
        self.assertIn(reverse('workforce:wf_dashboard'), res['Location'])

    def test_finance_staff_reach_finance_pages(self):
        user, _ = self.make_staff('fin1', [FIN])
        res = self.login_as(user).get(reverse('workforce:cod_ledger'))
        self.assertEqual(res.status_code, 200)

    def test_finance_staff_blocked_from_orders(self):
        user, _ = self.make_staff('fin2', [FIN])
        res = self.login_as(user).get(reverse('workforce:wf_orders_all'))
        self.assertEqual(res.status_code, 302)

    def test_marketing_staff_blocked_from_both(self):
        user, _ = self.make_staff('mkt1', [MKT])
        client = self.login_as(user)
        self.assertEqual(
            client.get(reverse('workforce:wf_orders_all')).status_code, 302)
        self.assertEqual(
            client.get(reverse('workforce:cod_ledger')).status_code, 302)

    def test_multi_department_staff_reach_both(self):
        user, _ = self.make_staff('both', [OPS, FIN])
        client = self.login_as(user)
        self.assertEqual(
            client.get(reverse('workforce:wf_orders_all')).status_code, 200)
        self.assertEqual(
            client.get(reverse('workforce:cod_ledger')).status_code, 200)

    def test_superadmin_bypasses_departments(self):
        user, _ = self.make_staff('boss2', [], superadmin=True)
        client = self.login_as(user)
        for name in ('wf_orders_all', 'cod_ledger', 'crm_leads_list', 'auto_triggers_list'):
            self.assertEqual(
                client.get(reverse(f'workforce:{name}')).status_code, 200, name)

    def test_shared_routes_open_to_any_department(self):
        user, _ = self.make_staff('mktshared', [MKT])
        res = self.login_as(user).get(reverse('workforce:wf_dashboard'))
        self.assertEqual(res.status_code, 200)

    def test_staff_with_no_department_still_reach_the_dashboard(self):
        """No desk must not mean no landing page, or the deny-redirect loops."""
        user, _ = self.make_staff('nodesk2', [])
        client = self.login_as(user)
        self.assertEqual(
            client.get(reverse('workforce:wf_dashboard')).status_code, 200)
        self.assertEqual(
            client.get(reverse('workforce:wf_orders_all')).status_code, 302)

    def test_ajax_request_gets_json_403_not_a_redirect(self):
        user, _ = self.make_staff('ops3', [OPS])
        res = self.login_as(user).get(
            reverse('workforce:cod_ledger'), HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(res.status_code, 403)
        self.assertFalse(json.loads(res.content)['success'])

    def test_admin_only_routes_refuse_ordinary_departments(self):
        user, _ = self.make_staff('allthree', [OPS, FIN, MKT])
        res = self.login_as(user).get(reverse('workforce:staff_roles_list'))
        self.assertEqual(res.status_code, 302)

    def test_non_workforce_paths_are_untouched(self):
        """The middleware must not gate anything outside /workforce/."""
        user, _ = self.make_staff('ops4', [OPS])
        res = self.login_as(user).get('/')
        self.assertNotEqual(res.status_code, 403)


class SidebarRenderingTests(DepartmentTestMixin, TestCase):
    """Staff should not be shown links their department cannot open."""

    def test_ops_sidebar_hides_finance_links(self):
        user, _ = self.make_staff('ops5', [OPS])
        html = self.login_as(user).get(reverse('workforce:wf_dashboard')).content.decode()
        self.assertIn(reverse('workforce:wf_orders_all'), html)
        self.assertNotIn(reverse('workforce:cod_ledger'), html)
        self.assertNotIn(reverse('workforce:crm_leads_board'), html)

    def test_finance_sidebar_hides_operations_links(self):
        user, _ = self.make_staff('fin3', [FIN])
        html = self.login_as(user).get(reverse('workforce:wf_dashboard')).content.decode()
        self.assertIn(reverse('workforce:cod_ledger'), html)
        self.assertNotIn(reverse('workforce:wf_orders_all'), html)

    def test_marketing_sidebar_shows_crm(self):
        user, _ = self.make_staff('mkt2', [MKT])
        html = self.login_as(user).get(reverse('workforce:wf_dashboard')).content.decode()
        self.assertIn(reverse('workforce:crm_leads_board'), html)
        self.assertNotIn(reverse('workforce:cod_ledger'), html)

    def test_staff_roles_link_is_superadmin_only(self):
        ops, _ = self.make_staff('ops6', [OPS])
        boss, _ = self.make_staff('boss3', [], superadmin=True)
        ops_html = self.login_as(ops).get(reverse('workforce:wf_dashboard')).content.decode()
        boss_html = self.login_as(boss).get(reverse('workforce:wf_dashboard')).content.decode()
        self.assertNotIn(reverse('workforce:staff_roles_list'), ops_html)
        self.assertIn(reverse('workforce:staff_roles_list'), boss_html)


class StaffRolesConsoleTests(DepartmentTestMixin, TestCase):
    """The super-admin page that assigns the departments."""

    def setUp(self):
        self.boss, _ = self.make_staff('boss4', [], superadmin=True)
        self.worker, self.worker_profile = self.make_staff('worker', [OPS])
        self.client_boss = self.login_as(self.boss)

    def test_page_loads_for_superadmin(self):
        res = self.client_boss.get(reverse('workforce:staff_roles_list'))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, 'Staff Roles')

    def test_page_refuses_ordinary_staff(self):
        res = self.login_as(self.worker).get(reverse('workforce:staff_roles_list'))
        self.assertEqual(res.status_code, 302)

    def test_grant_department(self):
        res = self.client_boss.post(
            reverse('workforce:staff_role_update', args=[self.worker_profile.id]),
            data=json.dumps({'department': FIN, 'enabled': True}),
            content_type='application/json')
        self.assertEqual(res.status_code, 200)
        self.assertTrue(json.loads(res.content)['success'])
        self.worker_profile.refresh_from_db()
        self.assertTrue(self.worker_profile.dept_finance)
        self.assertEqual(self.worker_profile.staff_departments, {OPS, FIN})

    def test_revoke_department(self):
        res = self.client_boss.post(
            reverse('workforce:staff_role_update', args=[self.worker_profile.id]),
            data=json.dumps({'department': OPS, 'enabled': False}),
            content_type='application/json')
        self.assertEqual(res.status_code, 200)
        self.worker_profile.refresh_from_db()
        self.assertEqual(self.worker_profile.staff_departments, set())

    def test_granted_department_takes_effect_immediately(self):
        """The point of the page: the user can open the page straight after."""
        worker_client = self.login_as(self.worker)
        self.assertEqual(
            worker_client.get(reverse('workforce:cod_ledger')).status_code, 302)
        self.client_boss.post(
            reverse('workforce:staff_role_update', args=[self.worker_profile.id]),
            data=json.dumps({'department': FIN, 'enabled': True}),
            content_type='application/json')
        self.assertEqual(
            worker_client.get(reverse('workforce:cod_ledger')).status_code, 200)

    def test_unknown_department_rejected(self):
        res = self.client_boss.post(
            reverse('workforce:staff_role_update', args=[self.worker_profile.id]),
            data=json.dumps({'department': 'legal', 'enabled': True}),
            content_type='application/json')
        self.assertEqual(res.status_code, 400)

    def test_superadmin_row_cannot_be_edited(self):
        other, other_profile = self.make_staff('boss5', [], superadmin=True)
        res = self.client_boss.post(
            reverse('workforce:staff_role_update', args=[other_profile.id]),
            data=json.dumps({'department': FIN, 'enabled': False}),
            content_type='application/json')
        self.assertEqual(res.status_code, 400)
        other_profile.refresh_from_db()
        self.assertFalse(other_profile.dept_finance)

    def test_non_staff_profile_cannot_be_given_a_department(self):
        user = User.objects.create_user(username='outsider', password='x', is_staff=False)
        profile = core_models.Profile.objects.create(user=user, is_staff=False)
        res = self.client_boss.post(
            reverse('workforce:staff_role_update', args=[profile.id]),
            data=json.dumps({'department': OPS, 'enabled': True}),
            content_type='application/json')
        self.assertEqual(res.status_code, 400)
        profile.refresh_from_db()
        self.assertFalse(profile.dept_operations)

    def test_get_is_not_allowed_on_the_update_endpoint(self):
        res = self.client_boss.get(
            reverse('workforce:staff_role_update', args=[self.worker_profile.id]))
        self.assertEqual(res.status_code, 405)

    def test_department_filter(self):
        res = self.client_boss.get(reverse('workforce:staff_roles_list') + '?dept=none')
        self.assertEqual(res.status_code, 200)
        self.assertNotContains(res, self.worker_profile.user_number)


class PageOverrideTests(DepartmentTestMixin, TestCase):
    """Super admins can move a page between desks, switch it off, or classify it."""

    def setUp(self):
        from core.departments import clear_override_cache
        clear_override_cache()
        self.boss, _ = self.make_staff('pageboss', [], superadmin=True)
        self.ops, _ = self.make_staff('pageops', [OPS])
        self.fin, _ = self.make_staff('pagefin', [FIN])
        self.client_boss = self.login_as(self.boss)

    def tearDown(self):
        from core.departments import clear_override_cache
        clear_override_cache()

    def _update(self, url_name, departments, enabled=True):
        return self.client_boss.post(
            reverse('workforce:staff_page_update'),
            data=json.dumps({
                'url_name': url_name, 'departments': departments, 'enabled': enabled}),
            content_type='application/json')

    def test_console_loads_for_superadmin(self):
        res = self.client_boss.get(reverse('workforce:staff_pages_list'))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, 'Staff Pages')

    def test_console_refuses_ordinary_staff(self):
        res = self.login_as(self.ops).get(reverse('workforce:staff_pages_list'))
        self.assertEqual(res.status_code, 302)

    def test_moving_a_page_changes_who_can_open_it(self):
        """The whole point: move cod_ledger to Operations and ops staff get in."""
        ops_client = self.login_as(self.ops)
        self.assertEqual(ops_client.get(reverse('workforce:cod_ledger')).status_code, 302)

        res = self._update('cod_ledger', [OPS])
        self.assertEqual(res.status_code, 200)
        self.assertTrue(json.loads(res.content)['success'])

        self.assertEqual(ops_client.get(reverse('workforce:cod_ledger')).status_code, 200)
        # ...and Finance loses it, because the override replaces the default.
        self.assertEqual(
            self.login_as(self.fin).get(reverse('workforce:cod_ledger')).status_code, 302)

    def test_page_can_be_given_to_two_departments(self):
        self._update('cod_ledger', [OPS, FIN])
        self.assertEqual(
            self.login_as(self.ops).get(reverse('workforce:cod_ledger')).status_code, 200)
        self.assertEqual(
            self.login_as(self.fin).get(reverse('workforce:cod_ledger')).status_code, 200)

    def test_switching_a_page_off_blocks_its_own_department(self):
        self._update('cod_ledger', [FIN], enabled=False)
        self.assertEqual(
            self.login_as(self.fin).get(reverse('workforce:cod_ledger')).status_code, 302)

    def test_superadmin_can_still_open_a_disabled_page(self):
        """Otherwise nobody could switch it back on."""
        self._update('cod_ledger', [FIN], enabled=False)
        self.assertEqual(
            self.client_boss.get(reverse('workforce:cod_ledger')).status_code, 200)

    def test_page_with_no_department_is_blocked_for_everyone_but_superadmin(self):
        self._update('cod_ledger', [])
        self.assertEqual(
            self.login_as(self.fin).get(reverse('workforce:cod_ledger')).status_code, 302)
        self.assertEqual(
            self.client_boss.get(reverse('workforce:cod_ledger')).status_code, 200)

    def test_shared_grants_every_department(self):
        self._update('cod_ledger', [SHARED])
        self.assertEqual(
            self.login_as(self.ops).get(reverse('workforce:cod_ledger')).status_code, 200)

    def test_shared_cannot_be_combined_with_a_desk(self):
        res = self._update('cod_ledger', [SHARED, FIN])
        self.assertEqual(res.status_code, 400)

    def test_unknown_department_rejected(self):
        res = self._update('cod_ledger', ['legal'])
        self.assertEqual(res.status_code, 400)

    def test_unknown_route_rejected(self):
        res = self._update('no_such_route', [OPS])
        self.assertEqual(res.status_code, 400)

    def test_restoring_the_default_clears_the_override(self):
        from core.models import PageDepartment

        self._update('cod_ledger', [OPS])
        self.assertTrue(PageDepartment.objects.filter(url_name='cod_ledger').exists())

        res = self._update('cod_ledger', [FIN])  # back to the shipped default
        self.assertEqual(res.status_code, 200)
        self.assertFalse(json.loads(res.content)['overridden'])
        self.assertFalse(PageDepartment.objects.filter(url_name='cod_ledger').exists())

    def test_classifying_a_route_outside_workforce_starts_enforcing_it(self):
        """
        Routes outside /workforce/ are ungated until a super admin classifies
        one — opt-in, so no app is silently locked down.
        """
        from core.departments import is_overridden

        self.assertFalse(is_overridden('inventory_list'))
        res = self._update('inventory_list', [FIN])
        self.assertEqual(res.status_code, 200)
        self.assertTrue(is_overridden('inventory_list'))
        self.assertEqual(
            self.login_as(self.ops).get(reverse('warehouse:inventory_list')).status_code, 302)
        self.assertEqual(
            self.login_as(self.fin).get(reverse('warehouse:inventory_list')).status_code, 200)

    def test_override_cache_is_dropped_on_save(self):
        """A stale cache would leave the old assignment in force after an edit."""
        from core.departments import departments_for

        self.assertEqual(departments_for('cod_ledger'), frozenset({FIN}))
        self._update('cod_ledger', [MKT])
        self.assertEqual(departments_for('cod_ledger'), frozenset({MKT}))

    def test_unclassified_filter_lists_routes_without_a_desk(self):
        res = self.client_boss.get(reverse('workforce:staff_pages_list') + '?dept=unassigned')
        self.assertEqual(res.status_code, 200)
        # Warehouse routes ship unclassified, so the bucket is not empty.
        self.assertContains(res, 'inventory_list')

    def test_get_not_allowed_on_update(self):
        res = self.client_boss.get(reverse('workforce:staff_page_update'))
        self.assertEqual(res.status_code, 405)


class AutoTriggerDepartmentTests(DepartmentTestMixin, TestCase):
    """
    /workforce/auto-triggers/ is open to every desk but shows only that desk's
    rows. These tests are the guarantee behind that sentence — if the page ever
    leaks another department's triggers, or lets a desk toggle them, they fail.
    """

    def setUp(self):
        self.ops_trigger = core_models.AutoTriggerConfig.objects.create(
            trigger_key='t_ops_case', label='Ops Case Trigger',
            category='system', department=OPS)
        self.fin_trigger = core_models.AutoTriggerConfig.objects.create(
            trigger_key='t_fin_case', label='Fin Case Trigger',
            category='system', department=FIN)
        self.admin_trigger = core_models.AutoTriggerConfig.objects.create(
            trigger_key='t_admin_case', label='Admin Case Trigger',
            category='system', department=ADMIN)

    # --- what each desk can see ---------------------------------------

    def test_ops_staff_open_the_page(self):
        user, _ = self.make_staff('atops', [OPS])
        res = self.login_as(user).get(reverse('workforce:auto_triggers_list'))
        self.assertEqual(res.status_code, 200)

    def test_ops_staff_see_only_ops_triggers(self):
        user, _ = self.make_staff('atops2', [OPS])
        html = self.login_as(user).get(
            reverse('workforce:auto_triggers_list')).content.decode()
        self.assertIn('t_ops_case', html)
        self.assertNotIn('t_fin_case', html)
        self.assertNotIn('t_admin_case', html)

    def test_finance_staff_see_only_finance_triggers(self):
        user, _ = self.make_staff('atfin', [FIN])
        html = self.login_as(user).get(
            reverse('workforce:auto_triggers_list')).content.decode()
        self.assertIn('t_fin_case', html)
        self.assertNotIn('t_ops_case', html)

    def test_superadmin_sees_every_department(self):
        user, _ = self.make_staff('atboss', [], superadmin=True)
        html = self.login_as(user).get(
            reverse('workforce:auto_triggers_list')).content.decode()
        for key in ('t_ops_case', 't_fin_case', 't_admin_case'):
            self.assertIn(key, html)

    def test_staff_with_no_department_are_refused(self):
        user, _ = self.make_staff('atnodesk', [])
        res = self.login_as(user).get(reverse('workforce:auto_triggers_list'))
        self.assertEqual(res.status_code, 302)

    def test_new_triggers_default_to_admin_only(self):
        """A trigger nobody classified must not surface on a desk by accident."""
        fresh = core_models.AutoTriggerConfig.objects.create(
            trigger_key='t_unclassified', label='Fresh', category='system')
        self.assertEqual(fresh.department, ADMIN)
        user, _ = self.make_staff('atops3', [OPS])
        html = self.login_as(user).get(
            reverse('workforce:auto_triggers_list')).content.decode()
        self.assertNotIn('t_unclassified', html)

    # --- what each desk can change ------------------------------------

    def test_desk_toggles_its_own_trigger(self):
        user, _ = self.make_staff('atops4', [OPS])
        res = self.login_as(user).post(
            reverse('workforce:auto_trigger_toggle'),
            data=json.dumps({'trigger_key': 't_ops_case'}),
            content_type='application/json')
        self.assertEqual(res.status_code, 200)
        self.ops_trigger.refresh_from_db()
        self.assertFalse(self.ops_trigger.is_enabled)

    def test_desk_cannot_toggle_another_departments_trigger(self):
        user, _ = self.make_staff('atops5', [OPS])
        res = self.login_as(user).post(
            reverse('workforce:auto_trigger_toggle'),
            data=json.dumps({'trigger_key': 't_fin_case'}),
            content_type='application/json')
        self.assertEqual(res.status_code, 403)
        self.fin_trigger.refresh_from_db()
        self.assertTrue(self.fin_trigger.is_enabled)

    def test_desk_cannot_edit_another_departments_trigger(self):
        user, _ = self.make_staff('atops6', [OPS])
        res = self.login_as(user).post(
            reverse('workforce:auto_trigger_update'),
            data=json.dumps({'trigger_key': 't_fin_case', 'label': 'Hijacked'}),
            content_type='application/json')
        self.assertEqual(res.status_code, 403)
        self.fin_trigger.refresh_from_db()
        self.assertEqual(self.fin_trigger.label, 'Fin Case Trigger')

    # --- sender routes are split the same way -------------------------

    def test_ops_owns_the_orders_route_only(self):
        user, _ = self.make_staff('atops7', [OPS])
        client = self.login_as(user)
        html = client.get(reverse('workforce:auto_triggers_list')).content.decode()
        self.assertIn('route_orders_tasks', html)
        self.assertNotIn('route_marketing_campaigns', html)

        self.assertEqual(client.post(
            reverse('workforce:whatsapp_sender_route_toggle'),
            data=json.dumps({'section': 'orders_tasks'}),
            content_type='application/json').status_code, 200)
        self.assertEqual(client.post(
            reverse('workforce:whatsapp_sender_route_toggle'),
            data=json.dumps({'section': 'marketing_campaigns'}),
            content_type='application/json').status_code, 403)

    def test_marketing_sees_its_own_routes(self):
        user, _ = self.make_staff('atmkt', [MKT])
        html = self.login_as(user).get(
            reverse('workforce:auto_triggers_list')).content.decode()
        self.assertIn('route_marketing_campaigns', html)
        self.assertIn('route_crm_leads', html)
        self.assertNotIn('route_orders_tasks', html)
