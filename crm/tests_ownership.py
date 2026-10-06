"""
Purpose: Tests for CRM lead ownership — visibility, take / release / reassign rules, the idle flag and the pages that enforce them.
Used by: python manage.py test crm.tests_ownership
Notes: Profiles are created by hand — core/signals.py is never imported, so a bare User has none.
"""
from datetime import timedelta

from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone

from core.models import Profile
from crm import ownership
from crm import services as crm_services
from crm.models import STAGE_CACHE_KEY, Lead, LeadActivity

HOST = {'HTTP_HOST': 'ezzydelivery.qa', 'secure': True}


def _staff(username, **depts):
    user = User.objects.create_user(username, password='x', is_staff=True,
                                    first_name=username.title())
    Profile.objects.create(user=user, is_staff=True, **depts)
    return user


def _lead(name, owner=None, category=Lead.CATEGORY_BUSINESS, **extra):
    return Lead.objects.create(
        category=category, source=Lead.SOURCE_MANUAL, company_name=name,
        stage=crm_services.initial_stage_key(category), assigned_to=owner, **extra)


class OwnershipRuleTests(TestCase):
    def setUp(self):
        cache.delete(STAGE_CACHE_KEY)
        self.ana = _staff('ana', dept_marketing=True)
        self.bob = _staff('bob', dept_operations=True)
        self.fin = _staff('finn', dept_finance=True)
        self.boss = _staff('boss', dept_marketing=True, lead_manager=True)
        self.pool = _lead('Pool Co')
        self.anas = _lead('Ana Co', owner=self.ana)
        self.bobs = _lead('Bob Co', owner=self.bob)

    def test_non_manager_sees_own_and_pool_only(self):
        seen = set(ownership.visible_leads(Lead.objects.all(), self.ana))
        self.assertEqual(seen, {self.pool, self.anas})

    def test_manager_and_super_admin_see_everything(self):
        root = User.objects.create_user('root', is_staff=True, is_superuser=True)
        for user in (self.boss, root):
            self.assertEqual(ownership.visible_leads(Lead.objects.all(), user).count(), 3)

    def test_claim_is_first_come(self):
        ok, _ = ownership.claim_lead(self.pool, self.ana)
        self.assertTrue(ok)
        # Bob's copy of the row is stale — the conditional update must still refuse.
        stale = Lead.objects.get(pk=self.pool.pk)
        stale.assigned_to = None
        ok, message = ownership.claim_lead(stale, self.bob)
        self.assertFalse(ok)
        self.assertIn('Ana', message)
        self.pool.refresh_from_db()
        self.assertEqual(self.pool.assigned_to, self.ana)
        self.assertIsNotNone(self.pool.assigned_at)

    def test_finance_cannot_take(self):
        ok, _ = ownership.claim_lead(self.pool, self.fin)
        self.assertFalse(ok)

    def test_operations_can_take(self):
        ok, _ = ownership.claim_lead(self.pool, self.bob)
        self.assertTrue(ok)

    def test_release_only_own(self):
        self.assertFalse(ownership.release_lead(self.bobs, self.ana)[0])
        self.assertTrue(ownership.release_lead(self.anas, self.ana)[0])
        self.anas.refresh_from_db()
        self.assertIsNone(self.anas.assigned_to)
        self.assertIsNone(self.anas.assigned_at)

    def test_non_manager_cannot_hand_over(self):
        ok, message, _ = ownership.set_owner(self.anas, self.bob, self.ana)
        self.assertFalse(ok)
        ok, message, _ = ownership.set_owner(self.bobs, self.ana, self.ana)
        self.assertFalse(ok)
        self.assertIn('Bob', message)

    def test_manager_reassigns_within_the_desk(self):
        ok, _, changed = ownership.set_owner(self.anas, self.bob, self.boss)
        self.assertTrue(ok and changed)
        self.anas.refresh_from_db()
        self.assertEqual(self.anas.assigned_to, self.bob)
        # Finance holds no pool desk, so nobody can hand them a lead.
        ok, _, _ = ownership.set_owner(self.anas, self.fin, self.boss)
        self.assertFalse(ok)

    def test_save_stamps_assigned_at(self):
        self.assertIsNotNone(self.anas.assigned_at)
        lead = Lead.objects.get(pk=self.pool.pk)
        lead.assigned_to = self.bob
        lead.save(update_fields=['assigned_to', 'updated_at'])
        lead.refresh_from_db()
        self.assertIsNotNone(lead.assigned_at)
        lead.assigned_to = None
        lead.save()
        lead.refresh_from_db()
        self.assertIsNone(lead.assigned_at)

    def _age(self, lead, days):
        Lead.objects.filter(pk=lead.pk).update(assigned_at=timezone.now() - timedelta(days=days))

    def test_idle_after_seven_quiet_days(self):
        self._age(self.anas, 8)
        self.assertIn(self.anas, ownership.filter_idle(Lead.objects.all()))

    def test_owner_activity_clears_idle(self):
        self._age(self.anas, 8)
        LeadActivity.objects.create(lead=self.anas, activity_type=LeadActivity.TYPE_NOTE,
                                    body='Called', created_by=self.ana)
        self.assertNotIn(self.anas, ownership.filter_idle(Lead.objects.all()))

    def test_someone_elses_note_does_not_clear_idle(self):
        self._age(self.anas, 8)
        LeadActivity.objects.create(lead=self.anas, activity_type=LeadActivity.TYPE_NOTE,
                                    body='Nudge', created_by=self.boss)
        self.assertIn(self.anas, ownership.filter_idle(Lead.objects.all()))

    def test_fresh_take_and_closed_lead_are_not_idle(self):
        self._age(self.anas, 3)
        self._age(self.bobs, 30)
        Lead.objects.filter(pk=self.bobs.pk).update(
            stage=crm_services.closed_stage_keys(Lead.CATEGORY_BUSINESS)[0])
        self.assertEqual(list(ownership.filter_idle(Lead.objects.all())), [])

    def test_pricing_sync_never_overwrites_an_owner(self):
        from crm.tests import make_pricing_inquiry

        inquiry = make_pricing_inquiry(assigned_to=self.bob)
        lead = self.anas
        lead.pricing_enquiry = inquiry
        lead.save()
        inquiry.refresh_from_db()
        crm_services.sync_lead_from_pricing_status(inquiry)
        lead.refresh_from_db()
        self.assertEqual(lead.assigned_to, self.ana)


