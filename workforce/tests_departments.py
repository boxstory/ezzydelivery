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
        """A shared route must never bounce staff with a permission denial. The
        staff home does redirect a marketing-only account — to that desk's own
        landing page, not away from the app — so follow it and check where it
        lands rather than insisting on a bare 200."""
        user, _ = self.make_staff('mktshared', [MKT])
        res = self.login_as(user).get(reverse('workforce:wf_dashboard'), follow=True)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(
            res.redirect_chain[-1][0] if res.redirect_chain else reverse('workforce:wf_dashboard'),
            reverse('workforce:wf_marketing_overview'))

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
        html = self.login_as(user).get(
            reverse('workforce:wf_dashboard'), follow=True).content.decode()
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

    def _outsider(self, username='newhire'):
        user = User.objects.create_user(
            username=username, password='x', email=f'{username}@gmail.com', is_staff=False)
        profile = core_models.Profile.objects.create(
            user=user, email=f'{username}@gmail.com', is_staff=False)
        return user, profile

    def test_search_lists_non_staff_account_as_candidate(self):
        _, profile = self._outsider()
        res = self.client_boss.get(reverse('workforce:staff_roles_list') + '?search=newhire%40gmail.com')
        self.assertEqual(res.status_code, 200)
        self.assertEqual([p.id for p in res.context['candidates']], [profile.id])
        self.assertContains(res, 'Add as staff')

    def test_grant_makes_account_staff_with_no_desk(self):
        user, profile = self._outsider()
        res = self.client_boss.post(reverse('workforce:staff_role_grant', args=[profile.id]))
        self.assertEqual(res.status_code, 200)
        profile.refresh_from_db()
        user.refresh_from_db()
        self.assertTrue(profile.is_staff)
        self.assertTrue(user.is_staff)
        self.assertEqual(profile.staff_departments, set())
        self.assertFalse(profile.is_superadmin)
        # Now in the staff table, no longer a candidate.
        res = self.client_boss.get(reverse('workforce:staff_roles_list') + '?search=newhire')
        self.assertEqual(res.context['candidates'], [])
        self.assertEqual([r['profile'].id for r in res.context['rows']], [profile.id])

    def test_grant_refuses_ordinary_staff(self):
        user, profile = self._outsider()
        res = self.login_as(self.worker).post(
            reverse('workforce:staff_role_grant', args=[profile.id]))
        self.assertEqual(res.status_code, 302)
        profile.refresh_from_db()
        self.assertFalse(profile.is_staff)

    def test_grant_refuses_deactivated_account(self):
        user, profile = self._outsider()
        user.is_active = False
        user.save()
        res = self.client_boss.post(reverse('workforce:staff_role_grant', args=[profile.id]))
        self.assertEqual(res.status_code, 400)
        profile.refresh_from_db()
        self.assertFalse(profile.is_staff)


