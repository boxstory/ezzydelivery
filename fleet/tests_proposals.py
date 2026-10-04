"""
Purpose: A driver proposal must appear on exactly the surfaces it was published to — the driver app, the careers page, or neither.
Used by: manage.py test fleet.tests_proposals
Notes: The audience rule is TWO conditions (live AND the per-surface flag), so every test here pairs a status with a
       flag rather than checking one of them. The staff console tests also pin that publishing stamps published_at once.
"""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from core import models as core_models
from core.departments import DEPARTMENT_FIELDS, MKT
from core.models import Profile
from fleet.models import Driver, DriverProposal
from fleet.proposals import careers_proposals, driver_app_proposals, live_proposals

User = get_user_model()


def make_proposal(title, **kwargs):
    defaults = {
        'status': 'published',
        'published_at': timezone.now(),
        'pay_package': 'QAR 3,500/month',
        'perks': 'Weekly payouts\nFuel allowance\n',
        'requirements': 'Valid QID\nOwn bike',
    }
    defaults.update(kwargs)
    return DriverProposal.objects.create(title=title, **defaults)


@override_settings(SECURE_SSL_REDIRECT=False, ALLOWED_HOSTS=['testserver'])
class ProposalVisibilityTests(TestCase):
    """Which proposals each surface is allowed to show."""

    def test_draft_is_live_nowhere(self):
        proposal = make_proposal('Draft offer', status='draft', published_at=None)
        self.assertFalse(proposal.is_live)
        self.assertNotIn(proposal, live_proposals())
        self.assertNotIn(proposal, driver_app_proposals())
        self.assertNotIn(proposal, careers_proposals())

    def test_closed_is_live_nowhere(self):
        proposal = make_proposal('Closed offer', status='closed')
        self.assertFalse(proposal.is_live)
        self.assertNotIn(proposal, live_proposals())

    def test_past_closing_time_is_not_live(self):
        """A closes_at in the past retires the offer without anyone touching it."""
        proposal = make_proposal(
            'Expired offer', closes_at=timezone.now() - timedelta(minutes=1))
        self.assertFalse(proposal.is_live)
        self.assertNotIn(proposal, live_proposals())

    def test_future_closing_time_is_still_live(self):
        proposal = make_proposal(
            'Open offer', closes_at=timezone.now() + timedelta(days=7))
        self.assertTrue(proposal.is_live)
        self.assertIn(proposal, live_proposals())

    def test_app_only_offer_never_reaches_careers(self):
        proposal = make_proposal(
            'App only', show_in_driver_app=True, show_on_careers=False)
        self.assertIn(proposal, driver_app_proposals())
        self.assertNotIn(proposal, careers_proposals())

    def test_careers_only_offer_never_reaches_the_app(self):
        proposal = make_proposal(
            'Careers only', show_in_driver_app=False, show_on_careers=True)
        self.assertIn(proposal, careers_proposals())
        self.assertNotIn(proposal, driver_app_proposals())

    def test_published_with_both_flags_off_shows_nowhere(self):
        proposal = make_proposal(
            'Nowhere', show_in_driver_app=False, show_on_careers=False)
        self.assertTrue(proposal.is_live)
        self.assertNotIn(proposal, driver_app_proposals())
        self.assertNotIn(proposal, careers_proposals())

    def test_display_order_comes_first(self):
        second = make_proposal('Second', display_order=5)
        first = make_proposal('First', display_order=1)
        self.assertEqual(list(live_proposals()), [first, second])

    def test_point_lists_drop_blank_lines(self):
        proposal = make_proposal('Points', perks='One\n\n  Two  \n', requirements='')
        self.assertEqual(proposal.perk_list, ['One', 'Two'])
        self.assertEqual(proposal.requirement_list, [])