class OwnershipViewTests(TestCase):
    def setUp(self):
        cache.delete(STAGE_CACHE_KEY)
        self.ana = _staff('ana', dept_marketing=True)
        self.bob = _staff('bob', dept_marketing=True)
        self.pool = _lead('Pool Co')
        self.anas = _lead('Ana Co', owner=self.ana)
        self.bobs = _lead('Bob Hidden Co', owner=self.bob)
        self.client.force_login(self.ana)

    def test_list_hides_other_peoples_leads(self):
        html = self.client.get('/workforce/crm/leads/', **HOST).content.decode()
        self.assertIn('Pool Co', html)
        self.assertIn('Ana Co', html)
        self.assertNotIn('Bob Hidden Co', html)

    def test_board_hides_other_peoples_leads(self):
        html = self.client.get('/workforce/crm/leads/board/', **HOST).content.decode()
        self.assertIn('Pool Co', html)
        self.assertNotIn('Bob Hidden Co', html)

    def test_detail_of_hidden_lead_redirects(self):
        response = self.client.get(f'/workforce/crm/leads/{self.bobs.pk}/', **HOST)
        self.assertEqual(response.status_code, 302)

    def test_writes_to_hidden_lead_are_refused(self):
        response = self.client.post(f'/workforce/crm/leads/{self.bobs.pk}/add-activity/',
                                    {'body': 'sneaky'}, **HOST)
        self.assertEqual(response.status_code, 403)
        self.assertFalse(LeadActivity.objects.filter(lead=self.bobs).exists())

    def test_update_cannot_hand_lead_to_someone_else(self):
        response = self.client.post(f'/workforce/crm/leads/{self.anas.pk}/update/',
                                    {'assigned_to': self.bob.pk}, **HOST)
        self.assertEqual(response.status_code, 403)
        self.anas.refresh_from_db()
        self.assertEqual(self.anas.assigned_to, self.ana)

    def test_saving_notes_without_picker_keeps_owner(self):
        response = self.client.post(f'/workforce/crm/leads/{self.anas.pk}/update/',
                                    {'notes': 'hello', 'next_followup_at': ''}, **HOST)
        self.assertTrue(response.json()['success'])
        self.anas.refresh_from_db()
        self.assertEqual(self.anas.assigned_to, self.ana)

    def test_take_button_claims_and_returns(self):
        response = self.client.post(f'/workforce/crm/leads/{self.pool.pk}/claim/',
                                    {'next': '/workforce/crm/leads/'}, **HOST)
        self.assertRedirects(response, '/workforce/crm/leads/', fetch_redirect_response=False)
        self.pool.refresh_from_db()
        self.assertEqual(self.pool.assigned_to, self.ana)
        # Bob now cannot see it at all.
        self.client.force_login(self.bob)
        html = self.client.get('/workforce/crm/leads/', **HOST).content.decode()
        self.assertNotIn('Pool Co', html)

    def test_take_next_opens_the_newest_pool_lead(self):
        newer = _lead('Newer Pool Co')
        response = self.client.post('/workforce/crm/leads/claim-next/',
                                    {'category': Lead.CATEGORY_BUSINESS}, **HOST)
        self.assertRedirects(response, f'/workforce/crm/leads/{newer.pk}/',
                             fetch_redirect_response=False)
        newer.refresh_from_db()
        self.assertEqual(newer.assigned_to, self.ana)

    def test_release_puts_lead_back_in_pool(self):
        self.client.post(f'/workforce/crm/leads/{self.anas.pk}/release/', **HOST)
        self.anas.refresh_from_db()
        self.assertIsNone(self.anas.assigned_to)

    def test_marketing_overview_shows_my_leads(self):
        response = self.client.get('/workforce/marketing/', **HOST)
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn('mko_card_my_leads', html)
        self.assertNotIn('Bob Hidden Co', html)


class LeadManagerToggleTests(TestCase):
    def test_super_admin_can_make_someone_a_lead_manager(self):
        import json

        root = User.objects.create_user('root', password='x', is_staff=True, is_superuser=True)
        Profile.objects.create(user=root, is_staff=True, is_superadmin=True)
        ana = _staff('ana', dept_marketing=True)
        self.client.force_login(root)
        response = self.client.post(
            f'/workforce/staff-roles/{ana.profile.pk}/update/',
            data=json.dumps({'department': 'lead_manager', 'enabled': True}),
            content_type='application/json', **HOST)
        self.assertTrue(response.json()['success'])
        ana.profile.refresh_from_db()
        self.assertTrue(ana.profile.lead_manager)
        self.assertTrue(ownership.is_lead_manager(User.objects.get(pk=ana.pk)))