class WahaInboxAccessTests(DepartmentTestMixin, TestCase):
    """The WAHA Inbox column — per-staff nginx logins for /waha/wa-chats/ only."""

    def setUp(self):
        import tempfile
        from django.test import override_settings

        self.tmp = tempfile.TemporaryDirectory()
        self.htpasswd = f'{self.tmp.name}/private/waha-inbox.htpasswd'
        self.nginx_conf = f'{self.tmp.name}/site.conf'
        with open(self.nginx_conf, 'w') as f:
            f.write('auth_basic_user_file /etc/nginx/.htpasswd;\n')
        self.settings_cm = override_settings(
            WAHA_INBOX_HTPASSWD=self.htpasswd, NGINX_SITE_CONF=self.nginx_conf)
        self.settings_cm.enable()

        self.boss, _ = self.make_staff('wahaboss', [], superadmin=True)
        self.worker, self.worker_profile = self.make_staff('wahaworker', [MKT])
        self.client_boss = self.login_as(self.boss)

    def tearDown(self):
        self.settings_cm.disable()
        self.tmp.cleanup()

    def _post(self, profile, action, client=None):
        return (client or self.client_boss).post(
            reverse('workforce:staff_waha_access', args=[profile.id]),
            data=json.dumps({'action': action}), content_type='application/json')

    def _lines(self):
        with open(self.htpasswd) as f:
            return f.read().splitlines()

    def test_grant_writes_a_verifiable_apr1_entry(self):
        import subprocess
        res = self._post(self.worker_profile, 'grant')
        self.assertEqual(res.status_code, 200)
        data = json.loads(res.content)
        self.assertEqual(data['username'], 'wahaworker')
        self.assertEqual(res['Cache-Control'], 'no-store')
        [line] = self._lines()
        user, hashed = line.split(':', 1)
        self.assertEqual(user, 'wahaworker')
        salt = hashed.split('$')[2]
        again = subprocess.run(['openssl', 'passwd', '-apr1', '-salt', salt, '-stdin'],
                               input=data['password'], capture_output=True, text=True).stdout.strip()
        self.assertEqual(again, hashed)

    def test_new_password_replaces_and_keeps_other_entries(self):
        import os
        os.makedirs(os.path.dirname(self.htpasswd))
        with open(self.htpasswd, 'w') as f:
            f.write('test:$apr1$abc$def\n')
        first = json.loads(self._post(self.worker_profile, 'grant').content)['password']
        second = json.loads(self._post(self.worker_profile, 'grant').content)['password']
        self.assertNotEqual(first, second)
        lines = self._lines()
        self.assertEqual(lines[0], 'test:$apr1$abc$def')
        self.assertEqual([l.split(':')[0] for l in lines], ['test', 'wahaworker'])

    def test_revoke_removes_the_entry(self):
        self._post(self.worker_profile, 'grant')
        res = self._post(self.worker_profile, 'revoke')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(self._lines(), [])

    def test_cannot_remove_own_login(self):
        boss_profile = self.boss.profile
        self._post(boss_profile, 'grant')
        res = self._post(boss_profile, 'revoke')
        self.assertEqual(res.status_code, 400)
        self.assertEqual([l.split(':')[0] for l in self._lines()], ['wahaboss'])

    def test_non_staff_refused(self):
        user = User.objects.create_user(username='wahaoutsider', password='x')
        profile = core_models.Profile.objects.create(user=user, is_staff=False)
        self.assertEqual(self._post(profile, 'grant').status_code, 400)

    def test_ordinary_staff_refused(self):
        res = self._post(self.worker_profile, 'grant', client=self.login_as(self.worker))
        self.assertEqual(res.status_code, 302)

    def test_page_shows_column_state_and_unwired_warning(self):
        self._post(self.worker_profile, 'grant')
        res = self.client_boss.get(reverse('workforce:staff_roles_list'))
        rows = {r['profile'].id: r['waha'] for r in res.context['rows']}
        self.assertTrue(rows[self.worker_profile.id])
        self.assertFalse(rows[self.boss.profile.id])
        self.assertContains(res, 'not live yet')
        with open(self.nginx_conf, 'w') as f:
            f.write(f'auth_basic_user_file {self.htpasswd};\n')
        res = self.client_boss.get(reverse('workforce:staff_roles_list'))
        self.assertNotContains(res, 'not live yet')


