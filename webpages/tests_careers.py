# Purpose: Regression cover for the two careers pages — office roles + form on /careers/, driver jobs on /careers/drivers/.
# Used by: python manage.py test webpages.tests_careers
# Notes: driver work was split onto its own page on 2026-10-02 so the fleet desk has a driver-only WhatsApp link;
#        /careers/ keeps a pointer to it, and neither page has a driver form (both link to core:join_driver_start).
#        Offer-visibility cover for the driver page lives in fleet/tests_proposals.py.

from django.test import TestCase
from django.urls import reverse

from webpages.models import Careers


class CareersPageTests(TestCase):
    """The careers page carries the office lane and still accepts an application."""

    def test_page_renders_office_lane_and_driver_pointer(self):
        r = self.client.get(reverse('webpages:careers'))
        self.assertEqual(r.status_code, 200)
        html = r.content.decode()
        for needle in ('Office roles in Doha', 'What happens next',
                       'webpages_careers_card_form',
                       # The driver lane is now a pointer, not the application itself
                       'See driver jobs', '/careers/drivers/'):
            self.assertIn(needle, html)

    def test_page_no_longer_carries_the_driver_application(self):
        """Driver intake lives on /careers/drivers/ — this page only points at it."""
        html = self.client.get(reverse('webpages:careers')).content.decode()
        self.assertNotIn('Start driver application', html)
        self.assertNotIn('webpages_careers_list_offers', html)

    def test_application_saves(self):
        r = self.client.post(reverse('webpages:careers'), {
            'full_name': 'Test Applicant',
            'email': 'applicant@example.com',
            'mobile': '33445566',
            'qid': '29912345678',
            'job': 'Business Development Executive (EZY-HR-02)',
            'self_intro': 'Five years in Doha logistics sales.',
        }, follow=True)
        self.assertEqual(r.status_code, 200)
        self.assertTrue(Careers.objects.filter(email='applicant@example.com').exists())

    def test_bad_qid_is_rejected_and_redisplayed(self):
        r = self.client.post(reverse('webpages:careers'), {
            'full_name': 'Test Applicant',
            'email': 'bad@example.com',
            'mobile': '33445566',
            'qid': '19912345678',
            'job': 'Data & Leads Generator (EZY-HR-01)',
            'self_intro': 'Hello.',
        })
        self.assertEqual(r.status_code, 200)
        self.assertFalse(Careers.objects.filter(email='bad@example.com').exists())
        self.assertIn('QID must be 11 digits', r.content.decode())


class DriverJobsPageTests(TestCase):
    """The driver jobs page is the public, indexed link shared on WhatsApp."""

    def test_page_renders_the_driver_lane(self):
        r = self.client.get(reverse('webpages:careers_drivers'))
        self.assertEqual(r.status_code, 200)
        html = r.content.decode()
        for needle in ('Driver jobs in Qatar', 'Drive with Ezzy',
                       'Start driver application', 'What you need to start',
                       'What happens after you apply'):
            self.assertIn(needle, html)

    def test_page_carries_no_office_roles_or_form(self):
        """The whole point of the split: a driver sent this link sees driver work."""
        html = self.client.get(reverse('webpages:careers_drivers')).content.decode()
        self.assertNotIn('Office roles in Doha', html)
        self.assertNotIn('Business Development Executive', html)
        self.assertNotIn('webpages_careers_form_application', html)

    def test_page_is_indexable_and_canonical(self):
        """Public and SEO-capable, not a hidden link."""
        r = self.client.get(reverse('webpages:careers_drivers'))
        html = r.content.decode()
        self.assertNotIn('noindex', html)
        self.assertIn('https://ezzydelivery.qa/careers/drivers/', html)

    def test_page_is_in_the_sitemap(self):
        r = self.client.get('/sitemap.xml')
        self.assertEqual(r.status_code, 200)
        self.assertIn('/careers/drivers/', r.content.decode())