@override_settings(SECURE_SSL_REDIRECT=False, ALLOWED_HOSTS=['testserver'])
class DriverJobsPageProposalTests(TestCase):
    """The public driver jobs page renders only the offers published to it.

    The offers moved off /careers/ to /careers/drivers/ so the fleet desk has a
    driver-only link to share on WhatsApp — these tests follow them.
    """

    def test_page_shows_a_published_offer(self):
        make_proposal('Full-time bike rider — Doha', ref_code='EZY-DRV-01')
        response = Client().get(reverse('webpages:careers_drivers'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Full-time bike rider')
        self.assertContains(response, 'EZY-DRV-01')
        self.assertContains(response, 'QAR 3,500/month')
        self.assertContains(response, 'Fuel allowance')

    def test_page_hides_an_app_only_offer(self):
        make_proposal('Inside the app only', show_on_careers=False)
        response = Client().get(reverse('webpages:careers_drivers'))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'Inside the app only')

    def test_page_hides_a_draft(self):
        make_proposal('Unfinished wording', status='draft', published_at=None)
        response = Client().get(reverse('webpages:careers_drivers'))
        self.assertNotContains(response, 'Unfinished wording')

    def test_page_renders_with_no_offers(self):
        """No proposals at all must not break the page or claim a vacancy."""
        response = Client().get(reverse('webpages:careers_drivers'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'driver intake is always open')
        self.assertNotContains(response, 'JobPosting')

    def test_published_offer_emits_a_job_posting(self):
        """SEO: a live offer must reach the page as JobPosting JSON-LD."""
        make_proposal('Van driver — Industrial Area', ref_code='EZY-DRV-07')
        response = Client().get(reverse('webpages:careers_drivers'))
        html = response.content.decode()
        self.assertIn('application/ld+json', html)
        self.assertIn('"@type": "JobPosting"', html)
        self.assertIn('EZY-DRV-07', html)

    def test_offers_are_no_longer_on_the_careers_page(self):
        """The split is the point: an offer must not render on /careers/ as well."""
        make_proposal('Full-time bike rider — Doha', ref_code='EZY-DRV-01')
        response = Client().get(reverse('webpages:careers'))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'Full-time bike rider')
        self.assertContains(response, '/careers/drivers/')

    def test_short_link_redirects_to_the_driver_page(self):
        """The WhatsApp-friendly alias must land on the canonical page."""
        response = Client().get('/driver-jobs/')
        self.assertEqual(response.status_code, 301)
        self.assertEqual(response['Location'], reverse('webpages:careers_drivers'))


@override_settings(SECURE_SSL_REDIRECT=False, ALLOWED_HOSTS=['testserver'])
class DriverAppProposalTests(TestCase):
    """The opportunities screen carries the app-facing offers."""

    def setUp(self):
        user = User.objects.create_user(
            username='propdriver', email='prop-driver@example.com',
            password='Str0ngPass!99')
        profile, _ = Profile.objects.get_or_create(user=user)
        profile.is_driver = True
        profile.save()
        self.driver = Driver.objects.create(
            driver_id=9941, user=user, profile=profile, driver_code='PRP9941',
            driver_phone='97412345678', driver_whatsapp='97412345678',
            driver_languages='english', driver_status='approved',
        )
        self.client = Client()
        self.client.force_login(user)

    def test_offer_shows_on_the_opportunities_screen(self):
        make_proposal('Switch to full time', headline='More drops, same zones')
        response = self.client.get(reverse('fleet:opportunities'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Switch to full time')
        self.assertContains(response, 'More drops, same zones')
        self.assertContains(response, 'Valid QID')

    def test_careers_only_offer_is_not_in_the_app(self):
        make_proposal('Recruitment advert', show_in_driver_app=False)
        response = self.client.get(reverse('fleet:opportunities'))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'Recruitment advert')

    def test_expired_offer_is_not_in_the_app(self):
        make_proposal('Last month', closes_at=timezone.now() - timedelta(hours=1))
        response = self.client.get(reverse('fleet:opportunities'))
        self.assertNotContains(response, 'Last month')


@override_settings(SECURE_SSL_REDIRECT=False, ALLOWED_HOSTS=['testserver'])
class StaffProposalConsoleTests(TestCase):
    """The marketing desk writes, publishes and retires the offers."""

    def setUp(self):
        self.user = User.objects.create_user(
            username='mktstaff', password='Staff@123',
            email='mktstaff@test.com', is_staff=True)
        core_models.Profile.objects.create(
            user=self.user, first_name='Mkt', last_name='Tester', is_staff=True,
            **{DEPARTMENT_FIELDS[MKT]: True})
        self.client = Client()
        self.client.force_login(self.user)

    def test_marketing_can_open_the_list(self):
        make_proposal('Existing offer')
        response = self.client.get(reverse('workforce:wf_driver_proposals'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Existing offer')

    def test_list_carries_the_public_driver_jobs_link(self):
        """The desk sends this link on WhatsApp, so the console must show it."""
        response = self.client.get(reverse('workforce:wf_driver_proposals'))
        html = response.content.decode()
        self.assertIn('http://testserver/careers/drivers/', html)
        self.assertIn('wa.me', html)
        self.assertIn('Copy link', html)

    def test_create_saves_the_offer(self):
        response = self.client.post(reverse('workforce:wf_driver_proposal_new'), {
            'title': 'Evening riders — Lusail',
            'ref_code': 'EZY-DRV-02',
            'headline': 'Six hours an evening',
            'pay_package': 'QAR 40/hour',
            'job_type': 'part_time',
            'vehicle_type': 'bike',
            'perks': 'Weekly payouts',
            'requirements': 'Own bike',
            'status': 'published',
            'show_in_driver_app': '1',
            'show_on_careers': '1',
            'display_order': '3',
        })
        self.assertRedirects(response, reverse('workforce:wf_driver_proposals'))

        proposal = DriverProposal.objects.get(title='Evening riders — Lusail')
        self.assertEqual(proposal.job_type, 'part_time')
        self.assertEqual(proposal.display_order, 3)
        self.assertEqual(proposal.created_by, self.user)
        self.assertIsNotNone(proposal.published_at)
        self.assertTrue(proposal.is_live)

    def test_unchecked_audience_boxes_turn_the_surface_off(self):
        """An HTML checkbox posts nothing when it is off — the view must read that."""
        self.client.post(reverse('workforce:wf_driver_proposal_new'), {
            'title': 'App only offer',
            'status': 'published',
            'show_in_driver_app': '1',
        })
        proposal = DriverProposal.objects.get(title='App only offer')
        self.assertTrue(proposal.show_in_driver_app)
        self.assertFalse(proposal.show_on_careers)

    def test_a_negative_display_order_is_clamped(self):
        self.client.post(reverse('workforce:wf_driver_proposal_new'), {
            'title': 'Clamped', 'status': 'draft', 'display_order': '-4',
        })
        self.assertEqual(DriverProposal.objects.get(title='Clamped').display_order, 0)

    def test_publishing_stamps_published_at_once(self):
        proposal = make_proposal('Draft first', status='draft', published_at=None)
        self.client.post(
            reverse('workforce:wf_driver_proposal_status', args=[proposal.pk]),
            {'status': 'published'})
        proposal.refresh_from_db()
        first_stamp = proposal.published_at
        self.assertIsNotNone(first_stamp)

        # A later wording edit is not a republication.
        self.client.post(
            reverse('workforce:wf_driver_proposal_edit', args=[proposal.pk]),
            {'title': 'Draft first', 'status': 'published'})
        proposal.refresh_from_db()
        self.assertEqual(proposal.published_at, first_stamp)

    def test_closing_takes_it_off_both_surfaces(self):
        proposal = make_proposal('Retire me')
        self.client.post(
            reverse('workforce:wf_driver_proposal_status', args=[proposal.pk]),
            {'status': 'closed'})
        proposal.refresh_from_db()
        self.assertEqual(proposal.status, 'closed')
        self.assertNotIn(proposal, driver_app_proposals())
        self.assertNotIn(proposal, careers_proposals())

    def test_delete_removes_it(self):
        proposal = make_proposal('Delete me')
        self.client.post(
            reverse('workforce:wf_driver_proposal_delete', args=[proposal.pk]))
        self.assertFalse(DriverProposal.objects.filter(pk=proposal.pk).exists())

    def test_a_get_never_deletes(self):
        proposal = make_proposal('Keep me')
        self.client.get(
            reverse('workforce:wf_driver_proposal_delete', args=[proposal.pk]))
        self.assertTrue(DriverProposal.objects.filter(pk=proposal.pk).exists())

    def test_title_is_required(self):
        response = self.client.post(reverse('workforce:wf_driver_proposal_new'),
                                    {'title': '   ', 'status': 'published'})
        self.assertEqual(response.status_code, 302)
        self.assertFalse(DriverProposal.objects.exists())


@override_settings(SECURE_SSL_REDIRECT=False, ALLOWED_HOSTS=['testserver'])
class ProposalAccessTests(TestCase):
    """The console is staff-only, and only the marketing desk's."""

    def test_anonymous_is_sent_to_login(self):
        response = Client().get(reverse('workforce:wf_driver_proposals'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/accounts/login/', response.url)

    def test_a_non_marketing_desk_is_refused(self):
        user = User.objects.create_user(
            username='finstaff', password='Staff@123',
            email='finstaff@test.com', is_staff=True)
        core_models.Profile.objects.create(
            user=user, first_name='Fin', last_name='Tester', is_staff=True,
            **{DEPARTMENT_FIELDS['fin']: True})
        client = Client()
        client.force_login(user)
        response = client.get(reverse('workforce:wf_driver_proposals'))
        self.assertEqual(response.status_code, 302)