class WahaNumberColumnTests(DepartmentTestMixin, TestCase):
    """The WhatsApp number columns — which WAHA sessions a staff member opens in the inbox."""

    def setUp(self):
        self.boss, _ = self.make_staff('numcolboss', [], superadmin=True)
        self.worker, self.worker_profile = self.make_staff('numcolworker', [MKT])
        self.client_boss = self.login_as(self.boss)

    def _post(self, profile, session, enabled, client=None):
        return (client or self.client_boss).post(
            reverse('workforce:staff_waha_session', args=[profile.id]),
            data=json.dumps({'session': session, 'enabled': enabled}), content_type='application/json')

    def _numbers(self, user):
        from whatsapp.models import InboxSessionAccess
        return set(InboxSessionAccess.objects.filter(user=user).values_list('session', flat=True))

    def test_open_and_close_a_number(self):
        res = self._post(self.worker_profile, 'default', True)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(json.loads(res.content)['sessions'], ['default'])
        self.assertEqual(self._numbers(self.worker), {'default'})
        self._post(self.worker_profile, 'default', False)
        self.assertEqual(self._numbers(self.worker), set())

    def test_unknown_number_refused(self):
        self.assertEqual(self._post(self.worker_profile, 'NotARealSession', True).status_code, 400)
        self.assertEqual(self._numbers(self.worker), set())

    def test_super_admin_row_refused(self):
        self.assertEqual(self._post(self.boss.profile, 'default', True).status_code, 400)

    def test_ordinary_staff_refused(self):
        res = self._post(self.worker_profile, 'default', True, client=self.login_as(self.worker))
        self.assertEqual(res.status_code, 302)
        self.assertEqual(self._numbers(self.worker), set())

    def test_page_shows_number_columns_and_ticks(self):
        self._post(self.worker_profile, 'default', True)
        res = self.client_boss.get(reverse('workforce:staff_roles_list'))
        self.assertEqual([n['name'] for n in res.context['wa_numbers']], ['default'])
        rows = {r['profile'].id: r for r in res.context['rows']}
        self.assertEqual(rows[self.worker_profile.id]['numbers'], {'default'})
        self.assertTrue(rows[self.boss.profile.id]['all_numbers'])
        self.assertEqual(rows[self.worker_profile.id]['numbers_open'], 1)
        self.assertContains(res, 'data-session="default"')
        self.assertContains(res, '1 of 1')

    def test_login_popup_lists_the_numbers_it_opens(self):
        from whatsapp.models import InboxSessionAccess
        import tempfile
        from django.test import override_settings
        with tempfile.TemporaryDirectory() as tmp, override_settings(
                WAHA_INBOX_HTPASSWD=f'{tmp}/h', NGINX_SITE_CONF=f'{tmp}/c'):
            url = reverse('workforce:staff_waha_access', args=[self.worker_profile.id])
            body = json.dumps({'action': 'grant'})
            data = json.loads(self.client_boss.post(url, body, content_type='application/json').content)
            self.assertEqual(data['numbers'], [])
            InboxSessionAccess.objects.create(user=self.worker, session='default')
            data = json.loads(self.client_boss.post(url, body, content_type='application/json').content)
            self.assertEqual([n['name'] for n in data['numbers']], ['default'])


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
    /workforce/auto-triggers/ is super-admin only (since 2026-10-04). Before
    that every desk opened it and saw its own rows; these tests fail if any
    desk can read the catalogue or change a trigger or sender route again.
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

    def _desk_users(self):
        for code in (OPS, FIN, MKT):
            user, _ = self.make_staff(f'at{code}', [code])
            yield code, user
        user, _ = self.make_staff('atall', [OPS, FIN, MKT])
        yield 'all-desks', user

    # --- who can open the page ----------------------------------------

    def test_every_desk_is_refused_the_page(self):
        for code, user in self._desk_users():
            res = self.login_as(user).get(reverse('workforce:auto_triggers_list'))
            self.assertEqual(res.status_code, 302, code)

    def test_staff_with_no_department_are_refused(self):
        user, _ = self.make_staff('atnodesk', [])
        res = self.login_as(user).get(reverse('workforce:auto_triggers_list'))
        self.assertEqual(res.status_code, 302)

    def test_superadmin_sees_every_department(self):
        user, _ = self.make_staff('atboss', [], superadmin=True)
        res = self.login_as(user).get(reverse('workforce:auto_triggers_list'))
        self.assertEqual(res.status_code, 200)
        html = res.content.decode()
        for key in ('t_ops_case', 't_fin_case', 't_admin_case'):
            self.assertIn(key, html)

    def test_new_triggers_default_to_admin(self):
        fresh = core_models.AutoTriggerConfig.objects.create(
            trigger_key='t_unclassified', label='Fresh', category='system')
        self.assertEqual(fresh.department, ADMIN)

    # --- who can change anything --------------------------------------

    def test_desk_cannot_toggle_even_its_own_trigger(self):
        user, _ = self.make_staff('atops4', [OPS])
        res = self.login_as(user).post(
            reverse('workforce:auto_trigger_toggle'),
            data=json.dumps({'trigger_key': 't_ops_case'}),
            content_type='application/json', HTTP_ACCEPT='application/json')
        self.assertEqual(res.status_code, 403)
        self.ops_trigger.refresh_from_db()
        self.assertTrue(self.ops_trigger.is_enabled)

    def test_desk_cannot_edit_a_trigger(self):
        user, _ = self.make_staff('atops6', [OPS])
        res = self.login_as(user).post(
            reverse('workforce:auto_trigger_update'),
            data=json.dumps({'trigger_key': 't_ops_case', 'label': 'Hijacked'}),
            content_type='application/json', HTTP_ACCEPT='application/json')
        self.assertEqual(res.status_code, 403)
        self.ops_trigger.refresh_from_db()
        self.assertEqual(self.ops_trigger.label, 'Ops Case Trigger')

    def test_desk_cannot_toggle_a_sender_route(self):
        user, _ = self.make_staff('atmkt7', [MKT])
        res = self.login_as(user).post(
            reverse('workforce:whatsapp_sender_route_toggle'),
            data=json.dumps({'section': 'marketing_campaigns'}),
            content_type='application/json', HTTP_ACCEPT='application/json')
        self.assertEqual(res.status_code, 403)

    def test_superadmin_toggles_a_trigger(self):
        user, _ = self.make_staff('atboss2', [], superadmin=True)
        res = self.login_as(user).post(
            reverse('workforce:auto_trigger_toggle'),
            data=json.dumps({'trigger_key': 't_fin_case'}),
            content_type='application/json')
        self.assertEqual(res.status_code, 200)
        self.fin_trigger.refresh_from_db()
        self.assertFalse(self.fin_trigger.is_enabled)

    # --- the menu matches ---------------------------------------------

    def test_sidebar_hides_auto_triggers_from_desks(self):
        for code, user in self._desk_users():
            html = self.login_as(user).get(reverse('workforce:wf_dashboard')).content.decode()
            self.assertNotIn('workforce_sidebar_link_auto_triggers', html, code)
            self.assertNotIn('workforce_sidebar_mob_link_auto_triggers', html, code)

    def test_sidebar_shows_auto_triggers_to_superadmin(self):
        user, _ = self.make_staff('atboss3', [], superadmin=True)
        html = self.login_as(user).get(reverse('workforce:wf_dashboard')).content.decode()
        self.assertIn('workforce_sidebar_link_auto_triggers', html)


