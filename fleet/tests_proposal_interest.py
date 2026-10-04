"""
Purpose: Drivers answering a driver proposal with "I'm interested", and the staff page that works those answers.
Used by: manage.py test fleet.tests_proposal_interest
Notes: Only an offer the driver app is actually showing (live AND show_in_driver_app) can be answered; once staff act
       on an interest the driver can no longer withdraw it themselves.
"""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from core.models import Profile
from fleet.models import DriverProposal, DriverProposalInterest
from fleet.proposals import express_interest, set_interest_status, withdraw_interest
from fleet.tests_opportunities import make_driver


def make_proposal(**over):
    fields = dict(title='Full time bike rider', status='published', published_at=timezone.now(),
                  pay_package='QAR 3,500/month', show_in_driver_app=True)
    fields.update(over)
    return DriverProposal.objects.create(**fields)


@override_settings(SECURE_SSL_REDIRECT=False, ALLOWED_HOSTS=['testserver'])
class ProposalInterestRuleTests(TestCase):

    def setUp(self):
        self.driver = make_driver('propdriver', 9951)
        self.proposal = make_proposal()

    def test_interest_is_idempotent(self):
        express_interest(self.driver, self.proposal)
        express_interest(self.driver, self.proposal)
        self.assertEqual(DriverProposalInterest.objects.filter(driver=self.driver).count(), 1)

    def test_only_offers_shown_in_the_app_can_be_answered(self):
        closed = make_proposal(title='Old', closes_at=timezone.now() - timedelta(hours=1))
        careers_only = make_proposal(title='Careers only', show_in_driver_app=False)
        self.assertEqual(express_interest(self.driver, closed)[1], 'not_live')
        self.assertEqual(express_interest(self.driver, careers_only)[1], 'not_in_app')
        self.assertFalse(DriverProposalInterest.objects.exists())

    def test_withdraw_then_interest_again_revives_the_row(self):
        interest, _ = express_interest(self.driver, self.proposal, note='first')
        withdraw_interest(self.driver, self.proposal)
        again, reason = express_interest(self.driver, self.proposal, note='second')
        self.assertIsNone(reason)
        self.assertEqual(again.pk, interest.pk)
        self.assertEqual(again.status, 'interested')
        self.assertEqual(again.note, 'second')

    def test_driver_cannot_withdraw_after_staff_acted(self):
        interest, _ = express_interest(self.driver, self.proposal)
        set_interest_status(interest, 'contacted')
        _i, reason = withdraw_interest(self.driver, self.proposal)
        self.assertEqual(reason, 'decided')
        interest.refresh_from_db()
        self.assertEqual(interest.status, 'contacted')


@override_settings(SECURE_SSL_REDIRECT=False, ALLOWED_HOSTS=['testserver'])
class ProposalInterestEndpointTests(TestCase):

    def setUp(self):
        self.driver = make_driver('propapp', 9952)
        self.proposal = make_proposal()
        self.client.force_login(self.driver.user)

    def test_driver_can_raise_and_withdraw(self):
        url = reverse('fleet:proposal_interest')
        r = self.client.post(url, {'proposal_id': self.proposal.pk, 'note': 'I have a bike'})
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json()['status'], 'interested')
        r = self.client.post(url, {'proposal_id': self.proposal.pk, 'action': 'withdraw'})
        self.assertEqual(r.json()['status'], 'withdrawn')

    def test_app_page_shows_the_button_then_the_state(self):
        page = reverse('fleet:opportunities')
        self.assertContains(self.client.get(page), f'data-proposal="{self.proposal.pk}"')
        express_interest(self.driver, self.proposal)
        self.assertContains(self.client.get(page), 'Interest sent')


@override_settings(SECURE_SSL_REDIRECT=False, ALLOWED_HOSTS=['testserver'])
class StaffProposalInterestPageTests(TestCase):

    def setUp(self):
        staff = get_user_model().objects.create_user(username='propops', password='x', is_staff=True)
        profile, _ = Profile.objects.get_or_create(user=staff)
        profile.is_staff = True
        profile.is_superadmin = True
        profile.save()
        self.staff = staff
        self.client.force_login(staff)
        self.driver = make_driver('propstaffdriver', 9953)
        self.proposal = make_proposal(title='Van driver offer')
        self.interest, _ = express_interest(self.driver, self.proposal, note='Weekends only')

    def test_list_shows_the_interested_driver(self):
        r = self.client.get(reverse('workforce:wf_driver_proposal_interests'))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'Van driver offer')
        self.assertContains(r, 'Weekends only')
        self.assertContains(r, 'https://wa.me/97412345678')

    def test_proposals_list_counts_interest(self):
        r = self.client.get(reverse('workforce:wf_driver_proposals'))
        self.assertContains(r, f'?proposal={self.proposal.pk}&amp;status=all')
        self.assertContains(r, '1 new')

    def test_status_filter_hides_closed_out_rows_by_default(self):
        set_interest_status(self.interest, 'declined')
        r = self.client.get(reverse('workforce:wf_driver_proposal_interests'))
        self.assertNotContains(r, 'Weekends only')
        r = self.client.get(reverse('workforce:wf_driver_proposal_interests'), {'status': 'declined'})
        self.assertContains(r, 'Weekends only')

    def test_update_records_status_note_and_who(self):
        back = reverse('workforce:wf_driver_proposal_interests') + '?status=all'
        r = self.client.post(
            reverse('workforce:wf_driver_proposal_interest_update', args=[self.interest.pk]),
            {'status': 'accepted', 'staff_note': 'Starts Sunday', 'next': back})
        self.assertRedirects(r, back, fetch_redirect_response=False)
        self.interest.refresh_from_db()
        self.assertEqual(self.interest.status, 'accepted')
        self.assertEqual(self.interest.staff_note, 'Starts Sunday')
        self.assertEqual(self.interest.decided_by, self.staff)

    def test_update_ignores_an_offsite_next(self):
        r = self.client.post(
            reverse('workforce:wf_driver_proposal_interest_update', args=[self.interest.pk]),
            {'status': 'contacted', 'next': 'https://evil.example/'})
        self.assertEqual(r['Location'], reverse('workforce:wf_driver_proposal_interests'))


@override_settings(SECURE_SSL_REDIRECT=False, ALLOWED_HOSTS=['testserver'])
class ProposalInterestDriverLinkTests(TestCase):
    """The driver record is an Operations page; marketing gets the name as text."""

    def setUp(self):
        self.driver = make_driver('proplinkdriver', 9954)
        express_interest(self.driver, make_proposal(title='Bike offer'), note='')

    def _as(self, username, **depts):
        user = get_user_model().objects.create_user(username=username, password='x', is_staff=True)
        profile, _ = Profile.objects.get_or_create(user=user)
        profile.is_staff = True
        for field, value in depts.items():
            setattr(profile, field, value)
        profile.save()
        self.client.force_login(user)
        r = self.client.get(reverse('workforce:wf_driver_proposal_interests'))
        self.assertEqual(r.status_code, 200)
        return r.content.decode()

    def test_marketing_sees_the_name_without_a_link(self):
        html = self._as('propmkt', dept_marketing=True)
        self.assertIn(self.driver.driver_name, html)
        self.assertNotIn(reverse('workforce:driver_detail', args=[self.driver.driver_id]), html)

    def test_operations_gets_the_link(self):
        html = self._as('propops2', dept_operations=True)
        self.assertIn(reverse('workforce:driver_detail', args=[self.driver.driver_id]), html)
