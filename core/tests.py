# Purpose: Tests for core views — main_dashboard post-login routing for team members.
# Used by: python manage.py test core

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from business import models as business_models
from core import models as core_models

User = get_user_model()


class MainDashboardTeamRoutingTest(TestCase):
    """Post-login routing for users who are not business/driver/staff.

    Such users are routed by their BusinessTeamProfile membership:
    active -> business dashboard, pending -> verification pending page,
    inactive/suspended -> blocked with a clear message (not the
    role-registration flow).
    """

    def setUp(self):
        owner = User.objects.create_user(
            username='owner', password='Owner@123', email='owner@test.com')
        owner_profile = core_models.Profile.objects.create(
            user=owner, first_name='Biz', last_name='Owner',
            phone=11111111, is_business=True,
            is_business_profile_completed=True)
        self.business = business_models.Business.objects.create(
            business_id=9000, user=owner, profile=owner_profile,
            business_name='Test Business', business_code='TBIZ',
            business_status='active')

        self.member = User.objects.create_user(
            username='member', password='Member@123', email='member@test.com')
        self.member_profile = core_models.Profile.objects.create(
            user=self.member, first_name='Team', last_name='Member',
            phone=22222222, is_profile_completed=True)
        self.client.login(username='member', password='Member@123')
        self.url = reverse('core:main_dashboard')

    def _make_membership(self, status, verifed=True):
        return business_models.BusinessTeamProfile.objects.create(
            user=self.member, profile=self.member_profile,
            business=self.business, team_role='staff',
            team_status=status, team_verifed=verifed)

    def test_active_member_goes_to_business_dashboard(self):
        self._make_membership('active')
        response = self.client.get(self.url)
        self.assertRedirects(response, reverse('business:business_dashboard'),
                             fetch_redirect_response=False)

    def test_pending_member_sees_verification_pending(self):
        self._make_membership('pending')
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'core/verification_pending.html')

    def test_inactive_member_is_blocked_with_message(self):
        self._make_membership('inactive')
        response = self.client.get(self.url)
        self.assertRedirects(response, reverse('core:profile_complete_update'),
                             fetch_redirect_response=False)
        messages = [str(m) for m in response.wsgi_request._messages]
        self.assertTrue(any('contact the business owner' in m for m in messages),
                        messages)

    def test_suspended_member_is_blocked_with_message(self):
        self._make_membership('suspended')
        response = self.client.get(self.url)
        self.assertRedirects(response, reverse('core:profile_complete_update'),
                             fetch_redirect_response=False)
        messages = [str(m) for m in response.wsgi_request._messages]
        self.assertTrue(any('contact the business owner' in m for m in messages),
                        messages)

    def test_rejected_membership_falls_through_to_registration(self):
        self._make_membership('rejected')
        response = self.client.get(self.url)
        self.assertRedirects(response, reverse('core:profile_complete_update'),
                             fetch_redirect_response=False)
        messages = [str(m) for m in response.wsgi_request._messages]
        self.assertFalse(any('contact the business owner' in m for m in messages),
                         messages)