class OnboardingMarketingViewOnlyTests(DepartmentTestMixin, TestCase):
    """
    Marketing opens the onboarding queues (2026-10-04) but only to look:
    approve / review / reject, team status, change role and the CSV export
    stay with Operations — hidden on the page AND refused by the endpoint.
    """

    def setUp(self):
        from django.utils import timezone
        from fleet.tests_opportunities import make_driver

        self.driver = make_driver('onbdriver', 9971)
        profile = self.driver.profile
        profile.first_name, profile.last_name = 'Onboard', 'Applicant'
        profile.verification_status = 'pending'
        profile.verification_applied_at = timezone.now()
        profile.save()
        self.driver.user.first_name, self.driver.user.last_name = 'Onboard', 'Applicant'
        self.driver.user.save()
        self.profile = profile

    def _queues(self):
        return [
            reverse('workforce:business_verification_list'),
            reverse('workforce:driver_verification_list'),
            reverse('workforce:user_verification_list'),
            reverse('workforce:team_verification_list'),
            reverse('workforce:view_user_driver_profile', args=[self.profile.id]),
            reverse('workforce:view_user_business_profile', args=[self.profile.id]),
        ]

    def test_marketing_opens_every_queue(self):
        user, _ = self.make_staff('onbmkt', [MKT])
        client = self.login_as(user)
        for url in self._queues():
            self.assertEqual(client.get(url).status_code, 200, url)

    def test_marketing_is_refused_every_decision(self):
        user, _ = self.make_staff('onbmkt2', [MKT])
        client = self.login_as(user)
        json_hdr = {'HTTP_ACCEPT': 'application/json'}
        for url in (
            reverse('workforce:update_verification_status', args=[self.profile.id]),
            reverse('workforce:change_user_role', args=[self.profile.id]),
            reverse('workforce:update_team_status', args=[1]),
        ):
            self.assertEqual(client.post(url, {'status': 'verified'}, **json_hdr).status_code, 403, url)
        self.assertNotEqual(
            client.get(reverse('workforce:export_driver_verification_csv')).status_code, 200)
        self.assertNotEqual(client.get(reverse('workforce:warehouses_list')).status_code, 200)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.verification_status, 'pending')

    def test_marketing_sees_no_decision_controls(self):
        user, _ = self.make_staff('onbmkt3', [MKT])
        client = self.login_as(user)
        driver_q = client.get(reverse('workforce:driver_verification_list')).content.decode()
        users_q = client.get(reverse('workforce:user_verification_list')).content.decode()
        self.assertIn('Onboard Applicant', driver_q)
        self.assertIn('Onboard Applicant', users_q)
        for html in (driver_q, users_q):
            self.assertNotIn('data-action="verify"', html)
            self.assertNotIn('data-action="under_review"', html)
            self.assertNotIn('data-action="reject"', html)
            self.assertNotIn(f'href="/workforce/drivers/{self.driver.driver_id}/"', html)
        self.assertNotIn('data-action="change_role"', users_q)
        self.assertNotIn('data-bs-target="#wfExportModal"', driver_q)
        self.assertNotIn('data-export-row', driver_q)

    def test_operations_keeps_every_control(self):
        user, _ = self.make_staff('onbops', [OPS])
        client = self.login_as(user)
        driver_q = client.get(reverse('workforce:driver_verification_list')).content.decode()
        users_q = client.get(reverse('workforce:user_verification_list')).content.decode()
        for html in (driver_q, users_q):
            self.assertIn('data-action="verify"', html)
            self.assertIn('data-action="reject"', html)
            self.assertIn(f'href="/workforce/drivers/{self.driver.driver_id}/"', html)
        self.assertIn('data-action="change_role"', users_q)
        self.assertIn('data-bs-target="#wfExportModal"', driver_q)

    def test_onboarding_menu_for_marketing_has_no_warehouse_link(self):
        user, _ = self.make_staff('onbmkt4', [MKT])
        # follow=True: marketing lands on its own overview, which carries the same sidebar.
        html = self.login_as(user).get(
            reverse('workforce:wf_dashboard'), follow=True).content.decode()
        self.assertIn('workforce_sidebar_menu_verifications', html)
        self.assertIn('workforce_sidebar_link_verify_driver', html)
        self.assertNotIn('href="/workforce/warehouses/"', html)
        self.assertIn('workforce_sidebar_mob_section_verifications', html)


class MarketingDriverDocumentTests(DepartmentTestMixin, TestCase):
    """
    Marketing works driver documents from the driver-lead page (2026-10-06): edit
    number / expiry, crop, add and verify. Delete stays with Operations.
    """

    def setUp(self):
        import datetime

        from django.utils import timezone
        from fleet.models import DriverDocument
        from fleet.tests_opportunities import make_driver

        self.driver = make_driver('docmktdriver', 9981)
        # Lead 339's QID: the image check read the expiry, nobody had typed it yet.
        self.doc = DriverDocument.objects.create(
            driver=self.driver, document_type='QID', document_no='30701200184')
        DriverDocument.objects.filter(pk=self.doc.pk).update(
            ai_status=DriverDocument.AI_MISMATCH, ai_document_no='30701200184',
            ai_expiry_date=datetime.date(2029, 7, 16), ai_checked_at=timezone.now(),
            ai_note='Expiry not entered (image shows 16 Jul 2029)')
        user, _ = self.make_staff('docmkt', [MKT])
        self.client = self.login_as(user)
        self.base = f'/workforce/drivers/{self.driver.driver_id}/document/{self.doc.pk}/'

    def test_marketing_typed_expiry_matches_the_image(self):
        resp = self.client.post(self.base + 'edit/', {
            'document_type': 'QID', 'document_no': '30701200184',
            'document_issued_from': '', 'document_expiry_date': '2029-07-16',
        }, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(resp.status_code, 200, resp.content)
        self.doc.refresh_from_db()
        self.assertEqual(str(self.doc.document_expiry_date), '2029-07-16')
        # The posted string must compare as a date, not flag "Expiry on image is 16 Jul 2029".
        self.assertEqual(self.doc.ai_status, self.doc.AI_VERIFIED, self.doc.ai_note)
        self.assertIsNotNone(self.doc.verified_at)

    def test_marketing_can_verify_by_eye(self):
        resp = self.client.post(self.base + 'verify/', {'action': 'verify'},
                                HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(resp.status_code, 200, resp.content)
        self.doc.refresh_from_db()
        self.assertIsNotNone(self.doc.verified_by_id)

    def test_marketing_cannot_delete_and_gets_json(self):
        resp = self.client.post(self.base + 'delete/', HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(resp.status_code, 403)
        self.assertIn('Department access required', resp.json()['error'])
        self.assertTrue(type(self.doc).objects.filter(pk=self.doc.pk).exists())
